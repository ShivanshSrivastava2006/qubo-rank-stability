#!/usr/bin/env python3
"""Prove the GPU energy benchmark cannot reach Gate-5 corpus/runner paths.

Static half: the benchmark library and runner are parsed and may not import
``src.g5``, any Gate-5 input boundary module under ``src.g6``, a Gate-6
pass/trial runner, or a dynamic-import facility other than ``importlib``
(which each uses for exactly one by-path load: the runner loads the
benchmark library, the library loads the pinned cross-check library), and
may not name a Gate-5 corpus path.  Dynamic half: the library is loaded in
a fresh interpreter with an empty PATH, its plan is built, and the module
table is inspected for any forbidden module.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "research/g6/gpu_qualification/energy_benchmark.py"
RUNNER = ROOT / "research/g6/run_gpu_energy_benchmark.py"
CROSSCHECK_LIBRARY_REL = "research/g6/gpu_qualification/energy_crosscheck.py"
BENCH_LIBRARY_REL = "research/g6/gpu_qualification/energy_benchmark.py"
PROTOTYPE_SOURCES = (LIBRARY, RUNNER)

FORBIDDEN_MODULE_PREFIXES = ("src.g5",)
FORBIDDEN_MODULES = frozenset({
    "src.g6.g5_input", "src.g6.ratified_g5_input", "src.g6.g5_digest_registry",
    "src.g6.trial_runner", "src.g6.d011_runner",
})
FORBIDDEN_PATH_FRAGMENTS = ("research/g5", "core_pass_output", "g5_identity_digest_registry")
DYNAMIC_IMPORT_NAMES = frozenset({"importlib", "runpy", "__import__", "exec", "eval"})
# Each file may use importlib for exactly one declared by-path target.
ALLOWED_BY_PATH_TARGET = {LIBRARY: CROSSCHECK_LIBRARY_REL, RUNNER: BENCH_LIBRARY_REL}
EXPECTED_LOADED = ["src", "src.g4", "src.g4.energy", "src.g4.instance", "src.g4.parameters", "src.g6", "src.g6.ledgers"]


def _module_is_forbidden(name: str) -> bool:
    return name in FORBIDDEN_MODULES or any(name == p or name.startswith(p + ".") for p in FORBIDDEN_MODULE_PREFIXES)


def static_violations(path: Path) -> list[str]:
    violations: list[str] = []
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    by_path_calls = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".")[0]
                if _module_is_forbidden(alias.name):
                    violations.append(f"import {alias.name}")
                if root_name in DYNAMIC_IMPORT_NAMES and root_name != "importlib":
                    violations.append(f"dynamic import facility: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                violations.append("relative import")
            if _module_is_forbidden(module) or module.startswith("src."):
                violations.append(f"from {module} import ... (benchmark sources import no src module directly)")
            if module.split(".")[0] in DYNAMIC_IMPORT_NAMES:
                violations.append(f"dynamic import facility: {module}")
        elif isinstance(node, ast.Name) and node.id in {"__import__", "exec", "eval"}:
            violations.append(f"dynamic facility name: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr == "spec_from_file_location":
            by_path_calls += 1
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for fragment in FORBIDDEN_PATH_FRAGMENTS:
                if fragment in node.value:
                    violations.append(f"forbidden path literal: {fragment}")
    if by_path_calls != 1:
        violations.append(f"expected exactly one by-path load, found {by_path_calls}")
    if ALLOWED_BY_PATH_TARGET[path] not in text:
        violations.append("by-path load target is not the declared module")
    return violations


DYNAMIC_PROBE = r"""
import importlib.util, json, sys
from pathlib import Path
library = Path(sys.argv[1])
specification = importlib.util.spec_from_file_location("g6_gpu_energy_benchmark_probe", library)
module = importlib.util.module_from_spec(specification)
specification.loader.exec_module(module)
plan = module.build_plan()
print(json.dumps({"loaded": sorted(name for name in sys.modules if name == "src" or name.startswith("src.")),
                  "mode": plan.get("mode"), "writes": plan.get("writes"), "hipcc": plan.get("hipcc_located")}))
"""


def dynamic_violations() -> tuple[list[str], list[str]]:
    result = subprocess.run(
        [sys.executable, "-c", DYNAMIC_PROBE, str(LIBRARY)], cwd=ROOT, text=True, capture_output=True,
        check=False, env={"PATH": "", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if result.returncode != 0:
        return ["dynamic probe failed: " + result.stderr[-400:]], []
    payload = json.loads(result.stdout)
    if payload.get("mode") != "plan" or payload.get("writes") != "none" or payload.get("hipcc") is not False:
        return ["dynamic probe did not build a no-write, no-hipcc plan"], []
    loaded = payload["loaded"]
    problems = [name for name in loaded if _module_is_forbidden(name)]
    if loaded != EXPECTED_LOADED:
        problems.append("loaded project modules differ from the cross-check's: " + ", ".join(loaded))
    return problems, loaded


def main() -> int:
    failures: list[str] = []
    for path in PROTOTYPE_SOURCES:
        for violation in static_violations(path):
            failures.append(f"{path.relative_to(ROOT)}: {violation}")
    dynamic, loaded = dynamic_violations()
    failures.extend(f"dynamic: {name}" for name in dynamic)
    if failures:
        print("FAIL GPU energy benchmark import boundary: " + "; ".join(failures), file=sys.stderr)
        return 1
    print("PASS GPU energy benchmark import boundary; project modules loaded: " + ", ".join(loaded))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
