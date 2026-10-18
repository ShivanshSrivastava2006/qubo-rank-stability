"""Independent bounded conformance evidence for frozen M5, V-4, and V-8.

Only isolated toy instances are enumerated.  The largest encoded toy below has
six total variables, below the authorized maximum of 22.  Nothing in this file
loads the primary instance, primary ledger, ADNYE records, encoded-energy
service, or a ground-state-search result.
"""

from __future__ import annotations

from itertools import product
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.g4.classification import DecodedClassifier, OriginalObjectiveService


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def bits(width: int):
    return product((0, 1), repeat=width)


def check_behavioral_isolation() -> None:
    """Exercise the actual callable boundary with strict injected capabilities."""
    calls: list[tuple[str, tuple[int, ...], float | None]] = []

    def objective(x: tuple[int, ...]) -> float:
        require(type(x) is tuple, "objective received something other than decoded x")
        calls.append(("objective", x, None))
        return -float(sum((index + 1) * bit for index, bit in enumerate(x)))

    def feasible(x: tuple[int, ...]) -> bool:
        require(type(x) is tuple, "predicate received something other than decoded x")
        calls.append(("feasible", x, None))
        return sum(x) == 1

    classifier = DecodedClassifier(OriginalObjectiveService(objective, 4.0), feasible)
    decoded = (1, 0, 0)
    require(classifier.label(decoded, -1.0) == "A", "isolated decoded A case failed")
    require(calls == [("feasible", decoded, None), ("objective", decoded, None)],
            "classifier crossed the injected decoded-service boundary")

    # Public calls cannot smuggle an encoded energy, encoding identity, raw
    # auxiliary state, or search output into the classifier.  These are live
    # behavioral calls, not source/module-name assertions.
    forbidden = (
        {"encoded_energy": -99.0},
        {"encoding": "slack"},
        {"auxiliary": (0, 1)},
        {"ground_state": object()},
    )
    for extra in forbidden:
        try:
            classifier.label(decoded, -1.0, **extra)
        except TypeError:
            pass
        else:
            raise AssertionError(f"classifier accepted prohibited input {tuple(extra)}")

    # External encoding context cannot change a call for which the complete
    # decoded input is identical, because there is no context-bearing slot.
    labels = []
    for external_context in ("slack", "unbalanced"):
        require(external_context in ("slack", "unbalanced"), "bad test fixture")
        labels.append(classifier.label(decoded, -1.0))
    require(labels == ["A", "A"], "external encoding context affected a decoded label")
    print("PASS M5 behavioral isolation: only decoded x/f* and injected original services cross the boundary")


def check_d015_comparator_boundary() -> None:
    """Pin immediately-inside, equality, and immediately-outside decisions.

    This fixture is independently derived from frozen §5.3, rather than by
    asking the production comparator for an expected tolerance.  Choose
    ``f*=0``, ``Lambda_ref=2^41-1``, and a comparison gap of exactly 1.  Then

        m = 1
        scale = fl((2^41-1) + 1) = 2^41
        c_f*epsilon = 2048*2^-52 = 2^-41
        tau = fl(2^-41 * 2^41) = 1 exactly.

    The adjacent binary64 gaps around 1 are nextafter(1,0) and
    nextafter(1,+inf).  Adding either to ``2^41-1`` also rounds to ``2^41``:
    an ulp at that scale is ``2^-11``, whereas their displacement from 1 is at
    most ``2^-52``.  Thus tau stays exactly 1 for all three cases, giving the
    independently fixed expected decisions inside/on/outside = A/A/B.  The
    equality case pins ``<=``; the three cases jointly distinguish the frozen
    c_f, epsilon, addition, and max operations from Claude's five mutations.
    """
    lambda_ref = float((1 << 41) - 1)
    expected_scale = float(1 << 41)
    inside = math.nextafter(1.0, 0.0)
    on = 1.0
    outside = math.nextafter(1.0, math.inf)
    require(inside.hex() == "0x1.fffffffffffffp-1", "unexpected inside-neighbour binary64")
    require(on.hex() == "0x1.0000000000000p+0", "unexpected equality binary64")
    require(outside.hex() == "0x1.0000000000001p+0", "unexpected outside-neighbour binary64")
    require(all(lambda_ref + gap == expected_scale for gap in (inside, on, outside)),
            "constructed D015 scales do not round to 2^41")
    independently_derived_tau = math.ldexp(1.0, -41) * expected_scale
    require(independently_derived_tau == 1.0,
            "constructed D015 boundary tolerance is not exactly one")

    states = ((0, 0, 1), (0, 1, 0), (1, 0, 0))
    values = dict(zip(states, (inside, on, outside)))

    def objective(decoded: tuple[int, ...]) -> float:
        return values[decoded]

    classifier = DecodedClassifier(
        OriginalObjectiveService(objective, lambda_ref),
        lambda decoded: True,
    )
    produced = tuple(classifier.label(decoded, 0.0) for decoded in states)
    require(produced == ("A", "A", "B"),
            f"D015 inside/on/outside decisions changed: {produced!r}")
    print("PASS D015 comparator boundary: adjacent inside/on/outside gaps give A/A/B at exact tau=1")


def check_v8() -> None:
    """Hand-constructed A/B/C cases, isolated violations, and boundaries."""
    sectors = ((0, 1), (2, 3), (4, 5), (6, 7))
    prices = (0, 5, 0, 6, 5, 6, 0, 6)
    weights = (-8, -1, -7, -2, -3, -4, -5, -6)
    k, cap, budget = 2, 1, 10

    def objective(x: tuple[int, ...]) -> float:
        return float(sum(weight * bit for weight, bit in zip(weights, x)))

    def feasible(x: tuple[int, ...]) -> bool:
        return (sum(x) == k
                and all(sum(x[i] for i in members) <= cap for members in sectors)
                and sum(price * bit for price, bit in zip(prices, x)) <= budget)

    def x(*selected: int) -> tuple[int, ...]:
        return tuple(int(index in selected) for index in range(8))

    def violations(decoded: tuple[int, ...]) -> frozenset[str]:
        found = set()
        if sum(decoded) != k:
            found.add("cardinality")
        if any(sum(decoded[i] for i in members) > cap for members in sectors):
            found.add("sector")
        if sum(price * bit for price, bit in zip(prices, decoded)) > budget:
            found.add("budget")
        return frozenset(found)

    optimum = x(0, 2)
    f_star = objective(optimum)
    classifier = DecodedClassifier(OriginalObjectiveService(objective, 20.0), feasible)
    cases = {
        "feasible-optimal": (optimum, "A"),
        "feasible-suboptimal": (x(0, 4), "B"),
        "cardinality K-1 only": (x(0), "C"),
        "cardinality K+1 only": (x(0, 2, 6), "C"),
        "sector C+1 only": (x(0, 1), "C"),
        "budget B+1 only": (x(1, 5), "C"),
        "simultaneous cardinality+budget": (x(1, 3, 6), "C"),
        "simultaneous cardinality+sector+budget": (x(0, 1, 5), "C"),
        "sector boundary n_j=C": (x(0, 4), "B"),
        "budget boundary p'x=B": (x(1, 4), "B"),
    }
    for name, (decoded, expected) in cases.items():
        require(classifier.label(decoded, f_star) == expected, f"V-8 failed: {name}")

    expected_violations = {
        "cardinality K-1 only": frozenset(("cardinality",)),
        "cardinality K+1 only": frozenset(("cardinality",)),
        "sector C+1 only": frozenset(("sector",)),
        "budget B+1 only": frozenset(("budget",)),
        "simultaneous cardinality+budget": frozenset(("cardinality", "budget")),
        "simultaneous cardinality+sector+budget": frozenset(("cardinality", "sector", "budget")),
    }
    for name, expected in expected_violations.items():
        require(violations(cases[name][0]) == expected,
                f"V-8 fixture does not isolate the declared violation set: {name}")

    require(sum(x(0)) == k - 1 and sum(x(0, 2, 6)) == k + 1,
            "V-8 cardinality boundaries were not exercised")
    require(sum(x(0, 4)[i] for i in sectors[0]) == cap,
            "V-8 sector equality boundary was not exercised")
    require(sum(x(0, 1)[i] for i in sectors[0]) == cap + 1,
            "V-8 sector violation boundary was not exercised")
    require(sum(price * bit for price, bit in zip(prices, x(1, 4))) == budget,
            "V-8 budget equality boundary was not exercised")
    require(sum(price * bit for price, bit in zip(prices, x(1, 5))) == budget + 1,
            "V-8 budget violation boundary was not exercised")

    require(classifier.label_set((optimum, optimum), f_star) == "A", "all-A set failed")
    require(classifier.label_set((optimum, x(0, 4)), f_star) == "B", "A+B set failed")
    require(classifier.label_set((optimum, x(1, 5)), f_star) == "C", "A+C set failed")
    require(classifier.label_set((x(0, 4), x(1, 5)), f_star) == "C", "B+C set failed")
    print("PASS V-8 hand-constructed decoded A/B/C cases and stated boundaries")


def _toy_ties(energies: dict[tuple[int, ...], float], lambda_ref: float) -> set[tuple[int, ...]]:
    minimum = min(energies.values())
    tied = set()
    for state, value in energies.items():
        gap = abs(value - minimum)
        scale = lambda_ref + max(abs(value), abs(minimum))
        tolerance = (2048.0 * math.ldexp(1.0, -52)) * scale
        if gap <= tolerance:
            tied.add(state)
    return tied


def check_v4_isolated_toy() -> None:
    """Compare an independent full raw oracle with a closed-form toy path."""
    n_assets, auxiliary_bits = 4, 2
    require(n_assets + auxiliary_bits <= 22, "V-4 toy exceeds the authorized variable cap")
    k, budget = 2, 2
    prices = (1, 1, 1, 1)
    alpha, slack_weight, lambda_ref = 4.0, 2.0, 4.0

    # Independent oracle: enumerate every raw encoded assignment and evaluate
    # the literal square expressions.  It does not call the closed-form path.
    raw_energies: dict[tuple[int, ...], float] = {}
    for raw in bits(n_assets + auxiliary_bits):
        x = raw[:n_assets]
        y = raw[n_assets:]
        selected = sum(x)
        register = y[0] + 2 * y[1]
        objective = -float(selected)
        raw_energies[raw] = (objective
                             + alpha * float((selected - k) * (selected - k))
                             + slack_weight * float((budget - selected - register) ** 2))
    oracle_ties = _toy_ties(raw_energies, lambda_ref)

    # Optimized path: enumerate decoded states only and derive the unique exact
    # integer slack minimizer by clamp.  Its implementation shares no helper
    # with the full raw oracle above.
    optimized_energies: dict[tuple[int, ...], float] = {}
    optimized_raw: dict[tuple[int, ...], tuple[int, ...]] = {}
    for decoded in bits(n_assets):
        count = sum(decoded)
        residual = budget - count
        register = min(max(residual, 0), 3)
        auxiliary = (register & 1, (register >> 1) & 1)
        optimized_raw[decoded] = decoded + auxiliary
        optimized_energies[decoded] = (-float(count)
                                       + alpha * float((count - k) * (count - k))
                                       + slack_weight * float((residual - register) ** 2))
    optimized_decoded_ties = _toy_ties(optimized_energies, lambda_ref)
    optimized_ties = {optimized_raw[decoded] for decoded in optimized_decoded_ties}
    require(oracle_ties == optimized_ties, "V-4 raw and closed-form full tie sets differ")

    def toy_objective(decoded: tuple[int, ...]) -> float:
        return -float(sum(decoded))

    def toy_feasible(decoded: tuple[int, ...]) -> bool:
        return sum(decoded) == k and sum(prices[i] * decoded[i] for i in range(n_assets)) <= budget

    classifier = DecodedClassifier(OriginalObjectiveService(toy_objective, lambda_ref), toy_feasible)
    decoded_ties = {raw[:n_assets] for raw in oracle_ties}
    require(classifier.label_set(decoded_ties, -2.0) == "A",
            "V-4 toy decoded tie set did not pass through the isolated classifier")
    print("PASS V-4 isolated toy: independent full raw and closed-form tie sets agree (6 total variables)")


def check_fail_closed() -> None:
    good_objective = lambda x: float(sum(x))
    good_feasible = lambda x: True
    for lambda_ref in (0.0, -1.0, float("nan"), float("inf")):
        try:
            OriginalObjectiveService(good_objective, lambda_ref)
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError("invalid Lambda_ref did not fail closed")
    classifier = DecodedClassifier(OriginalObjectiveService(good_objective, 1.0), good_feasible)
    for decoded in ((), (0, 2), (True, 0)):
        try:
            classifier.label(decoded, 0.0)
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError("malformed decoded x did not fail closed")
    for f_star in (float("nan"), float("inf")):
        try:
            classifier.label((0, 1), f_star)
        except ValueError:
            pass
        else:
            raise AssertionError("nonfinite f* did not fail closed")
    bad_predicate = DecodedClassifier(OriginalObjectiveService(good_objective, 1.0), lambda x: 1)
    try:
        bad_predicate.label((0, 1), 1.0)
    except TypeError:
        pass
    else:
        raise AssertionError("non-Boolean feasibility response did not fail closed")
    bad_objective = DecodedClassifier(OriginalObjectiveService(lambda x: float("nan"), 1.0), good_feasible)
    try:
        bad_objective.label((0, 1), 1.0)
    except ValueError:
        pass
    else:
        raise AssertionError("nonfinite objective response did not fail closed")
    try:
        classifier.label_set((), 0.0)
    except ValueError:
        pass
    else:
        raise AssertionError("empty decoded set did not fail closed")
    print("PASS malformed, nonfinite, invalid-service, and empty-set inputs fail closed")


def main() -> int:
    check_behavioral_isolation()
    check_d015_comparator_boundary()
    check_v8()
    check_v4_isolated_toy()
    check_fail_closed()
    print("RESULT: PASS — bounded M5/V-4/V-8 conformance only; no primary-instance certification,")
    print("        tie computation, classification result, sweep, experiment, or Gate-5 work")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
