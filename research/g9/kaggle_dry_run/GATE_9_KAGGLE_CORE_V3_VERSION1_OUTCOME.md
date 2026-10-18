# Gate-9 non-scientific CUDA core dry run v3 — version 1 outcome

Date: 2026-09-24 IST. Owner-approved release draft:
`GATE_9_CUDA_CORE_GPU_DRY_RUN_V3_RELEASE_DRAFT.md`, SHA-256
`f1b6d516d14ebd09791be8e7d52ed3a857e709507751be23a4ab7be545aad671`.
The owner approved exactly one private API push; the attempt is spent.

## Submission and result

- The pre-push gate verified the approved 11-file release, both staged files,
  private/T4/GPU/internet-off/source-free metadata, absence of submitted
  `docker_image` and `docker_image_pinning_type`, installed CLI flags, and
  absence of the new slug from the account's four listed kernels.
- The reviewer invoked the reviewed command once, with no retry:
  `/home/shivansh-srivastava/venv/bin/kaggle kernels push -p /tmp/g9-core-gpu-v3-repaired.dIYqMK --accelerator NvidiaTeslaT4 -t 3600`.
  It returned rc 0, stderr empty, and reported kernel version 1 successfully
  pushed at
  `https://www.kaggle.com/code/shivanshsrivastava06/g9-cuda-core-nonscientific-dry-run-v3-50f25827`.
- Separately authorized read-only status for `/1` reached
  `KernelWorkerStatus.COMPLETE`. Versioned output retrieval for `/1` returned
  the pre-launch environment JSON, a dry-run receipt, and a full kernel log;
  no failure log was listed.
- The log reports `PASS Gate-9 CUDA core dry run` after about 223 seconds.
  The later `mistune`/`nbconvert` warnings are Kaggle-side output-conversion
  warnings; they do not contradict the rc-0 receipt.

## Evidence and audit

| Preserved file suffix after `GATE_9_KAGGLE_CORE_V3_VERSION1_` | SHA-256 |
| --- | --- |
| `PULLED_SCRIPT.py.txt` | `ed4316a2c951fd219114aefdf62c3f609f6ece44126e7446553526f1bd9ffcb0` |
| `PULLED_METADATA.json` | `f014b41c8bcd866a31410411e9181f8ff21b57477eec9e08331e8bdcbdc071a8` |
| `PRELAUNCH_ENVIRONMENT.json` | `4adbe440355b12c9311e84af73d055c0417fe2da047c322258a245a9f8e48202` |
| `RECEIPT.json` | `41a32675e667ffe8e9fb0e2a5d15b191c242f39a221ce9a3d941152f41530859` |
| `FULL_KERNEL_LOG.json` | `882963835dee26da69248d43898c9238b693251441dab8faf92ebd729e7111de` |

Version-specific source pull for `/1` returned HTTP 403, as with the earlier
allocation probe. An unversioned read-only pull succeeded. It is a pull of
the *current* source, not a version-1-specific source response; its raw
bytes nevertheless exactly match the pinned submitted script hash above.
Pulled metadata identifies the expected private T4 GPU script with internet
off and empty source arrays. It reports a Kaggle-selected
`gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461`
image. The submitted metadata omitted both image keys, so this is an
after-the-fact observation, not a chosen image pin or causal explanation.

The versioned pre-launch record reports `COLAB_IMAGE_TYPE=gpu`,
`CUDA_HOME=/usr/local/cuda`, `/usr/local/cuda/bin/nvcc` on `PATH`, two NVIDIA
device nodes and two Tesla T4 models, with `problems=[]`. The receipt is
canonical JSON with a matching `content_sha256`; it binds the exact approved
release SHA-256 `50f25827ef07b8fcbf3f19223f3982b486f1b11c5d71a7d0c037fd1c6f5328a9`,
its ten source/authority hashes, the platform-probe literal hash, and the
reviewed compiler flags. The platform fingerprint reports Tesla T4,
compute capability 7.5, CUDA runtime 12.8, `nvcc` 12.8, Python 3.12.13,
and NumPy 2.0.2. Both bounded ABI validations have `status=pass`, with
one-row and two-row cases and distinct offset hashes. The self-test report
has `verdict=pass` and zero non-finite, reduction, reconstruction,
compaction, illegal-flag, nesting, overflow, and generic-disagreement
counters. The reviewer reran the pinned Python `validate_self_test_report` on the
downloaded GPU report; it passed against the full synthetic reference.

## Scope limit

This establishes a **successful non-scientific synthetic CUDA core dry run**
on the observed T4 platform. The receipt explicitly says
`mode=non_scientific_dry_run`, `scientific_outputs=intentionally absent`, and
`amendment_A_status=not_satisfied_corrupted_kernel_tests_pending`.
`kaggle_image_origin=operator_asserted` and the label
`kaggle-api-default-gpu-unverified` are not a provenance identity. No §A
corrupted-kernel qualification, Stage-2 candidate or instance, scientific
record, inference, or Gate-10 work was authorized or performed. A separately
reviewed and owner-approved §A plan is required before any further GPU run.
