"""CUDA/T4 V-14 core batch producer: independent, order-agnostic, collision-safe batches.

Production-isolated core system built on, and separately pinned from, the
reviewed non-value engine (``cuda_v14_engine.py``).  The device program
(``cuda_v14_core_batch_engine.cu``) returns only each encoding's H_min bit
pattern with its canonical domain index and a deterministically COMPACTED
tie list (one word per tied state: flags in the high bits, canonical index
in the low bits, ascending canonical order; see the ordering proof in the
program header).  No energy word and no per-state flag array ever reaches
the host, a temporary file, or an artifact; the output is proportional to
the tie count only, hard-capped, and is consumed by a streaming reader one
coordinate at a time with bounded memory.  The host reconstructs T_E from
the compact list, decodes and first-seen deduplicates to X_E with
``src.g5.certify.decode_x_e``, classifies every decoded portfolio
with ``src.g4.classification.DecodedClassifier`` (Lambda_ref and f* from the
pinned Gate-3 ground truth), and emits per-coordinate D015/D016 summaries:

* primary ``(c_H, c_f) = (2048, 2048)`` and the four D015 diagnostics
  ``(1024,2048)``, ``(4096,2048)``, ``(2048,1024)``, ``(2048,4096)``; ``c_f``
  only re-labels the same X_E (one energy scan per coordinate per encoding);
* exact binary64 ``H_E_min_hex``, tie comparator metadata, ``T_E_size``,
  ``X_E_size``, D016 set label, atomic A/B/C counts, atomic-label set,
  ``I_C_exist``/``I_C_univ`` (0/1), exact rational ``p_A``/``p_B``/``p_C`` as
  ``[numerator, denominator]``;
* SHA-256 commitments to the raw tied-domain-index stream (canonical order)
  and the first-seen deduplicated decoded-index stream instead of raw lists.

Modes: ``--plan`` (no nvcc/GPU/writes), ``--validate`` (non-value: counters
only), ``--measure`` (non-value: timing only; scientific records discarded),
and the future ``--run-batch`` (one ``[start, stop)`` range to an explicit
output directory outside the repository; atomic, collision-refusing).  Nothing
here aggregates, rates, compares, infers, triggers D013, or concludes.

Importing this module has no side effects and writes nothing.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g6.cuda_qualification import cuda_energy_crosscheck as cuda_unbalanced  # noqa: E402
from research.g6.cuda_qualification import cuda_v14_engine as engine  # noqa: E402
from src.g4.classification import DecodedClassifier, OriginalObjectiveService  # noqa: E402
from src.g4.energy import EPSILON, objective  # noqa: E402
from src.g5.certify import decode_x_e  # noqa: E402
from src.g5.domains import BinaryDomain, SlackDomainCache  # noqa: E402


SCHEMA_PLAN = "decisions_os/g6_cuda_t4_v14_core_plan/v1"
SCHEMA_VALIDATE = "decisions_os/g6_cuda_t4_v14_core_validation_run/v1"
SCHEMA_MEASURE = "decisions_os/g6_cuda_t4_v14_core_measure_run/v1"
SCHEMA_MEASUREMENT = "decisions_os/g6_v14_cuda_t4_core_throughput_measurement/v1"
SCHEMA_RECORDS = "decisions_os/g6_v14_cuda_t4_core_batch_records/v1"
SCHEMA_MANIFEST = "decisions_os/g6_v14_cuda_t4_core_batch_manifest/v1"
SCHEMA_RELEASE = "decisions_os/g6_v14_cuda_t4_core_batch_release/v1"
SCHEMA_BATCH_RUN = "decisions_os/g6_cuda_t4_v14_core_batch_run/v1"
PURPOSE = ("CUDA/T4 V-14 core batch producer: per-coordinate D015/D016 certification records with digest "
           "commitments; no aggregation, rate, transition, comparison, inference, D013, or conclusion")
TRACK = "cuda-t4"
PROBE = "v14_core_batch_engine_cuda"
BACKEND = cuda_unbalanced.BACKEND
COMPILE_FLAGS = engine.COMPILE_FLAGS
CH_VALUES = engine.CH_VALUES
CF_VALUES = (1024, 2048, 4096)
PRIMARY_PAIR = (2048, 2048)
DIAGNOSTIC_PAIRS = ((1024, 2048), (4096, 2048), (2048, 1024), (2048, 4096))
DECODED_COUNT = engine.DECODED_COUNT
MAX_COORDINATES_PER_INVOCATION = engine.MAX_COORDINATES_PER_INVOCATION
OUTPUT_MAGIC = int.from_bytes(b"G6V14CY1", "little")
FORMAT_VERSION = 1
ENTRY_FLAG_SHIFT = 32
ENTRY_INDEX_MASK = (1 << 32) - 1
LEGAL_FLAGS = (4, 6, 7)  # D015 nesting: tied at 4096 only, at 2048+4096, or at every c_H
MAX_TIED_ENTRIES_PER_RUN = 1 << 28
MODE_VALIDATE, MODE_PRODUCE = 0, 1
COMMITMENT_DESCRIPTORS = {
    "stream_encoding": "little-endian uint64 per index, concatenated, SHA-256",
    "T_E_order": ("canonical enumeration order: unbalanced = BinaryDomain index d in [0, 2^20) with x[i] = (d >> (19 - i)) & 1; "
                  "slack = SlackDomainCache entry e in cached order (decoded index major, lift order)"),
    "X_E_order": "first-seen deduplication of decode(T_E) in T_E order (src.g5.certify.decode_x_e); decoded index = BinaryDomain index of x",
    "decode": {"unbalanced": "decode(z) = z", "slack": "decode((x, y)) = x"},
    "compaction": "device chunked stable compaction (4096 contiguous chunks, host exclusive prefix offsets); ascending index order",
}
T_E_ORDER = ("canonical enumeration order: unbalanced = BinaryDomain index d in [0, 2^20) with x[i] = (d >> (19 - i)) & 1; "
             "slack = SlackDomainCache entry e in cached order (decoded index major, lift order)")
X_E_ORDER = "first-seen deduplication of decode(T_E) in T_E order (src.g5.certify.decode_x_e); decoded index = BinaryDomain index of x"
DECODE_RULE = COMMITMENT_DESCRIPTORS["decode"]
SUMMARY_KEYS = frozenset({"c_H", "c_f", "H_E_min_hex", "H_E_min_domain_index", "tie_comparator", "T_E_size", "X_E_size", "commitments",
                          "set_label", "atomic_counts", "atomic_label_set", "I_C_exist", "I_C_univ", "p_A", "p_B", "p_C"})
COMMITMENT_KEYS = frozenset({"T_E_domain_index_stream_sha256", "X_E_decoded_index_stream_sha256", "T_E_first_index", "T_E_last_index"})
TIE_COMPARATOR_KEYS = frozenset({"c_H", "epsilon_hex", "minimum_tau_hex", "lambda_ref_hex"})
RECORD_KEYS = frozenset({"key", "linear", "scale", "pass_id", "coefficients_hex", "commitment_descriptors", "primary_c_h_2048", "d015_diagnostics"})
KEY_KEYS = frozenset({"ell_card", "ell_sector", "ell_budget", "s_card_hex", "s_sector_hex", "s_budget_hex"})
COEFFICIENT_KEYS = frozenset({"alpha", "sector_slack", "budget_slack", "sector_linear", "sector_quadratic", "budget_linear", "budget_quadratic"})

GROUND_TRUTH_REL = "research/ground_truth/G3_GROUND_TRUTH.json"
ADNYE_001_REL = "research/adnye/ADNYE-001_Lambda_ref.json"
DECISIONS_REL = "research/decisions/DECISIONS.md"
OWNER_DECISIONS_REL = "research/decisions/GATE_6_OWNER_EXECUTION_DECISIONS.md"
CUDA_SOURCE_REL = "research/g6/cuda_qualification/cuda_v14_core_batch_engine.cu"
ENGINE_LIBRARY_REL = "research/g6/cuda_qualification/cuda_v14_engine.py"
PINNED_INPUTS: dict[str, str] = {
    **engine.PINNED_INPUTS,
    "src/g4/classification.py": "9a35f0829de8216ff47e6b1dd257e5dbc5a0dd96c9a051dd058bfe54bd672da1",
    GROUND_TRUTH_REL: "13229ad17e0a109731c0682c1ce22a820ea3ca412364fd882a897d036fc475db",
    ADNYE_001_REL: "9473c205a002697492c75af9ab694920b6bf822b38b5bd5c58f8f240ca66116a",
    DECISIONS_REL: "274c6cd92d4958957d125efc7ae2ddb6f40629eb78b7c2e2be99224e038ce849",
    OWNER_DECISIONS_REL: "0d7d212dd1205a8c1c84d702f0f8b44a444b952d84c29a6a352d9a17b716e4fe",
    ENGINE_LIBRARY_REL: "b032cea961d5e91a7cbc8bc09c1f6ae3f76d9b46267a3f112ec137d26529c518",
    CUDA_SOURCE_REL: "ac9cb5cb59320b9d9d1131f60fd4b954ec05ddc843dd94b6cf8ceab785d9e0c5",
}
SELF_RELATIVES = ("research/g6/cuda_qualification/cuda_v14_core_batch.py",
                  "research/g6/cuda_qualification/v14_core_batch_contract.py",
                  "research/g6/run_cuda_v14_core_batches.py",
                  "research/g6/plan_v14_cuda_core_batches.py")
COMPILE_TIMEOUT_SECONDS = engine.COMPILE_TIMEOUT_SECONDS
EXECUTE_TIMEOUT_SECONDS = engine.EXECUTE_TIMEOUT_SECONDS


class CoreError(RuntimeError):
    """Raised when the core batch contract cannot be established."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CoreError(message)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def content_sha256(payload: Mapping[str, Any]) -> str:
    return _sha256_bytes(canonical_bytes({key: value for key, value in payload.items() if key != "content_sha256"}))


def _shared(function: Callable, *arguments):
    try:
        return function(*arguments)
    except (engine.EngineError, cuda_unbalanced.CrosscheckError) as exc:
        raise CoreError(str(exc)) from exc


def current_hashes(relatives: Sequence[str]) -> dict[str, str]:
    return _shared(engine.current_hashes, tuple(relatives))


def verify_pinned_inputs(expected: Mapping[str, str] | None = None) -> dict[str, str]:
    pins = dict(PINNED_INPUTS if expected is None else expected)
    observed = current_hashes(tuple(pins))
    drifted = sorted(relative for relative in pins if observed[relative] != pins[relative])
    _require(not drifted, "pinned input drift: " + ", ".join(drifted))
    return observed


def _read_json(path: Path, label: str) -> dict[str, Any]:
    return _shared(engine._read_json, path, label)


# --------------------------------------------------------------------------
# Classifier inputs and canonical services
# --------------------------------------------------------------------------

def classifier_inputs(ledgers: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Lambda_ref and f* from the pinned Gate-3 ground truth; ledger Lambda_ref must agree."""
    ground_truth = _read_json(ROOT / GROUND_TRUTH_REL, "Gate-3 ground truth")
    try:
        lambda_ref = float(ground_truth["results"]["Lambda_ref"])
        f_star = float(ground_truth["results"]["f_star"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CoreError("Gate-3 ground truth classifier inputs are invalid") from exc
    _require(math.isfinite(lambda_ref) and lambda_ref > 0.0 and math.isfinite(f_star), "Gate-3 classifier inputs are nonfinite")
    _require(lambda_ref == _shared(engine.lambda_ref_from, ledgers), "V-14 ledgers and Gate-3 Lambda_ref disagree")
    pins = current_hashes((GROUND_TRUTH_REL, ADNYE_001_REL, DECISIONS_REL))
    return {"lambda_ref": lambda_ref, "f_star": f_star, "lambda_ref_hex": lambda_ref.hex(), "f_star_hex": f_star.hex(),
            "ground_truth_sha256": pins[GROUND_TRUTH_REL], "adnye_001_sha256": pins[ADNYE_001_REL],
            "d015_d016_decision_record_sha256": pins[DECISIONS_REL]}


def hard_feasible(instance, x: tuple[int, ...]) -> bool:
    """Original feasibility predicate, transcribed from src/g6/d011_runner.py::_hard_feasible."""
    if sum(x) != instance.K:
        return False
    for members in instance.sectors:
        if sum(x[index] for index in members) > instance.C:
            return False
    spend = +0.0
    for index, bit in enumerate(x):
        spend = spend + instance.prices[index] * float(bit)
    return spend <= instance.B


def build_classifiers(instance, lambda_ref: float) -> dict[int, DecodedClassifier]:
    """One encoding-blind D016 classifier per D015 c_f; f* is supplied at call time."""
    return {c_f: DecodedClassifier(OriginalObjectiveService(lambda x, base=instance: objective(base, x), lambda_ref, float(c_f)),
                                   lambda x, base=instance: hard_feasible(base, x))
            for c_f in CF_VALUES}


# --------------------------------------------------------------------------
# Device output
# --------------------------------------------------------------------------

def _read_exact(stream, size: int, label: str) -> bytes:
    data = stream.read(size)
    _require(len(data) == size, f"core output truncated at {label}")
    return data


def read_header(stream, coordinate_count: int, slack_count: int, mode: int) -> int:
    header = struct.unpack("<7Q", _read_exact(stream, 56, "header"))
    _require(header[0] == OUTPUT_MAGIC and header[1] == FORMAT_VERSION, "core output header mismatch")
    _require(header[2] == mode and header[3] == coordinate_count and header[4] == DECODED_COUNT and header[5] == slack_count,
             "core output counts mismatch")
    return header[6]


def _read_entries(stream, count: int, domain: int, h_min_index: int, label: str) -> list[tuple[int, int]]:
    """One encoding's compact tie list: strictly ascending indices, legal nested flags, minimum tied at every c_H."""
    _require(1 <= count <= domain, f"{label}: tied count outside [1, domain]")
    words = struct.unpack(f"<{count}Q", _read_exact(stream, 8 * count, f"{label} entries"))
    entries = []
    previous = -1
    min_seen = False
    for word in words:
        index = word & ENTRY_INDEX_MASK
        flag = word >> ENTRY_FLAG_SHIFT
        _require(index > previous and index < domain, f"{label}: compaction order or domain violated")
        _require(flag in LEGAL_FLAGS, f"{label}: D015 nesting violated in a compact entry")
        if index == h_min_index:
            min_seen = flag == 7
        entries.append((index, flag))
        previous = index
    _require(min_seen, f"{label}: minimum state is not tied at every c_H")
    return entries


def iter_output(path: Path, coordinate_count: int, slack_count: int, mode: int):
    """Stream the core program's output one coordinate at a time (bounded memory: one coordinate's tie lists).

    Yields ``(device_index, coordinate)`` where coordinate = {encoding: {h_min_bits, h_min_index, entries}}.
    Never reads the whole file into memory; requires exact EOF after the last coordinate.
    """
    with open(path, "rb") as stream:
        device_index = read_header(stream, coordinate_count, slack_count, mode)
        total_entries = 0
        for _ in range(coordinate_count):
            record = struct.unpack("<6Q", _read_exact(stream, 48, "coordinate record"))
            _require(record[1] < DECODED_COUNT and record[3] < slack_count, "core output minimum index outside its domain")
            total_entries += record[4] + record[5]
            _require(total_entries <= MAX_TIED_ENTRIES_PER_RUN, "tied-entry output cap exceeded")
            unbalanced = _read_entries(stream, record[4], DECODED_COUNT, record[1], "unbalanced")
            slack = _read_entries(stream, record[5], slack_count, record[3], "slack")
            yield device_index, {"unbalanced": {"h_min_bits": record[0], "h_min_index": record[1], "entries": unbalanced},
                                 "slack": {"h_min_bits": record[2], "h_min_index": record[3], "entries": slack}}
        _require(stream.read(1) == b"", "core output carries data after the last coordinate")


def compact_from_flags(flags: bytes) -> list[tuple[int, int]]:
    """The canonical compact list of a full flag array (reference only; never used on device output)."""
    return [(index, flag) for index, flag in enumerate(flags) if flag]


def compare_compact(device: Mapping[str, Any], reference: tuple[int, int, bytes]) -> dict[str, int]:
    """Counters only: minimum bits/index and the compact tie list versus a canonical (bits, index, flags) reduction."""
    bits, index, flags = reference
    expected = compact_from_flags(flags)
    observed = list(device["entries"])
    mismatches = 0
    i = j = 0
    while i < len(expected) or j < len(observed):
        if i < len(expected) and j < len(observed) and expected[i][0] == observed[j][0]:
            mismatches += int(expected[i][1] != observed[j][1])
            i += 1
            j += 1
        elif j >= len(observed) or (i < len(expected) and expected[i][0] < observed[j][0]):
            mismatches += 1
            i += 1
        else:
            mismatches += 1
            j += 1
    return {"h_min_bits_mismatch": int(device["h_min_bits"] != bits), "h_min_index_mismatch": int(device["h_min_index"] != index),
            "tie_entry_mismatches": mismatches}


# --------------------------------------------------------------------------
# Reconstruction, classification, commitments
# --------------------------------------------------------------------------

def decoded_index(x: tuple[int, ...]) -> int:
    """BinaryDomain index of a decoded state (x[i] is bit 19 - i)."""
    _require(len(x) == 20 and all(bit in (0, 1) for bit in x), "decoded state is not a 20-bit tuple")
    value = 0
    for bit in x:
        value = (value << 1) | bit
    return value


def _stream_digest(indices: Sequence[int]) -> str:
    return _sha256_bytes(b"".join(struct.pack("<Q", index) for index in indices))


def reconstruct(encoding: str, entries: Sequence[tuple[int, int]], c_h: int, cache: SlackDomainCache) -> dict[str, Any]:
    """T_E (tied domain indices, canonical order) and X_E (first-seen decoded states) for one c_H.

    ``entries`` is the compact list (index, flags) in ascending canonical order; only tied states are
    visited, so no per-state rescan happens.
    """
    _require(encoding in ("unbalanced", "slack") and c_h in CH_VALUES, "unknown encoding or c_H")
    bit = 1 << CH_VALUES.index(c_h)
    tied = [index for index, flag in entries if flag & bit]
    _require(tied, "empty tie set: the minimum state must always be tied")
    domain = BinaryDomain(engine.DECODED_WIDTH)
    if encoding == "unbalanced":
        raw_states = [domain[index] for index in tied]
        decoded = decode_x_e(raw_states, lambda z: z)
    else:
        raw_states = [cache[index] for index in tied]
        decoded = decode_x_e(raw_states, lambda z: z[0])
    return {"tied_indices": tied, "decoded_states": decoded,
            "decoded_indices": [decoded_index(x) for x in decoded]}


def summarize(encoding: str, device: Mapping[str, Any], reconstruction: Mapping[str, Any], c_h: int, c_f: int,
              classifier: DecodedClassifier, f_star: float, lambda_ref: float) -> dict[str, Any]:
    """One D015/D016 summary for (c_H, c_f): integers, hex strings, and [numerator, denominator] pairs only."""
    tied = reconstruction["tied_indices"]
    decoded = reconstruction["decoded_states"]
    h_min = engine.bits_float(device["h_min_bits"])
    _require(math.isfinite(h_min), "nonfinite H_min")
    _require(device["h_min_index"] in tied, "H_min state is not in its own tie set")
    atomic = [classifier.label(x, f_star) for x in decoded]
    set_label = classifier.label_set(decoded, f_star)
    counts = {label: sum(1 for item in atomic if item == label) for label in ("A", "B", "C")}
    expected = "C" if counts["C"] > 0 else ("A" if counts["A"] == len(decoded) else "B")
    _require(set_label == expected, "D016 label reconstruction drift")
    minimum_tau = float((float(c_h) * EPSILON) * float(lambda_ref + abs(h_min)))
    denominator = len(decoded)
    return {
        "c_H": c_h, "c_f": c_f,
        "H_E_min_hex": h_min.hex(),
        "H_E_min_domain_index": device["h_min_index"],
        "tie_comparator": {"c_H": c_h, "epsilon_hex": EPSILON.hex(), "minimum_tau_hex": minimum_tau.hex(),
                           "lambda_ref_hex": lambda_ref.hex()},
        "T_E_size": len(tied),
        "X_E_size": denominator,
        "commitments": {
            "T_E_domain_index_stream_sha256": _stream_digest(tied),
            "X_E_decoded_index_stream_sha256": _stream_digest(reconstruction["decoded_indices"]),
            "T_E_first_index": tied[0], "T_E_last_index": tied[-1],
        },
        "set_label": set_label,
        "atomic_counts": counts,
        "atomic_label_set": sorted(set(atomic)),
        "I_C_exist": 1 if counts["C"] > 0 else 0,
        "I_C_univ": 1 if counts["C"] == denominator else 0,
        "p_A": [counts["A"], denominator], "p_B": [counts["B"], denominator], "p_C": [counts["C"], denominator],
    }


def coordinate_record(point: Mapping[str, Any], ledger: Mapping[str, Any], device: Mapping[str, Any],
                      cache: SlackDomainCache, classifiers: Mapping[int, DecodedClassifier], f_star: float,
                      lambda_ref: float) -> dict[str, Any]:
    """The complete D015/D016 record for one coordinate, both encodings; energies never enter."""
    card, sector, budget = point["coordinate"]["card"], point["coordinate"]["sector"], point["coordinate"]["budget"]
    key = {"ell_card": card, "ell_sector": sector, "ell_budget": budget,
           "s_card_hex": ledger["coordinates"][card]["binary64_hex"],
           "s_sector_hex": ledger["coordinates"][sector]["binary64_hex"],
           "s_budget_hex": ledger["coordinates"][budget]["binary64_hex"]}
    primary: dict[str, Any] = {}
    diagnostics: dict[str, dict[str, Any]] = {f"c_H={c_h}__c_f={c_f}": {} for c_h, c_f in DIAGNOSTIC_PAIRS}
    for encoding in ("unbalanced", "slack"):
        reconstructions = {c_h: reconstruct(encoding, device[encoding]["entries"], c_h, cache) for c_h in CH_VALUES}
        for c_h in CH_VALUES:  # D015 nesting: T_E(1024) <= T_E(2048) <= T_E(4096)
            if c_h != CH_VALUES[-1]:
                nxt = CH_VALUES[CH_VALUES.index(c_h) + 1]
                _require(set(reconstructions[c_h]["tied_indices"]) <= set(reconstructions[nxt]["tied_indices"]),
                         "D015 tie-set nesting drift")
        for c_h, c_f in (PRIMARY_PAIR,) + DIAGNOSTIC_PAIRS:
            summary = summarize(encoding, device[encoding], reconstructions[c_h], c_h, c_f, classifiers[c_f], f_star, lambda_ref)
            if (c_h, c_f) == PRIMARY_PAIR:
                primary[encoding] = summary
            else:
                diagnostics[f"c_H={c_h}__c_f={c_f}"][encoding] = summary
    record = {"key": key, "linear": point["linear"], "scale": point["scale"], "pass_id": point["pass_id"],
              "coefficients_hex": {name: value.hex() for name, value in asdict(point["coefficients"]).items()},
              "commitment_descriptors": dict(COMMITMENT_DESCRIPTORS),
              "primary_c_h_2048": primary, "d015_diagnostics": diagnostics}
    require_no_float_or_bool(record, "record")
    return record


def require_no_float_or_bool(value: object, label: str) -> None:
    if isinstance(value, bool) or isinstance(value, float):
        raise CoreError(f"{label} contains a float or boolean")
    if isinstance(value, dict):
        for key, item in value.items():
            require_no_float_or_bool(item, f"{label}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            require_no_float_or_bool(item, f"{label}[{index}]")


def _legal_hex_float(value: object, label: str, finite: bool = True) -> float:
    _require(isinstance(value, str), f"{label}: not a hex string")
    try:
        parsed = float.fromhex(value)
    except ValueError as exc:
        raise CoreError(f"{label}: not a binary64 hex literal") from exc
    _require(parsed.hex() == value, f"{label}: hex literal is not canonical")
    _require(not finite or math.isfinite(parsed), f"{label}: nonfinite")
    return parsed


def _is_int(value: object) -> bool:
    return type(value) is int


def validate_record(record: Mapping[str, Any], linear: int, scale: str, ledger: Mapping[str, Any], lambda_ref_hex: str,
                    slack_count: int) -> None:
    """Strict semantic validation of one emitted coordinate record (exact keys, bindings, D015/D016 identities)."""
    label = f"record linear={linear}"
    _require(isinstance(record, dict) and set(record) == RECORD_KEYS, f"{label}: top-level key set")
    require_no_float_or_bool(record, label)
    axis_count = engine.SCALES[scale]["axis_count"]
    key = record["key"]
    _require(isinstance(key, dict) and set(key) == KEY_KEYS and all(_is_int(key[k]) for k in ("ell_card", "ell_sector", "ell_budget")),
             f"{label}: key shape")
    card, sector, budget = key["ell_card"], key["ell_sector"], key["ell_budget"]
    _require(_shared(engine.linear_index, card, sector, budget, axis_count) == linear == record["linear"], f"{label}: linear/key binding")
    _require(record["scale"] == scale and record["pass_id"] == engine.SCALES[scale]["pass_id"], f"{label}: scale/pass binding")
    for axis, index in (("card", card), ("sector", sector), ("budget", budget)):
        _require(key[f"s_{axis}_hex"] == ledger["coordinates"][index]["binary64_hex"], f"{label}: s_{axis}_hex differs from the ledger")
    expected_coefficients = {name: value.hex() for name, value in asdict(_shared(engine.coefficients_at, ledger, card, sector, budget)).items()}
    _require(record["coefficients_hex"] == expected_coefficients and set(record["coefficients_hex"]) == COEFFICIENT_KEYS,
             f"{label}: coefficients differ from the ledger")
    _require(record["commitment_descriptors"] == COMMITMENT_DESCRIPTORS, f"{label}: commitment descriptors")
    primary, diagnostics = record["primary_c_h_2048"], record["d015_diagnostics"]
    _require(isinstance(primary, dict) and set(primary) == {"unbalanced", "slack"} and isinstance(diagnostics, dict)
             and set(diagnostics) == {f"c_H={c_h}__c_f={c_f}" for c_h, c_f in DIAGNOSTIC_PAIRS}
             and all(isinstance(v, dict) and set(v) == {"unbalanced", "slack"} for v in diagnostics.values()), f"{label}: D015 condition set")
    for encoding in ("unbalanced", "slack"):
        domain = DECODED_COUNT if encoding == "unbalanced" else slack_count
        summaries = {PRIMARY_PAIR: primary[encoding]}
        for c_h, c_f in DIAGNOSTIC_PAIRS:
            summaries[(c_h, c_f)] = diagnostics[f"c_H={c_h}__c_f={c_f}"][encoding]
        for (c_h, c_f), summary in summaries.items():
            tag = f"{label} {encoding} c_H={c_h} c_f={c_f}"
            _require(isinstance(summary, dict) and set(summary) == SUMMARY_KEYS, f"{tag}: summary key set")
            _require(summary["c_H"] == c_h and summary["c_f"] == c_f, f"{tag}: c_H/c_f binding")
            h_min = _legal_hex_float(summary["H_E_min_hex"], f"{tag}: H_E_min_hex")
            _require(_is_int(summary["H_E_min_domain_index"]) and 0 <= summary["H_E_min_domain_index"] < domain, f"{tag}: minimum index")
            comparator = summary["tie_comparator"]
            _require(isinstance(comparator, dict) and set(comparator) == TIE_COMPARATOR_KEYS and comparator["c_H"] == c_h
                     and comparator["epsilon_hex"] == EPSILON.hex() and comparator["lambda_ref_hex"] == lambda_ref_hex, f"{tag}: tie comparator")
            lambda_ref = _legal_hex_float(lambda_ref_hex, f"{tag}: lambda_ref_hex")
            _require(comparator["minimum_tau_hex"] == float((float(c_h) * EPSILON) * float(lambda_ref + abs(h_min))).hex(),
                     f"{tag}: minimum_tau_hex does not reproduce")
            t_size, x_size = summary["T_E_size"], summary["X_E_size"]
            _require(_is_int(t_size) and _is_int(x_size) and 1 <= x_size <= t_size <= domain, f"{tag}: T_E/X_E sizes")
            _require(encoding == "slack" or x_size == t_size, f"{tag}: unbalanced decode is the identity, so X_E_size must equal T_E_size")
            commitments = summary["commitments"]
            _require(isinstance(commitments, dict) and set(commitments) == COMMITMENT_KEYS
                     and all(isinstance(commitments[k], str) and re.fullmatch(r"[0-9a-f]{64}", commitments[k]) is not None
                             for k in ("T_E_domain_index_stream_sha256", "X_E_decoded_index_stream_sha256"))
                     and _is_int(commitments["T_E_first_index"]) and _is_int(commitments["T_E_last_index"])
                     and 0 <= commitments["T_E_first_index"] <= summary["H_E_min_domain_index"] <= commitments["T_E_last_index"] < domain
                     and (t_size > 1 or commitments["T_E_first_index"] == commitments["T_E_last_index"])
                     and (t_size == 1 or commitments["T_E_first_index"] < commitments["T_E_last_index"]), f"{tag}: commitments")
            if t_size == 1:
                _require(commitments["T_E_domain_index_stream_sha256"] == _stream_digest([commitments["T_E_first_index"]]), f"{tag}: singleton commitment")
            counts = summary["atomic_counts"]
            _require(isinstance(counts, dict) and set(counts) == {"A", "B", "C"} and all(_is_int(v) and v >= 0 for v in counts.values())
                     and counts["A"] + counts["B"] + counts["C"] == x_size, f"{tag}: atomic counts")
            _require(summary["atomic_label_set"] == sorted(l for l in "ABC" if counts[l] > 0), f"{tag}: atomic label set")
            expected_label = "C" if counts["C"] > 0 else ("A" if counts["A"] == x_size else "B")
            _require(summary["set_label"] == expected_label, f"{tag}: D016 set label")
            _require(summary["I_C_exist"] == int(counts["C"] > 0) and summary["I_C_univ"] == int(counts["C"] == x_size)
                     and summary["I_C_exist"] in (0, 1) and summary["I_C_univ"] in (0, 1), f"{tag}: I_C indicators")
            for l in "ABC":
                _require(summary[f"p_{l}"] == [counts[l], x_size], f"{tag}: p_{l}")
        # c_f changes only classification; the scan-level fields must be identical across c_f for a given c_H.
        for c_h in CH_VALUES:
            group = [s for (h, _), s in summaries.items() if h == c_h]
            for field in ("H_E_min_hex", "H_E_min_domain_index", "T_E_size", "X_E_size", "commitments", "tie_comparator"):
                _require(all(s[field] == group[0][field] for s in group), f"{label} {encoding} c_H={c_h}: {field} varies with c_f")
        # The minimum is c_H-independent; T_E nests with c_H.
        by_ch = {c_h: next(s for (h, _), s in summaries.items() if h == c_h) for c_h in CH_VALUES}
        _require(len({s["H_E_min_hex"] for s in by_ch.values()}) == 1 and len({s["H_E_min_domain_index"] for s in by_ch.values()}) == 1,
                 f"{label} {encoding}: minimum varies with c_H")
        _require(by_ch[1024]["T_E_size"] <= by_ch[2048]["T_E_size"] <= by_ch[4096]["T_E_size"]
                 and by_ch[1024]["X_E_size"] <= by_ch[2048]["X_E_size"] <= by_ch[4096]["X_E_size"], f"{label} {encoding}: D015 nesting")


# --------------------------------------------------------------------------
# Binding, identity, execution
# --------------------------------------------------------------------------

def _bind(records: tuple[Mapping[str, Any], Mapping[str, Any]] | None):
    pins = verify_pinned_inputs()
    ledgers = _shared(engine.load_ledgers)
    inputs = classifier_inputs(ledgers)
    instance = engine.load_instance(ROOT / engine.INSTANCE_REL)
    cache = _shared(engine.build_slack_domain, instance)
    prerequisites = None if records is None else _shared(engine.validate_prerequisite_records, *records)
    return pins, ledgers, inputs, instance, cache, prerequisites


def core_identity(report: Mapping[str, Any], nvcc_info: Mapping[str, Any], command: list[str], pins: Mapping[str, str],
                  domain: Mapping[str, Any], prerequisites: Mapping[str, Any], inputs: Mapping[str, Any]) -> dict[str, Any]:
    identity = _shared(engine.engine_identity, report, nvcc_info, command, pins, domain, prerequisites)
    identity.update({
        "probe": PROBE, "role": "core-batch-producer",
        "core_source_sha256": pins[CUDA_SOURCE_REL], "cuda_source_sha256": pins[CUDA_SOURCE_REL],
        "engine_source_sha256": pins[engine.CUDA_SOURCE_REL], "engine_library_sha256": pins[ENGINE_LIBRARY_REL],
        "classifier": {"lambda_ref_hex": inputs["lambda_ref_hex"], "f_star_hex": inputs["f_star_hex"],
                       "ground_truth_sha256": inputs["ground_truth_sha256"], "adnye_001_sha256": inputs["adnye_001_sha256"],
                       "d015_d016_decision_record_sha256": inputs["d015_d016_decision_record_sha256"]},
        "d015_pairs": [list(PRIMARY_PAIR)] + [list(pair) for pair in DIAGNOSTIC_PAIRS],
        "record_schema": SCHEMA_RECORDS,
    })
    return identity


def identity_sha256(identity: Mapping[str, Any]) -> str:
    return _sha256_bytes(canonical_bytes(identity))


def _require_nvcc(locate: Callable[[], str | None]) -> str:
    """Fail closed before any binding or CPU reference work when no nvcc is available."""
    nvcc = locate()
    _require(nvcc is not None, "nvcc is unavailable; the CUDA V-14 core engine cannot run on this host")
    return nvcc


def _execute(points, mode: int, instance, lambda_ref: float, cache: SlackDomainCache, locate: Callable[[], str | None],
             consumer: Callable[[Any], Any]):
    """Compile and run the core program in an auto-removed temporary directory.

    ``consumer(coordinates)`` receives the streaming iterator over per-coordinate compact results and runs
    inside the temporary directory's lifetime; only what it returns survives.  Returns
    (report, consumer_result, nvcc_info, command, smi).
    """
    nvcc = _require_nvcc(locate)
    source = ROOT / CUDA_SOURCE_REL
    encoded = _shared(engine.encode_inputs, instance, lambda_ref, points, cache, mode)
    temporary_path: Path | None = None
    with tempfile.TemporaryDirectory(prefix="g6-cuda-t4-v14-core-") as temporary:
        temporary_path = Path(temporary)
        nvcc_info = _shared(cuda_unbalanced.nvcc_version, nvcc, temporary_path)
        smi = _shared(cuda_unbalanced.nvidia_smi_identity, temporary_path)
        staged = temporary_path / "cuda_v14_core_batch_engine.cu"
        binary = temporary_path / "core"
        input_path = temporary_path / "input.words"
        output_path = temporary_path / "output.words"
        staged.write_bytes(source.read_bytes())
        _require(_sha256_bytes(staged.read_bytes()) == PINNED_INPUTS[CUDA_SOURCE_REL], "staged core source drift")
        input_path.write_bytes(encoded)
        command = _shared(cuda_unbalanced.compile_command, nvcc, staged, binary)
        compilation = _shared(cuda_unbalanced._run_subprocess, command, temporary_path, COMPILE_TIMEOUT_SECONDS, "nvcc compilation")
        _require(compilation.returncode == 0, "nvcc compilation failed; do not substitute relaxed flags: " + compilation.stderr[-2000:])
        execution = _shared(cuda_unbalanced._run_subprocess, [str(binary), str(input_path), str(output_path)], temporary_path,
                            EXECUTE_TIMEOUT_SECONDS, "core execution")
        _require(execution.returncode == 0, "core binary failed: " + execution.stderr[-2000:])
        try:
            report = json.loads(execution.stdout)
        except json.JSONDecodeError as exc:
            raise CoreError("core engine emitted malformed JSON") from exc
        validate_device_report(report, len(points), len(cache), mode)
        device_indices: set[int] = set()

        def coordinates():
            for device_index, coordinate in iter_output(output_path, len(points), len(cache), mode):
                device_indices.add(device_index)
                yield coordinate

        result = consumer(coordinates())
        _require(device_indices == {report.get("device_index")}, "device index disagreement")
    _require(temporary_path is not None and not temporary_path.exists(), "temporary directory was not removed")
    return report, result, nvcc_info, command, smi


def validate_device_report(report: object, coordinate_count: int, slack_count: int, mode: int) -> dict[str, Any]:
    per_coordinate = DECODED_COUNT + slack_count
    validated = _shared(cuda_unbalanced.validate_device_report, report, coordinate_count, per_coordinate)
    _require(validated.get("probe") == PROBE, "device report is not from the core batch program")
    _require(validated.get("mode") == ("validate" if mode == MODE_VALIDATE else "produce"), "core mode mismatch")
    _require(validated.get("decoded_state_count") == DECODED_COUNT and validated.get("slack_state_count") == slack_count
             and validated.get("coordinate_count") == coordinate_count, "core domain counts mismatch")
    for key in ("nonfinite_energies", "tie_nesting_violations", "device_vs_host_cxx_mismatches"):
        _require(type(validated.get(key)) is int and validated[key] == 0, f"core engine reported a nonzero {key}")
    _require(validated.get("host_reference_evaluated") is (mode == MODE_VALIDATE), "host-reference flag mismatch")
    for key in ("elapsed_ns_prepare", "elapsed_ns_coordinates"):
        _require(isinstance(validated.get(key), int) and validated[key] >= 0, f"{key} missing")
    _require(_is_int(validated.get("tied_entries_written")) and 0 <= validated["tied_entries_written"] <= MAX_TIED_ENTRIES_PER_RUN,
             "tied-entry count missing or above the cap")
    return validated


def _common(report, nvcc_info, command, smi, pins, platform_before, cache, prerequisites, inputs) -> dict[str, Any]:
    identity = core_identity(report, nvcc_info, command, pins, engine.domain_identity(cache), prerequisites, inputs)
    _require({key: identity[key] for key in prerequisites["platform"]} == prerequisites["platform"],
             "observed platform/toolchain differs from the prerequisite qualifications; requalify")
    return {"purpose": PURPOSE, "track": TRACK, "platform": platform_before, "pinned_inputs": pins,
            "self_sha256": current_hashes(SELF_RELATIVES), "domain": engine.domain_identity(cache),
            "prerequisites": prerequisites, "compile_command": command, "nvcc": nvcc_info, "nvidia_smi": smi,
            "device": cuda_unbalanced.device_fingerprint(report), "device_reported": report,
            "core_validation_identity": identity, "core_validation_identity_sha256": identity_sha256(identity),
            "elapsed_ns_prepare": report["elapsed_ns_prepare"], "elapsed_ns_coordinates": report["elapsed_ns_coordinates"],
            "temporary_directory_removed": True, "writes": "none", "scientific_outputs": "intentionally absent"}


def build_plan(records: tuple[Mapping[str, Any], Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Validate every binding without nvcc, GPU, or writes."""
    pins, ledgers, inputs, instance, cache, prerequisites = _bind(records)
    points = _shared(engine.validation_points, ledgers)
    return {"schema": SCHEMA_PLAN, "mode": "plan", "purpose": PURPOSE, "track": TRACK,
            "pinned_inputs": pins, "self_sha256": current_hashes(SELF_RELATIVES), "domain": engine.domain_identity(cache),
            "classifier": {key: value for key, value in inputs.items() if key not in ("lambda_ref", "f_star")},
            "d015_pairs": [list(PRIMARY_PAIR)] + [list(pair) for pair in DIAGNOSTIC_PAIRS], "c_h_values": list(CH_VALUES),
            "record_schema": SCHEMA_RECORDS, "commitments": {"T_E_order": T_E_ORDER, "X_E_order": X_E_ORDER},
            "validation_coordinates": [engine._point_report(point) for point in points],
            "validation_coordinates_sha256": engine.validation_coordinates_sha256(),
            "prerequisites": prerequisites if prerequisites is not None else "not supplied to --plan",
            "compile_flags": list(COMPILE_FLAGS), "max_coordinates_per_invocation": MAX_COORDINATES_PER_INVOCATION,
            "nvcc_located": cuda_unbalanced.locate_nvcc() is not None, "writes": "none",
            "scientific_outputs": "intentionally absent"}


def run_validate(records, locate: Callable[[], str | None] = cuda_unbalanced.locate_nvcc) -> dict[str, Any]:
    """Non-value validation at the declared coordinates: device minima/compact ties and host summaries vs canonical CPU."""
    _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 is required")
    _require_nvcc(locate)
    pins, ledgers, inputs, instance, cache, prerequisites = _bind(records)
    platform_before = cuda_unbalanced._platform_fingerprint()
    points = _shared(engine.validation_points, ledgers)
    reference_u, reference_s = _shared(engine.cpu_reference, instance, points, cache)
    classifiers = build_classifiers(instance, inputs["lambda_ref"])
    canonical_per_point = []
    for k in range(len(points)):
        canonical: dict[str, Any] = {}
        for encoding, reference in (("unbalanced", reference_u[k]), ("slack", reference_s[k])):
            ordered = [reference[index] for index in range(len(reference))]
            bits, index, flags = _shared(engine.canonical_reduction, ordered, inputs["lambda_ref"])
            canonical[encoding] = (bits, index, flags)
        canonical_per_point.append(canonical)
    del reference_u, reference_s

    def consumer(coordinates):
        totals = {"h_min_bits_mismatches": 0, "h_min_index_mismatches": 0, "tie_entry_mismatches": 0, "summary_mismatches": 0}
        per_coordinate = []
        for k, device in enumerate(coordinates):
            point = points[k]
            entry: dict[str, Any] = {"scale": point["scale"], "coordinate": point["coordinate"], "linear": point["linear"]}
            canonical_device = {}
            for encoding in ("unbalanced", "slack"):
                counts = compare_compact(device[encoding], canonical_per_point[k][encoding])
                entry[encoding] = counts
                totals["h_min_bits_mismatches"] += counts["h_min_bits_mismatch"]
                totals["h_min_index_mismatches"] += counts["h_min_index_mismatch"]
                totals["tie_entry_mismatches"] += counts["tie_entry_mismatches"]
                bits, index, flags = canonical_per_point[k][encoding]
                canonical_device[encoding] = {"h_min_bits": bits, "h_min_index": index, "entries": compact_from_flags(flags)}
            ledger = ledgers[point["scale"]]
            from_device = coordinate_record(point, ledger, device, cache, classifiers, inputs["f_star"], inputs["lambda_ref"])
            from_canonical = coordinate_record(point, ledger, canonical_device, cache, classifiers, inputs["f_star"], inputs["lambda_ref"])
            validate_record(from_device, point["linear"], point["scale"], ledger, inputs["lambda_ref_hex"], len(cache))
            mismatch = int(canonical_bytes(from_device) != canonical_bytes(from_canonical))
            entry["summary_mismatch"] = mismatch
            totals["summary_mismatches"] += mismatch
            per_coordinate.append(entry)
        _require(len(per_coordinate) == len(points), "core output coordinate count mismatch")
        return per_coordinate, totals

    report, (per_coordinate, totals), nvcc_info, command, smi = _execute(points, MODE_VALIDATE, instance, inputs["lambda_ref"], cache,
                                                                         locate, consumer)
    _require(verify_pinned_inputs() == pins, "pinned input drift during validation")
    _require(cuda_unbalanced._platform_fingerprint() == platform_before, "platform fingerprint drift during validation")
    verdict = "pass" if all(value == 0 for value in totals.values()) else "fail"
    return {"schema": SCHEMA_VALIDATE, "mode": "validate",
            **_common(report, nvcc_info, command, smi, pins, platform_before, cache, prerequisites, inputs),
            "validation": {"per_coordinate": per_coordinate, "totals": totals,
                           "device_vs_host_cxx_mismatches": report["device_vs_host_cxx_mismatches"],
                           "tied_entries_written": report["tied_entries_written"],
                           "reference": "canonical CPU prepared domains -> certify.py reduction -> canonical reconstruction/classification"},
            "verdict": verdict}


def run_measure(records, scale: str, start: int, stop: int,
                locate: Callable[[], str | None] = cuda_unbalanced.locate_nvcc) -> dict[str, Any]:
    """Non-value timing of the exact core extraction/classification path over one independent range."""
    _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 is required")
    started_ns = time.monotonic_ns()
    _require_nvcc(locate)
    pins, ledgers, inputs, instance, cache, prerequisites = _bind(records)
    platform_before = cuda_unbalanced._platform_fingerprint()
    points = _shared(engine.range_points, ledgers, scale, start, stop)
    classifiers = build_classifiers(instance, inputs["lambda_ref"])

    def consumer(coordinates):
        built = 0
        for k, device in enumerate(coordinates):
            record = coordinate_record(points[k], ledgers[scale], device, cache, classifiers, inputs["f_star"], inputs["lambda_ref"])
            validate_record(record, points[k]["linear"], scale, ledgers[scale], inputs["lambda_ref_hex"], len(cache))
            built += 1  # the record is discarded here; nothing scientific leaves
        return built

    coordinate_started_ns = time.monotonic_ns()
    report, discarded, nvcc_info, command, smi = _execute(points, MODE_PRODUCE, instance, inputs["lambda_ref"], cache, locate, consumer)
    coordinate_finished_ns = time.monotonic_ns()
    _require(discarded == len(points), "measure built a different number of records than coordinates")
    _require(verify_pinned_inputs() == pins, "pinned input drift during measurement")
    _require(cuda_unbalanced._platform_fingerprint() == platform_before, "platform fingerprint drift during measurement")
    common = _common(report, nvcc_info, command, smi, pins, platform_before, cache, prerequisites, inputs)
    payload = {"schema": SCHEMA_MEASURE, "mode": "measure", **common,
               "range": {"scale": scale, "pass_id": engine.SCALES[scale]["pass_id"], "start": start, "stop": stop,
                         "count": stop - start, "linear_order": engine.LINEAR_ORDER},
               "records_built_and_discarded": discarded, "max_coordinates_per_invocation": MAX_COORDINATES_PER_INVOCATION,
               "verdict": "measured"}
    finished_ns = time.monotonic_ns()
    # coordinate time = compile + device run + host reconstruction/classification of every record (the exact
    # path a batch executes per coordinate); setup = binding, cache derivation, prerequisite checks, provenance.
    timing = _shared(engine.throughput_timing, finished_ns - started_ns, coordinate_finished_ns - coordinate_started_ns)
    measurement = {"schema": SCHEMA_MEASUREMENT, "unit": "coordinates",
                   "qualification_identity_sha256": common["core_validation_identity_sha256"],
                   "samples": [{"coordinates": len(points), **timing}],
                   "timing_rule": "wall = end-to-end monotonic span from the environment guard to result construction; "
                                  "coordinate = nvcc compile + device run + host reconstruction and classification of every record; "
                                  "setup = wall - coordinate (fixed per session)",
                   "measured_by": f"{SCHEMA_MEASURE} scale={scale} range=[{start},{stop})"}
    measurement["content_sha256"] = content_sha256(measurement)
    payload["timing"] = {"end_to_end_wall_ns": finished_ns - started_ns, **timing}
    payload["throughput_measurement"] = measurement
    return payload


# --------------------------------------------------------------------------
# Future --run-batch: artifact promotion (never invoked in this build)
# --------------------------------------------------------------------------

def require_safe_output_dir(output_dir: Path) -> Path:
    """Explicit directory outside the repository tree, no symlink escape, no nesting either way."""
    given = Path(output_dir)
    _require(given.is_absolute(), "output directory must be an absolute path")
    real = Path(os.path.realpath(given))
    _require(str(real) == str(given), "output directory path must not traverse a symbolic link")
    _require(real.is_dir(), "output directory must already exist")
    repository = Path(os.path.realpath(ROOT))
    for a, b in ((real, repository), (repository, real)):
        try:
            a.relative_to(b)
        except ValueError:
            continue
        raise CoreError("output directory must be outside the repository tree and must not contain it")
    return real


def validate_release(release: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
    _require(isinstance(release, dict) and release.get("schema") == SCHEMA_RELEASE, "release record schema mismatch")
    _require(release.get("content_sha256") == content_sha256(release), "release record content hash mismatch")
    _require(release.get("plan_content_sha256") == plan.get("content_sha256"), "release record is bound to a different plan")
    for key in ("released_by", "date", "review_id"):
        _require(isinstance(release.get(key), str) and release[key].strip() != "", f"release record lacks {key}")
    _require(release.get("authorizes") == "run-batch", "release record does not authorize run-batch")
    return dict(release)


def _fsync_write(path: Path, payload: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.pending-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_name, 0o644)
        os.link(temporary_name, path)  # refuses to overwrite
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def promote_batch(output_dir: Path, batch_id: str, records_payload: Mapping[str, Any], manifest_builder: Callable[[str, str], dict[str, Any]]) -> Path:
    """Stage records.json and manifest.json with fsync, then atomically rename the directory into place.

    ``manifest_builder(records_file_sha256, records_content_sha256)`` returns the manifest body; the
    final directory name never appears until both files are durable, and an existing final
    directory (complete or partial) is a refused collision.
    """
    root = require_safe_output_dir(output_dir)
    _require(isinstance(batch_id, str) and batch_id and "/" not in batch_id and batch_id[0] != ".", "malformed batch id")
    final = root / batch_id
    _require(not final.exists() and not final.is_symlink(), f"refusing to overwrite an existing batch artifact: {batch_id}")
    stage = Path(tempfile.mkdtemp(prefix=f".pending-{batch_id}-", dir=root))
    try:
        records_bytes = canonical_bytes(records_payload)
        _fsync_write(stage / "records.json", records_bytes)
        manifest = manifest_builder(_sha256_bytes(records_bytes), records_payload["content_sha256"])
        manifest["content_sha256"] = content_sha256(manifest)
        _fsync_write(stage / "manifest.json", canonical_bytes(manifest))
        _fsync_directory(stage)
        _require(not final.exists() and not final.is_symlink(), f"refusing to overwrite an existing batch artifact: {batch_id}")
        os.rename(stage, final)
        _fsync_directory(root)
    except OSError as exc:
        raise CoreError(f"batch artifact promotion failed: {exc}") from exc
    finally:
        if stage.exists():
            for name in ("records.json", "manifest.json"):
                try:
                    (stage / name).unlink()
                except FileNotFoundError:
                    pass
            try:
                stage.rmdir()
            except OSError:
                pass
    return final


def run_batch(records, plan: Mapping[str, Any], batch: Mapping[str, Any], release: Mapping[str, Any], output_dir: Path,
              locate: Callable[[], str | None] = cuda_unbalanced.locate_nvcc) -> dict[str, Any]:
    """FUTURE core producer: one independent batch range to a metadata manifest and canonical records.json.

    Requires the reviewed plan (validated by the contract before this call), a release record bound to it,
    both prerequisite records, nvcc and a T4.  Not invoked by any verifier; every guard fails closed.
    """
    _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 is required")
    started_ns = time.monotonic_ns()
    validate_release(release, plan)
    root = require_safe_output_dir(output_dir)
    batch_id = batch["batch_id"]
    _require(not (root / batch_id).exists(), f"batch artifact already exists: {batch_id}")
    _require_nvcc(locate)
    pins, ledgers, inputs, instance, cache, prerequisites = _bind(records)
    _require(plan.get("core_validation_identity", {}).get("pinned_inputs") == pins,
             "plan was produced against different pinned sources; re-validate and re-plan")
    _require(plan.get("prerequisite_qualification_identities") == {
        "unbalanced_identity_sha256": prerequisites["unbalanced_identity_sha256"],
        "slack_identity_sha256": prerequisites["slack_identity_sha256"]}, "plan binds different qualification identities")
    platform_before = cuda_unbalanced._platform_fingerprint()
    scale = plan["scale"]
    points = _shared(engine.range_points, ledgers, scale, batch["start"], batch["stop"])
    _require(len(points) == batch["count"] <= MAX_COORDINATES_PER_INVOCATION, "batch range exceeds the invocation cap")
    classifiers = build_classifiers(instance, inputs["lambda_ref"])

    def consumer(coordinates):
        built = []
        for k, device in enumerate(coordinates):
            record = coordinate_record(points[k], ledgers[scale], device, cache, classifiers, inputs["f_star"], inputs["lambda_ref"])
            validate_record(record, points[k]["linear"], scale, ledgers[scale], inputs["lambda_ref_hex"], len(cache))
            built.append(record)  # summaries only; the compact tie lists are dropped with the iterator
        return built

    report, coordinate_records, nvcc_info, command, smi = _execute(points, MODE_PRODUCE, instance, inputs["lambda_ref"], cache, locate, consumer)
    _require(len(coordinate_records) == len(points), "batch built a different number of records than coordinates")
    _require(verify_pinned_inputs() == pins, "pinned input drift during the batch")
    _require(cuda_unbalanced._platform_fingerprint() == platform_before, "platform fingerprint drift during the batch")
    common = _common(report, nvcc_info, command, smi, pins, platform_before, cache, prerequisites, inputs)
    _require(common["core_validation_identity_sha256"] == plan.get("core_validation_identity_sha256"),
             "observed core identity differs from the plan's validated identity; requalify/re-validate")
    records_payload = {"schema": SCHEMA_RECORDS, "batch_id": batch_id, "plan_content_sha256": plan["content_sha256"],
                       "pass_id": plan["pass_id"], "scale": scale,
                       "range": {"start": batch["start"], "stop": batch["stop"], "count": batch["count"]},
                       "linear_order": engine.LINEAR_ORDER, "record_count": len(coordinate_records),
                       "records": coordinate_records, "release_review_id": release["review_id"],
                       "core_validation_identity_sha256": common["core_validation_identity_sha256"]}
    records_payload["content_sha256"] = content_sha256(records_payload)
    session_id = _sha256_bytes(canonical_bytes({"platform": platform_before, "device": common["device"], "started_ns": started_ns}))

    def manifest_builder(records_file_sha256: str, records_content_sha256: str) -> dict[str, Any]:
        finished_ns = time.monotonic_ns()
        return {"schema": SCHEMA_MANIFEST, "batch_id": batch_id,
                "range": {"start": batch["start"], "stop": batch["stop"], "count": batch["count"]},
                "pass_id": plan["pass_id"], "scale": scale, "track": TRACK, "plan_content_sha256": plan["content_sha256"],
                "linear_order": plan["linear_order"], "grid": plan["grid"], "ledger_identity": plan["ledger_identity"],
                "source_sha256": plan["source_sha256"], "core_validation_identity_sha256": plan["core_validation_identity_sha256"],
                "prerequisite_qualification_identities": plan["prerequisite_qualification_identities"],
                "slack_domain_logical_sha256": plan["slack_domain_logical_sha256"], "compile_contract": plan["compile_contract"],
                "platform": plan["platform"], "release": {"review_id": release["review_id"], "released_by": release["released_by"],
                                                          "date": release["date"], "content_sha256": release["content_sha256"]},
                "records": {"file": "records.json", "file_sha256": records_file_sha256, "content_sha256": records_content_sha256,
                            "record_count": len(coordinate_records)},
                "session": {"session_id": session_id, "device_uuid_hex": common["device"]["device_uuid_hex"],
                            "start_platform_sha256": _sha256_bytes(canonical_bytes(platform_before)),
                            "end_platform_sha256": _sha256_bytes(canonical_bytes(cuda_unbalanced._platform_fingerprint()))},
                "timing": {"end_to_end_wall_ns": finished_ns - started_ns, "elapsed_ns_coordinates": report["elapsed_ns_coordinates"]},
                "scientific_outputs": "in records.json only; this manifest carries none"}

    final = promote_batch(root, batch_id, records_payload, manifest_builder)
    return {"schema": SCHEMA_BATCH_RUN, "mode": "run-batch", "batch_id": batch_id, "artifact_directory": str(final),
            "record_count": len(coordinate_records), "records_content_sha256": records_payload["content_sha256"],
            "core_validation_identity_sha256": common["core_validation_identity_sha256"], "verdict": "written",
            "scientific_outputs": "in records.json only"}
