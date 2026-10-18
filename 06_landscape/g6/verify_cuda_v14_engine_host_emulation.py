#!/usr/bin/env python3
"""Host-only C++ emulation of the CUDA V-14 prepared-domain engine versus the canonical CPU services.

Needs an ordinary C++ compiler and the existing ``cuda_qualification/
host_emulation_stub`` (never nvcc, CUDA, or a GPU).  The engine runs its full
2^20 + canonical-slack-cache domains serially on the CPU for all declared
validation coordinates in validate mode.  Proven here:

* device-word agreement with ``prepare_decoded_state`` / ``prepare_slack_state``
  / ``*_energy_prepared`` over a bounded canonical reference subset (the 1710
  reviewed raw masks mapped to BinaryDomain indices, plus every cached lift of
  those states) at all declared coordinates, both encodings;
* device reduction (first-seen minimum, D015 tie flags at every c_H) equal to
  the canonical CPU reduction over the full domain, both encodings, every
  coordinate;
* host-C++ transcript agreement with the emulated kernels (program-internal);
* four scratch-only mutations (arithmetic order, tie comparator, domain
  order, slack register weight) are each rejected, and a fifth that injects
  a non-finite energy word is caught by the device-side strided count in
  throughput mode (the mode that emits no words) and refused by the runner;
* the stub's device report is rejected by the real runner.

Everything is built in an automatically removed temporary directory; no
project file is written and no Gate-5 path is read.  Energies, minima, and
tie flags exist only inside this process and that directory.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MODULE = ROOT / "research/g6/cuda_qualification/cuda_v14_engine.py"
STUB_INCLUDE = ROOT / "research/g6/cuda_qualification/host_emulation_stub"
HOST_FLAGS = ("-std=c++17", "-O0", "-ffp-contract=off", "-fno-fast-math", "-w", "-x", "c++")

# (name, anchor, replacement, detector): every anchor must be unique in the
# pinned source; every mutated build must be rejected by the named detector.
MUTATIONS = (
    ("reordered_objective_accumulation",
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
  }""", "words"),
    ("tie_comparator_scale_sign",
     "  const double scale = lambda_ref + m;\n  std::uint8_t flags = 0;",
     "  const double scale = lambda_ref - m;\n  std::uint8_t flags = 0;", "reduction"),
    ("domain_order_identity_mask",
     "    mask |= static_cast<std::uint64_t>((index >> (kAssetCount - 1 - i)) & 1u) << i;",
     "    mask |= static_cast<std::uint64_t>((index >> i) & 1u) << i;", "words"),
    ("budget_slack_weight_dropped",
     """    const double weight = static_cast<double>(1ULL << d);
    const double term = weight * y_d;
    budget_s_acc = budget_s_acc + term;""",
     """    const double term = y_d;
    budget_s_acc = budget_s_acc + term;""", "words"),
)


# Injects one non-finite (NaN) slack energy word per coordinate; detected only
# if throughput mode genuinely inspects every word on the device.
NONFINITE_MUTATION = (
    "nonfinite_slack_word_injected",
    """    out_slack[entry] = double_to_word_any(
        slack_energy_prepared_transcript(&prepared[entry_mask[entry]], &slack[entry], values));""",
    """    out_slack[entry] = double_to_word_any(
        slack_energy_prepared_transcript(&prepared[entry_mask[entry]], &slack[entry], values));
    if (entry == 777777u) out_slack[entry] = 0x7FF8000000000001ULL;""",
)


class HostEmulationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise HostEmulationError(message)


def load_module():
    specification = importlib.util.spec_from_file_location("g6_cuda_v14_engine_host", MODULE)
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
    result = subprocess.run(command, cwd=source.parent, text=True, capture_output=True, check=False, timeout=900)
    require(result.returncode == 0, "host-emulation compile failed: " + result.stderr[-1500:])


def execute(binary: Path, input_path: Path, output_path: Path) -> dict:
    result = subprocess.run([str(binary), str(input_path), str(output_path)], cwd=binary.parent, text=True,
                            capture_output=True, check=False, timeout=3600)
    require(result.returncode == 0, "host-emulation binary failed: " + result.stderr[-1500:])
    return json.loads(result.stdout)


def word_mismatches(module, decoded, reference_u, reference_s) -> int:
    total = 0
    for k in range(len(reference_u)):
        total += module.compare_words(reference_u[k], decoded["coordinates"][k]["unbalanced"]["words"])
        total += module.compare_words(reference_s[k], decoded["coordinates"][k]["slack"]["words"])
    return total


def reduction_mismatches(module, decoded, lambda_ref, coordinates) -> int:
    total = 0
    for k in coordinates:
        for encoding in ("unbalanced", "slack"):
            device = decoded["coordinates"][k][encoding]
            total += sum(module.compare_reduction(device, module.canonical_reduction(device["words"], lambda_ref)).values())
    return total


def main() -> int:
    try:
        module = load_module()
        compiler = locate_compiler()
        from research.g6.gpu_qualification import energy_crosscheck as hip
        from src.g4.instance import load_instance

        module.verify_pinned_inputs()
        ledgers = module.load_ledgers()
        lambda_ref = module.lambda_ref_from(ledgers)
        instance = load_instance(ROOT / module.INSTANCE_REL)
        cache = module.build_slack_domain(instance)
        points = module.validation_points(ledgers)
        masks, _families = hip.declared_states(instance)
        subset = sorted({module.canonical_index_to_mask(mask) for mask in masks})  # involution: masks -> indices
        reference_u, reference_s = module.cpu_reference(instance, points, cache, subset)
        subset_evaluations = sum(len(r) for r in reference_u) + sum(len(r) for r in reference_s)
        source = ROOT / module.CUDA_SOURCE_REL
        temporary_path = None
        with tempfile.TemporaryDirectory(prefix="g6-cuda-t4-v14-engine-host-emulation-") as temporary:
            temporary_path = Path(temporary)
            staged = temporary_path / "engine.cu"
            staged.write_bytes(source.read_bytes())
            input_path = temporary_path / "input.words"
            input_path.write_bytes(module.encode_inputs(instance, lambda_ref, points, cache, module.MODE_VALIDATE))
            binary = temporary_path / "engine_host"
            build(compiler, staged, binary)
            report = execute(binary, input_path, temporary_path / "output.words")
            require(report.get("device_name") == "Tesla T4 host-emulation-stub" and report.get("device_index") == 1
                    and report.get("backend") == "not-nvcc" and report.get("probe") == module.PROBE
                    and report.get("mode") == "validate" and report.get("device_vs_host_cxx_mismatches") == 0
                    and report.get("nonfinite_energies") == 0 and report.get("tie_nesting_violations") == 0
                    and report.get("decoded_state_count") == module.DECODED_COUNT
                    and report.get("slack_state_count") == len(cache)
                    and report.get("evaluations") == len(points) * (module.DECODED_COUNT + len(cache)),
                    "host emulation report drift")
            try:
                module.validate_device_report(report, len(points), len(cache), module.MODE_VALIDATE)
            except module.EngineError:
                pass
            else:
                raise HostEmulationError("real runner would accept the emulation stub device report")
            decoded = module.decode_output((temporary_path / "output.words").read_bytes(), len(points), len(cache),
                                           module.MODE_VALIDATE)
            require(decoded["device_index"] == 1, "output device index drift")
            words = word_mismatches(module, decoded, reference_u, reference_s)
            require(words == 0, f"emulated prepared-domain words mismatch the canonical CPU services: {words}")
            reductions = reduction_mismatches(module, decoded, lambda_ref, range(len(points)))
            require(reductions == 0, f"emulated reduction mismatches the canonical CPU reduction: {reductions}")

            pinned_text = staged.read_text(encoding="utf-8")
            detected = {}
            for name, anchor, replacement, detector in MUTATIONS:
                require(pinned_text.count(anchor) == 1, f"mutation anchor not unique: {name}")
                mutated = temporary_path / f"mutated_{name}.cu"
                mutated.write_text(pinned_text.replace(anchor, replacement), encoding="utf-8")
                mutated_binary = temporary_path / f"mutated_{name}"
                build(compiler, mutated, mutated_binary)
                execute(mutated_binary, input_path, temporary_path / f"{name}.words")
                mutated_decoded = module.decode_output((temporary_path / f"{name}.words").read_bytes(), len(points),
                                                       len(cache), module.MODE_VALIDATE)
                if detector == "words":
                    count = word_mismatches(module, mutated_decoded, reference_u, reference_s)
                else:
                    count = reduction_mismatches(module, mutated_decoded, lambda_ref, (0,))
                require(count > 0, f"comparator failed to detect mutation: {name}")
                detected[name] = {"detector": detector, "mismatches": count}
            # Throughput mode on the pinned source: header-only output, zero non-finite, then the injection.
            throughput_input = temporary_path / "throughput.words"
            throughput_input.write_bytes(module.encode_inputs(instance, lambda_ref, points[:2], cache, module.MODE_THROUGHPUT))
            throughput_report = execute(binary, throughput_input, temporary_path / "throughput.out")
            require(throughput_report.get("mode") == "throughput" and throughput_report.get("nonfinite_energies") == 0
                    and throughput_report.get("host_reference_evaluated") is False
                    and throughput_report.get("evaluations") == 2 * (module.DECODED_COUNT + len(cache))
                    and module.decode_output((temporary_path / "throughput.out").read_bytes(), 2, len(cache),
                                             module.MODE_THROUGHPUT)["coordinates"] == [],
                    "throughput-mode emulation report drift")
            name, anchor, replacement = NONFINITE_MUTATION
            require(pinned_text.count(anchor) == 1, f"mutation anchor not unique: {name}")
            injected = temporary_path / f"mutated_{name}.cu"
            injected.write_text(pinned_text.replace(anchor, replacement), encoding="utf-8")
            injected_binary = temporary_path / f"mutated_{name}"
            build(compiler, injected, injected_binary)
            injected_report = execute(injected_binary, throughput_input, temporary_path / f"{name}.out")
            require(injected_report.get("nonfinite_energies") == 2, "throughput mode did not count the injected non-finite words")
            try:
                module.validate_device_report({**injected_report, "device_name": "Tesla T4", "backend": "cuda-runtime",
                                               "nvcc_version": "12.8.93", "cuda_driver_version": 1, "cuda_runtime_version": 1},
                                              2, len(cache), module.MODE_THROUGHPUT)
            except module.EngineError as exc:
                require("nonfinite" in str(exc), "runner rejected the injected report for the wrong reason")
            else:
                raise HostEmulationError("runner accepted a report with non-finite energies")
            detected[name] = {"detector": "device_nonfinite_count", "mismatches": injected_report["nonfinite_energies"]}
        require(temporary_path is not None and not temporary_path.exists(), "temporary directory was not removed")
        print(json.dumps({
            "verdict": "PASS", "compiler": compiler,
            "validation_coordinates": len(points), "decoded_state_count": module.DECODED_COUNT,
            "slack_entry_count": len(cache), "slack_domain_logical_sha256": cache.logical_sha256(),
            "emulated_evaluations": report["evaluations"],
            "canonical_reference_subset_evaluations": subset_evaluations,
            "subset_word_mismatches": words, "full_domain_reduction_mismatches": reductions,
            "host_cxx_vs_emulated_mismatches": report["device_vs_host_cxx_mismatches"],
            "mutations": detected, "stub_report_rejected_by_runner": True,
            "scientific_outputs": "intentionally absent",
        }, sort_keys=True))
        return 0
    except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"FAIL CUDA T4 V-14 engine host emulation: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
