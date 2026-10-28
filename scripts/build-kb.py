#!/usr/bin/env python3
"""Build the shared Foundry IQ knowledge base `livewell-guides-kb` (facilitator, once per environment).

Steps (all idempotent):
  1. Upload content/knowledge/livewell-guides/pdf/*.pdf to the knowledge container (Blob) or to the
     lakehouse Files folder (OneLake). For Blob on a default-Deny account (storageNetworkDefaultAction='Deny')
     the caller's IP is allowed on the storage firewall for the upload only and removed again (ASSUMPTIONS.md 4.4).
  2. Knowledge source `livewell-guides-ks`: indexed Blob source (default) or indexed OneLake Files source
     (--source onelake). Azure AI Search builds the indexer/index itself and embeds with the models.embeddings
     deployment (text-embedding-3-small) through its managed identity. When that deployment changes, the source
     and the knowledge base are deleted and recreated with the same names (the index vectors change size).
  3. Knowledge base `livewell-guides-kb`: reasoning effort low, extractive output (the agent writes the
     answer and cites guide ids), retrieval + answer instructions, models.default (gpt-5-mini) for query planning.
  4. Project connection `livewell-guides-kb-mcp` (RemoteTool, project managed identity) to the KB MCP
     endpoint, used by lab1_knowledge.py and the Navigator "Connect to Foundry IQ" flow.
  5. Retrieval check: the pre-diabetes prompt must come back with lg-05 (or another expected guide).

    python scripts/build-kb.py                     # Blob source (default)
    python scripts/build-kb.py --source onelake    # lakehouse Files/livewell-guides (Fabric capacity must be Active)
    python scripts/build-kb.py --check             # status + retrieval check only, no changes
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import wsconfig  # noqa: E402
from azrest import Api, ApiError, az_token  # noqa: E402

KB_API = "2026-05-01-preview"            # KB MCP endpoint + SDK default (azure-search-documents 12.1.0b1)
CONN_API = "2025-10-01-preview"          # project connections with category RemoteTool + audience
PDF_DIR = ROOT / "content" / "knowledge" / "livewell-guides" / "pdf"
ONELAKE_FOLDER = "Files/livewell-guides"

RETRIEVAL_INSTRUCTIONS = (
    "The LiveWell guides are short plain-language healthy-living guides for Singapore residents: healthy "
    "plate, physical activity, Nutri-Grade, salt and sugar, pre-diabetes eating, exercise by condition, sleep, "
    "screening, hazy-day activity, active after 60 and a LiveWell Coach FAQ. Search them for food, activity, "
    "sleep and screening questions. Medication, supplements, diagnosis and other residents' data are NOT "
    "covered; return nothing rather than a loosely related guide."
)
ANSWER_INSTRUCTIONS = (
    "Answer only from the retrieved guides, in plain Singapore English, in under 120 words. Name each guide "
    "you used by its id (the file name without .pdf, e.g. lg-05-eating-for-pre-diabetes). If the guides do "
    "not cover the question, say so and suggest a doctor, pharmacist or HealthHub. Never give medication advice."
)


def log(msg: str) -> None:
    print(f"[build-kb] {msg}", flush=True)


def azd_env() -> dict:
    try:
        out = subprocess.run(["azd", "env", "get-values"], cwd=ROOT, capture_output=True, text=True,
                             timeout=60, shell=os.name == "nt").stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    vals = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"')
    return vals


def require(env: dict, *keys: str) -> None:
    missing = [k for k in keys if not env.get(k)]
    if missing:
        raise SystemExit(f"[build-kb] missing {', '.join(missing)} in the azd env; run azd provision first")


# --- 1. upload ------------------------------------------------------------------------------------

def public_ip() -> str:
    with urllib.request.urlopen("https://api.ipify.org", timeout=20) as r:
        return r.read().decode().strip()


def az(*args: str, subscription: str) -> str:
    proc = subprocess.run(["az", *args, "--subscription", subscription, "-o", "tsv"],
                          capture_output=True, text=True, shell=os.name == "nt")
    if proc.returncode != 0:
        raise SystemExit(f"[build-kb] az {' '.join(args[:3])} failed: {proc.stderr.strip()[:300]}")
    return proc.stdout.strip()


def upload_blob(env: dict, container: str, pdfs: list[Path]) -> None:
    from azure.core.exceptions import HttpResponseError
    from azure.identity import AzureCliCredential
    from azure.storage.blob import BlobServiceClient, ContentSettings

    account, rg = env["AZURE_STORAGE_ACCOUNT_NAME"], env["AZURE_RESOURCE_GROUP"]
    subscription = env["AZURE_SUBSCRIPTION_ID"]
    deny = az("storage", "account", "show", "-n", account, "-g", rg, "--query", "networkRuleSet.defaultAction",
              subscription=subscription) == "Deny"
    ip = public_ip() if deny else ""
    rules = az("storage", "account", "network-rule", "list", "-n", account, "-g", rg,
               "--query", "ipRules[].ipAddressOrRange", subscription=subscription) if deny else ""
    added = deny and ip not in rules.split()
    if added:
        log(f"allowing {ip} on {account} for the upload")
        az("storage", "account", "network-rule", "add", "-n", account, "-g", rg, "--ip-address", ip,
           "--query", "defaultAction", subscription=subscription)
    try:
        svc = BlobServiceClient(env["AZURE_STORAGE_BLOB_ENDPOINT"], credential=AzureCliCredential(subscription=subscription))
        cc = svc.get_container_client(container)
        for attempt in range(12):  # firewall changes take up to ~1 min to apply
            try:
                existing = {b.name: b.size for b in cc.list_blobs()}
                break
            except HttpResponseError as e:
                if e.status_code != 403 or attempt == 11:
                    raise
                time.sleep(10)
        for pdf in pdfs:
            data = pdf.read_bytes()
            if existing.get(pdf.name) == len(data):
                continue
            cc.upload_blob(pdf.name, data, overwrite=True,
                           content_settings=ContentSettings(content_type="application/pdf"),
                           metadata={"guide_id": pdf.stem})
            log(f"uploaded {pdf.name}")
        stale = [n for n in existing if n.endswith(".pdf") and n not in {p.name for p in pdfs}]
        for name in stale:
            cc.delete_blob(name)
            log(f"deleted stale {name}")
        log(f"{container}: {len(pdfs)} guides in Blob")
    finally:
        if added:
            az("storage", "account", "network-rule", "remove", "-n", account, "-g", rg, "--ip-address", ip,
               "--query", "defaultAction", subscription=subscription)
            log(f"removed {ip} from {account}")


def upload_onelake(env: dict, pdfs: list[Path]) -> None:
    ws, lh = env["FABRIC_WORKSPACE_ID"], env["FABRIC_LAKEHOUSE_ID"]
    token = az_token("https://storage.azure.com", subscription=env["AZURE_SUBSCRIPTION_ID"])
    base = f"https://onelake.dfs.fabric.microsoft.com/{ws}/{lh}/{ONELAKE_FOLDER}"

    def call(method: str, url: str, data: bytes | None = None) -> None:
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {token}")
        if data is not None:
            req.add_header("Content-Length", str(len(data)))
        urllib.request.urlopen(req, timeout=120).close()

    for pdf in pdfs:
        data = pdf.read_bytes()
        url = f"{base}/{pdf.name}"
        call("PUT", f"{url}?resource=file")
        call("PATCH", f"{url}?action=append&position=0", data)
        call("PATCH", f"{url}?action=flush&position={len(data)}", b"")
        log(f"uploaded OneLake {ONELAKE_FOLDER}/{pdf.name}")


def grant_search_on_workspace(env: dict, search_principal: str) -> None:
    """OneLake indexing reads the lakehouse as the search service identity (workspace Contributor)."""
    fabric = Api("fabric", subscription=env["AZURE_SUBSCRIPTION_ID"])
    ws = env["FABRIC_WORKSPACE_ID"]
    current = fabric.get_all(f"/v1/workspaces/{ws}/roleAssignments")
    if any((a.get("principal") or {}).get("id") == search_principal for a in current):
        return
    fabric.post(f"/v1/workspaces/{ws}/roleAssignments",
                {"principal": {"id": search_principal, "type": "ServicePrincipal"}, "role": "Contributor"})
    log("search managed identity added to the Fabric workspace as Contributor")


# --- 2-3. knowledge source + knowledge base -----------------------------------------------------------

def aoai_params(env: dict, deployment: str):
    from azure.search.documents.indexes.models import AzureOpenAIVectorizerParameters
    return AzureOpenAIVectorizerParameters(resource_url=env["AZURE_OPENAI_ENDPOINT"].rstrip("/"),
                                           deployment_name=deployment, model_name=deployment)


def build_source(env: dict, names: dict, models: dict, source: str):
    from azure.search.documents.indexes.models import (
        AzureBlobKnowledgeSource, AzureBlobKnowledgeSourceParameters, IndexedOneLakeKnowledgeSource,
        IndexedOneLakeKnowledgeSourceParameters)
    from azure.search.documents.knowledgebases.models import (
        KnowledgeSourceAzureOpenAIVectorizer, KnowledgeSourceIngestionParameters)

    ingestion = KnowledgeSourceIngestionParameters(
        embedding_model=KnowledgeSourceAzureOpenAIVectorizer(azure_open_ai_parameters=aoai_params(env, models["embeddings"])),
        disable_image_verbalization=True,
        content_extraction_mode="minimal",
    )
    if source == "onelake":
        return IndexedOneLakeKnowledgeSource(
            name=names["knowledge_source"],
            description="LiveWell healthy-living guides (PDF) in the Resident 360 lakehouse Files folder.",
            indexed_one_lake_parameters=IndexedOneLakeKnowledgeSourceParameters(
                fabric_workspace_id=env["FABRIC_WORKSPACE_ID"], lakehouse_id=env["FABRIC_LAKEHOUSE_ID"],
                target_path=ONELAKE_FOLDER, ingestion_parameters=ingestion))
    storage_id = (f"/subscriptions/{env['AZURE_SUBSCRIPTION_ID']}/resourceGroups/{env['AZURE_RESOURCE_GROUP']}"
                  f"/providers/Microsoft.Storage/storageAccounts/{env['AZURE_STORAGE_ACCOUNT_NAME']}")
    return AzureBlobKnowledgeSource(
        name=names["knowledge_source"],
        description="LiveWell healthy-living guides (PDF), one file per guide; file name = guide id.",
        azure_blob_parameters=AzureBlobKnowledgeSourceParameters(
            connection_string=f"ResourceId={storage_id};", container_name=names["knowledge_container"],
            ingestion_parameters=ingestion))


def embedding_of(ks) -> str | None:
    """The embedding deployment a knowledge source ingests with (Blob or OneLake)."""
    def get(obj, attr: str, key: str):
        # A fetched source returns ingestion_parameters as a plain dict (REST names), a built one as models.
        return obj.get(key) if isinstance(obj, dict) else getattr(obj, attr, None)

    params = getattr(ks, "azure_blob_parameters", None) or getattr(ks, "indexed_one_lake_parameters", None)
    model = get(get(params, "ingestion_parameters", "ingestionParameters"), "embedding_model", "embeddingModel")
    return get(get(model, "azure_open_ai_parameters", "azureOpenAIParameters"), "deployment_name", "deploymentId")


def build_kb(env: dict, names: dict, models: dict):
    from azure.search.documents.indexes.models import (
        KnowledgeBase, KnowledgeBaseAzureOpenAIModel, KnowledgeSourceReference)
    from azure.search.documents.knowledgebases.models import (
        KnowledgeRetrievalLowReasoningEffort, KnowledgeRetrievalOutputMode)

    return KnowledgeBase(
        name=names["knowledge_base"],
        description="LiveWell healthy-living guides for the LiveWell Coach workshop (shared by all attendees).",
        knowledge_sources=[KnowledgeSourceReference(name=names["knowledge_source"])],
        models=[KnowledgeBaseAzureOpenAIModel(azure_open_ai_parameters=aoai_params(env, models["default"]))],
        retrieval_reasoning_effort=KnowledgeRetrievalLowReasoningEffort(),
        output_mode=KnowledgeRetrievalOutputMode.EXTRACTIVE_DATA,
        retrieval_instructions=RETRIEVAL_INSTRUCTIONS,
        answer_instructions=ANSWER_INSTRUCTIONS,
    )


def source_status(client, name: str) -> dict:
    status = client.get_knowledge_source_status(name)
    return status.as_dict() if hasattr(status, "as_dict") else dict(status)


def wait_for_ingestion(client, name: str, expected: int, timeout_s: int = 900) -> dict:
    deadline = time.time() + timeout_s
    last = ""
    while True:
        st = source_status(client, name)
        cur = st.get("currentSynchronizationState") or {}
        done = (st.get("lastSynchronizationState") or {})
        line = f"status={st.get('synchronizationStatus')} processed={cur.get('itemsUpdatesProcessed', done.get('itemsUpdatesProcessed'))} failed={cur.get('itemsUpdatesFailed', done.get('itemsUpdatesFailed'))}"
        if line != last:
            log(f"ingestion {line}")
            last = line
        if not cur and done and done.get("itemsUpdatesProcessed", 0) + done.get("itemsSkipped", 0) >= expected:
            return st
        if not cur and done and st.get("synchronizationStatus") == "active" and done.get("itemsUpdatesFailed"):
            return st
        if time.time() > deadline:
            log("ingestion still running; re-run with --check later")
            return st
        time.sleep(15)


# --- 4. project connection ------------------------------------------------------------------------------

def ensure_connection(env: dict, names: dict, check: bool) -> str:
    target = f"{env['AZURE_SEARCH_ENDPOINT'].rstrip('/')}/knowledgebases/{names['knowledge_base']}/mcp?api-version={KB_API}"
    url = f"{env['AZURE_AI_PROJECT_ID']}/connections/{names['kb_mcp_connection']}?api-version={CONN_API}"
    arm = Api("arm", subscription=env["AZURE_SUBSCRIPTION_ID"])
    current = arm.get(url, ok_404=True)
    if current and (current.get("properties") or {}).get("target") == target:
        return "in sync"
    if check:
        return "missing" if not current else "target drift"
    arm.put(url, {"properties": {"category": "RemoteTool", "authType": "ProjectManagedIdentity", "target": target,
                                 "isSharedToAll": True, "audience": "https://search.azure.com/",
                                 "metadata": {"ApiType": "Azure", "type": "knowledgeBase_MCP"}}})
    return "created" if not current else "updated"


# --- 5. retrieval check ---------------------------------------------------------------------------------

def retrieval_check(endpoint: str, kb: str, credential) -> tuple[bool, list[str]]:
    from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient
    from azure.search.documents.knowledgebases.models import (
        KnowledgeBaseMessage, KnowledgeBaseMessageTextContent, KnowledgeBaseRetrievalRequest,
        KnowledgeRetrievalLowReasoningEffort)

    prompts = json.loads((ROOT / "content" / "prompts" / "test-prompts.json").read_text(encoding="utf-8"))["prompts"]
    p = prompts["lab1_prediabetes_eat"]
    client = KnowledgeBaseRetrievalClient(endpoint=endpoint, knowledge_base_name=kb, credential=credential)
    result = client.retrieve(retrieval_request=KnowledgeBaseRetrievalRequest(
        messages=[KnowledgeBaseMessage(role="user", content=[KnowledgeBaseMessageTextContent(text=p["text"])])],
        retrieval_reasoning_effort=KnowledgeRetrievalLowReasoningEffort()))
    ids = []
    for ref in result.references or []:
        d = ref.as_dict() if hasattr(ref, "as_dict") else dict(ref)
        blob = d.get("blobUrl") or d.get("docUrl") or d.get("docKey") or json.dumps(d.get("sourceData") or {})
        for token in str(blob).replace("%2F", "/").split("/"):
            if token.startswith("lg-"):
                ids.append(token.split(".pdf")[0][:60])
                break
    ids = list(dict.fromkeys(ids))
    return bool(set(ids) & set(p["expected"]["cited_sources_any"])), ids


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", choices=["blob", "onelake"], default=os.environ.get("KB_SOURCE", "blob"))
    ap.add_argument("--check", action="store_true", help="report status and run the retrieval check only")
    ap.add_argument("--skip-upload", action="store_true")
    args = ap.parse_args()

    env = {**azd_env(), **{k: v for k, v in os.environ.items() if k.startswith(("AZURE_", "FABRIC_"))}}
    require(env, "AZURE_SEARCH_ENDPOINT", "AZURE_SEARCH_SERVICE_NAME", "AZURE_OPENAI_ENDPOINT", "AZURE_AI_PROJECT_ID",
            "AZURE_SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP", "AZURE_STORAGE_ACCOUNT_NAME", "AZURE_STORAGE_BLOB_ENDPOINT")
    if args.source == "onelake":
        require(env, "FABRIC_WORKSPACE_ID", "FABRIC_LAKEHOUSE_ID")
    cfg = wsconfig.load(env.get("AZURE_ENV_NAME"))
    names, models = cfg["names"], cfg["models"]

    from azure.identity import AzureCliCredential
    from azure.search.documents.indexes import SearchIndexClient

    credential = AzureCliCredential(subscription=env["AZURE_SUBSCRIPTION_ID"])
    client = SearchIndexClient(endpoint=env["AZURE_SEARCH_ENDPOINT"], credential=credential)
    pdfs = sorted(PDF_DIR.glob("lg-*.pdf"))
    if not pdfs:
        raise SystemExit("[build-kb] no PDFs; run python scripts/build-guides-pdf.py first")

    if not args.check:
        if not args.skip_upload:
            if args.source == "onelake":
                search_principal = az("search", "service", "show", "-n", env["AZURE_SEARCH_SERVICE_NAME"], "-g",
                                      env["AZURE_RESOURCE_GROUP"], "--query", "identity.principalId",
                                      subscription=env["AZURE_SUBSCRIPTION_ID"])
                grant_search_on_workspace(env, search_principal)
                upload_onelake(env, pdfs)
            else:
                upload_blob(env, names["knowledge_container"], pdfs)
        ks = build_source(env, names, models, args.source)
        try:
            existing = client.get_knowledge_source(ks.name)
        except Exception:  # noqa: BLE001 - ResourceNotFoundError
            existing = None
        old_emb, new_emb = (embedding_of(existing), embedding_of(ks)) if existing is not None else (None, None)
        if existing is not None and (existing.kind != ks.kind or (old_emb and old_emb != new_emb)):
            log(f"replacing {ks.name} ({existing.kind} -> {ks.kind}, embeddings {old_emb} -> {new_emb}); "
                "the knowledge base is detached first")
            try:
                client.delete_knowledge_base(names["knowledge_base"])
            except Exception:  # noqa: BLE001
                pass
            client.delete_knowledge_source(ks.name)
        client.create_or_update_knowledge_source(ks)
        log(f"knowledge source {ks.name} ({args.source}) ready")
        wait_for_ingestion(client, ks.name, len(pdfs))
        client.create_or_update_knowledge_base(build_kb(env, names, models))
        log(f"knowledge base {names['knowledge_base']} ready (reasoning effort low, extractive output)")

    st = source_status(client, names["knowledge_source"])
    done = st.get("lastSynchronizationState") or {}
    conn = ensure_connection(env, names, args.check)
    ok, ids = retrieval_check(env["AZURE_SEARCH_ENDPOINT"], names["knowledge_base"], credential)

    rows = [
        ("knowledge source", names["knowledge_source"], f"{st.get('synchronizationStatus')} processed={done.get('itemsUpdatesProcessed')} failed={done.get('itemsUpdatesFailed')}"),
        ("knowledge base", names["knowledge_base"], "reasoning effort low, extractive"),
        ("project connection", names["kb_mcp_connection"], conn),
        ("retrieval lab1_prediabetes_eat", "expect lg-05/lg-01/lg-04", ("PASS " if ok else "FAIL ") + (", ".join(ids) or "no references")),
    ]
    w = max(len(r[0]) for r in rows)
    for r in rows:
        print(f"  {r[0]:<{w}}  {r[1]:<28}  {r[2]}")
    return 0 if ok and conn in ("in sync", "created", "updated") else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ApiError as e:
        raise SystemExit(f"[build-kb] {e}")
