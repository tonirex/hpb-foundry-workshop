#!/usr/bin/env python3
"""Sync the Lab 2 guardrail from content/config/guardrails.yaml (azd postprovision hook).

Bicep creates the blocklist and the `livewell-guardrails` RAI policy, but not the blocklist items:
the Cognitive Services RP answers GET on a single raiBlocklistItems resource with HTTP 400 (LIST works),
which makes `azd provision --preview` / what-if fail on every run (ASSUMPTIONS.md 4.2). This script PUTs
each item (idempotent) and deletes items that are no longer in the YAML.

It also re-asserts the policy body and each deployment's guardrail (`deployment_policy`, or the custom policy
for names in `attach_to`), because tenant governance automation can rewrite a custom RAI policy after
provisioning. In the MCAPS tenant it happens every morning at about 09:15 SGT: the policy is replaced by a single
annotate-only "Indirect Attack" filter with no blocklist (ASSUMPTIONS.md 4.14). On the workshop day run it after
09:30 SGT and again just before Lab 2; `smoke-test.py` fails while the policy has drifted.

    python scripts/apply-guardrail.py            # reads AZURE_* from the azd env / process env
    python scripts/apply-guardrail.py --check    # report only, exit 1 on any drift
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
from azrest import Api  # noqa: E402

API = "2025-06-01"


def azd_env() -> dict:
    try:
        out = subprocess.run(["azd", "env", "get-values"], cwd=ROOT, capture_output=True, text=True,
                             timeout=60, shell=os.name == "nt").stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    vals = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"')
    return vals


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="report drift only")
    args = ap.parse_args()

    env = {**azd_env(), **{k: v for k, v in os.environ.items() if k.startswith("AZURE_")}}
    missing = [k for k in ("AZURE_SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP", "AZURE_AI_ACCOUNT_NAME") if not env.get(k)]
    if missing:
        print(f"[guardrail] missing {', '.join(missing)}; run after azd provision", file=sys.stderr)
        return 2

    cfg = yaml.safe_load((ROOT / "content" / "config" / "guardrails.yaml").read_text(encoding="utf-8"))
    bl = cfg["blocklist"]
    account = (f"/subscriptions/{env['AZURE_SUBSCRIPTION_ID']}/resourceGroups/{env['AZURE_RESOURCE_GROUP']}"
               f"/providers/Microsoft.CognitiveServices/accounts/{env['AZURE_AI_ACCOUNT_NAME']}")
    base = f"{account}/raiBlocklists/{bl['name']}"
    arm = Api("arm", subscription=env["AZURE_SUBSCRIPTION_ID"])
    if arm.get(f"{base}?api-version={API}", ok_404=True) is None:
        print(f"[guardrail] blocklist {bl['name']} not found; run azd provision first", file=sys.stderr)
        return 2

    # 1. Blocklist items.
    current = {i["name"]: i["properties"] for i in (arm.get(f"{base}/raiBlocklistItems?api-version={API}") or {}).get("value", [])}
    wanted = {i["id"]: {"pattern": i["pattern"], "isRegex": True} for i in bl["items"]}
    item_drift = [n for n, p in wanted.items() if current.get(n) != p] + [n for n in current if n not in wanted]

    # 2. Policy body (same shape as infra/modules/foundry.bicep).
    policy_url = f"{account}/raiPolicies/{cfg['policy_name']}?api-version={API}"
    policy_body = {"properties": {
        "basePolicyName": cfg["base_policy"], "mode": cfg["mode"], "contentFilters": cfg["content_filters"],
        "customBlocklists": [{"blocklistName": bl["name"], "blocking": True, "source": bl["source"]}]}}
    live = (arm.get(policy_url, ok_404=True) or {}).get("properties")
    policy_drift = policy_diff(policy_body["properties"], live)

    # 3. Deployment guardrails: the platform default, unless a deployment is listed in attach_to.
    deployments = {d["name"]: d for d in arm.get_all(f"{account}/deployments?api-version={API}")}
    attached = cfg.get("attach_to") or []
    default = cfg.get("deployment_policy") or "Microsoft.DefaultV2"
    want_policy = {n: cfg["policy_name"] if n in attached else default for n in deployments}
    attach_drift = [n for n, p in want_policy.items() if deployments[n]["properties"].get("raiPolicyName") != p]
    layout = ", ".join(f"{n}={p}" for n, p in sorted(want_policy.items()))

    print(f"[guardrail] {bl['name']}: {len(current)} items, drift={item_drift or 'none'}")
    print(f"[guardrail] policy {cfg['policy_name']}: drift={policy_drift or 'none'}")
    print(f"[guardrail] deployments {layout}: drift={attach_drift or 'none'}")
    if args.check:
        return 1 if (item_drift or policy_drift or attach_drift) else 0

    for name, props in wanted.items():
        if current.get(name) == props:
            continue
        arm.call("PUT", f"{base}/raiBlocklistItems/{name}?api-version={API}", {"properties": props})
        print(f"[guardrail] put item {name}")
    for name in current:
        if name not in wanted:
            arm.call("DELETE", f"{base}/raiBlocklistItems/{name}?api-version={API}")
            print(f"[guardrail] deleted item {name}")
    if policy_drift:
        arm.call("PUT", policy_url, policy_body)
        print(f"[guardrail] re-applied policy {cfg['policy_name']}")
    for name in attach_drift:
        d = deployments[name]
        body = {"sku": d["sku"], "properties": {**{k: v for k, v in d["properties"].items()
                                                   if k in ("model", "versionUpgradeOption", "currentCapacity")},
                                                "raiPolicyName": want_policy[name]}}
        body["properties"].pop("currentCapacity", None)
        arm.call("PUT", f"{account}/deployments/{name}?api-version={API}", body)
        print(f"[guardrail] set {name} guardrail to {want_policy[name]}")
    print(f"[guardrail] in sync: {len(wanted)} items; policy {cfg['policy_name']}; deployments {layout}")
    return 0


def policy_diff(want: dict, live: dict | None) -> list[str]:
    """Names of the policy settings that differ from the YAML (filters keyed by name + source)."""
    if live is None:
        return ["missing"]
    diff = [k for k in ("basePolicyName", "mode") if live.get(k) != want[k]]

    def filters(items):
        return {(f["name"], f["source"]): (bool(f.get("blocking")), bool(f.get("enabled")), f.get("severityThreshold"))
                for f in items or []}

    w, l = filters(want["contentFilters"]), filters(live.get("contentFilters"))
    diff += [f"{n}/{s}" for (n, s) in sorted(set(w) | set(l)) if w.get((n, s)) != l.get((n, s))]
    blocklists = {(b["blocklistName"], b["source"], bool(b.get("blocking"))) for b in live.get("customBlocklists") or []}
    if blocklists != {(b["blocklistName"], b["source"], bool(b["blocking"])) for b in want["customBlocklists"]}:
        diff.append("customBlocklists")
    return diff


if __name__ == "__main__":
    raise SystemExit(main())
