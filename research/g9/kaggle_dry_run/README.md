# Gate-9 CUDA core dry run — offline Kaggle handoff bundle (revision v2)

Packaging only. Nothing here contacts Kaggle, reads Kaggle credentials, runs
nvcc or a GPU, or pushes anything. The bundle is bound to
`research/decisions/GATE_9_CUDA_CORE_DRY_RUN_RELEASE.json` at SHA-256
`50f25827ef07b8fcbf3f19223f3982b486f1b11c5d71a7d0c037fd1c6f5328a9`. That release and its
source/authority files are unchanged from v1.

**No execution authority.** The one owner-approved attempt was used by v1. It failed closed
(see `GATE_9_KAGGLE_DRY_RUN_V1_OUTCOME.md` and `..._V1_POSTMORTEM.md`). Any v2 upload or run
needs independent review of this revision and a new, additive owner decision.

## Changes from v1

- **New kernel.** The slug is now `g9-cuda-core-nonscientific-dry-run-v2-50f25827`. The spent
  v1 kernel (`...-dry-run-50f25827`) is never addressed.
- **Explicit GPU image.** `kernel-metadata.json` adds
  `docker_image: gcr.io/kaggle-gpu-images/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461`.
  v1's server metadata recorded the CPU image, `gcr.io/kaggle-images/python@sha256:dafd4ce5…`.
- **Fixed, non-misleading label.** `--image-label` has been removed. The label is
  `kaggle-gpu-images/python@sha256:37c64f7d…+requested-not-digest-verified`. It states what was
  requested and that the container digest can't be observed from inside the session. The
  reviewed CLI still records it as `kaggle_image_origin: operator_asserted`.
- **Pre-launch environment check.** It runs after the payload and staging hash checks, and
  before the single launch (details below).

## Image pin: fact vs inference

Facts (checked on 2026-09-24 against the anonymous public registry, `gcr.io/v2/...`, with no
credentials):
- `gcr.io/kaggle-gpu-images/python` tags `latest` and `v170` resolve to manifest
  `sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461`. The served manifest bytes re-hash to that digest.
- That manifest's config blob is
  `sha256:c72831376c5485ec652a6f4a771bf091ae0726310e1b9db3db064387e173e941`. This is the
  GPU config named in the v1 postmortem. Its Env includes `COLAB_IMAGE_TYPE=gpu`,
  `CUDA_HOME=/usr/local/cuda`, `/usr/local/cuda/bin` on `PATH`, `CUDA_VERSION=12.8.1`,
  `BUILD_DATE=20260629-122508` and `GIT_COMMIT=fc61d5cda7da39530055bae9bd0e92865f995cd9`.
- v1's CPU digest `dafd4ce5…` is tag `latest`/`v170` in the CPU repository
  `gcr.io/kaggle-images/python`. The GPU pin is the same release line.
- Kaggle CLI 2.2.4's `kernels_push` reads `docker_image` from the metadata file and forwards it
  unchanged as `ApiSaveKernelRequest.docker_image` (kagglesdk 0.1.37). The SDK describes that
  field as "Which docker image to run with. This must be one of the Kaggle-provided, known
  images", and its example is a `gcr.io/kaggle-images/python@sha256:…` reference. Every metadata
  key used here is one that 2.2.4 reads.

Inference and open points (not proven):
- It's not established that Kaggle's server honours `docker_image` on push. It might ignore,
  translate or reject it, and it's unknown whether it accepts this digest as a "known image".
- `docker_image_pinning_type` (`original`/`latest`) is deliberately omitted. Its documented
  meaning covers future versions, and it's unknown how it interacts with `docker_image` on a
  first push.
- The config history installs `cuda-minimal-build-12-8`, which in NVIDIA's packaging includes
  `nvcc`. The layers weren't pulled, so `/usr/local/cuda/bin/nvcc` hasn't been observed
  directly.
- `latest` will move, but the digest pin does not. Kaggle may retire old digests.

## Files

- `build_g9_cuda_core_dry_run_bundle.py` is the deterministic, stdlib-only bundle generator.
- `verify_g9_cuda_core_dry_run_bundle.py` is the offline verifier. It uses a sentinel in place of
  `subprocess.run` and synthetic environment fixtures. It never invokes `--qualify-self-test`,
  nvcc or a GPU.

## Build (offline)

```
PYTHONDONTWRITEBYTECODE=1 python3 research/g9/kaggle_dry_run/build_g9_cuda_core_dry_run_bundle.py \
    --kaggle-user <kaggle-username> --output-dir /path/outside/project/new-dir
```

- `--kaggle-user` must be a lowercase slug (`[a-z0-9]`, single interior hyphens, 1–50 chars).
- `--output-dir` must be new (its parent must exist) or an empty directory. It can't be a
  symlink or sit inside the project tree.

The generator refuses unless the release record hashes to the approved value
and is canonical, lists exactly the reviewed 8 sources and 2 authorities, and
every listed file matches its hash. It embeds exactly those 11 files and no
other repository file. It writes two files and prints their SHA-256 values. Those hashes
depend on `--kaggle-user`, so the bundle for review must be generated for the real username.

- `kernel-metadata.json` makes it a private Python `script` with `enable_gpu: true`,
  `enable_internet: false`, `machine_shape: NvidiaTeslaT4` and the pinned `docker_image`. The
  dataset, competition, kernel and model source lists are empty. The id is
  `<user>/g9-cuda-core-nonscientific-dry-run-v2-50f25827`.
- `g9_cuda_core_dry_run_kaggle.py` is the generated launcher.

## Launcher behaviour (on Kaggle)

1. Decodes all 11 embedded files and checks each SHA-256. It also checks that the embedded
   release's own maps equal the embedded set, which must be exactly 11 files. This guard is
   unchanged from v1.
2. Stages them under a fresh temp root with the `research/...` layout preserved, then
   re-hashes them from disk.
3. **Pre-launch environment check.** It executes nothing: it reads named environment
   variables, does a `PATH` lookup and reads `/dev` and `/proc/driver/nvidia/gpus`. It writes
   bounded, nonsecret diagnostics to `/kaggle/working/g9_cuda_core_dry_run_prelaunch_environment.json`
   and prints them to the log. It records the requested image, `COLAB_IMAGE_TYPE`,
   `BUILD_DATE`, `GIT_COMMIT`, `CUDA_VERSION`, `CUDA_HOME`, whether `CUDA_HOME/bin` is on
   `PATH`, the resolved `nvcc` path, the `/dev/nvidiaN` character devices, whether
   `nvidiactl` is present, and the `/proc` GPU model names. Values are capped at 256 chars
   and lists at 16 items. No other environment variables are recorded. It refuses with exit
   code 2 and a failure log, **without launching**, unless all of these hold:
   - `COLAB_IMAGE_TYPE`, `BUILD_DATE` and `GIT_COMMIT` equal the pinned GPU image's values;
   - `CUDA_HOME` is absolute and `CUDA_HOME/bin` is on `PATH`;
   - the `nvcc` found on `PATH` (the same lookup the reviewed CLI performs) is executable and is
     `CUDA_HOME/bin/nvcc`;
   - at least one `/dev/nvidiaN` character device exists.
4. Only after that, it runs this command once, with cwd set to the staged root:
   `python run_stage2_cuda_core_qualification.py --qualify-self-test --reviewed 50f25827…`
   The environment is the checked environment plus `PYTHONDONTWRITEBYTECODE=1`,
   `G9_ALLOW_NONSCIENTIFIC_CUDA_QUALIFICATION=1` and `G9_KAGGLE_IMAGE_BUILD=<fixed label>`.
   There is no retry and no alternate path; the outer timeout is 3600 s.
5. If rc is 0 and stdout is receipt-shaped, stdout is saved verbatim to
   `/kaggle/working/g9_cuda_core_dry_run_receipt.json`. Anything else produces a bounded
   `/kaggle/working/g9_cuda_core_dry_run_failure.log` (16 KiB tail per stream, plus
   diagnostics) and no receipt.

The environment fingerprint is evidence that the container was built from that image
config. It is not proof of the container digest, and it is not a CUDA qualification. A pass
only means the reviewed CLI was allowed to run.

## Pushing is a separate owner-gated act

`kaggle kernels push -p <dir>` **without `--no-run` starts a GPU session
immediately**. Don't push from this task. Before any push, review both
files and their printed hashes.

The locally installed Kaggle CLI 2.2.4 does not list `--no-run` in
`kaggle kernels push --help`, despite the current online documentation. Do not
assume that a non-running upload is available on this installation; treat its
first push as an execution attempt that needs its own authority.

## Verify (offline)

```
PYTHONDONTWRITEBYTECODE=1 python3    research/g9/kaggle_dry_run/verify_g9_cuda_core_dry_run_bundle.py
PYTHONDONTWRITEBYTECODE=1 python3 -O research/g9/kaggle_dry_run/verify_g9_cuda_core_dry_run_bundle.py
```

The verifier also runs synthetic fixtures against the pre-launch check. Every wrong case must
end with rc 2, zero launches, and a failure log plus diagnostics naming the reason:
- wrong, missing or foreign image fingerprint, including a v1-like CPU environment;
- missing, non-executable or shadowed `nvcc`;
- `CUDA_HOME` unset, relative or off `PATH`;
- no, wrong-type or wrongly named NVIDIA device nodes.

Mutation checks show these fixtures are load-bearing: disabling the refusal, or the device
check, lets a launch through. Every tampered embedded payload, including a modified source
file, refuses before the environment check runs, even on a good fixture.

## Limitations

- The server may not honour `docker_image` (see above). If it doesn't, the expected result is
  a pre-launch refusal with diagnostics, not a CUDA run.
- `machine_shape` is honoured only by recent Kaggle CLI/API versions; older ones ignore it,
  and the session may then get a different GPU. Confirm the T4 accelerator in the Kaggle UI.
  The receipt's `gpu_name` records the GPU that was actually used.
- The staged `research` tree is a namespace package. If a regular package named `research`
  is installed on the Kaggle image, imports fail. That failure is closed: nonzero rc and a
  failure log.
- The launcher needs NumPy, which the qualifier imports, on the Kaggle image. Internet is off.
- The verifier proves the ordering and the refusals with an in-process sentinel and fixtures.
  The real CUDA path and the real Kaggle environment have not been exercised.
