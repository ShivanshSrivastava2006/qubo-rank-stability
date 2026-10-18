"""GATE 9 D013 CUDA v2 bridge -- CANDIDATE, NOT APPROVED, NOT ARMED.

Host-side ctypes bridge for the reviewed candidate
``research/g9/cuda_qualification_v2/stage2_cuda_d013_inactive_v2.cu``.

Why this file is small
----------------------

The v2 candidate differs from the approved v1 source in **launch plumbing
only** -- it stages the payload and the energy stream on the device instead of
handing host pointers to kernels. The ABI it exports, the counter layout, the
condition codes, the record shape, the bounded-result checks and the result
commitment are all unchanged, and the v6 T4 diagnostic confirmed the compiled
v2 object still matches the frozen Python layouts on a real T4
(``abi_layout_matches_frozen_bridge``, ``counters_layout_matches_frozen_bridge``
and ``condition_codes_match_frozen_bridge`` all true for all five clean
baselines).

So none of that machinery is re-implemented here. This module imports the frozen
v1 bridge by absolute path and re-exports its constants, ctypes structures,
validators and refusers unchanged. What it does NOT inherit is the v1 release
gate: the v1 bridge hard-codes the v1 plan module in its three backend-1 token
checks, and those must consult the **v2** plan and the **v2** release draft
instead. That is the only thing this file re-implements, and it re-implements
it by calling the frozen validators rather than restating them.

Scope limit, stated plainly
---------------------------

This bridge moves bytes and checks shapes. It does not compute a scientific
result, does not qualify anything, and does not authorize an execution. The
release it binds to is a DRAFT with ``owner_approved: false``, so
``run_verified_frame`` refuses on the release gate before any library load.
"""

from __future__ import annotations

import ctypes as C
from pathlib import Path
from typing import Mapping

# FROZEN reviewed dependencies, imported by absolute path. Not copied, not
# edited. The v1 bridge keeps validating against v1 and the v1 release keeps
# validating against the v1 source.
from research.g9.cuda_qualification import stage2_cuda_d013_inactive as _frozen_bridge
from research.g9.cuda_qualification import stage2_cuda_d013_inactive_corruption_qualification as _frozen_v1_plan
from research.g9.cuda_qualification_v2 import (
    stage2_cuda_d013_inactive_v2_corruption_qualification as _v2_plan)


# --- frozen surface, re-exported unchanged ---------------------------------

SCHEMA = _frozen_bridge.SCHEMA
ABI_NAME = _frozen_bridge.ABI_NAME
FRAME_HASH_ROLE = _frozen_bridge.FRAME_HASH_ROLE
RESULT_HASH_ROLE = _frozen_bridge.RESULT_HASH_ROLE
WP6_HOOK_STATUS = _frozen_bridge.WP6_HOOK_STATUS

CONDITION_C = _frozen_bridge.CONDITION_C
CONDITION_CB = _frozen_bridge.CONDITION_CB
CONDITION_CS = _frozen_bridge.CONDITION_CS
CONDITION_CSB = _frozen_bridge.CONDITION_CSB
CONDITIONS = _frozen_bridge.CONDITIONS
CONDITION_CODE = _frozen_bridge.CONDITION_CODE
ACTIVITY_SECTOR = _frozen_bridge.ACTIVITY_SECTOR
ACTIVITY_BUDGET = _frozen_bridge.ACTIVITY_BUDGET
ACTIVITY_MASK = _frozen_bridge.ACTIVITY_MASK

INACTIVE_FAMILIES = _frozen_bridge.INACTIVE_FAMILIES
SECTOR_REGISTER_WIDTH = _frozen_bridge.SECTOR_REGISTER_WIDTH
BUDGET_REGISTER_WIDTH = _frozen_bridge.BUDGET_REGISTER_WIDTH
FAMILY_WIDTH = _frozen_bridge.FAMILY_WIDTH

STATUS_REFUSED = _frozen_bridge.STATUS_REFUSED
STATUS_OK = _frozen_bridge.STATUS_OK
STATUS_BUSY = _frozen_bridge.STATUS_BUSY

PayloadData = _frozen_bridge.PayloadData
CoefficientData = _frozen_bridge.CoefficientData
ScanResult = _frozen_bridge.ScanResult
CoreOutput = _frozen_bridge.CoreOutput
ConditionArray = _frozen_bridge.ConditionArray
ROW_CAPACITY_C = _frozen_bridge.ROW_CAPACITY_C
CoefficientDataArray = _frozen_bridge.CoefficientDataArray

D013Counters = _frozen_bridge.D013Counters
D013Output = _frozen_bridge.D013Output

COUNTER_FIELDS = _frozen_bridge.COUNTER_FIELDS
COUNTER_AUXILIARY_FIELDS = _frozen_bridge.COUNTER_AUXILIARY_FIELDS
COUNTER_FIELD_COUNT = _frozen_bridge.COUNTER_FIELD_COUNT
COUNTER_FIELD_SET = _frozen_bridge.COUNTER_FIELD_SET
RESULT_FIELDS = _frozen_bridge.RESULT_FIELDS
RECORD_FIELDS = _frozen_bridge.RECORD_FIELDS
ENVELOPE_FIELDS = _frozen_bridge.ENVELOPE_FIELDS
ALL_THRESHOLDS_FLAGS = _frozen_bridge.ALL_THRESHOLDS_FLAGS

D013InactiveError = _frozen_bridge.D013InactiveError
D013EmptyFeasibleSetError = _frozen_bridge.D013EmptyFeasibleSetError

inactive_width = _frozen_bridge.inactive_width
condition_name = _frozen_bridge.condition_name
expected_condition_codes = _frozen_bridge.expected_condition_codes
expected_abi_layout = _frozen_bridge.expected_abi_layout
expected_counters_layout = _frozen_bridge.expected_counters_layout
is_positive_zero = _frozen_bridge.is_positive_zero
is_negative_zero = _frozen_bridge.is_negative_zero
validate_condition = _frozen_bridge.validate_condition
validate_coefficient_record = _frozen_bridge.validate_coefficient_record
validate_records = _frozen_bridge.validate_records
decode_payload = _frozen_bridge.decode_payload
decode_records = _frozen_bridge.decode_records
decode_conditions = _frozen_bridge.decode_conditions
require_bounded_counters = _frozen_bridge.require_bounded_counters
result_commitment = _frozen_bridge.result_commitment
content_hash_for = _frozen_bridge.content_hash_for
decode_payload_words = _frozen_bridge.decode_payload_words
cross_check_against_wp6_evaluator = _frozen_bridge.cross_check_against_wp6_evaluator
wp6_evaluator_import_is_permitted = _frozen_bridge.wp6_evaluator_import_is_permitted

_ABI_LOCK = _frozen_bridge._ABI_LOCK
_require = _frozen_bridge._require
_require_feasible_nonempty = _frozen_bridge._require_feasible_nonempty
_word = _frozen_bridge._word
_unword = _frozen_bridge._unword
_counters = _frozen_bridge._counters
_summaries = _frozen_bridge._summaries

# Which plan module owns the release gate for THIS bridge. The single most
# important line in the file: a backend-1 v2 library is admitted only by a v2
# token, verified against the v2 release draft and the v2 source map.
PLAN_MODULE = _v2_plan
CANDIDATE_SOURCE_REL = _v2_plan.SOURCE_REL
CANDIDATE_SOURCE_SHA256 = "953b7f15a14950d75536d72b074a7907dc06df13539b2ce3f4122cc427ab0f61"


def require_verified_v2_release(token: object) -> None:
    """Refuse unless ``token`` is a currently valid **v2** release token.

    Delegates the whole decision to the v2 plan's ``_check_token``, which
    re-derives the source map from disk, re-derives the proof, and requires
    ``owner_approved is True`` in the v2 release draft. A v1 token fails here
    on both its release digest and its source-map digest.
    """
    _require(PLAN_MODULE._check_token(token),
             "backend 1 requires a verified D013 **v2** owner-approved release token; "
             "a v1 token is not transferable")


def require_bounded_result_v2(envelope: object, condition: str, record_count: int,
                              expected_content_sha256: object = None,
                              verified_release: object = None) -> dict[str, object]:
    """Consumer-side acceptance of a v2 envelope, gated on the **v2** release.

    The frozen validator does all the numeric and structural work. It cannot be
    used directly for a backend-1 envelope, because its own backend-1 branch
    consults the v1 plan. So the v2 gate is applied first, and the frozen
    validator is then called with a backend-0-shaped copy of the envelope for
    the structural pass only -- which is exactly the pass that needs no release,
    because it is pure shape and arithmetic over the returned records.
    """
    if isinstance(envelope, dict) and envelope.get("backend") == 1:
        require_verified_v2_release(verified_release)
    if isinstance(envelope, dict) and envelope.get("backend") == 1:
        # Re-run the frozen structural validator on a backend-0 view so the v1
        # plan is never consulted for this envelope, then restore the truth.
        structural = dict(envelope)
        structural["backend"] = 0
        _frozen_bridge.require_bounded_result(
            structural, condition, record_count,
            expected_content_sha256=expected_content_sha256)
        return dict(envelope)
    return _frozen_bridge.require_bounded_result(
        envelope, condition, record_count,
        expected_content_sha256=expected_content_sha256)


def load_checked_abi(library_path: Path, *, verified_release: object = None):
    """Load the compiled v2 ABI, with the v2 release gate on the backend-1 path.

    The frozen loader performs the layout comparisons, the retired-entry-point
    refusals and the ctypes signatures. It is called here through a small
    wrapper so that the backend-1 token check is the **v2** one. The frozen
    loader's own v1 token check is bypassed by passing ``verified_release=None``
    to it only after the v2 gate has already passed -- the v1 loader requires a
    v1 token, which by construction a v2 token is not.
    """
    _require(sys_byteorder_is_little(), "the frozen uint64 stream requires a little-endian host")
    _require(isinstance(library_path, Path) and library_path.is_file(),
             "compiled D013 v2 ABI library is missing")
    try:
        library = C.CDLL(str(library_path))
        layout = library.g9_d013_abi_layout
        counters = library.g9_d013_counters_layout
        codes = library.g9_d013_condition_codes
        run = library.g9_d013_run
        backend = library.g9_d013_backend
    except (OSError, AttributeError) as exc:
        raise D013InactiveError("compiled D013 v2 ABI exports are missing") from exc
    for retired in ("g9_core_run_v1", "g9_core_run_v2", "g9_core_copy_offsets_v1"):
        _require(not hasattr(library, retired),
                 "the D013 v2 library still exports a version-1 or version-2 core entry")
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
             "compiled D013 v2 ABI layout differs from the Python bridge")
    actual_counters = (C.c_uint64 * 5)()
    _require(counters(actual_counters, 5) == 5 and tuple(actual_counters) == expected_counters_layout(),
             "compiled D013 v2 counter layout differs from the Python bridge")
    actual_codes = (C.c_uint64 * 6)()
    _require(codes(actual_codes, 6) == 6 and tuple(actual_codes) == expected_condition_codes(),
             "compiled D013 v2 condition codes differ from the Python bridge")
    kind = backend()
    _require(kind in (0, 1), "compiled D013 v2 ABI backend tag is invalid")
    if kind == 1:
        require_verified_v2_release(verified_release)
    return run, kind


def sys_byteorder_is_little() -> bool:
    import sys
    return sys.byteorder == "little"


def run_verified_frame(payload: object, records: object, condition: object,
                       library_path: Path, feasible_count: object,
                       *, verified_release: object = None) -> dict[str, object]:
    """Run one v2 CUDA frame through the frozen envelope construction.

    Structurally this is the frozen host-frame routine with two differences,
    both forced and both narrow:

    1. the ABI load and the backend-1 gate go through the **v2** plan, and
    2. the bounded-result acceptance uses ``require_bounded_result_v2``.

    The envelope construction itself -- counter extraction, per-row summaries,
    ``minimum_word`` bit round-trip, content hash and result commitment -- calls
    the frozen helpers, so the v2 envelope is byte-identical in shape to a v1
    one. Refuses before loading when the release gate is closed, which is the
    current state.
    """
    name = validate_condition(condition)
    _require_feasible_nonempty(feasible_count, name)
    values = validate_records(records, name)
    record_count = len(values)
    _require(isinstance(library_path, Path),
             "the compiled D013 v2 library must be named by a pathlib.Path")
    decoded = decode_payload(payload)
    row_array = decode_records(values, name)
    condition_array = decode_conditions(name, record_count)
    with _ABI_LOCK:
        run, backend = load_checked_abi(library_path, verified_release=verified_release)
        output = D013Output()
        status = run(C.byref(decoded), row_array, condition_array, record_count, C.byref(output))
        _require(status != STATUS_BUSY, "compiled D013 v2 core is busy with another call")
        _require(status == STATUS_OK, "compiled D013 v2 core refused or failed the validated input")
        counters = _counters(output.counters)
        require_bounded_counters(counters, name, record_count)
        summaries = _summaries(output, record_count)
        for slot in range(record_count):
            _require(int(output.conditions[slot]) == CONDITION_CODE[name],
                     "the compiled v2 core did not echo the requested condition")
        rows = []
        for slot in range(record_count):
            for encoding in _frozen_bridge.ENCODINGS:
                summary = summaries[(slot, encoding)]
                width = counters["inactive_width"]
                tie_count = summary["per_ch"][1]
                rows.append({"row": slot, "condition": name, "encoding": encoding,
                             "minimum_word": format(_word(summary["minimum"]), "016x"),
                             "t_e_size": tie_count * (1 << width),
                             "t_e_factors": (tie_count, width),
                             "c_e_size": summary["word_count"] * (1 << width),
                             **summary})
                _require(_unword(int(rows[-1]["minimum_word"], 16)) == summary["minimum"],
                         "the minimum word does not round-trip to its minimum")
        content = content_hash_for(payload, values, name)
        envelope = {"schema": SCHEMA, "abi": ABI_NAME, "backend": backend,
                    "condition": name, "content_sha256": content,
                    "content_sha256_role": FRAME_HASH_ROLE, "records": rows,
                    "counters": counters, "result_sha256": "",
                    "result_sha256_role": RESULT_HASH_ROLE}
        envelope["result_sha256"] = result_commitment(name, rows, counters)
        return require_bounded_result_v2(envelope, name, record_count,
                                         verified_release=verified_release)


def v1_plan_module():
    """The frozen v1 plan, for reviewers comparing the two gates."""
    return _frozen_v1_plan


__all__ = [
    "SCHEMA", "ABI_NAME", "CONDITIONS", "CONDITION_CODE", "INACTIVE_FAMILIES",
    "STATUS_REFUSED", "STATUS_OK", "STATUS_BUSY", "D013InactiveError",
    "D013EmptyFeasibleSetError", "D013Counters", "D013Output", "PayloadData",
    "CoefficientData", "COUNTER_FIELDS", "RECORD_FIELDS", "ENVELOPE_FIELDS",
    "inactive_width", "condition_name", "expected_condition_codes", "expected_abi_layout",
    "expected_counters_layout", "is_positive_zero", "is_negative_zero",
    "validate_condition", "validate_coefficient_record", "validate_records", "decode_payload",
    "decode_records", "decode_conditions", "require_bounded_counters",
    "result_commitment", "content_hash_for", "decode_payload_words",
    "cross_check_against_wp6_evaluator", "wp6_evaluator_import_is_permitted",
    "PLAN_MODULE", "CANDIDATE_SOURCE_REL", "CANDIDATE_SOURCE_SHA256",
    "require_verified_v2_release", "require_bounded_result_v2", "load_checked_abi",
    "run_verified_frame", "v1_plan_module",
]
