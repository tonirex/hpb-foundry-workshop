#!/usr/bin/env python3
"""Playwright helpers for the new Foundry portal (ai.azure.com), shared by the demo recorder and the
screenshot capture. Also a small CLI for the one-time sign-in and for looking around the portal.

    python demos/portal.py login                 # headed Edge: sign in once (MFA), the profile is kept
    python demos/portal.py status                # is the saved session still signed in?
    python demos/portal.py open agents           # open a portal page (see ROUTES) headed, for a look around
    python demos/portal.py shot agent:livewell-demo-kb --out demos/runs/kb.png [--aria]

The browser profile lives in demos/.playwright/profile (git-ignored). Use the facilitator account for the
demo agents and videos; screenshots mask the account menu. After the first sign-in, later runs get through
'Pick an account' by themselves (LIVEWELL_PORTAL_ACCOUNT, default: the selected subscription's CLI user). Install once:
    python -m pip install -r requirements-demos.txt      (uses the installed Microsoft Edge, no download)
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import os
import pathlib
import re
import sys
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "content" / "assets"))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from common import livewell_common as lw  # noqa: E402  (loads the azd env: subscription, RG, account, project)

PROFILE_DIR = ROOT / "demos" / ".playwright" / "profile"
PORTAL = "https://ai.azure.com"
VIEWPORT = {"width": 1440, "height": 900}
# Masked in every screenshot and hidden in videos: the signed-in account (name, e-mail, avatar).
ACCOUNT_SELECTORS = ["button[aria-label='My profile settings']", "#mectrl_main_trigger", "[data-testid='account-manager']",
                     "button[aria-label*='Account manager']", "button[aria-label*='account' i][aria-haspopup]"]
# Rewritten on screen (screenshots and videos): workshop pages show names only, never IDs, endpoints or e-mails.
ENDPOINT_SUFFIXES = r"services\.ai\.azure\.com|cognitiveservices\.azure\.com|openai\.azure\.com|search\.windows\.net|" \
                    r"blob\.core\.windows\.net|dfs\.core\.windows\.net|azurecontainerapps\.io|azurecr\.io|azurewebsites\.net"
NIL_GUID = "-".join("0" * n for n in (8, 4, 4, 4, 12))  # built, so check-content's GUID scan stays clean


def project_segment() -> str:
    """The portal's project route segment: base64url(subscription GUID bytes),rg,,account,project."""
    sub = os.environ.get("AZURE_SUBSCRIPTION_ID") or lw.account_id().split("/")[2]
    enc = base64.urlsafe_b64encode(uuid.UUID(sub).bytes).decode().rstrip("=")
    return ",".join([enc, os.environ["AZURE_RESOURCE_GROUP"], "", os.environ["AZURE_AI_ACCOUNT_NAME"],
                     os.environ.get("AZURE_AI_PROJECT_NAME") or lw.NAMES["foundry_project"]])


def url(route: str) -> str:
    """Portal URL for a short route: home, project, agents, agent:<name>[@version], knowledge, evaluations,
    guardrails, models, tools, traces, or any path starting with / (relative to the project)."""
    base = f"{PORTAL}/nextgen/r/{project_segment()}"
    if route in ("home", ""):
        link = f"{PORTAL}/nextgen"
    elif route == "project":
        link = f"{base}/home"
    elif route.startswith("agent:"):
        name, _, version = route[6:].partition("@")
        if not version:
            latest = lw.agent_by_name(name)
            version = str(latest.version) if latest is not None else "1"
        link = f"{base}/build/agents/{name}/build?version={version}"
    elif route.startswith("/"):
        link = base + route
    else:
        link = f"{base}/build/{route}"
    tenant = os.environ.get("AZURE_TENANT_ID")
    return f"{link}{'&' if '?' in link else '?'}tid={tenant}" if tenant else link


def launch(pw, *, headless: bool = False, video_dir: pathlib.Path | None = None, redacted: bool = True,
           cloak_login: bool = False):
    """Persistent Edge context. `redacted` rewrites IDs/endpoints/e-mails and hides the account button on the
    portal; `cloak_login` blanks the Microsoft sign-in pages (videos: the account picker shows an e-mail)."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    kw = {"channel": "msedge", "headless": headless, "viewport": VIEWPORT, "locale": "en-SG",
          "timezone_id": "Asia/Singapore", "color_scheme": "light", "args": ["--no-first-run"]}
    if video_dir:
        video_dir.mkdir(parents=True, exist_ok=True)
        kw.update(record_video_dir=str(video_dir), record_video_size=VIEWPORT)
    ctx = pw.chromium.launch_persistent_context(str(PROFILE_DIR), **kw)
    if redacted:
        ctx.add_init_script(redact_script())
    if cloak_login:
        ctx.add_init_script("if (/^login\\./.test(location.hostname)) document.documentElement.style.opacity = '0';")
    return ctx


def redaction_rules() -> list[tuple[str, str, str]]:
    """(regex, flags, replacement) applied to visible text: tenant/subscription IDs, service endpoints, e-mails."""
    rules = []
    for key in ("AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID"):
        if os.environ.get(key):
            rules.append((re.escape(os.environ[key]), "gi", NIL_GUID))
    rules += [
        (r"\b[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.(" + ENDPOINT_SUFFIXES + r")\b", "gi", "<endpoint>.$1"),
        # Any other GUID, whole or cut short by the UI (agent identity, blueprint and object IDs).
        (r"\b(?!0{8}-)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}(?:-[0-9a-f]{0,4}(?:-[0-9a-f]{0,12})?)?", "gi",
         NIL_GUID),
        # Real addresses only: the synthetic ones in the content (example.invalid, *.example, *.test) stay readable.
        (r"[A-Za-z0-9._%+-]+@(?![A-Za-z0-9.-]*\b(?:example|invalid|test)\b)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}",
         "g", "facilitator@livewell.example"),
        (r"\b[A-Za-z0-9-]+\.onmicrosoft\.com\b", "gi", "livewell.example"),
    ]
    return rules


def redact_script() -> str:
    """Init script: rewrite matching text nodes and input values now and whenever the page changes."""
    import json
    return """(() => {
  if (!location.hostname.endsWith('ai.azure.com')) return;
  const rules = %s.map(([p, f, r]) => [new RegExp(p, f), r]);
  const fix = s => { for (const [re, r] of rules) { re.lastIndex = 0; s = s.replace(re, r); } return s; };
  // Editors (CodeMirror) read DOM edits back into their document, so keep rewritten URLs valid there.
  const editable = n => n.parentElement && n.parentElement.closest('[contenteditable="true"]');
  const node = n => { const v = n.nodeValue; if (v && v.length > 6) {
    let f = fix(v); if (f !== v && editable(n)) f = f.replace(/<endpoint>/g, 'your-endpoint');
    if (f !== v) n.nodeValue = f; } };
  const walk = root => {
    if (!root) return;
    if (root.nodeType === 3) { node(root); return; }
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT); let n;
    while ((n = w.nextNode())) node(n);
    if (root.querySelectorAll) for (const el of root.querySelectorAll('input[readonly], input[disabled], textarea[readonly]')) {
      const f = fix(el.value || ''); if (f !== el.value) el.value = f;
    }
  };
  const start = () => {
    const css = document.createElement('style');
    css.textContent = %s + ' { visibility: hidden !important; }';
    document.head.appendChild(css);
    walk(document.body);
    new MutationObserver(ms => { for (const m of ms) {
      if (m.type === 'characterData') node(m.target); else m.addedNodes.forEach(walk);
    } }).observe(document.body, {subtree: true, childList: true, characterData: true});
  };
  if (document.body) start(); else document.addEventListener('DOMContentLoaded', start);
})();""" % (json.dumps(redaction_rules()), json.dumps(", ".join(ACCOUNT_SELECTORS)))


def signed_in(page, timeout: float = 45, *, wait_for_user: bool = False, verbose: bool = False):
    """The tab showing the loaded portal (any tab of the context), or None. Without wait_for_user, a bounce
    to the sign-in page is a fast None; with it (login), keep waiting while the facilitator signs in."""
    ctx = page.context
    deadline = time.time() + timeout
    last_report = 0.0
    login_since = None
    while time.time() < deadline:
        pages = [p for p in ctx.pages if not p.is_closed()]
        if not pages:
            return None
        for p in pages:
            if portal_loaded(p):
                return p
        if verbose and time.time() - last_report > 10:
            last_report = time.time()
            for p in pages:
                print(f"[portal]   tab: {describe(p)}", flush=True)
        on_login = all("login.microsoftonline.com" in p.url or "login.live.com" in p.url for p in pages)
        if on_login:
            for p in pages:
                pick_account(p)
        if not on_login:
            login_since = None
        elif login_since is None:
            login_since = time.time()
        # the sign-in page often redirects back by itself (saved session); give it a moment
        if on_login and not wait_for_user and time.time() - login_since > 25:
            return None
        time.sleep(1.5)
    return None


def portal_account() -> str | None:
    """Prefer LIVEWELL_PORTAL_ACCOUNT, otherwise the selected subscription's Azure CLI user."""
    global _ACCOUNT
    if _ACCOUNT is None:
        _ACCOUNT = os.environ.get("LIVEWELL_PORTAL_ACCOUNT") or None
        if not _ACCOUNT:
            import shutil
            import subprocess
            az = shutil.which("az") or shutil.which("az.cmd")
            if not az:
                raise SystemExit("Azure CLI is required to identify the portal account; set LIVEWELL_PORTAL_ACCOUNT explicitly.")
            cmd = [az, "account", "show", "--query", "user.name", "-o", "tsv"]
            if subscription := os.environ.get("AZURE_SUBSCRIPTION_ID"):
                cmd += ["--subscription", subscription]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode or not result.stdout.strip():
                raise SystemExit(f"Cannot identify the selected subscription's portal account: {result.stderr.strip()}")
            _ACCOUNT = result.stdout.strip()
    return _ACCOUNT or None


_ACCOUNT: str | None = None


def pick_account(page) -> bool:
    """Get through the sign-in pages that need no secrets: pick the facilitator's tile on 'Pick an account'
    (a restarted browser stops there when the account is not the Windows-connected one), 'Not now' on the
    security-info nudge, 'Yes' on 'Stay signed in?'. Password/MFA prompts are left to the facilitator."""
    if "login." not in page.url:
        return False
    with contextlib.suppress(Exception):
        text = page.locator("body").inner_text(timeout=1000)
        if re.search(r"stay signed in\?", text, re.I):
            with contextlib.suppress(Exception):
                page.get_by_label(re.compile(r"don.t show this again", re.I)).check(timeout=1000)
            page.get_by_role("button", name=re.compile(r"^yes$", re.I)).first.click(timeout=2000)
            time.sleep(3)
            return True
        if re.search(r"keep your account secure|more information required|set up another way", text, re.I):
            for name in (r"^not now$", r"^skip for now$", r"^ask later$"):
                loc = page.get_by_role("button", name=re.compile(name, re.I)).or_(
                    page.get_by_role("link", name=re.compile(name, re.I)))
                if loc.count():
                    loc.first.click(timeout=2000)
                    time.sleep(3)
                    return True
        account = portal_account()
        if account and re.search(r"pick an account", text, re.I):
            tile = page.get_by_text(re.compile(re.escape(account), re.I)).first
            if tile.is_visible(timeout=500):
                tile.click()
                time.sleep(3)
                return True
    return False


def describe(page) -> str:
    with contextlib.suppress(Exception):
        text = page.evaluate("() => (document.body && document.body.innerText || '').length")
        return f"{page.url[:110]} | title={page.title()[:50]!r} | text={text}"
    return page.url[:110]


def portal_loaded(page) -> bool:
    """On ai.azure.com (not a sign-in hop) with the app shell rendered: a real title and some visible text."""
    if not page.url.startswith(PORTAL) or "signin" in page.url.lower():
        return False
    with contextlib.suppress(Exception):
        title = page.title() or ""
        text = page.evaluate("() => (document.body && document.body.innerText || '').length")
        return "sign in" not in title.lower() and text > 150
    return False


def mask_locators(page) -> list:
    return [page.locator(s) for s in ACCOUNT_SELECTORS]


def hide_account(page) -> None:
    """Blank the account menu for videos (screenshots use Playwright's mask instead)."""
    css = ", ".join(ACCOUNT_SELECTORS) + " { visibility: hidden !important; }"
    with contextlib.suppress(Exception):
        page.add_style_tag(content=css)


def caption(page, text: str | None) -> None:
    """A small caption bar at the bottom of the page (used in the demo videos)."""
    script = """t => {
      let el = document.getElementById('livewell-caption');
      if (!t) { if (el) el.remove(); return; }
      if (!el) { el = document.createElement('div'); el.id = 'livewell-caption'; document.body.appendChild(el); }
      el.textContent = t;
      Object.assign(el.style, {position: 'fixed', left: '50%', bottom: '18px', transform: 'translateX(-50%)',
        background: 'rgba(17, 24, 39, .88)', color: '#fff', padding: '8px 16px', borderRadius: '8px',
        font: '600 15px Segoe UI, sans-serif', zIndex: 2147483647, maxWidth: '80%', textAlign: 'center',
        pointerEvents: 'none'});
    }"""
    with contextlib.suppress(Exception):
        page.evaluate(script, text)


def goto(page, route: str, settle: float = 2.0) -> None:
    page.goto(url(route), wait_until="domcontentloaded")
    with contextlib.suppress(Exception):
        page.wait_for_load_state("networkidle", timeout=20000)
    time.sleep(settle)


# --- chat in an agent playground ----------------------------------------------------------------------
CHAT_BOX = ["[role='textbox'][aria-label*='message the agent' i]", "textarea[placeholder*='message the agent' i]",
            "[aria-label*='message the agent' i]", "textarea[placeholder*='message' i]"]
STOP_BUTTONS = re.compile(r"^(stop|stop generating|cancel)$", re.I)


def chat_box(page, timeout: float = 30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for sel in CHAT_BOX:
            loc = page.locator(sel).last
            with contextlib.suppress(Exception):
                if loc.is_visible(timeout=500) and loc.is_editable(timeout=500):
                    return loc
        time.sleep(0.5)
    raise RuntimeError("chat message box not found (portal layout changed?)")


def click_first(page, names: list[str], roles: tuple[str, ...] = ("button", "tab", "menuitem", "link"),
                timeout: float = 5) -> bool:
    """Click the first visible control whose accessible name matches one of `names` (regex, case-insensitive)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for name in names:
            for role in roles:
                loc = page.get_by_role(role, name=re.compile(name, re.I))
                with contextlib.suppress(Exception):
                    if loc.count() and loc.first.is_visible(timeout=300):
                        loc.first.click()
                        return True
        time.sleep(0.4)
    return False


def new_chat(page) -> bool:
    ok = click_first(page, [r"^new chat$"], roles=("button",), timeout=8)
    time.sleep(1.5)
    return ok


def chat_panel(page):
    """The playground's chat tabpanel ('Chat' on prompt agents, unnamed on hosted agents)."""
    return page.get_by_role("tabpanel").filter(
        has=page.get_by_role("textbox", name=re.compile(r"message the agent", re.I))).last


def answers(page):
    """The agent's answer articles in the playground feed ('Copilot said:' / anything not 'You said:')."""
    return chat_panel(page).get_by_role("article").filter(has_not_text=re.compile(r"^\s*You said", re.I))


def reply_count(page) -> int:
    with contextlib.suppress(Exception):
        return answers(page).count()
    return 0


def last_answer(page) -> str:
    with contextlib.suppress(Exception):
        return answers(page).last.inner_text(timeout=3000)
    return ""


def approval_pending(page) -> bool:
    with contextlib.suppress(Exception):
        btn = chat_panel(page).get_by_role("button", name=re.compile(r"^approve$", re.I)).last
        return btn.is_visible(timeout=300) and btn.is_enabled(timeout=300)
    return False


def send(page, text: str, *, typing_delay: float = 12, timeout: float = 240) -> float:
    """Type a message, send it, and wait until the answer stops streaming (or asks for an approval)."""
    box = chat_box(page)
    box.click()
    if len(text) > 300:  # long prompts are pasted, not typed
        box.fill(text)
    else:
        box.press_sequentially(text, delay=typing_delay)
    start = time.time()
    before = reply_count(page)
    box.press("Enter")
    wait_for_answer(page, timeout=timeout, before=before)
    return time.time() - start


def wait_for_answer(page, timeout: float = 240, before: int | None = None) -> None:
    """Done when an approval card is waiting, or no Stop button is visible, the Send button is back and (if
    `before` is given) a new answer article exists - three quiet checks in a row."""
    time.sleep(3)
    deadline = time.time() + timeout
    quiet = 0
    while time.time() < deadline:
        if approval_pending(page):
            time.sleep(1)
            return
        busy = False
        with contextlib.suppress(Exception):
            busy = page.get_by_role("button", name=STOP_BUTTONS).first.is_visible(timeout=300)
        if not busy and before is not None:
            busy = reply_count(page) <= before
        quiet = 0 if busy else quiet + 1
        if quiet >= 3:
            return
        time.sleep(1)


def approve(page, *, deny: bool = False, timeout: float = 240, on_menu=None) -> bool:
    """Deny, or Approve → Approve once. The Approve button opens a menu (Approve once / Always approve this tool /
    Always approve all tools); `on_menu()` runs while it is open (e.g. to take a screenshot)."""
    button = chat_panel(page).get_by_role("button", name=re.compile(r"^deny$" if deny else r"^approve$", re.I)).last
    with contextlib.suppress(Exception):
        button.click(timeout=5000)
        time.sleep(1)
        once = page.get_by_role("menuitem", name=re.compile(r"^approve once$", re.I)).first
        if not deny and once.count() and once.is_visible(timeout=2000):
            if on_menu:
                on_menu()
            once.click(timeout=5000)
        wait_for_answer(page, timeout=timeout)
        return not approval_pending(page)
    return False


def open_trace(page, *, timeout: float = 240) -> bool:
    """Open the last answer's Traces dialog and wait until it has loaded. Traces take a minute or two to
    arrive, so an empty/still-loading dialog is closed and reopened until `timeout`."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with contextlib.suppress(Exception):
            chat_panel(page).get_by_role("button", name=re.compile(r"^traces$", re.I)).last.click(timeout=5000)
        dialog = page.get_by_role("dialog").last
        with contextlib.suppress(Exception):
            dialog.wait_for(state="visible", timeout=10000)
        until = min(deadline, time.time() + 45)
        while time.time() < until:
            loading = False
            with contextlib.suppress(Exception):
                loading = dialog.get_by_role("progressbar").first.is_visible(timeout=300)
            text = ""
            with contextlib.suppress(Exception):
                text = dialog.inner_text(timeout=2000)
            if not loading and len(text) > 200 and not re.search(r"no traces|no data|not found", text, re.I):
                time.sleep(2)
                return True
            time.sleep(2)
        close_dialog(page)
        time.sleep(10)
    return False


def trace_expand(page, rounds: int = 8) -> int:
    """Expand every collapsed row of an open trace dialog's tree; it sometimes opens with the agent span collapsed,
    which hides the tool spans. Returns how many rows were expanded."""
    tree = page.get_by_role("dialog").last.get_by_role("group", name=re.compile("trace tree", re.I))
    opened = 0
    for _ in range(rounds):
        row = tree.locator("[role=button][aria-expanded='false']").first
        try:
            if not row.count():
                break
            toggle = row.locator("[class*='toggleBtn']").first
            (toggle if toggle.count() else row).click(timeout=3000)
        except Exception:
            break
        opened += 1
        time.sleep(0.8)
    return opened


def trace_span(page, pattern: str) -> bool:
    """In an open trace dialog, select the first span whose label matches `pattern` (regex, case-insensitive).
    Agent and conversation rows are skipped (their labels carry the agent name, e.g. livewell-demo-fabric, and
    clicking one can collapse it) unless the pattern asks for invoke_agent."""
    trace_expand(page)
    tree = page.get_by_role("dialog").last.get_by_role("group", name=re.compile("trace tree", re.I))
    skip = None if re.search(r"invoke", pattern, re.I) else re.compile(r"^\s*(invoke\s*agent|conversation)\b", re.I)
    with contextlib.suppress(Exception):
        spans = tree.get_by_role("button", name=re.compile(pattern, re.I))
        for i in range(spans.count()):
            span = spans.nth(i)
            if skip and skip.search(span.inner_text(timeout=2000)):
                continue
            span.scroll_into_view_if_needed(timeout=3000)
            span.click(timeout=3000)
            time.sleep(2)
            return True
    return False


def trace_tab(page, name: str) -> bool:
    with contextlib.suppress(Exception):
        page.get_by_role("dialog").last.get_by_role("tab", name=re.compile(rf"^{name}$", re.I)).first.click(timeout=3000)
        time.sleep(1.5)
        return True
    return False


def trace_find(page, pattern: str) -> bool:
    """Scroll the trace dialog's right pane so the first text matching `pattern` is in view."""
    with contextlib.suppress(Exception):
        hit = page.get_by_role("dialog").last.get_by_text(re.compile(pattern, re.I)).first
        hit.scroll_into_view_if_needed(timeout=3000)
        hit.evaluate("el => el.scrollIntoView({block: 'center'})")
        time.sleep(1)
        return True
    return False


def scroll_instructions(page, *, to_end: bool = True) -> bool:
    """Scroll the Instructions box so its last block (or its start) is in view."""
    expand(page, "Instructions")
    return bool(page.evaluate("""end => {
      const el = [...document.querySelectorAll('textarea')].find(t => /prompt/i.test(t.placeholder || ''));
      if (!el) return false;
      el.scrollIntoView({block: 'center'}); el.scrollTop = end ? el.scrollHeight : 0; return true;
    }""", to_end))


def only_livewell_projects(page) -> None:
    """Project picker: hide the other projects of this tenant (shots show the workshop project only)."""
    with contextlib.suppress(Exception):
        page.evaluate("""() => document.querySelectorAll('[role=menuitemradio]').forEach(el => {
          if (!/livewell/i.test(el.textContent)) el.style.display = 'none'; })""")


def close_dialog(page) -> None:
    with contextlib.suppress(Exception):
        dialog = page.get_by_role("dialog").last
        if dialog.is_visible(timeout=500):
            close = dialog.get_by_role("button", name=re.compile(r"^close$", re.I))
            if close.count():
                close.first.click(timeout=2000)
            else:
                page.keyboard.press("Escape")
            time.sleep(1)


def expand(page, section: str, *, collapse: bool = False) -> bool:
    """Expand (or collapse) a configuration section button such as Knowledge, 'Memory Preview', Instructions."""
    loc = page.get_by_role("button", name=re.compile(rf"^{section}\b", re.I)).first
    with contextlib.suppress(Exception):
        loc.scroll_into_view_if_needed(timeout=3000)
        expanded = loc.get_attribute("aria-expanded", timeout=2000) == "true"
        if expanded == collapse:
            loc.click(timeout=3000)
            time.sleep(1)
        return True
    return False


def pick_model(page, name: str) -> bool:
    """Choose a model deployment in the agent's Model combobox (does not save the agent)."""
    with contextlib.suppress(Exception):
        page.get_by_role("combobox", name=re.compile(r"^model", re.I)).first.click(timeout=5000)
        time.sleep(1)
        page.get_by_role("option", name=re.compile(re.escape(name), re.I)).first.click(timeout=8000)
        time.sleep(1.5)
        return True
    page.keyboard.press("Escape")
    return False


def screenshot(page, out: pathlib.Path, *, full_page: bool = False, element=None) -> pathlib.Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    kw = {"path": str(out), "mask": mask_locators(page), "mask_color": "#F3F4F6", "animations": "disabled"}
    if element is not None:
        element.screenshot(**kw)
    else:
        page.screenshot(full_page=full_page, **kw)
    return out


def aria(page) -> str:
    with contextlib.suppress(Exception):
        return page.locator("body").aria_snapshot()
    return ""


def open_portal(pw, *, headless: bool = False, video_dir: pathlib.Path | None = None, cloak_login: bool = False,
                route: str = "project"):
    """Launch, open `route` and get through 'Pick an account'. Returns (context, page); raises when the saved
    session has expired (run `python demos/portal.py login`)."""
    ctx = launch(pw, headless=headless, video_dir=video_dir, cloak_login=cloak_login)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(url(route), wait_until="domcontentloaded")
    found = signed_in(page, timeout=120)
    if found is None:
        ctx.close()
        raise SystemExit("[portal] NOT signed in - run: python demos/portal.py login")
    for extra in ctx.pages:
        if extra is not found and not extra.is_closed():
            with contextlib.suppress(Exception):
                extra.close()
    time.sleep(2)
    return ctx, found


# --- CLI -------------------------------------------------------------------------------------------------
def main() -> int:
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    lg = sub.add_parser("login", help="headed sign-in; wait until the portal loads, then keep the profile")
    lg.add_argument("--explore", nargs="*", metavar="ROUTE",
                    help="after sign-in, save a screenshot + accessibility tree of each route to demos/runs/")
    st = sub.add_parser("status", help="check that the saved session is still signed in")
    st.add_argument("--headless", action="store_true")
    o = sub.add_parser("open", help="open a route headed and wait until you close the window")
    o.add_argument("route", nargs="?", default="project")
    s = sub.add_parser("shot", help="screenshot a route")
    s.add_argument("route")
    s.add_argument("--out", required=True)
    s.add_argument("--headless", action="store_true")
    s.add_argument("--aria", action="store_true", help="also print the page's accessibility tree")
    s.add_argument("--wait", type=float, default=4.0)
    args = ap.parse_args()

    with sync_playwright() as pw:
        if args.cmd == "login":
            ctx = launch(pw, headless=False)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(url("project"))
            print("[portal] sign in in the Edge window (choose 'Stay signed in'); waiting up to 10 minutes ...", flush=True)
            found = signed_in(page, timeout=600, wait_for_user=True, verbose=True)
            ok = found is not None
            page = found or page
            print(f"[portal] {'signed in' if ok else 'NOT signed in'}"
                  + (f": {page.url[:120]}" if not page.is_closed() else " (window closed)"), flush=True)
            if ok:
                for route in args.explore or []:
                    stem = re.sub(r"[^a-z0-9]+", "-", route.lower()).strip("-")
                    goto(page, route, settle=6)
                    screenshot(page, ROOT / "demos" / "runs" / f"explore-{stem}.png")
                    (ROOT / "demos" / "runs" / f"explore-{stem}.aria.txt").write_text(
                        page.url + "\n" + aria(page), encoding="utf-8")
                    print(f"[portal] explored {route}: {page.url[:120]}", flush=True)
                time.sleep(20)  # cookies are written to disk periodically; close gracefully afterwards
            ctx.close()
            return 0 if ok else 1
        if args.cmd == "status":
            ctx = launch(pw, headless=args.headless)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(url("project"))
            ok = signed_in(page, timeout=60, verbose=True) is not None
            print(f"[portal] {'signed in' if ok else 'NOT signed in - run: python demos/portal.py login'}")
            ctx.close()
            return 0 if ok else 1
        if args.cmd == "open":
            ctx = launch(pw, headless=False)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            goto(page, args.route)
            print("[portal] close the browser window when you are done", flush=True)
            with contextlib.suppress(Exception):
                page.wait_for_event("close", timeout=0)
            ctx.close()
            return 0
        ctx = launch(pw, headless=args.headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        goto(page, args.route, settle=args.wait)
        print(f"[portal] {page.url}")
        screenshot(page, pathlib.Path(args.out))
        if args.aria:
            print(aria(page))
        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
