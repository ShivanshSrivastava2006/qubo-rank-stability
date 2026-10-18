#!/usr/bin/env python3
"""Ensure synthetic preparation has no canonical-instance or solver dependency."""
from __future__ import annotations

import ast
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "research/g9/cuda_qualification/stage2_cuda_preparation.py"
FORBIDDEN = ("src", "research.g5", "research.g6", "research.g7", "research.g9.stage2_generator", "numpy")


def main() -> int:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    failures: list[str] = []
    for node in ast.walk(tree):
        names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
        for name in names:
            if any(name == prefix or name.startswith(prefix + ".") for prefix in FORBIDDEN):
                failures.append(name)
    if failures:
        print("FAIL Stage-2 CUDA preparation import boundary: " + ", ".join(failures), file=sys.stderr)
        return 1
    print("PASS Stage-2 CUDA preparation import boundary; no canonical/scientific module imported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
