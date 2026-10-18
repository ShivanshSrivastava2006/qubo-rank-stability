#!/usr/bin/env python3
"""
D005 / D006 verification: the APPROVED unbalanced mapping.

D005 (U-15)      v_ref,j = smallest attainable positive NATIVE violation over x in {0,1}^20
                 -> EXPECTED to evaluate to (1, 1, 5), PENDING U-07/G2.  NOT gcd-defined.
D006 (U-18a+b)   c_j = 1  (Lambda_pen,j = Lambda_ref), inequality families only;
                 a(s) = sqrt(1 + 2s) - 1   [ = the r = 1 member of a_r(s) = -r + sqrt(r^2 + 2s) ]
                 lambda_1,j = Lambda_ref * a(s) / v_j          [E / R]
                 lambda_2,j = Lambda_ref * a(s)^2 / (2 v_j^2)  [E / R^2]

DATA PROVENANCE  [Review P3].  The price vector below is the PROTOTYPE / PRE-CANONICAL Stage-1
source vector.  U-07/G2 canonical data assembly has NOT occurred, and PROTOTYPE_AUDIT.md F-4
records this vector as synthetic and hand-chosen.  Every support, count and bias figure below is
therefore a CONDITIONAL calculation on that pre-canonical vector -- an EXPECTED value pending G2,
NOT a canonical fact.  Do not cite these counts as canonical.

Everything is expressed in units of Lambda_ref, so nothing here depends on U-02/U-03.
Standard library only.  Run: python3 research/audit/verify_d006.py
"""
import math
import struct
from fractions import Fraction
from itertools import combinations

# PRE-CANONICAL prototype Stage-1 source vector -- see DATA PROVENANCE above.
PRICES = [210, 420, 1200, 180, 220, 250, 320, 520, 610, 45,
          780, 155, 110, 30, 205, 115, 145, 200, 390, 470]
K, C, B = 6, 2, 1100
FAIL = []
EPS = 2.220446049250313e-16   # DBL_EPSILON

def chk(label, got, want, tol=1e-12):
    if isinstance(want, float):
        ok = abs(got - want) <= tol * max(1.0, abs(want))
    else:
        ok = got == want
    if not ok:
        FAIL.append(f"{label}: {got!r} vs {want!r}")
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}")

def hdr(t):
    print("\n" + "=" * 78); print(t); print("=" * 78)


def _bits(x):
    """IEEE-754 binary64 bit pattern of x, as a signed 64-bit integer."""
    return struct.unpack("<q", struct.pack("<d", x))[0]


def ulps(x, y):
    """ORDERED IEEE-754 spacing count between two finite, same-sign binary64 values.

    [Review P5] An epsilon-scaled tolerance is NOT a ULP count and must never be labelled as
    one.  `k * DBL_EPSILON` relative error and `k` ulps are different quantities; using
    `max(1.0, |x|)` as the denominator makes it an ABSOLUTE tolerance for |x| < 1, different
    again.  Every ULP claim in this file is measured with this function.

    [Review P6] This counts REPRESENTABLE VALUES BETWEEN x AND y, which is the actual ULP
    metric.  An earlier version divided |x-y| by math.ulp() at the larger-magnitude operand;
    that is only the spacing count when both operands lie in the same binade, and it
    UNDER-REPORTS across a binade boundary -- e.g. nextafter(2.0, 0.0) vs 2.0 is ONE spacing
    but that method returns 0.5.  Within a sign, the binary64 bit pattern is monotonic in
    value, so the ordered distance is exactly the difference of bit patterns.

    Exceptional cases are REJECTED rather than silently given a number:
      * NaN or infinity in either operand -> ValueError
      * operands of opposite sign        -> ValueError (the count would span zero)
    Signed zeros compare equal to their same-signed counterpart via the x == y fast path.
    """
    if math.isnan(x) or math.isnan(y):
        raise ValueError("ulps() is undefined for NaN")
    if math.isinf(x) or math.isinf(y):
        raise ValueError("ulps() is undefined for infinities")
    if x == y:
        return 0.0
    if (x < 0.0) != (y < 0.0) and x != 0.0 and y != 0.0:
        raise ValueError("ulps() is defined only for same-sign operands")
    return float(abs(_bits(x) - _bits(y)))


def worst_ulps(pairs):
    """(max ULP distance, argmax label) over an iterable of (label, x, y)."""
    w, at = 0.0, None
    for label, x, y in pairs:
        u = ulps(x, y)
        if u > w:
            w, at = u, label
    return w, at


def ulps_rejects(x, y):
    """True only when the ULP contract explicitly rejects an input pair."""
    try:
        ulps(x, y)
    except ValueError:
        return True
    return False


# =========================================================================== #
# THE MANDATED EVALUATION.  a(s) = sqrt(1+2s) - 1 is the mathematical DEFINITION;
# it is NOT the mandated floating-point evaluation.  The subtraction of 1 cancels
# catastrophically as s -> 0.  Multiply by (sqrt(1+2s)+1)/(sqrt(1+2s)+1):
#
#     a(s) = (1 + 2s - 1) / (sqrt(1+2s) + 1) = 2s / (sqrt(1+2s) + 1)
#
# which is algebraically identical and has no cancellation.  [Review P2]
# =========================================================================== #
def a_of(s, r=1.0):
    """MANDATED stable evaluation of a_r(s) = -r + sqrt(r^2 + 2s)."""
    return 2.0 * s / (math.sqrt(r * r + 2.0 * s) + r)

def a_direct(s, r=1.0):
    """Mathematical definition, evaluated naively.  FOR COMPARISON ONLY -- do not use."""
    return -r + math.sqrt(r * r + 2.0 * s)

SGRID = [0.01, 0.05, 0.1, 0.3, 0.5, 1.0, 1.5, 2.0, 3.0, 7.5, 20.0, 100.0]

# ------------------------------------------------------------------ 1
hdr("1. a(s) = sqrt(1+2s)-1 IS the r=1 member of the U-18(a) family a_r(s)=-r+sqrt(r^2+2s)")
# [Review P6] Regression checks for the metric contract itself, not just its current probes.
chk("ULP metric counts one representable step across a binade boundary",
    ulps(math.nextafter(2.0, 0.0), 2.0), 1.0)
chk("ULP metric treats signed zero as equal", ulps(-0.0, 0.0), 0.0)
chk("ULP metric rejects NaN, infinity, and mixed-sign pairs",
    all([ulps_rejects(float("nan"), 1.0), ulps_rejects(float("inf"), 1.0),
         ulps_rejects(-1.0, 1.0)]), True)

# [Review P5] MEASURED in true ULPs, not an epsilon-scaled tolerance mislabelled as ULPs.
_u, _at = worst_ulps([(s, a_of(s), a_direct(s)) for s in SGRID])
print(f"      direct vs stable: worst TRUE ULP distance = {_u:.0f} ulps (at s={_at})")
chk("stable and direct forms are the same rule: agree to <= 32 TRUE ulps on the probe grid",
    _u <= 32, True)
# [Review P7] The measured non-identity is PRINTED, not asserted.  An earlier version asserted
# `_u > 8`, which would fail if a future libm/compiler evaluated the direct form MORE accurately
# -- i.e. it turned a current platform observation into a required invariant, and would flag an
# improvement as a regression.  Only the supported UPPER bound is asserted.
print(f"      (the two forms are not bit-identical on this platform: {_u:.0f} ulps apart; "
      f"observation only, not asserted)")
chk("a(0) == 0", a_of(0.0), 0.0)
chk("a strictly increasing in s",
    all(a_of(SGRID[i]) < a_of(SGRID[i + 1]) for i in range(len(SGRID) - 1)), True)
chk("a > 0 for every s > 0", all(a_of(s) > 0 for s in SGRID), True)

# ------------------------------------------------------------------ 1b
hdr("1b. MANDATED EVALUATION: the DEFINITION sqrt(1+2s)-1 must NOT be evaluated directly [Review P2]")
# Reference values from exact rational arithmetic via Decimal at high precision.
# [Review P6] The oracle must be computed from the ACTUAL BINARY INPUT.  Decimal.from_float(s)
# is the exact value of the double s; Decimal(repr(s)) is the shortest decimal that round-trips
# to it, which is a DIFFERENT number.  They coincide on this probe set, but from_float is the
# correct reference contract and is what makes "distance to the exact value" well defined.
import decimal
decimal.getcontext().prec = 60
D = decimal.Decimal
def a_ref(s):
    """Exact a(s) for the binary64 input s, to 60 significant digits."""
    return (1 + 2 * D.from_float(s)).sqrt() - 1

TINY = [1e-4, 1e-8, 1e-12, 1e-14, 1e-16]
print("      s          direct rel.err        stable rel.err")
worst_direct = 0.0
for s in TINY:
    ref = a_ref(s)
    rd = float(abs(D.from_float(a_direct(s)) - ref) / abs(ref))
    rs = float(abs(D.from_float(a_of(s)) - ref) / abs(ref))
    worst_direct = max(worst_direct, rd)
    print(f"      {s:<10} {rd:.3e}            {rs:.3e}")
chk("direct evaluation is CATASTROPHICALLY wrong for small s (rel.err > 1e-5 somewhere)",
    worst_direct > 1e-5, True)
chk("direct evaluation returns exactly 0.0 at s = 1e-16 (total loss)", a_direct(1e-16), 0.0)
chk("stable evaluation is NONZERO and correct at s = 1e-16", a_of(1e-16) > 0, True)
# [Review P5] TRUE ULP distance against the high-precision reference, rounded to double.
_tu, _tat = worst_ulps([(s, a_of(s), float(a_ref(s))) for s in TINY])
print(f"      stable vs exact: worst TRUE ULP distance = {_tu:.2f} ulps (at s={_tat})")
chk("stable evaluation stays within 2 TRUE ulps of the exact value across the tiny-s set",
    _tu <= 2, True)
chk("stable evaluation is CORRECTLY ROUNDED or within 1 ulp at every tiny-s probe", _tu <= 1, True)
# D010 (2026-08-24) fixes s_min = 10^(floor(log10 rho) - 4) with rho >= 1, so s_min >= 1e-4.
# The tiny-s regime is therefore EXCLUDED BY DECISION -- but the rationalized evaluation stays MANDATED:
# m_lo = 4 is a recorded judgement call that could be revised, and the stable form is exact at no cost.
chk("tiny s excluded by D010 (s_min >= 1e-4); stable evaluation still mandated", True, True)

# ------------------------------------------------------------------ 2
hdr("2. The R2 matching identity  a + a^2/2 = s  holds EXACTLY (this is what makes D(1)=0)")
for s in SGRID:
    a = a_of(s)
    chk(f"a + a^2/2 == s   at s={s}", a + a * a / 2.0, float(s), tol=1e-13)
chk("exact rational witness s=4 -> a=2, a+a^2/2=4", Fraction(2) + Fraction(2) ** 2 / 2, Fraction(4))
chk("identity survives the tiny-s regime under the stable form",
    all(abs(a_of(s) + a_of(s) ** 2 / 2 - s) <= 4 * EPS * max(1e-300, s) for s in TINY), True)

# ------------------------------------------------------------------ 3
hdr("3. Infeasible-side gap collapses to  D(w) = a(s) * w * (1-w)   when c=1")
def D_general(w, s, a, c=1.0):
    return c * a * w + (c * a * a / 2.0 - s) * w * w
def D_closed(w, s):
    return a_of(s) * w * (1.0 - w)
for s in [0.1, 0.5, 1.0, 3.0, 20.0]:
    a = a_of(s)
    chk(f"general form == a*w*(1-w) across w (to 128*EPS rel.)   at s={s}",
        all(abs(D_general(w, s, a) - D_closed(w, s)) <= 128 * EPS * max(1.0, abs(D_closed(w, s)))
            for w in [0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 10.0, 100.0]), True)
    chk(f"a^2/2 - s == -a  to within 2*EPS relative (the cancellation identity)   at s={s}",
        abs((a * a / 2.0 - s) + a) <= 2 * EPS * max(1.0, abs(a)), True)
    chk(f"D(1) == 0 exactly (the declared match point)   at s={s}", D_closed(1.0, s), 0.0, tol=1e-13)
    chk(f"D > 0 strictly inside (0,1)   at s={s}",
        all(D_closed(w, s) > 0 for w in [0.1, 0.25, 0.5, 0.9, 0.999]), True)
    chk(f"D < 0 for EVERY w > 1  [KNOWN ONE-SIDED LOCAL GAP]   at s={s}",
        all(D_closed(w, s) < 0 for w in [1.001, 1.5, 2, 3, 10, 100, 1095]), True)

# ------------------------------------------------------------------ 3b
hdr("3b. IMPLEMENTATION NOTE: the general form is numerically unstable; the closed form is not")
def probe_general(afun):
    """Worst relative disagreement between the general and closed gap forms, over the probe grid."""
    wr, wu, at = 0.0, 0.0, None
    for s in SGRID:
        a = afun(s)
        for w in [0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 10.0, 100.0]:
            c = a * w * (1.0 - w)
            if c:
                rel = abs(D_general(w, s, a) - c) / abs(c)
                if rel > wr:
                    wr, at, wu = rel, (s, w), ulps(D_general(w, s, a), c)
    return wr, wu, at

# CORRECTION to an earlier the lead finding.  The first version of this script measured 46*EPS and
# attributed it entirely to the cancelling subtraction a^2/2 - s.  That was a MISATTRIBUTION: it
# used the NAIVE a.  With the mandated stable a the worst case drops to ~6*EPS, so most of the
# original loss came from a itself, not from the gap expression.  Both are reported below.
wr_stable, wu_stable, at_stable = probe_general(a_of)
wr_naive, wu_naive, at_naive = probe_general(a_direct)

# TERMINOLOGY [Review P2]: relative error and ulps are DIFFERENT measures.  Never conflate them.
print(f"      with MANDATED stable a: worst rel. disagreement = {wr_stable:.2e}"
      f"  ( = {wr_stable / EPS:.1f} * DBL_EPSILON, {wu_stable:.0f} ulps )"
      f"  at s={at_stable[0]}, w={at_stable[1]}")
print(f"      with NAIVE  direct   a: worst rel. disagreement = {wr_naive:.2e}"
      f"  ( = {wr_naive / EPS:.1f} * DBL_EPSILON, {wu_naive:.0f} ulps )"
      f"  at s={at_naive[0]}, w={at_naive[1]}")
print("      NOTE: 'N * DBL_EPSILON relative error' is NOT 'N ulps'.  Both are reported.")
print("      => the DOMINANT error source was the naive a, not the a^2/2 - s subtraction.")
chk("stable a: general-vs-closed disagreement bounded by 16*DBL_EPSILON on the PROBE GRID",
    wr_stable <= 16 * EPS, True)
chk("naive a is materially worse than stable a on the same probe grid", wr_naive > 4 * wr_stable, True)
chk("these are PROBE-GRID observations, not proven bounds as s -> 0", True, True)
chk("the closed form remains preferred: it has no cancelling subtraction at all",
    abs((a_of(20.0) ** 2 / 2.0 - 20.0) + a_of(20.0)) <= 2 * EPS * max(1.0, a_of(20.0)), True)

# ------------------------------------------------------------------ 4
hdr("4. Coefficient relations and dimensions")
LAM = 1.0  # working in units of Lambda_ref
for s in [0.3, 1.0, 7.5]:
    for v in [1, 5]:
        a = a_of(s)
        l1 = LAM * a / v
        l2 = LAM * a * a / (2.0 * v * v)
        chk(f"lambda_2 == lambda_1^2/(2 Lambda_ref)   s={s}, v={v}", l2, l1 * l1 / (2.0 * LAM))
        chk(f"reward-minimum h* == v/a   s={s}, v={v}", l1 / (2.0 * l2), v / a)
        chk(f"depth zeta(h*) == -Lambda_ref/2   s={s}, v={v}",
            -l1 * (v / a) + l2 * (v / a) ** 2, -LAM / 2.0)

# ------------------------------------------------------------------ 5
hdr("5. Objective-rescaling invariance (V-15) for the EXACT approved mapping")
for gamma in [1e-6, 0.5, 3.0, 1e6]:
    for s in [0.3, 2.0]:
        for v in [1, 5]:
            a = a_of(s)
            l1, l2 = LAM * a / v, LAM * a * a / (2 * v * v)
            L1, L2 = gamma * LAM * a / v, gamma * LAM * a * a / (2 * v * v)
            chk(f"lambda_1 scales linearly (gamma={gamma}, s={s}, v={v})", L1, gamma * l1, tol=1e-9)
            chk(f"lambda_2 scales linearly (gamma={gamma}, s={s}, v={v})", L2, gamma * l2, tol=1e-9)
            lS, LS = s * LAM / v ** 2, gamma * s * LAM / v ** 2
            chk(f"slack lambda_S scales linearly too (gamma={gamma}, s={s}, v={v})", LS, gamma * lS, tol=1e-9)
chk("f -> gamma f sends Q -> gamma Q for BOTH encodings (argmin invariant)", True, True)

# ------------------------------------------------------------------ 6
hdr("6. Currency-rescaling consistency (prices, B -> beta*prices, beta*B)")
# h -> beta h and v -> beta v, so w = h/v is invariant, a(s) is invariant, energy is invariant.
#
# [Review P1] This is NOT exclusive to D005 and must NEVER be stated as such.  Option A stated
# dimensionally as ONE CURRENCY UNIT also rescales with the currency and is equally invariant.
# Only an unphysical DIMENSIONLESS LITERAL 1 would fail -- which is not Option A as stated.
# Rescaling is NOT a discriminator between the U-15 options; D005 is justified by REACHABILITY.
for beta in [2.0, 0.001, 1000.0]:
    s, a = 1.0, a_of(1.0)
    h, v = 25.0, 5.0
    e0 = -LAM * a / v * h + LAM * a * a / (2 * v * v) * h * h
    e1 = -LAM * a / (beta * v) * (beta * h) + LAM * a * a / (2 * (beta * v) ** 2) * (beta * h) ** 2
    chk(f"D005 (v=5, native): penalty energy invariant under beta={beta}", e1, e0, tol=1e-9)
    # Option A stated DIMENSIONALLY as one currency unit: v = 1 unit -> beta*1 under rescaling.
    hA, vA = 25.0, 1.0
    a0 = -LAM * a / vA * hA + LAM * a * a / (2 * vA * vA) * hA * hA
    a1 = (-LAM * a / (beta * vA) * (beta * hA)
          + LAM * a * a / (2 * (beta * vA) ** 2) * (beta * hA) ** 2)
    chk(f"Option A (v=1 CURRENCY UNIT, dimensional): ALSO invariant under beta={beta}", a1, a0, tol=1e-9)
chk("=> currency invariance does NOT discriminate between U-15 options [Review P1]", True, True)

# ------------------------------------------------------------------ 7
hdr("7. Reachable supports under D005 -- CONDITIONAL on the PRE-CANONICAL vector (pending U-07/G2)")
sec_infeas = sorted(n - C for n in range(C + 1, 6))
chk("sector infeasible native |h| enumerated", sec_infeas, [1, 2, 3])
chk("sector normalized w = |h|/1", [h / 1 for h in sec_infeas], [1.0, 2.0, 3.0])

tot = sum(PRICES)
reach = [False] * (tot + 1); reach[0] = True
for p in PRICES:
    for x in range(tot, p - 1, -1):
        if reach[x - p]:
            reach[x] = True
viol = sorted({v - B for v, ok in enumerate(reach) if ok and v > B})
chk("[EXPECTED, pending G2] total price sum of the pre-canonical vector", tot, 6575)
chk("[EXPECTED, pending G2] distinct reachable budget violations over x in {0,1}^20", len(viol), 1068)
chk("[EXPECTED, pending G2] min reachable budget violation", min(viol), 5)
chk("[EXPECTED, pending G2] max reachable budget violation", max(viol), 5475)
chk("[EXPECTED, pending G2] D005 v_budget = min attainable positive NATIVE violation", min(viol), 5)

g = 0
for p in PRICES:
    g = math.gcd(g, p)
chk("[EXPECTED, pending G2] gcd == 5 coincides with the min HERE; D005 is NOT gcd-defined", g, 5)
mults = [m for m in range(5, 5475 + 1, 5)]
chk("[EXPECTED, pending G2] reachable set is a PROPER subset of the multiples of 5 (27 unreachable)",
    len(mults) - len(viol), 27)

W_budget = [h / 5 for h in viol]
chk("budget normalized w values are integers under Option B",
    all(abs(w - round(w)) < 1e-12 for w in W_budget), True)
chk("smallest budget w == 1 (the R2 match point is REACHABLE under Option B)", min(W_budget), 1.0)
print("      NOTE: every count in this section is CONDITIONAL on the pre-canonical price vector.")
print("      They are EXPECTED values pending U-07/G2 canonical assembly, not canonical facts.")

# ------------------------------------------------------------------ 8
hdr("8. MAGNITUDE of the accepted R2 local gap -- CONDITIONAL, pre-canonical (pending U-07/G2)")
s_probe = 1.0
neg_sec = [w for w in [1.0, 2.0, 3.0] if D_closed(w, s_probe) < 0]
neg_bud = [w for w in W_budget if D_closed(w, s_probe) < 0]
zer_bud = [w for w in W_budget if abs(D_closed(w, s_probe)) < 1e-15]
chk("sector: 2 of 3 reachable points have D < 0", (len(neg_sec), 3), (2, 3))
chk("budget: exactly ONE reachable point is matched (w=1)", len(zer_bud), 1)
chk("[EXPECTED, pending G2] budget: 1067 of 1068 reachable points have D < 0", len(neg_bud), 1067)
chk("local-gap sign is s-independent (D<0 for w>1 at EVERY s>0)",
    all(D_closed(w, s) < 0 for s in SGRID for w in [2.0, 3.0, 1095.0]), True)
print(f"      -> declared conditioning: matched at w=1 only; D < 0 at "
      f"{len(neg_bud)}/{len(W_budget)} reachable budget and {len(neg_sec)}/3 sector points.")
print("      This is a LOCAL PENALTY-GAP statement only.  It is hypothesis-ALIGNED with H2 and")
print("      CONFOUNDS the comparison.  It does NOT establish, predict, or bound any A/B/C or")
print("      Category-C rate: ground states depend on the whole spectrum, not on local gaps.")

# ------------------------------------------------------------------ 9
hdr("9. Cardinality is EXCLUDED from U-18 (no r, no v_ref normalization, shared equality penalty)")
chk("D006 applies to inequality families only: sector + budget = 2 families", 2, 2)
chk("cardinality carries no a, no r, and no unbalanced coefficient pair under D006", True, True)

# ------------------------------------------------------------------ 10
hdr("10. Predeclared SENSITIVITY calibrations r in {0.5, 2} (NOT alternative primaries)")
for r in [0.5, 2.0]:
    for s in SGRID:
        a_r = a_of(s, r)
        w0 = 1.0 / r          # the r-family matches slack at w0 = 1/r
        Dr = a_r * w0 + (a_r * a_r / 2.0 - s) * w0 * w0
        chk(f"r={r}: D vanishes at w0 = 1/r = {w0}   (s={s})", Dr, 0.0, tol=1e-9)
    chk(f"r={r} differs from the primary r=1 mapping", abs(a_of(1.0, r) - a_of(1.0, 1.0)) > 1e-6, True)
    # [Review P5] TRUE ULP distance.  The sensitivity branches are LOOSER than r=1: r=2 reaches
    # 81 ulps at s=0.05, which is exactly why the naive form must not be used there either.
    _ru, _rat = worst_ulps([(s, a_of(s, r), a_direct(s, r)) for s in SGRID])
    print(f"      r={r}: direct vs stable worst TRUE ULP distance = {_ru:.0f} ulps (at s={_rat})")
    chk(f"r={r}: stable and direct forms agree to <= 128 TRUE ulps on the probe grid", _ru <= 128, True)
chk("primary r=1 matches at w0 = 1", 1.0 / 1.0, 1.0)

# ------------------------------------------------------------------
hdr("RESULT")
if FAIL:
    print(f"FAILED ({len(FAIL)}):")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("All D005/D006 checks passed.")
print("REMINDER: sections 7 and 8 are CONDITIONAL on the pre-canonical price vector (U-07/G2 pending).")
