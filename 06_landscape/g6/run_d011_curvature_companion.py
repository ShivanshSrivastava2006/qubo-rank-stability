#!/usr/bin/env python3
"""Plan or explicitly run the fixed, non-primary D011 companion service."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.g6.d011_runner import D011Error, D011Runner


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research/g6/d011_curvature_companion")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--session-hours", type=float, default=2.0)
    parser.add_argument("--checkpoint-minutes", type=float, default=20.0)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="validate inputs and print the fixed population without computing")
    mode.add_argument("--run", action="store_true", help="run or resume the D011 companion pass")
    args = parser.parse_args()
    try:
        runner = D011Runner(args.output_dir, args.workers, args.session_hours, args.checkpoint_minutes)
        result = runner.plan() if args.plan else runner.run()
        print(json.dumps(result, sort_keys=True))
        return 0
    except D011Error as exc:
        print(f"FAIL D011 companion service: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
