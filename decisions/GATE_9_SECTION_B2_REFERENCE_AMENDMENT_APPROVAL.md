# Owner Decision Record — Gate-9 §B item 2 Reference Amendment (Option A)

**Status:** APPROVED — OPTION A ONLY; AUTHORIZES BUILDING THE PRECOMPUTE-SEAL-SHIP STEP; NO PUSH, DRAW OR LAUNCH  
**Owner:** Shivansh  
**Approved:** 2026-09-27  
**Authority:** Direct owner answer in the project-control conversation, selecting the option presented by the lead.

## Owner approval (verbatim option selected)

Question: "Do you approve Option A of research/decisions/GATE_9_SECTION_B2_REFERENCE_AMENDMENT_DRAFT.md at SHA-256 0f8b45d9d6e79152efc651530adf6687480a4bcb9584264f839daaa73a9ebdcc? … Option B is not adopted. This authorizes building the precompute-seal-ship step only, not any push, draw or launch."  
Answer: "Approve Option A".

## Accepted amendment

`research/decisions/GATE_9_SECTION_B2_REFERENCE_AMENDMENT_DRAFT.md`, file SHA-256
`0f8b45d9d6e79152efc651530adf6687480a4bcb9584264f839daaa73a9ebdcc`, rehashed immediately
before this record and matching exactly. **Option A is adopted:** each session's §B item 2
comparison is made bit-for-bit between CUDA and a canonical frozen-Python reference
precomputed offline on the owner's machine for exactly that session's hash-bound inputs,
sealed and shipped into the session; any input-hash mismatch, missing coordinate or
encoding, or bit difference refuses writes. **Option B is not adopted.**

## Preserved limits

Nothing else in the approved CUDA amendment, the provider-trust amendment or the Stage-2
protocol changes. No frozen calculation is replaced. This record authorizes building and
synthetic testing of the precompute-seal-ship step only; it authorizes no Kaggle push or
run, candidate draw, instance, ground truth, scientific record or launch. §B remains
**OPEN**.
