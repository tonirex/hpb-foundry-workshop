"""Offline checks for participant approval, intake isolation and progressive disclosure."""
from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace as NS
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "content" / "assets"))
from common import livewell_common as lw


def visible_text(text: str) -> str:
    depth, visible = 0, []
    for line in text.splitlines():
        if re.match(r"\s*<details\b", line):
            depth += 1
        elif re.match(r"\s*</details>", line):
            depth -= 1
            if depth < 0:
                raise AssertionError("unmatched details closing tag")
        elif not depth:
            visible.append(line)
    if depth:
        raise AssertionError("unclosed details section")
    return "\n".join(visible)


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.call = NS(kind="mcp_approval_request", name="register_interest", server="activities",
                       arguments='{"activity_id":"ACT001"}', approved=None)

    def decide(self, *, tty=False, stdin_missing=False, flag="", answer=""):
        stdin = None if stdin_missing else NS(isatty=lambda: tty)
        with mock.patch.dict(lw.os.environ, {"LIVEWELL_AUTO_APPROVE": flag}), \
                mock.patch.object(lw.sys, "stdin", stdin), \
                mock.patch("builtins.input", return_value=answer) as prompt, \
                mock.patch.object(lw, "say") as say:
            decision = lw.ask_human(self.call)
        return decision, prompt, say

    def test_only_an_explicit_yes_approves_in_a_terminal(self):
        for answer in ("y", "YES", " yes "):
            self.assertTrue(self.decide(tty=True, answer=answer)[0])
        for answer in ("", "n", "maybe"):
            self.assertFalse(self.decide(tty=True, answer=answer)[0])

    def test_unattended_and_notebook_execution_deny_with_an_explanation(self):
        for missing in (False, True):
            decision, prompt, say = self.decide(stdin_missing=missing)
            self.assertFalse(decision)
            prompt.assert_not_called()
            self.assertIn("DENIED", say.call_args.args[0])

    def test_only_exact_rehearsal_setting_enables_unattended_approval(self):
        for flag in ("", "0", "false", "true", "yes"):
            self.assertFalse(self.decide(flag=flag)[0])
        decision, prompt, say = self.decide(flag="1")
        self.assertTrue(decision)
        prompt.assert_not_called()
        self.assertIn("AUTOMATED REHEARSAL", say.call_args.args[0])

    def test_input_failure_denies(self):
        for error in (EOFError(), OSError("closed input")):
            with mock.patch.dict(lw.os.environ, {"LIVEWELL_AUTO_APPROVE": ""}), \
                    mock.patch.object(lw.sys, "stdin", NS(isatty=lambda: True)), \
                    mock.patch("builtins.input", side_effect=error), mock.patch.object(lw, "say"):
                self.assertFalse(lw.ask_human(self.call))

    def run_approval_loop(self, **kwargs):
        client = NS(responses=NS(create=mock.Mock(side_effect=[
            NS(id="response-1", status="completed", output=[NS(id="approval-1", type="mcp_approval_request")],
               output_text=""),
            NS(id="response-2", status="completed", output=[], output_text="Decision recorded"),
        ])))
        with mock.patch.object(lw, "agent_reference", return_value={"name": "test-agent"}), \
                mock.patch.object(lw, "is_hosted", return_value=False), \
                mock.patch.object(lw, "openai_client", return_value=client), \
                mock.patch.object(lw, "retry", side_effect=lambda fn, **_: fn()), \
                mock.patch.object(lw, "_item_to_call", return_value=self.call), \
                mock.patch.object(lw, "ask_human", return_value=False) as ask, \
                mock.patch.object(lw, "say"):
            result = lw.ask("test-agent", "Register interest", consent=False, **kwargs)
        return result, client.responses.create, ask

    def test_unspecified_approval_uses_the_human_callback_and_sends_denial(self):
        self.assertIsNone(inspect.signature(lw.ask).parameters["approve"].default)
        result, create, ask = self.run_approval_loop()
        ask.assert_called_once_with(self.call)
        self.assertFalse(create.call_args.kwargs["input"][0]["approve"])
        self.assertFalse(result.approvals[0].approved)

    def test_explicit_callback_decisions_are_preserved(self):
        for decision in (False, True):
            _, create, ask = self.run_approval_loop(approve=lambda _: decision)
            ask.assert_not_called()
            self.assertIs(create.call_args.kwargs["input"][0]["approve"], decision)

    def test_truthy_non_boolean_callback_cannot_approve(self):
        with self.assertRaisesRegex(TypeError, "must return True or False"):
            self.run_approval_loop(approve=lambda _: "yes")


class ParticipantContentTests(unittest.TestCase):
    def test_required_reading_is_bounded_and_details_default_closed(self):
        labs = ROOT / "content" / "labs"
        for name in ("lab-00", "lab-01", "lab-02", "lab-03", "lab-04", "fabric-step"):
            with self.subTest(lab=name):
                text = (labs / f"{name}.md").read_text(encoding="utf-8")
                self.assertLessEqual(len(visible_text(text).split()), 1100)
                self.assertNotRegex(text, r"<details\b[^>]*\bopen\b")

    def test_retained_intake_schema_is_not_a_participant_exercise(self):
        spec = importlib.util.spec_from_file_location("schemas_for_learning_test", ROOT / "scripts" / "gen-schemas.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        path = module.SCHEMAS_DIR / "lab1-intake.schema.json"
        actual = json.loads(module.FILES[path]())
        self.assertEqual(actual["schema"], lw.intake_schema())
        self.assertIn("screening", actual["schema"]["properties"])
        self.assertNotIn("answer", actual["schema"]["properties"])
        text = (ROOT / "content" / "labs" / "lab-01.md").read_text(encoding="utf-8")
        self.assertNotIn("intake", text.lower())
        script = (ROOT / "content" / "assets" / "lab1_knowledge.py").read_text(encoding="utf-8")
        self.assertNotIn("--intake", script)
        self.assertNotIn('create_agent(\n        "intake"', script)

    def test_openapi_generated_blocks_remain_intact(self):
        path = ROOT / "content" / "labs" / "lab-03.md"
        text = path.read_text(encoding="utf-8")
        block = re.search(r"<!-- openapi-spec:begin.*?<!-- openapi-spec:end -->", text, re.S).group()
        spec = json.loads(re.search(r"```json\s*(.*?)```", block, re.S).group(1))
        self.assertEqual(spec["paths"]["/profile/{resident_id}"]["get"]["operationId"], "get_citizen_profile")
        legacy = (path.parent / "lab-03-portal.md").read_text(encoding="utf-8")
        self.assertNotIn("openapi-spec:begin", legacy)
        self.assertIn("(lab-03.md#navigator)", legacy)

    def test_legacy_visualiser_does_not_claim_unknown_steps_prove_no_query(self):
        spec = importlib.util.spec_from_file_location("fabric_steps_learning_test", ROOT / "demos" / "fabric-steps.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        data = {"question": "Synthetic aggregate question", "run": {"status": "completed"}, "steps": [],
                "answer": "No captured result", "_replayed": True}
        with mock.patch.object(module, "queries", return_value=[]):
            html = module.render(data)
        self.assertIn("Historical GQL diagnostic", html)
        self.assertIn("Absence here is not proof that no query ran", html)
        self.assertNotIn("numbers are not grounded", html)


if __name__ == "__main__":
    unittest.main()
