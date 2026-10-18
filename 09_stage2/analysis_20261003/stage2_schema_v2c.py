"""Frozen census, file layout and record reader for the G9 Stage-2 analysis pipeline.

This module is the SINGLE place where the Stage-2 per-slot census, the on-disk
production layout, and the record schema are declared.  `verify_outputs_v2.py`,
`analyze_stage2_v2.py`, `render_paper_slots_v2.py` and the MOCK harness all import
from here, so a census can never disagree between the verifier and the analysis.

It imports NOTHING from the project.  It reads bytes and hashes only.  Every
constant below carries the frozen source citation it was derived from.

--------------------------------------------------------------------------
WHERE THE NUMBERS COME FROM (every one derived from code, never assumed)
--------------------------------------------------------------------------

The five production kernels are the packaged v2 kernels under
`g9_jobs/push/g9-real-production-slot-N-<tag>-v2/`.  Each runs
`full_production_parent_v2.run_full_parent`
(`operational/prodfix_v2_20261003/full_production_parent_v2.py:40`), which:

  * runs the six baseline families via
    `production_parent_v2.run_actual_baseline_parent`
    (`operational/prodfix_v2_20261003/production_parent_v2.py:142`), streaming
    through `wp8c_streaming_session_v3_gzip.run_production_session_v3`
    (`scratch/production-package-prep/wp8c_streaming_session_v3_gzip.py:121`);
  * writes, per family, into `<instance_dir>/sweep/<family.key>/`
    (`wp8c_streaming_session_v3_gzip.py:232-235`): the sealed `range_plan.json`,
    one promoted `ranges/<batch_id>/{records.json,RANGE_MANIFEST.json}` per
    sealed range, and one `full_records/<batch_id>.jsonl.gz` per sealed range;
  * then extracts the D013 trigger from the primary streams
    (`full_production_parent_v2.py:86-88`).

Per-slot census derivation
--------------------------

| family key                              | coordinates | sealed ranges | source of the axis length                  |
|-----------------------------------------|-------------|---------------|--------------------------------------------|
| `primary__primary__r0x1_0000000000000p-1`          | 226,981     | 56            | `src/g5/core_pass.py:43-44` (`R_VALUES`, `ROW_COUNT=61`) |
| `primary__primary__r0x1_0000000000000p_0`          | 226,981     | 56            | same                                        |
| `primary__primary__r0x1_0000000000000p_1`          | 226,981     | 56            | same                                        |
| `d011__d011__r0x1_0000000000000p_0`     | 2,197       | 1             | `src/g6/d011_matched_subgrid.py:52-54` (`13**3`) |
| `v14__v14_0_5x__r0x1_0000000000000p_0` | 29,791      | 8             | `src/g6/ledgers.py:290` (`N_axis = 31`)   |
| `v14__v14_2x__r0x1_0000000000000p_0`   | 1,367,631   | 334           | `src/g6/ledgers.py:291` (`N_axis = 111`)  |

  * `226981 = 61**3` (`src/g5/core_pass.py:44`).
  * `2197 = 13**3` (`src/g6/d011_matched_subgrid.py:54`).
  * `29791 = 31**3`, `1367631 = 111**3` (`src/g6/ledgers.py:290-291`; asserted
    again at `research/g9/stage2_section_b2_harness.py:164`).
  * The sealed range partition is `MAX_COORDINATES_PER_RANGE = 4096`
    (`research/g9/cuda_qualification/stage2_cuda_execution_contract.py:19`),
    applied by `build_range_plan` (`:112-132`), so the sealed-range count is
    `ceil(total / 4096)`.
  * **Per-slot row total = 2,080,562** = 3*226981 + 2197 + 29791 + 1367631.
    This is the census independently reached and stated in
    `operational/xcheck_20261003/XCHECK_NOTES.md:223-229`, which also corrects
    an earlier 1,361,886 understatement in `prodfix_v2_20261003/FIXES.md:139`.
  * **Sealed ranges per slot = 511** (56*3 + 1 + 8 + 334).
  * **CUDA batch flushes per slot = 1,040,281** = 2,080,562 / 2, because
    `ROW_CAPACITY = 2`
    (`research/g9/cuda_qualification/stage2_cuda_core_bridge.py:22`) and the
    producer flushes whenever a batch is full
    (`scratch/production-package-prep/production_cuda_runner_v6.py:232-243`).
    This is the `1,040,281` of `XCHECK_NOTES.md:231`.  It is a *runtime* count,
    NOT an on-disk artefact: the sealed plan partitions at 4096, so the number
    of promoted range directories on disk is 511, not 1,040,281.  Both are
    reported, distinctly named, so neither is mistaken for the other.

--------------------------------------------------------------------------
WHAT IS *NOT* HERE
--------------------------------------------------------------------------

This module declares no scientific quantity.  It declares layout, census and
schema only.  Every number that reaches a paper table or figure is computed by
`analyze_stage2_v2.py`, and every one of those cites a frozen spec line.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

# ---------------------------------------------------------------------------
# Frozen census
# ---------------------------------------------------------------------------

MAX_COORDINATES_PER_RANGE = 4096
"""`stage2_cuda_execution_contract.py:19`."""

ROW_CAPACITY = 2
"""`stage2_cuda_core_bridge.py:22` — the CUDA batch capacity, hence the
flush count; it is not an on-disk artefact count."""

#: `family key -> (axis length, coordinate count, provenance citation)`.
#: The axis length is carried explicitly rather than re-derived from the
#: coordinate count, because the canonical linear order
#: (`stage2_coordinate_records.CoordinateSpace._strides:397-402`) depends on it
#: and it differs per family: 61 primary, 13 D011, 31 / 111 V-14.
FAMILY_CENSUS: dict[str, tuple[int, int, str]] = {
    "primary__primary__r0x1_0000000000000p-1": (
        61, 226_981, "src/g5/core_pass.py:43-44 (R_VALUES, ROW_COUNT=61) -> 61**3"),
    "primary__primary__r0x1_0000000000000p_0": (
        61, 226_981, "src/g5/core_pass.py:43-44 (R_VALUES, ROW_COUNT=61) -> 61**3"),
    "primary__primary__r0x1_0000000000000p_1": (
        61, 226_981, "src/g5/core_pass.py:43-44 (R_VALUES, ROW_COUNT=61) -> 61**3"),
    "d011__d011__r0x1_0000000000000p_0": (
        13, 2_197,
        "src/g6/d011_matched_subgrid.py:52-54 (MATCHED_COORDINATE_COUNT=13**3)"),
    "v14__v14_0_5x__r0x1_0000000000000p_0": (
        31, 29_791, "src/g6/ledgers.py:290 (N_axis=31) -> 31**3"),
    "v14__v14_2x__r0x1_0000000000000p_0": (
        111, 1_367_631, "src/g6/ledgers.py:291 (N_axis=111) -> 111**3"),
}

#: `Family.r_hex` for each family (`stage2_coordinate_records.py:379-380`).
#: The primary `r` values are `(0.5, 1.0, 2.0)` (`src/g5/core_pass.py:43`);
#: D011 and both V-14 companions are `r = 1` readings
#: (`stage2_coordinate_records.py:466, 472`), whose binary64 hex is the literal
#: pinned as `PRIMARY_R_HEX` (`:158`).
FAMILY_R_HEX: dict[str, str] = {
    "primary__primary__r0x1_0000000000000p-1": "0x1.0000000000000p-1",
    "primary__primary__r0x1_0000000000000p_0": "0x1.0000000000000p+0",
    "primary__primary__r0x1_0000000000000p_1": "0x1.0000000000000p+1",
    "d011__d011__r0x1_0000000000000p_0": "0x1.0000000000000p+0",
    "v14__v14_0_5x__r0x1_0000000000000p_0": "0x1.0000000000000p+0",
    "v14__v14_2x__r0x1_0000000000000p_0": "0x1.0000000000000p+0",
}

#: The six sealed baseline families, in the order `records.families(False)`
#: declares them (`research/g9/stage2_coordinate_records.py:511-526`).
BASELINE_FAMILIES: tuple[str, ...] = tuple(FAMILY_CENSUS)

#: `Family.group` for each baseline family, read off the key itself.
FAMILY_GROUP: dict[str, str] = {
    "primary__primary__r0x1_0000000000000p-1": "primary",
    "primary__primary__r0x1_0000000000000p_0": "primary",
    "primary__primary__r0x1_0000000000000p_1": "primary",
    "d011__d011__r0x1_0000000000000p_0": "d011",
    "v14__v14_0_5x__r0x1_0000000000000p_0": "v14",
    "v14__v14_2x__r0x1_0000000000000p_0": "v14",
}

#: The three primary `r` values as the binary64 hex the records carry.
#: `Family.r_hex` (`stage2_coordinate_records.py:379-380`) and
#: `PRIMARY_R_HEX` (`:158`).
PRIMARY_R_HEX: tuple[str, ...] = ("0x1.0000000000000p-1",
                                  "0x1.0000000000000p+0",
                                  "0x1.0000000000000p+1")

PRIMARY_R_DISPLAY: dict[str, str] = {
    "0x1.0000000000000p-1": "0.5",
    "0x1.0000000000000p+0": "1.0",
    "0x1.0000000000000p+1": "2.0",
}

ENCODINGS: tuple[str, str] = ("slack", "unbalanced")
"""`reconstruct_pair` iterates exactly `("unbalanced", "slack")`
(`research/g9/cuda_qualification/stage2_cuda_reconstruct.py:235`); the paper's
paired-encoding rule wants slack displayed first
(`project/paper/RESULTS_AND_FIGURE_SLOTS.md:41-43`)."""

PRIMARY_COORDINATE_COUNT = 226_981
"""61**3 — `src/g5/core_pass.py:44`."""

AXIS_LENGTH = 61
"""`src/g5/core_pass.py:44` (`ROW_COUNT`)."""

SLOT_NAMES: tuple[str, ...] = ("stage2_01", "stage2_02", "stage2_03",
                               "stage2_04", "stage2_05")
"""`research/g9/wp8d/wp8d_drawn_instance_layout.py:327`."""

INSTANCE_ROOT = "research/g9/stage2_instances"
"""`research/g9/wp8d/wp8d_drawn_instance_layout.py:321`."""


def sealed_range_count(total_coordinates: int) -> int:
    """Ranges in the sealed plan: `ceil(total / MAX_COORDINATES_PER_RANGE)`."""
    if type(total_coordinates) is not int or total_coordinates < 1:
        raise ValueError("total_coordinates must be a positive int")
    return -(-total_coordinates // MAX_COORDINATES_PER_RANGE)


PER_SLOT_ROWS = sum(count for _axis, count, _citation in FAMILY_CENSUS.values())
PER_SLOT_SEALED_RANGES = sum(sealed_range_count(count)
                             for _axis, count, _citation in FAMILY_CENSUS.values())
# v2c LEAD FIX 2026-10-04: production batches rows per family (cuda_range_producer per family
# space), so flushes = sum over families of ceil(count/ROW_CAPACITY), not ceil(total/ROW_CAPACITY).
PER_SLOT_CUDA_FLUSHES = sum(-(-count // ROW_CAPACITY) for _axis, count, _citation in FAMILY_CENSUS.values())

#: Fail at import time if the derivation ever stops matching the recorded
#: figures.  A silent drift here would silently change the census.
assert PER_SLOT_ROWS == 2_080_562, PER_SLOT_ROWS
assert PER_SLOT_SEALED_RANGES == 511, PER_SLOT_SEALED_RANGES
assert PER_SLOT_CUDA_FLUSHES == 1_040_284, PER_SLOT_CUDA_FLUSHES


# ---------------------------------------------------------------------------
# On-disk layout
# ---------------------------------------------------------------------------

PLAN_NAME = "range_plan.json"
RANGES_DIRNAME = "ranges"
RECORDS_NAME = "records.json"
RANGE_MANIFEST_NAME = "RANGE_MANIFEST.json"
FULL_RECORDS_DIRNAME = "full_records"

"""All five from `research/g9/stage2_production_writer.py:122-125` plus
`_persist_full`'s `'full_records'` directory
(`scratch/production-package-prep/wp8c_streaming_session_v3_gzip.py:48`)."""

RANGE_PLAN_SCHEMA = "decisions_os/g9_cuda_stage2_range_plan/v1"
RANGE_MANIFEST_SCHEMA = "decisions_os/g9_cuda_stage2_range_manifest/v1"
"""`stage2_cuda_execution_contract.py:13-14`."""

RECORD_SCHEMA = "decisions_os/g9_stage2_coordinate_record/v1"
"""`research/g9/stage2_coordinate_records.py:154`."""

SESSION_SCHEMA = "decisions_os/g9_streaming_production_session/v3"
"""`wp8c_streaming_session_v3_gzip.py:254, 264, 283`."""

SESSION_STATE_SCHEMA = "decisions_os/g9_wp8c_session_state/v1"
"""`research/g9/wp8c_production/wp8c_production_session.py:150`."""

SESSION_STATE_NAME = ".wp8c_session_{slot_name}.json"
"""`wp8c_production_session.session_state_path:406-408`: the per-slot
one-use session registry lives at `<staged>/research/g9/stage2_instances/`
(i.e. the PARENT of the slot tree), NOT inside it.  One file per slot, named
for the slot."""

BASELINE_COMPLETE_STATUS = "baseline_complete_pending_D013_trigger_and_image_audit"
"""`production_parent_v2.py:71, 372`."""

FULL_COMPLETE_STATUS = "full_computation_complete_pending_final_audit"
"""`full_production_parent_v2.py:89, 147`."""

PARTIAL_STATUSES = ("baseline_refused_or_partial",)
"""`production_parent_v2.py:72, 374`."""

#: The five top-level artefacts the kernel writes into `/kaggle/working/`
#: (`scratch/production-package-prep/...` bootstrap, as shipped in
#: `g9_jobs/push/g9-real-production-slot-*/kernel.py` line 56 and the
#: `operational/` retains inside `full_production_parent_v2.py:68, 88, 97, 118`).
RESULT_NAME = "FULL_PRODUCTION_RESULT.json"
FAILURE_NAME = "FULL_PRODUCTION_FAILURE.json"
INCOMPLETE_NAME = "FULL_PRODUCTION_INCOMPLETE_BUDGET.json"

BASELINE_RECEIPT_REL = "operational/BASELINE_RECEIPT.json"
D013_TRIGGER_REL = "operational/D013_TRIGGER.json"
D013_DECLARATION_REL = "operational/D013_PROSPECTIVE_DECLARATION.json"
D013_GROUND_TRUTH_REL = "operational/D013_CONDITION_GROUND_TRUTH.json"
D013_WP3_REL = "operational/D013_WP3_RECORD.json"
CONDITIONAL_SESSION_RECEIPT_NAME = "CONDITIONAL_SESSION_RECEIPT.json"

D013_CONDITIONS: tuple[str, ...] = ("C", "CB", "CS", "CSB")
"""`research/g9/stage2_coordinate_records.py:167` and
`research/decisions/DECISIONS.md:1106-1111`."""

#: The `Delta(r)` cells the trigger consumes, exactly.
TRIGGER_R_HEX: tuple[str, ...] = PRIMARY_R_HEX
"""`research/decisions/DECISIONS.md:1120-1124`: `Delta_i(r)` for
`r in {0.5, 1, 2}`, i.e. the three primary `r` values and no other."""

D013_DECLARED_FAMILY_COUNT = 22
"""`full_production_parent_v2.py:67, 146`: 4 conditions x (1 active + 3
companions) = 16 D013 families, plus the 6 baseline families = 22."""

MOCK_LABEL = "MOCK"
"""Every mock artefact and every rendered caption carries this token."""

#: The default MOCK sealed partition width.  The coordinate census is NEVER
#: parameterised — it stays the real 2,080,562 per slot — so this changes only
#: the number of promoted range DIRECTORIES, never a row count.  Passing the
#: real `MAX_COORDINATES_PER_RANGE` reproduces the exact real on-disk shape
#: (about 8 GB of tree for five slots).
MOCK_RECORDS_PER_RANGE = 32768

#: The shipped frozen census profile.  It is a FILE, not a constant, so that a
#: run always names the exact census it checked against by SHA-256 and the
#: frozen one can never be edited in place to match whatever happened to
#: arrive.  `verify_outputs_v2.py` defaults to it.
FROZEN_CENSUS_NAME = "FROZEN_CENSUS_v2.json"
MOCK_CENSUS_NAME = "MOCK_CENSUS_v2.json"
CENSUS_SCHEMA = "decisions_os/g9_stage2_census_profile/v1"


def _integer_cube_root(value: int) -> int:
    """The largest `n` with `n**3 <= value`, by integer arithmetic only."""
    if value < 1:
        return 1
    low, high = 1, 1
    while high ** 3 <= value:
        high *= 2
    while low + 1 < high:
        middle = (low + high) // 2
        if middle ** 3 <= value:
            low = middle
        else:
            high = middle
    return low


def build_census_profile(records_per_range: int,
                         families: dict[str, tuple[int, int, str]],
                         label: str, scale: int = 1) -> dict[str, Any]:
    """Derive a census profile from a family table.

    Two knobs, and they are deliberately SEPARATE so neither can be used to
    disguise the other:

    * `records_per_range` — the sealed partition WIDTH.  It changes only the
      number of promoted range directories, never a row count.  Setting it to
      the real `MAX_COORDINATES_PER_RANGE` reproduces the exact real on-disk
      shape (about 1.4 GB and 15 minutes per slot).
    * `scale` — shrinks each family's AXIS, and the coordinate count becomes
      the exact cube of that axis.  This DOES change the row census, so a
      profile built with `scale > 1` is never the frozen census
      (`is_frozen_census` returns False), and every artefact produced under it
      is labelled MOCK by the analyzer.  It exists because the real census is
      2,080,562 records per slot and a full-scale mock tree is neither
      storable nor generatable on the review host.

    The axis is scaled, NOT the count, and the count is then recomputed as
    `axis**3`.  That keeps the lattice a genuine cube: a truncated coordinate
    count that is not a perfect cube would make the canonical last-axis-fastest
    order (`stage2_coordinate_records.py:82-89`) unsatisfiable for the linear
    indices past the last whole cube, and every such record would be refused.
    """
    scaled: dict[str, tuple[int, int, str]] = {}
    for key, (axis, count, citation) in families.items():
        new_axis = max(1, _integer_cube_root(max(1, count // scale)))
        scaled[key] = (new_axis, new_axis ** 3, citation)
    profile = {
        "schema": CENSUS_SCHEMA,
        "label": label,
        "records_per_range": records_per_range,
        "max_coordinates_per_range": records_per_range,
        "row_capacity": ROW_CAPACITY,
        "scale": scale,
        "family_census": {
            key: {"axis_length": axis, "coordinates": count,
                  "sealed_ranges": -(-count // records_per_range),
                  "citation": citation}
            for key, (axis, count, citation) in sorted(scaled.items())},
    }
    profile["per_slot_rows"] = sum(count for _a, count, _c in scaled.values())
    profile["per_slot_sealed_ranges"] = sum(
        -(-count // records_per_range) for _a, count, _c in scaled.values())
    profile["per_slot_cuda_flushes"] = -(-profile["per_slot_rows"] // ROW_CAPACITY)
    profile["content_sha256"] = content_sha256(profile)
    return profile


def load_census_profile(path: Path) -> dict[str, Any]:
    """Read a census profile and re-derive its own hash.

    A census profile is CONFIGURATION, not evidence: it says what to expect,
    and it is refused unless it is internally consistent (every family's
    coordinate count is a positive int, its sealed-range count is
    `ceil(n / records_per_range)`, and the totals are their sums).  The report
    always records the profile's SHA-256 so the expectation is auditable, and
    always records whether it IS the frozen real census.
    """
    profile = read_sealed(path, f"census profile {path.name}")
    _require(profile["schema"] == CENSUS_SCHEMA,
             f"census profile schema is {profile['schema']!r}, not "
             f"{CENSUS_SCHEMA!r}")
    per_range = profile["records_per_range"]
    _require(type(per_range) is int and per_range >= 1,
             "census profile records_per_range must be a positive int")
    families = profile["family_census"]
    _require(isinstance(families, dict) and families,
             "census profile carries no family census")
    total_rows = 0
    total_ranges = 0
    for key, entry in families.items():
        _require(isinstance(entry, dict)
                 and set(entry) == {"axis_length", "coordinates",
                                    "sealed_ranges", "citation"},
                 f"census profile family {key!r} has the wrong shape")
        count = entry["coordinates"]
        _require(type(count) is int and count >= 1,
                 f"census profile family {key!r} coordinates is not a positive int")
        _require(entry["sealed_ranges"] == -(-count // per_range),
                 f"census profile family {key!r} declares "
                 f"{entry['sealed_ranges']} sealed ranges but "
                 f"ceil({count}/{per_range}) is {-(-count // per_range)}")
        total_rows += count
        total_ranges += entry["sealed_ranges"]
    _require(profile["per_slot_rows"] == total_rows,
             f"census profile per_slot_rows is {profile['per_slot_rows']} but "
             f"its families sum to {total_rows}")
    _require(profile["per_slot_sealed_ranges"] == total_ranges,
             f"census profile per_slot_sealed_ranges is "
             f"{profile['per_slot_sealed_ranges']} but its families sum to "
             f"{total_ranges}")
    _require(profile["per_slot_cuda_flushes"] == sum(-(-entry["coordinates"] // ROW_CAPACITY) for entry in profile["family_census"].values()),
             "census profile per_slot_cuda_flushes disagrees with per-family ROW_CAPACITY batching")
    return profile


def is_frozen_census(profile: dict[str, Any]) -> bool:
    """True iff the profile IS the frozen real census.

    Compared field by field against the module constants, not by label, so
    relabelling a mock profile as frozen does not pass.
    """
    return (profile["records_per_range"] == MAX_COORDINATES_PER_RANGE
            and profile["per_slot_rows"] == PER_SLOT_ROWS
            and profile["per_slot_sealed_ranges"] == PER_SLOT_SEALED_RANGES
            and profile["per_slot_cuda_flushes"] == PER_SLOT_CUDA_FLUSHES
            and set(profile["family_census"]) == set(FAMILY_CENSUS)
            and all(profile["family_census"][key]["coordinates"] == count
                    and profile["family_census"][key]["axis_length"] == axis
                    for key, (axis, count, _c) in FAMILY_CENSUS.items()))


class Stage2AnalysisError(RuntimeError):
    """A frozen input is missing, altered, or semantically inconsistent."""


def _require(ok: Any, message: str) -> None:
    if not ok:
        raise Stage2AnalysisError(message)


# ---------------------------------------------------------------------------
# Canonical encodings — must match production byte for byte
# ---------------------------------------------------------------------------

def canonical_bytes(value: Any) -> bytes:
    """The committable canonical encoding.

    Byte-identical to
    `research/g9/stage2_sampled_verification.canonical`
    (`stage2_sampled_verification.py:196-203`) and to `_canonical` in
    `wp8c_streaming_session_v3_gzip.py:43-44`.  Its allowlist is
    `None | bool | int | str | list | dict` (`:176`): a **bool IS committable**
    (the per-family coefficient `active` flags are bools, e.g.
    `stage2_coordinate_records.py:731`) but a **float is not** — every binary64
    value must already be a hex string (`:187-190`).  A float reaching here is
    refused rather than serialised.
    """
    _check_encodable(value, "$")
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise Stage2AnalysisError(f"value is not canonically encodable: {exc}") from None


_LEAF_TYPES = (bool, int, str)
_SCALARS = frozenset((type(None), bool, int, str))


def _check_encodable(value: Any, path: str) -> None:
    """The record-layer allowlist: no floats, no tuples, no subclasses.

    Iterative with an explicit stack rather than recursive.  This runs on every
    one of the 2,080,562 committed records per slot, so the recursion-per-leaf
    cost is real; the stack below is the same check with one call per CONTAINER
    instead of one per leaf.

    A `bool` IS committable — the per-family coefficient `active` flags are
    bools (`stage2_coordinate_records.py:731`) — but a `float` is NOT: every
    binary64 value must already be a hex string
    (`stage2_sampled_verification.py:187-190`).
    """
    stack: list[tuple[Any, str]] = [(value, path)]
    while stack:
        node, here = stack.pop()
        kind = type(node)
        if kind in _SCALARS:
            continue
        if kind is dict:
            for key, item in node.items():
                if type(key) is not str:
                    raise Stage2AnalysisError(f"non-string key at {here}")
                if type(item) in (dict, list):
                    stack.append((item, f"{here}.{key}"))
                elif type(item) not in _SCALARS:
                    _refuse_leaf(item, f"{here}.{key}")
            continue
        if kind is list:
            for index, item in enumerate(node):
                if type(item) in (dict, list):
                    stack.append((item, f"{here}[{index}]"))
                elif type(item) not in _SCALARS:
                    _refuse_leaf(item, f"{here}[{index}]")
            continue
        _refuse_leaf(node, here)


def _refuse_leaf(value: Any, path: str) -> None:
    """Name the offending leaf precisely.  Never reached for a valid record."""
    if isinstance(value, float):
        raise Stage2AnalysisError(
            f"float-valued object at {path}: a committed record encodes "
            "binary64 as a hex string, never as a JSON float "
            "(stage2_sampled_verification.py:176-193)")
    raise Stage2AnalysisError(
        f"type {type(value).__name__} at {path} is not committable; "
        "allowed: None, bool, int, str, list, dict "
        "(stage2_sampled_verification.py:176-193)")


def _check_no_float_or_bool(value: Any, path: str) -> None:
    """The STRICTER control-plane rule, for range plans and range manifests.

    `stage2_cuda_execution_contract._no_float_or_bool` (`:48-58`) refuses bool
    leaves too, on top of floats.  It applies to the sealed control-plane
    documents only, never to a committed record — the two rules are different
    and conflating them would either reject a valid record or admit a
    re-partitioned plan.
    """
    stack: list[tuple[Any, str]] = [(value, path)]
    while stack:
        node, here = stack.pop()
        kind = type(node)
        if kind in _SCALARS:
            continue
        if kind in (dict, list):
            items = node.items() if kind is dict else enumerate(node)
            for key, item in items:
                if kind is dict and type(key) is not str:
                    raise Stage2AnalysisError(f"non-string key at {here}")
                if type(item) in (dict, list):
                    stack.append((item, f"{here}.{key}"))
                elif type(item) not in _SCALARS:
                    raise Stage2AnalysisError(
                        f"control-plane document carries a "
                        f"{type(item).__name__} leaf at {here}.{key}; range "
                        "plans and range manifests admit neither "
                        "(stage2_cuda_execution_contract.py:48-58)")
            continue
        raise Stage2AnalysisError(
            f"control-plane document carries a {kind.__name__} at {here}; "
            "range plans and range manifests admit neither float nor bool "
            "(stage2_cuda_execution_contract.py:48-58)")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_sha256(value: dict[str, Any]) -> str:
    """`stage2_cuda_execution_contract.content_sha256` (`:38-40`) and
    `wp8c_production_session._seal` (`:324-328`): the digest over the document
    with its own `content_sha256` field removed."""
    body = dict(value)
    body.pop("content_sha256", None)
    return sha256_hex(canonical_bytes(body))


def read_json(path: Path, label: str) -> tuple[bytes, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise Stage2AnalysisError(f"{label} is unreadable: {exc}") from None
    try:
        return raw, json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Stage2AnalysisError(f"{label} is not ASCII JSON: {exc}") from None


def read_sealed(path: Path, label: str) -> dict[str, Any]:
    """Read a document and re-derive its own `content_sha256`.

    The digest is RECOMPUTED from the body, never read and trusted, so an
    edited document that kept its old hash is refused
    (`stage2_cuda_execution_contract.validate_range_plan:135-144`,
    `validate_final_manifests:181`).
    """
    _raw, payload = read_json(path, label)
    _require(isinstance(payload, dict), f"{label} is not an object")
    claimed = payload.get("content_sha256")
    _require(isinstance(claimed, str) and len(claimed) == 64
             and all(c in "0123456789abcdef" for c in claimed),
             f"{label} carries no lowercase SHA-256 content_sha256")
    _require(content_sha256(payload) == claimed,
             f"{label} content_sha256 does not match its own body")
    return payload


def read_prepared_metadata(path: Path, label: str) -> dict[str, Any]:
    """WP8d/WP5 preparation metadata uses canonical JSON with finite floats.

    This is deliberately separate from the coordinate record encoder.
    See wp8d_drawn_instance_layout._canonical and production_parent_v2.canonical.
    """
    _raw, payload = read_json(path, label)
    _require(isinstance(payload, dict), f"{label} is not an object")
    claimed = payload.get('content_sha256')
    _require(isinstance(claimed, str) and len(claimed) == 64
             and all(c in '0123456789abcdef' for c in claimed),
             f"{label} carries no lowercase SHA-256 content_sha256")
    body = {k: v for k, v in payload.items() if k != 'content_sha256'}
    try:
        encoded = json.dumps(body, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=True, allow_nan=False).encode('ascii')
    except (TypeError, ValueError) as exc:
        raise Stage2AnalysisError(f"{label} invalid preparation JSON: {exc}") from None
    _require(sha256_hex(encoded) == claimed,
             f"{label} content_sha256 does not match its own body")
    return payload


def rebuild_range_plan(payload: Any,
                       records_per_range: int = MAX_COORDINATES_PER_RANGE
                       ) -> dict[str, Any]:
    """Independently rebuild the sealed plan and require equality.

    This is `stage2_cuda_execution_contract.validate_range_plan` (`:135-144`)
    re-implemented read-only: the plan must have the exact key set, the exact
    partition width, and ranges that are exactly `ceil(total/width)` contiguous
    `[start, stop)` slices from zero.  No plan is trusted because it is on disk.

    `records_per_range` comes from the census PROFILE, never from the plan: a
    plan that declared its own partition width would be able to redefine the
    census it is being checked against.
    """
    _require(isinstance(payload, dict), "range plan is not an object")
    _require(set(payload) == {"schema", "family", "total_coordinates",
                              "max_coordinates_per_range",
                              "qualification_identity_sha256", "ranges",
                              "content_sha256"},
             "range plan has the wrong key set")
    _require(payload["schema"] == RANGE_PLAN_SCHEMA, "range plan schema mismatch")
    _check_no_float_or_bool(payload, "$")
    _require(records_per_range >= 1,
             "the census profile declares a non-positive partition width")
    _require(payload["max_coordinates_per_range"] == records_per_range,
             f"the plan declares max_coordinates_per_range="
             f"{payload['max_coordinates_per_range']}, but the census profile "
             f"says {records_per_range}")
    total = payload["total_coordinates"]
    _require(type(total) is int and total >= 1,
             "range plan total_coordinates is not a positive int")
    identity = payload["qualification_identity_sha256"]
    _require(isinstance(identity, str) and len(identity) == 64
             and all(c in "0123456789abcdef" for c in identity),
             "range plan qualification identity is not a lowercase SHA-256")
    ranges = payload["ranges"]
    _require(isinstance(ranges, list) and ranges,
             "range plan carries no ranges")
    expected: list[dict[str, Any]] = []
    start = 0
    ordinal = 0
    while start < total:
        stop = min(start + records_per_range, total)
        expected.append({"batch_id": f"{payload['family']}_b{ordinal:04d}",
                         "start": start, "stop": stop})
        start, ordinal = stop, ordinal + 1
    _require(ranges == expected,
             "range plan is re-partitioned or not the canonical "
             "[start, stop) cover from zero")
    _require(content_sha256(payload) == payload["content_sha256"],
             "range plan content_sha256 does not match its own body")
    return payload


def rebuild_range_manifest(plan: dict[str, Any], manifest: Any) -> dict[str, Any]:
    """Independently rebuild one range manifest and require equality.

    This is `stage2_cuda_execution_contract.complete_range_manifest`
    (`:147-168`) re-implemented read-only.
    """
    _require(isinstance(manifest, dict), "range manifest is not an object")
    _check_no_float_or_bool(manifest, "$")
    _require(set(manifest) == {"schema", "batch_id", "start", "stop",
                               "plan_content_sha256", "qualification_identity_sha256",
                               "records_file_sha256", "records_content_sha256",
                               "status", "content_sha256"},
             "range manifest has the wrong key set")
    _require(manifest["schema"] == RANGE_MANIFEST_SCHEMA,
             "range manifest schema mismatch")
    _require(manifest["status"] == "complete",
             "range manifest is not complete")
    _require(manifest["qualification_identity_sha256"]
             == plan["qualification_identity_sha256"],
             "range manifest carries a different qualification identity")
    _require(manifest["plan_content_sha256"] == plan["content_sha256"],
             "range manifest is bound to a different range plan")
    rows = {row["batch_id"]: row for row in plan["ranges"]}
    _require(manifest["batch_id"] in rows,
             "range manifest names a batch outside the sealed plan")
    row = rows[manifest["batch_id"]]
    _require(manifest["start"] == row["start"] and manifest["stop"] == row["stop"],
             "range manifest range differs from the sealed plan")
    for field in ("records_file_sha256", "records_content_sha256"):
        value = manifest[field]
        _require(isinstance(value, str) and len(value) == 64
                 and all(c in "0123456789abcdef" for c in value),
                 f"range manifest {field} is not a lowercase SHA-256")
    _require(content_sha256(manifest) == manifest["content_sha256"],
             "range manifest content_sha256 does not match its own body")
    return manifest


# ---------------------------------------------------------------------------
# The committed coordinate record
# ---------------------------------------------------------------------------

RECORD_REQUIRED_KEYS = frozenset({
    "schema", "family", "group", "companion", "condition", "r_hex", "mapping",
    "coordinate", "coordinate_label", "coordinate_binary64_hex", "linear_index",
    "coefficients", "reconstruction", "content_sha256",
})
"""The exact key set of `_build_body` (`stage2_coordinate_records.py:910-931`)
plus `content_sha256` added at `:1010`."""

#: `summarize` in `stage2_cuda_reconstruct.py:196-214`.  This is the ONLY
#: per-cell summary the reconstruction produces, and it is what Stage-1's
#: `SERIES_KEYS` analogue is built from.
CELL_SUMMARY_KEYS = frozenset({
    "c_H", "c_f", "H_E_min_hex", "H_E_min_domain_index", "tie_comparator",
    "T_E_size", "X_E_size", "commitments", "set_label", "atomic_counts",
    "atomic_label_set", "I_C_exist", "I_C_univ", "p_A", "p_B", "p_C",
})

#: `DIAGNOSTIC_PAIRS` (`stage2_cuda_reconstruct.py:29`) rendered as the frozen
#: key strings `reconstruct_pair` emits (`:218`, `:271`).
D015_DIAGNOSTIC_KEYS: tuple[str, ...] = (
    "c_H=1024__c_f=2048",
    "c_H=4096__c_f=2048",
    "c_H=2048__c_f=1024",
    "c_H=2048__c_f=4096",
)
PRIMARY_SUMMARY_KEY = "primary_c_h_2048"

#: `FROZEN_MATH_SPEC.md:404` — `c_H = c_f = 2048`, the only primary pair.
PRIMARY_C_H = 2048
PRIMARY_C_F = 2048


def _check_cell_summary(summary: Any, label: str,
                        expected_pair: tuple[int, int] | None = None
                        ) -> dict[str, Any]:
    """Shape-check one reconstruction summary (`stage2_cuda_reconstruct.py:196-214`).

    `expected_pair` is the `(c_H, c_f)` this cell must have been computed
    under.  For the primary cell it is the frozen `(2048, 2048)`
    (`FROZEN_MATH_SPEC.md:404`); for a D015 diagnostic cell it is the pair
    NAMED BY THE KEY ITSELF, which is deliberately non-primary
    (`stage2_cuda_reconstruct.py:29, 218`, `DECISIONS.md:437-438`).  A
    diagnostic cell claiming `(2048, 2048)` would be a real defect, and so is
    one whose `c_H`/`c_f` disagree with its own key — either way the cell is
    refused, by comparing against the pair the key declares.
    """
    _require(isinstance(summary, dict) and set(summary) == CELL_SUMMARY_KEYS,
             f"{label} does not have the frozen summary key set "
             f"(stage2_cuda_reconstruct.py:196-214)")
    if expected_pair is None:
        _require(type(summary["c_H"]) is int and type(summary["c_f"]) is int,
                 f"{label} c_H/c_f are not integers")
    else:
        _require((summary["c_H"], summary["c_f"]) == expected_pair,
                 f"{label} declares comparator "
                 f"({summary['c_H']}, {summary['c_f']}) but the frozen rule "
                 f"requires {expected_pair} "
                 f"({'FROZEN_MATH_SPEC.md:404' if expected_pair == (2048, 2048) else 'stage2_cuda_reconstruct.py:29'})")
    counts = summary["atomic_counts"]
    _require(isinstance(counts, dict) and set(counts) == {"A", "B", "C"},
             f"{label} atomic_counts is not an A/B/C census")
    _require(all(type(v) is int and v >= 0 for v in counts.values()),
             f"{label} atomic_counts carries a non-count")
    _require(sum(counts.values()) == summary["X_E_size"],
             f"{label} atomic counts do not sum to X_E_size "
             "(stage2_cuda_reconstruct.py:190-191)")
    _require(summary["set_label"] in ("A", "B", "C"),
             f"{label} set_label is not A, B or C")
    for field in ("I_C_exist", "I_C_univ", "T_E_size", "X_E_size",
                  "H_E_min_domain_index"):
        _require(type(summary[field]) is int and summary[field] >= 0,
                 f"{label}.{field} is not a non-negative int")
    _require(summary["X_E_size"] >= 1,
             f"{label} decoded set X_E is empty; rho_E^exact is undefined "
             "(FROZEN_MATH_SPEC.md:459 requires a nonempty X_E)")
    for field in ("p_A", "p_B", "p_C"):
        pair = summary[field]
        _require(isinstance(pair, list) and len(pair) == 2
                 and all(type(v) is int for v in pair) and pair[1] >= 1,
                 f"{label}.{field} is not a [numerator, denominator] int pair")
        _require(pair[0] == counts[field[-1]],
                 f"{label}.{field} numerator differs from the atomic census")
    _require(summary["I_C_exist"] == int(counts["C"] > 0)
             and summary["I_C_univ"] == int(counts["C"] == summary["X_E_size"]),
             f"{label} I_C_exist/I_C_univ are not the frozen indicators "
             "(stage2_cuda_reconstruct.py:210)")
    return summary


def _check_reconstruction(reconstruction: Any, label: str) -> dict[str, Any]:
    _require(isinstance(reconstruction, dict)
             and set(reconstruction) == {PRIMARY_SUMMARY_KEY, "d015_diagnostics"},
             f"{label} reconstruction has the wrong key set "
             f"(stage2_cuda_reconstruct.py:268-275)")
    primary = reconstruction[PRIMARY_SUMMARY_KEY]
    _require(isinstance(primary, dict) and set(primary) == set(ENCODINGS),
             f"{label} primary_c_h_2048 is not keyed by both encodings")
    for encoding in ENCODINGS:
        _check_cell_summary(primary[encoding],
                            f"{label} primary_c_h_2048[{encoding}]",
                            expected_pair=(PRIMARY_C_H, PRIMARY_C_F))
    diagnostics = reconstruction["d015_diagnostics"]
    _require(isinstance(diagnostics, dict)
             and set(diagnostics) == set(D015_DIAGNOSTIC_KEYS),
             f"{label} d015_diagnostics is not the four frozen diagnostic pairs "
             f"(stage2_cuda_reconstruct.py:29)")
    for key in D015_DIAGNOSTIC_KEYS:
        cell = diagnostics[key]
        pair = parse_diagnostic_pair(key)
        _require(isinstance(cell, dict) and set(cell) == set(ENCODINGS),
                 f"{label} d015_diagnostics[{key}] is not keyed by both encodings")
        for encoding in ENCODINGS:
            _check_cell_summary(cell[encoding],
                                f"{label} d015_diagnostics[{key}][{encoding}]",
                                expected_pair=pair)
    return reconstruction


def parse_diagnostic_pair(key: str) -> tuple[int, int]:
    """Parse a frozen `c_H=<n>__c_f=<n>` key back to its pair.

    `stage2_cuda_reconstruct._pair_of_key` (`:962-972`) does exactly this, and
    a key whose pair is not one of the four declared diagnostic pairs is
    refused here rather than silently accepted.
    """
    head, separator, tail = key.partition("__c_f=")
    _require(separator == "__c_f=" and head.startswith("c_H="),
             f"malformed D015 diagnostic key {key!r}")
    try:
        pair = (int(head[len("c_H="):]), int(tail))
    except ValueError:
        raise Stage2AnalysisError(
            f"malformed D015 diagnostic key {key!r}") from None
    _require(pair in DECLARED_DIAGNOSTIC_PAIRS,
             f"D015 diagnostic key {key!r} is not one of the four declared "
             f"pairs (stage2_cuda_reconstruct.py:29)")
    return pair


DECLARED_DIAGNOSTIC_PAIRS: frozenset[tuple[int, int]] = frozenset(
    {(1024, 2048), (4096, 2048), (2048, 1024), (2048, 4096)})
"""`stage2_cuda_reconstruct.DIAGNOSTIC_PAIRS` (`:29`)."""


def check_record(record: Any, family_key: str, label: str,
                 axis_length: int | None = None,
                 total: int | None = None) -> dict[str, Any]:
    """Validate ONE committed record against the frozen schema.

    This is `stage2_coordinate_records.validate_record`'s SCHEMA half (`:1044-1060`)
    plus `_verify_full_records`' identity checks
    (`wp8c_streaming_session_v3_gzip.py:74-80`), re-implemented read-only.  The
    NUMERIC half — replaying the CUDA energy, tie set and classifier — is NOT
    reproduced here and is explicitly out of scope: see `ANALYSIS_NOTES.md`.

    The checks, all of which a single altered byte trips:
      1. exact key set (`:911-931` + `:1010`);
      2. `schema` is `RECORD_SCHEMA`;
      3. `family` equals the sealed family's key;
      4. `group`/`r_hex`/`mapping` agree with the family (`:461-478`);
      5. `linear_index` in range and `coordinate` equals the coordinate the
         canonical linear order gives for it (`:404-429`);
      6. `content_sha256` re-derives over the canonical body (`:1010`);
      7. the frozen reconstruction has the frozen shape and the (2048, 2048)
         primary comparator (`:196-214`).
    """
    _require(isinstance(record, dict), f"{label} is not an object")
    _require(set(record) == RECORD_REQUIRED_KEYS,
             f"{label} does not have the exact committed record key set "
             f"(stage2_coordinate_records.py:911-931, 1010)")
    _require(record["schema"] == RECORD_SCHEMA,
             f"{label} schema is not {RECORD_SCHEMA}")
    _require(record["family"] == family_key,
             f"{label} names family {record['family']!r}, not the sealed "
             f"family {family_key!r}")
    _require(family_key in FAMILY_CENSUS, f"{label} unknown family {family_key!r}")
    _require(record["group"] == FAMILY_GROUP[family_key],
             f"{label} group {record['group']!r} disagrees with its family key")
    _require(record["r_hex"] == FAMILY_R_HEX[family_key],
             f"{label} r_hex {record['r_hex']!r} disagrees with its family key "
             "(stage2_coordinate_records.py:379-380, 158)")
    _require(record["mapping"] == ("d011_cm" if record["group"] == "d011"
                                   else "d006_r1"),
             f"{label} mapping {record['mapping']!r} disagrees with its group "
             "(stage2_coordinate_records.py:462-478)")
    _require(record["condition"] is None,
             f"{label} carries a D013 condition; a baseline family never does "
             "(stage2_coordinate_records.py:457)")

    frozen_axis, frozen_total, _citation = FAMILY_CENSUS[family_key]
    axis_length = frozen_axis if axis_length is None else axis_length
    total = frozen_total if total is None else total
    linear = record["linear_index"]
    _require(type(linear) is int and not isinstance(linear, bool)
             and 0 <= linear < total,
             f"{label} linear_index {linear!r} is outside 0..{total - 1}")
    coordinate = record["coordinate"]
    _require(isinstance(coordinate, dict) and len(coordinate) == 3,
             f"{label} coordinate is not a three-axis map "
             "(FROZEN_MATH_SPEC.md:171-174 fixes three axes)")
    axes = ("ell_card", "ell_sector", "ell_budget")
    _require(set(coordinate) == set(axes),
             f"{label} coordinate axes are not the three frozen axes")
    _require(all(type(v) is int and not isinstance(v, bool)
                 and 0 <= v < axis_length for v in coordinate.values()),
             f"{label} coordinate index is outside 0..{axis_length - 1}")
    expected_linear = ((coordinate["ell_card"] * axis_length
                        + coordinate["ell_sector"]) * axis_length
                       + coordinate["ell_budget"])
    _require(expected_linear == linear,
             f"{label} coordinate does not match its own linear index in the "
             "canonical last-axis-fastest order "
             "(stage2_coordinate_records.py:82-89, 404-429)")

    body = {key: value for key, value in record.items() if key != "content_sha256"}
    _require(sha256_hex(canonical_bytes(body)) == record["content_sha256"],
             f"{label} content_sha256 does not match its own canonical body "
             "(stage2_coordinate_records.py:1010)")
    _check_reconstruction(record["reconstruction"], label)
    return record


# ---------------------------------------------------------------------------
# The promoted-range reader
# ---------------------------------------------------------------------------

def read_full_records(path: Path, expected_count: int, label: str) -> list[dict[str, Any]]:
    """Decompress one `full_records/<batch_id>.jsonl.gz` and return its records.

    The gzip framing is `_persist_full`'s
    (`wp8c_streaming_session_v3_gzip.py:47-66`): `gzip.compress(raw,
    compresslevel=1, mtime=0)` over `canonical(record) + b"\\n"` joined lines.
    The **uncompressed** bytes are what the commitments hash — the range
    manifest's `records_file_sha256` and the streaming session's
    `full_records_commitment_sha256` are taken over the decompressed stream
    (`:66`, `:109`), never over the compressed file.  Both are checked by
    `verify_outputs_v2.py`.
    """
    try:
        stored = path.read_bytes()
    except OSError as exc:
        raise Stage2AnalysisError(f"{label} is unreadable: {exc}") from None
    try:
        raw = gzip.decompress(stored)
    except (OSError, EOFError) as exc:
        raise Stage2AnalysisError(f"{label} is not readable gzip: {exc}") from None
    _require(len(raw) > 0, f"{label} decompressed to zero bytes")
    lines = raw.splitlines()
    _require(len(lines) == expected_count,
             f"{label} holds {len(lines)} records but its sealed range spans "
             f"{expected_count} coordinates "
             "(wp8c_streaming_session_v3_gzip.py:73)")
    records = []
    for index, line in enumerate(lines):
        try:
            record = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise Stage2AnalysisError(
                f"{label} line {index} is not ASCII JSON: {exc}") from None
        records.append(record)
    return records


def iter_family_records(family_root: Path, family_key: str,
                        records_per_range: int = MAX_COORDINATES_PER_RANGE,
                        total: int | None = None,
                        axis_length: int | None = None
                        ) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield `(batch_id, record)` in the sealed plan's canonical order.

    The order is the plan's `[start, stop)` order, which
    `stage2_coordinate_records.range_plan` (`:645-664`) proves is exactly the
    canonical linear order of the family's coordinate space.  Reading in that
    order is what makes the row census a *census* rather than a sample
    (`project/paper/RESULTS_AND_FIGURE_SLOTS.md:44-48`).

    `total` and `axis_length` come from the census PROFILE.  Under the default
    (unscaled) profile they equal the frozen constants; under a scaled profile
    they are smaller, and `check_record` correspondingly accepts the truncated
    lattice.  A record is still required to sit exactly on the canonical
    last-axis-fastest order of the axis length in force.
    """
    plan = rebuild_range_plan(read_sealed(family_root / PLAN_NAME,
                                          f"{family_key} range_plan.json"),
                              records_per_range=records_per_range)
    _require(plan["family"] == family_key,
             f"{family_key} range_plan.json names family {plan['family']!r}")
    frozen_total = FAMILY_CENSUS[family_key][1]
    expected_total = frozen_total if total is None else total
    _require(plan["total_coordinates"] == expected_total,
             f"{family_key} sealed plan spans {plan['total_coordinates']} "
             f"coordinates; the census profile expects {expected_total}")
    _require(len(plan["ranges"]) == -(-expected_total // records_per_range),
             f"{family_key} sealed plan carries {len(plan['ranges'])} ranges; "
             f"ceil({expected_total}/{records_per_range}) is "
             f"{-(-expected_total // records_per_range)}")
    del axis_length
    for row in plan["ranges"]:
        batch = row["batch_id"]
        path = (family_root / FULL_RECORDS_DIRNAME / f"{batch}.jsonl.gz")
        for record in read_full_records(path, row["stop"] - row["start"],
                                        f"{family_key}/{batch}"):
            yield batch, record


# ---------------------------------------------------------------------------
# Slot discovery
# ---------------------------------------------------------------------------

def find_slot_dir(download_root: Path, slot_number: int) -> Path:
    """Locate one slot's staged instance tree inside a downloaded result dir.

    The collector writes each kernel's output under
    `push/<kernel-id>/results/`, from which `staged_qualified_sources/` is
    replicated verbatim (the bootstrap copies the pinned sources there,
    `kernel.py:7, 13-23`).  The instance tree lives under
    `<staged>/research/g9/stage2_instances/<stage2_0N>/`.

    A single slot directory holds EXACTLY ONE slot: an extra `stage2_0N`
    directory beside the requested one is an AMBIGUITY and is refused, never
    silently ignored, because two instances in one download cannot both be the
    slot whose name the caller asked for.  When several slots were downloaded
    under one root, each is found by its own slot NAME.

    Raises `Stage2AnalysisError` when the slot is absent — a missing slot is a
    fail-closed condition, never a silently skipped one.
    """
    name = SLOT_NAMES[slot_number - 1]
    wanted = f"{INSTANCE_ROOT}/{name}"
    parents: set[Path] = set()
    for path in download_root.rglob(wanted):
        if path.is_dir() and not path.is_symlink():
            parents.add(path.parent)
    if not parents:
        raise Stage2AnalysisError(
            f"slot {slot_number} ({name}) is missing from {download_root}: no "
            f"{wanted} directory was found. A missing slot is a fail-closed "
            "condition; nothing is analysed without all five.")
    if len(parents) > 1:
        raise Stage2AnalysisError(
            f"slot {slot_number} ({name}) is ambiguous: it appears under "
            f"{len(parents)} different staged trees "
            f"({', '.join(sorted(str(p) for p in parents))}). Exactly one "
            "instance tree per slot is required.")
    parent = next(iter(parents))
    siblings = sorted(child.name for child in parent.iterdir()
                      if child.is_dir() and not child.is_symlink()
                      and child.name in SLOT_NAMES)
    if siblings != [name]:
        raise Stage2AnalysisError(
            f"slot {slot_number} ({name}) is not alone in {parent}: that "
            f"directory holds {siblings}. One downloaded slot carries exactly "
            "one instance tree; two of them cannot both be this slot.")
    return parent / name


def instance_id_of(slot_dir: Path, slot_number: int) -> str:
    """The instance identity every artefact for this slot must agree on.

    `PREPARED.json` is the per-instance layout record the whole WP8b chain
    re-derives from (`production_parent_v2.py:188-190`).  Its
    `content_sha256` is the value the plan pins as
    `prepared_record_content_sha256` (`production_parent_v2.py:183-184`).
    """
    prepared = read_prepared_metadata(slot_dir / "instance/PREPARED.json", "PREPARED.json")
    name = SLOT_NAMES[slot_number - 1]
    observed = prepared.get("instance_id", prepared.get("slot_name"))
    if observed is None and isinstance(prepared.get("instance"), dict):
        observed = prepared["instance"].get("instance_id")
    if isinstance(observed, str):
        _require(observed == name,
                 f"PREPARED.json names {observed!r} in the {name} slot tree; "
                 "slot and instance identity must agree "
                 "(wp8d_production_layout._slot_dir:319-320)")
    return name
    return observed
