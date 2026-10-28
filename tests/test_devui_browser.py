"""Opt-in browser check against the actual pinned DevUI, with no Azure/model calls.

    Set LIVEWELL_BROWSER_TESTS=1, then python -m unittest tests.test_devui_browser

Requires requirements-demos.txt and installed Microsoft Edge. All HTTPS requests are fulfilled from an
in-process test app; no local service is left running.
"""
import os
import re
import time
import unittest

from agent_framework import Message, WorkflowBuilder, WorkflowContext, executor
from agent_framework_devui import DevServer
from playwright.sync_api import sync_playwright
from starlette.testclient import TestClient

from tests.test_devui_access import ORIGIN, SECRET, access


@executor(id="coach")
async def offline_coach(messages: list[Message], ctx: WorkflowContext[list[Message]]) -> None:
    await ctx.yield_output([Message(role="assistant", text="Offline fixture; no model was invoked.")])


@unittest.skipUnless(os.environ.get("LIVEWELL_BROWSER_TESTS") == "1", "opt-in Microsoft Edge browser check")
class FirstVisitBrowserTests(unittest.TestCase):
    def test_fresh_browser_opens_prepared_graph_without_token_entry(self):
        workflow = WorkflowBuilder(start_executor=offline_coach, name=access.DEFAULT_WORKFLOW).build()
        server = DevServer(host="0.0.0.0", auth_enabled=True, auth_token=SECRET)
        server.set_pending_entities([workflow])
        app = server.get_app()
        app.add_middleware(access.WorkshopAccessMiddleware, secret=SECRET)
        link, _ = access.issue_link(SECRET, ORIGIN, 600)
        with TestClient(app, base_url=ORIGIN) as client, sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context()
            page = context.new_page()
            def handle(route):
                request = route.request
                headers = {k: v for k, v in request.headers.items() if k not in ("content-length", "host")}
                client.cookies.clear()
                response = client.request(request.method, request.url, content=request.post_data_buffer,
                                          headers=headers, follow_redirects=False)
                response_headers = {k: v for k, v in response.headers.items()
                                    if k not in ("content-encoding", "content-length", "transfer-encoding")}
                route.fulfill(status=response.status_code, headers=response_headers, body=response.content)
            page.route(ORIGIN + "/**", handle)
            try:
                page.goto(ORIGIN + "/workshop")
                page.get_by_text("Open the complete private link", exact=False).wait_for()
                expired, _ = access.issue_link(SECRET, ORIGIN, 30, now=int(time.time()) - 60)
                page.goto(expired)
                page.get_by_text("Workshop access has expired", exact=False).wait_for()
                page.goto(link)
                page.wait_for_url(re.compile(r".*\?entity_id=workflow_.*"), timeout=30000)
                page.get_by_text(access.DEFAULT_WORKFLOW, exact=True).first.wait_for(timeout=15000)
                self.assertEqual(page.get_by_text("Enter Authentication Token", exact=False).count(), 0)
                self.assertIsNone(page.evaluate("localStorage.getItem('devui_auth_token')"))
                self.assertNotIn(SECRET, page.content())
                self.assertNotIn("access=", page.url)
                self.assertNotIn(access.COOKIE, page.evaluate("document.cookie"))
                cookie = next(c for c in context.cookies() if c["name"] == access.COOKIE)
                self.assertTrue(cookie["httpOnly"])
                self.assertTrue(cookie["secure"])
                page.reload()
                page.get_by_text(access.DEFAULT_WORKFLOW, exact=True).first.wait_for(timeout=15000)
            finally:
                context.close()
                browser.close()


if __name__ == "__main__":
    unittest.main()
