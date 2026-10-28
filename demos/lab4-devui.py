#!/usr/bin/env python3
"""Lab 4 facilitator demo: watch the Agent Framework orchestration run, agent by agent, in DevUI.

`lab4_multiagent.py` prints the route as text. This opens the same two workflows in Agent Framework DevUI, a local
web page that draws each workflow graph and shows agent outputs and local hand-off calls.
Foundry-hosted MCP calls are not listed in its Tools panel; inspect server-side traces for those operations.
The Traces panel shows the OpenTelemetry spans collected by this app for each run.

    python demos/lab4-devui.py                 # http://127.0.0.1:8090: "LiveWell sequential" and "LiveWell hand-off"
    python demos/lab4-devui.py --mermaid       # print the WorkflowViz graphs (the diagrams in lab-04.md) and exit
    python demos/lab4-devui.py --port 8091 --no-browser
    python demos/lab4-devui.py --capture       # run both workflows headless and refresh the lab-04 DevUI screenshots

It prints the request to paste into the chat box (your profile summary + `lab4_week_plan_handoff`). The agents
mirror `content/assets/lab4_multiagent.py` sections 3-5 (same instruction blocks, tools and builders) and, like
them, call the project's deployments directly under the deployment guardrail (Microsoft.DefaultV2). By default
DevUI binds to 127.0.0.1 with no sign-in. Needs `pip install -r requirements-demos.txt` (agent-framework-devui),
your az login with Foundry User and the azd env (AZURE_ENV_NAME) or a filled .env. Stop it with Ctrl+C.

The same script runs in Azure (`azd deploy lab4-devui`, demos/devui-aca/): `--host 0.0.0.0` requires the
server-only DEVUI_AUTH_TOKEN. Private expiring workshop links establish an HttpOnly browser session without
token entry (developer mode keeps the Events/Traces/Tools panel). The Container App's managed identity
(Foundry User) replaces your az login. Every run gets a freshly built workflow,
because a workflow object keeps its agents' chat history between runs; `--seats N` caps how many runs of one
workflow are in flight at once.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "content" / "assets"))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from common import livewell_common as lw  # noqa: E402

from agent_framework import (Agent, Message, WorkflowException, WorkflowViz, agent_middleware,  # noqa: E402
                             chat_middleware)
from agent_framework.orchestrations import HandoffAgentUserRequest, HandoffBuilder, SequentialBuilder  # noqa: E402

LOOPBACK = ("127.0.0.1", "localhost")


@agent_middleware
async def text_only(context, call_next):
    """Same as lab4_multiagent.py section 3: earlier answers reach each agent as plain text, plus its own hand-off result."""
    context.messages[:] = [m if m.role == "tool" else Message(m.role, [m.text], author_name=m.author_name)
                           for m in context.messages if m.text or m.role == "tool"]
    await call_next()


def answer_first() -> list:
    """Same as lab4_multiagent.py section 5: Nutrition's first turn has no hand-off tool, so it must write its food
    answer; it hands off on its autonomous turn."""
    turns = 0

    @agent_middleware
    async def count_turns(context, call_next):
        nonlocal turns
        turns += 1
        await call_next()

    @chat_middleware
    async def hide_handoff(context, call_next):
        if turns == 1:
            context.options = {**context.options, "tools": [t for t in context.options.get("tools") or []
                                                            if not getattr(t, "name", "").startswith("handoff_to_")]}
        await call_next()

    return [count_turns, hide_handoff]


def build(client, knowledge, find_activities):
    def team(*extra: str) -> tuple[Agent, Agent]:
        common = {"middleware": [text_only], "require_per_service_call_history_persistence": True}
        nutrition = Agent(client, lw.load_instructions("nutrition", *extra), name="nutrition",
                          description="Meal suggestions grounded in the LiveWell guides", tools=[knowledge], **common)
        activity = Agent(client, lw.load_instructions("activity", *extra), name="activity",
                         description="Safe activities and community activities", tools=[knowledge, find_activities],
                         **common)
        return nutrition, activity

    nutrition, activity = team()
    coach = Agent(client, lw.load_instructions("base", "safety", "merge"), name="coach",
                  description="LiveWell Coach: merges the specialists' answers", middleware=[text_only],
                  default_options=lw.af_json_format(lw.evidence_schema(), "livewell_evidence"))
    # Name the workflows at build time: checkpoints are saved under the build-time name and DevUI looks them up by
    # `workflow.name` when a participant answers the triage Coach's question (hand-off), so the two must match.
    sequential = SequentialBuilder(name="LiveWell sequential", participants=[nutrition, activity, coach],
                                   output_from="all").build()
    sequential.description = "Nutrition -> Activity -> Coach (Lab 4 section 4)"

    nutrition, activity = team("handoff")
    nutrition.middleware = [*nutrition.middleware, *answer_first()]
    triage = Agent(client, lw.load_instructions("base", "handoff"), name="coach",
                   description="LiveWell Coach: triage only", middleware=[text_only],
                   require_per_service_call_history_persistence=True)
    handoff = (HandoffBuilder(name="LiveWell hand-off", participants=[triage, nutrition, activity],
                              termination_condition=lambda conv: any(m.author_name == "activity" and m.text
                                                                     for m in conv if m.role == "assistant"))
               .with_start_agent(triage)
               .add_handoff(triage, [nutrition, activity])
               .add_handoff(nutrition, [activity])
               .with_autonomous_mode(agents=[nutrition], turn_limits={"nutrition": 1}, prompts={
                   "nutrition": "If the resident also asked about activity, hand off to the Activity specialist now."})
               .build())
    handoff.description = "Coach triages -> Nutrition -> Activity (Lab 4 section 5)"
    return sequential, handoff


def tidy_roles(value):
    """DevUI's Configure & Run form takes the role as free text, and Foundry rejects anything but an exact role
    ("user " or "User" fails the whole run with 400 invalid_payload). Trim and lowercase it; anything else is the
    resident speaking, so it becomes "user"."""
    for m in value if isinstance(value, list) else [value]:
        if isinstance(m, Message) and isinstance(m.role, str):
            role = m.role.strip().lower()
            m.role = role if role in ("user", "assistant", "system") else "user"
    return value


class FreshRuns:
    """One DevUI entry that builds a new copy of its workflow for every run, with at most `seats` runs in flight.
    A workflow object keeps state from one run to the next: each agent's chat history, and the hand-off
    conversation that the termination condition reads. Reusing one would show a participant the previous run, and a
    reused hand-off copy stops at once with no answer because Activity has already replied. Everything else (name,
    graph, executors) comes from a copy that never runs."""

    def __init__(self, make, seats: int):
        self._make, self._seats = make, max(seats, 1)
        self._shown = make()
        self._running = []

    def __getattr__(self, name):
        return getattr(self._shown, name)

    def run(self, *args, **kwargs):
        self._running = [wf for wf in self._running if wf._is_run_active()]
        if len(self._running) >= self._seats:
            raise WorkflowException(f"All {self._seats} seats of {self.name} are busy. Try again in a minute.")
        if kwargs.get("responses"):
            # The triage Coach's question (hand-off only) expects chat messages, but DevUI's reply box sends a string.
            kwargs["responses"] = {rid: HandoffAgentUserRequest.create_response(r) if isinstance(r, str) else r
                                   for rid, r in kwargs["responses"].items()}
        if args:
            args = (tidy_roles(args[0]), *args[1:])
        wf = self._make()
        stream = wf.run(*args, **kwargs)
        self._running.append(wf)
        return stream


# workflow -> (screenshot, side-panel tab to show)
SHOTS = {"LiveWell sequential": ("10-devui-sequential.png", "Events"),
         "LiveWell hand-off": ("11-devui-handoff.png", "Tools")}


def capture(port: int, request: str) -> int:
    """Start DevUI in a child process, run each workflow from its Configure & Run form and screenshot the result."""
    from playwright.sync_api import sync_playwright

    out = ROOT / "content" / "labs" / "screenshots" / "lab-04"
    base = f"http://127.0.0.1:{port}"
    server = subprocess.Popen([sys.executable, __file__, "--port", str(port), "--no-browser"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(f"{base}/health", timeout=2)
                break
            except OSError:
                time.sleep(1)
        else:
            lw.say("DevUI did not start")
            return 1
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 950})
            for name, (file, tab) in SHOTS.items():
                page.goto(base, wait_until="networkidle")
                page.get_by_role("button", name="LiveWell").first.click()
                page.get_by_role("menuitem", name=name).click()
                page.get_by_role("button", name="Configure & Run").click()
                page.get_by_placeholder("Enter role").fill("user")
                page.get_by_placeholder("Enter contents").fill(request)
                page.get_by_role("button", name="Run Workflow").click()
                page.get_by_role("button", name="Run Again").wait_for(timeout=300_000)
                page.get_by_role("tab", name=tab).click()
                page.wait_for_timeout(1500)
                page.screenshot(path=str(out / file))
                lw.say(f"saved {(out / file).relative_to(ROOT)}")
            browser.close()
        return 0
    finally:
        server.terminate()
        server.wait(timeout=30)


def stable_entity_ids() -> None:
    """Drop the random suffix DevUI adds to in-memory entity ids (workflow_in_memory_<name>_<uuid4>).

    Otherwise every restart (scale to zero, redeploy) gives new ids, and a page left open fails with
    "Failed to Load Workflow ... not found". The two workflow names are unique, so the ids stay unique.
    """
    from agent_framework_devui._discovery import EntityDiscovery  # pinned in requirements-demos.txt

    random_id = EntityDiscovery._generate_entity_id
    EntityDiscovery._generate_entity_id = lambda self, *a, **k: random_id(self, *a, **k).rsplit("_", 1)[0]


def per_run_traces() -> None:
    """Show each run only its own spans in Traces.

    DevUI attaches one trace collector per run to the shared tracer and never detaches it. With several people
    running at once, everyone's Traces panel shows everyone's spans, and finished runs keep collecting spans for the
    rest of the day (memory grows with every run). Keep only spans started inside the run, and detach at the end.
    """
    import contextlib
    import contextvars

    from agent_framework_devui import _executor, _tracing  # pinned in requirements-demos.txt
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    current = contextvars.ContextVar("livewell_devui_run", default=None)

    class ThisRunOnly(SimpleSpanProcessor):
        def __init__(self, collector):
            super().__init__(collector)
            self.mine: set[int] = set()

        def on_start(self, span, parent_context=None):
            if current.get() is self:
                self.mine.add(span.context.span_id)

        def on_end(self, span):
            if span.context.span_id in self.mine:
                self.mine.discard(span.context.span_id)
                super().on_end(span)

    @contextlib.contextmanager
    def capture_traces(response_id=None, entity_id=None):
        collector = _tracing.SimpleTraceCollector(response_id, entity_id)
        provider = trace.get_tracer_provider()
        if not isinstance(provider, TracerProvider):
            yield collector
            return
        processor = ThisRunOnly(collector)
        provider.add_span_processor(processor)
        token = current.set(processor)
        try:
            yield collector
        finally:
            with contextlib.suppress(ValueError):
                current.reset(token)
            multi = provider._active_span_processor
            with multi._lock:
                multi._span_processors = tuple(p for p in multi._span_processors if p is not processor)

    _executor.capture_traces = capture_traces


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address; anything but 127.0.0.1/localhost needs DEVUI_AUTH_TOKEN")
    ap.add_argument("--seats", type=int, default=int(os.environ.get("LIVEWELL_DEVUI_SEATS") or 1),
                    help="how many runs of one workflow can be in flight at once (each run builds a fresh copy)")
    ap.add_argument("--mermaid", action="store_true", help="print the two workflow graphs as Mermaid and exit")
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    ap.add_argument("--capture", action="store_true", help="refresh the lab-04 DevUI screenshots (needs Playwright)")
    args = ap.parse_args()
    lw.load_settings()
    if args.capture:
        return capture(args.port, f"{lw.profile_summary(lw.get_citizen_profile('me'))}\n\n"
                                  f"{lw.prompt_text('lab4_week_plan_handoff')}")

    client = lw.af_client()
    knowledge, find_activities = lw.af_kb_tool(client), lw.af_activities_tool(client)
    workflows = build(client, knowledge, find_activities)
    if args.mermaid:
        for wf in workflows:
            print(f"%% {wf.name}\n{WorkflowViz(wf).to_mermaid()}")
        return 0
    try:
        from agent_framework.devui import serve
    except ImportError:
        lw.say("DevUI is not installed: python -m pip install -r requirements-demos.txt")
        return 1

    local = args.host in LOOPBACK
    if not local and not os.environ.get("DEVUI_AUTH_TOKEN"):
        lw.say(f"--host {args.host} makes DevUI reachable from the network: set DEVUI_AUTH_TOKEN first.")
        return 1
    seats = max(args.seats, 1)
    entities = [FreshRuns(lambda i=i: build(client, knowledge, find_activities)[i], seats)
                for i in range(len(workflows))]

    lw.warm_activities()
    request = f"{lw.profile_summary(lw.get_citizen_profile('me'))}\n\n{lw.prompt_text('lab4_week_plan_handoff')}"
    lw.heading("Paste this into the DevUI chat box")
    print(request)
    lw.say(f"\nDevUI on http://{args.host}:{args.port} ({seats} seat(s) per workflow, "
           f"{'local development' if local else 'private workshop link'}; Ctrl+C to stop).")
    stable_entity_ids()
    per_run_traces()
    if local:
        serve(entities=entities, port=args.port, host=args.host, auto_open=not args.no_browser,
              instrumentation_enabled=True, auth_enabled=False, mode="developer")
    else:
        import uvicorn
        from agent_framework.observability import enable_instrumentation
        from agent_framework_devui import DevServer
        from common.devui_access import WorkshopAccessMiddleware

        enable_instrumentation(enable_sensitive_data=True)
        server = DevServer(port=args.port, host=args.host, auth_enabled=True, mode="developer")
        server.set_pending_entities(entities)
        app = server.get_app()
        app.add_middleware(WorkshopAccessMiddleware, secret=os.environ["DEVUI_AUTH_TOKEN"])
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
