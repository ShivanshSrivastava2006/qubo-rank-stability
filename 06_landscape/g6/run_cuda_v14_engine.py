#!/usr/bin/env python3
"""Plan, validate, or measure the non-value CUDA/T4 full-domain V-14 engine.

``--plan`` (default) validates every pin, both V-14 ledgers, the canonical
slack domain identity, and the declared validation coordinates; it needs no
nvcc or GPU and writes nothing.  ``--validate`` and ``--throughput`` require
the two passed qualification records (``--unbalanced-record``,
``--slack-record``), nvcc, and a Tesla T4; they compile and run in an
automatically removed temporary directory and print only counters, exact
elapsed times, and identities.  ``--throughput --scale S --start A --stop B``
processes the half-open linear range [A, B).  Nothing here prints an
energy, minimum, tie set, state, label, rate, or conclusion.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "research/g6/cuda_qualification/cuda_v14_engine.py"


def _load_module():
    specification = importlib.util.spec_from_file_location("g6_cuda_v14_engine", MODULE)
    if specification is None or specification.loader is None:
        raise RuntimeError("CUDA V-14 engine module is unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument("--plan", action="store_true", help="validate bindings and print the plan (default; no writes)")
    mode.add_argument("--validate", action="store_true", help="full-domain validation at the declared coordinates (T4)")
    mode.add_argument("--throughput", action="store_true", help="time one declared coordinate range (T4)")
    parser.add_argument("--unbalanced-record", type=Path, help="passed unbalanced CUDA/T4 cross-check --run JSON")
    parser.add_argument("--slack-record", type=Path, help="passed slack CUDA/T4 cross-check --run JSON")
    parser.add_argument("--scale", choices=("0.5x", "2x"))
    parser.add_argument("--start", type=int)
    parser.add_argument("--stop", type=int)
    args = parser.parse_args(argv)
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        print("FAIL CUDA T4 V-14 engine: PYTHONDONTWRITEBYTECODE=1 is required", file=sys.stderr)
        return 1
    module = _load_module()
    try:
        records = None
        if args.unbalanced_record is not None or args.slack_record is not None:
            if args.unbalanced_record is None or args.slack_record is None:
                raise module.EngineError("both --unbalanced-record and --slack-record are required together")
            records = (module._read_json(args.unbalanced_record, "unbalanced record"),
                       module._read_json(args.slack_record, "slack record"))
        if args.validate or args.throughput:
            if records is None:
                raise module.EngineError("--validate/--throughput require --unbalanced-record and --slack-record")
        if args.validate:
            result = module.run_validate(records)
        elif args.throughput:
            if args.scale is None or args.start is None or args.stop is None:
                raise module.EngineError("--throughput requires --scale, --start, and --stop")
            result = module.run_throughput(records, args.scale, args.start, args.stop)
        else:
            result = module.build_plan(records)
    except module.EngineError as exc:
        print(f"FAIL CUDA T4 V-14 engine: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if result.get("verdict", "pass") in ("pass", "measured") else 1


if __name__ == "__main__":
    raise SystemExit(main())
