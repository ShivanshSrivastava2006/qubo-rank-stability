# Gate-9 §B Kaggle Provider Trust Amendment — DRAFT

**Status:** DRAFT, unapproved. Takes effect only on owner approval of its final file SHA-256 (the project's convention). Authorizes no Kaggle push, run, candidate, instance, scientific write, or Gate-10 work. No scientific launch is authorized.

## 1. Explicit Provider Trust

On approval of this amendment, the owner explicitly trusts Kaggle as the execution provider for this project.

**What this trust covers:** On approval, the owner trusts that the platform runs the submitted source on the image and hardware it reports, and does not alter inputs, execution, or outputs.

**Residual risk accepted:** With the platform trusted, neither pre-write identity checks (removed) nor the §C post-write audit can detect a producer that ran a different image or altered results while reporting consistent metadata; the §B item 2 comparisons detect numerical deviation only at the listed validation coordinates and only as executed on the trusted platform; owner-side recomputation of sampled points, if used, is the only layer independent of the platform, and it is partial.

## 2. What is Removed

This amendment removes **only** the independent pre-write executing-image proof. Specifically:
- The requirement being removed originates in owner Choice A, `GATE_9_SECTION_B_STRICT_IMAGE_IDENTITY_OWNER_DECISION.md` (SHA-256 `db00ba1a2ae1f6ec981541746bea6cbeb3f06ffb7f8e467bf77eb55fb5de4369`), which interpreted the approved amendment as requiring that a session's own executing-image identity be independently established before its first scientific write. This amendment supersedes ONLY that executing-image element of Choice A.
- The approved `GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md` (SHA-256 `589fdc29d71cd5f70c0734e927d109dc00b389b40cc7c485e56a655f41fd57cf`) is not edited. Its execution rule, under which a session may produce records only when its qualification identity (including the Kaggle image/build) exactly matches a passed qualification record, remains in force; the image/build element of that identity is satisfied by platform-reported values as stated in §3.
- Choice A's other operative content stands: §B remains **OPEN**, and no Stage-2 scientific output may be written on Kaggle until the remaining §B requirements quoted in §4 are independently reviewed and satisfied. Approval of this amendment satisfies none of them and closes nothing by itself.

## 3. Image Metadata and Qualification

Image metadata—such as `KAGGLE_DOCKER_IMAGE`, saved-version metadata, and filesystem/package fingerprints—are recorded strictly as **PLATFORM-REPORTED**. They must be labelled as such in every record, and are never called proof.

A change in platform-reported image metadata **still forces requalification** under the approved execution rule. The qualification identity still includes the reported image/build, now strictly as a reported value rather than an independently proven one.

## 4. What is Retained

Every other requirement from the approved Kaggle CUDA amendment must remain in full force, unchanged, including its entire "Proposed execution rule" section (the exact-match qualification identity, one qualification identity per complete five-instance family, and the fixed binary64 numerical contract). The list below quotes VERBATIM the requirements in the categories the owner named; it is not exhaustive, and nothing omitted from it is relaxed:

- **Source and input integrity**:
  Under `### B. Per-session and per-instance validation`:
  > "1. recheck the approved protocol, generator, ground-truth, source, platform, and compiler identities;"

  This recheck remains in full; any image/build value it compares is platform-reported (§3).

- **Numerical qualification (corrupted-kernel rejection)**:
  Under `### A. Generic engine qualification`:
  > "The qualification must include deliberately corrupted-kernel rejection tests for accumulation order, index order, tie threshold, slack register handling, and non-finite outputs."

- **Numerical qualification (full-domain comparisons)**:
  Under `### B. Per-session and per-instance validation`:
  > "2. compare CUDA and Python bit-for-bit on the full prepared binary domain for both encodings at every fixed validation coordinate the session may produce: primary `(30,30,30)` at each `r in {0.5,1,2}` under every D015 comparator pair; D011 `(6,6,6)` on its declared 13-cubed subgrid; V-14 0.5x `(0,0,0)`, `(15,15,15)`, `(30,30,30)`, `(30,0,15)`; and V-14 2x `(0,0,0)`, `(55,55,55)`, `(110,110,110)`, `(110,0,55)`. If D013 fires, immediately before its CUDA ranges run, repeat this full-domain comparison at primary `(30,30,30)` for each of `C`, `CB`, `CS`, and `CSB`, including their inactive `+0.0` families. Every comparison includes energy-minimum words, canonical minimum index, tie flags, and D015/D016 reconstruction; and"

- **§B item 3 (the qualification-record content limit, referred to in other project records as §B.3)**:
  Under `### B. Per-session and per-instance validation`:
  > "3. write only the pass/fail counters, platform/source identities, and canonical validation digest. It retains no unapproved coordinate-level scientific values in the qualification record."

- **Fail-closed behaviour (session-wide)**:
  Under `### B. Per-session and per-instance validation`:
  > "The GPU is fail-closed: any mismatch, non-finite value, missing identity, invalid compiler flag, unavailable CUDA device, or interrupted validation prevents that session from writing the affected scientific records. A failed session is not repaired by changing numerical flags, code, coordinates, or thresholds after seeing the failure; such a change requires a new reviewed amendment."

- **Checkpoint validation and complete coverage (exact non-overlapping cover)**:
  Under `## D013 and restart handling`:
  > "Before the first production session of each instance/output family, the producer seals one canonical range plan with a content hash and an exact `[start, stop)` partition of its canonical linear coordinate order. Every range manifest carries that plan hash. A range is atomic: its records and manifest are written to staging, verified and atomically promoted together; an interrupted range is discarded, never resumed mid-range. A range is complete only when both records file and content hashes match its manifest. A later qualified session may run only a missing whole range, may not rewrite a completed range or repartition the plan, and may not aggregate before the final-set audit confirms an exact, non-overlapping cover of the sealed plan."

- **Complete coverage (§C post-write audit)**:
  Under `### C. Scientific-output review boundary`:
  > "After the five independent instances (or a declared hard stop) finish one scientific output family, that complete family needs one independent post-write hash/binding audit before acceptance. Per-instance validation is part of the producer's run; it does not add five repetitive review gates. This is the lean protocol's single audit at a material output boundary, not a full Python repetition of the grid. A source or platform change returns to A or B as applicable."

- **The D013 mechanical rule and the +0.0 evaluator prerequisite**:
  Under `## D013 and restart handling`:
  > "The original D013 exact-sign trigger remains mechanical and per-instance. A fired branch runs all and only the already-approved conditions once the separate `+0.0` inactive-family evaluator has passed its required validation. An unfired branch runs none. CUDA changes neither branch. The approved five-instance protocol's stronger prerequisite is unchanged: its `+0.0` evaluator validation must be available before any Stage-2 core pass starts."

- **Generator pre-run review and separate owner write authorizations**:
  Under `## Limits` (in the approved amendment draft):
  > "- This amendment does not authorize Stage-2 instance generation; the approved protocol's implementation and generator review still come first."
  Under `## Preserved limits` (in the approval record `GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_APPROVAL.md`):
  > "The Stage-2 generator remains subject to its own successful pre-run review and separate owner write permission."

## 5. Sampled Verification

This amendment neither requires nor forbids sampled verification. The unapproved sampled verification amendment remains unapproved, and nothing here is a dependency of it. This amendment establishes no sample floor and no corruption model.

If sampling is used, it is described **ONLY as quantified partial verification**.
- It does **NOT** independently establish D013 (a count-sign over every grid point), exact counts, or complete topology.
- It is most useful against widespread/systematic error, and weak against targeted corruption of a few points.

The numbers for a per-instance grid of **680,943** points demonstrate this limitation:
- A sample size of **2,000** detects **1** corrupted point with a **0.29371%** probability (`per_instance_only_not_family_wide`).
- A sample size of **2,000** detects **681** corrupted points (0.1%) with an **86.522%** probability (`per_instance_only_not_family_wide`).
- A sample size of **2,000** detects **6,809** corrupted points (1%) with a **> 99.9999%** probability (`per_instance_only_not_family_wide`).
- For **6,809** corrupted points (1%), a sample size of **459** gives a **99.009%** probability, and **916** gives a **99.990%** probability (`per_instance_only_not_family_wide`).

All figures are PER INSTANCE ONLY, not family-wide. No family-wide probability is claimed here.

## 6. Limits

Nothing else in the approved amendment or protocol changes. This amendment authorizes no conclusion, threshold, instance, or parameter change.

## 7. Owner Decision Required

To take effect, the owner must approve this entire amendment by its final file SHA-256 after independent cross-review. Approval explicitly accepts the Kaggle trust statement and removes the pre-write executing-image proof requirement, while retaining all other validation rules.
