#!/usr/bin/env python3
"""Compile the HIP cross-check source with a host-only stub and compare against Python.

This needs an ordinary C++ compiler (``c++``, ``g++`` or ``clang++``), not
HIP, ROCm, or a GPU.  The stub in ``gpu_qualification/host_emulation_stub``
runs the kernel serially on the CPU, so the check proves that the C++
transcript in ``gpu_unbalanced_energy_crosscheck.hip.cpp`` is bit-identical
to ``src.g4.energy.unbalanced_energy`` over the full declared state set at
all four declared coefficient points.  It also proves the comparator detects
a deliberately reordered accumulation compiled from a scratch copy.

Everything is built in an automatically removed temporary directory.  No
project file is written and no Gate-5 path is read.  A pass here is CPU
evidence about the transcription; it says nothing about the GPU device.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MODULE = ROOT / "research/g6/gpu_qualification/energy_crosscheck.py"
STUB_INCLUDE = ROOT / "research/g6/gpu_qualification/host_emulation_stub"
HOST_FLAGS = ("-std=c++17", "-O0", "-ffp-contract=off", "-fno-fast-math", "-w")
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
    specification = importlib.util.spec_from_file_location("g6_gpu_energy_crosscheck_host", MODULE)
    require(specification is not None and specification.loader is not None, "module unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def locate_compiler() -> str:
    for name in ("c++", "g++", "clang++"):
        found = shutil.which(name)
        if found:
            return found
    # Fedora and upstream ROCm ship clang++ with the HIP toolchain; it is an
    # ordinary host C++ compiler when invoked without --offload-arch.
    for candidate in (Path("/usr/lib64/rocm/llvm/bin/clang++"), Path("/opt/rocm/llvm/bin/clang++")):
        if candidate.is_file():
            return str(candidate)
    raise HostEmulationError("no C++ compiler (c++/g++/clang++) is available for host emulation")


def build(compiler: str, source: Path, binary: Path) -> None:
    command = [compiler, *HOST_FLAGS, f"-I{STUB_INCLUDE}", str(source), "-o", str(binary)]
    result = subprocess.run(command, cwd=source.parent, text=True, capture_output=True, check=False, timeout=600)
    require(result.returncode == 0, "host-emulation compile failed: " + result.stderr[-1500:])


def execute(binary: Path, input_path: Path, output_path: Path) -> dict:
    result = subprocess.run([str(binary), str(input_path), str(output_path)], cwd=binary.parent, text=True,
                            capture_output=True, check=False, timeout=600)
    require(result.returncode == 0, "host-emulation binary failed: " + result.stderr[-1500:])
    return json.loads(result.stdout)


def main() -> int:
    try:
        module = load_module()
        compiler = locate_compiler()
        instance, points, states, families, _pins = module._bind()
        reference = module.python_reference_bits(instance, points, states)
        source = ROOT / module.HIP_SOURCE_REL
        temporary_path = None
        with tempfile.TemporaryDirectory(prefix="g6-gpu-energy-host-emulation-") as temporary:
            temporary_path = Path(temporary)
            staged = temporary_path / "crosscheck.hip.cpp"
            staged.write_bytes(source.read_bytes())
            input_path = temporary_path / "input.words"
            input_path.write_bytes(module.encode_inputs(instance, points, states))

            binary = temporary_path / "crosscheck_host"
            build(compiler, staged, binary)
            report = execute(binary, input_path, temporary_path / "output.words")
            require(report.get("architecture") == "gfx1201-host-emulation-stub" and report.get("device_index") == 1,
                    "host emulation did not exercise explicit non-zero device selection")
            require(not module._architecture_is_target(report.get("architecture")),
                    "real runner would accept the emulation stub architecture")
            device_index, emulated_bits, host_bits = module.decode_output(
                (temporary_path / "output.words").read_bytes(), len(points), len(states))
            emulated = module.compare_bits(reference, emulated_bits, points, states)
            host = module.compare_bits(reference, host_bits, points, states)
            require(emulated["mismatches"] == 0 and host["mismatches"] == 0,
                    f"host-emulated transcript mismatches: kernel={emulated['mismatches']} host={host['mismatches']}")

            mutated_text = staged.read_text(encoding="utf-8")
            require(MUTATION_OLD in mutated_text, "mutation anchor not found in HIP source")
            mutated = temporary_path / "mutated.hip.cpp"
            mutated.write_text(mutated_text.replace(MUTATION_OLD, MUTATION_NEW), encoding="utf-8")
            mutated_binary = temporary_path / "mutated_host"
            build(compiler, mutated, mutated_binary)
            execute(mutated_binary, input_path, temporary_path / "mutated.words")
            _, mutated_bits, _ = module.decode_output((temporary_path / "mutated.words").read_bytes(),
                                                      len(points), len(states))
            detected = module.compare_bits(reference, mutated_bits, points, states)
            require(detected["mismatches"] > 0, "comparator failed to detect a reordered accumulation")
        require(temporary_path is not None and not temporary_path.exists(), "temporary directory was not removed")
        print(json.dumps({
            "verdict": "PASS",
            "compiler": compiler,
            "evaluations": emulated["evaluations"],
            "state_count": len(states),
            "point_ids": [point["point_id"] for point in points],
            "emulated_kernel_vs_python_mismatches": emulated["mismatches"],
            "host_cxx_vs_python_mismatches": host["mismatches"],
            "reordered_mutation_mismatches": detected["mismatches"],
            "scientific_outputs": "intentionally absent",
        }, sort_keys=True))
        return 0
    except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        # CrosscheckError and HostEmulationError are RuntimeError subclasses.
        print(f"FAIL GPU energy cross-check host emulation: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
