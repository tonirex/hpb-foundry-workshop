#!/usr/bin/env python3
"""Fabric workspace lookup and ownership-checked deletion for the workshop (scripts/teardown.sh, 10-workspace.sh).

  python scripts/lib/fabric_ws.py find   --env mcaps            one line per workspace named names.fabric_workspace:
                                                                id <TAB> capacityId <TAB> ours|foreign|unassigned
  python scripts/lib/fabric_ws.py delete --env mcaps --id <workspace-id> [--force]

A workspace is "ours" only when it is assigned to the workshop Fabric capacity (names.fabric_capacity, the F2 in the
workshop resource group). A workspace with the right NAME on another capacity, or on none, may belong to an earlier
workshop: `delete` refuses it without --force, and 10-workspace.sh will not adopt it without FABRIC_ADOPT_WORKSPACE_ID.
Deletion is by ID, never by name, and is verified afterwards. Standard library plus scripts/lib; ASCII output.

Exit: 0 ok, 1 refused or failed, 2 ambiguous (more than one workspace has the name).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wsconfig  # noqa: E402


def classify(workspaces: list[dict], capacities: list[dict], ws_name: str, cap_name: str) -> list[dict]:
    """Workspaces named ws_name with an ownership verdict against the workshop capacity (pure; unit-tested)."""
    cap = next((c for c in capacities if str(c.get("displayName", "")).lower() == cap_name.lower()), None)
    out = []
    for w in workspaces:
        if w.get("displayName") != ws_name:
            continue
        cid = str(w.get("capacityId") or "")
        if not cid:
            verdict = "unassigned"
        elif cap and cid.lower() == str(cap.get("id", "")).lower():
            verdict = "ours"
        else:
            verdict = "foreign"
        out.append({"id": w.get("id"), "capacityId": cid, "verdict": verdict})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["find", "delete"])
    ap.add_argument("--env", required=True)
    ap.add_argument("--id", help="workspace id (delete)")
    ap.add_argument("--force", action="store_true", help="delete a workspace that is not on the workshop capacity")
    args = ap.parse_args()

    from azrest import Api, ApiError

    cfg = wsconfig.load(args.env)
    names = cfg["names"]
    fabric = Api("fabric")
    found = classify(fabric.get_all("/v1/workspaces"), fabric.get_all("/v1/capacities"),
                     names["fabric_workspace"], names["fabric_capacity"])
    if args.mode == "find":
        for w in found:
            print(f"{w['id']}\t{w['capacityId'] or '-'}\t{w['verdict']}")
        return 2 if len(found) > 1 else 0

    if not args.id:
        print("delete needs --id (deletion is by ID, never by name)")
        return 1
    hit = [w for w in found if str(w["id"]).lower() == args.id.lower()]
    if not hit:
        print(f"no workspace named '{names['fabric_workspace']}' has id {args.id}: nothing deleted")
        return 1
    if hit[0]["verdict"] != "ours" and not args.force:
        print(f"workspace {args.id} is {hit[0]['verdict']} (not assigned to the workshop capacity {names['fabric_capacity']}): "
              "it may belong to an earlier workshop. Nothing deleted; pass --force only after checking its owner")
        return 1
    try:
        fabric.delete(f"/v1/workspaces/{args.id}")
    except ApiError as e:
        print(f"Fabric refused the delete ({e.status} {e.code or ''}): the identity needs workspace Admin")
        return 1
    gone = fabric.get(f"/v1/workspaces/{args.id}", ok_404=True) is None
    print(("deleted workspace " + args.id) if gone else f"workspace {args.id} still exists after the delete call")
    return 0 if gone else 1


if __name__ == "__main__":
    sys.exit(main())
