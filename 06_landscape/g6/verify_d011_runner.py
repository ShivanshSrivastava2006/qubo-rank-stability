#!/usr/bin/env python3
"""Fixture-only conformance checks for the additive D011 companion runner."""

from __future__ import annotations

import ast
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.g4.classification import DecodedClassifier, OriginalObjectiveService
from src.g4.energy import prepare_coefficients, unbalanced_energy_prepared
from src.g4.instance import Instance
from src.g4.parameters import Coefficients
from src.g5.certify import certify_prepared_domain
from src.g5.domains import prepare_fixture_domains
from src.g6.d011_runner import (
    AXIS_COUNT,
    CH_VALUES,
    D011Error,
    D011Runner,
    _coefficient_at,
    _key,
    _load_d011_ledger,
    certify_prepared_domain_multi_ch,
    d011_tasks,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise D011Error(message)


def _fixture_instance() -> Instance:
    tickers = tuple(f"T{index:02d}" for index in range(20))
    sectors = tuple(tuple(range(start, start + 5)) for start in range(0, 20, 5))
    return Instance(
        tickers=tickers,
        sectors=sectors,
        mu=(0.0,) * 20,
        sigma=tuple((0.0,) * 20 for _ in range(20)),
        prices=(0.0,) * 20,
        kappa_risk=0.0,
        K=0,
        C=0,
        B=0.0,
    )


def main() -> int:
    try:
        ledger, manifest = _load_d011_ledger()
        _require(len(d011_tasks()) == AXIS_COUNT * AXIS_COUNT == 169, "D011 task population drift")
        _require(len({task for task in d011_tasks()}) == 169, "D011 task duplication")
        _require(_key(ledger, 6, 6, 6)["s_card_hex"] == "0x1.999999999999ap-4",
                 "D011 primary-row coordinate drift")
        coefficients = _coefficient_at(ledger, 6, 6, 6)
        _require(coefficients.sector_slack == coefficients.sector_quadratic
                 and coefficients.budget_slack == coefficients.budget_quadratic,
                 "D011 curvature-match lambda_2 mapping drift")
        plan = D011Runner(ROOT / "research/g6/.fixture-d011-output").plan()
        _require(plan["shards"] == 169 and plan["coordinates"] == 2197
                 and plan["ledger_content_sha256"] == ledger["content_sha256"]
                 and plan["ledger_manifest_content_sha256"] == manifest["content_sha256"],
                 "D011 plan binding drift")

        instance = _fixture_instance()
        x_zero, x_one = (0,) * 20, (1,) * 20
        y_zero = (0,) * 19
        domains = prepare_fixture_domains(instance, (x_zero, x_one), ((x_zero, y_zero), (x_one, y_zero)))
        fixture_coefficients = Coefficients(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
        prepared = prepare_coefficients(fixture_coefficients)
        classifiers = {
            value: DecodedClassifier(OriginalObjectiveService(lambda _x: 0.0, 1.0, float(value)), lambda _x: True)
            for value in (1024, 2048, 4096)
        }
        multi = certify_prepared_domain_multi_ch(
            domains.unbalanced,
            lambda state: unbalanced_energy_prepared(state, prepared),
            1.0,
            0.0,
            lambda x: x,
            classifiers,
        )
        for c_h in CH_VALUES:
            direct = certify_prepared_domain(
                domains.unbalanced,
                lambda state: unbalanced_energy_prepared(state, prepared),
                1.0,
                0.0,
                lambda x: x,
                classifiers[2048],
                float(c_h),
            )
            _require(multi[(c_h, 2048)] == direct, f"multi-c_H result differs at c_H={c_h}")
        near_tie_gap = float(3000.0 * math.ldexp(1.0, -52))
        near_tie = certify_prepared_domain_multi_ch(
            domains.unbalanced,
            lambda state: 0.0 if state == domains.unbalanced[0] else near_tie_gap,
            1.0,
            0.0,
            lambda x: x,
            classifiers,
        )
        _require(len(near_tie[(1024, 2048)][1]) == 1
                 and len(near_tie[(2048, 2048)][1]) == 1
                 and len(near_tie[(4096, 2048)][1]) == 2,
                 "near-tie fixture does not distinguish D015 c_H thresholds")
        _require(set(multi) == {(2048, 2048), (1024, 2048), (4096, 2048), (2048, 1024), (2048, 4096)},
                 "D011 D015 population drift")
        tree = ast.parse((ROOT / "src/g6/d011_runner.py").read_text(encoding="utf-8"))
        _require(not any(isinstance(node, ast.Assert) for node in ast.walk(tree)),
                 "D011 runner must not rely on assert")
        print("PASS D011 runner fixtures")
        return 0
    except D011Error as exc:
        print(f"FAIL D011 runner fixtures: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
