"""Offline regressions for Builder evidence, responses, retries, settings and cleanup."""
from __future__ import annotations

import importlib.util
import ast
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

import openai
from azure.core.exceptions import HttpResponseError, ServiceRequestError, ServiceResponseError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "content" / "assets"))
from common import livewell_common as lw

spec = importlib.util.spec_from_file_location("builder_validator", ROOT / "scripts" / "validate-builder-rail.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)

GUIDE = "lg-05-eating-for-pre-diabetes"
OTHER_GUIDE = "lg-01-healthy-plate"


def retrieval(*, guide=GUIDE, snippet="Use the healthy plate.", status="completed", error="", payload=None):
    output = {"documents": [{"title": guide, "content": json.dumps({"snippet": snippet})}]}
    return lw.ToolCall(kind="mcp_call", name="knowledge_base_retrieve", server=lw.KB_LABEL,
                       status=status, error=error, output=json.dumps(output if payload is None else payload))


def api_error(status):
    error = HttpResponseError(message="offline API error")
    error.status_code = status
    return error


class RetrievalTests(unittest.TestCase):
    def test_completed_retrieval_carries_guide_and_passage_evidence(self):
        run = lw.Run(prompt="", tool_calls=[retrieval()])
        self.assertTrue(run.kb_called)
        self.assertEqual(run.retrieved_guides, [GUIDE])
        self.assertIn("Use the healthy plate.", lw.kb_context(run))
        self.assertEqual(run.summary()["retrieved_guides"], [GUIDE])

    def test_failed_or_unfinished_calls_never_supply_evidence(self):
        for status in ("failed", "in_progress", "incomplete", ""):
            with self.subTest(status=status):
                run = lw.Run(prompt="", tool_calls=[retrieval(status=status)])
                self.assertFalse(run.kb_called)
                self.assertEqual(run.retrieved_guides, [])
                self.assertEqual(lw.kb_context(run), "")
        for error in ("unavailable", '{"message":"request failed"}'):
            with self.subTest(error=error):
                self.assertFalse(lw.Run(prompt="", tool_calls=[retrieval(error=error)]).kb_called)

    def test_failed_call_does_not_override_a_later_successful_retrieval(self):
        run = lw.Run(prompt="", tool_calls=[retrieval(status="failed", error="timeout"), retrieval()])
        self.assertTrue(run.kb_called)
        self.assertEqual(run.retrieved_guides, [GUIDE])

    def test_completed_error_payload_is_not_success(self):
        for error in ({"error": "failed"}, {"isError": True}):
            payload = json.loads(retrieval().output) | error
            with self.subTest(error=error):
                self.assertFalse(lw.Run(prompt="", tool_calls=[retrieval(payload=payload)]).kb_called)

    def test_empty_unknown_and_malformed_documents_are_not_evidence(self):
        for call in (retrieval(snippet=" "), retrieval(guide="lg-99-invented"),
                     retrieval(payload=[]), retrieval(payload={"documents": "not a list"}),
                     retrieval(payload={"documents": [None, {"content": "no guide"}]}),
                     retrieval(payload={"documents": [{"title": GUIDE, "content": "null"}]})):
            with self.subTest(output=call.output):
                self.assertFalse(lw.Run(prompt="", tool_calls=[call]).kb_called)
        call = retrieval()
        call.output = "not JSON"
        self.assertFalse(lw.Run(prompt="", tool_calls=[call]).kb_called)

    def test_blob_metadata_and_plain_passages_are_supported(self):
        for content in (
            {"blob_url": f"https://example.invalid/{GUIDE}.pdf", "snippet": "Retrieved passage"},
            json.dumps({"blob_url": f"https://example.invalid/{GUIDE}.pdf", "content": "Retrieved passage"}),
            "Retrieved passage",
        ):
            payload = {"documents": [{"title": GUIDE, "content": content}]}
            with self.subTest(content=content):
                self.assertEqual(lw.Run(prompt="", tool_calls=[retrieval(payload=payload)]).retrieved_guides, [GUIDE])

    def run_lab1(self, call, citations):
        food = lw.Run(prompt="", text=json.dumps({"answer": "Food advice", "route": "self_care",
                                                "cited_sources": citations}), tool_calls=[call])
        supplement = lw.Run(prompt="", text=json.dumps({
            "answer": "The guides do not cover supplements.", "route": "clinician", "cited_sources": []}))
        with (patch.object(lw, "ask", side_effect=[food, supplement]),
              patch.object(lw, "lab_args", return_value=NS(verbose=False, cleanup=False)),
              patch.object(lw, "endpoint", return_value="offline"),
              patch.object(lw, "kb_tool", return_value=NS(server_label="kb", project_connection_id="offline")),
              patch.object(lw, "create_agent", return_value=NS(name="livewell-test-coach", version="1")),
              patch.object(lw, "save_results"), patch.object(lw, "say"),
              patch.object(lw, "RESULTS", {}), patch.dict(os.environ, {"INITIALS": "test"})):
            runpy.run_path(str(ROOT / "content" / "assets" / "lab1_knowledge.py"), run_name="__main__")
            return dict(lw.RESULTS["checks"])

    def test_lab1_rejects_failed_retrieval_with_valid_looking_citations(self):
        checks = self.run_lab1(retrieval(status="failed", error="unavailable"), [GUIDE])
        self.assertFalse(checks["lab1_prediabetes_eat: knowledge base searched"])
        self.assertFalse(checks["lab1_prediabetes_eat: cited guides were retrieved"])

    def test_lab1_rejects_a_citation_to_an_unretrieved_real_guide(self):
        checks = self.run_lab1(retrieval(), [GUIDE, OTHER_GUIDE])
        self.assertFalse(checks["lab1_prediabetes_eat: cited guides were retrieved"])

    def test_lab1_accepts_a_cited_retrieved_passage(self):
        checks = self.run_lab1(retrieval(), [GUIDE])
        self.assertTrue(all(checks.values()), checks)

    def test_validator_requires_the_new_retrieval_check(self):
        checks = {"lab1_prediabetes_eat: knowledge base searched": True,
                  "lab1_prediabetes_eat: cites a real guide": True}
        self.assertEqual(validator.signal_rows({"lab1": {"checks": checks}}, False)[0][2], "FAIL")
        checks["lab1_prediabetes_eat: cited guides were retrieved"] = True
        self.assertEqual(validator.signal_rows({"lab1": {"checks": checks}}, False)[0][2], "PASS")

    def test_failed_fabric_attempt_still_counts_as_routing_but_not_success(self):
        for status in ("failed", "completed"):
            call = lw.ToolCall(kind="mcp_call", name="DataAgent_query", server=lw.FABRIC_LABEL,
                               status=status, output="Aggregate results")
            run = lw.Run(prompt="", tool_calls=[call])
            self.assertTrue(run.fabric_called)
            self.assertEqual(run.fabric_succeeded, status == "completed")
        approval = lw.ToolCall(kind="mcp_approval_request", name="DataAgent_query", server=lw.FABRIC_LABEL,
                               status="completed", output="not executed")
        self.assertFalse(lw.Run(prompt="", tool_calls=[approval]).fabric_succeeded)


class AnswerShapeTests(unittest.TestCase):
    def test_single_objects_keep_nested_values_escapes_and_fences(self):
        data = {"advice": 'A quote: " and a brace: }', "nested": {"items": [1, 2]}}
        text = json.dumps(data)
        for answer in (text, f" \n{text}\n", f"```json\n{text}\n```", f"```\n{text}\n```"):
            with self.subTest(answer=answer):
                self.assertEqual(lw.extract_json(answer), data)

    def test_multiple_objects_extra_text_arrays_and_scalars_are_rejected(self):
        for text in ('{}{}', '{}\n{}', '```json\n{}\n```\n{}', '```json\n{}\n```\n```json\n{}\n```',
                     'Answer: {}', '{} trailing text', '[{}]', 'null', '42', '{"broken":', ''):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "exactly one"):
                lw.extract_json(text)

    def test_ask_selects_last_message_for_both_display_and_json_without_retrying(self):
        first, last = '{"advice":"first answer"}', '{"advice":"last answer"}'
        response = NS(id="offline-response", status="completed", output_text=first + last, output=[
            NS(type="message", content=[NS(text=first)]), NS(type="message", content=[NS(text=last)])])
        client = Mock()
        client.responses.create.return_value = response
        with patch.object(lw, "openai_client", return_value=client):
            result = lw.ask("livewell-test-coach", "offline")
        client.responses.create.assert_called_once()
        self.assertEqual(result.replies, 2)
        self.assertEqual(result.text, last)
        self.assertEqual(result.json(), {"advice": "last answer"})
        self.assertEqual(result.summary()["json"], {"advice": "last answer"})
        with patch.object(lw, "say") as say:
            lw.show_run(result)
        printed = "\n".join(call.args[0] for call in say.call_args_list)
        self.assertIn("showing the last", printed)
        self.assertIn(last, printed)
        self.assertNotIn(first, printed)

    def test_selected_message_still_requires_exactly_one_json_object(self):
        response = NS(id="offline-response", status="completed", output_text='{}{}{}', output=[
            NS(type="message", content=[NS(text="{}")]), NS(type="message", content=[NS(text="{}{}")])])
        client = Mock()
        client.responses.create.return_value = response
        with patch.object(lw, "openai_client", return_value=client):
            result = lw.ask("livewell-test-coach", "offline")
        self.assertEqual(result.text, "{}{}")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            result.json()
        client.responses.create.assert_called_once()

    def test_empty_last_message_does_not_fall_back_to_an_earlier_answer(self):
        response = NS(id="offline-response", status="completed", output_text='{"advice":"earlier"}', output=[
            NS(type="message", content=[NS(text='{"advice":"earlier"}')]), NS(type="message", content=[])])
        client = Mock()
        client.responses.create.return_value = response
        with patch.object(lw, "openai_client", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "without a final answer"):
                lw.ask("livewell-test-coach", "offline")
        client.responses.create.assert_called_once()

    def test_ask_preserves_one_answer_message(self):
        response = NS(id="offline-response", status="completed", output_text='{"advice":"one"}', output=[
            NS(type="message", content=[NS(text='{"advice":"one"}')])])
        client = Mock()
        client.responses.create.return_value = response
        with patch.object(lw, "openai_client", return_value=client):
            result = lw.ask("livewell-test-coach", "offline")
        self.assertEqual(result.json(), {"advice": "one"})


class MemoryIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / "content" / "assets" / "lab3_tools.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))

        def assigns(node, name):
            return isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name for target in node.targets)

        start = next(i for i, node in enumerate(tree.body) if assigns(node, "recall"))
        end = next(i for i, node in enumerate(tree.body) if assigns(node, "plans"))
        cls.memory_cell = compile(ast.Module(body=tree.body[start:end], type_ignores=[]), str(path), "exec")
        core_tools = next(node for node in tree.body if assigns(node, "tools"))
        cls.core_tools_cell = compile(ast.Module(body=[core_tools], type_ignores=[]), str(path), "exec")

    def setUp(self):
        import re

        self.fake = Mock()
        self.fake.AmbiguousResponseError = lw.AmbiguousResponseError
        self.fake.ascii_safe.side_effect = lw.ascii_safe
        self.fake.expect.side_effect = lambda label, ok, *detail: ok
        self.fake.new_conversation.side_effect = ["offline-set-conversation", "offline-recall-conversation"]
        self.fake.wait_for_memories.return_value = ["Prefers mornings; dislikes swimming."]
        self.run = lw.Run(prompt="offline", text=json.dumps({
            "advice": "Try a morning indoor class.", "supporting_guides": [],
        }), tool_calls=[lw.ToolCall(kind="memory_search_call", name="memory_search_call")])
        self.fake.ask.side_effect = [self.run, self.run]
        self.scope = {
            "lw": self.fake, "args": NS(verbose=False), "re": re, "store": "offline-memory",
            "blocks": ["base", "knowledge", "safety", "tools"], "GUARDRAIL": "offline-policy",
            "memory": object(), "profile": object(), "knowledge": object(), "activities": object(),
            "nutrition_tool": object(), "activity_tool": object(),
            "advice_of": lambda run: run.json()["advice"], "fits_profile": lambda run: (True, []),
            "invented": lambda run: [],
        }

    def test_write_capable_coach_has_no_memory_tool(self):
        exec(self.core_tools_cell, self.scope)
        self.assertNotIn(self.scope["memory"], self.scope["tools"])
        self.assertIn(self.scope["activities"], self.scope["tools"])

    def test_memory_agent_has_only_readonly_tools_and_no_specialist_handlers(self):
        exec(self.memory_cell, self.scope)
        self.fake.activities_tool.assert_called_once_with(read_only=True)
        created = self.fake.create_agent.call_args
        self.assertEqual(created.args[0], "memory-coach")
        self.assertEqual(created.kwargs["tools"], [
            self.scope["profile"], self.scope["knowledge"], self.fake.activities_tool.return_value,
            self.scope["memory"],
        ])
        self.fake.load_instructions.assert_called_once_with(*self.scope["blocks"], "memory")
        for call in self.fake.ask.call_args_list:
            self.assertIs(call.args[0], self.fake.create_agent.return_value)
            self.assertIs(call.kwargs["approve"], False)
            self.assertEqual(list(call.kwargs["functions"]), ["get_citizen_profile"])
        self.assertEqual(self.fake.new_conversation.call_count, 2)
        self.assertEqual([call.kwargs["conversation"] for call in self.fake.ask.call_args_list],
                         ["offline-set-conversation", "offline-recall-conversation"])
        self.assertEqual(self.scope["memory_status"], "VERIFIED")

    def test_readonly_activity_tool_exposes_only_discovery(self):
        with patch.object(lw, "connection", return_value=NS(target="https://example.invalid")):
            tool = lw.activities_tool(read_only=True)
        self.assertEqual(tool.as_dict()["allowed_tools"], ["find_activities"])
        self.assertEqual(tool.as_dict()["require_approval"], "never")

    def test_ambiguous_preview_is_reported_without_replay_or_false_pass(self):
        for turn in (0, 1):
            with self.subTest(turn=turn):
                self.setUp()
                trace = lw.Run(prompt="offline", agent="livewell-test-memory-coach", replies=2,
                               response_ids=["offline-memory-response"])
                error = lw.AmbiguousResponseError("two memory answers", trace)
                self.fake.ask.side_effect = [error] if turn == 0 else [self.run, error]
                exec(self.memory_cell, self.scope)
                self.assertEqual(self.fake.ask.call_count, turn + 1)
                self.fake.expect.assert_not_called()
                self.assertIsNone(self.scope["recall"])
                self.assertIn("NOT VERIFIED", self.scope["memory_status"])
                result = self.fake.record.call_args_list[0].args[1]
                self.assertEqual(result["status"], "NOT VERIFIED")
                self.assertEqual(result["trace"]["response_ids"], ["offline-memory-response"])
                self.assertEqual(result["trace"]["text"], "")

    def test_unrelated_errors_remain_failures(self):
        for error in (ValueError("invalid input"), RuntimeError("service failed")):
            with self.subTest(error=error):
                self.fake.ask.side_effect = error
                with self.assertRaises(type(error)):
                    exec(self.memory_cell, self.scope)

    def test_failed_evidence_is_not_reported_as_verified(self):
        self.fake.wait_for_memories.return_value = []
        exec(self.memory_cell, self.scope)
        self.assertIn("NOT VERIFIED", self.scope["memory_status"])

    def test_disabled_memory_creates_no_agent_and_sends_no_requests(self):
        self.scope["memory"] = None
        exec(self.memory_cell, self.scope)
        self.fake.create_agent.assert_not_called()
        self.fake.ask.assert_not_called()
        self.assertIn("SKIPPED", self.scope["memory_status"])

    def test_observed_memory_response_shape_uses_last_answer_without_replay(self):
        first, last = '{"advice":"first"}', '{"advice":"last"}'
        response = NS(id="offline-memory-response", status="completed", output_text=first + last, output=[
            NS(type="message", role="assistant", phase=None, status="completed", content=[NS(text=first)]),
            NS(type="message", role="assistant", phase=None, status="completed", content=[NS(text=last)]),
            NS(type="memory_search_call", id="offline-memory-call", status="in_progress"),
        ])
        client = Mock()
        client.responses.create.return_value = response
        with patch.object(lw, "openai_client", return_value=client):
            result = lw.ask("livewell-test-memory-coach", "offline", approve=False)
        client.responses.create.assert_called_once()
        self.assertEqual(result.replies, 2)
        self.assertEqual(result.response_ids, ["offline-memory-response"])
        self.assertEqual(result.text, last)
        self.assertEqual(result.json(), {"advice": "last"})
        self.assertEqual(result.tool_calls[0].kind, "memory_search_call")


def completed_response(text='{"advice":"one"}'):
    return NS(id="offline-completed", status="completed", output_text=text,
              output=[NS(type="message", content=[NS(text=text)])])


class ApprovalRetryTests(unittest.TestCase):
    def approval_response(self):
        return NS(id="offline-approval-response", status="completed", output_text="", output=[
            NS(type="mcp_approval_request", id="offline-approval", name="register_interest",
               server_label=lw.ACTIVITIES_LABEL, arguments='{"activity_id":"offline"}')])

    def status_error(self, status):
        return openai.APIStatusError("offline error", response=NS(status_code=status, request=Mock(), headers={}),
                                     body={"code": "offline_error"})

    def test_approval_submissions_are_never_replayed_after_transport_or_http_errors(self):
        errors = [openai.APIConnectionError(request=Mock()), openai.APITimeoutError(request=Mock()),
                  ServiceRequestError("offline"), ServiceResponseError("offline"),
                  self.status_error(429), self.status_error(503)]
        for error in errors:
            for decision in (True, False):
                with self.subTest(error=type(error).__name__, status=getattr(error, "status_code", None),
                                  decision=decision):
                    client = Mock()
                    client.responses.create.side_effect = [self.approval_response(), error, completed_response()]
                    with (patch.object(lw, "openai_client", return_value=client),
                          patch.object(lw.time, "sleep") as sleep, patch.object(lw, "say")):
                        with self.assertRaises(type(error)):
                            lw.ask("livewell-test-coach", "offline", approve=decision)
                    self.assertEqual(client.responses.create.call_count, 2)
                    self.assertIs(client.responses.create.call_args.kwargs["input"][0]["approve"], decision)
                    sleep.assert_not_called()

    def test_ordinary_model_calls_keep_transient_retries(self):
        for error in (openai.APIConnectionError(request=Mock()), self.status_error(503), self.status_error(429)):
            with self.subTest(error=type(error).__name__, status=getattr(error, "status_code", None)):
                client = Mock()
                client.responses.create.side_effect = [error, completed_response()]
                with (patch.object(lw, "openai_client", return_value=client),
                      patch.object(lw.time, "sleep") as sleep, patch.object(lw, "say")):
                    result = lw.ask("livewell-test-coach", "offline")
                self.assertEqual(result.json(), {"advice": "one"})
                self.assertEqual(client.responses.create.call_count, 2)
                sleep.assert_called_once()

    def test_transport_retry_opt_out_covers_connections_not_just_timeouts(self):
        for error in (openai.APIConnectionError(request=Mock()), openai.APITimeoutError(request=Mock()),
                      ServiceRequestError("offline"), ServiceResponseError("offline")):
            with self.subTest(error=type(error).__name__):
                fn = Mock(side_effect=[error, "must not run"])
                with patch.object(lw.time, "sleep") as sleep:
                    with self.assertRaises(type(error)):
                        lw.retry(fn, retry_timeouts=False)
                fn.assert_called_once()
                sleep.assert_not_called()

    def test_guardrail_block_after_an_approval_is_reported_without_replay(self):
        error = openai.BadRequestError("content_filter", response=NS(status_code=400, request=Mock(), headers={}),
                                       body={"code": "content_filter"})
        client = Mock()
        client.responses.create.side_effect = [self.approval_response(), error]
        with patch.object(lw, "openai_client", return_value=client), patch.object(lw, "say"):
            result = lw.ask("livewell-test-coach", "offline", approve=True)
        self.assertTrue(result.blocked)
        self.assertEqual(client.responses.create.call_count, 2)

    def test_denial_includes_explicit_reason_and_accepts_one_acknowledgement(self):
        client = Mock()
        client.responses.create.side_effect = [
            self.approval_response(), completed_response('{"advice":"Registration was not approved."}')]
        with patch.object(lw, "openai_client", return_value=client), patch.object(lw, "say"):
            result = lw.ask("livewell-test-coach", "offline", approve=False, conversation="offline-conversation")
        decision = client.responses.create.call_args.kwargs["input"][0]
        self.assertIs(decision["approve"], False)
        self.assertIn("Human approval denied", decision["reason"])
        self.assertIn("Do not execute or retry", decision["reason"])
        self.assertFalse(result.approvals[0].approved)
        self.assertEqual(result.json()["advice"], "Registration was not approved.")
        self.assertEqual(client.responses.create.call_count, 2)

    def test_denial_does_not_accept_or_retry_multiple_success_claims(self):
        response = NS(id="offline-denial-response", status="completed", output_text="Signed up.Signed up.",
                      output=[NS(type="message", content=[NS(text="Signed up.")]),
                              NS(type="message", content=[NS(text="Signed up.")])])
        client = Mock()
        client.responses.create.side_effect = [self.approval_response(), response, completed_response()]
        with patch.object(lw, "openai_client", return_value=client), patch.object(lw, "say"):
            with self.assertRaisesRegex(ValueError, "Recorded DENIED approval.*register_interest"):
                lw.ask("livewell-test-coach", "offline", approve=False)
        self.assertIs(client.responses.create.call_args.kwargs["input"][0]["approve"], False)
        self.assertEqual(client.responses.create.call_count, 2)

    def test_approved_write_with_multiple_answers_is_not_replayed(self):
        final = NS(id="offline-write-response", status="completed", output_text="first last", output=[
            NS(type="mcp_call", name="register_interest", server_label=lw.ACTIVITIES_LABEL,
               status="completed", output='{"registered":true}'),
            NS(type="message", content=[NS(text='{"advice":"first"}')]),
            NS(type="message", content=[NS(text='{"advice":"last"}')]),
        ])
        client = Mock()
        client.responses.create.side_effect = [self.approval_response(), final, completed_response()]
        with patch.object(lw, "openai_client", return_value=client), patch.object(lw, "say"):
            result = lw.ask("livewell-test-coach", "offline", approve=True)
        self.assertEqual(result.json(), {"advice": "last"})
        self.assertTrue(result.approvals[0].approved)
        self.assertEqual(client.responses.create.call_count, 2)
        self.assertTrue(client.responses.create.call_args.kwargs["input"][0]["approve"])

    def test_tools_instructions_require_denial_and_execution_evidence(self):
        instructions = lw.load_instructions("tools")
        self.assertIn("human approval decision is authoritative", instructions)
        self.assertIn("successful register_interest tool result for this request", instructions)
        self.assertIn("ONE final assistant message", instructions)


class ResponseCompletionTests(unittest.TestCase):
    def test_failed_incomplete_and_nonterminal_responses_raise_before_local_tools_run(self):
        for status in ("failed", "incomplete", "queued", "in_progress", "cancelled", None, ""):
            with self.subTest(status=status):
                response = NS(id="offline-failed", status=status, error=NS(code="offline_error"),
                              incomplete_details=NS(reason="max_output_tokens"), output_text="",
                              output=[NS(type="function_call", name="profile", call_id="offline", arguments="{}")])
                client, handler = Mock(), Mock()
                client.responses.create.return_value = response
                with patch.object(lw, "openai_client", return_value=client):
                    with self.assertRaisesRegex(RuntimeError, "offline-failed.*status"):
                        lw.ask("livewell-test-coach", "offline", functions={"profile": handler})
                client.responses.create.assert_called_once()
                handler.assert_not_called()

    def test_output_content_filter_is_still_a_block_not_a_generic_failure(self):
        response = NS(id="offline-filtered", status="incomplete", incomplete_details=NS(reason="content_filter"),
                      output_text="", output=[])
        client = Mock()
        client.responses.create.return_value = response
        with patch.object(lw, "openai_client", return_value=client):
            result = lw.ask("livewell-test-coach", "offline")
        self.assertTrue(result.blocked)
        self.assertIn("content_filter", result.block_reason)

    def test_exhausted_tool_loop_raises_without_restarting(self):
        response = NS(id="offline-tool", status="completed", output_text="", output=[
            NS(type="function_call", name="profile", call_id="offline", arguments="{}")])
        client, handler = Mock(), Mock(return_value={})
        client.responses.create.return_value = response
        with patch.object(lw, "openai_client", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "exhausted 2.*offline-tool"):
                lw.ask("livewell-test-coach", "offline", functions={"profile": handler}, max_rounds=2)
        self.assertEqual(client.responses.create.call_count, 2)
        self.assertEqual(handler.call_count, 2)

    def test_answer_on_last_allowed_round_is_accepted(self):
        response = NS(id="offline-tool", status="completed", output_text="", output=[
            NS(type="function_call", name="profile", call_id="offline", arguments="{}")])
        client = Mock()
        client.responses.create.side_effect = [response, completed_response()]
        with patch.object(lw, "openai_client", return_value=client):
            result = lw.ask("livewell-test-coach", "offline", functions={"profile": lambda: {}}, max_rounds=2)
        self.assertEqual(result.json(), {"advice": "one"})
        self.assertEqual(client.responses.create.call_count, 2)

    def test_invalid_round_limit_stops_before_creating_a_client(self):
        with patch.object(lw, "openai_client") as client:
            for rounds in (0, -1):
                with self.subTest(rounds=rounds), self.assertRaisesRegex(ValueError, "max_rounds"):
                    lw.ask("livewell-test-coach", "offline", max_rounds=rounds)
        client.assert_not_called()

    def test_completed_but_empty_response_is_an_error(self):
        for text in ("", " \n"):
            with self.subTest(text=text):
                client = Mock()
                client.responses.create.return_value = completed_response(text)
                with patch.object(lw, "openai_client", return_value=client):
                    with self.assertRaisesRegex(RuntimeError, "offline-completed.*without a final answer"):
                        lw.ask("livewell-test-coach", "offline")
                client.responses.create.assert_called_once()

    def test_refusal_content_remains_visible(self):
        response = NS(id="offline-refusal", status="completed", output_text="", output=[
            NS(type="message", content=[NS(type="refusal", refusal="I cannot diagnose.")])])
        client = Mock()
        client.responses.create.return_value = response
        with patch.object(lw, "openai_client", return_value=client):
            result = lw.ask("livewell-test-coach", "offline")
        self.assertEqual(result.text, "I cannot diagnose.")


class TimeoutSettingsTests(unittest.TestCase):
    def import_settings(self, *, participant="", azd="", shell=None):
        tree = ast.parse(lw.HERE.read_text(encoding="utf-8"))
        prefix = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "config":
                break
            prefix.append(node)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            assets = root / "content" / "assets"
            assets.mkdir(parents=True)
            (assets / ".env").write_text(participant, encoding="utf-8")
            env = root / ".azure" / "offline"
            env.mkdir(parents=True)
            (env / ".env").write_text(azd, encoding="utf-8")
            scope = {"__file__": str(assets / "common" / "livewell_common.py")}
            with patch.dict(os.environ, shell or {}, clear=True):
                exec(compile(ast.Module(body=prefix, type_ignores=[]), str(lw.HERE), "exec"), scope)
            return scope["RESPONSE_TIMEOUT"], scope["FABRIC_TIMEOUT"]

    def test_default_timeouts_are_preserved(self):
        self.assertEqual(self.import_settings(), (180.0, 300.0))

    def test_participant_env_timeouts_are_loaded_before_initialisation(self):
        self.assertEqual(self.import_settings(participant="LIVEWELL_TIMEOUT=7\nLIVEWELL_FABRIC_TIMEOUT=9\n"),
                         (7.0, 9.0))

    def test_azd_env_supplies_timeouts_and_participant_values_still_win(self):
        self.assertEqual(self.import_settings(participant="AZURE_ENV_NAME=offline\nLIVEWELL_TIMEOUT=7\n",
                                             azd="LIVEWELL_TIMEOUT=11\nLIVEWELL_FABRIC_TIMEOUT=13\n"), (7.0, 13.0))

    def test_shell_timeout_overrides_still_win(self):
        self.assertEqual(self.import_settings(participant="LIVEWELL_TIMEOUT=7\nLIVEWELL_FABRIC_TIMEOUT=9\n",
                                             shell={"LIVEWELL_TIMEOUT": "17", "LIVEWELL_FABRIC_TIMEOUT": "19"}),
                         (17.0, 19.0))


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.agents.list.return_value = [NS(name="livewell-test-coach"), NS(name="livewell-demo-coach")]
        self.client.beta.memory_stores.list.return_value = []
        self.patches = [
            patch.object(lw, "project", return_value=self.client),
            patch.object(lw, "say"),
            patch.object(lw, "CREATED", set()),
            patch.object(lw, "CREATED_STORES", set()),
            patch.dict(os.environ, {"INITIALS": "test"}),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_unsupported_memory_does_not_prevent_agent_cleanup(self):
        for status in (404, 405, 501):
            with self.subTest(status=status):
                self.client.beta.memory_stores.list.side_effect = api_error(status)
                deleted = lw.cleanup(everything=True)
                self.assertEqual(deleted, ["livewell-test-coach"])
                self.client.agents.delete.assert_called_with("livewell-test-coach")
                self.assertIn("NOT VERIFIED", lw.say.call_args_list[-2].args[0])

    def test_validator_marks_unsupported_memory_as_unverified(self):
        self.client.beta.memory_stores.list.side_effect = api_error(404)
        found, verified = validator.leftovers()
        self.assertEqual(found, ["livewell-test-coach"])
        self.assertFalse(verified)
        self.client.agents.delete.assert_called_once_with("livewell-test-coach")
        text = validator.report({}, [], [], "test", False, memory_verified=verified)
        self.assertIn("Memory cleanup: NOT VERIFIED", text)
        self.assertNotIn("Left behind after the run: nothing\n", text)

    def test_empty_memory_is_verified_not_unavailable(self):
        self.client.agents.list.return_value = []
        self.assertEqual(validator.leftovers(), ([], True))
        self.assertIn("Memory cleanup: verified", validator.report({}, [], [], "test", False))

    def test_core_validator_completes_and_persists_unverified_memory_status(self):
        self.client.agents.list.return_value = []
        self.client.beta.memory_stores.list.side_effect = api_error(404)
        checks = {name: True for lab, _, names, _ in validator.SIGNALS if lab == "lab0" for name in names}
        run = {"lab": "lab0", "exit": 0, "seconds": 1, "checks": checks}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.md"
            with (patch.object(sys, "argv", ["validate-builder-rail.py", "--labs", "0", "--report", str(path)]),
                  patch.object(validator, "run_lab", return_value=run), patch("builtins.print")):
                self.assertEqual(validator.main(), 0)
            self.assertIn("Memory cleanup: NOT VERIFIED", path.read_text(encoding="utf-8"))

    def test_permission_and_service_errors_are_not_hidden_after_agent_cleanup(self):
        for status in (401, 403, 429, 500):
            with self.subTest(status=status):
                self.client.beta.memory_stores.list.side_effect = api_error(status)
                with self.assertRaises(HttpResponseError):
                    validator.leftovers()
                self.client.agents.delete.assert_called_with("livewell-test-coach")

    def test_memory_and_agent_cleanup_never_delete_other_or_protected_names(self):
        self.client.beta.memory_stores.list.return_value = [
            NS(name="livewell-test-memory"), NS(name="livewell-demo-memory"), NS(name="livewell-other-memory")]
        found, verified = validator.leftovers()
        self.assertEqual(found, ["livewell-test-coach", "livewell-test-memory"])
        self.assertTrue(verified)
        self.client.agents.delete.assert_called_once_with("livewell-test-coach")
        self.client.beta.memory_stores.delete.assert_called_once_with("livewell-test-memory")
        self.client.beta.memory_stores.delete.reset_mock()
        self.assertEqual(lw.cleanup_memory_stores(["livewell-demo-memory", "livewell-other-memory"]), [])
        self.client.beta.memory_stores.delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
