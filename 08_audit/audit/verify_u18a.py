#!/usr/bin/env python3
"""
U-18(a) derivation support: candidate one-coordinate reductions a_j = g(s_j),
evaluated on the ACTUAL Stage-1 residual supports.

Conditional on c_j = 1 (Lambda_pen,j = Lambda_ref) -- a recommendation when this was written,
APPROVED 2026-08-23 as D006(b).  Both U-15 options for v_budget are analysed here; U-15 was
APPROVED 2026-08-23 as D005 (option (b), v_budget = 5), so the (b) branch is the operative one.
This script remains the DERIVATION support: it establishes that no candidate rule is neutral.
The approved mapping itself is verified by verify_d006.py.

All penalties in units of Lambda_ref, so nothing depends on U-02/U-03.
Standard library only.  Run: python3 research/audit/verify_u18a.py
"""
import math
from itertools import combinations

PRICES = [210, 420, 1200, 180, 220, 250, 320, 520, 610, 45,
          780, 155, 110, 30, 205, 115, 145, 200, 390, 470]
K, C, B = 6, 2, 1100
FAIL = []


def chk(label, got, want, tol=1e-9):
    ok = abs(got - want) <= tol * max(1.0, abs(want)) if isinstance(want, float) else got == want
    if not ok:
        FAIL.append(f"{label}: {got!r} vs {want!r}")
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}")


def hdr(t):
    print("\n" + "=" * 76); print(t); print("=" * 76)


# ---------------------------------------------------------------- 1. supports
hdr("1. Reachable residual supports - ENUMERATED, not inferred from bounds")

# --- sector: h = C - n_j, n_j in 0..5
sec_support = sorted({C - n for n in range(6)})
chk("sector support enumerated == [-3..2]", sec_support, [-3, -2, -1, 0, 1, 2])
sec_infeas = sorted(-h for h in sec_support if h < 0)
print(f"      sector infeasible |h| = {sec_infeas}   (v_sector = 1 under BOTH U-15 options)")

# --- cardinality: h = sum(x) - K
card_support = sorted({n - K for n in range(21)})
chk("cardinality support == [-6..14]", (card_support[0], card_support[-1]), (-6, 14))

# --- budget: enumerate reachable subset sums exactly
tot = sum(PRICES)
reach_all = [False] * (tot + 1)
reach_all[0] = True
for p in PRICES:
    for v in range(tot, p - 1, -1):
        if reach_all[v - p]:
            reach_all[v] = True
sums_all = [v for v, ok in enumerate(reach_all) if ok]

dp = [[False] * (tot + 1) for _ in range(K + 1)]
dp[0][0] = True
for p in PRICES:
    for k in range(K - 1, -1, -1):
        for v in range(tot - p, -1, -1):
            if dp[k][v]:
                dp[k + 1][v + p] = True
sums_K = [v for v, ok in enumerate(dp[K]) if ok]

chk("subset-sum DP over |x|=K matches direct enumeration count",
    len(sums_K), len({sum(PRICES[i] for i in c) for c in combinations(range(20), K)}))
chk("total price sum (enumerated, not assumed)", tot, 6575)

viol_all = sorted({v - B for v in sums_all if v > B})
viol_K = sorted({v - B for v in sums_K if v > B})
g = 0
for p in PRICES:
    g = math.gcd(g, p)
chk("gcd(prices)", g, 5)
chk("every reachable budget violation divisible by gcd (all x)", all(v % g == 0 for v in viol_all), True)
chk("smallest reachable budget violation (all x) [PRIMARY]", min(viol_all), 5)
chk("smallest reachable budget violation (|x|=K) [diagnostic]", min(viol_K), 5)
# PRIMARY support is ALL x: the QUBO domain is {0,1}^20 because cardinality is SOFT (D002
# sweeps s_card weak-to-strong, so off-cardinality states can attain the ground state).
# The |x|=K slice is a CONDITIONAL DIAGNOSTIC only. (review finding 1.)
def lattice_report(name, viol, step):
    lo, hi = min(viol), max(viol)
    full = (hi - lo) // step + 1
    missing = full - len(viol)
    print(f"      {name:<34} {len(viol):>5} distinct, min {lo}, max {hi}")
    print(f"        {'':<32} a PROPER SUBSET of {{{lo},{lo+step},...,{hi}}}: "
          f"{full} multiples in range, {missing} NOT reachable")
    return missing

print("\n      PRIMARY support = all x in {0,1}^20 (QUBO domain; cardinality is soft):")
miss_all = lattice_report("budget violations, ALL x", viol_all, g)
print("      SECONDARY (conditional diagnostic) = the |x|=K slice:")
miss_K = lattice_report("budget violations, |x|=K", viol_K, g)
chk("all-x budget support is NOT a contiguous 5Z lattice", miss_all > 0, True)
chk("|x|=K budget support is NOT a contiguous 5Z lattice", miss_K > 0, True)
print(f"      smallest reachable violation is {min(viol_all)} in BOTH supports, so the U-15")
print(f"      conclusion below does not depend on which support is used.")

# normalized supports under both U-15 options, on the PRIMARY (all-x) support
w_bud_v1 = [v / 1.0 for v in viol_all]    # U-15(a) global v_budget = 1
w_bud_v5 = [v / 5.0 for v in viol_all]    # U-15(b) per-constraint v_budget = 5
print(f"\n      U-15(a) v_budget=1 -> reachable w: subset of {{5,...,{max(viol_all)}}}, "
      f"min w = {min(w_bud_v1):.0f}  <-- w = 1 is UNREACHABLE")
print(f"      U-15(b) v_budget=5 -> reachable w: subset of {{1,...,{max(viol_all)//5}}}, "
      f"min w = {min(w_bud_v5):.0f}")
chk("under U-15(a), w = 1 is NOT reachable for budget", 1.0 in w_bud_v1, False)
chk("under U-15(b), w = 1 IS reachable for budget", 1.0 in w_bud_v5, True)


# ---------------------------------------------------------------- 2. unification
hdr("2. TARGET-POINT and FIXED-WEIGHTED-MEAN matching share one family: a(s;r)=-r+sqrt(r^2+2s)")
print("""
  Derivation. With c = 1, on the infeasible side (h = -w*v, w > 0):
      D(w) = a*w + (a^2/2 - s)*w^2
  Requiring D(w0) = 0 at a target w0 > 0:
      a + (a^2/2 - s)*w0 = 0  =>  a^2 + (2/w0)*a - 2s = 0
      a = -1/w0 + sqrt(1/w0^2 + 2s)
  Requiring instead a weighted mean E_pi[D(w)] = 0 over a declared distribution pi:
      a*E[w] + (a^2/2 - s)*E[w^2] = 0  =>  a^2 + 2r*a - 2s = 0,  r = E[w]/E[w^2]
      a = -r + sqrt(r^2 + 2s)
  These coincide with r = 1/w0. A point mass at w0 has r = w0/w0^2 = 1/w0, so the two
  readings are self-consistent: r is EITHER 1/(target violation) OR E[w]/E[w^2].

  SCOPE LIMIT (review finding 3). This family with FIXED POSITIVE r characterizes exactly two
  criteria: target-point matching and fixed-weighted-mean matching. It does NOT exhaust the
  one-coordinate reductions -- infinitely many rules a = g(s) lie outside it. Any positive
  g(s) CAN be written with r(s) = [s - g(s)^2/2] / g(s), but that r(s) is a physical
  target/weight statistic ONLY where it is positive and declared. So the representation is
  algebra, not a restriction, once r is allowed to vary with s.
""")


def a_of(s, r):
    return -r + math.sqrt(r * r + 2 * s)


def D(a, s, w):
    return a * w + (a * a / 2 - s) * w * w


for s_v in (0.3, 1.0, 4.0):
    for w0 in (1.0, 2.0, 5.0):
        a = a_of(s_v, 1.0 / w0)
        chk(f"    target-match at w0={w0} (s={s_v}) gives D(w0)=0", D(a, s_v, w0), 0.0)
    a2 = a_of(s_v, 1.0)
    chk(f"    r=1 reproduces R2 exactly (s={s_v})", a2, -1 + math.sqrt(1 + 2 * s_v))
    ws = [1.0, 2.0, 3.0]
    r = (sum(ws) / len(ws)) / (sum(w * w for w in ws) / len(ws))
    a4 = a_of(s_v, r)
    wm = sum(D(a4, s_v, w) for w in ws) / len(ws)
    chk(f"    R4 weighted mean D == 0 on w in {{1,2,3}} (s={s_v})", wm, 0.0)

print("\n  R1 (a = s) is an ALGEBRAIC drifting-r REPRESENTATION (not a fixed-r family member):")
for s_v in (0.3, 1.0, 1.9):
    r1 = 1 - s_v / 2
    chk(f"    a(s; r = 1 - s/2) == s   (s={s_v})", a_of(s_v, r1), s_v)
    print(f"        => R1's implied match point w0 = 1/r = {1/r1:.4f}  (drifts with s)")
print("      For s >= 2, r = 1 - s/2 <= 0: r leaves the positive range, so R1 has no physical")
print("      matching interpretation there at all -- it is outside the fixed-r matching family.")


# ---------------------------------------------------------------- 3. gaps on real supports
hdr("3. D(w) on the ACTUAL supports  (c = 1; units of Lambda_ref)")
CANDS = [("R1  a=s", lambda s: s),
         ("R2  r=1", lambda s: a_of(s, 1.0)),
         ("R4  r=E[w]/E[w^2] on sector {1,2,3}", lambda s: a_of(s, (2.0) / (14.0 / 3)))]

print("\n  --- SECTOR, v=1, reachable infeasible w in {1,2,3} ---")
for s_v in (0.5, 2.0):
    print(f"    s = {s_v}")
    print(f"      {'candidate':<36} " + "".join(f"{'w='+str(w):>12}" for w in (1, 2, 3)))
    for nm, g_ in CANDS:
        a = g_(s_v)
        print(f"      {nm:<36} " + "".join(f"{D(a,s_v,float(w)):>12.4f}" for w in (1, 2, 3)))

print("\n  --- BUDGET, both U-15 options, first reachable violations ---")
for lbl, ws in [("U-15(a) v=1  (w = 5,10,15,...)", w_bud_v1[:3]),
                ("U-15(b) v=5  (w = 1, 2, 3,...)", w_bud_v5[:3])]:
    print(f"\n    {lbl}")
    s_v = 1.0
    print(f"      {'candidate':<36} " + "".join(f"{'w='+format(w,'.0f'):>12}" for w in ws))
    for nm, g_ in CANDS:
        a = g_(s_v)
        print(f"      {nm:<36} " + "".join(f"{D(a,s_v,w):>12.4f}" for w in ws))
print("""
      NOTE: under U-15(a) the budget's smallest REACHABLE w is 5, so any rule matching at
      w0 = 1 (R2) targets a violation that CANNOT OCCUR for budget; D < 0 at every reachable
      budget violation and grows in magnitude.
      SCOPE (review finding 4): this makes U-15 blocking for a SUPPORT-CALIBRATED r, or for one
      shared rule across constraint families. It is NOT a proof that every U-18(a) choice is
      impossible -- a human could predeclare SEPARATE mappings conditional on each U-15 branch.
      The no-recommendation conclusion stands because no such external basis is specified.
""")


# ---------------------------------------------------------------- 4. feasible side
hdr("4. Feasible-side behaviour  (h = +u*v, u > 0; slack is identically 0 there)")
print("""
  zeta(+u*v)/Lambda_ref = -a*u + a^2*u^2/2 = a*u*(a*u/2 - 1)
    < 0 (REWARD)  for u < 2/a        vertex (deepest reward) at u = 1/a, depth -1/2
    > 0 (PENALTY) for u > 2/a
  Slack is exactly 0 for every feasible state, so ANY nonzero value here is a departure
  from slack's flatness -- the structural encoding difference, not a bias per se.
""")
for s_v in (0.5, 2.0):
    for nm, g_ in CANDS:
        a = g_(s_v)
        vals = [(u, a * u * (a * u / 2 - 1)) for u in (1.0, 2.0)]
        print(f"    s={s_v:<4} {nm:<36} a={a:7.4f}  sign-flip at u=2/a={2/a:8.4f}  "
              + "  ".join(f"zeta(u={u:.0f})={v:+.4f}" for u, v in vals))
print("""
    Sector feasible residuals are u in {0,1,2} (h = 0,1,2; h=2 means an EMPTY sector).
    The sign threshold is u = 2/a(s;r). Where 2/a > 2 the encoding REWARDS an empty sector;
    where 2/a < 2 it PENALIZES it. The examples printed above are AT THE TWO s VALUES SHOWN.
    SCOPE (review finding 6): whether any candidate actually changes sign WITHIN the sweep
    depends on the s-domain bounds and on r. U-04's RULE is CLOSED (D010, 2026-08-24) but its
    NUMBERS are a G3 ADNYE record, so the eventual range is still not known here. No claim is
    made that every candidate flips sign inside it.
    Either way a nonzero value here reorders FEASIBLE portfolios relative to f alone, which is
    the primary (exact-recovery) exposure. Whether any reordering changes a ground state is
    EXPERIMENTAL.
""")

print("=" * 76)
if FAIL:
    print(f"RESULT: {len(FAIL)} CHECK(S) FAILED")
    for f in FAIL:
        print("  - " + f)
    raise SystemExit(1)
print("RESULT: ALL CHECKS PASSED")
print("=" * 76)
