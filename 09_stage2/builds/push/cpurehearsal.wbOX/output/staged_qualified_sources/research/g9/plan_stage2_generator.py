#!/usr/bin/env python3
"""Read-only plan for the approved Stage-2 generator; deliberately has no draw command."""
from __future__ import annotations

import os
import sys

if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
    print("FAIL Stage-2 generator plan: PYTHONDONTWRITEBYTECODE=1 is required", file=sys.stderr)
    raise SystemExit(2)
sys.dont_write_bytecode = True

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9 import stage2_generator as generator  # noqa: E402


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_plan() -> dict[str, object]:
    runtime = generator.require_approved_runtime()
    payload: dict[str, object] = {
        "schema": "decisions_os/g9_stage2_generator_plan/v1",
        "mode": "plan",
        "writes": "none",
        "scientific_outputs": "intentionally absent",
        "candidate_draws": "intentionally absent",
        "master_seed": generator.MASTER_SEED,
        "master_seed_hex": generator.MASTER_SEED_HEX,
        "slots": list(range(1, generator.SLOT_COUNT + 1)),
        "attempt_range": [0, generator.MAX_ATTEMPT],
        "return_shape": [generator.RETURN_ROWS, generator.ASSET_COUNT],
        "return_draw": {
            "method": generator.DRAW_METHOD,
            "check_valid": generator.DRAW_CHECK_VALID,
            "svd_tolerance": generator.DRAW_SVD_TOLERANCE.hex(),
        },
        "partition_shape": [generator.SECTOR_COUNT, generator.SECTOR_SIZE],
        "only_candidate_rejection_codes": [
            "partition_matches_stage1",
            "partition_matches_earlier_accepted",
            "feasible_set_below_100",
        ],
        "runtime": runtime,
        "source_sha256": {
            "research/g9/stage2_generator.py": sha256(ROOT / "research/g9/stage2_generator.py"),
            "research/g9/plan_stage2_generator.py": sha256(Path(__file__).resolve()),
        },
    }
    payload["content_sha256"] = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    return payload


def main() -> int:
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[1] != "--plan"):
        print("usage: plan_stage2_generator.py [--plan]", file=sys.stderr)
        return 2
    print(canonical_bytes(build_plan()).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
