# %% [markdown]
# # Lab 2 - Evaluation code walkthrough (do not run during the workshop)
#
# Read these cells with the facilitator and inspect their completed v1/v2 comparison.
# Each judged row makes several model calls. A room of parallel evaluations can exhaust the shared
# quota and take longer than the hands-on lab. This is separate from lab2_govern.py.
#
# Opening this file, running it without flags, or using Run All in a notebook makes NO cloud calls.
# Only a deliberate terminal invocation with --run enables evaluation (facilitator or approved
# after-workshop use). --eval-all selects all 30 rows; otherwise the same six-row subset is used.
# --upload also publishes results to Foundry; it is not required for local result files.
# --verbose shows evaluator logs. --cleanup is a no-op: this script creates no agents.
#
# Preparation and the opt-in command are in content/admin/ADMIN-SETUP.md, "Lab 2 shared evaluation".
# Never import lab2_govern.py here: importing it would repeat the hands-on calls and create versions.

# %%
import argparse
import contextlib
import json
import math
import pathlib
import sys
import tempfile

parser = argparse.ArgumentParser(description="Lab 2 evaluation code walkthrough; no cloud calls without --run.",
                                 allow_abbrev=False)
parser.add_argument("--run", action="store_true", help="explicitly enable paid evaluation outside the participant lab")
parser.add_argument("--eval-all", action="store_true", help="evaluate all 30 rows instead of the six-row subset")
parser.add_argument("--upload", action="store_true", help="also publish the evaluation to Foundry")
parser.add_argument("--verbose", action="store_true", help="show evaluator logs and detailed metrics")
parser.add_argument("--cleanup", action="store_true", help="no-op: existing agents are reused, never created or deleted")
args = parser.parse_args([] if __name__ != "__main__" or "ipykernel" in sys.modules else None)
if not args.run:
    if args.eval_all or args.upload or args.cleanup:
        parser.error("--eval-all, --upload and --cleanup require explicit --run; read the code during the workshop.")
    print("CODE WALKTHROUGH ONLY - no cloud calls or evaluation jobs started.\n"
          "Do not run evaluations during the workshop: they can exceed the lab time and shared quota.\n"
          "Read cells 1-4 and review the facilitator's completed comparison instead.")

# %% [markdown]
# ## 1. Reuse the exact baseline and guarded versions from the hands-on run
#
# lab2_govern.py saves their names, version numbers and project binding in .runs/lab2-<initials>.json.
# Do not pick "latest": a later lab may have changed the coach. Do not silently use another environment.
# Both versions must still exist, so the facilitator prepares them without --cleanup.

# %%
if args.run:
    _here = pathlib.Path(__file__).resolve().parent
    sys.path.insert(0, str(_here))
    sys.path.insert(0, str(_here.parent / "eval" / "evaluators"))
    from common import livewell_common as lw
    from azure.core.exceptions import ResourceNotFoundError

    source = lw.RUNS_DIR / f"lab2-{lw.initials()}.json"
    try:
        saved = json.loads(source.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise SystemExit(f"Cannot read {source.name}. Prepare lab2_govern.py once without --cleanup; "
                         "do not run an evaluation during the workshop.") from error
    if not isinstance(saved, dict) or saved.get("lab") != "lab2" or saved.get("initials") != lw.initials():
        raise SystemExit("Saved comparison is not a Lab 2 run for these initials.")
    results = saved.get("results")
    comparison = results.get("comparison") if isinstance(results, dict) else None
    if not isinstance(comparison, dict):
        raise SystemExit("Saved run has no pinned comparison. Prepare it with the current lab2_govern.py first.")
    if comparison.get("project_endpoint") != lw.endpoint():
        raise SystemExit("Saved comparison belongs to a different project. Select its original environment.")
    if comparison.get("cleanup_requested"):
        raise SystemExit("The hands-on run requested cleanup. Prepare lab2_govern.py again without --cleanup.")
    for label in ("v1", "v2"):
        ref = comparison.get(label)
        allowed = {lw.agent_name("coach")}
        if label == "v2":
            allowed.add(lw.NAMING["demo_agents"]["guarded"])
        if (not isinstance(ref, dict) or ref.get("name") not in allowed
                or not isinstance(ref.get("version"), str) or not ref["version"].isascii()
                or not ref["version"].isdecimal()):
            raise SystemExit(f"Saved {label} must pin an own-coach version or the guarded comparator.")
    agents = {}
    for label in ("v1", "v2"):
        ref = comparison[label]
        try:
            agents[label] = lw.project().agents.get_version(agent_name=ref["name"], agent_version=ref["version"])
        except ResourceNotFoundError as error:
            raise SystemExit(f"Saved {label} version no longer exists. Prepare lab2_govern.py without --cleanup.") from error
        expected_guarded = label == "v2"
        if (lw.rai_policy_of(agents[label]) == lw.NAMES["rai_policy"]) != expected_guarded:
            raise SystemExit(f"Saved {label} does not have the expected default/custom guardrail configuration.")
        lw.say(f"{label}: {ref['name']} version {ref['version']}")

# %% [markdown]
# ## 2. Select the same rows and map their columns to the judges
#
# Five built-in LLM judges score groundedness, relevance, task adherence, intent resolution and
# tool-call accuracy. The existing advice_matches_conditions code check adds domain-specific checks.
# Groundedness needs the actual retrieved guide passages, not a prompt ID or a made-up context.

# %%
if args.run:
    from advice_matches_conditions import AdviceMatchesConditionsEvaluator
    from azure.ai.evaluation import (GroundednessEvaluator, IntentResolutionEvaluator, RelevanceEvaluator,
                                     TaskAdherenceEvaluator, ToolCallAccuracyEvaluator, evaluate)

    DEFAULT_ROWS = ["lw-02", "lw-09", "lw-10", "lw-26", "lw-03", "lw-29"]
    rows = lw.load_eval_rows() if args.eval_all else lw.load_eval_rows(ids=DEFAULT_ROWS)
    if not rows:
        raise SystemExit("The evaluation dataset is empty; no responses were generated and no judge calls were made.")
    judge, cred = lw.judge_model_config(), lw.credential()
    evaluators = {
        "groundedness": GroundednessEvaluator(judge, credential=cred),
        "relevance": RelevanceEvaluator(judge, credential=cred),
        "task_adherence": TaskAdherenceEvaluator(judge, credential=cred),
        "intent_resolution": IntentResolutionEvaluator(judge, credential=cred),
        "tool_call_accuracy": ToolCallAccuracyEvaluator(judge, credential=cred),
        "advice_matches_conditions": AdviceMatchesConditionsEvaluator(),
    }
    q, r = "${data.query}", "${data.response}"
    qm, rm, td = "${data.query_messages}", "${data.response_messages}", "${data.tool_definitions}"
    evaluator_config = {
        "groundedness": {"column_mapping": {"query": q, "response": r, "context": "${data.context}"}},
        "relevance": {"column_mapping": {"query": q, "response": r}},
        "task_adherence": {"column_mapping": {"query": qm, "response": rm, "tool_definitions": td}},
        "intent_resolution": {"column_mapping": {"query": qm, "response": rm, "tool_definitions": td}},
        "tool_call_accuracy": {"column_mapping": {"query": qm, "response": rm, "tool_calls": "${data.tool_calls}",
                                                  "tool_definitions": td}},
        "advice_matches_conditions": {"column_mapping": {"response": r, "conditions": "${data.conditions}"}},
    }

# %% [markdown]
# ## 3. Generate responses, then evaluate one version at a time
#
# This is the expensive step. Even local result files require live agent and judge calls.
# Red-flag rows and blocked replies are not sent to the judge deployment; inspect their guardrail
# outcomes separately. A blocked or unscored row is not a perfect groundedness score.
# --upload adds portal publishing. An evaluation/upload error stops the run, without automatically
# repeating the batch. Keep the input JSONL, result files and logs for diagnosis before retrying.

# %%
if args.run:
    lw.RUNS_DIR.mkdir(exist_ok=True)
    workdir = pathlib.Path(tempfile.mkdtemp(prefix=f"lab2-evaluation-{lw.initials()}-", dir=lw.RUNS_DIR))
    lw.say(f"Evaluation evidence and logs: {workdir}")
    eval_summary: dict = {"status": "incomplete", "comparison": comparison, "evidence_directory": str(workdir)}
    lw.record("evaluation", eval_summary)
    lw.save_results("lab2-evaluation")
    for label, agent in agents.items():
        lw.say(f"{label}: answering {len(rows)} rows ...")
        runs = lw.run_rows(agent, rows, workers=1)
        judged = [row for row in rows if row["category"] == "grounded" and not runs[row["id"]].blocked]
        system = getattr(agent.definition, "instructions", "") or ""
        data = workdir / f"{label}.jsonl"
        lines = []
        for row in judged:
            run = runs[row["id"]]
            query_messages, response_messages = lw.eval_messages(run, system)
            lines.append(json.dumps({
                "id": row["id"], "query": row["query"], "response": lw.reply_text(run),
                "context": lw.kb_context(run) or "(no guide passages were retrieved)",
                "query_messages": query_messages, "response_messages": response_messages,
                "tool_calls": lw.eval_tool_calls(run), "tool_definitions": [lw.KB_TOOL_DEFINITION],
                "conditions": row["conditions"]}, ensure_ascii=False))
        data.write_text("\n".join(lines), encoding="utf-8")
        metrics: dict = {}
        if judged:
            log = workdir / f"{label}.log"
            lw.say(f"{label}: evaluating {len(judged)} unblocked grounded rows; logs: "
                   + ("terminal" if args.verbose else str(log)))
            with contextlib.ExitStack() as quiet:
                if not args.verbose:
                    stream = quiet.enter_context(log.open("w", encoding="utf-8"))
                    quiet.enter_context(contextlib.redirect_stdout(stream))
                    quiet.enter_context(contextlib.redirect_stderr(stream))
                result = evaluate(
                    data=str(data), evaluators=evaluators, evaluator_config=evaluator_config,
                    evaluation_name=f"{agent.name}-v{agent.version}-{label}",
                    output_path=str(workdir / f"{label}.out.json"),
                    **({"azure_ai_project": lw.endpoint()} if args.upload else {}),
                )
            metrics = {n: round(result["metrics"][f"{n}.{n}"], 2) for n in evaluators if f"{n}.{n}" in result["metrics"]}
            missing = [n for n in evaluators if n not in metrics or not math.isfinite(metrics[n])]
            if missing:
                lw.say(f"   no usable score from {', '.join(missing)}; inspect the saved evaluator logs/results. "
                       "A missing score is not a pass; do not repeat batches during the workshop.")
            if "task_adherence" in metrics:
                metrics["task_adherence_pass_rate"] = metrics.pop("task_adherence")
            if args.verbose:
                lw.say(f"   all metrics: {json.dumps(result['metrics'], default=str)}")
            if result.get("studio_url"):
                lw.say(f"   Foundry > Evaluations: {result['studio_url']}")
        flags = [row for row in rows if row["category"] == "red_flag"]
        metrics["route_match"] = round(sum(lw.route_matches(runs[x["id"]], x) for x in rows) / len(rows), 2)
        metrics["blocked"] = sum(runs[x["id"]].blocked for x in rows)
        if flags:
            metrics["safe_outcome"] = round(sum(lw.safe_outcome(runs[x["id"]], x) for x in flags) / len(flags), 2)
        eval_summary[label] = {"agent": f"{agent.name} v{agent.version}", "rows": len(rows), "judged": len(judged), **metrics}
        lw.say(f"   {label}: " + ", ".join(f"{k}={v}" for k, v in metrics.items()))
        lw.record("evaluation", eval_summary)
        lw.save_results("lab2-evaluation")

# %% [markdown]
# ## 4. Compare the completed runs and discuss the evidence
#
# Read groundedness for both versions alongside the number of judged rows, safe outcomes and the
# false-positive example from the hands-on ladder. These scores belong to the named versions only.
# Participants read this shared result; they do not wait for or claim a score for their own coach.

# %%
if args.run:
    g1, g2 = eval_summary["v1"].get("groundedness"), eval_summary["v2"].get("groundedness")
    headline = (f"v2 (guarded) vs v1: groundedness {g2} vs {g1}; "
                f"judged rows {eval_summary['v2']['judged']} vs {eval_summary['v1']['judged']}. "
                "Compare guardrail outcomes separately; unscored rows are not passes.")
    eval_summary["headline"] = headline
    scored = all(score is not None and math.isfinite(score) for score in (g1, g2))
    eval_summary["status"] = "completed" if scored else "incomplete"
    lw.record("evaluation", eval_summary)
    lw.expect("evaluation produced groundedness scores for both versions", scored, f"v1={g1}, v2={g2}")
    lw.checkpoint("Lab 2 shared evaluation", {"headline": headline, "versions": comparison})
    lw.say(f"results saved to {lw.save_results('lab2-evaluation')}")
    if args.cleanup:
        lw.say("--cleanup: no agents were created by this script; existing and shared agents were not deleted.")
    if not scored:
        raise SystemExit("Evaluation is incomplete: a groundedness score is missing. Inspect the saved evidence.")
