# Lab 0 · Setup & first agent

**15 min · 10:15–10:30** · **Level:** L100 · **Rails:** everyone starts in the browser · **Pattern:** #10 Governance & Safety

**You are here:** **Lab 0** → [Lab 1](lab-01.md) → [Lab 2](lab-02.md) → [Lab 3](lab-03.md) → [Lab 4](lab-04.md) · [README](../../README.md)

**Your path:** [Navigator](#navigator) · [Builder setup](#builder) · [Checkpoint](#checkpoint) · [Troubleshooting](#troubleshooting)

## Shared objective

> Configure an agent's intended behaviour with a model and instructions, then inspect a response and its trace; one refusal is not proof of safety

## Foundry features covered

Prompt agents · shared model deployments · instructions · saved versions · playground · response traces.

## Story chapter

Rahim greets the coach, then asks whether he has diabetes. [Chapter 0](../narrative/rahim.md#chapter-0--rahim-opens-the-coach-for-the-first-time-lab-0--setup--first-agent) introduces a boundary: the coach provides general guidance, not a diagnosis. Lab 2 examines further controls.

## 🟢 Navigator

<a id="navigator"></a>

**Already prepared:** the project and model deployments. You create an **agent configuration**, not a model or Azure resource. Use only your workshop account and synthetic examples.

### 1. Configure

1. On a personal laptop, open the values sheet's project link in an **InPrivate** window. Sign in with your workshop username and **Temporary Access Pass (TAP)** from the sign-in card. Open **`livewell-workshop`**.
2. **Build → Agents → New agent → Build an agent**. Name it **`livewell-<initials>`**, keep **Text**, and select **Create agent and open playground**. Do not edit another participant's agent.
3. In the playground, select **Model → `gpt-5-mini`**. Open **Parameters** (sliders beside Model) → **Reasoning effort → Low**.
4. Under **Tools**, remove **Web search** if the template added it. This exercise needs **no tools**.
5. Expand the block below, use its **Copy** button, and **replace** the example Instructions. Select **Save** and note your agent name and version.

<details>
<summary><strong>Required copy block: base instructions</strong></summary>

<!-- copy:instructions base -->
```text
You are LiveWell Coach, a friendly healthy-living coach for residents of Singapore, built for a
Health Promotion Board (HPB) style workshop. You help with food, physical activity, sleep and
health-screening reminders.

Rules you always follow:
1. You are not a doctor. Say so when you introduce yourself and whenever someone asks for a diagnosis.
2. Never diagnose. If someone asks whether they have a condition, explain you cannot tell and suggest
   they speak to a doctor.
3. Never recommend a medication or give dosing advice. Refer medication questions to a doctor or pharmacist.
4. For urgent symptoms (chest pain, breathlessness, fainting, thoughts of self-harm) tell the person to
   call 995 or go to the nearest emergency department.
5. Keep answers short, warm and practical, in plain Singapore English.
6. Only discuss the person you are talking to. Never reveal or look up another resident's information.
7. If you do not have the information to answer safely, say "I don't have enough information to answer
   that safely" and suggest who can help.

Glossary (use these words exactly):
- MVPA = moderate-to-vigorous physical activity minutes.
- Healthpoints = the Healthy 365 rewards currency, redeemed as eVouchers.
- eVouchers = merchant vouchers that residents redeem with Healthpoints.
- disengaged = is_disengaged = 1 (low steps AND no events attended AND a dropped programme).
- hazy = regional 24-hour PSI >= 55 (a regional context proxy, not individual exposure).
- screening risk = the risk band from a resident's latest health screening (Low, Moderate, High or Not Screened).
- event occurrence = one dated, regional instance of an event (event_occurrence_id), not the recurring event series (event_id).
```
<!-- /copy -->

</details>

### 2. Predict → chat

**Predict:** should an agent with no health record diagnose Rahim?

Send `lab0_hi`:

<!-- copy:prompt lab0_hi -->
```text
Hi
```
<!-- /copy -->

Then send `lab0_am_i_diabetic`:

<!-- copy:prompt lab0_am_i_diabetic -->
```text
Am I diabetic?
```
<!-- /copy -->

**Observe:** an introduction, a statement that it is not a doctor, and a refusal to diagnose with a suggestion to speak to a doctor. Wording can differ.

### 3. Inspect → explain

Open **Response metrics → Traces → Conversation → Response** for the diagnosis question. Inspect that response's **Invoke Agent** entry and its model `chat` span, instructions and token counts. There should be no tool calls. The conversation contains two turns; do not mistake its two chat calls for two calls in one answer.

**Explain:** instructions describe intended behaviour; the trace records this execution. Neither one good answer nor one refusal establishes safety in every situation.

Keep your **agent name and saved version** for Labs 1–3. Help a neighbour rather than create more agents.

<details>
<summary><strong>Setup screenshots and FAQ</strong></summary>

Screenshots use the practice agent `livewell-wxyz`; use your own initials. Version numbers can differ.

![Project picker with livewell-workshop selected](screenshots/lab-00/03-open-livewell-project.png)

![Foundry navigation and the shared agent list](screenshots/lab-00/04-portal-tour-build.png)

![New agent menu with Build an agent selected](screenshots/lab-00/05-new-agent-menu.png)

![Create an agent with your initials and Text interaction mode](screenshots/lab-00/06-create-agent.png)

![gpt-5-mini with Low reasoning effort and no tools](screenshots/lab-00/06b-reasoning-low-no-tools.png)

![Base instructions saved on the practice agent](screenshots/lab-00/07-base-instructions-saved.png)

**Agent versus model:** many agents can share a model deployment. Their instructions, tools and saved configurations distinguish them. Saving creates a version; it does not retrain the model.

**Why Low?** It is the workshop's tested setting, not a safety guarantee. Leave model changes to the facilitator if capacity is constrained.

**Permissions:** Foundry User lets you build and run your agent. Shared connections, model deployment and hosted publishing belong to the facilitator. Do not use the portal **Workflows** item.

Further reading: [Foundry agents](https://learn.microsoft.com/azure/foundry/agents/overview).

</details>

## 🔵 Builder

<a id="builder"></a>

Complete the same browser exercise. [Builder setup](../../README.md#-builder-setup) is preparation for Lab 1, not a second Lab 0 task.

<details>
<summary><strong>Optional: prepare Python before the afternoon</strong></summary>

Use Codespaces or your local virtual environment. Follow Builder setup for sign-in and `content/assets/.env`, then run:

```bash
python content/assets/check_setup.py
```

Stop at **All set**; ask the facilitator about remaining FIX lines. Leave `FABRIC_BRIDGE=false`.

Builder scripts are canonical `# %%` files. They use **`livewell-<initials>-coach`**, distinct from Navigator's **`livewell-<initials>`**. [Switching rails](../../README.md#switching-rails) does not transfer configurations, versions or conversations.

</details>

## Checkpoint

✅ **Built** a prompt-agent configuration using a shared model and your instructions.

✅ **Did** two short chats and inspected one response's model call.

✅ **Learned** that intended behaviour and a successful example are not a safety guarantee.

Nothing to submit: explain the difference between a model and your agent to a neighbour.

<details>
<summary><strong>Expected output</strong></summary>

![LiveWell Coach introduces itself and states that it is not a doctor](screenshots/lab-00/08-lab0-hi.png)

![The coach refuses to diagnose and suggests speaking to a doctor](screenshots/lab-00/09-lab0-am-i-diabetic.png)

![Inspect the refusal's model span and instructions](screenshots/lab-00/10-refusal-trace.png)

A refusal is the model's response, not automatically a guardrail block.

</details>

## Troubleshooting

<details>
<summary><strong>Sign-in, missing model or unexpected answers</strong></summary>

| Symptom | What to do |
|---|---|
| TAP rejected or sign-in setup requested | Check the card's expiry, personal laptop and InPrivate window; ask the facilitator. Do not register Authenticator or change tenant settings. |
| Project, agent creation or model missing | Reopen the shared project link and tell the facilitator. Do not deploy a replacement. |
| Quota / 429 | Wait, then retry once; ask before changing models. |
| Web citations or `web_search` in the trace | Remove Web search under Tools and save. |
| The agent diagnoses | Check the copied base block and saved version, and report the response. Do not treat repeated retries as safety proof. |
| Trace missing | Allow ingestion time and reopen it, or use the captured example. Do not resend a successful request just to obtain telemetry. |

</details>

## Where next

[Lab 1 · Agents & Knowledge](lab-01.md) adds evidence to the same Navigator coach. The facilitator previews Lab 4's prepared workflows at 1:15.
