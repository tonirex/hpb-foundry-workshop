#!/usr/bin/env python3
"""Read-only Search SKU availability check. Quota and advertised offerings do not reserve capacity."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from azrest import Api, ApiError
import wsconfig

OFFERINGS_PATH = "/providers/Microsoft.Search/fetchOfferings?api-version=2026-09-01-preview"


def advertised_skus(payload: dict, region: str) -> set[str]:
    if not isinstance(payload, dict):
        raise ValueError("could not verify Search offerings: response is not an object")
    matches = [entry for entry in payload.get("regions", [])
               if str(entry.get("regionName", "")).replace(" ", "").lower() == region.lower()]
    if len(matches) != 1 or not isinstance(matches[0].get("skus"), list):
        raise ValueError(f"could not verify Search offerings for {region}: missing or ambiguous region/SKU data")
    result = set()
    for entry in matches[0]["skus"]:
        name = entry.get("name") or (entry.get("sku") or {}).get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"could not verify Search offerings for {region}: unrecognised SKU entry")
        result.add(name.lower())
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", required=True)
    parser.add_argument("--sku", default="basic")
    args = parser.parse_args()
    cfg = wsconfig.load(args.env)
    target = cfg["environments"][args.env]
    region = target["search_location"]
    arm = Api("arm", tenant=target["tenant_id"], subscription=target["subscription_id"])
    rid = (f"/subscriptions/{target['subscription_id']}/resourceGroups/{cfg['names']['resource_group']}"
           f"/providers/Microsoft.Search/searchServices/{cfg['names']['search_service']}")
    try:
        existing = arm.get(rid + "?api-version=2025-05-01", ok_404=True)
        if existing:
            actual_region = str(existing.get("location", "")).replace(" ", "").lower()
            if actual_region != region or existing.get("sku", {}).get("name") != args.sku:
                raise ValueError(f"existing workshop Search does not match {region}/{args.sku}; refusing to relocate or resize")
            print(f"ok\tworkshop Search already exists in {region} on {args.sku}; no new service allocation required")
            return 0
        payload = arm.call("POST", OFFERINGS_PATH)
        skus = advertised_skus(payload, region)
        record = {"checked_at": datetime.now(timezone.utc).isoformat(), "environment": args.env,
                  "region": region, "sku": args.sku, "advertised_skus": sorted(skus),
                  "offered": args.sku.lower() in skus, "capacity_reserved": False}
        path = Path(__file__).resolve().parents[2] / ".azure" / args.env / "search-offerings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        if not record["offered"]:
            print(f"bad\tSearch {args.sku} is NOT advertised in {region}; STOP, no region or SKU fallback")
            return 1
        print(f"ok\tSearch {args.sku} is advertised in {region} (FetchOfferings preview, checked with the target tenant)")
        print("info\tregional offerings are separate from subscription quota and do not reserve deployment capacity")
        return 0
    except (ApiError, ValueError, OSError) as exc:
        print(f"bad\tSearch capacity check could not complete: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
