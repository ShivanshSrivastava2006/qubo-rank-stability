"""Gate-5 producer checks for the prepared Python §5.2 evaluator.

This is conformance evidence for the performance-only clause-(c) repair.  It
does not search for a minimum, construct a tie set, classify a primary state,
or execute a grid pass.
"""

from __future__ import annotations

import itertools
import json
import math
from pathlib import Path
import random
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.g4.verify_g4_energy import load_review
from src.g4.energy import (
    PreparedCoefficients,
    PreparedDecodedState,
    prepare_coefficients,
    prepare_decoded_state,
    prepare_instance,
    prepare_slack_state,
    slack_energy_prepared,
    unbalanced_energy_prepared,
)
from src.g4.instance import load_instance
from src.g4.parameters import load_coefficients
from src.g5.certify import decode_x_e


INSTANCE_PATH = ROOT / "research/canonical/stage1_instance.json"
LEDGER_PATH = ROOT / "research/g4/G4_PRIMARY_LEDGER.json"
VECTOR_PATH = ROOT / "research/g5/worker_self_test.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _vector_states() -> list[tuple[int, ...]]:
    payload = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))
    states = []
    seen = set()
    for case in payload["cases"]:
        state = tuple(case["state_bits"])
        if state not in seen:
            seen.add(state)
            states.append(state)
    return states


def _auxiliary(state: tuple[int, ...], ordinal: int) -> tuple[int, ...]:
    mask = sum((bit << index) for index, bit in enumerate(state))
    return tuple((mask >> ((index + ordinal) % 20)) & 1 for index in range(19))


def check_exactness() -> None:
    instance = load_instance(INSTANCE_PATH)
    prepared_instance = prepare_instance(instance)
    review = load_review()
    feasible = review.feasible_states(instance)
    require(len(feasible) == 976, f"unexpected feasible population: {len(feasible)}")
    infeasible = review.infeasible_sample(
        instance, feasible, 2_000, random.Random(review.SEED)
    )
    states = feasible + [state for state, _ in infeasible]
    prepared_states = {state: prepare_decoded_state(prepared_instance, state) for state in states}
    cached = {
        state: (review.objective_value(instance, state), review.residual_triple(instance, state))
        for state in states
    }

    triples = {(index, index, index) for index in range(61)}
    triples.update(itertools.product((0, 30, 60), repeat=3))
    comparisons = 0
    for card_index, sector_index, budget_index in sorted(triples):
        raw_coefficients = load_coefficients(
            LEDGER_PATH, card_index, sector_index, budget_index
        )
        coefficients = prepare_coefficients(raw_coefficients)
        for ordinal, state in enumerate(states):
            decoded = prepared_states[state]
            auxiliary = _auxiliary(state, ordinal)
            slack_reference = review.slack_energy(
                instance, state, auxiliary, raw_coefficients, cached[state]
            )
            slack_produced = slack_energy_prepared(
                prepare_slack_state(decoded, auxiliary), coefficients
            )
            require(
                slack_produced.hex() == slack_reference.hex(),
                "prepared slack energy differs from independent §5.2 transcription "
                f"at {(card_index, sector_index, budget_index)} state {ordinal}",
            )
            unbalanced_reference = review.unbalanced_energy(
                instance, state, raw_coefficients, cached[state]
            )
            unbalanced_produced = unbalanced_energy_prepared(decoded, coefficients)
            require(
                unbalanced_produced.hex() == unbalanced_reference.hex(),
                "prepared unbalanced energy differs from independent §5.2 transcription "
                f"at {(card_index, sector_index, budget_index)} state {ordinal}",
            )
            comparisons += 2
    print(
        "PASS prepared evaluator bit-exact against pinned independent §5.2 oracle: "
        f"{comparisons} energies, {len(triples)} coefficient triples, {len(states)} states"
    )


def check_fail_closed() -> None:
    instance = load_instance(INSTANCE_PATH)
    state = tuple(0 for _ in range(20))
    prepared_instance = prepare_instance(instance)
    decoded = prepare_decoded_state(prepared_instance, state)
    coefficients = prepare_coefficients(load_coefficients(LEDGER_PATH, 0, 0, 0))

    probes = (
        lambda: prepare_decoded_state(instance, state),
        lambda: prepare_decoded_state(prepared_instance, state[:-1]),
        lambda: prepare_slack_state(decoded, tuple(0 for _ in range(18))),
        lambda: slack_energy_prepared(decoded, coefficients),
        lambda: unbalanced_energy_prepared(decoded, coefficients.coefficients),
        lambda: PreparedDecodedState(
            float("nan"), 0.0, 0.0, (0.0,) * 4, (0.0,) * 4, 0.0, 0.0
        ),
        lambda: PreparedCoefficients(object()),
    )
    for index, probe in enumerate(probes):
        try:
            probe()
        except (TypeError, ValueError):
            continue
        raise AssertionError(f"prepared-path fail-closed probe {index} was accepted")
    print(f"PASS prepared evaluator fails closed on {len(probes)} malformed inputs")


def check_decode_linear_path() -> None:
    distinct = [(index,) for index in range(20_000)]
    raw = [(value, None) for value in distinct + distinct[::7]]
    start = time.perf_counter()
    decoded = decode_x_e(raw, lambda item: item[0])
    elapsed = time.perf_counter() - start
    require(decoded == distinct, "linear decoder changed first-seen deduplication semantics")
    require(elapsed < 1.0, f"decoded-state deduplication is unexpectedly slow: {elapsed:.3f}s")
    try:
        decode_x_e([([0], None)], lambda item: item[0])
    except TypeError:
        pass
    else:
        raise AssertionError("non-hashable decoded state did not fail closed")
    print(f"PASS decoded-state deduplication: 22,858 inputs in {elapsed:.6f}s")


def measure_fast_path() -> None:
    instance = load_instance(INSTANCE_PATH)
    prepared_instance = prepare_instance(instance)
    raw_coefficients = load_coefficients(LEDGER_PATH, 60, 60, 60)
    coefficients = prepare_coefficients(raw_coefficients)
    states = _vector_states()
    decoded = [prepare_decoded_state(prepared_instance, state) for state in states]
    slack = [
        prepare_slack_state(value, _auxiliary(state, ordinal))
        for ordinal, (state, value) in enumerate(zip(states, decoded))
    ]

    repeats = 2_000
    timings = {}
    checksum = 0.0
    for label, values, evaluate in (
        ("slack", slack, lambda value: slack_energy_prepared(value, coefficients)),
        ("unbalanced", decoded, lambda value: unbalanced_energy_prepared(value, coefficients)),
    ):
        start = time.perf_counter()
        for _ in range(repeats):
            for value in values:
                checksum += evaluate(value)
        calls = repeats * len(values)
        timings[label] = (time.perf_counter() - start) / calls * 1e6
    require(math.isfinite(checksum), "benchmark checksum is nonfinite")
    print(
        "MEASURED prepared Python cost: "
        + ", ".join(f"{label}={value:.3f} us/call" for label, value in timings.items())
    )


def main() -> int:
    check_exactness()
    check_fail_closed()
    check_decode_linear_path()
    measure_fast_path()
    print("PASS Gate-5 Python evaluator repair checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
