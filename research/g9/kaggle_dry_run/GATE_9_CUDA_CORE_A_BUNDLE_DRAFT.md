# Gate-9 §A CUDA corruption qualification — offline Kaggle handoff draft

Status: **ARCHIVED PRE-RUN HANDOFF; ONE PUSH LATER COMPLETED; §A NOT SATISFIED**.
This records the handoff for one private, non-scientific GPU
corruption-qualification attempt. The owner later separately authorized and
The reviewer performed exactly one push of the bound bundle. Its GPU checks passed,
but the predeclared image-to-run provenance condition remains open; see
`GATE_9_KAGGLE_CORE_A_VERSION1_OUTCOME.md`. Neither this handoff nor that
run authorizes Stage-2 candidate or instance generation, scientific
computation, or Gate 10.

## Bound candidate

The read-only qualifier plan has content SHA-256
`a99fae9dd50f3c29e4db5110d05afc37f406f1cf443fbd03ae0009cba5d29856`.
It binds the approved clean core release
`50f25827ef07b8fcbf3f19223f3982b486f1b11c5d71a7d0c037fd1c6f5328a9`,
the preserved clean T4 receipt
`41a32675e667ffe8e9fb0e2a5d15b191c242f39a221ce9a3d941152f41530859`,
the exact twelve-file source map, eight deliberately corrupted CUDA source
hashes, and unchanged numerical compiler flags. The qualifier itself is
`65f0f1d67d9df65602df28854b1dcae976a9c0bfe0c25eebb45cd7249527e218`.
Its staged CLI is
`be6c06cf0587a0f4dadb47fb19554c4cbd4f368d9906a37bbc7b714c9c86f8b8`.
The offline bundle builder is
`2c678dfb937542b94750b2b15317380fc68aa8db260e30f27db6811af2d97706`;
its verifier is
`3a5a7d70b612904fface0c94fd0eba17a83bbceaa90d62053a106b5b097bf71e`.

The bundle builder's `--plan` is read-only and byte-identical under normal
Python and `python3 -O`. Bundling refuses until a separate canonical A release
exists at
`research/decisions/GATE_9_CUDA_CORE_CORRUPTION_QUALIFICATION_RELEASE.json`,
has status `approved`, binds that exact plan hash and source map, and matches
the `--reviewed` SHA-256 supplied at invocation. The owner-approved canonical
release now exists at SHA-256
`585da5d87908738e34c9b9858a0ef6d1c5e5cf4311dd1f6e3ba00a9d0ce6bfb9`.
The qualifier's release gate accepted that exact hash and plan binding before
any `nvcc` lookup. One subsequent Kaggle submission occurred as documented in
the outcome record; no retry or version 2 is authorized.

The builder embeds exactly seventeen bound files:
the twelve plan-bound sources/fixtures, the approved clean release and its
receipt, both amendment authorities, and the new A release. The generated
metadata requests one private Python script on a T4 GPU, internet off, no
attached sources, and no submitted `docker_image` or pinning field. Its slug
derives from the A release SHA and must not be reused for a retry or version 2.

The staged two-file bundle is at `/tmp/g9-A-bundle.quiYZ5nD/`:

| Staged file | SHA-256 |
| --- | --- |
| `g9_cuda_core_a_corruption_qualification_kaggle.py` | `4cf901c1c07370409aed2cb800c2172bc08e76f98c2e499042cc3b9698807588` |
| `kernel-metadata.json` | `84759f03f29a02f2a557acee8e33df50d438feb133553be4b9d30a83718bed39` |

The proposed new kernel ID is
`shivanshsrivastava06/g9-cuda-core-a-corruption-qualification-585da5d8`.
A second fresh temporary build reproduced both files byte-for-byte. The
staging directory contains exactly these two regular files. Temporary staging
is not a durable release archive; recheck its bytes immediately before any
separately authorized push.

The launcher will verify every embedded hash and the exact file set, stage and
rehash in a fresh temporary root, check the observed GPU image/toolchain/device
and required build fields without executing a binary, then invoke the reviewed
`--qualify-corruptions --reviewed <A release SHA>` CLI once. The launch timeout
is 7200 seconds, a cap rather than a runtime guarantee. Only an exact
canonical pending receipt with all eight planned, Python-rejected mutations
is saved; otherwise only a bounded failure log is written.

## Offline evidence and review limits

The repaired qualification fixture passed 8/8 selected compiled host mutations
under normal and optimized Python. The separate bundle verifier passed 225
checks in both modes, including a read-only check of the actual approved
release. Its other release and launcher tests use a synthetic approved release
only inside a `TemporaryDirectory`, a mocked launcher process, and fake device
nodes. It checked the real release binding, exact 17-file staging, tamper cases,
preflight failures, one-call behavior, malformed receipts, eight-mutation
requirements, and reproducible launcher bytes under distinct Python hash
seeds. It independently requires eight distinct planned mutations and the
reviewed compiler flags, and proves the CLI refuses a shadowed Python import.
No Kaggle API, CUDA compiler, GPU, or real Stage-2 data was used.

The clean T4 dry run remains distinct evidence, not §A. A GPU corruption
receipt will deliberately say
`not_satisfied_pending_post_run_audit_and_owner_acceptance`; it is not a
production qualification identity and cannot authorize scientific work.

## Post-run acceptance rule to review before any push

The proposed run must use a new slug for a single version only. After the
one attempt, an explicitly authorized read-only audit must preserve the
version-1 status, versioned output, submitted and pulled script bytes, pulled
metadata, receipt or failure log, and their SHA-256 values. It must establish
that the current unversioned pull still refers to the sole version by checking
that no version 2 exists and that pulled script bytes exactly match the staged
launcher. Pulled metadata must identify the same private T4 GPU script,
internet-off and source-free request and report a `docker_image` of the form
`<repository>@sha256:<64 lowercase hex digits>`. The digest is an observed
Kaggle metadata value, not an image pin submitted by us.

The audit must also compare the versioned receipt's observed `BUILD_DATE`,
`GIT_COMMIT`, `CUDA_VERSION`, GPU model/capability, driver/runtime, `nvcc`,
Python/NumPy versions, compiler flags, source map, plan, and all eight
mutation outcomes against the reviewed constraints. An independent image
configuration or otherwise version-bound source of truth is needed to prove
that the pulled digest describes the image that executed the run; matching a
current unversioned metadata response alone is not that proof. If Kaggle's
interfaces do not permit that binding, or if any check fails, §A remains
unsatisfied. No acceptance rule may be relaxed after observing a failure.

Only after that audit and explicit owner acceptance could a separate
qualification identity be considered. Per-session/per-instance validation,
the instance-ready runner, record writer, manifest path, and Stage-2
authorization remain separate work.

## Execution boundary

There was no push authority in this document. The one-shot command later
separately approved and used for version 1 was
`/home/shivansh-srivastava/venv/bin/kaggle kernels push -p /tmp/g9-A-bundle.quiYZ5nD --accelerator NvidiaTeslaT4 -t 8400`.
The `-t 8400` session cap leaves a cleanup window beyond the CLI's
7200-second launch cap. The separate authorization did not include retry,
a version 2, or alternate accelerators/images. The attempt is spent. No inference from this
archived handoff grants permission to execute again.
