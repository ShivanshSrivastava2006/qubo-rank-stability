#!/usr/bin/env python3
"""Keep the generic CUDA qualification core away from canonical/scientific data paths."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
MODULES = (
    ROOT / "research/g9/cuda_qualification/stage2_cuda_generic_engine.py",
    ROOT / "research/g9/cuda_qualification/stage2_cuda_execution_contract.py",
    ROOT / "research/g9/run_stage2_cuda_generic_engine.py",
)
FORBIDDEN_PREFIXES = ("src", "research.g6", "research.g5", "research.g7", "research.g9.stage2_generator", "numpy")
FORBIDDEN_LITERALS = ("research/canonical", "research/g5", "research/g6", "stage2_generation", "stage2_instance")


def static_violations(path: Path) -> list[str]:
    failures: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            names = []
        for name in names:
            if any(name == prefix or name.startswith(prefix + ".") for prefix in FORBIDDEN_PREFIXES):
                failures.append("forbidden import: " + name)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for fragment in FORBIDDEN_LITERALS:
                if fragment in node.value:
                    failures.append("forbidden path literal: " + fragment)
    return failures


def dynamic_check() -> list[str]:
    probe = (
        "import json,sys; from pathlib import Path; root=Path(sys.argv[1]); sys.path.insert(0,str(root)); "
        "from research.g9.cuda_qualification import stage2_cuda_generic_engine as e; "
        "print(json.dumps({'writes':e.build_plan()['writes'],'modules':sorted(k for k in sys.modules if k=='src' or k.startswith('src.'))}))"
    )
    result = subprocess.run([sys.executable, "-c", probe, str(ROOT)], cwd=ROOT,
                            env={"PATH": "", "PYTHONDONTWRITEBYTECODE": "1"}, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return ["dynamic probe failed: " + result.stderr[-400:]]
    payload = json.loads(result.stdout)
    return [] if payload["writes"] == "none" and not payload["modules"] else ["dynamic plan reached a prohibited module or write mode"]


def main() -> int:
    failures = [f"{path.relative_to(ROOT)}: {item}" for path in MODULES for item in static_violations(path)]
    failures.extend(dynamic_check())
    if failures:
        print("FAIL Stage-2 generic CUDA import boundary: " + "; ".join(failures), file=sys.stderr)
        return 1
    print("PASS Stage-2 generic CUDA import boundary; no canonical/scientific module imported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
