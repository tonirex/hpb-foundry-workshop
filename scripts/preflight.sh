#!/usr/bin/env bash
# preflight.sh — can this subscription/tenant/region host the LiveWell workshop? (SPEC.md §8.4)
#
#   scripts/preflight.sh [env]          # env = mcaps | sponsor (default: the selected azd env)
#
# Checks (any FAIL -> exit 1 and the quota-request links are printed):
#   1 tools + sign-in (az, azd >= 1.34, python + pyyaml; fab for Phase 3)
#   2 subscription/tenant match workshop.yaml
#   3 region matrix (SPEC.md §8.2) + live region availability for every resource type
#   4 resource providers registered (registers missing ones)
#   5 Fabric CU quota in region (FABRIC_SKU: F2 = 2 CU, F4 = 4 CU)
#   6 Foundry model quota + availability for the three deployments (Global Standard)
#   7 Azure AI Search Basic creatable (quota + name availability)
#   8 caller is a Fabric administrator (tenant settings, SPEC.md §12.2)
# Env: PREFLIGHT_ACCEPT_FALLBACK=1 accepts "unverified" matrix rows; PREFLIGHT_SKIP_FABRIC_ADMIN=1 turns
# check 8 into a warning when a separate Fabric admin has confirmed the tenant settings.
. "$(dirname "$0")/lib/common.sh"

load_azd_env "${1:-}"
ENV="$AZURE_ENV_NAME"
LOCATION="${AZURE_LOCATION:-$(cfg names.location)}"
RG="${AZURE_RESOURCE_GROUP:-$(cfg names.resource_group)}"
FABRIC_BRIDGE="${FABRIC_BRIDGE:-$(cfg modes.fabric_bridge)}"
TPM="$(cfg models.tpm_cap_thousands)"
EMB_TPM="$(cfg models.embedding_tpm_cap_thousands)"
TOOLS_TPM="$(cfg models.tools_tpm_cap_thousands)"
LINKS=()
TMPD="$(mktempdir)"; trap 'rm -rf "$TMPD"' EXIT

echo "LiveWell preflight — env=$ENV region=$LOCATION rg=$RG fabric_bridge=$FABRIC_BRIDGE"
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
ACCOUNT_JSON="$(azq account show -o json || true)"
[ -n "$ACCOUNT_JSON" ] || die "not signed in: az login --tenant <tenant-id>"
SUB_ID="$(azq account show --query id -o tsv)"
TENANT_ID="$(azq account show --query tenantId -o tsv)"
CALLER="$(azq account show --query user.name -o tsv)"
ok "signed in as $CALLER"
azd_ auth login --check-status >/dev/null 2>&1 && ok "azd signed in" || bad "azd not signed in: azd auth login --tenant-id $TENANT_ID"

# 2 ----------------------------------------------------------------------------------------------
log "2/8 subscription and tenant"
WANT_SUB="$(cfg "environments.$ENV.subscription_id" || true)"
WANT_TENANT="$(cfg "environments.$ENV.tenant_id" || true)"
[ -n "${AZURE_SUBSCRIPTION_ID:-}" ] && WANT_SUB="$AZURE_SUBSCRIPTION_ID"
if [ "$WANT_SUB" = "TODO" ] || [ -z "$WANT_SUB" ]; then
  bad "environments.$ENV.subscription_id is TODO in workshop.yaml"
elif [ "$SUB_ID" != "$WANT_SUB" ]; then
  bad "az is on subscription $SUB_ID, expected $WANT_SUB (az account set -s $WANT_SUB)"
else
  ok "subscription matches ($(azq account show --query name -o tsv))"
fi
if [ "$WANT_TENANT" != "TODO" ] && [ -n "$WANT_TENANT" ] && [ "$TENANT_ID" != "$WANT_TENANT" ]; then
  bad "tenant $TENANT_ID != workshop.yaml environments.$ENV.tenant_id"
else
  ok "tenant matches"
fi
# Look the caller up by object ID: a personal Microsoft account signs in as name@outlook.com, but its UPN in the
# tenant is name_outlook.com#EXT#@<tenant>, so --assignee <sign-in name> finds no one.
if [ "$(azq account show --query user.type -o tsv)" = "servicePrincipal" ]; then
  CALLER_ID="$(azq ad sp show --id "$CALLER" --query id -o tsv || true)"
else
  CALLER_ID="$(azq ad signed-in-user show --query id -o tsv || true)"
fi
ROLE_OK="$(azq role assignment list --assignee "${CALLER_ID:-$CALLER}" --scope "/subscriptions/$SUB_ID" --include-inherited \
  --query "[?roleDefinitionName=='Owner' || roleDefinitionName=='User Access Administrator'] | length(@)" -o tsv || echo 0)"
if [ "${ROLE_OK:-0}" -gt 0 ]; then ok "caller can assign roles (Owner / User Access Administrator)"
else bad "caller needs Owner (or Contributor + User Access Administrator) on the subscription for RBAC"; fi

# 3 ----------------------------------------------------------------------------------------------
log "3/8 region matrix (SPEC.md §8.2) and live availability"
case "$LOCATION" in
  southeastasia|eastus2) bad "region $LOCATION is ruled out: $(cfg "region_matrix.ruled_out.$LOCATION")" ;;
esac
MATRIX="$(cfg_json region_matrix.rows)"
while IFS=$'\t' read -r row value; do
  case "$value" in
    yes) ok "matrix: $row" ;;
    unverified)
      if [ "${PREFLIGHT_ACCEPT_FALLBACK:-0}" = "1" ]; then warn "matrix: $row unverified in $LOCATION (accepted by PREFLIGHT_ACCEPT_FALLBACK)"
      else bad "matrix: $row unverified in $LOCATION (re-validate, then PREFLIGHT_ACCEPT_FALLBACK=1)"; fi ;;
    *) bad "matrix: $row not available in $LOCATION" ;;
  esac
done < <(pyrun - "$LOCATION" "$MATRIX" <<'EOF'
import json, sys
loc, rows = sys.argv[1], json.loads(sys.argv[2])
for name, regions in rows.items():
    print(f"{name}\t{regions.get(loc, 'no')}")
EOF
)
warn "portal red teaming is not co-located: $(cfg region_matrix.not_colocated.portal_red_teaming)"
PROVIDERS=(Microsoft.Fabric Microsoft.CognitiveServices Microsoft.Search Microsoft.App
           Microsoft.ContainerRegistry Microsoft.Storage Microsoft.OperationalInsights Microsoft.Insights
           Microsoft.ManagedIdentity Microsoft.Consumption Microsoft.CostManagement)
for ns in "${PROVIDERS[@]}"; do  # one az process each, in parallel
  az provider show -n "$ns" -o json >"$TMPD/prov-$ns.json" 2>/dev/null &
done
wait
check_type_region() {  # provider resourceType label
  local locs
  locs="$(pyrun -c 'import json,sys
try:
    d=json.load(open(sys.argv[1], encoding="utf-8"))
except (OSError, ValueError):
    d={}
t=[r for r in d.get("resourceTypes",[]) if r["resourceType"]==sys.argv[2]]
print("\n".join(l.lower().replace(" ","") for l in (t[0].get("locations",[]) if t else [])))' "$TMPD/prov-$1.json" "$2")"
  if grep -qx "$LOCATION" <<<"$locs"; then ok "$3 offered in $LOCATION"; else bad "$3 not offered in $LOCATION"; fi
}
check_type_region Microsoft.CognitiveServices accounts "Foundry (AIServices)"
check_type_region Microsoft.Search searchServices "Azure AI Search"
check_type_region Microsoft.Fabric capacities "Fabric capacities"
check_type_region Microsoft.App managedEnvironments "Container Apps"
check_type_region Microsoft.ContainerRegistry registries "Container Registry"

# 4 ----------------------------------------------------------------------------------------------
log "4/8 resource providers"
for ns in "${PROVIDERS[@]}"; do
  state="$(pyrun -c 'import json,sys
try:
    print(json.load(open(sys.argv[1], encoding="utf-8")).get("registrationState","Unknown"))
except (OSError, ValueError):
    print("Unknown")' "$TMPD/prov-$ns.json")"
  if [ "$state" = "Registered" ]; then ok "$ns"
  else
    log "registering $ns (was $state) ..."
    if az provider register -n "$ns" --wait >/dev/null 2>&1; then ok "$ns registered now"
    else bad "$ns registration failed (az provider register -n $ns)"; fi
  fi
done

# 5 ----------------------------------------------------------------------------------------------
log "5/8 Fabric capacity quota"
if [ "$FABRIC_BRIDGE" = "true" ]; then
  FAB_CAP="$(cfg names.fabric_capacity)"
  FAB_SKU="${FABRIC_SKU:-F2}"; NEED_CU="${FAB_SKU#F}"
  USAGE="$(azq rest --method get --url "https://management.azure.com/subscriptions/$SUB_ID/providers/Microsoft.Fabric/locations/$LOCATION/usages?api-version=2023-11-01" -o json || true)"
  EXISTING_CU=0
  if azq resource show -g "$RG" -n "$FAB_CAP" --resource-type Microsoft.Fabric/capacities -o none; then
    EXISTING_CU="$(azq resource show -g "$RG" -n "$FAB_CAP" --resource-type Microsoft.Fabric/capacities --query sku.name -o tsv || echo F2)"
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
else
  warn "FABRIC_BRIDGE=false — Fabric capacity checks skipped"
fi

# 6 ----------------------------------------------------------------------------------------------
log "6/8 Foundry model quota and availability (Global Standard, default ${TPM}K / tools ${TOOLS_TPM}K / embeddings ${EMB_TPM}K TPM)"
USAGES="$(azq cognitiveservices usage list -l "$LOCATION" -o json || echo '[]')"
MODELS="$(azq cognitiveservices model list -l "$LOCATION" -o json || echo '[]')"
ACCOUNT="$(cfg names.foundry_account)"
DEPLOYED="$(azq cognitiveservices account deployment list -g "$RG" -n "$ACCOUNT" -o json || echo '[]')"
QNAMES="$(cfg_json models.quota_usage_names)"
printf '%s' "$USAGES" >"$TMPD/usages.json"; printf '%s' "$MODELS" >"$TMPD/models.json"; printf '%s' "$DEPLOYED" >"$TMPD/deployed.json"
while IFS=$'\t' read -r status msg; do
  if [ "$status" = "ok" ]; then ok "$msg"; else bad "$msg"; LINKS+=("models"); fi
done < <(pyrun - "$QNAMES" "$TMPD/usages.json" "$TMPD/models.json" "$TMPD/deployed.json" \
  "$(cfg models.default)=$TPM" "$(cfg models.tools)=$TOOLS_TPM" \
  "$(cfg models.embeddings)=$EMB_TPM" <<'EOF'
import json, sys
qnames = json.loads(sys.argv[1])
load = lambda p: json.loads(open(p, encoding="utf-8").read() or "[]")
usages, models, deployed = load(sys.argv[2]), load(sys.argv[3]), load(sys.argv[4])
wanted = [(a.rsplit("=", 1)[0], int(a.rsplit("=", 1)[1])) for a in sys.argv[5:]]
mine = {d["name"]: d.get("sku", {}).get("capacity", 0) for d in deployed}
for m, need in wanted:
    offers = [x for x in models if x.get("model", {}).get("name") == m
              and any(s.get("name") == "GlobalStandard" for s in x["model"].get("skus", []))]
    ga = [x for x in offers if x["model"].get("lifecycleStatus") in ("GenerallyAvailable", "Legacy", "Stable")]
    if not offers:
        print(f"bad\t{m}: not offered as GlobalStandard in region"); continue
    q = next((u for u in usages if u["name"]["value"] == f"OpenAI.GlobalStandard.{qnames.get(m, m)}"), None)
    if q is None:
        print(f"bad\t{m}: no GlobalStandard quota entry"); continue
    free = q["limit"] - q["currentValue"] + mine.get(m, 0)
    versions = ",".join(sorted({x["model"]["version"] for x in (ga or offers)}))
    if free >= need:
        print(f"ok\t{m} ({versions}): quota {int(q['currentValue'])}/{int(q['limit'])}K used, {int(free)}K free")
    else:
        print(f"bad\t{m}: only {int(free)}K TPM free (need {need}K)")
EOF
)

# 7 ----------------------------------------------------------------------------------------------
log "7/8 Azure AI Search Basic"
SEARCH="$(cfg names.search_service)"
SEARCH_SKU="${SEARCH_SKU:-basic}"
SEARCH_LOC="${SEARCH_LOCATION:-$LOCATION}"
BLOCK_NOTE="$(cfg "region_matrix.capacity_notes.search.$SEARCH_LOC" 2>/dev/null || true)"
if [ -n "$BLOCK_NOTE" ]; then
  bad "new search services in $SEARCH_LOC: $BLOCK_NOTE -> azd env set SEARCH_LOCATION <eu-region> (see ADMIN-SETUP.md), or re-test and clear region_matrix.capacity_notes"
fi
if [ "$SEARCH_LOC" != "$LOCATION" ]; then
  warn "search service in $SEARCH_LOC, everything else in $LOCATION (one-region exception for search capacity)"
fi
[ "$SEARCH_SKU" != "basic" ] && warn "SEARCH_SKU=$SEARCH_SKU (Basic is the default)"
SQ="$(azq rest --method get --url "https://management.azure.com/subscriptions/$SUB_ID/providers/Microsoft.Search/locations/$SEARCH_LOC/usages?api-version=2025-05-01" -o json || echo '{}')"
read -r SCUR SLIM <<<"$(pyrun -c 'import json,sys
d=json.loads(sys.stdin.read() or "{}").get("value",[])
b=next((u for u in d if u.get("name",{}).get("value","").lower()=="basic"),{})
print(int(b.get("currentValue",0)), int(b.get("limit",-1)))' <<<"$SQ")"
if [ "$SLIM" -lt 0 ]; then warn "could not read Search quota (usages API)"
elif [ $((SLIM - SCUR)) -ge 1 ] || azq resource show -g "$RG" -n "$SEARCH" --resource-type Microsoft.Search/searchServices -o none; then
  ok "Search Basic quota $SCUR/$SLIM in $SEARCH_LOC"
else bad "Search Basic quota exhausted ($SCUR/$SLIM)"; LINKS+=("search"); fi
AVAIL="$(azq rest --method post --url "https://management.azure.com/subscriptions/$SUB_ID/providers/Microsoft.Search/checkNameAvailability?api-version=2025-05-01" \
  --body "{\"name\":\"$SEARCH\",\"type\":\"searchServices\"}" --query nameAvailable -o tsv || echo unknown)"
if [ "$AVAIL" = "true" ]; then ok "search name $SEARCH available"
elif azq resource show -g "$RG" -n "$SEARCH" --resource-type Microsoft.Search/searchServices -o none; then ok "search $SEARCH already ours"
else bad "search name $SEARCH is taken by someone else (change names.search_service)"; fi
CS_AVAIL="$(azq rest --method post --url "https://management.azure.com/subscriptions/$SUB_ID/providers/Microsoft.CognitiveServices/checkDomainAvailability?api-version=2025-06-01" \
  --body "{\"subdomainName\":\"$ACCOUNT\",\"type\":\"Microsoft.CognitiveServices/accounts\",\"kind\":\"AIServices\"}" --query isSubdomainAvailable -o tsv || echo unknown)"
if [ "$CS_AVAIL" = "true" ]; then ok "Foundry subdomain $ACCOUNT available"
elif azq resource show -g "$RG" -n "$ACCOUNT" --resource-type Microsoft.CognitiveServices/accounts -o none; then ok "Foundry account $ACCOUNT already ours"
else
  DELETED="$(azq cognitiveservices account list-deleted --query "[?name=='$ACCOUNT'] | length(@)" -o tsv || echo 0)"
  if [ "${DELETED:-0}" -gt 0 ]; then bad "Foundry account $ACCOUNT is soft-deleted: az cognitiveservices account purge -l $LOCATION -g $RG -n $ACCOUNT"
  else bad "Foundry subdomain $ACCOUNT is taken (change names.foundry_account)"; fi
fi

# 8 ----------------------------------------------------------------------------------------------
log "8/8 Fabric administrator (tenant settings, SPEC.md §12.2)"
if [ "$FABRIC_BRIDGE" = "true" ]; then
  RESP="$(fabric_api GET /v1/admin/tenantsettings || true)"
  if grep -q '"tenantSettings"' <<<"$RESP"; then
    ok "caller is a Fabric administrator"
    printf '%s' "$RESP" >"$TMPD/tenantsettings.json"
    while IFS=$'\t' read -r st msg; do if [ "$st" = ok ]; then ok "$msg"; else warn "$msg"; fi; done < <(
    pyrun - "$TMPD/tenantsettings.json" <<'EOF'
import json, sys
raw = open(sys.argv[1], encoding="utf-8").read()
data = json.loads(raw[raw.index("{"):])
want = {
    "Users can create Fabric items": ("FabricGAWorkloads", "create"),
    "Users can create Ontology (preview) items": ("ontology", None),
    "Fabric data agent": ("dataagent", "aiskill"),
    "Copilot / Azure OpenAI features": ("AISkillArtifactTenantSwitch", "CopilotTenantSwitch"),
    "Cross-geo processing for AI": ("AllowGeoProcessing", "crossgeoprocessing"),
    "Cross-geo storing for AI": ("AllowGeoStorage", "crossgeostoring"),
    "Service principals can use Fabric APIs": ("ServicePrincipalAccessGlobalAPIs", "serviceprincipal"),
}
settings = data.get("tenantSettings", [])
for label, keys in want.items():
    hits = [s for s in settings if any(k and (k.lower() in s.get("settingName", "").lower()
            or k.lower() in s.get("title", "").lower()) for k in keys)]
    if not hits:
        print(f"warn\ttenant setting '{label}': not found by name — confirm in the admin portal"); continue
    on = any(h.get("enabled") for h in hits)
    print(f"{'ok' if on else 'warn'}\ttenant setting '{label}': {'enabled' if on else 'DISABLED'}")
EOF
    )
  else
    CODE="$(sed -n 's/.*"errorCode": *"\([^"]*\)".*/\1/p' <<<"$RESP" | head -1)"
    MSG="caller is not a Fabric administrator (${CODE:-no response})."
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
  echo "Quota / access request links:"
  echo "  Fabric capacity (CU) quota : https://learn.microsoft.com/fabric/enterprise/fabric-quotas  ->  Azure portal > Quotas > Microsoft Fabric > $LOCATION"
  echo "  Foundry model quota        : https://aka.ms/oai/stuquotarequest  (or Foundry portal > Management center > Quota)"
  echo "  Azure AI Search quota      : https://learn.microsoft.com/azure/search/search-limits-quotas-capacity  ->  Azure portal > Help + support > Service and subscription limits"
  echo "  Fabric admin / licence     : https://app.fabric.microsoft.com  and  content/admin/TENANT-BOOTSTRAP.md"
fi
summary_and_exit
