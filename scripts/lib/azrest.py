"""Tiny REST helper for workshop scripts: one `az account get-access-token` per API, then urllib.

Much faster than one `az rest` process per call when seeding 20+ users. Standard library only.

    from azrest import Api
    arm = Api("arm"); graph = Api("graph"); fabric = Api("fabric")
    arm.get("/subscriptions/<sub>/resourceGroups?api-version=2021-04-01")
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request

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


def az_token(resource: str, tenant: str | None = None, *, subscription: str | None = None) -> str:
    az = shutil.which("az") or "az"
    cmd = [az, "account", "get-access-token", "--resource", resource, "--query", "accessToken", "-o", "tsv"]
    subscription = subscription or os.environ.get("AZURE_SUBSCRIPTION_ID")
    if subscription:
        cmd += ["--subscription", subscription]
    elif tenant:
        cmd += ["--tenant", tenant]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"az account get-access-token --resource {resource} failed: {proc.stderr.strip()[:300]}")
    return proc.stdout.strip()


class Api:
    def __init__(self, kind: str, tenant: str | None = None, *, subscription: str | None = None):
        self.base, resource = RESOURCES[kind]
        self.token = az_token(resource, tenant or os.environ.get("AZURE_TENANT_ID") or None, subscription=subscription)

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
