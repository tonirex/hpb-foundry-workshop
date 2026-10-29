# %% [markdown]
# # Fabric step - Compare governed data with document retrieval - Builder rail
#
# Run `python content/assets/lab3_fabric.py` only after Fabric is enabled for the workshop.
# This read-only question pair does not rerun Lab 3, register interest or require a Navigator agent.
# --verbose shows tool arguments and responses; --cleanup removes this run's own agents.

# %%
import pathlib
import sys

_here = (pathlib.Path(globals()["__file__"]).resolve().parent if "__file__" in globals() else
         next(p for p in (pathlib.Path.cwd(), pathlib.Path.cwd() / "content" / "assets") if (p / "common").is_dir()))
sys.path.insert(0, str(_here))
from common import livewell_common as lw  # noqa: E402

args = lw.lab_args("Fabric step - read-only source comparison")
if not lw.fabric_enabled():
    raise SystemExit("Fabric is not enabled. Skip this optional step until FABRIC_BRIDGE=true is confirmed.")

# %% [markdown]
# ## 1. Connect the two prepared evidence sources
#
# A separate Builder agent keeps the Lab 3 coach and its memory/approval configuration unchanged.
# No activity-write or profile tool is attached to this two-question exercise.

# %%
agent = lw.create_agent(
    "fabric",
    lw.load_instructions("base", "knowledge", "safety", "fabric_read"),  # 👉
    tools=[lw.kb_tool(), lw.fabric_tool()],  # 👉
    schema=lw.lab1_schema(),
    model=lw.TOOLS_MODEL,
    rai_policy=lw.NAMES["rai_policy"],
    description="LiveWell - read-only Fabric and knowledge comparison",
)
lw.say(f"created {agent.name} version {agent.version}")

# %% [markdown]
# ## 2. Ask for region aggregates, then ask for guide-based advice
#
# Inspect the outgoing Fabric question and returned aggregates. The guide question should use the KB instead.

# %%
regions = lw.ask(agent, prompt_id="fabric_q_disengaged_regions", consent=False,
                 approve=False, timeout=lw.FABRIC_TIMEOUT)  # 👉
lw.show_run(regions, verbose=args.verbose)
lw.expect("fabric_q_disengaged_regions: Fabric IQ tool called", regions.fabric_succeeded, regions.tool_names)
lw.record("fabric_q_disengaged_regions", regions)

food = lw.ask(agent, prompt_id="lab1_prediabetes_eat", consent=False, approve=False)  # 👉
lw.show_run(food, verbose=args.verbose)
lw.expect("lab1_prediabetes_eat: knowledge base searched", food.kb_called, food.tool_names)
lw.expect("lab1_prediabetes_eat: no Fabric call", not food.fabric_called, food.tool_names)
lw.record("lab1_prediabetes_eat", food)

# %% [markdown]
# ## 3. Checkpoint

# %%
lw.checkpoint("Fabric step", {
    "region answer": regions.text,
    "region tools": regions.tool_names,
    "guide answer": food.text,
    "guide tools": food.tool_names,
})
lw.say(f"results saved to {lw.save_results('fabric')}")
if args.cleanup:
    lw.cleanup()
