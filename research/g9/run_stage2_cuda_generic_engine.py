#!/usr/bin/env python3
"""CLI for the generic synthetic CUDA engine; no production Stage-2 mode exists."""
from __future__ import annotations

import os
import sys

if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
    print("FAIL Stage-2 generic CUDA engine: PYTHONDONTWRITEBYTECODE=1 is required", file=sys.stderr)
    raise SystemExit(2)
sys.dont_write_bytecode = True

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9.cuda_qualification import stage2_cuda_generic_engine as engine  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage-2 generic CUDA synthetic qualification harness")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--qualify-self-test", action="store_true")
    parser.add_argument("--reviewed")
    args = parser.parse_args()
    try:
        if args.plan:
            if args.reviewed is not None:
                raise engine.GenericCUDAEngineError("--reviewed is valid only with --qualify-self-test")
            print(engine.canonical_bytes(engine.build_plan()).decode("ascii"))
        else:
            print(engine.canonical_bytes(engine.run_qualified_self_test(args.reviewed)).decode("ascii"))
    except engine.GenericCUDAEngineError as exc:
        print("FAIL Stage-2 generic CUDA engine: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
