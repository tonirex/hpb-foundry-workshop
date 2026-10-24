#!/usr/bin/env python3
"""Read values from content/config/workshop.yaml for shell scripts.

  python scripts/lib/wsconfig.py get names.search_service --env mcaps   -> srch-hpb-livewell-mcaps
  python scripts/lib/wsconfig.py get environments.mcaps.facilitator_upns -> one value per line
  python scripts/lib/wsconfig.py json region_matrix                     -> JSON

`<env>` placeholders are replaced when --env is given. Lists print one item per line; mappings
print as JSON. Exit 2 if the key is missing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write("pyyaml missing: pip install -r requirements.txt\n")
    raise SystemExit(3)

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "content" / "config" / "workshop.yaml"


def lookup(data, dotted: str):
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(dotted)
    return cur


def subst(value, env: str | None):
    if env is None:
        return value
    if isinstance(value, str):
        return value.replace("<env>", env)
    if isinstance(value, list):
        return [subst(v, env) for v in value]
    if isinstance(value, dict):
        return {k: subst(v, env) for k, v in value.items()}
    return value


def load(env: str | None = None) -> dict:
    """Whole workshop.yaml with <env> substituted (for Python callers)."""
    return subst(yaml.safe_load(CONFIG.read_text(encoding="utf-8")), env or None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["get", "json"])
    ap.add_argument("key")
    ap.add_argument("--env", default=None)
    args = ap.parse_args()
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    try:
        value = subst(lookup(data, args.key), args.env or None)
    except KeyError:
        sys.stderr.write(f"workshop.yaml has no key {args.key}\n")
        return 2
    if args.mode == "json" or isinstance(value, dict):
        print(json.dumps(value))
    elif isinstance(value, list):
        print("\n".join(str(v) for v in value))
    elif isinstance(value, bool):
        print("true" if value else "false")
    else:
        print(value)
    return 0


if __name__ == "__main__":
    sys.exit(main())
