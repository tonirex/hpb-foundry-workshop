# shellcheck shell=bash
# Shared helpers for scripts/*.sh. Source it:  . "$(dirname "$0")/lib/common.sh"
# Works in Codespaces / Linux / macOS bash and Git Bash on Windows.
set -euo pipefail

# Git Bash on Windows: stop MSYS rewriting "/subscriptions/..." arguments into file paths, and use
# mixed-form paths (C:/...) that both bash and native Windows programs (python.exe, az) understand.
export MSYS_NO_PATHCONV=1
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && (pwd -W 2>/dev/null || pwd))"
SCRIPT_NAME="$(basename "${0%.sh}")"
export PYTHONIOENCODING=utf-8

mktempdir() {
  local d
  d="$(mktemp -d)"
  if command -v cygpath >/dev/null 2>&1; then cygpath -m "$d"; else printf '%s\n' "$d"; fi
}

# Python: prefer the repo venv (has pyyaml), then python3, then python.
if [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
elif [ -x "$ROOT/.venv/Scripts/python.exe" ]; then
  PY="$ROOT/.venv/Scripts/python.exe"
elif python3 -c 'import sys' >/dev/null 2>&1; then
  PY=python3
else
  PY=python
fi

# fab: PATH first (fab.cmd shims are invisible to `command -v fab` in Git Bash), then the repo venv.
if command -v fab >/dev/null 2>&1; then
  FAB=fab
elif command -v fab.cmd >/dev/null 2>&1; then
  FAB=fab.cmd
elif [ -x "$ROOT/.venv/bin/fab" ]; then
  FAB="$ROOT/.venv/bin/fab"
elif [ -x "$ROOT/.venv/Scripts/fab.exe" ]; then
  FAB="$ROOT/.venv/Scripts/fab.exe"
else
  FAB=""
fi

if [ -t 1 ]; then
  C_OK=$'\033[32m'; C_BAD=$'\033[31m'; C_WARN=$'\033[33m'; C_DIM=$'\033[2m'; C_END=$'\033[0m'
else
  C_OK=""; C_BAD=""; C_WARN=""; C_DIM=""; C_END=""
fi
FAILURES=0
WARNINGS=0

log()  { printf '%s[%s]%s %s\n' "$C_DIM" "$SCRIPT_NAME" "$C_END" "$*"; }
ok()   { printf '  %sPASS%s  %s\n' "$C_OK" "$C_END" "$*"; }
bad()  { printf '  %sFAIL%s  %s\n' "$C_BAD" "$C_END" "$*"; FAILURES=$((FAILURES + 1)); }
warn() { printf '  %sWARN%s  %s\n' "$C_WARN" "$C_END" "$*"; WARNINGS=$((WARNINGS + 1)); }
die()  { printf '%s[%s] ERROR:%s %s\n' "$C_BAD" "$SCRIPT_NAME" "$C_END" "$*" >&2; exit 1; }

# az output on Windows can carry CRs; strip them everywhere.
azq() { az "$@" 2>/dev/null | tr -d '\r'; }
pyrun() { "$PY" "$@" | tr -d '\r'; }

# azd with the Foundry-skill user agent set INLINE for this one command (never persisted).
azd_() { AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd "$@"; }

# workshop.yaml lookups (<env> substituted with the active azd env).
cfg()      { "$PY" "$ROOT/scripts/lib/wsconfig.py" get "$1" --env "${AZURE_ENV_NAME:-}" | tr -d '\r'; }
cfg_json() { "$PY" "$ROOT/scripts/lib/wsconfig.py" json "$1" --env "${AZURE_ENV_NAME:-}" | tr -d '\r'; }

# Load .azure/<env>/.env into this shell (export). Optional arg selects the env first.
load_azd_env() {
  if [ -n "${1:-}" ]; then
    azd_ env select "$1" >/dev/null || die "azd env '$1' not found (azd env new $1)"
  fi
  local line key value
  while IFS= read -r line; do
    line="${line%$'\r'}"
    case "$line" in *=*) ;; *) continue ;; esac
    key="${line%%=*}"
    value="${line#*=}"
    value="${value#\"}"; value="${value%\"}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    export "$key=$value"
  done < <(azd_ env get-values 2>/dev/null || true)
  [ -n "${AZURE_ENV_NAME:-}" ] || die "no azd environment selected (azd env new mcaps | azd env select mcaps)"
}

# Fabric REST with the caller's user token. Usage: fabric_api GET /v1/workspaces [body]
fabric_api() {
  local method="$1" path="$2" body="${3:-}"
  local args=(rest --method "$method" --url "https://api.fabric.microsoft.com$path"
              --resource "https://api.fabric.microsoft.com")
  [ -n "${AZURE_SUBSCRIPTION_ID:-}" ] && args+=(--subscription "$AZURE_SUBSCRIPTION_ID")
  [ -n "$body" ] && args+=(--body "$body" --headers "Content-Type=application/json")
  az "${args[@]}" 2>&1 | tr -d '\r'
}

summary_and_exit() {
  echo
  if [ "$FAILURES" -gt 0 ]; then
    printf '%s%s: %d check(s) failed, %d warning(s).%s\n' "$C_BAD" "$SCRIPT_NAME" "$FAILURES" "$WARNINGS" "$C_END"
    exit 1
  fi
  printf '%s%s: all checks passed (%d warning(s)).%s\n' "$C_OK" "$SCRIPT_NAME" "$WARNINGS" "$C_END"
  exit 0
}
