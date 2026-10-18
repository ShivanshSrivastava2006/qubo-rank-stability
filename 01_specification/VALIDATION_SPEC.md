# VALIDATION SPECIFICATION — Gate 0

**Status:** Historical Gate-0 validation draft, with mapped validation obligations retained. The authoritative
Gate-1 mathematical rules and interfaces are `research/00_specifications/FROZEN_MATH_SPEC.md` under W0b
through D016. This document does not supersede an approved decision or frozen rule.
**Companion to:** `research/00_specifications/FROZEN_MATH_SPEC.md` (and historical interface detail in
`research/00_specifications/IMPLEMENTATION_SPEC.md`)
**Date:** 2026-08-22

---

## Gate-1 frozen authority map (W4)

This map adds no test and authorizes no execution. Current mathematical rules
come from `FROZEN_MATH_SPEC.md` and its cited decisions; the detailed test
design below remains the validation interface for later gates.

| Frozen subject | Current authority | Later validation boundary |
|---|---|---|
| Slack raw-domain/minimization and 39-bit layout | D005/D015, frozen spec §5 | V-1–V-5, V-11 |
| Separate encoded ties and original optimality | D015, frozen spec §5 | V-4, V-6, V-8, V-10, V-11 |
| Decoded A/B/C partition and denominators | D016, frozen spec §6 | V-8, V-16 |
| D006 primary and `r={0.5,2}` sensitivities | D006, frozen spec §4 | V-12, V-15 |
| D011 curvature-match companion | D011, frozen spec §4 | V-12 |
| No claimed cardinality threshold | D009, frozen spec §4 | V-17 obligation 1; obligation 2 remains untriggered unless a future claim is approved |
| Residual-sharing interface | frozen spec §3 / M4 declaration | V-18 at G4 |
| D014/D015/D016 provenance | D014–D016, frozen spec §§3,5–6 | V-13 |

**Explicit retirements / supersessions:** exact floating-point equality is not
the current tie rule (D015 supplies the canonical tolerance ledger); the Scope
Lock's literal curvature-match coefficient is not a primary mapping (D011
defines its non-primary companion); and any earlier suggestion that slack
states are automatically feasible is withdrawn. Historical prose below is read
through this map and cannot override it.

---

## Validation philosophy

Per the review logsINITIAL_TO_CODEX.md` §11: *"A test written by the lead that merely confirms the lead's own
implementation is NOT considered strong independent validation."*

This specification therefore ranks validation strength explicitly, and states for every critical component
what would **falsify** it — not merely what would confirm it.

**Strength tiers, weakest to strongest:**

| Tier | Kind | Why it is weak or strong |
|---|---|---|
| T0 | Self-consistency test (code compared to itself) | Near-worthless; catches only refactor regressions |
| T1 | Invariant / dimensional / type check | Catches gross errors, cannot catch a wrong-but-consistent formula |
| T2 | Algebraic identity check against a hand-derived closed form | Strong if the closed form is derived independently of the code |
| T3 | **Independent oracle** — brute force, or a second implementation written from the spec without reading the first | Strongest available to us |
| T4 | External ground truth (published numbers) | Not available for our specific instance |

Every item marked **CRITICAL** below must have at least one T3 check.

A passing test suite does **not** establish scientific validity `[reviewer brief §14]`. Technical correctness
and scientific validity are audited separately; this document covers only the former, plus the design-bias
checks in §V-12 to §V-14.

---

## Critical components and their falsification tests

### V-1 — Auxiliary-register independence `[CRITICAL, tier T3]`

**Claim under test (M4):** for fixed `x`, the slack registers of different constraints do not interact, so
the joint minimization over all auxiliary bits decomposes into independent per-constraint minimizations.

**Falsification test:** on a toy instance small enough to brute-force (e.g. 6 assets, 2 sectors, `K = 2`,
small `B`, register widths 2-3 bits), enumerate **all** joint auxiliary assignments and compare the true
joint minimum against the decomposed per-constraint minimum, for every `x` and for a spread of penalty
coefficients spanning several orders of magnitude.

**Falsified if:** any `(x, coefficients)` pair shows joint minimum < decomposed minimum.

**Why it could fail:** if two constraints were ever made to share a register, or if a cross-term were
introduced when the QUBO is assembled into matrix form, independence breaks silently and the "exact"
certification would return a non-minimal energy.

### V-2 — Closed-form slack minimization vs. naive brute force `[CRITICAL, tier T3]`

*Explicitly requested by the handoff, §G.*

**Claim under test (M5, M7):** `S* = clamp(round(h(x)), 0, 2^N - 1)` is the exact minimizer.

**Falsification test:** for each toy instance and each `x`, compute `argmin_S (h(x) - S)^2` by exhaustive
enumeration over all `2^N` register values, and compare against the closed form. Sweep `N` from 1 to 6 so
that both the under-provisioned regime (`2^N - 1 < max h`, forcing clamping) and the over-provisioned regime
are exercised. Include `h < 0`, `h = 0`, `h > 2^N - 1`, and — critically — **non-integer `h`** with
fractional part exactly 0.5, where `round()` has a tie.

**Falsified if:** the closed form and the brute-force minimizer ever disagree on the achieved *energy*.
(They may legitimately disagree on the *argument* at a `.5` tie; the test must compare energies, and must
separately record whether an argument tie occurred.)

**Adversarial cases the auditor should insist on:**
- `h` negative and large in magnitude (clamp to 0 must win).
- `h` exceeding `2^N - 1` (clamp to max must win).
- `h` exactly `2^N - 1` and exactly 0 (boundaries).
- Non-integer `h` at `.5` — currently unreachable on Stage 1 (integer residuals, M7) but reachable under a
  Stage-2 protocol that resamples prices as floats (U-09). **This is a latent trap.**

### V-3 — Penalty-coefficient independence of `S*` `[CRITICAL, tier T2 + T3]`

**Claim under test (M6):** `S*` depends only on `h(x)` and `N`, never on `lambda_S`.

**Falsification test:** recompute `S*` by brute force at many `lambda_S` spanning `1e-6` to `1e6` and assert
the minimizing energy is attained at the same `S` throughout.

**Why it matters:** this claim is what licenses the precompute-once architecture (§F.4) and the O(2^20)
cost. If `S*` were coefficient-dependent, the whole cost argument collapses.

**Note:** this holds because `lambda_S > 0` multiplies a *single* convex term. The test must include
`lambda_S = 0` as a degenerate case, where every `S` is a minimizer and the tie handling must not crash.

### V-4 — Exact ground state, full pipeline `[CRITICAL, tier T3]`

**Claim under test:** the O(2^20) certified ground state equals the true ground state of the encoded QUBO.

**Falsification test:** on toy instances where the *total* variable count (assets + all auxiliary bits) is
at most ~22, compute the ground state by naive enumeration over the full joint space (the "2^39-style"
brute force, scaled down) and compare against the O(2^{n_assets}) closed-form method. Compare the full
**tie set**, not merely one minimizer.

**Falsified if:** the ground-state energy differs, or the tie sets differ.

### V-5 — Slack marginalization identity `[tier T2]`

**Claim under test (M1):** with a sufficiently wide register, the marginalized slack penalty equals the
hinge-squared function `0 if h >= 0, lambda_S h^2 if h < 0`.

**Falsification test:** direct numeric comparison over a residual grid, for wide registers. Then, with a
deliberately **narrow** register, confirm the identity *breaks* in the predicted direction (feasible states
with `h > 2^N - 1` acquire a nonzero penalty). A test that only confirms the identity is weaker than one
that also predicts and confirms its failure mode — and this failure mode is exactly what U-06 is about.

### V-6 — Original-problem optimum `x*` `[CRITICAL, tier T3]`

**Falsification tests:**
1. Independent recomputation of `x*` by a second enumeration written directly from §C.2/§C.3 without
   reference to the first implementation.
2. Assert `|F| = 976` `[EXPERIMENTAL]` and that `x*` lies in `F`.
3. Assert `f(x*) <= f(x)` for a large random sample of `x in F`.
4. Cross-check against the prototype **only structurally** — its numeric outputs are untrustworthy (§E.2),
   so agreement is not expected and disagreement is not evidence of a bug here.

### V-7 — Encoding correctness: feasible states carry zero constraint penalty `[CRITICAL, tier T1 + T2]`

**Slack:** every `x in F` must achieve exactly zero total inequality penalty at its optimal register
setting. **Falsified if** any feasible `x` carries a nonzero slack penalty — which would indicate an
under-provisioned register and directly implicate U-06.

**Unbalanced:** this property does **not** hold by construction, and asserting it would be a bug in the
test, not the code. Under the approved D006 mapping, assert the derived shape
`zeta_{j,r}(h) = (Lambda_ref/2)*(a_r(s_j)*h/v_j - 1)^2 - Lambda_ref/2`: a parabola in `h` with vertex at
`h* = v_j/a_r(s_j)` and depth `-Lambda_ref/2` `[E]`, for the primary and every required sensitivity.
Confirm numerically that the *feasible* region is **not** flat — the property that distinguishes unbalanced
from slack (M2).

### V-8 — A/B/C classification `[CRITICAL, tier T3]`

**Falsification test:** hand-construct decoded portfolios for each category — feasible-optimal, feasible-
suboptimal, and each *individual* constraint violated in isolation (cardinality only, one sector only,
budget only), plus multiple simultaneous violations — and assert the expected label. Include the boundary
cases `|x| = K ± 1`, `n_j = C` vs. `C + 1`, and `p'x = B` vs. `B + 1`.

**Falsified if:** any B is reported as C or vice versa. **B/C merging is the single most damaging possible
classification bug**, because H2 is defined on the C-rate alone `[SCOPE §16, §20]`.

### V-9 — Structural non-equivalence of the two encodings `[tier T3, adversarial]`

**Claim under test (M2):** unbalanced is not a reparameterization of slack.

**Falsification test:** attempt to construct an approved slack/unbalanced mapping whose marginalized
penalty functions agree at all residuals **in the actual reachable support of the instance**.

> **SCOPE CORRECTION (C0-07).** The claim must be stated over the *reachable* residual support, not "any
> parameters in any toy domain" — a match on a smaller artificial support would not collapse the general
> premise, so an unscoped test could produce a misleading refutation.
>
> **A sharper, instance-specific proof now supersedes the generic argument.** On Stage-1 sector residuals
> both `h = 1` and `h = 2` are reachable and *feasible*, so slack's marginalized penalty is 0 at both.
> Under the approved family with `v_sector = 1`, unbalanced's zero set is
> `zeta(h) = Lambda_ref[-a*h + (a*h)^2/2] = 0` iff `h = 0` or `h = 2/a` — so a single positive
> `a` can zero **at most one** nonzero residual: `a = 2` zeros `h = 1` but leaves
> `zeta(2) = +4*Lambda_ref`; `a = 1` zeros `h = 2` but leaves `zeta(1) = -Lambda_ref/2`. Verified in
> `verify_gate0_review_findings.py` (C0-07). This is a direct non-equivalence proof on the real instance and is
> strictly stronger than "a smooth quadratic cannot reproduce a kink".

**Falsified if** a matching pair is found on the reachable support. This is deliberately an attempt to
break our own claim, per the handoff's §8 instruction.

### V-10 — Tie detection `[CRITICAL, tier T2]`

**Falsification test:** construct instances with engineered exact degeneracy (e.g. two assets with
identical `mu`, identical `Sigma` rows/columns, identical price, same sector) and assert the tie is
detected and the grid point is classified `A` **only** if *all* tied states decode to feasible-optimal.
Construct the adversarial case where one tied state is feasible-optimal and another is infeasible, and
assert the point is **not** `A`.

**Falsified if:** a point with a mixed tie set is labelled `A`.

**Resolved by D015/D016 (U-14/U-17):** exact float equality is not used. The canonical binary64 encoded-energy
ledger forms `T_E` with D015's fixed scale-aware tolerance; a separate encoding-blind original-objective
comparator forms `OPT_f`. Primary `(c_H,c_f)=(2048,2048)` and the four one-factor diagnostics are fixed
before results, with D015's fail-closed oracle disposition and R-U14-1. D016 then deduplicates to `X_E`,
assigns atomic labels, and requires `exists C -> C`, else `all A -> A`, else `B`; its diagnostics cannot
replace the primary partition (R-U17-1). V-10 must test those exact rules, not implementation-selected
tolerances or tie semantics.

### V-11 — Precompute-once equivalence `[CRITICAL, tier T0 + T3]`

**Claim under test (M8):** the cached-array evaluation gives identical results to a direct, naive
per-grid-point evaluation.

**Falsification test:** on a coarse grid, evaluate both ways and assert bitwise-identical classifications
and energies within a stated float tolerance. This is only T0 against our own code, so it must be
*paired* with V-4's independent oracle on toy instances to have real force.

**Why it is listed as critical anyway:** the precompute optimization is exactly the kind of premature
optimization the handoff §6 warns about. The correctness-first ordering is: implement the naive path,
validate it (V-4), *then* add the cached path and prove equivalence. **Do not build the cached path first.**

### V-12 — Parameterization-bias check `[SCIENTIFIC VALIDITY, tier T2]`

The Scope Lock's literal `lambda_S = kappa^2/2` is superseded and must not be implemented. **D011** supplies
its dimensionally valid, non-primary curvature-match companion: for each inequality family,
`lambda_S,j^CM = lambda_2,j^CM = s_j*Lambda_ref/v_j^2` and
`lambda_1,j^CM = s_j*Lambda_ref/v_j` (equivalently `a=2`,
`Lambda_pen,j=s_j*Lambda_ref/2`).

**Claim under test:** at every normalized violation `w=|h|/v_j > 0`, D011's local gap is exactly
`[zeta_CM(-w*v_j)-P_slack(-w*v_j)]/Lambda_ref = s_j*w > 0`.

**Test:** independently reconstruct that identity algebraically and numerically on the predeclared coarse
subgrid, including at least one positive `w` for each inequality family. Falsified if the coefficients fail
the displayed curvature equality or any reconstructed gap has the wrong sign or magnitude.

The bounded curvature-match sensitivity pass `[SCOPE §14, §18, D011]` is a required companion to the
primary sweep. Its purpose is to report whether the qualitative conclusion changes under this **known-biased,
non-primary** anchor. Its exact coarse-subgrid extent must be predeclared before execution; it is never a
post-result substitute for D006 primary R2 or its `r in {0.5,2}` sensitivities.

### V-13 — Pre-registration integrity `[SCIENTIFIC VALIDITY, process]`

`[handoff §7]` No parameter range, Stage-2 protocol, classification rule, or analysis rule that could affect
the conclusion may be chosen after the corresponding results are inspected.

**Mechanism:** the grid definition, `s`-bounds, `Lambda_ref` definition, tie tolerance, D016 mixed-tie
partition/reporting rule, D013's ablation subset **and exact trigger**, and all Stage-2 protocol parameters are committed to `DECISIONS.md` with an
approval timestamp **before** the corresponding runner is executed. The runner writes the hash of the frozen
decision record into every result file. D014 separately fixes the ADNYE record/output hash contract; it
does not replace the result-file decision hash. **Falsified if** any result file references a decision hash
that postdates it.

This is the one validation item that cannot be checked by a unit test — it is checked by the audit trail.

### V-14 — Domain-expansion robustness `[SCIENTIFIC VALIDITY]`

`[SCOPE §14, §18]` Once the `s`-box is fixed, re-run at 0.5x and 2x the box. **Required, not optional.**
If the qualitative conclusion changes under expansion, the box was chosen too narrowly and the conclusion
is box-dependent — which is itself a reportable finding and must not be quietly resolved by re-picking
the box.

### V-15 — Objective-rescaling invariance `[CRITICAL, tier T2, NEW — from C0-01]`

**Claim under test:** the approved parameterization is genuinely objective-normalized.

**Falsification test:** rescale `f -> c*f` for `c` spanning several decades, recompute `Lambda_ref`, remap
all coefficients, and require **every** encoding's decoded ground state and A/B/C classification to be
invariant at every grid point.

**Falsified if** any decoded outcome changes. `[EXPERIMENTAL]` The *currently frozen* mapping **fails this
test** — verified: the unbalanced decoded ground state flips between `c = 2` and `c = 6` while slack's is
invariant. This test is therefore a live, known-failing gate that any replacement family (U-16) must pass
before implementation.

**This is the single most important new validation item**, because it is the one that would have caught
C0-01 automatically.

> **ANALYTIC RE-DERIVATION FOR THE APPROVED MAPPING (D004 + D005 + D006), 2026-08-23.** Verified in
> `research/audit/verify_d006.py` §5. The approved mapping passes V-15 **analytically**, term by term:
>
> - `a(s) = sqrt(1+2s) - 1` is **dimensionless** and depends only on the sweep coordinate `s`, so it is
>   **unchanged** by `f -> gamma*f`.
> - `v_j` (D005) is a **native residual** scale, in units `R`, not energy — also unchanged by `f -> gamma*f`.
> - `Lambda_ref` is an objective-energy scale (U-03), so `Lambda_ref -> gamma*Lambda_ref`.
> - Therefore `lambda_1,j = Lambda_ref*a/v_j -> gamma*lambda_1,j` and
>   `lambda_2,j = Lambda_ref*a^2/(2 v_j^2) -> gamma*lambda_2,j`, both **linear**; and slack's
>   `lambda_S,j = s*Lambda_ref/v_j^2 -> gamma*lambda_S,j`, also linear.
> - Every term of `Q` therefore carries exactly one factor of `gamma`, so `Q -> gamma*Q` for **both**
>   encodings and the argmin is invariant.
>
> This is the **homogeneity derivation** required by charter finding M3 — a proof over all `gamma > 0`,
> not a finite-decade regression. The decade-spanning numerical test above remains required as a
> **regression witness** against implementation drift.
>
> **Currency-rescaling invariance additionally verified** (`verify_d006.py` §6): under
> `prices, B -> beta*prices, beta*B` we have `h -> beta*h` and `v_j -> beta*v_j`, so `w = |h|/v_j` and
> the penalty **energy** are both invariant. **D005's rule is currency-unit invariant.**
>
> > **Do NOT state this as exclusive to D005.** `[Review P1]` An earlier draft of this paragraph asserted
> > exclusivity to D005 and failure under Option A:
> >
> > [RETRACTED:U15-2] "This holds only because D005 defines `v_j` as a native violation; it would fail under a fixed `v_ref = 1`."
> >
> > **The correct statement:** Option A, stated dimensionally as **one currency unit**, is dimensioned and
> > rescales with the currency, so it is **equally invariant**. Only an unphysical *dimensionless literal*
> > `1` would fail, and that is not Option A as stated. Rescaling is **not** a discriminator between the
> > U-15 options — see `U15_DECISION_MEMO.md` and D005's "Explicitly NOT claimed" list.
> > **D005 is selected on REACHABILITY, not on units or invariance.**

### V-16 — Mixed tie-set semantics `[CRITICAL, tier T3, NEW — from C0-03]`

**Falsification test:** construct toy QUBOs with tied ground-state sets of composition `A+B`, `A+C`, and
`B+C`, and assert every primary *and secondary* metric returns its precommitted value. Include a tied set
containing a feasible-optimal and an infeasible state, which must not be `A`.

**Falsified if** any secondary metric is undefined, or silently picks one representative.

### V-17 — Certified `alpha` bound `[CRITICAL, tier T2, NEW — from C0-05]`

**Claim under test:** the chosen `alpha` actually prevents a cardinality-violating state from being the
ground state.

> **REFRAMED after the reviewer C1-01.** An earlier draft required that *no* off-cardinality state be a ground
> state **at any grid point**. That is **incompatible with D002**: the approved 3-D design deliberately
> sweeps `s_card` from comfortably-non-enforcing to comfortably-enforcing, so off-cardinality ground states
> are an **expected Category-C outcome** in the weak-`s_card` region — exactly as weak inequality weights
> are expected to yield C. A universal prevention assertion would make the low-penalty corner of the
> approved landscape impossible by definition. The requirement is withdrawn.

**Falsification test (revised).** Two separate obligations:

1. **Classification correctness (all grid points).** The evaluator must *correctly identify* off-cardinality
   ground states as Category C. Falsified if any off-cardinality ground state is misclassified — never by
   its mere existence.
2. **Threshold certification (only where a threshold is claimed).** If any analysis asserts an enforcement
   threshold `s_card >= s*` above which cardinality is guaranteed satisfied, that threshold must be
   certified against **all `2^20`** states, accounting for the lower bounds of every other active penalty
   term — including the unbalanced encoding's *negative* rewards.

**Still explicitly withdrawn:** `alpha > Lambda_ref` as a sufficient criterion (C0-05). `Lambda_ref` is a
range over `F`, while cardinality-violating candidates live *outside* `F` where `f` is not bounded by it.

### V-18 — Residuals vs. an independent feasibility predicate `[CRITICAL, tier T3, NEW — from C0-07]`

**Falsification test:** write a hard-feasibility predicate (`|x| == K and all n_j <= C and p'x <= B`)
**independently** of the residual functions, and assert `h_card == 0 and all h_sector >= 0 and h_budget >= 0`
agrees with it on all `2^20` states.

**Why:** shared residual code removes duplication but not bias (C0-07). This is the check that makes the
shared-residual architecture safe.

---

## Toy-instance oracle design

Several tests above need instances small enough for true brute force. Proposed family, requiring approval:

| Parameter | Toy value | Reason |
|---|---|---|
| assets `n` | 5-8 | `2^n` enumerable; joint space with auxiliaries stays under `2^22` |
| sectors | 2-3 | exercises multi-sector independence (V-1) |
| `K` | 2-3 | keeps `F` non-empty and small |
| prices | small integers, and a float variant | float variant reaches the `.5` rounding tie in V-2 |
| register widths | 1-6 bits | spans under- and over-provisioned regimes |
| coefficients | `1e-6` to `1e6`, log-spaced | spans non-enforcing to strongly-enforcing |

**Design requirement:** at least one toy instance must have a **non-empty infeasible region reachable at the
QUBO ground state** for the unbalanced encoding, or V-8's Category-C path is never exercised.

---

## Independence requirements — what the reviewer should do rather than re-run our tests

Per the handoff §8, the strongest available validation is the reviewer *independently reconstructing* expected
behaviour rather than reviewing ours. Specifically requested:

1. **Independently derive** the closed-form minimizer `S*` from `[SCOPE §15]` without reading our
   implementation, and state whether you obtain `clamp(round(h), 0, 2^N - 1)`.
2. **Independently determine** the correct register widths from the Scope Lock plus the actual price vector,
   and state whether you get 19 auxiliary bits or 17 (U-06). We consider both defensible; we want your
   reconstruction before we see it argued.
3. **Attempt to construct a counterexample** to auxiliary-register independence (V-1) — in particular, any
   way the QUBO matrix assembly could introduce a cross-term between two registers.
4. **Attempt to construct an approved slack/unbalanced coefficient mapping** that makes the two encodings'
   marginalized penalties coincide (V-9), which would falsify M2.
5. **Independently re-run** `research/audit/verify_gate0_facts.py` and challenge any number in it. It uses
   only the standard library, so it needs no environment setup.

---

## What this document does NOT establish

- **No test in this document has been written or run.** This is a plan, not a result.
- The toy-instance family is proposed, not approved.
- Tier assignments are our judgment `[INFERENCE]` and are open to challenge.
- V-11's estimate of the precompute speedup is unbenchmarked `[INFERENCE]`.
