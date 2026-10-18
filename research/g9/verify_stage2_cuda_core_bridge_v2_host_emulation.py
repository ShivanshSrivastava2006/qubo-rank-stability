#!/usr/bin/env python3
"""Host-stub v2 single-call ABI fixtures; no nvcc, device, Kaggle, or real instance.

OFFLINE / SYNTHETIC-ONLY. Builds the v2 sidecar with g++ against the host
emulation stub (warning-free, -ffp-contract=off -fno-fast-math), compares two
distinct synthetic frames word-exactly with the Python reference, and checks
failure scrubbing, result/offset swaps, single-word mutations, capacity and
malformed-frame refusal, the atomic C re-entry guard (deterministic probe and
real threads), and the exported symbol surface. Passing is synthetic evidence
only: it does not qualify a CUDA build, a GPU, an image, or Gate-9 §B.
"""

from __future__ import annotations

import ctypes as C
import copy
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading

if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
    raise SystemExit("PYTHONDONTWRITEBYTECODE=1 is required")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9.cuda_qualification import stage2_cuda_core_bridge_v2 as bridge
from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as core
from research.g9.cuda_qualification import stage2_cuda_input_frame as frame_api


QUALIFICATION_DIR = ROOT / "research/g9/cuda_qualification"
WRAPPER = QUALIFICATION_DIR / "stage2_cuda_core_bridge_v2.cu"
STUB = ROOT / "research/g6/cuda_qualification/host_emulation_stub"
BUILD_FLAGS = ["-x", "c++", "-std=c++17", "-O0", "-shared", "-fPIC", "-Wall", "-Wextra",
               "-Wno-unknown-pragmas", "-ffp-contract=off", "-fno-fast-math"]
# Test-only translation unit: the unchanged v2 sidecar plus two probes that
# hold/release its guard, so an in-flight call can be simulated
# deterministically. The release-shape library never contains these probes.
PROBE_SOURCE = '''#include "stage2_cuda_core_bridge_v2.cu"
extern "C" std::uint32_t g9_core_v2_probe_hold() {
  return g9_core_v2_busy.test_and_set(std::memory_order_acquire) ? 0u : 1u;
}
extern "C" void g9_core_v2_probe_release() {
  g9_core_v2_busy.clear(std::memory_order_release);
}
'''
EXPECTED_C_EXPORTS = {"g9_core_backend_v2", "g9_core_abi_layout_v2", "g9_core_run_v2"}
SENTINEL = 0xA5


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def refused(call, message: str) -> str:
    try:
        call()
    except bridge.CoreBridgeV2Error as exc:
        return str(exc)
    raise RuntimeError(message)


def compare_core(actual: dict[str, object], expected: dict[str, object]) -> None:
    require(actual.keys() == expected.keys() and
            actual["lift_total"] == expected["lift_total"] and
            actual["record_count"] == expected["record_count"] and
            actual["summaries"].keys() == expected["summaries"].keys(),
            "core result outer shape differs")
    for key, observed in actual["summaries"].items():
        wanted = expected["summaries"][key]
        require(observed.keys() == wanted.keys(), f"summary keys differ at {key}")
        for field in observed:
            if field == "minimum":
                require(struct.pack("<d", observed[field]) == struct.pack("<d", wanted[field]),
                        f"minimum word differs at {key}")
            else:
                require(observed[field] == wanted[field], f"{field} differs at {key}")


def flip_low_bit(value: float) -> float:
    """The adjacent binary64 word: one mutated input word, not a new value choice."""
    return struct.unpack("<d", struct.pack("<Q", struct.unpack("<Q", struct.pack("<d", value))[0] ^ 1))[0]


def matches_reference(actual: dict[str, object], expected: dict[str, object]) -> bool:
    try:
        compare_core(actual, expected)
    except RuntimeError:
        return False
    return True


def build(command_tail: list[str], library: Path, *, source: str | None = None) -> None:
    command = ["g++", *BUILD_FLAGS, "-I", str(STUB), "-I", str(QUALIFICATION_DIR),
               *command_tail, "-o", str(library)]
    built = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, input=source,
                           check=False, timeout=300)
    require(built.returncode == 0 and not built.stderr,
            "host-stub v2 build failed or warned: " + built.stderr)


def exported_c_symbols(library: Path) -> tuple[set[str], str]:
    listed = subprocess.run(["nm", "-D", "--defined-only", str(library)], text=True,
                            capture_output=True, check=True, timeout=60).stdout
    names = [line.split()[-1] for line in listed.splitlines() if line.strip()]
    demangled = subprocess.run(["c++filt"], input="\n".join(names), text=True,
                               capture_output=True, check=True, timeout=60).stdout
    return {name for name in names if not name.startswith("_Z")}, demangled


def load_run(library: Path):
    loaded = C.CDLL(str(library))
    run = loaded.g9_core_run_v2
    run.argtypes = [C.POINTER(bridge.PayloadData), C.POINTER(bridge.CoefficientData), C.c_uint32,
                    C.POINTER(bridge.CoreOutput), C.POINTER(C.c_uint64), C.c_uint64]
    run.restype = C.c_uint32
    return loaded, run


def sentinel_buffers() -> tuple[bridge.CoreOutput, bridge.OffsetTable]:
    output, offsets = bridge.CoreOutput(), bridge.OffsetTable()
    C.memset(C.addressof(output), SENTINEL, C.sizeof(output))
    C.memset(C.addressof(offsets), SENTINEL, C.sizeof(offsets))
    return output, offsets


def raw_bytes(buffer) -> bytes:
    return C.string_at(C.addressof(buffer), C.sizeof(buffer))


def untouched(*buffers) -> bool:
    return all(raw_bytes(buffer) == bytes([SENTINEL]) * C.sizeof(buffer) for buffer in buffers)


def scrubbed(*buffers) -> bool:
    return all(raw_bytes(buffer) == bytes(C.sizeof(buffer)) for buffer in buffers)


def direct_call(run, frame: dict[str, object]):
    validated = frame_api.validate_input_frame(frame)
    payload, rows = bridge.decode_frame(validated)
    output, offsets = sentinel_buffers()
    status = run(C.byref(payload), rows, len(rows), C.byref(output), offsets, bridge.OFFSET_WORDS)
    return status, validated, output, offsets


def offsets_sha(payload: dict[str, object]) -> tuple[str, int]:
    domain = core.build_domain(payload)
    return hashlib.sha256(domain["offsets"].tobytes()).hexdigest(), domain["lift_total"]


def main() -> None:
    require(sys.byteorder == "little", "fixtures require a little-endian host")
    # --- synthetic frames --------------------------------------------------
    payload_a = core.synthetic_payload()
    rows_a = [core.coefficient_row("row0")]
    sha_a, lift_a = offsets_sha(payload_a)
    frame_a = frame_api.build_input_frame(payload_a, rows_a, sha_a)

    payload_b = core.synthetic_payload()
    payload_b["sectors"] = core.ALTERNATE_MEMBERSHIP
    payload_b["lambda_ref"] = core.ALTERNATE_LAMBDA_REF
    payload_b["b"] = 45.0
    rows_b = [core.coefficient_row("row1"), core.coefficient_row("row0")]
    sha_b, lift_b = offsets_sha(payload_b)
    require(sha_b != sha_a and lift_b != lift_a, "frame B did not change the offset table")
    frame_b = frame_api.build_input_frame(payload_b, rows_b, sha_b)

    # Same payload (so the same offsets and lift total) but a different row.
    rows_a1 = [core.coefficient_row("row1")]
    frame_a1 = frame_api.build_input_frame(payload_a, rows_a1, sha_a)

    # Valid inputs whose every energy is +0.0: every state ties, so run_core
    # fails at the compaction cap AFTER the offsets and energies were built.
    payload_d = core.synthetic_payload()
    payload_d["mu"] = [0.0] * core.ASSET_COUNT
    payload_d["sigma"] = [[0.0] * core.ASSET_COUNT for _ in range(core.ASSET_COUNT)]
    row_d = dict(core.coefficient_row("row0"))
    for name in ("alpha", "sector_linear", "sector_quadratic", "budget_linear", "budget_quadratic"):
        row_d[name] = 0.0
    frame_d = frame_api.build_input_frame(payload_d, [row_d], sha_a)

    # Bit-distinct but numerically equal word: mu[9] is +0.0 in frame A.
    require(struct.pack("<d", payload_a["mu"][9]) == struct.pack("<d", 0.0),
            "synthetic mu[9] is no longer +0.0")
    payload_negzero = copy.deepcopy(payload_a)
    payload_negzero["mu"][9] = -0.0
    frame_negzero = frame_api.build_input_frame(payload_negzero, rows_a, sha_a)
    require(frame_negzero["payload"]["mu"][9] == "-0x0.0p+0" and
            frame_a["payload"]["mu"][9] == "0x0.0p+0" and
            frame_negzero["content_sha256"] != frame_a["content_sha256"],
            "+0.0 and -0.0 did not produce bit-distinct frames")

    reference_a = core.run_core(*frame_api.decoded_inputs(frame_a))
    reference_b = core.run_core(*frame_api.decoded_inputs(frame_b))

    with tempfile.TemporaryDirectory(prefix="g9-core-v2-host-") as temporary:
        library = Path(temporary) / "libg9_core_v2_host_stub.so"
        probe_library = Path(temporary) / "libg9_core_v2_probe_host_stub.so"
        build([str(WRAPPER)], library)
        build(["-"], probe_library, source=PROBE_SOURCE)

        # --- exported surface ----------------------------------------------
        c_exports, demangled = exported_c_symbols(library)
        require({name for name in c_exports if name.startswith("g9_")} == EXPECTED_C_EXPORTS,
                f"unexpected C exports: {sorted(c_exports)}")
        require("self_test" not in demangled and "run_core" not in demangled and
                "_v1" not in demangled, "a guard-bypassing entry point is exported")

        message = refused(lambda: bridge._run_compiled_frame_v2(frame_a, library, require_backend=1),
                          "offline v2 bridge accepted a CUDA backend request")
        require(message.startswith("no CUDA v2 library"), "CUDA request refused for another reason")

        # --- two distinct frames, word-exact vs the Python reference --------
        envelope_a = bridge.run_host_emulated_frame_v2(frame_a, library)
        require(envelope_a["schema"] == bridge.SCHEMA and envelope_a["abi"] == "g9_core_run_v2" and
                envelope_a["backend"] == 0 and
                envelope_a["input_frame_sha256"] == frame_a["content_sha256"] and
                envelope_a["input_frame_sha256_role"] == "host_bookkeeping_not_device_attestation" and
                envelope_a["offsets_sha256"] == sha_a, "frame A envelope binding drift")
        compare_core(envelope_a["core_result"], reference_a)
        bridge.require_consumer_envelope(envelope_a, payload_a, rows_a, sha_a)

        envelope_b = bridge.run_host_emulated_frame_v2(frame_b, library)
        require(envelope_b["input_frame_sha256"] == frame_b["content_sha256"] and
                envelope_b["offsets_sha256"] == sha_b and
                envelope_b["core_result"]["record_count"] == 2 and
                envelope_b["result_sha256"] != envelope_a["result_sha256"],
                "frame B was not bound independently")
        compare_core(envelope_b["core_result"], reference_b)
        bridge.require_consumer_envelope(envelope_b, payload_b, rows_b, sha_b)

        # --- consumer-side swaps and hash-consistent single-word edits -------
        refused(lambda: bridge.require_consumer_envelope(envelope_b, payload_a, rows_a, sha_a),
                "frame B envelope accepted against frame A inputs")
        swapped_result = dict(envelope_a, core_result=envelope_b["core_result"])
        refused(lambda: bridge.require_consumer_envelope(swapped_result, payload_a, rows_a, sha_a),
                "envelope with a swapped bounded result accepted")
        swapped_offsets = dict(envelope_a, offsets_sha256=sha_b)
        refused(lambda: bridge.require_consumer_envelope(swapped_offsets, payload_a, rows_a, sha_a),
                "envelope with a swapped offset identity accepted")
        mutated_rows = [dict(rows_a[0])]
        mutated_rows[0]["alpha"] = flip_low_bit(mutated_rows[0]["alpha"])
        refused(lambda: bridge.require_consumer_envelope(envelope_a, payload_a, mutated_rows, sha_a),
                "one-ulp coefficient edit accepted by the consumer")
        refused(lambda: bridge.require_consumer_envelope(envelope_b, payload_b, rows_b[::-1], sha_b),
                "reordered coefficient rows accepted by the consumer")
        refused(lambda: bridge.require_consumer_envelope(envelope_a, payload_negzero, rows_a, sha_a),
                "-0.0 payload word accepted against a +0.0 envelope")
        entry_edit = copy.deepcopy(envelope_a)
        stream = entry_edit["core_result"]["summaries"][(0, "slack")]
        stream["compacted_entries"] = (stream["compacted_entries"][0] ^ 1,
                                       *stream["compacted_entries"][1:])
        refused(lambda: bridge.require_consumer_envelope(entry_edit, payload_a, rows_a, sha_a),
                "one compacted entry edit accepted by the consumer")
        for field, value in (("schema", "decisions_os/g9_cuda_bound_core_result/v1"),
                             ("backend", 1), ("result_sha256", "0" * 64)):
            refused(lambda: bridge.require_consumer_envelope(dict(envelope_a, **{field: value}),
                                                             payload_a, rows_a, sha_a),
                    f"envelope with a wrong {field} accepted")

        # Equality alone is not a schema check: bool == 1 and 256.0 == 256.
        # The consumer must refuse int-like values of the wrong exact type.
        for label in ("record_count", "word_count", "illegal", "per_ch",
                      "compaction_chunks", "backend"):
            malformed = copy.deepcopy(envelope_a)
            if label == "record_count":
                malformed["core_result"]["record_count"] = True
            elif label == "backend":
                malformed["backend"] = False
            else:
                item = malformed["core_result"]["summaries"][(0, "unbalanced")]
                if label == "word_count":
                    item["word_count"] = float(item["word_count"])
                elif label == "illegal":
                    item["illegal"] = False
                elif label == "per_ch":
                    item["per_ch"] = (True, *item["per_ch"][1:])
                else:
                    item["compaction_chunks"] = float(item["compaction_chunks"])
            refused(lambda malformed=malformed: bridge.require_consumer_envelope(
                malformed, payload_a, rows_a, sha_a),
                f"wrongly typed {label} accepted by the consumer")

        # The -0.0 frame is a distinct identity even though its bounded
        # result equals frame A's word for word.
        envelope_negzero = bridge.run_host_emulated_frame_v2(frame_negzero, library)
        bridge.require_consumer_envelope(envelope_negzero, payload_negzero, rows_a, sha_a)
        require(envelope_negzero["input_frame_sha256"] != envelope_a["input_frame_sha256"] and
                envelope_negzero["result_sha256"] != envelope_a["result_sha256"],
                "-0.0 frame was not bound as a distinct identity")
        compare_core(envelope_negzero["core_result"], reference_a)

        # --- malformed frames never reach the ABI ----------------------------
        bad_hash = dict(frame_a, content_sha256="0" * 64)
        bad_schema = dict(frame_a, schema="decisions_os/g9_cuda_core_input_frame/v0")
        unhashed_word = copy.deepcopy(frame_a)
        unhashed_word["payload"]["mu"][0] = flip_low_bit(
            float.fromhex(frame_a["payload"]["mu"][0])).hex()
        three_rows = copy.deepcopy(frame_a)
        three_rows["coefficients"] = [frame_a["coefficients"][0]] * 3
        three_rows["content_sha256"] = frame_api.content_sha256(three_rows)
        zero_rows = dict(frame_a, coefficients=[])
        zero_rows["content_sha256"] = frame_api.content_sha256(zero_rows)
        for label, frame in (("content hash", bad_hash), ("schema", bad_schema),
                             ("unhashed payload word", unhashed_word),
                             ("three-row", three_rows), ("zero-row", zero_rows)):
            message = refused(lambda: bridge.run_host_emulated_frame_v2(frame, library),
                              f"malformed {label} frame accepted")
            require(message == "input frame is invalid", f"{label} frame reached the ABI")
        wrong_offsets = frame_api.build_input_frame(payload_a, rows_a,
                                                     hashlib.sha256(b"wrong offsets").hexdigest())
        message = refused(lambda: bridge.run_host_emulated_frame_v2(wrong_offsets, library),
                          "different valid offset identity accepted")
        require("offset table differs" in message, "wrong offset identity refused for another reason")

        # --- failure after intermediate arrays: status, scrub, never accepted
        message = refused(lambda: bridge.run_host_emulated_frame_v2(frame_d, library),
                          "compaction-overflow frame accepted")
        require(message == "compiled v2 core refused or failed the validated input",
                "overflow frame refused for an unexpected reason")
        _, run = load_run(library)
        status, validated_a, output_a, offsets_a = direct_call(run, frame_a)
        require(status == bridge.STATUS_OK, "direct v2 call for frame A failed")
        status, _, output_d, offsets_d = direct_call(run, frame_d)
        require(status == bridge.STATUS_REFUSED and scrubbed(output_d, offsets_d),
                "failed call did not scrub both caller buffers")
        refused(lambda: bridge._bind_call_outputs(validated_a, output_d, offsets_d),
                "scrubbed failure buffers were accepted")
        status, _, output_after, offsets_after = direct_call(run, frame_a)
        require(status == bridge.STATUS_OK and raw_bytes(output_after) == raw_bytes(output_a) and
                raw_bytes(offsets_after) == raw_bytes(offsets_a),
                "guard or state was not restored after a failed call")

        # --- ABI-level result/offset swaps ------------------------------------
        _, bound_a = bridge._bind_call_outputs(validated_a, output_a, offsets_a)
        compare_core(bound_a, envelope_a["core_result"])
        status, validated_b, output_b, offsets_b = direct_call(run, frame_b)
        require(status == bridge.STATUS_OK, "direct v2 call for frame B failed")
        refused(lambda: bridge._bind_call_outputs(validated_a, output_a, offsets_b),
                "frame A output with frame B offsets accepted")
        refused(lambda: bridge._bind_call_outputs(validated_a, output_b, offsets_a),
                "frame B output with frame A offsets accepted")
        refused(lambda: bridge._bind_call_outputs(validated_b, output_a, offsets_b),
                "frame A output bound to frame B accepted")
        # Equal lift totals and offsets: the host checks CANNOT tell these
        # results apart (nothing in CoreOutput identifies its input); only the
        # exact reference comparison rejects the swap. Recorded, not hidden.
        status, _, output_a1, offsets_a1 = direct_call(run, frame_a1)
        require(status == bridge.STATUS_OK and raw_bytes(offsets_a1) == raw_bytes(offsets_a),
                "frame A1 did not reproduce frame A's offsets")
        _, swapped_equal_lift = bridge._bind_call_outputs(validated_a, output_a1, offsets_a)
        require(swapped_equal_lift["lift_total"] == lift_a and
                not matches_reference(swapped_equal_lift, reference_a),
                "equal-lift result swap was not caught by the reference comparison")

        # --- single-word mutations of one successful call's buffers ----------
        def mutated(edit):
            output = bridge.CoreOutput.from_buffer_copy(output_a)
            offsets = bridge.OffsetTable.from_buffer_copy(offsets_a)
            edit(output, offsets)
            require(raw_bytes(output) != raw_bytes(output_a) or
                    raw_bytes(offsets) != raw_bytes(offsets_a), "a mutation fixture was a no-op")
            return lambda: bridge._bind_call_outputs(validated_a, output, offsets)

        def set_offset(index, delta):
            def edit(_output, offsets):
                offsets[index] += delta
            return edit

        def set_result(slot, encoding, field, value):
            def edit(output, _offsets):
                setattr(output.results[slot][encoding], field, value)
            return edit

        def set_entry(output, _offsets):
            output.results[0][1].entries[0] ^= 1

        def negate_minimum(output, _offsets):
            output.results[0][0].minimum = -output.results[0][0].minimum

        def bump_per_ch(output, _offsets):
            output.results[0][0].per_ch[1] += 1

        def dirty_unused(output, _offsets):
            output.results[1][0].word_count = 1

        cap = core.MAX_COMPACTED_ENTRIES
        for label, edit in (
                ("interior offset", set_offset(12345, 1)),
                ("final offset boundary", set_offset(core.STATE_COUNT, 1)),
                ("first offset boundary", set_offset(0, 1)),
                ("compacted entry", set_entry),
                ("minimum sign word", negate_minimum),
                ("minimum index", set_result(0, 0, "minimum_index", core.STATE_COUNT)),
                ("compacted count over cap", set_result(0, 0, "compacted_count", cap + 1)),
                ("illegal counter", set_result(0, 1, "illegal", 1)),
                ("overflow counter", set_result(0, 0, "compaction_overflows", 1)),
                ("qualification checksum", set_result(0, 0, "flags_checksum", 1)),
                ("per-c_H count", bump_per_ch),
                ("compaction checksum", set_result(0, 1, "compaction_checksum", 0)),
                ("unused slot", dirty_unused)):
            refused(mutated(edit), f"mutated {label} accepted")

        # --- direct C refusals: arguments, capacity, overlap, payload -------
        payload_abi, rows_abi = bridge.decode_frame(validated_a)
        for row_count in (0, 3):
            output, offsets = sentinel_buffers()
            require(run(C.byref(payload_abi), rows_abi, row_count, C.byref(output), offsets,
                        bridge.OFFSET_WORDS) == bridge.STATUS_REFUSED and untouched(output, offsets),
                    "invalid row count accepted or touched buffers")
        for capacity in (bridge.OFFSET_WORDS - 1, bridge.OFFSET_WORDS + 1, 0):
            output, offsets = sentinel_buffers()
            require(run(C.byref(payload_abi), rows_abi, 1, C.byref(output), offsets,
                        capacity) == bridge.STATUS_REFUSED and untouched(output, offsets),
                    "wrong offset capacity accepted or touched buffers")
        output, offsets = sentinel_buffers()
        require(run(C.byref(payload_abi), rows_abi, 1, C.byref(output), None,
                    bridge.OFFSET_WORDS) == bridge.STATUS_REFUSED and untouched(output),
                "null offset table accepted")
        overlapping = C.cast(C.addressof(output), C.POINTER(C.c_uint64))
        require(run(C.byref(payload_abi), rows_abi, 1, C.byref(output), overlapping,
                    bridge.OFFSET_WORDS) == bridge.STATUS_REFUSED and untouched(output),
                "overlapping output/offset buffers accepted")
        for label, c_value in (("fractional C", 2.5), ("out-of-range C", 1e200)):
            invalid = bridge.decode_frame(validated_a)[0]
            invalid.c_value = c_value
            output, offsets = sentinel_buffers()
            require(run(C.byref(invalid), rows_abi, 1, C.byref(output), offsets,
                        bridge.OFFSET_WORDS) == bridge.STATUS_REFUSED and scrubbed(output, offsets),
                    f"{label} accepted or left stale buffers")

        # --- deterministic re-entry: the guard held as if a call is in flight
        probe = C.CDLL(str(probe_library))
        probe.g9_core_v2_probe_hold.restype = C.c_uint32
        probe.g9_core_v2_probe_hold.argtypes = []
        probe.g9_core_v2_probe_release.restype = None
        probe.g9_core_v2_probe_release.argtypes = []
        _, probe_run = load_run(probe_library)
        require(probe.g9_core_v2_probe_hold() == 1, "probe could not take a free guard")
        try:
            require(probe.g9_core_v2_probe_hold() == 0, "a held guard was taken twice")
            for _ in range(2):
                status, _, output, offsets = direct_call(probe_run, frame_a)
                require(status == bridge.STATUS_BUSY and untouched(output, offsets),
                        "second direct C entry was not refused untouched")
            message = refused(lambda: bridge.run_host_emulated_frame_v2(frame_a, probe_library),
                              "bridge accepted a call while the guard was held")
            require("busy" in message, "held guard refused for an unexpected reason")
        finally:
            probe.g9_core_v2_probe_release()
        status, _, output, offsets = direct_call(probe_run, frame_a)
        require(status == bridge.STATUS_OK and raw_bytes(output) == raw_bytes(output_a) and
                raw_bytes(offsets) == raw_bytes(offsets_a),
                "guard release did not restore a correctly bound call")

        # --- real concurrency: never a mixed result ---------------------------
        barrier = threading.Barrier(3)
        outcomes: list[tuple[int, bridge.CoreOutput, bridge.OffsetTable]] = []
        errors: list[BaseException] = []

        def racer() -> None:
            try:
                payload_local, rows_local = bridge.decode_frame(validated_a)
                output_local, offsets_local = sentinel_buffers()
                barrier.wait()
                status_local = run(C.byref(payload_local), rows_local, len(rows_local),
                                   C.byref(output_local), offsets_local, bridge.OFFSET_WORDS)
                outcomes.append((status_local, output_local, offsets_local))
            except BaseException as exc:  # noqa: BLE001 - reported below
                errors.append(exc)

        threads = [threading.Thread(target=racer) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        require(not errors and len(outcomes) == 3, "concurrent direct calls raised")
        counts = {bridge.STATUS_OK: 0, bridge.STATUS_BUSY: 0}
        for status, output, offsets in outcomes:
            require(status in counts, "concurrent direct call returned an unexpected status")
            counts[status] += 1
            if status == bridge.STATUS_OK:
                require(raw_bytes(output) == raw_bytes(output_a) and
                        raw_bytes(offsets) == raw_bytes(offsets_a),
                        "a concurrent success returned a mixed result/offset pair")
            else:
                require(untouched(output, offsets), "a refused concurrent call touched its buffers")
        require(counts[bridge.STATUS_OK] >= 1, "no concurrent direct call succeeded")

        envelopes: list[dict[str, object]] = []
        bridge_errors: list[BaseException] = []

        def bridge_racer() -> None:
            try:
                envelopes.append(bridge.run_host_emulated_frame_v2(frame_a, library))
            except BaseException as exc:  # noqa: BLE001 - reported below
                bridge_errors.append(exc)

        threads = [threading.Thread(target=bridge_racer) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        require(not bridge_errors and len(envelopes) == 2 and
                all(envelope == envelope_a for envelope in envelopes),
                "Python-serialized concurrent bridge calls did not both bind correctly")

    mode = "python3 -O" if sys.flags.optimize else "python3"
    print(f"PASS Stage-2 host-stub v2 single-call core ABI ({mode}): exact Python comparison "
          f"for two frames, failure scrub, swaps, mutations, atomic re-entry guard "
          f"(threads ok={counts[bridge.STATUS_OK]} busy={counts[bridge.STATUS_BUSY]})")


if __name__ == "__main__":
    main()
