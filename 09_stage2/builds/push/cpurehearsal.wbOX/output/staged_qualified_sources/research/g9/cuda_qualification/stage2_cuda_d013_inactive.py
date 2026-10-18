"""D013 INACTIVE-FAMILY (`+0.0`) ADDITIVE CUDA PATH -- host bridge and typed validation.

OFFLINE / HOST-EMULATION-ONLY DRAFT.  This module is the host side of
``stage2_cuda_d013_inactive.cu``.  It sits BESIDE the qualified v1 release and
imports it, but never modifies it: all 12 files of
``research/decisions/GATE_9_CUDA_CORE_CORRUPTION_QUALIFICATION_RELEASE.json``
stay byte-identical, exactly as
``research/decisions/GATE_9_WP0_D013_CUDA_PATH_AND_IDENTITY_SCOPE_OWNER_DECISION.md``
decision 1 requires.  The v1 refusal of `+0.0` families (core_bridge.cu:29 and
core_stream_engine.py:274-275) is DELIBERATE and is not relaxed here.

The owner-decided semantics this path implements, and nothing beyond them:

* **Per-condition `F_q`.**  ``C``, ``CB``, ``CS`` and ``CSB`` each name their own
  feasible set; ``feasible_q`` is membership in `F_q` and ``f*_q`` is the
  minimum of `f` over `F_q`.
* **Empty `F_q` is a hard stop.**  Refused with a typed error, no value
  written, matching the G3 ground-truth rule.
* **`|T_E|` is an exact integer `tie_count * 2^w`**, computed arithmetically and
  recorded with its factors ``(tie_count, w)``. `|C_E|` separately uses the
  whole-domain base. The retained register is NEVER enumerated.
* **Fixed conditions.**  ``C`` inactivates sector+budget, ``CB`` inactivates
  sector, ``CS`` inactivates budget, ``CSB`` activates both.  Cardinality is
  never inactive.
* **The inactive register is RETAINED with coefficient exactly `+0.0`**, and an
  inactive family contributes exactly `+0.0` -- never `-0.0`, never a product
  with a negative factor.
* **Frozen accumulation order**: `f`, `P_card`, sector `j = 1..4`, budget.

The host-stub path remains the default. A backend-1 CUDA library is accepted
only with the hash-bound token emitted by a successful release-gated A
qualification. That token does not authorize scientific outputs or close
Gate-9 section B.

The WP6 Python evaluator is the canonical reference for the cross-check round.
The comparison hook below checks the canonical result on integral-lift fixtures.
"""

from __future__ import annotations

import ctypes as C
import hashlib
import math
from pathlib import Path
import struct
import sys
import threading
from typing import Mapping, Sequence

from research.g9.cuda_qualification import stage2_cuda_core_bridge as bridge_v1
from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as core
from research.g9.cuda_qualification import stage2_cuda_input_frame as input_frame


# ---------------------------------------------------------------------------
# Frozen constants.  Every one is cross-checked against the compiled object by
# ``expected_condition_codes`` / ``expected_abi_layout`` below, so a host and a
# device that disagree about a width cannot both pass.
# ---------------------------------------------------------------------------
SCHEMA = "decisions_os/g9_cuda_d013_inactive_result/v1"
ABI_NAME = "g9_d013_run"
FRAME_HASH_ROLE = "host_bookkeeping_not_device_attestation"
RESULT_HASH_ROLE = "accidental_corruption_check_only"
WP6_HOOK_STATUS = "wp6_python_evaluator_under_review_hook_reserved"

# The four D013 conditions, as a mask of WHICH FAMILIES ARE ACTIVE.
CONDITION_C = 0
CONDITION_CB = 2
CONDITION_CS = 1
CONDITION_CSB = 3
CONDITIONS = ("C", "CB", "CS", "CSB")
CONDITION_CODE = {"C": CONDITION_C, "CB": CONDITION_CB,
                  "CS": CONDITION_CS, "CSB": CONDITION_CSB}
ACTIVITY_SECTOR = 1
ACTIVITY_BUDGET = 2
ACTIVITY_MASK = 3

# Which families each condition inactivates, read straight off the four D013
# predicates (GATE_9_WP6_D013_SPEC_GAP_DRAFT.md section 1.1).
INACTIVE_FAMILIES = {
    "C": frozenset({"sector", "budget"}),
    "CB": frozenset({"sector"}),
    "CS": frozenset({"budget"}),
    "CSB": frozenset(),
}

# The retained register width of each family: 2 bits per sector register (8 for
# all four) and 11 for budget. This is the owner-decided exponent w.
SECTOR_REGISTER_WIDTH = 8
BUDGET_REGISTER_WIDTH = 11
FAMILY_WIDTH = {"sector": SECTOR_REGISTER_WIDTH, "budget": BUDGET_REGISTER_WIDTH}

COEFFICIENT_FIELDS = core.COEFFICIENT_FIELDS
SLACK_FIELDS = ("sector_slack", "budget_slack")
STATE_COUNT = core.STATE_COUNT
ENCODINGS = core.ENCODINGS
ROW_CAPACITY = bridge_v1.ROW_CAPACITY

STATUS_REFUSED = 0
STATUS_OK = 1
STATUS_BUSY = 2

PayloadData = bridge_v1.PayloadData
CoefficientData = bridge_v1.CoefficientData
ScanResult = bridge_v1.ScanResult
CoreOutput = bridge_v1.CoreOutput
ConditionArray = C.c_uint32 * bridge_v1.ROW_CAPACITY
ROW_CAPACITY_C = C.c_uint32 * ROW_CAPACITY

COUNTER_FIELDS = ("inactive_register_visits", "enumerated_lifts_visited",
                  "negative_zero_energies", "inactive_term_nonzero",
                  "hazard_negative_zero_states", "states", "lift_total_base",
                  "lift_total_exact", "inactive_width", "row_count",
                  "invalid_registers")
# `lift_total_exact` is |C_E| for the slack stream, never |T_E|.
# `reserved` is padding: declared so the layout matches, never read as a value.
COUNTER_AUXILIARY_FIELDS = ("reserved",)
# Every field of the compiled struct, in declaration order. The compiled
# object reports this same number, so a field added or dropped on either side
# is refused at load time rather than silently misread.
COUNTER_FIELD_COUNT = len(COUNTER_FIELDS) + len(COUNTER_AUXILIARY_FIELDS)
COUNTER_FIELD_SET = frozenset(COUNTER_FIELDS)

RESULT_FIELDS = frozenset({"schema", "abi", "backend", "condition", "content_sha256",
                           "content_sha256_role", "result_sha256", "result_sha256_role",
                           "records", "counters"})
RECORD_FIELDS = frozenset({"row", "condition", "encoding", "word_count", "minimum",
                           "minimum_word", "minimum_index", "per_ch", "illegal",
                           "nesting", "compacted_count", "compaction_chunks",
                           "compaction_checksum", "compacted_entries", "t_e_size",
                           "t_e_factors", "c_e_size"})
ENVELOPE_FIELDS = frozenset({"schema", "abi", "backend", "condition", "content_sha256",
                             "content_sha256_role", "result_sha256", "result_sha256_role",
                             "records", "counters"})

# The flags word every tied minimizer carries: bits for c_H in {1024, 2048,
# 4096}. Restated here rather than read off another module, so this bridge
# never mutates the frozen v1 core to get a constant.
ALL_THRESHOLDS_FLAGS = 7

# Held across library loading, the single ABI call and every check that follows.
# The C guard separately refuses entries that bypass this lock.
_ABI_LOCK = threading.Lock()

_POSITIVE_ZERO_WORD = 0
_NEGATIVE_ZERO_WORD = 0x8000000000000000


class D013InactiveError(RuntimeError):
    """A D013 `+0.0` path input, call or result is malformed, refused or inconsistent."""


class D013EmptyFeasibleSetError(D013InactiveError):
    """`F_q` is empty for the requested condition: the owner-decided hard stop.

    Separate from every other refusal on purpose.  An empty `F_q` is not a
    malformed input and not a failed call: it is the one situation in which the
    owner decision fixes the answer outright ("Hard stop", matching the G3
    ground-truth rule), so it must never be reported as a value, and no field of
    any result is written.
    """


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise D013InactiveError(message)


def _refuse_empty_set(message: str) -> None:
    raise D013EmptyFeasibleSetError(message)


def _word(value: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def _unword(word: int) -> float:
    return struct.unpack("<d", struct.pack("<Q", word))[0]


def is_positive_zero(value: object) -> bool:
    """True only for the POSITIVE zero, bit pattern 0.  `-0.0` is not `+0.0`."""
    _require(type(value) is float and math.isfinite(value),
             "a `+0.0` coefficient test needs a finite float")
    return _word(value) == _POSITIVE_ZERO_WORD


def is_negative_zero(value: object) -> bool:
    _require(type(value) is float and math.isfinite(value),
             "a `-0.0` test needs a finite float")
    return _word(value) == _NEGATIVE_ZERO_WORD


def inactive_width(condition: int) -> int:
    """`w`: the total retained width of the condition's inactive families."""
    _require(type(condition) is int and 0 <= condition <= ACTIVITY_MASK,
             "condition code is out of range")
    width = 0
    for family in INACTIVE_FAMILIES[condition_name(condition)]:
        width += FAMILY_WIDTH[family]
    return width


def condition_name(condition: int) -> str:
    """The canonical name of a condition code, refusing anything unknown.

    The lookup is a search rather than a direct index so that the refusal below
    is REACHABLE: an unknown code is refused here, by this function, instead of
    relying only on the caller's precondition. `check_typed_refusals` fuzzes
    `condition_name` directly, so weakening either the lookup or the refusal
    makes the fixtures fail.
    """
    _require(type(condition) is int, "condition code must be an int")
    for name, code in CONDITION_CODE.items():
        if code == condition:
            return name
    raise D013InactiveError("unknown D013 condition code")


def expected_condition_codes() -> tuple[int, int, int, int, int, int]:
    return (CONDITION_C, CONDITION_CB, CONDITION_CS, CONDITION_CSB,
            ACTIVITY_SECTOR, ACTIVITY_BUDGET)


def expected_abi_layout() -> tuple[int, int, int, int, int, int]:
    return (C.sizeof(PayloadData), C.sizeof(CoefficientData), C.sizeof(ScanResult),
            C.sizeof(CoreOutput), C.sizeof(D013Counters), C.sizeof(D013Output))


def expected_counters_layout() -> tuple[int, ...]:
    """A description of the counter struct, for cross-checking the compiled object.

    ctypes exposes no public field-offset accessor, so offsets cannot be read
    directly.  What IS checked is the struct's total size, the number of
    declared counter fields, and the sizes of the three field classes, all of
    which together pin the layout the compiled object must agree on.  The
    counter SEMANTICS that matter -- the three MUST-BE-ZERO invariants and
    ``|T_E| = base * 2^w`` -- are checked against real returned VALUES in
    ``require_bounded_counters``, not against offsets.
    """
    return (C.sizeof(C.c_uint64), C.sizeof(C.c_uint32),
            C.sizeof(D013Counters), len(COUNTER_FIELDS),
            COUNTER_FIELD_COUNT)


class D013Counters(C.Structure):
    # Field ORDER matches the compiled `G9D013Counters` exactly; the last two
    # uint32 fields are declared in the order `inactive_width, row_count,
    # invalid_registers, reserved`. A different order here would silently
    # misread `row_count` as `invalid_registers`, so the layout description
    # exported by the compiled object is compared at load time.
    _fields_ = [("inactive_register_visits", C.c_uint64),
                ("enumerated_lifts_visited", C.c_uint64),
                ("negative_zero_energies", C.c_uint64),
                ("inactive_term_nonzero", C.c_uint64),
                ("hazard_negative_zero_states", C.c_uint64),
                ("states", C.c_uint64),
                ("lift_total_base", C.c_uint64),
                ("lift_total_exact", C.c_uint64),
                ("inactive_width", C.c_uint32),
                ("row_count", C.c_uint32),
                ("invalid_registers", C.c_uint32),
                ("reserved", C.c_uint32)]


class D013Output(C.Structure):
    _fields_ = [("core", CoreOutput), ("conditions", ROW_CAPACITY_C),
                ("counters", D013Counters)]


class CoefficientDataArray(C.Array):
    _length_ = ROW_CAPACITY
    _type_ = CoefficientData


def _load_checked_abi(library_path: Path, *, verified_release: object = None):
    _require(sys.byteorder == "little", "the frozen uint64 stream requires a little-endian host")
    _require(isinstance(library_path, Path) and library_path.is_file(),
             "compiled D013 ABI library is missing")
    try:
        library = C.CDLL(str(library_path))
        layout = library.g9_d013_abi_layout
        counters = library.g9_d013_counters_layout
        codes = library.g9_d013_condition_codes
        run = library.g9_d013_run
        backend = library.g9_d013_backend
    except (OSError, AttributeError) as exc:
        raise D013InactiveError("compiled D013 ABI exports are missing") from exc
    # This path is ADDITIVE. It must not also carry the v1 entry points, whose
    # `+0.0` refusal this path exists to complement, not to reuse or override.
    for retired in ("g9_core_run_v1", "g9_core_run_v2", "g9_core_copy_offsets_v1"):
        _require(not hasattr(library, retired),
                 "the D013 library still exports a version-1 or version-2 core entry")
    for function, width in ((layout, 6), (counters, 5), (codes, 6)):
        function.argtypes = [C.POINTER(C.c_uint64), C.c_uint32]
        function.restype = C.c_uint32
    run.argtypes = [C.POINTER(PayloadData), C.POINTER(CoefficientData), C.POINTER(C.c_uint32),
                    C.c_uint32, C.POINTER(D013Output)]
    run.restype = C.c_uint32
    backend.argtypes = []
    backend.restype = C.c_uint32

    actual_layout = (C.c_uint64 * 6)()
    _require(layout(actual_layout, 6) == 6 and tuple(actual_layout) == expected_abi_layout(),
             "compiled D013 ABI layout differs from the Python bridge")
    actual_counters = (C.c_uint64 * 5)()
    _require(counters(actual_counters, 5) == 5 and tuple(actual_counters) == expected_counters_layout(),
             "compiled D013 counter layout differs from the Python bridge")
    actual_codes = (C.c_uint64 * 6)()
    _require(codes(actual_codes, 6) == 6 and tuple(actual_codes) == expected_condition_codes(),
             "compiled D013 condition codes differ from the Python bridge")
    kind = backend()
    _require(kind in (0, 1), "compiled D013 ABI backend tag is invalid")
    if kind == 1:
        from research.g9.cuda_qualification import stage2_cuda_d013_inactive_corruption_qualification as qualification
        _require(qualification._check_token(verified_release),
                 "backend 1 requires a verified D013 release token")
    return run, kind


def validate_condition(condition: object) -> str:
    """Return the canonical condition name, refusing anything malformed.

    A bool, a float, a negative code, an unknown bit pattern and an unknown
    name are all refused: the four conditions are the ONLY admissible inputs,
    and an unrecognised code must never be silently clamped to a valid one.

    There is no separate ``type(...) is int`` discriminator, because one would
    be redundant: the NAME table and the CODE table are keyed so that neither
    accepts the other's domain, and ``condition_name`` re-checks the type
    itself.  Every guard below is therefore load-bearing and independently
    covered by ``check_typed_refusals`` and ``check_argument_fuzz``:

    * a name is checked against the NAME table and returned unchanged;
    * anything else must be an int that is in the CODE table, and is resolved
      to its canonical name by ``condition_name``, which refuses a non-int and
      an unknown code in its own right.
    """
    if type(condition) is str:
        _require(condition in CONDITION_CODE, "unknown D013 condition name")
        return condition
    _require(type(condition) is int and condition in CONDITION_CODE.values(),
             "unknown D013 condition code")
    return condition_name(condition)


def validate_coefficient_record(record: object, condition: str) -> dict[str, float]:
    """Validate one coefficient record against one condition's active families.

    The rules are the owner-decided ones and they are ASYMMETRIC on purpose:

    * an ACTIVE family's slack coefficient must be strictly positive, exactly as
      v1 requires (``core_stream_engine.py:274-275``);
    * an INACTIVE family's slack coefficient must be the POSITIVE ZERO, bit
      pattern 0.  ``-0.0`` is refused: D015 section 1.4 says the coefficient is
      "exactly `+0.0`", and a negative zero is a different binary64 word.  A
      tiny POSITIVE value is refused too, because a strictly positive
      coefficient is a mathematically ACTIVE coefficient and would make the
      family's register non-degenerate -- exactly the corruption the WP0 audit
      section 2.2.4 identifies.
    """
    _require(isinstance(record, Mapping), "coefficient record must be a mapping")
    _require(set(record) == set(COEFFICIENT_FIELDS),
             "coefficient record has the wrong field set")
    values = {}
    for field in COEFFICIENT_FIELDS:
        value = record[field]
        _require(type(value) is float and math.isfinite(value),
                 f"coefficient {field} must be a finite float")
        values[field] = value
    inactive = INACTIVE_FAMILIES[condition]
    for field, family in (("sector_slack", "sector"), ("budget_slack", "budget")):
        if family in inactive:
            _require(is_positive_zero(values[field]),
                     f"an inactive {family} family's coefficient must be exactly +0.0, "
                     f"not {_hex_of(values[field])}")
        else:
            _require(values[field] > 0.0,
                     f"an active {family} family's coefficient must be strictly positive")
    return values


def _hex_of(value: float) -> str:
    return value.hex()


def validate_records(records: object, condition: str) -> list[dict[str, float]]:
    _require(isinstance(records, Sequence) and not isinstance(records, (str, bytes)),
             "coefficient records must be a sequence")
    _require(1 <= len(records) <= ROW_CAPACITY,
             "exactly one or two coefficient records are required")
    return [validate_coefficient_record(record, condition) for record in records]


def decode_payload(payload: object) -> PayloadData:
    """Decode a validated v1 payload into the unchanged ABI struct."""
    try:
        normalized = core.validate_payload(payload)
    except (core.CoreStreamEngineError, TypeError, ValueError, OverflowError) as exc:
        raise D013InactiveError("input payload is invalid") from exc
    value = PayloadData()
    for index, word in enumerate(normalized["mu"]):
        value.mu[index] = word
    for row in range(core.ASSET_COUNT):
        for column in range(core.ASSET_COUNT):
            value.sigma[row * core.ASSET_COUNT + column] = normalized["sigma"][row][column]
    for index, word in enumerate(normalized["prices"]):
        value.prices[index] = word
    value.kappa_risk = normalized["kappa_risk"]
    value.k_value = normalized["k"]
    value.c_value = normalized["c"]
    value.b = normalized["b"]
    value.lambda_ref = normalized["lambda_ref"]
    for sector, block in enumerate(normalized["sectors"]):
        for member, asset in enumerate(block):
            value.membership[sector][member] = asset
    return value


def decode_records(records: object, condition: str = "CSB") -> "CoefficientDataArray":
    """Fill the ABI coefficient array from validated records.

    ``condition`` is required by the caller in ``run_host_emulated_frame``, so
    this lower-level entry re-validates by default against the all-active
    condition, which is the strictest: a record valid there is valid for every
    condition.  A caller that has already validated for a specific condition
    passes that name and the same rule is applied for it.
    """
    values = validate_records(records, condition)
    array = CoefficientDataArray()
    for index, record in enumerate(values):
        for field in COEFFICIENT_FIELDS:
            setattr(array[index], field, record[field])
    return array


def decode_conditions(condition: object, record_count: object) -> "ConditionArray":
    """Fill the ABI condition array, refusing anything not a real condition."""
    name = validate_condition(condition)
    _require(type(record_count) is int and 1 <= record_count <= ROW_CAPACITY,
             "the condition array needs a row count inside the ABI capacity")
    code = CONDITION_CODE[name]
    array = ConditionArray()
    for index in range(record_count):
        array[index] = code
    return array


def _counters(raw: D013Counters) -> dict[str, int]:
    return {name: int(getattr(raw, name)) for name in COUNTER_FIELDS}


def _summaries(output: D013Output, record_count: int) -> dict[tuple[int, str], dict[str, object]]:
    summaries: dict[tuple[int, str], dict[str, object]] = {}
    for slot in range(record_count):
        for encoding_index, encoding in enumerate(ENCODINGS):
            result = output.core.results[slot][encoding_index]
            count = int(result.compacted_count)
            _require(1 <= count <= core.MAX_COMPACTED_ENTRIES,
                     "compiled D013 core returned an invalid compacted count")
            summaries[(slot, encoding)] = {
                "word_count": int(result.word_count),
                "minimum": float(result.minimum),
                "minimum_index": int(result.minimum_index),
                "per_ch": tuple(int(value) for value in result.per_ch),
                "illegal": int(result.illegal),
                "nesting": int(result.nesting),
                "compacted_count": count,
                "compaction_chunks": int(result.compaction_chunks),
                "compaction_checksum": int(result.compaction_checksum),
                "compacted_entries": tuple(int(result.entries[slot_index])
                                           for slot_index in range(count)),
            }
    return summaries


def require_bounded_counters(counters: Mapping[str, object], condition: str,
                             record_count: int) -> None:
    """Direct checks on the bounded counters, before anything is trusted.

    The three MUST-BE-ZERO counters are the whole `+0.0` claim in numeric form:
    a non-zero `inactive_register_visits` means an inactive register was
    enumerated, a non-zero `inactive_term_nonzero` means an inactive family
    reported something other than the positive zero, and a non-zero
    `negative_zero_energies` means the inactive term's sign reached the energy
    stream.  `hazard_negative_zero_states` is NOT required to be zero: it
    measures the hazard this path avoids.
    """
    _require(isinstance(counters, Mapping) and set(counters) == COUNTER_FIELD_SET,
             "counters have the wrong key set")
    for name, value in counters.items():
        _require(type(value) is int and value >= 0,
                 f"counter {name} must be a non-negative int")
    _require(counters["inactive_register_visits"] == 0,
             "an inactive family's register was visited; the symbolic factor was not honoured")
    _require(counters["inactive_term_nonzero"] == 0,
             "an inactive family reported a term other than exactly +0.0")
    _require(counters["negative_zero_energies"] == 0,
             "a -0.0 reached the energy stream")
    _require(counters["invalid_registers"] == 0,
             "compiled D013 core reported an invalid register")
    _require(counters["states"] == STATE_COUNT,
             "the decoded state count differs from the frozen 2^20 domain")
    _require(counters["row_count"] == record_count, "the counter row count differs")
    # This counter describes the whole active-lift domain |C_E|. The tied
    # subset |T_E| is computed separately for each record below.
    width = inactive_width(CONDITION_CODE[condition])
    _require(counters["inactive_width"] == width,
             "the retained inactive register width differs from the owner decision")
    _require(counters["lift_total_base"] >= STATE_COUNT,
             "the |C_E| base is smaller than the decoded domain")
    _require(counters["lift_total_exact"] ==
             counters["lift_total_base"] * (1 << counters["inactive_width"]),
             "|C_E| is not the exact integer base * 2^w")


def require_bounded_result(envelope: object, condition: str, record_count: int,
                           expected_content_sha256: object = None,
                           verified_release: object = None) -> dict[str, object]:
    """Consumer-side acceptance of a whole envelope, with no trust in the caller.

    ``expected_content_sha256`` is what a consumer REBUILDS from the inputs it
    independently holds. It is required for a caller that has those inputs;
    passing ``None`` accepts the field's own shape only, which is a bare echo
    and therefore proves nothing about which inputs the call consumed.
    """
    _require(isinstance(envelope, dict) and set(envelope) == ENVELOPE_FIELDS,
             "envelope has the wrong key set")
    _require(envelope["schema"] == SCHEMA and envelope["abi"] == ABI_NAME and
             envelope["content_sha256_role"] == FRAME_HASH_ROLE and
             envelope["result_sha256_role"] == RESULT_HASH_ROLE,
             "envelope schema or declared roles differ")
    _require(type(envelope["backend"]) is int and envelope["backend"] in (0, 1),
             "envelope backend is not the host-emulation stub or verified CUDA ABI")
    if envelope["backend"] == 1:
        from research.g9.cuda_qualification import stage2_cuda_d013_inactive_corruption_qualification as qualification
        _require(qualification._check_token(verified_release),
                 "CUDA D013 envelope requires a verified owner-approved release token")
    _require(envelope["condition"] == condition, "envelope condition differs")
    _require(type(envelope["content_sha256"]) is str and len(envelope["content_sha256"]) == 64 and
             all(character in "0123456789abcdef" for character in envelope["content_sha256"]),
             "content hash is not a lowercase SHA-256")
    if expected_content_sha256 is not None:
        _require(type(expected_content_sha256) is str and
                 len(expected_content_sha256) == 64 and
                 envelope["content_sha256"] == expected_content_sha256,
                 "envelope content hash differs from the consumer's rebuilt inputs")
    counters = envelope["counters"]
    require_bounded_counters(counters, condition, record_count)
    records = envelope["records"]
    _require(isinstance(records, list) and len(records) == record_count * len(ENCODINGS),
             "record set has the wrong size")
    for record in records:
        _require(isinstance(record, dict) and set(record) == RECORD_FIELDS,
                 "record has the wrong field set")
        _require(record["condition"] == condition, "record condition differs")
        _require(record["encoding"] in ENCODINGS, "record encoding is unknown")
        _require(type(record["row"]) is int and 0 <= record["row"] < record_count,
                 "record row is out of range")
        _require(type(record["word_count"]) is int and record["word_count"] >= STATE_COUNT,
                 "record word count is below the decoded domain")
        _require(type(record["minimum"]) is float and math.isfinite(record["minimum"]),
                 "record minimum is not finite")
        _require(type(record["minimum_word"]) is str and len(record["minimum_word"]) == 16 and
                 all(character in "0123456789abcdef" for character in record["minimum_word"]),
                 "record minimum word is not a 16-digit binary64 bit pattern")
        # The exact bits are authoritative: the value must be what those bits
        # say. A `-0.0` and a `+0.0` compare equal as floats, so the VALUE is
        # reconstructed from the word, never merely compared.
        _require(_unword(int(record["minimum_word"], 16)) == record["minimum"],
                 "record minimum word differs from its minimum")
        _require(type(record["minimum_index"]) is int and
                 0 <= record["minimum_index"] < record["word_count"],
                 "record minimum index is outside the stream")
        _require(type(record["per_ch"]) is tuple and len(record["per_ch"]) == len(core.CH_VALUES) and
                 all(type(value) is int and value >= 0 for value in record["per_ch"]),
                 "per-c_H counts are malformed")
        _require(type(record["illegal"]) is int and record["illegal"] == 0 and
                 type(record["nesting"]) is int and record["nesting"] == 0,
                 "record reports illegal or non-nested flags")
        count = record["compacted_count"]
        entries = record["compacted_entries"]
        _require(type(count) is int and 1 <= count <= core.MAX_COMPACTED_ENTRIES and
                 isinstance(entries, tuple) and len(entries) == count,
                 "compacted entry count is outside the declared cap")
        _require(type(record["compaction_chunks"]) is int and
                 record["compaction_chunks"] == core.compaction_chunk_count(record["word_count"]),
                 "compaction chunk count differs from the stream length")
        previous = -1
        checksum = core.FNV_OFFSET
        per_ch = [0] * len(core.CH_VALUES)
        for entry in entries:
            _require(type(entry) is int and 0 <= entry <= core.MASK64,
                     "compacted entry is not a uint64")
            flags, index = entry >> 32, entry & 0xFFFFFFFF
            _require(flags in core.COMPACTED_FLAGS,
                     "compacted entry carries an illegal flag word")
            _require(previous < index < record["word_count"],
                     "compacted entries are not strictly ascending inside the stream")
            previous = index
            for bit in range(len(per_ch)):
                per_ch[bit] += (flags >> bit) & 1
            checksum = ((checksum ^ entry) * core.FNV_PRIME) & core.MASK64
        _require(tuple(per_ch) == record["per_ch"],
                 "per-c_H counts differ from the compacted entries")
        width = counters["inactive_width"]
        tie_count = per_ch[1]  # canonical WP6 c_H = 2048
        _require(type(record["t_e_factors"]) is tuple and
                 record["t_e_factors"] == (tie_count, width),
                 "|T_E| factors differ from the tied active candidates")
        _require(type(record["t_e_size"]) is int and
                 record["t_e_size"] == tie_count * (1 << width),
                 "|T_E| differs from tie_count * 2^w")
        _require(type(record["c_e_size"]) is int and
                 record["c_e_size"] == record["word_count"] * (1 << width),
                 "|C_E| differs from the whole active domain")
        if record["encoding"] == "slack":
            _require(record["c_e_size"] == counters["lift_total_exact"],
                     "the slack |C_E| differs from the whole-domain counter")
        _require(checksum == record["compaction_checksum"],
                 "compaction checksum differs from the compacted entries")
        _require(((ALL_THRESHOLDS_FLAGS << 32) | record["minimum_index"]) in entries,
                 "the stream minimum is missing from its compacted tie entries")
    _require(envelope["result_sha256"] == result_commitment(condition, records, counters),
             "result commitment differs from the bounded result")
    return dict(envelope)


def result_commitment(condition: object, records: object,
                      counters: object) -> str:
    """Domain-separated canonical-JSON SHA-256; each minimum by its binary64 word.

    The inputs are validated rather than trusted, because a NaN or a non-string
    minimum would otherwise escape as a raw ``ValueError`` from the JSON
    encoder instead of this path's own typed refusal.
    """
    name = validate_condition(condition)
    _require(isinstance(records, Sequence) and not isinstance(records, (str, bytes)),
             "commitment records must be a sequence")
    _require(isinstance(counters, Mapping) and set(counters) == COUNTER_FIELD_SET,
             "commitment counters have the wrong key set")
    body = []
    for record in records:
        _require(isinstance(record, Mapping) and set(record) == RECORD_FIELDS,
                 "commitment record has the wrong field set")
        _require(record["condition"] == name and record["encoding"] in ENCODINGS,
                 "commitment record names a different condition or encoding")
        for field, value in record.items():
            if field == "minimum":
                _require(type(value) is float and math.isfinite(value),
                         "a commitment minimum must be a finite float")
        body.append({name_: (list(value) if type(value) is tuple else value)
                     for name_, value in record.items()})
    return hashlib.sha256(input_frame.canonical_bytes(
        {"schema": "decisions_os/g9_cuda_d013_inactive_commitment/v1",
         "condition": name, "records": body, "counters": dict(counters)})).hexdigest()


def _require_feasible_nonempty(payoff: object, condition: str) -> None:
    """Owner decision 2: an empty `F_q` is a typed hard stop, never a value.

    ``payoff`` is the caller's already-computed count of members of `F_q`.  It
    is checked here, BEFORE the ABI is touched, so an empty `F_q` cannot
    produce a partial record, a scrubbed buffer or any other artefact that a
    caller ignoring the exception could mistake for a result.
    """
    _require(type(payoff) is int and payoff >= 0,
             "the feasible-set size must be a non-negative int")
    if payoff == 0:
        _refuse_empty_set(f"F_{condition} is empty: no feasible portfolio for this condition; "
                          "this is a D013 hard stop, not a value")


def content_hash_for(payload: object, records: object, condition: object) -> str:
    """The exact-binary64 content identity of ONE call's inputs.

    A consumer rebuilds this from the payload, the coefficient records and the
    condition it independently holds, and compares it with the envelope's
    ``content_sha256``. That is what stops an envelope being replayed against
    different inputs: the field is a bare echo on its own, and only a REBUILT
    value is evidence.
    """
    name = validate_condition(condition)
    values = validate_records(records, name)
    body = {"condition": name, "payload": decode_payload_words(payload),
            "records": [{field: value[field].hex() for field in COEFFICIENT_FIELDS}
                        for value in values]}
    return hashlib.sha256(input_frame.canonical_bytes(body)).hexdigest()


def run_host_emulated_frame(payload: object, records: object, condition: object,
                            library_path: Path, feasible_count: object,
                            *, verified_release: object = None) -> dict[str, object]:
    """Exercise the D013 ABI, defaulting to the caller-built g++ host stub.

    A CUDA backend requires ``verified_release`` from a successful
    release-gated qualification; backend 0 needs no token. ``feasible_count``
    is `|F_q|`. It is required, not optional: the owner
    decision fixes an empty `F_q` as a hard stop, so this entry point cannot
    omit the feasibility information it is refusing on.
    """
    name = validate_condition(condition)
    _require_feasible_nonempty(feasible_count, name)
    values = validate_records(records, name)
    record_count = len(values)
    # The library path is validated HERE, before any decoding, so a malformed
    # path is this path's own typed refusal rather than a raw PathError from
    # further down.
    _require(isinstance(library_path, Path),
             "the compiled D013 library must be named by a pathlib.Path")
    decoded = decode_payload(payload)
    row_array = decode_records(values, name)
    condition_array = decode_conditions(name, record_count)
    with _ABI_LOCK:
        run, backend = _load_checked_abi(library_path, verified_release=verified_release)
        if backend == 1:
            from research.g9.cuda_qualification import stage2_cuda_d013_inactive_corruption_qualification as qualification
            _require(qualification._check_token(verified_release),
                     "backend 1 requires a verified D013 release token")
        output = D013Output()
        status = run(C.byref(decoded), row_array, condition_array, record_count, C.byref(output))
        # A refused or busy call's buffer is never read.
        _require(status != STATUS_BUSY, "compiled D013 core is busy with another call")
        _require(status == STATUS_OK, "compiled D013 core refused or failed the validated input")
        counters = _counters(output.counters)
        require_bounded_counters(counters, name, record_count)
        summaries = _summaries(output, record_count)
        for slot in range(record_count):
            _require(int(output.conditions[slot]) == CONDITION_CODE[name],
                     "the compiled core did not echo the requested condition")
        rows = []
        for slot in range(record_count):
            for encoding in ENCODINGS:
                summary = summaries[(slot, encoding)]
                width = counters["inactive_width"]
                tie_count = summary["per_ch"][1]
                rows.append({"row": slot, "condition": name, "encoding": encoding,
                             "minimum_word": format(_word(summary["minimum"]), "016x"),
                             "t_e_size": tie_count * (1 << width),
                             "t_e_factors": (tie_count, width),
                             "c_e_size": summary["word_count"] * (1 << width),
                             **summary})
                # `minimum_word` is the exact binary64 BIT PATTERN, kept beside
                # the value so a later reader can distinguish `+0.0` from
                # `-0.0` and can never re-spell a minimum as a decimal. It is
                # validated against `minimum` in `require_bounded_result`, and
                # the value it must decode to is reconstructed from those bits
                # rather than from a float comparison.
                _require(_unword(int(rows[-1]["minimum_word"], 16)) == summary["minimum"],
                         "the minimum word does not round-trip to its minimum")
        # The content identity is computed by the SAME public function a
        # consumer uses to rebuild it, so the two can never drift apart.
        content = content_hash_for(payload, values, name)
        envelope = {"schema": SCHEMA, "abi": ABI_NAME, "backend": backend,
                    "condition": name, "content_sha256": content,
                    "content_sha256_role": FRAME_HASH_ROLE, "records": rows,
                    "counters": counters, "result_sha256": "", "result_sha256_role": RESULT_HASH_ROLE}
        envelope["result_sha256"] = result_commitment(name, rows, counters)
        return require_bounded_result(envelope, name, record_count,
                                      verified_release=verified_release)


def decode_payload_words(payload: object) -> dict[str, object]:
    """The exact validated binary64 words of a payload, for content binding only."""
    normalized = core.validate_payload(payload)
    return {"mu": [value.hex() for value in normalized["mu"]],
            "sigma": [[value.hex() for value in row] for row in normalized["sigma"]],
            "prices": [value.hex() for value in normalized["prices"]],
            "kappa_risk": normalized["kappa_risk"].hex(),
            "k": normalized["k"].hex(), "c": normalized["c"].hex(),
            "b": normalized["b"].hex(), "lambda_ref": normalized["lambda_ref"].hex(),
            "sectors": [list(block) for block in normalized["sectors"]]}


def _canonical_registers_are_whole(wp6_result: object) -> bool:
    """True iff every ACTIVE register in WP6's canonical word is a whole number.

    A whole register value is its own exact minimiser, so the base lift stream
    carries exactly one word for that state and the frozen v1 stream index of
    the state's word IS the displayed x index.  A non-whole value is the floor
    of a fractional residual, so the base word is the minimum of that state's
    lifts and the position of the tied word is not determined by x alone.
    """
    from research.g9 import stage2_d013_inactive_evaluator as wp6
    _require(isinstance(wp6_result, wp6.ConditionResult),
             "the canonical WP6 result is malformed")
    width = len(wp6_result.z_ref) - 5
    return all(float(value).is_integer() for value in wp6_result.z_ref[width:])


def cross_check_against_wp6_evaluator(result: object, condition: object,
                                      wp6_result: object, row: object = 0,
                                      wp6_context: object = None) -> dict[str, object]:
    """Compare one integral-lift slack row with the canonical WP6 result.

    The caller evaluates WP6 independently. Integral residuals give one active
    lift per decoded state, so a compacted stream index is the displayed x
    index. Other landscapes are refused instead of silently mis-mapping ties.
    """
    from research.g9 import stage2_d013_inactive_evaluator as wp6
    name = validate_condition(condition)
    _require(type(result) is dict and set(result) == ENVELOPE_FIELDS,
             "the result offered for a WP6 cross-check is malformed")
    _require(isinstance(wp6_result, wp6.ConditionResult) and
             wp6_result.condition == name,
             "the canonical WP6 result or condition is malformed")
    _require(isinstance(wp6_context, wp6.ConditionContext) and
             wp6_context.condition == name, "the WP6 D016 context is malformed")
    _require(type(row) is int and row >= 0, "the cross-check row must be a nonnegative int")
    matches = [item for item in result["records"]
               if item["row"] == row and item["encoding"] == "slack"]
    _require(len(matches) == 1, "the requested slack row is missing or duplicated")
    item = matches[0]
    # WP6's canonical word stores four sector register *values* plus one
    # budget register value after the displayed x bits.
    width = len(wp6_result.z_ref) - 5
    _require(width > 0 and wp6_result.raw_domain.base == item["word_count"],
             "the cross-check requires one active lift per decoded state")
    def _same(field: str, actual: object, expected: object) -> None:
        _require(actual == expected,
                 f"WP6 mismatch {name} row {row} {field}: WP6b={actual!r} WP6={expected!r}")
    _same("minimum_word", item["minimum_word"], format(wp6.bits_of(wp6_result.h_e_min), "016x"))
    # The canonical argmin is compared AS A WORD, not mapped onto a stream
    # index.  WP6's canonical word is the displayed x followed by the five
    # ACTIVE registers' base minimiser VALUES, while the frozen v1 stream index
    # is the position of the first word attaining H_E,min in the LIFT stream --
    # a different object under two different tie conventions (see the
    # `check_wp6_crosscheck` scope note).  The mapping from x to a stream index
    # needs a WHOLE-number slack residual, so it is applied only when the
    # canonical registers really are whole: then the base stream carries one
    # word per decoded state and position == the displayed x index.  On a
    # non-whole register the position is not determined by the displayed x, so
    # the index is not compared at all -- never a silently invented one.
    x_index = sum(bit << (width - 1 - index) for index, bit in enumerate(wp6_result.z_ref[:width]))
    if _canonical_registers_are_whole(wp6_result):
        _same("canonical_minimum_index", item["minimum_index"], x_index)
    _require(wp6_result.t_e_factors[0] >= 1,
             "WP6 reported an empty tie set, so |T_E| would be vacuously zero")
    tied = tuple(tuple((entry & 0xFFFFFFFF) >> (width - 1 - index) & 1
                       for index in range(width))
                  for entry in item["compacted_entries"] if (entry >> 32) & 2)
    _same("tie_set", tied, wp6_result.tie_set)
    _same("tie_count", len(tied), wp6_result.t_e_factors[0])
    _same("|T_E|", item["t_e_size"], wp6_result.t_e_size)
    _same("|T_E| factors", item["t_e_factors"], wp6_result.t_e_factors)
    _same("|C_E|", item["c_e_size"], wp6_result.raw_domain.raw_size)
    from src.g4.classification import DecodedClassifier, OriginalObjectiveService
    classifier = DecodedClassifier(
        optimum_service=OriginalObjectiveService(
            objective=lambda state: wp6.fast_decoded_state(wp6_context, state).f_value,
            lambda_ref=wp6_context.lambda_ref),
        feasible=lambda state: wp6.feasible_q(wp6_context, state))
    atomic = tuple((x, classifier.label(x, wp6_result.optimum.f_star))
                   for x in tuple(dict.fromkeys(tied)))
    _same("D016 atomic labels", atomic, wp6_result.atomic_labels)
    _same("D016 primary label", classifier.label_set(tuple(x for x, _ in atomic),
                                                    wp6_result.optimum.f_star),
          wp6_result.primary_label)
    counts = {label: sum(value == label for _, value in atomic)
              for label in ("A", "B", "C")}
    _same("D016 label counts", counts, wp6_result.label_counts)
    return {"condition": name, "row": row, "minimum_word": item["minimum_word"],
            "minimum_index": item["minimum_index"], "tie_set": tied,
            "t_e_size": item["t_e_size"], "t_e_factors": item["t_e_factors"],
            "c_e_size": item["c_e_size"]}


def wp6_evaluator_import_is_permitted() -> bool:
    """The canonical WP6 evaluator has passed independent validation."""
    return True


__all__ = [
    "D013InactiveError", "D013EmptyFeasibleSetError", "D013Counters", "D013Output",
    "CONDITIONS", "CONDITION_CODE", "CONDITION_C", "CONDITION_CB", "CONDITION_CS",
    "CONDITION_CSB", "INACTIVE_FAMILIES", "SECTOR_REGISTER_WIDTH", "BUDGET_REGISTER_WIDTH",
    "FAMILY_WIDTH", "COUNTER_FIELDS", "ENVELOPE_FIELDS", "RECORD_FIELDS", "SCHEMA", "ABI_NAME",
    "STATUS_REFUSED", "STATUS_OK", "STATUS_BUSY", "WP6_HOOK_STATUS",
    "inactive_width", "condition_name", "expected_condition_codes", "expected_abi_layout",
    "expected_counters_layout", "is_positive_zero", "is_negative_zero",
    "validate_condition", "validate_coefficient_record", "validate_records", "decode_payload",
    "decode_records", "decode_conditions", "require_bounded_counters", "require_bounded_result",
    "result_commitment", "content_hash_for", "run_host_emulated_frame", "decode_payload_words",
    "cross_check_against_wp6_evaluator", "wp6_evaluator_import_is_permitted",
]
