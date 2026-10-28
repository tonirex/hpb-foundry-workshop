# %% [markdown]
# # Lab 4 - Multi-agent & Hosted deploy - Builder rail
#
# The coach becomes a team. Microsoft Agent Framework runs the orchestration on your machine and calls the
# project's model deployments directly, so these local agents run under the deployment's guardrail (the platform
# default, Microsoft.DefaultV2), not `livewell-guardrails`. The Foundry agents below (Programme-Insights, the
# hosted agent) carry `livewell-guardrails` themselves.
#
# * Two local specialists, Nutrition and Activity, with the same hosted tools as Lab 3: the knowledge-base
#   MCP endpoint and `find_activities` (never `register_interest`).
# * A SEQUENTIAL workflow: Nutrition -> Activity -> Coach. The Coach merges both answers into one evidence JSON.
# * A HAND-OFF workflow: the Coach triages, hands off to Nutrition, and Nutrition hands off to Activity.
# * Optional facilitator-only Programme-Insights: creates a Foundry agent with the Fabric IQ tool
#   only with both `--fabric` and FABRIC_BRIDGE=true. The default run creates no Foundry agents.
# * Optional operator endpoint proof with --hosted; no hosted call in the participant default.
#
# Run it all:  `python content/assets/lab4_multiagent.py` (INITIALS and endpoint from content/assets/.env)
# Flags:       `--no-handoff`, `--verbose`, `--cleanup`; operator extensions: `--fabric`, `--hosted`.
#
# Lines marked `# 👉` are the ones to retype during the lab.

# %%
import json
import pathlib
import re
import sys

import openai

_here = (pathlib.Path(globals()["__file__"]).resolve().parent if "__file__" in globals() else
         next(p for p in (pathlib.Path.cwd(), pathlib.Path.cwd() / "content" / "assets") if (p / "common").is_dir()))
sys.path.insert(0, str(_here))
from common import livewell_common as lw  # noqa: E402

from agent_framework import Agent, Message, agent_middleware, chat_middleware  # noqa: E402
from agent_framework.orchestrations import HandoffBuilder, SequentialBuilder  # noqa: E402


def _flags(p):
    p.add_argument("--fabric", action="store_true",
                   help="facilitator only: create/run Programme-Insights (needs FABRIC_BRIDGE=true and active Fabric)")
    p.add_argument("--no-handoff", action="store_true", help="skip the hand-off workflow")
    p.add_argument("--hosted", action="store_true", help="optional operator check of the existing hosted endpoint")


args = lw.lab_args("Lab 4 - multi-agent and hosted deploy", _flags)
if args.fabric and not lw.fabric_enabled():
    raise SystemExit("--fabric is facilitator-only and requires FABRIC_BRIDGE=true; omit it for core Lab 4.")
GUARDRAIL = lw.NAMES["rai_policy"]
HOSTED = lw.NAMES["hosted_agent"]
lw.heading(f"Lab 4 for livewell-{lw.initials()}-*")

# %% [markdown]
# ## 1. The request and the resident
#
# The local specialists have no profile tool, so this script reads the session resident's profile (as in Lab 3)
# and passes a summary with the request. The summary never includes the resident_id.

# %%
PROFILE = lw.profile_summary(lw.get_citizen_profile("me"))
REQUEST = f"{PROFILE}\n\n{lw.prompt_text('lab4_week_plan_handoff')}"  # 👉
lw.say(REQUEST)

# %% [markdown]
# ## 2. An Agent Framework client and the hosted tools
#
# `lw.af_client()` is a `FoundryChatClient` on the project's default deployment. The tools are the same project
# connections as Lab 3; Foundry calls the MCP servers, not your machine.

# %%
client = lw.af_client()  # 👉
knowledge = lw.af_kb_tool(client)  # 👉
find_activities = lw.af_activities_tool(client)
lw.warm_activities()  # the activities server scales to zero; wake it now
lw.say(f"client on {lw.DEFAULT_MODEL}; tools: {lw.KB_LABEL} (knowledge_base_retrieve), {lw.ACTIVITIES_LABEL} (find_activities)")

# %% [markdown]
# ## 3. The specialists, with a middleware that passes plain text
#
# Another agent's tool-call items mean nothing to the Coach and can fail its model call, so each agent gets earlier
# answers as plain text (who said what), plus its own hand-off result. This is an Agent Framework **agent middleware**.

# %%
@agent_middleware
async def text_only(context, call_next):  # 👉
    context.messages[:] = [m if m.role == "tool" else Message(m.role, [m.text], author_name=m.author_name)
                           for m in context.messages if m.text or m.role == "tool"]  # keeps its own hand-off result
    await call_next()


def team(*extra_blocks: str) -> tuple[Agent, Agent]:
    """Fresh Nutrition and Activity agents (an agent instance belongs to one workflow)."""
    common = {"middleware": [text_only], "require_per_service_call_history_persistence": True}
    nutrition = Agent(client, lw.load_instructions("nutrition", *extra_blocks), name="nutrition",  # 👉
                      description="Meal suggestions grounded in the LiveWell guides", tools=[knowledge], **common)
    activity = Agent(client, lw.load_instructions("activity", *extra_blocks), name="activity",  # 👉
                     description="Safe activities and community activities", tools=[knowledge, find_activities],
                     **common)
    return nutrition, activity


def show_steps(steps: list[dict]) -> None:
    lw.say("trace: " + " -> ".join(s["agent"] for s in steps))
    for s in steps:
        lw.say(f"   {s['agent']:<10} tools: {', '.join(s['tools']) or 'none'}")
        if args.verbose and s["text"]:
            lw.say("      " + lw._trunc(s["text"].replace("\n", " "), 600))


def order_ok(steps: list[dict], expected: list[str]) -> tuple[bool, list[str]]:
    """The expected agents spoke, in that order (other speakers in between are allowed)."""
    seen = [s["agent"] for s in steps]
    firsts = [seen.index(a) if a in seen else -1 for a in expected]
    return -1 not in firsts and firsts == sorted(firsts), seen


def no_resident_id(text: str) -> bool:
    return not re.search(r"RESIDENT_\d+", text or "")


# %% [markdown]
# ## 4. Sequential workflow: Nutrition -> Activity -> Coach (`lab4_week_plan_handoff`)
#
# The Coach merges the two answers into the Lab 3 evidence JSON. Its schema only accepts real guide ids.
# `output_from="all"` makes every agent's answer a workflow output, so the trace shows all three.

# %%
def sequential():
    nutrition, activity = team()
    coach = Agent(client, lw.load_instructions("base", "safety", "merge"), name="coach",  # 👉
                  description="LiveWell Coach: merges the specialists' answers", middleware=[text_only],
                  default_options=lw.af_json_format(lw.evidence_schema(), "livewell_evidence"))
    return SequentialBuilder(participants=[nutrition, activity, coach], output_from="all").build()  # 👉


messages, seconds = lw.af_run(sequential, REQUEST, what="sequential workflow")  # 👉
steps = lw.af_steps(messages)
lw.say(f"sequential workflow finished in {seconds:.0f}s")
show_steps(steps)
merged_text = next((s["text"] for s in reversed(steps) if s["agent"] == "coach"), "")
try:
    plan = json.loads(merged_text)
except ValueError:
    plan = {}
lw.show_json(plan or merged_text)
guides = [g for g in plan.get("supporting_guides", []) if g in lw.guide_ids()]
searched = [s["agent"] for s in steps if "knowledge_base_retrieve" in s["tools"]]
advice = str(plan.get("advice", ""))
lw.expect("lab4_week_plan_handoff: Nutrition -> Activity -> Coach", *order_ok(steps, ["nutrition", "activity", "coach"]))
lw.expect("lab4_week_plan_handoff: valid JSON", bool(plan.get("advice")), lw._trunc(merged_text, 120))
lw.expect("lab4_week_plan_handoff: >= 1 real guide cited", bool(guides), plan.get("supporting_guides"))
lw.expect("lab4_week_plan_handoff: specialists searched the guides", bool(searched), searched)
lw.expect("lab4_week_plan_handoff: indoor morning activity", bool(re.search(r"indoor", advice, re.I)
          and re.search(r"morning|\b0?([6-9]|1[01])((:\d\d)?\s*a\.?m\b|:\d\d\b(?!\s*p))", advice, re.I)), lw._trunc(advice, 160))
lw.expect("lab4_week_plan_handoff: no resident_id", no_resident_id(merged_text))
lw.record("lab4_week_plan_sequential", {"seconds": round(seconds, 1), "steps": steps, "json": plan})

# %% [markdown]
# ## 5. Hand-off workflow: Coach -> Nutrition -> Activity
#
# The developer permits hand-offs; the model selects among them using the `handoff` instruction block.
# Unlike the sequential team, this example ends with Activity's answer, not merged JSON.
# Nutrition gets one autonomous turn after its answer so it hands off instead of waiting for
# the resident. The instructions alone were not enough (`gpt-5-mini` sometimes handed off without answering), so a
# **chat middleware** hides Nutrition's hand-off tool on its first turn: it has to answer before it can hand off.
# Activity gets no hand-off tool, because it is the last stop: the workflow stops once it has answered. That is why
# `HandoffBuilder` warns that Activity "will not be able to hand off".

# %%
def answer_first() -> list:
    """Nutrition's middleware: count its turns, and on the first one remove the hand-off tools from the model call."""
    turns = 0

    @agent_middleware
    async def count_turns(context, call_next):
        nonlocal turns
        turns += 1
        await call_next()

    @chat_middleware
    async def hide_handoff(context, call_next):  # 👉 runs before each model call and can change its options
        if turns == 1:
            context.options = {**context.options, "tools": [t for t in context.options.get("tools") or []
                                                            if not getattr(t, "name", "").startswith("handoff_to_")]}
        await call_next()

    return [count_turns, hide_handoff]


handoff_steps: list[dict] = []
if not args.no_handoff:
    def handoff():
        nutrition, activity = team("handoff")
        nutrition.middleware = [*nutrition.middleware, *answer_first()]  # 👉
        coach = Agent(client, lw.load_instructions("base", "handoff"), name="coach",  # 👉
                      description="LiveWell Coach: triage only", middleware=[text_only],
                      require_per_service_call_history_persistence=True)
        return (HandoffBuilder(name="livewell_handoff", participants=[coach, nutrition, activity],  # 👉
                               termination_condition=lambda conv: any(m.author_name == "activity" and m.text
                                                                      for m in conv if m.role == "assistant"))
                .with_start_agent(coach)
                .add_handoff(coach, [nutrition, activity])  # 👉
                .add_handoff(nutrition, [activity])  # 👉
                # after its answer Nutrition gets one more turn instead of waiting for the resident
                .with_autonomous_mode(agents=[nutrition], turn_limits={"nutrition": 1}, prompts={
                    "nutrition": "If the resident also asked about activity, hand off to the Activity specialist now."})
                .build())

    messages, seconds = lw.af_run(handoff, REQUEST, what="hand-off workflow")  # 👉
    handoff_steps = lw.af_steps(messages)
    lw.say(f"hand-off workflow finished in {seconds:.0f}s")
    show_steps(handoff_steps)
    answered = {s["agent"] for s in handoff_steps if s["text"]}
    lw.expect("handoff: Coach -> Nutrition -> Activity", *order_ok(handoff_steps, ["coach", "nutrition", "activity"]))
    lw.expect("handoff: both specialists answered", {"nutrition", "activity"} <= answered, sorted(answered))
    lw.expect("handoff: a guide is cited", any(lw.cited_guides(s["text"]) for s in handoff_steps))
    lw.expect("handoff: no resident_id", all(no_resident_id(s["text"]) for s in handoff_steps))
    lw.record("lab4_week_plan_handoff", {"seconds": round(seconds, 1), "steps": handoff_steps})
else:
    lw.say("hand-off workflow skipped (--no-handoff)")

# %% [markdown]
# ## 6. Programme-Insights specialist (`lab4_q_programmes_disengaged`, only with `--fabric`)
#
# Officer questions take a different route: a Foundry agent with the Fabric IQ tool and the `insights` block, under
# the same guardrail. It answers with aggregates by programme and never with a resident.

# %%
insights_result: dict = {}
if args.fabric:
    insights = lw.create_agent("insights", lw.load_instructions("insights"),  # 👉
                               tools=[lw.fabric_tool()], rai_policy=GUARDRAIL,  # 👉
                               model=lw.TOOLS_MODEL,  # Fabric tools are not supported on gpt-5-mini
                               description="LiveWell Programme-Insights specialist (Fabric IQ)")
    lw.say(f"insights = {insights.name} version {insights.version}")
    mei = lw.ask(insights, prompt_id="lab4_q_programmes_disengaged", consent=False,  # 👉
                 timeout=lw.FABRIC_TIMEOUT)
    lw.show_run(mei, verbose=args.verbose)
    reference = json.loads((lw.CONTENT / "fabric" / "reference-answers.json").read_text(encoding="utf-8"))
    rows = sorted(reference["q_programmes_disengaged_enrolled"]["rows"], key=lambda r: -r["disengaged_enrolled"])
    ranked = [r["programme_name"] for r in rows]
    answer = lw.ascii_safe(mei.text)
    positions = {p: answer.find(p.split(" (")[0]) for p in ranked if p.split(" (")[0] in answer}
    top = min(positions, key=positions.get) if positions else None
    lw.expect("lab4_q_programmes_disengaged: Fabric IQ tool called", mei.fabric_called, mei.tool_names)
    lw.expect("lab4_q_programmes_disengaged: grouped by programme (>= 3 named)", len(positions) >= 3, sorted(positions))
    lw.expect("lab4_q_programmes_disengaged: top programme matches the reference (+-1 rank)", top in ranked[:2],
              f"{top} vs reference {ranked[:3]}")
    lw.expect("lab4_q_programmes_disengaged: no resident_id", no_resident_id(mei.text))
    insights_result = {"lab4_q_programmes_disengaged": lw._trunc(mei.text, 600)}
    lw.record("lab4_q_programmes_disengaged", mei)
else:
    lw.say("Programme-Insights skipped (facilitator-only --fabric; core Lab 4 needs no Fabric)")

# %% [markdown]
# ## 7. Optional operator check of the existing hosted agent (--hosted)
#
# `content/assets/hosted-agent-example/` packages this sequential team as a hosted agent. Publishing needs Foundry
# Project Manager, so the facilitator deploys `livewell-workshop-hosted`. Its `rai_config` points at the same
# guardrail as your agents, by full resource ID. Once it exists, anyone with Foundry User can call it. A hosted
# agent answers on its own endpoint (`.../agents/<name>/endpoint/protocols/openai`); `lw.ask` picks it for you.

# %%
hosted_result: dict = {}
hosted, smoke = None, None
if args.hosted:
    lw.say(f"rai_config for the hosted agent: {{'rai_policy_name': '{lw.rai_policy_id(GUARDRAIL)}'}}")
    hosted = lw.agent_by_name(HOSTED)
    if hosted is None:
        lw.say(f"{HOSTED} is unavailable; the optional hosted check cannot run.")
        lw.expect("hosted: existing agent available", False, HOSTED)
    else:
        policy = lw.rai_policy_of(hosted)
        lw.say(f"{HOSTED} version {hosted.version} ({hosted.definition.kind}), guardrail: {policy or '(deployment default)'}")
        lw.expect("hosted: the same guardrail is attached", policy == GUARDRAIL, policy)
        try:
            smoke = lw.ask(HOSTED, prompt_id="lab4_week_plan_handoff", consent=False)  # 👉
        except openai.APIStatusError as e:
            lw.say(f"the hosted endpoint did not answer ({lw._trunc(str(e), 200)}): see the hosted agent README > Troubleshooting")
            lw.expect("hosted: the endpoint answered", False, e.status_code)
else:
    lw.say("Hosted endpoint check skipped; core Lab 4 compares the two Agent Framework workflows.")
if hosted is not None and smoke is not None:
    lw.show_run(smoke, verbose=args.verbose)
    try:
        smoke_json = smoke.json() if not smoke.blocked else {}
    except ValueError:
        smoke_json = {}
    lw.expect("hosted: valid JSON", bool(smoke_json.get("advice")), lw._trunc(smoke.text, 120))
    lw.expect("hosted: >= 1 real guide cited", bool(smoke.citations), smoke.citations)
    lw.expect("hosted: no resident_id", no_resident_id(smoke.text))
    hosted_result = {"hosted smoke test": smoke_json or smoke.text}
    lw.record("lab4_hosted_smoke", smoke)

# %% [markdown]
# ## 8. Checkpoint
#
# Who spoke in each workflow, the merged plan and the hosted smoke test in one place. Compare them with Expected
# output under Checkpoint on the lab page; there is nothing to submit.

# %%
lw.checkpoint("Lab 4", {
    "sequential trace": " -> ".join(s["agent"] for s in steps),
    "lab4_week_plan_handoff": plan or merged_text,
    "hand-off trace": " -> ".join(s["agent"] for s in handoff_steps) or "(skipped)",
    **insights_result,
    **hosted_result,
})
lw.say(f"results saved to {lw.save_results('lab4')}")
if args.cleanup:
    lw.cleanup()
