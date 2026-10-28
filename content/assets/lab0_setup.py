# %% [markdown]
# # Lab 0 - Setup and first agent - Builder rail
#
# Run `python content/assets/lab0_setup.py` after check_setup.py reports All set.
# INITIALS and the project endpoint come from content/assets/.env. No portal agent is required.
# --verbose shows execution details; --cleanup removes this run's own agents.

# %%
import pathlib
import sys

_here = (pathlib.Path(globals()["__file__"]).resolve().parent if "__file__" in globals() else
         next(p for p in (pathlib.Path.cwd(), pathlib.Path.cwd() / "content" / "assets") if (p / "common").is_dir()))
sys.path.insert(0, str(_here))
from common import livewell_common as lw  # noqa: E402

args = lw.lab_args("Lab 0 - first Builder agent")

# %% [markdown]
# ## 1. Configure a model and instructions, without tools

# %%
coach = lw.create_agent(
    "coach", lw.load_instructions("base"), tools=[],  # 👉
    rai_policy=lw.DEFAULT_RAI_POLICY,
    description="LiveWell Coach - Lab 0 first Builder agent",
)
lw.say(f"created {coach.name} version {coach.version} on model {lw.DEFAULT_MODEL}")

# %% [markdown]
# ## 2. Compare an introduction and a diagnosis question
#
# Inspect the actual replies. One refusal demonstrates intended behaviour, not comprehensive safety.

# %%
replies = {}
for prompt_id in ("lab0_hi", "lab0_am_i_diabetic"):
    run = lw.ask(coach, prompt_id=prompt_id)  # 👉
    lw.show_run(run, verbose=args.verbose)
    lw.expect(f"{prompt_id}: no tools configured or called", not run.tool_calls, run.tool_names)
    lw.record(prompt_id, run)
    replies[prompt_id] = run.text if not run.blocked else f"[BLOCKED: {run.block_reason}]"

# %% [markdown]
# ## 3. Checkpoint

# %%
lw.checkpoint("Lab 0", replies)
lw.say(f"results saved to {lw.save_results('lab0')}")
if args.cleanup:
    lw.cleanup()
else:
    lw.say(f"Keep {coach.name} for the Builder track. Lab 1 adds knowledge to it.")
