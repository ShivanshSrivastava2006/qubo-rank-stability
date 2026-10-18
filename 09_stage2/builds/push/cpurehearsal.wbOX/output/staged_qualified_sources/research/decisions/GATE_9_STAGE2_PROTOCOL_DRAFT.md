# Draft — Gate-9 Stage-2 Pre-result Protocol

**Status:** DRAFT ONLY — not owner-approved; not executable  
**Prepared:** 2026-09-22  
**Purpose:** Put every remaining Stage-2 design choice in one place for a
single owner decision. This document does not generate, inspect, screen,
retain, compute, or interpret any candidate instance.

## 1. Authority and boundaries

This draft is subordinate to the scope lock, `DECISIONS.md`,
`UNRESOLVED_DECISIONS.md`, the accepted Gate-6 aggregate, and the accepted
Gate-7/8 records. It is an additive proposed decision because `DECISIONS.md`
is hash-pinned by accepted artifacts and must not be edited.

The proposed protocol preserves all of the following:

- 20 assets and `K=6` are fixed; every primary value remains Python-produced
  exact certification, never a CUDA/HIP/GPU primary value.
- The Stage-1 price vector, `C=2`, `B=1100`, and `kappa_risk=1/day` are fixed.
  Keeping integral prices preserves the current residual/register-width and
  `v_ref=(1,1,5)` basis.
- Stage 2 varies only the daily-return draw and the balanced sector partition.
  It is a new instance family, not a re-reading, pooling, or modification of
  Stage 1.
- No hypothesis threshold introduced here may be applied retrospectively to
  Stage 1. All D005/D006 non-neutral-mapping, box, V-14, D011, and
  Stage-1-only conditioning persists.

The final owner record will pin this approved protocol and its implementation
record. At this drafting point, the fixed authority baseline is:

| Authority | File SHA-256 |
| --- | --- |
| `RESEARCH_SCOPING_AND_SCOPE_LOCK.md` | `86fe02434d31180db8780c8545f151c460cee1b41b86236401173165bd28f6bc` |
| `research/00_specifications/IMPLEMENTATION_SPEC.md` | `6aad8221e45fd34d707e0e33e289aab2f9e099dc51590c4793da2679d4c78dae` |
| `research/decisions/DECISIONS.md` | `274c6cd92d4958957d125efc7ae2ddb6f40629eb78b7c2e2be99224e038ce849` |
| `research/decisions/UNRESOLVED_DECISIONS.md` | `18d5b578be411dbadffc9128882a000ff5137b1e72878a4b0e17e70e5124156b` |
| Gate-8 exit | `ba3f81459ab2511de924f04e8ca87e80c62dd41cdcfe09ea61d5d79f866f75b8` |
| Gate-9 entry | `42c6a07a39873bf74939f75f93a176a316d9313ef1b85ffb46ab0c4ec42d5585` |
| Canonical Stage-1 instance | `c4615d9b5066597c4754a1e06d2b3a7906c218965a7d6d530cf54f75c4b5f243` |

Before the first draw, a separate implementation record must pin the exact
generator and validator source hashes, the CPython fingerprint, and NumPy
version. It may implement this protocol but may not modify any choice in it.

## 2. Proposed exact instance family

### Count and attempt ordering

Produce exactly **five** accepted Stage-2 instances, identified `stage2_01`
through `stage2_05`. For each slot, attempts are considered in increasing
integer order `0..127`; the first attempt satisfying every predeclared
structural rule below is accepted. If a slot has no accepted attempt by 127,
the run stops fail-closed. It does not substitute a fifth slot, relax a rule,
or select a different generator after seeing any values.

Every attempt—accepted or rejected—will be retained in a non-scientific
generation ledger with its slot, attempt number, derived seeds, sector
partition digest, feasibility count, and one or more fixed rejection codes.
The ledger contains no QUBO energy, minimum, tie, label, rate, or hypothesis
outcome.

### U-08 — deterministic seed derivation

The proposed arbitrary master seed is the unsigned integer
`1592594996` (`0x5EED2024`). It was selected for this draft before a Stage-2
candidate exists and is not derived from any Stage-1 result.

For each independent stream, form ASCII bytes exactly as:

```
decisions_os/stage2/v1|master=1592594996|slot=<01..05>|attempt=<0..127>|purpose=<returns|sectors>
```

Take SHA-256 of those bytes; interpret the first 16 digest bytes as an
unsigned big-endian integer; initialise `numpy.random.PCG64` with that integer
and use `numpy.random.Generator` around it. The approved execution baseline is
CPython `3.12.3` and NumPy `2.4.4`; an implementation record must pin the full
build fingerprint before the first draw. The generator source records the full
SHA-256 input/output seed commitment, and no shared mutable RNG state is
allowed. This makes an attempt independent of all earlier accepted/rejected
attempts.

### U-09 — return/covariance generator

For each attempt's `returns` stream, draw exactly 249 rows of 20 daily simple
decimal returns from the multivariate normal distribution with the accepted
Stage-1 `mu` and `Sigma` as mean and covariance. No bootstrap is used because
the historical raw series is unavailable.

Let `R` be that `249 x 20` draw, `mu_new = mean(R, axis=0)`, and
`Y = R - mu_new`. Define the reported covariance as
`Sigma_new = (Y.T @ Y) / 248`, then symmetrise it once as
`(Sigma_new + Sigma_new.T) / 2`. This is the unbiased sample covariance and is
positive semidefinite by construction; no covariance shrinkage, eigenvalue
clipping, optimization, or outcome-based repair is permitted. A non-finite
input/output or failed finite/shape/symmetry/PSD validation is a **producer
failure**, not a candidate rejection: Stage-2 stops.

The generated instance records the 249-row return matrix hash and canonical
binary64 encodings of `mu_new` and `Sigma_new`, not any result calculated from
them. Daily simple-return units are retained, so `kappa_risk=1/day` retains
its Stage-1 meaning.

### U-10 — balanced sector assignment

For the same slot/attempt's independent `sectors` stream, draw one uniformly
random permutation of the 20 canonical ticker indices. The first five indices
form sector 0, the next five sector 1, then sector 2, then sector 3. Thus every
assignment has exactly five assets per sector.

For structural uniqueness, compare the unordered collection of four sorted
five-ticker blocks, not their arbitrary numeric sector names. Reject an
attempt if that normalized partition is equal to the Stage-1 partition or to
an earlier accepted Stage-2 partition. This filter is independent of returns,
energies, labels, rates, and hypotheses.

### U-11 — feasibility and degeneracy rule

For the proposed partition and fixed `p,K,C,B`, enumerate only the
`C(20,6)=38,760` cardinality-feasible portfolios and count those satisfying
the sector and budget constraints. No objective, optimum, QUBO, tie, label,
or rate is evaluated in this step.

Accept an attempt only if `|F| >= 100`. Reject it with the fixed code
`feasible_set_below_100` otherwise. The floor is deliberately a low
non-degeneracy guard rather than a closeness-to-Stage-1 filter (`|F|=976` is
not a target). The exact `|F|` is retained as a predeclared difficulty
descriptor, never used to drop an already accepted instance or weight a
cross-instance conclusion.

## 3. Proposed primary platform and per-instance execution package

### Primary producer policy

All Stage-2 scientific values are produced by the Python exact-certification
implementation. CUDA/T4, HIP, and any other accelerator may only be used for
separately authorized non-value qualification; they do not supply a Stage-2
primary value. The producer records its CPython and NumPy fingerprints at
start/end and refuses drift. A different Python build requires an independently
reviewed bit-identity qualification before it can produce a replacement shard.

### Mandatory package proposed for every accepted instance

The following proposal intentionally keeps the locked §18 companions rather
than silently narrowing Stage 2 after observing Stage 1:

1. Primary CSB exact sweep at `r in {0.5, 1, 2}` on the full fixed 61-cubed
   joint grid, using the frozen `(2048,2048)` comparator/classifier.
2. All four D015 diagnostic pairs on that same grid as newly generated
   diagnostics, never pooled into the primary result.
3. D011 curvature-match companion on its already declared 13-cubed matched
   subgrid, with its matched-primary comparison and known directional-bias
   conditioning.
4. Both V-14 expansion readings at `r=1` only, retaining the declared 0.5x
   floor-to-zero defect, as separate report-only companions.

The D013 ablation is not a base pass, but its already-approved exact-sign
trigger is applied mechanically and separately after each instance's three-r
primary core pass. If the trigger does not fire, no ablation runs. If it fires,
all and only `{C, CB, CS, CSB}` run with D013's already-fixed active-axis,
D011, and V-14 package; none is pooled with the primary result. This protocol
does not replace, widen, or reinterpret that trigger.

Before the first Stage-2 primary core pass, the exact `+0.0` inactive-family
evaluator required by a fired D013 branch must have its own reviewed
non-scientific validation. If that prerequisite is unavailable or fails, no
Stage-2 core pass starts: otherwise a later fired trigger could not receive
its predeclared complete package. This is a readiness condition, not a new
ablation authorization.

## 4. Ground truth, boxes, and hard stops

For each accepted instance, recompute the original feasible optimum and
`Lambda_ref` from its own `F` and objective before any encoding sweep. Rebuild
the D006/D008/D010 ledgers under the same frozen formulas, grid, comparator,
and decoded-only classifier rules; record the new instance-specific
provenance.

Hard-stop, requiring a new owner decision rather than reseeding or repair:

- non-finite return/covariance/objective input;
- no unique original optimum or an invalid/non-positive `Lambda_ref`;
- a failure of required self-tests, canonicalization, source pinning,
  platform pinning, or ledger replay;
- inability to complete any mandatory package member;
- a source, authority, or protocol identity mismatch.

The only permitted candidate rejections are the predeclared normalized-sector
duplicate rule and `|F| < 100`, within the fixed 128 attempts per slot.

## 5. Predeclared analysis boundary

Each instance is reported separately first. Cross-instance adjudication is
mechanical and unweighted: for each already-declared exact predicate, retain
the vector of five instance statuses plus `all_five`, `any_one`, and
`count_of_five`; do not pool raw rates across instances or with Stage 1.

The Stage-1 H0/H1/H2/H3 threshold limitations remain limitations. This draft
does not invent a rate-comparability, H1 sub-region, or H2 measurability
threshold for either Stage 1 or Stage 2. A claim beyond the family still
requires the final Gate-10 audit and cannot be inferred from five instances
alone.

## 6. Roles, locations, and review cadence

The owner is Shivansh. Codex is the proposed primary producer for Stage-2
implementation and primary Python computation. A separate Claude session,
designated by the owner and not used as the producer for that boundary, is the
proposed independent reviewer. If either role changes, the owner must record
the replacement before the affected write; no producer self-accepts an output.

No directory below is created by this draft. Once the protocol and its
implementation have passed pre-write review, the exact locations are:

| Purpose | Canonical location |
| --- | --- |
| Attempt ledger and accepted-instance index | `research/g9/stage2_generation/` |
| Per-instance input manifests | `research/g9/stage2_instances/stage2_01/` through `stage2_05/` |
| Per-instance original-problem ground truth | `research/g9/stage2_ground_truth/stage2_01/` through `stage2_05/` |
| Per-instance primary and companion outputs | `research/g9/stage2_core/stage2_01/` through `stage2_05/` |
| Independent-review records and Gate-9 synthesis | `research/g9/reviews/` |

The V-14 CUDA/T4 provenance and overlap evidence is not Stage-2 precedent
until independently accepted; its current evidence record is
`research/decisions/GATE_6_V14_CUDA_T4_PROVENANCE_EVIDENCE.md`.

The lean verification rule applies: one independent pre-write review and one
post-write hash/binding audit are required for each scientific output family
(generation, ground truth, primary sweep, each non-primary companion, and
final synthesis). Routine source edits require fixtures and source review but
do not create extra scientific approval steps.

## 7. Owner decision required

Owner approval must accept or amend this entire protocol as one pre-result
choice. Until that approval is recorded, this file is only a proposal and the
Gate-9 hold point in `GATE_9_STAGE2_ENTRY_AND_PREREGISTRATION.md` remains in
force.
