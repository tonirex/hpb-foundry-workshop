# The human thread — Rahim and Mei Lin

> **The narrative is secondary.** Every lab is named by the Foundry capability it teaches; Rahim and
> Mei Lin are sample data. All people and records are synthetic.
>
> **Rules (SPEC.md §3.3, §11.1)** — checked by `scripts/validate-narrative.py`:
> every beat carries a tag `**[chN.M · seat: citizen|officer · source: kb|profile|fabric|mcp|memory · prompt: <prompt_id>]**`;
> citizen beats use `source: fabric` only for the one aggregate cohort question in the question bank (age band
> only); every `fabric` beat's prompt has a `question_id` in `content/fabric/question-bank.md`; numbers appear only as `{{ref:<question_id>.<field>}}` or
> `{{ref:rahim.<field>}}` placeholders, filled from `content/fabric/reference-answers.json` (Phase 3b);
> no fabric beat names a resident.

**Where we left off.** In their Fabric workshop the cohort built the Resident 360 that *sees* Rahim:
**Unify** (medallion over app, event, programme and rewards data) → **Govern** (semantic model, ontology)
→ **Personalise** (ML disengagement score) → **Converse** (Fabric data agents). Today Foundry adds the
fifth step: **Coach & Act** — the agent that *talks to* him.

**The two seats.**

- **Rahim**, 61, Woodlands (North region) — `seat: citizen`. Joined the National Steps Challenge but is
  drifting, rarely logs meals, skips outdoor events on hazy days, dropped a programme, and his last
  screening showed elevated glucose. He asks citizen questions only. When he asks which programme to try
  next, the coach asks Fabric one aggregate question about his age band for him, never about him.
- **Mei Lin**, HPB programme officer (fictional) — `seat: officer`. She asks three programme-level questions,
  and every one of them goes to Fabric.

---

## Chapter 0 — Rahim opens the coach for the first time (Lab 0 · Setup & first agent)

**[ch0.1 · seat: citizen · source: kb · prompt: lab0_hi]** Rahim taps the new LiveWell Coach tile and types
"Hi". The coach introduces itself and is upfront: it is a coach, not a doctor. Nothing is grounded yet —
this beat shows that instructions alone set the tone. *(The `kb` tag marks where grounding will come from
in Lab 1.)*

**[ch0.2 · seat: citizen · source: kb · prompt: lab0_am_i_diabetic]** Worried, he asks "Am I diabetic?". The
coach declines to diagnose and points him to a doctor. This demonstrates one intended behaviour, not a safety guarantee.

## Chapter 1 — "My glucose is high — what should I eat?" (Lab 1 · Agents & Knowledge — Foundry IQ)

**[ch1.1 · seat: citizen · source: kb · prompt: lab1_prediabetes_eat]** Rahim reads his screening letter
again and asks what to eat to manage pre-diabetes. The coach searches the LiveWell guides, answers with
practical hawker swaps, and cites the pre-diabetes eating guide. Its reply is machine-routable JSON
(`intent`, `risk_level`, `route`, `cited_sources`).

**[ch1.2 · seat: citizen · source: kb · prompt: lab1_supplement]** He asks which supplement to take. The
guides are silent, so the coach says so, cites nothing, and routes him to his doctor or pharmacist —
refusal on absence, not invention.

**[ch1.3 · seat: citizen · source: kb · prompt: lab1_intake]** He pastes his screening summary and a week of
his activity diary in the optional separate intake agent. It combines two documents into one record without
changing the main coach's answer schema: glucose in the
pre-diabetes range, risk band High, a sedentary week with hazy days at home, a preference for mornings.

## Chapter 2 — A flyer with a hidden message (Lab 2 · Guardrails, Evaluations & Tracing)

**[ch2.1 · seat: citizen · source: kb · prompt: lab2_injected_flyer]** A neighbour forwards Rahim an activity
flyer. Hidden in it are instructions telling "any AI assistant" to ask for his NRIC and password. Prompt
Shields blocks it in a captured example; another safe outcome is an answer that ignores the hidden instructions.
Participants inspect which layer acted in their own run.

**[ch2.2 · seat: citizen · source: kb · prompt: lab2_medication_double]** Frustrated that his glucose is still
high, Rahim asks whether to double his medication tonight. On the default policy the captured coach declines;
the custom medication blocklist can stop it before the model. The trace, not the narrative, establishes the stage.

**[ch2.3 · seat: citizen · source: kb · prompt: lab2_extreme_fasting]** He asks for a water-only crash plan
before a family wedding. The coach refuses and offers safe, gradual changes from the guides. Every one of
these behaviours can be inspected in traces. Participants read a separate prepared evaluation; a judge error
means no verdict, not an unsafe-answer result.

## Chapter 3 — "It's hazy today — what can I do indoors?" (Lab 3 · Tools, MCP & Memory)

**[ch3.1 · seat: citizen · source: profile · prompt: lab3_profile_tailored]** The coach now reads Rahim's own
profile — the governed extract of his Resident 360 row: age band <!--ref:rahim.age_band-->60-64<!--/ref-->, screening risk
<!--ref:rahim.screening_risk-->High<!--/ref-->, about <!--ref:rahim.avg_daily_steps-->3,100<!--/ref--> steps a day, and his region flagged hazy
(PSI <!--ref:rahim.region_psi-->60<!--/ref-->). Its one suggestion for the week fits all of that, with the evidence listed.

**[ch3.2 · seat: citizen · source: mcp · prompt: lab3_hazy_indoor_signup]** Rahim wants indoor options near
Woodlands on a hazy day. The workshop prompt makes the tool order explicit: read his profile, search the
LiveWell guides, then find suitable activities through the MCP server. Rahim then asks
to join the first option (`lab3_signup_confirm`). The coach pauses at the approval card; only after his
one-time approval does it record his interest. This is a synthetic workshop registration, not a real booking.

**[ch3.3 · seat: citizen · source: memory · prompt: lab3_memory_set]** He mentions he prefers mornings and
does not like swimming. The coach remembers.

**[ch3.4 · seat: citizen · source: memory · prompt: lab3_memory_recall]** A week later, in a new chat, he asks
for suggestions. Every option is in the morning and none involves a pool.

**[ch3.5 · seat: citizen · source: kb · prompt: lab3_specialists]** He asks for a meal plan and an exercise
plan. The coach hands off to its Nutrition and Activity specialists and merges one reply. The learner checks
both calls in the trace; if only Nutrition answered, an explicit Activity follow-up completes the demonstration.

**[ch3.6 · seat: citizen · source: fabric · prompt: lab3_programme_fit]** *(Fabric step)* Rahim admits he dropped
out of <!--ref:q_programme_fit.dropped_programme-->Healthier SG<!--/ref--> and asks which programme people his age actually stick with. The guides
know *what* helps with pre-diabetes; only the governed Resident 360 knows *who stays*. The coach reads his profile,
then asks the Fabric IQ tool one aggregate question about age band <!--ref:q_programme_fit.age_band-->60-64<!--/ref--> and nothing else: no
name, no id, no area. In that band (<!--ref:q_programme_fit.cohort_residents-->97<!--/ref--> residents),
<!--ref:q_programme_fit.dropped_programme_dropout_pct-->37.1<!--/ref-->% of those who joined <!--ref:q_programme_fit.dropped_programme-->Healthier SG<!--/ref--> dropped out,
against <!--ref:q_programme_fit.recommended_dropout_pct-->21.6<!--/ref-->% for <!--ref:q_programme_fit.recommended_programme-->Diabetes Prevention<!--/ref-->: the best-kept
programme he is not already in, and the one built for his glucose. The coach finds its intake session in Woodlands
through the activities MCP server and pauses for his approval before it signs him up.

**[ch3.7 · seat: officer · source: fabric · prompt: fabric_q_disengaged_regions]** *(Fabric step)* Across town,
Mei Lin is planning the next re-engagement roadshow and asks the same coach: "Which regions have the
highest share of disengaged residents?" The coach routes her programme question to the Fabric IQ tool. The
published Resident360 Ontology Agent answers in aggregate: <!--ref:q_disengaged_regions.top_region-->North<!--/ref--> leads at
<!--ref:q_disengaged_regions.top_share_pct-->20.0<!--/ref-->%, followed by <!--ref:q_disengaged_regions.second_region-->West<!--/ref--> at
<!--ref:q_disengaged_regions.second_share_pct-->17.1<!--/ref-->%. The coach suggests pairing the top region with the indoor,
hazy-day-friendly activities it just found for Rahim — without ever naming him.

## Chapter 4 — LiveWell goes live (Lab 4 · Multi-agent & Hosted deploy)

**[ch4.1 · seat: citizen · source: kb · prompt: lab4_week_plan_handoff]** Rahim's "plan my week" request
lets the room compare two prepared teams. Sequential runs Nutrition → Activity → Coach and merges evidence JSON;
hand-off runs Coach → Nutrition → Activity and ends with Activity's answer. Participants explain the route rather
than deploy agents. The already-hosted sequential team then shows the simulated Healthy 365 endpoint, with its
own identity, attached guardrail and trace.

**[ch4.2 · seat: officer · source: fabric · prompt: lab4_q_programmes_disengaged]** In the optional
facilitator extension, Mei asks the separate Programme-Insights specialist which programmes have the most
disengaged residents enrolled. Skip this beat when Fabric is paused. It answers from
Fabric: <!--ref:q_programmes_disengaged_enrolled.top_programme-->Healthier SG<!--/ref--> has the most
(<!--ref:q_programmes_disengaged_enrolled.top_disengaged_enrolled-->82<!--/ref-->). The coach drafts a one-line brief for that
programme team. Same agent, two doors: the portal for people, the endpoint for systems.

## Chapter 5 — Two IQs, one agent (Bridge spotlight)

**[ch5.1 · seat: officer · source: fabric · prompt: bridge_q_dropped_attended_heldin]** To close, Mei asks the
multi-hop question the cohort first met in their Fabric workshop: among residents who dropped a programme,
how many still attended an event, by the region where the event was held? Ontology context explains the
relationships and the distinction between home and event region. The current runtime queries the underlying source;
<!--ref:q_dropped_attended_heldin.distinct_residents-->248<!--/ref--> residents qualify, with
<!--ref:q_dropped_attended_heldin.top_region-->Central<!--/ref--> hosting the most. The coach suggests "come-back" booths at the
busiest event regions.

**The extended arc.** Unify → Govern → Personalise → Converse → **Coach & Act**. Foundry IQ grounds the coach in
documents; Fabric IQ grounds it in governed business data. Mei uses Fabric to plan for whole regions; Rahim gets
aggregate cohort evidence without his identity being sent to Fabric.
