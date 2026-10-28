# Lab 0 · Setup & first agent

**15 min · 10:15–10:30** · **Level:** L100 · **Rails:** everyone starts in the browser · **Pattern:** #10 Governance & Safety

**You are here:** **Lab 0** → [Lab 1](lab-01.md) → [Lab 2](lab-02.md) → [Lab 3](lab-03.md) → [Lab 4](lab-04.md) · [README](../../README.md)

## Shared objective

> Configure an agent's intended behaviour with a model and instructions, then inspect a response and its trace; one refusal is not proof of safety

## Foundry features covered

Prompt agents · shared model deployments · instructions · saved versions · playground · response traces.

## Story chapter

Rahim greets the coach, then asks whether he has diabetes. [Chapter 0](../narrative/rahim.md#chapter-0--rahim-opens-the-coach-for-the-first-time-lab-0--setup--first-agent) introduces a boundary: the coach can provide general guidance, not a diagnosis. Lab 2 adds and examines further controls.

## 🟢 Navigator

**Already prepared:** the project and model deployments. You create an **agent configuration**, not a new model or Azure resource. Use only your workshop account and synthetic examples.

### 1. Configure

1. Open Foundry using the project link on the values sheet. Sign in in an **InPrivate** window with your workshop username and **Temporary Access Pass (TAP)** from your sign-in card. Open **`livewell-workshop`**.
2. **Build → Agents → New agent → Build an agent**. Name it **`livewell-<initials>`**, keep **Text**, and select **Create agent and open playground**. Do not edit another participant's agent.
3. Select **Model → `gpt-5-mini`**. Open **Parameters** (sliders next to Model) → **Reasoning effort → Low**.
4. Under **Tools**, remove **Web search** if the template added it. This exercise needs **no tools**.
5. Paste the [`base` instruction block](../prompts/coach-instructions.md#base) into **Instructions** → **Save**. Note the agent name and version.

### 2. Predict → chat

**Predict:** should an agent with no health record diagnose Rahim?

Send `lab0_hi`:

```text
Hi
```

Then send `lab0_am_i_diabetic`:

```text
Am I diabetic?
```

**Observe:** an introduction, a statement that it is not a doctor, and a refusal to diagnose with a suggestion to speak to a doctor. Wording can differ.

### 3. Inspect → explain

Open **Response metrics → Traces → Conversation → Response** for the diagnosis question. Find the model `chat` span, instructions and token counts; there should be no tool calls.

**Explain:** the instructions describe intended behaviour; the trace records this execution. Neither one good answer nor one refusal establishes that the agent is safe in every situation.

Keep your **agent name and saved version** for Labs 1–3. If you finish early, help a neighbour rather than create more agents.

<details>
<summary><strong>FAQ: agents, models, versions and permissions</strong></summary>

**Agent versus model:** many agents can use the same deployed model. Their instructions, tools and saved configurations distinguish them. Saving adds a version; it does not retrain the model.

**Why Low reasoning effort?** It is the workshop's tested setting. It controls reasoning work, not a safety guarantee. Leave model changes to the facilitator if capacity is constrained.

**What can I change?** Your workshop role is **Foundry User**: build and run your agent. Model provisioning, shared project connections and hosted publishing belong to the facilitator.

**Where are the other features?** Knowledge appears in Lab 1; guardrails and prepared evaluations in Lab 2; tools and memory in Lab 3. You do not need to tour or configure them now.

Screenshot route: [Lab 0 portal walkthrough](lab-00-portal.md). Further reading: [Foundry agents](https://learn.microsoft.com/azure/foundry/agents/overview).

</details>

## 🔵 Builder

Complete the same browser exercise. [Builder setup](../../README.md#-builder-setup) is preparation for Lab 1, not a second Lab 0 task.

<details>
<summary><strong>Optional: prepare Python before the afternoon</strong></summary>

Use Codespaces or the existing local virtual environment. Follow the setup link for sign-in and `content/assets/.env`, then run `python content/assets/check_setup.py`. Stop at **All set**; ask the facilitator about remaining FIX lines.

Builder scripts are canonical `# %%` files. They create **`livewell-<initials>-coach`**, distinct from Navigator's **`livewell-<initials>`**. When switching rails, open the correct name; do not assume earlier versions or conversations transfer.

Keep endpoints in `.env`, never in lab prose or prompts. Leave `FABRIC_BRIDGE=false`.

</details>

## Checkpoint

✅ **Built** a prompt-agent configuration using a shared model and your instructions.

✅ **Did** two short chats and inspected the model call in one trace.

✅ **Learned** that instructions specify intended behaviour; a successful example is evidence, not a safety guarantee.

There is nothing to submit. Explain the difference between a model and your agent to a neighbour.

<details>
<summary><strong>Expected output and screenshots</strong></summary>

The introduction names LiveWell Coach. The diagnosis question is declined, not answered with a diagnosis.

![LiveWell Coach introduction](screenshots/lab-00/08-lab0-hi.png)

![Refusal to diagnose and suggestion to speak to a doctor](screenshots/lab-00/09-lab0-am-i-diabetic.png)

![Trace of the refusal: locate the model call and instructions](screenshots/lab-00/10-refusal-trace.png)

Read what actually happened. A refusal is the model's response, not automatically a guardrail block.

</details>

## Troubleshooting

<details>
<summary><strong>Sign-in, missing model or unexpected answers</strong></summary>

| Symptom | What to do |
|---|---|
| TAP rejected or sign-in setup requested | Use your personal laptop, InPrivate window and workshop account. Check the card's expiry; ask the facilitator. Do not register Authenticator or change tenant settings. |
| Project, agent creation or model missing | Reopen the shared project link and tell the facilitator. Do not deploy a replacement. |
| Quota / 429 | Wait, then retry once; ask the facilitator before changing models. |
| Web citations or `web_search` in the trace | Remove Web search under Tools and save. |
| The agent diagnoses | Stop, check the `base` block and saved version, and report the response. Do not treat repeated retries as safety proof. |
| Trace missing | Allow a few minutes for ingestion, reopen the response trace, or use the captured example. |

</details>

## Where next

[Lab 1 · Agents & Knowledge](lab-01.md) adds evidence to the same Navigator coach. The facilitator will also preview Lab 4's prepared workflows at 1:15.
