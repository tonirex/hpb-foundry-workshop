#!/usr/bin/env python3
"""End-to-end smoke test (facilitator, T-3 after provisioning and T-0 before doors open). SPEC.md §11.2.

Builds temporary portal-style agents `livewell-smoke-*` from the same definitions as the demo agents
(demos/create-demo-agents.py), asks one question per capability in parallel, deletes the agents, and prints
a pass/fail table plus the total cost since provision (Cost Management, resource group scope):

  * MCP server        /healthz answers (the Container App scales to zero; the first call wakes it)
  * Knowledge         lab1_prediabetes_eat searches the knowledge base and cites a real guide
  * Guardrail         lab2_injected_flyer is blocked, or safely refused, under livewell-guardrails;
                      lab2_medication_double is blocked by the blocklist (the default never blocks it); and
                      `apply-guardrail.py --check` finds no drift (tenant governance can reset the policy)
  * Tools             lab3_hazy_indoor_signup fires >= 2 tools (livewell_profile + find_activities);
                      discovery must stay read-only; an unexpected approval is denied and fails the check
  * Specialists       a temporary coach with the livewell-nutrition-a2a / livewell-activity-a2a tools asks
                      lab3_specialists and both A2A calls complete (Lab 3 Navigator step 11; also with --demo-agents)
  * Fabric bridge     fabric_q_disengaged_regions calls Fabric IQ and ranks the reference top region first
                      (+-1); lab1_prediabetes_eat on the same agent does NOT call Fabric (FABRIC_BRIDGE only)
  * Hosted agent      livewell-workshop-hosted (if deployed) answers lab4_week_plan_handoff with evidence
                      JSON that cites a guide, under livewell-guardrails
  * Demo memory       your scope in livewell-demo-memory holds no red-team attack summaries
                      (scripts/reset-demo-memory.py; they make the Lab 3 demo agents trip the content filter)

    python scripts/smoke-test.py                   # temporary agents, ~3-5 min
    python scripts/smoke-test.py --demo-agents     # T-0: test the livewell-demo-* agents (never deleted)
    python scripts/smoke-test.py --no-fabric --no-hosted --since 2026-09-01 --report demos/runs/smoke.md

Needs the facilitator's azd env (AZURE_ENV_NAME) and Cost Management Reader (or Reader) on the resource
group. Exit code 1 if any check fails or a temporary agent is left behind.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "content" / "assets"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
os.environ["INITIALS"] = "smoke"
os.environ.setdefault("LIVEWELL_AUTO_APPROVE", "1")

from common import livewell_common as lw  # noqa: E402

COST_API = "2023-11-01"


def demo_module():
    spec = importlib.util.spec_from_file_location("create_demo_agents", ROOT / "demos" / "create-demo-agents.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def no_resident_id(text: str) -> bool:
    return not re.search(r"RESIDENT_\d+", text or "")


def outcome(run) -> str:
    if run.blocked:
        return f"BLOCKED ({run.block_reason})"
    try:
        return f"answered, route={run.json().get('route')}"
    except ValueError:
        return "answered (not JSON)"


# --- checks -------------------------------------------------------------------------------------------
# Each returns a list of (check, ok, detail). ok=None means skipped.
def check_mcp() -> list:
    url = lw.connection(lw.NAMES["mcp_connection"]).target.rstrip("/").removesuffix("/mcp") + "/healthz"
    start = time.time()
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except (urllib.error.URLError, TimeoutError) as e:
        code = str(e)[:60]
    return [("MCP server /healthz", code == 200, f"{code} in {time.time() - start:.0f}s")]


def check_knowledge(agent) -> list:
    run = lw.ask(agent, prompt_id="lab1_prediabetes_eat")
    want = lw.expected("lab1_prediabetes_eat").get("cited_sources_any") or ["lg-05-eating-for-pre-diabetes"]
    invented = lw.invented_guides(run)
    return [("Knowledge: guide question cites a KB doc",
             run.kb_called and bool(set(want) & set(run.citations)) and not invented,
             f"kb={'yes' if run.kb_called else 'no'}, cites {', '.join(run.citations) or 'nothing'}"
             + (f", invented {invented}" if invented else "") + f" ({run.seconds:.0f}s)")]


def check_guardrail(agent) -> list:
    row = next(r for r in lw.load_eval_rows() if r.get("source_prompt_id") == "lab2_injected_flyer")
    run = lw.ask(agent, prompt_id="lab2_injected_flyer")
    policy = lw.rai_policy_of(agent)
    rows = [("Guardrail: injected flyer blocked or refused",
             policy == lw.NAMES["rai_policy"] and lw.safe_outcome(run, row),
             f"{outcome(run)} under {policy or 'deployment default'} ({run.seconds:.0f}s)")]
    # The flyer is blocked by the platform default too, so it can't tell whether the custom policy is intact.
    # The blocklist can: tenant governance has been seen to strip it (ASSUMPTIONS.md 4.14).
    med = lw.ask(agent, prompt_id="lab2_medication_double")
    rows.append(("Guardrail: blocklist blocks lab2_medication_double",
                 med.blocked and "blocklist" in (med.block_reason or ""),
                 f"{outcome(med)} ({med.seconds:.0f}s)"
                 + ("" if med.blocked else "; policy reset? python scripts/apply-guardrail.py")))
    return rows


def check_guardrail_config() -> list:
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / "apply-guardrail.py"), "--check"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8", timeout=300)
    if res.returncode == 0:
        detail = "in sync"
    else:
        drift = [ln.removeprefix("[guardrail] ") for ln in res.stdout.splitlines()
                 if "drift=" in ln and "drift=none" not in ln]
        last = (res.stdout + res.stderr).strip().splitlines()
        detail = ("; ".join(drift) or (last[-1] if last else f"exit {res.returncode}")) \
            + "; fix: python scripts/apply-guardrail.py"
    return [("Guardrail: livewell-guardrails matches guardrails.yaml", res.returncode == 0, detail)]


def check_tools(agent, attempts: int = 2) -> list:
    # One retry: the model occasionally answers the discovery question from the KB + profile alone.
    for attempt in range(1, attempts + 1):
        run = lw.ask(agent, prompt_id="lab3_hazy_indoor_signup", approve=False)
        names = sorted({c.name for c in run.tool_calls if c.kind in ("openapi_call", "mcp_call", "function_call")})
        profile = any(n.endswith("get_citizen_profile") for n in names)
        wrote = any(c.name == "register_interest" and c.kind == "mcp_call" for c in run.tool_calls)
        ok = (profile and "find_activities" in names and run.called("knowledge_base_retrieve")
              and len(names) >= 2 and not run.approvals and not wrote and no_resident_id(run.text))
        if ok or wrote or run.approvals:
            break
    retry = f", attempt {attempt}/{attempts}" if attempt > 1 else ""
    return [("Tools: compound question fires >= 2 tools", ok,
             f"{', '.join(names) or 'no tools'}; {len(run.approvals)} approval request(s)"
             f"{' denied' if run.approvals else ''} ({run.seconds:.0f}s{retry})")]


def check_specialists(demo, created: list, attempts: int = 3) -> list:
    """A temporary Lab 3 coach with the two A2A tools asks lab3_specialists; both specialists must answer."""
    label = "Specialists: coach calls both over A2A"
    names = demo.demo_names()
    missing = [names[r] for r in demo.SPECIALISTS if lw.agent_by_name(names[r]) is None]
    if missing:
        return [(label, False, f"{', '.join(missing)} missing: python demos/create-demo-agents.py")]
    try:
        a2a = lw.specialist_a2a_tools()
    except Exception as e:
        return [(label, False, f"A2A connection missing ({lw._trunc(e, 60)}): python scripts/connect-tools.py")]
    kwargs, _ = demo.definition("tools", memory=False)
    kwargs["tools"] = kwargs["tools"] + a2a
    name = lw.agent_name("specialists")
    created.append(name)
    _, agent = demo.upsert(name, kwargs, "Smoke test (specialists over A2A)", rail="smoke")
    want = {lw.NAMES["nutrition_a2a_connection"], lw.NAMES["activity_a2a_connection"]}
    for attempt in range(1, attempts + 1):  # two retries: the coach sometimes plans from the KB alone
        run = lw.ask(agent, prompt_id="lab3_specialists", approve=False)
        calls = {c.name for c in run.tool_calls if c.kind.startswith("a2a") and not c.error}
        ok = want <= calls and not run.blocked
        if ok:
            break
    retry = f", attempt {attempt}/{attempts}" if attempt > 1 else ""
    return [(label, ok, f"{', '.join(sorted(calls)) or 'no A2A calls'}; "
                        f"{f'BLOCKED ({run.block_reason})' if run.blocked else 'answered'} ({run.seconds:.0f}s{retry})")]


def fabric_capacity_state() -> str:
    cap = os.environ.get("FABRIC_CAPACITY_ID", "")
    if not cap:
        return "unknown"
    from azrest import Api

    body = Api("arm").get(f"{cap}?api-version=2023-11-01", ok_404=True) or {}
    return (body.get("properties") or {}).get("state", "not found")


def check_fabric(agent) -> list:
    state = fabric_capacity_state()
    if state not in ("Active", "unknown"):
        msg = f"capacity {state}: bash scripts/capacity.sh resume {os.environ.get('AZURE_ENV_NAME', '<env>')}"
        return [("Fabric: Mei's question calls Fabric IQ", False, msg),
                ("Fabric: Rahim's question stays off Fabric", False, msg)]
    mei = lw.ask(agent, prompt_id="fabric_q_disengaged_regions", approve=False, timeout=lw.FABRIC_TIMEOUT)
    reference = json.loads((lw.CONTENT / "fabric" / "reference-answers.json").read_text(encoding="utf-8"))
    ranked = [r["region"] for r in sorted(reference["q_disengaged_regions"]["rows"], key=lambda r: -r["share_pct"])]
    first = re.search(r"\b(North[- ]East|North|West|Central|East)\b", lw.ascii_safe(mei.text))
    top = first.group(1).replace(" ", "-") if first else None
    rahim = lw.ask(agent, prompt_id="lab1_prediabetes_eat", approve=False)
    return [("Fabric: Mei's question calls Fabric IQ",
             mei.fabric_called and top in ranked[:2] and no_resident_id(mei.text),
             f"fabric={'yes' if mei.fabric_called else 'no'}, top region {top} (reference {', '.join(ranked[:3])}) "
             f"({mei.seconds:.0f}s)"),
            ("Fabric: Rahim's question stays off Fabric", not rahim.fabric_called and rahim.kb_called,
             f"tools {', '.join(sorted(set(rahim.tool_names))) or 'none'} ({rahim.seconds:.0f}s)")]


def check_memory() -> list:
    """Your scope in the demo memory store must not hold red-team attack summaries (ASSUMPTIONS 5.22)."""
    spec = importlib.util.spec_from_file_location("reset_demo_memory", ROOT / "scripts" / "reset-demo-memory.py")
    mem = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mem)
    found = mem.scope_memories()
    flagged = mem.residue(found)
    return [("Demo memory: no red-team residue in your scope", not flagged,
             f"{len(found)} memories, {len(flagged)} flagged"
             + ("; python scripts/reset-demo-memory.py --reset" if flagged else ""))]


def check_hosted() -> list:
    import openai

    agent = lw.agent_by_name(lw.NAMES["hosted_agent"])
    if agent is None:
        return [("Hosted endpoint: JSON with a citation", None, f"{lw.NAMES['hosted_agent']} not deployed")]
    policy = lw.rai_policy_of(agent)
    try:
        run = lw.ask(agent, prompt_id="lab4_week_plan_handoff", consent=False)
    except openai.APIStatusError as e:
        return [("Hosted endpoint: JSON with a citation", False, f"HTTP {e.status_code}: {lw._trunc(e.message, 80)}")]
    try:
        data = run.json()
    except ValueError:
        data = {}
    return [("Hosted endpoint: JSON with a citation",
             bool(data.get("advice")) and bool(run.citations) and policy == lw.NAMES["rai_policy"]
             and no_resident_id(run.text),
             f"v{agent.version}, {'JSON' if data else 'not JSON'}, cites {', '.join(run.citations) or 'nothing'}, "
             f"guardrail {policy or 'none'} ({run.seconds:.0f}s)")]


# --- cost since provision -------------------------------------------------------------------------------
def provision_date(arm, sub: str, rg: str) -> str:
    resources = arm.get_all(f"/subscriptions/{sub}/resourceGroups/{rg}/resources?$expand=createdTime"
                            f"&api-version=2021-04-01")
    dates = sorted(r["createdTime"][:10] for r in resources if r.get("createdTime"))
    return dates[0] if dates else (os.environ.get("BUDGET_START_DATE") or dt.date.today().replace(day=1).isoformat())


def cost_since_provision(since: str | None) -> dict:
    from azrest import Api, ApiError

    sub, rg = os.environ.get("AZURE_SUBSCRIPTION_ID"), os.environ.get("AZURE_RESOURCE_GROUP")
    if not (sub and rg):
        return {"error": "AZURE_SUBSCRIPTION_ID / AZURE_RESOURCE_GROUP missing from the azd env"}
    try:
        arm = Api("arm")
        since = since or provision_date(arm, sub, rg)
        body = {"type": "ActualCost", "timeframe": "Custom",
                "timePeriod": {"from": f"{since}T00:00:00Z", "to": f"{dt.date.today():%Y-%m-%d}T23:59:59Z"},
                "dataset": {"granularity": "None",
                            "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
                            "grouping": [{"type": "Dimension", "name": "ServiceName"}]}}
        q = arm.post(f"/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CostManagement/query"
                     f"?api-version={COST_API}", body) or {}
    except (ApiError, SystemExit) as e:
        return {"error": lw._trunc(e, 200), "since": since}
    props = q.get("properties") or {}
    cols = [c["name"] for c in props.get("columns", [])]
    services, currency = [], "USD"
    for row in props.get("rows", []):
        rec = dict(zip(cols, row))
        currency = rec.get("Currency", currency)
        services.append((rec.get("ServiceName") or "(other)", float(rec.get("Cost", 0))))
    services.sort(key=lambda s: -s[1])
    return {"since": since, "rg": rg, "currency": currency, "total": sum(c for _, c in services),
            "services": services}


def cost_lines(cost: dict) -> list[str]:
    if "error" in cost:
        return [f"Cost since provision: unavailable ({cost['error']})"]
    top = ", ".join(f"{name} {c:,.2f}" for name, c in cost["services"][:6] if c >= 0.01) or "nothing billed yet"
    return [f"Cost since provision ({cost['since']}, resource group {cost['rg']}): "
            f"**{cost['currency']} {cost['total']:,.2f}**",
            f"By service: {top}. Cost Management lags usage by 8-24 hours."]


# --- main -----------------------------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--demo-agents", action="store_true", help="test the livewell-demo-* agents instead of "
                    "temporary ones (run demos/create-demo-agents.py first)")
    ap.add_argument("--fabric", action="store_true", help="force the Fabric checks on (default: FABRIC_BRIDGE)")
    ap.add_argument("--no-fabric", action="store_true", help="skip the Fabric checks")
    ap.add_argument("--no-hosted", action="store_true", help="skip the hosted-agent check")
    ap.add_argument("--since", help="cost window start YYYY-MM-DD (default: oldest resource in the group)")
    ap.add_argument("--report", help="also write the markdown report here (default: content/assets/.runs/)")
    args = ap.parse_args()

    fabric = not args.no_fabric and lw.fabric_enabled(args.fabric)
    demo = demo_module()
    names = demo.demo_names()
    roles = ["knowledge", "guarded", "tools"] + (["fabric"] if fabric else [])
    agents: dict = {}
    created: list[str] = []
    start = time.time()
    print(f"[smoke] env {os.environ.get('AZURE_ENV_NAME', '?')}, "
          f"{'demo agents' if args.demo_agents else 'temporary livewell-smoke-* agents'}, "
          f"Fabric {'on' if fabric else 'off'}", flush=True)
    lw.warm_activities()
    try:
        for role in roles:
            if args.demo_agents:
                agents[role] = lw.agent_by_name(names[role])
                if agents[role] is None:
                    raise SystemExit(f"[smoke] {names[role]} not found: python demos/create-demo-agents.py")
            else:
                kwargs, description = demo.definition(role, memory=False)
                name = lw.agent_name(role)
                created.append(name)
                _, agents[role] = demo.upsert(name, kwargs, f"Smoke test ({role})", rail="smoke")
        print(f"[smoke] agents: {', '.join(f'{a.name} v{a.version}' for a in agents.values())}", flush=True)

        jobs = {"mcp": check_mcp, "knowledge": lambda: check_knowledge(agents["knowledge"]),
                "guarded": lambda: check_guardrail(agents["guarded"]), "guardrail-config": check_guardrail_config,
                "tools": lambda: check_tools(agents["tools"]), "memory": check_memory,
                "specialists": lambda: check_specialists(demo, created)}
        if fabric:
            jobs["fabric"] = lambda: check_fabric(agents["fabric"])
        if not args.no_hosted:
            jobs["hosted"] = check_hosted
        jobs["cost"] = lambda: cost_since_provision(args.since)
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = {k: pool.submit(fn) for k, fn in jobs.items()}
            results = {}
            for k, f in futures.items():
                try:
                    results[k] = f.result()
                except Exception as e:  # one broken capability must not hide the others
                    results[k] = [(f"{k}: crashed", False, f"{type(e).__name__}: {lw._trunc(e, 160)}")]
                print(f"[smoke] {k} done", flush=True)
    finally:
        left = []
        if created:
            lw.cleanup(created)
            left = [a.name for a in lw.project().agents.list() if a.name.startswith("livewell-smoke-")]

    rows = [r for k in jobs if k != "cost" for r in results[k]]
    if not fabric:
        rows.append(("Fabric bridge", None, "FABRIC_BRIDGE off"))
    cost = results["cost"] if isinstance(results["cost"], dict) else {"error": str(results["cost"])}
    mark = {True: "PASS", False: "FAIL", None: "SKIP"}
    lines = [f"# Smoke test - {dt.date.today():%Y-%m-%d}", "",
             f"`python scripts/smoke-test.py{' --demo-agents' if args.demo_agents else ''}` against "
             f"AZURE_ENV_NAME={os.environ.get('AZURE_ENV_NAME', '?')}, "
             f"{'livewell-demo-* agents' if args.demo_agents else 'temporary livewell-smoke-* agents'}, "
             f"Fabric {'on' if fabric else 'off'}, {time.time() - start:.0f} s.", "",
             "| Check | Result | Detail |", "|---|---|---|"]
    lines += [f"| {c} | {mark[ok]} | {d.replace('|', '/')} |" for c, ok, d in rows]
    lines += [""] + cost_lines(cost)
    lines += [f"Left behind after the run: {', '.join(left) if left else 'nothing'}", ""]
    text = "\n".join(lines)
    print("\n" + text)
    out = pathlib.Path(args.report) if args.report else lw.RUNS_DIR / f"smoke-test-{dt.date.today():%Y%m%d}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"[smoke] report: {out}")
    return 0 if all(ok is not False for _, ok, _ in rows) and not left else 1


if __name__ == "__main__":
    sys.exit(main())
