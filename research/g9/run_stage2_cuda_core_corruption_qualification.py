#!/usr/bin/env python3
"""Plan or, after a new owner release, run Gate-9 non-scientific CUDA A-tests."""

from __future__ import annotations

import os
import sys

if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
    print("FAIL: PYTHONDONTWRITEBYTECODE=1 is required", file=sys.stderr)
    raise SystemExit(2)
sys.dont_write_bytecode = True

import argparse
from pathlib import Path
import tempfile
import uuid

# Ignore pre-existing project bytecode while importing hash-pinned source.
sys.pycache_prefix = str(Path(tempfile.gettempdir()) / ("g9-A-pycache-isolated-" + uuid.uuid4().hex))
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9.cuda_qualification import stage2_cuda_core_corruption_qualification as qualifier  # noqa: E402
from research.g9.cuda_qualification import stage2_cuda_execution_contract as contract  # noqa: E402

# A regular installed ``research`` package can outrank this staged namespace
# package despite ROOT being first on sys.path.  Qualification must compare
# against the exact hash-pinned Python modules staged with the CUDA source.
_BOUND_IMPORTS = (
    (qualifier, "research/g9/cuda_qualification/stage2_cuda_core_corruption_qualification.py"),
    (qualifier.core, "research/g9/cuda_qualification/stage2_cuda_core_stream_engine.py"),
    (qualifier.clean, "research/g9/cuda_qualification/stage2_cuda_core_qualification.py"),
    (qualifier.clean.bridge, "research/g9/cuda_qualification/stage2_cuda_core_bridge.py"),
    (qualifier.clean.input_frame, "research/g9/cuda_qualification/stage2_cuda_input_frame.py"),
    (contract, "research/g9/cuda_qualification/stage2_cuda_execution_contract.py"),
)
for _module, _relative in _BOUND_IMPORTS:
    _origin = getattr(_module, "__file__", None)
    if type(_origin) is not str or Path(_origin).resolve() != ROOT / _relative:
        print("FAIL: Python qualification import escaped the staged source: " + _relative,
              file=sys.stderr)
        raise SystemExit(2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate-9 non-scientific CUDA corruption qualification")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--qualify-corruptions", action="store_true")
    parser.add_argument("--reviewed")
    args = parser.parse_args()
    try:
        if args.plan:
            if args.reviewed is not None:
                raise qualifier.CorruptionQualificationError("--reviewed is only for --qualify-corruptions")
            result = qualifier.build_plan()
        else:
            result = qualifier.run_qualification(args.reviewed)
    except qualifier.CorruptionQualificationError as exc:
        print("FAIL Gate-9 CUDA corruption qualification: " + str(exc), file=sys.stderr)
        return 1
    print(contract.canonical_bytes(result).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
