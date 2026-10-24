"""The target guard: the shell must be pointed at the workshop subscription and tenant before anything runs.

Offline; no Azure calls. Ids are plain labels, not real identifiers.
"""
import base64
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import azrest  # noqa: E402
import target  # noqa: E402

WANT_SUB, WANT_TENANT = "sub-workshop", "tenant-workshop"


def active(sub=WANT_SUB, tenant=WANT_TENANT, name="Workshop subscription"):
    return {"id": sub, "tenantId": tenant, "name": name, "user": {"name": "facilitator@example.test"}}


def fake_jwt(claims: dict) -> str:
    def b64(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'none'})}.{b64(claims)}.sig"


class Evaluate(unittest.TestCase):
    def check(self, act, environ=None, tenant_only=False, sub=WANT_SUB):
        return target.evaluate("mcaps", sub, WANT_TENANT, act, environ or {}, tenant_only=tenant_only)

    def test_match_has_no_problems(self):
        self.assertEqual(self.check(active()), [])

    def test_case_insensitive_ids(self):
        self.assertEqual(self.check(active(sub="SUB-WORKSHOP", tenant="Tenant-Workshop")), [])

    def test_wrong_subscription_names_the_fix_and_never_switches(self):
        problems = self.check(active(sub="sub-other", name="Some other subscription"))
        self.assertEqual(len(problems), 1)
        self.assertIn("az account set --subscription sub-workshop", problems[0])
        self.assertIn("Some other subscription", problems[0])

    def test_wrong_tenant_is_reported_separately(self):
        problems = self.check(active(tenant="tenant-other"))
        self.assertTrue(any("az login --tenant tenant-workshop" in p for p in problems))

    def test_not_signed_in(self):
        problems = self.check(None)
        self.assertEqual(len(problems), 1)
        self.assertIn("not signed in", problems[0])

    def test_stale_environment_values_are_caught_even_when_az_matches(self):
        problems = self.check(active(), {"AZURE_SUBSCRIPTION_ID": "sub-old", "AZURE_TENANT_ID": "tenant-old"})
        self.assertEqual(len(problems), 2)

    def test_matching_environment_values_are_fine(self):
        self.assertEqual(self.check(active(), {"AZURE_SUBSCRIPTION_ID": WANT_SUB, "AZURE_TENANT_ID": WANT_TENANT}), [])

    def test_tenant_only_mode_ignores_the_subscription(self):
        self.assertEqual(self.check(active(sub="sub-other"), {"AZURE_SUBSCRIPTION_ID": "sub-old"}, tenant_only=True), [])
        self.assertTrue(self.check(active(sub="sub-other", tenant="tenant-other"), tenant_only=True))

    def test_placeholder_subscription_is_refused(self):
        problems = target.evaluate("mcaps", "TODO", WANT_TENANT, active(), {})
        self.assertIn("not set", problems[0])
        self.assertTrue(target.evaluate("mcaps", "", WANT_TENANT, active(), {}))


class Configured(unittest.TestCase):
    def test_reads_the_ids_for_each_environment(self):
        mcaps = target.configured("mcaps")
        sponsor = target.configured("sponsor")
        self.assertNotEqual(mcaps, sponsor)
        self.assertTrue(all(mcaps) and all(sponsor))

    def test_unknown_environment_yields_empty_values(self):
        self.assertEqual(target.configured("nope", {"environments": {}}), ("", ""))


class Tokens(unittest.TestCase):
    def test_tenant_claim_is_read_from_the_payload(self):
        self.assertEqual(azrest.token_tenant(fake_jwt({"tid": "tenant-workshop", "oid": "user-1"})), "tenant-workshop")
        self.assertEqual(azrest.token_tenant("not-a-jwt"), "")

    def proc(self, token, code=0):
        return mock.Mock(returncode=code, stdout=token + "\n", stderr="")

    def test_token_for_the_expected_tenant_is_accepted(self):
        token = fake_jwt({"tid": WANT_TENANT})
        with mock.patch.object(azrest, "run_az", return_value=self.proc(token)) as run:
            self.assertEqual(azrest.az_token("https://example.test", tenant=WANT_TENANT), token)
        self.assertIn("--tenant", run.call_args.args[0])

    def test_token_for_another_tenant_is_refused(self):
        with mock.patch.object(azrest, "run_az", return_value=self.proc(fake_jwt({"tid": "tenant-other"}))):
            with self.assertRaises(SystemExit) as ctx:
                azrest.az_token("https://example.test", tenant=WANT_TENANT)
        self.assertIn("refusing to call", str(ctx.exception))

    def test_subscription_is_preferred_over_tenant_to_select_the_account(self):
        token = fake_jwt({"tid": WANT_TENANT})
        with mock.patch.object(azrest, "run_az", return_value=self.proc(token)) as run:
            azrest.az_token("https://example.test", tenant=WANT_TENANT, subscription=WANT_SUB)
        args = run.call_args.args[0]
        self.assertIn("--subscription", args)
        self.assertNotIn("--tenant", args)

    def test_a_hung_token_request_becomes_a_clear_error(self):
        import subprocess
        with mock.patch.object(azrest, "run_az", side_effect=subprocess.TimeoutExpired("az", 1)):
            with self.assertRaises(SystemExit) as ctx:
                azrest.az_token("https://example.test", tenant=WANT_TENANT)
        self.assertIn("did not finish", str(ctx.exception))
        self.assertIn("az login --tenant", str(ctx.exception))


class SelectParams(unittest.TestCase):
    """scripts/select-params.py: never adopts a resource group that is not this workshop's."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("select_params", ROOT / "scripts" / "select-params.py")
        cls.sp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.sp)

    def state(self, shown, count="0"):
        with mock.patch.object(self.sp.azrest, "Api") as api:
            api.return_value.get.return_value = json.loads(shown) if shown else None
            api.return_value.get_all.return_value = [{"name": "resource"}] * int(count)
            result = self.sp.rg_state("rg-test", "sub-workshop", "mcaps")
        api.assert_called_once_with("arm", subscription="sub-workshop")
        return result

    def test_missing_group(self):
        self.assertEqual(self.state(""), "missing")

    def test_group_tagged_as_ours(self):
        tags = json.dumps({"tags": {"workshop": "livewell", "azd-env-name": "mcaps"}})
        self.assertEqual(self.state(tags, "12"), "ours")

    def test_empty_foreign_group_is_adoptable(self):
        self.assertEqual(self.state(json.dumps({"tags": {}}), "0"), "empty")

    def test_foreign_group_with_resources_is_refused(self):
        self.assertEqual(self.state(json.dumps({"tags": {"workshop": "livewell", "azd-env-name": "sponsor"}}), "7"), "foreign")
        self.assertEqual(self.state(json.dumps({"tags": None}), "3"), "foreign")

    def test_unreadable_group_is_not_treated_as_missing(self):
        with mock.patch.object(self.sp.azrest, "Api") as api:
            api.return_value.get.side_effect = azrest.ApiError(403, "", "https://example.test")
            with self.assertRaises(azrest.ApiError):
                self.sp.rg_state("rg-test", "sub-workshop", "mcaps")

    def test_unreadable_inventory_is_not_treated_as_empty(self):
        with mock.patch.object(self.sp.azrest, "Api") as api:
            api.return_value.get.return_value = {"tags": {}}
            api.return_value.get_all.side_effect = azrest.ApiError(403, "", "https://example.test")
            with self.assertRaises(azrest.ApiError):
                self.sp.rg_state("rg-test", "sub-workshop", "mcaps")


if __name__ == "__main__":
    unittest.main()
