"""scopecheck / fabric_ws: everything lands in the one resource group, and nothing is adopted or deleted that is not ours.

Offline: synthetic compiled templates and inventories. Names and ids are labels.
"""
import copy
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import fabric_ws  # noqa: E402
import scopecheck as sc  # noqa: E402
import wsconfig  # noqa: E402

LOC = "swedencentral"


def tpl(resources=None, allowed=(LOC,), params=None):
    p = {"location": {"type": "string", "allowedValues": list(allowed)}}
    p.update(params or {})
    return {"parameters": p, "resources": resources if resources is not None else [
        {"type": "Microsoft.Storage/storageAccounts", "name": "[format('st{0}', parameters('env'))]"}]}


def module(name, inner, **extra):
    return {"type": "Microsoft.Resources/deployments", "name": name, "properties": {"template": {"resources": inner}}, **extra}


def role(scope=None):
    r = {"type": "Microsoft.Authorization/roleAssignments", "name": "[guid('x')]"}
    if scope is not None:
        r["scope"] = scope
    return r


def statuses(results, needle=""):
    return [r.status for r in results if needle in r.text]


class PlanAnalysis(unittest.TestCase):
    def test_clean_template_passes_and_lists_what_is_not_in_the_group(self):
        res = sc.analyze_template(tpl([module("m", [{"type": "Microsoft.Search/searchServices", "name": "s"},
                                                    role("[resourceId('Microsoft.Search/searchServices', 's')]")])]), LOC)
        self.assertNotIn("bad", statuses(res))
        self.assertTrue(any("every resource is created in the deployment's own resource group" in r.text for r in res))
        info = " ".join(r.text for r in res if r.status == "info")
        for item in ("Entra", "quota", "Fabric workspace", "Agent Service platform storage"):
            self.assertIn(item, info)

    def test_module_with_another_subscription_or_group_fails(self):
        for key in ("subscriptionId", "resourceGroup"):
            res = sc.analyze_template(tpl([module("m", [{"type": "Microsoft.Search/searchServices", "name": "s"}], **{key: "x"})]), LOC)
            self.assertIn("bad", statuses(res, key), key)

    def test_extension_scopes_that_leave_the_group_fail(self):
        for scope in ("[subscription().id]", "[resourceGroup('other').id]", "/subscriptions/x", "[managementGroup().id]"):
            res = sc.analyze_template(tpl([role(scope)]), LOC)
            self.assertIn("bad", statuses(res, "reaches outside"), scope)

    def test_role_assignment_without_a_resource_scope_fails(self):
        self.assertIn("bad", statuses(sc.analyze_template(tpl([role()]), LOC), "whole resource group"))

    def test_resource_scoped_assignments_in_both_compiled_forms_pass(self):
        for scope in ("[format('Microsoft.CognitiveServices/accounts/{0}', parameters('a'))]",
                      "[resourceId('Microsoft.Storage/storageAccounts', parameters('s'))]",
                      "Microsoft.Storage/storageAccounts/s"):
            res = sc.analyze_template(tpl([role(scope)]), LOC)
            self.assertNotIn("bad", statuses(res), scope)
            self.assertNotIn("warn", statuses(res, "unusual scope"), scope)

    def test_the_region_must_be_pinned(self):
        self.assertIn("bad", statuses(sc.analyze_template(tpl(allowed=(LOC, "northcentralus")), LOC), "allows"))
        self.assertIn("bad", statuses(sc.analyze_template(tpl(allowed=()), LOC), "allows"))

    def test_unrestricted_search_location_parameter_fails(self):
        self.assertIn("bad", statuses(sc.analyze_template(tpl(params={"searchLocation": {"type": "string"}}), LOC), "searchLocation allows"))

    def test_only_search_can_use_the_approved_region_through_nested_modules(self):
        resources = [{"type": "Microsoft.Search/searchServices", "name": "search", "location": "[parameters('location')]"}]
        mod = module("search", resources)
        mod["properties"]["parameters"] = {"location": {"value": "[parameters('searchLocation')]"}}
        t = tpl([mod], params={"searchLocation": {"type": "string", "allowedValues": [LOC, "francecentral"]}})
        self.assertNotIn("bad", statuses(sc.analyze_template(t, LOC, "francecentral")))
        resources[0]["type"] = "Microsoft.Storage/storageAccounts"
        self.assertIn("bad", statuses(sc.analyze_template(t, LOC, "francecentral"), "only Search"))

    def test_search_in_wrong_region_and_unresolvable_location_fail(self):
        for value in ("swedencentral", "[variables('unknown')]"):
            t = tpl([{"type": "Microsoft.Search/searchServices", "name": "search", "location": value}],
                    params={"searchLocation": {"type": "string", "allowedValues": [LOC, "francecentral"]}})
            self.assertIn("bad", statuses(sc.analyze_template(t, LOC, "francecentral"), "only Search"))

    def test_built_in_role_definition_references_are_allowed_other_subscription_references_warn(self):
        ok = tpl([{"type": "Microsoft.Storage/storageAccounts", "name": "s",
                   "properties": {"r": "[subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'x')]"}}])
        self.assertNotIn("warn", statuses(sc.analyze_template(ok, LOC), "subscription-scope reference"))
        odd = tpl([{"type": "Microsoft.Storage/storageAccounts", "name": "s",
                    "properties": {"r": "[subscriptionResourceId('Microsoft.Network/virtualNetworks', 'v')]"}}])
        self.assertIn("warn", statuses(sc.analyze_template(odd, LOC), "subscription-scope reference"))

    def test_workload_profiles_are_flagged_as_a_possible_platform_managed_group(self):
        t = tpl([{"type": "Microsoft.App/managedEnvironments", "name": "e", "properties": {"workloadProfiles": [{"name": "c"}]}}])
        self.assertIn("warn", statuses(sc.analyze_template(t, LOC), "platform-managed infrastructure resource group"))

    def test_empty_template_is_not_a_pass(self):
        self.assertIn("bad", statuses(sc.analyze_template(tpl([]), LOC)))

    @unittest.skipUnless(shutil.which("az"), "az CLI (bicep) not installed")
    def test_the_real_template_stays_inside_the_group(self):
        compiled = sc.compile_template(ROOT / "infra" / "main.bicep")
        cfg = wsconfig.load("mcaps")
        res = sc.analyze_template(compiled, cfg["names"]["location"], cfg["environments"]["mcaps"]["search_location"])
        self.assertEqual([r.text for r in res if r.status == "bad"], [])


def deployed_cfg():
    return wsconfig.load("mcaps")


def res(name, rtype, loc=LOC):
    return {"name": name, "type": rtype, "location": loc, "id": f"/subscriptions/sub/resourceGroups/rg/{name}"}


class DeployedAnalysis(unittest.TestCase):
    def setUp(self):
        self.cfg = deployed_cfg()
        self.e = self.cfg["environments"]["mcaps"]
        self.rg = self.cfg["names"]["resource_group"]
        self.sub = self.e["subscription_id"]
        self.inv = [res("aif-acct", "Microsoft.CognitiveServices/accounts"),
                    res("srch-x", "Microsoft.Search/searchServices", self.e["search_location"]),
                    res("stx", "Microsoft.Storage/storageAccounts"), res("crx", "Microsoft.ContainerRegistry/registries"),
                    res("ca-mcp", "Microsoft.App/containerApps"), res("fab", "Microsoft.Fabric/capacities"),
                    res("appi", "Microsoft.Insights/components", "global")]

    def run_all(self, **over):
        args = dict(rg_obj={"location": LOC, "tags": {"workshop": "livewell", "azd-env-name": "mcaps"}}, resources=self.inv,
                    tagged=[], groups=[], connections=[], envvals={}, roles=[], budgets=None, fabric=None, principals={})
        args.update(over)
        return sc.analyze_deployed(self.cfg, "mcaps", args["rg_obj"], args["resources"], args["tagged"], args["groups"],
                                   args["connections"], args["envvals"], args["roles"], args["budgets"], args["fabric"],
                                   args["principals"])

    def test_missing_group_is_a_single_failure(self):
        self.assertEqual(statuses(self.run_all(rg_obj=None)), ["bad"])

    def test_group_in_another_region_or_untagged_fails(self):
        self.assertIn("bad", statuses(self.run_all(rg_obj={"location": "elsewhere", "tags": {}}), "is in elsewhere"))
        self.assertIn("bad", statuses(self.run_all(rg_obj={"location": LOC, "tags": {}}), "not tagged"))

    def test_only_search_uses_francecentral_global_resources_are_fine(self):
        out = self.run_all(resources=self.inv + [res("odd", "Microsoft.Storage/storageAccounts", "francecentral")])
        self.assertIn("bad", statuses(out, "resources outside their approved regions"))
        self.assertIn("ok", statuses(self.run_all(), "every resource matches its approved region"))
        for location in ("swedencentral", "global", "italynorth"):
            out = self.run_all(resources=self.inv + [res("odd", "Microsoft.Search/searchServices", location)])
            self.assertIn("bad", statuses(out, "resources outside their approved regions"))

    def test_stale_search_output_region_is_rejected(self):
        self.assertIn("bad", statuses(self.run_all(envvals={"AZURE_SEARCH_LOCATION": LOC}), "AZURE_SEARCH_LOCATION"))

    def test_arm_region_display_names_are_normalised(self):
        inventory = [dict(r, location="France Central" if r["type"] == "Microsoft.Search/searchServices"
                          else "Sweden Central") for r in self.inv]
        self.assertNotIn("bad", statuses(self.run_all(resources=inventory)))

    def test_workshop_tagged_resource_in_another_group_fails(self):
        stray = {"id": f"/subscriptions/{self.sub}/resourceGroups/rg-old/providers/x/y/z", "name": "old-search",
                 "tags": {"workshop": "livewell", "azd-env-name": "mcaps"}}
        self.assertIn("bad", statuses(self.run_all(tagged=[stray]), "OUTSIDE the group"))
        mine = dict(stray, id=f"/subscriptions/{self.sub}/resourceGroups/{self.rg}/providers/x/y/z")
        self.assertIn("ok", statuses(self.run_all(tagged=[mine]), "no workshop-tagged resource exists outside"))

    def test_connection_targets_must_be_resources_in_the_group(self):
        good = [{"name": "search", "properties": {"target": "https://srch-x.search.windows.net"}},
                {"name": "storage", "properties": {"metadata": {"ResourceId": f"/subscriptions/{self.sub}/resourceGroups/{self.rg}/providers/x/stx"}}}]
        self.assertNotIn("bad", statuses(self.run_all(connections=good)))
        bad = [{"name": "search", "properties": {"target": "https://srch-old.search.windows.net"}},
               {"name": "storage", "properties": {"metadata": {"ResourceId": f"/subscriptions/{self.sub}/resourceGroups/rg-old/providers/x/y"}}}]
        out = self.run_all(connections=bad)
        self.assertEqual(statuses(out, "connection search").count("bad"), 1)
        self.assertEqual(statuses(out, "connection storage").count("bad"), 1)

    def test_runtime_endpoints_are_checked_against_the_group(self):
        good = {"AZURE_AI_PROJECT_ENDPOINT": "https://aif-acct.services.ai.azure.com/api/projects/p",
                "AZURE_SEARCH_ENDPOINT": "https://srch-x.search.windows.net", "MCP_URL": "https://ca-mcp.env123.swedencentral.azurecontainerapps.io/mcp",
                "AZURE_CONTAINER_REGISTRY_ENDPOINT": "crx.azurecr.io", "AZURE_SUBSCRIPTION_ID": self.sub,
                "AZURE_RESOURCE_GROUP": self.rg, "AZURE_TENANT_ID": self.e["tenant_id"]}
        self.assertNotIn("bad", statuses(self.run_all(envvals=good)))
        stale = dict(good, AZURE_SEARCH_ENDPOINT="https://srch-previous.search.windows.net", AZURE_SUBSCRIPTION_ID="other")
        out = self.run_all(envvals=stale)
        self.assertIn("bad", statuses(out, "AZURE_SEARCH_ENDPOINT"))
        self.assertIn("bad", statuses(out, "AZURE_SUBSCRIPTION_ID"))

    def test_fabric_connection_must_target_the_recorded_workshop_artifacts(self):
        workspace = {"id": "ws", "displayName": self.cfg["names"]["fabric_workspace"], "capacityId": "cap"}
        fabric = {"workspaces": [workspace], "capacities": [
            {"id": "cap", "displayName": self.cfg["names"]["fabric_capacity"], "sku": "F2", "region": LOC}]}
        values = {"FABRIC_WORKSPACE_ID": "ws", "FABRIC_DATA_AGENT_ID": "agent"}
        for path, expected in (("ws/dataagents/agent", "ok"), ("other/dataagents/agent", "bad"),
                               ("ws/dataagents/other", "bad")):
            connections = [{"name": "fabric", "properties": {
                "target": f"https://api.fabric.microsoft.com/v1/mcp/workspaces/{path}/agent"}}]
            out = self.run_all(connections=connections, envvals=values, fabric=fabric)
            self.assertIn(expected, statuses(out, "connection fabric"))

    def test_attendees_must_not_hold_group_or_subscription_scope_roles(self):
        prefix = self.e["lab_accounts"]["prefix"]
        facilitator = self.e["facilitator_upns"][0]
        roles = [{"properties": {"scope": f"/subscriptions/{self.sub}/resourceGroups/{self.rg}", "principalType": "User", "principalId": "p-lab"}},
                 {"properties": {"scope": f"/subscriptions/{self.sub}", "principalType": "User", "principalId": "p-fac"}},
                 {"properties": {"scope": f"/subscriptions/{self.sub}/resourceGroups/{self.rg}/providers/x/y", "principalType": "User", "principalId": "p-res"}}]
        out = self.run_all(roles=roles, principals={"p-lab": f"{prefix}07@example.test", "p-fac": facilitator, "p-res": "x@example.test"})
        self.assertEqual(statuses(out, "lab account").count("bad"), 1)
        self.assertNotIn("warn", statuses(out, "other user/group principal"))
        out = self.run_all(roles=roles[1:2], principals={"p-fac": "someone.else@example.test"})
        self.assertIn("warn", statuses(out, "other user/group principal"))

    def test_budget_amount_must_match_the_config(self):
        name = self.cfg["names"]["budget"]
        ok = [{"name": name, "properties": {"amount": self.e["budget_usd"], "notifications": {"a": {}, "b": {}}}}]
        self.assertIn("ok", statuses(self.run_all(budgets=ok), "budget"))
        self.assertIn("bad", statuses(self.run_all(budgets=[{"name": name, "properties": {"amount": 1}}]), "budget"))
        self.assertIn("bad", statuses(self.run_all(budgets=[]), "does not exist"))

    def test_platform_managed_groups_are_reported_not_hidden(self):
        out = self.run_all(groups=[{"name": "ME_cae-livewell-mcaps_rg_swedencentral"}, {"name": "rg-other"}])
        self.assertIn("warn", statuses(out, "platform-managed resource group"))
        self.assertIn("ok", statuses(self.run_all(groups=[{"name": "rg-other"}]), "no platform-managed resource group"))

    def test_unreadable_datasets_are_warnings_never_silent_passes(self):
        out = self.run_all(resources=None, tagged=None, connections=None, roles=None, budgets=None, fabric=None)
        self.assertGreaterEqual(statuses(out).count("warn"), 5)


class FabricChecks(unittest.TestCase):
    def setUp(self):
        self.cfg = deployed_cfg()
        n = self.cfg["names"]
        self.cap = {"id": "cap-1", "displayName": n["fabric_capacity"], "sku": "F2", "region": "Sweden Central"}
        self.ws = {"id": "ws-1", "displayName": n["fabric_workspace"], "capacityId": "cap-1"}

    def check(self, caps, wss):
        return sc.fabric_results(self.cfg, "mcaps", {"capacities": caps, "workspaces": wss})

    def test_workspace_on_the_f2_capacity_in_the_right_region_passes(self):
        self.assertNotIn("bad", statuses(self.check([self.cap], [self.ws])))

    def test_wrong_sku_or_region_fails(self):
        self.assertIn("bad", statuses(self.check([dict(self.cap, sku="F4")], [self.ws]), "SKU"))
        self.assertIn("bad", statuses(self.check([dict(self.cap, region="Southeast Asia")], [self.ws]), "region"))

    def test_workspace_on_another_capacity_or_duplicated_fails(self):
        self.assertIn("bad", statuses(self.check([self.cap], [dict(self.ws, capacityId="cap-other")]), "NOT assigned"))
        self.assertIn("bad", statuses(self.check([self.cap], [self.ws, dict(self.ws, id="ws-2")]), "ambiguous"))

    def test_missing_workspace_is_only_a_warning(self):
        self.assertIn("warn", statuses(self.check([self.cap], []), "does not exist yet"))


class FabricOwnership(unittest.TestCase):
    NAMES = ("HPB Workspace", "fabcap")

    def classify(self, workspaces, capacities=None):
        caps = capacities if capacities is not None else [{"id": "cap-1", "displayName": "FABCAP"}]
        return fabric_ws.classify(workspaces, caps, *self.NAMES)

    def test_only_a_workspace_on_the_workshop_capacity_is_ours(self):
        out = self.classify([{"id": "a", "displayName": "HPB Workspace", "capacityId": "cap-1"},
                             {"id": "b", "displayName": "HPB Workspace", "capacityId": "cap-9"},
                             {"id": "c", "displayName": "HPB Workspace"},
                             {"id": "d", "displayName": "Another", "capacityId": "cap-1"}])
        self.assertEqual({w["id"]: w["verdict"] for w in out}, {"a": "ours", "b": "foreign", "c": "unassigned"})

    def test_when_the_capacity_is_gone_nothing_is_ours(self):
        out = self.classify([{"id": "a", "displayName": "HPB Workspace", "capacityId": "cap-1"}], capacities=[])
        self.assertEqual(out[0]["verdict"], "foreign")

    def test_workspace_script_refuses_to_adopt_by_name(self):
        script = (ROOT / "scripts" / "fabric" / "10-workspace.sh").read_text(encoding="utf-8")
        self.assertIn("FABRIC_ADOPT_WORKSPACE_ID", script)
        self.assertIn("Not adopting it", script)


if __name__ == "__main__":
    unittest.main()
