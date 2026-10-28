#!/usr/bin/env python3
"""Thin CLI for scripts/lib/scopecheck.py: verify the one-resource-group scope. See that module for the modes.

  python scripts/verify-scope.py plan|caller|deployed|manifest --env mcaps
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import scopecheck  # noqa: E402

if __name__ == "__main__":
    sys.exit(scopecheck.main())
