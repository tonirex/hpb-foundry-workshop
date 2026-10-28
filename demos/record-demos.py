#!/usr/bin/env python3
"""Record one 🟢 Navigator demo video per lab from the live portal (headed Edge, 1440x900 WebM).

    python demos/record-demos.py --lab lab-00            # one lab
    python demos/record-demos.py --lab lab-00 lab-01 lab-02 lab-03
    python demos/record-demos.py                          # all five labs; live model calls

Output: demos/videos/<lab>-<YYYY-MM-DD>.webm (git-ignored; share the files with the co-facilitators). The
videos walk the facilitator demo agents (livewell-demo-*, livewell-workshop-hosted) with captions at the
bottom; nothing is saved in the portal. The sign-in pages are blanked and the account button is hidden, and
IDs, endpoints and e-mails are rewritten in the page, but watch each video once before sharing it.
Prerequisites as for capture-screenshots.py (`python demos/portal.py login`, create-demo-agents.py).
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import shutil
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import portal as P  # noqa: E402
import scenes as S  # noqa: E402

OUT = P.ROOT / "demos" / "videos"
TITLES = {
    "lab-00": "Lab 0 · First agent: the LiveWell Coach on gpt-5-mini",
    "lab-01": "Lab 1 · Grounding in the LiveWell guides (Foundry IQ)",
    "lab-02": "Lab 2 · Red flags, guardrails and evaluation",
    "lab-03": "Lab 3 · Profile tool, activities MCP, memory and Fabric IQ",
    "lab-04": "Lab 4 · The hosted LiveWell Coach team",
}


def record(pw, lab: str) -> pathlib.Path | None:
    tmp = OUT / f".raw-{lab}"
    shutil.rmtree(tmp, ignore_errors=True)
    ctx, page = P.open_portal(pw, headless=False, video_dir=tmp, cloak_login=True)
    run = S.Run(page, mode="video", log=lambda m: print(m, flush=True))
    started = time.time()
    run.say(TITLES[lab], 4)
    for name in S.VIDEOS[lab]:
        fn, _ = S.SCENES[name]
        print(f"[record] {lab}: scene {name}", flush=True)
        with run.soft(f"{lab} scene {name}"):
            fn(run)
    run.say("End of demo", 3)
    video = page.video
    raw = pathlib.Path(video.path()) if video else None
    ctx.close()
    if raw is None or not raw.exists():
        print(f"[record] {lab}: no video")
        return None
    out = OUT / f"{lab}-{dt.date.today():%Y-%m-%d}.webm"
    # A persistent context takes the browser down with it, so move the finished file instead of Video.save_as.
    shutil.move(str(raw), out)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"[record] {lab}: {out.relative_to(P.ROOT)} ({out.stat().st_size / 1e6:.1f} MB, "
          f"{(time.time() - started) / 60:.1f} min)", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lab", nargs="*", choices=sorted(S.VIDEOS), help="default: all labs")
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright

    done = {}
    with sync_playwright() as pw:
        for lab in args.lab or sorted(S.VIDEOS):
            done[lab] = record(pw, lab)
    print("\n| Lab | Video | Size |\n|---|---|---|")
    for lab, path in done.items():
        size = f"{path.stat().st_size / 1e6:.1f} MB" if path else "-"
        print(f"| {lab} | `{path.relative_to(P.ROOT) if path else 'failed'}` | {size} |")
    return 0 if all(done.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
