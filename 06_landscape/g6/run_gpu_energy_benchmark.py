#!/usr/bin/env python3
"""Plan or explicitly run the non-production unbalanced-energy GPU throughput benchmark.

Default (or ``--plan``) validates every pinned input, binds the same 1710
states and four reviewed coefficient points as the bit-exact cross-check,
and prints the two compile profiles.  It compiles nothing, evaluates
nothing, and writes nothing.  ``--run`` compiles both profiles in an
automatically removed temporary directory, gates each on the existing
6840-evaluation GPU-vs-Python cross-check, times only profiles that pass,
and prints durations and counts.  It never prints an energy or any other
scientific quantity, never reads the Gate-5 corpus, and never writes a
project file.  An ``accepted`` verdict is a bounded measurement, not a
production claim.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "research/g6/gpu_qualification/energy_benchmark.py"


def _load_module():
    # Loaded by path so this runner cannot drift onto a production Gate-6
    # runner or a Gate-5 module through the package tree.
    specification = importlib.util.spec_from_file_location("g6_gpu_energy_benchmark", MODULE)
    if specification is None or specification.loader is None:
        raise RuntimeError("GPU energy benchmark module is unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument("--plan", action="store_true", help="validate bindings and print the plan (default; no writes)")
    mode.add_argument("--run", action="store_true", help="compile, gate, and time both profiles in a temporary directory")
    parser.add_argument("--warmup", type=int, default=None, help="warm-up launches per profile (excluded from timing)")
    parser.add_argument("--launches", type=int, default=None, help="timed launches per profile")
    args = parser.parse_args(argv)
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        print("FAIL GPU energy benchmark: PYTHONDONTWRITEBYTECODE=1 is required", file=sys.stderr)
        return 1
    module = _load_module()
    warmup = module.DEFAULT_WARMUP_LAUNCHES if args.warmup is None else args.warmup
    timed = module.DEFAULT_TIMED_LAUNCHES if args.launches is None else args.launches
    try:
        result = module.run_benchmark(warmup, timed) if args.run else module.build_plan(warmup, timed)
    except module.BenchmarkError as exc:
        print(f"FAIL GPU energy benchmark: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if result.get("verdict", "accepted") == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
