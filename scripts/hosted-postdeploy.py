#!/usr/bin/env python3
"""Finish a livewell-workshop-hosted deploy: agent-identity RBAC + livewell-guardrails (azd postdeploy hook).

Two things `azd deploy livewell-workshop-hosted` cannot do from azure.yaml:

1. RBAC. Each hosted agent runs as its own Entra agent identity, created on the first deploy. It needs
   Foundry User (Azure AI User) on the project to call the model deployments and read the knowledge-base
   and activities connections. Without it the container exits at start-up and invokes fail with 424
   session_not_ready. Same role and scope as attendees (workshop.yaml rbac_roles.foundry_user).
2. Guardrail. The azd AI agents extension sends `policies[].raiPolicyName` verbatim for hosted agents (no
   ${VAR} expansion) and the service needs the FULL resource ID, which differs per tenant. So azure.yaml
   has no `policies` block; this script publishes a new version with the same code zip and definition
   plus rai_config = the full ID of livewell-guardrails when the latest version lacks it (ASSUMPTIONS.md).

    python scripts/hosted-postdeploy.py            # grant + attach if needed (idempotent)
    python scripts/hosted-postdeploy.py --check    # report only; exit 1 if either is missing
    python scripts/hosted-postdeploy.py --verify   # also send a blocklisted prompt: must be blocked (HTTP 400)
"""
from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.parse import quote

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "content" / "assets"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from common import livewell_common as lw  # noqa: E402

BLOCKED_PROMPT = "lab2_medication_double"  # the medication-dosage blocklist stops it at the input
RA_API = "api-version=2022-04-01"
NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/tonirex/livewell-foundry-workshop/hosted-agent")


def log(msg: str, err: bool = False) -> None:
    print(f"[hosted-postdeploy] {msg}", file=sys.stderr if err else sys.stdout, flush=True)


def ensure_role(principal_id: str, check: bool) -> bool:
    """Foundry User on the project for the agent identity. Returns True when the grant exists."""
    from azrest import Api, ApiError

    arm = Api("arm")
    account = lw.account_id()
    scope = f"{account}/projects/{lw.endpoint().rsplit('/', 1)[-1]}"
    sub = account.split("/")[2]
    role_def = (f"/subscriptions/{sub}/providers/Microsoft.Authorization/roleDefinitions/"
                f"{lw.config()['rbac_roles']['foundry_user']}")
    flt = quote(f"principalId eq '{principal_id}'")
    existing = arm.get_all(f"{scope}/providers/Microsoft.Authorization/roleAssignments?{RA_API}&$filter={flt}")
    if any(a["properties"]["roleDefinitionId"].lower() == role_def.lower() for a in existing):
        log(f"agent identity {principal_id}: Foundry User on the project")
        return True
    if check:
        log(f"agent identity {principal_id} has no Foundry User on the project", err=True)
        return False
    name = uuid.uuid5(NS, f"{scope.lower()}|{principal_id}|foundry_user")
    body = {"properties": {"roleDefinitionId": role_def, "principalId": principal_id,
                           "principalType": "ServicePrincipal"}}
    for attempt in range(6):  # a brand-new agent identity can take a minute to replicate
        try:
            arm.put(f"{scope}/providers/Microsoft.Authorization/roleAssignments/{name}?{RA_API}", body)
            break
        except ApiError as e:
            if e.code == "RoleAssignmentExists":
                break
            if e.code != "PrincipalNotFound" or attempt == 5:
                raise
            time.sleep(15)
    log(f"agent identity {principal_id}: Foundry User granted on the project (allow ~2 min to propagate)")
    return True


def wait_active(name: str, version: str, timeout: float = 900) -> str:
    status, start = "", time.time()
    while time.time() - start < timeout:
        v = lw.project().agents.get_version(agent_name=name, agent_version=version)
        raw = getattr(v, "status", "") or ""
        status = str(getattr(raw, "value", raw)).lower()
        if status in ("active", "failed", "deleted"):
            return status
        time.sleep(10)
    return status or "timeout"


def republish_code(name: str, version: str, definition, description, metadata):
    """Code-deployed versions only accept multipart/form-data, so re-upload the same code zip."""
    agents = lw.project().agents
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = pathlib.Path(tmp) / f"{name}-v{version}.zip"
        zip_path.write_bytes(b"".join(agents.download_code(agent_name=name, agent_version=version)))

        def create():
            with zip_path.open("rb") as code:
                return agents.create_version_from_code(
                    agent_name=name, definition=definition, code=code,
                    description=description, metadata=metadata)

        return lw.retry(create, what=f"new version of {name}")


def ensure_guardrail(name: str, latest, check: bool) -> bool:
    policy = lw.rai_policy_id(lw.NAMES["rai_policy"])
    current = getattr(getattr(latest.definition, "rai_config", None), "rai_policy_name", None) or ""
    if current == policy:
        log(f"{name} v{latest.version}: {lw.NAMES['rai_policy']} attached")
        return True
    if check:
        log(f"{name} v{latest.version}: guardrail is '{current or 'none'}', expected {lw.NAMES['rai_policy']}",
            err=True)
        return False
    definition = latest.definition
    definition.rai_config = lw.models().RaiConfig(rai_policy_name=policy)
    new = republish_code(name, str(latest.version), definition, latest.description, latest.metadata)
    log(f"{name} v{new.version}: {lw.NAMES['rai_policy']} attached; waiting for it to become active")
    status = wait_active(name, str(new.version))
    log(f"{name} v{new.version}: {status}", err=status != "active")
    return status == "active"


def record_version(name: str, version: str) -> None:
    key = f"AGENT_{name.upper().replace('-', '_')}_VERSION"
    result = subprocess.run([shutil.which("azd") or "azd", "env", "set", key, version], cwd=ROOT,
                            env={**os.environ, "AZURE_DEV_USER_AGENT": "microsoft_foundry_skill"},
                            capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(f"could not record guarded agent version in azd: {result.stderr.strip()[:300]}")
    log(f"azd now tracks {name} v{version}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="report only; exit 1 if RBAC or the guardrail is missing")
    ap.add_argument("--verify", action="store_true", help="send a blocklisted prompt; it must be blocked")
    args = ap.parse_args()

    name = lw.NAMES["hosted_agent"]
    latest = lw.agent_by_name(name)
    if latest is None:
        log(f"{name} is not deployed; run azd deploy {name}", err=True)
        return 2
    principal = (getattr(latest, "instance_identity", None) or {}).get("principal_id")
    ok = ensure_role(principal, args.check) if principal else True
    if not principal:
        log(f"{name} v{latest.version} reports no agent identity; skipping RBAC", err=True)
    ok = ensure_guardrail(name, latest, args.check) and ok
    if not ok:
        return 1

    if not args.check:
        guarded = lw.agent_by_name(name)
        if guarded is None:
            log(f"{name} cannot be read after guardrail attachment", err=True)
            return 1
        record_version(name, str(guarded.version))

    if args.verify:
        run = lw.ask(name, prompt_id=BLOCKED_PROMPT, consent=False)
        if not run.blocked:
            log(f"verify FAILED: '{BLOCKED_PROMPT}' was answered: {lw._trunc(run.text, 200)}", err=True)
            return 1
        log(f"verify: '{BLOCKED_PROMPT}' blocked ({run.block_reason}) in {run.seconds:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
