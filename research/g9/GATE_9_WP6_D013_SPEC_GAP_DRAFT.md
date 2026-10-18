# Gate-9 WP6 — D013 `+0.0` inactive-family evaluator: SPEC-GAP RECORD

**Status:** DRAFT. Not an approval, release, authorization, or specification of the
evaluator. **It authorizes no code, no Kaggle push, no candidate draw, no
instance, no ground truth, no scientific launch.** §B remains **OPEN**.

**Purpose:** STEP 1 of WP6 required a spec check *before* any code. The instruction
was explicit: if any of the three required items — (a) which coefficient families
are active vs set to `+0.0` per condition, (b) the per-condition feasibility
rule, (c) the `f*_q` contract — is **not** fixed by an approved record, do not
choose one; record the gap instead.

**Outcome: items (a) is FIXED. Items (b) and (c) are NOT FIXED, and one of them
is expressly deferred by an approved record to a D013 authorization that does
not exist.** No evaluator was written.

**Records searched:** `research/decisions/DECISIONS.md` (D008, D013, D014, D015,
D016, and the Gate-4/Gate-6 process approvals), `research/decisions/U12_DECISION_MEMO.md`,
`U14_DECISION_MEMO.md`, `U17_DECISION_MEMO.md`, `GATE_9_STAGE2_PROTOCOL_DRAFT.md`
and `GATE_9_STAGE2_PROTOCOL_APPROVAL.md`, `GATE_9_STAGE2_ENTRY_AND_PREREGISTRATION.md`,
`GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md` and its approval,
`GATE_9_SECTION_B_KAGGLE_PROVIDER_TRUST_AMENDMENT_*`, `SCOPE_AMENDMENT_001.md`,
`UNRESOLVED_DECISIONS.md`, `research/00_specifications/FROZEN_MATH_SPEC.md`,
`research/STATUS.md`, `research/g6/G6_PREPRODUCTION_EXECUTION_PLAN.md`,
`research/g6/rate_surface_and_d013.py`, and all of `research/g9/`.

---

## Part 1 — What IS fixed, quoted

### 1.1 The four conditions, and which families are active per condition

`research/decisions/DECISIONS.md:1104-1113` (D013, "Fixed conditions and coordinates"):

> ```
> F_C   = {x in {0,1}^20 : sum_i x_i = K}
> F_CB  = {x in {0,1}^20 : sum_i x_i = K and p^T x <= B}
> F_CS  = {x in {0,1}^20 : sum_i x_i = K and n_j(x) <= C for every sector j}
> F_CSB = {x in {0,1}^20 : sum_i x_i = K and p^T x <= B and n_j(x) <= C for every sector j}
> ```

`research/decisions/DECISIONS.md:1106` (preceding line, establishing exclusivity):

> For each independently eligible instance, the only conditional constraint conditions are exactly:

**Derived active/inactive map, read directly off the four predicates above
(cardinality is present in all four; the budget family is absent from `C` and
`CS`; the sector family is absent from `C` and `CB`):**

| Condition | cardinality `alpha` | sector family | budget family | active penalty axes |
| --- | --- | --- | --- | --- |
| `C`   | active | **inactive (`+0.0`)** | **inactive (`+0.0`)** | 1 |
| `CB`  | active | **inactive (`+0.0`)** | active | 2 |
| `CS`  | active | active | **inactive (`+0.0`)** | 2 |
| `CSB` | active | active | active | 3 |

**Cardinality is never inactive.** D013's four predicates all contain
`sum_i x_i = K`, and `DECISIONS.md:1142-1143` independently confirms cardinality is
an equality penalty handled separately: "Cardinality is an equality penalty and
has no invented D006 `r` analogue." So an evaluator only ever needs to zero the
*sector* and *budget* inequality families. This is FIXED.

The active-axis count is corroborated verbatim in the supporting memo,
`research/decisions/U12_DECISION_MEMO.md:142-144`:

> Thus `C`, `CB`, `CS`, and `CSB` use respectively one, two, two, and three active dimensions, with every
> shared active coordinate sampled at the same D010/D012 values. An inactive coordinate must not remain in
> the denominator as repeated copies of an otherwise identical result.

### 1.2 Inactive penalties are identically zero and leave the grid

`research/decisions/DECISIONS.md:1115-1118`:

> Use D008's canonical `Lambda_ref`, D010's per-axis domain rule, and D012's grid density **only on each
> condition's active penalty axes**. Every inactive penalty is identically zero and omitted from that
> condition's grid; it is not an additional sampled or duplicated dimension. No per-condition normalizer,
> box, penalty axis, condition, or selective repetition is authorized.

This is the authority for the "+0.0 exact, and axis dropped" requirement. FIXED.

### 1.3 The register is RETAINED with a `+0.0` coefficient

This is the subtle part, and it is fixed. The inactive family is *not* removed
from the QUBO variable set; only its coefficient goes to zero.

`research/00_specifications/FROZEN_MATH_SPEC.md:345-349` (§5.1):

> The Scope-locked raw
> layout has 39 variables: 20 original bits, two sector slack bits for each of
> four sectors, and 11 budget slack bits. For D013 inactive inequalities, the
> coefficient is exactly `+0.0` but the raw register stays; its multiplicity is
> symbolic and never triggers a `2^39` enumeration.

`research/decisions/U14_DECISION_MEMO.md:191-197` (D015's approved §5.1 arithmetic):

> `P_E_ineq = fl((-linear_product) + quadratic_product)`. For a D013-inactive
> inequality family, set its `P_E_ineq = +0.0` exactly and retain its register as
> §5.3 requires. Name the resulting values `P_E_sector[j]` and `P_E_budget` for
> their respective families. All symbols named in these paths, including each
> coefficient, must be finite binary64 values; mathematically active coefficients
> must be strictly positive. A zero coefficient is permitted only for a
> D013-inactive family.

`research/decisions/U14_DECISION_MEMO.md:288-292` (D015's approved §5.3):

> The raw slack domain retains the Scope-locked
> 39-variable register layout in a D013 ablation: an inactive family has a zero
> coefficient, so every assignment of that family's still-present register is an
> exact lift. Its multiplicity may be represented symbolically, never materialized
> by forbidden `2^39` enumeration. This is the tractable `O(2^20)` path.

Note the direct consequence: with `lambda_S = 0`, **every** value of the retained
register is an exact minimizer, so the certified raw slack domain `C_slack` gains
a factor of `2^2` (sector) or `2^11` (budget) per inactive family. Any evaluator
that drops the register entirely produces a different raw domain and a different
`z_ref` ordering. FIXED as to *behaviour*; see GAP-2 for what is not fixed.

### 1.4 The `+0.0` must be the positive zero, and the accumulation order is fixed

`research/decisions/U14_DECISION_MEMO.md:199-207` (D015's approved unshifted sum):

> ```
> H_acc = f
> H_acc = fl(H_acc + P_card)
> for sector j = 1..4:           H_acc = fl(H_acc + P_E_sector[j])
> H_acc = fl(H_acc + P_E_budget)
> H_E = H_acc
> ```

Adding `+0.0` to `H_acc` must not perturb the accumulator, and must not introduce
`-0.0`. This is FIXED, and it is precisely the "never `-0.0`" requirement.

### 1.5 The evaluator is a hard prerequisite

`research/decisions/GATE_9_STAGE2_PROTOCOL_DRAFT.md:166-171` (§3):

> Before the first Stage-2 primary core pass, the exact `+0.0` inactive-family
> evaluator required by a fired D013 branch must have its own reviewed
> non-scientific validation. If that prerequisite is unavailable or fails, no
> Stage-2 core pass starts: otherwise a later fired trigger could not receive
> its predeclared complete package. This is a readiness condition, not a new
> ablation authorization.

Restated in the approved CUDA amendment,
`research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md:111-116`, and the
required comparison content at `:83-87`:

> If D013 fires,
> immediately before its CUDA ranges run, repeat this full-domain comparison
> at primary `(30,30,30)` for each of `C`, `CB`, `CS`, and `CSB`, including
> their inactive `+0.0` families. Every comparison includes energy-minimum
> words, canonical minimum index, tie flags, and D015/D016 reconstruction

### 1.6 The frozen-authority refusal that motivates an additive evaluator

`research/decisions/DECISIONS.md:2026-2030` (Gate-4 authorization, item 4):

> **Explicitly excluded and carried forward.** `+0.0` inactive-coefficient representability —
> `src/g4/parameters.py` rejects coefficients `<= 0.0`, so §5.1's inactive-inequality case cannot be loaded
> — is **not** in scope. D013 ablation is excluded from the parent Gate-4 authorization, and how symbolic
> multiplicity is realised is a design question belonging to D013's own authorization. **It carries to
> Gate 6.**

Verified in the frozen source: `src/g4/parameters.py:22-25` raises on any
coefficient `<= 0.0`, and `src/g5/domains.py:126-127` refuses a non-`(True, True)`
activity signature with `"active-CSB cache cannot represent an inactive +0.0 family"`.
`src/g5/domains.py:6-8` states the intent: "A future D013 inactive family uses
+0.0 and must build a different, coefficient-dependent domain; this module
therefore rejects inactive coefficients rather than reusing this cache."

So the evaluator **must** be additive and must not touch `src/`. That much is
settled. It does not settle GAP-1..GAP-3 below.

---

## Part 2 — What is OPEN

### GAP-1 — The per-condition feasibility rule (and the disposition of an empty `F_q`)

**No approved record states what the evaluator does when a condition's feasible
set `F_q` is empty, or defines a per-condition feasibility predicate that the
D016 classifier could consume.**

The supporting memo has one sentence —
`research/decisions/U12_DECISION_MEMO.md:110`:

> Category C means
> violation of that condition's active predicate only.

— but D013 is explicitly authoritative over its memo.
`research/decisions/DECISIONS.md:1099-1102`:

> **Memo:** `research/decisions/U12_DECISION_MEMO.md` revision 3 (supporting analysis; this
> record is authoritative).

`DECISIONS.md` contains **no** occurrence of `f*_q`, `X*_q`, or `argmin`
(verified by direct search of the whole file). So the memo's `f*_q` /
`X*_q` sentence — `U12_DECISION_MEMO.md:109`:

> For every condition, `X*_q = argmin_{x in F_q} f(x)` and `f*_q = min_{x in F_q} f(x)`. Category C means
> violation of that condition's active predicate only.

— is the *only* statement of the `f*_q` contract anywhere in the record, and it
sits in a document that declares itself non-authoritative. D016, which supplies
the actual classifier, is written entirely against a single unqualified
predicate. `DECISIONS.md:1294-1297`:

> ```
> A_x = D015 OPT_f(x)                    # encoding-blind feasible-optimal predicate
> B_x = feasible(x) and not A_x
> C_x = not feasible(x)
> ```

and `DECISIONS.md:1299-1300`:

> The classifier's only runtime inputs are decoded `x`, `f*`, and the original feasibility predicate; under
> D015's immutable encoding-blind configuration, those inputs determine `OPT_f`.

Neither D015 nor D016 says which `feasible` a D013 condition supplies, and
neither mentions D013's active predicates at all.

**Candidate readings, none of them selected:**

1. **Strict per-condition reading (memo §5.1).** `feasible_q(x)` is membership in
   `F_q`; `f*_q = min_{x in F_q} f(x)`. Requires an owner rule for `F_q = {}`.
2. **Full-CSB reading.** The feasibility predicate and `f*` stay the canonical
   `CSB` ones and the ablation varies only the *penalty coefficients* under test,
   never the classifier's ground truth. Note this is *closer* to D013's actual
   wording — D013:1115-1118 speaks only of *penalties* and *grid axes*, never of
   changing the feasibility predicate — and it is therefore in tension with the
   memo's own sentence.
3. **Reject-the-instance reading.** An empty `F_q` is a hard stop, never a value.

Reading 2 is arguably the better-supported of the three from the authoritative
text, and reading 3 is what the existing G3 ground-truth code does for the
all-constraints set (`research/ground_truth/compute_g3_ground_truth.py:267-268`:
`"F is empty — no feasible portfolio; this is a G3 stop condition, not a value"`).
**I am not choosing among these.** They are scientifically consequential: they
decide whether a D013 ablation reports A/B/C rates against a relaxed ground
truth, and a choice made here is exactly the kind R-U12-1 and R-U17-1 forbid
being made post-result.

There is a strong *inference* that empty `F_q` is unreachable for any accepted
Stage-2 instance: the protocol's U-11 screen accepts only when
`|F| >= 100` where `F` is the all-constraints set
(`GATE_9_STAGE2_PROTOCOL_DRAFT.md:121-127`), and `F_CSB ⊆ F_CB, F_CS ⊆ F_C`, so
all four conditions would be nonempty. **This is my inference, not a quoted
rule**, and it rests on reading U-11's `F` as `F_CSB`. It is not sufficient: it
protects only Stage-2 generator output, not the Stage-1 instance, and it says
nothing about the *predicate* half of GAP-1. The WP6 evaluator must have a total
behaviour on all inputs, not a total behaviour justified by an unstated
precondition.

**The project's own Gate-6 plan already demands this be resolved by the owner.**
`research/g6/G6_PREPRODUCTION_EXECUTION_PLAN.md:90-93`:

> **Conditional D013 only if it fires** remains unresolved. Before an ablation
> run, the owner must resolve the authoritative per-condition feasibility and
> `f*_q` contract. G4/G5 coefficient and domain types reject inactive `+0.0`
> families, so any D013 evaluator must be additive and separately verified.

This is a pre-existing, independent instruction to stop and ask. I am following it.

### GAP-2 — How symbolic multiplicity is realised

**An approved record expressly declines to fix this and assigns it to a D013
authorization that does not exist.** `DECISIONS.md:2028-2030`, quoted in full in
Part 1.6:

> how symbolic
> multiplicity is realised is a design question belonging to D013's own authorization

D015 and `FROZEN_MATH_SPEC.md:347-349` fix that the multiplicity is *symbolic* and
must never be materialized by `2^39` enumeration, and
`U14_DECISION_MEMO.md:290-292` fixes that every assignment of the retained
register is an exact lift. But **how** `|T_E|` is to be reported and reduced —
exact integer, factorized `(base, 2^2)`, or symbolic — is not fixed. D016 requires
`|T_E|` be reported separately (`DECISIONS.md:1288-1289`, `:1312`), and
`U17_DECISION_MEMO.md:34-35` says the multiplicity "may be represented
symbolically... symbolic representation is not an excuse to omit the raw count."

**Candidate readings, none selected:**

1. Exact Python integer `|T_E|` (exact at any width; only the domain is huge).
2. Factorized symbolic form `|base| * 2^w`, which is what "never materialize
   `2^39`" seems to be driving at.
3. Both: exact integer for the *decoded* accounting, symbolic for the raw count.

The choice changes the WP6 output record's schema, and the schema is hash-bound
into every downstream artifact.

### GAP-3 — Whether the `CSB` condition must reproduce the v1 release bit-for-bit, and against which coordinate

`GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md:83-87` fixes the *comparison content*
(energy-minimum words, canonical minimum index, tie flags, D015/D016
reconstruction) and pins the coordinate to primary `(30,30,30)`. It does not fix
which reference the comparison is *against*. WP6's task text asks for a Python
reference that "reuses the frozen `src/g4` energy authority" and reproduces "the
existing frozen authority bit-for-bit over the full domain" — but the qualified v1
release is a **CUDA** release (`research/decisions/GATE_9_CUDA_CORE_CORRUPTION_QUALIFICATION_RELEASE.json`,
T4 / CC 7.5 / driver 13000 / CUDA 12080 / Python 3.12.13 / NumPy 2.0.2), and
`src/g4/energy.py` is a *different* authority that Stage 1 has never been shown to
agree with the v1 CUDA engine bit-for-bit at `+0.0` conditions. No approved record
states the Python reference and the v1 CUDA engine are bit-identical for the
`+0.0` inactive-family case. Choosing the wrong reference would silently
re-point a WP6 fixture at the wrong authority — the "repointing a test so it
fails for a different reason" pattern the build instruction explicitly forbids.

---

## Part 3 — What I did not do, and why

- I did **not** write `stage2_d013_inactive_evaluator.py` or
  `verify_stage2_d013_inactive_evaluator_fixtures.py`. GAP-1 through GAP-3 are
  owner decisions, not implementer choices; each one determines a semantic
  output, and R-U12-1 / R-U17-1 / R-U14-1 all prohibit post-result adjustment of
  exactly these.
- I did **not** modify `src/`, the qualified v1 release, or any existing file.
  This record is the only file created. See the additive-only proof in the build
  report.
- I did **not** run any candidate draw, instance generation, ground truth, or
  scientific computation. The fixtures WP6 would use are synthetic, and none were
  written, because writing them would require first fixing GAP-1..GAP-3.

## Part 4 — What the owner needs to fix to unblock WP6

1. **GAP-1:** the authoritative per-condition feasibility predicate and the
   `f*_q` contract, including the disposition of an empty `F_q`. State it in a
   dated approved record, not in a memo.
2. **GAP-2:** the `|T_E|` representation for a retained zero-coefficient register
   — exact integer, factorized symbolic, or both — fixing the output record
   schema at the same time.
3. **GAP-3:** which frozen authority the `CSB` condition is required to reproduce
   bit-for-bit (`src/g4/energy.py` Python, or the qualified v1 CUDA engine), and
   whether a Python-vs-CUDA bit-identity is a required precondition of WP6 or a
   WP7 concern.

Items 1 and 2 are on the critical path to *any* WP6 evaluator. Item 3
determines what the fixtures compare against. All three are cheap to answer and
none can be inferred safely from the current record — which is why I stopped.
