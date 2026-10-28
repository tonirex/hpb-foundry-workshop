#!/usr/bin/env python3
"""Temporary Access Passes (TAP) for the workshop lab accounts, via Microsoft Graph.

Called by scripts/tenant/issue-tap.sh, which runs the tenant guard first:

    issue-tap.sh [env] issue  [--check | --apply] [--lifetime-minutes M] [--start ISO-8601] [--replace] [--show-secrets]
    issue-tap.sh [env] revoke [--apply]
    issue-tap.sh [env] status

Common options: --env (default AZURE_ENV_NAME), --count N (default lab_accounts.count), --prefix (default
lab_accounts.prefix), --only N[,N...] (account numbers: re-issue or revoke just those). Accounts are <prefix>NN @ the
tenant's default domain (read from Graph /v1.0/organization, and only when a Graph call is allowed).

`issue` and `revoke` print their plan and contact nothing unless asked:
  issue            plan only, no network: how many passes, for how long, valid from when, and where the values go
  issue --check    read-only Graph GETs, never modifies anything: the token's delegated scopes (decoded locally), the
                   TAP policy (enabled, lifetime bounds, one-time use, who it targets) and that every account exists
  issue --apply    repeats the checks and refuses to run if one fails, then creates one TAP per account. An account that
                   already holds an unexpired TAP is skipped (so a re-run never creates a second pass for it, whose
                   earlier twin may already be on a printed card) unless --replace deletes the old one first.
  revoke --apply   deletes every TAP of each account and revokes its sign-in sessions. It does NOT disable the
                   account: use scripts/tenant/create-lab-users.sh --disable (or --delete) for that.
  status           read-only: per account, whether a TAP exists and when it expires (never its value)

Secrets: Graph returns a pass's value once, when it is created. Values are written only to .azure/<env>/tap-issued.csv
(gitignored; upn,tap_id,tap,start_utc,expires_utc,one_time; owner-only permissions where the OS supports them) and are
printed only with --show-secrets. They never go to logs or error messages: treat the CSV and printed cards like
passwords.

Who can run --apply: issuing a TAP needs the Authentication Administrator role (Privileged Authentication
Administrator for admin accounts) plus the delegated Graph permission UserAuthenticationMethod.ReadWrite.All; a plain
az CLI token may not carry that scope (--check reads the token's scopes and says so). The Temporary Access Pass policy
(Entra admin center > Authentication methods > Policies) must be enabled for the lab accounts; editing it needs the
Authentication Policy Administrator role. This script never edits the policy.

UNVERIFIED: that a browser sign-in, `az login` or `az login --use-device-code` accepts a TAP in this tenant or in
Codespaces, and how Conditional Access or security defaults treat it. TAP expiry neither disables the account nor ends
sessions already issued. Username+password style (ROPC) flows do not work with a TAP. Test one account first.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wsconfig  # noqa: E402
from azrest import Api, ApiError, jwt_claims  # noqa: E402
from lab_users import lab_settings  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TAP_SCOPE = "UserAuthenticationMethod.ReadWrite.All"
POLICY_PATH = "/v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/TemporaryAccessPass"
TAP_METHODS = "/v1.0/users/{uid}/authentication/temporaryAccessPassMethods"
TAP_FIELDS = ["upn", "tap_id", "tap", "start_utc", "expires_utc", "one_time"]
LIVE_STATES = ("active", "pending")  # an unexpired TAP: usable now, or valid from a later start time

FIX_ROLE = ("Issuing a Temporary Access Pass needs the Authentication Administrator role (Privileged Authentication "
            f"Administrator for admin accounts) plus the delegated Graph permission {TAP_SCOPE}; a plain az CLI "
            "token may not carry that scope.")
FIX_POLICY = ("Editing the Temporary Access Pass policy needs the Authentication Policy Administrator role; this "
              "script never edits it.")

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
LOCAL_ZONES = {"SG": ("SGT", timedelta(hours=8))}  # no daylight saving; any other usage location is shown in UTC


# ---------------------------------------------------------------------------------------------------- time helpers
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_utc(value) -> datetime | None:
    """An ISO-8601 time from Graph or the CSV -> aware UTC datetime; None when it is empty or unreadable."""
    if not value:
        return None
    text = re.sub(r"(\.\d{6})\d+", r"\1", str(value).strip()).replace("Z", "+00:00")  # Graph can send 7 digits
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def parse_start(text: str) -> datetime:
    try:
        dt = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"--start '{text}' is not an ISO-8601 time (example: 2026-11-03T08:00:00+08:00)") from None
    if dt.tzinfo is None:
        raise ValueError("--start needs a UTC offset or Z so the time is unambiguous "
                         "(example: 2026-11-03T08:00:00+08:00)")
    return dt.astimezone(timezone.utc).replace(microsecond=0)


def fmt_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fmt_local(dt: datetime, usage_location: str = "SG") -> str:
    """Wall-clock time where the workshop runs (from the usage location), e.g. 'Tue 3 Nov 2026, 16:00 SGT'."""
    label, offset = LOCAL_ZONES.get(str(usage_location).upper(), ("UTC", timedelta(0)))
    d = dt.astimezone(timezone(offset))
    return f"{WEEKDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]} {d.year}, {d:%H:%M} {label}"


# ------------------------------------------------------------------------------------------------- output helpers
class Report:
    """PASS / INFO / WARN / FAIL lines in the style of scripts/lib/common.sh."""

    def __init__(self) -> None:
        self.failures = 0
        self.warnings = 0

    @staticmethod
    def _emit(tag: str, msg: str, fix: tuple | list = ()) -> None:
        print(f"  {tag}  {msg}")
        for paragraph in fix:
            for line in textwrap.wrap(paragraph, 96):
                print(f"          {line}")

    def ok(self, msg: str) -> None:
        self._emit("PASS", msg)

    def info(self, msg: str) -> None:
        self._emit("INFO", msg)

    def warn(self, msg: str, fix: tuple | list = ()) -> None:
        self.warnings += 1
        self._emit("WARN", msg, fix)

    def bad(self, msg: str, fix: tuple | list = ()) -> None:
        self.failures += 1
        self._emit("FAIL", msg, fix)


def usage_error(message: str) -> int:
    print(f"[issue-tap] {message}", file=sys.stderr)
    return 2


def describe(e: ApiError) -> str:
    """HTTP status, Graph error code and message. Never the raw body or URL."""
    try:
        message = str((json.loads(e.body).get("error") or {}).get("message") or "")
    except (ValueError, AttributeError):
        message = ""
    message = " ".join(message.split())[:200].encode("ascii", "replace").decode("ascii")  # console output stays ASCII
    return f"HTTP {e.status} {e.code or 'error'}" + (f": {message}" if message else "")


def fix_for(e: ApiError, kind: str, tenant: str) -> list[str]:
    """Exact fix text for a Graph error. kind: policy | users | tap | revoke."""
    login = f"az login --tenant {tenant or '<tenant-id>'}"
    if e.status == 401:
        return [f"Graph rejected the sign-in token (HTTP 401): it has expired or belongs to another tenant. "
                f"Run: {login} and re-run."]
    if e.status == 403:
        if kind == "policy":
            return ["Graph denied reading the Temporary Access Pass policy. Ask someone who can read the "
                    "authentication methods policies (for example an Authentication Policy Administrator) to "
                    "confirm it is enabled for the lab accounts, allows the lifetime you need and does not force "
                    "one-time use.", FIX_POLICY]
        if kind == "users":
            return [f"Graph denied reading the users. Sign in as an administrator of this tenant: {login}."]
        if kind == "revoke":
            return ["Graph denied revokeSignInSessions: the signed-in account or token may not revoke sign-in "
                    "sessions of these users.", FIX_ROLE]
        return [FIX_ROLE,
                f"To get the scope, sign in again requesting it: {login} --scope "
                f"https://graph.microsoft.com/{TAP_SCOPE} (UNVERIFIED: the az CLI may not be allowed to request it "
                "in this tenant). Otherwise create the passes in the Entra admin center: Users > the user > "
                "Authentication methods > Add authentication method > Temporary Access Pass.",
                FIX_POLICY]
    if e.status == 400:
        return ["Graph rejected the request (HTTP 400). Compare --lifetime-minutes and the one-time setting with "
                "the Temporary Access Pass policy: run `issue --check`. The policy bounds the lifetime (minimum "
                "and maximum) and can force one-time use.", FIX_POLICY]
    if e.status == 404:
        if kind == "policy":
            return ["Graph could not find the Temporary Access Pass policy (HTTP 404): check that the token is for the "
                    f"right tenant ({login}) and look at Entra admin center > Authentication methods > Policies."]
        return ["Graph could not find the user or the pass (HTTP 404): run `status` and `issue --check`."]
    if e.status in (429, 500, 502, 503, 504):
        return [f"Graph throttled or failed the request even after retries (HTTP {e.status}). Wait a minute and "
                "re-run: accounts that already have a pass are skipped."]
    return []


def print_fixes(failures: list[tuple[ApiError, str]], tenant: str) -> None:
    """Fix text once per distinct (status, kind), however many accounts failed the same way."""
    seen: set[tuple[int, str]] = set()
    for e, kind in failures:
        if (e.status, kind) in seen:
            continue
        seen.add((e.status, kind))
        for paragraph in fix_for(e, kind, tenant):
            for line in textwrap.wrap(paragraph, 96):
                print(f"          {line}")


# -------------------------------------------------------------------------------------------------- the run settings
@dataclass
class Run:
    env: str
    prefix: str
    numbers: list[int]
    lifetime: int
    one_time: bool
    start: datetime | None
    usage_location: str
    sign_in: str
    tenant: str
    tap_path: Path
    replace: bool = False
    show_secrets: bool = False
    now: Callable[[], datetime] = utc_now

    @property
    def csv_name(self) -> str:
        return f".azure/{self.env}/tap-issued.csv"


@dataclass
class Account:
    number: int
    upn: str
    user_id: str = ""
    exists: bool = False
    enabled: bool = True
    taps: list[dict] | None = None  # None: not listed


@dataclass
class Checked:
    report: Report
    domain: str = ""
    accounts: list[Account] = field(default_factory=list)


def make_client():
    """The Graph client. Built only when a Graph call is allowed, so importing this module never calls Azure."""
    return Api("graph")


def tap_file_path(env: str, root: Path = ROOT) -> Path:
    return root / ".azure" / env / "tap-issued.csv"


def parse_only(text: str | None, count: int) -> list[int]:
    if not text:
        return list(range(1, count + 1))
    numbers: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit() or not 1 <= int(part) <= count:
            raise ValueError(f"--only takes account numbers between 1 and {count} (raise --count to go higher), "
                             f"got '{part}'")
        numbers.add(int(part))
    if not numbers:
        raise ValueError("--only is empty")
    return sorted(numbers)


def accounts_text(run: Run) -> str:
    nums, p = run.numbers, run.prefix
    if len(nums) > 2 and nums == list(range(nums[0], nums[-1] + 1)):
        names = f"{p}{nums[0]:02d} .. {p}{nums[-1]:02d}"
    else:
        names = ", ".join(f"{p}{n:02d}" for n in nums)
    return f"{len(nums)} account(s): {names} @ <tenant-domain>   (pattern <prefix>NN@<tenant-domain>)"


def preview(names: list[str], limit: int = 5) -> str:
    shown = ", ".join(names[:limit])
    return shown + (f" and {len(names) - limit} more" if len(names) > limit else "")


# ------------------------------------------------------------------------------------------ the TAP file (secrets)
def read_tap_file(path: Path, include_secret: bool = True) -> dict[str, dict]:
    """upn (lower case) -> row with every TAP_FIELDS key. include_secret=False blanks the pass value as it is read."""
    rows: dict[str, dict] = {}
    if not path.exists():
        return rows
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            upn = (r.get("upn") or "").strip()
            if not upn:
                continue
            row = {k: (r.get(k) or "").strip() for k in TAP_FIELDS}
            if not include_secret:
                row["tap"] = ""
            rows[upn.lower()] = row
    return rows


def write_tap_file(path: Path, rows: dict[str, dict]) -> None:
    """Whole file, atomically, created owner-only (0600) where the OS supports it. If the final replace fails (for
    example the file is open in another program) the complete data stays in <name>.tmp and OSError is raised."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.chmod(tmp, 0o600)  # a leftover .tmp may be older than this call; nothing is written to it yet
    except OSError:
        pass  # Windows: no POSIX permissions
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TAP_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: r["upn"].lower()))
    os.replace(tmp, path)


def forget_rows(path: Path, upns: list[str]) -> int:
    """Drop the rows of these accounts (their passes are revoked); the file goes when nothing is left."""
    rows = read_tap_file(path)
    dropped = [u for u in (x.lower() for x in upns) if rows.pop(u, None) is not None]
    if dropped:
        if rows:
            write_tap_file(path, rows)
        else:
            path.unlink()
    return len(dropped)


# ------------------------------------------------------------------------------------------------------ Graph reads
def tap_info(method: dict, now: datetime) -> dict:
    """One temporaryAccessPassMethods entry -> state (active | pending | expired | used), start and expiry."""
    start = parse_utc(method.get("startDateTime")) or parse_utc(method.get("createdDateTime"))
    try:
        expires = start + timedelta(minutes=int(method["lifetimeInMinutes"])) if start else None
    except (KeyError, TypeError, ValueError):
        expires = None
    reason = str(method.get("methodUsabilityReason") or "")
    one_time = bool(method.get("isUsableOnce"))
    if reason == "OneTimeUsed":
        state = "used"
    elif reason == "Expired" or (expires is not None and expires <= now):
        state = "expired"
    elif reason == "NotYetValid" or (start is not None and start > now):
        state = "pending"
    elif one_time and method.get("isUsable") is False and not reason:
        state = "used"  # unexpired, already valid, one-time and no longer usable: it has been used
    else:
        state = "active"
    return {"id": str(method.get("id") or ""), "state": state, "start": start, "expires": expires,
            "one_time": one_time, "reason": reason, "usable": method.get("isUsable")}


def list_taps(client, user_id: str, now: datetime) -> list[dict]:
    page = client.get(TAP_METHODS.format(uid=user_id), ok_404=True) or {}
    return [tap_info(m, now) for m in page.get("value", [])]


def read_org(client) -> tuple[str, str]:
    """(tenant display name, default domain)."""
    org = client.get("/v1.0/organization?$select=id,displayName,verifiedDomains")["value"][0]
    domain = next(d["name"] for d in org["verifiedDomains"] if d.get("isDefault"))
    return str(org.get("displayName") or "?"), domain


def lookup_accounts(client, run: Run, domain: str) -> list[Account]:
    accounts = []
    for n in run.numbers:
        upn = f"{run.prefix}{n:02d}@{domain}"
        user = client.get(f"/v1.0/users/{upn}?$select=id,userPrincipalName,accountEnabled", ok_404=True)
        if user:
            accounts.append(Account(n, upn, str(user["id"]), True, user.get("accountEnabled") is not False))
        else:
            accounts.append(Account(n, upn))
    return accounts


def window(start: datetime | None, expires: datetime | None, usage: str, now: datetime) -> str:
    if expires is None:
        return "expiry unknown"
    head = f"from {fmt_utc(start)} " if start is not None and start > now else ""
    return f"{head}until {fmt_utc(expires)} ({fmt_local(expires, usage)})"


# --------------------------------------------------------------------------------------------------------- the check
def evaluate_policy(rep: Report, policy: dict, run: Run) -> None:
    state = str(policy.get("state") or "").lower()
    if state == "enabled":
        rep.ok("the Temporary Access Pass policy is enabled")
    else:
        rep.bad(f"the Temporary Access Pass policy is '{state or 'unknown'}', not enabled",
                ["Enable it for the lab accounts: Entra admin center > Authentication methods > Policies > "
                 "Temporary Access Pass.", FIX_POLICY])

    lo, hi = policy.get("minimumLifetimeInMinutes"), policy.get("maximumLifetimeInMinutes")
    lo = lo if isinstance(lo, int) else None
    hi = hi if isinstance(hi, int) else None
    if lo is not None and run.lifetime < lo:
        rep.bad(f"the requested lifetime ({run.lifetime} minutes) is below the policy minimum ({lo} minutes)",
                [f"Use --lifetime-minutes between {lo} and {hi if hi is not None else '?'}, or ask for the policy "
                 "to change.", FIX_POLICY])
    elif hi is not None and run.lifetime > hi:
        rep.bad(f"the requested lifetime ({run.lifetime} minutes) is above the policy maximum ({hi} minutes)",
                [f"Use --lifetime-minutes between {lo if lo is not None else '?'} and {hi}, or ask for the policy "
                 "to change.", FIX_POLICY])
    elif lo is None and hi is None:
        rep.warn("the policy did not report its lifetime bounds: confirm them in the Entra admin center")
    else:
        rep.ok(f"the requested lifetime ({run.lifetime} minutes) is within the policy bounds "
               f"({lo if lo is not None else '?'} to {hi if hi is not None else '?'} minutes)")

    forced = policy.get("isUsableOnce")
    if forced is True and not run.one_time:
        rep.bad("the policy forces one-time passes (isUsableOnce = true) but workshop.yaml asks for reusable "
                "passes (tap.one_time_use: false)",
                ["A one-time pass stops working after its first sign-in, so the portal, Fabric and az login would "
                 "each need a new pass. Ask for the policy's one-time use to be turned off, or set "
                 "tap.one_time_use: true and plan one pass per sign-in.", FIX_POLICY])
    elif forced is True:
        rep.ok("the policy forces one-time passes, as workshop.yaml asks")
    elif forced is False:
        rep.ok("the policy allows " + ("one-time passes (requested)" if run.one_time else "reusable passes"))
    else:
        rep.warn("the policy did not report isUsableOnce: confirm it in the Entra admin center")

    targets = [t for t in (policy.get("includeTargets") or []) if isinstance(t, dict)]
    excluded = [t for t in (policy.get("excludeTargets") or []) if isinstance(t, dict)]
    if any(str(t.get("id", "")).lower() == "all_users" for t in targets):
        if excluded:
            rep.warn(f"the policy targets all users but excludes {len(excluded)} group(s): verify group membership "
                     "(the lab accounts must not be in them)")
        else:
            rep.ok("the policy targets all users and excludes no group")
    elif targets:
        rep.warn(f"the policy targets {len(targets)} specific group(s), not all users: verify group membership "
                 "(the lab accounts must be in them; this check cannot see group membership)")
    else:
        rep.warn("the policy lists no include targets: verify who it applies to in the Entra admin center")


def run_checks(run: Run, client, announce: bool = True) -> Checked:
    """Read-only: Graph GETs and a local token decode. Shared by `issue --check` and `issue --apply`."""
    rep = Report()
    now = run.now()
    if announce:
        print(f"[issue-tap] environment '{run.env}': checking (read-only; nothing is created, changed or deleted)")
    if run.sign_in != "tap":
        rep.bad(f"environments.{run.env}.lab_accounts.sign_in is '{run.sign_in}', not 'tap'",
                ["This environment signs in with passwords. Set sign_in: tap in content/config/workshop.yaml "
                 "before issuing Temporary Access Passes."])
    if run.start is not None and run.start <= now:
        rep.bad(f"--start {fmt_utc(run.start)} is not in the future",
                ["Leave --start out to make the passes valid as soon as they are created."])

    claims = jwt_claims(str(getattr(client, "token", "") or ""))
    granted = {s.lower() for s in str(claims.get("scp") or "").split()}
    granted |= {str(r).lower() for r in (claims.get("roles") or [])}
    who = claims.get("upn") or claims.get("unique_name") or claims.get("preferred_username") or claims.get("appid")
    if who:
        rep.info(f"the Graph token is for {who}")
    if not claims:
        rep.warn("cannot read the scopes of the Graph token locally (it is not a JWT)",
                 [f"Issuing needs the delegated permission {TAP_SCOPE}."])
    elif TAP_SCOPE.lower() in granted:
        rep.ok(f"the Graph token carries {TAP_SCOPE}")
    else:
        rep.warn(f"the Graph token does not carry {TAP_SCOPE}", fix_for(ApiError(403, "", ""), "tap", run.tenant))

    checked = Checked(rep)
    try:
        tenant_name, domain = read_org(client)
    except ApiError as e:
        rep.bad(f"cannot read the tenant: {describe(e)}", fix_for(e, "users", run.tenant))
        return checked
    except (KeyError, IndexError, StopIteration, TypeError):
        rep.bad("the tenant has no default domain in Graph /v1.0/organization")
        return checked
    checked.domain = domain
    rep.ok(f"tenant '{tenant_name}', default domain {domain}")

    try:
        policy = client.get(POLICY_PATH)
    except ApiError as e:
        rep.bad(f"cannot read the Temporary Access Pass policy: {describe(e)}", fix_for(e, "policy", run.tenant))
    else:
        evaluate_policy(rep, policy or {}, run)

    try:
        checked.accounts = lookup_accounts(client, run, domain)
    except ApiError as e:
        rep.bad(f"cannot look up the lab accounts: {describe(e)}", fix_for(e, "users", run.tenant))
        return checked
    missing = [a.upn for a in checked.accounts if not a.exists]
    disabled = [a.upn for a in checked.accounts if a.exists and not a.enabled]
    total = len(checked.accounts)
    if missing:
        rep.bad(f"{len(missing)} of {total} accounts do not exist: {preview(missing)}",
                [f"Create them: scripts/tenant/create-lab-users.sh {run.env}"])
    if disabled:
        rep.bad(f"{len(disabled)} of {total} accounts are disabled: {preview(disabled)}",
                ["A disabled account cannot sign in, even with a pass. Re-enable it in the Entra admin center."])
    if not missing and not disabled:
        rep.ok(f"all {total} lab accounts exist and are enabled")

    listing_failed = False
    for a in checked.accounts:
        if not a.exists or listing_failed:
            continue
        try:
            a.taps = list_taps(client, a.user_id, now)
        except ApiError as e:
            rep.bad(f"cannot read the Temporary Access Pass methods of {a.upn}: {describe(e)}",
                    fix_for(e, "tap", run.tenant))
            listing_failed = e.status in (401, 403)  # the same answer would follow for every account
    listed = [a for a in checked.accounts if a.taps is not None]
    if listed:
        live = sum(1 for a in listed if any(t["state"] in LIVE_STATES for t in a.taps or []))
        rep.info(f"{live} of {len(listed)} accounts already hold an unexpired pass: `issue --apply` skips them "
                 "unless --replace is given")
    return checked


def cmd_check(run: Run, client) -> int:
    rep = run_checks(run, client).report
    print(f"[issue-tap] check finished: {rep.failures} failure(s), {rep.warnings} warning(s). Nothing was changed.")
    if rep.failures:
        return 1
    print("  Only creating a pass proves the signed-in account may issue it: the warnings above show what could "
          "still fail.")
    print("  Next: issue --apply (add --start <ISO time with offset> to issue ahead of the day).")
    return 0


# ----------------------------------------------------------------------------------------------------------- plans
def start_text(run: Run) -> str:
    if run.start is None:
        return "when each pass is created (no --start)"
    return f"{fmt_utc(run.start)}  ({fmt_local(run.start, run.usage_location)})"


def plan_issue(run: Run) -> int:
    print(f"[issue-tap] environment '{run.env}' (sign_in = {run.sign_in}): PLAN ONLY. "
          "Nothing was contacted or changed.")
    print(f"  accounts   : {accounts_text(run)}")
    print(f"  lifetime   : {run.lifetime} minutes")
    print("  one-time   : " + ("yes: each pass works for one sign-in" if run.one_time
                               else "no: reusable until it expires"))
    print(f"  valid from : {start_text(run)}")
    print(f"  output     : {run.csv_name} (gitignored; upn,tap_id,tap,start_utc,expires_utc,one_time)")
    print("  secrets    : values go to that file only; the console shows UPNs and expiry (values only with "
          "--show-secrets)")
    print("  existing   : an account that already holds an unexpired pass is skipped unless --replace")
    if run.replace:
        print("  replace    : yes: with --apply an unexpired pass is deleted first and a new one issued")
    if run.show_secrets:
        print("  show       : yes: with --apply the values are printed to the console after a loud warning")
    if run.sign_in != "tap":
        print(f"  NOTE       sign_in is '{run.sign_in}' for this environment: --check and --apply refuse until "
              "workshop.yaml says tap")
    if run.start is not None and run.start <= run.now():
        print("  NOTE       --start is not in the future: --check and --apply refuse. Leave --start out to make the "
              "passes valid as soon as they are created.")
    print("  Next: `issue --check` (read-only Graph GETs), then `issue --apply` (creates the passes).")
    return 0


def plan_revoke(run: Run) -> int:
    print(f"[issue-tap] environment '{run.env}': REVOKE PLAN ONLY. Nothing was contacted or changed.")
    print(f"  accounts   : {accounts_text(run)}")
    print("  would      : delete every Temporary Access Pass of each account, then revoke its sign-in sessions")
    print(f"  also       : drop those accounts' rows from {run.csv_name}")
    print("  does NOT   : disable or delete the accounts (scripts/tenant/create-lab-users.sh "
          f"{run.env} --disable or --delete)")
    print("  Run again with --apply to do it (this changes the tenant).")
    return 0


# ---------------------------------------------------------------------------------------------------------- issue
def issue_apply(run: Run, client) -> int:
    print(f"[issue-tap] environment '{run.env}': issuing Temporary Access Passes (this CREATES passes in the tenant)")
    checked = run_checks(run, client, announce=False)
    if checked.report.failures:
        print(f"[issue-tap] REFUSING to issue: {checked.report.failures} check(s) failed (see above). "
              "Nothing was created.")
        return 1
    if checked.report.warnings:
        print(f"[issue-tap] {checked.report.warnings} warning(s) above: continuing. A Graph 403 below means the "
              "scope or role warning was real.")

    path = run.tap_path
    try:
        rows = read_tap_file(path)
        write_tap_file(path, rows)  # fail now, not after passes exist whose values could not be saved
    except OSError as e:
        print(f"[issue-tap] REFUSING to issue: cannot use {run.csv_name} ({e.strerror or e.__class__.__name__}). "
              "Close it in any other program and re-run. Nothing was created.")
        return 1
    if run.show_secrets:
        print("  ###############################################################################")
        print("  # --show-secrets: the Temporary Access Pass VALUES are printed below.         #")
        print("  # Anyone who sees this screen, its scrollback or a log of it can sign in as   #")
        print("  # these accounts until the passes expire. Clear the screen afterwards.        #")
        print("  ###############################################################################")

    body = {"lifetimeInMinutes": run.lifetime, "isUsableOnce": run.one_time}
    if run.start is not None:
        body["startDateTime"] = fmt_utc(run.start)
    created = replaced = skipped = 0
    failures: list[tuple[ApiError, str]] = []
    failed = 0
    unsaved = False

    def save() -> None:
        nonlocal unsaved
        try:
            write_tap_file(path, rows)
        except OSError as e:
            unsaved = True
            print(f"  ERROR     cannot update {run.csv_name} ({e.strerror or e.__class__.__name__}): the complete "
                  f"data is in {run.csv_name}.tmp. KEEP THAT FILE.")

    for a in checked.accounts:
        key = a.upn.lower()
        now = run.now()
        live = [t for t in (a.taps or []) if t["state"] in LIVE_STATES]
        if live and not run.replace:
            have = rows.get(key)
            on_file = bool(have and have["tap"] and have["tap_id"] in {t["id"] for t in live})
            if have and not on_file:
                rows.pop(key)  # a row from an older pass that no longer exists
                save()
            first = min(live, key=lambda t: t["expires"] or now)
            print(f"  skipped   {a.upn}  already holds an unexpired pass "
                  f"({window(first['start'], first['expires'], run.usage_location, now)}); "
                  + ("its value is in the CSV" if on_file else "its value is NOT in the CSV: use --replace to "
                     "issue a new one"))
            skipped += 1
            continue
        old_deleted = False
        try:
            for t in live:
                client.delete(TAP_METHODS.format(uid=a.user_id) + "/" + t["id"])
            old_deleted = bool(live)
            resp = client.post(TAP_METHODS.format(uid=a.user_id), body) or {}
        except ApiError as e:
            if old_deleted and rows.pop(key, None) is not None:
                save()
            failed += 1
            failures.append((e, "tap"))
            print(f"  FAILED    {a.upn}  {describe(e)}" + ("  (the old pass was deleted: this account has no pass)"
                                                           if old_deleted else ""))
            continue
        secret = str(resp.get("temporaryAccessPass") or "")
        start = parse_utc(resp.get("startDateTime")) or run.start or now
        try:
            minutes = int(resp.get("lifetimeInMinutes") or run.lifetime)
        except (TypeError, ValueError):
            minutes = run.lifetime
        expires = start + timedelta(minutes=minutes)
        if not secret:
            failed += 1
            rows.pop(key, None)
            save()
            print(f"  FAILED    {a.upn}  Graph created a pass but returned no value, and a value cannot be read "
                  "again: run again with --replace --only " + str(a.number))
            continue
        rows[key] = {"upn": a.upn, "tap_id": str(resp.get("id") or ""), "tap": secret, "start_utc": fmt_utc(start),
                     "expires_utc": fmt_utc(expires), "one_time": "true" if resp.get("isUsableOnce", run.one_time)
                     else "false"}
        save()
        if live:
            replaced += 1
        else:
            created += 1
        line = (f"  {'replaced' if live else 'created':<9} {a.upn}  "
                f"{window(start, expires, run.usage_location, now)}"
                + ("  one-time" if rows[key]["one_time"] == "true" else ""))
        if run.show_secrets:
            line += f"  TAP: {secret}"
        print(line)

    print(f"[issue-tap] created {created}, replaced {replaced}, skipped {skipped}, failed {failed}.")
    if failures:
        print_fixes(failures, run.tenant)
    if created or replaced:
        print(f"  Pass values: {run.csv_name} (gitignored; owner-only where the OS supports it). They are not printed"
              f"{'' if run.show_secrets else ' (use --show-secrets, or print them on the cards)'}.")
        print(f"  Next: python scripts/tenant/sign-in-cards.py {run.env} --lab-accounts [--with-tap], then test ONE "
              "account in a private browser window before the day.")
        print("  UNVERIFIED here: whether the portal, Fabric and `az login` (browser or --use-device-code) accept a "
              "pass in this tenant or in Codespaces.")
    return 1 if failed or unsaved else 0


# ---------------------------------------------------------------------------------------------------------- revoke
def revoke_apply(run: Run, client) -> int:
    print(f"[issue-tap] environment '{run.env}': revoking (this DELETES passes and REVOKES sign-in sessions)")
    try:
        _, domain = read_org(client)
    except (KeyError, IndexError, StopIteration, TypeError):
        print("[issue-tap] the tenant has no default domain in Graph /v1.0/organization")
        return 1
    revoked, purge, passes, absent, failed = [], [], 0, 0, 0
    failures: list[tuple[ApiError, str]] = []
    for a in lookup_accounts(client, run, domain):
        if not a.exists:
            absent += 1
            print(f"  absent    {a.upn}")
            continue
        kind = "tap"
        try:
            methods = list_taps(client, a.user_id, run.now())
            for t in methods:
                client.delete(TAP_METHODS.format(uid=a.user_id) + "/" + t["id"])
                passes += 1
            purge.append(a.upn)  # its passes are gone, so their values have no use left
            kind = "revoke"
            client.post(f"/v1.0/users/{a.user_id}/revokeSignInSessions")
        except ApiError as e:
            failed += 1
            failures.append((e, kind))
            print(f"  FAILED    {a.upn}  {describe(e)}")
            continue
        revoked.append(a.upn)
        print(f"  revoked   {a.upn}  {len(methods)} pass(es) deleted, sign-in sessions revoked")
    dropped = 0
    if purge:
        try:
            dropped = forget_rows(run.tap_path, purge)
        except OSError as e:
            print(f"  WARN      could not update {run.csv_name} ({e.strerror or e.__class__.__name__}): delete the "
                  "file yourself, its values are no longer valid")
    print(f"[issue-tap] revoked {len(revoked)} account(s) ({passes} pass(es) deleted), failed {failed}, "
          f"absent {absent}." + (f" Dropped {dropped} row(s) from {run.csv_name}." if dropped else ""))
    if failures:
        print_fixes(failures, run.tenant)
    print("  This does NOT disable the accounts: use scripts/tenant/create-lab-users.sh "
          f"{run.env} --disable (or --delete); it runs scripts/lib/lab_users.py.")
    return 1 if failed else 0


# ---------------------------------------------------------------------------------------------------------- status
def status(run: Run, client) -> int:
    print(f"[issue-tap] environment '{run.env}': status (read-only; pass values are never shown)")
    now = run.now()
    try:
        _, domain = read_org(client)
    except (KeyError, IndexError, StopIteration, TypeError):
        print("[issue-tap] the tenant has no default domain in Graph /v1.0/organization")
        return 1
    on_file = read_tap_file(run.tap_path, include_secret=False)
    counts = {"active": 0, "pending": 0, "none": 0}
    problems = 0
    failures: list[tuple[ApiError, str]] = []
    for a in lookup_accounts(client, run, domain):
        if not a.exists:
            print(f"  MISSING   {a.upn}  account not found")
            problems += 1
            continue
        try:
            taps = list_taps(client, a.user_id, now)
        except ApiError as e:
            problems += 1
            failures.append((e, "tap"))
            print(f"  FAILED    {a.upn}  {describe(e)}")
            if e.status in (401, 403):
                break
            continue
        live = [t for t in taps if t["state"] in LIVE_STATES]
        flag = "  DISABLED" if not a.enabled else ""
        if live:
            t = min(live, key=lambda x: x["expires"] or now)
            counts[t["state"]] += 1
            row = on_file.get(a.upn.lower())
            held = "value in CSV" if row and row["tap_id"] == t["id"] else "value NOT in CSV"
            unusable = ""
            if t["state"] == "active" and t["usable"] is False:
                unusable = "  Graph: not usable now" + (f" ({t['reason']})" if t["reason"] else "")
            print(f"  {t['state']:<9} {a.upn}  {window(t['start'], t['expires'], run.usage_location, now)}  "
                  f"{'one-time  ' if t['one_time'] else ''}{held}{unusable}{flag}")
        else:
            counts["none"] += 1
            last = max(taps, key=lambda x: x["expires"] or now, default=None)
            why = f"  (last pass: {last['state']})" if last else ""
            print(f"  none      {a.upn}{why}{flag}")
    print(f"[issue-tap] {counts['active']} active, {counts['pending']} not yet valid, {counts['none']} without an "
          f"unexpired pass, {problems} problem(s).")
    if failures:
        print_fixes(failures, run.tenant)
    return 1 if problems else 0


# ------------------------------------------------------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="issue_tap.py", description=__doc__.splitlines()[0],
                                 epilog="issue and revoke only print their plan unless --check / --apply is given.")
    sub = ap.add_subparsers(dest="command", required=True, metavar="{issue,revoke,status}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--env", help="environment name (default: AZURE_ENV_NAME)")
    common.add_argument("--count", type=int, help="number of lab accounts (default: lab_accounts.count)")
    common.add_argument("--prefix", help="account name prefix (default: lab_accounts.prefix)")
    common.add_argument("--only", metavar="N[,N...]", help="only these account numbers (default: 1..count)")

    issue = sub.add_parser("issue", parents=[common], help="create passes: plan only unless --check or --apply")
    issue.add_argument("--check", action="store_true", help="read-only Graph checks (scopes, policy, accounts)")
    issue.add_argument("--apply", action="store_true", help="create the passes (checks first; refuses if they fail)")
    issue.add_argument("--lifetime-minutes", type=int,
                       help="pass lifetime (default: lab_accounts.tap.lifetime_minutes, else 480)")
    issue.add_argument("--start", metavar="ISO", help="valid from this time, with a UTC offset or Z, "
                                                      "e.g. 2026-11-03T08:00:00+08:00 (default: at creation)")
    issue.add_argument("--replace", action="store_true",
                       help="delete an account's unexpired pass first (default: skip such accounts)")
    issue.add_argument("--show-secrets", action="store_true",
                       help="also print the pass values to the console (default: CSV only)")

    revoke = sub.add_parser("revoke", parents=[common],
                            help="delete passes and revoke sign-in sessions: plan only unless --apply")
    revoke.add_argument("--apply", action="store_true", help="do it (changes the tenant)")
    sub.add_parser("status", parents=[common], help="read-only: which accounts hold a pass and until when")
    return ap


def main(argv: list[str] | None = None, *, cfg: dict | None = None, client_factory=None, root: Path | None = None,
         environ=None, now: Callable[[], datetime] | None = None) -> int:
    """cfg, client_factory, root, environ and now are injection points for tests; the CLI passes none of them."""
    args = build_parser().parse_args(argv)
    environ = os.environ if environ is None else environ
    env = args.env or environ.get("AZURE_ENV_NAME", "")
    if not env:
        return usage_error("no environment: pass --env, or run scripts/tenant/issue-tap.sh [env]")
    cfg = cfg if cfg is not None else wsconfig.load(env)
    env_cfg = (cfg.get("environments") or {}).get(env)
    if not env_cfg:
        return usage_error(f"environment '{env}' is not in content/config/workshop.yaml")
    settings = lab_settings(cfg, env)
    if args.count is not None and args.count < 1:
        return usage_error("--count must be at least 1")
    count = args.count or settings["count"]
    lifetime = getattr(args, "lifetime_minutes", None)
    if lifetime is not None and lifetime < 1:
        return usage_error("--lifetime-minutes must be at least 1")
    try:
        numbers = parse_only(args.only, count)
        start = parse_start(args.start) if getattr(args, "start", None) else None
    except ValueError as e:
        return usage_error(str(e))
    tenant = str(env_cfg.get("tenant_id") or "")
    run = Run(env=env, prefix=args.prefix or settings["prefix"], numbers=numbers,
              lifetime=lifetime or settings["tap_lifetime_minutes"], one_time=settings["tap_one_time_use"],
              start=start, usage_location=settings["usage_location"], sign_in=settings["sign_in"],
              tenant="" if tenant.strip().upper() in ("", "TODO") else tenant,
              tap_path=tap_file_path(env, ROOT if root is None else root),
              replace=getattr(args, "replace", False), show_secrets=getattr(args, "show_secrets", False),
              now=now or utc_now)
    factory = client_factory or make_client
    try:
        if args.command == "issue":
            if args.check and args.apply:
                return usage_error("choose --check (read-only) or --apply (creates passes), not both")
            if args.apply:
                return issue_apply(run, factory())
            return cmd_check(run, factory()) if args.check else plan_issue(run)
        if args.command == "revoke":
            return revoke_apply(run, factory()) if args.apply else plan_revoke(run)
        return status(run, factory())
    except ApiError as e:
        print(f"[issue-tap] Graph request failed: {describe(e)}")
        print_fixes([(e, "tap")], run.tenant)
        return 1


if __name__ == "__main__":
    sys.exit(main())
