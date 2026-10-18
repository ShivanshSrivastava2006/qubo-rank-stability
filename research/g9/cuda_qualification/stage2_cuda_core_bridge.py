"""In-memory ABI bridge for the generic core; host-emulation fixtures only.

One validated input frame is decoded into the exact C ABI structs, passed to
the compiled core, and bound to the offset table copied from that same call.
This module does not compile or locate a library, open a Stage-2 input, or
write an artifact. Loading a real CUDA library remains unauthorized until a
separate owner release and integrated qualification review.
"""

from __future__ import annotations

import ctypes as C
import hashlib
from pathlib import Path
import sys

from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as core
from research.g9.cuda_qualification import stage2_cuda_input_frame as input_frame


SCHEMA = "decisions_os/g9_cuda_bound_core_result/v1"
ROW_CAPACITY = 2
ENCODING_COUNT = 2


class CoreBridgeError(RuntimeError):
    """A compiled ABI or its returned bounded data disagrees with the frame."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CoreBridgeError(message)


class PayloadData(C.Structure):
    _fields_ = [
        ("mu", C.c_double * core.ASSET_COUNT),
        ("sigma", C.c_double * (core.ASSET_COUNT * core.ASSET_COUNT)),
        ("prices", C.c_double * core.ASSET_COUNT),
        ("kappa_risk", C.c_double), ("k_value", C.c_double),
        ("c_value", C.c_double), ("b", C.c_double), ("lambda_ref", C.c_double),
        ("membership", (C.c_uint32 * core.SECTOR_SIZE) * core.SECTOR_COUNT),
    ]


class CoefficientData(C.Structure):
    _fields_ = [(name, C.c_double) for name in core.COEFFICIENT_FIELDS]


class ScanResult(C.Structure):
    _fields_ = [
        ("natural_checksum", C.c_uint64), ("controlled_checksum", C.c_uint64),
        ("flags_checksum", C.c_uint64), ("minimum_checksum", C.c_uint64),
        ("word_count", C.c_uint64), ("per_ch", C.c_uint64 * 3),
        ("illegal", C.c_uint32), ("nesting", C.c_uint32),
        ("nonfinite", C.c_uint32), ("disagreements", C.c_uint32),
        ("compacted_count", C.c_uint64), ("compaction_checksum", C.c_uint64),
        ("compaction_chunks", C.c_uint32), ("order_violations", C.c_uint32),
        ("compaction_mismatches", C.c_uint32), ("compaction_overflows", C.c_uint32),
        ("natural_minimum_checksum", C.c_uint64), ("minimum", C.c_double),
        ("minimum_index", C.c_uint64),
        ("entries", C.c_uint64 * core.MAX_COMPACTED_ENTRIES),
    ]


class CoreOutput(C.Structure):
    _fields_ = [
        ("results", (ScanResult * ENCODING_COUNT) * ROW_CAPACITY),
        ("lift_total", C.c_uint64), ("invalid_registers", C.c_uint32),
        ("row_count", C.c_uint32),
    ]


def expected_abi_layout() -> tuple[int, ...]:
    return (
        C.sizeof(PayloadData), C.sizeof(CoefficientData), C.sizeof(ScanResult), C.sizeof(CoreOutput),
        *(getattr(PayloadData, name).offset for name in
          ("mu", "sigma", "prices", "kappa_risk", "k_value", "c_value", "b", "lambda_ref", "membership")),
        *(getattr(ScanResult, name).offset for name in
          ("word_count", "per_ch", "illegal", "compacted_count", "compaction_checksum",
           "compaction_chunks", "natural_minimum_checksum", "minimum", "minimum_index", "entries")),
        *(getattr(CoreOutput, name).offset for name in ("results", "lift_total", "row_count")),
    )


def _decode_frame(frame: dict[str, object]) -> tuple[PayloadData, object]:
    encoded = frame["payload"]
    payload = PayloadData()
    for asset, word in enumerate(encoded["mu"]):
        payload.mu[asset] = float.fromhex(word)
    for asset, row in enumerate(encoded["sigma"]):
        for column, word in enumerate(row):
            payload.sigma[asset * core.ASSET_COUNT + column] = float.fromhex(word)
    for asset, word in enumerate(encoded["prices"]):
        payload.prices[asset] = float.fromhex(word)
    for target, source in (("kappa_risk", "kappa_risk"), ("k_value", "k"),
                           ("c_value", "c"), ("b", "b"), ("lambda_ref", "lambda_ref")):
        setattr(payload, target, float.fromhex(encoded[source]))
    for sector, block in enumerate(encoded["sectors"]):
        for member, asset in enumerate(block):
            payload.membership[sector][member] = asset
    rows = (CoefficientData * len(frame["coefficients"]))()
    for slot, record in enumerate(frame["coefficients"]):
        for name in core.COEFFICIENT_FIELDS:
            setattr(rows[slot], name, float.fromhex(record[name]))
    return payload, rows


def _load_checked_abi(library_path: Path):
    _require(sys.byteorder == "little", "the frozen uint64 stream requires a little-endian host")
    _require(library_path.is_file(), "compiled ABI library is missing")
    try:
        library = C.CDLL(str(library_path))
        layout = library.g9_core_abi_layout_v1
        run = library.g9_core_run_v1
        copy_offsets = library.g9_core_copy_offsets_v1
        backend = library.g9_core_backend_v1
    except (OSError, AttributeError) as exc:
        raise CoreBridgeError("compiled ABI exports are missing") from exc
    layout.argtypes = [C.POINTER(C.c_uint64), C.c_uint32]
    layout.restype = C.c_uint32
    run.argtypes = [C.POINTER(PayloadData), C.POINTER(CoefficientData), C.c_uint32,
                    C.POINTER(CoreOutput)]
    run.restype = C.c_uint32
    copy_offsets.argtypes = [C.POINTER(C.c_uint64), C.c_uint64]
    copy_offsets.restype = C.c_uint32
    backend.argtypes = []
    backend.restype = C.c_uint32
    expected = expected_abi_layout()
    actual = (C.c_uint64 * len(expected))()
    _require(layout(actual, len(expected)) == len(expected) and tuple(actual) == expected,
             "compiled ABI layout differs from the Python bridge")
    backend_kind = backend()
    _require(backend_kind in (0, 1), "compiled ABI backend tag is invalid")
    return run, copy_offsets, backend_kind


def _run_compiled_frame(frame: object, library_path: Path, *, require_backend: int) -> dict[str, object]:
    """Common ABI call, only behind a host fixture or an owner-released gate."""
    try:
        validated = input_frame.validate_input_frame(frame)
    except input_frame.InputFrameError as exc:
        raise CoreBridgeError("input frame is invalid") from exc
    payload, rows = _decode_frame(validated)
    run, copy_offsets, backend = _load_checked_abi(Path(library_path))
    _require(backend == require_backend, "compiled ABI backend is not authorized for this path")
    output = CoreOutput()
    _require(run(C.byref(payload), rows, len(rows), C.byref(output)) == 1,
             "compiled core refused the validated input")
    _require(output.row_count == len(rows) and output.invalid_registers == 0 and
             core.STATE_COUNT <= output.lift_total <= core.CACHE_CAPACITY,
             "compiled core returned invalid domain metadata")
    offsets = (C.c_uint64 * (core.STATE_COUNT + 1))()
    _require(copy_offsets(offsets, len(offsets)) == 1,
             "compiled core did not return its computed offsets")
    offset_bytes = C.string_at(C.addressof(offsets), C.sizeof(offsets))
    actual_offsets_sha = hashlib.sha256(offset_bytes).hexdigest()
    _require(actual_offsets_sha == validated["offsets_sha256"],
             "compiled core offset table differs from input-frame identity")
    _require(offsets[0] == 0 and offsets[core.STATE_COUNT] == output.lift_total,
             "compiled core offset boundaries are invalid")
    summaries: dict[tuple[int, str], dict[str, object]] = {}
    for slot in range(len(rows)):
        for encoding_index, encoding in enumerate(core.ENCODINGS):
            result = output.results[slot][encoding_index]
            _require(all(getattr(result, name) == 0 for name in
                         ("illegal", "nesting", "nonfinite", "disagreements",
                          "order_violations", "compaction_mismatches", "compaction_overflows")),
                     "compiled core returned nonzero failure counters")
            count = result.compacted_count
            _require(1 <= count <= core.MAX_COMPACTED_ENTRIES,
                     "compiled core returned an invalid compacted count")
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
    for slot in range(len(rows), ROW_CAPACITY):
        for encoding_index in range(ENCODING_COUNT):
            unused = output.results[slot][encoding_index]
            _require(C.string_at(C.addressof(unused), C.sizeof(unused)) ==
                     bytes(C.sizeof(unused)), "unused core output slot is not zero")
    raw = {"lift_total": output.lift_total, "record_count": len(rows), "summaries": summaries}
    return {"schema": SCHEMA, "input_frame_sha256": validated["content_sha256"],
            "offsets_sha256": actual_offsets_sha, "core_result": raw}


def run_host_emulated_frame(frame: object, library_path: Path) -> dict[str, object]:
    """Exercise the same-call binding with a caller-built g++ host-stub library.

    This is a fixture surface, not permission to load a CUDA shared library.
    The future GPU qualification harness calls the private common ABI path
    only after its separate owner-release guard has passed.
    """
    return _run_compiled_frame(frame, library_path, require_backend=0)
