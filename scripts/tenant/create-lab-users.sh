#!/usr/bin/env bash
# create-lab-users.sh - cloud-only lab accounts (SPEC.md 12.2): hpb.lab01..hpb.lab30 for mcaps. Idempotent.
#
#   scripts/tenant/create-lab-users.sh [env] [--count N] [--dry-run] [--break-glass] [--reset-passwords]
#                                            [--disable | --delete]
#
# How people sign in comes from workshop.yaml environments.<env>.lab_accounts.sign_in:
#   tap       (mcaps)   Temporary Access Pass. Every account gets a random password that is never printed or saved, so
#                       the passes from scripts/tenant/issue-tap.sh are the way in (no Authenticator registration).
#                       .azure/<env>/lab-accounts.csv (gitignored) lists upn,display_name only.
#   password  (sponsor) a temporary password per account in .azure/<env>/lab-accounts.csv (gitignored, never printed);
#                       --reset-passwords issues new ones. Entra security defaults add Authenticator at first sign-in.
# --break-glass  OPT-IN: also creates hpb.breakglass, a STANDING Global Administrator (needs Privileged Role
#                Administrator). Delete it at teardown (--delete). --no-break-glass is accepted and ignored.
# --disable      sets accountEnabled=false on the lab accounts; nothing is deleted.
# --delete       deletes the lab accounts and the break-glass account if it exists.
# Needs User Administrator in the tenant of <env>. Names, count and usage location (SG) come from workshop.yaml
# environments.<env>.lab_accounts.
. "$(dirname "$0")/../lib/common.sh"

ENV_ARG=""
PASS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --count) PASS+=("$1" "$2"); shift ;;
    --reset-passwords|--break-glass|--no-break-glass|--disable|--delete|--dry-run) PASS+=("$1") ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    -*) die "unknown option $1" ;;
    *) ENV_ARG="$1" ;;
  esac
  shift
done
load_azd_env "$ENV_ARG"
export AZURE_TENANT_ID="${AZURE_TENANT_ID:-$(cfg "environments.$AZURE_ENV_NAME.tenant_id")}"
[ "$AZURE_TENANT_ID" = "TODO" ] && unset AZURE_TENANT_ID
exec "$PY" "$ROOT/scripts/lib/lab_users.py" "${PASS[@]}"
