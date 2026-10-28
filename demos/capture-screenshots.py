#!/usr/bin/env python3
"""Capture numbered Navigator screenshots referenced by the canonical lab pages.

    python demos/capture-screenshots.py --list-missing        # which slots have no PNG yet (no browser)
    python demos/capture-screenshots.py --list-outdated       # reviewed historical captures (no browser)
    python demos/capture-screenshots.py --outdated-only --dry-run  # inspect the exact retake selection offline
    python demos/capture-screenshots.py --outdated-only       # retake only that subset after sign-in
    python demos/capture-screenshots.py --only lab-00/08       # retake a reviewed, outdated screenshot
    python demos/capture-screenshots.py --only lab-01          # one lab
    python demos/capture-screenshots.py --only lab-03/12 lab-03/13
    python demos/capture-screenshots.py --link                 # turn filled slots into markdown images

Prerequisites: `python demos/portal.py login` once (facilitator account), and the demo agents from
`python demos/create-demo-agents.py`. Scenes chat with the livewell-demo-* agents and the hosted agent, open
menus and dialogs and cancel them; nothing is saved. Tenant/subscription IDs, endpoints and e-mails are
rewritten in the page and the account button is masked before each shot. Review every PNG before committing.
PNGs go to content/labs/screenshots/lab-0N/. Use --only for a selective refresh.
Unillustrated participant steps are text-only; do not create new captures just to fill them.
DevUI screenshots are owned by demos/lab4-devui.py --capture, not portal scenes.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import portal as P  # noqa: E402
import scenes as S  # noqa: E402


def status_rows(results: dict[str, str] | None = None) -> list[tuple[str, str, str]]:
    rows = []
    for sid, slot in sorted(S.slots().items()):
        if results and sid in results:
            state = results[sid]
        elif slot.file.exists():
            state = "present"
        elif sid in S.MANUAL:
            state = "manual: " + S.MANUAL[sid]
        elif sid in S.EXTERNAL_CAPTURE:
            state = "missing: use demos/lab4-devui.py --capture"
        else:
            state = "missing"
        rows.append((sid, slot.path, state))
    return rows


def link(dry_run: bool = False) -> int:
    """Rewrite every slot whose PNG exists as `![caption](path)`; slots without a PNG stay as slots."""
    changed = 0
    for md in S.slot_pages():
        lines = md.read_text(encoding="utf-8").split("\n")
        out = []
        for line in lines:
            m = S.SLOT_RE.match(line)
            if m and (S.LABS / m["path"]).exists():
                line = f"{m['indent']}![{m['caption']}]({m['path']})"
                changed += 1
            out.append(line)
        if not dry_run and out != lines:
            md.write_bytes("\n".join(out).encode("utf-8"))  # LF on Windows too
    print(f"[capture] linked {changed} slot(s){' (dry run)' if dry_run else ''}")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="+", metavar="SLOT", help="lab-0N or lab-0N/NN (several allowed)")
    ap.add_argument("--list-missing", action="store_true", help="print the slots without a PNG and exit")
    ap.add_argument("--list-outdated", action="store_true", help="list historical captures awaiting refresh/review")
    ap.add_argument("--link", action="store_true", help="convert filled slots into markdown images and exit")
    ap.add_argument("--dry-run", action="store_true", help="list selected captures without a browser; with --link: count only")
    ap.add_argument("--missing-only", action="store_true", help="capture only slots that have no PNG yet")
    ap.add_argument("--outdated-only", action="store_true", help="capture only images marked historical in the guides")
    ap.add_argument("--headless", action="store_true", help="no browser window (the default is headed Edge)")
    args = ap.parse_args()

    if args.list_outdated:
        historical = S.historical_paths()
        rows = [slot for slot in S.slots().values() if slot.path in historical]
        for slot in sorted(rows, key=lambda slot: slot.id):
            print(f"{slot.id:10} {slot.path}")
        print(f"[capture] {len(rows)} historical screenshots await refresh/review; use --only with these IDs")
        return int(bool(rows))
    if args.link:
        link(args.dry_run)
        return 0
    if args.list_missing:
        rows = [r for r in status_rows() if r[2] != "present"]
        for sid, path, state in rows:
            print(f"{sid:10} {state:60} {path}")
        print(f"[capture] {len(rows)} of {len(S.slots())} referenced screenshots have no PNG")
        return int(bool(rows))

    only = set(args.only) if args.only else None
    if only:
        known = set(S.slots()) | {sid.split("/")[0] for sid in S.slots()}
        if unknown := only - known:
            ap.error("unknown screenshot selection: " + ", ".join(sorted(unknown)))
        if external := only & S.EXTERNAL_CAPTURE:
            ap.error("DevUI captures use demos/lab4-devui.py --capture: " + ", ".join(sorted(external)))
    if args.outdated_only:
        historical = S.historical_paths()
        outdated = {sid for sid, slot in S.slots().items() if slot.path in historical}
        only = {sid for sid in outdated if sid in only or sid.split("/")[0] in only} if only else outdated
    if args.missing_only:
        missing = {sid for sid, _, state in status_rows() if state == "missing"}
        only = {sid for sid in missing if sid in only or sid.split("/")[0] in only} if only is not None else missing
    if args.dry_run:
        selected = [
            slot for sid, slot in sorted(S.slots().items())
            if sid not in S.EXTERNAL_CAPTURE and (only is None or sid in only or sid.split("/")[0] in only)
        ]
        for slot in selected:
            print(f"{slot.id:10} {slot.path}")
        print(f"[capture] dry run: {len(selected)} selected; no browser, model calls or files changed")
        return 0
    wanted = [name for name, (_, ids) in S.SCENES.items()
              if only is None or any(sid in only or sid.split("/")[0] in only for sid in ids)]
    if not wanted:
        print("[capture] nothing to capture")
        return 0

    from playwright.sync_api import sync_playwright

    started = time.time()
    with sync_playwright() as pw:
        ctx, page = P.open_portal(pw, headless=args.headless)
        run = S.Run(page, mode="shots", only=only, log=lambda m: print(m, flush=True))
        for name in wanted:
            fn, ids = S.SCENES[name]
            print(f"[capture] scene {name}", flush=True)
            with run.soft(f"scene {name}", *ids):
                fn(run)
        ctx.close()

    selected = [sid for sid in S.slots() if run.selected(sid) and sid not in S.EXTERNAL_CAPTURE]
    for sid in selected:
        if sid not in run.results:
            run.results[sid] = "manual: " + S.MANUAL[sid] if sid in S.MANUAL else "not captured"
    print(f"\n| Slot | File | Result |\n|---|---|---|")
    for sid, path, state in status_rows(run.results):
        if sid in selected:
            print(f"| {sid} | `{path}` | {state} |")
    ok = sum(1 for sid in selected if run.results[sid].startswith("captured"))
    print(f"\n[capture] {ok}/{len(selected)} captured in {(time.time() - started) / 60:.1f} min - review the PNGs "
          "before publishing image links; --link converts legacy slots only")
    return int(any(not run.results[sid].startswith("captured") for sid in selected))


if __name__ == "__main__":
    raise SystemExit(main())
