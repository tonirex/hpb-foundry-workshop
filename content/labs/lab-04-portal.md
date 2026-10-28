# Lab 4 · Multi-agent & Hosted deploy — portal walkthrough

**5 min · hosted proof at 5:15** · Main page: [Lab 4](lab-04.md) · [Portal track](PORTAL-TRACK.md)

Start with the [shared DevUI comparison](lab-04.md#-navigator) at 1:15: the facilitator's **private expiring link** opens the sequential demo without token entry or deployment. Here, at 5:15, use your workshop-account sign-in to inspect the **already-deployed hosted team** in Foundry. Watch the facilitator if your account cannot open its playground.

1. **Open the prepared agent.** **Build → Agents → search `livewell-workshop-hosted` → Playground**. Use the active version; do not select **Edit**, **Deploy** or **Publish**.
2. **Run a small hosted example.** Start **New chat** and send `lab1_prediabetes_eat`:

   ```text
   My screening says my glucose is high. What should I eat to manage pre-diabetes?
   ```

   Expect evidence JSON with guide ids. This is a hosted smoke check, not the same-input timing comparison from DevUI.
3. **Explain the execution.** Open **Response metrics → Traces → Conversation → Response**. Expand `workflow.run`: look for `resident_profile`, then `nutrition`, `activity` and `coach`. The extra profile step prepares the input; the orchestration is still sequential. Inspect model/tool spans where recorded—token totals alone do not prove a tool call.

**Hosted proof:** the facilitator shows the existing endpoint returning cited JSON and blocking the workshop's blocklisted prompt, live or from captured evidence. The hosted playground and endpoint use **`livewell-guardrails`**. DevUI's direct model calls instead use the deployment's default guardrail.

**Explain before moving on:** what stayed the same (the sequential team), and what changed (host, identity, endpoint and policy attachment)?

<details>
<summary><strong>Screenshots: find the agent and read the hosted trace</strong></summary>

![Agents list filtered to the pre-deployed livewell-workshop-hosted](screenshots/lab-04/01-find-hosted-agent.png)

![Hosted agent page opened in the Foundry portal](screenshots/lab-04/02-open-hosted-agent.png)

![Hosted agent returning evidence JSON and a citation](screenshots/lab-04/05-hosted-agent-food-prompt.png)

![Hosted workflow trace showing the profile step and specialist executors](screenshots/lab-04/06-hosted-agent-trace.png)

Expand `workflow.run`, then the executor and model spans. The container log stream is useful for troubleshooting, but it is not the same view as the structured trace tree.

</details>

<details>
<summary><strong>Optional: inspect versions and publishing permissions</strong></summary>

**Version dropdown → Show all version history**, then **Details → Active version**. Inspect only; do not change traffic.

![Hosted agent version history](screenshots/lab-04/03-hosted-agent-versions.png)

![Active hosted-agent version details](screenshots/lab-04/04-active-version-details.png)

Participants use **Foundry User** to run agents; hosted publishing needs **Foundry Project Manager**. The facilitator can show **Project settings → Access control → My role** and the protected publishing controls.

> 📸 **Screenshot slot** · `screenshots/lab-04/07-disabled-deploy-publish.png` · Deploy or Publish controls disabled for Foundry User

> 📸 **Screenshot slot** · `screenshots/lab-04/08-foundry-user-role.png` · Participant role showing Foundry User

![Facilitator view with publishing controls available](screenshots/lab-04/09-project-manager-publish-path.png)

The presence of a button is not permission to use it. No participant provisioning or publishing is part of Lab 4.

</details>

<details>
<summary><strong>If the portal looks different or a trace is missing</strong></summary>

- **Agent missing / playground refuses access:** check the shared project and agent name with the facilitator; watch their run instead. Do not create a replacement.
- **Trace not ready:** allow a few minutes for ingestion, then reopen it. Use the captured trace above if it remains unavailable; missing telemetry is not proof that a tool was not called.
- **Different labels or role controls:** ask the facilitator. Leave **Edit**, **Deploy** and **Publish** alone even if your account can see them.

</details>
