#!/usr/bin/env python3
"""Compile the CUDA slack cross-check source with a host-only stub and compare against Python.

This needs an ordinary C++ compiler (``c++``, ``g++`` or ``clang++``), not
nvcc, CUDA, or a GPU.  The stub in ``cuda_qualification/host_emulation_stub``
runs the kernel serially on the CPU (the source's ``G6_LAUNCH_KERNEL`` macro
resolves to the stub's serial launch because ``__CUDACC__`` is absent), so
the check proves that the C++ transcript in
``cuda_slack_energy_crosscheck.cu`` is bit-identical to
``src.g4.energy.slack_energy`` over the whole derived lifted set (every raw
state with a canonical ``exact_slack_lift``) at all four declared coefficient
points.  It also proves the comparator detects three scratch-only mutations
(reordered objective accumulation, a flipped sector slack-delta sign, and a
dropped budget register bit weight) and that the real runner rejects the
stub's device report.

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
MODULE = ROOT / "research/g6/cuda_qualification/cuda_slack_energy_crosscheck.py"
STUB_INCLUDE = ROOT / "research/g6/cuda_qualification/host_emulation_stub"
HOST_FLAGS = ("-std=c++17", "-O0", "-ffp-contract=off", "-fno-fast-math", "-w", "-x", "c++")
# Each mutation is (name, anchor, replacement); every anchor must be unique in
# the pinned source and every mutated build must produce at least one mismatch.
MUTATIONS = (
    (
        "reordered_objective_accumulation",
        """  for (std::uint32_t i = 0; i < kAssetCount; ++i) {
    f_acc = f_acc + mu_term[i];
  }
  for (std::uint32_t index = 0; index < kSigmaCount; ++index) {
    f_acc = f_acc + quad_term[index];
  }""",
        """  for (std::uint32_t index = 0; index < kSigmaCount; ++index) {
    f_acc = f_acc + quad_term[index];
  }
  for (std::uint32_t i = 0; i < kAssetCount; ++i) {
    f_acc = f_acc + mu_term[i];
  }""",
    ),
    (
        "sector_slack_delta_sign_flip",
        "    const double slack_delta = h_sector[j] - s_acc;",
        "    const double slack_delta = h_sector[j] + s_acc;",
    ),
    (
        "budget_slack_weight_dropped",
        """    const double weight = static_cast<double>(1ULL << d);
    const double term = weight * y_d;
    budget_s_acc = budget_s_acc + term;""",
        """    const double term = y_d;
    budget_s_acc = budget_s_acc + term;""",
    ),
)


class HostEmulationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise HostEmulationError(message)


def load_module():
    specification = importlib.util.spec_from_file_location("g6_cuda_slack_energy_crosscheck_host", MODULE)
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
        instance, points, states, _families, lifted, excluded, _pins = module._bind()
        require(len(lifted) + sum(excluded.values()) == len(states) and len(lifted) > 0, "lift partition incomplete")
        reference = module.python_reference_bits(instance, points, lifted)
        source = ROOT / module.CUDA_SOURCE_REL
        temporary_path = None
        with tempfile.TemporaryDirectory(prefix="g6-cuda-t4-slack-energy-host-emulation-") as temporary:
            temporary_path = Path(temporary)
            staged = temporary_path / "crosscheck.cu"
            staged.write_bytes(source.read_bytes())
            input_path = temporary_path / "input.words"
            input_path.write_bytes(module.encode_inputs(instance, points, lifted))

            binary = temporary_path / "crosscheck_host"
            build(compiler, staged, binary)
            report = execute(binary, input_path, temporary_path / "output.words")
            require(report.get("device_name") == "Tesla T4 host-emulation-stub" and report.get("device_index") == 1
                    and report.get("compute_capability") == "7.5" and report.get("backend") == "not-nvcc"
                    and report.get("probe") == module.PROBE and report.get("state_count") == len(lifted),
                    "host emulation did not exercise explicit non-zero T4 device selection")
            try:
                module.validate_device_report(report, len(points), len(lifted))
            except module.CrosscheckError:
                pass
            else:
                raise HostEmulationError("real runner would accept the emulation stub device report")
            device_index, emulated_bits, host_bits = module.decode_output(
                (temporary_path / "output.words").read_bytes(), len(points), len(lifted))
            require(device_index == 1, "output device index drift")
            emulated = module.compare_bits(reference, emulated_bits, points, lifted)
            host = module.compare_bits(reference, host_bits, points, lifted)
            require(emulated["mismatches"] == 0 and host["mismatches"] == 0,
                    f"host-emulated transcript mismatches: kernel={emulated['mismatches']} host={host['mismatches']}")

            pinned_text = staged.read_text(encoding="utf-8")
            detected = {}
            for name, anchor, replacement in MUTATIONS:
                require(pinned_text.count(anchor) == 1, f"mutation anchor not unique in CUDA source: {name}")
                mutated = temporary_path / f"mutated_{name}.cu"
                mutated.write_text(pinned_text.replace(anchor, replacement), encoding="utf-8")
                mutated_binary = temporary_path / f"mutated_{name}"
                build(compiler, mutated, mutated_binary)
                execute(mutated_binary, input_path, temporary_path / f"{name}.words")
                _, mutated_bits, _ = module.decode_output((temporary_path / f"{name}.words").read_bytes(),
                                                          len(points), len(lifted))
                detected[name] = module.compare_bits(reference, mutated_bits, points, lifted)["mismatches"]
                require(detected[name] > 0, f"comparator failed to detect mutation: {name}")
        require(temporary_path is not None and not temporary_path.exists(), "temporary directory was not removed")
        print(json.dumps({
            "verdict": "PASS",
            "compiler": compiler,
            "evaluations": emulated["evaluations"],
            "raw_state_count": len(states),
            "lifted_count": len(lifted),
            "excluded_by_register": excluded,
            "point_ids": [point["point_id"] for point in points],
            "emulated_kernel_vs_python_mismatches": emulated["mismatches"],
            "host_cxx_vs_python_mismatches": host["mismatches"],
            "mutation_mismatches": detected,
            "stub_report_rejected_by_runner": True,
            "scientific_outputs": "intentionally absent",
        }, sort_keys=True))
        return 0
    except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"FAIL CUDA T4 slack energy cross-check host emulation: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
