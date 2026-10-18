#!/usr/bin/env python3
"""Forbid future Gate-6 code from bypassing the ratified input boundary."""

from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_DIRECT_G5_INPUT_IMPORTS = {
    ROOT / "src/g6/g5_digest_registry.py",
    ROOT / "src/g6/ratified_g5_input.py",
    ROOT / "research/g6/verify_g5_input.py",
}


def _imports_structural_loader(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "src.g6.g5_input":
                return True
            if node.module == "src.g6" and any(alias.name == "g5_input" for alias in node.names):
                return True
        if isinstance(node, ast.Import) and any(alias.name == "src.g6.g5_input" for alias in node.names):
            return True
    return False


def main() -> int:
    violations: list[str] = []
    for path in tuple((ROOT / "src/g6").glob("*.py")) + tuple((ROOT / "research/g6").glob("*.py")):
        if path not in ALLOWED_DIRECT_G5_INPUT_IMPORTS and _imports_structural_loader(path):
            violations.append(str(path.relative_to(ROOT)))
    if violations:
        print("FAIL direct structural Gate-5 input import outside the approved boundary: " + ", ".join(violations),
              file=sys.stderr)
        return 1
    print("PASS Gate-6 input import boundary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
