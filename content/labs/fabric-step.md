# Fabric step · Compare governed data with document knowledge

**10 min · Optional, preview · Pattern #2 Evidence-Based Decision Support**

> **Stay on your chosen track; do not switch midway.**
> **Stuck?** Go to [Checkpoint](#checkpoint) and expand **Expected output (open after you have tried it)**. Use the examples and ask for help. If this optional service is unavailable, continue to Lab 4.

**Your path:** [Navigator](#navigator) · [Builder](#builder) · [Checkpoint](#checkpoint) · [Troubleshooting](#troubleshooting)

## Shared objective

> Use governed cohort evidence when guidance alone cannot answer a question, and inspect exactly what information the coach sends to Fabric

## Foundry features covered

Prepared Fabric IQ connection (**preview**) · aggregate queries · tool routing and trace evidence.

## Story chapter

Mei needs region statistics; Rahim needs food guidance. Compare the sources used to answer those two questions.

## 🟢 Navigator

<a id="navigator"></a>

**Before starting:** use your Navigator Lab 3 coach on **`gpt-4.1-mini`**. Do this step only when workshop Fabric access is available.

### 1. Attach the prepared connection

Select **Tools → Add → Add tools → Configured → `livewell-fabric-resident360` → Add tool**. If absent, ask for help rather than create a connection.

![Select the existing Fabric IQ connection](screenshots/lab-03/17-existing-fabric-connection.png)

Append these read-only routing instructions and **Save**:

<details>
<summary><strong>Copy the Fabric comparison instructions</strong></summary>

<!-- copy:instructions fabric_read -->
```text
Read-only source comparison:
- For population questions about regions and disengagement, ask the Fabric tool (Resident360 Ontology Agent)
  directly for aggregates. Do not narrow the question using an individual profile or remembered preferences.
- Never ask Fabric about an individual or send a resident_id, name or other personal identifier to it.
- For food, activity, sleep or screening guidance, search the LiveWell knowledge base instead, not Fabric.
- Preserve the current JSON answer format. Use route programme_insights for aggregate questions when the
  format contains a route field. Do not invent guide citations for Fabric data.
- Do not register interest or take any other write action in this comparison.
```
<!-- /copy -->

</details>

### 2. Ask for population evidence

In a new chat, send `fabric_q_disengaged_regions`:

<!-- copy:prompt fabric_q_disengaged_regions -->
```text
Which regions have the highest share of disengaged residents?
```
<!-- /copy -->

Open **Traces → Fabric IQ call → Input**. Inspect **`userQuestion`**: it should request region aggregates, not an individual record. Inspect the returned groups and any error.

<!-- historical-screenshot: screenshots/lab-03/22-fabric-disengaged-regions.png -->
<!-- historical-screenshot: screenshots/lab-03/23-fabric-iq-trace.png -->

### 3. Compare with a guide question

In another new chat, send `lab1_prediabetes_eat`:

<!-- copy:prompt lab1_prediabetes_eat -->
```text
My screening says my glucose is high. What should I eat to manage pre-diabetes?
```
<!-- /copy -->

Inspect the complete trace: **knowledge retrieval, without a Fabric call**. Explain why the source changed.

<!-- historical-screenshot: screenshots/lab-03/24-no-fabric-for-citizen-question.png -->

## 🔵 Builder

<a id="builder"></a>

**Before starting:** use your Builder environment from Lab 0. Enable `FABRIC_BRIDGE=true` in `content/assets/.env` only when workshop Fabric access is available. You do not need a Navigator agent.

```bash
python content/assets/lab3_fabric.py --verbose
```

Or run [`lab3_fabric.py`](../assets/lab3_fabric.py) as `# %%` cells.

1. The script creates **`livewell-<initials>-fabric`** with the prepared knowledge and Fabric connections, leaving your Lab 3 coach unchanged.
2. Inspect the region answer and Fabric tool arguments. Only aggregates should be requested.
3. Inspect the food answer: `knowledge_base_retrieve` should appear, with no Fabric call.
4. Read the `CHECKPOINT`. This script makes no registrations and does not rerun Lab 3.

Set `FABRIC_BRIDGE=false` afterwards. `--cleanup` removes only this run's own agents if requested.

## Checkpoint

✅ **Built** a configuration that can choose between two prepared evidence sources.

✅ **Did** a population question and a guide question, inspecting each route.

✅ **Learned** to inspect outgoing tool arguments and distinguish aggregate data from individual guidance.

<details>
<summary><strong>Expected output (open after you have tried it)</strong></summary>

![Prepared Fabric connection: configuration reference](screenshots/lab-03/17-existing-fabric-connection.png)

The computed region reference ranks **<!--ref:q_disengaged_regions.top_region-->North<!--/ref-->**
(**<!--ref:q_disengaged_regions.top_share_pct-->20.0<!--/ref-->%**) before
**<!--ref:q_disengaged_regions.second_region-->West<!--/ref-->**
(**<!--ref:q_disengaged_regions.second_share_pct-->17.1<!--/ref-->%**).
The guide answer uses retrieved passages instead. A missing trace is not proof of correct routing.

Builder prints the two answers, their tool lists and the source-routing checks. If Fabric is unavailable, use this reference to discuss the distinction without claiming a live pass.

Live result screenshots were deferred while the workshop capacity was paused; the figures above are the computed data reference, not a new execution.

</details>

## Troubleshooting

<details>
<summary><strong>Troubleshooting</strong></summary>

| Problem | Next action |
|---|---|
| Fabric unavailable / capacity paused | Skip this optional exercise and continue to Lab 4; do not resume capacity yourself. |
| Connection missing / 403 | Check the workshop account and ask for help. |
| Slow response | Allow time for the preview service; do not send repeated requests. |
| Wrong figure or query error | Record the answer/error and inspect the tool response. Do not invent a replacement. |
| Individual details in `userQuestion` | Stop and report the run. |
| Guide question calls Fabric | Check the saved routing instructions and report the trace. |

</details>

## Where next

[Lab 4 · Multi-agent & Hosted deploy](lab-04.md)—continue on the same track.
