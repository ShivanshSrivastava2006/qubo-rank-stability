#!/usr/bin/env python3
"""Confirm the prospective generator is isolated from candidate/scientific machinery."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]


class BoundaryError(RuntimeError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise BoundaryError(message)


def loaded_modules(optimized: bool) -> set[str]:
    code = """
import json
import sys
from research.g9 import stage2_generator
print(json.dumps(sorted(name for name in sys.modules if name.startswith(('src.', 'research.')))))
"""
    command = [sys.executable]
    if optimized:
        command.append("-O")
    command.extend(["-c", code])
    result = subprocess.run(command, cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                            capture_output=True, text=True, check=True)
    return set(json.loads(result.stdout))


def main() -> int:
    source = (ROOT / "research/g9/stage2_generator.py").read_text(encoding="utf-8")
    forbidden_text = (
        "stage1_instance.json",
        "load_instance",
        "src.g4.energy",
        "src.g5.certify",
        "src.g5.runner",
        "objective(",
        "--run",
    )
    for token in forbidden_text:
        require(token not in source, f"generator source imports or invokes forbidden boundary token: {token}")
    normal = loaded_modules(False)
    optimized = loaded_modules(True)
    require(normal == optimized, "import set differs under -O")
    require(not any(name.startswith("src.") for name in normal), "generator imports src scientific machinery")
    require(normal <= {"research.g9", "research.g9.stage2_generator"}, f"unexpected research import: {sorted(normal)}")
    print("PASS Stage-2 generator import boundary; no canonical instance or scientific solver imported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
