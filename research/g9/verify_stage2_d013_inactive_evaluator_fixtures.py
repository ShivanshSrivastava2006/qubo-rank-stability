"""Synthetic-only fixtures for the WP6 D013 ``+0.0`` inactive-family evaluator.

Non-scientific. Every instance is synthetic and built here; no real candidate,
instance artifact, ground truth, D013 trigger, ablation run, device or network
is used, and nothing is written to disk. Gate-9 section B remains **OPEN**.

Run with ``python3 -B`` and ``python3 -B -O``. Checks are explicit ``require``
calls that raise, never bare ``assert``, so ``-O`` cannot remove one.

No check is an existence or ``hasattr`` test. Every one compares a computed
value against an independently computed value.

Instance widths
---------------
Two widths are used, for two different reasons.

* **20 tickers, the Scope-locked width.**  Used only for the CSB frozen
  bit-identity fixture, which is meaningless anywhere else: the frozen ledger it
  compares against is itself bound to 20 tickers and 4 sectors.  The decoded
  domain is the full ``2**20``.
* **8 tickers, 4 sectors of 2.**  Used for everything else.  The whole D013
  machinery is width-independent -- every predicate, penalty, register,
  tolerance and label reads the same way -- so an 8-ticker synthetic instance
  exercises all of it.  It is small enough that the independent slow reference
  can afford a *complete* register scan per state, which is what makes that
  reference a genuine check rather than a restatement of the evaluator's own
  closed-form register minimiser.

The independent slow reference
------------------------------
:func:`slow_reference` shares no code with the evaluator.  It:

* walks the decoded domain as a plain list of integers, not through
  ``src.g4.energy`` preparation services;
* finds each active family's exact register minimiser by **exhaustively
  scanning every register value**, where the evaluator uses a closed form;
* builds each ``S_acc`` from a weight list with its own loop;
* recomputes ``f*_q``, ``H_E,min``, the canonical argmin, the tie set, ``X_E``,
  the A/B/C labels and ``|T_E|`` from those per-family sums.

The fixture then requires exact agreement, and for the energies specifically it
requires agreement on the binary64 **bit pattern**, not on ``==`` alone.
"""

from __future__ import annotations

import ast
import math
import os
import struct
import sys
from pathlib import Path

if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
    raise SystemExit("PYTHONDONTWRITEBYTECODE=1 required")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.g4 import energy as frozen_energy
from src.g4.energy import prepare_decoded_state
from src.g4.instance import Instance
from src.g4.parameters import Coefficients

from research.g9 import stage2_d013_inactive_evaluator as ev

FROZEN_WIDTH = 20
SMALL_WIDTH = 8
SMALL_SECTORS = ((0, 1), (2, 3), (4, 5), (6, 7))
SECTOR = 4
POS_ZERO = 0x0000000000000000
NEG_ZERO = 0x8000000000000000


def require(condition: object, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def pattern(value: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def is_negative_zero(value: float) -> bool:
    return value == 0.0 and math.copysign(1.0, value) < 0.0


ACTIVE_LEDGER = {
    "alpha": 1.5,
    "sector_slack": 2.0,
    "budget_slack": 3.0,
    "sector_linear": 0.5,
    "sector_quadratic": 0.75,
    "budget_linear": 0.25,
    "budget_quadratic": 0.4,
}
LAMBDA_REF = 120.0


def build_instance(mu, prices, K, C, B, width, sectors, sigma=None) -> Instance:
    if sigma is None:
        sigma = tuple(tuple(0.0 for _ in range(width)) for _ in range(width))
    return Instance(
        tickers=tuple(f"SYN{i:02d}" for i in range(width)),
        sectors=sectors,
        mu=tuple(float(v) for v in mu),
        sigma=tuple(tuple(float(v) for v in row) for row in sigma),
        prices=tuple(float(p) for p in prices),
        kappa_risk=2.5,
        K=K,
        C=C,
        B=float(B),
    )


def spread_sigma(width: int):
    """A non-degenerate, asymmetric Sigma whose sums genuinely round.

    With ``Sigma = 0`` every penalty is a clean integer or dyadic square, and
    floating-point addition is commutative, so the D015 accumulation order
    would be untestable.  These values are deliberately of mixed magnitude so
    partial sums round differently depending on the order they are added in.
    """
    rows = []
    for i in range(width):
        row = []
        for k in range(width):
            if i == k:
                row.append(0.0137 + 0.0021 * i)
            else:
                row.append((0.0007 * ((i + 3 * k) % 11 + 1)) * (1.0 if (i + k) % 2 else -0.5))
        rows.append(tuple(row))
    return tuple(rows)


#: ``flat`` -- every ticker identical, so f depends only on the cardinality and
#: all K-subsets attain one exact binary64 value: a real, large tie set.
FLAT = build_instance([-1.0] * SMALL_WIDTH, [1] * SMALL_WIDTH, 3, 1, 5.0, SMALL_WIDTH, SMALL_SECTORS)

#: ``budget_c`` -- distinct dyadic mu, so the f-minimiser is unique and it
#: VIOLATES the active budget.  D016 must label it C.
BUDGET_C = build_instance(
    [-(2.0**e) for e in range(SMALL_WIDTH)],
    [1, 1, 2, 2, 3, 3, 4, 4],
    2,
    1,
    3.0,
    SMALL_WIDTH,
    SMALL_SECTORS,
)

#: ``grouped`` -- four groups of two with halving mu, so f is an exact function
#: of the per-group counts: a tie set whose members differ in feasibility.
GROUPED = build_instance(
    [-1.0, -1.0, -2.0, -2.0, -4.0, -4.0, -8.0, -8.0],
    [1] * SMALL_WIDTH,
    2,
    1,
    3.0,
    SMALL_WIDTH,
    SMALL_SECTORS,
)

#: ``sector_c`` -- the f-minimiser is unique and violates an active *sector*
#: capacity, so the C label arises from the sector family rather than budget.
#: ``C = 1`` admits one name per sector, so ``F_q`` stays nonempty for every
#: condition while the f-minimiser (which takes both names of a group) is
#: sector-infeasible.
SECTOR_C = build_instance(
    [-1.0, -1.0, -2.0, -2.0, -4.0, -4.0, -8.0, -8.0],
    [1] * SMALL_WIDTH,
    2,
    1,
    9.0,
    SMALL_WIDTH,
    SMALL_SECTORS,
)

#: ``mixed_sigma`` -- a non-degenerate Sigma, so the D015 accumulation order is
#: load-bearing (with ``Sigma = 0`` every penalty is an exact square and binary64
#: addition is commutative, which would make the order untestable).  Its prices
#: are **fractional**, so ``p^T x`` and hence ``h_budget`` are non-integral on
#: most states.  That matters: with integral prices every budget residual is an
#: exact integer, and any rounding of it would be invisible.  With fractional
#: prices the budget residual is a genuinely rounded binary64 value, so the
#: residual transcript is pinned bit for bit.
MIXED_SIGMA = build_instance(
    [-1.0, -1.0, -2.0, -2.0, -4.0, -4.0, -8.0, -8.0],
    [1.25, 2.5, 3.75, 4.125, 5.5, 6.25, 7.875, 8.0],
    2,
    1,
    9.0,
    SMALL_WIDTH,
    SMALL_SECTORS,
    sigma=spread_sigma(SMALL_WIDTH),
)

#: ``zero_accumulator`` -- built so that ``f + P_card`` is *exactly* ``+0.0``
#: for the empty portfolio: ``Sigma = 0`` so the quadratic transcript adds
#: nothing, ``K = 0`` so ``h_card = 0`` and ``P_card = +0.0``, and ``f = +0.0``
#: for the empty portfolio because every ``mu_term`` is a zero term.  The
#: accumulator entering the first inactive addition is therefore the positive
#: zero, which is the one state in which ``fl(+0.0 + +0.0)`` and
#: ``fl(+0.0 + -0.0)`` differ.  Without this instance the positive-zero
#: requirement would never be exercised where it is decisive.
ZERO_ACCUMULATOR = build_instance(
    [-1.0] * SMALL_WIDTH, [1] * SMALL_WIDTH, 0, 1, 5.0, SMALL_WIDTH, SMALL_SECTORS
)

SMALL_INSTANCES = (
    ("flat", FLAT),
    ("budget_c", BUDGET_C),
    ("grouped", GROUPED),
    ("sector_c", SECTOR_C),
    ("mixed_sigma", MIXED_SIGMA),
)
#: Instances on which the general per-condition fixtures run.
EVALUATED_INSTANCES = SMALL_INSTANCES + (("zero_accumulator", ZERO_ACCUMULATOR),)

#: The Scope-locked 20-ticker instance used for the frozen CSB energy
#: comparison.  ``B`` is an integer and ``C`` is an integer, so the frozen
#: ``exact_slack_lift`` -- which admits a register only when the residual is
#: *exactly* an integer -- yields a lift for essentially every state, and the
#: whole ``2**20`` domain is compared against the frozen ``slack_energy``.
FROZEN_INSTANCE = build_instance(
    [-1.0] * FROZEN_WIDTH,
    [1] * FROZEN_WIDTH,
    3,
    1,
    5.0,
    FROZEN_WIDTH,
    tuple(tuple(range(4 * j, 4 * j + 4)) for j in range(SECTOR)),
    sigma=spread_sigma(FROZEN_WIDTH),
)

#: A second Scope-locked 20-ticker instance with a **non-integral** sector
#: capacity, so the frozen register minimiser is two-valued on many states.
#: The frozen ``exact_slack_lift`` correctly refuses a lift there, so this
#: instance is used only for the domain comparison, where the frozen
#: ``build_slack_domain_cache`` is the authority and its lift multiplicity is
#: the thing under test.
FROZEN_TIE_INSTANCE = build_instance(
    [-1.0] * FROZEN_WIDTH,
    [1] * FROZEN_WIDTH,
    3,
    0.5,
    5.0,
    FROZEN_WIDTH,
    tuple(tuple(range(4 * j, 4 * j + 4)) for j in range(SECTOR)),
    sigma=spread_sigma(FROZEN_WIDTH),
)


# --------------------------------------------------------------------------- #
# Independent slow reference: a second implementation, sharing no code
# --------------------------------------------------------------------------- #

WEIGHTS = {1: (), 2: (1.0,), 11: tuple(float(1 << d) for d in range(11))}


def _ref_family_penalty(coef: float, residual: float, width: int):
    """``(penalty, lift_multiplier)`` for one family, by exhaustive scan.

    An active family is scored by walking **every** register value in the family
    and keeping the exact minimum square.  The evaluator instead uses a closed
    form, so agreement between the two is a real check on that closed form and
    not a restatement of it.  An inactive family returns ``+0.0`` and its full
    register width as a lift multiplier, with no scan at all.
    """
    if coef != 0.0:
        weights = WEIGHTS[width]
        best = None
        for value in range(1 << width):
            register = 0.0
            for d, weight in enumerate(weights):
                register = register + (weight * float((value >> d) & 1))
            delta = residual - register
            square = delta * delta
            if best is None or square < best:
                best = square
        return coef * best, 1
    return 0.0, 1 << width


def slow_reference(inst: Instance, condition: str, ledger: dict):
    """Independent evaluation of one condition, written from the definitions."""
    width = len(inst.tickers)
    active = ev.family_activity(condition)
    sector_coef = ledger["sector_slack"] if active["sector"] else 0.0
    budget_coef = ledger["budget_slack"] if active["budget"] else 0.0

    def objective(x: list[int]) -> float:
        acc = 0.0
        for i in range(width):
            acc = acc + (-(inst.mu[i] * float(x[i])))
        for i in range(width):
            for k in range(width):
                inner = (inst.sigma[i][k] * float(x[i])) * float(x[k])
                acc = acc + (inst.kappa_risk * inner)
        return acc

    def residuals(x: list[int]):
        card = 0.0
        for i in range(width):
            card = card + float(x[i])
        h_sector = []
        for members in inst.sectors:
            total = 0.0
            for i in sorted(members):
                total = total + float(x[i])
            h_sector.append(float(inst.C) - total)
        spend = 0.0
        for i in range(width):
            spend = spend + (inst.prices[i] * float(x[i]))
        return card - float(inst.K), h_sector, inst.B - spend

    def feasible(x: list[int]) -> bool:
        h_card, h_sector, h_budget = residuals(x)
        if h_card != 0.0:
            return False
        if active["sector"] and any(value < 0.0 for value in h_sector):
            return False
        if active["budget"] and h_budget < 0.0:
            return False
        return True

    energies = []
    objectives = []
    feasibilities = []
    for value in range(1 << width):
        x = [(value >> (width - 1 - i)) & 1 for i in range(width)]
        h_card, h_sector, h_budget = residuals(x)
        p_card = ledger["alpha"] * (h_card * h_card)
        sector_penalties = [
            _ref_family_penalty(sector_coef, h_sector[j], 2) for j in range(SECTOR)
        ]
        budget_penalty, _ = _ref_family_penalty(budget_coef, h_budget, 11)
        acc = objective(x)
        acc = acc + p_card
        for penalty, _mult in sector_penalties:
            acc = acc + penalty
        acc = acc + budget_penalty
        energies.append(acc)
        objectives.append(objective(x))
        feasibilities.append(feasible(x))

    feasible_values = [v for v in range(1 << width) if feasibilities[v]]
    if not feasible_values:
        raise ev.InertEvaluatorError(f"F_{condition} is empty in the slow reference too")
    best_f = min(objectives[v] for v in feasible_values)
    f_argmins = tuple(v for v in feasible_values if objectives[v] == best_f)
    h_min = min(energies)
    epsilon = math.ldexp(1.0, -52)
    tol = (2048.0 * epsilon) * (LAMBDA_REF + abs(h_min))
    ties = tuple(v for v in range(1 << width) if abs(energies[v] - h_min) <= tol)

    def decoded(value: int) -> tuple[int, ...]:
        return tuple((value >> (width - 1 - i)) & 1 for i in range(width))

    def label_of(value: int) -> str:
        if not feasibilities[value]:
            return "C"
        gap = abs(objectives[value] - best_f)
        scale = (2048.0 * epsilon) * (
            LAMBDA_REF + max(abs(objectives[value]), abs(best_f))
        )
        return "A" if gap <= scale else "B"

    x_e = tuple(dict.fromkeys(decoded(v) for v in ties))
    atomic = tuple((decoded(v), label_of(v)) for v in ties)
    dedup_atomic = tuple(dict.fromkeys(atomic))
    labels = [label for _, label in dedup_atomic]
    if "C" in labels:
        primary = "C"
    elif labels and all(label == "A" for label in labels):
        primary = "A"
    else:
        primary = "B"
    w = (0 if active["sector"] else SECTOR * 2) + (0 if active["budget"] else 11)
    return {
        "f_star": best_f,
        "f_star_bits": pattern(best_f),
        "x_ref": decoded(f_argmins[0]),
        "f_argmin_count": len(f_argmins),
        "feasible_count": len(feasible_values),
        "h_min": h_min,
        "h_min_bits": pattern(h_min),
        "canonical_argmin": decoded(ties[0]),
        "tie_set": tuple(decoded(v) for v in ties),
        "x_e": x_e,
        "atomic": dedup_atomic,
        "primary": primary,
        "t_e_size": len(ties) << w,
        "t_e_factors": (len(ties), w),
    }


# --------------------------------------------------------------------------- #
# Fixture 1 -- CSB reproduces the frozen authority bit-for-bit
# --------------------------------------------------------------------------- #

#: The full ``2**20`` domain stride for the two frozen-authority CSB fixtures.
#: It is ``1`` and is asserted to be ``1`` by
#: ``require_full_domain_coverage``; it exists as a named constant so that the
#: mutation sweep has a single, obvious thing to break -- and breaking it makes
#: the fixtures FAIL rather than silently comparing fewer states.
DOMAIN_MASK_LIMIT = 1


# --------------------------------------------------------------------------- #

def require_full_domain_coverage(fixture: str) -> None:
    """Refuse any attempt to run a full-domain fixture over a subset.

    The two CSB fixtures are the *only* full ``2**20`` authority comparisons in
    the suite, and the mutation sweep needs to run the suite dozens of times.
    Allowing an external override here would mean a strided run could be
    mistaken for a full-domain one, so the coverage is asserted unconditionally
    and the sweep instead reduces the *authority* fixtures it disables.
    """
    for variable, value in sorted(globals().items()):
        if variable.startswith("WP6_") and "STRIDE" in variable:
            require(
                value == 1,
                f"{fixture} is a full-2**20 authority comparison and must not be "
                f"strided, but {variable} = {value}; a partial sweep would "
                f"silently weaken the frozen-authority proof",
            )
    require(
        DOMAIN_MASK_LIMIT == 1,
        f"the full-domain comparison was limited to every "
        f"{DOMAIN_MASK_LIMIT}th state; that is a weakened run, not a full one",
    )


def fixture_csb_frozen_bit_identical() -> None:
    """CSB equals ``src.g4.energy`` bit-for-bit over the full ``2**20`` domain.

    Compared against the frozen entry points themselves, not a re-implementation:
    ``prepare_decoded_state`` for the transcript, and ``slack_energy`` at the
    frozen exact lift for the assembled ``H_E``.
    """
    require_full_domain_coverage("fixture_csb_frozen_bit_identical")
    inst = FROZEN_INSTANCE
    context = ev.prepare_condition(inst, "CSB", ACTIVE_LEDGER, LAMBDA_REF)
    require(context.active_families == ("sector", "budget"), "CSB must be all-active")
    require(context.inactive_families == (), "CSB must have no inactive family")
    require(context.inactive_width == 0, "CSB must have w == 0")
    require(context.active_penalty_axes == 3, "CSB must have three active axes")
    frozen_coefficients = Coefficients(**ACTIVE_LEDGER)
    prepared = frozen_energy.prepare_instance(inst)

    compared = 0
    for value in range(1 << FROZEN_WIDTH):
        x = ev.mask_to_bits(value, FROZEN_WIDTH)
        mine = ev.fast_decoded_state(context, x)
        theirs = prepare_decoded_state(prepared, x)
        require(
            mine == theirs,
            f"CSB transcript disagrees with the frozen preparation at mask {value}",
        )
        require(
            pattern(mine.f_value) == pattern(theirs.f_value),
            f"CSB f is not bit-identical to the frozen ledger at mask {value}",
        )
        try:
            lift = frozen_energy.exact_slack_lift(inst, x)
        except ValueError:
            continue  # residual outside the register range: not a C_slack lift
        frozen_h = frozen_energy.slack_energy(inst, x, lift, frozen_coefficients)
        ledger = ev.state_ledger(context, x)
        require(
            pattern(ledger.h_e) == pattern(frozen_h),
            f"CSB H_E is not bit-identical to frozen slack_energy at mask {value}: "
            f"{ledger.h_e!r} vs {frozen_h!r}",
        )
        compared += 1
    require(compared > 0, "CSB H_E was compared against the frozen lift on no state")


def fixture_csb_frozen_domain_and_reconstruction() -> None:
    """CSB reproduces the frozen G5 slack domain cache, lift for lift.

    ``src/g5/domains.build_slack_domain_cache`` refuses any non-``(True, True)``
    activity signature, so the frozen cache exists only for the all-active CSB
    case.  That makes it the right frozen authority for the *domain*: the
    evaluator's active lifts must be exactly the cache's exact-minimiser lifts,
    in the same order, for the whole decoded domain.

    The frozen *unbalanced* ledger is deliberately **not** compared against
    here.  Slack and unbalanced are two different encodings of the same
    objective and their ``H_E`` values are not equal -- that is the whole point
    of the encoding comparison -- so demanding bit-identity between them would
    be a false requirement.  This fixture instead pins that the evaluator
    tracks the frozen **slack** encoding, and records that it differs from the
    unbalanced one.
    """
    inst = FROZEN_TIE_INSTANCE
    require_full_domain_coverage("fixture_csb_frozen_domain_and_reconstruction")
    context = ev.prepare_condition(inst, "CSB", ACTIVE_LEDGER, LAMBDA_REF)
    frozen_coefficients = Coefficients(**ACTIVE_LEDGER)
    from src.g5.domains import build_slack_domain_cache

    cache = build_slack_domain_cache(inst, frozen_coefficients)
    require(
        cache.activity_signature == (True, True),
        "the frozen cache is the all-active CSB domain",
    )
    require(
        cache.require_canonical_energy_layout() is None,
        "the frozen cache must accept the canonical energy layout",
    )
    require(
        cache.decoded_width == FROZEN_WIDTH
        and cache.sector_slack_bits == 2
        and cache.budget_slack_bits == 11
        and cache.auxiliary_width == 19,
        f"the frozen cache must carry the Scope-locked register layout: {cache}",
    )

    # Lift for lift, in the frozen cache's own order, over the whole domain.
    # The cache is the frozen authority on *which registers are exact
    # minimisers*; the per-state energy equality against ``slack_energy`` is
    # checked by the previous fixture on the lift-representable instance.
    cache_index = 0
    multi_lift_states = 0
    cache_bounds: dict[int, tuple[int, int]] = {}
    for value in range(1 << FROZEN_WIDTH):
        x = ev.mask_to_bits(value, FROZEN_WIDTH)
        require(
            cache[cache_index][0] == x,
            f"the frozen cache order diverged at index {cache_index}: "
            f"{cache[cache_index][0]} is not mask {value}",
        )
        start = cache_index
        state_words = []
        while cache_index < len(cache) and cache[cache_index][0] == x:
            state_words.append(cache[cache_index][1])
            cache_index += 1
        cache_bounds[value] = (start, cache_index)
        require(
            state_words,
            f"the frozen cache supplied no exact-minimiser lift for mask {value}",
        )
        for word in state_words:
            require(
                len(word) == 19,
                f"a frozen cache word must be the 19-bit auxiliary register: {word}",
            )
        if len(state_words) > 1:
            multi_lift_states += 1
    require(
        cache_index == len(cache),
        f"the frozen cache has lifts the evaluator never reached: "
        f"{cache_index} of {len(cache)} consumed",
    )
    require(
        multi_lift_states > 0,
        "no state had more than one exact-minimiser register, so the cache's "
        "lift multiplicity was never exercised",
    )
    require(
        len(cache) > (1 << FROZEN_WIDTH),
        "the frozen cache must carry more lifts than there are decoded states, "
        "or the multiplicity claim is not being observed",
    )

    # Every lift the cache holds must be an **exact** minimiser, never a merely
    # near-minimal one -- that is the frozen §5.3 rule.  Verified by exhaustive
    # scan of the family registers, independently of the cache and of the
    # evaluator, on a sample of states that includes multi-lift states.
    def exact_scan(value: int):
        """The exact-minimiser register words, found by scanning every value."""
        x = ev.mask_to_bits(value, FROZEN_WIDTH)
        _h_card, h_sector, h_budget = frozen_energy.residuals(inst, x)
        sector_choices = []
        for residual in h_sector:
            best = None
            chosen = []
            for word in range(4):
                square = (residual - float(word)) ** 2
                if best is None or square < best:
                    best, chosen = square, [word]
                elif square == best:
                    chosen.append(word)
            sector_choices.append(chosen)
        best = None
        chosen = []
        for word in range(1 << 11):
            square = (h_budget - float(word)) ** 2
            if best is None or square < best:
                best, chosen = square, [word]
            elif square == best:
                chosen.append(word)
        words = []
        for a in sector_choices[0]:
            for b in sector_choices[1]:
                for c in sector_choices[2]:
                    for d in sector_choices[3]:
                        for e in chosen:
                            bits = []
                            for value_bits in (a, b, c, d):
                                bits.extend((value_bits & 1, (value_bits >> 1) & 1))
                            bits.extend((e >> i) & 1 for i in range(11))
                            words.append(tuple(bits))
        return tuple(sorted(words))

    sampled_multi = 0
    for value in range(0, 1 << FROZEN_WIDTH, 4001):
        expected_words = exact_scan(value)
        start, stop = cache_bounds[value]
        cache_words = sorted({cache[index][1] for index in range(start, stop)})
        require(
            cache_words == list(expected_words),
            f"the frozen cache's lift set is not the exact-minimiser set at {value}: "
            f"{len(cache_words)} cached vs {len(expected_words)} exact",
        )
        if len(cache_words) > 1:
            sampled_multi += 1
    require(
        sampled_multi > 0,
        "no sampled state had more than one exact minimiser, so the exactness of "
        "the cached lift set was never actually tested",
    )


# --------------------------------------------------------------------------- #
# Fixture 2 -- the independent slow reference
# --------------------------------------------------------------------------- #


def fixture_slow_reference_agreement(inst: Instance, label: str) -> None:
    """Evaluator vs the independent reference, for all four conditions."""
    transcript = None
    for condition in ev.CONDITIONS:
        context = ev.prepare_condition(inst, condition, ACTIVE_LEDGER, LAMBDA_REF)
        if transcript is None:
            transcript = ev.prepare_transcript(context)
        result = ev.evaluate_condition(context, transcript)
        reference = slow_reference(inst, condition, ACTIVE_LEDGER)

        require(
            pattern(result.optimum.f_star) == reference["f_star_bits"],
            f"{label}/{condition}: f*_q bit pattern disagrees with the reference",
        )
        require(
            result.optimum.x_ref == reference["x_ref"],
            f"{label}/{condition}: the canonical x_ref disagrees",
        )
        require(
            len(result.optimum.argmin_set) == reference["f_argmin_count"],
            f"{label}/{condition}: the f*_q argmin set size disagrees",
        )
        require(
            result.optimum.feasible_count == reference["feasible_count"],
            f"{label}/{condition}: |F_q| disagrees",
        )
        require(
            pattern(result.h_e_min) == reference["h_min_bits"],
            f"{label}/{condition}: the H_E,min bit pattern disagrees",
        )
        require(
            result.z_ref[: len(inst.tickers)] == reference["canonical_argmin"],
            f"{label}/{condition}: the canonical argmin word disagrees",
        )
        require(
            result.tie_set == reference["tie_set"],
            f"{label}/{condition}: the tie set disagrees with the reference",
        )
        require(
            result.x_e == reference["x_e"],
            f"{label}/{condition}: X_E disagrees with the reference",
        )
        require(
            result.atomic_labels == reference["atomic"],
            f"{label}/{condition}: the A/B/C atomic labels disagree",
        )
        require(
            result.primary_label == reference["primary"],
            f"{label}/{condition}: the D016 primary label disagrees",
        )
        require(
            result.t_e_size == reference["t_e_size"],
            f"{label}/{condition}: |T_E| disagrees with the reference",
        )
        require(
            result.t_e_factors == reference["t_e_factors"],
            f"{label}/{condition}: the |T_E| factors (base, w) disagree",
        )
        require(
            result.raw_domain.w == reference["t_e_factors"][1],
            f"{label}/{condition}: the retained register width disagrees",
        )
        require(
            result.raw_domain.base == (1 << len(inst.tickers)),
            f"{label}/{condition}: the walk must cover the whole decoded domain",
        )


def fixture_labels_are_actually_exercised() -> None:
    """The synthetic set must reach A, B and C, or the label checks prove nothing."""
    seen = set()
    census_seen = set()
    for label, inst in SMALL_INSTANCES:
        transcript = None
        for condition in ev.CONDITIONS:
            context = ev.prepare_condition(inst, condition, ACTIVE_LEDGER, LAMBDA_REF)
            if transcript is None:
                transcript = ev.prepare_transcript(context)
            result = ev.evaluate_condition(context, transcript)
            for value in result.label_counts.values():
                if value:
                    seen.add(True)
            seen.update(result.label_counts)
            seen.add(result.primary_label)
            census_seen.add((result.census["I_C_exist"], result.census["I_C_univ"]))
    require("A" in seen, "no synthetic instance produced an A label")
    require("C" in seen, "no synthetic instance produced a C label")
    require("B" in seen, "no synthetic instance produced a B label")
    require(
        len(census_seen) >= 1 and all(
            value in (0, 1) for pair in census_seen for value in pair
        ),
        "the I_C indicators must be 0/1",
    )


# --------------------------------------------------------------------------- #
# Fixture 3 -- inactive contributions are exactly +0.0 and are inert
# --------------------------------------------------------------------------- #


def fixture_inactive_is_exact_positive_zero(inst: Instance, label: str) -> None:
    """Each inactive penalty is bit-exactly ``+0.0``, never ``-0.0``, never absent."""
    for condition in ("C", "CB", "CS"):
        context = ev.prepare_condition(inst, condition, ACTIVE_LEDGER, LAMBDA_REF)
        require(
            context.inactive_families != (), f"{condition} must have an inactive family"
        )
        observed = 0
        zero_accumulator_cases = 0
        for value in range(1 << len(inst.tickers)):
            x = ev.mask_to_bits(value, len(inst.tickers))
            ledger = ev.state_ledger(context, x)
            expected = len(ledger.inactive_penalties())
            require(
                expected > 0,
                f"{condition} must have an inactive penalty on every state",
            )
            require(
                ledger.inert_contributions == expected,
                f"{condition} must add and count every inactive family",
            )
            require(
                len(ledger.inert_additions) == expected,
                f"{condition} must route every inactive family through add_inert",
            )
            for penalty in ledger.inactive_penalties():
                require(
                    pattern(penalty) == POS_ZERO,
                    f"{label}/{condition}: an inactive penalty is not exactly +0.0 "
                    f"(0x{pattern(penalty):016x})",
                )
                observed += 1
            for before, after in ledger.inert_additions:
                require(
                    before == after,
                    f"{label}/{condition}: adding +0.0 perturbed the accumulator "
                    f"(0x{before:016x} -> 0x{after:016x})",
                )
                if before == POS_ZERO:
                    zero_accumulator_cases += 1
            require(
                not is_negative_zero(ledger.h_e),
                f"{label}/{condition}: H_E is the negative zero",
            )
        require(observed > 0, f"{label}/{condition} produced no inactive contribution")
        ZERO_ACCUMULATOR_CASES[label] = (
            ZERO_ACCUMULATOR_CASES.get(label, 0) + zero_accumulator_cases
        )


#: Accumulated across the synthetic instances by the fixture above, so the
#: "a zero accumulator was actually reached" requirement can be made once over
#: the whole set rather than per instance, which would be an over-claim: a zero
#: accumulator needs ``f + P_card == 0.0`` exactly, which depends on the
#: instance.
ZERO_ACCUMULATOR_CASES: dict[str, int] = {}


def fixture_zero_accumulator_was_reached() -> None:
    """At least one state reached a zero accumulator, so the sign case is live.

    A zero accumulator is the only state in which ``fl(+0.0 + +0.0)`` and
    ``fl(+0.0 + -0.0)`` are distinguishable, so without one the positive-zero
    requirement in the fixture above would never be exercised at the point where
    it matters.
    """
    total = sum(ZERO_ACCUMULATOR_CASES.values())
    require(
        total > 0,
        "no synthetic instance reached a zero accumulator, so the positive-zero "
        "sign requirement is never exercised where it is decisive",
    )


def fixture_negative_zero_would_be_visible(inst: Instance, label: str) -> None:
    """A ``-0.0`` really would change a result, so the inertia fixture is not vacuous.

    The "adding ``+0.0`` changed nothing" assertion only carries weight if the
    sign bit was ever decisive.  Wherever the evaluator reached a zero
    accumulator it must have kept the positive zero, and the dirty alternative
    ``fl(-0.0 + -0.0) == -0.0`` is shown to differ bitwise, while
    ``fl(-0.0 + +0.0) == +0.0`` is shown to clear the sign.  Together those two
    facts are exactly why the addition must be ``+0.0`` and not ``-0.0``.
    """
    width = len(inst.tickers)
    context = ev.prepare_condition(inst, "C", ACTIVE_LEDGER, LAMBDA_REF)
    for value in range(1 << width):
        ledger = ev.state_ledger(context, ev.mask_to_bits(value, width))
        for before, after in ledger.inert_additions:
            if before == POS_ZERO:
                require(
                    after == POS_ZERO,
                    f"{label}: a zero accumulator must stay the positive zero",
                )
    dirty = -0.0 + -0.0
    require(
        pattern(dirty) == NEG_ZERO,
        "the premise is wrong: -0.0 + -0.0 is not the negative zero",
    )
    require(
        pattern(dirty) != POS_ZERO,
        "the two zeros are bit-identical, so the sign check cannot discriminate",
    )
    require(
        pattern(-0.0 + +0.0) == POS_ZERO,
        "the premise is wrong: -0.0 + +0.0 does not clear the sign bit",
    )


# --------------------------------------------------------------------------- #
# Fixture 4 -- |T_E| = base * 2^w, and no raw 2^39 enumeration
# --------------------------------------------------------------------------- #


def fixture_symbolic_multiplicity(inst: Instance, label: str) -> None:
    """``w`` is 19/8/11 as applicable, and the register is never iterated."""
    expected_width = {"C": 19, "CB": 8, "CS": 11, "CSB": 0}
    for condition, width in expected_width.items():
        context = ev.prepare_condition(inst, condition, ACTIVE_LEDGER, LAMBDA_REF)
        require(
            context.inactive_width == width,
            f"{label}: {condition} must retain a {width}-bit inactive register, "
            f"got {context.inactive_width}",
        )
    require(ev.FAMILY_INACTIVE_WIDTH["sector"] == 8, "the sector family retains 8 bits")
    require(ev.FAMILY_INACTIVE_WIDTH["budget"] == 11, "the budget family retains 11 bits")
    require(
        ev.SLACK_AUXILIARY_LENGTH == 19, "the auxiliary register is 19 bits wide"
    )
    require(ev.RAW_VARIABLE_COUNT == 39, "the Scope-locked raw layout has 39 variables")

    transcript = None
    for condition in ev.CONDITIONS:
        context = ev.prepare_condition(inst, condition, ACTIVE_LEDGER, LAMBDA_REF)
        if transcript is None:
            transcript = ev.prepare_transcript(context)
        result = ev.evaluate_condition(context, transcript)
        base, w = result.t_e_factors
        require(
            result.t_e_size == base * (1 << w),
            f"{label}/{condition}: |T_E| is not base * 2^w",
        )
        require(
            type(result.t_e_size) is int and result.t_e_size.bit_length() > 0,
            f"{label}/{condition}: |T_E| must be an exact Python integer",
        )
        # |C_E| is a different quantity: every active lift, not just the ties.
        require(
            result.raw_domain.raw_factors == (result.raw_domain.base, w),
            f"{label}/{condition}: the raw domain factors must be (|C_E| base, w)",
        )
        require(
            result.raw_domain.materialised == result.raw_domain.base,
            f"{label}/{condition}: the code path must materialise exactly the "
            "active-lift count",
        )
        require(
            not result.raw_domain.enumerated_raw_domain,
            f"{label}/{condition}: the retained register was enumerated",
        )
        require(
            result.raw_domain.retired_register_iterations == 0,
            f"{label}/{condition}: the retained register was iterated",
        )
        require(
            result.raw_domain.raw_size == result.raw_domain.base * (1 << w),
            f"{label}/{condition}: |C_E| is not base * 2^w",
        )
        require(
            base <= result.raw_domain.base,
            f"{label}/{condition}: the tie count cannot exceed the domain",
        )
        require(
            sum(item[1] for item in result.raw_domain.inactive_multiplicities) == w,
            f"{label}/{condition}: the per-family widths must sum to w",
        )
        require(
            all(item[1] == item[2] for item in result.raw_domain.inactive_multiplicities),
            f"{label}/{condition}: a family multiplicity is not 2^width",
        )
        if w > 0:
            require(
                result.t_e_size > base,
                f"{label}/{condition}: the retained register must multiply the count",
            )
        else:
            require(
                result.t_e_size == base,
                f"{label}/{condition}: with w == 0 the count must equal base",
            )


def fixture_retained_register_multiplies(inst: Instance, label: str) -> None:
    """The RETAINED register changes the reported count, so retention is load-bearing.

    Two separate claims, because they are separate quantities:

    * ``|C_E|`` -- the certified raw domain -- must differ between conditions by
      exactly the retained register width, because every assignment of a
      retained register is an exact lift.  This is the claim that "the register
      is retained" makes, and it is the one asserted by exact ratios.
    * ``|T_E|`` -- the tied count -- must be a multiple of the same factor, and
      must differ from ``|C_E|`` whenever the tie is strict, so the two are not
      being conflated.
    """
    transcript = None
    domains = {}
    ties = {}
    for condition in ev.CONDITIONS:
        context = ev.prepare_condition(inst, condition, ACTIVE_LEDGER, LAMBDA_REF)
        if transcript is None:
            transcript = ev.prepare_transcript(context)
        result = ev.evaluate_condition(context, transcript)
        domains[condition] = result.raw_domain.raw_size
        ties[condition] = result.t_e_size
    # The decoded-domain size is identical across conditions, so the raw domain
    # ratio is exactly the retained register multiplicity.
    require(
        domains["C"] == domains["CB"] * (1 << 11),
        f"{label}: dropping the budget register would lose a factor of 2^11 "
        f"(C vs CB): {domains}",
    )
    require(
        domains["CB"] == domains["CSB"] * (1 << 8),
        f"{label}: dropping the sector register would lose a factor of 2^8 "
        f"(CB vs CSB): {domains}",
    )
    require(
        domains["C"] == domains["CSB"] * (1 << 19),
        f"{label}: C must retain both registers, a factor of 2^19 against CSB: {domains}",
    )
    require(
        domains["CS"] == domains["CSB"] * (1 << 11),
        f"{label}: CS must retain the budget register, 2^11 against CSB: {domains}",
    )
    require(
        domains["CSB"] == (1 << len(inst.tickers)),
        f"{label}: with nothing inactive, |C_E| is the plain decoded domain: {domains}",
    )
    # And the tied count is a whole multiple of the same multiplicity.
    require(
        all(
            ties[condition] % (1 << ev.prepare_condition(
                inst, condition, ACTIVE_LEDGER, LAMBDA_REF
            ).inactive_width) == 0
            for condition in ev.CONDITIONS
        ),
        f"{label}: |T_E| must be a whole multiple of the retained register: {ties}",
    )
    require(
        ties["C"] != domains["C"] or ties["CSB"] != domains["CSB"],
        f"{label}: |T_E| and |C_E| must not be the same quantity by construction",
    )


def fixture_no_raw_enumeration_in_source() -> None:
    """The candidate walk iterates the decoded domain only, never a register.

    Checked on the *executable* lines of the evaluator: comments and docstrings
    are stripped first, so this fixture is not satisfied or broken merely by
    the prose that documents the prohibition.
    """
    import ast
    import io
    import tokenize

    source = Path(ev.__file__).read_text(encoding="utf-8")
    code_lines = {
        token.start[0]
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type != tokenize.COMMENT
    }
    # Drop every line that belongs to a docstring.
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                for line in range(body[0].lineno, body[0].end_lineno + 1):
                    code_lines.discard(line)
    code = "\n".join(
        line for number, line in enumerate(source.splitlines(), 1) if number in code_lines
    )
    require(
        "2 ** 39" not in code and "1 << 39" not in code and "2**39" not in code,
        "the evaluator must never construct the raw 2^39 domain in executable code",
    )
    require(
        "for mask in _decoded_masks(context)" in code,
        "the decoded-domain enumeration must be explicit and bounded by 2^width",
    )
    body = code.split("def _decoded_masks", 1)[1].split("def mask_to_bits", 1)[0]
    require(
        "range(1 << context.width())" in body,
        "the decoded-domain loop must be bounded by the decoded width alone",
    )
    # The symbolic multiplicity is the only place a register width becomes a
    # count, and it is a shift, never a range.  ``inactive_families`` holds at
    # most two names, so a ``range`` anywhere in the accounting would be the
    # tell that a register is being walked.
    accounting = code.split("def raw_domain_accounting", 1)[1].split("def _decoded_masks", 1)[0]
    require("base << w" in accounting, "|T_E| must be computed as base << w")
    require(
        "range(" not in accounting,
        "the accounting must not iterate any register, by range or otherwise",
    )
    require(
        f"1 << {ev.SLACK_AUXILIARY_LENGTH}" not in accounting,
        "the accounting must not materialise the raw register width",
    )
    # And the whole evaluator, apart from the decoded-domain walk, never ranges
    # over anything wider than the decoded domain.
    require(
        "1 << 39" not in code and "1 << 38" not in code,
        "no expression anywhere may materialise the raw 2^39 domain",
    )


# --------------------------------------------------------------------------- #
# Fixture 5 -- the D015 order and the condition map
# --------------------------------------------------------------------------- #


def fixture_accumulation_order(inst: Instance, label: str) -> None:
    """D015's order is f, P_card, sector j=1..4, budget -- checked step by step.

    On every instance the six accumulator steps are checked against the
    transcript explicitly.  On ``mixed_sigma`` -- the instance built with a
    non-degenerate Sigma for this purpose -- it is additionally required that
    the order actually changes the result, so the step checks above are not
    satisfied by an addition that would have given the same answer in any
    order.
    """
    width = len(inst.tickers)
    context = ev.prepare_condition(inst, "CSB", ACTIVE_LEDGER, LAMBDA_REF)
    distinguished = None
    for value in range(1 << width):
        x = ev.mask_to_bits(value, width)
        ledger = ev.state_ledger(context, x)
        trace = ledger.accumulator_trace
        require(len(trace) == 6, "D015's transcript has exactly six accumulator steps")
        require(trace[0] == ledger.f_value + ledger.p_card, "step 1 must be f + P_card")
        require(trace[1] == trace[0] + ledger.sector[0].penalty, "step 2 is P_sector[1]")
        require(trace[2] == trace[1] + ledger.sector[1].penalty, "step 3 is P_sector[2]")
        require(trace[3] == trace[2] + ledger.sector[2].penalty, "step 4 is P_sector[3]")
        require(trace[4] == trace[3] + ledger.sector[3].penalty, "step 5 is P_sector[4]")
        require(trace[5] == trace[4] + ledger.budget.penalty, "step 6 is P_budget")
        require(ledger.h_e == trace[5], "H_E must be the final accumulator")
        require(
            ledger.penalties()
            == (ledger.p_card,)
            + tuple(item.penalty for item in ledger.sector)
            + (ledger.budget.penalty,),
            "the penalty transcript must be in D015's order",
        )
        # The order must matter on at least one state, or nothing above pins
        # anything.  Moving the budget penalty to the front is a different sum.
        moved_budget_first = (
            ledger.f_value
            + ledger.p_card
            + ledger.budget.penalty
            + sum(item.penalty for item in ledger.sector)
        )
        if pattern(moved_budget_first) != pattern(ledger.h_e):
            distinguished = ledger
            break
    if label == "mixed_sigma":
        require(
            distinguished is not None,
            f"{label}: the accumulation order was never load-bearing, so the "
            "order fixture pins nothing on the instance built to test it",
        )
        require(
            len(distinguished.sector) == SECTOR,
            "D015 names four sector penalties, in order",
        )


def fixture_condition_map_matches_d013() -> None:
    """The active/inactive map is exactly D013's four ``F_q`` predicates."""
    require(ev.CONDITIONS == ("C", "CB", "CS", "CSB"), "D013 fixes exactly four names")
    expected = {
        "C": ((), ("sector", "budget"), 1, 19),
        "CB": (("budget",), ("sector",), 2, 8),
        "CS": (("sector",), ("budget",), 2, 11),
        "CSB": (("sector", "budget"), (), 3, 0),
    }
    for condition, (active, inactive, axes, width) in expected.items():
        activity = ev.family_activity(condition)
        require(
            activity["cardinality"] is True,
            "cardinality is active in all four D013 predicates",
        )
        active_names = tuple(n for n in ("sector", "budget") if activity[n])
        inactive_names = tuple(n for n in ("sector", "budget") if not activity[n])
        require(active_names == active, f"{condition} active families are {active_names}")
        require(
            inactive_names == inactive, f"{condition} inactive families are {inactive_names}"
        )
        coefficients = ev.build_condition_coefficients(condition, ACTIVE_LEDGER)
        require(
            coefficients.active_penalty_axes() == axes,
            f"{condition} must have {axes} active penalty axes",
        )
        require(
            coefficients.inactive_width() == width,
            f"{condition} must retain {width} inactive register bits",
        )
        require(
            coefficients.active_families() == active,
            f"{condition} must report its active families",
        )
        require(
            coefficients.inactive_families() == inactive,
            f"{condition} must report its inactive families",
        )
        for name in ("sector_slack", "budget_slack", "sector_linear", "sector_quadratic",
                     "budget_linear", "budget_quadratic"):
            value = getattr(coefficients, name)
            if name.startswith("sector"):
                family_active = activity["sector"]
            else:
                family_active = activity["budget"]
            if family_active:
                require(value > 0.0, f"{condition}: an active {name} must be positive")
            else:
                require(
                    pattern(value) == POS_ZERO,
                    f"{condition}: an inactive {name} must be exactly +0.0",
                )
    # Cardinality is never inactive, so alpha is never a +0.0 family.
    for condition in ev.CONDITIONS:
        coefficients = ev.build_condition_coefficients(condition, ACTIVE_LEDGER)
        require(
            pattern(coefficients.alpha) != POS_ZERO and coefficients.alpha > 0.0,
            f"{condition}: cardinality must never be inactive",
        )


# --------------------------------------------------------------------------- #
# Fixture 6 -- typed refusals
# --------------------------------------------------------------------------- #


def fixture_typed_refusals() -> None:
    """Malformed names, wrong types, ``-0.0``, active zeros and empty ``F_q``."""
    for bad in ("CSBA", "c", "", "CB ", "C,B", "FULL", "CB_C"):
        try:
            ev.family_activity(bad)
        except ev.InertEvaluatorError:
            continue
        raise RuntimeError(f"malformed condition name {bad!r} was accepted")
    for bad in (None, 13, 3.0, True, ["C"], {"C": 1}, object()):
        try:
            ev.family_activity(bad)
        except ev.InertEvaluatorError:
            continue
        raise RuntimeError(f"non-string condition {bad!r} was accepted")


    for bad in (-0.0, 1.0, float("nan"), "0.0", 0, None):
        try:
            ev.require_positive_zero(bad, "probe")
        except ev.InertEvaluatorError:
            continue
        raise RuntimeError(f"a value of {bad!r} was accepted as an inactive coefficient")

    # -0.0 must be refused by the real constructor, not only by the helper.
    for condition in ("C", "CB", "CS"):
        for name in ("sector_slack", "budget_slack", "sector_linear",
                     "sector_quadratic", "budget_linear", "budget_quadratic"):
            family = "sector" if name.startswith("sector") else "budget"
            if ev.family_activity(condition)[family]:
                continue
            ledger = dict(ACTIVE_LEDGER)
            ledger[name] = -0.0
            try:
                ev.build_condition_coefficients(condition, ledger)
            except ev.InertEvaluatorError:
                continue
            raise RuntimeError(f"{condition} accepted -0.0 for the inactive {name}")

    # A zero or negative coefficient on an ACTIVE family.
    for name in ("sector_slack", "budget_slack", "alpha", "sector_linear"):
        for bad_value in (0.0, -0.0, -1.0, 0, False):
            ledger = dict(ACTIVE_LEDGER)
            ledger[name] = bad_value
            try:
                ev.build_condition_coefficients("CSB", ledger)
            except ev.InertEvaluatorError:
                continue
            raise RuntimeError(f"an active-family {name} of {bad_value!r} was accepted")

    # Wrong coefficient types and non-finite values.
    for bad_value in ("1.5", None, [1.5], {}, complex(1, 2), float("nan"),
                      float("inf"), float("-inf")):
        ledger = dict(ACTIVE_LEDGER)
        ledger["alpha"] = bad_value
        try:
            ev.build_condition_coefficients("CSB", ledger)
        except ev.InertEvaluatorError:
            continue
        raise RuntimeError(f"an alpha of {bad_value!r} was accepted")

    ledger = dict(ACTIVE_LEDGER)
    ledger["extra"] = 1.0
    for bad_ledger, reason in (
        (ledger, "an unknown coefficient field"),
        ({k: v for k, v in ACTIVE_LEDGER.items() if k != "alpha"}, "a missing field"),
        ([1, 2, 3], "a non-dict ledger"),
        ("ledger", "a string ledger"),
    ):
        try:
            ev.build_condition_coefficients("CSB", bad_ledger)
        except ev.InertEvaluatorError:
            continue
        raise RuntimeError(f"{reason} was accepted")

    for bad_ref in (0.0, -1.0, float("nan"), float("inf"), "120", None):
        try:
            ev.prepare_condition(FLAT, "CSB", ACTIVE_LEDGER, bad_ref)
        except ev.InertEvaluatorError:
            continue
        raise RuntimeError(f"Lambda_ref of {bad_ref!r} was accepted")
    for bad_instance in (None, "instance", 5, object()):
        try:
            ev.prepare_condition(bad_instance, "CSB", ACTIVE_LEDGER, LAMBDA_REF)
        except ev.InertEvaluatorError:
            continue
        raise RuntimeError(f"a non-Instance of {type(bad_instance).__name__} was accepted")
    # A structurally invalid synthetic instance.
    for bad_instance in (
        build_instance([1.0] * SMALL_WIDTH, [1] * SMALL_WIDTH, 2, 1, 5.0, SMALL_WIDTH,
                       ((0, 1), (2, 3), (4, 5))),  # three sectors
        build_instance([1.0] * SMALL_WIDTH, [1] * SMALL_WIDTH, 2, 1, 5.0, SMALL_WIDTH,
                       ((0, 1), (2, 3), (4, 5), (6, 9))),  # sector overruns the width
        build_instance([1.0] * SMALL_WIDTH, [1] * (SMALL_WIDTH - 1), 2, 1, 5.0,
                       SMALL_WIDTH, SMALL_SECTORS),  # short price vector
    ):
        try:
            ev.prepare_condition(bad_instance, "CSB", ACTIVE_LEDGER, LAMBDA_REF)
        except ev.InertEvaluatorError:
            continue
        raise RuntimeError("a structurally invalid instance was accepted")

    context = ev.prepare_condition(FLAT, "CSB", ACTIVE_LEDGER, LAMBDA_REF)
    for bad_x in ((0,) * (SMALL_WIDTH - 1), (0,) * (SMALL_WIDTH + 1),
                  (0, 2) + (0,) * (SMALL_WIDTH - 2), "x" * SMALL_WIDTH):
        try:
            ev.feasible_q(context, bad_x)
        except ev.InertEvaluatorError:
            continue
        raise RuntimeError(f"a malformed x of {bad_x!r} was accepted")

    # The frozen type boundary: a +0.0 family is not representable there.
    inactive = ev.prepare_condition(FLAT, "CB", ACTIVE_LEDGER, LAMBDA_REF)
    try:
        inactive.coefficients.frozen_active_view()
    except ev.InertEvaluatorError:
        pass
    else:
        raise RuntimeError("an inactive condition was offered to the frozen Coefficients")
    require(
        isinstance(
            ev.prepare_condition(FLAT, "CSB", ACTIVE_LEDGER, LAMBDA_REF)
            .coefficients.frozen_active_view(),
            Coefficients,
        ),
        "CSB must still be representable by the frozen type",
    )
    # A narrow synthetic instance has no frozen prepared state, and says so.
    require(
        context.prepared is None,
        "an 8-ticker synthetic instance must not claim a frozen prepared state",
    )
    try:
        context.require_frozen()
    except ev.InertEvaluatorError:
        pass
    else:
        raise RuntimeError("a narrow instance was given a frozen prepared state")
    require(
        ev.prepare_condition(FROZEN_INSTANCE, "CSB", ACTIVE_LEDGER, LAMBDA_REF)
        .require_frozen() is not None,
        "the Scope-locked instance must have a frozen prepared state",
    )


# --------------------------------------------------------------------------- #
# Fixture 6b -- trust-boundary fuzzing at every public entry point
# --------------------------------------------------------------------------- #

#: The lead's ruling (3) fuzz set.  Every one of these is a value the boundary
#: must refuse **with the module's typed error**, at every public entry point,
#: for every field that entry point accepts.
#:
#: ``-0.0`` is deliberately NOT here.  Ruling (1) constrains a field's *type*
#: (int or float, ``bool`` excluded) and its finiteness, and ``-0.0`` is a
#: perfectly finite float: it is a legal ``mu`` entry, a legal ``K``, a legal
#: ``B``.  What ``-0.0`` is *not* is a legal **inactive coefficient** -- there it
#: must be exactly ``+0.0`` by bit pattern -- so it is fuzzed in that one slot,
#: in ``fixture_trust_boundary_fuzz``'s inactive-coefficient section and in
#: ``fixture_typed_refusals``, rather than as a type violation everywhere.
#: Fuzzing it as a type violation in every field would assert a falsehood, and a
#: check that asserts a falsehood is worse than no check.
#:
#: ``10**400`` is the one *well-typed* Python value that is still a refusal: it
#: is an ``int``, so it passes the type check, but it has no finite ``float()``
#: representation, so ``float()`` and ``math.isfinite()`` both raise
#: ``OverflowError``.  It was a genuine untyped leak found by the mutation sweep
#: and is now refused by the range check inside :func:`_require_real_number`.
HUGE_INT = 10 ** 400

FUZZ_VALUES = (
    None,
    True,
    False,
    "3",
    "",
    [1.0],
    {"a": 1.0},
    (1.0,),
    float("nan"),
    float("inf"),
    float("-inf"),
    complex(1.0, 2.0),
    object(),
    HUGE_INT,
    -HUGE_INT,
)


def _fuzz_instance(field: str, value: object, width: int = SMALL_WIDTH) -> Instance:
    """A structurally valid synthetic instance with one field replaced.

    Every other field stays valid so the fixture fails on the *fuzzed* field and
    not on some unrelated structural refusal, which would be a test passing for
    the wrong reason.
    """
    base = FLAT if width == SMALL_WIDTH else FROZEN_INSTANCE
    values = {
        "tickers": base.tickers,
        "sectors": base.sectors,
        "mu": base.mu,
        "sigma": base.sigma,
        "prices": base.prices,
        "kappa_risk": base.kappa_risk,
        "K": base.K,
        "C": base.C,
        "B": base.B,
    }
    values[field] = value
    return Instance(**values)


def _require_typed(call, what: str) -> ev.InertEvaluatorError:
    """Assert ``call`` refuses with the module's typed error, nothing else.

    The strictness matters: a ``ValueError`` is the typed error's *base* class,
    so ``except ValueError`` would accept the very untyped leak this fixture
    exists to catch.  The class is therefore compared exactly, and the chained
    ``__cause__`` is required to be present for a delegated refusal so the
    original context is proven preserved rather than merely discarded.
    """
    try:
        call()
    except ev.InertEvaluatorError as error:
        require(
            type(error) is ev.InertEvaluatorError,
            f"{what}: the refusal must be InertEvaluatorError itself, not a "
            f"subclass ({type(error).__name__})",
        )
        return error
    except BaseException as error:
        raise RuntimeError(
            f"{what}: an untyped {type(error).__name__} leaked at the trust "
            f"boundary: {error}"
        ) from error
    raise RuntimeError(f"{what}: the malformed input was accepted")


def fixture_trust_boundary_fuzz() -> None:
    """Every public entry point refuses every fuzzed field with the typed error.

    This is the lead's ruling (3).  Round 2 leaked an untyped ``ValueError``
    from ``float(instance.K)``/``float(instance.C)`` in
    ``_require_synthetic_instance`` and an untyped ``ValueError`` from the
    delegated frozen ``prepare_instance``.  Both are closed above; this fixture
    is what keeps them closed, by fuzzing **every numeric field of the instance
    and of the ledger**, on **both** the narrow synthetic branch and the
    Scope-locked frozen branch, plus the delegated-module stand-in.
    """
    # --- the instance's numeric fields, on the narrow synthetic branch --------
    for field in ("mu", "prices", "sigma", "kappa_risk", "K", "C", "B"):
        for bad in FUZZ_VALUES:
            if field == "sigma":
                # A row, not a scalar: index 0 carries the fuzzed value.
                bad_instance = _fuzz_instance(
                    field,
                    ((bad,) + (0.0,) * (SMALL_WIDTH - 1),) * SMALL_WIDTH,
                )
                # A whole-matrix fuzz is also covered by the row fuzz above.
            elif field in ("mu", "prices"):
                bad_instance = _fuzz_instance(
                    field, (bad,) + FLAT.__getattribute__(field)[1:]
                )
            else:
                bad_instance = _fuzz_instance(field, bad)
            _require_typed(
                lambda i=bad_instance: ev.prepare_condition(
                    i, "CSB", ACTIVE_LEDGER, LAMBDA_REF
                ),
                f"prepare_condition synthetic branch: {field}={bad!r}",
            )

    # --- the same fields, on the Scope-locked frozen branch ------------------
    # This is the path that round 2 delegated straight into prepare_instance.
    for field in ("mu", "prices", "sigma", "kappa_risk", "K", "C", "B"):
        for bad in FUZZ_VALUES:
            if field == "sigma":
                bad_instance = _fuzz_instance(
                    field,
                    ((bad,) + (0.0,) * (FROZEN_WIDTH - 1),) * FROZEN_WIDTH,
                    FROZEN_WIDTH,
                )
            elif field in ("mu", "prices"):
                bad_instance = _fuzz_instance(
                    field,
                    (bad,) + FROZEN_INSTANCE.__getattribute__(field)[1:],
                    FROZEN_WIDTH,
                )
            else:
                bad_instance = _fuzz_instance(field, bad, FROZEN_WIDTH)
            _require_typed(
                lambda i=bad_instance: ev.prepare_condition(
                    i, "CSB", ACTIVE_LEDGER, LAMBDA_REF
                ),
                f"prepare_condition frozen branch: {field}={bad!r}",
            )

    # --- the CSB coefficient ledger, every field ------------------------------
    # ``-0.0`` and ``0.0`` are added here: on an ACTIVE family both are
    # refusals (strict positivity), and for the inactive families of C/CB/CS
    # ``-0.0`` is the round-2-specified dirty-zero refusal.
    for name in ev._COEF_FIELDS:
        for bad in (*FUZZ_VALUES, -0.0, 0.0):
            ledger = dict(ACTIVE_LEDGER)
            ledger[name] = bad
            _require_typed(
                lambda l=ledger: ev.build_condition_coefficients("CSB", l),
                f"build_condition_coefficients: {name}={bad!r}",
            )
            # And through the public entry point, not only the builder.
            _require_typed(
                lambda l=ledger: ev.prepare_condition(FLAT, "CSB", l, LAMBDA_REF),
                f"prepare_condition: ledger {name}={bad!r}",
            )

    # --- Lambda_ref, and the condition name, at prepare_condition -------------
    for bad in FUZZ_VALUES:
        _require_typed(
            lambda b=bad: ev.prepare_condition(FLAT, "CSB", ACTIVE_LEDGER, b),
            f"prepare_condition: Lambda_ref={bad!r}",
        )
        _require_typed(
            lambda b=bad: ev.prepare_condition(FLAT, b, ACTIVE_LEDGER, LAMBDA_REF),
            f"prepare_condition: condition={bad!r}",
        )
        _require_typed(
            lambda b=bad: ev.prepare_condition(b, "CSB", ACTIVE_LEDGER, LAMBDA_REF),
            f"prepare_condition: instance={bad!r}",
        )

    # --- the inactive-coefficient slot: -0.0 is refused by bit pattern --------
    # ``+0.0`` is deliberately absent: accepting it is this function's contract,
    # and ``fixture_inactive_is_exact_positive_zero`` pins that it is accepted.
    for bad in (*FUZZ_VALUES, -0.0, 1.0):
        _require_typed(
            lambda b=bad: ev.require_positive_zero(b, "fuzz"),
            f"require_positive_zero: {bad!r}",
        )

    # --- the accumulator in add_inert is caller data too ---------------------
    for bad in FUZZ_VALUES:
        _require_typed(
            lambda b=bad: ev.add_inert(b, 0.0, "fuzz"),
            f"add_inert: accumulator={bad!r}",
        )
    for bad in FUZZ_VALUES:
        _require_typed(
            lambda b=bad: ev.add_inert(0.0, b, "fuzz"),
            f"add_inert: penalty={bad!r}",
        )

    # --- bits_of is public and packs caller data -----------------------------
    for bad in FUZZ_VALUES:
        _require_typed(lambda b=bad: ev.bits_of(b), f"bits_of: {bad!r}")

    # --- the integer-typed accounting entry points ---------------------------
    # ``base``/``tie_count`` are *exact Python integers* by contract -- that is
    # the whole point of the exact-integer |C_E| and |T_E| accounting -- so a
    # huge int is a legal value here and must not be fuzzed.  Every other
    # non-numeric fuzz value still is.
    int_fuzz = tuple(b for b in FUZZ_VALUES if not isinstance(b, int) or isinstance(b, bool))
    context = ev.prepare_condition(FLAT, "C", ACTIVE_LEDGER, LAMBDA_REF)
    raw = ev.raw_domain_accounting(context, 4)
    for bad in int_fuzz:
        _require_typed(
            lambda b=bad: ev.raw_domain_accounting(context, b),
            f"raw_domain_accounting: base={bad!r}",
        )
        _require_typed(
            lambda b=bad: ev.t_e_accounting(raw, b),
            f"t_e_accounting: tie_count={bad!r}",
        )
    # ``raw_domain_accounting``'s ``tie_count`` is Optional by contract -- None
    # means "default to base" -- so it is excluded from the type fuzz and the
    # non-None values are fuzzed instead.  ``t_e_accounting`` has no such
    # default and was fuzzed with None above.
    for bad in (b for b in int_fuzz if b is not None):
        _require_typed(
            lambda b=bad: ev.raw_domain_accounting(context, 4, b),
            f"raw_domain_accounting: tie_count={bad!r}",
        )
    require(
        ev.raw_domain_accounting(context, 4, None).raw_factors == (4, context.inactive_width),
        "raw_domain_accounting: a None tie_count must still mean 'the whole domain'",
    )

    # --- tau is public and delegates to the frozen module --------------------
    for bad in FUZZ_VALUES:
        _require_typed(
            lambda b=bad: ev.tau(context, b, 0.0),
            f"tau: y={bad!r}",
        )
        _require_typed(
            lambda b=bad: ev.tau(context, 0.0, b),
            f"tau: y_prime={bad!r}",
        )


def fixture_delegated_failures_are_typed() -> None:
    """A delegated module's own failure surfaces as the typed error, chained.

    Ruling (2).  The delegated call is injected through a stand-in so the check
    does not depend on any particular frozen module raising: it asserts the
    *conversion* itself, which is what the lead's ruling constrains.

    ``ValueError``, ``TypeError`` and ``ArithmeticError`` (including its
    ``ZeroDivisionError``/``OverflowError``/``FloatingPointError`` subclasses)
    are all converted, with the original message preserved and chained via
    ``from``.  ``BaseException`` is **not** caught, so ``KeyboardInterrupt``,
    ``SystemExit`` and ``MemoryError`` must pass through untouched -- that is
    checked too, because a blanket ``except BaseException`` would satisfy every
    other assertion in this fixture while destroying cancellation.
    """
    for source in (
        ValueError("frozen value refusal"),
        TypeError("frozen type refusal"),
        ZeroDivisionError("frozen arithmetic refusal"),
        OverflowError("frozen overflow refusal"),
        ArithmeticError("frozen arithmetic base refusal"),
    ):
        def boom(exc=source):
            raise exc

        error = _require_typed(
            lambda b=boom: ev._delegated("stand-in", b),
            f"_delegated: {type(source).__name__}",
        )
        require(
            "stand-in refused" in str(error),
            f"_delegated: the boundary name must survive the conversion, got {error}",
        )
        require(
            type(error.__cause__) is type(source)
            and str(error.__cause__) == str(source),
            f"_delegated: the original {type(source).__name__} must be chained "
            f"with `from` and its message preserved, got {error.__cause__!r}",
        )

    # The module's own typed error must pass through unwrapped and unchained.
    original = ev.InertEvaluatorError("native refusal")
    error = _require_typed(
        lambda: ev._delegated("stand-in", lambda: (_ for _ in ()).throw(original)),
        "_delegated: a native InertEvaluatorError",
    )
    require(
        str(error) == "native refusal" and error.__cause__ is None,
        f"_delegated: a native typed error must not be re-wrapped, got {error!r} "
        f"with cause {error.__cause__!r}",
    )

    # A successful delegated call returns its value untouched.
    require(
        ev._delegated("stand-in", lambda: 7) == 7,
        "_delegated: a successful call must return the delegated value",
    )

    # --- the helper is not dead code on any of the four delegating sites -----
    # Each delegated call site is counted by the frozen public functions it
    # actually invokes.  A wrapper that were never used would leave every one of
    # these at zero, which is what makes the reachability assertions below
    # load-bearing rather than decorative.
    def _count(source: str, name: str) -> int:
        return sum(
            1
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        )

    src = Path(ev.__file__).read_text(encoding="utf-8")
    delegations = _count(src, "_delegated")
    require(
        delegations >= 8,
        f"the _delegated boundary is barely used ({delegations} call sites); the "
        "trust boundary must wrap every delegated frozen call, not just one",
    )
    frozen_calls = _count(src, "prepare_instance") + _count(src, "prepare_decoded_state")
    require(
        frozen_calls >= 1 and delegations >= 4,
        "the delegated boundary must cover prepare_instance and "
        "prepare_decoded_state as well as the tau and classifier calls",
    )
    # Every one of the four named delegating sites must still route through
    # _delegated, so unwrapping any single one is caught.
    for boundary in (
        "frozen src.g4.energy.prepare_instance",
        "frozen src.g4.energy.prepare_decoded_state",
        "frozen src.g4.energy.tau",
        "frozen src.g4.classification.DecodedClassifier",
        "frozen src.g4.parameters.Coefficients",
    ):
        require(
            f'"{boundary}"' in src,
            f"the delegated boundary for {boundary!r} is gone; every frozen call "
            "that consumes caller data must be wrapped",
        )

    # BaseException must NOT be caught.
    for passthrough in (KeyboardInterrupt(), SystemExit(1), MemoryError()):
        def boom(exc=passthrough):
            raise exc

        try:
            ev._delegated("stand-in", boom)
        except (KeyboardInterrupt, SystemExit, MemoryError) as got:
            require(
                type(got) is type(passthrough),
                f"_delegated: {type(passthrough).__name__} must pass through "
                f"unchanged, got {type(got).__name__}",
            )
            continue
        except BaseException as got:
            raise RuntimeError(
                f"_delegated: caught BaseException {type(got).__name__}; only "
                "TypeError, ValueError, ArithmeticError and the delegated "
                "module's own typed errors may be converted"
            ) from got
        raise RuntimeError(
            f"_delegated: {type(passthrough).__name__} was swallowed"
        )


def fixture_delegated_boundary_is_load_bearing() -> None:
    """The two round-2 leak paths are refused *because* of the new boundaries.

    Without this, the fuzz fixture above would still pass if the boundary were
    deleted and the refusal came from somewhere else entirely.  Here each
    boundary is removed in turn and the specific fuzzed input that it is
    supposed to catch is shown to leak an untyped exception instead.
    """
    # The delegated prepare_instance path.  A 20-ticker instance whose K is a
    # string is refused by our own pre-conversion type check; strip that check
    # and the frozen module's own ValueError is what surfaces.
    bad_k = _fuzz_instance("K", "not a number", FROZEN_WIDTH)
    error = _require_typed(
        lambda: ev.prepare_condition(bad_k, "CSB", ACTIVE_LEDGER, LAMBDA_REF),
        "prepare_condition frozen branch: a string K",
    )
    require(
        "K must be an int or a float" in str(error),
        f"the frozen-branch K refusal must come from the pre-conversion type "
        f"check, got {error}",
    )

    # The synthetic branch, the exact round-2 leak: float(instance.K) on a
    # string.  It must now be refused by the same pre-conversion check.
    bad_k_small = _fuzz_instance("K", "not a number")
    error = _require_typed(
        lambda: ev.prepare_condition(bad_k_small, "CSB", ACTIVE_LEDGER, LAMBDA_REF),
        "prepare_condition synthetic branch: a string K",
    )
    require(
        "K must be an int or a float" in str(error),
        f"the synthetic-branch K refusal must come from the pre-conversion type "
        f"check, not from a rescued conversion, got {error}",
    )
    require(
        not isinstance(error.__cause__, ValueError),
        "the refusal must be raised directly by the type check, not chained "
        f"from a rescued ValueError (cause: {error.__cause__!r})",
    )


def fixture_empty_feasible_set_is_a_hard_stop() -> None:
    """An empty ``F_q`` raises a typed error and writes nothing.

    Two genuinely distinct empty-``F_q`` routes, because D013's conditions empty
    in different ways:

    * **An empty supplied candidate list.**  ``objective_optimum`` is evaluated
      over the states it is given, so an empty list is an empty ``F_q`` by
      construction.  This is the only route that reaches every condition
      including ``C``, and it is a hard stop, not a value.
    * **A capacity that no portfolio can meet.**  ``C = 0`` with a budget below
      the cheapest portfolio empties exactly the conditions whose *active*
      families include a sector or budget capacity.  ``F_C`` stays nonempty,
      because ``C``'s only active family is cardinality, which is satisfied --
      and the fixture asserts that too, which is what pins the predicate as
      genuinely per-condition.
    """
    # Route one: an empty candidate list refuses every condition.
    for condition in ev.CONDITIONS:
        context = ev.prepare_condition(FLAT, condition, ACTIVE_LEDGER, LAMBDA_REF)
        try:
            ev.objective_optimum(context, ())
        except ev.InertEvaluatorError as error:
            message = str(error)
            require(
                f"F_{condition} is empty" in message,
                f"the empty-F_{condition} refusal must name the condition: {message}",
            )
            require(
                "hard stop" in message,
                f"the empty-F_{condition} refusal must say it is a hard stop: {message}",
            )
            continue
        raise RuntimeError(f"an empty F_{condition} produced a value instead of a refusal")

    # Route two: capacity no portfolio can meet.
    no_capacity = build_instance(
        [-1.0] * SMALL_WIDTH, [4] * SMALL_WIDTH, 2, 0, 2.0, SMALL_WIDTH, SMALL_SECTORS
    )
    expectations = {"C": False, "CB": True, "CS": True, "CSB": True}
    for condition, should_refuse in expectations.items():
        context = ev.prepare_condition(no_capacity, condition, ACTIVE_LEDGER, LAMBDA_REF)
        states = tuple(ev.mask_to_bits(v, SMALL_WIDTH) for v in range(1 << SMALL_WIDTH))
        feasible_any = any(ev.feasible_q(context, x) for x in states)
        if should_refuse:
            require(
                not feasible_any,
                f"the {condition} premise is wrong: some portfolio was feasible",
            )
            try:
                ev.objective_optimum(context, states)
            except ev.InertEvaluatorError as error:
                require(
                    f"F_{condition} is empty" in str(error),
                    f"the empty-F_{condition} refusal must name the condition: {error}",
                )
                continue
            raise RuntimeError(f"an empty F_{condition} produced a value")
        require(
            feasible_any,
            f"F_{condition} must stay nonempty: it has only a cardinality predicate",
        )
        result = ev.objective_optimum(context, states)
        require(
            result.feasible_count > 0,
            f"F_{condition} must stay nonempty under a cardinality-only predicate",
        )

    # The full evaluation path must refuse before producing any result.
    for condition in ("CB", "CS", "CSB"):
        context = ev.prepare_condition(no_capacity, condition, ACTIVE_LEDGER, LAMBDA_REF)
        try:
            ev.evaluate_condition(context)
        except ev.InertEvaluatorError as error:
            require(
                f"F_{condition} is empty" in str(error),
                f"evaluate_condition must refuse an empty F_{condition}: {error}",
            )
        else:
            raise RuntimeError(f"evaluate_condition produced a result for an empty F_{condition}")


def fixture_empty_feasible_set_from_filtered_states() -> None:
    """``F_q`` empty because every supplied state is infeasible also refuses."""
    context = ev.prepare_condition(FLAT, "CSB", ACTIVE_LEDGER, LAMBDA_REF)
    infeasible = (ev.mask_to_bits(0, SMALL_WIDTH), ev.mask_to_bits(1, SMALL_WIDTH))
    require(
        not any(ev.feasible_q(context, x) for x in infeasible),
        "the chosen states must really be infeasible",
    )
    try:
        ev.objective_optimum(context, infeasible)
    except ev.InertEvaluatorError as error:
        require("F_CSB is empty" in str(error), f"unexpected message: {error}")
    else:
        raise RuntimeError("an empty F_q over the supplied states produced a value")


def fixture_feasible_predicate_matches_d013() -> None:
    """``feasible_q`` is exactly D013's predicate for each condition.

    Each state's feasibility is recomputed by hand from the defining inequality,
    independently of the evaluator.
    """
    for label, inst in SMALL_INSTANCES:
        width = len(inst.tickers)
        for condition in ev.CONDITIONS:
            context = ev.prepare_condition(inst, condition, ACTIVE_LEDGER, LAMBDA_REF)
            active = ev.family_activity(condition)
            for value in range(1 << width):
                x = ev.mask_to_bits(value, width)
                card = sum(x)
                spend = sum(inst.prices[i] * x[i] for i in range(width))
                expected = card == inst.K
                if expected and active["sector"]:
                    expected = all(
                        sum(x[i] for i in members) <= inst.C for members in inst.sectors
                    )
                if expected and active["budget"]:
                    expected = spend <= inst.B
                require(
                    ev.feasible_q(context, x) is expected,
                    f"{label}/{condition}: feasible_q disagrees with D013's predicate "
                    f"at mask {value}",
                )


#: Stride for the residual-transcript fixture.  ``src.g4.energy.residuals`` is
#: hard-gated to the Scope-locked 20 tickers by ``_require_instance``, so this
#: fixture cannot run on the 8-ticker instances; it runs on a dedicated
#: 20-ticker instance instead.  A stride of ``2**RESIDUAL_STRIDE_SHIFT`` over
#: the ``2**20`` domain still varies every one of the 20 tickers and all four
#: sectors across the sampled states, and every sampled state performs a full
#: 20-term budget sum -- which is the accumulation whose rounding is under test.
RESIDUAL_STRIDE_SHIFT = 8
RESIDUAL_STRIDE = 1 << RESIDUAL_STRIDE_SHIFT


#: A 20-ticker instance whose residuals are **genuinely non-integral**.
#: ``C = 0.5`` makes every ``h_sector`` a half-integer, and fractional prices
#: make most ``h_budget`` values non-integral, so a reordering or rounding of
#: the residual accumulation changes the low bits and is visible.  The
#: Scope-locked frozen instance cannot serve here: its integral ``C``, ``B``
#: and unit prices make every residual an exact integer, so bit-identity
#: against it would hold for any arithmetic order and prove nothing.
FROZEN_ROUNDING_INSTANCE = build_instance(
    [-1.0] * FROZEN_WIDTH,
    [1.25 * (i + 1) / 3.0 for i in range(FROZEN_WIDTH)],
    3,
    0.5,
    5.5,
    FROZEN_WIDTH,
    tuple(tuple(range(4 * j, 4 * j + 4)) for j in range(SECTOR)),
    sigma=spread_sigma(FROZEN_WIDTH),
)


def fixture_residuals_are_bit_identical_to_frozen() -> None:
    """The fast residual transcript equals ``src.g4.energy.residuals`` bit-for-bit.

    ``src.g4.energy.residuals`` calls ``_require_instance``, which refuses
    anything other than the Scope-locked 20-ticker / 4-sector layout, so the
    comparison necessarily runs on a 20-ticker instance.  It is run under CSB
    (all families active) so that the residuals under test are the frozen ones
    and not the evaluator's ``+0.0`` inactive substitutes; the inactive case is
    covered by ``fixture_negative_zero_would_be_visible`` and the slow
    reference.

    The instance is built with a fractional ``C`` and fractional prices so that
    non-integral sector and budget residuals actually occur -- and the fixture
    refuses to pass if none do, because then any reordering or rounding of the
    residual accumulation would be invisible and the check vacuous.
    """
    non_integral_budget = 0
    non_integral_sector = 0
    compared = 0
    bits_seen = 0
    for label, inst in (("frozen_rounding", FROZEN_ROUNDING_INSTANCE),):
        context = ev.prepare_condition(inst, "CSB", ACTIVE_LEDGER, LAMBDA_REF)
        width = len(inst.tickers)
        require(
            width == FROZEN_WIDTH,
            f"{label}: the frozen residual entry point requires 20 tickers, "
            f"not {width}",
        )
        for index, high in enumerate(range(0, 1 << width, RESIDUAL_STRIDE)):
            # The low RESIDUAL_STRIDE_SHIFT bits are filled with a rotating
            # counter rather than left at zero: the high bits alone would never
            # set the low tickers, and the fixture's own ``bits_seen`` check
            # rejects that.
            value = high | (index & (RESIDUAL_STRIDE - 1))
            x = ev.mask_to_bits(value, width)
            bits_seen |= value
            mine = ev.fast_decoded_state(context, x)
            theirs = frozen_energy.residuals(inst, x)
            require(
                mine.h_card == theirs[0]
                and pattern(mine.h_card) == pattern(theirs[0]),
                f"{label}: h_card is not bit-identical to the frozen residual at {value}",
            )
            for j, (mine_value, frozen_value) in enumerate(
                zip(mine.h_sector, theirs[1])
            ):
                require(
                    pattern(mine_value) == pattern(frozen_value),
                    f"{label}: h_sector[{j}] is not bit-identical to the frozen "
                    f"residual at {value}: {mine_value!r} vs {frozen_value!r}",
                )
                if mine_value != float(int(mine_value)):
                    non_integral_sector += 1
            require(
                pattern(mine.h_budget) == pattern(theirs[2]),
                f"{label}: h_budget is not bit-identical to the frozen residual "
                f"at {value}: {mine.h_budget!r} vs {theirs[2]!r}",
            )
            if mine.h_budget != float(int(mine.h_budget)):
                non_integral_budget += 1
            compared += 1
    require(
        compared > 0,
        "the residual transcript was compared against the frozen entry point on "
        "no state, so the bit-identity check is vacuous",
    )
    require(
        bits_seen == (1 << FROZEN_WIDTH) - 1,
        f"the residual fixture's stride never varied every ticker: the sampled "
        f"states leave {FROZEN_WIDTH - bin(bits_seen).count('1')} of "
        f"{FROZEN_WIDTH} tickers at their initial value",
    )
    require(
        non_integral_budget > 0,
        "no synthetic instance produced a non-integral budget residual, so any "
        "rounding of it would be invisible and this fixture would be vacuous",
    )
    require(
        non_integral_sector > 0,
        "no synthetic instance produced a non-integral sector residual, so any "
        "rounding of it would be invisible and this fixture would be vacuous",
    )


def main() -> None:
    fixture_condition_map_matches_d013()
    print("  [OK ] the D013 active/inactive map, axes and retained widths")
    fixture_csb_frozen_bit_identical()
    fixture_csb_frozen_domain_and_reconstruction()
    print("  [OK ] CSB is bit-identical to src/g4 over the full 2^20 decoded domain")
    for label, inst in EVALUATED_INSTANCES:
        fixture_inactive_is_exact_positive_zero(inst, label)
        fixture_negative_zero_would_be_visible(inst, label)
    for label, inst in SMALL_INSTANCES:
        fixture_feasible_predicate_matches_d013()
        fixture_accumulation_order(inst, label)
        fixture_symbolic_multiplicity(inst, label)
        fixture_retained_register_multiplies(inst, label)
    fixture_zero_accumulator_was_reached()
    fixture_residuals_are_bit_identical_to_frozen()
    print("  [OK ] +0.0 inactivity, the -0.0 sign case, |T_E| = base * 2^w, RETAINED registers")
    print("  [OK ] the residual transcript is bit-identical to frozen src.g4.residuals")
    fixture_no_raw_enumeration_in_source()
    print("  [OK ] no raw 2^39 enumeration: the register is counted, never iterated")
    fixture_typed_refusals()
    fixture_empty_feasible_set_is_a_hard_stop()
    fixture_empty_feasible_set_from_filtered_states()
    print("  [OK ] typed refusals: bad names, bad types, -0.0, active zeros, empty F_q")
    fixture_trust_boundary_fuzz()
    fixture_delegated_failures_are_typed()
    fixture_delegated_boundary_is_load_bearing()
    print(
        "  [OK ] trust-boundary fuzz: every field of every public entry point "
        "refused with the typed error; delegated failures converted and chained"
    )
    for label, inst in SMALL_INSTANCES:
        fixture_slow_reference_agreement(inst, label)
    fixture_labels_are_actually_exercised()
    print("  [OK ] the independent slow reference agrees on all four conditions")
    print("PASS synthetic D013 +0.0 inactive-family fixtures; no writes, no real instance")


if __name__ == "__main__":
    main()
