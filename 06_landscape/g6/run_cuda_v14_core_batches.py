#!/usr/bin/env python3
"""Plan, validate, measure, or (after review and release) run one CUDA/T4 V-14 core batch.

``--plan`` (default) needs no nvcc or GPU and writes nothing.  ``--validate``
and ``--measure`` are non-value: counters, timing, and identities only.
``--run-batch`` is the future producer: one batch id from a reviewed plan,
a release record bound to that plan, both qualification records, an explicit
output directory outside the repository; it writes ``records.json`` and
``manifest.json`` atomically and refuses any collision.  Nothing here
aggregates, rates, compares, or concludes.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "research/g6/cuda_qualification/cuda_v14_core_batch.py"
CONTRACT = ROOT / "research/g6/cuda_qualification/v14_core_batch_contract.py"


def _load(name: str, path: Path):
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"module unavailable: {path}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--validate", action="store_true")
    mode.add_argument("--measure", action="store_true")
    mode.add_argument("--run-batch", action="store_true")
    parser.add_argument("--unbalanced-record", type=Path)
    parser.add_argument("--slack-record", type=Path)
    parser.add_argument("--scale", choices=("0.5x", "2x"))
    parser.add_argument("--start", type=int)
    parser.add_argument("--stop", type=int)
    parser.add_argument("--plan-file", type=Path, help="reviewed core batch plan (run-batch)")
    parser.add_argument("--batch-id", help="one batch id from the plan (run-batch)")
    parser.add_argument("--release-record", type=Path, help="owner release record bound to the plan (run-batch)")
    parser.add_argument("--output-dir", type=Path, help="existing directory outside the repository (run-batch)")
    args = parser.parse_args(argv)
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        print("FAIL CUDA T4 V-14 core batches: PYTHONDONTWRITEBYTECODE=1 is required", file=sys.stderr)
        return 1
    core = _load("g6_cuda_v14_core_batch", CORE)
    try:
        records = None
        if args.unbalanced_record is not None or args.slack_record is not None:
            if args.unbalanced_record is None or args.slack_record is None:
                raise core.CoreError("both --unbalanced-record and --slack-record are required together")
            records = (core._read_json(args.unbalanced_record, "unbalanced record"), core._read_json(args.slack_record, "slack record"))
        if (args.validate or args.measure or args.run_batch) and records is None:
            raise core.CoreError("--validate/--measure/--run-batch require --unbalanced-record and --slack-record")
        if args.validate:
            result = core.run_validate(records)
        elif args.measure:
            if args.scale is None or args.start is None or args.stop is None:
                raise core.CoreError("--measure requires --scale, --start, and --stop")
            result = core.run_measure(records, args.scale, args.start, args.stop)
        elif args.run_batch:
            if None in (args.plan_file, args.batch_id, args.release_record, args.output_dir):
                raise core.CoreError("--run-batch requires --plan-file, --batch-id, --release-record, and --output-dir")
            contract = _load("g6_v14_core_batch_contract", CONTRACT)
            plan = core._read_json(args.plan_file, "core batch plan")
            try:
                by_id = contract.validate_plan(plan)
            except contract.CoreContractError as exc:
                raise core.CoreError(str(exc)) from exc
            if args.batch_id not in by_id:
                raise core.CoreError(f"batch id is not in the plan: {args.batch_id}")
            release = core._read_json(args.release_record, "release record")
            result = core.run_batch(records, plan, by_id[args.batch_id], release, args.output_dir)
        else:
            result = core.build_plan(records)
    except core.CoreError as exc:
        print(f"FAIL CUDA T4 V-14 core batches: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if result.get("verdict", "pass") in ("pass", "measured", "written") else 1


if __name__ == "__main__":
    raise SystemExit(main())
