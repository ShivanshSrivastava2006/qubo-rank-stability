#!/usr/bin/env python3
"""Independently replay ADNYE-001 from immutable G2 inputs.

This is an audit-only program.  It first requires the D014 validator to accept
the official record, then uses the frozen scalar binary64 objective transcript
to enumerate the predicate-defined feasible set and the complete binary space.
It writes no G3 artifact.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable

from validate_adnye_output import ContractError, ONE_JSON, preflight_one


REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL = REPO_ROOT / "research/canonical/stage1_instance.json"
EPSILON = 2.0 ** -52


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def load_instance() -> tuple[list[float], list[list[float]], list[int], list[list[int]], int, int, int]:
    raw: dict[str, Any] = json.loads(CANONICAL.read_text(encoding="utf-8"))
    order = raw["universe"]["canonical_order"]
    require(type(order) is list and len(order) == 20, "canonical universe is not the required 20-ticker list")
    mu = [float(raw["mu_by_ticker"][ticker]) for ticker in order]
    sigma = [[float(raw["Sigma_by_ticker"][i][j]) for j in order] for i in order]
    prices = [int(raw["p_by_ticker"][ticker]) for ticker in order]
    labels = raw["universe"]["sector_labels"]
    sector_of = raw["universe"]["sector_of_ticker"]
    sectors = [[index for index, ticker in enumerate(order) if sector_of[ticker] == label] for label in labels]
    require(len(sectors) == 4 and all(len(sector) == 5 for sector in sectors), "canonical sectors are not 4 x 5")
    require(raw["kappa_risk"]["value"] == 1.0, "D007 kappa_risk is not exactly 1.0")
    return mu, sigma, prices, sectors, int(raw["K"]), int(raw["C"]), int(raw["B"])


def ledger_objective(bits: tuple[int, ...], mu: list[float], sigma: list[list[float]]) -> float:
    """The frozen §5.2 f transcript: no dot product, FMA, or reassociation."""
    accumulator = 0.0
    for i in range(20):
        accumulator = accumulator + (-(mu[i] * float(bits[i])))
    for i in range(20):
        for k in range(20):
            sigma_xi = sigma[i][k] * float(bits[i])
            quad_term = 1.0 * (sigma_xi * float(bits[k]))
            accumulator = accumulator + quad_term
    require(math.isfinite(accumulator), "non-finite frozen f transcript")
    return accumulator


def is_feasible(bits: tuple[int, ...], prices: list[int], sectors: list[list[int]], k: int, cap: int, budget: int) -> bool:
    """Independent hard predicate; deliberately does not use residual helpers."""
    return (
        sum(bits) == k
        and all(sum(bits[index] for index in sector) <= cap for sector in sectors)
        and sum(price * bit for price, bit in zip(prices, bits)) <= budget
    )


def bits_from_mask(mask: int) -> tuple[int, ...]:
    return tuple((mask >> index) & 1 for index in range(20))


def population_std(values: Iterable[float]) -> float:
    values = list(values)
    require(bool(values), "cannot compute standard deviation of empty population")
    mean = math.fsum(values) / len(values)
    return math.sqrt(math.fsum((value - mean) ** 2 for value in values) / len(values))


def one_bits(indices: tuple[int, ...]) -> tuple[int, ...]:
    bits = [0] * 20
    for index in indices:
        bits[index] = 1
    return tuple(bits)


def enumerate_statistics() -> dict[str, float | int]:
    mu, sigma, prices, sectors, k, cap, budget = load_instance()
    cardinality_values: list[float] = []
    feasible_values: list[float] = []
    f_star = math.inf
    minimizer_count = 0

    for selected in itertools.combinations(range(20), k):
        bits = one_bits(selected)
        value = ledger_objective(bits, mu, sigma)
        cardinality_values.append(value)
        if is_feasible(bits, prices, sectors, k, cap, budget):
            feasible_values.append(value)
            if value < f_star:
                f_star, minimizer_count = value, 1
            elif value == f_star:
                minimizer_count += 1

    require(bool(feasible_values), "D008 feasible population is empty")
    full_min = math.inf
    full_max = -math.inf
    for mask in range(1 << 20):
        value = ledger_objective(bits_from_mask(mask), mu, sigma)
        full_min = min(full_min, value)
        full_max = max(full_max, value)

    return {
        "f_star": f_star,
        "x_star_count": minimizer_count,
        "F_count": len(feasible_values),
        "cardinality_count": len(cardinality_values),
        "range_F": max(feasible_values) - min(feasible_values),
        "std_F": population_std(feasible_values),
        "range_cardinality": max(cardinality_values) - min(cardinality_values),
        "std_cardinality": population_std(cardinality_values),
        "range_full": full_max - full_min,
    }


def within_32_ulps(actual: float, expected: float) -> bool:
    if actual == expected:
        return True
    if not (math.isfinite(actual) and math.isfinite(expected)):
        return False
    return abs(actual - expected) <= 32 * max(math.ulp(actual), math.ulp(expected), EPSILON * EPSILON)


def audit(root: Path) -> dict[str, Any]:
    preflight_one(root)
    record = json.loads((root / ONE_JSON).read_text(encoding="utf-8"))
    calculated = enumerate_statistics()
    candidate_values = record["transparency_candidates"]
    actual = {
        "range_F": float(record["value"]),
        "delta_full": float(record["delta_full"]),
        "std_F": float(candidate_values[1]["value"]),
        "range_cardinality": float(candidate_values[2]["value"]),
        "std_cardinality": float(candidate_values[3]["value"]),
        "range_full": float(candidate_values[4]["value"]),
    }
    expected = {
        "range_F": float(calculated["range_F"]),
        "delta_full": float(calculated["range_full"]),
        "std_F": float(calculated["std_F"]),
        "range_cardinality": float(calculated["range_cardinality"]),
        "std_cardinality": float(calculated["std_cardinality"]),
        "range_full": float(calculated["range_full"]),
    }
    for name in expected:
        require(within_32_ulps(actual[name], expected[name]),
                f"official ADNYE-001 {name} differs from independent replay: {actual[name]!r} vs {expected[name]!r}")

    print("PASS: independent ADNYE-001 pre-acceptance replay agrees within 32 ULPs")
    print(f"  F_count={calculated['F_count']}; cardinality_count={calculated['cardinality_count']}")
    print(f"  f_star={calculated['f_star']!r}; X_star raw-minimum count={calculated['x_star_count']}")
    for name in ("range_F", "std_F", "range_cardinality", "std_cardinality", "range_full"):
        print(f"  {name}={expected[name]!r}")
    return {"calculated": calculated, "official": actual}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="official research/adnye directory")
    parser.add_argument("--report", type=Path, help="write one new JSON replay report after computation")
    args = parser.parse_args()
    try:
        if args.report is not None and args.report.exists():
            raise ContractError(f"refusing to overwrite existing audit report: {args.report}")
        result = audit(args.root)
    except (ContractError, OSError, ValueError, json.JSONDecodeError) as exc:
        if args.report is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps({"status": "FAILED", "error": str(exc)}, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print(f"AUDIT FAILED: {exc}", file=sys.stderr)
        return 1
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps({"status": "REPLAY_CLEAN_NOT_ACCEPTED", **result}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
