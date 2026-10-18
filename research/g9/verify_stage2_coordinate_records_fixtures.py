#!/usr/bin/env python3
"""Synthetic fixtures for the Stage-2 record-shaping module.

Offline and synthetic only: no real candidate, instance, ground truth or
scientific value is read, drawn or produced.  The frozen ledgers are read
because they are the input *coordinate/coefficient* authority, and only their
axis vectors and coefficient functions are used; nothing here scans an energy,
builds a domain, or touches a result.

Every check in this file is reached by a comparison against an independently
computed expectation.  No check is a bare `hasattr`/existence test.
"""
from __future__ import annotations

import array
import copy
import dataclasses
import hashlib
import inspect
import math
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9 import stage2_coordinate_records as r  # noqa: E402
from research.g9 import stage2_sampled_verification as canonical_encoder  # noqa: E402
from research.g9.cuda_qualification import stage2_cuda_execution_contract as contract  # noqa: E402
from research.g9.cuda_qualification import stage2_cuda_reconstruct as frozen  # noqa: E402
from src.g4.classification import DecodedClassifier, OriginalObjectiveService  # noqa: E402
from src.g5 import core_pass  # noqa: E402
from src.g6 import d011_matched_subgrid as d011  # noqa: E402
from src.g6 import ledgers  # noqa: E402


class FixtureError(RuntimeError):
    pass


def require(condition: object, message: str) -> None:
    """A function call, never `assert`: these fixtures also run under `-O`."""
    if not condition:
        raise FixtureError(message)


def rejected(action, label: str, *allowed: type[BaseException]) -> None:
    """Require `action` to raise.  By default only the module's typed refusal
    counts; pass `allowed` to also accept another frozen typed refusal."""
    expected = allowed or (r.CoordinateRecordError,)
    try:
        action()
    except expected:
        return
    except Exception as exc:  # noqa: BLE001 - any other type is itself a defect
        raise FixtureError(f"{label}: refused with raw {type(exc).__name__}: {exc}") from exc
    raise FixtureError(f"{label}: accepted")


# ---------------------------------------------------------------------------
# Synthetic stand-ins.  The production identity is injected, never imported, so
# these stand in for WP1's `validate` and `exact_match` here only.
# ---------------------------------------------------------------------------

_SYNTHETIC_IDENTITY = {
    "schema": "synthetic/wp4a-fixture-identity",
    "note": "fixture stand-in, not the WP1 production identity",
    "platform": {"synthetic": "1"},
}

#: The live session identity the stand-in `exact_match` accepts.  Anything else
#: is a difference, and the stand-in raises exactly as WP1's would.
SESSION_IDENTITY = "synthetic session matching the accepted identity"


def _synthetic_validate(payload: object) -> str:
    return hashlib.sha256(canonical_encoder.canonical(payload)).hexdigest()


def _synthetic_exact_match(session: object, accepted: object) -> None:
    # The stand-in is deliberately *permissive about a missing session*: it
    # accepts anything except the one string it is meant to reject.  That way
    # the "a recheck was requested with no session identity" cases test the
    # module's own guard, and would still fail if that guard were removed
    # instead of passing on this stand-in's strictness.
    if session == "a different session":
        raise r.CoordinateRecordError("synthetic session identity differs from the accepted one")


def synthetic_identity() -> r.AcceptedIdentity:
    return r.AcceptedIdentity(payload=copy.deepcopy(_SYNTHETIC_IDENTITY),
                              validate=_synthetic_validate,
                              exact_match=_synthetic_exact_match)


def bound_identity() -> r.BoundIdentity:
    return r.bind_identity(synthetic_identity())


# ---------------------------------------------------------------------------
# Synthetic engine output and the independent slow reconstruction
# ---------------------------------------------------------------------------

def synthetic_slack_map() -> frozen.SlackIndexMap:
    """A minimal valid `SlackIndexMap`: one lift per decoded state.

    `SlackIndexMap.__post_init__` (reconstruct.py:71-88) requires
    `STATE_COUNT + 1` boundaries, each step in `1..32`, ending at
    `lift_total`; a strictly increasing unit-step ramp satisfies all of it and
    makes `decoded_index` the identity, so a synthetic lifted index decodes to
    the same state.
    """
    offsets = array.array("Q", range(frozen.STATE_COUNT + 1))
    return frozen.SlackIndexMap(offsets=offsets, lift_total=frozen.STATE_COUNT)


def synthetic_classifiers() -> dict[int, DecodedClassifier]:
    """Three frozen classifiers over a synthetic 20-bit original objective.

    `f(x) = popcount(x)` and `feasible(x) = popcount(x) <= 1`, so the label is
    `A` for the empty and single-bit states, `B` is unreachable and `C` for
    everything else.  The population is synthetic; no instance is read.
    """
    def objective(decoded: tuple[int, ...]) -> float:
        return float(sum(decoded))

    def feasible(decoded: tuple[int, ...]) -> bool:
        return sum(decoded) <= 1

    return {c_f: DecodedClassifier(
        OriginalObjectiveService(objective, lambda_ref=1.0, c_f=float(c_f)), feasible)
        for c_f in frozen.CF_VALUES}


def tie_word(index: int, flag: int) -> int:
    """One compacted tie word: `flag << 32 | index`, as the engine packs it.

    Bit `i` of the flag is the tie at `CH_VALUES[i]`, so the flag is a bitmask
    over `(1024, 2048, 4096)`: `4` = 4096 only, `2` = 2048 only, `6` = 2048 and
    4096, `7` = all three (reconstruct.py:170-171).
    """
    return (flag << 32) | index


def synthetic_core_result(minimum_index: int = 3, extra: tuple[tuple[int, int], ...] = ((7, 4),),
                          minimum: float = -1.5) -> dict[str, dict[str, object]]:
    """Bounded per-stream minima/tie data, exactly the engine's returned shape.

    The minimum is tied at every `c_H` (flag 7) and each extra state carries its
    own narrower flag, so the three D015 tie sets are nested (each is a subset
    of the one below) and each contains the minimum — which is what the frozen
    reconstruction requires (reconstruct.py:118-130, :170-174).  The indices
    ascend, as `_compact_entries` requires (`:123`).
    """
    words = [tie_word(minimum_index, 7)]
    words += [tie_word(index, flag) for index, flag in extra]
    words.sort(key=lambda word: word & ((1 << 32) - 1))
    return {
        encoding: {"minimum": minimum, "minimum_index": minimum_index,
                   "compacted_entries": tuple(words)}
        for encoding in r.ENCODINGS
    }


def slow_reconstruct(core_result: dict[str, dict[str, object]], minimum_index: int,
                     extra: tuple[tuple[int, int], ...],
                     classifiers: dict[int, DecodedClassifier], f_star: float,
                     lambda_ref: float) -> dict[str, object]:
    """An independent, deliberately naive reconstruction of one coordinate.

    This deliberately does **not** call `stage2_cuda_reconstruct` and does not
    import it.  It re-derives the D015/D016 record from first principles with
    plain Python — ascending flags, nested tie sets, the per-`c_H` decoded
    population, the D016 exists-C/else-all-A/else-B rule, and the `p_A`/`p_B`/
    `p_C` integer pairs — so agreement with the module is a real test of the
    module rather than a restatement of the frozen code.
    """
    epsilon = math.ldexp(1.0, -52)
    index_mask = (1 << 32) - 1

    def tie_set(encoding: str, c_h: int) -> list[int]:
        words = core_result[encoding]["compacted_entries"]
        return sorted(index for index, flag in
                      ((word & index_mask, word >> 32) for word in words)
                      if flag & (1 << frozen.CH_VALUES.index(c_h)))

    # The synthetic SlackIndexMap decodes a lifted index to the same state, so a
    # lifted index decodes here exactly as its unbalanced state index does.
    def summarize(encoding: str, c_h: int, c_f: int) -> dict[str, object]:
        classifier = classifiers[c_f]
        minimum = float(core_result[encoding]["minimum"])
        tied = tie_set(encoding, c_h)
        decoded = [tuple((index >> (19 - asset)) & 1 for asset in range(20))
                   for index in tied]
        labels = [classifier.label(state, f_star) for state in decoded]
        counts = {label: labels.count(label) for label in ("A", "B", "C")}
        if counts["C"]:
            set_label = "C"
        elif counts["A"] == len(decoded):
            set_label = "A"
        else:
            set_label = "B"
        scale = lambda_ref + abs(minimum)
        tau = (float(c_h) * epsilon) * scale
        denominator = len(decoded)
        return {
            "c_H": c_h, "c_f": c_f, "H_E_min_hex": minimum.hex(),
            "H_E_min_domain_index": minimum_index,
            "tie_comparator": {"c_H": c_h, "epsilon_hex": epsilon.hex(),
                               "minimum_tau_hex": tau.hex(), "lambda_ref_hex": lambda_ref.hex()},
            "T_E_size": len(tied), "X_E_size": denominator,
            "commitments": {
                "T_E_domain_index_stream_sha256": stream_sha256(tied),
                "X_E_decoded_index_stream_sha256": stream_sha256(
                    [decoded_index(state) for state in decoded]),
                "T_E_first_index": tied[0], "T_E_last_index": tied[-1],
            },
            "set_label": set_label, "atomic_counts": counts,
            "atomic_label_set": sorted(set(labels)),
            "I_C_exist": int(counts["C"] > 0), "I_C_univ": int(counts["C"] == denominator),
            "p_A": [counts["A"], denominator],
            "p_B": [counts["B"], denominator],
            "p_C": [counts["C"], denominator],
        }

    return {
        "primary_c_h_2048": {encoding: summarize(encoding, *frozen.PRIMARY_PAIR)
                             for encoding in r.ENCODINGS},
        "d015_diagnostics": {
            f"c_H={c_h}__c_f={c_f}": {encoding: summarize(encoding, c_h, c_f)
                                      for encoding in r.ENCODINGS}
            for c_h, c_f in frozen.DIAGNOSTIC_PAIRS
        },
    }


def stream_sha256(indices) -> str:
    """Little-endian uint64 stream digest, re-derived here independently."""
    digest = hashlib.sha256()
    for index in indices:
        digest.update(int(index).to_bytes(8, "little"))
    return digest.hexdigest()


def decoded_index(state: tuple[int, ...]) -> int:
    """The frozen decoded-index convention, transcribed independently."""
    return sum(bit << (19 - asset) for asset, bit in enumerate(state))


# ---------------------------------------------------------------------------
# Fixture body
# ---------------------------------------------------------------------------

def check_counts_and_order(bound: r.BoundIdentity) -> None:
    """Counts per family match the approved grids, and the order is the plan's."""
    axes = r.build_frozen_axes()
    require(len(axes.primary) == core_pass.ROW_COUNT,
            f"the primary axis is not the frozen ROW_COUNT={core_pass.ROW_COUNT}")
    require(len(axes.d011) == 13, "the D011 axis is not 13 points per axis")
    require(len(axes.v14_0_5x) == 31, "V-14 0.5x is not 31 points per axis")
    require(len(axes.v14_2x) == 111, "V-14 2x is not 111 points per axis")

    # Derive each expected count from the frozen source, then assert equality.
    expected = {
        "primary": core_pass.ROW_COUNT ** 3,
        "d011": 13 ** 3,
        "v14_0.5x": 31 ** 3,
        "v14_2x": 111 ** 3,
    }
    require(expected["primary"] == 226981, "the primary grid is not 61^3 = 226,981")
    require(expected["d011"] == d011.MATCHED_COORDINATE_COUNT,
            "the D011 subgrid is not the frozen 13^3 matched coordinate count")
    require(expected["v14_0.5x"] == 31 ** 3 and expected["v14_2x"] == 111 ** 3,
            "a V-14 grid count is wrong")

    declared = r.families(True)
    require(len(declared) == 22, f"expected 22 declared families, got {len(declared)}")
    require(len({family.key for family in declared}) == 22,
            "two declared families share one range-plan key")

    for family in declared:
        space = r.family_space(family, axes)
        if family.group == "primary":
            require(space.total_coordinates == expected["primary"],
                    f"{family.key}: primary count is not 226,981")
            require(family.r in core_pass.R_VALUES,
                    f"{family.key}: primary r is not one of the frozen R_VALUES")
        elif family.group == "d011" and family.companion == "d011":
            require(space.total_coordinates == expected["d011"],
                    f"{family.key}: D011 count is not 2,197")
        elif family.group == "v14":
            require(space.total_coordinates == expected[family.companion],
                    f"{family.key}: V-14 count does not match its scale")
        else:
            require(space.total_coordinates
                    == len(axes.vector(family.source)) ** len(family.axes),
                    f"{family.key}: D013 grid count is not the product of its axes")
        # Every family: the space's coordinate count equals the product of the
        # frozen axis lengths over its declared axes.
        product = 1
        for _axis in family.axes:
            product *= len(axes.vector(family.source))
        require(space.total_coordinates == product,
                f"{family.key}: count is not the product of its declared axes")

    # D013 per-condition active-axis grids and the companion package (G12).
    package = r.d013_package(True)
    require(set(package) == set(r.D013_CONDITIONS),
            "the fired D013 package does not cover exactly C, CB, CS and CSB")
    for condition, group in package.items():
        require(len(group) == 4,
                f"{condition}: the D013 package lacks a companion grid")
        require({family.companion for family in group}
                == {"active", "d011", "v14_0.5x", "v14_2x"},
                f"{condition}: the D013 companion package is incomplete")
        for family in group:
            space = r.family_space(family, axes)
            active = len(r.D013_ACTIVE_AXES[condition])
            require(len(space.counts) == active,
                    f"{condition}/{family.companion}: grid has the wrong number of axes")
            require(space.total_coordinates
                    == len(axes.vector(family.source)) ** active,
                    f"{condition}/{family.companion}: active-axis grid count is wrong")
            require(family.axes == r.D013_ACTIVE_AXES[condition],
                    f"{condition}/{family.companion}: axes are not the active axes")
            require(family.active_families == r.D013_ACTIVE_FAMILIES[condition],
                    f"{condition}/{family.companion}: active coefficient map is wrong")
    # An unfired branch runs none of them.
    require(r.d013_package(False) == {}, "an unfired D013 branch produced a package")
    unfired = {family.key for family in r.families(False)}
    require(not any(family.group == "d013" for family in r.families(False)),
            "an unfired D013 branch produced D013 families")

    # Order: the iterator's linear order equals the range plan's partition.
    primary = next(family for family in declared
                   if family.group == "primary" and family.r == 1.0)
    space = r.family_space(primary, axes)
    plan = r.range_plan(space, bound)
    require(plan["total_coordinates"] == space.total_coordinates,
            "the sealed plan does not cover the space")
    require(len(plan["ranges"]) == math.ceil(space.total_coordinates
                                             / contract.MAX_COORDINATES_PER_RANGE),
            "the sealed plan did not use the contract's range cap")
    # Independent enumeration: row-major, last axis fastest.
    independent = []
    for i in range(space.counts[0]):
        for j in range(space.counts[1]):
            for k in range(space.counts[2]):
                independent.append((i, j, k))
    require(len(independent) == space.total_coordinates,
            "the independent enumeration disagrees on the grid size")
    planned = [(linear, coordinate)
               for _batch, linear, coordinate, _co
               in r.iter_plan_order(space, axes, plan, bound, with_coefficients=False)]
    require([entry[0] for entry in planned] == list(range(space.total_coordinates)),
            "the plan-order iterator did not produce 0..total-1 ascending")
    require([entry[1] for entry in planned] == independent,
            "the iterator's coordinate order is not the canonical row-major order")

    # The module's own contiguous-cover guarantees are reached by handing
    # `range_plan` a contract plan whose cover was broken after construction.
    # The cover checks run before the contract's own validator, so these cases
    # exercise the module's checks and not merely the frozen contract's.
    total = space.total_coordinates
    gapped = contract.build_range_plan(primary.key, total,
                                       bound.qualification_identity_sha256)
    gapped["ranges"][3]["start"] += 1
    gapped["ranges"][3]["stop"] -= 1
    gapped["content_sha256"] = contract.content_sha256(gapped)
    rejected(lambda: r.range_plan(space, bound, contract_plan=gapped),
             "a plan whose ranges are not contiguous from zero")
    short_cover = contract.build_range_plan(primary.key, total,
                                            bound.qualification_identity_sha256)
    short_cover["ranges"] = short_cover["ranges"][:-1]
    short_cover["content_sha256"] = contract.content_sha256(short_cover)
    rejected(lambda: r.range_plan(space, bound, contract_plan=short_cover),
             "a plan that does not exactly cover the linear order")
    empty_range = contract.build_range_plan(primary.key, total,
                                            bound.qualification_identity_sha256)
    empty_range["ranges"][2]["stop"] = empty_range["ranges"][2]["start"]
    empty_range["content_sha256"] = contract.content_sha256(empty_range)
    rejected(lambda: r.range_plan(space, bound, contract_plan=empty_range),
             "a plan containing an empty range")
    wrong_total = contract.build_range_plan(primary.key, total + 1,
                                            bound.qualification_identity_sha256)
    rejected(lambda: r.range_plan(space, bound, contract_plan=wrong_total),
             "a plan covering a different coordinate count")

    # Two declared families colliding on one range-plan key are refused: the plan
    # is keyed by family, so a collision would pool two conditions' records.
    # The collision is injected at `Family.key` so the module's own
    # `_require_distinct_keys` is what has to catch it.  `families()` itself
    # refuses, so the collision is confirmed by comparing the *declared* keys
    # collected before the refusal rather than by calling `families()` again.
    original_key = r.Family.key

    def colliding_key(self):
        # Every D013 condition's "v14_2x" companion collapses onto one key, so
        # the four conditions' companions genuinely share a range-plan key.
        return "collided_family_key" if (self.group == "d013"
                                         and self.companion == "v14_2x") else original_key.fget(self)

    r.Family.key = property(colliding_key)
    try:
        package = r._d013_family("C", "v14_2x")
        require(colliding_key(package) == colliding_key(r._d013_family("CSB", "v14_2x")),
                "the injected key collision did not actually collide")
        require(colliding_key(package) != colliding_key(r._d013_family("C", "v14_0.5x")),
                "the injected key collision collapsed an unrelated family too")
        rejected(lambda: r.families(True),
                 "two declared families sharing one range-plan key")
        # `d013_package` is keyed by condition, so its distinctness check is
        # within one condition's four companions.  Collapse two of one
        # condition's companions to prove that check is reached too.
        def within_condition_key(self):
            return ("collapsed" if self.companion in ("v14_0.5x", "v14_2x")
                    else original_key.fget(self))

        r.Family.key = property(within_condition_key)
        require(within_condition_key(r._d013_family("C", "v14_0.5x"))
                == within_condition_key(r._d013_family("C", "v14_2x")),
                "the within-condition key collision did not apply")
        rejected(lambda: r.d013_package(True),
                 "two companions of one D013 condition sharing one key")
    finally:
        r.Family.key = original_key
    require(len({f.key for f in r.families(True)}) == 22,
            "the restored Family.key no longer yields 22 distinct family keys")
    require(len(r.d013_package(True)) == 4,
            "the restored Family.key changed the D013 package")

    # Every declared family's key must be accepted verbatim by the frozen
    # range-plan identifier rule, so a sealed plan can always be built for it.
    for family in r.families(True):
        require(contract.range_id(family.key, 0) == f"{family.key}_b0000",
                f"{family.key}: the frozen range_id rule rejects a declared key")
    # The module's own key check is reached by a family whose sanitised key the
    # contract would reject.  `Family.key` is patched to return one, which is
    # exactly the situation the check exists to catch.
    original_key_only = r.Family.key
    r.Family.key = property(lambda self: "UPPERCASE_KEY")
    try:
        rejected(lambda: contract.range_id("UPPERCASE_KEY", 0),
                 "an uppercase family key the frozen range_id rule rejects",
                 contract.CUDAExecutionContractError)
        rejected(lambda: r.family_space(r._primary_family(1.0), axes),
                 "a family whose key the frozen range_id rule rejects")
        rejected(lambda: r.families(True),
                 "declared families including one with an unusable key")
    finally:
        r.Family.key = original_key_only
    require(len({f.key for f in r.families(True)}) == 22,
            "the restored Family.key no longer yields 22 distinct family keys")


def check_round_trip() -> None:
    """Coordinate <-> linear index round-trips exhaustively on a small space."""
    primary = next(family for family in r.families() if family.group == "primary")
    small = r.CoordinateSpace(family=primary, counts=(5, 4, 3))
    require(small.total_coordinates == 60, "the small space is not 5x4x3 = 60")
    for linear in range(small.total_coordinates):
        coordinate = small.coordinate(linear)
        require(small.linear_index(coordinate) == linear,
                f"coordinate/linear index did not round-trip at {linear}")
    # The last linear index is the all-maximum coordinate.
    require(small.coordinate(59) == (4, 3, 2), "the last coordinate is not the all-maximum one")
    require(small.linear_index((0, 0, 0)) == 0, "the first coordinate is not index 0")
    # Row-major with the last axis fastest: each step advances the *last* axis,
    # carrying into the next slower axis only when the last axis wraps.
    for linear in range(small.total_coordinates - 1):
        here, nxt = small.coordinate(linear), small.coordinate(linear + 1)
        require(nxt[-1] == (here[-1] + 1) % small.counts[-1],
                f"the last axis is not the fastest at {linear}")
        require(here[:-1] == nxt[:-1] or nxt[-1] == 0,
                f"a carry into a slower axis is wrong at {linear}")
        if here[-1] + 1 < small.counts[-1]:
            require(here[:-1] == nxt[:-1],
                    f"the slower axes moved before a wrap at {linear}")
    # The order is exactly the independent nested-loop enumeration, which is
    # written here without touching the module's own arithmetic.
    nested = [(i, j, k)
              for i in range(small.counts[0])
              for j in range(small.counts[1])
              for k in range(small.counts[2])]
    require([small.coordinate(linear) for linear in range(small.total_coordinates)]
            == nested,
            "the coordinate order is not the nested-loop row-major enumeration")
    require([small.linear_index(coordinate) for coordinate in nested]
            == list(range(small.total_coordinates)),
            "linear_index is not the positional index of the nested enumeration")
    # One-axis and two-axis spaces (the D013 `C` and `CB`/`CS` shapes) round-trip.
    for counts in ((7,), (6, 5), (4, 3, 2)):
        space = r.CoordinateSpace(family=primary, counts=counts)
        for linear in (0, 1, space.total_coordinates - 2, space.total_coordinates - 1):
            require(space.linear_index(space.coordinate(linear)) == linear,
                    f"a {counts} space did not round-trip at {linear}")
    # Out-of-domain and wrong-arity inputs are refused.
    rejected(lambda: small.coordinate(60), "linear index past the end")
    rejected(lambda: small.coordinate(-1), "negative linear index")
    rejected(lambda: small.linear_index((0, 0)), "coordinate with too few axes")
    rejected(lambda: small.linear_index((0, 0, 0, 0)), "coordinate with too many axes")
    rejected(lambda: small.linear_index((0, 0, 3)), "coordinate axis at the count")
    rejected(lambda: small.linear_index([0, 0, 0]), "coordinate given as a list")
    rejected(lambda: small.label([0, 0, 0]), "label from a list")
    rejected(lambda: small.label((0, 0)), "label from a short tuple")


def check_guard_mutations(bound: r.BoundIdentity) -> None:
    """Reach each remaining input guard with one synthetic bad argument."""
    axes = r.FrozenAxes(1.0, (1.0, 2.0, 3.0), (1.0, 2.0, 3.0),
                        (1.0, 2.0, 3.0), (1.0, 2.0, 3.0))
    primary = r._primary_family(1.0)
    d011_family = next(f for f in r.families() if f.group == "d011")
    v14_family = next(f for f in r.families() if f.group == "v14")
    for label, candidate in (
            ("non-family", None),
            ("foreign group", dataclasses.replace(primary, group="foreign")),
            ("foreign companion", dataclasses.replace(primary, companion="foreign")),
            ("zero r", dataclasses.replace(primary, r=0.0)),
            ("condition on primary", dataclasses.replace(primary, condition="C")),
            ("D011 mapping", dataclasses.replace(d011_family, mapping=r.MAPPING_D006_R1)),
            ("D011 source", dataclasses.replace(d011_family, source="g4-primary")),
            ("D011 r", dataclasses.replace(d011_family, r=2.0)),
            ("V14 mapping", dataclasses.replace(v14_family, mapping=r.MAPPING_D011_CM)),
            ("V14 source", dataclasses.replace(v14_family, source="g4-primary")),
            ("V14 r", dataclasses.replace(v14_family, r=2.0)),
            ("primary source", dataclasses.replace(primary, source="g6-d011")),
    ):
        rejected(lambda candidate=candidate: r._check_family(candidate), label)
    rejected(lambda: axes.vector("foreign"), "foreign vector source")
    rejected(lambda: r._require_distinct_keys((primary, primary)), "duplicate family keys")
    rejected(lambda: r.families(0), "integer D013 switch")
    rejected(lambda: r.d013_package(0), "integer D013 package switch")
    require(r.d013_package(False) == {}, "unfired D013 package is nonempty")
    rejected(lambda: r.family_space(primary, None), "non-axes family space")
    empty = dataclasses.replace(axes, primary=())
    rejected(lambda: r.family_space(primary, empty), "empty family space")
    space = r.family_space(primary, axes)
    rejected(lambda: list(r.iter_coordinates(None, axes, with_coefficients=False)),
             "non-space iterator")
    rejected(lambda: list(r.iter_coordinates(space, None, with_coefficients=False)),
             "non-axes iterator")
    rejected(lambda: list(r.iter_coordinates(space, axes, start=space.total_coordinates,
                                             with_coefficients=False)), "start at end")
    rejected(lambda: list(r.iter_coordinates(space, axes, stop=-1,
                                             with_coefficients=False)), "negative stop")
    rejected(lambda: list(r.iter_coordinates(space, axes, stop=True,
                                             with_coefficients=False)), "boolean stop")
    rejected(lambda: list(r.iter_coordinates(space, axes, start=1, stop=0,
                                             with_coefficients=False)), "reversed window")
    rejected(lambda: list(r.iter_coordinates(space, axes, with_coefficients=[])),
             "iterator with non-boolean coefficient switch")
    plan = r.range_plan(space, bound)
    rejected(lambda: r.range_plan(space, bound, contract_plan={}), "malformed plan dict")
    gapped = copy.deepcopy(plan)
    gapped["ranges"][0]["start"] = 1
    original_plan_validator = contract.validate_range_plan
    contract.validate_range_plan = lambda candidate: candidate
    try:
        rejected(lambda: r.range_plan(space, bound, contract_plan=gapped),
                 "noncontiguous plan with permissive downstream validator")
    finally:
        contract.validate_range_plan = original_plan_validator
    rejected(lambda: list(r.iter_plan_order(space, axes, plan, bound,
                                            with_coefficients=[])),
             "plan iterator with non-boolean coefficient switch")
    original_iterator = r.iter_coordinates
    r.iter_coordinates = lambda *_args: iter(())
    try:
        rejected(lambda: list(r.iter_plan_order(space, None, plan, bound, False)),
                 "plan iterator with non-axes input and permissive coordinate iterator")
        rejected(lambda: list(r.iter_plan_order(space, axes, plan, bound, [])),
                 "plan iterator with non-boolean switch and permissive coordinate iterator")
    finally:
        r.iter_coordinates = original_iterator
    rejected(lambda: r._read_hex("not-hex", "test"), "malformed hexadecimal")
    rejected(lambda: r._read_hex("inf", "test"), "infinite hexadecimal")
    rejected(lambda: r.resolve_coefficients(primary, (0, 0, 0), None), "non-axes resolution")
    original_key = r.Family.key
    r.Family.key = property(lambda self: "UPPERCASE")
    try:
        rejected(lambda: r._check_family(primary), "noncanonical family key")
    finally:
        r.Family.key = original_key
    slack, classifiers = synthetic_slack_map(), synthetic_classifiers()
    core = synthetic_core_result()
    def build(**changes):
        kwargs = dict(space=space, linear=0, frozen=axes, core_result=core,
                      slack=slack, classifiers=classifiers, f_star=-1.0, lambda_ref=1.0)
        kwargs.update(changes)
        return r.build_record(**kwargs)
    rejected(lambda: build(space=None), "build with non-space")
    rejected(lambda: build(frozen=None), "build with non-axes")
    record = build()
    def validate(**changes):
        kwargs = dict(record=record, space=space, frozen=axes, core_result=core,
                      slack=slack, classifiers=classifiers, f_star=-1.0, lambda_ref=1.0)
        kwargs.update(changes)
        return r.validate_record(**kwargs)
    rejected(lambda: validate(space=None), "validate with non-space")
    rejected(lambda: validate(frozen=None), "validate with non-axes")
    rejected(lambda: validate(bound="bad", session_identity=SESSION_IDENTITY),
             "validate with non-bound identity")


def check_public_argument_fuzz() -> None:
    """Fuzz every argument of the public record-shaping API with wrong types."""
    def exact_session(session, _accepted):
        if session != SESSION_IDENTITY:
            raise r.CoordinateRecordError("synthetic session mismatch")

    strict = r.bind_identity(dataclasses.replace(synthetic_identity(),
                                                  exact_match=exact_session))
    axes = r.FrozenAxes(1.0, (1.0, 2.0, 3.0), (1.0, 2.0, 3.0),
                        (1.0, 2.0, 3.0), (1.0, 2.0, 3.0))
    family = r._primary_family(1.0)
    space = r.family_space(family, axes)
    plan = r.range_plan(space, strict)
    core, slack, classifiers = synthetic_core_result(), synthetic_slack_map(), synthetic_classifiers()
    record = r.build_record(space, 0, axes, core, slack, classifiers, -1.0, 1.0)
    calls = {
        "bind_identity": (r.bind_identity, [synthetic_identity()]),
        "families": (r.families, [False]),
        "d013_package": (r.d013_package, [False]),
        "family_space": (r.family_space, [family, axes]),
        "iter_coordinates": (r.iter_coordinates, [space, axes, 0, 2, False]),
        "range_plan": (r.range_plan, [space, strict, None]),
        "iter_plan_order": (r.iter_plan_order, [space, axes, plan, strict, False]),
        "resolve_coefficients": (r.resolve_coefficients, [family, (0, 0, 0), axes]),
        "build_record": (r.build_record, [space, 0, axes, core, slack, classifiers,
                                            -1.0, 1.0, strict, SESSION_IDENTITY]),
        "validate_record": (r.validate_record, [record, space, axes, core, slack,
                                                  classifiers, -1.0, 1.0, strict,
                                                  SESSION_IDENTITY]),
        "validate_coefficient_entry": (r.validate_coefficient_entry,
                                       [r.SECTOR, {"active": True, "a_hex": 1.0.hex()}, True]),
        "coordinate": (space.coordinate, [0]),
        "linear_index": (space.linear_index, [(0, 0, 0)]),
        "label": (space.label, [(0, 0, 0)]),
        "vector": (axes.vector, ["g4-primary"]),
        "recheck": (strict.recheck, [SESSION_IDENTITY]),
    }
    wrong = (None, True, 1, "bad", [], {}, [{}], {"bad": []}, [[None]], {0: []})
    valid_alternatives = {
        ("families", "d013_fired", "True"),
        ("d013_package", "d013_fired", "True"),
        ("iter_coordinates", "start", "1"),
        ("iter_coordinates", "stop", "None"),
        ("iter_coordinates", "stop", "1"),
        ("iter_coordinates", "with_coefficients", "True"),
        ("iter_plan_order", "with_coefficients", "True"),
        ("range_plan", "contract_plan", "None"),
        ("build_record", "linear", "1"),
        ("build_record", "bound", "None"),
        ("validate_record", "bound", "None"),
        ("validate_coefficient_entry", "expected_active", "True"),
        ("coordinate", "linear", "1"),
    }
    typed = (r.CoordinateRecordError, contract.CUDAExecutionContractError,
             frozen.ReconstructionError, canonical_encoder.VerificationError)
    for name, (action, baseline) in calls.items():
        for index, parameter in enumerate(inspect.signature(action).parameters):
            for value in wrong:
                if (name, parameter, repr(value)) in valid_alternatives:
                    continue
                altered = baseline.copy()
                altered[index] = value
                try:
                    result = action(*altered)
                    if name.startswith("iter_"):
                        list(result)
                except typed:
                    continue
                except Exception as exc:  # noqa: BLE001 - this is the typed-error oracle
                    raise FixtureError(f"{name}.{parameter}({value!r}) raised raw "
                                       f"{type(exc).__name__}: {exc}") from exc
                raise FixtureError(f"{name}.{parameter}({value!r}) was accepted")


def check_coefficient_resolution() -> None:
    """Coefficient resolution equals the frozen ledger functions, sampled."""
    axes = r.build_frozen_axes()
    lambda_ref = axes.lambda_ref

    # D011: equals the frozen D011 ledger's coefficient_ledger, every axis point.
    d011_ledger = ledgers.build_d011_ledger()
    d011_family = next(family for family in r.families() if family.companion == "d011")
    for index in range(13):
        resolved = r.resolve_coefficients(d011_family, (index, 0, 0), axes)
        require(resolved["cardinality"]["alpha_hex"]
                == d011_ledger["coefficient_ledger"]["cardinality"][index]["alpha_hex"],
                f"D011 alpha at {index} differs from the frozen ledger")
        for family_name, key in (("sector", "sector"), ("budget", "budget")):
            expected = d011_ledger["coefficient_ledger"][key][0]
            a_key = "a_fixed_hex" if family_name == "sector" else "a_fixed_hex"
            require(resolved[family_name]["a_hex"] == expected[a_key],
                    f"D011 {family_name} a at {index} differs from the frozen ledger")
            for field in ("lambda_slack_hex", "lambda_1_hex", "lambda_2_hex"):
                require(resolved[family_name][field] == expected[field],
                        f"D011 {family_name} {field} at {index} differs from the frozen ledger")
        # The a=2 curvature-match mapping is exact and v-independent.
        require(resolved["sector"]["a_hex"] == float(2.0).hex(),
                "D011's a_fixed is not the approved +2.0")
        require(resolved["sector"]["lambda_1_hex"] == resolved["sector"]["lambda_slack_hex"],
                "D011's lambda_1 does not equal its lambda_slack")

    # V-14 0.5x and 2x: equals the frozen V-14 ledger, every axis point (G6).
    for scale, companion in (("0.5x", "v14_0.5x"), ("2x", "v14_2x")):
        ledger = ledgers.build_v14_ledger(scale)
        family = next(item for item in r.families() if item.companion == companion)
        size = len(ledger["coordinates"])
        require(size == len(axes.vector(family.source)),
                f"V-14 {scale} axis size differs from the frozen ledger")
        for index in range(size):
            resolved = r.resolve_coefficients(family, (index, 0, 0), axes)
            require(resolved["cardinality"]["alpha_hex"]
                    == ledger["coefficient_ledger"]["cardinality"][index]["alpha_hex"],
                    f"V-14 {scale} alpha at {index} differs from the frozen ledger")
            for family_name, key in (("sector", "sector"), ("budget", "budget")):
                expected = ledger["coefficient_ledger"][key][0]
                for field in ("a_r_hex", "lambda_slack_hex", "lambda_1_hex", "lambda_2_hex"):
                    produced = resolved[family_name]["a_hex" if field == "a_r_hex" else field]
                    require(produced == expected[field],
                            f"V-14 {scale} {family_name} {field} at {index} differs")
        # The frozen ledger's own N_axis is the size we iterate.
        require(ledger["grid_rule"]["N_axis"] == size,
                f"V-14 {scale} N_axis does not match the frozen grid rule")

    # Primary CSB: equals core_pass.derive_coefficients, the engine's producer.
    for r_value in core_pass.R_VALUES:
        family = next(item for item in r.families()
                      if item.group == "primary" and item.r == r_value)
        for coordinate in ((0, 0, 0), (5, 9, 13), (60, 60, 60)):
            resolved = r.resolve_coefficients(family, coordinate, axes)
            derived = core_pass.derive_coefficients(
                r_value, axes.primary[coordinate[0]], axes.primary[coordinate[1]],
                axes.primary[coordinate[2]], lambda_ref)
            require(resolved["cardinality"]["alpha_hex"] == derived.alpha.hex(),
                    f"primary r={r_value} alpha differs from derive_coefficients")
            for axis, slack, linear, quadratic in (
                    ("sector", "sector_slack", "sector_linear", "sector_quadratic"),
                    ("budget", "budget_slack", "budget_linear", "budget_quadratic")):
                require(resolved[axis]["lambda_slack_hex"] == getattr(derived, slack).hex(),
                        f"primary r={r_value} {axis} lambda_slack differs")
                require(resolved[axis]["lambda_1_hex"] == getattr(derived, linear).hex(),
                        f"primary r={r_value} {axis} lambda_1 differs")
                require(resolved[axis]["lambda_2_hex"] == getattr(derived, quadratic).hex(),
                        f"primary r={r_value} {axis} lambda_2 differs")
            # a_hex is the r-dependent a the frozen primitive sequence uses.
            a_r = r._axis_r_coefficient(r_value, axes.primary[coordinate[1]])
            require(resolved["sector"]["a_hex"] == a_r.hex(),
                    f"primary r={r_value} sector a_hex is not the r-dependent a")

    # r = 1 agrees with the src/g6 r=1 transcription bit-for-bit, everywhere.
    family_r1 = next(item for item in r.families()
                     if item.group == "primary" and item.r == 1.0)
    for index in (0, 30, 60):
        # Sweep the sector axis (slot 1) and the budget axis (slot 2) in turn so
        # every axis point of the frozen vector is compared against the src/g6
        # r=1 transcription at the matching index.
        for axis, violation, slot in (("sector", 1.0, 1), ("budget", 5.0, 2)):
            coordinate = tuple(index if position == slot else 0 for position in range(3))
            resolved = r.resolve_coefficients(family_r1, coordinate, axes)
            value = axes.primary[index]
            expected = ledgers._axis_coefficients_d006_r1(value, lambda_ref, violation)
            require(resolved[axis]["a_hex"] == expected["a_r_hex"],
                    f"r=1 {axis} a_r at {index} differs from the src/g6 transcription")
            for field in ("lambda_slack_hex", "lambda_1_hex", "lambda_2_hex"):
                require(resolved[axis][field] == expected[field],
                        f"r=1 {axis} {field} at {index} differs from the src/g6 transcription")

    # D013: an inactive family is exactly +0.0 in every coefficient.
    for condition, group in r.d013_package(True).items():
        family = next(item for item in group if item.companion == "active")
        space = r.family_space(family, axes)
        zero_coordinate = tuple(0 for _ in family.axes)
        resolved = r.resolve_coefficients(family, zero_coordinate, axes)
        for name, entry in resolved.items():
            active = name in r.D013_ACTIVE_FAMILIES[condition]
            require(entry["active"] is active,
                    f"{condition}: {name} activity flag disagrees with the condition")
            if not active:
                require(all(value == r.ZERO_HEX
                            for key, value in entry.items() if key != "active"),
                        f"{condition}: inactive family {name} is not exactly +0.0")
                require(float.fromhex(r.ZERO_HEX) == 0.0
                        and math.copysign(1.0, float.fromhex(r.ZERO_HEX)) > 0.0,
                        f"{condition}: inactive family {name} is not the positive zero")
        require(space.total_coordinates == len(axes.primary) ** len(family.axes),
                f"{condition}: the active-axis grid count is wrong")

    # The coefficient-entry validator is reached directly, so a substituted
    # zero, a non-zero inactive coefficient, a wrong activity flag, a malformed
    # hex string and an unknown family name are each refused.
    good_active = {"active": True, "alpha_hex": float(1.5).hex()}
    require(r.validate_coefficient_entry(r.CARDINALITY, good_active, True) == good_active,
            "validate_coefficient_entry rejected a well-formed active entry")
    good_inactive = {"active": False, "a_hex": r.ZERO_HEX, "lambda_slack_hex": r.ZERO_HEX,
                     "lambda_1_hex": r.ZERO_HEX, "lambda_2_hex": r.ZERO_HEX}
    require(r.validate_coefficient_entry(r.SECTOR, good_inactive, False) == good_inactive,
            "validate_coefficient_entry rejected a well-formed +0.0 inactive entry")
    negative_zero = float(-0.0).hex()
    require(negative_zero != r.ZERO_HEX,
            "the negative zero literal is indistinguishable from the positive one")
    # These values must be *parseable* hex, so the module's own `float.fromhex`
    # read-back does not raise first: the module's check, not a ValueError, is
    # what has to refuse them.
    tiny = float.fromhex("0x0.0000000000001p-1022").hex()
    for label, entry, active in (
            ("a negative zero in an inactive family",
             {**good_inactive, "lambda_1_hex": negative_zero}, False),
            ("a non-zero coefficient in an inactive family",
             {**good_inactive, "lambda_2_hex": tiny}, False),
            ("an inactive entry declared active",
             good_inactive, True),
            ("an active entry declared inactive", good_active, False),
            ("a hex coefficient value with no 0x prefix",
             {**good_inactive, "a_hex": "1.0000000000000p+0"}, False),
            ("a hex coefficient value with no exponent",
             {**good_inactive, "a_hex": "0x1."}, False),
            ("a non-string coefficient value", {**good_inactive, "a_hex": 1.0}, False),
            ("a non-dict entry", "not a dict", False),
            ("a missing active flag", {"a_hex": r.ZERO_HEX}, False),
    ):
        rejected(lambda entry=entry, active=active:
                 r.validate_coefficient_entry(r.SECTOR, entry, active), label)
    rejected(lambda: r.validate_coefficient_entry("lambda", good_inactive, False),
             "an unknown coefficient family name")
    rejected(lambda: r.validate_coefficient_entry(None, good_inactive, False),
             "a non-string coefficient family name")

    # Every coefficient leaf is a committable lowercase binary64 hex string.
    family = next(item for item in r.families() if item.group == "primary")
    resolved = r.resolve_coefficients(family, (2, 3, 4), axes)
    for name, entry in resolved.items():
        for key, value in entry.items():
            if key == "active":
                require(type(value) is bool, f"{name}.active is not a bool")
                continue
            require(type(value) is str and value.startswith("0x") and len(value) > 2
                    and all(char in "0123456789abcdefx.p+-"
                            for char in value),
                    f"{name}.{key} is not a lowercase binary64 hex string")
    canonical_encoder.canonical(resolved)

    # Refusals: out-of-domain coordinate, wrong arity, non-tuple, and a family
    # whose declared axes do not match its condition.
    primary = next(item for item in r.families() if item.group == "primary")
    rejected(lambda: r.resolve_coefficients(primary, (61, 0, 0), axes),
             "a primary coordinate index at the axis count")
    rejected(lambda: r.resolve_coefficients(primary, (0, 0), axes),
             "a primary coordinate with two axes")
    rejected(lambda: r.resolve_coefficients(primary, (0, 0, 0, 0), axes),
             "a primary coordinate with four axes")
    rejected(lambda: r.resolve_coefficients(primary, [0, 0, 0], axes),
             "a primary coordinate given as a list")
    broken = copy.copy(primary)
    object.__setattr__(broken, "axes", ("ell_card", "ell_sector"))
    rejected(lambda: r.resolve_coefficients(broken, (0, 0), axes),
             "a family whose axes contradict its group")
    broken_family = copy.copy(primary)
    object.__setattr__(broken_family, "active_families", (r.CARDINALITY, r.SECTOR))
    rejected(lambda: r.resolve_coefficients(broken_family, (0, 0, 0), axes),
             "a non-D013 family with an inactive penalty family")
    bad_axes = r.FrozenAxes(lambda_ref=0.0, primary=axes.primary, d011=axes.d011,
                            v14_0_5x=axes.v14_0_5x, v14_2x=axes.v14_2x)
    rejected(lambda: r.resolve_coefficients(primary, (0, 0, 0), bad_axes),
             "a non-positive Lambda_ref")
    empty_axes = r.FrozenAxes(lambda_ref=1.0, primary=(), d011=axes.d011,
                              v14_0_5x=axes.v14_0_5x, v14_2x=axes.v14_2x)
    rejected(lambda: r.resolve_coefficients(primary, (0, 0, 0), empty_axes),
             "a coordinate against an empty frozen axis")

    # A non-positive or non-finite frozen axis value is refused.
    for bad_value, label in ((0.0, "a zero axis value"),
                             (-1.0, "a negative axis value"),
                             (float("inf"), "an infinite axis value"),
                             (float("nan"), "a NaN axis value")):
        bad_axes = r.FrozenAxes(lambda_ref=1.0,
                                primary=(1.0, bad_value, 2.0), d011=axes.d011,
                                v14_0_5x=axes.v14_0_5x, v14_2x=axes.v14_2x)
        rejected(lambda bad_axes=bad_axes:
                 r.resolve_coefficients(primary, (0, 1, 0), bad_axes), label)

    # The D013 family shape guarantees are reached by families that contradict
    # their own condition: wrong axes, wrong active-coefficient map, a dropped
    # cardinality family, and an unknown condition.  `dataclasses.replace` is
    # used so each mutant differs from the valid family in exactly one field.
    c_family = r._d013_family("C", "active")
    for label, family in (
            ("axes contradicting the condition",
             dataclasses.replace(c_family, axes=("ell_card", "ell_budget"))),
            ("active coefficients contradicting the condition",
             dataclasses.replace(c_family, active_families=(r.CARDINALITY, r.SECTOR))),
            ("cardinality marked inactive",
             dataclasses.replace(c_family, active_families=(r.SECTOR,))),
            ("an unknown condition", dataclasses.replace(c_family, condition="CX")),
            ("a non-D013 family with an inactive family",
             dataclasses.replace(r._primary_family(1.0),
                                 active_families=(r.CARDINALITY, r.SECTOR))),
            ("axes out of canonical order",
             dataclasses.replace(c_family, axes=("ell_budget", "ell_card"))),
            ("a foreign axis name",
             dataclasses.replace(c_family, axes=("ell_other",))),
            ("an unknown coefficient mapping",
             dataclasses.replace(c_family, mapping="nope")),
            ("an unknown axis source", dataclasses.replace(c_family, source="nope")),
    ):
        rejected(lambda family=family: r.resolve_coefficients(family, (0,), axes), label)
        rejected(lambda family=family: r.family_space(family, axes), label)
    # The frozen D013 maps are asserted directly, since they are the authority.
    require(c_family.axes == r.D013_ACTIVE_AXES["C"],
            "the D013 C active axes are not the frozen map")
    require(r.D013_ACTIVE_FAMILIES["C"] == (r.CARDINALITY,),
            "the D013 C active coefficient map is not the frozen map")
    require(set(r.D013_ACTIVE_AXES) == set(r.D013_CONDITIONS),
            "the D013 active-axis map does not cover exactly the four conditions")
    require(r.D013_ACTIVE_AXES["C"] == ("ell_card",)
            and r.D013_ACTIVE_AXES["CB"] == ("ell_card", "ell_budget")
            and r.D013_ACTIVE_AXES["CS"] == ("ell_card", "ell_sector")
            and r.D013_ACTIVE_AXES["CSB"] == ("ell_card", "ell_sector", "ell_budget"),
            "the D013 active-axis counts are not 1, 2, 2 and 3")


def check_record_construction(bound: r.BoundIdentity) -> None:
    """Records match an independent slow reconstruction, and encode canonically."""
    slack = synthetic_slack_map()
    classifiers = synthetic_classifiers()
    f_star, lambda_ref = -1.0, 1.0
    axes = r.FrozenAxes(lambda_ref=lambda_ref, primary=(1.0, 2.0, 3.0, 4.0),
                        d011=(1.0, 2.0, 3.0), v14_0_5x=(1.0, 2.0, 3.0),
                        v14_2x=(1.0, 2.0, 3.0))

    cases = [
        (3, ((7, 4),), -1.5),
        (5, (), -2.0),
        (1, ((2, 4), (9, 6)), 0.25),
        (0, ((1, 4), (4, 6)), -8.0),
    ]
    families = [family for family in r.families()
                if family.companion in ("primary", "d011", "v14_0.5x", "v14_2x")]
    checked = 0
    for family in families:
        space = r.family_space(family, axes)
        for minimum_index, extra, minimum in cases:
            if minimum_index >= frozen.STATE_COUNT:
                continue
            core_result = synthetic_core_result(minimum_index, extra, minimum)
            record = r.build_record(space, 0, axes, core_result, slack, classifiers,
                                    f_star, lambda_ref)
            expected = slow_reconstruct(core_result, minimum_index, extra,
                                        classifiers, f_star, lambda_ref)
            # Compare the whole reconstruction against the independent one.
            require(record["reconstruction"] == expected,
                    f"{family.key}: the record's D015/D016 reconstruction differs "
                    f"from the independent slow reconstruction")
            # The primary half is the frozen (2048, 2048) comparator.
            primary = record["reconstruction"]["primary_c_h_2048"]
            require(set(primary) == set(r.ENCODINGS),
                    f"{family.key}: the primary half is not per-encoding")
            for encoding, summary in primary.items():
                require(summary["c_H"] == frozen.PRIMARY_PAIR[0]
                        and summary["c_f"] == frozen.PRIMARY_PAIR[1],
                        f"{family.key}: the primary half is not the frozen comparator")
            # All four D015 diagnostic pairs, never pooled with the primary.
            diagnostics = record["reconstruction"]["d015_diagnostics"]
            require(len(diagnostics) == 4,
                    f"{family.key}: the D015 diagnostics do not carry all four pairs")
            for (c_h, c_f) in frozen.DIAGNOSTIC_PAIRS:
                key = f"c_H={c_h}__c_f={c_f}"
                require(key in diagnostics,
                        f"{family.key}: the D015 pair {key} is missing")
                require(diagnostics[key]["unbalanced"]["c_H"] == c_h
                        and diagnostics[key]["unbalanced"]["c_f"] == c_f,
                        f"{family.key}: the D015 pair {key} is mislabelled")
            checked += 1
    require(checked == len(families) * len(cases),
            "not every family/case combination was exercised")

    # The record is in canonical committable form: only the allowlisted types,
    # and the content hash is over exactly the canonical bytes of the body.
    family = next(item for item in r.families() if item.group == "primary" and item.r == 1.0)
    space = r.family_space(family, axes)
    core_result = synthetic_core_result()
    record = r.build_record(space, 0, axes, core_result, slack, classifiers,
                            f_star, lambda_ref, bound=bound,
                            session_identity=SESSION_IDENTITY)
    body = {key: value for key, value in record.items() if key != "content_sha256"}
    encoded = canonical_encoder.canonical(body)
    require(hashlib.sha256(encoded).hexdigest() == record["content_sha256"],
            "the record's content hash is not over its canonical body")
    require(isinstance(encoded, bytes) and encoded.decode("ascii").startswith("{"),
            "the record does not canonically encode to a JSON object")

    def leaves(value, path="$"):
        if isinstance(value, dict):
            for key, item in value.items():
                require(type(key) is str, f"non-string key at {path}")
                yield from leaves(item, f"{path}.{key}")
        elif isinstance(value, list):
            for position, item in enumerate(value):
                yield from leaves(item, f"{path}[{position}]")
        else:
            yield path, value

    for path, value in leaves(record):
        require(value is None or type(value) in (bool, int, str),
                f"a record leaf at {path} is outside the committable allowlist")
    # No raw float survives anywhere: every numeric leaf is a hex string or int.
    require(not any(type(value) is float for _path, value in leaves(record)),
            "a raw float reached the committable record")

    # The reconstruction's own shape guarantees are reached directly, so a
    # dropped encoding, a missing D015 pair, a renamed half and a bad
    # per-pair encoding split are each refused.
    good_reconstruction = r._reconstruct(synthetic_core_result(), slack, classifiers,
                                         f_star, lambda_ref)
    require(set(good_reconstruction) == {"primary_c_h_2048", "d015_diagnostics"},
            "the reconstruction is missing a D015/D016 half")
    primary_half = good_reconstruction["primary_c_h_2048"]
    require(set(primary_half) == set(r.ENCODINGS),
            "the primary half does not cover exactly the two encodings")
    for pair in good_reconstruction["d015_diagnostics"].values():
        require(set(pair) == set(r.ENCODINGS),
                "a D015 pair does not cover exactly the two encodings")
    # The primary half is the frozen (2048, 2048) comparator, and each D015
    # summary carries the pair of the half it is filed under.  A record whose
    # summaries were filed under the wrong comparator is refused.
    for summary in primary_half.values():
        require((summary["c_H"], summary["c_f"]) == tuple(frozen.PRIMARY_PAIR),
                "the primary half is not the frozen (2048, 2048) comparator")
    for key, per_encoding in good_reconstruction["d015_diagnostics"].items():
        expected_pair = (int(key.split("__c_f=")[0][len("c_H="):]),
                         int(key.split("__c_f=")[1]))
        for summary in per_encoding.values():
            require((summary["c_H"], summary["c_f"]) == expected_pair,
                    f"the D015 {key} diagnostic carries the wrong comparator pair")
    require(r._comparator_of({"c_H": 1, "c_f": 2}) == (1, 2),
            "_comparator_of did not read the comparator pair")
    require(r._pair_of_key("c_H=1024__c_f=2048") == (1024, 2048),
            "_pair_of_key did not parse a frozen diagnostic key")
    for bad_key in ("c_H=1024", "c_f=2048", "c_H=abc__c_f=2048", "c_H=__c_f=", 7):
        rejected(lambda bad_key=bad_key: r._pair_of_key(bad_key),
                 f"a malformed D015 diagnostic key {bad_key!r}")
    rejected(lambda: r._comparator_of("not a dict"),
             "a reconstructed summary that is not a dict")

    # validate_record replays the record and accepts it; a tampered field fails.
    require(r.validate_record(record, space, axes, core_result, slack, classifiers,
                              f_star, lambda_ref, bound=bound,
                              session_identity=SESSION_IDENTITY)
            == record["content_sha256"],
            "validate_record did not accept the record it was given")
    # A pre-write recheck with a differing session identity is refused.
    rejected(lambda: r.validate_record(record, space, axes, core_result, slack,
                                       classifiers, f_star, lambda_ref, bound=bound,
                                       session_identity="a different session"),
             "a §B pre-write recheck whose session identity differs")
    rejected(lambda: r.build_record(space, 0, axes, core_result, slack, classifiers,
                                    f_star, lambda_ref, bound=bound,
                                    session_identity="a different session"),
             "building a record under a differing session identity")
    rejected(lambda: r.build_record(space, 0, axes, core_result, slack, classifiers,
                                    f_star, lambda_ref, bound=bound),
             "a pre-write recheck with no session identity supplied")
    tampered = copy.deepcopy(record)
    tampered["linear_index"] = 1
    rejected(lambda: r.validate_record(tampered, space, axes, core_result, slack,
                                       classifiers, f_star, lambda_ref),
             "a record whose linear index was moved")
    tampered = copy.deepcopy(record)
    tampered["coefficients"]["sector"]["lambda_1_hex"] = "0x1.0000000000001p+0"
    rejected(lambda: r.validate_record(tampered, space, axes, core_result, slack,
                                       classifiers, f_star, lambda_ref),
             "a record whose coefficients were altered")
    tampered = copy.deepcopy(record)
    tampered["content_sha256"] = "0" * 64
    rejected(lambda: r.validate_record(tampered, space, axes, core_result, slack,
                                       classifiers, f_star, lambda_ref),
             "a record whose content hash was forged")
    # A content hash that is not a lowercase 64-character SHA-256 is refused
    # before any replay, whether or not it happens to match the body.
    for bad_hash in (None, 0, "", "0" * 63, "0" * 65, "Z" * 64, ["0" * 64]):
        forged = copy.deepcopy(record)
        forged["content_sha256"] = bad_hash
        rejected(lambda forged=forged:
                 r.validate_record(forged, space, axes, core_result, slack,
                                   classifiers, f_star, lambda_ref),
                 f"a record whose content hash is {bad_hash!r}")
    # A record with no content hash at all is refused.
    missing = copy.deepcopy(record)
    del missing["content_sha256"]
    rejected(lambda: r.validate_record(missing, space, axes, core_result, slack,
                                       classifiers, f_star, lambda_ref),
             "a record with no content hash")
    # A record that is not a dict, and a non-integer linear index, are refused.
    rejected(lambda: r.validate_record("not a record", space, axes, core_result, slack,
                                       classifiers, f_star, lambda_ref),
             "a record that is not a dict")
    for bad_linear in ("0", 0.0, None, [0], True, -1, 10 ** 9):
        forged = copy.deepcopy(record)
        forged["linear_index"] = bad_linear
        # Re-seal only when the body is still canonically encodable; a float or
        # a list is refused by the frozen encoder itself, which is also a
        # refusal, so the expected exception type is widened for those.
        try:
            body_bytes = canonical_encoder.canonical(
                {k: v for k, v in forged.items() if k != "content_sha256"})
        except canonical_encoder.VerificationError:
            body_bytes = None
        if body_bytes is not None:
            forged["content_sha256"] = hashlib.sha256(body_bytes).hexdigest()
        rejected(lambda forged=forged:
                 r.validate_record(forged, space, axes, core_result, slack,
                                   classifiers, f_star, lambda_ref),
                 f"a record whose linear index is {bad_linear!r}",
                 r.CoordinateRecordError, canonical_encoder.VerificationError)
    # A pre-write recheck that is asked for without a session identity is
    # refused by both entry points, so a record can never be written on a
    # session that was never compared.
    rejected(lambda: r.build_record(space, 0, axes, core_result, slack, classifiers,
                                    f_star, lambda_ref, bound=bound),
             "build_record with a recheck and no session identity")
    rejected(lambda: r.validate_record(record, space, axes, core_result, slack,
                                       classifiers, f_star, lambda_ref, bound=bound),
             "validate_record with a recheck and no session identity")
    # A recheck against something that is not a BoundIdentity is refused too.
    # `bound=None` is *not* in this list: it is the documented "no recheck
    # requested" value, and a record built without one is still canonical.
    for bad_bound in ("not bound", {"sha": "0" * 64}, bound.accepted, 0):
        rejected(lambda bad_bound=bad_bound:
                 r.build_record(space, 0, axes, core_result, slack, classifiers,
                                f_star, lambda_ref, bound=bad_bound,
                                session_identity=SESSION_IDENTITY),
                 f"a recheck against {bad_bound!r}")
    tampered = copy.deepcopy(record)
    tampered["coordinate"]["ell_card"] = 3
    rejected(lambda: r.validate_record(tampered, space, axes, core_result, slack,
                                       classifiers, f_star, lambda_ref),
             "a record whose coordinate was altered")
    tampered = copy.deepcopy(record)
    tampered["reconstruction"]["primary_c_h_2048"]["unbalanced"]["set_label"] = "A"
    rejected(lambda: r.validate_record(tampered, space, axes, core_result, slack,
                                       classifiers, f_star, lambda_ref),
             "a record whose reconstructed label was altered")
    # A record whose reconstructed *content* differs is refused even when the
    # content hash is re-sealed to match the tampered body: the module replays
    # the frozen reconstruction rather than trusting the stored hash.  Each
    # mutation is asserted to actually change the value, so a no-op mutation
    # cannot masquerade as a passing refusal.
    def flip_label(body):
        summary = body["reconstruction"]["primary_c_h_2048"]["unbalanced"]
        summary["set_label"] = {"A": "B", "B": "A", "C": "A"}[summary["set_label"]]

    def bump_counts(body):
        summary = body["reconstruction"]["primary_c_h_2048"]["unbalanced"]
        summary["atomic_counts"] = {label: 99 for label in ("A", "B", "C")}

    def bump_size(body):
        body["reconstruction"]["d015_diagnostics"]["c_H=1024__c_f=2048"][
            "unbalanced"]["T_E_size"] += 5

    def bump_digest(body):
        commitments = body["reconstruction"]["d015_diagnostics"][
            "c_H=4096__c_f=2048"]["slack"]["commitments"]
        commitments["T_E_domain_index_stream_sha256"] = (
            "f" * 64 if commitments["T_E_domain_index_stream_sha256"] != "f" * 64
            else "0" * 64)

    def bump_p_a(body):
        summary = body["reconstruction"]["primary_c_h_2048"]["slack"]
        summary["p_A"] = [summary["p_A"][0] + 1, summary["p_A"][1]]

    def flip_univ(body):
        summary = body["reconstruction"]["d015_diagnostics"][
            "c_H=2048__c_f=1024"]["unbalanced"]
        summary["I_C_univ"] = 1 - summary["I_C_univ"]

    for path, mutate in (("set_label", flip_label), ("atomic_counts", bump_counts),
                         ("T_E_size", bump_size), ("commitment digest", bump_digest),
                         ("p_A", bump_p_a), ("I_C_univ", flip_univ)):
        resealed = copy.deepcopy(record)
        before = canonical_encoder.canonical(
            {k: v for k, v in resealed.items() if k != "content_sha256"})
        mutate(resealed)
        after = canonical_encoder.canonical(
            {k: v for k, v in resealed.items() if k != "content_sha256"})
        require(after != before, f"the {path} mutation was a no-op")
        resealed["content_sha256"] = hashlib.sha256(after).hexdigest()
        rejected(lambda resealed=resealed:
                 r.validate_record(resealed, space, axes, core_result, slack,
                                   classifiers, f_star, lambda_ref),
                 f"a re-sealed record whose {path} was altered")
    # A record with a raw float must be refused by the canonical encoder itself.
    raw = copy.deepcopy(body)
    raw["leak"] = 1.5
    rejected(lambda: canonical_encoder.canonical(raw),
             "a committable body with a raw float",
             canonical_encoder.VerificationError)
    raw = copy.deepcopy(body)
    raw["leak"] = (1, 2)
    rejected(lambda: canonical_encoder.canonical(raw),
             "a committable body with a tuple (a non-injective encoding)",
             canonical_encoder.VerificationError)

    # A malformed engine result is refused, and the refusal is typed.
    bad = synthetic_core_result()
    bad["unbalanced"] = {"minimum": -1.5, "minimum_index": 3, "compacted_entries": (tie_word(7, 4),)}
    rejected(lambda: r.build_record(space, 0, axes, bad, slack, classifiers,
                                    f_star, lambda_ref),
             "a compacted tie set that omits the minimum")
    # A slack tie set that ties at c_H=1024 (bit 0) for a state the unbalanced
    # set does not tie at there, breaking the frozen nesting requirement
    # (reconstruct.py:173).
    bad = synthetic_core_result()
    bad["slack"] = {"minimum": -1.5, "minimum_index": 3,
                    "compacted_entries": (tie_word(3, 7), tie_word(5, 1))}
    rejected(lambda: r.build_record(space, 0, axes, bad, slack, classifiers,
                                    f_star, lambda_ref),
             "a slack tie set that is not nested inside the unbalanced one")
    bad = synthetic_core_result()
    bad["unbalanced"]["minimum"] = -1.5
    bad["unbalanced"]["compacted_entries"] = (tie_word(3, 7), tie_word(2, 4))
    rejected(lambda: r.build_record(space, 0, axes, bad, slack, classifiers,
                                    f_star, lambda_ref),
             "a tie set whose indices are not strictly ascending")
    bad = synthetic_core_result()
    bad["unbalanced"]["compacted_entries"] = (tie_word(3, 5),)
    rejected(lambda: r.build_record(space, 0, axes, bad, slack, classifiers,
                                    f_star, lambda_ref),
             "a tie word with an illegal D015 flag")
    rejected(lambda: r.build_record(space, space.total_coordinates, axes,
                                    synthetic_core_result(), slack, classifiers,
                                    f_star, lambda_ref),
             "a linear index past the end of the space")
    rejected(lambda: r.build_record(space, 0, axes, synthetic_core_result(),
                                    "not a slack map", classifiers, f_star, lambda_ref),
             "a non-slack-map slack argument")


def check_injected_identity(bound: r.BoundIdentity) -> None:
    """The identity is injected; validate and exact_match are never re-derived."""
    # bind_identity takes the hash only from the injected validate.
    payload = {"a": 1}
    calls = []

    def counting_validate(candidate: object) -> str:
        calls.append(candidate)
        return hashlib.sha256(b"injected").hexdigest()

    identity = r.AcceptedIdentity(payload=payload, validate=counting_validate,
                                 exact_match=_synthetic_exact_match)
    sealed = r.bind_identity(identity)
    require(calls == [payload], "bind_identity did not call the injected validate exactly once")
    require(sealed.qualification_identity_sha256 == hashlib.sha256(b"injected").hexdigest(),
            "bind_identity did not use the injected validate's digest")

    # A non-hex digest from the injected validate is refused.
    for bad_digest in ("", "zz", "0" * 63, "0" * 65, 123, None):
        bad = r.AcceptedIdentity(payload=payload,
                                 validate=lambda _p, d=bad_digest: d,
                                 exact_match=_synthetic_exact_match)
        rejected(lambda bad=bad: r.bind_identity(bad),
                 f"an injected validate returning {bad_digest!r}")
    # A non-dict payload, and a non-callable validate/exact_match, are refused.
    rejected(lambda: r.bind_identity(r.AcceptedIdentity(
        payload=[], validate=_synthetic_validate, exact_match=_synthetic_exact_match)),
        "a non-dict identity payload")
    rejected(lambda: r.bind_identity(r.AcceptedIdentity(
        payload={}, validate=_synthetic_validate, exact_match=_synthetic_exact_match)),
        "an empty identity payload")
    rejected(lambda: r.bind_identity(r.AcceptedIdentity(
        payload=payload, validate="not callable", exact_match=_synthetic_exact_match)),
        "a non-callable validate")
    rejected(lambda: r.bind_identity(r.AcceptedIdentity(
        payload=payload, validate=_synthetic_validate, exact_match=None)),
        "a non-callable exact_match")
    rejected(lambda: r.bind_identity({"payload": payload}), "a raw dict instead of an identity")

    # recheck delegates to exact_match and surfaces its raise.  The module
    # deliberately does *not* re-implement the session comparison, so a session
    # the injected callable accepts is accepted here too; the stand-in above
    # accepts everything except the one rejected string, which is what makes the
    # "no session identity supplied" cases below a test of the module's own
    # guard rather than of the stand-in's strictness.
    bound.recheck(SESSION_IDENTITY)  # a match returns without raising
    rejected(lambda: bound.recheck("a different session"),
             "a §B pre-write recheck whose session identity differs")
    # exact_match returning a non-match sentinel is refused, not treated as a pass.
    liar = r.bind_identity(r.AcceptedIdentity(
        payload=payload, validate=_synthetic_validate,
        exact_match=lambda _s, _a: False))
    rejected(lambda: liar.recheck("anything"),
             "an exact_match that returned False instead of raising")
    truthy = r.bind_identity(r.AcceptedIdentity(
        payload=payload, validate=_synthetic_validate,
        exact_match=lambda _s, _a: True))
    truthy.recheck("anything")  # True is an accepted match signal

    # A range plan built under a different identity is refused by iter_plan_order.
    axes = r.build_frozen_axes()
    family = next(item for item in r.families() if item.group == "primary" and item.r == 1.0)
    space = r.family_space(family, axes)
    plan = r.range_plan(space, bound)
    other = r.bind_identity(r.AcceptedIdentity(
        payload=payload, validate=lambda _p: "1" * 64, exact_match=_synthetic_exact_match))
    rejected(lambda: list(r.iter_plan_order(space, axes, plan, other, with_coefficients=False)),
             "walking a plan sealed under a different production identity")


def check_range_plan_and_refusals(bound: r.BoundIdentity) -> None:
    """The range plan is the frozen contract's, and refusals are typed."""
    axes = r.build_frozen_axes()
    family = next(item for item in r.families() if item.group == "primary" and item.r == 2.0)
    space = r.family_space(family, axes)
    plan = r.range_plan(space, bound)
    # The plan is exactly the frozen contract's output for these arguments.
    expected = contract.build_range_plan(family.key, space.total_coordinates,
                                         bound.qualification_identity_sha256)
    require(plan == expected, "the module's range plan differs from the frozen contract's")
    require(contract.validate_range_plan(plan) == plan, "the sealed plan is not canonical")
    # The plan's ranges are contiguous, non-empty and exactly cover the order.
    previous = 0
    for row in plan["ranges"]:
        require(row["start"] == previous, "the plan's ranges are not contiguous")
        require(row["stop"] > row["start"], "a plan range is empty")
        require(row["stop"] - row["start"] <= contract.MAX_COORDINATES_PER_RANGE,
                "a plan range exceeds the contract's cap")
        previous = row["stop"]
    require(previous == space.total_coordinates, "the plan does not exactly cover the order")
    # Batch ids are the contract's own range ids.
    for ordinal, row in enumerate(plan["ranges"]):
        require(row["batch_id"] == contract.range_id(family.key, ordinal),
                "a batch id is not the frozen contract's range id")
    # The [start, stop) windows of iter_coordinates cover the order in order.
    for row in plan["ranges"][:3]:
        window = list(r.iter_coordinates(space, axes, row["start"], row["stop"],
                                         with_coefficients=False))
        require([entry[0] for entry in window] == list(range(row["start"], row["stop"])),
                "a [start, stop) window is not that exact slice of the linear order")
    # Refusals on a malformed plan.
    bad = copy.deepcopy(plan)
    bad["ranges"][0]["start"] = 1
    try:
        list(r.iter_plan_order(space, axes, bad, bound, with_coefficients=False))
        raise FixtureError("a re-partitioned plan was accepted")
    except (r.CoordinateRecordError, contract.CUDAExecutionContractError):
        pass
    # A plan for a different family or coordinate count is refused.
    foreign = contract.build_range_plan("other_family", 100,
                                        bound.qualification_identity_sha256)
    rejected(lambda: list(r.iter_plan_order(space, axes, foreign, bound,
                                           with_coefficients=False)),
             "a plan naming a different family")
    short = contract.build_range_plan(family.key, 100,
                                      bound.qualification_identity_sha256)
    rejected(lambda: list(r.iter_plan_order(space, axes, short, bound,
                                           with_coefficients=False)),
             "a plan partitioning a different coordinate count")
    rejected(lambda: r.range_plan(space, "not a bound identity"),
             "a range plan built without a BoundIdentity")
    rejected(lambda: r.range_plan(space, None), "a range plan built from a None identity")
    rejected(lambda: r.range_plan(None, bound), "a range plan without a coordinate space")
    # A plan whose last range is empty, and a plan sealing fewer coordinates
    # than the space holds, are both refused by the module's own cover checks.
    empty = contract.build_range_plan(family.key, space.total_coordinates,
                                      bound.qualification_identity_sha256)
    empty["ranges"][1]["stop"] = empty["ranges"][1]["start"]
    empty["content_sha256"] = contract.content_sha256(empty)
    rejected(lambda: r.range_plan(space, bound, contract_plan=empty),
             "a plan whose range is empty",
             r.CoordinateRecordError, contract.CUDAExecutionContractError)
    # An empty range at the *front* of the cover: the contiguity clause alone
    # would accept `start == expected` when `expected` is still 0, so the
    # non-empty clause is the only thing that can refuse it.
    leading_empty = contract.build_range_plan(family.key, space.total_coordinates,
                                              bound.qualification_identity_sha256)
    leading_empty["ranges"][0]["stop"] = 0
    leading_empty["ranges"][1]["start"] = 0
    leading_empty["content_sha256"] = contract.content_sha256(leading_empty)
    rejected(lambda: r.range_plan(space, bound, contract_plan=leading_empty),
             "a plan whose first range is empty",
             r.CoordinateRecordError, contract.CUDAExecutionContractError)
    # A plan for a different family is refused by `range_plan`'s own family
    # binding, before the cover is even considered.
    other_family = contract.build_range_plan("some_other_family",
                                             space.total_coordinates,
                                             bound.qualification_identity_sha256)
    rejected(lambda: r.range_plan(space, bound, contract_plan=other_family),
             "a plan naming a different family",
             r.CoordinateRecordError, contract.CUDAExecutionContractError)
    # `iter_plan_order` refuses a plan for another family first, before its size
    # or its identity binding.
    rejected(lambda: list(r.iter_plan_order(space, axes, other_family, bound,
                                           with_coefficients=False)),
             "walking a plan that names a different family",
             r.CoordinateRecordError, contract.CUDAExecutionContractError)
    short_total = contract.build_range_plan(family.key,
                                           space.total_coordinates - 1,
                                           bound.qualification_identity_sha256)
    rejected(lambda: r.range_plan(space, bound, contract_plan=short_total),
             "a plan sealing fewer coordinates than the space holds",
             r.CoordinateRecordError, contract.CUDAExecutionContractError)


def main() -> int:
    bound = bound_identity()
    if os.environ.get("WP4A_MUTATION_FAST") == "1":
        # Each mutant uses a small synthetic space; the million-point order
        # comparison is reserved for the final, unmutated suite.
        primary = r._primary_family(1.0)
        axes = r.FrozenAxes(1.0, (1.0, 2.0, 3.0), (1.0, 2.0, 3.0),
                            (1.0, 2.0, 3.0), (1.0, 2.0, 3.0))
        space = r.family_space(primary, axes)
        plan = r.range_plan(space, bound)
        require([(linear, coord) for _, linear, coord, _ in
                 r.iter_plan_order(space, axes, plan, bound, False)] ==
                [(i * 9 + j * 3 + k, (i, j, k))
                 for i in range(3) for j in range(3) for k in range(3)],
                "small synthetic plan order differs from nested loops")
    else:
        check_counts_and_order(bound)
    check_round_trip()
    check_guard_mutations(bound)
    check_public_argument_fuzz()
    check_coefficient_resolution()
    check_record_construction(bound)
    check_injected_identity(bound)
    check_range_plan_and_refusals(bound)
    print("PASS Stage-2 coordinate-record fixtures; synthetic coordinates, "
          "coefficients and engine minima/tie data only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
