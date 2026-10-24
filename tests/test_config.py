"""Consistency of content/config/workshop.yaml with the Bicep, the scripts and the one-region / one-group rules.

Offline; stdlib unittest. Run: python -m unittest discover -s tests
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import wsconfig  # noqa: E402

ENVS = ("mcaps", "sponsor")
ROLES = ("default", "tools", "embeddings")


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class ModelConfig(unittest.TestCase):
    def setUp(self):
        self.cfg = wsconfig.load("mcaps")
        self.m = self.cfg["models"]

    def test_three_distinct_deployments(self):
        names = [self.m[r] for r in ROLES]
        self.assertEqual(len(set(names)), 3, names)

    def test_versions_exist_for_every_role_and_for_the_documented_fallback(self):
        for role in ROLES:
            self.assertTrue(self.m["versions"].get(self.m[role]), role)
        self.assertIn("gpt-5.4-mini", self.m["versions"])

    def test_units_per_environment_cover_every_role_as_positive_ints(self):
        for env in ENVS:
            for role in ROLES:
                self.assertGreater(int(self.m["units"][env][role]), 0, (env, role))

    def test_units_fit_the_bicep_limits(self):
        main, foundry = text("infra/main.bicep"), text("infra/modules/foundry.bicep")
        cap_max = int(re.search(r"capacity: int", foundry) and re.search(r"@maxValue\((\d+)\)\s*\n\s*capacity", foundry).group(1))
        for env in ENVS:
            for role in ROLES:
                self.assertLessEqual(int(self.m["units"][env][role]), cap_max, (env, role))
        # the per-parameter minimum / maximum on the three capacity params
        for param in ("chatTpmCapThousands", "toolsTpmCapThousands", "embeddingTpmCapThousands"):
            block = re.search(rf"@minValue\((\d+)\)\s*@maxValue\((\d+)\)\s*param {param} int", main)
            self.assertIsNotNone(block, param)
        limits = {"default": "chatTpmCapThousands", "tools": "toolsTpmCapThousands", "embeddings": "embeddingTpmCapThousands"}
        for role, param in limits.items():
            lo, hi = map(int, re.search(rf"@minValue\((\d+)\)\s*@maxValue\((\d+)\)\s*param {param} int", main).groups())
            for env in ENVS:
                self.assertTrue(lo <= int(self.m["units"][env][role]) <= hi, (env, role, lo, hi))

    def test_no_router_and_only_pay_per_token_deployment_types(self):
        for role in ROLES:
            self.assertNotIn("router", self.m[role].lower())
        self.assertIn(self.m["deployment_type"], ("GlobalStandard", "DataZoneStandard"))
        self.assertIn("model-router", self.m["forbidden"])

    def test_sizing_assumptions_are_complete(self):
        s = self.m["sizing"]
        self.assertGreaterEqual(float(s["burst_factor"]), 1.0)
        for group in ("participant_minute", "facilitator_demo"):
            for role in ROLES:
                self.assertGreater(float(s[group][role]["tokens_k"]), 0)
                self.assertGreater(float(s[group][role]["requests"]), 0)

    def test_stale_keys_are_gone(self):
        for key in ("tpm_cap_thousands", "tools_tpm_cap_thousands", "embedding_tpm_cap_thousands", "quota_usage_names"):
            self.assertNotIn(key, self.m)
        self.assertNotIn("fallback_location", self.cfg["names"])
        self.assertNotIn("participant_count", self.cfg["workshop"])


class ApprovedRegionsOneGroup(unittest.TestCase):
    def test_swedencentral_is_primary_and_only_search_has_a_regional_exception(self):
        cfg = wsconfig.load("mcaps")
        self.assertEqual(cfg["names"]["location"], "swedencentral")
        main = text("infra/main.bicep")
        allowed = re.search(r"@allowed\(\[\s*([^\]]*?)\s*\]\)\s*param location string", main, re.S).group(1)
        self.assertEqual(allowed.replace("'", "").split(), ["swedencentral"])
        for name, rows in cfg["region_matrix"]["rows"].items():
            expected = {"swedencentral", "francecentral"} if name == "search_agentic_retrieval_semantic_ranker" else {"swedencentral"}
            self.assertEqual(set(rows), expected)
        self.assertEqual(cfg["environments"]["mcaps"]["search_location"], "francecentral")

    def test_search_location_comes_from_config_not_an_arbitrary_env_override(self):
        for env in ENVS:
            params = text(f"infra/env/{env}.bicepparam")
            self.assertIn("param searchLocation = cfg.search_location", params)
            self.assertNotIn("readEnvironmentVariable('SEARCH_LOCATION'", params)
        main = text("infra/main.bicep")
        allowed = re.search(r"@allowed\(\[\s*([^\]]*?)\s*\]\)\s*param searchLocation string", main, re.S).group(1)
        self.assertEqual(set(allowed.replace("'", "").split()), {"swedencentral", "francecentral"})
        self.assertIn("output AZURE_SEARCH_LOCATION string = searchLocation", main)

    def test_storage_exception_is_environment_scoped_and_explicit(self):
        envs = wsconfig.load(None)["environments"]
        self.assertEqual(envs["mcaps"]["storage_policy_opt_out_tag"], {"SecurityControl": "Ignore"})
        self.assertEqual(envs["sponsor"]["storage_policy_opt_out_tag"], {})
        for env in ENVS:
            self.assertIn("param storagePolicyOptOutTag = cfg.storage_policy_opt_out_tag", text(f"infra/env/{env}.bicepparam"))

    def test_one_resource_group_named_once_per_environment(self):
        cfg = wsconfig.load("mcaps")
        self.assertEqual(cfg["names"]["resource_group"], "rg-livewell-workshop-mcaps")
        raw = wsconfig.load(None)
        self.assertIn("<env>", raw["names"]["resource_group"])
        # no script hard-codes a resource group name
        for path in list((ROOT / "scripts").rglob("*.sh")) + list((ROOT / "scripts").rglob("*.py")):
            self.assertNotRegex(path.read_text(encoding="utf-8"), r"rg-livewell-workshop-(mcaps|sponsor)", path.name)

    def test_bicepparam_reads_per_environment_values_from_the_yaml(self):
        for env in ENVS:
            p = text(f"infra/env/{env}.bicepparam")
            self.assertIn(f"$.environments.{env}", p)
            self.assertIn(f"$.models.units.{env}", p)
            for literal in ("chatTpmCapThousands", "toolsTpmCapThousands", "embeddingTpmCapThousands", "budgetAmountUsd"):
                self.assertNotRegex(p, rf"param {literal} = \d", (env, literal))

    def test_generated_param_path_rewrite_matches_the_script(self):
        script = text("scripts/select-params.py")
        self.assertIn("'../../content/", script)
        self.assertIn("'../content/", script)


class Environments(unittest.TestCase):
    def test_mcaps_delivery_values(self):
        e = wsconfig.load("mcaps")["environments"]["mcaps"]
        self.assertEqual(e["participants"], 30)
        self.assertGreaterEqual(int(e["lab_accounts"]["count"]), e["participants"])
        self.assertEqual(e["lab_accounts"]["sign_in"], "tap")
        self.assertEqual(e["budget_usd"], 500)
        self.assertEqual(e["budget_alerts_usd"], [250, 500])
        self.assertEqual(e["budget_alerts_usd"][-1], e["budget_usd"])
        self.assertTrue(e["facilitator_upns"])
        self.assertTrue(e["budget_contacts"])

    def test_every_environment_defines_what_bicep_and_the_scripts_read(self):
        for env, e in wsconfig.load(None)["environments"].items():
            for key in ("subscription_id", "tenant_id", "participants", "facilitator_upns", "lab_accounts",
                        "budget_usd", "budget_alerts_usd", "budget_contacts", "search_location", "storage_policy_opt_out_tag"):
                self.assertIn(key, e, (env, key))
            self.assertEqual(sorted(e["budget_alerts_usd"]), e["budget_alerts_usd"])
            self.assertLessEqual(max(e["budget_alerts_usd"]), e["budget_usd"])

    def test_the_two_environments_are_different_tenants_and_subscriptions(self):
        envs = wsconfig.load(None)["environments"]
        self.assertNotEqual(envs["mcaps"]["subscription_id"], envs["sponsor"]["subscription_id"])
        self.assertNotEqual(envs["mcaps"]["tenant_id"], envs["sponsor"]["tenant_id"])

    def test_participants_are_not_asked_for_authenticator_when_tap_is_used(self):
        self.assertFalse(wsconfig.load(None)["workshop"]["logistics"]["authenticator_registration_at_first_sign_in"])

    def test_private_repo_url_is_this_repository(self):
        self.assertTrue(wsconfig.load(None)["workshop"]["repo_url"].endswith("/hpb-foundry-workshop"))


if __name__ == "__main__":
    unittest.main()
