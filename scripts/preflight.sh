#!/usr/bin/env bash
# preflight.sh — can this subscription/tenant/region host the LiveWell workshop? (SPEC.md §8.4)
#
#   scripts/preflight.sh [env]          # env = mcaps | sponsor (default: the selected azd env)
#
# READ-ONLY by default: the POSTs discover names and regional offerings. The optional provider registration flag
# needs separate approval. The target guard has already stopped the run if az points
# at another subscription or tenant.
#
# Checks (any FAIL -> exit 1; the quota-request links are printed, but nothing is requested automatically):
#   1 tools + sign-in (az, azd >= 1.34, python + pyyaml; fab for Phase 3)
#   2 subscription/tenant match workshop.yaml; the caller can assign roles (read from ARM, not Graph)
#   3 Sweden Central for everything except the explicitly configured Search region
#   4 resource providers registered (read-only; PREFLIGHT_REGISTER_PROVIDERS=1 registers missing ones)
#   5 Fabric CU quota in region (F2 = 2 CU; any other SKU warns)
#   6 Foundry models (scripts/lib/modelcheck.py): catalogue, lifecycle, eligibility, quota (summed per pool) and the
#     capacity API, reported separately, plus RPM next to TPM and the 30-participant sizing. The inventory is saved
#     under .azure/<env>/ with its timestamp: run preflight again at T-3.
#   7 Azure AI Search Basic creatable (quota + name availability). A capacity failure is reported, never worked around
#     by switching region.
#   8 caller is a Fabric administrator and the required Fabric tenant settings are on (SPEC.md §12.2; cross-geo AI
#     switches are info only: not required inside the EU data boundary)
# Env: PREFLIGHT_SKIP_FABRIC_ADMIN=1 turns check 8 into a warning when a separate Fabric admin has confirmed the
# tenant settings; PREFLIGHT_REGISTER_PROVIDERS=1 lets check 4 register missing providers (a subscription write).
. "$(dirname "$0")/lib/common.sh"

load_azd_env "${1:-}"
ENV="$AZURE_ENV_NAME"
LOCATION="${AZURE_LOCATION:-$(cfg names.location)}"
SEARCH_LOC="$(cfg "environments.$ENV.search_location")"
RG="${AZURE_RESOURCE_GROUP:-$(cfg names.resource_group)}"
FABRIC_BRIDGE="${FABRIC_BRIDGE:-$(cfg modes.fabric_bridge)}"
LINKS=()
TMPD="$(mktempdir)"; trap 'rm -rf "$TMPD"' EXIT

echo "LiveWell preflight — env=$ENV region=$LOCATION search=$SEARCH_LOC rg=$RG fabric_bridge=$FABRIC_BRIDGE (read-only)"
echo

# 1 ----------------------------------------------------------------------------------------------
log "1/8 tools and sign-in"
command -v az >/dev/null && ok "az $(azq version --query '"azure-cli"' -o tsv)" || bad "az CLI not found"
if command -v azd >/dev/null; then
  AZD_VER="$(azd_ version 2>/dev/null | tr -d '\r' | sed -n 's/^azd version \([0-9.]*\).*/\1/p')"
  if pyrun - "$AZD_VER" <<'EOF'
import sys
v = tuple(int(x) for x in (sys.argv[1] or "0").split(".")[:3])
sys.exit(0 if v >= (1, 34, 0) else 1)
EOF
  then ok "azd $AZD_VER"; else bad "azd $AZD_VER < 1.34.0 (upgrade: https://aka.ms/azd/upgrade)"; fi
else
  bad "azd not found (https://aka.ms/azd/install)"
fi
pyrun -c 'import yaml' 2>/dev/null && ok "python + pyyaml ($PY)" || bad "pyyaml missing: pip install -r requirements.txt"
if [ -n "$FAB" ]; then ok "fab CLI ($FAB)"; else warn "fab CLI not found (needed for Phase 3: pip install ms-fabric-cli)"; fi
# The target guard already verified the active session; these are the verified values.
SUB_ID="$AZURE_SUBSCRIPTION_ID"
TENANT_ID="$AZURE_TENANT_ID"
CALLER="$(azq account show --query user.name -o tsv || echo unknown)"
ok "signed in as $CALLER"
azd_ auth login --check-status >/dev/null 2>&1 && ok "azd signed in" || bad "azd not signed in: azd auth login --tenant-id $TENANT_ID"

# 2 ----------------------------------------------------------------------------------------------
log "2/8 subscription, tenant and the caller's roles"
if [ "${TARGET_GUARD:-}" = "skip" ]; then
  warn "target guard skipped (TARGET_GUARD=skip): the subscription and tenant were NOT verified"
else
  ok "subscription $SUB_ID ($(azq account show --query name -o tsv)) and tenant match workshop.yaml environments.$ENV"
fi
# Roles are read from ARM (the caller's token + role assignments), not from Graph: a Graph lookup goes to whichever
# tenant az is signed in to, and a personal or guest account has no matching UPN there.
GOT=0
while IFS=$'\t' read -r status msg; do
  case "$status" in ok) ok "$msg"; GOT=1 ;; bad) bad "$msg"; GOT=1 ;; warn) warn "$msg" ;; *) log "${msg:-$status}" ;; esac
done < <("$PY" "$ROOT/scripts/verify-scope.py" caller --env "$ENV" 2>&1 | tr -d '\r' || true)
[ "$GOT" = 1 ] || bad "could not determine the caller's roles (see the lines above)"

# 3 ----------------------------------------------------------------------------------------------
log "3/8 region (pinned) and live availability"
WANT_LOC="$(cfg names.location)"
if [ "$LOCATION" != "$WANT_LOC" ]; then
  bad "region $LOCATION differs from names.location=$WANT_LOC: only Search has an approved regional exception"
fi
case "$LOCATION" in
  southeastasia|eastus2) bad "region $LOCATION is ruled out: $(cfg "region_matrix.ruled_out.$LOCATION")" ;;
esac
MATRIX="$(cfg_json region_matrix.rows)"
while IFS=$'\t' read -r row value; do
  case "$value" in
    yes) ok "matrix: $row" ;;
    *) bad "matrix: $row not available in $LOCATION" ;;
  esac
done < <(pyrun - "$LOCATION" "$MATRIX" "$SEARCH_LOC" <<'EOF'
import json, sys
loc, rows = sys.argv[1], json.loads(sys.argv[2])
for name, regions in rows.items():
    region = sys.argv[3] if name == "search_agentic_retrieval_semantic_ranker" else loc
    print(f"{name} ({region})\t{regions.get(region, 'no')}")
EOF
)
PROVIDERS=(Microsoft.Fabric Microsoft.CognitiveServices Microsoft.Search Microsoft.App
           Microsoft.ContainerRegistry Microsoft.Storage Microsoft.OperationalInsights Microsoft.Insights
           Microsoft.ManagedIdentity Microsoft.Consumption Microsoft.CostManagement)
for ns in "${PROVIDERS[@]}"; do  # one az process each, in parallel
  az provider show -n "$ns" --subscription "$SUB_ID" -o json >"$TMPD/prov-$ns.json" 2>/dev/null &
done
wait
check_type_region() {  # provider resourceType label [region]
  local locs region="${4:-$LOCATION}"
  locs="$(pyrun -c 'import json,sys
try:
    d=json.load(open(sys.argv[1], encoding="utf-8"))
except (OSError, ValueError):
    d={}
t=[r for r in d.get("resourceTypes",[]) if r["resourceType"]==sys.argv[2]]
print("\n".join(l.lower().replace(" ","") for l in (t[0].get("locations",[]) if t else [])))' "$TMPD/prov-$1.json" "$2")"
  if grep -qx "$region" <<<"$locs"; then ok "$3 offered in $region"; else bad "$3 not offered in $region"; fi
}
check_type_region Microsoft.CognitiveServices accounts "Foundry (AIServices)"
check_type_region Microsoft.Search searchServices "Azure AI Search" "$SEARCH_LOC"
check_type_region Microsoft.Fabric capacities "Fabric capacities"
check_type_region Microsoft.App managedEnvironments "Container Apps"
check_type_region Microsoft.ContainerRegistry registries "Container Registry"

# 4 ----------------------------------------------------------------------------------------------
log "4/8 resource providers (read-only)"
for ns in "${PROVIDERS[@]}"; do
  state="$(pyrun -c 'import json,sys
try:
    print(json.load(open(sys.argv[1], encoding="utf-8")).get("registrationState","Unknown"))
except (OSError, ValueError):
    print("Unknown")' "$TMPD/prov-$ns.json")"
  if [ "$state" = "Registered" ]; then ok "$ns"
  elif [ "${PREFLIGHT_REGISTER_PROVIDERS:-0}" = "1" ]; then
    log "registering $ns (was $state; PREFLIGHT_REGISTER_PROVIDERS=1) ..."
    if az provider register -n "$ns" --subscription "$SUB_ID" --wait >/dev/null 2>&1; then ok "$ns registered now"
    else bad "$ns registration failed (az provider register -n $ns)"; fi
  else
    bad "$ns is $state: register it (az provider register -n $ns --subscription $SUB_ID) after approval, or re-run with PREFLIGHT_REGISTER_PROVIDERS=1"
  fi
done

# 5 ----------------------------------------------------------------------------------------------
log "5/8 Fabric capacity quota"
if [ "$FABRIC_BRIDGE" = "true" ]; then
  FAB_CAP="$(cfg names.fabric_capacity)"
  FAB_SKU="${FABRIC_SKU:-F2}"; NEED_CU="${FAB_SKU#F}"
  [ "$FAB_SKU" = "F2" ] || warn "FABRIC_SKU=$FAB_SKU: the workshop plan is F2 (resizing needs separate approval)"
  USAGE="$(azq rest --method get --subscription "$SUB_ID" --url "https://management.azure.com/subscriptions/$SUB_ID/providers/Microsoft.Fabric/locations/$LOCATION/usages?api-version=2023-11-01" -o json || true)"
  EXISTING_CU=0
  if azq resource show -g "$RG" -n "$FAB_CAP" --subscription "$SUB_ID" --resource-type Microsoft.Fabric/capacities -o none; then
    EXISTING_CU="$(azq resource show -g "$RG" -n "$FAB_CAP" --subscription "$SUB_ID" --resource-type Microsoft.Fabric/capacities --query sku.name -o tsv || echo F2)"
    EXISTING_CU="${EXISTING_CU#F}"
  fi
  read -r CUR LIM <<<"$(pyrun -c 'import json,sys
d=json.loads(sys.stdin.read() or "{}").get("value",[])
cu=[u for u in d if "CapacityUnit" in u.get("name",{}).get("value","") or "CU" in u.get("name",{}).get("value","")]
u=cu[0] if cu else (d[0] if d else {})
print(int(u.get("currentValue",0)), int(u.get("limit",0)))' <<<"$USAGE")"
  FREE=$((LIM - CUR + EXISTING_CU))
  if [ "$FREE" -ge "$NEED_CU" ]; then ok "Fabric CU quota $CUR/$LIM used in $LOCATION ($FAB_SKU needs $NEED_CU)"
  else bad "Fabric CU quota $CUR/$LIM in $LOCATION — $FAB_SKU needs $NEED_CU CU"; LINKS+=("fabric"); fi
  FAB_NAME="$(pyrun - "$ROOT/scripts/lib" "$FAB_CAP" "$LOCATION" "$SUB_ID" "$RG" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from azrest import Api
name, location, sub, rg = sys.argv[2:]
arm = Api("arm", subscription=sub)
base = f"/subscriptions/{sub}"
owned = arm.get(f"{base}/resourceGroups/{rg}/providers/Microsoft.Fabric/capacities/{name}?api-version=2023-11-01",
                ok_404=True)
if owned:
    print("ours")
else:
    result = arm.post(f"{base}/providers/Microsoft.Fabric/locations/{location}/checkNameAvailability?api-version=2023-11-01",
                      {"name": name, "type": "Microsoft.Fabric/capacities"})
    print("available" if result.get("nameAvailable") is True else "unavailable")
PY
)" || FAB_NAME=unknown
  case "$FAB_NAME" in
    available|ours) ok "Fabric capacity name $FAB_CAP: $FAB_NAME" ;;
    unavailable) bad "Fabric capacity name $FAB_CAP is occupied; choose an available names.fabric_capacity before provisioning" ;;
    *) bad "could not verify Fabric capacity name $FAB_CAP (see the error above)" ;;
  esac
else
  warn "FABRIC_BRIDGE=false — Fabric capacity checks skipped"
fi

# 6 ----------------------------------------------------------------------------------------------
log "6/8 Foundry models: catalogue, lifecycle, eligibility, quota and capacity, reported separately"
ACCOUNT="$(cfg names.foundry_account)"
INV="$ROOT/.azure/$ENV/model-inventory-$(date -u +%Y%m%dT%H%MZ).json"
"$PY" "$ROOT/scripts/lib/modelcheck.py" --env "$ENV" --location "$LOCATION" --subscription "$SUB_ID" \
  --rg "$RG" --account "$ACCOUNT" --save "$INV" 2>&1 | tr -d '\r' >"$TMPD/modelcheck.out" || true
GOT=0
while IFS=$'\t' read -r status msg; do
  case "$status" in
    ok) ok "$msg"; GOT=1 ;;
    bad) bad "$msg"; LINKS+=("models"); GOT=1 ;;
    warn) warn "$msg" ;;
    info) printf '  %sinfo%s  %s\n' "$C_DIM" "$C_END" "$msg" ;;
    *) printf '  %s\n' "${msg:-$status}" ;;
  esac
done <"$TMPD/modelcheck.out"
[ "$GOT" = 1 ] || bad "modelcheck produced no result (see the lines above)"
[ -f "$INV" ] && log "inventory record: ${INV#"$ROOT"/} (gitignored). Re-run this preflight at T-3."

# 7 ----------------------------------------------------------------------------------------------
log "7/8 Azure AI Search Basic"
SEARCH="$(cfg names.search_service)"
SEARCH_SKU="${SEARCH_SKU:-basic}"
if [ -n "${SEARCH_LOCATION:-}" ] && [ "$SEARCH_LOCATION" != "$SEARCH_LOC" ]; then
  bad "SEARCH_LOCATION=$SEARCH_LOCATION differs from the approved environments.$ENV.search_location=$SEARCH_LOC; remove the stale env override"
fi
BLOCK_NOTE="$(cfg "region_matrix.capacity_notes.search.$SEARCH_LOC" 2>/dev/null || true)"
if [ -n "$BLOCK_NOTE" ]; then
  bad "new search services in $SEARCH_LOC: $BLOCK_NOTE -> STOP and report; re-test, then clear region_matrix.capacity_notes (never switch region)"
fi
[ "$SEARCH_SKU" != "basic" ] && warn "SEARCH_SKU=$SEARCH_SKU (Basic is the default; serverless is preview)"
warn "Search capacity in $SEARCH_LOC is unproven until a service is created: if provisioning fails with ResourcesForSkuUnavailable, STOP and report it (no automatic region switch, ASSUMPTIONS.md 11.13)"
SQ="$(azq rest --method get --subscription "$SUB_ID" --url "https://management.azure.com/subscriptions/$SUB_ID/providers/Microsoft.Search/locations/$SEARCH_LOC/usages?api-version=2025-05-01" -o json || echo '{}')"
read -r SCUR SLIM <<<"$(pyrun -c 'import json,sys
d=json.loads(sys.stdin.read() or "{}").get("value",[])
b=next((u for u in d if u.get("name",{}).get("value","").lower()=="basic"),{})
print(int(b.get("currentValue",0)), int(b.get("limit",-1)))' <<<"$SQ")"
if [ "$SLIM" -lt 0 ]; then bad "could not read Search quota (usages API)"
elif [ $((SLIM - SCUR)) -ge 1 ] || azq resource show -g "$RG" -n "$SEARCH" --subscription "$SUB_ID" --resource-type Microsoft.Search/searchServices -o none; then
  ok "Search Basic quota $SCUR/$SLIM in $SEARCH_LOC"
else bad "Search Basic quota exhausted ($SCUR/$SLIM)"; LINKS+=("search"); fi
GOT=0
while IFS=$'\t' read -r status msg; do
  case "$status" in ok) ok "$msg"; GOT=1 ;; bad) bad "$msg"; GOT=1 ;; *) log "${msg:-$status}" ;; esac
done < <("$PY" "$ROOT/scripts/lib/searchcheck.py" --env "$ENV" --sku "$SEARCH_SKU" 2>&1 | tr -d '\r' || true)
[ "$GOT" = 1 ] || bad "could not determine Search regional offerings (see above)"
# Both names are global DNS names. An API error is "could not verify" (a warning), never "taken".
AVAIL="$(azq rest --method post --subscription "$SUB_ID" --url "https://management.azure.com/subscriptions/$SUB_ID/providers/Microsoft.Search/checkNameAvailability?api-version=2025-05-01" \
  --body "{\"name\":\"$SEARCH\",\"type\":\"searchServices\"}" --query nameAvailable -o tsv || true)"
case "$AVAIL" in
  true) ok "search name $SEARCH is available" ;;
  false)
    if azq resource show -g "$RG" -n "$SEARCH" --subscription "$SUB_ID" --resource-type Microsoft.Search/searchServices -o none; then ok "search $SEARCH already exists in $RG (ours)"
    else bad "search name $SEARCH is taken: names are global across Azure, so it belongs to another subscription or tenant (probably an earlier workshop). Do not reuse it: change names.search_service in content/config/workshop.yaml"; fi ;;
  *) warn "could not verify search name $SEARCH (checkNameAvailability returned '${AVAIL:-nothing}'): re-run, or check it in the portal before provisioning" ;;
esac
CS_AVAIL="$(azq rest --method post --subscription "$SUB_ID" --url "https://management.azure.com/subscriptions/$SUB_ID/providers/Microsoft.CognitiveServices/checkDomainAvailability?api-version=2025-06-01" \
  --body "{\"subdomainName\":\"$ACCOUNT\",\"type\":\"Microsoft.CognitiveServices/accounts\",\"kind\":\"AIServices\"}" --query isSubdomainAvailable -o tsv || true)"
case "$CS_AVAIL" in
  true) ok "Foundry subdomain $ACCOUNT is available" ;;
  false)
    if azq resource show -g "$RG" -n "$ACCOUNT" --subscription "$SUB_ID" --resource-type Microsoft.CognitiveServices/accounts -o none; then ok "Foundry account $ACCOUNT already exists in $RG (ours)"
    else
      DELETED="$(azq cognitiveservices account list-deleted --subscription "$SUB_ID" --query "[?name=='$ACCOUNT'] | length(@)" -o tsv || echo 0)"
      if [ "${DELETED:-0}" -gt 0 ]; then bad "Foundry account $ACCOUNT is soft-deleted: purging is a destructive step that needs separate approval (az cognitiveservices account purge -l $LOCATION -g $RG -n $ACCOUNT)"
      else bad "Foundry subdomain $ACCOUNT is taken: names are global across Azure, so it belongs to another subscription or tenant (probably an earlier workshop). Do not reuse it: change names.foundry_account in content/config/workshop.yaml"; fi
    fi ;;
  *) warn "could not verify Foundry subdomain $ACCOUNT (checkDomainAvailability returned '${CS_AVAIL:-nothing}'): re-run, or check it in the portal before provisioning" ;;
esac

# 8 ----------------------------------------------------------------------------------------------
log "8/8 Fabric administrator (tenant settings, SPEC.md §12.2)"
if [ "$FABRIC_BRIDGE" = "true" ]; then
  RESP="$(fabric_api GET /v1/admin/tenantsettings || true)"
  if grep -q '"tenantSettings"' <<<"$RESP"; then
    ok "caller is a Fabric administrator"
    printf '%s' "$RESP" >"$TMPD/tenantsettings.json"
    while IFS=$'\t' read -r st msg; do
      case "$st" in ok) ok "$msg" ;; bad) bad "$msg" ;; info) printf '  %sinfo%s  %s\n' "$C_DIM" "$C_END" "$msg" ;; *) warn "$msg" ;; esac
    done < <(
    pyrun - "$TMPD/tenantsettings.json" <<'EOF'
import json, sys
raw = open(sys.argv[1], encoding="utf-8").read()
data = json.loads(raw[raw.index("{"):])
settings = {s.get("settingName", "").lower(): s for s in data.get("tenantSettings", [])}
# settingName values as returned by the admin API (checked against a live tenant 2026-10-23). Required for the labs.
REQUIRED = [
    ("FabricGAWorkloads", "Users can create Fabric items"),
    ("OntologyPreview", "Users can create Ontology (preview) items"),
    ("EnableAOAI", "Users can use Copilot, AI Agents and other AI experiences powered by Azure OpenAI (data agent)"),
    ("CopilotCapacitySetupPermissionSwitch", "Capacities can be designated as Fabric Copilot capacities (data agent)"),
]
# Microsoft Learn (data-agent-tenant-settings): needed only for capacities OUTSIDE the EU data boundary and the US.
# swedencentral is inside it, so an "off" value here is expected (ASSUMPTIONS.md 11.12).
GEO = [
    ("AllowSendAOAIDataToOtherRegions", "Azure OpenAI data processed outside the capacity's region"),
    ("AllowStoreAOAIDataInOtherRegions", "Azure OpenAI data stored outside the capacity's region"),
]
for name, label in REQUIRED:
    s = settings.get(name.lower())
    if s is None:
        print(f"warn\ttenant setting '{label}' ({name}): not returned by the admin API; confirm it in the admin portal")
    elif s.get("enabled"):
        print(f"ok\ttenant setting '{label}': enabled")
    else:
        print(f"bad\ttenant setting '{label}' ({name}) is DISABLED: enable it in the Fabric admin portal (a tenant change that needs approval) and allow up to an hour")
for name, label in GEO:
    s = settings.get(name.lower())
    state = "not returned" if s is None else ("enabled" if s.get("enabled") else "off")
    print(f"info\t{label}: {state}. Not required for a swedencentral capacity (inside the EU data boundary); enable it only if the data agent reports a region error, and only with approval")
print("info\tno separate data-agent creation switch is checked: it is covered by 'Users can create Fabric items'; the first Fabric run proves it")
print("info\tFabric data agents used from Foundry may send responses outside Fabric's compliance boundary (Microsoft Learn): the workshop data is synthetic")
EOF
    )
  else
    CODE="$(sed -n 's/.*"errorCode": *"\([^"]*\)".*/\1/p' <<<"$RESP" | head -1)"
    MSG="could not verify Fabric administrator access (${CODE:-no response}; check the token's tenant, scopes and role)."
    [ "$CODE" = "UserNotLicensed" ] && MSG="$MSG Sign in once at https://app.fabric.microsoft.com as $CALLER to activate the free Fabric licence, then re-run."
    if [ "${PREFLIGHT_SKIP_FABRIC_ADMIN:-0}" = "1" ]; then warn "$MSG (accepted by PREFLIGHT_SKIP_FABRIC_ADMIN)"
    else bad "$MSG Needs the Fabric Administrator role (Entra) — see content/admin/TENANT-BOOTSTRAP.md"; fi
  fi
else
  warn "FABRIC_BRIDGE=false — Fabric admin check skipped"
fi

# -------------------------------------------------------------------------------------------------
if [ "$FAILURES" -gt 0 ]; then
  echo
  echo "Quota / access links (informational: nothing is requested automatically, and no region is switched):"
  echo "  Fabric capacity (CU) quota : https://learn.microsoft.com/fabric/enterprise/fabric-quotas  ->  Azure portal > Quotas > Microsoft Fabric > $LOCATION"
  echo "  Foundry model quota        : https://aka.ms/oai/stuquotarequest  (or Foundry portal > Management center > Quota)"
  echo "  Azure AI Search quota      : https://learn.microsoft.com/azure/search/search-limits-quotas-capacity  ->  Azure portal > Help + support > Service and subscription limits"
  echo "  Fabric admin / licence     : https://app.fabric.microsoft.com  and  content/admin/TENANT-BOOTSTRAP.md"
fi
summary_and_exit
