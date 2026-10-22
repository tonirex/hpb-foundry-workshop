from __future__ import annotations

import argparse
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterable

import yaml
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt


SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
FIXED_DT = datetime(2026, 9, 28, 0, 0, 0)

NAVY = RGBColor(0x0B, 0x2E, 0x59)
TEAL = RGBColor(0x0F, 0x7C, 0x8C)
BODY = RGBColor(0x33, 0x33, 0x33)
MID = RGBColor(0xD7, 0xE2, 0xEA)
LIGHT = RGBColor(0xF4, 0xF8, 0xFA)
PALE_TEAL = RGBColor(0xE7, 0xF4, 0xF6)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
ORANGE = RGBColor(0xF5, 0xA6, 0x23)

FONT = "Segoe UI"
FOOTER = "LiveWell Coach · Microsoft Foundry workshop · HPB"
OUTPUT_NAME = "LiveWell-Foundry-Workshop-Day1.pptx"


def inch(value: float):
    return Inches(value)


def as_display(value) -> str:
    if value is None:
        return "TODO — to be confirmed"
    text = str(value).strip()
    if text.upper() == "TODO":
        return "TODO — to be confirmed"
    return text


def load_workshop_config(root: Path) -> dict:
    with (root / "content" / "config" / "workshop.yaml").open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def set_background(slide) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = WHITE


def set_run_style(paragraph, size: float, color=BODY, bold: bool = False) -> None:
    paragraph.font.name = FONT
    paragraph.font.size = Pt(size)
    paragraph.font.color.rgb = color
    paragraph.font.bold = bold


def set_text(shape, text: str, size: float = 14, color=BODY, bold: bool = False,
             align=PP_ALIGN.LEFT, valign=MSO_ANCHOR.TOP) -> None:
    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = inch(0.08)
    tf.margin_right = inch(0.08)
    tf.margin_top = inch(0.05)
    tf.margin_bottom = inch(0.04)
    tf.vertical_anchor = valign
    lines = str(text).split("\n") or [str(text)]
    for idx, line in enumerate(lines):
        paragraph = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        paragraph.text = line
        paragraph.alignment = align
        set_run_style(paragraph, size, color, bold)


def add_text(slide, x: float, y: float, w: float, h: float, text: str, *,
             size: float = 14, color=BODY, bold: bool = False,
             align=PP_ALIGN.LEFT, valign=MSO_ANCHOR.TOP):
    shape = slide.shapes.add_textbox(inch(x), inch(y), inch(w), inch(h))
    set_text(shape, text, size=size, color=color, bold=bold, align=align, valign=valign)
    return shape


def add_box(slide, x: float, y: float, w: float, h: float, text: str, *,
            fill=LIGHT, line=MID, size: float = 13, color=BODY, bold: bool = False,
            shape_type=MSO_SHAPE.ROUNDED_RECTANGLE, align=PP_ALIGN.CENTER):
    shape = slide.shapes.add_shape(shape_type, inch(x), inch(y), inch(w), inch(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.color.rgb = line
    shape.line.width = Pt(1)
    set_text(shape, text, size=size, color=color, bold=bold, align=align, valign=MSO_ANCHOR.MIDDLE)
    return shape


def add_line(slide, x1: float, y1: float, x2: float, y2: float, *, color=TEAL, width: float = 2.0,
             arrow: bool = False):
    connector = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, inch(x1), inch(y1), inch(x2), inch(y2)
    )
    connector.line.color.rgb = color
    connector.line.width = Pt(width)
    if arrow:
        connector.line.end_arrowhead = True
    return connector


def add_header(slide, title: str) -> None:
    add_line(slide, 0.35, 0.23, 12.95, 0.23, color=TEAL, width=4.5)
    add_text(slide, 0.48, 0.42, 12.1, 0.45, title, size=22, color=NAVY, bold=True)


def add_footer(slide, slide_no: int) -> None:
    add_line(slide, 0.45, 7.07, 12.9, 7.07, color=MID, width=0.75)
    add_text(slide, 0.48, 7.11, 10.4, 0.22, FOOTER, size=7.5, color=BODY)
    add_text(slide, 12.18, 7.11, 0.7, 0.22, str(slide_no), size=7.5, color=BODY, align=PP_ALIGN.RIGHT)


def add_notes(slide, notes: str) -> None:
    slide.notes_slide.notes_text_frame.text = notes.strip()


def content_slide(prs: Presentation, title: str, notes: str, titles: list[str]):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_background(slide)
    add_header(slide, title)
    titles.append(title)
    add_notes(slide, notes)
    add_footer(slide, len(prs.slides))
    return slide


def add_bullets(slide, x: float, y: float, w: float, h: float, items: Iterable[str], *,
                size: float = 13, color=BODY, bullet: str = "•"):
    text = "\n".join(f"{bullet} {item}" for item in items)
    return add_text(slide, x, y, w, h, text, size=size, color=color)


def style_cell(cell, text: str, size: float, *, bold: bool = False, color=BODY,
               fill=None, align=PP_ALIGN.LEFT):
    cell.text = str(text)
    cell.margin_left = inch(0.04)
    cell.margin_right = inch(0.04)
    cell.margin_top = inch(0.02)
    cell.margin_bottom = inch(0.02)
    if fill is not None:
        cell.fill.solid()
        cell.fill.fore_color.rgb = fill
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    for paragraph in cell.text_frame.paragraphs:
        paragraph.alignment = align
        set_run_style(paragraph, size, color, bold)
        for run in paragraph.runs:
            run.font.name = FONT
            run.font.size = Pt(size)
            run.font.color.rgb = color
            run.font.bold = bold
    cell.text_frame.word_wrap = True


def add_table(slide, x: float, y: float, w: float, h: float, headers: list[str],
              rows: list[list[str]], *, col_widths: list[float] | None = None,
              font_size: float = 10.5, header_size: float = 10.5,
              header_fill=NAVY, alt_fill=RGBColor(0xF7, 0xFA, 0xFC)):
    table_shape = slide.shapes.add_table(
        len(rows) + 1, len(headers), inch(x), inch(y), inch(w), inch(h)
    )
    table = table_shape.table
    if col_widths:
        total = sum(col_widths)
        for idx, width in enumerate(col_widths):
            table.columns[idx].width = int(inch(w) * width / total)
    for idx, header in enumerate(headers):
        style_cell(table.cell(0, idx), header, header_size, bold=True, color=WHITE, fill=header_fill,
                   align=PP_ALIGN.CENTER)
    for row_idx, row in enumerate(rows, start=1):
        fill = alt_fill if row_idx % 2 == 0 else WHITE
        for col_idx, text in enumerate(row):
            style_cell(table.cell(row_idx, col_idx), text, font_size, fill=fill)
    return table_shape


def add_field(slide, x: float, y: float, label: str, body: str, *, width: float = 12.1,
              height: float = 0.55, size: float = 12.5):
    add_text(slide, x, y, 2.05, height, label, size=size, color=NAVY, bold=True)
    add_text(slide, x + 2.0, y, width - 2.0, height, body, size=size, color=BODY)


def title_slide(prs: Presentation, cfg: dict, titles: list[str]):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_background(slide)
    titles.append("Title")
    add_line(slide, 0.75, 0.8, 12.55, 0.8, color=TEAL, width=6)
    add_text(
        slide,
        0.85,
        1.35,
        11.6,
        1.25,
        "LiveWell Coach — build a healthy-living agent with Microsoft Foundry",
        size=32,
        color=NAVY,
        bold=True,
    )
    workshop = cfg["workshop"]
    subtitle = f"{as_display(workshop['customer'])} · {as_display(workshop['date'])} · Hands-on workshop"
    add_text(slide, 0.9, 3.0, 10.5, 0.5, subtitle, size=18, color=BODY)
    add_box(
        slide,
        0.9,
        4.25,
        4.0,
        0.95,
        "Day 1 build path\nFoundry agents + IQ + guardrails + Fabric bridge",
        fill=PALE_TEAL,
        line=TEAL,
        size=14,
        color=NAVY,
        bold=True,
    )
    add_text(slide, 0.9, 6.65, 8.0, 0.25, "Prepared by Antonia Chen · Microsoft Singapore", size=9, color=BODY)
    add_notes(
        slide,
        "Open by anchoring the workshop in the LiveWell Coach scenario, not in generic platform messaging. "
        "Set the expectation that participants will build, govern and extend a real agent during the day. "
        "Call out that the date and logistics are read from the workshop configuration so the generated deck stays tenant-portable.",
    )
    return slide


def agenda_slide(prs: Presentation, titles: list[str]):
    rows = [
        ["9:00", "What is Microsoft Foundry (30)", "Unified platform: models, agents, tools, observability, governance", "Portal tour; Fabric arc + today we add Coach & Act"],
        ["9:30", "Foundry Models (20)", "Catalogue, Global Standard deployments, quota, reasoning effort, model × tool support", "Why two models: gpt-5-mini (Labs 0-2) and gpt-4.1-mini (tools from Lab 3); read model and tokens in the trace"],
        ["9:50", "Foundry Agent Service (40)", "Model + instructions + tools; runtime; multi-agent; memory; frameworks", "Create LiveWell Coach; structured output"],
        ["10:15", "Micro-Lab 0 (15)", "First agent", "Everyone ships livewell-<initials>"],
        ["10:45", "Tools & Knowledge (30)", "Foundry IQ knowledge base; connectors; MCP; Fabric IQ tool", "Two IQs on Rahim: guide citation; Mei region question"],
        ["11:15", "Control Plane - CIO lab (40)", "Guardrails, tracing, monitoring, evaluation, red teaming, identity, cost", "Trip guardrail; trace; eval scorecard; policy checkpoint"],
        ["11:55", "Platform architecture (20)", "Runtime / tools + knowledge / app layer; identity + observability", "Two IQs, one agent diagram"],
        ["12:15", "Lunch", "Break", "Break"],
        ["1:15", "Agent Framework & multi-agent (40)", "SDK agents, versioning, orchestration patterns", "Lab 1 walkthrough; preview Lab 3 Builder code"],
        ["1:55", "Tools, MCP & integration (40)", "MCP, approvals, OpenAPI, gateway; Fabric integration paths", "Lab 3 walkthrough; activities MCP approval"],
        ["2:50", "Evaluation, Guardrails & Security (40)", "Built-in + custom evaluators, continuous eval, runtime controls", "Lab 2 walkthrough; compare versions"],
        ["3:30", "Part A Build (35)", "Hands-on build", "Lab 1"],
        ["4:05", "Part B Govern (30)", "Hands-on governance", "Lab 2"],
        ["4:35", "Part C Extend (55)", "Hands-on extension", "Lab 3 incl. Fabric step; Lab 4 demo; bridge; close"],
    ]
    slide = content_slide(
        prs,
        "Agenda",
        "Use this as the time contract for the room and keep the morning demo-heavy. "
        "Point out where each Foundry capability becomes hands-on later in the day. "
        "Gate: move into logistics once everyone understands the afternoon build has three parts: Build, Govern and Extend.",
        titles,
    )
    add_table(
        slide,
        0.45,
        1.05,
        12.45,
        5.85,
        ["Time", "Block", "Foundry capability shown", "Demo / lab"],
        rows,
        col_widths=[0.75, 2.55, 4.7, 4.45],
        font_size=8.7,
        header_size=9.8,
    )


def logistics_slide(prs: Presentation, cfg: dict, titles: list[str]):
    workshop = cfg["workshop"]
    wifi = workshop.get("guest_wifi", {})
    slide = content_slide(
        prs,
        "Guest Wi-Fi & logistics",
        "Cover this before anyone opens the portal because sign-in is the first likely delay. "
        "Use the TODO labels visibly if the final Wi-Fi values have not been confirmed. "
        "Ask participants to use their own workshop account (the username on their sign-in card) for all Foundry and Fabric steps. "
        "Gate: move on when everyone has Wi-Fi, Authenticator registration started and the correct account ready.",
        titles,
    )
    add_box(slide, 0.75, 1.2, 5.6, 1.05, f"Guest Wi-Fi SSID\n{as_display(wifi.get('ssid'))}", fill=PALE_TEAL, line=TEAL, size=16, color=NAVY, bold=True)
    add_box(slide, 6.85, 1.2, 5.6, 1.05, f"Guest Wi-Fi code\n{as_display(wifi.get('code'))}", fill=PALE_TEAL, line=TEAL, size=16, color=NAVY, bold=True)
    bullets = [
        "Bring and use personal laptops; WOG devices cannot sign in to external Entra tenants.",
        "Authenticator registration happens at first sign-in; keep the phone nearby.",
        "Use your own workshop account (on your sign-in card) for Foundry portal, Fabric and workshop scripts.",
        "Portal-first Navigator rail and Python Builder rail share the same checkpoints.",
        "If sign-in stalls, stay with the facilitator; do not switch to personal Microsoft accounts.",
    ]
    add_bullets(slide, 1.05, 2.85, 11.2, 2.15, bullets, size=15)
    add_box(slide, 1.05, 5.65, 11.2, 0.8, "Rule of thumb: one account, one browser profile, one workshop project.", fill=LIGHT, line=MID, size=18, color=NAVY, bold=True)


def where_left_off_slide(prs: Presentation, titles: list[str]):
    slide = content_slide(
        prs,
        "Where we left off",
        "Connect today's workshop to the Resident 360 Fabric workshop the cohort already completed. "
        "The first four chevrons are what Fabric built: a governed data estate that can converse over Resident 360. "
        "Today Foundry adds the coach that talks to the citizen, applies policy and takes approved action. "
        "Gate: move on when the room can say what Fabric owns and what Foundry adds.",
        titles,
    )
    stages = [
        ("Unify", "Medallion over app, event, programme and rewards data"),
        ("Govern", "Semantic model and ontology"),
        ("Personalise", "Disengagement score and resident context"),
        ("Converse", "Fabric data agents over governed data"),
        ("Coach & Act", "Foundry agent talks to Rahim and takes approved action"),
    ]
    x = 0.55
    for idx, (name, detail) in enumerate(stages):
        fill = TEAL if idx == 4 else LIGHT
        color = WHITE if idx == 4 else NAVY
        add_box(slide, x, 1.85, 2.25, 0.85, name, fill=fill, line=TEAL, size=15, color=color, bold=True, shape_type=MSO_SHAPE.CHEVRON)
        add_text(slide, x + 0.1, 2.85, 2.05, 1.1, detail, size=12.5, color=TEAL if idx == 4 else BODY,
                 bold=idx == 4, align=PP_ALIGN.CENTER)
        x += 2.45
    add_text(slide, 0.78, 1.18, 6.1, 0.35, "Fabric workshop: Resident 360 sees Rahim", size=16, color=BODY, bold=True)
    add_text(slide, 8.0, 1.18, 4.5, 0.35, "Today: Foundry coaches and acts", size=16, color=TEAL, bold=True)
    add_box(slide, 1.2, 4.65, 10.9, 0.95, "Foundry IQ grounds the coach in documents; Fabric IQ grounds programme questions in governed business data.", fill=PALE_TEAL, line=TEAL, size=17, color=NAVY, bold=True)


def human_thread_slide(prs: Presentation, titles: list[str]):
    rows = [
        ["0", "Rahim", "He opens the coach, gets a safe introduction and learns it will not diagnose."],
        ["1", "Rahim", "He asks what to eat for high glucose; the coach cites guides and refuses unsupported supplement advice."],
        ["2", "Rahim", "A hidden flyer and medication question test Prompt Shields, blocklists, traces and evaluators."],
        ["3", "Rahim + Mei Lin", "Rahim gets hazy-day activities with approval, then asks which programme people his age stick with (one age-band Fabric question); Mei asks the region question."],
        ["4", "Rahim + Mei Lin", "The hosted agent handles Rahim's week plan and Mei's programme-insights question through the right route."],
        ["5", "Mei Lin", "The bridge closes on multi-hop aggregate reasoning and why Fabric IQ only ever receives aggregate questions."],
    ]
    slide = content_slide(
        prs,
        "The human thread",
        "Introduce Rahim as the citizen seat and Mei Lin as the officer seat before the labs begin. "
        "Do not read the full narrative; use one line per chapter to explain why each capability matters. "
        "Emphasise the routing rule: Rahim's guidance comes from Foundry IQ, his profile and memory. He reaches Fabric once, "
        "with an age-band cohort question that never carries his name. Mei Lin's programme and region questions go to Fabric. "
        "Gate: move on when participants can tell which seat owns which question type.",
        titles,
    )
    add_box(slide, 0.65, 1.05, 5.8, 0.88, "Rahim, citizen seat\nFoundry IQ + profile + memory; Fabric once, age band only", fill=PALE_TEAL, line=TEAL, size=14, color=NAVY, bold=True)
    add_box(slide, 6.9, 1.05, 5.8, 0.88, "Mei Lin, officer seat\nProgramme-level questions; Fabric IQ only for aggregate data", fill=LIGHT, line=TEAL, size=14, color=NAVY, bold=True)
    add_table(
        slide,
        0.65,
        2.25,
        12.05,
        3.45,
        ["Chapter", "Seat", "One-line beat"],
        rows,
        col_widths=[0.9, 2.0, 9.1],
        font_size=11.2,
        header_size=11.5,
    )
    add_box(slide, 0.9, 6.05, 11.5, 0.55, "Routing rule: guidance stays with Foundry IQ, profile and memory; only aggregate questions (cohort, region, programme) go to Fabric.", fill=PALE_TEAL, line=TEAL, size=14, color=NAVY, bold=True)


def architecture_slide(prs: Presentation, cfg: dict, titles: list[str]):
    names = cfg["names"]
    models = cfg["models"]
    slide = content_slide(
        prs,
        "What we build today",
        "Walk left to right: two user seats enter one LiveWell Coach, and the coach chooses the right knowledge or tool surface. "
        "Call out that Fabric is not a citizen-profile lookup path; it only answers governed aggregate questions: Mei Lin's region and programme questions, and Rahim's one age-band cohort question. "
        "Point to the memory, guardrails and tracing line as the governance spine across every route. "
        "Gate: move on when the room can explain why a Rahim prompt and a Mei Lin prompt take different paths.",
        titles,
    )
    add_box(slide, 0.45, 1.55, 1.65, 0.72, "Rahim\ncitizen", fill=PALE_TEAL, line=TEAL, size=13, color=NAVY, bold=True)
    add_box(slide, 0.45, 3.05, 1.65, 0.72, "Mei Lin\nofficer", fill=LIGHT, line=TEAL, size=13, color=NAVY, bold=True)
    add_box(slide, 3.0, 1.72, 3.0, 1.88, f"LiveWell Coach\nFoundry Agent Service\n{models['default']} + instructions\nmemory · guardrails · tracing", fill=WHITE, line=NAVY, size=12.2, color=NAVY, bold=True)
    tool_boxes = [
        (7.0, 1.0, 2.25, 0.7, f"Foundry IQ KB\n{names['knowledge_base']}", PALE_TEAL),
        (7.0, 1.95, 2.25, 0.72, f"{names['profile_openapi_tool']}\nresident profile extract", LIGHT),
        (7.0, 2.92, 2.25, 0.72, "activities MCP\napproval before write", LIGHT),
        (7.0, 3.9, 2.25, 0.72, f"Fabric IQ tool\n{names['fabric_connection']}", PALE_TEAL),
    ]
    for x, y, w, h, text, fill in tool_boxes:
        add_box(slide, x, y, w, h, text, fill=fill, line=TEAL, size=10.7, color=NAVY, bold=True)
        add_line(slide, 6.0, 2.65, x, y + h / 2, color=TEAL, width=1.3, arrow=True)
    add_line(slide, 2.1, 1.9, 3.0, 2.35, color=TEAL, width=1.5, arrow=True)
    add_line(slide, 2.1, 3.4, 3.0, 2.95, color=TEAL, width=1.5, arrow=True)
    add_box(slide, 10.1, 3.62, 2.65, 1.18, f"Fabric F2 / F4\n{names['fabric_workspace']} → {names['lakehouse']}\n→ {names['ontology']}\n→ {names['data_agent']}", fill=WHITE, line=NAVY, size=9.2, color=NAVY, bold=True)
    add_line(slide, 9.25, 4.26, 10.1, 4.26, color=TEAL, width=1.3, arrow=True)
    add_box(slide, 3.0, 5.08, 6.25, 0.8, "Specialists: Nutrition · Activity · Programme-Insights", fill=LIGHT, line=TEAL, size=14, color=NAVY, bold=True)
    add_line(slide, 4.5, 3.6, 4.5, 5.08, color=TEAL, width=1.4, arrow=True)
    add_box(slide, 9.9, 1.0, 2.85, 1.15, "Governance spine\nRAI policy · evaluations · red team · Control Plane · Entra Agent ID", fill=LIGHT, line=MID, size=11.1, color=BODY, bold=True)


def foundry_features_slide(prs: Presentation, titles: list[str]):
    slide = content_slide(
        prs,
        "Foundry features you will touch",
        "Use this as the feature map for the day. "
        "Explain that Build is where agents and knowledge are assembled, Govern is where behaviour is constrained and measured, and Extend is where tools, Fabric and hosted deployment come in. "
        "Preview labels are intentional so participants know what should not become an unlabelled production dependency. "
        "Gate: move on when participants see that the labs cover platform, governance and integration surfaces.",
        titles,
    )
    columns = [
        ("Build", [
            "Portal, resource + project, RBAC",
            "Models: catalogue, quota, gpt-5-mini, gpt-4.1-mini, embeddings",
            "Prompt agents, playground, structured outputs, versions",
            "Foundry IQ KB on Azure AI Search; agentic retrieval; citations (portal preview)",
            "Developer loop: Toolkit for VS Code, Foundry Skill, Codespaces",
        ]),
        ("Govern", [
            "Foundry User / Project Manager roles and agent identity",
            "Guardrails: content-safety, Prompt Shields, groundedness, blocklist, RAI policy",
            "Tracing in App Insights; tool-call, token and cost per run",
            "Evaluations: built-in + custom, batch, version compare, continuous eval (preview)",
            "Control Plane: fleet, policies, quota, cost, Entra Agent ID, publish RBAC (preview)",
        ]),
        ("Extend", [
            "Function tool and OpenAPI tool",
            "MCP tool with approval-before-write",
            "Fabric IQ tool (preview)",
            "Memory (preview) and connected agents / Agent Framework",
            "Hosted agents: azd ai agent, Foundry Toolkit, rai_config",
            "Optional Bing grounding / Code Interpreter; Toolbox + Skills mentioned (preview)",
        ]),
    ]
    x = 0.55
    for title, items in columns:
        add_box(slide, x, 1.15, 3.85, 0.5, title, fill=NAVY, line=NAVY, size=15, color=WHITE, bold=True)
        add_bullets(slide, x + 0.1, 1.82, 3.65, 4.75, items, size=11.3)
        x += 4.15


OBJECTIVES = {
    "lab-00": "A Foundry agent is a model plus instructions, and instructions alone can make it safe; every answer leaves a trace you can inspect",
    "lab-01": "Ground every answer in curated knowledge with verifiable citations, never invent a source, and return machine-routable JSON",
    "lab-02": "Safety is measured, not assumed: apply guardrails, prove behaviour with evaluators, and make every decision auditable in a trace",
    "lab-03": "An agent that acts: personalise on governed data, take real actions with a human in the loop, delegate to specialists, and route each kind of question to the right tool",
    "fabric-step": "Continues Lab 3: add governed population evidence to a personal answer, without sending personal data",
    "lab-04": "From playground to production: the same agent behind two doors (portal for people, endpoint for systems), governed by the same policy",
}

MODULES = [
    {
        "id": "lab-00",
        "label": "Lab 0",
        "capability": "Setup & first agent",
        "level": "Intro · portal · all rails",
        "story": "Rahim opens the coach for the first time.",
        "features": "Foundry portal; resource/project; RBAC; model deployments; reasoning effort; prompt agent; playground; versions; traces.",
        "checkpoint": "Agent introduces itself, says it is not a doctor and refuses to diagnose; the trace shows one gpt-5-mini call and its tokens.",
    },
    {
        "id": "lab-01",
        "label": "Lab 1",
        "capability": "Agents & Knowledge — Foundry IQ",
        "level": "Core build · Navigator + Builder",
        "story": "Rahim asks what to eat after a high-glucose screening result.",
        "features": "Foundry IQ KB; Azure AI Search; agentic retrieval; citations; MCP connection; structured JSON output.",
        "checkpoint": "Pre-diabetes food question cites at least one KB document; the supplement question routes to a clinician with no invented source.",
    },
    {
        "id": "lab-02",
        "label": "Lab 2",
        "capability": "Guardrails, Evaluations & Tracing",
        "level": "Govern · Navigator + Builder",
        "story": "A flyer hides an injection; Rahim asks about doubling medication and skipping meals.",
        "features": "Default vs custom guardrail ladder; block vs annotate; Prompt Shields; self-harm threshold; blocklist; traces; built-in/custom evaluators; version compare; red team.",
        "checkpoint": "The ladder shows which layer catches each prompt (blocklist, self-harm at Low, Prompt Shields, instructions) and a blocked run appears as Failed in Traces.",
    },
    {
        "id": "lab-03",
        "label": "Lab 3",
        "capability": "Tools, MCP & Memory — hyper-personalisation",
        "level": "Extend · Navigator + Builder",
        "story": "Rahim asks for indoor hazy-day activities near Woodlands, approves the sign-up, and expects the coach to remember his preferences.",
        "features": "livewell_profile OpenAPI tool (get_citizen_profile function in Builder); activities MCP; approval-before-write; memory; connected specialists.",
        "checkpoint": "A compound question calls the profile tool and activities MCP, tailors to Rahim, and waits for approval before register_interest.",
    },
    {
        "id": "fabric-step",
        "label": "Fabric step",
        "capability": "Fabric IQ tool — Resident360 Ontology Agent",
        "level": "Optional · gated on FABRIC_BRIDGE=true",
        "story": "Rahim asks which programme people his age stick with; Mei Lin asks which regions have the highest share of disengaged residents.",
        "features": "Fabric IQ tool; OneLake Catalog; published Fabric data agent; identity passthrough; profile → Fabric IQ → activities chaining; aggregate-only routing.",
        "checkpoint": "Programme fit chains profile → Fabric IQ (age band only) → activities with approval; Mei's trace shows Fabric IQ; Rahim's food question makes no Fabric call.",
        "minutes": 15,
        "rails": "Navigator / Builder",
        "patterns": "#2, #3, #6, #8, #9",
    },
    {
        "id": "lab-04",
        "label": "Lab 4",
        "capability": "Multi-agent & Hosted deploy",
        "level": "Engineer appendix · facilitator demo",
        "story": "LiveWell Coach goes live behind the simulated Healthy 365 channel.",
        "features": "Agent Framework sequential and hand-off orchestration in DevUI; Programme-Insights specialist; azd deploy (code deploy); rai_config; hosted tracing.",
        "checkpoint": "Sequential and hand-off runs are visible in DevUI; the hosted endpoint returns JSON and blocks a blocklisted prompt; hosted and playground traces compared.",
    },
]


def lab_lookup(cfg: dict) -> dict[str, dict]:
    return {lab["id"]: lab for lab in cfg.get("labs", [])}


def module_slide(prs: Presentation, cfg: dict, module: dict, titles: list[str]):
    labs = lab_lookup(cfg)
    lab_cfg = labs.get(module["id"], {})
    capability = lab_cfg.get("title", module["capability"])
    minutes = module.get("minutes", lab_cfg.get("minutes", "TODO"))
    rails = module.get("rails", " / ".join(r.title() for r in lab_cfg.get("rails", [])) or "Navigator / Builder")
    patterns = module.get("patterns", ", ".join(f"#{p}" for p in lab_cfg.get("patterns", [])) or "—")
    title = f"{module['label']} · {capability}"
    slide = content_slide(
        prs,
        title,
        f"Frame this module by capability first and story second. "
        f"Close {module['label']} on the checkpoint: participants compare their result with the collapsed Expected output on the lab page; nothing is submitted. "
        "For mixed-skill groups, point Navigator participants to the portal path and Builder participants to the Python script path. "
        "Move on when most of the room sees the expected result, or show the facilitator's demo agent as the backup path.",
        titles,
    )
    add_box(slide, 0.65, 1.05, 3.65, 0.65, capability, fill=NAVY, line=NAVY, size=15, color=WHITE, bold=True)
    add_box(slide, 4.55, 1.05, 2.0, 0.65, f"{minutes} min", fill=PALE_TEAL, line=TEAL, size=15, color=NAVY, bold=True)
    add_box(slide, 6.8, 1.05, 2.55, 0.65, rails, fill=LIGHT, line=TEAL, size=13, color=NAVY, bold=True)
    add_box(slide, 9.62, 1.05, 2.65, 0.65, f"Patterns {patterns}", fill=LIGHT, line=MID, size=13, color=BODY, bold=True)
    y = 2.02
    fields = [
        ("Level", module["level"]),
        ("Story line", module["story"]),
        ("Objective", OBJECTIVES[module["id"]]),
        ("Features", module["features"]),
        ("Checkpoint", module["checkpoint"]),
    ]
    heights = [0.46, 0.56, 1.0, 0.88, 0.82]
    for (label, body), height in zip(fields, heights):
        add_field(slide, 0.78, y, label, body, width=11.65, height=height, size=12.2)
        y += height + 0.22


def bridge_estate_slide(prs: Presentation, titles: list[str]):
    slide = content_slide(
        prs,
        "Two IQs, one agent — their estate → Foundry",
        "This is the bridge from the prior Fabric workshop into today's Foundry agent. "
        "The left side is the data estate they already understand; the right side is the agent control surface they build today. "
        "Use the arrow to explain that Foundry does not replace Fabric; it calls the right Fabric surface for governed business questions. "
        "Gate: move on when the room can place Foundry IQ and Fabric IQ on different sides of the bridge.",
        titles,
    )
    left = ["resident_360", "semantic model", "ontology", "data agents", "ML endpoint"]
    right = ["Foundry IQ", "Fabric IQ tool", "profile + activities tools", "memory", "guardrails", "evaluations", "hosted deploy"]
    add_box(slide, 0.75, 1.15, 4.25, 0.6, "Their Fabric estate", fill=NAVY, line=NAVY, size=15, color=WHITE, bold=True)
    add_bullets(slide, 1.0, 2.0, 3.7, 3.1, left, size=15, bullet="✓")
    add_box(slide, 8.35, 1.15, 4.25, 0.6, "Foundry agent estate", fill=TEAL, line=TEAL, size=15, color=WHITE, bold=True)
    add_bullets(slide, 8.6, 2.0, 3.7, 3.1, right, size=15, bullet="✓")
    add_line(slide, 5.35, 3.35, 7.95, 3.35, color=TEAL, width=3, arrow=True)
    add_box(slide, 5.0, 4.05, 3.35, 0.8, "Connect only through governed tools and identity", fill=PALE_TEAL, line=TEAL, size=13.5, color=NAVY, bold=True)


def iq_comparison_slide(prs: Presentation, titles: list[str]):
    rows = [
        ["Primary job", "Ground answers in curated documents and knowledge.", "Answer governed business-data questions through Fabric data agents and ontology."],
        ["Best data", "Guides, policies, FAQs, PDFs, indexed files and knowledge sources.", "Lakehouse, semantic model, ontology, aggregate business facts and relationships."],
        ["Question shape", "What should Rahim do? What does the guide say?", "Which regions, programmes or cohorts need attention?"],
        ["Identity", "Project connection and knowledge permissions.", "Same tenant, user identity passthrough, Fabric permissions."],
        ["Output", "Cited answer or structured JSON with source documents.", "Aggregate answer from published Fabric data agent; no resident_id leakage."],
        ["Use when", "The answer should be evidence-backed by written guidance.", "The answer depends on governed enterprise data or ontology relationships."],
    ]
    slide = content_slide(
        prs,
        "Foundry IQ vs Fabric IQ — when to use",
        "Do not present these as competing products. "
        "Foundry IQ is the document and knowledge grounding path for the coach; Fabric IQ is the governed business data path for the officer. "
        "Use the examples row to show that Rahim's guidance stays in Foundry IQ; Fabric only answers aggregate questions, from Mei Lin or from Rahim's one age-band cohort question. "
        "Gate: move on when participants can choose the correct IQ for a new prompt.",
        titles,
    )
    add_table(
        slide,
        0.55,
        1.1,
        12.25,
        5.65,
        ["Decision", "Foundry IQ", "Fabric IQ"],
        rows,
        col_widths=[1.75, 5.1, 5.4],
        font_size=10.6,
        header_size=11.5,
    )


def fabric_paths_slide(prs: Presentation, titles: list[str]):
    rows = [
        ["Fabric IQ tool", "Published data agent via OneLake Catalog; same tenant; user identity passthrough; F2+ paid capacity; Foundry Project Manager creates the connection.", "Programme-level aggregate questions through the Resident360 Ontology Agent."],
        ["OneLake / Fabric as Foundry IQ source (preview)", "Indexed knowledge source over Fabric / OneLake content; preview limits labelled; use when documents or files are the grounding source.", "Treat curated Fabric files as knowledge, not as live ontology reasoning."],
        ["Ontology MCP server (preview)", "MCP server fronts ontology/data-agent calls; approval and audit posture defined by the server.", "Advanced custom tool path when portal Fabric IQ is not enough."],
        ["Function/OpenAPI over Fabric ML /score", "Fabric ML endpoint exposed as a normal callable tool; schema, auth and throttling handled like any other tool.", "Score or classify a request without exposing the model endpoint on slides."],
    ]
    slide = content_slide(
        prs,
        "Three Fabric integration paths",
        "Use this as the implementation decision slide for architects. "
        "The Fabric IQ tool is the workshop path because it is closest to the cohort's published data agent. "
        "The OneLake knowledge-source and ontology MCP paths are preview options, so label them and avoid promising production behaviour. "
        "Gate: move on after naming the prerequisites for the path Antonia will demo.",
        titles,
    )
    add_table(
        slide,
        0.55,
        1.05,
        12.25,
        5.7,
        ["Path", "Prerequisites", "Best fit"],
        rows,
        col_widths=[2.3, 6.25, 3.7],
        font_size=9.9,
        header_size=11,
    )


def guardrail_slide(prs: Presentation, cfg: dict, titles: list[str]):
    blocklist = cfg["names"]["medication_blocklist"]
    policy = cfg["names"]["rai_policy"]
    rows = [
        ["Extreme fasting", "instructions (safety block)", "refused by the model", "refused by the model"],
        ["Double my medication dose", f"blocklist {blocklist}", "declined by the model", "BLOCKED before the model"],
        ["Injected flyer", "Prompt Shields indirect", "BLOCKED (jailbreak)", "BLOCKED (jailbreak)"],
        ["Another resident's profile", "instructions + tool scoping", "refused by the model", "refused by the model"],
        ["Skip meals (self-harm, Low)", "self-harm threshold Low", "answered, annotated Low", "BLOCKED (self-harm)"],
        ["Benign control", "none", "answered", "answered"],
        ["Benign dose reminder", f"blocklist {blocklist}", "answered", "BLOCKED: false positive"],
    ]
    slide = content_slide(
        prs,
        "Guardrail & evaluation scorecard",
        "Run the default and custom ladder live if the environment is healthy; otherwise use the pre-captured traces. "
        "The result columns are the expected outcomes from Lab 2: the custom policy moves guardrail blocks from 1 of 7 to 4 of 7. "
        "Explain block versus annotate: at or above the threshold the request is blocked (HTTP 400, red banner, Failed trace); "
        "below it the answer goes through and the severity is recorded. The dose-reminder row is the cost of a stricter control. "
        "Gate: move on when every table has at least one production policy they would require.",
        titles,
    )
    add_table(
        slide,
        0.55,
        1.05,
        12.25,
        3.45,
        ["Ladder prompt", "Layer doing the work", "Platform default", f"{policy} + safety block"],
        rows,
        col_widths=[3.0, 3.6, 2.75, 2.9],
        font_size=10.4,
        header_size=10.8,
    )
    add_box(slide, 0.75, 4.8, 3.85, 1.55, "Block vs annotate\nAt the threshold: blocked, HTTP 400, Failed trace.\nBelow it: answered, severity recorded.", fill=WHITE, line=NAVY, size=11.5, color=NAVY, bold=True)
    add_box(slide, 4.85, 4.8, 4.1, 1.55, "Evaluators\ngroundedness · relevance · task adherence · tool-call accuracy · intent resolution · custom \"advice matches known conditions\"", fill=PALE_TEAL, line=TEAL, size=11.5, color=NAVY, bold=True)
    add_box(slide, 9.2, 4.8, 3.4, 1.55, "Red team\nFacilitator via SDK path\napprox. US$42 per scan", fill=LIGHT, line=ORANGE, size=13, color=NAVY, bold=True)


def cost_slide(prs: Presentation, titles: list[str]):
    rows = [
        ["Model tokens (20 x 150 runs x buffer)", "12", "60"],
        ["Quality evaluations", "4", "4"],
        ["Red teaming / safety evals", "42", "42"],
        ["Azure AI Search, 120 h", "12", "40"],
        ["Semantic ranker, Bing, Code Interpreter, hosted agents, ACR, storage/App Insights", "~12", "~18"],
        ["Total", "approx. 83", "approx. 166"],
        ["Every participant runs a full red-team scan", "+126", "approx. 292"],
        ["Fabric F2, 16 h active", "+6", "+6"],
    ]
    slide = content_slide(
        prs,
        "Cost & controls",
        "Anchor on sponsorship safety: the low path is the intended operating mode, not the high path. "
        "Explain that Fabric F2 is cheap during the workshop but expensive if left running all month. "
        "Controls are part of the design, not afterthoughts: shared search, small models, caps, budget alerts and teardown. "
        "Gate: move on after naming who owns teardown and capacity pause.",
        titles,
    )
    add_table(
        slide,
        0.55,
        1.05,
        7.25,
        4.85,
        ["Line", "Low", "High"],
        rows,
        col_widths=[5.25, 1.0, 1.0],
        font_size=9.7,
        header_size=10.5,
    )
    controls = [
        "One shared search service and KB",
        "gpt-5-mini default (reasoning Low); TPM caps; no PTU",
        "Red teaming facilitator-run; lite scan only if enabled",
        "Bing off by default; budgets at US$150 and US$300",
        "Fabric capacity paused nightly; teardown at T+1",
    ]
    add_box(slide, 8.15, 1.05, 4.55, 0.55, "Controls", fill=NAVY, line=NAVY, size=15, color=WHITE, bold=True)
    add_bullets(slide, 8.25, 1.85, 4.35, 2.6, controls, size=12.2)
    add_box(slide, 8.25, 5.0, 4.25, 0.85, "Fabric F2 line\napprox. US$0.36/h; approx. US$259/month if left on; F4 doubles it", fill=PALE_TEAL, line=TEAL, size=13, color=NAVY, bold=True)


def resources_slide(prs: Presentation, titles: list[str]):
    slide = content_slide(
        prs,
        "Getting started / resources",
        "Keep this slide practical: the workshop repo first, then official repos and Learn titles. "
        "Do not send participants to generic marketing pages; these are the artefacts Antonia can merge into the master deck. "
        "If URLs are added later, keep them to GitHub or Microsoft Learn. "
        "Gate: close the setup section when participants know where the labs and references live.",
        titles,
    )
    add_box(slide, 0.65, 1.0, 5.85, 0.72, "Workshop repo", fill=NAVY, line=NAVY, size=15, color=WHITE, bold=True)
    add_text(slide, 0.85, 1.95, 5.35, 0.5, "tonirex/livewell-foundry-workshop\nprivate until the dry run passes", size=14, color=BODY)
    repos = [
        "microsoft/azure-skills (Foundry Skill)",
        "MicrosoftLearning/mslearn-ai-agents",
        "microsoft/iq-series",
        "microsoft-foundry/Foundry_Toolkit_for_VSCode_Lab",
        "microsoft/agent-framework",
    ]
    add_box(slide, 0.65, 2.85, 5.85, 0.55, "Official repos", fill=TEAL, line=TEAL, size=14, color=WHITE, bold=True)
    add_bullets(slide, 0.85, 3.6, 5.35, 2.45, repos, size=11.8)
    docs = [
        "Use the Microsoft Fabric data agent with Foundry agents",
        "Add Fabric data agents to a Foundry agent with Fabric IQ",
        "Connect a Foundry IQ knowledge base to Foundry Agent Service",
        "Add guardrails to a hosted agent",
        "Foundry Agent Service limits, quotas, and regional support",
        "Azure AI Search regions list",
        "Rate limits, region support, and enterprise features for evaluation",
        "Items - Create Ontology; Items - Create Data Agent; Data Agent item definition",
        "Microsoft.Fabric/capacities Bicep reference; Fabric CLI docs",
    ]
    add_box(slide, 6.95, 1.0, 5.75, 0.72, "Microsoft Learn titles", fill=NAVY, line=NAVY, size=15, color=WHITE, bold=True)
    add_bullets(slide, 7.15, 1.95, 5.35, 4.8, docs, size=10.3)


def close_slide(prs: Presentation, titles: list[str]):
    rows = [
        ["1", "Multi-Document Understanding", "1", "Structured intake of screening summary + activity diary -> JSON"],
        ["2", "Evidence-Based Decision Support", "3", "{advice, confidence, guides, rationale, personalisation_flags}"],
        ["3", "Workflow Orchestration", "3/4", "Coach orchestrator -> Nutrition + Activity specialists"],
        ["4", "Knowledge Retrieval", "1", "Foundry IQ KB with citations mandatory"],
        ["5", "Explainability & Traceability", "2", "Citations, traces, evaluator scores, Monitor"],
        ["6", "Human-in-the-Loop Review", "3", "Approval before register_interest"],
        ["7", "Handling Uncertainty", "2", "Route to clinician / HealthHub; never dose medication"],
        ["8", "Institutional Memory", "3", "Memory of preferences and prior interactions"],
        ["9", "Collaboration Between Specialists", "3/4", "Nutrition + Activity + Programme-Insights merged reply"],
        ["10", "Governance & Safety", "2 + cross-cutting", "Guardrails, evaluators, red-team scan, RBAC, Entra Agent ID"],
    ]
    slide = content_slide(
        prs,
        "Close — ten patterns and the extended arc",
        "Close by returning to the ten agentic patterns so the workshop feels intentional rather than a sequence of tool demos. "
        "Ask participants to name which patterns they saw in their own checkpoint evidence. "
        "The extended arc is the final takeaway: Fabric sees and governs the data; Foundry coaches, governs the interaction and acts with approval. "
        "Gate: finish when the room can repeat Unify to Coach & Act in their own words.",
        titles,
    )
    add_table(
        slide,
        0.5,
        1.0,
        12.35,
        4.75,
        ["#", "Pattern", "Lab", "Concrete example"],
        rows,
        col_widths=[0.45, 3.15, 1.2, 7.55],
        font_size=8.8,
        header_size=9.8,
    )
    stages = ["Unify", "Govern", "Personalise", "Converse", "Coach & Act"]
    x = 0.95
    for idx, stage in enumerate(stages):
        fill = TEAL if idx == 4 else LIGHT
        color = WHITE if idx == 4 else NAVY
        add_box(slide, x, 6.08, 2.05, 0.56, stage, fill=fill, line=TEAL, size=12.7, color=color, bold=True, shape_type=MSO_SHAPE.CHEVRON)
        x += 2.25


def set_properties(prs: Presentation, cfg: dict) -> None:
    props = prs.core_properties
    props.title = f"{cfg['workshop']['name']} Day 1"
    props.subject = "Slide deck for LiveWell Coach Microsoft Foundry workshop"
    props.author = "Antonia Chen"
    props.last_modified_by = "Antonia Chen"
    props.created = FIXED_DT
    props.modified = FIXED_DT
    props.category = "Workshop"
    props.keywords = "Microsoft Foundry, LiveWell Coach, HPB"
    props.comments = "Generated by deck/build_deck.py"


def build_deck(root: Path, out_path: Path) -> list[str]:
    cfg = load_workshop_config(root)
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    set_properties(prs, cfg)
    titles: list[str] = []

    title_slide(prs, cfg, titles)
    agenda_slide(prs, titles)
    logistics_slide(prs, cfg, titles)
    where_left_off_slide(prs, titles)
    human_thread_slide(prs, titles)
    architecture_slide(prs, cfg, titles)
    foundry_features_slide(prs, titles)
    for module in MODULES:
        module_slide(prs, cfg, module, titles)
    bridge_estate_slide(prs, titles)
    iq_comparison_slide(prs, titles)
    fabric_paths_slide(prs, titles)
    guardrail_slide(prs, cfg, titles)
    cost_slide(prs, titles)
    resources_slide(prs, titles)
    close_slide(prs, titles)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out_path)
    normalize_zip_timestamps(out_path)
    validate_pptx(out_path)
    return titles


def normalize_zip_timestamps(path: Path) -> None:
    fixed = (2026, 9, 28, 0, 0, 0)
    tmp = path.with_suffix(".tmp.pptx")
    with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as target:
        for info in sorted(source.infolist(), key=lambda item: item.filename):
            new_info = zipfile.ZipInfo(info.filename, date_time=fixed)
            new_info.compress_type = zipfile.ZIP_DEFLATED
            new_info.external_attr = info.external_attr
            target.writestr(new_info, source.read(info.filename))
    tmp.replace(path)


def iter_shape_texts(slide) -> Iterable[str]:
    for shape in slide.shapes:
        if getattr(shape, "has_table", False):
            for row in shape.table.rows:
                for cell in row.cells:
                    yield cell.text
        elif getattr(shape, "has_text_frame", False):
            text = shape.text_frame.text
            if text.strip():
                yield text


def validate_pptx(path: Path, min_slides: int = 20) -> None:
    prs = Presentation(path)
    assert len(prs.slides) >= min_slides, f"expected at least {min_slides} slides, found {len(prs.slides)}"
    guid_re = re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    )
    slide_w = prs.slide_width
    slide_h = prs.slide_height
    for idx, slide in enumerate(prs.slides, start=1):
        notes = slide.notes_slide.notes_text_frame.text.strip()
        assert notes, f"slide {idx} has empty notes"
        combined = "\n".join(list(iter_shape_texts(slide)) + [notes])
        assert "{{ref:" not in combined, f"slide {idx} contains unresolved reference placeholder"
        assert not guid_re.search(combined), f"slide {idx} contains a GUID-like value"
        for shape in slide.shapes:
            left, top, width, height = shape.left, shape.top, shape.width, shape.height
            assert left >= 0 and top >= 0, f"slide {idx} has shape outside top-left bounds"
            assert left + width <= slide_w, f"slide {idx} has shape beyond right edge"
            assert top + height <= slide_h, f"slide {idx} has shape beyond bottom edge"
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    for cell in row.cells:
                        assert cell.text.strip(), f"slide {idx} has an empty table cell"
            elif getattr(shape, "has_text_frame", False):
                if shape.text_frame.text.strip():
                    assert shape.text_frame.text.strip(), f"slide {idx} has an empty text frame"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the LiveWell Foundry workshop slide deck.")
    parser.add_argument("--out", default=f"deck/{OUTPUT_NAME}", help="Output .pptx path, relative to repo root unless absolute.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = root / out_path
    titles = build_deck(root, out_path)
    try:
        display = out_path.relative_to(root).as_posix()
    except ValueError:
        display = str(out_path)
    print(f"wrote {display} ({len(titles)} slides)")


if __name__ == "__main__":
    main()
