#!/usr/bin/env python3
"""
Gate-0 fact verification.

Reproduces every numeric claim made in the Gate-0 deliverables directly from
primary project material. No dependency beyond the standard library so it can be
re-run by an independent auditor without environment setup.

Primary sources:
  - previous_work/QDTRINITY_sTAGE_2/datasets/mu.csv
  - previous_work/QDTRINITY_sTAGE_2/datasets/Sigma.csv
  - previous_work/QDTRINITY_sTAGE_2/Jupyter_Notebook_For_Submission.ipynb
      cell 12 (stocks, sector_map), cell 14 (K, alpha), cell 16 (C),
      cell 17 (prices, budget)

Run:  python3 research/audit/verify_gate0_facts.py
"""
import csv
import json
import math
import os
import sys
from itertools import combinations

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROTO = os.path.join(ROOT, "previous_work", "QDTRINITY_sTAGE_2")
NB = os.path.join(PROTO, "Jupyter_Notebook_For_Submission.ipynb")

# ---- values transcribed from the prototype notebook (cells 12/14/16/17) ----
STOCKS = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
          "JPM", "V", "MA", "GS", "BAC",
          "LLY", "JNJ", "MRK", "PFE", "ABBV",
          "XOM", "CVX", "GE", "CAT", "HON"]
SECTOR_MAP = {"Technology": list(range(0, 5)),
              "Finance": list(range(5, 10)),
              "Healthcare": list(range(10, 15)),
              "Industrial_Energy": list(range(15, 20))}
PRICES = [210, 420, 1200, 180, 220, 250, 320, 520, 610, 45,
          780, 155, 110, 30, 205, 115, 145, 200, 390, 470]
K, C, B, ALPHA = 6, 2, 1100, 20

failures = []


def check(label, got, expected):
    ok = got == expected
    if not ok:
        failures.append(f"{label}: got {got!r}, expected {expected!r}")
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}: {got}")
    return ok


def transcription_guard():
    """Fail loudly if the notebook's literals ever drift from what is hard-coded above."""
    print("\n[0] Transcription guard - notebook literals still match this script")
    nb = json.load(open(NB))
    src = {i: "".join(c["source"]) for i, c in enumerate(nb["cells"])}
    joined = "\n".join(src.values())
    for token in ["prices = np.array([", "budget = 1100", "sector_cap = 2", "K = 6", "alpha = 20"]:
        check(f"notebook contains {token!r}", token in joined, True)
    # price literals appear in cell 17 in order
    c17 = src.get(17, "")
    nums = [int(t) for t in c17.replace(",", " ").replace("[", " ").replace("]", " ").split()
            if t.isdigit()]
    check("price vector transcribed correctly", nums[:20], PRICES)


def data_order():
    print("\n[1] Data ordering: mu/Sigma index vs prototype's positional universe")
    mu_rows = list(csv.reader(open(os.path.join(PROTO, "datasets", "mu.csv"))))
    mu_idx = [r[0] for r in mu_rows[1:]]
    s_rows = list(csv.reader(open(os.path.join(PROTO, "datasets", "Sigma.csv"))))
    s_idx, s_cols = [r[0] for r in s_rows[1:]], s_rows[0][1:]

    check("mu.csv has 20 assets", len(mu_idx), 20)
    check("Sigma is 20x20", (len(s_idx), len(s_cols)), (20, 20))
    check("Sigma index == Sigma columns", s_idx == s_cols, True)
    check("Sigma index == mu index", s_idx == mu_idx, True)
    check("mu.csv is alphabetically sorted", mu_idx == sorted(mu_idx), True)
    check("prototype STOCKS list is NOT alphabetical", STOCKS == sorted(STOCKS), False)
    check("mu.csv order == prototype STOCKS order", mu_idx == STOCKS, False)

    mismatched = [i for i in range(20) if mu_idx[i] != STOCKS[i]]
    check("positions where mu.csv ticker != STOCKS ticker", len(mismatched), 18)
    print(f"         mu.csv  : {mu_idx}")
    print(f"         STOCKS  : {STOCKS}")
    return mu_idx


def constraint_geometry():
    print("\n[2] Constraint geometry (depends only on prices/sectors/K/C/B)")
    sector_of = [0] * 5 + [1] * 5 + [2] * 5 + [3] * 5
    n_card = 0
    costs = []
    sec_ok_costs = []
    n_feasible = 0
    for comb in combinations(range(20), K):
        n_card += 1
        cost = sum(PRICES[i] for i in comb)
        costs.append(cost)
        cnt = [0, 0, 0, 0]
        for i in comb:
            cnt[sector_of[i]] += 1
        if all(v <= C for v in cnt):
            sec_ok_costs.append(cost)
            if cost <= B:
                n_feasible += 1

    check("cardinality-feasible count == C(20,6)", n_card, 38760)
    check("min cost over cardinality-feasible", min(costs), 600)
    check("max cost over cardinality-feasible", max(costs), 4000)
    check("cardinality+sector feasible count", len(sec_ok_costs), 19000)
    check("|F| (cardinality+sector+budget)", n_feasible, 976)
    check("F is non-empty and a strict subset", 0 < n_feasible < n_card, True)
    return n_feasible


def slack_sizing():
    print("\n[3] Slack auxiliary register sizing (the 39-vs-37 question)")
    # Sector: h_j(x) = C - n_j(x); over all x in {0,1}^20, max h_j = C = 2
    sec_bits = math.ceil(math.log2(C + 1))
    check("bits per sector register (max h_j = C = 2)", sec_bits, 2)
    check("total sector aux bits (4 sectors)", 4 * sec_bits, 8)

    # Budget: h(x) = B - p'x. Max over domain depends on which domain is used.
    hmax_all = B - 0                      # x = 0 is in {0,1}^20
    hmax_card = B - 600                   # min cost among |x| = K
    bits_all = math.ceil(math.log2(hmax_all + 1))
    bits_card = math.ceil(math.log2(hmax_card + 1))
    check("max h_budget over ALL x in {0,1}^20 (x=0)", hmax_all, 1100)
    check("bits if register must cover all x", bits_all, 11)
    check("max h_budget over |x| = K only", hmax_card, 500)
    check("bits if register covers only |x| = K", bits_card, 9)

    check("TOTAL aux bits / QUBO vars, domain = all x", (8 + bits_all, 20 + 8 + bits_all), (19, 39))
    check("TOTAL aux bits / QUBO vars, domain = |x|=K", (8 + bits_card, 20 + 8 + bits_card), (17, 37))
    print("         Scope Lock SS13 asserts 19 aux / 39 vars -> matches the 'all x' reading.")


def integrality():
    """CORRECTED after review finding C0-04.

    The earlier version of this section claimed integrality 'justifies v_ref = 1'.
    That was an OVERCLAIM and is withdrawn: integrality gives h in Z, but the
    ATTAINABLE residual lattice for the budget constraint is 5Z, so a budget
    violation of 1 is unreachable. Integrality justifies only the exactness of the
    clamp minimiser, not the choice of v_ref.
    """
    import math as _m
    print("\n[4] Residual integrality -> exactness of the clamp minimiser (NOT v_ref)")
    check("all prices integer", all(float(p).is_integer() for p in PRICES), True)
    check("budget integer", float(B).is_integer(), True)
    print("         => h_budget, h_sector, h_cardinality are all integer-valued,")
    print("            so S* = clamp(round(h),0,2^N-1) = clamp(h,0,2^N-1) exactly (no rounding ties).")

    print("\n[5] Attainable residual lattice per constraint (v_ref is a DECISION, not a fact)")
    g = 0
    for p_ in PRICES:
        g = _m.gcd(g, p_)
    check("gcd(prices)", g, 5)
    check("B divisible by gcd(prices)", B % g == 0, True)
    viol = set()
    for comb in combinations(range(20), K):
        h = B - sum(PRICES[i] for i in comb)
        if h < 0:
            viol.add(-h)
    check("smallest ATTAINABLE budget violation", min(viol), 5)
    check("every attainable budget violation divisible by gcd", all(v % g == 0 for v in viol), True)
    print("         => budget residuals lie in 5Z; a unit budget violation is UNREACHABLE.")
    print("         => sector and cardinality residuals step by 1, so v_ref = 1 IS attainable there.")
    print("         => a single common v_ref = 1 is therefore a MODELLING CHOICE (see U-15),")
    print("            not a consequence of integrality. The prior claim is withdrawn.")


def main():
    print("=" * 72)
    print("GATE-0 FACT VERIFICATION")
    print("=" * 72)
    transcription_guard()
    data_order()
    constraint_geometry()
    slack_sizing()
    integrality()
    print("\n" + "=" * 72)
    if failures:
        print(f"RESULT: {len(failures)} CHECK(S) FAILED")
        for f in failures:
            print("  - " + f)
        return 1
    print("RESULT: ALL CHECKS PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
