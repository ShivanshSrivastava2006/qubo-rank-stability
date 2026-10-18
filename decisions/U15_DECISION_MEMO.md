# U-15 DECISION MEMO — reference violation scale `v_ref,j`

**Status: APPROVED — OPTION B (D005, Shivansh, 2026-08-23).** `v_ref,j` is the smallest attainable positive
**native** violation over `x in {0,1}^20`; **not** gcd-defined. The **rule** is approved; the numeric
`(1, 1, 5)` remains **pending canonical-data assembly and verification at U-07/G2**. Approved scope of
record: `DECISIONS.md` D005. This memo is the supporting analysis, not the decision.
**Date:** 2026-08-22 · **Author:** the lead · **Verification:** `research/audit/verify_u15.py` (stdlib only)
**Did not resolve:** U-18(a) — consequences were *reported*, not acted on. **U-18(a) and U-18(b) were
subsequently approved as D006 (2026-08-23), selecting R2 at `r = 1`.** Still open: U-07, U-02, U-03, U-17.
**Options compared:** **A** global `v_ref = (1,1,1)` · **B** per-constraint `v_ref = (1,1,5)`
(cardinality, sector, budget).

---

## 1. Exact definitions and units

| Family | Residual | Units | Type |
|---|---|---|---|
| cardinality | `h_card(x) = sum(x) - K`, `K = 6` | count | **equality** — both signs are violations |
| sector (×4) | `h_sector,j(x) = C - n_j(x)`, `C = 2` | count | inequality, `h >= 0` feasible |
| budget | `h_budget(x) = B - p'x`, `B = 1100` | currency | inequality, `h >= 0` feasible |

`v_ref,j` must carry the **same units as `h_j`** for `w_j = h_j / v_ref,j` to be dimensionless. So:

- **Option A**: `v_card = 1 count`, `v_sector = 1 count`, `v_budget = 1 currency unit (one dollar)`.
- **Option B**: `v_card = 1 count`, `v_sector = 1 count`, `v_budget = 5 currency units (one gcd-lot)`.

The two options **differ only in the budget family**. Cardinality and sector are identical under both.

---

## 2. Normalized residual supports

`[EXPERIMENTAL]` Supports enumerated over the **primary domain, all `x ∈ {0,1}^20`** (the QUBO domain —
cardinality is soft and D002 sweeps `s_card`).

| Family | Native support | Option A `w = |h|/v` | Option B `w = |h|/v` |
|---|---|---|---|
| cardinality | `h ∈ [-6,14]`, step 1 | `|w|` integers, min 1 | identical |
| sector | `h ∈ {-3,…,2}`; infeasible `|h| ∈ {1,2,3}` | `w ∈ {1,2,3}` | identical |
| budget | 1068 distinct violations, min 5, max 5475, a **proper subset** of the multiples of 5 (27 unreachable) | proper subset of `{5,…,5475}` | proper subset of `{1,…,1095}` |

---

## 3. Scientific interpretation — and why B is not merely convenient

**Both options are "one unit of native constraint violation".** They disagree about **what the budget
constraint's native unit is.**

`[DERIVED, verified §3 of the script]` Define lot-units `p' = p/gcd`, `B' = B/gcd`. Then
`h'_budget = h_budget/gcd`, and **Option A applied in lot-units is exactly Option B**. So this is not a
choice between two normalization philosophies; it is a choice of the budget constraint's unit of account:

- **A:** the dollar — the unit the data happens to be written in.
- **B:** the **gcd-lot** — the actual quantum of expenditure in this instance. Because every price is a
  multiple of 5, expenditure moves in steps of 5; a one-dollar change in `p'x` is not a physically
  realizable event in this model.

**A's defect is therefore substantive, not aesthetic.** Under A the budget penalty is referenced to a
violation that **cannot occur**. `[SCOPE §14]`'s own justification for `v_ref` — *"the smallest nonzero
integer violation"* — is **factually false for budget** under A: the smallest reachable violation is 5.
A is defensible only if restated as *"one dollar, chosen as a conventional unit of account"*, abandoning
the smallest-violation justification the Scope Lock gives.

**B's weakness, stated plainly.** `gcd(prices) = 5` is a property of a price vector that the prototype
audit found to be **hand-chosen round numbers with no documented derivation from market data**
(`PROTOTYPE_AUDIT.md` F-4). So B's reference unit is contingent on a synthetic modelling artifact. If a
Stage-2 protocol resamples prices (U-09), the gcd could become 1 and `v_budget` would change between
instances — making `s` incomparable across the instance family. **This couples U-15 to U-09** and is a
genuine cost of B, addressed in §11.

---

## 4. Objective-rescaling behaviour

`v_ref` carries **residual** units, not energy. Under `f -> c*f`: `Lambda_ref -> c*Lambda_ref` while
`v_ref` is **unchanged**. Hence for both options:

```
lambda_S   = s*Lambda_ref / v^2        -> c * lambda_S
lambda_1   = Lambda_ref * a / v        -> c * lambda_1
lambda_2   = Lambda_ref * a^2 / (2v^2) -> c * lambda_2
```

**Both options preserve objective-rescaling invariance. U-15 is orthogonal to the V-15 test** and cannot
reintroduce the C0-01 defect.

**A second, distinct rescaling matters here** — of the *residual* unit (dollars → cents, `p -> beta*p`,
`B -> beta*B`). `[EXPERIMENTAL]`, `beta = 100`:

| Reading of `v_budget` | `w_min` before → after | invariant? |
|---|---|---|
| A as the literal **number 1** | 5 → 500 | NO |
| A as **one dollar** (dimensional) | 5 → 5 | **yes** |
| B as the smallest reachable violation | 1 → 1 | **yes** |

> **RECAST after review finding 2 — an earlier claim here is WITHDRAWN.** `v_budget = 1 currency unit` is
> **dimensioned**: under dollars→cents it is 100 cents, so **Option A stated as "one dollar" is already
> invariant**. Reading the printed numeral `1` as a dimensionless literal manufactures a failure the Scope
> Lock does not actually commit to.
>
> [RETRACTED:U15-2] **Withdrawn:** ~~"This is the same class of defect as C0-01."~~ A is **not** a residual-rescaling defect,
> and not of C0-01's class.
>
> **The real Scope Lock error is narrower and stands on its own:** §14 justifies `v_ref` as *"the smallest
> nonzero integer violation"*, and that justification is **factually false for budget under A** — the
> smallest reachable violation is 5, not 1. This is a **reachability and interpretation conflict, not a
> units failure.**

---

## 5. Smallest reachable positive normalized violation

| Family | Option A | Option B |
|---|---|---|
| cardinality | 1 | 1 |
| sector | 1 | 1 |
| **budget** | **5** | **1** |
| **equal across the two INEQUALITY families (sector, budget)?** | **NO** | **YES** |

Cardinality is listed for completeness only — it plays no part in the U-18(a) `r` comparison (§7).

---

## 6. What `v_ref` is intended to represent

Stating this explicitly, because the Scope Lock conflates two readings:

| Candidate meaning | Applies? |
|---|---|
| one unit of **native** constraint violation | **Both** — they differ on what the native unit is (§3) |
| the **minimum reachable** positive violation | **B only.** Under A this is true for cardinality and sector but **false for budget** |
| a common **energy/return** scale | **Neither.** That is `Lambda_ref` (U-03). `v_ref` is residual-valued |
| something else | — |

`[SCOPE §14]` asserts *both* of the first two simultaneously. That is self-consistent for cardinality and
sector, and **false for budget**. The contradiction is the whole of U-15.

---

## 7. Consequences for U-18(a) — reported, NOT resolved

> **SCOPE CORRECTION (review finding 1).** U-18(a)'s `r` applies **only to the Taylor-family inequality
> constraints — sector and budget.** Cardinality uses the shared equality term `alpha(s_card)*h_card^2` in
> **both** encodings and has **no `r` at all**. An earlier version of this section carried an `r_card`
> column; that was an error, and it contradicted `U18_DECISION_MEMO.md` §5, which states the same
> exclusion correctly. The comparison is **sector vs budget only** — and the central argument survives
> unchanged.

**Target-point matching** uses `r = 1/w0`. To target each *inequality* family's smallest *reachable*
violation:

| Option | `r_sector` | `r_budget` | common `r` possible? |
|---|---|---|---|
| A | 1 | **1/5 = 0.2** | **NO** |
| B | 1 | **1** | **YES**, at `r = 1` |

- **Is `w = 1` reachable?** Under A: yes for sector, **no for budget**. Under B: yes for both.
- **Does a common `r` stay meaningful?** Under **B**, yes — one `r` denotes the same *kind* of event (the
  minimum reachable violation) in both inequality families. Under **A**, a common `r = 1` targets a
  reachable event for sector and an **unreachable** one for budget, so the single symbol denotes different
  things per family.
- **Does branch-specific `r_j` become preferable?** Under **A**, effectively yes — one would need
  `r = (1, 1/5)`, which is *exactly* option B's common `r = 1` re-expressed. Under **B**, a common `r` is
  coherent and branch-specific `r_j` would need its own separate justification.

**Where U-15 has real content.** At matched `s` (`[EXPERIMENTAL]`, `Lambda_ref = 1`, `s = 1`, `a = 0.7321`):

| | `lambda_S,bud` | `lambda_1,bud` | ratio `lambda_1/lambda_S` |
|---|---|---|---|
| A (`v=1`) | 1.000000 | 0.732051 | 0.732051 |
| B (`v=5`) | 0.040000 | 0.146410 | **3.660254** |

`lambda_S` differs by `v^2 = 25×` and `lambda_1` by `v = 5×`, so **at fixed numerical `s` and `a`** the
budget family's slack-vs-unbalanced calibration differs by `v = 5×` between the options.

> **SCOPE (review finding 3).** These ratios are arithmetically correct **at fixed coordinates**. Whether an
> *allowed* one-coordinate rule `a = g(s)` preserves the relation is **precisely U-18(a)**, which is
> unresolved — the parent family can be reparameterized. So **no categorical claim is made** that the
> difference is unabsorbable across encodings. An earlier draft asserted that; it is withdrawn pending the
> U-18(a) mapping. What is established is the fixed-coordinate comparison only.

**This memo does not choose an `r`.** U-18(a) was at NO RECOMMENDATION when this was written;
**it was approved as D006 on 2026-08-23, selecting R2 at `r = 1`.**

---

## 8. Does per-constraint normalization change the scientific question?

**No — it changes the conditioning, not the question.** The locked question (rank stability of slack vs
unbalanced across a swept penalty landscape) is untouched; H0–H3 are unchanged in statement.

**But it is not "merely making the coordinates dimensionless" either.** Both options achieve
dimensionlessness (§4). What differs is *which penalty vectors are sampled at a given `s`*, and *how slack
and unbalanced are relatively calibrated for the budget family* (§7, the 5× ratio). Conclusions are
therefore conditional on the choice, and must be reported as such — the same standing caveat that attaches
to D004 and to U-18.

---

## 9. Three distinct things, deliberately separated

| | What it does | Achieved by |
|---|---|---|
| **Dimensional normalization** | makes `w = h/v` a pure number, so `a` can be dimensionless | **Both options.** Not a discriminator |
| **Residual-support normalization** | aligns the reference to an event the instance can actually exhibit | **B only.** A references an unreachable violation for budget |
| **Penalty-strength calibration** | sets how strong the penalty is at a given `s` | **Both, differently** — by `v^2` for slack, `v` for unbalanced, **at fixed numerical `s` and `a`**. Whether an *allowed* one-coordinate `a = g(s)` absorbs the difference **is U-18(a), unresolved** — see §7. No unconditional claim is made here |

Conflating the first two is what produced `[SCOPE §14]`'s false justification. Conflating the second and
third is what would make it tempting — illegitimately — to pick `v_ref` for its effect on results.

> [RETRACTED:U15-1] "not absorbed across families or across encodings"
> **CORRECTED after the reviewer U-15 pass 2, finding 1.** This earlier wording was an **unconditional** claim that
> contradicted §7 of this memo. **Withdrawn.** A full two-parameter reparameterization *can* match coefficient
> pairs per branch; whether an **allowed one-coordinate** mapping can is exactly the unresolved U-18(a) question.
> The defensible statement is the fixed-coordinate one only.

---

## 10. Selection basis

`[handoff §7]` **Neither option was evaluated for its effect on A/B/C outcomes, and no such evaluation
informed this recommendation.** No experiment has been run. The comparison rests only on: unit coherence,
reachability of the reference event, invariance behaviour, and cross-family commensurability. Every
statement in §7 is a *local* calibration fact; none is a claim about global A/B/C rates.

---

## 11. Recommendation

**PROPOSE Option B — per-constraint `v_ref = (1, 1, 5)`**, with `v_budget` defined as the **exact,
DP-derived smallest attainable positive budget violation** for the instance.

> **DEFINITION CORRECTED (review finding 5).** `v_budget` is **not** defined as `gcd(prices)`. The gcd is a
> **lower bound** only; equality is an **instance fact**, verified here: for Stage 1, `gcd = 5` **and** the
> exact DP-derived minimum attainable violation is **5**. Counterexamples where they differ, both verified:
> `prices=[10,10,10], B=15` → `gcd=10` but minimum violation `5`; `prices=[6,10,15], B=7` → `gcd=1` but
> minimum violation `3`. For any instance where the two diverge, `v_budget` follows the **exact attainable
> minimum**, or the decision is reopened.

**Grounds, in order:**

1. **The reference event is reachable in every family.** Under A the budget reference is a one-dollar
   violation that cannot occur, so `[SCOPE §14]`'s own stated justification for `v_ref` is false there.
2. **It makes the smallest reachable normalized violation equal (`= 1`) across all three families**,
   which is precisely what makes a *common* `r` in U-18(a) denote the same kind of event everywhere.
   Under A the equivalent effect requires `r = (1,1,1/5)` — i.e. B re-expressed, with the normalization
   smuggled into `r` instead.
3. **A and B are both invariant under a change of currency unit when stated dimensionally**
   `[review finding 2]` — this is *not* a discriminator. What distinguishes them is that A must abandon
   §14's smallest-violation justification and fall back on "one dollar as a conventional unit of account",
   whereas B's reference *is* the smallest attainable violation.
4. **It is Option A honestly applied**, in the budget's actual unit of account (§3) — not a new mechanism.

### Conditioning assumptions attached to this recommendation

1. **`c_j` must not be used to compensate for this choice** (The reviewer's standing instruction), and neither
   must `r`. U-15 is settled on its own merits here.
2. **Requires an explicit U-09 decision — but incomparability is NOT automatic** `[review finding 4]`.
   If Stage 2 resamples prices, the minimum attainable violation may change per instance. `s` would then be
   incomparable **in absolute currency terms**, but could remain comparable **in each instance's own
   normalized lattice units**. Which of those the study needs depends on the **Stage-2 estimand**, which is
   not yet defined. So: U-09 must decide explicitly; do not treat cross-instance incomparability as
   automatic. My standing U-09 recommendation (resample `mu`/`Sigma` only, keep `p`, `K`, `C`, `B` fixed)
   side-steps the question entirely by holding the reference constant.
3. **`v_budget = 5` is contingent on a synthetic price vector.** The prices are hand-chosen round numbers
   with no documented market derivation (`PROTOTYPE_AUDIT.md` F-4). This must be stated in any write-up:
   the budget normalization is a property of the constructed instance, not of portfolio optimization.
4. **Conclusions remain conditional on this choice**, per §8. It does not become canonical by being
   approved.
5. **It does not resolve U-18(a).** It removes one obstacle (a common `r` becomes coherent); the choice of
   `r` remains an external conditioning decision with no recommendation.

### If Option A is preferred instead

It must be **restated dimensionally** as "one dollar, a conventional unit of account" (§4), the
smallest-violation justification in `[SCOPE §14]` must be **explicitly withdrawn for budget**, and U-18(a)
should then expect **branch-specific `r_j`** rather than a common `r` (§7).

---

## What this memo does NOT establish

- It does not resolve U-18(a), U-07, U-02, U-03 or U-17.
- It makes no claim about A/B/C rates; §7's figures are local calibration facts.
- It does not establish that `gcd` is the right notion of "native unit" for any *other* instance — only
  for this one, where every price is a multiple of 5.
- No independent party has audited it. independent audit requested.
