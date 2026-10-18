#!/usr/bin/env python3
"""Host-only C++ emulation of the CUDA V-14 core batch engine versus canonical CPU results.

Needs an ordinary C++ compiler and the existing ``host_emulation_stub`` (never
nvcc, CUDA, or a GPU).  At the eight declared validation coordinates:

* the reviewed non-value engine is emulated to obtain full-domain energy
  words, re-checked against the canonical CPU prepared services on the
  bounded reviewed-mask subset, and reduced with the canonical CPU reduction
  (first-seen minimum, D015 flags at every c_H) to the expected results;
* the core engine (which returns only minima and the deterministically
  compacted tie list, streamed one coordinate at a time) is emulated and its
  device minima/indices and compact entries must equal those expectations
  bitwise, both encodings, every coordinate, with its internal host-C++
  reference at zero mismatches and an output whose size is the tie count
  (never a per-state array);
* the host-produced D015/D016 summaries and commitments (built from the core
  flags) must equal the canonical CPU reconstruction from the expected flags,
  and an independent re-derivation here (direct DecodedClassifier labels,
  direct digest recomputation) must agree with the primary summaries;
* five scratch-only mutations (accumulation order, tie threshold, index/
  decode ordering, slack register handling, injected non-finite energy) are
  each rejected.

Everything is built in an automatically removed temporary directory; no
project file is written; energies, minima, flags, ties, and labels exist only
inside this process and that directory and are never printed.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CORE = ROOT / "research/g6/cuda_qualification/cuda_v14_core_batch.py"
STUB_INCLUDE = ROOT / "research/g6/cuda_qualification/host_emulation_stub"
HOST_FLAGS = ("-std=c++17", "-O0", "-ffp-contract=off", "-fno-fast-math", "-w", "-x", "c++")
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
  }"""),
    ("tie_comparator_scale_sign",
     "  const double scale = lambda_ref + m;\n  std::uint8_t flags = 0;",
     "  const double scale = lambda_ref - m;\n  std::uint8_t flags = 0;"),
    ("domain_order_identity_mask",
     "    mask |= static_cast<std::uint64_t>((index >> (kAssetCount - 1 - i)) & 1u) << i;",
     "    mask |= static_cast<std::uint64_t>((index >> i) & 1u) << i;"),
    ("budget_slack_weight_dropped",
     """    const double weight = static_cast<double>(1ULL << d);
    const double term = weight * y_d;
    budget_s_acc = budget_s_acc + term;""",
     """    const double term = y_d;
    budget_s_acc = budget_s_acc + term;"""),
)
NONFINITE_MUTATION = ("nonfinite_slack_word_injected",
                      """    out_slack[entry] = double_to_word_any(
        slack_energy_prepared_transcript(&prepared[entry_mask[entry]], &slack[entry], values));""",
                      """    out_slack[entry] = double_to_word_any(
        slack_energy_prepared_transcript(&prepared[entry_mask[entry]], &slack[entry], values));
    if (entry == 777777u) out_slack[entry] = 0x7FF8000000000001ULL;""")


class HostEmulationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise HostEmulationError(message)


def load_core():
    specification = importlib.util.spec_from_file_location("g6_cuda_v14_core_batch_host", CORE)
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


def stream(core, path: Path, count: int, slack_count: int, mode: int) -> list:
    """Collect the streamed per-coordinate compact results (tests only; sizes here are tiny)."""
    return [coordinate for _device_index, coordinate in core.iter_output(path, count, slack_count, mode)]


def reduction_mismatches(core, decoded, expected, coordinates) -> int:
    total = 0
    for k in coordinates:
        for encoding in ("unbalanced", "slack"):
            total += sum(core.compare_compact(decoded[k][encoding], expected[k][encoding]).values())
    return total


def independent_check(core, record, device, cache, classifiers, f_star, lambda_ref, point) -> None:
    """Re-derive the primary summaries without the core's reconstruct/summarize helpers."""
    from src.g5.domains import BinaryDomain

    domain = BinaryDomain(20)
    for encoding in ("unbalanced", "slack"):
        tied = [i for i, f in device[encoding]["entries"] if f & 2]
        seen = []
        for i in tied:
            x = domain[i] if encoding == "unbalanced" else cache[i][0]
            if x not in seen:
                seen.append(x)
        labels = [classifiers[2048].label(x, f_star) for x in seen]
        summary = record["primary_c_h_2048"][encoding]
        require(summary["T_E_size"] == len(tied) and summary["X_E_size"] == len(seen), f"{encoding}: sizes differ from the independent reconstruction")
        require(summary["atomic_counts"] == {label: labels.count(label) for label in "ABC"}, f"{encoding}: atomic counts differ")
        require(summary["set_label"] == ("C" if "C" in labels else ("A" if all(l == "A" for l in labels) else "B")), f"{encoding}: set label differs")
        require(summary["commitments"]["T_E_domain_index_stream_sha256"] == hashlib.sha256(b"".join(struct.pack("<Q", i) for i in tied)).hexdigest(),
                f"{encoding}: T_E commitment differs")
        decoded_indices = [int("".join(str(b) for b in x), 2) for x in seen]
        require(summary["commitments"]["X_E_decoded_index_stream_sha256"] == hashlib.sha256(b"".join(struct.pack("<Q", i) for i in decoded_indices)).hexdigest(),
                f"{encoding}: X_E commitment differs")
        require(summary["H_E_min_hex"] == core.engine.bits_float(device[encoding]["h_min_bits"]).hex()
                and summary["H_E_min_domain_index"] == device[encoding]["h_min_index"] in tied, f"{encoding}: minimum binding differs")
        require(summary["p_A"] == [labels.count("A"), len(seen)] and summary["I_C_exist"] == int("C" in labels)
                and summary["I_C_univ"] == int(all(l == "C" for l in labels)), f"{encoding}: fractions/indicators differ")
    require(record["linear"] == point["linear"], "record coordinate binding differs")


def main() -> int:
    try:
        core = load_core()
        engine = core.engine
        compiler = locate_compiler()
        from research.g6.gpu_qualification import energy_crosscheck as hip
        from src.g4.instance import load_instance

        core.verify_pinned_inputs()
        ledgers = engine.load_ledgers()
        inputs = core.classifier_inputs(ledgers)
        lambda_ref, f_star = inputs["lambda_ref"], inputs["f_star"]
        instance = load_instance(ROOT / engine.INSTANCE_REL)
        cache = engine.build_slack_domain(instance)
        points = engine.validation_points(ledgers)
        classifiers = core.build_classifiers(instance, lambda_ref)
        masks, _ = hip.declared_states(instance)
        subset = sorted({engine.canonical_index_to_mask(mask) for mask in masks})
        reference_u, reference_s = engine.cpu_reference(instance, points, cache, subset)
        temporary_path = None
        with tempfile.TemporaryDirectory(prefix="g6-cuda-t4-v14-core-host-emulation-") as temporary:
            temporary_path = Path(temporary)
            input_path = temporary_path / "input.words"
            input_path.write_bytes(engine.encode_inputs(instance, lambda_ref, points, cache, engine.MODE_VALIDATE))
            # 1. Reviewed engine: full-domain words -> canonical CPU reduction = expectations.
            engine_source = temporary_path / "engine.cu"
            engine_source.write_bytes((ROOT / engine.CUDA_SOURCE_REL).read_bytes())
            engine_binary = temporary_path / "engine_host"
            build(compiler, engine_source, engine_binary)
            execute(engine_binary, input_path, temporary_path / "engine.out")
            words = engine.decode_output((temporary_path / "engine.out").read_bytes(), len(points), len(cache), engine.MODE_VALIDATE)
            subset_mismatches = 0
            expected = []
            for k in range(len(points)):
                subset_mismatches += engine.compare_words(reference_u[k], words["coordinates"][k]["unbalanced"]["words"])
                subset_mismatches += engine.compare_words(reference_s[k], words["coordinates"][k]["slack"]["words"])
                expected.append({encoding: engine.canonical_reduction(words["coordinates"][k][encoding]["words"], lambda_ref)
                                 for encoding in ("unbalanced", "slack")})
            require(subset_mismatches == 0, f"reviewed engine words mismatch the canonical CPU subset: {subset_mismatches}")
            # 2. Core engine: minima and flags only.
            core_source = temporary_path / "core.cu"
            core_source.write_bytes((ROOT / core.CUDA_SOURCE_REL).read_bytes())
            core_binary = temporary_path / "core_host"
            build(compiler, core_source, core_binary)
            report = execute(core_binary, input_path, temporary_path / "core.out")
            require(report.get("probe") == core.PROBE and report.get("mode") == "validate"
                    and report.get("device_vs_host_cxx_mismatches") == 0 and report.get("nonfinite_energies") == 0
                    and report.get("tie_nesting_violations") == 0 and report.get("device_name") == "Tesla T4 host-emulation-stub"
                    and report.get("device_index") == 1 and report.get("backend") == "not-nvcc", "core emulation report drift")
            try:
                core.validate_device_report(report, len(points), len(cache), core.MODE_VALIDATE)
            except core.CoreError:
                pass
            else:
                raise HostEmulationError("real runner would accept the emulation stub device report")
            tied_total = sum(len(core.compact_from_flags(expected[k][encoding][2])) for k in range(len(points)) for encoding in ("unbalanced", "slack"))
            output_size = (temporary_path / "core.out").stat().st_size
            require(output_size == 56 + len(points) * 48 + 8 * tied_total and report.get("tied_entries_written") == tied_total,
                    "core output size is not header + per-coordinate record + one word per tied state")
            require(output_size < len(points) * (engine.DECODED_COUNT + len(cache)) // 64, "core output is not bounded by the tie count")
            decoded = stream(core, temporary_path / "core.out", len(points), len(cache), core.MODE_VALIDATE)
            reductions = reduction_mismatches(core, decoded, expected, range(len(points)))
            require(reductions == 0, f"core minima/flags mismatch the canonical CPU reduction: {reductions}")
            # 3. Summaries and commitments.
            summary_mismatches = 0
            for k, point in enumerate(points):
                ledger = ledgers[point["scale"]]
                from_device = core.coordinate_record(point, ledger, decoded[k], cache, classifiers, f_star, lambda_ref)
                canonical = {encoding: {"h_min_bits": expected[k][encoding][0], "h_min_index": expected[k][encoding][1],
                                        "entries": core.compact_from_flags(expected[k][encoding][2])} for encoding in ("unbalanced", "slack")}
                from_canonical = core.coordinate_record(point, ledger, canonical, cache, classifiers, f_star, lambda_ref)
                summary_mismatches += int(core.canonical_bytes(from_device) != core.canonical_bytes(from_canonical))
                independent_check(core, from_device, decoded[k], cache, classifiers, f_star, lambda_ref, point)
                core.validate_record(from_device, point["linear"], point["scale"], ledger, inputs["lambda_ref_hex"], len(cache))
            require(summary_mismatches == 0, f"host summaries differ from the canonical reconstruction: {summary_mismatches}")
            # 4. Mutations.
            pinned_text = core_source.read_text(encoding="utf-8")
            detected = {}
            for name, anchor, replacement in MUTATIONS:
                require(pinned_text.count(anchor) == 1, f"mutation anchor not unique: {name}")
                mutated = temporary_path / f"mutated_{name}.cu"
                mutated.write_text(pinned_text.replace(anchor, replacement), encoding="utf-8")
                mutated_binary = temporary_path / f"mutated_{name}"
                build(compiler, mutated, mutated_binary)
                try:
                    execute(mutated_binary, input_path, temporary_path / f"{name}.out")
                except HostEmulationError as exc:
                    # The program's own structural checks refused the mutated run (e.g. an empty tie set): detected.
                    require("binary failed" in str(exc), f"unexpected failure for mutation {name}: {exc}")
                    detected[name] = {"detector": "program_refused", "mismatches": 1}
                    continue
                mutated_decoded = stream(core, temporary_path / f"{name}.out", len(points), len(cache), core.MODE_VALIDATE)
                count = reduction_mismatches(core, mutated_decoded, expected, range(len(points)))
                require(count > 0, f"comparator failed to detect mutation: {name}")
                detected[name] = {"detector": "reduction", "mismatches": count}
            produce_input = temporary_path / "produce.words"
            produce_input.write_bytes(engine.encode_inputs(instance, lambda_ref, points[:2], cache, core.MODE_PRODUCE))
            produce_report = execute(core_binary, produce_input, temporary_path / "produce.out")
            require(produce_report.get("mode") == "produce" and produce_report.get("host_reference_evaluated") is False
                    and produce_report.get("nonfinite_energies") == 0, "produce-mode emulation report drift")
            produced = stream(core, temporary_path / "produce.out", 2, len(cache), core.MODE_PRODUCE)
            require(reduction_mismatches(core, produced, expected, range(2)) == 0, "produce-mode compact output differs from validate mode")
            name, anchor, replacement = NONFINITE_MUTATION
            require(pinned_text.count(anchor) == 1, "non-finite mutation anchor not unique")
            injected = temporary_path / f"mutated_{name}.cu"
            injected.write_text(pinned_text.replace(anchor, replacement), encoding="utf-8")
            injected_binary = temporary_path / f"mutated_{name}"
            build(compiler, injected, injected_binary)
            injected_report = execute(injected_binary, produce_input, temporary_path / f"{name}.out")
            require(injected_report.get("nonfinite_energies") == 2, "produce mode did not count the injected non-finite words")
            try:
                core.validate_device_report({**injected_report, "device_name": "Tesla T4", "backend": "cuda-runtime", "nvcc_version": "12.8.93",
                                             "cuda_driver_version": 1, "cuda_runtime_version": 1}, 2, len(cache), core.MODE_PRODUCE)
            except core.CoreError as exc:
                require("nonfinite" in str(exc), "runner rejected the injected report for the wrong reason")
            else:
                raise HostEmulationError("runner accepted a report with non-finite energies")
            detected[name] = {"detector": "device_nonfinite_count", "mismatches": injected_report["nonfinite_energies"]}
        require(temporary_path is not None and not temporary_path.exists(), "temporary directory was not removed")
        print(json.dumps({"verdict": "PASS", "compiler": compiler, "validation_coordinates": len(points),
                          "decoded_state_count": engine.DECODED_COUNT, "slack_entry_count": len(cache),
                          "engine_subset_word_mismatches": subset_mismatches, "core_reduction_mismatches": reductions,
                          "core_host_cxx_vs_device_mismatches": report["device_vs_host_cxx_mismatches"],
                          "summary_mismatches": summary_mismatches, "independent_reconstruction": "agreed",
                          "core_output_bytes": output_size, "tied_entries_written": tied_total,
                          "mutations": detected, "stub_report_rejected_by_runner": True,
                          "scientific_outputs": "intentionally absent"}, sort_keys=True))
        return 0
    except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"FAIL CUDA T4 V-14 core batch host emulation: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
