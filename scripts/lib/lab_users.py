#!/usr/bin/env python3
"""Create, disable or delete the cloud-only workshop lab accounts via Microsoft Graph.

Called by scripts/tenant/create-lab-users.sh. Idempotent: existing users are left alone.

Accounts: <prefix>01..<prefix><count> @ the tenant's default domain (count from workshop.yaml: 30 for mcaps),
usageLocation from workshop.yaml (SG). How people sign in is environments.<env>.lab_accounts.sign_in:

  tap       (mcaps) Temporary Access Pass. Every account gets a random password that is never printed or written
            anywhere, and no forced password change: the passes from scripts/lib/issue_tap.py are the way in, with no
            Authenticator registration. .azure/<env>/lab-accounts.csv (gitignored) lists the lab accounts as
            upn,display_name only (never the break-glass account, never a password).
  password  (sponsor) a temporary password per account (forceChangePasswordNextSignIn), written to
            .azure/<env>/lab-accounts.csv (gitignored) and never printed; --reset-passwords issues new ones.
            MFA comes from security defaults (Authenticator at first sign-in, no Entra P1 needed).

The break-glass account (<break_glass>) is OPT-IN: --break-glass creates it with Global Administrator
(entra_roles.global_administrator). It is a STANDING Global Administrator: delete it when the workshop is over (--delete
removes it together with the lab accounts) and keep it out of any Conditional Access policy that could lock it out.
--disable sets accountEnabled=false on the lab accounts (nothing is deleted).
"""
from __future__ import annotations

import argparse
import csv
import os
import secrets
import string
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wsconfig  # noqa: E402
from azrest import Api, ApiError  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SIGN_IN_MODES = ("tap", "password")


def temp_password() -> str:
    alphabet = string.ascii_letters + string.digits
    core = "".join(secrets.choice(alphabet) for _ in range(14))
    return f"Lw-{core}!{secrets.randbelow(90) + 10}"


def random_password() -> str:
    """tap mode: nobody ever needs this password, so it is never printed or written anywhere. Entra wants three of the
    four character classes; the suffix guarantees upper, lower, digit and symbol."""
    return secrets.token_urlsafe(32) + "Aa1!"


def lab_settings(cfg: dict, env: str) -> dict:
    """environments.<env>.lab_accounts with the defaults these scripts have always used."""
    lab = ((cfg.get("environments") or {}).get(env) or {}).get("lab_accounts") or {}
    tap = lab.get("tap") or {}
    return {
        "prefix": lab.get("prefix", "hpb.lab"),
        "count": int(lab.get("count", 20)),
        "usage_location": lab.get("usage_location", "SG"),
        "break_glass": lab.get("break_glass", "hpb.breakglass"),
        "sign_in": str(lab.get("sign_in", "password")).strip().lower(),
        "tap_lifetime_minutes": int(tap.get("lifetime_minutes", 480)),
        "tap_one_time_use": bool(tap.get("one_time_use", False)),
    }


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--count", type=int, help="number of lab accounts (default: lab_accounts.count in workshop.yaml)")
    ap.add_argument("--break-glass", action="store_true",
                    help="also create the break-glass account: a STANDING Global Administrator (off by default)")
    ap.add_argument("--no-break-glass", action="store_true",
                    help="accepted and ignored: the break-glass account is created only with --break-glass")
    ap.add_argument("--reset-passwords", action="store_true", help="password mode only: issue new temporary passwords")
    what = ap.add_mutually_exclusive_group()
    what.add_argument("--delete", action="store_true",
                      help="delete the lab accounts and the break-glass account if it exists")
    what.add_argument("--disable", action="store_true",
                      help="set accountEnabled=false on the lab accounts (nothing is deleted)")
    ap.add_argument("--dry-run", action="store_true")
    return ap.parse_args(argv)


def usage_error(message: str) -> int:
    print(f"[create-lab-users] {message}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None, *, cfg: dict | None = None, graph_factory=None, root: Path = ROOT,
         environ=None) -> int:
    """graph_factory, cfg, root and environ are injection points for tests; the CLI passes none of them."""
    args = parse_args(argv)
    environ = os.environ if environ is None else environ
    env = environ.get("AZURE_ENV_NAME", "")
    cfg = cfg if cfg is not None else wsconfig.load(env)
    settings = lab_settings(cfg, env)
    mode = settings["sign_in"]
    if mode not in SIGN_IN_MODES:
        return usage_error(f"environments.{env}.lab_accounts.sign_in is '{mode}': use 'tap' or 'password'")
    tap_mode = mode == "tap"
    if tap_mode and args.reset_passwords:
        return usage_error(
            f"--reset-passwords does not apply: environment '{env}' signs in with a Temporary Access Pass "
            "(lab_accounts.sign_in = tap), so no account has a password to reset. Issue a new pass instead: "
            f"scripts/tenant/issue-tap.sh {env} issue --replace --only <account number> --apply "
            "(scripts/lib/issue_tap.py).")
    if args.break_glass and (args.delete or args.disable):
        return usage_error("--break-glass only applies when creating accounts: --delete already removes the "
                           "break-glass account, and --disable leaves it alone")
    if args.break_glass and args.no_break_glass:
        return usage_error("--break-glass and --no-break-glass contradict each other")
    if args.no_break_glass:
        print("[create-lab-users] note: --no-break-glass is ignored; the break-glass account is created only with "
              "--break-glass.")

    prefix, usage, bg = settings["prefix"], settings["usage_location"], settings["break_glass"]
    count = args.count or settings["count"]

    graph = (graph_factory or (lambda: Api("graph")))()
    org = graph.get("/v1.0/organization?$select=id,displayName,countryLetterCode,verifiedDomains")["value"][0]
    domain = next(d["name"] for d in org["verifiedDomains"] if d.get("isDefault"))
    print(f"[create-lab-users] tenant {org['displayName']} (country {org.get('countryLetterCode')}), domain {domain}")
    if org.get("countryLetterCode") not in (None, "SG"):
        print("  WARN  tenant country is not SG (SPEC.md §12.2) — continuing")
    if tap_mode:
        print("[create-lab-users] sign-in mode: tap (Temporary Access Pass); passwords are random and never "
              "shown or saved")

    wanted = [(f"{prefix}{i:02d}", f"LiveWell Lab {i:02d}", False) for i in range(1, count + 1)]
    if args.break_glass or args.delete:
        wanted.append((bg, "LiveWell Break Glass", True))

    bg_upn = f"{bg}@{domain}"
    out = root / ".azure" / (env or "default") / "lab-accounts.csv"
    rows: list[dict] = []
    if out.exists():
        with out.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    had_passwords = tap_mode and any(r.get("temporary_password") for r in rows)
    by_upn = {r["upn"]: ({"upn": r["upn"], "display_name": r.get("display_name", "")} if tap_mode else r)
              for r in rows}
    if tap_mode:
        by_upn.pop(bg_upn, None)  # the account list feeds the sign-in cards: never a card for a Global Administrator
    created = existing = reset = deleted = disabled = 0
    bg_created = bg_role_added = False
    for nick, display, is_bg in wanted:
        upn = f"{nick}@{domain}"
        tag = "  (break-glass account)" if is_bg else ""
        user = graph.get(f"/v1.0/users/{upn}?$select=id,userPrincipalName,usageLocation,accountEnabled", ok_404=True)
        if args.delete:
            if user and not args.dry_run:
                graph.delete(f"/v1.0/users/{user['id']}")
            if user:
                deleted += 1
                by_upn.pop(upn, None)
            verb = ("would delete" if args.dry_run else "deleted") if user else "absent"
            print(f"  {verb}  {upn}{tag}")
            continue
        if args.disable:
            if not user:
                print(f"  absent   {upn}")
            elif user.get("accountEnabled") is False:
                print(f"  already disabled  {upn}")
            else:
                if not args.dry_run:
                    graph.patch(f"/v1.0/users/{user['id']}", {"accountEnabled": False})
                disabled += 1
                print(f"  {'would disable' if args.dry_run else 'disabled'}  {upn}")
            continue
        if user:
            existing += 1
            if tap_mode and not is_bg:
                by_upn.setdefault(upn, {"upn": upn, "display_name": display})  # cards need only the account name
            if user.get("usageLocation") != usage and not args.dry_run:
                graph.patch(f"/v1.0/users/{user['id']}", {"usageLocation": usage})
            if args.reset_passwords and not args.dry_run:
                pwd = temp_password()
                graph.patch(f"/v1.0/users/{user['id']}", {"passwordProfile": {
                    "forceChangePasswordNextSignIn": True, "password": pwd}})
                by_upn[upn] = {"upn": upn, "display_name": display, "temporary_password": pwd}
                reset += 1
            if user.get("accountEnabled") is False:
                off = "  (account is DISABLED: re-enable it in the Entra admin center)"
            else:
                off = ""
            print(f"  exists   {upn}{' (password reset)' if args.reset_passwords else ''}{off}")
        else:
            if args.dry_run:
                print(f"  would create {upn}{'  (break-glass: a STANDING Global Administrator)' if is_bg else ''}")
                continue
            pwd = random_password() if tap_mode else temp_password()
            user = graph.post("/v1.0/users", {
                "accountEnabled": True, "displayName": display, "mailNickname": nick.replace(".", ""),
                "userPrincipalName": upn, "usageLocation": usage,
                "passwordProfile": {"forceChangePasswordNextSignIn": not is_bg and not tap_mode, "password": pwd},
            })
            if not (tap_mode and is_bg):
                by_upn[upn] = ({"upn": upn, "display_name": display} if tap_mode
                               else {"upn": upn, "display_name": display, "temporary_password": pwd})
            created += 1
            bg_created = bg_created or is_bg
            print(f"  created  {upn}")
        if is_bg and not args.dry_run:
            role = cfg["entra_roles"]["global_administrator"]
            flt = urllib.parse.quote(f"principalId eq '{user['id']}' and roleDefinitionId eq '{role}'", safe="'")
            have = graph.get(f"/v1.0/roleManagement/directory/roleAssignments?$filter={flt}").get("value", [])
            if not have:
                try:
                    graph.post("/v1.0/roleManagement/directory/roleAssignments",
                               {"principalId": user["id"], "roleDefinitionId": role, "directoryScopeId": "/"})
                    print(f"  role     Global Administrator -> {upn}")
                    bg_role_added = True
                except ApiError as e:
                    print(f"  WARN     could not assign Global Administrator to {upn}: {e.code or e.status} "
                          "(needs Privileged Role Administrator)")

    if args.break_glass and not args.dry_run:
        if bg_created or bg_role_added:
            print(f"  !!! BREAK-GLASS ACCOUNT {bg_upn} IS A STANDING GLOBAL ADMINISTRATOR.")
            print(f"  !!! Delete it when the workshop is over: scripts/tenant/create-lab-users.sh {env} --delete")
            print("  !!! (that also deletes the lab accounts). Exclude it from any Conditional Access policy that "
                  "could lock it out.")
            if tap_mode:
                print("  !!! Its random password was not saved anywhere: to sign in with it, another administrator "
                      "must issue it a Temporary Access Pass (Privileged Authentication Administrator) or reset "
                      "its password.")
            else:
                print(f"  !!! Its temporary password is in .azure/{env or 'default'}/lab-accounts.csv: keep it "
                      "offline and delete that file after the workshop.")
        else:
            print(f"  NOTE     {bg_upn} already exists and is a standing Global Administrator: delete it at "
                  "teardown (--delete).")
    if args.disable:
        bg_user = graph.get(f"/v1.0/users/{bg_upn}?$select=id,accountEnabled", ok_404=True)
        if bg_user and bg_user.get("accountEnabled") is not False:
            print(f"  WARN     {bg_upn} (break-glass, a standing Global Administrator) is still ENABLED: --disable "
                  f"leaves it alone. Delete it with scripts/tenant/create-lab-users.sh {env} --delete (which also "
                  "deletes the lab accounts) or in the Entra admin center.")

    if not args.dry_run and not args.disable:
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["upn", "display_name"] + ([] if tap_mode else ["temporary_password"]))
            w.writeheader()
            w.writerows(sorted(by_upn.values(), key=lambda r: r["upn"]))
        if had_passwords:
            print("  note     dropped the temporary_password column from lab-accounts.csv: tap mode keeps no "
                  "passwords")
    counts = [f"created {created}", f"existing {existing}"]
    if not tap_mode:
        counts.append(f"passwords reset {reset}")
    counts.append(f"deleted {deleted}")
    if args.disable:
        counts.append(f"disabled {disabled}")
    rel = out.relative_to(root).as_posix()
    where = ""
    if not args.dry_run and not args.disable:
        where = (f" Account list: {rel} (gitignored; no passwords are kept)." if tap_mode
                 else f" Temporary passwords: {rel} (gitignored).")
    print(f"[create-lab-users] {', '.join(counts)}.{where}")
    if tap_mode and not args.dry_run and args.disable:
        print(f"  Passes: scripts/tenant/issue-tap.sh {env} revoke --apply deletes any remaining Temporary Access "
              "Passes and revokes sign-in sessions.")
    if tap_mode and not args.dry_run and (args.disable or args.delete):
        print(f"  Delete .azure/{env or 'default'}/tap-issued.csv too: it still holds Temporary Access Pass values.")
    if tap_mode and created:
        print("  Next: scripts/seed-attendees.sh --lab-accounts. Then the passes:")
        print(f"    scripts/tenant/issue-tap.sh {env} issue --check     (read-only), then: issue --apply")
        print(f"    python scripts/tenant/sign-in-cards.py {env} --lab-accounts     (--with-tap prints the passes)")
    elif not tap_mode and (created or reset):
        print("  Next: print one card per account; first sign-in forces a password change and Authenticator")
        print("  registration (security defaults). Then: scripts/seed-attendees.sh --lab-accounts")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ApiError as e:
        if e.status == 403:
            print(f"[create-lab-users] Graph denied the request ({e.code}). Needs User Administrator "
                  "(and Privileged Role Administrator for the break-glass role) in this tenant.")
            sys.exit(1)
        raise
