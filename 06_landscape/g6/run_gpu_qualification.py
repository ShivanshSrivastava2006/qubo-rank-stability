#!/usr/bin/env python3
"""Run a non-production RX 9070 ROCm/HIP qualification step.

Default mode only inventories the machine. ``--probe`` compiles and runs a
small binary64 HIP probe in an automatically deleted temporary directory. It
does not read the Gate-5 corpus or any Gate-6 runner, and it writes no project
file. Its output is never a Gate-6 input or result.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = ROOT / "research/g6/gpu_qualification/gpu_preflight.py"
PROBE_SOURCE = ROOT / "research/g6/gpu_qualification/gpu_binary64_probe.hip.cpp"
TARGET_ARCHITECTURE = "gfx1201"


class GPUQualificationError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GPUQualificationError(message)


def _locate_hipcc() -> str | None:
    candidate = Path("/opt/rocm/bin/hipcc")
    return shutil.which("hipcc") or (str(candidate) if candidate.is_file() else None)


def _preflight() -> dict[str, Any]:
    # Import only the dedicated GPU inventory module. This path deliberately
    # cannot reach Gate-5, a Gate-6 runner, or an accepted corpus.
    import importlib.util

    specification = importlib.util.spec_from_file_location("g6_gpu_preflight", PREFLIGHT)
    _require(specification is not None and specification.loader is not None,
             "GPU preflight module is unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    result = module.collect_preflight()
    _require(isinstance(result, dict), "GPU preflight returned malformed data")
    return result


def run_probe(preflight: dict[str, Any]) -> dict[str, Any]:
    checks = preflight.get("checks")
    _require(isinstance(checks, dict) and checks.get("hip_probe_ready") is True,
             "GPU is not ready for the HIP binary64 probe; run without --probe to inspect preflight")
    hipcc = _locate_hipcc()
    _require(hipcc is not None, "hipcc disappeared after preflight")
    _require(PROBE_SOURCE.is_file(), "GPU probe source is missing")
    with tempfile.TemporaryDirectory(prefix="g6-gpu-probe-") as temporary:
        binary = Path(temporary) / "gpu_binary64_probe"
        command = [
            hipcc,
            "-std=c++17",
            "-O0",
            "-ffp-contract=off",
            "-mno-unsafe-fp-atomics",
            f"--offload-arch={TARGET_ARCHITECTURE}",
            str(PROBE_SOURCE),
            # Fedora's HIP package keeps libamdhip64 in the system library
            # path but its hipcc wrapper does not add it at link time.  Keep
            # this explicit rather than changing any floating-point flag.
            "-lamdhip64",
            "-o",
            str(binary),
        ]
        compilation = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
        _require(compilation.returncode == 0,
                 "HIP probe compilation failed; do not substitute relaxed floating-point flags")
        execution = subprocess.run([str(binary)], cwd=ROOT, text=True, capture_output=True, check=False)
        _require(execution.returncode == 0, "HIP binary64 probe failed")
        try:
            result = json.loads(execution.stdout)
        except json.JSONDecodeError as exc:
            raise GPUQualificationError("HIP probe emitted malformed JSON") from exc
        _require(isinstance(result, dict) and result.get("verdict") == "pass",
                 "HIP probe did not report bit-identical binary64 output")
        _require(isinstance(result.get("architecture"), str)
                 and result["architecture"].startswith(TARGET_ARCHITECTURE),
                 "HIP probe ran on an unexpected GPU architecture")
        return {
            "compile_command": command,
            "probe": result,
            "scientific_outputs": "intentionally absent",
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true", help="compile and run the temporary HIP probe")
    args = parser.parse_args(argv)
    try:
        preflight = _preflight()
        output: dict[str, Any] = {
            "preflight": preflight,
            "scientific_outputs": "intentionally absent",
        }
        if args.probe:
            output["binary64_probe"] = run_probe(preflight)
        print(json.dumps(output, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
        return 0
    except GPUQualificationError as exc:
        print(f"FAIL GPU qualification: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
