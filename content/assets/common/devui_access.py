"""Expiring private links for the shared workshop DevUI; no backend secret in the browser."""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

COOKIE = "__Host-livewell-devui"
LAUNCH_PATH = "/workshop"
SESSION_PATH = "/workshop/session"
MAX_LIFETIME = 12 * 60 * 60
MAX_TICKET_BYTES = 2048
DEFAULT_WORKFLOW = "LiveWell sequential"


class InvalidTicket(ValueError):
    pass


def origin_of(url: str) -> str:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("DevUI needs its HTTPS root URL, without credentials, path, query or fragment.")
    return f"https://{parsed.netloc.lower()}"


def _encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decoded(value: str) -> bytes:
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


def _sign(payload: dict, secret: str) -> str:
    if len(secret) < 24:
        raise ValueError("The DevUI backend secret must be at least 24 characters.")
    data = _encoded(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), b"livewell-devui-v1:" + data.encode("ascii"),
                         hashlib.sha256).digest()
    return f"{data}.{_encoded(signature)}"


def issue_link(secret: str, origin: str, lifetime_seconds: int, *, now: int | None = None) -> tuple[str, int]:
    if type(lifetime_seconds) is not int or not 1 <= lifetime_seconds <= MAX_LIFETIME:
        raise ValueError("DevUI launch-link lifetime must be between one second and twelve hours.")
    issued = int(time.time()) if now is None else now
    origin = origin_of(origin)
    expiry = issued + lifetime_seconds
    ticket = _sign({"v": 1, "kind": "launch", "aud": origin, "iat": issued, "exp": expiry,
                    "nonce": secrets.token_hex(16)}, secret)
    return f"{origin}{LAUNCH_PATH}#access={ticket}", expiry


def verify_ticket(ticket: str, secret: str, origin: str, kind: str, *, now: int | None = None) -> dict:
    if not isinstance(ticket, str) or not ticket or len(ticket) > MAX_TICKET_BYTES:
        raise InvalidTicket("Missing or invalid private workshop link.")
    try:
        data, signature = ticket.split(".")
        expected = hmac.new(secret.encode("utf-8"), b"livewell-devui-v1:" + data.encode("ascii"),
                            hashlib.sha256).digest()
        if not hmac.compare_digest(_decoded(signature), expected):
            raise InvalidTicket("Invalid private workshop link.")
        payload = json.loads(_decoded(data))
    except (ValueError, UnicodeError, binascii.Error) as error:
        raise InvalidTicket("Invalid private workshop link.") from error
    current = int(time.time()) if now is None else now
    if (not isinstance(payload, dict) or payload.get("v") != 1 or payload.get("kind") != kind
            or payload.get("aud") != origin or type(payload.get("iat")) is not int
            or type(payload.get("exp")) is not int or not isinstance(payload.get("nonce"), str)
            or not 0 < payload["exp"] - payload["iat"] <= MAX_LIFETIME
            or payload["iat"] > current + 30):
        raise InvalidTicket("Invalid private workshop link.")
    if payload["exp"] <= current:
        raise InvalidTicket("Workshop access has expired. Ask the facilitator for a fresh private link.")
    return payload


LAUNCH_SCRIPT = """
const status = document.getElementById("status");
async function openDemo() {
  const ticket = new URLSearchParams(location.hash.slice(1)).get("access");
  history.replaceState(null, "", "/workshop");
  if (!ticket) {
    status.textContent = "Open the complete private link from your facilitator. No token entry or deployment is needed.";
    return;
  }
  const response = await fetch("/workshop/session", {
    method: "POST", credentials: "same-origin", cache: "no-store",
    headers: {"Content-Type": "application/json"}, body: JSON.stringify({ticket})
  });
  const session = await response.json();
  if (!response.ok) throw new Error(session.detail || "Workshop access could not be established.");
  localStorage.removeItem("devui_auth_token");
  const entitiesResponse = await fetch("/v1/entities", {credentials: "same-origin", cache: "no-store"});
  if (!entitiesResponse.ok) throw new Error("The shared demo is unavailable. Tell the facilitator.");
  const {entities} = await entitiesResponse.json();
  const selected = entities.find(entity => entity.name === session.default_workflow && entity.type === "workflow");
  if (!selected) throw new Error("The prepared workflow is missing. Tell the facilitator; do not deploy an agent.");
  location.replace("/?entity_id=" + encodeURIComponent(selected.id));
}
function launch() {
  openDemo().catch(error => {
    status.textContent = error.message + " Ask the facilitator for help; do not paste a token.";
  });
}
window.addEventListener("hashchange", launch);
launch();
"""

LAUNCH_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>LiveWell workshop access</title>
<style>body{font:18px system-ui;max-width:640px;margin:12vh auto;padding:24px;color:#14314a}
h1{font-size:30px}p{line-height:1.6}.note{font-size:15px;color:#455868}</style></head>
<body><h1>LiveWell multi-agent demo</h1><p id="status" role="status">Opening the prepared workflow...</p>
<p class="note">Browser only. Nothing to install or deploy. This private link expires and must not be shared publicly.</p>
<noscript>Enable JavaScript to open the workshop demo, or watch the facilitator's screen.</noscript>
<script>""" + LAUNCH_SCRIPT + "</script></body></html>"


class WorkshopAccessMiddleware:
    """Cookie-to-bearer adapter outside DevUI's existing auth; preserves streaming bodies."""

    def __init__(self, app: ASGIApp, secret: str):
        if len(secret) < 24:
            raise ValueError("The DevUI backend secret must be at least 24 characters.")
        self.app, self.secret = app, secret

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        from starlette.requests import Request
        from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

        request = Request(scope, receive)
        path, method = scope["path"], scope["method"]
        private_headers = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                           "X-Content-Type-Options": "nosniff"}
        try:
            origin = origin_of("https://" + request.headers.get("host", ""))
        except ValueError:
            await JSONResponse({"detail": "Invalid host."}, status_code=400)(scope, receive, send)
            return
        session = None
        if cookie := request.cookies.get(COOKIE):
            try:
                session = verify_ticket(cookie, self.secret, origin, "session")
            except InvalidTicket:
                session = None

        if path == LAUNCH_PATH and method == "GET":
            script_hash = base64.b64encode(hashlib.sha256(LAUNCH_SCRIPT.encode("utf-8")).digest()).decode("ascii")
            headers = {**private_headers, "Content-Security-Policy":
                       f"default-src 'none'; script-src 'sha256-{script_hash}'; style-src 'unsafe-inline'; "
                       "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"}
            await HTMLResponse(LAUNCH_HTML, headers=headers)(scope, receive, send)
            return

        if path == SESSION_PATH:
            if (method != "POST" or request.headers.get("origin") != origin
                    or request.headers.get("content-type", "").split(";")[0] != "application/json"):
                await JSONResponse({"detail": "Use the private workshop link from this site."}, status_code=403,
                                   headers=private_headers)(scope, receive, send)
                return
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > MAX_TICKET_BYTES:
                    await JSONResponse({"detail": "Invalid workshop request."}, status_code=413,
                                       headers=private_headers)(scope, receive, send)
                    return
            try:
                data = json.loads(body)
                if not isinstance(data, dict):
                    raise InvalidTicket("Invalid workshop request.")
                payload = verify_ticket(data.get("ticket", ""), self.secret, origin, "launch")
            except (InvalidTicket, ValueError, UnicodeError) as error:
                detail = str(error) if isinstance(error, InvalidTicket) else "Invalid workshop request."
                await JSONResponse({"detail": detail}, status_code=401,
                                   headers=private_headers)(scope, receive, send)
                return
            session_ticket = _sign({**payload, "kind": "session", "nonce": secrets.token_hex(16)}, self.secret)
            response = JSONResponse({"default_workflow": DEFAULT_WORKFLOW}, headers=private_headers)
            response.set_cookie(COOKIE, session_ticket, max_age=payload["exp"] - int(time.time()),
                                httponly=True, secure=True, samesite="strict", path="/")
            await response(scope, receive, send)
            return

        if path == "/health":
            await self.app(scope, receive, send)
            return

        if session is None:
            # Existing explicit bearer clients remain supported; a plain browser never reaches the token form.
            if not request.headers.get("authorization"):
                response = (RedirectResponse(LAUNCH_PATH, status_code=303, headers=private_headers)
                            if path == "/" else JSONResponse(
                                {"detail": "Workshop access is missing or expired. Reopen the private link."},
                                status_code=401, headers=private_headers))
                await response(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return

        if method not in ("GET", "HEAD") and request.headers.get("origin") != origin:
            await JSONResponse({"detail": "Cross-origin workshop request refused."}, status_code=403,
                               headers=private_headers)(scope, receive, send)
            return
        if (path.startswith("/v1/deployments") or path.endswith(("/deploy", "/reload"))
                or request.headers.get("x-proxy-backend")):
            await JSONResponse({"detail": "Deployment, reload and model proxy are not participant actions."},
                               status_code=403, headers=private_headers)(scope, receive, send)
            return

        forwarded = dict(scope)
        forwarded["headers"] = [(k, v) for k, v in scope["headers"] if k.lower() != b"authorization"]
        forwarded["headers"].append((b"authorization", f"Bearer {self.secret}".encode("ascii")))
        metadata = bytearray()
        meta_start = None

        async def authenticated_send(message):
            nonlocal meta_start
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message["headers"]
                           if k.lower() not in (b"cache-control", b"referrer-policy")]
                message = {**message, "headers": headers + [(k.lower().encode(), v.encode())
                                                           for k, v in private_headers.items()]}
                if path == "/meta" and message["status"] == 200:
                    meta_start = message
                    return
            if meta_start is not None and message["type"] == "http.response.body":
                metadata.extend(message.get("body", b""))
                if not message.get("more_body", False):
                    value = json.loads(metadata)
                    value["auth_required"] = False  # Cookie already validated; the backend still requires its bearer.
                    value["capabilities"] = {**value.get("capabilities", {}), "deployment": False, "openai_proxy": False}
                    content = json.dumps(value).encode("utf-8")
                    headers = [(k, v) for k, v in meta_start["headers"] if k.lower() != b"content-length"]
                    await send({**meta_start, "headers": headers + [(b"content-length", str(len(content)).encode())]})
                    await send({**message, "body": content})
                return
            await send(message)

        await self.app(forwarded, receive, authenticated_send)
