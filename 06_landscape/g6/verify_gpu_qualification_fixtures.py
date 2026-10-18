#!/usr/bin/env python3
"""Static/no-hardware fixtures for the isolated GPU qualification track."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "research/g6/run_gpu_qualification.py"
PREFLIGHT = ROOT / "research/g6/gpu_qualification/gpu_preflight.py"
PROBE = ROOT / "research/g6/gpu_qualification/gpu_binary64_probe.hip.cpp"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    runner_text = RUNNER.read_text(encoding="utf-8")
    probe_text = PROBE.read_text(encoding="utf-8")
    require('TARGET_ARCHITECTURE = "gfx1201"' in runner_text
            and 'f"--offload-arch={TARGET_ARCHITECTURE}"' in runner_text,
            "missing RX 9070 target")
    require("-ffp-contract=off" in runner_text, "floating-point contraction is not disabled")
    require("-mno-unsafe-fp-atomics" in runner_text, "unsafe floating atomics are not disabled")
    require('"-lamdhip64"' in runner_text,
            "Fedora HIP runtime is not linked explicitly")
    require("src.g4" not in runner_text and "src.g5" not in runner_text,
            "GPU qualification runner must not reach a Gate-4/Gate-5 compute path")
    require("#pragma clang fp contract(off)" in probe_text,
            "probe source does not disable contraction in source")
    require("scientific_outputs" in probe_text and "intentionally absent" in probe_text,
            "probe must explicitly exclude scientific output")
    for source in (RUNNER, PREFLIGHT):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        require(not any(isinstance(node, ast.Assert) for node in ast.walk(tree)),
                f"assert is not permitted: {source.name}")

    # A hardware-free invocation must only report the absent toolchain; it may
    # not attempt HIP compilation or access any corpus path.
    result = subprocess.run(
        [sys.executable, str(RUNNER)], cwd=ROOT, text=True, capture_output=True, check=False,
        env={"PATH": "", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    require(result.returncode == 0, "hardware-free preflight must remain observational")
    require("blocked_missing_hipcc" in result.stdout, "preflight verdict is not fail-closed")
    print("PASS GPU qualification fixtures; no HIP compiler, corpus read, or repository write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
