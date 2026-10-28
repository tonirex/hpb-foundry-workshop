"""Offline safeguards for publishing and resuming the facilitator's Lab 2 evidence."""
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("matrix_evidence_test", ROOT / "demos" / "guardrail-matrix.py")
matrix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matrix)


def complete_summary():
    return {"schema": 2, "evaluation": "LiveWell guardrail matrix example", "date": "2026-10-26", "rows": 7,
            "runs": [{"run": matrix.label(model, guardrail), "status": "completed", "rows": 7,
                      "criteria": {name: {"passed": 4, "failed": 2, "not_scored": 1}
                                   for name in ("guardrail_blocked", "handled_safely", "self_harm")}}
                     for _, model, guardrail in matrix.CONFIGS]}


class EvidenceTests(unittest.TestCase):
    def test_completed_matrix_can_be_saved_without_erasing_unscored_counts(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(matrix.lw, "say"):
            path = Path(tmp) / "summary.json"
            matrix.save_summary(complete_summary(), path)
            self.assertIn('"not_scored": 1', path.read_text(encoding="utf-8"))

    def test_incomplete_matrices_never_overwrite_the_participant_capture(self):
        changes = [
            lambda s: s["runs"].pop(),
            lambda s: s["runs"].append(copy.deepcopy(s["runs"][0])),
            lambda s: s["runs"][0].update(status="running"),
            lambda s: s["runs"][0].update(rows=6),
            lambda s: s["runs"][0]["criteria"]["handled_safely"].update(passed=0, failed=0, not_scored=7),
            lambda s: s["runs"][0]["criteria"]["self_harm"].update(passed=-1),
        ]
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "summary.json"
                path.write_text("existing evidence", encoding="utf-8")
                summary = complete_summary()
                change(summary)
                with self.assertRaises(ValueError):
                    matrix.save_summary(summary, path)
                self.assertEqual(path.read_text(encoding="utf-8"), "existing evidence")

    def test_collection_only_reads_and_persists_rows(self):
        evaluation = NS(id="eval-example", name="LiveWell guardrail matrix example", created_at=1793016000,
                        model_dump=lambda **_: {"id": "eval-example"})
        run = NS(id="run-example", name="gpt-5-mini + default", status="completed",
                 model_dump=lambda **_: {"id": "run-example", "status": "completed"})
        items = [NS(model_dump=lambda **_: {"datasource_item": {"id": "lab2_benign_control"},
                   "results": [{"name": name, "passed": True}
                               for name in ("guardrail_blocked", "handled_safely", "self_harm")]})]
        runs = NS(list=mock.Mock(return_value=[run]), retrieve=mock.Mock(return_value=run),
                  output_items=NS(list=mock.Mock(return_value=items)))
        client = NS(evals=NS(runs=runs))
        with mock.patch.object(matrix, "persist_evidence") as persist, mock.patch("builtins.print"):
            summary = matrix.collect_evaluation(client, evaluation)
        self.assertEqual(summary["runs"][0]["rows"], 1)
        self.assertEqual(persist.call_args.args[2]["output_items"][0]["datasource_item"]["id"],
                         "lab2_benign_control")
        runs.list.assert_called_once_with(eval_id="eval-example")
        runs.output_items.list.assert_called_once_with(run_id="run-example", eval_id="eval-example")

    def test_saved_ids_recover_an_eventually_consistent_empty_list(self):
        evaluation = NS(id="eval-example", name="LiveWell guardrail matrix example", created_at=1793016000,
                        model_dump=lambda **_: {"id": "eval-example"})
        run = NS(id="evalrun_example", name="gpt-5-mini + default", status="completed",
                 model_dump=lambda **_: {"id": "evalrun_example", "status": "completed"})
        runs = NS(list=mock.Mock(return_value=[]), retrieve=mock.Mock(return_value=run),
                  output_items=NS(list=mock.Mock(return_value=[])))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(matrix, "EVIDENCE", Path(tmp)), \
                mock.patch.dict(matrix.os.environ, {"AZURE_ENV_NAME": "test"}), mock.patch("builtins.print"):
            matrix.persist_evidence(evaluation.id, "evalrun_example.json", {"run": {"id": "evalrun_example"}})
            summary = matrix.collect_evaluation(NS(evals=NS(runs=runs)), evaluation)
        self.assertEqual(len(summary["runs"]), 1)
        self.assertEqual(summary["runs"][0]["status"], "completed")
        runs.output_items.list.assert_called_once_with(run_id="evalrun_example", eval_id="eval-example")


if __name__ == "__main__":
    unittest.main()
