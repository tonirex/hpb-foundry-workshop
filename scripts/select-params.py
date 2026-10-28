#!/usr/bin/env python3
"""Select the per-environment parameter file and make `azd provision` self-contained.

Run by scripts/provision.sh BEFORE `azd provision`, and again as the azd preprovision hook (--hook).

0. Stops unless the az session targets this environment's subscription and tenant (scripts/lib/target.py).
1. Copies infra/env/<AZURE_ENV_NAME>.bicepparam -> infra/main.bicepparam (gitignored), fixing the
   `using` path, because azd only reads infra/main.bicepparam.
2. Fills AZURE_PRINCIPAL_ID / AZURE_PRINCIPAL_TYPE in the azd env from the signed-in az identity
   if they are missing (facilitator RBAC in the template), generates the Lab 4 DevUI token
   (LIVEWELL_DEVUI_TOKEN, unless LAB4_DEVUI=false) and pins BUDGET_START_DATE.
3. Creates the resource group (idempotent) with the workshop tags, because the template is
   resource-group scoped. It REFUSES to adopt an existing resource group that holds resources and is not
   tagged as this workshop's (workshop=livewell, azd-env-name=<env>): the workshop never silently reuses
   infrastructure from another workshop or group. ALLOW_EXISTING_RG=1 overrides after a manual review.
   --plan (used by `provision.sh --what-if-only`) does steps 0-2 but creates nothing in Azure.
4. With FABRIC_BRIDGE=true, stops if the Fabric capacity is paused (ARM cannot update it).

azd resolves parameters BEFORE the preprovision hook runs, so in --hook mode any change made in
steps 1-2 stops the run with "re-run" (a stale file can never deploy the wrong environment).

Standard library only (plus the repo's scripts/lib); ASCII output. Exit code != 0 stops `azd provision`.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra"
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import azrest  # noqa: E402
import target  # noqa: E402
import wsconfig  # noqa: E402


def run(cmd: list[str], check: bool = True) -> str:
    exe = shutil.which(cmd[0]) or cmd[0]
    proc = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True)
    if check and proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"[select-params] command failed: {' '.join(cmd)}")
    return proc.stdout.strip()


def load_azd_env() -> None:
    """Outside azd hooks, pull the selected azd env's values into os.environ."""
    out = run(["azd", "env", "get-values"], check=False)
    for line in out.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


def guard_target(env: str) -> str | None:
    """None when the session targets the configured subscription and tenant, else the reason (nothing is switched)."""
    want_sub, want_tenant = target.configured(env)
    active = target.az_json(["account", "show", "-o", "json"])
    problems = target.evaluate(env, want_sub, want_tenant, active, dict(os.environ))
    return "; ".join(problems) if problems else None


def rg_state(rg: str, sub: str, env: str) -> str:
    """missing | ours | empty | foreign. Only 'foreign' (holds resources, not tagged as this workshop) is refused."""
    arm = azrest.Api("arm", subscription=sub)
    base = f"/subscriptions/{sub}/resourceGroups/{rg}"
    shown = arm.get(f"{base}?api-version=2021-04-01", ok_404=True)
    if shown is None:
        return "missing"
    tags = shown.get("tags") or {}
    if tags.get("workshop") == "livewell" and tags.get("azd-env-name") == env:
        return "ours"
    resources = arm.get_all(f"{base}/resources?api-version=2021-04-01")
    return "foreign" if resources else "empty"


def principal_from_token() -> tuple[str, str] | None:
    """Object ID and type of the signed-in identity from its ARM token: no Graph call, so it also works where the
    CLI has no Graph consent. None when the claims are missing."""
    tenant = os.environ.get("AZURE_TENANT_ID") or None
    try:
        claims = azrest.jwt_claims(azrest.az_token("https://management.azure.com", tenant))
    except SystemExit:
        return None
    oid = str(claims.get("oid", ""))
    if not oid:
        return None
    return oid, ("ServicePrincipal" if claims.get("idtyp") == "app" else "User")

def main() -> int:
    hook_mode = "--hook" in sys.argv[1:]
    plan_mode = "--plan" in sys.argv[1:]
    env = os.environ.get("AZURE_ENV_NAME", "").strip()
    if not env:
        env = run(["azd", "env", "get-value", "AZURE_ENV_NAME"], check=False)
        if not env or " " in env:
            print("[select-params] AZURE_ENV_NAME is not set (run inside azd, or `azd env select <env>`).")
            return 1
        load_azd_env()
    wrong = guard_target(env)
    if wrong:
        print(f"[select-params] WRONG TARGET, nothing was changed: {wrong}")
        return 1
    src = INFRA / "env" / f"{env}.bicepparam"
    if not src.exists():
        choices = ", ".join(p.stem for p in sorted((INFRA / "env").glob("*.bicepparam")))
        print(f"[select-params] no parameter file for env '{env}'. Known envs: {choices}")
        return 1

    text = src.read_text(encoding="utf-8")
    text, count = re.subn(r"^using\s+'\.\./main\.bicep'", "using 'main.bicep'", text, flags=re.M)
    if count != 1:
        print(f"[select-params] {src.name} must start with: using '../main.bicep'")
        return 1
    text = text.replace("'../../content/", "'../content/")  # the copy sits one directory higher than infra/env/
    header = f"// GENERATED by scripts/select-params.py from infra/env/{env}.bicepparam. Do not edit.\n"
    desired = header + text
    target_file = INFRA / "main.bicepparam"
    current = target_file.read_text(encoding="utf-8") if target_file.exists() else None
    if current != desired:
        target_file.write_text(desired, encoding="utf-8", newline="\n")
        print(f"[select-params] infra/main.bicepparam <- infra/env/{env}.bicepparam (regenerated)")
        if hook_mode:
            # azd resolved parameters before this hook ran, so this run would use stale/missing values.
            print("[select-params] Parameters changed after azd read them. Re-run the same command "
                  "(or use scripts/provision.sh, which runs this step first).")
            return 1
    else:
        print(f"[select-params] infra/main.bicepparam matches infra/env/{env}.bicepparam")

    if os.environ.get("AZURE_PRINCIPAL_ID"):
        print("[select-params] AZURE_PRINCIPAL_ID already set")
    else:
        found = principal_from_token()
        if found:
            pid, ptype = found
        else:
            account = json.loads(run(["az", "account", "show", "-o", "json"]))
            if account.get("user", {}).get("type") == "servicePrincipal":
                pid = run(["az", "ad", "sp", "show", "--id", account["user"]["name"], "--query", "id", "-o", "tsv"])
                ptype = "ServicePrincipal"
            else:
                pid = run(["az", "ad", "signed-in-user", "show", "--query", "id", "-o", "tsv"])
                ptype = "User"
        run(["azd", "env", "set", "AZURE_PRINCIPAL_ID", pid])
        run(["azd", "env", "set", "AZURE_PRINCIPAL_TYPE", ptype])
        os.environ["AZURE_PRINCIPAL_ID"] = pid
        print(f"[select-params] AZURE_PRINCIPAL_ID set for the signed-in {ptype.lower()}")
        if hook_mode:
            print("[select-params] Principal added after azd read parameters. Re-run the same command.")
            return 1

    # Lab 4 DevUI bearer token (LAB4_DEVUI): one per environment, read by the bicepparam as a secure parameter and
    # used server-side and to sign private expiring links. Never a Bicep output or participant token.
    if (os.environ.get("LAB4_DEVUI", "true").strip().lower() in ("1", "true", "yes")
            and not os.environ.get("LIVEWELL_DEVUI_TOKEN")):
        token = secrets.token_urlsafe(18)
        run(["azd", "env", "set", "LIVEWELL_DEVUI_TOKEN", token])
        os.environ["LIVEWELL_DEVUI_TOKEN"] = token
        print("[select-params] LIVEWELL_DEVUI_TOKEN generated (server-only Lab 4 secret)")
        if hook_mode:
            print("[select-params] DevUI token added after azd read parameters. Re-run the same command.")
            return 1

    # Pin the budget start month for the life of this environment (a budget cannot move its start date).
    # When azd has already read an empty value, main.bicep falls back to the same current month.
    if os.environ.get("BUDGET_START_DATE"):
        print(f"[select-params] BUDGET_START_DATE={os.environ['BUDGET_START_DATE']}")
    else:
        start = datetime.now(timezone.utc).strftime("%Y-%m-01")
        run(["azd", "env", "set", "BUDGET_START_DATE", start])
        print(f"[select-params] BUDGET_START_DATE pinned to {start}")

    cfg = wsconfig.load(env)
    rg = os.environ.get("AZURE_RESOURCE_GROUP", "").strip()
    location = cfg["names"]["location"]
    sub = os.environ.get("AZURE_SUBSCRIPTION_ID", "").strip()
    if os.environ.get("AZURE_LOCATION", location).strip() != location:
        print(f"[select-params] AZURE_LOCATION={os.environ['AZURE_LOCATION']} differs from names.location={location}. "
              f"The workshop is pinned to one region: azd env set AZURE_LOCATION {location}")
        return 1
    if not rg:
        print("[select-params] AZURE_RESOURCE_GROUP is not set (expected names.resource_group from workshop.yaml).")
        return 1
    if rg != cfg["names"]["resource_group"]:
        print(f"[select-params] AZURE_RESOURCE_GROUP={rg} differs from names.resource_group="
              f"{cfg['names']['resource_group']} in workshop.yaml (one resource group, named once).")
        return 1
    state = rg_state(rg, sub, env)
    if state == "foreign" and os.environ.get("ALLOW_EXISTING_RG") != "1":
        print(f"[select-params] resource group {rg} already exists, holds resources and is not tagged as this "
              f"workshop's (workshop=livewell, azd-env-name={env}). Refusing to reuse it. Review its contents, "
              "then pick another names.resource_group or set ALLOW_EXISTING_RG=1.")
        return 1
    if plan_mode:
        print(f"[select-params] --plan: resource group {rg} is '{state}'; nothing was created in Azure")
        return 0
    cmd = ["az", "group", "create", "-n", rg, "-l", location, "--tags", "workshop=livewell",
           f"env={env}", f"azd-env-name={env}", "-o", "none"]
    if sub:
        cmd += ["--subscription", sub]
    run(cmd)
    print(f"[select-params] resource group {rg} ready in {location} (was: {state})")
    return 0 if fabric_capacity_updatable(rg, sub, env) else 1


def fabric_capacity_updatable(rg: str, sub: str, env: str) -> bool:
    """ARM cannot update a paused Fabric capacity ("Service is not ready to be updated"), which fails the whole
    deployment after every other resource has gone through. Stop before azd starts instead."""
    if os.environ.get("FABRIC_BRIDGE", "false").strip().lower() not in ("1", "true", "yes"):
        return True
    sub = sub or run(["az", "account", "show", "--query", "id", "-o", "tsv"], check=False)
    url = (f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
           "/providers/Microsoft.Fabric/capacities?api-version=2023-11-01")
    out = run(["az", "rest", "--method", "get", "--url", url, "--subscription", sub, "--query",
               "value[].[name, properties.state]", "-o", "tsv"], check=False)
    paused = [line.split("\t")[0] for line in out.splitlines()
              if line.split("\t")[-1] in ("Paused", "Suspended")]
    if paused:
        print(f"[select-params] Fabric capacity {paused[0]} is paused and ARM cannot update it. Run "
              f"`bash scripts/capacity.sh resume {env}`, provision, then `bash scripts/capacity.sh suspend {env}`.")
        return False
    return True


if __name__ == "__main__":
    sys.exit(main())
