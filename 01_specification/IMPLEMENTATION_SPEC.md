# IMPLEMENTATION SPECIFICATION — Gate 0

**Status:** Historical Gate-0 draft, with selected implementation-interface detail retained. The authoritative
Gate-1 mathematical definitions are now `FROZEN_MATH_SPEC.md`, consolidated under W0b through D016.
Where this historical draft differs from that frozen consolidation or an approved decision, the frozen
consolidation / decision controls. No downstream implementation may begin.
**Author:** Claude (primary research engineer)
**Date:** 2026-08-22
**Authority:** Subordinate to the Scope Lock as amended, the approved decisions, and
`research/00_specifications/FROZEN_MATH_SPEC.md`. This file is not an independent source of a current
mathematical choice.

**Evidence labels used throughout:** `[SCOPE §n]` = frozen Scope Lock section; `[PROTOTYPE]` = read from
previous_work; `[DERIVED]` = worked out in this project; `[EXPERIMENTAL]` = computed from project data by
`research/audit/verify_gate0_facts.py`; `[INFERENCE]` = interpretation, not fact; `UNKNOWN` /
`CANNOT VERIFY` used literally.

---

## A. Research Question

The frozen research question, reproduced verbatim from `[SCOPE §25]`:

> Does the relative performance of slack-variable and unbalanced-penalization QUBO encodings remain stable
> across a principled, jointly-swept, dimension-matched penalty landscape, when evaluated against the
> certified exact ground state of the encoded QUBO, under multiple simultaneous heterogeneous constraints
> (cardinality, sector cap, budget) in portfolio optimization — or is the reported superiority of one
> encoding an artifact of the specific, single, separately-tuned penalty values at which prior comparisons
> were made?

### What is actually being tested

The object of study is **the stability of a ranking**, not the ranking itself.

Prior work (Montañez-Barrera et al. 2024; its 2023 D-Wave follow-up; the unpublished portfolio repo)
calibrates each encoding to **one** tuned operating point and reports a winner there `[SCOPE §4.3, §8]`.
This project asks whether that reported winner is a property of the *encodings* or a property of the
*calibration point chosen*. The sweep is therefore **the instrument, not the result** `[SCOPE §22]`.

### What is explicitly NOT being tested

Restating the exclusions so the implementation cannot drift into them `[SCOPE §23, §25]`:

- Not "which encoding is better."
- Not "unbalanced is more robust / superior."
- Not "first comparison of slack vs. unbalanced" — **FALSE**, contradicted by Montañez-Barrera et al.
- Not "first penalty sweep of two encodings" — **FALSE** in general, contradicted by Kikuchi et al. 2024.
- Not "first certified/exact-ground-truth QUBO benchmark" — **FALSE**, contradicted by Stopfer & Wagner 2025.
- Not "first portfolio QUBO" — **FALSE**.
- Not hardware (QAOA/annealing) behaviour; this study is entirely classical exact enumeration.

A single-instance, single-penalty-point winner is classified in the Scope Lock as a **Weak** result and is
"explicitly insufficient" `[SCOPE §21]`. The implementation must not be structured so that such a result is
the natural output.

### Conditionality that must survive into every artifact

Every conclusion is conditional on the chosen dimension-matched, objective-normalized parameterization.
`[SCOPE §14]` states plainly: **"There is no unique canonical mapping between the two encodings' penalty
parameter spaces."** The implementation must therefore record the parameterization alongside every result
file, so that no downstream artifact can present a result as parameterization-independent.

---

## B. Scientific Claims — classified

### B.1 Established prior-art claims (external, not ours to prove)

| Claim | Source | Status |
|---|---|---|
| A direct numeric slack-vs-unbalanced comparison already exists (TSP, bin-packing, knapsack) | Montañez-Barrera et al., *Quantum Sci. Technol.* 9:025022 (arXiv:2211.13914) | Verified from primary text `[SCOPE §4.2, §7]` |
| Two encodings have been compared across a swept penalty coefficient (domain-wall vs. one-hot, knapsack) | Kikuchi, Takahashi & Tanaka, arXiv:2410.11198 | Verified `[SCOPE §4.5, §7]` |
| Exact/certified ground truth exists in portfolio QUBO without an encoding comparison | Stopfer & Wagner 2025 | Verified `[SCOPE §7, §8]` |
| Unbalanced penalization does not guarantee feasible-beats-infeasible energy ordering | Montañez-Barrera et al. 2024, their Fig. 6 | Verified `[SCOPE §11]` |
| ~~Slack encoding *does* guarantee that ordering by construction~~ **WITHDRAWN — see C0-02 below.** Slack guarantees only that feasible states carry *zero marginal inequality penalty*; it does **not** guarantee feasible-beats-infeasible, because the penalty is finite | — | **RETRACTED 2026-08-22** |

### B.2 Project-derived mathematical claims (ours; must be independently checkable)

| ID | Claim | Where derived | Verification owed |
|---|---|---|---|
| M1 | After marginalizing the auxiliary register, slack's effective penalty is the hinge-squared function `0 if h>=0, lambda_S*h^2 if h<0` | `[SCOPE §11, DERIVED]` | Algebraic + numeric oracle (V-2) |
| M2 | Unbalanced penalization is **not** a special case or rearrangement of slack for any parameters (a smooth quadratic cannot reproduce a kink) | `[SCOPE §11, DERIVED]` | Algebraic argument; numeric counterexample search (V-9) |
| M3 | Awai et al.'s ALF retains the slack register and is **not** unbalanced penalization | `[SCOPE §11, DERIVED]` | Literature-level; not re-derived here. Out of implementation scope |
| M4 | For fixed `x`, each slack register is independent and convex; the joint auxiliary minimization decomposes | `[SCOPE §15, DERIVED]` | V-1, V-2 (brute-force oracle) |
| M5 | The energy-minimizing register is `S* = clamp(round(h(x)), 0, 2^N - 1)`, an O(1) computation | `[SCOPE §15, DERIVED]` | V-2 |
| M6 | `S*` does not depend on the penalty coefficients, so exact certification costs O(2^20) **once per x**, not per grid point | `[SCOPE §15, DERIVED]` | V-3 |
| M7 | All three constraint residuals are integer-valued on this instance, so `round()` is exact and `S* = clamp(h,0,2^N-1)` | `[EXPERIMENTAL]`, facts script §4 | Verified; re-verify per Stage-2 instance |
| M8 | `f(x)`, `h_card(x)`, `h_sector,j(x)`, `h_budget(x)` can be precomputed once over all 2^20 `x`; each grid point is then a weighted sum + argmin | `[DERIVED]`, this document §F.4 | V-3, V-11 |

**M7 and M8 are new in this document** and are not in the Scope Lock. M8 in particular is what makes a
multi-axis grid computationally viable (see §F.4) and should be attacked first by the auditor.

### B.3 Hypotheses (pre-registered, not yet tested)

Reproduced from `[SCOPE §20]`, unmodified:

- **H0 (null, rank stability):** recovery rates approximately equal and the A/B/C ranking never flips across the grid.
- **H1 (rank instability):** sub-regions exist where slack wins and other sub-regions where unbalanced wins.
- **H2 (infeasibility asymmetry):** Category C occurs measurably more often for unbalanced than slack.
- **H3 (constraint heterogeneity):** robustness-region *shape* depends on which constraint types are active.

Falsification conditions for each are stated in `[SCOPE §20]` and must be copied into the analysis code as
literal pre-registered predicates, evaluated mechanically, not judged by eye.

### B.4 Experimentally testable claims in this project

1. `rho_E^exact` for each encoding at each grid point.
2. Whether the sign of `rho_slack^exact - rho_unbalanced^exact` changes anywhere in the sampled grid (H1).
3. C-rate gap between encodings (H2).
4. Robustness-region geometry and connectedness under constraint ablation (H3).
5. Whether conclusions survive the 0.5x/2x domain expansion and the D011 curvature-match alternate anchor `[SCOPE §14, §18]`.

### B.5 Unresolved questions (not claims — see UNRESOLVED_DECISIONS.md)

U-01 grid dimensionality **[CLOSED, D002]**; U-02 `kappa_risk` **[CLOSED, D007]**; U-03 `Lambda_ref` definition **[CLOSED, D008]**;
U-04 `s`-domain bounds **[CLOSED, D010 — RULE ONLY, numbers are a G3 ADNYE record]**;
U-05 grid resolution **[CLOSED, D012 — `P=10` base-10 log intervals per decade on all axes, endpoints included]**;
U-06 slack register domain **[CLOSED, 39 variables]**;
U-07 canonical data assembly (prototype ordering defect); U-08 to U-11 Stage-2 protocol;
U-12 constraint ablation subset **[CLOSED, D013 — conditional four-condition exact-sign rule]**;
U-13 `alpha` treatment **[CLOSED, D009 — map was already approved under D002; D009 propagated it and set certification policy]**;
U-14 tie-detection numerical comparators **[CLOSED, D015 — canonical binary64 `T_E` ledger and separate
encoding-blind `OPT_f` service]**; U-17 mixed tie-set semantics **[CLOSED, D016 — decoded `A_x/B_x/C_x`
labels, primary partition, and required reporting]**.

---

## C. Mathematical Specification

### C.1 Decision variables

```
x in {0,1}^20                     one bit per asset            [SCOPE §12]
y_sector,j in {0,1}^2   j = 1..4  slack register per sector    [SCOPE §13]
y_budget   in {0,1}^N_b           slack register for budget    N_b UNRESOLVED (U-06)
```

Unbalanced encoding uses `x` alone — zero auxiliary variables `[SCOPE §13]`.

### C.2 Objective (original problem)

```
f(x) = -mu^T x + kappa_risk * x^T Sigma x        (minimize)    [SCOPE §12]
```

`mu` in R^20, `Sigma` in R^{20x20} symmetric PSD, `kappa_risk` a scalar.

**`kappa_risk` is APPROVED (D007, 2026-08-23) as an indivisible `(value, unit, period)` TRIPLE:**

```
kappa_risk = ( 1.0 , (decimal simple daily return)^-1 , daily )
```

`mu` is the mean **daily simple decimal** return vector; `Sigma` the **daily** covariance of those
returns. **No annualization or other horizon conversion** absent a separately approved aggregation
model. **`[kappa_risk] = E^-1` — it is NOT dimensionless** (`[mu] = E`, `[Sigma] = E^2` under the
declared algebra; do NOT write this as `R^-1` — `R` is the RESIDUAL unit here). The numeral alone does not name a
model: `R' = c*R` gives `mu' = c*mu`, `Sigma' = c^2*Sigma`, hence `kappa_risk' = kappa_risk / c`. So
decimal `1.0` and percentage `0.01` are the SAME model, while percentage `1.0` is a DIFFERENT one,
100x more risk-averse. **Implementers must carry the unit and period, never the bare scalar.**
`kappa_risk` is constant across every grid point, both encodings, all ablations and all instances, and
must appear in **no** coefficient map as a function of `s`. Exact scope: `DECISIONS.md` D007.

*(Historical: the Scope Lock treated it as a fixed scalar but never fixed it, and the prototype swept it
as `lambda in {0.1, 0.3, 0.5, 0.75, 1.0, 2.0}` `[PROTOTYPE cell 14]`. That is why D007 was required; the
prototype's swept set is not the source of the approved value.)*

Renaming note `[SCOPE §12]`: the Scope Lock document itself overloads the symbol `kappa` for both risk
aversion and the unbalanced decay rate. This project uses `kappa_risk` and `kappa_penalty` throughout and
must never emit a bare `kappa` in code or results.

### C.3 Constraints

```
cardinality (equality) : sum_i x_i = K,                K = 6      [SCOPE §12]
sector caps (4 ineq.)  : n_j(x) = sum_{i in S_j} x_i <= C, C = 2
budget      (1 ineq.)  : p^T x <= B,                   B = 1100
F = { x : all three families hold }
```

Signed residuals, sign convention `h >= 0 <=> feasible` `[SCOPE §11]`:

```
h_card(x)     = sum_i x_i - K            (equality: target 0, NOT a one-sided residual)
h_sector,j(x) = C - n_j(x)
h_budget(x)   = B - p^T x
```

`[EXPERIMENTAL]` Constraint geometry on the Stage-1 instance, from the facts script:

| Quantity | Value |
|---|---|
| cardinality-feasible portfolios `C(20,6)` | 38,760 |
| cardinality + sector feasible | 19,000 |
| **fully feasible `|F|`** | **976** |
| cost range over cardinality-feasible | [600, 4000] |

`|F| = 976` confirms the feasible region is non-empty and a strict, small subset (2.5% of the
cardinality-feasible set) — tight enough for the budget and sector constraints to genuinely bind, which is
a precondition for the experiment being informative at all.

### C.4 Slack encoding

Cardinality uses an ordinary quadratic penalty in **both** encodings; no auxiliary variables are ever used
for the equality constraint `[SCOPE §13]`:

```
P_card(x) = alpha * (sum_i x_i - K)^2
```

Per inequality with residual `h(x)` and register `S = sum_d 2^d y_d`:

```
P_slack(x,y) = lambda_S * (h(x) - S)^2                          [SCOPE §13]
```

Register widths `[SCOPE §13]` / `[EXPERIMENTAL]`:

| Constraint | max h over `{0,1}^20` | bits | note |
|---|---|---|---|
| sector (each of 4) | `C = 2` | 2 | 8 bits total; Scope Lock and computation agree |
| budget | 1100 (at `x = 0`) | 11 | **only if the register must cover all `x`** |
| budget | 500 (at `|x| = K`) | 9 | if the register need only cover cardinality-feasible `x` |

**RESOLVED (C0-06): the 39-variable construction is fixed by the Scope Lock, not an open choice.**
The QUBO's domain is all of `{0,1}^20` because cardinality is enforced *softly*; the budget register must
therefore represent `h = 1100` at `x = 0`, requiring 11 bits. Codex independently derived the same result.
The 37-variable variant is a *different, deliberately narrow-domain formulation*, not an equally valid
reading — so it is **not** a blocking decision and must **not** be presented as a comparable headline
variable count. Retained below only as a footnote. Original framing: The Scope Lock asserts 19 auxiliary bits and 39 total QUBO
variables `[SCOPE §13, §15, §25]`, which corresponds to the *all-`x`* reading. The alternative reading gives
17 auxiliary bits and 37 variables. The number is not cosmetic: variable count is a **reported secondary
metric** `[SCOPE §17]` ("20 for unbalanced vs. 39 for slack"), so the headline qubit-overhead comparison
changes with this choice. It may also change the ground state at small `alpha`, where `|x| != K` states are
not strongly suppressed. Do not resolve by picking the smaller number because it is tighter.

### C.5 Unbalanced encoding

> **RESOLVED 2026-08-23 — implement the APPROVED mapping in C.5a below, NOT the frozen `[SCOPE §14]`
> formula.** D004 (parent family), D005 (`v_ref`) and D006 (reduction + outer scale) together fully
> determine the unbalanced mapping. The defect record that follows is retained as the reason the frozen
> text must not be implemented.

> **CRITICAL DEFECT IN THE FROZEN `[SCOPE §14]` TEXT — DO NOT IMPLEMENT AS WRITTEN. See U-16.**
> The mapping below is inherited verbatim from `[SCOPE §14]` and is **dimensionally inconsistent**.
> Independently confirmed by `research/audit/verify_codex_findings.py` (finding C0-01).
>
> With `[f] = E` and `[h] = R`: `Lambda_ref` has units `E`, `v_ref` has units `R`, so
> `kappa = s*Lambda_ref/v_ref` has units `E/R`. Then `lambda_1*h` has units `E` (correct) but
> `lambda_2*h^2 = (kappa^2/2)*h^2` has units **`E^2`**, not `E`.
>
> **Consequence (demonstrated, not asserted):** rescaling the objective `f -> c*f` — a pure change of
> units with no scientific content — scales the slack penalty linearly (landscape invariant) but the
> unbalanced quadratic term *quadratically*. In the verified counterexample the unbalanced decoded
> ground state **flips** between `c = 2` and `c = 6` while slack's never moves. Any A/B/C comparison
> built on this mapping is therefore partly an artifact of the units `f` is expressed in, and the
> mapping is **not** "objective-normalized" as `[SCOPE §14]` claims.
>
> `[SCOPE §14]` is also internally contradictory: it states the reward minimum has "constant depth
> `-1/2` regardless of `kappa`" — a *dimensionless* depth, requiring `[kappa] = 1/R` — while
> simultaneously defining `kappa(s) = s*Lambda_ref/v_ref`, giving `[kappa] = E/R`. Both cannot hold.
>
> This was a **scientific decision, not a code repair** `[handoff §2]`. It was escalated as U-16 and
> **approved 2026-08-22/23** as D004 + D006. The formula is retained below only to record what the frozen
> document says. **It is superseded. Do not implement it.**

```
zeta(x) = -lambda_1 * h(x) + lambda_2 * h(x)^2                  [SCOPE §13, §14]
lambda_1 = kappa_penalty,  lambda_2 = kappa_penalty^2 / 2        (Taylor family, AS FROZEN — DEFECTIVE)
```

Applied to the two inequality families only. Cardinality uses the same `P_card` as slack `[SCOPE §13]`.
No auxiliary variables; total variable count 20.

### C.5a Unbalanced encoding — **APPROVED MAPPING (D004 + D005 + D006). IMPLEMENT THIS.**

For each **inequality** constraint family `j` (sector and budget **only**):

```
zeta_j(h)   = Lambda_ref * [ -a(s_j)*(h/v_j) + ( a(s_j)*h/v_j )^2 / 2 ]

a(s)        = sqrt(1 + 2*s) - 1                       [dimensionless]   D006(a), R2 at r = 1
lambda_1,j  = Lambda_ref * a(s_j)   / v_j             [E / R]
lambda_2,j  = Lambda_ref * a(s_j)^2 / (2 * v_j^2)     [E / R^2]
Lambda_pen,j = Lambda_ref                             i.e. c_j = 1      D006(b)
```

Derived properties (verified, `verify_d006.py` §4): `lambda_2 = lambda_1^2 / (2*Lambda_ref)`;
reward minimum at `h* = v_j / a` `[R]`; depth `-Lambda_ref/2` `[E]`.

**Dimensions are now consistent:** `lambda_1*h` has units `E` and `lambda_2*h^2` has units `E`.
The `[SCOPE §14]` contradiction (dimensionless depth vs `[kappa] = E/R`) is resolved — the depth is
`-Lambda_ref/2`, an **energy**, not a dimensionless `-1/2`.

**Cardinality is EXCLUDED from this section.** It is the shared **equality** penalty `P_card` / `alpha`
(U-13), identical to slack's. It has **no `a`, no `r`, and no `v_ref` normalization** under D006.
No auxiliary variables; total variable count 20.

> **MANDATORY 1 — `a(s)` MUST NOT be evaluated as written.** `[Codex P2]` `sqrt(1 + 2s) - 1` above is
> the mathematical **definition**. Evaluated directly it **cancels catastrophically** as `s -> 0`:
> relative error `~1.3e-4` at `s = 1e-12`, and at `s = 1e-16` double precision returns **exactly `0.0`**
> (`verify_d006.py` §1b). **SUPERSEDED RATIONALE, 2026-08-24 (D010):** U-04 now fixes
> `s_min = 10^(floor(log10 rho_box) - 4)` with `rho_box >= 1`, hence **`s_min >= 1e-4`** — about eight decades
> clear of the failure regime (measured relative error of the naive form is `9.6e-13` at `1e-4`, degrading
> to `1.3e-4` only at `1e-12`). **THE MANDATE BELOW IS NOT RELAXED AND MUST NOT BE:** `m_lo` is a recorded
> judgement call that could be revised, and the rationalized form is exact at no cost, so there is never a
> reason to prefer the subtractive one. The original rationale read: **U-04 has not fixed a positive lower
> bound on the `s` box**, so nothing
> currently excludes that regime. Implement the algebraically identical rationalized form:
>
> ```
> a(s)   = 2*s / ( sqrt(1 + 2*s) + 1 )                MANDATED
> a_r(s) = 2*s / ( sqrt(r^2 + 2*s) + r )              MANDATED, sensitivity r
> ```

> **MANDATORY 2 — implement the gap using the CLOSED form.** With `c = 1` the infeasible-side gap
> against slack is exactly
>
> ```
> D(w) = a(s) * w * (1 - w),        w = |h| / v_j
> ```
>
> because the R2 identity `a + a^2/2 = s` makes `a^2/2 - s` equal to **exactly** `-a`.
> **Do not evaluate `D` as `a*w + (a^2/2 - s)*w^2`.** With the mandated `a` the two forms differ by
> `~5.9 * DBL_EPSILON` relative (6 ulps) on the probe grid; with the naive `a` by `46.1 * DBL_EPSILON`
> (88 ulps). `N * DBL_EPSILON` relative error and `N` ulps are **different measures** — do not conflate
> them, and treat both figures as **probe-grid observations, not bounds**.

> **MANDATORY CONDITIONING ON EVERY UNBALANCED RESULT.** `D < 0` for **every** `w > 1` at **every**
> `s > 0`, so unbalanced is **under-penalized relative to slack** at **2 of 3** reachable sector points
> and **1067 of 1068** reachable budget points *(counts conditional on the pre-canonical price vector,
> pending U-07/G2)*. **Stated precisely** `[Codex U16-01, P4]`: this is a **LOCAL PENALTY-GAP**
> statement. It is **hypothesis-ALIGNED with H2 and CONFOUNDS the comparison**, but it does **NOT**
> establish, predict or bound any A/B/C outcome or Category-C rate — ground states depend on the whole
> spectrum, not on local gaps. R2 matches at `w = 1` **only** and asserts **no** neutrality; any
> unbalanced-vs-slack difference at `w > 1` is confounded with this accepted gap and may not be
> attributed to the encoding without separating the two. See `DECISIONS.md` D006.

**Sensitivity calibrations (secondary, pre-registered):** `r in {0.5, 2}` with
`a_r(s) = -r + sqrt(r^2 + 2*s)`, which matches slack at `w0 = 1/r`. These are **sensitivity analyses
only** and **must not** be selected or substituted for the primary `r = 1` mapping after results are
observed.

**D011 curvature-match companion (required, non-primary):** this is distinct from D006's `r` sensitivities.
For each inequality family only, use

```
lambda_S,j^CM = s_j * Lambda_ref / v_j^2
lambda_1,j^CM = s_j * Lambda_ref / v_j
lambda_2,j^CM = s_j * Lambda_ref / v_j^2
```

Equivalently `a^CM = 2` and `Lambda_pen,j^CM = s_j*Lambda_ref/2`; therefore
`lambda_2,j^CM = lambda_S,j^CM`. At `h=-w*v_j`, its local gap against slack is exactly
`D_CM(w) = s_j*w > 0`. This known directional bias is mandatory conditioning, never an A/B/C prediction.
Run it only as the Scope-mandated **coarse** companion subgrid; its exact predeclared extent is still
required before execution. It never replaces D006 primary R2 or either `r in {0.5,2}` sensitivity.

> **SUPERSEDED / DO NOT IMPLEMENT.** The Scope-Lock `kappa` completed-square derivation belongs only to the
> defective mapping retained in §C.5. Its dimensionless depth `-1/2` is incompatible with the approved
> objective-unit mapping. For D006 (primary `r = 1` and sensitivity `r in {0.5, 2}`), the correct identity is
>
> ```
> zeta_{j,r}(h) = (Lambda_ref / 2) * (a_r(s_j)*h/v_j - 1)^2 - Lambda_ref / 2
> ```
>
> so the reward minimum is `h* = v_j/a_r(s_j)` and its depth is `-Lambda_ref/2` `[E]`. The contrast with
> slack remains relevant, but only under this approved, dimensionally homogeneous form.

### C.6 Penalty parameterization (frozen family, unfrozen numbers)

> **SUPERSEDED IN PART, 2026-08-23.** `v_ref = 1` is **replaced by D005** and `kappa(s)` is **replaced
> by D006** (see C.5a). The frozen block is retained to record what `[SCOPE §14]` says.

```
v_ref       = 1                  smallest nonzero integer violation      [SCOPE §14] SUPERSEDED BY D005
Lambda_ref  = range (or std) of f(x) over the feasible set               [SCOPE §14] SUPERSEDED BY D008
lambda_S(s) = s * Lambda_ref / v_ref^2
kappa(s)    = s * Lambda_ref / v_ref                                     SUPERSEDED BY D006 — DEFECTIVE
```

**APPROVED replacement (D005 + D006 + D008 + D009 + D010):**

```
v_ref,j     = smallest ATTAINABLE positive NATIVE violation of family j over x in {0,1}^20   D005
              -> expected (1, 1, 5) for cardinality, sector, budget on canonical Stage-1 data.
              PENDING STATUS IS NOT UNIFORM  [D009(c)]:
                v_card   = 1  EXACT       - integrality of sum_i x_i with K=6; no data dependency
                v_sector = 1  EXACT       - counts are integers, C=2, and 20 assets across 4 sectors
                                            forces some sector to hold ceil(20/4)=5 >= C+1=3
                                            (pigeonhole).  F-1 permutes membership, not the counts.
                v_budget = 5  PRE-CANONICAL - synthetic price vector (PROTOTYPE_AUDIT F-4);
                                            genuinely PENDING U-07/G2.  ONLY this one can move.
              NOT gcd-defined: gcd is only a lower bound (counterexamples in D005).
Lambda_ref  = max_{x in F} f(x) - min_{x in F} f(x)                      D008 - RANGE over F
              F = { x in {0,1}^20 : sum_i x_i = K, n_j(x) <= C all j, p^T x <= B }  (PREDICATE,
              never the pre-canonical count 976).  Units E.  RULE ONLY - the NUMBER is a
              prospective ADNYE record executed at G3.compute_Lambda_ref.
              Lambda_ref == 0  ->  G3 STOP CONDITION, never patched at runtime.
alpha(s_card) = s_card * Lambda_ref / v_card^2                           CARDINALITY, BOTH ENCODINGS
              Source: D002 via SCOPE_AMENDMENT_001.md SS3 (approved 2026-08-22).
              Propagated here by D009(a) as a non-substantive repair -- this block
              previously omitted it while SSC.4 defined only the FORM P_card = alpha*h_card^2.
              Units [alpha] = E/R^2, so [alpha*h_card^2] = E.
              WRITE v_card^2 EXPLICITLY even though it evaluates to 1: with it elided the
              expression is homogeneous only by numerical coincidence and M1/M2 pass by accident.
              alpha has NO a(s), NO r, and NO reduction rule.  D006's exclusion of cardinality
              concerns the UNBALANCED coefficient pair only and does NOT remove v_card [D009(d)].
lambda_S,j(s) = s * Lambda_ref / v_j^2                                   slack, unchanged in form
a(s)          = sqrt(1 + 2*s) - 1                                        D006(a) — replaces kappa(s)
lambda_1,j(s) = Lambda_ref * a(s)   / v_j
lambda_2,j(s) = Lambda_ref * a(s)^2 / (2 * v_j^2)

s-DOMAIN BOX  [D010, RULE ONLY -- the NUMBERS are a G3 ADNYE record]
Delta_full  = max_{x in {0,1}^20} f(x) - min_{x in {0,1}^20} f(x)        [E]
              EXPRESSLY AUTHORIZED by D010 as the box rule's SECOND input.  D008 admits this
              quantity for TRANSPARENCY REPORTING ONLY; that is not authority to make it a
              load-bearing input.  It is NOT a normalizer -- Lambda_ref remains the normalizer.
rho_box     = Delta_full / Lambda_ref                                    [dimensionless, >= 1]
s_max       = 10 ^ ( ceil(log10(rho_box))  + m_hi ),   m_hi = 1   DERIVED
s_min       = 10 ^ ( floor(log10(rho_box)) - m_lo ),   m_lo = 4   JUDGEMENT CALL, recorded as one
              COMMON CUBE on all three axes.  Executed at G3.exit.resolve_box, after Lambda_ref
              and before G4.start.  TWO named inputs: Lambda_ref AND Delta_full.
```

`s` — not `lambda_S`, `kappa_penalty`, `alpha`, or `a` — remains the swept quantity, log-spaced
`[SCOPE §14]`, now on the three D002 axes `(s_card, s_sector, s_budget)`, over the D010 box.

> **`m_hi = 1` is DERIVED; `m_lo = 4` is a JUDGEMENT CALL.** They are not equally grounded and must not be
> reported as if they were. `m_hi` covers the worst pre-registered mapping (`r = 2`), whose bracketing
> condition solves as `s_2(rho_box) = (rho_box-1) + sqrt(2*rho_box+1)` with
> `sup_{rho_box>=1} s_2(rho_box)/rho_box = sqrt(3)`.
> **`s_max` is a DESIGN TARGET, not a certification** — it is a single-family, `w = 1`, in-isolation
> statement and does not prove enforcement (C0-05 stands). **Per D009(b) no enforcement threshold is
> claimed**, so V-17 obligation 2 is untriggered — untriggered, **not** retired.
>
> **Grid RESOLUTION is CLOSED by D012.** The primary three-axis grid uses `P=10` base-10 log intervals per
> decade, endpoints included. D010 fixes its later extent only. Any write-up must report `m_hi`, `m_lo`,
> the decade span, and the fixed density alongside `rho_E^exact`, which is conditional on the box.

> **CORRECTION (C0-04). The earlier justification of `v_ref = 1` in this document was an OVERCLAIM and
> is withdrawn.**
>
> `[EXPERIMENTAL]` Integrality gives `h in Z`, but it does **not** give an attainable unit violation.
> `gcd(prices) = 5` and `B = 1100` is divisible by 5, so `h_budget = B - p'x` lies in **`5Z`**: a budget
> violation of 1 is *unreachable*, and the smallest attainable budget violation is **5** (verified,
> facts script §5). Sector and cardinality residuals step by 1, so `v_ref = 1` is attainable *there*.
>
> Applying one common `v_ref = 1` across all three constraints is therefore a **modelling choice**, not a
> consequence of integrality — and it silently normalizes the budget constraint on a scale 5x finer than
> its own attainable lattice. Escalated as **U-15** and **CLOSED by D005 (2026-08-23)**, which adopts the
> per-constraint attainable scale. The common `v_ref = 1` is **rejected**.

Integrality *does* still establish the separate, narrower claim that the closed-form register minimizer is
exact with no rounding ties (M7).

`Lambda_ref`'s **definition** is **CLOSED by D008** (range over predicate-defined `F`, units `E`) — but
its **numeric value is not fixed** and is a prospective ADNYE record executed at `G3.compute_Lambda_ref`.
The `s`-domain bounds (U-04) are **CLOSED by D010** as a **RULE** — common cube,
`s_max = 10^(ceil(log10 rho_box)+1)`, `s_min = 10^(floor(log10 rho_box)-4)`,
`rho_box = Delta_full/Lambda_ref` — whose
**numeric** output is the second prospective ADNYE record, executed at `G3.exit.resolve_box`.
**U-05 grid resolution is CLOSED by D012.** `[SCOPE §14, §25]`'s earlier NOT-YET-FIXED marking is
superseded for density: `P=10` base-10 log intervals per decade, endpoints included. U-04's numeric
bounds remain prospective ADNYE outputs, not frozen numbers.

### C.7 The two distinct exact objects

These must never be conflated; the Codex brief flags conflation as a critical issue `[codex_messages §5]`.

```
X*        = argmin_{x in F} f(x)                  original-problem optimum SET (may contain ties)
f*        = min_{x in F} f(x)                     the optimal objective VALUE
z*_E(s)   = argmin_z Q_E(z; s)                    encoded-QUBO ground state, one PER ENCODING PER GRID POINT
```

> **CORRECTION (C0-03).** An earlier draft called `x*` "ONE per instance". Original-objective ties are
> possible, so the ground truth is stored as the **set** `X*` (or equivalently `f*` plus a feasibility
> predicate), never as one arbitrarily chosen representative. `classify.py` must not consume a single
> `x*`.

The scientific question is whether decoding `z*_E(s)` recovers a member of `X*` — **checked, never
assumed**, at every grid point and every encoding independently `[SCOPE §12]`. The implementation enforces this by computing the
two objects in separate modules with no shared code path (see §F.2).

### C.8 A/B/C classification

For each distinct decoded portfolio `x in X_E`, D016 defines the atomic labels:

```
A_x  : D015 OPT_f(x) through the encoding-blind original-objective service
B_x  : feasible(x) AND NOT A_x
C_x  : NOT feasible(x)
```

`OPT_f`, not bare exact equality, is the frozen numerical meaning of feasible-optimal. The classifier
receives only decoded `x`, `f*`, and the original feasibility predicate; it receives no encoded energy or
encoding identity.

`[SCOPE §16]` **B and C must never be merged.** Collapsing them into an objective gap would hide the
distinction between "wrong answer, still a portfolio" (B) and "not a portfolio at all" (C), which have
different causes and different practical implications. Every downstream metric, table, and plot keeps them
separate.

> [RETRACTED:C0-02] "only unbalanced can produce Category C by construction"
> **CORRECTION (C0-02):** `[SCOPE §16]` asserts this and `[SCOPE §11]` says slack "does not need this extra check
> (guaranteed by construction)". Both are **false across the swept landscape**, and implementing them
> would produce wrong C-rates.
>
> Slack's marginalized penalty for an infeasible state is `lambda_S * h^2` — **finite**. An infeasible
> state whose objective is better by more than that penalty is the ground state. Verified counterexample
> (`verify_codex_findings.py`, C0-02): with `f_feas = 0`, `f_infeas = -100`, `h = -1`, slack's ground
> state is **infeasible for every `lambda_S < 100`**. The finite cardinality penalty `alpha` creates the
> same exposure in *both* encodings.
>
> The claim is true only asymptotically (large `lambda_S`) — but the sweep deliberately includes the
> "comfortably non-enforcing" regime `[SCOPE §14]`, which is exactly where it fails.
>
> **Required:** decoded feasibility is checked for **both** encodings at **every** grid point. H2 remains
> a legitimate *empirical directional* hypothesis; it may **not** be justified by asserting that slack's
> C-rate is structurally zero.

### C.9 Tie handling

`[SCOPE §16]`

- U-14 selects the raw encoded tie set `T_E`. Decode and deduplicate it to the distinct portfolio set
  `X_E = {decode(z) : z in T_E}` before any classification or fraction is computed.
- Auxiliary-register degeneracy is not decision-equivalent to a distinct portfolio tie: report both `|T_E|`
  and `|X_E|` rather than silently discarding either.
- **Frozen strict rule:** a grid point is classified `A` only if **every distinct decoded portfolio** in
  `X_E` is feasible-optimal — not merely at least one.
- Tie fractions are reported over `|X_E|`, never as partial credit toward A.

**D016 U-17 mixed-tie rule:** assign atomic labels over `X_E` as in §C.8 and classify each nonempty finite
decoded tie set as `C` if any `C_x` exists, otherwise `A` if all members are `A_x`, otherwise `B`. This
preserves Scope §16's universal-A condition. Store `|T_E|`, `|X_E|`, atomic-label set, and primary label;
report the mixed-label census, `I_C^exist`, `I_C^univ`, and `p_A`, `p_B`, `p_C` over denominator `|X_E|`.
Fractional diagnostics are never partial credit toward A. D015's four one-factor configurations repeat this
reporting as non-primary diagnostics only; D013 consumes primary classification only. Full normative detail:
`DECISIONS.md` D016.

**D015 U-14 comparator rule:** form `T_E` from the approved canonical unshifted binary64 encoded-energy
ledger over the certified raw domain before decoding; form `OPT_f` only through the separate encoding-blind
original-objective service. Both use D015's exact scale-aware tolerance formula, primary
`(c_H,c_f)=(2048,2048)`, finite-only failure rule, provenance requirements, oracle disposition, and fixed
one-factor diagnostics. The encoded-energy comparator never decides original optimality, and the
original-objective service receives neither encoded energy nor an encoding identity. Full normative detail:
`DECISIONS.md` D015.

### C.10 Metrics

**Primary** `[SCOPE §17]`: `rho_E^exact = |{grid points classified A}| / |Lambda|`.

**Secondary** `[SCOPE §17, D016]`: feasibility rate `1 - I_C^exist`; B-alone and C-alone primary-label
rates; universal/existential/fractional-C diagnostics; full atomic fractions; raw/decoded tie multiplicity;
mixed-composition census; robustness-region geometry (shape, explicitly not just a scalar fraction);
connectedness; variable/qubit overhead; and D015 one-factor sensitivity diagnostics.

---

## D. Data Specification

### D.1 Inventory

| Input | Source | Dims | Available? | Validation required |
|---|---|---|---|---|
| `mu` | `previous_work/.../datasets/mu.csv` | 20 | **YES** | ticker-keyed join; finite; no NaN |
| `Sigma` | `previous_work/.../datasets/Sigma.csv` | 20x20 | **YES** | symmetry; PSD; diag > 0; index == columns == mu index |
| `p` (prices) | **notebook cell 17, inline literal** | 20 | **YES, but not a data file** | integer; positive; provenance recorded |
| sector map | notebook cell 12, positional | 4 x 5 | **YES** | partition of 0..19; 5 per sector |
| `K, C, B, alpha` | notebook cells 14/16/17 | scalars | **YES** | 6, 2, 1100, 20 |
| `kappa_risk` | **`DECISIONS.md` D007** (decision, not a data file) | scalar | **YES** | triple `(1.0, (decimal simple daily return)^-1, daily)`; carry unit+period, never the bare scalar |
| `Lambda_ref` | **rule fixed by D008** — range of `f` over predicate-defined `F` | scalar, units `E` | **rule YES**; numeric value computable at **G3** once canonical data exists | ADNYE record at `G3.compute_Lambda_ref`; `Lambda_ref == 0` is a G3 stop condition |
| Stage-2 instances | — | — | **NO** | protocol unfrozen (U-08..U-11) |

`[EXPERIMENTAL]` Verified: `mu.csv` has 20 rows; `Sigma.csv` is 20x20; `Sigma` index == columns == `mu`
index; no missing values.

### D.2 Provenance hazards — must be handled explicitly

**HAZARD 1 — prices are not in a data file.** The price vector lives as an inline literal in notebook
cell 17 `[PROTOTYPE]`, contradicting the prototype README's claim that "Stock prices extracted and frozen
for reproducibility" (there is no price CSV). It must be extracted into a versioned data file as part of
G2, with the notebook cell recorded as its provenance.

**HAZARD 2 — a second, decoy price vector exists.** Notebook cell 32 defines `prices_stress =
[500, 600, 700, 150, 120, 100]` for a 6-asset budget stress test, with a different budget (1200) and
different `K` (3) `[PROTOTYPE]`. It is explicitly annotated in the notebook as test-only. Any extraction
script must select cell 17, never cell 32, and must assert length 20.

**HAZARD 3 — the ordering defect.** See §E.2. This is the most serious item in this document.

### D.3 Canonical data assembly (proposed, requires approval)

To make HAZARD 3 impossible to reproduce, the loader must:

1. Read `mu` and `Sigma` **keyed by ticker**, never positionally.
2. Define the canonical universe order **once**, explicitly, as a named constant.
3. Reindex `mu` and `Sigma` onto that order by ticker label, and **assert** the reindex succeeded
   (`set(index) == set(canonical)` and post-reindex `index == canonical`).
4. Attach `p` and the sector map to the same canonical order.
5. Assert `Sigma` symmetry and PSD after reindexing (a permutation preserves both, so failure indicates a
   join bug).
6. Emit a single frozen, hash-stamped instance artifact; every downstream stage reads only that artifact.

Which order becomes canonical is **UNRESOLVED (U-07)**.

---

## E. Existing Prototype Audit

Full detail in `research/audit/PROTOTYPE_AUDIT.md`. Summary:

### E.1 What it implements

A **soft-penalty QUBO-inspired** model `[PROTOTYPE README, cells 19-22]`:

```
E(x) = -mu^T x + lambda x^T Sigma x + alpha(|x|_1 - K)^2
       + beta * sum_j max(0, n_j - C)^2 + gamma * max(0, p^T x - B)^2
```

solved by exhaustive enumeration over `C(20,6) = 38,760` cardinality-restricted portfolios `[PROTOTYPE cell 25]`.

### E.2 CRITICAL — asset ordering defect

`[EXPERIMENTAL]` `mu.csv` and `Sigma.csv` are indexed **alphabetically**
(`AAPL, ABBV, AMZN, BAC, CAT, ...`). The prototype's `stocks` list, `sector_map`, and `prices` array are all
**sector-grouped** (`AAPL, MSFT, NVDA, GOOGL, AMZN, JPM, ...`) `[PROTOTYPE cell 12, 17]`. The code converts
`mu` and `Sigma` to positional arrays via `np.array(mu)` `[PROTOTYPE cell 19]` and indexes sectors
positionally, and **no reindex, `.loc[stocks]`, or `.reindex()` appears anywhere in the notebook**
(verified by exhaustive search of all code cells).

**Consequence:** at 18 of 20 positions the return/covariance values are attached to the wrong ticker, and
therefore to the wrong sector and the wrong price. Only positions 0 (AAPL) and 8 (GS) coincide by accident.

**Severity:** CRITICAL for data provenance; **NOT** fatal to the mathematical structure. The prototype still
minimized a well-defined objective over a well-defined constraint set — just one whose labels do not
correspond to the real assets. Its numeric V2/V3 portfolio outputs and its "~95-98% of unconstrained return"
claim are **not trustworthy as financial statements** and must not be quoted.

**Implication for this project:** because the research question is about *encodings*, not about real
finance, a label-scrambled instance would still be a mathematically valid test instance. But it must be
chosen **deliberately and documented**, never inherited by accident. See U-07.

### E.3 Other findings

- `[PROTOTYPE]` The prototype implements **neither** encoding under study. Its sector and budget terms are
  ordinary hinge-squared soft penalties — not slack-variable encoding (no auxiliary registers anywhere) and
  not unbalanced penalization (no linear reward term). The technical report lists "explicit QUBO compilation
  with slack bits" as deferred future work. This corroborates `[SCOPE §3]`.
- `[PROTOTYPE cell 25]` Enumeration is restricted to `|x| = K` and yet the cardinality penalty
  `alpha(|x|-K)^2` is still applied — it is identically zero over the enumerated set. Harmless in the
  prototype; **must not be inherited**, since this project's QUBO ground state is over all `2^20` states
  where that term is load-bearing.
- `[PROTOTYPE cell 32]` The budget stress test overwrites every `mu` value it uses, so the ordering defect
  does not corrupt that specific test's *mechanics* — but `Sigma_stress` is still mis-joined.
- `[PROTOTYPE]` The `git/` directory is empty (0 bytes); no VCS history is available for the prototype.
  Provenance beyond the files themselves is **UNKNOWN**.

### E.4 Reuse verdict

| Component | Verdict |
|---|---|
| `mu.csv`, `Sigma.csv` numeric contents | **REUSE** — verified well-formed; join by ticker, never positionally |
| price vector, sector map, `K/C/B` | **REUSE AS PARAMETERS** — extract to versioned file, record cell provenance |
| `energy()`, `sector_penalty()`, `budget_penalty()` | **DO NOT REUSE** — hinge-squared soft penalty, neither encoding under study |
| enumeration loop | **DO NOT REUSE** — restricted to `|x| = K`; this project needs all `2^20` |
| Markowitz baseline, plots, V1/V2/V3 sweeps | **OUT OF SCOPE** |
| numeric results / README claims | **DO NOT TRUST** — invalidated as financial statements by §E.2 |

Per the handoff instruction, the prototype is **not** rewritten for cleanliness; it is left intact as
historical evidence and this project builds independently alongside it.

---

## F. Implementation Architecture

Minimal, modular, correctness-first. No optimization before correctness `[handoff §6]`.

### F.1 Module layout

```
src/
  data/
    load.py           ticker-keyed load, canonical reindex, assertions -> frozen instance artifact
    extract_prices.py one-off: notebook cell 17 -> versioned prices file (asserts len 20, integer)
  problem/
    instance.py       immutable Instance: mu, Sigma, p, sectors, K, C, B, kappa_risk + content hash
    objective.py      f(x) ONLY. No penalties. No encoding awareness.
    constraints.py    h_card, h_sector, h_budget. Residuals ONLY. Shared by both encodings.
  groundtruth/
    enumerate.py      x* over F by exhaustive enumeration. Independent of any encoding.
  encodings/
    slack.py          register widths, S*(h), slack energy
    unbalanced.py     zeta(h); Taylor map lambda_1, lambda_2 <- kappa_penalty
    parameterization.py  s -> (lambda_S, kappa_penalty); Lambda_ref; v_ref
  certify/
    groundstate.py    O(2^20) exact encoded-QUBO ground state + tie set
  experiment/
    grid.py           log-spaced grid construction; domain-expansion variants
    runner.py         sweep driver; writes append-only raw results
  analysis/
    classify.py       A/B/C + strict all-ties-must-be-A rule
    metrics.py        rho_exact, feasibility, B-rate, C-rate, tie fraction
    regions.py        robustness-region geometry + connectedness
```

### F.2 Anti-coupling rules (directly answering the Codex brief's §10 concerns)

1. `objective.py` and `constraints.py` know **nothing** about encodings; both encodings import the same
   residual functions.
   > **CORRECTION (C0-07).** An earlier draft claimed this means a residual bug "cannot silently favour
   > one encoding". **That is false and is withdrawn.** The two encodings' penalty *shapes* respond
   > differently to the same wrong residual — slack is flat on the feasible side while unbalanced is a
   > parabola — so a shared residual error can still bias the comparison. Shared code removes
   > *duplication*, not *bias*. **Required:** validate residuals against an independent hard-feasibility
   > predicate written separately from the residual functions (V-18).
2. `slack.py` and `unbalanced.py` share **no code** with each other beyond those residuals. No common base
   class, no shared "penalty" helper. Duplication is preferred over abstraction here.
3. `groundtruth/enumerate.py` (which produces `x*`) and `certify/groundstate.py` (which produces `z*_E`)
   are separate modules with **no shared code path**, enforcing §C.7.
4. `classify.py` consumes only decoded `x` vectors plus `x*`; it never sees energies or encoding identity,
   so it cannot apply a different rule to one encoding.
5. Raw results are **append-only**; the runner refuses to overwrite an existing result file.

### F.3 Exact ground-state certification

`[SCOPE §15]` For fixed `x`, each slack penalty term is convex in its own independent register with no
cross-terms, so the joint minimization decomposes into independent O(1) per-constraint minimizations:

```
S*_c = clamp(round(h_c(x)), 0, 2^{N_c} - 1)
```

`[EXPERIMENTAL, M7]` Because all residuals are integer-valued on the Stage-1 instance, this is exactly
`clamp(h_c(x), 0, 2^{N_c} - 1)` with no rounding ties.

`[DERIVED, M6]` `S*` depends only on `h(x)` and `N` — both fixed by the problem, not by the penalty
coefficients — so it is computed **once per `x`**, not once per grid point.

Naive `2^39` enumeration is **forbidden** as the production path `[SCOPE §26]`, but is required as a
small-instance validation oracle (V-2).

### F.4 The precompute-once structure `[DERIVED — new here, not in the Scope Lock]`

This is the load-bearing architectural claim and should be attacked first.

Every quantity that varies over `x` is independent of `s`. So:

**Pass 1 (once per instance, O(2^20)):** compute and cache, as flat arrays of length `2^20`:
`f(x)`, `h_card(x)`, `h_sector,j(x)` for `j = 1..4`, `h_budget(x)`, and the clamped slack residuals
`(h_c - S*_c)` per constraint.

**Pass 2 (per grid point, O(2^20) arithmetic, no recomputation of `x`-dependent structure):** each encoding's
energy is a weighted sum of cached arrays; ground state is an `argmin`; the tie set is the argmin's
multiplicity.

Consequences:
- Memory: ~8 cached float64/int arrays x 2^20 x 8 B ~ 60 MB. Fits comfortably in RAM.
- Cost per grid point: a handful of vectorized passes over 10^6 elements — milliseconds, not minutes.
- This is what makes a **multi-axis** grid (U-01) tractable. If the grid turns out to be 3-D at ~50 points
  per axis (125,000 points x 2 encodings), the naive "redo the O(2^20) search per grid point" reading would
  be ~10^11 operations; the precompute structure reduces it to ~10^11 *cached-array arithmetic* operations
  that vectorize, which is the difference between infeasible and an overnight run.

**This estimate is `[INFERENCE]`, not measured.** Its earlier suggestion that a small-grid benchmark must
precede freezing U-05 is superseded by D012's human approval of the density rule. Any later performance
claim still requires an appropriately reported benchmark; no such claim is established here.

### F.5 Result storage

`[SCOPE §26]` Save **every grid result**, not just summary statistics — the region-shape and connectedness
analysis needs the full field. Alongside results, persist: grid definition, `s`-domain bounds, `Lambda_ref`
and its definition, `kappa_risk`, register widths, instance content hash, all RNG seeds, and
library/interpreter versions.

### F.6 Environment `[EXPERIMENTAL]`

Python 3.12.3; `numpy` present; **`pandas`, `scipy`, `matplotlib`, `pytest` absent**. `pip3` available, no
virtualenv yet. The loader must therefore either avoid pandas or the environment must be provisioned; this
is a Gate-2 task, recorded here so it does not surprise us later. The facts script deliberately uses only
the standard library so the auditor can re-run it with zero setup.

---

## G. Validation Architecture

Specified separately in `research/01_validation/VALIDATION_SPEC.md`.

---

## H. Unresolved Decisions

Specified separately in `research/decisions/UNRESOLVED_DECISIONS.md`. **Fourteen** items, of which
U-01 (grid dimensionality, **CLOSED D002**), U-02 (`kappa_risk`, **CLOSED D007**), U-03 (`Lambda_ref`, **CLOSED D008**), U-06 (register domain, **CLOSED**) and U-07
(canonical data assembly) are blocking for any implementation work.

---

## What this document does NOT establish

- Nothing here is validated. No test has been run against any component of this specification.
- No experimental result exists, and none may be produced before Gate 0 closes.
- The prototype audit is based on reading the notebook and data files; the prototype was **not executed**
  (it requires pandas/scipy, absent from this environment), so its reported outputs are `CANNOT VERIFY`.
- The technical report PDF was not parsed; claims attributed to it come from `[SCOPE §3]` and the README.
- The literature record in the Scope Lock was taken as given and **not re-verified** — re-auditing it is
  outside Gate 0's remit and is explicitly discouraged by `[SCOPE §24]` absent new cause.
