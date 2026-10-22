#!/usr/bin/env python3
"""Render content/config/values.md (gitignored) from .azure/<env>/.env + content/config/workshop.yaml.

    python scripts/render-values.py [env]          # default: the selected azd env

The values sheet is what facilitators put on screen at T-0 (SPEC.md §12.1): project endpoint, agent and
resource names, lab-account pattern, Wi-Fi. Lab pages only ever use NAMES; runtime values live here.
Missing values (e.g. Fabric IDs before Phase 3) render as "(not yet provisioned)".

It is regenerated automatically after every deploy: the azd postprovision and postdeploy hooks
(azure.yaml), scripts/provision.sh, scripts/fabric/deploy.sh and scripts/connect-tools.py all call it.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import wsconfig  # noqa: E402

MISSING = "(not yet provisioned)"


def selected_env() -> str:
    try:
        out = subprocess.run(["azd", "env", "list", "--output", "json"], capture_output=True, text=True,
                             shell=os.name == "nt").stdout
        import json
        for e in json.loads(out or "[]"):
            if e.get("IsDefault"):
                return e["Name"]
    except (OSError, ValueError):
        pass
    return ""


def read_env(env: str) -> dict[str, str]:
    path = ROOT / ".azure" / env / ".env"
    if not path.exists():
        raise SystemExit(f"[render-values] {path.relative_to(ROOT)} not found (run scripts/provision.sh {env})")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition("=")
            values[k.strip()] = v.strip().strip('"')
    return values


def main() -> int:
    env = (sys.argv[1] if len(sys.argv) > 1 else "") or os.environ.get("AZURE_ENV_NAME", "") or selected_env()
    if not env:
        print("[render-values] usage: python scripts/render-values.py <env>")
        return 1
    cfg = wsconfig.load(env)
    v = read_env(env)
    names, models, ws = cfg["names"], cfg["models"], cfg["workshop"]
    env_cfg = cfg["environments"].get(env, {})
    lab = env_cfg.get("lab_accounts", {})
    tenant_domain = ""
    for upn in env_cfg.get("facilitator_upns", []):
        if "@" in upn:
            tenant_domain = upn.split("@", 1)[1]
            break

    def g(key: str) -> str:
        return v.get(key) or MISSING

    def portal_link() -> str:
        pid = v.get("AZURE_AI_PROJECT_ID")
        return f"https://ai.azure.com/resource/overview?wsid={pid}" if pid else MISSING

    def hosted() -> str:
        # Name only: the postdeploy hook publishes a newer version than the one azd records in .env.
        return v.get("AGENT_LIVEWELL_WORKSHOP_HOSTED_NAME") or MISSING

    count = int(lab.get("count", 20) or 20)
    prefix = lab.get("prefix", "hpb.lab")
    at_domain = f" @ {tenant_domain}" if tenant_domain else ""
    if lab.get("naming") == "named":
        accounts = f"firstname.lastname{at_domain} (on each participant's sign-in card)"
    else:
        accounts = f"{prefix}01 ... {prefix}{count:02d}{at_domain}"
    fabric_ws_url = v.get("FABRIC_WORKSPACE_URL") or MISSING
    devui_on = (v.get("LAB4_DEVUI") or "true").strip().lower() in ("1", "true", "yes")
    devui_off = "not deployed (LAB4_DEVUI=false)"
    # Owner or Contributor can read the token themselves (listSecrets); Foundry User cannot. Lab 4 step 1.
    devui_cmd = (f"`az containerapp secret show -n {v.get('LAB4_DEVUI_APP_NAME') or names['devui_app']}"
                 f" -g {v.get('AZURE_RESOURCE_GROUP') or names['resource_group']}"
                 f" --subscription {g('AZURE_SUBSCRIPTION_ID')}"
                 " --secret-name devui-auth-token --query value -o tsv`")

    rows = [
        ("Environment", env),
        ("Region", g("AZURE_LOCATION")),
        ("Subscription", g("AZURE_SUBSCRIPTION_ID")),
        ("Foundry portal", "https://ai.azure.com"),
        ("Project", f"{names['foundry_project']} (resource {g('AZURE_AI_ACCOUNT_NAME')})"),
        ("Project endpoint", g("AZURE_AI_PROJECT_ENDPOINT")),
        ("Project deep link", portal_link()),
        ("Model deployment (Labs 0-2, specialists)", models["default"]),
        ("Tools model deployment (Lab 3 coach on)", models["tools"]),
        ("Embedding deployment", models["embeddings"]),
        ("Knowledge base", names["knowledge_base"]),
        ("Search service", g("AZURE_SEARCH_SERVICE_NAME")),
        ("Activities MCP server", g("MCP_URL")),
        ("MCP project connection", names["mcp_connection"]),
        ("Profile OpenAPI spec URL (Lab 3)", g("PROFILE_OPENAPI_URL")),
        ("Fabric workspace", f"{names['fabric_workspace']} — {fabric_ws_url}"),
        ("Fabric data agent", names["data_agent"]),
        ("Fabric IQ connection", v.get("FABRIC_IQ_CONNECTION_ID") and names["fabric_connection"] or MISSING),
        ("Your agent name", ws["agent_naming"]["portal_agent"] + "  (Navigator)"),
        ("Builder agents", ws["agent_naming"]["builder_agent"] + "  (Builder)"),
        ("Hosted agent (Lab 4, facilitator)", hosted()),
        ("Lab 4 DevUI (browser, no install)", g("LAB4_DEVUI_URL") if devui_on else devui_off),
        ("Lab 4 DevUI token", g("LIVEWELL_DEVUI_TOKEN") if devui_on else devui_off),
        ("Lab 4 DevUI token command (Owner or Contributor)", devui_cmd if devui_on else devui_off),
        ("Workshop accounts", accounts),
        ("Guest Wi-Fi", f"{ws['guest_wifi']['ssid']} / {ws['guest_wifi']['code']}"),
    ]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# LiveWell Coach — values sheet ({env})",
        "",
        f"<!-- GENERATED by scripts/render-values.py from .azure/{env}/.env at {now}. Do not commit. -->",
        "",
        f"Workshop date: {ws['date']}",
        "",
        "| What | Value |",
        "|---|---|",
    ]
    lines += [f"| {k} | {val} |" for k, val in rows]
    lines += [
        "",
        "Sign in to https://ai.azure.com with your own workshop account (the username on your sign-in card), open",
        "the project above, and name every agent you create with your initials. Ask a facilitator if the project",
        "does not appear.",
        "",
    ]
    out = ROOT / "content" / "config" / "values.md"
    out.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"[render-values] wrote {out.relative_to(ROOT).as_posix()} ({len(rows)} values, "
          f"{sum(1 for _, x in rows if MISSING in x)} not yet provisioned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
