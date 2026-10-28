"""modelcheck: availability, lifecycle, eligibility, quota and capacity are separate verdicts, and nothing unexpected passes.

Offline: a small HAND-MADE catalogue / usage list in the real API shape (no tenant data). Ids are labels.
"""
import copy
import re
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import modelcheck as mc  # noqa: E402
import wsconfig  # noqa: E402

LOC = "swedencentral"
TODAY = date(2026, 10, 23)


def sku(name, usage, retire="2028-01-01", rate=((1.0, 60.0), (1000.0, 60.0))):
    return {"name": name, "usageName": usage, "deprecationDate": retire + "T00:00:00+00:00",
            "capacity": {"default": 10, "maximum": 1000000},
            "rateLimits": [{"count": c, "renewalPeriod": p} for c, p in rate]}


def entry(name, version, skus, lifecycle="GenerallyAvailable", retire="2028-01-01"):
    return {"kind": "OpenAI", "model": {"name": name, "version": version, "lifecycleStatus": lifecycle,
                                         "deprecation": {"inference": retire + "T00:00:00Z"}, "skus": skus}}


def usage(pool, current, limit):
    return {"name": {"value": pool}, "currentValue": current, "limit": limit}


def catalogue(legacy=False, retire="2028-01-01"):
    g, d = "GlobalStandard", "DataZoneStandard"
    return [
        entry("model-a", "1", [sku(g, "OpenAI.GlobalStandard.model-a", retire), sku(d, "OpenAI.DataZoneStandard.model-a", retire)],
              retire=retire),
        entry("model-b", "2", [sku(g, "OpenAI.GlobalStandard.model-b", retire)], lifecycle="Legacy" if legacy else "GenerallyAvailable",
              retire=retire),
        entry("embed-c", "1", [sku(g, "OpenAI.GlobalStandard.embed-c", retire, rate=((1.0, 10.0), (1000.0, 60.0)))], retire=retire),
        # the fine-tune pool shares the SKU name and must never be picked
        entry("model-a", "1", [sku(g, "OpenAI.GlobalStandard.model-a-finetune", retire)], retire=retire),
        entry("model-router", "9", [sku(g, "OpenAI.GlobalStandard.ModelRouter", retire)], retire=retire),
    ]


def usages(a=(100, 3000), b=(0, 2000), c=(10, 1000)):
    return [usage("OpenAI.GlobalStandard.model-a", *a), usage("OpenAI.GlobalStandard.model-b", *b),
            usage("OpenAI.GlobalStandard.embed-c", *c), usage("OpenAI.GlobalStandard.ModelRouter", 0, 500)]


def config(units=(800, 1000, 100), participants=30, workshop_date="TODO", default="model-a", tools="model-b",
           embeddings="embed-c", sku_type="GlobalStandard"):
    return {
        "workshop": {"date": workshop_date},
        "environments": {"test": {"participants": participants}},
        "models": {
            "default": default, "tools": tools, "embeddings": embeddings, "deployment_type": sku_type,
            "versions": {"model-a": "1", "model-b": "2", "embed-c": "1", "model-router": "9"},
            "units": {"test": dict(zip(("default", "tools", "embeddings"), units))},
            "retirement_warn_days": 120,
            "sizing": {
                "participant_minute": {"default": {"tokens_k": 18, "requests": 6}, "tools": {"tokens_k": 18, "requests": 6},
                                       "embeddings": {"tokens_k": 2, "requests": 3}},
                "facilitator_demo": {"default": {"tokens_k": 40, "requests": 20}, "tools": {"tokens_k": 40, "requests": 20},
                                     "embeddings": {"tokens_k": 5, "requests": 5}},
                "burst_factor": 1.25},
        },
    }


def dep(name, model, version, sku_name="GlobalStandard", capacity=10, fmt="OpenAI", account="aif-x", rg="rg-x"):
    return {"name": name, "account": account, "resourceGroup": rg, "sku": {"name": sku_name, "capacity": capacity},
            "properties": {"model": {"format": fmt, "name": model, "version": version}}}


def capacity_entry(model, version, sku_name, available, loc=LOC):
    return {"location": loc, "properties": {"skuName": sku_name, "availableCapacity": available,
                                            "model": {"format": "OpenAI", "name": model, "version": version}}}


def run(cfg=None, cat=None, use=None, deployments=(), capacities=None, deleted=(), own=("rg-x", "aif-x"), today=TODAY):
    return mc.evaluate(cfg or config(), "test", LOC, cat if cat is not None else catalogue(), use if use is not None else usages(),
                       list(deployments) if deployments is not None else None, capacities, list(deleted), own, today)[0]


def statuses(results, needle):
    return [r.status for r in results if needle in r.text]


class Catalogue(unittest.TestCase):
    def test_explicit_subscription_selects_the_authentication_account(self):
        with patch("azrest.Api") as api:
            api.return_value.get_all.return_value = []
            result = mc.fetch_live("target-subscription", LOC, [])
        api.assert_called_once_with("arm", subscription="target-subscription")
        self.assertEqual(result["warnings"], [])

    def test_a_fitting_plan_has_no_failures(self):
        res = run(deployments=[dep("model-b", "model-b", "2", capacity=500, account="aif-other", rg="rg-other")])
        self.assertNotIn("bad", [r.status for r in res], [r.text for r in res if r.status == "bad"])

    def test_missing_version_is_reported_with_what_is_offered(self):
        cfg = config()
        cfg["models"]["versions"]["model-a"] = "7"
        res = run(cfg)
        bad = [r.text for r in res if r.status == "bad" and "NOT offered" in r.text]
        self.assertEqual(len(bad), 1)
        self.assertIn("1/GlobalStandard", bad[0])

    def test_missing_catalogue_means_nothing_is_verified(self):
        res = mc.evaluate(config(), "test", LOC, None, usages(), [], None, [], None, TODAY)[0]
        self.assertEqual([r.status for r in res], ["bad"])

    def test_fine_tune_pool_is_never_used_for_quota(self):
        res = run()
        self.assertTrue(any("OpenAI.GlobalStandard.model-a:" in r.text for r in res))
        self.assertFalse(any("finetune" in r.text for r in res))


class Quota(unittest.TestCase):
    def test_free_quota_is_limit_minus_allocated_and_reported_per_pool(self):
        res = run()
        line = next(r for r in res if r.text.startswith("quota: pool OpenAI.GlobalStandard.model-a"))
        self.assertEqual(line.status, "ok")
        self.assertIn("free 2900K", line.text)
        self.assertIn("-> 2100K left", line.text)

    def test_insufficient_quota_fails_and_never_suggests_switching_region(self):
        res = run(use=usages(a=(2500, 3000)))
        line = next(r for r in res if r.text.startswith("quota: pool OpenAI.GlobalStandard.model-a"))
        self.assertEqual(line.status, "bad")
        self.assertIn("do not switch region", line.text)

    def test_existing_own_deployment_is_not_counted_twice(self):
        # 500 of the 800 planned units are already allocated to OUR deployment: only 300 are still needed
        res = run(use=usages(a=(2700, 3000)), deployments=[dep("model-a", "model-a", "1", capacity=500)])
        line = next(r for r in res if r.text.startswith("quota: pool OpenAI.GlobalStandard.model-a"))
        self.assertEqual(line.status, "ok")
        self.assertIn("still to allocate 300K", line.text)

    def test_plans_that_draw_on_one_pool_are_summed(self):
        cat = catalogue()
        cat.append(entry("model-d", "1", [sku("GlobalStandard", "OpenAI.GlobalStandard.model-a")]))  # same pool as model-a
        cfg = config(units=(800, 1000, 100), tools="model-d")
        cfg["models"]["versions"]["model-d"] = "1"
        res = run(cfg, cat, usages(a=(100, 1700)))  # free 1600 < 800 + 1000
        line = next(r for r in res if r.text.startswith("quota: pool OpenAI.GlobalStandard.model-a"))
        self.assertEqual(line.status, "bad")
        self.assertIn("model-a 800", line.text)
        self.assertIn("model-d 1000", line.text)

    def test_no_pool_for_the_model_is_an_eligibility_failure(self):
        res = run(use=[u for u in usages() if "model-a" not in u["name"]["value"]])
        self.assertIn("bad", statuses(res, "eligibility: no quota pool"))

    def test_zero_limit_pool_is_not_eligible(self):
        res = run(use=usages(a=(0, 0)))
        self.assertIn("bad", statuses(res, "limit 0"))

    def test_unattributed_allocation_is_reported_but_not_touched(self):
        res = run(use=usages(a=(1500, 3000)), deployments=[dep("model-a", "model-a", "1", capacity=500, account="aif-o", rg="rg-o")])
        info = [r for r in res if "not explained" in r.text and "model-a is" in r.text]
        self.assertEqual(len(info), 1)
        self.assertEqual(info[0].status, "info")
        self.assertIn("not touched", info[0].text)


class Eligibility(unittest.TestCase):
    def test_legacy_model_without_an_existing_deployment_warns(self):
        res = run(cat=catalogue(legacy=True), deployments=[])
        self.assertIn("warn", statuses(res, "a NEW deployment may be refused"))

    def test_legacy_model_with_an_existing_deployment_is_evidence(self):
        res = run(cat=catalogue(legacy=True), deployments=[dep("anything", "model-b", "2", account="aif-o", rg="rg-o")])
        self.assertIn("info", statuses(res, "existing-customer evidence"))
        self.assertNotIn("warn", statuses(res, "a NEW deployment may be refused"))

    def test_legacy_model_with_unreadable_deployments_is_unverified(self):
        res = mc.evaluate(config(), "test", LOC, catalogue(legacy=True), usages(), None, None, [], None, TODAY)[0]
        self.assertIn("warn", statuses(res, "not verified"))


class Lifecycle(unittest.TestCase):
    def test_retirement_inside_the_warning_window_warns(self):
        res = run(cat=catalogue(retire="2026-12-31"), use=usages())
        self.assertIn("warn", statuses(res, "retires 2026-12-31"))

    def test_retirement_before_the_workshop_fails(self):
        res = run(config(workshop_date="2026-12-01"), cat=catalogue(retire="2026-11-15"))
        self.assertIn("bad", statuses(res, "RETIRES"))

    def test_far_retirement_is_ok(self):
        self.assertIn("ok", statuses(run(), "retires 2028-01-01"))

    def test_non_ga_lifecycle_is_flagged(self):
        res = run(cat=catalogue(legacy=True))
        self.assertIn("warn", statuses(res, "lifecycle Legacy"))


class Capacity(unittest.TestCase):
    def full(self, a=3000):
        return [capacity_entry("model-a", "1", "GlobalStandard", a), capacity_entry("model-b", "2", "GlobalStandard", 5000),
                capacity_entry("embed-c", "1", "GlobalStandard", 900)]

    def test_capacity_api_is_a_separate_line_and_states_its_limit(self):
        res = run(capacities=self.full())
        lines = [r for r in res if r.text.startswith("capacity:")]
        self.assertEqual(len(lines), 3)
        self.assertTrue(all("only proof" in l.text for l in lines))

    def test_capacity_below_the_plan_fails(self):
        res = run(capacities=self.full(a=100))
        self.assertIn("bad", statuses(res, "capacity: API reports only"))

    def test_not_queried_is_not_verified(self):
        self.assertIn("warn", statuses(run(capacities=None), "capacity API: not queried"))

    def test_other_regions_are_ignored(self):
        caps = [capacity_entry("model-a", "1", "GlobalStandard", 9999, loc="elsewhere")]
        self.assertIn("warn", statuses(run(capacities=caps), "no GlobalStandard entry for model-a"))


class Rates(unittest.TestCase):
    def test_rate_per_unit_comes_from_the_catalogue(self):
        idx = mc.index_catalogue(catalogue())
        self.assertEqual(mc.per_unit_rates(idx[("model-a", "1", "GlobalStandard")][1]), (1.0, 1.0))
        self.assertEqual(mc.per_unit_rates(idx[("embed-c", "1", "GlobalStandard")][1]), (1.0, 6.0))

    def test_rpm_is_reported_next_to_tpm(self):
        res = run()
        self.assertTrue(any("100 units = 100K TPM and 600 RPM" in r.text for r in res))

    def test_keyed_rate_limits_are_understood(self):
        s = {"rateLimits": [{"key": "token", "count": 50000, "renewalPeriod": 60}, {"key": "request", "count": 300, "renewalPeriod": 60}]}
        self.assertEqual(mc.per_unit_rates(s), (50.0, 300.0))


class Sizing(unittest.TestCase):
    def test_thirty_participants_fit_the_default_allocation(self):
        res = run()
        line = next(r for r in res if r.text.startswith("sizing default"))
        self.assertEqual(line.status, "ok")
        self.assertIn("725K TPM needed vs 800K planned", line.text)
        self.assertIn("250 RPM needed", line.text)
        self.assertIn("not measurements", line.text)

    def test_too_few_units_warn_instead_of_silently_passing(self):
        res = run(config(units=(400, 1000, 100)))
        self.assertEqual(next(r for r in res if r.text.startswith("sizing default")).status, "warn")


class Guards(unittest.TestCase):
    def test_a_model_router_in_the_plan_fails(self):
        cfg = config(default="model-router")
        cfg["models"]["versions"]["model-router"] = "9"
        self.assertIn("bad", statuses(run(cfg), "model-router"))

    def test_a_router_deployed_in_the_workshop_account_fails(self):
        res = run(deployments=[dep("router", "model-router", "9")])
        self.assertIn("bad", statuses(res, "unexpected model-router deployment"))

    def test_other_providers_and_ptu_fail(self):
        res = run(deployments=[dep("m", "partner-model", "1", fmt="Other"), dep("p", "model-a", "1", sku_name="GlobalProvisionedManaged")])
        self.assertIn("bad", statuses(res, "only OpenAI models are approved"))
        self.assertIn("bad", statuses(res, "provisioned (PTU)"))

    def test_extra_deployments_warn(self):
        self.assertIn("warn", statuses(run(deployments=[dep("extra", "model-a", "1")]), "extra deployment"))

    def test_ptu_deployment_type_in_the_plan_fails(self):
        self.assertIn("bad", statuses(run(config(sku_type="GlobalProvisionedManaged")), "not allowed"))

    def test_units_outside_the_bicep_limits_fail(self):
        self.assertIn("bad", statuses(run(config(units=(5000, 1000, 100))), "outside"))
        self.assertIn("bad", statuses(run(config(units=(800, 1000, 5))), "outside"))

    def test_two_roles_must_not_share_a_deployment(self):
        self.assertIn("bad", statuses(run(config(tools="model-a")), "both use deployment"))

    def test_soft_deleted_accounts_are_mentioned_never_purged(self):
        res = run(deleted=[{"name": "old-account"}])
        line = next(r for r in res if r.text.startswith("1 soft-deleted Foundry account"))
        self.assertIn("separate approval", line.text)


class RealConfigAndBicep(unittest.TestCase):
    def test_limits_match_the_bicep_source(self):
        main = (ROOT / "infra" / "main.bicep").read_text(encoding="utf-8")
        foundry = (ROOT / "infra" / "modules" / "foundry.bicep").read_text(encoding="utf-8")
        lo = {int(m) for m in re.findall(r"@minValue\((\d+)\)\s*@maxValue\(\d+\)\s*param (?:chat|tools|embedding)TpmCapThousands", main)}
        self.assertEqual(lo, {mc.MIN_UNITS})
        self.assertEqual(int(re.search(r"@maxValue\((\d+)\)\s*capacity: int", foundry).group(1)), mc.MAX_UNITS)

    def test_the_real_plans_follow_workshop_yaml(self):
        cfg = wsconfig.load("mcaps")
        plans = {p.role: p for p in mc.plans(cfg, "mcaps")}
        self.assertEqual(plans["default"].units, 800)
        self.assertEqual(plans["tools"].units, 1000)
        self.assertEqual(plans["embeddings"].units, 100)
        self.assertTrue(all(p.version for p in plans.values()))

    def test_table_and_record_are_produced(self):
        res, recs = mc.evaluate(config(), "test", LOC, catalogue(), usages(), [], None, [], None, TODAY)
        self.assertEqual([r["role"] for r in recs], ["default", "tools", "embeddings"])
        self.assertIn("| default | model-a 1 |", mc.table(recs))


if __name__ == "__main__":
    unittest.main()
