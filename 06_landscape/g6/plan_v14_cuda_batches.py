#!/usr/bin/env python3
"""Plan V-14 CUDA/T4 coordinate batches or validate a final batch set; never compute a value.

``plan --scale {0.5x,2x} --qualification ENGINE_VALIDATION_RECORD --throughput MEASUREMENT [--derate p/q]``
prints the canonical plan to stdout.  ``validate-final-set --plan PLAN MANIFEST...``
prints the acceptance summary and exits non-zero on any rejection.
``manifest-skeleton --plan PLAN --batch-id ID`` prints the plan-bound fields a
future emitter must carry.  Every mode is metadata-only: no energy is
computed, no Gate-5 path is read, and nothing is written.
"""

from __future__ import annotations

import argparse
from fractions import Fraction
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "research/g6/cuda_qualification/v14_batch_contract.py"


def _load_module():
    specification = importlib.util.spec_from_file_location("g6_v14_batch_contract", MODULE)
    if specification is None or specification.loader is None:
        raise RuntimeError("V-14 batch contract module is unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _emit(payload) -> None:
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    plan = modes.add_parser("plan", help="emit the canonical batch plan (no writes)")
    plan.add_argument("--scale", required=True, choices=("0.5x", "2x"))
    plan.add_argument("--qualification", required=True, type=Path, help="passed CUDA/T4 V-14 engine --validate record (binds both qualifications)")
    plan.add_argument("--throughput", required=True, type=Path, help="engine --throughput measurement (coordinates, wall/setup/coordinate_seconds)")
    plan.add_argument("--derate", default=None, help="rational in (0,1], e.g. 9/10 (default 9/10)")
    final = modes.add_parser("validate-final-set", help="metadata-only merge validation")
    final.add_argument("--plan", required=True, type=Path)
    final.add_argument("manifests", nargs="+", type=Path)
    skeleton = modes.add_parser("manifest-skeleton", help="print the plan-bound manifest fields")
    skeleton.add_argument("--plan", required=True, type=Path)
    skeleton.add_argument("--batch-id", required=True)
    args = parser.parse_args(argv)
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        print("FAIL V-14 CUDA batch contract: PYTHONDONTWRITEBYTECODE=1 is required", file=sys.stderr)
        return 1
    module = _load_module()
    try:
        if args.mode == "plan":
            derate = module.DEFAULT_DERATE if args.derate is None else Fraction(args.derate)
            record = module._read_json(args.qualification, "qualification record")
            measurement = module._read_json(args.throughput, "throughput measurement")
            _emit(module.build_plan(args.scale, record, measurement, derate))
        elif args.mode == "validate-final-set":
            plan_payload = module._read_json(args.plan, "batch plan")
            manifests = [module._read_json(path, f"manifest {path}") for path in args.manifests]
            _emit(module.validate_final_set(plan_payload, manifests))
        else:
            _emit(module.manifest_skeleton(module._read_json(args.plan, "batch plan"), args.batch_id))
    except (module.BatchContractError, module.cuda.CrosscheckError, ValueError, ZeroDivisionError) as exc:
        print(f"FAIL V-14 CUDA batch contract: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
