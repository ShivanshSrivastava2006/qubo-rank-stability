#!/usr/bin/env python3
"""
U-15 support computations: global v_ref = (1,1,1) vs per-constraint v_ref = (1,1,5).

Establishes the reachable supports, the normalized supports under each option, the
rescaling behaviour, and the consequences for U-18(a). Does NOT resolve U-18(a).

STATUS 2026-08-23: U-15 was APPROVED as D005 (option B, per-constraint, v = (1,1,5) --
rule-defined as the smallest ATTAINABLE positive native violation, NOT gcd-defined; the
numeric value is pending canonical-data verification at U-07/G2).  U-18(a)+(b) were
approved as D006.  This script is retained as the comparative support analysis for both
options; the approved mapping is verified by verify_d006.py.

Standard library only.  Run: python3 research/audit/verify_u15.py
"""
import math

PRICES = [210, 420, 1200, 180, 220, 250, 320, 520, 610, 45,
          780, 155, 110, 30, 205, 115, 145, 200, 390, 470]
K, C, B = 6, 2, 1100
FAIL = []


def chk(l, g, w, tol=1e-12):
    ok = abs(g - w) <= tol * max(1.0, abs(w)) if isinstance(w, float) else g == w
    if not ok:
        FAIL.append(f"{l}: {g!r} vs {w!r}")
    print(f"  [{'OK ' if ok else 'FAIL'}] {l}")


def hdr(t):
    print("\n" + "=" * 78); print(t); print("=" * 78)


def budget_violations(prices, budget):
    tot = sum(prices)
    reach = [False] * (tot + 1); reach[0] = True
    for p in prices:
        for v in range(tot, p - 1, -1):
            if reach[v - p]:
                reach[v] = True
    return sorted({v - budget for v, ok in enumerate(reach) if ok and v > budget})


# ------------------------------------------------------------------ 1
hdr("1. Native residuals, units, and reachable supports (PRIMARY domain = all x)")
g = 0
for p in PRICES:
    g = math.gcd(g, p)
viol_bud = budget_violations(PRICES, B)
print(f"""
  h_card(x)     = sum(x) - K        [count]   EQUALITY: both signs are violations
  h_sector,j(x) = C - n_j(x)        [count]   inequality, h >= 0 feasible
  h_budget(x)   = B - p'x           [currency] inequality, h >= 0 feasible
""")
chk("gcd(prices)", g, 5)
chk("B divisible by gcd", B % g, 0)
chk("smallest reachable |h_card| violation", 1, 1)
chk("smallest reachable |h_sector| violation", 1, 1)
chk("smallest reachable |h_budget| violation (exact, DP-derived)", min(viol_bud), 5)
chk("INSTANCE FACT: gcd == exact smallest reachable violation (Stage 1 only)", g, min(viol_bud))
print("      NOTE (review finding 5): gcd is a LOWER BOUND, not a definition. Equality is an")
print("      INSTANCE FACT here, not a general rule. Counterexamples:")
for pr, bb in ([10, 10, 10], 15), ([6, 10, 15], 7):
    gg = 0
    for q in pr:
        gg = math.gcd(gg, q)
    mv = min(budget_violations(pr, bb))
    print(f"        prices={pr} B={bb}: gcd={gg}, exact smallest violation={mv} -> equal? {gg == mv}")
    chk(f"        gcd != exact minimum for prices={pr}, B={bb}", gg == mv, False)
print("      => v_budget MUST be defined as the EXACT DP-derived attainable minimum,")
print("         not as gcd(prices). For Stage 1 they coincide at 5.")
print(f"      budget: {len(viol_bud)} distinct violations, min {min(viol_bud)}, max {max(viol_bud)}")
print(f"              a PROPER SUBSET of the multiples of {g} (not contiguous)")

# ------------------------------------------------------------------ 2
hdr("2. Normalized supports w_j = |h_j| / v_ref,j, and smallest reachable w")
OPTS = {"A global (1,1,1)": (1, 1, 1), "B per-constraint (1,1,5)": (1, 1, 5)}
for name, (vc, vs, vb) in OPTS.items():
    wmin = (1 / vc, 1 / vs, min(viol_bud) / vb)
    print(f"\n  {name}")
    print(f"      cardinality  w = |h|/{vc}  -> smallest reachable w = {wmin[0]:g}")
    print(f"      sector       w = |h|/{vs}  -> smallest reachable w = {wmin[1]:g}   support {{1,2,3}}")
    print(f"      budget       w = |h|/{vb}  -> smallest reachable w = {wmin[2]:g}")
    aligned = len(set(wmin)) == 1
    print(f"      smallest reachable w EQUAL across families? {aligned}")
    if "A global" in name:
        chk("    A: families have DIFFERENT smallest reachable w", aligned, False)
        chk("    A: w = 1 is UNREACHABLE for budget", min(viol_bud) / vb == 1.0, False)
    else:
        chk("    B: families share smallest reachable w = 1", aligned, True)
        chk("    B: w = 1 IS reachable for budget", min(viol_bud) / vb == 1.0, True)

# ------------------------------------------------------------------ 3
hdr("3. B is A in lot-units: rescaling the budget's NATIVE UNIT")
print("""
  Define lot-units: p' = p/gcd, B' = B/gcd. Then h'_budget = B' - p''x = h_budget/gcd,
  and option A applied in lot-units (v' = 1 lot) gives w = h_budget/gcd -- exactly option B.
  So A and B are NOT two normalization philosophies. Both are "one unit of native
  violation"; they DISAGREE ABOUT WHAT THE NATIVE UNIT IS (a dollar, or the actual
  quantum of expenditure).
""")
p_lot = [p // g for p in PRICES]
viol_lot = budget_violations(p_lot, B // g)
chk("lot-unit violations == dollar violations / gcd", viol_lot, [v // g for v in viol_bud])
chk("smallest lot-unit violation == 1", min(viol_lot), 1)

# ------------------------------------------------------------------ 4
hdr("4. Rescaling behaviour")
print("""
  (i) OBJECTIVE rescaling f -> c*f.  v_ref carries RESIDUAL units, not energy, so it is
      UNCHANGED. Lambda_ref -> c*Lambda_ref, hence lambda_S = s*Lambda_ref/v^2 -> c*lambda_S,
      lambda_1 = Lambda_ref*a/v -> c*lambda_1, lambda_2 -> c*lambda_2.
      => BOTH options preserve objective-rescaling invariance. U-15 is ORTHOGONAL to it.

  (ii) RESIDUAL-UNIT rescaling (e.g. dollars -> cents), p -> beta*p, B -> beta*B:
""")
beta = 100
viol_cents = budget_violations([p * beta for p in PRICES], B * beta)
chk("cents violations == beta * dollar violations", viol_cents, [v * beta for v in viol_bud])
w_A_literal = min(viol_cents) / 1          # v_ref taken as the NUMBER 1
w_A_dimensional = min(viol_cents) / beta   # v_ref taken as ONE DOLLAR = beta cents
w_B = min(viol_cents) / (g * beta)         # v_ref = smallest reachable violation
print(f"      A as the literal NUMBER 1 : w_min {min(viol_bud)} -> {w_A_literal:g}   NOT invariant")
print(f"      A as ONE DOLLAR (dimensional): w_min {min(viol_bud)} -> {w_A_dimensional:g}   invariant")
print(f"      B as smallest reachable  : w_min 1 -> {w_B:g}   invariant")
chk("    A-as-literal-1 is NOT residual-unit invariant", w_A_literal == min(viol_bud), False)
chk("    A-as-one-dollar IS residual-unit invariant", w_A_dimensional, float(min(viol_bud)))
chk("    B IS residual-unit invariant", w_B, 1.0)
print("""
      RECAST (review finding 2). v_budget = "1 currency unit" is DIMENSIONED: under
      dollars->cents it is 100 cents, so Option A stated as ONE DOLLAR is ALREADY invariant.
      Reading the printed numeral 1 as a dimensionless literal manufactures a failure that
      the Scope Lock does not actually commit to. This is NOT a residual-rescaling defect and
      NOT the same class as C0-01 -- that earlier framing is WITHDRAWN.

      The REAL Scope Lock error is narrower and stands on its own: SS14 justifies v_ref as
      "the smallest nonzero integer violation", and that justification is FACTUALLY FALSE for
      budget under A -- the smallest reachable violation is 5, not 1. It is a REACHABILITY
      and INTERPRETATION conflict, not a units failure.
""")

# ------------------------------------------------------------------ 5
hdr("5. Consequences for U-18(a) - reported, NOT resolved")
print("""
  SCOPE (review finding 1): U-18(a)'s r applies ONLY to the Taylor-family INEQUALITY
  constraints -- SECTOR and BUDGET. Cardinality uses the shared equality term
  alpha(s_card)*h_card^2 in BOTH encodings and has NO r at all. The comparison below is
  therefore sector-vs-budget only; any earlier r_card column was an error.

  Target-point matching uses r = 1/w0. To target each family's SMALLEST REACHABLE violation:
""")
for name, (vc, vs, vb) in OPTS.items():
    r_sec = 1 / (1 / vs)
    r_bud = 1 / (min(viol_bud) / vb)
    print(f"  {name}   (INEQUALITY families only)")
    print(f"      r_sector = {r_sec:g}   r_budget = {r_bud:g}")
    common_ok = abs(r_sec - r_bud) < 1e-12
    print(f"      a COMMON r can target BOTH inequality families' smallest reachable violation? {common_ok}")
    if "A global" in name:
        chk("    A: common r CANNOT do so (budget needs r = 1/5)", common_ok, False)
    else:
        chk("    B: common r = 1 CAN do so", common_ok, True)

print("""
  Penalty-strength consequence at MATCHED s (this is where U-15 has real content):
      lambda_S,bud   = s*Lambda_ref / v_bud^2      -> differs by v_bud^2 = 25x between options
      lambda_1,bud   = Lambda_ref*a / v_bud        -> differs by v_bud     = 5x between options
      ratio lambda_1/lambda_S                      -> differs by v_bud     = 5x
  SCOPE (review finding 3): these ratios are arithmetically correct AT FIXED NUMERICAL s AND a.
  Whether an ALLOWED one-coordinate rule a = g(s) preserves the relation is precisely U-18(a),
  which is UNRESOLVED. So no categorical claim is made that the difference is unabsorbable
  across encodings. What IS established: at fixed coordinates the budget family's
  slack-vs-unbalanced calibration differs by v_bud between the options.
""")
Lam, s_v, a_v = 1.0, 1.0, 0.732050807568877
for lbl, vb in (("A (v_bud=1)", 1.0), ("B (v_bud=5)", 5.0)):
    lS = s_v * Lam / vb**2
    l1 = Lam * a_v / vb
    print(f"      {lbl}: lambda_S = {lS:.6f}  lambda_1 = {l1:.6f}  ratio l1/lS = {l1/lS:.6f}")
chk("    ratio lambda_1/lambda_S differs by exactly v_bud between options",
    (Lam*a_v/5.0)/(s_v*Lam/25.0) / ((Lam*a_v/1.0)/(s_v*Lam/1.0)), 5.0)

print("\n" + "=" * 78)
if FAIL:
    print(f"RESULT: {len(FAIL)} CHECK(S) FAILED")
    for f in FAIL:
        print("  - " + f)
    raise SystemExit(1)
print("RESULT: ALL CHECKS PASSED")
print("=" * 78)
