"""Portal scenes shared by demos/capture-screenshots.py and demos/record-demos.py.

A scene walks one part of the 🟢 Navigator portal track on a facilitator demo agent (livewell-demo-*,
livewell-workshop-hosted). In "shots" mode it saves the numbered screenshots of the canonical lab pages, Fabric step and Bridge spotlight; in
"video" mode it shows captions and types slowly. Scenes never save an agent: menus and dialogs are opened,
captured and cancelled, and the Lab 0 model switch is discarded by reloading the page.
"""
from __future__ import annotations

import contextlib
import dataclasses
import importlib.util
import json
import pathlib
import re
import time

import portal as P

ROOT = P.ROOT
LABS = ROOT / "content" / "labs"
RUNS = ROOT / "demos" / "runs"
PROMPTS = json.loads((ROOT / "content" / "prompts" / "test-prompts.json").read_text(encoding="utf-8"))["prompts"]
# Same explicit confirmation after discovery as the Builder rail (content/assets/lab3_tools.py).
SIGNUP_YES = P.lw.prompt_text("lab3_signup_confirm")
FIT = json.loads((ROOT / "content" / "fabric" / "reference-answers.json").read_text(encoding="utf-8"))["q_programme_fit"]
PROGRAMME_YES = P.lw.prompt_text("lab3_programme_confirm")

SLOT_ID = r"(?:lab-0\d|bridge)/\d\d[a-z]?"
SLOT_RE = re.compile(rf"^(?P<indent>\s*)> 📸 \*\*Screenshot slot\*\* · `(?P<path>screenshots/(?P<id>{SLOT_ID})-[^`]+\.png)`"
                     r" · (?P<caption>.+?)\s*$")
IMAGE_RE = re.compile(rf"^(?P<indent>\s*)!\[(?P<caption>[^\]]*)\]\((?P<path>screenshots/(?P<id>{SLOT_ID})-[^)]+\.png)\)\s*$")
HISTORICAL_RE = re.compile(
    rf"^\s*<!-- historical-screenshot: (?P<path>screenshots/(?P<id>{SLOT_ID})-[^\s]+\.png) -->\s*$"
)

# Slots requiring manual identity/setup checks or a specific live evidence state.
MANUAL = {
    "lab-00/01": "fresh InPrivate sign-in with a lab account",
    "lab-00/02": "Authenticator registration on a lab account",
    "lab-04/07": "needs a Foundry User lab account (disabled controls)",
    "lab-04/08": "needs a Foundry User lab account (Access control, My role)",
    "lab-01/02": "Knowledge Add menu on an agent without KB; show the existing prepared entry",
    "lab-01/02b": "existing livewell-guides-kb-mcp entry under Available knowledge bases",
    "lab-02/20": "compare the existing shared guardrail matrix; do not submit a new participant batch",
    "lab-03/02b": "facilitator-prepared Anonymous OpenAPI connection in the current portal form",
    "lab-03/03": "current OpenAPI form with the prepared Anonymous connection selected; use native canvas capture",
    "lab-03/12b": "ordered profile, knowledge retrieval and activity discovery trace with real source evidence",
    "lab-03/13b": "completed, once-approved synthetic registration trace; do not repeat a write just for a screenshot",
    "lab-03/15b": "read-only details of this participant's stored preference, with identifiers hidden",
    "lab-03/25": "existing specialist A2A connections in the Configured catalog",
    "lab-03/26": "one merged evidence reply from the participant's A2A-equipped coach",
    "lab-03/27": "actual trace showing both specialist A2A calls",
}
EXTERNAL_CAPTURE = {"lab-04/10", "lab-04/11"}  # demos/lab4-devui.py --capture owns these.


@dataclasses.dataclass
class Slot:
    id: str
    path: str
    caption: str
    page: pathlib.Path
    linked: bool

    @property
    def file(self) -> pathlib.Path:
        return LABS / self.path


def slot_pages() -> list[pathlib.Path]:
    """Canonical pages only; legacy portal pages contain compatibility links."""
    return [LABS / f"lab-0{n}.md" for n in range(5)] + [LABS / "fabric-step.md", LABS / "bridge-spotlight.md"]


def historical_paths() -> set[str]:
    return {
        path for page in slot_pages()
        for path in re.findall(r"<!-- historical-screenshot: (screenshots/\S+\.png) -->",
                               page.read_text(encoding="utf-8"))
    }


def slots() -> dict[str, Slot]:
    found: dict[str, Slot] = {}
    for md in slot_pages():
        for line in md.read_text(encoding="utf-8").splitlines():
            m = SLOT_RE.match(line) or IMAGE_RE.match(line) or HISTORICAL_RE.match(line)
            if m:
                if m["id"] in found and found[m["id"]].path != m["path"]:
                    raise ValueError(f"{md.name}: screenshot id {m['id']} refers to different files")
                caption = m.groupdict().get("caption") or pathlib.PurePosixPath(m["path"]).stem
                found.setdefault(m["id"], Slot(m["id"], m["path"], caption, md, bool(IMAGE_RE.match(line))))
    return found


def prompt(pid: str) -> str:
    return P.lw.prompt_text(pid, with_attachments=False) if pid in PROMPTS else pid


def profile_spec() -> str:
    """The livewell_profile OpenAPI spec as a participant would copy it from the values-sheet URL."""
    import os
    import urllib.request

    url = os.environ.get("PROFILE_OPENAPI_URL", "")
    if not url:
        return ""
    with contextlib.suppress(Exception):
        return json.dumps(json.loads(urllib.request.urlopen(url, timeout=60).read()), indent=2)
    return ""


class Run:
    """Scene context: the page, the mode, the selected slots and the per-slot results."""

    def __init__(self, page, *, mode: str = "shots", only: set[str] | None = None, log=print):
        self.page, self.mode, self.only, self.log = page, mode, only, log
        self.slots = slots()
        self.results: dict[str, str] = {}
        page.on("dialog", lambda d: d.accept())

    @property
    def video(self) -> bool:
        return self.mode == "video"

    def selected(self, sid: str) -> bool:
        return self.only is None or sid in self.only or sid.split("/")[0] in self.only

    def wants(self, *ids: str) -> bool:
        return self.video or any(self.selected(i) for i in ids)

    def shot(self, sid: str, *, element=None, note: str = "") -> None:
        if self.video or not self.selected(sid) or sid not in self.slots:
            return
        P.caption(self.page, None)
        time.sleep(0.8)
        P.screenshot(self.page, self.slots[sid].file, element=element)
        self.results[sid] = "captured" + (f" ({note})" if note else "")
        self.log(f"  [shot] {sid} -> {self.slots[sid].path}" + (f" ({note})" if note else ""))

    def say(self, text: str, pause: float = 2.5) -> None:
        if self.video:
            P.caption(self.page, text)
            time.sleep(pause)

    def pause(self, seconds: float) -> None:
        if self.video:
            time.sleep(seconds)

    def goto(self, route: str, settle: float = 4.0) -> None:
        P.goto(self.page, route, settle=settle)

    def chat(self, pid: str, *, new: bool = True, timeout: float = 300) -> str:
        if new:
            P.new_chat(self.page)
        text = prompt(pid)
        self.say(f"Prompt: {text}" if len(text) < 110 else "Send the prompt", 1.5)
        took = P.send(self.page, text, typing_delay=30 if self.video else 4, timeout=timeout)
        answer = P.last_answer(self.page)
        self.log(f"  [chat] {pid}: {took:.0f}s, {len(answer)} chars" + (" (approval pending)" if P.approval_pending(self.page) else ""))
        if len(answer) < 300:
            self.log("         " + " ".join(answer.split())[:240])
        self.pause(3)
        return answer

    def trace(self, span: str | None = None, tab: str | None = None) -> bool:
        ok = P.open_trace(self.page)
        if ok:
            P.trace_expand(self.page)
        if ok and span:
            # Spans arrive over a minute or two; a trace opened early can lack the one we want, so reopen it.
            for attempt in range(3):
                if P.trace_span(self.page, span) or attempt == 2:
                    break
                self.log(f"  [trace] no span like {span!r} yet; reopening")
                P.close_dialog(self.page)
                time.sleep(30)
                ok = P.open_trace(self.page)
                if not ok:
                    break
                P.trace_expand(self.page)
        if ok and tab:
            P.trace_tab(self.page, tab)
        if ok:
            self.page.mouse.move(640, 600)  # clear span tooltips (empty part of the trace tree)
        if not ok:
            self.log("  [trace] dialog did not load")
        self.pause(3)
        return ok

    def escape(self, times: int = 2) -> None:
        for _ in range(times):
            self.page.keyboard.press("Escape")
            time.sleep(0.6)
        P.close_dialog(self.page)
        with contextlib.suppress(Exception):
            cancel = self.page.get_by_role("button", name=re.compile(r"^cancel$", re.I))
            if cancel.count() and cancel.first.is_visible(timeout=500):
                cancel.first.click(timeout=2000)
                time.sleep(0.8)

    @contextlib.contextmanager
    def soft(self, what: str, *ids: str):
        """Best-effort part of a scene: on failure, log, keep the page's accessibility tree, and move on."""
        try:
            yield
        except Exception as e:  # noqa: BLE001 - portal UI drift must not stop the whole capture
            lines = str(e).splitlines()
            reason = lines[0][:160]
            waiting = next((ln.strip() for ln in lines if ln.strip().startswith("- waiting for")), "")
            self.log(f"  [skip] {what}: {reason}" + (f" ({waiting[2:][:160]})" if waiting else ""))
            for sid in ids:
                if self.selected(sid) and sid not in self.results:
                    self.results[sid] = f"failed: {what}"
            with contextlib.suppress(Exception):
                RUNS.mkdir(parents=True, exist_ok=True)
                stem = re.sub(r"[^a-z0-9]+", "-", what.lower()).strip("-")
                (RUNS / f"fail-{stem}.aria.txt").write_text(self.page.url + "\n" + P.aria(self.page), encoding="utf-8")
                P.screenshot(self.page, RUNS / f"fail-{stem}.png")
        finally:
            with contextlib.suppress(Exception):
                self.escape()

    # small UI verbs ------------------------------------------------------------------------------------
    def button(self, name: str, nth: int = 0, scope=None):
        loc = (scope or self.page).get_by_role("button", name=re.compile(name, re.I)).nth(nth)
        loc.scroll_into_view_if_needed(timeout=5000)
        loc.click(timeout=5000)
        time.sleep(1.5)

    def menuitem(self, name: str, *, hover: bool = False):
        loc = self.page.get_by_role("menuitem", name=re.compile(name, re.I)).first
        loc.hover(timeout=5000) if hover else loc.click(timeout=5000)
        time.sleep(1.5)

    def section_add(self, section: str) -> None:
        """Click the Add button that belongs to a configuration section (Tools, Knowledge)."""
        P.expand(self.page, section)
        header = self.page.get_by_role("button", name=re.compile(rf"^{section}\b", re.I)).first
        adds = self.page.get_by_role("button", name=re.compile(r"^add$", re.I))
        hy = header.bounding_box()["y"]
        best = None
        for i in range(adds.count()):
            box = adds.nth(i).bounding_box()
            if box and box["y"] > hy and (best is None or box["y"] < best[1]):
                best = (i, box["y"])
        if best is None:
            raise RuntimeError(f"no Add button under {section}")
        adds.nth(best[0]).click(timeout=5000)
        time.sleep(1.5)

    def version_history(self) -> None:
        self.page.get_by_role("combobox", name=re.compile(r"^version", re.I)).first.click(timeout=5000)
        time.sleep(1)
        self.page.get_by_role("option", name=re.compile(r"show all version history", re.I)).first.click(timeout=5000)
        time.sleep(2.5)

    def wizard_next(self, wait: float = 60) -> None:
        """Click the wizard's Next once it is enabled (it stays disabled while a dataset preview loads)."""
        end = time.time() + wait
        while True:
            for b in self.page.get_by_role("button", name="Next", exact=True).all():
                if b.is_visible() and b.is_enabled():
                    b.click(timeout=5000)
                    return
            if time.time() > end:
                raise RuntimeError("wizard Next stayed disabled")
            time.sleep(1)

    def blocked_trace(self, wait: float = 240) -> bool:
        """Open the newest guardrail-blocked run from the agent's Traces tab (they are listed as Failed)."""
        end = time.time() + wait
        while True:
            self.page.get_by_role("tab", name=re.compile(r"^traces$", re.I)).first.click(timeout=8000)
            time.sleep(6)
            rows = self.page.get_by_role("row").filter(has_text="Failed")
            for i in range(min(rows.count(), 3)):
                rows.nth(i).get_by_role("button").first.click(timeout=8000)
                alert = self.page.get_by_role("alert").filter(has_text=re.compile("blocked by a safety", re.I))
                with contextlib.suppress(Exception):
                    alert.first.wait_for(state="visible", timeout=20000)
                if alert.count():
                    self.page.mouse.move(640, 600)
                    self.pause(3)
                    return True
                self.escape(1)
                rows = self.page.get_by_role("row").filter(has_text="Failed")
            if time.time() > end:
                return False
            self.log("  [trace] no blocked trace listed yet; waiting for ingestion")
            time.sleep(30)
            self.page.reload()
            time.sleep(6)

    def tool_catalog(self, tab: str = "Custom") -> None:
        self.section_add("Tools")
        self.menuitem(r"^add tools$|browse all tools")
        self.page.get_by_role("dialog").last.get_by_role("tab", name=re.compile(rf"^{tab}$", re.I)).first.click(timeout=5000)
        time.sleep(2)

    def tool_card(self, name: str):
        return self.page.get_by_role("dialog").last.get_by_role("button", name=re.compile(name, re.I)).first

    def search_agents(self, text: str) -> None:
        box = self.page.get_by_role("searchbox", name=re.compile("search agents", re.I)).first
        box.fill(text)
        time.sleep(2.5)

    def collapse(self, *sections: str) -> None:
        for s in sections:
            P.expand(self.page, s, collapse=True)


# --- scenes -----------------------------------------------------------------------------------------------
def tour(run: Run) -> None:
    """Lab 0 steps 3-6: project, Build area, New agent (cancelled); agents list filters for Labs 2 and 4."""
    run.goto("project")
    run.say("Lab 0 · Open the livewell-workshop project")
    with run.soft("project picker", "lab-00/03"):
        run.button(r"^livewell-workshop$")
        P.only_livewell_projects(run.page)
        run.pause(2)
        run.shot("lab-00/03")
    run.goto("agents")
    run.say("Build → Agents: the Build area holds Agents, Knowledge, Evaluations and Guardrails")
    run.shot("lab-00/04")
    with run.soft("new agent menu", "lab-00/05", "lab-00/06"):
        run.button(r"^new agent$")
        run.menuitem(r"^build an agent$", hover=True)
        run.say("New agent → Build an agent")
        run.shot("lab-00/05")
        run.menuitem(r"^build an agent$")
        name = run.page.get_by_role("dialog").last.get_by_role("textbox", name=re.compile("agent name", re.I))
        name.fill("")
        name.press_sequentially("livewell-jt", delay=60 if run.video else 10)
        run.say("Name it livewell-<initials>, Text mode; the model is picked in the playground (not created in this demo)")
        run.shot("lab-00/06")
    if run.wants("lab-02/10"):
        with run.soft("agents list demo", "lab-02/10"):
            run.search_agents("livewell-demo")
            run.shot("lab-02/10")
    if run.wants("lab-04/01"):
        with run.soft("agents list hosted", "lab-04/01"):
            run.search_agents("hosted")
            run.shot("lab-04/01")


def lab0(run: Run) -> None:
    """Lab 0 steps 7-11 on livewell-demo-lab0 (base instructions, gpt-5-mini at Low reasoning effort, no tools)."""
    run.goto("agent:livewell-demo-lab0", settle=5)
    with run.soft("lab0 parameters", "lab-00/06b"):
        P.expand(run.page, "Tools")
        run.button(r"^parameters$")
        run.say("Parameters: reasoning effort Low; Tools: none")
        run.shot("lab-00/06b")
    run.escape()
    run.say(f"Instructions: the base LiveWell Coach block, {P.lw.DEFAULT_MODEL}, no tools")
    P.scroll_instructions(run.page, to_end=False)
    run.shot("lab-00/07")
    run.chat("lab0_hi")
    run.shot("lab-00/08")
    run.chat("lab0_am_i_diabetic")
    run.shot("lab-00/09")
    run.say("Open the trace: one model call, no tools, the token counts")
    with run.soft("lab0 refusal trace", "lab-00/10"):
        if run.trace():
            run.shot("lab-00/10")
    run.escape()


def kb_config(run: Run) -> None:
    """Lab 1 steps 1-6 on livewell-demo-kb (Foundry IQ knowledge base, JSON response format)."""
    run.goto("agent:livewell-demo-kb", settle=5)
    run.say("Lab 1 · Agent configuration")
    run.shot("lab-01/01")
    with run.soft("knowledge add menu", "lab-01/02"):
        run.section_add("Knowledge")
        run.menuitem(r"connect to foundry iq", hover=True)
        run.say("Knowledge → Add → Connect to Foundry IQ")
        run.shot("lab-01/02")
    if run.wants("lab-01/03"):
        with run.soft("foundry iq dialog", "lab-01/03"):
            run.section_add("Knowledge")
            run.menuitem(r"connect to foundry iq")
            dlg = run.page.get_by_role("dialog").last
            dlg.get_by_role("combobox", name=re.compile("connection", re.I)).click(timeout=5000)
            run.page.get_by_role("option", name="livewell-search", exact=True).click(timeout=8000)
            time.sleep(1.5)
            dlg.get_by_role("combobox", name=re.compile("knowledge base", re.I)).click(timeout=5000)
            time.sleep(1.5)
            run.page.get_by_role("option", name=re.compile("livewell-guides-kb", re.I)).first.click(timeout=8000)
            time.sleep(3)
            run.say("Connection livewell-search, knowledge base livewell-guides-kb → Connect")
            run.shot("lab-01/03")
    if run.wants("lab-01/04"):
        with run.soft("kb settings", "lab-01/04"):
            run.goto("knowledge", settle=5)
            run.page.get_by_role("link", name=re.compile(r"^livewell-guides-kb$", re.I)).first.click(timeout=8000)
            time.sleep(5)
            run.say("Knowledge base settings: retrieval reasoning effort, output mode, retrieval instructions")
            run.shot("lab-01/04")
            RUNS.mkdir(parents=True, exist_ok=True)
            (RUNS / "kb-settings.aria.txt").write_text(run.page.url + "\n" + P.aria(run.page), encoding="utf-8")
        run.goto("agent:livewell-demo-kb", settle=5)
    P.scroll_instructions(run.page)
    run.say("Instructions: base + knowledge blocks")
    run.shot("lab-01/05")
    with run.soft("parameters", "lab-01/06"):
        run.button(r"^parameters$")
        run.say("Parameters → Text format: JSON Schema (livewell_lab1_answer)")
        run.shot("lab-01/06")
    if run.wants("lab-02/01"):
        with run.soft("kb versions", "lab-02/01"):
            run.page.get_by_role("combobox", name=re.compile(r"^version", re.I)).first.click(timeout=5000)
            time.sleep(1.5)
            run.shot("lab-02/01")


def kb_chat(run: Run) -> None:
    """Lab 1 steps 7-11: grounded JSON answer, citation, trace, and the no-source supplement answer."""
    run.goto("agent:livewell-demo-kb", settle=5)
    run.chat("lab1_prediabetes_eat")
    run.say("JSON answer with cited_sources from the LiveWell guides")
    run.shot("lab-01/07")
    with run.soft("citation", "lab-01/08"):
        answer = P.answers(run.page).last
        more = answer.get_by_role("button", name=re.compile(r"^\+\d+$"))
        if more.count():
            more.first.click(timeout=3000)
            time.sleep(1.5)
        answer.scroll_into_view_if_needed(timeout=3000)
        run.say("Citations: lg-05 Eating for pre-diabetes and other LiveWell guides")
        run.shot("lab-01/08", element=answer, note="citations under the answer")
    with run.soft("knowledge trace", "lab-01/09"):
        if run.trace(span=r"knowledge|retriev|search|livewell_guides|mcp|tool"):
            run.say("Trace: knowledge-base retrieval before the answer")
            run.shot("lab-01/09")
    run.escape()
    run.chat("lab1_supplement")
    run.say("No source → route: clinician, cited_sources empty")
    run.shot("lab-01/10")
    with run.soft("supplement json", "lab-01/11"):
        run.shot("lab-01/11", element=P.answers(run.page).last)


def kb_redflags(run: Run) -> None:
    """Lab 2 steps 2-8: the ladder on the baseline (livewell-demo-kb, platform default guardrail)."""
    run.goto("agent:livewell-demo-kb", settle=5)
    run.say("Lab 2 · The ladder on the platform default guardrail (Microsoft.DefaultV2)")
    for sid, pid, note in (("lab-02/02", "lab2_extreme_fasting", "Crash diets are not a filter category: the instructions refuse"),
                           ("lab-02/03", "lab2_medication_double", "The model declines - nothing outside the model stopped it")):
        run.chat(pid)
        run.say(note)
        run.shot(sid)
    if run.wants("lab-02/04"):
        P.new_chat(run.page)
        run.say("Paste the community-club flyer below the prompt (it hides an injected instruction)")
        took = P.send(run.page, lw_prompt_text("lab2_injected_flyer"), timeout=300)
        run.log(f"  [chat] lab2_injected_flyer (flyer pasted): {took:.0f}s")
        run.say("Blocked: the default already includes Prompt Shields (jailbreak)")
        run.shot("lab-02/04")
    for sid, pid, note in (("lab-02/05", "lab2_other_resident", "Privacy is about whose data: the instructions refuse"),
                           ("lab-02/06", "lab2_skip_meals", "Answered: self-harm scored Low, so the default only annotates it"),
                           ("lab-02/07", "lab2_benign_control", "Benign: answered"),
                           ("lab-02/08", "lab2_benign_dose_reminder", "Benign medication habit: answered")):
        run.chat(pid)
        run.say(note)
        run.shot(sid)


def guarded(run: Run) -> None:
    """Lab 2 steps 9-18 on livewell-demo-guarded (livewell-guardrails, safety block)."""
    run.goto("agent:livewell-demo-guarded", settle=5)
    run.say("livewell-demo-guarded: livewell-guardrails attached")
    with run.soft("guardrail section", "lab-02/09"):
        run.collapse("Instructions", "Tools", "Knowledge")
        P.expand(run.page, "Guardrail")
        run.page.get_by_role("button", name=re.compile(r"^guardrail", re.I)).first.scroll_into_view_if_needed(timeout=5000)
        run.shot("lab-02/09")
    run.goto("agent:livewell-demo-guarded", settle=5)
    P.scroll_instructions(run.page)
    run.say("Instructions: base + knowledge + safety blocks")
    run.shot("lab-02/11")
    with run.soft("guarded versions", "lab-02/12"):
        run.version_history()
        run.shot("lab-02/12", note="demo agent shows v1")
    run.goto("agent:livewell-demo-guarded", settle=5)  # closes the version-history panel before chatting
    for sid, pid, note in (("lab-02/13", "lab2_medication_double", "Blocked by the medication-dosage blocklist, before the model"),
                           ("lab-02/14", "lab2_skip_meals", "Blocked: same Low self-harm score, stricter threshold - the custom guardrail's benefit"),
                           ("lab-02/15", "lab2_benign_control", "Normal sugar advice is still allowed"),
                           ("lab-02/16", "lab2_benign_dose_reminder", "Over-blocked by the blocklist: the cost of a stricter control")):
        run.chat(pid)
        run.say(note, 4)
        run.shot(sid)
    run.say("Back to an allowed run to compare its trace")
    run.chat("lab2_benign_control")
    with run.soft("allowed trace", "lab-02/18"):
        if run.trace():
            run.shot("lab-02/18")
    run.escape()
    with run.soft("blocked trace", "lab-02/17"):
        # A guardrail-blocked chat turn has no response-metrics row, so open it from the agent's Traces tab.
        if run.wants("lab-02/17"):
            run.say("Blocked runs have no metrics row in chat: open them from the Traces tab (Status: Failed)")
            if not run.blocked_trace():
                raise RuntimeError("no guardrail-blocked trace in the Traces tab yet")
            run.shot("lab-02/17")
    run.escape()


def evals(run: Run) -> None:
    """Lab 2 step 19: the evaluation wizard with the guarded agent and livewell-eval selected (nothing is submitted)."""
    run.goto("evaluations", settle=5)
    run.say("Evaluations → Create: pick the agent, then the livewell-eval dataset")
    with run.soft("evaluation wizard", "lab-02/19"):
        run.button(r"^create$")
        time.sleep(3)
        row = run.page.get_by_role("row").filter(has_text="livewell-demo-guarded").first
        row.get_by_role("checkbox").first.check(timeout=5000)
        time.sleep(1)
        source = run.page.get_by_role("radiogroup", name=re.compile("dataset source", re.I)).first
        for _ in range(4):  # Target -> Scope -> Frequency -> Data
            if source.is_visible():
                break
            run.wizard_next()
            time.sleep(2.5)
        run.page.get_by_role("radio", name=re.compile(r"^existing dataset", re.I)).first.check(timeout=5000)
        time.sleep(3)
        with contextlib.suppress(Exception):
            run.page.get_by_role("progressbar", name=re.compile("loading datasets", re.I)).wait_for(state="hidden", timeout=60000)
        run.page.get_by_role("row").filter(has_text="livewell-eval").first.get_by_role("radio").first.check(timeout=10000)
        with contextlib.suppress(Exception):
            run.page.get_by_role("progressbar", name=re.compile("loading dataset preview", re.I)).wait_for(state="hidden", timeout=90000)
        time.sleep(2)
        run.say("Existing dataset: livewell-eval (registered by create-demo-agents.py)")
        run.shot("lab-02/19", note="livewell-eval selected")
        if run.video:
            run.wizard_next()
            time.sleep(4)
            run.say("Field mapping: set Context to Not available (source_prompt_id is an id, not context)")
            with contextlib.suppress(Exception):
                run.page.get_by_role("combobox", name="Context").first.click(timeout=5000)
                time.sleep(1)
                run.page.get_by_role("option", name="Not available").first.click(timeout=5000)
                time.sleep(1.5)
            for _ in range(2):  # Field mapping -> Configure agents -> Criteria
                run.wizard_next()
                time.sleep(4)
            run.say("Criteria: keep a few evaluators, then Review → Submit (not submitted here)", 4)
        RUNS.mkdir(parents=True, exist_ok=True)
        (RUNS / "evals-wizard.aria.txt").write_text(run.page.url + "\n" + P.aria(run.page), encoding="utf-8")
    run.goto("evaluations", settle=2)


def tools_config(run: Run) -> None:
    """Lab 3 steps 1-9 on livewell-demo-tools (OpenAPI profile, activities MCP with approval, memory)."""
    run.goto("agent:livewell-demo-tools", settle=5)
    run.say("Lab 3 · Tools, MCP and memory")
    run.shot("lab-03/01")
    with run.soft("tool catalog custom", "lab-03/02"):
        run.tool_catalog("Custom")
        run.tool_card(r"openapi").hover(timeout=5000)
        run.say("Tools → Add → Add tools → Custom → OpenAPI tool")
        run.shot("lab-03/02")
    run.escape()
    if run.wants("lab-03/03"):
        with run.soft("openapi form", "lab-03/03"):
            run.tool_catalog("Custom")
            run.tool_card(r"openapi").click(timeout=5000)
            time.sleep(1)
            nxt = run.page.get_by_role("dialog").last.get_by_role("button", name=re.compile(r"^(next|create|continue)$", re.I))
            if nxt.count() and nxt.first.is_enabled(timeout=1000):
                nxt.first.click(timeout=3000)
                time.sleep(2)
            dlg = run.page.get_by_role("dialog").last
            try:
                dlg.get_by_role("textbox", name=re.compile(r"^name", re.I)).first.fill("livewell_profile")
                dlg.get_by_role("textbox", name=re.compile(r"^description", re.I)).first.fill(
                    "Profile of the signed-in resident. Always pass resident_id 'me'.")
                spec = profile_spec()
                if spec:
                    dlg.get_by_role("textbox", name=re.compile(r"openapi.*schema", re.I)).first.click(timeout=5000)
                    run.page.keyboard.insert_text(spec)
                    time.sleep(1.5)
                    run.page.keyboard.press("Control+Home")
                    time.sleep(0.5)
                run.say("Name livewell_profile · description · Anonymous · spec pasted from the values sheet URL")
                run.shot("lab-03/03", note="" if spec else "spec not pasted: PROFILE_OPENAPI_URL unset")
            finally:
                with contextlib.suppress(Exception):
                    run.page.get_by_role("dialog").last.get_by_role("button", name=re.compile(r"^cancel$", re.I)).first.click(timeout=3000)
                    time.sleep(1)
                run.escape()
    if run.wants("lab-03/04", "lab-03/05"):
        # The Configured tab hides connections already attached to the agent, so show it on the Lab 2 demo agent.
        run.goto("agent:livewell-demo-guarded", settle=5)
        with run.soft("mcp configured", "lab-03/04", "lab-03/05"):
            run.tool_catalog("Configured")
            card = run.tool_card(r"^livewell-activities-mcp")
            card.hover(timeout=5000)
            run.say("Tools → Add → Add tools → Configured lists the project's tool connections")
            run.shot("lab-03/04")
            card.click(timeout=5000)
            time.sleep(1)
            run.say("Select livewell-activities-mcp → Add tool (Custom → MCP would create a new connection)")
            run.shot("lab-03/05")
        run.escape()
        run.goto("agent:livewell-demo-tools", settle=5)
    with run.soft("mcp approval", "lab-03/06"):
        item = run.page.get_by_role("listitem").filter(has_text="livewell-activities-mcp")
        item.get_by_role("button", name=re.compile(r"^actions$", re.I)).first.click(timeout=5000)
        run.menuitem(r"^configure$")
        run.say("Approval: find_activities runs freely; register_interest needs approval")
        run.shot("lab-03/06")
    run.goto("agent:livewell-demo-tools", settle=5)
    with run.soft("memory section", "lab-03/07"):
        run.collapse("Instructions", "Tools", "Knowledge")
        P.expand(run.page, "Memory")
        run.say(f"Memory (Preview) on, model {P.lw.TOOLS_MODEL}")
        run.shot("lab-03/07")
    run.goto("agent:livewell-demo-tools", settle=5)
    with run.soft("tools instructions", "lab-03/08"):
        P.scroll_instructions(run.page)
        run.button(r"^parameters$")
        run.say("Instructions + tools block; response format livewell_evidence")
        run.shot("lab-03/08")
    with run.soft("tools versions", "lab-03/09"):
        run.version_history()
        run.shot("lab-03/09", note="demo agent shows v1")


def tools_chat(run: Run) -> None:
    """Lab 3 steps 10-15: profile-tailored answer, MCP approval, memory set and recall."""
    run.goto("agent:livewell-demo-tools", settle=5)
    run.chat("lab3_profile_tailored")
    run.say("Advice tailored from the resident profile (OpenAPI tool)")
    run.shot("lab-03/10")
    with run.soft("profile trace", "lab-03/11"):
        if run.trace(span=r"openapi|profile|tool"):
            run.shot("lab-03/11")
    run.escape()
    run.chat("lab3_hazy_indoor_signup")
    if P.approval_pending(run.page):
        raise RuntimeError("discovery unexpectedly requested write approval; do not approve it")
    run.say("Discover indoor options first; registration is a separate confirmation")
    run.shot("lab-03/12")
    run.chat(SIGNUP_YES, new=False)
    run.say("register_interest waits for approval")
    with run.soft("approve", "lab-03/13"):
        if not P.approval_pending(run.page):
            raise RuntimeError("no approval card")
        run.say("Approve → Approve once")
        if not P.approve(run.page, on_menu=lambda: run.shot("lab-03/13")):
            raise RuntimeError("approval still pending after Approve once")
    run.chat("lab3_memory_set", new=False)
    run.shot("lab-03/14")
    if run.wants("lab-03/15"):
        run.say("Memory is written in the background - give it a minute, then start a new chat", 2)
        time.sleep(60)
        run.chat("lab3_memory_recall")
        run.say("New chat: mornings, no swimming")
        run.shot("lab-03/15")


def fabric(run: Run) -> None:
    """Lab 3 steps 16-24 on livewell-demo-fabric (optional Fabric IQ step)."""
    run.goto("agent:livewell-demo-fabric", settle=5)
    run.say("Optional Fabric step · Fabric IQ for programme-level questions")
    if run.wants("lab-03/16"):
        with run.soft("fabric onelake catalog", "lab-03/16"):
            run.tool_catalog("Configured")
            run.tool_card(r"^Fabric IQ \(OneLake").click(timeout=5000)
            time.sleep(1)
            run.page.get_by_role("dialog", name="Select a tool").get_by_role("button", name="Add tool", exact=True).click(timeout=5000)
            dlg = run.page.get_by_role("dialog", name="OneLake Catalog")
            dlg.wait_for(timeout=20000)
            frame = run.page.frame_locator("[role=dialog] iframe").first
            box = frame.get_by_placeholder(re.compile("filter by keyword", re.I)).first
            box.wait_for(timeout=45000)
            box.fill("Resident360")
            time.sleep(5)
            frame.get_by_text(re.compile(r"^Resident360 Ontology Agent$")).first.click(timeout=15000)
            time.sleep(2)
            run.page.mouse.move(700, 620)
            time.sleep(1)
            run.say("Configured → Fabric IQ (OneLake Catalog) → Add tool → Resident360 Ontology Agent → Add")
            run.shot("lab-03/16")
        run.escape()
    if run.wants("lab-03/17"):
        with run.soft("fabric existing connection", "lab-03/17"):
            run.tool_catalog("Configured")
            run.tool_card(r"^livewell-fabric-resident360").click(timeout=5000)
            time.sleep(1)
            run.say("Or select the existing connection livewell-fabric-resident360 → Add tool")
            run.shot("lab-03/17")
        run.escape()
    run.goto("agent:livewell-demo-fabric", settle=5)
    P.scroll_instructions(run.page)
    run.say("Instructions: fabric routing rules at the end")
    run.shot("lab-03/18")
    run.chat("lab3_programme_fit", timeout=480)
    run.say(f"Profile → Fabric IQ (age band only) → {FIT['recommended_programme']} intake near Woodlands")
    run.shot("lab-03/19", note="" if P.approval_pending(run.page) else "coach asked first; no approval card yet")
    with run.soft("programme fit trace", "lab-03/20"):
        if run.trace(span=r"resident360|dataagent|fabric"):
            P.trace_find(run.page, r"age band")
            run.say("What left the coach: userQuestion names the age band only")
            run.shot("lab-03/20")
    run.escape()
    with run.soft("programme fit approve", "lab-03/21"):
        if not P.approval_pending(run.page):
            run.chat(PROGRAMME_YES, new=False)
        if not P.approval_pending(run.page):
            raise RuntimeError("no approval card")
        run.say("Approve → Approve once: only now is he registered")
        if not P.approve(run.page):
            raise RuntimeError("approval still pending after Approve once")
        run.shot("lab-03/21")
    run.chat("fabric_q_disengaged_regions")
    run.say("Mei: aggregated by region - never an individual resident")
    run.shot("lab-03/22")
    with run.soft("fabric trace", "lab-03/23"):
        if run.trace(span=r"resident360|dataagent|fabric|mcp"):
            run.shot("lab-03/23")
    run.escape()
    run.chat("lab1_prediabetes_eat")
    with run.soft("citizen trace", "lab-03/24"):
        if run.trace():
            run.say("Citizen food question: knowledge/profile, no Fabric call")
            run.shot("lab-03/24")
    run.escape()


def hosted(run: Run) -> None:
    """Lab 4 facilitator watch-along on livewell-workshop-hosted."""
    run.goto("agent:livewell-workshop-hosted", settle=6)
    run.say("Lab 4 · The hosted LiveWell Coach team")
    run.shot("lab-04/02")
    with run.soft("hosted versions", "lab-04/03"):
        run.version_history()
        run.shot("lab-04/03")
    with run.soft("hosted details", "lab-04/04"):
        run.page.get_by_role("tab", name=re.compile(r"^details$", re.I)).first.click(timeout=5000)
        time.sleep(4)
        run.say("Details: active version, identity, endpoints")
        run.shot("lab-04/04")
    run.goto("agent:livewell-workshop-hosted", settle=6)
    run.chat("lab1_prediabetes_eat", timeout=420)
    run.shot("lab-04/05")
    with run.soft("hosted trace", "lab-04/06"):
        if run.trace():
            run.shot("lab-04/06")
    run.escape()
    with run.soft("publish menu", "lab-04/09"):
        run.button(r"^publish$")
        run.say("Project Manager view: Publish to Teams / web app")
        run.shot("lab-04/09")


def fabric_steps():
    """demos/fabric-steps.py as a module (the file name has a hyphen)."""
    spec = importlib.util.spec_from_file_location("fabric_steps", ROOT / "demos" / "fabric-steps.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bridge(run: Run) -> None:
    """Bridge spotlight step 5: Mei's multi-hop question, its Foundry trace, then the data agent's own steps."""
    run.goto("agent:livewell-demo-fabric", settle=5)
    run.say("Bridge spotlight · Two IQs, one agent")
    run.chat("bridge_q_dropped_attended_heldin", timeout=480)
    run.say("Mei: residents who dropped a programme, by the region where their events were held")
    run.shot("bridge/01")
    with run.soft("bridge trace", "bridge/02"):
        if run.trace(span=r"resident360|dataagent|fabric|mcp"):
            P.trace_find(run.page, r"userQuestion")
            run.say("The Foundry trace: one Fabric IQ call, an aggregate question in, an answer out")
            run.shot("bridge/02")
    run.escape()
    if not run.wants("bridge/03", "bridge/04", "bridge/05"):
        return
    with run.soft("bridge visualiser", "bridge/03", "bridge/04", "bridge/05"):
        try:
            page = fabric_steps().replay_page("bridge")
        except SystemExit as e:  # no saved run yet: skip these slots, not the whole capture
            raise RuntimeError(f"{e}; run: python demos/fabric-steps.py bridge --save-sample") from None
        run.log(f"  [page] {page.relative_to(ROOT)}")
        run.page.goto(page.resolve().as_uri(), wait_until="load")
        time.sleep(1.5)
        run.say("Inside the data agent: the steps the Foundry trace does not show (demos/fabric-steps.py)", 4)
        run.shot("bridge/03")
        for sid, section, text in [
            ("bridge/04", "queries", "Each query: the rewrite, the GQL it generated, the rows it read"),
            ("bridge/05", "check", "Checked against the reference answer: 248 residents, Central first"),
        ]:
            run.page.evaluate("id => document.getElementById(id).scrollIntoView({block: 'start'})", section)
            time.sleep(1)
            run.say(text, 4)
            run.shot(sid)
        run.page.evaluate("document.getElementById('answer').scrollIntoView({block: 'start'})")
        run.say("The answer the coach receives: aggregate only, event region kept apart from home region", 4)


def lw_prompt_text(pid: str) -> str:
    """The prompt with its attachments inlined (the flyer), as the Builder scripts send it."""
    return P.lw.prompt_text(pid)


SCENES = {
    "tour": (tour, ["lab-00/03", "lab-00/04", "lab-00/05", "lab-00/06", "lab-02/10", "lab-04/01"]),
    "lab0": (lab0, ["lab-00/06b"] + [f"lab-00/{n:02d}" for n in range(7, 11)]),
    "kb-config": (kb_config, [f"lab-01/{n:02d}" for n in range(1, 7)] + ["lab-02/01"]),
    "kb-chat": (kb_chat, [f"lab-01/{n:02d}" for n in range(7, 12)]),
    "kb-redflags": (kb_redflags, [f"lab-02/{n:02d}" for n in range(2, 9)]),
    "guarded": (guarded, ["lab-02/09"] + [f"lab-02/{n:02d}" for n in range(11, 19)]),
    "evals": (evals, ["lab-02/19"]),
    "tools-config": (tools_config, [f"lab-03/{n:02d}" for n in range(1, 10)]),
    "tools-chat": (tools_chat, [f"lab-03/{n:02d}" for n in range(10, 16)]),
    "fabric": (fabric, [f"lab-03/{n:02d}" for n in range(16, 25)]),
    "hosted": (hosted, ["lab-04/02", "lab-04/03", "lab-04/04", "lab-04/05", "lab-04/06", "lab-04/09"]),
    "bridge": (bridge, [f"bridge/{n:02d}" for n in range(1, 6)]),
}

# One Navigator-rail demo video per lab, plus the Bridge spotlight.
VIDEOS = {
    "lab-00": ["tour", "lab0"],
    "lab-01": ["kb-config", "kb-chat"],
    "lab-02": ["kb-redflags", "guarded", "evals"],
    "lab-03": ["tools-config", "tools-chat", "fabric"],
    "lab-04": ["hosted"],
    "bridge": ["bridge"],
}
