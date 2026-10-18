"""Amortised Gate-5 certification runner boundaries.

Domain construction and state preparation occur once outside the coefficient
loop. Each grid point validates its coefficients once, evaluates the accepted
residual-form prepared energies, and reconstructs raw states only through
``certify_prepared_domain`` for members of the encoded tie set.

This module defines services only. Importing it performs no certification.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.g4.classification import DecodedClassifier
from src.g4.energy import (
    prepare_coefficients,
    slack_energy_prepared,
    unbalanced_energy_prepared,
)
from src.g4.instance import Instance
from src.g4.parameters import Coefficients
from src.g5.certify import certify_prepared_domain
from src.g5.domains import (
    BinaryDomain,
    PreparedDomainPair,
    SlackDomainCache,
    prepare_active_domains,
    prepare_fixture_domains,
)


@dataclass(frozen=True)
class GridCertification:
    """The two encoded certifications for one supplied coefficient point."""

    coefficients: Coefficients
    unbalanced: tuple
    slack: tuple


def certify_prepared_grid(
    domains: PreparedDomainPair,
    coefficient_points: Iterable[Coefficients],
    lambda_ref: float,
    f_star: float,
    classifier: DecodedClassifier,
) -> tuple[GridCertification, ...]:
    """Certify supplied points without rebuilding or re-preparing either domain."""
    if not isinstance(domains, PreparedDomainPair):
        raise TypeError("domains must come from a paired preparation service")
    results = []
    for coefficients in coefficient_points:
        prepared_coefficients = prepare_coefficients(coefficients)
        unbalanced = certify_prepared_domain(
            domain=domains.unbalanced,
            energy_func=lambda state, values=prepared_coefficients: unbalanced_energy_prepared(
                state, values
            ),
            lambda_ref=lambda_ref,
            f_star=f_star,
            decode_func=lambda x: x,
            classifier=classifier,
        )
        slack = certify_prepared_domain(
            domain=domains.slack,
            energy_func=lambda state, values=prepared_coefficients: slack_energy_prepared(
                state, values
            ),
            lambda_ref=lambda_ref,
            f_star=f_star,
            decode_func=lambda state: state[0],
            classifier=classifier,
        )
        results.append(GridCertification(coefficients, unbalanced, slack))
    if not results:
        raise ValueError("coefficient grid must be nonempty")
    return tuple(results)


def prepare_and_certify_active_grid(
    instance: Instance,
    slack_domain: SlackDomainCache,
    coefficient_points: Iterable[Coefficients],
    lambda_ref: float,
    f_star: float,
    classifier: DecodedClassifier,
) -> tuple[GridCertification, ...]:
    """Full active-CSB service; callers remain responsible for grid construction."""
    domains = prepare_active_domains(instance, slack_domain)
    return certify_prepared_grid(
        domains, coefficient_points, lambda_ref, f_star, classifier
    )


def run_amortisation_contract(*, grid_points: int, fixture) -> tuple[GridCertification, ...]:
    """Run only the injected bounded acceptance fixture used by review tooling."""
    if not getattr(fixture, "is_contract_fixture", False):
        raise TypeError("an explicit isolated amortisation contract fixture is required")
    if not isinstance(grid_points, int) or grid_points not in (1, 4):
        raise ValueError("contract grid_points must be exactly 1 or 4")
    if fixture.expected_D != 16 or fixture.expected_L != 16:
        raise ValueError("contract fixture must contain exactly 16 states per encoding")
    if fixture.active_encodings != ("slack", "unbalanced"):
        raise ValueError("contract fixture must exercise both encodings")
    if len(fixture.coefficients) < grid_points:
        raise ValueError("contract fixture has too few coefficient points")

    # Construct exactly one compact binary-domain service and bind the supplied
    # toy states to its first sixteen positions. The full primary domain is
    # never iterated by this contract path.
    binary_domain = BinaryDomain(len(fixture.instance.tickers))
    expected_raw = tuple(binary_domain[index] for index in range(fixture.expected_D))
    if fixture.raw_domain_decoded != expected_raw:
        raise ValueError("contract decoded states do not match binary-domain ordering")

    domains = prepare_fixture_domains(
        fixture.instance,
        fixture.raw_domain_decoded,
        fixture.raw_domain_slack,
    )
    return certify_prepared_grid(
        domains=domains,
        coefficient_points=fixture.coefficients[:grid_points],
        lambda_ref=fixture.lambda_ref,
        f_star=fixture.f_star,
        classifier=fixture.classifier,
    )
