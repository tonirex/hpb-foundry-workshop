#!/usr/bin/env bash
# teardown.sh — remove everything the workshop created in one environment (T+1, SPEC.md §12.1).
#
#   scripts/teardown.sh [env] [--yes] [--pause-only] [--keep-fabric-workspace]
#
#   --pause-only             only suspend the Fabric capacity (overnight / between sessions)
#   --keep-fabric-workspace  skip deleting the Fabric workspace (normally deleted first)
#   --yes                    no confirmation prompt
#
# Order: Fabric workspace (fab rm "<ws>.Workspace" -f, or the Fabric REST API) -> azd down --purge
# (deletes the resource group incl. the Fabric capacity and budget, and purges the soft-deleted
# Foundry account) -> verify nothing is left -> clear Fabric IDs from .azure/<env>/.env.
# Entra lab accounts are NOT deleted here (scripts/tenant/create-lab-users.sh --delete).
. "$(dirname "$0")/lib/common.sh"

ENV_ARG=""; YES=0; PAUSE_ONLY=0; KEEP_WS=0
for arg in "$@"; do
  case "$arg" in
    --yes|-y) YES=1 ;;
    --pause-only) PAUSE_ONLY=1 ;;
    --keep-fabric-workspace) KEEP_WS=1 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
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
LOCATION="${AZURE_LOCATION:-$(cfg names.location)}"
cd "$ROOT"

if [ "$PAUSE_ONLY" = "1" ]; then
  exec bash "$ROOT/scripts/capacity.sh" suspend "$ENV"
fi

if [ "$YES" != "1" ]; then
  echo "This deletes resource group $RG (subscription $SUB), purges $ACCOUNT and deletes the Fabric"
  echo "workspace \"$WS_NAME\". Type the environment name to continue:"
  read -r answer
  [ "$answer" = "$ENV" ] || die "aborted"
fi

# 1 Fabric workspace (items on it stop working once the capacity is gone, so remove them first).
if [ "$KEEP_WS" = "1" ]; then
  warn "keeping Fabric workspace \"$WS_NAME\""
elif [ -n "$FAB" ] && "$FAB" auth status >/dev/null 2>&1; then
  if "$FAB" exists "$WS_NAME.Workspace" 2>/dev/null | tr -d '\r' | grep -qi true; then
    log "fab rm \"$WS_NAME.Workspace\" -f"
    "$FAB" rm "$WS_NAME.Workspace" -f && ok "Fabric workspace deleted" || bad "fab rm failed"
  else
    ok "Fabric workspace \"$WS_NAME\" not present"
  fi
else
  WS_ID="${FABRIC_WORKSPACE_ID:-}"
  if [ -z "$WS_ID" ]; then
    WS_ID="$(fabric_api GET /v1/workspaces | pyrun -c 'import json,sys
try:
    d=json.load(sys.stdin)
except ValueError:
    sys.exit(0)
print(next((w["id"] for w in d.get("value",[]) if w.get("displayName")==sys.argv[1]),""))' "$WS_NAME" || true)"
  fi
  if [ -n "$WS_ID" ]; then
    fabric_api DELETE "/v1/workspaces/$WS_ID" >/dev/null && ok "Fabric workspace $WS_ID deleted (REST)" ||
      bad "could not delete Fabric workspace $WS_ID — delete \"$WS_NAME\" in the Fabric portal"
  else
    warn "Fabric workspace not found or Fabric API unavailable (fab not signed in) — check app.fabric.microsoft.com"
  fi
fi

# 2 Azure resources.
if [ "$(azq group exists -n "$RG" --subscription "$SUB")" = "true" ]; then
  log "azd down --purge --force (≈10 min)"
  azd_ down --purge --force --no-prompt || warn "azd down reported an error — verifying below"
else
  ok "resource group $RG already gone"
fi

# 3 Verify: resource group gone, Foundry account not left soft-deleted, no stray workshop resources.
if [ "$(azq group exists -n "$RG" --subscription "$SUB")" = "true" ]; then
  log "resource group still exists — deleting it"
  az group delete -n "$RG" --subscription "$SUB" --yes && ok "resource group $RG deleted" || bad "az group delete $RG failed"
else
  ok "resource group $RG deleted"
fi
DELETED="$(azq cognitiveservices account list-deleted --subscription "$SUB" --query "[?name=='$ACCOUNT'].name" -o tsv || true)"
if [ -n "$DELETED" ]; then
  log "purging soft-deleted $ACCOUNT"
  az cognitiveservices account purge -n "$ACCOUNT" -g "$RG" -l "$LOCATION" --subscription "$SUB" &&
    ok "$ACCOUNT purged" || bad "purge failed: az cognitiveservices account purge -n $ACCOUNT -g $RG -l $LOCATION"
else
  ok "no soft-deleted Foundry account left"
fi
LEFT="$(azq resource list --subscription "$SUB" --tag workshop=livewell --query "[?tags.env=='$ENV'].id" -o tsv || true)"
if [ -n "$LEFT" ]; then bad "workshop resources still present:"; echo "$LEFT" | sed 's/^/    /'
else ok "no resources tagged workshop=livewell env=$ENV remain"; fi

# 4 Clear runtime IDs that no longer exist (lab pages use names; the next provision rewrites the rest).
# AZURE_AI_ACCOUNT_NAME too: while it is set, Bicep links the guardrail blocklist, which fails on a new account.
for key in FABRIC_WORKSPACE_ID FABRIC_WORKSPACE_URL FABRIC_LAKEHOUSE_ID FABRIC_ONTOLOGY_ID FABRIC_GRAPH_MODEL_ID \
           FABRIC_DATA_AGENT_ID FABRIC_DATA_AGENT_URL FABRIC_IQ_CONNECTION_ID BUDGET_START_DATE AZURE_AI_ACCOUNT_NAME; do
  if [ -n "${!key:-}" ]; then azd_ env set "$key" "" >/dev/null; fi
done
rm -f "$ROOT/content/config/values.md"
summary_and_exit
