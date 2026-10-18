#!/usr/bin/env python3
"""Hardware-free fixtures for the CUDA/T4 V-14 core batch producer and its plan/merge contract.

No nvcc, CUDA runtime, GPU, or Gate-5 corpus is touched: refusals are proven
by injecting a locator, and --run-batch/--validate/--measure are never invoked
with a qualified environment.  Proven: static contract (core .cu shares every
transcript and reduction segment with the pinned engine and emits no energy
word; 64-bit cumulative controls; no assert); pins; reconstruction, D015/D016
summarisation, commitments and the no-float/no-bool rule on synthetic flags;
validation-record, measurement, plan, and cap-limited handling; release,
output-directory, atomic promotion, collision/partial/symlink/nesting
refusals; artifact validation, exact coverage, order independence, mixed/ROCm
rejection, merged index write; run-batch guard ordering; and --plan and plan
CLI byte-identical under normal and -O Python.
"""

from __future__ import annotations

import ast
import copy
from decimal import Decimal
from fractions import Fraction
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CORE = ROOT / "research/g6/cuda_qualification/cuda_v14_core_batch.py"
CONTRACT = ROOT / "research/g6/cuda_qualification/v14_core_batch_contract.py"
RUNNER = ROOT / "research/g6/run_cuda_v14_core_batches.py"
PLANNER = ROOT / "research/g6/plan_v14_cuda_core_batches.py"
CORE_SOURCE = ROOT / "research/g6/cuda_qualification/cuda_v14_core_batch_engine.cu"
ENGINE_SOURCE = ROOT / "research/g6/cuda_qualification/cuda_v14_prepared_domain_engine.cu"
BOUNDARY = ROOT / "research/g6/verify_cuda_v14_core_batch_import_boundary.py"
HOST_EMULATION = ROOT / "research/g6/verify_cuda_v14_core_batch_host_emulation.py"
NEW_PYTHON = (CORE, CONTRACT, RUNNER, PLANNER, Path(__file__).resolve(), BOUNDARY, HOST_EMULATION)


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def rejects(errors, function, *arguments, reason: str) -> None:
    try:
        function(*arguments)
    except errors:
        return
    raise FixtureError(f"accepted: {reason}")


def load(name: str, path: Path):
    specification = importlib.util.spec_from_file_location(name, path)
    require(specification is not None and specification.loader is not None, "module unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def tree_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(ROOT)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def pyc_snapshot() -> set[str]:
    return {str(p) for base in (ROOT / "src", ROOT / "research") for p in base.rglob("*.pyc")}


def segment(text: str, start: str, end: str) -> str:
    a = text.index(start)
    return text[a:text.index(end, a) + len(end)]


def check_static(core, contract) -> None:
    core_text = CORE_SOURCE.read_text(encoding="utf-8")
    engine_text = ENGINE_SOURCE.read_text(encoding="utf-8")
    code = re.sub(r"//[^\n]*", "", core_text)
    for start, end in (("__host__ __device__ static std::uint64_t canonical_index_to_mask(", "  return mask;\n}\n"),
                       ("__host__ __device__ static void prepare_decoded_transcript(", "  out->budget_square = h_budget * h_budget;\n}\n"),
                       ("__host__ __device__ static void prepare_slack_transcript(", "  out->budget_slack_square = budget_slack_square;\n}\n"),
                       ("__host__ __device__ static double unbalanced_energy_prepared_transcript(", "  return h_e;\n}\n"),
                       ("__host__ __device__ static double slack_energy_prepared_transcript(", "  return h_e;\n}\n"),
                       ("__host__ __device__ static std::uint8_t tie_flags_transcript(", "  return flags;\n}\n"),
                       ("__host__ __device__ static bool word_is_nonfinite(", "}\n"),
                       ("__global__ void min_partial_kernel(", "    partial_nonfinite[t] = nonfinite;\n  }\n}\n"),
                       ("__global__ void tie_flags_kernel(", "  }\n}\n"),
                       ("__global__ void energy_kernel(", "  }\n}\n"),
                       ("__global__ void prepare_decoded_kernel(", "  }\n}\n"),
                       ("__global__ void prepare_slack_kernel(", "  }\n}\n"),
                       ("static bool finish_minimum(", "  return have;\n}\n"),
                       ("static bool is_target_device(", "}\n"),
                       ("static bool load_inputs(", "  return ok;\n}\n"),
                       ):
        core_segment = segment(core_text, start, end).replace("kModeProduce", "kModeThroughput")
        require(core_segment == segment(engine_text, start, end), f"core segment differs from the pinned engine: {start[:50]!r}")
    for anchor in ('0x3159433431563647ULL', "constexpr std::uint64_t kModeProduce = 1;", "std::uint64_t nonfinite_total = 0;",
                   "std::uint64_t nesting_total = 0;", '\\"nonfinite_energies\\":%llu', '\\"tie_nesting_violations\\":%llu',
                   "static_cast<unsigned long long>(nonfinite_total)", "static_cast<unsigned long long>(nesting_total)",
                   "v14_core_batch_engine_cuda", 'validate ? "validate" : "produce"', "#pragma STDC FP_CONTRACT OFF",
                   "#if defined(__CUDACC__)\n#define G6_LAUNCH_KERNEL(kernel, grid, block, ...) kernel<<<grid, block>>>(__VA_ARGS__)\n#else",
                   "ok = write_words(stream, coordinate_record, 6) && write_words(stream, encoding_entries[0], tied_counts[0]) &&\n           write_words(stream, encoding_entries[1], tied_counts[1]);",
                   "if (double_to_word_any(best) != h_min_bits[enc] || best_index != h_min_index[enc]) {",
                   "std::free(host_energy);", "__global__ void tie_count_kernel(", "__global__ void tie_compact_kernel(",
                   "constexpr std::uint64_t kMaxTiedEntriesPerRun = 1ULL << 28;", "constexpr std::uint32_t kEntryFlagShift = 32;",
                   "chunk_offsets[c2] = running;", "if (running == 0 || running > counts[enc]) {", "compaction order violated",
                   "minimum state is not tied at every c_H", "tied-entry output cap exceeded", "tied_entries_written",
                   "std::free(encoding_entries[0]);", "std::calloc(tied_counts[enc], sizeof(std::uint64_t))"):
        require(anchor in core_text, f"core anchor missing: {anchor[:60]!r}")
    calls = re.findall(r"write_words\(stream, ([^,]+),", code)
    require("host_out_u" not in code and "host_out_s" not in code and "write_flags" not in code and "nesting_violations(" not in code
            and sorted(calls) == ["coordinate_record", "encoding_entries[0]", "encoding_entries[1]", "header"]
            and re.search(r"cudaMemcpy\([^;]*device_out_[us][^;]*cudaMemcpyDeviceToHost", code, flags=re.S) is None
            and re.search(r"cudaMemcpy\([^;]*device_flags(_[us]|\[enc\])[^;]*cudaMemcpyDeviceToHost", code, flags=re.S) is None,
            "core program must never copy or write energy words or per-state flag arrays")
    core_py = CORE.read_text(encoding="utf-8")
    require("decode_output" not in core_py and "output_path.read_bytes" not in core_py and "output_bytes" not in core_py
            and "def iter_output(" in core_py and 'with open(path, "rb") as stream:' in core_py
            and "MAX_TIED_ENTRIES_PER_RUN = 1 << 28" in core_py, "core Python must stream the output, never read a whole batch")
    for token in ("__shared__", "atomicAdd", "atomicMin", "fma(", "__fma", "pow(", "sqrt(", "exp(", "log(", "-ffast-math",
                  "use_fast_math", "__fmul_rn", "__dmul_rn", "isfinite", "cudaEvent", "thrust", "cub::"):
        require(token not in code, f"forbidden token in core source: {token!r}")
    require(re.search(r"\bfloat\b", code) is None, "core source must not declare fp32 values")
    for word in ("h_min_bits", "tie_indices", "tie_count", "flags_u", "host_energy"):
        require(re.search(r'std::printf\([^;]*' + word, core_text, flags=re.S) is None, f"core prints an internal value: {word}")
    require(core.DIAGNOSTIC_PAIRS == ((1024, 2048), (4096, 2048), (2048, 1024), (2048, 4096)) and core.PRIMARY_PAIR == (2048, 2048)
            and core.CH_VALUES == (1024, 2048, 4096) and core.CF_VALUES == (1024, 2048, 4096), "D015 configuration drift")
    require(core.COMPILE_FLAGS == core.engine.COMPILE_FLAGS and core.MAX_COORDINATES_PER_INVOCATION == 4096, "contract constants drift")
    require(set(contract.PRODUCER_RELATIVES) >= {core.CUDA_SOURCE_REL, core.engine.CUDA_SOURCE_REL, core.ENGINE_LIBRARY_REL,
            "research/g6/cuda_qualification/cuda_v14_core_batch.py", "research/g6/cuda_qualification/v14_core_batch_contract.py",
            "research/g6/run_cuda_v14_core_batches.py", "research/g6/plan_v14_cuda_core_batches.py"}, "producer hashes incomplete")
    for source in NEW_PYTHON:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        require(not any(isinstance(node, ast.Assert) for node in ast.walk(tree)), f"assert is not permitted: {source.name}")
    for source in (CORE, CONTRACT, RUNNER, PLANNER):
        text = source.read_text(encoding="utf-8")
        require("d011_runner" not in text.replace("src/g6/d011_runner.py::_hard_feasible", "") and "core_pass_output" not in text
                and "research/g5" not in text, f"{source.name} names a prohibited producer or corpus path")


def check_pins(core) -> None:
    observed = core.verify_pinned_inputs()
    require(observed == core.PINNED_INPUTS, "pinned inputs drifted")
    for key, value in core.engine.PINNED_INPUTS.items():
        require(core.PINNED_INPUTS[key] == value, f"core pin differs from the engine pin: {key}")
    for rel in (core.CUDA_SOURCE_REL, core.ENGINE_LIBRARY_REL, core.GROUND_TRUTH_REL, core.DECISIONS_REL, "src/g4/classification.py"):
        require(observed[rel] == hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(), f"pin stale: {rel}")
    tampered = dict(core.PINNED_INPUTS)
    tampered[core.GROUND_TRUTH_REL] = "0" * 64
    rejects(core.CoreError, core.verify_pinned_inputs, tampered, reason="drifted ground truth")


def synthetic_device(core, cache, tied_u, tied_s, min_u, min_s, flag: int = 7) -> dict:
    entries_u = sorted({*tied_u, min_u})
    entries_s = sorted({*tied_s, min_s})
    return {"unbalanced": {"h_min_bits": core.engine.float_bits(-1.5), "h_min_index": min_u, "entries": [(i, flag) for i in entries_u]},
            "slack": {"h_min_bits": core.engine.float_bits(-2.25), "h_min_index": min_s, "entries": [(i, flag) for i in entries_s]}}


def synthetic_output(core, coordinates: list[dict], slack_count: int, mode: int, device_index: int = 1) -> bytes:
    body = struct.pack("<7Q", core.OUTPUT_MAGIC, 1, mode, len(coordinates), core.DECODED_COUNT, slack_count, device_index)
    for coordinate in coordinates:
        u, s = coordinate["unbalanced"], coordinate["slack"]
        body += struct.pack("<6Q", u["h_min_bits"], u["h_min_index"], s["h_min_bits"], s["h_min_index"], len(u["entries"]), len(s["entries"]))
        for encoding in (u, s):
            body += b"".join(struct.pack("<Q", (flag << core.ENTRY_FLAG_SHIFT) | index) for index, flag in encoding["entries"])
    return body


def check_reconstruction(core, instance, ledgers, inputs, cache) -> None:
    from src.g5.domains import BinaryDomain

    points = core.engine.validation_points(ledgers)
    classifiers = core.build_classifiers(instance, inputs["lambda_ref"])
    tied_u, tied_s = [5, 77, 4096, 999_999], [3, 77, 500_000]
    device = synthetic_device(core, cache, tied_u, tied_s, 77, 3)
    record = core.coordinate_record(points[1], ledgers["0.5x"], device, cache, classifiers, inputs["f_star"], inputs["lambda_ref"])
    core.require_no_float_or_bool(record, "record")
    core.validate_record(record, points[1]["linear"], "0.5x", ledgers["0.5x"], inputs["lambda_ref_hex"], len(cache))
    primary = record["primary_c_h_2048"]["unbalanced"]
    require(primary["T_E_size"] == 4 and primary["X_E_size"] == 4 and primary["H_E_min_hex"] == (-1.5).hex()
            and primary["H_E_min_domain_index"] == 77 and primary["c_H"] == 2048 and primary["c_f"] == 2048, "primary summary drift")
    require(primary["commitments"]["T_E_domain_index_stream_sha256"]
            == hashlib.sha256(b"".join(struct.pack("<Q", i) for i in sorted(tied_u))).hexdigest(), "T_E commitment drift")
    require(primary["commitments"]["X_E_decoded_index_stream_sha256"]
            == hashlib.sha256(b"".join(struct.pack("<Q", i) for i in sorted(tied_u))).hexdigest(), "X_E commitment drift (unbalanced decode is identity)")
    labels = [classifiers[2048].label(BinaryDomain(20)[i], inputs["f_star"]) for i in sorted(tied_u)]
    require(primary["atomic_counts"] == {l: labels.count(l) for l in "ABC"} and primary["atomic_label_set"] == sorted(set(labels))
            and primary["set_label"] == classifiers[2048].label_set([BinaryDomain(20)[i] for i in sorted(tied_u)], inputs["f_star"])
            and primary["p_A"][0] + primary["p_B"][0] + primary["p_C"][0] == 4, "D016 census drift")
    slack = record["primary_c_h_2048"]["slack"]
    decoded = [cache[i][0] for i in sorted(tied_s)]
    require(slack["T_E_size"] == 3 and slack["X_E_size"] == 3 and slack["commitments"]["X_E_decoded_index_stream_sha256"]
            == hashlib.sha256(b"".join(struct.pack("<Q", core.decoded_index(x)) for x in decoded)).hexdigest(), "slack decode commitment drift")
    require(set(record["d015_diagnostics"]) == {"c_H=1024__c_f=2048", "c_H=4096__c_f=2048", "c_H=2048__c_f=1024", "c_H=2048__c_f=4096"}
            and record["commitment_descriptors"] == core.COMMITMENT_DESCRIPTORS, "diagnostic configuration drift")
    for name, summary in record["d015_diagnostics"].items():
        c_h, c_f = (int(part.split("=")[1]) for part in name.split("__"))
        require(summary["unbalanced"]["c_H"] == c_h and summary["unbalanced"]["c_f"] == c_f, "diagnostic c_H/c_f binding drift")
    require(json.loads(json.dumps(record)) == record, "record is not JSON-native")
    # Nested flags: an entry tied only at c_H=4096 is excluded from c_H<=2048 reconstructions.
    partial = synthetic_device(core, cache, tied_u, tied_s, 77, 3)
    partial["unbalanced"]["entries"] = [(i, 4 if i == 5 else 7) for i, _ in partial["unbalanced"]["entries"]]
    nested_record = core.coordinate_record(points[1], ledgers["0.5x"], partial, cache, classifiers, inputs["f_star"], inputs["lambda_ref"])
    require(nested_record["primary_c_h_2048"]["unbalanced"]["T_E_size"] == 3
            and nested_record["d015_diagnostics"]["c_H=4096__c_f=2048"]["unbalanced"]["T_E_size"] == 4
            and nested_record["d015_diagnostics"]["c_H=1024__c_f=2048"]["unbalanced"]["T_E_size"] == 3, "nested reconstruction drift")
    core.validate_record(nested_record, points[1]["linear"], "0.5x", ledgers["0.5x"], inputs["lambda_ref_hex"], len(cache))
    loose = synthetic_device(core, cache, tied_u, tied_s, 77, 3)
    loose["unbalanced"]["h_min_index"] = 12
    rejects(core.CoreError, core.coordinate_record, points[1], ledgers["0.5x"], loose, cache, classifiers, inputs["f_star"], inputs["lambda_ref"],
            reason="minimum outside its own tie set")
    rejects(core.CoreError, core.require_no_float_or_bool, {"a": [1, {"b": 0.5}]}, "x", reason="float in record")
    rejects(core.CoreError, core.require_no_float_or_bool, {"a": True}, "x", reason="bool in record")
    require(core.decoded_index(BinaryDomain(20)[0xABCDE]) == 0xABCDE, "decoded index drift")
    # Large tie sets with bounded work: 20,000 tied states through the full path; all 2^20 through reconstruction/commitments.
    large = list(range(0, 20_000 * 52, 52))
    big = synthetic_device(core, cache, large, large, large[7], large[9])
    big_record = core.coordinate_record(points[4], ledgers["2x"], big, cache, classifiers, inputs["f_star"], inputs["lambda_ref"])
    core.validate_record(big_record, points[4]["linear"], "2x", ledgers["2x"], inputs["lambda_ref_hex"], len(cache))
    require(big_record["primary_c_h_2048"]["unbalanced"]["T_E_size"] == 20_000 and big_record["primary_c_h_2048"]["slack"]["X_E_size"] == 20_000,
            "large tie set summary drift")
    all_tied = [(i, 7) for i in range(core.DECODED_COUNT)]
    reconstruction = core.reconstruct("unbalanced", all_tied, 2048, cache)
    require(len(reconstruction["tied_indices"]) == core.DECODED_COUNT and reconstruction["decoded_indices"] == list(range(core.DECODED_COUNT)),
            "all-tied reconstruction drift")
    reconstruction = core.reconstruct("slack", all_tied[:len(cache)], 1024, cache)
    require(len(reconstruction["decoded_indices"]) == len(cache), "all-tied slack reconstruction drift")
    del reconstruction, all_tied
    # Streaming reader: strict per-coordinate validation, bounded reading, cap enforcement, exact EOF.
    n = len(cache)
    with tempfile.TemporaryDirectory(prefix="g6-core-stream-") as temporary:
        path = Path(temporary) / "out.words"
        two = [synthetic_device(core, cache, [1, 2], [4], 1, 4), synthetic_device(core, cache, [9], [8, 9], 9, 8)]
        path.write_bytes(synthetic_output(core, two, n, core.MODE_PRODUCE))
        streamed = [c for _, c in core.iter_output(path, 2, n, core.MODE_PRODUCE)]
        require(len(streamed) == 2 and streamed[0]["unbalanced"]["entries"] == [(1, 7), (2, 7)] and streamed[1]["slack"]["entries"] == [(8, 7), (9, 7)],
                "streaming decode drift")
        # Truncated second coordinate: the first is yielded before the truncation is reached (no whole-file read).
        path.write_bytes(synthetic_output(core, two, n, core.MODE_PRODUCE)[:-8])
        iterator = core.iter_output(path, 2, n, core.MODE_PRODUCE)
        require(next(iterator)[1]["unbalanced"]["entries"] == [(1, 7), (2, 7)], "first coordinate not streamed before truncation")
        rejects(core.CoreError, lambda: next(iterator), reason="truncated second coordinate")
        for label, mutate in (("mode", lambda b: b[:16] + struct.pack("<Q", 0) + b[24:]),
                              ("extra data", lambda b: b + b"\0" * 8),
                              ("descending order", lambda b: b.replace(struct.pack("<QQ", (7 << 32) | 1, (7 << 32) | 2), struct.pack("<QQ", (7 << 32) | 2, (7 << 32) | 1))),
                              ("illegal flag", lambda b: b.replace(struct.pack("<Q", (7 << 32) | 2), struct.pack("<Q", (3 << 32) | 2))),
                              ("minimum not fully tied", lambda b: b.replace(struct.pack("<Q", (7 << 32) | 1), struct.pack("<Q", (6 << 32) | 1)))):
            path.write_bytes(mutate(synthetic_output(core, two, n, core.MODE_PRODUCE)))
            rejects(core.CoreError, lambda: list(core.iter_output(path, 2, n, core.MODE_PRODUCE)), reason=label)
        capped = struct.pack("<7Q", core.OUTPUT_MAGIC, 1, 1, 1, core.DECODED_COUNT, n, 1) + struct.pack("<6Q", 0, 0, 0, 0, core.MAX_TIED_ENTRIES_PER_RUN + 1, 1)
        path.write_bytes(capped)
        rejects(core.CoreError, lambda: list(core.iter_output(path, 1, n, core.MODE_PRODUCE)), reason="declared entries above the cap (refused before reading them)")
    bits, index, flags = core.engine.canonical_reduction([core.engine.float_bits(v) for v in (2.0, 1.0, 1.0, 3.0)], 1.0)
    reference = (bits, index, flags)
    require(core.compare_compact({"h_min_bits": bits, "h_min_index": index, "entries": core.compact_from_flags(flags)}, reference)
            == {"h_min_bits_mismatch": 0, "h_min_index_mismatch": 0, "tie_entry_mismatches": 0}, "compact comparator clean drift")
    require(core.compare_compact({"h_min_bits": bits, "h_min_index": 2, "entries": [(1, 7), (3, 7)]}, reference)["tie_entry_mismatches"] == 2
            and core.compare_compact({"h_min_bits": bits, "h_min_index": 2, "entries": [(1, 7), (3, 7)]}, reference)["h_min_index_mismatch"] == 1,
            "compact comparator mismatch drift")


def synthetic_qualifier(core, encoding: str) -> dict:
    qualifier = core.cuda_unbalanced if encoding == "unbalanced" else core.engine.cuda_slack
    report = {"architecture": "sm_75", "backend": "cuda-runtime", "compute_capability": "7.5", "cuda_driver_version": 13000,
              "cuda_runtime_version": 12080, "device_count": 1, "device_index": 0, "device_name": "Tesla T4",
              "device_uuid_hex": "0123456789abcdef0123456789abcdef", "device_vs_host_cxx_mismatches": 0,
              "evaluations": 6840 if encoding == "unbalanced" else 1172, "multiprocessor_count": 40, "nvcc_version": "12.8.93",
              "pci_bus_id": 0, "pci_device_id": 4, "pci_domain_id": 0, "point_count": 4,
              "probe": "unbalanced_energy_transcript_crosscheck_cuda" if encoding == "unbalanced" else qualifier.PROBE,
              "scientific_outputs": "intentionally absent", "state_count": 1710 if encoding == "unbalanced" else 293,
              "total_global_memory_bytes": 15828320256}
    nvcc_info = {"path": "/usr/local/cuda/bin/nvcc", "release": "12.8", "build": "12.8.93", "stdout": ""}
    command = core.cuda_unbalanced.compile_command(nvcc_info["path"], Path("x.cu"), Path("x"))
    ids = ["d011_primary_ell_30", "v14_2x_row_70_embedded_primary", "v14_2x_row_0_lower_endpoint", "v14_2x_row_110_upper_endpoint"]
    if encoding == "unbalanced":
        identity = qualifier.qualification_identity(report, nvcc_info, command, qualifier.PINNED_INPUTS, "b" * 64, ids, 6840)
    else:
        identity = qualifier.qualification_identity(report, nvcc_info, command, qualifier.PINNED_INPUTS, "c" * 64, "b" * 64, ids, 1172)
    return {"schema": qualifier.SCHEMA_RUN, "mode": "run", "track": "cuda-t4", "verdict": "pass",
            "gpu_vs_python": {"mismatches": 0, "evaluations": report["evaluations"]},
            "host_cxx_vs_python": {"mismatches": 0, "evaluations": report["evaluations"]},
            "qualification_identity": identity, "qualification_identity_sha256": qualifier.identity_sha256(identity),
            "device": core.cuda_unbalanced.device_fingerprint(report), "scientific_outputs": "intentionally absent"}


def synthetic_validation_record(core, cache, inputs, prerequisites) -> dict:
    per = core.DECODED_COUNT + len(cache)
    report = {"architecture": "sm_75", "backend": "cuda-runtime", "compute_capability": "7.5", "coordinate_count": 8,
              "cuda_driver_version": 13000, "cuda_runtime_version": 12080, "decoded_state_count": core.DECODED_COUNT, "device_count": 1,
              "device_index": 0, "device_name": "Tesla T4", "device_uuid_hex": "0123456789abcdef0123456789abcdef",
              "device_vs_host_cxx_mismatches": 0, "elapsed_ns_coordinates": 8_000_000_000, "elapsed_ns_prepare": 50_000_000,
              "evaluations": 8 * per, "host_reference_evaluated": True, "mode": "validate", "multiprocessor_count": 40,
              "nonfinite_energies": 0, "nvcc_version": "12.8.93", "pci_bus_id": 0, "pci_device_id": 4, "pci_domain_id": 0, "point_count": 8,
              "probe": core.PROBE, "scientific_outputs": "intentionally absent", "slack_state_count": len(cache), "state_count": per,
              "tie_nesting_violations": 0, "tied_entries_written": 16, "total_global_memory_bytes": 15828320256}
    require(core.validate_device_report(report, 8, len(cache), core.MODE_VALIDATE) is report, "canonical core report rejected")
    nvcc_info = {"path": "/usr/local/cuda/bin/nvcc", "release": "12.8", "build": "12.8.93", "stdout": ""}
    command = core.cuda_unbalanced.compile_command(nvcc_info["path"], Path("c.cu"), Path("c"))
    identity = core.core_identity(report, nvcc_info, command, core.PINNED_INPUTS, core.engine.domain_identity(cache), prerequisites, inputs)
    per_coordinate = [{"scale": s, "coordinate": {"card": c, "sector": e, "budget": b},
                       "unbalanced": {"h_min_bits_mismatch": 0, "h_min_index_mismatch": 0, "tie_entry_mismatches": 0},
                       "slack": {"h_min_bits_mismatch": 0, "h_min_index_mismatch": 0, "tie_entry_mismatches": 0}, "summary_mismatch": 0}
                      for s, (c, e, b) in core.engine.VALIDATION_COORDINATES]
    return {"schema": core.SCHEMA_VALIDATE, "mode": "validate", "track": "cuda-t4", "verdict": "pass",
            "validation": {"per_coordinate": per_coordinate, "device_vs_host_cxx_mismatches": 0,
                           "totals": {"h_min_bits_mismatches": 0, "h_min_index_mismatches": 0, "tie_entry_mismatches": 0, "summary_mismatches": 0},
                           "tied_entries_written": 16},
            "core_validation_identity": identity, "core_validation_identity_sha256": core.identity_sha256(identity),
            "device": core.cuda_unbalanced.device_fingerprint(report), "scientific_outputs": "intentionally absent"}


def synthetic_measurement(core, identity_sha256: str, samples, schema=None) -> dict:
    rendered = []
    for coordinates, coordinate, setup in samples:
        rendered.append({"coordinates": coordinates, "wall_seconds": str(Decimal(setup) + Decimal(coordinate)),
                         "setup_seconds": setup, "coordinate_seconds": coordinate})
    payload = {"schema": schema or core.SCHEMA_MEASUREMENT, "unit": "coordinates", "qualification_identity_sha256": identity_sha256,
               "samples": rendered, "measured_by": "synthetic fixture; not a measurement"}
    payload["content_sha256"] = core.content_sha256(payload)
    return payload


def check_records_and_plan(core, contract, cache, inputs):
    unbalanced, slack = synthetic_qualifier(core, "unbalanced"), synthetic_qualifier(core, "slack")
    prerequisites = core.engine.validate_prerequisite_records(unbalanced, slack)
    record = synthetic_validation_record(core, cache, inputs, prerequisites)
    identity = contract.validate_core_validation_record(record)
    sha = core.identity_sha256(identity)
    require(identity["role"] == "core-batch-producer" and identity["classifier"]["f_star_hex"] == inputs["f_star_hex"], "identity drift")
    E = contract.CoreContractError
    rejects(E, contract.validate_core_validation_record, {**record, "verdict": "fail"}, reason="failed validation")
    bad = copy.deepcopy(record); bad["validation"]["totals"]["summary_mismatches"] = 1
    rejects(E, contract.validate_core_validation_record, bad, reason="summary mismatch")
    rejects(E, contract.validate_core_validation_record, {**record, "schema": core.engine.SCHEMA_VALIDATE}, reason="non-value engine record")
    for key, value in (("gpu_name", "AMD Radeon RX 9070"), ("backend", "hip-runtime"), ("architecture", "gfx1201"), ("role", "non-value-engine"),
                       ("compile_flags", [f for f in core.COMPILE_FLAGS if f != "--fmad=false"]), ("cuda_driver_version", 0)):
        changed = copy.deepcopy(record); changed["core_validation_identity"][key] = value
        changed["core_validation_identity_sha256"] = core.identity_sha256(changed["core_validation_identity"])
        rejects(E, contract.validate_core_validation_record, changed, reason=f"identity {key}={value!r}")
    for path in (("pinned_inputs", core.CUDA_SOURCE_REL), ("pinned_inputs", "src/g4/energy.py"),
                 ("classifier", "ground_truth_sha256"), ("domain", "slack")):
        changed = copy.deepcopy(record)
        if path[1] == "slack":
            changed["core_validation_identity"]["domain"]["slack"]["logical_sha256"] = "d" * 64
        else:
            changed["core_validation_identity"][path[0]][path[1]] = "1" * 64
        changed["core_validation_identity_sha256"] = core.identity_sha256(changed["core_validation_identity"])
        rejects(E, contract.validate_core_validation_record, changed, reason=f"changed {path}")
    rejects(E, contract.validate_core_validation_record, {**record, "core_validation_identity_sha256": "0" * 64}, reason="identity hash")
    same = copy.deepcopy(record); same["core_validation_identity"]["prerequisites"]["slack_identity_sha256"] = same["core_validation_identity"]["prerequisites"]["unbalanced_identity_sha256"]
    same["core_validation_identity_sha256"] = core.identity_sha256(same["core_validation_identity"])
    rejects(E, contract.validate_core_validation_record, same, reason="one qualification identity used for both prerequisites")
    measured = contract.validate_measurement(synthetic_measurement(core, sha, [(40, "400", "600")]), sha)
    require(measured["conservative_rate_coordinates_per_second"] == "1/10" and measured["acceptance_basis"] == "duration_threshold"
            and measured["measurement_schema"] == core.SCHEMA_MEASUREMENT, "measurement derivation drift")
    rejects(E, contract.validate_measurement, synthetic_measurement(core, sha, [(40, "400", "600")], schema=core.engine.SCHEMA_THROUGHPUT_MEASUREMENT),
            sha, reason="non-value engine measurement used for core sizing")
    rejects(E, contract.validate_measurement, synthetic_measurement(core, "0" * 64, [(40, "400", "600")]), sha, reason="foreign identity")
    rejects(E, contract.validate_measurement, synthetic_measurement(core, sha, [(4095, "40", "5")]), sha, reason="short non-cap sample")
    capped = contract.validate_measurement(synthetic_measurement(core, sha, [(4096, "40", "5")]), sha)
    require(capped["acceptance_basis"] == "invocation_cap_limited", "cap-limited calibration not accepted")
    plan = contract.build_plan("0.5x", record, synthetic_measurement(core, sha, [(40, "400", "600")]))
    again = contract.build_plan("0.5x", record, synthetic_measurement(core, sha, [(40, "400", "600")]))
    require(contract.canonical_bytes(plan) == contract.canonical_bytes(again), "core plan not deterministic")
    require(plan["sizing"]["coordinates_per_batch"] == 1080 and plan["sizing"]["batch_count"] == 28 and plan["batches"][-1]["stop"] == 29791
            and plan["core_validation_identity_sha256"] == sha and plan["prerequisite_qualification_identities"] == identity["prerequisites"]
            and set(plan["source_sha256"]) == set(contract.PRODUCER_RELATIVES)
            and plan["source_sha256"]["research/g6/cuda_qualification/cuda_v14_core_batch.py"] == hashlib.sha256(CORE.read_bytes()).hexdigest()
            and plan["compile_contract"]["cuda_source_sha256"] == core.PINNED_INPUTS[core.CUDA_SOURCE_REL]
            and plan["batches"][0]["batch_id"] == "v14_0_5x_core_cuda_t4_b0000" and plan["record_schema"] == core.SCHEMA_RECORDS
            and "release record" in plan["release_rule"], "core plan binding drift")
    fast = contract.build_plan("2x", record, synthetic_measurement(core, sha, [(4096, "40", "5")]), Fraction(1))
    require(fast["sizing"]["coordinates_per_batch"] == 4096 and fast["sizing"]["cap_applied"] is True
            and fast["sizing"]["measurement_acceptance_basis"] == "invocation_cap_limited" and fast["batches"][-1]["stop"] == 1367631
            and all(b["count"] <= 4096 for b in fast["batches"]), "cap-limited core plan drift")
    over = copy.deepcopy(fast); over["sizing"]["coordinates_per_batch"] = 4097
    over["batches"] = contract.base.batch_ranges(1367631, 4097, "v14_2x_core"); over["sizing"]["batch_count"] = len(over["batches"])
    over["content_sha256"] = contract.content_sha256(over)
    rejects(E, contract.validate_plan, over, reason="plan above the invocation cap")
    tampered = copy.deepcopy(plan); tampered["prerequisite_qualification_identities"]["slack_identity_sha256"] = "9" * 64
    tampered["content_sha256"] = contract.content_sha256(tampered)
    rejects(E, contract.validate_plan, tampered, reason="plan whose prerequisites differ from its identity")
    rejects(E, contract.validate_plan, {**plan, "content_sha256": "0" * 64}, reason="unsealed plan")
    return (unbalanced, slack), record, plan


def synthetic_records(core, plan, batch, template: dict, ledger: dict) -> dict:
    """Semantically valid records: real D015/D016 summaries (shared) with each coordinate's own key/coefficients."""
    from dataclasses import asdict

    axis_count = core.engine.SCALES[plan["scale"]]["axis_count"]
    records = []
    for linear in range(batch["start"], batch["stop"]):
        card, sector, budget = core.engine.coordinate_at(linear, axis_count)
        coefficients = core.engine.coefficients_at(ledger, card, sector, budget)
        records.append({"key": {"ell_card": card, "ell_sector": sector, "ell_budget": budget,
                                "s_card_hex": ledger["coordinates"][card]["binary64_hex"],
                                "s_sector_hex": ledger["coordinates"][sector]["binary64_hex"],
                                "s_budget_hex": ledger["coordinates"][budget]["binary64_hex"]},
                        "linear": linear, "scale": plan["scale"], "pass_id": plan["pass_id"],
                        "coefficients_hex": {name: value.hex() for name, value in asdict(coefficients).items()},
                        "commitment_descriptors": template["commitment_descriptors"],
                        "primary_c_h_2048": template["primary_c_h_2048"], "d015_diagnostics": template["d015_diagnostics"]})
    payload = {"schema": core.SCHEMA_RECORDS, "batch_id": batch["batch_id"], "plan_content_sha256": plan["content_sha256"],
               "pass_id": plan["pass_id"], "scale": plan["scale"], "range": {"start": batch["start"], "stop": batch["stop"], "count": batch["count"]},
               "linear_order": plan["linear_order"], "record_count": len(records), "records": records, "release_review_id": "review-x",
               "core_validation_identity_sha256": plan["core_validation_identity_sha256"]}
    payload["content_sha256"] = core.content_sha256(payload)
    return payload


def manifest_builder_for(core, plan, batch, session: str, uuid: str):
    def build(records_file_sha256: str, records_content_sha256: str) -> dict:
        fingerprint = hashlib.sha256(session.encode()).hexdigest()
        return {"schema": core.SCHEMA_MANIFEST, "batch_id": batch["batch_id"],
                "range": {"start": batch["start"], "stop": batch["stop"], "count": batch["count"]},
                "pass_id": plan["pass_id"], "scale": plan["scale"], "track": "cuda-t4", "plan_content_sha256": plan["content_sha256"],
                "linear_order": plan["linear_order"], "grid": plan["grid"], "ledger_identity": plan["ledger_identity"],
                "source_sha256": plan["source_sha256"], "core_validation_identity_sha256": plan["core_validation_identity_sha256"],
                "prerequisite_qualification_identities": plan["prerequisite_qualification_identities"],
                "slack_domain_logical_sha256": plan["slack_domain_logical_sha256"], "compile_contract": plan["compile_contract"],
                "platform": plan["platform"], "release": {"review_id": "review-x", "released_by": "owner", "date": "2026-09-21", "content_sha256": "e" * 64},
                "records": {"file": "records.json", "file_sha256": records_file_sha256, "content_sha256": records_content_sha256,
                            "record_count": batch["count"]},
                "session": {"session_id": hashlib.sha256(session.encode()).hexdigest(), "device_uuid_hex": uuid,
                            "start_platform_sha256": fingerprint, "end_platform_sha256": fingerprint},
                "timing": {"end_to_end_wall_ns": 1, "elapsed_ns_coordinates": 1}, "scientific_outputs": "in records.json only; this manifest carries none"}
    return build


def check_artifacts(core, contract, plan, ledgers, inputs, cache, instance) -> None:
    E = contract.CoreContractError
    ledger = ledgers[plan["scale"]]
    classifiers = core.build_classifiers(instance, inputs["lambda_ref"])
    point = core.engine.validation_points(ledgers)[0]
    template = core.coordinate_record(point, ledger, synthetic_device(core, cache, [5, 77, 4096], [3, 77], 77, 3), cache, classifiers,
                                      inputs["f_star"], inputs["lambda_ref"])
    with tempfile.TemporaryDirectory(prefix="g6-core-batch-fixture-") as temporary:
        root = Path(temporary).resolve()
        artifacts = root / "artifacts"
        artifacts.mkdir()
        batches = plan["batches"]
        order = list(range(len(batches)))
        order.reverse()
        for k in order:  # reverse creation order: the validator is order-agnostic
            batch = batches[k]
            final = core.promote_batch(artifacts, batch["batch_id"], synthetic_records(core, plan, batch, template, ledger),
                                       manifest_builder_for(core, plan, batch, f"session-{k}", f"{k:032x}"))
            require(final == artifacts / batch["batch_id"] and (final / "records.json").is_file() and (final / "manifest.json").is_file(),
                    "promotion did not produce the final artifact")
        require(not list(artifacts.glob(".pending-*")), "pending staging directories left behind")
        index = contract.validate_final_set(plan, artifacts)
        require(index["verdict"] == "accepted" and index["batch_count"] == len(batches) and index["total_coordinates"] == 29791
                and index["session_count"] == len(batches) and [b["batch_id"] for b in index["batches"]] == [b["batch_id"] for b in batches]
                and "records" not in json.dumps(index["batches"][0]).replace("records_file_sha256", "").replace("records_content_sha256", ""),
                "merged index drift")
        written = contract.write_merged_index(index, root / "merged_index.json")
        require(json.loads(written.read_bytes()) == index, "merged index write drift")
        rejects(E, contract.write_merged_index, index, root / "merged_index.json", reason="merged index collision")
        rejects(E, contract.write_merged_index, index, ROOT / "research/g6/merged_index.json", reason="merged index inside the repository")
        # Collision, partial, symlink, nesting, inside-repo refusals.
        batch = batches[3]
        rejects(core.CoreError, core.promote_batch, artifacts, batch["batch_id"], synthetic_records(core, plan, batch, template, ledger),
                manifest_builder_for(core, plan, batch, "s", "0" * 32), reason="artifact collision")
        rejects(core.CoreError, core.promote_batch, artifacts, "../escape", synthetic_records(core, plan, batch, template, ledger),
                manifest_builder_for(core, plan, batch, "s", "0" * 32), reason="path traversal batch id")
        rejects(core.CoreError, core.require_safe_output_dir, ROOT / "research" / "g6", reason="output inside the repository")
        rejects(core.CoreError, core.require_safe_output_dir, ROOT.parent, reason="output containing the repository")
        rejects(core.CoreError, core.require_safe_output_dir, Path("relative/dir"), reason="relative output")
        rejects(core.CoreError, core.require_safe_output_dir, root / "absent", reason="missing output directory")
        link = root / "link"
        link.symlink_to(artifacts)
        rejects(core.CoreError, core.require_safe_output_dir, link, reason="symlink output directory")
        require(core.require_safe_output_dir(artifacts) == artifacts, "safe output directory rejected")
        # Coverage / identity / semantic rejections, applied in place and restored (no tree copies).
        import shutil

        by_id = contract.validate_plan(plan)
        b1 = batches[1]["batch_id"]

        def variant(mutator, restore, whole_set: bool = False):
            """Mutate in place; single-batch cases validate that batch directly (the same validator the set uses)."""
            try:
                mutator(artifacts)
                if whole_set:
                    return contract.validate_final_set(plan, artifacts)
                return contract.validate_artifact(artifacts / b1, plan, by_id, ledger)
            finally:
                restore(artifacts)

        original_manifest = (artifacts / b1 / "manifest.json").read_bytes()
        original_records = (artifacts / b1 / "records.json").read_bytes()

        def restore_b1(r):
            (r / b1 / "manifest.json").write_bytes(original_manifest)
            (r / b1 / "records.json").write_bytes(original_records)

        def reseal_manifest(r, **changes):
            manifest = json.loads((r / b1 / "manifest.json").read_bytes())
            manifest.update(changes)
            manifest["content_sha256"] = contract.content_sha256(manifest)
            (r / b1 / "manifest.json").write_bytes(contract.canonical_bytes(manifest))

        def reseal_records(r, mutate_record):
            """Rehash a semantically corrupted records.json and its manifest binding so only semantics can reject it."""
            records = json.loads((r / b1 / "records.json").read_bytes())
            mutate_record(records["records"][2])
            records["content_sha256"] = core.content_sha256(records)
            body = core.canonical_bytes(records)
            (r / b1 / "records.json").write_bytes(body)
            manifest = json.loads((r / b1 / "manifest.json").read_bytes())
            manifest["records"]["file_sha256"] = hashlib.sha256(body).hexdigest()
            manifest["records"]["content_sha256"] = records["content_sha256"]
            manifest["content_sha256"] = contract.content_sha256(manifest)
            (r / b1 / "manifest.json").write_bytes(contract.canonical_bytes(manifest))

        b5 = batches[5]["batch_id"]
        rejects(E, variant, lambda r: shutil.move(str(r / b5), str(r / ".moved")), lambda r: shutil.move(str(r / ".moved"), str(r / b5)), True,
                reason="missing batch (gap)")
        rejects(E, variant, lambda r: reseal_manifest(r, platform={**plan["platform"], "nvcc_build": "12.4.131"}), restore_b1, True,
                reason="mixed toolchain across the set")
        rejects(E, variant, lambda r: (r / b1 / "manifest.json").unlink(), restore_b1, reason="partial artifact")
        rejects(E, variant, lambda r: (r / b1 / "records.json").write_bytes(b"{}"), restore_b1, reason="tampered records")
        rejects(E, variant, lambda r: (r / b1 / "extra.json").write_bytes(b"{}"), lambda r: (r / b1 / "extra.json").unlink(), reason="extra artifact member")
        def symlink_member(r):
            (r / b1 / "records.json").rename(r / b1 / "records.real")
            (r / b1 / "records.json").symlink_to(r / b1 / "records.real")

        def restore_member(r):
            (r / b1 / "records.json").unlink()
            (r / b1 / "records.real").rename(r / b1 / "records.json")

        rejects(E, variant, symlink_member, restore_member, reason="symlinked member")
        for label, changes in (("ROCm platform", {"platform": {**plan["platform"], "gpu_name": "AMD Radeon RX 9070"}}),
                               ("mixed toolchain", {"platform": {**plan["platform"], "nvcc_build": "12.4.131"}}),
                               ("changed core identity", {"core_validation_identity_sha256": "4" * 64}),
                               ("changed slack qualification identity", {"prerequisite_qualification_identities": {"unbalanced_identity_sha256": "a" * 64, "slack_identity_sha256": "c" * 64}}),
                               ("changed ledger", {"ledger_identity": {**plan["ledger_identity"], "content_sha256": "5" * 64}}),
                               ("foreign plan", {"plan_content_sha256": "7" * 64}),
                               ("overlapping range", {"range": {"start": batches[1]["start"] - 1, "stop": batches[1]["stop"], "count": batches[1]["count"] + 1}}),
                               ("intra-batch platform drift", {"session": {"session_id": "0" * 64, "device_uuid_hex": "0" * 32, "start_platform_sha256": "1" * 64, "end_platform_sha256": "2" * 64}})):
            rejects(E, variant, lambda r, c=changes: reseal_manifest(r, **c), restore_b1, reason=label)
        rejects(E, variant, lambda r: (r / b1 / "manifest.json").write_bytes(b'{"schema": "x"}'), restore_b1, reason="unsealed manifest")

        def set_summary(record, path, value):
            target = record
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value

        primary_u = ("primary_c_h_2048", "unbalanced")
        corruptions = (
            ("p_A numerator", lambda rec: set_summary(rec, primary_u + ("p_A",), [rec["primary_c_h_2048"]["unbalanced"]["p_A"][0] + 1, rec["primary_c_h_2048"]["unbalanced"]["p_A"][1]])),
            ("set label", lambda rec: set_summary(rec, primary_u + ("set_label",), "C" if rec["primary_c_h_2048"]["unbalanced"]["set_label"] != "C" else "A")),
            ("c_f binding", lambda rec: set_summary(rec, ("d015_diagnostics", "c_H=2048__c_f=1024", "slack", "c_f"), 4096)),
            ("c_H binding", lambda rec: set_summary(rec, ("d015_diagnostics", "c_H=1024__c_f=2048", "unbalanced", "c_H"), 2048)),
            ("extra summary key", lambda rec: set_summary(rec, primary_u + ("energy",), "0x0p+0")),
            ("missing summary key", lambda rec: rec["primary_c_h_2048"]["slack"].pop("I_C_univ")),
            ("extra top-level key", lambda rec: rec.__setitem__("note", "x")),
            ("float smuggled", lambda rec: set_summary(rec, primary_u + ("T_E_size",), 4.0)),
            ("bool smuggled", lambda rec: set_summary(rec, primary_u + ("I_C_exist",), False)),
            ("tie tau", lambda rec: set_summary(rec, primary_u + ("tie_comparator", "minimum_tau_hex"), "0x1p-40")),
            ("epsilon", lambda rec: set_summary(rec, primary_u + ("tie_comparator", "epsilon_hex"), "0x1p-53")),
            ("non-canonical hex", lambda rec: set_summary(rec, primary_u + ("H_E_min_hex",), "-0X1.8P+0")),
            ("commitment format", lambda rec: set_summary(rec, primary_u + ("commitments", "T_E_domain_index_stream_sha256"), "Z" * 64)),
            ("descriptor", lambda rec: set_summary(rec, ("commitment_descriptors", "X_E_order"), "unsorted")),
            ("minimum outside T_E span", lambda rec: set_summary(rec, primary_u + ("H_E_min_domain_index",), 10_000_000)),
            ("count sum", lambda rec: set_summary(rec, primary_u + ("atomic_counts", "B"), rec["primary_c_h_2048"]["unbalanced"]["atomic_counts"]["B"] + 1)),
            ("X_E above T_E", lambda rec: set_summary(rec, primary_u + ("X_E_size",), 99)),
            ("scan varies with c_f", lambda rec: set_summary(rec, ("d015_diagnostics", "c_H=2048__c_f=4096", "unbalanced", "H_E_min_hex"), "0x1p+0")),
            ("nesting", lambda rec: set_summary(rec, ("d015_diagnostics", "c_H=1024__c_f=2048", "unbalanced", "T_E_size"), 5)),
            ("key/linear binding", lambda rec: set_summary(rec, ("key", "ell_budget"), (rec["key"]["ell_budget"] + 1) % 31)),
            ("coefficient binding", lambda rec: set_summary(rec, ("coefficients_hex", "alpha"), "0x1p+0")),
            ("ledger coordinate binding", lambda rec: set_summary(rec, ("key", "s_card_hex"), "0x1p+0")),
            ("lambda_ref binding", lambda rec: set_summary(rec, primary_u + ("tie_comparator", "lambda_ref_hex"), "0x1p-7")),
            ("atomic label set", lambda rec: set_summary(rec, primary_u + ("atomic_label_set",), ["A", "B", "C"])),
            ("I_C_exist", lambda rec: set_summary(rec, primary_u + ("I_C_exist",), 1 - rec["primary_c_h_2048"]["unbalanced"]["I_C_exist"])),
        )
        for label, mutate in corruptions:
            rejects(E, variant, lambda r, m=mutate: reseal_records(r, m), restore_b1, reason=f"rehashed but semantically corrupted record: {label}")
        require(contract.validate_final_set(plan, artifacts)["verdict"] == "accepted", "artifact tree not restored after variants")
    # Release records.
    release = {"schema": core.SCHEMA_RELEASE, "plan_content_sha256": plan["content_sha256"], "released_by": "owner", "date": "2026-09-21",
               "review_id": "review-x", "authorizes": "run-batch"}
    release["content_sha256"] = core.content_sha256(release)
    require(core.validate_release(release, plan) == release, "release validation drift")
    rejects(core.CoreError, core.validate_release, {**release, "plan_content_sha256": "0" * 64}, plan, reason="release for another plan")
    rejects(core.CoreError, core.validate_release, {**release, "authorizes": "measure"}, plan, reason="release not authorizing run-batch")
    rejects(core.CoreError, core.validate_release, {**release, "content_sha256": "0" * 64}, plan, reason="unsealed release")
    return release


def check_run_guards(core, records, plan, release) -> None:
    batch = plan["batches"][0]

    def must_not_be_called():
        raise FixtureError("nvcc locator consulted before a guard")

    calls = []

    def never_located():
        calls.append(1)
        return None

    with tempfile.TemporaryDirectory(prefix="g6-core-batch-guard-") as temporary:
        out = Path(temporary).resolve()
        previous = os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
        try:
            for function, arguments in ((core.run_validate, (records, must_not_be_called)),
                                        (core.run_measure, (records, "2x", 0, 4, must_not_be_called)),
                                        (core.run_batch, (records, plan, batch, release, out, must_not_be_called))):
                rejects(core.CoreError, function, *arguments, reason=f"{function.__name__} without the environment guard")
        finally:
            os.environ["PYTHONDONTWRITEBYTECODE"] = "1" if previous is None else previous
        rejects(core.CoreError, core.run_batch, records, plan, batch, {**release, "authorizes": "nothing"}, out, must_not_be_called,
                reason="run-batch without a valid release")
        rejects(core.CoreError, core.run_batch, records, plan, batch, release, ROOT / "research" / "g6", must_not_be_called,
                reason="run-batch into the repository")
        for function, arguments in ((core.run_validate, (records, never_located)), (core.run_measure, (records, "0.5x", 0, 3, never_located)),
                                    (core.run_batch, (records, plan, batch, release, out, never_located))):
            calls.clear()
            try:
                function(*arguments)
            except core.CoreError as exc:
                require("nvcc is unavailable" in str(exc) and calls == [1], f"{function.__name__} no-nvcc refusal drift")
            else:
                raise FixtureError(f"{function.__name__} proceeded without nvcc")
        require(not any(out.iterdir()), "refused run-batch left files in the output directory")
    require(not list(Path(tempfile.gettempdir()).glob("g6-cuda-t4-v14-core-*")), "refused runs left temporary directories")


def check_cli(core, contract, records, record, plan) -> None:
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    before = tree_digest(ROOT / "research/g6")
    with tempfile.TemporaryDirectory(prefix="g6-core-batch-cli-") as temporary:
        d = Path(temporary)
        (d / "u.json").write_bytes(core.canonical_bytes(records[0]))
        (d / "s.json").write_bytes(core.canonical_bytes(records[1]))
        (d / "v.json").write_bytes(core.canonical_bytes(record))
        sha = record["core_validation_identity_sha256"]
        (d / "m.json").write_bytes(core.canonical_bytes(synthetic_measurement(core, sha, [(4096, "40", "5")])))
        base = [str(RUNNER), "--plan", "--unbalanced-record", str(d / "u.json"), "--slack-record", str(d / "s.json")]
        normal = subprocess.run([sys.executable, *base], cwd=ROOT, text=True, capture_output=True, check=False, env=environment)
        require(normal.returncode == 0, "CLI plan failed: " + normal.stderr[-400:])
        optimized = subprocess.run([sys.executable, "-O", *base], cwd=ROOT, text=True, capture_output=True, check=False, env=environment)
        require(optimized.stdout == normal.stdout and optimized.returncode == 0, "--plan differs under python -O")
        payload = json.loads(normal.stdout)
        require(payload["mode"] == "plan" and payload["writes"] == "none" and payload["nvcc_located"] is False
                and payload["prerequisites"]["slack_identity_sha256"] == records[1]["qualification_identity_sha256"], "plan payload drift")
        planning = [str(PLANNER), "plan", "--scale", "2x", "--validation-record", str(d / "v.json"), "--measurement", str(d / "m.json")]
        p1 = subprocess.run([sys.executable, *planning], cwd=ROOT, text=True, capture_output=True, check=False, env=environment)
        p2 = subprocess.run([sys.executable, "-O", *planning], cwd=ROOT, text=True, capture_output=True, check=False, env=environment)
        require(p1.returncode == 0 and p1.stdout == p2.stdout and json.loads(p1.stdout)["sizing"]["coordinates_per_batch"] == 4096,
                "plan CLI drift or -O difference: " + p1.stderr[-300:])
        for arguments in (["--validate"], ["--measure", "--unbalanced-record", str(d / "u.json")], ["--run-batch", "--unbalanced-record", str(d / "u.json"),
                          "--slack-record", str(d / "s.json")], ["--plan", "--run-batch"]):
            result = subprocess.run([sys.executable, str(RUNNER), *arguments], cwd=ROOT, text=True, capture_output=True, check=False, env=environment)
            require(result.returncode in (1, 2) and result.stdout == "", f"CLI accepted an incomplete invocation: {arguments}")
        no_env = {key: value for key, value in os.environ.items() if key != "PYTHONDONTWRITEBYTECODE"}
        guarded = subprocess.run([sys.executable, "-B", str(RUNNER), "--run-batch"], cwd=ROOT, text=True, capture_output=True, check=False, env=no_env)
        require(guarded.returncode == 1 and "PYTHONDONTWRITEBYTECODE=1 is required" in guarded.stderr, "CLI without the environment guard")
    require(tree_digest(ROOT / "research/g6") == before, "CLI invocations changed the research/g6 tree")


def main() -> int:
    pyc_before = pyc_snapshot()
    try:
        require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "run with PYTHONDONTWRITEBYTECODE=1")
        core = load("g6_cuda_v14_core_batch_fixture", CORE)
        contract = load("g6_v14_core_batch_contract_fixture", CONTRACT)
        check_static(core, contract)
        check_pins(core)
        from src.g4.instance import load_instance

        ledgers = core.engine.load_ledgers()
        inputs = core.classifier_inputs(ledgers)
        instance = load_instance(ROOT / core.engine.INSTANCE_REL)
        cache = core.engine.build_slack_domain(instance)
        check_reconstruction(core, instance, ledgers, inputs, cache)
        records, record, plan = check_records_and_plan(core, contract, cache, inputs)
        release = check_artifacts(core, contract, plan, ledgers, inputs, cache, instance)
        check_run_guards(core, records, plan, release)
        check_cli(core, contract, records, record, plan)
        forbidden = [name for name in sys.modules if name in {"src.g5.runner", "src.g5.core_pass", "src.g5.make_self_test", "src.g6.g5_input",
                     "src.g6.ratified_g5_input", "src.g6.g5_digest_registry", "src.g6.trial_runner", "src.g6.d011_runner"}]
        require(not forbidden, "fixtures loaded a Gate-5 corpus/runner module: " + ", ".join(forbidden))
        require(pyc_snapshot() == pyc_before, "verification wrote bytecode")
        print("PASS CUDA T4 V-14 core batch fixtures; no nvcc, GPU, core batch run, Gate-5 corpus read, bytecode, or repository write")
        return 0
    except FixtureError as exc:
        print(f"FAIL CUDA T4 V-14 core batch fixtures: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
