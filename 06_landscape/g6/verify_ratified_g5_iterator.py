#!/usr/bin/env python3
"""Read-only count check for the registry-bound Gate-5 record iterator."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.g6.ratified_g5_input import (
    EXPECTED_COORDINATE_COUNT,
    RatifiedG5InputError,
    iter_ratified_records,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, default=ROOT / "research/g5/core_pass_output")
    args = parser.parse_args()
    try:
        count = sum(1 for _ in iter_ratified_records(args.corpus_dir))
    except RatifiedG5InputError as exc:
        print(f"FAIL ratified Gate-5 record iterator: {exc}", file=sys.stderr)
        return 1
    if count != EXPECTED_COORDINATE_COUNT:
        print(f"FAIL ratified Gate-5 record iterator: expected {EXPECTED_COORDINATE_COUNT}, found {count}", file=sys.stderr)
        return 1
    print(f"PASS ratified Gate-5 record iterator records={count}")
    print("scientific_outputs=intentionally absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
