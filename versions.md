# versions.md: pinned tools, SDKs and preview surfaces

Last checked: 2026-09-30 (Phase 4). Re-check before each delivery with `bash scripts/preflight.sh <env>`.

## Participant / facilitator tooling

| Tool | Pin | Why |
|---|---|---|
| Python | 3.13 (devcontainer); 3.12+ works locally | Matches Foundry SDK support matrix |
| uv | latest | Fast env creation in Codespaces |
| Azure CLI (`az`) | ≥ 2.75 | `az cognitiveservices`, `az role assignment` |
| Azure Developer CLI (`azd`) | ≥ 1.31 (1.34 available) | `azd provision`, `azd down --purge` |
| Fabric CLI (`fab`) | `ms-fabric-cli==1.7.0` | Workspace, lakehouse, notebook, ontology import |
| Playwright for Python | `playwright>=1.47` (1.63.0 tested), `requirements-demos.txt` | Facilitator demo kit (`demos/`): drives the installed Microsoft Edge (`channel="msedge"`), so no browser download |
| Agent Framework DevUI | `agent-framework-devui==1.0.0b260918`, `requirements-demos.txt` | Lab 4 (`demos/lab4-devui.py`): workflow graph, execution timeline and traces. Navigators use the hosted copy (`lab4-devui` container app, token, developer mode so the trace panel shows); locally it serves 127.0.0.1. Pre-release, so pinned |

Verified end to end on 2026-09-29 (Phase 2, `mcaps` environment): az 2.87.0, azd 1.34.2, Bicep 0.47.16,
azd extension `azure.ai.agents` 1.0.0-beta.17, fab 1.7.0, Git Bash (Git for Windows) on Windows ARM64.
Phase 3 (`scripts/fabric/deploy.sh mcaps`) verified on 2026-09-29 with the same tools.

## Azure resource API versions (Bicep, `infra/`)

| Resource type | API version |
|---|---|
| `Microsoft.CognitiveServices/accounts` (+ `/deployments`, `/projects`, `/projects/connections`) | 2025-06-01 |
| `Microsoft.Search/searchServices` | 2026-09-01-preview (create); 2025-05-01 (`existing` in RBAC) |
| `Microsoft.Fabric/capacities` | 2023-11-01 |
| `Microsoft.Consumption/budgets` | 2023-11-01 |
| `Microsoft.App/managedEnvironments`, `Microsoft.App/containerApps` | 2024-03-01 |
| `Microsoft.ContainerRegistry/registries` | 2023-07-01 |
| `Microsoft.Storage/storageAccounts` | 2023-05-01 |
| `Microsoft.OperationalInsights/workspaces` | 2023-09-01 |
| `Microsoft.Insights/components` | 2020-02-02 |
| `Microsoft.ManagedIdentity/userAssignedIdentities` | 2023-01-31 |
| `Microsoft.Authorization/roleAssignments` | 2022-04-01 |

Management-plane REST calls in `scripts/` use the same versions (Search usages and name check 2025-05-01,
Cost Management query 2023-11-01, Fabric capacity suspend/resume 2023-11-01). Fabric data plane: REST `v1`.

## Fabric REST surfaces (Phase 3, `scripts/fabric/`)

| Surface | Endpoint | Status |
|---|---|---|
| Items, lakehouse tables, job scheduler | `/v1/workspaces/{ws}/items`, `…/lakehouses/{id}/tables`, `…/items/{id}/jobs/{type}/instances` | GA |
| Ontology item (create / updateDefinition / getDefinition) | `/v1/workspaces/{ws}/items` with `type: Ontology` (Lab 28 part layout) | Preview |
| Graph model refresh | `…/items/{graph}/jobs/refreshGraph/instances` | Preview |
| Graph GQL query (instance check) | `/v1/workspaces/{ws}/graphModels/{id}/executeQuery?beta=true` | Beta |
| Graph GQL query (Phase 3b graph check) | `/v1/workspaces/{ws}/GraphModels/{id}/executeQuery?preview=true`; `status.code` `00000`, rows in `result.data` | Preview |
| Data agent management | `/v1/workspaces/{ws}/dataAgents/{id}/staging/{settings,datasources,…/elements,publish}` | Preview; the same calls as `fabric-data-agent-sdk` 0.1.32a0 (not installed) |
| Data source instructions (Phase 3b) | `PATCH …/staging/datasources/{id}` with `instructions`; published with the agent. `…/fewShots` answers 400 for ontology sources | Preview |
| Data agent MCP endpoint | `/v1/mcp/workspaces/{ws}/dataagents/{id}/agent`, MCP protocol 2025-06-18 | Preview |
| OneLake file read | `https://onelake.dfs.fabric.microsoft.com/{ws}/{item}/Files/…` (x-ms-version 2023-11-03) | GA |

## Python packages (Builder rail and scripts)

| Package | Pin | Notes |
|---|---|---|
| `azure-ai-projects` | `>=2.6.1` (2.6.1 tested) | New Agents API (`agents.create_version`, `create_version_from_code`, Responses, `get_openai_client(agent_name=...)` for hosted agents). 2.2.0 lacks `agents.download_code` (hosted-postdeploy) and `ProtocolConfiguration` (A2A) |
| `azure-identity` | `>=1.19` (1.25.3 tested) | `DefaultAzureCredential` / device code |
| `openai` | `>=1.99` (3.17.0 tested) | Responses client from `project.get_openai_client()` |
| `azure-search-documents` | `==12.1.0b1` | Foundry IQ knowledge base API (per microsoft/iq-series); 12.1.0b2 exists but is not validated |
| `azure-ai-evaluation` | `>=1.10` (1.18.7 tested) | Groundedness, relevance, safety evaluators |
| `agent-framework-core` | `>=1.19,<2` (1.19.0 tested) | Lab 4: `Agent`, agent middleware (`text_only`) |
| `agent-framework-foundry` | `>=1.13,<2` (1.13.1 tested) | Lab 4: `FoundryChatClient`, hosted MCP tools |
| `agent-framework-orchestrations` | `>=1.2,<2` (1.2.0 tested) | Lab 4: `SequentialBuilder(output_from="all")`, `HandoffBuilder` (autonomous mode) |
| `agent-framework-foundry-hosting` | `==1.0.0b260918` (hosted agent only) | `ResponsesHostServer`; pinned with the rest in `content/assets/hosted-agent-example/requirements.txt` |
| `mcp` | `<2` (1.30.0 tested) | FastMCP activities server; mcp 2.x changed the server API (casepal lesson) |
| `pyyaml`, `python-pptx`, `fpdf2`, `jupytext` | see `requirements.txt` | Content build (deck, guide PDFs, notebooks) |
| `ipykernel` | `>=6.29` | Builder rail: VS Code **Run Cell** on the `# %%` lab files without an install prompt |

Facilitator red team (`requirements-redteam.txt`, its own venv): `azure-ai-evaluation[redteam]==1.18.7`, which
brings PyRIT 0.11.0 and pins its own dependencies.

Verified end to end on 2026-09-30 (Phase 4, `mcaps` environment): Labs 1–4 with `INITIALS=test`, hosted agent
`livewell-workshop-hosted` deployed with azd extension `azure.ai.agents` 1.0.0-beta.17 (code deploy,
`python_3_13`, remote build), red-team lite scan.

Phase 5 (`mcaps`): `scripts/smoke-test.py` 7/7, `demos/create-demo-agents.py` (5 agents plus the `livewell-eval`
dataset), and portal screenshots and videos with Playwright 1.63.0 and Edge on Windows ARM64. Portal surfaces
the demo kit depends on (the new Foundry portal at `ai.azure.com`, "New Foundry" toggle on): agent playground
(model picker, Knowledge → Connect to Foundry IQ, Tools → Add, response format), trace dialog, Knowledge, Memory,
Guardrails and Evaluations pages. The playground accepts only png, jpg, jpeg, webp, gif and pdf attachments.

## Models

Deployment names equal model names (see `models:` in `content/config/workshop.yaml`).

| Role | Model | SKU | Region |
|---|---|---|---|
| Default | gpt-5-mini (2025-08-07), reasoning effort Low | GlobalStandard, 400K TPM cap | swedencentral (Labs 0–2, Lab 3 specialists, memory store, KB query planning, Lab 4) |
| Tools | gpt-4.1-mini (2025-04-14) | GlobalStandard, 200K TPM cap | swedencentral (Lab 3 coach on: OpenAPI, A2A, function and Fabric tools are not supported on gpt-5-mini; also the evaluation judges) |
| Embeddings | text-embedding-3-small (1) | GlobalStandard, 100K TPM cap | swedencentral |

PTU deployments and partner models are never used.

## Preview surfaces (may change; each has a fallback in `foundry-workshop-plan.md`)

| Surface | Used in | Fallback |
|---|---|---|
| Foundry IQ knowledge bases (agentic retrieval) | Lab 1 | Classic Azure AI Search tool on the same index |
| Guardrails (new Foundry portal) and custom blocklists | Lab 2 | Content filter on the deployment; prebuilt demo agent `livewell-demo-guarded` |
| Prompt shields / indirect-attack detection | Lab 2 | Instruction-level defence plus a facilitator demo |
| Memory (Foundry Agent Service) | Lab 3 | Conversation-scoped preferences in instructions |
| Specialist agents as tools (multi-agent) | Lab 3, Lab 4 | No connected-agent tool in the new Agent Service. Navigator (optional step 11) attaches two admin-built specialists with the GA A2A tool: incoming A2A on the specialists is REST/SDK only and the connections need Foundry Project Manager, so `create-demo-agents.py` and `connect-tools.py` do both before the workshop. Builder calls its own specialists through function tools. Without the A2A tools, the Navigator coach writes both plans from the knowledge base |
| Fabric IQ tool (Ontology Agent via OneLake Catalog) | Fabric step, Lab 4 | Facilitator-only demo from `demos/`; pre-computed numbers from `scripts/r360.py` |
| Fabric ontology (preview), graph model and data agent over the ontology | Phase 3 | Fabric data agent over the lakehouse tables |
| Hosted agents (Agent Framework, code deploy) | Lab 4: the facilitator deploys; participants chat with it | Run the same team locally (`lab4_multiagent.py` section 4); prompt agent published to Teams / M365 |
| Foundry MCP server | Admin | `az` and SDK scripts |
