#!/usr/bin/env python3
"""Target guard: is this shell pointed at the workshop subscription and tenant?

  python scripts/lib/target.py check --env mcaps [--tokens]

A laptop is often signed in to several tenants, and `az` acts on whichever subscription is its default. Every
script that reads, creates or deletes workshop resources calls this first (scripts/lib/common.sh: load_azd_env)
and STOPS on a mismatch. It never switches subscription for you; it prints the exact command to run.

--tokens also requests an ARM token for the configured tenant and checks its `tid` claim, which catches a
stale AZURE_TENANT_ID or a cached sign-in for the wrong tenant.

Exit: 0 match, 2 mismatch or unsafe state, 3 az missing / not signed in.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wsconfig  # noqa: E402
from azrest import az_token, jwt_claims, run_az, token_tenant  # noqa: E402,F401  (jwt_claims/token_tenant re-exported)

PLACEHOLDERS = {"", "todo"}
AZ_TIMEOUT = 60


def same(a: str, b: str) -> bool:
    return a.strip().lower() == b.strip().lower()


def configured(env: str, cfg: dict | None = None) -> tuple[str, str]:
    cfg = cfg if cfg is not None else wsconfig.load(env)
    e = (cfg.get("environments") or {}).get(env) or {}
    return str(e.get("subscription_id", "")), str(e.get("tenant_id", ""))


def evaluate(env: str, want_sub: str, want_tenant: str, active: dict | None, environ: dict,
             tenant_only: bool = False) -> list[str]:
    """Pure check. Returns the problems; an empty list means the session targets the workshop subscription.
    tenant_only: for Entra / Graph scripts, which need the right tenant but not a subscription."""
    problems: list[str] = []
    if tenant_only:
        if not want_tenant or want_tenant.strip().lower() in PLACEHOLDERS:
            return [f"environments.{env}.tenant_id is not set in content/config/workshop.yaml"]
    elif want_sub.strip().lower() in PLACEHOLDERS:
        return [f"environments.{env}.subscription_id is not set in content/config/workshop.yaml"]
    if not active:
        return [f"az is not signed in. Run: az login --tenant {want_tenant or '<tenant-id>'}"]
    if not tenant_only and not same(active.get("id", ""), want_sub):
        problems.append(
            f"az is on subscription {active.get('id', '?')} ({active.get('name', '?')}) but environment '{env}' "
            f"targets {want_sub}. Run: az account set --subscription {want_sub}  "
            f"(if that fails: az login --tenant {want_tenant})")
    if want_tenant and not same(active.get("tenantId", ""), want_tenant):
        problems.append(
            f"az is signed in to tenant {active.get('tenantId', '?')} but environment '{env}' targets {want_tenant}. "
            f"Run: az login --tenant {want_tenant}")
    var = environ.get("AZURE_SUBSCRIPTION_ID", "")
    if not tenant_only and var and not same(var, want_sub):
        problems.append(f"AZURE_SUBSCRIPTION_ID is {var} (stale shell or azd env value), expected {want_sub}")
    var = environ.get("AZURE_TENANT_ID", "")
    if want_tenant and var and not same(var, want_tenant):
        problems.append(f"AZURE_TENANT_ID is {var} (stale shell or azd env value), expected {want_tenant}")
    return problems


def az_json(args: list[str]) -> dict | None:
    try:
        proc = run_az(args, AZ_TIMEOUT)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return None


def arm_token_problem(want_sub: str, want_tenant: str, tenant_only: bool = False) -> str | None:
    """None when an ARM token can be obtained silently for the configured tenant (its `tid` claim is checked)."""
    try:
        az_token("https://management.azure.com/", want_tenant or None, None if tenant_only else (want_sub or None))
    except SystemExit as e:
        return str(e)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["check"])
    ap.add_argument("--env", default=os.environ.get("AZURE_ENV_NAME", ""))
    ap.add_argument("--tokens", action="store_true", help="also verify the tenant claim of an ARM token")
    ap.add_argument("--tenant-only", action="store_true",
                    help="Entra/Graph scripts: require the right tenant, not a particular subscription")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    if not args.env:
        sys.stderr.write("target: no environment (use --env or select an azd environment)\n")
        return 2

    want_sub, want_tenant = configured(args.env)
    if not shutil.which("az"):
        sys.stderr.write("target: az CLI not found\n")
        return 3
    active = az_json(["account", "show", "-o", "json"])
    problems = evaluate(args.env, want_sub, want_tenant, active, dict(os.environ), tenant_only=args.tenant_only)
    if not problems and args.tokens:
        extra = arm_token_problem(want_sub, want_tenant, args.tenant_only)
        if extra:
            problems.append(extra)
    if problems:
        sys.stderr.write(f"target: WRONG TARGET for environment '{args.env}' (nothing was changed):\n")
        for p in problems:
            sys.stderr.write(f"  - {p}\n")
        return 3 if active is None else 2
    if not args.quiet:
        who = (active.get("user") or {}).get("name", "?")
        scope = "tenant" if args.tenant_only else f"subscription {want_sub} ({active.get('name', '?')}), tenant"
        print(f"target: environment '{args.env}' -> {scope} {want_tenant}, signed in as {who}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
