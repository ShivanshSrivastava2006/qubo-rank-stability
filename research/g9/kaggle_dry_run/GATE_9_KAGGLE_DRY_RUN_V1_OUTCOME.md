# Gate-9 synthetic Kaggle CUDA-core dry-run attempt 1 — failed closed

Date: 2026-09-24 (IST). Scope: the owner's one approved **non-scientific synthetic** dry-run
attempt only. This is not amendment §A qualification, Stage-2 computation, or Gate 10.

The approved release was SHA-256
`50f25827ef07b8fcbf3f19223f3982b486f1b11c5d71a7d0c037fd1c6f5328a9`.
The generated private Kaggle bundle had script SHA-256
`1abdf82d745659b55956958c81ade9fce5e5e5837ac7ff72ba0bfe6503f4b284` and metadata
SHA-256 `09c329901365885a6ff8281fe71e3cbe028126a6c77306897d5bdbd6bf7573dd`.
It requested `NvidiaTeslaT4`, GPU enabled, internet disabled, and no attached data sources.
The image label in the bundle was explicitly `kaggle-default-image-unpinned-operator-unverified`.

One CLI push used `/home/shivansh-srivastava/venv/bin/kaggle` 2.2.4 with `-t 3600` and
`--accelerator NvidiaTeslaT4`. Kaggle accepted kernel version 1 at
https://www.kaggle.com/code/shivanshsrivastava06/g9-cuda-core-nonscientific-dry-run-50f25827 .
Its status changed from `RUNNING` to `ERROR`. No second push was made.

The downloaded failure log is preserved byte-for-byte as
`GATE_9_KAGGLE_DRY_RUN_V1_FAILURE.log` (SHA-256
`db711f51e998e5f8b45b6ecc41dd0699f24df684ff4fd892f16da7fe4749fb3e`).
The downloaded Kaggle kernel log had SHA-256
`f7bad9c62e72190852a1396596b380aadeee40d158a05beda19f2d3eaa0f2467`.
The failure log says the reviewed CLI returned 1 with
`FAIL Gate-9 core qualification: nvcc is unavailable`. The release/source checks therefore
passed far enough to reach the `shutil.which("nvcc")` test, but no CUDA compilation or device
qualification occurred. This establishes only that `nvcc` was unavailable on the Kaggle
process `PATH`; it does not establish whether the image contains a compiler elsewhere.
No dry-run receipt or scientific output was produced. A post-run quota query still displayed
30.00 GPU-hours remaining, which does not prove whether a GPU device was allocated.

The single authorized attempt is treated as spent. Do not retry, amend the release, claim §A
qualification, generate Stage-2 data, or start Gate 10 without a new owner decision and review.
