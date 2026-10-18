# Gate-9 Kaggle synthetic dry run v1 — read-only postmortem

Date: 2026-09-24. This note changes no execution authority and reports no scientific result.
The lead performed a read-only investigation; the reviewer independently inspected the pulled
server metadata and image configuration fields named below. Neither performed a second run.

## Established by the failed run

The reviewed CLI passed the approved-release/source checks and stopped at
`shutil.which("nvcc")` with `nvcc is unavailable`. No compiler invocation, GPU probe,
NumPy import, qualification receipt, or scientific computation followed. The observed
failure proves **`nvcc` was not on that process's `PATH`**. It does not, by itself,
prove that no compiler was installed elsewhere or that no GPU device was attached.

## Read-only Kaggle and image evidence

The lead used read-only `kernels status` and `kernels pull -m` calls for version 1.
The pulled `kernel-metadata.json` is SHA-256
`b271f425fdfb19921ae52133d0a77ad6529cb130e378d510c7320eee448bb242`.
It reports `enable_gpu: true`, `machine_shape: NvidiaTeslaT4`, `is_private: true`, but
`docker_image: gcr.io/kaggle-images/python@sha256:dafd4ce5668bbf1ad422e4c109e0f18c9623c3a7c7f48b0235f13142755c40b9`.
Kaggle's [docker-python README](https://github.com/Kaggle/docker-python/blob/main/README.md)
identifies `gcr.io/kaggle-images/python` as its CPU-only image repository and
`gcr.io/kaggle-gpu-images/python` as its GPU repository. The anonymously retrieved
CPU image config (SHA-256
`baf69fed26af6330ecb1c477f3aa0470f5d83a390ab86b63ac3239d5c153b624`)
has `COLAB_IMAGE_TYPE=cpu` and a `PATH` without `/usr/local/cuda/bin`. A separately
retrieved GPU-image config (SHA-256
`c72831376c5485ec652a6f4a771bf091ae0726310e1b9db3db064387e173e941`)
has `COLAB_IMAGE_TYPE=gpu`, `CUDA_VERSION=12.8.1`, and `/usr/local/cuda/bin` on `PATH`.
Kaggle's [Dockerfile template](https://github.com/Kaggle/docker-python/blob/main/Dockerfile.tmpl)
uses distinct CPU and GPU base images.

The server metadata's CPU-image pin is a **strong lead**, not proof of the exact runtime
container. Kaggle might translate the recorded image at runtime; version 1 did not record
image environment or a device fingerprint. The mechanism by which Kaggle selected or
recorded the CPU image is not established.

## Prospective repair boundary

A PATH-only change is not justified: it would not supply a missing compiler if the CPU
image was actually run. The narrow next investigation is to determine whether Kaggle can
honour an explicitly selected, hash-pinned GPU image, and add a **pre-launch** image/compiler/
device check that emits only diagnostic evidence if the environment is wrong. That would
change the unpinned Kaggle bundle, not necessarily the eight-file approved core release.
The image choice and diagnostic check would need fixtures, independent review, new bundle
hashes, and an additive owner decision for any upload or new run. If Kaggle cannot provide
a suitable compiler-equipped GPU image, an alternative qualified platform or reviewed
offline toolchain plan is needed. Do not reuse version 1's authority for another attempt.
