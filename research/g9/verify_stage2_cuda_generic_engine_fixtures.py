#!/usr/bin/env python3
"""Static/synthetic fixtures for the generic Stage-2 CUDA numerical core."""
from __future__ import annotations

import ast
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9.cuda_qualification import stage2_cuda_generic_engine as engine  # noqa: E402

SOURCE = ROOT / engine.CUDA_SOURCE_REL
RUNNER = ROOT / engine.RUNNER_REL
MODULE = ROOT / engine.SELF_REL


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def rejected(action, label: str) -> None:
    try:
        action()
    except engine.GenericCUDAEngineError:
        return
    except Exception as exc:
        raise FixtureError(f"{label}: raw {type(exc).__name__}") from exc
    raise FixtureError(f"{label}: accepted")


def static_checks() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    uncommented = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("//"))
    for anchor in ("--self-test", "__global__ void energy_kernel", "__global__ void minimum_kernel",
                   "__global__ void tie_flags_kernel", "if (candidate < best)", "word_is_nonfinite",
                   "--fmad=false", "scientific_outputs", "intentionally absent", "kLambdaRef", "frozen_tie",
                   "synthetic_control_energy", "tie_counts"):
        require(anchor in source, f"source anchor missing: {anchor}")
    for token in ("__shared__", "atomicAdd", "atomicMin", "fma(", "__fma", "pow(", "sqrt(", "exp(", "log(",
                  "-ffast-math", "use_fast_math", "float ", "ofstream", "fopen(", "open("):
        require(token not in uncommented, f"forbidden source token: {token}")
    for path in (MODULE, RUNNER, Path(__file__).resolve()):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        require(not any(isinstance(node, ast.Assert) for node in ast.walk(tree)), f"assert in {path.name}")
    require("G9_ALLOW_NONSCIENTIFIC_CUDA_QUALIFICATION" in MODULE.read_text(encoding="utf-8"), "qualification permission guard missing")


def report_checks() -> None:
    expected = engine.expected_self_test()
    report = {**expected, "device_index": 0, "device_name": "synthetic NVIDIA"}
    require(engine.validate_self_test_report(report)["verdict"] == "pass", "valid synthetic report refused")
    require(report["tie_counts"] == [[3, 4, 5]] * (engine.POINT_COUNT * engine.ENCODING_COUNT),
            "synthetic tie nesting is not load-bearing")
    for label, mutate in (
        ("checksum", lambda p: p.__setitem__("energy_checksum", "0" * 16)),
        ("nonfinite", lambda p: p.__setitem__("nonfinite_energies", 1)),
        ("scope", lambda p: p.__setitem__("scientific_outputs", "present")),
        ("float", lambda p: p.__setitem__("state_count", 257.0)),
        ("extra", lambda p: p.__setitem__("extra", 1)),
    ):
        bad = copy.deepcopy(report)
        mutate(bad)
        rejected(lambda bad=bad: engine.validate_self_test_report(bad), label)


def cli_checks() -> None:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    normal = subprocess.run([sys.executable, str(RUNNER), "--plan"], cwd=ROOT, env=env, text=True, capture_output=True, check=True)
    optimized = subprocess.run([sys.executable, "-O", str(RUNNER), "--plan"], cwd=ROOT, env=env, text=True, capture_output=True, check=True)
    require(normal.stdout == optimized.stdout, "plan differs under -O")
    payload = json.loads(normal.stdout)
    require(payload["writes"] == "none" and payload["stage2_inputs"] == "intentionally absent"
            and payload["synthetic_self_test"] == engine.expected_self_test()
            and tuple(payload["compile_flags"]) == engine.COMPILE_FLAGS, "plan payload drift")
    refused = subprocess.run([sys.executable, "-B", str(RUNNER), "--qualify-self-test", "--reviewed", "fixture"],
                             cwd=ROOT, env=env, text=True, capture_output=True, check=False)
    require(refused.returncode != 0 and "separate CUDA qualification permission" in refused.stderr,
            "qualification guard did not refuse before nvcc/GPU lookup")
    bare_env = {key: value for key, value in os.environ.items() if key != "PYTHONDONTWRITEBYTECODE"}
    bare = subprocess.run([sys.executable, "-B", str(RUNNER), "--plan"], cwd=ROOT, env=bare_env, text=True, capture_output=True, check=False)
    require(bare.returncode != 0 and "PYTHONDONTWRITEBYTECODE=1" in bare.stderr, "bytecode guard drift")


def main() -> int:
    require(not (ROOT / "research/g9/stage2_generation").exists(), "fixtures must not create a Stage-2 output")
    static_checks()
    report_checks()
    cli_checks()
    print("PASS Stage-2 generic CUDA engine fixtures; synthetic self-test only, no nvcc/GPU/Stage-2 input")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
