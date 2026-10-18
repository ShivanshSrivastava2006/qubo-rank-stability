#!/usr/bin/env python3
"""Bounded W3 structural verification for the frozen Gate-1 math package.

This script checks only literal declaration presence and a few bounded forbidden
patterns in the frozen text. It is not a semantic-consistency, algebraic-proof,
or implementation verifier. It deliberately does not claim to verify canonical
data, numeric ADNYE values, coefficient bit generation, QUBO code, solver
behavior, or any result (G2+ work).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "research/00_specifications/FROZEN_MATH_SPEC.md"
CHARTER = ROOT / "research/00_specifications/GATE_1_CHARTER.md"
DECISIONS = ROOT / "research/decisions/DECISIONS.md"


def require(text: str, fragment: str, label: str, failures: list[str]) -> None:
    if fragment not in text:
        failures.append(f"{label}: missing required text {fragment!r}")


def forbid(text: str, pattern: str, label: str, failures: list[str]) -> None:
    if re.search(pattern, text, flags=re.MULTILINE):
        failures.append(f"{label}: prohibited current-spec pattern {pattern!r}")


def main() -> int:
    failures: list[str] = []
    for path in (SPEC, CHARTER, DECISIONS):
        if not path.is_file():
            failures.append(f"required source absent: {path.relative_to(ROOT)}")
    if failures:
        print("FAIL: verify_gate1_math")
        print("\n".join(f"- {item}" for item in failures))
        return 1

    spec = SPEC.read_text(encoding="utf-8")
    charter = CHARTER.read_text(encoding="utf-8")
    decisions = DECISIONS.read_text(encoding="utf-8")

    require(spec, "FROZEN — AUTHORITATIVE CONSOLIDATION UNDER W0b", "authority", failures)
    require(spec, "W2 operational determinization in §4.3", "W2 provenance", failures)
    require(charter, "FROZEN — AUTHORITATIVE GATE-1 CHARTER", "charter authority", failures)
    require(decisions, "## Process Approval — W0b, Gate-1 Charter Freeze", "W0b record", failures)

    for decision in ("D001", "D002", "D004", "D005", "D006", "D007", "D008", "D009",
                     "D010", "D011", "D012", "D013", "D014", "D015", "D016"):
        require(spec, decision, f"decision carry-forward {decision}", failures)
        require(decisions, f"{decision}", f"decision record {decision}", failures)

    # M1: every primary formula family has a table declaration with a source.
    for symbol in (
        "`kappa_risk`", "`Lambda_ref`", "`Delta_full`", "`rho_box`", "`alpha`",
        "`lambda_S,j`", "`lambda_1,j`", "`lambda_2,j`", "`H_E(z;lambda)`",
        "`T_E`", "`X_E`", "`epsilon`", "`c_H,c_f`", "`OPT_f(x)`", "`A_x,B_x,C_x`",
    ):
        require(spec, symbol, f"M1 symbol {symbol}", failures)

    # Declaration presence only: objective/coefficient/transcription statements.
    for formula in (
        "kappa_risk * x^T Sigma x",
        "alpha(s_card) = s_card * Lambda_ref / v_card^2",
        "lambda_S,j = s_j * Lambda_ref / v_j^2",
        "lambda_1,j = Lambda_ref * a_r(s_j) / v_j",
        "lambda_2,j = Lambda_ref * a_r(s_j)^2 / (2v_j^2)",
        "s(ell) = 10^(q_min + ell/P)",
        "W2 operational determinization under W0b — not a decision-record rule.",
        "The primary binary64 coordinate is the correctly rounded, round-to-nearest",
        "sqrt_RN_even(t2)",
    ):
        require(spec, formula, "M2 coefficient/objective map", failures)

    # Approved D006 numerical path; the direct subtractive expression is only
    # permitted when explicitly described as mathematical, not evaluation.
    require(spec, "a_r(s) = 2s / (sqrt(r^2 + 2s) + r)", "D006 stable evaluation", failures)
    require(spec, "prohibited as its small-positive-`s` numerical evaluation", "D006 prohibition", failures)

    # D008/D010/D012 and D014 boundaries.
    for fragment in (
        "Lambda_ref = max_{x in F} f(x) - min_{x in F} f(x)",
        "Delta_full = max_{x in {0,1}^20} f(x) - min_{x in {0,1}^20} f(x)",
        "s_max = 10^(ceil(log10(rho_box)) + 1)",
        "s_min = 10^(floor(log10(rho_box)) - 4)",
        "P=10` log **intervals** per decade",
        "ADNYE-001", "ADNYE-002", "admitted, not executed",
    ):
        require(spec, fragment, "approved deferred/grid rule", failures)

    # M4/M5 declaration only: class-B enforcement is intentionally not claimed.
    require(spec, "share **no** penalty helper", "M4 declaration", failures)
    require(spec, "It receives no\nenergy and no encoding identity", "M5 interface", failures)
    require(spec, "Class B is only M4 and M5", "Class B boundary", failures)

    # D015 canonical ledger, separate comparators and provenance.
    for fragment in (
        "There is no\nFMA, contraction, reassociation",
        "All state-independent constants implied by those formulas belong to the\ncanonical unshifted ledger",
        "gap   = abs(fl(y-y'))",
        "tau   = fl((c*epsilon)*scale)",
        "T_E = {z in C_E", "OPT_f(x) iff x in F",
        "ADNYE-001 digest and separate D015/D016 approved-decision hashes",
        "numerical-rule conflict that stops acceptance",
    ):
        require(spec, fragment, "D015 comparator/provenance rule", failures)

    # M6 declaration presence only: arbitrary-size, decoded-only partition text.
    for fragment in (
        "For every nonempty finite `X_E`", "if exists x in X_E with C_x: C",
        "else if all x in X_E have A_x: A", "else: B",
        "denominator `|X_E|`", "never supply partial credit to the primary A-rate",
    ):
        require(spec, fragment, "M6/D016 partition", failures)

    # D013 must consume the primary classification only.
    require(spec, "the trigger uses\nprimary classification only", "D013 primary-only trigger", failures)

    # The frozen current specification cannot contain a live unresolved marker
    # or a bare historical `rho` assignment.
    forbid(spec, r"\b(?:TODO|TBD|UNRESOLVED)\b", "no live open marker", failures)
    forbid(spec, r"(?m)^\s*rho\s*=", "no bare rho assignment", failures)
    forbid(spec, r"(?m)^\s*sensitivity.*=.*primary", "no sensitivity-as-primary rewrite", failures)

    # Unit-table declaration presence only; this is not an exponent proof.
    for fragment in (
        "| `f(x)` | original objective | `E`", "| `alpha` | cardinality penalty coefficient | `E/R^2`",
        "| `lambda_S,j` | slack inequality coefficient | `E/R^2`",
        "| `lambda_1,j` | unbalanced linear coefficient | `E/R`",
        "| `lambda_2,j` | unbalanced quadratic coefficient | `E/R^2`",
        "| `H_E(z;lambda)` | canonical unshifted encoded energy | `E`",
        "| `s_j` | `s_sector` for sector family `j`; `s_budget` for budget",
        "| `v_sector` | smallest positive native sector violation, exactly `1`",
    ):
        require(spec, fragment, "M2 unit-table declaration", failures)

    if failures:
        print("FAIL: verify_gate1_math")
        print("\n".join(f"- {item}" for item in failures))
        return 1
    print("PASS: verify_gate1_math (bounded declaration-presence checks only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
