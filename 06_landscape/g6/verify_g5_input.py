#!/usr/bin/env python3
"""Read-only Gate-5 acceptance-boundary verifier for Gate-6 pre-production."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.g6.g5_input import G5InputError, verify_accepted_g5_corpus


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, default=ROOT / "research/g5/core_pass_output")
    args = parser.parse_args()
    try:
        summary = verify_accepted_g5_corpus(args.corpus_dir)
    except G5InputError as exc:
        print(f"FAIL read-only Gate-5 input verification: {exc}", file=sys.stderr)
        return 1
    print("PASS read-only Gate-5 input verification")
    print(f"shards={summary.shard_count} coordinates={summary.coordinate_count}")
    print("accepted_platform_split="
          f"{summary.platform_counts['baseline']} baseline + "
          f"{summary.platform_counts['minority']} owner-exception minority")
    print("scientific_outputs=intentionally absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
