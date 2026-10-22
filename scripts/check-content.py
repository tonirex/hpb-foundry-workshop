#!/usr/bin/env python3
"""Static content checks for the LiveWell Foundry workshop (Phase 1 acceptance gate).

Run from the repo root:  python scripts/check-content.py [--skip-generators]
Exits non-zero if any check fails. Needs pyyaml (see requirements.txt).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", ".venv-redteam", ".runs", "venv", "node_modules", "_refs", ".azure", "__pycache__", "out",
             ".playwright", "runs"}  # demos/.playwright (browser profile) and demos/runs (capture dumps) are gitignored
TEXT_EXT = {".md", ".json", ".yaml", ".yml", ".py", ".txt", ".csv", ".sh", ".ps1", ".bicep", ".jsonl", ".ipynb"}

GUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
ENDPOINT_RE = re.compile(
    r"https?://[a-z0-9][a-z0-9-]*\.(?:services\.ai\.azure\.com|openai\.azure\.com|cognitiveservices\.azure\.com|"
    r"search\.windows\.net|(?:[a-z0-9-]+\.)+azurecontainerapps\.io|azurecr\.io|blob\.core\.windows\.net)",
    re.IGNORECASE,
)
ID_ALLOWED = {"content/config/workshop.yaml", "SPEC.md", "CODING-AGENT-PROMPTS.md"}
ID_ALLOWED_GLOBS = ("infra/env/*.bicepparam",)
# The one place a lab page may hold an endpoint: the Lab 3 OpenAPI spec block written by
# scripts/sync-openapi-block.py (the tool calls the spec's server, so the address must be in it).
SPEC_BLOCK_PAGES = {"content/labs/lab-03.md", "content/labs/lab-03-portal.md"}
SPEC_BLOCK_RE = re.compile(r"<!-- openapi-spec:begin\b.*?-->(.*?)<!-- openapi-spec:end -->", re.S)
SPEC_CODE_RE = re.compile(r"```json[ \t]*\n(.*?)\n[ \t]*```", re.S)
LINK_RE = re.compile(r"(?<!!)\[(?:[^\]\[]|\[[^\]]*\])*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
PROMPT_TOKEN_RE = re.compile(r"`((?:lab[0-4]|fabric_q|bridge_q)_[a-z0-9_]+)`")
BEAT_RE = re.compile(
    r"\*\*\[(ch\d+\.\d+) · seat: (citizen|officer) · source: (kb|profile|fabric|mcp|memory) · prompt: ([a-z0-9_]+)\]\*\*"
)
LAB_SECTIONS = [
    "Shared objective",
    "Foundry features covered",
    "Story chapter",
    "🟢 Navigator",
    "🔵 Builder",
    "Checkpoint",
    "Troubleshooting",
    "Where next",
]
LAB_PAGES = ["lab-00", "lab-01", "lab-02", "lab-03", "lab-04", "fabric-step", "bridge-spotlight"]
COACH_BLOCKS = ["base", "knowledge", "safety", "tools", "fabric", "nutrition", "activity", "insights", "handoff", "merge"]


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.passed: list[str] = []

    def check(self, name: str, problems: list[str]) -> None:
        if problems:
            self.failures.append(name)
            print(f"FAIL  {name}")
            for p in problems[:40]:
                print(f"      - {p}")
            if len(problems) > 40:
                print(f"      … {len(problems) - 40} more")
        else:
            self.passed.append(name)
            print(f"PASS  {name}")

    def warn(self, name: str, notes: list[str]) -> None:
        if notes:
            self.warnings.append(name)
            print(f"WARN  {name}")
            for n in notes[:20]:
                print(f"      - {n}")


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def repo_files(exts: set[str] | None = None) -> list[Path]:
    out = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts):
            continue
        if rel(p) == "content/config/values.md" or rel(p).startswith("demos/devui-aca/app/"):
            continue  # values.md and the staged DevUI build copy (scripts/stage-devui.py) are gitignored
        if exts is None or p.suffix.lower() in exts:
            out.append(p)
    return sorted(out)


def strip_code(md: str) -> str:
    """Remove fenced blocks and inline code so links inside code are ignored."""
    md = re.sub(r"^(```|~~~).*?^\1\s*$", "", md, flags=re.MULTILINE | re.DOTALL)
    return re.sub(r"`[^`\n]*`", "", md)


def github_slug(heading: str) -> str:
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    text = text.replace("`", "").replace("*", "")
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    return text.replace(" ", "-")


def anchors_of(md_path: Path) -> set[str]:
    text = md_path.read_text(encoding="utf-8")
    text = re.sub(r"^(```|~~~).*?^\1\s*$", "", text, flags=re.MULTILINE | re.DOTALL)
    seen: dict[str, int] = {}
    out: set[str] = set()
    for m in re.finditer(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, flags=re.MULTILINE):
        slug = github_slug(m.group(1))
        n = seen.get(slug, 0)
        out.add(slug if n == 0 else f"{slug}-{n}")
        seen[slug] = n + 1
    for m in re.finditer(r"<a\s+(?:name|id)=\"([^\"]+)\"", text):
        out.add(m.group(1))
    return out


def fenced_blocks(md: str) -> dict[str, str]:
    blocks = {}
    for m in re.finditer(r"^```text name=([a-z_]+)\n(.*?)^```\s*$", md, flags=re.MULTILINE | re.DOTALL):
        blocks[m.group(1)] = m.group(2)
    return blocks


# --------------------------------------------------------------------------------------------------
def check_links(r: Report) -> None:
    problems = []
    for md in repo_files({".md"}):
        if rel(md) in {"SPEC.md", "CODING-AGENT-PROMPTS.md"}:
            continue
        text = strip_code(md.read_text(encoding="utf-8"))
        for img in IMAGE_RE.findall(text):
            if not img.startswith(("http://", "https://")) and not (md.parent / img.split("#")[0]).exists():
                problems.append(f"{rel(md)}: missing image {img}")
        for target in LINK_RE.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path_part, _, anchor = target.partition("#")
            dest = md if not path_part else (md.parent / path_part)
            try:
                dest = dest.resolve()
            except OSError:
                problems.append(f"{rel(md)}: bad link {target}")
                continue
            if not dest.exists():
                problems.append(f"{rel(md)}: broken link {target}")
                continue
            if ROOT not in dest.parents and dest != ROOT:
                problems.append(f"{rel(md)}: link leaves the repo {target}")
                continue
            if anchor and dest.suffix == ".md" and anchor not in anchors_of(dest):
                problems.append(f"{rel(md)}: missing anchor #{anchor} in {rel(dest)}")
    r.check("relative links and anchors resolve", problems)


def without_spec_blocks(text: str, rp: str, problems: list[str]) -> str:
    """Blank the Lab 3 OpenAPI spec block out of the endpoint scan, but only if it is an OpenAPI 3 document,
    so the exception cannot carry anything else. Newlines are kept so line numbers stay right."""
    def blank(m: re.Match) -> str:
        code = SPEC_CODE_RE.search(m.group(1))
        try:
            spec = json.loads(code.group(1)) if code else None
        except ValueError:
            spec = None
        if not (isinstance(spec, dict) and str(spec.get("openapi", "")).startswith("3.") and spec.get("servers")):
            problems.append(f"{rp}:{text.count(chr(10), 0, m.start()) + 1}: openapi-spec block is not an OpenAPI 3 "
                            "document (python scripts/sync-openapi-block.py <env>)")
            return m.group(0)
        return re.sub(r"[^\n]", " ", m.group(0))
    return SPEC_BLOCK_RE.sub(blank, text)


def check_ids_and_endpoints(r: Report) -> None:
    problems = []
    allowed = set(ID_ALLOWED)
    for g in ID_ALLOWED_GLOBS:
        allowed.update(rel(p) for p in ROOT.glob(g))
    for f in repo_files(TEXT_EXT):
        rp = rel(f)
        if rp in allowed:
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        for m in GUID_RE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            problems.append(f"{rp}:{line}: GUID {m.group(0)[:8]}…")
        if rp.startswith("content/") or rp in {"README.md", "foundry-workshop-plan.md"}:
            scan = without_spec_blocks(text, rp, problems) if rp in SPEC_BLOCK_PAGES else text
            for m in ENDPOINT_RE.finditer(scan):
                line = scan.count("\n", 0, m.start()) + 1
                problems.append(f"{rp}:{line}: concrete endpoint {m.group(0)}")
    r.check("no GUIDs outside workshop.yaml / bicepparam; no endpoints in content (except the Lab 3 spec block)",
            problems)


def spec_objectives() -> dict[str, str]:
    """Lab objectives from SPEC.md §5.1 (tab-separated rows 0–4)."""
    spec = (ROOT / "SPEC.md").read_text(encoding="utf-8").splitlines()
    out = {}
    in_51 = False
    for line in spec:
        if line.startswith("5.1 "):
            in_51 = True
            continue
        if in_51:
            m = re.match(r"^([0-4]) [^\t]+\t[^\t]+\t([^\t]+)\t", line)
            if m:
                out[f"lab-0{m.group(1)}"] = m.group(2).strip()
            elif out and not line.strip():
                break
            elif out and not re.match(r"^[0-4] ", line):
                break
    return out


def check_lab_pages(r: Report) -> None:
    problems = []
    objectives = spec_objectives()
    if len(objectives) != 5:
        problems.append(f"could not read 5 objectives from SPEC.md §5.1 (got {len(objectives)})")
    for page in LAB_PAGES:
        p = ROOT / "content" / "labs" / f"{page}.md"
        if not p.exists():
            problems.append(f"missing {rel(p)}")
            continue
        text = p.read_text(encoding="utf-8")
        h2 = [h.strip() for h in re.findall(r"^## (.+)$", strip_code_fences(text), flags=re.MULTILINE)]
        idx = []
        for s in LAB_SECTIONS:
            if s not in h2:
                problems.append(f"{page}: missing section '## {s}'")
            else:
                idx.append(h2.index(s))
        if idx != sorted(idx):
            problems.append(f"{page}: sections out of order {h2}")
        if page in objectives:
            obj = objectives[page]
            if normalise(obj) not in normalise(text):
                problems.append(f"{page}: shared objective is not verbatim from SPEC §5.1")
    for n in range(5):
        pp = ROOT / "content" / "labs" / f"lab-0{n}-portal.md"
        if not pp.exists():
            problems.append(f"missing {rel(pp)}")
    if not (ROOT / "content" / "labs" / "PORTAL-TRACK.md").exists():
        problems.append("missing content/labs/PORTAL-TRACK.md")
    r.check("lab pages: 8 sections in order, verbatim objectives, portal track present", problems)


def strip_code_fences(md: str) -> str:
    return re.sub(r"^(```|~~~).*?^\1\s*$", "", md, flags=re.MULTILINE | re.DOTALL)


def normalise(s: str) -> str:
    s = s.replace("—", "-").replace("–", "-").replace("’", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[*_>`]", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def check_patterns(r: Report, cfg: dict) -> None:
    problems = []
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\|\s*(\d{1,2})\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", readme, flags=re.MULTILINE)
    nums = sorted({int(n) for n, _, lab in rows if lab.strip() and int(n) <= 10})
    if nums != list(range(1, 11)):
        problems.append(f"README ten-patterns table covers {nums}, expected 1..10")
    mapped = set()
    for lab in cfg.get("labs", []):
        mapped.update(lab.get("patterns", []))
    if mapped != set(range(1, 11)):
        problems.append(f"workshop.yaml labs[].patterns cover {sorted(mapped)}, expected 1..10")
    for lab in cfg.get("labs", []):
        page = ROOT / "content" / "labs" / f"{lab['id']}.md"
        if page.exists() and lab.get("patterns"):
            text = page.read_text(encoding="utf-8")
            for n in lab["patterns"]:
                if not re.search(rf"#{n}\b", text):
                    problems.append(f"{lab['id']}: pattern #{n} (from workshop.yaml) not mentioned on the page")
    r.check("ten agentic patterns each mapped (README, workshop.yaml, lab pages)", problems)


def check_prompts(r: Report, prompts: dict, contracts: set[str]) -> None:
    problems = []
    ids = set(prompts)
    used = set()
    scan = [ROOT / "README.md", ROOT / "foundry-workshop-plan.md", ROOT / "content" / "narrative" / "rahim.md",
            ROOT / "content" / "fabric" / "question-bank.md"]
    scan += sorted((ROOT / "content" / "labs").glob("*.md"))
    for f in scan:
        text = f.read_text(encoding="utf-8")
        for tok in PROMPT_TOKEN_RE.findall(text):
            if tok in contracts:
                continue
            used.add(tok)
            if tok not in ids:
                problems.append(f"{rel(f)}: unknown prompt_id `{tok}`")
    for key in sorted((ROOT / "content" / "answer-keys").glob("lab-*.json")):
        data = json.loads(key.read_text(encoding="utf-8"))
        cps = data.get("checkpoints", [])
        if not cps:
            problems.append(f"{rel(key)}: no checkpoints")
        for cp in cps:
            pid = cp.get("prompt_id")
            if pid is None:
                if not cp.get("checkpoint_id"):
                    problems.append(f"{rel(key)}: checkpoint without prompt_id needs checkpoint_id")
                continue
            used.add(pid)
            if pid not in ids:
                problems.append(f"{rel(key)}: unknown prompt_id {pid}")
            ref = cp.get("expected_ref", "")
            if ref.startswith("prompts/test-prompts.json#/prompts/") and ref.split("/")[3] != pid:
                problems.append(f"{rel(key)}: expected_ref {ref} does not match prompt_id {pid}")
    for pid, p in prompts.items():
        for field in ("seat", "lab", "text", "expected"):
            if field not in p:
                problems.append(f"test-prompts.json: {pid} missing '{field}'")
        if p.get("seat") not in ("citizen", "officer"):
            problems.append(f"test-prompts.json: {pid} has seat {p.get('seat')!r}")
        if p.get("seat") == "officer" and not p.get("question_id"):
            problems.append(f"test-prompts.json: officer prompt {pid} has no question_id")
    labs_keys = {k.stem for k in (ROOT / "content" / "answer-keys").glob("lab-*.json")}
    for n in range(5):
        if f"lab-0{n}" not in labs_keys:
            problems.append(f"missing content/answer-keys/lab-0{n}.json")
    # The Lab 2 flyer paste must be exactly what the scripts send (lw.prompt_text): Prompt Shields scores the
    # whole message, so a missing HTML comment or extra text around the flyer changes the verdict (ASSUMPTIONS 8.2).
    flyer = (ROOT / "content" / "data" / "flyer-injected.md").read_text(encoding="utf-8")
    flyer = re.sub(r"\A(?:>.*\n)+\s*^---\s*$\n", "", flyer, count=1, flags=re.MULTILINE).strip()
    want = prompts.get("lab2_injected_flyer", {}).get("text", "") + "\n\n" + flyer
    for page in ("lab-02.md", "lab-02-portal.md"):
        md = (ROOT / "content" / "labs" / page).read_text(encoding="utf-8")
        blocks = [textwrap.dedent(m.group(2)).strip()
                  for m in re.finditer(r"^( *)```text\n(.*?)^\1```", md, flags=re.MULTILINE | re.DOTALL)
                  if "SYSTEM NOTICE" in m.group(2)]
        if blocks != [want]:
            problems.append(f"content/labs/{page}: the lab2_injected_flyer block must be the prompt + flyer-injected.md "
                            f"without its repo note ({len(blocks)} flyer block(s) found)")
    r.check("prompt ids consistent across pages, plan, narrative, answer keys", problems)
    r.warn("prompts defined but never referenced", sorted(ids - used))


def check_narrative(r: Report, prompts: dict) -> None:
    problems = []
    text = (ROOT / "content" / "narrative" / "rahim.md").read_text(encoding="utf-8")
    body = strip_code(text)
    beats = BEAT_RE.findall(body)
    if not beats:
        problems.append("no beat tags found in rahim.md")
    loose = re.findall(r"\*\*\[ch\d+\.\d+[^\]]*\]\*\*", body)
    if len(loose) != len(beats):
        problems.append(f"{len(loose) - len(beats)} malformed beat tag(s)")
    qbank = (ROOT / "content" / "fabric" / "question-bank.md").read_text(encoding="utf-8")
    row_re = re.compile(r"^\|\s*`(q_[a-z0-9_]+)`\s*\|", flags=re.MULTILINE)
    cohort_head = re.search(r"^## [^\n]*cohort question[^\n]*$", qbank, flags=re.MULTILINE | re.IGNORECASE)
    if cohort_head:
        nxt = re.search(r"^## ", qbank[cohort_head.end():], flags=re.MULTILINE)
        cohort_end = cohort_head.end() + (nxt.start() if nxt else len(qbank) - cohort_head.end())
        cohort_q = set(row_re.findall(qbank[cohort_head.start():cohort_end]))
        main_q = set(row_re.findall(qbank[:cohort_head.start()] + qbank[cohort_end:]))
    else:
        cohort_q, main_q = set(), set(row_re.findall(qbank))
    chapters = set()
    fabric_questions = set()
    cohort_used = set()
    for beat, seat, source, pid in beats:
        chapters.add(beat.split(".")[0])
        if pid not in prompts:
            problems.append(f"{beat}: unknown prompt {pid}")
            continue
        p = prompts[pid]
        if p.get("seat") != seat:
            problems.append(f"{beat}: seat {seat} but prompt {pid} is {p.get('seat')}")
        if seat == "citizen" and source == "fabric" and p.get("question_id") not in cohort_q:
            problems.append(f"{beat}: citizen beat may use source fabric only for the cohort question")
        if seat == "officer" and source != "fabric":
            problems.append(f"{beat}: officer beat must use source fabric")
        if source == "fabric":
            q = p.get("question_id")
            if not q:
                problems.append(f"{beat}: fabric beat prompt {pid} has no question_id")
            elif seat == "citizen":
                cohort_used.add(q)
            elif q not in main_q:
                problems.append(f"{beat}: question_id {q} not in question-bank.md main table")
            else:
                fabric_questions.add(q)
    if len(main_q) > 3:
        problems.append(f"question-bank.md has {len(main_q)} Mei questions (max 3)")
    if len(cohort_q) > 1:
        problems.append(f"question-bank.md has {len(cohort_q)} cohort questions (max 1)")
    if len(fabric_questions) > 3:
        problems.append(f"narrative uses {len(fabric_questions)} Mei questions (max 3)")
    for ch in range(6):
        if f"ch{ch}" not in chapters:
            problems.append(f"chapter {ch} has no beats")
    for m in re.finditer(r"RESIDENT_\d{5}", body):
        ctx = body[max(0, m.start() - 400): m.start()]
        last = BEAT_RE.findall(ctx)
        if last and last[-1][2] == "fabric":
            problems.append(f"resident_id {m.group(0)} appears in a fabric beat")
    refs = set(re.findall(r"\{\{ref:([a-z0-9_.\[\]-]+)\}\}", body))
    refs |= set(re.findall(r"<!--ref:([a-z0-9_.\[\]-]+)-->", text))
    if not refs:
        problems.append("narrative has no {{ref:...}} placeholders or filled <!--ref:...--> values")
    r.check(f"narrative beats ({len(beats)} beats, {len(fabric_questions)} Mei questions, "
            f"{len(cohort_used)} cohort question, {len(refs)} refs)", problems)


def check_glossary(r: Report, glossary: dict) -> None:
    problems = []
    coach = fenced_blocks((ROOT / "content" / "prompts" / "coach-instructions.md").read_text(encoding="utf-8"))
    for b in COACH_BLOCKS:
        if b not in coach:
            problems.append(f"coach-instructions.md: missing block name={b}")
    agent = (ROOT / "content" / "fabric" / "data-agent-instructions.md").read_text(encoding="utf-8")
    base = coach.get("base", "")
    for t in glossary.get("terms", []):
        d = t["definition"]
        if d not in base:
            problems.append(f"glossary '{t['id']}' not verbatim in coach-instructions base block")
        if d not in agent:
            problems.append(f"glossary '{t['id']}' not verbatim in data-agent-instructions.md")
    regions = set(glossary.get("regions", []))
    if regions != {"Central", "East", "North", "North-East", "West"}:
        problems.append(f"glossary regions {sorted(regions)}")
    r.check("glossary verbatim in coach + data-agent instructions; coach blocks present", problems)


def check_data(r: Report, glossary: dict) -> None:
    problems = []
    data = ROOT / "content" / "data"
    regions = set(glossary.get("regions", []))
    forbidden = {f.lower() for f in glossary.get("forbidden_fields", [])}
    for f in sorted((data / "resident360").glob("*.csv")):
        with f.open(encoding="utf-8", newline="") as fh:
            rd = csv.DictReader(fh)
            cols = [c.lower() for c in (rd.fieldnames or [])]
            bad = forbidden.intersection(cols)
            if bad:
                problems.append(f"{rel(f)}: forbidden column(s) {sorted(bad)}")
            rcol = next((c for c in (rd.fieldnames or []) if c.lower() in ("region", "event_region")), None)
            if rcol:
                vals = {row[rcol] for row in rd if row.get(rcol)}
                if not vals <= regions:
                    problems.append(f"{rel(f)}: unknown region value(s) {sorted(vals - regions)}")
    citizens = json.loads((data / "citizens.json").read_text(encoding="utf-8"))
    clist = citizens["citizens"] if isinstance(citizens, dict) else citizens
    if not any(c.get("resident_id") == "RESIDENT_00061" for c in clist):
        problems.append("citizens.json has no RESIDENT_00061 (Rahim)")
    for c in clist:
        if c.get("region") and c["region"] not in regions:
            problems.append(f"citizens.json: {c.get('resident_id')} region {c['region']}")
        bad = forbidden.intersection(k.lower() for k in c)
        if bad:
            problems.append(f"citizens.json: {c.get('resident_id')} has forbidden field(s) {sorted(bad)}")
    acts = json.loads((data / "activities.json").read_text(encoding="utf-8"))
    alist = acts["activities"] if isinstance(acts, dict) else acts
    if not any("woodlands" in json.dumps(a).lower() for a in alist):
        problems.append("activities.json has no Woodlands activity")
    for req in ("flyer-injected.md", "intake/rahim-screening-summary.md", "intake/rahim-activity-diary.md"):
        if not (data / req).exists():
            problems.append(f"missing content/data/{req}")
    guides = sorted((ROOT / "content" / "knowledge" / "livewell-guides").glob("lg-*.md"))
    if len(guides) < 10:
        problems.append(f"only {len(guides)} knowledge guides")
    for g in guides:
        if not (g.parent / "pdf" / f"{g.stem}.pdf").exists():
            problems.append(f"missing PDF for {g.name}")
        if "supplement" in g.read_text(encoding="utf-8").lower():
            problems.append(f"{g.name} mentions supplements (breaks refusal-on-absence for lab1_supplement)")
    r.check("data files: regions, forbidden fields, Rahim, guides + PDFs", problems)


def check_fabric_blueprint(r: Report) -> None:
    problems = []
    bp = yaml.safe_load((ROOT / "content" / "fabric" / "ontology.blueprint.yaml").read_text(encoding="utf-8"))
    ents = bp.get("entity_types", [])
    rels = bp.get("relationship_types", [])
    if len(ents) != 4:
        problems.append(f"blueprint has {len(ents)} entities (expected 4)")
    if len(rels) != 5:
        problems.append(f"blueprint has {len(rels)} relationships (expected 5)")
    r.check("fabric ontology blueprint: 4 entities / 5 relationships", problems)


def check_generators(r: Report) -> None:
    problems = []
    for script in ("gen-activity.py", "gen-citizens.py", "gen-schemas.py"):
        res = subprocess.run([sys.executable, str(ROOT / "scripts" / script), "--check"],
                             cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        if res.returncode != 0:
            problems.append(f"{script} --check: {(res.stdout + res.stderr).strip()[-300:]}")
    r.check("generators up to date (--check)", problems)


def check_repo_files(r: Report) -> None:
    need = ["README.md", "foundry-workshop-plan.md", "ASSUMPTIONS.md", "versions.md", "CHANGELOG.md", "NOTICE.md",
            "LICENSE", "AGENTS.md", ".devcontainer/devcontainer.json", "content/config/workshop.yaml",
            "content/config/glossary.yaml", "content/prompts/test-prompts.json",
            "content/fabric/ontology.blueprint.yaml", "content/fabric/data-agent-instructions.md",
            "content/fabric/question-bank.md", "content/narrative/rahim.md",
            "deck/LiveWell-Foundry-Workshop-Day1.pptx", "deck/build_deck.py"]
    r.check("required Phase 1 files exist", [f"missing {n}" for n in need if not (ROOT / n).exists()])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-generators", action="store_true", help="skip the slower generator --check runs")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "content" / "config" / "workshop.yaml").read_text(encoding="utf-8"))
    glossary = yaml.safe_load((ROOT / "content" / "config" / "glossary.yaml").read_text(encoding="utf-8"))
    bank = json.loads((ROOT / "content" / "prompts" / "test-prompts.json").read_text(encoding="utf-8"))
    prompts = bank["prompts"]
    contracts = set(bank.get("structured_contracts", {}))

    r = Report()
    check_repo_files(r)
    check_links(r)
    check_ids_and_endpoints(r)
    check_lab_pages(r)
    check_patterns(r, cfg)
    check_prompts(r, prompts, contracts)
    check_narrative(r, prompts)
    check_glossary(r, glossary)
    check_data(r, glossary)
    check_fabric_blueprint(r)
    if not args.skip_generators:
        check_generators(r)

    print(f"\n{len(r.passed)} passed, {len(r.failures)} failed, {len(r.warnings)} warnings")
    return 1 if r.failures else 0


if __name__ == "__main__":
    sys.exit(main())
