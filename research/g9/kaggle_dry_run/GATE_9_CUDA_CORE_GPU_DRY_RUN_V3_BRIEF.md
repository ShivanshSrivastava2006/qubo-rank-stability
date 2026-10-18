# Gate-9 CUDA core GPU dry run v3 — offline implementation brief

Status: **implementation brief only; no execution release**. Prepared after the
one-shot GPU-allocation API probe completed on 2026-09-24. Nothing in this brief
authorizes a Kaggle push, CUDA compilation, §A qualification, Stage-2 data, or
scientific computation.

## Established observations, not a causal diagnosis

- The v1 and v2 core dry-run versions are spent and failed before CUDA
  compilation in CPU runtimes. Do not edit or re-version either kernel.
- The separate private API allocation probe, with submitted metadata omitting
  `docker_image`, completed as version 1. Its versioned log reports two Tesla
  T4s, `COLAB_IMAGE_TYPE=gpu`, `/usr/local/cuda/bin/nvcc --version` return code
  0, and a satisfied CUDA-home guard. Its current pulled source exactly matched
  the pinned probe bytes. See `GATE_9_KAGGLE_GPU_ALLOCATION_API_PROBE_OUTCOME.md`
  and the preserved full log.
- Pulled probe metadata reported
  `gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461`.
  This is an **after-the-fact observation**, not proof that omitting
  `docker_image`, phone verification, or the API delivery channel caused the
  successful allocation. The API did not expose an environment-pinning choice.
- The existing 11-file non-scientific dry-run release remains byte-unchanged at
  SHA-256 `50f25827ef07b8fcbf3f19223f3982b486f1b11c5d71a7d0c037fd1c6f5328a9`.
  `load_release_payload()` currently validates all 11 embedded-source and
  authority hashes. That release was approval for a **spent** run, not an
  approval for v3 execution.

## Requested offline v3 work

Create additive v3 builder, verifier, and release-candidate documentation;
leave v1/v2 builders, bundles, outcomes, the approved 11-file release, all
core sources, protocols, and scientific paths byte-unchanged. The new bundle
must use a new, absent private kernel slug and cannot target a spent kernel.

The v3 metadata must request `enable_gpu=true`, `machine_shape=NvidiaTeslaT4`,
`enable_tpu=false`, `enable_internet=false`, and empty source arrays. **Omit**
both `docker_image` and `docker_image_pinning_type`; do not claim that omission
is the reason GPU allocation succeeded. Keep the exact approved 11-file
source/authority embedding and fail-closed hash/staging checks. Name the image
label honestly as an unverified API-default runtime, not the v2 requested
digest or a claimed Kaggle build identity.

Before the one permitted CLI launch inside a future run, inspect only bounded
environment/device facts: `COLAB_IMAGE_TYPE=gpu`, absolute `CUDA_HOME`,
`CUDA_HOME/bin` on `PATH`, executable resolved `nvcc` exactly at
`CUDA_HOME/bin/nvcc`, and at least one `/dev/nvidiaN` character device. Record
the bounded observations. Do **not** require v2's pinned `BUILD_DATE` or
`GIT_COMMIT`: neither was attested by the allocation probe. The bundle may
record them as diagnostics but must not turn guesses into a provenance claim.
Refuse before invoking the reviewed CLI if any guard fails. After the guard,
invoke the exact reviewed non-scientific `--qualify-self-test` CLI once, with
no retry, no fallback, and a bounded timeout. Preserve a receipt only if the
reviewed CLI succeeds and emits the expected receipt shape; otherwise preserve
a bounded failure log. The receipt must still say §A is **not satisfied**.

Build and verify entirely offline in normal Python and `python3 -O`, with
bytecode disabled. Fixtures should prove the metadata key absence, new slug,
all source hashes, guard ordering, CPU/no-device/missing-or-shadowed-nvcc
refusals, one-launch-on-valid-fixture behavior, and that tampering with any
embedded file fails before the environment check or launch. Use load-bearing
mutations, not merely a self-consistent reference. If the existing v2 verifier
can be safely adapted for v3, preserve its coverage rather than shrinking it.
The unchanged v2 verifier currently passes **134 checks** in each mode
(`PYTHONDONTWRITEBYTECODE=1 python3` and `python3 -O`); those are baseline
evidence for the existing bundle, not v3 or CUDA qualification.

Produce a bundle for `shivanshsrivastava06` in a new empty temporary
directory, report its two exact SHA-256s, and independently review the final
source, metadata, release wording, and tests. The reviewer must check that no
canonical Stage-2 instance, coefficient ledger, candidate, scientific value,
or source was read and that no Kaggle call or `nvcc` invocation occurred.

## Release boundary

A READY offline verdict is **not** permission to push. Before any v3 Kaggle
run, the owner must approve a new, final hash-specific one-attempt release
that names the exact bundle hashes, one private kernel slug, one CLI command,
no retry, and read-only post-run retrieval. A v3 pass would establish only a
non-scientific CUDA dry run; amendment §A's corrupted-kernel qualification
and the Stage-2 scientific write boundaries remain separate.
