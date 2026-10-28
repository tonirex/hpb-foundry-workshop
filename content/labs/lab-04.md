# Lab 4 · Multi-agent & Hosted deploy

**30 min** · **Browser hands-on + facilitator demo / Engineer appendix** · **Level:** L300 · **Rails:** 🟢 DevUI and playground in the browser + watch the deploy · 🔵 local orchestration · **Patterns:** #3 Workflow Orchestration · #9 Collaboration Between Specialists · #10 Governance & Safety

**You are here:** [Lab 0](lab-00.md) → [Lab 1](lab-01.md) → [Lab 2](lab-02.md) → [Lab 3](lab-03.md) ([Fabric step](fabric-step.md)) → **Lab 4** → [Bridge spotlight](bridge-spotlight.md) · [README](../../README.md)

**Your path:** [Navigator](#navigator) · [Builder](#builder) · [Checkpoint](#checkpoint) · [Troubleshooting](#troubleshooting)

## Shared objective

> From playground to production: the same agent behind two doors (portal for people, endpoint for systems), governed by the same policy

Patterns: #3 Workflow Orchestration; #9 Collaboration Between Specialists; #10 Governance & Safety.

## Foundry features covered

- Microsoft Agent Framework sequential and handoff orchestration: Nutrition → Activity → Coach, and Coach → Nutrition → Activity.
- Programme-Insights specialist **`livewell-<INITIALS>-insights`** using the Fabric tool for officer questions.
- Agent versioning and trace comparison across local and hosted runs.
- Hosted deploy with `azd deploy` (code deploy: Foundry builds the container; no Docker needed).
- `rai_config` on the hosted agent so the same RAI policy protects the endpoint.
- Hosted-agent tracing in Foundry (stored in the project's Application Insights).
- RBAC ceiling: participants are Foundry User, so publishing is facilitator-only. The hosted agent runs as its own Entra agent identity with Foundry User on the project.

## Story chapter

[Chapter 4](../narrative/rahim.md#chapter-4--livewell-goes-live-lab-4--multi-agent--hosted-deploy) moves LiveWell Coach from playground behaviour to a hosted endpoint. Rahim's week-planning request flows through Nutrition and Activity specialists before returning a single JSON reply. Mei's programme question goes to a Programme-Insights specialist, showing the same agent family serving citizen and officer seats through governed routes.

## 🟢 Navigator

<a id="navigator"></a>

Steps 1–3 and 7 are hands-on in your browser, with nothing to install. The facilitator shows the rest.

1. **Open the Lab 4 DevUI.**

   **What DevUI is.** [DevUI](https://learn.microsoft.com/agent-framework/integrations/by-component/ui/devui/) is the developer web page that comes with Microsoft Agent Framework. It lists the agents and workflows that a Python app registers. You send one a message, and DevUI shows the run live: the workflow graph, each agent's answer, the raw event stream, tool calls and OpenTelemetry traces. It is a sample for building and testing, not a chat app for residents. Here it runs `demos/lab4-devui.py`, which holds the Builder script's two teams. That app runs as the container app **`ca-lab4-devui-<env>`** in the workshop's Azure Container Apps environment, so you only need a browser. It calls the same Foundry project with its own managed identity.

   1. Open **Lab 4 DevUI (browser, no install)** from the facilitator's values sheet.
   2. Copy **Lab 4 DevUI token** from the same sheet. If either value is missing, ask the facilitator; no terminal is required.
   3. Paste the token into **Enter Authentication Token**, then select **Connect**. DevUI keeps it in this browser only.

   <details>
   <summary>Optional facilitator/Builder lookup when you have additional Azure permissions</summary>

   In the [Azure portal](https://portal.azure.com), search for `ca-lab4-devui-<env>` and copy **Application Url**
   from **Overview**. This needs Reader. Reading the token additionally needs Owner or Contributor; Foundry User
   alone cannot read it. In [Cloud Shell](https://shell.azure.com) (Bash, no storage required) or your signed-in
   Builder terminal, replace the placeholders using the values sheet:

      ```bash
      az containerapp show -n ca-lab4-devui-<env> -g rg-livewell-workshop-<env> --subscription <subscription-id> --query properties.configuration.ingress.fqdn -o tsv
      az containerapp secret show -n ca-lab4-devui-<env> -g rg-livewell-workshop-<env> --subscription <subscription-id> --secret-name devui-auth-token --query value -o tsv
      ```

   `AuthorizationFailed` means your account cannot read the token. Use the values sheet instead; do not request broader permissions for this exercise.

   </details>

   You see two workflows, the same Agent Framework orchestration that the Builder script runs. **LiveWell sequential** is a fixed route (Nutrition → Activity → Coach). In **LiveWell hand-off**, the Coach triages and the agents pass the request on (Coach → Nutrition → Activity). [Under the hood](#under-the-hood) below explains what you see.
2. **Run the sequential team.** Pick **LiveWell sequential** at the top left. Select **+** (top right) to start a fresh session: everyone shares this DevUI, so the session list also shows other people's runs. Select **Configure & Run**, type `user` in **role** and paste this into **contents**. It is Rahim's profile line, which the Builder script also adds, followed by `lab4_week_plan_handoff`. Then select **Run Workflow**.

   <!-- copy:request lab4_week_plan_handoff -->
   ```text
   Resident profile: age band 60-64, lives in Woodlands (North region, hazy today: yes), screening risk High, conditions: elevated blood glucose, about 3100 steps a day.

   Plan my week: what to eat for my glucose, and one indoor morning activity near Woodlands.
   ```
   <!-- /copy -->

   Each box turns green when that agent finishes. A run takes about a minute. In **Execution Timeline**, look for Nutrition, then Activity, then the Coach's evidence JSON with at least one guide id.
3. **Run the hand-off team.** Switch to **LiveWell hand-off**, select **+** and run the same request. Open **Tools** on the right: it lists two hand-off calls, newest at the top. Read from the bottom: `handoff_to_nutrition` (the Coach chose Nutrition), then `handoff_to_activity` (Nutrition passed on to Activity). This shows the model chose the route. **Traces** shows each agent's time and tokens. In this team every message goes to all three agents, so **Execution Timeline** lists the same agent several times (**Run #2**, **Run #3** …). Most of those entries just record the message and take no time. The real work is the entries with an **Output**, and the spans in **Traces** that show token counts (↑ in / ↓ out). Ignore the **Deployment Guide** button; this lab does not use it.

   **Then see where hand-off wins.** The week plan needs both specialists, so both teams took the same path. Now ask for an activity only. In each team, select **+** and run:

   <!-- copy:request lab4_activity_only -->
   ```text
   Resident profile: age band 60-64, lives in Woodlands (North region, hazy today: yes), screening risk High, conditions: elevated blood glucose, about 3100 steps a day.

   Suggest one indoor morning activity near Woodlands for me this week.
   ```
   <!-- /copy -->

   This is the `lab4_activity_only` comparison prompt; keep the same profile context in both teams.

   In the hand-off team, **Tools** lists only `handoff_to_activity` and the run takes about 25 seconds. The sequential team still runs all three agents and takes about a minute. A fixed route is predictable and always ends with the Coach's evidence JSON. A model-chosen route skips agents the request does not need, but it can vary, and it ends with Activity's answer rather than a merged JSON. If the Coach answers by itself and a reply box appears, type what you need and send it: the run carries on from there.
4. The facilitator adds or shows **`livewell-<INITIALS>-insights`**, the Programme-Insights specialist that uses the Fabric tool for programme-level questions, and sends it (`lab4_q_programmes_disengaged`):

   <!-- copy:prompt lab4_q_programmes_disengaged -->
   ```text
   Which programmes have the most disengaged residents enrolled?
   ```
   <!-- /copy -->

   Look for a Fabric-routed aggregate answer grouped by programme and no resident-level detail. The reference
   answer puts **<!--ref:q_programmes_disengaged_enrolled.top_programme-->Healthier SG<!--/ref-->** first
   (<!--ref:q_programmes_disengaged_enrolled.top_disengaged_enrolled-->82<!--/ref--> disengaged residents enrolled). The top programmes
   are close, so ±1 rank is a pass.
5. Watch the hosted deploy path. The facilitator runs `azd deploy livewell-workshop-hosted`: Foundry builds the sequential team from `content/assets/hosted-agent-example/`, then a postdeploy step gives the agent's identity Foundry User on the project and attaches **`livewell-guardrails`** with `rai_config`.
6. Watch the smoke test on the hosted endpoint (`azd ai agent invoke`, or section 7 of the Builder script). The endpoint is read from the values sheet shown on screen and is never written into this page. Then a blocklisted prompt: it must come back blocked.
7. **Chat with the hosted agent yourself.** In Foundry, open **Build → Agents**, search for **`livewell-workshop-hosted`**, and open it. This is a shared agent: chat and inspect only; do not edit it.

   ![Agent list filtered to the hosted workshop agent](screenshots/lab-04/01-find-hosted-agent.png)

   ![Hosted agent page in Foundry](screenshots/lab-04/02-open-hosted-agent.png)

   Open **Version → Show all version history**, then **Details → Active version**. Do not change traffic or select Edit.

   ![Hosted agent version history](screenshots/lab-04/03-hosted-agent-versions.png)

   ![Active hosted-agent version details](screenshots/lab-04/04-active-version-details.png)

   Return to **Playground → New chat** and send (`lab1_prediabetes_eat`):

   <!-- copy:prompt lab1_prediabetes_eat -->
   ```text
   My screening says my glucose is high. What should I eat to manage pre-diabetes?
   ```
   <!-- /copy -->

   Open **Response metrics → Traces**. Compare with Lab 1: the hosted `workflow.run` has one step per agent.
   The answer and trace examples are in [Expected output](#checkpoint) below.
8. **Observe the publishing boundary, without publishing.** Foundry User permits building, testing and calling the hosted agent, but hosted publishing requires Foundry Project Manager or broader rights. The disabled controls and role check are text-only steps. Your workshop account may have broader permissions, so a visible Publish button is not a failure and is not an instruction to use it. The facilitator demonstrates the publishing path:

   ![Facilitator view of the hosted publishing path](screenshots/lab-04/09-project-manager-publish-path.png)

> The Foundry portal **Workflows** item is not used in this workshop because it is retiring on **1 Dec 2026**. Multi-agent orchestration is shown with Microsoft Agent Framework, with specialist agents called through function tools (Builder) and with the A2A tool (Navigator, Lab 3 step 11) instead.

Demo map:

| Moment | What to watch | Why it matters |
|---|---|---|
| DevUI sequential run | Nutrition runs before Activity | Sequential handoff is explicit, not implied. |
| DevUI hand-off run | The **Tools** tab lists `handoff_to_nutrition` then `handoff_to_activity` | In a hand-off team the model picks the route by calling a tool. |
| DevUI activity-only run | Hand-off calls only `handoff_to_activity` and takes about half the time of sequential | A model-chosen route skips agents the request does not need; a fixed route always runs every agent. |
| Programme-Insights | Officer prompt uses Fabric | Specialist routing keeps citizen and officer data paths separate. |
| Hosted deploy | `rai_config` references the RAI policy; the agent identity gets a role | Governance and least privilege follow the agent into production. |
| Smoke test | JSON plus citation returns from endpoint; the blocklisted prompt is blocked | Systems can consume the same governed behaviour. |
| Hosted trace | Tool calls are counted in the trace header | Operations can audit the deployed agent. |

### Under the hood

<details>
<summary><b>Optional: orchestration diagrams, code and DevUI screenshots</b></summary>

**What runs where.** The orchestration is Python: on your laptop or Codespace for Builder, and in the **Lab 4 DevUI** container app for Navigator. The models, tools and guardrails are in the Foundry project. Agent Framework sends each agent's turn to a project model deployment through the Responses API. The knowledge base and `find_activities` are *hosted* MCP tools: Foundry calls them server-side through the project connections, so no tool secrets reach your laptop or the container. The container app signs in to Foundry with its own managed identity, which has only Foundry User on the project, so you need the token and no Azure sign-in. The hosted agent is the same sequential team, packaged as a container that Foundry runs behind its own endpoint.

```mermaid
flowchart LR
  subgraph laptop["Your laptop or Codespace (Builder)"]
    script["lab4_multiagent.py<br/>Agent Framework workflows:<br/>sequential and hand-off"]
  end
  subgraph aca["Azure Container Apps (Navigator)"]
    devui["Lab 4 DevUI: demos/lab4-devui.py<br/>same workflows, token sign-in,<br/>managed identity: Foundry User"]
  end
  subgraph project["Foundry project livewell-workshop"]
    dep["Model deployment gpt-5-mini<br/>guardrail: Microsoft.DefaultV2"]
    kb["Foundry IQ knowledge base<br/>MCP: knowledge_base_retrieve"]
    acts["Activities app<br/>MCP: find_activities, /profile/me"]
    insights["Prompt agent livewell-INITIALS-insights<br/>gpt-4.1-mini · Fabric tool · guardrail: livewell-guardrails"]
    hosted["Hosted agent livewell-workshop-hosted<br/>container: hosted-agent-example/main.py<br/>rai_config: livewell-guardrails"]
    appi["Application Insights<br/>traces"]
  end
  fabric["Fabric IQ<br/>LiveWell ontology"]
  apps["Apps and systems"]
  script -- "sections 4-5" --> dep
  devui --> dep
  dep -- "hosted MCP via<br/>project connections" --> kb
  dep --> acts
  script -- "section 6" --> insights
  insights --> fabric
  script -- "section 7" --> hosted
  apps -- "agents/NAME/endpoint" --> hosted
  hosted --> dep
  hosted -. "spans" .-> appi
```

**Who does what.** Every agent is a plain `Agent` with an instruction block from [`coach-instructions.md`](../prompts/coach-instructions.md) and a tool list; the builders add the routing.

| Agent | Instruction blocks | Tools | Returns | Code |
|---|---|---|---|---|
| Nutrition | `nutrition` | `knowledge_base_retrieve` | A meal tip under 120 words ending with guide ids, e.g. `(lg-05-eating-for-pre-diabetes)` | [`lab4_multiagent.py` L87-91](../assets/lab4_multiagent.py#L87-L91) |
| Activity | `activity` | `knowledge_base_retrieve`, `find_activities` (read-only) | A safe, indoor-on-hazy-days activity plus guide ids | [L92-94](../assets/lab4_multiagent.py#L92-L94) |
| Coach, sequential | `base`, `safety`, `merge` | none | One evidence JSON (strict schema): `advice`, `confidence`, `supporting_guides`, `rationale`, `personalisation_flags` | [L124-129](../assets/lab4_multiagent.py#L124-L129) |
| Coach, hand-off | `base`, `handoff` | `handoff_to_nutrition`, `handoff_to_activity` (added by `HandoffBuilder`) | Nothing: it only routes | [L187-202](../assets/lab4_multiagent.py#L187-L202) |
| Programme-Insights | `insights` | Fabric tool | Programme-level aggregates, no resident rows | [L226-228](../assets/lab4_multiagent.py#L226-L229) (a Foundry prompt agent, so it runs server-side under `livewell-guardrails`) |

**Sequential: the code decides the route.** `SequentialBuilder` wires the participants in a fixed order and passes one shared conversation down the chain. Each agent sees the request and every earlier answer, adds its own, and hands the longer conversation on. The Coach has no tools and a strict JSON schema, so the last message is always the evidence JSON. `output_from="all"` makes the workflow emit every agent's answer, which is how the script prints the route.

```mermaid
sequenceDiagram
  autonumber
  participant W as Workflow (SequentialBuilder)
  participant N as Nutrition
  participant A as Activity
  participant C as Coach
  participant T as Foundry hosted tools
  Note over W: input: profile summary + request
  W->>N: conversation [request]
  N->>T: knowledge_base_retrieve
  N-->>W: meal tip + guide ids
  W->>A: conversation [request, nutrition]
  A->>T: knowledge_base_retrieve, find_activities
  A-->>W: indoor activity + guide ids
  W->>C: conversation [request, nutrition, activity]
  Note over C: no tools, strict JSON schema
  C-->>W: one evidence JSON (the reply)
```

**Hand-off: the model decides the route.** `HandoffBuilder` gives each agent a `handoff_to_<name>` function tool for every target allowed by `add_handoff` (L197-198). An agent hands over by *calling* that tool, and the workflow then makes the target agent active. The instruction block tells the Coach never to answer and to send food-plus-activity requests to Nutrition first. Nutrition runs in **autonomous mode** for one turn: its first reply is the food answer, and on the extra turn it calls `handoff_to_activity` instead of waiting for the resident. The instructions alone were not enough: in about 1 run in 4, `gpt-5-mini` called the hand-off tool and skipped the answer. So the **chat middleware** `answer_first()` (L165-182) removes Nutrition's hand-off tool from its first model call, and the answer has to come first. Activity has no hand-off tool: it is the last stop, and the `termination_condition` (L194-195) stops the run as soon as it has answered. Section 5 still checks the route, because the model chooses it; that is the trade-off for flexibility.

```mermaid
flowchart LR
  req(["Request"]) --> coach["Coach (start)<br/>triage only, never answers"]
  coach -- "handoff_to_nutrition" --> nutrition["Nutrition<br/>answers the food part<br/>(no hand-off tool on turn 1)<br/>autonomous: 1 turn"]
  nutrition -- "handoff_to_activity" --> activity["Activity<br/>answers the activity part<br/>(no hand-off tools)"]
  activity -- "termination_condition:<br/>Activity has answered" --> done(["Done"])
  coach -. "handoff_to_activity<br/>(activity-only questions)" .-> activity
```

**The `text_only` middleware** (L81-84) is the one piece of glue. Each agent's turn contains its own tool calls (MCP calls, hand-off calls), and the next agent must not replay calls it never made. The middleware passes earlier turns on as plain text, keeping who said what (`author_name`).

**The hosted agent is the sequential team in a container.** [`hosted-agent-example/main.py`](../assets/hosted-agent-example/main.py) builds the same three agents from `livewell.json` (L87-100). It puts a small `ResidentProfile` executor first (L58-78), which reads `/profile/me` for the session resident and prepends the profile summary. `SequentialBuilder([...]).build().as_agent()` (L102-104) turns the workflow into one agent, and `ResponsesHostServer` (L108) serves it on the Responses protocol. Foundry builds and runs the container, gives it an Entra agent identity, and applies `rai_config` (`livewell-guardrails`) to every call on its endpoint.

**Watch it run.** [Agent Framework DevUI](https://learn.microsoft.com/agent-framework/integrations/by-component/ui/devui/) shows both workflows. Navigator uses the hosted copy from the values sheet (Navigator steps 1–3). To run it locally instead, use `python demos/lab4-devui.py` (install `requirements-demos.txt` first). It opens `http://127.0.0.1:8090` without a token and prints the request to paste.

1. Pick **LiveWell sequential** or **LiveWell hand-off** at the top left, and select **+** for a fresh session.
2. Select **Configure & Run**, type `user` in **role**, paste the request into **contents**, then select **Run Workflow**.
3. Each box turns green as that agent finishes. **Execution Timeline** shows each agent's answer. On the right, **Events** is the raw stream, **Traces** lists the spans with each agent's time and tokens, and **Tools** lists the local tool calls, which in the hand-off team are `handoff_to_nutrition` then `handoff_to_activity`. The `knowledge_base_retrieve` and `find_activities` calls are hosted MCP tools that Foundry runs server-side, so DevUI does not list them; their results show up as the large input token counts in **Traces**.

`python demos/lab4-devui.py --mermaid` prints the graphs Agent Framework itself derives (`WorkflowViz`). For the hand-off team it draws every possible edge, not just the configured ones. Likewise, the hand-off timeline lists each agent several times: the workflow broadcasts every turn to all participants so they share one conversation, and only the active agent answers.

![DevUI after a sequential run: input, Nutrition, Activity and Coach all completed, with the Coach's evidence JSON in the timeline](screenshots/lab-04/10-devui-sequential.png)

![DevUI after a hand-off run: Coach, Nutrition and Activity completed; the Tools tab shows handoff_to_nutrition then handoff_to_activity](screenshots/lab-04/11-devui-handoff.png)

Further reading: [sequential orchestration](https://learn.microsoft.com/agent-framework/workflows/orchestrations/sequential) and [handoff orchestration](https://learn.microsoft.com/agent-framework/workflows/orchestrations/handoff) in the Agent Framework docs.

</details>

## 🔵 Builder

<a id="builder"></a>

```bash
python content/assets/lab4_multiagent.py
```

Same in bash and PowerShell; your initials and endpoint come from `content/assets/.env` ([Builder setup](../../README.md#-builder-setup)).

Or open `content/assets/lab4_multiagent.py` and run it cell by cell in VS Code or Codespaces. The Agent Framework orchestration runs on your machine and calls the project's model deployments directly, so those local agents run under the deployment's guardrail (the platform default), not `livewell-guardrails`; the Foundry agents in the lab (Programme-Insights and the hosted agent) carry `livewell-guardrails` themselves. Hosted deploy remains facilitator-only.

What the script does per section (the diagrams and line-by-line pointers are in [Under the hood](#under-the-hood)):

1. **Request.** The local specialists have no profile tool, so the script reads the session resident's profile with the same function as Lab 3 (`get_citizen_profile("me")`), turns it into a one-line summary and puts it in front of `lab4_week_plan_handoff`. The summary carries no resident_id. The hosted agent does the same step server-side, from the activities app's `/profile/me`.
2. **Client and tools.** One Agent Framework client for the project, plus the Lab 3 tools: the knowledge-base MCP endpoint and `find_activities` (never `register_interest`).
3. **Specialists.** Nutrition and Activity, each with its instruction block. A small `text_only` middleware passes earlier answers on as plain text.
4. **Sequential team.** Nutrition → Activity → Coach; the Coach merges both answers into the Lab 3 evidence JSON. Prints the trace and checks JSON, a real guide citation, an indoor morning activity and no resident_id.
5. **Handoff team** (skip with `--no-handoff`). The Coach triages and hands off to Nutrition, which hands off to Activity. Checks the route and that both specialists answered.
6. **Programme-Insights** (only with `--fabric`, when the facilitator confirms `FABRIC_BRIDGE=true`). Creates **`livewell-<INITIALS>-insights`** with the Fabric tool and asks `lab4_q_programmes_disengaged`; checks the top programme against the reference answer.
7. **Hosted agent.** Once the facilitator has deployed **`livewell-workshop-hosted`**, sends it the same week-plan prompt on its own endpoint and checks that its guardrail is **`livewell-guardrails`**, the reply is evidence JSON with a real guide, and no resident_id appears. Before the deploy it just says "not deployed yet".
8. **Checkpoint.** Prints your key results under **CHECKPOINT** and saves the run to `content/assets/.runs/lab4-<initials>.json`.

Use `--verbose` for each agent's full answer. Use `--cleanup` to delete only `livewell-<INITIALS>-*` agents (the hosted agent has a protected name and is never deleted). Retype lines are marked `# 👉`.

### How the code works

[Under the hood](#under-the-hood) has the diagrams and the agent table. This is the short map from each script section to the code that does the work.

| Section | Code | What it does |
|---|---|---|
| 1 | [L56-L58](../assets/lab4_multiagent.py#L56-L58), [`profile_summary`](../assets/common/livewell_common.py#L570-L575) | Builds the request: one profile line plus the prompt. |
| 2 | [`af_client`](../assets/common/livewell_common.py#L1120-L1136), [`af_kb_tool` and `af_activities_tool`](../assets/common/livewell_common.py#L1139-L1150) | A `FoundryChatClient` on the project's model deployment, and the two hosted MCP tools from `client.get_mcp_tool`. `allowed_tools` keeps Activity to `find_activities`. |
| 3 | [`text_only` and `team()`](../assets/lab4_multiagent.py#L80-L95) | Agent middleware that strips other agents' tool calls (but keeps the agent's own hand-off result, so a second turn still has input), and a factory for fresh Nutrition and Activity agents. An agent instance belongs to one workflow, so each workflow builds its own. |
| 4 | [`sequential()`](../assets/lab4_multiagent.py#L124-L129), [run and checks](../assets/lab4_multiagent.py#L132-L152) | `SequentialBuilder` in a fixed order. The Coach's strict schema comes from [`af_json_format`](../assets/common/livewell_common.py#L1153-L1156), the same evidence contract as Lab 3. |
| 5 | [`answer_first()` and `handoff()`](../assets/lab4_multiagent.py#L165-L202) | A chat middleware that makes Nutrition answer before it can hand off, then `HandoffBuilder`: who may hand off to whom, the start agent, one autonomous turn for Nutrition and a stop condition. |
| 6 | [L226-L232](../assets/lab4_multiagent.py#L226-L233) | Not Agent Framework: a Foundry prompt agent with the Fabric tool, created and asked exactly as in Lab 3. |
| 7 | [L260-L283](../assets/lab4_multiagent.py#L261-L284) | Finds `livewell-workshop-hosted`, checks its guardrail, and sends it the week-plan prompt. |

Two helpers do the plumbing:

- [`af_run`](../assets/common/livewell_common.py#L1184-L1210) builds a **fresh** workflow, runs it with `await workflow.run(request)` and collects every output message. A 429 or a model error re-runs the whole workflow, because a half-finished hand-off cannot be resumed.
- [`af_steps`](../assets/common/livewell_common.py#L1159-L1174) turns those messages into the printed trace: who spoke (`author_name`), in order, and which tools each speaker called.

`lw.ask` knows that a hosted agent only answers on its own endpoint. For `livewell-workshop-hosted` it uses an OpenAI client for `{project}/agents/<name>/endpoint/protocols/openai` ([`_openai_agent`](../assets/common/livewell_common.py#L404-L406)). For a prompt agent it sends an `agent_reference` instead.

Engineer appendix notes:

- `content/assets/hosted-agent-example/` packages section 4 as a hosted agent: `main.py` (about 100 lines), `livewell.json` (instructions, tools and schema, generated from the same prompt blocks) and a pinned `requirements.txt`. Its [README](../assets/hosted-agent-example/README.md) covers deploy, smoke test, local runs and troubleshooting.
- Hosted agents answer only on their own endpoint, `{project endpoint}/agents/<name>/endpoint/protocols/openai`; the project's Responses endpoint with an `agent_reference` is refused.
- The facilitator reads endpoint values from the values sheet or environment only.
- Participants can still run the Agent Framework orchestration locally without hosted publish rights.
- Any production channel setup is outside the participant checkpoint.
- Keep local orchestration output for comparison with the hosted trace.

## Checkpoint

✅ **Built** or ran a multi-agent orchestration with governed handoffs (Builder script, or the Lab 4 DevUI in the browser).

✅ **Did** a hosted-agent chat and trace in the playground, or the hosted smoke test if you are the facilitator.

✅ **Learned** what changes when an agent moves from playground to endpoint: RBAC, policy attachment, versioning and operational traces.

There is nothing to submit. Try the steps first, then open **Expected output** to compare.

<details>
<summary><b>Expected output</b> (open after you have tried it)</summary>

**What this demonstrates.** One request can be split across specialists, and you choose who decides the route. The sequential team fixes the order and ends with the Coach's merged evidence JSON. The hand-off team chooses its route through `handoff_to_…` tools and ends with Activity's answer; it does **not** promise the same merged JSON. Inspect both specialists' answers and the route. Officer questions go to Programme-Insights with Fabric access. The hosted agent packages the **sequential** team behind its own endpoint, with the workshop guardrail, an agent identity and traces.

**Hosted agent playground.** The food prompt returns evidence JSON with real guide ids. The log stream on the right shows the container's own logs (Agent Framework workflow runner, agent server).

![Hosted agent playground: evidence JSON for the food prompt, with the container log stream](screenshots/lab-04/05-hosted-agent-food-prompt.png)

**Hosted trace.** `workflow.run` contains one `executor.process` span per step: `resident_profile` first, then `nutrition`, `activity` and the coach. Each agent has its own `invoke_agent` and `chat` span. That is the sequential team, seen from production.

<!-- historical-screenshot: screenshots/lab-04/06-hosted-agent-trace.png -->

**DevUI** (Navigator steps 1–3): see the two screenshots at the end of [Under the hood](#under-the-hood).

**Builder.** Look for:

- `trace: nutrition -> activity -> coach`, with `coach tools: none`, then one evidence JSON;
- `trace: coach -> nutrition -> activity`, with `handoff_to_nutrition` and `handoff_to_activity` in the tool lists: the model chose that route;
- with `--fabric`: `livewell-<INITIALS>-insights` calls the Fabric data agent and returns a table by programme, with no resident rows;
- `livewell-workshop-hosted version N (hosted), guardrail: livewell-guardrails`, then a hosted reply with real guide ids;
- PASS on every line.

![lab4_multiagent.py output: sequential and hand-off traces with tools per agent, merged evidence JSON, Programme-Insights ranking and the hosted smoke test, each with PASS lines](screenshots/lab-04/builder-output.png)

</details>

## Troubleshooting

| Symptom | Fix |
|---|---|
| Participant cannot publish | Expected. Hosted publish needs Foundry Project Manager; watch the facilitator demo. |
| DevUI asks for a token again, or a run fails with 401 | Paste the **Lab 4 DevUI token** from the values sheet again (it is kept in this browser only). |
| Token command: `AuthorizationFailed` … `listSecrets/action` | Your account is not Owner or Contributor on the workshop subscription. Use the token from the values sheet, or ask the facilitator. |
| Token command: `ResourceNotFound` or "could not be found" | Cloud Shell is on another subscription or the names are wrong. Copy the whole command from the values sheet; it includes `--subscription`. |
| DevUI takes 20–30 s to open | It scales to zero when idle and is starting up. The facilitator keeps one copy warm on the day (`DEVUI_MIN_REPLICAS=1`). |
| DevUI: "Failed to Load Workflow … not found", **Run Workflow** does nothing, or your earlier runs are gone | DevUI restarted (idle scale-to-zero or a redeploy) and keeps runs in memory only. Open the DevUI link from the values sheet again, pick the team and select **+**. |
| DevUI: a node shows **failed** with "Error: [object Object]" | Select **Show error** to read it. Open **Traces → OTel Spans** and select the failed `chat` span: `gen_ai.input.messages` shows exactly what was sent. A stray space or capital in **role** is handled for you; anything else, tell the facilitator. |
| DevUI: "All N seats of LiveWell … are busy" | Every seat is running someone's request. Wait a minute and run again. |
| DevUI session list shows other people's runs | Expected: the room shares one DevUI. Select **+** for your own session. |
| Hosted playground refuses to chat for a Foundry User account | Watch the facilitator's playground run instead; report the missing access rather than changing project permissions yourself. |
| Section 7 says the hosted agent is not deployed yet | Expected before the facilitator demo; re-run the cell afterwards. |
| Section 7: 424 `session_not_ready` | The hosted agent is cold-starting; wait a minute and re-run. If it persists, the facilitator checks the container log (hosted-agent README). |
| Section 7: guardrail check fails | Facilitator: `python scripts/hosted-postdeploy.py --verify` re-attaches **`livewell-guardrails`** and checks a blocked prompt. |
| Trace shows only one specialist | Re-run the Agent Framework script and check the handoff rule; the week-plan prompt should require both Nutrition and Activity. |
| `Workflow is already running` | One request at a time per workflow; re-run the cell. |
| Programme-Insights calls the knowledge base instead of Fabric | Re-copy the fabric routing block in the specialist instructions and confirm the Fabric tool is attached. |
| Section 6: 400 "Remote MCP server error while enumerating tools … did not return a valid MCP JSON-RPC response" | The Fabric capacity is paused (it is paused overnight). Facilitator: `bash scripts/capacity.sh resume <env>`; re-run after a minute. To carry on without Fabric, prefix the run with `FABRIC_BRIDGE=false`. |
| Endpoint smoke test returns prose | The hosted agent's `livewell.json` is stale: the facilitator runs `python scripts/gen-schemas.py` and redeploys. |
| 429 or quota errors | Wait 30 seconds and re-run, or reduce concurrent participant runs. For the demo, set `LIVEWELL_MODEL=gpt-4.1-mini` to move the team to the tools deployment. |

## Where next

**Previous:** [Lab 3](lab-03.md) / [optional Fabric step](fabric-step.md) · **Next:** [Bridge spotlight](bridge-spotlight.md) · **Home:** [Workshop map](../../README.md)
