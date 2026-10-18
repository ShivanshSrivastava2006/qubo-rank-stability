#!/usr/bin/env python3
"""
U-16 supporting computation: candidate unbalanced parameterizations on the ACTUAL
Stage-1 constraint residual supports.

All penalties are reported in UNITS OF Lambda_ref, so nothing here depends on the
unresolved kappa_risk (U-02) or on the choice of range-vs-std (U-03): every candidate
and slack are all linear in Lambda_ref, so the ratio is Lambda_ref-free.

v_ref remains UNRESOLVED (U-15); both candidate settings are carried symbolically.

Standard library only.  Run: python3 research/audit/verify_u16.py
"""
import math
from itertools import combinations

PRICES = [210, 420, 1200, 180, 220, 250, 320, 520, 610, 45,
          780, 155, 110, 30, 205, 115, 145, 200, 390, 470]
K, C, B = 6, 2, 1100
FAIL = []


def chk(label, got, want, tol=1e-12):
    ok = abs(got - want) <= tol * max(1.0, abs(want)) if isinstance(want, float) else got == want
    if not ok:
        FAIL.append(f"{label}: got {got!r} want {want!r}")
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}: {got}")


def hdr(t):
    print("\n" + "=" * 74); print(t); print("=" * 74)


# ---------------------------------------------------------------- 1. supports
hdr("1. Reachable residual supports on the Stage-1 instance")

h_card = sorted({n - K for n in range(0, 21)})
h_sec = sorted({C - n for n in range(0, 6)})
allp = set()
for r in range(21):
    pass
# budget: exact reachable set over all x is large; report bounds + the |x|=K slice
tot = sum(PRICES)
bud_all_min, bud_all_max = B - tot, B - 0
card_costs = [sum(PRICES[i] for i in comb) for comb in combinations(range(20), K)]
bud_K_min, bud_K_max = B - max(card_costs), B - min(card_costs)

print(f"  cardinality  h = sum(x) - K      support {h_card[0]} .. {h_card[-1]}  (step 1)")
print(f"  sector       h = C - n_j         support {h_sec[0]} .. {h_sec[-1]}  (step 1)")
print(f"  budget       h = B - p'x         over all x: {bud_all_min} .. {bud_all_max}")
print(f"                                    over |x|=K: {bud_K_min} .. {bud_K_max}  (step 5, gcd=5)")
chk("sector support == [-3..2]", h_sec, [-3, -2, -1, 0, 1, 2])
chk("cardinality support == [-6..14]", (h_card[0], h_card[-1]), (-6, 14))

# ---------------------------------------------------------------- 2. family algebra
hdr("2. Option 1 derived coefficients, and the frozen formula as its Lambda_pen = 1 case")
print("""
  Motivating object (Montanez-Barrera eq.24): a multiplicative feasibility factor
  exp(-eta*h) with [eta] = 1/R, so that eta*h is DIMENSIONLESS.
      exp(-eta h) ~= 1 - eta h + (eta h)^2 / 2
  Drop the constant 1 (an energy offset; does not move an argmin). The SHAPE
      phi(h) = -eta h + (eta h)^2 / 2                is dimensionless.
  An energy contribution therefore requires an outer energy scale Lambda_pen:
      zeta(h) = Lambda_pen * [ -eta h + (eta h)^2 / 2 ],   eta = a / v_ref, a dimensionless
  Expanding:
      lambda_1 = Lambda_pen * a   / v_ref          [E/R]
      lambda_2 = Lambda_pen * a^2 / (2 v_ref^2)    [E/R^2]
  Eliminating a:
      lambda_2 = lambda_1^2 / (2 * Lambda_pen)
  The FROZEN SS14 relation lambda_2 = lambda_1^2 / 2 requires an OMITTED energy reference:
      lambda_2 = lambda_1^2 / (2 * E0).
  PRECISION (review): E0 must CARRY ENERGY UNITS. The frozen formula declares neither E0 nor
  its rescaling rule. Earlier shorthand described a bare numeric
  scale; the defect is that an ENERGY-VALUED reference was omitted from the record and therefore
  NEVER RESCALED. That omission is exactly why
  [lambda_2 h^2] = E^2 and why the mapping fails objective rescaling.
""")


def coeffs_opt1(Lam_pen, a, v):
    return Lam_pen * a / v, Lam_pen * a * a / (2 * v * v)


L, a_, v_ = 3.7, 1.3, 5.0
l1, l2 = coeffs_opt1(L, a_, v_)
chk("lambda_2 == lambda_1^2/(2*Lambda_pen)", l2, l1 * l1 / (2 * L))
chk("frozen lambda_2 = lambda_1^2/2 <=> Lambda_pen = 1", coeffs_opt1(1.0, a_, v_)[1],
    coeffs_opt1(1.0, a_, v_)[0] ** 2 / 2)
# vertex and depth
vert = l1 / (2 * l2)
depth = -l1 * l1 / (4 * l2)
chk("vertex h* == v_ref / a   [units R]", vert, v_ / a_)
chk("depth == -Lambda_pen/2   [units E]", depth, -L / 2)
print("  => SS14's PROSE ('kappa is a decay-rate/length-scale', 'constant depth regardless of kappa')")
print("     describes the CORRECT family. Its FORMULAS describe the broken one:")
print("     frozen h* = 1/kappa has units R/E, and frozen depth -1/2 is dimensionless.")

# ---------------------------------------------------------------- 3. option 2 and 3 are the same family
hdr("3. Options 2 and 3 are NOT separate families - they are reductions of Option 1")
print("""
  Option 2:  lambda_1 = s*Lambda_ref/v,   lambda_2 = s*Lambda_ref/v^2
    vertex h* = lambda_1/(2 lambda_2) = v/2   -> PINNED, independent of s
    depth     = -lambda_1^2/(4 lambda_2) = -s*Lambda_ref/4
  Matching against Option 1: identical iff  a == 2  and  Lambda_pen == s*Lambda_ref/2.
""")
s_ = 2.9
o2_l1, o2_l2 = s_ * 3.7 / v_, s_ * 3.7 / (v_ * v_)
m_l1, m_l2 = coeffs_opt1(s_ * 3.7 / 2, 2.0, v_)
chk("Option 2 == Option 1 with a=2, Lambda_pen=s*Lambda_ref/2 (lambda_1)", o2_l1, m_l1)
chk("Option 2 == Option 1 with a=2, Lambda_pen=s*Lambda_ref/2 (lambda_2)", o2_l2, m_l2)
chk("Option 2 vertex is pinned at v/2", o2_l1 / (2 * o2_l2), v_ / 2)

# Option 3 bijection
tl1, tl2 = 0.8, 0.11
Lp = tl1 * tl1 / (2 * tl2)
aa = 2 * tl2 * v_ / tl1
b1, b2 = coeffs_opt1(Lp, aa, v_)
chk("Option 3 (free lambda_1,lambda_2) maps bijectively into Option 1 (lambda_1)", b1, tl1)
chk("Option 3 (free lambda_1,lambda_2) maps bijectively into Option 1 (lambda_2)", b2, tl2)
print("\n  => Option 1 (2 DOF) is the PARENT family. Option 2 is the reduction a==2 with the")
print("     outer scale swept. Option 3 is 'no reduction at all'. U-16 and U-18 are therefore")
print("     MATHEMATICALLY COUPLED (implementation needs both), but NOT one governance")
print("     decision: the family may be approved conditionally while U-18 stays open. (U16-03)")

# ---------------------------------------------------------------- 4. rescaling
hdr("4. Objective-rescaling invariance,  f -> c*f")
print("""
  Lambda_ref is positively homogeneous of degree 1 in f (true for BOTH candidate
  statistics in U-03: range and std), so Lambda_ref -> c*Lambda_ref.
""")
print(f"  {'quantity':<34} {'frozen SS14':>18} {'Option 1':>18}")
print("  " + "-" * 72)
rows = [("Lambda_ref", "c", "c"), ("slack lambda_S", "c", "c"),
        ("alpha (cardinality)", "c", "c"), ("lambda_1", "c", "c"),
        ("lambda_2", "c^2   <-- BREAKS", "c"),
        ("total energy Q", "mixes c and c^2", "c*Q"),
        ("argmin / tie set / A-B-C", "CAN CHANGE", "INVARIANT")]
for n, f_, o in rows:
    print(f"  {n:<34} {f_:>18} {o:>18}")
print("\n  Option 1: every term scales by exactly c, so Q -> c*Q with c>0.")
print("  argmin, tie sets and A/B/C classification are therefore invariant. The dimensionless")
print("  sweep coordinate a is NOT rescaled, so it indexes the same physical landscape in any units.")

# ---------------------------------------------------------------- 5. bias on real supports
hdr("5. Comparative neutrality on the REAL Stage-1 supports (units of Lambda_ref)")
print("""
  Slack, marginalized (SS11):   P_slack(h)/Lambda_ref = s*(h/v)^2 for h<0, else 0
  Option 1 reduction R2 (point-match at h=-v):  a = -1 + sqrt(1+2s)
  Option 1 reduction R1 (a = s)
  Option 2 (== a==2, outer scale swept)

  Reported: zeta/Lambda_ref MINUS P_slack/Lambda_ref.
    > 0  unbalanced penalized MORE on that residual -> directionally biases the
         infeasible-side comparison toward unbalanced
    < 0  unbalanced penalized LESS -> biases it toward slack
  NOTE (review U16-01): D is a PER-RESIDUAL LOCAL energy difference. Its sign does NOT by
  itself establish any change in the global ground state or in the C-rate -- objective gaps,
  other constraints and feasible-side rewards all enter the same argmin. C-rate effects
  require the experiment.
""")


def p_slack(s, h, v):
    return s * (h / v) ** 2 if h < 0 else 0.0


def zeta_o1(a, Lp_over_Lref, h, v):
    return Lp_over_Lref * (-a * (h / v) + (a * h / v) ** 2 / 2)


for label, v, support in [("SECTOR   (v_ref = 1)", 1.0, [-3, -2, -1, 0, 1, 2]),
                          ("BUDGET   (v_ref = 5, U-15 per-constraint)", 5.0, [-15, -10, -5, 0, 5, 10])]:
    print(f"\n  --- {label} ---")
    s = 1.0
    aR2 = -1 + math.sqrt(1 + 2 * s)
    print(f"      at s = {s}:  R1 a={s};  R2 a={aR2:.6f};  Opt2 a=2, outer={s/2}")
    print(f"      {'h':>6} {'slack':>10} | {'R1 diff':>10} {'R2 diff':>10} {'Opt2 diff':>10}")
    print("      " + "-" * 52)
    for h in support:
        ps = p_slack(s, h, v)
        d1 = zeta_o1(s, 1.0, h, v) - ps
        d2 = zeta_o1(aR2, 1.0, h, v) - ps
        do = zeta_o1(2.0, s / 2, h, v) - ps
        print(f"      {h:>6} {ps:>10.4f} | {d1:>10.4f} {d2:>10.4f} {do:>10.4f}")

print("""
  READING  (all statements below are about LOCAL per-residual penalty differences;
            see the standing caveat -- review U16-01):
   * On the FEASIBLE side (h > 0) slack is exactly 0 while every unbalanced candidate is
     NON-ZERO (and negative near its vertex). That is a structural difference, not a bias:
     it is the encoding distinctness the project exists to study. It makes it POSSIBLE for
     unbalanced to rank a feasible-SUBOPTIMAL portfolio below the true optimum, which would
     DIRECTIONALLY bias the primary (exact-recovery) comparison against unbalanced. Whether
     any such reordering actually occurs is an EXPERIMENTAL question.
   * On the INFEASIBLE side the sign of the gap DIRECTIONALLY biases the infeasible-side
     comparison relevant to H2. It does NOT decide the C-rate.
  => Neither the A-rate nor the C-rate is determined by these local signs. Objective gaps,
     the other constraint families, and feasible-side rewards all enter the same global
     argmin. GLOBAL A/B/C RATES REQUIRE SOLVING THE FULL EXPERIMENT.
  => 'Bias' is METRIC-DEPENDENT: no reduction is directionally neutral on both the feasible
     and infeasible sides at once. State it as a conditioning assumption, never as neutrality.
""")

# ---------------------------------------------------------------- 6. closed forms
hdr("6. Closed-form bias of each reduction  (w = |h|/v_ref > 0, infeasible side)")
print("""
  Writing the gap  D(w) = [zeta(-w*v) - P_slack(-w*v)] / Lambda_ref :

    R1   (a = s,          Lambda_pen = Lambda_ref)   D = s*w*[ 1 + w*(s/2 - 1) ]
    R2   (point-match,    Lambda_pen = Lambda_ref)   D = a*w*(1 - w),  a = -1+sqrt(1+2s)
    Opt2 (a = 2,          Lambda_pen = s*Lambda_ref/2) D = s*w
""")
for s_v in (0.5, 1.0, 2.0, 4.0):
    aR2 = -1 + math.sqrt(1 + 2 * s_v)
    for w in (0.5, 1.0, 2.0, 3.0):
        h, v = -w, 1.0
        ps = p_slack(s_v, h, v)
        chk(f"    R1 closed form  s={s_v} w={w}", zeta_o1(s_v,1.0,h,v)-ps, s_v*w*(1+w*(s_v/2-1)))
        chk(f"    R2 closed form  s={s_v} w={w}", zeta_o1(aR2,1.0,h,v)-ps, aR2*w*(1-w))
        chk(f"    Opt2 closed form s={s_v} w={w}", zeta_o1(2.0,s_v/2,h,v)-ps, s_v*w)

print("\n  CONSEQUENCES on the reachable sector support w in {1,2,3}:")
print("   * Opt2: D = s*w > 0 for ALL s,w -> unbalanced penalized MORE everywhere.")
print("     Moreover Opt2 has lambda_2 = s*Lambda_ref/v^2 = lambda_S exactly: it IS the")
print("     CURVATURE-MATCH rule, and D = s*w reproduces SS14's own rejected bias 'kappa*v > 0'.")
print("     SS14 explicitly rejected this rule. => Option 2 must be REJECTED on SS14's own grounds.")
print("   * R2: D = a*w*(1-w) is 0 at w=1, NEGATIVE for all w>1 -> unbalanced UNDER-penalized")
print("     on 2 of the 3 reachable sector violations -> DIRECTIONALLY biases the infeasible-")
print("     side comparison toward unbalanced yielding more C, the direction H2 predicts.")
print("     (A LOCAL energy bias, NOT a demonstrated C-rate effect -- review U16-01.)")
print("   * R1: sign flips at w = 2/(2-s) for s<2; D >= 0 everywhere once s >= 2.")
print("     Not one-directional across the sweep, but not neutral either.")
# curvature-match identity
chk("Opt2 lambda_2 == slack lambda_S (curvature match)", coeffs_opt1(2.9*3.7/2, 2.0, 5.0)[1], 2.9*3.7/(5.0**2))

# ---------------------------------------------------------------- 7. review R4
hdr("7. The reviewer's generalized weighted-neutral reduction (R4) - independent check")
print("""
  the reviewer proposes: for a PREDECLARED distribution of normalized violation magnitudes w,
  let r = E[w]/E[w^2]. Then choosing
        a = -r + sqrt(r^2 + 2s)
  makes the WEIGHTED MEAN of D(w) = a*w + (a^2/2 - s)*w^2 equal to zero.
  R2 (point-match) is the special case r = 1.
""")
chk("D(w) algebraic form matches direct evaluation",
    zeta_o1(0.9, 1.0, -2.0, 1.0) - p_slack(1.7, -2.0, 1.0),
    0.9*2.0 + (0.9**2/2 - 1.7)*4.0)

for r_lbl, ws in [("uniform on {1,2,3} (sector support)", [1.0, 2.0, 3.0]),
                  ("uniform on {1,2}", [1.0, 2.0]),
                  ("point mass at w=1 (=> r=1, recovers R2)", [1.0])]:
    Ew = sum(ws)/len(ws); Ew2 = sum(w*w for w in ws)/len(ws)
    r = Ew/Ew2
    print(f"\n  --- weights: {r_lbl};  r = E[w]/E[w^2] = {r:.6f} ---")
    for s_v in (0.5, 1.0, 4.0):
        a = -r + math.sqrt(r*r + 2*s_v)
        wmean = sum(a*w + (a*a/2 - s_v)*w*w for w in ws)/len(ws)
        chk(f"    weighted mean D == 0  (s={s_v}, a={a:.6f})", wmean, 0.0, tol=1e-9)
        chk(f"    a > 0                 (s={s_v})", a > 0, True)
    if len(ws) == 1:
        a_r4 = -r + math.sqrt(r*r + 2*1.0)
        chk("    r=1 case reproduces R2 exactly", a_r4, -1 + math.sqrt(1 + 2*1.0))

print("""
  VERDICT: the reviewer's R4 derivation is CORRECT and generalizes R2 (r = 1).
  BUT it is NOT a canonical neutral reduction: the weights and the support are themselves
  a conditioning choice that must be predeclared before results, and different weightings
  give different 'neutral' a(s). The reviewer does not recommend it without a predeclared
  sensitivity protocol, and neither do I. Recorded as candidate R4 in U-18.
""")

# ---------------------------------------------------------------- 8. U-18(b)
hdr("8. U-18(b): what the outer scale c_j can and cannot do")
print("""
  CORRECTED 2026-08-22 after independent audit. Earlier explanatory prose overclaimed both the
  nonzero-root count and what c can establish about comparative matching. BOTH claims were
  wrong. The CHECKS below were already correct ("at most one positive nonzero root"); only
  the explanatory PROSE overclaimed.

  With Lambda_pen,j = c_j * Lambda_ref:
      D(w) = c*a*w + (c*a^2/2 - s)*w^2  =  w * [ c*a + (c*a^2/2 - s)*w ]
      w_star = c*a / (s - c*a^2/2)

  CORRECT STATEMENTS:
   (i)   AT MOST ONE positive nonzero match. It exists only when s > c*a^2/2; at equality
         there is no nonzero root (D is linear), and when s < c*a^2/2 the root is negative
         and therefore outside the physical domain.
   (ii)  c cannot create a SECOND nonzero match: the factor [c*a + (...)w] is linear in w
         for every (c,a,s), so multi-residual neutrality is unreachable by any c.
   (iii) c DOES move the single match location, jointly with a. For a target w0 > 0,
         c = s*w0 / (a + a^2*w0/2) matches slack at w0; equivalently, fixing c and setting
         a(s) = -1 + sqrt(1 + 2s/c) preserves the R2-style match at w0 = 1.
   (iv)  c is not inert: it multiplies unbalanced's coefficients and NOT slack's, so it sets
         unbalanced-vs-slack relative strength at matched s. c = 1 is a CONDITIONING CHOICE.
""")
for c, a, s_v in [(1.0, 0.8, 2.0), (2.0, 1.5, 0.4), (1.0, 2.0, 2.0), (0.5, 1.2, 3.0)]:
    Kq = c * a * a / 2 - s_v
    if abs(Kq) < 1e-15:
        chk(f"    s == c*a^2/2 (c={c},a={a},s={s_v}): NO nonzero root", abs(c*a*3.7) > 1e-12, True)
    else:
        ws = c * a / (s_v - c * a * a / 2)
        chk(f"    w_star solves D=0 (c={c},a={a},s={s_v})",
            c*a*ws + (c*a*a/2 - s_v)*ws*ws, 0.0, tol=1e-9)
        chk(f"      positive iff s > c*a^2/2 (c={c},a={a},s={s_v})", ws > 0, Kq < 0)
for w0, a, s_v in [(1.0, 0.8, 2.0), (3.0, 1.5, 1.0), (0.5, 2.2, 4.0)]:
    c = s_v * w0 / (a + a * a * w0 / 2)
    chk(f"    c = s*w0/(a + a^2*w0/2) matches at w0={w0}",
        c*a*w0 + (c*a*a/2 - s_v)*w0*w0, 0.0, tol=1e-9)
for c, s_v in [(1.0, 1.0), (2.5, 4.0), (0.3, 0.7)]:
    a = -1 + math.sqrt(1 + 2 * s_v / c)
    chk(f"    a(s) = -1+sqrt(1+2s/c) preserves match at w0=1 (c={c},s={s_v})",
        c*a*1.0 + (c*a*a/2 - s_v)*1.0, 0.0, tol=1e-9)
    if abs(c - 1.0) < 1e-12:
        chk("      c=1 recovers R2 exactly", a, -1 + math.sqrt(1 + 2*s_v))

print("""
  VERDICT: the reviewer's U-18(b) recommendation (one common fixed c, provisionally c = 1) STANDS,
  but ONLY on its original grounds: minimality, transparency and identifiability. It is NOT
  supported by any fairness theorem.

  Narrower correct conclusion: per-constraint c_j cannot achieve MULTI-RESIDUAL neutrality
  (ii). It remains unjustified ON THE PRESENT RECORD because v_ref,j and the explicit sweep
  coordinates already supply the only stated constraint-family normalizations -- a separate
  c_j would need a predeclared external valuation, or a specified one-point matching rule
  per (iii).
""")

print("=" * 74)
if FAIL:
    print(f"RESULT: {len(FAIL)} CHECK(S) FAILED")
    for f in FAIL:
        print("  - " + f)
    raise SystemExit(1)
print("RESULT: ALL CHECKS PASSED")
print("=" * 74)
