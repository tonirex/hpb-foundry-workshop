#!/usr/bin/env python3
"""Print one sign-in card per participant: an A4 PDF to hand out (or send) before the workshop.

    python scripts/tenant/sign-in-cards.py [env] --lab-accounts [--with-tap]   # hpb.labNN accounts from
                                                                              # .azure/<env>/lab-accounts.csv
    python scripts/tenant/sign-in-cards.py [env] --file attendees.txt [--password <temporary password>]

How people sign in is environments.<env>.lab_accounts.sign_in in workshop.yaml, and the card follows it:

  tap       (mcaps) the card shows the username, a Temporary Access Pass line, a valid-until line (the tenant's local
            time, read from .azure/<env>/tap-issued.csv when that file knows the account) and the sign-in steps: enter
            the pass when asked for a password, do not register Authenticator, stop and ask if a method must be set up.
            The pass line is BLANK for hand-writing, so cards can be printed before the passes are issued; --with-tap
            prints each pass from tap-issued.csv instead (scripts/tenant/issue-tap.sh issue --apply writes it) and
            stops if any account has none or an expired one. A pass is a secret: with --with-tap the PDF is as
            sensitive as a password list. UNVERIFIED: that `az login` (browser or --use-device-code) accepts a pass in
            this tenant or in Codespaces.
  password  (sponsor) the card shows a temporary password and the Authenticator steps, as before.

--file takes one UPN per line ('#' comments allowed), the same file as seed-attendees.sh; in password mode it also takes
one shared temporary password (asked for when --password is left out). Display names come from Entra (az ad user show)
and fall back to the UPN. The cards can hold secrets, so the PDF goes to the gitignored .azure/<env>/sign-in-cards.pdf
and nothing is printed. Needs fpdf2 (requirements.txt).
"""
from __future__ import annotations

import argparse
import csv
import getpass
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import issue_tap  # noqa: E402
import wsconfig  # noqa: E402
from lab_users import lab_settings  # noqa: E402

NAVY, TEAL, PALE_TEAL, GREY = (11, 46, 89), (15, 124, 140), (225, 242, 244), (90, 90, 90)
CORE_FONT_MAP = {"\u2014": "-", "\u2013": "-", "\u2026": "...", "\u2192": ">", "\u2018": "'", "\u2019": "'",
                 "\u201c": '"', "\u201d": '"', "\u00a0": " "}
BLANK = "_" * 24  # a line to write on by hand
TAP_INSTRUCTION = ("Enter your Temporary Access Pass when asked for a password. Do not register Authenticator. "
                   "If the sign-in page asks you to set up a method, stop and ask the facilitator.")
TAP_FOOTER = ("Your Temporary Access Pass is a secret: do not photograph this card or share it. "
              "Ask a facilitator if anything does not work.")


def latin1(text: str) -> str:
    """The PDF core fonts are Latin-1 only."""
    text = "".join(CORE_FONT_MAP.get(c, c) for c in str(text))
    return text.encode("latin-1", "replace").decode("latin-1")


def run(cmd: list[str]) -> str:
    try:
        proc = subprocess.run([shutil.which(cmd[0]) or cmd[0], *cmd[1:]], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def env_name(arg: str | None) -> str:
    env = arg or os.environ.get("AZURE_ENV_NAME") or run(["azd", "env", "get-value", "AZURE_ENV_NAME"])
    if not env or " " in env:
        sys.exit("[sign-in-cards] no environment: pass it (sponsor | mcaps) or select one with azd env select")
    return env


def display_name(upn: str) -> str:
    name = run(["az", "ad", "user", "show", "--id", upn, "--query", "displayName", "-o", "tsv"])
    return name or " ".join(p.capitalize() for p in upn.split("@")[0].replace("_", ".").split("."))


def read_upns(path: Path) -> list[str]:
    upns = [line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return [u for u in upns if u]


class Cards(FPDF):
    def __init__(self, cfg: dict, mode: str = "password"):
        super().__init__(format="A4")
        self.cfg = cfg
        self.mode = mode  # "password" or "tap": environments.<env>.lab_accounts.sign_in
        self.set_margins(18, 16, 18)
        self.set_auto_page_break(True, 14)

    def heading(self, text: str) -> None:
        self.ln(4)
        self.set_text_color(*TEAL)
        self.set_font("Helvetica", "B", 13)
        self.cell(0, 8, latin1(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)

    def numbered(self, items: list[str]) -> None:
        self.set_font("Helvetica", "", 11.5)
        for i, item in enumerate(items, 1):
            self.cell(7, 6.5, f"{i}.")
            self.multi_cell(0, 6.5, latin1(item), align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(1)

    def bullets(self, items: list[str | tuple[str, str]]) -> None:
        """Items are text, or (text, command) to print the command on its own line in a code font."""
        for item in items:
            text, command = item if isinstance(item, tuple) else (item, "")
            self.set_font("Helvetica", "", 11.5)
            self.cell(7, 6.5, "-")
            self.multi_cell(0, 6.5, latin1(text), align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            if command:
                self.set_x(self.l_margin + 12)
                self.set_font("Courier", "B", 11)
                self.cell(0, 7, latin1(command), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(1)

    def fit_mono(self, text: str, width: float, size: float = 13) -> None:
        """Courier bold, shrunk until a long username fits the box."""
        while size > 8:
            self.set_font("Courier", "B", size)
            if self.get_string_width(text) <= width:
                return
            size -= 0.5

    def card(self, name: str, upn: str, secret: str = "", valid_until: str = "") -> None:
        """secret: the temporary password (password mode) or the Temporary Access Pass (tap mode; blank = a line to
        write it on). valid_until: tap mode only, already formatted in local time (blank = a line to write on)."""
        tap = self.mode == "tap"
        ws, names = self.cfg["workshop"], self.cfg["names"]
        self.add_page()
        width = self.w - self.l_margin - self.r_margin

        self.set_fill_color(*NAVY)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 17)
        self.cell(0, 12, latin1(ws["name"]), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        self.set_font("Helvetica", "", 11)
        when = "" if str(ws.get("date", "TODO")).upper() == "TODO" else f"  |  {ws['date']}"
        self.cell(0, 8, latin1(f"{ws['customer']}{when}"), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        self.set_text_color(0, 0, 0)
        self.ln(6)

        if tap:
            rows = [("Username", upn), ("Temporary Access Pass", secret or BLANK),
                    ("Valid until", valid_until or BLANK)]
            label_w = 54
            note = "This pass is for this workshop only and stops working at the time above."
        else:
            rows = [("Username", upn), ("Temporary password", secret)]
            label_w = 42
            note = "The temporary password works once: you choose your own at first sign-in."
        box_h = 24 + 9 * len(rows)  # 42 mm for the two password rows

        top = self.get_y()
        self.set_fill_color(*PALE_TEAL)
        self.set_draw_color(*TEAL)
        self.rect(self.l_margin, top, width, box_h, style="DF")
        self.set_xy(self.l_margin + 6, top + 4)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*NAVY)
        self.cell(0, 7, latin1(f"Your workshop account: {name}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)
        for label, value in rows:
            self.set_x(self.l_margin + 6)
            self.set_font("Helvetica", "", 11)
            self.cell(label_w, 9, latin1(label))
            self.fit_mono(latin1(value), width - 6 - label_w - 4)
            self.cell(0, 9, latin1(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(self.l_margin + 6)
        self.set_font("Helvetica", "I", 9)
        self.set_text_color(*GREY)
        self.cell(0, 6, note, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)
        self.set_y(top + box_h + 4)

        repo = str(ws.get("repo_url") or "").strip()
        if repo:
            self.heading("Lab instructions")
            self.set_font("Courier", "B", 12)
            self.cell(0, 7, latin1(repo), link=repo, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("Helvetica", "", 11.5)
            self.cell(0, 6.5, "Start with the README, then Lab 0.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        laptop = "Use your personal laptop: government (WOG) devices cannot sign in to the workshop tenant."
        private = ("Open a private browser window (Edge: InPrivate, Chrome: Incognito) so your work account stays out "
                   "of the way.")
        portal = ("You are in when the Azure portal opens. Then open https://ai.azure.com in the same window: the project "
                  f"{names['foundry_project']} should be listed. If it is not, wait 5 minutes and sign in again.")
        if tap:
            self.heading("Signing in")
            self.numbered([
                f"{laptop} {private}",
                "Go to portal.azure.com and sign in with the username above.",
                TAP_INSTRUCTION,
                portal,
            ])
        else:
            self.heading("Before the workshop (about 5 minutes)")
            self.numbered([
                laptop,
                private,
                "Go to portal.azure.com and sign in with the username and temporary password above.",
                "Choose a new password when you are asked, and remember it.",
                "If you are asked for more information, install Microsoft Authenticator on your phone, tap "
                "+ > Work or school account > Scan QR code, and follow the prompts.",
                portal,
            ])

        self.heading("During the workshop")
        tips: list[str | tuple[str, str]] = [
            "Use this account, not your work account, everywhere the labs say \"your workshop account\": the "
            "Foundry portal, Fabric and the terminal.",
            ("Builder rail: sign in to Azure in the terminal with this account:",
             "az login --use-device-code --allow-no-subscriptions"),
            "Name your agents livewell-<your initials>, and never edit the livewell-demo-* agents.",
        ]
        wifi = ws.get("guest_wifi") or {}
        if all(str(wifi.get(k, "TODO")).upper() != "TODO" for k in ("ssid", "code")):
            tips.append(f"Guest Wi-Fi: {wifi['ssid']} (code {wifi['code']}).")
        self.bullets(tips)

        self.ln(3)
        self.set_font("Helvetica", "I", 9)
        self.set_text_color(*GREY)
        footer = TAP_FOOTER if tap else "Keep this card to yourself. Ask a facilitator if anything does not work."
        self.multi_cell(0, 5, footer, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("env", nargs="?")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="one UPN per line (the same file as seed-attendees.sh --file)")
    src.add_argument("--lab-accounts", action="store_true", help="read .azure/<env>/lab-accounts.csv")
    ap.add_argument("--password",
                    help="password mode: the shared temporary password for --file (asked for when left out)")
    ap.add_argument("--with-tap", action="store_true",
                    help="tap mode: print each Temporary Access Pass from .azure/<env>/tap-issued.csv on its card "
                         "(default: a blank line to write it on by hand, so cards can be printed before issuing)")
    ap.add_argument("--out", help="PDF path (default .azure/<env>/sign-in-cards.pdf)")
    args = ap.parse_args(argv)

    env = env_name(args.env)
    cfg = wsconfig.load(env)
    settings = lab_settings(cfg, env)
    tap_mode = settings["sign_in"] == "tap"
    if args.with_tap and not tap_mode:
        sys.exit(f"[sign-in-cards] --with-tap is for sign_in: tap; environment '{env}' uses passwords")
    if args.password and tap_mode:
        sys.exit(f"[sign-in-cards] --password is for sign_in: password; environment '{env}' uses a Temporary "
                 "Access Pass")

    if args.lab_accounts:
        path = ROOT / ".azure" / env / "lab-accounts.csv"
        if not path.exists():
            sys.exit(f"[sign-in-cards] {path.relative_to(ROOT)} not found: run scripts/tenant/create-lab-users.sh {env}")
        with path.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not tap_mode and any("temporary_password" not in r for r in rows):
            sys.exit(f"[sign-in-cards] {path.relative_to(ROOT)} has no temporary_password column (it was written in "
                     f"tap mode): run scripts/tenant/create-lab-users.sh {env} for this environment")
        people = [(r["display_name"], r["upn"], "" if tap_mode else r["temporary_password"]) for r in rows]
    else:
        upns = read_upns(Path(args.file))
        if not upns:
            sys.exit(f"[sign-in-cards] no UPNs in {args.file}")
        password = "" if tap_mode else args.password or getpass.getpass("Temporary password for every account: ")
        people = [(display_name(u), u, password) for u in upns]

    cards = [(name, upn, secret, "") for name, upn, secret in people]
    if tap_mode:
        # Read the pass values only when asked for: without --with-tap they never leave the file.
        tap_path = issue_tap.tap_file_path(env, ROOT)
        issued = issue_tap.read_tap_file(tap_path, include_secret=args.with_tap)
        now = datetime.now(timezone.utc)
        cards, problems = [], []
        for name, upn, _ in people:
            row = issued.get(upn.lower())
            expires = issue_tap.parse_utc(row["expires_utc"]) if row else None
            valid_until = issue_tap.fmt_local(expires, settings["usage_location"]) if expires else ""
            tap = ""
            if args.with_tap:
                if not row:
                    problems.append(f"{upn}: not in {tap_path.relative_to(ROOT).as_posix()}")
                elif not row["tap"]:
                    problems.append(f"{upn}: the file has no pass value")
                elif expires is not None and expires <= now:
                    problems.append(f"{upn}: the pass expired at {issue_tap.fmt_utc(expires)}")
                else:
                    tap = row["tap"]
            cards.append((name, upn, tap, valid_until))
        if problems:
            more = f"\n  ... and {len(problems) - 10} more" if len(problems) > 10 else ""
            sys.exit(f"[sign-in-cards] --with-tap: {len(problems)} account(s) have no usable pass, so no PDF was "
                     "written:\n  " + "\n  ".join(problems[:10]) + more
                     + f"\nIssue them first: scripts/tenant/issue-tap.sh {env} issue --apply (--replace for expired "
                     "ones)")

    pdf = Cards(cfg, "tap" if tap_mode else "password")
    for card in cards:
        pdf.card(*card)
    out = Path(args.out) if args.out else ROOT / ".azure" / env / "sign-in-cards.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out))
    summary = f"[sign-in-cards] wrote {out} ({len(people)} card(s), one A4 page each)."
    if not tap_mode:
        print(f"{summary} It holds passwords: do not commit it.")
    elif args.with_tap:
        print(f"{summary} It holds Temporary Access Passes, which are secrets: do not commit or share it; hand out the "
              "cards, then delete the PDF.")
    else:
        print(f"{summary} The Temporary Access Pass lines are blank: write each pass on its card by hand, or re-run "
              "with --with-tap once the passes are issued.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
