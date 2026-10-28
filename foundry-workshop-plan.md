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
  The optional Rahim programme-fit extension sends only his age band to Fabric for cohort statistics, never his identity.
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
| Lab 2 evidence ready | Verify prepared same-model default/custom runs or a schema-2 captured summary before participants arrive | Pass/fail/not-scored are distinguishable; absent evidence means an incomplete checkpoint, not permission to start an evaluation |
| Lab 4 shared access ready | Render the values sheet shortly before use; privately distribute its expiring launch link and expiry | A fresh browser opens LiveWell sequential without token entry; hand-off remains selectable; no participant provisioning |
| Reference agents alive | Open the `livewell-demo-*` agents (`agent_naming.demo_agents` in `content/config/workshop.yaml`), send `lab0_hi` to `livewell-demo-lab0` | Introduces itself, says it is not a doctor |
| Fabric tool alive | Send `fabric_q_disengaged_regions` to `livewell-demo-fabric` | Trace shows the Fabric IQ call; North ranks first |
| Knowledge base alive | Send `lab1_prediabetes_eat` to `livewell-demo-kb` | ≥ 1 citation to `lg-05-eating-for-pre-diabetes` |
| MCP alive | `GET /health` on `ca-mcp-activities-<env>` | 200 |
| Demo videos ready | `demos/videos/<lab>-<date>.webm` from `python demos/record-demos.py` (T-1) open in a local player | Plays offline |
| Smoke test | `python scripts/smoke-test.py --demo-agents` | 11/11 PASS (includes the guardrail drift check, the demo-memory residue check and the A2A specialists check) |
| Demo memory clean | `python scripts/reset-demo-memory.py` (`--reset` if it flags residue after a red team) | Exit 0, 0 flagged |
| Wi-Fi slide | SSID/code from `content/config/workshop.yaml` | Correct values (TODO until confirmed) |

## Morning: L100, everyone (9:00–12:15)

| Time | Block | Facilitation notes | Demo prompt(s) | Checkpoint to move on |
|---|---|---|---|---|
| 9:00 | What is Microsoft Foundry (30) | New Foundry portal tour: models, agents, tools, observability, governance. "Where we left off": the Fabric arc, then "today we add Coach & Act". | — | Room can name the four Fabric arc steps and the new fifth one |
| 9:30 | Foundry Models (20) | Catalogue, Global Standard, quota, TPM caps, reasoning effort. Why two models: `gpt-5-mini` at Low reasoning effort for Labs 0-2, `gpt-4.1-mini` from Lab 3 because not every model supports every tool (OpenAPI, A2A, Fabric). Open a trace and read the model and tokens. | `lab0_am_i_diabetic` | Room can say why the Lab 3 coach changes model |
| 9:50 | Foundry Agent Service (25) | Agent = model + instructions (+ tools). Managed runtime, versions, multi-agent, memory, frameworks. Build LiveWell Coach live; show a structured output. | `lab0_hi`, `lab0_am_i_diabetic` | Agent states it is not a doctor and refuses to diagnose |
| 10:15 | **Micro-Lab 0** (15, all rails, portal) | Everyone creates `livewell-<initials>`, pastes the `base` instructions block from [coach-instructions.md](content/prompts/coach-instructions.md), sets Reasoning effort to Low, removes Web search if the template added it, sends two prompts and reads the trace. [Lab 0](content/labs/lab-00.md). | `lab0_hi`, `lab0_am_i_diabetic` | ≥ 80% of the room shows the refusal to diagnose. Stragglers pair with a neighbour |
| 10:30 | Break (15) | Helpers triage sign-in (Temporary Access Pass) and RBAC. | — | — |
| 10:45 | Tools & Knowledge (30) | Foundry IQ knowledge base on Azure AI Search (agentic retrieval, citations, refusal on absence), connectors, MCP, the Fabric IQ tool. **Two IQs on Rahim:** guide question with citation, then Mei's region question via their own Fabric data agent. | `lab1_prediabetes_eat`, `lab1_supplement`, `fabric_q_disengaged_regions` | Room can say which IQ answered which question |
| 11:15 | Control Plane: "CIO lab" (40) | Guardrails (input/output/tool), tracing, monitoring, evaluation, red teaming, identity (Entra Agent ID), cost tracking. Trip a guardrail, open the trace, show the pre-run eval and red-team scorecards (facilitator-run; participants only watch). Stress the Foundry User ceiling. | `lab2_medication_double`, `lab2_injected_flyer`, `lab2_benign_control` | Each table names **one policy they would require before production** |
| 11:55 | Platform architecture (20) | "Two IQs, one agent" diagram: their medallion on the left, Foundry on the right. Map all ten patterns to labs (README table). | — | — |
| 12:15 | Lunch (60) | Announce: the afternoon is L200–L300, Builder cells start at Lab 1. | — | — |

### CIO framing for the Control Plane

Identity decides who can build; RBAC decides who can publish; guardrails decide what the agent may attempt;
evaluators decide whether behaviour is acceptable; traces make it auditable. Participants hold **Foundry User**:
they can build and run agents but cannot deploy models, create connections or publish hosted agents.

## Afternoon: L200–L300 (1:15–5:30)

| Time | Block | Lab mapping | Demo prompt(s) | Checkpoint to move on |
|---|---|---|---|---|
| 1:15 | Agent Framework & multi-agent (40) | [Lab 4](content/labs/lab-04.md): 25 min guided shared-browser comparison, then 15 min optional Builder code map and discussion. Start with when one agent is enough; predict, run, observe and explain both routes. No participant provisioning. | `lab4_week_plan_handoff`, `lab4_activity_only` | Explain code-fixed versus model-selected routing; identify a real hand-off call and each team's final answerer |
| 1:55 | Tools, MCP & integration (40) | MCP, approval workflows, OpenAPI, gateway; the three Fabric integration paths (Fabric IQ tool, OneLake as Foundry IQ source, ML `/score` endpoint). [Lab 3](content/labs/lab-03.md) walkthrough; activities MCP with approval. | `lab3_hazy_indoor_signup` | Approval card shown before `register_interest` |
| 2:35 | Break (15) | Helpers fix `.env` and sign-in issues for Builder. | — | — |
| 2:50 | Evaluation, Guardrails & Security (40) | Built-in + custom evaluators, continuous evaluation, runtime controls, Entra Agent ID, auditability. [Lab 2](content/labs/lab-02.md) walkthrough; compare two agent versions through the facilitator's **pre-run** evaluation (look-only: participants run no evaluation or red-team scan). | `lab2_extreme_fasting`, `lab2_other_resident` | Room sees v1 vs v2 evaluator deltas |
| 3:30 | **Part A Build** (35) | [Lab 1](content/labs/lab-01.md): attach the shared KB, add the JSON contract. | `lab1_prediabetes_eat`, `lab1_supplement`, `lab1_intake` | Paste a reply that cites ≥ 1 KB document and invents no source ([answer key](content/answer-keys/lab-01.json)) |
| 4:05 | **Part B Govern** (30) | [Lab 2](content/labs/lab-02.md): seven-prompt default/custom comparison in staggered waves, inspect the layer, then read the prepared evaluation (look-only). | `lab2_extreme_fasting`, `lab2_medication_double`, `lab2_injected_flyer`, `lab2_other_resident`, `lab2_skip_meals`, `lab2_benign_control`, `lab2_benign_dose_reminder` | Flyer blocked or ignored; explain same-model demo-run `handled_safely` results, coverage and errors—not a claim about participant versions |
| 4:35 | **Part C Extend** (55) | See the Part C breakdown below. | | |

### Part C breakdown (4:35–5:30)

| Time | Beat | Who | Prompt(s) | Checkpoint |
|---|---|---|---|---|
| 4:35 | [Lab 3](content/labs/lab-03.md) core: profile read, activity approval, memory evidence; specialists optional | Everyone | `lab3_profile_tailored`, `lab3_hazy_indoor_signup`, `lab3_memory_set`, `lab3_memory_recall` | Identify lookup and proposed write; explicitly approve or deny; memory claims have stored/search evidence |
| 5:05 | [Fabric step](content/labs/fabric-step.md) (only if `fabric_bridge: true` and the room is on time) | Everyone, or facilitator on screen | `fabric_q_disengaged_regions`, then `lab1_prediabetes_eat` | Trace shows the Fabric IQ call for Mei's question and the KB for Rahim's; region order matches `scripts/r360.py`; no `resident_id` |
| 5:15 | [Lab 4 hosted proof](content/labs/lab-04-portal.md): 5 min to inspect the already-deployed sequential team, then 2 min transition; do not redeploy during the lab | Facilitator, participants may inspect | `lab1_prediabetes_eat`; facilitator endpoint/guardrail evidence | Recognise the same sequential team plus the profile step; endpoint returns cited JSON and the blocklisted prompt is blocked ([answer key](content/answer-keys/lab-04.json)) |
| 5:22 | [Bridge spotlight](content/labs/bridge-spotlight.md) + close on the ten patterns and the extended arc | Facilitator | `bridge_q_dropped_attended_heldin` (only if time) | — |

Timing rule: if behind at 5:05, show captured Fabric evidence and Lab 4 hosted proof. The orchestration comparison
already ran at 1:15. The bridge is an eight-minute no-build recap even when Fabric was skipped; no mandatory live
query or capacity resume. Label legacy GQL replay as historical, not current source-native execution.

Core reading follows why → prepared resources → action → inspect → explain. Expand screenshot/setup blocks
when needed; leave optional intake, A2A, programme fit and runtime internals for spare time. Builder write approval
uses an interactive terminal; non-interactive denial is expected, never hidden approval.

### Lab 4 facilitation

- Demonstrate the first run, then let small groups try the prepared prompts. Do not start 30 runs together.
- Use groups of at most eight per workflow. Share the private link only with the workshop; do not put it in the
  repository or public slides. Regenerate it when expired; opening the plain app address is not first-time access.
- Keep the visible guide on the core path; screenshots, FAQ and implementation details expand only when needed.
- A graph is not execution evidence. Ask who answered, who handed off, and which call proves it. In DevUI,
  two hand-off calls plus their results make four Tools entries; hosted MCP operations need server-side tracing.
- Do not sell hand-off as inherently faster: this example also omits the final Coach merge. Compare routing and outputs.
- Programme-Insights is a separate, optional facilitator extension, not a fourth DevUI participant. Skip it when
  Fabric is paused or time is short. Core Lab 4 and the hosted sequential proof need no Fabric capacity.

## Demo prompts by lab

| Lab | prompt_ids (in order) |
|---|---|
| 0 | `lab0_hi`, `lab0_am_i_diabetic` |
| 1 | `lab1_prediabetes_eat`, `lab1_supplement`, `lab1_activity_guideline`, `lab1_intake` |
| 2 | `lab2_extreme_fasting`, `lab2_medication_double`, `lab2_injected_flyer`, `lab2_other_resident`, `lab2_skip_meals`, `lab2_benign_control`, `lab2_benign_dose_reminder` |
| 3 | `lab3_profile_tailored`, `lab3_hazy_indoor_signup`, `lab3_memory_set`, `lab3_memory_recall`, `lab3_specialists` |
| Fabric step | `fabric_q_disengaged_regions` |
| 4 | `lab4_week_plan_handoff`, `lab4_activity_only`; hosted proof: `lab1_prediabetes_eat`; optional facilitator Fabric: `lab4_q_programmes_disengaged` |
| Bridge | `bridge_q_dropped_attended_heldin` |

Scripted runs prepend the `consent_line` from the prompt bank so the Lab 0 consent rule does not stall them.

## Backup plans

| Failure | Backup |
|---|---|
| Sign-in / TAP / RBAC | Pair with a neighbour on a shared screen while an operator fixes access (re-issue the pass with `scripts/tenant/issue-tap.sh <env> issue --apply --replace`; `scripts/seed-attendees.sh` re-run for RBAC) |
| Model quota (429 on `gpt-5-mini`) | Stagger the next step in waves of ten first. If it persists, switch the agent to `gpt-4.1-mini` (no Reasoning effort setting; separate quota) and carry on. The facilitator does **not** raise a cap or request quota on the day: that needs the T-3 inventory and separate approval |
| Knowledge base missing or slow | Show the static guides in [content/knowledge/livewell-guides/](content/knowledge/livewell-guides/); Builder asserts on expected guide ids |
| Guardrail attach fails in the portal | Use the prebuilt `livewell-demo-guarded` agent for the red-flag contrast |
| Evaluators unavailable | Show the pre-captured evaluation run (`content/data/lab2-prepared-eval.json` if the facilitator saved it, else the screenshots) and trace from `demos/` |
| Activities MCP down | Run `content/assets/mcp-activities/server.py` locally behind a tunnel, or show the recorded approval trace |
| Fabric tool down, capacity paused, or data agent unpublished | Play the recorded Fabric-step answer; quote the region order from `python scripts/r360.py` |
| Portal glitch in general | Pre-recorded demo videos and screenshots in `demos/` and the [Portal Track](content/labs/PORTAL-TRACK.md) |

## RBAC gotchas

- **Foundry User** (participants): create and run agents, use shared deployments, the shared KB and shared connections.
  Cannot deploy models, create connections, or publish hosted agents.
- **Foundry Project Manager** (facilitator): everything above, plus connections and hosted deploy. Only Lab 4's
  deployment preparation and optional Fabric specialist creation need this role; the shared-browser comparison does not.
- The Fabric IQ tool uses identity passthrough: participants need **Viewer** (or read on the data agent) in the
  `HPB Resident 360` workspace, or the call fails with 403.
- Never delete agents with the `livewell-demo-` or `livewell-workshop-` prefix.

## After the day (T+1)

- Pause the Fabric capacity immediately after the session: `bash scripts/capacity.sh suspend <env>`.
- Run [`scripts/teardown.sh`](scripts/teardown.sh) once demos are archived. See the cost table in [ADMIN-SETUP](content/admin/ADMIN-SETUP.md).
