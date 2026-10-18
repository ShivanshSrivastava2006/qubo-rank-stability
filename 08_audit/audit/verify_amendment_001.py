#!/usr/bin/env python3
"""
Verification of the algebraic claims in SCOPE_AMENDMENT_001 section 4 (U-18 reductions).

Checks, for the outer-scale Taylor family
    zeta_c(x) = Lambda_pen * [ -a*(h/v) + (a*h/v)^2 / 2 ]
against slack
    P_slack   = lambda_S * h^2,   lambda_S = s * Lambda_ref / v^2

  R1 (a = s, Lambda_pen = Lambda_ref) reintroduces the directional bias SS14 rejected.
  R2 (point-match at the reference violation) removes it, via a = -1 + sqrt(1 + 2s).

Standard library only.  Run: python3 research/audit/verify_amendment_001.py
"""
import math

FAIL = []


def chk(label, got, want, tol=1e-12):
    ok = abs(got - want) <= tol * max(1.0, abs(want))
    if not ok:
        FAIL.append(f"{label}: got {got!r} want {want!r}")
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}: {got:.12g}")


def slack_pen(s, Lam, v, h):
    return (s * Lam / v**2) * h**2


def unbal_pen(a, Lam_pen, v, h):
    return Lam_pen * (-a * (h / v) + (a * h / v) ** 2 / 2)


print("=" * 72)
print("VERIFY SCOPE_AMENDMENT_001 section 4 — U-18 candidate reductions")
print("=" * 72)

Lam, v = 3.7, 5.0          # arbitrary non-round values; v=5 mirrors the budget lattice

print("\n[1] R1 (a = s): unbalanced is ALWAYS penalized more at the reference violation")
print(f"      predicted excess = Lambda_ref * s^2 / 2\n")
print(f"  {'s':>8} {'slack@-v':>14} {'unbal@-v':>14} {'excess':>14} {'predicted':>14}")
print("  " + "-" * 68)
all_pos = True
for s in (0.01, 0.1, 1.0, 5.0, 20.0):
    sp = slack_pen(s, Lam, v, -v)
    up = unbal_pen(s, Lam, v, -v)          # R1: a = s, Lambda_pen = Lambda_ref
    exc, pred = up - sp, Lam * s**2 / 2
    all_pos &= exc > 0
    print(f"  {s:>8} {sp:>14.6f} {up:>14.6f} {exc:>14.6f} {pred:>14.6f}")
    chk(f"    R1 excess matches Lambda*s^2/2 at s={s}", exc, pred)
print(f"\n  R1 excess strictly positive for every s tested: {all_pos}")
print("  => R1 reproduces the SS14 directional bias (unbalanced always penalized more).")
if not all_pos:
    FAIL.append("R1 excess not strictly positive")

print("\n[2] R2 (point-match): a = -1 + sqrt(1 + 2s) equalizes the two at h = -v")
print(f"\n  {'s':>8} {'a(s)':>12} {'slack@-v':>14} {'unbal@-v':>14} {'diff':>12}")
print("  " + "-" * 64)
prev_a = -1.0
mono = True
for s in (0.01, 0.1, 1.0, 5.0, 20.0):
    a = -1 + math.sqrt(1 + 2 * s)
    mono &= a > prev_a
    prev_a = a
    sp = slack_pen(s, Lam, v, -v)
    up = unbal_pen(a, Lam, v, -v)
    print(f"  {s:>8} {a:>12.8f} {sp:>14.6f} {up:>14.6f} {up-sp:>12.3e}")
    chk(f"    R2 equalizes at s={s}", up, sp)
    chk(f"    R2 inverse round-trips at s={s}", a + a**2 / 2, s)
print(f"\n  a(s) strictly increasing (invertible on s>0): {mono}")
print(f"  a(s) > 0 for s > 0: {(-1 + math.sqrt(1 + 2*1e-9)) > 0}")
if not mono:
    FAIL.append("a(s) not monotone")

print("\n[3] R2 does NOT equalize away from the reference violation (expected, not a bug)")
print("      the two encodings still have genuinely different SHAPES — that is the premise")
print(f"\n  {'h':>8} {'slack':>14} {'unbal (R2)':>14}   note")
print("  " + "-" * 60)
s = 1.0
a = -1 + math.sqrt(1 + 2 * s)
for h, note in [(-3 * v, "3x reference violation"), (-v, "reference violation"),
                (0.0, "boundary"), (v, "feasible, slack flat"), (2 * v, "feasible, slack flat")]:
    sp = slack_pen(s, Lam, v, h) if h < 0 else 0.0     # marginalized slack: 0 when feasible
    up = unbal_pen(a, Lam, v, h)
    print(f"  {h:>8.1f} {sp:>14.6f} {up:>14.6f}   {note}")
print("\n  => slack is FLAT on the feasible side; unbalanced is not. Non-equivalence preserved.")

print("\n" + "=" * 72)
if FAIL:
    print(f"RESULT: {len(FAIL)} CHECK(S) FAILED")
    for f in FAIL:
        print("  - " + f)
    raise SystemExit(1)
print("RESULT: ALL CHECKS PASSED")
print("=" * 72)
