"""Offline execution tests: no participant path may start a batch evaluation."""
from __future__ import annotations

import argparse
import builtins
import contextlib
import io
import json
import re
import runpy
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "content" / "assets"
HANDS_ON = ASSETS / "lab2_govern.py"
EVALUATION = ASSETS / "lab2_evaluate.py"
DEFAULT_ROWS = ["lw-02", "lw-09", "lw-10", "lw-26", "lw-03", "lw-29"]
METRICS = ("groundedness", "relevance", "task_adherence", "intent_resolution", "tool_call_accuracy",
           "advice_matches_conditions")


class HttpResponseError(Exception):
    status_code = 403
    message = "policy attachment denied"


class ResourceNotFoundError(HttpResponseError):
    pass


def version(name="livewell-test-coach", number="1", policy="Microsoft.DefaultV2"):
    return types.SimpleNamespace(name=name, version=number, definition=types.SimpleNamespace(
        instructions="Use the guide passages.", rai_config=types.SimpleNamespace(rai_policy_name=policy)))


def run(blocked=False):
    return types.SimpleNamespace(
        blocked=blocked, block_reason="custom_blocklists" if blocked else "", annotations=[],
        citations=["lg-05"], text='{"route": "self_care", "answer": "Use the guide."}',
        json=lambda: {"route": "self_care", "answer": "Use the guide."},
    )


@contextlib.contextmanager
def no_cloud_imports():
    original = builtins.__import__

    def checked(name, *args, **kwargs):
        if name == "common" or name.startswith("azure") or name == "advice_matches_conditions":
            raise AssertionError(f"read-only walkthrough imported cloud code: {name}")
        return original(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=checked):
        yield


class WalkthroughTests(unittest.TestCase):
    def test_default_and_verbose_execution_need_no_cloud_dependencies(self):
        for flags in ([], ["--verbose"]):
            with self.subTest(flags=flags), no_cloud_imports(), patch.object(sys, "argv", [str(EVALUATION), *flags]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    namespace = runpy.run_path(str(EVALUATION), run_name="__main__")
                self.assertFalse(namespace["args"].run)
                self.assertNotIn("lw", namespace)
                self.assertIn("CODE WALKTHROUGH ONLY", output.getvalue())

    def test_import_never_honours_the_importers_run_flag(self):
        with no_cloud_imports(), patch.object(sys, "argv", ["caller", "--run", "--eval-all"]):
            with contextlib.redirect_stdout(io.StringIO()):
                namespace = runpy.run_path(str(EVALUATION), run_name="evaluation_reference")
        self.assertFalse(namespace["args"].run)
        self.assertNotIn("lw", namespace)

    def test_notebook_run_all_ignores_kernel_arguments_even_without_file(self):
        namespace = {"__name__": "__main__"}
        cells = re.split(r"(?m)^# %%[^\n]*\n", EVALUATION.read_text(encoding="utf-8"))
        with no_cloud_imports(), patch.dict(sys.modules, {"ipykernel": types.ModuleType("ipykernel")}):
            with patch.object(sys, "argv", ["kernel", "--run", "--eval-all", "-f", "kernel.json"]):
                with contextlib.redirect_stdout(io.StringIO()):
                    for cell in cells:
                        exec(compile(cell, str(EVALUATION), "exec"), namespace)
        self.assertFalse(namespace["args"].run)
        self.assertNotIn("lw", namespace)

    def test_other_flags_cannot_enable_evaluation_or_abbreviate_run(self):
        for flags in (["--eval-all"], ["--upload"], ["--cleanup"], ["--r"], ["--run-eval"]):
            with self.subTest(flags=flags), no_cloud_imports(), patch.object(sys, "argv", [str(EVALUATION), *flags]):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    runpy.run_path(str(EVALUATION), run_name="__main__")
                self.assertEqual(error.exception.code, 2)


class Lab2ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runs_dir = Path(self.temp.name)
        self.rows = [json.loads(line) for line in (ROOT / "content" / "eval" / "livewell-eval.jsonl")
                     .read_text(encoding="utf-8").splitlines() if line.strip()]
        self.records = {}
        self.v1, self.v2 = version(), version(number="2", policy="livewell-guardrails")
        self.guarded = version("livewell-demo-guarded", policy="livewell-guardrails")
        self.lw = Mock()
        self.lw.NAMES = {"rai_policy": "livewell-guardrails"}
        self.lw.NAMING = {"demo_agents": {"guarded": "livewell-demo-guarded"}}
        self.lw.DEFAULT_RAI_POLICY = "Microsoft.DefaultV2"
        self.lw.RUNS_DIR = self.runs_dir
        self.lw.KB_TOOL_DEFINITION = {"name": "knowledge_base_retrieve"}
        self.lw.re = re
        self.lw.initials.return_value = "test"
        self.lw.endpoint.return_value = "selected-project"
        self.lw.agent_name.side_effect = lambda role: f"livewell-test-{role}"
        self.lw.versions.return_value = [self.v1]
        self.lw.create_agent.return_value = self.v2
        self.lw.project.return_value.agents.get.return_value.versions.latest = self.guarded
        self.lw.project.return_value.agents.get_version.side_effect = self.get_version
        self.lw.rai_policy_of.side_effect = lambda agent: agent.definition.rai_config.rai_policy_name
        self.lw.agent_reference.side_effect = self.reference
        self.lw.load_eval_rows.side_effect = self.load_rows
        self.lw.lab_args.side_effect = self.lab_args
        self.lw.ask.side_effect = lambda *args, **kwargs: run()
        self.lw.run_rows.side_effect = lambda agent, rows, **kwargs: {
            row["id"]: run(blocked=row["category"] == "red_flag") for row in rows
        }
        self.lw.safe_outcome.return_value = True
        self.lw.route_matches.return_value = True
        self.lw.eval_messages.return_value = ([{"role": "user", "content": "question"}],
                                               [{"role": "assistant", "content": "answer"}])
        self.lw.reply_text.return_value = "Use the retrieved guide."
        self.lw.kb_context.return_value = "Retrieved guide passage."
        self.lw.eval_tool_calls.return_value = []
        self.lw.record.side_effect = lambda key, value: self.records.update({key: value})
        self.lw.expect.side_effect = lambda label, ok, detail="": self.records.setdefault("checks", {}).update({label: ok})
        self.lw.save_results.side_effect = self.save_results
        self.lw.say.side_effect = lambda *parts: print(" ".join(str(part) for part in parts))
        common = types.ModuleType("common")
        common.livewell_common = self.lw
        exceptions = types.ModuleType("azure.core.exceptions")
        exceptions.HttpResponseError = HttpResponseError
        exceptions.ResourceNotFoundError = ResourceNotFoundError
        sdk = types.ModuleType("azure.ai.evaluation")
        for name in ("Groundedness", "IntentResolution", "Relevance", "TaskAdherence", "ToolCallAccuracy"):
            setattr(sdk, f"{name}Evaluator", Mock())
        self.evaluate = Mock(return_value={"metrics": {f"{name}.{name}": 4.5 for name in METRICS}})
        sdk.evaluate = self.evaluate
        custom = types.ModuleType("advice_matches_conditions")
        custom.AdviceMatchesConditionsEvaluator = Mock()
        self.modules = {"common": common, "azure.core.exceptions": exceptions,
                        "azure.ai.evaluation": sdk, "advice_matches_conditions": custom}

    @staticmethod
    def reference(agent):
        return {"name": agent.name, "version": agent.version, "type": "agent_reference"}

    def get_version(self, *, agent_name, agent_version):
        for agent in (self.v1, self.v2, self.guarded):
            if (agent.name, agent.version) == (agent_name, agent_version):
                return agent
        raise ResourceNotFoundError("missing version")

    def load_rows(self, *, ids=None):
        if ids is None:
            return self.rows
        return [next(row for row in self.rows if row["id"] == rid) for rid in ids]

    @staticmethod
    def lab_args(description, extra):
        parser = argparse.ArgumentParser(description=description)
        parser.add_argument("--verbose", action="store_true")
        parser.add_argument("--cleanup", action="store_true")
        extra(parser)
        return parser.parse_args()

    def save_results(self, lab):
        path = self.runs_dir / f"{lab}-test.json"
        path.write_text(json.dumps({"lab": lab, "initials": "test", "results": self.records}, default=str),
                        encoding="utf-8")
        return path

    def prepare_comparison(self, *, guarded=None):
        self.records["comparison"] = {
            "project_endpoint": "selected-project", "v1": self.reference(self.v1),
            "v2": self.reference(guarded or self.v2), "cleanup_requested": False,
        }
        return self.save_results("lab2")

    def execute(self, script, flags=()):
        with patch.dict(sys.modules, self.modules), patch.object(sys, "argv", [str(script), *flags]):
            with patch.object(sys, "path", sys.path.copy()), contextlib.redirect_stdout(io.StringIO()):
                return runpy.run_path(str(script), run_name="__main__")

    def test_hands_on_runs_only_ladder_and_saves_exact_versions_without_scores(self):
        self.execute(HANDS_ON)
        self.assertEqual(self.lw.ask.call_count, 14)
        self.lw.run_rows.assert_not_called()
        self.lw.judge_model_config.assert_not_called()
        self.evaluate.assert_not_called()
        self.assertEqual(self.records["evaluation"]["status"], "not_run")
        self.assertEqual(self.records["comparison"]["v1"], self.reference(self.v1))
        self.assertEqual(self.records["comparison"]["v2"], self.reference(self.v2))
        checkpoint = self.lw.checkpoint.call_args.args[1]
        self.assertIn("NOT RUN", checkpoint["batch evaluation"])
        self.assertIn("not measured", checkpoint["groundedness"])
        self.assertTrue((self.runs_dir / "lab2-test.json").is_file())

    def test_legacy_eval_flags_stop_before_any_hands_on_calls(self):
        for flag in ("--eval-all", "--upload"):
            with self.subTest(flag=flag), self.assertRaisesRegex(SystemExit, "moved to lab2_evaluate.py"):
                self.execute(HANDS_ON, [flag])
        self.lw.kb_tool.assert_not_called()
        self.lw.ask.assert_not_called()
        self.evaluate.assert_not_called()

    def test_legacy_no_eval_and_cleanup_still_work(self):
        self.execute(HANDS_ON, ["--no-eval", "--cleanup"])
        self.assertEqual(self.records["evaluation"]["status"], "not_run")
        self.assertTrue(self.records["comparison"]["cleanup_requested"])
        self.lw.cleanup.assert_called_once_with()
        self.evaluate.assert_not_called()

    def test_fallback_comparator_is_pinned_and_reused_without_modification(self):
        self.lw.create_agent.side_effect = HttpResponseError()
        self.execute(HANDS_ON)
        self.assertEqual(self.records["comparison"]["v2"], self.reference(self.guarded))
        self.lw.create_agent.reset_mock()
        self.lw.ask.reset_mock()
        self.execute(EVALUATION, ["--run"])
        self.lw.project.return_value.agents.get_version.assert_any_call(
            agent_name="livewell-demo-guarded", agent_version="1")
        self.lw.create_agent.assert_not_called()
        self.lw.ask.assert_not_called()
        self.lw.cleanup.assert_not_called()

    def test_opt_in_reuses_versions_and_keeps_hands_on_results_separate(self):
        source = self.prepare_comparison()
        before = source.read_bytes()
        self.execute(EVALUATION, ["--run", "--cleanup"])
        self.assertEqual(self.lw.project.return_value.agents.get_version.call_args_list, [
            call(agent_name="livewell-test-coach", agent_version="1"),
            call(agent_name="livewell-test-coach", agent_version="2"),
        ])
        self.assertEqual(self.lw.run_rows.call_count, 2)
        for request in self.lw.run_rows.call_args_list:
            self.assertEqual([row["id"] for row in request.args[1]], DEFAULT_ROWS)
            self.assertEqual(request.kwargs, {"workers": 1})
        self.assertEqual(self.evaluate.call_count, 2)
        for request in self.evaluate.call_args_list:
            self.assertNotIn("azure_ai_project", request.kwargs)
            rows = [json.loads(line) for line in Path(request.kwargs["data"]).read_text(encoding="utf-8").splitlines()]
            self.assertTrue(rows)
            self.assertTrue(all(next(row for row in self.rows if row["id"] == scored["id"])["category"] == "grounded"
                                for scored in rows))
            self.assertTrue(all(row["context"] == "Retrieved guide passage." for row in rows))
        self.lw.ask.assert_not_called()
        self.lw.create_agent.assert_not_called()
        self.lw.cleanup.assert_not_called()
        self.assertEqual(source.read_bytes(), before)
        result = json.loads((self.runs_dir / "lab2-evaluation-test.json").read_text(encoding="utf-8"))
        self.assertEqual(result["results"]["evaluation"]["status"], "completed")

    def test_full_dataset_and_upload_require_explicit_opt_in(self):
        self.prepare_comparison()
        self.execute(EVALUATION, ["--run", "--eval-all", "--upload", "--verbose"])
        self.assertEqual(len(self.rows), 30)
        for request in self.lw.run_rows.call_args_list:
            self.assertEqual(request.args[1], self.rows)
        self.assertEqual(self.evaluate.call_count, 2)
        for request in self.evaluate.call_args_list:
            self.assertEqual(request.kwargs["azure_ai_project"], "selected-project")
        self.assertEqual(self.records["evaluation"]["v1"]["rows"], 30)
        self.assertEqual(self.records["evaluation"]["v2"]["rows"], 30)

    def test_missing_or_invalid_saved_run_stops_before_cloud_access(self):
        path = self.runs_dir / "lab2-test.json"
        for text in (None, "bad json", "[]", '{"lab":"lab1","initials":"test"}',
                     '{"lab":"lab2","initials":"test","results":{}}'):
            with self.subTest(text=text):
                if text is not None:
                    path.write_text(text, encoding="utf-8")
                with self.assertRaises(SystemExit):
                    self.execute(EVALUATION, ["--run"])
        self.lw.project.assert_not_called()
        self.evaluate.assert_not_called()

    def test_wrong_project_cleanup_and_unpinned_versions_stop_before_cloud_access(self):
        for mutate in (
            lambda comparison: comparison.update(project_endpoint="different-project"),
            lambda comparison: comparison.update(cleanup_requested=True),
            lambda comparison: comparison["v2"].pop("version"),
            lambda comparison: comparison["v1"].update(name="livewell-someone-else-coach"),
        ):
            with self.subTest(mutate=mutate):
                self.prepare_comparison()
                mutate(self.records["comparison"])
                self.save_results("lab2")
                with self.assertRaises(SystemExit):
                    self.execute(EVALUATION, ["--run"])
        self.lw.project.assert_not_called()
        self.evaluate.assert_not_called()

    def test_deleted_version_or_wrong_guardrail_never_starts_evaluation(self):
        self.prepare_comparison()
        self.lw.project.return_value.agents.get_version.side_effect = ResourceNotFoundError("gone")
        with self.assertRaisesRegex(SystemExit, "no longer exists"):
            self.execute(EVALUATION, ["--run"])
        self.lw.project.return_value.agents.get_version.side_effect = self.get_version
        self.v2.definition.rai_config.rai_policy_name = "Microsoft.DefaultV2"
        with self.assertRaisesRegex(SystemExit, "expected default/custom guardrail"):
            self.execute(EVALUATION, ["--run"])
        self.lw.run_rows.assert_not_called()
        self.evaluate.assert_not_called()

    def test_upload_error_is_surfaced_without_repeating_paid_evaluation(self):
        self.prepare_comparison()
        self.evaluate.side_effect = RuntimeError("storage upload failed")
        with self.assertRaisesRegex(RuntimeError, "storage upload failed"):
            self.execute(EVALUATION, ["--run", "--upload"])
        self.evaluate.assert_called_once()
        self.lw.run_rows.assert_called_once()
        self.assertEqual(self.records["evaluation"]["status"], "incomplete")
        evidence = Path(self.records["evaluation"]["evidence_directory"])
        self.assertTrue((evidence / "v1.jsonl").is_file())
        self.assertTrue((evidence / "v1.log").is_file())
        self.assertNotIn("v2", self.records["evaluation"])

    def test_missing_or_nonfinite_groundedness_is_not_a_completed_comparison(self):
        for metrics in ({}, {"groundedness.groundedness": float("nan")}):
            with self.subTest(metrics=metrics):
                self.prepare_comparison()
                self.evaluate.return_value = {"metrics": metrics}
                with self.assertRaisesRegex(SystemExit, "Evaluation is incomplete"):
                    self.execute(EVALUATION, ["--run"])
                self.assertEqual(self.records["evaluation"]["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
