# Lab 1 · Agents & Knowledge — Foundry IQ

**35 min · 3:30–4:05** · **Level:** L200 · **Rails:** 🟢 Navigator + 🔵 Builder · **Patterns:** #4 Knowledge Retrieval; #1 Multi-Document Understanding in the optional intake extension

**You are here:** [Lab 0](lab-00.md) → **Lab 1** → [Lab 2](lab-02.md) → [Lab 3](lab-03.md) → [Lab 4](lab-04.md) · [README](../../README.md)

## Shared objective

> Ground every answer in curated knowledge with verifiable citations, never invent a source, and return machine-routable JSON

## Foundry features covered

Shared Foundry IQ knowledge base · portal connection (**preview**) · retrieval evidence · structured output · no-source routing.

## Story chapter

Rahim asks about food after a high-glucose screening, then about supplements the guides do not cover. [Chapter 1](../narrative/rahim.md#chapter-1--my-glucose-is-high--what-should-i-eat-lab-1--agents--knowledge--foundry-iq) contrasts an evidence-backed answer with admitting the source is silent.

## 🟢 Navigator

**Why this capability?** A model's general knowledge is not your organisation's approved guidance. Retrieval supplies relevant passages; JSON gives applications predictable fields such as `answer`, `route` and `cited_sources`. A valid JSON shape does not make the answer true.

**Already prepared:** one shared knowledge base and its indexed guide PDFs. You attach it to your agent; you do not create an index or change shared settings.

### 1. Connect the evidence source

1. Open **`livewell-<initials>`** from Lab 0. Keep `gpt-5-mini`, Reasoning effort **Low**, and no Web search.
2. **Knowledge → Add → Connect to Foundry IQ → `livewell-guides-kb` → Connect**.
3. Keep the [`base`](../prompts/coach-instructions.md#base) instructions and append [`knowledge`](../prompts/coach-instructions.md#knowledge-lab-1).
4. **Parameters** (sliders next to Model) → **Text format → JSON Schema**. Paste all of [`lab1-answer.schema.json`](../config/schemas/lab1-answer.schema.json), save the schema, close Parameters, then **Save** the agent.

The schema restricts guide ids to an allowed list. It **cannot prove a cited passage supports a claim**; you check that next.

### 2. Predict → run → inspect: an answer in the guides

**Predict:** what evidence would make food advice trustworthy?

Send `lab1_prediabetes_eat` in a new chat:

```text
My screening says my glucose is high. What should I eat to manage pre-diabetes?
```

**Inspect:** open a citation and find one passage supporting a specific sentence in the answer. Open **Response metrics → Traces** and find `knowledge_base_retrieve` and its retrieved content.

**Explain:** the source exists, it was retrieved, and it supports the claim—three different checks. `route: self_care` describes application routing; it does not itself take an action.

### 3. Predict → run → inspect: the guides are silent

Send `lab1_supplement` in a new chat:

```text
Which supplement should I take to bring my blood sugar down?
```

**Inspect:** the coach should say the guides do not cover this, use `route: clinician`, and leave `cited_sources` empty. No product or dosing recommendation should be invented.

**Explain:** why is “I have no supported answer” better than attaching an unrelated citation?

<details>
<summary><strong>Screenshots and FAQ: connection, JSON and retrieval</strong></summary>

![Select the prepared shared knowledge base](screenshots/lab-01/03-connect-foundry-iq.png)

![Parameters: Text format set to JSON Schema](screenshots/lab-01/06-json-response-format.png)

**Where are the knowledge-base settings?** Under the project's **Knowledge** area, not the attach panel. They are shared; inspect only. The workshop uses extractive passages so your agent can write its own structured reply.

**Is this training the model?** No. The source was indexed ahead of time; the agent retrieves passages when answering.

**Does JSON remove hallucination?** No. It constrains structure and allowed ids, not whether a claim follows from a passage.

**Why a shared base?** Ingestion is facilitator preparation, not the lesson. Many agents can reuse one knowledge domain without building duplicate indexes.

Further reading: [Foundry IQ](https://learn.microsoft.com/azure/foundry/agents/concepts/what-is-foundry-iq) · [agentic retrieval](https://learn.microsoft.com/azure/search/agentic-retrieval-overview) · [retrieval reasoning effort](https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-set-retrieval-reasoning-effort).

</details>

<details>
<summary><strong>Optional Pattern #1: combine two documents into a separate intake record</strong></summary>

Do this only after the core checkpoint. **Do not replace your coach's answer schema**: Lab 2 needs it.

1. Create a separate prompt agent **`livewell-<initials>-intake`** on the same `gpt-5-mini` deployment, Reasoning effort **Low**. Remove default Web search; no tools are needed.
2. Paste the [`base`](../prompts/coach-instructions.md#base) instructions, then add:

   ```text
   Combine every document the resident pastes into ONE intake record in the JSON schema.
   Copy values exactly; use null when a value is not in the documents.
   Do not diagnose and do not add advice.
   ```

3. **Parameters → Text format → JSON Schema**: paste [`lab1-intake.schema.json`](../config/schemas/lab1-intake.schema.json), save it, then save the agent.
4. Send `lab1_intake`, followed by all of [Rahim's screening summary](../data/intake/rahim-screening-summary.md) and [activity diary](../data/intake/rahim-activity-diary.md):

   ```text
   Read my screening summary and my activity diary below and fill in the intake JSON.
   ```

5. Inspect `screening`, `activity` and `preferences` against both source documents. Missing values stay `null`; no diagnosis is added.
6. Return to **`livewell-<initials>`** for Lab 2. Its knowledge connection and `livewell_answer` schema remain unchanged.

Builder's `--intake` option creates the same separate intake agent with the same generated schema.

</details>

## 🔵 Builder

Use the [existing Builder setup](../../README.md#-builder-setup):

```bash
python content/assets/lab1_knowledge.py
```

Then apply the same **inspect → explain** questions above. Builder creates **`livewell-<initials>-coach`**, not Navigator's `livewell-<initials>`.

<details>
<summary><strong>Optional: inspect the Python cells</strong></summary>

Open [`lab1_knowledge.py`](../assets/lab1_knowledge.py) as `# %%` cells. `lw.kb_tool()` uses the shared connection; `lw.create_agent()` saves the agent configuration; `lw.ask()` sends the prepared prompts. Section 5 uses a **separate** intake agent only with `--intake`.

`--verbose` exposes tool/citation detail. Keep the coach for Lab 2; `--cleanup` deletes only your `livewell-<initials>-*` agents and is not needed between labs.

</details>

## Checkpoint

✅ **Built** a coach connected to shared knowledge with a structured answer contract.

✅ **Did** a supported food answer and a no-source clinician route.

✅ **Learned** to verify a retrieved passage against a claim, not treat a citation id or JSON as proof of correctness.

Nothing to submit: show a neighbour one supported claim and explain the empty citations on the supplement answer.

<details>
<summary><strong>Expected output</strong></summary>

Food advice: `route: self_care`, a real guide id and a passage supporting the advice. The supplement answer uses `route: clinician` and empty `cited_sources`; `intent` can be `nutrition` or `out_of_scope`.

![Food answer with cited_sources](screenshots/lab-01/07-prediabetes-json-answer.png)

![Retrieval evidence in the trace](screenshots/lab-01/09-knowledge-trace.png)

![No-source answer with clinician route](screenshots/lab-01/11-json-route-clinician.png)

</details>

## Troubleshooting

<details>
<summary><strong>Missing connection, schema or citation</strong></summary>

| Symptom | What to do |
|---|---|
| Knowledge base / connection missing | Check the project and tell the facilitator. Do not create a replacement. |
| Cannot find response format | Use the sliders beside Model → Text format → JSON Schema. |
| 400 mentions the word “json” | You selected JSON Object; switch to JSON Schema and paste the supplied schema. |
| Food advice has no retrieval or citation | Check the saved knowledge block, connection and Low reasoning effort. Report the run if it still skips retrieval. |
| A real guide is cited but does not support the claim | Treat that as a grounding failure; show the passage and claim to the facilitator. |
| Output is an intake record | You opened the intake agent. Return to your main coach for Lab 2. |
| 429 / temporary failure | Wait and retry once; tell the facilitator if it persists. |

Screenshot route: [Lab 1 portal walkthrough](lab-01-portal.md).

</details>

## Where next

[Lab 2 · Guardrails, Evaluations & Tracing](lab-02.md) compares behaviour under different controls.
