"""Bounded producer checks for the amortised Gate-5 runner.

Only sixteen explicitly supplied toy states per encoding are certified. No
primary instance, primary grid point, reported result, or Gate-6 work occurs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.g4.classification import DecodedClassifier, OriginalObjectiveService
from src.g4.energy import objective, residuals, slack_energy, unbalanced_energy
from src.g4.instance import Instance
from src.g4.parameters import Coefficients
from src.g5.certify import certify_domain
from src.g5.domains import BinaryDomain, prepare_fixture_domains
from src.g5.runner import certify_prepared_grid, run_amortisation_contract


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_failure(callable_, label: str) -> None:
    try:
        callable_()
    except (TypeError, ValueError):
        return
    raise AssertionError(f"runner fail-closed probe accepted: {label}")


def _instance() -> Instance:
    return Instance(
        tickers=tuple(f"T{i}" for i in range(20)),
        mu=tuple(0.01 * (i + 1) for i in range(20)),
        sigma=tuple(
            tuple(0.001 if i == j else 0.0001 for j in range(20))
            for i in range(20)
        ),
        prices=tuple(10.0 + i for i in range(20)),
        sectors=(
            (0, 1, 2, 3, 4),
            (5, 6, 7, 8, 9),
            (10, 11, 12, 13, 14),
            (15, 16, 17, 18, 19),
        ),
        kappa_risk=1.0,
        K=6,
        C=2,
        B=100.0,
    )


def _coefficients(offset: float) -> Coefficients:
    value = 1.0 + offset
    return Coefficients(value, value, value, value, value, value, value)


def _classifier(instance: Instance) -> DecodedClassifier:
    service = OriginalObjectiveService(
        objective=lambda x: objective(instance, x), lambda_ref=10.0
    )

    def feasible(x):
        h_card, h_sector, h_budget = residuals(instance, x)
        return h_card == 0.0 and all(value >= 0.0 for value in h_sector) and h_budget >= 0.0

    return DecodedClassifier(service, feasible)


@dataclass(frozen=True)
class Fixture:
    instance: Instance
    coefficients: tuple[Coefficients, ...]
    raw_domain_decoded: tuple
    raw_domain_slack: tuple
    f_star: float
    lambda_ref: float
    classifier: DecodedClassifier
    expected_D: int = 16
    expected_L: int = 16
    active_encodings: tuple[str, ...] = ("slack", "unbalanced")
    is_contract_fixture: bool = True


def main() -> int:
    instance = _instance()
    binary = BinaryDomain(20)
    raw_decoded = tuple(binary[index] for index in range(16))
    auxiliary = (0,) * 19
    raw_slack = tuple((x, auxiliary) for x in raw_decoded)
    coefficients = tuple(_coefficients(0.1 * index) for index in range(4))
    classifier = _classifier(instance)

    domains = prepare_fixture_domains(instance, raw_decoded, raw_slack)
    for decoded, slack in zip(domains.unbalanced.states, domains.slack.states, strict=True):
        require(slack.decoded is decoded, "runner duplicated decoded preparation")

    produced = certify_prepared_grid(
        domains, coefficients, 10.0, -0.5, classifier
    )
    require(len(produced) == 4, "runner did not return one record per coefficient point")
    for record, values in zip(produced, coefficients, strict=True):
        expected_unbalanced = certify_domain(
            lambda: iter(raw_decoded),
            lambda x, values=values: unbalanced_energy(instance, x, values),
            10.0,
            -0.5,
            lambda x: x,
            classifier,
        )
        expected_slack = certify_domain(
            lambda: iter(raw_slack),
            lambda state, values=values: slack_energy(instance, state[0], state[1], values),
            10.0,
            -0.5,
            lambda state: state[0],
            classifier,
        )
        require(record.unbalanced == expected_unbalanced, "unbalanced runner result differs from legacy oracle")
        require(record.slack == expected_slack, "slack runner result differs from legacy oracle")

    fixture = Fixture(
        instance,
        coefficients,
        raw_decoded,
        raw_slack,
        -0.5,
        10.0,
        classifier,
    )
    contract = run_amortisation_contract(grid_points=4, fixture=fixture)
    require(contract == produced, "fixture-gated runner differs from direct prepared runner")
    expect_failure(
        lambda: run_amortisation_contract(grid_points=4, fixture=object()),
        "missing isolated fixture marker",
    )
    expect_failure(
        lambda: run_amortisation_contract(grid_points=2, fixture=fixture),
        "unauthorized contract grid size",
    )
    print("PASS Gate-5 amortised runner on isolated 16-state fixtures; no primary execution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
