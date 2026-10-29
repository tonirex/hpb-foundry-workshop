"""Offline checks for Lab 4's explicit Fabric opt-in and concise participant path."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "content" / "assets" / "lab4_multiagent.py"
PAGE = ROOT / "content" / "labs" / "lab-04.md"


class FabricOptInTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        nodes = ast.parse(LAB.read_text(encoding="utf-8")).body
        cls.flags = next(n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == "_flags")
        cls.no_resident_id = next(n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == "no_resident_id")
        cls.guard = next(n for n in nodes if isinstance(n, ast.If)
                         and any(isinstance(statement, ast.Raise) for statement in n.body))
        cls.section = next(n for n in nodes if isinstance(n, ast.If)
                           and ast.unparse(n.test) == "args.fabric")

    def parse(self, *argv):
        namespace = {}
        exec(compile(ast.Module(body=[self.flags], type_ignores=[]), str(LAB), "exec"), namespace)
        parser = argparse.ArgumentParser()
        namespace["_flags"](parser)
        return parser.parse_args(argv), parser.format_help()

    def run_section(self, requested, configured):
        self.lw = NS(
            fabric_enabled=Mock(return_value=configured),
            create_agent=Mock(return_value=NS(name="livewell-test-insights", version=1)),
            load_instructions=Mock(return_value="aggregate-only instructions"),
            fabric_tool=Mock(return_value=object()),
            ask=Mock(return_value=NS(text="Healthier SG; I Quit; National Steps Challenge",
                                     fabric_called=True, fabric_succeeded=True, tool_names=["fabric_iq"])),
            say=Mock(), show_run=Mock(), expect=Mock(), record=Mock(),
            ascii_safe=lambda text: text, _trunc=lambda text, length: text[:length],
            CONTENT=ROOT / "content", TOOLS_MODEL="tools-model", FABRIC_TIMEOUT=180,
        )
        namespace = {"args": NS(fabric=requested, verbose=False), "lw": self.lw,
                     "GUARDRAIL": "livewell-guardrails", "insights_result": {}, "json": json, "re": re}
        code = ast.Module(body=[self.no_resident_id, self.guard, self.section], type_ignores=[])
        exec(compile(code, str(LAB), "exec"), namespace)
        return namespace["insights_result"]

    def test_flag_defaults_off_and_identifies_facilitator_scope(self):
        args, help_text = self.parse()
        self.assertFalse(args.fabric)
        self.assertIn("facilitator only", help_text)
        self.assertTrue(self.parse("--fabric")[0].fabric)

    def test_default_run_never_creates_or_invokes_fabric(self):
        for configured in (False, True):
            with self.subTest(configured=configured):
                self.assertEqual(self.run_section(False, configured), {})
                self.lw.create_agent.assert_not_called()
                self.lw.fabric_tool.assert_not_called()
                self.lw.ask.assert_not_called()
                self.lw.record.assert_not_called()
                self.lw.say.assert_called_once()

    def test_requested_but_disabled_fails_before_any_cloud_call(self):
        with self.assertRaises(SystemExit) as caught:
            self.run_section(True, False)
        self.assertIn("FABRIC_BRIDGE=true", str(caught.exception))
        self.assertTrue(str(caught.exception).isascii())
        self.lw.create_agent.assert_not_called()
        self.lw.fabric_tool.assert_not_called()
        self.lw.ask.assert_not_called()

    def test_explicit_enabled_extension_preserves_facilitator_path(self):
        result = self.run_section(True, True)
        self.lw.create_agent.assert_called_once()
        self.lw.fabric_tool.assert_called_once()
        self.lw.ask.assert_called_once()
        self.assertEqual(self.lw.ask.call_args.kwargs["prompt_id"], "lab4_q_programmes_disengaged")
        self.assertIn("lab4_q_programmes_disengaged", result)


class ParticipantContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = PAGE.read_text(encoding="utf-8")
        cls.prompts = json.loads((ROOT / "content" / "prompts" / "test-prompts.json")
                                .read_text(encoding="utf-8"))["prompts"]

    def test_main_path_stays_concise_and_details_default_closed(self):
        visible = re.sub(r"<details\b[^>]*>.*?</details>", "", self.page, flags=re.S)
        self.assertLessEqual(len(visible.split()), 1100)
        self.assertEqual(self.page.count("<details>"), self.page.count("</details>"))
        self.assertNotRegex(self.page, r"<details\b[^>]*\bopen\b")

    def test_stack_rationale_is_visible_before_both_tracks(self):
        shared = self.page.split("## 🟢 Navigator", 1)[0]
        visible = re.sub(r"<details\b[^>]*>.*?</details>", "", shared, flags=re.S)
        for phrase in ("Microsoft Agent Framework", "open-source SDK", "Microsoft Foundry",
                       "DevUI", "state management", "Why visualise with DevUI?",
                       "optional, not a production UI"):
            self.assertIn(phrase, visible)
        self.assertIn("start with one agent when that is enough", visible.lower())

    def test_developer_detail_is_collapsed_and_explains_visibility_limits(self):
        shared = self.page.split("## 🟢 Navigator", 1)[0]
        faq = re.search(r"<details>\s*<summary><strong>Developer FAQ:.*?</details>", shared, re.S)
        self.assertIsNotNone(faq)
        for phrase in ("Agent Inspector", "Foundry tracing", "not a generic viewer", "server-side"):
            self.assertIn(phrase, faq.group())

    def test_copy_ready_requests_match_the_prompt_bank(self):
        visible = re.sub(r"<details\b[^>]*>.*?</details>", "", self.page, flags=re.S)
        requests = re.findall(r"```text\n.*?\n\n(.*?)\n```", visible, flags=re.S)
        self.assertEqual(requests, [self.prompts[pid]["text"]
                                   for pid in ("lab4_week_plan_handoff", "lab4_activity_only")])

    def test_expected_outputs_distinguish_the_two_patterns(self):
        expected = self.prompts["lab4_week_plan_handoff"]["expected"]["workflows"]
        self.assertEqual(expected["sequential"]["route"][-1], "coach")
        self.assertEqual(expected["handoff"]["route"][-1], "activity")
        self.assertIn("not merged JSON", expected["handoff"]["final_output"])
        activity_only = self.prompts["lab4_activity_only"]["expected"]["workflows"]["handoff"]
        self.assertEqual(activity_only["route"], ["coach", "activity"])
        self.assertEqual(activity_only["tools"], ["handoff_to_activity"])


if __name__ == "__main__":
    unittest.main()
