#!/usr/bin/env bash
# cost-guardrails.sh — assert the SPEC.md §13 cost controls on a provisioned environment. Read-only
# unless --pause-fabric is given.
#
#   scripts/cost-guardrails.sh [env] [--max-usd N] [--pause-fabric]
#
# Checks: budget exists with alerts at the workshop.yaml thresholds (150/300 USD) · model deployments
# Global Standard, capacity <= TPM cap, no PTU / partner models · exactly one search service, never
# Standard tier, semantic + agentic-retrieval plans on Free · Fabric capacity F2 or F4 (FABRIC_SKU; state
# reported; Active = billing) · MCP and Lab 4 DevUI app replicas · Log Analytics daily cap · no Bing grounding connection ·
# every resource tagged workshop=livewell + env=<env> · month-to-date cost for the resource group
# (--max-usd fails the run above N).
. "$(dirname "$0")/lib/common.sh"

ENV_ARG=""; MAX_USD=""; PAUSE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --max-usd) MAX_USD="$2"; shift ;;
    --pause-fabric) PAUSE=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    -*) die "unknown option $1" ;;
    *) ENV_ARG="$1" ;;
  esac
  shift
done
load_azd_env "$ENV_ARG"
ENV="$AZURE_ENV_NAME"
SUB="${AZURE_SUBSCRIPTION_ID:?AZURE_SUBSCRIPTION_ID missing in the azd env}"
RG="${AZURE_RESOURCE_GROUP:-$(cfg names.resource_group)}"
ACCOUNT="${AZURE_AI_ACCOUNT_NAME:-$(cfg names.foundry_account)}"
PROJECT="${AZURE_AI_PROJECT_NAME:-$(cfg names.foundry_project)}"
SEARCH="${AZURE_SEARCH_SERVICE_NAME:-$(cfg names.search_service)}"
CAPACITY="${FABRIC_CAPACITY_NAME:-}"
MCP_APP="${MCP_APP_NAME:-$(cfg names.mcp_app)}"
DEVUI_APP="${LAB4_DEVUI_APP_NAME:-$(cfg names.devui_app)}"
BUDGET="${BUDGET_NAME:-$(cfg names.budget)}"
ARM="https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers"
TMPD="$(mktempdir)"; trap 'rm -rf "$TMPD"' EXIT

echo "LiveWell cost guardrails — env=$ENV rg=$RG"
az group show -n "$RG" --subscription "$SUB" -o none 2>/dev/null || die "resource group $RG not found (provision first)"

# Every ARM read in parallel (each az start-up costs seconds on some machines).
get() {  # name url
  az rest --method get --url "$2" -o json >"$TMPD/$1.json" 2>"$TMPD/$1.err" || echo '{}' >"$TMPD/$1.json"
}
FROM="$(date -u +%Y-%m-01T00:00:00Z)"; TO="$(date -u +%Y-%m-%dT23:59:59Z)"
cat >"$TMPD/costq.json" <<EOF
{"type":"ActualCost","timeframe":"Custom","timePeriod":{"from":"$FROM","to":"$TO"},
 "dataset":{"granularity":"None","aggregation":{"totalCost":{"name":"Cost","function":"Sum"}},
 "grouping":[{"type":"Dimension","name":"ResourceType"}]}}
EOF
az resource list -g "$RG" --subscription "$SUB" -o json >"$TMPD/resources.json" 2>/dev/null &
get budget "$ARM/Microsoft.Consumption/budgets/$BUDGET?api-version=2023-11-01" &
get deployments "$ARM/Microsoft.CognitiveServices/accounts/$ACCOUNT/deployments?api-version=2025-06-01" &
get connections "$ARM/Microsoft.CognitiveServices/accounts/$ACCOUNT/projects/$PROJECT/connections?api-version=2025-06-01" &
get searchsvcs "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.Search/searchServices?api-version=2025-05-01" &
get mcp "$ARM/Microsoft.App/containerApps/$MCP_APP?api-version=2024-03-01" &
get devui "$ARM/Microsoft.App/containerApps/$DEVUI_APP?api-version=2024-03-01" &
get law "$ARM/Microsoft.OperationalInsights/workspaces/log-livewell-$ENV?api-version=2023-09-01" &
[ -n "$CAPACITY" ] && get fabric "$ARM/Microsoft.Fabric/capacities/$CAPACITY?api-version=2023-11-01" &
( az rest --method post --url "$ARM/Microsoft.CostManagement/query?api-version=2023-11-01" \
    --body "@$TMPD/costq.json" -o json >"$TMPD/cost.json" 2>"$TMPD/cost.err" || echo '{}' >"$TMPD/cost.json" ) &
wait
[ -f "$TMPD/fabric.json" ] || echo '{}' >"$TMPD/fabric.json"

THRESHOLDS="$(cfg_json "environments.$ENV.budget_alerts_usd" 2>/dev/null || echo '[150, 300]')"
MODELS="$(cfg_json models)"
set +e
pyrun - "$TMPD" "$ENV" "$SEARCH" "$THRESHOLDS" "$MODELS" "${MAX_USD:-}" <<'EOF'
import json, os, sys
d, env, search_name, thresholds, models, max_usd = sys.argv[1:7]
thresholds = sorted(json.loads(thresholds)); models = json.loads(models)
def load(n):
    try:
        return json.load(open(os.path.join(d, n + ".json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {}
fails = warns = 0
def ok(m): print(f"  PASS  {m}")
def bad(m):
    global fails; fails += 1; print(f"  FAIL  {m}")
def warn(m):
    global warns; warns += 1; print(f"  WARN  {m}")

# Budget
b = load("budget").get("properties")
if not b:
    bad("budget missing (infra/modules/budget.bicep)")
else:
    amount = b.get("amount", 0)
    got = sorted(round(n["threshold"] * amount / 100) for n in b.get("notifications", {}).values() if n.get("enabled"))
    if got == thresholds:
        ok(f"budget {amount} USD/month, alerts at {', '.join(f'US${t}' for t in got)}")
    else:
        bad(f"budget alerts {got} != {thresholds}")
    if not any(n.get("contactEmails") or n.get("contactRoles") for n in b.get("notifications", {}).values()):
        bad("budget notifications have no recipients")

# Model deployments
cap = int(models.get("tpm_cap_thousands", 100))
emb_cap = int(models.get("embedding_tpm_cap_thousands", cap))
tools_cap = int(models.get("tools_tpm_cap_thousands", cap))
allowed = {models["default"], models["tools"], models["embeddings"]}
deps = load("deployments").get("value", [])
if not deps:
    bad("no model deployments found (Foundry account missing?)")
for dep in deps:
    sku = dep.get("sku", {}); m = dep.get("properties", {}).get("model", {})
    label = f"deployment {dep['name']} ({m.get('format')}/{m.get('name')} {m.get('version')}, {sku.get('name')} {sku.get('capacity')}K TPM)"
    limit = {models["embeddings"]: emb_cap, models["tools"]: tools_cap}.get(dep["name"], cap)
    if "provisioned" in sku.get("name", "").lower():
        bad(label + " — PTU is forbidden")
    elif sku.get("name") != models.get("deployment_type", "GlobalStandard"):
        bad(label + " — must be GlobalStandard")
    elif int(sku.get("capacity", 0)) > limit:
        bad(label + f" — above the {limit}K TPM cap")
    elif m.get("format") not in ("OpenAI", "Microsoft"):
        bad(label + " — partner models are forbidden")
    elif dep["name"] not in allowed:
        warn(label + " — not one of the three workshop deployments")
    else:
        ok(label)

# Resources: search, tags, Fabric SKU
res = load("resources")
res = res if isinstance(res, list) else []
svcs = [s for s in load("searchsvcs").get("value", []) if s.get("tags", {}).get("workshop") == "livewell"
        and s.get("tags", {}).get("env") == env]
if len(svcs) == 1:
    s = svcs[0]; sku = s.get("sku", {}).get("name", "")
    p = s.get("properties", {})
    if sku.startswith("standard") or sku.startswith("storage"):
        bad(f"search {s['name']} on {sku} — Standard tiers are forbidden")
    else:
        ok(f"one search service {s['name']} ({sku})")
    if p.get("semanticSearch") not in (None, "free", "disabled"):
        warn(f"semantic ranker plan is {p.get('semanticSearch')} (free covers the workshop)")
    kr = p.get("knowledgeRetrieval")
    if kr not in (None, "free"):
        warn(f"agentic retrieval plan is {kr} (SPEC.md: Free until the allowance is hit)")
    else:
        ok(f"agentic retrieval plan {kr or 'free (default)'}; semantic ranker {p.get('semanticSearch') or 'default'}")
else:
    bad(f"expected exactly one workshop search service for env={env}, found {len(svcs)}")

# App Insights creates these (free, untaggable at create): smart-detector alert rules and, in a subscription that has
# none yet, the "Application Insights Smart Detection" action group. The template creates no action groups.
AUTO_CREATED = {"microsoft.alertsmanagement/smartdetectoralertrules"}
AUTO_CREATED_NAMED = {("microsoft.insights/actiongroups", "application insights smart detection")}
is_auto = lambda r: (r.get("type", "").lower() in AUTO_CREATED
                     or (r.get("type", "").lower(), r.get("name", "").lower()) in AUTO_CREATED_NAMED)
auto = [r["name"] for r in res if is_auto(r)]
untagged = [r["name"] for r in res if not is_auto(r)
            and ((r.get("tags") or {}).get("workshop") != "livewell" or (r.get("tags") or {}).get("env") != env)]
if res and not untagged:
    ok(f"all {len(res) - len(auto)} resources tagged workshop=livewell env={env}"
       + (f" (skipped {len(auto)} auto-created App Insights item(s))" if auto else ""))
elif untagged:
    bad("resources missing workshop/env tags: " + ", ".join(untagged))
acrs = [r for r in res if r.get("type", "").lower() == "microsoft.containerregistry/registries"]
for r in acrs:
    sku = (r.get("sku") or {}).get("name", "")
    (ok if sku == "Basic" else bad)(f"ACR {r['name']} is {sku}" + ("" if sku == "Basic" else " (Basic only)"))

fab = load("fabric")
if fab.get("sku"):
    state = fab.get("properties", {}).get("state", "?")
    sku, want = fab["sku"].get("name"), os.environ.get("FABRIC_SKU") or "F2"
    rate = {"F2": 0.36, "F4": 0.76}.get(sku)
    if rate is None:
        bad(f"Fabric capacity {fab['name']} is {sku} (F2 or F4 only)")
    elif sku != want:
        warn(f"Fabric capacity {fab['name']} is {sku} but FABRIC_SKU={want}: the next provision resizes it "
             f"(azd env set FABRIC_SKU {sku} keeps it)")
    else:
        ok(f"Fabric capacity {fab['name']} {sku}")
    msg = f"Fabric capacity state {state}"
    (warn(msg + f" — billing ~US${rate or 0.36:.2f}/h; pause when idle: scripts/capacity.sh suspend")
     if state == "Active" else ok(msg))
    print(f"FABRIC_STATE={state}", file=open(os.path.join(d, "fabric.state"), "w"))
elif fab == {}:
    warn("no Fabric capacity (FABRIC_BRIDGE=false or not provisioned)")

# MCP app
mcp = load("mcp")
if mcp.get("properties"):
    scale = mcp["properties"].get("template", {}).get("scale", {})
    mn = scale.get("minReplicas", 0)
    (warn if mn else ok)(f"MCP app {mcp['name']} minReplicas={mn} (1 only on workshop day: MCP_MIN_REPLICAS=1)")
else:
    warn("MCP container app not found")

# Lab 4 DevUI app (optional, LAB4_DEVUI)
devui = load("devui")
if devui.get("properties"):
    scale = devui["properties"].get("template", {}).get("scale", {})
    mn, mx = scale.get("minReplicas", 0), scale.get("maxReplicas")
    if mx != 1:
        bad(f"DevUI app {devui['name']} maxReplicas={mx} (must be 1: DevUI keeps conversations in memory)")
    (warn if mn else ok)(f"DevUI app {devui['name']} minReplicas={mn} (1 only on workshop day: DEVUI_MIN_REPLICAS=1)")
else:
    ok("no Lab 4 DevUI app (LAB4_DEVUI=false or not provisioned)")

# Log Analytics cap
law = load("law")
quota = law.get("properties", {}).get("workspaceCapping", {}).get("dailyQuotaGb")
if law.get("properties"):
    (ok if quota not in (None, -1) and quota <= 1 else bad)(f"Log Analytics daily cap {quota} GB")

# Connections: no Bing
conns = load("connections").get("value", [])
bing = [c["name"] for c in conns if "bing" in (c.get("properties", {}).get("category", "") + c["name"]).lower()]
(bad if bing else ok)("no Bing grounding connection" if not bing else "Bing connection present (off by default, SPEC.md §13): " + ", ".join(bing))

# Month-to-date cost
cost = load("cost").get("properties")
if cost is None:
    err = open(os.path.join(d, "cost.err"), encoding="utf-8", errors="replace").read().strip().splitlines()
    warn("cost query unavailable: " + (err[-1][:160] if err else "no data yet"))
else:
    cols = [c["name"] for c in cost.get("columns", [])]
    rows = cost.get("rows", [])
    ci = cols.index("Cost") if "Cost" in cols else 0
    ti = cols.index("ResourceType") if "ResourceType" in cols else None
    total = sum(float(r[ci]) for r in rows)
    currency = rows[0][cols.index("Currency")] if rows and "Currency" in cols else "USD"
    print(f"  INFO  month-to-date cost for the resource group: {total:.2f} {currency} (Cost Management lags up to 24 h)")
    for r in sorted(rows, key=lambda r: -float(r[ci]))[:6]:
        if ti is not None and float(r[ci]) >= 0.01:
            print(f"          {float(r[ci]):8.2f}  {r[ti]}")
    if max_usd and total > float(max_usd):
        bad(f"month-to-date {total:.2f} > --max-usd {max_usd}")
open(os.path.join(d, "counts"), "w", newline="\n").write(f"{fails} {warns}\n")
EOF
set -e
read -r F W < <(tr -d '\r' <"$TMPD/counts") || { F=1; W=0; }
FAILURES=$((FAILURES + F)); WARNINGS=$((WARNINGS + W))

if [ "$PAUSE" = "1" ] && [ -n "$CAPACITY" ]; then
  if grep -q 'FABRIC_STATE=Active' "$TMPD/fabric.state" 2>/dev/null; then
    log "suspending Fabric capacity $CAPACITY"
    az rest --method post --url "$ARM/Microsoft.Fabric/capacities/$CAPACITY/suspend?api-version=2023-11-01" -o none &&
      ok "Fabric capacity $CAPACITY suspend requested" || bad "suspend failed"
  else
    ok "Fabric capacity already paused"
  fi
fi
summary_and_exit
