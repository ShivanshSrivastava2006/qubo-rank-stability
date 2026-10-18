#!/usr/bin/env python3
"""Compile the CUDA cross-check source with a host-only stub and compare against Python.

This needs an ordinary C++ compiler (``c++``, ``g++`` or ``clang++``), not
nvcc, CUDA, or a GPU.  The stub in ``cuda_qualification/host_emulation_stub``
runs the kernel serially on the CPU (the source's ``G6_LAUNCH_KERNEL`` macro
resolves to the stub's serial launch because ``__CUDACC__`` is absent), so
the check proves that the C++ transcript in
``cuda_unbalanced_energy_crosscheck.cu`` is bit-identical to
``src.g4.energy.unbalanced_energy`` over the full declared state set at all
four declared coefficient points.  It also proves the comparator detects a
deliberately reordered accumulation compiled from a scratch copy, and that
the real runner rejects the stub's device report.

Everything is built in an automatically removed temporary directory.  No
project file is written and no Gate-5 path is read.  A pass here is CPU
evidence about the transcription; it says nothing about the T4 device.
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
MODULE = ROOT / "research/g6/cuda_qualification/cuda_energy_crosscheck.py"
STUB_INCLUDE = ROOT / "research/g6/cuda_qualification/host_emulation_stub"
HOST_FLAGS = ("-std=c++17", "-O0", "-ffp-contract=off", "-fno-fast-math", "-w", "-x", "c++")
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
    specification = importlib.util.spec_from_file_location("g6_cuda_energy_crosscheck_host", MODULE)
    require(specification is not None and specification.loader is not None, "module unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def locate_compiler() -> str:
    for name in ("c++", "g++", "clang++"):
        found = shutil.which(name)
        if found:
            return found
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
        instance, points, states, _families, _pins = module._bind()
        reference = module.python_reference_bits(instance, points, states)
        source = ROOT / module.CUDA_SOURCE_REL
        temporary_path = None
        with tempfile.TemporaryDirectory(prefix="g6-cuda-t4-energy-host-emulation-") as temporary:
            temporary_path = Path(temporary)
            staged = temporary_path / "crosscheck.cu"
            staged.write_bytes(source.read_bytes())
            input_path = temporary_path / "input.words"
            input_path.write_bytes(module.encode_inputs(instance, points, states))

            binary = temporary_path / "crosscheck_host"
            build(compiler, staged, binary)
            report = execute(binary, input_path, temporary_path / "output.words")
            require(report.get("device_name") == "Tesla T4 host-emulation-stub" and report.get("device_index") == 1
                    and report.get("compute_capability") == "7.5" and report.get("backend") == "not-nvcc",
                    "host emulation did not exercise explicit non-zero T4 device selection")
            try:
                module.validate_device_report(report, len(points), len(states))
            except module.CrosscheckError:
                pass
            else:
                raise HostEmulationError("real runner would accept the emulation stub device report")
            device_index, emulated_bits, host_bits = module.decode_output(
                (temporary_path / "output.words").read_bytes(), len(points), len(states))
            require(device_index == 1, "output device index drift")
            emulated = module.compare_bits(reference, emulated_bits, points, states)
            host = module.compare_bits(reference, host_bits, points, states)
            require(emulated["mismatches"] == 0 and host["mismatches"] == 0,
                    f"host-emulated transcript mismatches: kernel={emulated['mismatches']} host={host['mismatches']}")

            mutated_text = staged.read_text(encoding="utf-8")
            require(MUTATION_OLD in mutated_text, "mutation anchor not found in CUDA source")
            mutated = temporary_path / "mutated.cu"
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
            "stub_report_rejected_by_runner": True,
            "scientific_outputs": "intentionally absent",
        }, sort_keys=True))
        return 0
    except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"FAIL CUDA T4 energy cross-check host emulation: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
