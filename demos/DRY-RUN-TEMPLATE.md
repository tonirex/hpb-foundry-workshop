# Dry run - YYYY-MM-DD

<!-- Copy to demos/DRY-RUN-<date>.md before the dry run and fill in as you go. Phase 6 fixes every row in
     "Findings", so write each one so that someone else can reproduce it. Keep the numbering stable (F01, F02 ...);
     Phase 6 logs each fix against its ID in CHANGELOG.md. -->

| | |
|---|---|
| azd environment | `mcaps` / `sponsor` |
| Facilitator | |
| Attendee accounts used | e.g. `hpb.lab01` (Navigator), `hpb.lab02` (Builder), one guest |
| Browser / device | e.g. Edge private window, 1440×900 |
| Builder environment | Codespaces / local Python 3.12 |
| Fabric capacity | F2 / F4, resumed at hh:mm, suspended at hh:mm |
| Repo commit | `git rev-parse --short HEAD` |

## 1. Gates before the day

Paste the summary lines. Every gate must be green before the timed run starts.

| Gate | Command | Result | Time | Notes |
|---|---|---|---:|---|
| Preflight | `bash scripts/preflight.sh <env>` | | | |
| Smoke test | `AZURE_ENV_NAME=<env> python scripts/smoke-test.py` | _/7 | | report: `content/assets/.runs/` |
| Narrative gate | `python scripts/validate-narrative.py --env <env> --layers all` | | | |
| Builder rail | `make -C content/assets validate-rail` | _/_ signals | | report: `content/assets/.runs/builder-rail-<date>.md` |
| Demo agents | `python demos/create-demo-agents.py` | 5 agents, dataset v____ | | |
| Screenshots | `python demos/capture-screenshots.py --list-missing` | _ missing | | |
| Demo videos | `python demos/record-demos.py` | lab-00 … lab-04, bridge | | `demos/videos/` |
| Bridge visualiser | `python demos/fabric-steps.py bridge --save-sample` | 248 ✓ / Central ✓ | | `demos/runs/` |
| Red team (facilitator) | `scripts/red-team.py` / `--lite` | ASR __% (_/_) | | cost US$__ |
| Values sheet | `python scripts/render-values.py <env>` | _ values, _ missing | | |
| Cost check | `bash scripts/cost-guardrails.sh <env> --max-usd 150` | US$__ to date | | |

## 2. Timed run of show

One row per lab and rail. "Checkpoint" is the move-on gate on the lab page; mark it only when a lab account (not the
facilitator) reaches it without help.

| Lab | Rail | Planned | Actual | Checkpoint reached | Blocked by (finding ID) |
|---|---|---:|---:|---|---|
| Lab 0 Setup & first agent | 🟢 Navigator | 15 min | | ☐ | |
| Lab 0 Setup & first agent | 🔵 Builder | 15 min | | ☐ | |
| Lab 1 Foundry IQ | 🟢 Navigator | 40 min | | ☐ | |
| Lab 1 Foundry IQ | 🔵 Builder | 40 min | | ☐ | |
| Lab 2 Guardrails, evals, tracing | 🟢 Navigator | 40 min | | ☐ | |
| Lab 2 Guardrails, evals, tracing | 🔵 Builder | 40 min | | ☐ | |
| Lab 3 Tools, MCP, memory | 🟢 Navigator | 40 min | | ☐ | |
| Lab 3 Tools, MCP, memory | 🔵 Builder | 40 min | | ☐ | |
| Fabric step (optional) | both | 15 min | | ☐ | |
| Lab 4 Multi-agent & hosted (demo) | facilitator | 30 min | | ☐ | |

## 3. Things only a dry run can answer

Each was left open in [ASSUMPTIONS.md](../ASSUMPTIONS.md). Record the observed answer and whether the assumption stands.

| # | Question | Observed | Assumption stands? |
|---|---|---|---|
| Q1 | Does a **Foundry User** lab account reach the Fabric IQ data agent (ontology-backed) and get an answer? | | |
| Q2 | Can a Foundry User call the **hosted agent** endpoint (Lab 4 slots 04/07, 04/08)? | | |
| Q3 | F2 under load: data-agent latency and any 429 `CapacityLimitExceeded` with _ concurrent attendees | | |
| Q4 | Portal batch evaluation (Lab 2): time to finish, and does slot 02/16 now have a run to screenshot? | | |
| Q5 | Red-team full scan: wall-clock time and cost | | |
| Q6 | Memory recall in Lab 3: how long before "I prefer mornings" is recalled in a new conversation? | | |
| Q7 | Model quota: any 429s on gpt-5-mini / gpt-4.1-mini during Labs 1–3? | | |
| Q8 | Sign-in: first-login MFA / password change time for a fresh lab account | | |

## 4. Findings

Severity: **S1** blocks the lab or gives a wrong or unsafe answer · **S2** needs facilitator help or loses more than
5 minutes · **S3** wording, screenshot or cosmetic.

| ID | Sev | Lab / step | Rail | What happened (exact error text, screenshot path) | Expected | Suggested fix | Fixed in (Phase 6) |
|---|---|---|---|---|---|---|---|
| F01 | | | | | | | |
| F02 | | | | | | | |
| F03 | | | | | | | |

## 5. Screenshots and videos

| Item | Status | Notes |
|---|---|---|
| Portal slots filled (`--list-missing`) | _ of 71 | still manual: 00/01, 00/02, 04/07, 04/08, 02/16 |
| Portal UI drift since capture (any slot that no longer matches the portal) | | list slot IDs as findings |
| Videos lab-00 … lab-04 play end to end, no credentials visible | | |

## 6. Cost and cleanup

| Item | Value |
|---|---|
| Spend for the dry-run day (Cost Management, tag `workshop=livewell`) | US$ |
| Fabric capacity suspended afterwards (`scripts/capacity.sh suspend <env>`) | ☐ |
| Attendee agents cleaned up (`lw.cleanup(everything=True)` per account, `livewell-demo-*` kept) | ☐ |
| Lab accounts reset or disabled (`scripts/tenant/create-lab-users.sh <env> --reset-passwords`) | ☐ |

## 7. Sign-off

- [ ] Every S1 and S2 finding has a Phase 6 fix or an agreed workaround in the facilitator notes.
- [ ] Section 3 answers copied into ASSUMPTIONS.md (update or close each entry).
- [ ] Go / no-go for the sponsor tenant (Phase 7): **___**
