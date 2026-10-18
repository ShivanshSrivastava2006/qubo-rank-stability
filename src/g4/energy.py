"""Canonical FROZEN_MATH_SPEC.md section 5.2 residual-form binary64 energy ledger.

This module is the D015 comparison path. It is not the expanded QUBO matrix,
and it contains no ground-state search, minimum, tie set, T_E, X_E, OPT_f
service, A/B/C classification, grid sweep, experiment, result, or conclusion.

Every written arithmetic step is one rounded binary64 operation. Accumulators
start at +0.0. There is no FMA, reassociation, contraction, library dot
product, pow, math.fsum, or NumPy vectorisation.

Importing this module has no side effects and writes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .instance import Instance
from .parameters import Coefficients


# Scope-locked slack register widths (FROZEN_MATH_SPEC.md section 5.1).
SECTOR_SLACK_BITS = 2
BUDGET_SLACK_BITS = 11
SLACK_AUXILIARY_LENGTH = 4 * SECTOR_SLACK_BITS + BUDGET_SLACK_BITS

# D015 frozen judgements, used only by tau(). Not a classifier.
EPSILON = math.ldexp(1.0, -52)
C_H_PRIMARY = 2048.0


@dataclass(frozen=True)
class PreparedInstance:
    """An instance whose complete frozen schema was validated once."""

    instance: Instance

    def __post_init__(self) -> None:
        _require_instance(self.instance)


@dataclass(frozen=True)
class PreparedCoefficients:
    """A coefficient tuple whose active values were validated once."""

    coefficients: Coefficients

    def __post_init__(self) -> None:
        _require_coefficients(self.coefficients)


@dataclass(frozen=True)
class PreparedDecodedState:
    """Grid-independent §5.2 intermediates for one decoded state."""

    f_value: float
    h_card: float
    card_square: float
    h_sector: tuple[float, ...]
    sector_square: tuple[float, ...]
    h_budget: float
    budget_square: float

    def __post_init__(self) -> None:
        if len(self.h_sector) != 4 or len(self.sector_square) != 4:
            raise ValueError("prepared state must contain four sector residuals and squares")
        for label, value in (
            ("f", self.f_value),
            ("h_card", self.h_card),
            ("card_square", self.card_square),
            ("h_budget", self.h_budget),
            ("budget_square", self.budget_square),
        ):
            _finite(value, f"prepared {label}")
        for j, value in enumerate(self.h_sector):
            _finite(value, f"prepared h_sector[{j}]")
        for j, value in enumerate(self.sector_square):
            _finite(value, f"prepared sector_square[{j}]")


@dataclass(frozen=True)
class PreparedSlackState:
    """Grid-independent §5.2 intermediates for one encoded slack state."""

    decoded: PreparedDecodedState
    sector_slack_square: tuple[float, ...]
    budget_slack_square: float

    def __post_init__(self) -> None:
        if not isinstance(self.decoded, PreparedDecodedState):
            raise TypeError("decoded must be a PreparedDecodedState")
        if len(self.sector_slack_square) != 4:
            raise ValueError("prepared slack state must contain four sector squares")
        for j, value in enumerate(self.sector_slack_square):
            _finite(value, f"prepared sector_slack_square[{j}]")
        _finite(self.budget_slack_square, "prepared budget_slack_square")


def _finite(value: float, label: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"nonfinite {label}: {value!r}")
    return value


def _bit(value: object, label: str) -> float:
    if value not in (0, 1):
        raise ValueError(f"{label} is not a bit: {value!r}")
    return float(value)


def _x_bits(x: tuple[int, ...]) -> tuple[float, ...]:
    if len(x) != 20:
        raise ValueError("x must be a length-20 binary vector")
    return tuple(_bit(bit, f"x[{index}]") for index, bit in enumerate(x))


def _require_instance(instance: Instance) -> None:
    if len(instance.tickers) != 20:
        raise ValueError("instance must contain 20 tickers")
    if len(instance.mu) != 20 or len(instance.sigma) != 20 or len(instance.prices) != 20:
        raise ValueError("instance arrays must have length 20")
    if len(instance.sectors) != 4:
        raise ValueError("instance must contain 4 sectors")
    _finite(instance.kappa_risk, "kappa_risk")
    _finite(float(instance.K), "K")
    _finite(float(instance.C), "C")
    _finite(instance.B, "B")
    for index, value in enumerate(instance.mu):
        _finite(value, f"mu[{index}]")
    for index, row in enumerate(instance.sigma):
        if len(row) != 20:
            raise ValueError(f"Sigma row {index} must have length 20")
        for column, value in enumerate(row):
            _finite(value, f"Sigma[{index},{column}]")
    for index, value in enumerate(instance.prices):
        _finite(value, f"p[{index}]")


def _require_coefficients(coefficients: Coefficients) -> None:
    if not isinstance(coefficients, Coefficients):
        raise TypeError("coefficients must come from parameters.load_coefficients")
    for name in (
        "alpha",
        "sector_slack",
        "budget_slack",
        "sector_linear",
        "sector_quadratic",
        "budget_linear",
        "budget_quadratic",
    ):
        value = getattr(coefficients, name)
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"{name} must be finite and strictly positive")


def _bit_weight(degree: int) -> float:
    """Exactly representable 2^d for slack bit d. Integer shift, not pow."""
    if not isinstance(degree, int) or degree < 0 or degree >= 53:
        raise ValueError(f"slack bit degree {degree!r} is not a representable binary64 power of two")
    return _finite(float(1 << degree), f"2^{degree}")


def _objective_from_bits(instance: Instance, xs: tuple[float, ...]) -> float:
    mu_term = []
    for i in range(20):
        product = _finite(instance.mu[i] * xs[i], f"mu[{i}]*x[{i}]")
        mu_term.append(-product)
    quad_term = []
    for i in range(20):
        for k in range(20):
            sigma_xi = _finite(instance.sigma[i][k] * xs[i], f"sigma_xi[{i},{k}]")
            inner = _finite(sigma_xi * xs[k], f"sigma_xi[{i},{k}]*x[{k}]")
            quad_term.append(_finite(instance.kappa_risk * inner, f"quad_term[{i},{k}]"))
    f_acc = +0.0
    for term in mu_term:
        f_acc = _finite(f_acc + term, "f_acc")
    for term in quad_term:
        f_acc = _finite(f_acc + term, "f_acc")
    return f_acc


def _residuals_from_bits(
    instance: Instance, xs: tuple[float, ...]
) -> tuple[float, tuple[float, ...], float]:
    card_sum = +0.0
    for i in range(20):
        card_sum = _finite(card_sum + xs[i], "card_sum")
    h_card = _finite(card_sum - float(instance.K), "h_card")
    h_sector = []
    for j, members in enumerate(instance.sectors):
        sector_sum = +0.0
        for i in sorted(members):
            sector_sum = _finite(sector_sum + xs[i], f"sector_sum[{j}]")
        h_sector.append(_finite(float(instance.C) - sector_sum, f"h_sector[{j}]"))
    budget_sum = +0.0
    for i in range(20):
        spend = _finite(instance.prices[i] * xs[i], f"p[{i}]*x[{i}]")
        budget_sum = _finite(budget_sum + spend, "budget_sum")
    h_budget = _finite(instance.B - budget_sum, "h_budget")
    return h_card, tuple(h_sector), h_budget


def prepare_instance(instance: Instance) -> PreparedInstance:
    """Validate the full immutable instance once at an execution boundary."""
    return PreparedInstance(instance)


def prepare_coefficients(coefficients: Coefficients) -> PreparedCoefficients:
    """Validate one grid point's active coefficients once."""
    return PreparedCoefficients(coefficients)


def prepare_decoded_state(
    prepared_instance: PreparedInstance, x: tuple[int, ...]
) -> PreparedDecodedState:
    """Compute and retain the grid-independent §5.2 state intermediates."""
    if not isinstance(prepared_instance, PreparedInstance):
        raise TypeError("prepared_instance must come from prepare_instance")
    instance = prepared_instance.instance
    xs = _x_bits(x)
    f_value = _objective_from_bits(instance, xs)
    h_card, h_sector, h_budget = _residuals_from_bits(instance, xs)
    card_square = _finite(h_card * h_card, "card_square")
    sector_square = tuple(
        _finite(residual * residual, f"sector[{j}] quadratic_square")
        for j, residual in enumerate(h_sector)
    )
    budget_square = _finite(h_budget * h_budget, "budget quadratic_square")
    return PreparedDecodedState(
        f_value=f_value,
        h_card=h_card,
        card_square=card_square,
        h_sector=h_sector,
        sector_square=sector_square,
        h_budget=h_budget,
        budget_square=budget_square,
    )


def objective(instance: Instance, x: tuple[int, ...]) -> float:
    """Section 5.2 f transcript: mu_term[1..20] then quad_term[1,1]..quad_term[20,20]."""
    _require_instance(instance)
    return _objective_from_bits(instance, _x_bits(x))


def residuals(instance: Instance, x: tuple[int, ...]) -> tuple[float, tuple[float, ...], float]:
    """Section 5.2 residual transcript: h_card, four h_sector[j], h_budget."""
    _require_instance(instance)
    return _residuals_from_bits(instance, _x_bits(x))


def exact_slack_lift(instance: Instance, x: tuple[int, ...]) -> tuple[int, ...]:
    """C_slack register contents: each auxiliary is the exact residual integer.

    This reconstructs one decoded state's unique exact-minimizer lift. It does
    not search, minimise over a state set, or form a tie set.
    """
    _, h_sector, h_budget = residuals(instance, x)
    bits: list[int] = []
    for j, residual in enumerate(h_sector):
        value = int(residual)
        if float(value) != residual or value < 0 or value >= (1 << SECTOR_SLACK_BITS):
            raise ValueError(
                f"sector[{j}] residual {residual!r} is not exactly representable in the slack register"
            )
        for d in range(SECTOR_SLACK_BITS):
            bits.append((value >> d) & 1)
    value = int(h_budget)
    if float(value) != h_budget or value < 0 or value >= (1 << BUDGET_SLACK_BITS):
        raise ValueError(
            f"budget residual {h_budget!r} is not exactly representable in the slack register"
        )
    for d in range(BUDGET_SLACK_BITS):
        bits.append((value >> d) & 1)
    return tuple(bits)


def _slack_register(y_bits: tuple[int, ...] | list[int], label: str) -> float:
    s_acc = +0.0
    for d, bit in enumerate(y_bits):
        y_d = _bit(bit, f"{label} y[{d}]")
        term = _finite(_bit_weight(d) * y_d, f"{label} 2^{d}*y[{d}]")
        s_acc = _finite(s_acc + term, f"{label} S_acc")
    return s_acc


def prepare_slack_state(
    decoded: PreparedDecodedState, auxiliary: tuple[int, ...]
) -> PreparedSlackState:
    """Prepare the grid-independent slack-square intermediates for one raw state."""
    if not isinstance(decoded, PreparedDecodedState):
        raise TypeError("decoded must come from prepare_decoded_state")
    if len(auxiliary) != SLACK_AUXILIARY_LENGTH:
        raise ValueError("slack auxiliary has the wrong length")
    offset = 0
    sector_slack_square = []
    for j in range(4):
        y_bits = auxiliary[offset:offset + SECTOR_SLACK_BITS]
        offset += SECTOR_SLACK_BITS
        s_acc = _slack_register(y_bits, f"sector[{j}]")
        slack_delta = _finite(decoded.h_sector[j] - s_acc, f"sector[{j}] slack_delta")
        sector_slack_square.append(
            _finite(slack_delta * slack_delta, f"sector[{j}] slack_square")
        )
    y_bits = auxiliary[offset:offset + BUDGET_SLACK_BITS]
    if offset + BUDGET_SLACK_BITS != len(auxiliary):
        raise ValueError("slack auxiliary layout mismatch")
    s_acc = _slack_register(y_bits, "budget")
    slack_delta = _finite(decoded.h_budget - s_acc, "budget slack_delta")
    budget_slack_square = _finite(slack_delta * slack_delta, "budget slack_square")
    return PreparedSlackState(decoded, tuple(sector_slack_square), budget_slack_square)


def slack_energy_prepared(
    state: PreparedSlackState, coefficients: PreparedCoefficients
) -> float:
    """Canonical slack energy from already validated §5.2 intermediates."""
    if not isinstance(state, PreparedSlackState):
        raise TypeError("state must come from prepare_slack_state")
    if not isinstance(coefficients, PreparedCoefficients):
        raise TypeError("coefficients must come from prepare_coefficients")
    values = coefficients.coefficients
    p_card = _finite(values.alpha * state.decoded.card_square, "P_card")
    h_acc = state.decoded.f_value
    h_acc = _finite(h_acc + p_card, "H_acc")
    for j in range(4):
        penalty = _finite(
            values.sector_slack * state.sector_slack_square[j], f"P_sector[{j}]"
        )
        h_acc = _finite(h_acc + penalty, "H_acc")
    p_budget = _finite(values.budget_slack * state.budget_slack_square, "P_budget")
    return _finite(h_acc + p_budget, "H_E")


def unbalanced_energy_prepared(
    state: PreparedDecodedState, coefficients: PreparedCoefficients
) -> float:
    """Canonical unbalanced energy from already validated §5.2 intermediates."""
    if not isinstance(state, PreparedDecodedState):
        raise TypeError("state must come from prepare_decoded_state")
    if not isinstance(coefficients, PreparedCoefficients):
        raise TypeError("coefficients must come from prepare_coefficients")
    values = coefficients.coefficients
    p_card = _finite(values.alpha * state.card_square, "P_card")
    h_acc = state.f_value
    h_acc = _finite(h_acc + p_card, "H_acc")
    for j in range(4):
        residual = state.h_sector[j]
        linear_product = _finite(values.sector_linear * residual, f"sector[{j}] linear_product")
        quadratic_product = _finite(
            values.sector_quadratic * state.sector_square[j], f"sector[{j}] quadratic_product"
        )
        penalty = _finite((-linear_product) + quadratic_product, f"P_sector[{j}]")
        h_acc = _finite(h_acc + penalty, "H_acc")
    linear_product = _finite(values.budget_linear * state.h_budget, "budget linear_product")
    quadratic_product = _finite(
        values.budget_quadratic * state.budget_square, "budget quadratic_product"
    )
    p_budget = _finite((-linear_product) + quadratic_product, "P_budget")
    return _finite(h_acc + p_budget, "H_E")


def slack_energy(instance: Instance, x: tuple[int, ...], auxiliary: tuple[int, ...],
                 coefficients: Coefficients) -> float:
    """Canonical H_slack = f + P_card + sum_j P_slack,j, section 5.2 order."""
    _require_instance(instance)
    _require_coefficients(coefficients)
    if len(auxiliary) != SLACK_AUXILIARY_LENGTH:
        raise ValueError("slack auxiliary has the wrong length")
    f_value = objective(instance, x)
    h_card, h_sector, h_budget = residuals(instance, x)
    card_square = _finite(h_card * h_card, "card_square")
    p_card = _finite(coefficients.alpha * card_square, "P_card")
    h_acc = f_value
    h_acc = _finite(h_acc + p_card, "H_acc")
    offset = 0
    for j in range(4):
        y_bits = auxiliary[offset:offset + SECTOR_SLACK_BITS]
        offset += SECTOR_SLACK_BITS
        s_acc = _slack_register(y_bits, f"sector[{j}]")
        slack_delta = _finite(h_sector[j] - s_acc, f"sector[{j}] slack_delta")
        slack_square = _finite(slack_delta * slack_delta, f"sector[{j}] slack_square")
        penalty = _finite(coefficients.sector_slack * slack_square, f"P_sector[{j}]")
        h_acc = _finite(h_acc + penalty, "H_acc")
    y_bits = auxiliary[offset:offset + BUDGET_SLACK_BITS]
    if offset + BUDGET_SLACK_BITS != len(auxiliary):
        raise ValueError("slack auxiliary layout mismatch")
    s_acc = _slack_register(y_bits, "budget")
    slack_delta = _finite(h_budget - s_acc, "budget slack_delta")
    slack_square = _finite(slack_delta * slack_delta, "budget slack_square")
    p_budget = _finite(coefficients.budget_slack * slack_square, "P_budget")
    return _finite(h_acc + p_budget, "H_E")


def unbalanced_energy(instance: Instance, x: tuple[int, ...],
                      coefficients: Coefficients) -> float:
    """Canonical H_unbalanced = f + P_card + sum_j zeta_j, section 5.2 order."""
    _require_instance(instance)
    _require_coefficients(coefficients)
    f_value = objective(instance, x)
    h_card, h_sector, h_budget = residuals(instance, x)
    card_square = _finite(h_card * h_card, "card_square")
    p_card = _finite(coefficients.alpha * card_square, "P_card")
    h_acc = f_value
    h_acc = _finite(h_acc + p_card, "H_acc")
    for j in range(4):
        residual = h_sector[j]
        linear_product = _finite(coefficients.sector_linear * residual, f"sector[{j}] linear_product")
        quadratic_square = _finite(residual * residual, f"sector[{j}] quadratic_square")
        quadratic_product = _finite(
            coefficients.sector_quadratic * quadratic_square, f"sector[{j}] quadratic_product"
        )
        penalty = _finite((-linear_product) + quadratic_product, f"P_sector[{j}]")
        h_acc = _finite(h_acc + penalty, "H_acc")
    residual = h_budget
    linear_product = _finite(coefficients.budget_linear * residual, "budget linear_product")
    quadratic_square = _finite(residual * residual, "budget quadratic_square")
    quadratic_product = _finite(
        coefficients.budget_quadratic * quadratic_square, "budget quadratic_product"
    )
    p_budget = _finite((-linear_product) + quadratic_product, "P_budget")
    return _finite(h_acc + p_budget, "H_E")


def tau(y: float, y_prime: float, lambda_ref: float, c: float) -> float:
    """D015 binary64 scale for a pair of finite energies. Not a tie test.

    gap = abs(fl(y - y')); m = max(|y|, |y'|); scale = fl(Lambda_ref + m);
    tau = fl((c * epsilon) * scale). Fails closed on nonfinite inputs,
    nonpositive Lambda_ref, or nonpositive c.
    """
    if not math.isfinite(lambda_ref) or lambda_ref <= 0.0:
        raise ValueError("Lambda_ref must be finite and strictly positive")
    if not math.isfinite(c) or c <= 0.0:
        raise ValueError("tolerance multiplier c must be finite and strictly positive")
    y_value = _finite(y, "y")
    y_prime_value = _finite(y_prime, "y'")
    difference = _finite(y_value - y_prime_value, "y-y'")
    gap = abs(difference)
    m = max(abs(y_value), abs(y_prime_value))
    scale = _finite(lambda_ref + m, "scale")
    return _finite((c * EPSILON) * scale, "tau")
