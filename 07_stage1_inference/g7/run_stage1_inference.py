#!/usr/bin/env python3
"""Build a canonical Gate-7 Stage-1 inference artifact to stdout; never writes a repository file."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g7.stage1_inference import Gate7InferenceError, RATE_REL, build_inference  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rate-surface", type=Path, default=ROOT / RATE_REL)
    parser.add_argument("--reviewed")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        raise SystemExit("FAIL Gate-7 inference: PYTHONDONTWRITEBYTECODE=1 is required")
    if not args.run:
        print(json.dumps({"schema": "decisions_os/g7_stage1_inference_plan/v1", "mode": "plan", "writes": "none",
                          "rate_surface": str(args.rate_surface), "scientific_outputs": "intentionally absent"},
                         sort_keys=True, separators=(",", ":")))
        return 0
    if not args.reviewed:
        raise SystemExit("FAIL Gate-7 inference: --reviewed is required with --run")
    try:
        result = build_inference(rate_path=args.rate_surface, reviewed_handoff=args.reviewed)
    except Gate7InferenceError as exc:
        raise SystemExit(f"FAIL Gate-7 inference: {exc}") from exc
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
