#!/usr/bin/env python3
"""Render participant copy blocks from canonical prompts, instructions and schemas.

    python scripts/sync-lab-blocks.py
    python scripts/sync-lab-blocks.py --check

Only <!-- copy:KIND SOURCE --> ... <!-- /copy --> regions are generated.
The environment-specific OpenAPI block remains owned by sync-openapi-block.py.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "content" / "assets"))
from common import livewell_common as lw  # noqa: E402

BLOCK_RE = re.compile(
    r"^(?P<indent>[ \t]*)<!-- copy:(?P<kind>[a-z]+) (?P<source>[\w,-]+) -->\n"
    r"(?P<body>.*?)^(?P=indent)<!-- /copy -->[ \t]*$",
    re.M | re.S,
)
MARKER_RE = re.compile(r"^[ \t]*<!-- /?copy\b[^\n]*", re.M)
REQUIRED = {
    "lab-00": {("instructions", "base"), ("prompt", "lab0_hi"), ("prompt", "lab0_am_i_diabetic")},
    "lab-01": {
        ("instructions", "knowledge"), ("schema", "lab1-answer"),
        ("prompt", "lab1_prediabetes_eat"), ("prompt", "lab1_supplement"),
        ("prompt", "lab1_activity_guideline"), ("prompt", "lab1_intake"),
        ("instructions", "base,intake"), ("schema", "lab1-intake"),
    },
    "lab-02": {("instructions", "safety")} | {
        ("prompt", pid) for pid in (
            "lab2_extreme_fasting", "lab2_medication_double", "lab2_injected_flyer",
            "lab2_other_resident", "lab2_skip_meals", "lab2_benign_control", "lab2_benign_dose_reminder",
        )
    },
    "lab-03": {("instructions", "tools"), ("schema", "lab3-evidence")} | {
        ("prompt", pid) for pid in (
            "lab3_profile_tailored", "lab3_hazy_indoor_signup", "lab3_signup_confirm",
            "lab3_memory_set", "lab3_memory_recall", "lab3_specialists",
        )
    },
    "fabric-step": {("instructions", "fabric")} | {
        ("prompt", pid) for pid in (
            "lab3_programme_fit", "lab3_programme_confirm", "fabric_q_disengaged_regions", "lab1_prediabetes_eat",
        )
    },
    "lab-04": {
        ("request", "lab4_week_plan_handoff"), ("request", "lab4_activity_only"),
        ("prompt", "lab4_q_programmes_disengaged"), ("prompt", "lab1_prediabetes_eat"),
    },
    "bridge-spotlight": {("prompt", "bridge_q_dropped_attended_heldin")},
}
SCHEMAS = {"lab1-answer", "lab1-intake", "lab3-evidence"}


def payload(kind: str, source: str) -> tuple[str, str]:
    if kind == "instructions":
        return "text", lw.load_instructions(*source.split(","))
    if kind == "schema":
        if source not in SCHEMAS:
            raise ValueError(f"unknown schema {source!r}")
        text = (ROOT / "content" / "config" / "schemas" / f"{source}.schema.json").read_text(encoding="utf-8").strip()
        schema = json.loads(text)
        if not (schema.get("name") and schema.get("strict") is True and isinstance(schema.get("schema"), dict)):
            raise ValueError(f"{source}: expected the complete name/strict/schema wrapper")
        return "json", text
    if kind in {"prompt", "request"}:
        text = lw.prompt_text(source)
        if source == "lab2_injected_flyer":
            # Keep the tested portal framing: prompt + flyer, without a filename label or repo note.
            text = lw.prompt_text(source, with_attachments=False) + "\n\n" + lw.attachment_text(
                "content/data/flyer-injected.md"
            )
        if kind == "request":
            if source not in {"lab4_week_plan_handoff", "lab4_activity_only"}:
                raise ValueError(f"unknown profile-prefixed request {source!r}")
            bank = json.loads((ROOT / "content" / "prompts" / "test-prompts.json").read_text(encoding="utf-8"))
            citizens = json.loads((ROOT / "content" / "data" / "citizens.json").read_text(encoding="utf-8"))
            rows = citizens["citizens"] if isinstance(citizens, dict) else citizens
            matches = [row for row in rows if row["resident_id"] == bank["session_resident_id"]]
            if len(matches) != 1:
                raise ValueError("the canonical session resident must have exactly one generated profile")
            text = lw.profile_summary(matches[0]) + "\n\n" + text
        return "text", text
    raise ValueError(f"unknown copy block kind {kind!r}")


def render_page(text: str, required: set[tuple[str, str]]) -> str:
    matches = list(BLOCK_RE.finditer(text))
    if len(MARKER_RE.findall(text)) != 2 * len(matches):
        raise ValueError("unmatched or malformed copy markers")
    found = {(m["kind"], m["source"]) for m in matches}
    if missing := required - found:
        raise ValueError("missing copy blocks: " + ", ".join(f"{kind} {source}" for kind, source in sorted(missing)))

    def replace(match: re.Match) -> str:
        language, body = payload(match["kind"], match["source"])
        if re.search(r"^```", body, re.M):
            raise ValueError(f"{match['source']}: nested code fence in copy payload")
        lines = [
            f"<!-- copy:{match['kind']} {match['source']} -->", f"```{language}",
            *body.splitlines(), "```", "<!-- /copy -->",
        ]
        return "\n".join(match["indent"] + line if line else "" for line in lines)

    return BLOCK_RE.sub(replace, text)


def updates(root: Path = ROOT) -> list[tuple[Path, str]]:
    changes = []
    for stem, required in REQUIRED.items():
        path = root / "content" / "labs" / f"{stem}.md"
        text = path.read_text(encoding="utf-8")
        try:
            rendered = render_page(text, required)
        except (KeyError, ValueError, OSError) as exc:
            raise ValueError(f"{path.name}: {exc}") from exc
        if text != rendered:
            changes.append((path, rendered))
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report drift without writing files")
    args = parser.parse_args()
    try:
        changes = updates()
    except (ValueError, OSError) as exc:
        print(f"FAIL  copy blocks: {exc}")
        return 1
    for path, rendered in changes:
        if not args.check:
            path.write_bytes(rendered.encode("utf-8"))
        print(f"{'STALE' if args.check else 'WROTE'} {path.relative_to(ROOT).as_posix()}")
    if not changes:
        print("PASS  participant copy blocks match their canonical sources")
    elif args.check:
        print("Run python scripts/sync-lab-blocks.py and commit the generated blocks.")
    return int(args.check and bool(changes))


if __name__ == "__main__":
    raise SystemExit(main())
