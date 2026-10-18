"""Claude independent G4 review probe — energy-formulation conformance only.

WHY THIS EXISTS.  `research/g4/verify_g4_conformance.py` compares each produced
QUBO against an in-file "oracle" whose `add_oracle_square` / `add_oracle_zeta` /
`add_oracle_objective` bodies are line-for-line copies of the producer's own
`slack._add_square`, `unbalanced._add_zeta`, and `objective.add_qubo_terms`.  A
shared expansion error would be reproduced identically on both sides and pass.
It also never calls `Qubo.energy`, so the drift figure quoted in
`G4_PROVENANCE.md` has no reproducible witness in the shipped package.

This probe closes both gaps from the reviewer side.  It transcribes the frozen
`FROZEN_MATH_SPEC.md` section 5.2 residual-form energy directly from the
specification text -- deliberately not importing the producer's penalty
assembly -- and compares it against the expanded-matrix accumulation over real
states.  Agreement at every state is independent evidence that the expansion
algebra is right; the residual gap it measures is the binary64 cancellation
drift, reported against the D015 `tau` at `c_H = 2048` for scale.

SCOPE.  Bounded G4 conformance review under the 2026-08-25 authorization.  It
performs NO ground-state search, computes NO minimum, forms NO tie set, applies
NO A/B/C classification, and runs NO grid sweep.  Drift is reported, never
compared against a pass threshold of its own invention: the numerical rule
belongs to D015, not to this script.

Read-only.  Writes nothing.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.g4.instance import load_instance
from src.g4.parameters import load_coefficients
from src.g4 import slack, unbalanced

INSTANCE_PATH = ROOT / "research/canonical/stage1_instance.json"
LEDGER_PATH = ROOT / "research/g4/G4_PRIMARY_LEDGER.json"
ADNYE_001 = ROOT / "research/adnye/ADNYE-001_Lambda_ref.json"

EPSILON = 2.0 ** -52
C_H = 2048
INFEASIBLE_SAMPLE = 2000
SEED = 20260825
# Derived, not chosen. The largest expanded-vs-residual cancellation drift observed
# across all 61 rows and both populations is ~1.4e-09 absolute; the tolerance below
# exceeds that by ~7x at the smallest energy scale in play, so real rounding never
# trips it, while any relative coefficient error at or above ~1e-8 is caught. An
# independent audit (0xalpha, 2026-08-26) measured the previous 1.0e-6 value letting
# relative lambda_2 perturbations up to 1e-7 escape, and noted the constant was a
# judgement rather than a derivation; this replaces it with the derived bound. Note
# that the bit-exactness check performed separately is far stricter than this gate --
# this is a backstop against gross algebra errors, not the primary evidence.
ALGEBRA_TOLERANCE = 1.0e-8


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


# --- independent transcription of frozen section 5.2 ------------------------

def objective_value(instance, x):
    """mu_term[1..20] then quad_term[1,1]..quad_term[20,20], accumulator at +0.0."""
    acc = 0.0
    for i in range(20):
        acc = acc + (-(instance.mu[i] * float(x[i])))
    for i in range(20):
        for k in range(20):
            acc = acc + (instance.kappa_risk * ((instance.sigma[i][k] * float(x[i])) * float(x[k])))
    return acc


def residual_triple(instance, x):
    """h_card = sum-K; h_sector,j = C-n_j; h_budget = B-p^T x, in frozen order."""
    card_sum = 0.0
    for i in range(20):
        card_sum = card_sum + float(x[i])
    h_card = card_sum - float(instance.K)
    h_sector = []
    for members in instance.sectors:
        sector_sum = 0.0
        for i in sorted(members):
            sector_sum = sector_sum + float(x[i])
        h_sector.append(float(instance.C) - sector_sum)
    budget_sum = 0.0
    for i in range(20):
        budget_sum = budget_sum + (instance.prices[i] * float(x[i]))
    return h_card, tuple(h_sector), instance.B - budget_sum


def slack_energy(instance, x, auxiliary, coefficients, cached):
    f_value, (h_card, h_sector, h_budget) = cached
    energy = f_value
    energy = energy + (coefficients.alpha * (h_card * h_card))
    offset = 0
    for j in range(4):
        register = 0.0
        for d in range(slack.SECTOR_BITS):
            register = register + (float(1 << d) * float(auxiliary[offset + d]))
        offset += slack.SECTOR_BITS
        delta = h_sector[j] - register
        energy = energy + (coefficients.sector_slack * (delta * delta))
    register = 0.0
    for d in range(slack.BUDGET_BITS):
        register = register + (float(1 << d) * float(auxiliary[offset + d]))
    delta = h_budget - register
    return energy + (coefficients.budget_slack * (delta * delta))


def unbalanced_energy(instance, x, coefficients, cached):
    f_value, (h_card, h_sector, h_budget) = cached
    energy = f_value + (coefficients.alpha * (h_card * h_card))
    for j in range(4):
        h = h_sector[j]
        energy = energy + ((-(coefficients.sector_linear * h)) + (coefficients.sector_quadratic * (h * h)))
    h = h_budget
    return energy + ((-(coefficients.budget_linear * h)) + (coefficients.budget_quadratic * (h * h)))


def tau(value, lambda_ref, c=C_H):
    """D015 tolerance scale at a single energy; not a tie test."""
    return (c * EPSILON) * (lambda_ref + abs(value))


# --- state construction -----------------------------------------------------

def feasible_states(instance):
    """Predicate written here, independent of src/g4.constraints."""
    states = []
    for mask in range(1 << 20):
        x = tuple((mask >> i) & 1 for i in range(20))
        if sum(x) != instance.K:
            continue
        if any(sum(x[i] for i in members) > instance.C for members in instance.sectors):
            continue
        if sum(instance.prices[i] * x[i] for i in range(20)) > instance.B:
            continue
        states.append(x)
    return states


def exact_lift(instance, x):
    """The C_slack lift: every auxiliary register is the exact minimizer."""
    _, h_sector, h_budget = residual_triple(instance, x)
    bits = []
    for j in range(4):
        value = int(h_sector[j])
        require(float(value) == h_sector[j] and 0 <= value < (1 << slack.SECTOR_BITS),
                f"sector residual {h_sector[j]!r} is not exactly representable")
        bits += [(value >> d) & 1 for d in range(slack.SECTOR_BITS)]
    value = int(h_budget)
    require(float(value) == h_budget and 0 <= value < (1 << slack.BUDGET_BITS),
            f"budget residual {h_budget!r} is not exactly representable")
    bits += [(value >> d) & 1 for d in range(slack.BUDGET_BITS)]
    return tuple(bits)


def infeasible_sample(instance, feasible, count, rng):
    known = set(feasible)
    states = []
    while len(states) < count:
        x = tuple(rng.randint(0, 1) for _ in range(20))
        if x not in known:
            states.append((x, tuple(rng.randint(0, 1) for _ in range(slack.variable_count() - 20))))
    return states


def main() -> int:
    instance = load_instance(INSTANCE_PATH)
    lambda_ref = float(json.loads(ADNYE_001.read_text(encoding="utf-8"))["value"])
    require(math.isfinite(lambda_ref) and lambda_ref > 0.0, "Lambda_ref must be finite and positive")

    feasible = feasible_states(instance)
    require(len(feasible) == 976, f"unexpected feasible population {len(feasible)}")
    rng = random.Random(SEED)
    infeasible = infeasible_sample(instance, feasible, INFEASIBLE_SAMPLE, rng)

    cached = {x: (objective_value(instance, x), residual_triple(instance, x))
              for x in feasible}
    lifts = {x: exact_lift(instance, x) for x in feasible}
    for x, _ in infeasible:
        if x not in cached:
            cached[x] = (objective_value(instance, x), residual_triple(instance, x))

    rows = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))["grid_rule"]["N_axis"]
    # Track the largest absolute gap and the largest gap/tau ratio separately: they
    # occur at different states, and only the ratio speaks to whether drift could
    # reach the D015 comparison scale.
    keys = ("slack_feasible", "unbalanced_feasible", "slack_infeasible", "unbalanced_infeasible")
    worst_gap = {key: (0.0, None) for key in keys}
    worst_ratio = {key: (0.0, None) for key in keys}

    for index in range(rows):
        coefficients = load_coefficients(LEDGER_PATH, index, index, index)
        slack_qubo = slack.formulate(instance, coefficients)
        unbalanced_qubo = unbalanced.formulate(instance, coefficients)
        for label, states in (("feasible", [(x, lifts[x]) for x in feasible]),
                              ("infeasible", infeasible)):
            for x, auxiliary in states:
                reference = slack_energy(instance, x, auxiliary, coefficients, cached[x])
                expanded = slack_qubo.energy(tuple(x) + tuple(auxiliary))
                require(math.isfinite(reference) and math.isfinite(expanded),
                        f"nonfinite slack energy at row {index}")
                gap = abs(reference - expanded)
                require(gap <= ALGEBRA_TOLERANCE * (1.0 + abs(reference)),
                        f"slack expansion disagrees with section 5.2 at row {index}: "
                        f"{reference!r} vs {expanded!r}")
                key = f"slack_{label}"
                ratio = gap / tau(reference, lambda_ref)
                if gap > worst_gap[key][0]:
                    worst_gap[key] = (gap, index)
                if ratio > worst_ratio[key][0]:
                    worst_ratio[key] = (ratio, index)

                reference = unbalanced_energy(instance, x, coefficients, cached[x])
                expanded = unbalanced_qubo.energy(tuple(x))
                require(math.isfinite(reference) and math.isfinite(expanded),
                        f"nonfinite unbalanced energy at row {index}")
                gap = abs(reference - expanded)
                require(gap <= ALGEBRA_TOLERANCE * (1.0 + abs(reference)),
                        f"unbalanced expansion disagrees with section 5.2 at row {index}: "
                        f"{reference!r} vs {expanded!r}")
                key = f"unbalanced_{label}"
                ratio = gap / tau(reference, lambda_ref)
                if gap > worst_gap[key][0]:
                    worst_gap[key] = (gap, index)
                if ratio > worst_ratio[key][0]:
                    worst_ratio[key] = (ratio, index)

    print(f"PASS both expanded QUBOs reproduce the independent section 5.2 residual-form energy")
    print(f"     over {len(feasible)} feasible lifts and {len(infeasible)} infeasible states "
          f"at all {rows} primary rows")
    print()
    print("REPORTED (not a pass/fail criterion) — expanded-vs-residual binary64 drift,")
    print(f"     against the D015 tau at c_H={C_H}:")
    for key in keys:
        gap, gap_row = worst_gap[key]
        ratio, ratio_row = worst_ratio[key]
        print(f"     {key:22s} max gap {gap:.12e} (row {gap_row})"
              f"   max gap/tau {ratio:10.1f} (row {ratio_row})")
    print()
    print("RESULT: PASS — bounded G4 energy-formulation review only; no search, minimum,")
    print("        tie set, classification, or sweep was computed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
