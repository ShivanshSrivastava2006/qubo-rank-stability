"""Record shaping for the Stage-2 CUDA path: coordinate iterator, V-14 and D011
coordinate-to-coefficient resolution, and D015/D016 record reconstruction.

This module closes the WP0 audit's class-(a) host-side record-shaping gaps
**G1** (per-coordinate 3-D iterator + record construction), **G2**
(D016 reconstruction/label builder), **G6** (V-14 0.5x/2x coordinate to
coefficient resolution) and **G12** (the D011 + V-14 companion package carried
per fired D013 condition).  The audit lists them at
`research/g9/GATE_9_WP0_V1_PRODUCTION_GAP_AUDIT_DRAFT.md:827-828,832,836` and
routes all of them to the production identity and WP7 (`:1197-1205`; owner
decision `research/decisions/GATE_9_WP0_D013_CUDA_PATH_AND_IDENTITY_SCOPE_OWNER_DECISION.md:36-43`).
It therefore imports, and never edits, its frozen dependencies.

Frozen dependencies (all imported, none modified):

* `research/g9/cuda_qualification/stage2_cuda_execution_contract.py` — the
  sealed range plan.  `build_range_plan` (`:112-132`) partitions
  `[0, total_coordinates)` into contiguous `[start, stop)` ranges of at most
  `MAX_COORDINATES_PER_RANGE` (`:19`), and `validate_range_plan` (`:135-144`)
  refuses any re-partition.  This module's canonical linear order *is* the
  order that plan partitions, and the two are checked against each other
  rather than merely declared equal.
* `research/g9/cuda_qualification/stage2_cuda_reconstruct.py` — the D015/D016
  reconstruction.  It is deliberately **outside** the 12-file qualified v1 map
  (audit §3.3 G2, `:828`); the approved amendment assigns reconstruction to the
  host (`research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md:55-56`).
  `reconstruct_pair` (`:223-276`) is the per-coordinate entry point and
  `ReconstructionError` (`:33-34`) is the frozen refusal.
* `src/g5/core_pass.py` — the primary CSB coefficient producer.
  `derive_coefficients` (`:127-139`) with its frozen primitive sequence
  `_coefficient_family` (`:118-124`), and `ROW_COUNT = 61` (`:44`) /
  `R_VALUES = (0.5, 1.0, 2.0)` (`:43`).
* `src/g6/ledgers.py` — the V-14 and D011 coordinate/coefficient input
  authority.  `_load_accepted_inputs` (`:120-161`) hash-binds the G4 primary
  ledger, ADNYE-001/002 and the frozen spec and fails closed on drift.
  `_axis_coefficients_d006_r1` (`:174-192`) is the V-14 / r=1 primitive
  transcription, `_axis_coefficients_d011_cm` (`:195-208`) is D011's approved
  `a = 2` curvature-match mapping, `_cardinality_coefficients` (`:211-213`) is
  the cardinality row, `_coefficient_ledger` (`:216-231`) is the frozen caller
  contract, and the V-14 axis sizes `N_axis = 31` (0.5x) and `N_axis = 111`
  (2x) are fixed at `:290-291`.
* `src/g6/d011_matched_subgrid.py` — D011's declared 13-cubed subgrid.
  `MATCHED_COORDINATE_COUNT = 13 ** 3` (`:54`), `COARSE_INDICES` (`:52`) and
  `PRIMARY_INDICES = (0, 5, …, 60)` (`:53`).
* `src/g4/classification.py` — the frozen D016 classifier the reconstructor
  uses: `OriginalObjectiveService` (`:40-78`) and `DecodedClassifier`
  (`:81-120`).
* `research/g9/stage2_sampled_verification.py` — the canonical committable
  encoder.  `canonical` (`:196-203`) enforces the *allowlist*
  `None | bool | int | str | list | dict` (`:176-193`), so a raw float, a
  `tuple` or any container/float subclass is refused rather than serialised
  through `repr`.  Every record this module emits is pushed through it, which
  is what the audit's commitment must-fix items require (`:1207`, M1-M7).

Coordinate families and their counts (each is a *coordinate space*; both
encodings are compared at every coordinate of a space, so a family's
per-encoding coordinate count equals its space's count):

| family | axes | count per r/encoding |
| --- | --- | --- |
| primary CSB, `r in {0.5, 1, 2}` | 61 x 61 x 61 | 226,981 |
| D011 matched subgrid | 13 x 13 x 13 | 2,197 |
| V-14 0.5x | 31 x 31 x 31 | 29,791 |
| V-14 2x | 111 x 111 x 111 | 1,367,631 |
| D013 `C` active axes | 61 | 61 |
| D013 `CB` active axes | 61 x 61 | 3,721 |
| D013 `CS` active axes | 61 x 61 | 3,721 |
| D013 `CSB` active axes | 61 x 61 x 61 | 226,981 |

The D013 active-axis and active-family maps are read off the four frozen
predicates at `research/decisions/DECISIONS.md:1106-1111`: cardinality is active
in all four conditions, the sector family is absent from `C` and `CB`, and the
budget family is absent from `C` and `CS`, giving one, two, two and three
active axes respectively.  Every shared active coordinate is sampled at the same
D010/D012 values, and an inactive penalty is identically `+0.0` and leaves the
grid entirely (`DECISIONS.md:1115-1118`; supporting reading
`research/g9/GATE_9_WP6_D013_SPEC_GAP_DRAFT.md:46-79`).  The retained inactive
register's multiplicity belongs to the WP6 evaluator
(`research/decisions/GATE_9_D013_INACTIVE_EVALUATOR_SPEC_OWNER_DECISION.md:33-37`);
this module only records the exact `+0.0`, and never enumerates that register.

Canonical linear order.  Within one coordinate space the order is row-major
over the family's declared axes in canonical order with the **last axis
fastest**, so `linear = (i0 * n1 + i1) * n2 + i2`.  This is the order the frozen
G5 core pass walks — its shard tasks are `for r … for card … for sector` with
the budget axis innermost (`src/g5/core_pass.py:266`, `:210`) — so a linear
index here addresses the same coordinate the engine's slot addressing already
uses.  The range plan's `[start, stop)` ranges slice exactly this order, which
`iter_plan_order` makes checkable rather than assumed.

Refusals are typed (`CoordinateRecordError`) and fail closed.  Nothing here
reads an instance, an engine, a candidate, a ground truth or a result: the only
inputs are the frozen ledgers, the injected production identity, and the
bounded minima/tie data handed over by the engine.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from research.g9 import stage2_sampled_verification
from research.g9.cuda_qualification import stage2_cuda_execution_contract as contract
from research.g9.cuda_qualification import stage2_cuda_reconstruct
from src.g4.classification import DecodedClassifier
from src.g5 import core_pass
from src.g6 import d011_matched_subgrid
from src.g6 import ledgers

__all__ = [
    "AXES",
    "BUDGET",
    "CARDINALITY",
    "COEFFICIENT_FAMILIES",
    "D013_ACTIVE_AXES",
    "D013_ACTIVE_FAMILIES",
    "D013_CONDITIONS",
    "ENCODINGS",
    "PRIMARY_R_HEX",
    "ZERO_HEX",
    "AcceptedIdentity",
    "BoundIdentity",
    "CoordinateRecordError",
    "CoordinateSpace",
    "Family",
    "FrozenAxes",
    "RECORD_SCHEMA",
    "bind_identity",
    "build_frozen_axes",
    "build_record",
    "d013_package",
    "families",
    "family_space",
    "iter_coordinates",
    "iter_plan_order",
    "range_plan",
    "resolve_coefficients",
    "validate_record",
]

AXES = ("ell_card", "ell_sector", "ell_budget")
ENCODINGS = ("unbalanced", "slack")
CARDINALITY = "cardinality"
SECTOR = "sector"
BUDGET = "budget"
COEFFICIENT_FAMILIES = (CARDINALITY, SECTOR, BUDGET)
_COMPANIONS = ("primary", "active", "d011", "v14_0.5x", "v14_2x")
_SOURCES = ("g4-primary", "g6-d011", "g6-v14-0.5x", "g6-v14-2x")
_GROUPS = ("primary", "d011", "v14", "d013")

RECORD_SCHEMA = "decisions_os/g9_stage2_coordinate_record/v1"

#: `float(1.0).hex()`; D011's matched-subgrid module pins the same literal for
#: the primary `r` at `src/g6/d011_matched_subgrid.py:49`.
PRIMARY_R_HEX = "0x1.0000000000000p+0"
ZERO_HEX = float(0.0).hex()

MAPPING_D006_R1 = "d006_r1"
MAPPING_D011_CM = "d011_cm"
_MAPPINGS = (MAPPING_D006_R1, MAPPING_D011_CM)

#: D013's exactly four conditional conditions and their active penalty axes,
#: read off `DECISIONS.md:1106-1111`.  Cardinality is active in all four.
D013_CONDITIONS = ("C", "CB", "CS", "CSB")
D013_ACTIVE_AXES: dict[str, tuple[str, ...]] = {
    "C": ("ell_card",),
    "CB": ("ell_card", "ell_budget"),
    "CS": ("ell_card", "ell_sector"),
    "CSB": ("ell_card", "ell_sector", "ell_budget"),
}
D013_ACTIVE_FAMILIES: dict[str, tuple[str, ...]] = {
    "C": (CARDINALITY,),
    "CB": (CARDINALITY, BUDGET),
    "CS": (CARDINALITY, SECTOR),
    "CSB": (CARDINALITY, SECTOR, BUDGET),
}


class CoordinateRecordError(ValueError):
    """Typed refusal for an unsafe coordinate, coefficient or record shape."""


def _require(condition: object, message: str) -> None:
    """Fail-closed assertion.

    Deliberately a function call, never a bare `assert`: the fixtures run under
    `python3 -B -O` as well as `-B`, and `-O` strips `assert` statements, which
    would silently remove a refusal.
    """
    if not condition:
        raise CoordinateRecordError(message)




def _index(value: object, upper: int, label: str) -> int:
    _require(type(value) is int and 0 <= value < upper,
             f"{label} is outside its canonical domain 0..{upper - 1}")
    return value


def _positive_zero(value: object) -> bool:
    """The D013 inactive-family coefficient: exactly the *positive* zero."""
    return type(value) is float and value == 0.0 and math.copysign(1.0, value) > 0.0


# ---------------------------------------------------------------------------
# Production identity (WP1) — injected, never imported
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AcceptedIdentity:
    """The injected WP1 production identity.

    WP1's production identity is still under review, so this module does not
    import it.  It takes three injected dependencies and treats them as
    authoritative: an accepted identity `payload` (`dict`), a
    `validate(payload) -> sha256-hex` callable, and an
    `exact_match(session, accepted)` callable that *raises* on any difference.
    This module never re-implements either callable, never compares payloads
    with its own equality, and never derives an identity digest itself.
    """

    payload: Mapping[str, Any]
    validate: Callable[[object], str]
    exact_match: Callable[[object, object], object]


@dataclass(frozen=True)
class BoundIdentity:
    """An `AcceptedIdentity` whose hash has been taken once, up front.

    The hash comes only from calling the injected `validate`; this module never
    computes an identity digest of its own.
    """

    accepted: AcceptedIdentity
    qualification_identity_sha256: str

    def recheck(self, session: Any) -> None:
        """§B item 1's pre-write recheck, delegated in full to `exact_match`.

        The caller's session identity is compared against the accepted payload
        by the injected callable; any difference raises out of here.  This
        module adds no second, weaker comparison that could pass where
        `exact_match` would have failed.
        """
        result = self.accepted.exact_match(session, self.accepted.payload)
        _require(result is None or result is True,
                 "exact_match must return None or True on a match")
        return None


def bind_identity(accepted: AcceptedIdentity) -> BoundIdentity:
    """Validate the accepted identity once and return its sealed hash."""
    _require(isinstance(accepted, AcceptedIdentity), "an AcceptedIdentity is required")
    _require(isinstance(accepted.payload, dict) and bool(accepted.payload),
             "the accepted identity payload must be a non-empty dict")
    _require(callable(accepted.validate), "the injected validate(payload) is not callable")
    _require(callable(accepted.exact_match),
             "the injected exact_match(session, accepted) is not callable")
    digest = accepted.validate(accepted.payload)
    _require(type(digest) is str and len(digest) == 64
             and all(char in "0123456789abcdef" for char in digest),
             "validate(payload) must return a lowercase SHA-256 hex digest")
    return BoundIdentity(accepted=accepted, qualification_identity_sha256=digest)


# ---------------------------------------------------------------------------
# Frozen axis value sources
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FrozenAxes:
    """The frozen per-axis coordinate vectors and `Lambda_ref`.

    Built by `build_frozen_axes` from the frozen modules only, so the production
    path cannot substitute a caller-supplied axis.  The fixture path constructs
    the same dataclass directly with synthetic values.
    """

    lambda_ref: float
    primary: tuple[float, ...]
    d011: tuple[float, ...]
    v14_0_5x: tuple[float, ...]
    v14_2x: tuple[float, ...]

    def vector(self, source: str) -> tuple[float, ...]:
        _require(type(source) is str and source in _SOURCES,
                 f"unknown frozen axis source: {source!r}")
        return {
            "g4-primary": self.primary,
            "g6-d011": self.d011,
            "g6-v14-0.5x": self.v14_0_5x,
            "g6-v14-2x": self.v14_2x,
        }[source]


def build_frozen_axes() -> FrozenAxes:
    """Assemble the frozen axis vectors through the frozen ledgers.

    `ledgers._load_accepted_inputs` (`:120-161`) hash-binds the G4 primary
    ledger, ADNYE-001 and ADNYE-002, the canonical instance, the frozen math
    spec, DECISIONS.md and the Gate-5 owner record and returns
    `(g4, lambda_ref, snapshot)`; its `_require` calls fail closed on any
    drift.  The D011 and both V-14 axis vectors come from
    `ledgers.build_d011_ledger` (`:262-285`) and `ledgers.build_v14_ledger`
    (`:288-323`), which re-derive their own coordinates and are themselves the
    frozen authority for `N_axis`.
    """
    g4, lambda_ref, _snapshot = ledgers._load_accepted_inputs()
    primary = tuple(ledgers._g4_coordinate(row, index)
                    for index, row in enumerate(g4["coordinates"]))
    d011_rows = ledgers.build_d011_ledger()["coordinates"]
    half_rows = ledgers.build_v14_ledger("0.5x")["coordinates"]
    double_rows = ledgers.build_v14_ledger("2x")["coordinates"]
    return FrozenAxes(
        lambda_ref=lambda_ref,
        primary=primary,
        d011=tuple(ledgers._positive_hex(row["binary64_hex"],
                                         f"D011 coordinate {row['index']}")
                   for row in d011_rows),
        v14_0_5x=tuple(ledgers._positive_hex(row["binary64_hex"],
                                              f"V-14 0.5x coordinate {row['index']}")
                        for row in half_rows),
        v14_2x=tuple(ledgers._positive_hex(row["binary64_hex"],
                                           f"V-14 2x coordinate {row['index']}")
                     for row in double_rows),
    )


# ---------------------------------------------------------------------------
# Coordinate families and spaces
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Family:
    """One record family: an axis source, an axis list, a mapping and an `r`.

    `axes` is a subsequence of `AXES`; a D013 condition's inactive axis is
    absent from `axes` rather than repeated, per `DECISIONS.md:1115-1118`.
    """

    group: str
    companion: str
    source: str
    mapping: str
    r: float
    axes: tuple[str, ...]
    active_families: tuple[str, ...]
    condition: str | None = None
    label: str = ""

    @property
    def key(self) -> str:
        """A range-plan-safe family identifier.

        `contract.range_id` (`:105-109`) accepts only lowercase, digits, `_`
        and `-`.  Every part is therefore lowercased and every character outside
        that alphabet replaced by `_`, then the parts are joined by `__`.  The
        mapping is injective over the declared alphabet: the group, condition
        and companion names are distinct ASCII alphanumerics, the `r` token is
        the frozen binary64 hex, and a family with no condition emits two parts
        where a D013 family emits three.  `_declared_families` re-checks the
        resulting keys for exact distinctness rather than assuming it.
        """
        parts = [self.group, self.condition, self.companion, f"r{float(self.r).hex()}"]
        token = "__".join(
            "".join(char if char.islower() or char.isdigit() or char in "_-" else "_"
                    for char in part.lower())
            for part in parts if part is not None
        )
        return token

    @property
    def r_hex(self) -> str:
        return float(self.r).hex()


@dataclass(frozen=True)
class CoordinateSpace:
    """A family's coordinate space and its canonical linear order."""

    family: Family
    counts: tuple[int, ...]

    @property
    def total_coordinates(self) -> int:
        total = 1
        for count in self.counts:
            total *= count
        return total

    def _strides(self) -> tuple[int, ...]:
        """Last axis fastest, matching `src/g5/core_pass.py:210,266`."""
        strides: list[int] = [1] * len(self.counts)
        for position in range(len(self.counts) - 2, -1, -1):
            strides[position] = strides[position + 1] * self.counts[position + 1]
        return tuple(strides)

    def linear_index(self, coordinate: Sequence[int]) -> int:
        """Canonical linear index of a coordinate (row-major, last axis fastest)."""
        _require(type(coordinate) is tuple, "a coordinate must be an explicit tuple")
        _require(len(coordinate) == len(self.counts),
                 f"coordinate has {len(coordinate)} indices, space has {len(self.counts)} axes")
        strides = self._strides()
        total = 0
        for position, value in enumerate(coordinate):
            _index(value, self.counts[position],
                   f"coordinate axis {self.family.axes[position]!r}")
            total += value * strides[position]
        return total

    def coordinate(self, linear: int) -> tuple[int, ...]:
        """Inverse of `linear_index`."""
        _index(linear, self.total_coordinates, "linear coordinate index")
        values: list[int] = [0] * len(self.counts)
        remaining = linear
        # Peel from the fastest axis: each axis's digit is the remainder divided
        # by that axis's own stride, then the remainder is reduced modulo the
        # *next slower* axis's stride so the next digit cannot overflow.
        for position in range(len(self.counts) - 1, 0, -1):
            values[position] = remaining % self.counts[position]
            remaining //= self.counts[position]
        values[0] = remaining
        return tuple(values)

    def label(self, coordinate: Sequence[int]) -> str:
        _require(type(coordinate) is tuple and len(coordinate) == len(self.counts),
                 "a coordinate must be a tuple matching the family's axes")
        return "|".join(f"{axis}={value}"
                        for axis, value in zip(self.family.axes, coordinate, strict=True))


def _check_family(family: Family) -> Family:
    _require(isinstance(family, Family), "a Family is required")
    _require(family.group in _GROUPS, "unknown family group")
    _require(family.companion in _COMPANIONS, "unknown family companion")
    _require(type(family.r) is float and math.isfinite(family.r) and family.r > 0.0,
             "family r must be a finite positive binary64")
    # Cardinality is never inactive: D013's four predicates all contain
    # `sum_i x_i = K` (DECISIONS.md:1106-1111), and DECISIONS.md:1142-1143
    # records it as an equality penalty handled separately.  A D013 family
    # therefore always has cardinality active, which the condition's own
    # active-family map below already encodes; a non-D013 family must have all
    # three active, asserted here.
    if family.group == "d013":
        _require(family.condition in D013_CONDITIONS, "unknown D013 condition")
        _require(family.axes == D013_ACTIVE_AXES[family.condition],
                 "D013 family axes differ from the condition's active axes")
        _require(family.active_families == D013_ACTIVE_FAMILIES[family.condition],
                 "D013 family coefficients differ from the condition's active families")
    else:
        _require(family.condition is None, "only a D013 family carries a condition")
        _require(family.active_families == COEFFICIENT_FAMILIES,
                 f"a {family.group} family keeps every coefficient family active")
        _require(family.axes == AXES,
                 f"a {family.group} family uses all three axes")
    if family.companion == "d011":
        _require(family.mapping == MAPPING_D011_CM,
                 "the D011 companion must use D011's curvature-match mapping")
        _require(family.source == "g6-d011", "the D011 companion must use the D011 axis source")
        _require(family.r_hex == PRIMARY_R_HEX, "the D011 companion is an r=1 pass")
    elif family.companion in ("v14_0.5x", "v14_2x"):
        _require(family.mapping == MAPPING_D006_R1,
                 "the V-14 companions must use the r=1 D006 mapping")
        _require(family.source == f"g6-v14-{family.companion.removeprefix('v14_')}",
                 "the V-14 companion's axis source does not match its scale")
        _require(family.r_hex == PRIMARY_R_HEX, "the V-14 companions are r=1 readings")
    else:
        _require(family.mapping == MAPPING_D006_R1,
                 "the CSB companion must use the r=1 D006 mapping")
        if family.group != "d013":
            _require(family.source == "g4-primary",
                     "the primary CSB companion must use the G4 primary axis source")
    key = family.key
    # The key must satisfy `contract.range_id`'s character rule (`:105-109`).
    # That rule is exactly the alphabet test below, so it is applied directly
    # rather than by calling the contract and shadowing this check behind it.
    _require(bool(key) and all(char.islower() or char.isdigit() or char in "_-"
                               for char in key),
             f"family key is not range-plan safe: {key!r}")
    return family


def _primary_family(r: float) -> Family:
    return Family(group="primary", companion="primary", source="g4-primary",
                  mapping=MAPPING_D006_R1, r=float(r), axes=AXES,
                  active_families=COEFFICIENT_FAMILIES, label="primary")


def _d013_family(condition: str, companion: str) -> Family:
    source, mapping = {
        "active": ("g4-primary", MAPPING_D006_R1),
        "d011": ("g6-d011", MAPPING_D011_CM),
        "v14_0.5x": ("g6-v14-0.5x", MAPPING_D006_R1),
        "v14_2x": ("g6-v14-2x", MAPPING_D006_R1),
    }[companion]
    # Every D013 family of a condition — the active-axis grid itself and each
    # companion — is sampled only on that condition's active axes; an inactive
    # axis never appears (DECISIONS.md:1115-1118).
    axes = D013_ACTIVE_AXES[condition]
    return Family(group="d013", companion=companion, source=source, mapping=mapping,
                  r=1.0, axes=axes, active_families=D013_ACTIVE_FAMILIES[condition],
                  condition=condition, label="d013")


def _base_families() -> tuple[Family, ...]:
    """The primary CSB, D011 and V-14 families the protocol always declares.

    `R_VALUES = (0.5, 1.0, 2.0)` and `ROW_COUNT = 61` are
    `src/g5/core_pass.py:43-44`; D011's 13-cubed subgrid and both V-14 scales
    are the approved companions (`GATE_9_STAGE2_PROTOCOL_DRAFT.md:151-157`).
    """
    built: list[Family] = [_primary_family(r) for r in core_pass.R_VALUES]
    built.append(Family(group="d011", companion="d011", source="g6-d011",
                        mapping=MAPPING_D011_CM, r=1.0, axes=AXES,
                        active_families=COEFFICIENT_FAMILIES, label="d011"))
    for scale, source in (("v14_0.5x", "g6-v14-0.5x"), ("v14_2x", "g6-v14-2x")):
        built.append(Family(group="v14", companion=scale, source=source,
                            mapping=MAPPING_D006_R1, r=1.0, axes=AXES,
                            active_families=COEFFICIENT_FAMILIES, label="v14"))
    return tuple(_check_family(family) for family in built)


def _require_distinct_keys(declared: Sequence[Family]) -> tuple[Family, ...]:
    """Refuse two declared families that share one range-plan family key.

    The sealed range plan is keyed by family, so two families colliding on one
    key would share a plan, a range-id namespace and a records file.  This is
    checked rather than assumed: the key sanitiser maps `CB` and `CS` through
    the contract's restricted alphabet, and a mistake there would silently
    pool two conditions' records.
    """
    keys = [family.key for family in declared]
    _require(len(set(keys)) == len(keys),
             "two declared families share one range-plan family key")
    return tuple(declared)


def families(d013_fired: bool = False) -> tuple[Family, ...]:
    """Every declared family; the D013 package appears only when the trigger fired.

    The protocol runs "all and only `{C, CB, CS, CSB}`" with D013's fixed
    package *if* the trigger fires and none otherwise
    (`GATE_9_STAGE2_PROTOCOL_DRAFT.md:161-163`).
    """
    _require(type(d013_fired) is bool, "d013_fired must be a bool")
    base = _base_families()
    if not d013_fired:
        return _require_distinct_keys(base)
    return _require_distinct_keys(base + tuple(
        _check_family(_d013_family(condition, companion))
        for condition in D013_CONDITIONS
        for companion in ("active", "d011", "v14_0.5x", "v14_2x")
    ))


def d013_package(d013_fired: bool) -> dict[str, tuple[Family, ...]]:
    """The per-condition companion package, keyed by fired D013 condition.

    Each fired condition carries its own active-axis grid plus its own D011
    13-cubed and V-14 0.5x/2x companion grids, none pooled with the primary
    result.  An unfired branch runs none of them.
    """
    _require(type(d013_fired) is bool, "d013_fired must be a bool")
    if not d013_fired:
        return {}
    return {condition: _require_distinct_keys(tuple(
        _check_family(_d013_family(condition, companion))
        for companion in ("active", "d011", "v14_0.5x", "v14_2x")
    )) for condition in D013_CONDITIONS}


def family_space(family: Family, frozen: FrozenAxes) -> CoordinateSpace:
    """The family's coordinate space, with its axis sizes read from the frozen source.

    The counts are not hard-coded here: they are the lengths of the frozen axis
    vectors, so a drifted ledger or a changed `N_axis` refuses instead of
    silently producing a differently sized space.
    """
    _check_family(family)
    _require(isinstance(frozen, FrozenAxes), "a FrozenAxes is required")
    vector = frozen.vector(family.source)
    counts = tuple(len(vector) for _ in family.axes)
    space = CoordinateSpace(family=family, counts=counts)
    _require(all(count >= 1 for count in counts), "a family axis has no coordinates")
    return space


# ---------------------------------------------------------------------------
# The per-coordinate iterator
# ---------------------------------------------------------------------------

def iter_coordinates(space: CoordinateSpace, frozen: FrozenAxes, start: int = 0,
                    stop: int | None = None, with_coefficients: bool = True
                    ) -> Iterator[tuple[int, tuple[int, ...], Any]]:
    """Walk the space's canonical linear order as `(linear, coordinate, coefficients)`.

    The order is the range plan's canonical linear order: linear indices are
    produced ascending and without gaps, and
    `linear = (i0 * n1 + i1) * n2 + i2` over the family's declared axes with the
    last axis fastest.  A `[start, stop)` window is therefore exactly one sealed
    range's slice of that order.
    """
    _require(isinstance(space, CoordinateSpace), "a CoordinateSpace is required")
    _require(isinstance(frozen, FrozenAxes), "a FrozenAxes is required")
    _require(type(with_coefficients) is bool, "with_coefficients must be a bool")
    total = space.total_coordinates
    _index(start, total, "start")
    end = total if stop is None else stop
    _require(type(end) is int and 0 <= end <= total, "stop is outside the coordinate space")
    _require(end >= start, "stop precedes start")
    for linear in range(start, end):
        coordinate = space.coordinate(linear)
        yield (linear, coordinate,
               resolve_coefficients(space.family, coordinate, frozen)
               if with_coefficients else None)


def range_plan(space: CoordinateSpace, bound: BoundIdentity,
                contract_plan: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Seal the space's range plan with the frozen contract.

    `contract.build_range_plan` (`:112-132`) is called, never edited.  The
    family identifier is this module's key and the identity hash is the one the
    injected `validate(payload)` returned — this module derives no identity
    digest of its own.  The plan is re-validated (`:135-144`) and its exact
    `[start, stop)` cover of the space's linear order is checked here, so a
    plan that is canonical but partitions a *different* order is refused.

    `contract_plan` substitutes an already-built plan for the sealed one.  It
    exists so the fixture can present a plan whose cover is broken; the
    production path leaves it `None`, so the sealed plan always comes from the
    frozen contract.
    """
    _require(isinstance(space, CoordinateSpace), "a CoordinateSpace is required")
    _require(isinstance(bound, BoundIdentity), "a BoundIdentity is required")
    total = space.total_coordinates
    _require(contract_plan is None or type(contract_plan) is dict,
             "contract_plan must be a plan dict")
    plan = dict(contract_plan) if contract_plan is not None else contract.build_range_plan(
        space.family.key, total, bound.qualification_identity_sha256)
    # The ordered-cover check below already forces the ranges to end exactly at
    # `total`, so it subsumes a separate `total_coordinates` comparison: a plan
    # declaring a different total cannot produce that cover.  Only the family
    # binding is checked here, since the plan's own family is what names the
    # range-id namespace and records file.
    try:
        _require(plan["family"] == space.family.key,
                 "the sealed plan names a different family")
        expected = 0
        for row in plan["ranges"]:
            _require(row["start"] == expected,
                     "the sealed plan's ranges are not contiguous from zero")
            expected = row["stop"]
        _require(expected == total, "the sealed plan does not exactly cover the linear order")
    except (KeyError, TypeError, ValueError) as exc:
        raise CoordinateRecordError(f"malformed range plan: {exc}") from None
    contract.validate_range_plan(plan)
    return plan


def iter_plan_order(space: CoordinateSpace, frozen: FrozenAxes, plan: Mapping[str, Any],
                    bound: BoundIdentity, with_coefficients: bool = True
                    ) -> Iterator[tuple[str, int, tuple[int, ...], Any]]:
    """Walk the sealed plan's ranges in order as `(batch_id, linear, coordinate, coefficients)`.

    The yielded linear indices must be exactly `0 … total-1` ascending.  The
    caller compares that against an independently enumerated order; this
    function only guarantees it, so the comparison is a real test.
    """
    _require(isinstance(space, CoordinateSpace), "a CoordinateSpace is required")
    _require(isinstance(frozen, FrozenAxes), "a FrozenAxes is required")
    _require(isinstance(bound, BoundIdentity), "a BoundIdentity is required")
    _require(type(with_coefficients) is bool, "with_coefficients must be a bool")
    validated = contract.validate_range_plan(plan)
    # Family first: it names the range-id namespace and the records file, so a
    # plan for another family must be refused before its size or identity is
    # even considered.  Then the identity binding, then the size.
    _require(validated["family"] == space.family.key,
             "the sealed plan names a different family")
    _require(validated["qualification_identity_sha256"]
             == bound.qualification_identity_sha256,
             "the sealed plan was built under a different production identity")
    _require(validated["total_coordinates"] == space.total_coordinates,
             "the sealed plan does not partition this space")
    for row in validated["ranges"]:
        batch = row["batch_id"]
        for linear, coordinate, coefficients in iter_coordinates(
                space, frozen, row["start"], row["stop"], with_coefficients):
            yield (batch, linear, coordinate, coefficients)


# ---------------------------------------------------------------------------
# Coordinate -> coefficient resolution
# ---------------------------------------------------------------------------

def _read_hex(value: object, label: str) -> float:
    """Parse a committed binary64 hex literal, failing closed and typed.

    A raw `float.fromhex` would raise `ValueError` and escape this module's
    contract, so an unparseable or non-string literal is refused here as this
    module's own typed error.
    """
    _require(type(value) is str, f"{label} must be a hexadecimal binary64 string")
    try:
        parsed = float.fromhex(value)
    except ValueError:
        raise CoordinateRecordError(f"{label} is not a hexadecimal binary64 value") from None
    _require(math.isfinite(parsed) or parsed == 0.0, f"{label} is not a finite binary64")
    return parsed


def validate_coefficient_entry(name: str, entry: Mapping[str, Any],
                               expected_active: bool) -> dict[str, Any]:
    """Validate one coefficient family entry and return it unchanged.

    The entry must be a dict whose ``active`` flag is exactly
    ``expected_active``, whose every other value is a lowercase binary64 hex
    string, and — when inactive — must be the *positive* zero in every slot.
    Each stored value is read back with `float.fromhex`, so this is a real
    numeric assertion: a substituted ``-0.0``, a non-zero coefficient, or a
    malformed hex string is refused.
    """
    _require(type(name) is str and name in COEFFICIENT_FAMILIES,
             f"unknown coefficient family {name!r}")
    _require(type(entry) is dict and entry.get("active") is expected_active,
             f"coefficient family {name!r} activity disagrees with the family")
    # One pass, one gate per coefficient.  `_read_hex` requires a `str` and a
    # parseable hexadecimal binary64 literal; for an inactive family the parsed
    # value must additionally be the *positive* zero.  A single loop avoids two
    # passes over the same slots, where the second would shadow the first.
    for key, value in entry.items():
        if key == "active":
            continue
        parsed = _read_hex(value, f"coefficient {name!r}.{key}")
        if not expected_active:
            _require(_positive_zero(parsed),
                     f"inactive family {name!r} coefficient {key!r} is not +0.0")
    return dict(entry)


def _inactive_coefficients() -> dict[str, Any]:
    """A D013-inactive penalty family: every coefficient exactly `+0.0`.

    The coefficient is the *positive* zero and the register is retained, so the
    raw domain gains the multiplicity factors the WP6 evaluator records
    (`…SPEC_OWNER_DECISION.md:33-37`).  This module records the zero and never
    enumerates the retained register.
    """
    return {"active": False, "a_hex": ZERO_HEX, "lambda_slack_hex": ZERO_HEX,
            "lambda_1_hex": ZERO_HEX, "lambda_2_hex": ZERO_HEX}


def _axis_ledger_coefficients(mapping: str, axis: str, value: float,
                              lambda_ref: float) -> dict[str, Any]:
    """Resolve one active penalty family through the frozen `src/g6` functions.

    `ledgers._axis_coefficients_d006_r1` (`:174-192`) is the frozen r=1
    primitive transcription, used by the V-14 companions and, with `v = 1.0`
    for the sector row and `v = 5.0` for the budget row, exactly as
    `ledgers._coefficient_ledger` (`:216-231`) calls it.
    `ledgers._axis_coefficients_d011_cm` (`:195-208`) is D011's approved
    `a = 2` curvature-match mapping.  Each is called with the family's own
    `Lambda_ref`; neither is re-derived here.
    """
    violation = 1.0 if axis == SECTOR else 5.0
    if mapping == MAPPING_D011_CM:
        produced = ledgers._axis_coefficients_d011_cm(value, lambda_ref, violation)
        a_hex = produced["a_fixed_hex"]
    else:
        produced = ledgers._axis_coefficients_d006_r1(value, lambda_ref, violation)
        a_hex = produced["a_r_hex"]
    return {"active": True, "a_hex": a_hex,
            "lambda_slack_hex": produced["lambda_slack_hex"],
            "lambda_1_hex": produced["lambda_1_hex"],
            "lambda_2_hex": produced["lambda_2_hex"]}


def _axis_r_coefficient(r: float, s: float) -> float:
    """The `a_r` that `core_pass._coefficient_family` (`:118-124`) uses for this `r`.

    That frozen sequence is
    ``t0 = fl(2*s)``; ``den = fl(sqrt(fl(fl(r*r) + t0)) + r)``; ``a = fl(t0/den)``.
    It is the `a` behind `lambda_1 = fl(fl(lambda_ref*a)/v)` and
    `lambda_2 = fl(fl(lambda_ref*fl(a*a))/fl(2*v2))`, so the committed `a_hex`
    must be *this* `a` for the family's `r`, not the `r = 1` value the `src/g6`
    transcription produces.  For `r = 1` the two coincide, which is exactly
    what `ledgers._axis_coefficients_d006_r1` (`:174-192`) is a transcription
    of; the frozen G5 producer and G6 ledger each own their conformance checks.
    """
    two_s = float(2.0 * s)
    denominator = float(math.sqrt(float(float(r * r) + two_s)) + r)
    a = float(two_s / denominator)
    return a


def _full_axis_coefficients(family: Family, values: tuple[float, ...],
                            lambda_ref: float) -> dict[str, Any]:
    """A three-axis d006_r1 family's coefficients, from `core_pass.derive_coefficients`.

    `src/g5/core_pass.py:127-139` with its frozen primitive sequence
    `_coefficient_family` (`:118-124`) is the producer the engine is fed from,
    so the primary CSB family and the r=1 companions resolve through it rather
    than through the r=1-only ledger transcription alone.

    The `lambda_slack` terms are `r`-independent (`fl(fl(s*lambda_ref)/v2)`) and
    come from the frozen `src/g6` transcription either way; `a_hex`, `lambda_1`
    and `lambda_2` are `r`-dependent and come from `derive_coefficients`.  For
    `r = 1` the two sources agree bit-for-bit under the frozen
    `core_pass._require_r1_ledger_conformance` (`:142-154`).
    """
    s_card, s_sector, s_budget = values
    derived = core_pass.derive_coefficients(family.r, s_card, s_sector, s_budget, lambda_ref)

    sector = _axis_ledger_coefficients(MAPPING_D006_R1, SECTOR, s_sector, lambda_ref)
    budget = _axis_ledger_coefficients(MAPPING_D006_R1, BUDGET, s_budget, lambda_ref)
    resolved = {
        CARDINALITY: {"active": True,
                      "alpha_hex": ledgers._cardinality_coefficients(
                          s_card, lambda_ref)["alpha_hex"]},
        SECTOR: sector,
        BUDGET: budget,
    }
    # The r-dependent half is the engine's own output, keyed by this family's r.
    for axis, s_value, derived_names in (
            (SECTOR, s_sector, ("sector_slack", "sector_linear", "sector_quadratic")),
            (BUDGET, s_budget, ("budget_slack", "budget_linear", "budget_quadratic"))):
        a_r = _axis_r_coefficient(family.r, s_value)
        resolved[axis]["a_hex"] = a_r.hex()
        resolved[axis]["lambda_1_hex"] = getattr(derived, derived_names[1]).hex()
        resolved[axis]["lambda_2_hex"] = getattr(derived, derived_names[2]).hex()
        # lambda_slack is r-independent: derive_coefficients must agree with the
        # frozen src/g6 transcription for every r, not only r = 1.
    return resolved


def resolve_coefficients(family: Family, coordinate: Sequence[int],
                         frozen: FrozenAxes) -> dict[str, Any]:
    """Resolve one coordinate of one family into its full coefficient record.

    The record is committable: every numeric value is a lowercase binary64 hex
    string or an `int`, and the only `bool` leaves are the per-family `active`
    flags.  An inactive D013 family's four coefficients are exactly `+0.0`; an
    active family's come from the frozen `src/g6` or `src/g5` functions cited on
    the helpers above.
    """
    _check_family(family)
    _require(isinstance(frozen, FrozenAxes), "a FrozenAxes is required")
    lambda_ref = frozen.lambda_ref
    _require(type(lambda_ref) is float and math.isfinite(lambda_ref) and lambda_ref > 0.0,
             "Lambda_ref must be a finite positive binary64")
    vector = frozen.vector(family.source)
    _require(type(coordinate) is tuple and len(coordinate) == len(family.axes),
             "coordinate does not match the family's declared axes")
    for position, value in enumerate(coordinate):
        _index(value, len(vector), f"coordinate axis {family.axes[position]!r}")
    values = tuple(vector[value] for value in coordinate)
    for position, value in enumerate(values):
        _require(type(value) is float and math.isfinite(value) and value > 0.0,
                 f"frozen axis value {family.axes[position]!r} is not a positive binary64")

    if family.mapping == MAPPING_D011_CM:
        by_axis = dict(zip(family.axes, values, strict=True))
        resolved = {
            CARDINALITY: {"active": True,
                          "alpha_hex": ledgers._cardinality_coefficients(
                              by_axis["ell_card"], lambda_ref)["alpha_hex"]},
            SECTOR: _axis_ledger_coefficients(MAPPING_D011_CM, SECTOR,
                                              by_axis["ell_sector"], lambda_ref),
            BUDGET: _axis_ledger_coefficients(MAPPING_D011_CM, BUDGET,
                                              by_axis["ell_budget"], lambda_ref),
        }
    elif len(family.axes) == len(AXES):
        resolved = _full_axis_coefficients(family, values, lambda_ref)
    else:
        by_axis = dict(zip(family.axes, values, strict=True))
        resolved = {CARDINALITY: {"active": True,
                                  "alpha_hex": ledgers._cardinality_coefficients(
                                      by_axis["ell_card"], lambda_ref)["alpha_hex"]}}
        for name, axis in ((SECTOR, "ell_sector"), (BUDGET, "ell_budget")):
            if name not in family.active_families:
                resolved[name] = _inactive_coefficients()
            else:
                resolved[name] = _axis_ledger_coefficients(
                    family.mapping, name, by_axis[axis], lambda_ref)

    for name, entry in resolved.items():
        validate_coefficient_entry(name, entry, name in family.active_families)
    return resolved


# ---------------------------------------------------------------------------
# Per-coordinate record construction (D015/D016)
# ---------------------------------------------------------------------------

def _canonical(payload: object) -> bytes:
    """The frozen committable encoding; a refusal here is re-raised as ours."""
    try:
        return stage2_sampled_verification.canonical(payload)
    except stage2_sampled_verification.VerificationError as exc:
        raise CoordinateRecordError(
            f"record is not canonically committable: {exc}") from None


def _build_body(space: CoordinateSpace, linear: int, coordinate: tuple[int, ...],
                frozen: FrozenAxes, reconstruction: Mapping[str, Any]) -> dict[str, Any]:
    family = space.family
    vector = frozen.vector(family.source)
    return {
        "schema": RECORD_SCHEMA,
        "family": family.key,
        "group": family.group,
        "companion": family.companion,
        "condition": family.condition,
        "r_hex": family.r_hex,
        "mapping": family.mapping,
        "coordinate": {axis: value
                       for axis, value in zip(family.axes, coordinate, strict=True)},
        "coordinate_label": space.label(coordinate),
        "coordinate_binary64_hex": {
            axis: vector[value].hex()
            for axis, value in zip(family.axes, coordinate, strict=True)},
        "linear_index": linear,
        "coefficients": resolve_coefficients(family, coordinate, frozen),
        "reconstruction": dict(reconstruction),
    }


def _reconstruct(core_result: Mapping[str, Any], slack: Any,
                 classifiers: Mapping[int, DecodedClassifier],
                 f_star: float, lambda_ref: float) -> dict[str, Any]:
    """Call the frozen host-side D015/D016 reconstruction.

    `stage2_cuda_reconstruct.reconstruct_pair` (`:223-276`) is the frozen
    reconstructor: it reads only the engine's minima/tie data and the validated
    slack offsets, and labels through the frozen `src/g4/classification.py`
    classifier, as the approved amendment assigns (`:55-56`).  No tie set is
    re-derived from energies and no full-domain enumeration happens.
    """
    try:
        reconstruction = stage2_cuda_reconstruct.reconstruct_pair(
            core_result, slack, classifiers, f_star, lambda_ref)
    except stage2_cuda_reconstruct.ReconstructionError as exc:
        raise CoordinateRecordError(
            f"frozen D015/D016 reconstruction refused the engine result: {exc}") from None
    # `reconstruct_pair` owns the shape and comparator guarantees.  Rechecking
    # its fixed output here would make an unreachable guard.
    return reconstruction


def _comparator_of(summary: Mapping[str, Any]) -> tuple[int, int]:
    """The `(c_H, c_f)` a reconstructed summary was computed under."""
    _require(type(summary) is dict, "a reconstructed summary must be a dict")
    return (summary.get("c_H"), summary.get("c_f"))


def _pair_of_key(key: str) -> tuple[int, int]:
    """Parse a frozen ``c_H=…__c_f=…`` diagnostic key back to its pair."""
    _require(type(key) is str, f"malformed D015 diagnostic key {key!r}")
    parts = key.split("__c_f=")
    _require(len(parts) == 2 and parts[0].startswith("c_H="),
             f"malformed D015 diagnostic key {key!r}")
    try:
        return (int(parts[0][len("c_H="):]), int(parts[1]))
    except ValueError:
        raise CoordinateRecordError(f"malformed D015 diagnostic key {key!r}") from None


def build_record(space: CoordinateSpace, linear: int, frozen: FrozenAxes,
                 core_result: Mapping[str, Any], slack: Any,
                 classifiers: Mapping[int, DecodedClassifier],
                 f_star: float, lambda_ref: float,
                 bound: BoundIdentity | None = None,
                 session_identity: Any = None) -> dict[str, Any]:
    """Build one committed coordinate record from the engine's bounded result.

    The returned record is in canonical committable form: it contains only
    `None | bool | int | str | list | dict` and is encoded with
    `stage2_sampled_verification.canonical` before `content_sha256` is taken
    over the encoded bytes, so the committed hash is the commitment.

    When `bound` is supplied, the §B item 1 pre-write recheck runs first: the
    caller's `session_identity` is handed to the injected
    `exact_match(session, accepted)`, which raises on any difference.  The
    session identity is the caller's live session payload and is deliberately
    **not** committed into the record — this module never derives it and never
    stores a value the caller did not supply.
    """
    _require(isinstance(space, CoordinateSpace), "a CoordinateSpace is required")
    _require(isinstance(frozen, FrozenAxes), "a FrozenAxes is required")
    coordinate = space.coordinate(linear)
    if bound is not None:
        _require(isinstance(bound, BoundIdentity), "a BoundIdentity is required")
        # A missing session identity is refused here rather than handed to
        # `exact_match`: the injected callable is WP1's, and this module must not
        # depend on it happening to reject `None`.  The guard is what makes
        # "a record was written on a session that was never compared"
        # unreachable, independently of the injected implementation.
        _require(session_identity is not None,
                 "a pre-write recheck needs the caller's session identity")
        bound.recheck(session_identity)
    body = _build_body(space, linear, coordinate, frozen,
                       _reconstruct(core_result, slack, classifiers, f_star, lambda_ref))
    record = dict(body)
    record["content_sha256"] = hashlib.sha256(_canonical(body)).hexdigest()
    return record


def validate_record(record: Mapping[str, Any], space: CoordinateSpace, frozen: FrozenAxes,
                    core_result: Mapping[str, Any], slack: Any,
                    classifiers: Mapping[int, DecodedClassifier],
                    f_star: float, lambda_ref: float,
                    bound: BoundIdentity | None = None,
                    session_identity: Any = None) -> str:
    """Replay a record against its inputs and return its content hash.

    Two independent things are checked.  First the stored commitment: the
    record's `content_sha256` must be a lowercase SHA-256 taken over the
    canonical bytes of its own body.  Then the record is *rebuilt* — coordinate
    from the linear index, the frozen coefficient resolution, and the whole
    frozen D015/D016 reconstruction — and the rebuilt body must equal the
    stored one field for field.  That single equality subsumes per-field
    checks, so a record whose coordinate, coefficients, family, `r`, schema,
    label or any reconstructed value drifted is refused, and no field is
    trusted merely because the hash matched.

    When `bound` is supplied, the §B item 1 pre-write recheck runs against the
    injected production identity as well.
    """
    _require(isinstance(record, dict), "a record dict is required")
    _require(type(space) is CoordinateSpace, "a CoordinateSpace is required")
    _require(isinstance(frozen, FrozenAxes), "a FrozenAxes is required")
    # The §B item 1 pre-write recheck runs first and unconditionally, before any
    # value in the record is trusted: a record is never replayed on a session
    # that was not compared against the accepted identity.
    if bound is not None:
        _require(isinstance(bound, BoundIdentity), "a BoundIdentity is required")
        _require(session_identity is not None,
                 "a pre-write recheck needs the caller's session identity")
        bound.recheck(session_identity)
    # The stored commitment is checked next.  Comparing it to the hash of the
    # canonical body subsumes a separate shape test: `hexdigest()` always
    # yields exactly 64 lowercase hex characters, so a digest that survives
    # this equality is a well-formed lowercase SHA-256 by construction.
    observed = record.get("content_sha256")
    body = {key: value for key, value in record.items() if key != "content_sha256"}
    _require(hashlib.sha256(_canonical(body)).hexdigest() == observed,
             "record content hash does not match its canonical body")
    linear = record.get("linear_index")
    # `coordinate` applies the shared typed index gate.
    coordinate = space.coordinate(linear)
    rebuilt = _build_body(space, linear, coordinate, frozen,
                          _reconstruct(core_result, slack, classifiers, f_star, lambda_ref))
    _require(_canonical(body) == _canonical(rebuilt),
             "record differs from its own rebuilt reconstruction")
    return observed
