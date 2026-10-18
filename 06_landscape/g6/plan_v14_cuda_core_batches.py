#!/usr/bin/env python3
"""Plan CUDA/T4 V-14 core batches or validate a complete artifact set and emit the merged index.

``plan --scale S --validation-record R --measurement M [--derate p/q]`` prints
the canonical core plan (no writes).  ``validate-final-set --plan P
--artifacts DIR --output INDEX`` validates every batch directory under DIR
against the plan and writes only a merged index manifest to INDEX (outside
the repository, collision-refusing).  Nothing here computes a value,
aggregate, rate, or conclusion, and no scientific record is copied.
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
MODULE = ROOT / "research/g6/cuda_qualification/v14_core_batch_contract.py"


def _load_module():
    specification = importlib.util.spec_from_file_location("g6_v14_core_batch_contract", MODULE)
    if specification is None or specification.loader is None:
        raise RuntimeError("core batch contract module is unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _emit(payload) -> None:
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    plan = modes.add_parser("plan")
    plan.add_argument("--scale", required=True, choices=("0.5x", "2x"))
    plan.add_argument("--validation-record", required=True, type=Path, help="passed core --validate record")
    plan.add_argument("--measurement", required=True, type=Path, help="core --measure throughput_measurement JSON")
    plan.add_argument("--derate", default=None, help="rational in (0,1] (default 9/10)")
    final = modes.add_parser("validate-final-set")
    final.add_argument("--plan", required=True, type=Path)
    final.add_argument("--artifacts", required=True, type=Path, help="directory holding one subdirectory per batch id")
    final.add_argument("--output", required=True, type=Path, help="merged index path (outside the repository; must not exist)")
    args = parser.parse_args(argv)
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        print("FAIL V-14 core batch contract: PYTHONDONTWRITEBYTECODE=1 is required", file=sys.stderr)
        return 1
    module = _load_module()
    try:
        if args.mode == "plan":
            derate = module.base.DEFAULT_DERATE if args.derate is None else Fraction(args.derate)
            _emit(module.build_plan(args.scale, module._read_json(args.validation_record, "core validation record"),
                                    module._read_json(args.measurement, "core measurement"), derate))
        else:
            index = module.validate_final_set(module._read_json(args.plan, "core batch plan"), args.artifacts)
            module.write_merged_index(index, args.output)
            _emit({key: value for key, value in index.items() if key != "batches"} | {"written": str(args.output)})
    except (module.CoreContractError, module.core.CoreError, ValueError, ZeroDivisionError) as exc:
        print(f"FAIL V-14 core batch contract: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
