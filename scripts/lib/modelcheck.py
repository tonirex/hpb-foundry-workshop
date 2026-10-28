#!/usr/bin/env python3
"""Model availability, lifecycle, eligibility and quota check for the workshop deployments. READ-ONLY.

  python scripts/lib/modelcheck.py --env mcaps                 live, against the subscription in workshop.yaml
  python scripts/lib/modelcheck.py --env mcaps --table         also print the recommendation table (live numbers)
  python scripts/lib/modelcheck.py --env mcaps --json          machine-readable inventory record
  python scripts/lib/modelcheck.py --env mcaps --catalogue C.json --usage U.json [--deployments D.json]
                                   [--capacities K.json] [--deleted X.json] --today 2026-10-23     offline (tests)

Each planned deployment (workshop.yaml models.default / tools / embeddings, at models.versions and
models.units.<env>) is checked on FOUR separate lines, because none of them proves the next:

  catalogue    the model + version + SKU is offered in the region (and its lifecycle / retirement date)
  eligibility  this subscription has a quota pool for it (limit > 0); a Legacy model also needs an existing
               deployment in the subscription as evidence that new deployments are accepted
  quota        free quota in the shared pool covers the SUM of the planned deployments that draw on it
  capacity     the regional capacity API (best effort). It mirrors the quota headroom: it is NOT proof that the
               backend can place the deployment. Only a real deployment is, and that needs separate approval.

It also reports RPM next to TPM (from the catalogue rate limits), checks the 30-participant sizing assumptions in
models.sizing, and refuses anything unexpected: a model-router, a non-OpenAI model format, a provisioned (PTU) SKU.
It never requests quota, never changes a deployment and never picks another region: if something does not fit,
it says so and stops.

Output: one `status<TAB>message` line each (ok | bad | warn | info); exit 1 if any line is bad.
Standard library plus scripts/lib; ASCII output.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wsconfig  # noqa: E402

API = "2025-06-01"
CAPACITY_API = "2024-10-01"
ROLES = ("default", "tools", "embeddings")
ALLOWED_SKUS = ("GlobalStandard", "DataZoneStandard")
# Mirrors infra/main.bicep (@minValue / @maxValue on the three capacity params) and infra/modules/foundry.bicep
# (deploymentType.capacity @maxValue(1000)); tests/test_modelcheck.py keeps them in sync.
MIN_UNITS, MAX_UNITS = 10, 1000


@dataclass(frozen=True)
class Plan:
    role: str
    name: str
    version: str
    sku: str
    units: int


@dataclass
class Result:
    status: str  # ok | bad | warn | info
    text: str

    def line(self) -> str:
        return f"{self.status}\t{self.text}"


# --------------------------------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------------------------------
def plans(cfg: dict, env: str) -> list[Plan]:
    m = cfg["models"]
    units = (m.get("units") or {}).get(env) or {}
    versions = m.get("versions") or {}
    out = []
    for role in ROLES:
        name = str(m[role])
        out.append(Plan(role, name, str(versions.get(name, "")), str(m.get("deployment_type", "")),
                        int(units.get(role, 0) or 0)))
    return out


def parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def index_catalogue(raw: list[dict]) -> dict:
    """(model, version, sku) -> (model dict, sku dict). The listing repeats entries per kind, and fine-tune pools
    share SKU names with the inference pool, so skip those: they are separate quota pools."""
    idx: dict = {}
    for entry in raw or []:
        model = entry.get("model") or {}
        for sku in model.get("skus") or []:
            if "finetune" in str(sku.get("usageName", "")).lower():
                continue
            idx.setdefault((model.get("name"), str(model.get("version")), sku.get("name")), (model, sku))
    return idx


def per_unit_rates(sku: dict) -> tuple[float, float]:
    """(K tokens per minute, requests per minute) that ONE capacity unit buys, from the catalogue rate limits.
    The catalogue lists [requests, tokens] (e.g. 1 per 60 s and 1000 per 60 s; embeddings: 1 per 10 s = 6 RPM)."""
    limits = sku.get("rateLimits") or []

    def per_minute(r: dict) -> float:
        return float(r.get("count", 0)) * 60.0 / float(r.get("renewalPeriod") or 60.0)

    keyed = {str(r.get("key", "")).lower(): r for r in limits if r.get("key")}
    if "request" in keyed and "token" in keyed:
        req, tok = per_minute(keyed["request"]), per_minute(keyed["token"])
    elif len(limits) >= 2:
        req, tok = per_minute(limits[0]), per_minute(limits[1])
    else:
        return 0.0, 0.0
    return tok / 1000.0, req


def usage_by_name(usages: list[dict]) -> dict:
    out = {}
    for u in usages or []:
        out[str((u.get("name") or {}).get("value", ""))] = u
    return out


def capacity_of(dep: dict) -> int:
    sku = dep.get("sku") or {}
    props = dep.get("properties") or {}
    return int(sku.get("capacity") or props.get("currentCapacity") or 0)


def model_of(dep: dict) -> dict:
    return (dep.get("properties") or {}).get("model") or dep.get("model") or {}


def lifecycle_result(plan: Plan, model: dict, sku: dict, ref: date, ref_label: str, warn_days: int) -> Result:
    status = str(model.get("lifecycleStatus") or "Unknown")
    retire = parse_date(sku.get("deprecationDate")) or parse_date((model.get("deprecation") or {}).get("inference"))
    worst, parts = "ok", [f"lifecycle {status}"]
    if status != "GenerallyAvailable":
        worst = "warn"
        parts.append("not GA: label it, and keep participant checkpoints on GA paths")
    if retire is None:
        worst = "warn"
        parts.append("no retirement date published")
    else:
        days = (retire - ref).days
        if days <= 0:
            worst = "bad"
            parts.append(f"RETIRES {retire}, on or before {ref_label}")
        else:
            parts.append(f"retires {retire} ({days} days after {ref_label})")
            if days <= warn_days:
                worst = "warn" if worst != "bad" else worst
    return Result(worst, f"{plan.name} {plan.version}: " + "; ".join(parts))


def sizing_results(cfg: dict, env: str, plan: Plan, tpm_k_per_unit: float, rpm_per_unit: float) -> list[Result]:
    sizing = (cfg["models"].get("sizing") or {})
    people = int(((cfg.get("environments") or {}).get(env) or {}).get("participants", 0) or 0)
    pm = (sizing.get("participant_minute") or {}).get(plan.role)
    fd = (sizing.get("facilitator_demo") or {}).get(plan.role)
    if not (people and pm and fd and tpm_k_per_unit):
        return [Result("info", f"sizing {plan.role}: no sizing assumptions for this environment (models.sizing)")]
    burst = float(sizing.get("burst_factor", 1.0))
    need_k = math.ceil((people * float(pm["tokens_k"]) + float(fd["tokens_k"])) * burst)
    need_rpm = math.ceil((people * float(pm["requests"]) + float(fd["requests"])) * burst)
    have_k = plan.units * tpm_k_per_unit
    have_rpm = plan.units * rpm_per_unit
    ok = have_k >= need_k and have_rpm >= need_rpm
    text = (f"sizing {plan.role}: {people} people x {pm['tokens_k']}K + {fd['tokens_k']}K demo, x{burst:g} burst = "
            f"{need_k}K TPM needed vs {have_k:g}K planned; {people} x {pm['requests']} + {fd['requests']} requests, "
            f"x{burst:g} = {need_rpm} RPM needed vs {have_rpm:g} planned "
            "(planning assumptions, not measurements: confirm with the approved load test)")
    return [Result("ok" if ok else "warn", text)]


# --------------------------------------------------------------------------------------------------
# The check
# --------------------------------------------------------------------------------------------------
def evaluate(cfg: dict, env: str, location: str, catalogue: list[dict] | None, usages: list[dict] | None,
             deployments: list[dict] | None, capacities: list[dict] | None, deleted: list[dict] | None,
             own: tuple[str, str] | None, today: date) -> tuple[list[Result], list[dict]]:
    """Returns (results, records). `own` = (resource group, account name) of the workshop Foundry account.
    A dataset that is None could not be read: the checks that need it say so instead of guessing."""
    out: list[Result] = []
    recs: list[dict] = []
    todo = [p for p in plans(cfg, env)]
    workshop_date = parse_date((cfg.get("workshop") or {}).get("date"))
    ref, ref_label = (workshop_date, "the workshop") if workshop_date else (today, "today")
    warn_days = int((cfg["models"] or {}).get("retirement_warn_days", 120))

    if catalogue is None or usages is None:
        out.append(Result("bad", "cannot read the model catalogue or the usage list: nothing about availability or quota is verified"))
        return out, recs
    idx = index_catalogue(catalogue)
    usage = usage_by_name(usages)

    seen_names: dict[str, str] = {}
    for p in todo:
        if p.name in seen_names:
            out.append(Result("bad", f"{p.role} and {seen_names[p.name]} both use deployment '{p.name}': "
                                     "the template creates one deployment per name, so they must differ"))
        seen_names[p.name] = p.role
        if "router" in p.name.lower():
            out.append(Result("bad", f"{p.role}: '{p.name}' is a model-router; it is not part of this delivery "
                                     "(routing could reach models that are not approved)"))
        if p.sku not in ALLOWED_SKUS:
            out.append(Result("bad", f"{p.role}: deployment type '{p.sku}' is not allowed (use one of "
                                     f"{', '.join(ALLOWED_SKUS)}; never a provisioned/PTU type)"))
        if not p.version:
            out.append(Result("bad", f"{p.role}: no version for '{p.name}' in models.versions"))
        if not MIN_UNITS <= p.units <= MAX_UNITS:
            out.append(Result("bad", f"{p.role}: {p.units} units is outside {MIN_UNITS}..{MAX_UNITS} "
                                     "(infra/modules/foundry.bicep limit)"))

    own_deps: dict[str, dict] = {}
    if deployments is not None and own:
        own_deps = {d["name"]: d for d in deployments
                    if (d.get("resourceGroup", "").lower(), d.get("account", "").lower()) == (own[0].lower(), own[1].lower())}

    pools: dict[str, dict] = {}
    for p in todo:
        key = (p.name, p.version, p.sku)
        found = idx.get(key)
        if not found:
            offered = sorted({f"{k[1]}/{k[2]}" for k in idx if k[0] == p.name})
            out.append(Result("bad", f"catalogue: {p.name} {p.version} {p.sku} is NOT offered in {location}"
                                     + (f" (offered: {', '.join(offered)})" if offered else " (model not offered at all)")))
            continue
        model, sku = found
        out.append(Result("ok", f"catalogue: {p.name} {p.version} {p.sku} is offered in {location}"))
        out.append(lifecycle_result(p, model, sku, ref, ref_label, warn_days))
        tpm_k, rpm = per_unit_rates(sku)
        pool_name = str(sku.get("usageName", ""))
        u = usage.get(pool_name)
        legacy = str(model.get("lifecycleStatus")) in ("Legacy", "Deprecated")

        # eligibility ----------------------------------------------------------------------------
        if u is None:
            out.append(Result("bad", f"eligibility: no quota pool {pool_name} in this subscription for {location}"))
        elif float(u.get("limit", 0)) <= 0:
            out.append(Result("bad", f"eligibility: quota pool {pool_name} has limit 0 (not eligible / no quota granted)"))
        else:
            out.append(Result("ok", f"eligibility: quota pool {pool_name} is granted (limit {int(u['limit'])})"))
        if legacy:
            if deployments is None:
                out.append(Result("warn", f"eligibility: {p.name} is {model.get('lifecycleStatus')} (existing customers only) "
                                          "and the existing deployments could not be read: not verified"))
            else:
                ev = [d for d in deployments if model_of(d).get("name") == p.name and str(model_of(d).get("version")) == p.version]
                if ev:
                    d = ev[0]
                    out.append(Result("info", f"eligibility: {p.name} is {model.get('lifecycleStatus')}; existing-customer evidence: "
                                              f"deployment '{d.get('name')}' already exists in this subscription"))
                else:
                    out.append(Result("warn", f"eligibility: {p.name} is {model.get('lifecycleStatus')} and this subscription has "
                                              "no deployment of it: a NEW deployment may be refused"))

        own_dep = own_deps.get(p.name)
        own_cap = 0
        if own_dep:
            m = model_of(own_dep)
            if m.get("name") == p.name and str(m.get("version")) == p.version:
                own_cap = capacity_of(own_dep)
            else:
                out.append(Result("warn", f"existing deployment '{p.name}' in the workshop account is {m.get('name')} "
                                          f"{m.get('version')}, not the planned {p.version}"))
        pool = pools.setdefault(pool_name, {"u": u, "plans": [], "need": 0, "rates": (tpm_k, rpm), "own": 0})
        pool["plans"].append(p)
        pool["need"] += max(0, p.units - own_cap)
        pool["own"] += own_cap
        out.append(Result("info", f"rate: {p.name}: {p.units} units = {p.units * tpm_k:g}K TPM and "
                                  f"{p.units * rpm:g} RPM at the catalogue rate ({tpm_k:g}K TPM + {rpm:g} RPM per unit)"))
        out.extend(sizing_results(cfg, env, p, tpm_k, rpm))
        maximum = (sku.get("capacity") or {}).get("maximum")
        if maximum and p.units > int(maximum):
            out.append(Result("bad", f"{p.name}: {p.units} units exceeds the catalogue maximum {int(maximum)}"))

        # capacity API ---------------------------------------------------------------------------
        if capacities is None:
            out.append(Result("warn", f"capacity API: not queried for {p.name}: deployable capacity not verified"))
        else:
            hit = [c for c in capacities
                   if str(c.get("location", "")).lower() == location.lower()
                   and (c.get("properties") or {}).get("skuName") == p.sku
                   and ((c.get("properties") or {}).get("model") or {}).get("name") == p.name
                   and str(((c.get("properties") or {}).get("model") or {}).get("version")) == p.version]
            if not hit:
                out.append(Result("warn", f"capacity API: no {p.sku} entry for {p.name} {p.version} in {location}: not verified"))
            else:
                avail = float((hit[0].get("properties") or {}).get("availableCapacity", 0))
                need = max(0, p.units - own_cap)
                if avail >= need:
                    out.append(Result("ok", f"capacity: API reports availableCapacity {avail:g} >= {need} still to allocate "
                                            "(it mirrors the quota headroom; a real deployment is the only proof)"))
                else:
                    out.append(Result("bad", f"capacity: API reports only {avail:g} available for {p.name} {p.sku} in {location}, "
                                             f"{need} needed. Report it; do not switch region or request quota automatically"))
        recs.append({"role": p.role, "model": p.name, "version": p.version, "deployment_type": p.sku, "region": location,
                     "pool": pool_name, "limit": (u or {}).get("limit"), "current": (u or {}).get("currentValue"),
                     "planned_units": p.units, "tpm_k": p.units * tpm_k, "rpm": p.units * rpm,
                     "lifecycle": model.get("lifecycleStatus"),
                     "retires": str(parse_date(sku.get("deprecationDate")) or parse_date((model.get("deprecation") or {}).get("inference")))})

    # quota: summed per pool ---------------------------------------------------------------------
    for pool_name, pool in pools.items():
        u = pool["u"]
        if u is None:
            continue
        limit, current = float(u.get("limit", 0)), float(u.get("currentValue", 0))
        free = limit - current
        names = ", ".join(f"{p.name} {p.units}" for p in pool["plans"])
        text = (f"quota: pool {pool_name}: limit {limit:g}K, allocated {current:g}K, free {free:g}K; planned {names} "
                f"(still to allocate {pool['need']}K) -> {free - pool['need']:g}K left")
        if pool["need"] <= free:
            out.append(Result("ok", text))
        else:
            out.append(Result("bad", text + ". INSUFFICIENT: report it; do not switch region or request quota automatically"))
        if deployments is not None:
            explained = 0.0
            unmapped = 0
            for d in deployments:
                m = model_of(d)
                hit = idx.get((m.get("name"), str(m.get("version")), (d.get("sku") or {}).get("name")))
                if hit is None:
                    unmapped += 1
                    continue
                if str(hit[1].get("usageName")) == pool_name:
                    explained += capacity_of(d)
            gap = current - explained
            if gap > 0:
                extra = f"; {len(deleted)} soft-deleted account(s) exist" if deleted else ""
                bound = "at most " if unmapped else ""
                out.append(Result("info", f"quota: {bound}{gap:g}K of {pool_name} is allocated but not explained by the {location} "
                                          f"deployments visible here (accounts in other regions if the pool is shared, soft-deleted "
                                          f"accounts, other principals{extra}). It stays allocated until released: not touched"))

    # unexpected deployments in the workshop account ----------------------------------------------
    for name, d in own_deps.items():
        m = model_of(d)
        sku_name = str((d.get("sku") or {}).get("name", ""))
        if "router" in str(m.get("name", "")).lower():
            out.append(Result("bad", f"unexpected model-router deployment '{name}' in the workshop account: not part of this delivery"))
        if str(m.get("format", "OpenAI")) != "OpenAI":
            out.append(Result("bad", f"deployment '{name}' has model format {m.get('format')}: only OpenAI models are approved"))
        if "provisioned" in sku_name.lower():
            out.append(Result("bad", f"deployment '{name}' is a provisioned (PTU) SKU {sku_name}: not allowed"))
        if name not in seen_names:
            out.append(Result("warn", f"extra deployment '{name}' ({m.get('name')} {m.get('version')}) in the workshop account is not in workshop.yaml"))
    if deleted:
        names = ", ".join(sorted(str(x.get("name")) for x in deleted))
        out.append(Result("info", f"{len(deleted)} soft-deleted Foundry account(s) in {location} may still hold quota ({names}); "
                                  "purging needs separate approval"))
    return out, recs


# --------------------------------------------------------------------------------------------------
# Live data (read-only ARM GETs through scripts/lib/azrest.py, pinned to the configured tenant)
# --------------------------------------------------------------------------------------------------
def fetch_live(subscription: str, location: str, plan_list: list[Plan]) -> dict:
    from azrest import Api, ApiError  # lazy: tests never need az

    arm = Api("arm", subscription=subscription)
    base = f"/subscriptions/{subscription}/providers/Microsoft.CognitiveServices"
    data: dict = {"warnings": []}

    def grab(key: str, fn):
        try:
            data[key] = fn()
        except (ApiError, SystemExit) as e:
            data[key] = None
            data["warnings"].append(f"{key}: {str(e)[:200]}")

    grab("catalogue", lambda: arm.get_all(f"{base}/locations/{location}/models?api-version={API}"))
    grab("usages", lambda: arm.get_all(f"{base}/locations/{location}/usages?api-version={API}"))

    def deployments() -> list[dict]:
        accounts = [a for a in arm.get_all(f"{base}/accounts?api-version={API}")
                    if str(a.get("location", "")).lower() == location.lower()]

        def one(account: dict) -> list[dict]:
            try:
                items = arm.get_all(f"{account['id']}/deployments?api-version={API}")
            except ApiError as exc:
                data["warnings"].append(f"deployments in {account['name']}: {exc.status} {exc.code}; inventory incomplete")
                return []
            rg = account["id"].split("/resourceGroups/")[1].split("/")[0]
            return [{**d, "account": account["name"], "resourceGroup": rg} for d in items]

        with ThreadPoolExecutor(max_workers=8) as pool:
            return [d for chunk in pool.map(one, accounts) for d in chunk]

    grab("deployments", deployments)
    grab("deleted", lambda: [a for a in arm.get_all(f"{base}/deletedAccounts?api-version={API}")
                             if str(a.get("location", "")).lower() == location.lower()])

    def capacities() -> list[dict]:
        out: list[dict] = []
        for p in plan_list:
            if not p.version:
                continue
            out += arm.get_all(f"{base}/modelCapacities?api-version={CAPACITY_API}&modelFormat=OpenAI"
                               f"&modelName={p.name}&modelVersion={p.version}")
        return out

    grab("capacities", capacities)
    return data


def table(records: list[dict]) -> str:
    rows = ["| role | model/version | deployment type | region | free quota (K TPM) | planned (K TPM / RPM) | left after | lifecycle (retires) |",
            "|---|---|---|---|---|---|---|---|"]
    for r in records:
        free = float(r["limit"] or 0) - float(r["current"] or 0)
        rows.append(f"| {r['role']} | {r['model']} {r['version']} | {r['deployment_type']} | {r['region']} | {free:g} | "
                    f"{r['tpm_k']:g} / {r['rpm']:g} | {free - r['planned_units']:g} | {r['lifecycle']} ({r['retires']}) |")
    return "\n".join(rows)


def load_json(path: str | None):
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", required=True)
    ap.add_argument("--location")
    ap.add_argument("--subscription")
    ap.add_argument("--account", help="workshop Foundry account name (default names.foundry_account)")
    ap.add_argument("--rg", help="workshop resource group (default names.resource_group)")
    ap.add_argument("--catalogue")
    ap.add_argument("--usage")
    ap.add_argument("--deployments")
    ap.add_argument("--capacities")
    ap.add_argument("--deleted")
    ap.add_argument("--today", help="YYYY-MM-DD (offline runs and tests)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--table", action="store_true")
    ap.add_argument("--save", help="also write the inventory record (JSON) to this path, e.g. under .azure/<env>/")
    args = ap.parse_args()

    cfg = wsconfig.load(args.env)
    env_cfg = (cfg.get("environments") or {}).get(args.env) or {}
    location = args.location or cfg["names"]["location"]
    sub = args.subscription or str(env_cfg.get("subscription_id", ""))
    own = (args.rg or cfg["names"]["resource_group"], args.account or cfg["names"]["foundry_account"])
    today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()
    checked = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    offline = any([args.catalogue, args.usage])
    if offline:
        data = {"catalogue": load_json(args.catalogue), "usages": load_json(args.usage),
                "deployments": load_json(args.deployments), "capacities": load_json(args.capacities),
                "deleted": load_json(args.deleted) or [], "warnings": []}
    else:
        data = fetch_live(sub, location, plans(cfg, args.env))
    results, records = evaluate(cfg, args.env, location, data["catalogue"], data["usages"], data["deployments"],
                                data["capacities"], data["deleted"], own, today)
    header = [Result("info", f"inventory checked {checked} for environment '{args.env}' in {location}: "
                             "catalogue, eligibility, quota and capacity are reported separately; re-run at T-3 "
                             "(quota can be consumed by other workloads in the subscription)")]
    header += [Result("warn", w) for w in data["warnings"]]
    results = header + results
    record = {"checked_at": checked, "environment": args.env, "region": location,
              "plans": records, "results": [{"status": r.status, "text": r.text} for r in results]}
    if args.save:
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(json.dumps(record, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(record, indent=2))
    else:
        for r in results:
            print(r.line())
        if args.table:
            print("info\trecommendation table (live numbers):")
            print(table(records))
    return 1 if any(r.status == "bad" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
