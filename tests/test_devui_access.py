"""Offline tests for private launch links and the pinned DevUI browser-auth adapter."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import time
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from agent_framework_devui import DevServer
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "content" / "assets"))
from common import devui_access as access

SECRET = "offline-test-only-" + "x" * 32
ORIGIN = "https://workshop.example.invalid"


def ticket_from(link):
    return parse_qs(urlsplit(link).fragment)["access"][0]


class TicketTests(unittest.TestCase):
    def test_fragment_contains_ticket_not_backend_secret(self):
        link, expiry = access.issue_link(SECRET, ORIGIN, 600, now=1000)
        self.assertNotIn(SECRET, link)
        self.assertEqual(urlsplit(link).query, "")
        self.assertEqual(urlsplit(link).path, "/workshop")
        payload = access.verify_ticket(ticket_from(link), SECRET, ORIGIN, "launch", now=1001)
        self.assertEqual(payload["exp"], expiry)

    def test_expired_tampered_wrong_audience_and_wrong_purpose_fail(self):
        link, _ = access.issue_link(SECRET, ORIGIN, 600, now=1000)
        token = ticket_from(link)
        for value, key, origin, kind, now in (
            (token, SECRET, ORIGIN, "launch", 1600),
            (token + "x", SECRET, ORIGIN, "launch", 1001),
            (token, SECRET + "rotated", ORIGIN, "launch", 1001),
            (token, SECRET, "https://another.example.invalid", "launch", 1001),
            (token, SECRET, ORIGIN, "session", 1001),
            ("invalid", SECRET, ORIGIN, "launch", 1001),
        ):
            with self.subTest(kind=kind, now=now), self.assertRaises(access.InvalidTicket):
                access.verify_ticket(value, key, origin, kind, now=now)

    def test_unsafe_origins_and_unbounded_lifetimes_fail(self):
        for origin in ("http://example.invalid", "https://a:b@example.invalid", ORIGIN + "/path",
                       ORIGIN + "?key=x", ORIGIN + "#key=x"):
            with self.assertRaises(ValueError):
                access.issue_link(SECRET, origin, 600)
        for lifetime in (0, -1, 13 * 3600, True, 60.5):
            with self.assertRaises(ValueError):
                access.issue_link(SECRET, ORIGIN, lifetime)


class MiddlewareTests(unittest.TestCase):
    def setUp(self):
        self.server = DevServer(host="0.0.0.0", auth_enabled=True, auth_token=SECRET)
        app = self.server.get_app()

        @app.get("/test-stream")
        async def stream(request: Request):
            self.assertEqual(request.headers["authorization"], f"Bearer {SECRET}")
            async def events():
                yield "data: first\n\n"
                yield "data: last\n\n"
            return StreamingResponse(events(), media_type="text/event-stream")

        app.router.routes.insert(0, app.router.routes.pop())  # Test route must precede DevUI's catch-all UI mount.
        app.add_middleware(access.WorkshopAccessMiddleware, secret=SECRET)
        self.client = TestClient(app, base_url=ORIGIN)
        self.addCleanup(self.client.close)

    def login(self, lifetime=600):
        link, expiry = access.issue_link(SECRET, ORIGIN, lifetime)
        response = self.client.post(access.SESSION_PATH, json={"ticket": ticket_from(link)},
                                    headers={"Origin": ORIGIN})
        return response, expiry

    def test_plain_link_is_help_page_not_native_token_form(self):
        response = self.client.get("/")
        self.assertEqual(str(response.url), ORIGIN + "/workshop")
        self.assertIn("No token entry or deployment is needed", response.text)
        self.assertIn("history.replaceState", response.text)
        self.assertNotIn(SECRET, response.text)
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        self.assertEqual(self.client.get("/meta").status_code, 401)
        self.assertEqual(self.client.get("/v1/entities").status_code, 401)

    def test_first_visit_sets_http_only_cookie_and_skips_frontend_gate(self):
        response, expiry = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["default_workflow"], access.DEFAULT_WORKFLOW)
        cookie = response.headers["set-cookie"]
        for flag in ("HttpOnly", "Secure", "SameSite=strict", "Path=/"):
            self.assertIn(flag, cookie)
        self.assertNotIn(SECRET, cookie)
        payload = access.verify_ticket(self.client.cookies[access.COOKIE], SECRET, ORIGIN, "session")
        self.assertEqual(payload["exp"], expiry)
        metadata = self.client.get("/meta")
        self.assertEqual(metadata.status_code, 200)
        self.assertFalse(metadata.json()["auth_required"])
        self.assertFalse(metadata.json()["capabilities"]["deployment"])
        self.assertNotIn(SECRET, metadata.text)
        self.assertEqual(metadata.headers["cache-control"], "no-store")
        self.assertEqual(self.client.get("/v1/entities").status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_invalid_or_expired_link_does_not_set_cookie(self):
        with mock.patch.object(access.time, "time", return_value=1000):
            link, _ = access.issue_link(SECRET, ORIGIN, 1)
        response = self.client.post(access.SESSION_PATH, json={"ticket": ticket_from(link)},
                                    headers={"Origin": ORIGIN})
        self.assertEqual(response.status_code, 401)
        self.assertIn("expired", response.json()["detail"])
        self.assertNotIn("set-cookie", response.headers)

    def test_session_expires_without_extending_the_link(self):
        _, expiry = self.login()
        with mock.patch.object(access.time, "time", return_value=expiry):
            self.assertEqual(self.client.get("/meta").status_code, 401)
            self.assertEqual(self.client.get("/v1/entities").status_code, 401)
            self.assertEqual(str(self.client.get("/").url), ORIGIN + "/workshop")

    def test_cross_origin_exchange_and_writes_are_refused(self):
        link, _ = access.issue_link(SECRET, ORIGIN, 600)
        for origin in ("https://attacker.example.invalid", "null", ""):
            response = self.client.post(access.SESSION_PATH, json={"ticket": ticket_from(link)},
                                        headers={"Origin": origin})
            self.assertEqual(response.status_code, 403)
        self.login()
        self.assertEqual(self.client.post("/v1/conversations", json={}).status_code, 403)
        self.assertEqual(self.client.post("/v1/conversations", json={},
                                         headers={"Origin": "https://attacker.example.invalid"}).status_code, 403)

    def test_admin_operations_and_proxy_are_not_participant_actions(self):
        self.login()
        for path in ("/v1/deployments", "/v1/entities/example/deploy", "/v1/entities/example/reload"):
            self.assertEqual(self.client.post(path, headers={"Origin": ORIGIN}).status_code, 403)
        self.assertEqual(self.client.get("/v1/entities", headers={"X-Proxy-Backend": "openai"}).status_code, 403)

    def test_conversations_and_streaming_keep_working_with_cookie_auth(self):
        self.login()
        response = self.client.post("/v1/conversations", json={"metadata": {"lab": "test"}},
                                    headers={"Origin": ORIGIN})
        self.assertEqual(response.status_code, 200)
        with self.client.stream("GET", "/test-stream") as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/event-stream", response.headers["content-type"])
            self.assertEqual("".join(response.iter_text()), "data: first\n\ndata: last\n\n")

    def test_old_browser_token_is_overridden_only_after_cookie_validation(self):
        self.assertEqual(self.client.get("/meta", headers={"Authorization": "Bearer stale"}).status_code, 401)
        self.login()
        self.assertEqual(self.client.get("/meta", headers={"Authorization": "Bearer stale"}).status_code, 200)

    def test_operator_bearer_still_requires_the_server_secret(self):
        response = self.client.get("/meta", headers={"Authorization": f"Bearer {SECRET}"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["auth_required"])

    def test_oversized_exchange_is_refused(self):
        response = self.client.post(access.SESSION_PATH, json={"ticket": "a" * 4096}, headers={"Origin": ORIGIN})
        self.assertEqual(response.status_code, 413)


class PackagingTests(unittest.TestCase):
    def test_adapter_is_in_the_image_staging_manifest(self):
        text = (ROOT / "scripts" / "stage-devui.py").read_text(encoding="utf-8")
        self.assertIn('"content/assets/common/devui_access.py"', text)

    def test_values_sheet_never_prints_server_secret(self):
        spec = importlib.util.spec_from_file_location("values_devui_test", ROOT / "scripts" / "render-values.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        captured = []
        with mock.patch.object(module, "read_env", return_value={
            "LAB4_DEVUI_URL": ORIGIN, "LIVEWELL_DEVUI_TOKEN": SECRET}), \
                mock.patch.object(sys, "argv", ["render-values.py", "mcaps"]), \
                mock.patch.object(Path, "write_text", side_effect=lambda text, **_: captured.append(text)), \
                mock.patch("builtins.print"):
            self.assertEqual(module.main(), 0)
        self.assertNotIn(SECRET, captured[0])
        self.assertIn("/workshop#access=", captured[0])
        self.assertIn("Lab 4 access expires", captured[0])


if __name__ == "__main__":
    unittest.main()
