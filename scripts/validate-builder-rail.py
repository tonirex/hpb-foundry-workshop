#!/usr/bin/env python3
"""Run every Builder-rail lab top to bottom and print a pass/fail table (facilitator, T-3 and T-1).

Each lab runs as `python content/assets/labN_*.py --cleanup` with INITIALS=test (or --initials) and
LIVEWELL_AUTO_APPROVE=1 for explicit automated rehearsal, not participant consent. Every lab records its checks in
content/assets/.runs/<lab>-<initials>.json (livewell_common.expect); this script reads them, adds the
semantic signals below, then makes sure nothing of livewell-<initials>-* is left behind (items an
interrupted earlier run left are deleted before the labs start and don't count).

Semantic signals (SPEC.md phase 4 verification):
  * Lab 1: the knowledge base is cited
  * Lab 2: the injected flyer is blocked or ignored, the four red flags are blocked or safely refused on v2, and the
    look-only prepared-evaluation cell has completed evidence to inspect (live or captured).
    Lab 2 evaluates nothing here: paid evaluation is in the separate facilitator-only lab2_evaluate.py
  * Lab 3: the compound question makes >= 2 tool calls
  * Lab 3 Fabric step: Fabric IQ is called for Mei's question and not for Rahim's (only with FABRIC_BRIDGE=true)
  * Lab 4: sequential evidence JSON and actual hand-off contributions; hosted proof is operator-only

    python scripts/validate-builder-rail.py                     # all labs, INITIALS=test
    python scripts/validate-builder-rail.py --labs 1,3 --fabric # a subset, with the Fabric step
    python scripts/validate-builder-rail.py --report demos/BUILDER-RAIL-VALIDATION-2026-10-01.md

Needs the facilitator's azd env (AZURE_ENV_NAME) or content/assets/.env, and the shared resources: the
knowledge base, the MCP app, the tool connections and livewell-guardrails. Takes about 15-20 minutes.
Lab 2 covers the hands-on guardrail ladder only: batch evaluation is a separate, opt-in facilitator run
in content/assets/lab2_evaluate.py, never part of this participant-path validation.
Exit code 1 if any check fails, a lab crashes, or agents are left behind.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "content" / "assets"
sys.path.insert(0, str(ASSETS))

LABS = {
    "0": ("lab0", "lab0_setup.py", []),
    "1": ("lab1", "lab1_knowledge.py", []),
    "2": ("lab2", "lab2_govern.py", []),  # batch evaluation is a separate facilitator-only script
    "3": ("lab3", "lab3_tools.py", ["--fabric"]),
    "4": ("lab4", "lab4_multiagent.py", ["--fabric"]),
    "fabric": ("fabric", "lab3_fabric.py", []),
}

LAB2_RED_FLAGS = ("lab2_extreme_fasting", "lab2_medication_double", "lab2_injected_flyer", "lab2_other_resident")

# (lab, label, check labels that must all pass; fabric-only?)
SIGNALS = [
    ("lab0", "first agent has no tool calls", ["lab0_hi: no tools configured or called",
                                               "lab0_am_i_diabetic: no tools configured or called"], False),
    ("lab1", "KB citation present", ["lab1_prediabetes_eat: knowledge base searched",
                                     "lab1_prediabetes_eat: cites a real guide"], False),
    ("lab2", "injected flyer blocked or ignored", ["v2 lab2_injected_flyer: blocked or safely refused"], False),
    ("lab2", "four red flags blocked or safely refused on v2",
     [f"v2 {pid}: blocked or safely refused" for pid in LAB2_RED_FLAGS], False),
    ("lab2", "prepared evaluation: evidence available",
     ["prepared evaluation: results available for the look-only checkpoint"], False),
    ("lab3", "compound question >= 2 tool calls", ["lab3_hazy_indoor_signup: >= 2 tools (profile + find_activities)",
                                                 "lab3_hazy_indoor_signup: discovery is read-only",
                                                 "lab3_hazy_indoor_signup: knowledge base searched"],
     False),
    ("lab3", "Fabric IQ called for Mei", ["fabric_q_disengaged_regions: Fabric IQ tool called"], True),
    ("lab3", "Fabric IQ not called for Rahim", ["lab1_prediabetes_eat on the Fabric coach: no Fabric call"], True),
    ("lab4", "sequential order and evidence", ["lab4_week_plan_handoff: Nutrition -> Activity -> Coach",
                                               "lab4_week_plan_handoff: valid JSON"], False),
    ("lab4", "hand-off specialist contributions", ["handoff: Coach -> Nutrition -> Activity",
                                                     "handoff: both specialists answered"], False),
    ("fabric", "governed data and document routes", ["fabric_q_disengaged_regions: Fabric IQ tool called",
                                                      "lab1_prediabetes_eat: knowledge base searched",
                                                      "lab1_prediabetes_eat: no Fabric call"], False),
]


def run_lab(key: str, initials: str, fabric: bool, verbose: bool) -> dict:
    lab, script, fabric_flags = LABS[key]
    results = ASSETS / ".runs" / f"{lab}-{initials}.json"
    log = ASSETS / ".runs" / f"{lab}-{initials}.log"
    results.unlink(missing_ok=True)
    log.parent.mkdir(exist_ok=True)
    cmd = [sys.executable, "-u", str(ASSETS / script), "--cleanup"] + (fabric_flags if fabric else [])
    env = dict(os.environ, INITIALS=initials, LIVEWELL_AUTO_APPROVE="1", PYTHONIOENCODING="utf-8")
    print(f"[validate] {lab}: content/assets/{script} {' '.join(cmd[3:])}", flush=True)
    start = time.time()
    with log.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
        for line in proc.stdout:
            fh.write(line)
            if verbose or "[CHECK]" in line or "Traceback" in line:
                print(f"   {line.rstrip()}", flush=True)
        code = proc.wait()
    seconds = time.time() - start
    checks = {}
    if results.exists():
        checks = json.loads(results.read_text(encoding="utf-8")).get("results", {}).get("checks", {})
    passed = sum(1 for v in checks.values() if v)
    print(f"[validate] {lab}: exit {code}, {passed}/{len(checks)} checks, {seconds:.0f}s (log {log.name})", flush=True)
    return {"lab": lab, "exit": code, "seconds": seconds, "checks": checks, "log": str(log)}


def signal_rows(runs: dict[str, dict], fabric: bool) -> list[tuple[str, str, str]]:
    rows = []
    for lab, label, needed, fabric_only in SIGNALS:
        if lab not in runs:
            continue
        checks = runs[lab]["checks"]
        if fabric_only and not fabric:
            rows.append((lab, label, "SKIP (FABRIC_BRIDGE off)"))
        elif all(checks.get(k) for k in needed):
            rows.append((lab, label, "PASS"))
        else:
            rows.append((lab, label, "FAIL"))
    return rows


def leftovers() -> list[str]:
    """Delete and return every livewell-<initials>-* agent and memory store."""
    from common import livewell_common as lw

    prefix = f"livewell-{lw.initials()}-"
    agents = [a.name for a in lw.project().agents.list() if a.name.startswith(prefix)]
    stores = [s.name for s in lw.project().beta.memory_stores.list() if s.name.startswith(prefix)]
    if agents or stores:
        lw.cleanup(everything=True)
    return agents + stores


def report(runs: dict[str, dict], signals: list, left: list[str], initials: str, fabric: bool) -> str:
    lines = [f"# Builder-rail validation - {dt.date.today():%Y-%m-%d}", "",
             f"`python scripts/validate-builder-rail.py` with INITIALS={initials}, "
             f"AZURE_ENV_NAME={os.environ.get('AZURE_ENV_NAME', '(content/assets/.env)')}, "
             f"Fabric step {'on' if fabric else 'off'}.", "",
             "| Lab | Exit | Checks | Time |", "|---|---:|---:|---:|"]
    for r in runs.values():
        passed = sum(1 for v in r["checks"].values() if v)
        lines.append(f"| {r['lab']} | {r['exit']} | {passed}/{len(r['checks'])} | {r['seconds']:.0f} s |")
    lines += ["", "| Lab | Semantic signal | Result |", "|---|---|---|"]
    lines += [f"| {lab} | {label} | {res} |" for lab, label, res in signals]
    failed = [(r["lab"], k) for r in runs.values() for k, v in r["checks"].items() if not v]
    lines += ["", "Failed checks: " + (", ".join(f"{lab}: {k}" for lab, k in failed) if failed else "none"),
              f"Left behind after the run: {', '.join(left) if left else 'nothing'}", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--labs", default="0,1,2,3,4", help="comma-separated lab numbers; add fabric only when enabled")
    ap.add_argument("--initials", default="test", help="INITIALS for the run (default test)")
    ap.add_argument("--fabric", action="store_true", help="include the Fabric steps (default: FABRIC_BRIDGE)")
    ap.add_argument("--report", help="also write the markdown report here (default: content/assets/.runs/)")
    ap.add_argument("--verbose", action="store_true", help="stream every lab's output")
    args = ap.parse_args()
    os.environ["INITIALS"] = args.initials

    from common import livewell_common as lw  # loads the azd env / .env before FABRIC_BRIDGE is read

    lw.initials()
    fabric = lw.fabric_enabled(args.fabric)
    stale = leftovers()  # an interrupted earlier run must not fail this one
    if stale:
        print(f"[validate] cleared {len(stale)} item(s) left by an earlier run: {', '.join(stale)}", flush=True)
    runs = {}
    for key in [k.strip() for k in args.labs.split(",") if k.strip()]:
        if key not in LABS:
            raise SystemExit(f"unknown lab {key!r}; choose from {', '.join(LABS)}")
        r = run_lab(key, args.initials, fabric, args.verbose)
        runs[r["lab"]] = r
    signals = signal_rows(runs, fabric)
    left = leftovers()
    text = report(runs, signals, left, args.initials, fabric)
    print("\n" + text)
    out = pathlib.Path(args.report) if args.report else ASSETS / ".runs" / f"builder-rail-{dt.date.today():%Y%m%d}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"[validate] report: {out}")

    ok = (all(r["exit"] == 0 and r["checks"] and all(r["checks"].values()) for r in runs.values())
          and all(res != "FAIL" for _, _, res in signals) and not left)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
