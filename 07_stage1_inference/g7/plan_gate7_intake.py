#!/usr/bin/env python3
"""Run the read-only Gate-7 intake check; emits an evidence-only JSON receipt."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g7.gate7_intake import Gate7IntakeError, build_intake


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v14-0-5-plan", type=Path, required=True)
    parser.add_argument("--v14-0-5-artifacts", type=Path, required=True)
    parser.add_argument("--v14-2x-plan", type=Path, required=True)
    parser.add_argument("--v14-2x-artifacts", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        raise SystemExit("FAIL Gate-7 intake: PYTHONDONTWRITEBYTECODE=1 is required")
    try:
        receipt = build_intake(
            v14_0_5_plan=args.v14_0_5_plan,
            v14_0_5_artifacts=args.v14_0_5_artifacts,
            v14_2x_plan=args.v14_2x_plan,
            v14_2x_artifacts=args.v14_2x_artifacts,
        )
    except Gate7IntakeError as exc:
        raise SystemExit(f"FAIL Gate-7 intake: {exc}") from exc
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
