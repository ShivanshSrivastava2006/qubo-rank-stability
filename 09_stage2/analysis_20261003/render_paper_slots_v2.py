#!/usr/bin/env python3
"""Render the Stage-2 paper slots from STAGE2_INFERENCE.json.

Run after `analyze_stage2_v2.py` has written the inference record:

    python3 -B render_paper_slots_v2.py --inference <dir>/STAGE2_INFERENCE.json \\
                                      --out <dir>

It writes, into `--out` ONLY:

  tables/  the Stage-2 LaTeX tables for the slots whose input exists
  figures/ a CSV of exact integers plus a PNG/PDF plot per figure slot

It NEVER writes into `project/paper/`.  `project/paper/` is a read-only input;
`--out` is required and has no default, so a missing argument cannot cause a
write there.

--------------------------------------------------------------------------
SLOT-BY-SLOT: what is emitted, and what is NOT
--------------------------------------------------------------------------

SOURCE OF THE SLOT LIST: `project/paper/RESULTS_AND_FIGURE_SLOTS.md`.

SLOT-1  Paired 3-D table — primary A/B/C census and `rho_E^exact` per `r`,
        slack and unbalanced side by side, plus the paired
        `rho_slack - rho_unbalanced` differences with signs.
        Status: EMITTED for Stage 2.  **No winner is adjudicated**, because no
        pre-registered comparability threshold exists (SLOT-1 analysis rule,
        `:72`; `CLAIMS_AND_LIMITATIONS_REGISTER.md` P-06).

SLOT-2  Paired 3-D figure — the exact integer spatial predicates of the
        A-region and of each directional A-advantage set.
        Status: EMITTED as a table of the exact predicates AND as a CSV.
        **No boundary is fitted and no sub-region or crossover criterion is
        derived** (SLOT-2 PROHIBITED use, `:91`;
        `GATE_8_CRITICAL_REVIEW_AND_EXIT.md:59-60`).

SLOT-3  `D(w) = a(s) w (1-w)` conditioning figure.
        Status: **NOT EMITTED HERE.**  It is a RULE, not a record: its input is
        `DECISIONS.md:266-270` and `FROZEN_MATH_SPEC.md:190, 211-214`, and it
        requires `Lambda_ref` and the reachable supports, which are *pre-
        canonical expected values* that `P-18` and `DECISIONS.md:273-277`
        forbid citing as canonical.  Emitting it from this pipeline would put an
        uncited pre-canonical quantity into a figure.  `project/paper/
        manuscript/figures/plot_slot3_penalty_gap_dw.py` already exists for it
        and is left untouched.

SLOT-4  V-14 box-expansion companion — three labelled panels (0.5x / primary /
        2x), reported separately, never pooled.
        Status: EMITTED as three separate labelled blocks with the declared
        extents and the mandatory 0.5x floor-to-zero defect annotation
        (SLOT-4 mandatory annotation, `:119`; `DECISIONS.md:1834-1836`).

SLOT-5  D011 curvature-match matched-subgrid table.
        Status: EMITTED **only** as the exact rational `A_count / 2197` per
        encoding.  **No float approximation, no full-grid rate, no D015
        diagnostic, no label lattice, no edge list, no inference, and no
        cross-generation numerator difference** (SLOT-5 analysis rule, `:130`).
        The known `D_CM(w) = s_j w > 0` bias annotation is mandatory (`:134`).

SLOT-6  D013 trigger disposition table.
        Status: EMITTED — the per-instance exact-sign disposition and the
        mechanical cross-instance `all_five/any_one/count_of_five`.
        **It never claims H3 is confirmed** (SLOT-6, `:149`; C-19).

SLOT-7  Per-instance exact-census table.
        Status: EMITTED as ONE TABLE PER INSTANCE, with a single separate
        cross-instance reduction block.  **Raw rates are never pooled**, and
        the reduction is mechanical and unweighted (SLOT-7 analysis rule,
        `:159`; `GATE_9_STAGE2_PROTOCOL_DRAFT.md:195-198`; P-16).

SLOT-8  D013 ablation conditions C / CB / CS / CSB.
        Status: **NOT EMITTED.**  The input does not exist for this reader: the
        four conditions are not declared families of `stage2_schema_v2`, they ran
        in-kernel only if the trigger fired
        (`full_production_parent_v2.py:119-146`), and no ablation quantity is
        derived by `analyze_stage2_v2.py`.  A stub is written that states exactly
        this and produces no number — the SLOT-7 precedent is
        `project/paper/manuscript/figures/plot_slot7_stage2_per_instance.py`,
        an explicit machine-checkable marker of a correctly refused slot.

MOCK LABELLING
--------------
Every generated file — every `.tex`, every `.csv`, every plot title and every
caption — carries the literal token `MOCK` when, and only when, the inference
record declares itself a mock (`STAGE2_MOCK.json` present, or
`is_mock == true` in the record).  The token is written into the file body, not
just the filename, so a stray file cannot be mistaken for a real result.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import stage2_schema_v2 as schema  # noqa: E402
from stage2_schema_v2 import Stage2AnalysisError  # noqa: E402

_require = Stage2AnalysisError
"""The renderer's single refusal type, matching the other three scripts."""

RENDER_SCHEMA = "decisions_os/g9_stage2_rendered_slots/v1"

CONDITIONING_BANNER = (
    "D006's mapping is not neutral: $D(w)=a(s)w(1-w)<0$ for every $w>1$ at "
    "every $s>0$, so unbalanced is under-penalised relative to slack at larger "
    "violations. Any unbalanced-vs-slack difference at $w>1$ is confounded with "
    "this known bias."
)


# ---------------------------------------------------------------------------
# Small LaTeX helpers
# ---------------------------------------------------------------------------

def tex_escape(text: str) -> str:
    for char in ("\\", "{", "}", "$", "&", "#", "_", "%", "~", "^"):
        text = text.replace(char, "\\" + char if char in "\\&#$_%{}^~" else char)
    return text


def rational_block(value: dict[str, Any], label: str = "") -> str:
    return (f"$\\frac{{{value['numerator']:,}}}{{{value['denominator']:,}}}$"
            + (f" {tex_escape(label)}" if label else ""))


def num(value: int) -> str:
    """An integer for a LaTeX table cell.

    A bare `1,225` makes LaTeX read a PUNCTUATION comma as a thousands
    separator and drop it, so the cell typesets as `1225`; grouping must be
    written `1{,}225`, which LaTeX renders as `1,225`.  An exact count must not
    silently lose its grouping in the paper.
    """
    _require(type(value) is int,
             f"only an exact integer may be formatted as a table number: {value!r}")
    return f"{value:,}".replace(",", "{,}")


def sign_word(value: str) -> str:
    return {"positive": "$+$", "negative": "$-$", "zero": "$0$"}.get(value,
                                                                   str(value))


def bool_word(value: bool) -> str:
    """LaTeX for a Python bool.  `True`/`False` are identifiers in a LaTeX
    document, not the words the paper uses, so they are rendered explicitly."""
    return "\\textbf{true}" if value else "\\textbf{false}"


def banner(is_mock: bool, status: str) -> list[str]:
    lines = [f"% STATUS: {status}"]
    if is_mock:
        lines.insert(0, "% " + schema.MOCK_LABEL + " DATA — SYNTHETIC, NOT A RESULT")
        lines.insert(1, "% This file was produced from a MOCK harness run. "
                        "Every number is fabricated")
        lines.insert(2, "% by make_mock_outputs_v2.py and is NOT a scientific "
                        "result of the study.")
    return lines


def mock_caption(is_mock: bool) -> str:
    if is_mock:
        return ("\\textbf{MOCK SYNTHETIC DATA --- NOT A RESULT.} Produced by the "
                "pipeline's MOCK harness from fabricated records; every value "
                "below is an artefact of the mock generator and carries no "
                "scientific meaning.")
    return ""


# ---------------------------------------------------------------------------
# SLOT-1 / SLOT-7 — the paired 3-D census tables
# ---------------------------------------------------------------------------

def primary_rows(slot: dict[str, Any]) -> list[dict[str, Any]]:
    """The three primary cells, one per `r`, merged for the census tables.

    Each primary FAMILY carries exactly one `r`
    (`stage2_coordinate_records.py:370-377`), so the three-r table is assembled
    by reading the r = 0.5, 1.0 and 2.0 family entries in the frozen r order.
    `RESULTS_AND_FIGURE_SLOTS.md:72` requires the six cells grouped by `r_hex`
    with slack and unbalanced side by side, which is exactly this shape.
    """
    rows: list[dict[str, Any]] = []
    for r_hex in schema.PRIMARY_R_HEX:
        key = next(key for key in slot["families"]
                   if schema.FAMILY_R_HEX[key] == r_hex
                   and schema.FAMILY_GROUP[key] == "primary")
        cells = slot["families"][key]["reported_cells"]
        _require(len(cells) == 1 and cells[0]["r_hex"] == r_hex,
                 f"the primary family {key} does not carry exactly r={r_hex}")
        rows.append({"r_hex": r_hex,
                     "r_display": schema.PRIMARY_R_DISPLAY[r_hex],
                     **cells[0]["encodings"]})
    return rows


def slot_census_table(rows: list[dict[str, Any]], is_mock: bool, title: str,
                      caption_source: str, slot: str) -> str:
    """One paired table: per `r`, both encodings side by side.

    `RESULTS_AND_FIGURE_SLOTS.md:41-43` requires a paired encoding comparison
    to display slack and unbalanced on the SAME axis settings side by side;
    `:69` requires the A-rate per `r` without adjudication.
    """
    lines = banner(is_mock, f"{slot} — exact census, quoted, not interpreted")
    lines += [
        "% Exact integer counts and exact rationals only; no decimals "
        "(RESULTS_AND_FIGURE_SLOTS.md:38-41).",
        "% Third axis: the sweep is the 3-D cube [s_min,s_max]^3 over "
        f"(s_card, s_sector, s_budget) with 61 points per axis = "
        f"{schema.PRIMARY_COORDINATE_COUNT:,} coordinates. rho_E^exact is the "
        "exact finite-grid A-rate over all three axes "
        "(FROZEN_MATH_SPEC.md:473); a 2-D projection would discard s_card.",
        "% Worst-case decisive caveat: one bad label record at any one "
        "coordinate changes that coordinate's label and therefore this table's "
        "numerator (GATE_9_CONCLUSION_VERIFICATION_MAPPING_DRAFT.md:6-10; CL-16).",
        "",
        f"\\begin{{table}}[t]",
        "\\centering",
        f"\\caption{{\\textbf{{{slot}}} --- {tex_escape(title)}. "
        f"{mock_caption(is_mock)} Exact integer counts and exact rationals; "
        f"signs are presented, \\textbf{{no winner is adjudicated}}. "
        f"\\accLbl\\ Source: {tex_escape(caption_source)}. "
        "The unbalanced mapping is not a neutral baseline: "
        "$D(w)<0$ for all $w>1$, which confounds the comparison "
        "(DECISIONS.md:266-296).}",
        f"\\label{{tab:{slot.lower().replace('-', '').replace(' ', '-')}}}",
        "\\begin{tabular}{@{}llrrrrrr@{}}",
        "\\toprule",
        "\\textbf{$r$} & \\textbf{encoding} & \\textbf{$A$} & \\textbf{$B$} "
        "& \\textbf{$C$} & \\textbf{$I_C^{\\mathrm{exist}}$} "
        "& \\textbf{$I_C^{\\mathrm{univ}}$} & \\textbf{$\\rho_E^{\\mathrm{exact}}$}\\\\",
        "\\midrule",
    ]
    for row in rows:
        for encoding in schema.ENCODINGS:
            cell = row[encoding]
            counts = cell["set_label_counts"]
            lines.append(
                f"{row['r_display']} & {encoding} "
                f"& {num(counts['A'])} & {num(counts['B'])} & {num(counts['C'])} "
                f"& {num(cell['I_C_exist_count'])} & {num(cell['I_C_univ_count'])} "
                f"& {num(cell['rho_E_exact']['numerator'])}"
                f"/{num(cell['rho_E_exact']['denominator'])}\\\\")
    lines += ["\\bottomrule", "\\end{tabular}", "\\end{table}", ""]
    return "\n".join(lines)


def slot_difference_table(rates: list[dict[str, Any]],
                          c_rates: list[dict[str, Any]], is_mock: bool,
                          slot: str, source: str) -> str:
    """SLOT-1's paired differences and the C-rate differences, with signs."""
    lines = banner(is_mock, f"{slot} — paired differences, signs only")
    lines += [
        "% Delta(r) = rho_slack - rho_unbalanced is the ACCEPTED encoding "
        "contrast (DECISIONS.md:1120-1124). Count(A)-Count(C) is NOT used: it "
        "is a within-encoding mixture with no slack-vs-unbalanced contrast "
        "(RESULTS_AND_FIGURE_SLOTS.md:21).",
        "% No threshold exists against which any sign could be adjudicated; "
        "the rate-comparison component is INDETERMINATE "
        "(GATE_7_STAGE1_CONCLUSION_AND_EXIT.md:26-28; P-06).",
        "",
        f"\\begin{{table}}[t]",
        "\\centering",
        f"\\caption{{\\textbf{{{slot}}} --- paired encoding differences on the "
        f"matched 3-D primary grid. {mock_caption(is_mock)} "
        "$\\Delta(r)=\\rho^{\\mathrm{exact}}_{\\mathrm{slack}}-"
        "\\rho^{\\mathrm{exact}}_{\\mathrm{unbalanced}}$ is the accepted "
        "encoding contrast; the second block is the C-census difference "
        "$\\mathrm{unbalanced}-\\mathrm{slack}$. "
        "\\textbf{Signs are shown; nothing is adjudicated.} "
        f"\\accLbl\\ Source: {tex_escape(source)}. "
        "Signs are unadjudicated: no pre-registered comparability threshold "
        "exists.}",
        f"\\label{{tab:{slot.lower().replace('-', '').replace(' ', '-')}-diff}}",
        "\\begin{tabular}{@{}llrrl@{}}",
        "\\toprule",
        "\\textbf{quantity} & \\textbf{$r$} & \\textbf{numerator} "
        "& \\textbf{denominator} & \\textbf{sign}\\\\",
        "\\midrule",
    ]
    for row in rates:
        lines.append(
            "$\\Delta(r)=\\rho_{\\mathrm{slack}}-"
            "\\rho_{\\mathrm{unbalanced}}$ "
            f"& {row['r_display']} & {num(row['numerator'])} "
            f"& {num(row['denominator'])} & {sign_word(row['sign'])}\\\\")
    lines.append("\\midrule")
    for row in c_rates:
        lines.append(
            "$C$-census $\\mathrm{unbalanced}-\\mathrm{slack}$ "
            f"& {row['r_display']} & {num(row['numerator'])} "
            f"& {num(row['denominator'])} & {sign_word(row['sign'])}\\\\")
    lines += ["\\bottomrule", "\\end{tabular}", "\\end{table}", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SLOT-2 — the exact integer spatial predicates
# ---------------------------------------------------------------------------

def slot2_table(spatial: dict[str, Any], is_mock: bool, source: str) -> str:
    lines = banner(is_mock, "SLOT-2 — exact A-region shape and topology")
    lines += [
        "% Rendered verbatim from the exact integer predicates. No label is "
        "re-derived and no boundary is refit "
        "(RESULTS_AND_FIGURE_SLOTS.md:86).",
        "% PROHIBITED use: these fields may NOT be repurposed as a crossover or "
        "sub-region criterion (RESULTS_AND_FIGURE_SLOTS.md:91; "
        "GATE_8_CRITICAL_REVIEW_AND_EXIT.md:59-60). That prohibition is exactly "
        "why H1 is not adjudicated.",
        "% Projections are over ALL THREE axes: [61,32,52] would mean the slack "
        "A-region spans all 61 s_card coordinates but only 32 of 61 s_sector "
        "and 52 of 61 s_budget coordinates (RESULTS_AND_FIGURE_SLOTS.md:87).",
        "% Worst-case decisive caveat: one mislabelled point inside the region "
        "can add a bridge and change component_count; one point added just "
        "outside can flip axis_aligned_box "
        "(RESULTS_AND_FIGURE_SLOTS.md:89).",
        "",
        "\\begin{table}[t]",
        "\\centering",
        f"\\caption{{\\textbf{{SLOT-2}} --- shape and topology of the "
        f"exact-optimum region, exact integers only. {mock_caption(is_mock)} "
        "No boundary is fitted and no crossover criterion is derived; these "
        "fields may not be repurposed as one. "
        f"\\accLbl\\ Source: {tex_escape(source)}.}}",
        "\\label{tab:stage2-slot2}",
        "\\begin{tabular}{@{}llrrrrl@{}}",
        "\\toprule",
        "\\textbf{$r$} & \\textbf{region} & \\textbf{points} "
        "& \\textbf{components} & \\textbf{largest} "
        "& \\textbf{projections} & \\textbf{box}\\\\",
        "\\midrule",
    ]
    for r_hex in schema.PRIMARY_R_HEX:
        entry = spatial[r_hex]
        display = schema.PRIMARY_R_DISPLAY[r_hex]
        for encoding in schema.ENCODINGS:
            shape = entry["A_region_shape"][encoding]
            projections = ",".join(str(v) for v in shape["axis_projection_sizes"])
            lines.append(
                f"{display} & {encoding} A-region & {num(shape['A_point_count'])} "
                f"& --- & --- & [{projections}] "
                f"& {shape['axis_aligned_box']}\\\\")
        for direction in ("slack_A_advantage", "unbalanced_A_advantage"):
            row = entry[direction]
            lines.append(
                f"{display} & {direction} & {num(row['point_count'])} "
                f"& {num(row['component_count'])} & {num(row['largest_component_size'])} "
                f"& --- & ---\\\\")
        lines.append(
            f"{display} & both-directional present "
            f"& --- & --- & --- & --- "
            f"& {entry['both_directional_A_advantages']}\\\\")
        lines.append("\\midrule")
    lines += ["\\bottomrule", "\\end{tabular}", "\\end{table}", ""]
    return "\n".join(lines)


def slot2_csv(spatial: dict[str, Any], is_mock: bool) -> str:
    out = ["# MOCK SYNTHETIC DATA — NOT A RESULT"]
    out.append("# exact integers only; no fitted boundary; see ANALYSIS_NOTES.md")
    out.append("r_hex,r_display,encoding,A_point_count,cartesian_product,"
               "axis_aligned_box,proj_card,proj_sector,proj_budget")
    for r_hex in schema.PRIMARY_R_HEX:
        for encoding in schema.ENCODINGS:
            shape = spatial[r_hex]["A_region_shape"][encoding]
            projections = shape["axis_projection_sizes"]
            out.append(f"{r_hex},{schema.PRIMARY_R_DISPLAY[r_hex]},{encoding},"
                       f"{shape['A_point_count']},{shape['cartesian_product']},"
                       f"{shape['axis_aligned_box']},{projections[0]},"
                       f"{projections[1]},{projections[2]}")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# SLOT-4 / SLOT-5 / SLOT-6
# ---------------------------------------------------------------------------

def slot4_table(v14: dict[str, Any], primary_rates: list[dict[str, Any]],
                is_mock: bool, source: str) -> str:
    lines = banner(is_mock, "SLOT-4 — V-14 box expansion, report-only")
    lines += [
        "% Three separate, labelled panels with their DECLARED extents. The "
        "grids differ in extent, so a shared axis range would misrepresent one "
        "of them (RESULTS_AND_FIGURE_SLOTS.md:116).",
        "% MANDATORY ANNOTATION — the 0.5x RECORDED DEFECT: 0.5*m_hi is "
        "non-integer and is floored to m_hi = 0. This is a judgement, not a "
        "theorem, and it must be printed with any V-14 result "
        "(DECISIONS.md:1834-1836; CL-05).",
        "% PROOF / POOLING PROHIBITION: both scales remain separate report-only "
        "companion evidence, not pooled with the primary grid or used to extend "
        "a conclusion (GATE_7_STAGE1_CONCLUSION_AND_EXIT.md:38-40; P-16).",
        "% V-14 is r = 1 only (DECISIONS.md:1829).",
        "",
        "\\begin{table}[t]",
        "\\centering",
        f"\\caption{{\\textbf{{SLOT-4}} --- V-14 penalty-box expansion, three "
        f"separate report-only panels. {mock_caption(is_mock)} "
        "Each panel keeps its own declared extent; the three are never pooled. "
        "The $0.5\\times$ panel carries a \\textbf{recorded structural defect}: "
        "$0.5\\cdot m_{hi}=0.5$ is non-integer and is floored to $m_{hi}=0$, a "
        "judgement and not a theorem (DECISIONS.md:1834-1836). "
        "No conclusion is extended from this companion. "
        f"\\accLbl\\ Source: {tex_escape(source)}.}}",
        "\\label{tab:stage2-slot4}",
        "\\begin{tabular}{@{}llrrrrl@{}}",
        "\\toprule",
        "\\textbf{panel} & \\textbf{$r$} & \\textbf{$q$ range} "
        "& \\textbf{points} & \\textbf{$\\rho_{\\mathrm{slack}}-"
        "\\rho_{\\mathrm{unbalanced}}$} & \\textbf{sign} & \\textbf{status}\\\\",
        "\\midrule",
    ]
    primary_delta = next(row for row in primary_rates
                         if row["r_hex"] == schema.PRIMARY_R_HEX[1])
    lines.append(
        f"0.5$\\times$ & 1.0 & $[{v14['0.5x']['q_range'][0]},"
        f"{v14['0.5x']['q_range'][1]}]$ "
        f"& {num(v14['0.5x']['coordinate_count'])} "
        f"& {num(v14['0.5x']['exact_counts'][0])}"
        f"/{num(v14['0.5x']['exact_counts'][1])} "
        f"& {sign_word(v14['0.5x']['sign'])} "
        "& report-only; \\\\textbf{recorded $m_{hi}=0$ floor defect}\\\\")
    lines.append(
        f"primary & 1.0 & $[-4, 2]$ "
        f"& {num(schema.PRIMARY_COORDINATE_COUNT)} "
        f"& {num(primary_delta['numerator'])}/{num(primary_delta['denominator'])} "
        f"& {sign_word(primary_delta['sign'])} & primary grid\\\\")
    lines.append(
        f"2$\\times$ & 1.0 & $[{v14['2x']['q_range'][0]},"
        f"{v14['2x']['q_range'][1]}]$ "
        f"& {num(v14['2x']['coordinate_count'])} "
        f"& {num(v14['2x']['exact_counts'][0])}"
        f"/{num(v14['2x']['exact_counts'][1])} "
        f"& {sign_word(v14['2x']['sign'])} & report-only\\\\")
    lines += ["\\bottomrule", "\\end{tabular}", "\\end{table}", ""]
    return "\n".join(lines)


def slot5_table(d011: dict[str, Any], is_mock: bool, source: str) -> str:
    lines = banner(is_mock, "SLOT-5 — D011 curvature-match matched subgrid")
    lines += [
        "% Reported SOLELY as the exact rational A_count / 2197. No float "
        "approximation, no full-grid rate, no D015 diagnostic, no label "
        "lattice, no edge list, no inference "
        "(RESULTS_AND_FIGURE_SLOTS.md:130; "
        "GATE_6_D011_MATCHED_SUBGRID_AUTHORIZATION.md:16-22).",
        "% MANDATORY ANNOTATION: the known directional bias "
        "D_CM(w) = s_j*w > 0 is conditioning only and does not predict, "
        "establish or bound any A/B/C result (DECISIONS.md:1036-1038; CL-06).",
        "% NOT a D013 trigger input (DECISIONS.md:1153) and NOT rank-stability "
        "evidence (P-17).",
        "",
        "\\begin{table}[t]",
        "\\centering",
        f"\\caption{{\\textbf{{SLOT-5}} --- D011 curvature-match companion on "
        f"the {num(d011['coordinate_count'])}-point matched subgrid. "
        f"{mock_caption(is_mock)} Exact rationals only. The known directional "
        "bias $D_{{CM}}(w)=s_jw>0$ is conditioning only and does not predict, "
        "establish or bound any A/B/C result; this companion is not a D013 "
        "trigger input and not rank-stability evidence. "
        f"\\accLbl\\ Source: {tex_escape(source)}.}}",
        "\\label{tab:stage2-slot5}",
        "\\begin{tabular}{@{}lrrl@{}}",
        "\\toprule",
        "\\textbf{encoding} & \\textbf{$A$ count} & \\textbf{denominator} "
        "& \\textbf{$\\rho_E^{\\mathrm{exact}}$}\\\\",
        "\\midrule",
    ]
    for encoding in schema.ENCODINGS:
        counts = d011["exact_counts"][encoding]
        value = d011["rho_E_exact"][encoding]
        lines.append(f"{encoding} & {num(counts[0])} & {num(counts[1])} "
                     f"& {num(value['numerator'])}/{num(value['denominator'])}\\\\")
    lines += ["\\bottomrule", "\\end{tabular}", "\\end{table}", ""]
    return "\n".join(lines)


def slot6_table(dispositions: list[dict[str, Any]], reduction: dict[str, Any],
                is_mock: bool, source: str) -> str:
    lines = banner(is_mock, "SLOT-6 — D013 trigger disposition")
    lines += [
        "% The rule is applied MECHANICALLY: fires iff any Delta(r) is exactly "
        "zero OR the three do not all share one strict sign. NO numerical "
        "tolerance of any kind (DECISIONS.md:1125-1131; "
        "RESULTS_AND_FIGURE_SLOTS.md:144).",
        "% The trigger consumes exactly the six (c_H,c_f)=(2048,2048) primary "
        "cells r in {0.5,1,2} x {slack, unbalanced}; it must NOT be computed "
        "from a 2-D projection or from D015 diagnostics "
        "(RESULTS_AND_FIGURE_SLOTS.md:146).",
        "% This table NEVER claims H3 is confirmed (C-19); it reports the "
        "disposition only.",
        "",
        "\\begin{table}[t]",
        "\\centering",
        f"\\caption{{\\textbf{{SLOT-6}} --- D013 exact-sign trigger disposition, "
        f"per instance and across the family. {mock_caption(is_mock)} "
        "Applied mechanically with no numerical tolerance. A no-fire or a fire "
        "is a bounded disposition; it is not a confirmation of H3. "
        f"\\accLbl\\ Source: {tex_escape(source)}.}}",
        "\\label{tab:stage2-slot6}",
        "\\begin{tabular}{@{}llccl@{}}",
        "\\toprule",
        "\\textbf{instance} & \\textbf{signs of $\\Delta(r)$, "
        "$r=0.5,1,2$} & \\textbf{any $\\Delta=0$} "
        "& \\textbf{disposition} & \\textbf{ablation}\\\\",
        "\\midrule",
    ]
    for row in dispositions:
        disposition = row["d013_trigger_disposition"]
        signs = ", ".join(sign_word(s) for s in disposition["signs"])
        lines.append(
            f"{row['instance_id']} & {signs} "
            f"& {'yes' if disposition['any_delta_exactly_zero'] else 'no'} "
            f"& {disposition['disposition']} "
            f"& {tex_escape(disposition['ablation_status'])}\\\\")
    reduction = reduction["d013_trigger_fired"]
    lines += [
        "\\midrule",
        f"all\\_five & --- & --- & {bool_word(reduction['all_five'])} "
        f"& count\\_of\\_five = {reduction['count_of_five']} / 5"
        f" (any\\_one = {str(reduction['any_one']).lower()})\\\\",
        "\\bottomrule",
        "\\end{tabular}",
        "\\end{table}",
        "",
        "\\noindent\\emph{The cross-instance row is the mechanical, unweighted "
        "reduction of five boolean statuses. No raw rate is pooled across "
        "instances or with Stage 1 "
        "(GATE\\_9\\_STAGE2\\_PROTOCOL\\_DRAFT.md:195-198; P-16).}",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SLOT-7 / SLOT-8
# ---------------------------------------------------------------------------

def slot7_header(is_mock: bool) -> str:
    lines = banner(is_mock, "SLOT-7 — per-instance exact census (Stage 2)")
    lines += [
        "% One table PER INSTANCE, reported separately FIRST. The cross-instance "
        "figure is the mechanical all_five / any_one / count_of_five reduction "
        "of five statuses and nothing else; raw rates are NEVER pooled across "
        "instances or with Stage 1 "
        "(GATE_9_STAGE2_PROTOCOL_DRAFT.md:195-198; P-16, C-22).",
        "% Worst-case decisive caveat: one decisive point in one instance is "
        "decisive for the cross-instance reduction "
        "(GATE_9_CONCLUSION_VERIFICATION_MAPPING_DRAFT.md:20).",
        "",
    ]
    return "\n".join(lines)


def slot7_reduction_table(reductions: dict[str, Any], is_mock: bool,
                          source: str) -> str:
    lines = banner(is_mock, "SLOT-7 — mechanical cross-instance reduction")
    lines += [
        "% Five boolean statuses per predicate, reduced mechanically and "
        "unweighted. No rate is aggregated here.",
        "",
        "\\begin{table}[t]",
        "\\centering",
        f"\\caption{{\\textbf{{SLOT-7}} --- mechanical cross-instance "
        f"reduction. {mock_caption(is_mock)} Exact predicates only, reduced "
        "unweighted. No pooled rate is reported and no generalisation beyond "
        "the five-instance family is claimed (C-21, CL-03). "
        f"\\accLbl\\ Source: {tex_escape(source)}.}}",
        "\\label{tab:stage2-slot7-reduction}",
        "\\begin{tabular}{@{}lllll@{}}",
        "\\toprule",
        "\\textbf{predicate} & \\textbf{count\\_of\\_five} "
        "& \\textbf{all\\_five} & \\textbf{any\\_one} "
        "& \\textbf{instance statuses}\\\\",
        "\\midrule",
    ]
    for name, reduction in sorted(reductions.items()):
        statuses = "".join("1" if value else "0"
                           for value in reduction["instance_statuses"])
        lines.append(f"\\texttt{{{tex_escape(name)}}} "
                     f"& {reduction['count_of_five']}/5 "
                     f"& {bool_word(reduction['all_five'])} "
                     f"& {bool_word(reduction['any_one'])} "
                     f"& {statuses}\\\\")
    lines += ["\\bottomrule", "\\end{tabular}", "\\end{table}", ""]
    return "\n".join(lines)


def slot8_stub(dispositions: list[dict[str, Any]], is_mock: bool) -> str:
    """The SLOT-8 refusal marker. It writes NO number and no table body."""
    fired = [row["instance_id"] for row in dispositions
             if row["d013_trigger_disposition"]["fired"]]
    lines = banner(
        is_mock, "SLOT-8 — D013 ablation conditions C / CB / CS / CSB")
    lines += [
        "% STATUS: NOT EMITTED BY THIS PIPELINE. NO TABLE, NO FIGURE, NO NUMBER.",
        "%",
        "% SLOT-8 is conditional on the trigger. This pipeline reads only the six",
        "% declared BASELINE families; the four conditions C/CB/CS/CSB are not",
        "% among them and no ablation quantity is derived anywhere in",
        "% analyze_stage2_v2.py. Where the trigger fired, those families already ran",
        "% in-kernel as part of the 22-family package",
        f"% (full_production_parent_v2.py:119-146); they require a separate,",
        "% separately reviewed reader.",
        f"% Trigger fired in: {', '.join(fired) if fired else 'no instance'}.",
        "%",
        "% Even if it had fired, SLOT-8 may NOT be presented as primary",
        "% confirmation of H3 and may NOT be pooled (DECISIONS.md:1155; C-19).",
        "% Each condition has a DIFFERENT active-axis set, so a common 3-D frame",
        "% implying all axes were swept would misrepresent them",
        "% (RESULTS_AND_FIGURE_SLOTS.md:173).",
        "%",
        "% The precedent for this marker is",
        "% project/paper/manuscript/figures/plot_slot7_stage2_per_instance.py.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def write_figures(out_dir: Path, payload: dict[str, Any], is_mock: bool,
                  slot: dict[str, Any]) -> list[str]:
    """CSV + PNG + PDF per figure slot, from exact integers only.

    `matplotlib` is optional, exactly as in the manuscript's own figure scripts
    (`project/paper/manuscript/figures/plot_slot1_primary_rates.py:24-30`): if
    it is not importable the CSV is still written and the plot is skipped with a
    notice.  The CSV is the primary artefact; the plot only displays it.
    """
    written: list[str] = []
    header = ["# MOCK SYNTHETIC DATA — NOT A RESULT"] if is_mock else []

    # SLOT-1 figure: the paired A/B/C census per r and encoding.
    rows: list[list[Any]] = []
    for row in primary_rows(slot):
        denominator = slot["families"][next(
            key for key in slot["families"]
            if schema.FAMILY_R_HEX[key] == row["r_hex"]
            and schema.FAMILY_GROUP[key] == "primary")]["coordinate_count"]
        for encoding in schema.ENCODINGS:
            counts = row[encoding]["set_label_counts"]
            rows.append([row["r_display"], encoding, counts["A"], counts["B"],
                         counts["C"], denominator])
    slot1_csv = out_dir / "slot7_stage2_per_instance.csv"
    lines = list(header)
    lines += ["# exact integer counts; denominator is the per-instance "
              "coordinate count; no pooling across instances",
              "r,encoding,A,B,C,coordinate_count"]
    for row in rows:
        lines.append(",".join(str(v) for v in row))
    slot1_csv.write_text("\n".join(lines) + "\n", encoding="utf-8")
    written.append(str(slot1_csv))

    # SLOT-2 figure: the exact predicates as a CSV, no fitted boundary.
    slot2_csv_path = out_dir / "slot2_a_region_topology.csv"
    slot2_csv_path.write_text(slot2_csv(slot["spatial_A_predicates"], is_mock),
                              encoding="utf-8")
    written.append(str(slot2_csv_path))

    # SLOT-4 figure: the three V-14 panels as separate CSV rows.
    slot4_csv_path = out_dir / "slot4_v14_box_expansion.csv"
    lines = list(header)
    lines.append("# three separate panels, declared extents, NEVER pooled; "
                 "0.5x carries the recorded m_hi=0 floor defect")
    lines.append("panel,r,q_min,q_max,decades,points,numerator,denominator,sign")
    for scale in ("0.5x", "2x"):
        entry = slot["v14_primary_condition_comparison"][scale]
        lines.append(f"{scale},1.0,{entry['q_range'][0]},{entry['q_range'][1]},"
                     f"{entry['decades']},{entry['coordinate_count']},"
                     f"{entry['slack_minus_unbalanced_rho']['numerator']},"
                     f"{entry['slack_minus_unbalanced_rho']['denominator']},"
                     f"{entry['sign']}")
    slot4_csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    written.append(str(slot4_csv_path))

    written += _plot(out_dir, rows, is_mock)
    return written


def _plot(out_dir: Path, rows: list[list[Any]], is_mock: bool) -> list[str]:
    import os
    os.environ['MPLCONFIGDIR'] = str(out_dir.parent.parent / 'mplconfig_v2')
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        sys.stderr.write("matplotlib not importable; CSVs written, plots "
                         "skipped (no package install is permitted)\n")
        return []

    rs = ["0.5", "1.0", "2.0"]
    encodings = list(schema.ENCODINGS)
    labels = ["A", "B", "C"]
    colors = ["#1b6ca8", "#f0a202", "#c0392b"]
    fig, axes = plt.subplots(1, 2, figsize=(10.0, 4.4), sharey=True)
    width = 0.35
    for ax, encoding in zip(axes, encodings):
        selected = {row[0]: row for row in rows if row[1] == encoding}
        bottoms = [0, 0, 0]
        for offset, (label, color) in enumerate(zip(labels, colors)):
            values = [selected[r][2 + offset] for r in rs]
            ax.bar([index + (0.0 if encoding == "slack" else width)
                    for index in range(len(rs))],
                   values, width, bottom=bottoms, label=label, color=color,
                   edgecolor="black", linewidth=0.4)
            bottoms = [b + v for b, v in zip(bottoms, values)]
        ax.set_xticks([index + width / 2 for index in range(len(rs))])
        ax.set_xticklabels([f"r = {r}" for r in rs])
        ax.set_title(encoding)
        ax.set_xlabel("D006 mapping r")
        ax.yaxis.grid(True, linewidth=0.3, alpha=0.6)
        ax.set_axisbelow(True)
    total = sum(row[5] for row in rows) // max(1, len(encodings))
    axes[0].set_ylabel(f"grid points (exact count, denominator {total:,})")
    axes[0].legend(title="category", loc="upper right", fontsize=8)
    title = ("SLOT-7: per-instance exact A/B/C census on the 61^3 = "
             f"{schema.PRIMARY_COORDINATE_COUNT:,}-coordinate primary grid\n")
    if is_mock:
        title += ("MOCK SYNTHETIC DATA — NOT A RESULT; fabricated by the "
                  "pipeline's mock harness\n")
    title += ("exact counts quoted, not interpreted; signs only, no winner "
              "adjudicated (no pre-registered comparability threshold); the "
              "unbalanced mapping is not a neutral baseline")
    fig.suptitle(title, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    written = []
    for suffix in ("png", "pdf"):
        target = out_dir / f"slot7_stage2_per_instance.{suffix}"
        fig.savefig(target, dpi=200) if suffix == "png" else fig.savefig(target)
        written.append(str(target))
    plt.close(fig)
    return written


# ---------------------------------------------------------------------------
# The runner
# ---------------------------------------------------------------------------

def render(inference_path: Path, out_dir: Path) -> dict[str, Any]:
    _raw, payload = schema.read_json(inference_path, "STAGE2_INFERENCE.json")
    schema.content_sha256(payload)  # re-derives; raises if it disagrees
    is_mock = bool(payload.get("is_mock")) or \
        (inference_path.parent / "STAGE2_MOCK.json").is_file()
    source = ("STAGE2_INFERENCE.json (content sha256 "
              f"{payload['content_sha256'][:16]}...)")

    tables_dir = out_dir / "tables"
    figures_dir = out_dir / "figures"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    written: list[dict[str, Any]] = []
    first = payload["slots"][0]

    # SLOT-1 and SLOT-7 share the census table shape; they differ in scope
    # (per family vs per instance) and therefore get separate files.
    for slot in payload["slots"]:
        name = slot["instance_id"]
        table = tables_dir / f"slot7_{name}_exact_census.tex"
        table.write_text(
            slot_census_table(primary_rows(slot), is_mock,
                              f"per-instance exact census, {name}",
                              source, f"SLOT-7 ({name})"), encoding="utf-8")
        written.append({"path": str(table), "slot": "SLOT-7",
                        "instance_id": name})

    slot = first
    rows = primary_rows(slot)
    table = tables_dir / "slot1_slot2_primary_rates.tex"
    table.write_text(
        slot_census_table(rows, is_mock, "primary census (slot 1 shown; "
                          "all five instances are in the SLOT-7 tables)",
                          source, "SLOT-1"), encoding="utf-8")
    written.append({"path": str(table), "slot": "SLOT-1"})

    table = tables_dir / "slot1_primary_rate_differences.tex"
    table.write_text(
        slot_difference_table(first["primary_rate_differences"],
                              first["primary_C_rate_differences_unbalanced_minus_slack"],
                              is_mock, "SLOT-1", source), encoding="utf-8")
    written.append({"path": str(table), "slot": "SLOT-1"})

    table = tables_dir / "slot2_a_region_topology.tex"
    table.write_text(slot2_table(first["spatial_A_predicates"], is_mock, source),
                     encoding="utf-8")
    written.append({"path": str(table), "slot": "SLOT-2"})

    table = tables_dir / "slot4_v14_box_expansion.tex"
    table.write_text(
        slot4_table(first["v14_primary_condition_comparison"],
                    first["primary_rate_differences"], is_mock, source),
        encoding="utf-8")
    written.append({"path": str(table), "slot": "SLOT-4"})

    table = tables_dir / "slot5_d011_matched_subgrid.tex"
    table.write_text(slot5_table(first["d011_matched_subgrid"], is_mock, source),
                     encoding="utf-8")
    written.append({"path": str(table), "slot": "SLOT-5"})

    table = tables_dir / "slot6_d013_disposition.tex"
    table.write_text(
        slot6_table(payload["slots"],
                    payload["cross_instance_reduction"], is_mock, source),
        encoding="utf-8")
    written.append({"path": str(table), "slot": "SLOT-6"})

    table = tables_dir / "slot7_cross_instance_reduction.tex"
    table.write_text(
        slot7_reduction_table(payload["cross_instance_reduction"], is_mock,
                              source), encoding="utf-8")
    written.append({"path": str(table), "slot": "SLOT-7"})

    table = tables_dir / "slot8_d013_ablation_NOT_EMITTED.tex"
    table.write_text(slot8_stub(payload["slots"], is_mock), encoding="utf-8")
    written.append({"path": str(table), "slot": "SLOT-8"})

    for path in write_figures(figures_dir, payload, is_mock, first):
        written.append({"path": path,
                        "slot": "SLOT-1/SLOT-2/SLOT-4/SLOT-7"})

    manifest = {
        "schema": RENDER_SCHEMA,
        "inference_record": str(inference_path),
        "inference_content_sha256": payload["content_sha256"],
        "is_mock": is_mock,
        "mock_label": schema.MOCK_LABEL if is_mock else None,
        "out_dir": str(out_dir),
        "slots_emitted": ["SLOT-1", "SLOT-2", "SLOT-4", "SLOT-5", "SLOT-6",
                          "SLOT-7"],
        "slots_not_emitted": {
            "SLOT-3": "rule, not record; requires pre-canonical supports that "
                      "P-18 and DECISIONS.md:273-277 forbid citing as canonical; "
                      "the existing manuscript figure script covers it",
            "SLOT-8": "conditional on the trigger; the four conditions are not "
                      "declared families of this reader and no ablation "
                      "quantity is derived (full_production_parent_v2.py:119-146)",
        },
        "written": written,
    }
    manifest["content_sha256"] = schema.content_sha256(manifest)
    (out_dir / "RENDERED_SLOTS.json").write_bytes(
        schema.canonical_bytes(manifest) + b"\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the Stage-2 paper slots from "
                    "STAGE2_INFERENCE.json into a caller-chosen output dir. "
                    "Never writes into project/paper/.")
    parser.add_argument("--inference", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path,
                        help="Output directory. REQUIRED and without a default, "
                             "so no invocation can write into project/paper/.")
    args = parser.parse_args(argv)

    paper = Path("/home/shivansh-srivastava/decisions_os/project/paper").resolve()
    out = args.out.resolve()
    if out == paper or paper in out.parents:
        sys.stderr.write(
            f"refusing to render into the read-only paper directory: {out}\n")
        return 2

    try:
        manifest = render(args.inference, out)
    except Stage2AnalysisError as exc:
        sys.stderr.write(f"render refused: {exc}\n")
        return 1

    print("G9 Stage-2 paper-slot render")
    print("=" * 72)
    print(f"inference     : {args.inference}")
    print(f"out           : {out}")
    print(f"MOCK labelled : {manifest['is_mock']}")
    print(f"emitted       : {', '.join(manifest['slots_emitted'])}")
    print(f"not emitted   : "
          f"{', '.join(sorted(manifest['slots_not_emitted']))}")
    for entry in manifest["written"]:
        print(f"  {entry['slot']:<10} {entry['path']}")
    print(f"manifest      : {out / 'RENDERED_SLOTS.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
