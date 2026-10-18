#!/usr/bin/env python3
"""Plan or, after a separate owner release, qualify the synthetic CUDA core."""

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

# Ignore any pre-existing project .pyc while reading hash-pinned source.
# The path is unique and nonexistent; dont_write_bytecode keeps it that way.
sys.pycache_prefix = str(Path(tempfile.gettempdir()) / ("g9-pycache-isolated-" + uuid.uuid4().hex))

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9.cuda_qualification import stage2_cuda_core_qualification as qualifier  # noqa: E402
from research.g9.cuda_qualification import stage2_cuda_execution_contract as contract  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate-9 non-scientific core qualification")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--qualify-self-test", action="store_true")
    parser.add_argument("--reviewed")
    args = parser.parse_args()
    try:
        if args.plan:
            if args.reviewed is not None:
                raise qualifier.CoreQualificationError("--reviewed is only for --qualify-self-test")
            result = qualifier.build_plan()
        else:
            result = qualifier.run_qualification(args.reviewed)
    except qualifier.CoreQualificationError as exc:
        print("FAIL Gate-9 core qualification: " + str(exc), file=sys.stderr)
        return 1
    print(contract.canonical_bytes(result).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
