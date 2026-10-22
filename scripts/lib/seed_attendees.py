#!/usr/bin/env python3
"""Grant (or revoke) workshop access for attendees. Called by scripts/seed-attendees.sh.

Sources (pick one):
  --lab-accounts          <prefix>01..<prefix><count> @ the tenant's default domain (workshop.yaml)
  --file FILE             one UPN per line (members of the tenant; '#' comments allowed)
  --guests FILE           one email per line -> Entra B2B invitation, then the same grants
  --users UPN[,UPN...]    explicit list (e.g. a facilitator test)

Grants per attendee (idempotent: GET before create; deterministic role-assignment names):
  * workshop.yaml attendee_roles (Foundry User on the project, Search Index Data Reader on the search
    service, Log Analytics Reader on Application Insights, Cognitive Services OpenAI User on the account)
  * MODE=project-per-attendee: a project livewell-<labNN> under the shared Foundry account, Foundry User on it
  * Fabric workspace Viewer when FABRIC_WORKSPACE_ID is set (Viewer = read on every item, incl. the data agent)

--remove revokes the same grants (Entra users and guests are never deleted here). --dry-run prints the plan.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wsconfig  # noqa: E402
from azrest import Api, ApiError  # noqa: E402

RA_API = "api-version=2022-04-01"
NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/tonirex/livewell-foundry-workshop/seed-attendees")


def read_list(path: str) -> list[str]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--lab-accounts", action="store_true")
    src.add_argument("--file")
    src.add_argument("--guests")
    src.add_argument("--users")
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    env = os.environ.get("AZURE_ENV_NAME", "")
    if not env:
        print("[seed-attendees] AZURE_ENV_NAME not set (run via scripts/seed-attendees.sh)")
        return 1
    cfg = wsconfig.load(env)
    sub = os.environ["AZURE_SUBSCRIPTION_ID"]
    rg = os.environ.get("AZURE_RESOURCE_GROUP") or cfg["names"]["resource_group"]
    project_id = os.environ.get("AZURE_AI_PROJECT_ID", "")
    if not project_id:
        print("[seed-attendees] AZURE_AI_PROJECT_ID missing in the azd env (provision first)")
        return 1
    account_id = project_id.split("/projects/")[0]
    prov = f"/subscriptions/{sub}/resourceGroups/{rg}/providers"
    scopes = {
        "project": project_id,
        "account": account_id,
        "search": f"{prov}/Microsoft.Search/searchServices/{os.environ.get('AZURE_SEARCH_SERVICE_NAME') or cfg['names']['search_service']}",
        "appinsights": f"{prov}/Microsoft.Insights/components/{os.environ.get('APPLICATIONINSIGHTS_NAME', '')}",
    }
    mode = os.environ.get("MODE") or cfg["modes"]["project_mode"]
    ws_id = os.environ.get("FABRIC_WORKSPACE_ID", "")

    graph = Api("graph")
    arm = Api("arm")

    # ---- resolve attendees -> (upn, object id)
    lab = cfg["environments"].get(env, {}).get("lab_accounts", {})
    people: list[tuple[str, str]] = []
    if args.guests:
        for email in read_list(args.guests):
            existing = graph.get(f"/v1.0/users?$filter=mail eq '{email}' or otherMails/any(m:m eq '{email}')"
                                 f"&$select=id,userPrincipalName").get("value", [])
            if existing:
                people.append((email, existing[0]["id"]))
            elif args.dry_run or args.remove:
                people.append((email, ""))
            else:
                inv = graph.post("/v1.0/invitations", {
                    "invitedUserEmailAddress": email,
                    "inviteRedirectUrl": "https://ai.azure.com",
                    "sendInvitationMessage": True,
                    "invitedUserMessageInfo": {"customizedMessageBody":
                                               "Invitation to the LiveWell Coach Microsoft Foundry workshop."},
                })
                people.append((email, inv["invitedUser"]["id"]))
                print(f"  invited {email}")
    else:
        if args.users:
            upns = [u.strip() for u in args.users.split(",") if u.strip()]
        elif args.file:
            upns = read_list(args.file)
        else:
            domain = next(d["id"] for d in graph.get("/v1.0/domains")["value"] if d.get("isDefault"))
            prefix, count = lab.get("prefix", "hpb.lab"), int(lab.get("count", 20))
            upns = [f"{prefix}{i:02d}@{domain}" for i in range(1, count + 1)]
        for upn in upns:
            u = graph.get(f"/v1.0/users/{upn}?$select=id", ok_404=True)
            people.append((upn, u["id"] if u else ""))

    missing = [u for u, oid in people if not oid]
    if missing and not args.dry_run:
        print("[seed-attendees] not found in Entra (create them first: scripts/tenant/create-lab-users.sh):")
        for u in missing:
            print(f"    {u}")
        people = [p for p in people if p[1]]
        if not people:
            return 1

    # ---- grants
    role_ids = cfg["rbac_roles"]
    grants = [(r["role"], r["scope"]) for r in cfg["attendee_roles"]]
    if not os.environ.get("APPLICATIONINSIGHTS_NAME"):
        grants = [g for g in grants if g[1] != "appinsights"]

    def role_def(key: str) -> str:
        return f"/subscriptions/{sub}/providers/Microsoft.Authorization/roleDefinitions/{role_ids[key]}"

    existing_cache: dict[str, list] = {}

    def existing(scope: str) -> list:
        if scope not in existing_cache:
            existing_cache[scope] = arm.get_all(f"{scope}/providers/Microsoft.Authorization/roleAssignments"
                                                f"?{RA_API}&$filter=atScope()")
        return existing_cache[scope]

    def grant(scope: str, key: str, oid: str) -> str:
        rd = role_def(key).lower()
        match = [a for a in existing(scope) if a["properties"]["principalId"] == oid
                 and a["properties"]["roleDefinitionId"].lower() == rd]
        if args.remove:
            if not match:
                return "absent"
            if not args.dry_run:
                for a in match:
                    arm.delete(f"{a['id']}?{RA_API}")
            return "removed"
        if match:
            return "exists"
        if args.dry_run:
            return "would add"
        name = uuid.uuid5(NS, f"{scope.lower()}|{oid}|{key}")
        try:
            arm.put(f"{scope}/providers/Microsoft.Authorization/roleAssignments/{name}?{RA_API}", {
                "properties": {"roleDefinitionId": role_def(key), "principalId": oid, "principalType": "User"}})
        except ApiError as e:
            if e.code == "RoleAssignmentExists":
                return "exists"
            if e.code == "PrincipalNotFound":  # new users / guests take a moment to replicate
                import time
                time.sleep(15)
                arm.put(f"{scope}/providers/Microsoft.Authorization/roleAssignments/{name}?{RA_API}", {
                    "properties": {"roleDefinitionId": role_def(key), "principalId": oid, "principalType": "User"}})
            else:
                raise
        return "added"

    def attendee_project(upn: str) -> str:
        short = upn.split("@")[0].replace(".", "-").lower()
        name = f"livewell-{short}"[:32]
        pid = f"{account_id}/projects/{name}"
        api = "api-version=2025-06-01"
        if args.remove:
            if not args.dry_run and arm.get(f"{pid}?{api}", ok_404=True):
                arm.delete(f"{pid}?{api}")
            return pid
        if not arm.get(f"{pid}?{api}", ok_404=True) and not args.dry_run:
            location = os.environ.get("AZURE_LOCATION") or cfg["names"]["location"]
            arm.put(f"{pid}?{api}", {"location": location, "identity": {"type": "SystemAssigned"},
                                     "properties": {"displayName": name,
                                                    "description": f"LiveWell workshop project for {upn}"},
                                     "tags": {"workshop": "livewell", "env": env}})
        return pid

    fabric = None
    fabric_existing: dict[str, str] = {}
    if ws_id:
        try:
            fabric = Api("fabric")
            for ra in fabric.get_all(f"/v1/workspaces/{ws_id}/roleAssignments"):
                fabric_existing[ra["principal"]["id"]] = ra["role"]
        except (ApiError, SystemExit) as e:
            print(f"  WARN  Fabric workspace role assignments unavailable: {e}")
            fabric = None

    def fabric_viewer(oid: str) -> str:
        if not ws_id:
            return "n/a (no workspace yet)"
        if fabric is None:
            return "SKIPPED (Fabric API)"
        role = fabric_existing.get(oid)
        if args.remove:
            if role == "Viewer" and not args.dry_run:
                fabric.delete(f"/v1/workspaces/{ws_id}/roleAssignments/{oid}")
            return "removed" if role == "Viewer" else ("kept " + role if role else "absent")
        if role:
            return f"exists ({role})"
        if args.dry_run:
            return "would add"
        fabric.post(f"/v1/workspaces/{ws_id}/roleAssignments",
                    {"principal": {"id": oid, "type": "User"}, "role": "Viewer"})
        return "added"

    header = ["attendee"] + [f"{k}@{s}" for k, s in grants] + ["fabric viewer"]
    if mode == "project-per-attendee":
        header.insert(1, "own project")
    print("  " + " | ".join(header))
    failures = 0
    for upn, oid in people:
        row = [upn]
        try:
            if mode == "project-per-attendee":
                pid = attendee_project(upn)
                row.append(pid.rsplit("/", 1)[-1])
                if oid:
                    row[-1] += " " + grant(pid, "foundry_user", oid)
            for key, scope_key in grants:
                row.append(grant(scopes[scope_key], key, oid) if oid else "would add (user missing)")
            row.append(fabric_viewer(oid) if oid else "-")
        except ApiError as e:
            failures += 1
            row.append(f"ERROR {e.status} {e.code or e.body[:120]}")
        print("  " + " | ".join(row))
    verb = "revoked" if args.remove else "granted"
    print(f"[seed-attendees] {len(people)} attendee(s) {verb}{' (dry run)' if args.dry_run else ''}; "
          f"{failures} error(s). Role assignments can take up to 5 minutes to apply.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
