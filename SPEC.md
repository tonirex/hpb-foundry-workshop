LiveWell Coach — Microsoft Foundry Workshop for HPB
Build brief for the coding agent (Microsoft Scout)
Version 1.4 · Validated Navigator journeys (1.1 adds §5.1 learning objectives and canonical Python scripts; 1.2 unifies Navigator pages; 1.3 separates evaluation from participant execution; 1.4 records native-canvas validation and tool prerequisites) · Owner: Antonia Chen (Sr Solution Engineer, Microsoft Singapore) Target repo: github.com/tonirex/hpb-foundry-workshop (MIT) Companion file: CODING-AGENT-PROMPTS.md — the standing prompt and per-phase kick-off prompts that reference this spec.

0. How to work from this brief
Read this whole file before writing anything. Then read the reference repos in §2 (in that order).
Install the Foundry Skill first: npx skills add https://github.com/microsoft/azure-skills --skill microsoft-foundry (and npx skills add microsoft/skills, selecting agent-framework-azure-ai-py, azure-ai, azure-ai-contentsafety-py). Follow its workflows for anything touching azd, hosted agents, evaluations or the Foundry MCP server.
Work one phase at a time (§15). Each phase is one PR. Finish the phase, run its verification, write the report, stop. I review and say "next".
If you have a signed-in az / azd / fab session, run every verification yourself against the configured azd environment. If you do not, stop and hand me the exact commands to run, then wait for the output.
Ask no questions. Make reasonable assumptions and record every one in ASSUMPTIONS.md with the phase number.
Anything preview, region-dependent or unverified gets a ⚠️ badge in the docs and a line in versions.md.
Small commits, conventional messages (feat(lab2): …, fix(fabric): …, docs(admin): …).
Never write a subscription ID, tenant ID, GUID, endpoint or key into a lab page or slide. Names only; values live in the azd environment file (§8).
1. Mission and non-negotiables
Mission. A one-day, hands-on Microsoft Foundry workshop for the Health Promotion Board (Singapore), ~20 mixed-skill participants (data engineers, architects, BI, data scientists, a few developers). Participants build LiveWell Coach — a citizen healthy-living agent — and extend it with Fabric IQ so it can use the Resident 360 the same cohort built in their earlier Fabric workshop.

Primary objective: showcase Microsoft Foundry capabilities. The narrative is secondary — name every lab by the capability; the story is only the sample data.

Non-negotiables:

Two rails: 🟢 Navigator (browser-only: Foundry portal, plus the hosted Agent Framework DevUI in Lab 4) and 🔵 Builder (Python scripts are canonical — one hands-on labN_*.py per lab written in cell form with # %% markers so it runs as a script or cell-by-cell in the VS Code / Codespaces interactive window; Lab 2 additionally has a separate, default-inactive evaluation code walkthrough; no committed .ipynb for the Foundry labs). The only notebooks in the repo are Fabric items that must run inside Fabric (load_resident360.ipynb). If a participant insists on a notebook, make notebooks renders .ipynb from the scripts with jupytext into an untracked folder. An Engineer appendix exists only for the hosted-deploy stretch.
Ten agentic patterns frame the whole day (§3.4); every lab makes at least two concrete.
Portable across two environments: a dry run in my MCAPS tenant/subscription, then a redeploy into an Azure sponsored subscription in a different Entra tenant. Redeploy = azd env new <name> + a parameter file + one Fabric script run + the tenant bootstrap runbook. Anything that differs between environments is a parameter or an env-file value — never an edit.
Single region: swedencentral for every resource, including the Fabric F2 capacity (§8.2). Never Southeast Asia.
Sponsorship-safe cost: ≈ US$83–166 for the day; budgets and teardown built in (§13). No PTU, no S1+ search, no partner models (Anthropic, Mistral, Cohere), no Databricks.
All data synthetic. No real residents. No copied HealthHub text — write original HPB-style guidance. No race or religion fields anywhere.
Preview-aware: Foundry IQ portal experience, Fabric IQ tool, ontology, memory, Toolboxes/Skills are preview — label them; keep validator checkpoints on GA paths.
Do not use the Foundry portal Workflows item (retiring 1 Dec 2026) — multi-agent is Microsoft Agent Framework / connected agents / function tools.
2. Read first (in this order) and what to inherit
Source	Inherit
github.com/tonirex/casepal-foundry-workshop (my previous workshop; read README.md, foundry-workshop-plan.md, content/admin/ADMIN-SETUP.md, content/README.md, content/labs/lab-00…05.md, content/assets/common/casepal_common.py, content/prompts/test-prompts.json, content/answer-keys/, demos/)	Repository layout; two-rail lab pages; README that leads with the Labs table and collapses the rest; facilitator run-of-show with checkpoint-to-move-on gates and backup plans; prompts/test-prompts.json as single source of truth; server-side answer keys; admin page with RBAC-by-role-ID script; agent naming <prefix>-<INITIALS>-<role> with a cleanup() guard that never deletes <prefix>-demo-*; common/*_common.py helper including its strict-mode schema fix and 5xx retry; Playwright demo recorder, screenshot capture, bulk demo-agent creation, builder-rail validation harness; mcp<2 pin.
github.com/tonirex/care-pal-foundry-workshop	Codespaces devcontainer; portal screenshot track; narrative-per-lab pattern.
github.com/stellistic/resident-360-data-workshop (the cohort's Fabric workshop; pin commit <PINNED_SHA>)	Scenario, persona Rahim, HPB vocabulary, data files (lab1-build-resident360/data/), ontology blueprint (lab4-ontology-dataagent/), data-agent instructions and question bank (lab4-ontology-dataagent/assets/data_agent_questions.md). MIT — vendor with NOTICE.md attribution.
github.com/MicrosoftLearning/mslearn-ai-agents (exercises 01–09)	Current API shapes: portal + Foundry Toolkit, function tools, MCP, 04 Foundry IQ, workflows-in-portal (do not use), Agent Framework, multi-agent, A2A.
github.com/microsoft/iq-series (Foundry-IQ cookbooks)	Knowledge-base creation with azure-search-documents==12.1.0b1.
github.com/microsoft-foundry/Foundry_Toolkit_for_VSCode_Lab	Hosted-agent scaffold → Agent Inspector → Docker → ACR → Foundry deploy.
github.com/PlagueHO/foundry-agentic-workshop	Group-lab provisioning, project-per-attendee mode.
github.com/corticalstack/awesome-foundry-nextgen (13-guardrails, 14-red-teaming)	Guardrail and red-team notebooks.
Forgebook notebook "Microsoft IQ in Foundry" (microsoft-foundry.github.io/forgebook)	Fabric IQ / OneLake as Foundry IQ knowledge sources (preview) — bridge spotlight demo.
Microsoft Learn: Fabric Lab 28 setup-ontology.ipynb (microsoftlearning.github.io/mslearn-fabric/Instructions/Labs/28-build-data-agent-ontology.html)	Ontology creation via Fabric REST from a notebook.
Microsoft Learn: "Use the Microsoft Fabric data agent with Foundry agents", "Add Fabric data agents to a Foundry agent with Fabric IQ", "Connect a Foundry IQ knowledge base to Foundry Agent Service", "Add guardrails to a hosted agent", "Foundry Agent Service limits, quotas, and regional support", "Azure AI Search regions list", "Rate limits, region support, and enterprise features for evaluation", Fabric REST "Items – Create Ontology", "Items – Create Data Agent", "Data Agent item definition", Microsoft.Fabric/capacities Bicep reference, Fabric CLI docs (microsoft.github.io/fabric-cli)	Verify every API call against these before writing it.
CasePal lessons to carry forward (all real bugs or gaps from the last delivery):

Use a real Foundry IQ knowledge base on Azure AI Search, not a File Search vector store.
OpenAI strict-mode function tools need additionalProperties: false and a complete required[]; use strict=False for free-form object arguments.
Exponential-backoff retry for transient 5xx on the Responses API.
A Lab-0 "ask for consent first" rule stalls scripted runs — prepend an in-band consent line in scripts.
Assert on semantic signals, not exact JSON paths or citation strings.
Use Foundry LLM-judge evaluators, not regex scorers.
Hosted deploy needs Foundry Project Manager — facilitator-only.
Pre-recorded demo videos and screenshot fallbacks saved the day when the portal glitched — keep the recorder.
3. Scenario, narrative and the ten patterns
3.1 LiveWell Coach
Answers citizens' healthy-living questions (food, exercise, sleep, screening reminders), grounds every answer in an HPB-style knowledge base, recommends nearby community activities, personalises on a synthetic citizen profile plus remembered preferences, refuses to diagnose or dose medication, and hands the citizen to a clinician or HealthHub when appropriate. Uses HPB terminology exactly as the Fabric cohort's data-agent instructions do: MVPA = moderate-to-vigorous physical activity minutes; Healthpoints = Healthy 365 rewards currency, redeemed as eVouchers; disengaged = is_disengaged = 1 (low steps AND no events attended AND a dropped programme); hazy = regional 24-hour PSI ≥ 55 (a regional context proxy, not individual exposure).

3.2 Two seats, one coach
Rahim, 61, Woodlands (North region) — the same synthetic resident the cohort met in the Fabric workshop: joined the National Steps Challenge but drifting, rarely logs meals, skips outdoor events on hazy days, dropped a programme, elevated glucose at his last screening. Ordinary citizen questions use Foundry IQ + profile tool + memory. The optional programme-fit exercise is the one exception: after reading his profile, the coach asks Fabric one aggregate question about his age band only, then finds a programme intake through the activities tool and waits for approval before registration. No name, resident_id, area, region, gender or screening risk is sent to Fabric.
Mei Lin, HPB programme officer (fictional) — asks programme-level questions ("which regions have the highest share of disengaged residents?") → the Fabric IQ tool (the published Fabric data agent). All her questions use Fabric; Rahim's individual profile never does.
Story arc: Fabric built the Resident 360 that sees Rahim (Unify → Govern → Personalise → Converse); Foundry builds the coach that talks to him (→ Coach & Act). One short chapter per lab in content/narrative/rahim.md; every beat tagged seat: citizen|officer and source: kb|profile|fabric|mcp|memory.
3.3 Data and vocabulary rules
Rahim is a real row: RESIDENT_00061 — region North, age band 60–64, screening risk High, National Steps Challenge low progress, one dropped programme, ≤ 2 attended events, is_disengaged = 1 — upserted by load_resident360.ipynb.
content/data/citizens.json (profile tool) is generated from resident_360, never hand-written, so profile answers and Fabric aggregates always agree.
One content/config/glossary.yaml (MVPA, Healthpoints/eVouchers, disengaged, hazy, the five region names) feeds the narrative, coach instructions and data-agent instructions.
The story quotes only numbers computed by scripts/validate-narrative.py (§11.1), never numbers seen in a portal run.
Any fabric beat is aggregate-only (region, age band, programme, event, challenge) and never names a resident_id.
3.4 The ten agentic patterns → LiveWell labs (README table; revisit all ten at close)
#	Pattern	Lab	Concrete example
1	Multi-Document Understanding	1	Structured intake of a screening summary + activity diary → JSON
2	Evidence-Based Decision Support	3	{advice, confidence, supporting_guides[], rationale, personalisation_flags[]}
3	Workflow Orchestration	3/4	Coach orchestrator → Nutrition + Activity specialists
4	Knowledge Retrieval	1	Foundry IQ knowledge base, citations mandatory
5	Explainability & Traceability	2	Citations, traces, evaluator scores, Monitor
6	Human-in-the-Loop Review	3	Approval before register_interest
7	Handling Uncertainty	2	Route to clinician / HealthHub; never dose medication; "insufficient information"
8	Institutional Memory	3	Agent memory of stated preferences and prior interactions
9	Collaboration Between Specialists	3/4	Nutrition + Activity + Programme-Insights specialists, one merged reply
10	Governance & Safety	2 + cross-cutting	Guardrails, evaluators, red-team scan, RBAC, Entra Agent ID
4. Agenda (fixed by HPB) and what is demonstrated where
Time	Block	Foundry capability shown	Demo / lab
9:00	What is Microsoft Foundry (30)	Unified platform: models, agents, tools, observability, governance	New Foundry portal tour; "where we left off" — the Fabric arc + "today we add Coach & Act"
9:30	Foundry Models (20)	Catalogue, Global Standard deployments, quota, reasoning effort, model × tool support	Why two models: gpt-5-mini (reasoning effort Low) for Labs 0-2, gpt-4.1-mini from Lab 3 because it supports OpenAPI, A2A and Fabric tools; read model and tokens in the trace
9:50	Foundry Agent Service (40)	Model + instructions + tools; managed runtime; multi-agent; memory; frameworks	Create LiveWell Coach in the portal; structured output
10:15	Micro-Lab 0 (15, all rails, portal)	First agent	Everyone ships livewell-<initials>
10:45	Tools & Knowledge (30)	Foundry IQ knowledge base; connectors; MCP; Fabric IQ tool	Two IQs on Rahim: guide question with citation; Mei's region question via their Fabric data agent
11:15	Control Plane — "CIO lab" (40)	Guardrails (input/output/tool), tracing, monitoring, evaluation, red teaming, identity, cost tracking	Trip a guardrail, open the trace, eval + red-team scorecard; checkpoint: name one policy you would require before production
11:55	Platform architecture (20)	Reasoning engine / runtime / tools + knowledge / app layer; identity + observability	"Two IQs, one agent" diagram — their medallion on the left, Foundry on the right
12:15	Lunch		
1:15	Agent Framework & multi-agent (40)	SDK agents, versioning, orchestration patterns	Lab 1 walkthrough (Builder preview of Lab 3 code)
1:55	Tools, MCP & integration (40)	MCP, approval workflows, OpenAPI, gateway; the three Fabric integration paths	Lab 3 walkthrough; activities MCP with approval
2:50	Evaluation, Guardrails & Security (40)	Built-in + custom evaluators, continuous eval, runtime controls, Entra Agent ID, auditability	Lab 2 walkthrough; compare two agent versions
3:30–4:05	Part A Build (35)		Lab 1
4:05–4:35	Part B Govern (30)		Lab 2
4:35–5:30	Part C Extend (55)		Lab 3 incl. the Fabric step; Lab 4 facilitator demo; bridge spotlight; close on the ten patterns and the extended arc
Logistics to state in the README and deck: participants bring personal laptops (WOG devices cannot sign in to external Entra tenants); guest Wi-Fi slide; Authenticator registration at first sign-in.

5. Lab specification
Every lab page (content/labs/lab-0N.md): shared objective · Foundry features covered · story chapter · 🟢 Navigator and 🔵 Builder sections · checkpoint (nothing to submit: a collapsed Expected output block with screenshots and a short explainer; facilitator reference answers in content/answer-keys/) · troubleshooting · "Where next" footer. Navigator is the single screenshot-led portal procedure on that page, with native copyable blocks for every required instruction, prompt, schema and attachment. Canonical sources generate these blocks with scripts/sync-lab-blocks.py; the OpenAPI exception stays owned by scripts/sync-openapi-block.py. PORTAL-TRACK.md and lab-0N-portal.md retain compatibility links only. Unillustrated steps are explicitly text-only; retake existing screenshots only when out of date.

Lab 1's optional multi-document intake uses a separate agent and the generated intake schema, matching Builder; it must not replace the main coach's knowledge-answer schema. Lab 4 includes browser hands-on DevUI and hosted-agent chat, while deployment remains facilitator-only. Sequential and hosted runs return merged evidence JSON; hand-off ends with the Activity specialist's answer, not a merged-JSON guarantee. These distinctions apply to the learning evidence and module cards below.

Lab 2 separates doing from reviewing: `lab2_govern.py` runs the guardrail ladder and traces, never batch evaluation. Participants read `lab2_evaluate.py` as a code step-through and inspect a facilitator-prepared comparison; they must not launch evaluation batches during the workshop because multiple judges per row can exhaust shared quota and exceed the lab time. The separate script requires explicit terminal `--run`; default execution and notebook Run All make no cloud calls. Its shared scores belong to the named evaluated versions, not to each participant's agent.

Navigator reuses `livewell-guides-kb-mcp` under Available knowledge bases; the facilitator's alternative
Connect to Foundry IQ flow selects `livewell-search` first and may create a connection. Preparation also
includes a facilitator-created Anonymous OpenAPI connection, `livewell-profile-openapi`, before Lab 3. Anonymous
authentication does not remove that portal prerequisite. Its name is configurable, its target comes from
the selected environment, and readiness validation is read-only until a supported create contract is documented.

Lab 3 discovery is read-only and explicitly requests profile → knowledge retrieval → activity lookup.
Verify retrieved source evidence and one complete JSON object, then send `lab3_signup_confirm` separately
and approve the proposed write once. Do not silently accept the first of several concatenated objects.
Memory is checked in a new conversation after its update delay, with stored-preference evidence. Optional
A2A routing is verified from actual calls; a merged meal/exercise answer alone is insufficient. If only
Nutrition was called, the documented Activity follow-up may complete the two-turn demonstration. Label
the current portal A2A surface preview, and keep recovery runs distinct from first-attempt successes.

Lab	Title (capability first) · time	Build	Checkpoint
0	Setup & first agent · 15 min · morning, portal, all rails	Sign in; portal tour; create livewell-<initials> prompt agent (model + instructions + playground) on gpt-5-mini, reasoning effort Low, no tools; read the trace	Agent introduces itself, states it is not a doctor, refuses to diagnose
1	Agents & Knowledge — Foundry IQ · 40 min · Part A	Attach the shared Foundry IQ knowledge base (portal: Add → Available knowledge bases → prepared connection; Builder: same MCP knowledge-base connection in code); structured JSON contract {intent, risk_level, route, cited_sources, personalisation_flags}	"What should I eat to manage pre-diabetes?" cites ≥ 1 knowledge-base document and invents no source
2	Guardrails, Evaluations & Tracing · 40 min · Part B	Apply an RAI policy (content-safety categories incl. self-harm, Prompt Shields direct + indirect, groundedness detection, medication-dosage blocklist); re-run four red-flag prompts (extreme fasting, medication dosage, injected activity flyer, "show me another resident's profile"); inspect traces in Foundry + App Insights; read the separate evaluation code and review the facilitator's completed comparison on content/eval/livewell-eval.jsonl (30 rows: groundedness, relevance, task adherence, tool-call accuracy, intent resolution + custom "advice matches known conditions"). No participant batch during the workshop. Facilitator-only: AI Red Teaming Agent via the SDK path (≈ US$42/scan documented); participants may run a "lite" scan (10 prompts × 2 strategies) only if enabled	Injected flyer prompt is blocked or ignored AND participant explains a trade-off in the shared comparison, identifying versions, groundedness and judged-row counts
3	Tools, MCP & Memory — hyper-personalisation · 40 min · Part C	get_citizen_profile(resident_id) function tool (Builder) / OpenAPI tool (Navigator) over the resident_360-shaped extract; activities MCP server (content/assets/mcp-activities/, FastMCP, mcp<2, find_activities(area, condition_friendly), register_interest with human approval); memory for stated preferences; connected agents (Coach → Nutrition + Activity specialists). Fabric step (optional, 15 min, gated on FABRIC_BRIDGE=true): add the published Resident360 Ontology Agent as a Fabric IQ tool (Navigator: Add tool → Fabric IQ → pick from the OneLake Catalog; Builder: same in code); optional function tool calling a Fabric ML /score endpoint if present; instructions route programme questions to the Fabric tool and citizen questions to Foundry IQ + profile, and never ask Fabric about an individual	Compound question invokes ≥ 2 tools/agents (trace); reply tailored to Rahim's conditions; registration waits for approval. Fabric step: trace shows the Fabric IQ MCP call answering "Which regions have the highest share of disengaged residents?" while "what should I eat?" is answered from the knowledge base; region figures match validate-narrative.py ground truth; no resident_id in the Fabric answer
4	Multi-agent & Hosted deploy · 30 min · browser hands-on + facilitator deploy	Microsoft Agent Framework sequential/handoff orchestration in browser DevUI or Builder; versioning; facilitator hosted deploy with rai_config; hosted-agent chat and tracing	Sequential/hosted returns cited evidence JSON; hand-off ends with Activity's answer and a visible route. Only deployment requires Foundry Project Manager
Bridge spotlight	10 min · facilitator · slides + optional Forgebook notebook	"Two IQs, one agent": their medallion (resident_360, semantic model, ontology, data agents, ML endpoint) → Foundry (Foundry IQ for guides, Fabric IQ tool for programme questions, profile + activities tools, memory, guardrails, evaluations, hosted deploy); OneLake Files as a Foundry IQ source; ontology MCP server and Fabric-as-Foundry-IQ-source as preview options; extended arc	Slides-only when the Lab 3 Fabric step is live; full demo when it is not
5.1 Learning objectives per lab (use verbatim as the "shared objective" line on each lab page and module card)
Lab	Topics covered	Key learning objective (one sentence)	Demonstrated by	Patterns	Story beat
0 Setup & first agent	Foundry portal, resource/project, RBAC (Foundry User vs Project Manager), model deployments, reasoning effort, prompt agent = model + instructions, playground, versions, traces	A Foundry agent is a model plus instructions, and instructions alone can make it safe; every answer leaves a trace you can inspect	Everyone creates livewell-<initials> in the portal on gpt-5-mini, pastes the instructions block, sends Hi and Am I diabetic?, and reads the model, instructions and tokens in the trace	sets up #10	Rahim opens the coach for the first time
1 Agents & Knowledge — Foundry IQ	Foundry IQ knowledge base on Azure AI Search, indexed knowledge source, agentic retrieval + reasoning effort, retrieval/answer instructions, citations, MCP connection to the agent, structured outputs, refusal on absence	Ground every answer in curated knowledge with verifiable citations, never invent a source, and return machine-routable JSON	Navigator: Add → Available knowledge bases → prepared shared KB; Builder: same KB MCP connection in code; response format JSON {intent, risk_level, route, cited_sources, personalisation_flags}; "what should I eat to manage pre-diabetes?" → cited guide; "which supplement should I take?" → guide is silent, route to clinician	#1, #4	Rahim: "my screening says my glucose is high — what should I eat?"
2 Guardrails, Evaluations & Tracing	RAI policy (content-safety categories incl. self-harm, Prompt Shields direct + indirect, groundedness detection, medication-dosage blocklist); tracing in Foundry + App Insights (tool calls, tokens, cost); built-in + custom evaluators; batch-evaluation code walkthrough; compare two agent versions; AI Red Teaming Agent (facilitator, SDK)	Safety is measured, not assumed: apply guardrails, prove behaviour with evaluators, and make every decision auditable in a trace	Bare-vs-guarded contrast on four red-flag prompts (extreme fasting, medication dosage, injected flyer, "show me another resident's profile"); open the trace of a blocked and an allowed run; read evaluation code without running it and compare the facilitator's completed 30-row v1/v2 results; facilitator red-team scorecard	#5, #7, #10	A pasted activity flyer hides an injection; Rahim asks about doubling his medication
3 Tools, MCP & Memory — hyper-personalisation (+ Fabric step)	Function/OpenAPI tool (get_citizen_profile), MCP tool with approval-before-write (activities), memory, connected agents (Coach → Nutrition + Activity), tool routing via instructions, Fabric IQ tool (published Fabric data agent, OneLake Catalog, MCP, identity passthrough)	An agent that acts: personalise on governed data, take real actions with a human in the loop, delegate to specialists, and route each kind of question to the right tool	Profile tool → advice tailored to Rahim's age band, risk and hazy-day preference; MCP → find_activities then register_interest behind an approval card; memory → "I prefer mornings" respected next turn; compound question fires ≥ 2 tools/agents; Fabric step: Mei's "which regions have the highest share of disengaged residents?" answered via the Fabric IQ MCP call, figures match ground truth, no resident_id, citizen question still goes to the KB	#2, #3, #6, #8, #9	Rahim discovers grounded indoor options near Woodlands, then separately confirms one and approves the write; Mei: the programme question
4 Multi-agent & Hosted deploy (browser hands-on / facilitator deploy)	Microsoft Agent Framework orchestration, agent versioning, hosted agents (container → ACR → Agent Service via azd ai agent / Foundry Toolkit), rai_config, hosted-agent tracing, Entra agent identity, Foundry User vs Project Manager ceiling	From playground to production: the same agent behind two doors (portal for people, endpoint for systems), governed by the same policy	Participants run browser DevUI or Builder and chat with the hosted agent; sequential/hosted returns cited evidence JSON, while hand-off ends at Activity. The facilitator deploys and explains the publish permission boundary	#3, #9, #10	LiveWell Coach goes live in the (simulated) Healthy 365 channel
Bridge spotlight (facilitator)	Foundry IQ vs Fabric IQ positioning; OneLake as a Foundry IQ source; ontology MCP server; Fabric data agent / ontology as Foundry IQ sources (preview); the three Fabric integration paths and their prerequisites	Know when to reach for Foundry IQ (documents and knowledge) versus Fabric IQ (governed business data and ontology), and how to connect them	"Two IQs, one agent" diagram over their own Resident 360 estate; optional Forgebook notebook	—	Unify → Govern → Personalise → Converse → Coach & Act
CIO lab (11:15, everyone, no build)	Control Plane: fleet view, policies, guardrails, evaluations, traces, quota, cost & usage, Entra Agent ID, publish RBAC	Governance in plain language: identity decides who builds, RBAC who publishes, guardrails what the agent may attempt, evaluators whether behaviour is acceptable, traces make it defensible	Facilitator tour of the Control Plane surfaces; checkpoint: each table names one policy they would require before production	#10	—
Red-flag and canned prompts live once in content/prompts/test-prompts.json (with prompt_id, expected route/flags); answer keys reference them by id and never ship to participants.

6. Architecture and Foundry components
Rahim (citizen)  ─┐                                   ┌─ Foundry IQ knowledge base (Azure AI Search, Blob/OneLake indexed source, agentic retrieval, citations)
                  ├─► LiveWell Coach (Foundry Agent Service, gpt-4.1-mini) ─┼─ Function/OpenAPI tool: get_citizen_profile (resident_360 extract)
Mei Lin (officer) ┘      │ memory · guardrails (RAI policy) · tracing         ├─ MCP tool: activities server (Container Apps) — approval before write
                         │ evaluations · red team · Control Plane            ├─ Fabric IQ tool: published Fabric data agent (OneLake Catalog → MCP, identity passthrough)
                         └─ Specialists: Nutrition · Activity · Programme-Insights
Fabric (F2, same tenant, swedencentral): workspace "HPB Resident 360" → lh_resident360 (7 Delta tables) → resident_ontology (4 entities / 5 relationships) → Resident360 Ontology Agent (published)
Components demonstrated (put this as the "Foundry features you will touch" slide, grouped Build / Govern / Extend):

Layer	Component	Status
Platform	New Foundry portal, resource + project, RBAC (Foundry User / Project Manager), agent identity	GA
Models	Catalogue, Global Standard deployments, quota, gpt-5-mini, gpt-4.1-mini, text-embedding-3-small	GA
Agent Service	Prompt agents, playground, structured outputs, versions, connected agents / Agent Framework multi-agent, memory (preview), hosted agents (azd ai agent, Foundry Toolkit, rai_config)	GA / preview
Foundry IQ	Knowledge base on Azure AI Search, Blob/OneLake indexed source, agentic retrieval (reasoning effort), retrieval + answer instructions, citations, MCP connection	API GA, portal preview
Foundry Tools	Function tool, OpenAPI tool, MCP tool with approval-before-write, Fabric IQ tool (preview), optional Bing grounding / Code Interpreter; Toolbox + Skills mentioned	GA / preview
Guardrails & controls	Content-safety categories, Prompt Shields (direct + indirect), groundedness detection, blocklist, RAI policy on prompt and hosted agents	GA
Observability	Tracing (App Insights), tool-call and token/cost per run, Monitor; evaluations (built-in + custom, batch, compare versions; continuous eval mentioned); AI Red Teaming Agent via SDK	GA / preview
Control Plane	Fleet view, policies, quota, cost & usage, Entra Agent ID, publish RBAC — the "CIO lab"	GA / preview
Developer loop	Foundry Toolkit for VS Code, Foundry Skill for coding agents, Codespaces, Playwright demo kit	GA
7. Repository layout
.
├── README.md                          ← Labs table first; rail picker; ten-pattern table; everything else collapsed
├── foundry-workshop-plan.md           ← facilitator run-of-show (agenda §4, gates, backup plans, demo prompts)
├── ASSUMPTIONS.md · CHANGELOG.md · versions.md · LICENSE (MIT) · NOTICE.md (Resident 360 kit attribution)
├── AGENTS.md                          ← how coding agents should work in this repo
├── .devcontainer/                     ← Codespaces: Python 3.13, uv, az, azd, fab, Docker-in-Docker
├── azure.yaml                         ← azd project (services: mcp-activities, hosted-agent-example)
├── infra/
│   ├── main.bicep + modules/          ← RG-scoped: Foundry account/project/deployments, AI Search, storage, App Insights, ACR, ACA env, Fabric F2 capacity, RBAC, budget
│   └── env/mcaps.bicepparam · env/sponsor.bicepparam
├── scripts/
│   ├── preflight.sh · provision.sh · cost-guardrails.sh · seed-attendees.sh · teardown.sh · render-values.py
│   ├── build-kb.py                    ← Foundry IQ knowledge base over content/knowledge
│   ├── validate-narrative.py · smoke-test.py · validate-builder-rail.py
│   ├── fabric/deploy.sh · 10-workspace.sh · 20-lakehouse-load.sh · 30-ontology.py · 35-graph-refresh.py · 40-data-agent.py · 90-write-env.py
│   └── tenant/create-lab-users.sh
├── admin/ADMIN-SETUP.md · TENANT-BOOTSTRAP.md · screenshots/
├── content/
│   ├── config/workshop.yaml · glossary.yaml · values.md (generated)
│   ├── narrative/rahim.md             ← six chapters, beat tags
│   ├── knowledge/livewell-guides/     ← 8–12 original guides (md + pdf): healthy plate, physical-activity guideline 150–300 min/week, Nutri-Grade explainer, sodium & sugar tips, exercise by condition, sleep, screening schedule, FAQ
│   ├── data/resident360/              ← vendored kit files (pinned commit) + activity_daily.csv
│   ├── data/citizens.json (generated) · activities.json (40+ activities across planning areas) · flyer-injected.md
│   ├── prompts/test-prompts.json      ← single source of truth
│   ├── eval/livewell-eval.jsonl (30 rows) · evaluators/advice_matches_conditions.py
│   ├── fabric/ontology.blueprint.yaml · data-agent-instructions.md · question-bank.md · reference-answers.json (generated)
│   ├── labs/lab-00.md … lab-04.md · fabric-step.md · bridge-spotlight.md · PORTAL-TRACK.md · lab-0N-portal.md
│   ├── answer-keys/*.json             ← facilitator reference
│   └── assets/
│       ├── common/livewell_common.py  ← the one helper that calls Foundry (strict-schema fix, 5xx retry, consent line)
│       ├── lab1_knowledge.py · lab2_govern.py · lab3_tools.py · lab4_multiagent.py (canonical; `# %%` cells; `python labN_*.py` or run cells in VS Code)
│       ├── lab2_evaluate.py           ← read-only code walkthrough by default; separate opt-in facilitator evaluation
│       ├── Makefile: `make notebooks` (jupytext → .ipynb, untracked) · `make validate` · `make clean-agents`
│       ├── load_resident360.ipynb     ← Fabric notebook: 5 Delta tables + pinned Rahim row
│       ├── mcp-activities/            ← FastMCP server, Dockerfile, deploy to ACA
│       └── hosted-agent-example/      ← azd ai agent scaffold with rai_config
├── demos/                             ← Playwright recorder, screenshot capture, create-demo-agents.py, DRY-RUN-<date>.md, NARRATIVE-VALIDATION-<date>.md
└── deck/LiveWell-Foundry-Workshop-Day1.pptx (+ build script)
8. Infrastructure and environments
8.1 azd environments
mcaps (dry run) and sponsor (delivery). .azure/<env>/.env is the single source of truth for every output: project endpoint, search endpoint, capacity name, Fabric workspace ID, ontology ID, data-agent ID, Fabric IQ connection ID, MCP URL. Fabric scripts read from and write back to it (90-write-env.py).
infra/env/mcaps.bicepparam and sponsor.bicepparam differ only in subscription, capacity admins (UPNs in that tenant), SKU caps and tags. Same template, same azure.yaml.
MODE=shared-project | project-per-attendee (default shared: attendees own agents livewell-<INITIALS>-<role> in one project).
FABRIC_BRIDGE=true|false (default true; when false the profile tool reads the local citizens.json and the Fabric step is skipped).
8.2 Region rule
One location parameter, default swedencentral, applied to every resource including the Fabric capacity. Validated 25 Sep 2026: Foundry project + Agent Service ✅; model-router and all needed models Global Standard ✅; Fabric all workloads incl. ontology + data agent ✅ (EU → no cross-geo AI setting strictly required); Azure AI Search agentic retrieval + semantic ranker incl. medium reasoning effort ✅; agent-playground / batch / risk-safety evaluators and Groundedness Pro ✅; hosted agents ✅. Not co-located: the portal red-teaming run (East US 2 / North Central US only) → run red teaming via the azure-ai-evaluation SDK path. Documented fallback: northcentralus. East US 2 is ruled out (new AI Search services capacity-blocked). scripts/preflight.sh must fail if the configured region lacks any row above.

8.3 Resources (infra/main.bicep, RG rg-livewell-workshop-<env>)
Foundry account aif-livewell-<env> + project livewell-workshop; deployments gpt-5-mini (default, Labs 0-2 and specialists, reasoning effort Low), gpt-4.1-mini (tools: Lab 3 coach on, because gpt-5-mini does not support OpenAPI, A2A, Fabric or function tools), text-embedding-3-small — Global Standard, TPM capped (400K / 200K / 100K for 6 attendees), no PTU. No model-router: the Sponsorship subscription (quota Tier 0) does not offer it (ASSUMPTIONS.md 9.1).
Azure AI Search Basic srch-livewell-<env> (parameter to choose the Serverless Developer tier; never S1+ by default); agentic-retrieval plan left on Free until the allowance is hit.
Storage account (knowledge blobs), Application Insights (connected to the project), ACR Basic + Container Apps environment (MCP server; hosted agent for Lab 4).
Fabric capacity fablivewell<env>: Microsoft.Fabric/capacities@2023-11-01, sku { name: 'F2', tier: 'Fabric' }, properties.administration.members = [facilitator UPNs]; register Microsoft.Fabric first; same RG so azd down removes it; paused outside sessions (az fabric capacity suspend|resume).
Managed identities + RBAC: Foundry User for attendees (role ID 53ca6127-db72-4b80-b1b0-d745d6d5456d), Foundry Project Manager for facilitators (eadc314b-1a2d-4efa-be10-5d325db5065e), Search Index Data Reader for the project identity, Cognitive Services User for the search identity.
Azure Budget with alerts at US$150 and US$300; tags workshop=livewell, env=<env>.
8.4 Scripts
preflight.sh (provider registration for Microsoft.Fabric, Microsoft.CognitiveServices, Microsoft.Search, Microsoft.App; Fabric CU quota; Foundry model quota in region; AI Search Basic creatable in region; Fabric admin rights; prints quota-request links) · provision.sh (azd provision wrapper) · cost-guardrails.sh · seed-attendees.sh (Entra lab accounts or guests → Foundry User; Fabric workspace Viewer; read on the data agent) · render-values.py → content/config/values.md · teardown.sh (azd down --purge, fab rm <ws>.Workspace -f, pause/delete capacity). All idempotent (fab exists / GET-before-create).

9. Minimal Resident 360 on Fabric (scripts/fabric/deploy.sh, ~30–45 min)
Step	Tooling	Detail
10 workspace	Fabric CLI (pip install ms-fabric-cli; fab auth login user/SP/MI)	fab create "HPB Resident 360.Workspace" -P capacityname=fablivewell<env>; fab acl set facilitators Admin
20 lakehouse + data	fab create lh_resident360.Lakehouse; fab cp content/data/resident360/* …/Files/; fab import + fab start load_resident360.ipynb; poll until tables exist	Five Delta tables: resident_360 (wide gold: region, age band, steps, MVPA, sleep, meal stats, Healthpoints, screening risk, is_disengaged, region_is_hazy), dim_region, dim_event_occurrence (occurrence grain event_occurrence_id), fact_event_attendance (attended rows only), fact_programme_enrolment; upsert Rahim RESIDENT_00061 (§3.3); replace the Databricks activity table with generated activity_daily.csv
30 ontology	Fabric REST POST /v1/workspaces/{ws}/ontologies with definition parts rendered from content/fabric/ontology.blueprint.yaml (definition.json, .platform, EntityTypes/{id}/definition.json, EntityTypes/{id}/DataBindings/*.json, RelationshipTypes/{id}/definition.json); model on Learn Lab 28 setup-ontology.ipynb; poll the LRO	resident_ontology: entities Resident, Region, EventOccurrence, Programme; relationships livesIn, attended, heldIn, enrolledIn, droppedOut; first binding non-timeseries
35 graph refresh	Script if the API allows; otherwise a documented one-click (graph model resident_ontology_graph_* → Schedule → Refresh now); wait for Completed	Skipping this makes the data agent fail with a backend graph error
40 data agent	REST POST /v1/workspaces/{ws}/dataAgents with draft and published stage parts + publish_info.json (or the Fabric data agent Python SDK from a notebook)	Resident360 Ontology Agent; instructions = content/fabric/data-agent-instructions.md (aggregate-only, HPB vocabulary, glossary-driven); verify it is published
90 write env	Write workspace/ontology/data-agent IDs and workspace URL to .azure/<env>/.env	Lab pages use names only
Prerequisites (state in ADMIN-SETUP.md): paid F2+ (trial refused); full-Fabric-stack region; tenant settings (§12.2); the Fabric data agent, its sources and capacity in one region; Foundry project and Fabric workspace in the same Entra tenant, participants signed in with the same account to both; user identity only (no service principal) for the Fabric IQ tool at runtime.

10. Foundry ↔ Fabric IQ connection
Portal: agent → Add tool → Fabric IQ → OneLake Catalog → pick Resident360 Ontology Agent (published agents only appear) → creates a project connection. Needs Foundry Project Manager. Script it where the SDK allows; otherwise a two-minute runbook step with screenshots. Write the connection ID to the env file; participants add the tool to their own agents (Foundry User + read on the data agent is enough). Agent instructions must include explicit tool guidance ("for programme-level questions about regions, age bands, programmes, events or challenges, use the Fabric tool; never ask it about an individual").

11. Validation and proof
11.1 scripts/validate-narrative.py — narrative ↔ Fabric data agent gate (Phase 3b, dry run, every redeploy)
Layer	Checks	Fails when
Static	Every beat has seat + source; every fabric beat ↔ test-prompts.json entry ↔ question-bank entry; citizen beats may use source: fabric only for the single age-band cohort question; glossary terms consistent across narrative, coach instructions, data-agent instructions; no resident_id in Fabric questions/expected answers	Orphan beat, vocabulary drift, ID leak
Data	Rahim's row exists and matches citizens.json and the prose; every attendance/enrolment row joins to resident, event occurrence, programme; region names match dim_region; reference answers recomputed → content/fabric/reference-answers.json	Any mismatch or broken join
Live	Per fabric prompt: call the published data agent 3× (user token) → grouped, no resident_id, top-N regions/counts match reference (exact counts, ±1 rank), latency logged (expect 30–90 s, flag > 120 s); same question via the LiveWell agent → trace shows the Fabric IQ MCP call; one citizen prompt → no Fabric call	Any run outside tolerance; missing/unexpected tool call
Output	demos/NARRATIVE-VALIDATION-<date>.md; non-zero exit blocks Phase 4	—
Human table-read (Phase 1 review, 3b, dry run): read the six chapters aloud with validated answers pasted in; for every fabric beat answer "why would this seat ask Fabric here, and what does the coach do with the answer?"; cut beats without a crisp answer. Mei has ≤ 3 questions, each tied to a lab checkpoint (e.g. "regions with highest share of disengaged residents" → Lab 3 Fabric step; the multi-hop dropped-programme → attended → held-in-region question → bridge spotlight). Rahim's core chapters do not depend on Fabric. His optional programme-fit beat uses one age-band-only aggregate and remains gated by FABRIC_BRIDGE.

11.2 Other proofs
scripts/validate-builder-rail.py (CasePal style): runs every lab script with INITIALS=test, asserts semantic signals, tears down its agents, prints a pass/fail table.
scripts/smoke-test.py: end-to-end — guide question cites a KB doc; injected flyer blocked; compound question fires ≥ 2 tools; Mei's question answered via the Fabric IQ MCP call (trace); hosted endpoint (if deployed) returns JSON with a citation; prints pass/fail and total cost since provision.
demos/: Playwright demo recorder (one video per lab), screenshot capture for the portal track, create-demo-agents.py (livewell-demo-*, with the cleanup guard), DRY-RUN-<date>.md template.
12. Admin runbooks
12.1 admin/ADMIN-SETUP.md
T-10 quota requests (Fabric CU in region, Foundry models) · T-7 tenant settings + preflight.sh · T-3 azd provision (~15 min) → scripts/fabric/deploy.sh (~30–45 min) → Fabric IQ connection → build-kb.py → MCP deploy → seed-attendees.sh → smoke-test.py + validate-narrative.py · T-1 dry run, record demos · T-0 az fabric capacity resume, project endpoint + values sheet on screen · T+1 teardown.sh. Include the cost table (§13), the "what not to leave running" list, RBAC gotchas (Foundry User cannot deploy models, create connections or publish hosted agents), and backup plans (sign-in, quota → gpt-4.1-mini, KB missing → static guides, evaluators unavailable → pre-captured trace, MCP down → local server + tunnel, Fabric tool down → pre-recorded answer).

12.2 admin/TENANT-BOOTSTRAP.md (the sponsored subscription is in a different tenant)
First check whether the sponsorship offer permits the Azure "Change directory" transfer into my MCAPS tenant (subscription owner initiates, Entra admin in the destination accepts; CSP excluded; role assignments are lost and re-created) — if yes, this runbook is unnecessary.
Confirm Global Administrator / Fabric Administrator in the target tenant; tenant country Singapore; facilitator as a member account.
Fabric admin portal: Users can create Fabric items; Ontology item (preview); Fabric data agent; Users can use Copilot and other features powered by Azure OpenAI; cross-geo processing and storing for AI (enable even though Sweden Central is EU); Service principals can use Fabric APIs; Create workspaces scoped to the facilitator group. Allow up to an hour to propagate.
Azure: register providers; request Fabric CU quota (often 0 on a fresh subscription) and Foundry model quota in swedencentral.
scripts/tenant/create-lab-users.sh: 20 cloud-only lab accounts + a break-glass account (Graph; usage location SG; temporary passwords; security defaults for MFA — no Entra P1).
azd env new sponsor → preflight.sh → azd provision (capacity admins = UPNs in this tenant) → scripts/fabric/deploy.sh → Fabric IQ connection → seed-attendees.sh → smoke-test.py + validate-narrative.py → full second dry run. Everything carries over except GUIDs, RBAC, lab accounts and tenant settings — all re-created by scripts or this runbook.
13. Cost model and controls (US$ list, Sept 2026)
Line	Low (gpt-4.1-mini, Basic search, facilitator red team)	High (gpt-4.1, S1, Bing $35/1k)
Model tokens (20 × 150 runs × 3k in / 500 out, ×2 buffer)	12	60
Quality evaluations (model tokens, no surcharge)	4	4
Red teaming / safety evals (AI evaluations meter $20/$60 per 1M; 5 scans × 50 prompts × 4 strategies)	42	42
Azure AI Search, 120 h	12	40
Semantic ranker, Bing, Code Interpreter, hosted agents, ACR, storage/App Insights	~12	~18
Total	≈ 83	≈ 166
Every participant runs a full red-team scan	+126	→ ≈ 292
Fabric F2, 16 h active (≈ $0.36/h; ≈ $259/month if left on)	+6	+6
Controls: one shared search service and knowledge base (20 Basic services would be ~$1,475/month); gpt-5-mini default at reasoning effort Low, TPM caps, no PTU; Lab 2 batch evaluation prepared once by the facilitator, participants read code and shared results; red teaming facilitator-run (lite 10×2 for participants ≈ $17 total); Bing off by default; budgets $150/$300; capacity paused nightly; teardown.sh at T+1; agentic-retrieval plan on Free until needed.

14. Deliverable 2 — slide deck deck/LiveWell-Foundry-Workshop-Day1.pptx
python-pptx, 16:9, clean white/dark-blue; I merge it into my Microsoft Foundry master deck, so no generic platform slides. Slides with speaker notes: title · agenda (§4 table) · guest Wi-Fi placeholder · "Where we left off" (the Fabric arc + what today adds) · "The human thread" (Rahim and Mei chapters, one per lab) · "What we build today" architecture (§6) · "Foundry features you will touch" checklist grouped Build / Govern / Extend · one module card per lab (title = capability, duration, level, rails, story line, objective, features, checkpoint) · "Two IQs, one agent" bridge (3 slides: their estate → Foundry; Foundry IQ vs Fabric IQ when-to-use; the three Fabric integration paths with prerequisites) · guardrail & evaluation scorecard · cost & controls (§13) · getting started / resources (official repos) · close: the ten patterns + extended arc.

15. Phase plan (one PR per phase; stop after each)
Phase	You deliver	I verify in MCAPS	Acceptance
1 Spec & content	foundry-workshop-plan.md, ASSUMPTIONS.md, content/config/workshop.yaml + glossary.yaml, README, narrative/rahim.md (beat tags), knowledge guides, data (resident360/ vendored + activity_daily.csv, activities.json, flyer-injected.md; citizens.json generator), test-prompts.json, answer keys, lab pages + Fabric step + spotlight, fabric/ontology.blueprint.yaml + data-agent-instructions.md + question-bank.md, deck	Read-through + table-read	Links resolve; no GUIDs in lab pages; every lab has objective/features/story/rails/checkpoint/troubleshooting/where-next; ten patterns each mapped; Mei ≤ 3 questions
2 Infra	infra/ + azure.yaml + both .bicepparam, preflight.sh, cost-guardrails.sh, seed-attendees.sh, teardown.sh, render-values.py, admin/ADMIN-SETUP.md, admin/TENANT-BOOTSTRAP.md, scripts/tenant/create-lab-users.sh	azd env new mcaps → preflight.sh → azd provision → cost-guardrails.sh; then azd down and re-provision	What-if clean; green twice; budget alerts exist; capacity visible in Fabric admin portal
3 Minimal Resident 360	scripts/fabric/*, load_resident360.ipynb, blueprint renderer, data-agent create + publish, env write-back	Run deploy.sh; inspect in Fabric	5 tables; ontology 4/4 with instances; graph refresh Completed; data agent published and answers the region question; IDs in .azure/mcaps/.env
3b Narrative gate	validate-narrative.py, reference answers	Run 3× per question; table-read	All layers green; every Fabric beat survives the two questions
4 Labs code	livewell_common.py, lab scripts (# %% cell form, no committed notebooks), build-kb.py, mcp-activities/ (+ ACA deploy), hosted-agent-example/, RAI policy definition, livewell-eval.jsonl + custom evaluator, validate-builder-rail.py, Fabric IQ connection helper + runbook step	build-kb.py; deploy MCP; create the connection; validate-builder-rail.py with INITIALS=test	All lab scripts pass; KB citation; flyer blocked; compound question ≥ 2 tools; Fabric step routes correctly (trace)
5 Proof & demo kit	smoke-test.py, demos/ (recorder, screenshots, demo agents, cleanup guard), PORTAL-TRACK.md slots, values.md renderer wired, CHANGELOG.md, versions.md	Smoke test; record demos	Smoke test green; one video + screenshots per lab
6 Dry run fixes	Fix list from demos/DRY-RUN-<date>.md	Re-run everything; teardown.sh → re-provision → smoke test + narrative gate green again	Portability proven from an empty subscription
7 Sponsor tenant	(runbook execution; no new code unless a gap appears)	Bootstrap → azd env new sponsor → provision → Fabric deploy → connection → seed → smoke test → second dry run	Green in the sponsor tenant
Builder-rail code rules (apply in Phase 4): every labN_*.py is a linear, idempotent script in # %% cell form — a short markdown cell (as a comment block) before each step, one step per cell, canned prompts pulled by prompt_id from prompts/test-prompts.json, lines the participant should retype marked # 👉, genuinely open extensions marked # TODO (bonus), print() output ASCII-only (no emoji — Windows consoles) with a --verbose flag, --cleanup to delete the agents it created (guarded to livewell-<INITIALS>-*), and it must pass validate-builder-rail.py when run top to bottom with INITIALS=test. The .devcontainer includes the Python + Jupyter extensions so # %% cells run interactively in Codespaces, and sets PYTHONIOENCODING=utf-8. Lab pages show the script command first and "or open the same file and run it cell by cell" second.

The separate Lab 2 evaluation walkthrough is excluded from automatic live Builder validation. Its default and notebook cell execution must make no cloud calls; only an explicit terminal `--run` may evaluate. It reuses pinned versions without creating or deleting agents, so `--cleanup` explains that nothing was created to clean up. Keep evaluation results separate from the hands-on checkpoint and never automatically repeat a batch after an upload error.

Report format at the end of each phase: files created/changed · what was verified and how (commands + results) · what is unverified · what I must do manually (Entra accounts, quota, tenant settings, connection step, Wi-Fi code, screenshots) · new entries in ASSUMPTIONS.md and versions.md.

16. Values I will fill in (placeholders in workshop.yaml / .bicepparam)
<PINNED_SHA> of stellistic/resident-360-data-workshop · MCAPS subscription ID and tenant ID · sponsor subscription ID and tenant ID · facilitator UPNs per tenant · lab-account prefix and count (default hpb.lab01…20) · workshop date · guest Wi-Fi code · HPB participant count.
