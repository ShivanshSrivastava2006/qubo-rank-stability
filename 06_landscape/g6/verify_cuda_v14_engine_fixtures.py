#!/usr/bin/env python3
"""Hardware-free fixtures for the non-value CUDA/T4 full-domain V-14 engine.

No nvcc, CUDA runtime, GPU, or Gate-5 corpus is touched, even when nvcc is
installed: refusals are proven by injecting a locator, never by editing
PATH, and neither ``--validate`` nor ``--throughput`` is ever invoked with a
qualified environment.  Proven: static contract (qualified transcript
segments verbatim, T4/7.5 selection, flags, no shared-memory/atomic
reductions, no assert); pins; the declared validation coordinates; ledger
and per-family coefficient binding; the canonical domain identity
(re-derived); BinaryDomain-order mapping; input/output encodings; canonical
CPU reference and reduction against ``certify_prepared_domain`` and
``energy.tau``; prerequisite-record, device-report, and identity behaviour;
read-only ``--plan`` byte-identical under normal and ``-O`` Python.
"""

from __future__ import annotations

import ast
import copy
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
MODULE = ROOT / "research/g6/cuda_qualification/cuda_v14_engine.py"
RUNNER = ROOT / "research/g6/run_cuda_v14_engine.py"
CUDA_SOURCE = ROOT / "research/g6/cuda_qualification/cuda_v14_prepared_domain_engine.cu"
UNBALANCED_SOURCE = ROOT / "research/g6/cuda_qualification/cuda_unbalanced_energy_crosscheck.cu"
SLACK_SOURCE = ROOT / "research/g6/cuda_qualification/cuda_slack_energy_crosscheck.cu"
BOUNDARY = ROOT / "research/g6/verify_cuda_v14_engine_import_boundary.py"
HOST_EMULATION = ROOT / "research/g6/verify_cuda_v14_engine_host_emulation.py"
NEW_PYTHON = (MODULE, RUNNER, Path(__file__).resolve(), BOUNDARY, HOST_EMULATION)
EXPECTED_COORDINATES = (("0.5x", (0, 0, 0)), ("0.5x", (15, 15, 15)), ("0.5x", (30, 30, 30)), ("0.5x", (30, 0, 15)),
                        ("2x", (0, 0, 0)), ("2x", (70, 70, 70)), ("2x", (110, 110, 110)), ("2x", (110, 0, 55)))


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def rejects(module, function, *arguments, reason: str) -> None:
    try:
        function(*arguments)
    except module.EngineError:
        return
    raise FixtureError(f"accepted: {reason}")


def load_module():
    specification = importlib.util.spec_from_file_location("g6_cuda_v14_engine_fixture", MODULE)
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


def check_static(module) -> None:
    engine = CUDA_SOURCE.read_text(encoding="utf-8")
    code = re.sub(r"//[^\n]*", "", engine)
    unbalanced = UNBALANCED_SOURCE.read_text(encoding="utf-8")
    slack = SLACK_SOURCE.read_text(encoding="utf-8")
    prefix = segment(unbalanced, "  // _x_bits: float(bit) for each of the 20 bits.\n", "  const double h_budget = instance->b - budget_sum;\n")
    require(prefix in engine and engine.count("double xs[kAssetCount];") == 1, "prepare_decoded prefix is not the qualified transcript")
    sector = segment(slack, "    // _slack_register over this sector's y bits: S_acc starts at +0.0;\n", "    const double slack_square = slack_delta * slack_delta;\n")
    budget = segment(slack, "  // _slack_register over the budget's y bits.\n", "  const double budget_slack_square = budget_slack_delta * budget_slack_delta;\n")
    require(sector in engine and budget in engine, "prepare_slack registers are not the qualified slack transcript")
    for anchor in ("static bool is_target_device(const cudaDeviceProp& properties) {",
                   "properties.major == kTargetMajor && properties.minor == kTargetMinor",
                   'std::strstr(properties.name, "T4") != nullptr', "constexpr int kTargetMajor = 7;", "constexpr int kTargetMinor = 5;",
                   "cudaSetDevice(selected_device)", "#pragma STDC FP_CONTRACT OFF", "__CUDACC_VER_MAJOR__", '"cuda-runtime"',
                   '"not-nvcc"', "#if defined(__CUDACC__)\n#define G6_LAUNCH_KERNEL(kernel, grid, block, ...) kernel<<<grid, block>>>(__VA_ARGS__)\n#else",
                   "constexpr std::uint32_t kDecodedCount = 1u << kAssetCount;", "constexpr double kEpsilon = 0x1p-52;",
                   "return k == 0 ? 1024.0 : (k == 1 ? 2048.0 : 4096.0);", "constexpr std::uint32_t kPartialCount = 4096;",
                   "if (!have || y < best) {", "(y == best && partial_index[t] < best_index)",
                   "const double m = (abs_min > abs_y) ? abs_min : abs_y;", "if (gap <= tie_tau) {",
                   "static_cast<std::uint64_t>((index >> (kAssetCount - 1 - i)) & 1u) << i;",
                   "inputs->offsets[0] != 0 || inputs->offsets[kDecodedCount] != inputs->slack_count",
                   "inputs->offsets[d + 1] <= inputs->offsets[d]", "v14_prepared_domain_engine_cuda",
                   "checksum ^=", "deliberately not printed", "std::chrono::steady_clock::now()",
                   "return ((word >> 52) & 0x7FFULL) == 0x7FFULL;", "if (word_is_nonfinite(words[i])) ++nonfinite;",
                   "partial_nonfinite[t] = nonfinite;", "nonfinite_total += found;",
                   "device_nonfinite_this_coordinate += found;", "if (host_nonfinite != device_nonfinite_this_coordinate) {",
                   '"cudaMemcpy(partial_nonfinite)"', "std::uint64_t nonfinite_total = 0;",
                   '\\"nonfinite_energies\\":%llu,', "static_cast<unsigned long long>(nonfinite_total), nvcc_major",
                   "std::uint64_t nesting_total = 0;", '\\"tie_nesting_violations\\":%llu,',
                   "static_cast<unsigned long long>(nesting_total),", "static std::uint32_t nesting_violations("):
        require(anchor in engine, f"engine anchor missing: {anchor[:60]!r}")
    require(code.count("<<<") == 1 and code.count("g6_host_emulation_launch") == 1
            and code.count("G6_LAUNCH_KERNEL(") == 7, "launch macro use drift")
    for token in ("__shared__", "atomicAdd", "atomicMin", "fma(", "__fma", "pow(", "sqrt(", "exp(", "log(", "-ffast-math",
                  "use_fast_math", "__fmul_rn", "__dmul_rn", "__dadd_rn", "_Float", "__half", "half", "__float2", "rsqrt", "ldexp",
                  "cudaEvent", "thrust", "cub::"):
        require(token not in code, f"forbidden token in engine source: {token!r}")
    require(re.search(r"\bfloat\b", code) is None, "engine source must not declare fp32 values")
    require('std::printf(\n      "{\\"architecture\\"' in engine, "identity JSON drift")
    for word in ("h_min_bits", "tie_indices", "tie_count", "flags_u"):
        require(re.search(r'std::printf\([^;]*' + word, engine, flags=re.S) is None, f"engine prints an internal value: {word}")
    require(module.COMPILE_FLAGS == module.cuda_unbalanced.COMPILE_FLAGS, "compile flags drift")
    for flag in ("-O0", "arch=compute_75,code=sm_75", "--fmad=false", "--ftz=false", "--prec-div=true", "--prec-sqrt=true",
                 "-Xptxas", "-ffp-contract=off", "-fno-fast-math"):
        require(flag in module.COMPILE_FLAGS, f"compile contract lacks {flag}")
    require(module.VALIDATION_COORDINATES == EXPECTED_COORDINATES, "validation coordinate declaration drift")
    require({scale for scale, _ in module.VALIDATION_COORDINATES} == {"0.5x", "2x"}, "validation set must span both scales")
    for scale, triple in module.VALIDATION_COORDINATES:
        axis = module.SCALES[scale]["axis_count"]
        require(all(0 <= v < axis for v in triple), "validation coordinate outside its axis")
    require(("0.5x", (0, 0, 0)) in module.VALIDATION_COORDINATES and ("0.5x", (30, 30, 30)) in module.VALIDATION_COORDINATES
            and ("2x", (0, 0, 0)) in module.VALIDATION_COORDINATES and ("2x", (110, 110, 110)) in module.VALIDATION_COORDINATES
            and ("2x", (70, 70, 70)) in module.VALIDATION_COORDINATES, "endpoints/embedded primary missing")
    require(module.CH_VALUES == (1024, 2048, 4096) and module.DECODED_COUNT == 1 << 20
            and module.MAX_COORDINATES_PER_INVOCATION == 4096, "D015/domain/cap constants drift")
    require("isfinite" not in code, "non-finite detection must be the exact exponent-field test, not a library call")
    # The cumulative non-finite total is 64-bit (4096 coordinates x 2^21 words exceeds 2^32) and is never
    # narrowed: no 32-bit declaration, no %u format, and the bounded per-encoding/per-coordinate counts stay 32-bit.
    require("std::uint32_t nonfinite_total" not in code and '\\"nonfinite_energies\\":%u' not in code
            and "static std::uint32_t sum_partials(" in code and "std::uint32_t device_nonfinite_this_coordinate = 0;" in code
            and "const std::uint32_t host_nonfinite =" in code, "non-finite counter widths drift")
    require("std::uint32_t nesting_total" not in code and '\\"tie_nesting_violations\\":%u' not in code,
            "nesting counter width drift")
    require(module.EXPECTED_SLACK_DOMAIN == {"entries": 1048576,
                                              "logical_sha256": "d052e67892d0e39882db26798f881628480d83c0119ee3a1e2ba9b1cdcf03063"},
            "pinned slack domain identity drift")
    from research.g6.cuda_qualification import v14_batch_contract as contract
    require(module.SCHEMA_THROUGHPUT_MEASUREMENT == contract.SCHEMA_THROUGHPUT, "throughput measurement schema drift")
    for axis in (31, 111):
        for triple in ((0, 0, 0), (1, 2, 3), (axis - 1, axis - 1, axis - 1), (5, 0, axis - 1)):
            require(module.linear_index(*triple, axis) == contract.linear_index(*triple, axis)
                    and module.coordinate_at(module.linear_index(*triple, axis), axis) == triple, "linear order disagreement")
    for source in NEW_PYTHON:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        require(not any(isinstance(node, ast.Assert) for node in ast.walk(tree)), f"assert is not permitted: {source.name}")


def check_pins(module) -> None:
    observed = module.verify_pinned_inputs()
    require(observed == module.PINNED_INPUTS, "pinned inputs drifted")
    for rel in ("src/g5/domains.py", "src/g5/certify.py", module.CUDA_SOURCE_REL):
        require(observed[rel] == hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(), f"pin stale: {rel}")
    for other in (module.cuda_unbalanced.PINNED_INPUTS, module.cuda_slack.PINNED_INPUTS):
        for key, value in other.items():
            if key in module.PINNED_INPUTS:
                require(module.PINNED_INPUTS[key] == value, f"pin differs from a qualifier: {key}")
    tampered = dict(module.PINNED_INPUTS)
    tampered["src/g5/domains.py"] = "0" * 64
    rejects(module, module.verify_pinned_inputs, tampered, reason="drifted domain source")


def check_ledgers_and_coefficients(module):
    ledgers = module.load_ledgers()
    lambda_ref = module.lambda_ref_from(ledgers)
    require(lambda_ref > 0 and ledgers["2x"]["inputs"]["lambda_ref_binary64_hex"] == lambda_ref.hex(), "Lambda_ref binding drift")
    points = module.validation_points(ledgers)
    require([p["linear"] for p in points] == [module.linear_index(*t, module.SCALES[s]["axis_count"]) for s, t in EXPECTED_COORDINATES],
            "validation linear indices drift")
    for scale, index in (("2x", 70), ("2x", 0), ("2x", 110)):
        shared = module.cuda_unbalanced.load_ledgers()[module.cuda_unbalanced.V14_2X_LEDGER_REL]
        require(module.coefficients_at(ledgers[scale], index, index, index) == module.cuda_unbalanced.shared._coefficients_at(shared, index),
                "all-axis coefficients differ from the qualifier binding")
    mixed = module.coefficients_at(ledgers["2x"], 110, 0, 55)
    require(mixed.alpha == module.coefficients_at(ledgers["2x"], 110, 110, 110).alpha
            and mixed.sector_slack == module.coefficients_at(ledgers["2x"], 0, 0, 0).sector_slack
            and mixed.budget_slack == module.coefficients_at(ledgers["2x"], 55, 55, 55).budget_slack, "per-family row mapping drift")
    rejects(module, module.coefficients_at, ledgers["0.5x"], 31, 0, 0, reason="row outside axis")
    rejects(module, module.range_points, ledgers, "2x", 5, 5, reason="empty range")
    rejects(module, module.range_points, ledgers, "2x", 0, 4097, reason="range above the bound")
    rejects(module, module.range_points, ledgers, "0.5x", 29790, 29792, reason="range outside the grid")
    small = module.range_points(ledgers, "0.5x", 29789, 29791)
    require([p["coordinate"] for p in small] == [{"card": 30, "sector": 30, "budget": 29}, {"card": 30, "sector": 30, "budget": 30}],
            "range coordinates drift")
    return ledgers, lambda_ref, points


def check_domain_and_encoding(module, instance, ledgers, lambda_ref, points):
    from research.g6.gpu_qualification import energy_crosscheck as hip
    from src.g5.domains import BinaryDomain

    for index in (0, 1, 2, 1023, 0x80000, (1 << 20) - 1, 0x2468A):
        mask = module.canonical_index_to_mask(index)
        require(module.canonical_index_to_mask(mask) == index, "index/mask mapping is not an involution")
        require(BinaryDomain(20)[index] == hip.mask_to_x(mask), "BinaryDomain order drift")
    cache = module.build_slack_domain(instance)
    identity = module.domain_identity(cache)
    require(identity["slack"]["entries"] == 1048576 and identity["slack"]["logical_sha256"] == module.EXPECTED_SLACK_DOMAIN["logical_sha256"]
            and identity["unbalanced"]["count"] == 1 << 20, "domain identity drift")
    offsets = memoryview(cache.offset_bytes).cast("Q")
    for entry in range(0, 64):
        require(cache[entry] == (BinaryDomain(20)[entry], cache[entry][1]) and offsets[entry] == entry, "canonical cache order drift")
    payload = module.encode_inputs(instance, lambda_ref, points, cache, module.MODE_VALIDATE)
    words = struct.unpack(f"<{len(payload) // 8}Q", payload)
    require(words[:9] == (module.INPUT_MAGIC, 1, 20, 2, 11, 0, len(points), len(cache), module.float_bits(lambda_ref)), "input header drift")
    require(words[-len(cache):] == tuple(memoryview(cache.auxiliary_bytes).cast("I"))
            and words[-len(cache) - (1 << 20) - 1:-len(cache)] == tuple(offsets), "cache buffers not encoded verbatim")
    require(len(module.encode_inputs(instance, lambda_ref, points[:1], cache, module.MODE_THROUGHPUT)) == len(payload) - 7 * 8 * 7,
            "coefficient block size drift")
    rejects(module, module.encode_inputs, instance, lambda_ref, points, cache, 2, reason="unknown mode")
    # Output decoding: one synthetic coordinate record.
    n = len(cache)
    header = struct.pack("<7Q", module.OUTPUT_MAGIC, 1, 0, 1, 1 << 20, n, 1)
    record = struct.pack("<4Q", 1, 2, 3, 4)
    body = header + record + b"\x11" * (8 << 20) + b"\x22" * (8 * n) + b"\x02" * (1 << 20) + b"\x06" * n
    decoded = module.decode_output(body, 1, n, module.MODE_VALIDATE)
    entry = decoded["coordinates"][0]
    require(decoded["device_index"] == 1 and entry["unbalanced"]["h_min_bits"] == 1 and entry["slack"]["h_min_index"] == 4
            and entry["unbalanced"]["words"][5] == 0x1111111111111111 and entry["slack"]["flags"][7] == 6
            and len(entry["unbalanced"]["flags"]) == 1 << 20, "output decoding drift")
    rejects(module, module.decode_output, body[:-8], 1, n, module.MODE_VALIDATE, reason="truncated output")
    rejects(module, module.decode_output, body, 1, n, module.MODE_THROUGHPUT, reason="mode mismatch")
    require(module.decode_output(struct.pack("<7Q", module.OUTPUT_MAGIC, 1, 1, 3, 1 << 20, n, 0), 3, n, module.MODE_THROUGHPUT)["coordinates"] == [],
            "throughput output must carry no data")
    rejects(module, module.decode_output, struct.pack("<7Q", module.OUTPUT_MAGIC, 1, 1, 3, 1 << 20, n, 0) + b"\0" * 8, 3, n,
            module.MODE_THROUGHPUT, reason="throughput output carrying data")
    return cache


def check_reference_and_reduction(module, instance, points, cache, lambda_ref) -> None:
    from src.g4.classification import DecodedClassifier, OriginalObjectiveService
    from src.g4.energy import (prepare_coefficients, prepare_decoded_state, prepare_instance, prepare_slack_state,
                               slack_energy_prepared, tau, unbalanced_energy_prepared)
    from src.g5.certify import certify_prepared_domain
    from src.g5.domains import BinaryDomain, prepare_fixture_domains

    subset = [0, 1, 7, 0x0F0F0, 0xABCDE, (1 << 20) - 1]
    reference_u, reference_s = module.cpu_reference(instance, points[:2], cache, subset)
    prepared_instance = prepare_instance(instance)
    for k in range(2):
        values = prepare_coefficients(points[k]["coefficients"])
        for d in subset:
            decoded = prepare_decoded_state(prepared_instance, BinaryDomain(20)[d])
            require(reference_u[k][d] == module.float_bits(unbalanced_energy_prepared(decoded, values)), "unbalanced reference drift")
            _, y = cache[d]
            require(reference_s[k][d] == module.float_bits(slack_energy_prepared(prepare_slack_state(decoded, y), values)), "slack reference drift")
    # canonical_reduction versus certify_prepared_domain on a bounded prepared fixture domain.
    raw_decoded = tuple(BinaryDomain(20)[d] for d in range(0, 4096, 16))
    raw_slack = tuple((BinaryDomain(20)[d], cache[d][1]) for d in range(0, 4096, 16))
    domains = prepare_fixture_domains(instance, raw_decoded, raw_slack)
    classifier = DecodedClassifier(OriginalObjectiveService(lambda x: 0.0, lambda_ref), lambda x: True)
    for k in range(2):
        values = prepare_coefficients(points[k]["coefficients"])
        for encoding, domain, function, decode in (("unbalanced", domains.unbalanced, unbalanced_energy_prepared, lambda s: s),
                                                   ("slack", domains.slack, slack_energy_prepared, lambda s: s[0])):
            words = [module.float_bits(function(state, values)) for state in domain]
            h_min_bits, h_index, flags = module.canonical_reduction(words, lambda_ref)
            for c_h in module.CH_VALUES:
                h_min, tied, _decoded, _label = certify_prepared_domain(domain, lambda state, v=values: function(state, v),
                                                                        lambda_ref, 0.0, decode, classifier, float(c_h))
                require(module.float_bits(h_min) == h_min_bits and words[h_index] == h_min_bits, f"{encoding} minimum drift")
                k_bit = 1 << module.CH_VALUES.index(c_h)
                require([domain.raw_state(i) for i in range(len(words)) if flags[i] & k_bit] == tied,
                        f"{encoding} c_H={c_h} tie set differs from certify_prepared_domain")
            for i, word in enumerate(words):
                y = module.bits_float(word)
                for k_bit, c_h in enumerate(module.CH_VALUES):
                    expected = abs(y - module.bits_float(h_min_bits)) <= tau(y, module.bits_float(h_min_bits), lambda_ref, float(c_h))
                    require(bool(flags[i] & (1 << k_bit)) == expected, "tie flags differ from energy.tau")
    # First-seen minimum with duplicates and signed zeros; nonfinite refused.
    duplicate = [module.float_bits(v) for v in (3.0, -1.0, 2.0, -1.0, -1.0)]
    h_min_bits, h_index, _ = module.canonical_reduction(duplicate, 1.0)
    require(h_index == 1 and h_min_bits == module.float_bits(-1.0), "first-seen minimum drift")
    h_min_bits, h_index, _ = module.canonical_reduction([module.float_bits(0.0), module.float_bits(-0.0)], 1.0)
    require(h_index == 0 and h_min_bits == module.float_bits(0.0), "signed-zero minimum must keep the first-seen +0.0")
    rejects(module, module.canonical_reduction, [module.float_bits(float("inf"))], 1.0, reason="nonfinite energy")
    require(module.compare_words({0: 1, 2: 5}, [1, 9, 6]) == 1, "word comparator drift")
    require(module.compare_reduction({"h_min_bits": 1, "h_min_index": 2, "flags": b"\x07\x06"}, (1, 3, b"\x07\x07"))
            == {"h_min_bits_mismatch": 0, "h_min_index_mismatch": 1, "tie_flag_mismatches": 1}, "reduction comparator drift")


def synthetic_qualifier_record(module, encoding: str, driver: int = 13000) -> dict:
    qualifier = module.cuda_unbalanced if encoding == "unbalanced" else module.cuda_slack
    report = {"architecture": "sm_75", "backend": "cuda-runtime", "compute_capability": "7.5", "cuda_driver_version": driver,
              "cuda_runtime_version": 12080, "device_count": 1, "device_index": 0, "device_name": "Tesla T4",
              "device_uuid_hex": "0123456789abcdef0123456789abcdef", "device_vs_host_cxx_mismatches": 0,
              "evaluations": 6840 if encoding == "unbalanced" else 1172, "multiprocessor_count": 40, "nvcc_version": "12.8.93",
              "pci_bus_id": 0, "pci_device_id": 4, "pci_domain_id": 0, "point_count": 4,
              "probe": "unbalanced_energy_transcript_crosscheck_cuda" if encoding == "unbalanced" else qualifier.PROBE,
              "scientific_outputs": "intentionally absent", "state_count": 1710 if encoding == "unbalanced" else 293,
              "total_global_memory_bytes": 15828320256}
    nvcc_info = {"path": "/usr/local/cuda/bin/nvcc", "release": "12.8", "build": "12.8.93", "stdout": ""}
    command = module.cuda_unbalanced.compile_command(nvcc_info["path"], Path("x.cu"), Path("x"))
    ids = ["d011_primary_ell_30", "v14_2x_row_70_embedded_primary", "v14_2x_row_0_lower_endpoint", "v14_2x_row_110_upper_endpoint"]
    if encoding == "unbalanced":
        identity = qualifier.qualification_identity(report, nvcc_info, command, qualifier.PINNED_INPUTS, "b" * 64, ids, 6840)
    else:
        identity = qualifier.qualification_identity(report, nvcc_info, command, qualifier.PINNED_INPUTS, "c" * 64, "b" * 64, ids, 1172)
    return {"schema": qualifier.SCHEMA_RUN, "mode": "run", "track": "cuda-t4", "verdict": "pass",
            "gpu_vs_python": {"mismatches": 0, "evaluations": report["evaluations"]},
            "host_cxx_vs_python": {"mismatches": 0, "evaluations": report["evaluations"]},
            "qualification_identity": identity, "qualification_identity_sha256": qualifier.identity_sha256(identity),
            "device": module.cuda_unbalanced.device_fingerprint(report), "scientific_outputs": "intentionally absent"}


def engine_report(module, cache, coordinate_count: int, mode: str) -> dict:
    per = module.DECODED_COUNT + len(cache)
    return {"architecture": "sm_75", "backend": "cuda-runtime", "compute_capability": "7.5", "coordinate_count": coordinate_count,
            "cuda_driver_version": 13000, "cuda_runtime_version": 12080, "decoded_state_count": module.DECODED_COUNT,
            "device_count": 1, "device_index": 0, "device_name": "Tesla T4", "device_uuid_hex": "0123456789abcdef0123456789abcdef",
            "device_vs_host_cxx_mismatches": 0, "elapsed_ns_coordinates": 123456789, "elapsed_ns_prepare": 1000,
            "evaluations": coordinate_count * per, "host_reference_evaluated": mode == "validate", "mode": mode,
            "multiprocessor_count": 40, "nonfinite_energies": 0, "nvcc_version": "12.8.93", "pci_bus_id": 0, "pci_device_id": 4,
            "pci_domain_id": 0, "point_count": coordinate_count, "probe": module.PROBE, "scientific_outputs": "intentionally absent",
            "slack_state_count": len(cache), "state_count": per, "tie_nesting_violations": 0, "total_global_memory_bytes": 15828320256}


def check_records_reports_identity(module, cache) -> tuple:
    unbalanced = synthetic_qualifier_record(module, "unbalanced")
    slack = synthetic_qualifier_record(module, "slack")
    prerequisites = module.validate_prerequisite_records(unbalanced, slack)
    require(prerequisites["platform"]["nvcc_build"] == "12.8.93" and prerequisites["unbalanced_identity_sha256"] != prerequisites["slack_identity_sha256"],
            "prerequisite summary drift")
    rejects(module, module.validate_prerequisite_records, {**unbalanced, "verdict": "fail"}, slack, reason="failed unbalanced record")
    rejects(module, module.validate_prerequisite_records, unbalanced, {**slack, "gpu_vs_python": {"mismatches": 1, "evaluations": 1172}},
            reason="slack record with a mismatch")
    rejects(module, module.validate_prerequisite_records, unbalanced, synthetic_qualifier_record(module, "slack", driver=13001),
            reason="records from different drivers")
    rejects(module, module.validate_prerequisite_records, unbalanced, unbalanced, reason="unbalanced record supplied as slack")
    rejects(module, module.validate_prerequisite_records, slack, unbalanced, reason="records swapped")
    tampered = copy.deepcopy(unbalanced)
    tampered["qualification_identity"]["cuda_driver_version"] = 1
    rejects(module, module.validate_prerequisite_records, tampered, slack, reason="tampered identity")
    tampered = copy.deepcopy(unbalanced)
    tampered["qualification_identity"]["pinned_inputs"]["src/g4/energy.py"] = "1" * 64
    tampered["qualification_identity_sha256"] = module.cuda_unbalanced.identity_sha256(tampered["qualification_identity"])
    rejects(module, module.validate_prerequisite_records, tampered, slack, reason="record against a different evaluator")
    tampered = copy.deepcopy(unbalanced)
    tampered["qualification_identity"]["gpu_name"] = "AMD Radeon RX 9070"
    tampered["qualification_identity_sha256"] = module.cuda_unbalanced.identity_sha256(tampered["qualification_identity"])
    rejects(module, module.validate_prerequisite_records, tampered, slack, reason="ROCm identity")

    good = engine_report(module, cache, 8, "validate")
    require(module.validate_device_report(good, 8, len(cache), module.MODE_VALIDATE) is good, "canonical engine report rejected")
    require(module.validate_device_report(engine_report(module, cache, 3, "throughput"), 3, len(cache), module.MODE_THROUGHPUT), "throughput report rejected")
    for label, report, mode in (("probe", {**good, "probe": "slack_energy_transcript_crosscheck_cuda"}, module.MODE_VALIDATE),
                                ("mode", good, module.MODE_THROUGHPUT), ("nonfinite", {**good, "nonfinite_energies": 1}, module.MODE_VALIDATE),
                                ("nesting", {**good, "tie_nesting_violations": 2}, module.MODE_VALIDATE),
                                ("nonfinite_2^32", {**good, "nonfinite_energies": 1 << 32}, module.MODE_VALIDATE),
                                ("nonfinite_max", {**good, "nonfinite_energies": 4096 * (1 << 21)}, module.MODE_VALIDATE),
                                ("nonfinite_float", {**good, "nonfinite_energies": 0.0}, module.MODE_VALIDATE),
                                ("nonfinite_bool", {**good, "nonfinite_energies": False}, module.MODE_VALIDATE),
                                ("nesting_2^32", {**good, "tie_nesting_violations": 1 << 32}, module.MODE_VALIDATE),
                                ("nesting_2^33", {**good, "tie_nesting_violations": 1 << 33}, module.MODE_VALIDATE),
                                ("nesting_float", {**good, "tie_nesting_violations": 0.0}, module.MODE_VALIDATE),
                                ("nesting_bool", {**good, "tie_nesting_violations": False}, module.MODE_VALIDATE),
                                ("host_flag", {**good, "host_reference_evaluated": False}, module.MODE_VALIDATE),
                                ("slack_count", {**good, "slack_state_count": len(cache) - 8}, module.MODE_VALIDATE),
                                ("a100", {**good, "device_name": "NVIDIA A100-SXM4-40GB", "compute_capability": "8.0", "architecture": "sm_80"}, module.MODE_VALIDATE),
                                ("hip", {**good, "backend": "hip-runtime"}, module.MODE_VALIDATE),
                                ("stub", {**good, "device_name": "Tesla T4 host-emulation-stub"}, module.MODE_VALIDATE),
                                ("elapsed", {**good, "elapsed_ns_coordinates": -1}, module.MODE_VALIDATE)):
        try:
            module.validate_device_report(report, 8, len(cache), mode)
        except module.EngineError:
            continue
        raise FixtureError(f"device validation accepted: {label}")
    nvcc_info = {"path": "/usr/local/cuda/bin/nvcc", "release": "12.8", "build": "12.8.93", "stdout": ""}
    command = module.cuda_unbalanced.compile_command(nvcc_info["path"], Path("e.cu"), Path("e"))
    identity = module.engine_identity(good, nvcc_info, command, module.PINNED_INPUTS, module.domain_identity(cache), prerequisites)
    again = module.engine_identity(good, nvcc_info, command, module.PINNED_INPUTS, module.domain_identity(cache), prerequisites)
    require(identity == again, "engine identity not deterministic")
    require(identity["prerequisites"] == {"unbalanced_identity_sha256": prerequisites["unbalanced_identity_sha256"],
                                          "slack_identity_sha256": prerequisites["slack_identity_sha256"]}
            and identity["domain"]["slack"]["logical_sha256"] == module.EXPECTED_SLACK_DOMAIN["logical_sha256"]
            and identity["engine_source_sha256"] == module.PINNED_INPUTS[module.CUDA_SOURCE_REL]
            and identity["cuda_source_sha256"] == identity["engine_source_sha256"]
            and identity["validation_coordinates_sha256"] == module.validation_coordinates_sha256()
            and identity["compile_flags"] == list(module.COMPILE_FLAGS) and identity["pinned_inputs"] == module.PINNED_INPUTS
            and "device_uuid_hex" not in identity and "evaluations" not in identity, "engine identity binding drift")
    changed = module.engine_identity({**good, "cuda_runtime_version": 12090}, nvcc_info, command, module.PINNED_INPUTS,
                                     module.domain_identity(cache), prerequisites)
    require(module.identity_sha256(changed) != module.identity_sha256(identity), "runtime change not reflected")
    return unbalanced, slack


def check_timing(module) -> None:
    from decimal import Decimal

    timing = module.throughput_timing(1_234_567_890_123, 34_567_890_123)
    require(timing == {"wall_seconds": "1234.567890123", "setup_seconds": "1200.000000000",
                       "coordinate_seconds": "34.567890123"}, "timing fields drift")
    require(Decimal(timing["wall_seconds"]) == Decimal(timing["setup_seconds"]) + Decimal(timing["coordinate_seconds"]),
            "timing fields do not reconcile")
    require(module.throughput_timing(5, 5) == {"wall_seconds": "0.000000005", "setup_seconds": "0.000000000",
                                               "coordinate_seconds": "0.000000005"}, "nanosecond rendering drift")
    rejects(module, module.throughput_timing, 10, 11, reason="coordinate time above wall time")
    rejects(module, module.throughput_timing, -1, 0, reason="negative wall time")
    rejects(module, module.throughput_timing, 1.5, 0, reason="non-integer nanoseconds")
    require(module._seconds_text(0) == "0.000000000" and module._seconds_text(10**9) == "1.000000000", "seconds text drift")


def check_run_refusals(module, records) -> None:
    def must_not_be_called():
        raise FixtureError("nvcc locator consulted before the environment guard")

    calls = []

    def never_located():
        calls.append(1)
        return None

    previous = os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
    try:
        rejects(module, module.run_validate, records, must_not_be_called, reason="validate without the environment guard")
        rejects(module, module.run_throughput, records, "2x", 0, 4, must_not_be_called, reason="throughput without the environment guard")
    finally:
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1" if previous is None else previous
    try:
        module.run_validate(records, locate=never_located)
    except module.EngineError as exc:
        require("nvcc is unavailable" in str(exc) and calls == [1], "validate no-nvcc refusal drift")
    else:
        raise FixtureError("run_validate proceeded without nvcc")
    calls.clear()
    try:
        module.run_throughput(records, "0.5x", 0, 3, locate=never_located)
    except module.EngineError as exc:
        require("nvcc is unavailable" in str(exc) and calls == [1], "throughput no-nvcc refusal drift")
    else:
        raise FixtureError("run_throughput proceeded without nvcc")
    rejects(module, module.run_throughput, records, "0.5x", 3, 3, never_located, reason="empty throughput range")
    require(not list(Path(tempfile.gettempdir()).glob("g6-cuda-t4-v14-engine-*")), "refused runs left temporary directories")


def check_cli(module, records) -> None:
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    before = tree_digest(ROOT / "research/g6")
    with tempfile.TemporaryDirectory(prefix="g6-cuda-t4-v14-engine-fixture-") as temporary:
        directory = Path(temporary)
        (directory / "u.json").write_bytes(module.canonical_bytes(records[0]))
        (directory / "s.json").write_bytes(module.canonical_bytes(records[1]))
        base = [str(RUNNER), "--plan", "--unbalanced-record", str(directory / "u.json"), "--slack-record", str(directory / "s.json")]
        plan = subprocess.run([sys.executable, *base], cwd=ROOT, text=True, capture_output=True, check=False, env=environment)
        require(plan.returncode == 0, "CLI plan failed: " + plan.stderr[-400:])
        payload = json.loads(plan.stdout)
        require(payload["mode"] == "plan" and payload["writes"] == "none" and payload["nvcc_located"] is False
                and payload["domain"]["slack"]["entries"] == 1048576 and payload["planned_validation_evaluations"] == 8 * (2 * (1 << 20))
                and payload["prerequisites"]["slack_identity_sha256"] == records[1]["qualification_identity_sha256"]
                and payload["scientific_outputs"] == "intentionally absent"
                and [tuple(c["coordinate"].values()) for c in payload["validation_coordinates"]][0] == (0, 0, 0), "plan payload drift")
        require("verdict" not in payload and "validation" not in payload, "plan must not carry run fields")
        optimized = subprocess.run([sys.executable, "-O", *base], cwd=ROOT, text=True, capture_output=True, check=False, env=environment)
        require(optimized.returncode == 0 and optimized.stdout == plan.stdout, "--plan differs under python -O")
        both = subprocess.run([sys.executable, str(RUNNER), "--plan", "--validate"], cwd=ROOT, text=True, capture_output=True,
                              check=False, env=environment)
        require(both.returncode == 2, "modes must be mutually exclusive")
        # --validate/--throughput are exercised only where they refuse before any nvcc lookup.
        missing = subprocess.run([sys.executable, str(RUNNER), "--validate"], cwd=ROOT, text=True, capture_output=True,
                                 check=False, env=environment)
        require(missing.returncode == 1 and missing.stdout == "" and "require --unbalanced-record" in missing.stderr,
                "--validate without records must fail closed")
        half = subprocess.run([sys.executable, str(RUNNER), "--throughput", "--unbalanced-record", str(directory / "u.json")],
                              cwd=ROOT, text=True, capture_output=True, check=False, env=environment)
        require(half.returncode == 1 and "required together" in half.stderr, "one record must fail closed")
        no_env = {key: value for key, value in os.environ.items() if key != "PYTHONDONTWRITEBYTECODE"}
        guarded = subprocess.run([sys.executable, "-B", str(RUNNER), "--validate", "--unbalanced-record", str(directory / "u.json"),
                                  "--slack-record", str(directory / "s.json")], cwd=ROOT, text=True, capture_output=True,
                                 check=False, env=no_env)
        require(guarded.returncode == 1 and guarded.stdout == "" and "PYTHONDONTWRITEBYTECODE=1 is required" in guarded.stderr,
                "--validate without PYTHONDONTWRITEBYTECODE must fail closed")
    require(tree_digest(ROOT / "research/g6") == before, "CLI invocations changed the research/g6 tree")
    require(not list(Path(tempfile.gettempdir()).glob("g6-cuda-t4-v14-engine-*")), "temporary leftovers")


def main() -> int:
    pyc_before = pyc_snapshot()
    try:
        require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "run with PYTHONDONTWRITEBYTECODE=1")
        module = load_module()
        check_static(module)
        check_pins(module)
        from src.g4.instance import load_instance

        instance = load_instance(ROOT / module.INSTANCE_REL)
        ledgers, lambda_ref, points = check_ledgers_and_coefficients(module)
        cache = check_domain_and_encoding(module, instance, ledgers, lambda_ref, points)
        check_reference_and_reduction(module, instance, points, cache, lambda_ref)
        records = check_records_reports_identity(module, cache)
        check_timing(module)
        check_run_refusals(module, records)
        check_cli(module, records)
        forbidden = [name for name in sys.modules if name in {"src.g5.runner", "src.g5.core_pass", "src.g5.make_self_test",
                     "src.g6.g5_input", "src.g6.ratified_g5_input", "src.g6.g5_digest_registry", "src.g6.trial_runner", "src.g6.d011_runner"}]
        require(not forbidden, "fixtures loaded a Gate-5 corpus/runner module: " + ", ".join(forbidden))
        require(pyc_snapshot() == pyc_before, "verification wrote bytecode")
        print("PASS CUDA T4 V-14 engine fixtures; "
              f"validation_coordinates={len(points)} decoded_states={module.DECODED_COUNT} slack_entries={len(cache)} "
              f"evaluations_per_coordinate={module.DECODED_COUNT + len(cache)}; no nvcc, GPU, Gate-5 corpus read, bytecode, or repository write")
        return 0
    except FixtureError as exc:
        print(f"FAIL CUDA T4 V-14 engine fixtures: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
