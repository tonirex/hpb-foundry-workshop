#!/usr/bin/env python3
"""Historical Fabric GQL diagnostic and replay; not a viewer for the current ontology-context runtime.

The Foundry trace shows the Fabric IQ call as a single tool call (`userQuestion` in, answer out). This script asks
the published data agent the same question through its OpenAI-compatible Assistants endpoint and reads the run
steps, which show what the trace cannot: how the agent rewrote the question, the GQL it generated per query
(`analyze.database.nl2code`), the rows each query returned (`analyze.database.execute`) and how long each step took.
It writes a self-contained HTML page (no CDN): ontology path with the traversed edges highlighted, a step timeline,
one card per query (rewrite -> GQL -> rows with bars), a check against content/fabric/reference-answers.json and
the answer the coach receives.

    python demos/fabric-steps.py bridge --open             # the Bridge question (q_dropped_attended_heldin)
    python demos/fabric-steps.py fit --open                # Rahim's programme-fit cohort question (q_programme_fit)
    python demos/fabric-steps.py q_disengaged_regions      # any question-bank id, test-prompt id or free text
    python demos/fabric-steps.py --replay bridge --open    # no capacity needed: latest saved run, else demos/samples/
    python demos/fabric-steps.py bridge --save-sample      # also refresh demos/samples/fabric-steps-<id>.json

Runs are saved to demos/runs/ (git-ignored) as JSON + HTML. Workspace and artifact ids are stripped before saving.
Needs your az login with access to the Fabric workspace, an Active capacity and the azd env (FABRIC_* values).
Expect 30-90 s per question. Endpoint: {FABRIC}/v1/workspaces/{ws}/dataagents/{id}/aiassistant/openai (preview).
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "fabric"))
import fabriclib as fl  # noqa: E402

QBANK = ROOT / "content" / "fabric" / "question-bank.md"
REF_JSON = ROOT / "content" / "fabric" / "reference-answers.json"
PROMPTS = ROOT / "content" / "prompts" / "test-prompts.json"
BLUEPRINT = ROOT / "content" / "fabric" / "ontology.blueprint.yaml"
RUNS = ROOT / "demos" / "runs"
SAMPLES = ROOT / "demos" / "samples"
API_VERSION = "2024-05-01-preview"
FOUNDRY_TOOL = "DataAgent_Resident360_Ontology_Agent"
ALIASES = {"bridge": "q_dropped_attended_heldin", "fit": "q_programme_fit", "programme-fit": "q_programme_fit",
           "regions": "q_disengaged_regions", "programmes": "q_programmes_disengaged_enrolled"}
QBANK_ROW_RE = re.compile(r"^\|\s*`(q_[a-z0-9_]+)`\s*\|\s*([^|]+?)\s*\|", re.MULTILINE)
GQL_RE = re.compile(r"^```gql name=([a-z0-9_.]+)\n(.*?)^```\s*$", re.MULTILINE | re.DOTALL)
ONTOLOGY_RE = re.compile(r"```ontology\s*\n(.*?)\n```", re.DOTALL)
EDGE_RE = re.compile(r"-\[\s*\w*\s*:\s*`?(\w+)`?\s*\]->")
NODE_RE = re.compile(r"\(\s*\w*\s*:\s*`?(\w+)`?\s*\)")
DROP_KEYS = ("datasource_artifact_id", "datasource_workspace_id")
COLOURS = ["#0f6cbd", "#c4314b", "#107c10", "#8764b8", "#ca5010"]
SMALL_CELL = 5
NOTES = {
    "q_dropped_attended_heldin": [
        "Grain: the region where the event was <b>held</b> (EventOccurrence -heldIn-> Region), not where the "
        "resident lives (Resident -livesIn-> Region). The trace only shows the question; this page shows the path.",
        "The rows add up to {row_sum} but there are only {distinct} distinct residents: someone who attended events "
        "in two regions counts in both. {overlap} residents are counted more than once.",
        "Only aggregate counts leave Fabric. The question carries no resident_id and the answer names no resident.",
    ],
    "q_programme_fit": [
        "Two queries, joined by the agent: enrolledIn per programme, then droppedOut per programme. One combined "
        "MATCH would keep only the residents who dropped out, so enrolled would equal dropped (ASSUMPTIONS.md 6.7).",
        "The cohort is the age band only ({cohort} residents). Raw counts inside Fabric are exact; the answer the "
        "coach receives shows a count of 1-4 as \"fewer than {small}\".",
        "The coach then recommends the lowest drop-out programme Rahim is not already in and asks before it "
        "registers his interest.",
    ],
}
JOINS = {"q_programme_fit": ("enrolled", "dropped", "drop-out %")}


# ---------------------------------------------------------------- inputs

def load_env(env: str) -> None:
    path = ROOT / ".azure" / env / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition("=")
                if k.strip() in ("FABRIC_WORKSPACE_ID", "FABRIC_DATA_AGENT_ID", "AZURE_TENANT_ID"):
                    os.environ.setdefault(k.strip(), v.strip().strip('"'))


def default_env() -> str:
    if os.environ.get("AZURE_ENV_NAME"):
        return os.environ["AZURE_ENV_NAME"]
    cfg = ROOT / ".azure" / "config.json"
    return json.loads(cfg.read_text(encoding="utf-8")).get("defaultEnvironment", "") if cfg.exists() else ""


def qbank() -> tuple[dict[str, str], dict[str, str]]:
    md = QBANK.read_text(encoding="utf-8")
    return ({m.group(1): m.group(2).strip() for m in QBANK_ROW_RE.finditer(md)},
            {m.group(1): m.group(2).strip() for m in GQL_RE.finditer(md)})


def resolve_question(arg: str) -> tuple[str | None, str]:
    """Question-bank id, alias or test-prompt id -> (question_id, aggregate question text); else free text."""
    questions, _ = qbank()
    qid = ALIASES.get(arg, arg)
    if qid in questions:
        return qid, questions[qid]
    prompts = json.loads(PROMPTS.read_text(encoding="utf-8")).get("prompts", {})
    p = prompts.get(arg) or {}
    if p.get("question_id") in questions:
        return p["question_id"], questions[p["question_id"]]
    if p.get("text"):
        return None, p["text"]
    return None, arg


# ---------------------------------------------------------------- live capture

class Assistants:
    def __init__(self, ws: str, agent: str, token: str):
        self.base = f"{fl.FABRIC}/v1/workspaces/{ws}/dataagents/{agent}/aiassistant/openai"
        self.token = token

    def call(self, method: str, path: str, body: dict | None = None):
        req = urllib.request.Request(f"{self.base}{path}?api-version={API_VERSION}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None)
        req.add_header("Authorization", "Bearer " + self.token)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            hint = ""
            if "CapacityLimitExceeded" in detail or e.code == 429:
                hint = ("\nThe Fabric capacity is throttled: wait 10-20 minutes, or show a saved run with "
                        "--replay (works with no capacity).")
            elif e.code in (401, 403):
                hint = "\nCheck `az login` and your access to the Fabric workspace."
            raise SystemExit(f"HTTP {e.code} {method} {path}: {detail[:400]}{hint}") from None


def sanitise(steps: list[dict]) -> list[dict]:
    out = []
    for s in steps:
        calls = []
        for tc in (s.get("step_details") or {}).get("tool_calls") or []:
            fn = tc.get("function") or {}
            args = fn.get("arguments") or ""
            with contextlib.suppress(ValueError, TypeError):
                a = json.loads(args)
                if isinstance(a, dict):
                    args = json.dumps({k: v for k, v in a.items() if k not in DROP_KEYS})
            calls.append({"name": fn.get("name", ""), "arguments": args, "output": fn.get("output") or ""})
        out.append({"type": s.get("type"), "status": s.get("status"), "created_at": s.get("created_at"),
                    "completed_at": s.get("completed_at"), "last_error": s.get("last_error"), "tool_calls": calls})
    return out


def capture(question: str) -> dict:
    ws, agent = os.environ.get("FABRIC_WORKSPACE_ID", ""), os.environ.get("FABRIC_DATA_AGENT_ID", "")
    if not (ws and agent):
        import ask  # scripts/fabric/ask.py: looks the workspace and agent up by name
        ws, agent = ask.resolve()
    api = Assistants(ws, agent, fl.az_token(fl.FABRIC, os.environ.get("AZURE_TENANT_ID") or None))
    start = time.time()
    assistant = api.call("POST", "/assistants", {"model": "not-used"})
    thread = api.call("POST", "/threads", {})
    try:
        api.call("POST", f"/threads/{thread['id']}/messages", {"role": "user", "content": question})
        run = api.call("POST", f"/threads/{thread['id']}/runs", {"assistant_id": assistant["id"]})
        while run.get("status") in ("queued", "in_progress", "cancelling"):
            if time.time() - start > 600:
                raise SystemExit("the data agent run did not finish within 10 minutes")
            time.sleep(3)
            print(f"  ... {run.get('status')} {time.time() - start:.0f} s", end="\r", flush=True)
            run = api.call("GET", f"/threads/{thread['id']}/runs/{run['id']}")
        print(" " * 40, end="\r")
        steps = api.call("GET", f"/threads/{thread['id']}/runs/{run['id']}/steps").get("data", [])
        msgs = api.call("GET", f"/threads/{thread['id']}/messages").get("data", [])
    finally:
        with contextlib.suppress(SystemExit, Exception):
            api.call("DELETE", f"/threads/{thread['id']}")
    answer = next((c.get("text", {}).get("value", "") for m in msgs if m.get("role") == "assistant"
                   for c in m.get("content", []) if c.get("type") == "text"), "")
    return {"run": {k: run.get(k) for k in ("status", "created_at", "started_at", "completed_at", "last_error")},
            "seconds": round(time.time() - start, 1), "steps": sanitise(steps), "answer": answer}


# ---------------------------------------------------------------- parsing

def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def md_tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    lines, out, i = text.splitlines(), [], 0
    sep = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
    while i < len(lines):
        if lines[i].strip().startswith("|") and i + 1 < len(lines) and sep.match(lines[i + 1].strip()):
            head, rows, i = cells(lines[i]), [], i + 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            out.append((head, rows))
        else:
            i += 1
    return out


def num(s) -> float | None:
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return None


def gql_from(text: str) -> str:
    m = ONTOLOGY_RE.search(text or "")
    body = m.group(1) if m else (text or "")
    with contextlib.suppress(ValueError, TypeError, AttributeError):
        return json.loads(body)["entitySelector"]["query"]
    return body.strip()


def queries(run: dict) -> list[dict]:
    """Group the tool calls by the natural-language query the orchestrator wrote."""
    calls = []
    for s in run["steps"]:
        for tc in s["tool_calls"]:
            calls.append({**tc, "t0": s.get("created_at") or 0, "t1": s.get("completed_at") or s.get("created_at") or 0})
    calls.sort(key=lambda c: (c["t0"], c["t1"]))
    groups: dict[str, dict] = {}
    for c in calls:
        try:
            args = json.loads(c["arguments"]) if c["arguments"] else {}
        except ValueError:
            args = {}
        nl = args.get("natural_language_query") or (args.get("query") if c["name"] == "trace.analyze_ontology" else None)
        if not nl:
            continue
        g = groups.setdefault(nl, {"nl": nl, "gql": "", "table": None, "raw": "", "t0": c["t0"], "t1": c["t1"],
                                   "steps": []})
        g["t0"], g["t1"] = min(g["t0"], c["t0"]), max(g["t1"], c["t1"])
        g["steps"].append({"name": c["name"], "t0": c["t0"], "t1": c["t1"]})
        if c["name"] == "analyze.database.nl2code" and not g["gql"]:
            g["gql"] = gql_from(c["output"])
        elif c["name"] == "analyze.database.execute":
            g["gql"] = gql_from(args.get("code", "")) or g["gql"]
            g["raw"] = c["output"]
            tables = md_tables(c["output"])
            g["table"] = tables[0] if tables else None
        elif c["name"] == "trace.analyze_ontology" and g["table"] is None:
            tables = md_tables(c["output"])
            g["table"] = tables[0] if tables else None
            g["raw"] = g["raw"] or c["output"]
    return sorted(groups.values(), key=lambda g: g["t0"])


def blueprint() -> tuple[list[str], list[tuple[str, str, str]]]:
    import yaml
    bp = yaml.safe_load(BLUEPRINT.read_text(encoding="utf-8"))
    ents = [e["id"] for e in bp.get("entity_types", [])]
    rels = [(r["id"], (r.get("origin") or r.get("source"))["entity"], r["target"]["entity"]) for r in bp.get("relationship_types", [])]
    return ents, rels


# ---------------------------------------------------------------- HTML

def esc(s) -> str:
    return html.escape(str(s), quote=True)


def pretty_gql(q: str) -> str:
    q = re.sub(r"\s+(OPTIONAL MATCH|MATCH|WHERE|RETURN|GROUP BY|ORDER BY|LIMIT|UNION ALL)\b", r"\n\1", q.strip())
    out = esc(q)
    out = re.sub(r"\b(OPTIONAL MATCH|MATCH|WHERE|RETURN|GROUP BY|ORDER BY|LIMIT|UNION ALL|AS|AND|OR|COUNT|DISTINCT|"
                 r"LOWER|count|sum|DESC|ASC)\b", r'<span class="kw">\1</span>', out)
    return re.sub(r"`(\w+)`", r'<span class="id">\1</span>', out)


def md_html(text: str) -> str:
    """Just enough markdown for a data agent answer: tables, bullets, headings, bold, paragraphs."""
    blocks, lines, i = [], text.splitlines(), 0
    inline = lambda s: re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(s))  # noqa: E731
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("|") and md_tables("\n".join(lines[i:i + 2])):
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            head, rows = md_tables("\n".join(lines[i:j]))[0]
            blocks.append(table_html(head, rows, inline))
            i = j
            continue
        if re.match(r"^\s*[-*]\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append(f"<li>{inline(re.sub(r'^\s*[-*]\s+', '', lines[i]))}</li>")
                i += 1
            blocks.append(f"<ul>{''.join(items)}</ul>")
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            blocks.append(f"<h4>{inline(m.group(2))}</h4>")
        elif line.strip():
            blocks.append(f"<p>{inline(line)}</p>")
        i += 1
    return "\n".join(blocks)


def table_html(head: list[str], rows: list[list[str]], fmt=esc) -> str:
    th = "".join(f"<th>{fmt(h)}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td class=\"{'n' if num(c) is not None else ''}\">{fmt(c)}</td>" for c in r)
                 + "</tr>" for r in rows)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>"


def bars_html(head: list[str], rows: list[list[str]], colour: str) -> str:
    numeric = [j for j in range(len(head)) if rows and all(num(r[j]) is not None for r in rows if j < len(r))]
    labels = [j for j in range(len(head)) if j not in numeric]
    if not numeric or not labels:
        return ""
    lj, vj = labels[0], numeric[0]
    top = max((num(r[vj]) or 0) for r in rows) or 1
    out = [f'<div class="bars"><div class="bars-h">{esc(head[vj])} by {esc(head[lj])}</div>']
    for r in sorted(rows, key=lambda r: -(num(r[vj]) or 0)):
        v = num(r[vj]) or 0
        small = ' <span class="tag">raw count under 5</span>' if 0 < v < SMALL_CELL else ""
        out.append(f'<div class="bar"><span class="bl">{esc(r[lj])}</span><span class="bt"><span style="width:'
                   f'{100 * v / top:.1f}%;background:{colour}"></span></span><span class="bv">{v:g}{small}</span></div>')
    return "".join(out) + "</div>"


def ontology_svg(qs: list[dict]) -> str:
    ents, rels = blueprint()
    pos = {"Resident": (110, 175), "Programme": (450, 55), "EventOccurrence": (330, 300), "Region": (600, 205)}
    used_e: dict[str, list[int]] = {}
    used_n: set[str] = set()
    for k, q in enumerate(qs):
        for e in EDGE_RE.findall(q["gql"]):
            used_e.setdefault(e, []).append(k)
        used_n.update(NODE_RE.findall(q["gql"]))
    parts = ['<svg viewBox="0 0 720 360" class="onto" role="img" aria-label="Ontology path"><defs>']
    for k, c in enumerate(COLOURS + ["#9a9a9a"]):
        parts.append(f'<marker id="a{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="12" markerHeight="12" '
                     f'markerUnits="userSpaceOnUse" '
                     f'orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="{c}"/></marker>')
    parts.append("</defs>")
    pair_seen: dict[tuple[str, str], int] = {}
    for rid, src, tgt in rels:
        if src not in pos or tgt not in pos:
            continue
        (x1, y1), (x2, y2) = pos[src], pos[tgt]
        n = pair_seen.get((src, tgt), 0)
        pair_seen[(src, tgt)] = n + 1
        bend = (-50 if n == 0 else 44) if (src, tgt) == ("Resident", "Programme") else 0
        dx, dy = x2 - x1, y2 - y1
        ln = (dx * dx + dy * dy) ** 0.5 or 1
        sx, sy = x1 + dx / ln * 78, y1 + dy / ln * 28
        ex, ey = x2 - dx / ln * 82, y2 - dy / ln * 30
        mx, my = (sx + ex) / 2 - dy / ln * bend, (sy + ey) / 2 + dx / ln * bend
        hit = used_e.get(rid)
        col = COLOURS[hit[0] % len(COLOURS)] if hit else "#9a9a9a"
        mk = hit[0] % len(COLOURS) if hit else len(COLOURS)
        style = f'stroke="{col}" stroke-width="{4 if hit else 1.5}"' + ("" if hit else ' stroke-dasharray="5 4"')
        parts.append(f'<path d="M{sx:.0f},{sy:.0f} Q{mx:.0f},{my:.0f} {ex:.0f},{ey:.0f}" fill="none" {style} '
                     f'marker-end="url(#a{mk})"/>')
        lx, ly = (sx + 2 * mx + ex) / 4, (sy + 2 * my + ey) / 4
        badge = "".join(f" Q{k + 1}" for k in sorted(set(hit))) if hit else ""
        ly += 16 if bend > 0 else -7
        parts.append(f'<text x="{lx:.0f}" y="{ly:.0f}" class="el{" on" if hit else ""}" fill="{col}">'
                     f'{esc(rid)}{esc(badge)}</text>')
    for e in ents:
        if e not in pos:
            continue
        x, y = pos[e]
        on = e in used_n
        parts.append(f'<rect x="{x - 76}" y="{y - 26}" width="152" height="52" rx="12" class="node{" on" if on else ""}"/>'
                     f'<text x="{x}" y="{y + 5}" class="nl{" on" if on else ""}">{esc(e)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def timeline_html(run: dict, qs: list[dict]) -> str:
    r = run["run"]
    starts = [s["created_at"] for s in run["steps"] if s.get("created_at")]
    t0 = r.get("created_at") or (min(starts) if starts else 0)
    t1 = r.get("completed_at") or max([s.get("completed_at") or 0 for s in run["steps"]] + [t0 + 1])
    span = max(t1 - t0, 1)
    rows = []

    def bar(label: str, a: float, b: float, colour: str, cls: str = "") -> str:
        left, width = 100 * (a - t0) / span, max(100 * (b - a) / span, 0.8)
        return (f'<div class="tl {cls}"><span class="tll">{esc(label)}</span><span class="tlt"><span style="left:'
                f'{left:.1f}%;width:{width:.1f}%;background:{colour}"></span></span><span class="tlv">{b - a:.0f} s</span></div>')
    for k, q in enumerate(qs):
        c = COLOURS[k % len(COLOURS)]
        rows.append(bar(f"Q{k + 1} query", q["t0"], q["t1"], c))
        for s in q["steps"]:
            if s["name"] in ("analyze.database.nl2code", "analyze.database.execute"):
                rows.append(bar(s["name"].split(".")[-1].replace("nl2code", "write GQL").replace("execute", "run GQL"),
                                s["t0"], s["t1"], c + "99", "sub"))
    last = max([q["t1"] for q in qs] + [t0])
    rows.append(bar("write the answer", last, t1, "#605e5c"))
    return f'<div class="timeline"><div class="tlh">0 s<span>{span:.0f} s</span></div>{"".join(rows)}</div>'


def reference_html(qid: str | None, qs: list[dict], answer: str) -> tuple[str, list[str]]:
    if not qid:
        return "", []
    refs = json.loads(REF_JSON.read_text(encoding="utf-8"))
    ref = refs.get(qid)
    if not isinstance(ref, dict) or not ref.get("rows"):
        return "", []
    found: dict[str, list[float]] = {}
    for q in qs:
        if q["table"]:
            for r in q["table"][1]:
                if r:
                    found.setdefault(r[0].strip().lower(), []).extend(v for v in map(num, r[1:]) if v is not None)
    label = next(k for k, v in ref["rows"][0].items() if isinstance(v, str))
    keys = [k for k, v in ref["rows"][0].items() if isinstance(v, (int, float))]
    head = [label] + keys
    body, ok, total = [], 0, 0
    for row in ref["rows"]:
        got = found.get(str(row[label]).lower(), [])
        tds = [f"<td>{esc(row[label])}</td>"]
        for k in keys:
            if k.endswith("_pct"):
                tds.append(f'<td class="n muted">{row[k]:g} <span class="tag">worked out from the counts</span></td>')
                continue
            total += 1
            hit = any(abs(v - row[k]) < 0.05 for v in got)
            ok += hit
            tds.append(f'<td class="n {"ok" if hit else "bad"}">{row[k]:g} {"&#10003;" if hit else "&#10007;"}</td>')
        body.append("<tr>" + "".join(tds) + "</tr>")
    th = "".join(f"<th>{esc(h)}</th>" for h in head)
    verdict = (f'<p class="{"ok" if ok == total else "bad"}"><b>{ok}/{total}</b> reference counts appear in the rows '
               f'the data agent\'s queries returned (reference-answers.json, grain: {esc(ref.get("grain", ""))}).</p>')
    rows_sum = sum(r.get("residents", 0) for r in ref["rows"])
    fmt = {"row_sum": rows_sum, "distinct": ref.get("distinct_residents", ""),
           "overlap": rows_sum - (ref.get("distinct_residents") or rows_sum), "cohort": ref.get("cohort_residents", ""),
           "small": SMALL_CELL}
    notes = [n.format(**fmt) for n in NOTES.get(qid, [])]
    if qid == "q_dropped_attended_heldin" and str(ref.get("distinct_residents")) not in answer:
        notes.append(f"This answer does not state the distinct total ({ref.get('distinct_residents')}); ask the "
                     "follow-up \"How many distinct residents is that in total?\" to show the difference.")
    return verdict + f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(body)}</tbody></table>", notes


def joined_html(qid: str | None, qs: list[dict]) -> str:
    names = JOINS.get(qid or "")
    tabs = [q["table"] for q in qs if q["table"]]
    if not names or len(tabs) < 2:
        return ""
    a = {r[0]: num(r[1]) for r in tabs[0][1] if len(r) > 1}
    b = {r[0]: num(r[1]) for r in tabs[1][1] if len(r) > 1}
    rows = []
    for lab in sorted(a, key=lambda k: (b.get(k) or 0) / (a[k] or 1)):
        x, y = a[lab] or 0, b.get(lab) or 0
        pct = f"{100 * y / x:.1f}" if x else "-"
        rows.append([lab, f"{x:g}", f"{y:g}", pct])
    return ("<h3>Joined by the agent (Q1 + Q2)</h3>" + table_html([tabs[0][0][0], *names], rows)
            + '<p class="muted">Sorted by drop-out rate. Rahim is already in Active Ageing and Eat Drink Shop Healthy '
              'and dropped Healthier SG, so the lowest rate he can still join is the recommendation.</p>')


CSS = """
body{font:15px/1.45 'Segoe UI',system-ui,sans-serif;margin:0;background:#f5f5f5;color:#242424}
main{max-width:1100px;margin:0 auto;padding:24px 28px 60px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:28px 0 10px}h3{font-size:15px;margin:18px 0 8px}
.q{font-size:18px;background:#fff;border-left:5px solid #0f6cbd;padding:12px 16px;border-radius:6px;margin:12px 0}
.meta{color:#616161;font-size:13px}.muted{color:#707070;font-size:13px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.card{background:#fff;border-radius:8px;padding:14px 18px;box-shadow:0 1px 3px #0002}
.trace{border-top:4px solid #605e5c}.inside{border-top:4px solid #0f6cbd}
.mono,pre{font-family:Consolas,'Cascadia Mono',monospace;font-size:13px}
pre{background:#1e1e1e;color:#d4d4d4;padding:12px 14px;border-radius:6px;white-space:pre-wrap;margin:6px 0}
.kw{color:#569cd6;font-weight:600}.id{color:#9cdcfe}
table{border-collapse:collapse;margin:6px 0;background:#fff;font-size:14px}
th,td{border:1px solid #e0e0e0;padding:4px 10px;text-align:left}th{background:#fafafa}td.n{text-align:right}
td.ok,p.ok{color:#107c10}td.bad,p.bad{color:#c4314b}
.query{background:#fff;border-radius:8px;padding:12px 18px 16px;margin:14px 0;box-shadow:0 1px 3px #0002}
.badge{display:inline-block;color:#fff;border-radius:12px;padding:1px 10px;font-weight:600;margin-right:8px}
.stepn{font-weight:600;color:#424242;margin-top:10px}
.bars{margin:8px 0;max-width:640px}.bars-h{font-size:12px;color:#616161;margin-bottom:4px}
.bar{display:flex;align-items:center;gap:8px;margin:3px 0}.bl{width:190px;font-size:13px;text-align:right}
.bt{flex:1;background:#eee;height:16px;border-radius:3px;overflow:hidden}.bt span{display:block;height:100%}
.bv{width:150px;font-size:13px}
.tag{font-size:11px;background:#fff4ce;color:#835b00;border-radius:4px;padding:0 5px;margin-left:4px}
.onto{width:100%;max-width:720px;background:#fff;border-radius:8px}
.node{fill:#f0f0f0;stroke:#9a9a9a}.node.on{fill:#ebf3fc;stroke:#0f6cbd;stroke-width:2}
.nl{text-anchor:middle;font-size:15px;fill:#616161}.nl.on{fill:#0f3a6b;font-weight:600}
.el{text-anchor:middle;font-size:13px;paint-order:stroke;stroke:#fff;stroke-width:4px}.el.on{font-weight:700}
.timeline{background:#fff;border-radius:8px;padding:10px 16px;max-width:900px}
.tlh{display:flex;justify-content:space-between;margin-left:170px;margin-right:60px;font-size:11px;color:#707070}
.tl{display:flex;align-items:center;gap:8px;margin:3px 0}.tll{width:162px;font-size:13px;text-align:right}
.tl.sub .tll{color:#707070;font-size:12px}.tlt{flex:1;position:relative;height:14px;background:#f3f3f3;border-radius:3px}
.tlt span{position:absolute;top:0;bottom:0;border-radius:3px}.tlv{width:52px;font-size:12px;color:#616161}
ul.notes li{margin:6px 0}.answer{background:#fff;border-radius:8px;padding:8px 18px;box-shadow:0 1px 3px #0002}
footer{margin-top:30px;color:#707070;font-size:12px}
"""


def render(data: dict) -> str:
    qs = queries(data)
    qid, question = data.get("question_id"), data["question"]
    ref_block, notes = reference_html(qid, qs, data.get("answer", ""))
    canon = qbank()[1].get(qid or "", "")
    cards = []
    for k, q in enumerate(qs):
        c = COLOURS[k % len(COLOURS)]
        rows = (table_html(*q["table"]) + bars_html(*q["table"], c)) if q["table"] else f"<pre>{esc(q['raw'][:1500])}</pre>"
        cards.append(f'<div class="query"><div><span class="badge" style="background:{c}">Q{k + 1}</span>'
                     f'<span class="muted">{q["t1"] - q["t0"]:.0f} s</span></div>'
                     f'<div class="stepn">1. Rewrite: the question the orchestrator sent to the ontology</div>'
                     f'<div>{esc(q["nl"])}</div>'
                     f'<div class="stepn">2. GQL generated (analyze.database.nl2code)</div><pre>{pretty_gql(q["gql"])}</pre>'
                     f'<div class="stepn">3. Rows returned (analyze.database.execute)</div>{rows}</div>')
    if not qs:
        cards.append('<p class="bad">No legacy GQL query records recognised. This viewer does not interpret current '
                     'source-native SQL/KQL/DAX run steps. Absence here is not proof that no query ran; inspect '
                     'the native Fabric run steps.</p>')
    edges = list(dict.fromkeys(e for q in qs for e in EDGE_RE.findall(q["gql"])))
    run = data["run"]
    replay = " &middot; <b>replayed from a saved run</b>" if data.get("_replayed") else ""
    excerpt = data.get("answer", "")[:420] + ("..." if len(data.get("answer", "")) > 420 else "")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Inside the data agent: {esc(qid or 'question')}</title>
<style>{CSS}</style></head><body><main>
<section id="overview">
<h1>Inside the Fabric data agent</h1>
<p class="q"><b>Historical GQL diagnostic.</b> Current ontology context guides source-native SQL, KQL or DAX.
This is a separate data-agent run, not a correlated expansion of the coach's Foundry trace.
Use Fabric run steps for current execution evidence.</p>
<div class="meta">{esc(qid or 'free-text question')} &middot; env {esc(data.get('env', ''))} &middot; captured {esc(data.get('captured_at', ''))}
 &middot; run {esc(run.get('status'))} in {data.get('seconds', 0):g} s &middot; {len(qs)} ontology quer{'y' if len(qs) == 1 else 'ies'}{replay}</div>
<div class="q">{esc(question)}</div>
<div class="grid">
 <div class="card trace"><h3>What the Foundry trace shows</h3>
  <div class="muted">One tool call on the coach's run (Foundry &gt; Traces, span kind <span class="mono">mcp_call</span>):</div>
  <pre>{esc(FOUNDRY_TOOL)}(
  userQuestion: "{esc(question)}"
)
&rarr; {esc(excerpt)}</pre>
  <div class="muted">Question in, answer out. No query, no rows, no path.</div></div>
 <div class="card inside"><h3>What happened inside Fabric</h3>
  <ul><li><b>{len(qs)}</b> natural-language quer{'y' if len(qs) == 1 else 'ies'} planned by the agent's orchestrator</li>
  <li>Each one turned into GQL over the <b>resident_ontology</b> graph</li>
  <li>Relationships traversed: <b>{esc(', '.join(edges) or 'none')}</b></li>
  <li>Rows returned are aggregate counts; no resident_id leaves Fabric</li>
  <li>The agent then wrote the answer the coach receives (below)</li></ul></div>
</div>
<h2>Path through the ontology</h2>{ontology_svg(qs)}
<div class="muted">Solid, coloured edges were traversed (Q1, Q2 ...). Dashed edges exist in the ontology but were not used.</div>
</section>
<section id="timeline"><h2>Timeline</h2>{timeline_html(data, qs)}</section>
<section id="queries"><h2>Queries</h2>{''.join(cards)}
{joined_html(qid, qs)}
{f'<h3>Canonical query in the question bank (for comparison)</h3><pre>{pretty_gql(canon)}</pre>' if canon else ''}</section>
<section id="check">{'<h2>Check against the reference answer</h2>' + ref_block if ref_block else ''}
{'<h2>What to point out</h2><ul class="notes">' + ''.join(f'<li>{n}</li>' for n in notes) + '</ul>' if notes else ''}</section>
<section id="answer"><h2>Answer returned to the coach</h2><div class="answer">{md_html(data.get('answer', '')) or '<p class="bad">(no answer)</p>'}</div></section>
<footer>Generated by demos/fabric-steps.py from the data agent's run steps (Assistants endpoint, preview). Synthetic data.
Workspace and artifact ids are removed. Re-render with <span class="mono">python demos/fabric-steps.py --replay &lt;json&gt;</span>.</footer>
</main></body></html>"""


# ---------------------------------------------------------------- main

def slug(qid: str | None, question: str) -> str:
    return qid or re.sub(r"[^a-z0-9]+", "-", question.lower()).strip("-")[:40] or "question"


def find_replay(arg: str) -> Path:
    p = Path(arg)
    if p.exists():
        return p
    if arg == "latest":
        cands = sorted(RUNS.glob("fabric-steps-*.json"), key=lambda f: f.stat().st_mtime)
    else:
        qid = ALIASES.get(arg, arg)
        cands = sorted(RUNS.glob(f"fabric-steps-{qid}-*.json"), key=lambda f: f.stat().st_mtime)
        if not cands and (SAMPLES / f"fabric-steps-{qid}.json").exists():
            cands = [SAMPLES / f"fabric-steps-{qid}.json"]
    if not cands:
        raise SystemExit(f"no saved run for {arg!r} in {RUNS.relative_to(ROOT)} or {SAMPLES.relative_to(ROOT)}")
    return cands[-1]


def load_replay(arg: str) -> tuple[dict, Path, Path]:
    """The saved run for arg (path, id, alias or "latest") and the HTML path its page is rendered to."""
    src = find_replay(arg).resolve()
    data = json.loads(src.read_text(encoding="utf-8"))
    data["_replayed"] = True
    return data, src, RUNS / f"{src.stem if src.parent == RUNS else src.stem + '-replay'}.html"


def replay_page(arg: str) -> Path:
    """Render the latest saved run for arg (else the committed sample) and return the HTML file."""
    data, _, out = load_replay(arg)
    RUNS.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    return out


def summary(data: dict) -> None:
    qs = queries(data)
    print("HISTORICAL GQL diagnostic: not current source-native execution proof. Inspect Fabric run steps.")
    print(f"Q: {data['question']}\n   {data['run'].get('status')} in {data.get('seconds')} s, {len(qs)} ontology queries")
    for k, q in enumerate(qs):
        print(f"\n[Q{k + 1}] {q['nl']}  ({q['t1'] - q['t0']:.0f} s)\n  GQL: {q['gql']}")
        if q["table"]:
            head, rows = q["table"]
            print("  " + " | ".join(head))
            for r in rows[:10]:
                print("  " + " | ".join(r))
    print("\nANSWER:\n" + data.get("answer", "")[:1200])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", nargs="?", help="bridge | fit | question-bank id | test-prompt id | free text")
    ap.add_argument("--replay", metavar="JSON|ID|latest", help="re-render a saved run instead of asking Fabric")
    ap.add_argument("--env", default=default_env(), help="azd env name (default: AZURE_ENV_NAME or azd default)")
    ap.add_argument("--open", action="store_true", help="open the HTML page in the default browser")
    ap.add_argument("--save-sample", action="store_true", help="also write demos/samples/fabric-steps-<id>.json")
    ap.add_argument("--quiet", action="store_true", help="do not print the steps to the console")
    a = ap.parse_args()
    if not a.question and not a.replay:
        ap.error("give a question (bridge, fit, an id or text) or --replay")
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    if a.replay:
        data, src, out = load_replay(a.replay)
        print(f"replaying {src.relative_to(ROOT) if src.is_relative_to(ROOT) else src}")
    else:
        qid, question = resolve_question(a.question)
        if a.env:
            os.environ["AZURE_ENV_NAME"] = a.env
            load_env(a.env)
        print(f"asking the data agent ({a.env}): {question}")
        data = {"tool": "demos/fabric-steps.py", "captured_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "env": a.env, "question_id": qid, "question": question, **capture(question)}
        RUNS.mkdir(parents=True, exist_ok=True)
        js = RUNS / f"fabric-steps-{slug(qid, question)}-{stamp}.json"
        js.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        out = js.with_suffix(".html")
        if a.save_sample:
            SAMPLES.mkdir(parents=True, exist_ok=True)
            sample = SAMPLES / f"fabric-steps-{slug(qid, question)}.json"
            sample.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"sample: {sample.relative_to(ROOT)}")
        print(f"saved: {js.relative_to(ROOT)}")
    if not a.quiet:
        summary(data)
    RUNS.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    print(f"\npage: {out.relative_to(ROOT)}")
    if a.open:
        webbrowser.open(out.resolve().as_uri())
    return 0 if data["run"].get("status") == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
