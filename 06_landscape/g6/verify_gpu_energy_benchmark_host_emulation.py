#!/usr/bin/env python3
"""Drive the benchmark's per-profile gate with a host-only stub and an ordinary C++ compiler.

Needs ``c++``/``g++``/``clang++`` only: no HIP, ROCm, or GPU.  The stub in
``gpu_qualification/host_emulation_stub_benchmark`` layers steady-clock event
shims over the cross-check stub, so ``gpu_unbalanced_energy_benchmark.hip.cpp``
(which textually includes the pinned cross-check source) compiles and runs its
repeated launches serially on the CPU.  This proves, without hardware:

* both declared profiles (``-O0`` and ``-O3``, fp contraction off, no
  fast-math) pass the 6840-evaluation cross-check gate and the harness gate
  on the host, and produce timing-only reports;
* a profile whose cross-check build is deliberately mutated is rejected at
  gate 1 with no timing measured;
* a profile whose harness build is deliberately mutated is rejected at gate
  2 with timings withheld;
* a compile command carrying a forbidden fp flag is refused outright.

Host timings are meaningless for the GPU and are not reported here.  All
builds happen in an automatically removed temporary directory; no project
file is written and no Gate-5 path is read.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Mapping

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "research/g6/gpu_qualification/energy_benchmark.py"
STUB_INCLUDE = ROOT / "research/g6/gpu_qualification/host_emulation_stub_benchmark"
HOST_FLAGS = ("-std=c++17", "-ffp-contract=off", "-fno-fast-math", "-w")
STUB_ARCHITECTURE = "gfx1201-host-emulation-stub"
WARMUP = 1
TIMED = 3
MUTATION_OLD = """  for (std::uint32_t i = 0; i < kAssetCount; ++i) {
    f_acc = f_acc + mu_term[i];
  }
  for (std::uint32_t index = 0; index < kSigmaCount; ++index) {
    f_acc = f_acc + quad_term[index];
  }"""
MUTATION_NEW = """  for (std::uint32_t index = 0; index < kSigmaCount; ++index) {
    f_acc = f_acc + quad_term[index];
  }
  for (std::uint32_t i = 0; i < kAssetCount; ++i) {
    f_acc = f_acc + mu_term[i];
  }"""


class HostEmulationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise HostEmulationError(message)


def load_module():
    specification = importlib.util.spec_from_file_location("g6_gpu_energy_benchmark_host", MODULE)
    require(specification is not None and specification.loader is not None, "module unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def locate_compiler() -> str:
    for name in ("c++", "g++", "clang++"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in (Path("/usr/lib64/rocm/llvm/bin/clang++"), Path("/opt/rocm/llvm/bin/clang++")):
        if candidate.is_file():
            return str(candidate)
    raise HostEmulationError("no C++ compiler (c++/g++/clang++) is available for host emulation")


def host_command(compiler: str, profile: Mapping[str, str], source: Path, binary: Path) -> list[str]:
    # Host analogue of the profile: same optimisation level and fp-semantics
    # flags plus the stub include path.  The AMDGPU-only device flags
    # (-mno-unsafe-fp-atomics, --offload-arch, -lamdhip64) have no host
    # analogue and are required only of the hipcc command builder.
    return [compiler, *HOST_FLAGS, profile["optimization"], f"-I{STUB_INCLUDE}", str(source), "-o", str(binary)]


FORBIDDEN_KEY_FRAGMENTS = ("energy", "minimum", "minima", "label", "rate", "tie_set", "x_e", "t_e", "value")


def float_leaves(payload, path: str = "") -> list[tuple[str, float]]:
    """Every float in a JSON-like payload with its dotted path."""
    leaves: list[tuple[str, float]] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            leaves.extend(float_leaves(value, f"{path}.{key}" if path else str(key)))
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            leaves.extend(float_leaves(value, f"{path}[{index}]"))
    elif isinstance(payload, float):
        leaves.append((path, payload))
    return leaves


def forbidden_keys(payload, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            here = f"{path}.{key}" if path else str(key)
            if any(fragment in str(key).lower() for fragment in FORBIDDEN_KEY_FRAGMENTS):
                found.append(here)
            found.extend(forbidden_keys(value, here))
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            found.extend(forbidden_keys(value, f"{path}[{index}]"))
    return found


def mutated_copy(source: Path) -> Path:
    text = source.read_text(encoding="utf-8")
    require(MUTATION_OLD in text, "mutation anchor not found in the staged cross-check source")
    mutated = source.with_name("mutated_" + source.name)
    mutated.write_text(text.replace(MUTATION_OLD, MUTATION_NEW), encoding="utf-8")
    return mutated


def main() -> int:
    try:
        module = load_module()
        compiler = locate_compiler()
        crosscheck = module.load_crosscheck()
        instance, points, states, _families = module._bind(crosscheck)
        reference = crosscheck.python_reference_bits(instance, points, states)
        encoded = crosscheck.encode_inputs(instance, points, states)
        accepts = lambda architecture: architecture == STUB_ARCHITECTURE  # noqa: E731
        require(not crosscheck._architecture_is_target(STUB_ARCHITECTURE),
                "real runner would accept the emulation stub architecture")

        def honest(profile, source, binary):
            return host_command(compiler, profile, source, binary)

        def sabotage_crosscheck(profile, source, binary):
            # Gate-1 sabotage: the cross-check binary is built from a reordered
            # accumulation.  The harness is never reached.
            if binary.name == "crosscheck":
                return host_command(compiler, profile, mutated_copy(source), binary)
            raise HostEmulationError("harness was built although the cross-check gate should have rejected")

        def sabotage_harness(profile, source, binary):
            # Gate-2 sabotage: the cross-check binary is honest, but the harness
            # includes a reordered copy of the transcript.
            if binary.name == "crosscheck":
                return host_command(compiler, profile, source, binary)
            mutated_include = mutated_copy(source.parent / module.CROSSCHECK_STAGED_NAME)
            harness_text = source.read_text(encoding="utf-8")
            require(module.INCLUDE_DIRECTIVE in harness_text, "harness include directive drift")
            mutated_harness = source.with_name("mutated_" + source.name)
            mutated_harness.write_text(harness_text.replace(module.INCLUDE_DIRECTIVE, f'#include "{mutated_include.name}"'),
                                       encoding="utf-8")
            return host_command(compiler, profile, mutated_harness, binary)

        def forbidden(profile, source, binary):
            return host_command(compiler, profile, source, binary) + ["-ffast-math"]

        summary = {}
        temporary_path = None
        with tempfile.TemporaryDirectory(prefix="g6-gpu-energy-benchmark-host-") as temporary:
            temporary_path = Path(temporary)
            for profile in module.PROFILES:
                staging = temporary_path / f"honest_{profile['profile_id']}"
                staging.mkdir()
                result = module.evaluate_profile(crosscheck, profile, staging, honest, accepts, encoded, reference,
                                                 points, states, WARMUP, TIMED)
                require(result["status"] == "accepted", f"{profile['profile_id']} rejected on host: {result.get('rejection')}")
                gate = result["crosscheck_gate"]
                bench = result["benchmark_gate"]
                require(gate["evaluations"] == bench["evaluations"] == 4 * 1710, "evaluation count drift")
                require(gate["gpu_vs_python_mismatches"] == 0 and gate["host_cxx_vs_python_mismatches"] == 0
                        and bench["last_launch_gpu_vs_python_mismatches"] == 0
                        and bench["host_cxx_vs_python_mismatches"] == 0
                        and bench["device_vs_host_cxx_mismatches_reported"] == 0, "host-emulated profile is not bit-exact")
                timings = result["timings"]
                require(timings["timed_launches"] == TIMED and timings["warmup_launches"] == WARMUP
                        and timings["timed_evaluations_total"] == TIMED * 6840
                        and len(timings["per_launch_ms"]) == 4 and timings["batch"]["launches"] == TIMED,
                        "timing summary drift")
                stray = [path for path, _value in float_leaves(result) if not path.startswith("timings.")]
                require(not stray, "result carries a floating-point value outside timings: " + ", ".join(stray))
                require(not forbidden_keys(result), "result carries a scientific key: " + ", ".join(forbidden_keys(result)))
                summary[profile["profile_id"]] = {
                    "status": result["status"],
                    "crosscheck_gate_mismatches": gate["gpu_vs_python_mismatches"],
                    "harness_gate_mismatches": bench["last_launch_gpu_vs_python_mismatches"],
                    "timed_launches": timings["timed_launches"],
                }

            candidate = module.profile_by_id("candidate_o3")
            staging = temporary_path / "sabotage_crosscheck"
            staging.mkdir()
            rejected_1 = module.evaluate_profile(crosscheck, candidate, staging, sabotage_crosscheck, accepts, encoded,
                                                 reference, points, states, WARMUP, TIMED)
            require(rejected_1["status"] == "rejected" and "timings" not in rejected_1
                    and rejected_1["benchmark_gate"] is None and rejected_1["crosscheck_gate"]["passed"] is False
                    and rejected_1["crosscheck_gate"]["gpu_vs_python_mismatches"] > 0
                    and "benchmark_compile_command" not in rejected_1,
                    "gate 1 did not reject a mutated cross-check build without timing it")

            staging = temporary_path / "sabotage_harness"
            staging.mkdir()
            rejected_2 = module.evaluate_profile(crosscheck, candidate, staging, sabotage_harness, accepts, encoded,
                                                 reference, points, states, WARMUP, TIMED)
            require(rejected_2["status"] == "rejected" and "timings" not in rejected_2
                    and rejected_2["crosscheck_gate"]["passed"] is True
                    and rejected_2["benchmark_gate"]["passed"] is False
                    and rejected_2["benchmark_gate"]["last_launch_gpu_vs_python_mismatches"] > 0,
                    "gate 2 did not withhold timings for a mutated harness build")

            staging = temporary_path / "forbidden_flag"
            staging.mkdir()
            try:
                module.evaluate_profile(crosscheck, candidate, staging, forbidden, accepts, encoded, reference,
                                        points, states, WARMUP, TIMED)
            except module.BenchmarkError as exc:
                require("forbidden compile flag" in str(exc), "forbidden-flag refusal message drift")
            else:
                raise HostEmulationError("a -ffast-math compile command was accepted")
        require(temporary_path is not None and not temporary_path.exists(), "temporary directory was not removed")
        print(json.dumps({
            "verdict": "PASS",
            "compiler": compiler,
            "profiles": summary,
            "gate1_sabotage_crosscheck_mismatches": rejected_1["crosscheck_gate"]["gpu_vs_python_mismatches"],
            "gate2_sabotage_harness_mismatches": rejected_2["benchmark_gate"]["last_launch_gpu_vs_python_mismatches"],
            "forbidden_flag_refused": True,
            "host_timings": "measured only to exercise the harness; deliberately not reported",
            "scientific_outputs": "intentionally absent",
        }, sort_keys=True))
        return 0
    except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        # BenchmarkError, CrosscheckError and HostEmulationError are RuntimeError subclasses.
        print(f"FAIL GPU energy benchmark host emulation: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
