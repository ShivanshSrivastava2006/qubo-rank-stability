#!/usr/bin/env python3
"""Keep the tie transport away from canonical inputs, solvers, and writers."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "research/g9/cuda_qualification/stage2_cuda_tie_transport.py"
CUDA_SOURCE = ROOT / "research/g9/cuda_qualification/stage2_cuda_tie_transport.cu"
FORBIDDEN_PREFIXES = ("src", "research.g5", "research.g6", "research.g7",
                      "research.g9.stage2_generator", "research.g9.stage2_generation_contract", "numpy")
FORBIDDEN_LITERALS = ("research/canonical", "research/ground_truth", "research/g5", "research/g6",
                      "stage2_generation", "stage2_instance", "stage1_instance")
FORBIDDEN_CUDA_TOKENS = ("__shared__", "atomicAdd", "atomicMin", "atomicExch", "fma(", "__fma",
                         "sqrt(", "pow(", "exp(", "log(", "qsort", "std::sort", "thrust",
                         "-ffast-math", "use_fast_math", "float ", "ofstream", "fopen(", "freopen(",
                         "std::ifstream", "__syncthreads")
REQUIRED_CUDA_ANCHORS = ("--self-test", "compact_word", "chunk_count_kernel", "prefix_kernel",
                         "compact_kernel", "stream_audit_kernel", "flag_is_legal",
                         "flag_violates_nesting", "scientific_outputs", "intentionally absent")


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
        "from research.g9.cuda_qualification import stage2_cuda_tie_transport as t; "
        "r=t.expected_self_test(); "
        "print(json.dumps({'scope':r['scientific_outputs'],'verdict':r['verdict'],"
        "'containers':[k for k,v in r.items() if isinstance(v,(list,tuple,dict))],"
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
    if payload["containers"]:
        failures.append("report carries a container: " + ", ".join(payload["containers"]))
    return failures


def main() -> int:
    failures = static_python_violations() + static_cuda_violations() + dynamic_violations()
    if failures:
        print("FAIL Stage-2 tie-transport import boundary: " + "; ".join(failures), file=sys.stderr)
        return 1
    print("PASS Stage-2 tie-transport import boundary; no canonical input, solver, writer, or sort reachable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
