# Gate-9 Kaggle CUDA core synthetic dry run v2, version 2 — outcome

Status: **FAILED CLOSED before the reviewed CLI launched**, again. This records the
owner's single UI retry of the v2 bundle. That retry is now spent and no further run
is authorized.

Kernel: `shivanshsrivastava06/g9-cuda-core-nonscientific-dry-run-v2-50f25827`.
The owner used the Kaggle UI **Save & Run All (Commit)** after selecting **GPU T4 x2**
and **Always use latest environment**. The screenshot shows **Version 2** as the latest
version and its state as **Failed**. No Kaggle CLI push, GPU run, or source execution
was performed by the lead for this record; these are downloads and hashes only.

## Downloaded artifacts (version2/latest outputs)

| Artifact | SHA-256 |
|---|---|
| Kernel log `g9-cuda-core-nonscientific-dry-run-v2-50f25827.log` | `d0fe495e3d591f2c89ee06a038cdbfc0957100627646a2da5eb5c364aa0930c7` |
| Failure log `g9_cuda_core_dry_run_failure.log` | `4b38dc7fc6e3c546c0c121b6208d38f29df09f8741d4cfc2909dd3ebae8d6c8d` |
| Pre-launch environment `g9_cuda_core_dry_run_prelaunch_environment.json` | `bf2b7d129be1f96169b8498ea8bf0f1e482ecf57636df2944f5a66f0f0f5583b` |

The failure log and the pre-launch environment diagnostic are **byte-identical to the
version-1 records already preserved in this directory**: the existing
[failure log](GATE_9_KAGGLE_DRY_RUN_V2_FAILURE.log) and
[environment diagnostic](GATE_9_KAGGLE_DRY_RUN_V2_PRELAUNCH_ENVIRONMENT.json) carry the
same two hashes. Those files are left unchanged; this outcome is additive and links to
them rather than duplicating or overwriting them. The kernel log differs from
version 1's (`8070f1a8241e9bc9af8d1772e3c8e262a69fe80d53534b805358181970654bae`), as
expected for a separate run.

## Runtime observed

Same CPU-only runtime as version 1: `COLAB_IMAGE_TYPE=cpu`, `CUDA_HOME` absent, `nvcc`
absent from PATH, and no NVIDIA device node. The bundle refused before invoking the
reviewed CLI, so no receipt was written. There was no CUDA compilation, qualification
receipt, GPU numerical result, candidate/instance generation, scientific computation,
or Gate-10 work.

## Source identity

The latest pulled source has SHA-256
`5054eb41e482313a362ad4665e86f960044e43b0445fe12766a7c4a83bdbd591`. It is exactly the
12-byte marker `b'# %% [code]\n'` prepended to the reviewed source. Removing only that
exact leading marker reproduces the reviewed source hash
`8550de50060de8aaa65eb17d797d68d1fabe36eda99593a9451bb66486a7d119`. The code body is
therefore unchanged; the difference is Kaggle's cell marker, not an edit.

## Pulled metadata

The latest pulled `kernel-metadata.json` has SHA-256
`78de6a657dd8fa2d97808e4dea00a5d67d17f512a6b94cdfa61cd73cc3a3df28`. It still declares
`enable_gpu: true` and `machine_shape: NvidiaTeslaT4`, while `docker_image` is the CPU
repository digest `gcr.io/kaggle-images/python@sha256:dafd4ce5…`.

**No `docker_image_pinning_type` field is present in this metadata.** Do not conflate
that absent field with the `docker_image` value recorded above; nothing here states how
or whether the image pin was interpreted.

## Scope limits of this evidence

- Version-suffix behavior is **not established**. The version-2 output download and the
  latest output download are identical, and the version-suffixed source pull was refused
  with HTTP 403. The evidence above is therefore described as *latest*, justified by the
  screenshot showing Version 2 as the latest version.
- The exact root cause of Kaggle's CPU allocation is **not claimed**. `enable_gpu: true`
  and `machine_shape: NvidiaTeslaT4` must not be read as proof of GPU allocation, and the
  CPU `docker_image` value is an observation, not a demonstrated mechanism.
- The UI retry is spent. No further run, push, or backend change is authorized without a
  fresh explicit owner release.
