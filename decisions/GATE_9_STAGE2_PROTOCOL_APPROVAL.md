# Owner Decision Record — Gate-9 Five-Instance Stage-2 Protocol

**Status:** APPROVED — IMPLEMENTATION AND REVIEW ONLY  
**Owner:** Shivansh  
**Approved:** 2026-09-22  
**Authority:** Direct owner approval in the project-control conversation.

## Owner authorization (verbatim)

> I approve the Gate‑9 five-instance Stage‑2 pre-result protocol at SHA‑256
> `8a5785fd6d495f548ebd94d61fac9aab9986413c2c1d2b0a7528500fd86635d0`.
> This fixes U‑08 through U‑11 and authorizes implementation and review of the
> deterministic generator, but no Stage‑2 scientific computation until its
> pre-run review passes.

## Accepted protocol

The accepted document is
`research/decisions/GATE_9_STAGE2_PROTOCOL_DRAFT.md`, file SHA-256
`8a5785fd6d495f548ebd94d61fac9aab9986413c2c1d2b0a7528500fd86635d0`.

This closes the design choices U-08 through U-11 as the approved Stage-2
protocol: exactly five instances; deterministic independent streams; a
249-day parametric return/covariance draw; balanced five-asset sector blocks;
first-valid ordering with a fixed 128-attempt cap; and the sole candidate
feasibility guard `|F| >= 100`.

## Scope now authorized

Implementation and review of the deterministic generator and its validators
are authorized. No candidate draw, screening, retention, instance manifest,
ground truth, scientific core/companion sweep, or inference may occur until a
pre-run review of that implementation passes and the owner separately permits
the resulting write boundary.

The accepted protocol's Python-only primary-producer clause remains binding.
`GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md` is a later proposed amendment,
not part of this approval; it has no effect until independently reviewed and
explicitly accepted by the owner.

## Preserved limits

This decision does not alter any accepted Stage-1 artifact or conclusion. It
does not change D006/D011/D013/D015/D016, introduce a hypothesis threshold,
authorize a GPU primary result, authorize a Stage-2 scientific computation, or
begin Gate 10.
