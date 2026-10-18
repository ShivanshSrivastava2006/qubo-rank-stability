# Gate-6 Pre-Production Execution Plan

Status: **PRE-PRODUCTION ONLY — NO GATE-6 COMPUTATION RELEASED**

This plan records the work sequence after Gate-5 acceptance.  It does not
change the frozen decision record, make a scientific claim, derive a rate, or
authorize a production computation.

## Authority and fixed boundary

Gate 5 is accepted by the owner record
`research/decisions/GATE_5_OWNER_EXCEPTION_AND_EXIT.md`.  Gate 6 is authorized
only for its already-frozen Stage-1 scope.  Gate-7 interpretation,
conclusions, post-hoc sensitivity selection, and Rust primary values remain
unauthorized.

The accepted corpus in `research/g5/core_pass_output/` is immutable input.  A
Gate-6 component must never use a G5 runner capable of writing, quarantining,
or otherwise mutating that directory.

## Phase 1 — additive CPU reference foundation

Build and qualify an additive `src/g6/` implementation before any large run.
The reference implementation will provide:

1. A read-only Gate-5 corpus loader with full structural, digest, coverage,
   accepted-platform-split validation, and a mandatory owner-ratified
   per-shard identity-registry boundary.  A future Gate-6 trial or pass must
   use `iter_ratified_records` from the ratified boundary, not the upstream
   structural loader directly.
2. Exact integer-count trigger evaluation for D013, isolated from every
   diagnostic and non-primary result path.
3. Separate, hash-pinned coordinate/coefficient ledgers for D011 and the two
   V-14 grids, including hex-coordinate joins rather than bare grid indices.
4. A Gate-6-specific worker qualification vector, valid under normal Python
   and `python -O` execution, without changing snapshot-pinned G5 fixtures.
5. New output schemas, atomic collision-refusing promotion, restart
   validation, and pass-specific manifests.  Every Gate-6 pass will pin one
   platform fingerprint and refuse drift within that pass. Each trial or pass
   manifest will also pin the live SHA-256 values of its ratified-input
   boundary sources, as recorded by `G6_VALIDATOR_LINEAGE_NOTE.md`.
6. Fixture-only and small primary-instance trials.  No full-grid result is
   released until a fresh independent review accepts the trial evidence.

The bounded CPU qualification trial is fixed in `src/g6/trial_runner.py`:
D011 `(30,30,30)`, V-14 2x's embedded `(70,70,70)` primary coordinate, and
the two V-14 2x all-axis endpoints. It is not a pass runner and can execute
only through the explicit `--run` CLI switch. Its default fixture path performs
no Gate-5 corpus read and no energy enumeration.

The CPU implementation is the correctness reference for any experimental GPU
backend.  It remains separate from the accepted Gate-5 code and corpus.
The ledger emitter's `--reviewed` value is a recorded handoff identifier only;
it is not, by itself, an authenticated approval or a release gate.

## Phase 2 — GPU feasibility qualification (non-production)

The available machine is reported as an AMD Radeon RX 9070.  It is a candidate
accelerator only, not an approved numerical producer.

A separate prototype may establish, on a fixed predeclared fixture set:

- binary64-only arithmetic;
- explicitly disabled floating-point contraction/FMA where applicable;
- bit-for-bit agreement with the CPU reference for every checked energy,
  minimum, raw tie set, decoded tie set, and D016 label;
- measured wall-time and memory use on representative D011 and V-14 points.

GPU output is limited to non-production profiling or cross-check evidence.  It
cannot contribute to a Gate-6 certification artifact or replace the CPU
reference without a separate dated owner approval that expressly authorizes
the named non-Python backend, its numerical contract, and its provenance.
GPU work never mutates or substitutes the accepted Gate-5 corpus.

## Owner execution decisions recorded

`research/decisions/GATE_6_OWNER_EXECUTION_DECISIONS.md` records the
following pre-production choices. They are mechanical reporting and execution
bounds, not scientific conclusions.

1. **D015 deployment scope:** all four frozen pairs apply only to newly
   generated Gate-6 passes; no re-sweep of the completed Gate-5 corpus.
2. **Transition output:** the complete label lattice, exact integer count
   tables, and every face-adjacent unequal-label edge only—no fitting,
   smoothing, ranking, or interpretation.
3. **Cross-platform comparison:** each new pass pins one homogeneous platform
   and refuses drift. V-14 never reuses Gate-5 records; it recomputes the
   embedded overlap solely for a bit-identity artifact.

**Conditional D013 only if it fires** remains unresolved. Before an ablation
run, the owner must resolve the authoritative per-condition feasibility and
`f*_q` contract. G4/G5 coefficient and domain types reject inactive `+0.0`
families, so any D013 evaluator must be additive and separately verified.

## Release sequence

1. Implement Phase 1 and run fixture-only checks.
2. Obtain any remaining conditional D013 decision that applies to the planned
   release.
3. Run the bounded CPU trial; separately run the GPU qualification prototype
   if its environment is ready.
4. Send source, trial evidence, and the execution plan to an independent
   reviewer.
5. Release only the reviewed backend and only the authorized passes.
6. Run each full pass with checkpointing and a homogeneous platform
   fingerprint; then conduct a fresh post-run audit before any Gate exit.
