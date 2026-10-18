# OFFLINE Owner-Decision Memo: Gate-9 §B Pre-Write Image Identity

**Status:** DRAFT
**Prepared:** the second reviewer via the builder; corrected by the reviewer
**Target:** Owner decision required

## 1. Context and Reviewer Ruling

The approved CUDA amendment requires a writing session's qualification identity to match before scientific output is written. The current project interpretation includes that session's exact executing image identity. No reviewed in-session channel has yet established that identity independently of Kaggle's own report. The evidence below shows a gap in the channels tested, not that every possible Kaggle channel is impossible:

*   **Fingerprint limitations:** `/var/lib/dpkg/status` and the distributions enumerated through `importlib.metadata` are runtime observations, not immutable image-layer measurements. The container's writable filesystem view, possible symlink targets and incomplete file coverage mean neither this fingerprint nor package versions establish the exact OCI manifest digest. `/var/lib/dpkg/status` may remain a bounded diagnostic, but not an identity component.
*   **Assertion vs. Proof:** The single in-session `KAGGLE_DOCKER_IMAGE` match observed in the v1 image-channel probe is an *assertion* by the platform, not a proof.
*   **v2/v3 Data Scope:** The v2/v3 data falsify simple CONSTANT/ECHO models for the **saved-version metadata only**, not the in-session variable. 
*   **CPU Follow-up Push:** A CPU follow-up push may test the responsiveness of the in-session variable but cannot by itself close the current strict §B requirement and is **NOT authorized**.

## 2. Stale Document Corrections

The following framing in the existing tracking design draft (`GATE_9_CUDA_IMAGE_TRACKING_EXPERIMENT_DESIGN_DRAFT.md`) and outcome documents is stale and explicitly corrected:

1.  **Identity vs. diagnostics:** The existing sampled filesystem fingerprint does not justify calling it an exact OCI-image identity. It is optional corroborating diagnostic evidence, not a necessary or sufficient §B check.
2.  **Experiment arm dependency:** The original four-arm design predates the preserved v2/v3 saved-version evidence and the fingerprint review. It should be rewritten before any follow-up experiment is proposed. The saved-version and in-session channels must be assessed separately.

## 3. Exact Owner Choices

Kaggle scientific work remains blocked because the strict §B rule has **not yet been met**. The owner must choose one of the following paths:

**Choice A: Retain strict self-proven executing-manifest rule.**
Keep scientific writes blocked unless a reviewed channel can establish the required executing-image identity before the first write. That channel has not been found; a trusted runtime identity service or stronger attestation would be possible routes, but neither is available in the reviewed evidence.

**Choice B: Explicitly amend rule to accept Kaggle platform attestation.**
Amend the rule to accept Kaggle platform attestation with pre-write in-session digest equality (`KAGGLE_DOCKER_IMAGE`), same-session source/compiler/platform checks, and post-run saved-version binding/final audit. This choice explicitly acknowledges the correlated-report risk and makes **no claim of cryptographic self-proof**.

**Choice C: Use a controlled platform with stronger runtime identity access.**
Move the scientific execution backend to a controlled platform with a reviewable runtime identity channel, under a separately approved protocol change.

## 4. Recommendation

**Choice B** is recommended *only* as a risk-accepting protocol change if the owner prioritizes continuing work on the Kaggle platform. 

*Note: the reviewer cannot make this choice; it is strictly an owner decision.*

## 5. Separate Decision: CPU Probe

The owner may separately authorize one CPU-session probe to test whether in-session `KAGGLE_DOCKER_IMAGE` changes when the allocation changes. This is a prediction test of channel responsiveness, not proof that the variable reports the exact executing manifest, and it would not close strict §B. No such push is authorized now.

## 6. Limits of Authorization

Make no mistake: **Approval of Choice B alone does NOT authorize a new push, candidate, instance, science write, or Gate 10.** 
Production source/flags and validation still need separate review and authorization, as stipulated by the approved CUDA amendment. No actual protocol text changes are made or authorized by this document.
