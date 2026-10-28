LiveWell Foundry Workshop — prompts for the coding agent
Current target: tonirex/hpb-foundry-workshop. The phase prompts below are historical; SPEC.md A.14 takes precedence. Current participants choose one independent track, use inline Navigator screenshots and collapsed checkpoints/troubleshooting, and run no evaluations. Do not restore the retired intake exercise or closing spotlight. Operator demonstrations belong in content/admin/FACILITATOR-DEMOS.md.
Use with SPEC.md (= LiveWell-Foundry-Workshop-SCOUT-BRIEF.md v1.1). Commit both at the root of tonirex/livewell-foundry-workshop. Send Prompt A once at the start of every session (or put it in AGENTS.md / the agent's custom instructions), then one Prompt B per phase. After each phase: review the PR → merge → send the next Prompt B. Never send two phases at once.

Before Prompt 1: fill the placeholders in SPEC.md §16 — at minimum <PINNED_SHA> (the stellistic/resident-360-data-workshop commit to vendor) and the MCAPS subscription/tenant IDs — and create the empty private repo with SPEC.md, CODING-AGENT-PROMPTS.md, LICENSE (MIT) and .gitignore committed.

Prompt A — standing prompt (paste once per session)
You are a senior Microsoft Foundry solution engineer and workshop author working in the repository
tonirex/livewell-foundry-workshop. SPEC.md at the repo root is the complete, authoritative specification
for what we are building: a one-day Microsoft Foundry workshop for the Health Promotion Board (Singapore)
whose participants build "LiveWell Coach", a citizen healthy-living agent, and extend it with Fabric IQ
over a minimal Resident 360 on Microsoft Fabric.

Ground rules (all of them are also in SPEC.md §0–§1; they win over anything else you know):
1. Read SPEC.md in full before doing anything. Then read the reference repos listed in SPEC.md §2, in
   that order, and inherit exactly what §2 says to inherit — especially from tonirex/casepal-foundry-workshop.
2. First run: npx skills add https://github.com/microsoft/azure-skills --skill microsoft-foundry
   (and npx skills add microsoft/skills selecting agent-framework-azure-ai-py, azure-ai,
   azure-ai-contentsafety-py). Follow the Foundry Skill's workflows for anything that touches azd, hosted
   agents, evaluations or the Foundry MCP server.
3. Work ONE phase at a time (SPEC.md §15). A phase = one branch + one PR. Finish the phase, run its
   verification, write the report in the format at the end of §15, then STOP and wait for me.
4. If you have signed-in az / azd / fab sessions, run every verification yourself against the azd
   environment I name. If you do not, stop and give me the exact commands to run, then wait for the output.
   Never fake a verification result; mark anything you could not run as "unverified".
5. Ask no questions. Make reasonable assumptions and record each one in ASSUMPTIONS.md with the phase number.
6. Non-negotiables: two rails (Navigator = portal only; Builder = canonical Python scripts in "# %%" cell
   form, no committed .ipynb for Foundry labs); the ten agentic patterns frame the day; everything is
   portable across two azd environments (mcaps, sponsor) and two Entra tenants — anything that differs is a
   parameter or an env-file value, never an edit; single region swedencentral for EVERY resource including
   the Fabric F2 capacity (never Southeast Asia); sponsorship-safe cost (no PTU, no S1+ search, no partner
   models, no Databricks); all data synthetic, original HPB-style guidance, no race/religion fields; label
   every preview surface; never use the Foundry portal Workflows item.
7. Never write a subscription ID, tenant ID, GUID, endpoint or key into a lab page, slide or script
   constant. Lab pages use names; values live in .azure/<env>/.env and content/config/workshop.yaml.
8. Verify every API call against the Microsoft Learn pages listed in SPEC.md §2 before you write it; pin
   versions (ms-fabric-cli, azure-ai-projects>=2.0.0, azure-search-documents==12.1.0b1, azure-ai-evaluation,
   agent-framework, mcp<2, Python 3.13) and list preview surfaces in versions.md.
9. Small commits with conventional messages (feat(lab2): …, fix(fabric): …, docs(admin): …).
10. Keep the narrative secondary: every lab is named by the Foundry capability it teaches; Rahim (citizen)
    and Mei Lin (programme officer) are sample data, and the narrative-versus-data rules in SPEC.md §3.3
    and §11.1 are hard constraints.

Acknowledge by listing the SPEC.md section headings you have read and the reference repos you have opened,
then wait for the phase prompt.
Prompt B — per-phase kick-off prompts
Phase 1 — Spec & content
Do Phase 1 only (SPEC.md §15, row "1 Spec & content"), then stop and report.

Deliver on branch phase-1-content:
- foundry-workshop-plan.md: facilitator run-of-show mapped minute-by-minute to the agenda in SPEC.md §4,
  with a checkpoint-to-move-on gate per block and the backup plans from §12.1; demo prompts by prompt_id.
- README.md: one-line pitch; "Start here" Labs table (Lab 0–4 and the optional Fabric step) first; rail
  picker; the ten-patterns table from SPEC.md §3.4; everything else collapsed in <details>; logistics
  (personal laptops, guest Wi-Fi, Authenticator).
- content/config/workshop.yaml (names from SPEC.md §8.3 and §16 placeholders) and content/config/glossary.yaml.
- content/narrative/rahim.md: six chapters (Lab 0–4 + bridge), every beat tagged seat: citizen|officer and
  source: kb|profile|fabric|mcp|memory; Mei Lin has at most three questions, each tied to a lab checkpoint;
  Rahim's chapters never depend on Fabric; quote no numbers yet — leave {{ref:<question_id>}} placeholders
  that scripts/validate-narrative.py (Phase 3b) will fill from reference answers.
- content/knowledge/livewell-guides/: 8–12 original HPB-style guides (markdown + PDF): healthy plate,
  physical-activity guideline 150–300 min/week, Nutri-Grade explainer, sodium and sugar tips, exercise by
  condition (pre-diabetes, hypertension, high cholesterol), sleep, screening schedule, FAQ. Original text
  only; no HealthHub copy.
- content/data/: vendor the Resident 360 kit data files from stellistic/resident-360-data-workshop at
  <PINNED_SHA> into content/data/resident360/ with NOTICE.md; generate activity_daily.csv to replace the
  Databricks activity table; activities.json (40+ community activities across Singapore planning areas,
  condition_friendly flags, indoor/outdoor); flyer-injected.md (an activity flyer containing an indirect
  prompt injection); scripts/gen-citizens.py that will generate citizens.json from resident_360 (Rahim =
  RESIDENT_00061 per SPEC.md §3.3).
- content/prompts/test-prompts.json: single source of truth for every canned and red-flag prompt with
  prompt_id, seat, expected route/flags/tool.
- content/answer-keys/lab-00.json … lab-04.json (server-side validators referencing prompt_ids).
- content/labs/lab-00.md … lab-04.md, fabric-step.md, PORTAL-TRACK.md and
  lab-0N-portal.md with screenshot slots. Each lab page: shared objective (verbatim from SPEC.md §5.1),
  Foundry features, story chapter, Navigator section, Builder section (script command first, "or run the
  same file cell by cell" second), checkpoint, troubleshooting, "Where next" footer.
- content/fabric/ontology.blueprint.yaml (4 entities, 4 relationships per SPEC.md §9),
  data-agent-instructions.md (aggregate-only, glossary-driven) and question-bank.md.
- deck/build_deck.py producing deck/LiveWell-Foundry-Workshop-Day1.pptx per SPEC.md §14 with speaker notes.
- ASSUMPTIONS.md, CHANGELOG.md, versions.md (initial), .devcontainer/ (Python 3.13, uv, az, azd, fab,
  Docker-in-Docker, Python + Jupyter extensions, PYTHONIOENCODING=utf-8), AGENTS.md.

Acceptance (check before reporting): every relative link resolves; no GUID/endpoint anywhere in content/;
every lab page has all eight sections; all ten patterns map to a lab; every fabric beat has a matching
prompt_id and question-bank entry; Mei ≤ 3 questions; the deck builds without error.
Phase 2 — Infra
Do Phase 2 only (SPEC.md §15, row "2 Infra"), then stop and report. azd environment: mcaps.

Deliver on branch phase-2-infra:
- infra/main.bicep (resource-group scope) + modules for every resource in SPEC.md §8.3: Foundry account +
  project + deployments (gpt-5-mini default, gpt-4.1-mini tools, text-embedding-3-small; Global Standard;
  TPM capped), Azure AI Search Basic (parameter for Serverless Developer tier), storage, Application
  Insights connected to the project, ACR Basic, Container Apps environment, Fabric capacity
  (Microsoft.Fabric/capacities@2023-11-01, sku F2 / tier Fabric, administration.members from a parameter),
  managed identities and RBAC by role ID, Azure Budget with alerts at 150 and 300 USD, tags.
- A single location parameter (default swedencentral) used by every resource.
- azure.yaml (services: mcp-activities, hosted-agent-example), infra/env/mcaps.bicepparam and
  infra/env/sponsor.bicepparam (differ only in subscription, admins, caps, tags).
- scripts/preflight.sh: registers/checks Microsoft.Fabric, Microsoft.CognitiveServices, Microsoft.Search,
  Microsoft.App; Fabric CU quota in the configured region; Foundry model quota for the three deployments;
  AI Search Basic creatable in the region; caller is Fabric admin; fails with the quota-request links if any
  check fails. Assert the region matrix in SPEC.md §8.2.
- scripts/provision.sh, cost-guardrails.sh, seed-attendees.sh (lab accounts or guests → Foundry User; later
  Fabric workspace Viewer + data-agent read), teardown.sh (azd down --purge, fab rm workspace, pause/delete
  capacity), render-values.py (→ content/config/values.md from .azure/<env>/.env).
- scripts/tenant/create-lab-users.sh (Graph; 20 cloud-only users + break-glass; usage location SG).
- admin/ADMIN-SETUP.md (T-10…T+1 per SPEC.md §12.1, cost table, RBAC gotchas, backup plans) and
  admin/TENANT-BOOTSTRAP.md (SPEC.md §12.2, starting with the "Change directory" check).

Verification (run it, or hand me the commands): azd env new mcaps → scripts/preflight.sh →
az deployment group what-if → azd provision → scripts/cost-guardrails.sh; confirm the capacity is visible
in the Fabric admin portal; then azd down and azd provision again to prove idempotency. Report both runs.
Phase 3 — Minimal Resident 360 on Fabric
Do Phase 3 only (SPEC.md §15, row "3 Minimal Resident 360"; details in SPEC.md §9), then stop and report.
azd environment: mcaps.

Deliver on branch phase-3-fabric:
- scripts/fabric/deploy.sh orchestrating 10-workspace.sh, 20-lakehouse-load.sh, 30-ontology.py,
  35-graph-refresh.py, 40-data-agent.py, 90-write-env.py; every step idempotent (fab exists / GET before
  create) and re-runnable.
- content/assets/load_resident360.ipynb (the only committed notebook — it must run inside Fabric): loads the
  vendored files, writes the five Delta tables (resident_360, dim_region, dim_event_occurrence,
  fact_event_attendance attended rows only, fact_programme_enrolment), upserts Rahim RESIDENT_00061 exactly
  as SPEC.md §3.3 specifies, and prints row counts.
- 30-ontology.py: renders content/fabric/ontology.blueprint.yaml into Fabric REST definition parts and
  creates resident_ontology (4 entity types, 4 relationship types; first binding non-timeseries), polling
  the long-running operation; modelled on Microsoft Learn mslearn-fabric Lab 28 setup-ontology.ipynb.
- 35-graph-refresh.py: triggers the graph-model refresh if an API exists, else prints the exact one-click
  runbook step and waits for confirmation.
- 40-data-agent.py: creates AND publishes "Resident360 Ontology Agent" via POST
  /v1/workspaces/{ws}/dataAgents with draft + published stage parts and publish_info.json (or the Fabric
  data agent Python SDK), instructions from content/fabric/data-agent-instructions.md; verifies published.
- 90-write-env.py: writes workspace/ontology/data-agent IDs and URLs to .azure/mcaps/.env.
- scripts/gen-citizens.py wired to read resident_360 (via the lakehouse SQL endpoint or the loaded files)
  and emit content/data/citizens.json.

Verification: run deploy.sh end to end and report timings; confirm in Fabric: five tables with counts,
ontology with 4/4 and entity instances, graph refresh Completed, data agent published and answering
"Which regions have the highest share of disengaged residents?"; confirm IDs in .azure/mcaps/.env.
Phase 3b — Narrative gate
Do Phase 3b only (SPEC.md §15, row "3b Narrative gate"; details in SPEC.md §11.1), then stop and report.
azd environment: mcaps.

Deliver on branch phase-3b-narrative-gate:
- scripts/validate-narrative.py with the three layers in SPEC.md §11.1 (static, data, live) and a
  --layers flag; writes content/fabric/reference-answers.json and demos/NARRATIVE-VALIDATION-<date>.md;
  non-zero exit on any failure.
- Replace every {{ref:<question_id>}} placeholder in content/narrative/rahim.md and the lab pages with the
  computed reference values (rounded), via a --fill flag; never with values observed in a portal run.
- Latency logging for the live layer (expect 30–90 s per data-agent answer; flag > 120 s).
- Wire it into the Makefile (make validate) and into CI as a manual workflow_dispatch job.

Verification: run all three layers against the published data agent (three calls per fabric prompt) and
paste the resulting table into the report; list any beat you had to cut or rewrite and why.
Phase 4 — Foundry labs code
Do Phase 4 only (SPEC.md §15, row "4 Labs code"), then stop and report. azd environment: mcaps.

Deliver on branch phase-4-labs:
- content/assets/common/livewell_common.py: the one helper that calls Foundry — inherits CasePal's
  casepal_common.py fixes (strict-mode schema auto-fix, exponential-backoff retry on transient 5xx,
  in-band consent line), agent naming livewell-<INITIALS>-<role>, cleanup() that refuses to touch
  livewell-demo-* or livewell-workshop-*.
- content/assets/lab1_knowledge.py, lab2_govern.py, lab3_tools.py, lab4_multiagent.py following the
  Builder-rail code rules in SPEC.md §15 ("# %%" cells, comment-block explainers, prompts by prompt_id,
  "# 👉" retype lines, "# TODO (bonus)", ASCII-only output, --verbose, --cleanup). Makefile targets
  notebooks (jupytext → untracked .ipynb), validate, clean-agents.
- scripts/build-kb.py: Foundry IQ knowledge base on the Azure AI Search service over
  content/knowledge/livewell-guides (Blob indexed source; parameter for OneLake Files), retrieval and
  answer instructions, reasoning effort low, and the MCP connection to the project.
- content/assets/mcp-activities/: FastMCP server (mcp<2) with find_activities(area, condition_friendly)
  and register_interest (write) + Dockerfile + azd service definition for Container Apps; portal setup
  notes for read = no approval, write = approval required.
- content/assets/hosted-agent-example/: azd ai agent scaffold (Microsoft Agent Framework, Python) with
  rai_config referencing the RAI policy resource ID; README for the facilitator.
- Guardrail definition: RAI policy (content-safety categories incl. self-harm, Prompt Shields direct +
  indirect, groundedness detection, medication-dosage blocklist) as Bicep or script, attached to the
  deployments and referenced by hosted agents.
- content/eval/livewell-eval.jsonl (30 rows) and content/eval/evaluators/advice_matches_conditions.py
  (custom evaluator); Lab 2 script runs the built-in evaluators + custom one and compares two agent
  versions; facilitator-only red-team script via the azure-ai-evaluation SDK path with its cost printed.
- Lab 3 Fabric step: helper that adds the published Fabric data agent as a Fabric IQ tool by connection
  ID from the env file (or prints the two-minute portal runbook step if the SDK cannot), plus instructions
  routing programme questions to the Fabric tool and citizen questions to the KB/profile tool.
- scripts/validate-builder-rail.py: runs every lab script top to bottom with INITIALS=test, asserts
  semantic signals (KB citation present; injected flyer blocked or ignored; compound question ≥ 2 tool
  calls; Fabric IQ MCP call present for Mei's question and absent for Rahim's), tears down its agents,
  prints a pass/fail table.

Verification: build-kb.py; deploy the MCP server; create the Fabric IQ connection (needs Foundry Project
Manager — do it or hand me the step); run validate-builder-rail.py and paste the table. Everything the
scripts create must be gone afterwards except the shared KB, the MCP app and the connection.
Phase 5 — Proof & demo kit
Do Phase 5 only (SPEC.md §15, row "5 Proof & demo kit"), then stop and report. azd environment: mcaps.

Deliver on branch phase-5-proof:
- scripts/smoke-test.py per SPEC.md §11.2 (end-to-end pass/fail incl. the Fabric bridge and total cost
  since provision from Cost Management).
- demos/: Playwright demo recorder (one video per lab, Navigator rail), screenshot capture for
  PORTAL-TRACK.md slots, create-demo-agents.py (livewell-demo-* with the cleanup guard),
  DRY-RUN-<date>.md template modelled on CasePal's builder-rail validation report.
- render-values.py wired so content/config/values.md is regenerated after every deploy.
- CHANGELOG.md and versions.md brought current; README "facilitator" section linking everything.

Verification: run smoke-test.py and paste the table; record the Lab 0–3 demo videos and capture the
portal screenshots into their slots; list any lab page whose screenshot slot is still empty.
Phase 6 — Dry-run fixes
Do Phase 6 only (SPEC.md §15, row "6 Dry run fixes"), then stop and report. azd environment: mcaps.
Input: demos/DRY-RUN-<date>.md (my findings from the dry run) — fix every item, log each fix in
CHANGELOG.md, and re-run validate-builder-rail.py, validate-narrative.py and smoke-test.py.
Then prove portability: scripts/teardown.sh → azd provision → scripts/fabric/deploy.sh → build-kb.py →
MCP deploy → connection → smoke-test.py → validate-narrative.py, all from an empty resource group. Report
both the fix list and the second-run timings.
Phase 7 — Sponsor tenant redeploy
Do Phase 7 only (SPEC.md §15, row "7 Sponsor tenant"), then stop and report. azd environment: sponsor.
Walk admin/TENANT-BOOTSTRAP.md with me step by step (tell me which steps only I can do in the target
tenant), then azd env new sponsor → preflight.sh → azd provision → scripts/fabric/deploy.sh → Fabric IQ
connection → seed-attendees.sh → smoke-test.py → validate-narrative.py. No new code unless a gap appears;
if one does, fix it as a parameter or env value, never a tenant-specific edit, and add it to CHANGELOG.md.
Report format (end of every phase — copy into the PR description)
## Phase N report
Branch / PR:
Files created or changed:
Verification performed (commands + results):
Unverified (and why):
Manual steps for Antonia (tenant settings, quota, connection, accounts, Wi-Fi, screenshots):
New ASSUMPTIONS.md entries:
New versions.md entries (preview / region-dependent):
Cost since provision (if applicable):
Ready for: Phase N+1
Follow-up prompts you may need
"Continue Phase N: address these review comments: …" (paste the PR review).
"Re-run the Phase N verification and paste the updated table."
"Explain the trade-off you chose in ASSUMPTIONS.md item N.x and propose the alternative."
"Switch azd environment to sponsor and repeat the Phase N verification."
