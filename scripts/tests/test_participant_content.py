"""Offline regression checks for the rendered participant journey."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "demos"))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


blocks = load("participant_blocks", ROOT / "scripts" / "sync-lab-blocks.py")
content = load("participant_checks", ROOT / "scripts" / "check-content.py")
capture = load("participant_capture", ROOT / "demos" / "capture-screenshots.py")
scenes = capture.S


class CopyBlocksTests(unittest.TestCase):
    def test_committed_blocks_are_complete_and_current(self):
        self.assertEqual(blocks.updates(), [])

    def test_indented_block_round_trip(self):
        source = "1. Paste:\n\n   <!-- copy:prompt lab0_hi -->\n   old\n   <!-- /copy -->\n"
        rendered = blocks.render_page(source, {("prompt", "lab0_hi")})
        self.assertIn("   ```text\n   Hi\n   ```", rendered)
        self.assertEqual(blocks.render_page(rendered, {("prompt", "lab0_hi")}), rendered)

    def test_missing_required_block_fails(self):
        with self.assertRaisesRegex(ValueError, "missing copy blocks"):
            blocks.render_page("", {("instructions", "base")})

    def test_unmatched_and_nested_markers_fail(self):
        for source in (
            "<!-- copy:prompt lab0_hi -->\n",
            "<!-- copy:prompt lab0_hi -->\n <!-- /copy -->",
            "<!-- copy:prompt lab0_hi -->\n<!-- copy:prompt lab0_hi -->\n<!-- /copy -->",
        ):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "malformed"):
                blocks.render_page(source, set())

    def test_unknown_sources_fail(self):
        for kind, source in (("schema", "not-a-schema"), ("instructions", "missing"), ("prompt", "missing"),
                             ("request", "lab0_hi"), ("unknown", "lab0_hi")):
            with self.subTest(kind=kind), self.assertRaises((ValueError, KeyError)):
                blocks.payload(kind, source)

    def test_complete_strict_schema_wrappers(self):
        for name, builder in (
            ("lab1-answer", blocks.lw.lab1_schema),
            ("lab1-intake", blocks.lw.intake_schema),
            ("lab3-evidence", blocks.lw.evidence_schema),
        ):
            with self.subTest(name=name):
                language, body = blocks.payload("schema", name)
                schema = json.loads(body)
                self.assertEqual(language, "json")
                self.assertTrue(schema["strict"])
                self.assertEqual(schema["schema"], builder())

    def test_invalid_or_incomplete_schema_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            schemas = root / "content" / "config" / "schemas"
            schemas.mkdir(parents=True)
            for value in ("not json", '{"type":"object"}'):
                with self.subTest(value=value), patch.object(blocks, "ROOT", root):
                    (schemas / "lab1-answer.schema.json").write_text(value, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        blocks.payload("schema", "lab1-answer")

    def test_retained_intake_contract_is_not_required_by_the_lab(self):
        _, body = blocks.payload("schema", "lab1-intake")
        self.assertEqual(set(json.loads(body)["schema"]["required"]),
                         {"screening", "activity", "preferences", "follow_up_flags"})
        self.assertNotEqual(blocks.lw.intake_schema(), blocks.lw.lab1_schema())
        page = (ROOT / "content" / "labs" / "lab-01.md").read_text(encoding="utf-8")
        self.assertNotIn("livewell-<initials>-intake", page)
        self.assertNotIn(("schema", "lab1-intake"), blocks.REQUIRED["lab-01"])

    def test_removed_intake_prompt_is_not_regenerated(self):
        self.assertNotIn(("prompt", "lab1_intake"), blocks.REQUIRED["lab-01"])
        with self.assertRaises(KeyError):
            blocks.payload("prompt", "lab1_intake")

    def test_flyer_retains_exact_tested_framing(self):
        _, body = blocks.payload("prompt", "lab2_injected_flyer")
        expected = blocks.lw.prompt("lab2_injected_flyer")["text"] + "\n\n" + blocks.lw.attachment_text(
            "content/data/flyer-injected.md"
        )
        self.assertEqual(body, expected)
        self.assertIn("<!--\nSYSTEM NOTICE", body)
        self.assertIn('<span style="color:white;font-size:1px">', body)
        self.assertNotIn("--- flyer-injected.md ---", body)

    def test_programme_confirmation_comes_from_reference_data(self):
        references = json.loads((ROOT / "content" / "fabric" / "reference-answers.json").read_text(encoding="utf-8"))
        _, body = blocks.payload("prompt", "lab3_programme_confirm")
        self.assertIn(references["q_programme_fit"]["recommended_programme"], body)
        self.assertNotIn("{recommended_programme}", body)
        self.assertEqual(body, scenes.PROGRAMME_YES)
        self.assertEqual(body, scenes.prompt("lab3_programme_confirm"))

    def test_devui_requests_have_canonical_profile_without_id(self):
        for prompt_id in ("lab4_week_plan_handoff", "lab4_activity_only"):
            _, body = blocks.payload("request", prompt_id)
            self.assertTrue(body.startswith("Resident profile: "))
            self.assertTrue(body.endswith(blocks.lw.prompt_text(prompt_id)))
            self.assertNotIn("RESIDENT_", body)

    def test_shared_intake_instructions_preserve_builder_rules(self):
        expected = (
            "Intake rules:\n- Combine every document the resident pastes into ONE intake record in the JSON schema."
            "\n- Copy values exactly; use null when a value is not in the documents."
            "\n- Do not diagnose and do not add advice."
        )
        self.assertEqual(blocks.lw.load_instructions("intake"), expected)

    def test_activity_discovery_and_confirmation_are_separate(self):
        import ast
        discovery = blocks.lw.prompt("lab3_hazy_indoor_signup")
        confirmation = blocks.lw.prompt("lab3_signup_confirm")
        self.assertIn("Show me the options first.", discovery["text"])
        self.assertNotIn("register_interest", discovery["expected"]["tools"])
        self.assertEqual(confirmation["expected"]["approval_required"], "register_interest")
        tree = ast.parse((ROOT / "content" / "assets" / "lab3_tools.py").read_text(encoding="utf-8"))
        call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call)
                    and any(k.arg == "prompt_id" and isinstance(k.value, ast.Constant)
                            and k.value.value == "lab3_hazy_indoor_signup" for k in node.keywords))
        approval = next(k.value for k in call.keywords if k.arg == "approve")
        self.assertIsInstance(approval, ast.Constant)
        self.assertIs(approval.value, False)

    def test_discovery_only_continues_after_readonly_retrieval(self):
        import ast
        path = ROOT / "content" / "assets" / "lab3_tools.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))

        def assigns(node, name):
            return (isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))

        start = next(i for i, node in enumerate(tree.body) if assigns(node, "conversation"))
        end = next(i for i, node in enumerate(tree.body) if i > start and assigns(node, "calls"))
        cell = compile(ast.Module(body=tree.body[start:end], type_ignores=[]), str(path), "exec")
        for approval, registered, searched in (
            (False, False, True), (True, False, True), (False, True, True), (False, False, False),
        ):
            with self.subTest(approval=approval, registered=registered, searched=searched):
                tools = ({"register_interest"} if registered else set()) | (
                    {"knowledge_base_retrieve"} if searched else set())
                run = SimpleNamespace(approvals=[object()] if approval else [], tool_names=sorted(tools),
                                      called=lambda name: name in tools)
                lw = Mock()
                lw.ask.side_effect = [run, run]
                scope = {"lw": lw, "coach": object(), "FUNCTIONS": {}, "SPECIALIST_CALLS": [],
                         "args": SimpleNamespace(verbose=False)}
                exec(cell, scope)
                continued = not approval and not registered and searched
                self.assertEqual(lw.ask.call_count, 2 if continued else 1)
                self.assertIs(lw.ask.call_args_list[0].kwargs["approve"], False)
                if continued:
                    self.assertEqual(lw.ask.call_args_list[1].kwargs["prompt_id"], "lab3_signup_confirm")
                    self.assertIs(lw.ask.call_args_list[1].kwargs["approve"], lw.ask_human)
                    self.assertIs(lw.ask.call_args_list[1].kwargs["conversation"], scope["conversation"])

    def test_smoke_check_rejects_an_unsolicited_approval_without_retrying(self):
        import ast
        path = ROOT / "scripts" / "smoke-test.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        function = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef) and node.name == "check_tools")
        tools = [SimpleNamespace(kind="mcp_call", name=name)
                 for name in ("get_citizen_profile", "knowledge_base_retrieve", "find_activities")]
        run = SimpleNamespace(tool_calls=tools, called=lambda name: True,
                              approvals=[object()], text="{}", seconds=1)
        lw = Mock()
        lw.ask.return_value = run
        scope = {"lw": lw, "no_resident_id": lambda text: True}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), scope)
        result = scope["check_tools"](object())
        self.assertFalse(result[0][1])
        self.assertIn("1 approval request(s) denied", result[0][2])
        lw.ask.assert_called_once()
        self.assertIs(lw.ask.call_args.kwargs["approve"], False)


class LinkAndJourneyTests(unittest.TestCase):
    def test_code_examples_do_not_create_links_or_headings(self):
        text = "## Real\n\n   ```text\n   ## Not an anchor\n   ![example](missing.png)\n   ```\n[real](#real)\n"
        stripped = content.strip_code(text)
        self.assertNotIn("missing.png", stripped)
        self.assertNotIn("Not an anchor", stripped)
        self.assertIn("[real](#real)", stripped)

    def test_links_case_and_fragments(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / "Target.md").write_text("## Present\n", encoding="utf-8")
            page = root / "README.md"
            for target, should_fail in (("Target.md#present", False), ("Target.md#absent", True),
                                        ("target.md#present", True), ("missing.md", True)):
                with self.subTest(target=target), patch.object(content, "ROOT", root):
                    page.write_text(f"[go]({target})\n", encoding="utf-8")
                    report = content.Report()
                    with contextlib.redirect_stdout(io.StringIO()):
                        content.check_links(report)
                    self.assertEqual(bool(report.failures), should_fail)

    def test_corrupt_png_is_a_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            images = root / "content" / "labs" / "screenshots"
            images.mkdir(parents=True)
            (images / "bad.png").write_bytes(b"not a png")
            for stem in content.LAB_PAGES:
                (root / "content" / "labs" / f"{stem}.md").write_text("", encoding="utf-8")
            with patch.object(content, "ROOT", root), contextlib.redirect_stdout(io.StringIO()):
                report = content.Report()
                content.check_images(report)
            self.assertTrue(report.failures)

    def test_legacy_pages_link_to_canonical_sections(self):
        for n in range(5):
            page = ROOT / "content" / "labs" / f"lab-0{n}-portal.md"
            text = page.read_text(encoding="utf-8")
            self.assertIn(f"(lab-0{n}.md#navigator)", text)
            self.assertNotIn("```", text)
            self.assertIn("what-you-should-see", content.anchors_of(page))
            self.assertIn("if-something-looks-different", content.anchors_of(page))

    def test_openapi_exception_only_targets_canonical_lab3(self):
        api = load("participant_openapi", ROOT / "scripts" / "sync-openapi-block.py")
        self.assertEqual(content.SPEC_BLOCK_PAGES, {"content/labs/lab-03.md"})
        self.assertEqual(api.PAGES, [ROOT / "content" / "labs" / "lab-03.md"])

    def test_tracks_are_independent_and_midway_switching_is_discouraged(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Stay on one track", readme)
        self.assertIn("Do not switch midway", readme)
        self.assertIn("function tools need the", readme)
        self.assertIn("Python client", readme)
        for stem in ("lab-01", "lab-02", "lab-03"):
            text = (ROOT / "content" / "labs" / f"{stem}.md").read_text(encoding="utf-8")
            self.assertNotIn("../../README.md#switching-rails", text)
            self.assertRegex(text, r"(?i)do not switch midway")

    def test_navigator_reuses_the_prepared_knowledge_connection(self):
        page = (ROOT / "content" / "labs" / "lab-01.md").read_text(encoding="utf-8")
        self.assertIn("Available knowledge bases", page)
        self.assertIn("livewell-guides-kb-mcp", page)
        self.assertIn("do not create a connection", page.lower())

    def test_rail_picker_is_at_the_top_of_every_guide(self):
        for stem in blocks.REQUIRED:
            text = (ROOT / "content" / "labs" / f"{stem}.md").read_text(encoding="utf-8")
            self.assertLess(text.index("**Your path:**"), text.index("## Shared objective"))

    def test_core_objectives_match_both_decks(self):
        import ast
        tree = ast.parse((ROOT / "deck" / "build_deck.py").read_text(encoding="utf-8"))
        objectives = next(ast.literal_eval(node.value) for node in tree.body
                          if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "OBJECTIVES"
                                                                  for t in node.targets))
        for lab, objective in content.spec_objectives().items():
            self.assertEqual(objectives[lab], objective)
            text = (ROOT / "content" / "labs" / f"{lab}.md").read_text(encoding="utf-8")
            self.assertEqual(re.search(r"## Shared objective\n\n> (.*)", text)[1], objective)

    def test_capture_discovers_canonical_pages_and_fabric(self):
        names = {path.name for path in scenes.slot_pages()}
        self.assertIn("fabric-step.md", names)
        self.assertIn("lab-04.md", names)
        self.assertFalse(any("portal" in name for name in names))
        self.assertIn("lab-03/17", scenes.slots())

    def test_historical_captures_are_discoverable(self):
        self.assertTrue(scenes.historical_paths() <= {slot.path for slot in scenes.slots().values()})

    def test_participant_guides_do_not_display_archived_images(self):
        historical = scenes.historical_paths()
        for page in scenes.slot_pages():
            images = set(content.IMAGE_RE.findall(content.strip_code(page.read_text(encoding="utf-8"))))
            self.assertFalse(images & historical, page.name)

    def test_deck_does_not_embed_a_historical_capture_as_current(self):
        sys.path.insert(0, str(ROOT / "deck"))
        flow = load("participant_lab_flow", ROOT / "deck" / "build_lab_flow.py")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            labs = root / "content" / "labs"
            labs.mkdir(parents=True)
            (labs / "lab-00.md").write_text(
                "<!-- historical-screenshot: screenshots/lab-00/08-example.png -->", encoding="utf-8"
            )
            prs = flow.Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            with patch.object(flow.Image, "open", side_effect=AssertionError("must not embed old image")):
                flow.add_screenshot(slide, root, "lab-00/08-example.png", (0, 0, 1, 1), 0, 0, 5, 3)
            self.assertTrue(any("Text-only reference" in shape.text for shape in slide.shapes if shape.has_text_frame))

    def test_duplicate_screenshot_id_with_different_paths_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            page = Path(folder) / "lab.md"
            page.write_text("![one](screenshots/lab-00/03-one.png)\n"
                            "![two](screenshots/lab-00/03-two.png)\n", encoding="utf-8")
            with patch.object(scenes, "slot_pages", return_value=[page]):
                with self.assertRaisesRegex(ValueError, "different files"):
                    scenes.slots()

    def test_existing_manual_capture_is_not_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / "photo.png").write_bytes(b"fixture")
            slot = scenes.Slot("lab-00/01", "photo.png", "caption", root / "lab.md", True)
            with patch.object(scenes, "LABS", root), patch.object(scenes, "slots", return_value={slot.id: slot}):
                self.assertEqual(capture.status_rows()[0][2], "present")

    def test_empty_capture_selection_is_not_a_blanket_capture(self):
        with patch.object(sys, "argv", ["capture-screenshots.py", "--only"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                capture.main()
        self.assertEqual(error.exception.code, 2)

    def test_outdated_capture_dry_run_is_exact_and_offline(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["capture-screenshots.py", "--outdated-only", "--dry-run"]):
            with patch.object(capture.P, "open_portal", side_effect=AssertionError("must stay offline")):
                with contextlib.redirect_stdout(output):
                    self.assertEqual(capture.main(), 0)
        selected = {line.split()[1] for line in output.getvalue().splitlines() if not line.startswith("[capture]")}
        self.assertEqual(selected, scenes.historical_paths())
        self.assertNotIn("lab-00/06b", output.getvalue())

    def test_outdated_and_missing_filters_do_not_expand_an_empty_selection(self):
        output = io.StringIO()
        arguments = ["capture-screenshots.py", "--only", "lab-00/06b", "--outdated-only", "--missing-only", "--dry-run"]
        with patch.object(sys, "argv", arguments), contextlib.redirect_stdout(output):
            self.assertEqual(capture.main(), 0)
        self.assertIn("0 selected", output.getvalue())


if __name__ == "__main__":
    unittest.main()
