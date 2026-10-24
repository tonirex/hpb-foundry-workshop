"""Tests for the Temporary Access Pass tooling: scripts/lib/issue_tap.py, the tap mode of scripts/lib/lab_users.py and the
tap cards of scripts/tenant/sign-in-cards.py. Standard library only and no network: Graph is a fake client.

    python -m unittest discover -s tests -p "test_tap.py"

Scratch files go to test-results/unittest-tap/ (gitignored) and are removed after each test. Pass values in the fixtures
are the obvious strings FAKE-TAP-VALUE-nnnn, so a leak into stdout or a file is easy to see.
"""
from __future__ import annotations

import base64
import contextlib
import csv
import importlib.util
import io
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import types
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import issue_tap  # noqa: E402
import lab_users  # noqa: E402
from azrest import ApiError  # noqa: E402

NOW = datetime(2026, 11, 2, 12, 0, 0, tzinfo=timezone.utc)
SECRET = "FAKE-TAP-VALUE-"
SCOPE = issue_tap.TAP_SCOPE
SCRATCH_PARENT = ROOT / "test-results" / "unittest-tap"
GUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def flat(text: str) -> str:
    """Console fix text is wrapped; collapse whitespace so a phrase can be found wherever the line broke."""
    return re.sub(r"\s+", " ", text)


def fake_jwt(claims: dict) -> str:
    def part(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'none'})}.{part(claims)}.signature"


def api_error(status: int, code: str = "", message: str = "") -> ApiError:
    body = json.dumps({"error": {"code": code, "message": message}}) if code else ""
    return ApiError(status, body, "https://graph.example.test/fake")


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def make_cfg(sign_in: str = "tap", count: int = 3, lifetime: int = 480, one_time: bool = False) -> dict:
    return {
        "workshop": {"name": "LiveWell Coach - Test Workshop", "customer": "Example Customer", "date": "TODO",
                     "repo_url": "https://repo.example.test/workshop", "guest_wifi": {"ssid": "TODO", "code": "TODO"}},
        "names": {"foundry_project": "livewell-workshop"},
        "entra_roles": {"global_administrator": "role-ga"},
        "environments": {"mcaps": {
            "tenant_id": "tenant-0001",
            "lab_accounts": {"prefix": "hpb.lab", "count": count, "usage_location": "SG",
                             "break_glass": "hpb.breakglass", "sign_in": sign_in,
                             "tap": {"lifetime_minutes": lifetime, "one_time_use": one_time}}}},
    }


def good_policy(**over) -> dict:
    policy = {"id": "TemporaryAccessPass", "state": "enabled", "minimumLifetimeInMinutes": 60,
              "maximumLifetimeInMinutes": 480, "defaultLifetimeInMinutes": 60, "isUsableOnce": False,
              "includeTargets": [{"id": "all_users", "targetType": "group"}], "excludeTargets": []}
    policy.update(over)
    return policy


class FakeGraph:
    """Just enough Microsoft Graph for lab_users and issue_tap, with the azrest.Api interface (token, get, post, patch,
    delete). Every call is recorded as (method, path, body); `fail` holds (method, path fragment, ApiError) rules."""

    def __init__(self, count: int = 3, scopes: tuple = (SCOPE,), policy: dict | None = None,
                 domain: str = "example.test", users: bool = True) -> None:
        self.domain = domain
        self.token = fake_jwt({"scp": " ".join(("User.Read",) + tuple(scopes)), "upn": "admin@example.test"})
        self.policy = policy if policy is not None else good_policy()
        self.users: dict[str, dict] = {}
        self.taps: dict[str, list[dict]] = {}
        self.role_assignments: list[dict] = []
        self.sessions_revoked: list[str] = []
        self.calls: list[tuple] = []
        self.fail: list[tuple] = []
        self.seq = 0
        self.user_seq = 0
        if users:
            for i in range(1, count + 1):
                self.add_user(f"hpb.lab{i:02d}")

    def add_user(self, nick: str, enabled: bool = True) -> dict:
        self.user_seq += 1
        user = {"id": f"user-{self.user_seq:04d}", "userPrincipalName": f"{nick}@{self.domain}",
                "usageLocation": "SG", "accountEnabled": enabled}
        self.users[user["userPrincipalName"].lower()] = user
        return user

    def uid(self, nick: str) -> str:
        return self.users[f"{nick}@{self.domain}".lower()]["id"]

    def add_tap(self, nick: str, start: datetime, minutes: int = 480, reason: str = "EnabledByPolicy",
                one_time: bool = False) -> dict:
        self.seq += 1
        method = {"id": f"tap-{self.seq:04d}", "createdDateTime": iso(start), "startDateTime": iso(start),
                  "lifetimeInMinutes": minutes, "isUsableOnce": one_time, "isUsable": reason == "EnabledByPolicy",
                  "methodUsabilityReason": reason}
        self.taps.setdefault(self.uid(nick), []).append(method)
        return method

    def calls_of(self, method: str, fragment: str = "") -> list[tuple]:
        return [c for c in self.calls if c[0] == method and fragment in c[1]]

    def _record(self, method: str, path: str, body: object = None) -> None:
        self.calls.append((method, path, body))
        for m, fragment, error in self.fail:
            if m == method and fragment in path:
                raise error

    def get(self, path: str, ok_404: bool = False):
        self._record("GET", path)
        if path.startswith("/v1.0/organization"):
            return {"value": [{"id": "tenant-0001", "displayName": "Example Tenant", "countryLetterCode": "SG",
                               "verifiedDomains": [{"name": "other.example.test", "isDefault": False},
                                                   {"name": self.domain, "isDefault": True}]}]}
        if path.startswith(issue_tap.POLICY_PATH):
            return dict(self.policy)
        m = re.fullmatch(r"/v1\.0/users/([^/?]+)/authentication/temporaryAccessPassMethods", path)
        if m:
            return {"value": [dict(t) for t in self.taps.get(m.group(1), [])]}
        if path.startswith("/v1.0/roleManagement/directory/roleAssignments"):
            wanted = urllib.parse.unquote(path)
            return {"value": [r for r in self.role_assignments if f"'{r['principalId']}'" in wanted]}
        m = re.fullmatch(r"/v1\.0/users/([^/?]+)(\?.*)?", path)
        if m:
            user = self.users.get(m.group(1).lower())
            if user is None:
                if ok_404:
                    return None
                raise api_error(404, "Request_ResourceNotFound")
            return dict(user)
        raise AssertionError(f"FakeGraph: unexpected GET {path}")

    def post(self, path: str, body: object = None):
        self._record("POST", path, body)
        m = re.fullmatch(r"/v1\.0/users/([^/?]+)/authentication/temporaryAccessPassMethods", path)
        if m:
            start = issue_tap.parse_utc(body.get("startDateTime")) or NOW
            self.seq += 1
            method = {"id": f"tap-{self.seq:04d}", "createdDateTime": iso(NOW), "startDateTime": iso(start),
                      "lifetimeInMinutes": body["lifetimeInMinutes"], "isUsableOnce": body["isUsableOnce"],
                      "isUsable": start <= NOW,
                      "methodUsabilityReason": "EnabledByPolicy" if start <= NOW else "NotYetValid"}
            self.taps.setdefault(m.group(1), []).append(method)
            return {**method, "temporaryAccessPass": f"{SECRET}{self.seq:04d}"}
        m = re.fullmatch(r"/v1\.0/users/([^/?]+)/revokeSignInSessions", path)
        if m:
            self.sessions_revoked.append(m.group(1))
            return {"value": True}
        if path == "/v1.0/users":
            user = self.add_user(body["userPrincipalName"].split("@")[0], body.get("accountEnabled", True))
            user["usageLocation"] = body.get("usageLocation")
            return dict(user)
        if path == "/v1.0/roleManagement/directory/roleAssignments":
            self.role_assignments.append(dict(body))
            return dict(body)
        raise AssertionError(f"FakeGraph: unexpected POST {path}")

    def patch(self, path: str, body: object):
        self._record("PATCH", path, body)
        m = re.fullmatch(r"/v1\.0/users/([^/?]+)", path)
        for user in self.users.values():
            if m and user["id"] == m.group(1):
                user.update({k: v for k, v in body.items() if k != "passwordProfile"})
                return {}
        raise AssertionError(f"FakeGraph: unexpected PATCH {path}")

    def delete(self, path: str):
        self._record("DELETE", path)
        m = re.fullmatch(r"/v1\.0/users/([^/?]+)/authentication/temporaryAccessPassMethods/([^/?]+)", path)
        if m:
            self.taps[m.group(1)] = [t for t in self.taps.get(m.group(1), []) if t["id"] != m.group(2)]
            return {}
        m = re.fullmatch(r"/v1\.0/users/([^/?]+)", path)
        if m:
            self.users = {k: u for k, u in self.users.items() if u["id"] != m.group(1)}
            return {}
        raise AssertionError(f"FakeGraph: unexpected DELETE {path}")


class Scratch(unittest.TestCase):
    """A private scratch directory inside the repo (gitignored test-results/), removed after every test."""

    counter = itertools.count(1)

    def setUp(self) -> None:
        super().setUp()
        SCRATCH_PARENT.mkdir(parents=True, exist_ok=True)
        self.scratch = SCRATCH_PARENT / f"{os.getpid()}-{next(self.counter)}"  # short: Windows paths are limited
        shutil.rmtree(self.scratch, ignore_errors=True)
        self.scratch.mkdir(parents=True)
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        shutil.rmtree(self.scratch, ignore_errors=True)
        for parent in (SCRATCH_PARENT, SCRATCH_PARENT.parent):
            with contextlib.suppress(OSError):
                parent.rmdir()  # only when empty

    @property
    def tap_csv(self) -> Path:
        return self.scratch / ".azure" / "mcaps" / "tap-issued.csv"

    def read_tap_rows(self) -> list[dict]:
        return read_csv(self.tap_csv)


class TapTestCase(Scratch):
    def setUp(self) -> None:
        super().setUp()
        self.graph = FakeGraph()

    def tap(self, *argv: str, graph: FakeGraph | None = None, cfg: dict | None = None):
        """Run issue_tap.main with the fake client. Returns (exit code, stdout, stderr, times the client was built)."""
        out, err, built = io.StringIO(), io.StringIO(), []

        def factory():
            built.append(1)
            return graph or self.graph

        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = issue_tap.main(list(argv), cfg=cfg or make_cfg(), client_factory=factory, root=self.scratch,
                                  environ={"AZURE_ENV_NAME": "mcaps"}, now=lambda: NOW)
        return code, out.getvalue(), err.getvalue(), len(built)


class PlanOnlyTests(TapTestCase):
    def test_issue_plan_only_default_makes_no_client_calls(self):
        code, out, err, built = self.tap("issue")
        self.assertEqual(code, 0)
        self.assertEqual(built, 0, "the Graph client must not even be built in plan-only mode")
        self.assertEqual(self.graph.calls, [])
        self.assertIn("PLAN ONLY", out)
        self.assertIn("<tenant-domain>", out)
        self.assertIn("480 minutes", out)
        self.assertIn("no: reusable", out)
        self.assertIn(".azure/mcaps/tap-issued.csv", out)
        self.assertIn("hpb.lab01 .. hpb.lab03", out)
        self.assertFalse(self.tap_csv.exists())

    def test_plan_shows_start_time_and_lifetime_overrides(self):
        code, out, _, built = self.tap("issue", "--start", "2026-11-03T08:00:00+08:00", "--lifetime-minutes", "240",
                                       "--only", "2")
        self.assertEqual((code, built), (0, 0))
        self.assertIn("240 minutes", out)
        self.assertIn("2026-11-03T00:00:00Z", out)
        self.assertIn("08:00 SGT", out)
        self.assertIn("hpb.lab02", out)
        self.assertNotIn("hpb.lab01", out)

    def test_revoke_plan_only_default_makes_no_client_calls(self):
        code, out, _, built = self.tap("revoke")
        self.assertEqual((code, built), (0, 0))
        self.assertEqual(self.graph.calls, [])
        self.assertIn("REVOKE PLAN ONLY", out)
        self.assertIn("does NOT", out)

    def test_plan_mentions_replace_show_secrets_and_a_password_environment(self):
        code, out, _, built = self.tap("issue", "--replace", "--show-secrets", cfg=make_cfg(sign_in="password"))
        self.assertEqual((code, built), (0, 0))
        self.assertIn("replace    : yes", out)
        self.assertIn("show       : yes", out)
        self.assertIn("NOTE       sign_in is 'password'", out)
        self.assertEqual(self.graph.calls, [])

    def test_plan_warns_about_a_start_time_in_the_past(self):
        code, out, _, built = self.tap("issue", "--start", "2026-11-01T08:00:00+08:00")
        self.assertEqual((code, built), (0, 0))
        self.assertIn("--start is not in the future", flat(out))

    def test_status_is_the_only_subcommand_that_reads_without_a_flag(self):
        code, _, _, built = self.tap("status")
        self.assertEqual((code, built), (0, 1))
        self.assertTrue(self.graph.calls)
        self.assertEqual({c[0] for c in self.graph.calls}, {"GET"})

    def test_importing_the_modules_never_asks_azure_for_a_token(self):
        code = ("import sys\n"
                f"sys.path.insert(0, {str(ROOT / 'scripts' / 'lib')!r})\n"
                "import azrest\n"
                "def boom(*a, **k):\n"
                "    raise AssertionError('a token was requested while importing')\n"
                "azrest.az_token = boom\n"
                "import issue_tap, lab_users\n"
                "print('imported')\n")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "imported"), done.stderr)

    def test_usage_errors_exit_2_before_any_client_call(self):
        for argv in (("issue", "--only", "9"), ("issue", "--start", "2026-11-03T08:00:00"), ("issue", "--count", "0"),
                     ("issue", "--lifetime-minutes", "0"), ("issue", "--check", "--apply")):
            code, _, err, built = self.tap(*argv)
            self.assertEqual((code, built), (2, 0), argv)
            self.assertTrue(err.strip(), argv)


class CheckTests(TapTestCase):
    def test_check_passes_and_only_reads(self):
        code, out, _, _ = self.tap("issue", "--check")
        self.assertEqual(code, 0, out)
        self.assertTrue(self.graph.calls)
        self.assertEqual({c[0] for c in self.graph.calls}, {"GET"}, "--check must never modify anything")
        self.assertIn("PASS  the Temporary Access Pass policy is enabled", out)
        self.assertIn("PASS  all 3 lab accounts exist and are enabled", out)
        self.assertIn(f"the Graph token carries {SCOPE}", out)
        self.assertIn("default domain example.test", out)
        self.assertFalse(self.tap_csv.exists())
        self.assertFalse(any(" " in c[1] for c in self.graph.calls), "URLs must not contain spaces")

    def test_check_warns_when_the_token_lacks_the_scope(self):
        graph = FakeGraph(scopes=())
        code, out, _, _ = self.tap("issue", "--check", graph=graph)
        self.assertEqual(code, 0, "a missing scope is a warning, not a failure")
        self.assertIn(f"WARN  the Graph token does not carry {SCOPE}", out)
        text = flat(out)
        self.assertIn("Authentication Administrator", text)
        self.assertIn("Privileged Authentication", text)
        self.assertIn("plain az CLI token may not carry that scope", text)
        self.assertIn("UNVERIFIED", text)
        self.assertEqual({c[0] for c in graph.calls}, {"GET"})

    def test_check_reads_application_roles_as_well_as_delegated_scopes(self):
        graph = FakeGraph(scopes=())
        graph.token = fake_jwt({"roles": [SCOPE], "appid": "app-0001"})
        code, out, _, _ = self.tap("issue", "--check", graph=graph)
        self.assertEqual(code, 0)
        self.assertIn(f"the Graph token carries {SCOPE}", out)

    def test_check_fails_when_the_policy_is_disabled(self):
        graph = FakeGraph(policy=good_policy(state="disabled"))
        code, out, _, _ = self.tap("issue", "--check", graph=graph)
        self.assertEqual(code, 1)
        self.assertIn("FAIL  the Temporary Access Pass policy is 'disabled', not enabled", out)
        self.assertIn("Authentication Policy Administrator", flat(out))
        self.assertIn("never edits it", flat(out))
        self.assertEqual({c[0] for c in graph.calls}, {"GET"})

    def test_check_fails_when_the_lifetime_is_outside_the_policy_bounds(self):
        code, out, _, _ = self.tap("issue", "--check", graph=FakeGraph(policy=good_policy(maximumLifetimeInMinutes=240)))
        self.assertEqual(code, 1)
        self.assertIn("above the policy maximum (240 minutes)", out)
        code, out, _, _ = self.tap("issue", "--check", "--lifetime-minutes", "30")
        self.assertEqual(code, 1)
        self.assertIn("below the policy minimum (60 minutes)", out)
        code, out, _, _ = self.tap("issue", "--check", "--lifetime-minutes", "120")
        self.assertEqual(code, 0)
        self.assertIn("within the policy bounds (60 to 480 minutes)", out)

    def test_check_fails_when_the_policy_forces_one_time_use(self):
        code, out, _, _ = self.tap("issue", "--check", graph=FakeGraph(policy=good_policy(isUsableOnce=True)))
        self.assertEqual(code, 1)
        self.assertIn("forces one-time passes", out)
        self.assertIn("tap.one_time_use: false", out)
        self.assertIn("Authentication Policy Administrator", flat(out))

    def test_check_accepts_a_forced_one_time_policy_when_the_config_asks_for_it(self):
        code, out, _, _ = self.tap("issue", "--check", graph=FakeGraph(policy=good_policy(isUsableOnce=True)),
                                   cfg=make_cfg(one_time=True))
        self.assertEqual(code, 0, out)
        self.assertIn("as workshop.yaml asks", out)

    def test_check_does_not_claim_group_scoped_policies_cover_the_lab_accounts(self):
        policy = good_policy(includeTargets=[{"id": "group-0001", "targetType": "group"}])
        code, out, _, _ = self.tap("issue", "--check", graph=FakeGraph(policy=policy))
        self.assertEqual(code, 0)
        self.assertIn("WARN  the policy targets 1 specific group(s), not all users: verify group membership", out)
        self.assertNotIn("targets all users", out)

    def test_check_warns_about_excluded_groups_even_for_all_users(self):
        policy = good_policy(excludeTargets=[{"id": "group-0002", "targetType": "group"}])
        code, out, _, _ = self.tap("issue", "--check", graph=FakeGraph(policy=policy))
        self.assertEqual(code, 0)
        self.assertIn("excludes 1 group(s): verify group membership", out)

    def test_check_reports_missing_and_disabled_accounts(self):
        graph = FakeGraph(count=3)
        del graph.users["hpb.lab02@example.test"]
        graph.users["hpb.lab03@example.test"]["accountEnabled"] = False
        code, out, _, _ = self.tap("issue", "--check", graph=graph)
        self.assertEqual(code, 1)
        self.assertIn("1 of 3 accounts do not exist: hpb.lab02@example.test", out)
        self.assertIn("create-lab-users.sh mcaps", out)
        self.assertIn("1 of 3 accounts are disabled: hpb.lab03@example.test", out)

    def test_check_explains_a_403_with_the_role_and_scope_text(self):
        graph = FakeGraph()
        graph.fail.append(("GET", "temporaryAccessPassMethods", api_error(403, "Authorization_RequestDenied",
                                                                           "Insufficient privileges")))
        code, out, _, _ = self.tap("issue", "--check", graph=graph)
        self.assertEqual(code, 1)
        self.assertIn("HTTP 403 Authorization_RequestDenied: Insufficient privileges", out)
        text = flat(out)
        self.assertIn("Authentication Administrator role (Privileged Authentication Administrator for admin accounts)",
                      text)
        self.assertIn(SCOPE, text)
        self.assertIn("Authentication Policy Administrator", text)
        self.assertEqual(len(graph.calls_of("GET", "temporaryAccessPassMethods")), 1,
                         "after a 403 the same answer would follow for every account: stop asking")

    def test_check_explains_a_403_on_the_policy_and_a_401(self):
        graph = FakeGraph()
        graph.fail.append(("GET", issue_tap.POLICY_PATH, api_error(403, "Authorization_RequestDenied")))
        code, out, _, _ = self.tap("issue", "--check", graph=graph)
        self.assertEqual(code, 1)
        self.assertIn("cannot read the Temporary Access Pass policy: HTTP 403", out)
        self.assertIn("Authentication Policy Administrator", flat(out))
        graph = FakeGraph()
        graph.fail.append(("GET", "/v1.0/organization", api_error(401, "InvalidAuthenticationToken")))
        code, out, _, _ = self.tap("issue", "--check", graph=graph)
        self.assertEqual(code, 1)
        self.assertIn("az login --tenant tenant-0001", flat(out))

    def test_check_explains_a_404_on_the_policy_and_a_400(self):
        graph = FakeGraph()
        graph.fail.append(("GET", issue_tap.POLICY_PATH, api_error(404, "Request_ResourceNotFound")))
        code, out, _, _ = self.tap("issue", "--check", graph=graph)
        self.assertEqual(code, 1)
        self.assertIn("could not find the Temporary Access Pass policy (HTTP 404)", flat(out))
        graph = FakeGraph()
        graph.fail.append(("GET", "temporaryAccessPassMethods", api_error(400, "BadRequest", "Bad value")))
        code, out, _, _ = self.tap("issue", "--check", graph=graph)
        self.assertEqual(code, 1)
        self.assertIn("HTTP 400 BadRequest: Bad value", out)
        self.assertIn("run `issue --check`", flat(out))

    def test_check_refuses_an_environment_that_signs_in_with_passwords(self):
        code, out, _, _ = self.tap("issue", "--check", cfg=make_cfg(sign_in="password"))
        self.assertEqual(code, 1)
        self.assertIn("is 'password', not 'tap'", out)

    def test_check_fails_for_a_start_time_in_the_past(self):
        code, out, _, _ = self.tap("issue", "--check", "--start", "2026-11-01T08:00:00+08:00")
        self.assertEqual(code, 1)
        self.assertIn("is not in the future", out)

    def test_check_reports_existing_passes(self):
        self.graph.add_tap("hpb.lab01", NOW - timedelta(hours=1))
        code, out, _, _ = self.tap("issue", "--check")
        self.assertEqual(code, 0)
        self.assertIn("1 of 3 accounts already hold an unexpired pass", out)


class IssueTests(TapTestCase):
    def apply(self, *extra: str, **kw):
        return self.tap("issue", "--apply", *extra, **kw)

    def test_apply_writes_the_csv_and_keeps_secrets_off_the_console(self):
        code, out, err, _ = self.apply()
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.graph.calls_of("POST", "temporaryAccessPassMethods")), 3)
        header = self.tap_csv.read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(header, "upn,tap_id,tap,start_utc,expires_utc,one_time")
        rows = self.read_tap_rows()
        self.assertEqual([r["upn"] for r in rows], [f"hpb.lab0{i}@example.test" for i in (1, 2, 3)])
        for row in rows:
            self.assertTrue(row["tap"].startswith(SECRET), row)
            self.assertTrue(row["tap_id"].startswith("tap-"))
            self.assertEqual(row["start_utc"], "2026-11-02T12:00:00Z")
            self.assertEqual(row["expires_utc"], "2026-11-02T20:00:00Z")
            self.assertEqual(row["one_time"], "false")
        self.assertNotIn(SECRET, out)
        self.assertNotIn(SECRET, err)
        self.assertIn("hpb.lab01@example.test", out)
        self.assertIn("until 2026-11-02T20:00:00Z (Tue 3 Nov 2026, 04:00 SGT)", out)
        self.assertIn("created 3, replaced 0, skipped 0, failed 0", out)
        body = self.graph.calls_of("POST", "temporaryAccessPassMethods")[0][2]
        self.assertEqual(body, {"lifetimeInMinutes": 480, "isUsableOnce": False})

    def test_show_secrets_prints_a_loud_warning_before_the_first_value(self):
        code, out, _, _ = self.apply("--show-secrets")
        self.assertEqual(code, 0)
        self.assertIn("--show-secrets", out)
        self.assertIn("VALUES are printed below", out)
        self.assertLess(out.index("VALUES are printed below"), out.index(SECRET))
        for row in self.read_tap_rows():
            self.assertIn(row["tap"], out)

    def test_apply_refuses_when_the_checks_fail(self):
        graph = FakeGraph(policy=good_policy(state="disabled"))
        code, out, _, _ = self.apply(graph=graph)
        self.assertEqual(code, 1)
        self.assertIn("REFUSING to issue", out)
        self.assertEqual(graph.calls_of("POST"), [])
        self.assertFalse(self.tap_csv.exists())

    def test_apply_refuses_an_environment_that_signs_in_with_passwords(self):
        code, out, _, _ = self.apply(cfg=make_cfg(sign_in="password"))
        self.assertEqual(code, 1)
        self.assertEqual(self.graph.calls_of("POST"), [])

    def test_apply_refuses_when_the_output_file_cannot_be_written(self):
        self.tap_csv.mkdir(parents=True)  # a directory where the file should go
        code, out, _, _ = self.apply()
        self.assertEqual(code, 1)
        self.assertIn("REFUSING to issue: cannot use .azure/mcaps/tap-issued.csv", out)
        self.assertEqual(self.graph.calls_of("POST"), [], "no pass may be created when its value cannot be saved")

    def test_rerun_skips_accounts_that_already_hold_an_unexpired_pass(self):
        self.assertEqual(self.apply()[0], 0)
        before = self.tap_csv.read_bytes()
        posts = len(self.graph.calls_of("POST", "temporaryAccessPassMethods"))
        code, out, _, _ = self.apply()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.graph.calls_of("POST", "temporaryAccessPassMethods")), posts, "no duplicates")
        self.assertEqual(self.graph.calls_of("DELETE"), [])
        self.assertEqual(out.count("skipped   "), 3)
        self.assertIn("its value is in the CSV", out)
        self.assertIn("created 0, replaced 0, skipped 3, failed 0", out)
        self.assertEqual(self.tap_csv.read_bytes(), before, "the CSV keeps the values of skipped accounts")
        self.assertEqual(sum(len(v) for v in self.graph.taps.values()), 3)

    def test_skipped_account_whose_value_is_not_on_file_says_so(self):
        self.graph.add_tap("hpb.lab01", NOW - timedelta(hours=1))
        code, out, _, _ = self.apply("--only", "1")
        self.assertEqual(code, 0)
        self.assertIn("its value is NOT in the CSV: use --replace", out)
        self.assertEqual(self.graph.calls_of("POST", "temporaryAccessPassMethods"), [])

    def test_replace_deletes_the_old_pass_then_creates_a_new_one_for_that_account_only(self):
        self.assertEqual(self.apply()[0], 0)
        old = {r["upn"]: r for r in self.read_tap_rows()}
        self.graph.calls.clear()
        code, out, _, _ = self.apply("--replace", "--only", "2")
        self.assertEqual(code, 0, out)
        uid = self.graph.uid("hpb.lab02")
        kinds = [(c[0], c[1].rsplit("/", 1)[-1]) for c in self.graph.calls if c[0] in ("DELETE", "POST")]
        self.assertEqual(kinds, [("DELETE", old["hpb.lab02@example.test"]["tap_id"]),
                                 ("POST", "temporaryAccessPassMethods")])
        self.assertTrue(all(uid in c[1] for c in self.graph.calls if c[0] in ("DELETE", "POST")))
        self.assertIn("replaced", out)
        new = {r["upn"]: r for r in self.read_tap_rows()}
        self.assertNotEqual(new["hpb.lab02@example.test"]["tap"], old["hpb.lab02@example.test"]["tap"])
        for other in ("hpb.lab01@example.test", "hpb.lab03@example.test"):
            self.assertEqual(new[other], old[other])
        self.assertEqual(len(self.graph.taps[uid]), 1)

    def test_an_expired_or_used_pass_does_not_block_a_new_one(self):
        self.graph.add_tap("hpb.lab01", NOW - timedelta(days=30), minutes=60)
        self.graph.add_tap("hpb.lab02", NOW - timedelta(minutes=5), minutes=480, reason="OneTimeUsed", one_time=True)
        code, out, _, _ = self.apply("--only", "1,2")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.graph.calls_of("POST", "temporaryAccessPassMethods")), 2)
        self.assertEqual(self.graph.calls_of("DELETE"), [])

    def test_a_pass_that_is_not_valid_yet_counts_as_unexpired(self):
        self.graph.add_tap("hpb.lab01", NOW + timedelta(hours=12), reason="NotYetValid")
        code, out, _, _ = self.apply("--only", "1")
        self.assertEqual(code, 0)
        self.assertIn("skipped   hpb.lab01@example.test", out)
        self.assertEqual(self.graph.calls_of("POST", "temporaryAccessPassMethods"), [])

    def test_a_one_time_pass_that_graph_no_longer_calls_usable_is_treated_as_used(self):
        self.graph.add_tap("hpb.lab01", NOW - timedelta(hours=1), minutes=480, reason="", one_time=True)
        info = issue_tap.tap_info(self.graph.taps[self.graph.uid("hpb.lab01")][0], NOW)
        self.assertEqual(info["state"], "used")
        code, out, _, _ = self.apply("--only", "1")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.graph.calls_of("POST", "temporaryAccessPassMethods")), 1)

    def test_start_time_is_sent_in_utc_and_reported(self):
        code, out, _, _ = self.apply("--start", "2026-11-03T08:00:00+08:00", "--lifetime-minutes", "240", "--only", "1")
        self.assertEqual(code, 0, out)
        body = self.graph.calls_of("POST", "temporaryAccessPassMethods")[0][2]
        self.assertEqual(body, {"lifetimeInMinutes": 240, "isUsableOnce": False, "startDateTime": "2026-11-03T00:00:00Z"})
        self.assertIn("from 2026-11-03T00:00:00Z until 2026-11-03T04:00:00Z", out)
        row = self.read_tap_rows()[0]
        self.assertEqual((row["start_utc"], row["expires_utc"]), ("2026-11-03T00:00:00Z", "2026-11-03T04:00:00Z"))

    def test_one_time_use_comes_from_the_config(self):
        graph = FakeGraph(policy=good_policy(isUsableOnce=False))
        code, out, _, _ = self.apply("--only", "1", graph=graph, cfg=make_cfg(one_time=True))
        self.assertEqual(code, 0)
        self.assertTrue(graph.calls_of("POST", "temporaryAccessPassMethods")[0][2]["isUsableOnce"])
        self.assertEqual(self.read_tap_rows()[0]["one_time"], "true")

    def test_one_failing_account_does_not_stop_the_others(self):
        graph = FakeGraph()
        graph.fail.append(("POST", f"{graph.uid('hpb.lab02')}/authentication", api_error(400, "BadRequest", "no")))
        code, out, _, _ = self.apply(graph=graph)
        self.assertEqual(code, 1)
        self.assertIn("FAILED    hpb.lab02@example.test  HTTP 400 BadRequest: no", out)
        self.assertIn("issue --check", out)
        self.assertEqual([r["upn"] for r in self.read_tap_rows()], ["hpb.lab01@example.test", "hpb.lab03@example.test"])
        self.assertIn("created 2, replaced 0, skipped 0, failed 1", out)

    def test_an_authorization_failure_prints_the_fix_text_once(self):
        graph = FakeGraph()
        graph.fail.append(("POST", "temporaryAccessPassMethods", api_error(403, "Authorization_RequestDenied")))
        code, out, _, _ = self.apply(graph=graph)
        self.assertEqual(code, 1)
        text = flat(out)
        self.assertEqual(text.count("a plain az CLI token may not carry that scope"), 1)
        self.assertEqual(out.count("FAILED"), 3)
        self.assertIn("Authentication Policy Administrator", text)
        self.assertNotIn(SECRET, out)

    def test_a_response_without_a_value_is_reported_not_silently_accepted(self):
        graph = FakeGraph()
        real_post = graph.post

        def post_without_value(path, body=None):
            resp = real_post(path, body)
            resp.pop("temporaryAccessPass", None)
            return resp

        graph.post = post_without_value
        code, out, _, _ = self.apply("--only", "1", graph=graph)
        self.assertEqual(code, 1)
        self.assertIn("returned no value", out)
        self.assertIn("--replace --only 1", out)

    @unittest.skipIf(os.name == "nt", "POSIX permission bits")
    def test_the_csv_is_owner_only(self):
        self.assertEqual(self.apply()[0], 0)
        self.assertEqual(self.tap_csv.stat().st_mode & 0o077, 0)

    def test_the_csv_is_the_only_file_that_holds_a_value(self):
        self.assertEqual(self.apply()[0], 0)
        holders = [p for p in self.scratch.rglob("*") if p.is_file() and SECRET in p.read_text(errors="replace")]
        self.assertEqual(holders, [self.tap_csv])

    def test_when_the_csv_cannot_be_updated_the_values_are_kept_in_the_tmp_file_and_the_run_fails(self):
        real_replace, calls = os.replace, []

        def flaky(src, dst):
            calls.append(src)
            if len(calls) > 1:  # the first call is the write-test before any pass is created
                raise PermissionError("the file is open in another program")
            return real_replace(src, dst)

        with mock.patch.object(issue_tap.os, "replace", flaky):
            code, out, err, _ = self.apply()
        self.assertEqual(code, 1)
        self.assertIn("KEEP THAT FILE", out)
        self.assertNotIn(SECRET, out + err)
        tmp = self.tap_csv.with_name("tap-issued.csv.tmp")
        self.assertEqual(tmp.read_text(encoding="utf-8").count(SECRET), 3, "all three values survive")


class RevokeTests(TapTestCase):
    def issue_all(self):
        self.assertEqual(self.tap("issue", "--apply")[0], 0)
        self.graph.calls.clear()

    def test_revoke_deletes_every_pass_revokes_sessions_and_drops_the_csv_rows(self):
        self.issue_all()
        code, out, _, _ = self.tap("revoke", "--apply")
        self.assertEqual(code, 0, out)
        for nick in ("hpb.lab01", "hpb.lab02", "hpb.lab03"):
            uid = self.graph.uid(nick)
            self.assertEqual(self.graph.taps[uid], [])
            self.assertIn(uid, self.graph.sessions_revoked)
        order = [(c[0], "revokeSignInSessions" in c[1]) for c in self.graph.calls if c[0] in ("DELETE", "POST")]
        self.assertEqual(order, [("DELETE", False), ("POST", True)] * 3)
        self.assertIn("revoked 3 account(s) (3 pass(es) deleted), failed 0, absent 0", out)
        self.assertIn("does NOT disable the accounts", out)
        self.assertIn("create-lab-users.sh mcaps --disable", out)
        self.assertFalse(self.tap_csv.exists(), "no revoked value may linger in the file")

    def test_revoke_continues_past_a_failure_and_exits_nonzero(self):
        self.issue_all()
        uid1, uid2, uid3 = (self.graph.uid(f"hpb.lab0{i}") for i in (1, 2, 3))
        self.graph.fail.append(("DELETE", f"{uid2}/authentication", api_error(403, "Authorization_RequestDenied")))
        code, out, _, _ = self.tap("revoke", "--apply")
        self.assertEqual(code, 1)
        self.assertIn("FAILED    hpb.lab02@example.test  HTTP 403", out)
        self.assertEqual(sorted(self.graph.sessions_revoked), sorted([uid1, uid3]))
        self.assertIn("revoked 2 account(s) (2 pass(es) deleted), failed 1, absent 0", out)
        self.assertEqual(len(self.graph.taps[uid2]), 1, "the pass that could not be deleted is still alive")
        self.assertEqual([r["upn"] for r in self.read_tap_rows()], ["hpb.lab02@example.test"],
                         "its value stays on file because it still works")

    def test_revoke_failing_only_at_the_session_step_still_drops_the_dead_values(self):
        self.issue_all()
        uid2 = self.graph.uid("hpb.lab02")
        self.graph.fail.append(("POST", f"{uid2}/revokeSignInSessions", api_error(403, "Authorization_RequestDenied")))
        code, out, _, _ = self.tap("revoke", "--apply")
        self.assertEqual(code, 1)
        self.assertIn("FAILED    hpb.lab02@example.test  HTTP 403", out)
        self.assertIn("revoked 2 account(s) (3 pass(es) deleted), failed 1, absent 0", out)
        self.assertNotIn(uid2, self.graph.sessions_revoked)
        self.assertFalse(self.tap_csv.exists(), "all three passes are deleted, so no value may stay on file")
        self.assertIn("revokeSignInSessions", flat(out))

    def test_revoke_deletes_expired_passes_too_and_reports_absent_accounts(self):
        graph = FakeGraph(count=3)
        del graph.users["hpb.lab03@example.test"]
        graph.add_tap("hpb.lab01", NOW - timedelta(days=30), minutes=60)
        code, out, _, _ = self.tap("revoke", "--apply", graph=graph)
        self.assertEqual(code, 0)
        self.assertEqual(graph.taps[graph.uid("hpb.lab01")], [])
        self.assertIn("absent    hpb.lab03@example.test", out)
        self.assertIn("absent 1", out)

    def test_revoke_never_touches_anything_without_apply(self):
        self.issue_all()
        code, _, _, built = self.tap("revoke")
        self.assertEqual((code, built, self.graph.calls), (0, 0, []))


class StatusTests(TapTestCase):
    def test_status_lists_each_account_and_never_prints_a_value(self):
        self.assertEqual(self.tap("issue", "--apply", "--only", "1")[0], 0)
        self.graph.add_tap("hpb.lab02", NOW - timedelta(days=30), minutes=60)
        self.graph.calls.clear()
        code, out, err, _ = self.tap("status")
        self.assertEqual(code, 0, out)
        self.assertEqual({c[0] for c in self.graph.calls}, {"GET"})
        self.assertNotIn(SECRET, out + err)
        self.assertRegex(out, r"active\s+hpb\.lab01@example\.test\s+until 2026-11-02T20:00:00Z .*value in CSV")
        self.assertRegex(out, r"none\s+hpb\.lab02@example\.test\s+\(last pass: expired\)")
        self.assertRegex(out, r"none\s+hpb\.lab03@example\.test")
        self.assertIn("1 active, 0 not yet valid, 2 without an unexpired pass, 0 problem(s)", out)

    def test_status_says_when_graph_reports_an_unexpired_pass_as_not_usable(self):
        self.graph.add_tap("hpb.lab01", NOW - timedelta(hours=1), reason="DisabledByPolicy")
        self.graph.add_tap("hpb.lab02", NOW + timedelta(hours=12), reason="NotYetValid")
        code, out, _, _ = self.tap("status", "--only", "1,2")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"active\s+hpb\.lab01@example\.test .*Graph: not usable now \(DisabledByPolicy\)")
        self.assertRegex(out, r"pending\s+hpb\.lab02@example\.test\s+from 2026-11-03T00:00:00Z until")
        self.assertIn("1 active, 1 not yet valid, 0 without an unexpired pass", out)

    def test_status_flags_missing_accounts_and_a_403(self):
        graph = FakeGraph(count=2)
        del graph.users["hpb.lab02@example.test"]
        code, out, _, _ = self.tap("status", "--count", "2", graph=graph)
        self.assertEqual(code, 1)
        self.assertIn("MISSING   hpb.lab02@example.test", out)
        graph = FakeGraph()
        graph.fail.append(("GET", "temporaryAccessPassMethods", api_error(403, "Authorization_RequestDenied")))
        code, out, _, _ = self.tap("status", graph=graph)
        self.assertEqual(code, 1)
        self.assertIn("Authentication Administrator", flat(out))
        self.assertEqual(len(graph.calls_of("GET", "temporaryAccessPassMethods")), 1)


class LabUsersTests(Scratch):
    def users(self, *argv: str, cfg: dict | None = None, graph: FakeGraph | None = None):
        graph = graph if graph is not None else FakeGraph(users=False)
        built = []
        out, err = io.StringIO(), io.StringIO()

        def factory():
            built.append(1)
            return graph

        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lab_users.main(list(argv), cfg=cfg or make_cfg(count=2), graph_factory=factory, root=self.scratch,
                                  environ={"AZURE_ENV_NAME": "mcaps"})
        return code, out.getvalue(), err.getvalue(), graph, len(built)

    @property
    def accounts_csv(self) -> Path:
        return self.scratch / ".azure" / "mcaps" / "lab-accounts.csv"

    def created_bodies(self, graph: FakeGraph) -> list[dict]:
        return [c[2] for c in graph.calls_of("POST") if c[1] == "/v1.0/users"]

    def test_tap_mode_creates_accounts_with_a_random_password_that_is_never_shown_or_saved(self):
        code, out, err, graph, _ = self.users()
        self.assertEqual(code, 0, err)
        bodies = self.created_bodies(graph)
        self.assertEqual([b["userPrincipalName"] for b in bodies], ["hpb.lab01@example.test", "hpb.lab02@example.test"])
        passwords = set()
        for body in bodies:
            profile = body["passwordProfile"]
            self.assertIs(profile["forceChangePasswordNextSignIn"], False)
            self.assertGreaterEqual(len(profile["password"]), 40)
            passwords.add(profile["password"])
        self.assertEqual(len(passwords), 2, "every account gets its own random password")
        text = self.accounts_csv.read_text(encoding="utf-8")
        self.assertEqual(text.splitlines()[0], "upn,display_name")
        self.assertNotIn("password", text.lower())
        everything = out + err + text
        for pwd in passwords:
            self.assertNotIn(pwd, everything)
        self.assertEqual([r["upn"] for r in read_csv(self.accounts_csv)],
                         ["hpb.lab01@example.test", "hpb.lab02@example.test"])
        self.assertIn("sign-in mode: tap", out)
        self.assertIn("issue-tap.sh mcaps issue --check", out)
        self.assertNotIn("Authenticator", out)

    def test_tap_mode_drops_the_password_column_of_an_older_file(self):
        self.accounts_csv.parent.mkdir(parents=True)
        self.accounts_csv.write_text("upn,display_name,temporary_password\n"
                                     "hpb.lab01@example.test,LiveWell Lab 01,Old-Password-Value-1\n"
                                     "hpb.breakglass@example.test,LiveWell Break Glass,Old-Password-Value-2\n",
                                     encoding="utf-8")
        graph = FakeGraph(count=1)
        code, out, _, _, _ = self.users(graph=graph)
        self.assertEqual(code, 0)
        text = self.accounts_csv.read_text(encoding="utf-8")
        self.assertNotIn("Old-Password-Value", text)
        self.assertNotIn("temporary_password", text)
        self.assertNotIn("breakglass", text, "an old break-glass row must not become a sign-in card")
        self.assertIn("dropped the temporary_password column", out)

    def test_tap_mode_lists_existing_accounts_but_never_the_break_glass_account(self):
        graph = FakeGraph(count=2)  # the accounts exist, but this machine has no lab-accounts.csv yet
        graph.add_user("hpb.breakglass")
        code, out, _, _, _ = self.users("--break-glass", graph=graph)
        self.assertEqual(code, 0)
        self.assertEqual([r["upn"] for r in read_csv(self.accounts_csv)],
                         ["hpb.lab01@example.test", "hpb.lab02@example.test"])
        self.assertEqual([r["display_name"] for r in read_csv(self.accounts_csv)],
                         ["LiveWell Lab 01", "LiveWell Lab 02"])
        self.assertNotIn("breakglass", self.accounts_csv.read_text(encoding="utf-8"))

    def test_reset_passwords_in_tap_mode_points_to_issue_tap_and_touches_nothing(self):
        code, out, err, graph, built = self.users("--reset-passwords")
        self.assertEqual((code, built, graph.calls), (2, 0, []))
        self.assertIn("issue_tap.py", err)
        self.assertIn("issue-tap.sh mcaps issue --replace", err)
        self.assertFalse(self.accounts_csv.exists())

    def test_password_mode_keeps_temporary_passwords_and_forced_change(self):
        code, out, err, graph, _ = self.users(cfg=make_cfg(sign_in="password", count=2))
        self.assertEqual(code, 0, err)
        for body in self.created_bodies(graph):
            self.assertIs(body["passwordProfile"]["forceChangePasswordNextSignIn"], True)
        rows = read_csv(self.accounts_csv)
        self.assertEqual(list(rows[0]), ["upn", "display_name", "temporary_password"])
        for row in rows:
            self.assertTrue(row["temporary_password"].startswith("Lw-"))
            self.assertNotIn(row["temporary_password"], out)
        self.assertIn("Temporary passwords: .azure/mcaps/lab-accounts.csv (gitignored).", out)
        self.assertIn("created 2, existing 0, passwords reset 0, deleted 0.", out)
        self.assertIn("Authenticator", out)
        self.assertNotIn("sign-in mode", out)

    def test_password_mode_reset_passwords_still_works(self):
        graph = FakeGraph(count=1)
        code, out, _, _, _ = self.users("--reset-passwords", cfg=make_cfg(sign_in="password", count=1), graph=graph)
        self.assertEqual(code, 0)
        patch = graph.calls_of("PATCH")[0][2]
        self.assertIs(patch["passwordProfile"]["forceChangePasswordNextSignIn"], True)
        self.assertIn("(password reset)", out)

    def test_break_glass_is_off_by_default_and_opt_in(self):
        code, out, _, graph, _ = self.users()
        self.assertEqual(code, 0)
        self.assertFalse(any("breakglass" in u for u in graph.users))
        self.assertEqual(graph.role_assignments, [])
        self.assertNotIn("STANDING GLOBAL ADMINISTRATOR", out)

        code, out, _, graph, _ = self.users("--break-glass")
        self.assertEqual(code, 0)
        self.assertIn("hpb.breakglass@example.test", graph.users)
        bg = graph.users["hpb.breakglass@example.test"]
        self.assertEqual(graph.role_assignments, [{"principalId": bg["id"], "roleDefinitionId": "role-ga",
                                                   "directoryScopeId": "/"}])
        self.assertIn("BREAK-GLASS ACCOUNT hpb.breakglass@example.test IS A STANDING GLOBAL ADMINISTRATOR", out)
        self.assertIn("create-lab-users.sh mcaps --delete", out)
        self.assertIn("Its random password was not saved anywhere", out)
        self.assertNotIn("password", self.accounts_csv.read_text(encoding="utf-8").lower())
        self.assertFalse(any(" " in c[1] for c in graph.calls), "URLs must not contain spaces (the role lookup)")

    def test_break_glass_in_password_mode_keeps_its_password_in_the_csv_and_says_so(self):
        code, out, _, graph, _ = self.users("--break-glass", cfg=make_cfg(sign_in="password"))
        self.assertEqual(code, 0)
        body = [b for b in self.created_bodies(graph) if "breakglass" in b["userPrincipalName"]][0]
        self.assertIs(body["passwordProfile"]["forceChangePasswordNextSignIn"], False)
        self.assertIn("keep it offline", out)

    def test_an_existing_break_glass_account_gets_a_reminder_not_a_second_one(self):
        graph = FakeGraph(count=2)
        bg = graph.add_user("hpb.breakglass")
        graph.role_assignments.append({"principalId": bg["id"], "roleDefinitionId": "role-ga", "directoryScopeId": "/"})
        code, out, _, _, _ = self.users("--break-glass", graph=graph)
        self.assertEqual(code, 0)
        self.assertEqual(len(graph.role_assignments), 1)
        self.assertIn("already exists and is a standing Global Administrator", out)

    def test_no_break_glass_is_accepted_as_a_noop_with_a_note(self):
        code, out, _, graph, _ = self.users("--no-break-glass")
        self.assertEqual(code, 0)
        self.assertIn("note: --no-break-glass is ignored", out)
        self.assertFalse(any("breakglass" in u for u in graph.users))

    def test_break_glass_does_not_combine_with_delete_or_disable_or_no_break_glass(self):
        for argv in (("--break-glass", "--delete"), ("--break-glass", "--disable"),
                     ("--break-glass", "--no-break-glass")):
            code, _, err, graph, built = self.users(*argv)
            self.assertEqual((code, built), (2, 0), argv)
            self.assertTrue(err.strip())

    def test_disable_sets_account_enabled_false_and_deletes_nothing(self):
        graph = FakeGraph(count=2)
        graph.add_user("hpb.breakglass")
        code, out, _, _, _ = self.users("--disable", graph=graph)
        self.assertEqual(code, 0)
        self.assertEqual([c[2] for c in graph.calls_of("PATCH")], [{"accountEnabled": False}] * 2)
        self.assertEqual(graph.calls_of("DELETE"), [])
        self.assertEqual(graph.calls_of("POST"), [])
        self.assertIn("disabled  hpb.lab01@example.test", out)
        self.assertIn("disabled 2.", out)
        self.assertIn("hpb.breakglass@example.test (break-glass, a standing Global Administrator) is still ENABLED", out)
        self.assertTrue(graph.users["hpb.breakglass@example.test"]["accountEnabled"])
        self.assertFalse(self.accounts_csv.exists())
        self.assertIn("issue-tap.sh mcaps revoke --apply", out)

    def test_disable_skips_accounts_that_are_already_disabled_or_absent(self):
        graph = FakeGraph(count=2)
        graph.users["hpb.lab01@example.test"]["accountEnabled"] = False
        del graph.users["hpb.lab02@example.test"]
        code, out, _, _, _ = self.users("--disable", graph=graph)
        self.assertEqual(code, 0)
        self.assertEqual(graph.calls_of("PATCH"), [])
        self.assertIn("already disabled  hpb.lab01@example.test", out)
        self.assertIn("absent   hpb.lab02@example.test", out)

    def test_delete_also_removes_the_break_glass_account_and_says_which(self):
        graph = FakeGraph(count=2)
        graph.add_user("hpb.breakglass")
        code, out, _, _, _ = self.users("--delete", graph=graph)
        self.assertEqual(code, 0)
        self.assertEqual(len(graph.calls_of("DELETE")), 3)
        self.assertEqual(graph.users, {})
        self.assertIn("deleted  hpb.breakglass@example.test  (break-glass account)", out)
        self.assertIn("deleted  hpb.lab01@example.test", out)
        self.assertIn("deleted 3", out)

    def test_delete_reports_an_absent_break_glass_account(self):
        graph = FakeGraph(count=2)
        code, out, _, _, _ = self.users("--delete", "--dry-run", graph=graph)
        self.assertEqual(code, 0)
        self.assertEqual(graph.calls_of("DELETE"), [])
        self.assertIn("would delete  hpb.lab01@example.test", out)
        self.assertIn("absent  hpb.breakglass@example.test  (break-glass account)", out)

    def test_dry_run_changes_nothing_and_the_count_comes_from_the_config(self):
        code, out, _, graph, _ = self.users("--dry-run", "--break-glass", cfg=make_cfg(count=30))
        self.assertEqual(code, 0)
        self.assertEqual(out.count("would create"), 31)
        self.assertIn("would create hpb.breakglass@example.test  (break-glass: a STANDING Global Administrator)", out)
        self.assertEqual([c[0] for c in graph.calls if c[0] != "GET"], [])
        self.assertFalse(self.accounts_csv.exists())

    def test_count_option_overrides_the_config(self):
        code, out, _, graph, _ = self.users("--count", "1", "--dry-run")
        self.assertEqual(out.count("would create"), 1)

    def test_an_unknown_sign_in_mode_is_rejected(self):
        code, _, err, _, built = self.users(cfg=make_cfg(sign_in="magic"))
        self.assertEqual((code, built), (2, 0))
        self.assertIn("'tap' or 'password'", err)


def load_cards_module():
    """scripts/tenant/sign-in-cards.py, with a minimal fpdf stand-in when fpdf2 is not installed."""
    stub = importlib.util.find_spec("fpdf") is None
    if stub:
        class StubFPDF:
            w, h = 210.0, 297.0
            l_margin = r_margin = 18.0

            def __init__(self, *a, **k):
                self.y = 0.0
                self.pages = 0

            def set_margins(self, left, top, right):
                self.l_margin, self.r_margin = left, right

            def add_page(self):
                self.pages += 1
                self.y = 16.0

            def get_y(self):
                return self.y

            def set_y(self, y):
                self.y = y

            def ln(self, h=0):
                self.y += h

            def get_string_width(self, text):
                return 0.0

            def output(self, path):
                Path(path).write_bytes(b"%PDF-stub")

        def noop(self, *a, **k):
            return None

        for name in ("set_auto_page_break", "set_fill_color", "set_text_color", "set_draw_color", "set_font", "set_x",
                     "set_xy", "rect", "cell", "multi_cell"):
            setattr(StubFPDF, name, noop)  # real methods exist on fpdf2's FPDF; super().cell(...) needs them here too

        fpdf = types.ModuleType("fpdf")
        enums = types.ModuleType("fpdf.enums")
        enums.XPos = types.SimpleNamespace(LMARGIN="LMARGIN")
        enums.YPos = types.SimpleNamespace(NEXT="NEXT")
        fpdf.FPDF, fpdf.enums = StubFPDF, enums
        sys.modules.update({"fpdf": fpdf, "fpdf.enums": enums})
    try:
        spec = importlib.util.spec_from_file_location("sign_in_cards_under_test",
                                                      ROOT / "scripts" / "tenant" / "sign-in-cards.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if stub:
            sys.modules.pop("fpdf", None)
            sys.modules.pop("fpdf.enums", None)
    module.using_stub = stub
    return module


class CardsTests(Scratch):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_cards_module()

        class Recorder(cls.mod.Cards):
            """Records every text the card writes, then lets the real (or stub) FPDF do its work."""
            instances: list = []

            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                self.texts: list[str] = []
                Recorder.instances.append(self)

            def cell(self, *args, **kw):
                self.texts.append(self._text(args, kw))
                return super().cell(*args, **kw)

            def multi_cell(self, *args, **kw):
                self.texts.append(self._text(args, kw))
                return super().multi_cell(*args, **kw)

            @staticmethod
            def _text(args, kw):
                return str(kw.get("text", kw.get("txt", args[2] if len(args) > 2 else "")))

        cls.Recorder = Recorder

    def setUp(self) -> None:
        super().setUp()
        self.Recorder.instances.clear()
        self.cfg = make_cfg()

    def card_text(self, mode: str, secret: str = "", valid_until: str = "") -> str:
        pdf = self.Recorder(self.cfg, mode)
        pdf.card("LiveWell Lab 01", "hpb.lab01@example.test", secret, valid_until)
        return "\n".join(pdf.texts)

    def run_cards(self, *argv: str, cfg: dict | None = None):
        out = io.StringIO()
        with mock.patch.object(self.mod, "ROOT", self.scratch), \
                mock.patch.object(self.mod, "Cards", self.Recorder), \
                mock.patch.object(self.mod.wsconfig, "load", return_value=cfg or self.cfg), \
                contextlib.redirect_stdout(out):
            code = self.mod.main(["mcaps", *argv, "--out", str(self.scratch / "cards.pdf")])
        return code, out.getvalue()

    def write_accounts(self, with_password: bool = False) -> None:
        path = self.scratch / ".azure" / "mcaps" / "lab-accounts.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["upn,display_name" + (",temporary_password" if with_password else "")]
        for i in (1, 2):
            lines.append(f"hpb.lab0{i}@example.test,LiveWell Lab 0{i}" + (f",Pw-Value-{i}" if with_password else ""))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def write_tap_file(self, rows: dict[str, tuple[str, str]]) -> None:
        """rows: nick -> (pass value, expires_utc)."""
        data = {f"hpb.{nick}@example.test": {"upn": f"hpb.{nick}@example.test", "tap_id": f"tap-{i:04d}", "tap": tap,
                                              "start_utc": "2026-11-02T02:00:00Z", "expires_utc": expires,
                                              "one_time": "false"}
                for i, (nick, (tap, expires)) in enumerate(rows.items(), 1)}
        issue_tap.write_tap_file(issue_tap.tap_file_path("mcaps", self.scratch), data)

    # ---- the card itself
    def test_tap_card_has_the_upn_the_sign_in_sites_and_the_instruction(self):
        text = self.card_text("tap")
        self.assertIn("hpb.lab01@example.test", text)
        self.assertIn("Temporary Access Pass", text)
        self.assertIn("portal.azure.com", text)
        self.assertIn("https://ai.azure.com", text)
        self.assertIn("Fabric", text)
        self.assertIn("az login --use-device-code", text)
        self.assertIn(self.mod.TAP_INSTRUCTION, text)
        self.assertIn("Enter your Temporary Access Pass when asked for a password", self.mod.TAP_INSTRUCTION)
        self.assertIn("Do not register Authenticator", self.mod.TAP_INSTRUCTION)
        self.assertIn("stop and ask the facilitator", self.mod.TAP_INSTRUCTION)
        self.assertIn("do not photograph this card", text)
        self.assertEqual(self.mod.TAP_FOOTER, text.splitlines()[-1])

    def test_tap_card_has_no_password_or_authenticator_text_beyond_the_required_instruction(self):
        text = self.card_text("tap", "Some-Pass-Value", "Mon 2 Nov 2026, 18:00 SGT")
        rest = text.replace(self.mod.TAP_INSTRUCTION, "")
        for word in ("password", "authenticator", "scan qr", "choose a new"):
            self.assertNotIn(word, rest.lower())

    def test_tap_card_leaves_blank_lines_when_the_pass_and_time_are_not_known(self):
        text = self.card_text("tap")
        self.assertEqual(text.count(self.mod.BLANK), 2)
        text = self.card_text("tap", "Some-Pass-Value", "Mon 2 Nov 2026, 18:00 SGT")
        self.assertEqual(text.count(self.mod.BLANK), 0)
        self.assertIn("Some-Pass-Value", text)
        self.assertIn("Mon 2 Nov 2026, 18:00 SGT", text)

    def test_password_cards_are_unchanged(self):
        text = self.card_text("password", "Lw-Example-Value!42")
        for expected in ("Temporary password", "Lw-Example-Value!42", "The temporary password works once",
                         "Before the workshop (about 5 minutes)", "install Microsoft Authenticator",
                         "Choose a new password", "sign in with the username and temporary password above",
                         "Keep this card to yourself."):
            self.assertIn(expected, text)
        self.assertNotIn("Temporary Access Pass", text)
        self.assertNotIn(self.mod.BLANK, text)

    def test_cards_fit_one_page_when_fpdf2_is_installed(self):
        if self.mod.using_stub:
            self.skipTest("fpdf2 is not installed here: the card layout was only simulated, not rendered")
        cfg = make_cfg()
        cfg["workshop"]["guest_wifi"] = {"ssid": "HPB-Guest", "code": "12345678"}  # the longest card
        for mode, secret, until in (("tap", "", ""), ("tap", "A" * 48, "Mon 2 Nov 2026, 18:00 SGT"),
                                    ("password", "Lw-Example-Value!42", "")):
            pdf = self.Recorder(cfg, mode)
            pdf.card("LiveWell Lab 01", "hpb.lab01@LongTenantNameForLayout.example.test", secret, until)
            self.assertEqual(pdf.page, 1, (mode, secret))

    # ---- the command
    def test_default_leaves_the_pass_blank_but_shows_the_valid_until_time_from_the_file(self):
        self.write_accounts()
        self.write_tap_file({"lab01": (f"{SECRET}0001", "2026-11-02T10:00:00Z"),
                             "lab02": (f"{SECRET}0002", "2026-11-02T10:00:00Z")})
        code, out = self.run_cards("--lab-accounts")
        self.assertEqual(code, 0)
        texts = "\n".join(t for pdf in self.Recorder.instances for t in pdf.texts)
        self.assertNotIn(SECRET, texts)
        self.assertNotIn(SECRET, out)
        self.assertIn("2 Nov 2026, 18:00 SGT", texts)
        self.assertEqual(texts.count(self.mod.BLANK), 2, "one blank pass line per card")
        self.assertIn("hpb.lab01@example.test", texts)
        self.assertIn("hpb.lab02@example.test", texts)
        self.assertIn("blank: write each pass on its card by hand", out)
        self.assertTrue((self.scratch / "cards.pdf").exists())

    def test_default_works_before_any_pass_is_issued(self):
        self.write_accounts()
        code, out = self.run_cards("--lab-accounts")
        self.assertEqual(code, 0)
        texts = "\n".join(t for pdf in self.Recorder.instances for t in pdf.texts)
        self.assertEqual(texts.count(self.mod.BLANK), 4, "pass and valid-until are blank on both cards")

    def test_with_tap_prints_the_pass_values_but_never_to_the_console(self):
        self.write_accounts()
        self.write_tap_file({"lab01": (f"{SECRET}0001", "2026-11-02T10:00:00Z"),
                             "lab02": (f"{SECRET}0002", "2026-11-02T10:00:00Z")})
        with mock.patch.object(self.mod, "datetime", wraps=datetime) as fake_dt:
            fake_dt.now.return_value = NOW - timedelta(days=1)
            code, out = self.run_cards("--lab-accounts", "--with-tap")
        self.assertEqual(code, 0, out)
        texts = "\n".join(t for pdf in self.Recorder.instances for t in pdf.texts)
        self.assertIn(f"{SECRET}0001", texts)
        self.assertIn(f"{SECRET}0002", texts)
        self.assertNotIn(SECRET, out)
        self.assertIn("secrets", out)

    def test_with_tap_stops_when_a_pass_is_missing_or_expired_and_writes_no_pdf(self):
        self.write_accounts()
        self.write_tap_file({"lab01": (f"{SECRET}0001", "2026-11-02T10:00:00Z")})  # lab02 has none
        with mock.patch.object(self.mod, "datetime", wraps=datetime) as fake_dt:
            fake_dt.now.return_value = NOW - timedelta(days=1)
            with self.assertRaises(SystemExit) as caught:
                self.run_cards("--lab-accounts", "--with-tap")
        message = str(caught.exception.code)
        self.assertIn("hpb.lab02@example.test: not in", message)
        self.assertIn("no PDF was written", message)
        self.assertNotIn(SECRET, message)
        self.assertFalse((self.scratch / "cards.pdf").exists())
        with mock.patch.object(self.mod, "datetime", wraps=datetime) as fake_dt:  # now: after the expiry
            fake_dt.now.return_value = NOW
            with self.assertRaises(SystemExit) as caught:
                self.run_cards("--lab-accounts", "--with-tap")
        self.assertIn("the pass expired at 2026-11-02T10:00:00Z", str(caught.exception.code))

    def test_password_mode_still_reads_passwords_from_the_csv(self):
        self.write_accounts(with_password=True)
        code, out = self.run_cards("--lab-accounts", cfg=make_cfg(sign_in="password"))
        self.assertEqual(code, 0)
        texts = "\n".join(t for pdf in self.Recorder.instances for t in pdf.texts)
        self.assertIn("Pw-Value-1", texts)
        self.assertIn("Temporary password", texts)
        self.assertNotIn("Pw-Value", out)
        self.assertIn("holds passwords", out)

    def test_mode_specific_options_are_rejected_in_the_wrong_mode(self):
        self.write_accounts(with_password=True)
        with self.assertRaises(SystemExit) as caught:
            self.run_cards("--lab-accounts", "--with-tap", cfg=make_cfg(sign_in="password"))
        self.assertIn("--with-tap is for sign_in: tap", str(caught.exception.code))
        with self.assertRaises(SystemExit) as caught:
            self.run_cards("--lab-accounts", "--password", "x")
        self.assertIn("--password is for sign_in: password", str(caught.exception.code))

    def test_a_tap_mode_account_list_cannot_be_used_for_password_cards(self):
        self.write_accounts(with_password=False)
        with self.assertRaises(SystemExit) as caught:
            self.run_cards("--lab-accounts", cfg=make_cfg(sign_in="password"))
        self.assertIn("has no temporary_password column", str(caught.exception.code))


class HelperTests(unittest.TestCase):
    def test_parse_utc_reads_graph_and_offset_formats(self):
        self.assertEqual(issue_tap.parse_utc("2026-11-02T12:00:00Z"), NOW)
        self.assertEqual(issue_tap.parse_utc("2026-11-02T12:00:00.1234567Z"), NOW.replace(microsecond=123456))
        self.assertEqual(issue_tap.parse_utc("2026-11-02T20:00:00+08:00"), NOW)
        self.assertEqual(issue_tap.parse_utc("2026-11-02T12:00:00"), NOW, "no offset: taken as UTC")
        self.assertIsNone(issue_tap.parse_utc("not a time"))
        self.assertIsNone(issue_tap.parse_utc(""))
        self.assertIsNone(issue_tap.parse_utc(None))

    def test_start_needs_an_offset(self):
        self.assertEqual(issue_tap.parse_start("2026-11-03T08:00:00+08:00"), datetime(2026, 11, 3, tzinfo=timezone.utc))
        self.assertEqual(issue_tap.parse_start("2026-11-03T00:00:00Z"), datetime(2026, 11, 3, tzinfo=timezone.utc))
        for bad in ("2026-11-03T08:00:00", "tomorrow", ""):
            with self.assertRaises(ValueError):
                issue_tap.parse_start(bad)

    def test_local_time_is_singapore_for_sg_and_utc_for_anything_else(self):
        self.assertEqual(issue_tap.fmt_local(NOW, "SG"), "Mon 2 Nov 2026, 20:00 SGT")
        self.assertEqual(issue_tap.fmt_local(NOW, "sg"), "Mon 2 Nov 2026, 20:00 SGT")
        self.assertEqual(issue_tap.fmt_local(NOW, "XX"), "Mon 2 Nov 2026, 12:00 UTC")

    def test_only_selects_account_numbers_within_the_count(self):
        self.assertEqual(issue_tap.parse_only(None, 3), [1, 2, 3])
        self.assertEqual(issue_tap.parse_only("3, 1,3,,2", 3), [1, 2, 3])
        for bad in ("0", "4", "x", "1-2", ","):
            with self.assertRaises(ValueError):
                issue_tap.parse_only(bad, 3)

    def test_tap_info_states(self):
        base = {"id": "tap-0001", "startDateTime": iso(NOW - timedelta(hours=1)), "lifetimeInMinutes": 480,
                "isUsableOnce": False, "isUsable": True, "methodUsabilityReason": "EnabledByPolicy"}
        self.assertEqual(issue_tap.tap_info(base, NOW)["state"], "active")
        self.assertEqual(issue_tap.tap_info(base, NOW + timedelta(hours=8))["state"], "expired")
        self.assertEqual(issue_tap.tap_info({**base, "startDateTime": iso(NOW + timedelta(hours=1))}, NOW)["state"],
                         "pending")
        self.assertEqual(issue_tap.tap_info({**base, "methodUsabilityReason": "OneTimeUsed"}, NOW)["state"], "used")
        info = issue_tap.tap_info({"id": "x"}, NOW)  # a listing with almost nothing in it must not crash
        self.assertEqual((info["state"], info["expires"]), ("active", None))

class TapFileTests(Scratch):
    ROW = {"upn": "A@x.test", "tap_id": "t1", "tap": "S1", "start_utc": "s", "expires_utc": "e", "one_time": "false"}

    def test_values_are_only_read_when_asked_for(self):
        path = issue_tap.tap_file_path("mcaps", self.scratch)
        issue_tap.write_tap_file(path, {"a@x.test": self.ROW})
        self.assertEqual(issue_tap.read_tap_file(path)["a@x.test"]["tap"], "S1")
        self.assertEqual(issue_tap.read_tap_file(path, include_secret=False)["a@x.test"]["tap"], "")
        self.assertEqual([p.name for p in path.parent.iterdir()], ["tap-issued.csv"], "no .tmp file is left behind")

    def test_a_failed_replace_keeps_the_complete_data_in_the_tmp_file(self):
        path = issue_tap.tap_file_path("mcaps", self.scratch)
        with mock.patch.object(issue_tap.os, "replace", side_effect=PermissionError("locked")):
            with self.assertRaises(PermissionError):
                issue_tap.write_tap_file(path, {"a@x.test": self.ROW})
        self.assertIn("S1", path.with_name(path.name + ".tmp").read_text(encoding="utf-8"))
        self.assertFalse(path.exists())

    def test_forgetting_rows_removes_the_file_when_nothing_is_left(self):
        path = issue_tap.tap_file_path("mcaps", self.scratch)
        other = {**self.ROW, "upn": "B@x.test", "tap": "S2"}
        issue_tap.write_tap_file(path, {"a@x.test": self.ROW, "b@x.test": other})
        self.assertEqual(issue_tap.forget_rows(path, ["A@X.test"]), 1)
        self.assertEqual(list(issue_tap.read_tap_file(path)), ["b@x.test"])
        self.assertEqual(issue_tap.forget_rows(path, ["b@x.test"]), 1)
        self.assertFalse(path.exists())
        self.assertEqual(issue_tap.forget_rows(path, ["b@x.test"]), 0)


class HygieneTests(unittest.TestCase):
    FILES = ("scripts/lib/issue_tap.py", "scripts/lib/lab_users.py", "scripts/tenant/issue-tap.sh",
             "scripts/tenant/create-lab-users.sh", "scripts/tenant/sign-in-cards.py", "tests/test_tap.py")

    def test_no_guid_shaped_strings(self):
        for rel in self.FILES:
            self.assertIsNone(GUID_RE.search((ROOT / rel).read_text(encoding="utf-8")), rel)

    def test_new_scripts_are_ascii_only(self):
        for rel in ("scripts/lib/issue_tap.py", "scripts/tenant/issue-tap.sh", "tests/test_tap.py"):
            (ROOT / rel).read_bytes().decode("ascii")

    def test_the_tap_policy_is_never_written(self):
        source = (ROOT / "scripts" / "lib" / "issue_tap.py").read_text(encoding="utf-8")
        self.assertNotIn("PATCH", source)
        self.assertNotIn(".patch(", source)
        self.assertNotIn(".put(", source)


if __name__ == "__main__":
    unittest.main()
