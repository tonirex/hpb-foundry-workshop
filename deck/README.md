# Slide deck generators

The PowerPoint files in this folder are generated; do not hand-edit the `.pptx` files.
Edit the generator and rebuild instead.

| Deck | Generator | Audience |
|---|---|---|
| `LiveWell-Foundry-Workshop-Day1.pptx` (20 slides) | `build_deck.py` | Facilitator's day deck: agenda, concepts, module cards, cost |
| `LiveWell-Lab-Flow.pptx` (18 slides) | `build_lab_flow.py` | Participants: the lab flow, what each lab builds, learning objectives |

Build from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install python-pptx pyyaml pillow
.\.venv\Scripts\python.exe deck\build_deck.py
.\.venv\Scripts\python.exe deck\build_lab_flow.py
```

Both accept `--out <path>`. Each build validates the file: speaker notes on every slide, no GUIDs or `{{ref:`
placeholders, every shape inside the slide, and no empty table cells.

## Day 1 deck

Slides cover: title, agenda, logistics, Fabric-to-Foundry arc, human thread, architecture, Foundry features, six
module cards (Labs 0-4 and the Fabric step), three Two IQs bridge slides, the guardrail scorecard, cost controls,
resources and close.

The module cards match the current lab pages: the Lab 0 refusal trace, the Lab 1 clinician route, the Lab 2
default-vs-custom guardrail ladder (block vs annotate, evaluators, red team), Lab 3 `livewell_profile` and approval
before `register_interest`, the Fabric step's programme-fit and region questions, and the Lab 4 DevUI sequential and
hand-off runs. Checkpoints are self-check against the collapsed Expected output; nothing is submitted.

## Lab-flow deck

A participant walkthrough of the day, built from the lab pages so it stays in step with them:

1. Title and the journey (seven stops, what the agent gains, the question that proves it).
2. The layer staircase (what each lab adds to the one agent) and the two seats, Rahim and Mei Lin, with the routing rule.
3. How every lab page works (Navigator, Builder, Checkpoint and Expected output).
4. One slide per lab (Labs 0-4, the Fabric step and the Bridge): objective, story, steps and a reviewed illustration
   or text-only expected-output reference, plus the Lab 2 guardrail ladder and the Lab 4 orchestration lanes (sequential, hand-off, hosted).
5. Learning objectives at a glance, the ten agent patterns by lab, where to find everything, and the takeaways.

Objectives and "You learned" lines are read from `content/labs/*.md`, prompts from
`content/prompts/test-prompts.json` (the build fails on an unknown prompt id), minutes and patterns from
`content/config/workshop.yaml`, and screenshots from `content/labs/screenshots/`.

The main lab pages now contain the full Navigator procedure and inline copy blocks. Images recorded by hidden
`historical-screenshot` markers are not rendered in the guides or embedded as current deck evidence: the lab-flow
deck renders a text-only reference card instead. Optional maintenance: retake only those images, review them,
replace their markers with normal Markdown images, then rebuild.
Lab 4 now distinguishes browser participation from facilitator-only deploy, and sequential JSON from hand-off output.

Workshop date, customer, Wi-Fi, lab durations, rails, resource names and model names are read from
`content/config/workshop.yaml`. Values set to `TODO` in that YAML render as `TODO — to be confirmed`.
