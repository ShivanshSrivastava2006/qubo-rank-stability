# Gate-9 §B closure plan — DRAFT

**Status:** planning draft by the lead, 2026-09-27. Not an approval, release or
authorization. It authorizes no Kaggle push or run, candidate draw, instance,
ground truth, scientific write or Gate-10 work. §B remains **OPEN**.

**Governing texts:** approved CUDA amendment (`589fdc29…`); owner-approved
provider-trust amendment (`aa10e23d…`, approval record `d777e49b…`), which
removed only the independent pre-write image proof; Stage-2 protocol; generator
pre-run review (`research/g9/GATE_9_GENERATOR_PRERUN_REVIEW.md`).

## What the provider-trust approval changed for planning

- No image-proof channel is needed. Image values are platform-reported, but a
  reported change still forces requalification, so **pinning the Kaggle
  environment** becomes an operational requirement: an unpinned notebook can
  silently move to a new image and invalidate the qualification identity.
- Sampled verification is neither required nor forbidden. The beacon, the
  timestamp witness, the commitment adapter, the drand chain choice and the
  `py_ecc` venv are therefore **off the critical path**. They remain an
  optional post-hoc audit layer.

## Current state (from the records)

| Item | State |
| --- | --- |
| §A, v1 engine | Accepted 2026-09-25 for the exact v1 release on T4 / CC 7.5 / driver 13000 / CUDA 12080 / nvcc 12.8.93 / Python 3.12.13 / NumPy 2.0.2 / image `sha256:37c64f…d461`. **No production qualification identity issued.** |
| v2 sidecar | Offline host-emulation only; never compiled with nvcc; new source/ABI identity, so it needs fresh §A plus owner acceptance. |
| Execution contract | `stage2_cuda_execution_contract.py` defines the identity and range-plan/manifest shape; production writer integration and atomic promotion are not established. |
| §B.1 recheck | No in-session harness. Generator guard (applied 2026-09-27) covers the generator-side source/runtime capture. |
| §B.2 comparisons | Engine-level comparisons exist for qualification; no per-session harness over the full coordinate list. |
| `+0.0` inactive-family evaluator | No implementation found; `src/g5/domains.py:127` deliberately refuses inactive families. The protocol requires its non-scientific validation before the first core pass. |
| Generator | Pure mechanics reviewed. Missing: implementation record, before-draw checks integrated, atomic generation writer, owner draw/write permission. |

## Decisions needed first

- **D1 (owner) — engine: v1 or v2.** the lead recommends **v1** unless a gap audit
  (WP0) finds a production need that only v2 meets. v1 already has §A; v2 costs
  a fresh §A qualification and an extra Kaggle push.
- **D2 (owner) — sampling layer.** Recommendation: defer it. It is not needed to
  close §B; revisit after the first family if an independent audit is wanted.

## Work packages

Offline packages are built by one external model and validated by the other in
isolated copies, with mutation tables and the pyc/`-B` rules. The lead decides
and applies only PASS builds.

| WP | Content | Depends on | Kaggle? |
| --- | --- | --- | --- |
| **WP0** | v1 production-gap audit: can v1, as accepted, produce every declared record type (both encodings, D015/D016 reconstruction, D011, V-14, D013 families)? | — | no |
| **WP1** | **Production qualification identity.** Define the record from the v1 §A evidence and the execution contract: source map, flags, platform fields, image fields labelled platform-reported. Define the exact-match rule and environment pinning. Independent review, then owner acceptance. | D1, WP0 | no |
| **WP2** | **§B item 1 recheck harness.** Before any write, compare protocol, generator, ground-truth, source, compiler and platform identities with the accepted identity; fail closed. | WP1 | no |
| **WP3** | **§B item 2 validation harness.** Full-domain CUDA-vs-Python, bit-for-bit, both encodings, at every listed coordinate, plus the D013 pre-range repeat. Retain only counters, identities and digest (§B item 3). Measure session time: the pure-Python reference is about 290 s per coordinate-row, so the list may need about an hour per session. | WP1, WP6 for the D013 repeat | no (build) |
| **WP4** | **Production writer.** Sealed range plan, staging with atomic promotion, manifests with content hashes, interrupted-range discard, missing-range-only resume, final-set exact-cover audit. | WP1 | no |
| **WP5** | **Generator production path** (the generator review's items 1–3): implementation record pinning generator and validator hashes plus the full runtime fingerprint; guard integrated before and after the draw; atomic generation writer. Ground truth is recomputed on CPU. | — | no |
| **WP6** | **`+0.0` inactive-family evaluator**, plus its reviewed non-scientific validation. | — | no |
| **WP7** | **Non-scientific end-to-end Kaggle dry run** on synthetic inputs: pinned environment, WP2→WP3→WP4 in one session, no scientific value. It checks that the platform still reports the §A image. If it does not, or v2 was chosen, §A requalification is folded in. | WP1–WP4, WP6 | **push #1** (owner approval) |
| **WP8** | **Owner gates, in order:** accept WP1 identity and WP7 outcome → generator draw/write permission (WP5; runs locally) → scientific write authorization → launch. | WP7, WP5 | production pushes (owner approval each) |

WP0, WP5 and WP6 can start immediately and run in parallel. WP1 follows D1 and
WP0; WP2–WP4 follow WP1. Everything before WP7 is offline.

## Risks

- **Kaggle image drift:** the most likely schedule risk. Mitigate by pinning the
  environment in WP1 and checking the reported image in WP7.
- **Session length:** the WP3 Python reference cost may approach the GPU-session
  limit once all coordinates are included. WP3 must measure it; splitting
  validation across sessions is not allowed by the amendment without review.
- **WP6 scope:** unknown size; it is the only prerequisite with no existing code.

## Revision 2026-09-27 — owner decisions after WP0 round 2

Recorded in `research/decisions/GATE_9_WP0_D013_CUDA_PATH_AND_IDENTITY_SCOPE_OWNER_DECISION.md`
and in `GATE_9_D013_INACTIVE_EVALUATOR_SPEC_OWNER_DECISION.md`.

- **D1 holds:** v1 remains the engine. WP0 found no production need that only v2
  meets.
- **New WP6b — additive CUDA `+0.0` path.** v1 refuses inactive `+0.0` families
  (`stage2_cuda_core_bridge.cu:29`), but a fired D013 branch runs as CUDA ranges.
  - The capability is built in new files; the 12 v1 files stay byte-identical.
  - Bit-exact reference: the WP6 Python evaluator. WP6b depends on WP6 step 2.
  - Needs its own §A corruption qualification (including `+0.0` and
    slack-register cases), folded into the WP7 Kaggle session.
- **WP1 scope decided (G10):** the production identity binds the 12 §A files,
  the WP6b path and every host-side record-shaping file (WP2, WP3, WP4, D016
  reconstruction, generation binding). WP7 qualifies that identity, and any later
  change to a bound file forces requalification.
- **WP7 therefore covers, in one owner-approved push:**
  - WP6b §A corruption qualification;
  - production-identity qualification;
  - the non-scientific end-to-end dry run.
- **Commitment requirements** (WP0 §5, pending round-3 validation): the record
  form, a sealed per-instance root, an external timestamp and a pinned
  chain/round-selection rule must be fixed in WP4 before production, even though
  sampling itself is deferred.
- **New WP5b — per-instance Python preparation.** Protocol §4 (`GATE_9_STAGE2_PROTOCOL_DRAFT.md:174-178`)
  requires, for each accepted instance before any encoding sweep, the original
  feasible optimum, `Lambda_ref`, and the D006/D008/D010 ledgers rebuilt under
  the frozen formulas with instance-specific provenance. The amendment assigns
  these to Python (`:51-52`). They are record-shaping, so they are bound into the
  production identity. The work is offline build plus synthetic fixtures, and
  it runs locally on real instances only after the owner's draw/write
  permission. Surfaced by the WP0 round-3 validator; it was missing from this
  plan.
