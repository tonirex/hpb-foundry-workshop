#!/usr/bin/env bash
# teardown.sh — remove what the workshop created in ONE environment (T+1, SPEC.md §12.1).
# PLAN ONLY unless --yes: without it nothing is changed and the exact steps are listed.
#
#   scripts/teardown.sh [env]                              plan: lists what would be removed, changes nothing
#   scripts/teardown.sh [env] --yes [--with-identity] [--keep-fabric-workspace]
#   scripts/teardown.sh [env] --pause-only                 only suspend the Fabric capacity (between sessions)
#
#   --yes                    execute the plan (no further prompt: pass it only after the teardown is approved)
#   --with-identity          also revoke TAPs and delete the lab accounts (and the break-glass account if it exists):
#                            tenant-level Entra changes, run FIRST so no issued credential outlives the workshop
#   --keep-fabric-workspace  do not delete the Fabric workspace (it is orphaned when the capacity goes)
#
# With --yes the order is: 0 manifest (ids, no secrets) -> 1 identity (only --with-identity) -> 2 Fabric workspace,
# deleted BY ID after checking it sits on the workshop capacity -> 3 azd down --purge, then verify: group gone, our
# soft-deleted Foundry account purged, nothing tagged workshop/env left, no platform-managed group left -> 4 clear
# runtime ids. EVERY step stops the run on failure: nothing is skipped silently and a failed step is never reported
# as done. Deleting the resource group alone is NOT complete cleanup: Entra accounts / TAPs and Fabric workspace
# items live outside it (content/admin/HPB-DELIVERY-RUNBOOK.md, "Teardown").
. "$(dirname "$0")/lib/common.sh"

ENV_ARG=""; YES=0; PAUSE_ONLY=0; KEEP_WS=0; WITH_ID=0
for arg in "$@"; do
  case "$arg" in
    --yes|-y) YES=1 ;;
    --pause-only) PAUSE_ONLY=1 ;;
    --keep-fabric-workspace) KEEP_WS=1 ;;
    --with-identity) WITH_ID=1 ;;
    -h|--help) sed -n '2,23p' "$0"; exit 0 ;;
    -*) die "unknown option $arg" ;;
    *) ENV_ARG="$arg" ;;
  esac
done
load_azd_env "$ENV_ARG"
ENV="$AZURE_ENV_NAME"
SUB="${AZURE_SUBSCRIPTION_ID:?}"
RG="${AZURE_RESOURCE_GROUP:-$(cfg names.resource_group)}"
ACCOUNT="$(cfg names.foundry_account)"
WS_NAME="$(cfg names.fabric_workspace)"
CAP_NAME="$(cfg names.fabric_capacity)"
LOCATION="${AZURE_LOCATION:-$(cfg names.location)}"
cd "$ROOT"

if [ "$PAUSE_ONLY" = "1" ]; then
  exec bash "$ROOT/scripts/capacity.sh" suspend "$ENV"
fi

fabric_found() { "$PY" "$ROOT/scripts/lib/fabric_ws.py" find --env "$ENV" 2>&1 | tr -d '\r' || true; }
tsv_ok() { [ -z "$1" ] || printf '%s\n' "$1" | awk -F'\t' 'NF != 3 { exit 1 }'; }

# -- discover (read-only) ---------------------------------------------------------------------------------
RG_EXISTS="$(azq group exists -n "$RG" --subscription "$SUB" || echo unknown)"
N_RES="-"
[ "$RG_EXISTS" = "true" ] && N_RES="$(azq resource list -g "$RG" --subscription "$SUB" --query 'length(@)' -o tsv || echo '?')"
FOUND="$(fabric_found)"
tsv_ok "$FOUND" || { warn "could not look up the Fabric workspaces: $FOUND"; FOUND=""; }
N_WS="$(printf '%s\n' "$FOUND" | grep -c . || true)"
LAB_ROWS=0; TAP_ROWS=0
[ -f "$ROOT/.azure/$ENV/lab-accounts.csv" ] && LAB_ROWS="$(( $(wc -l <"$ROOT/.azure/$ENV/lab-accounts.csv") - 1 ))"
[ -f "$ROOT/.azure/$ENV/tap-issued.csv" ] && TAP_ROWS="$(( $(wc -l <"$ROOT/.azure/$ENV/tap-issued.csv") - 1 ))"

echo "LiveWell teardown — env=$ENV subscription=$SUB"
echo "  Azure   : resource group $RG exists=$RG_EXISTS ($N_RES resources); Foundry account $ACCOUNT is purged after the delete"
echo "  Fabric  : $N_WS workspace(s) named \"$WS_NAME\" (capacity $CAP_NAME is deleted with the group)"
[ -n "$FOUND" ] && printf '%s\n' "$FOUND" | awk -F'\t' '{ printf "            id %s  capacity %s  -> %s\n", $1, $2, $3 }'
echo "  Entra   : lab accounts and TAPs are tenant-level, NOT in the group. Local records: $LAB_ROWS lab account row(s), $TAP_ROWS TAP row(s)"
if [ "$WITH_ID" = "1" ]; then
  echo "            --with-identity: scripts/tenant/issue-tap.sh $ENV revoke --apply ; scripts/tenant/create-lab-users.sh $ENV --delete"
else
  echo "            NOT touched by this run. Do it separately: scripts/tenant/issue-tap.sh $ENV revoke --apply ; scripts/tenant/create-lab-users.sh $ENV --disable|--delete"
fi
echo "  Not removed by anyone: subscription quota, resource-provider registrations, other resource groups."

if [ "$YES" != "1" ]; then
  echo
  echo "PLAN ONLY: nothing was changed. Re-run with --yes after the teardown has been approved."
  exit 0
fi
echo

# 0 manifest -------------------------------------------------------------------------------------------------
if [ "$RG_EXISTS" = "true" ]; then
  log "0/4 manifest (ids only, no secrets)"
  "$PY" "$ROOT/scripts/verify-scope.py" manifest --env "$ENV" | tr -d '\r' || die "could not write the manifest: stopping before anything is deleted"
else
  ok "0/4 resource group already gone: no manifest to take"
fi

# 1 identity -------------------------------------------------------------------------------------------------
if [ "$WITH_ID" = "1" ]; then
  log "1/4 identity: revoke TAPs, delete lab accounts"
  bash "$ROOT/scripts/tenant/issue-tap.sh" "$ENV" revoke --apply || die "TAP revocation failed: stopping; fix it, then re-run (the run is idempotent)"
  bash "$ROOT/scripts/tenant/create-lab-users.sh" "$ENV" --delete || die "deleting the lab accounts failed: stopping"
  rm -f "$ROOT/.azure/$ENV/tap-issued.csv" "$ROOT/.azure/$ENV/lab-accounts.csv" && ok "local TAP and lab-account records removed"
else
  warn "1/4 identity skipped: lab accounts, TAPs and any break-glass account still exist (see the runbook)"
fi

# 2 Fabric workspace (by id, only if it sits on the workshop capacity) ---------------------------------------
log "2/4 Fabric workspace"
if [ "$KEEP_WS" = "1" ]; then
  warn "keeping Fabric workspace \"$WS_NAME\": it is orphaned (no capacity) once the group is deleted"
elif [ "$N_WS" -eq 0 ]; then
  ok "no Fabric workspace named \"$WS_NAME\""
elif [ "$N_WS" -gt 1 ]; then
  die "$N_WS Fabric workspaces are named \"$WS_NAME\": ambiguous, nothing deleted. Resolve in the Fabric portal, then re-run"
else
  WS_ID="$(printf '%s\n' "$FOUND" | cut -f1)"
  FORCE=()
  [ "${FABRIC_FORCE_DELETE_WORKSPACE_ID:-}" = "$WS_ID" ] && FORCE=(--force)
  "$PY" "$ROOT/scripts/lib/fabric_ws.py" delete --env "$ENV" --id "$WS_ID" ${FORCE[@]+"${FORCE[@]}"} | tr -d '\r' ||
    die "Fabric workspace $WS_ID was not deleted: stopping so the capacity is not removed from under it"
  ok "Fabric workspace $WS_ID deleted"
fi

# 3 Azure resources, then verify ------------------------------------------------------------------------------
log "3/4 Azure: resource group $RG"
if [ "$(azq group exists -n "$RG" --subscription "$SUB")" = "true" ]; then
  log "azd down --purge --force (≈10 min)"
  azd_ down --purge --force --no-prompt || warn "azd down reported an error: checking, then falling back to az group delete"
fi
if [ "$(azq group exists -n "$RG" --subscription "$SUB")" = "true" ]; then
  log "resource group still exists: az group delete"
  az group delete -n "$RG" --subscription "$SUB" --yes || die "az group delete $RG failed: the group is NOT deleted"
fi
[ "$(azq group exists -n "$RG" --subscription "$SUB")" = "true" ] && die "resource group $RG still exists"
ok "resource group $RG is gone"

DELETED="$(azq cognitiveservices account list-deleted --subscription "$SUB" --query "[?name=='$ACCOUNT'].name" -o tsv || true)"
if [ -n "$DELETED" ]; then
  log "purging our soft-deleted $ACCOUNT (no other account is touched)"
  az cognitiveservices account purge -n "$ACCOUNT" -g "$RG" -l "$LOCATION" --subscription "$SUB" ||
    die "purge of $ACCOUNT failed: az cognitiveservices account purge -n $ACCOUNT -g $RG -l $LOCATION --subscription $SUB"
  ok "$ACCOUNT purged"
else
  ok "no soft-deleted $ACCOUNT left"
fi
LEFT="$(azq resource list --subscription "$SUB" --tag workshop=livewell --query "[?tags.\"azd-env-name\"=='$ENV'].id" -o tsv || true)"
if [ -n "$LEFT" ]; then echo "$LEFT" | sed 's/^/    /'; die "workshop resources are still present (listed above)"; fi
ok "no resource tagged workshop=livewell azd-env-name=$ENV remains in the subscription"
MANAGED="$(azq group list --subscription "$SUB" --query "[?starts_with(name,'ME_') || starts_with(name,'MC_')].name" -o tsv | grep -i "$ENV" || true)"
if [ -n "$MANAGED" ]; then warn "platform-managed resource group(s) still present (they go with the Container Apps environment; re-check later): $MANAGED"
else ok "no platform-managed resource group left for this environment"; fi
AFTER="$(fabric_found)"
if [ -z "$AFTER" ]; then ok "no Fabric workspace named \"$WS_NAME\" remains"
elif [ "$KEEP_WS" = "1" ]; then warn "Fabric workspace kept as requested"
else die "a Fabric workspace named \"$WS_NAME\" still exists"; fi

# 4 Clear runtime IDs that no longer exist (lab pages use names; the next provision rewrites the rest).
# AZURE_AI_ACCOUNT_NAME too: while it is set, Bicep links the guardrail blocklist, which fails on a new account.
log "4/4 clear runtime ids from the azd env"
for key in FABRIC_WORKSPACE_ID FABRIC_WORKSPACE_URL FABRIC_LAKEHOUSE_ID FABRIC_ONTOLOGY_ID FABRIC_GRAPH_MODEL_ID \
           FABRIC_DATA_AGENT_ID FABRIC_DATA_AGENT_URL FABRIC_IQ_CONNECTION_ID BUDGET_START_DATE AZURE_AI_ACCOUNT_NAME; do
  if [ -n "${!key:-}" ]; then azd_ env set "$key" "" >/dev/null; fi
done
rm -f "$ROOT/content/config/values.md"
echo
if [ "$WITH_ID" != "1" ]; then
  warn "NOT cleaned by this run: Entra lab accounts, TAPs, any break-glass account, and the local secret files (.azure/$ENV/tap-issued.csv, lab-accounts.csv, printed sign-in cards)"
fi
summary_and_exit
