# UNRESOLVED SCIENTIFIC DECISIONS — Gate 0

**Status:** Open. **None of these is decided.** Recommendations below are recommendations, not approvals
`[handoff §4H]`.
**Date:** 2026-08-22

Each item states: why it matters, the options, advantages/disadvantages, **bias risk**, and a
recommendation where we have one. Items marked **BLOCKING** must be resolved before the corresponding
implementation stage can begin.

Approval is recorded in `DECISIONS.md`, not here. An item moves out of this file only when it has an
approver and a date.

---

## U-01 — Grid dimensionality ~~BLOCKING~~ **CLOSED 2026-08-22 — see SCOPE_AMENDMENT_001**

> **CLOSED. Approved: 3-D joint grid `(s_card, s_sector, s_budget)`, formally recorded as a SCOPE
> AMENDMENT to §14/§25 — not as an interpretation.** Both the earlier Claude recommendation and the Codex
> audit implied a 3-D vector would preserve the frozen scope; **both were wrong**, since §25 explicitly
> freezes `s` as a single scalar. Every option departs from some frozen text. Full reasoning, exact
> per-constraint mappings, and the H3 relationship: `research/decisions/SCOPE_AMENDMENT_001.md`.
> Original analysis retained below for provenance.

**Why it matters.** This determines what experiment is actually run. It changes the primary metric's
denominator `|Lambda|`, whether H3 is testable at all, and the entire shape of the result.

**The ambiguity is in the frozen document itself.** `[SCOPE §14]` defines a **single** scalar `s`:
"`s` — not `lambda_S` or `kappa` directly — is the swept quantity." But `[SCOPE §18]` requires a
"**Joint grid** over the shared dimensionless `s` ..., **not one-parameter-at-a-time sweeps**" — and a
single scalar swept alone *is* a one-parameter sweep. And `[SCOPE §22]` defends the design with "Why three
coefficients? They correspond to three structurally different constraint types."

These three statements cannot all be literally true at once. This is the single most consequential
unresolved item in the project.

**Options.**

| # | Design | `|Lambda|` at 50 pts/axis | Assessment |
|---|---|---|---|
| 1 | One shared `s` for everything | 50 | Literal reading of §14. But it is a one-parameter sweep, contradicting §18, and makes H3 untestable inside the sweep — all constraints move together, so "does robustness differ by constraint type" cannot be asked |
| 2 | `alpha` fixed; joint 2-D grid over `(s_sector, s_budget)` | 2,500 | Satisfies §18's "joint, not one-at-a-time". Tests H3 across the two *inequality* types — which are the only constraints the two encodings treat differently. Keeps the equality penalty out of a contrast where it does not belong |
| 3 | Full 3-D grid over `(s_card, s_sector, s_budget)` | 125,000 | Most literal reading of §22's "three coefficients". Largest evidence base |

**Compute is not a discriminator.** `[EXPERIMENTAL]` Measured on this machine with the precompute-once
architecture (§F.4): ~8.8 ms per grid point for slack, ~68 ms for unbalanced (the latter is unoptimized and
reducible to slack's cost by caching `sum_j h_j` and `sum_j h_j^2`). Even the full 3-D grid runs in
~18 min (slack) + ~142 min (unbalanced). **All three options are affordable**, so this must be decided on
scientific grounds alone.

**Argument for fixing `alpha` (relevant to options 2 vs. 3).** Cardinality is an **equality** constraint,
penalized by the *identical* term `alpha(sum x - K)^2` in **both** encodings `[SCOPE §13]`. It is not part of
the encoding contrast: changing `alpha` moves both encodings' energy landscapes the same way. Sweeping it
adds an axis along which the two encodings are, by construction, treated identically.

**Counter-argument.** `alpha` is not perfectly neutral: it determines how strongly `|x| != K` states are
suppressed, and those states are exactly where the two encodings' inequality penalties differ most (and
where U-06's register-width question bites). So a fixed `alpha` should be accompanied by a sensitivity check.

**Bias risk.** HIGH in one specific direction: choosing option 1 after seeing that a 1-D sweep produces a
cleaner story would be post-hoc design. Choosing the dimensionality **before** any result is inspected is
mandatory `[handoff §7]`. There is also a subtler risk in option 2 — fixing `alpha` at a value that happens
to favour one encoding. This is mitigated by the sensitivity check, not eliminated.

**Recommendation.** Option 2: fix `alpha` (value per U-13), sweep a joint 2-D grid over
`(s_sector, s_budget)`, and run a bounded `alpha`-sensitivity check on a coarse subgrid. Rationale: it is
the only option that satisfies §18's "joint, not one-at-a-time" while keeping the swept axes confined to the
constraints the two encodings actually encode differently.

> **REFRAMED per Codex C0-06.** Codex's independent reconstruction reads §18+§22 as most strongly
> supporting a **joint three-family vector**, treating §14's scalar notation as ambiguous shorthand. Codex
> and Claude therefore **disagree**, and Codex's stronger point stands regardless of who is right:
>
> **A fixed-`alpha` 2-D grid is a SCOPE AMENDMENT, not an implementation interpretation.** It cannot be
> adopted as "merely reading §14 sensibly". It requires explicit human approval as a change to the frozen
> scope. If the scope is to be preserved without amendment, freeze the **3-D** vector and define the
> cardinality coordinate's mapping explicitly.
>
> `[EXPERIMENTAL]` Compute does not discriminate: the reproducible benchmark
> (`research/audit/benchmark_gridpoint.py`) measures 8.2 ms/point (slack) and 17.7 ms/point (unbalanced,
> cached), so even the 3-D `50^3` grid costs ~17 min + ~37 min. **This is a purely scientific decision.**

---

## ~~U-02 — Value of `kappa_risk` (risk aversion)~~ **CLOSED — APPROVED as D007 (Shivansh, 2026-08-23)**

> **CLOSED.** `kappa_risk = ( 1.0 , (decimal simple daily return)^-1 , daily )`, approved as an
> **indivisible (value, unit, period) triple** — the scalar alone does not name a model, because
> `R' = c*R` implies `kappa_risk' = kappa_risk / c` (decimal `1.0` == percentage `0.01`; percentage
> `1.0` is a *different*, 100x more risk-averse model). Horizon policy: native sampling period, **no
> annualization or other conversion** absent a separately approved aggregation model. **U-02 fixes the
> period; U-07/G2 builds the canonical series at it and verifies conformance.** Pre-declaration
> **R-U02-2 accepted**: a large or degenerate `X*` at G3 is **not** grounds to revisit `kappa_risk`.
> A bounded sensitivity probe was **deferred, not approved** — the study will produce **no** sensitivity
> evidence for `kappa_risk`. Authoritative scope: `DECISIONS.md` **D007**. Supporting analysis:
> `U02_DECISION_MEMO.md` (revision 5). **The analysis below is retained as the pre-approval record and
> is NOT rewritten; where it differs from D007, D007 governs.**

> **SUPERSEDED IN THE TEXT BELOW.** The "Recommendation" paragraph calls `1.0` "a neutral, round value
> in the middle of the prototype's own swept range". **D007 adopts none of that wording.** `1.0` is the
> 5th of the 6 prototype values and is the interval midpoint on only one of four readings of "middle";
> and "neutral" is reserved in this project for the D006 conditioning sense. D007 records the ground of
> choice as **outcome-independent provenance** plus **structural symmetry across encodings**, and
> nothing else. See `U02_DECISION_MEMO.md` SS5.2-5.3.

**Why it matters.** `kappa_risk` sets the objective `f(x)`, hence `x*`, hence `Lambda_ref`, hence the entire
`s` mapping. Everything numeric downstream depends on it.

**Current state.** `[SCOPE §12]` treats it as a fixed scalar but never fixes it, noting only that its value
"lives in the prototype's data files" — it does not. `[PROTOTYPE cell 14]` **sweeps** it as
`lambda in {0.1, 0.3, 0.5, 0.75, 1.0, 2.0}`. So there is no inherited value to adopt.

**Options.** (a) Fix at a single value (e.g. 1.0) and hold it constant across all instances and grid points.
(b) Treat it as an additional experimental axis. (c) Choose it so the constraints bind "interestingly".

**Assessment.** (b) multiplies the whole study by 6 and is outside the frozen scope — the Scope Lock's
swept quantity is the *penalty* landscape, not risk aversion. (c) is **methodologically dangerous**: choosing
`kappa_risk` by looking at what makes results interesting is precisely the post-hoc design `[handoff §7]`
forbids.

**Bias risk.** HIGH for option (c). LOW for (a) provided the value is fixed before any result is seen and
the choice is justified on grounds independent of the outcome.

**Recommendation.** Option (a) with `kappa_risk = 1.0` — a neutral, round value in the middle of the
prototype's own swept range, chosen for being unremarkable rather than for any property of the result.
Report it prominently as a fixed conditioning parameter, and state in any write-up that conclusions are
conditional on it. **Needs approval before Lambda_ref can be computed.**

---

## ~~U-03 — Definition of `Lambda_ref`: range or standard deviation?~~ **CLOSED — APPROVED as D008 (Shivansh, 2026-08-24)**

> **CLOSED.** `Lambda_ref = max_{x in F} f(x) - min_{x in F} f(x)` — the **range**, over `F` defined by
> the **predicate** `{ x in {0,1}^20 : sum_i x_i = K, n_j(x) <= C, p^T x <= B }`. Units `E`.
> **RULE ONLY — no numeric value is approved;** the number is a prospective **ADNYE** record executing at
> `G3.compute_Lambda_ref`. `Lambda_ref = 0` is a **G3 stop condition**. **R-U03-2 accepted.** All
> considered candidates to be **reported at G3 for transparency only, never re-selection.**
> Authoritative scope: `DECISIONS.md` **D008**. Supporting analysis: `U03_DECISION_MEMO.md` (revision 4).
> **The analysis below is retained as the pre-approval record and is NOT rewritten.**

> **TWO CORRECTIONS TO THE TEXT BELOW.** (1) Its **bias rating of "LOW-MEDIUM" understates the choice.**
> `Lambda_ref -> gamma*Lambda_ref` with `s -> s/gamma` leaves slack's `lambda_S` exactly invariant but
> sends unbalanced's **`lambda_2 -> lambda_2/gamma`**, so U-03 is a **physical choice for the unbalanced
> encoding that U-04 CANNOT compensate for** — not merely a rescaling of the `s` axis. (2) Its
> **assessment argues that the cardinality-feasible set "includes portfolios the constraints are meant to
> exclude"; D008 does NOT adopt that reasoning** — on a sufficiency reading those are exactly the
> portfolios a penalty must outweigh. D008's grounds are interpretability, completeness, and the fact
> that under D002 all three families are swept. Its request to report candidates "in the Gate-2 data
> artifact" is also **misplaced: `Lambda_ref` is a statistic of `f` and cannot exist before G3.**
> See `U03_DECISION_MEMO.md` SS3.3, SS5.1, SS5.2.

**Why it matters.** `[SCOPE §14]` says "`Lambda_ref` = range (**or std**) of `f(x)` over the feasible set" —
two different numbers, typically differing by a factor of several. Since `lambda_S(s) = s * Lambda_ref` and
`kappa(s) = s * Lambda_ref`, the choice **rescales the entire `s` axis**. It does not change the *shape* of
the landscape, but it changes which numeric `s`-bounds correspond to "comfortably non-enforcing" and
"comfortably enforcing", so it interacts directly with U-04.

**Additional ambiguity, not flagged in the Scope Lock:** "over the feasible set" — which set? `F` (all three
constraints, `|F| = 976` `[EXPERIMENTAL]`) or the cardinality-feasible set (38,760)? The two give different
values. §14 says "the 38,760-portfolio feasible set" in one place and "the feasible set" in another.

**Options.** (1) range over `F`; (2) std over `F`; (3) range over cardinality-feasible; (4) std over
cardinality-feasible.

**Assessment.** Range is more directly interpretable as "the objective scale a penalty must overcome" and
is what makes `s ~ 1` mean "penalty comparable to the whole objective spread". Std is more robust to a
single outlier portfolio but has no natural "enough to overcome the objective" reading. Range over `F` is
the tightest and most meaningful denominator; range over the cardinality-feasible set is larger and includes
portfolios the constraints are meant to exclude.

**Bias risk.** LOW-MEDIUM. It rescales both encodings' axes identically, so it cannot favour one encoding
directly. The risk is indirect: a poor choice pushes the interesting transition region outside the chosen
`s`-box (U-04).

**Recommendation.** Range over `F`. Report the value of all four candidates in the Gate-2 data artifact so
the choice is transparent and the sensitivity is visible.

---

## ~~U-04 — Numeric `s`-domain bounds~~ **CLOSED — APPROVED as D010 (Shivansh, 2026-08-24)**

> **CLOSED, RULE ONLY.** Common cube on all three axes with
> `s_max = 10^(ceil(log10 rho) + 1)`, `s_min = 10^(floor(log10 rho) - 4)`,
> `rho = Delta_full / Lambda_ref`, `Delta_full = max_{x in {0,1}^20} f(x) - min_{x in {0,1}^20} f(x)`.
> **`Delta_full` is EXPRESSLY AUTHORIZED by D010 as the rule's second input** — D008 admits it for
> transparency reporting **only**, which is not authority to make it load-bearing.
> **`m_hi = 1` is DERIVED** (worst pre-registered mapping `r = 2`: `s_2(rho) = (rho-1)+sqrt(2rho+1)`,
> `sup s_2/rho = sqrt(3)`); **`m_lo = 4` is a recorded JUDGEMENT CALL.**
> The **numbers** are a prospective **ADNYE** record at `G3.exit.resolve_box` with **two** named inputs.
> **Option (c) — calibrating after seeing the transition — remains DISQUALIFYING.**
> Authoritative scope: `DECISIONS.md` **D010**. Supporting analysis: `U13_U04_DECISION_MEMO.md` rev 3.
> **The analysis below is retained as the pre-approval record and is NOT rewritten.**

> **ONE CORRECTION TO THE TEXT BELOW.** Its option (b) framing treats U-04 as a *numbers* decision.
> **D010 is rule-first**: numbers-first carries a trap with no exit — if `rho` exceeds a frozen `s_max`,
> the box misses the transition and the only repair is the disqualifying option (c).


**Why it matters.** These bounds *are* the sampled landscape. `[SCOPE §14, §25]` explicitly marks them
NOT YET FIXED and preserves only the principle: "comfortably-non-enforcing to comfortably-enforcing,
relative to `Lambda_ref`".

**Options.** (a) Derive analytically: pick `s_min` such that the penalty for a unit violation is provably
negligible against the objective range, and `s_max` such that it provably dominates. (b) Pick round numbers
spanning many decades (e.g. `1e-3` to `1e3`). (c) Calibrate by inspecting where the transition occurs.

**Bias risk.** **(c) is disqualifying.** Choosing bounds after seeing where the transition happens is
exactly the post-hoc methodology `[handoff §7]` forbids, and it would make the primary metric
`rho = |A| / |Lambda|` meaningless — that ratio is trivially manipulable by choosing how much
uninteresting territory to include on either side. **This is the metric's central weakness and must be
stated in any write-up.**

**Recommendation.** (a), with the derivation written down *before* execution, cross-checked against (b) for
sanity, and followed by the mandatory 0.5x/2x domain-expansion check `[SCOPE §14, §18]`. If the qualitative
conclusion changes under expansion, that is a finding to report, not a reason to re-pick the box.

---

## U-05 — Grid resolution and log-spacing base

**Why it matters.** Resolution sets `|Lambda|`, hence the denominator of the primary metric, and determines
whether a narrow rank-flip region (H1) is resolvable at all. Too coarse and a real crossover is missed; too
fine and nothing is gained but runtime.

**Bias risk.** MEDIUM. Refining the grid *after* seeing a boundary, in order to sharpen a story, is post-hoc.
Fix resolution up front; if refinement is later needed, report it explicitly as a second, separately-declared
pass.

**Recommendation.** Fix a base-10 log grid at a stated points-per-decade (e.g. 10/decade) rather than a
fixed total count, so that resolution is invariant to the U-04 bound choice. `[EXPERIMENTAL]` compute is not
a constraint (see U-01), so choose resolution on resolving-power grounds.

> **CLOSED — D012, 2026-08-25.** Shivansh approved `P=10` **log intervals** per decade, base-10, on all
> three axes, endpoints included, and accepted R-U05-1: any later refinement is separately declared and
> additionally reported, never a replacement. The original analysis above is retained as pre-approval
> provenance; D012 is authoritative.

---

## U-06 — Slack register domain: 39 or 37 QUBO variables? ~~BLOCKING~~ **CLOSED 2026-08-22**

> **CLOSED per Codex C0-06, which independently derived the same result.** The QUBO's domain is all of
> `{0,1}^20` (cardinality is soft), so the budget register must represent `h = 1100` at `x = 0` -> 11 bits
> -> 19 auxiliary -> **39 variables, fixed by the Scope Lock**. The 37-variable variant is a *different,
> narrow-domain formulation*, not a competing reading, and must not be reported as a comparable headline
> variable count. No decision is required. Original analysis retained below for provenance.

**Why it matters.** Three ways.
1. Variable count is a **reported secondary metric** `[SCOPE §17]` — "20 for unbalanced vs. 39 for slack" is
   the headline qubit-overhead comparison.
2. It changes whether the slack encoding can represent zero penalty for every budget-feasible `x`.
3. It may change the ground state at small `alpha`, where `|x| != K` states are not strongly suppressed.

**The two readings** `[EXPERIMENTAL]`:

| Reading | Domain the register must cover | max `h_budget` | bits | aux total | QUBO vars |
|---|---|---|---|---|---|
| A | all `x in {0,1}^20` (`x = 0` gives `h = B`) | 1100 | 11 | 19 | **39** |
| B | only cardinality-feasible `x` (`|x| = K`) | 500 | 9 | 17 | **37** |

`[SCOPE §13, §15, §25]` asserts 19 aux bits / 39 variables throughout, which matches **reading A**. Our
independent computation confirms A is self-consistent: `ceil(log2(1100+1)) = 11`.

**Assessment.** Reading A is correct *if* one requires the encoding to be exact over the QUBO's actual
domain — which is all of `{0,1}^20`, since cardinality is enforced only softly by a penalty, not as a hard
restriction. Reading B is a legitimate tightening only if one is willing to accept that states with
`|x| < K` may carry a spurious residual penalty. Since those states are already penalized by `alpha`, the
practical effect may be nil — but "may be nil" is not a proof, and it becomes load-bearing exactly when
`alpha` is small (U-13).

**Bias risk.** LOW-MEDIUM, but in a specific direction: the smaller register makes slack look cheaper
(37 vs. 39) on a *reported metric*, while potentially making it less exact. Choosing the tighter number
because it flatters slack's overhead would be a bias. Choosing it for correctness reasons is fine.

**Recommendation.** Keep **reading A (39 variables)**, matching the Scope Lock, because it is the reading
under which the slack encoding is exact over the QUBO's true domain — and exactness is the property the
whole certification argument rests on. Additionally, **verify empirically** (test V-5, narrow-register
variant) that no feasible `x` carries a nonzero slack penalty under A, and report the 37-variable figure as
a footnote for transparency.

---

## ~~U-07~~ — Canonical data assembly, given the prototype ordering defect **CLOSED 2026-08-25**

**Why it matters.** `[EXPERIMENTAL]` `mu`/`Sigma` are alphabetically indexed while `prices`/`sector_map` are
sector-grouped, and the prototype never reindexes — 18 of 20 positions are mis-joined (see
`research/audit/PROTOTYPE_AUDIT.md`). We must decide what instance this project actually studies.

**Options.**

| # | Choice | Assessment |
|---|---|---|
| 1 | **Corrected join** — reindex `mu`/`Sigma` by ticker onto the sector-grouped universe | Real assets carry their real returns, prices, and sectors. Financially meaningful. **Differs numerically from every prototype output** |
| 2 | **Reproduce the defect** — keep the positional mis-join | Preserves exact continuity with prototype numbers. Studies a synthetic instance with mislabelled assets |
| 3 | Treat the data as an anonymous synthetic instance; drop ticker labels entirely | Honest about what is being studied; discards the financial framing |

**Assessment.** The research question is about **encodings**, not about real finance. Any fixed
`(mu, Sigma, p, sectors)` tuple is a mathematically valid test instance, so all three options can support a
valid experiment. But option 2 requires knowingly publishing an instance whose asset labels are wrong, and
option 3 discards the portfolio framing that the Scope Lock's title and §12 rest on.

**Bias risk.** LOW for the encoding comparison itself — the defect does not favour either encoding, since
both read the same instance. **HIGH for scientific presentation**: reporting sector-constrained portfolio
results where "Technology" contains ABBV and CAT would be a serious misstatement.

**Recommendation.** Option 1 (corrected, ticker-keyed join), with the defect and the correction documented
in the audit record and the provenance chain. Additionally, **record the corrected instance's `x*` and
`|F|`** and note that these will not match any prototype output — so that a future reader does not mistake
the divergence for a new bug. `[EXPERIMENTAL]` `|F| = 976` is unaffected by this choice, since the feasible
set depends only on prices, sectors, `K`, `C`, `B` — none of which is mis-joined relative to each other.

---

## U-08 — Stage-2 RNG seed policy **BLOCKING for Stage 2**

`[SCOPE §19, §25]` NOT YET FIXED. `[SCOPE §19]` requires it be fixed "before running anything, so it isn't
chosen post hoc to favor a result", and notes this is currently "a commitment, not yet an executed fact".

**Why it matters.** Unfixed seeds make Stage 2 irreproducible and, worse, allow (even unintentional)
seed selection that favours a conclusion.

**Options.** (a) one fixed master seed, per-instance seeds derived deterministically; (b) a published list
of explicit per-instance seeds; (c) seed from instance index.

**Bias risk.** HIGH if unfixed. Trying several seeds and keeping the informative ones would be fabrication
of evidence.

**Recommendation.** (a) with `numpy.random.default_rng` (PCG64), one master seed recorded in `DECISIONS.md`
before generation, per-instance streams via `SeedSequence.spawn`. Commit to the **number of instances in
advance** (U-11) so there is no discretion to stop when the picture looks good.

---

## U-09 — Stage-2 `mu` / `Sigma` generation protocol **BLOCKING for Stage 2**

`[SCOPE §19]` NOT YET FIXED beyond the principle "resample with a fixed random seed protocol".

**Why it matters.** Determines what "robustness across instances" actually means. It also has a hidden
interaction: **if prices are resampled as non-integers, `v_ref = 1` loses its justification** (`[SCOPE §14]`
grounds `v_ref = 1` in all residuals being integer-valued) and the closed-form minimizer's `round()` acquires
genuine `.5` ties (validation V-2). The Scope Lock does not appear to note this coupling.

**Options.** (a) parametric resampling from a fitted distribution; (b) bootstrap from the underlying
historical data — **not available**, only `mu.csv`/`Sigma.csv` survive, so `CANNOT VERIFY` whether the raw
series can be recovered; (c) structured perturbation of the Stage-1 `mu`/`Sigma`.

**Bias risk.** MEDIUM-HIGH. A protocol that produces near-identical instances would make Stage 2 look
confirmatory while testing nothing.

**Recommendation.** No recommendation yet — this needs a decision on whether prices are resampled at all.
**Explicitly recommend keeping prices, `K`, `C`, `B` fixed at Stage-1 values** and resampling only
`mu`/`Sigma`, which preserves integrality (protecting `v_ref = 1` and V-2) and keeps `|F|` and the register
widths constant across Stage 2, isolating the return/covariance draw as the only varying factor. This
recommendation conflicts with `[SCOPE §18]`'s "varying the return/covariance draw **and sector assignment**"
— see U-10.

---

## U-10 — Stage-2 sector reassignment **BLOCKING for Stage 2**

`[SCOPE §19]` NOT YET FIXED. `[SCOPE §18]` requires varying sector assignment.

**Why it matters.** Sector assignment changes `|F|` and the sector constraint's tightness, so it changes the
problem's difficulty — potentially confounding "encoding robustness varies" with "instance difficulty
varies".

**Options.** (a) random permutation of the sector labels across assets; (b) structured reshuffling keeping
5 assets per sector; (c) hold sectors fixed and vary only `mu`/`Sigma`.

**Bias risk.** MEDIUM. Under (a), a permutation producing a near-empty or near-trivial feasible region would
distort the aggregate.

**Recommendation.** (b), constrained to keep exactly 5 assets per sector (preserving the balanced structure),
with a **feasibility guard** (U-11). Report `|F|` for every Stage-2 instance as a difficulty covariate so
that difficulty variation is visible rather than hidden.

---

## U-11 — Stage-2 feasibility handling and instance count **BLOCKING for Stage 2**

`[SCOPE §19]` NOT YET FIXED — "no explicit rejection-sampling or repair procedure ... was specified".
Count is "4-6" `[SCOPE §19, §25]`.

**Why it matters.** A degenerate instance (empty `F`, or `F` so small the optimum is forced) contributes
nothing but is silently averaged in. Rejection sampling is the obvious fix but is itself a filter that can
bias the instance family.

**Bias risk.** HIGH if the rejection criterion is chosen after seeing instances. Also **HIGH if the count is
left as a range** — "4-6" permits stopping at 4 when the picture is clean or extending to 6 when it is not.

**Recommendation.** Fix an **exact** count (not a range) before generation. Define the feasibility guard as
an explicit, pre-declared predicate on `|F|` (e.g. `|F| >= some floor`), applied by rejection-and-reseed,
with every rejected seed **logged** so the filter's effect is auditable.

---

## ~~U-12 — Constraint-ablation subset~~ **CLOSED — APPROVED as D013 (Shivansh, 2026-08-25)**

> **CLOSED.** D013 approves the exact conditional set `{C, CB, CS, CSB}`, the all-three exact-sign
> trigger over D006 `r={0.5,1,2}`, active-axis D008/D010/D012 coordinates, the applicable D006/D011/V-14
> package, and R-U12-1. It remains a conditional non-primary follow-up; U-14/U-17, D011's coarse extent,
> and the V-14 reading are separate prerequisites. Authoritative scope: `DECISIONS.md` **D013**. Supporting
> analysis: `U12_DECISION_MEMO.md` rev 3. **The analysis below is retained as the pre-approval record and
> is NOT rewritten.**

`[SCOPE §18]` The ablation set (cardinality-only, +budget, +sector, all-three) is carried forward, but "the
exact minimum useful subset ... was not finally pinned down", to be decided "only if Stage 1/2 results are
ambiguous". `[SCOPE §25]` lists the full matrix as explicitly **not** committed core scope.

**Tension.** Deciding an ablation subset *after* seeing that Stage 1/2 is ambiguous is conditioning a design
choice on observed results — the pattern `[handoff §7]` forbids. The Scope Lock authorizes it, so this is a
**conflict between two frozen instructions**, not something to resolve unilaterally.

**Bias risk.** MEDIUM-HIGH. Mitigated substantially if the *trigger condition* and the *subset* are both
pre-declared, so that only the trigger's firing depends on results, not the design.

**Recommendation.** Pre-declare now: (i) the exact ablation subset that would be run, and (ii) the explicit,
quantitative condition under which it fires. Then results determine only *whether* a pre-specified analysis
runs, never *what* it is. Flag this to Codex as a genuine tension worth an independent opinion.

---

## ~~U-13 — Treatment and value of `alpha`~~ **CLOSED — APPROVED as D009 (Shivansh, 2026-08-24)**

> **CLOSED.** `alpha(s_card) = s_card * Lambda_ref / v_card^2`, applied **identically in both encodings**.
> **This map was ALREADY APPROVED on 2026-08-22** under D002 via `SCOPE_AMENDMENT_001.md` §3. D009 does
> **not** re-approve it: it (a) propagated the map into `IMPLEMENTATION_SPEC.md` §C.6, which had omitted
> it while §C.4 defined only the penalty *form*; (b) approved asserting **NO** cardinality-enforcement
> threshold, leaving **V-17 obligation 1 unconditional** and **obligation 2 untriggered but binding**;
> (c) recorded that `v_card = 1` and `v_sector = 1` are **EXACT** while only `v_budget = 5` is
> pre-canonical; (d) clarified that D006's exclusion of cardinality does **not** remove `v_card`.
> Authoritative scope: `DECISIONS.md` **D009**. Supporting analysis: `U13_U04_DECISION_MEMO.md` rev 3.
> **The analysis below is retained as the pre-approval record and is NOT rewritten.**

> **TWO CORRECTIONS TO THE TEXT BELOW.** (1) Its title asks for a **value**; D002 made `s_card` a swept
> axis, so `alpha` is a **function**, and the function was already fixed. (2) Its **MEDIUM** bias rating
> rests on "*an `alpha` too small lets `|x| != K` states reach the ground state*" — under D002 that is a
> **deliberately sampled corner**, not an error, and V-17's reframing makes those Category-C outcomes
> **expected**. The residual risk is the `s_card` **lower bound** (a U-04 concern, now D010), not `alpha`.


**Why it matters.** Interacts with U-01 (is it an axis?) and U-06 (register adequacy off the `|x| = K`
shell). `[PROTOTYPE cell 14]` fixes `alpha = 20`, described in `[PROTOTYPE cell 15]` as "selected empirically
to ensure the cardinality penalty strongly dominates". That justification was made for a model enumerated
**only over `|x| = K`**, where the term is identically zero — so **the prototype's `alpha = 20` was never
actually exercised** and carries no validation weight here.

**Bias risk.** MEDIUM. An `alpha` too small lets `|x| != K` states reach the ground state, where the two
encodings differ most and where U-06's register question bites.

**Recommendation — CORRECTED per Codex C0-05.** Do not inherit `alpha = 20` on the prototype's authority.

> **The earlier recommendation `alpha > Lambda_ref` is WITHDRAWN as insufficient.** `Lambda_ref` is a range
> computed **over `F`**, and cardinality-violating candidates live **outside `F`**, where `f` is not bounded
> by that range. The bound also ignores the *negative* rewards the unbalanced encoding supplies on the
> inequality terms, which can offset a cardinality penalty.

A sufficient criterion must compare **every** off-cardinality `x` against the best cardinality-feasible
candidate, including the lower bounds of every other active penalty term — or, since `2^20` is fully
enumerable, simply **certify the bound numerically over all states** at each grid point (V-17). Certification
is cheap here and strictly stronger than any closed-form bound, so it is the recommended route.

---

## ~~U-14 — Tie-detection numerical tolerance~~ **CLOSED — APPROVED as D015 (Shivansh, 2026-08-25)**

> **CLOSED.** D015 approves U-14 revision 6's two-comparator rule: the canonical binary64 encoded-energy
> ledger for `T_E`, the separate encoding-blind original-objective `OPT_f` service, primary
> `(c_H,c_f)=(2048,2048)`, its four fixed one-factor diagnostics, D014 plus D015 provenance, the exact
> oracle/mismatch disposition, and R-U14-1. U-17 remains open and must consume this two-comparator boundary.
> Authoritative scope: `DECISIONS.md` **D015**. The analysis below is retained as the pre-approval record and
> is **NOT rewritten**.
>
> **DATED STATUS SUPERSESSION (2026-08-25):** D016 now closes U-17 after consuming this boundary. The prior
> forward-looking U-17 status above describes D015's approval-time state only; `DECISIONS.md` D016 is current.

**Why it matters.** `[SCOPE §16]` mandates tie detection at every grid point and a strict all-ties-must-be-A
rule, but specifies no tolerance. Exact float equality will under-detect near-degenerate ground states;
too loose a tolerance will over-detect and depress the A-rate through the strict rule.

**Bias risk.** MEDIUM, and **asymmetric**: because the rule is strict (all tied states must be A), a looser
tolerance can only ever *reduce* the measured A-rate. If the tolerance were tuned after seeing results, it
would be a direct lever on the primary metric.

**Recommendation.** Fix a relative tolerance scaled to the energy magnitude before any run, report the tie
fraction at that tolerance as the mandated diagnostic `[SCOPE §16]`, and additionally report A-rate
sensitivity across a small pre-declared ladder of tolerances so the dependence is visible rather than hidden.

---

## U-15 — Is `v_ref` global or per-constraint? **APPROVED — OPTION B** *(D005, 2026-08-23)*

> **APPROVED 2026-08-23 (Shivansh) as D005 — Option B, per-constraint.** `v_ref,j` is the **smallest
> attainable positive NATIVE violation** over `x in {0,1}^20`, **not** `gcd`-defined. Expected to
> evaluate to `(1, 1, 5)` for canonical Stage-1 data, **pending final canonical-data assembly and
> verification at U-07/G2** — the rule is approved; the numeric value is a consequence of it.
> **Not claimed:** that `(1,1,5)` is a general constant (the Stage-1 price vector is synthetic,
> `PROTOTYPE_AUDIT.md` F-4); that U-15 was a rescaling-invariance repair (both options are invariant,
> so rescaling is not a discriminator); or that Stage-2 comparability is settled (needs U-09 and a
> defined Stage-2 estimand).
> Full approved scope: `DECISIONS.md` D005. The analysis below is retained as the record.

> **Memo: `research/decisions/U15_DECISION_MEMO.md`** (verified by `research/audit/verify_u15.py`).
> **Proposed: Option B, per-constraint `v_ref = (1, 1, 5)`** with `v_budget` defined as the **exact
> DP-derived smallest attainable positive budget violation** — **not** as `gcd(prices)`. The gcd is only a
> lower bound; equality is a verified **instance fact** for Stage 1 (both are 5). Counterexamples where
> they diverge: `[10,10,10], B=15` (gcd 10, min 5); `[6,10,15], B=7` (gcd 1, min 3).
>
> **Key results:**
> - **A and B are the same philosophy applied to different units.** In lot-units (`p/gcd`, `B/gcd`),
>   Option A *is* Option B. The question is what the budget's native unit is: the dollar, or the actual
>   quantum of expenditure.
> - Under **A the budget reference violation cannot occur** — the smallest reachable is 5, so
>   `[SCOPE §14]`'s justification ("smallest nonzero integer violation") is **factually false for budget**.
> - **Both options preserve objective-rescaling invariance** — U-15 is orthogonal to V-15/C0-01. **Both
>   are also invariant under a change of currency unit when stated dimensionally**, so rescaling is **not**
>   a discriminator. ~~Earlier claim that A is a residual-rescaling defect of C0-01's class~~ —
>   **withdrawn** (Codex). The real §14 error is narrower: its *"smallest nonzero integer violation"*
>   justification is **factually false for budget** under A. A **reachability/interpretation** conflict,
>   not a units failure.
> - **Smallest reachable normalized violation:** A gives `(1, 1, 5)`; B gives `(1, 1, 1)`.
> - **U-18(a) consequence (reported, not resolved):** `r` applies **only to the inequality families
>   (sector, budget)** — cardinality uses the shared equality penalty and has **no `r`**. A common `r` is
>   coherent under B (`r = 1` targets the minimum reachable violation in both); under A it needs
>   `r = (1, 1/5)` — B with the normalization smuggled into `r`.
> - **Real content, at FIXED numerical `s` and `a`:** `lambda_S,bud` differs by `v^2 = 25x` and
>   `lambda_1,bud` by `v = 5x`, so the budget family's slack-vs-unbalanced calibration differs by `5x`
>   between options. **No categorical claim** that this is unabsorbable — whether an allowed `a = g(s)`
>   preserves it *is* U-18(a), still unresolved.
>
> **Conditioning:** requires an **explicit U-09 decision** — if Stage 2 resamples prices, `s` becomes
> incomparable in *absolute currency* terms but may remain comparable in each instance's *own normalized
> lattice units*; which is needed depends on the **Stage-2 estimand**, not yet defined, so incomparability
> is **not automatic**. `v_budget = 5`
> is contingent on a **synthetic** hand-chosen price vector (`PROTOTYPE_AUDIT.md` F-4); neither `c_j` nor
> `r` may be used to compensate for this choice; **it does not resolve U-18(a)**.

Original analysis retained below for provenance.

**Why it matters.** `[SCOPE §14]` fixes `v_ref = 1` as "the smallest nonzero integer violation — all three
constraint residuals in this problem are integer-valued". `[EXPERIMENTAL]` The premise is true but the
conclusion does not follow: `gcd(prices) = 5` and `B = 1100` is divisible by 5, so `h_budget in 5Z` and a
**unit budget violation is unreachable**. The smallest attainable budget violation is **5**.

Using a common `v_ref = 1` normalizes the budget constraint on a scale **5x finer** than its own attainable
lattice, while sector and cardinality are normalized on their true unit. Since `v_ref` enters
`lambda_S = s*Lambda_ref/v_ref^2` (a factor of 25) and `kappa = s*Lambda_ref/v_ref` (a factor of 5), this is
not a rounding detail.

**Options.** (a) Global abstract reference unit `v_ref = 1` for all constraints — simple, but deliberately
mismatched for budget; (b) per-constraint attainable scale `v_ref,c` (1, 1, 5) — dimensionally honest, but
departs from the frozen text; (c) rescale prices/budget by their gcd so the lattice *is* unit — changes the
instance.

**Bias risk.** MEDIUM. Mis-normalizing one constraint shifts where in `s` that constraint starts binding,
which distorts the *shape* of the robustness region — and region shape is a primary object of interest
`[SCOPE §17]`, not an incidental.

**Recommendation.** Escalate. If (a) is kept, the write-up must state explicitly that the budget constraint
is normalized on a non-attainable unit, and a sensitivity check under (b) is required.

---

## U-16 — Unbalanced penalty parameterization family **APPROVED — PARENT FAMILY ONLY** *(D004, 2026-08-22)*

> **APPROVED 2026-08-22 (Shivansh) at the PARENT-FAMILY level only.** The outer-scale Taylor family, its
> `lambda_1` / `lambda_2` coefficients and derived properties are approved; **Option 2 rejected**; Option 3
> retained as a sensitivity probe only. Exact scope in `DECISIONS.md` D004.
>
> **NOT approved by this decision:** U-18(a) reduction rule, U-18(b) outer-scale calibration `c_j`, U-15
> `v_ref`, or any numeric value (`Lambda_ref`, the three-axis box, `kappa_risk`). **No claim of canonicity,
> uniqueness or comparative neutrality.** The family retains **2 DOF per constraint** and is therefore not
> yet dimension-matched to slack's 1 DOF.
>
> Gate-1 entry: **E2 met**; E3/E4/E5 remain unmet.

> **STATUS: PROPOSED — Codex has independently audited (and independently re-derived) the parent family;
> awaiting final human scientific review.** Full derivation, units, rescaling
> proof, and bias analysis on the real Stage-1 residual supports:
> **`research/decisions/U16_DECISION_MEMO.md`** (verified by `research/audit/verify_u16.py`).
>
> **Proposed:** Option 1, outer-scale Taylor, in explicit two-parameter form
> `zeta_j = Lambda_pen,j * [ -a_j (h_j/v_ref,j) + (a_j h_j/v_ref,j)^2 / 2 ]`,
> giving `lambda_1 = Lambda_pen*a/v` `[E/R]` and `lambda_2 = Lambda_pen*a^2/(2v^2)` `[E/R^2]`.
>
> **Key results from the memo:**
> - The frozen relation `lambda_2 = lambda_1^2/2` requires an omitted energy reference `E0` to be
>   represented as `lambda_2 = lambda_1^2/(2*E0)`. `E0` must *carry energy units*; the frozen formula
>   neither declares it nor supplies its rescaling rule.
> [RETRACTED:C0-01/E0] "set to the dimensionless number 1"
> This superseded shorthand is imprecise because the omitted reference carries energy units.
> - §14's *prose* describes the correct family (`h* = v/a` in `R`, depth `-Lambda_pen/2` in `E`); its
>   *formulas* describe the broken one (`h* = 1/kappa` in `R/E`, depth `-1/2` dimensionless).
> - **Options 2 and 3 are not separate families** — both are reductions/reparameterizations of Option 1.
>   Therefore U-16 and U-18 are **mathematically coupled** (implementation needs both). They are **not one
>   governance decision**: the parent family may be approved conditionally while U-18 stays open — such an
>   approval simply cannot authorize implementation. (Superseded wording: "are one decision", per
>   Codex U16-03.)
> - **Option 2 is REJECTED on §14's own grounds**: it has `lambda_2 = lambda_S` exactly, i.e. it *is* the
>   curvature-match rule §14 rejected, with the identical bias `D = s*w > 0`.
> - **R2 (point-match) is RETRACTED as a recommendation**: `D = a*w*(1-w) < 0` for all `w > 1`, so it
>   under-penalizes unbalanced on 2 of 3 reachable sector violations, **directionally biasing the
>   infeasible-side comparison** toward unbalanced yielding more Category C — the direction H2 predicts.
>   `D` is a *local per-residual energy difference*: it does **not** establish a C-rate effect, which
>   requires the experiment.
> [RETRACTED:U16-01a] "mechanically inflates the C-rate"
> This superseded wording was corrected per Codex U16-01.
> - **No reduction is comparatively neutral**; bias is metric-dependent (A-rate vs C-rate).
> - **U-18 has two parts**, both open: (a) the `a_j` rule; (b) the outer-scale calibration
>   `Lambda_pen,j = c_j*Lambda_ref`. The derivation selects neither `c_j = 1` nor common-vs-per-constraint
>   scales (Codex U16-02). **Current status: part (a) has NO recommendation; part (b) has the UNAPPROVED
>   common `c_j = 1` recommendation from both agents.**
> [RETRACTED:U18b-3] "No recommendation is offered for either part"
> This superseded wording predated the U-18(b) analysis and contradicted the summary row and STATUS.md.

Original analysis retained below for provenance.

**Why it matters.** This is the most serious open item in the project. The frozen mapping is
**mathematically invalid**, independently confirmed (`verify_codex_findings.py`, C0-01):

- **Dimensional:** `[lambda_2 * h^2] = E^2`, must be `E`.
- **Consequence:** rescaling `f -> c*f` flips the unbalanced decoded ground state (verified between
  `c = 2` and `c = 6`) while slack is invariant. The comparison is therefore partly an artifact of units.
- **Internal contradiction in §14:** "constant depth `-1/2` regardless of `kappa`" requires
  `[kappa] = 1/R`; `kappa(s) = s*Lambda_ref/v_ref` gives `[kappa] = E/R`.

**This cannot be silently repaired in code** `[handoff §2]`, and `[SCOPE §14]`'s own warning applies with
full force: *"There is no unique canonical mapping between the two encodings' penalty parameter spaces."*
Choosing the replacement **is** choosing part of the answer.

**Options.**

| # | Family | Notes |
|---|---|---|
| 1 | `zeta = Lambda_ref * [ -a*(h/v_ref) + (a*h/v_ref)^2 / 2 ]`, sweep dimensionless `a` | Codex's suggestion. Preserves the Taylor *shape* from Montañez-Barrera eq. 24; outer `Lambda_ref` supplies the energy scale; `a` is dimensionless so rescaling-invariant. Reward depth becomes `-Lambda_ref/2`, correctly energy-valued |
| 2 | `lambda_1 = s*Lambda_ref/v_ref`, `lambda_2 = s*Lambda_ref/v_ref^2` | Both terms scale linearly in `Lambda_ref`, matching slack's normalization. **Abandons** the Taylor relation `lambda_2 = lambda_1^2/2`, so a reviewer may not recognise it as "actually unbalanced penalization" — the very objection `[SCOPE §14]` retained the Taylor family to avoid |
| 3 | Two independent coordinates `(lambda_1, lambda_2)`, each normalized | Explicitly rejected as Design 3 in `[SCOPE §14]`; doubles unbalanced's grid dimensionality |

**Bias risk.** **HIGH and directional.** `[SCOPE §14]` already proved that the *naive* curvature-match rule
biases the comparison against unbalanced by exactly `kappa*v` at every matched violation. A replacement
chosen carelessly can reintroduce a comparable directional bias. Whichever family is approved, **V-15
(rescaling invariance) and the `[SCOPE §14]` bias inequality must both be re-derived against it before
implementation.**

**Recommendation.** Option 1 — it is the minimal repair that fixes the units while preserving the Taylor
shape that makes the method recognisable as unbalanced penalization. **But this is a scientific decision
requiring explicit approval, and every downstream conclusion is conditional on it.**

---

## ~~U-17 — Mixed tie-set semantics~~ **CLOSED — APPROVED as D016 (Shivansh, 2026-08-25)**

> **CLOSED.** D016 approves the U-17 revision-2 package: consume D015's separate encoded-energy `T_E` and
> encoding-blind `OPT_f` comparators unchanged; deduplicate to distinct decoded portfolios `X_E`; assign
> atomic `A_x`, `B_x`, and `C_x`; use `exists C -> C`, else `all A -> A`, else `B` as the primary partition;
> require raw/decoded multiplicity, mixed-composition, universal/existential/fractional-C, complete atomic
> fraction, and D015 one-factor diagnostic reporting; and accept R-U17-1. Authoritative scope:
> `DECISIONS.md` **D016**. The proposal below is retained as the pre-approval record and is **NOT rewritten**.
>
> **Memo: `research/decisions/U17_DECISION_MEMO.md`** (verified by `research/audit/verify_u17.py).
> **Proposed primary partition, over distinct decoded portfolios `X_E`:**
> `if EXISTS C -> C (existential); elif ALL A -> A (universal, frozen §16); else -> B`.
> It is a partition for every nonempty finite `X_E`: either a C exists, otherwise all are A, otherwise a B
> exists. Thus it preserves frozen A exactly and gives feasibility `= 1 -` existential C.
>
> **Deduplication is mandatory:** form raw U-14-selected tied states `T_E`, then
> `X_E = {decode(z) : z in T_E}`. Classify and fractionate `X_E`, never raw auxiliary states; report both
> `|T_E|` and `|X_E|` so auxiliary degeneracy stays visible.
>
> **Mandated reporting:** primary label; mixed decoded-label census; universal/existential/fractional C
> diagnostics; and full decoded-portfolio fractions `p_A`, `p_B`, `p_C` with denominator `|X_E|`.
> Universal-C is retained as a different diagnostic estimand, not rejected as impossible. It cannot replace
> the primary C branch without separately placing mixed `A+C`/`B+C` sets while preserving B's feasibility
> meaning.
>
> **Depends on D015 / U-14:** D015 fixes both encoded-energy tie membership and the separate,
> encoding-blind original-objective `OPT_f` comparator. U-17 consumes both without altering either; no
> rate outcome is claimed.
>
> **Superseded provenance:** the earlier register summary described universal-C as rejected outright and
> recommended universal feasibility/fractional reporting without a full primary partition. The memo above
> is the live proposal; the retained historical text below is not a recommendation.

### Historical analysis (superseded; provenance only)

**Why it mattered.** The strict all-ties-must-be-A rule `[SCOPE §16]` settles only the **primary** metric.
A tied ground-state set may be a mixture (`A+B`, `A+C`, `B+C`), and its secondary semantics must be fixed
before results are seen.

**Historical recommendation - superseded.** Store the class and count of every distinct tied `x`; this did
not yet define the primary partition or the exact fractional denominator. The live memo now supplies both.

---

## U-18 — Unbalanced 2-DOF -> 1-DOF reduction **APPROVED — (a)+(b) AS ONE PACKAGE** *(D006, 2026-08-23)*

> **APPROVED 2026-08-23 (Shivansh) as D006, both parts jointly.**
> **(b)** `Lambda_pen,j = Lambda_ref` (`c_j = 1`), inequality families only.
> **(a)** R2 minimum-reachable-violation point matching at `r = 1`:
> `a(s) = sqrt(1 + 2s) - 1`, `lambda_1,j = Lambda_ref*a(s)/v_j`,
> `lambda_2,j = Lambda_ref*a(s)^2/(2*v_j^2)`. **Sector and budget ONLY — cardinality is EXCLUDED**
> (it is the shared *equality* penalty `alpha`, U-13, and has no `r`).
> Sensitivity `r in {0.5, 2}` via `a_r(s) = -r + sqrt(r^2 + 2s)` — **sensitivity only, never a
> post-hoc substitute for the primary `r = 1`**.
> **KNOWN BIAS, ACCEPTED AS A CONDITIONING CHOICE:** with `c = 1` the gap collapses to
> `D(w) = a(s)*w*(1-w)`, so `D < 0` for **every** `w > 1` at **every** `s > 0` — unbalanced is
> under-penalized at **2 of 3** reachable sector points and **1067 of 1068** reachable budget points
> (`verify_d006.py` §8; now tied to the closed U-07 canonical synthetic price vector). **Stated
> precisely** `[Codex U16-01, P4]`: a **LOCAL PENALTY-GAP** statement, **hypothesis-ALIGNED with H2** and
> **confounding** any `w > 1` result, but establishing/predicting/bounding **no** A/B/C outcome or
> Category-C rate.
> R2 remains **non-neutral**; the earlier retraction of R2 as a *recommendation* stands as the reason
> this bias must be reported with every unbalanced result.
> Full approved scope and mandatory conditioning: `DECISIONS.md` D006. The analysis below is retained.

**Why it matters.** The corrected outer-scale Taylor family has **two** degrees of freedom per constraint —
outer energy scale `Lambda_pen,c` (strength) and dimensionless `a_c` (decay rate, `h* = v_c/a_c`) — while
slack has **one**. Reducing two to one is unfrozen, and **it is precisely the reduction that broke in the
original formulation**: `[SCOPE §14]`'s `lambda_1 = kappa, lambda_2 = kappa^2/2` collapsed strength and
shape into one symbol with inconsistent units.

> **SECTION REWRITTEN 2026-08-22 after Codex U16-04.** The previous text recommended R2 and asserted that
> R1 "penalizes unbalanced more at every violation by exactly `Lambda_ref*s^2/2`". **Both statements are
> superseded and were wrong**: the constant-gap claim came from a two-state toy, not the general form.
> The corrected closed forms below are derived in `U16_DECISION_MEMO.md` §6.2 and independently
> re-derived by Codex.

**U-18 has TWO parts** (Codex U16-02 — the second was previously left implicit). **Both were open when
this was written; both were approved 2026-08-23 as D006:**

**(a) The rule for `a_j`** (the dimensionless shape/decay coordinate).
**(b) The outer-scale calibration `Lambda_pen,j`.** Rescaling invariance requires only
`Lambda_pen,j = c_j * Lambda_ref` for *some* fixed dimensionless `c_j > 0`. **The derivation does NOT
select `c_j = 1`, and does not decide common vs. per-constraint outer scales.** `c_j` changes relative
constraint strengths, so it is a live scientific choice — it cannot be inherited silently from the
derivation, nor treated as settled by U-15.

**Candidate rules for (a).** With `D(w) = [zeta(-w*v) - P_slack(-w*v)]/Lambda_ref`, `w = |h|/v_ref`:

| # | Rule | `D(w)` | Sign behaviour |
|---|---|---|---|
| R1 | `a = s` | `s*w*[1 + w(s/2 - 1)]` | flips at `w = 2/(2-s)` for `s<2`; `>= 0` once `s >= 2` |
| R2 | point-match, `a = -1+sqrt(1+2s)` | `a*w*(1-w)` | `0` at `w=1`; **negative for all `w>1`** |
| R3 | `a = 1` fixed, sweep outer scale | — | pins `h* = v_ref`; strength-only sweep |
| R4 | **weighted-neutral (Codex):** `a = -r + sqrt(r^2 + 2s)`, `r = E[w]/E[w^2]` | weighted mean of `D` `= 0` | R2 is the special case `r = 1` |

**Bias risk. HIGH and directional — no candidate is neutral.** `[EXPERIMENTAL]` verified in
`verify_u16.py` §6-§7. **R2 is RETRACTED as a recommendation**: `D < 0` for every `w > 1`, so on the
reachable sector support `w in {1,2,3}` unbalanced is under-penalized at 2 of 3 points, **directionally
biasing the infeasible-side comparison** in favour of finding more Category C for unbalanced — the
direction H2 predicts. R4 is correct algebra but **not canonical**: the weights and support are themselves
a conditioning choice requiring predeclaration.

### Part (b) — outer-scale calibration: RECOMMENDATION ON RECORD (2026-08-22)

**Codex recommends** one common, fixed constant across all inequality families, provisionally

```
Lambda_pen,j = Lambda_ref     for every inequality family j       (i.e. c_j = 1)
```

on **minimality and identifiability** grounds — explicitly *not* derived from the Taylor expansion.
Its argument: `v_ref,j` already normalizes residual units, and the approved 3-D coordinates `s_sector`,
`s_budget` already express independently swept strength, so a family-specific `c_j` would add a hidden
relative-strength calibration living outside the swept axes.

**Claude checked this independently and CONCURS — but a first attempt at a "stronger argument" was
OVERCLAIMED and is retracted (Codex audit, 2026-08-22).** With `Lambda_pen,j = c_j*Lambda_ref`:

```
D(w)   = c*a*w + (c*a^2/2 - s)*w^2  =  w * [ c*a + (c*a^2/2 - s)*w ]
w_star = c*a / (s - c*a^2/2)
```

> [RETRACTED:U18b-1] "D has exactly one nonzero root for any c"
> [RETRACTED:U18b-2] "c cannot improve comparative neutrality at all"
> [RETRACTED:U18b-2] "no fairness justification whatever"
> These three statements overstate the result. The verifier's checks were already correct (at most one
> positive nonzero root); only its prose overclaimed.

**Correct statements** (all verified, `verify_u16.py` §8):

| | Statement |
|---|---|
| (i) | **At most one** positive nonzero match. It exists **only when `s > c*a^2/2`**; at equality there is no nonzero root (`D` is linear), and when `s < c*a^2/2` the root is negative and outside the physical domain. |
| (ii) | `c` **cannot create a second** nonzero match — the bracket is linear in `w` for every `(c,a,s)`, so **multi-residual neutrality is unreachable by any `c`**. This part of the earlier argument survives. |
| (iii) | `c` **does move the single match location**, jointly with `a`. For a target `w0 > 0`, `c = s*w0/(a + a^2*w0/2)` matches slack at `w0`; equivalently, fixing `c` and setting `a(s) = -1 + sqrt(1 + 2s/c)` preserves the R2-style match at `w0 = 1`. |

**Narrower correct conclusion.** Per-constraint `c_j` cannot achieve *multi-residual* neutrality (ii). It
remains unjustified **on the present record** — because `v_ref,j` and the explicit sweep coordinates
already supply the only stated constraint-family normalizations — and a separate `c_j` would need either a
predeclared external valuation of one normalized violation against another, or a specified one-point
matching rule per (iii). **This is not a fairness theorem.**

**Two cautions that must travel with this recommendation:**

1. **`c = 1` is NOT a neutral default.** `c` multiplies unbalanced's coefficients and **not** slack's, so it
   directly sets unbalanced-vs-slack relative strength at matched `s`. It is a conditioning choice and must
   be reported as one.
2. **Its appropriateness cannot be judged independently of part (a)** — `c` and `a` jointly determine
   `lambda_1` and `lambda_2`, so (a) and (b) must be approved together.

`[Codex]` **Do not use `c_j` to compensate for U-15 choices.** Settle `v_ref` on its own merits, or the
calibration silently changes the meaning of its alternatives.

**Status of (b):** recommendation on record from both agents — **common fixed `c_j = 1`, standing as a
minimal, transparent conditioning choice and NOT as a consequence of any fairness theorem.**
~~**Not approved.** Human sign-off required, jointly with part (a).~~
**APPROVED 2026-08-23 as D006(b)**, jointly with part (a) exactly as this required. The two cautions above
**travel with the approval unretracted**: `c = 1` is **not** a neutral default, and it is a conditioning
choice that must be reported as one.

### Part (a) — the `a_j` rule: ~~**NO RECOMMENDATION**~~ **APPROVED 2026-08-23 as D006(a) — R2, `r = 1`** *(derivation complete 2026-08-22)*

> The derivation below reached **NO RECOMMENDATION** and that remains an accurate record of its finding:
> **no candidate rule is neutral.** The human approver selected **R2** (`a(s) = sqrt(1+2s)-1`), accepting
> its quantified one-sided bias — `D(w) = a(s)*w*(1-w) < 0` for every `w > 1` — as a pre-registered
> conditioning choice. **The R2 retraction below is NOT reversed by the approval:** it stands as the
> record of the bias that must accompany every unbalanced result. See `DECISIONS.md` D006.

Full derivation: **`research/decisions/U18_DECISION_MEMO.md`**, verified by
`research/audit/verify_u18a.py`. Headline results:

- **Target-point and fixed-weighted-mean matching are the SAME rule:** `a(s; r) = -r + sqrt(r^2 + 2s)`,
  indexed by one external parameter `r > 0` — *either* `1/(target violation)` *or* `E[w]/E[w^2]` under a
  declared weighting. `r` **cannot be derived** from the Taylor expansion.
  **Scope limit:** this covers those **two criteria only**, not every one-coordinate rule; infinitely many
  `a = g(s)` lie outside it and are not excluded mathematically. Any positive `g(s)` can be *rewritten* with
  `r(s) = [s - g(s)^2/2]/g(s)`, but that is algebra — `r(s)` is a matching statistic only where positive and
  declared.
- **R1 (`a = s`) is an ALGEBRAIC drifting-`r` representation**, not a fixed-`r` family member: `r(s) = 1 - s/2`,
  implied match point `2/(2-s)` (1.18 at `s=0.3`, 2.00 at `s=1.0`, 20.0 at `s=1.9`), and for `s >= 2`,
  `r <= 0` leaves the positive range so there is **no physical matching interpretation**. Its infeasible-side
  sign is **mapping-dependent, reversing with `s`**.
- **R3 is eliminated**: with `c_j = 1` and `a_j = 1` both fixed there is no swept coordinate.
- **U-15 gates any support-calibrated `r`.** Budget support enumerated by exact DP over the **PRIMARY**
  all-`x` domain (the QUBO domain; cardinality is soft): **1068 distinct violations, min 5, max 5475**, a
  **proper subset** of the multiples of 5 (27 unreachable) — *not* a contiguous lattice. The `|x|=K` slice
  (541 distinct, 39 unreachable) is a conditional diagnostic only. Under U-15(a) `v_budget = 1` the smallest
  reachable `w` is **5**, so a rule matching at `w0 = 1` targets a violation that **cannot occur**; under
  U-15(b) `v_budget = 5` it is reachable.
  **Scope:** U-15 is blocking for a *support-calibrated* `r` and for one rule shared across constraint
  families. It is **not** a universal impossibility — a human could predeclare separate mappings conditional
  on each U-15 branch.
- Feasible-side: `zeta/Lambda_ref = a*u*(a*u/2 - 1)` rewards `u < 2/a` and penalizes `u > 2/a`, threshold
  `u = 2/a(s;r)`. For sector, `u = 2` means an **empty sector**. At the two evaluated `s` values the sign
  differs; whether any candidate flips *within the sweep* depends on the **unfrozen** `s`-bounds (U-04) and
  on `r`, and is not claimed.

**Conclusion: no candidate is recommended.** `r` is an irreducible external conditioning choice; U-15 must
be resolved (or branch-conditional mappings predeclared) before a support-calibrated `r`; R1 — the only rule
needing no declared `r` — **lacks a stable matching interpretation** and is mapping-dependent, though no
metric has been defined against which it could be called formally "worst"; and selecting `r` with the
direction of H2 in view would be methodologically illegitimate `[handoff §7]`.

**Pre-declared requirement, attached to any future `r` approval:** a sensitivity pass at `r/2` and `2r` on
a coarse subgrid, reporting whether the qualitative rank-stability conclusion changes — mirroring the
mandated 0.5x/2x `s`-domain expansion `[SCOPE §14, §18]`.

---

## Summary

| ID | Item | Blocking for | Bias risk | Have recommendation? |
|---|---|---|---|---|
| U-01 | ~~Grid dimensionality~~ | **CLOSED** — 3-D approved as scope amendment | — | Closed (D002) |
| U-02 | ~~`kappa_risk` value~~ | **CLOSED** — D007, triple `(1.0, (decimal simple daily return)^-1, daily)` | — | Closed (D007) |
| U-03 | ~~`Lambda_ref` definition~~ | **CLOSED** — D008, range over predicate-defined `F`, rule only | — (rating superseded: NOT reparameterizable for unbalanced) | Closed (D008) |
| U-04 | `s`-domain bounds | the sweep | **disqualifying if post-hoc** | Yes (analytic) |
| U-05 | ~~Grid resolution~~ | **CLOSED — D012: 10 base-10 log intervals/decade, endpoints included** | — | Closed (D012) |
| U-06 | ~~Register domain 39 vs 37~~ | **CLOSED** — 39 fixed by Scope Lock | — | Closed (C0-06) |
| ~~U-07~~ | Canonical data assembly | **CLOSED 2026-08-25** | — | Closed by direct human approval after G2 assembly and Codex audit |
| U-08 | Stage-2 RNG | Stage 2 | HIGH | Yes (master seed) |
| U-09 | Stage-2 mu/Sigma protocol | Stage 2 | MED-HIGH | Partial |
| U-10 | Stage-2 sector reassignment | Stage 2 | MEDIUM | Yes (structured) |
| U-11 | Stage-2 feasibility + count | Stage 2 | HIGH | Yes (exact count) |
| U-12 | ~~Ablation subset~~ | **CLOSED — D013 conditional exact-sign rule** | — | Closed (D013) |
| U-13 | `alpha` treatment | encoding impl. | MEDIUM | Yes (derive) |
| ~~U-14~~ | Tie tolerance | **CLOSED — D015 two-comparator rule** | — | Closed (D015) |
| ~~**U-15**~~ | **`v_ref` global vs per-constraint** | **CLOSED** | — | **APPROVED 2026-08-23 (D005): Option B**, rule-defined as the smallest attainable positive native violation, **not** gcd. Numeric `(1,1,5)` verified by closed U-07/G2 |
| **U-16** | **Unbalanced parameterization (frozen mapping is INVALID)** | **everything** | **HIGH, directional** | **APPROVED (D004) — PARENT FAMILY ONLY**; reduction + outer scale remain U-18 |
| ~~**U-17**~~ | **Mixed tie semantics** | **CLOSED — D016 primary partition/reporting** | — | Closed (D016): consumes D015's two comparators unchanged |
| ~~**U-18**~~ | **Unbalanced reduction: (a) `a_j` rule + (b) outer scale `c_j`** | **everything** | **HIGH, directional — bias ACCEPTED, not removed** | **APPROVED 2026-08-23 (D006) as one package.** **(b)** `c_j = 1`. **(a)** R2 `a(s) = sqrt(1+2s)-1` at `r = 1`, **inequality families only, cardinality excluded**. Sensitivity `r in {0.5, 2}`, not post-hoc selectable. **Known one-sided bias `D < 0` for all `w > 1` (1067/1068 budget, 2/3 sector points) is an accepted conditioning choice and must be reported with every unbalanced result** |


**Nothing above is approved. No implementation may proceed on the basis of a recommendation in this file.**

### U-07 closure note — 2026-08-25

**CLOSED by direct human approval.** The approved G2 canonical-input package was assembled by Claude,
independently audited by Codex, and accepted in `DECISIONS.md` under
**Process Approval — U-07 Closure**. The retained source bytes, corrected ticker join, evidence-based
cell-17 synthetic price vector, ticker-keyed sector labels, D007 conformance, limited source fidelity,
calendar-derived/not-observed terminal-session qualification, and tested D005 `(1,1,5)` are now the
canonical U-07 record. This closure does **not** authorize G3 or any later gate.
