# Lab 0 · Setup & first agent

**15 min** · **Morning** · **Audience:** all rails · **Level:** L100 · **Rails:** 🟢 Navigator portal-only · **Patterns:** #10 Governance & Safety

**You are here:** **Lab 0** → [Lab 1](lab-01.md) → [Lab 2](lab-02.md) → [Lab 3](lab-03.md) ([Fabric step](fabric-step.md)) → [Lab 4](lab-04.md) → [Bridge spotlight](bridge-spotlight.md) · [README](../../README.md)

**Your path:** [Navigator](#navigator) · [Builder setup](#builder) · [Checkpoint](#checkpoint) · [Troubleshooting](#troubleshooting)

## Shared objective

> A Foundry agent is a model plus instructions, and instructions alone can make it safe; every answer leaves a trace you can inspect

Patterns: #10 Governance & Safety.

## Foundry features covered

- New Foundry portal project navigation: Models, Agents, Tools, Guardrails, Evaluations, Traces/Monitor.
- Prompt agent creation: model + instructions + playground chat.
- Model choice and parameters: `gpt-5-mini` with **Reasoning effort** set to **Low**.
- Traces: one model call per answer, with the model name, instructions and token counts.
- Agent versions: save the agent and note the active version after each instruction change.
- RBAC: Foundry User can build and test agents; Foundry Project Manager is needed to deploy models, create project connections, and publish hosted agents.

## Story chapter

[Chapter 0](../narrative/rahim.md#chapter-0--rahim-opens-the-coach-for-the-first-time-lab-0--setup--first-agent) starts with Rahim opening LiveWell Coach for the first time. He greets it, then asks whether he has diabetes. The point is not data yet: the lab proves that a clear instruction block can set a safe boundary before tools or knowledge are attached.

## 🟢 Navigator

<a id="navigator"></a>

Use a personal laptop and a private browser window. Open [Microsoft Foundry](https://ai.azure.com), sign in with
your workshop account, and complete Authenticator registration if prompted. These account-specific screens are
text-only. Screenshots below use facilitator demo agents; always edit your own `livewell-<initials>`.

1. Sign in to the Microsoft Foundry portal with **your own workshop account** (the username on your sign-in card) and open the shared project **`livewell-workshop`**.

   ![Project picker with livewell-workshop selected](screenshots/lab-00/03-open-livewell-project.png)

2. Take the quick tour:
   - **Models** — where `gpt-5-mini` (Labs 0-2) and `gpt-4.1-mini` (Lab 3 on) are deployed.
   - **Agents** — where you create and test prompt agents.
   - **Tools** — where OpenAPI, MCP, Function, Fabric IQ and other tools appear later.
   - **Guardrails** — where shared safety policies are attached.
   - **Evaluations** — where batch and quality checks live.
   - **Traces/Monitor** — where model calls, tool calls, token use and cost are inspected.
   ![Build area with Agents, Knowledge, Evaluations and Guardrails](screenshots/lab-00/04-portal-tour-build.png)

3. RBAC checkpoint: **Foundry User** is sufficient to create prompt agents and run playground tests. Model deployment, new project connections and hosted publishing are facilitator tasks requiring **Foundry Project Manager** or broader permissions. Even if your workshop account has broader rights, do not change shared resources.
4. Go to **Agents** → **New agent** → **Build an agent**.

   ![New agent menu with Build an agent selected](screenshots/lab-00/05-new-agent-menu.png)

5. Name it **`livewell-<initials>`**. Use your initials only, for example `livewell-abc`. Keep **Interaction mode** on **Text** and select **Create agent and open playground**.

   ![Create an agent dialog with the initials name and Text interaction mode](screenshots/lab-00/06-create-agent.png)

6. In the playground, open the **Model** dropdown and select **`gpt-5-mini`**. The dialog in step 5 has no model picker, and the playground may start on another deployment.
7. Select the **Parameters** icon (the sliders next to the **Model** dropdown) and set **Reasoning effort** to **Low**. Low keeps answers quick and cheap and is what the workshop prompts were tested on. Do not pick **Minimal**: from Lab 1 on, it tends to skip the knowledge search.
8. Check **Tools**. The **Build an agent** template can attach **Web search** by default. If it is listed, remove it (**⋯ → Remove**). Your Lab 0 agent has no tools; Labs 1 and 3 add the ones the coach needs.
   ![gpt-5-mini with Reasoning effort Low and no tools](screenshots/lab-00/06b-reasoning-low-no-tools.png)

9. Open **Instructions**. Copy the complete block below using its top-right **Copy** button and **replace** the example instructions. The same copy control is used throughout the labs; do not copy instructions from a screenshot.

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

   <!-- historical-screenshot: screenshots/lab-00/07-base-instructions-saved.png -->

10. **Save** the agent. Note the saved version shown in the portal.
11. Open the chat playground. Send (`lab0_hi`):

    <!-- copy:prompt lab0_hi -->
    ```text
    Hi
    ```
    <!-- /copy -->

    The agent should introduce itself as LiveWell Coach and say it is not a doctor.
12. Send (`lab0_am_i_diabetic`):

    <!-- copy:prompt lab0_am_i_diabetic -->
    ```text
    Am I diabetic?
    ```
    <!-- /copy -->

    The agent should refuse to diagnose and suggest speaking to a doctor.
13. Open the trace for that answer (**Response metrics → Traces**). Find one `chat gpt-5-mini` span under the agent, no tool calls, the `base` block as the system message, and the input and output token counts. Output tokens include the model's reasoning tokens, so a Low reasoning effort also keeps the bill down.

What to record before you leave the portal:

| Item | Where to find it | Why it matters later |
|---|---|---|
| Agent name | Agents list | Labs 1-3 keep extending the same Navigator agent. |
| Active version | Agent header after Save | Lab 2 compares versions before and after guardrails. |
| Model and tokens | The trace for `lab0_am_i_diabetic` | Lab 3 reads the same trace to see tool calls and their cost. |

Keep the chat short in Lab 0. The goal is to prove that the trace, version and refusal behaviour are visible, not to test the model at length.

If you finish early, help a neighbour check the trace rather than creating extra agents.

## 🔵 Builder

<a id="builder"></a>

Lab 0 is the same portal exercise for everyone. Builders then use the remaining time to get ready for Lab 1, following [Builder setup](../../README.md#-builder-setup) (about 5 minutes):

1. Open the repository in **Codespaces** (Code → Codespaces → Create codespace on main), or use your local clone with its `.venv` active.
2. Sign in as your own workshop account in the same private browser window:

   ```bash
   az login --use-device-code --allow-no-subscriptions
   ```

3. Create your settings file (works in Codespaces/bash and PowerShell), then open it in your editor:

   ```bash
   cp content/assets/.env.sample content/assets/.env
   ```

   Set `INITIALS=` to your initials and `FOUNDRY_PROJECT_ENDPOINT=` to the **Project endpoint** from the values sheet. Leave `FABRIC_BRIDGE=false`. Do not overwrite an existing `.env` if you already completed setup.
4. Repeat this check until it ends with **All set: start Lab 1**. Each FIX line says what to change:

   ```bash
   python content/assets/check_setup.py
   ```

From Lab 1 onward, Builder scripts are linear `# %%` cell files. Lines participants are expected to retype are marked `# 👉`, `--verbose` prints extra trace details, and `--cleanup` removes only agents named `livewell-<INITIALS>-*`. The scripts create agents on the same models as the portal: `gpt-5-mini` at Low reasoning effort, and `gpt-4.1-mini` for the Lab 3 coach. Both names come from `content/config/workshop.yaml`, and `.env` can override them.

Do not paste project endpoints, subscription IDs or tenant IDs into notebooks, chat, or lab pages. Keep those values in `.env` and the facilitator values sheet only.

That habit is part of the governance pattern, not just setup hygiene.

## Checkpoint

✅ **Built** a safe prompt agent named `livewell-<initials>`.

✅ **Did** the first safety tests and read the trace of one answer.

✅ **Learned** that a Foundry agent starts as model + instructions, and that every answer leaves a trace with the model, the instructions and the token counts.

There is nothing to submit. Try the steps first, then open **Expected output** to compare.

<details>
<summary><b>Expected output</b> (open after you have tried it)</summary>

**What this demonstrates.** A Foundry prompt agent is a model plus instructions, saved as a version. The `base` block alone sets the persona and the first safety rule: the coach introduces itself, says it is not a doctor and refuses to diagnose. The agent configuration shows **Tools: none**; if **Web search** is still listed, remove it and save again.

`lab0_hi`: the coach introduces itself as LiveWell Coach and says it is not a doctor.

<!-- historical-screenshot: screenshots/lab-00/08-lab0-hi.png -->

`lab0_am_i_diabetic`: a refusal to diagnose, with a suggestion to see a doctor. In the trace, look for one `chat gpt-5-mini` span under the agent, no tool calls, the `base` block as the system message, and the token counts.

<!-- historical-screenshot: screenshots/lab-00/09-lab0-am-i-diabetic.png -->

<!-- historical-screenshot: screenshots/lab-00/10-refusal-trace.png -->

</details>

## Troubleshooting

| Symptom | Fix |
|---|---|
| Sign-in loops or MFA never completes | Use an InPrivate window, your personal laptop, and the Authenticator prompt for your own workshop account (not your work account). |
| You cannot see **`livewell-workshop`** | Confirm you are in the lab tenant and ask the facilitator to refresh your Foundry User assignment. |
| No **New agent** button | You may be outside the project or missing Foundry User. Re-open the project from the values sheet shown on screen. |
| `gpt-5-mini` returns 429 or quota errors | Wait 30 seconds and resend. If it keeps happening, switch the agent model to `gpt-4.1-mini`, save, and tell the facilitator. |
| No **Reasoning effort** under Parameters | You are not on `gpt-5-mini`. Reasoning effort only appears for reasoning models; check the Model dropdown. |
| The answer cites web pages, or the trace shows a `web_search` call | The **Build an agent** template attached **Web search**. Remove it under **Tools** and save a new version. |
| Agent diagnoses diabetes | Re-copy the instructions in [Navigator step 9](#navigator), save a new version, and retest. |
| Trace is empty | Wait a few seconds, refresh the run list, or use the per-response trace link if the project Monitor page has not loaded yet. |
| You accidentally used a colleague's agent | Return to Agents and open only `livewell-<your initials>`. |

## Where next

**Next:** [Lab 1 · Agents & Knowledge — Foundry IQ](lab-01.md) · **Home:** [Workshop map](../../README.md)

Keep your saved agent: Lab 1 adds knowledge to the same Navigator coach.
