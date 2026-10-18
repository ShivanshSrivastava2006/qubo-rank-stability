# Gate-9 Kaggle CUDA core synthetic dry run v2 — outcome

Status: **FAILED CLOSED before the reviewed CLI launched**. This was the single
owner-authorized v2 push; there is no automatic retry authority.

Kernel: `shivanshsrivastava06/g9-cuda-core-nonscientific-dry-run-v2-50f25827`,
version 1, `KernelWorkerStatus.ERROR`.

The locally submitted metadata requested a private T4 GPU run and
`gcr.io/kaggle-gpu-images/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461`.
Kaggle's pulled version-1 metadata still has `enable_gpu: true` and
`machine_shape: NvidiaTeslaT4`, but reports `docker_image` as
`gcr.io/kaggle-images/python@sha256:dafd4ce5668bbf1ad422e4c109e0f18c9623c3a7c7f48b0235f13142755c40b9`.
The pulled source SHA-256 is
`8550de50060de8aaa65eb17d797d68d1fabe36eda99593a9451bb66486a7d119`,
identical to the submitted source. The originally downloaded metadata has SHA-256
`78de6a657dd8fa2d97808e4dea00a5d67d17f512a6b94cdfa61cd73cc3a3df28`;
the repository's [persisted JSON](GATE_9_KAGGLE_DRY_RUN_V2_PULLED_METADATA.json) is
semantically identical but adds a final newline (SHA-256
`36e3fa6c82058940606cc4b296b3c48d71c44c7adc1e70daa7c14431825f2489`).

The [failure log](GATE_9_KAGGLE_DRY_RUN_V2_FAILURE.log) and
[environment diagnostic](GATE_9_KAGGLE_DRY_RUN_V2_PRELAUNCH_ENVIRONMENT.json)
were preserved byte-for-byte from Kaggle, SHA-256
`4b38dc7fc6e3c546c0c121b6208d38f29df09f8741d4cfc2909dd3ebae8d6c8d`
and `bf2b7d129be1f96169b8498ea8bf0f1e482ecf57636df2944f5a66f0f0f5583b`.
The downloaded kernel log SHA-256 is
`8070f1a8241e9bc9af8d1772e3c8e262a69fe80d53534b805358181970654bae`.
The environment reported `COLAB_IMAGE_TYPE=cpu`, no `CUDA_HOME`, no `nvcc` on PATH,
and no `/dev/nvidiaN` character device. The script refused before invoking the
reviewed CLI, so there was no CUDA compilation, qualification receipt, GPU numerical
result, candidate/instance generation, scientific computation, or Gate-10 work.

Inference: Kaggle appears to have stored/substituted the CPU image despite the
submitted GPU-image pin. The runtime environment is demonstrably CPU-only; the
mechanism of the substitution and why no GPU device was attached are not established
by these artifacts. Do not treat `enable_gpu: true` or `machine_shape: NvidiaTeslaT4`
as proof of actual GPU allocation. Resolve that discrepancy through read-only
platform diagnosis and a separately reviewed remedy; any new push requires a fresh
owner authorization.
