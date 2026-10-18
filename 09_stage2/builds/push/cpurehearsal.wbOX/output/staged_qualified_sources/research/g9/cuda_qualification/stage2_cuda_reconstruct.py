"""In-memory D015/D016 reconstruction from a bounded CUDA core result.

The caller supplies the reviewed core's minimum and compacted tie words, the
already validated active-CSB slack offsets, and frozen decoded classifiers.
This module reads no instance, ledger, or artifact and performs no energy scan.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import math
import struct

from src.g4.classification import DecodedClassifier
from src.g5.certify import decode_x_e
from src.g5.domains import BinaryDomain


STATE_COUNT = 1 << 20
MAX_LIFTS_PER_STATE = 32
MAX_COMPACTED_ENTRIES = 1 << 14
CH_VALUES = (1024, 2048, 4096)
CF_VALUES = (1024, 2048, 4096)
PRIMARY_PAIR = (2048, 2048)
DIAGNOSTIC_PAIRS = ((1024, 2048), (4096, 2048), (2048, 1024), (2048, 4096))
EPSILON = math.ldexp(1.0, -52)
LEGAL_FLAGS = (4, 6, 7)
INDEX_MASK = (1 << 32) - 1


class ReconstructionError(RuntimeError):
    """A compact core result cannot be reconstructed under the frozen rules."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReconstructionError(message)


def _finite_float(value: object, name: str) -> float:
    _require(type(value) is float and math.isfinite(value), f"{name} must be finite binary64")
    return value


def _index(value: object, upper: int, name: str) -> int:
    _require(type(value) is int and 0 <= value < upper, f"{name} outside its canonical domain")
    return value


def _stream_sha256(indices: Sequence[int]) -> str:
    digest = hashlib.sha256()
    for index in indices:
        digest.update(struct.pack("<Q", index))
    return digest.hexdigest()


@dataclass(frozen=True)
class SlackIndexMap:
    """Validated offsets for decoding a slack-cache index back to its x index.

    Validate the million-state prefix once when an instance is prepared, then
    use binary search for each compacted entry of each coordinate.
    """

    offsets: Sequence[int]
    lift_total: int
    _offset_bytes: bytes = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        offsets = self.offsets
        _require(isinstance(offsets, Sequence) and len(offsets) == STATE_COUNT + 1,
                 "slack offsets must have one boundary per decoded state")
        _require(type(self.lift_total) is int and STATE_COUNT <= self.lift_total
                 <= STATE_COUNT * MAX_LIFTS_PER_STATE, "slack lift total outside the declared bound")
        _require(type(offsets[0]) is int and offsets[0] == 0,
                 "slack offsets must start at zero")
        previous = 0
        canonical = bytearray(8 * len(offsets))
        for position in range(1, len(offsets)):
            current = offsets[position]
            _require(type(current) is int and 1 <= current - previous <= MAX_LIFTS_PER_STATE,
                     f"slack offset drift at decoded state {position - 1}")
            struct.pack_into("<Q", canonical, 8 * position, current)
            previous = current
        _require(previous == self.lift_total, "slack offsets do not cover the declared lift total")
        object.__setattr__(self, "_offset_bytes", bytes(canonical))

    @property
    def offsets_sha256(self) -> str:
        """SHA-256 of the immutable little-endian uint64 offset snapshot."""
        return hashlib.sha256(self._offset_bytes).hexdigest()

    def decoded_index(self, lift_index: int) -> int:
        _index(lift_index, self.lift_total, "slack lift index")
        # Search the validated immutable snapshot, never the caller's possibly
        # mutable array. The endianness is fixed even across host platforms.
        left, right = 0, STATE_COUNT + 1
        while left < right:
            middle = (left + right) // 2
            boundary = struct.unpack_from("<Q", self._offset_bytes, 8 * middle)[0]
            if boundary <= lift_index:
                left = middle + 1
            else:
                right = middle
        decoded = left - 1
        _require(0 <= decoded < STATE_COUNT, "slack index did not decode")
        return decoded


def _compact_entries(entries: Sequence[int], domain_size: int, minimum_index: int) -> tuple[tuple[int, int], ...]:
    _require(isinstance(entries, Sequence) and 1 <= len(entries) <= MAX_COMPACTED_ENTRIES,
             "compacted tie count outside the declared bound")
    parsed: list[tuple[int, int]] = []
    previous = -1
    winner_seen = False
    for word in entries:
        _require(type(word) is int and 0 <= word < (1 << 64), "compacted word is not uint64")
        flag, index = word >> 32, word & INDEX_MASK
        _require(flag in LEGAL_FLAGS, "compacted word has an illegal D015 flag")
        _index(index, domain_size, "compacted index")
        _require(index > previous, "compacted indices are not strictly ascending")
        if index == minimum_index:
            _require(flag == 7, "minimum state is not tied at every c_H")
            winner_seen = True
        parsed.append((index, flag))
        previous = index
    _require(winner_seen, "minimum index is absent from the compacted ties")
    return tuple(parsed)


def _classifiers(classifiers: Mapping[int, DecodedClassifier], lambda_ref: float) -> None:
    _require(isinstance(classifiers, Mapping) and set(classifiers) == set(CF_VALUES),
             "classifier set must contain exactly the three D015 c_f values")
    first_objective = None
    first_feasible = None
    for c_f in CF_VALUES:
        classifier = classifiers[c_f]
        _require(isinstance(classifier, DecodedClassifier), "classifier has the wrong type")
        service = classifier.optimum_service
        _require(service.c_f == float(c_f) and service.lambda_ref == lambda_ref,
                 "classifier comparator is not bound to c_f and lambda_ref")
        if first_objective is None:
            first_objective, first_feasible = service.objective, classifier.feasible
        else:
            _require(service.objective is first_objective and classifier.feasible is first_feasible,
                     "D015 c_f diagnostics changed the original problem")


def reconstruct_stream(encoding: str, minimum: float, minimum_index: int,
                       entries: Sequence[int], slack: SlackIndexMap,
                       classifiers: Mapping[int, DecodedClassifier],
                       f_star: float, lambda_ref: float) -> dict[str, object]:
    """Return primary and diagnostic summaries, with no raw tie set retained."""
    _require(encoding in ("unbalanced", "slack"), "unknown encoding")
    minimum = _finite_float(minimum, "minimum")
    f_star = _finite_float(f_star, "f_star")
    lambda_ref = _finite_float(lambda_ref, "lambda_ref")
    _require(lambda_ref > 0.0, "lambda_ref must be strictly positive")
    _require(isinstance(slack, SlackIndexMap), "slack index map is required")
    _classifiers(classifiers, lambda_ref)
    domain_size = STATE_COUNT if encoding == "unbalanced" else slack.lift_total
    _index(minimum_index, domain_size, "minimum index")
    compact = _compact_entries(entries, domain_size, minimum_index)
    binary = BinaryDomain(20)

    reconstructions: dict[int, tuple[list[int], list[tuple[int, ...]], list[int]]] = {}
    previous_tied: set[int] = set()
    for bit, c_h in enumerate(CH_VALUES):
        tied = [index for index, flags in compact if flags & (1 << bit)]
        _require(tied and minimum_index in tied, "D015 tie set omits the minimum")
        _require(previous_tied <= set(tied), "D015 tie sets are not nested")
        previous_tied = set(tied)
        decoded = decode_x_e(
            tied,
            lambda index: binary[index if encoding == "unbalanced" else slack.decoded_index(index)],
        )
        decoded_indices = [sum(bit_value << (19 - asset) for asset, bit_value in enumerate(x))
                           for x in decoded]
        reconstructions[c_h] = (tied, decoded, decoded_indices)

    def summarize(c_h: int, c_f: int) -> dict[str, object]:
        tied, decoded, decoded_indices = reconstructions[c_h]
        classifier = classifiers[c_f]
        atomic = [classifier.label(x, f_star) for x in decoded]
        counts = {label: atomic.count(label) for label in ("A", "B", "C")}
        set_label = classifier.label_set(decoded, f_star)
        expected = "C" if counts["C"] else ("A" if counts["A"] == len(decoded) else "B")
        _require(set_label == expected and sum(counts.values()) == len(decoded),
                 "D016 decoded-set label is inconsistent")
        scale = lambda_ref + abs(minimum)
        tau = (float(c_h) * EPSILON) * scale
        _require(math.isfinite(scale) and math.isfinite(tau) and tau > 0.0,
                 "minimum tie tolerance is invalid")
        denominator = len(decoded)
        return {
            "c_H": c_h, "c_f": c_f, "H_E_min_hex": minimum.hex(),
            "H_E_min_domain_index": minimum_index,
            "tie_comparator": {"c_H": c_h, "epsilon_hex": EPSILON.hex(),
                               "minimum_tau_hex": tau.hex(), "lambda_ref_hex": lambda_ref.hex()},
            "T_E_size": len(tied), "X_E_size": denominator,
            "commitments": {
                "T_E_domain_index_stream_sha256": _stream_sha256(tied),
                "X_E_decoded_index_stream_sha256": _stream_sha256(decoded_indices),
                "T_E_first_index": tied[0], "T_E_last_index": tied[-1],
            },
            "set_label": set_label, "atomic_counts": counts,
            "atomic_label_set": sorted(set(atomic)),
            "I_C_exist": int(counts["C"] > 0), "I_C_univ": int(counts["C"] == denominator),
            "p_A": [counts["A"], denominator],
            "p_B": [counts["B"], denominator],
            "p_C": [counts["C"], denominator],
        }

    return {
        "primary_c_h_2048": summarize(*PRIMARY_PAIR),
        "d015_diagnostics": {f"c_H={c_h}__c_f={c_f}": summarize(c_h, c_f)
                             for c_h, c_f in DIAGNOSTIC_PAIRS},
    }


def reconstruct_pair(core_results: Mapping[str, Mapping[str, object]],
                     slack: SlackIndexMap, classifiers: Mapping[int, DecodedClassifier],
                     f_star: float, lambda_ref: float) -> dict[str, object]:
    """Combine both returned encoding streams into one in-memory record body.

    Accept the bounded fields of either ``core.scan`` or ``core.run_core``
    directly. Tie flags are asserted by that core, not recomputed here from
    energies; this function independently validates their shape and census.
    """
    _require(isinstance(core_results, Mapping) and set(core_results) == {"unbalanced", "slack"},
             "core result must contain exactly the two encodings")
    by_encoding: dict[str, dict[str, object]] = {}
    for encoding in ("unbalanced", "slack"):
        result = core_results[encoding]
        _require(isinstance(result, Mapping) and
                 {"minimum", "minimum_index", "compacted_entries"} <= set(result),
                 f"{encoding} core result lacks a required field")
        entries = result["compacted_entries"]
        _require(isinstance(entries, Sequence), f"{encoding} compacted entries are not a sequence")
        _require(all(type(word) is int and 0 <= word < (1 << 64) for word in entries),
                 f"{encoding} compacted entries contain a non-uint64 word")
        if "word_count" in result:
            expected = STATE_COUNT if encoding == "unbalanced" else slack.lift_total
            _require(type(result["word_count"]) is int and result["word_count"] == expected,
                     f"{encoding} core word count disagrees with the domain")
        if "compacted_count" in result:
            _require(type(result["compacted_count"]) is int and
                     result["compacted_count"] == len(entries),
                     f"{encoding} compacted count disagrees with its entries")
        if "per_ch" in result:
            counts = result["per_ch"]
            _require(isinstance(counts, Sequence) and len(counts) == len(CH_VALUES) and
                     all(type(count) is int for count in counts),
                     f"{encoding} D015 counters are malformed")
            observed = tuple(sum(bool((word >> 32) & (1 << bit)) for word in entries)
                             for bit in range(len(CH_VALUES)))
            _require(tuple(counts) == observed, f"{encoding} D015 counters disagree with entries")
        for name in ("illegal", "nesting"):
            if name in result:
                _require(type(result[name]) is int and result[name] == 0,
                         f"{encoding} core reported {name} flags")
        by_encoding[encoding] = reconstruct_stream(
            encoding, result["minimum"], result["minimum_index"],
            entries, slack, classifiers, f_star, lambda_ref,
        )
    return {
        "primary_c_h_2048": {encoding: by_encoding[encoding]["primary_c_h_2048"]
                              for encoding in ("unbalanced", "slack")},
        "d015_diagnostics": {
            key: {encoding: by_encoding[encoding]["d015_diagnostics"][key]
                  for encoding in ("unbalanced", "slack")}
            for key in (f"c_H={c_h}__c_f={c_f}" for c_h, c_f in DIAGNOSTIC_PAIRS)
        },
    }


def reconstruct_core_run(core_result: Mapping[str, object], slot: int,
                         slack: SlackIndexMap, classifiers: Mapping[int, DecodedClassifier],
                         f_star: float, lambda_ref: float) -> dict[str, object]:
    """Project one record directly from ``core.run_core``'s bounded result.

    The caller must supply offsets from the *same* prepared domain. Matching
    ``lift_total`` rejects size drift but cannot prove offset-table identity;
    the prepared in-memory runner keeps both objects together by construction.
    """
    _require(isinstance(core_result, Mapping) and
             set(core_result) == {"lift_total", "record_count", "summaries"},
             "core run has the wrong outer key set")
    _require(type(core_result["lift_total"]) is int and
             core_result["lift_total"] == slack.lift_total,
             "core lift total disagrees with the validated offsets")
    count = core_result["record_count"]
    _require(type(count) is int and count >= 1, "core record count is invalid")
    _index(slot, count, "core record slot")
    summaries = core_result["summaries"]
    _require(isinstance(summaries, Mapping), "core summaries are not a mapping")
    _require(len(summaries) == 2 * count, "core summary count disagrees with its record count")
    expected = {(record_slot, encoding) for record_slot in range(count)
                for encoding in ("unbalanced", "slack")}
    _require(set(summaries) == expected, "core summaries do not cover the two encodings per record")
    return reconstruct_pair({encoding: summaries[(slot, encoding)]
                             for encoding in ("unbalanced", "slack")},
                            slack, classifiers, f_star, lambda_ref)
