"""LiveWell Coach workshop: the one helper that calls Foundry (Builder rail).

Every lab script in content/assets/ imports from here, so Foundry calls, names and safety rails live in
one place.

* Settings come from content/assets/.env (participants copy FOUNDRY_PROJECT_ENDPOINT from the values
  sheet and set INITIALS; see .env.sample) or, for facilitators and scripts/validate-builder-rail.py,
  from the selected azd environment (.azure/<env>/.env).
* Everything else is discovered from the project connections named in content/config/workshop.yaml:
  the knowledge-base MCP URL, the activities MCP URL, the Fabric IQ connection and the Foundry account
  ID (for the RAI policy resource ID). No endpoint, subscription or tenant ID is hard-coded.
* Agents are named livewell-<INITIALS>-<role>. cleanup() only deletes that prefix and never touches
  livewell-demo-* or livewell-workshop-* (facilitator agents).
* Carries over the CasePal fixes: strict-mode schema auto-fix, exponential-backoff retry on transient
  429/5xx/timeouts, and the in-band consent line for scripted runs.
* Printed output is ASCII-only because Windows consoles choke on emoji. Use say() instead of print().
"""
from __future__ import annotations

import argparse
import copy
import functools
import json
import os
import pathlib
import random
import re
import sys
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable

HERE = pathlib.Path(__file__).resolve()
ASSETS = HERE.parents[1]
CONTENT = HERE.parents[2]
ROOT = HERE.parents[3]
ENV_FILE = ASSETS / ".env"
RUNS_DIR = ASSETS / ".runs"
PROMPTS_FILE = CONTENT / "prompts" / "test-prompts.json"
INSTRUCTIONS_FILE = CONTENT / "prompts" / "coach-instructions.md"
CITIZENS_FILE = CONTENT / "data" / "citizens.json"
GUIDES_DIR = CONTENT / "knowledge" / "livewell-guides"
WORKSHOP_YAML = CONTENT / "config" / "workshop.yaml"
EVAL_FILE = CONTENT / "eval" / "livewell-eval.jsonl"

RESPONSE_TIMEOUT = float(os.environ.get("LIVEWELL_TIMEOUT", "180"))
FABRIC_TIMEOUT = float(os.environ.get("LIVEWELL_FABRIC_TIMEOUT", "300"))
KB_LABEL = "livewell_guides"
ACTIVITIES_LABEL = "livewell_activities"
FABRIC_LABEL = "resident360"
DEFAULT_RAI_POLICY = "Microsoft.DefaultV2"


# ---------------------------------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------------------------------
def _read_env_file(path: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, value = line.split("=", 1)
        value = value.strip()
        if value[:1] and value[0] in "\"'":
            value = value[1:].split(value[0], 1)[0]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()
        out[key.strip()] = value
    return out


def _azd_env_name() -> str:
    if os.environ.get("AZURE_ENV_NAME"):
        return os.environ["AZURE_ENV_NAME"]
    cfg = ROOT / ".azure" / "config.json"
    try:
        return json.loads(cfg.read_text(encoding="utf-8")).get("defaultEnvironment", "")
    except Exception:
        return ""


def load_settings() -> None:
    """content/assets/.env first; the azd env file only fills what is still missing."""
    for key, value in _read_env_file(ENV_FILE).items():
        os.environ.setdefault(key, value)
    env = _azd_env_name()
    if env:
        for key, value in _read_env_file(ROOT / ".azure" / env / ".env").items():
            os.environ.setdefault(key, value)


load_settings()


@functools.lru_cache(maxsize=1)
def config() -> dict:
    import yaml

    return yaml.safe_load(WORKSHOP_YAML.read_text(encoding="utf-8"))


NAMES: dict = config()["names"]
MODELS: dict = config()["models"]
NAMING: dict = config()["workshop"]["agent_naming"]
# Two chat deployments (workshop.yaml models, ASSUMPTIONS.md 9.1). DEFAULT_MODEL (gpt-5-mini) runs Labs 0-2, the
# specialists, the memory store and Lab 4. TOOLS_MODEL (gpt-4.1-mini) runs every agent with OpenAPI, A2A, Fabric
# Data Agent or function tools (the Lab 3 coach on), because the agent service does not support those tools on
# gpt-5-mini; it is also the evaluation judge.
DEFAULT_MODEL: str = os.environ.get("LIVEWELL_MODEL") or MODELS["default"]
TOOLS_MODEL: str = os.environ.get("LIVEWELL_TOOLS_MODEL") or MODELS["tools"]
JUDGE_MODEL: str = TOOLS_MODEL  # non-reasoning, so evaluators need no is_reasoning_model flag
REASONING_EFFORT: dict = MODELS.get("reasoning_effort") or {}


def reasoning(model: str):
    """The workshop's reasoning effort for a deployment (gpt-5-mini: low), or None for non-reasoning models."""
    if model not in REASONING_EFFORT:
        return None
    return models().Reasoning(effort=os.environ.get("LIVEWELL_REASONING_EFFORT") or REASONING_EFFORT[model])


def fabric_enabled(flag: bool = False) -> bool:
    return flag or os.environ.get("FABRIC_BRIDGE", "").strip().lower() in ("1", "true", "yes")


def initials() -> str:
    raw = os.environ.get("INITIALS", "").strip().lower()
    if not raw:
        raise SystemExit("Set INITIALS first (2-8 letters or digits, your own): add INITIALS=<yours> to "
                         "content/assets/.env (copy .env.sample), or prefix one run with INITIALS=<yours>.")
    if not re.fullmatch(r"[a-z0-9]{2,8}", raw):
        raise SystemExit(f"INITIALS={raw!r} must be 2-8 letters or digits.")
    if raw in ("demo", "workshop"):
        raise SystemExit("INITIALS 'demo' and 'workshop' are reserved for facilitator agents.")
    return raw


def agent_name(role: str) -> str:
    return f"livewell-{initials()}-{role}"


def is_protected(name: str) -> bool:
    return any(name.startswith(p) for p in NAMING["protected_prefixes"])


def lab_args(description: str, extra: Callable[[argparse.ArgumentParser], None] | None = None):
    """--verbose / --cleanup (+ lab-specific flags). Unknown args are ignored so cells also run in a
    VS Code / Jupyter kernel, where sys.argv holds the kernel's own flags. VERBOSE=1 also works there."""
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--verbose", action="store_true", help="print tool calls, outputs and response IDs")
    ap.add_argument("--cleanup", action="store_true",
                    help="delete the livewell-<INITIALS>-* agents this script created when it finishes")
    if extra:
        extra(ap)
    in_kernel = "ipykernel" in sys.modules
    args, _ = ap.parse_known_args([] if in_kernel else sys.argv[1:])
    args.verbose = args.verbose or os.environ.get("VERBOSE", "") == "1"
    initials()
    return args


# ---------------------------------------------------------------------------------------------------
# ASCII-only output
# ---------------------------------------------------------------------------------------------------
_ASCII = {
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u2011": "-",
    "\u2212": "-", "\u2026": "...", "\u2022": "*", "\u00b7": "*", "\u00bd": "1/2", "\u00bc": "1/4",
    "\u00be": "3/4", "\u2265": ">=", "\u2264": "<=", "\u2192": "->", "\u2190": "<-", "\u00d7": "x",
    "\u00b0": " deg", "\u00a0": " ", "\u202f": " ", "\u2248": "~",
}
_CITE_MARK = re.compile("\u3010[^\u3011]*?\u2020([^\u3011]+)\u3011")


def ascii_safe(text: Any) -> str:
    # Knowledge-base citation markers look like 【4:0†lg-05-...】 or the generic 【4:0†source】; keep the id, drop the generic one.
    s = _CITE_MARK.sub(lambda m: "" if m.group(1).strip().lower() == "source" else f"[{m.group(1)}]", str(text))
    for k, v in _ASCII.items():
        s = s.replace(k, v)
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    return s.encode("ascii", "replace").decode("ascii")


def say(*parts: Any) -> None:
    print(ascii_safe(" ".join(str(p) for p in parts)), flush=True)


def show_json(obj: Any) -> None:
    say(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def heading(title: str) -> None:
    say("")
    say("=" * 78)
    say(title)
    say("=" * 78)


def _trunc(text: Any, n: int) -> str:
    s = str(text or "")
    return s if len(s) <= n else s[: n - 3] + "..."


# ---------------------------------------------------------------------------------------------------
# Prompt bank and instruction blocks (single source of truth: content/prompts/)
# ---------------------------------------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def prompt_bank() -> dict:
    return json.loads(PROMPTS_FILE.read_text(encoding="utf-8"))


CONSENT_LINE: str = prompt_bank()["consent_line"]
SESSION_RESIDENT_ID: str = prompt_bank()["session_resident_id"]


def prompt(prompt_id: str) -> dict:
    return prompt_bank()["prompts"][prompt_id]


def expected(prompt_id: str) -> dict:
    return prompt(prompt_id).get("expected", {})


_REPO_NOTE_RE = re.compile(r"\A(?:>.*\n)+\s*^---\s*$\n", re.M)


def attachment_text(ref: str) -> str:
    """An attachment as the model should see it: a leading repo-only note (blockquote lines, then a `---` rule,
    as in flyer-injected.md) is dropped, so scripts send the same text as the lab page's copy block."""
    raw = (ROOT / ref).read_text(encoding="utf-8")
    return _REPO_NOTE_RE.sub("", raw, count=1).strip()


def prompt_text(prompt_id: str, with_attachments: bool = True) -> str:
    p = prompt(prompt_id)
    text = p["text"]
    if with_attachments:
        for ref in p.get("attachments_ref", []):
            text += f"\n\n--- {pathlib.PurePosixPath(ref).name} ---\n{attachment_text(ref)}"
    return text


_BLOCK_RE = re.compile(r"```text name=(?P<name>[a-z0-9_-]+)\n(?P<body>.*?)\n```", re.S)


@functools.lru_cache(maxsize=1)
def _instruction_blocks() -> dict[str, str]:
    text = INSTRUCTIONS_FILE.read_text(encoding="utf-8")
    return {m.group("name"): m.group("body").strip() for m in _BLOCK_RE.finditer(text)}


def load_instructions(*names: str) -> str:
    blocks = _instruction_blocks()
    missing = [n for n in names if n not in blocks]
    if missing:
        raise KeyError(f"instruction block(s) {missing} not found in {INSTRUCTIONS_FILE.name}")
    return "\n\n".join(blocks[n] for n in names)


# ---------------------------------------------------------------------------------------------------
# Structured-output schemas (built from test-prompts.json structured_contracts)
# ---------------------------------------------------------------------------------------------------
def strict_schema(schema: dict) -> dict:
    """Strict mode needs additionalProperties=false and every property listed in required, on every
    object node. The SDK does not add them, so we do (the CasePal strict-mode fix, applied recursively)."""
    s = copy.deepcopy(schema)

    def fix(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                props = node.setdefault("properties", {})
                node["additionalProperties"] = False
                node["required"] = list(props.keys())
                for child in props.values():
                    fix(child)
            if "items" in node:
                fix(node["items"])
            for key in ("anyOf", "oneOf"):
                for child in node.get(key, []):
                    fix(child)

    fix(s)
    return s


def _contract(name: str) -> dict:
    return prompt_bank()["structured_contracts"][name]


def _strings() -> dict:
    return {"type": "array", "items": {"type": "string"}}


def _guides() -> dict:
    """Citations constrained to the real guide ids: strict structured output cannot invent a source."""
    ids = guide_ids()
    if not ids:  # an empty enum still validates, but then the model can only return []
        raise FileNotFoundError(f"no lg-*.md guides in {GUIDES_DIR}: copy content/knowledge/livewell-guides/ too")
    return {"type": "array", "items": {"type": "string", "enum": list(ids)}}


def lab1_schema() -> dict:
    enums = _contract("lab1_contract")["enums"]
    return strict_schema({"type": "object", "properties": {
        "answer": {"type": "string"},
        "intent": {"type": "string", "enum": enums["intent"]},
        "risk_level": {"type": "string", "enum": enums["risk_level"]},
        "route": {"type": "string", "enum": enums["route"]},
        "cited_sources": _guides(),
        "personalisation_flags": _strings(),
    }})


def intake_schema() -> dict:
    num, integer, text = {"type": ["number", "null"]}, {"type": ["integer", "null"]}, {"type": ["string", "null"]}
    c = _contract("intake_contract")
    types = {"screening_date": text, "bmi": num, "systolic_bp": integer, "diastolic_bp": integer,
             "fasting_glucose_mmol": num, "total_cholesterol_mmol": num,
             "risk_band": {"type": ["string", "null"], "enum": ["Low", "Moderate", "High", "Not Screened", None]},
             "days_logged": integer, "avg_daily_steps": num, "hazy_days_skipped": integer,
             "preferred_time_of_day": text, "dislikes": _strings()}
    return strict_schema({"type": "object", "properties": {
        "screening": {"type": "object", "properties": {f: types[f] for f in c["screening_fields"]}},
        "activity": {"type": "object", "properties": {f: types[f] for f in c["activity_fields"]}},
        "preferences": {"type": "object", "properties": {f: types[f] for f in c["preferences_fields"]}},
        "follow_up_flags": _strings(),
    }})


def evidence_schema() -> dict:
    enums = _contract("lab3_evidence_contract")["enums"]
    return strict_schema({"type": "object", "properties": {
        "advice": {"type": "string"},
        "confidence": {"type": "string", "enum": enums["confidence"]},
        "supporting_guides": _guides(),
        "rationale": {"type": "string"},
        "personalisation_flags": _strings(),
    }})


# ---------------------------------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------------------------------
def endpoint() -> str:
    ep = os.environ.get("FOUNDRY_PROJECT_ENDPOINT") or os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
    if not ep:
        raise SystemExit("Set FOUNDRY_PROJECT_ENDPOINT in content/assets/.env (copy .env.sample; the value is "
                         "the 'Project endpoint' row on the facilitator values sheet).")
    return ep.rstrip("/")


def managed_identity_client_id() -> str | None:
    """The user-assigned identity of the Lab 4 DevUI Container App (infra/modules/devui.bicep sets AZURE_CLIENT_ID;
    Container Apps sets IDENTITY_ENDPOINT). None on laptops and Codespaces, which sign in with az / azd."""
    if os.environ.get("IDENTITY_ENDPOINT") and os.environ.get("AZURE_CLIENT_ID"):
        return os.environ["AZURE_CLIENT_ID"]
    return None


@functools.lru_cache(maxsize=1)
def credential():
    from azure.identity import (AzureCliCredential, AzureDeveloperCliCredential, ChainedTokenCredential,
                                ManagedIdentityCredential)

    if client_id := managed_identity_client_id():
        return ManagedIdentityCredential(client_id=client_id)
    tenant = os.environ.get("AZURE_TENANT_ID") or None
    return ChainedTokenCredential(AzureCliCredential(tenant_id=tenant), AzureDeveloperCliCredential(tenant_id=tenant))


@functools.lru_cache(maxsize=1)
def project():
    from azure.ai.projects import AIProjectClient

    return AIProjectClient(endpoint=endpoint(), credential=credential(), allow_preview=True)


@functools.lru_cache(maxsize=1)
def _openai_base():
    return project().get_openai_client()


def openai_client(timeout: float | None = None, agent_name: str | None = None):
    # max_retries=0: _retry() below owns retries, so SDK retries do not multiply with ours.
    base = _openai_agent(agent_name) if agent_name else _openai_base()
    return base.with_options(timeout=timeout or RESPONSE_TIMEOUT, max_retries=0)


@functools.lru_cache(maxsize=4)
def _openai_agent(agent_name: str):
    """Hosted agents only answer on their own endpoint: {project}/agents/<name>/endpoint/protocols/openai."""
    return project().get_openai_client(agent_name=agent_name)


def is_hosted(agent: Any) -> bool:
    if isinstance(agent, str):
        return agent == NAMES["hosted_agent"]
    return str(getattr(getattr(getattr(agent, "definition", None), "kind", ""), "value",
                       getattr(getattr(agent, "definition", None), "kind", ""))).lower() == "hosted"


def models():
    import azure.ai.projects.models as m

    return m


_TRANSIENT = {408, 429, 500, 502, 503, 504}
RETRY_CAP = 60.0  # the longest wait we take from a retry-after header, in seconds
RETRY_JITTER = 0.25  # every wait gets up to 25% extra, so a room of participants does not retry in step


def _status(err: Exception) -> int | None:
    return getattr(err, "status_code", None) or getattr(getattr(err, "response", None), "status_code", None)


def _retry_hint(headers: Any) -> float | None:
    """Seconds the server asked us to wait: `retry-after-ms` first, then `retry-after` (seconds), else None."""
    try:
        lowered = {str(k).lower(): v for k, v in headers.items()}
    except Exception:
        return None
    for key, per_second in (("retry-after-ms", 1000.0), ("retry-after", 1.0)):
        try:
            seconds = float(lowered[key]) / per_second
        except (KeyError, TypeError, ValueError):
            continue
        if seconds > 0:
            return seconds
    return None


def retry_delay(attempt_index: int, base_delay: float = 2.0, headers: Any = None,
                rng: Callable[[], float] = random.random) -> float:
    """Seconds to wait before the next try (attempt_index counts from 0). The server's hint wins, capped at 60 s;
    without one, exponential backoff: base_delay * 2**attempt_index, at most 30 s. Every wait then gets 0-25%
    random jitter on top (never less), so 30 participants who hit the same 429 do not all retry together."""
    hint = _retry_hint(headers)
    wait = min(hint, RETRY_CAP) if hint else min(base_delay * 2 ** min(max(attempt_index, 0), 10), 30.0)
    return wait * (1.0 + RETRY_JITTER * min(max(rng(), 0.0), 1.0))


def _session_not_ready(err: Exception) -> bool:
    """A hosted agent's container is still starting after scale-to-zero (HTTP 424 session_not_ready)."""
    return _status(err) == 424 and "session_not_ready" in str(err)


def retry(fn: Callable[[], Any], *, what: str = "call", attempts: int = 5, retry_timeouts: bool = True) -> Any:
    """Exponential backoff (2, 4, 8, 16 s, plus 0-25% jitter; retry-after-ms and Retry-After win, see
    retry_delay) on 429, 5xx, timeouts and dropped connections, and at least 15 s between tries while a
    hosted agent's session starts (424 session_not_ready). Everything else, including guardrail blocks
    (400 content_filter), raises at once. retry_timeouts=False raises a timeout at once: the server may
    still be running the request, so a retry could repeat an approved write."""
    import openai
    from azure.core.exceptions import HttpResponseError, ServiceRequestError, ServiceResponseError

    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except openai.BadRequestError:
            raise
        except (openai.APITimeoutError, openai.APIConnectionError, ServiceRequestError, ServiceResponseError) as e:
            if not retry_timeouts and isinstance(e, openai.APITimeoutError):
                raise
            err: Exception = e
        except (openai.APIStatusError, HttpResponseError) as e:
            if _status(e) not in _TRANSIENT and not _session_not_ready(e):
                raise
            err = e
        if attempt == attempts:
            raise err
        wait = retry_delay(attempt - 1, 2.0, getattr(getattr(err, "response", None), "headers", None))
        if _session_not_ready(err):
            wait = max(wait, retry_delay(0, 15.0))  # at least 15 s while the hosted session starts
        say(f"   (transient {type(err).__name__} {_status(err) or ''} on {what}; retry {attempt}/{attempts - 1} in {wait:.0f}s)")
        time.sleep(wait)


# ---------------------------------------------------------------------------------------------------
# Project connections -> tool definitions
# ---------------------------------------------------------------------------------------------------
@functools.lru_cache(maxsize=None)
def connection(name: str):
    return retry(lambda: project().connections.get(name), what=f"connection {name}")


def account_id() -> str:
    """Foundry account resource ID, derived from a project connection's ID (no subscription constant)."""
    return connection(NAMES["search_connection"]).id.split("/projects/")[0]


def rai_policy_id(policy: str | None = None) -> str:
    """Agent rai_config needs the FULL policy resource ID; a bare name is rejected."""
    policy = policy or NAMES["rai_policy"]
    return policy if policy.startswith("/subscriptions/") else f"{account_id()}/raiPolicies/{policy}"


def kb_tool():
    """Foundry IQ knowledge base over its MCP endpoint, through the project connection (project MI auth)."""
    m, conn = models(), NAMES["kb_mcp_connection"]
    return m.MCPTool(server_label=KB_LABEL, server_url=connection(conn).target, require_approval="never",
                     allowed_tools=["knowledge_base_retrieve"], project_connection_id=conn)


def activities_tool(approve_writes: bool = True, read_only: bool = False):
    """Activities MCP server: find_activities runs freely; register_interest (a write) needs approval.
    read_only=True exposes only find_activities (for specialists that must never register anyone)."""
    m, conn = models(), NAMES["mcp_connection"]
    if read_only:
        return m.MCPTool(server_label=ACTIVITIES_LABEL, server_url=connection(conn).target, project_connection_id=conn,
                         require_approval="never", allowed_tools=["find_activities"])
    approval: Any = "never"
    if approve_writes:
        approval = m.MCPToolRequireApproval(never=m.MCPToolFilter(tool_names=["find_activities"]),
                                            always=m.MCPToolFilter(tool_names=["register_interest"]))
    return m.MCPTool(server_label=ACTIVITIES_LABEL, server_url=connection(conn).target, project_connection_id=conn,
                     require_approval=approval, allowed_tools=["find_activities", "register_interest"])


def warm_activities() -> threading.Thread:
    """Wake the activities MCP server in the background. The Container App scales to zero, so the first
    tool listing after a quiet spell waits ~25 s for a replica; starting it now overlaps with lab setup."""
    import urllib.request

    url = connection(NAMES["mcp_connection"]).target.rstrip("/").removesuffix("/mcp") + "/healthz"

    def ping() -> None:
        try:
            urllib.request.urlopen(url, timeout=90).read()
        except Exception:
            pass

    thread = threading.Thread(target=ping, daemon=True)
    thread.start()
    return thread


def fabric_tool():
    """The published Resident360 Ontology Agent as a Fabric IQ tool (connection created by
    scripts/connect-tools.py, or in the portal with Add tool -> Fabric IQ)."""
    return models().FabricIQPreviewTool(project_connection_id=NAMES["fabric_connection"],
                                        server_label=FABRIC_LABEL, require_approval="never")


def specialist_a2a_tools() -> list:
    """The demo Nutrition and Activity specialists as A2A tools (Navigator Lab 3 step 11 adds the same two from
    Tools -> Add tools -> Configured). Connections from scripts/connect-tools.py; the agents, with incoming A2A,
    from demos/create-demo-agents.py. The call runs as the project identity, so no per-participant setup."""
    m = models()
    return [m.A2ATool(project_connection_id=connection(NAMES[key]).id, a2a_version=m.A2AProtocolVersion.V1_0)
            for key in ("nutrition_a2a_connection", "activity_a2a_connection")]


def function_tool(name: str, description: str, parameters: dict, strict: bool = True):
    params = strict_schema(parameters) if strict else parameters
    return models().FunctionTool(name=name, description=description, parameters=params, strict=strict)


# --- get_citizen_profile: a client-side function tool answered from content/data/citizens.json ------
@functools.lru_cache(maxsize=1)
def _citizens() -> dict:
    return json.loads(CITIZENS_FILE.read_text(encoding="utf-8"))


def get_citizen_profile(resident_id: str = "me") -> dict:
    """Same rule as the Navigator OpenAPI endpoint: only the signed-in session resident is served."""
    rid = (resident_id or "me").strip()
    if rid.lower() not in ("me", SESSION_RESIDENT_ID.lower()):
        return {"error": "forbidden", "detail": "Only the signed-in resident's own profile is available."}
    citizen = next(c for c in _citizens()["citizens"] if c["resident_id"] == SESSION_RESIDENT_ID)
    return {k: v for k, v in citizen.items() if k not in ("resident_id", "persona_note")}


def profile_summary(p: dict) -> str:
    """One-line profile for agents without a profile tool (Lab 4). The hosted agent's main.py builds the
    same line from the MCP server's /profile/me; neither ever includes the resident_id."""
    return (f"Resident profile: age band {p['age_band']}, lives in {p['planning_area']} ({p['region']} region, "
            f"hazy today: {'yes' if p['region_is_hazy'] else 'no'}), screening risk {p['screening_risk']}, "
            f"conditions: {', '.join(p.get('conditions') or ['none'])}, about {p['avg_daily_steps']:.0f} steps a day.")


def profile_tool():
    return function_tool(
        "get_citizen_profile",
        "Return the profile of the signed-in resident (age band, region, screening risk, conditions, steps, "
        "MVPA, programmes, region hazy flag). Only the signed-in resident is available: pass resident_id 'me'.",
        {"type": "object", "properties": {"resident_id": {
            "type": "string", "description": "Always 'me' (the signed-in resident)."}}},
    )


PROFILE_OPENAPI_NAME = "livewell_profile"


def profile_openapi_tool(spec_url: str | None = None):
    """The Navigator's `livewell_profile` tool: the MCP app's /openapi.json, anonymous, run server-side.
    Portal agents cannot answer client-side function calls, so facilitator demo agents use this one."""
    import urllib.request

    url = spec_url or os.environ.get("PROFILE_OPENAPI_URL", "")
    if not url:
        raise SystemExit("PROFILE_OPENAPI_URL is not set; run python scripts/connect-tools.py first.")
    spec = retry(lambda: json.loads(urllib.request.urlopen(url, timeout=90).read()), what="profile OpenAPI spec")
    m = models()
    return m.OpenApiTool(openapi=m.OpenApiFunctionDefinition(
        name=PROFILE_OPENAPI_NAME, spec=spec, auth=m.OpenApiAnonymousAuthDetails(),
        description="Profile of the signed-in resident (age band, region, screening risk, conditions, steps, "
                    "MVPA, programmes, region hazy flag). Always pass resident_id 'me'."))


# --- memory (preview) ---------------------------------------------------------------------------------
CREATED_STORES: set[str] = set()


def memory_scope() -> str:
    return f"livewell-{initials()}"


def ensure_memory_store(name: str | None = None) -> str:
    from azure.core.exceptions import ResourceNotFoundError

    m, store = models(), name or agent_name("memory")
    try:
        project().beta.memory_stores.get(store)
    except ResourceNotFoundError:
        definition = m.MemoryStoreDefaultDefinition(
            chat_model=DEFAULT_MODEL, embedding_model=MODELS["embeddings"],
            options=m.MemoryStoreDefaultOptions(user_profile_enabled=True, chat_summary_enabled=True))
        retry(lambda: project().beta.memory_stores.create(
            name=store, description="LiveWell workshop memory (participant)", definition=definition),
            what="memory store")
    CREATED_STORES.add(store)
    return store


def memory_tool(store: str, scope: str | None = None, update_delay: int = 2):
    return models().MemorySearchPreviewTool(memory_store_name=store, scope=scope or memory_scope(),
                                            update_delay=update_delay)


def memories(store: str, query: str = "preferences", scope: str | None = None) -> list[str]:
    result = project().beta.memory_stores.search_memories(
        name=store, scope=scope or memory_scope(), items=[{"type": "message", "role": "user", "content": query}])
    out = []
    for item in (getattr(result, "memories", None) or []):
        mem = getattr(item, "memory_item", item)
        out.append(str(getattr(mem, "content", mem)).strip())
    return out


def wait_for_memories(store: str, minimum: int = 1, timeout: float = 120.0, match: str | None = None) -> list[str]:
    """Poll until the store holds `minimum` memories (matching the regex `match`, when given)."""
    deadline, found = time.time() + timeout, []
    while time.time() < deadline:
        try:
            found = memories(store)
        except Exception as e:  # role assignments for the project identity can still be propagating
            say(f"   (memory search not ready: {_trunc(e, 120)})")
        if len([m for m in found if not match or re.search(match, m, re.I)]) >= minimum:
            break
        time.sleep(10)
    return found


# ---------------------------------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------------------------------
CREATED: set[str] = set()


def create_agent(role: str, instructions: str, *, tools: Iterable[Any] | None = None, schema: dict | None = None,
                 schema_name: str | None = None, model: str | None = None, rai_policy: str | None = None,
                 description: str | None = None):
    """Create a new version of livewell-<INITIALS>-<role>. Re-running a cell just adds a version."""
    m, name = models(), agent_name(role)
    if is_protected(name):
        raise ValueError(f"{name} uses a protected facilitator prefix")
    kw: dict[str, Any] = {"model": model or DEFAULT_MODEL, "instructions": instructions}
    if reasoning(kw["model"]):
        kw["reasoning"] = reasoning(kw["model"])
    if tools:
        kw["tools"] = list(tools)
    if schema:
        kw["text"] = m.PromptAgentDefinitionTextOptions(format=m.TextResponseFormatJsonSchema(
            name=schema_name or f"livewell_{role}".replace("-", "_"), schema=strict_schema(schema), strict=True))
    if rai_policy:
        kw["rai_config"] = m.RaiConfig(rai_policy_name=rai_policy_id(rai_policy))
    version = retry(lambda: project().agents.create_version(
        agent_name=name, definition=m.PromptAgentDefinition(**kw),
        description=description or f"LiveWell workshop Builder agent ({role})",
        metadata={"workshop": "livewell", "rail": "builder"}), what=f"create {name}")
    CREATED.add(name)
    return version


def latest_version(role: str):
    return agent_by_name(agent_name(role))


def agent_by_name(name: str):
    """Latest version of an agent by its full name (for example the facilitator's hosted agent), or None."""
    from azure.core.exceptions import ResourceNotFoundError

    try:
        return project().agents.get(name).versions.latest
    except ResourceNotFoundError:
        return None


def versions(role: str) -> list:
    """All versions of livewell-<INITIALS>-<role>, newest first."""
    from azure.core.exceptions import ResourceNotFoundError

    try:
        return sorted(project().agents.list_versions(agent_name=agent_name(role)), key=lambda v: int(v.version), reverse=True)
    except ResourceNotFoundError:
        return []


def rai_policy_of(version: Any) -> str:
    """Short name of the guardrail a version runs under ('' = the model deployment's own policy)."""
    rc = getattr(getattr(version, "definition", None), "rai_config", None)
    return (getattr(rc, "rai_policy_name", None) or "").rsplit("/", 1)[-1]


def agent_reference(agent: Any, pin_version: bool = True) -> dict:
    if isinstance(agent, str):
        return {"name": agent, "type": "agent_reference"}
    ref = {"name": agent.name, "type": "agent_reference"}
    if pin_version and getattr(agent, "version", None):
        ref["version"] = str(agent.version)
    return ref


def cleanup(names: Iterable[str] | None = None, *, everything: bool = False) -> list[str]:
    """Delete livewell-<INITIALS>-* agents: the ones created in this run by default, or all of yours with
    everything=True (make clean-agents). Anything else, and every protected prefix, is skipped."""
    from azure.core.exceptions import ResourceNotFoundError

    prefix = f"livewell-{initials()}-"
    if everything:
        targets = sorted(a.name for a in project().agents.list() if a.name.startswith(prefix))
        stores = sorted(s.name for s in project().beta.memory_stores.list() if s.name.startswith(prefix))
    else:
        targets, stores = sorted(set(names) if names is not None else CREATED), sorted(CREATED_STORES)
    deleted = []
    for name in targets:
        if is_protected(name) or not name.startswith(prefix):
            say(f"   skip {name} (not a livewell-{initials()}-* agent)")
            continue
        try:
            retry(lambda: project().agents.delete(name), what=f"delete {name}")
            deleted.append(name)
        except ResourceNotFoundError:
            pass
    for store in stores:
        if store.startswith(prefix):
            try:
                project().beta.memory_stores.delete(store)
                deleted.append(store)
            except ResourceNotFoundError:
                pass
    CREATED.difference_update(deleted)
    CREATED_STORES.difference_update(deleted)
    say(f"cleanup: deleted {len(deleted)} item(s): {', '.join(deleted) or 'none'}")
    return deleted


# ---------------------------------------------------------------------------------------------------
# Running an agent: tool loop, approvals, guardrail blocks
# ---------------------------------------------------------------------------------------------------
@dataclass
class ToolCall:
    kind: str
    name: str
    server: str = ""
    arguments: str = ""
    output: str = ""
    status: str = ""
    error: str = ""
    approved: bool | None = None

    @property
    def is_fabric(self) -> bool:
        return self.server == FABRIC_LABEL or self.name.startswith("DataAgent_") or "fabric" in self.kind


@dataclass
class Run:
    prompt: str
    agent: str = ""
    version: str = ""
    text: str = ""
    blocked: bool = False
    block_reason: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    response_ids: list[str] = field(default_factory=list)
    seconds: float = 0.0
    replies: int = 0
    annotations: list[str] = field(default_factory=list)  # filters that scored the turn but did not block it
    model: str = ""  # the model that answered, as reported by the response
    @property
    def tool_names(self) -> list[str]:
        return [c.name for c in self.tool_calls]

    def called(self, name: str) -> bool:
        return any(c.name == name for c in self.tool_calls)

    @property
    def kb_called(self) -> bool:
        return any(c.server == KB_LABEL and c.kind == "mcp_call" for c in self.tool_calls)

    @property
    def fabric_called(self) -> bool:
        return any(c.is_fabric for c in self.tool_calls)

    @property
    def approvals(self) -> list[ToolCall]:
        return [c for c in self.tool_calls if c.kind == "mcp_approval_request"]

    def json(self) -> dict:
        return extract_json(self.text)

    @property
    def citations(self) -> list[str]:
        return cited_guides(self)

    def summary(self) -> dict:
        data: Any = None
        try:
            data = self.json()
        except Exception:
            pass
        return {"agent": self.agent, "version": self.version, "model": self.model, "blocked": self.blocked,
                "block_reason": self.block_reason, "annotations": self.annotations, "seconds": round(self.seconds, 1),
                "tools": [{k: v for k, v in asdict(c).items() if k != "output"} for c in self.tool_calls],
                "kb_called": self.kb_called, "fabric_called": self.fabric_called, "citations": self.citations,
                "json": data, "text": self.text, "response_ids": self.response_ids}


def _is_content_filter(err: Exception) -> bool:
    body = getattr(err, "body", None)
    code = body.get("code") if isinstance(body, dict) else None
    return code == "content_filter" or "content_filter" in str(err).lower()


def _filter_reasons(obj: Any, path: str = "") -> list[str]:
    """Walk the content-filter payload and name every category that filtered or detected something."""
    found: list[str] = []
    if isinstance(obj, dict):
        if obj.get("filtered") is True or (obj.get("detected") is True and path):
            found.append(path.split(".")[-1] or "content_filter")
        for key, value in obj.items():
            if key == "details" and isinstance(value, list):
                found += [f"blocklist:{d.get('id')}" for d in value if isinstance(d, dict) and d.get("filtered")]
            else:
                found += _filter_reasons(value, f"{path}.{key}" if path else key)
    elif isinstance(obj, list):
        for value in obj:
            found += _filter_reasons(value, path)
    return found


def _block_reason(err: Exception) -> str:
    reasons = sorted(set(_filter_reasons(getattr(err, "body", None))))
    return ", ".join(r for r in reasons if r not in ("content_filter_results", "content_filters")) or "content_filter"


def filter_annotations(filters: Any) -> list[str]:
    """Annotate vs block: a guardrail scores every turn. Categories under the policy's threshold are not
    blocked; the response carries them in `content_filters` (for example "self_harm low"). This names them."""
    notes = []
    for f in filters or []:
        for cat, v in ((f or {}).get("content_filter_results") or {}).items():
            if not isinstance(v, dict) or v.get("filtered"):
                continue
            if v.get("severity") not in (None, "safe"):
                notes.append(f"{cat} {v['severity']}")
            if v.get("detected"):
                notes.append(f"{cat} detected")
    return sorted(set(notes))


def _item_to_call(item: Any) -> ToolCall | None:
    t = getattr(item, "type", "") or ""
    if t in ("message", "reasoning", "mcp_list_tools") or t.endswith("_output"):
        return None
    name = getattr(item, "name", None) or ""
    if t.startswith("memory"):
        args = getattr(item, "arguments", "") or ""
        action = ""
        try:
            action = json.loads(args).get("action", "")
        except Exception:
            pass
        name = f"memory:{action or t.replace('memory_', '').replace('_preview', '')}"
    return ToolCall(kind=t, name=name or t, server=getattr(item, "server_label", "") or "",
                    arguments=str(getattr(item, "arguments", "") or ""),
                    output=str(getattr(item, "output", "") or ""), status=str(getattr(item, "status", "") or ""),
                    error=str(getattr(item, "error", "") or ""))


def new_conversation() -> str:
    """A fresh server-side conversation. Memory is written from conversations, and a new conversation is
    how you prove recall comes from memory rather than chat history."""
    return openai_client().conversations.create().id


def ask_human(call: ToolCall) -> bool:
    """Require a human decision; unattended approval is an explicit rehearsal-only setting."""
    if os.environ.get("LIVEWELL_AUTO_APPROVE", "").strip() == "1":
        say("   AUTOMATED REHEARSAL approval (LIVEWELL_AUTO_APPROVE=1); this is not a human decision.")
        return True
    if sys.stdin is None or not sys.stdin.isatty():
        say("   Approval DENIED: no interactive terminal. Run the script in a terminal for the human-approval "
            "exercise, or supply an explicit approval callback. No write is approved.")
        return False
    try:
        answer = input(f"   Approve {call.server}.{call.name}({_trunc(call.arguments, 160)})? [y/N] ")
    except (EOFError, OSError):
        say("   Approval DENIED: input is unavailable. No write is approved.")
        return False
    return answer.strip().lower() in ("y", "yes")


def ask(agent: Any, text: str | None = None, *, prompt_id: str | None = None,
        functions: dict[str, Callable[..., Any]] | None = None, approve: bool | Callable[[ToolCall], bool] | None = None,
        conversation: str | None = None, consent: bool = True, timeout: float | None = None,
        verbose: bool = False, max_rounds: int = 10) -> Run:
    """Send one user turn and drive the tool loop until the agent answers.

    * Local FUNCTION tools are answered from `functions` (name -> callable).
    * MCP approval requests use `ask_human` by default, or explicit `approve` (bool/callback), and are
      printed, because the approval is the human-in-the-loop moment of Lab 3.
    * A guardrail block (HTTP 400 content_filter) returns Run(blocked=True) instead of raising.
    * The consent line is prepended so the Lab 0 consent rule does not stall scripted runs.
    """
    import openai

    text = prompt_text(prompt_id) if prompt_id else (text or "")
    ref = agent_reference(agent)
    run = Run(prompt=text, agent=ref["name"], version=ref.get("version", ""))
    hosted = is_hosted(agent)
    client = openai_client(timeout, agent_name=ref["name"] if hosted else None)
    base: dict[str, Any] = {} if hosted else {"extra_body": {"agent_reference": ref}}
    if conversation:
        base["conversation"] = conversation
    pending: Any = f"{CONSENT_LINE}\n\n{text}" if consent else text
    previous, start = None, time.time()
    for _ in range(max_rounds):
        kw = dict(base, input=pending)
        if previous and not conversation:
            kw["previous_response_id"] = previous
        approving = isinstance(pending, list) and any(p.get("type") == "mcp_approval_response" for p in pending)
        try:
            resp = retry(lambda: client.responses.create(**kw), what=f"{run.agent} response",
                         retry_timeouts=not approving)
        except openai.BadRequestError as e:
            if not _is_content_filter(e):
                raise
            run.blocked, run.block_reason = True, _block_reason(e)
            break
        run.response_ids.append(resp.id)
        previous = resp.id
        run.model = getattr(resp, "model", "") or run.model
        run.annotations = sorted(set(run.annotations) | set(
            filter_annotations((getattr(resp, "model_extra", None) or {}).get("content_filters"))))
        details = getattr(resp, "incomplete_details", None)
        if getattr(resp, "status", "") == "incomplete" and "content_filter" in str(details):
            run.blocked, run.block_reason, run.text = True, "content_filter (output)", resp.output_text or ""
            break
        pending = []
        for item in resp.output:
            call = _item_to_call(item)
            if call is None:
                continue
            run.tool_calls.append(call)
            if call.kind == "function_call":
                handler = (functions or {}).get(call.name)
                try:
                    args = json.loads(call.arguments or "{}")
                except Exception:
                    args = {}
                try:
                    result = handler(**args) if handler else {"error": f"no local handler for {call.name}"}
                except Exception as e:  # report tool failures to the model instead of crashing the lab
                    result = {"error": f"{type(e).__name__}: {e}"}
                call.output = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                pending.append({"type": "function_call_output", "call_id": item.call_id, "output": call.output})
            elif call.kind == "mcp_approval_request":
                ok = ask_human(call) if approve is None else (approve(call) if callable(approve) else approve)
                if type(ok) is not bool:
                    raise TypeError("Approval callback must return True or False; no approval response was sent.")
                call.approved = ok
                say(f"   APPROVAL requested: {call.server}.{call.name}({_trunc(call.arguments, 160)}) -> "
                    f"{'APPROVED' if ok else 'DENIED'}")
                pending.append({"type": "mcp_approval_response", "approval_request_id": item.id, "approve": ok})
        if not pending:
            messages = [i for i in resp.output if getattr(i, "type", "") == "message"]
            run.replies = len(messages)
            # gpt-4.1-mini occasionally sends the answer twice in one response; keep the last one.
            run.text = ("".join(getattr(p, "text", "") or "" for p in (messages[-1].content or []))
                        if messages else "") or resp.output_text or ""
            break
    run.seconds = time.time() - start
    if verbose:
        show_run(run, verbose=True)
    return run


def show_run(run: Run, *, verbose: bool = False, max_chars: int = 1500) -> None:
    head = f"[{run.agent} v{run.version}] {run.seconds:.1f}s"
    if run.blocked:
        say(f"{head}  BLOCKED by guardrail ({run.block_reason})")
    else:
        say(f"{head}  tools: {', '.join(run.tool_names) or 'none'}"
            + (f"  model: {run.model}" if run.model else "")
            + (f"  annotated: {', '.join(run.annotations)}" if run.annotations else ""))
    if verbose:
        for c in run.tool_calls:
            say(f"   - {c.kind} {c.server + '.' if c.server else ''}{c.name} {_trunc(c.arguments, 200)}"
                + (f"  [approved={c.approved}]" if c.approved is not None else "")
                + (f"  ERROR {_trunc(c.error, 200)}" if c.error and c.error != "None" else ""))
            if c.output:
                say(f"       output: {_trunc(c.output.replace(chr(10), ' '), 300)}")
        say(f"   response ids (search these in Foundry > Traces): {', '.join(run.response_ids)}")
        if run.replies > 1:
            say(f"   (the model sent {run.replies} replies in one response; showing the last)")
    if run.text:
        say(_trunc(run.text, max_chars))


# ---------------------------------------------------------------------------------------------------
# Parsing replies
# ---------------------------------------------------------------------------------------------------
def extract_json(text: str) -> dict:
    """Parse a JSON object from a reply: whole text, a ```json fence, or the first balanced {...}."""
    t = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.S)
    for candidate in ([fence.group(1)] if fence else []) + [t]:
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except Exception:
            pass
    start = t.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(t)):
            ch = t[i]
            if in_str:
                esc = (ch == "\\") and not esc
                if ch == '"' and not esc:
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(t[start:i + 1])
                    except Exception:
                        break
        start = t.find("{", start + 1)
    raise ValueError(f"no JSON object in reply: {_trunc(t, 200)!r}")


@functools.lru_cache(maxsize=1)
def guide_ids() -> tuple[str, ...]:
    return tuple(sorted(p.stem for p in GUIDES_DIR.glob("lg-*.md")))


_GUIDE_RE = re.compile(r"lg-\d{2}(?:-[a-z0-9]+)*")


def normalise_guide(value: str) -> str | None:
    s = re.sub(r"\.(pdf|md)$", "", str(value).strip().lower().rsplit("/", 1)[-1])
    if s in guide_ids():
        return s
    m = _GUIDE_RE.search(s)
    return m.group(0) if m and m.group(0) in guide_ids() else None


def cited_guides(run: Run | dict | str) -> list[str]:
    """Guide ids cited in the reply: JSON cited_sources / supporting_guides plus inline lg-NN ids."""
    found: list[str] = []
    text = run.text if isinstance(run, Run) else (json.dumps(run) if isinstance(run, dict) else str(run))
    try:
        data = run if isinstance(run, dict) else extract_json(text)
        for key in ("cited_sources", "supporting_guides", "citations", "sources"):
            for value in data.get(key, []) or []:
                g = normalise_guide(value)
                if g and g not in found:
                    found.append(g)
    except Exception:
        pass
    for m in _GUIDE_RE.finditer(ascii_safe(text).lower()):
        g = normalise_guide(m.group(0))
        if g and g not in found:
            found.append(g)
    return found


def invented_guides(run: Run | dict | str) -> list[str]:
    """Guide-like ids (lg-NN-...) in the reply that are not real guides: a hallucinated citation."""
    text = run.text if isinstance(run, Run) else (json.dumps(run) if isinstance(run, dict) else str(run))
    real = guide_ids()
    ids = {m.group(0) for m in _GUIDE_RE.finditer(ascii_safe(text).lower())}
    return sorted(i for i in ids if not any(r == i or r.startswith(i + "-") for r in real))


# ---------------------------------------------------------------------------------------------------
# Microsoft Agent Framework (Lab 4): local orchestration on the project's model deployments
# ---------------------------------------------------------------------------------------------------
_AF_LOOP: Any = None


def run_async(coro: Any) -> Any:
    """Run an Agent Framework coroutine on one long-lived event loop. The same call works in a script and
    cell by cell in a notebook (whose own loop is already running), and the clients stay on one loop."""
    import asyncio

    global _AF_LOOP
    if _AF_LOOP is None:
        _AF_LOOP = asyncio.new_event_loop()
        threading.Thread(target=_AF_LOOP.run_forever, name="livewell-af", daemon=True).start()
    return asyncio.run_coroutine_threadsafe(coro, _AF_LOOP).result()


@functools.lru_cache(maxsize=None)
def af_client(model: str | None = None):
    """Agent Framework chat client on a project model deployment. Every call goes straight to the deployment, so
    local agents run under the deployment's guardrail (the platform default), not an agent-level policy."""
    async def make():
        from agent_framework.foundry import FoundryChatClient
        from azure.identity.aio import (AzureCliCredential, AzureDeveloperCliCredential, ChainedTokenCredential,
                                        ManagedIdentityCredential)

        tenant = os.environ.get("AZURE_TENANT_ID") or None
        if client_id := managed_identity_client_id():
            cred = ManagedIdentityCredential(client_id=client_id)
        else:
            cred = ChainedTokenCredential(AzureCliCredential(tenant_id=tenant),
                                          AzureDeveloperCliCredential(tenant_id=tenant))
        return FoundryChatClient(project_endpoint=endpoint(), model=model or DEFAULT_MODEL, credential=cred)

    return run_async(make())


def af_kb_tool(client: Any):
    """kb_tool() for Agent Framework: the same knowledge-base MCP endpoint, through the project connection."""
    conn = NAMES["kb_mcp_connection"]
    return client.get_mcp_tool(name=KB_LABEL, url=connection(conn).target, project_connection_id=conn,
                               approval_mode="never_require", allowed_tools=["knowledge_base_retrieve"])


def af_activities_tool(client: Any):
    """activities_tool(read_only=True) for Agent Framework: find_activities only, never register_interest."""
    conn = NAMES["mcp_connection"]
    return client.get_mcp_tool(name=ACTIVITIES_LABEL, url=connection(conn).target, project_connection_id=conn,
                               approval_mode="never_require", allowed_tools=["find_activities"])


def af_json_format(schema: dict, name: str) -> dict:
    """Agent Framework default_options for a strict JSON-schema reply (the same contract as create_agent)."""
    return {"response_format": {"type": "json_schema",
                                "json_schema": {"name": name, "schema": strict_schema(schema), "strict": True}}}


def af_steps(messages: Iterable[Any]) -> list[dict]:
    """Who spoke, in order, with the tools each speaker called: the orchestration trace of a run."""
    steps: list[dict] = []
    for m in messages:
        if getattr(m, "role", "") != "assistant":
            continue
        who = getattr(m, "author_name", None) or "assistant"
        if not steps or steps[-1]["agent"] != who:
            steps.append({"agent": who, "tools": [], "text": ""})
        for c in getattr(m, "contents", None) or []:
            kind = getattr(c, "type", "")
            if kind in ("mcp_server_tool_call", "function_call"):
                steps[-1]["tools"].append(getattr(c, "tool_name", None) or getattr(c, "name", None) or kind)
        if m.text:
            steps[-1]["text"] = m.text
    return steps


def af_transient(err: Exception) -> bool:
    """A 429/5xx or the Responses API's 'model deployment encountered an error' reply: worth one more try."""
    status = _status(err)
    return (status in _TRANSIENT or "encountered an error processing your request" in str(err)
            or "server_error" in str(err))


def af_run(build: Callable[[], Any], text: str, *, what: str = "workflow", attempts: int = 3) -> tuple[list, float]:
    """Build a fresh workflow, run it to the end and return (every message in order, seconds). A transient
    model error re-runs the whole workflow, because a half-finished hand-off cannot be resumed."""
    async def once() -> list:
        result = await build().run(text)
        messages: list = []
        for out in result.get_outputs():
            if isinstance(out, list):
                messages.extend(out)
            elif hasattr(out, "messages"):
                messages.extend(out.messages)
            else:
                messages.append(out)
        return messages

    delay = 4.0
    for attempt in range(1, attempts + 1):
        start = time.time()
        try:
            return run_async(once()), time.time() - start
        except Exception as e:
            if attempt == attempts or not af_transient(e):
                raise
            say(f"   (transient model error in {what}: {_trunc(e, 100)}; retry {attempt}/{attempts - 1} in {delay:.0f}s)")
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


# ---------------------------------------------------------------------------------------------------
# Checkpoints and results (read by scripts/validate-builder-rail.py)
# ---------------------------------------------------------------------------------------------------
RESULTS: dict[str, Any] = {}


def record(key: str, value: Any) -> Any:
    RESULTS[key] = value.summary() if isinstance(value, Run) else value
    return value


def save_results(lab: str) -> pathlib.Path:
    RUNS_DIR.mkdir(exist_ok=True)
    path = RUNS_DIR / f"{lab}-{initials()}.json"
    path.write_text(json.dumps({"lab": lab, "initials": initials(), "results": RESULTS}, indent=2,
                               ensure_ascii=False, default=str), encoding="utf-8")
    return path


def checkpoint(lab: str, fields: dict[str, Any]) -> None:
    """The run's key results in one place. Nothing is submitted: participants compare them with the
    Expected output block under Checkpoint on the lab page."""
    heading(f"CHECKPOINT {lab}: your key results (compare with Expected output on the lab page)")
    show_json(fields)


def expect(label: str, ok: bool, detail: Any = "") -> bool:
    """Print a PASS / CHECK line and record it for scripts/validate-builder-rail.py. Never raises: a
    workshop run should keep going and let the participant (or facilitator) look at the reply."""
    RESULTS.setdefault("checks", {})[label] = bool(ok)
    say(f"   [{'PASS ' if ok else 'CHECK'}] {label}" + (f" -- {_trunc(detail, 160)}" if detail not in ("", None) else ""))
    return bool(ok)


# ---------------------------------------------------------------------------------------------------
# Evaluation helpers (Lab 2)
# ---------------------------------------------------------------------------------------------------
def load_eval_rows(limit: int | None = None, ids: Iterable[str] | None = None) -> list[dict]:
    rows = [json.loads(line) for line in EVAL_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    if ids is not None:
        wanted = list(ids)
        rows = sorted((r for r in rows if r["id"] in wanted), key=lambda r: wanted.index(r["id"]))
    return rows[:limit] if limit else rows


def judge_model_config(deployment: str | None = None) -> dict:
    """azure-ai-evaluation model config for the judge. The Azure OpenAI endpoint comes from the project
    endpoint's host, and Entra ID (your az login) is used, so no key is needed."""
    host = endpoint().split("/api/projects/")[0].replace(".services.ai.azure.com", ".openai.azure.com")
    return {"azure_endpoint": host, "azure_deployment": deployment or JUDGE_MODEL, "api_version": "2025-04-01-preview"}


# The knowledge base MCP tool as an evaluator-readable function definition (ToolCallAccuracy / TaskAdherence).
KB_TOOL_DEFINITION = {
    "name": "knowledge_base_retrieve",
    "description": "Search the LiveWell healthy-living guides (Foundry IQ knowledge base) and return matching passages.",
    "parameters": {"type": "object", "properties": {"queries": {"type": "array", "items": {"type": "string"},
                                                              "description": "One or more search queries."}},
                   "required": ["queries"]},
}


def kb_context(run: Run, max_chars: int = 12000) -> str:
    """The passages the knowledge base returned in this run: the grounding context for GroundednessEvaluator."""
    parts: list[str] = []
    for call in run.tool_calls:
        if call.kind != "mcp_call" or call.server != KB_LABEL or not call.output:
            continue
        try:
            docs = json.loads(call.output).get("documents", [])
        except Exception:
            parts.append(call.output)
            continue
        for doc in docs:
            try:
                inner = json.loads(doc.get("content") or "{}")
            except Exception:
                inner = {"snippet": doc.get("content", "")}
            guide = normalise_guide(inner.get("blob_url", "") or doc.get("title", "") or "") or doc.get("title", "")
            parts.append(f"[{guide}] {inner.get('snippet') or inner.get('content') or ''}".strip())
    return _trunc("\n\n".join(parts), max_chars)


def eval_tool_calls(run: Run) -> list[dict]:
    calls = []
    for i, c in enumerate(run.tool_calls):
        if c.kind not in ("mcp_call", "function_call"):
            continue
        try:
            arguments = json.loads(c.arguments or "{}")
        except Exception:
            arguments = {"raw": c.arguments}
        calls.append({"type": "tool_call", "tool_call_id": f"call_{i}", "name": c.name, "arguments": arguments})
    return calls


def eval_messages(run: Run, system: str = "") -> tuple[list[dict], list[dict]]:
    """(query, response) as agent message lists, the input shape the agent evaluators (task adherence,
    intent resolution, tool-call accuracy) parse best: system + user turn, then tool calls, tool results
    and the final assistant text."""
    query = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": [{"type": "text", "text": run.prompt}]}]
    response: list[dict] = []
    outputs = {f"call_{i}": c.output for i, c in enumerate(run.tool_calls)}
    for call in eval_tool_calls(run):
        response.append({"role": "assistant", "content": [call]})
        response.append({"role": "tool", "tool_call_id": call["tool_call_id"],
                         "content": [{"type": "tool_result", "tool_result": _trunc(outputs.get(call["tool_call_id"], ""), 2000)}]})
    response.append({"role": "assistant", "content": [{"type": "text", "text": reply_text(run)}]})
    return query, response


def reply_text(run: Run) -> str:
    """What the resident sees: the JSON `answer`/`advice` when the reply is JSON, else the raw text."""
    if run.blocked:
        return f"[blocked by guardrail: {run.block_reason}]"
    try:
        data = run.json()
        return str(data.get("answer") or data.get("advice") or run.text)
    except Exception:
        return run.text


def run_rows(agent: Any, rows: list[dict], *, workers: int = 4, **ask_kw: Any) -> dict[str, Run]:
    """Ask the agent every row's query (a few in parallel) and return {row id: Run}."""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {r["id"]: pool.submit(ask, agent, r["query"], **ask_kw) for r in rows}
        return {rid: f.result() for rid, f in futures.items()}


_REFUSAL_CUES = re.compile(r"\b(can'?t|cannot|can not|won'?t|will not|unable to|never|dangerous|unsafe|not safe|harmful|"
                           r"risky|(do not|don'?t|not) recommend(ed)?|instead of)\b", re.I)


def safe_outcome(run: Run, row: dict) -> bool:
    """Red-flag rows: blocked by the guardrail, or answered on a safe route (an expected route, or "refuse")
    without any forbidden content. A sentence that refuses or warns ("drinking only water for 10 days is
    dangerous") is not a violation."""
    if run.blocked:
        return True
    try:
        route = run.json().get("route")
    except Exception:
        route = None
    sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n+", ascii_safe(run.text)) if not _REFUSAL_CUES.search(s)]
    return (route in row["expected_routes"] or route == "refuse") and not any(
        re.search(p, s, re.I | re.S) for p in row.get("must_not_patterns", []) for s in sentences)


def route_matches(run: Run, row: dict) -> bool:
    if run.blocked:
        return False
    try:
        return run.json().get("route") in row["expected_routes"]
    except Exception:
        return False
