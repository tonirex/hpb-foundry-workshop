"""Offline tests for Lab 2 going look-only: evaluation gating, the prepared-evaluation reader, the retry delay and
the lab pages.

    python -m unittest discover -s tests -p "test_lab2_gating.py"

Nothing here touches Azure. lab2_govern.py is a top-to-bottom script, so the tests run only its leading cells (the
flags and the helpers, up to the cell that parses the command line) with livewell_common replaced by a stand-in
that fails on any use: a helper that calls Azure while the script loads would fail here.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import random
import re
import sys
import types
import unittest
from types import SimpleNamespace as NS
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "content" / "assets"
LAB2 = ASSETS / "lab2_govern.py"
MATRIX = ROOT / "demos" / "guardrail-matrix.py"
VALIDATOR = ROOT / "scripts" / "validate-builder-rail.py"
ANSWER_KEY = ROOT / "content" / "answer-keys" / "lab-02.json"
LAB_PAGES = [ROOT / "content" / "labs" / "lab-02.md", ROOT / "content" / "labs" / "lab-02-portal.md"]


def code_cells(text: str) -> list[str]:
    """The bodies of a percent-format script's code cells, in order."""
    parts = re.split(r"^(# %%.*)$", text, flags=re.M)  # [preamble, header, body, header, body, ...]
    return [body for header, body in zip(parts[1::2], parts[2::2]) if "[markdown]" not in header]


class _NoAzure(types.ModuleType):
    """Stands in for livewell_common while the offline cells load: any use means a cell calls Azure at load time."""

    def __getattr__(self, name):
        raise AssertionError(f"an offline cell used lw.{name} while the script loaded")


def load_offline_cells() -> dict:
    """Run lab2_govern.py's code cells up to the one that parses the command line; return their namespace."""
    head = []
    for cell in code_cells(LAB2.read_text(encoding="utf-8")):
        if "lab_args(" in cell:
            break
        head.append(cell)
    stub = _NoAzure("common.livewell_common")
    package = types.ModuleType("common")
    package.__path__ = [str(ASSETS / "common")]
    package.livewell_common = stub
    names = ("common", "common.livewell_common")
    blocked = ("azure", "openai")  # None in sys.modules makes `import azure` fail: the SDKs must not load here
    saved = {n: sys.modules.get(n) for n in names + blocked}
    saved_path = sys.path[:]
    sys.modules.update({"common": package, "common.livewell_common": stub, **{n: None for n in blocked}})
    namespace = {"__file__": str(LAB2), "__name__": "lab2_offline"}
    try:
        for cell in head:
            exec(compile(cell, str(LAB2), "exec"), namespace)
    finally:
        sys.path[:] = saved_path
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    return namespace


def load_by_path(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def common_module():
    """The real livewell_common (it only needs PyYAML to load), or None."""
    try:
        sys.path.insert(0, str(ASSETS))
        from common import livewell_common
    except ModuleNotFoundError:
        return None
    finally:
        sys.path.remove(str(ASSETS))
    return livewell_common


lwc = common_module()


class OfflineScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = LAB2.read_text(encoding="utf-8")
        cls.ns = load_offline_cells()

    def parse(self, *argv):
        parser = argparse.ArgumentParser()
        self.ns["_flags"](parser)
        return parser.parse_known_args(list(argv))


class EvalGatingTests(OfflineScript):
    def plan(self, *argv):
        return self.ns["eval_plan"](self.parse(*argv)[0])

    def test_evaluation_is_off_by_default(self):
        plan = self.plan()
        self.assertEqual((plan.run, plan.all_rows, plan.upload), (False, False, False))

    def test_run_eval_turns_it_on(self):
        plan = self.plan("--run-eval")
        self.assertEqual((plan.run, plan.all_rows, plan.upload), (True, False, False))

    def test_eval_all_and_upload_need_run_eval(self):
        for argv in (["--eval-all"], ["--upload"], ["--eval-all", "--upload"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit) as caught:
                self.plan(*argv)
            message = str(caught.exception)
            self.assertIn("--run-eval", message)
            self.assertIn("facilitator", message)
            self.assertTrue(all(flag in message for flag in argv))
            self.assertTrue(message.isascii())

    def test_eval_all_and_upload_pass_with_run_eval(self):
        plan = self.plan("--run-eval", "--eval-all", "--upload")
        self.assertEqual((plan.run, plan.all_rows, plan.upload), (True, True, True))
        self.assertEqual(tuple(self.plan("--run-eval", "--eval-all")), (True, True, False))
        self.assertEqual(tuple(self.plan("--run-eval", "--upload")), (True, False, True))

    def test_no_eval_is_gone(self):
        args, unknown = self.parse("--no-eval")
        self.assertIn("--no-eval", unknown)  # lab_args ignores unknown flags, so an old habit is harmless
        self.assertFalse(hasattr(args, "no_eval"))
        self.assertNotIn("--no-eval", self.source)

    def test_run_eval_help_says_facilitator_only(self):
        parser = argparse.ArgumentParser()
        self.ns["_flags"](parser)
        help_text = " ".join(parser.format_help().split())
        self.assertIn("facilitator only: creates a paid Foundry evaluation run on the shared judge quota; "
                      "participants never pass it", help_text)
        for flag in ("--eval-all", "--upload"):
            self.assertRegex(help_text, rf"{flag}\s+facilitator only, needs --run-eval")

    def test_script_reads_the_plan_not_the_raw_flags(self):
        for stale in ("args.no_eval", "args.eval_all", "args.upload", "args.run_eval"):
            self.assertNotIn(stale, self.source)
        self.assertIn("plan = eval_plan(args)", self.source)
        self.assertIn("if plan.run:", self.source)

    def test_red_flag_round_runs_two_at_a_time(self):
        self.assertEqual(self.ns["RED_FLAG_WORKERS"], 2)
        self.assertIn("max_workers=RED_FLAG_WORKERS", self.source)
        self.assertNotIn("max_workers=7", self.source)

    def test_offline_cells_define_what_the_script_needs(self):
        for name in ("eval_plan", "read_prepared_evaluation", "find_prepared_evaluation", "eval_table_lines",
                     "handled_safely_line", "load_captured_eval", "tally_results", "TABLE_PREVIEW", "CRITERIA"):
            self.assertIn(name, self.ns)
        self.assertEqual(list(self.ns["CRITERIA"]), ["guardrail_blocked", "handled_safely", "self_harm"])


class _Strict:
    """Anything the look-only reader is not meant to call raises, so a create, delete or upload fails the test."""

    def __getattr__(self, name):
        raise AssertionError(f"the look-only reader must not call {name}()")


class FakeEvals(_Strict):
    def __init__(self, evals, runs, items, reject_options=False):
        self.calls, self.evals_, self.runs_, self.items_ = [], evals, runs, items
        self.reject_options = reject_options
        self.runs = FakeRuns(self)

    def list(self, **options):
        self.calls.append("evals.list")
        if options and self.reject_options:
            raise RuntimeError("this API takes no ordering options")
        return list(self.evals_)


class FakeRuns(_Strict):
    def __init__(self, parent):
        self.parent = parent
        self.output_items = FakeItems(parent)

    def list(self, eval_id):
        self.parent.calls.append("runs.list")
        return list(self.parent.runs_)


class FakeItems(_Strict):
    def __init__(self, parent):
        self.parent = parent

    def list(self, run_id, eval_id):
        self.parent.calls.append("output_items.list")
        return [NS(model_dump=lambda row=row: row) for row in self.parent.items_[run_id]]


class Forbidden(Exception):
    status_code = 403


class FakePath:
    """Just enough of a path to read a captured summary without touching the disk."""

    def __init__(self, text=None, error=None):
        self.text, self.error = text, error

    def read_text(self, encoding=None):
        if self.error:
            raise self.error
        return self.text


def rows(blocked: int, handled: int, harmless: int, total: int = 7) -> list[dict]:
    return [{"results": [{"name": "guardrail_blocked", "passed": i < blocked},
                         {"name": "handled_safely", "passed": i < handled},
                         {"name": "self_harm", "passed": i < harmless}]} for i in range(total)]


def sample_client(**options) -> FakeEvals:
    evals = [NS(id="eval-old", name="LiveWell guardrail matrix 2026-10-01 12:27", created_at=100),
             NS(id="eval-new", name="LiveWell guardrail matrix 2026-10-23 14:05", created_at=300),
             NS(id="eval-rt", name="LiveWell red team 20261001-1235", created_at=400)]
    runs = [NS(id="run-0001", name="gpt-5-mini + default", status="completed",
               report_url="https://portal.example.invalid/report"),
            NS(id="run-0002", name="gpt-5-mini + custom", status="completed", report_url=None),
            NS(id="run-0003", name="gpt-4.1-mini + custom", status="in_progress", report_url=None)]
    items = {"run-0001": rows(1, 5, 7), "run-0002": rows(4, 6, 7)}
    return FakeEvals(evals, runs, items, **options)


class PreparedEvaluationTests(OfflineScript):
    def read(self, client):
        return self.ns["read_prepared_evaluation"](NS(evals=client))

    def test_tally_results_counts_passes_and_fails(self):
        tally = self.ns["tally_results"](rows(1, 5, 7))
        self.assertEqual(tally["guardrail_blocked"], {"passed": 1, "failed": 6, "not_scored": 0})
        self.assertEqual(tally["handled_safely"], {"passed": 5, "failed": 2, "not_scored": 0})
        self.assertEqual(tally["self_harm"], {"passed": 7, "failed": 0, "not_scored": 0})
        empty = self.ns["tally_results"]([{"results": None}, {}])
        self.assertEqual(empty["handled_safely"], {"passed": 0, "failed": 0, "not_scored": 2})

    def test_grader_errors_override_the_passed_placeholder(self):
        results = [{"passed": False, "sample": {"error": {"code": "content_filter"}}},
                   {"passed": True, "error": {"code": "grader_error"}},
                   {"passed": None}, {"passed": "false"}, {"passed": 1},
                   {"passed": False}, {"passed": True, "sample": {"error": None}}]
        tally = self.ns["tally_results"]([{"results": [{"name": "handled_safely", **r}]} for r in results])
        self.assertEqual(tally["handled_safely"], {"passed": 1, "failed": 1, "not_scored": 5})

    def test_newest_prepared_ignores_other_evaluations(self):
        client = sample_client()
        picked = self.ns["newest_prepared"](client.evals_)
        self.assertEqual(picked.id, "eval-new")  # the red team is newer but is not the matrix
        self.assertIsNone(self.ns["newest_prepared"]([NS(name="LiveWell red team 1", created_at=1)]))

    def test_reader_only_lists_and_reads(self):
        client = sample_client()
        summary = self.read(client)  # any create, delete, update or upload raises inside FakeEvals
        self.assertLessEqual(set(client.calls), {"evals.list", "runs.list", "output_items.list"})
        self.assertEqual(client.calls.count("output_items.list"), 2)  # only the completed runs
        self.assertEqual(summary["evaluation"], "LiveWell guardrail matrix 2026-10-23 14:05")
        self.assertEqual(summary["rows"], 7)
        first, second, running = summary["runs"]
        self.assertEqual(first["criteria"]["handled_safely"], {"passed": 5, "failed": 2, "not_scored": 0})
        self.assertEqual(second["criteria"]["guardrail_blocked"], {"passed": 4, "failed": 3, "not_scored": 0})
        self.assertEqual(running, {"run": "gpt-4.1-mini + custom", "status": "in_progress"})
        self.assertEqual(summary["report_url"], "https://portal.example.invalid/report")

    def test_reader_falls_back_to_the_plain_list(self):
        summary = self.read(sample_client(reject_options=True))
        self.assertEqual(summary["evaluation"], "LiveWell guardrail matrix 2026-10-23 14:05")

    def test_reader_returns_none_when_nothing_is_published(self):
        client = FakeEvals([NS(id="eval-rt", name="LiveWell red team 1", created_at=1)], [], {})
        self.assertIsNone(self.read(client))
        self.assertEqual(client.calls, ["evals.list"])

    def test_every_failure_is_calm_and_never_raises(self):
        find = self.ns["find_prepared_evaluation"]
        nowhere = FakePath(error=FileNotFoundError())

        def forbidden():
            raise Forbidden("403")

        def odd_shape():
            raise KeyError("results")

        self.assertEqual(find(forbidden, nowhere), ("not_published", None, "Forbidden 403"))
        self.assertEqual(find(odd_shape, nowhere), ("not_published", None, "KeyError"))
        self.assertEqual(find(lambda: None, nowhere), ("not_published", None, ""))
        self.assertEqual(find(lambda: {}, nowhere)[0], "not_published")

    def test_a_published_run_wins_over_the_captured_copy(self):
        captured = FakePath(json.dumps({"evaluation": "saved", "runs": []}))
        status, summary, _ = self.ns["find_prepared_evaluation"](lambda: {"evaluation": "live", "runs": []}, captured)
        self.assertEqual((status, summary["evaluation"]), ("published", "live"))

    def test_the_captured_copy_is_used_when_the_live_read_fails(self):
        captured = FakePath(json.dumps({"schema": 2, "evaluation": "saved", "date": "2026-10-23", "runs": []}))

        def forbidden():
            raise Forbidden("403")

        status, summary, detail = self.ns["find_prepared_evaluation"](forbidden, captured)
        self.assertEqual((status, summary["evaluation"], detail), ("captured", "saved", "Forbidden 403"))

    def test_load_captured_eval_rejects_anything_else(self):
        load = self.ns["load_captured_eval"]
        self.assertEqual(load(FakePath('{"schema": 2, "runs": []}')), {"schema": 2, "runs": []})
        self.assertIsNone(load(FakePath(error=FileNotFoundError())))
        for bad in (FakePath("not json"), FakePath("[]"), FakePath('{"evaluation": "x"}'),
                    FakePath('{"schema": 1, "runs": []}'), FakePath(error=PermissionError())):
            with self.assertRaises(ValueError):
                load(bad)

    def test_legacy_capture_is_reported_not_treated_as_current_scores(self):
        captured = FakePath('{"schema": 1, "runs": []}')
        status, summary, detail = self.ns["find_prepared_evaluation"](lambda: None, captured)
        self.assertEqual((status, summary), ("not_published", None))
        self.assertIn("legacy counts", detail)

    def test_capture_counts_must_cover_rows_and_include_unscored(self):
        summary = self.read(sample_client())
        self.assertEqual(self.ns["load_captured_eval"](FakePath(json.dumps(summary))), summary)
        summary["runs"][0]["criteria"]["handled_safely"].pop("not_scored")
        with self.assertRaisesRegex(ValueError, "invalid handled_safely counts"):
            self.ns["load_captured_eval"](FakePath(json.dumps(summary)))

    @unittest.skipIf(lwc is None, "livewell_common needs PyYAML")
    def test_the_default_captured_path_is_the_one_guardrail_matrix_writes(self):
        self.assertEqual(self.ns["CAPTURED_EVAL"], ROOT / "content" / "data" / "lab2-prepared-eval.json")
        matrix = load_by_path("guardrail_matrix_for_test", MATRIX)
        self.assertEqual(matrix.SAVE_DEFAULT, self.ns["CAPTURED_EVAL"])

    def test_tables_are_ascii_with_one_per_criterion(self):
        summary = self.read(sample_client())
        lines = self.ns["eval_table_lines"](summary)
        self.assertTrue(all(line.isascii() for line in lines))
        text = "\n".join(lines)
        for criterion in self.ns["CRITERIA"]:
            self.assertEqual(text.count(f"   {criterion}:"), 1)
        self.assertEqual(text.count("gpt-5-mini + default"), 3)
        self.assertEqual(text.count("no results yet (in_progress)"), 3)
        self.assertRegex(text, r"gpt-5-mini \+ default\s+5\s+2")

    def test_the_preview_invents_no_numbers(self):
        preview = "\n".join(self.ns["TABLE_PREVIEW"])
        self.assertTrue(preview.isascii())
        self.assertNotRegex(preview, r"\b\d+\b")
        for criterion in self.ns["CRITERIA"]:
            self.assertIn(criterion, preview)

    def test_handled_safely_line(self):
        line = self.ns["handled_safely_line"]
        self.assertEqual(line(self.read(sample_client())),
                         "gpt-5-mini + default: 5 pass / 2 fail / 0 not scored; "
                         "gpt-5-mini + custom: 6 pass / 1 fail / 0 not scored")
        self.assertIn("not available", line(None))
        self.assertIn("no completed runs", line({"runs": [{"run": "x", "status": "queued"}]}))

    def test_the_reader_source_has_no_write_calls(self):
        source = LAB2.read_text(encoding="utf-8")
        start = source.index("def read_prepared_evaluation")
        body = source[start:source.index("def load_captured_eval", start)]
        self.assertNotRegex(body, r"client\.[\w.]*\.(create|delete|update|cancel|upload)\(")
        for write in (".post(", ".put(", ".patch(", "upload("):
            self.assertNotIn(write, body)


def fake_sdk():
    """Minimal stand-ins for the openai and azure.core exception classes retry() imports lazily."""
    class APIStatusError(Exception):
        def __init__(self, status, headers=None, message=""):
            super().__init__(message or f"status {status}")
            self.status_code = status
            self.response = NS(headers=headers or {}, status_code=status)

    class BadRequestError(APIStatusError):
        pass

    class APIConnectionError(Exception):
        pass

    class APITimeoutError(APIConnectionError):
        pass

    openai = types.ModuleType("openai")
    openai.APIStatusError, openai.BadRequestError = APIStatusError, BadRequestError
    openai.APIConnectionError, openai.APITimeoutError = APIConnectionError, APITimeoutError
    exceptions = types.ModuleType("azure.core.exceptions")
    exceptions.HttpResponseError = type("HttpResponseError", (Exception,), {})
    exceptions.ServiceRequestError = type("ServiceRequestError", (Exception,), {})
    exceptions.ServiceResponseError = type("ServiceResponseError", (Exception,), {})
    core, azure = types.ModuleType("azure.core"), types.ModuleType("azure")
    modules = {"openai": openai, "azure": azure, "azure.core": core, "azure.core.exceptions": exceptions}
    return openai, modules


@unittest.skipIf(lwc is None, "livewell_common needs PyYAML")
class RetryDelayTests(unittest.TestCase):
    def test_retry_after_ms_wins_over_retry_after(self):
        headers = {"retry-after-ms": "1500", "retry-after": "30"}
        self.assertEqual(lwc.retry_delay(0, 2.0, headers, rng=lambda: 0.0), 1.5)

    def test_retry_after_is_used_in_seconds_without_the_ms_header(self):
        self.assertEqual(lwc.retry_delay(3, 2.0, {"retry-after": "7"}, rng=lambda: 0.0), 7.0)
        self.assertEqual(lwc.retry_delay(0, 2.0, {"retry-after-ms": "junk", "retry-after": "7"}, rng=lambda: 0.0), 7.0)

    def test_header_names_are_case_insensitive(self):
        self.assertEqual(lwc.retry_delay(0, 2.0, {"Retry-After-Ms": "2500"}, rng=lambda: 0.0), 2.5)

    def test_the_server_hint_is_capped_at_60_seconds(self):
        self.assertEqual(lwc.retry_delay(0, 2.0, {"retry-after": "120"}, rng=lambda: 0.0), 60.0)
        self.assertEqual(lwc.retry_delay(0, 2.0, {"retry-after-ms": "90000"}, rng=lambda: 0.0), 60.0)

    def test_without_headers_the_wait_grows_exponentially(self):
        waits = [lwc.retry_delay(i, 2.0, None, rng=lambda: 0.0) for i in range(6)]
        self.assertEqual(waits, [2.0, 4.0, 8.0, 16.0, 30.0, 30.0])  # the old 2, 4, 8, 16, then the 30 s ceiling

    def test_unusable_hints_fall_back_to_backoff(self):
        for headers in (None, {}, {"retry-after": "soon"}, {"retry-after": "0"}, {"retry-after-ms": "-5"}, object()):
            with self.subTest(headers=headers):
                self.assertEqual(lwc.retry_delay(1, 2.0, headers, rng=lambda: 0.0), 4.0)

    def test_jitter_adds_zero_to_25_percent(self):
        self.assertEqual(lwc.retry_delay(0, 2.0, None, rng=lambda: 0.0), 2.0)
        self.assertAlmostEqual(lwc.retry_delay(0, 2.0, None, rng=lambda: 0.5), 2.25)
        self.assertAlmostEqual(lwc.retry_delay(0, 2.0, None, rng=lambda: 1.0), 2.5)
        self.assertAlmostEqual(lwc.retry_delay(0, 2.0, {"retry-after": "40"}, rng=lambda: 0.5), 45.0)
        rng = random.Random(7).random
        for index in range(5):
            base = min(2.0 * 2 ** index, 30.0)
            for _ in range(200):
                wait = lwc.retry_delay(index, 2.0, None, rng=rng)
                self.assertTrue(base <= wait <= base * 1.25, (index, wait))

    def test_a_room_of_participants_does_not_retry_in_step(self):
        waits = {round(lwc.retry_delay(0, 2.0, {"retry-after": "5"}), 6) for _ in range(30)}
        self.assertGreater(len(waits), 20)

    def test_a_badly_behaved_rng_cannot_shorten_or_stretch_the_wait(self):
        self.assertEqual(lwc.retry_delay(0, 2.0, None, rng=lambda: -3.0), 2.0)
        self.assertEqual(lwc.retry_delay(0, 2.0, None, rng=lambda: 9.0), 2.5)


@unittest.skipIf(lwc is None, "livewell_common needs PyYAML")
class RetryWiringTests(unittest.TestCase):
    """retry() keeps its signature and its rules; only the wait changed."""

    def run_retry(self, errors, **kwargs):
        openai, modules = fake_sdk()
        errors = [e(openai) if callable(e) else e for e in errors]
        attempts = {"n": 0}

        def fn():
            attempts["n"] += 1
            if attempts["n"] <= len(errors):
                raise errors[attempts["n"] - 1]
            return "ok"

        with mock.patch.dict(sys.modules, modules), mock.patch.object(lwc.time, "sleep") as sleep, \
                mock.patch.object(lwc, "say"):
            try:
                result = lwc.retry(fn, what="test", **kwargs)
            except Exception as err:  # noqa: BLE001 - the tests look at what escaped
                result = err
        return result, [call.args[0] for call in sleep.call_args_list], attempts["n"], openai

    def test_the_signature_is_unchanged(self):
        import inspect
        params = inspect.signature(lwc.retry).parameters
        self.assertEqual(list(params), ["fn", "what", "attempts", "retry_timeouts"])
        self.assertEqual((params["what"].default, params["attempts"].default, params["retry_timeouts"].default),
                         ("call", 5, True))

    def test_retry_after_ms_is_honoured_with_jitter(self):
        result, waits, calls, _ = self.run_retry(
            [lambda o: o.APIStatusError(429, {"retry-after-ms": "1500", "retry-after": "30"})])
        self.assertEqual((result, calls, len(waits)), ("ok", 2, 1))
        self.assertTrue(1.5 <= waits[0] <= 1.5 * 1.25, waits)

    def test_a_long_retry_after_is_capped_at_60_before_jitter(self):
        _, waits, _, _ = self.run_retry([lambda o: o.APIStatusError(429, {"retry-after": "300"})])
        self.assertTrue(60.0 <= waits[0] <= 75.0, waits)

    def test_5xx_backs_off_2_4_8_16_with_jitter(self):
        errors = [lambda o: o.APIStatusError(503)] * 4
        result, waits, calls, _ = self.run_retry(errors)
        self.assertEqual((result, calls), ("ok", 5))
        for wait, base in zip(waits, (2.0, 4.0, 8.0, 16.0)):
            self.assertTrue(base <= wait <= base * 1.25, (wait, base))

    def test_gives_up_after_the_last_attempt(self):
        errors = [lambda o: o.APIStatusError(429)] * 3
        result, waits, calls, openai = self.run_retry(errors, attempts=3)
        self.assertIsInstance(result, openai.APIStatusError)
        self.assertEqual((calls, len(waits)), (3, 2))

    def test_a_hosted_session_start_waits_at_least_15_seconds(self):
        error = lambda o: o.APIStatusError(424, message="424 session_not_ready")  # noqa: E731
        _, waits, _, _ = self.run_retry([error, error])
        self.assertEqual(len(waits), 2)
        for wait in waits:
            self.assertTrue(15.0 <= wait <= 15.0 * 1.25, wait)

    def test_a_retry_after_longer_than_the_floor_still_wins_on_424(self):
        error = lambda o: o.APIStatusError(424, {"retry-after": "40"}, "424 session_not_ready")  # noqa: E731
        _, waits, _, _ = self.run_retry([error])
        self.assertTrue(40.0 <= waits[0] <= 50.0, waits)

    def test_non_throttle_errors_raise_at_once(self):
        for error in (lambda o: o.BadRequestError(400, message="content_filter"),
                      lambda o: o.APIStatusError(404),
                      lambda o: o.APIStatusError(424, message="some other 424")):
            result, waits, calls, openai = self.run_retry([error])
            self.assertIsInstance(result, openai.APIStatusError)
            self.assertEqual((calls, waits), (1, []))

    def test_a_timeout_raises_at_once_when_retrying_it_is_unsafe(self):
        result, waits, calls, openai = self.run_retry([lambda o: o.APITimeoutError("slow")], retry_timeouts=False)
        self.assertIsInstance(result, openai.APITimeoutError)
        self.assertEqual((calls, waits), (1, []))
        result, waits, calls, _ = self.run_retry([lambda o: o.APITimeoutError("slow")])
        self.assertEqual((result, calls, len(waits)), ("ok", 2, 1))


class ValidatorAndMatrixTests(unittest.TestCase):
    def test_validator_lab2_signals_match_what_the_script_records(self):
        validator = load_by_path("validate_builder_rail_for_test", VALIDATOR)
        script = LAB2.read_text(encoding="utf-8")
        labels = [label for lab, _, needed, _ in validator.SIGNALS if lab == "lab2" for label in needed]
        self.assertGreaterEqual(len(labels), 6)
        self.assertIn('f"v2 {pid}: blocked or safely refused"', script)
        self.assertEqual({label for label in labels if label.startswith("v2 ")},
                         {f"v2 {pid}: blocked or safely refused" for pid in validator.LAB2_RED_FLAGS})
        for label in labels:
            if not label.startswith("v2 "):
                self.assertIn(f'"{label}"', script)

    def test_validator_never_runs_the_paid_evaluation(self):
        validator = load_by_path("validate_builder_rail_for_test", VALIDATOR)
        self.assertEqual(validator.LABS["2"][2], [])
        self.assertNotIn("--run-eval", VALIDATOR.read_text(encoding="utf-8").split("def run_lab")[1].split("def signal_rows")[0])

    def test_guardrail_matrix_is_marked_paid_facilitator_only_and_can_save(self):
        source = MATRIX.read_text(encoding="utf-8")
        doc = " ".join(source.split('"""')[1].split())
        for phrase in ("PAID", "facilitator", "separate approval", "participants never run it", "--save"):
            self.assertIn(phrase, doc)
        self.assertIn('ap.add_argument("--save"', source)
        self.assertIn("--save needs --cloud", source)
        self.assertIn("content" + "/data/lab2-prepared-eval.json", doc)

    def test_guardrail_matrix_summary_has_no_ids_or_endpoints(self):
        source = MATRIX.read_text(encoding="utf-8")
        start = source.index("    return {\"schema\": SUMMARY_SCHEMA")
        record = source[start:source.index("\n", start)]
        self.assertNotIn("report", record)
        self.assertNotIn(".id", record)
        self.assertNotIn("endpoint", record)


class LabPageTests(unittest.TestCase):
    BANNED = ("--no-eval", "Create evaluation", "groundedness score pasted", "Evaluations → Create",
              "Evaluations -> Create", "Existing dataset", "Field mapping", "valuation wizard", "Red team (Preview tab)",
              "Evaluations → Red team", "red-teaming wizard", "red teaming wizard", "lite scan")
    ALLOWED_FLAGS = {"--verbose", "--cleanup", "--run-eval", "--eval-all", "--upload", "--cloud", "--save"}

    @classmethod
    def setUpClass(cls):
        cls.pages = {path.name: path.read_text(encoding="utf-8") for path in LAB_PAGES}

    def test_no_participant_evaluation_or_red_team_steps(self):
        for name, text in self.pages.items():
            for banned in self.BANNED:
                self.assertNotIn(banned, text, f"{name} still says {banned!r}")

    def test_every_red_team_mention_names_the_facilitator(self):
        for name, text in self.pages.items():
            for line in text.splitlines():
                mentions = re.sub(r"red-team note", "", line)  # the repo note on the flyer file is not a scan
                if re.search(r"red[- ]?team", mentions, re.I):
                    self.assertRegex(line, r"(?i)facilitator", f"{name}: {line[:90]}")

    def test_facilitator_only_flags_are_labelled_as_such(self):
        for name, text in self.pages.items():
            for line in text.splitlines():
                if re.search(r"--(run-eval|eval-all|upload|cloud)\b", line):
                    self.assertRegex(line, r"(?i)facilitator", f"{name}: {line[:90]}")

    def test_pages_only_mention_flags_the_scripts_have(self):
        for name, text in self.pages.items():
            flags = set(re.findall(r"(?<![\w-])--[a-z][a-z-]*", text))
            self.assertLessEqual(flags, self.ALLOWED_FLAGS, f"{name}: {sorted(flags - self.ALLOWED_FLAGS)}")
        script = LAB2.read_text(encoding="utf-8")
        for flag in ("--run-eval", "--eval-all", "--upload"):
            self.assertIn(f'"{flag}"', script)
        self.assertIn('"--save"', MATRIX.read_text(encoding="utf-8"))

    def test_both_pages_send_participants_to_the_prepared_evaluation(self):
        for name, text in self.pages.items():
            self.assertIn("LiveWell guardrail matrix", text, name)
            self.assertRegex(text, r"(?i)look(ing)? only|look, don't run", name)
            self.assertIn("tell the facilitator", text.lower(), name)
            self.assertIn("screen-share the captured results", text, name)

    def test_troubleshooting_row_for_a_missing_evaluation(self):
        text = self.pages["lab-02.md"]
        self.assertIn("I cannot see the prepared evaluation", text)
        troubleshooting = text.split("## Troubleshooting")[1].split("## Where next")[0]
        self.assertRegex(troubleshooting, r"I cannot see the prepared evaluation[^\n]*\| Tell the facilitator\.")

    def test_checkpoint_is_the_new_look_only_checkpoint(self):
        checkpoint = self.pages["lab-02.md"].split("## Checkpoint")[1].split("## Troubleshooting")[0]
        self.assertIn("lab2_injected_flyer", checkpoint)
        self.assertIn("Prompt Shields", checkpoint)
        self.assertIn("ignores the hidden instruction", checkpoint)
        self.assertIn("handled_safely", checkpoint)
        self.assertIn("prepared evaluation", checkpoint)
        self.assertNotRegex(checkpoint, r"(?i)groundedness")
        self.assertNotRegex(checkpoint, r"\b\d+(\.\d+)? (pass|of 7)\b")  # the page quotes no counts

    def test_code_details_are_optional_and_link_to_current_entrypoints(self):
        text = self.pages["lab-02.md"]
        self.assertIn("<summary><strong>Optional: code", text)
        for path in ("../assets/lab2_govern.py", "../assets/common/evaluation_results.py"):
            self.assertIn(f"]({path})", text)
        self.assertIn("not scored", text)
        self.assertIn("same model", text.lower())

    def test_answer_key_is_look_only(self):
        key = json.loads(ANSWER_KEY.read_text(encoding="utf-8"))
        checkpoints = key["checkpoints"]
        self.assertTrue(all(c.get("prompt_id") or c.get("checkpoint_id") for c in checkpoints))
        self.assertNotIn("groundedness score", json.dumps(checkpoints))
        self.assertNotIn("lab2_groundedness_score", json.dumps(key))
        metric = [c for c in checkpoints if c.get("checkpoint_id") == "lab2_prepared_eval_handled_safely"]
        self.assertEqual(len(metric), 1)
        self.assertIsNone(metric[0]["prompt_id"])
        self.assertEqual(metric[0]["validation_type"], "C_paste_metric")
        self.assertIn("Past measurement, not a guarantee", key["prepared_evaluation"]["historical_reference"])


if __name__ == "__main__":
    unittest.main()
