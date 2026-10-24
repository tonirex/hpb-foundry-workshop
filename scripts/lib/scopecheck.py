#!/usr/bin/env python3
"""Scope verification for the ONE-resource-group workshop deployment. READ-ONLY (manifest writes only a local file).

  python scripts/verify-scope.py plan     --env mcaps   before deploying: prove the compiled template stays in the group
  python scripts/verify-scope.py caller   --env mcaps   can the signed-in identity assign roles on the subscription?
  python scripts/verify-scope.py deployed --env mcaps   AFTER an approved deployment: inventory, locations, connection
                                                        targets, role scopes, budget, Fabric capacity and workspace
  python scripts/verify-scope.py manifest --env mcaps   write .azure/<env>/manifest.json (ids, no secrets) for teardown

`plan` compiles infra/main.bicep (az bicep build) and checks every resource: no cross-subscription or cross-group
module, no role assignment above resource scope, no reference outside the group, the region parameter pinned. It
also lists what is NOT in the group by design. `deployed` then verifies the real inventory and where every connection
and endpoint points. Nothing here changes Azure, Entra or Fabric.

Literal single-group containment is not achievable and this tool says so: Entra objects, quota, Fabric workspace items,
the Agent Service platform storage / Key Vault and (possibly) a Container Apps infrastructure group live elsewhere.

Output: `status<TAB>message` (ok | bad | warn | info); exit 1 if any line is bad. ASCII only.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import wsconfig  # noqa: E402

ARM_API = "2021-04-01"
FOUNDRY_API = "2025-06-01"
RBAC_API = "2022-04-01"
BUDGET_API = "2023-11-01"
FABRIC_ARM_API = "2023-11-01"
RESOURCE_SCOPED = "Microsoft."  # compiled scope strings that start like this are relative to the deployment's group

OUT_OF_GROUP_BY_DESIGN = [
    "Entra users, groups, TAPs and directory roles: tenant level (scripts/tenant/*, content/admin/HPB-DELIVERY-RUNBOOK.md)",
    "quota and resource-provider registration: subscription level",
    "Fabric workspace, lakehouse, notebooks, ontology, graph model, data agent and their Viewer grants: Fabric service "
    "artifacts, linked to the F2 capacity that IS in the group",
    "Foundry Agent Service platform storage, a Microsoft-managed Key Vault and hosted-agent sandboxes: service-managed, "
    "not visible as resources in the group",
]


@dataclass
class Result:
    status: str  # ok | bad | warn | info
    text: str

    def line(self) -> str:
        return f"{self.status}\t{self.text}"


# --------------------------------------------------------------------------------------------------
# plan: static analysis of the compiled template
# --------------------------------------------------------------------------------------------------
def walk(resources, path: str = ""):
    items = resources.items() if isinstance(resources, dict) else enumerate(resources or [])
    for _, r in items:
        name = str(r.get("name", "?"))
        yield path, r
        if r.get("type") == "Microsoft.Resources/deployments":
            inner = (r.get("properties") or {}).get("template") or {}
            yield from walk(inner.get("resources"), f"{path}/{name}")


def expressions(node):
    """Every ARM expression string ('[...]') in a JSON tree."""
    if isinstance(node, str):
        if node.startswith("[") and not node.startswith("[["):
            yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from expressions(v)
    elif isinstance(node, list):
        for v in node:
            yield from expressions(v)


def split_args(text: str) -> list[str]:
    args, depth, cur, quote_ch = [], 0, [], ""
    for ch in text:
        if quote_ch:
            cur.append(ch)
            if ch == quote_ch:
                quote_ch = ""
            continue
        if ch in "'\"":
            quote_ch = ch
            cur.append(ch)
        elif ch in "([":
            depth += 1
            cur.append(ch)
        elif ch in ")]":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        args.append("".join(cur).strip())
    return args


def call_args(expr: str, func: str) -> list[list[str]]:
    out = []
    for m in re.finditer(rf"\b{func}\(", expr):
        depth, i, start = 1, m.end(), m.end()
        while i < len(expr) and depth:
            depth += {"(": 1, ")": -1}.get(expr[i], 0)
            i += 1
        out.append(split_args(expr[start:i - 1]))
    return out


def is_type_literal(arg: str) -> bool:
    return bool(re.match(r"^'Microsoft\.[A-Za-z.]+/", arg)) or arg.startswith("format('Microsoft.")


def local_resource_expr(expr: str) -> bool:
    """A scope / reference expression built only from resource types and names of this deployment: a compiled
    relative scope string, or resourceId('Microsoft.X/y', ...) with the type first (no subscription / group override)."""
    if expr.startswith(f"[format('{RESOURCE_SCOPED}") or expr.startswith(RESOURCE_SCOPED) or expr.startswith(f"[concat('{RESOURCE_SCOPED}"):
        return True
    calls = call_args(expr, "resourceId")
    return bool(calls) and all(a and is_type_literal(a[0]) for a in calls) and not re.search(
        r"subscription\(\)|managementGroup|tenant\(\)|resourceGroup\(\s*[^)\s]|/subscriptions/", expr, re.I)


def template_locations(tpl: dict, bindings: dict[str, str], path: str = ""):
    def resolve(value):
        if not isinstance(value, str) or not value.startswith("["):
            return value
        match = re.fullmatch(r"\[parameters\('([^']+)'\)\]", value)
        return bindings.get(match.group(1)) if match else None

    resources = tpl.get("resources") or []
    for resource in resources.values() if isinstance(resources, dict) else resources:
        label = f"{path}/{resource.get('name', '?')}"
        if resource.get("type") == "Microsoft.Resources/deployments":
            props = resource.get("properties") or {}
            inner = props.get("template") or {}
            values = {key: resolve(param.get("value") if isinstance(param, dict) else param)
                      for key, param in (props.get("parameters") or {}).items()}
            for key, param in (inner.get("parameters") or {}).items():
                if key not in values:
                    values[key] = param.get("defaultValue")
            yield from template_locations(inner, values, label)
        elif "location" in resource:
            yield str(resource.get("type", "")), label, resolve(resource["location"])


def analyze_template(tpl: dict, location: str, search_location: str | None = None) -> list[Result]:
    out: list[Result] = []
    types: dict[str, int] = {}
    workload_profiles = False
    for path, r in walk(tpl.get("resources")):
        rtype = str(r.get("type", ""))
        raw = str(r.get("name", "?"))
        label = (path + "/" + (raw if not raw.startswith("[") else "<name expression>")).strip("/")
        if rtype == "Microsoft.Resources/deployments":
            for key in ("subscriptionId", "resourceGroup"):
                if r.get(key):
                    out.append(Result("bad", f"module {label} sets {key}: it would deploy outside the workshop resource group"))
            continue
        types[rtype] = types.get(rtype, 0) + 1
        scope = r.get("scope")
        if isinstance(scope, str):
            if re.search(r"subscription\(\)|managementGroup|tenant\(\)|resourceGroup\(\s*[^)\s]|'?/subscriptions/", scope, re.I):
                out.append(Result("bad", f"{rtype} {label} has scope {scope[:90]}: it reaches outside the group"))
            elif not local_resource_expr(scope):
                out.append(Result("warn", f"{rtype} {label} has an unusual scope expression {scope[:90]}: review"))
        elif rtype == "Microsoft.Authorization/roleAssignments":
            out.append(Result("bad", f"role assignment {label} has no resource scope: it would apply to the whole resource group"))
        if rtype == "Microsoft.App/managedEnvironments" and (r.get("properties") or {}).get("workloadProfiles"):
            workload_profiles = True
    if not types:
        out.append(Result("bad", "the compiled template contains no resources: nothing was analysed"))
        return out

    for expr in expressions(tpl):
        for args in call_args(expr, "resourceId"):
            if len(args) >= 3 and not is_type_literal(args[0]):
                out.append(Result("warn", f"resourceId call with a subscription/group override: {expr[:110]}"))
        for args in call_args(expr, "subscriptionResourceId"):
            if not (args and args[0].strip("'") == "Microsoft.Authorization/roleDefinitions"):
                out.append(Result("warn", f"subscription-scope reference other than a built-in role definition: {expr[:110]}"))
        for args in call_args(expr, "extensionResourceId"):
            if not (args and local_resource_expr(args[0])):
                out.append(Result("warn", f"extensionResourceId on a scope that is not a resource of this deployment: {expr[:110]}"))
        for func in ("tenantResourceId", "managementGroupResourceId"):
            if re.search(rf"\b{func}\(", expr):
                out.append(Result("bad", f"{func} reference: {expr[:110]}"))

    allowed = ((tpl.get("parameters") or {}).get("location") or {}).get("allowedValues")
    if allowed == [location]:
        out.append(Result("ok", f"the location parameter is pinned to {location} (no other region can be passed)"))
    else:
        out.append(Result("bad", f"the location parameter allows {allowed}, expected exactly [{location!r}]"))
    search_location = search_location or location
    search_param = (tpl.get("parameters") or {}).get("searchLocation")
    if search_param is not None:
        permitted = search_param.get("allowedValues") or []
        if not permitted or search_location not in permitted or not set(permitted) <= {location, search_location}:
            out.append(Result("bad", f"searchLocation allows {permitted}; only the primary and approved Search regions are permitted"))
    elif search_location != location:
        out.append(Result("bad", "searchLocation is missing: the approved Search-only exception is not wired"))
    for rtype, label, actual in template_locations(tpl, {"location": location, "searchLocation": search_location}):
        is_search = rtype.lower() == "microsoft.search/searchservices"
        expected = search_location if is_search else location
        if actual != expected and (is_search or actual != "global"):
            out.append(Result("bad", f"{rtype} {label}: location {actual!r}, expected {expected}; only Search may use its exception"))
    if not any(r.status == "bad" for r in out):
        out.append(Result("ok", f"resource locations match the plan: Search in {search_location}, everything else in {location} (or global)"))

    bad = [x for x in out if x.status == "bad"]
    summary = ", ".join(f"{t} x{n}" for t, n in sorted(types.items()))
    out.append(Result("ok" if not bad else "info", f"the template creates {sum(types.values())} resources: {summary}"))
    if not bad:
        out.append(Result("ok", "every resource is created in the deployment's own resource group with RG-relative scopes"))
    if workload_profiles:
        out.append(Result("warn", "the Container Apps environment uses workload profiles: Azure may create a platform-managed "
                                  "infrastructure resource group (ME_<environment>_<group>_<region>) OUTSIDE the workshop group. "
                                  "Unverified until the first approved deployment; `deployed` lists any such group"))
    for line in OUT_OF_GROUP_BY_DESIGN:
        out.append(Result("info", f"not in the group by design: {line}"))
    return out


def compile_template(template: Path) -> dict:
    az = shutil.which("az")
    if not az:
        raise SystemExit("az CLI not found (needed to compile Bicep: az bicep build)")
    proc = subprocess.run([az, "bicep", "build", "--file", str(template), "--stdout"], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=300)
    if proc.returncode != 0:
        raise SystemExit(f"az bicep build failed: {proc.stderr.strip()[:400]}")
    return json.loads(proc.stdout)


# --------------------------------------------------------------------------------------------------
# deployed: verify the real inventory and where everything points
# --------------------------------------------------------------------------------------------------
HOST_SUFFIXES = {  # host suffix -> resource type whose name is the first DNS label (None: the Container App name)
    ".services.ai.azure.com": "Microsoft.CognitiveServices/accounts",
    ".openai.azure.com": "Microsoft.CognitiveServices/accounts",
    ".cognitiveservices.azure.com": "Microsoft.CognitiveServices/accounts",
    ".search.windows.net": "Microsoft.Search/searchServices",
    ".blob.core.windows.net": "Microsoft.Storage/storageAccounts",
    ".azurecr.io": "Microsoft.ContainerRegistry/registries",
    ".azurecontainerapps.io": "Microsoft.App/containerApps",
}
ENDPOINT_KEYS = ["AZURE_AI_PROJECT_ENDPOINT", "FOUNDRY_PROJECT_ENDPOINT", "AZURE_OPENAI_ENDPOINT", "AZURE_SEARCH_ENDPOINT",
                 "AZURE_STORAGE_BLOB_ENDPOINT", "AZURE_CONTAINER_REGISTRY_ENDPOINT", "MCP_URL", "LAB4_DEVUI_URL"]


def host_of(target: str) -> str:
    t = target.strip()
    if "://" not in t:
        t = "https://" + t
    return (urlparse(t).hostname or "").lower()


def classify_host(host: str) -> tuple[str, str] | None:
    """(resource type, name) a host points at, or None when it is not an Azure resource host."""
    for suffix, rtype in HOST_SUFFIXES.items():
        if host.endswith(suffix):
            label = host[: -len(suffix)]
            if rtype == "Microsoft.App/containerApps":
                label = label.split(".")[0]  # <app>.<env-unique>.<region> -> <app>
            return rtype, label.split(".")[0]
    return None


def names_by_type(resources: list[dict]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for r in resources:
        out.setdefault(str(r.get("type", "")).lower(), set()).add(str(r.get("name", "")).lower())
    return out


def check_target(label: str, target: str, owned: dict[str, set[str]]) -> Result:
    cls = classify_host(host_of(target))
    if cls is None:
        return Result("info", f"{label}: {host_of(target) or target} is not an Azure resource host (skipped)")
    rtype, name = cls
    if name in owned.get(rtype.lower(), set()):
        return Result("ok", f"{label}: points at {rtype.split('/')[-1]} '{name}' in the workshop group")
    return Result("bad", f"{label}: points at '{name}' ({rtype}), which is NOT a resource in the workshop group")


def analyze_deployed(cfg: dict, env: str, rg_obj: dict | None, resources: list[dict] | None, tagged: list[dict] | None,
                     groups: list[dict] | None, connections: list[dict] | None, envvals: dict, roles: list[dict] | None,
                     budgets: list[dict] | None, fabric: dict | None, principals: dict[str, str] | None) -> list[Result]:
    out: list[Result] = []
    names, e = cfg["names"], (cfg.get("environments") or {}).get(env) or {}
    sub, rg, loc = str(e.get("subscription_id", "")), names["resource_group"], names["location"]
    if rg_obj is None:
        return [Result("bad", f"resource group {rg} does not exist (or cannot be read) in the configured subscription")]
    tags = rg_obj.get("tags") or {}
    out.append(Result("ok" if str(rg_obj.get("location")).replace(" ", "").lower() == loc else "bad",
                      f"resource group {rg} is in {rg_obj.get('location')} (expected {loc})"))
    if tags.get("workshop") == "livewell" and tags.get("azd-env-name") == env:
        out.append(Result("ok", f"resource group is tagged workshop=livewell, azd-env-name={env}"))
    else:
        out.append(Result("bad", f"resource group {rg} is not tagged as this workshop's (workshop=livewell, azd-env-name={env})"))

    # inventory + locations ----------------------------------------------------------------------------
    if resources is None:
        out.append(Result("warn", "could not list the group's resources: inventory not verified"))
        resources = []
    else:
        kinds: dict[str, int] = {}
        for r in resources:
            kinds[str(r.get("type"))] = kinds.get(str(r.get("type")), 0) + 1
        out.append(Result("info", f"the group holds {len(resources)} resources: "
                                  + ", ".join(f"{t.split('/')[-1]} x{n}" for t, n in sorted(kinds.items()))))
        search_loc = e["search_location"]
        elsewhere = []
        for r in resources:
            is_search = str(r.get("type", "")).lower() == "microsoft.search/searchservices"
            expected = search_loc if is_search else loc
            allowed = (expected,) if is_search else (expected, "global")
            if str(r.get("location", "")).replace(" ", "").lower() not in allowed:
                elsewhere.append(f"{r['name']} ({r.get('location')}; expected {expected})")
        out.append(Result("bad" if elsewhere else "ok",
                          "resources outside their approved regions: " + ", ".join(elsewhere) if elsewhere
                          else f"every resource matches its approved region: Search {search_loc}, others {loc} (or global)"))
        cap_names = [r for r in resources if r.get("type") == "Microsoft.Fabric/capacities"]
        out.append(Result("ok" if cap_names else "warn", "the Fabric capacity is in the workshop group" if cap_names
                          else "no Fabric capacity in the group (FABRIC_BRIDGE=false, or not deployed yet)"))

    # workshop-tagged resources outside the group --------------------------------------------------------
    if tagged is None:
        out.append(Result("warn", "could not search the subscription for workshop-tagged resources outside the group"))
    else:
        stray = []
        for r in tagged:
            m = re.search(r"/resourceGroups/([^/]+)/", str(r.get("id", "")), re.I)
            if m and m.group(1).lower() != rg.lower() and (r.get("tags") or {}).get("azd-env-name") == env:
                stray.append(f"{r.get('name')} in {m.group(1)}")
        out.append(Result("bad" if stray else "ok", "workshop-tagged resources OUTSIDE the group: " + ", ".join(stray) if stray
                          else "no workshop-tagged resource exists outside the group"))

    # platform-managed groups -----------------------------------------------------------------------------
    if groups is not None:
        managed = [g["name"] for g in groups
                   if rg.lower() in str(g.get("managedBy", "")).lower() or re.match(r"^(ME|MC)_", str(g.get("name", "")))
                   and env in str(g.get("name", "")).lower()]
        out.append(Result("warn" if managed else "ok",
                          "platform-managed resource group(s) outside the workshop group: " + ", ".join(managed)
                          + " (service-owned; removed with the environment: record them, do not edit them)" if managed
                          else "no platform-managed resource group was found for this deployment"))

    # connection and endpoint targets ------------------------------------------------------------------------
    owned = names_by_type(resources)
    if connections is None:
        out.append(Result("warn", "could not read the Foundry project connections: connection targets not verified"))
    else:
        for c in connections:
            props = c.get("properties") or {}
            label = f"connection {c.get('name')}"
            rid = str((props.get("metadata") or {}).get("ResourceId", ""))
            if rid:
                inside = rid.lower().startswith(f"/subscriptions/{sub}/resourcegroups/{rg}/".lower())
                out.append(Result("ok" if inside else "bad",
                                  f"{label}: resource id is {'inside' if inside else 'OUTSIDE'} the workshop group"))
            elif host_of(str(props.get("target", ""))) == "api.fabric.microsoft.com":
                workspace, agent = envvals.get("FABRIC_WORKSPACE_ID"), envvals.get("FABRIC_DATA_AGENT_ID")
                owned_workspaces = {w.get("id") for w in (fabric or {}).get("workspaces", [])
                                    if w.get("displayName") == names["fabric_workspace"]}
                if not workspace or not agent or fabric is None:
                    out.append(Result("warn", f"{label}: Fabric artifact IDs or workspace inventory unavailable; target not verified"))
                else:
                    expected = f"https://api.fabric.microsoft.com/v1/mcp/workspaces/{workspace}/dataagents/{agent}/agent"
                    matches = workspace in owned_workspaces and str(props["target"]).rstrip("/").lower() == expected.lower()
                    out.append(Result("ok" if matches else "bad",
                                      f"{label}: " + ("targets the recorded data agent in the workshop Fabric workspace"
                                                     if matches else "does NOT target the recorded workshop Fabric data agent")))
            elif props.get("target"):
                out.append(check_target(label, str(props["target"]), owned))
    for key in ENDPOINT_KEYS:
        if envvals.get(key):
            out.append(check_target(f"{key}", envvals[key], owned))
    for key, want in (("AZURE_SUBSCRIPTION_ID", sub), ("AZURE_RESOURCE_GROUP", rg), ("AZURE_TENANT_ID", e.get("tenant_id")),
                      ("AZURE_LOCATION", loc), ("AZURE_SEARCH_LOCATION", e["search_location"])):
        have = envvals.get(key)
        if have is not None:
            out.append(Result("ok" if str(have).lower() == str(want).lower() else "bad",
                              f"azd env {key} {'matches' if str(have).lower() == str(want).lower() else 'DIFFERS from'} workshop.yaml"))

    # role assignments: attendees must hold resource-scoped roles only -----------------------------------------
    if roles is None:
        out.append(Result("warn", "could not list role assignments: permission scopes not verified"))
    else:
        broad = [r for r in roles if str((r.get("properties") or {}).get("scope", "")).lower().rstrip("/")
                 in (f"/subscriptions/{sub}".lower(), f"/subscriptions/{sub}/resourcegroups/{rg}".lower())
                 and (r.get("properties") or {}).get("principalType") in ("User", "Group")]
        lab_prefix = str((e.get("lab_accounts") or {}).get("prefix", "hpb.lab")).lower()
        facilitators = {str(u).lower() for u in e.get("facilitator_upns", [])}
        flagged = []
        for r in broad:
            pid = str((r.get("properties") or {}).get("principalId", ""))
            who = (principals or {}).get(pid, pid)
            if str(who).lower().startswith(lab_prefix):
                out.append(Result("bad", f"lab account {who} holds a role at group or subscription scope: attendees must have "
                                         "resource-scoped roles only"))
            elif str(who).lower() not in facilitators:
                flagged.append(str(who))
        if flagged:
            out.append(Result("warn", f"{len(set(flagged))} other user/group principal(s) hold a role at group or subscription "
                                      f"scope (review; not necessarily wrong): {', '.join(sorted(set(flagged))[:6])}"))
        out.append(Result("info", f"{len(roles)} role assignment(s) apply at or below the group"))

    # budget ---------------------------------------------------------------------------------------------------
    if budgets is None:
        out.append(Result("warn", "could not read the budget: not verified"))
    else:
        want = names["budget"]
        hit = [b for b in budgets if str(b.get("name")) == want]
        if not hit:
            out.append(Result("bad", f"budget {want} does not exist on the workshop resource group"))
        else:
            p = hit[0].get("properties") or {}
            amount = e.get("budget_usd")
            ok = float(p.get("amount", -1)) == float(amount)
            out.append(Result("ok" if ok else "bad", f"budget {want} on {rg}: {p.get('amount')} (config {amount}); "
                                                      f"{len(p.get('notifications') or {})} alert(s)"))

    # Fabric -----------------------------------------------------------------------------------------------------
    if fabric is None:
        out.append(Result("warn", "Fabric REST API not queried: workspace ownership and capacity association not verified"))
    else:
        out.extend(fabric_results(cfg, env, fabric))
    return out


def fabric_results(cfg: dict, env: str, fabric: dict) -> list[Result]:
    names = cfg["names"]
    loc = names["location"].replace(" ", "").lower()
    out: list[Result] = []
    cap = [c for c in fabric.get("capacities", []) if str(c.get("displayName", "")).lower() == names["fabric_capacity"].lower()]
    if not cap:
        out.append(Result("warn", f"Fabric capacity {names['fabric_capacity']} is not visible to the Fabric API for this identity"))
    else:
        c = cap[0]
        out.append(Result("ok" if str(c.get("sku")) == "F2" else "bad", f"Fabric capacity SKU is {c.get('sku')} (the workshop uses F2)"))
        out.append(Result("ok" if str(c.get("region", "")).replace(" ", "").lower() == loc else "bad",
                          f"Fabric capacity region is {c.get('region')} (expected {names['location']})"))
    ws = [w for w in fabric.get("workspaces", []) if str(w.get("displayName", "")) == names["fabric_workspace"]]
    if not ws:
        out.append(Result("warn", f"Fabric workspace '{names['fabric_workspace']}' does not exist yet (created by scripts/fabric/10-workspace.sh)"))
    elif len(ws) > 1:
        out.append(Result("bad", f"{len(ws)} Fabric workspaces are named '{names['fabric_workspace']}': ownership is ambiguous"))
    else:
        w = ws[0]
        linked = bool(cap) and str(w.get("capacityId", "")).lower() == str(cap[0].get("id", "")).lower()
        out.append(Result("ok" if linked else "bad",
                          f"Fabric workspace '{w.get('displayName')}' (id {w.get('id')}) is "
                          + ("assigned to the workshop F2 capacity" if linked else "NOT assigned to the workshop capacity")))
    return out


# --------------------------------------------------------------------------------------------------
# Live reads (ARM / Fabric / Graph GETs through scripts/lib/azrest.py)
# --------------------------------------------------------------------------------------------------
def read_env_file(env: str) -> dict:
    p = ROOT / ".azure" / env / ".env"
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip().strip('"')
    return out


def fetch_deployed(cfg: dict, env: str) -> dict:
    from azrest import Api, ApiError

    names = cfg["names"]
    sub = str(cfg["environments"][env]["subscription_id"])
    rg = names["resource_group"]
    auth = {"tenant": cfg["environments"][env]["tenant_id"], "subscription": sub}
    arm = Api("arm", **auth)
    base = f"/subscriptions/{sub}/resourceGroups/{rg}"
    data: dict = {"warnings": []}

    def grab(key, fn):
        try:
            data[key] = fn()
        except (ApiError, SystemExit) as ex:
            data[key] = None
            data["warnings"].append(f"{key}: {str(ex)[:160]}")

    grab("rg", lambda: arm.get(f"/subscriptions/{sub}/resourcegroups/{rg}?api-version={ARM_API}", ok_404=True))
    grab("resources", lambda: arm.get_all(f"{base}/resources?api-version={ARM_API}"))
    flt = quote("tagName eq 'workshop' and tagValue eq 'livewell'", safe="")
    grab("tagged", lambda: arm.get_all(f"/subscriptions/{sub}/resources?api-version={ARM_API}&$filter={flt}"))
    grab("groups", lambda: arm.get_all(f"/subscriptions/{sub}/resourcegroups?api-version={ARM_API}"))
    grab("roles", lambda: arm.get_all(f"{base}/providers/Microsoft.Authorization/roleAssignments?api-version={RBAC_API}"))
    grab("budgets", lambda: arm.get_all(f"{base}/providers/Microsoft.Consumption/budgets?api-version={BUDGET_API}"))

    def connections():
        acct = names["foundry_account"]
        proj = names["foundry_project"]
        return arm.get_all(f"{base}/providers/Microsoft.CognitiveServices/accounts/{acct}/projects/{proj}/connections"
                           f"?api-version={FOUNDRY_API}")

    grab("connections", connections)

    def principals():
        ids = sorted({str((r.get("properties") or {}).get("principalId", "")) for r in (data.get("roles") or [])
                      if (r.get("properties") or {}).get("principalType") in ("User", "Group")})
        if not ids:
            return {}
        graph = Api("graph", **auth)
        resp = graph.post("/v1.0/directoryObjects/getByIds", {"ids": ids[:900], "types": ["user", "group"]}) or {}
        return {o["id"]: o.get("userPrincipalName") or o.get("displayName") or o["id"] for o in resp.get("value", [])}

    grab("principals", principals)

    def fabric():
        f = Api("fabric", **auth)
        return {"capacities": f.get_all("/v1/capacities"), "workspaces": f.get_all("/v1/workspaces")}

    grab("fabric", fabric)
    return data


def caller_results(cfg: dict, env: str) -> list[Result]:
    from azrest import Api, ApiError, az_token, jwt_claims

    e = cfg["environments"][env]
    sub = str(e["subscription_id"])
    claims = jwt_claims(az_token("https://management.azure.com", str(e.get("tenant_id") or "") or None, sub))
    oid = str(claims.get("oid", ""))
    if not oid:
        return [Result("bad", "the ARM token has no object id claim: cannot identify the caller")]
    roles = cfg["rbac_roles"]
    wanted = {roles["owner"], roles["user_access_administrator"], roles["rbac_administrator"]}
    arm = Api("arm", tenant=e["tenant_id"], subscription=sub)
    flt = quote(f"assignedTo('{oid}')", safe="")
    try:
        items = arm.get_all(f"/subscriptions/{sub}/providers/Microsoft.Authorization/roleAssignments?api-version={RBAC_API}"
                            f"&$filter={flt}")
    except ApiError as ex:
        return [Result("bad", f"cannot list the caller's role assignments ({ex.status}): {str(ex)[:120]}")]
    mine = [i for i in items if str((i.get("properties") or {}).get("roleDefinitionId", "")).split("/")[-1] in wanted
            and str((i.get("properties") or {}).get("scope", "")).lower().rstrip("/") == f"/subscriptions/{sub}".lower()]
    who = claims.get("upn") or claims.get("unique_name") or claims.get("appid") or "caller"
    if mine:
        return [Result("ok", f"{who} can assign roles on the subscription (Owner / User Access Administrator / RBAC Administrator, "
                             "read from ARM, not Graph)")]
    return [Result("bad", f"{who} holds none of Owner / User Access Administrator / RBAC Administrator on the subscription: "
                          "the template's role assignments would fail")]


def manifest(cfg: dict, env: str, data: dict) -> dict:
    ws = None
    if data.get("fabric"):
        names = cfg["names"]
        ws = [w for w in data["fabric"]["workspaces"] if w.get("displayName") == names["fabric_workspace"]]
        caps = [c for c in data["fabric"]["capacities"] if str(c.get("displayName", "")).lower() == names["fabric_capacity"].lower()]
    else:
        caps = []

    def csv_rows(name: str) -> list[dict]:
        p = ROOT / ".azure" / env / name
        return list(csv.DictReader(p.open(encoding="utf-8"))) if p.exists() else []

    taps = [{"upn": r.get("upn"), "tap_id": r.get("tap_id"), "expires_utc": r.get("expires_utc")} for r in csv_rows("tap-issued.csv")]
    return {
        "environment": env,
        "resource_group": cfg["names"]["resource_group"],
        "region": cfg["names"]["location"],
        "search_region": cfg["environments"][env]["search_location"],
        "resources": [r.get("id") for r in (data.get("resources") or [])],
        "fabric": {"workspace_ids": [w.get("id") for w in (ws or [])], "capacity_ids": [c.get("id") for c in caps]},
        "lab_accounts": [r.get("upn") for r in csv_rows("lab-accounts.csv")],
        "tap_ids": taps,
        "note": "ids only, no secrets; used by scripts/teardown.sh",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["plan", "caller", "deployed", "manifest"])
    ap.add_argument("--env", required=True)
    ap.add_argument("--template", default=str(ROOT / "infra" / "main.bicep"))
    ap.add_argument("--compiled", help="analyse this compiled ARM template JSON instead of compiling (tests)")
    args = ap.parse_args()
    cfg = wsconfig.load(args.env)
    results: list[Result] = []
    if args.mode == "plan":
        tpl = json.loads(Path(args.compiled).read_text(encoding="utf-8")) if args.compiled else compile_template(Path(args.template))
        results = analyze_template(tpl, cfg["names"]["location"], cfg["environments"][args.env]["search_location"])
    elif args.mode == "caller":
        results = caller_results(cfg, args.env)
    else:
        data = fetch_deployed(cfg, args.env)
        if args.mode == "manifest":
            out = ROOT / ".azure" / args.env / "manifest.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(manifest(cfg, args.env, data), indent=2), encoding="utf-8")
            results = [Result("ok", f"wrote {out.relative_to(ROOT).as_posix()} (ids only; gitignored)")]
            results += [Result("warn", w) for w in data["warnings"]]
        else:
            results = [Result("warn", w) for w in data["warnings"]]
            results += analyze_deployed(cfg, args.env, data["rg"], data["resources"], data["tagged"], data["groups"],
                                        data["connections"], read_env_file(args.env), data["roles"], data["budgets"],
                                        data["fabric"], data["principals"])
    for r in results:
        print(r.line())
    return 1 if any(r.status == "bad" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
