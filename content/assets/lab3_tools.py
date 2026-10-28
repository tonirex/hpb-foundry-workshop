# %% [markdown]
# # Lab 3 - Tools, MCP & Memory - Builder rail
#
# The coach becomes personal and starts to act. It gets:
#
# * `get_citizen_profile`: a FUNCTION tool with a strict schema, answered here on your machine from
#   `content/data/citizens.json`, and only for the signed-in session resident;
# * the activities MCP server (project connection `livewell-activities-mcp`): `find_activities` runs freely,
#   `register_interest` waits for a human approval;
# * memory (preview) for stated preferences across conversations;
# * two specialists, `livewell-<INITIALS>-nutrition` and `livewell-<INITIALS>-activity`, connected to the coach
#   as function tools: when the coach calls one, this script asks that specialist agent and hands back its reply.
#
# Run it all:            `python content/assets/lab3_tools.py` (INITIALS and endpoint from content/assets/.env)
# Fabric step:           add `--fabric` only when the facilitator confirms FABRIC_BRIDGE=true
# Flags:                 `--verbose` (tool calls and outputs), `--no-memory`, `--cleanup`.
# Approvals:             in a terminal you are asked y/N; in a notebook or a scripted run they are approved.
#
# Lines marked `# 👉` are the ones to retype during the lab.

# %%
import json
import pathlib
import re
import sys

_here = (pathlib.Path(globals()["__file__"]).resolve().parent if "__file__" in globals() else
         next(p for p in (pathlib.Path.cwd(), pathlib.Path.cwd() / "content" / "assets") if (p / "common").is_dir()))
sys.path.insert(0, str(_here))
from common import livewell_common as lw  # noqa: E402


def _flags(p):
    p.add_argument("--fabric", action="store_true", help="run the Fabric step (needs FABRIC_BRIDGE=true)")
    p.add_argument("--no-memory", action="store_true", help="skip memory (preview)")


args = lw.lab_args("Lab 3 - tools, MCP and memory", _flags)
GUARDRAIL = lw.NAMES["rai_policy"]
lw.heading(f"Lab 3 for {lw.agent_name('coach')}")

# %% [markdown]
# ## 1. The session resident and the profile tool
#
# The function tool only describes the call; the model decides when to make it and this script answers it.
# `get_citizen_profile` refuses any resident except the signed-in one, exactly like the Navigator OpenAPI tool.

# %%
me = lw.get_citizen_profile("me")
lw.say(f"session resident: {me['display_name']}, {me['age_band']}, {me['planning_area']} ({me['region']}), "
       f"screening {me['screening_risk']}, {me['avg_daily_steps']:.0f} steps/day, hazy region: {bool(me['region_is_hazy'])}")
lw.say(f"another resident -> {lw.get_citizen_profile('RESIDENT_00062')}")
profile = lw.profile_tool()  # 👉
knowledge = lw.kb_tool()

# %% [markdown]
# ## 2. The activities MCP server, with approval before any write

# %%
activities = lw.activities_tool(approve_writes=True)  # 👉
lw.warm_activities()  # the server scales to zero; wake it while the agents are created

# %% [markdown]
# ## 3. Memory (preview)
#
# A memory store per participant (`livewell-<INITIALS>-memory`), scoped to you. The store uses gpt-5-mini to
# extract and summarise memories.

# %%
memory, store = None, None
if not args.no_memory:
    try:
        store = lw.ensure_memory_store()  # 👉
        memory = lw.memory_tool(store)  # 👉
        lw.say(f"memory store {store}, scope {lw.memory_scope()}")
    except Exception as e:  # preview not enabled in this project/region
        lw.say(f"memory is not available here ({lw._trunc(e, 160)}); continuing without it")

# %% [markdown]
# ## 4. Specialists, connected as function tools
#
# The Nutrition specialist searches the guides; the Activity specialist also sees `find_activities` but never
# `register_interest`, so only the coach can ask you to approve a registration.

# %%
nutrition = lw.create_agent("nutrition", lw.load_instructions("nutrition"), tools=[knowledge], rai_policy=GUARDRAIL,
                            description="LiveWell Nutrition specialist")
activity = lw.create_agent("activity", lw.load_instructions("activity"),
                           tools=[knowledge, lw.activities_tool(read_only=True)], rai_policy=GUARDRAIL,
                           description="LiveWell Activity specialist")
SPECIALIST_PARAMS = {"type": "object", "properties": {
    "question": {"type": "string", "description": "What the resident needs from the specialist."},
    "profile_summary": {"type": "string", "description": "Age band, conditions, steps, region hazy flag and stated "
                                                         "preferences. Never include a resident_id."}}}
nutrition_tool = lw.function_tool("livewell-nutrition", "Ask the Nutrition specialist for a meal suggestion or "
                                  "meal plan grounded in the LiveWell guides.", SPECIALIST_PARAMS)  # 👉
activity_tool = lw.function_tool("livewell-activity", "Ask the Activity specialist for a safe exercise plan and "
                                 "community activities grounded in the LiveWell guides.", SPECIALIST_PARAMS)  # 👉


SPECIALIST_CALLS: list[tuple[str, list[str]]] = []  # (specialist, its own tool calls), for the checks below


def specialist(agent):
    def handler(question: str, profile_summary: str = "") -> str:
        run = lw.ask(agent, f"Resident profile: {profile_summary}\n\nQuestion: {question}", consent=False)
        SPECIALIST_CALLS.append((agent.name, run.tool_names))
        if args.verbose:
            lw.show_run(run, verbose=True, max_chars=400)
        return f"[specialist blocked by guardrail: {run.block_reason}]" if run.blocked else run.text
    return handler


FUNCTIONS = {"get_citizen_profile": lw.get_citizen_profile,  # 👉
             "livewell-nutrition": specialist(nutrition), "livewell-activity": specialist(activity)}
lw.say(f"specialists: {nutrition.name} v{nutrition.version}, {activity.name} v{activity.version}")

# %% [markdown]
# ## 5. The Lab 3 coach
#
# Base + knowledge + safety + tools instruction blocks, the workshop guardrail, and the evidence JSON contract
# (advice, confidence, supporting_guides, rationale, personalisation_flags). The coach runs on `lw.TOOLS_MODEL`
# (gpt-4.1-mini): the agent service does not support function, OpenAPI, A2A or Fabric tools on gpt-5-mini.
# The specialists above have only the knowledge base and MCP, so they stay on gpt-5-mini.

# %%
blocks = ["base", "knowledge", "safety", "tools"]
tools = [profile, knowledge, activities, nutrition_tool, activity_tool] + ([memory] if memory else [])
coach = lw.create_agent(
    "coach",
    lw.load_instructions(*blocks),  # 👉
    tools=tools,  # 👉
    schema=lw.evidence_schema(), schema_name="livewell_evidence",
    model=lw.TOOLS_MODEL,  # 👉
    rai_policy=GUARDRAIL,
    description="LiveWell Coach - Lab 3 tools, MCP and memory",
)
lw.say(f"coach = {coach.name} version {coach.version} on {coach.definition.model}")


def no_resident_id(run) -> bool:
    return not re.search(r"RESIDENT_\d+", run.text or "")


# find_activities condition_friendly values that fit the session resident (the tools block has the same mapping)
CONDITION_MAP = {"elevated blood glucose": "pre-diabetes", "high blood pressure": "hypertension",
                 "high cholesterol": "high-cholesterol"}
FITS = {CONDITION_MAP[c] for c in me.get("conditions", []) if c in CONDITION_MAP} | {"seniors", "beginners", ""}
CONDITION_WORDS = {"blood pressure": "high blood pressure", "hypertension": "high blood pressure",
                   "cholesterol": "high cholesterol", "glucose": "elevated blood glucose",
                   "diabetes": "elevated blood glucose"}
OTHER_CONDITIONS = [w for w, cond in CONDITION_WORDS.items() if cond not in me.get("conditions", [])]


def advice_of(run) -> str:
    """The advice field of the evidence JSON, or the whole reply when it is not JSON."""
    if run.blocked:
        return ""
    try:
        return str(run.json().get("advice", run.text))
    except ValueError:
        return run.text or ""


def fits_profile(*runs) -> tuple[bool, list]:
    """find_activities used a condition the resident has, and the advice names no condition they do not have."""
    used = [json.loads(c.arguments or "{}").get("condition_friendly", "") for r in runs for c in r.tool_calls
            if c.kind == "mcp_call" and c.name == "find_activities"]
    advice = " ".join(advice_of(r) for r in runs).lower()
    wrong = [u for u in used if u not in FITS] + [c for c in OTHER_CONDITIONS if c in advice]
    return not wrong, wrong or used


def invented(*runs) -> list[str]:
    return sorted({g for r in runs for g in lw.invented_guides(r)})


# %% [markdown]
# ## 6. Personalised advice (`lab3_profile_tailored`)

# %%
tailored = lw.ask(coach, prompt_id="lab3_profile_tailored", functions=FUNCTIONS)  # 👉
lw.show_run(tailored, verbose=args.verbose)
evidence = tailored.json() if not tailored.blocked else {}
flags = " ".join(evidence.get("personalisation_flags", [])).lower().replace("-", "_")
signals = {"age_60_64": r"60_64|60s|age", "screening_high": r"screening|high risk", "elevated_glucose": r"glucose|sugar",
           "low_steps": r"step|activity|mvpa", "hazy_region": r"haz|psi"}
hit = [k for k, pattern in signals.items() if re.search(pattern, flags)]
lw.expect("lab3_profile_tailored: profile tool called", tailored.called("get_citizen_profile"), tailored.tool_names)
lw.expect("lab3_profile_tailored: >= 2 personalisation signals", len(hit) >= 2, hit)
lw.expect("lab3_profile_tailored: cites a real guide", bool(tailored.citations), tailored.citations)
lw.expect("lab3_profile_tailored: no invented guide ids", not invented(tailored), invented(tailored))
lw.expect("lab3_profile_tailored: no resident_id in the reply", no_resident_id(tailored))
lw.record("lab3_profile_tailored", tailored)

# %% [markdown]
# ## 7. A compound request with a human in the loop (`lab3_hazy_indoor_signup`)
#
# Expect the profile and `find_activities` first. Discovery lists options without registering; the next turn
# confirms the first indoor option in the same conversation. The approval request must appear BEFORE
# `register_interest` runs.

# %%
conversation = lw.new_conversation()
SPECIALIST_CALLS.clear()
signup = lw.ask(coach, prompt_id="lab3_hazy_indoor_signup", functions=FUNCTIONS, approve=False,  # 👉
                conversation=conversation)
lw.show_run(signup, verbose=args.verbose)
turns = [signup]
discovery_read_only = not signup.approvals and not signup.called("register_interest")
lw.expect("lab3_hazy_indoor_signup: discovery is read-only", discovery_read_only, signup.tool_names)
discovery_searched = signup.called("knowledge_base_retrieve")
lw.expect("lab3_hazy_indoor_signup: knowledge base searched", discovery_searched, signup.tool_names)
if discovery_read_only and discovery_searched:
    follow = lw.ask(coach, prompt_id="lab3_signup_confirm", functions=FUNCTIONS,
                    approve=lw.ask_human, conversation=conversation, consent=False)
    lw.show_run(follow, verbose=args.verbose)
    turns.append(follow)
calls = [c for run in turns for c in run.tool_calls]
kinds = [(c.kind, c.name) for c in calls]
names = [c.name for c in calls]
asked = next((i for i, c in enumerate(calls) if c.kind == "mcp_approval_request" and c.name == "register_interest"), None)
wrote = next((i for i, c in enumerate(calls) if c.kind == "mcp_call" and c.name == "register_interest"), None)
# The coach may search activities itself or through the Activity specialist (read-only find_activities).
delegated = [f"{name.rsplit('-', 1)[-1]}:{tool}" for name, used in SPECIALIST_CALLS for tool in used]
lw.expect("lab3_hazy_indoor_signup: >= 2 tools (profile + find_activities)",
          "get_citizen_profile" in names and ("find_activities" in names or "activity:find_activities" in delegated),
          sorted(set(names)) + delegated)
lw.expect("lab3_hazy_indoor_signup: approval requested before register_interest", asked is not None
          and (wrote is None or asked < wrote), f"approval at {asked}, write at {wrote}")
lw.expect("lab3_hazy_indoor_signup: activities fit the resident's conditions", *fits_profile(*turns))
lw.expect("lab3_hazy_indoor_signup: no invented guide ids", not invented(*turns), invented(*turns))
lw.expect("lab3_hazy_indoor_signup: no resident_id in the reply", all(no_resident_id(r) for r in turns))
lw.record("lab3_hazy_indoor_signup", {"turns": [r.summary() for r in turns], "tool_calls": kinds})

# %% [markdown]
# ## 8. Memory across conversations (`lab3_memory_set` -> new conversation -> `lab3_memory_recall`)

# %%
recall = None
if memory:
    told = lw.ask(coach, prompt_id="lab3_memory_set", functions=FUNCTIONS, conversation=lw.new_conversation())  # 👉
    lw.show_run(told, verbose=args.verbose)
    lw.say("waiting for the preference to reach memory (up to 2 minutes) ...")
    remembered = lw.wait_for_memories(store, match=r"morning|swim")
    lw.say(f"memories: {remembered}")
    recall = lw.ask(coach, prompt_id="lab3_memory_recall", functions=FUNCTIONS,  # 👉
                    conversation=lw.new_conversation())
    lw.show_run(recall, verbose=args.verbose)
    advice = lw.ascii_safe(advice_of(recall))
    negated = re.compile(r"\b(not|no|avoid\w*|dislike\w*|instead|skip|without)\b|n't", re.I)
    swim = [s for s in re.split(r"(?<=[.!?;])\s+|\n+", advice) if re.search(r"swim|aqua|pool", s, re.I)
            and not negated.search(s)]
    lw.expect("lab3_memory_recall: preference remembered",
              any(re.search(r"morning|swim", m, re.I) for m in remembered), remembered)
    lw.expect("lab3_memory_recall: suggests mornings", bool(re.search(r"morning|\b([6-9]|1[01])(:\d\d)?\s*a\.?m", advice, re.I)))
    lw.expect("lab3_memory_recall: no swimming or aqua suggestion", not swim, swim)
    lw.expect("lab3_memory_recall: activities fit the resident's conditions", *fits_profile(recall))
    lw.expect("lab3_memory_recall: no invented guide ids", not invented(recall), invented(recall))
    lw.record("lab3_memory_recall", recall)
else:
    lw.say("memory skipped")

# %% [markdown]
# ## 9. Specialists (`lab3_specialists`)

# %%
plans = lw.ask(coach, prompt_id="lab3_specialists", functions=FUNCTIONS)  # 👉
lw.show_run(plans, verbose=args.verbose)
lw.expect("lab3_specialists: both specialists consulted",
          plans.called("livewell-nutrition") and plans.called("livewell-activity"), plans.tool_names)
lw.expect("lab3_specialists: one merged reply with guides", bool(plans.citations), plans.citations)
lw.expect("lab3_specialists: no invented guide ids", not invented(plans), invented(plans))
lw.record("lab3_specialists", plans)

# %% [markdown]
# ## 10. Fabric step (only with `--fabric` / FABRIC_BRIDGE=true)
#
# A new coach version adds the Fabric IQ tool (the published Resident360 Ontology Agent, connection
# `livewell-fabric-resident360`) and the `fabric` routing block. Mei's programme question should go to Fabric
# (the first call can take 1-2 minutes); Rahim's food question must not. Then Rahim's programme fit: the coach
# reads his profile, asks Fabric ONE aggregate question about his age band (never his id, name or area),
# recommends the programme people his age stay in that he is not already in, finds its intake session and asks
# before it registers him.

# %%
fabric_result: dict = {}
if lw.fabric_enabled(args.fabric):
    fabric_coach = lw.create_agent(
        "coach", lw.load_instructions(*blocks, "fabric"),  # 👉
        tools=tools + [lw.fabric_tool()],  # 👉
        schema=lw.evidence_schema(), schema_name="livewell_evidence",
        model=lw.TOOLS_MODEL, rai_policy=GUARDRAIL,
        description="LiveWell Coach - Lab 3 Fabric step")
    lw.say(f"fabric coach = {fabric_coach.name} version {fabric_coach.version}")
    mei = lw.ask(fabric_coach, prompt_id="fabric_q_disengaged_regions", functions=FUNCTIONS,  # 👉
                 timeout=lw.FABRIC_TIMEOUT)
    lw.show_run(mei, verbose=args.verbose)
    reference = json.loads((lw.CONTENT / "fabric" / "reference-answers.json").read_text(encoding="utf-8"))
    ranked = [r["region"] for r in sorted(reference["q_disengaged_regions"]["rows"], key=lambda r: -r["share_pct"])]
    first = re.search(r"\b(North[- ]East|North|West|Central|East)\b", lw.ascii_safe(mei.text))
    top = first.group(1).replace(" ", "-") if first else None
    lw.expect("fabric_q_disengaged_regions: Fabric IQ tool called", mei.fabric_called, mei.tool_names)
    lw.expect("fabric_q_disengaged_regions: top region matches the reference (+-1 rank)", top in ranked[:2],
              f"{top} vs reference {ranked[:3]}")
    lw.expect("fabric_q_disengaged_regions: no resident_id", no_resident_id(mei))
    rahim = lw.ask(fabric_coach, prompt_id="lab1_prediabetes_eat", functions=FUNCTIONS)  # 👉
    lw.show_run(rahim, verbose=args.verbose)
    lw.expect("lab1_prediabetes_eat on the Fabric coach: no Fabric call", not rahim.fabric_called, rahim.tool_names)
    lw.expect("lab1_prediabetes_eat on the Fabric coach: answered from the guides (knowledge base or Nutrition "
              "specialist)", rahim.kb_called or rahim.called("livewell-nutrition"), rahim.tool_names)
    fabric_line = next((f"{c.kind} {c.server}.{c.name} ({mei.seconds:.0f}s)" for c in mei.tool_calls if c.is_fabric), None)
    fabric_result = {"fabric trace line": fabric_line, "fabric answer": mei.json() if not mei.blocked else mei.block_reason}
    lw.record("fabric_q_disengaged_regions", mei)
    lw.record("fabric_citizen_control", rahim)

    fit_ref = reference["q_programme_fit"]
    conversation = lw.new_conversation()
    fit = lw.ask(fabric_coach, prompt_id="lab3_programme_fit", functions=FUNCTIONS, approve=lw.ask_human,  # 👉
                 conversation=conversation, timeout=lw.FABRIC_TIMEOUT)
    lw.show_run(fit, verbose=args.verbose)
    fit_turns = [fit]
    if not fit.approvals:
        more = lw.ask(fabric_coach, prompt_id="lab3_programme_confirm",
                      functions=FUNCTIONS, approve=lw.ask_human, conversation=conversation, consent=False,
                      timeout=lw.FABRIC_TIMEOUT)
        lw.show_run(more, verbose=args.verbose)
        fit_turns.append(more)
    fit_calls = [c for r in fit_turns for c in r.tool_calls]

    def question_sent(call) -> str:
        try:
            return str(json.loads(call.arguments or "{}").get("userQuestion", call.arguments))
        except ValueError:
            return call.arguments

    sent = [question_sent(c) for c in fit_calls if c.is_fabric and c.kind == "mcp_call"]
    personal = [w for w in (r"RESIDENT_\d+", re.escape(me["display_name"]), re.escape(me["planning_area"]))
                if any(re.search(w, s, re.I) for s in sent)]
    first_profile = next((i for i, c in enumerate(fit_calls) if c.name == "get_citizen_profile"), None)
    first_fabric = next((i for i, c in enumerate(fit_calls) if c.is_fabric), None)
    asked = next((i for i, c in enumerate(fit_calls) if c.kind == "mcp_approval_request" and c.name == "register_interest"), None)
    wrote = next((i for i, c in enumerate(fit_calls) if c.kind == "mcp_call" and c.name == "register_interest"), None)
    said = lw.ascii_safe(" ".join(advice_of(r) for r in fit_turns))
    lw.expect("lab3_programme_fit: Fabric IQ tool called", bool(sent), [c.name for c in fit_calls])
    lw.expect("lab3_programme_fit: profile read before the Fabric question",
              first_profile is not None and first_fabric is not None and first_profile < first_fabric,
              f"profile at {first_profile}, Fabric at {first_fabric}")
    lw.expect("lab3_programme_fit: no resident_id or personal detail sent to Fabric", bool(sent) and not personal,
              sent or "no Fabric call")
    lo, hi = re.findall(r"\d+", me["age_band"])[:2]
    lw.expect("lab3_programme_fit: asks about the age band",
              any(re.search(rf"\b{lo}\s*(?:-|–|to)\s*{hi}\b", s) for s in sent), sent)
    lw.expect("lab3_programme_fit: recommends the reference programme",
              fit_ref["recommended_programme"].lower() in said.lower(), fit_ref["recommended_programme"])
    lw.expect("lab3_programme_fit: approval requested before register_interest", asked is not None
              and (wrote is None or asked < wrote), f"approval at {asked}, write at {wrote}")
    lw.expect("lab3_programme_fit: no resident_id in the reply", all(no_resident_id(r) for r in fit_turns))
    fabric_result["programme fit: question sent to Fabric"] = sent
    fabric_result["programme fit: advice"] = said
    lw.record("lab3_programme_fit", {"turns": [r.summary() for r in fit_turns],
                                     "tool_calls": [(c.kind, c.name) for c in fit_calls], "sent_to_fabric": sent})
else:
    lw.say("Fabric step skipped (run with --fabric when the facilitator confirms FABRIC_BRIDGE=true)")

# %% [markdown]
# ## 11. Checkpoint
#
# The tool-call order, the evidence JSON and the memory recall (plus the Fabric results with `--fabric`) in one
# place. Compare them with Expected output under Checkpoint on the lab page; there is nothing to submit.

# %%
lw.checkpoint("Lab 3", {
    "lab3_hazy_indoor_signup tool calls": [f"{k} {n}" for k, n in kinds],
    "lab3_profile_tailored": evidence,
    "lab3_memory_recall (new conversation)": (recall.json() if recall and not recall.blocked else "(memory skipped)"),
    **fabric_result,
})
lw.say(f"results saved to {lw.save_results('lab3')}")
if args.cleanup:
    lw.cleanup()
