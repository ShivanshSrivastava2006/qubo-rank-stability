#!/usr/bin/env python3
"""
G2 conformance test — D005 native-violation rule on the canonical Stage-1 instance.

D005: `v_ref,j` is the SMALLEST ATTAINABLE POSITIVE NATIVE VIOLATION of constraint family j
over the declared primary decision domain `x in {0,1}^20`. It is explicitly NOT gcd-defined;
the gcd is only a lower bound.

Residual conventions (FROZEN_MATH_SPEC.md §3.1):
    h_card(x)      = sum_i x_i - K          feasible iff == 0   (equality)
    h_sector,j(x)  = C - n_j(x)             feasible iff >= 0   (inequality)
    h_budget(x)    = B - p^T x              feasible iff >= 0   (inequality)
so the native violation magnitudes are |h_card|, max(0, n_j - C), max(0, p^T x - B).

Inputs are read from the canonical artifact, keyed by ticker — never positionally.
The pre-canonical expectation (1,1,5) is NOT assumed; it is tested and reported either way.
This script computes v_ref only. It computes no Lambda_ref, f*, box, or any G3+ object.
"""
import hashlib, json, os, sys
from itertools import combinations
from math import gcd
from functools import reduce

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(ROOT, "research", "canonical", "stage1_instance.json")

failures = []


def check(label, got, expected):
    ok = got == expected
    if not ok:
        failures.append(f"{label}: got {got!r}, expected {expected!r}")
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}: {got}")
    return ok


def main():
    a = json.load(open(ART))

    # Integrity gate FIRST: a standalone D005 PASS must not be producible from a
    # tampered or internally inconsistent artifact.
    print("\n[0] Artifact integrity gate")
    body = {k: v for k, v in a.items() if k != "content_sha256"}
    recomputed = hashlib.sha256(
        json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if recomputed != a.get("content_sha256"):
        print(f"  [FAIL] content_sha256: recomputed {recomputed} != recorded "
              f"{a.get('content_sha256')}")
        print("  refusing to evaluate D005 on an artifact that does not hash to its own digest")
        sys.exit(1)
    print(f"  [OK ] content_sha256 recomputes ({recomputed})")

    order = a["universe"]["canonical_order"]
    p = [a["p_by_ticker"][t] for t in order]          # ticker-keyed, then ordered
    sec = a["universe"]["sector_of_ticker"]
    K, C, B = a["K"], a["C"], a["B"]
    n = len(order)

    print(f"\nInstance: n={n}, K={K}, C={C}, B={B}")
    print(f"  artifact content_sha256 = {a['content_sha256']}")

    # ---------------- cardinality ----------------
    # h_card = sum(x) - K over sum(x) in {0..20}; violation = |h_card|.
    print("\n[1] v_card — smallest attainable positive |sum(x) - K| over x in {0,1}^20")
    card_viols = sorted({abs(s - K) for s in range(n + 1)} - {0})
    v_card = card_viols[0]
    wit_card = sorted(range(n))[:K + v_card]          # any set of size K + v_card
    check("v_card", v_card, 1)
    print(f"       witness: |x| = {len(wit_card)} gives |h_card| = {abs(len(wit_card) - K)}")

    # ---------------- sector ----------------
    # h_sector,j = C - n_j; violation = n_j - C. Sector sizes are 5, so n_j reaches C+1.
    print("\n[2] v_sector — smallest attainable positive (n_j - C) over x in {0,1}^20")
    sizes = {}
    for t in order:
        sizes[sec[t]] = sizes.get(sec[t], 0) + 1
    print(f"       sector sizes: {sizes}")
    reachable = sorted({nj - C for lab, sz in sizes.items() for nj in range(sz + 1) if nj - C > 0})
    v_sector = reachable[0]
    check("v_sector", v_sector, 1)
    lab0 = sorted(sizes)[0]
    wit_sec = [t for t in order if sec[t] == lab0][:C + v_sector]
    print(f"       witness: select {wit_sec} -> n_j = {C + v_sector}, violation {v_sector}")

    # ---------------- budget ----------------
    # v_budget = min over x in {0,1}^20 of (p^T x - B), restricted to strictly positive.
    # Exact: reachable-sum DP over all 2^20 subsets (no cardinality restriction, per D005).
    print("\n[3] v_budget — smallest attainable positive (p^T x - B) over x in {0,1}^20")
    total = sum(p)
    reach = 1  # bitset: bit k set <=> sum k is reachable
    for pi in p:
        reach |= reach << pi
    over = [s for s in range(B + 1, total + 1) if (reach >> s) & 1]
    if not over:
        print("       STOP CONDITION: budget is unviolatable over the full cube")
        sys.exit(1)
    v_budget = over[0] - B
    print(f"       total cost of all 20 assets = {total}")
    print(f"       smallest reachable cost strictly above B: {over[0]}  ->  violation {v_budget}")

    # independent witness by direct search (does NOT reuse the DP)
    wit = None
    for k in range(1, n + 1):
        for comb in combinations(range(n), k):
            if sum(p[i] for i in comb) == over[0]:
                wit = comb
                break
        if wit:
            break
    if wit is None:
        failures.append("no explicit witness found for the DP-reported minimal cost")
    else:
        cost = sum(p[i] for i in wit)
        print(f"       witness x: {[order[i] for i in wit]}")
        print(f"       cost = {cost}, h_budget = B - cost = {B - cost}, violation = {cost - B}")
        check("witness cost matches DP", cost, over[0])

    # gcd is a LOWER BOUND only — reported to show the rule was not gcd-shortcut
    g = reduce(gcd, p)
    print(f"\n[4] gcd(prices) = {g}  (lower bound only; D005 is NOT gcd-defined)")
    check("B divisible by gcd", B % g == 0, True)
    check("v_budget is a multiple of gcd (necessary condition)", v_budget % g == 0, True)
    print(f"       gcd bound {g} vs attained {v_budget}: "
          f"{'coincide (instance fact)' if g == v_budget else 'DIVERGE'}")

    # ---------------- verdict ----------------
    v_ref = (v_card, v_sector, v_budget)
    print("\n" + "=" * 74)
    print(f"D005 v_ref = (v_card, v_sector, v_budget) = {v_ref}")
    print(f"Pre-canonical expectation (1, 1, 5): "
          f"{'CONFIRMED on canonical data' if v_ref == (1, 1, 5) else 'NOT CONFIRMED'}")
    if failures:
        print("RESULT: FAIL")
        for f in failures:
            print("  - " + f)
        print("=" * 74)
        sys.exit(1)
    print("RESULT: ALL CHECKS PASSED (D005 rule evaluated on canonical data;")
    print("        this is evidence, not a U-07 closure)")
    print("=" * 74)


if __name__ == "__main__":
    main()
