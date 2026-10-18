#!/usr/bin/env python3
"""Stage-2 inference over the five real production slots, frozen quantities only.

Run after `verify_outputs_v2.py` has returned `VERDICT: PASS`:

    python3 -B analyze_stage2_v3.py --results-root <root> --out <dir>

It reads the verified committed records and emits `STAGE2_INFERENCE.json`
carrying its own `content_sha256` and the SHA-256 of every input it consumed.

--------------------------------------------------------------------------
EVERY QUANTITY COMPUTED HERE, WITH ITS FROZEN CITATION
--------------------------------------------------------------------------

Nothing in this file is computed that the frozen protocol does not
pre-specify.  The table is the whole of it.

Q1  Per-instance, per-`r`, per-encoding **exact A/B/C census of decoded set
    labels** and the exact rational `rho_E^exact = A_count / |X_E|`.
    Citation: `research/00_specifications/FROZEN_MATH_SPEC.md:459-471` — "Report
    raw `|T_E|` separately ..., decoded `|X_E|`, atomic-label census,
    `I_C^exist`, `I_C^univ`, per-grid `p_A,p_B,p_C` with denominator `|X_E|`,
    and arithmetic-mean aggregate fractions"; and `:473` — "`rho_E^exact` is
    the exact finite-grid primary A-rate".  The counts are read from the
    committed reconstruction summary
    (`research/g9/cuda_qualification/stage2_cuda_reconstruct.py:196-214`), not
    re-derived from energies.

Q2  The **paired encoding difference** `Delta(r) = rho_slack - rho_unbalanced`
    per `r`, as an exact rational with its sign.
    Citation: `research/decisions/DECISIONS.md:1120-1124` — "`Delta_i(r) =
    rho_slack,i,r^exact - rho_unbalanced,i,r^exact`"; and
    `GATE_9_STAGE2_PROTOCOL_DRAFT.md:161-164` — the trigger "is applied
    mechanically and separately after each instance's three-r primary core
    pass".

Q3  The **D013 trigger disposition**, per instance, by the exact-sign rule.
    Citation: `research/decisions/DECISIONS.md:1125-1131` — "The rule fires iff
    at least one of the three values is exactly zero **or** they do not all
    have one strict sign. It does not fire only for `(+,+,+)` and `(-,-,-)`.
    There is no numerical tolerance in this rule."

Q4  The **C-rate difference** `unbalanced - slack`, per `r`, as exact integers.
    Citation: `project/paper/RESULTS_AND_FIGURE_SLOTS.md:21` names
    `primary_C_rate_differences_unbalanced_minus_slack` as the accepted
    C-rate contrast, and `FROZEN_MATH_SPEC.md:459-471` fixes the denominator
    as `|X_E|`.  Note the difference is taken on the C **census over
    coordinates**, exactly as Stage-1 does
    (`research/g7/stage1_inference.py:315-316`), and it is reported beside
    Q2, never substituted for it.

Q5  **Exact integer spatial predicates of the A-region** per `r` per encoding:
    `A_point_count`, `cartesian_product`, `axis_aligned_box`,
    `axis_projection_sizes`; and of each directional A-advantage set,
    `component_count` and `largest_component_size`.
    Citations: `project/paper/RESULTS_AND_FIGURE_SLOTS.md:79-91` (SLOT-2,
    "Render the exact, already-computed predicates. Do **not** re-derive
    labels and do **not** refit a boundary"), and the Stage-1 implementations
    these are defined by —
    `research/g7/stage1_inference.py:181-197` (`_components`),
    `:200-215` (`_region_shape`), `:248-251` (the advantage sets), and
    `:218-268` (`scan_primary_lattice`).  The predicates themselves are
    mechanical and are re-implemented here on Stage-2 coordinates with the
    Stage-2 axis length; the LABELS they consume are the committed ones.

Q6  **V-14 companion** `slack - unbalanced` `rho_E^exact` per scale, with sign.
    Citation: `project/paper/RESULTS_AND_FIGURE_SLOTS.md:108-121` (SLOT-4);
    the rule at `research/decisions/DECISIONS.md:1829` — "Both expansion passes
    execute at D006 **`r = 1` only**. V-14 is a report-only robustness
    companion"; and the extents at `:1823-1828`.

Q7  **D011 matched-subgrid** `rho_E^exact` per encoding as the exact rational
    `A_count / 2197`.
    Citation: `project/paper/RESULTS_AND_FIGURE_SLOTS.md:123-135` (SLOT-5)
    — "Report `rho_E^exact` **solely** as the exact rational `A_count / 2197`
    with the exact numerator difference versus the matching accepted Gate-5
    subset. Do **not** emit a float approximation, a full-grid rate, a D015
    diagnostic, a label lattice, an edge list, or any inference."  The
    "matching accepted Gate-5 subset" is NOT computed here: Stage-1's subset is
    a Stage-1 artefact and this pipeline emits no cross-generation comparison.
    See ANALYSIS_NOTES.md.

Q8  The **cross-instance reduction**: the vector of five instance dispositions
    plus `all_five`, `any_one`, `count_of_five`.
    Citation: `research/decisions/GATE_9_STAGE2_PROTOCOL_DRAFT.md:195-198` —
    "Cross-instance adjudication is mechanical and unweighted: for each
    already-declared exact predicate, retain the vector of five instance
    statuses plus `all_five`, `any_one`, and `count_of_five`; **do not pool raw
    rates across instances or with Stage 1**."  No pooling is performed: no
    mean, no pooled rate, no cross-instance aggregate of any raw rate appears
    anywhere in the output.

--------------------------------------------------------------------------
WHAT IS DELIBERATELY NOT COMPUTED
--------------------------------------------------------------------------

N1  **No H0/H1/H2/H3 threshold, score, or verdict.**
    `GATE_9_STAGE2_PROTOCOL_DRAFT.md:200-204` — "The Stage-1 H0/H1/H2/H3
    threshold limitations remain limitations. This draft does not invent a
    rate-comparability, H1 sub-region, or H2 measurability threshold for
    either Stage 1 or Stage 2."  No dated owner approval changing this exists
    in the reviewed decision set, so every threshold word stays
    `indeterminate`.  `hypothesis_evaluation` records the *observed exact
    predicates* and the *status word*, never a support/refute verdict.

N2  **No winner, no advantage, no gap magnitude.**
    `project/paper/CLAIMS_AND_LIMITATIONS_REGISTER.md` P-06 — "Slack
    outperforms unbalanced" / "any winner claim" is PROHIBITED because the
    rate-comparison component is indeterminate.  A sign is reported; no
    comparison to any threshold is performed, because none exists.

N3  **No pooled rate, mean rate, or cross-instance or cross-generation
    aggregate.**  `GATE_9_STAGE2_PROTOCOL_DRAFT.md:195-198`; P-16.

N4  **No boundary fit, smoothing, ranking, or regression.**  P-20 and
    `research/decisions/GATE_6_OWNER_EXECUTION_DECISIONS.md:19-22`.  SLOT-2
    predicates are rendered, not inferred from.

N5  **No D013 ablation result.**  The four conditions are only *dispositions*.
    If a trigger fires, `full_production_parent_v2.py:119-146` already ran the
    complete 22-family package in-kernel and this pipeline would need a
    different, separately reviewed reader for those families; they are not
    declared in `stage2_schema_v2.FAMILY_CENSUS` and are therefore out of scope
    here.  The output says so explicitly under `d013.conditions_not_analysed`.

N6  **No re-derivation of `H_E`, `T_E`, `X_E`, `f*`, `Lambda_ref` or any
    label.**  Those are produced by the CUDA core and certified by the frozen
    reconstruction (`stage2_cuda_reconstruct.py:223-276`).  Re-deriving them
    would be a second scientific computation, which this pipeline is not
    authorised to perform.  Every number below is read from a committed,
    hash-verified reconstruction summary.

N7  **No float anywhere in the output document.**  Exact integers and exact
    rationals only, per `RESULTS_AND_FIGURE_SLOTS.md:38-41` ("Exact integers,
    never decimals").  `stage2_schema_v2.canonical_bytes` refuses a float leaf, so
    a decimal could not be written even by accident.
"""

from __future__ import annotations

import argparse
import sys
from collections import deque
from fractions import Fraction
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import real_layout_v2 as layout
import stage2_schema_v2 as schema  # noqa: E402
from stage2_schema_v2 import Stage2AnalysisError  # noqa: E402
import verify_outputs_v2  # noqa: E402

INFERENCE_SCHEMA = "decisions_os/g9_stage2_inference/v1"


def _require(ok: Any, message: str) -> None:
    if not ok:
        raise Stage2AnalysisError(message)


# ---------------------------------------------------------------------------
# Q1 / Q4 — the exact per-cell censuses
# ---------------------------------------------------------------------------

def _rational(count: int, total: int, label: str) -> dict[str, Any]:
    """The exact rational, stored as `{numerator, denominator}` INTEGERS.

    Stage-1 stores `Fraction(n, d)` reduced through
    `json.dumps` as `{"numerator": ..., "denominator": ...}`
    (`research/g7/stage1_inference.py:100-105, 312-314`).  A raw count pair
    `(count, total)` is ALSO carried as `exact_counts` so the reduction is
    visible and reversible; the reduced form is the comparable one.
    """
    _require(type(count) is int and type(total) is int and total >= 1,
             f"{label} must be an integer count over a positive integer total")
    value = Fraction(count, total)
    return {"numerator": value.numerator, "denominator": value.denominator}


def _sign(value: int) -> str:
    return "positive" if value > 0 else "negative" if value < 0 else "zero"


def _cell(encoding: str, label_counts: dict[str, int],
          coordinate_count: int, spread: dict[str, Any]) -> dict[str, Any]:
    """One `(r, encoding)` cell: Q1's census and exact `rho_E^exact`.

    `coordinate_count` is the number of GRID POINTS in the cell.  It is the
    denominator of the *aggregate over coordinates*, and it is reported
    separately from `X_E_size`, which is the denominator of the per-point
    `p_A` (`FROZEN_MATH_SPEC.md:468-470`: "per-grid `p_A,p_B,p_C` with
    denominator `|X_E|`").  Conflating the two is the error
    `RESULTS_AND_FIGURE_SLOTS.md:21` warns about, so both are named.

    `|T_E|` and `|X_E|` VARY across the grid — they are per-point quantities,
    and `FROZEN_MATH_SPEC.md:468` asks for them to be "reported ... separately
    (symbolically where allowed)".  A single point's value would be a fiction,
    so what is reported is the exact integer MINIMUM and MAXIMUM over the whole
    cell, plus the exact census counts of the two indicators.  No mean, no
    representative value, no float.
    """
    _require(sum(label_counts.values()) == coordinate_count,
             f"{encoding}: the label census sums to "
             f"{sum(label_counts.values())}, not {coordinate_count}")
    return {
        "encoding": encoding,
        "set_label_counts": dict(label_counts),
        "rho_E_exact": _rational(label_counts["A"], coordinate_count,
                                 f"{encoding} rho_E^exact"),
        "rho_E_exact_counts": [label_counts["A"], coordinate_count],
        "I_C_exist_count": spread["I_C_exist"],
        "I_C_univ_count": spread["I_C_univ"],
        "X_E_size_min": spread["X_E_min"],
        "X_E_size_max": spread["X_E_max"],
        "T_E_size_min": spread["T_E_min"],
        "T_E_size_max": spread["T_E_max"],
        "T_E_and_X_E_are_per_point": "reported as exact integer extremes over "
                                     "the cell; they are per-point quantities "
                                     "and no representative value is claimed "
                                     "(FROZEN_MATH_SPEC.md:468-470)",
    }


# ---------------------------------------------------------------------------
# Q5 — the exact integer spatial predicates (Stage-1's definitions, Stage-2 data)
# ---------------------------------------------------------------------------

def _neighbors(linear: int, axis_length: int) -> tuple[int, ...]:
    """Face-adjacent neighbours on the 3-D lattice, last axis fastest."""
    card, remainder = divmod(linear, axis_length * axis_length)
    sector, budget = divmod(remainder, axis_length)
    out: list[int] = []
    for axis, coordinate in enumerate((card, sector, budget)):
        for delta in (-1, 1):
            changed = coordinate + delta
            if not 0 <= changed < axis_length:
                continue
            fields = [card, sector, budget]
            fields[axis] = changed
            out.append((fields[0] * axis_length + fields[1]) * axis_length
                       + fields[2])
    return tuple(out)


def _components(points: set[int], axis_length: int) -> dict[str, int]:
    """Connected components under face adjacency.

    The adjacency relation is Stage-1's own
    (`research/g7/stage1_inference.py:167-178, 181-197`): only the six
    face-adjacent lattice neighbours.  No diagonal, no fitted boundary.
    """
    remaining = set(points)
    component_count = 0
    largest = 0
    while remaining:
        component_count += 1
        queue = deque([remaining.pop()])
        size = 0
        while queue:
            current = queue.popleft()
            size += 1
            for neighbour in _neighbors(current, axis_length):
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    queue.append(neighbour)
        largest = max(largest, size)
    return {"component_count": component_count,
            "largest_component_size": largest}


def _region_shape(points: set[int], axis_length: int) -> dict[str, Any]:
    """`A_point_count`, `cartesian_product`, `axis_aligned_box`, projections.

    Byte-for-byte Stage-1's `_region_shape`
    (`research/g7/stage1_inference.py:200-215`), generalised only by the axis
    length.  `axis_aligned_box` requires BOTH that the region is a full
    Cartesian product AND that each projection is contiguous.
    """
    if not points:
        return {"A_point_count": 0, "cartesian_product": "empty",
                "axis_aligned_box": "empty", "axis_projection_sizes": [0, 0, 0]}
    projections: list[set[int]] = [set(), set(), set()]
    for value in points:
        card, remainder = divmod(value, axis_length * axis_length)
        sector, budget = divmod(remainder, axis_length)
        projections[0].add(card)
        projections[1].add(sector)
        projections[2].add(budget)
    product_size = 1
    for projection in projections:
        product_size *= len(projection)
    cartesian = len(points) == product_size
    contiguous = all(max(p) - min(p) + 1 == len(p) for p in projections)
    return {
        "A_point_count": len(points),
        "cartesian_product": "yes" if cartesian else "no",
        "axis_aligned_box": "yes" if cartesian and contiguous else "no",
        "axis_projection_sizes": [len(p) for p in projections],
    }


# ---------------------------------------------------------------------------
# The per-family scan
# ---------------------------------------------------------------------------

def scan_family(family_key: str, family_root: Path, records_per_range: int,
                axis_length: int, coordinate_count: int) -> dict[str, Any]:
    """Stream one family's committed records and derive only what is frozen.

    Derived per family:
      * the per-`r`/per-encoding set-label census (Q1);
      * the A-region and advantage-region sets (Q5) — retained as exact integer
        predicates only, never as a lattice dump;
      * the set of DISTINCT decoded set labels observed, as a guard: a family
        whose records disagree with their own census is refused rather than
        averaged.

    The D015 diagnostics are read and shape-checked but NOT reduced to any
    rate: `research/decisions/DECISIONS.md:437-438` makes the four pairs
    "additionally reported and ... cannot select a primary result", and
    `RESULTS_AND_FIGURE_SLOTS.md:130` forbids emitting D015 diagnostics in the
    D011 slot.  Their presence is recorded, their counts are not turned into a
    second A-rate.
    """
    axis_length = int(axis_length)
    coordinate_count = int(coordinate_count)
    _require(axis_length >= 1 and coordinate_count >= 1,
             f"{family_key}: the census profile declares a non-positive axis "
             "length or coordinate count")
    group = schema.FAMILY_GROUP[family_key]
    label_counts: dict[tuple[str, str], dict[str, int]] = {}
    spread: dict[tuple[str, str], dict[str, int]] = {}
    a_regions: dict[tuple[str, str], set[int]] = {}
    advantage: dict[tuple[str, str], set[int]] = {}
    decoded = {}
    seen_linear: set[int] = set()

    # A PRIMARY family carries one family key per r in {0.5, 1, 2}, so its records
    # span all three r_hex values.  D011 and both V-14 companions are r = 1
    # ONLY readings (`stage2_coordinate_records.py:466, 472`;
    # `DECISIONS.md:1829`), so each of their records carries exactly one r_hex.
    # Which r_hex values a family is expected to carry is therefore read off the
    # records themselves, and the cell list is built from that — never assumed.
    observed_r_hex: list[str] = []
    for _batch, record in schema.iter_family_records(
            family_root, family_key, records_per_range,
            total=coordinate_count, axis_length=axis_length):
        linear = record["linear_index"]
        _require(linear not in seen_linear,
                 f"{family_key}: linear index {linear} appears twice; the "
                 "census would double-count (stage2_coordinate_records.py:82-89)")
        seen_linear.add(linear)
        r_hex = record["r_hex"]
        if r_hex not in observed_r_hex:
            observed_r_hex.append(r_hex)
        _require(r_hex in schema.PRIMARY_R_HEX,
                 f"{family_key}: a record carries r_hex={r_hex!r}, which is not "
                 "one of the three frozen primary r values "
                 "(src/g5/core_pass.py:43)")
        point: dict[str, str] = {}
        primary = record["reconstruction"][schema.PRIMARY_SUMMARY_KEY]
        for encoding in schema.ENCODINGS:
            summary = primary[encoding]
            label = summary["set_label"]
            key = (r_hex, encoding)
            bucket = label_counts.setdefault(key, {"A": 0, "B": 0, "C": 0})
            bucket[label] += 1
            from completeness_core_v3 import new_bucket, add_summary
            add_summary(decoded.setdefault(key, new_bucket()), summary)
            point[encoding] = label
            if label == "A":
                a_regions.setdefault(key, set()).add(linear)
            # Exact integer extremes of the per-point |T_E| and |X_E|, plus
            # the two indicators' census counts.  Nothing here is a mean.
            cell_spread = spread.get(key)
            if cell_spread is None:
                cell_spread = {
                    "T_E_min": summary["T_E_size"],
                    "T_E_max": summary["T_E_size"],
                    "X_E_min": summary["X_E_size"],
                    "X_E_max": summary["X_E_size"],
                    "I_C_exist": 0, "I_C_univ": 0,
                }
                spread[key] = cell_spread
            else:
                cell_spread["T_E_min"] = min(cell_spread["T_E_min"],
                                             summary["T_E_size"])
                cell_spread["T_E_max"] = max(cell_spread["T_E_max"],
                                             summary["T_E_size"])
                cell_spread["X_E_min"] = min(cell_spread["X_E_min"],
                                             summary["X_E_size"])
                cell_spread["X_E_max"] = max(cell_spread["X_E_max"],
                                             summary["X_E_size"])
            cell_spread["I_C_exist"] += summary["I_C_exist"]
            cell_spread["I_C_univ"] += summary["I_C_univ"]
        if point["slack"] == "A" and point["unbalanced"] != "A":
            advantage.setdefault((r_hex, "slack_A_advantage"), set()).add(linear)
        elif point["unbalanced"] == "A" and point["slack"] != "A":
            advantage.setdefault((r_hex, "unbalanced_A_advantage"), set()).add(linear)

    _require(len(seen_linear) == coordinate_count,
             f"{family_key}: streamed {len(seen_linear)} coordinates; the "
             f"frozen census is {coordinate_count} "
             "(--stream-only a census: RESULTS_AND_FIGURE_SLOTS.md:44-48)")

    primary_cells: list[dict[str, Any]] = []
    spatial: dict[str, Any] = {}
    rate_differences: list[dict[str, Any]] = []
    c_rate_differences: list[dict[str, Any]] = []
    # Each family key carries EXACTLY ONE r: `Family.key` embeds the r token
    # (`stage2_coordinate_records.py:370-377`), so `primary__r0x1.0p-1` is the
    # r = 0.5 sweep and nothing else.  The three primary family keys together
    # are the three-r comparison.  The cell list is therefore exactly the single
    # r this family declares, read off `FAMILY_R_HEX` — never assumed, and never
    # fanned out over all three.
    rates = [schema.FAMILY_R_HEX[family_key]]
    _require(rates[0] in observed_r_hex,
             f"{family_key}: the family declares r={rates[0]} but no record "
             f"carries it; the records carry {observed_r_hex}")
    _require(len(observed_r_hex) == 1,
             f"{family_key}: one family key carries exactly one r, but its "
             f"records span {observed_r_hex} "
             "(stage2_coordinate_records.py:370-377)")
    diagnostic_cells = 0

    for r_hex in rates:
        pair: dict[str, Any] = {}
        for encoding in schema.ENCODINGS:
            key = (r_hex, encoding)
            bucket = label_counts.get(key)
            if bucket is None:
                raise Stage2AnalysisError(
                    f"{family_key}: no committed record carried a "
                    f"r_hex={r_hex!r} {encoding!r} cell")
            cell = _cell(encoding, bucket, coordinate_count, spread[key])
            from completeness_core_v3 import render_series
            series = render_series(decoded[key], family_key, r_hex, encoding)
            cell["mean_p"] = series["mean_p"]
            cell["series"] = series
            pair[encoding] = cell
            diagnostic_cells += 1
        primary_cells.append({"r_hex": r_hex,
                              "r_display": schema.PRIMARY_R_DISPLAY[r_hex],
                              "coordinate_count": coordinate_count,
                              "encodings": pair})
        if group == "primary":
            # Q2 — DECISIONS.md:1120-1124.
            delta = (Fraction(pair["slack"]["rho_E_exact_counts"][0],
                              coordinate_count)
                     - Fraction(pair["unbalanced"]["rho_E_exact_counts"][0],
                                coordinate_count))
            rate_differences.append({
                "r_hex": r_hex, "r_display": schema.PRIMARY_R_DISPLAY[r_hex],
                "numerator": delta.numerator, "denominator": delta.denominator,
                "sign": _sign(delta.numerator),
                "exact_counts": [pair["slack"]["rho_E_exact_counts"][0]
                                 - pair["unbalanced"]["rho_E_exact_counts"][0],
                                 coordinate_count],
            })
            # Q4 — RESULTS_AND_FIGURE_SLOTS.md:21, Stage-1 :315-316.
            c_delta = (pair["unbalanced"]["set_label_counts"]["C"]
                       - pair["slack"]["set_label_counts"]["C"])
            c_rate_differences.append({
                "r_hex": r_hex, "r_display": schema.PRIMARY_R_DISPLAY[r_hex],
                "numerator": c_delta, "denominator": coordinate_count,
                "sign": _sign(c_delta),
                "exact_counts": [c_delta, coordinate_count],
            })
        # Q5 — RESULTS_AND_FIGURE_SLOTS.md:79-91.
        wins = {direction: advantage.get((r_hex, direction), set())
                for direction in ("slack_A_advantage", "unbalanced_A_advantage")}
        spatial[r_hex] = {
            "slack_A_advantage": {"point_count": len(wins["slack_A_advantage"]),
                                  **_components(wins["slack_A_advantage"], axis_length)},
            "unbalanced_A_advantage": {"point_count": len(wins["unbalanced_A_advantage"]),
                                       **_components(wins["unbalanced_A_advantage"],
                                                     axis_length)},
            "both_directional_A_advantages":
                "yes" if all(wins[d] for d in wins) else "no",
            "A_region_shape": {encoding: _region_shape(a_regions.get((r_hex, encoding),
                                                                     set()),
                                                         axis_length)
                               for encoding in schema.ENCODINGS},
        }

    v14 = None
    if group == "v14":
        slack_a = primary_cells[0]["encodings"]["slack"]["rho_E_exact_counts"]
        unbalanced_a = primary_cells[0]["encodings"]["unbalanced"]["rho_E_exact_counts"]
        delta = Fraction(slack_a[0], slack_a[1]) - Fraction(unbalanced_a[0],
                                                             unbalanced_a[1])
        scale = "0.5x" if "0_5x" in family_key else "2x"
        v14 = {
            "scale": scale,
            "coordinate_count": coordinate_count,
            "axis_length": axis_length,
            "q_range": [-2, 1] if scale == "0.5x" else [-8, 3],
            "decades": 3 if scale == "0.5x" else 11,
            "slack_minus_unbalanced_rho": {
                "numerator": delta.numerator, "denominator": delta.denominator},
            "exact_counts": [slack_a[0] - unbalanced_a[0], coordinate_count],
            "sign": _sign(delta.numerator),
            "r_hex": schema.PRIMARY_R_HEX[1],
            "status": "report_only_companion",
        }

    d011 = None
    if group == "d011":
        pair = primary_cells[0]["encodings"]
        d011 = {
            "coordinate_count": coordinate_count,
            "matched_subgrid_indices": "ell in {0,5,...,60} over the 61-axis "
                                       "primary cube, 13**3 points "
                                       "(src/g6/d011_matched_subgrid.py:52-54)",
            "rho_E_exact": {
                encoding: _rational(pair[encoding]["rho_E_exact_counts"][0],
                                    coordinate_count,
                                    f"d011 {encoding}")
                for encoding in schema.ENCODINGS},
            "exact_counts": {
                encoding: list(pair[encoding]["rho_E_exact_counts"])
                for encoding in schema.ENCODINGS},
            "status": "non_primary_matched_subgrid_companion",
        }

    return {
        "family": family_key,
        "group": group,
        "axis_length": axis_length,
        "coordinate_count": coordinate_count,
        "census_citation": schema.FAMILY_CENSUS[family_key][2],
        "rows_streamed": len(seen_linear),
        "reported_cells": primary_cells,
        "series": [cell["series"] for row in primary_cells for cell in row["encodings"].values()],
        "primary_rate_differences": rate_differences,
        "primary_C_rate_differences_unbalanced_minus_slack": c_rate_differences,
        "spatial_A_predicates": spatial,
        "v14_primary_condition_comparison": v14,
        "d011_matched_subgrid": d011,
        "d015_diagnostic_cells_present": diagnostic_cells,
        "d015_diagnostics_reduced_to_rates": False,
    }


# ---------------------------------------------------------------------------
# Q3 / Q8 — the trigger disposition and the mechanical cross-instance reduction
# ---------------------------------------------------------------------------

def trigger_disposition(rate_differences: list[dict[str, Any]]) -> dict[str, Any]:
    """Q3. The exact-sign D013 rule, applied mechanically.

    `research/decisions/DECISIONS.md:1125-1131`.  Fires iff at least one of the
    three `Delta` values is exactly zero, OR they do not all share one strict
    sign.  No tolerance of any kind is applied — the rule says so explicitly
    and `RESULTS_AND_FIGURE_SLOTS.md:144` restates it as "**No numerical
    tolerance**".
    """
    _require(len(rate_differences) == len(schema.TRIGGER_R_HEX),
             f"the trigger consumes exactly {len(schema.TRIGGER_R_HEX)} Delta "
             f"cells, not {len(rate_differences)} "
             "(DECISIONS.md:1120-1124)")
    signs = [row["sign"] for row in rate_differences]
    any_zero = "zero" in signs
    one_strict_sign = all(sign == signs[0] for sign in signs)
    fires = any_zero or not one_strict_sign
    return {
        "rule": "fires iff any Delta(r) is exactly zero, or the three do not "
                "all share one strict sign (DECISIONS.md:1125-1131); no "
                "numerical tolerance",
        "deltas": rate_differences,
        "signs": signs,
        "any_delta_exactly_zero": any_zero,
        "all_share_one_strict_sign": one_strict_sign,
        "fired": fires,
        "ablation_status": "run_in_kernel_see_d013_conditions_not_analysed"
                           if fires else "not_applicable",
        "disposition": "fires" if fires else "does_not_fire",
    }


def cross_instance_reduction(per_instance: list[dict[str, Any]],
                             predicate: str) -> dict[str, Any]:
    """Q8. `all_five` / `any_one` / `count_of_five`, mechanically and unweighted.

    `GATE_9_STAGE2_PROTOCOL_DRAFT.md:195-198`.  It reduces a vector of five
    BOOLEAN statuses and nothing else.  No rate, count or magnitude is
    aggregated here; doing so is P-16 and is not done.
    """
    statuses = [bool(row["observed_exact_predicates"][predicate])
              for row in per_instance]
    return {
        "predicate": predicate,
        "instance_statuses": statuses,
        "all_five": all(statuses),
        "any_one": any(statuses),
        "count_of_five": sum(1 for value in statuses if value),
        "aggregation": "mechanical_and_unweighted; no rate is pooled "
                       "(GATE_9_STAGE2_PROTOCOL_DRAFT.md:195-198, P-16)",
    }


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def build_inference(results_root: Path, census: dict[str, Any]) -> dict[str, Any]:
    """Stream all five slots and emit the single inference document."""
    missing = layout.inventory(results_root, census)
    _require(not missing, '\n'.join(missing))
    per_slot: list[dict[str, Any]] = []
    input_hashes: dict[str, Any] = {}
    records_per_range = census["records_per_range"]

    for number in range(1, len(schema.SLOT_NAMES) + 1):
        slot_dir = schema.find_slot_dir(results_root, number)
        slot_name = schema.SLOT_NAMES[number - 1]
        families: dict[str, Any] = {}
        for family_key in schema.BASELINE_FAMILIES:
            entry = census["family_census"][family_key]
            families[family_key] = scan_family(
                family_key, layout.family_root(slot_dir, family_key), records_per_range,
                entry["axis_length"], entry["coordinates"])
            plan_path = layout.family_root(slot_dir, family_key) / schema.PLAN_NAME
            input_hashes[f"{slot_name}/{family_key}/range_plan.json"] = \
                schema.sha256_hex(plan_path.read_bytes())

        primary = sorted(
            (row for row in families.values() if row["group"] == "primary"),
            key=lambda row: schema.PRIMARY_R_HEX.index(
                row["reported_cells"][0]["r_hex"]))
        _require(len(primary) == len(schema.PRIMARY_R_HEX),
                 f"slot {slot_name}: {len(primary)} primary families were read; "
                 f"exactly {len(schema.PRIMARY_R_HEX)} (one per r) are required "
                 "(src/g5/core_pass.py:43)")
        # Q2/Q3/Q4 are defined over the THREE-r comparison, so the per-family
        # single-r differences are concatenated in the frozen r order.  Each
        # family's own difference is computed over its OWN r; pooling across r
        # is never done, only ordered.
        rate_differences = [row for entry in primary
                            for row in entry["primary_rate_differences"]]
        c_rate_differences = [
            row for entry in primary
            for row in entry["primary_C_rate_differences_unbalanced_minus_slack"]]
        spatial = {}
        for r_hex in schema.PRIMARY_R_HEX:
            entry = next(row for row in primary
                         if row["reported_cells"][0]["r_hex"] == r_hex)
            spatial[r_hex] = entry["spatial_A_predicates"][
                entry["reported_cells"][0]["r_hex"]]
        disposition = trigger_disposition(rate_differences)

        v14 = {row["v14_primary_condition_comparison"]["scale"]:
               row["v14_primary_condition_comparison"]
               for row in families.values()
               if row["v14_primary_condition_comparison"] is not None}
        d011 = next(row["d011_matched_subgrid"] for row in families.values()
                    if row["d011_matched_subgrid"] is not None)

        per_slot.append({
            "slot": number,
            "instance_id": slot_name,
            "prepared_record_content_sha256": schema.read_prepared_metadata(
                slot_dir / "instance/PREPARED.json", f"{slot_name} PREPARED.json"
            )["content_sha256"],
            "families": families,
            "primary_rate_differences": rate_differences,
            "primary_C_rate_differences_unbalanced_minus_slack": c_rate_differences,
            "spatial_A_predicates": spatial,
            "d013_trigger_disposition": disposition,
            "v14_primary_condition_comparison": v14,
            "d011_matched_subgrid": d011,
        })

    # The five boolean predicates the mechanical reduction consumes, derived
    # once per instance so `cross_instance_reduction` reads a status rather
    # than recomputing.  They are OBSERVED exact predicates, never verdicts.
    for row in per_slot:
        spatial = row["spatial_A_predicates"]
        row["observed_exact_predicates"] = {
            "d013_trigger_fired": bool(row["d013_trigger_disposition"]["fired"]),
            "nonbox_A_region_observed": any(
                shape["axis_aligned_box"] == "no"
                for entry in spatial.values()
                for shape in entry["A_region_shape"].values()),
            "both_directional_A_advantages_observed": any(
                entry["both_directional_A_advantages"] == "yes"
                for entry in spatial.values()),
        }

    reductions = {
        name: cross_instance_reduction(per_slot, name)
        for name in ("d013_trigger_fired", "nonbox_A_region_observed",
                     "both_directional_A_advantages_observed")
    }

    payload: dict[str, Any] = {
        "schema": INFERENCE_SCHEMA,
        "purpose": "Stage-2 inference over five real production slots. Frozen "
                   "quantities only: exact censuses, the paired encoding "
                   "difference, the exact-sign D013 disposition, exact integer "
                   "spatial predicates, the V-14 and D011 companions, and the "
                   "mechanical all_five/any_one/count_of_five reduction. No "
                   "threshold, no winner, no pooling, no boundary fit.",
        "slot_count": len(per_slot),
        "is_mock": not schema.is_frozen_census(census),
        "is_mock_statement":
            "TRUE means every number below is FABRICATED by "
            "make_mock_outputs_v2.py and is not a scientific result. It is set "
            "solely by the census profile not being the frozen real census."
            if not schema.is_frozen_census(census) else None,
        "slots": per_slot,
        "cross_instance_reduction": reductions,
        "hypothesis_evaluation": {
            "H0_rate_comparability": {
                "status": "indeterminate_no_preregistered_comparability_threshold",
                "citation": "GATE_9_STAGE2_PROTOCOL_DRAFT.md:200-204; "
                            "CLAIMS_AND_LIMITATIONS_REGISTER.md CL-02",
                "observed": "exact Delta(r) signs are reported per instance; "
                            "no threshold exists against which to compare them",
            },
            "H1_rank_instability": {
                "status": "indeterminate_no_preregistered_subregion_criterion",
                "citation": "CLAIMS_AND_LIMITATIONS_REGISTER.md C-17, CL-02; "
                            "GATE_8_CRITICAL_REVIEW_AND_EXIT.md:59-60",
                "observed": "literal pointwise A-advantage predicates are "
                            "reported; no sub-region criterion exists and none "
                            "is derived here",
            },
            "H2_infeasibility_asymmetry": {
                "status": "indeterminate_no_preregistered_measurability_threshold",
                "citation": "CLAIMS_AND_LIMITATIONS_REGISTER.md C-18, CL-02",
                "observed": "exact C-census differences are reported; no "
                            "measurability threshold exists",
            },
            "H3_constraint_heterogeneity": {
                "status": "indeterminate_for_the_active_set_claim",
                "citation": "CLAIMS_AND_LIMITATIONS_REGISTER.md C-19, CL-08",
                "observed": "within-sweep non-box A-region predicates are "
                            "reported; the active-set claim requires a fired "
                            "trigger and a completed ablation",
            },
            "note": "Every threshold word stays INDETERMINATE. No dated owner "
                    "approval in the reviewed decision set raises any of them; "
                    "GATE_9_STAGE2_PROTOCOL_APPROVAL.md:44-46 explicitly "
                    "records that the protocol decision 'does not ... "
                    "introduce a hypothesis threshold'.",
        },
        "not_computed": {
            "thresholds": "GATE_9_STAGE2_PROTOCOL_DRAFT.md:200-204",
            "winners_or_advantages": "CLAIMS_AND_LIMITATIONS_REGISTER.md P-06",
            "pooled_rates": "GATE_9_STAGE2_PROTOCOL_DRAFT.md:195-198, P-16",
            "boundary_fit_smoothing_ranking": "P-20; "
                                             "GATE_6_OWNER_EXECUTION_DECISIONS.md:19-22",
            "d013_ablation_results":
                "the four conditions ran in-kernel only when the trigger fired "
                "(full_production_parent_v2.py:119-146); they are not declared "
                "families of this reader and no ablation quantity is derived "
                "here",
            "energies_ties_labels": "re-deriving H_E, T_E, X_E, f* or Lambda_ref "
                                    "would be a second scientific computation; "
                                    "every number here is read from a committed, "
                                    "hash-verified reconstruction summary "
                                    "(stage2_cuda_reconstruct.py:196-214)",
            "d015_diagnostic_rates": "DECISIONS.md:437-438 — the four "
                                     "(c_H,c_f) pairs are additionally reported "
                                     "and cannot select a primary result; their "
                                     "shape is verified, their counts are not "
                                     "reduced to a second A-rate",
            "cross_generation_comparison":
                "SLOT-5's 'exact numerator difference versus the matching "
                "accepted Gate-5 subset' (RESULTS_AND_FIGURE_SLOTS.md:130) is "
                "NOT computed: that subset is a Stage-1 artefact and this "
                "pipeline emits no cross-generation comparison",
        },
        "mandatory_conditioning": [
            "D006's mapping is not neutral: D(w)=a(s)w(1-w)<0 for every w>1 at "
            "every s>0, so unbalanced is under-penalised relative to slack at "
            "larger violations. Every unbalanced-vs-slack difference at w>1 is "
            "confounded with this known bias "
            "(DECISIONS.md:266-296; FROZEN_MATH_SPEC.md:211-214; P-09, P-10, CL-01).",
            "The penalty box is conditioning for every conclusion: m_lo=4 is a "
            "recorded judgement and the box neither certifies enforcement nor "
            "makes the A-rate box-independent (FROZEN_MATH_SPEC.md:241-243; CL-04).",
            "V-14 is report-only at r=1; its 0.5x m_hi floor-to-zero defect is a "
            "recorded judgement and both V-14 scales stay separate from the "
            "primary grid and from each other (DECISIONS.md:1829, 1834-1836; CL-05, P-16).",
            "D011 is non-primary, matched-subgrid only, and carries the known "
            "positive local curvature-match bias D_CM(w)=s_j*w>0; it is not a "
            "D013 trigger input and not rank-stability evidence "
            "(DECISIONS.md:1036-1038, 1153; CL-06, P-17).",
            "Exactness rests on frozen judgements, not theorems: epsilon=2^-52 "
            "and c_H=c_f=2048 are not universal forward-error bounds "
            "(FROZEN_MATH_SPEC.md:404-405; CL-07).",
            "One bad paired record is decisive for essentially every exact "
            "count, rate, sign and topology predicate reported here "
            "(GATE_9_CONCLUSION_VERIFICATION_MAPPING_DRAFT.md:6-10; CL-16).",
            "Each instance is reported separately first; the cross-instance "
            "figure is the mechanical all_five/any_one/count_of_five reduction "
            "of five statuses and no rate is pooled "
            "(GATE_9_STAGE2_PROTOCOL_DRAFT.md:195-198).",
            "No generalisation beyond the five-instance family is claimed "
            "(CLAIMS_AND_LIMITATIONS_REGISTER.md C-21, CL-03).",
        ],
    }
    payload["provenance"] = {
        "results_root": str(results_root),
        "census_profile": {
            "label": census["label"],
            "content_sha256": census["content_sha256"],
            "records_per_range": census["records_per_range"],
            "per_slot_rows": census["per_slot_rows"],
            "per_slot_sealed_ranges": census["per_slot_sealed_ranges"],
            "per_slot_cuda_flushes": census["per_slot_cuda_flushes"],
            "is_frozen_real_census": schema.is_frozen_census(census),
        },
        "input_sha256": input_hashes,
        "verified_by": "verify_outputs_v2.py (run separately; its own "
                       "report hash is supplied by the caller)",
        "analyzer_source_sha256": schema.sha256_hex(
            Path(__file__).resolve().read_bytes()),
        "schema_module_source_sha256": schema.sha256_hex(
            Path(schema.__file__).resolve().read_bytes()),
    }
    payload["content_sha256"] = schema.content_sha256(payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit STAGE2_INFERENCE.json from five verified real "
                    "production slots.")
    parser.add_argument("--results-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path,
                        help="Output directory for STAGE2_INFERENCE.json.")
    parser.add_argument("--verify-report", type=Path, default=None,
                        help="A verify_outputs_v2.py report to embed as evidence.")
    parser.add_argument("--census", type=Path,
                        default=Path(__file__).resolve().parent
                        / schema.FROZEN_CENSUS_NAME,
                        help="Census profile the inputs were verified against. "
                             "Defaults to the shipped frozen real census. A "
                             "non-frozen profile sets is_mock: true in the "
                             "output record.")
    parser.add_argument('--check-inputs-only', action='store_true',
                        help='Validate format and completeness, then exit before inference.')
    parser.add_argument('--piece-plan', type=Path)
    parser.add_argument('--piece-outputs', type=Path)
    args = parser.parse_args(argv)

    if not args.results_root.is_dir():
        sys.stderr.write(f"results root is not a directory: {args.results_root}\n")
        return 2

    try:
        census = schema.load_census_profile(args.census)
    except Stage2AnalysisError as exc:
        sys.stderr.write(f"census profile refused: {exc}\n")
        return 2

    from verify_outputs_v2 import build_report
    validation = build_report(args.results_root.resolve(), census, args.piece_plan, args.piece_outputs)
    if validation['failure_count']:
        sys.stderr.write(f"incomplete: verification failures={validation['failure_count']}: "
                         + validation['failures'][0]['detail'] + '\n')
        return 2
    if args.check_inputs_only:
        print(f"input checks={validation['checks_run']} failures=0")
        return 0
    from export_certificates_v3 import scratch_only
    scratch_only(args.out)
    if schema.is_frozen_census(census):
        raise Stage2AnalysisError('real-data runs are FORMAT tests only; use --check-inputs-only')
    payload = build_inference(args.results_root.resolve(), census)
    payload['provenance']['validation_report_content_sha256'] = validation['content_sha256']
    payload['provenance']['verification_scope'] = validation['verification_scope']
    if validation['piece_collection_proofs']:
        payload['accepted'] = False
        payload['status'] = 'candidate_baseline_piece_merge'
        payload['conditional_and_image_acceptance_pending'] = True
    if args.verify_report is not None:
        payload["provenance"]["verify_outputs_v2_report_sha256"] = \
            schema.sha256_hex(args.verify_report.read_bytes())
        payload["content_sha256"] = schema.content_sha256(payload)

    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / "STAGE2_INFERENCE.json"
    if target.exists():
        raise Stage2AnalysisError('refusing overwrite of inference')
    payload["content_sha256"] = schema.content_sha256(payload)
    body = schema.canonical_bytes(payload) + b"\n"
    target.write_bytes(body)

    print("G9 Stage-2 inference")
    print("=" * 72)
    print(f"output        : {target}")
    print(f"content sha256: {payload['content_sha256']}")
    print(f"file sha256   : {schema.sha256_hex(body)}")
    for row in payload["slots"]:
        disposition = row["d013_trigger_disposition"]
        print(f"  slot {row['slot']} ({row['instance_id']}): "
              f"D013 {disposition['disposition']}, signs "
              f"{','.join(disposition['signs'])}")
    for name, reduction in payload["cross_instance_reduction"].items():
        print(f"  {name}: count_of_five={reduction['count_of_five']}/5 "
              f"all_five={reduction['all_five']} any_one={reduction['any_one']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
