#!/usr/bin/env python3
"""Print one sign-in card per participant: an A4 PDF to hand out (or send) before the workshop.

    python scripts/tenant/sign-in-cards.py [env] --file attendees.txt [--password <temporary password>]
    python scripts/tenant/sign-in-cards.py [env] --lab-accounts      # hpb.labNN accounts and their passwords
                                                                    # from .azure/<env>/lab-accounts.csv

--file takes one UPN per line ('#' comments allowed), the same file as seed-attendees.sh, and one shared temporary
password (asked for when --password is left out). Display names come from Entra (az ad user show) and fall back to
the UPN. The cards hold passwords, so the PDF goes to the gitignored .azure/<env>/sign-in-cards.pdf and nothing is
printed. Needs fpdf2 (requirements.txt).
"""
from __future__ import annotations

import argparse
import csv
import getpass
import os
import shutil
import subprocess
import sys
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import wsconfig  # noqa: E402

NAVY, TEAL, PALE_TEAL, GREY = (11, 46, 89), (15, 124, 140), (225, 242, 244), (90, 90, 90)
CORE_FONT_MAP = {"\u2014": "-", "\u2013": "-", "\u2026": "...", "\u2192": ">", "\u2018": "'", "\u2019": "'",
                 "\u201c": '"', "\u201d": '"', "\u00a0": " "}


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
    def __init__(self, cfg: dict):
        super().__init__(format="A4")
        self.cfg = cfg
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

    def card(self, name: str, upn: str, password: str) -> None:
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

        top = self.get_y()
        self.set_fill_color(*PALE_TEAL)
        self.set_draw_color(*TEAL)
        self.rect(self.l_margin, top, width, 42, style="DF")
        self.set_xy(self.l_margin + 6, top + 4)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*NAVY)
        self.cell(0, 7, latin1(f"Your workshop account: {name}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)
        for label, value in (("Username", upn), ("Temporary password", password)):
            self.set_x(self.l_margin + 6)
            self.set_font("Helvetica", "", 11)
            self.cell(42, 9, latin1(label))
            self.fit_mono(latin1(value), width - 6 - 42 - 4)
            self.cell(0, 9, latin1(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(self.l_margin + 6)
        self.set_font("Helvetica", "I", 9)
        self.set_text_color(*GREY)
        self.cell(0, 6, "The temporary password works once: you choose your own at first sign-in.",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)
        self.set_y(top + 46)

        repo = str(ws.get("repo_url") or "").strip()
        if repo:
            self.heading("Lab instructions")
            self.set_font("Courier", "B", 12)
            self.cell(0, 7, latin1(repo), link=repo, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("Helvetica", "", 11.5)
            self.cell(0, 6.5, "Start with the README, then Lab 0.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.heading("Before the workshop (about 5 minutes)")
        self.numbered([
            "Use your personal laptop: government (WOG) devices cannot sign in to the workshop tenant.",
            "Open a private browser window (Edge: InPrivate, Chrome: Incognito) so your work account stays out of the way.",
            "Go to portal.azure.com and sign in with the username and temporary password above.",
            "Choose a new password when you are asked, and remember it.",
            "If you are asked for more information, install Microsoft Authenticator on your phone, tap "
            "+ > Work or school account > Scan QR code, and follow the prompts.",
            "You are in when the Azure portal opens. Then open https://ai.azure.com in the same window: the project "
            f"{names['foundry_project']} should be listed. If it is not, wait 5 minutes and sign in again.",
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
        self.multi_cell(0, 5, "Keep this card to yourself. Ask a facilitator if anything does not work.",
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("env", nargs="?")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="one UPN per line (the same file as seed-attendees.sh --file)")
    src.add_argument("--lab-accounts", action="store_true", help="read .azure/<env>/lab-accounts.csv")
    ap.add_argument("--password", help="the shared temporary password for --file (asked for when left out)")
    ap.add_argument("--out", help="PDF path (default .azure/<env>/sign-in-cards.pdf)")
    args = ap.parse_args()

    env = env_name(args.env)
    cfg = wsconfig.load(env)
    if args.lab_accounts:
        path = ROOT / ".azure" / env / "lab-accounts.csv"
        if not path.exists():
            sys.exit(f"[sign-in-cards] {path.relative_to(ROOT)} not found: run scripts/tenant/create-lab-users.sh {env}")
        people = [(r["display_name"], r["upn"], r["temporary_password"]) for r in csv.DictReader(path.open(encoding="utf-8"))]
    else:
        upns = read_upns(Path(args.file))
        if not upns:
            sys.exit(f"[sign-in-cards] no UPNs in {args.file}")
        password = args.password or getpass.getpass("Temporary password for every account: ")
        people = [(display_name(u), u, password) for u in upns]

    pdf = Cards(cfg)
    for name, upn, password in people:
        pdf.card(name, upn, password)
    out = Path(args.out) if args.out else ROOT / ".azure" / env / "sign-in-cards.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out))
    print(f"[sign-in-cards] wrote {out} ({len(people)} card(s), one A4 page each). It holds passwords: do not commit it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
