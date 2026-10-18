# Owner Decision Record — Gate-8 Critical Review and Exit

**Status:** APPROVED  
**Owner:** Shivansh  
**Approved:** 2026-09-22 11:05:24 IST  
**Authority:** Direct owner approval in the project-control conversation.

## Owner decision (verbatim)

> I accept the Gate-8 independent critical review as READY and close Gate 8 for
> the accepted Stage-1 record. No stronger conclusion, new computation, Stage-2
> work, or relaxation of limitations is authorized.

## Evidence reviewed and accepted

The independent Gate-8 reviewer reported READY after read-only review of:

- Gate-7 Stage-1 inference artifact
  `research/g7/stage1_inference/STAGE1_INFERENCE.json`, file SHA-256
  `cae3de4152c8d1e4ca0f2d494be8320486efa8374a865359a93529e5510780cf`,
  content SHA-256
  `f76156e9971321e4de7c595bb7ea0a800065dcd349b48fb0292b6f1009816271`;
- Gate-7 owner conclusion and exit record
  `research/decisions/GATE_7_STAGE1_CONCLUSION_AND_EXIT.md`, SHA-256
  `2088e84a6d85184a22d18d10e363e8d6a50ac13f494030e95d48f10929839b84`;
- Gate-6 accepted rate-surface / mechanical-D013 artifact, file SHA-256
  `6f052678ad854f3a8e705c365df4221b70cdaa347007436d3bedbda8e31229ff`,
  content SHA-256
  `00636483e62e78f4b865274b6b79b47842072f90312beee3425c7fce5d8597ea`.

The reviewer independently verified canonical identities and bindings; the
non-firing D013 branch; accepted Gate-5, D011, V-14, and authority pins; exact
aggregate and report consistency; scope containment; and Gate-7 fixture
success under normal Python and `python -O`.

## Critical-review finding

No blocker was found. The review confirmed that the accepted Stage-1 conclusion
is deliberately bounded:

- H0 is falsified only through its exact pointwise rank-flip predicate; no
  unregistered rate-comparability threshold is used.
- H1 is not represented as supported or confirmed without a pre-registered
  sub-region criterion.
- H2 and H3 retain their indeterminate statuses under their stated threshold
  and conditional-ablation limitations.
- D005/D006, kappa/box, V-14 floor-defect/report-only, D011-bias, and
  Stage-1-only conditioning remain intact.

## Non-blocking maintenance notes

The independent review recorded, without reopening the accepted artifact:

1. The Python bytecode guard in `run_stage1_inference.py` occurs after import.
2. `research/g7/gate7_intake.py` is obsolete pre-Gate-6 scaffolding and still
   reports its historical missing-input state.
3. The accepted payload does not self-embed producer-source hashes; the
   accepted artifact identities and post-run audit provide current traceability.
4. Descriptive spatial-component fields may not be repurposed post hoc as a
   crossover criterion.

## Gate effects

1. **Gate 8 is accepted and exited** for the accepted Stage-1 evidence and
   bounded conclusion.
2. This record starts no Gate 9 work and authorizes no Stage-2 design,
   computation, experiment, or inference.
3. No accepted artifact may be modified or reinterpreted beyond the limits
   preserved above without new owner authority and a review appropriate to the
   changed boundary.

## Provenance preservation

This is an additive decision record. `research/decisions/DECISIONS.md` remains
unchanged because accepted artifacts pin its identity.
