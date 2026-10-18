#!/usr/bin/env python3
"""Prove the CUDA/T4 V-14 engine cannot reach Gate-5 corpus, registry, runner, ratified-input, or result paths.

The engine legitimately needs the canonical prepared-domain material in
``src.g5.domains`` (BinaryDomain, SlackDomainCache, build_slack_domain_cache)
and pins ``src.g5.certify`` as its reduction reference.  Every other Gate-5
module (runner, core pass, self-test), every Gate-5 input boundary module
under ``src.g6``, every Gate-6 pass/trial runner, and every dynamic-import
facility is forbidden in the engine library and CLI, and no Gate-5 corpus
path may be named.  Dynamically, the engine is loaded in a fresh
interpreter, its plan is built, and the module table is inspected.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "research/g6/cuda_qualification/cuda_v14_engine.py"
RUNNER = ROOT / "research/g6/run_cuda_v14_engine.py"
PROTOTYPE_SOURCES = (LIBRARY, RUNNER)

ALLOWED_G5_MODULES = frozenset({"src.g5.domains", "src.g5.certify"})
FORBIDDEN_MODULES = frozenset({
    "src.g5.runner", "src.g5.core_pass", "src.g5.make_self_test",
    "src.g6.g5_input", "src.g6.ratified_g5_input", "src.g6.g5_digest_registry",
    "src.g6.trial_runner", "src.g6.d011_runner", "src.g6.d011_transition_output", "src.g6.d011_matched_subgrid",
})
FORBIDDEN_G6_NAMES = frozenset({"g5_input", "ratified_g5_input", "g5_digest_registry", "trial_runner", "d011_runner",
                                "d011_transition_output", "d011_matched_subgrid"})
FORBIDDEN_G5_NAMES = frozenset({"runner", "core_pass", "make_self_test"})
FORBIDDEN_PATH_FRAGMENTS = ("research/g5", "core_pass_output", "g5_identity_digest_registry", "d011_curvature_companion/",
                            "d011_transition_output", "d011_matched_subgrid_comparison", "bounded_cpu_trial")
DYNAMIC_IMPORT_NAMES = frozenset({"importlib", "runpy", "__import__", "exec", "eval"})
ALLOWED_DYNAMIC = {RUNNER: frozenset({"importlib"})}


def _module_is_forbidden(name: str) -> bool:
    if name in FORBIDDEN_MODULES:
        return True
    # "src.g5" itself is an empty namespace package; only its submodules carry code.
    return name.startswith("src.g5.") and name not in ALLOWED_G5_MODULES


def static_violations(path: Path) -> list[str]:
    violations: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
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
            if module == "src.g5" and any(alias.name in FORBIDDEN_G5_NAMES for alias in node.names):
                violations.append("from src.g5 import <forbidden>")
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
specification = importlib.util.spec_from_file_location("g6_cuda_v14_engine_probe", library)
module = importlib.util.module_from_spec(specification)
specification.loader.exec_module(module)
plan = module.build_plan()
print(json.dumps({"loaded": sorted(name for name in sys.modules if name == "src" or name.startswith("src.")),
                  "mode": plan.get("mode"), "writes": plan.get("writes")}))
"""


def dynamic_violations() -> tuple[list[str], list[str]]:
    result = subprocess.run([sys.executable, "-c", DYNAMIC_PROBE, str(LIBRARY)], cwd=ROOT, text=True, capture_output=True,
                            check=False, env={"PATH": "", "PYTHONDONTWRITEBYTECODE": "1"})
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
        print("FAIL CUDA T4 V-14 engine import boundary: " + "; ".join(failures), file=sys.stderr)
        return 1
    print("PASS CUDA T4 V-14 engine import boundary; project modules loaded: " + ", ".join(loaded))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
