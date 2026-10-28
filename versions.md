# versions.md: pinned tools, SDKs and preview surfaces

Last checked: 2026-09-30 (Phase 4). Re-check before each delivery with `bash scripts/preflight.sh <env>`.

## HPB regional exception (2026-10-24)

The user approved **Search Basic in France Central only**; all other customer-managed resources remain in Sweden
Central in the same resource group. This supersedes the single-region statements in older phase records.
Search FetchOfferings (`2026-09-01-preview`, read-only) returned Basic for France Central but no SKUs for Sweden
Central; subscription Basic usage was 0/12 and 2/12 respectively. `scripts/lib/searchcheck.py` now gates new creation
on advertised SKU availability, separately from quota. Neither reserves physical capacity.

Sources: [Search regions](https://learn.microsoft.com/azure/search/search-region-support),
[embedding placement](https://learn.microsoft.com/azure/search/cognitive-search-skill-azure-openai-embedding#best-practices),
[keyless enrichment billing](https://learn.microsoft.com/azure/search/cognitive-search-attach-cognitive-services#bill-through-a-keyless-connection),
[resource-group locations](https://learn.microsoft.com/azure/azure-resource-manager/management/overview#what-is-a-resource-group).
The approved rehearsal deployment indexed all 11 Blob PDFs and returned the expected cited guides across regions.

## Fabric ontology context (2026-10-24)

The live service rejects new ontology attachments through `/staging/datasources` with
`OntologyAddAsDataSourceBlocked`. [Current Learn guidance](https://learn.microsoft.com/fabric/data-science/data-agent-ontology-sources)
uses **Sources > Add sources > Add an ontology** and treats the ontology as context for source-native SQL/KQL/DAX,
not as the query execution endpoint. The inspected public SDK `fabric-data-agent-sdk==0.1.33a0` and public REST
specification do not expose the new attachment operation, so new deployments have one explicit portal step.
`40-data-agent.py` then verifies the matching draft/published ontology item-definition parts and instructions.
The ontology part uses the [official ontology schema](https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/definition/ontology/1.0.0/schema.json).
Older GQL-based teaching examples describe the legacy path and need a table-read against the new runtime before delivery.

## Participant / facilitator tooling

Participant simplification (2026-10-29): no dependency or deployed-image upgrade. The supplied
[Foundry Toolkit hosted-agent tutorial](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/vs-code-agents-workflow-pro-code)
was checked and linked as optional Builder learning. DevUI captures use the existing pinned version below.
Fresh workflow checks include one documented recovery after a 90-second Foundry IQ timeout; Fabric live
screenshots were deferred and no capacity state was changed. See ASSUMPTIONS.md Phase 14.

Integration for GitHub publication (2026-10-29): retained the same deployed DevUI pins and added the
environment-aware configuration loader to its build context. The separate default-inactive evaluator from
main coexists with the prepared matrix's schema-2 reader; no new evaluation or runtime deployment was started.

Teaching revision (2026-10-26): no SDK upgrades or cloud changes. Lab 2 captures use schema 2 to separate
pass/fail/not-scored; old aggregate counts cannot be reinterpreted reliably. The current
[Fabric ontology-context documentation](https://learn.microsoft.com/fabric/data-science/data-agent-ontology-sources)
was rechecked: execution uses source-native SQL/KQL/DAX, not the historical GQL visualiser's expected records.
That visualiser is retained only as a labelled legacy diagnostic/replay, not current-runtime proof.

Lab 4 teaching clarification (2026-10-25): DevUI remains pinned below; no package upgrade or authentication change.
It is Microsoft's MIT-licensed [development sample](https://learn.microsoft.com/agent-framework/integrations/by-component/ui/devui/),
not a production portal. In this workshop its Tools panel exposes local hand-offs, not the server-side Foundry MCP
operations. [Foundry tracing](https://learn.microsoft.com/azure/foundry/observability/how-to/trace-agent-framework)
is the complementary cloud view; large input-token counts alone cannot establish tool execution.

| Tool | Pin | Why |
|---|---|---|
| Python | 3.13 (devcontainer); 3.12+ works locally | Matches Foundry SDK support matrix |
| uv | latest | Fast env creation in Codespaces |
| Azure CLI (`az`) | ≥ 2.75 | `az cognitiveservices`, `az role assignment` |
| Azure Developer CLI (`azd`) | ≥ 1.31 (1.34 available) | `azd provision`, `azd down --purge` |
| Fabric CLI (`fab`) | `ms-fabric-cli==1.7.0` | Workspace, lakehouse, notebook, ontology import |
| Playwright for Python | `playwright>=1.47` (1.63.0 tested), `requirements-demos.txt` | Facilitator demo kit (`demos/`): drives the installed Microsoft Edge (`channel="msedge"`), so no browser download |
| Agent Framework DevUI | `agent-framework-devui==1.0.0b260918`, `requirements-demos.txt` | Lab 4 (`demos/lab4-devui.py`): shared workflow graph and traces. Private expiring links establish secure cookie access; backend bearer remains enabled. `DevServer` is the public extension point; authenticated `/meta` avoids the frontend token gate. Local loopback development is unchanged. |

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
| `azure-identity` | `>=1.20` (1.25.3 and scoped CLI on 1.27.0 tested) | 1.20 introduced `AzureCliCredential(subscription=...)`; select subscription or tenant, never both |
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

Deployment names equal model names (see `models:` in `content/config/workshop.yaml`; versions, capacity per
environment and the 30-participant sizing assumptions live there, and `scripts/lib/modelcheck.py` checks them).
Inventory read-only against the HPB MCAPS subscription, swedencentral, **2026-10-23**: re-run `scripts/preflight.sh`
at T-3 (quota can be consumed by other workloads). Catalogue, eligibility, quota and capacity are four separate facts.

| Role | Model | SKU | Units (1K TPM each) / RPM | Lifecycle (retires) | Free quota then |
|---|---|---|---|---|---|
| Default | gpt-5-mini (2025-08-07), reasoning effort Low | GlobalStandard | 800 / 800 RPM (Labs 0–2, Lab 3 specialists, memory store, KB query planning, Lab 4) | GA (2027-02-09) | 1,275 of 3,000 |
| Tools and facilitator pre-run judge | gpt-4.1-mini (2025-04-14) | GlobalStandard | 1,000 / 1,000 RPM (Lab 3 coach on: OpenAPI, A2A, function and Fabric tools are not supported on gpt-5-mini) | **Legacy**, existing customers only (2027-04-14) | 5,830 of 15,000 |
| Embeddings | text-embedding-3-small (1) | GlobalStandard | 100 / 600 RPM (1,536 dimensions: no re-index) | GA (2028-02-09) | 750 of 1,000 |
| Router | none | n/a | not deployed, not checked, not allowed | n/a | n/a |

Fallback for the default role only: `gpt-5.4-mini` (2026-03-17, GA, retires 2027-09-21) on DataZoneStandard (1,000 free;
GlobalStandard has 75), switched by `models.default` and `models.deployment_type`. Not deployed: the Learn tool-support table
lists function tools as No for it, so it needs a live compatibility test first. Live compatibility and load tests are
**pending separate approval**; static checks do not prove runtime support.

PTU deployments, model-router and partner models are never used.

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

## Participant guide revision

- Canonical Navigator pages now include the screenshot directions and generated copy blocks. The old portal
  filenames are compatibility pages. Model versions are unchanged; the later MCAPS binding fix raises the
  Azure Identity minimum to 1.20 for explicit CLI subscription selection.
- Optional intake uses the existing strict intake schema on a separate agent. A2A remains the Navigator specialist
  path; sequential and hand-off output contracts are documented separately.
- At the Phase 11b consolidation, all 83 files decoded and 50 archived captures were hidden behind complete
  text-only directions. That historical count and no-retake status are superseded for Labs 0-3 by the native
  canvas walkthrough below. `python demos/capture-screenshots.py --list-outdated` lists the remaining archived
  subset; never treat file integrity alone as proof that an illustration is current.
- Microsoft Learn's current Fabric Lab 28 marks its ontology experience as preview and notes a January 31, 2027
  retirement. This content revision does not migrate the Fabric deployment; reassess that preview dependency before
  a future delivery. See [Fabric Lab 28](https://microsoftlearning.github.io/mslearn-fabric/Instructions/Labs/28-build-data-agent-ontology.html).
- Copy rendering is offline (`sync-lab-blocks.py --check`); environment-specific OpenAPI freshness is checked
  separately with `sync-openapi-block.py <env> --check` when the selected environment is available.
- Follow-up capture readiness: an isolated x64 Python 3.13 environment with `azure-ai-projects==2.6.1` resolves the
  ARM64 `cryptography` build failure. Read-only sponsor checks confirm the intended demo models and schema shapes.
  Those checks used sponsor and legacy MCAPS, not the user-selected subscription; their Paused status and the
  sponsor password prompt are superseded by the MCAPS correction below. No cloud configuration, capacity state
  or screenshot changed. Use `--outdated-only --dry-run` to inspect the optional bounded retake job.
- **MCAPS correction:** the explicitly selected subscription's existing HPB-prefixed account, Search and Fabric
  resources now match Python/Bicep configuration and local azd metadata. The browser canvas opens its project
  with the existing MCAPS session. Fabric is **Active F2**, and its Resident 360 workspace assignment is verified.
  The Lab 3 OpenAPI block was regenerated from this target. Models, demo schemas, connections and endpoints were
  checked read-only. The policy drift found during that check was repaired with the user's authorization below.
- API compatibility: [AzureCliCredential](https://learn.microsoft.com/python/api/azure-identity/azure.identity.azureclicredential)
  and the [Azure Identity 1.20 release notes](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/identity/azure-identity/CHANGELOG.md#1200-2025-02-11)
  document the subscription parameter. The CLI's mutually exclusive subscription/tenant token flags were also
  verified live. No SDK workaround, new sign-in, account creation, deployment or permission change was used.
- **Guardrail repair (2026-10-28):** the canonical Blocking policy, 13 filters and prompt-side custom-blocklist
  attachment are restored on the selected MCAPS account; `apply-guardrail.py --check` reports zero drift.
  Existing guarded-agent probes confirm medication blocklist enforcement, self-harm blocking and an allowed
  benign control with retrieval/citations. No model or agent version changed, and no full evaluation was run.
  An external-tenant application wrote the policy on the previous day, so retain the day-of drift check.
- Principal lookup uses the shared subscription-scoped Graph REST helper, not unsupported `az ad --subscription`
  flags. The [service-principal alternate-key lookup](https://learn.microsoft.com/graph/api/serviceprincipal-get)
  and `/me` were verified read-only; no dependency version changed for this compatibility fix.

## Lab 2 evaluation pacing

- No model or package version changes. `lab2_govern.py` is hands-on only; `lab2_evaluate.py` is an
  inactive-by-default code walkthrough with an explicit terminal `--run` gate. Participants review a
  shared completed comparison; automatic Builder validation does not start batch evaluation.
- The existing [Azure AI Evaluation SDK](https://learn.microsoft.com/python/api/azure-ai-evaluation/azure.ai.evaluation)
  supplies `evaluate`, column mappings, local output and optional project upload. The
  [agent-version lookup](https://learn.microsoft.com/python/api/azure-ai-projects/azure.ai.projects.operations.agentsoperations)
  pins `agent_name` and `agent_version` from the saved hands-on result. These API shapes were checked
  against Microsoft Learn; no new evaluation API or service was introduced.
- Default/CLI/cell execution and the opt-in path are covered offline with mocked cloud boundaries.
  No new live batch, judge score or runtime claim is made. Prepare the shared comparison before delivery;
  do not use a historical combined-output screenshot as proof of the current participant run.

## Native Navigator walkthrough (2026-10-28 UTC)

- No model deployment or package version changed. Fresh `livewell-wxyz` versions use `gpt-5-mini` Low for
  Labs 0-2 and `gpt-4.1-mini` for Lab 3. The separate intake agent and fresh memory store do not reuse demo
  conversations. Screenshots are actual Copilot browser-canvas captures; addresses/identifiers may be hidden,
  never answers or verdicts.
- Portal paths verified live: reuse the existing KB connection under Available knowledge bases; the
  facilitator-only Connect alternative selects Search before KB selection; JSON citations through retrieved
  passages; **Manage guardrail → Reassign guardrail → Assign → Save**; MCP's CSV tool fields and
  **Always auto-approve specific tools**; **Memory → Add → Auto-create memory store**.
  The [guardrail assignment guidance](https://learn.microsoft.com/azure/foundry/guardrails/how-to-create-guardrails)
  describes immediate effect, but the observed draft banner explicitly required saving the agent.
- `connect-tools.py` retains ARM `2025-10-01-preview` and checks the portal-created OpenAPI connection by
  GET only. Its observed `OpenAPI` category is absent from the published
  [2025-10-01-preview](https://learn.microsoft.com/azure/templates/microsoft.cognitiveservices/2025-10-01-preview/accounts/projects/connections)
  and [2026-09-01](https://learn.microsoft.com/azure/templates/microsoft.cognitiveservices/2026-09-01/accounts/projects/connections)
  category enums. Creation stays a documented facilitator portal step, not an undocumented automated PUT.
- Source-aware discovery and separate confirmation replace the combined request that repeated JSON.
  A source-skipping variant was rejected too: the final prompt names the retrieval tools, and its three
  read operations plus actual returned guide IDs were verified. Approval/write evidence was collected once
  in a separate rehearsal on the same saved configuration. This is not a claim that the service-loop cause
  was fixed or that every model run is deterministic.
- Memory recall recovered after one delayed read-only retry; an existing preference record proves storage.
  A2A required an explicit Activity follow-up after the initial Nutrition-only route. The portal labels its
  A2A cards Preview and returns `a2a_preview_call`, so the participant-facing portal surface is labelled
  preview regardless of the older general-availability wording in 4.16a.
- The pre-existing seven-prompt matrix and automatic response metrics are not a new full evaluation.
  The [coverage record](content/admin/ADMIN-SETUP.md#navigator-walkthrough-coverage) distinguishes recoveries,
  facilitator identity, unverified attendee permissions, and the optional Fabric step not rerun here.
- The final KB binding check saved `wxyz` v8 on the existing `livewell-guides-kb-mcp` connection without
  altering its instructions, model, remaining tools, memory or guardrail. Saved YAML, not the pre-save YAML
  view, confirmed the new binding. The prepared connection returned live retrieval results; the earlier
  generated-connection route remains a facilitator alternative only.
