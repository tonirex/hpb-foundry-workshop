# LiveWell Coach — Portal track (🟢 Navigator)

This browser-only track is for 🟢 Navigator participants who want a click-by-click path through the workshop. You use the Microsoft Foundry portal, plus the shared DevUI in Lab 4: no code, terminal, SDK or notebooks.

Screenshots come from the live portal, captured with Playwright by `demos/capture-screenshots.py` (facilitator demo agents, names only). A step whose screenshot exists shows it as an image. A step still waiting for one keeps a text-only screenshot slot, so link checkers never fail.

## Naming rules

Your portal agent is `livewell-<initials>` and is reused from Lab 0 through Lab 3. Lab 4 uses prepared shared workflows instead. Do not edit or delete facilitator demo agents named `livewell-demo-*` or protected workshop agents named `livewell-workshop-*`; inspect and run them only when instructed.

## Walkthroughs

| # | Walkthrough | Capability | Time | Guide |
|---|---|---|---:|---|
| 0 | Setup & first agent | Foundry portal, prompt agent, reasoning effort, traces | 15 min | [Lab 0 portal](lab-00-portal.md) |
| 1 | Agents & Knowledge | Retrieval evidence, supported citations, JSON response | 35 min | [Lab 1 portal](lab-01-portal.md) |
| 2 | Guardrails, Evaluations & Tracing | Compare controls and read prepared evaluation verdicts/errors (look only) | 30 min | [Lab 2 portal](lab-02-portal.md) |
| 3 | Tools, MCP & Memory | Profile read, explicit approval, memory evidence | 30 min | [Lab 3 portal](lab-03-portal.md) |
| 4 | Multi-agent & Hosted deploy | Compare prepared workflows at 1:15; inspect the already-deployed hosted team at 5:15 | 25 + 5 min | [DevUI comparison](lab-04.md#-navigator) · [Hosted proof](lab-04-portal.md) |

## Screenshot slot convention

Each lab step has a screenshot slot in this exact format:

> 📸 **Screenshot slot** · `screenshots/lab-01/03-connect-foundry-iq.png` · Knowledge panel with livewell-guides-kb selected

Once its PNG exists, `python demos/capture-screenshots.py --link` rewrites the slot as `![caption](path)`. The capture still finds linked slots by their path, so re-capturing after a portal change needs no edits.

Rules for screenshot authors:

- Keep screenshot paths relative to `content/labs/`.
- Use `screenshots/lab-0N/NN-short-slug.png`.
- Convert a slot to an image only after reviewing its PNG against the caption; `--link` converts only slots whose PNG exists.
- `python demos/capture-screenshots.py --list-missing` lists empty slots, including the ones taken by hand with a lab account.
- Capture only names shown in [workshop.yaml](../config/workshop.yaml), never tenant IDs, subscription IDs, endpoints, keys, or real email domains.
