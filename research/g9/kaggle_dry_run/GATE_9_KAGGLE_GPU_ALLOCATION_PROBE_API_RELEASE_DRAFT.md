# Gate-9 GPU allocation probe, API-launched — RELEASE DRAFT (not a run)

Status: **DRAFT, OFFLINE, AWAITING OWNER RELEASE.** Nothing here has been executed.
While writing this, no Kaggle API call, CLI push, UI action, kernel creation, version,
accelerator selection, GPU operation, credential read, or Stage-2 operation was performed,
and no Kaggle attempt was spent. Only three new files were added to this directory
(section 6); no existing protocol, outcome, core, or journal file was edited.

This draft **REPLACES**, and does not add to, the owner-run one-shot release proposed by
[the probe draft](GATE_9_KAGGLE_GPU_ALLOCATION_PROBE_DRAFT.md) (SHA-256
`13034e40a4f4ebfa5f22d364920dfe0773f03c4e5aeea9ae2f4c60c28295ac65`). If that draft is
separately approved, **only one of the two routes may run** and the combined budget stays
**one attempt in total**. Releasing this one retires the owner-run UI route; releasing the
UI route retires this one. Running both would be two attempts and is not authorized by
either document.

## 1. What changes, and what does not

The probe itself is unchanged. The code that runs is **byte-for-byte the pinned §4 probe
cell** (`b0aa74f3ff1710e9eecae40cc077c031ea39689da433672ede4fc22c29841bff`), extracted from
the pinned draft rather than retyped or copied into a second file, as §7.1 requires. It
remains **non-scientific**: no Stage-2 generator, candidate, instance, fixture, or
computation; **no compilation, assembly, linking, or execution of CUDA**; the single
permitted compiler contact is still one bounded `nvcc --version`.

These parts of the probe draft stay **in force, unchanged**: §4 (the cell and its four
statuses), §6 (the decision rule), §7.1 (source identity), and §8 (standing limits). In
particular `gpu_allocation`, `cuda_compiler`, `cuda_compiler_usable`, and
`launcher_guard_cuda_home` remain **four separate statuses**: an absent compiler is never
recorded as an absent GPU, an absent `CUDA_HOME` is never recorded as an absent compiler,
`INCONCLUSIVE` is never recorded as "no GPU", and `probe_conditions_met == true`
authorizes nothing.

These parts are **replaced** by this draft:

| Probe draft | Replaced by |
| --- | --- |
| §3 step 1: a fresh notebook created in the Kaggle UI, *not* a CLI push | one fresh **private SCRIPT kernel**, pushed once by the official Kaggle CLI (§3) |
| §3 step 5: explicitly select **Always use latest environment** before the first Save Version | **not assertable over the API.** No `docker_image` and no `docker_image_pinning_type` is sent; whatever Kaggle then applies is an observation (§2) |
| §3 steps 6-8: replace starter cells, one cell, one Save & Run All | the pushed code file **is** the probe bytes and nothing else; one push, which is one run |
| §7 items 1-2: pre-Save-Version screenshots of the accelerator, settings, and single cell | the locally built bundle bytes and their hashes, recorded **before** the push (§5) |
| §6.5/§7.1: an `.ipynb` pull is expected, `script` is the defensive branch | `script` is now the **expected** branch: the 12-byte marker rule applies as the primary path (§5) |

## 2. Honest cost of the API route

State these in the outcome record; do not paper over them.

- **The environment-pinning state is unasserted.** The API push carries no image pin and
  no pinning-type field, so the attempt is **not** a controlled observation on that axis.
  The outcome record must say the environment-pinning selection was **unasserted**; it may
  **not** be written up as "Always use latest environment" or as "pin to original".
  Whatever the pulled metadata shows is recorded as an observation with no inferred cause.
- **No pre-commit screenshots exist.** Nothing is selected on screen, so §7 items 1-2
  cannot be captured. Their evidentiary role is taken by the built bundle bytes, which are
  hashed before the push and are the exact bytes sent.
- **Push is run.** The v2 README records that the locally installed Kaggle CLI 2.2.4 does
  not offer `--no-run`. The single push therefore **starts the single session
  immediately**; there is no non-running upload to inspect first.
- **Owner verification is context only.** The owner reports completing Kaggle phone and
  identity verification. That is recorded as context for why a GPU is being requested
  again. It is **not** evidence that a GPU will be allocated, not a diagnosis of the v1/v2
  CPU allocations, and it may not later be recorded as a cause or a remedy.
- **Attribution stays impossible.** As in §2 and §3 of the probe draft, several
  differences from the spent v2 run change together, so even a GPU-visible result would
  not identify which difference mattered.

## 3. The single attempt

- **Exactly one push, which is exactly one run, producing exactly one version. No retry**,
  under any outcome: not on `FAIL`, not on `INCONCLUSIVE`, not on an inconclusive probe,
  not on a platform error, not with different settings, and not via the UI.
- **New kernel.** Slug `g9-gpu-allocation-probe-api-b0aa74f3`, distinct from both spent
  kernels (`g9-cuda-core-nonscientific-dry-run-50f25827` and
  `g9-cuda-core-nonscientific-dry-run-v2-50f25827`). Neither spent kernel is addressed,
  copied, forked, re-versioned, or edited.
- **Metadata:** private, `kernel_type: script`, `language: python`, `enable_gpu: true`,
  `machine_shape: NvidiaTeslaT4` (GPU T4 x2), `enable_internet: false`, every source list
  empty, and **no `docker_image` or `docker_image_pinning_type` key of any kind**.
- **The command, planned and NOT executed:**

  ```
  kaggle kernels push -p <staging-dir>
  ```

  It has not been run, and nothing in this repository runs it. The builder cannot: it
  imports no `subprocess`, `socket`, `urllib`, or `http` module, and the verifier checks
  that (section 6). Issuing this command is an **owner act** after an explicit written
  release.
- **Who may do what.** Building and verifying offline are safe to automate and have been done.
  The push, and therefore the run, is the owner's. Before the owner's release, and while
  the version is still running, **no automated Kaggle call of any kind is authorized** --
  read-only included. Afterwards the read-only retrieval allowed by §5 of the probe draft
  applies unchanged.

## 4. Build and verify (offline, already done)

```
PYTHONDONTWRITEBYTECODE=1 python3 research/g9/kaggle_dry_run/build_g9_gpu_allocation_probe_api_bundle.py \
    --kaggle-user <kaggle-username> --plan
PYTHONDONTWRITEBYTECODE=1 python3 research/g9/kaggle_dry_run/build_g9_gpu_allocation_probe_api_bundle.py \
    --kaggle-user <kaggle-username> --output-dir /path/outside/project/new-dir
PYTHONDONTWRITEBYTECODE=1 python3    research/g9/kaggle_dry_run/verify_g9_gpu_allocation_probe_api_bundle.py
PYTHONDONTWRITEBYTECODE=1 python3 -O research/g9/kaggle_dry_run/verify_g9_gpu_allocation_probe_api_bundle.py
```

`--plan` is pure: it prints the plan and its hashes and writes nothing, anywhere.
`--output-dir` is the only writing mode; the directory must be new or empty, must not be a
symlink, and must sit **outside** the project tree. The builder refuses unless the draft
hashes to its pinned value, the draft holds exactly one fenced `python` block, and that
block hashes to **both** pinned §7.1 values. Bundle bytes are a pure function of (draft
bytes, `--kaggle-user`); two builds are byte-identical.

Bundle contents for `--kaggle-user shivanshsrivastava06` (the metadata hash depends on the
username; the code hash does not):

| Staged file | SHA-256 |
| --- | --- |
| `g9_gpu_allocation_probe.py` | `b0aa74f3ff1710e9eecae40cc077c031ea39689da433672ede4fc22c29841bff` |
| `kernel-metadata.json` | `27a73cf9fd95dbaa72a1c5451774fdad4d2bf24ac79d909260da26b2102c08bd` |

## 5. Evidence and identity checks (if and when it is released)

Preserved additively under the `GATE_9_KAGGLE_GPU_ALLOCATION_PROBE_` prefix, each with its
SHA-256, overwriting nothing:

1. **The pushed bytes**, recorded from the build output above **before** the push. These
   are the requested-settings record that replaces §7 items 1-2.
2. **`..._OUTPUT.json`** -- the probe's printed JSON, verbatim. The §4 cell prints to
   stdout and writes no file, so for a script kernel this is **extracted from the kernel
   log**, not downloaded as a kernel output. It must reproduce `gpu_allocation`,
   `gpu_allocation_notes`, `cuda_compiler`, `cuda_compiler_usable`,
   `launcher_guard_cuda_home`, `caveats`, and `probe_conditions_met` as separate fields,
   never collapsed into one pass/fail.
3. **`..._KERNEL.log`** -- the full kernel log.
4. **`..._FAILURE.log`** -- if the version fails. When the failure is the cell's own
   fail-closed exit carrying `GATE9_PROBE_NOT_CLEAN`, it is a **valid diagnostic** under
   §6.5, not a lost attempt and not a platform failure.
5. **`..._PULLED_METADATA.json`** -- recording the observed `enable_gpu`, `machine_shape`,
   and whatever `docker_image` value Kaggle stores, **as observations with no inferred
   cause**.
6. **The §7.1 source-identity record**, computed offline: `kernel_type`, `code_file`, the
   raw pulled-source SHA-256, the extracted SHA-256, and which pinned variant matched.

   **Script prefix rule (now the expected path).** A pulled `script` source must begin
   with the exact 12-byte marker `b'# %% [code]\n'`; remove **only** that marker and
   require the SHA-256 of the remaining bytes to equal exactly one of the two pinned
   values. Both v2 pulls showed this marker, so the predicted raw pulled-source hash is
   `547d7460c7fa413502d84e6fb1e7050b0c478bcea8f527e29a3b584d14ad3b6d` -- a **prediction,
   not a guarantee**. The `.ipynb` branch of §7.1 is retained for the case where Kaggle
   returns a notebook instead. Run it with:

   ```
   PYTHONDONTWRITEBYTECODE=1 python3 research/g9/kaggle_dry_run/verify_g9_gpu_allocation_probe_api_bundle.py \
       --pulled-source /path/to/pulled/source
   ```

   On any mismatch the run is **not established** as a probe of the pinned draft: record
   the raw hash and the mismatch, draw **no** allocation, compiler, or usability
   conclusion, and do not retry under this release.

Screenshots after the push (the kernel page, the version list and its state, the session
indicator) remain welcome and are observations, not attempts.

## 6. Files added by this draft

Three files, all new, in `research/g9/kaggle_dry_run/`:

- `build_g9_gpu_allocation_probe_api_bundle.py` -- the deterministic offline builder.
- `verify_g9_gpu_allocation_probe_api_bundle.py` -- the offline verifier and its fixtures.
- this file.

The verifier runs offline with fixtures and executes nothing: it parses the probe cell with
`ast` instead of running it, and never touches Kaggle, nvcc, a GPU, or the network. It
checks the pinned draft binding with load-bearing mutations (an edited cell still refuses
even when the draft hash is re-pinned to the edited draft), the metadata invariants
including the absence of `docker_image` as bytes, slug distinctness from both spent
kernels, `--plan` purity, the `--output-dir` guards, the builder's lack of any network or
subprocess capability, the cell's bounded non-scientific shape (six stdlib imports, exactly
two bounded subprocess calls, no file writes, exactly three environment variables read, no
compilation), and the §7.1 identity rules against accepting and rejecting fixtures.

## 7. Standing limits

- **No authority is granted by this draft or by any probe outcome:** no §A qualification,
  no Stage-2 candidate, instance, generator, or fixture work, no CUDA compilation, no
  qualification receipt, no scientific computation, and no Gate-10 work.
- No claim is made, and none may later be recorded, that omitting `docker_image`, using the
  API instead of the UI, or completing phone/identity verification fixes, fixed, or would
  fix the CPU allocation.
- The v1 and v2 attempts remain spent; this route does not restore or extend them.
- This draft authorizes **zero** pushes and **zero** runs by itself. Absent a fresh written
  owner release naming this API route, the standing position is *no run*.
