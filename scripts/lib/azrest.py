"""Tiny REST helper for workshop scripts: one `az account get-access-token` per API, then urllib.

Much faster than one `az rest` process per call when seeding 20+ users. Standard library only.

    from azrest import Api
    arm = Api("arm"); graph = Api("graph"); fabric = Api("fabric")
    arm.get("/subscriptions/<sub>/resourceGroups?api-version=2021-04-01")

Tenant safety: when a tenant is known (the `tenant` argument or AZURE_TENANT_ID, which the scripts export from
workshop.yaml) the token is requested for THAT tenant, and its `tid` claim is checked, so a call can never go to
a different tenant than the one the environment is configured for.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request

TOKEN_TIMEOUT = 90


def run_az(args: list[str], timeout: int = TOKEN_TIMEOUT) -> subprocess.CompletedProcess:
    """Run `az <args>` with no stdin and a hard timeout that also kills az's child processes. (On Windows az is a
    .cmd wrapper: a plain subprocess timeout kills only the wrapper and then waits forever for the real process,
    which is what happens when a token request is silently waiting for an interactive sign-in.)"""
    az = shutil.which("az") or "az"
    proc = subprocess.Popen([az, *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.kill()
        proc.communicate()
        raise
    return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)

RESOURCES = {
    "arm": ("https://management.azure.com", "https://management.azure.com"),
    "graph": ("https://graph.microsoft.com", "https://graph.microsoft.com"),
    "fabric": ("https://api.fabric.microsoft.com", "https://api.fabric.microsoft.com"),
}


class ApiError(RuntimeError):
    def __init__(self, status: int, body: str, url: str):
        super().__init__(f"HTTP {status} {url}: {body[:400]}")
        self.status = status
        self.body = body
        try:
            self.code = (json.loads(body).get("error") or {}).get("code", "") if body else ""
        except (ValueError, AttributeError):
            self.code = ""


def jwt_claims(token: str) -> dict:
    """Payload of a JWT, unverified: used only to see which tenant a token was issued for."""
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part))
    except (IndexError, ValueError):
        return {}


def token_tenant(token: str) -> str:
    return str(jwt_claims(token).get("tid", ""))


def az_token(resource: str, tenant: str | None = None, subscription: str | None = None) -> str:
    """Token for `resource`. When a subscription is known it is used to pick the account and tenant (az selects the
    signed-in account that owns that subscription, silently); `--tenant` alone uses the ACTIVE account against that
    tenant, which can wait for an interactive sign-in when the active account belongs elsewhere."""
    cmd = ["account", "get-access-token", "--resource", resource, "--query", "accessToken", "-o", "tsv"]
    if subscription:
        cmd += ["--subscription", subscription]
    elif tenant:
        cmd += ["--tenant", tenant]
    hint = (f"az account set --subscription {subscription}" if subscription
            else f"az login --tenant {tenant or '<tenant-id>'}")
    try:
        proc = run_az(cmd)
    except subprocess.TimeoutExpired:
        raise SystemExit(f"az account get-access-token --resource {resource} did not finish in {TOKEN_TIMEOUT}s "
                         f"(an interactive sign-in is probably pending, or the active account belongs to another tenant). "
                         f"Run: {hint}") from None
    if proc.returncode != 0:
        raise SystemExit(f"az account get-access-token --resource {resource} failed: {proc.stderr.strip()[:300]}")
    token = proc.stdout.strip()
    if tenant and token_tenant(token).lower() != tenant.lower():
        raise SystemExit(f"the {resource} token is for tenant {token_tenant(token) or '?'}, expected {tenant}: "
                         f"refusing to call. Run: {hint}")
    return token


class Api:
    def __init__(self, kind: str, tenant: str | None = None, subscription: str | None = None):
        self.base, resource = RESOURCES[kind]
        self.token = az_token(resource, tenant or os.environ.get("AZURE_TENANT_ID") or None,
                              subscription or os.environ.get("AZURE_SUBSCRIPTION_ID") or None)

    def call(self, method: str, path: str, body: object | None = None, ok_404: bool = False,
             headers: dict | None = None) -> dict | None:
        url = path if path.startswith("http") else self.base + path
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(6):
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header("Authorization", f"Bearer {self.token}")
            req.add_header("Content-Type", "application/json")
            for k, v in (headers or {}).items():
                req.add_header(k, v)
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    raw = resp.read().decode("utf-8", "replace")
                    return json.loads(raw) if raw.strip() else {}
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", "replace")
                if e.code == 404 and ok_404:
                    return None
                if e.code in (429, 500, 502, 503, 504) and attempt < 5:
                    time.sleep(int(e.headers.get("Retry-After", "0") or 0) or 2 ** attempt)
                    continue
                raise ApiError(e.code, raw, url) from None
        return None

    def get(self, path: str, ok_404: bool = False):
        return self.call("GET", path, ok_404=ok_404)

    def get_all(self, path: str) -> list:
        """Follow nextLink / @odata.nextLink / continuationUri."""
        items, url = [], path
        while url:
            page = self.get(url) or {}
            items += page.get("value", [])
            url = page.get("nextLink") or page.get("@odata.nextLink") or page.get("continuationUri")
        return items

    def put(self, path: str, body: object):
        return self.call("PUT", path, body)

    def post(self, path: str, body: object | None = None):
        return self.call("POST", path, body if body is not None else {})

    def patch(self, path: str, body: object):
        return self.call("PATCH", path, body)

    def delete(self, path: str):
        return self.call("DELETE", path, ok_404=True)
