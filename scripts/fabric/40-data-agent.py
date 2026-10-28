#!/usr/bin/env python3
"""Step 40: create, configure and verify the Fabric data agent over resident_ontology.

New Fabric deployments use ontology context (October 2026). The public SDK/REST source-attachment API
does not expose that operation yet: attach it once in Sources > Add sources > Add an ontology, then
re-run this step. The script verifies the documented item-definition ontology parts before publishing.
Existing legacy ontology data sources keep their original configuration path.

Uses the public Fabric data agent management API (the same calls as fabric-data-agent-sdk 0.1.32):
  POST  /v1/workspaces/{ws}/dataAgents                                  create (GET first)
  PATCH /v1/workspaces/{ws}/dataAgents/{id}/staging/settings            aiInstructions
  POST  /v1/workspaces/{ws}/items/{id}/getDefinition                  read draft/published ontology context
  PATCH /v1/workspaces/{ws}/dataAgents/{id}/staging/datasources/{ds}/elements?id=  select every entity type
  PATCH /v1/workspaces/{ws}/dataAgents/{id}/staging/datasources/{ds}    data source instructions
  POST  /v1/workspaces/{ws}/dataAgents/{id}/staging/publish             publish
A newly added ontology source has NO entity types selected (selectionState "None"); the agent then cannot
query and answers "There's content here that I can't work with" followed by invented numbers.
Agent instructions are the `data-agent-instructions` block of content/fabric/data-agent-instructions.md and
the ontology source's instructions its `datasource-instructions` block (they steer the GQL the agent writes).
For ontology sources, instructions are the only tuning mechanism: POST .../fewShots answers 400 "Few shot
examples are not supported for Ontology data sources".

Idempotent: re-running re-applies instructions, verifies an attached ontology and publishes only when needed.
Fresh ontology context attachments have one explicit portal step; they are not silently substituted.

  python scripts/fabric/40-data-agent.py [--no-publish] [--dry-run]     (normally run by deploy.sh)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fabriclib as fl  # noqa: E402

INSTRUCTIONS = fl.ROOT / "content" / "fabric" / "data-agent-instructions.md"
DESCRIPTION = ("Aggregate-only questions for HPB programme officers over the synthetic LiveWell Resident 360 "
               "ontology (resident_ontology). Synthetic data.")


def instructions_text(name: str = "data-agent-instructions") -> str:
    m = re.search(rf"```text name={re.escape(name)}\n(.*?)\n```", INSTRUCTIONS.read_text(encoding="utf-8"), re.S)
    if not m:
        raise SystemExit(f"no ```text name={name} block in {INSTRUCTIONS}")
    return m.group(1).strip()


def mentions(obj, needle: str) -> bool:
    return needle.lower() in json.dumps(obj).lower()


def has_ontology_context(definition: dict, stage: str, workspace: str, ontology: str) -> bool:
    prefix = f"Files/Config/{stage}/ontologies/"
    return any(path.startswith(prefix) and path.endswith("/ontology.json") and isinstance(part, dict)
               and str(part.get("artifactId", "")).lower() == ontology.lower()
               and str(part.get("workspaceId", "")).lower() == workspace.lower()
               for path, part in definition.items())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-publish", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="print the instructions and exit")
    a = ap.parse_args()
    text = instructions_text()
    ds_text = instructions_text("datasource-instructions")
    if a.dry_run:
        print(text)
        print(f"\n({len(text)} characters)\n")
        print(ds_text)
        print(f"\n({len(ds_text)} characters)")
        return 0

    n = fl.names()
    agent_name, onto_name = n["data_agent"], n["ontology"]
    fab = fl.Fabric()
    ws = fab.workspace_id(n["fabric_workspace"])
    if not ws:
        raise SystemExit(f"workspace \"{n['fabric_workspace']}\" not found: run 10-workspace.sh")
    onto = fab.item_id(ws, "Ontology", onto_name)
    if not onto:
        raise SystemExit(f"ontology {onto_name} not found: run 30-ontology.py")

    agent = fab.item_id(ws, "DataAgent", agent_name)
    if agent:
        fl.say(f"  PASS  data agent exists ({agent})")
    else:
        res = fab.lro("POST", f"/v1/workspaces/{ws}/dataAgents",
                      {"displayName": agent_name, "description": DESCRIPTION}, what=f"create {agent_name}")
        agent = (res or {}).get("id") or fab.item_id(ws, "DataAgent", agent_name)
        if not agent:
            raise SystemExit(f"{agent_name} not found after create")
        fl.say(f"  PASS  data agent created ({agent})")
    base = f"/v1/workspaces/{ws}/dataAgents/{agent}"

    fab.call("PATCH", f"{base}/staging/settings", {"aiInstructions": text})
    staged = fab.get(f"{base}/staging/settings") or {}
    same = (staged.get("aiInstructions") or "").strip() == text
    fl.say(f"  {'PASS' if same else 'FAIL'}  staging instructions ({len(text)} characters)")
    if not same:
        return 1

    definition = fab.definition(ws, agent)
    if has_ontology_context(definition, "draft", ws, onto):
        fl.say(f"  PASS  ontology context {onto_name} is attached to the draft")
        if a.no_publish:
            fl.say("  WARN  --no-publish: the draft was not published")
        else:
            published = fab.get(f"{base}/settings") or {}
            if not (has_ontology_context(definition, "published", ws, onto)
                    and (published.get("aiInstructions") or "").strip() == text):
                fab.lro("POST", f"{base}/staging/publish", {"publishedDescription": DESCRIPTION}, what="publish")
            definition = fab.definition(ws, agent)
            published = fab.get(f"{base}/settings") or {}
            if not (has_ontology_context(definition, "published", ws, onto)
                    and (published.get("aiInstructions") or "").strip() == text):
                fl.say("  FAIL  published ontology context or instructions do not match")
                return 1
            fl.say("  PASS  published ontology context and instructions verified")
        fl.say("  info  ontology context uses source-native queries; legacy GQL data-source instructions are not applied")
        print(json.dumps({"FABRIC_DATA_AGENT_ID": agent}))
        return 0

    sources = fab.get(f"{base}/staging/datasources") or {}
    if mentions(sources, onto):
        fl.say(f"  PASS  ontology source {onto_name} already staged")
    else:
        fl.say("  ACTION REQUIRED  Fabric no longer accepts new ontology attachments through the data-source API.")
        fl.say(f"  Open {agent_name} in workspace {n['fabric_workspace']}: Sources > Add sources > Add an ontology "
               f"> {onto_name}. Then re-run this step; no tenant setting or evaluation is needed.")
        fl.say("  https://learn.microsoft.com/fabric/data-science/data-agent-ontology-sources")
        return 2

    ds_id = next((d["id"] for d in (sources.get("value") or []) if mentions(d, onto)), onto)
    elements = fab.get_all(f"{base}/staging/datasources/{ds_id}/elements")
    todo = [e for e in elements if not e.get("isSelected")]
    for e in todo:
        fab.call("PATCH", f"{base}/staging/datasources/{ds_id}/elements?id={urllib.parse.quote(e['id'])}",
                 {"isSelected": True})
    elements = fab.get_all(f"{base}/staging/datasources/{ds_id}/elements")
    unselected = [e["displayName"] for e in elements if not e.get("isSelected")]
    if not elements or unselected:
        fl.say(f"  FAIL  entity types not selected: {unselected or 'no elements listed'}")
        return 1
    fl.say(f"  PASS  {len(elements)} entity types selected ({len(todo)} changed): "
           + ", ".join(sorted(e["displayName"] for e in elements)))

    fab.call("PATCH", f"{base}/staging/datasources/{ds_id}", {"instructions": ds_text})
    staged_ds = fab.get(f"{base}/staging/datasources/{ds_id}") or {}
    same = (staged_ds.get("instructions") or "").strip() == ds_text
    fl.say(f"  {'PASS' if same else 'FAIL'}  staging data source instructions ({len(ds_text)} characters)")
    if not same:
        return 1

    if a.no_publish:
        fl.say("  WARN  --no-publish: the agent is not published, so Foundry's Fabric IQ tool cannot see it")
    else:
        fab.lro("POST", f"{base}/staging/publish", {"publishedDescription": DESCRIPTION}, what="publish")
        pub = fab.get(f"{base}/settings") or {}
        pub_src = fab.get(f"{base}/datasources") or {}
        pub_el = fab.get_all(f"{base}/datasources/{ds_id}/elements")
        pub_ds = fab.get(f"{base}/datasources/{ds_id}") or {}
        ok = ((pub.get("aiInstructions") or "").strip() == text and mentions(pub_src, onto)
              and (pub_ds.get("instructions") or "").strip() == ds_text
              and pub_el and all(e.get("isSelected") for e in pub_el))
        fl.say(f"  {'PASS' if ok else 'FAIL'}  published: instructions, ontology source + its instructions, "
               f"{sum(1 for e in pub_el if e.get('isSelected'))}/{len(pub_el)} entity types selected")
        if not ok:
            fl.say(f"        settings={json.dumps(pub)[:300]} datasources={json.dumps(pub_src)[:300]}")
            return 1
    print(json.dumps({"FABRIC_DATA_AGENT_ID": agent}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
