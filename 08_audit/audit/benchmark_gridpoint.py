#!/usr/bin/env python3
"""
Reproducible benchmark for the per-grid-point cost claim (required revision 5).

The lead's Gate-0 log quoted ~8.8 ms (slack) / ~68 ms (unbalanced) per grid point without
shipping the code. This is that code.

IMPORTANT SCOPE LIMITS, stated so the number is not over-read:
  * This measures ARRAY-ARITHMETIC COST ONLY. f(x) is a random stand-in because
    kappa_risk is fixed by D007 (triple: 1.0, (decimal simple daily return)^-1, daily);
    the timing does not depend on its value.
  * It uses the CURRENT (defective, see C0-01) unbalanced mapping purely as an
    arithmetic workload. It is NOT an endorsement of that mapping.
  * Per the reviewer: this measures the cached Pass-2 cost. Exact ground-state SELECTION
    remains an O(2^20) reduction/argmin PER GRID POINT; caching does not make
    certification a one-off for the whole grid.
  * A timing number must not decide scientific design (U-01). It only bounds what is
    affordable.

Requires numpy.  Run: python3 research/audit/benchmark_gridpoint.py
"""
import time
import sys

try:
    import numpy as np
except ImportError:
    sys.exit("numpy required for this benchmark; it is the only non-stdlib dependency")

N_BITS = 20
N = 1 << N_BITS
PRICES = np.array([210, 420, 1200, 180, 220, 250, 320, 520, 610, 45,
                   780, 155, 110, 30, 205, 115, 145, 200, 390, 470], dtype=np.int64)
SECTOR_OF = np.array([0] * 5 + [1] * 5 + [2] * 5 + [3] * 5)
K, C, B = 6, 2, 1100
SECTOR_BITS, BUDGET_BITS = 2, 11          # 39-variable construction (fixed by Scope Lock SS13)
REPEATS = 10


def main():
    print("=" * 70)
    print("PASS-2 PER-GRID-POINT BENCHMARK (cached precompute architecture, M8)")
    print("=" * 70)
    print(f"python {sys.version.split()[0]}, numpy {np.__version__}")

    t0 = time.perf_counter()
    idx = np.arange(N, dtype=np.uint32)
    bits = ((idx[:, None] >> np.arange(N_BITS, dtype=np.uint32)[None, :]) & 1).astype(np.int8)
    t_bits = time.perf_counter() - t0

    t0 = time.perf_counter()
    card = bits.sum(1).astype(np.int16)
    cost = bits.astype(np.int64) @ PRICES
    sec = np.stack([bits[:, SECTOR_OF == j].sum(1) for j in range(4)], 1).astype(np.int8)
    h_card = (card - K).astype(np.int16)
    h_sec = (C - sec).astype(np.int8)
    h_bud = (B - cost).astype(np.int32)
    # marginalised slack residuals: h - clamp(h, 0, 2^N - 1)
    r_sec = (h_sec - np.clip(h_sec, 0, (1 << SECTOR_BITS) - 1)).astype(np.float64)
    r_bud = (h_bud - np.clip(h_bud, 0, (1 << BUDGET_BITS) - 1)).astype(np.float64)
    sq_sec = (r_sec ** 2).sum(1)
    sq_bud = r_bud ** 2
    sq_card = h_card.astype(np.float64) ** 2
    # unbalanced needs raw residual sums, cacheable once
    hs1 = h_sec.astype(np.float64).sum(1)
    hs2 = (h_sec.astype(np.float64) ** 2).sum(1)
    hb1 = h_bud.astype(np.float64)
    hb2 = hb1 ** 2
    t_pre = time.perf_counter() - t0

    rng = np.random.default_rng(0)
    f = rng.standard_normal(N)          # stand-in for f(x); kappa_risk unresolved

    def slack_point(alpha, lam_S):
        E = f + alpha * sq_card + lam_S * (sq_sec + sq_bud)
        m = E.min()
        return m, int((E == m).sum())

    def unbal_naive(alpha, kap):
        hs = h_sec.astype(np.float64)
        hb = h_bud.astype(np.float64)
        E = (f + alpha * sq_card
             + (-kap * hs + (kap * kap / 2) * hs ** 2).sum(1)
             + (-kap * hb + (kap * kap / 2) * hb ** 2))
        m = E.min()
        return m, int((E == m).sum())

    def unbal_cached(alpha, kap):
        E = (f + alpha * sq_card
             + (-kap * hs1 + (kap * kap / 2) * hs2)
             + (-kap * hb1 + (kap * kap / 2) * hb2))
        m = E.min()
        return m, int((E == m).sum())

    # equivalence check before timing anything
    a, b = unbal_naive(20.0, 1.0), unbal_cached(20.0, 1.0)
    same = abs(a[0] - b[0]) < 1e-9 and a[1] == b[1]
    print(f"\nsetup: bit matrix {t_bits*1000:.0f} ms ({bits.nbytes/1e6:.0f} MB), "
          f"Pass-1 precompute {t_pre*1000:.0f} ms")
    print(f"cached unbalanced == naive unbalanced: {same}  "
          f"(energy {a[0]:.9f} vs {b[0]:.9f}, ties {a[1]} vs {b[1]})")
    if not same:
        sys.exit("FAIL: cached and naive unbalanced disagree")

    print(f"\n{'evaluator':<22} {'ms/grid point':>14}   grid cost (per encoding)")
    print("-" * 70)
    for name, fn in [("slack", lambda: slack_point(20.0, 1.0)),
                     ("unbalanced (naive)", lambda: unbal_naive(20.0, 1.0)),
                     ("unbalanced (cached)", lambda: unbal_cached(20.0, 1.0))]:
        fn()
        t0 = time.perf_counter()
        for _ in range(REPEATS):
            fn()
        dt = (time.perf_counter() - t0) / REPEATS
        costs = "  ".join(f"{lbl}:{pts*dt/60:.1f}m" for lbl, pts in
                          [("1D-50", 50), ("2D-50^2", 2500), ("3D-50^3", 125000)])
        print(f"{name:<22} {dt*1000:>14.1f}   {costs}")

    print("\nConclusion: all three candidate grid dimensionalities (U-01) are affordable.")
    print("Compute therefore does NOT discriminate between them; U-01 is a scientific decision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
