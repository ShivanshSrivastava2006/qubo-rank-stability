#!/usr/bin/env python3
"""Plan, emit, or read-only validate the bounded D011 matched-subgrid comparison."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.g6.d011_matched_subgrid import (
    DEFAULT_OUTPUT_REL,
    D011MatchedSubgridError,
    build_plan,
    validate_published_comparison,
    write_comparison,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument("--plan", action="store_true", help="validate both inputs and print the no-write plan")
    mode.add_argument("--write", action="store_true", help="emit one reviewed bounded comparison")
    mode.add_argument("--verify", action="store_true", help="read-only validate a published comparison")
    parser.add_argument("--reviewed", help="non-empty independent-review handoff identifier; required with --write/--verify")
    parser.add_argument("--output-dir", type=Path, default=ROOT / DEFAULT_OUTPUT_REL)
    args = parser.parse_args()
    try:
        if args.write:
            if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
                raise D011MatchedSubgridError("PYTHONDONTWRITEBYTECODE=1 is required with --write")
            if not args.reviewed or not args.reviewed.strip():
                raise D011MatchedSubgridError("--write requires a non-empty --reviewed handoff identifier")
            result = write_comparison(args.output_dir, args.reviewed)
        elif args.verify:
            if not args.reviewed or not args.reviewed.strip():
                raise D011MatchedSubgridError("--verify requires the expected non-empty --reviewed handoff identifier")
            validate_published_comparison(args.output_dir, args.reviewed)
            result = {"verdict": "PASS", "output_dir": str(args.output_dir), "writes": "none",
                      "scientific_outputs": "mechanical matched-subgrid rho comparison only"}
        else:
            result = build_plan()
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
        return 0
    except D011MatchedSubgridError as exc:
        print(f"FAIL D011 matched-subgrid comparison: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
