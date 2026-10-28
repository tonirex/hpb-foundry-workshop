#!/usr/bin/env python3
"""Write the generated JSON files that must stay identical to the Builder-rail code.

* content/config/schemas/*.schema.json: paste-ready schemas for Navigator participants (portal: Response
  format -> JSON schema). The Builder scripts build the same schemas in code (livewell_common.lab1_schema /
  evidence_schema), so both rails get identical contracts: strict mode, every property required, and
  citations limited to the real guide ids (the file stems of content/knowledge/livewell-guides/lg-*.md).
* content/assets/hosted-agent-example/livewell.json: the hosted agent's instructions, evidence schema and
  tool connections. The hosted agent is deployed on its own, so it cannot import livewell_common or read
  coach-instructions.md; this file carries exactly what lab4_multiagent.py uses.

  python scripts/gen-schemas.py           # (re)write the files
  python scripts/gen-schemas.py --check   # exit 1 if a file is missing or stale (run by check-content.py)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMAS_DIR = ROOT / "content" / "config" / "schemas"
HOSTED_FILE = ROOT / "content" / "assets" / "hosted-agent-example" / "livewell.json"
sys.path.insert(0, str(ROOT / "content" / "assets"))

from common import livewell_common as lw  # noqa: E402


def _dump(obj: dict) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def schema_file(name: str, build) -> str:
    return _dump({"name": name, "strict": True, "schema": build()})


def hosted_file() -> str:
    """Same agents as the sequential workflow in lab4_multiagent.py (section 4)."""
    return _dump({
        "_generated": "by scripts/gen-schemas.py from content/prompts/coach-instructions.md and "
                      "livewell_common.py; do not edit by hand",
        "agents": {
            "nutrition": {"instructions": lw.load_instructions("nutrition"), "tools": ["knowledge"],
                          "description": "Meal suggestions grounded in the LiveWell guides"},
            "activity": {"instructions": lw.load_instructions("activity"), "tools": ["knowledge", "activities"],
                         "description": "Safe activities and community activities"},
            "coach": {"instructions": lw.load_instructions("base", "safety", "merge"), "tools": [],
                      "description": "LiveWell Coach: merges the specialists' answers"},
        },
        "tools": {
            "knowledge": {"label": lw.KB_LABEL, "connection": lw.NAMES["kb_mcp_connection"],
                          "allowed_tools": ["knowledge_base_retrieve"]},
            "activities": {"label": lw.ACTIVITIES_LABEL, "connection": lw.NAMES["mcp_connection"],
                           "allowed_tools": ["find_activities"]},
        },
        "response_format": {"name": "livewell_evidence", "schema": lw.strict_schema(lw.evidence_schema())},
    })


FILES = {
    SCHEMAS_DIR / "lab1-answer.schema.json": lambda: schema_file("livewell_answer", lw.lab1_schema),
    SCHEMAS_DIR / "lab1-intake.schema.json": lambda: schema_file("livewell_intake", lw.intake_schema),
    SCHEMAS_DIR / "lab3-evidence.schema.json": lambda: schema_file("livewell_evidence", lw.evidence_schema),
    HOSTED_FILE: hosted_file,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="fail if a file is missing or out of date")
    args = ap.parse_args()
    stale = []
    for path, render in FILES.items():
        text = render()
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == text:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if args.check:
            stale.append(rel)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
            print(f"wrote {rel}")
    if stale:
        print("stale or missing: " + ", ".join(stale) + " -> run python scripts/gen-schemas.py")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
