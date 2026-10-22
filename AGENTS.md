# AGENTS.md — how coding agents work in this repo

This repository builds the **LiveWell Coach** one-day Microsoft Foundry workshop for the Health Promotion Board (Singapore).
`SPEC.md` is the authoritative specification; `CODING-AGENT-PROMPTS.md` holds the standing prompt and the per-phase kick-off prompts.

Before you change anything: read `SPEC.md` in full, then the reference repositories in SPEC.md §2 (in that order).
Install the Foundry Skill first (`npx skills add https://github.com/microsoft/azure-skills --skill microsoft-foundry`, and
`npx skills add microsoft/skills` selecting `agent-framework-azure-ai-py`, `azure-ai`, `azure-ai-contentsafety-py`) and follow its
workflows for anything touching azd, hosted agents, evaluations or the Foundry MCP server.

## Standing rules

- SPEC.md is authoritative. Where SPEC.md and a reference repo disagree, SPEC.md wins; where SPEC.md and current Microsoft Learn docs disagree, follow the docs and record the deviation in ASSUMPTIONS.md and versions.md.
- Two rails only: 🟢 Navigator (Foundry portal) and 🔵 Builder (canonical Python scripts in # %% cell form; no committed .ipynb except the Fabric loader notebook; make notebooks renders untracked notebooks via jupytext).
- Single region swedencentral for every resource including the Fabric F2 capacity. Never Southeast Asia.
- Portable across two azd environments (mcaps, sponsor) in two Entra tenants: anything that differs is a parameter or an env-file value, never an edit.
- No subscription ID, tenant ID, GUID, endpoint or key in any lab page, slide or script constant — names only; values live in .azure/<env>/.env and content/config/workshop.yaml. One exception: the Lab 3 OpenAPI spec block (between `<!-- openapi-spec:begin/end -->`), which carries the activities server's address and is written only by scripts/sync-openapi-block.py.
- All data synthetic; original HPB-style guidance (no HealthHub text); no race or religion fields; Rahim = RESIDENT_00061 exactly as SPEC.md §3.3; the story quotes only numbers computed by scripts/validate-narrative.py.
- The narrative is secondary — every lab is named by the Foundry capability it teaches; the ten agentic patterns frame the day.
- Label every preview surface; keep validator checkpoints on GA paths; never use the Foundry portal Workflows item; use Foundry LLM-judge evaluators, not regex scorers.
- Pin versions (ms-fabric-cli, azure-ai-projects>=2.6.1, azure-search-documents==12.1.0b1, azure-ai-evaluation, agent-framework, mcp<2, Python 3.13); verify every API call against the Microsoft Learn pages in SPEC.md §2 before writing it.
- Small commits, conventional messages; one branch and one PR per phase; the PR description is the phase report.
- Ask no questions. Make reasonable assumptions, record each in ASSUMPTIONS.md with the phase number, and keep going.

## Practical notes for agents

- Builder-rail scripts live in `content/assets/` as `labN_*.py` in `# %%` cell form; `print()` output is ASCII-only; every script supports `--verbose` and `--cleanup`.
- Agent names follow `livewell-<INITIALS>-<role>`; `cleanup()` must never delete `livewell-demo-*` or `livewell-workshop-*`.
- Canned prompts are pulled by `prompt_id` from `content/prompts/test-prompts.json`; answer keys in `content/answer-keys/` are facilitator-only.
- Run `python scripts/check-content.py` before opening a PR (links resolve, no GUID/endpoint leaks, lab-page sections present).
