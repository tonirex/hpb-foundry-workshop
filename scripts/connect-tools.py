#!/usr/bin/env python3
"""Create the Lab 3 tool connections in the shared project (facilitator, once per environment).

  1. `livewell-activities-mcp`: RemoteTool connection (no auth, metadata type custom_MCP) to the activities
     MCP server on Container Apps (`MCP_URL`). Navigator attaches it with Tools -> Add tools -> Configured;
     lab3_tools.py references it by name.
  2. `livewell-fabric-resident360` (only when FABRIC_BRIDGE=true): RemoteTool connection with UserEntraToken
     (identity passthrough, audience https://analysis.windows.net/powerbi/api) to the published data agent's
     MCP endpoint `https://api.fabric.microsoft.com/v1/mcp/workspaces/<ws>/dataagents/<id>/agent`. The Fabric IQ
     tool (`fabric_iq_preview`) uses it, so each lab account queries Fabric as itself.
  3. `livewell-nutrition-a2a` and `livewell-activity-a2a`: RemoteA2A connections (ProjectManagedIdentity,
     audience https://ai.azure.com) to the A2A endpoints of the demo specialists `livewell-demo-nutrition` and
     `livewell-demo-activity` (`<project endpoint>/agents/<name>/endpoint/protocols/a2a`). Navigator attaches
     them in Lab 3 step 11 with Tools -> Add tools -> Configured. The agents themselves, with incoming A2A, come
     from demos/create-demo-agents.py; the project identity's Foundry Agent Consumer role from rbac.bicep.
  4. azd env: PROFILE_OPENAPI_URL (Navigator `livewell_profile` tool), FABRIC_IQ_SERVER_URL and
     FABRIC_IQ_CONNECTION_ID, then runs `scripts/render-values.py` to put them on the values sheet.
  5. Checks: /healthz, /openapi.json (operationId get_citizen_profile), /profile/me 200 and another resident 403,
     and that the Lab 3 spec block matches the live spec (scripts/sync-openapi-block.py --check; a warning only).

    python scripts/connect-tools.py            # create/update + checks
    python scripts/connect-tools.py --check    # report only
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import wsconfig  # noqa: E402
from azrest import Api, ApiError  # noqa: E402

CONN_API = "2025-10-01-preview"
FABRIC_AUDIENCE = "https://analysis.windows.net/powerbi/api"
FABRIC_HOST = "https://api.fabric.microsoft.com"
FOUNDRY_AUDIENCE = "https://ai.azure.com"
A2A_SPECIALISTS = {"nutrition": "nutrition_a2a_connection", "activity": "activity_a2a_connection"}


def log(msg: str) -> None:
    print(f"[connect-tools] {msg}", flush=True)


def azd(*args: str) -> str:
    proc = subprocess.run(["azd", *args], cwd=ROOT, capture_output=True, text=True, timeout=120,
                          shell=os.name == "nt")
    if proc.returncode != 0:
        raise SystemExit(f"[connect-tools] azd {' '.join(args[:3])} failed: {proc.stderr.strip()[:300]}")
    return proc.stdout


def azd_env() -> dict:
    vals = {}
    for line in azd("env", "get-values").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"')
    return vals


def http(url: str, timeout: int = 60) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError) as e:
        return 0, str(e)


def ensure_connection(arm: Api, project_id: str, name: str, props: dict, check: bool) -> tuple[str, str]:
    url = f"{project_id}/connections/{name}?api-version={CONN_API}"
    current = arm.get(url, ok_404=True)
    cur = (current or {}).get("properties") or {}
    same = current and all(cur.get(k) == v for k, v in props.items() if k not in ("metadata", "isSharedToAll"))
    conn_id = f"{project_id}/connections/{name}"
    if same:
        return "in sync", conn_id
    if check:
        return ("missing" if not current else "drift"), conn_id
    arm.put(url, {"properties": props})
    return ("created" if not current else "updated"), conn_id


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="report only, change nothing")
    args = ap.parse_args()

    env = azd_env()
    for key in ("AZURE_AI_PROJECT_ID", "MCP_URL"):
        if not env.get(key):
            raise SystemExit(f"[connect-tools] {key} missing in the azd env; run azd provision first")
    cfg = wsconfig.load(env.get("AZURE_ENV_NAME"))
    names = cfg["names"]
    fabric = (env.get("FABRIC_BRIDGE") or str(cfg["modes"]["fabric_bridge"])).lower() == "true"
    arm = Api("arm")
    rows: list[tuple[str, str, str]] = []
    ok = True

    mcp_url = env["MCP_URL"]
    base = mcp_url.rsplit("/mcp", 1)[0]
    profile_url = f"{base}/openapi.json"

    state, _ = ensure_connection(arm, env["AZURE_AI_PROJECT_ID"], names["mcp_connection"], {
        "category": "RemoteTool", "authType": "None", "target": mcp_url, "isSharedToAll": True,
        "metadata": {"type": "custom_MCP"}}, args.check)
    rows.append(("MCP connection", names["mcp_connection"], state))
    ok &= state in ("in sync", "created", "updated")

    # A2A specialists: the calling coach authenticates as the project's managed identity, so one connection
    # serves every participant's agent. A2A must be on for the agents (create-demo-agents.py) before the
    # connections answer; creating the connections first is fine.
    endpoint = env.get("AZURE_AI_PROJECT_ENDPOINT", "").rstrip("/")
    demo_agents = cfg["workshop"]["agent_naming"]["demo_agents"]
    for role, key in A2A_SPECIALISTS.items():
        if not endpoint:
            rows.append(("A2A connection", names[key], "SKIP: AZURE_AI_PROJECT_ENDPOINT not set"))
            ok = False
            continue
        state, _ = ensure_connection(arm, env["AZURE_AI_PROJECT_ID"], names[key], {
            "category": "RemoteA2A", "authType": "ProjectManagedIdentity", "audience": FOUNDRY_AUDIENCE,
            "target": f"{endpoint}/agents/{demo_agents[role]}/endpoint/protocols/a2a", "isSharedToAll": True,
            "metadata": {"ApiType": "Azure"}}, args.check)
        rows.append(("A2A connection", names[key], state))
        ok &= state in ("in sync", "created", "updated")

    if fabric:
        ws, agent = env.get("FABRIC_WORKSPACE_ID"), env.get("FABRIC_DATA_AGENT_ID")
        if not (ws and agent):
            rows.append(("Fabric IQ connection", names["fabric_connection"], "SKIP: FABRIC_DATA_AGENT_ID not set (Phase 3)"))
            ok = False
        else:
            fabric_url = f"{FABRIC_HOST}/v1/mcp/workspaces/{ws}/dataagents/{agent}/agent"
            state, conn_id = ensure_connection(arm, env["AZURE_AI_PROJECT_ID"], names["fabric_connection"], {
                "category": "RemoteTool", "authType": "UserEntraToken", "target": fabric_url,
                "audience": FABRIC_AUDIENCE, "isSharedToAll": True,
                "metadata": {"type": "fabric_iq_dataagent"}}, args.check)
            rows.append(("Fabric IQ connection", names["fabric_connection"], state))
            ok &= state in ("in sync", "created", "updated")
            if not args.check:
                if env.get("FABRIC_IQ_CONNECTION_ID") != conn_id:
                    azd("env", "set", "FABRIC_IQ_CONNECTION_ID", conn_id)
                if env.get("FABRIC_IQ_SERVER_URL") != fabric_url:
                    azd("env", "set", "FABRIC_IQ_SERVER_URL", fabric_url)
    else:
        rows.append(("Fabric IQ connection", names["fabric_connection"], "skipped (FABRIC_BRIDGE=false)"))

    if not args.check and env.get("PROFILE_OPENAPI_URL") != profile_url:
        azd("env", "set", "PROFILE_OPENAPI_URL", profile_url)

    code, body = http(f"{base}/healthz", timeout=90)  # first call may cold-start the container
    rows.append(("MCP /healthz", base.split("//")[1][:40], f"{'PASS' if code == 200 else 'FAIL'} {body[:60]}"))
    ok &= code == 200
    code, body = http(profile_url)
    try:
        op = json.loads(body)["paths"]["/profile/{resident_id}"]["get"]["operationId"]
    except (ValueError, KeyError, TypeError):
        op = ""
    rows.append(("Profile OpenAPI", "/openapi.json", f"{'PASS' if op == 'get_citizen_profile' else 'FAIL'} operationId={op or '?'}"))
    ok &= op == "get_citizen_profile"
    me, _ = http(f"{base}/profile/me")
    other, _ = http(f"{base}/profile/RESIDENT_00062")
    good = me == 200 and other == 403
    rows.append(("Profile scope", "me / another resident", f"{'PASS' if good else 'FAIL'} {me} / {other}"))
    ok &= good
    # Navigators copy the spec, with this server's address, from the Lab 3 pages: warn when the block is stale.
    env_name = env.get("AZURE_ENV_NAME", "")
    sync = subprocess.run([sys.executable, str(ROOT / "scripts" / "sync-openapi-block.py"), env_name, "--check"],
                          cwd=ROOT, capture_output=True, text=True, check=False)
    last = ((sync.stdout + sync.stderr).strip().splitlines() or [""])[-1].replace("[sync-openapi-block] ", "")
    rows.append(("Lab 3 spec block", "content/labs/lab-03*.md", "in sync" if sync.returncode == 0 else f"WARN {last[:120]}"))

    w = max(len(r[0]) for r in rows)
    for r in rows:
        print(f"  {r[0]:<{w}}  {r[1]:<30}  {r[2]}")
    if not args.check:
        rendered = subprocess.run([sys.executable, str(ROOT / "scripts" / "render-values.py"), env.get("AZURE_ENV_NAME", "")],
                                  cwd=ROOT, check=False).returncode == 0
        if not rendered:
            log("values sheet not refreshed: run python scripts/render-values.py")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ApiError as e:
        raise SystemExit(f"[connect-tools] {e}")
