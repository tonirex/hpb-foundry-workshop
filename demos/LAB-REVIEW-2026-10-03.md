# Lab review: flow, consistency and objectives (2026-10-03)

This review checks that the labs still hang together after the move to the Sponsorship-subscription models
(`gpt-5-mini` Low by default, `gpt-4.1-mini` for the Lab 3 tools coach and the judges, `text-embedding-3-small`),
and that every lab meets its stated objective on both rails: 🟢 Navigator (portal) and 🔵 Builder (Python).

> **Status, end of 2026-10-03:** the text fixes and the DevUI fix are applied (section 9). L4-3 is verified for the
> data plane, and Lab 4 now has a browser-hosted DevUI for Navigators. Still open: the screenshot retake pass (X-1,
> L2-4), the lab-account portal check (L4-5) and the timing decision (X-2).

## 1. Scope and method

| Source | What it gave us |
|---|---|
| Lab pages | [Lab 0](../content/labs/lab-00.md) to [Lab 4](../content/labs/lab-04.md), the `lab-0N-portal.md` walkthroughs, the [Fabric step](../content/labs/fabric-step.md), the then-existing Bridge spotlight (retired 2026-10-29) and [PORTAL-TRACK](../content/labs/PORTAL-TRACK.md) |
| Sources of truth | [workshop.yaml](../content/config/workshop.yaml), [coach-instructions.md](../content/prompts/coach-instructions.md), [test-prompts.json](../content/prompts/test-prompts.json), `content/answer-keys/`, [ASSUMPTIONS.md](../ASSUMPTIONS.md) |
| Run of show | [foundry-workshop-plan.md](../foundry-workshop-plan.md) |
| Builder evidence | Casts re-recorded on 2026-10-03 in `demos/evidence/2026-10-03/`; all exit 0 |
| Smoke test | `content/assets/.runs/smoke-test-20261003.md`: **11/11 PASS** with Fabric on |
| Dry run | [DRY-RUN-2026-10-02.md](DRY-RUN-2026-10-02.md): F01–F09 fixed; the timed table and Q1–Q8 are still open |

Five reviewers each read one lab area. The cross-lab checks were done separately. Every High finding and every
claim about screenshots or flow was then re-checked against the files. No portal clicks, Azure calls or model calls
were made for this review. Section 6 lists what still needs a live check.

## 2. Verdict

- **🔵 Builder: ready.** Every Builder objective is met and evidenced on the new models. The casts show the coach
  going from v1 to v4 across Labs 1–3 and the Fabric step, the insights agent, and the hosted agent at v6 with
  `livewell-guardrails`.
- **🟢 Navigator: text ready, visuals not.** The click paths, prompts, state chain and model names are current. But
  most portal screenshots predate the model switch and still show `model-router`, `gpt-5.4-mini` or `gpt-5.6-*`.
  Lab 3 also has one flow gap that can weaken its checkpoint.
- **Facilitator demos: one risk.** The Lab 4 DevUI script never received the hand-off fix that the Builder script
  got, so the live hand-off demo may fail on `gpt-5-mini`.
- **Timing is unproven.** The run of show gives the Lab 2 and Lab 3 builds 30 minutes each and Lab 1 35; the lab
  pages advertise 40. The dry run only timed Lab 0.

**21 findings:** 2 High, 11 Medium, 8 Low. None of them blocks the Builder rail.

## 3. Objectives by lab

| Lab | Shared objective | 🟢 Navigator | 🔵 Builder | Main gaps |
|---|---|---|---|---|
| 0 | An agent is a model plus instructions; instructions make it safe; traces can be inspected | ✅ Met | ➖ N/A (Navigator-only; Builders do the same portal exercise) | Answer screenshots show `model-router` (X-1) |
| 1 | Curated knowledge, citations, no invented sources, machine-routable JSON | ✅ Met | ✅ Met | Stale screenshots (X-1); Pattern #1 is advertised but optional (L1-3) |
| 2 | Apply guardrails, prove them with evaluators, make decisions auditable in traces | ✅ Met | ✅ Met (trace inspection only with `--verbose`) | Prompt count (L2-1), New chat (L2-2), fallback path (L2-3) |
| 3 | Personalise on governed data, act with human approval, delegate, route tools correctly | 🟡 Partially | ✅ Met | Signup prompt is sent in the same chat (L3-2); screenshots show `gpt-5.4-mini` with Reasoning (X-1) |
| Fabric step | Population evidence from Fabric, aggregate-only, profile first | 🟡 Partially | ✅ Met | Stale screenshots (X-1); no `gpt-4.1-mini` prerequisite (FS-2); version number (X-3) |
| 4 (demo) | Same agent via portal and endpoint, same policy; sequential and hand-off orchestration | 🟡 Partially | ✅ Met | DevUI hand-off (L4-1); Foundry User access to the hosted endpoint is unverified (L4-3) |
| Bridge | Choose Foundry IQ or Fabric IQ, and connect them | 🟡 Partially | ✅ Met | Stale screenshots (X-1); fallback wording (BS-2) |

## 4. Cross-lab flow and consistency

| Check | Result |
|---|---|
| "Where next" chain | ✅ 0 → 1 → 2 → 3 → Fabric step (when `FABRIC_BRIDGE` is on) → 4 → Bridge → README |
| Story chapters | ✅ Chapters 0–5 are linked in order and match each lab's scenario |
| Navigator agent state | ✅ Lab 0 sets `gpt-5-mini` Low with the `base` block. Lab 1 adds the knowledge base, the `knowledge` block and the JSON schema. Lab 2 adds the guardrail and the `safety` block. Lab 3 switches to `gpt-4.1-mini` first, then adds tools, memory and A2A. The Fabric step adds the Fabric tool and the `fabric` block |
| Builder agent state | ✅ One name, `livewell-<INITIALS>-coach`, at v1 → v2 → v3 → v4. ⚠️ The Fabric step text says "version 2" (X-3) |
| Model names in participant content | ✅ No `model-router`, `gpt-5.4-mini` or `text-embedding-3-large` in the text. ❌ Many screenshots still show them (X-1) |
| Names and policies | ✅ `livewell-guardrails`, `livewell-medication-dosage`, `livewell-activities-mcp` and `livewell_profile` are consistent across pages, config and code |
| Lab 2 guardrail ladder | ✅ Expected results match ASSUMPTIONS 9.2: the default guardrail blocks 1 of 7 prompts, the custom one blocks 4 of 7. ⚠️ The pages say "eight prompts" (L2-1) |
| Answer keys | ✅ They match the checkpoints, except for the Fabric programme-fit prompt (FS-3) and the Lab 1 supplement intent (L1-4) |
| Timing | ⚠️ The pages and the run of show disagree; see the table below |

| Item | Pages and workshop.yaml | Run of show | Gap |
|---|---|---|---|
| Lab 1 (Part A) | 40 min | 35 min | −5 |
| Lab 2 (Part B) | 40 min | 30 min | −10 |
| Lab 3 core | 40 min | 30 min | −10 |
| Fabric step | 15 min | 10 min | −5 |
| Lab 4 demo | 30 min | 7 min | −23 |
| Bridge spotlight | 10 min | 8 min | −2 |

ASSUMPTIONS 1.32 records this gap, but participants only see the longer times. The Lab 3 Navigator build has the
most risk: in 30 minutes it covers a model switch, the OpenAPI tool, the MCP tool with approval, memory and A2A.

## 5. Findings

Severity: **High** = could fail live or mislead most participants. **Medium** = confusing or weakens a checkpoint.
**Low** = polish.

### High

| ID | Rail | Where | Issue | Fix |
|---|---|---|---|---|
| X-1 | 🟢 | Screenshots for all portal pages | Of the portal screenshots, 73 were taken before the model switch (Lab 0: 6, Lab 1: 11, Lab 2: 19, Lab 3: 22, Lab 4: 9, Bridge: 6, dated 2026-09-30 or 2026-10-01). The 2026-10-03 retakes only covered the shots marked "Retake pending". Any playground shot shows the **Model** field and the reply footer. Confirmed stale: Lab 0 `08`/`09` (`model-router`, `gpt-5.6-luna`), the Lab 1 portal set (`model-router`, trace `chat model-router`, schema label `livewell_lab1_answer` against `livewell_answer` in the text), the KB settings shot `04` (shows `gpt-4.1-mini`; the planner is `gpt-5-mini`), Lab 3 `06`/`08`/`09`/`10`/`12` (`gpt-5.4-mini` with **Reasoning Effort low**), Fabric step `19`/`20`/`22`/`24`, and Bridge `01`–`05` | Do one retake pass on the current models: playground, footer and trace shots first, then a check of the rest |
| L4-1 | 🟢 facilitator demo | [demos/lab4-devui.py](lab4-devui.py) L40–43 | The DevUI `text_only` middleware still drops every message without text, including role-`tool` messages. The Builder script ([lab4_multiagent.py](../content/assets/lab4_multiagent.py) L80–83) keeps them; ASSUMPTIONS 9.2 records that keeping them was needed to avoid "Messages are required for chat completions" in the hand-off. The DevUI hand-off is Lab 4 step 1 | Copy the fixed middleware into DevUI, run the hand-off on `gpt-5-mini`, and retake `10-devui-sequential.png` and `11-devui-handoff.png` |

### Medium

| ID | Rail | Where | Issue | Fix |
|---|---|---|---|---|
| X-2 | Both | [foundry-workshop-plan.md](../foundry-workshop-plan.md) L58–82 compared with the lab pages | The timing gap above. The dry run only timed Lab 0 (about 20 min against 15 planned) | Either show the run-of-show minutes on the pages, or trim Lab 3 for the Navigator rail (for example, make A2A optional). Time a full Navigator run of Labs 1–3 |
| X-3 | 🔵 | [fabric-step.md](../content/labs/fabric-step.md) L157, L197 | Says "the coach, version 2"; today's cast creates **version 4** (v1 Lab 1, v2 Lab 2, v3 Lab 3) | Write "the next version (version 4 if you ran Labs 1–3 once)" |
| L2-1 | Both | [lab-02.md](../content/labs/lab-02.md) L15, L29; [lab-02-portal.md](../content/labs/lab-02-portal.md) L5 | Says "eight prompts"; the ladder, the script and the answer key use **seven** | Change to "seven" |
| L2-2 | 🟢 | lab-02.md L32; lab-02-portal.md steps 3–8 | The main page says to start a new chat for each prompt; the walkthrough only says it for the first default prompt | Add **New chat** to steps 3–8, or a note after step 2 |
| L2-3 | 🟢 | lab-02.md L103, L113; lab-02-portal.md L158–160, L233–239 | If a Foundry User cannot attach `livewell-guardrails`, the fallback is `livewell-demo-guarded`. The later evaluation and version comparison still assume the participant's own versions | Add a fallback branch: run the guarded prompts on the comparator and use the facilitator's evaluation comparison |
| L3-2 | 🟢 | [lab-03-portal.md](../content/labs/lab-03-portal.md) step 12 (L101–107) | `lab3_hazy_indoor_signup` is sent in the same chat as `lab3_profile_tailored`. The `tools` block only calls the profile "if not already called in this conversation", but the checkpoint and answer key expect `get_citizen_profile` and `find_activities`. The Builder script starts a new conversation | Add **Chat → New chat** to step 12 |
| FS-2 | 🟢 | fabric-step.md L63–78 | No prerequisite saying the coach must already be on `gpt-4.1-mini` (Lab 3 step 1). Fabric, OpenAPI and A2A depend on it | Add a "Before you start" check |
| FS-3 | Both | [lab-03.json](../content/answer-keys/lab-03.json) L30–33 | The answer key only covers `fabric_q_disengaged_regions`. The page's main Fabric prompt, `lab3_programme_fit` (profile first, an age-band-only Fabric question, Diabetes Prevention, approval), has no answer-key entry | Add an answer-key entry for `lab3_programme_fit` |
| L1-3 | Both | lab-01.md L3, L11 (header) against L65, L158; lab1_knowledge.py L98, L126 | Pattern #1 (multi-document intake) is listed as a Lab 1 pattern, but both rails mark it optional and the Builder cast skips it | Mark Pattern #1 "optional" in the header and objective |
| L4-3 | Both | lab4_multiagent.py L228–233; ASSUMPTIONS 4.20 | The text says a Foundry User can call the hosted endpoint; ASSUMPTIONS still lists this as unverified | Live check with a lab account. If it fails, describe it as facilitator-only |
| L4-4 | Both | lab-04.md L20–22; lab-04-portal.md L45–49 | The features list promises hosted-agent tracing "in Foundry **and Application Insights**", but no step opens App Insights | Add a 1-minute App Insights step, or drop "and Application Insights" |

### Low

| ID | Rail | Where | Issue | Fix |
|---|---|---|---|---|
| X-5 | Facilitator | foundry-workshop-plan.md, Part B | Lists 5 prompts and "four red-flag prompts"; the Lab 2 page uses 7 (adds `lab2_skip_meals` and `lab2_benign_dose_reminder`) | List all 7 prompts |
| L1-4 | Both | lab-01.md L202; [lab-01.json](../content/answer-keys/lab-01.json) L14; test-prompts.json L66 | The supplement prompt expects `intent: out_of_scope`; the Builder cast returns `nutrition`. The answer key allows a citation, but the prompt bank says 0 | Pick one contract and assert it in the script |
| L2-4 | 🟢 | lab-02-portal.md L241 | Screenshot slot `20-compare-v1-v2.png` has no file | Capture it in the retake pass |
| L2-5 | Both | [rahim.md](../content/narrative/rahim.md) L56–62 | The story says the coach summarises the injected flyer; in the lab, Prompt Shields blocks it before any reply | Say "blocked before the coach replies" |
| L3-3 | 🟢 | lab-03-portal.md L9, L20, L43 | Screenshots show the facilitator's `livewell-demo-tools`; the text says `livewell-<initials>` | Add a one-line note |
| L4-2 | 🟢 | lab-04-portal.md step 5 | The hosted-agent smoke test uses `lab1_prediabetes_eat`; the main page's hand-off prompt `lab4_week_plan_handoff` is not in the walkthrough | Mark step 5 as the hosted smoke test, or switch it to the week-plan prompt |
| L4-5 | 🟢 | lab-04-portal.md L55, L61 | Screenshot slots `07` and `08` have no files (they need a Foundry User account) | Capture them with a lab account, or label them "live only" |
| BS-2 | Facilitator | bridge-spotlight.md L28, L93, L114–115, L238 | The page says both "full demo when the Fabric step is skipped" and "slides only if Fabric is unavailable" | With `FABRIC_BRIDGE=false`, use `--replay`; use slides only if the replay also fails |

## 6. Needs a live check

These cannot be settled by reading files. Most need a real `hpb.lab*` account, and none exists in the mcaps tenant.

1. ~~**DevUI hand-off on `gpt-5-mini`** after the L4-1 fix~~ **Done 2026-10-03** on MCAPS: both DevUI
   workflows ran first time with retries off (hand-off Coach → Nutrition → Activity in 53 s; sequential in 60 s;
   guides cited), and `--capture` retook `10-devui-sequential.png` and `11-devui-handoff.png`.
2. **Reasoning effort after switching to `gpt-4.1-mini`.** lab-03.md L36 says the control disappears; the old
   screenshots show it still there.
3. **Planner model on `livewell-guides-kb`**: expected `gpt-5-mini` (workshop.yaml L77). The screenshot shows
   `gpt-4.1-mini`.
4. **Foundry User limits**, using a real lab account:
   - attaching `livewell-guardrails` (Lab 2);
   - adding the OpenAPI, A2A and Fabric tools (Lab 3 and the Fabric step);
   - calling the hosted endpoint (Lab 4);
   - Publish being disabled (Lab 4, screenshots 07 and 08).
5. **A timed Navigator run** of Labs 1–3 and the Fabric step, against the run-of-show slots.
6. **Dry-run open questions Q1–Q8**: F2 load, batch-evaluation time, red-team cost, memory latency, 429s, sign-in time.

## 7. What works well

- **Builder evidence is strong.** Every script asserts its own checkpoint (ordering, privacy, approval, memory
  recall, Fabric routing, the hosted guardrail and the JSON schema), and today's casts all exit 0 on the new models.
- **Navigator text is current.** It covers the no-model-picker Create dialog, picking `gpt-5-mini` Low in the
  playground, switching to `gpt-4.1-mini` at the start of Lab 3, numbered versions, and the explicit OpenAPI paste
  from the values sheet.
- **The guardrail ladder is good teaching material.** Default 1 of 7 against custom 4 of 7 shows block against
  annotate, and one deliberate false positive.
- **Cross-rail parity is clear.** Differences are intentional and explained (Navigator uses OpenAPI and A2A;
  Builder uses function tools), and both rails reach the same checkpoint answers.
- **Fabric reference numbers agree** across the story, the question bank, the pages and `reference-answers.json`.
- **Smoke test 11/11 PASS**, with Fabric on.

## 8. Suggested order of fixes

1. ✅ **Text-only fixes (about 30 min, can do now):** X-3, L2-1, X-5, L2-2, L3-2, FS-2, FS-3, L1-3, L1-4, L2-5, L3-3,
   L4-2, L4-4, BS-2.
2. ✅ **DevUI fix and live run:** L4-1, then live check 1.
3. **Screenshot retake pass on the current models:** X-1, L2-4. Do it on the Sponsorship project if it is ready, so
   it is done once.
4. **Lab-account session** for live checks 4 and 6, including Lab 4 screenshots 07 and 08 (L4-5).
5. **Timing decision**, after a timed Navigator run (X-2).

## 9. Fixes applied (2026-10-03)

| ID | Status | What changed |
|---|---|---|
| X-1 | 🟡 Partly | Only the DevUI shots (Lab 4 `10`, `11`) were retaken; the portal retake pass is still open |
| L4-1 | ✅ Fixed | [lab4-devui.py](lab4-devui.py) `text_only` now keeps role-`tool` messages, as in the Builder script. Live run and screenshots: section 6, item 1 |
| X-2 | ⏳ Open | Needs a timed Navigator run |
| X-3 | ✅ Fixed | fabric-step.md says "the next version (version 4 after one run each of Labs 1–3)" |
| L2-1 | ✅ Fixed | "seven prompts" on lab-02.md and lab-02-portal.md |
| L2-2 | ✅ Fixed | lab-02-portal.md steps 3–8 start with **Chat → New chat** |
| L2-3 | ✅ Fixed | Fallback-path note in lab-02-portal.md (after step 10) and lab-02.md step 9 |
| L3-2 | ✅ Fixed | lab-03-portal.md step 12 and lab-03.md step 8 start a new chat |
| FS-2 | ✅ Fixed | fabric-step.md Navigator step 1 checks that the model is `gpt-4.1-mini`, and says why |
| FS-3 | ✅ Fixed | `lab3_programme_fit` added to [lab-03.json](../content/answer-keys/lab-03.json) |
| L1-3 | ✅ Fixed | lab-01.md header and objective mark Pattern #1 as the optional intake step |
| L4-3 | ✅ Data plane verified | A managed identity with only Foundry User called the hosted agent and received its evidence JSON (ASSUMPTIONS 4.20). Lab 4 Navigators now chat with it themselves; a playground check with a lab account is folded into L4-5 |
| L4-4 | ✅ Fixed | lab-04.md: "tracing in Foundry (stored in the project's Application Insights)" |
| X-5 | ✅ Fixed | foundry-workshop-plan.md lists all seven Lab 2 prompts |
| L1-4 | ✅ Fixed | lab-01.md and lab-01.json accept `intent` `out_of_scope` or `nutrition`; `cited_sources` must be empty, matching the prompt bank |
| L2-4 | ⏳ Open | Retake pass |
| L2-5 | ✅ Fixed | rahim.md: the flyer is blocked before the coach replies; the medication chapter separates the unguarded and guarded outcomes |
| L3-3 | ✅ Fixed | lab-03-portal.md says the screenshots use `livewell-demo-tools` |
| L4-2 | ✅ Fixed | lab-04-portal.md step 5 is labelled the hosted-agent smoke test; the week-plan prompt runs in DevUI |
| L4-5 | ⏳ Open | Needs a lab account |
| BS-2 | ✅ Fixed | bridge-spotlight.md: when the Fabric step was skipped, run the demo live or with `--replay`; slides-only only if the replay fails |
