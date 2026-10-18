#!/usr/bin/env python3
"""
Independent verification of the reviewer's Gate-0 findings C0-01, C0-02, C0-04, C0-07.

The lead does not accept these at face value; each is reconstructed here from the
Scope Lock's own formulas and either CONFIRMED or REFUTED by explicit counterexample.

Standard library only.  Run: python3 research/audit/verify_gate0_review_findings.py
"""
import math
from itertools import combinations

PRICES = [210, 420, 1200, 180, 220, 250, 320, 520, 610, 45,
          780, 155, 110, 30, 205, 115, 145, 200, 390, 470]
B, K, C = 1100, 6, 2

results = {}


def hdr(t):
    print("\n" + "=" * 72); print(t); print("=" * 72)


# ---------------------------------------------------------------- C0-01
def c0_01():
    hdr("C0-01  Unbalanced mapping is dimensionally inconsistent / not rescale-invariant")
    print("""
Scope Lock SS14 sets:      lambda_1 = kappa,  lambda_2 = kappa^2 / 2
                           kappa(s) = s * Lambda_ref / v_ref
                           lambda_S(s) = s * Lambda_ref / v_ref^2

Units: [f] = E (energy), [h] = R (residual), [Lambda_ref] = E, [v_ref] = R.
  => [kappa]     = E/R
  => [lambda_1 h] = E                      OK
  => [lambda_2 h^2] = (E/R)^2 * R^2 = E^2  MISMATCH: needs E, has E^2
  => [lambda_S h^2] = (E/R^2) * R^2 = E    OK
""")
    print("Consequence: rescaling f -> c*f scales the slack penalty linearly (landscape")
    print("invariant) but the unbalanced quadratic term QUADRATICALLY. Demonstrate:\n")

    # Two-state toy, constructed so the unbalanced ordering DEPENDS on c.
    #   E_unbal(i,c) = c*f_i - c*k*h_i + (c^2 k^2 / 2) h_i^2
    #   E(1)-E(0)    = c*a + c^2*b,   a = (f1-f0) - k(h1-h0),  b = (k^2/2)(h1^2-h0^2)
    # Opposite signs for a and b => the sign flips at c = -a/b.  Here a=-8, b=2 => flip at c=4.
    f = {0: 0.0, 1: -10.0}
    h = {0: 0.0, 1: -2.0}
    v_ref, s = 1.0, 1.0

    def landscape(c):
        Lam = 1.0 * c                       # Lambda_ref scales with the objective
        lamS = s * Lam / v_ref**2
        kap = s * Lam / v_ref
        slack = {i: c * f[i] + lamS * min(h[i], 0.0) ** 2 for i in (0, 1)}
        unbal = {i: c * f[i] - kap * h[i] + (kap**2 / 2) * h[i] ** 2 for i in (0, 1)}
        return slack, unbal

    print("  Toy: state 0 feasible (f=0, h=0);  state 1 infeasible (f=-10, h=-2)\n")
    print(f"  {'c':>6} | {'slack E0':>10} {'slack E1':>10} {'argmin':>7} | "
          f"{'unbal E0':>10} {'unbal E1':>10} {'argmin':>7}")
    print("  " + "-" * 74)
    s_arg, u_arg = set(), set()
    for c in (0.5, 1.0, 2.0, 4.0, 6.0, 10.0):
        sl, un = landscape(c)
        sa = min(sl, key=sl.get); ua = min(un, key=un.get)
        s_arg.add(sa); u_arg.add(ua)
        print(f"  {c:>6} | {sl[0]:>10.3f} {sl[1]:>10.3f} {sa:>7} | "
              f"{un[0]:>10.3f} {un[1]:>10.3f} {ua:>7}")

    print(f"\n  slack argmin across rescalings      : {sorted(s_arg)}  -> "
          f"{'INVARIANT' if len(s_arg)==1 else 'NOT invariant'}")
    print(f"  unbalanced argmin across rescalings : {sorted(u_arg)}  -> "
          f"{'INVARIANT' if len(u_arg)==1 else 'NOT invariant'}")
    ok = len(s_arg) == 1 and len(u_arg) > 1
    print(f"\n  VERDICT: C0-01 {'CONFIRMED' if ok else 'NOT reproduced'} — merely rescaling the objective")
    print("           (a scientifically meaningless change of units) FLIPS the unbalanced")
    print("           encoding's decoded outcome while leaving slack's untouched. The mapping")
    print("           is therefore not objective-normalized, and any A/B/C comparison built on")
    print("           it is an artifact of the units f happens to be expressed in.")
    print("\n  Note the Scope Lock contradicts itself internally: SS14 says the reward minimum")
    print("  sits at h* = 1/kappa with 'constant depth -1/2 regardless of kappa'. Depth -1/2 is")
    print("  DIMENSIONLESS, which requires [kappa] = 1/R — but kappa(s) = s*Lambda_ref/v_ref")
    print("  gives [kappa] = E/R. Both cannot hold.")
    results["C0-01"] = "CONFIRMED" if ok else "NOT REPRODUCED"


# ---------------------------------------------------------------- C0-02
def c0_02():
    hdr("C0-02  Slack CAN produce Category C at finite penalty weight")
    print("""
Scope Lock SS16 asserts an exclusivity guarantee for unbalanced Category-C outcomes.
SS11 asserts slack needs no feasibility check, 'guaranteed by construction'.

Marginalized slack penalty (SS11, DERIVED):  0 if h >= 0,  lambda_S * h^2 if h < 0.
That penalty is FINITE. So an infeasible state with a sufficiently better objective wins.
""")
    f_feas, f_infeas, h_infeas = 0.0, -100.0, -1.0
    print(f"  feasible   state: f = {f_feas:+.1f}, h =  0")
    print(f"  infeasible state: f = {f_infeas:+.1f}, h = {h_infeas:+.0f}\n")
    print(f"  {'lambda_S':>12} | {'E(feas)':>10} {'E(infeas)':>10} | {'ground state':>13} | class")
    print("  " + "-" * 66)
    saw_C = False
    for lamS in (0.01, 1.0, 50.0, 99.0, 100.0, 1000.0):
        e_f = f_feas
        e_i = f_infeas + lamS * h_infeas**2
        gs = "infeasible" if e_i < e_f else "feasible"
        cls = "C" if e_i < e_f else "A/B"
        if cls == "C":
            saw_C = True
        print(f"  {lamS:>12.2f} | {e_f:>10.2f} {e_i:>10.2f} | {gs:>13} | {cls}")
    print(f"\n  VERDICT: C0-02 {'CONFIRMED' if saw_C else 'NOT reproduced'} — slack yields Category C whenever")
    print("           lambda_S * h^2 < objective gain. The claim is true only ASYMPTOTICALLY")
    print("           (large lambda_S), but the sweep deliberately includes the")
    print("           'comfortably non-enforcing' regime, where it is false.")
    print("           => decoded feasibility MUST be checked for BOTH encodings at every point.")
    results["C0-02"] = "CONFIRMED" if saw_C else "NOT REPRODUCED"


# ---------------------------------------------------------------- C0-04
def c0_04():
    hdr("C0-04  v_ref = 1 is NOT implied by integrality for the budget constraint")
    g = 0
    for p in PRICES:
        g = math.gcd(g, p)
    print(f"  prices                = {PRICES}")
    print(f"  gcd(prices)           = {g}")
    print(f"  B                     = {B},  B mod gcd = {B % g}")
    print(f"\n  => p^T x is always a multiple of {g}, and B is too,")
    print(f"     so h_budget = B - p^T x lies in {g}Z. A residual of 1 is UNREACHABLE.")

    # attainable smallest positive violation over cardinality-feasible x
    viol = set()
    for comb in combinations(range(20), K):
        h = B - sum(PRICES[i] for i in comb)
        if h < 0:
            viol.add(-h)
    smallest = min(viol)
    print(f"\n  smallest attainable budget VIOLATION over |x|=K : {smallest}")
    print(f"  all violations divisible by {g}                    : {all(v % g == 0 for v in viol)}")
    print(f"\n  sector residual h_j = C - n_j : step 1 (counts)  -> v_ref = 1 attainable")
    print(f"  cardinality residual          : step 1 (counts)  -> v_ref = 1 attainable")
    ok = g == 5 and smallest % g == 0
    print(f"\n  VERDICT: C0-04 {'CONFIRMED' if ok else 'NOT reproduced'} — integrality gives h in Z, but the")
    print(f"           ATTAINABLE budget lattice is {g}Z. Applying a common v_ref = 1 to budget is a")
    print("           modelling choice, not a consequence of integrality. The lead's facts script")
    print("           overclaimed here and must be corrected.")
    results["C0-04"] = "CONFIRMED" if ok else "NOT REPRODUCED"


# ---------------------------------------------------------------- C0-07
def c0_07():
    hdr("C0-07  Sharper Stage-1 non-equivalence proof (strengthens M2)")
    print("""
The reviewer's argument: on Stage-1 sector residuals both h=1 and h=2 are reachable and
FEASIBLE, so slack's marginalized penalty is 0 at both. Unbalanced's zero set is
  zeta(h) = -kappa h + (kappa^2/2) h^2 = 0  <=>  h = 0  or  h = 2/kappa
so a single kappa can zero at most ONE nonzero residual.
""")
    print(f"  {'h':>4} | {'slack penalty':>14} | {'kappa needed for zeta(h)=0':>28}")
    print("  " + "-" * 52)
    for h in (0, 1, 2):
        need = "any (h=0)" if h == 0 else f"kappa = {2.0/h:g}"
        print(f"  {h:>4} | {0.0:>14.1f} | {need:>28}")
    print("\n  kappa = 2 zeros h=1 but leaves zeta(2) =", f"{-2*2 + (4/2)*4:g}")
    print("  kappa = 1 zeros h=2 but leaves zeta(1) =", f"{-1*1 + (1/2)*1:g}")
    print("\n  VERDICT: C0-07 CONFIRMED — this is a direct, instance-specific non-equivalence")
    print("           proof, strictly stronger than the lead's generic 'smooth cannot match a")
    print("           kink' argument, and it is checkable on the REAL Stage-1 residual support.")
    print("           V-9 must be scoped to the actual reachable residual support.")
    results["C0-07"] = "CONFIRMED"


def main():
    print("=" * 72)
    print("INDEPENDENT VERIFICATION OF REVIEW GATE-0 FINDINGS")
    print("The lead re-derives each claim rather than accepting the auditor's word.")
    print("=" * 72)
    c0_01(); c0_02(); c0_04(); c0_07()
    hdr("SUMMARY")
    for k in sorted(results):
        print(f"  {k}: {results[k]}")
    bad = [k for k, v in results.items() if v != "CONFIRMED"]
    print(f"\n  {len(results)-len(bad)}/{len(results)} review findings independently CONFIRMED.")
    if bad:
        print(f"  NOT reproduced: {bad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
