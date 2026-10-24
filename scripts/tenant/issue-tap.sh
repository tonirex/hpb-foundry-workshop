#!/usr/bin/env bash
# issue-tap.sh - Temporary Access Passes (TAP) for the lab accounts (workshop.yaml lab_accounts.sign_in = tap).
#
#   scripts/tenant/issue-tap.sh [env] issue  [--check | --apply] [--count N] [--only N[,N...]] [--prefix P]
#                                            [--lifetime-minutes M] [--start 2026-11-03T08:00:00+08:00]
#                                            [--replace] [--show-secrets]
#   scripts/tenant/issue-tap.sh [env] revoke [--apply] [--count N] [--only N[,N...]]
#   scripts/tenant/issue-tap.sh [env] status [--count N] [--only N[,N...]]
#
# issue (the default) and revoke only PRINT THE PLAN until --apply; `issue --check` is read-only Graph GETs.
# Lifetime and one-time use come from environments.<env>.lab_accounts.tap (480 minutes, reusable); --start issues
# the evening before a pass that is valid from the workshop morning. Pass values go to .azure/<env>/tap-issued.csv
# (gitignored, a secret) and are printed only with --show-secrets. An account that already has an unexpired pass is
# skipped unless --replace. Needs the Authentication Administrator role (Privileged Authentication Administrator for
# admin accounts) AND a Graph token with UserAuthenticationMethod.ReadWrite.All (a plain az CLI token may not have
# it: issue --check says), and the Temporary Access Pass policy enabled for the lab accounts (an Authentication
# Policy Administrator edits it; this script never does). UNVERIFIED: that az login, the portal or Fabric accept a
# pass in this tenant or in Codespaces: test one account first. The guard checks the TENANT only. revoke does not
# disable accounts: use create-lab-users.sh --disable or --delete.
. "$(dirname "$0")/../lib/common.sh"

ENV_ARG=""
SUBCMD=""
PASS=()
while [ $# -gt 0 ]; do
  case "$1" in
    issue|revoke|status) [ -z "$SUBCMD" ] || die "give one subcommand only (issue | revoke | status)"; SUBCMD="$1" ;;
    --count|--only|--prefix|--lifetime-minutes|--start) [ $# -ge 2 ] || die "$1 needs a value"; PASS+=("$1" "$2"); shift ;;
    --check|--apply|--replace|--show-secrets) PASS+=("$1") ;;
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    -*) die "unknown option $1" ;;
    *) ENV_ARG="$1" ;;
  esac
  shift
done

# Entra / Graph work: the tenant must match, a subscription need not. TARGET_GUARD=skip (offline tests) is kept.
[ "${TARGET_GUARD:-}" = "skip" ] || TARGET_GUARD=tenant
load_azd_env "$ENV_ARG"
export AZURE_TENANT_ID="${AZURE_TENANT_ID:-$(cfg "environments.$AZURE_ENV_NAME.tenant_id")}"
[ "$AZURE_TENANT_ID" = "TODO" ] && unset AZURE_TENANT_ID
exec "$PY" "$ROOT/scripts/lib/issue_tap.py" "${SUBCMD:-issue}" --env "$AZURE_ENV_NAME" ${PASS[@]+"${PASS[@]}"}
