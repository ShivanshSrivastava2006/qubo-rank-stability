"""WP6 STEP 2 -- exact ``+0.0`` inactive-family evaluator (Python reference).

Non-scientific. Building and synthetic testing only. This module draws no
candidate, reads no instance artifact, computes no ground truth, writes no file,
and contacts no device or network. It fires no D013 trigger, authorises no
ablation run, no Kaggle push and no launch. Gate-9 section B remains **OPEN**.

Binding authority actually read, in order
-----------------------------------------
* ``research/decisions/GATE_9_D013_INACTIVE_EVALUATOR_SPEC_OWNER_DECISION.md``
  -- GAP-1 (per-condition ``F_q`` / ``f*_q``), GAP-1b (empty ``F_q`` is a hard
  stop, nothing written), GAP-2 (``|T_E|`` as an exact integer together with its
  factors ``(base, w)``, computed arithmetically, never by enumerating 2^39).
* ``research/g9/GATE_9_WP6_D013_SPEC_GAP_DRAFT.md`` -- every FIXED item, with its
  quotes: the four ``F_q`` predicates and the active/inactive map; inactive
  penalties identically zero and omitted from the grid; the raw register
  RETAINED with a ``+0.0`` coefficient; the positive-zero and fixed
  accumulation-order requirements; the additive-only requirement.
* ``research/decisions/DECISIONS.md`` D013, D015, D016.
* ``research/decisions/U14_DECISION_MEMO.md`` sections 5.1, 5.3, 5.4.
* ``research/00_specifications/FROZEN_MATH_SPEC.md`` section 5.1.

Why this file is additive, and exactly where
--------------------------------------------
``src/g4/parameters.py:22-25`` rejects every coefficient ``<= 0.0``, and
``src/g5/domains.py:126-127`` refuses any activity signature other than
``(True, True)``.  A D013 inactive family therefore cannot be loaded through the
frozen G4/G5 types at all.  ``src/`` is frozen and is NOT modified.  The
minimal additive path is:

* the *arithmetic* is the frozen ``src/g4.energy`` transcript wherever it
  applies -- ``f``, ``h_card``/``h_sector``/``h_budget``, ``card_square``,
  the register ``S_acc`` order, and ``tau``;
* only the *coefficient/activity* layer is new, because the frozen
  ``PreparedCoefficients`` refuses ``+0.0``.  ``InertCoefficients`` is the single
  new type and is deliberately NOT a ``parameters.Coefficients``.

Two ledger paths live here, and they are bit-identical by construction and by
fixture over the whole decoded domain:

``fast``
    the section 5.2 transcript with zero-multiplicand terms elided.  Eliding a
    term is only sound because ``fl(a + (+0.0)) == a`` for every ``a != -0.0``
    and the accumulator is never ``-0.0``; ``fl(a + (-0.0)) == a`` for every
    ``a``, and ``-0.0 + -0.0 == -0.0`` while ``-0.0 + +0.0 == +0.0``.  Those
    are the two branch points the fixtures pin.
``literal``
    the same transcript with every term written out, used by
    :func:`literal_state_ledger` so the fixture has a second in-module path.

Semantics fixed here
--------------------
Conditions ``C``, ``CB``, ``CS``, ``CSB`` per D013's ``F_q`` predicates.
Cardinality is active in all four.  ``C``: sector and budget inactive.
``CB``: sector inactive.  ``CS``: budget inactive.  ``CSB``: all active.
An inactive family's coefficient is exactly ``+0.0`` (binary64 bit pattern
``0x0000000000000000``) and its raw register is RETAINED.  Accumulation follows
D015's fixed order: ``f``, ``P_card``, sector ``j = 1..4``, then budget.
``feasible_q(x)`` iff ``x in F_q``; ``f*_q = min_{x in F_q} f(x)``; D016's
A/B/C for condition ``q`` uses ``feasible_q`` and ``f*_q``.  Empty ``F_q``
raises :class:`InertEvaluatorError` and writes nothing.  ``|T_E|`` is the exact
integer ``base * 2**w`` with ``w`` the total retained inactive register width
(8 for the sector family, 11 for budget), computed arithmetically.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from src.g4 import energy as frozen_energy
from src.g4.classification import DecodedClassifier, OriginalObjectiveService
from src.g4.energy import (
    BUDGET_SLACK_BITS,
    EPSILON,
    SECTOR_SLACK_BITS,
    SLACK_AUXILIARY_LENGTH,
    PreparedDecodedState,
    PreparedInstance,
    prepare_decoded_state,
    prepare_instance,
)
from src.g4.instance import Instance

SECTOR_COUNT = 4
#: Scope-locked raw layout: 20 bits + 2*4 sector slack + 11 budget slack.
RAW_VARIABLE_COUNT = 20 + SLACK_AUXILIARY_LENGTH
RAW_DOMAIN_BITS = 39

#: binary64 bit pattern of the one permitted inactive coefficient.
POSITIVE_ZERO_PATTERN = 0x0000000000000000
#: binary64 bit pattern of the zero that must never be produced or consumed.
NEGATIVE_ZERO_PATTERN = 0x8000000000000000

#: D015's four conditions, in the order D013 fixes them.
CONDITIONS: tuple[str, ...] = ("C", "CB", "CS", "CSB")

#: D013's active/inactive map, read directly off the four ``F_q`` predicates.
#: Cardinality is present in all four predicates and is therefore never inactive.
FAMILY_ACTIVE: dict[str, dict[str, bool]] = {
    "C": {"cardinality": True, "sector": False, "budget": False},
    "CB": {"cardinality": True, "sector": False, "budget": True},
    "CS": {"cardinality": True, "sector": True, "budget": False},
    "CSB": {"cardinality": True, "sector": True, "budget": True},
}

#: Retained inactive register width contributed by each family, in bits.
FAMILY_INACTIVE_WIDTH: dict[str, int] = {
    "sector": SECTOR_COUNT * SECTOR_SLACK_BITS,  # 8
    "budget": BUDGET_SLACK_BITS,                 # 11
}

_COEF_FIELDS: tuple[str, ...] = (
    "alpha",
    "sector_slack",
    "budget_slack",
    "sector_linear",
    "sector_quadratic",
    "budget_linear",
    "budget_quadratic",
)
_FAMILY_FIELDS: dict[str, tuple[str, ...]] = {
    "cardinality": ("alpha",),
    "sector": ("sector_slack", "sector_linear", "sector_quadratic"),
    "budget": ("budget_slack", "budget_linear", "budget_quadratic"),
}
_FIELD_FAMILY: dict[str, str] = {
    name: family for family, names in _FAMILY_FIELDS.items() for name in names
}
_COEFFICIENT_SETS: dict[str, frozenset[str]] = {
    family: frozenset(names) for family, names in _FAMILY_FIELDS.items()
}


class InertEvaluatorError(ValueError):
    """A typed refusal. Raised before any result is constructed."""


#: Typed refusals raised by delegated modules.  A call into any of these must
#: surface as :class:`InertEvaluatorError` at this module's trust boundary, never
#: as the delegated module's own exception class.
_DELEGATED_TYPED_ERRORS: tuple[type[BaseException], ...] = (ValueError, TypeError)


def _require(condition: object, message: str) -> None:
    if not condition:
        raise InertEvaluatorError(message)


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InertEvaluatorError(f"{label} must be a real number, not {type(value).__name__}")
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError) as error:
        raise InertEvaluatorError(
            f"{label} must be a finite binary64 value ({error})"
        ) from error
    if not math.isfinite(result):
        raise InertEvaluatorError(f"{label} must be finite, got {value!r}")
    return result


def _require_real_number(value: object, label: str) -> None:
    """Type-check a numeric field **before** any conversion or arithmetic.

    This is the lead's ruling (1) at the trust boundary: a numeric field must be
    an ``int`` or a ``float`` -- ``bool`` excluded, since ``True`` is an ``int``
    and would silently pass as ``1.0`` -- and must be finite.  Both checks run
    on the *raw* value, so a ``str``/``list``/``dict``/``None`` can never reach a
    ``float()`` call that would raise an untyped ``ValueError`` or ``TypeError``.

    The check is deliberately type-based rather than exception-based: it runs
    before the conversion, not as a rescue of a failed conversion.

    ``math.isfinite`` cannot take an ``int`` at all -- it raises
    ``OverflowError: int too large to convert to float`` for an integer beyond
    binary64's range, and ``TypeError`` for a non-numeric -- so an ``int`` is
    range-checked by conversion inside a narrow ``try`` that catches **only**
    ``OverflowError``, ``TypeError`` and ``ValueError``.  Without that, a
    perfectly well-typed Python ``int`` such as ``10**400`` would leak an
    untyped ``OverflowError`` out of the very check meant to keep exceptions
    typed.  ``BaseException`` is not caught, so cancellation still passes
    through.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InertEvaluatorError(
            f"{label} must be an int or a float, not {type(value).__name__}"
        )
    try:
        finite = math.isfinite(value)
    except (OverflowError, TypeError, ValueError) as error:
        raise InertEvaluatorError(
            f"{label} must be a finite binary64 value; an int of this magnitude "
            f"has no finite float() representation ({error})"
        ) from error
    if not finite:
        raise InertEvaluatorError(f"{label} must be finite, got {value!r}")


def _delegated(boundary: str, call: object) -> object:
    """Run one call into a delegated module and type its failure.

    This is the lead's ruling (2).  Every call into ``src.g4``, ``src.g5`` or
    ``research.g9.stage2_instance_preparation`` -- and any other frozen ``src``
    call that consumes caller data -- goes through this one helper.  It converts
    the delegated module's own typed errors plus ``TypeError``, ``ValueError``
    and ``ArithmeticError`` into :class:`InertEvaluatorError`, preserving the
    original message and chaining with ``from`` so no context is lost.

    ``BaseException`` is deliberately NOT caught: ``KeyboardInterrupt``,
    ``SystemExit`` and ``MemoryError`` must pass through untouched.
    """
    try:
        return call()
    except InertEvaluatorError:
        raise
    except _DELEGATED_TYPED_ERRORS + (ArithmeticError,) as error:
        raise InertEvaluatorError(
            f"{boundary} refused: {error}"
        ) from error


def _wp5b_prepared_state(instance: Instance) -> PreparedInstance:
    """WP5b's prepared instance, typed at this module's boundary.

    ``research.g9.stage2_instance_preparation`` (WP5b) validates and prepares an
    instance at the protocol's own entry boundary.  Its refusals are
    :class:`InstancePreparationError` and its underlying frozen calls raise plain
    ``ValueError``/``TypeError``, neither of which is this module's typed error.
    The call is therefore routed through :func:`_delegated` so a bad instance
    surfaces as :class:`InertEvaluatorError` and never as an untyped built-in.
    """
    from research.g9 import stage2_instance_preparation as wp5b

    return _delegated(
        "WP5b stage2_instance_preparation validation",
        lambda: wp5b.validate_envelope(instance),
    )


# --------------------------------------------------------------------------- #
# Positive zero
# --------------------------------------------------------------------------- #


def bits_of(value: float) -> int:
    """IEEE-754 binary64 bit pattern of a finite float, sign bit included."""
    _require(type(value) is float, "bits_of requires a float")
    _require(math.isfinite(value), "bits_of requires a finite float")
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def require_positive_zero(value: object, label: str) -> float:
    """Accept only the exact positive zero, judged by bit pattern, never by value.

    ``-0.0 == +0.0`` in binary64, so a value comparison cannot separate them and
    the sign bit must.  This is the refusal that makes an inactive coefficient
    impossible to supply as ``-0.0``, and it is also the guarantee that every
    inactive penalty is emitted with a clear sign bit.
    """
    _require(type(value) is float, f"{label} must be a float; got {type(value).__name__}")
    _require(math.isfinite(value), f"{label} must be finite")
    pattern = bits_of(value)
    _require(
        pattern == POSITIVE_ZERO_PATTERN,
        f"{label} must be exactly +0.0 (0x{POSITIVE_ZERO_PATTERN:016x}); "
        f"got bit pattern 0x{pattern:016x}",
    )
    return +0.0


def add_inert(accumulator: float, penalty: float, label: str) -> float:
    """``fl(accumulator + penalty)`` for an inactive family's ``+0.0`` penalty.

    The addition is performed, then its result is checked to be bit-identical to
    the accumulator unless the accumulator was a zero, in which case the result
    is required to be the *positive* zero.  This is where a ``-0.0`` penalty
    would be caught: ``fl(-0.0 + -0.0) == -0.0`` keeps a dirty sign bit that
    ``fl(-0.0 + +0.0) == +0.0`` clears.

    The accumulator is caller data, so it is type-checked **before** the
    addition: a ``str``/``list``/``dict``/``None`` would otherwise make the
    ``accumulator + penalty`` expression itself raise an untyped ``TypeError``.
    """
    _require_real_number(accumulator, f"{label} accumulator")
    require_positive_zero(penalty, f"{label} inactive contribution")
    result = accumulator + penalty
    result = _finite(result, f"{label} H_acc")
    if accumulator == 0.0:
        _require(
            bits_of(result) == POSITIVE_ZERO_PATTERN,
            f"{label} adding +0.0 to a zero accumulator must yield +0.0, not a "
            f"negative zero (0x{bits_of(result):016x})",
        )
    else:
        _require(
            result == accumulator,
            f"{label} adding the inactive +0.0 perturbed the accumulator",
        )
        _require(
            bits_of(result) == bits_of(accumulator),
            f"{label} adding the inactive +0.0 changed the accumulator bit pattern",
        )
    return result


# --------------------------------------------------------------------------- #
# Conditions and coefficients
# --------------------------------------------------------------------------- #


def family_activity(condition: object) -> dict[str, bool]:
    """D013's active/inactive map for one condition name.

    A malformed name is a typed refusal.  There is deliberately no default and
    no silent fallback to ``CSB``.
    """
    if not isinstance(condition, str):
        raise InertEvaluatorError(
            f"condition must be a string, not {type(condition).__name__}"
        )
    if condition not in FAMILY_ACTIVE:
        raise InertEvaluatorError(
            f"unknown condition {condition!r}; D013 fixes exactly {CONDITIONS}"
        )
    return dict(FAMILY_ACTIVE[condition])


@dataclass(frozen=True)
class InertCoefficients:
    """One condition's coefficients, permitting exactly ``+0.0`` per family.

    A field is ``+0.0`` exactly when its family is inactive, and strictly
    positive when its family is active.  There is no third possibility: the
    correspondence is enforced field by field in ``__post_init__``.
    """

    condition: str
    alpha: float
    sector_slack: float
    budget_slack: float
    sector_linear: float
    sector_quadratic: float
    budget_linear: float
    budget_quadratic: float

    def __post_init__(self) -> None:
        activity = family_activity(self.condition)
        for family in ("cardinality", "sector", "budget"):
            for name in _FAMILY_FIELDS[family]:
                value = getattr(self, name)
                if activity[family]:
                    number = _finite(value, f"{self.condition}:{name}")
                    _require(
                        number > 0.0,
                        f"{self.condition}:{name} belongs to the ACTIVE family {family!r} and "
                        f"must be strictly positive, got {value!r}",
                    )
                    object.__setattr__(self, name, number)
                else:
                    object.__setattr__(
                        self, name, require_positive_zero(value, f"{self.condition}:{name}")
                    )

    def active_families(self) -> tuple[str, ...]:
        activity = family_activity(self.condition)
        return tuple(name for name in ("sector", "budget") if activity[name])

    def inactive_families(self) -> tuple[str, ...]:
        activity = family_activity(self.condition)
        return tuple(name for name in ("sector", "budget") if not activity[name])

    def inactive_width(self) -> int:
        """``w``: total retained inactive register width, in bits."""
        return sum(FAMILY_INACTIVE_WIDTH[name] for name in self.inactive_families())

    def active_penalty_axes(self) -> int:
        """D013's active-axis count: 1 for C, 2 for CB and CS, 3 for CSB.

        An inactive axis is omitted, not duplicated, so this is the count a
        denominator may use (U12 memo 5.1, corroborating D013's
        active-coordinate rule).
        """
        return 1 + len(self.active_families())

    def frozen_active_view(self):
        """``parameters.Coefficients`` -- only representable when all-active.

        This exists so the ``CSB`` fixture can drive the frozen ledger through
        the frozen type rather than a look-alike.  Every other condition is
        refused here, because the frozen type cannot hold ``+0.0``.
        """
        activity = family_activity(self.condition)
        if not all(activity.values()):
            inactive = self.inactive_families()
            raise InertEvaluatorError(
                f"{self.condition} has inactive {inactive} family/families and cannot be "
                "represented by parameters.Coefficients, which rejects coefficients <= 0.0"
            )
        from src.g4.parameters import Coefficients  # frozen-type boundary

        return _delegated(
            "frozen src.g4.parameters.Coefficients",
            lambda: Coefficients(
                alpha=self.alpha,
                sector_slack=self.sector_slack,
                budget_slack=self.budget_slack,
                sector_linear=self.sector_linear,
                sector_quadratic=self.sector_quadratic,
                budget_linear=self.budget_linear,
                budget_quadratic=self.budget_quadratic,
            ),
        )


def build_condition_coefficients(condition: object, active: object) -> InertCoefficients:
    """Apply D013's ablation to an all-active CSB coefficient ledger.

    ``active`` is the **CSB** ledger: a complete, closed set of seven fields,
    every one of them finite and strictly positive.  It is validated in full
    first, so a ``0.0``, a ``-0.0``, a negative number, a non-finite number or a
    wrong type anywhere in it is a typed refusal, in an inactive field just as
    much as in an active one.

    Only then is the ablation applied: each field of an inactive family is
    *replaced* by exactly ``+0.0``.  The supplied value is not used for an
    inactive field -- D013 fixes that coefficient to ``+0.0``, never to a scaled
    or carried-over number -- and each field of an active family is carried
    through unchanged.
    """
    activity = family_activity(condition)
    if not isinstance(active, dict):
        raise InertEvaluatorError(
            f"active coefficient ledger must be a dict, not {type(active).__name__}"
        )
    unknown = sorted(set(active) - set(_COEF_FIELDS))
    _require(not unknown, f"unknown coefficient fields: {unknown}")
    missing = sorted(set(_COEF_FIELDS) - set(active))
    _require(not missing, f"missing coefficient fields: {missing}")
    values: dict[str, float] = {}
    for name in _COEF_FIELDS:
        # Validate the whole supplied CSB ledger before substituting anything.
        number = _finite(active[name], f"CSB ledger {name}")
        _require(
            number > 0.0,
            f"the CSB coefficient ledger requires a strictly positive {name}, "
            f"got {active[name]!r}",
        )
        values[name] = +0.0 if not activity[_FIELD_FAMILY[name]] else number
    return InertCoefficients(condition=condition, **values)


# --------------------------------------------------------------------------- #
# Condition context
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ConditionContext:
    """One instance bound to one D013 condition and its coefficient ledger."""

    condition: str
    instance: Instance
    prepared: PreparedInstance | None
    coefficients: InertCoefficients
    active_families: tuple[str, ...]
    inactive_families: tuple[str, ...]
    inactive_width: int
    active_penalty_axes: int
    lambda_ref: float
    c_h: float = 2048.0

    def width(self) -> int:
        return len(self.instance.tickers)

    def require_frozen(self) -> PreparedInstance:
        """The frozen prepared instance, or a refusal.

        ``src.g4.energy.prepare_decoded_state`` is hard-bound to 20 tickers and
        4 sectors, so the frozen prepared state exists only at the Scope-locked
        width.  The synthetic fixtures use a narrower instance to stay
        tractable, and every frozen-path call refuses there rather than
        silently substituting a local path.
        """
        if self.prepared is None:
            raise InertEvaluatorError(
                f"this {self.width()}-ticker synthetic instance has no frozen "
                "src.g4.energy prepared state; the frozen ledger is bound to 20 tickers"
            )
        return self.prepared


def _require_instance_numbers(instance: Instance, width: int) -> None:
    """Type-check every numeric instance field **before** it is converted.

    Shared by both branches of :func:`prepare_condition`, so a 20-ticker
    instance and a narrow synthetic one are held to the same type boundary.
    Splitting it out of :func:`_require_synthetic_instance` is a move, not a
    removal: the synthetic branch still runs every check this performs, plus its
    own structural ones.
    """
    for label, values in (
        ("mu", instance.mu),
        ("prices", instance.prices),
    ):
        if len(values) != width:
            raise InertEvaluatorError(f"{label} must have length {width}")
        for index, value in enumerate(values):
            _require_real_number(value, f"{label}[{index}]")
    if len(instance.sigma) != width:
        raise InertEvaluatorError("Sigma must have one row per ticker")
    for index, row in enumerate(instance.sigma):
        if len(row) != width:
            raise InertEvaluatorError(f"Sigma row {index} must have length {width}")
        for column, value in enumerate(row):
            _require_real_number(value, f"Sigma[{index},{column}]")
    _require_real_number(instance.kappa_risk, "kappa_risk")
    _require_real_number(instance.K, "K")
    _require_real_number(instance.C, "C")
    _require_real_number(instance.B, "B")


def _require_synthetic_instance(instance: Instance) -> None:
    """Typed validation for a narrower synthetic instance.

    The Scope-locked frozen validator (``src.g4.energy._require_instance``) is
    not weakened and is still applied at 20 tickers.  This narrower check exists
    only so the synthetic fixtures can exercise the whole four-condition
    machinery on a small decoded domain; it enforces the same structural
    requirements that the D013 predicates actually rely on.

    Every numeric field is **type-checked before it is converted**.  Round 2
    validated ``K`` and ``C`` by evaluating ``float(instance.K)`` and
    ``float(instance.C)`` and handing the *result* to :func:`_finite`; a
    non-numeric ``K`` or ``C`` therefore raised an untyped ``ValueError`` (or
    ``TypeError``) from the conversion itself, before ``_finite`` could run, and
    the typed refusal contract was broken.  :func:`_require_real_number` checks
    the raw value's type and finiteness first, so no conversion is ever
    attempted on a value that is not already a real number.
    """
    width = len(instance.tickers)
    if width <= 0:
        raise InertEvaluatorError("an instance must have at least one ticker")
    if len(instance.sectors) != SECTOR_COUNT:
        raise InertEvaluatorError(
            f"an instance must have exactly {SECTOR_COUNT} sectors"
        )
    covered = sorted(index for sector in instance.sectors for index in sector)
    if covered != list(range(width)):
        raise InertEvaluatorError("the sector map must partition the instance width")
    _require_instance_numbers(instance, width)


def prepare_condition(
    instance: object, condition: object, active: object, lambda_ref: object
) -> ConditionContext:
    """Validate the instance, the condition name and the CSB ledger together.

    Nothing is produced here, so a refusal at this boundary writes nothing.

    Trust boundary, in the order it runs:

    1. ``condition`` and the CSB ledger are validated by the typed helpers
       above, which type-check before converting.
    2. ``lambda_ref`` is type-checked and converted by :func:`_finite`, which
       refuses a non-``int``/``float`` (including ``bool``) and a non-finite
       value before any arithmetic.
    3. The instance's numeric fields are type-checked by
       :func:`_require_instance_numbers` on **both** width branches, so no
       malformed value ever reaches the frozen validator.
    4. The frozen ``prepare_instance`` call is routed through
       :func:`_delegated`, so its ``ValueError``/``TypeError`` on a structurally
       bad Scope-locked instance surfaces as :class:`InertEvaluatorError`
       instead of leaking a built-in.
    """
    activity = family_activity(condition)
    coefficients = build_condition_coefficients(condition, active)
    if not isinstance(instance, Instance):
        raise InertEvaluatorError(
            f"instance must be a src.g4.instance.Instance, not {type(instance).__name__}"
        )
    scale = _finite(lambda_ref, "Lambda_ref")
    _require(scale > 0.0, "Lambda_ref must be strictly positive")
    if len(instance.tickers) == 20 and len(instance.sectors) == SECTOR_COUNT:
        # The Scope-locked width: type-check every numeric field on the raw
        # value first, then apply the frozen validator unchanged.  Round 2 went
        # straight to the frozen call, so a bad ``mu``/``Sigma``/``K``/``C``/
        # ``B`` raised the frozen module's own untyped ValueError/TypeError.
        _require_instance_numbers(instance, len(instance.tickers))
        prepared = _delegated(
            "frozen src.g4.energy.prepare_instance", lambda: prepare_instance(instance)
        )
    else:
        _require_synthetic_instance(instance)
        prepared = None
    return ConditionContext(
        condition=condition,
        instance=instance,
        prepared=prepared,
        coefficients=coefficients,
        active_families=tuple(name for name in ("sector", "budget") if activity[name]),
        inactive_families=tuple(name for name in ("sector", "budget") if not activity[name]),
        inactive_width=coefficients.inactive_width(),
        active_penalty_axes=coefficients.active_penalty_axes(),
        lambda_ref=scale,
    )


# --------------------------------------------------------------------------- #
# Section 5.2 primitives
# --------------------------------------------------------------------------- #


def _register_value(bits: Sequence[int], label: str) -> float:
    """``S_acc`` in increasing register-bit order, ``bit_weight[d] = 2^d``.

    The weights are integer shifts, never ``pow``.  This is the frozen
    ``src/g4.energy._slack_register`` order, re-stated so the inactive path can
    evaluate the register without importing a private name.
    """
    accumulator = +0.0
    for degree, bit in enumerate(bits):
        if bit not in (0, 1):
            raise InertEvaluatorError(f"{label} y[{degree}] is not a bit: {bit!r}")
        weight = _finite(float(1 << degree), f"{label} 2^{degree}")
        accumulator = _finite(accumulator + (weight * float(bit)), f"{label} S_acc")
    return accumulator


def _register_bits(value: int, width: int) -> tuple[int, ...]:
    return tuple((value >> degree) & 1 for degree in range(width))


def exact_register_minimisers(residual: float, maximum: int) -> tuple[int, ...]:
    """Every register value that exactly minimises ``(residual - S)**2``.

    Closed form, not a scan, and it is the *same* rule the frozen
    ``src/g5.domains._register_minimizers`` applies: an integral residual has a
    unique minimiser, a non-integral residual has at most two, and a merely
    near-minimal register is never admitted.
    """
    if not math.isfinite(residual):
        raise InertEvaluatorError(f"slack residual must be finite, got {residual!r}")
    lower = math.floor(residual)
    candidates = {min(max(lower, 0), maximum), min(max(lower + 1, 0), maximum)}
    scored = []
    for value in sorted(candidates):
        delta = residual - float(value)
        penalty = delta * delta
        if not math.isfinite(penalty):
            raise InertEvaluatorError("nonfinite slack-minimiser penalty")
        scored.append((value, penalty))
    best = min(score for _, score in scored)
    return tuple(value for value, score in scored if score == best)


def _family_square(residual: float, values: Sequence[int], width: int) -> float:
    """``min`` of ``fl(fl(h - S_acc)**2)`` over the exact register minimisers."""
    best: float | None = None
    for value in values:
        s_acc = _register_value(_register_bits(value, width), "register")
        slack_delta = _finite(residual - s_acc, "slack_delta")
        square = _finite(slack_delta * slack_delta, "slack_square")
        if best is None or square < best:
            best = square
    if best is None:
        raise InertEvaluatorError("a family must have at least one exact register minimiser")
    return best


@dataclass(frozen=True)
class FamilyPenalty:
    """One inequality family's ``P_E_ineq`` for one raw state."""

    family: str
    active: bool
    penalty: float
    minimum_square: float
    minimum_count: int
    minimum_values: tuple[int, ...]


def family_penalty(
    family: str, active: bool, residual: float, coefficient: float, width: int
) -> FamilyPenalty:
    """Evaluate one family's ``P_E_ineq`` under the active/inactive split.

    Active: the frozen slack path over the exact register minimisers, so
    ``P_E_ineq = fl(lambda_S * slack_square)`` with ``lambda_S > 0``.

    Inactive: the coefficient is ``+0.0`` and the register is RETAINED.  The
    frozen product is *evaluated*, not assumed: ``fl(+0.0 * slack_square)`` is
    ``+0.0`` for every finite square, and the result is then refused unless its
    bit pattern is exactly ``0x0000000000000000``.  Every assignment of the
    still-present register is an exact lift, so the family's lift multiplicity is
    ``2**width`` and is carried symbolically -- the register is never enumerated.
    """
    if not isinstance(family, str) or not family:
        raise InertEvaluatorError("family label must be a nonempty string")
    if not isinstance(width, int) or isinstance(width, bool) or width <= 0:
        raise InertEvaluatorError(f"{family} register width must be a positive int")
    if active:
        values = exact_register_minimisers(residual, (1 << width) - 1)
        square = _family_square(residual, values, width)
        penalty = _finite(coefficient * square, f"P_E_{family}")
        _require(
            bits_of(penalty) != NEGATIVE_ZERO_PATTERN or penalty != 0.0,
            f"active {family} penalty must not be the negative zero",
        )
        return FamilyPenalty(family, True, penalty, square, len(values), values)
    require_positive_zero(coefficient, f"{family} inactive coefficient")
    # Evaluate the frozen product on the family's canonical register words.  A
    # +0.0 coefficient is inert under every finite register assignment, so one
    # canonical word plus the all-zero word is a complete witness that the
    # product does not depend on the retained register.
    for witness in (0, (1 << width) - 1):
        s_acc = _register_value(_register_bits(witness, width), f"{family} retained register")
        slack_delta = _finite(residual - s_acc, f"{family} slack_delta")
        slack_square = _finite(slack_delta * slack_delta, f"{family} slack_square")
        penalty = _finite(coefficient * slack_square, f"P_E_{family}")
        require_positive_zero(penalty, f"{family} inactive penalty")
    return FamilyPenalty(family, False, +0.0, +0.0, 1 << width, ())


# --------------------------------------------------------------------------- #
# Per-state ledgers
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class StateLedger:
    """D015's ordered transcript for one raw state under one condition."""

    condition: str
    x: tuple[int, ...]
    f_value: float
    p_card: float
    sector: tuple[FamilyPenalty, ...]
    budget: FamilyPenalty
    h_e: float
    accumulator_trace: tuple[float, ...]
    #: Accumulator bit pattern before/after each inactive addition, and how many
    #: such additions this state made. Recorded, not asserted.
    inert_additions: tuple[tuple[int, int], ...]
    inert_contributions: int

    def penalties(self) -> tuple[float, ...]:
        """The six penalty values in D015's fixed order."""
        return (self.p_card,) + tuple(item.penalty for item in self.sector) + (self.budget.penalty,)

    def inactive_penalties(self) -> tuple[float, ...]:
        """The penalties of the inactive families, in D015's order."""
        return tuple(item.penalty for item in self.sector if not item.active) + (
            (self.budget.penalty,) if not self.budget.active else ()
        )


def _accumulate(
    f_value: float, p_card: float, sector: Sequence[FamilyPenalty], budget: FamilyPenalty
) -> tuple[float, tuple[float, ...], tuple[tuple[int, int], ...], int]:
    """D015's unshifted sum, in its fixed order, with the ``+0.0`` guard.

    ``H_acc = f``; ``H_acc = fl(H_acc + P_card)``; ``for j = 1..4``;
    ``H_acc = fl(H_acc + P_E_sector[j])``; ``H_E = fl(H_acc + P_E_budget)``.

    An active family's penalty is added by the frozen addition.  An inactive
    family's ``+0.0`` is routed through :func:`add_inert`, which performs the
    addition and then refuses a perturbed accumulator or a dirty sign bit.

    Returns ``(H_E, trace, inert_additions, inert_contributions)`` where
    ``inert_additions`` records the accumulator's bit pattern immediately before
    and after each inactive addition, so a fixture can independently confirm
    that the addition was performed and changed nothing.
    """
    trace: list[float] = []
    inert: list[tuple[int, int]] = []
    h_acc = _finite(f_value, "f")
    h_acc = _finite(h_acc + p_card, "H_acc")
    trace.append(h_acc)
    for item in sector:
        if item.active:
            h_acc = _finite(h_acc + item.penalty, "H_acc")
        else:
            before = bits_of(h_acc)
            h_acc = add_inert(h_acc, item.penalty, f"sector[{item.family}]")
            inert.append((before, bits_of(h_acc)))
        trace.append(h_acc)
    if budget.active:
        h_acc = _finite(h_acc + budget.penalty, "H_E")
    else:
        before = bits_of(h_acc)
        h_acc = add_inert(h_acc, budget.penalty, "budget")
        inert.append((before, bits_of(h_acc)))
    trace.append(h_acc)
    return h_acc, tuple(trace), tuple(inert), len(inert)


def decoded_state(context: ConditionContext, x: tuple[int, ...]):
    """The **frozen** grid-independent section 5.2 intermediates for one state.

    This is the only call into ``src.g4.energy.prepare_decoded_state``, and it is
    available only at the Scope-locked 20-ticker width, where the frozen
    prepared instance exists.  It is what the CSB fixture compares
    :func:`fast_decoded_state` against; every other path uses the fast
    preparation, which the same fixture pins as bit-identical.
    """
    return _delegated(
        "frozen src.g4.energy.prepare_decoded_state",
        lambda: prepare_decoded_state(context.require_frozen(), x),
    )


def _accumulator_is_negative_zero(value: float) -> bool:
    """True iff ``value`` is the negative zero. Cheaper than :func:`bits_of`.

    ``math.copysign`` distinguishes the two zeros directly, and this is on the
    hot path of :func:`fast_decoded_state`, so it avoids a struct round trip.
    The check itself is identical in meaning: the two zeros compare equal, so
    equality alone can never see it and the sign must be consulted.
    """
    return value == 0.0 and math.copysign(1.0, value) < 0.0


def _nonnegative_accumulator(value: float, label: str) -> float:
    """Refuse an accumulator that is the negative zero, before it can spread.

    Every section 5.2 accumulator here starts at ``+0.0`` and only ever receives
    either a non-negative term (a count, a price, a square) or a ``+/-0.0``
    term.  ``fl(+0.0 + (+/-0.0)) == +0.0``, so no accumulator can become
    ``-0.0``.  This check makes that invariant explicit and enforced rather
    than assumed, and it is what licenses the elision in
    :func:`fast_decoded_state`.
    """
    _require(
        not _accumulator_is_negative_zero(value),
        f"{label} became the negative zero; the ledger invariant is broken",
    )
    return value


def fast_decoded_state(
    context: ConditionContext, x: tuple[int, ...]
) -> PreparedDecodedState:
    """The section 5.2 intermediates, bit-identical to the frozen preparation.

    This exists only for speed, and it is *not* a different arithmetic.  It
    elides section 5.2 terms whose multiplicand is a zero bit.  Elision is
    bit-exact, not approximately equal, for three reasons:

    1. A zero-bit term is exactly ``+/-0.0``: ``fl(mu[i] * (+0.0))`` is ``+0.0``
       for ``mu[i] > 0`` and ``-0.0`` for ``mu[i] < 0``, and the leading unary
       minus of ``mu_term`` may flip that sign again.  The sign is
       unobservable here because ``fl(a + (+0.0)) == a`` for every ``a != -0.0``
       and ``fl(a + (-0.0)) == a`` for *every* ``a``.
    2. No accumulator in the section 5.2 transcript can be ``-0.0``: each
       starts at ``+0.0`` and only ever receives non-negative terms, and
       ``fl(+0.0 + (+/-0.0)) == +0.0``.  :func:`_nonnegative_accumulator`
       enforces this at every step.
    3. The one case where an elision would be visible -- adding ``+0.0`` to a
       ``-0.0`` accumulator, which yields ``+0.0`` -- is therefore unreachable,
       and the guard in (2) is what rules it out.

    The fixture pins this claim over the **full decoded domain** against
    ``src.g4.energy.prepare_decoded_state`` itself; this function is not
    accepted on inspection.
    """
    if not isinstance(context, ConditionContext):
        raise InertEvaluatorError("context must come from prepare_condition")
    instance = context.instance
    width = context.width()
    if not isinstance(x, tuple) or len(x) != width:
        raise InertEvaluatorError(f"x must be a length-{width} tuple of bits")
    if any(bit not in (0, 1) for bit in x):
        raise InertEvaluatorError("x must contain only the bits 0 and 1")
    mu = instance.mu
    sigma = instance.sigma
    kappa = instance.kappa_risk

    f_acc = +0.0
    for i in range(width):
        if x[i]:
            # mu_term[i] = -fl(mu[i] * x[i]); with x[i] == 1 this is -mu[i].
            f_acc = f_acc - mu[i]
            if not math.isfinite(f_acc):
                raise InertEvaluatorError("nonfinite f_acc")
            if _accumulator_is_negative_zero(f_acc):
                raise InertEvaluatorError("f_acc became the negative zero")
    for i in range(width):
        if not x[i]:
            continue
        row = sigma[i]
        for k in range(width):
            if x[k]:
                # fl(kappa_risk * fl(fl(Sigma[i,k]*x[i]) * x[k])) with both bits set.
                f_acc = f_acc + (kappa * row[k])
                if not math.isfinite(f_acc):
                    raise InertEvaluatorError("nonfinite f_acc")
                if _accumulator_is_negative_zero(f_acc):
                    raise InertEvaluatorError("f_acc became the negative zero")
    f_value = f_acc

    # The residual accumulators only ever receive non-negative counts and
    # prices, so they are a single subtraction/multiply away from -0.0 at worst;
    # the negative-zero guard is applied to the results, which is where the
    # elision would be observable.
    card_sum = 0.0
    for i in range(width):
        if x[i]:
            card_sum += 1.0
    h_card = card_sum - float(instance.K)
    h_sector = []
    sector_square = []
    for j, members in enumerate(instance.sectors):
        sector_sum = 0.0
        for i in sorted(members):
            if x[i]:
                sector_sum += 1.0
        residual = float(instance.C) - sector_sum
        _nonnegative_accumulator(residual, f"h_sector[{j}]")
        h_sector.append(residual)
        square = residual * residual
        _require(math.isfinite(square), f"nonfinite sector[{j}] quadratic_square")
        sector_square.append(square)
    budget_sum = 0.0
    prices = instance.prices
    for i in range(width):
        if x[i]:
            budget_sum += prices[i]
    h_budget = instance.B - budget_sum
    _nonnegative_accumulator(h_budget, "h_budget")
    budget_square = h_budget * h_budget
    _require(math.isfinite(budget_square), "nonfinite budget quadratic_square")
    card_square = h_card * h_card
    _require(math.isfinite(card_square), "nonfinite card_square")
    for label, value in (
        ("card_sum", card_sum),
        ("budget_sum", budget_sum),
        ("h_card", h_card),
    ):
        if not math.isfinite(value):
            raise InertEvaluatorError(f"nonfinite {label}")
    return PreparedDecodedState(
        f_value=f_value,
        h_card=h_card,
        card_square=card_square,
        h_sector=tuple(h_sector),
        sector_square=tuple(sector_square),
        h_budget=h_budget,
        budget_square=budget_square,
    )


def state_ledger(
    context: ConditionContext, x: tuple[int, ...], frozen_intermediates=None
) -> StateLedger:
    """D015's transcript for one raw state, with ``+0.0`` for inactive families.

    The residuals and ``f`` come from the frozen ``src/g4.energy`` preparation
    service.  Only the coefficient layer is additive, because
    ``PreparedCoefficients`` refuses ``+0.0`` outright.
    """
    if not isinstance(context, ConditionContext):
        raise InertEvaluatorError("context must come from prepare_condition")
    if not isinstance(x, tuple) or len(x) != context.width():
        raise InertEvaluatorError(f"x must be a length-{context.width()} tuple of bits")
    if any(bit not in (0, 1) for bit in x):
        raise InertEvaluatorError("x must contain only the bits 0 and 1")
    decoded = (
        frozen_intermediates
        if frozen_intermediates is not None
        else fast_decoded_state(context, x)
    )
    coefficients = context.coefficients
    sector_active = "sector" in context.active_families
    budget_active = "budget" in context.active_families
    p_card = _finite(coefficients.alpha * decoded.card_square, "P_card")
    sector = tuple(
        family_penalty(
            f"sector[{j}]",
            sector_active,
            decoded.h_sector[j],
            coefficients.sector_slack,
            SECTOR_SLACK_BITS,
        )
        for j in range(SECTOR_COUNT)
    )
    budget = family_penalty(
        "budget", budget_active, decoded.h_budget, coefficients.budget_slack, BUDGET_SLACK_BITS
    )
    h_e, trace, inert, inert_count = _accumulate(
        decoded.f_value, p_card, sector, budget
    )
    return StateLedger(
        condition=context.condition,
        x=x,
        f_value=decoded.f_value,
        p_card=p_card,
        sector=sector,
        budget=budget,
        h_e=h_e,
        accumulator_trace=trace,
        inert_additions=inert,
        inert_contributions=inert_count,
    )


def literal_state_ledger(context: ConditionContext, x: tuple[int, ...]) -> StateLedger:
    """The same transcript with every section 5.2 term written out.

    This is the second in-module code path.  It does not call
    :func:`state_ledger`, does not use the fast decoded-state preparation, and
    writes each of the 20 ``mu_term`` and 400 ``quad_term`` terms explicitly, so
    the fixture can compare two independent assemblies of the same ledger.
    """
    if not isinstance(context, ConditionContext):
        raise InertEvaluatorError("context must come from prepare_condition")
    instance = context.instance
    if not isinstance(x, tuple) or len(x) != context.width():
        raise InertEvaluatorError(f"x must be a length-{context.width()} tuple of bits")
    if any(bit not in (0, 1) for bit in x):
        raise InertEvaluatorError("x must contain only the bits 0 and 1")
    bits = tuple(float(bit) for bit in x)
    width = context.width()

    mu_term = []
    for i in range(width):
        product = _finite(instance.mu[i] * bits[i], f"mu[{i}]*x[{i}]")
        mu_term.append(-product)
    quad_term = []
    for i in range(width):
        for k in range(width):
            sigma_xi = _finite(instance.sigma[i][k] * bits[i], f"sigma_xi[{i},{k}]")
            inner = _finite(sigma_xi * bits[k], f"sigma_xi[{i},{k}]*x[{k}]")
            quad_term.append(
                _finite(instance.kappa_risk * inner, f"quad_term[{i},{k}]")
            )
    f_acc = +0.0
    for term in mu_term:
        f_acc = _finite(f_acc + term, "f_acc")
    for term in quad_term:
        f_acc = _finite(f_acc + term, "f_acc")
    f_value = f_acc

    card_sum = +0.0
    for i in range(width):
        card_sum = _finite(card_sum + bits[i], "card_sum")
    h_card = _finite(card_sum - float(instance.K), "h_card")
    h_sector = []
    for j, members in enumerate(instance.sectors):
        sector_sum = +0.0
        for i in sorted(members):
            sector_sum = _finite(sector_sum + bits[i], f"sector_sum[{j}]")
        h_sector.append(_finite(float(instance.C) - sector_sum, f"h_sector[{j}]"))
    budget_sum = +0.0
    for i in range(width):
        spend = _finite(instance.prices[i] * bits[i], f"p[{i}]*x[{i}]")
        budget_sum = _finite(budget_sum + spend, "budget_sum")
    h_budget = _finite(instance.B - budget_sum, "h_budget")

    card_square = _finite(h_card * h_card, "card_square")
    p_card = _finite(context.coefficients.alpha * card_square, "P_card")
    sector_active = "sector" in context.active_families
    budget_active = "budget" in context.active_families
    sector = tuple(
        family_penalty(
            f"sector[{j}]",
            sector_active,
            h_sector[j],
            context.coefficients.sector_slack,
            SECTOR_SLACK_BITS,
        )
        for j in range(SECTOR_COUNT)
    )
    budget = family_penalty(
        "budget",
        budget_active,
        h_budget,
        context.coefficients.budget_slack,
        BUDGET_SLACK_BITS,
    )
    h_e, trace, inert, inert_count = _accumulate(f_value, p_card, sector, budget)
    return StateLedger(
        condition=context.condition,
        x=x,
        f_value=f_value,
        p_card=p_card,
        sector=sector,
        budget=budget,
        h_e=h_e,
        accumulator_trace=trace,
        inert_additions=inert,
        inert_contributions=inert_count,
    )


# --------------------------------------------------------------------------- #
# Feasibility and the original-objective optimum
# --------------------------------------------------------------------------- #


def feasible_q(context: ConditionContext, x: tuple[int, ...]) -> bool:
    """``feasible_q(x)`` iff ``x in F_q`` -- D013's predicate for this condition.

    Only the condition's ACTIVE families enter the predicate; an inactive family
    is not consulted at all, which is what makes ``F_C`` a relaxation of
    ``F_CSB`` rather than a differently-weighted copy of it.
    """
    if not isinstance(context, ConditionContext):
        raise InertEvaluatorError("context must come from prepare_condition")
    if not isinstance(x, tuple) or len(x) != context.width():
        raise InertEvaluatorError(f"x must be a length-{context.width()} tuple of bits")
    if any(bit not in (0, 1) for bit in x):
        raise InertEvaluatorError("x must contain only the bits 0 and 1")
    bits = tuple(float(bit) for bit in x)
    card_sum = +0.0
    for i in range(context.width()):
        card_sum = _finite(card_sum + bits[i], "card_sum")
    h_card = _finite(card_sum - float(context.instance.K), "h_card")
    if h_card != 0.0:
        return False
    if "sector" in context.active_families:
        for members in context.instance.sectors:
            sector_sum = +0.0
            for i in sorted(members):
                sector_sum = _finite(sector_sum + bits[i], "feasible sector_sum")
            if _finite(float(context.instance.C) - sector_sum, "feasible h_sector") < 0.0:
                return False
    if "budget" in context.active_families:
        budget_sum = +0.0
        for i in range(context.width()):
            budget_sum = _finite(
                budget_sum + (context.instance.prices[i] * bits[i]), "feasible budget_sum"
            )
        if _finite(context.instance.B - budget_sum, "feasible h_budget") < 0.0:
            return False
    return True


@dataclass(frozen=True)
class ObjectiveOptimum:
    """``f*_q`` for one condition: value plus its canonical witness."""

    condition: str
    f_star: float
    x_ref: tuple[int, ...]
    feasible_count: int
    argmin_set: tuple[tuple[int, ...], ...]


def objective_optimum(
    context: ConditionContext,
    states: Sequence[tuple[int, ...]],
    transcript: DecodedTranscript | None = None,
) -> ObjectiveOptimum:
    """``f*_q = min_{x in F_q} f(x)``, computed over the supplied states.

    An empty ``F_q`` is a hard stop: :class:`InertEvaluatorError` is raised
    before any result is constructed, so nothing is produced and nothing is
    written.  ``x_ref`` is the lexicographically first feasible portfolio
    attaining ``f*_q`` (D015 section 5.4).
    """
    if not isinstance(context, ConditionContext):
        raise InertEvaluatorError("context must come from prepare_condition")
    width = context.width()
    index_of = None
    if transcript is not None:
        index_of = {}
        for position, mask in enumerate(transcript.mask):
            index_of[mask] = position
    best: float | None = None
    argmins: list[tuple[int, ...]] = []
    feasible = 0
    for x in states:
        if not feasible_q(context, x):
            continue
        feasible += 1
        if index_of is not None:
            mask = 0
            for index, bit in enumerate(x):
                if bit:
                    mask |= 1 << (width - 1 - index)
            value = transcript.f[index_of[mask]]
        else:
            value = fast_decoded_state(context, x).f_value
        if best is None or value < best:
            best = value
            argmins = [x]
        elif value == best:
            argmins.append(x)
    if best is None:
        raise InertEvaluatorError(
            f"F_{context.condition} is empty -- no feasible portfolio under this condition's "
            "active predicates; this is a hard stop, not a value, and nothing was written"
        )
    ordered = tuple(sorted(argmins))
    return ObjectiveOptimum(
        condition=context.condition,
        f_star=best,
        x_ref=ordered[0],
        feasible_count=feasible,
        argmin_set=ordered,
    )


# --------------------------------------------------------------------------- #
# The retained register: symbolic multiplicity, never enumerated
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RawDomainAccounting:
    """Exact arithmetic accounting of the certified raw domain ``C_E``.

    ``base`` is the number of *active* lifts the code path actually walks, and
    ``w`` is the retained inactive register width, so ``|C_E| = base * 2**w``.
    ``materialised`` is the number of raw states the walk actually produced and
    it must equal ``base``: that equality is the mechanical proof that the
    retained register was counted, never traversed.  The retained register is
    counted, never iterated.

    ``|T_E|`` is a *different* quantity with the same shape: it is
    ``(ties in C_E) * 2**w``, where the tie count is generally smaller than
    ``base``.  Both are recorded, with their own factors, and neither is derived
    from the other.
    """

    condition: str
    base: int
    w: int
    raw_size: int
    raw_factors: tuple[int, int]
    inactive_multiplicities: tuple[tuple[str, int, int], ...]
    materialised: int
    retired_register_iterations: int

    @property
    def enumerated_raw_domain(self) -> bool:
        """True iff the code path actually walked the retained register."""
        return self.materialised != self.base


def raw_domain_accounting(
    context: ConditionContext, base: int, tie_count: int | None = None
) -> RawDomainAccounting:
    """Record ``|C_E| = base * 2^w``, and ``|T_E| = tie_count * 2^w``, arithmetically.

    ``base`` is what the active-lift walk produced.  ``tie_count`` is how many
    of those attain a tied energy; it defaults to ``base``, which is correct for
    the whole-domain accounting and is not a claim about ``T_E``.
    """
    if not isinstance(context, ConditionContext):
        raise InertEvaluatorError("context must come from prepare_condition")
    if isinstance(base, bool) or not isinstance(base, int) or base < 0:
        raise InertEvaluatorError("base must be a nonnegative int")
    if tie_count is not None and (isinstance(tie_count, bool) or not isinstance(tie_count, int)):
        raise InertEvaluatorError("tie_count must be an int")
    if tie_count is not None and not 0 <= tie_count <= base:
        raise InertEvaluatorError("tie_count must lie between zero and base")
    w = context.inactive_width
    if w < 0 or w >= RAW_DOMAIN_BITS:
        raise InertEvaluatorError("inactive register width is out of range")
    multiplicities = tuple(
        (family, FAMILY_INACTIVE_WIDTH[family], FAMILY_INACTIVE_WIDTH[family])
        for family in context.inactive_families
    )
    if sum(width for _, width, _ in multiplicities) != w:
        raise InertEvaluatorError("inactive multiplicities do not sum to w")
    return RawDomainAccounting(
        condition=context.condition,
        base=base,
        w=w,
        raw_size=base << w,
        raw_factors=(base, w),
        inactive_multiplicities=multiplicities,
        materialised=base,
        retired_register_iterations=0,
    )


def t_e_accounting(raw: RawDomainAccounting, tie_count: int) -> tuple[int, tuple[int, int]]:
    """``|T_E|`` as the exact integer ``tie_count * 2**w``, with its factors.

    Computed by a shift, never by enumerating the retained register.
    """
    if not isinstance(raw, RawDomainAccounting):
        raise InertEvaluatorError("raw must come from raw_domain_accounting")
    if isinstance(tie_count, bool) or not isinstance(tie_count, int):
        raise InertEvaluatorError("tie_count must be an int")
    if not 0 <= tie_count <= raw.base:
        raise InertEvaluatorError("tie_count must lie between the empty and full domain")
    return tie_count << raw.w, (tie_count, raw.w)


def _decoded_masks(context: ConditionContext) -> Iterator[int]:
    """Every decoded bit string, in the frozen lexicographic display order."""
    for mask in range(1 << context.width()):
        yield mask


def mask_to_bits(mask: int, width: int) -> tuple[int, ...]:
    return tuple((mask >> (width - 1 - index)) & 1 for index in range(width))


def active_lifts(
    context: ConditionContext,
    x: tuple[int, ...],
    decoded: PreparedDecodedState | None = None,
) -> tuple[tuple[int, ...], tuple[FamilyPenalty, ...], float, float, FamilyPenalty]:
    """The active-lift words of one decoded state, plus ``f`` and ``P_card``.

    An active family's register is pinned to its exact minimiser -- at most two
    words.  An inactive family's register is RETAINED and therefore absent from
    this tuple entirely: it is not enumerated, it is counted symbolically by
    :func:`raw_domain_accounting`.
    """
    if not isinstance(context, ConditionContext):
        raise InertEvaluatorError("context must come from prepare_condition")
    if decoded is None:
        decoded = fast_decoded_state(context, x)
    sector_active = "sector" in context.active_families
    budget_active = "budget" in context.active_families
    words: list[int] = []
    sector: list[FamilyPenalty] = []
    for j in range(SECTOR_COUNT):
        if sector_active:
            values = exact_register_minimisers(decoded.h_sector[j], (1 << SECTOR_SLACK_BITS) - 1)
            sector.append(
                family_penalty(
                    f"sector[{j}]",
                    True,
                    decoded.h_sector[j],
                    context.coefficients.sector_slack,
                    SECTOR_SLACK_BITS,
                )
            )
        else:
            values = ()
            sector.append(
                family_penalty(
                    f"sector[{j}]", False, decoded.h_sector[j], +0.0, SECTOR_SLACK_BITS
                )
            )
        words.append(min(values) if values else 0)
    if budget_active:
        budget_values = exact_register_minimisers(
            decoded.h_budget, (1 << BUDGET_SLACK_BITS) - 1
        )
        budget = family_penalty(
            "budget", True, decoded.h_budget, context.coefficients.budget_slack, BUDGET_SLACK_BITS
        )
    else:
        budget_values = ()
        budget = family_penalty(
            "budget", False, decoded.h_budget, +0.0, BUDGET_SLACK_BITS
        )
    words.append(min(budget_values) if budget_values else 0)
    p_card = _finite(context.coefficients.alpha * decoded.card_square, "P_card")
    return tuple(words), tuple(sector), decoded.f_value, p_card, budget


def iter_candidate_lifts(
    context: ConditionContext, transcript: DecodedTranscript | None = None
) -> Iterator[tuple[tuple[int, ...], float, float, tuple[FamilyPenalty, ...], FamilyPenalty]]:
    """Walk every ACTIVE lift of ``C_E``, never the retained register.

    The yielded count is exactly ``base``; the retained inactive register is
    accounted for by :func:`raw_domain_accounting`, so the raw ``2**39`` domain
    is never materialised.  This is D015 section 5.3's tractable ``O(2^20)``
    path.
    """
    if not isinstance(context, ConditionContext):
        raise InertEvaluatorError("context must come from prepare_condition")
    if transcript is None:
        transcript = prepare_transcript(context)
    for index in range(len(transcript)):
        x = mask_to_bits(transcript.mask[index], context.width())
        words, sector, f_value, p_card, budget = active_lifts(
            context, x, transcript.as_decoded_state(index)
        )
        del words
        yield x, f_value, p_card, sector, budget


# --------------------------------------------------------------------------- #
# Grid-independent, condition-independent decoded transcript
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DecodedTranscript:
    """The section 5.2 intermediates for every decoded state, computed once.

    These values depend on the instance alone -- not on the condition, not on
    the grid coordinate -- so all four D013 conditions share one transcript.
    This is the same grid-independence ``src/g5.domains.prepare_unbalanced_domain``
    relies on, and it is what keeps the four-condition evaluation tractable.

    The arrays are indexed by decoded mask, i.e. in the frozen lexicographic
    display order of the displayed ``x`` bits.
    """

    width: int
    f: tuple[float, ...]
    h_card: tuple[float, ...]
    card_square: tuple[float, ...]
    h_sector: tuple[tuple[float, ...], ...]
    sector_square: tuple[tuple[float, ...], ...]
    h_budget: tuple[float, ...]
    budget_square: tuple[float, ...]
    mask: tuple[int, ...]

    def __len__(self) -> int:
        return len(self.mask)

    def as_decoded_state(self, index: int) -> PreparedDecodedState:
        """The transcript entry as the frozen prepared-state record."""
        return PreparedDecodedState(
            f_value=self.f[index],
            h_card=self.h_card[index],
            card_square=self.card_square[index],
            h_sector=tuple(column[index] for column in self.h_sector),
            sector_square=tuple(column[index] for column in self.sector_square),
            h_budget=self.h_budget[index],
            budget_square=self.budget_square[index],
        )


def prepare_transcript(context: ConditionContext) -> DecodedTranscript:
    """Compute the whole instance's decoded transcript exactly once.

    Uses :func:`fast_decoded_state`, whose bit-identity with the frozen
    ``src.g4.energy.prepare_decoded_state`` the fixture pins over the entire
    decoded domain.  The per-state value function is hoisted out of the loop
    and the states are collected in plain tuples first, so the hot path builds
    no short-lived objects beyond the returned value itself.
    """
    if not isinstance(context, ConditionContext):
        raise InertEvaluatorError("context must come from prepare_condition")
    width = context.width()
    fast = fast_decoded_state
    states = [fast(context, mask_to_bits(mask, width)) for mask in _decoded_masks(context)]
    return _transcript_from_states(width, states)


def _transcript_from_states(width: int, states: list) -> DecodedTranscript:
    """Pack a list of prepared states into the shared transcript.

    Kept separate so a caller that has already built its own state list -- the
    independent fixture reference does exactly this -- can be compared against
    the evaluator without reusing the evaluator's own assembly.
    """
    return DecodedTranscript(
        width=width,
        f=tuple(state.f_value for state in states),
        h_card=tuple(state.h_card for state in states),
        card_square=tuple(state.card_square for state in states),
        h_sector=tuple(
            tuple(state.h_sector[j] for state in states) for j in range(SECTOR_COUNT)
        ),
        sector_square=tuple(
            tuple(state.sector_square[j] for state in states) for j in range(SECTOR_COUNT)
        ),
        h_budget=tuple(state.h_budget for state in states),
        budget_square=tuple(state.budget_square for state in states),
        mask=tuple(range(len(states))),
    )


# --------------------------------------------------------------------------- #
# D015 tolerance and the certified result
# --------------------------------------------------------------------------- #


def _frozen_tau(y: object, y_prime: object, lambda_ref: object, c: object) -> float:
    """The frozen ``src.g4.energy.tau``, typed at this module's boundary.

    Ruling (1) then (2): the four numeric arguments are type-checked **before**
    they are handed to the frozen function, so a non-numeric ``y``/``y'``/
    ``Lambda_ref``/``c`` is refused here rather than reaching the frozen
    ``math.isfinite``, which would raise an untyped ``TypeError``.  The call
    itself is then wrapped, because the frozen ``tau`` raises plain
    ``ValueError`` on a nonpositive ``Lambda_ref`` or ``c``.
    """
    for label, value in (
        ("y", y),
        ("y'", y_prime),
        ("Lambda_ref", lambda_ref),
        ("c_h", c),
    ):
        _require_real_number(value, f"tau {label}")
    return _delegated(
        "frozen src.g4.energy.tau",
        lambda: frozen_energy.tau(y, y_prime, lambda_ref, c),
    )


def tau(context: ConditionContext, y: float, y_prime: float) -> float:
    """D015's scale, delegating to the frozen ``src.g4.energy.tau``."""
    return _frozen_tau(y, y_prime, context.lambda_ref, context.c_h)


@dataclass(frozen=True)
class ConditionResult:
    """Everything D013/D015/D016 require for one condition at one coordinate."""

    condition: str
    active_families: tuple[str, ...]
    inactive_families: tuple[str, ...]
    active_penalty_axes: int
    h_e_min: float
    z_ref: tuple[int, ...]
    min_words: tuple[tuple[int, ...], ...]
    min_x: tuple[tuple[int, ...], ...]
    tie_set: tuple[tuple[int, ...], ...]
    x_e: tuple[tuple[int, ...], ...]
    t_e_size: int
    t_e_factors: tuple[int, int]
    raw_domain: RawDomainAccounting
    optimum: ObjectiveOptimum
    atomic_labels: tuple[tuple[tuple[int, ...], str], ...]
    primary_label: str
    census: dict[str, int]
    label_counts: dict[str, int]
    #: Number of inactive contributions observed. Recorded so a fixture can
    #: assert the count is nonzero and a mutation that stops producing them is
    #: visible; it is a tally, not a self-issued certificate.
    inactive_contributions: int
    #: Accumulator bit patterns observed immediately before each inactive
    #: addition, paired with the accumulator bit pattern immediately after. The
    #: fixture recomputes the no-addition control and compares.
    inert_additions: tuple[tuple[int, int], ...]


def _energies(
    context: ConditionContext, transcript: DecodedTranscript
) -> tuple[list[float], list[tuple[int, ...]], int, list[tuple[int, int]]]:
    """``H_E`` for every active lift, in the frozen lexicographic display order.

    Also returns the number of inactive additions performed and the recorded
    before/after accumulator bit patterns, aggregated over the whole walk.
    """
    values: list[float] = []
    owners: list[tuple[int, ...]] = []
    inert: list[tuple[int, int]] = []
    inert_count = 0
    for x, f_value, p_card, sector, budget in iter_candidate_lifts(context, transcript):
        h_e, _, state_inert, state_count = _accumulate(f_value, p_card, sector, budget)
        _require(
            bits_of(h_e) != NEGATIVE_ZERO_PATTERN or h_e != 0.0,
            "H_E must never be the negative zero",
        )
        values.append(h_e)
        owners.append(x)
        inert.extend(state_inert)
        inert_count += state_count
    if not values:
        raise InertEvaluatorError("the active-lift walk produced no candidate")
    return values, owners, inert_count, inert


def evaluate_condition(
    context: ConditionContext, transcript: DecodedTranscript | None = None
) -> ConditionResult:
    """Evaluate one condition end to end at one grid coordinate.

    Order of operations matters for the hard-stop rule: ``f*_q`` is resolved
    *before* any tie set, label or count is constructed, so an empty ``F_q``
    writes nothing.  ``transcript`` is the shared, grid-independent decoded
    ledger; supply it to evaluate several conditions without recomputing it.
    """
    if not isinstance(context, ConditionContext):
        raise InertEvaluatorError("context must come from prepare_condition")
    if transcript is None:
        transcript = prepare_transcript(context)
    width = context.width()
    state_list = tuple(
        mask_to_bits(transcript.mask[index], width) for index in range(len(transcript))
    )
    optimum = objective_optimum(context, state_list, transcript)
    values, owners, inert_count, inert = _energies(context, transcript)
    base = len(values)
    raw = raw_domain_accounting(context, base)

    h_e_min = min(values)
    # The D015 tolerance is delegated to the frozen src.g4.energy.tau, and the
    # local implementation of the same formula is cross-checked against it so a
    # drift in either is a refusal rather than a silent disagreement.
    reference_tau = _finite(
        _frozen_tau(h_e_min, h_e_min, context.lambda_ref, context.c_h), "tau"
    )
    _require(reference_tau > 0.0, "the D015 tolerance must be strictly positive")
    local_tau = _finite(
        (context.c_h * EPSILON) * (context.lambda_ref + abs(h_e_min)), "tau"
    )
    _require(
        local_tau == reference_tau and bits_of(local_tau) == bits_of(reference_tau),
        "the evaluator's tolerance disagrees with the frozen src.g4.energy.tau",
    )

    minimum_indices = [index for index, value in enumerate(values) if value == h_e_min]
    min_x = tuple(dict.fromkeys(owners[index] for index in minimum_indices))
    tie_indices = []
    for index, value in enumerate(values):
        gap = abs(_finite(value - h_e_min, "gap"))
        if gap <= _finite(
            _frozen_tau(value, h_e_min, context.lambda_ref, context.c_h), "tau"
        ):
            tie_indices.append(index)
    tie_set = tuple(owners[index] for index in tie_indices)
    # Every exact minimum candidate is in T_E; a miss would fail certification.
    _require(
        set(minimum_indices) <= set(tie_indices),
        "T_E must include every exact minimum candidate",
    )
    x_e = tuple(dict.fromkeys(tie_set))
    _require(x_e, "X_E must be nonempty")

    # |T_E| is the tied count times the retained register multiplicity. It is a
    # different quantity from |C_E|: the domain holds every active lift, while
    # T_E holds only the tied ones. Both are recorded with their own factors.
    t_e_size, t_e_factors = t_e_accounting(raw, len(tie_indices))
    _require(
        t_e_factors[1] == raw.w and t_e_factors[0] == len(tie_indices),
        "|T_E| must carry the retained register width",
    )

    # Canonical argmin: the first raw candidate in the display order attaining
    # H_E,min.  An inactive register is free, so its canonical word is all-zero.
    z_ref = _canonical_argmin(context, owners, tie_indices, transcript)

    classifier = _delegated(
        "frozen src.g4.classification.DecodedClassifier",
        lambda: DecodedClassifier(
            optimum_service=OriginalObjectiveService(
                objective=lambda state: fast_decoded_state(context, state).f_value,
                lambda_ref=context.lambda_ref,
            ),
            feasible=lambda state: feasible_q(context, state),
        ),
    )
    atomic = tuple(
        (x, _delegated("frozen src.g4.classification.DecodedClassifier.label",
                        lambda x=x: classifier.label(x, optimum.f_star)))
        for x in x_e
    )
    primary = _delegated(
        "frozen src.g4.classification.DecodedClassifier.label_set",
        lambda: classifier.label_set(x_e, optimum.f_star),
    )
    label_counts = {"A": 0, "B": 0, "C": 0}
    for _, label in atomic:
        label_counts[label] += 1
    denominator = len(x_e)
    census = {
        "I_C_exist": 1 if any(label == "C" for _, label in atomic) else 0,
        "I_C_univ": 1 if all(label == "C" for _, label in atomic) else 0,
        "p_A": label_counts["A"] / denominator,
        "p_B": label_counts["B"] / denominator,
        "p_C": label_counts["C"] / denominator,
    }
    return ConditionResult(
        condition=context.condition,
        active_families=context.active_families,
        inactive_families=context.inactive_families,
        active_penalty_axes=context.active_penalty_axes,
        h_e_min=h_e_min,
        z_ref=z_ref,
        min_words=min_x,
        min_x=min_x,
        tie_set=tie_set,
        x_e=x_e,
        t_e_size=t_e_size,
        t_e_factors=t_e_factors,
        raw_domain=raw,
        optimum=optimum,
        atomic_labels=atomic,
        primary_label=primary,
        census=census,
        label_counts=label_counts,
        inactive_contributions=inert_count,
        inert_additions=tuple(inert),
    )


def _canonical_argmin(
    context: ConditionContext,
    owners: Sequence[tuple[int, ...]],
    tie_indices: Sequence[int],
    transcript: DecodedTranscript,
) -> tuple[int, ...]:
    """``z_ref``: the first raw candidate in the display order attaining H_E,min.

    The display order is the displayed ``x`` bits followed by the auxiliary
    bits.  An inactive register is unconstrained, so the lexicographically first
    candidate in the tie carries the all-zero word there; an active register
    carries its smallest exact minimiser.
    """
    if not tie_indices:
        raise InertEvaluatorError("cannot form a canonical argmin from an empty tie set")
    first = min(tie_indices)
    x = owners[first]
    width = context.width()
    mask = 0
    for index, bit in enumerate(x):
        if bit:
            mask |= 1 << (width - 1 - index)
    decoded = transcript.as_decoded_state(transcript.mask.index(mask))
    sector_active = "sector" in context.active_families
    budget_active = "budget" in context.active_families
    words: list[int] = []
    for j in range(SECTOR_COUNT):
        if sector_active:
            words.append(
                min(
                    exact_register_minimisers(
                        decoded.h_sector[j], (1 << SECTOR_SLACK_BITS) - 1
                    )
                )
            )
        else:
            words.append(0)
    if budget_active:
        words.append(
            min(exact_register_minimisers(decoded.h_budget, (1 << BUDGET_SLACK_BITS) - 1))
        )
    else:
        words.append(0)
    return x + tuple(words)
