# Scientific Decisions

## Process Approval Record — Gate 0

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-23.

**Decision:** Accept `research/audit/GATE_0_CODEX_AUDIT.md` and authorize **entry to Gate 1 only**.

**Scope:** This is a governance approval, not a new numbered scientific decision. It authorizes **entry to
Gate 1 only**: freeze and validate the executable mathematical specification and resolve the decisions
assigned to that gate.

It does **not** authorize (the list is quoted from `research/audit/GATE_0_CODEX_AUDIT.md`, "What Human
Gate-0 Approval Authorizes"):

- changing D004/D005/D006 or selecting a sensitivity calibration after results;
- treating pre-canonical data-derived values as canonical;
- canonical-data assembly (G2), original-problem ground truth (G3), encoding work (G4), QUBO
  certification (G5), experiments (G6-G9), or final scientific conclusions (G10);
- resolving any deferred scientific decision without its own recorded approval.

D001, D002, D004, D005, and D006 remain scoped exactly as recorded. Each later gate is separately gated.

---

## D001 — Penalty parameterization
Status: APPROVED

Decision:
Use objective-normalized dimensionless s parameterization.

Reason:
As specified in Scope Lock §14.

Approved:
Shivansh
2026-08-22

---

## D002 — Penalty-coordinate dimensionality (3-D joint grid)
Status: APPROVED (with conditions)

Decision:
The penalty landscape is a 3-D joint grid over one dimensionless coordinate per constraint family,
s = (s_card, s_sector, s_budget). The four sector constraints share one coordinate.

Reason:
Scope Lock SS18/SS22 (three coefficients, joint grid, H3) versus SS14/SS25 (single frozen scalar s) are
mutually contradictory; every option is a departure from some frozen text. The SS18/SS22 reading is adopted
because a single scalar makes the pre-registered hypothesis H3 untestable inside the sweep. Compute does not
discriminate (benchmarked).

IMPORTANT — classification:
This is formally a SCOPE AMENDMENT to SS14/SS25, NOT a mere interpretation. An earlier Claude draft and the
Codex audit both implied 3-D was scope-preserving; both were wrong. Recorded in
research/decisions/SCOPE_AMENDMENT_001.md. The Scope Lock itself is NOT modified.

Conditions:
- U-16 (unbalanced parameterization family) remains OPEN and BLOCKING.
- U-18 (unbalanced 2-DOF -> 1-DOF reduction) is NEW, raised by this amendment; decide with U-16.
- U-15 (v_ref) remains OPEN and enters every mapping.
- U-04/U-05 must now be fixed for three axes.
- Submit to Codex for independent review before implementation.

Approved:
Shivansh
2026-08-22

---

## D003 — Stage 2 RNG protocol
Status: PENDING

Proposed:
...

Codex audit:
...

Claude response:
...

Final decision:
[PENDING]

---

## D004 — Unbalanced penalty parameterization (U-16)
Status: **APPROVED — PARENT FAMILY ONLY**

Proposed:
Adopt Option 1 (outer-scale Taylor) as the unbalanced parameterization family, in explicit two-parameter
form; reject Option 2 (it is the curvature-match rule Scope Lock SS14 already rejected); retain Option 3 as
a sensitivity probe only. Do NOT bundle a 2-DOF -> 1-DOF reduction into this approval (that is U-18).

Reason:
The frozen SS14 mapping is dimensionally inconsistent ([lambda_2 h^2] = E^2, not E) and not
objective-rescaling invariant — verified to flip the decoded ground state under a pure change of units.
Option 1 is the minimal repair: it restores the omitted penalty energy reference and preserves the
Montanez-Barrera Taylor shape.

Memo:
research/decisions/U16_DECISION_MEMO.md
Verification: research/audit/verify_u16.py

Explicitly NOT claimed:
That this mapping is canonical, unique, or comparatively neutral. It is not. All A/B/C classifications for
unbalanced, and H0/H1/H2/H3, become conditional on this choice and on U-18.

Codex audit:
Independently DERIVED the same parent family from Scope Lock SS14 + Montanez-Barrera eq. 24 without
working from the memo, reaching identical coefficients, units, the lambda_2 = lambda_1^2/(2*Lambda_pen)
relation, h* = v/a and depth -Lambda_pen/2. Confirmed Option 2 is the curvature-match rule SS14 already
rejected. Findings U16-01..05 raised and actioned.
Propagation audit of THIS approval: **COMPLETED 2026-08-23** in `research/audit/GATE_0_CODEX_AUDIT.md`; no scope change to D004.

---

## APPROVED SCOPE (exact, limited)

Approved: Shivansh, 2026-08-22.

**What is approved — the PARENT FAMILY ONLY**, for each inequality constraint family `j`:

    zeta_j(h) = Lambda_pen,j * [ -a_j * (h / v_j) + ( a_j * h / v_j )^2 / 2 ]
    lambda_1,j = Lambda_pen,j * a_j   / v_j            [E / R]
    lambda_2,j = Lambda_pen,j * a_j^2 / (2 * v_j^2)    [E / R^2]

with the derived properties `lambda_2 = lambda_1^2 / (2*Lambda_pen)`, reward-minimum location
`h* = v_j / a_j` [R], and depth `-Lambda_pen,j / 2` [E].

Also approved as part of this scope:
- **Option 2 is REJECTED** — it is the curvature-match rule Scope Lock SS14 already rejected, with the
  identical directional gap `D = s*w > 0`.
- **Option 3 is retained as a SENSITIVITY PROBE ONLY**, never as the primary design.

**What this decision explicitly does NOT approve** *(status as of D004, 2026-08-22; the first three
items were subsequently approved on 2026-08-23 by D005 and D006 — this list records D004's own scope,
not current project status)*:
- **U-18(a)** — the reduction rule `a_j = g(s_j)`. NO RECOMMENDATION exists. NOT approved by D004.
  → **Approved 2026-08-23 as D006(a): R2, `a(s) = sqrt(1+2s)-1`.**
- **U-18(b)** — the outer-scale calibration `c_j` / `Lambda_pen,j`. Recommendation only. NOT approved by
  D004. → **Approved 2026-08-23 as D006(b): `c_j = 1`.**
- **U-15** — `v_ref`. PROPOSED — NOT APPROVED by D004.
  → **Approved 2026-08-23 as D005: Option B, per-constraint.**
- Any numeric value: `Lambda_ref` (U-03), the three-axis box (U-04), `kappa_risk` (U-02).
  → **Still not approved.** D005 approves a *rule*; the numeric `v_ref = (1,1,5)` remains pending G2.
- Any claim that the family is canonical, unique, or comparatively neutral. **It is none of these.**

**Conditioning that travels with this approval:**
1. `Lambda_pen,j` and `a_j` both remain free. The approved family has **2 DOF per constraint** and is
   therefore **not yet dimension-matched** to slack's 1 DOF. The reduction is U-18 and is unresolved.
2. All A/B/C classifications for the unbalanced encoding, and hypotheses H0-H3, are conditional on this
   family **and** on the still-unresolved U-18.
3. Gate-1 entry criterion **E2 is now met**. **E3 (U-18a), E4 (U-18b) and E5 (U-15) remain unmet**, so
   Gate 1 cannot be entered on this approval.

> **SUPERSESSION NOTE (2026-08-23, after D005 + D006).** The three conditioning clauses above were
> written when U-15 and U-18 were open. Their current standing:
>
> - **Clause 1 is DISCHARGED by D006.** With `c_j = 1` and `a_j = a(s_j)`, the unbalanced family has
>   **1 DOF per inequality family**, which dimension-matches slack. The clause text is retained as the
>   record of what was true at approval time.
> - **Clause 2 STANDS, with its conditioning now NAMED rather than open.** Unbalanced A/B/C
>   classifications and H0-H3 remain conditional — no longer on an *unresolved* U-18, but on the
>   *specific, non-neutral* D005 + D006 choices, including D006's quantified `D < 0` bias for all
>   `w > 1`. Resolution did not remove the conditionality; it fixed its content.
> - **Clause 3 is SUPERSEDED in part.** E2, E3, E4 and E5 are now met. Gate 1 entry is governed by the
>   remaining criteria; see `STATUS.md` for the current arithmetic.
>
> D004's own approved scope is otherwise unchanged: the parent family, Option 2 rejected, Option 3 as a
> sensitivity probe only, and no claim of canonicity, uniqueness or comparative neutrality.

Final decision:
**APPROVED at the parent-family level only, 2026-08-22, Shivansh.** Scope strictly as stated above.


---

## D005 — Reference violation scale `v_ref` (U-15)
Status: **APPROVED — Option B (per-constraint)**

Approved: Shivansh, 2026-08-23.

Decision:
`v_ref,j` is the **smallest attainable positive NATIVE violation** of constraint family `j` over the
declared primary QUBO/original decision domain `x in {0,1}^20`.

**It is NOT defined via `gcd(prices)`.** The gcd is only a lower bound on the attainable violation;
that the two coincide for Stage 1 (both 5) is a verified **instance fact**, not the definition.
Counterexamples where they diverge are on record: `[10,10,10], B=15` (gcd 10, min 5);
`[6,10,15], B=7` (gcd 1, min 3).

For the canonical Stage-1 instance the rule is **expected to evaluate to `v_ref = (1, 1, 5)`**
(cardinality, sector, budget), **subject to final canonical-data assembly and verification under
U-07/G2**. The value is a consequence of the rule applied to canonical data, not an independently
approved constant.

Reason:
Under the rejected global `v_ref = 1`, Scope Lock SS14's stated justification — "the smallest nonzero
integer violation" — is **factually false for the budget family**: the smallest reachable budget
violation is 5, so a unit budget violation cannot occur and the constraint would be normalized on a
non-attainable unit. Option B normalizes each family on its own attainable lattice.

Explicitly NOT claimed:
- That `(1, 1, 5)` is a general or market constant. It is contingent on the Stage-1 price vector,
  which `PROTOTYPE_AUDIT.md` F-4 records as **synthetic and hand-chosen**.
- That U-15 is a rescaling-invariance repair. **Both options preserve objective-rescaling invariance**
  and both are currency-unit invariant when stated dimensionally; rescaling is NOT a discriminator here.
  The SS14 defect is narrower: a reachability/interpretation error, not a units failure.
- That this resolves the Stage-2 comparability question, which requires an explicit U-09 decision and a
  defined Stage-2 estimand.

Verification: `research/audit/verify_u15.py`, `research/audit/verify_d006.py` SS7,
`research/audit/audit_u15.py`.
Memo: `research/decisions/U15_DECISION_MEMO.md`.

Final decision:
**APPROVED — Option B, rule-defined, 2026-08-23, Shivansh.** The numeric `(1, 1, 5)` is pending
canonical-data verification at G2.

---

## D006 — Unbalanced 2-DOF -> 1-DOF reduction (U-18(a) + U-18(b))
Status: **APPROVED — as ONE package**

Approved: Shivansh, 2026-08-23.

Approved jointly because `c_j` and `a_j` together determine `lambda_1` and `lambda_2`; neither part is
meaningful alone.

### (b) Outer-scale calibration — APPROVED

    Lambda_pen,j = Lambda_ref        i.e.  c_j = 1,  for every INEQUALITY family j

One common fixed constant across the inequality families, on **minimality and identifiability** grounds:
`v_ref,j` (D005) already normalizes residual units and the D002 sweep coordinates `s_sector`, `s_budget`
already express independently swept strength, so a family-specific `c_j` would add a hidden relative-
strength calibration living outside the swept axes.

### (a) Reduction rule — APPROVED: R2, minimum-reachable-violation point matching, `r = 1`

    a(s)         = sqrt(1 + 2s) - 1
    lambda_1,j   = Lambda_ref * a(s) / v_j                [E / R]
    lambda_2,j   = Lambda_ref * a(s)^2 / (2 * v_j^2)      [E / R^2]

This is the `r = 1` member of the one-parameter family `a_r(s) = -r + sqrt(r^2 + 2s)` established in
`U18_DECISION_MEMO.md`. It applies to the **sector and budget inequality families ONLY**.

**Cardinality is EXCLUDED from D006.** It is the separate shared **equality** penalty governed by U-13
(`alpha`); it has no `r`, no reduction rule, and no unbalanced coefficient pair under this decision.

### Predeclared sensitivity calibrations

`r in {0.5, 2}`, evaluated with the SAME general rule `a_r(s) = -r + sqrt(r^2 + 2s)`.

These are **sensitivity analyses only**. They are **not alternative primary calibrations** and
**must not be selected or substituted for the primary `r = 1` mapping after results are observed.**
The primary calibration is pre-registered as `r = 1` and is frozen.

### KNOWN BIAS — mandatory conditioning statement

With `c_j = 1` and the R2 identity `a + a^2/2 = s`, the infeasible-side gap collapses exactly to

    D(w) = a(s) * w * (1 - w),        w = |h| / v_ref

so `D = 0` at `w = 1` only, `D > 0` on `0 < w < 1`, and **`D < 0` for EVERY `w > 1`, at every `s > 0`.**
Negative `D` means the unbalanced encoding is **under-penalized relative to slack**.

Quantified on the reachable supports under D005 (`verify_d006.py` SS8). **These counts are CONDITIONAL
on the PRE-CANONICAL prototype price vector and are EXPECTED values pending U-07/G2** `[Codex P3]` —
canonical data assembly has not occurred, and `PROTOTYPE_AUDIT.md` F-4 records that vector as synthetic
and hand-chosen. **Do not cite them as canonical.** The *sign* result (`D < 0` for all `w > 1`) is
independent of the data; only the counts are conditional.

| Family | Reachable normalized violations | Matched (`D=0`) | Under-penalized (`D<0`) |
|---|---|---|---|
| Sector | `w in {1, 2, 3}` | 1 of 3 | **2 of 3** |
| Budget | 1068 distinct `w in {1..1095}` | 1 of 1068 | **1067 of 1068** |

**Stated precisely** `[Codex U16-01, P4]` — this is a **LOCAL PENALTY-GAP** statement and nothing more.
It is **hypothesis-ALIGNED with H2 and it CONFOUNDS the comparison**. It does **NOT** establish, predict
or bound any A/B/C outcome or Category-C rate: ground states depend on the entire spectrum, not on local
gaps, and whether this changes any global ground state is an **experimental question**. The concern is
that the gap points the same way as the hypothesis — enough to disqualify R2 as a *default*, which is why
R2 was previously RETRACTED as a *recommendation*. It is accepted here as a deliberate, pre-registered
**conditioning choice**, with that retraction standing unreversed.

Every reported unbalanced result MUST carry this conditioning. Specifically:
1. R2 establishes matching at `w = 1` **only**. It establishes **no** neutrality at larger violations.
2. It **predicts no A/B/C outcome** and must never be described as a neutral or fair baseline.
3. Any observed unbalanced-vs-slack difference at `w > 1` is **confounded with this known bias** and
   may not be attributed to the encoding without separating the two.

Explicitly NOT claimed:
- Neutrality, canonicity, or uniqueness of this reduction. `U18_DECISION_MEMO.md` establishes that
  **no candidate rule is neutral**; choosing one selects where in residual space the comparison is
  conditioned.
- That the `a_r` family exhausts the one-coordinate rules. Infinitely many `a = g(s)` lie outside it;
  the family covers target-point and fixed-weighted-mean matching only.

### Implementation constraints (numerical) — MANDATORY

**1. `a(s)` MUST NOT be evaluated as written.** `[Codex P2]` `sqrt(1 + 2s) - 1` is the mathematical
**definition**; evaluated directly it **cancels catastrophically** as `s -> 0`. Measured
(`verify_d006.py` SS1b): relative error `~1e-9` at `s = 1e-8`, `~1.3e-4` at `s = 1e-12`, and at
`s = 1e-16` double precision returns **exactly `0.0`** while the true value is `~1e-16`.
**U-04 has not fixed a positive lower bound on the `s` box, so no approved decision excludes this
regime.** Implementations MUST use the algebraically identical rationalized form:

    a(s)   = 2*s / ( sqrt(1 + 2*s) + 1 )                      [MANDATED evaluation]
    a_r(s) = 2*s / ( sqrt(r^2 + 2*s) + r )                     [sensitivity r]

**2. The gap `D` MUST use the closed form.** `a^2/2 - s` equals exactly `-a`, so
`D(w) = a(s)*w*(1-w)`. Implementations MUST NOT recompute `a^2/2 - s`.

**Measured magnitudes, stated precisely** (`verify_d006.py` SS3b) — `N * DBL_EPSILON` **relative
error** and `N` **ulps** are *different measures* and are not interchangeable:

| Evaluation of `a` | Worst general-vs-closed disagreement on the probe grid | at |
|---|---|---|
| **Mandated (rationalized)** | `5.9 * DBL_EPSILON` relative (`6` ulps) | `s = 20`, `w = 1.5` |
| Naive (`sqrt(1+2s)-1`) | `46.1 * DBL_EPSILON` relative (`88` ulps) | `s = 0.01`, `w = 1.5` |

**Measured TRUE ULP distance between the two evaluations of `a` itself** (`verify_d006.py` SS1/SS10,
`[Codex P5]` — measured with `math.ulp`, not an epsilon-scaled tolerance):

| Calibration | Worst direct-vs-stable distance | at |
|---|---|---|
| `r = 1` (primary) | **20 ulps** | `s = 0.01` |
| `r = 0.5` (sensitivity) | 17 ulps | `s = 0.01` |
| `r = 2` (sensitivity) | **81 ulps** | `s = 0.05` |

The sensitivity branches are **not** better behaved than the primary — `r = 2` is four times worse — so
the mandated rationalized evaluation applies to **all three** calibrations, not only `r = 1`.
Against a high-precision reference the stable form is within **1 ulp** across the tiny-`s` set.

> **CORRECTION to an earlier Claude finding.** The first propagation reported "up to 46 ULP, worst as
> `s -> 0`" and attributed it to the `a^2/2 - s` subtraction. That **misattributed** the error and
> **misused the term ULP**: the figure was `46 * DBL_EPSILON` *relative error* (`88` ulps), and the
> **dominant source was the naive `a`, not the gap expression**. With the mandated evaluation the
> residual is `~6 * DBL_EPSILON`. Both are **probe-grid observations**, not proven bounds as `s -> 0`.

### Consequence for D004

The approved family now has **1 DOF per inequality family** (`s_j` alone), which **dimension-matches
slack's 1 DOF**. This discharges D004 conditioning clause 1. Clauses 2 and 3 are superseded only in
part — see the supersession note recorded under D004.

Verification: `research/audit/verify_d006.py` (new), `research/audit/verify_u18a.py`,
`research/audit/verify_u16.py`.
Memo: `research/decisions/U18_DECISION_MEMO.md`.

Final decision:
**APPROVED as one package — (b) `c_j = 1`; (a) R2 with `r = 1`; sensitivity `r in {0.5, 2}`;
inequality families only; 2026-08-23, Shivansh.** Conditional on D005.

---

## D007 — Risk-aversion parameter `kappa_risk` (U-02)
Status: **APPROVED — as a (value, unit, period) TRIPLE**

**Approved:** Shivansh, 2026-08-23. **Memo:** `research/decisions/U02_DECISION_MEMO.md` (revision 5,
supporting analysis — not the decision). **U-02 is CLOSED.**

### The approved triple

    kappa_risk = ( 1.0 , (decimal simple daily return)^-1 , daily )

Recorded as **one indivisible item, not three fields.** By the rescaling law below, the scalar alone does
not name a model.

| Component | Approved value |
|---|---|
| value | `1.0` |
| unit | `(decimal simple daily return)^-1` |
| period | `daily` — no annualization or other horizon conversion |

`f(x) = -mu^T x + kappa_risk * x^T Sigma x` `[SCOPE §12]`, with `mu` the mean **daily simple decimal**
return vector and `Sigma` the **daily** covariance of those returns.

### Why the unit is load-bearing — the rescaling law

For a change of return representation `R' = c*R`: `mu' = c*mu` and `Sigma' = c^2*Sigma`, so preserving the
objective's ordering of portfolios requires

    kappa_risk' = kappa_risk / c

Exact and unit-derived; no data required. Consequences:

| Representation | Ordering-equivalent value | Status |
|---|---|---|
| decimal returns | `1.0 R^-1` | **the approved value** |
| percentage returns | `0.01 (% return)^-1` | the SAME model, correctly transcribed |
| percentage returns | `1.0 (% return)^-1` | a **DIFFERENT** model — 100x more risk-averse |

**A record giving the value without the unit fixes nothing, and the failure is silent — both records read
`1.0`.** `[kappa_risk] = R^-1`: it is **not dimensionless**.

### Horizon policy — approved

> Use the native sampling period of the canonical return series, with **no annualization or other horizon
> conversion**, unless a separately declared aggregation model is approved.

Every horizon conversion requires an aggregation model, and **no aggregation model is declared by the
frozen scope, by any approved decision, or by this record**. Should one ever be wanted, it is a further
declared assumption requiring **its own approved record**.

### Ordering: U-02 fixes the period; U-07/G2 builds to it

    U-02 (G1)   FIXES the period — part of this approved triple
    U-07 / G2   BUILDS the canonical return series at that period and VERIFIES conformance

**G2 does not supply the period and cannot change it.** This decision is therefore a **binding constraint
on U-07**, recorded before U-07 is resolved. `mu` and `Sigma` assembled at G2 must be verified to conform
to **value, unit AND period**, and the G2 record must state that conformance explicitly. A later mismatch
is a **silent objective substitution**, not a rounding difference.

### Ground of choice — recorded exactly, because it is narrow

**Outcome-independent provenance.** The value was fixed before any result was observed, on grounds
independent of any outcome. This is the auditable condition M10 supports (approval timestamp precedes any
result artifact referencing it). **It is NOT a positive scientific justification, and none is claimed:**
no criterion distinguishes `1.0` from `0.5` or `0.75` without appealing to a result, which is forbidden.
This is a **conventional choice made openly and early**, and that is its entire defence.

**Structural symmetry.** `kappa_risk` enters `f`, and `f` enters BOTH encodings' QUBOs identically
(`Q_E = f + penalty terms of E`). It appears in no encoding-distinguishing term, so it introduces **no
direct asymmetric bias** between slack and unbalanced. Mechanically checkable from the frozen formulas.

**Provenance of the unit and period.** The prototype pipeline computes `prices_df.pct_change()` (simple,
decimal), `mu = returns_df.mean()` and `Sigma = returns_df.cov()` on adjusted **daily** closes, with no
annualization — verified in `previous_work/QDTRINITY_sTAGE_2/datasets/QD_Trinity_Data_Pipeline_Setup (2).ipynb`
cells 11, 14, 17, 20. **This provenance supports the PERIOD and REPRESENTATION only.** The prototype's
numeric outputs remain **DO NOT TRUST** under `PROTOTYPE_AUDIT.md` F-1 (18 of 20 positions mis-joined);
a column mis-join cannot alter what `pct_change()` on daily prices computes, which is why the period and
representation survive the defect that invalidates the numbers.

**The word "neutral" is deliberately NOT used.** It is reserved in this project for the D006 conditioning
sense; the two precise claims above replace it.

### Rejected, with reasons

- **`kappa_risk` as an experimental axis** — outside frozen scope; the swept quantity is the *penalty*
  landscape (D001/D002). Would require a formal scope amendment.
- **Choosing `kappa_risk` so constraints bind "interestingly"** — **INADMISSIBLE.** Post-hoc design; an
  M10 failure and an R3 stop condition.
- **A data-derived deterministic rule** — *admissible* but not adopted: it needs its own ADNYE record, it
  relocates discretion into the rule rather than removing it, and it would be a **third** prospective
  record, which the Gate-1 charter's enumeration does not admit. **No cyclicity or DAG objection exists**;
  an earlier claim to that effect was withdrawn.
- **`kappa_risk = 0`** — deletes the risk term and discards `Sigma`; a different problem from `[SCOPE §12]`.

### Constancy

`kappa_risk` is **constant** across all grid points of the 3-D `(s_card, s_sector, s_budget)` grid, across
**both encodings**, across **all constraint-ablation configurations** (U-12), and across **all instances
including Stage-2** (U-08..U-11; D003 pending) unless a later approved decision says otherwise. It must
appear in **no** coefficient map as a function of `s`.

### Pre-declaration (accepted with this approval) — R-U02-2

**A large, degenerate or otherwise inconvenient `X*` discovered at G3 is NOT grounds to revisit
`kappa_risk`.** It is grounds to invoke U-17's mixed-tie semantics. Any genuine re-opening requires a new
dated approval that states what was observed first. **Recording this now is what makes it binding;
recording it after G3 would not.**

### Sensitivity probe — NOT approved

A bounded `kappa_risk` sensitivity probe (memo option (d)) is **outside the frozen scope** and was
**deferred, not approved** ("not now", Shivansh, 2026-08-23). Authorizing it would need explicit separate
scope authority, most likely a formal amendment on the D002 model. **Consequence, which must survive into
any write-up:** the study will produce **no evidence whatever** on sensitivity of conclusions to
`kappa_risk`.

### Explicitly NOT approved by D007

- Any claim that `1.0` is financially realistic, calibrated, or optimal.
- Any claim of insensitivity to `kappa_risk`, or any sensitivity evidence.
- `Lambda_ref`'s definition (U-03) or its numeric value; the `s`-box (U-04); grid resolution (U-05);
  `alpha` (U-13); any value of `X*`, `f*` or `Lambda_ref`.
- The date window of the canonical return series — **U-07/G2**, and see the note below.
- Any Stage-2 parameter.

### MANDATORY CONDITIONING

Every downstream conclusion — H0-H3, all A/B/C classifications, all robustness-region geometry — is
**CONDITIONAL ON `kappa_risk = ( 1.0 , (decimal simple daily return)^-1 , daily )`**, and must be reported
as such alongside the D006 conditioning it already carries. `kappa_risk` is **not** absorbed by D001's
objective normalization: `f_kappa = f_0 + kappa*g` is **affine in `kappa`, not proportional**, so different
values give functions that are not scalar multiples and can order `F` differently. V-15's rescaling
invariance (`f -> gamma*f`) does **not** apply to it.

### Carried finding for U-07 (not resolved here)

The prototype pipeline's date window **floats with the run date**
(`end_date = today - 1 day; start_date = end_date - 1 year`, cell 11), so re-running it yields different
`mu`/`Sigma`. **U-07/G2 must pin an explicit start/end date**, or the canonical data is not reproducible
however well this triple is specified. This is a U-07 obligation; D007 neither resolves nor depends on it.

### NOTATION CORRECTION — 2026-08-23, Claude (post-approval; the DECISION is unchanged)

**Defect, self-reported.** The text above writes `[kappa_risk] = R^-1` using `R` for the **return
representation**. That **collides with the project's declared units algebra**, in which
`[f] = E` (objective) and **`[h] = R` (RESIDUAL / violation)** — see `IMPLEMENTATION_SPEC.md` C0-01 note
(`Lambda_ref` has units `E`, `v_ref` has units `R`, `lambda_1` has units `E / R`). Two different meanings
of `R` in the same specification is precisely the `kappa` collision `[SCOPE §12]` already warns against.

**Canonical statement, in the declared algebra.** From `[f] = E` and `f = -mu^T x + kappa_risk * x^T Sigma x`
with `x` dimensionless: `[mu] = E`, `[Sigma] = E^2`, therefore

    [kappa_risk] = E / E^2 = E^-1

**`[kappa_risk] = E^-1` is the form that binds implementers and M2.** It is the same fact as
"inverse return" — the objective's unit `E` is *realized* as decimal simple daily return under this
decision — but stated in the algebra the acceptance checks actually use.

**Scope of this correction: NOTATION ONLY.** The approved triple, the horizon policy, the rescaling law,
the ordering, R-U02-2 and the option-(d) deferral are all unchanged and require no re-approval. Where the
text above uses `R` inside the rescaling law (`R' = c*R`, `mu' = c*mu`, `Sigma' = c^2*Sigma`), `R` there
denotes the **return representation** and the law is correct as written; only the *unit symbol* for
`kappa_risk` was wrong. When the frozen symbol table is written at W2, the `kappa_risk` row must carry
**`E^-1`**, with the return convention and period recorded alongside it.

Final decision:
**APPROVED — `kappa_risk = ( 1.0 , (decimal simple daily return)^-1 , daily )`, constant everywhere,
no horizon conversion absent a separately approved aggregation model; R-U02-2 accepted; option (d)
deferred. 2026-08-23, Shivansh. U-02 CLOSED.**

---

## Process Approval Record — Gate-1 Work Plan (Revision 2)

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-23.

**Decision:** Adopt Gate-1 work-plan **revision 2** (`claude_messages/to_codex.md` [2026-08-23 07:10:55])
as the **operational Gate-1 sequence**.

**Scope:** This is a **governance approval of sequencing**, not a numbered scientific decision, and it
approves **no** scientific content. It fixes the order of work only:

    W0a -> W1 -> W0b -> W2 -> W3 -> W4 -> W5

- **W0a** — draft a clearly-labelled **NON-AUTHORITATIVE** Gate-1 charter. Ordinary G1 work; needs no
  scientific approval. **Already executed** under direct instruction (2026-08-23);
  `research/00_specifications/GATE_1_CHARTER.md` exists as a DRAFT and approves nothing.
- **W1** — resolve the **eight** Gate-1 decisions in dependency order:
  `U-02 -> U-03`, then `{U-13, U-04}` **jointly**, then `U-05`, then `U-12`, then `U-14 -> U-17`.
  **U-02 is now closed by D007.**
- **W0b** — freeze the charter as **authoritative**. **NOT APPROVED. Requires its own separate human
  approval and must follow W1.** This record does not authorize it.

> **SUPERSEDED STATUS NOTE — 2026-08-25, Codex.** The preceding W0b status was correct when Plan Revision 2
> was approved. Shivansh has since separately approved W0b; the authoritative current record is
> **Process Approval — W0b, Gate-1 Charter Freeze** at the end of this file. This preserves the original
> plan's non-authorization while correcting its now-stale status.
- **W2..W5** — frozen math specification; bounded specification verifier; propagation; independent
  reconstruction and human Gate-1 exit approval.

**Load-bearing points carried by revision 2, none of which this approval alters:**

- Gate-1 entry criteria are **E1-E5, all met**. **E6 was WITHDRAWN** as a standalone criterion and folded
  into E1 as a documentation-integrity precondition. **It must not be revived.**
- The Gate-1 acceptance checks keep the **Class A / Class B** split, with **M3a** (analytic proof) distinct
  from **M3b** (finite regression witness) — both required, and M3b never presented as establishing M3.
  Class B is **M4 and M5** specifically: declared at G1, enforced at G4. **M10** is a narrow necessary
  audit-trail condition only.
- **U-12 is in the decision set.** It is a G1 pre-registration decision gating the first result-producing
  run, though not an algebraic-specification prerequisite.
- **U-14 must define TWO comparators**: encoded-energy tie membership, and the separate original-objective
  `f(x) == f*` rule that U-17 consumes. The energy tolerance must not silently become the optimality rule.
- **U-03/U-04 freeze RULES, never numbers.** Their numeric outputs are prospective **ADNYE** records
  executing at G3 and G3-exit respectively. ADNYE currently has **zero instances**, both rules being
  unapproved.

> **SUPERSEDED STATUS NOTE — 2026-08-25, Codex.** The preceding ADNYE-count sentence was true when
> revision 2 was approved (before D008 and D010) but is not current status. **D008 and D010 now admit two
> prospective records** — numeric `Lambda_ref` and the three-axis domain box — and both remain **unexecuted**.
> This corrects status only; the governance sequencing approved in this record is unchanged.

**It does NOT authorize:** W0b; any scientific decision; canonical-data assembly (G2/U-07); original-problem
ground truth (G3); encoding work (G4); QUBO certification (G5); experiments (G6-G9); conclusions (G10).
**Each later gate remains separately gated.**

---

## D008 — Definition of `Lambda_ref` (U-03)
Status: **APPROVED — RULE ONLY; NO NUMERIC VALUE**

**Approved:** Shivansh, 2026-08-24. **Approval provenance:** given by Shivansh and relayed verbatim in
`codex_messages/to_claude.md` [2026-08-24 09:47:14], and confirmed directly by Shivansh to Claude in the
same session. **Memo:** `research/decisions/U03_DECISION_MEMO.md` (revision 4, supporting analysis — not
the decision). **U-03 is CLOSED.**

### The approved rule

    Lambda_ref = max_{x in F} f(x) - min_{x in F} f(x)

    F = { x in {0,1}^20 : sum_i x_i = K,  n_j(x) <= C for all j = 1..4,  p^T x <= B }

- **Statistic:** the **range** of `f` over the population — not the standard deviation.
- **Population `F`:** defined by the **predicate above**, never by a cardinality. **Do not write "the
  976-portfolio feasible set":** `|F| = 976` is `[EXPERIMENTAL]` and **pre-canonical**, depending on the
  synthetic hand-chosen price vector (`PROTOTYPE_AUDIT.md` F-4). `C(20,6) = 38,760` is exact combinatorics
  and may be stated as such.
- **Units:** `[Lambda_ref] = E`, the objective unit, realized under D007 as decimal simple daily return.
  **Never `R`** — in the declared algebra `R` is the **residual / violation** unit (`[h] = R`,
  `[v_ref] = R`, `[lambda_1] = E/R`). See D007's NOTATION CORRECTION.

### RULE ONLY — the number is NOT approved

**D008 approves a rule and fixes no numeric value.** The numeric `Lambda_ref` is a prospective **ADNYE**
record executing at `G3.compute_Lambda_ref`, with all six mandatory fields: the rule above; named inputs
(canonical `mu`, `Sigma`, the D007 triple, the canonical instance, and the `F` predicate); declared
dependency edges with acyclic closure; exact execution point; immutable hashed output location; and the
prohibition on encoded-QUBO or result artifacts anywhere in its closure.

> **CLARIFICATION — 2026-08-24, Claude. FIELD 5 IS ASSERTED BUT NOT SPECIFIED.**
> The sentence above lists six fields and thereby claims the charter §5 closure is complete. **It is not.**
> Field 5 — *standalone output location and content-hash scheme* — is discharged here only by the phrase
> "immutable hashed output location", which **names no location and defines no scheme**, and **no
> authoritative file supplies either** (searched: `IMPLEMENTATION_SPEC.md`, `VALIDATION_SPEC.md`,
> `GATE_1_CHARTER.md`, this register). **Raised by Codex** (`codex_messages/to_claude.md`
> [2026-08-24 15:12:23]) and verified before recording.
>
> **What this does and does not do.** It does **NOT** undo or narrow this decision: the rule, units,
> population, execution point and prohibitions all stand exactly as approved. It **DOES** mean the
> six-field closure **must not be claimed complete at W0b** until field 5 is actually specified and
> approved. **Neither agent has invented the missing fields.** Recommendation drafted for human review in
> `research/decisions/ADNYE_OUTPUT_CONTRACT_MEMO.md` (non-authoritative).

> **SUPERSEDED STATUS — D014, 2026-08-25.** Field 5 is now specified and human-approved for this record
> and D010's box record by D014, which adopts the ADNYE Output Contract revision 6. This changes neither
> D008's rule, numeric status, stop condition, or gate: the record remains admitted and unexecuted. The
> quoted clarification above is retained as the accurate pre-D014 state.


> **STATUS CHANGE — ADNYE now has its FIRST admitted prospective record.** Until this approval the ADNYE
> table had **zero** instances, because both its candidate source rules (U-03, U-04) were unapproved. With
> D008 the `Lambda_ref` row's source rule **is** approved, so it becomes an **admitted prospective record —
> still NOT executed.** The three-axis domain box (U-04) remains **unapproved and therefore still not an
> admitted instance.** Any surface stating "ADNYE has zero current instances" is now stale.
>
> **SUPERSEDED IN PART, 2026-08-24 by D010.** The sentence above about U-04 was true when D008 was
> approved and is retained unrewritten as the record of that moment. **U-04 was approved later the same
> day as D010**, so the box row is now an admitted prospective record too: **ADNYE has TWO admitted
> records, not one.** "`Lambda_ref` is ADNYE's first admitted record" remains true historically but must
> not be used as a present-tense count.

### Degeneracy guard

If `Lambda_ref` evaluates to `0` — every member of `F` sharing an identical `f` — this is a **G3 STOP
CONDITION**, not a value to be patched or substituted at runtime. Gate-1 exit forbids unresolved
mathematical choices, and an approved rule with an undefined edge case is one.

### Transparency reporting — approved, with an explicit limit

All considered candidate values are to be **reported at G3** alongside the approved value. **For
transparency ONLY, never for re-selection.** Seeing the candidates does not license changing the rule; it
exists so the conditioning can be reported honestly — if the candidates prove close, the caveat is minor;
if they diverge widely, that belongs prominently in any write-up.

**The considered candidates are these five** (statistic x population):

| # | Statistic | Population | Status |
|---|---|---|---|
| 1 | range | `F` (all three constraint families) | **APPROVED — this is the rule** |
| 2 | std | `F` | considered, rejected |
| 3 | range | cardinality-feasible (`sum_i x_i = K`) | considered, rejected |
| 4 | std | cardinality-feasible | considered, rejected |
| 5 | range | full decoded search space `{0,1}^20` | considered, rejected |

Candidates 2 and 4 are **not reportable as written**: "std" is incomplete until `ddof` is fixed (the same
completeness objection that counted against them in the ground of choice above). Whichever `ddof` G3
reports must be **stated with the number**; it is a reporting convention, not a decision, and it must not
be presented as a value `D008` could have approved.

> **CLARIFICATION — 2026-08-24 10:05 IST, Claude.** As first written, this section enumerated only "range
> and std, over `F` and over the cardinality-feasible set" — the **register's four**. That enumeration was
> **incomplete against the memo the approval rested on**: `U03_DECISION_MEMO.md` §4 ("A fifth the register
> does not list", lines 196-213) raises range over `{0,1}^20`, assesses it, and rejects it on two stated
> grounds. Shivansh approved "**all considered** candidates" reported at G3, so candidate 5 is inside the
> approval and was omitted by a clerical defect in Claude's drafting, not by any narrowing decision.
> **Raised by Codex** (`codex_messages/to_claude.md` [2026-08-24 09:55:10]) and verified against the memo
> before amending. **This is clerical: it implements the existing approval and changes no scientific
> content, no rule, no scope.** The approved rule, population, units, R-U03-2 and the ground of choice are
> all untouched.
>
> Two consequences Shivansh should see, neither of which is assumed resolved here:
> - **G3 cost.** Candidate 5 requires evaluating `f` over `2^20 = 1,048,576` points, against 976 for `F`
>   and 38,760 for cardinality-feasible. That is cheap, but it is a real G3 obligation this amendment
>   creates, and it did not exist under the four-candidate reading.
> - **If the narrower reading was intended,** i.e. Shivansh meant only the register's four, this is a
>   **one-line narrowing** — strike row 5 and say so. That narrowing needs his word; **Claude must not
>   choose it**, because the wider reading is the one the approval's own words support.

### Pre-declaration (accepted with this approval) — R-U03-2

**A transition region falling outside the eventual `s`-box is NOT grounds to revisit U-03.** It is grounds
for U-04's declared 0.5x/2x domain-expansion check `[SCOPE §14]`. Any genuine re-opening requires a new
dated approval that states what was observed first. **Recording this now is what makes it binding.**

**Scope note on R-U03-2, carried from the memo:** R-U03-2 constrains **re-selection after results**. It does
**not** restrict which arguments could be weighed before the decision. Ex-ante robustness was a legitimate
competing consideration and was weighed on its merits, not ruled out of order.

### Ground of choice — recorded narrowly

**Interpretability.** The range *is* the quantity `Lambda_ref` denotes: the largest objective difference
within the population, i.e. the objective scale a penalty competes against. Standard deviation is a proxy,
and a dispersion statistic imports a distributional framing absent from an exhaustive combinatorial
enumeration.

**Completeness.** `max - min` is a complete rule as written. "Standard deviation" is **not** complete until
`ddof` is fixed, and M1 forbids residual discretion at Gate 1.

**Population.** `F` is the population the scientific question is about (`X*`, `f*` and H0-H3 are defined
over it), and under **D002 all three constraint families are swept**, so singling out cardinality to define
the normalizer's population has no principled basis.

**NOT claimed, and recorded as unrefuted:** that robustness is irrelevant. Exhaustive enumeration removes
the **sampling-error** rationale for preferring std — `Lambda_ref` is a deterministic functional of a fixed
finite population, carrying no estimation uncertainty — but it does **not** remove **finite-population
sensitivity to extreme values**: the range is determined by exactly two members of `F` and the std by all
of them, however `F` was obtained. **That trade-off is real, was weighed, and is not refuted.** A reviewer
weighing finite-population sensitivity above interpretability would reach std by sound reasoning. The
residual concern stands on the record: if the extreme portfolio setting the range is one no penalty setting
under study would select, the range inflates the scale relative to the region actually explored. **The G3
candidate report is the declared mitigation** — it makes that a reported fact rather than a silent one.

### Bias

`Lambda_ref` is a **single common scalar** entering the slack and unbalanced coefficient maps identically
and appearing in no encoding-distinguishing term. It introduces **no direct asymmetric bias** at any grid
point. This is checkable from the frozen formulas.

**But it is NOT a free reparameterization.** `Lambda_ref -> gamma*Lambda_ref` with `s -> s/gamma` leaves
slack's `lambda_S` **exactly** invariant and sends unbalanced's **`lambda_2 -> lambda_2/gamma`** — worst in
the small-`s` regime, where the ratio is exactly `1/gamma`. `lambda_2` is quadratic in `a(s)`, so the
leading `gamma` cannot cancel `1/gamma^2` from `a(s/gamma)^2`. **Consequence: U-03's choice is a physical
choice for the unbalanced encoding and U-04 CANNOT compensate for it.** This distinguishes it from V-15,
which rescales `f` and drags `Lambda_ref` with it (`Q -> gamma*Q`, argmin invariant) — **V-15 is
unaffected**. No claim is made about how the two encodings' sampled grids correspond under a change of
normalizer; that belongs to U-04 and G6+.

### Explicitly NOT approved by D008

- Any numeric `Lambda_ref`, any candidate value, or any ratio between candidates.
- The `s`-box (U-04), grid resolution (U-05), `alpha` (U-13), canonical data (U-07), or any Stage-2 item.
- Any claim that the range is stable under canonical data, or that robustness is irrelevant.
- Execution of the `Lambda_ref` ADNYE record — that is **G3**, separately gated.

### MANDATORY CONDITIONING

Every downstream conclusion is **CONDITIONAL ON** the U-03 rule alongside D004-D007. Because U-03 is not
reparameterizable for the unbalanced encoding, a different `Lambda_ref` definition would sample a genuinely
different set of `(lambda_1, lambda_2)` pairs — this conditioning is **not** cosmetic.

Final decision:
**APPROVED — `Lambda_ref = range of f over predicate-defined F`, units `E`, RULE ONLY with no numeric
value; R-U03-2 accepted; all considered candidates to be reported at G3 for transparency only, never
re-selection. 2026-08-24, Shivansh. U-03 CLOSED.**

---

## D009 — `alpha(s_card)`: authority, specification repair, and certification policy (U-13)
Status: **APPROVED — CONFIRMS AN EXISTING APPROVAL; APPROVES A SPEC REPAIR AND A CERTIFICATION POLICY**

**Approved:** Shivansh, 2026-08-24, as one package with **D010**. **Approval provenance:** recommended
jointly by Claude (`U13_U04_DECISION_MEMO.md` §9, revision 3) and by Codex; **approved by Shivansh
directly to Claude in session.** **Memo:** `research/decisions/U13_U04_DECISION_MEMO.md` revision 3
(supporting analysis — not the decision). **U-13 is CLOSED.**

### The map was ALREADY approved — D009 does not re-approve it

    alpha(s_card) = s_card * Lambda_ref / v_card^2                    [E / R^2]

**This was approved on 2026-08-22** in `SCOPE_AMENDMENT_001.md` §3 ("Exact per-constraint mappings"), the
approved record of **D002**, which carries "*Status: APPROVED as the intended primary design (Shivansh,
2026-08-22)*". Its §3 sub-decision 2 adds that cardinality is penalized identically in both encodings so
`alpha(s_card)` is shared, while `s_card` remains a swept axis.

**D009 confirms that authority and closes what was actually left open.** It creates no new coefficient map.
Any statement that U-13 "selected" or "froze" `alpha` is wrong: **D002 is the source of the rule.**

> **RECORD CORRECTION.** `U13_U04_DECISION_MEMO.md` revisions 1-2 asserted that no approved decision
> supplied this map. That was **FALSE**, was found by Codex, and is retracted in `progress.md`
> [2026-08-24 ~11:4x] and in the memo's header and §11. Recorded here so the register does not inherit the
> error.

### (a) SPECIFICATION REPAIR — APPROVED

`IMPLEMENTATION_SPEC.md` §C.6's "**APPROVED replacement (D005 + D006)**" block lists `v_ref,j`,
`Lambda_ref`, `lambda_S,j(s)`, `a(s)`, `lambda_1,j(s)` and `lambda_2,j(s)` — and **omits the map
`s_card -> alpha`**. §C.4 line 199 does define the penalty **form** `P_card(x) = alpha*(sum_i x_i - K)^2`.

**So the specification reads as complete while leaving `alpha` a free parameter** — the downstream
discretion `GATE_1_CHARTER.md` §1 says Gate 1 exists to eliminate, and an **M1** symbol-completeness
failure that would block Gate-1 exit independently.

**APPROVED: propagate the approved map verbatim into §C.6.** This is a **non-substantive propagation
repair** — it relocates an approved formula, adds no computation, no obligation and no rule.

**`v_card^2` must be written explicitly even though it evaluates to 1.** With `v_card` elided the
expression is homogeneous only by numerical coincidence for this instance, and M1/M2 would pass by
accident.

### (b) CERTIFICATION POLICY — APPROVED: assert NO enforcement threshold

**No cardinality-enforcement threshold `s*` is asserted in the primary analysis.** Consequently:

- **V-17 obligation 1 (classification correctness at ALL grid points) stands UNCHANGED and unconditional.**
  Off-cardinality ground states must be *correctly classified as Category C*, **never prevented** — they
  are an expected outcome in the weak-`s_card` region under D002's deliberate sweep.
- **V-17 obligation 2 (threshold certification against all `2^20` states) does not fire**, because its
  trigger — a claimed threshold — is not present. It is **not weakened, retired, or waived**; it remains
  binding on any future analysis that does claim one, and such a claim would need its own approval.

**`alpha > Lambda_ref` remains WITHDRAWN as a sufficiency criterion** (C0-05): `Lambda_ref` is a range over
`F`, while cardinality-violating candidates live outside `F` where `f` is not bounded by it.

### (c) `v_ref` exactness — RECORDED, refining D005's pending clause

D005 records the expected triple `(1, 1, 5)` "*pending canonical-data assembly and verification at
U-07/G2*". **That pending status is NOT uniform across the three components:**

| Component | Status | Ground |
|---|---|---|
| `v_card = 1` | **EXACT** | `h_card = sum_i x_i - K` is an integer; `K = 6`, `n = 20`; support `[-6, +14]` step 1. Depends on **no** price, return, or ticker join. |
| `v_sector = 1` | **EXACT** | Counts are integers, `C = 2`; the Scope Lock fixes 20 assets across 4 sectors, so by **pigeonhole** some sector holds `ceil(20/4) = 5 >= C+1 = 3`. D005 evaluates `v_ref` over all of `{0,1}^20`, so an `x` with `n_j = 3` exists. **F-1 permutes which ticker occupies a slot; it does not change the counts 20 and 4.** |
| `v_budget = 5` | **PRE-CANONICAL** | Depends on the synthetic hand-chosen price vector (`PROTOTYPE_AUDIT.md` F-4). Genuinely pending U-07/G2. |

**D005 is NOT amended** — its rule and its numbers are unchanged. This records which of its components
U-07/G2 can still move. **Only `v_budget` is at risk.**

### (d) NOTATION CLARIFICATION

D006 states cardinality "*has no `a`, no `r`, and no `v_ref` normalization **under D006***". **That clause
scopes to the unbalanced coefficient pair D006 governs and does NOT remove cardinality's `v_ref`.**
`alpha` uses `v_card` per D005 and `SCOPE_AMENDMENT_001.md` §3. The alternative reading yields
`alpha = s_card*Lambda_ref`, which carries units `E` and **fails M2**.

### Explicitly NOT approved by D009

- Any numeric `alpha`, or any numeric `s_card` grid point.
- Any cardinality-enforcement threshold, now or by implication.
- Any reopening of D002, D005 or D006. D009 **confirms** D002 and **refines the reading** of D005's
  pending clause; it amends neither.
- Any claim that M2 or dimensional analysis *derives* the map. **M2 eliminates wrong forms; it does not
  single out this one** — `c*s*Lambda_ref/v^2` and `g(s)*Lambda_ref/v^2` are homogeneous too. **D002 is
  the source of uniqueness.**

Final decision:
**APPROVED — the `alpha(s_card)` map stands as approved under D002/`SCOPE_AMENDMENT_001` §3; propagate it
into `IMPLEMENTATION_SPEC.md` §C.6 as a non-substantive repair; assert NO cardinality-enforcement threshold,
leaving V-17 obligation 1 unconditional and obligation 2 untriggered but binding. 2026-08-24, Shivansh.
U-13 CLOSED.**

---

## D010 — Three-axis `s`-domain box (U-04)
Status: **APPROVED — RULE ONLY; NO NUMERIC BOUNDS**

**Approved:** Shivansh, 2026-08-24, as one package with **D009**. **Approval provenance:** recommended
jointly by Claude (`U13_U04_DECISION_MEMO.md` §9, revision 3) and by Codex; **approved by Shivansh
directly to Claude in session.** **Memo:** `research/decisions/U13_U04_DECISION_MEMO.md` revision 3
(supporting analysis — not the decision). **U-04 is CLOSED.**

### The approved rule — RULE-FIRST

    Delta_full = max_{x in {0,1}^20} f(x) - min_{x in {0,1}^20} f(x)          [E]
    rho        = Delta_full / Lambda_ref                                       [dimensionless, >= 1]

    s_max  = 10 ^ (  ceil( log10(rho) ) + m_hi )
    s_min  = 10 ^ ( floor( log10(rho) ) - m_lo )

    COMMON CUBE [s_min, s_max] on ALL THREE axes: s_card, s_sector, s_budget.
    m_hi = 1   (DERIVED -- see below)
    m_lo = 4   (JUDGEMENT CALL -- see below)

`rho >= 1` is exact because `F` is a subset of `{0,1}^20`.

**Why rule-first, recorded as an accepted risk trade:** frozen literal bounds (e.g. `[1e-3, 1e3]`) are
knowable today but carry a **trap with no exit** — if `rho` exceeds the frozen `s_max`, the box sits
entirely in the non-enforcing regime, and the only repair is moving the box after seeing where the
transition is, which is the **disqualifying** option (c). The derived rule brackets `rho` by construction.

### `Delta_full` IS EXPRESSLY AUTHORIZED AS THE BOX RULE'S SECOND INPUT

**This authorization is granted HERE and by D010 alone.** D008 admits the full-space range of `f` as a
**rejected candidate reportable for transparency ONLY, never for re-selection** — and **transparency
reporting is not authority to make a quantity a load-bearing input to another frozen rule.** Reusing an
already-computed number adds no arithmetic cost but **changes its authorized purpose**, and purpose is what
D008 scoped.

**The box's ADNYE record therefore has TWO named inputs — `Lambda_ref` AND `Delta_full`** — each with its
own declared dependency edge in the acyclic closure. **The box is not "a function of one G3 number".**

**This does NOT reopen U-03.** The U-03 memo §4 rejected range-over-`{0,1}^20` as the **normalizer**
because it "*would be a scale dominated by irrelevant corners*". That objection holds for a normalizer and
does **not** transfer to a **box bound**: a normalizer should reflect the region of scientific interest,
whereas a box must *contain* the regime in which even the most extreme violating state is dominated.
**The same quantity is wrong for one job and right for the other.** `Lambda_ref` remains the range over `F`
and remains the normalizer in every coefficient map.

### RULE ONLY — the numbers are NOT approved

**D010 approves a rule and fixes no numeric bound.** Numeric `rho`, `s_min` and `s_max` are a prospective
**ADNYE** record executing at `G3.exit.resolve_box`, **after `Lambda_ref` and before `G4.start`**, with all
six mandatory fields.

> **CLARIFICATION — 2026-08-24, Claude. FIELD 5 IS ASSERTED BUT NOT SPECIFIED.**
> The sentence above lists six fields and thereby claims the charter §5 closure is complete. **It is not.**
> Field 5 — *standalone output location and content-hash scheme* — is discharged here only by the phrase
> "immutable hashed output location", which **names no location and defines no scheme**, and **no
> authoritative file supplies either** (searched: `IMPLEMENTATION_SPEC.md`, `VALIDATION_SPEC.md`,
> `GATE_1_CHARTER.md`, this register). **Raised by Codex** (`codex_messages/to_claude.md`
> [2026-08-24 15:12:23]) and verified before recording.
>
> **What this does and does not do.** It does **NOT** undo or narrow this decision: the rule, units,
> population, execution point and prohibitions all stand exactly as approved. It **DOES** mean the
> six-field closure **must not be claimed complete at W0b** until field 5 is actually specified and
> approved. **Neither agent has invented the missing fields.** Recommendation drafted for human review in
> `research/decisions/ADNYE_OUTPUT_CONTRACT_MEMO.md` (non-authoritative).

> **SUPERSEDED STATUS — D014, 2026-08-25.** Field 5 is now specified and human-approved for this record
> and D008's `Lambda_ref` record by D014, which adopts the ADNYE Output Contract revision 6. This changes
> neither D010's rule, numeric status, execution point, or gate: the record remains admitted and unexecuted.
> The quoted clarification above is retained as the accurate pre-D014 state.


> **STATUS CHANGE — ADNYE now has TWO admitted prospective records.** D008 admitted the `Lambda_ref` row;
> **D010 admits the three-axis domain box row.** Both are **admitted, NOT executed.** Every surface stating
> that ADNYE has *zero* instances, or that `Lambda_ref` is its *only* / *first and only* admitted record,
> is now stale. `GATE_1_CHARTER.md` §5's clause that U-04's box "*is not admitted until its rule is
> approved*" has been satisfied and needs updating (charter is Codex-owned).

### The two margins are NOT equally grounded

**`m_hi = 1` is DERIVED.** The penalty at one minimum attainable violation (`w = 1`), in units of
`Lambda_ref`, is `s` for slack and cardinality, and `a_r + a_r^2/2 = s + r^2 - r + (1-r)*sqrt(r^2+2s)` for
unbalanced — equal to `s` **iff `r = 1`**. The binding pre-registered mapping is `r = 2`, whose bracketing
condition solves in closed form as

    s_2(rho) = (rho - 1) + sqrt(2*rho + 1),     sup_{rho >= 1} s_2(rho)/rho = sqrt(3) at rho = 1

so `m_hi = 1` (giving `s_max >= 10*rho`) covers the worst pre-registered mapping with margin. **Verified
to `< 3e-14` against the numeric root; closed form contributed by Codex.**

**`m_lo = 4` is a JUDGEMENT CALL and is recorded as one.** It is retained because it preserves a generous
pre-result non-enforcing region, as `[SCOPE §14, §25]` requires, and because **too tight a lower bound is a
failure that cannot be detected from inside the box**, whereas too loose only dilutes the primary metric.

> **The mandatory 0.5x/2x domain-expansion check `[SCOPE §14, §18]` probes LOCAL domain sensitivity around
> the chosen box. It does NOT prove that four decades was uniquely optimal, and nothing can** — there is no
> data-free criterion for "comfortably". A changed qualitative conclusion under expansion is **a finding to
> report, not a reason to re-pick the box.**

### Bracketing is a DESIGN TARGET, not a certification

`s_max` is designed so that one minimum attainable violation costs more than the largest objective swing
available anywhere in the domain. **This is a single-family, `w = 1`, in-isolation statement and does not
prove enforcement.** C0-05 stands: a sufficient criterion must compare every violating state against the
best feasible candidate, including other families' lower bounds and the unbalanced encoding's **negative
rewards**. Per D009(b) no threshold is claimed, so no certification obligation is triggered.

### Bias — the metric's central weakness, restated because it survives this decision

`rho = |A| / |Lambda|` is "*trivially manipulable by choosing how much uninteresting territory to include
on either side*" (`UNRESOLVED_DECISIONS.md` §U-04). **A derived rule removes the post-hoc route to that
manipulation; it does NOT make the metric box-independent.** `m_hi` and `m_lo` still set the denominator.

**MANDATORY REPORTING:** any write-up must report `m_hi`, `m_lo` and the resulting decade span **alongside**
`rho`, and state that `rho` is conditional on them.

**NO DIRECTION IS CLAIMED** for how either margin moves `rho`. An earlier draft argued that raising `m_hi`
dilutes the A-rate toward a shared value; **that claim is WITHDRAWN** — large-`s` convergence of the
*quadratic coefficient* `lambda_2 -> lambda_S` does **not** imply landscape, encoding, or A-rate
convergence. The unbalanced linear reward term survives at every `s`, and on the feasible inequality side
slack is identically zero while unbalanced is not.

### Explicitly NOT approved by D010

- Any numeric `rho`, `Delta_full`, `s_min`, `s_max`, or grid point.
- **Grid resolution or points-per-decade — that is U-05, still OPEN.** D010 fixes *extent* only.
- Any enforcement threshold (see D009(b)), or any claim that `s_max` certifies enforcement.
- Per-axis boxes. **A common cube is approved**, on minimality and H3-testability grounds; per-axis boxes
  were assessed as admissible and rejected, not as unsound.
- Any reopening of U-03, or any use of `Delta_full` as a normalizer.
- Execution of the box ADNYE record — that is **G3**, separately gated.

### MANDATORY CONDITIONING

Every downstream conclusion is **CONDITIONAL ON** the box rule alongside D004-D009, and specifically on
`m_hi` and `m_lo`. Because U-03 is not reparameterizable for the unbalanced encoding **in the small-`s`
regime** — `lambda_2 -> lambda_2/gamma` as `s -> 0`, returning to invariance as `s` grows — the box's
**lower** bound is where that non-invariance has physical content. This conditioning is **not** cosmetic.

Final decision:
**APPROVED — rule-first three-axis box: common cube `[s_min, s_max]` on all three axes with
`s_max = 10^(ceil(log10 rho)+1)`, `s_min = 10^(floor(log10 rho)-4)`, `rho = Delta_full/Lambda_ref`;
`Delta_full` expressly authorized as the rule's second input; `m_hi = 1` derived, `m_lo = 4` a recorded
judgement call; RULE ONLY, numbers are a G3 ADNYE record with two named inputs. 2026-08-24, Shivansh.
U-04 CLOSED.**

---

## D011 — Curvature-match sensitivity disposition (V-12)
Status: **APPROVED — NON-PRIMARY, COARSE COMPANION ONLY**

**Approved:** Shivansh, 2026-08-25. **Provenance:** direct human approval of Codex's exact recommendation
in session. This resolves the authority ambiguity left when the Scope Lock required a curvature-match
companion while D004 rejected Option 2 as a *primary* mapping. It does **not** reopen D004, D006, U-05, or
the Stage-1/Stage-2 protocol.

For each **inequality** family `j` only (sector and budget; cardinality remains the separate shared
`alpha` equality penalty), approve the required curvature-match sensitivity:

```
lambda_S,j^CM = s_j * Lambda_ref / v_j^2
lambda_1,j^CM = s_j * Lambda_ref / v_j
lambda_2,j^CM = s_j * Lambda_ref / v_j^2
```

Equivalently, within D004's approved parent family, `a^CM = 2` and
`Lambda_pen,j^CM = s_j*Lambda_ref/2`. Thus `lambda_2,j^CM = lambda_S,j^CM`: this is the
dimensionally valid translation of the Scope-Lock curvature-match anchor, **not** the superseded literal
`lambda_S = kappa^2/2`.

At `h = -w*v_j`, the local comparison is
`[zeta_CM(-w*v_j) - P_slack(-w*v_j)] / Lambda_ref = s_j*w > 0` for `s_j,w > 0`.
This known directional bias is mandatory conditioning and must be reported with the companion pass. It is
a local penalty-gap statement only; it does not predict, establish, or bound any A/B/C result.

### Explicit limits

- This is a **non-primary**, Scope-mandated companion sensitivity. It must never replace, select against,
  or be reported as an alternative primary result to D006's frozen R2 mapping.
- D006's separately predeclared `r in {0.5,2}` sensitivities remain required and unchanged; D011 is an
  additional, distinct curvature-match companion, not an `r` member.
- The pass is required on a **coarse subgrid**, but its exact extent/resolution remains to be predeclared
  before execution. No result may choose or alter that extent.
- No numeric coefficient, `Lambda_ref`, box, grid resolution, encoded-QUBO result, or G2+ work is approved.

Final decision:
**APPROVED — the displayed `a=2`, `Lambda_pen=s*Lambda_ref/2` mapping only as the required non-primary
coarse curvature-match sensitivity for inequality families; D006 primary and `r={0.5,2}` sensitivities
unchanged. 2026-08-25, Shivansh.**

> **NOTATION CLARIFICATION — 2026-08-25, Codex.** D010 used bare `rho` both for its box-rule input
> `Delta_full/Lambda_ref` and, elsewhere in the same decision, for the primary A-rate. They are different
> dimensionless quantities. This is a symbol-completeness repair, not a change to D010's rule, inputs,
> margins, metric, or approval. Henceforth **`rho_box = Delta_full/Lambda_ref`** is the D010 box input and
> **`rho_E^exact = |{grid points classified A for encoding E}|/|Lambda|`** is the primary metric. Bare
> `rho` is forbidden in current/frozen specification text. D010's original unqualified notation above is
> retained as the historical approved record.

---

## D012 — Grid resolution and log-spacing (U-05)
Status: **APPROVED — PRIMARY-GRID RULE ONLY**

**Approved:** Shivansh, 2026-08-25. **Provenance:** direct human approval in session of the exact
U-05 recommendation and R-U05-1. This closes U-05 only. It does not approve the ADNYE output contract,
which remains a separate unapproved draft and a W0b blocker.

For each of the three D002 sweep axes `(s_card, s_sector, s_budget)`, the primary grid uses **base-10
logarithmic spacing with `P = 10` log intervals per decade**, including both endpoints. Thus, for a span
of `D` whole decades on an axis, `N_axis = 10*D + 1`; D010 determines the later numeric bounds and hence
whether the realized span is five or six decades, but does not alter this density rule.

**R-U05-1 accepted:** any later refinement must be a separately declared and additionally reported pass;
it must never replace, silently supersede, or be selected in preference to the approved primary-grid
pass. No observed result may choose the refinement.

### Explicit limits

- This does not choose a numeric grid point, execute a sweep, or authorize G2+ work.
- It does not resolve V-14's 0.5x/2x expansion interpretation, the required D011 coarse-subgrid extent,
  or any other sensitivity-pass extent; each remains a pre-execution commitment.
- It does not certify that this resolution resolves H1 or any other feature; `P=10` is a pre-result
  design convention, not an outcome claim.

Final decision:
**APPROVED — `P=10` base-10 logarithmic intervals per decade on all three axes, endpoints included, and
R-U05-1 requiring any later refinement to be separately declared and additionally reported, never a
replacement. U-05 CLOSED. 2026-08-25, Shivansh.**

---

## D013 — Conditional constraint-ablation rule (U-12)
Status: **APPROVED — CONDITIONAL, NON-PRIMARY FOLLOW-UP RULE ONLY**

**Approved:** Shivansh, 2026-08-25. **Provenance:** direct human approval in session of the exact U-12
revision-3 rule. **Memo:** `research/decisions/U12_DECISION_MEMO.md` revision 3 (supporting analysis; this
record is authoritative). U-12 is **CLOSED**. This decision fixes a prospective follow-up rule only; it
does not create an instance, execute an ablation, alter the primary `CSB` comparison, or authorize G2+.

### Fixed conditions and coordinates

For each independently eligible instance, the only conditional constraint conditions are exactly:

```
F_C   = {x in {0,1}^20 : sum_i x_i = K}
F_CB  = {x in {0,1}^20 : sum_i x_i = K and p^T x <= B}
F_CS  = {x in {0,1}^20 : sum_i x_i = K and n_j(x) <= C for every sector j}
F_CSB = {x in {0,1}^20 : sum_i x_i = K and p^T x <= B and n_j(x) <= C for every sector j}
```

Use D008's canonical `Lambda_ref`, D010's per-axis domain rule, and D012's grid density **only on each
condition's active penalty axes**. Every inactive penalty is identically zero and omitted from that
condition's grid; it is not an additional sampled or duplicated dimension. No per-condition normalizer,
box, penalty axis, condition, or selective repetition is authorized.

### Mechanical firing rule

After the predeclared all-three-condition (`CSB`) core pass is complete, define for each eligible instance
`i` and each D006 mapping `r in {0.5, 1, 2}`:

```
Delta_i(r) = rho_slack,i,r^exact - rho_unbalanced,i,r^exact
```

where each rate is the exact finite-grid A-rate under the then-approved U-14/U-17 classification definitions.
The rule fires iff at least one of the three values is exactly zero **or** they do not all have one strict
sign. It does not fire only for `(+,+,+)` and `(-,-,-)`. There is no numerical tolerance in this rule.

If it fires, run all and only `C`, `CB`, `CS`, and `CSB` and report them as a triggered H3 follow-up, never
as selectively pooled primary confirmation. If it does not fire, run none. U-14 and U-17 remain separately
unresolved prerequisites to applying the classification definition; D013 does not choose either one.

### Required pass package and pre-declaration

Every fired condition carries the complete applicable package: D006 primary `r=1` and its `r={0.5,2}`
sensitivities for every active **inequality** family; D011's non-primary curvature-match companion for each
such family on its predeclared coarse subgrid; and V-14's expansion pass on active dimensions under the
single V-14 reading fixed before any core result. Cardinality is an equality penalty and has no invented
D006 `r` analogue. D013 does not set D011's coarse extent or the V-14 reading; both remain mandatory
pre-execution commitments and must predate all relevant core results.

**R-U12-1 accepted:** no trigger outcome, core result, or ablation result may change the trigger, subset,
coordinates, normalizer, pass package, or reporting disposition. Any change requires a new dated human
approval that states the result already observed.

### Explicit limits

- This does not authorize Stage-2 generation, change its protocol, or presume any Stage-2 instance exists.
- It does not treat D011's known-biased companion as a trigger input.
- It does not amend D006, D008, D010, D011, D012, V-13, or V-14.
- It does not establish H3; it makes a bounded conditional test auditable.

Final decision:
**APPROVED — the exact four-condition, exact-sign-trigger, active-axis-coordinate, full-pass-package rule
above, with R-U12-1. U-12 CLOSED. 2026-08-25, Shivansh.**

---

## D014 — ADNYE output contract (charter §5 field 5)
Status: **APPROVED — OUTPUT-PROVENANCE CONTRACT FOR THE TWO ADMITTED PROSPECTIVE RECORDS**

**Approved:** Shivansh, 2026-08-25. **Provenance:** direct human approval in session of
`research/decisions/ADNYE_OUTPUT_CONTRACT_MEMO.md` **revision 6**. An earlier prospective approval was
explicitly retracted before this approval; this is the controlling approval. The supporting contract's
recommendation/revision history remains retained, but this record is authoritative.

D014 supplies the previously missing charter §5 field-5 rule for **only** D008's numeric `Lambda_ref`
record and D010's numeric three-axis box record. It completes their *declaration* of an output
location/content-hash scheme. It does not execute either record, create `research/adnye/`, create a
validator, waive any G3 stop condition, or authorize G2+ work.

### Approved contract

The location is `research/adnye/`. The branch-conditional whitelist is exactly:

```
resolved:     ADNYE-001_Lambda_ref.json + ADNYE-001_Lambda_ref.json.sha256
              ADNYE-002_s_domain_box.json + ADNYE-002_s_domain_box.json.sha256
stopped_zero: ADNYE-001_Lambda_ref.json + ADNYE-001_Lambda_ref.json.sha256
```

No other file, extension, subdirectory, or name is permitted. `Lambda_ref = 0` is the D008 stopped-zero
branch and forbids ADNYE-002. `Delta_full` is serialized exactly once as ADNYE-001 `delta_full`; ADNYE-002
references that field and ADNYE-001's sidecar-verified record digest and may not serialize a duplicate.

The D014 contract is the exact closed-schema, source-attested, two-digest, and chronology scheme in
`ADNYE_OUTPUT_CONTRACT_MEMO.md` revision 6: unknown/missing/duplicate JSON keys and invalid shapes fail;
numbers are finite; dates/UTC instants are valid; sidecars hash canonical UTF-8 JSON; an intake captures
the exact D008/D010 decision section with a source-file digest and its digest; the record separately carries
the exact permitted UTF-8 governing-rule string and digest; and date-only decision provenance fails closed
on same-day resolution. The D008/D010 strings, schemas, dependency edges, candidate reporting, and validator
requirements are exactly those stated in the approved revision-6 contract, not an implementer-selected
variant.

Before either G3 record is accepted or cited, the required `research/audit/validate_adnye_output.py` must
exist and pass against that contract. This is an implementation prerequisite, not code created or approved
by D014. Later output records and downstream artifacts must satisfy M10/V-13; D014 narrows neither.

### Explicit limits

- Both ADNYE records remain **admitted, not executed**; their numeric values are not approved.
- `Lambda_ref = 0` remains a G3 stop condition, never a substituted value.
- This does not authorize an encoding, QUBO, result artifact, experiment, W0b charter freeze, or G2+ work.
- This removes the field-5 W0b blocker only. U-14, U-17, required Gate-1 artifacts, independent
  reconstruction, and a later human Gate-1 exit decision remain outstanding.

Final decision:
**APPROVED — ADNYE Output Contract revision 6 for D008/D010's field-5 output location/content-hash scheme,
with its branch-conditional whitelist, single-source `Delta_full`, closed schemas, source-attested decision
snapshots, exact rule strings, two digest fields, and conservative date rule. 2026-08-25, Shivansh.**

---

## D015 — Numerical comparators for encoded ties and original optimality (U-14)
Status: **APPROVED — TWO-COMPARATOR RULE, PRIMARY AND FIXED DIAGNOSTICS**

**Approved:** Shivansh, 2026-08-25. **Provenance:** direct human approval in session of
`research/decisions/U14_DECISION_MEMO.md` **revision 6**, after its bounded external final-delta audit
attested SHA-256 `b55ada2c44bcb8eeca8e9fc7bf7e2e212edca48628b33df60b2aca7926a0b7c5`, 494 lines, and returned
`CLEAN`. The supporting memo and review history remain retained; this record is authoritative.

D015 closes U-14. It fixes two distinct numerical comparators before results exist:

1. **Encoded-energy tie membership.** Use the memo's canonical unshifted IEEE-754 binary64 primitive
   ledger, round-to-nearest ties-to-even, no FMA/contraction/reassociation, fixed ordered transcript,
   exact auxiliary-minimizer domain `C_E`, and fail-closed finite-intermediate rule to form `T_E`.
   State-independent QUBO constants are retained/restored in that comparison ledger. Decode and deduplicate
   only after `T_E` is formed.
2. **Original-objective optimality.** Use the separate, encoding-blind original-objective service to form
   `OPT_f`; encoded energy and encoding identity are not inputs to that service. `T_E` never decides
   `OPT_f`, and `OPT_f` never decides encoded-energy membership.

For each comparator, the primary tolerance is exactly the revision-6 binary64 evaluation of

```
tau_c(y, y') = c * 2^-52 * (Lambda_ref + max(|y|, |y'|))
```

with primary `(c_H, c_f) = (2048, 2048)`. The non-primary, additionally reported one-factor diagnostic
configurations are exactly `(1024,2048)`, `(4096,2048)`, `(2048,1024)`, and `(2048,4096)`; none may select,
replace, or reinterpret the primary result.

`Lambda_ref` is parsed from the sidecar-verified D014 `ADNYE-001_Lambda_ref` record by correctly rounded
binary64 conversion under round-to-nearest ties-to-even. Every dependent result records both that ADNYE
record digest and, separately, the hash of this approved D015 decision record required by V-13/M10. Neither
digest substitutes for the other, and an in-memory recomputation/substitution is forbidden.

The memo's exact-rational oracle transcript is a diagnostic, not a replacement classifier. A replay-detected
departure from the ledger is an implementation defect requiring correction and rerun. If replay conforms but
the oracle predicate disagrees, acceptance stops and the numerical-rule conflict requires a dated human
resolution; no result may select a multiplier or replacement rule.

**R-U14-1 accepted:** observed tie rates, A/B/C rates, oracle outcomes, or inconvenient conclusions may not
change either comparator, primary multiplier, diagnostic ladder, ledger, transcript, or mismatch disposition.
Any change requires a new dated human approval that discloses the result already observed.

### Explicit limits

- This approves no numeric `Lambda_ref`, QUBO, data reconstruction, ground-truth computation, ADNYE output,
  certification run, experiment, or W0b charter freeze.
- It does not decide U-17's mixed-tie partition, secondary estimands, or denominators. U-17 must consume the
  D015 two-comparator boundary and is the only remaining Gate-1 decision.
- It does not amend D007–D014, D006's mappings, D010's box, D011's companion, D012's grid, or D013's trigger.

Final decision:
**APPROVED — U-14 revision 6's canonical binary64/ledger and oracle rule; separate `T_E` and encoding-blind
`OPT_f` comparators; primary `(c_H,c_f)=(2048,2048)` and its four stated non-primary diagnostics; separate
D014 ADNYE and D015 decision-hash provenance; fail-closed mismatch dispositions; and R-U14-1. U-14 CLOSED.
2026-08-25, Shivansh.**

---

## D016 — Mixed decoded tie-set semantics and reporting (U-17)
Status: **APPROVED — PRIMARY PARTITION AND FIXED DIAGNOSTICS**

**Approved:** Shivansh, 2026-08-25. **Provenance:** direct human approval in session of
`research/decisions/U17_DECISION_MEMO.md` revision 2 after its bounded independent audit attested
SHA-256 `2794f9074eb34905e530c9e478558cddf13820ee17f21d1fcb2b0721d3e6f2d1`, 183 lines, and returned
`CLEAN`. The supporting memo and review history remain retained; this record is authoritative.

D016 closes U-17 and consumes, without modifying, D015's two comparators. At each encoding/grid point,
form the raw encoded-energy tie set `T_E` only through D015, then decode and deduplicate it to
`X_E = {decode(z) : z in T_E}`. All labels, primary classification, and fractional denominators operate on
the nonempty finite set of distinct decoded portfolios `X_E`; raw `|T_E|` is separately reported and may be
symbolic where D015 permits.

For every `x in X_E`, assign exactly one atomic label:

```
A_x = D015 OPT_f(x)                    # encoding-blind feasible-optimal predicate
B_x = feasible(x) and not A_x
C_x = not feasible(x)
```

The classifier's only runtime inputs are decoded `x`, `f*`, and the original feasibility predicate; under
D015's immutable encoding-blind configuration, those inputs determine `OPT_f`. It receives neither encoded
energy nor encoding identity. Its primary partition is exactly:

```
if EXISTS x in X_E with C_x:      C
elif FOR ALL x in X_E, A_x:       A
else:                             B
```

This is mutually exclusive and exhaustive for every nonempty finite `X_E` and preserves Scope §16's
universal-A rule. It also fixes feasibility as `1 - I_C^exist`.

For each primary D015 comparator pair, report `|T_E|`, `|X_E|`, the atomic-label set, the primary label,
the mixed decoded-label census, `I_C^exist`, `I_C^univ`, and the complete decoded-portfolio fractions
`p_A`, `p_B`, and `p_C`, each with denominator `|X_E|`. Aggregate fractional rates are arithmetic means of
their per-grid-point values and never partial credit toward the primary A-rate. Repeat this reporting under
each of D015's four one-factor comparator configurations as non-primary diagnostics only; D013's trigger
consumes primary classification only. Every dependent result retains the D014 ADNYE-record digest and the
separate governing D015 and D016 decision-record hashes required by V-13/M10; none substitutes for another.

**R-U17-1 accepted:** no observed raw multiplicity, tie composition, A/B/C rate, D013 trigger outcome, or
sensitivity result may change the atomic labels, primary partition, decoded denominator, estimands, or
reporting disposition. Any change requires a new dated human approval that discloses the result already
observed.

### Explicit limits

- This approves no QUBO, numeric data value, ADNYE output, G2+ work, certification run, experiment, W0b
  charter freeze, or Gate-1 exit.
- It does not amend D007–D015, including D015's numerical comparators or D013's trigger.
- It closes the final Gate-1 scientific decision only; W0b and the W2–W5 frozen-specification,
  verification, reconstruction, and human-exit work remain required.

Final decision:
**APPROVED — U-17 revision 2: consume D015's separate `T_E` and `OPT_f` comparators unchanged; assign
atomic `A_x`, `B_x`, and `C_x` over distinct decoded portfolios; use `exists C -> C`, else `all A -> A`,
else `B` as the primary partition; require the stated reporting and D015 one-factor diagnostics; and accept
R-U17-1. U-17 CLOSED. 2026-08-25, Shivansh.**

---

## Process Approval — W0b, Gate-1 Charter Freeze

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-25. **Provenance:** direct human approval in session:
“Approve W0b: freeze the current `research/00_specifications/GATE_1_CHARTER.md` as the authoritative
Gate-1 charter, incorporating approved decisions through D016. This authorizes only W2–W5 Gate-1 artifact
work; it does not authorize G2+, ADNYE execution, or Gate-1 exit.”

**Attestation:** the reviewed pre-promotion charter was 164 lines, SHA-256
`1e9f38d995efd6819657ab007a439561d6f659c1bc4b74c5723437873555e864`. Its promotion changed only the
authority/status wording and resulting post-promotion artifact is 169 lines, SHA-256
`21f4e9752c14cbc53361e3dda2073a06386c4c94a55ed67184af5ca180a2eb13`.

**Decision:** freeze `research/00_specifications/GATE_1_CHARTER.md` as the authoritative Gate-1 charter
through D016. The charter is authoritative for the approved mathematical rules, interfaces, deferred-record
contract, validation obligations, and Gate-1 exit criteria it states. Any substantive amendment requires a
new dated human approval.

**Scope:** this governance approval authorizes W2–W5 only: the frozen mathematical specification, bounded
verification, propagation/Gate-1 logging, and independent reconstruction/exit package. It does not add or
amend a scientific decision and does not authorize canonical-data assembly (G2/U-07), ADNYE execution,
ground-truth computation, encoding, certification, experiments, conclusions, or Gate-1 exit.

**Current gate boundary:** Gate 1 remains active until the charter's Section 8 exit criteria are met and a
separate human Gate-1 exit approval is recorded.

---

## Process Approval — Gate-1 Exit

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-25. **Provenance:** direct human approval in session of the exact
post-review package:

> Approve Gate-1 exit based on the W0b charter and the post-review W2–W5 package:
> `FROZEN_MATH_SPEC.md` SHA-256
> `e963a7e10ba797a373ef50d585bec1056ee82f7274d762b7c8bab9a817062900`;
> `verify_gate1_math.py` SHA-256
> `bd9bfd069aae4358695cb62a9281dd9d8bd29a110ee0e985abdf6198f7baa801`; and
> `GATE_1_RECONSTRUCTION.md` SHA-256
> `60e9c7ce82d258b735a2ce2f913fbf68161b2f517e28219cdbb70ebb424218be`.

**Review basis:** Claude independently attested those exact bytes, ran all 11 standing verifiers plus
`verify_gate1_math.py`, and returned `CLEAN` in its 2026-08-25 17:17:07 IST bounded delta recheck.

**Decision:** Gate 1 is closed. The frozen charter, decisions through D016, and the approved W2–W5
artifact package are accepted as the Gate-1 exit package.

**Scope:** authorize **G2 / U-07 canonical-data reconstruction only**. This authorization permits work to
define and build the canonical ticker-keyed, typed, unit-specified input assembly required by the frozen
specification. It does not resolve U-07 in advance of that work.

**Explicit limits:** this approval does **not** authorize ADNYE execution, G3 original-problem ground truth,
QUBO construction, encoded certification, experiments, conclusions, or any later gate. D014's prospective
records remain admitted and unexecuted. Per Shivansh's instruction accompanying this approval, no G2 work
is started by this record; the next action is an explanatory handoff.

---

## Process Approval — G2 / U-07 Canonical-Input Package

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-25. **Provenance:** direct human approval in session:

> Approved, 2026-08-25: authorize the seven-item G2/U-07 canonical-input package as stated, including retained
> CSV sources, no re-download, limited source-fidelity status, cell-17 price vector as evidence-based rather
> than Scope-entailment, ticker-keyed sector labels, D007/digest/alpha/D005 disclosures, and Claude assembly
> with independent Codex audit. This does not close U-07 or authorize G3+ work.

**Decision:** approve the seven-item source/price/label package stated in `progress.md`
[2026-08-25 18:26:12 IST] and relayed in `codex_messages/to_claude.md`
[2026-08-25 18:28:56 IST]. In particular: retain the pinned `mu.csv` and `Sigma.csv` bytes without a
re-download; record their limited source fidelity and approved date/window evidence; select submission
cell 17's synthetic price vector by its stated G2 evidence rather than as a Scope-entailment; use the
ticker-keyed sector labels and representation; carry D007 and all required disclosure/digest boundaries;
and keep Claude as assembler with Codex independent auditor.

**Scope:** this authorizes only the approved G2 provenance record and canonical-instance assembly. It
expressly authorizes neither a source substitution nor a re-download.

**Explicit limits:** this does **not** close U-07; approve or assume a numeric `v_ref` value, including
`(1,1,5)`; authorize ADNYE execution, G3 ground truth, QUBO construction, certification, experiments,
conclusions, or a later gate. D005 conformance must be reported after assembly and independently audited.
U-07 closure remains a separate, later direct human approval.

---

## Process Approval — U-07 Closure

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-25. **Provenance:** direct human approval in session:

> Approved, 2026-08-25: close U-07. I accept the audited G2 canonical-input assembly and provenance record,
> including the retained CSV return-statistic bytes, ticker-keyed join, limited source fidelity, approved
> evidence-based cell-17 synthetic price vector, ticker-keyed sector labels, D007 conformance,
> calendar-derived (not observed) terminal-session qualification, and tested D005 result (1,1,5). This
> closes U-07 only; it does not authorize G3 or any later gate.

**Review basis:** Claude's owned provenance/assembly package in `research/canonical/`, including its
six-file digest manifest; Codex's independent delta audit
`research/audit/G2_CODEX_DELTA_AUDIT.md` (SHA-256
`0d7e884ec10a76e9d1d86ce7c5eb4b273822eaba606ca15085470e5422ac0d46`), which passed its independent
source/cell-anchor, calendar, manifest, deterministic-rebuild, D005-integrity, and regression checks.

**Decision:** U-07 is **CLOSED**. The G2 canonical Stage-1 input assembly is accepted on the audited
bytes. The D005 rule's instance result is now verified as `(v_card, v_sector, v_budget) = (1,1,5)`,
tested after the evidence-based price-vector approval rather than assumed before it.

**Propagation note:** earlier records that describe the numeric D005 triple, the date window, or the
price-dependent support counts as pending canonical-data verification were accurate before G2 completed.
They are superseded as current status by this closure record; their historical wording is intentionally
preserved.

**Explicit limits:** this closes **U-07 only**. It does not authorize G3 original-problem ground truth,
ADNYE execution, the D010 domain-box record, QUBO construction, certification, experiments, conclusions,
or any later gate. A separate dated authorization is required for each later-gate action.

---

## Process Approval — Gate 3 / ADNYE-001 and ADNYE-002 bounded execution

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-25. **Provenance:** direct human reply in session, “continue,” accepting
the immediately preceding, explicitly scoped Codex proposal:

> Approved 2026-08-25: start Gate 3, limited to D014 ADNYE-001 and ADNYE-002, including their validator,
> official outputs, independent audit, and necessary append-only logs. Authorize the Claude/Codex ownership
> split above. This excludes G4+, QUBO construction, certification, experiments, and conclusions.

**Decision:** Gate 3 is authorized and starts only for the sequential D014 execution of **ADNYE-001**
(`G3.compute_Lambda_ref`) and, only after it is sidecar-verified and independently accepted with nonzero
`Lambda_ref`, **ADNYE-002** (`G3.exit.resolve_box`). The D008/D010/D014 rules and all their stop
conditions remain binding. `Lambda_ref = 0` is a stop condition: record the stopped-zero branch and do not
produce ADNYE-002 or a substitute value.

**Ownership and review:** Claude owns official resolver and `research/adnye/**` output production; Codex
owns `research/audit/validate_adnye_output.py` and the independent audit/replay material. Each record must
be independently reviewed before it is accepted or used by its successor. The canonical G2 evidence and
`previous_work/**` remain read-only.

**Explicit limits:** this approval permits neither any G4/QUBO construction nor certification, experiment,
result, conclusion, or any later-gate work. It does not authorize re-selection of D008 transparency values,
patching a G3 stop condition, or unreviewed use of an ADNYE output.

### Chronology clarification — 2026-08-25, Codex (operational; no scientific decision changed)

The preceding approval's review language is read under the binding D014/FROZEN_MATH_SPEC chronology:
**ADNYE-002 executes after a sidecar/schema verification of a nonzero ADNYE-001, not after final
acceptance of the complete resolved branch.** D014's full validator correctly requires both record pairs
before it can accept that resolved branch; requiring final acceptance before emitting ADNYE-002 would make
the approved chronology impossible. A preflight may verify ADNYE-001's closed schema, source capture,
exact rule, and canonical sidecar, but cannot accept or cite it. Final branch acceptance occurs only after
ADNYE-002 is present and the full D014 validator and independent audit pass. The `Lambda_ref = 0` stopped
branch remains unchanged and forbids ADNYE-002.

---

## Process Approval — Gate 3 bounded execution: CONTROLLING AUTHORIZATION TEXT (correction)

**Status: APPROVED — this record supplies the controlling wording for the immediately preceding
Gate-3 approval record; it does not create a second authorization.**

**Approved:** Shivansh, 2026-08-25. **Provenance:** direct human authorization issued verbatim to Claude
in session, recorded here by Claude on receipt:

> Approved 2026-08-25: start Gate 3, limited to (a) enumeration of F and {0,1}^20 and computation of f*,
> X*, Lambda_ref, and Delta_full, with f*/X* recorded in a named artifact outside research/adnye/; (b) D014
> ADNYE-001 and ADNYE-002, their validator, official outputs, and independent audit; and (c) necessary
> append-only logs. Claude owns research/adnye/** and the ground-truth artifact; Codex owns new
> research/audit/** G3 validation material, with the existing frozen verifier scripts unchanged absent a
> corrective task. Canonical inputs stay read-only. This excludes G4+, QUBO construction, certification,
> experiments, and conclusions.

**Why this record exists.** The preceding record, *Process Approval — Gate 3 / ADNYE-001 and ADNYE-002
bounded execution*, quotes an **earlier draft** of this authorization. That draft was Claude's proposed
text; Shivansh then issued the corrected text above, which is what Claude received and is acting on. Both
records describe the same single dated authorization. **Neither record is rewritten** — the historical
entry stands as appended, and this later entry supplies the controlling wording, per the append-only rule.

**The two texts differ in exactly two ways, both wider here:**

1. **Clause (a) exists only in the controlling text.** It authorizes enumeration of `F` and `{0,1}^20` and
   computation of `f*`, `X*`, `Lambda_ref`, and `Delta_full`, with `f*`/`X*` recorded in a named artifact
   **outside** `research/adnye/`. This is required: D014's whitelist permits no file in `research/adnye/`
   beyond the two record/sidecar pairs, and ADNYE-001's closed schema is exactly the §4.2 common fields
   plus `{"value", "delta_full", "transparency_candidates"}` — so `f*` and `X*` cannot be carried by an
   ADNYE record and need their own location. `FROZEN_MATH_SPEC.md` §8 assigns `f*` and the enumeration of
   `F` and the full space to G3.
2. **The ownership clause carries an explicit carve-out**: Codex owns **new** `research/audit/**` G3
   validation material, with the **existing frozen verifier scripts unchanged absent a corrective task**.
   The 12 frozen Gate-1 closure verifiers live in that directory and are not transferred by this approval.

**Everything else is identical** in both texts: ADNYE-001 and ADNYE-002 under D014; their validator,
official outputs, and independent audit; necessary append-only logs; the Claude/Codex ownership split;
canonical inputs read-only; and the exclusion of G4+, QUBO construction, certification, experiments, and
conclusions. All D008/D010/D014 rules and stop conditions remain binding, including `Lambda_ref = 0` as a
stop condition that is never substituted or patched, and the rule that ADNYE-002 follows only a
sidecar-verified, independently accepted, nonzero ADNYE-001.

**Named artifact under clause (a):** `research/ground_truth/G3_GROUND_TRUTH.json`, produced by
`research/ground_truth/compute_g3_ground_truth.py`. Both are Claude-owned under this approval.

**Explicit limits:** unchanged from the preceding record. This authorizes no G4/QUBO construction,
certification, experiment, result, conclusion, or later-gate work; no re-selection of D008 transparency
values; no patching of a G3 stop condition; and no unreviewed use of an ADNYE output. Recorded by Claude,
2026-08-25.

---

## Process Approval — Gate 3 exit

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-25. **Provenance:** direct human approval in session:

> Approved 2026-08-25: Gate 3 exit is approved based on the accepted exit-readiness packet. This does not authorize G4 or later work.

**Decision:** Gate 3 is **CLOSED** on the accepted basis documented in
`research/audit/G3_EXIT_READINESS_PACKET.md`. This records the gate-exit decision only; it does not alter
the accepted G3 ground-truth or D014 record bytes, their sidecars, or their historical decision-register
intake captures.

**Explicit limits:** Gate 4 and every later gate remain unauthorized and unstarted. This approval does not
authorize grid construction, coefficients, QUBOs, certification, experiments, results, conclusions, or any
other G4+ object. A separate dated human authorization must name the next permitted scope.

---

## Process Approval — Gate 4 bounded encoding formulation and conformance

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-25. **Provenance:** direct human approval in session:

> Approved 2026-08-25: start Gate 4, limited to (a) generating the frozen primary coordinate and binary64 coefficient ledgers from the accepted canonical and ADNYE inputs; (b) implementing the objective, residual, slack, and unbalanced encoding modules and their explicit QUBO formulations, with the required separation—shared residual definitions only, no shared penalty helper; (c) implementing G4 conformance checks, including independently written hard-feasibility versus residual validation (V-18), formula/ledger conformance, and feasible-state penalty behavior. Establish an explicit producer and independent-review ownership split before substantive work.
>
> This excludes G5 exact ground-state certification, encoded tie-set computation, A/B/C classification, grid sweeps, experiments, domain-expansion or curvature-companion execution, results, and conclusions. previous_work/**, research/canonical/**, research/ground_truth/**, and research/adnye/** remain read-only absent a corrective task.

**Decision:** Gate 4 is started only for the three bounded items above. The named Gate-4 record is this
approval; produced coordinate/coefficient ledgers, implementation modules, and conformance evidence are
working artifacts subject to independent review, not G4 acceptance by themselves.

**Ownership and review:** Codex is the producer for the bounded G4 work. Claude is the independent reviewer
for any G4 formulation/conformance artifact; Codex may not self-accept it or claim a G4 exit. The historical
G2/G3 evidence remains read-only as stated in the approval.

**Explicit limits:** This approval authorizes no G5 exact certification, raw encoded tie-set computation,
decoded A/B/C classification, grid sweep, sensitivity/expansion execution, experiment, result, conclusion,
or later-gate work. Existing frozen verifier scripts remain unchanged unless a separately authorized
corrective task names them.

## Process Approval — Gate 4 ownership amendment: 0xalpha as producer for the bounded F3 repair

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-25 (recorded 22:23:04 IST). **Provenance:** direct human approval in
session, across two messages:

> to be honest I was thinking of reducing you to the verifier/planner/orchestrator role for the next 2 hours till GPT's limit resets, till then the heavy lifting can be done by 0xalpha

and, selecting the second of two options put to him — the first retaining Codex as producer, the second
reading "0xalpha produces the evaluator, I verify — needs a dated line in DECISIONS.md naming the new
split, since the authorization says to establish ownership *before* substantive work":

> yeah let's go with the second one

**Decision:** For bounded Gate-4 work only, and for approximately the next two hours from the time
recorded above, the agent `0xalpha` is a Gate-4 **producer** alongside Codex. Claude is **verifier,
planner, and orchestrator** and performs no producer work in that window.

**Scope of the amendment.** This changes *who* may produce within the already approved Gate-4 bounded
scope. It does **not** widen that scope, and every exclusion in *Process Approval — Gate 4 bounded
encoding formulation and conformance* stands unchanged: no G5 exact certification, encoded tie-set
computation, A/B/C classification, grid sweep, sensitivity/expansion execution, experiment, result,
conclusion, or later-gate work. `previous_work/**`, `research/canonical/**`, `research/ground_truth/**`,
and `research/adnye/**` remain read-only.

**Separation of duties preserved.** No agent may review its own production. `0xalpha` currently holds an
independent Gate-4 review task; any artifact it produces under this amendment must be reviewed by Claude,
and its own outstanding review verdict remains a separate reviewer-side product. Claude may not produce
Gate-4 artifacts and then verify them. Neither producer may self-accept or claim a Gate-4 exit.

**Occasion.** The immediate producer task is the canonical `FROZEN_MATH_SPEC.md` §5.2 `H_E` evaluator,
absent from the delivered Gate-4 package (Claude review finding F3). Recording this ownership line
discharges the parent authorization's requirement to establish an explicit producer/independent-review
split before substantive work.

**Explicit limits:** This is a process and ownership record only. It approves no scientific content,
advances no gate, and creates no Gate-5 authority. Gate 5 remains unauthorized and unstarted.

## Correction — Gate 4 ownership amendment: F3 producer is Grok 4.6, not 0xalpha

**Status: APPROVED — supersedes the producer assignment in the immediately preceding record.**

**Approved:** Shivansh, 2026-08-25 (recorded 2026-08-25 22:38:53 IST). **Provenance:** direct human approval in session:

> btw I have grok 4.6 as well on limited usage, so it can do something in parallel while [...] 0xaplha performs the checklist

followed, on being shown that 0xalpha's checklist ends in "Append review verdict to to_codex.md and
progress.md" and that a reviewer of record cannot then produce the same gate's repair:

> yeah please do it

**Correction.** The preceding record named `0xalpha` as producer for the bounded F3 repair. That
assignment is **withdrawn**. `0xalpha` is the Gate-4 **independent reviewer** and is completing a review
checklist ending in a filed verdict; it produces no Gate-4 artifact. **Grok 4.6** is the Gate-4 producer
for the bounded F3 repair. Claude remains verifier/planner/orchestrator and produces nothing.

Everything else in the preceding record stands unchanged: the bounded Gate-4 scope and all its exclusions,
the read-only status of `previous_work/**`, `research/canonical/**`, `research/ground_truth/**`, and
`research/adnye/**`, the rule that no agent reviews its own production, and the prohibition on any producer
self-accepting or claiming a Gate-4 exit. Gate 5 remains unauthorized and unstarted.

**Concurrency directive.** Two agents now work in parallel. To prevent a lost append on the shared
append-only logs, Grok writes its handoff to `grok_messages/to_claude.md` and does **not** write to
`progress.md`, `claude_messages/**`, or `codex_messages/**`. Claude folds that handoff into `progress.md`.
`0xalpha` retains its existing instruction to append its verdict directly.

**Explicit limits:** process and ownership record only. It approves no scientific content, advances no
gate, and creates no Gate-5 authority.

## Correction — Gate 4 ownership: Laguna 2.1 succeeds Grok 4.6 as producer for the F3 finish

**Status: APPROVED — supersedes the producer assignment in the two preceding records.**

**Approved:** Shivansh, 2026-08-25 (recorded 2026-08-25 23:01:56 IST). **Provenance:** direct human approval in session:

> yeah so an update, grok's limit hti mid usage, so I never got an output at all, but the good part is that I can start another 0xalpha session or Laguna s 2.1 session as epr what you recommend

followed, on being shown that Grok's artifacts were in fact on disk and verified bit-exact, that three
unfinished edits remained, and that a second `0xalpha` session would reintroduce the producer/reviewer
conflict:

> yeah please write the prompt for laguna s 2.1

**Correction.** Grok 4.6 completed the substantive F3 deliverable — `src/g4/energy.py`, verified by Claude
at exact binary64 equality against an independent §5.2 transcription — but hit its usage limit before
finishing its evidence script, provenance, and handoff. **Laguna 2.1** is now the Gate-4 producer for the
remaining bounded work: the three unfinished edits and review findings F1, F2, and F5. `0xalpha` remains
the independent reviewer and produces nothing. Claude remains verifier/planner/orchestrator and produces
nothing. Codex remains the original G4 producer, paused.

Everything else stands unchanged: the bounded Gate-4 scope and all exclusions, the read-only status of
`previous_work/**`, `research/canonical/**`, `research/ground_truth/**`, and `research/adnye/**`, the rule
that no agent reviews its own production, and the prohibition on any producer self-accepting or claiming a
Gate-4 exit.

**Concurrency directive.** Laguna writes its handoff to `laguna_messages/to_claude.md` only, and not to
`progress.md`, `grok_messages/**`, `claude_messages/**`, or `codex_messages/**`. Claude folds it in.

**Explicit limits:** process and ownership record only. It approves no scientific content, advances no
gate, and creates no Gate-5 authority. Gate 5 remains unauthorized and unstarted.

## Process Approval — V-14 affordability disposition: visible reduction, never a cheaper reading

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-26 (recorded 2026-08-26 00:33:39 IST). **Provenance:** direct human approval in session. The
text put before him, verbatim from Claude's staged recommendation:

> if the honest V-14 reading proves unaffordable, you declare it and *then* declare a bounded reduction
> visibly, rather than picking a cheaper reading. That's the more expensive path and I've written it as
> the default.

His approval:

> you have my nod for the same too

**Decision.** Should the V-14 domain-expansion reading, once chosen, prove computationally unaffordable,
the reading shall **not** be reinterpreted to reduce cost. The reading is declared on its merits; any
reduction in executed extent is then declared **separately and visibly** as a reduction, reported
alongside the result, and never presented as the check itself. This mirrors R-U05-1's existing structure,
under which a refinement is "a separately declared and additionally reported pass, never a replacement."

**Rationale recorded.** Selecting among interpretations of a required check on the basis of what is
affordable makes the executed check a function of available compute rather than of the validation
question. The distinction preserved here is between a **limitation**, which is visible in the record and
can be weighed by a reader, and a **defect**, which is not.

**Explicit limits — this approval names no value.** It does **not** choose the V-14 reading, set the
expanded domains, fix the density on expanded passes, set the D011 coarse extent, assign the core pass to
a gate, define Gate-5 scope, or take a Gate-4 exit. Every one of those remains an open dated human act,
staged blank in `claude_messages/DRAFT_PRE_EXECUTION_DECLARATIONS.md`. It advances no gate and creates no
Gate-5 authority.

## Process Approval — Gate 5 / Gate 6 boundary: the core pass and its `r` extent

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-26 (recorded 2026-08-26 00:45:52 IST). **Provenance:** direct human selection in session from
three alternatives presented by Claude. The selected option, verbatim:

> **G5 = CSB pass at r in {0.5,1,2}** — G5 owns the core pass at all three r values, making the D013
> trigger evaluable within G5. G6 owns D011, V-14, D015 diagnostics, triggered ablation and landscape
> characterization. ~21 core-days, ~1.2 days wall. Single named grid point verified first, inside G5.

**Provenance disclosure.** This option was labelled "(Recommended)" by Claude when presented. The
alternatives offered were a primary-only `r=1` pass with the sensitivities moved to Gate 6, and deferring
the boundary to the Gate-5 authorization. Recorded so a later reader can weigh the influence.

**Decision.** The `61^3 = 226,981`-point CSB core pass, executed at D006 `r in {0.5, 1, 2}`, belongs to
**Gate 5**. Gate 6 owns the D011 curvature-match companion, the V-14 domain-expansion passes, the D015
non-primary diagnostic `(c_H,c_f)` pairs, any D013-triggered ablation, and landscape characterization.

**Rationale recorded.** §6 makes D013 fire on the three differences `Delta_i(r)` for `r in {0.5,1,2}`
jointly. Splitting the sensitivities from the primary would leave Gate 5 with a result whose own trigger
could not be evaluated until Gate 6, so the three `r` values form one decision unit.

**Bounded-batch discipline is retained inside Gate 5:** a single named grid point must be verified end to
end before the pass is released. This preserves the practice that surfaced real defects at Gate 3 and
Gate 4 without spending a separate gate on it.

**Load-bearing inference flagged at the time of decision.** "Core pass" is read as all three constraint
families active at all three `r` values, inferred from D013's trigger wording rather than from an explicit
definition. If a controlling text is later found defining "core pass" as `r = 1` only, this boundary must
be revisited by a new dated approval.

**Explicit limits.** This fixes a gate boundary only. It does **not** authorize Gate 5, start any pass,
choose the V-14 reading, set the D011 coarse extent, define Gate-5 exclusions or ownership, or take a
Gate-4 exit. Gate 5 remains unauthorized and unstarted.

## Process Approval — D011 coarse curvature-match subgrid extent, with mandatory matched-subgrid comparison

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-26 (recorded 2026-08-26 00:47:03 IST). **Provenance:** direct human selection in session from
three alternatives presented by Claude. The selected option, verbatim:

> **Every 5th: 13/axis, 2,197 pts** — `l in {0,5,...,60}`, one point per half-decade, all three axes
> retained. ~1% of primary, ~0.07 core-days. Derived from D012's `P=10`. Matched-subgrid comparison
> against the primary restricted to these same points.

**Provenance disclosure.** This option was labelled "(Recommended)" by Claude when presented. The
alternatives offered were a 7-per-axis decade-boundary lattice (343 points) and a full-density 61x61
two-axis slice (3,721 points). Recorded so a later reader can weigh the influence.

**Decision.** D011's required non-primary curvature-match companion executes on the coarse subgrid
`ell in {0, 5, 10, ..., 60}` on each of the three axes — 13 coordinates per axis, `13^3 = 2,197` points,
one point per half-decade. This discharges D011's outstanding pre-execution commitment. It is declared
before any core result exists and may not be revised in light of any result; a revision requires a new
dated approval stating the result already observed.

**MANDATORY — matched-subgrid comparison.** The companion's `rho_E^exact` shall be compared **only**
against the primary restricted to these same 2,197 points, never against the full-density 226,981-point
primary rate. Because `rho_E^exact` is exact over whatever grid is declared rather than sampled, a
comparison across differing grid densities is confounded by density rather than by the alternate anchor
the companion exists to test, and constitutes no evidence about rank stability.

**Standing conditioning, unchanged.** The companion remains **non-primary** and report-only; it carries
its known local bias `D_CM(w) = s*w > 0`; it is **not** a D013 trigger input; and it does not alter
D006's `r in {0.5, 2}` sensitivities. Per §4.1 the companion has no `r` analogue — it is the single fixed
`a = 2`, `Lambda_pen = s*Lambda_ref/2` mapping for inequality families only, cardinality excluded.

**Explicit limits.** This sets an extent and a comparison rule only. It does not authorize Gate 5 or
Gate 6, execute any pass, choose the V-14 reading, or take a Gate-4 exit. Gate 5 remains unauthorized and
unstarted; the D011 companion belongs to Gate 6 per the boundary fixed earlier today.

## Process Approval — V-14 domain-expansion execution reading

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-26 (recorded 2026-08-26 00:48:41 IST). **Provenance:** direct human selection in session from
four alternatives presented by Claude. The selected option, verbatim:

> **Scale D010 margins, r=1** — 0.5x -> `m_lo=2, m_hi=0` (3 decades, 29,791 pts); 2x -> `m_lo=8, m_hi=2`
> (11 decades, 1,367,631 pts). Tests the actual discretionary choice (`m_lo=4` judgement). Defect to
> record: `0.5 x m_hi` is non-integer, resolved by floor to 0. ~43 core-days, ~2.4 days wall.

**Provenance disclosure.** This option was labelled "(Recommended)" by Claude when presented. The
alternatives were literal log-span scaling (3 and 12 decades), a margins reading with the 2x pass executed
on a visibly declared reduction, and deferral. Claude explicitly recorded the counter-argument against its
own recommendation at the time of presentation: "0.5x/2x the box" read literally means the box, and
margin-scaling yields 3 and 11 decades rather than the 3 and 12 of literal span-scaling; the recommendation
prefers the better-targeted test over the more literal one. Recorded so a later reader can weigh both.

**Decision.** V-14's required domain-expansion check executes by scaling D010's decade margins:

| pass | margins | `q` range | decades | pts/axis | grid points |
|---|---|---|---|---|---|
| 0.5x | `m_lo=2, m_hi=0` | `[-2, 1]` | 3 | 31 | 29,791 |
| primary | `m_lo=4, m_hi=1` | `[-4, 2]` | 6 | 61 | 226,981 |
| 2x | `m_lo=8, m_hi=2` | `[-8, 3]` | 11 | 111 | 1,367,631 |

Both expansion passes execute at D006 **`r = 1` only**. V-14 is a report-only robustness companion under
§6, and the conclusion whose box-dependence is under test is the primary one; running all three `r` would
triple the cost without posing an additional robustness question. D012's `P = 10` intervals per decade
carries over to both expanded passes.

**RECORDED DEFECT — a judgement, not a theorem.** `0.5 x m_hi = 0.5` decades is not an integer. It is
resolved by **floor to `m_hi = 0`** on the 0.5x pass. This is a recorded judgement call in the same sense
as D010's `m_lo = 4`, and it must be reported alongside any V-14 result. No reading of "0.5x/2x the box"
is free of a structural defect; three alternatives were examined and each carries one.

**Grounds of choice, recorded.** V-14's text reads "the box was chosen too narrowly." The box's only
discretionary content is D010's margins — `rho_box` is derived, `m_hi = 1` is derived, and `m_lo = 4` is
recorded as a judgement. Scaling the margins therefore stress-tests the choice actually made. This is a
pre-result design ground, not an outcome claim.

**Declared before any result exists.** No ground state, tie set, A/B/C label, or rate existed at the time
of this approval. It may not be revised in light of any result; a revision requires a new dated approval
stating the result already observed. The affordability disposition approved earlier today governs: should
this reading prove unaffordable, the reading is not reinterpreted downward — a reduction is declared
separately and visibly as a reduction.

**Explicit limits.** This fixes an execution reading only. It does not authorize Gate 5 or Gate 6, execute
any pass, define Gate-5 scope or ownership, or take a Gate-4 exit. Gate 5 remains unauthorized and
unstarted; V-14 belongs to Gate 6 per the boundary fixed earlier today.

## Process Approval — Gate 4 bounded M5 enforcement extension

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-26 (recorded 2026-08-26 01:01:40 IST). **Provenance:** direct human
approval in session, verbatim:

> Approved: extend Gate 4 solely to enforce M5’s decoded-only classifier/service boundary and its V-4/V-8 conformance checks, including isolated toy
> fixtures as required. This does not authorize any primary-instance ground-state certification, encoded tie-set computation, reported A/B/C
> classification, experiment, result, conclusion, or Gate 5 work. Gate 4 remains open pending producer handoff, independent review, and my explicit
> final exit decision.

**Decision.** The existing bounded Gate-4 authorization is extended only for M5's decoded-only
classifier/service boundary and the mapped V-4/V-8 conformance checks, including isolated toy fixtures as
required. This resolves the prior authorization conflict between frozen M5 enforcement at G4 and the
earlier exclusion of classifier work.

**Interpretation restraint.** The quoted approval controls its own boundary. In particular, no
primary-instance exact ground-state certification, encoded tie-set computation, reported A/B/C
classification, experiment, result, conclusion, or Gate-5 work is authorized. This record does not
broaden the extension beyond the stated M5 interface and V-4/V-8 conformance purpose, and it makes no
scientific claim.

**Ownership and exit remain open.** This is a scope authorization only. Before substantive M5 producer
work starts, an explicit producer and independent-review ownership split must be recorded for that work, as
required by the parent Gate-4 approval. Gate 4 remains open; its exit still requires the current producer
handoff, independent review of the final snapshot, and Shivansh's explicit final decision. Gate 5 remains
unauthorized and unstarted.

## Clarification and ownership amendment — Gate 4 bounded M5 enforcement

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-26 (recorded 2026-08-26 01:09:05 IST). **Provenance:** direct human
approval in session, verbatim:

> For V‑4 only, exact ground-state and full encoded tie-set enumeration are authorized on isolated toy instances of at most approximately 22 total
> variables, solely as a conformance check. The prohibition on encoded tie-set computation continues to apply to the primary instance and to any result-
> producing run.
>
> Approved: upon filing the current F3/F1/F2/F5 handoff, Laguna 2.1 is the sole producer for the bounded Gate 4 M5 work. 0xalpha is the independent
> reviewer. Claude remains planner/verifier/orchestrator and Codex remains paused from producer work. M5 work may not begin before this split is
> recorded and must remain within the approved M5/V‑4/V‑8 scope.

**V-4 clarification.** The prior M5 authorization's encoded-tie-set prohibition is clarified: for V-4
only, full encoded tie-set enumeration and exact ground-state enumeration are authorized on isolated toy
instances with at most approximately 22 total variables, solely for conformance. The prohibition continues
for the primary instance and every result-producing run. This creates no authority to report a scientific
result, decoded A/B/C classification, primary-instance tie set, or Gate-5 work.

**Ownership amendment.** Once Laguna 2.1 files the current F3/F1/F2/F5 handoff, Laguna 2.1 is the sole
producer for the bounded M5 work. 0xalpha is the independent reviewer. Claude remains
planner/verifier/orchestrator and produces no M5 artifact; Codex remains paused from producer work. M5
implementation must not begin before the handoff condition is met, and must remain within the approved
M5/V-4/V-8 scope.

**Explicit limits.** This clarification and ownership amendment do not take a Gate-4 exit and do not
authorize primary-instance ground-state certification, primary-instance encoded tie-set computation,
reported A/B/C classification, experiment, result, conclusion, or Gate-5 work. Gate 4 remains open pending
the specified producer handoff, independent review, and Shivansh's explicit final exit decision.

## Ownership amendment — Gate 4 M5 reassignment after Laguna handoff

**Status: APPROVED — supersedes Laguna's prospective M5 assignment in the preceding M5 ownership amendment.**

**Approved:** Shivansh, 2026-08-26 (recorded 2026-08-26 13:11:12 IST). **Provenance:** direct human
approval in session, verbatim:

> Approved: Laguna 2.1 is relieved of all further Gate 4 work. Sol Medium is the sole producer for the bounded M5 scope. Claude is the independent M5
> reviewer; 0xalpha is a non-blocking independent auditor. Codex remains paused from production.

**Decision.** Laguna 2.1's current F3/F1/F2/F5 handoff was filed at
`laguna_messages/to_claude.md` [2026-08-26 12:29:39 IST], satisfying the handoff condition of the prior
M5 ownership amendment. Laguna is relieved of all further Gate-4 work. Sol Medium is the sole producer
for the already approved bounded M5 scope. Claude is the independent M5 reviewer. 0xalpha may conduct an
independent audit but is explicitly non-blocking. Codex remains paused from production.

**Separate current-snapshot review remains required.** This reassignment does not accept the F3/F1/F2/F5
producer handoff or authorize any agent to self-accept it. The final current G4 snapshot remains subject to
the parent approval's independent-review and owner-exit requirements.

**Explicit limits.** This changes ownership only. It authorizes no work outside the approved M5/V-4/V-8
scope and no primary-instance certification, primary-instance encoded tie computation, reported A/B/C
classification, experiment, result, conclusion, Gate-4 exit, or Gate-5 work.

## Bounded corrective approval — Gate 4 M5 comparator evidence and final review

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-26 (recorded 2026-08-26 14:02:05 IST). **Provenance:** direct human
approval in session after Claude's independent M5 review, verbatim:

> Approved: Sol Medium may perform one bounded Gate 4 M5 evidentiary repair limited to (a) adding independently derived comparator fixtures immediately
> inside, exactly on, and immediately outside the frozen D015 tolerance boundary, sufficient to detect the five mutations identified by Claude’s N-1;
> and (b) adding a documentation warning that agrees_with_frozen_optimum is only the objective-comparison component of OPT_f, not the complete
> feasibility-aware predicate. No other implementation change is authorized. Claude must review the resulting delta and independently review Laguna’s
> F3/F1/F2/F5 contribution and the final combined Gate 4 snapshot. 0xalpha remains a non-blocking auditor. This authorizes no primary computation, Gate
> 4 exit, or Gate 5 work.

**Decision.** Sol Medium remains the sole producer only for this bounded M5 corrective delta. The allowed
production is limited to independently derived D015 tolerance-boundary fixtures that detect all five
mutations in Claude's N-1 and a documentation warning on the objective-only helper identified by N-4. No
other implementation or conformance change is authorized.

**Review obligation.** Claude remains independent and must review the exact corrective delta, independently
review Laguna's F3/F1/F2/F5 contribution, and review the final combined Gate-4 snapshot. These are required
review surfaces, not producer tasks. 0xalpha remains a non-blocking independent auditor.

**Explicit limits.** This corrective approval authorizes no primary-instance computation, ground-state or
tie-set production, reported primary classification, sweep, experiment, result, conclusion, Gate-4 exit,
or Gate-5 work. Gate 4 remains open pending producer handoff, the specified independent review, and the
owner's explicit final exit decision.

## Bounded corrective approval — Gate 4 B-1/B-2/B-3 verifier hardening

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-26 (recorded 2026-08-26 14:36:52 IST). **Provenance:** direct human
approval in session after Claude's final combined Gate-4 review, verbatim:

> Approved: Gate 4 remains open. Sol Medium is authorized as sole producer for one bounded corrective pass addressing Claude’s B-1, B-2, and B-3
> findings only.
>
> For B-1, replace the arbitrary algebra-conformance tolerance with an explicitly derived tolerance based on measured binary64 accumulation drift and
> demonstrate adequate mutation-detection power across all ledger rows and both encodings.
>
> For B-2, replace the remaining substring-based forbidden-operation checks with structural AST-based checks that detect aliased/imported fsum, indirect
> or aliased fma, pow/**, and NumPy imports or access without triggering on comments, docstrings, or unrelated string literals.
>
> For B-3, pin the exact SHA-256 of claude_messages/review_g4_energy_conformance.py in Gate-4 provenance and require verify_g4_energy.py to verify that
> hash before dynamically loading the reviewer oracle. The reviewer-owned oracle itself must not be modified.
>
> Sol may update only the minimum necessary Gate-4 verifier and provenance files and its own append-only handoff. It must run all affected verification
> under normal Python and python3 -O, preserve explicit fail-closed behavior, and report exact opening and final hashes. No mathematical formulation,
> ledger, production energy evaluator, classifier, protected input, frozen authority, primary computation, Gate-5 work, experiment, result, or
> conclusion may change.
>
> Claude is the independent reviewer of this corrective delta and the resulting final combined Gate-4 snapshot. Codex remains paused from production,
> and 0xalpha remains a non-blocking auditor. Gate 4 remains open pending producer handoff, independent review, and my explicit final exit decision.

**Decision.** The prior final-review recommendation does not close Gate 4. Sol Medium is the sole producer
for a corrective pass limited to B-1, B-2, and B-3 exactly as quoted. Claude independently reviews both
the delta and the resulting combined snapshot. The reviewer-owned oracle is read-only to the producer.

**Explicit limits.** No formulation, ledger, production evaluator, classifier, protected input, frozen
authority, primary computation, Gate-5 object, experiment, result, or conclusion is authorized to change.
Gate 4 remains open pending Sol's handoff, Claude's independent review, and the owner's explicit exit act.

## Ownership amendment — Gate 4 final corrective pass: Gemini as sole producer

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-26 (recorded 2026-08-26 16:15:51 IST). **Provenance:** direct human approval in session,
verbatim, signed "~ shivansh":

> Approved [DATE]: Gemini is authorized as sole producer for one bounded Gate-4 corrective pass, limited to the six items in claude_messages/TASK_SPEC_G4_FINAL_CORRECTIVE.md. Claude is the independent reviewer; 0xalpha remains a non-blocking auditor; Codex remains paused and Sol Medium is unavailable. Gemini's filed audit stands as an artifact and is not reopened; it does not review its own production. +0.0 inactive-coefficient representability is explicitly excluded and carries to Gate 6 with D013. Gate 4 remains open pending producer handoff, independent review, and my explicit final exit decision.

**Note on the quoted text.** The approval was given with the literal placeholder `[DATE]` from the draft
Claude presented. The effective date is the recorded timestamp above. No other substitution was made and
the wording is otherwise verbatim.

**Decision.** Gemini is the sole producer for one bounded Gate-4 corrective pass, limited to the six items
specified in `claude_messages/TASK_SPEC_G4_FINAL_CORRECTIVE.md`: the `math.pow`/aliased-`pow` detector
gap; the overstated coverage claim; the oracle check/load gap; the constant-term detection gap; the
`getattr` false positive; and, only if it changes no emitted value, an independent high-precision
cross-check of the §4.3 coefficient transcript.

**Ownership and separation.** Claude is the independent reviewer. 0xalpha remains a non-blocking auditor.
Codex remains paused from production and Sol Medium is unavailable. **Gemini's filed audit at
`gemini_messages/to_claude.md` stands as an artifact and is not reopened**; Gemini produces under this
amendment and does **not** review its own production.

**Explicitly excluded and carried forward.** `+0.0` inactive-coefficient representability —
`src/g4/parameters.py` rejects coefficients `<= 0.0`, so §5.1's inactive-inequality case cannot be loaded
— is **not** in scope. D013 ablation is excluded from the parent Gate-4 authorization, and how symbolic
multiplicity is realised is a design question belonging to D013's own authorization. **It carries to
Gate 6.**

**Occasion.** This pass follows Claude's [15:23] review, Gemini's dissenting audit, and Claude's
verification of that dissent, which confirmed that one of Claude's severity arguments was mathematically
wrong: D015's `tau` scales with `max(|y|,|y'|)` and is therefore **not** shift-invariant, so a
constant-term error can alter a tie set. Items 1 and 4 above were upgraded on that basis.

**Explicit limits.** This authorizes no primary-instance certification, encoded tie-set computation,
reported A/B/C classification, sweep, experiment, result, conclusion, Gate-4 exit, or Gate-5 work. Gate 4
remains open pending producer handoff, independent review, and the owner's explicit final exit decision.

## Process Approval — GATE 4 EXIT

**Status: APPROVED — GATE 4 IS CLOSED**

**Approved:** Shivansh, 2026-08-26 (recorded 2026-08-26 17:02:01 IST). **Provenance:** direct human approval in session,
verbatim:

> okay I approve of your recommendations

**Provenance transparency.** This approval was given as assent to three enumerated recommendations Claude
had just put to him, rather than as bespoke decision text. The full text of what was assented to is
reproduced here so the chain is auditable:

> **1. Confirm Gate 4 now.** Every recorded condition is met — Sol's handoff, my independent review, and
> the corrective pass verified clean. The draft in `claude_messages/DRAFT_G4_EXIT_AND_G5_AUTHORIZATION.md`
> needs only a date.
> **2. Authorize Gate 5** from the same file. Both blanks are closed, the ordering requirement and
> handover protocol are in the text.
> **3. One adjustment to the producer plan:** give Gemini the low-risk slice now (remove
> `src/g4/__pycache__/` and re-attest; build the worker self-test vector and per-shard provenance
> contract). Codex takes the evaluator repair and the core pass when it returns. Sequence by risk rather
> than by availability.

**Decision — Gate 4 is closed.** Its accepted scope is the bounded encoding formulation and conformance
work, the canonical §5.2 `H_E` evaluator, the M5 decoded-only classifier with V-4/V-8 conformance, and the
B-1/B-2/B-3 verifier hardening with its subsequent repair — produced across Codex, Grok 4.6, Laguna 2.1,
Sol Medium and Gemini, and independently reviewed by Claude at the 16:40:30 snapshot.

**Recorded exit conditions, all discharged:** producer handoff (Gemini, [16:38]); Claude's independent
review of the final snapshot ([17:0x], all runs completed in both modes, snapshot byte-identical
throughout); and this explicit owner exit act.

**THIS EXIT ASSERTS CORRECTNESS, NOT FITNESS FOR GATE-5 SCALE.** The following are recorded as known
limitations carried forward. Closure does **not** assert that any is repaired:

1. `src/g4/energy.py` costs **830.7 us/call** against ~3.5 us for an equivalent cached path —
   approximately **13 core-years** at Gate-5 scale versus ~7 core-days. Architecture, not arithmetic; the
   arithmetic is verified bit-exact and must not change.
2. Expanded-matrix QUBO accumulation drifts from the canonical residual form by up to **3279.9x the D015
   `tau`** at `c_H = 2048`. The §5.2 residual form is the sole canonical comparison path.
3. V-4's conformance toy exhibits no auxiliary degeneracy and its closed-form path emits one lift per
   decoded state. This becomes load-bearing at Gate 5 under D013's inactive-coefficient case.
4. `+0.0` inactive-coefficient representability: `src/g4/parameters.py` rejects coefficients `<= 0.0`, so
   §5.1's inactive-inequality case cannot be loaded. Excluded from Gate 4; **carried to Gate 6 with D013**.
5. `src/g4/__pycache__/` contains two `.pyc` artifacts timestamped 16:17:49 that two producer handoffs
   attested were absent. To be removed and re-attested.
6. Producer attestation reliability: one handoff reported item 6 declined when it had been implemented and
   left failing in the tree; another reported a ~1s runtime for a verifier measured five times at
   122-133s; a third asserted "All verifiers continue to pass" with no commands or exit codes. The
   delivered artifacts were independently verified correct; the attestations were not reliable.

**Explicit limits.** This closes Gate 4 only. It authorizes no primary-instance certification, encoded
tie-set computation, reported A/B/C classification, grid sweep, experiment, result, or conclusion.
`previous_work/**`, `research/canonical/**`, `research/ground_truth/**`, and `research/adnye/**` remain
read-only.

## Process Approval — GATE 5 authorization

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-26 (recorded 2026-08-26 17:02:01 IST). **Provenance:** the same verbatim approval and
enumerated recommendations reproduced in the Gate-4 exit record immediately above, approving the Gate-5
authorization drafted at `claude_messages/DRAFT_G4_EXIT_AND_G5_AUTHORIZATION.md`.

**Decision.** Gate 5 is authorized, limited to:

(a) implementing exact ground-state certification over `C_slack` and `C_unbalanced` per
    `FROZEN_MATH_SPEC.md` §5.1, with `T_E` construction and `X_E` decoding per §5.3 and D016 labelling;
(b) executing the CSB core pass over the primary `61^3 = 226,981`-point grid at D006 `r in {0.5, 1, 2}`,
    per the Gate-5/Gate-6 boundary fixed 2026-08-26;
(c) repairing the canonical evaluator's per-call cost — validation hoisted to a run boundary, a
    prepared-state path accepting precomputed `f` and residuals, per-state arithmetic byte-identical;
(d) the carried Gate-4 verifier corrections, including removal and re-attestation of
    `src/g4/__pycache__/`;
(e) a worker self-test vector and per-shard provenance contract if execution is distributed.

**ORDERING REQUIREMENT, BINDING.** Clause (c) shall complete and be **independently verified bit-exact
against an independent §5.2 transcription before clause (b) executes.** The core pass may not run on an
evaluator whose bit-exactness has not been re-verified after the repair. **A single named grid point shall
be verified end to end before the full pass is released.**

**ENERGY AUTHORITY, BINDING.** All Gate-5 energies shall be computed by the `FROZEN_MATH_SPEC.md` §5.2
residual-form ledger. **Expanded-matrix accumulation is barred from any comparison, tie determination, or
reported energy.**

**Ownership — staged, sequenced by risk.** Gemini is the producer until Codex returns from its usage
limit, and its slice is limited to the low-risk items: `__pycache__` removal and re-attestation, and the
clause (e) worker self-test vector and provenance contract. **The clause (c) evaluator repair and the
clause (b) core pass are reserved for Codex.** Claude is the independent reviewer throughout; 0xalpha
remains a non-blocking auditor.

**HANDOVER PROTOCOL, BINDING.** The two producers shall never hold the tree simultaneously. Gemini's stint
ends with a filed handoff naming every changed file with opening and final SHA-256, **and** Claude's
independent review of it, before Codex begins — so that Codex never inherits and builds upon unreviewed
work. No agent reviews its own production; no producer may self-accept or claim a Gate-5 exit.

**Excluded:** the D011 companion, V-14 expansion passes, D015 non-primary diagnostic pairs, any
D013-triggered ablation, landscape characterization, Stage-2 work, and all conclusions — these belong to
Gate 6 or later. Protected trees remain read-only.

## Process Approval — Gate 6 / Gate 7 boundary: computation versus inference

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-26 (recorded 2026-08-26 18:02:43 IST). **Provenance:** direct human selection in session from
three alternatives presented by Claude. The selected option, verbatim:

> **G6 = all computation, G7 = inference** — G6 produces every remaining number: D011 companion, V-14
> expansion, D015 diagnostics, D013 ablation if fired, and the rate surfaces. G7 draws conclusions from
> them: hypothesis evaluation, the primary slack-vs-unbalanced comparison, reported rates with mandatory
> conditioning. The gate falls exactly where interpretation enters, which is the boundary an adversarial
> audit cares about.

**Provenance disclosure.** This option carried Claude's "(Recommended)" label when presented. The
alternatives were a smaller Gate 6 owning only landscape characterisation with the robustness passes moved
to Gate 7, and merging the two gates outright. Recorded so a later reader can weigh the influence.

**Decision.** **Gate 6 owns all remaining computation** on the Stage-1 instance: the D011 curvature-match
companion on its declared 2,197-point subgrid with mandatory matched-subgrid comparison; the V-14
domain-expansion passes at the declared margins; the four D015 non-primary diagnostic `(c_H,c_f)` pairs;
any D013-triggered `{C, CB, CS, CSB}` ablation; and the rate surfaces over the `s`-grid.

**Gate 7 owns inference on the Stage-1 instance** and produces no new primary numbers: hypothesis
evaluation, the primary slack-versus-unbalanced comparison, `rho_E^exact` reporting with the mandatory
D006 conditioning, and the Stage-1 conclusions.

**Grounds recorded.** `DECISIONS.md` already requires that original-problem facts, encoding construction,
certification, experiments and conclusions be kept as separately gated layers. This places the Gate-6/7
boundary exactly where interpretation enters rather than at an arbitrary point inside the computation, so
that an adversarial reviewer can examine the numbers and the inferences drawn from them as separate
accepted artifacts.

**Consequence recorded — Gate 6's scope is partly conditional on Gate 5's output.** D013 fires only if the
three differences `Delta_i(r) = rho_slack,i,r^exact - rho_unbalanced,i,r^exact` for `r in {0.5,1,2}`
include zero or fail to share one strict sign. Whether the `{C, CB, CS, CSB}` ablation runs at all is
therefore not knowable until the Gate-5 core pass completes.

**Prerequisite recorded.** If D013 fires, the ablation requires inactive constraint families with
coefficient exactly `+0.0`. `src/g4/parameters.py` currently rejects any coefficient `<= 0.0`, so §5.1's
inactive case cannot be loaded. That carried Gate-4 limitation is on Gate 6's critical path, not a
footnote, and must be resolved before any ablation executes.

**Explicit limits.** This fixes a gate boundary only. It authorizes no Gate-6 or Gate-7 work, starts no
pass, resolves no Stage-2 decision, and creates no authority beyond the currently authorized Gate 5. U-08
through U-11 remain open and blocking for Stage 2.

## Process Approval — Gate 5 clause-(a) ratification and conditional Rust batch evaluator

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-26 (recorded 2026-08-26 18:19:27 IST). **Provenance:** direct human
approval in session, verbatim:

> Approved 2026-08-26:
>
> 1. I ratify Gemini’s completed Gate-5 clause-(a) certification machinery, repairs, and follow-on work as bounded Gate-5 production. This ratification
>    is based on Claude’s independent reviews and does not accept or close Gate 5.
>
> 2. Codex remains the sole producer for Gate-5 clauses (c) and (b). Codex shall first complete the authorized Python evaluator repair, the linear-time
>    decode_x_e correction, and independent bit-exact review.
>
> 3. After the repaired Python path is independently accepted, Codex is additionally authorized to implement a bounded Rust batch evaluator for the
>    frozen §5.2 inner loop. Python remains the canonical reference and accepted fallback. Rust may receive only precomputed objective/residual data and
>    coefficients and return canonical residual-form energies; domain construction, certification, tie-set construction, decoding, classification,
>    sharding, and interpretation remain in Python.
>
> 4. Before any Rust-produced value may contribute to the primary pass, the implementation must:
>     - pass the frozen worker vector as a pre-execution gate;
>     - agree bit-for-bit with the repaired Python evaluator and independent §5.2 oracle;
>     - pass an explicit FMA/contraction-discriminating test;
>     - record Rust, LLVM, target, build flags, source hashes, and binary SHA-256;
>     - demonstrate end-to-end performance, including Python/Rust boundary and result processing;
>     - fail closed on any digest, build, platform, or numerical mismatch;
>     - pass the required single named grid-point certification and independent review.
>
> 5. The projected speed is not accepted as fact until measured. If the compiled path fails exactness, provenance, or material-speedup requirements, it
>    is rejected and the verified Python path remains controlling.
>
> 6. Claude is the independent reviewer and 0xalpha remains a non-blocking auditor. This authorizes no Gate-6 execution, Stage-1 inference, experiment
>    beyond the authorized Gate-5 core pass, result, conclusion, or Gate-5 exit.

**Decision.** Gemini's completed clause-(a) artifacts and follow-on are ratified as bounded Gate-5
production on the strength of Claude's independent reviews. Codex is the sole producer for clauses (c)
and (b). The existing order remains binding: the Python repair and linear-time decoder must be produced
and independently accepted before any Rust production begins; the named-point review remains mandatory
before the full core pass.

**Conditional compiled path.** The Rust batch evaluator is authorized only after that independent Python
acceptance. It is an optional accelerator, never the canonical reference. Its measured verification,
toolchain/binary provenance, fail-closed gate, and fallback conditions are exactly those quoted above.
This approval does not authorize installing a toolchain through an unrecorded external mutation; any
required installation must remain separately visible in the implementation handoff.

**Explicit limits.** No Rust-produced value may contribute before all quoted gates pass. No Gate-6
execution, inference, work beyond the authorized Gate-5 core pass, result, conclusion, or Gate-5 exit is
authorized.

## Process Approval — Gate-5 accepted-source byte preservation

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-26 (recorded 2026-08-26 20:14:28 IST). **Provenance:** direct human
approval in session, verbatim:

> Approved: promote the exact recovered gemini_messages/domains_ratified_clause_a_candidate.py.txt, SHA-256
> 3ec856d3b3061605aa6d583bb7a94a9d27c699aa08b88c64ff12e622a714d7cc, to inert evidence at research/g5/domains_ratified_clause_a.py.txt. For the remainder
> of Gate 5, preserve exact prior bytes as inert hash-pinned evidence before modifying any accepted or ratified source artifact. This grants no
> additional computational or gate authority.

**Decision.** The recovered ratified clause-(a) enumerator is promoted exactly as authorized. Its
candidate and inert evidence copy are byte-identical and each hashes to the approved digest. For the
remainder of Gate 5, an accepted or ratified source artifact must have its exact prior bytes preserved as
inert hash-pinned evidence before in-place modification. This is a provenance rule only and creates no
new execution, experiment, gate, or ownership authority.

## Process Approval — Gate-5 independent-review ownership amendment

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-26 (recorded 2026-08-26 23:50:49 IST). **Provenance:** direct human
approval in session, verbatim:

> Approved 2026-08-26: Claude is relieved of all remaining Gate-5 review duties due to unavailability. Codex remains the sole producer for the current
> Gate-5 clause-(b) Python pipeline. A fresh, production-isolated Gemini session is designated as the controlling independent reviewer for the corrected
> clause-(b) delta and final combined snapshot. That reviewer may inspect and execute verification but may not modify production, research, authority,
> status, progress, or Codex-owned artifacts. Gemini #1, #2, and #3 remain supporting non-blocking auditors whose prior evidence may be considered but
> does not substitute for the fresh review. No named grid point, Rust-produced primary value, full core pass, Gate-6 work, acceptance, or Gate-5 exit is
> authorized by this ownership amendment.

**Decision.** Claude is relieved of the remaining Gate-5 reviewer role. Codex remains the sole producer for
the current corrected clause-(b) Python pipeline. A fresh production-isolated Gemini session is the
controlling independent reviewer for that delta and its final combined snapshot. Earlier Gemini sessions
remain supporting non-blocking auditors only.

**Explicit limits.** The new reviewer may inspect and execute verification but may not modify production,
research, authority, status, progress, or Codex-owned artifacts. This ownership amendment releases no named
grid point, Rust-produced primary value, full core pass, Gate-6 work, acceptance, or Gate-5 exit.

## Process Approval — Gate-5 clause-(b) infrastructure acceptance and single named point

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-27 (recorded 2026-08-27 00:06:45 IST). **Provenance:** direct human
approval in session, verbatim:

> Approved 2026-08-27: I accept the corrected Gate-5 clause-(b) Python pipeline as infrastructure, based on the fresh controlling Gemini review.
>
> Codex, as sole producer, is authorized to execute exactly one primary named grid point using the accepted Python residual-form path: r = 1, (ℓ_card,
> ℓ_sector, ℓ_budget) = (30,30,30), corresponding to (s_card,s_sector,s_budget) = (0.1,0.1,0.1), for both slack and unbalanced encodings.
>
> This authorization includes computing and recording the exact encoded minimum, complete encoded tie set T_E, decoded set X_E, and decoded-only A/B/C
> labels for this point only. Codex must run the worker pre-execution gate, bind all accepted artifact hashes, record timing and peak-memory evidence,
> and stop after filing a producer handoff.
>
> A fresh production-isolated Gemini session is the controlling independent reviewer of the named-point output. This authorizes no additional grid
> point, grid sweep, full core pass, Rust-produced primary value, Gate-6 work, interpretation, conclusion, Gate-5 acceptance, or Gate-5 exit.

**Decision.** The corrected clause-(b) Python pipeline is accepted as infrastructure. Codex remains sole
producer and may execute exactly the declared primary center point at `r=1`, ledger indices `(30,30,30)`
and coordinates `(0.1,0.1,0.1)`, for both encodings. The named-point output must include the exact encoded
minimum, complete `T_E`, decoded `X_E`, decoded-only D016 labels, bound artifact hashes, and timing and
peak-memory evidence. The worker self-test is a pre-execution gate.

**Review and stop boundary.** A fresh production-isolated Gemini session controls independent review of
the resulting output. Codex must stop after its producer handoff. No other grid point, sweep, full core
pass, Rust-produced primary value, Gate-6 work, interpretation, conclusion, Gate-5 acceptance, or Gate-5
exit is released by this decision.

## Process Approval — Gate-5 core-pass release and Gemini ownership

**Status: APPROVED**

**Approved:** Shivansh, 2026-08-27 (recorded 2026-08-27 01:18:10 IST). **Provenance:** direct human
approval in session, verbatim:

> Approved 2026-08-27:
>
> 1. I accept the reviewed Gate-5 single named point as the required pre-core-pass check, and accept N-2 half-integer/clipping minimizer evidence as
>    closed for core-pass release consideration.
>
> 2. Gemini is the sole producer for the Gate-5 primary Python CSB core pass: all 61^3 = 226,981 primary coordinates, D006 r ∈ {0.5, 1, 2}, and both
>    slack and unbalanced encodings, using only the accepted canonical residual-form Python path.
>
> 3. A separate fresh Gemini session is the controlling independent reviewer of the completed core-pass artifacts. Codex is restricted to planning,
>    provenance coordination, prompt writing, and light consistency adjudication; it is not a core-pass producer.
>
> 4. Rust is deferred and may not contribute any primary value. This authorization excludes D011, V-14, D015 diagnostics, D013 ablation, Gate 6 work,
>    interpretation, conclusions, Gate-5 acceptance, and Gate-5 exit.
>
> 5. The producer must stop after filing hash-bound, shard-complete core-pass artifacts and a handoff for independent review. No result is accepted
>    until that review and my separate decision.

**Decision.** The named-point preflight and N-2 fixture prerequisite are accepted for core-pass release
consideration. Gemini is sole producer for the full primary Python CSB pass: every `61^3` coordinate at
each D006 `r in {0.5,1,2}`, for both encodings, using the accepted canonical residual-form path only. A
separate fresh Gemini session is controlling independent reviewer. Codex is restricted to planning,
provenance coordination, prompt writing and light consistency adjudication.

**Operational safety rule.** The producer must measure end-to-end throughput and peak RSS from the accepted
named-point architecture before launching shards, record its worker count, and use no more than 12 workers
without a new owner decision. Rust contributes no primary value.

**Stop boundary.** The producer must stop after hash-bound, shard-complete artifacts and a handoff. D011,
V-14, D015 diagnostics, D013 ablation, Gate-6 work, interpretation, conclusions, Gate-5 acceptance and
Gate-5 exit remain excluded pending separate authority.
