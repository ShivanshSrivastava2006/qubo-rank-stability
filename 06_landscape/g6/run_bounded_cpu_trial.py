#!/usr/bin/env python3
"""Plan or explicitly run the fixed Gate-6 bounded CPU qualification trial."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.g6.trial_runner import TrialError, fixture_plan, run_bounded_cpu_trial


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture-only", action="store_true", help="validate fixed bindings without a corpus read or energy sweep")
    mode.add_argument("--run", action="store_true", help="perform the one explicitly bounded CPU qualification trial")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research/g6/bounded_cpu_trial")
    args = parser.parse_args()
    try:
        if args.fixture_only:
            print(json.dumps(fixture_plan(), sort_keys=True))
        else:
            print(json.dumps({"trial_file": str(run_bounded_cpu_trial(args.output_dir))}, sort_keys=True))
        return 0
    except TrialError as exc:
        print(f"FAIL bounded CPU trial: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
