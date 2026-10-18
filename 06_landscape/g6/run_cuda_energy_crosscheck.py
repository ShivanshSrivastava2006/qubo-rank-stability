#!/usr/bin/env python3
"""Plan or explicitly run the bounded CUDA-vs-CPU unbalanced-energy cross-check on an NVIDIA T4.

Default (or ``--plan``) validates every pinned input, loads the four reviewed
coefficient points, declares the finite state set, and prints the plan.  It
needs no nvcc or GPU, compiles nothing, evaluates nothing, and writes nothing.
``--run`` compiles the CUDA cross-check with nvcc in an automatically removed
temporary directory, executes it on a Tesla T4 (compute capability 7.5), and
prints mismatch counts plus environment identity only.  It fails closed
without nvcc, the CUDA runtime, or a T4, and installs nothing.  Neither mode
reads the Gate-5 corpus or writes a project file.  A ``pass`` is
non-production qualification evidence, not authorization for GPU output.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "research/g6/cuda_qualification/cuda_energy_crosscheck.py"


def _load_module():
    # Loaded by path so this runner cannot drift onto a production Gate-6
    # runner or a Gate-5 module through the package tree.
    specification = importlib.util.spec_from_file_location("g6_cuda_energy_crosscheck", MODULE)
    if specification is None or specification.loader is None:
        raise RuntimeError("CUDA energy cross-check module is unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument("--plan", action="store_true", help="validate bindings and print the plan (default; no writes)")
    mode.add_argument("--run", action="store_true", help="compile with nvcc and execute the temporary T4 cross-check")
    args = parser.parse_args(argv)
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        print("FAIL CUDA T4 energy cross-check: PYTHONDONTWRITEBYTECODE=1 is required", file=sys.stderr)
        return 1
    module = _load_module()
    try:
        result = module.run_crosscheck() if args.run else module.build_plan()
    except module.CrosscheckError as exc:
        print(f"FAIL CUDA T4 energy cross-check: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if result.get("verdict", "pass") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
