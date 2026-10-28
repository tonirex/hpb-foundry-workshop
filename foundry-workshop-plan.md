# LiveWell Coach Foundry Workshop: Facilitator Run of Show

**Format:** one day, 9:00–5:30, agenda fixed by HPB. **Rails:** 🟢 Navigator (portal) and 🔵 Builder
(Python cells). **Outcome:** every participant builds the same LiveWell Coach, grounds it in Foundry IQ,
governs it, personalises it on Resident 360, and sees it answer Mei's programme question through the
Fabric data agent the cohort built in the Fabric workshop.

All prompts are referenced by `prompt_id` from [content/prompts/test-prompts.json](content/prompts/test-prompts.json).
All figures come from `python scripts/r360.py` (and, from Phase 3b, `scripts/validate-narrative.py`), never from a portal run.

## Facilitator stance

- Two seats, one coach. **Rahim** (RESIDENT_00061, 61, Woodlands, North) asks citizen questions →
  Foundry IQ + profile + memory. **Mei Lin** (programme officer) asks population questions → the Fabric IQ tool.
  Mei is the only reason the coach ever calls Fabric.
- Arc: Fabric **Unify → Govern → Personalise → Converse**; today Foundry adds **Coach & Act**. See
  [content/narrative/rahim.md](content/narrative/rahim.md).
- Vocabulary is fixed by [content/config/glossary.yaml](content/config/glossary.yaml): MVPA, Healthpoints/eVouchers,
  disengaged, hazy (PSI ≥ 55, regional proxy). Use it exactly.
- The coach never diagnoses, never doses medication and never shows another resident's data.

## T-0 checklist (07:30–08:45)

| Check | How | Pass |
|---|---|---|
| Fabric capacity resumed | `bash scripts/capacity.sh resume <env>` (see [ADMIN-SETUP](content/admin/ADMIN-SETUP.md)) | Capacity **Active** in Fabric admin portal |
| Values sheet on screen | `python scripts/render-values.py` → `content/config/values.md` (gitignored) | Project endpoint + agent names visible |
| Reference agents alive | Open the `livewell-demo-*` agents (`agent_naming.demo_agents` in `content/config/workshop.yaml`), send `lab0_hi` to `livewell-demo-lab0` | Introduces itself, says it is not a doctor |
| Fabric tool alive | Send `fabric_q_disengaged_regions` to `livewell-demo-fabric` | Trace shows the Fabric IQ call; North ranks first |
| Knowledge base alive | Send `lab1_prediabetes_eat` to `livewell-demo-kb` | ≥ 1 citation to `lg-05-eating-for-pre-diabetes` |
| MCP alive | `GET /health` on `ca-mcp-activities-<env>` | 200 |
| Demo videos ready | `demos/videos/<lab>-<date>.webm` from `python demos/record-demos.py` (T-1) open in a local player | Plays offline |
| Smoke test | `python scripts/smoke-test.py --demo-agents` | 11/11 PASS (includes the guardrail drift check, the demo-memory residue check and the A2A specialists check) |
| Demo memory clean | `python scripts/reset-demo-memory.py` (`--reset` if it flags residue after a red team) | Exit 0, 0 flagged |
| Lab 2 shared evaluation ready | Open the comparison prepared using [ADMIN-SETUP](content/admin/ADMIN-SETUP.md#lab-2-shared-evaluation), plus a recorded fallback | Completed v1/v2 results with agent versions, groundedness and judged-row counts; no participant batches |
| Wi-Fi slide | SSID/code from `content/config/workshop.yaml` | Correct values (TODO until confirmed) |

## Morning: L100, everyone (9:00–12:15)

| Time | Block | Facilitation notes | Demo prompt(s) | Checkpoint to move on |
|---|---|---|---|---|
| 9:00 | What is Microsoft Foundry (30) | New Foundry portal tour: models, agents, tools, observability, governance. "Where we left off": the Fabric arc, then "today we add Coach & Act". | — | Room can name the four Fabric arc steps and the new fifth one |
| 9:30 | Foundry Models (20) | Catalogue, Global Standard, quota, TPM caps, reasoning effort. Why two models: `gpt-5-mini` at Low reasoning effort for Labs 0-2, `gpt-4.1-mini` from Lab 3 because not every model supports every tool (OpenAPI, A2A, Fabric). Open a trace and read the model and tokens. | `lab0_am_i_diabetic` | Room can say why the Lab 3 coach changes model |
| 9:50 | Foundry Agent Service (25) | Agent = model + instructions (+ tools). Managed runtime, versions, multi-agent, memory, frameworks. Build LiveWell Coach live; show a structured output. | `lab0_hi`, `lab0_am_i_diabetic` | Agent states it is not a doctor and refuses to diagnose |
| 10:15 | **Micro-Lab 0** (15, all rails, portal) | Everyone creates `livewell-<initials>`, pastes the `base` instructions block from [coach-instructions.md](content/prompts/coach-instructions.md), sets Reasoning effort to Low, removes Web search if the template added it, sends two prompts and reads the trace. [Lab 0](content/labs/lab-00.md). | `lab0_hi`, `lab0_am_i_diabetic` | ≥ 80% of the room shows the refusal to diagnose. Stragglers pair with a neighbour |
| 10:30 | Break (15) | Helpers triage sign-in, Authenticator and RBAC. | — | — |
| 10:45 | Tools & Knowledge (30) | Foundry IQ knowledge base on Azure AI Search (agentic retrieval, citations, refusal on absence), connectors, MCP, the Fabric IQ tool. **Two IQs on Rahim:** guide question with citation, then Mei's region question via their own Fabric data agent. | `lab1_prediabetes_eat`, `lab1_supplement`, `fabric_q_disengaged_regions` | Room can say which IQ answered which question |
| 11:15 | Control Plane: "CIO lab" (40) | Guardrails (input/output/tool), tracing, monitoring, evaluation, red teaming, identity (Entra Agent ID), cost tracking. Trip a guardrail, open the trace, show eval and red-team scorecards. Stress the Foundry User ceiling. | `lab2_medication_double`, `lab2_injected_flyer`, `lab2_benign_control` | Each table names **one policy they would require before production** |
| 11:55 | Platform architecture (20) | "Two IQs, one agent" diagram: their medallion on the left, Foundry on the right. Map all ten patterns to labs (README table). | — | — |
| 12:15 | Lunch (60) | Announce: the afternoon is L200–L300, Builder cells start at Lab 1. | — | — |

### CIO framing for the Control Plane

Identity decides who can build; RBAC decides who can publish; guardrails decide what the agent may attempt;
evaluators decide whether behaviour is acceptable; traces make it auditable. Participants hold **Foundry User**:
they can build and run agents but cannot deploy models, create connections or publish hosted agents.

## Afternoon: L200–L300 (1:15–5:30)

| Time | Block | Lab mapping | Demo prompt(s) | Checkpoint to move on |
|---|---|---|---|---|
| 1:15 | Agent Framework & multi-agent (40) | SDK agents, versioning, orchestration patterns. [Lab 1](content/labs/lab-01.md) walkthrough (Builder: KB MCP connection in code, JSON contract), with a preview of Lab 3 code. | `lab1_prediabetes_eat`, `lab1_intake` | Builder sees valid `lab1_contract` JSON with `cited_sources` |
| 1:55 | Tools, MCP & integration (40) | MCP, approval workflows, OpenAPI, gateway; the three Fabric integration paths (Fabric IQ tool, OneLake as Foundry IQ source, ML `/score` endpoint). [Lab 3](content/labs/lab-03.md) walkthrough; activities MCP with approval. | `lab3_hazy_indoor_signup` | Approval card shown before `register_interest` |
| 2:35 | Break (15) | Helpers fix `.env` and sign-in issues for Builder. | — | — |
| 2:50 | Evaluation, Guardrails & Security (40) | Built-in + custom evaluators, continuous evaluation, runtime controls, Entra Agent ID, auditability. [Lab 2](content/labs/lab-02.md) evaluation code step-through (read, do not run); compare the facilitator's completed versions. | `lab2_extreme_fasting`, `lab2_other_resident` | Room interprets shared v1/v2 evaluator deltas and missing scores |
| 3:30 | **Part A Build** (35) | [Lab 1](content/labs/lab-01.md): attach the shared KB, add the JSON contract. | `lab1_prediabetes_eat`, `lab1_supplement`, `lab1_intake` | Paste a reply that cites ≥ 1 KB document and invents no source ([answer key](content/answer-keys/lab-01.json)) |
| 4:05 | **Part B Govern** (30) | [Lab 2](content/labs/lab-02.md): seven-prompt guardrail ladder (default, then `livewell-guardrails`), traces, evaluation code walkthrough and shared results. No participant batch. | `lab2_extreme_fasting`, `lab2_medication_double`, `lab2_injected_flyer`, `lab2_other_resident`, `lab2_skip_meals`, `lab2_benign_control`, `lab2_benign_dose_reminder` | Flyer injection blocked or ignored **and** one trade-off explained from the shared comparison, naming versions, groundedness and judged-row counts ([answer key](content/answer-keys/lab-02.json)) |
| 4:35 | **Part C Extend** (55) | See the Part C breakdown below. | | |

### Part C breakdown (4:35–5:30)

| Time | Beat | Who | Prompt(s) | Checkpoint |
|---|---|---|---|---|
| 4:35 | [Lab 3](content/labs/lab-03.md) core: profile tool, activities MCP with approval, memory, specialists | Everyone | `lab3_profile_tailored`, `lab3_hazy_indoor_signup`, `lab3_memory_set`, `lab3_memory_recall`, `lab3_specialists` | Compound question fires ≥ 2 tools/agents in the trace; reply fits Rahim's glucose; registration waits for approval ([answer key](content/answer-keys/lab-03.json)) |
| 5:05 | [Fabric step](content/labs/fabric-step.md) (only if `fabric_bridge: true` and the room is on time) | Everyone, or facilitator on screen | `lab3_programme_fit`, `fabric_q_disengaged_regions`, then `lab1_prediabetes_eat` | Profile precedes the age-band-only Fabric question; registration waits for approval. Mei uses Fabric; Rahim's food question does not. Reference figures match; no individual data leaves for Fabric |
| 5:15 | [Lab 4](content/labs/lab-04.md): sequential/hand-off and hosted agent | Facilitator-led; participants can use browser DevUI and hosted chat | `lab4_week_plan_handoff`, `lab4_activity_only`, `lab4_q_programmes_disengaged` | Sequential/hosted returns cited evidence JSON; hand-off ends with Activity's answer and a visible route. Only the facilitator deploys ([answer key](content/answer-keys/lab-04.json)) |
| 5:22 | [Bridge spotlight](content/labs/bridge-spotlight.md) + close on the ten patterns and the extended arc | Facilitator | `bridge_q_dropped_attended_heldin` (only if time) | — |

Timing rule: if the room is more than 10 minutes behind at 5:05, run the Fabric step on screen and play the
Lab 4 recording. The bridge spotlight is slides-only when the Fabric step ran live, and a full demo when it did not.

The lab-page durations describe the full reference exercises, not additional agenda slots. Keep this fixed agenda:
use the optional intake, A2A and browser orchestration sections as extensions or facilitated demonstrations when
the room cannot complete them. State which outcomes were demonstrated rather than claiming every participant ran every optional path.
Participants use one lab page per capability: the Navigator section now includes the screenshots and copy blocks.
For Lab 2, run only the hands-on `lab2_govern.py` during the lab. Read `lab2_evaluate.py` with the class
without enabling it, then use the comparison prepared before the session. Do not turn spare time or
an unavailable score into permission for the room to submit batches; multiple judges per row multiply
quota use. Shared scores are demonstration evidence, not measurements of each participant's coach.

## Demo prompts by lab

| Lab | prompt_ids (in order) |
|---|---|
| 0 | `lab0_hi`, `lab0_am_i_diabetic` |
| 1 | `lab1_prediabetes_eat`, `lab1_supplement`, `lab1_activity_guideline`, `lab1_intake` |
| 2 | `lab2_extreme_fasting`, `lab2_medication_double`, `lab2_injected_flyer`, `lab2_other_resident`, `lab2_skip_meals`, `lab2_benign_control`, `lab2_benign_dose_reminder` |
| 3 | `lab3_profile_tailored`, `lab3_hazy_indoor_signup`, `lab3_memory_set`, `lab3_memory_recall`, `lab3_specialists` |
| Fabric step | `lab3_programme_fit`, `lab3_programme_confirm`, `fabric_q_disengaged_regions`, `lab1_prediabetes_eat` |
| 4 | `lab4_week_plan_handoff`, `lab4_activity_only`, `lab4_q_programmes_disengaged` |
| Bridge | `bridge_q_dropped_attended_heldin` |

Scripted runs prepend the `consent_line` from the prompt bank so the Lab 0 consent rule does not stall them.

## Backup plans

| Failure | Backup |
|---|---|
| Sign-in / Authenticator / RBAC | Pair with a neighbour on a shared screen while an operator fixes access (`scripts/seed-attendees.sh` re-run) |
| Model quota (429 on `gpt-5-mini`) | Switch the agent to `gpt-4.1-mini` (no Reasoning effort setting) and carry on; the facilitator raises the TPM cap if the quota allows |
| Knowledge base missing or slow | Show the static guides in [content/knowledge/livewell-guides/](content/knowledge/livewell-guides/); Builder asserts on expected guide ids |
| Guardrail attach fails in the portal | Use the prebuilt `livewell-demo-guarded` agent for the red-flag contrast |
| Evaluators unavailable | Show the pre-captured evaluation run and trace from `demos/` |
| Activities MCP down | Run `content/assets/mcp-activities/server.py` locally behind a tunnel, or show the recorded approval trace |
| Fabric tool down, capacity paused, or data agent unpublished | Play the recorded Fabric-step answer; quote the region order from `python scripts/r360.py` |
| Portal glitch in general | Use reviewed screenshots in the canonical lab's Navigator section or the facilitator recordings in `demos/`; do not present an older model configuration as current |

## RBAC gotchas

- **Foundry User** (participants): create and run agents, use shared deployments, the shared KB and shared connections.
  Cannot deploy models, create connections, or publish hosted agents.
- **Foundry Project Manager** (facilitator): everything above, plus connections and hosted deploy. Lab 4 deployment is facilitator-only; browser DevUI and hosted chat are participant activities. Accounts with broader permissions still follow that boundary.
- The Fabric IQ tool uses identity passthrough: participants need **Viewer** (or read on the data agent) in the
  `HPB Resident 360` workspace, or the call fails with 403.
- Never delete agents with the `livewell-demo-` or `livewell-workshop-` prefix.

## After the day (T+1)

- Pause the Fabric capacity immediately after the session: `bash scripts/capacity.sh suspend <env>`.
- Run [`scripts/teardown.sh`](scripts/teardown.sh) once demos are archived. See the cost table in [ADMIN-SETUP](content/admin/ADMIN-SETUP.md).
