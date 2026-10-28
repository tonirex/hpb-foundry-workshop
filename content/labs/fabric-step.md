# Fabric step · Add the Resident 360 data agent as a Fabric IQ tool

**10 min guided · 5:05–5:15** · **Optional, preview** · **Rails:** 🟢 Navigator + 🔵 Builder · **Patterns:** #2 Evidence-Based Decision Support · #3 Workflow Orchestration · #6 Human-in-the-Loop Review · #8 Institutional Memory · #9 Collaboration Between Specialists

**You are here:** [Lab 3](lab-03.md) → **Fabric step** → [Lab 4 hosted proof](lab-04.md#hosted-proof) → [Bridge spotlight](bridge-spotlight.md) · [README](../../README.md)

**Your path:** [Navigator](#navigator) · [Builder](#builder) · [Checkpoint](#checkpoint) · [Troubleshooting](#troubleshooting)

## Shared objective

> Use governed cohort evidence when guidance alone cannot answer a question, and inspect exactly what information the coach sends to Fabric

## Foundry features covered

Fabric IQ tool (**preview**) · existing project connection · user identity passthrough · aggregate-only questions · comparison with Foundry IQ retrieval.

## Story chapter

Mei needs region statistics, not generic advice. Rahim's optional programme-fit question asks what his age-band cohort tends to stick with. [Chapter 3](../narrative/rahim.md#chapter-3--its-hazy-today--what-can-i-do-indoors-lab-3--tools-mcp--memory) links cohort facts to actions without sending his identity to Fabric.

## 🟢 Navigator

<a id="navigator"></a>

**Start only when the facilitator confirms active capacity, published data-agent context and your access. Otherwise skip.** Paused Fabric does not prevent core Labs 3 or 4.

**Already prepared:** `HPB Resident 360`, its data/ontology context, published `Resident360 Ontology Agent`, and `livewell-fabric-resident360`. You attach a connection, not provision items or resume capacity. Switching from Builder? Complete [Navigator Lab 3](lab-03.md#navigator) first.

### 1. Choose the evidence source

| Question | Workshop source | Why |
|---|---|---|
| “What should I eat?” | Foundry IQ guides | Approved guidance and cited passages |
| “Which regions have more disengaged residents?” | Fabric data agent | A calculation over governed records |
| “What is my profile?” | Profile API | The fixed synthetic session record |

These are our design choices, not exclusive product capabilities.

### 2. Attach the existing tool

On your Lab 3 coach, keep **`gpt-4.1-mini`**. **Tools → Add → Add tools → Configured → `livewell-fabric-resident360` → Add tool**. Append the Fabric block below, then **Save**.

Use the same workshop account in Foundry and Fabric. Missing connection or access goes to the facilitator; do not create a replacement.

<details>
<summary><strong>Required copy block and connection screenshots</strong></summary>

<!-- copy:instructions fabric -->
```text
Fabric routing rules:
- For programme-level questions about regions, age bands, programmes, events or challenges (for example
  from an HPB programme officer), use the Fabric tool (Resident360 Ontology Agent). Report aggregates only.
- Never ask the Fabric tool about an individual resident and never include a resident_id in a question to it
  or in your reply.
- When a resident asks which programme to join, or which one people like them stick with, follow these steps
  in order. Never guess their age.
  a. Call get_citizen_profile on its own and wait for the result. Do not call the Fabric tool until you have it.
  b. Ask the Fabric tool ONE question, copying the age_band field from the profile exactly (for example
     "60-64"), in exactly this form:
     "For residents in age band <age_band>, how many enrolled in each programme and how many dropped out?"
     Never add their name, area, region, gender or screening risk.
  c. Recommend the programme with the lowest drop-out share that they are not already in and have not
     dropped, say why it fits their profile, and quote the cohort numbers as Fabric gives them (keep "fewer
     than 5" as it is, and write "fewer than 5" for any count from 1 to 4 that Fabric did not mask).
  d. Use find_activities to find that programme's intake session near them, and ask before register_interest.
- Other citizen questions about food, activity, sleep or screening still go to the knowledge base and the
  profile tool, never to Fabric.
```
<!-- /copy -->

![Existing Fabric IQ connection](screenshots/lab-03/17-existing-fabric-connection.png)

Only the facilitator uses OneLake Catalog to create the connection if missing:

![Facilitator reference: published agent in OneLake Catalog](screenshots/lab-03/16-fabric-iq-onelake-catalog.png)

<!-- historical-screenshot: screenshots/lab-03/18-fabric-instructions.png -->

</details>

### 3. Predict → run → inspect

**Predict:** would a guide PDF be enough to calculate this? As Mei, send `fabric_q_disengaged_regions` in a new chat:

<!-- copy:prompt fabric_q_disengaged_regions -->
```text
Which regions have the highest share of disengaged residents?
```
<!-- /copy -->

Open **Response metrics → Traces → Fabric IQ call → Input**. Inspect **`userQuestion`**: region aggregates, not an individual record. Inspect the returned groups and any errors. Allow time for the preview; do not repeatedly resend.

### 4. Compare with a guide question

In another new chat, send `lab1_prediabetes_eat`:

<!-- copy:prompt lab1_prediabetes_eat -->
```text
My screening says my glucose is high. What should I eat to manage pre-diabetes?
```
<!-- /copy -->

Expect knowledge retrieval and **no Fabric call in a complete trace**. Missing telemetry is not routing proof.

**Explain:** why did the source change, and which argument shows what left the coach?

<details>
<summary><strong>Optional extension: programme fit, then an approved action</strong></summary>

Only with extra time and facilitator approval. The core comparison is enough for the guided slot.

As Rahim, send `lab3_programme_fit` in a new chat:

<!-- copy:prompt lab3_programme_fit -->
```text
I dropped out of Healthier SG last year. Which programme do people my age actually stick with? Find me a way to start near Woodlands and sign me up.
```
<!-- /copy -->

Inspect **profile → Fabric cohort question → activities → proposed registration**. Fabric's `userQuestion` must contain **age band only**: no name, resident ID, area, gender or screening risk. Counts below five should say “fewer than 5”; this workshop output rule is not proof of complete privacy protection.

If asked to confirm, send `lab3_programme_confirm` in the same chat:

<!-- copy:prompt lab3_programme_confirm -->
```text
Yes, please sign me up for the Diabetes Prevention intake session.
```
<!-- /copy -->

Then inspect the tool card and choose **Approve → Approve once** or **Deny**. Chat “yes” does not replace approval. Registration is synthetic and temporary.

The computed reference recommends **<!--ref:q_programme_fit.recommended_programme-->Diabetes Prevention<!--/ref-->** among applicable programmes he is not already in: drop-out **<!--ref:q_programme_fit.recommended_dropout_pct-->21.6<!--/ref-->%**, versus **<!--ref:q_programme_fit.dropped_programme_dropout_pct-->37.1<!--/ref-->%** for **<!--ref:q_programme_fit.dropped_programme-->Healthier SG<!--/ref-->**. Descriptive cohort evidence does not prove a programme will work for an individual.

<!-- historical-screenshot: screenshots/lab-03/19-programme-fit-recommendation.png -->
<!-- historical-screenshot: screenshots/lab-03/20-programme-fit-fabric-question.png -->
<!-- historical-screenshot: screenshots/lab-03/21-programme-fit-approved.png -->

</details>

<details>
<summary><strong>FAQ: ontology context, identity and current execution</strong></summary>

**What does ontology do?** It provides terms, relationships and source mappings. The data agent generates **source-native SQL, KQL or DAX**, executed by the underlying source. Ontology is not itself the query endpoint.

**Where is the internal query?** Foundry records the external request/response where available. Inspect Fabric run steps for the selected source, generated query and errors; do not assume GQL or a specific internal tool name.

**Does sharing the agent grant data access?** No. Users also need relevant ontology and source permissions; the request uses the caller's identity.

**Citizen sign-in design?** No. Tenant users act out a synthetic scenario. A public citizen app needs its own authentication and authorised data-access design.

**What was configured?** The facilitator attached `resident_ontology` through **Sources → Add sources → Add an ontology**, then published and verified it. Check stale downloaded context and source bindings before assuming graph refresh is the fix.

Further reading: [ontology as context](https://learn.microsoft.com/fabric/data-science/data-agent-ontology-sources) · [share a data agent](https://learn.microsoft.com/fabric/data-science/data-agent-sharing).

</details>

## 🔵 Builder

<a id="builder"></a>

Watching the guided comparison is sufficient. Optional execution:

```bash
python content/assets/lab3_tools.py --fabric
```

<details>
<summary><strong>Optional: running and inspecting the Fabric cells</strong></summary>

Only run after readiness is confirmed. This runs Lab 3 **and** Fabric, not just a trace viewer, and creates a new version of your Builder coach.

`FABRIC_BRIDGE=true` also enables Lab 3's Fabric section without the flag. Turn it off afterwards. Lab 4 separately requires explicit `--fabric` for its facilitator-only specialist.

Use an interactive terminal for approval; unattended runs deny. `--verbose` exposes outgoing `userQuestion`, tool order and approval. `--cleanup` removes only your agents.

### How the code works

Section 10 of [`lab3_tools.py`](../assets/lab3_tools.py) adds `FabricIQPreviewTool` to the same coach via [`fabric_tool()`](../assets/common/livewell_common.py). It asks Mei's question, the guide control and programme fit. Recorded arguments establish the age-band-only boundary and profile-before-Fabric order; the separate tool approval gates registration.

![Historical Builder reference, not current-runtime proof](screenshots/lab-03/builder-output-fabric.png)

</details>

## Checkpoint

✅ **Built** a connection to prepared cohort evidence, or followed the facilitator's run.

✅ **Did** one aggregate and one guide question, checking their routes.

✅ **Learned** to inspect outgoing arguments and distinguish cohort evidence from personal advice.

Nothing to submit. Optional programme fit brings #3/#6/#8/#9 together; it is not required when capacity is paused or time is short.

<details>
<summary><strong>Expected output</strong></summary>

Mei's reference ranks **<!--ref:q_disengaged_regions.top_region-->North<!--/ref-->** first (**<!--ref:q_disengaged_regions.top_share_pct-->20.0<!--/ref-->%**), then **<!--ref:q_disengaged_regions.second_region-->West<!--/ref-->** (**<!--ref:q_disengaged_regions.second_share_pct-->17.1<!--/ref-->%**). Check computed reference figures, not confidence labels.

<!-- historical-screenshot: screenshots/lab-03/22-fabric-disengaged-regions.png -->
<!-- historical-screenshot: screenshots/lab-03/23-fabric-iq-trace.png -->
<!-- historical-screenshot: screenshots/lab-03/24-no-fabric-for-citizen-question.png -->

Earlier portal captures remain archived rather than presented as current-runtime evidence. Inspect live or facilitator-prepared evidence with its provenance.

</details>

## Troubleshooting

<details>
<summary><strong>Capacity, permissions and query errors</strong></summary>

| Symptom | What to do |
|---|---|
| Capacity paused / connection missing | Skip or watch the facilitator; do not resume or create resources. |
| 403 | Check the account and underlying source permissions with the facilitator. |
| Query error / wrong result | Inspect Fabric run steps, selected source, query and ontology mappings. |
| Personal details leave the coach | Stop and report the run; inspect instructions and arguments before retrying. |
| Stale context | Facilitator checks downloaded ontology context and refreshes if appropriate. |
| No approval for a write | Stop and return to Lab 3's approval configuration. |

</details>

## Where next

[Lab 4 hosted proof](lab-04.md#hosted-proof) at 5:15, then [Bridge spotlight](bridge-spotlight.md).
