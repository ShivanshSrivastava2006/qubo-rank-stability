# Draft — Gate-9 Kaggle CUDA Primary-Execution Amendment

**Status:** DRAFT ONLY — not owner-approved; not executable  
**Prepared:** 2026-09-22  
**Amends if approved:** `GATE_9_STAGE2_PROTOCOL_DRAFT.md` at file SHA-256
`8a5785fd6d495f548ebd94d61fac9aab9986413c2c1d2b0a7528500fd86635d0`.

## Purpose and non-retroactivity

The approved Stage-2 protocol fixes the instance family and analysis rules. It
currently specifies Python as the primary scientific producer. This proposed
amendment changes **only the execution backend**: a reviewed generic CUDA
engine on a Kaggle GPU may produce Stage-2 core and declared companion records
after the validation gates below. It changes no seed, data generator, sector
rule, feasibility threshold, grid, coefficient map, comparator, classifier,
primary metric, D013 trigger, companion extent, or conclusion rule.

It does not authorize a QAOA, annealing, sampling-noise, or other quantum
hardware experiment. CUDA is solely an implementation of the already-fixed
classical exact certificate.

No Stage-2 instance, candidate attempt, CUDA source, CUDA compilation, Kaggle
execution, scientific record, or GPU result is created by this draft.

## Proposed execution rule

Kaggle is the intended hosted environment. The allocated NVIDIA GPU model,
compute capability, driver, CUDA runtime, `nvcc` version, Kaggle image/build,
and Python/NumPy fingerprints are **not guessed in advance**; they are
captured in a qualification identity. The identity includes every numerical
property above plus source hashes and compiler flags, and deliberately excludes
the transient device UUID and session ID. A session may produce records only
when its identity exactly matches a passed qualification record. A changed GPU
model, compute capability, driver, runtime, compiler, image, source, or
numeric-compiler flag requires a new qualification before any further record
is written.

Every complete five-instance scientific-output family carries exactly one such
qualification identity. Its final-set audit refuses a mixed identity. A later
Kaggle session may contribute only when it receives a matching allocation; a
different accelerator must wait rather than contribute a second platform to an
already-started family.

The engine must use a fixed, reviewed binary64 numerical contract: deterministic
canonical index order; no fast math, contraction, atomics, or nondeterministic
reductions in energy/minimum/tie decisions; explicit non-finite detection; and
the same frozen D015/D016 comparators as the Python reference. It must retain
only the declared Stage-2 records and provenance, never opaque device-only
state as evidence.

Python remains the canonical reference implementation. It produces the
canonical binary64 input/coefficient ledgers and original-problem ground truth;
CUDA consumes those host-validated values and does not derive coefficient maps
on device. The GPU owns fixed-order energy, minimum, and tie-flag evaluation.
The host performs bounded reference checks and reconstructs declared records
from the returned canonical minima/tie data under the frozen Python rules. This
is **not** a duplicate full primary-grid sweep. Once validation passes, the
CUDA engine is permitted to generate the primary and declared companion records
for an accepted Stage-2 instance.

## Required validation before GPU records

### A. Generic engine qualification

Before any Stage-2 candidate is generated, the generic CUDA source and its
Python reference harness require source review and normal/`-O` fixture passes.
The qualification must include deliberately corrupted-kernel rejection tests
for accumulation order, index order, tie threshold, slack register handling,
and non-finite outputs. It must produce no Stage-2 scientific value.

### B. Per-session and per-instance validation

Before a session writes a scientific output for `stage2_01` through
`stage2_05`, it must:

1. recheck the approved protocol, generator, ground-truth, source, platform,
   and compiler identities;
2. compare CUDA and Python bit-for-bit on the full prepared binary domain for
   both encodings at every fixed validation coordinate the session may produce:
   primary `(30,30,30)` at each `r in {0.5,1,2}` under every D015 comparator
   pair; D011 `(6,6,6)` on its declared 13-cubed subgrid; V-14 0.5x
   `(0,0,0)`, `(15,15,15)`, `(30,30,30)`, `(30,0,15)`; and V-14 2x
   `(0,0,0)`, `(55,55,55)`, `(110,110,110)`, `(110,0,55)`. If D013 fires,
   immediately before its CUDA ranges run, repeat this full-domain comparison
   at primary `(30,30,30)` for each of `C`, `CB`, `CS`, and `CSB`, including
   their inactive `+0.0` families. Every comparison includes energy-minimum
   words, canonical minimum index, tie flags, and D015/D016 reconstruction; and
3. write only the pass/fail counters, platform/source identities, and canonical
   validation digest. It retains no unapproved coordinate-level scientific
   values in the qualification record.

The GPU is fail-closed: any mismatch, non-finite value, missing identity,
invalid compiler flag, unavailable CUDA device, or interrupted validation
prevents that session from writing the affected scientific records. A failed
session is not repaired by changing numerical flags, code, coordinates, or
thresholds after seeing the failure; such a change requires a new reviewed
amendment.

### C. Scientific-output review boundary

After the five independent instances (or a declared hard stop) finish one
scientific output family, that complete family needs one independent post-write
hash/binding audit before acceptance. Per-instance validation is part of the
producer's run; it does not add five repetitive review gates. This is the lean
protocol's single audit at a material output boundary, not a full Python
repetition of the grid. A source or platform change returns to A or B as
applicable.

## D013 and restart handling

The original D013 exact-sign trigger remains mechanical and per-instance. A
fired branch runs all and only the already-approved conditions once the
separate `+0.0` inactive-family evaluator has passed its required validation.
An unfired branch runs none. CUDA changes neither branch. The approved
five-instance protocol's stronger prerequisite is unchanged: its `+0.0`
evaluator validation must be available before any Stage-2 core pass starts.

Kaggle session termination is operationally expected. Before the first
production session of each instance/output family, the producer seals one
canonical range plan with a content hash and an exact `[start, stop)` partition
of its canonical linear coordinate order. Every range manifest carries that
plan hash. A range is atomic: its records and manifest are written to staging,
verified and atomically promoted together; an interrupted range is discarded,
never resumed mid-range. A range is complete only when both records file and
content hashes match its manifest. A later qualified session may run only a
missing whole range, may not rewrite a completed range or repartition the plan,
and may not aggregate before the final-set audit confirms an exact,
non-overlapping cover of the sealed plan.

## Limits

- This amendment does not authorize Stage-2 instance generation; the approved
  protocol's implementation and generator review still come first.
- It does not permit CPU and GPU records to be mixed without an explicit
  provenance field. The intended scientific producer for a completed family is
  one qualified CUDA backend.
- It authorizes no result-dependent parameter selection, no change to the five
  instances, no rate pooling, no new hypothesis threshold, no Stage-2
  conclusion, and no Gate-10 work.

## Owner decision required

To take effect, the owner must approve this entire amendment by its final file
SHA-256 after independent review. Until then, the Python-only execution rule
in the already-approved Stage-2 protocol remains binding.
