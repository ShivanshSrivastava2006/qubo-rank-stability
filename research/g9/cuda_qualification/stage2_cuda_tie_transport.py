"""Python reference for the synthetic CUDA stable tie-compaction self-test.

Scope.  This component transports already-computed tie flags.  It never
computes an energy, a minimum, a tie threshold, a label, or a rate: its input
is a fixed synthetic table of canonical decoded indices with packed nested
D015-like flags, and its output is a compacted word stream plus counters.  It
is isolated from canonical inputs, ledgers, solvers, the Stage-2 generator and
NumPy, and it writes no file.

Flag encoding.  Bit 0 is the ``c_H = 1024`` membership, bit 1 is ``2048`` and
bit 2 is ``4096``.  Because the D015 tolerance grows with ``c_H``, membership
is nested, so the only legal values are:

* ``0`` — not tied;
* ``4`` — tied at 4096 only;
* ``6`` — tied at 2048 and 4096;
* ``7`` — tied at 1024, 2048 and 4096.

Every other value is rejected.  ``1``, ``2``, ``3`` and ``5`` are additionally
counted as nesting violations because they claim a tighter threshold without
the looser one that must contain it.

Compaction contract.  A flagged entry becomes the word
``(flags << 32) | canonical_index``.  The stream is produced by counting
flagged entries per fixed contiguous chunk, forming exclusive offsets in
ascending chunk order, and writing each chunk's flagged entries in ascending
local order — no atomics, no shared memory, no sort, and no dependence on
thread scheduling.  The resulting stream is exactly the flagged entries in
ascending canonical-index order.
"""
from __future__ import annotations

import struct
from typing import Mapping, Sequence


STATE_COUNT = 257
CHUNK_SIZE = 32
CHUNK_COUNT = (STATE_COUNT + CHUNK_SIZE - 1) // CHUNK_SIZE
INDEX_STRIDE = 4073
CH_VALUES = (1024, 2048, 4096)
LEGAL_FLAGS = (0, 4, 6, 7)
FORCED_EMPTY_CHUNK = 5
SENTINEL = (1 << 64) - 1
FNV_OFFSET, FNV_PRIME, MASK64 = 1469598103934665603, 1099511628211, (1 << 64) - 1
SCHEMA = "decisions_os/g9_cuda_tie_transport_self_test/v1"


class TieTransportError(RuntimeError):
    """Typed refusal for a malformed flag table, stream, or self-test report."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TieTransportError(message)


def _fnv(state: int, word: int) -> int:
    return ((state ^ word) * FNV_PRIME) & MASK64


def _word(value: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def synthetic_index(position: int) -> int:
    """Strictly ascending synthetic canonical indices inside the 20-bit space."""
    _require(type(position) is int and 0 <= position < STATE_COUNT, "table position is out of range")
    index = position * INDEX_STRIDE
    _require(index < (1 << 20), "synthetic index escaped the 20-bit decoded space")
    return index


def synthetic_flags(position: int) -> int:
    """Fixed deterministic legal flag pattern; no result is consulted."""
    _require(type(position) is int and 0 <= position < STATE_COUNT, "table position is out of range")
    if position // CHUNK_SIZE == FORCED_EMPTY_CHUNK or position == STATE_COUNT - 1:
        return 0
    if position % 7 == 3:
        return 7
    if position % 5 == 2:
        return 6
    if position % 11 == 4:
        return 4
    return 0


def synthetic_table() -> tuple[tuple[int, int], ...]:
    """The fixed (canonical index, flags) control table for this component."""
    return tuple((synthetic_index(position), synthetic_flags(position)) for position in range(STATE_COUNT))


def flag_is_legal(flags: int) -> bool:
    return flags in LEGAL_FLAGS


def flag_violates_nesting(flags: int) -> bool:
    """A tighter-threshold bit set without the looser bit that must contain it."""
    tied_1024 = bool(flags & 1)
    tied_2048 = bool(flags & 2)
    tied_4096 = bool(flags & 4)
    return (tied_1024 and not tied_2048) or (tied_2048 and not tied_4096)


def compact_word(index: int, flags: int) -> int:
    """The transported word: flags in the high half, canonical index in the low half."""
    _require(type(index) is int and 0 <= index < (1 << 32), "canonical index does not fit the word")
    _require(type(flags) is int and 0 <= flags < (1 << 32), "flags do not fit the word")
    return (flags << 32) | index


def chunk_counts(table: Sequence[tuple[int, int]]) -> tuple[int, ...]:
    """Flagged entries per fixed contiguous chunk, in ascending chunk order."""
    counts = [0] * CHUNK_COUNT
    for position, (_, flags) in enumerate(table):
        if flags != 0:
            counts[position // CHUNK_SIZE] += 1
    return tuple(counts)


def exclusive_offsets(counts: Sequence[int]) -> tuple[int, ...]:
    """Exclusive prefix in ascending chunk order; the last entry is the total."""
    offsets = [0]
    running = 0
    for count in counts:
        running += count
        offsets.append(running)
    return tuple(offsets)


def compact_stream(table: Sequence[tuple[int, int]]) -> tuple[int, ...]:
    """Stable chunked compaction: ascending chunks, ascending within each chunk."""
    counts = chunk_counts(table)
    offsets = exclusive_offsets(counts)
    stream = [SENTINEL] * offsets[-1]
    for chunk in range(CHUNK_COUNT):
        cursor = offsets[chunk]
        start = chunk * CHUNK_SIZE
        stop = min(start + CHUNK_SIZE, len(table))
        for position in range(start, stop):
            index, flags = table[position]
            if flags != 0:
                stream[cursor] = compact_word(index, flags)
                cursor += 1
    return tuple(stream)


def audit_stream(stream: Sequence[int]) -> dict[str, int]:
    """Ordering, duplicate, and sentinel audit over the compacted words only."""
    order_violations = 0
    duplicate_entries = 0
    unwritten_slots = 0
    previous: int | None = None
    for word in stream:
        if word == SENTINEL:
            unwritten_slots += 1
            continue
        index = word & 0xFFFFFFFF
        if previous is not None:
            if index == previous:
                duplicate_entries += 1
            if index <= previous:
                order_violations += 1
        previous = index
    return {"order_violations": order_violations, "duplicate_entries": duplicate_entries,
            "unwritten_slots": unwritten_slots}


def expected_self_test() -> dict[str, object]:
    """Reproduce every device checksum and counter from the fixed control table."""
    table = synthetic_table()
    counts = chunk_counts(table)
    offsets = exclusive_offsets(counts)
    stream = compact_stream(table)
    audit = audit_stream(stream)
    input_checksum = FNV_OFFSET
    illegal = 0
    nesting = 0
    per_ch = [0, 0, 0]
    direct_total = 0
    for index, flags in table:
        input_checksum = _fnv(input_checksum, index)
        input_checksum = _fnv(input_checksum, flags)
        if not flag_is_legal(flags):
            illegal += 1
        if flag_violates_nesting(flags):
            nesting += 1
        for bit in range(len(CH_VALUES)):
            if flags & (1 << bit):
                per_ch[bit] += 1
        if flags != 0:
            direct_total += 1
    compacted_checksum = FNV_OFFSET
    for word in stream:
        compacted_checksum = _fnv(compacted_checksum, word)
    offsets_checksum = FNV_OFFSET
    for count in counts:
        offsets_checksum = _fnv(offsets_checksum, count)
    for offset in offsets:
        offsets_checksum = _fnv(offsets_checksum, offset)
    return {"schema": SCHEMA, "state_count": STATE_COUNT, "chunk_size": CHUNK_SIZE,
            "chunk_count": CHUNK_COUNT, "input_checksum": f"{input_checksum:016x}",
            "offsets_checksum": f"{offsets_checksum:016x}",
            "compacted_checksum": f"{compacted_checksum:016x}",
            "compacted_total": offsets[-1], "direct_flagged_total": direct_total,
            "total_mismatch": 0 if offsets[-1] == direct_total else 1,
            "count_c_h_1024": per_ch[0], "count_c_h_2048": per_ch[1], "count_c_h_4096": per_ch[2],
            "illegal_flag_entries": illegal, "nesting_violations": nesting,
            "order_violations": audit["order_violations"], "duplicate_entries": audit["duplicate_entries"],
            "unwritten_slots": audit["unwritten_slots"], "sentinel_violations": 0,
            "scientific_outputs": "intentionally absent", "verdict": "pass"}


def validate_self_test_report(payload: object) -> dict[str, object]:
    """Fail closed unless the device reproduces every expected field exactly."""
    expected = expected_self_test()
    required = set(expected) | {"device_index", "device_name"}
    _require(isinstance(payload, dict) and set(payload) == required, "tie-transport report has wrong key set")
    _require(type(payload["device_index"]) is int and payload["device_index"] >= 0
             and type(payload["device_name"]) is str and payload["device_name"],
             "tie-transport device metadata malformed")
    for key in ("state_count", "chunk_size", "chunk_count", "compacted_total", "direct_flagged_total",
                "total_mismatch", "count_c_h_1024", "count_c_h_2048", "count_c_h_4096",
                "illegal_flag_entries", "nesting_violations", "order_violations", "duplicate_entries",
                "unwritten_slots", "sentinel_violations"):
        _require(type(payload[key]) is int, f"tie-transport integer field has wrong type: {key}")
    # The report may carry counters and checksums only; a compacted index or
    # word list would leak the transported payload itself.
    for key, value in payload.items():
        _require(not isinstance(value, (list, tuple, dict)), f"tie-transport report carries a container: {key}")
    for key, value in expected.items():
        _require(payload[key] == value, f"tie-transport self-test mismatch: {key}")
    return dict(payload)
