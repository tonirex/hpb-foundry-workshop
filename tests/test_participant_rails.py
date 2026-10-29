"""Offline execution and layout checks for the independent participant tracks."""
from __future__ import annotations

import ast
from pathlib import Path
import re
import runpy
import sys
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "content" / "assets"
PAGES = ("lab-00", "lab-01", "lab-02", "lab-03", "lab-04", "fabric-step")


class ScriptTests(unittest.TestCase):
    def setUp(self):
        self.lw = Mock()
        self.lw.NAMES = {"rai_policy": "workshop-policy"}
        self.lw.DEFAULT_RAI_POLICY = "platform-default"
        self.lw.DEFAULT_MODEL = "chat-model"
        self.lw.TOOLS_MODEL = "tools-model"
        self.lw.FABRIC_TIMEOUT = 300
        self.lw.lab_args.return_value = NS(verbose=True, cleanup=False)
        self.lw.create_agent.return_value = NS(name="livewell-test-coach", version="1")
        self.lw.ask.return_value = NS(text="Example response", blocked=False, tool_calls=[], tool_names=[])
        self.package = ModuleType("common")
        self.package.livewell_common = self.lw

    def execute(self, name):
        with patch.dict(sys.modules, {"common": self.package}), patch.object(sys, "path", sys.path.copy()):
            return runpy.run_path(str(ASSETS / name), run_name="__main__")

    def test_builder_lab0_creates_its_own_tool_free_agent(self):
        self.execute("lab0_setup.py")
        self.assertEqual(self.lw.create_agent.call_args.args[0], "coach")
        self.assertEqual(self.lw.create_agent.call_args.kwargs["tools"], [])
        self.assertEqual([call.kwargs["prompt_id"] for call in self.lw.ask.call_args_list],
                         ["lab0_hi", "lab0_am_i_diabetic"])
        self.lw.agent_by_name.assert_not_called()
        self.lw.kb_tool.assert_not_called()
        self.lw.cleanup.assert_not_called()

    def test_builder_lab0_cleanup_remains_explicit(self):
        self.lw.lab_args.return_value.cleanup = True
        self.execute("lab0_setup.py")
        self.lw.cleanup.assert_called_once_with()

    def test_fabric_disabled_stops_before_creating_or_calling_an_agent(self):
        self.lw.fabric_enabled.return_value = False
        with self.assertRaisesRegex(SystemExit, "Fabric is not enabled"):
            self.execute("lab3_fabric.py")
        self.lw.create_agent.assert_not_called()
        self.lw.ask.assert_not_called()
        self.lw.fabric_tool.assert_not_called()

    def test_fabric_comparison_is_independent_and_has_no_write_tools(self):
        self.lw.fabric_enabled.return_value = True
        self.lw.ask.side_effect = [
            NS(text="Aggregate regions", fabric_called=True, fabric_succeeded=True, tool_names=["fabric_iq"]),
            NS(text="Guide advice", fabric_called=False, kb_called=True, tool_names=["knowledge_base_retrieve"]),
        ]
        self.execute("lab3_fabric.py")
        self.assertEqual(self.lw.create_agent.call_args.args[0], "fabric")
        self.assertEqual(self.lw.create_agent.call_args.kwargs["tools"],
                         [self.lw.kb_tool.return_value, self.lw.fabric_tool.return_value])
        self.lw.activities_tool.assert_not_called()
        self.lw.profile_tool.assert_not_called()
        self.lw.agent_by_name.assert_not_called()
        self.assertEqual([call.kwargs["prompt_id"] for call in self.lw.ask.call_args_list],
                         ["fabric_q_disengaged_regions", "lab1_prediabetes_eat"])
        self.assertTrue(all(call.kwargs["approve"] is False for call in self.lw.ask.call_args_list))

    def test_lab3_does_not_inherit_the_optional_programme_fit_run(self):
        source = ASSETS / "lab3_tools.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        extension = next(node for node in tree.body if isinstance(node, ast.If)
                         and ast.unparse(node.test) == "args.fabric")
        scope = {"args": NS(fabric=False), "lw": self.lw}
        exec(compile(ast.Module(body=[extension], type_ignores=[]), str(source), "exec"), scope)
        self.lw.create_agent.assert_not_called()
        self.lw.ask.assert_not_called()

    def test_lab4_default_does_not_call_the_operator_hosted_endpoint(self):
        source = ASSETS / "lab4_multiagent.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        extension = next(node for node in tree.body if isinstance(node, ast.If)
                         and ast.unparse(node.test) == "args.hosted")
        scope = {"args": NS(hosted=False), "lw": self.lw}
        exec(compile(ast.Module(body=[extension], type_ignores=[]), str(source), "exec"), scope)
        self.lw.agent_by_name.assert_not_called()
        self.lw.rai_policy_id.assert_not_called()
        self.lw.ask.assert_not_called()


class LayoutTests(unittest.TestCase):
    def test_help_precedes_the_objective_and_troubleshooting_is_closed(self):
        for stem in PAGES:
            with self.subTest(page=stem):
                text = (ROOT / "content" / "labs" / f"{stem}.md").read_text(encoding="utf-8")
                intro = text.split("## Shared objective")[0]
                self.assertIn("[Checkpoint](#checkpoint)", intro)
                self.assertIn("Expected output (open after you have tried it)", intro)
                self.assertIn("track", intro)
                troubleshoot = text.split("## Troubleshooting")[1].split("## Where next")[0].strip()
                self.assertTrue(troubleshoot.startswith("<details>"))
                self.assertTrue(troubleshoot.endswith("</details>"))
                self.assertNotRegex(text, r"<details\b[^>]*\bopen\b")

    def test_navigator_screenshots_are_inline_not_in_a_gallery(self):
        minimum = {"lab-00": 6, "lab-01": 6, "lab-02": 10, "lab-03": 10, "lab-04": 3, "fabric-step": 1}
        for stem in PAGES:
            with self.subTest(page=stem):
                text = (ROOT / "content" / "labs" / f"{stem}.md").read_text(encoding="utf-8")
                navigator = text.split("## 🟢 Navigator")[1].split("## 🔵 Builder")[0]
                depth, inline_images = 0, 0
                for line in navigator.splitlines():
                    if re.match(r"\s*<details\b", line):
                        depth += 1
                    elif re.match(r"\s*</details>", line):
                        depth -= 1
                    elif depth == 0 and re.match(r"\s*!\[", line):
                        inline_images += 1
                self.assertGreaterEqual(inline_images, minimum[stem])
                self.assertNotIn("Setup screenshots and FAQ", navigator)

    def test_builder_does_not_send_the_reader_to_navigator(self):
        for stem in PAGES:
            text = (ROOT / "content" / "labs" / f"{stem}.md").read_text(encoding="utf-8")
            builder = text.split("## 🔵 Builder")[1].split("## Checkpoint")[0]
            self.assertNotIn("(#navigator)", builder)
            self.assertNotRegex(builder, r"(?i)follow.*navigator|same.*above|reuse.*prompt.*above")

    def test_removed_module_and_intake_are_not_in_active_participant_content(self):
        self.assertFalse((ROOT / "content" / "labs" / "bridge-spotlight.md").exists())
        for stem in PAGES:
            text = (ROOT / "content" / "labs" / f"{stem}.md").read_text(encoding="utf-8")
            self.assertNotIn("bridge-spotlight", text)
            self.assertNotIn("lab1_intake", text)
        source = (ASSETS / "lab1_knowledge.py").read_text(encoding="utf-8")
        self.assertNotIn("--intake", source)


if __name__ == "__main__":
    unittest.main()
