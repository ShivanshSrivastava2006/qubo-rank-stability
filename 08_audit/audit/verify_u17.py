#!/usr/bin/env python3
"""U-17 verifier: mixed decoded tie-set semantics.

The proposed primary partition is:
    exists C -> C; else all A -> A; else B.
It is defined over DISTINCT DECODED PORTFOLIOS, not raw auxiliary-register states.
The printed case proof applies to every nonempty finite decoded tie set; bounded enumeration
is only a regression sanity check.
"""
import itertools
import sys

FAIL = []


def chk(label, got, want=True):
    ok = got == want
    if not ok:
        FAIL.append(f"{label}: got {got!r}, expected {want!r}")
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}")


def hdr(title):
    print("\n" + "=" * 76)
    print(title)
    print("=" * 76)


def classify(labels):
    """Classify labels of one nonempty, distinct decoded tie set."""
    if not labels:
        raise ValueError("decoded tie set cannot be empty")
    if any(label == "C" for label in labels):
        return "C"
    if all(label == "A" for label in labels):
        return "A"
    return "B"


def c_universal(labels):
    return all(label == "C" for label in labels)


def c_existential(labels):
    return any(label == "C" for label in labels)


def fractions(labels):
    if not labels:
        raise ValueError("decoded tie set cannot be empty")
    n = len(labels)
    return {label: labels.count(label) / n for label in "ABC"}


def deduplicate_raw(raw_states):
    """Collapse raw states (state_id, decoded_x, atomic_label) by decoded portfolio."""
    by_x = {}
    for _, decoded_x, atomic_label in raw_states:
        previous = by_x.setdefault(decoded_x, atomic_label)
        if previous != atomic_label:
            raise ValueError("one decoded portfolio received conflicting atomic labels")
    return list(by_x.values())


hdr("1. General partition proof")
print("  For nonempty X: either exists C; otherwise either all A or some B.")
print("  These three cases are mutually exclusive and exhaustive, so the rule partitions every")
print("  nonempty finite decoded tie set. The checks below are finite regression witnesses only.")

hdr("2. Bounded composition sanity check")
compositions = sorted({tuple(sorted(c))
                       for n in range(1, 9)
                       for c in itertools.product("ABC", repeat=n)})
labels = {c: classify(list(c)) for c in compositions}
chk("every bounded composition receives A, B, or C", all(v in "ABC" for v in labels.values()))
chk("A iff every decoded portfolio is atomically A",
    all((labels[c] == "A") == all(v == "A" for v in c) for c in compositions))
chk("C iff at least one decoded portfolio is atomically C",
    all((labels[c] == "C") == any(v == "C" for v in c) for c in compositions))
chk("B iff no C exists and not all decoded portfolios are A",
    all((labels[c] == "B") == (not any(v == "C" for v in c) and not all(v == "A" for v in c))
        for c in compositions))
chk("universal feasibility equals not existential C",
    all((labels[c] != "C") == (not c_existential(list(c))) for c in compositions))
print(f"  regression enumeration: {len(compositions)} multiset compositions (sizes 1-8)")

hdr("3. Deduplicate decoded portfolios before every classification")
raw = [
    ("z0", "x_feasible_optimal", "A"),
    ("z1", "x_feasible_optimal", "A"),  # distinct auxiliary state, same portfolio
    ("z2", "x_infeasible", "C"),
]
decoded = deduplicate_raw(raw)
chk("raw multiplicity is retained as a separate diagnostic", len(raw), 3)
chk("classification denominator is distinct decoded portfolios", len(decoded), 2)
chk("primary label uses decoded set, not raw state count", classify(decoded), "C")
frac = fractions(decoded)
chk("C fractional diagnostic is 1/2, not raw-state 1/3", frac["C"], 0.5)
chk("full fractional A/B/C diagnostics sum to one", sum(frac.values()), 1.0)
print(f"  decoded fractions: A={frac['A']:.3f}, B={frac['B']:.3f}, C={frac['C']:.3f}")

hdr("4. C estimands are distinct diagnostics")
for c in [("A",), ("C",), ("A", "C"), ("A", "B"), ("B", "C"), ("A", "B", "C")]:
    p = fractions(list(c))
    print(f"  {'+'.join(c):<5} primary={classify(list(c))}  C_univ={c_universal(list(c))!s:<5} "
          f"C_exist={c_existential(list(c))!s:<5} p_A={p['A']:.3f} p_B={p['B']:.3f} p_C={p['C']:.3f}")
chk("universal and existential C differ on mixed C sets",
    c_universal(["A", "C"]) != c_existential(["A", "C"]))
chk("fractional diagnostics are a partition over atomic decoded labels",
    all(sum(fractions(list(c)).values()) == 1.0 for c in compositions))

print("\n" + "=" * 76)
if FAIL:
    print(f"RESULT: {len(FAIL)} CHECK(S) FAILED")
    for failure in FAIL:
        print("  - " + failure)
    sys.exit(1)
print("RESULT: ALL CHECKS PASSED")
print("=" * 76)
