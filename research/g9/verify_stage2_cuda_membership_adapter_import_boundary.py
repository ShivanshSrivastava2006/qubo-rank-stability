#!/usr/bin/env python3
"""Keep the membership adapter away from canonical inputs, solvers, and writers.

Static checks cover the Python reference and the .cu; a dynamic probe imports
the reference with an empty PATH and confirms no scientific module is loaded.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "research/g9/cuda_qualification/stage2_cuda_membership_adapter.py"
CUDA_SOURCE = ROOT / "research/g9/cuda_qualification/stage2_cuda_membership_adapter.cu"
FORBIDDEN_PREFIXES = ("src", "research.g5", "research.g6", "research.g7",
                      "research.g9.stage2_generator", "research.g9.stage2_generation_contract", "numpy")
FORBIDDEN_LITERALS = ("research/canonical", "research/ground_truth", "research/g5", "research/g6",
                      "stage2_generation", "stage2_instance", "stage1_instance")
FORBIDDEN_CUDA_TOKENS = ("__shared__", "atomicAdd", "atomicMin", "fma(", "__fma", "sqrt(", "pow(",
                         "exp(", "log(", "floor(", "-ffast-math", "use_fast_math", "float ",
                         "ofstream", "fopen(", "freopen(", "std::ifstream")
REQUIRED_CUDA_ANCHORS = ("--self-test", "membership[sector][member]", "kAssetCount - 1u - asset",
                         "scientific_outputs", "intentionally absent", "register_policy",
                         "sector_weight", "budget_weight")


def static_python_violations() -> list[str]:
    failures: list[str] = []
    tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
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
        if isinstance(node, ast.Assert):
            failures.append("assert statement in the reference module")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            failures.append("reference module opens a file")
    return failures


def static_cuda_violations() -> list[str]:
    source = CUDA_SOURCE.read_text(encoding="utf-8")
    uncommented = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("//"))
    failures = [f"forbidden CUDA token: {token}" for token in FORBIDDEN_CUDA_TOKENS if token in uncommented]
    failures.extend(f"missing CUDA anchor: {anchor}" for anchor in REQUIRED_CUDA_ANCHORS if anchor not in source)
    for fragment in FORBIDDEN_LITERALS:
        if fragment in uncommented:
            failures.append("forbidden CUDA path literal: " + fragment)
    return failures


def dynamic_violations() -> list[str]:
    probe = (
        "import json,sys; from pathlib import Path; root=Path(sys.argv[1]); sys.path.insert(0,str(root)); "
        "from research.g9.cuda_qualification import stage2_cuda_membership_adapter as a; "
        "r=a.expected_self_test(); "
        "print(json.dumps({'scope':r['scientific_outputs'],'verdict':r['verdict'],"
        "'modules':sorted(k for k in sys.modules if k=='src' or k.startswith(('src.','numpy')))}))"
    )
    result = subprocess.run([sys.executable, "-c", probe, str(ROOT)], cwd=ROOT,
                            env={"PATH": "", "PYTHONDONTWRITEBYTECODE": "1"},
                            text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return ["dynamic probe failed: " + result.stderr[-400:]]
    payload = json.loads(result.stdout)
    failures: list[str] = []
    if payload["modules"]:
        failures.append("scientific module imported: " + ", ".join(payload["modules"]))
    if payload["scope"] != "intentionally absent" or payload["verdict"] != "pass":
        failures.append("reference self-test scope statement drifted")
    return failures


def main() -> int:
    failures = static_python_violations() + static_cuda_violations() + dynamic_violations()
    if failures:
        print("FAIL Stage-2 membership adapter import boundary: " + "; ".join(failures), file=sys.stderr)
        return 1
    print("PASS Stage-2 membership adapter import boundary; no canonical input, solver, or writer reachable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
