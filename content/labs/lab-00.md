# Lab 0 · Setup & first agent

**15 min · Level L100 · Pattern #10 Governance & Safety**

> **Choose one track:** Navigator or Builder. Stay on that track throughout the workshop; the agents are separate.
> **Stuck?** Go to [Checkpoint](#checkpoint) and expand **Expected output (open after you have tried it)**. Use the examples to follow the lesson and ask for help rather than retry repeatedly.

**Your path:** [Navigator](#navigator) · [Builder](#builder) · [Checkpoint](#checkpoint) · [Troubleshooting](#troubleshooting)

## Shared objective

> Configure an agent's intended behaviour with a model and instructions, then inspect a response and its trace; one refusal is not proof of safety

## Foundry features covered

Model + instructions · saved agent versions · playground or Python · response traces.

## Story chapter

Rahim greets the coach, then asks whether he has diabetes. The coach should offer general guidance, not a diagnosis.

## 🟢 Navigator

<a id="navigator"></a>

### 1. Open the project and create your agent

Use your personal laptop and an InPrivate window. Open the supplied project link, sign in with your workshop username and **Temporary Access Pass**, and select **`livewell-workshop`**.

![Select the shared project](screenshots/lab-00/03-open-livewell-project.png)

Select **Build → Agents → New agent → Build an agent**.

![Choose Build an agent](screenshots/lab-00/05-new-agent-menu.png)

Name it **`livewell-<initials>`**, keep **Text**, then select **Create agent and open playground**. Screenshots use `livewell-wxyz`; edit only your own agent.

![Create your agent with Text interaction mode](screenshots/lab-00/06-create-agent.png)

### 2. Set its behaviour

Select **Model → `gpt-5-mini`**. Open **Parameters** (sliders beside Model) → **Reasoning effort → Low**. Remove **Web search** under Tools if the template added it.

![Low reasoning effort and no tools](screenshots/lab-00/06b-reasoning-low-no-tools.png)

Replace the example **Instructions** with this block, then **Save**:

<details>
<summary><strong>Copy the base instructions</strong></summary>

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

![Base instructions saved on the practice agent](screenshots/lab-00/07-base-instructions-saved.png)

### 3. Chat, then inspect

Send `lab0_hi`:

<!-- copy:prompt lab0_hi -->
```text
Hi
```
<!-- /copy -->

![The coach introduces itself and states its limits](screenshots/lab-00/08-lab0-hi.png)

Send `lab0_am_i_diabetic`:

<!-- copy:prompt lab0_am_i_diabetic -->
```text
Am I diabetic?
```
<!-- /copy -->

![The coach declines to diagnose](screenshots/lab-00/09-lab0-am-i-diabetic.png)

Open the diagnosis response's **Traces → Conversation → Response**. Inspect its **Invoke Agent** and `chat` spans: model, instructions and tokens, with no tool calls. The conversation includes both turns; inspect the refusal's response, not the combined call count.

![The response trace shows the model call without tools](screenshots/lab-00/10-refusal-trace.png)

Keep your agent for Navigator Lab 1.

## 🔵 Builder

<a id="builder"></a>

**Before starting:** use the prepared Codespace or your local environment from [Builder setup](../../README.md#-builder-setup). Set your initials and supplied project endpoint in `content/assets/.env`. No Navigator agent is needed.

1. Check readiness:

   ```bash
   python content/assets/check_setup.py
   ```

   Continue when it says **All set**; ask for help with remaining FIX lines.
2. Create and test your own model-and-instructions agent:

   ```bash
   python content/assets/lab0_setup.py --verbose
   ```

   Alternatively, open [`lab0_setup.py`](../assets/lab0_setup.py) and run its `# %%` cells in order.
3. Inspect the printed introduction and diagnosis reply, model details and empty tool lists. To inspect the service trace, open your Builder agent **`livewell-<initials>-coach` → Traces** and locate the response ID printed in the terminal.

The script uses a shared model deployment, creates no model resources, and keeps your Builder coach for Lab 1. Do not run Navigator's creation steps or use `--cleanup` between labs.

## Checkpoint

✅ **Built** your own agent configuration with a model and instructions.

✅ **Did** an introduction, a diagnosis question and an execution inspection.

✅ **Learned** that intended behaviour and one successful example are not a safety guarantee.

<details>
<summary><strong>Expected output (open after you have tried it)</strong></summary>

The coach introduces itself, says it is not a doctor, and declines to diagnose. Wording varies.

![Example refusal, not a safety certification](screenshots/lab-00/09-lab0-am-i-diabetic.png)

Builder prints the two responses and a `CHECKPOINT` block. Its agent is `livewell-<initials>-coach`; Navigator's is `livewell-<initials>`. Both have no tools in this lab.

</details>

## Troubleshooting

<details>
<summary><strong>Troubleshooting</strong></summary>

| Problem | Next action |
|---|---|
| Sign-in rejected or extra registration requested | Check your workshop account and pass expiry; ask for help. Do not change sign-in settings. |
| Project/model missing | Reopen the supplied project link; do not deploy a replacement. |
| Web citations appear | Remove Web search and save. |
| The coach diagnoses | Check the copied instructions and saved version; report the answer. |
| Trace missing | Allow ingestion time and reopen it. Use the expected-output example if still unavailable. |
| 429 | Wait and retry once, then ask for help. |

</details>

## Where next

[Lab 1 · Agents & Knowledge](lab-01.md)—continue on the same track.
