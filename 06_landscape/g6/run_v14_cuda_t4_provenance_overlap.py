#!/usr/bin/env python3
"""CLI for the non-scientific CUDA/T4 V-14 provenance/overlap repair."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
    print("FAIL V-14 CUDA/T4 provenance/overlap audit: PYTHONDONTWRITEBYTECODE=1 is required", file=sys.stderr)
    raise SystemExit(1)
sys.dont_write_bytecode = True

from research.g6 import v14_cuda_t4_provenance_overlap as audit


def _environment_guard() -> None:
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1" or sys.dont_write_bytecode is not True:
        raise audit.ProvenanceOverlapError("PYTHONDONTWRITEBYTECODE=1 is required")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zero-five-plan", type=Path, required=True)
    parser.add_argument("--zero-five-root", type=Path, required=True)
    parser.add_argument("--two-x-plan", type=Path, required=True)
    parser.add_argument("--two-x-root", type=Path, required=True)
    parser.add_argument("--reviewed", default="")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research/g6/v14_cuda_t4_provenance_overlap")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--plan", action="store_true")
    group.add_argument("--write", action="store_true")
    group.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    try:
        _environment_guard()
        if args.plan:
            print(json.dumps({"mode": "plan", "writes": "none", "scientific_outputs": "intentionally absent",
                              "expected_plan_content_sha256": audit.EXPECTED_PLAN_CONTENT_SHA256}, sort_keys=True, separators=(",", ":")))
            return 0
        if not args.reviewed.strip():
            raise audit.ProvenanceOverlapError("--reviewed must be non-empty for --write or --verify")
        if args.write:
            payload = audit.build(zero_five_plan=args.zero_five_plan, zero_five_root=args.zero_five_root,
                                  two_x_plan=args.two_x_plan, two_x_root=args.two_x_root, reviewed_handoff=args.reviewed)
            audit.write_new(args.output_dir, payload)
            print(json.dumps({"verdict": "written", "output_dir": str(args.output_dir),
                              "content_sha256": payload["content_sha256"]}, sort_keys=True, separators=(",", ":")))
            return 0
        print(json.dumps(audit.validate_published(args.output_dir, zero_five_plan=args.zero_five_plan,
                                                  zero_five_root=args.zero_five_root, two_x_plan=args.two_x_plan,
                                                  two_x_root=args.two_x_root, reviewed_handoff=args.reviewed),
                         sort_keys=True, separators=(",", ":")))
        return 0
    except audit.ProvenanceOverlapError as exc:
        print(f"FAIL V-14 CUDA/T4 provenance/overlap audit: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
