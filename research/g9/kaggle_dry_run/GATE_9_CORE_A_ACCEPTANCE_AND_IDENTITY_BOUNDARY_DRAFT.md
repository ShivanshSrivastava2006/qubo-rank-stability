# Gate-9 §A acceptance and CUDA identity boundary — owner-review draft

Status: **OFFLINE DRAFT ONLY; §A NOT YET OWNER-ACCEPTED; NO QUALIFICATION
IDENTITY ISSUED.** This document records the next decision and design
questions. It is not a range-plan pin, production release, scientific
record, or authorization for another Kaggle run.

The CUDA amendment is accepted by the owner at SHA-256
`589fdc29d71cd5f70c0734e927d109dc00b389b40cc7c485e56a655f41fd57cf`,
but its durable approval limits work to implementation, fixtures, and review.
The later one-shot §A GPU attempt was separately authorized and is spent.

## 1. Decision awaiting the owner: accept the §A evidence

In the completed synthetic corruption test, all eight planned CUDA
corruptions were rejected by the Python reference; three were also rejected
by the device self-test. An independent reviewer judged the previously
missing image-to-executed-version evidence condition closed by Kaggle's
version-1 run record, parsed from raw responses. The owner has not yet
accepted that judgment. The evidence to accept or reject is bound by:

| Evidence | SHA-256 or identity |
| --- | --- |
| Approved §A release | `585da5d87908738e34c9b9858a0ef6d1c5e5cf4311dd1f6e3ba00a9d0ce6bfb9` |
| Qualifier plan, content SHA-256 | `a99fae9dd50f3c29e4db5110d05afc37f406f1cf443fbd03ae0009cba5d29856` |
| Version-1 receipt file | `e6f18e4a9b198b1e8dfd61a09e79588f1ca0c7e425cd62ee7388500731ee0217` |
| Version-1 outcome record | `fe42a38170e1dbda433974990236353900c6217031afdc880d58fb7741c7ea59` |
| Sanitized execution-image attestation | `04baf3acb4ca8be20cd015047ad5543e1f48d16cb68a7b382c94abc139857b85` |
| Kaggle raw `ListKernelVersions` response | `121d2d927f51e49cd74d7f4dce5eb29b7f2fc964605b86963120e557c1aa71b9` |
| Kaggle raw `GetKernelViewModel` response | `b0489f93edddf3aaecda366461a57a8c855d845bbd9159ff7afa5d5763bda7e3` |
| Saved version/run | version 1 (ID `213905783`), run `352588357`, kernel `135769337` |
| Executed image manifest | `sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461` |
| Executed image config ID | `sha256:c72831376c5485ec652a6f4a771bf091ae0726310e1b9db3db064387e173e941` |

The raw response bodies are private, owner-only files outside the project,
as documented in the sanitized attestation. The trust assumption is explicit:
**the image binding relies on Kaggle's unsigned, version-bound platform run
record, not an image digest measured inside the run.** Kaggle reports two
repository names for the same content digest. The independent review found
that this meets the predeclared “otherwise version-bound source of truth”
condition under the original rule, without waiver; the owner must decide
whether to accept that finding.

Proposed owner decision, **not yet made**: explicitly accept or reject that
evidence and trust assumption as satisfying this one §A corrupted-kernel
qualification attempt, limited to the exact 12-file source map, eight
compiler flags, and observed T4 platform tuple. The offline source review
and normal/`-O` fixture passes remain part of that evidence. Acceptance
would be recorded in a separate immutable
decision record; the historical receipt's pending fields would not be
rewritten. Acceptance by itself would not issue a CUDA qualification identity,
approve a new GPU attempt, authorize Stage-2 generation or scientific writes,
or start Gate 10.

## 2. Identity-binding design questions (no identity value yet)

`stage2_cuda_execution_contract.py` defines a canonical qualification identity
with exactly eight platform fields plus `source_sha256` and `compiler_flags`.
Its digest may pin a range plan, so **do not call `qualification_identity()` on
the real evidence or emit its content hash before the owner accepts §A and
the field rules below are reviewed.**

| Required field/group | Candidate evidence | Open issue |
| --- | --- | --- |
| GPU name, compute capability, driver/runtime | §A receipt `platform_probe`: Tesla T4 / 7.5 / 13000 / 12080 | Must match a future session before any scientific write. |
| `nvcc_version`, Python, NumPy | §A receipt: full `nvcc` string / 3.12.13 / 2.0.2 | Use exact strings, not normalized approximations. |
| `kaggle_image` | Version-bound manifest digest above | Define a content-addressed spelling; repository name is not stable. More importantly, an exact future-session image check must be possible *before* any scientific write. |
| `source_sha256` | §A receipt's 12-file map; clean diagnostic has 8 files plus `platform_probe_literal` | Define the qualified production source boundary. Qualification-only files are present; the future runner/writer are absent. A production source set differing from the §A-qualified map, including added CUDA code or removed identity-bound files, requires new qualification; review alone is insufficient. |
| `compiler_flags` | §A self-test used eight flags; clean ABI receipt used these plus `-shared` | Define whether the identity binds the complete per-artifact command or a reviewed numerical flag contract, and prove every production build uses it. |

The clean diagnostic receipt's `kaggle_image` is
`kaggle-api-default-gpu-unverified` with origin `operator_asserted`; it must
not be promoted to an image identity. The §A receipt has no in-run digest and
retains `image_digest_status=post_run_metadata_audit_required`. The external
version-bound attestation closes the §A image-to-executed-version **evidence
condition** retrospectively, subject to owner acceptance; §A remains not
satisfied until then. It does **not** provide an in-run, pre-write digest
channel for future sessions.

This is a fail-closed design gate, not a scheduling detail. The accepted
amendment requires a session's identity to match a passed qualification
identity **before** it writes scientific outputs; §B repeats the pre-write
check. In-run `BUILD_DATE`/`GIT_COMMIT`/`CUDA_VERSION` values are useful
cross-checks, but have not been shown to uniquely establish the manifest
digest. A later version-bound audit cannot silently substitute for that
pre-write requirement. Contract-compatible progress requires either an
in-session channel, reviewed in advance, that establishes **that writing
session's own executing manifest digest before its first scientific write**,
or a new execution-rule amendment independently reviewed and approved by
the owner at its file SHA-256. A prior session's run record, a pre-run
registry/tag lookup, or an operator assertion does not satisfy this check.
Neither path is established or authorized here.

After explicit §A owner acceptance, resolution of these field rules and the
pre-write image path, and separate owner authorization, an offline
implementation/review can construct and validate a canonical identity under
the existing schema. Resolving the pre-write image path itself authorizes no
Kaggle session or scientific write. Per-session/per-instance §B full-domain checks,
the inactive `+0.0` families, the record writer and atomic range path, and
the generator's own pre-run review and write authorization remain separate.
No Stage-2 candidate, instance, record, inference, or Gate-10 work follows
from this draft.
