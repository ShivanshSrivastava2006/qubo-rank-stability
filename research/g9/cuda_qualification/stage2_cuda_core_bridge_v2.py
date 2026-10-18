"""Version-2 single-call ABI host bridge; offline host-stub fixtures only.

OFFLINE / SYNTHETIC-ONLY DRAFT for the Gate-9 result/offset binding design
(GATE_9_DEVICE_RESULT_BINDING_DESIGN_DRAFT.md). It sits beside the accepted
version-1 bridge, which it imports but never modifies. One validated input
frame is decoded into the unchanged ABI structs and passed to ONE call of
``g9_core_run_v2``, which returns the bounded ``CoreOutput`` and the full
``STATE_COUNT + 1`` offset table computed by that same call. The host then
hashes the returned table, compares it with the frame's expected identity,
checks every bounded counter and capacity, and returns a versioned envelope.

What the envelope does NOT prove: ``input_frame_sha256`` is host bookkeeping
attached by this process, not a device attestation; ``result_sha256`` detects
accidental storage/transport corruption only, since any holder can recompute
it. Nothing here shows which binary, compiler flags, GPU or image produced the
numbers. This module loads only a caller-built g++ host-stub library (backend
0). It refuses a CUDA library outright: a v2 CUDA run needs a fresh,
separately approved §A qualification, and Gate-9 §B remains open.
"""

from __future__ import annotations

import ctypes as C
import hashlib
import math
from pathlib import Path
import struct
import sys
import threading

from research.g9.cuda_qualification import stage2_cuda_core_bridge as bridge_v1
from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as core
from research.g9.cuda_qualification import stage2_cuda_input_frame as input_frame


SCHEMA = "decisions_os/g9_cuda_bound_core_result/v2"
RESULT_COMMITMENT_SCHEMA = "decisions_os/g9_cuda_core_result_commitment/v2"
ABI_NAME = "g9_core_run_v2"
FRAME_HASH_ROLE = "host_bookkeeping_not_device_attestation"
RESULT_HASH_ROLE = "accidental_corruption_check_only"
ENVELOPE_FIELDS = frozenset({"schema", "abi", "backend", "input_frame_sha256",
                             "input_frame_sha256_role", "offsets_sha256", "core_result",
                             "result_sha256", "result_sha256_role"})
SUMMARY_FIELDS = frozenset({"word_count", "minimum", "minimum_index", "per_ch", "illegal",
                            "nesting", "compacted_count", "compaction_chunks",
                            "compaction_checksum", "compacted_entries"})
FAILURE_COUNTERS = ("illegal", "nesting", "nonfinite", "disagreements", "order_violations",
                    "compaction_mismatches", "compaction_overflows")
QUALIFICATION_ONLY_CHECKSUMS = ("natural_checksum", "controlled_checksum", "flags_checksum",
                                "natural_minimum_checksum")
STATUS_REFUSED = 0
STATUS_OK = 1
STATUS_BUSY = 2
OFFSET_WORDS = core.STATE_COUNT + 1
ALL_THRESHOLDS_FLAGS = 7
MASK64 = core.MASK64

# The unchanged version-1 ctypes structs are the v2 struct layout.
PayloadData = bridge_v1.PayloadData
CoefficientData = bridge_v1.CoefficientData
ScanResult = bridge_v1.ScanResult
CoreOutput = bridge_v1.CoreOutput
OffsetTable = C.c_uint64 * OFFSET_WORDS

# Held across library loading, the single ABI call and every check that
# follows. The C guard separately refuses entries that bypass this lock.
_ABI_LOCK = threading.Lock()


class CoreBridgeV2Error(RuntimeError):
    """The v2 ABI refused, failed, or returned data that disagrees with the frame."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CoreBridgeV2Error(message)


def _fnv(state: int, word: int) -> int:
    return ((state ^ word) * core.FNV_PRIME) & MASK64


def _double_word(value: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def expected_abi_layout_v2() -> tuple[int, ...]:
    return (*bridge_v1.expected_abi_layout(), OFFSET_WORDS, C.sizeof(OffsetTable))


def decode_frame(validated: dict[str, object]) -> tuple[PayloadData, object]:
    """Exact binary64 words of an ALREADY validated frame, in the v1 ABI structs."""
    return bridge_v1._decode_frame(validated)


def _load_checked_abi_v2(library_path: Path):
    _require(sys.byteorder == "little", "the frozen uint64 stream requires a little-endian host")
    _require(library_path.is_file(), "compiled v2 ABI library is missing")
    try:
        library = C.CDLL(str(library_path))
        layout = library.g9_core_abi_layout_v2
        run = library.g9_core_run_v2
        backend = library.g9_core_backend_v2
    except (OSError, AttributeError) as exc:
        raise CoreBridgeV2Error("compiled v2 ABI exports are missing") from exc
    for retired in ("g9_core_run_v1", "g9_core_copy_offsets_v1", "g9_core_abi_layout_v1"):
        _require(not hasattr(library, retired),
                 "v2 library still exports a version-1 or separate offset-copy entry")
    layout.argtypes = [C.POINTER(C.c_uint64), C.c_uint32]
    layout.restype = C.c_uint32
    run.argtypes = [C.POINTER(PayloadData), C.POINTER(CoefficientData), C.c_uint32,
                    C.POINTER(CoreOutput), C.POINTER(C.c_uint64), C.c_uint64]
    run.restype = C.c_uint32
    backend.argtypes = []
    backend.restype = C.c_uint32
    expected = expected_abi_layout_v2()
    actual = (C.c_uint64 * len(expected))()
    _require(layout(actual, len(expected)) == len(expected) and tuple(actual) == expected,
             "compiled v2 ABI layout differs from the Python bridge")
    backend_kind = backend()
    _require(backend_kind in (0, 1), "compiled v2 ABI backend tag is invalid")
    return run, backend_kind


def require_bounded_result(raw: object, record_count: int) -> None:
    """Direct field checks on a bounded core result (bridge and consumer side).

    Checks shapes, capacities, legal flags, strict canonical order, per-c_H
    counts recomputed from the entries, the entry checksum, and that each
    stream's first-seen minimum is itself a compacted all-threshold entry.
    """
    _require(type(record_count) is int and 1 <= record_count <= bridge_v1.ROW_CAPACITY,
             "record count is outside the ABI row capacity")
    _require(type(raw) is dict and set(raw) == {"lift_total", "record_count", "summaries"},
             "bounded result has the wrong key set")
    lift_total = raw["lift_total"]
    _require(type(lift_total) is int and core.STATE_COUNT <= lift_total <= core.CACHE_CAPACITY,
             "lift total is outside the slack cache capacity")
    _require(type(raw["record_count"]) is int and raw["record_count"] == record_count,
             "bounded result has the wrong row count")
    summaries = raw["summaries"]
    expected_keys = {(slot, encoding) for slot in range(record_count) for encoding in core.ENCODINGS}
    _require(type(summaries) is dict and set(summaries) == expected_keys,
             "bounded result has the wrong stream set")
    for (_, encoding), summary in summaries.items():
        _require(type(summary) is dict and set(summary) == SUMMARY_FIELDS,
                 "bounded summary has the wrong field set")
        word_count = core.STATE_COUNT if encoding == "unbalanced" else lift_total
        _require(type(summary["word_count"]) is int and summary["word_count"] == word_count,
                 "stream word count differs from its domain")
        _require(type(summary["illegal"]) is int and type(summary["nesting"]) is int and
                 summary["illegal"] == 0 and summary["nesting"] == 0,
                 "bounded summary reports illegal or non-nested flags")
        count = summary["compacted_count"]
        entries = summary["compacted_entries"]
        _require(type(count) is int and 1 <= count <= core.MAX_COMPACTED_ENTRIES and
                 type(entries) is tuple and len(entries) == count,
                 "compacted entry count is outside the declared cap")
        _require(type(summary["compaction_chunks"]) is int and
                 summary["compaction_chunks"] == core.compaction_chunk_count(word_count),
                 "compaction chunk count differs from the stream length")
        previous = -1
        per_ch = [0] * len(core.CH_VALUES)
        checksum = core.FNV_OFFSET
        for entry in entries:
            _require(type(entry) is int and 0 <= entry <= MASK64, "compacted entry is not a uint64")
            flags, index = entry >> 32, entry & 0xFFFFFFFF
            _require(flags in core.COMPACTED_FLAGS, "compacted entry carries an illegal flag word")
            _require(previous < index < word_count,
                     "compacted entries are not strictly ascending inside the stream")
            previous = index
            for bit in range(len(per_ch)):
                per_ch[bit] += (flags >> bit) & 1
            checksum = _fnv(checksum, entry)
        _require(type(summary["per_ch"]) is tuple and
                 all(type(value) is int for value in summary["per_ch"]) and
                 summary["per_ch"] == tuple(per_ch),
                 "per-c_H counts differ from the compacted entries")
        _require(type(summary["compaction_checksum"]) is int and
                 summary["compaction_checksum"] == checksum,
                 "compaction checksum differs from the compacted entries")
        minimum = summary["minimum"]
        minimum_index = summary["minimum_index"]
        _require(type(minimum) is float and math.isfinite(minimum), "stream minimum is not finite")
        _require(type(minimum_index) is int and 0 <= minimum_index < word_count,
                 "stream minimum index is outside the stream")
        _require(((ALL_THRESHOLDS_FLAGS << 32) | minimum_index) in entries,
                 "stream minimum is missing from its compacted tie entries")


def _bind_call_outputs(validated: dict[str, object], output: CoreOutput,
                       offsets: OffsetTable) -> tuple[str, dict[str, object]]:
    """Bind the outputs of ONE successful v2 call to the frame that produced its input.

    Must be applied only to buffers from a call that returned STATUS_OK.
    """
    record_count = len(validated["coefficients"])
    _require(C.sizeof(offsets) == C.sizeof(OffsetTable), "offset table capacity differs")
    offset_bytes = C.string_at(C.addressof(offsets), C.sizeof(offsets))
    offsets_sha = hashlib.sha256(offset_bytes).hexdigest()
    _require(offsets_sha == validated["offsets_sha256"],
             "returned offset table differs from the input-frame identity")
    _require(output.row_count == record_count and output.invalid_registers == 0 and
             core.STATE_COUNT <= output.lift_total <= core.CACHE_CAPACITY,
             "compiled core returned invalid domain metadata")
    _require(offsets[0] == 0 and offsets[core.STATE_COUNT] == output.lift_total,
             "returned offset boundaries do not match the bounded output")
    summaries: dict[tuple[int, str], dict[str, object]] = {}
    for slot in range(record_count):
        for encoding_index, encoding in enumerate(core.ENCODINGS):
            result = output.results[slot][encoding_index]
            _require(all(getattr(result, name) == 0 for name in FAILURE_COUNTERS),
                     "compiled core returned nonzero failure counters")
            _require(all(getattr(result, name) == 0 for name in QUALIFICATION_ONLY_CHECKSUMS),
                     "generic call returned qualification-only checksums")
            count = result.compacted_count
            _require(1 <= count <= core.MAX_COMPACTED_ENTRIES,
                     "compiled core returned an invalid compacted count")
            tail = C.string_at(C.addressof(result.entries) + 8 * count,
                               8 * (core.MAX_COMPACTED_ENTRIES - count))
            _require(tail == bytes(len(tail)), "entries beyond the compacted count are not zero")
            _require(result.minimum_checksum ==
                     _fnv(_fnv(core.FNV_OFFSET, _double_word(result.minimum)), result.minimum_index),
                     "minimum checksum differs from the returned minimum")
            summaries[(slot, encoding)] = {
                "word_count": result.word_count,
                "minimum": result.minimum,
                "minimum_index": result.minimum_index,
                "per_ch": tuple(result.per_ch),
                "illegal": result.illegal,
                "nesting": result.nesting,
                "compacted_count": count,
                "compaction_chunks": result.compaction_chunks,
                "compaction_checksum": result.compaction_checksum,
                "compacted_entries": tuple(result.entries[:count]),
            }
    for slot in range(record_count, bridge_v1.ROW_CAPACITY):
        for encoding_index in range(bridge_v1.ENCODING_COUNT):
            unused = output.results[slot][encoding_index]
            _require(C.string_at(C.addressof(unused), C.sizeof(unused)) ==
                     bytes(C.sizeof(unused)), "unused core output slot is not zero")
    raw = {"lift_total": output.lift_total, "record_count": record_count, "summaries": summaries}
    require_bounded_result(raw, record_count)
    return offsets_sha, raw


def result_commitment(input_frame_sha256: str, offsets_sha256: str,
                      raw: dict[str, object]) -> str:
    """Domain-separated canonical-JSON SHA-256; each minimum by its exact binary64 word."""
    streams = []
    for slot in range(raw["record_count"]):
        for encoding in core.ENCODINGS:
            summary = raw["summaries"][(slot, encoding)]
            body = {name: list(value) if type(value) is tuple else value
                    for name, value in summary.items() if name != "minimum"}
            body["minimum_word"] = format(_double_word(summary["minimum"]), "016x")
            streams.append({"slot": slot, "encoding": encoding, "summary": body})
    commitment = {"schema": RESULT_COMMITMENT_SCHEMA, "input_frame_sha256": input_frame_sha256,
                  "offsets_sha256": offsets_sha256, "lift_total": raw["lift_total"],
                  "record_count": raw["record_count"], "streams": streams}
    return hashlib.sha256(input_frame.canonical_bytes(commitment)).hexdigest()


def _envelope(validated: dict[str, object], backend: int, offsets_sha: str,
              raw: dict[str, object]) -> dict[str, object]:
    frame_sha = validated["content_sha256"]
    return {"schema": SCHEMA, "abi": ABI_NAME, "backend": backend,
            "input_frame_sha256": frame_sha, "input_frame_sha256_role": FRAME_HASH_ROLE,
            "offsets_sha256": offsets_sha, "core_result": raw,
            "result_sha256": result_commitment(frame_sha, offsets_sha, raw),
            "result_sha256_role": RESULT_HASH_ROLE}


def _run_compiled_frame_v2(frame: object, library_path: Path, *,
                           require_backend: int) -> dict[str, object]:
    # This draft loads host-stub libraries only; there is no v2 CUDA release.
    _require(require_backend == 0, "no CUDA v2 library may be loaded by this offline draft")
    try:
        validated = input_frame.validate_input_frame(frame)
    except input_frame.InputFrameError as exc:
        raise CoreBridgeV2Error("input frame is invalid") from exc
    payload, rows = decode_frame(validated)
    with _ABI_LOCK:
        run, backend = _load_checked_abi_v2(Path(library_path))
        _require(backend == require_backend, "compiled v2 ABI backend is not authorized for this path")
        output = CoreOutput()
        offsets = OffsetTable()
        status = run(C.byref(payload), rows, len(rows), C.byref(output), offsets, OFFSET_WORDS)
        # A failed or refused call's buffers are never read, even if the
        # library had partially filled them.
        _require(status != STATUS_BUSY, "compiled v2 core is busy with another call")
        _require(status == STATUS_OK, "compiled v2 core refused or failed the validated input")
        offsets_sha, raw = _bind_call_outputs(validated, output, offsets)
        return _envelope(validated, backend, offsets_sha, raw)


def run_host_emulated_frame_v2(frame: object, library_path: Path) -> dict[str, object]:
    """Exercise the single-call binding with a caller-built g++ host-stub library."""
    return _run_compiled_frame_v2(frame, library_path, require_backend=0)


def require_consumer_envelope(envelope: object, payload, records, offsets_sha256: str
                              ) -> dict[str, object]:
    """Consumer-side acceptance against the consumer's OWN validated inputs.

    Rebuilds the expected frame from separately held payload, ordered rows and
    expected offset identity; never trusts the envelope's echoed hashes alone.
    Returns the bounded core result only when every check passes.
    """
    try:
        expected = input_frame.build_input_frame(payload, records, offsets_sha256)
    except input_frame.InputFrameError as exc:
        raise CoreBridgeV2Error("consumer expected inputs are invalid") from exc
    _require(type(envelope) is dict and set(envelope) == ENVELOPE_FIELDS,
             "envelope has the wrong key set")
    _require(envelope["schema"] == SCHEMA and envelope["abi"] == ABI_NAME and
             envelope["input_frame_sha256_role"] == FRAME_HASH_ROLE and
             envelope["result_sha256_role"] == RESULT_HASH_ROLE,
             "envelope schema or declared roles differ")
    _require(type(envelope["backend"]) is int and envelope["backend"] == 0,
             "envelope backend is not the host-emulation stub")
    _require(envelope["input_frame_sha256"] == expected["content_sha256"],
             "envelope frame differs from the consumer's expected payload and rows")
    _require(envelope["offsets_sha256"] == expected["offsets_sha256"],
             "envelope offset identity differs from the consumer's expected table")
    raw = envelope["core_result"]
    require_bounded_result(raw, len(expected["coefficients"]))
    _require(envelope["result_sha256"] ==
             result_commitment(expected["content_sha256"], expected["offsets_sha256"], raw),
             "envelope result commitment differs from its bounded result")
    return raw
