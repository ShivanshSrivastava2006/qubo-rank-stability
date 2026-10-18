#!/usr/bin/env python3
"""Prove the CUDA/T4 energy cross-check prototype cannot reach Gate-5 corpus/runner paths.

Static half: every prototype source is parsed and may not import ``src.g5``,
any Gate-5 input boundary module under ``src.g6``, a Gate-6 pass/trial
runner, or a dynamic-import facility (the prototype library), and may not
name a Gate-5 corpus path.  Dynamic half: the prototype is loaded in a fresh
interpreter, its plan is built, and the interpreter's module table is
inspected for any forbidden module.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "research/g6/cuda_qualification/cuda_energy_crosscheck.py"
RUNNER = ROOT / "research/g6/run_cuda_energy_crosscheck.py"
PROTOTYPE_SOURCES = (LIBRARY, RUNNER)

FORBIDDEN_MODULE_PREFIXES = ("src.g5",)
FORBIDDEN_MODULES = frozenset({
    "src.g6.g5_input",
    "src.g6.ratified_g5_input",
    "src.g6.g5_digest_registry",
    "src.g6.trial_runner",
    "src.g6.d011_runner",
})
FORBIDDEN_G6_NAMES = frozenset({"g5_input", "ratified_g5_input", "g5_digest_registry", "trial_runner", "d011_runner"})
FORBIDDEN_PATH_FRAGMENTS = ("research/g5", "core_pass_output", "g5_identity_digest_registry")
DYNAMIC_IMPORT_NAMES = frozenset({"importlib", "runpy", "__import__", "exec", "eval"})
ALLOWED_DYNAMIC = {RUNNER: frozenset({"importlib"})}


def _module_is_forbidden(name: str) -> bool:
    return name in FORBIDDEN_MODULES or any(name == p or name.startswith(p + ".") for p in FORBIDDEN_MODULE_PREFIXES)


def static_violations(path: Path) -> list[str]:
    violations: list[str] = []
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    allowed_dynamic = ALLOWED_DYNAMIC.get(path, frozenset())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _module_is_forbidden(alias.name):
                    violations.append(f"import {alias.name}")
                if alias.name.split(".")[0] in DYNAMIC_IMPORT_NAMES and alias.name.split(".")[0] not in allowed_dynamic:
                    violations.append(f"dynamic import facility: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                violations.append("relative import")
            if _module_is_forbidden(module):
                violations.append(f"from {module} import ...")
            if module == "src.g6" and any(alias.name in FORBIDDEN_G6_NAMES for alias in node.names):
                violations.append("from src.g6 import <forbidden>")
            if module.split(".")[0] in DYNAMIC_IMPORT_NAMES and module.split(".")[0] not in allowed_dynamic:
                violations.append(f"dynamic import facility: {module}")
        elif isinstance(node, ast.Name) and node.id in {"__import__", "exec", "eval"}:
            violations.append(f"dynamic facility name: {node.id}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for fragment in FORBIDDEN_PATH_FRAGMENTS:
                if fragment in node.value:
                    violations.append(f"forbidden path literal: {fragment}")
    return violations


DYNAMIC_PROBE = r"""
import importlib.util, json, sys
from pathlib import Path
library = Path(sys.argv[1])
specification = importlib.util.spec_from_file_location("g6_cuda_energy_crosscheck_probe", library)
module = importlib.util.module_from_spec(specification)
specification.loader.exec_module(module)
plan = module.build_plan()
print(json.dumps({"loaded": sorted(name for name in sys.modules if name == "src" or name.startswith("src.")),
                  "mode": plan.get("mode"), "writes": plan.get("writes")}))
"""


def dynamic_violations() -> tuple[list[str], list[str]]:
    result = subprocess.run(
        [sys.executable, "-c", DYNAMIC_PROBE, str(LIBRARY)], cwd=ROOT, text=True, capture_output=True,
        check=False, env={"PATH": "", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if result.returncode != 0:
        return ["dynamic probe failed: " + result.stderr[-400:]], []
    payload = json.loads(result.stdout)
    if payload.get("mode") != "plan" or payload.get("writes") != "none":
        return ["dynamic probe did not build a no-write plan"], []
    loaded = payload["loaded"]
    return [name for name in loaded if _module_is_forbidden(name)], loaded


def main() -> int:
    failures: list[str] = []
    for path in PROTOTYPE_SOURCES:
        for violation in static_violations(path):
            failures.append(f"{path.relative_to(ROOT)}: {violation}")
    dynamic, loaded = dynamic_violations()
    failures.extend(f"dynamic: {name}" for name in dynamic)
    if failures:
        print("FAIL CUDA T4 energy cross-check import boundary: " + "; ".join(failures), file=sys.stderr)
        return 1
    print("PASS CUDA T4 energy cross-check import boundary; project modules loaded: " + ", ".join(loaded))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
