# Fabric step · Add the Resident 360 data agent as a Fabric IQ tool

**10 min guided · 5:05–5:15** · **Optional, preview** · **Rails:** 🟢 Navigator + 🔵 Builder · **Patterns:** #2 Evidence-Based Decision Support · #3 Workflow Orchestration · #6 Human-in-the-Loop Review · #8 Institutional Memory · #9 Collaboration Between Specialists

**You are here:** [Lab 3](lab-03.md) → **Fabric step** → [Lab 4 hosted proof](lab-04-portal.md) → [Bridge spotlight](bridge-spotlight.md) · [README](../../README.md)

## Shared objective

> Use governed cohort evidence when guidance alone cannot answer a question, and inspect exactly what information the coach sends to Fabric

## Foundry features covered

Fabric IQ tool (**preview**) · existing project connection · user identity passthrough · aggregate-only questions · comparison with Foundry IQ retrieval.

## Story chapter

Mei needs region statistics, not generic advice. Rahim's optional programme-fit question asks what people in his age band tend to stick with. [Chapter 3](../narrative/rahim.md#chapter-3--its-hazy-today--what-can-i-do-indoors-lab-3--tools-mcp--memory) links those facts to actions without sending his identity to Fabric.

## 🟢 Navigator

**Start only when the facilitator confirms active Fabric capacity, published data-agent context and your access. Otherwise skip this page.** Paused capacity does not prevent core Lab 3 or Lab 4.

**Already prepared:** `HPB Resident 360`, its data and ontology context, the published `Resident360 Ontology Agent`, and project connection `livewell-fabric-resident360`. You attach the connection; you do not provision Fabric items or resume capacity.

### 1. Choose the evidence source

| Question | Workshop source | Why |
|---|---|---|
| “What should I eat?” | Foundry IQ guides | Approved guidance with cited passages |
| “Which regions have more disengaged residents?” | Fabric data agent | A calculation over governed Resident 360 records |
| “What is my profile?” | Profile API | The fixed synthetic session record, not a population query |

These are this workshop's choices, not a claim that either product supports only one data type.

### 2. Attach the existing tool

Open your Lab 3 agent on **`gpt-4.1-mini`**. **Tools → Add → Add tools → Configured → `livewell-fabric-resident360` → Add tool**. Append the [`fabric` instructions](../prompts/coach-instructions.md#fabric-lab-3-fabric-step--only-when-fabric_bridgetrue) and **Save**.

Use the same workshop account in Foundry and Fabric. Missing connection or access is a facilitator issue; do not create a replacement.

### 3. Predict → run → inspect

**Predict:** would a guide PDF be enough to calculate this?

As Mei, start a new chat with `fabric_q_disengaged_regions`:

```text
Which regions have the highest share of disengaged residents?
```

Open **Response metrics → Traces → Fabric IQ call → Input**. Inspect **`userQuestion`**, the text sent to Fabric: it should ask for region aggregates, not a resident's record. Inspect the returned groups and any errors. Allow time for the preview service; do not repeatedly resend.

### 4. Compare with a guide question

In another new chat, send `lab1_prediabetes_eat`:

```text
My screening says my glucose is high. What should I eat to manage pre-diabetes?
```

Expect knowledge retrieval and no Fabric call **in a complete trace**. Missing telemetry is not proof of routing.

**Explain:** why did the source change? Which argument shows that personal information was not sent to Fabric?

<details>
<summary><strong>Optional extension: programme fit, then an approved action</strong></summary>

Do this only with additional time and the facilitator's go-ahead. Core comparison above is enough for the guided slot.

In a new chat as Rahim, send `lab3_programme_fit`:

```text
I dropped out of Healthier SG last year. Which programme do people my age actually stick with? Find me a way to start near Woodlands and sign me up.
```

Inspect the sequence: **profile → Fabric cohort question → activities → proposed registration**. The Fabric `userQuestion` must contain **age band only**: no name, resident id, area, gender or screening risk. Counts below five should be suppressed as “fewer than 5”; this is a workshop output rule, not proof of complete privacy protection.

If the coach asks which activity to choose, reply in the same chat. Then inspect the tool card and choose **Approve → Approve once** or **Deny**. A chat “yes” is not the approval itself. Registrations remain synthetic, temporary workshop records.

The computed reference recommends **<!--ref:q_programme_fit.recommended_programme-->Diabetes Prevention<!--/ref-->** among the applicable programmes Rahim is not already in: drop-out **<!--ref:q_programme_fit.recommended_dropout_pct-->21.6<!--/ref-->%**, versus **<!--ref:q_programme_fit.dropped_programme_dropout_pct-->37.1<!--/ref-->%** for **<!--ref:q_programme_fit.dropped_programme-->Healthier SG<!--/ref-->**. This is a descriptive comparison of synthetic data, not proof that a programme will work for a person.

![Historical example: inspect only the age-band question sent to Fabric](screenshots/lab-03/20-programme-fit-fabric-question.png)

</details>

<details>
<summary><strong>FAQ: ontology context, identity and current execution</strong></summary>

**What does the ontology do now?** It provides business terms, relationships and source mappings. The data agent uses that context to generate **source-native SQL, KQL or DAX**, executed by the underlying source. The ontology itself is not the query endpoint.

**Where can I see the internal query?** Foundry records the external tool request and response where available. The facilitator can inspect Fabric's own run steps to see the selected source, generated query and errors. Do not assume a particular internal tool name or query language.

**Does sharing the data agent grant data access?** No. Users also need the relevant ontology and underlying source permissions. The request uses the caller's identity.

**Is this a citizen sign-in design?** No. Participants are tenant users acting out a synthetic scenario. A public citizen app would need its own authentication and a properly authorised data-access design.

**What was configured?** The facilitator attached `resident_ontology` through **Sources → Add sources → Add an ontology**, then published and verified it. If context is stale, the facilitator checks the downloaded context and source bindings—not automatically a graph refresh.

Further reading: [ontology as context](https://learn.microsoft.com/fabric/data-science/data-agent-ontology-sources) · [share a data agent](https://learn.microsoft.com/fabric/data-science/data-agent-sharing).

</details>

## 🔵 Builder

The core guided comparison may be watched on screen. Optional Python execution uses the existing script:

```bash
python content/assets/lab3_tools.py --fabric
```

<details>
<summary><strong>Optional: running the Fabric cells</strong></summary>

Only run after the facilitator confirms capacity and permissions. This runs Lab 3 plus the Fabric extension, not just a read-only trace viewer. It uses your existing **`livewell-<initials>-coach`** with a new version.

For cell-by-cell use, `FABRIC_BRIDGE=true` also enables Lab 3's Fabric section. Turn it back off afterward; do not assume omission of `--fabric` disables an inherited setting. Lab 4 separately requires explicit `--fabric` for its facilitator-only specialist.

Use an interactive terminal for human approval. Non-interactive approval requests are denied; an automated rehearsal setting is not participant consent. Inspect the recorded `userQuestion`, tool order and approval response using `--verbose`.

</details>

## Checkpoint

✅ **Built** a connection from your coach to prepared cohort evidence, or followed the facilitator's run.

✅ **Did** one aggregate question and one guide question, checking each route.

✅ **Learned** to inspect outgoing arguments and distinguish descriptive cohort evidence from individual advice.

Nothing to submit. The optional programme-fit extension demonstrates #3/#6/#8/#9 together; it is not required when capacity is paused or time is short.

<details>
<summary><strong>Expected output and captured examples</strong></summary>

Mei's reference ranks **<!--ref:q_disengaged_regions.top_region-->North<!--/ref-->** first (**<!--ref:q_disengaged_regions.top_share_pct-->20.0<!--/ref-->%**), then **<!--ref:q_disengaged_regions.second_region-->West<!--/ref-->** (**<!--ref:q_disengaged_regions.second_share_pct-->17.1<!--/ref-->%**). Check figures against the computed reference, not a model's confidence label.

![Captured region aggregates](screenshots/lab-03/22-fabric-disengaged-regions.png)

![Captured guide-question trace without Fabric](screenshots/lab-03/24-no-fabric-for-citizen-question.png)

Captures show earlier runs, not a guarantee of current UI or internal query details. Optional programme-fit evidence should show only the age-band question leaving the coach, and explicit approval before any registration.

</details>

## Troubleshooting

<details>
<summary><strong>Capacity, permissions and query errors</strong></summary>

| Symptom | What to do |
|---|---|
| Capacity paused / connection unavailable | Skip the extension or watch captured evidence. Only the facilitator handles capacity and connections. |
| 403 | Check the workshop account with the facilitator; sharing an agent does not grant underlying source permissions. |
| Query error or wrong result | Facilitator checks Fabric run steps, the selected source, query, permissions and ontology mappings. Do not assume graph refresh is the fix. |
| Personal details in `userQuestion` or the answer | Stop and report the run; inspect routing instructions and tool arguments before retrying. |
| Context does not reflect changes | Facilitator checks downloaded ontology context and refreshes it if appropriate. |
| No approval request for a proposed write | Do not proceed; return to Lab 3's approval configuration. |

</details>

## Where next

[Lab 4 hosted proof](lab-04-portal.md) at 5:15, then the [bridge recap](bridge-spotlight.md).
