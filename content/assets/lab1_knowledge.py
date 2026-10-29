# %% [markdown]
# # Lab 1 - Agents & Knowledge (Foundry IQ) - Builder rail
#
# Rahim's screening came back with high glucose. In this lab you build **livewell-<INITIALS>-coach**, a
# prompt agent that answers ONLY from the LiveWell guides (a Foundry IQ knowledge base on Azure AI Search),
# cites the guide ids it used, and replies as machine-routable JSON.
#
# Run it all:            `python content/assets/lab1_knowledge.py` (INITIALS and endpoint from content/assets/.env)
# Or cell by cell:       open this file in VS Code / Codespaces and use "Run Cell" on each `# %%`.
# Flags:                 `--verbose` (tool calls, citations, response ids), `--cleanup`.
#
# Lines marked `# 👉` are the ones to retype during the lab.

# %%
import pathlib
import sys

_here = (pathlib.Path(globals()["__file__"]).resolve().parent if "__file__" in globals() else
         next(p for p in (pathlib.Path.cwd(), pathlib.Path.cwd() / "content" / "assets") if (p / "common").is_dir()))
sys.path.insert(0, str(_here))
from common import livewell_common as lw  # noqa: E402

args = lw.lab_args("Lab 1 - knowledge-grounded coach")
lw.heading(f"Lab 1 for {lw.agent_name('coach')} on {lw.endpoint()}")

# %% [markdown]
# ## 1. Instructions and the knowledge tool
#
# The coach keeps the Lab 0 `base` block and appends the `knowledge` block from
# `content/prompts/coach-instructions.md`. The knowledge base is reached over its MCP endpoint through the
# project connection `livewell-guides-kb-mcp`; the helper looks up the connection so no URL or key lives
# in this file.

# %%
instructions = lw.load_instructions("base", "knowledge")  # 👉
knowledge = lw.kb_tool()  # 👉
lw.say(f"knowledge tool: server_label={knowledge.server_label} connection={knowledge.project_connection_id}")
if args.verbose:
    lw.say(f"   MCP endpoint: {knowledge.server_url}")

# %% [markdown]
# ## 2. Create the coach with a strict JSON response format
#
# `lab1_schema()` is the Lab 1 contract from `test-prompts.json`: `answer`, `intent`, `risk_level`, `route`,
# `cited_sources`, `personalisation_flags`. `strict=True` means the model must return exactly that shape.
#
# The coach runs with the platform's default guardrail (`Microsoft.DefaultV2`). In Lab 2 you attach the
# workshop guardrail `livewell-guardrails` and compare the two.

# %%
coach = lw.create_agent(
    "coach",
    instructions,
    tools=[knowledge],  # 👉
    schema=lw.lab1_schema(),  # 👉
    rai_policy=lw.DEFAULT_RAI_POLICY,
    description="LiveWell Coach - Lab 1 knowledge-grounded version",
)
lw.say(f"created {coach.name} version {coach.version} on model {lw.DEFAULT_MODEL}")

# %% [markdown]
# ## 3. A cited food-guidance answer (`lab1_prediabetes_eat`)
#
# Expect route `self_care`, at least one real guide id in `cited_sources` (usually
# `lg-05-eating-for-pre-diabetes`) and no invented source.

# %%
eat = lw.ask(coach, prompt_id="lab1_prediabetes_eat")  # 👉
lw.show_run(eat, verbose=args.verbose)
eat_json = eat.json() if not eat.blocked else {}
exp = lw.expected("lab1_prediabetes_eat")
invented = [s for s in eat_json.get("cited_sources", []) if not lw.normalise_guide(s)]
lw.expect("lab1_prediabetes_eat: knowledge base searched", eat.kb_called)
lw.expect("lab1_prediabetes_eat: cites a real guide", bool(set(eat.citations) & set(lw.guide_ids())), eat.citations)
lw.expect("lab1_prediabetes_eat: cites an expected guide", bool(set(eat.citations) & set(exp["cited_sources_any"])))
lw.expect("lab1_prediabetes_eat: cited guides were retrieved",
          bool(eat.citations) and set(eat.citations) <= set(eat.retrieved_guides), eat.retrieved_guides)
lw.expect("lab1_prediabetes_eat: no invented source", not invented, invented)
lw.expect("lab1_prediabetes_eat: route self_care", eat_json.get("route") == exp["route"], eat_json.get("route"))
lw.record("lab1_prediabetes_eat", eat)

# %% [markdown]
# ## 4. When the guides are silent (`lab1_supplement`)
#
# The guides do not cover supplements. A grounded coach says so, cites nothing and routes to a clinician.

# %%
supp = lw.ask(coach, prompt_id="lab1_supplement")  # 👉
lw.show_run(supp, verbose=args.verbose)
supp_json = supp.json() if not supp.blocked else {}
lw.expect("lab1_supplement: route clinician", supp_json.get("route") == "clinician", supp_json.get("route"))
lw.expect("lab1_supplement: cites nothing", len(supp_json.get("cited_sources", [])) == 0, supp_json.get("cited_sources"))
lw.expect("lab1_supplement: says the guides don't cover it",
          bool(lw.re.search(r"(guides?|LiveWell)[^.]{0,40}(do(n't| not)|does(n't| not)) (cover|include|mention)", supp_json.get("answer", ""), lw.re.I)))
lw.record("lab1_supplement", supp)

# %% [markdown]
# ## 5. Checkpoint
#
# The two JSON replies in one place. Compare them with Expected output
# under Checkpoint on the lab page; there is nothing to submit.

# %%
lw.checkpoint("Lab 1", {"lab1_prediabetes_eat": eat_json, "lab1_supplement": supp_json})
lw.say(f"results saved to {lw.save_results('lab1')}")
if args.cleanup:
    lw.cleanup()
else:
    lw.say(f"{coach.name} stays in the project for Lab 2. Open it in the portal: Agents > {coach.name}.")
