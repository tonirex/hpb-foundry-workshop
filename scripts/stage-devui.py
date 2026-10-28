#!/usr/bin/env python3
"""Stage the Lab 4 DevUI build context: copy demos/lab4-devui.py and the files it reads into demos/devui-aca/app/.

Run by the azd prepackage hook of the `lab4-devui` service (azure.yaml). The copies keep the repo layout, so
livewell_common finds content/ exactly as it does on a laptop. demos/devui-aca/app/ is git-ignored.
Standard library only.
"""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "demos" / "devui-aca" / "app"
FILES = [
    "demos/lab4-devui.py",
    "content/assets/common/__init__.py",
    "content/assets/common/livewell_common.py",
    "scripts/lib/wsconfig.py",
    "content/config/workshop.yaml",
    "content/prompts/test-prompts.json",
    "content/prompts/coach-instructions.md",
    "content/data/citizens.json",
]
# The Coach's evidence schema only accepts these ids (livewell_common.guide_ids()); without them the enum is
# empty and the hosted Coach can only return "supporting_guides": [].
GLOBS = ["content/knowledge/livewell-guides/lg-*.md"]


def main() -> int:
    if APP.exists():
        shutil.rmtree(APP)
    files = FILES + [p.relative_to(ROOT).as_posix() for g in GLOBS for p in sorted(ROOT.glob(g))]
    if not any(f.startswith("content/knowledge/") for f in files):
        print("[stage-devui] no LiveWell guides found under content/knowledge/livewell-guides/")
        return 1
    for rel in files:
        dst = APP / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)
    print(f"[stage-devui] {len(files)} files -> {APP.relative_to(ROOT).as_posix()}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
