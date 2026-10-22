#!/usr/bin/env bash
# seed-attendees.sh — give attendees access to the shared workshop project (SPEC.md §8.4). Idempotent.
#
#   scripts/seed-attendees.sh [env] [--lab-accounts | --file attendees.txt | --guests emails.txt |
#                                    --users upn1,upn2] [--remove] [--dry-run]
#
# Default source: --lab-accounts (<prefix>01..<prefix><count> from workshop.yaml, tenant default domain).
# Grants: Foundry User on the project + Search Index Data Reader + Log Analytics Reader + Cognitive Services
# OpenAI User on the account (workshop.yaml attendee_roles); Fabric workspace Viewer (read on the data agent) once
# FABRIC_WORKSPACE_ID exists — so re-run it after scripts/fabric/deploy.sh. MODE=project-per-attendee also creates
# one project each.
# attendees.txt / attendees*.csv are gitignored: never commit attendee names.
. "$(dirname "$0")/lib/common.sh"

ENV_ARG=""
PASS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --file|--guests|--users) PASS+=("$1" "$2"); shift ;;
    --lab-accounts|--remove|--dry-run) PASS+=("$1") ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    -*) die "unknown option $1" ;;
    *) ENV_ARG="$1" ;;
  esac
  shift
done
load_azd_env "$ENV_ARG"
export AZURE_TENANT_ID="${AZURE_TENANT_ID:-$(cfg "environments.$AZURE_ENV_NAME.tenant_id")}"
[ "$AZURE_TENANT_ID" = "TODO" ] && unset AZURE_TENANT_ID
log "env=$AZURE_ENV_NAME project=${AZURE_AI_PROJECT_NAME:-?} mode=${MODE:-shared-project}"
exec "$PY" "$ROOT/scripts/lib/seed_attendees.py" "${PASS[@]}"
