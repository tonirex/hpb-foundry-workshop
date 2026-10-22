# ADMIN-SETUP — facilitator runbook (T-10 → T+1)

Everything a facilitator runs to stand up, operate and tear down one LiveWell Coach workshop environment.
The resources, names and costs come from [SPEC.md](../../SPEC.md) §8, §12.1 and §13. The one config file is
[workshop.yaml](../config/workshop.yaml). The sponsored-tenant variant is in [TENANT-BOOTSTRAP.md](TENANT-BOOTSTRAP.md).

- [Who needs what](#who-needs-what)
- [Timeline](#timeline)
- [Cost table](#cost-table)
- [What not to leave running](#what-not-to-leave-running)
- [RBAC model and gotchas](#rbac-model-and-gotchas)
- [Backup plans](#backup-plans)
- [Troubleshooting provisioning](#troubleshooting-provisioning)
- [Script reference](#script-reference)

## Who needs what

| Who | Needs | Why |
|---|---|---|
| Facilitator (runs the scripts) | **Owner** on the subscription (or Contributor + User Access Administrator) | The template creates role assignments |
| Facilitator | **Fabric Administrator** (Entra role) and a Fabric licence (Free is enough; sign in once at app.fabric.microsoft.com) | Tenant settings, capacity admin, `scripts/fabric/deploy.sh` |
| Facilitator | Listed in `fabricAdminMembers` in `infra/env/<env>.bicepparam` | Capacity admin in the Fabric admin portal |
| Whoever creates lab accounts | **User Administrator** (Privileged Role Administrator for the break-glass role) | [create-lab-users.sh](../../scripts/tenant/create-lab-users.sh) |
| Attendee | Nothing up front: [seed-attendees.sh](../../scripts/seed-attendees.sh) grants it | See [RBAC model](#rbac-model-and-gotchas) |

Tools: Azure CLI, Azure Developer CLI **1.34 or later** (`azd version`), Python 3.11+ with
`pip install -r requirements.txt`, Fabric CLI (`pip install ms-fabric-cli`, Phase 3), and bash. The Codespace
has all of them. On Windows, use Git Bash (`bash scripts/preflight.sh mcaps`).

Sign in once per shell:

```bash
az login --tenant <tenant-id>             # tenant ID: workshop.yaml environments.<env>.tenant_id
azd auth login --tenant-id <tenant-id>
fab auth login                            # Phase 3 onwards
```

## Timeline

### T-10: quota requests

```bash
azd env new mcaps --subscription <subscription-id> --location swedencentral   # once per environment
bash scripts/preflight.sh mcaps
```

For every FAIL, preflight prints the quota-request link. Typical asks on a fresh subscription:

| Quota | Needed | Where |
|---|---|---|
| Fabric capacity units in `swedencentral` | 2 CU for F2, 4 CU for F4 (`FABRIC_SKU`) | Azure portal → Quotas → Microsoft Fabric |
| `gpt-5-mini` Global Standard | 400K TPM (Labs 0–2, Lab 3 specialists, memory store, KB planner, Lab 4) | Foundry portal → Management center → Quota |
| `gpt-4.1-mini` Global Standard | 200K TPM (Lab 3 coach on, Fabric tool agents, evaluation judges) | Same |
| `text-embedding-3-small` Global Standard | 100K TPM | Same |
| Azure AI Search Basic in `swedencentral` | 1 service | Usually available; preflight checks it |

These caps are sized for 6 participants plus the facilitator on one shared project. The Azure sponsorship
subscription (quota Tier 0) offers 500K TPM for `gpt-5-mini`, 200K for `gpt-4.1-mini` and 1M for
`text-embedding-3-small`, and no `model-router` (ASSUMPTIONS.md 9.1). Quota is per subscription, per region and per
model, so **delete any test deployment of the same model first**: a 100K `gpt-4.1-mini` test deployment leaves only
100K for the workshop and the 200K deployment fails. A second region adds no quota on Tier 0, so keep one region.

### T-7: tenant settings and preflight green

1. Fabric admin portal → Tenant settings, as listed in [TENANT-BOOTSTRAP.md](TENANT-BOOTSTRAP.md#fabric-tenant-settings).
   Allow up to an hour to propagate.
2. Lab accounts, if the tenant does not have them yet:
   `bash scripts/tenant/create-lab-users.sh mcaps`. Passwords go to `.azure/mcaps/lab-accounts.csv` (gitignored).
3. `bash scripts/preflight.sh mcaps` must end with **all checks passed**. Warnings are fine.
   Accepted warnings are portal red teaming (the cloud red team runs from `scripts/red-team-cloud.py`) and a missing `fab`
   before Phase 3.
4. Builder repository access. This repository is private, and a Codespace needs read access. Collect the
   Builders' GitHub user names and add them as collaborators with **Read** (repository **Settings → Collaborators**),
   or publish a public copy for the day. Their Codespace hours come from their own GitHub account. Anyone without
   a GitHub account uses the local option in the [README](../../README.md#-builder-setup).

### T-3: build the environment

About 1.5 h end to end.

| Step | Command | Time | Done when |
|---|---|---|---|
| 1 Provision | `bash scripts/provision.sh mcaps --what-if` | ≈ 15 min | "provisioned mcaps" and `content/config/values.md` written (refreshed again after every deploy, Fabric deploy and `connect-tools.py`) |
| 2 Guardrails | `bash scripts/cost-guardrails.sh mcaps` | 1 min | All PASS; budget alerts at US$150 and US$300 listed |
| 3 Resident 360 on Fabric | `bash scripts/fabric/deploy.sh mcaps` | ≈ 17–20 min | 7 tables, ontology 4/5 with instances, graph refresh Completed, data agent published |
| 4 Knowledge base | `python scripts/build-kb.py` | 5 min | `livewell-guides-kb` answers with a citation (`--check` re-tests it) |
| 5 MCP server | `azd deploy mcp-activities` | 5 min | `MCP_URL` responds |
| 6 Tool connections | `python scripts/connect-tools.py`, then `python scripts/sync-openapi-block.py mcaps` (commit and push the two Lab 3 pages if it changed them) | 2 min | Activities MCP, Fabric IQ and the two specialist A2A connections (`livewell-nutrition-a2a`, `livewell-activity-a2a`); `/profile/me` 200, another resident 403; `FABRIC_IQ_CONNECTION_ID` in `.azure/mcaps/.env`; "Lab 3 spec block in sync" |
| 7 Hosted agent and DevUI (Lab 4) | Repo `.venv` active: `azd deploy livewell-workshop-hosted`, then `python scripts/hosted-postdeploy.py --verify`, then `azd deploy lab4-devui` | ≈ 10 min | Agent active; a week plan comes back as evidence JSON; the blocklisted prompt is blocked ([README](../assets/hosted-agent-example/README.md)). The values sheet shows **Lab 4 DevUI** and its token; signing in with the token lists both workflows |
| 8 Demo agents | `python demos/create-demo-agents.py` | 3 min | Seven `livewell-demo-*` agents listed (five lab agents plus the Nutrition and Activity specialists, each with "a2a on") and the `livewell-eval` dataset registered (Lab 2 portal evaluation picks it); `--check` re-tests |
| 9 Attendees | `bash scripts/seed-attendees.sh mcaps --lab-accounts` | 2 min | Every row shows `added` or `exists` |
| 10 Proof | `python scripts/smoke-test.py`, `make -C content/assets validate`, then `make -C content/assets validate-live ENV=mcaps` (graph check + 9 data-agent calls, ≈ 8 min) | 15 min | Smoke test 11/11 PASS (report in `content/assets/.runs/`); narrative report in `demos/NARRATIVE-VALIDATION-<date>.md` |
| 11 Pause | `bash scripts/capacity.sh suspend mcaps` | 1 min | Capacity `Paused` |

> **Always provision through `scripts/provision.sh`.** azd reads `infra/main.bicepparam` *before* its
> preprovision hook runs. The script runs `scripts/select-params.py` first, which copies
> `infra/env/<env>.bicepparam` into place, records your principal ID and creates the resource group. A bare
> `azd provision` still works once that file exists. If the hook had to regenerate anything, it stops with "re-run"
> so a stale file can never deploy the wrong environment. With `FABRIC_BRIDGE=true` it also stops while the Fabric
> capacity is paused, because ARM cannot update a paused capacity. Resume it first, then suspend it again afterwards.

**Lab 4 DevUI (`lab4-devui`).** Navigators run the Lab 4 orchestration in the browser, with no local install. It is
`demos/lab4-devui.py` in a container app (`ca-lab4-devui-<env>`) on the workshop's Container Apps environment.
- **Identity.** It has its own managed identity with Foundry User on the project and AcrPull. It has no other Azure
  access.
- **Sign-in.** One bearer token per environment (`LIVEWELL_DEVUI_TOKEN`). `select-params.py` generates it, Bicep
  stores it as the container-app secret `devui-auth-token`, and it appears on the values sheet.
- **Who can read the token.** The values sheet also prints the command that reads it
  (`az containerapp secret show … --secret-name devui-auth-token`). Running it needs
  `Microsoft.App/containerApps/listSecrets/action`, which in the built-in roles means **Owner** or **Contributor** on
  the app, its resource group or the subscription. Foundry User, the role `seed-attendees.sh` grants, cannot run
  it. Attendees with one of those roles can get it themselves (Lab 4 step 1); everyone else uses the values sheet.
- **Capacity.** It runs one replica. Every run builds a fresh copy of its workflow, so runs never share chat history.
  `DEVUI_SEATS` (default 8) caps how many runs of each workflow can be in flight at once; a ninth gets "All 8 seats
  … are busy".
- **Validation.** Validated 2026-10-03 on MCAPS: 6 sequential runs at once took 55–73 s each, and 6 hand-off runs at
  once took 38–52 s each.
- **Opting out.** `azd env set LAB4_DEVUI false` skips it. Then deploy services by name and leave out `lab4-devui`.
- **Caveats.** DevUI is a sample (beta), not a production app. Everyone with the token shares one session list, and
  the data is fictional. Rotate the token with `azd env set LIVEWELL_DEVUI_TOKEN ""`, then provision again.

Re-run step 9 after step 3 so that attendees also get **Viewer** on the Fabric workspace, which gives read access to
the data agent. The postprovision hook (`scripts/apply-guardrail.py`) keeps every model deployment on the platform
default (`Microsoft.DefaultV2`) and the Lab 2 guardrail (`livewell-guardrails` + blocklist) current on every
provision; agents attach the guardrail themselves (ASSUMPTIONS.md 6.1). `--check` reports drift.

#### Step 3 in detail: `scripts/fabric/deploy.sh`

Needs `az login` and `fab auth login` as the facilitator, the capacity **Active** (`scripts/capacity.sh resume`), and the
tenant settings above. Every step checks before it creates, so re-running is safe. After a failure, resume with
`--from NN`. Use `--only NN` for one step and `--skip-upload` to reuse the files already in OneLake.

| Step | What it does | Typical time (F2) |
|---|---|---|
| 10 workspace | `HPB Resident 360` on the capacity; facilitators as workspace Admin | 1 min |
| 20 lakehouse-load | `lh_resident360`; uploads the kit files and `r360.py` (one file at a time); imports and runs `load_resident360`; checks the 7 tables, Rahim and the headline answer against the local build | 6–8 min |
| 30 ontology | `resident_ontology` from `content/fabric/ontology.blueprint.yaml` (create, or update in place). Either one starts a graph refresh | 2 min first time, then < 1 min |
| 35 graph-refresh | Waits for the refresh that step 30 started (or starts one) and counts nodes and edges with GQL | 8–9 min |
| 40 data-agent | `Resident360 Ontology Agent`: instructions, ontology source, **all entity types selected**, publish | 1 min |
| 90 write-env | `FABRIC_*` IDs and URLs into `.azure/<env>/.env` | 1 min |

Then check the agent from the command line (30–45 s per answer):

```bash
python scripts/fabric/ask.py "Which regions have the highest share of disengaged residents?"
# North 60/300 = 20.0%, then West 17.1%, Central 13.1%, East 11.7%, North-East 8.3%
python scripts/gen-citizens.py --from-onelake --check    # citizens.json agrees with the lakehouse
```

| Symptom | Fix |
|---|---|
| Step 30: 403 `FeatureNotAvailable` | Tenant setting **Users can create Ontology (preview) items** is off, or has not propagated yet (wait 15–60 min) |
| Data agent answers "There's content here that I can't work with" and then gives numbers | Its entity types are not selected, so the numbers are invented. Run `deploy.sh <env> --only 40`, then check again |
| Data agent reports a backend graph error | The graph has not loaded yet. Run `deploy.sh <env> --only 35` |
| Step 20 fails inside the notebook | Open `load_resident360` in the workspace to see the failing cell. The capacity must be Active |
| You changed the blueprint | `deploy.sh <env> --from 30`. The ontology is updated in place, then refreshed and republished |
| You changed `scripts/r360.py` (gold build or aggregates) | `deploy.sh <env> --from 20`: the notebook imports `r360.py`, so the tables, graph and agent all follow |
| Data agent: 429 `CapacityLimitExceeded`, or OneLake 503s during step 20 | F2 is throttled after a burst of calls. `scripts/capacity.sh suspend <env>` then `resume <env>` clears the carried-forward overage (≈ 2 min). `validate-narrative.py` waits 20 s between calls by default (`--pause`) |
| Data agent: 429 `RequestBlocked` ("blocked until" keeps moving) | The capacity is in interactive rejection after a long day of calls. `scripts/capacity.sh scale F4 <env>` (seconds; twice the CUs, so the overage burns down twice as fast; cleared in ≈ 4 min on 2026-10-01) and `azd env set FABRIC_SKU F4` so a provision keeps it. Suspend/resume clears it at once but bills the overage. Scale back with `scale F2` and `FABRIC_SKU F2`. F4 throttles too after a full day of runs (2026-10-01): suspend/resume cleared it |
| Data agent says the result was cut off, or gives counts far below the reference | Its query tool reads at most 200 rows. Check the data source instructions were published (`deploy.sh <env> --only 40`) and compare with the canonical GQL in `question-bank.md` |

### T-1: dry run

- `bash scripts/capacity.sh resume mcaps`, then run the whole day with a participant account in a private browser window.
- Builder setup as a participant: create a Codespace from `main`, sign in with
  `az login --use-device-code --allow-no-subscriptions` as a participant account, fill `content/assets/.env`
  ([README](../../README.md#your-env)) and run `python content/assets/check_setup.py`. It must end with
  **All set**. It is read-only and also confirms that the lab account can open the project, its connections and
  its model deployments.
- Builder rail end to end: `make -C content/assets validate-rail` (Labs 1–4 as `INITIALS=test`, ≈ 20 min; report in
  `content/assets/.runs/builder-rail-<date>.md`). It fails if a key signal is missing or an agent is left behind.
  To keep evidence that a script works, wrap it in `demos/record-terminal.py`, e.g.
  `python demos/record-terminal.py builder-lab3 -- python scripts/validate-builder-rail.py --labs 3 --verbose`: it
  writes the output with real timings (`.cast`) and a full-page PNG to `demos/evidence/<date>/` (commit them) and a
  replay video to `demos/videos/` (git-ignored). The current Builder Labs 1–4 set (sponsorship models) is indexed in
  [demos/evidence/2026-10-03/README.md](../../demos/evidence/2026-10-03/README.md); the Bridge replay is in
  [demos/evidence/2026-10-01/README.md](../../demos/evidence/2026-10-01/README.md).
- Lab 0 and Lab 2 facilitator demos (repo `.venv`; results stay in the project so the room can open them on the day):
  1. `python scripts/apply-guardrail.py --check`: drift none (deployments on `Microsoft.DefaultV2`).
  2. `python demos/guardrail-matrix.py --cloud`: four `livewell-demo-gr-*` agents and the evaluation
     `LiveWell guardrail matrix <timestamp>` (≈ 3 min, cents). Open it in **Evaluations → Compare** before the day.
  3. `python scripts/red-team-cloud.py --agents livewell-demo-tools,livewell-demo-guarded --yes`: cloud red team
     whose scorecard opens in **Evaluations → Red team** (≈ 50 min for both agents in parallel, so start it in the
     morning; ≈ US$35: about 1.2 M judge tokens on the AI evaluations meter plus about 2 M target tokens; one agent is
     about half). Afterwards, `--report <eval id>` reprints the table. Open two or three `[n safe?]` attacks in the
     portal before the day: in the validation run every counted success was a refusal the judge mislabelled.
     The red team runs as you, so the demo agents' memory tool saves its attack summaries into **your** memory
     scope, and those memories later get ordinary portal chats blocked by the content filter (ASSUMPTIONS 5.22).
     The script clears your scope in `livewell-demo-memory` when it finishes (skip with `--keep-memory`). If a run
     was interrupted, run `python scripts/reset-demo-memory.py` (lists and flags residue) and `--reset`.
- Lab 4 DevUI: open **Lab 4 DevUI** from the values sheet in a private window, connect with the token, and run each
  workflow once (≈ 1 min, cents) so the first live run is not a cold start. The steps are in Lab 4 Navigator steps
  1–3. To run it locally: `python demos/lab4-devui.py` opens `http://127.0.0.1:8090` without a token (install
  `requirements-demos.txt` first). `--capture` reruns both workflows headless and refreshes `screenshots/lab-04/10-`
  and `11-`.
- Red team on this laptop instead (content-harm categories only), in its own venv (PyRIT pins its own dependencies):
  `python -m venv .venv-redteam && .venv-redteam/bin/pip install -r requirements-redteam.txt`, then
  `INITIALS=fac .venv-redteam/bin/python scripts/red-team.py` (full scan, 192 attacks, ≈ US$8, estimated 30 min) or
  `--lite` (20 attacks, ≈ US$0.85, ≈ 3 min). It creates a temporary guarded coach, scans it and deletes it; keep the
  ASR scorecard it prints for Lab 2.
- Record the demos and refresh the portal screenshots (Phase 5 `demos/`; install once with
  `python -m pip install -r requirements-demos.txt`, which drives the installed Edge):
  1. `python demos/portal.py login`: headed Edge; sign in once as the facilitator (MFA). The profile is kept in
     `demos/.playwright/` (git-ignored), and later runs pick the account by themselves.
  2. `python demos/capture-screenshots.py` (≈ 30 min, or `--only lab-01 lab-03/12`), then review every PNG in
     `content/labs/screenshots/` against its slot caption. `--list-missing` lists the slots still empty, and
     `--link` turns filled slots into images on the portal lab pages and the Bridge spotlight. The Bridge slots
     (`--only bridge`) also screenshot the `demos/fabric-steps.py` page. It shows the newest saved run, else the
     committed sample `demos/samples/fabric-steps-q_dropped_attended_heldin.json` (captured live on F4,
     2026-10-01), which is also what `--replay` shows on the day if the capacity is throttled. After a data or
     prompt change, refresh it with `python demos/fabric-steps.py bridge --save-sample` and commit it.
  3. `python demos/record-demos.py` (≈ 70 min, or `--lab lab-02`): one captioned WebM per lab, plus `bridge`
     (Mei's multi-hop question, its Fabric IQ trace and the fabric-steps.py page), in `demos/videos/` (git-ignored).
     Watch each once before sharing; they are the backup for a stuck portal step.

  Both only chat with the `livewell-demo-*` agents and the hosted agent, open and cancel dialogs, and never save.
  IDs, endpoints and e-mails are rewritten in the page, and the account button is masked. Slots 00/01, 00/02,
  04/07 and 04/08 need a lab account and are taken by hand. Slot 02/16 needs a finished portal evaluation run.
- Copy `demos/DRY-RUN-TEMPLATE.md` to `demos/DRY-RUN-<date>.md` and fill it in during the run. Phase 6 fixes every
  finding in it.
- `bash scripts/cost-guardrails.sh mcaps --max-usd 150`, then `bash scripts/capacity.sh suspend mcaps`.

### T-0: workshop day

```bash
bash scripts/capacity.sh resume mcaps                    # ~1 min; Fabric step + bridge spotlight need it
MCP_MIN_REPLICAS=1 DEVUI_MIN_REPLICAS=1 bash scripts/provision.sh mcaps --skip-preflight   # no MCP or Lab 4 DevUI cold starts
python scripts/render-values.py mcaps                    # values sheet -> content/config/values.md (hooks also refresh it)
python scripts/apply-guardrail.py                        # AFTER 09:30 SGT: restores livewell-guardrails (reset daily ~09:15)
python scripts/smoke-test.py --demo-agents               # all PASS on the livewell-demo-* agents (incl. demo memory), ≈ 3 min
python scripts/reset-demo-memory.py                      # exit 0 = no red-team residue in your demo memory; else --reset
```

> ⚠️ **Re-apply the guardrail on the day.** In the MCAPS tenant a governance automation (`MCAPSGovernance-AutomationApp`) rewrites `livewell-guardrails` every morning at about 09:15 SGT: it keeps one annotate-only Indirect Attack filter and drops the blocklist. Agents still show the policy attached, but Lab 2's custom-guardrail blocks stop happening. Run `python scripts/apply-guardrail.py` after 09:30 SGT, then `python scripts/apply-guardrail.py --check` just before Lab 2 (exit 1 = drifted again; run it without `--check`). It takes under a minute and needs no agent changes (ASSUMPTIONS.md 4.14).

Put `content/config/values.md` on screen: the project endpoint, agent names, lab-account pattern and Wi-Fi.
Also post its rows in the workshop chat, so the URLs are clickable. Builders copy the project endpoint into `.env`,
which is too long to retype from the screen. In Lab 3, Navigators copy the profile OpenAPI spec straight from the lab
page: the block carries this environment's server address, so `python scripts/sync-openapi-block.py <env> --check`
must pass (if not, run it without `--check`, then commit and push the two Lab 3 pages). The sheet holds no keys or
passwords. Lab pages only ever use names, except that spec block.

### T+1: teardown

```bash
bash scripts/teardown.sh mcaps          # asks you to type the env name; --yes for scripts
```

This deletes the Fabric workspace, runs `azd down --purge` (resource group, Fabric capacity, budget, and purge of
the soft-deleted Foundry account), then verifies that nothing tagged `workshop=livewell env=mcaps` remains.
Lab accounts stay; remove them with `bash scripts/tenant/create-lab-users.sh mcaps --delete`.
Between sessions use `bash scripts/teardown.sh mcaps --pause-only` (pauses the capacity).
If you turned **security defaults** off in the sponsor tenant for the workshop (device code sign-in, ASSUMPTIONS.md
10.11), turn them back on: Entra admin center → Entra ID → Overview → Properties → Manage security defaults → Enabled.

## Cost table

US$ list prices, September 2026 (SPEC.md §13). The cohort is 20 people × 150 runs.

| Line | Low (gpt-4.1-mini, Basic search, facilitator red team) | High (gpt-4.1, S1, Bing $35/1k) |
|---|---:|---:|
| Model tokens (20 × 150 runs × 3k in / 500 out, ×2 buffer) | 12 | 60 |
| Quality evaluations (model tokens, no surcharge) | 4 | 4 |
| Red teaming / safety evals (AI evaluations meter $20/$60 per 1M; 5 scans × 50 prompts × 4 strategies) | 42 | 42 |
| Azure AI Search, 120 h | 12 | 40 |
| Semantic ranker, Bing, Code Interpreter, hosted agents, ACR, storage/App Insights | ~12 | ~18 |
| **Total** | **≈ 83** | **≈ 166** |
| Every participant runs a full red-team scan | +126 | → ≈ 292 |
| Fabric F2, 16 h active (≈ $0.36/h; ≈ $259/month if left on). F4 doubles it: ≈ $0.76/h, +12, ≈ $550/month | +6 | +6 |

Controls built into the template and checked by [cost-guardrails.sh](../../scripts/cost-guardrails.sh):

- One shared search service and knowledge base. Twenty Basic services would cost about $1,475/month.
- `gpt-5-mini` at reasoning effort Low is the default deployment. Every deployment is Global Standard with no PTU and
  no partner models. `gpt-5-mini` is capped at 400K TPM, `gpt-4.1-mini` (Lab 3 coach, Fabric tool agents, judges) at
  200K and embeddings at 100K. Pay-as-you-go tokens mean the cap costs nothing by itself; at 100K, three Lab 3
  coaches running at once already hit HTTP 429.
- Red teaming is run by the facilitator. The participant "lite" run (10 prompts × 2 strategies) costs about $17 in total.
- Bing grounding is off: there is no connection.
- The budget alerts at US$150 and US$300 (actual spend) and emails the facilitators plus the subscription Owners and Contributors.
- The Fabric capacity is paused every night, and `teardown.sh` runs at T+1.
- The agentic-retrieval plan stays on Free, and the semantic ranker plan on Free.
- Log Analytics has a 1 GB/day ingestion cap.

Check spend at any time with `bash scripts/cost-guardrails.sh mcaps`, which shows month-to-date cost by resource
type. Cost Management lags by up to 24 h.

## What not to leave running

| Resource | Idle cost | Action |
|---|---|---|
| Fabric capacity `fablivewell<env>` | ≈ US$0.36/h on F2 (≈ $259/month), ≈ US$0.76/h on F4 (≈ $550/month) | `scripts/capacity.sh suspend` every evening; `scale F2` after a busy day on F4; deleted by `teardown.sh` |
| Azure AI Search Basic `srch-livewell-<env>` | ≈ US$0.10/h (≈ $74/month) | Delete with `teardown.sh` at T+1; do not keep an environment "just in case" |
| MCP app with `MCP_MIN_REPLICAS=1` | A few US$/day | Re-provision with the default (0) after the workshop |
| Lab 4 DevUI app `ca-lab4-devui-<env>` (1 vCPU / 2 GiB) | Nothing at the default `DEVUI_MIN_REPLICAS=0`; ≈ US$0.11/h while active or with `DEVUI_MIN_REPLICAS=1` | Re-provision with the default (0) after the workshop; `teardown.sh` |
| ACR Basic | ≈ US$0.17/day | `teardown.sh` |
| Hosted agent `livewell-workshop-hosted` (Lab 4) | Container compute (0.5 vCPU / 1 GiB) only while a session is active; nothing when idle | `azd ai agent delete livewell-workshop-hosted` after the workshop, or `teardown.sh` |
| Red-team scans | $20–$60 per 1M evaluation tokens | Facilitator only; never loop them |
| Log Analytics / App Insights | Per GB ingested (capped at 1 GB/day) | `teardown.sh` |

## RBAC model and gotchas

| Principal | Role | Scope | Granted by |
|---|---|---|---|
| Facilitators | Foundry Project Manager | Foundry account | `infra/modules/rbac.bicep` |
| Facilitators | Foundry User | Project | `rbac.bicep` |
| Facilitators | Search Service Contributor + Search Index Data Contributor | Search service | `rbac.bicep` |
| Facilitators | Storage Blob Data Contributor, AcrPush | Storage, ACR | `rbac.bicep` |
| Project managed identity | Search Index Data Reader, AcrPull | Search, ACR | `rbac.bicep` |
| Project managed identity | Foundry User (memory calls the deployments as the project; 401 without it) | Foundry account | `rbac.bicep` |
| Project managed identity | Storage Blob Data Contributor (evaluation uploads) | Storage | `rbac.bicep` |
| Project managed identity | Foundry Agent Consumer (the A2A connections sign in as the project to call the demo specialists in Lab 3 step 11) | Project | `rbac.bicep` |
| Search managed identity | Cognitive Services User, Storage Blob Data Reader | Foundry account, storage | `rbac.bicep` |
| MCP app identity | AcrPull | ACR | `infra/modules/containerapps.bicep` |
| Lab 4 DevUI identity (`id-livewell-devui-<env>`) | Foundry User, AcrPull | Project, ACR | `infra/modules/devui.bicep` |
| Hosted agent identity (`livewell-workshop-hosted`) | Foundry User | Project | `scripts/hosted-postdeploy.py` (azd postdeploy hook; the identity only exists after the first deploy) |
| Attendees | Foundry User | Project | `seed-attendees.sh` |
| Attendees | Search Index Data Reader | Search service | `seed-attendees.sh` |
| Attendees | Log Analytics Reader | Application Insights | `seed-attendees.sh` (Tracing tab) |
| Attendees | Cognitive Services OpenAI User (Builder Lab 2 judges call the account's OpenAI endpoint, which a project role does not reach) | Foundry account | `seed-attendees.sh` |
| Attendees | Fabric workspace Viewer (read on the data agent) | Fabric workspace | `seed-attendees.sh`, after Phase 3 |

Role IDs are built-in and the same in every tenant. They live only in `workshop.yaml` → `rbac_roles`.

Gotchas:

- **Foundry User cannot deploy models, create connections or publish hosted agents.** The facilitator
  pre-creates every deployment, connection (search, storage, ACR, App Insights, MCP, Fabric IQ) and the Lab 4
  hosted agent. Attendees only create agents, threads and evaluations.
- **The Fabric IQ connection needs Foundry Project Manager to create** and only lists *published* data agents.
  Attendees reuse it; they need Foundry User plus read on the data agent (workspace Viewer).
- **The Fabric IQ tool runs as the signed-in user** (no service principal at runtime). The attendee's
  Foundry account and Fabric account must be the same Entra identity in the same tenant.
- **Attendees need a Fabric licence** for that call. Assign the tenant's free Microsoft Fabric licence (Entra →
  Users → Licenses, or Graph `assignLicense`), or have each attendee sign in once at app.fabric.microsoft.com before
  the Fabric step. An unlicensed account gets `UserNotLicensed` from Fabric, as the facilitator did in preflight.
- Role assignments take up to 5 minutes to apply. Attendees should sign out and back in to ai.azure.com if
  the project is missing.
- `azd down` removes every role assignment with the resource group. `seed-attendees.sh` must be re-run after
  each re-provision.
- Guests (B2B) must redeem the invitation before role assignments show up in the portal. Lab accounts are simpler.

### Evaluation uploads

`lab2_govern.py` scores locally by default and prints the headline. `--upload` also publishes the run to the project's
**Evaluations** page through the project's storage connection (the knowledge storage account). The account allows
public network access with Entra ID only (`storageNetworkDefaultAction='Allow'`, ASSUMPTIONS 4.4 and 4.15), so the
upload works from a laptop or Codespace. The red-team script's `--upload` uses the same path.

If a tenant requires the account to be locked down, set `storageNetworkDefaultAction = 'Deny'` in the env's
`.bicepparam` and re-provision. Uploads then fail from outside Azure: the scripts say "upload to Foundry failed …
scored locally instead", and the local scores are still valid. To publish a run in that mode, add your IP with
`az storage account network-rule add` for the upload and remove it afterwards.

## Backup plans

| Failure | Backup |
|---|---|
| Sign-in / Authenticator / RBAC | Pair with a neighbour on a shared screen while an operator re-runs `seed-attendees.sh`; the break-glass account signs in if Entra is the problem |
| Model quota exhausted / 429s | Switch agents to the `gpt-4.1-mini` deployment (fallback, separate quota); lower concurrency by pairing |
| Knowledge base missing or broken | Attach the static guides (`content/knowledge/*.md`) as file search on the agent; rebuild the KB during the break |
| Evaluators unavailable in region | Show the pre-captured trace and evaluation screenshots (`content/labs/screenshots/lab-02/`) and the Lab 2 video (`demos/videos/`) |
| MCP server down | Run `content/assets/mcp-activities` locally (`python server.py`) and expose it with a dev tunnel; update the connection URL |
| Fabric tool down / capacity not resumed | `scripts/capacity.sh resume`; if the data agent still fails, play the Lab 3 or Bridge video from the dry run (the Fabric step is optional), or show `python demos/fabric-steps.py --replay bridge --open` (no capacity needed) |
| Portal step changed, or an attendee table is stuck | Demo it on the matching `livewell-demo-*` agent, or play that lab's video from `demos/videos/` |
| Whole region degraded | The documented fallback is `northcentralus`: `PREFLIGHT_ACCEPT_FALLBACK=1`, set `AZURE_LOCATION`, then re-provision (≈ 1.5 h). Decide by T-1 |

## Troubleshooting provisioning

| Symptom | Fix |
|---|---|
| `azd provision` → "missing required inputs" | Run `bash scripts/provision.sh <env>`, which generates `infra/main.bicepparam` first |
| Preprovision hook says "re-run" | Expected after switching environments; run the same command again |
| Preprovision hook: "Fabric capacity … is paused", or a provision fails on `fabric` with "Service is not ready to be updated" | ARM cannot update a paused capacity. `bash scripts/capacity.sh resume <env>`, provision, then `suspend <env>` |
| Lab 4 DevUI shows the "Your Azure Container Apps app is live" page | The app still has the placeholder image: run `azd deploy lab4-devui` |
| Budget deployment fails with a start-date error | An existing budget cannot move its start month. `select-params.py` pins `BUDGET_START_DATE` in the azd env on first provision and `teardown.sh` clears it. If you deleted the resource group by hand, run `azd env set BUDGET_START_DATE ""` before re-provisioning |
| `FlagMustBeSetForRestore` / "soft-deleted" Foundry account | `az cognitiveservices account purge -n aif-livewell-<env> -g rg-livewell-workshop-<env> -l swedencentral` (`teardown.sh` does this) |
| Fabric capacity "admin members invalid" | `fabricAdminMembers` must be UPNs of **member** accounts in the same tenant (no guests) |
| Fabric API `UserNotLicensed` | Sign in once at app.fabric.microsoft.com with that account to get the free Fabric licence |
| Fabric capacity: "Tenant ... wasn't recognized by Microsoft Fabric" | The tenant has never signed up for Fabric. A tenant admin signs in once at app.fabric.microsoft.com, then re-run `provision.sh`. Until then, `azd env set FABRIC_BRIDGE false` provisions everything else |
| Search: `ResourcesForSkuUnavailable` | The region has no capacity for new search services (seen in swedencentral for Basic **and** serverless). `azd env set SEARCH_LOCATION francecentral` (fallback `uksouth`, `switzerlandnorth`) and re-provision. Only the search service moves; Foundry reaches it over its managed identity. Record the block in `region_matrix.capacity_notes.search` so preflight catches it |
| `agent definition not found for service livewell-workshop-hosted` | The `azure.ai.agents` azd extension needs the inline agent definition in `azure.yaml`, and the service key must equal its `name` |
| Hosted agent: 424 `session_not_ready`, or `postdeploy` hook failed | See the troubleshooting table in [hosted-agent-example/README.md](../assets/hosted-agent-example/README.md) |
| Git Bash: paths like `C:/Program Files/Git/subscriptions/...` | Use the scripts; `scripts/lib/common.sh` sets `MSYS_NO_PATHCONV=1` |

## Script reference

| Script | What it does |
|---|---|
| [preflight.sh](../../scripts/preflight.sh) | Tools, subscription, region matrix, providers, Fabric CU quota, model quota, Search Basic, Fabric admin |
| [provision.sh](../../scripts/provision.sh) | Env + parameters + optional what-if + `azd provision` + values sheet |
| [cost-guardrails.sh](../../scripts/cost-guardrails.sh) | Asserts the §13 controls; month-to-date cost; `--pause-fabric`, `--max-usd N` |
| [capacity.sh](../../scripts/capacity.sh) | `status`, `suspend` or `resume` the Fabric capacity, or `scale F2\|F4` (pair it with `azd env set FABRIC_SKU`) |
| [fabric/deploy.sh](../../scripts/fabric/deploy.sh) | Resident 360 on Fabric: workspace, lakehouse and load, ontology, graph refresh, data agent, env IDs; `--from`, `--only`, `--skip-upload` |
| [fabric/ask.py](../../scripts/fabric/ask.py) | Ask the published data agent a question over MCP; `--json` |
| [validate-narrative.py](../../scripts/validate-narrative.py) | Narrative gate: `--layers static,data,live` (or `all`), `--fill`, `--check`, `--runs`, `--pause`, `--questions`; writes `reference-answers.json` and `demos/NARRATIVE-VALIDATION-<date>.md`. `make -C content/assets validate` / `validate-live` |
| [gen-citizens.py](../../scripts/gen-citizens.py) | `citizens.json` from the gold build; `--check`, `--from-onelake` |
| [apply-guardrail.py](../../scripts/apply-guardrail.py) | `livewell-guardrails` + blocklist from `guardrails.yaml`, and each deployment's guardrail (`Microsoft.DefaultV2`) (postprovision hook); `--check` |
| [build-kb.py](../../scripts/build-kb.py) | Foundry IQ knowledge base `livewell-guides-kb` + its MCP connection; `--source onelake`, `--check` |
| [connect-tools.py](../../scripts/connect-tools.py) | Activities MCP, Fabric IQ and specialist A2A connections, profile tool URL, access checks, Lab 3 spec block check; `--check` |
| [sync-openapi-block.py](../../scripts/sync-openapi-block.py) | Writes the live profile OpenAPI spec into the Lab 3 copy-and-paste block (both pages); `--check`. Commit and push the pages after it changes them |
| [hosted-postdeploy.py](../../scripts/hosted-postdeploy.py) | Hosted agent: identity RBAC + guardrail (azd postdeploy hook); `--check`, `--verify` |
| [gen-schemas.py](../../scripts/gen-schemas.py) | Navigator JSON schemas and the hosted agent's `livewell.json` from the prompts and `livewell_common.py`; `--check` |
| [validate-builder-rail.py](../../scripts/validate-builder-rail.py) | Runs Labs 1–4 as `INITIALS=test` with `--cleanup`, checks the key signals (KB citation, injected flyer blocked, ≥ 2 tools, Fabric for Mei and not for Rahim, hosted agent) and that nothing is left behind (items an interrupted earlier run left are deleted first); `--labs`, `--fabric`, `--report`, `--verbose`. `make -C content/assets validate-rail` |
| [red-team.py](../../scripts/red-team.py) | AI Red Teaming Agent scan of a temporary guarded coach (or `--agent NAME`); `--lite`, `--yes`, `--upload`, `--parallel`. Needs `.venv-redteam` (`requirements-redteam.txt`) |
| [red-team-cloud.py](../../scripts/red-team-cloud.py) | Cloud red team of `livewell-demo-tools` (or `--agents a,b`) with agentic + content-harm evaluators; results in **Evaluations → Red team**; clears your demo memory scope afterwards; `--taxonomy-only`, `--strategies`, `--turns`, `--yes`, `--report <eval id>`, `--keep-memory` |
| [reset-demo-memory.py](../../scripts/reset-demo-memory.py) | Lists your scope in `livewell-demo-memory` and flags red-team residue (exit 1); `--reset` clears it (`--yes` skips the prompt). Run after a red team and at T-0 |
| [guardrail-matrix.py](../../demos/guardrail-matrix.py) | Lab 2 demo: 7 prompts × {`gpt-5-mini`, `gpt-4.1-mini`} × {default, `livewell-guardrails`} on four `livewell-demo-gr-*` agents; `--cloud` (Foundry evaluation to compare), `--reps`, `--verbose`, `--delete` |
| [lab4-devui.py](../../demos/lab4-devui.py) | Lab 4: the sequential and hand-off teams from `lab4_multiagent.py` in Agent Framework DevUI on `127.0.0.1:8090`; `--port`, `--host`, `--seats N` (runs of one workflow in flight at once; each run builds a fresh workflow), `--no-browser`, `--mermaid` (prints the WorkflowViz graphs), `--capture` (headless runs and the two lab-04 DevUI screenshots). In the `lab4-devui` container app it runs with `--host 0.0.0.0`, the token from `DEVUI_AUTH_TOKEN` and DevUI developer mode (needed for the Events/Traces/Tools panel) |
| [stage-devui.py](../../scripts/stage-devui.py) | `lab4-devui` azd prepackage hook: copies the demo, `livewell_common.py`, `workshop.yaml`, the prompts, `citizens.json` and the 11 LiveWell guides (the Coach's `supporting_guides` may only use their ids) into `demos/devui-aca/app/` (git-ignored) for the image build |
| [seed-attendees.sh](../../scripts/seed-attendees.sh) | Lab accounts / file / guests → project, search, tracing and Fabric access; `--remove`, `--dry-run` |
| [render-values.py](../../scripts/render-values.py) | `.azure/<env>/.env` → `content/config/values.md`. Runs by itself after `azd provision` and `azd deploy` (hooks), `fabric/deploy.sh` and `connect-tools.py` |
| [smoke-test.py](../../scripts/smoke-test.py) | End-to-end check with temporary `livewell-smoke-*` agents: MCP, knowledge, guardrail, tools, Fabric, hosted agent, demo-memory residue, cost since provision; `--demo-agents`, `--no-fabric`, `--no-hosted`, `--since`, `--report` |
| [create-demo-agents.py](../../demos/create-demo-agents.py) | The seven `livewell-demo-*` agents (one per lab, plus the Nutrition and Activity specialists with incoming A2A and an agent card) and the `livewell-eval` dataset; a new version only when the definition changed; `--check`, `--roles`, `--no-memory`, `--no-dataset` |
| [portal.py](../../demos/portal.py) | Playwright helpers for the Foundry portal; `login`, `status`, `open <page>`, `shot <page>` |
| [capture-screenshots.py](../../demos/capture-screenshots.py) | Navigator screenshot slots from the live portal; `--only`, `--list-missing`, `--link [--dry-run]`, `--headless` |
| [record-demos.py](../../demos/record-demos.py) | One captioned WebM per lab and the Bridge spotlight into `demos/videos/`; `--lab` |
| [fabric-steps.py](../../demos/fabric-steps.py) | Bridge visualiser: the Fabric data agent's own run steps (rewrite, GQL, rows) for one question as an HTML page; `bridge`, `fit`, any question id; `--replay`, `--open`, `--save-sample` |
| [record-terminal.py](../../demos/record-terminal.py) | Evidence recorder: runs any script, then saves its output with real timings (`.cast`) and a PNG in `demos/evidence/<date>/` and a replay WebM in `demos/videos/`; IDs, endpoints, e-mails and local paths redacted; `--title`, `--render`, `--idle`, `--no-video` |
| [teardown.sh](../../scripts/teardown.sh) | Fabric workspace → `azd down --purge` → verify; `--pause-only` |
| [create-lab-users.sh](../../scripts/tenant/create-lab-users.sh) | 20 lab accounts + break-glass (Graph); `--delete`, `--reset-passwords` |
| [sign-in-cards.py](../../scripts/tenant/sign-in-cards.py) | One A4 sign-in card per participant (`--file attendees.txt` or `--lab-accounts`) → `.azure/<env>/sign-in-cards.pdf` (gitignored; holds passwords) |
