# HPB delivery runbook: MCAPS, 30 participants, one resource group

> **Status (2026-10-24): rehearsal stack deployed; limited facilitator readiness checks passed.** Search is in France
> Central (SPEC.md A.8); the other customer-managed resources are in Sweden Central in the same resource group.
> The user approved the workshop storage tag exception described below. No participant identities/TAPs, tenant-policy
> edits, quota requests, evaluations, red-team scans or load tests have been run. Limited facilitator readiness calls
> confirmed cited retrieval, profile-tool routing, a blocked medication prompt, the hosted structured plan and
> a Fabric-routed regional answer. This is not a full lab or 30-participant load rehearsal; items marked
> **UNVERIFIED** still need it. Lab 2's paid prepared evaluation has not been created.
>
> This is the primary procedure for the `mcaps` environment. [ADMIN-SETUP.md](ADMIN-SETUP.md) and
> [TENANT-BOOTSTRAP.md](TENANT-BOOTSTRAP.md) are earlier reference material from the 6-person sponsor delivery; where they
> differ from this page, this page wins. Why each decision was made is in [ASSUMPTIONS.md](../../ASSUMPTIONS.md) (Phase 11).

## 1. What is decided

| Topic | Decision | Single source |
|---|---|---|
| Target | The HPB MCAPS subscription and tenant in `environments.mcaps` | [workshop.yaml](../config/workshop.yaml) |
| Region | swedencentral, Fabric included; **Search only in francecentral**, explicitly approved. No automatic fallback | `names.location`, `environments.mcaps.search_location` |
| Resource group | One: `rg-livewell-workshop-mcaps` | `names.resource_group` |
| Participants | 30 accounts `hpb.lab01` to `hpb.lab30`, signing in with a Temporary Access Pass (TAP) | `environments.mcaps.participants`, `lab_accounts` |
| Models | gpt-5-mini (default), gpt-4.1-mini (tools and facilitator judge), text-embedding-3-small; **no model-router** | `models:` |
| Fabric | F2 (resizing needs separate approval) | `FABRIC_SKU`, [fabric.bicep](../../infra/modules/fabric.bicep) |
| Lab 2 | Look-only: participants explore a facilitator pre-run evaluation; they run no evaluation or red team | [lab-02.md](../labs/lab-02.md) |
| Budget | US$500 a month on the group, alerts at US$250 and US$500. A planning ceiling, **not an approved spend**; budgets alert, they do not stop spend | `environments.mcaps.budget_*` |
| Search capacity failure | Stop and report; never switch away from the approved region or SKU automatically | ASSUMPTIONS 11.13 |

## 2. Approval gates

Nothing in this table happens without separate approval from the customer or sponsor. The scripts enforce the first two
by design (`--yes` is required; the default is plan-only).

| Action | Command | Notes |
|---|---|---|
| Create the resource group and deploy | `bash scripts/provision.sh mcaps --yes` | `--what-if-only` is read-only and creates nothing |
| Register a resource provider | `PREFLIGHT_REGISTER_PROVIDERS=1 bash scripts/preflight.sh mcaps` | All 11 providers were Registered at the 2026-10-23 check |
| Create lab accounts, edit the TAP policy, issue or revoke TAPs | `scripts/tenant/create-lab-users.sh`, `scripts/tenant/issue-tap.sh ... --apply` | Tenant-level Entra changes |
| Create the Fabric workspace and items | `bash scripts/fabric/deploy.sh mcaps` | Fabric tenant settings and workspace ownership checks first |
| Paid evaluation or red-team run | `python demos/guardrail-matrix.py --cloud --save`, `scripts/red-team-cloud.py` | Facilitator only; paid |
| Live compatibility run, load test | `scripts/smoke-test.py`, `scripts/validate-builder-rail.py`, a staged load test | Model calls against the shared quota |
| Quota request, Fabric resize, purge of anyone else's soft-deleted account | none planned | Four soft-deleted accounts in swedencentral may hold quota; they are not touched |
| Teardown | `bash scripts/teardown.sh mcaps --with-identity --yes` | Plan-only without `--yes` |

## 3. Models and quota

### 3.1 Recommendation (inventory checked 2026-10-23; **re-check at T-3**)

Read-only discovery against the subscription in `environments.mcaps`, region swedencentral. Units are 1K TPM each; the RPM
per unit comes from the catalogue (1 for the chat models, 6 for embeddings). Free quota is `limit - allocated` and includes
other workloads in the subscription.

| Role | Model / version | Deployment type | Region | Free quota then | Allocation | Why | Fallback |
|---|---|---|---|---|---|---|---|
| Default chat / reasoning | gpt-5-mini 2025-08-07, effort Low | GlobalStandard | swedencentral | 1,275 of 3,000 | 800 units = 800K TPM, 800 RPM (475 left) | GA (retires 2027-02-09); supports MCP; the repo's labs were tested on it at Low effort | gpt-5.4-mini 2026-03-17 on DataZoneStandard (1,000 free; GlobalStandard has 75): needs a live test, Learn lists function tools as No for it |
| Tools and facilitator judge | gpt-4.1-mini 2025-04-14 | GlobalStandard | swedencentral | 5,830 of 15,000 | 1,000 units = 1M TPM, 1,000 RPM (4,830 left; the Bicep maximum) | Only candidate with ample quota that the Learn matrix lists for functions, A2A, OpenAPI, Fabric Data Agent and MCP together. **Legacy** lifecycle, retires 2027-04-14, existing customers only: this subscription already deploys it | gpt-5.4-mini after a live function-tool test; gpt-4.1 |
| Embeddings | text-embedding-3-small v1 (1,536 dimensions) | GlobalStandard | swedencentral | 750 of 1,000 | 100 units = 100K TPM, 600 RPM (650 left) | GA (retires 2028-02-09); unchanged, so **no re-index** | text-embedding-3-large (needs new index dimensions and a full re-index: not planned) |
| Router | none | n/a | n/a | n/a | none | An earlier run routed the default pool to a non-approved provider and memory does not run behind it (ASSUMPTIONS 6.3, 6.5). Preflight and cost-guardrails fail if one appears | n/a |
| Judge | shares gpt-4.1-mini | n/a | n/a | n/a | no extra allocation | Non-reasoning, so no `is_reasoning_model` flag | n/a |

Re-run at T-3 and keep the output with the date:

```bash
bash scripts/preflight.sh mcaps                              # read-only; saves .azure/mcaps/model-inventory-<time>.json
python scripts/lib/modelcheck.py --env mcaps --table         # the table above with live numbers
python scripts/lib/searchcheck.py --env mcaps               # read-only regional SKU offerings, separate from quota
```

`modelcheck.py` reports four facts separately because none proves the next: **catalogue** (offered in the region),
**eligibility** (this subscription has a quota pool; a Legacy model also needs an existing deployment), **quota** (free
quota covers the sum of the planned deployments per pool) and **capacity** (the capacity API, which turned out to mirror the
quota headroom: it is not proof, only a real deployment is). If quota is short it says so and stops: **no quota is requested
and no region is changed automatically.** Retirement dates are warnings inside 180 days of the workshop date.

### 3.2 Compatibility (documentation and code paths; live runs pending)

| Surface | Model used in the code | Status |
|---|---|---|
| Prompt agents, Responses API, Agent Framework, DevUI, hosted agent | `models.default` (gpt-5-mini, Low effort); reasoning effort is set only for reasoning models | Documented; **live run pending** |
| Coach with OpenAPI, A2A, Fabric Data Agent and function tools | `models.tools` (gpt-4.1-mini). gpt-5-mini is listed as No for all four (Learn tool-support table, updated 2026-10-15) | Documented; ASSUMPTIONS 9.1 recorded 16/16 on gpt-4.1-mini with the re-ordered `tools` block |
| Specialists (knowledge base and MCP only) | gpt-5-mini; MCP is listed as Yes | Documented |
| Foundry IQ retrieval and query planning | `models.default` plans with low retrieval effort; embeddings by `text-embedding-3-small` | Documented; live run pending |
| Memory | memory store on `models.default` plus embeddings | Documented; live run pending |
| Fabric IQ | tool on the coach (gpt-4.1-mini); needs the Fabric licence and Viewer on the workspace | **UNVERIFIED** for a participant account (ASSUMPTIONS 3.16, 10.10) |
| Guardrails | policy `livewell-guardrails` attached by `apply-guardrail.py` | Documented; live run pending |
| Facilitator evaluation | judge on gpt-4.1-mini | Documented; paid, needs approval |

Static checks do not prove runtime support. No request in the repo passes `temperature`, `top_p` or `max_tokens` to the
reasoning model (checked by search), and the model, version and capacity are no longer hard-coded outside `workshop.yaml`.

### 3.3 Sizing for 30 (assumptions, not measurements)

Peak minute per participant: 18K tokens and 6 requests on each chat pool, 2K and 3 on embeddings; plus a 40K-token, 20-request
facilitator demo; times a 1.25 burst factor (`models.sizing`). That needs 725K TPM and 250 RPM on each chat pool against
800K / 800 (default) and 1,000K / 1,000 (tools), and 82K TPM / 119 RPM on embeddings against 100K / 600. The per-minute figure can
fit while a start where all 30 press Run together still exceeds the per-10-second request limit, so **start in waves of
ten**; Lab 2's red-flag round now uses 2 parallel workers instead of 7, and retries add jitter. The approved load test replaces
these assumptions. A model-router is not a throttling solution and is not used.

## 4. One resource group

**In the group:** Foundry account, project and model deployments; Azure AI Search; knowledge storage; Application Insights and
Log Analytics; Container Registry; Container Apps environment with the MCP and DevUI apps; the Fabric F2 capacity; the user-assigned
identities; the budget.

**Not in the group, and tracked separately:**

| Item | Where it lives | How it is tracked and cleaned |
|---|---|---|
| Entra users, TAPs, directory roles | Tenant | `lab-accounts.csv` and `tap-issued.csv` (gitignored); `issue-tap.sh revoke`, `create-lab-users.sh --delete` |
| Quota, provider registration | Subscription | Left alone; not a cost |
| Fabric workspace, lakehouse, notebooks, ontology, graph model, data agent, Viewer grants | Fabric service, assigned to the F2 | `verify-scope.py manifest` records ids; `teardown.sh` deletes the workspace by ID |
| Agent Service platform storage, a Microsoft-managed Key Vault, hosted-agent sandboxes | Service-managed | Not visible as resources; go with the project |
| A Container Apps infrastructure group (`ME_...`) | Possibly a platform-managed group in the subscription | **UNVERIFIED** until the first deployment; `verify-scope.py deployed` lists it |

Literal single-group containment is therefore not achievable and this runbook does not claim it.

Before deploying (read-only):

```bash
bash scripts/provision.sh mcaps --what-if-only     # target guard, preflight, static scope check, what-if only if the group exists
python scripts/verify-scope.py plan --env mcaps    # one group, Search in France Central only, all others Sweden Central
```

After an approved deployment (read-only):

```bash
python scripts/verify-scope.py deployed --env mcaps   # inventory and regions, tagged strays, connection and endpoint targets,
                                                      # role scopes, budget, Fabric capacity and workspace link
bash scripts/cost-guardrails.sh mcaps                 # budget, deployments vs units, search, tags, month-to-date cost
```

Permissions are resource-scoped: attendees get Foundry User on the project, Search Index Data Reader, Log Analytics Reader and
OpenAI User on the account, plus Viewer on the Fabric workspace and a Fabric licence; none at group or subscription scope.
Attendees cannot read the DevUI container-app secret (it needs Owner or Contributor): they use the token on the values sheet.

## 5. Procedure

1. **Point the shell at the workshop subscription** (section 6).
2. **Identity** (separate approval): create the 30 accounts, then issue TAPs (section 7). Skip this for the facilitator rehearsal.
3. **Plan** (read-only): `provision.sh mcaps --what-if-only`, `modelcheck`, `verify-scope plan`.
4. **Provision** (approval): `bash scripts/provision.sh mcaps --yes`, then `verify-scope deployed` and `cost-guardrails.sh`.
5. **Fabric** (approval): tenant settings as in [TENANT-BOOTSTRAP.md](TENANT-BOOTSTRAP.md#fabric-tenant-settings), then
   `bash scripts/fabric/deploy.sh mcaps`. The workspace is created on the F2 in the group and refused if a same-named workspace
   sits on another capacity; ids go to the manifest. **F2 has 2 capacity units: many simultaneous Fabric-step queries may
   queue.** Run that step in waves or as a facilitator demo; resizing is a separate approval. Pause when idle:
   `bash scripts/capacity.sh suspend mcaps`.

   **Current ontology attachment (October 2026):** if step 40 prints **ACTION REQUIRED**, open **Resident360 Ontology
   Agent** in **HPB Resident 360**, select **Sources > Add sources > Add an ontology > resident_ontology**, then
   resume with `bash scripts/fabric/deploy.sh mcaps --from 40`. The script verifies the context and publishes it.
   Do not retry the removed ontology-as-data-source API. The new context runtime uses source-native queries;
   the older GQL query screenshots are not a guaranteed description of its execution.
6. **Knowledge, tools, guardrails:** the steps 4 to 8 of the T-3 table in [ADMIN-SETUP.md](ADMIN-SETUP.md#t-3-build-the-environment)
   (`build-kb.py`, `azd deploy mcp-activities`, `connect-tools.py`, hosted agent and DevUI, demo agents) are unchanged.
7. **Facilitator pre-run evaluation** (paid, approval): `python demos/guardrail-matrix.py --cloud --save`. Check that a lab
   account can open the run in the portal; if not, the captured file (`content/data/lab2-prepared-eval.json`) or a screen share is the
   fallback. **UNVERIFIED** until a participant account tries it.
8. **Attendees:** `bash scripts/seed-attendees.sh mcaps --lab-accounts`, again after the Fabric deploy.
9. **Rehearsal** (section 8), then **workshop day** (section 9), then **teardown** (section 10).

## 6. Point the shell at the right subscription

The machine may be signed in to many tenants and `az` acts on its default subscription, which for this workshop is a
different one. The target tenant also holds a second subscription. Every script stops on a mismatch and prints the fix; none
switches subscription for you.

```bash
export AZURE_CONFIG_DIR="$HOME/.azure-hpb"           # recommended: a profile used only for this workshop
az login --tenant <tenant-id>                         # tenant id: environments.mcaps.tenant_id
az account set --subscription <subscription-id>       # subscription id: environments.mcaps.subscription_id
azd auth login --tenant-id <tenant-id>
python scripts/lib/target.py check --env mcaps       # prints the matched subscription and tenant, or what to fix
python scripts/verify-scope.py caller --env mcaps    # can this identity assign roles? (Owner read from ARM; Graph is not used)
```

On Windows run the `.sh` scripts in Git Bash. Facilitator roles: **Owner** on the subscription (read from ARM);
Fabric admin settings were readable with the target token on 2026-10-24. Authentication (Policy) Administrator
and TAP permissions remain **UNVERIFIED**; a TAP-policy read returned 403.

For this worktree's rehearsal, the isolated Azure CLI profile is `.azure/mcaps/azure-cli`, and azd's isolated
configuration is `.azure/mcaps/azd-config` with `auth.useAzCliAuth=true`. Set `AZURE_CONFIG_DIR` and `AZD_CONFIG_DIR`
to those absolute paths in each terminal that performs deployment. This does not switch the machine's default
profiles. Do not copy credential caches or turn off the target guard to work around a sign-in failure.

### Search-only regional exception

Search Basic, its index and the knowledge base are in France Central; the Foundry model and embedding deployments,
Blob source and Fabric F2 stay in Sweden Central. All customer-managed Azure resources still share the workshop group
and budget. Preflight checks Search in its own configured region, including current FetchOfferings results.
Cross-region calls can add latency and transfer costs, and indexed guides are stored in France. Keeping both resources
in the EU is not an EU-only processing guarantee for the GlobalStandard models. Rehearse ingestion and cited retrieval
before declaring the knowledge lab ready.

### Approved workshop storage exception

The inherited MCAPSGov storage Modify policy disables public network access, blocking local Blob guide ingestion.
The user approved `SecurityControl: Ignore` for **the workshop storage account only**, configured through
`environments.mcaps.storage_policy_opt_out_tag`. The public endpoint is enabled, but anonymous blob access and
shared-key access remain disabled: uploads and reads use Entra RBAC. No tenant/subscription policy assignment is edited.
The guide source stays Blob. Foundry also has conditional approval for this tag if API keys become necessary, but
the current deployment uses Entra and does not need that exception.

## 7. Identity: Temporary Access Pass

TAP replaces passwords and Authenticator for the 30 accounts. The tooling is plan-only by default and was tested with a fake
client only.

```bash
bash scripts/tenant/create-lab-users.sh mcaps --dry-run     # lists the 30 accounts; add --break-glass only if truly needed
bash scripts/tenant/issue-tap.sh mcaps issue                 # plan only: nothing is called
bash scripts/tenant/issue-tap.sh mcaps issue --check         # read-only: scopes, TAP policy state and bounds, accounts exist
# after approval, issue the passes (valid from the workshop morning; secrets go to .azure/mcaps/tap-issued.csv only):
bash scripts/tenant/issue-tap.sh mcaps issue --apply --start <ISO time> --lifetime-minutes 480
python scripts/tenant/sign-in-cards.py mcaps --with-tap      # print cards; the pass is a secret
```

Needs: an Authentication Administrator (Privileged Authentication Administrator for admin accounts) and the Graph scope
`UserAuthenticationMethod.ReadWrite.All`, which a plain `az` token may lack; the TAP method enabled in the tenant's
authentication-methods policy (editing it needs Authentication Policy Administrator). **None of this is verified.** TAP expiry
does not disable an account or end issued sessions: teardown revokes TAPs and deletes the accounts.

**Builder rail.** Whether `az login` accepts a TAP by browser or device code in this tenant, or from a Codespace, is
**UNVERIFIED**; a new tenant's security defaults can block device code (error 530035, ASSUMPTIONS 10.11). Do **not** turn a security
default off without approval: test plain `az login` first. The repository is private: invite each Builder's GitHub username
as a collaborator (Read) or give the release ZIP; an Entra account does not grant GitHub access.

## 8. Rehearsal checklist (everything here is still to do)

| Check | How | Pass when |
|---|---|---|
| Target and roles | `target.py check`, `verify-scope.py caller` | Both pass |
| TAP policy, issuing, sign-in | `issue-tap.sh ... --check`, then one test account | Policy enabled; portal sign-in works; Builder `az login` result recorded |
| Provision to an empty group | `provision.sh mcaps --yes` | `verify-scope.py deployed` has no failure; any `ME_` group is recorded |
| Search Basic in swedencentral | Part of provisioning | Created, or the failure is reported (no region switch) |
| Container Apps quota, storage network setting | Provisioning, `verify-scope.py deployed` | Environment and apps created; storage reachable by Search |
| Live compatibility | `smoke-test.py`, `validate-builder-rail.py` with `INITIALS=test` | Every lab passes on the chosen models, including tools, structured output, memory, guardrails |
| Load test | Staged waves of 10, 20, 30 simulated participants on both chat pools | No sustained 429s; latency acceptable; replaces section 3.3 |
| Participant permissions | Two real lab accounts, Navigator and Builder | Agent creation, Lab 2 prepared evaluation visible (also try without the account-scope OpenAI User role, which is only a leftover of the old Lab 2 judges), Fabric step works, DevUI via the values-sheet token |
| GitHub and Codespaces for 30 | Invites sent; one Codespace per rail | Everyone can open the repo |
| Fabric | Tenant settings; N simultaneous data-agent queries on F2 | Settings enabled; behaviour at concurrency recorded |
| Budget mail, prices | Alert recipient receives mail; pricing calculator | Mailbox confirmed; gpt-5-mini and gpt-4.1-mini meters confirmed |
| Teardown plan | `bash scripts/teardown.sh mcaps` (plan only) | Lists the group, workspace and accounts correctly |

## 9. Workshop day

- Resume the Fabric capacity (`scripts/capacity.sh resume mcaps`) and set `MCP_MIN_REPLICAS=1`, `DEVUI_MIN_REPLICAS=1` (one DevUI
  replica, 8 seats). Run `preflight.sh` and `cost-guardrails.sh mcaps --max-usd 150` the evening before.
- Start Lab 2 and the Fabric step in waves of ten. Do not raise a cap or request quota on the day; on sustained 429s switch the
  affected agents to the other deployment, per the run of show.
- Facilitators run the pre-run evaluation, the red-team scan and demos; participants only explore results.

## 10. Teardown (one runbook for Azure, Fabric and the temporary identities)

Deleting the resource group alone is **not** complete cleanup. The sequence:

```bash
bash scripts/teardown.sh mcaps                       # PLAN ONLY: lists the group, the Fabric workspace by id, the accounts and TAPs
# after approval:
bash scripts/teardown.sh mcaps --with-identity --yes
```

With `--yes` it takes a manifest (ids, no secrets), revokes TAPs and deletes the lab accounts and any break-glass account
(`--with-identity`), deletes the Fabric workspace **by id** after checking it sits on the workshop capacity, runs `azd down
--purge`, purges **only** the workshop's own soft-deleted Foundry account, and verifies: group gone, nothing tagged
`workshop=livewell` left in the subscription, no platform-managed group left, no workshop-named Fabric workspace. Every step stops
the run on failure. Without `--with-identity` the Entra accounts and TAPs remain and the script says so. Afterwards delete the local
secret files (`lab-accounts.csv`, `tap-issued.csv`, printed cards) and confirm the budget alert mailbox no longer needs the group.
Quota, provider registrations and anyone else's resources are never touched.

## 11. Unverified and open

TAP policy and Entra roles; whether a TAP works for browser or device-code `az login`; Fabric tenant settings and existing
workspaces in the HPB tenant; Search Basic capacity in swedencentral; Container Apps quota and a possible `ME_` group; the storage
Modify policy (the `SecurityControl: Ignore` tag is kept from ASSUMPTIONS 4.4); model prices; gpt-5.4-mini with function tools;
burst request-rate adequacy at 30; participant read access to the prepared evaluation; GitHub or Codespaces access for 30; the
budget alert mailbox. Full list: ASSUMPTIONS 11.10.
