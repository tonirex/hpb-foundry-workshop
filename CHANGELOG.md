# Changelog

All notable changes to this workshop. One entry per phase PR.

## [Unreleased]

### Sponsor environment (2026-10-04)

- **Sponsor values filled in.** `workshop.yaml` → `environments.sponsor` and `infra/env/sponsor.bicepparam` hold the
  sponsorship subscription, its tenant and the facilitator, the cloud-only work account `hpb.facilitator` (Fabric
  capacity admin). Budget alerts go to the outlook.com mailbox that created the tenant. ASSUMPTIONS.md 10.1–10.12.
- **A new environment provisions in one pass.** ARM preflight rejected `livewell-guardrails` on a brand-new Foundry
  account because the blocklist it names is created in the same deployment. `guardrailLinkBlocklist` keeps the policy
  unlinked until the azd env has `AZURE_AI_ACCOUNT_NAME`; the postprovision hook links it. MCAPS is unchanged, and
  `teardown.sh` clears the value so the next provision starts fresh.
- **Preflight finds a personal-account Owner.** Check 2 looked the caller up by sign-in name. For a personal Microsoft
  account (`name@outlook.com`, tenant UPN `name_outlook.com#EXT#@…`) that matches no one, so an Owner failed the check.
  `scripts/preflight.sh` now looks the caller up by object ID.
- **Cost guardrails on a new subscription.** The "Application Insights Smart Detection" action group that App Insights
  creates in a subscription's first resource group no longer fails the tag check.
- **`azure-ai-projects>=2.6.1`.** An already-installed 2.2.0 satisfied the old `>=2.0.0` floor but lacks
  `agents.download_code` and `ProtocolConfiguration`, so the hosted-agent postdeploy hook and the A2A demo agents failed.
- **One machine, two tenants.** TENANT-BOOTSTRAP Step 2 gives the sponsor tenant its own az and azd profile folders
  (`AZURE_CONFIG_DIR`, `AZD_CONFIG_DIR` with `auth.useAzCliAuth`). A sponsor terminal cannot touch MCAPS, and MCAPS
  terminals keep their sign-in. Step 1 now requires a work or school facilitator: ARM cannot create a Fabric capacity
  for a personal Microsoft account.
- **`fab` without a shared sign-in.** TENANT-BOOTSTRAP Step 4 runs the Fabric deploy on the sponsor az sign-in's tokens
  (`FAB_TOKEN`, `FAB_TOKEN_ONELAKE`, `FAB_TOKEN_AZURE`) instead of `fab auth login`. Step 3 covers named participant
  accounts (`seed-attendees.sh --file attendees.txt`).
- **Attendees can run the Lab 2 judges.** `lab2_govern.py` calls the Foundry account's OpenAI endpoint as the attendee,
  which their project-level Foundry User role does not cover. `attendee_roles` adds Cognitive Services OpenAI User on
  the account. ADMIN-SETUP also notes that attendees need a Fabric licence for the Fabric IQ tool (ASSUMPTIONS.md 10.10).
- **Participants use their own accounts.** Lab 0 (both rails), the Fabric step, the README, the values sheet and both
  decks now say "your own workshop account" instead of `hpb.labNN`; both decks are rebuilt. `check_setup.py` no longer
  warns on every account outside the `hpb.lab` prefix: it warns when the account is not in a workshop tenant (for
  example a work account). `lab_accounts.naming: named` makes the values sheet show `firstname.lastname@<tenant>`.
- **Sign-in cards.** `scripts/tenant/sign-in-cards.py` prints one A4 card per participant (username, temporary
  password, the labs repository from `workshop.repo_url`, first sign-in steps) from `attendees.txt` or the
  lab-accounts CSV into the gitignored `.azure/<env>/`.
- **Device code sign-in in new tenants.** Security defaults in tenants created since July 2026 block
  `az login --use-device-code` (error 530035). TENANT-BOOTSTRAP Step 1 and ADMIN-SETUP T+1 cover turning them off for
  the workshop and back on afterwards (ASSUMPTIONS.md 10.11).
- **Lab 3 spec as a copy-and-paste block.** Navigators copy the profile OpenAPI spec from Lab 3 (both pages) instead of
  opening the spec URL and selecting all. `scripts/sync-openapi-block.py` writes it from the live server; it carries
  the environment's address, the one endpoint allowed in a lab page. `check-content.py` allows it only there and now
  also catches real Container Apps hosts; `connect-tools.py` warns when the block is stale (ASSUMPTIONS.md 10.12).

### Lab 4 DevUI token (2026-10-05)

- **Participants can read the DevUI token themselves.** Lab 4 step 1 now shows the Cloud Shell (or Codespace)
  command `az containerapp secret show … --secret-name devui-auth-token`, and the values sheet prints it with the
  environment's app, resource group and subscription filled in. It works only for Owner or Contributor on the
  subscription, resource group or app (it needs `listSecrets`); Foundry User cannot, so those attendees keep using the
  token on the values sheet. Lab-04 troubleshooting covers `AuthorizationFailed` and a wrong subscription;
  ADMIN-SETUP explains who can read it.
- **Lab 4 step 1 explains DevUI and where it lives.** What Agent Framework DevUI is, that it runs as the container app
  `ca-lab4-devui-<env>`, and how to find its address: the values sheet, the Azure portal (**Overview → Application
  Url**, needs Reader) or `az containerapp show … --query properties.configuration.ingress.fqdn`. The values sheet
  now also lists the subscription.

### Lab 4 DevUI stable ids (2026-10-04)

- **Open DevUI pages survive a restart.** DevUI gave each workflow a random id at start-up, so after an idle
  scale-to-zero or a redeploy a page left open failed with "Failed to Load Workflow … not found".
  `demos/lab4-devui.py` now drops the random suffix (`workflow_in_memory_livewell-sequential` /
  `…-hand-off`); lab-04 troubleshooting covers the symptom. Runs are still in memory only, so they reset on restart.
- **A typo in the role box no longer fails the run.** Foundry rejects any role but an exact `user`, so `user ` (with a
  trailing space) failed the Coach's first call with 400 invalid_payload ("Error: [object Object]" in DevUI).
  `demos/lab4-devui.py` now trims and lowercases the role and treats anything else as `user`. Lab-04 troubleshooting
  shows how to read a failed node from its trace.
- **Traces show only your own run.** DevUI attached a span collector per run and never removed it, so with several
  people on the shared app each Traces panel mixed in everyone's spans, and memory grew all day.
  `demos/lab4-devui.py` now keeps only spans started inside the run and detaches the collector when the run ends.
- **Hand-off runs always end with both answers.** Even with the `handoff` instruction block, Nutrition sometimes
  handed off without writing its food answer, and Activity then handed back to the Coach, so the run ended with
  no answer (2 of 8 hosted runs). A chat middleware (`answer_first()`) now removes Nutrition's hand-off tool from
  its first turn, and Activity has no hand-off tools at all. Same change in `lab4_multiagent.py` section 5 and
  `demos/lab4-devui.py`; 8 of 8 food-plus-activity runs and all activity-only and food-only runs passed. Lab-04
  explains the middleware and the line references moved.

### Builder setup (2026-10-04)

- **Codespace fixed.** The dev container failed in three places before any lab ran. The `python:3.13` image
  is now Debian trixie, where the Docker-in-Docker feature refuses to install and the Azure CLI feature falls back
  to Debian's `az` 2.74 with broken command modules. The post-create also ran `uv pip install --system` as
  `vscode`, which cannot write to the system site-packages. The image is pinned to `python:3.13-bookworm`
  (current `az` from packages.microsoft.com), and post-create installs into a `.venv` that `remoteEnv` and
  `python.defaultInterpreterPath` make active. Tested with the dev container CLI: build, post-create, `az`, `azd`,
  `fab`, `docker`, `make notebooks` and the setup check.
- **`content/assets/check_setup.py`.** Read-only check that Builders run after filling `.env`. It checks Python
  and the packages, `INITIALS`, the endpoint format, the Azure sign-in (and that it is an `hpb.labNN` account),
  the project's tool connections (401/403 means ask for Foundry User) and the two model deployments. Each problem
  prints a FIX line with what to do.
- **One way to set initials.** `.env.sample` has an empty `INITIALS=` and numbered lines for the two values to
  fill. Lab pages, script headers and the Makefile now run `python content/assets/labN_….py`. The old
  `INITIALS=abc python …` lines overrode `.env`, so anyone who copied them shared the `abc` agents. An empty value
  in `.env` no longer crashes the settings loader.
- **Setup docs.** README Builder setup has step-by-step Codespaces and local options, a `.env` table (what, where
  from) and a check-output table. Lab 0 Builder has the four steps. ADMIN-SETUP T-7 adds GitHub repository access
  for Builders (the repository is private), and T-1 adds the participant setup check. `ipykernel` was added to
  `requirements.txt` so **Run Cell** works without an install prompt.

### Lab 4 in the browser (2026-10-03)

- **Hosted DevUI.** The `lab4-devui` service is optional and defaults to on (`LAB4_DEVUI`). `demos/lab4-devui.py`
  runs as a Container App on the workshop environment (`demos/devui-aca/`, `infra/modules/devui.bicep`,
  `scripts/stage-devui.py`). It has its own managed identity with Foundry User, a bearer token on the values sheet,
  DevUI developer mode (so the Events/Traces/Tools panel shows), a cap on runs in flight (`DEVUI_SEATS`, default 8)
  and scale to zero. Navigators run the sequential and hand-off teams in the browser, with no install and no
  Codespace. On MCAPS, 6 concurrent runs of each workflow passed. The image also carries the 11 LiveWell guides:
  without them the Coach's `supporting_guides` enum was empty and it always returned `[]` (`_guides()` now refuses
  an empty list).
- **Fresh workflow per DevUI run.** A workflow object keeps its agents' chat history and the hand-off conversation
  between runs. With the old seat pool, a second hand-off run on the same copy ended in about 1 s with no answer
  (Activity had "already replied"), and a sequential run carried the previous person's chat. Each run now builds a
  new workflow; `DEVUI_SEATS` only caps runs in flight.
- **Answering the triage Coach in DevUI works.** When the Coach asks back instead of handing off, DevUI shows a reply
  box. The reply failed twice: DevUI looked up the checkpoint under the display name, but the workflow had saved it
  under its build-time name, and the box sends text where the hand-off expects chat messages. The workflows are now
  named at build time and text replies are wrapped as a user message.
- **Lab 4 step 3 shows where hand-off wins.** The week plan needs both specialists, so both teams took the same
  path. Navigators now also run an activity-only request on both teams: hand-off calls only `handoff_to_activity`
  (about 25 s on MCAPS) while sequential runs all three agents (about 55 s). New demo-map row.
- **Specialists copy guide ids from their search results.** The Nutrition and Activity blocks in
  `coach-instructions.md` now say to copy ids exactly from the guide search results and never invent or shorten
  one. Before, the Activity specialist made up ids such as `lg-07-physical-activity` in 4 of 6 runs; after, 0 of
  8, and 8 of 8 hand-off runs still ended with an Activity answer. A stricter "always search the guides first"
  rule was dropped because it made some hand-off runs end without the food answer.
- **Navigators chat with the hosted agent.** A Foundry User-only identity can call `livewell-workshop-hosted`
  (ASSUMPTIONS 4.20, review item L4-3). Lab 4 and the portal walkthrough now have Navigators chat with it
  themselves; deploy and publish stay facilitator-only.
- **Paused-Fabric pre-check.** `scripts/select-params.py` stops provisioning early when the Fabric capacity is paused.
  ARM cannot update a paused capacity, so the provision would otherwise fail at the end.
- `lw.credential()` uses a user-assigned managed identity when `AZURE_CLIENT_ID` is set.

### Lab review fixes (2026-10-03)

- **Lab review report** in `demos/LAB-REVIEW-2026-10-03.md`: flow, consistency and objectives on both rails after the
  model switch (21 findings; section 9 tracks the fixes).
- **DevUI hand-off fix**: `demos/lab4-devui.py` keeps each agent's own hand-off result, as the Builder script does;
  both DevUI workflows pass on `gpt-5-mini` and the two DevUI screenshots are retaken.
- **Text fixes**: Lab 2 says seven prompts, starts a new chat per prompt and has a fallback path for
  `livewell-demo-guarded`. Lab 3 sends the signup prompt in a new chat. The Fabric step checks for `gpt-4.1-mini` and
  says version 4. The Lab 3 answer key gains `lab3_programme_fit`, and Lab 1 marks Pattern #1 as optional. The Lab 1
  supplement contract is aligned. The plan lists all seven Lab 2 prompts. Rahim's chapter 2 matches the guardrail
  outcomes. Lab 4 labels its smoke test and clarifies tracing. The bridge spotlight falls back to `--replay` before
  slides.

### Sponsorship subscription models (`dry-run-navigator-fixes`)

- **Two models, no model-router.** The delivery sponsorship subscription (quota Tier 0) offers no `model-router`. Labs
  0–2, the Lab 3 specialists, memory, KB planning and Lab 4 use `gpt-5-mini` at reasoning effort Low; any agent with
  OpenAPI, A2A, function or Fabric tools (the Lab 3 coach on, the Lab 4 insights agent) and the judges use
  `gpt-4.1-mini`; embeddings use `text-embedding-3-small`. Caps 400K / 200K / 100K for 6 participants
  (ASSUMPTIONS.md 9.1).
- **Lab 0 rewritten** around model, instructions, reasoning effort and a refusal trace; `demos/router-picks.py` and the
  router screenshots are removed. Lab 3 step 1 switches the coach to `gpt-4.1-mini` before adding tools.
- **Coach `tools` block re-ordered** (profile → knowledge base always → specialists → activities → reply): 16/16 on
  the Lab 3 bench.
- **Lab 4 `handoff` block for `gpt-5-mini`**: Nutrition answers in one turn and hands off in the next, and Activity
  never hands back (the hand-off had skipped Nutrition's answer). Scripts: `build-kb.py` recreates a knowledge source
  whose embedding model changed, `create-demo-agents.py` recreates a stale memory store, the guardrail-matrix judge
  labels rows its own filter blocked as "judge filtered", and the smoke A2A check tries 3 times. Re-validated on MCAPS
  (ASSUMPTIONS.md 9.2).
- **`fabric` block programme-fit steps**: `gpt-4.1-mini` skipped the profile and guessed Rahim's age band in 3 of 4
  runs, so the rule is now ordered steps (profile alone first, then one Fabric question with the profile's
  `age_band`): 4 of 4. New troubleshooting row in `fabric-step.md`.
- **Lab 4 `text_only` middleware keeps the agent's own hand-off result**, so an agent given a second turn in the
  hand-off workflow no longer sends an empty request ("Messages are required for chat completions").
- **Screenshots retaken and Builder runs re-recorded.** The portal's Create-an-agent dialog lost its model picker, so
  Lab 0 picks `gpt-5-mini` in the playground (new slot 06b: Reasoning Low, no tools). Lab 0 06, 06b, 10 and Lab 3
  01, 07 retaken; Builder Labs 1–4 re-recorded in `demos/evidence/2026-10-03/` and the lab-page crops refreshed.
- **Dry-run fixes** (`demos/DRY-RUN-2026-10-02.md`): Web search removal, Foundry IQ explainer,
  Text format steps, guardrail reset, injected flyer, version numbers, OpenAPI vs MCP and workshop shortcuts, and
  pre-built A2A specialists.

### Lab-flow deck and Day 1 deck refresh (`deck-lab-flow`)

- **New participant deck.** `deck/LiveWell-Lab-Flow.pptx` (18 slides, built by `deck/build_lab_flow.py`) explains the
  flow of the labs and the learning objectives: the journey, the layer staircase, the two seats, how a lab page works,
  one slide per lab with a screenshot of success, the Lab 2 guardrail ladder, the Lab 4 orchestration lanes, an
  objectives table, the ten patterns by lab, resources and takeaways. Objectives, prompts and minutes are read from the
  lab pages, `test-prompts.json` and `workshop.yaml`.
- **Day 1 deck refresh.** Module cards, agenda, human thread and architecture now match the current labs (router pick,
  clinician route, default-vs-custom guardrail ladder, `livewell_profile`, approval before `register_interest`, the
  Fabric step's aggregate questions, DevUI sequential and hand-off). The guardrail slide is the seven-prompt ladder
  with block vs annotate, evaluators and red team; the Fabric step card no longer carries the Bridge objective; the
  "Where we left off" chevrons no longer overflow; checkpoint notes say nothing is submitted.
### Checkpoints show the expected output (`checkpoint-expected-output`)

There was no checkpoint form to paste into. Participants now submit nothing and compare with a hidden example
instead. Details in ASSUMPTIONS 7.1-7.4.

- **Expected output blocks.** Every Checkpoint (Labs 0-4, Lab 1 portal, Fabric step, Bridge spotlight) ends with a
  collapsed block: what the step demonstrates, portal screenshots with what to look for, and the Builder script's
  output from a fresh recording (`content/labs/screenshots/*/builder-output*.png`).
- **How the code works.** Each Builder section walks through its script with links to the line ranges: the tools,
  `create_agent`, the `ask` loop and approvals, specialists as tools, the Agent Framework runs and the Fabric checks.
- **Bridge Builder.** Rewritten around `demos/fabric-steps.py` (live, `--replay`, `fit`, `--save-sample`) with a
  code walkthrough; the old command used the protected `demo` prefix and never asked the Bridge question.
- **Fixes.** Lab 4 step 1 profile wording, the Bridge traversal, Lab 3 look-for flags, and the scripts'
  `CHECKPOINT` heading and comments. Answer keys are labelled as facilitator reference (README, SPEC).

### Builder evidence and Fabric F4 (`builder-evidence`)

Evidence that the Builder-rail scripts work, and the Bridge captured live. Details in ASSUMPTIONS 3b.7, 4.16, 4.23
and 6.8.

- **Fabric F4.** F2 was throttled (429 `RequestBlocked`) after a day of testing; F4 cleared it in about 4 minutes.
  The SKU is now a parameter: `FABRIC_SKU` (default F2) in `infra/env/*.bicepparam`, `azd env set FABRIC_SKU F4`,
  and `scripts/capacity.sh scale F2|F4 <env>` to change it in seconds. `cost-guardrails.sh` prices F2 and F4 and
  warns when the capacity and `FABRIC_SKU` disagree; `preflight.sh` checks the CU quota for the chosen SKU.
  ADMIN-SETUP covers the quota, the 429 fix and the cost (F4 ≈ US$0.76/h, F2 ≈ US$0.36/h).
- **Bridge captured live.** `fabric-steps.py bridge` ran on F4 (123 s, one 3-hop GQL query, 5/5 reference counts).
  The run is committed as `demos/samples/fabric-steps-q_dropped_attended_heldin.json`, so `--replay` works on the
  day with no capacity, and screenshots bridge/01-05 are filled.
- **Terminal evidence recorder.** `demos/record-terminal.py NAME -- <command>` records a script's output with real
  timings (asciinema `.cast`), a full-page PNG and a replay video, as WebM and, when ffmpeg is installed, as MP4
  for PowerPoint and Teams (`demos/videos/`, git-ignored). Local paths are
  redacted, and `--render` re-redacts and re-renders an existing cast. The 2026-10-01 set (Lab 0 router picks,
  Builder Labs 1-4, the Bridge replay) is indexed in `demos/evidence/2026-10-01/README.md`.
- **Lab 3 specialists.** The coach's `tools` instructions told it both to search the knowledge base before food or
  activity advice and to ask the specialists for plans, so it sometimes planned from the knowledge base itself and
  `lab3_specialists` failed. The rule now says plans come from the specialists when the coach has them (ask both,
  keep their guide ids) and from the knowledge base otherwise. A/B probe: both specialists consulted 9/9 vs 7/9.
- **Validator.** `validate-builder-rail.py` deletes stale `livewell-test-*` agents and memory stores from an earlier
  interrupted run before it starts, so the leftover check only fails on this run's leftovers.
- **Trace screenshots.** The portal's trace dialog sometimes opens with the agent span collapsed or before every span
  has arrived, and a span pattern such as `fabric` also matched the agent row (`livewell-demo-fabric`), so lab-03/11,
  lab-03/20, lab-03/23 and bridge/02 showed the agent's instructions instead of the tool call. `portal.trace_expand`
  opens the tree, `trace_span` skips agent and conversation rows, and `scenes.Run.trace` reopens a partial trace.
  Lab 3 steps 19-21 now say the coach asks before `register_interest`, so the approval card follows Rahim's "yes"
  (ASSUMPTIONS 5.21).
- **Red-team memory pollution.** Lab 3's prediabetes prompt was blocked in the portal (self-harm, medium) but passed
  through the SDK. The cause: the cloud red team runs as the facilitator, so `livewell-demo-tools`' memory tool saved
  its attack summaries (starvation diets, self-harm, poisoning) into the facilitator's memory scope, and memory search
  fed them back into ordinary chats. The consent line that `lw.ask` adds hid it from the validators. The scope was
  cleared, and the prompt now passes 6/6 without the consent line. New `scripts/reset-demo-memory.py` lists your
  scope, flags residue and `--reset`s it; `red-team-cloud.py` clears it after each run (`--keep-memory` skips), and
  `smoke-test.py` fails on residue. Lab 2 uses it as a second red-team teaching point (ASSUMPTIONS 5.22).

### Navigator feedback (`navigator-feedback`)

Facilitator feedback on the 🟢 Navigator rail, so each lab has something concrete to show on the day. Details and
live results are in ASSUMPTIONS 6.1–6.8.

- **Guardrails (all labs).** The model deployments now carry `Microsoft.DefaultV2` (`deployment_policy` in
  `content/config/guardrails.yaml`, `infra/modules/foundry.bicep`). The custom `livewell-guardrails` policy is
  attached per agent instead (Lab 2 v2, the guarded demo agents, the hosted agent). Before, every agent inherited the
  custom policy from its deployment, so Lab 2's v1 blocked the red flags too and the custom guardrail showed no
  benefit. `scripts/apply-guardrail.py --check` reports a per-deployment policy as drift.
- **Lab 0: which model did the router pick?** The agent trace only says `model-router`. The lab now shows the
  deployment Playground (model name under each answer) and the Monitor tab, and `demos/router-picks.py` prints the
  chosen model per prompt from `response.model` and the preview `model_selection_details`. Slot 00/12 shows the
  playground.
- **Lab 2: guardrails, evaluations, red teaming.** The portal track runs a red-flag ladder on v1 (default policy)
  and v2 (custom), explains **block vs annotate** (the severity threshold and the blocklist decide; annotate records
  the category and lets the answer through), and shows the custom policy's deliberate over-block (dose reminder).
  New prompts `lab2_skip_meals` and `lab2_benign_dose_reminder` (test-prompts, answer key).
  Facilitator demos: `demos/guardrail-matrix.py` (red-flag and benign prompts × model choice × guardrail, printed
  locally or as a portal evaluation with `--cloud`), and `scripts/red-team-cloud.py`, the cloud AI Red Teaming Agent
  against named agent versions, including the agentic risk categories. Its results open under **Evaluations → Red
  team**; `--report <eval id>` reprints the table and flags scored "successes" whose judge reason says the agent
  refused. Lab 2 judges use code metrics for red-flag rows (`lab2_govern.py`).
- **Lab 3 Fabric step: Programme fit.** A citizen reason to call Fabric: Rahim asks which programme people his age
  stick with (`lab3_programme_fit`, narrative ch3.6). The coach asks Fabric one age-band question
  (`q_programme_fit`), recommends the lowest drop-out programme he is not already in (Diabetes Prevention), finds
  its intake session through MCP (ACT047, new `programme` field) and asks before `register_interest`. The ontology
  gains a `droppedOut` edge (`scripts/r360.py`, `30-ontology.py`, blueprint); the data agent and the coach both
  apply the "fewer than 5" rule. The data agent is told to run two queries and join them (one combined query
  returned enrolled = dropped). `validate-narrative.py` and `check-content.py` allow exactly this one citizen
  cohort question. `lab3_tools.py --fabric` and the portal Fabric step (slots 03/19–03/21) follow it.
- **Lab 4: what is happening.** `lab-04.md` adds a component diagram, a who-does-what table linked to the Agent
  Framework code in `lab4_multiagent.py` and `hosted-agent-example/main.py`, and sequence and hand-off diagrams.
  `demos/lab4-devui.py` serves the same two workflows in Agent Framework DevUI (beta, `requirements-demos.txt`) for
  a live graph and timeline; slots 04/10 and 04/11.
- **Bridge spotlight (the "Lab 5" in the feedback).** Step 5 says what to observe in the Fabric IQ trace, and a new
  step 6 shows what the trace cannot: `demos/fabric-steps.py` reads the data agent's own run steps (rewrite,
  generated GQL, rows) and renders one HTML page with the ontology path, a timeline, the queries, a check against
  `reference-answers.json` and talking points. `--replay` works with the capacity paused, from `demos/runs/` or a
  sample in `demos/samples/` (`--save-sample`; see Builder evidence above for the committed one). Five Bridge
  screenshot slots; `record-demos.py --lab bridge` records the step to
  `demos/videos/bridge-<date>.webm` (git-ignored).
- Demo kit: `scenes.py` adds the ladder, programme-fit and Bridge scenes and parses slots from
  `bridge-spotlight.md` too; renamed Lab 2 and Lab 3 screenshots follow the new step numbers.
  `capture-screenshots.py --link` writes LF and only touches pages it changes.
- Docs: ADMIN-SETUP (captures, videos, backups, script reference), DRY-RUN-TEMPLATE, question bank, data-agent and
  coach instructions, workshop.yaml region note for cloud red teaming, versions.md (DevUI), NOTICE and SPEC
  (5 relationships).

### Phase 5: Proof & demo kit (`phase-5-proof`)

- `scripts/smoke-test.py` (SPEC §11.2): temporary `livewell-smoke-*` agents built from the demo-agent definitions
  check the MCP server, knowledge base citation, guardrail, ≥ 2 tools, Fabric for Mei and not for Rahim, and the
  hosted agent, then print the cost since provision. `--demo-agents` tests the facilitator agents at T-0. It exits 1
  on a failure or a leftover agent. Verified 7/7 in `mcaps`.
- `demos/create-demo-agents.py`: the five portal-track reference agents `livewell-demo-{lab0,kb,guarded,tools,fabric}`
  from the same instruction blocks, schemas, tools and guardrail as the lab pages. All tools run server-side (the
  profile tool is an OpenAPI tool), so they work in the playground. Re-runs are idempotent (definition hash in the
  version metadata). It also registers the `livewell-eval` dataset that the Lab 2 portal evaluation picks.
  `livewell_common.profile_openapi_tool()` is shared with the smoke test.
- `demos/portal.py`, `demos/scenes.py`, `demos/capture-screenshots.py`, `demos/record-demos.py`: Playwright (Edge)
  kit for the new Foundry portal. It covers a one-time sign-in with a kept profile, 11 scenes that fill the Navigator
  screenshot slots, `--list-missing` and `--link`, and one captioned WebM per lab. Scenes never save; IDs, endpoints
  and e-mails are rewritten and the account button is masked. `requirements-demos.txt` (Playwright ≥ 1.47).
- `content/labs/screenshots/`: Navigator screenshots for Labs 0–4, linked into the portal lab pages. Five slots stay
  manual (two lab-account sign-in shots, two Foundry User views of the hosted agent, and the v1/v2 evaluation
  comparison).
- `demos/DRY-RUN-TEMPLATE.md`: dry-run report (gates, timed run of show per rail, open questions from
  ASSUMPTIONS, findings with severity, cost and cleanup, sign-off) that Phase 6 works from.
- The values sheet refreshes by itself: the `postprovision` hook (after the guardrail), a new project `postdeploy`
  hook, `scripts/fabric/deploy.sh` and `scripts/connect-tools.py` all run `render-values.py`. The sheet adds the
  profile OpenAPI URL (Lab 3) and the hosted agent name (Lab 4).
- Lab 1 portal: step 3 names the Connect to Foundry IQ dialog fields, and step 4 opens the knowledge base page
  directly (it opens on its settings).
- Lab 2 portal: the injected flyer is pasted below the prompt instead of attached. The playground accepts only
  image and PDF attachments, and a rejected `.md` file blocks Send. Step 13 opens the blocked run from the agent's
  Traces tab (a guardrail-blocked chat turn has no metrics row or Traces button). Step 15 follows the live
  evaluation wizard: row Version picker, `livewell-eval` dataset, Context set to Not available, and seven evaluators
  instead of the 22 suggested.
- Lab 3: the profile tool is `livewell_profile` (the portal rejects dashes in OpenAPI tool names) in the lab pages,
  answer keys, `connect-tools.py` and the demo agents. The portal OpenAPI step pastes the schema from the values
  sheet (Tools → Add → Add tools → Custom → OpenAPI tool). The MCP server and the Fabric IQ tool are added from the
  **Configured** tab of Select a tool (project connections), and the MCP approval rule is edited from the tool
  row's Actions → Configure. The Fabric step picks the Resident360 ontology agent in the OneLake Catalog. The
  register-interest prompt adds a "yes" follow-up because the coach asks before it signs Mei up. The approval step
  now reads **Approve → Approve once**, because Approve has become a split button.
- `scripts/check-content.py` skips the gitignored `demos/.playwright` (browser profile) and `demos/runs`.
- Docs: ADMIN-SETUP (demo-agent step at T-3, screenshot and video capture at T-1, smoke test at T-0, backups,
  script reference), run of show T-0 checklist, PORTAL-TRACK slot rules, versions.md (Playwright 1.63.0, portal
  surfaces), ASSUMPTIONS 5.x.

### Phase 4: Builder-rail code (`phase-4-labs`)

- `content/assets/common/livewell_common.py`: shared helper for every lab. It covers settings from `.env` and the
  azd env, `livewell-<INITIALS>-<role>` naming with protected prefixes, strict schemas with a guide-id enum, retries
  on transient errors, tools (KB, activities MCP with approvals, Fabric IQ, profile function, memory), `ask()` with
  function calls, approvals and guardrail blocks, hosted-agent routing, Lab 2 evaluation helpers, Agent Framework
  helpers, recorded checks, and `cleanup()`.
- Lab scripts in `# %%` cell form with `# 👉` retype lines, `--verbose` and `--cleanup`:
  `lab1_knowledge.py` (`--intake`), `lab2_govern.py` (`--eval-all`, `--no-eval`, `--upload`), `lab3_tools.py`
  (`--fabric`, `--no-memory`) and `lab4_multiagent.py` (`--fabric`, `--no-handoff`; sequential and handoff Agent
  Framework teams, Fabric insights agent, hosted-agent smoke test).
- Guardrail: `content/config/guardrails.yaml` drives the Bicep blocklist, the policy and the deployment
  attachments; `scripts/apply-guardrail.py` (postprovision) syncs the blocklist items and repairs drift (`--check`).
- `scripts/build-kb.py`: Foundry IQ knowledge base `livewell-guides-kb` (Blob or OneLake source) plus its MCP
  connection and a retrieval check.
- `content/assets/mcp-activities/`: FastMCP activities server (`find_activities`, `register_interest`) plus the
  session-scoped profile REST/OpenAPI endpoint, deployed with `azd deploy mcp-activities`.
- `scripts/connect-tools.py`: activities MCP and Fabric IQ connections, with end-to-end checks.
- `content/assets/hosted-agent-example/`: Agent Framework hosted agent `livewell-workshop-hosted` (code deploy), and
  `scripts/hosted-postdeploy.py` (azd postdeploy hook). The hook grants the agent identity Foundry User and attaches
  `livewell-guardrails`; `--check` and `--verify` are available.
- `content/eval/livewell-eval.jsonl` (30 rows) and the custom evaluator `advice_matches_conditions.py`.
- `scripts/red-team.py` and `requirements-redteam.txt`: facilitator AI Red Teaming Agent scan (lite ≈ US$0.85,
  full ≈ US$8), with the cost printed before the scan starts.
- `scripts/validate-builder-rail.py`: runs Labs 1–4 as `INITIALS=test`, checks the SPEC signals and leftovers, and
  writes a report.
- `scripts/gen-schemas.py` and `content/config/schemas/`: paste-ready Navigator schemas plus the hosted agent's
  `livewell.json`.
- Makefile targets `notebooks`, `validate-rail` and `clean-agents`. `validate-narrative.py` now reads the
  coach-routing row from the Lab 3 run.
- Models: `gpt-5.4-mini` deployment (200K TPM) for the Lab 3 coach with memory. Chat TPM caps go from 100K to 400K.
  RBAC is added for memory (the project identity) and the hosted agent identity.
- Storage: MCAPS policy opt-out tag, a resource-instance rule for Search, and `storageNetworkDefaultAction`
  (`Allow` by default: Entra-only public access, so Lab 2 and the red team can publish evaluation runs; `Deny`
  admits only Search and trusted services).
- Prompts: the `nutrition` and `activity` specialist blocks now end every answer with the guide ids used (moved
  from the `handoff` block), so the Lab 4 sequential Coach can cite them; `livewell.json` regenerated.
- Docs: lab pages 1–4 (Builder sections, JSON schema instead of JSON object, troubleshooting), ADMIN-SETUP
  (T-3 steps 4–7, the T-1 rail validation and red team, cost and RBAC rows, script reference), versions.md,
  ASSUMPTIONS 4.1–4.23.

### Phase 3b: narrative gate (`phase-3b-narrative-gate`)

- `scripts/validate-narrative.py` with three layers (`--layers static,data,live` or `all`), `--fill`, `--check`,
  `--runs`, `--pause`, `--questions`. Static: beats, seats, sources, prompts, glossary spelling, no `resident_id`,
  numbers only through `{{ref:...}}`, filled values current. Data: rebuilds Resident 360 with `r360.py`, checks
  joins, glossary rules, Rahim across citizens.json, intake documents and story, and writes
  `content/fabric/reference-answers.json`. Live: a graph check (canonical GQL on the graph model), then three
  data-agent calls per fabric question with latency, judged against the reference; writes
  `demos/NARRATIVE-VALIDATION-<date>.md` with every raw answer.
- `--fill` wrote 22 reference values into `content/narrative/rahim.md`, `bridge-spotlight.md`, `fabric-step.md` and
  `lab-04.md` as `<!--ref:key-->value<!--/ref-->` markers; `check-content.py` accepts them.
- Ontology: gold aggregates `Region.disengaged_residents`, `Region.disengaged_share_pct` and
  `Programme.disengaged_enrolled` (built by `r360.py`), so the two strict questions read one row per group.
- Data agent: `40-data-agent.py` deploys and publishes **data source instructions** (graph schema, flag conditions,
  GQL shapes, the 200-row query limit) alongside the agent instructions. Example queries are not supported for
  ontology sources.
- `question-bank.md`: canonical GQL per question (traversal and aggregate), used by the graph check and the bridge
  spotlight.
- `content/assets/Makefile` (`make validate`, `validate-live`, `fill`) and the manual CI workflow
  `.github/workflows/validate-narrative.yml`.
- ADMIN-SETUP: the proof step, F2 throttling and 200-row troubleshooting rows, and the script reference.

### Phase 3: minimal Resident 360 on Fabric (`phase-3-fabric`)

- `scripts/fabric/deploy.sh [env] [--from NN] [--only NN] [--skip-upload]` runs six idempotent steps with
  per-step timings: `10-workspace.sh`, `20-lakehouse-load.sh`, `30-ontology.py`, `35-graph-refresh.py`,
  `40-data-agent.py` and `90-write-env.py`. The shared helpers live in `fabriclib.py` and `notebook.py`.
- `content/assets/load_resident360.ipynb` imports `scripts/r360.py` from OneLake and writes the six Delta tables.
  It exports summary and CSV files for the local checks.
- The ontology `resident_ontology` (4 entity types, 4 relationship types) is rendered from
  `content/fabric/ontology.blueprint.yaml`. The graph refresh runs through the job API, and a GQL check confirms
  the instance counts.
- The data agent `Resident360 Ontology Agent` is created, its entity types are selected, and it is published.
  `scripts/fabric/ask.py` queries it over MCP.
- `scripts/gen-citizens.py --from-onelake` rebuilds `citizens.json` from the lakehouse export.
- Instructions: counting rules. Tenant setting renamed ("Users can create Ontology (preview) items").
  `teardown.sh` clears the new `FABRIC_*` keys.
- Verified in the `mcaps` environment: the table counts, the graph instances and the data agent answer all match
  the local reference. A full run takes 17–20 minutes on F2. `35-graph-refresh.py` reuses the refresh that the
  ontology update starts instead of running a second one.

### Phase 2: infrastructure and admin scripts (`phase-2-infra`)

- Bicep (`infra/`): Foundry account and project (model-router, gpt-4.1-mini, text-embedding-3-large;
  100K TPM caps), Azure AI Search Basic, storage, ACR, Log Analytics and App Insights, Container Apps
  environment with the MCP placeholder app (min replicas 0), Fabric F2 capacity (opt-out with
  `FABRIC_BRIDGE=false`), US$300 budget with alerts at 50% and 100%, facilitator and project RBAC.
- Per-environment parameters (`infra/env/mcaps.bicepparam`, `sponsor.bicepparam`) selected by
  `scripts/select-params.py`; `SEARCH_LOCATION` override for regional Search capacity shortages.
- Admin scripts: `preflight.sh` (8 checks), `provision.sh` (preflight, what-if, `azd provision`),
  `cost-guardrails.sh`, `capacity.sh`, `teardown.sh`, `seed-attendees.sh`, `tenant/create-lab-users.sh`,
  `render-values.py`, plus the `lib/` helpers (`common.sh`, `azrest.py`, `wsconfig.py`).
- Admin docs: `content/admin/ADMIN-SETUP.md`, `TENANT-BOOTSTRAP.md`, troubleshooting table.
- Verified in the `mcaps` environment: provision, guardrails, teardown and provision from empty.

### Phase 1: content and data (`phase-1-content`)

- Workshop config (`content/config/workshop.yaml`) and glossary (`content/config/glossary.yaml`).
- Resident 360 data: 7 vendored kit files (pinned at `3ce11e4`), Rahim overlay, and generated
  `activity_daily`, `health_screening` and `air_quality_snapshot` (`scripts/gen-activity.py`).
- Local gold build and reference answers (`scripts/r360.py`); 12 synthetic citizens
  (`scripts/gen-citizens.py`); 46 activities; injected flyer; Rahim intake documents.
- 11 LiveWell guides (markdown and PDF) for Foundry IQ.
- Lab pages 0–4, Fabric step and bridge spotlight, both rails; Portal Track.
- Prompt bank (`content/prompts/test-prompts.json`), coach instruction blocks, answer keys.
- Fabric ontology blueprint, data-agent instructions and question bank (Mei's 3 questions).
- Rahim narrative (6 chapters) with beat tags.
- Deck builder and 16:9 deck.
- README, facilitator run of show, ASSUMPTIONS, versions, NOTICE, devcontainer, `scripts/check-content.py`.

### Bootstrap

- SPEC.md, CODING-AGENT-PROMPTS.md, AGENTS.md, LICENSE, .gitignore.
