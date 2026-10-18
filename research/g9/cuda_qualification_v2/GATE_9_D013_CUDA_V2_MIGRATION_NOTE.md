# GATE 9 D013 CUDA — CANDIDATE v2 MIGRATION NOTE (NOT APPROVED, NOT ROUTED)

**Status: DRAFT CANDIDATE. `owner_approved` is NOT set to `true` anywhere in this
directory. No release, runtime config, source map, bundle or launcher binding was
modified. The one-use discovery push is consumed; nothing here authorises a
re-run or a new push.**

Date: 2026-10-01. Author: Space Bunny Alpha/high (builder), offline only.
Host: Linux, g++ 13.3.0, Python 3.12.3, **no `nvcc`, no CUDA device, no
`/dev/nvidia*`**.

---

## 1. What the candidate is, and what it is not

| | |
|---|---|
| Candidate source | `research/g9/cuda_qualification_v2/stage2_cuda_d013_inactive_v2.cu` |
| Derived from | `research/g9/cuda_qualification/stage2_cuda_d013_inactive.cu` (sha256 `2d7bc8f5…023f`), which is **preserved byte-identically and unmodified** |
| Edits | 10 anchored replacements, enumerated in `candidate_edit_log.json`, diffed in `candidate_v1_to_v2.diff` |
| Net effect | `+1 cudaMalloc`, `+1 cudaMemcpy(HostToDevice)`, `+1 cudaFree`, 5 kernel-pointer substitutions. Nothing else. |
| Approval | **none.** Not owner-approved, not release-bound, not launcher-routed, not bundle-included. |

### The defect being repaired

`g9_d013_run` in the approved v1 source declared **no device payload at all** and
passed the caller's **host** `payload` pointer into all three D013 kernels
(`:684` terms, `:726` probe, `:768` energy). A device kernel cannot dereference a
host pointer.

**A second, independent instance of the same defect class was found during this
build and is also fixed.** v1 passed the **host** `energies` array into
`segment_kernel` (`:784`) and `flags_kernel` (`:828`) — the two *unchanged* v1
core kernels that consume the energy stream. The qualified v1 core passes
`device_energies` (`stream_engine.cu:733`, `:757`), and the D013 energy kernel
produces its output into `device_energies`, so that is the only correct
device-side source. The root-cause report did not enumerate this second instance.

### Deliberately NOT changed (reviewed, explicit, non-defect)

`payload->lambda_ref` at the `flags_kernel` launch is still read from the
validated **host** payload, exactly as in v1. It is a host-side **scalar** kernel
argument passed *by value*; the kernel body never dereferences it. It is not a
device-pointer defect, and it was left untouched to keep the candidate minimal
and to avoid any appearance of altering v1 numerics.

---

## 2. Evidence class — read before quoting anything

**Everything here is static analysis plus CPU host-stub execution.** The host stub
is the repo's pinned `research/g6/cuda_qualification/host_emulation_stub/cuda_runtime.h`
(sha256 `fff06b9a…a4c`), in which `cudaMalloc` is `malloc` and a "device" kernel
runs serially on the CPU.

**NOT established, and not claimed:**

- That the v1 host-pointer launch is the cause of the observed T4 `REFUSED`.
  That remains a **strong static inference**, consistent with the exclusion
  evidence in `logs/discovery.d013.rootcause.vout` (arch, image drift and OOM
  already excluded; core passed 8/8 on the same T4).
- That this candidate is correct on real hardware. **Unverified.**
- A host stub **cannot** reproduce an invalid device memory access, because on
  the host the "device" pointer and the host pointer are both ordinary
  addressable memory. Only a T4 run can settle the causal claim.

The `log` of what the fixture actually proved is in §5.

---

## 3. Every binding that needs a NEW owner-reviewed release

The candidate is bound by **none** of the following. Each entry is a place that
**currently pins the v1 `.cu` hash `2d7bc8f5…023f`** and would have to be
re-derived, re-reviewed and re-approved before the candidate could ever run. **No
item below was edited.**

### 3.1 The D013 release itself (must be superseded, not edited)

| # | Artifact | Current binding | What a new release needs |
|---|---|---|---|
| 1 | `research/g9/cuda_qualification/GATE_9_D013_CUDA_RELEASE_DRAFT.json` | `owner_approved: true`; `source_sha256[…/stage2_cuda_d013_inactive.cu] = 2d7bc8f5…023f`; 4 bound files | A **new** release document with a **new** schema id, a **new** `source_sha256` map naming the v2 `.cu`, a fresh `content_sha256`, and a fresh `owner_approved` decision. The old release must keep validating against v1 — it currently does, and the fixture asserts it (T5a). |
| 2 | `research/g9/cuda_qualification/stage2_cuda_d013_inactive_corruption_qualification.py` | `SOURCE_REL` / `SOURCE_RELS` (`:64`, `:75`) hard-code the **v1** path | A v2 plan module with a v2 `SOURCE_REL`, a re-derived `detection_table_sha256`, and — critically — the **full 9-mutation sweep re-run** against the candidate. The 9 anchors are all still present exactly once (fixture T2b), so the plan remains applicable, but it has **never been executed against v2**. |
| 3 | Verified-release token | `_token_proof(release_sha256, source_map)`, `_check_token` at `:455`, backend-1 gate at `.py:316` and `:537` | A new token bound to the new release + new source map. The existing token is derived from the old release and **must not** be reused. |

### 3.2 Runtime configuration and the accepted launcher

| # | Artifact | Current binding | What a new release needs |
|---|---|---|---|
| 4 | `research/g9/kaggle_wp7b/runtime_config.json` | `:51` source map → v1 hash; `:93` `d013_plus_zero_cuda_path` role → v1 path; `:26388` bundle closure entry; `:435` `d013_corruption_release_sha256 = e73a4ff4…0721` | Regenerated by `generate_wp7b_runtime_config.py` against the new release. Every hash, the role path and the corruption release id change. |
| 5 | `research/g9/kaggle_wp7b/wp7b_launcher.py` | `:470` compiles `src/"stage2_cuda_d013_inactive.cu"`; `:481` loads the v1 bridge; `:488–494` runs the v1 corruption qualification and mints the token | A new launcher build must point at the v2 source **and** the v2 bridge/plan. This is the **accepted** launcher and is **not** to be edited here. |
| 6 | `research/g9/kaggle_wp7b/verify_wp7b_device_backend_emulation.py` | `:35` compiles the v1 `.cu` | Re-pointed and re-run. |
| 7 | `research/g9/kaggle_wp7b/verify_wp7b_bundle_fixtures.py` | `:1155` asserts the compiled output is named `stage2_cuda_d013_inactive.cu` | Filename expectation must follow the new release's naming. |

### 3.3 Bundle, package and seal

| # | Artifact | Current binding | What a new release needs |
|---|---|---|---|
| 8 | `research/g9/kaggle_wp7b/build_wp7b_bundle.py` | `EXTRAS` pins the v1 corruption plan, the host-emulation verifier and `GATE_9_D013_CUDA_RELEASE_DRAFT.json = e73a4ff4…0721` | A new bundle: new `EXTRAS` hashes, new closure, new `BUNDLE_SHA`, new seal, new owner approval record. The existing approval record is bound to the old bundle and is **not** transferable. |
| 9 | `research/g9/kaggle_wp7/wp7_reviewed_dependencies.json` | `:9` → v1 hash | New reviewed-dependency table. This is the **reviewed** table; its hash is itself an anchor in the bundle approval. |
| 10 | `research/g9/kaggle_wp7/build_wp7_package.py` | `:144` binds the v1 `.cu` (currently `PENDING`) | Re-resolved in the new package build. |
| 11 | `research/g9/kaggle_wp7/wp7_push_manifest.draft.json` | `:55` → v1 path | New push manifest. Remains DRAFT. |
| 12 | `research/g9/kaggle_wp7/wp7_session.py` | `:182` lists the v1 `.cu` in the session file set | New session file set + new session digest. |
| 13 | `research/g9/kaggle_wp7b/seal/build_wp7b_seal.py` | `:247` lists the v1 `.cu` in the seal closure | New seal. The existing `wp7b_production_identity.json` is `status: DRAFT_UNQUALIFIED`, `authorization: NONE` and its `d013_plus_zero_cuda_path` role pins v1. |
| 14 | `research/g9/kaggle_wp7b/seal/wp7b_seal_inputs.json`, `wp7b_reference_seal.json`, `wp7b_coordinates.json` | derived from the closure above | Re-derived. |
| 15 | `research/g9/kaggle_wp7b/WP7B_BUNDLE_NOTES.md` | `:321` documents the v1 file as reviewed | Documentation updated with the new release. |

### 3.4 Diagnostic-only artifacts in this directory

`verify_d013_cuda_v2_candidate.py` and `host_stub_fault_injection/cuda_runtime.h`
are **diagnostics**, not release artifacts. They are deliberately **excluded**
from every release, source map, bundle and runtime config, and must never be
added to a bundle. The fault-injection stub in particular must never be on the
include path of a real `nvcc` build.

---

## 4. What T4 qualification would be required

The candidate is **unqualified**. Before it could be relied on, all of the
following must run on a real Tesla T4 (compute capability 7.5, CUDA 12.8.93,
the pinned Kaggle image), and each must be re-recorded:

1. **Real `nvcc` compile** of the v2 source with the reviewed flags
   (`-std=c++17 -O0 --fmad=false --ftz=false --prec-div=true --prec-sqrt=true
   -Xcompiler -O0,-ffp-contract=off,-fno-fast-math,-fPIC -shared`).
2. **The clean case must return `G9_D013_OK` (1), not `REFUSED` (0)**, for
   condition `C` with the non-commuting builder — the exact case that failed the
   consumed discovery push. This is the single most important datum.
3. **All four conditions** (`C`, `CB`, `CS`, `CSB`) complete, with
   `reference_agrees_with_result` true against the independent reference.
4. **The full 9-mutation corruption sweep**, re-run against the v2 source, each
   mutation still detected and refused. The candidate changes launch pointers;
   a reviewer must confirm no mutation's detection semantics shifted.
5. **Negative control on real hardware**: re-confirm that the *v1* source, built
   for the T4, still fails — i.e. that the device-pointer fix is load-bearing
   rather than cosmetic.
6. **Fault-path behaviour on device** for real `cudaMalloc` / `cudaMemcpy` /
   launch failures. The CPU fault-injection evidence is not a substitute.
7. **Per-stage `cudaGetLastError()` / `cudaDeviceSynchronize()` capture.** The
   root-cause report could not identify the failing launch because the harness
   discards CUDA status exactly as it discarded `str(exc)`. Capturing it is what
   converts the current inference into evidence, and it should be part of the new
   release rather than a later patch.
8. **Memory accounting.** The candidate adds one `sizeof(PayloadData)`
   allocation. D013 previously needed 198.24 MiB of 16384 MiB; this is
   immaterial, but a real `cudaMemGetInfo` reading should be recorded.
9. **Independent, different-family review** of the new source, the new release
   and the new receipts, exactly as the current draft received.
10. **A fresh owner decision.** The current `owner_approved: true` belongs to
    the v1 release and confers nothing on v2.

The consumed one-use discovery push confers **no authority** to run any of this.
A new authorisation is required.

---

## 5. What the offline fixture actually proved

See `verify_d013_cuda_v2_candidate.py` (docstring carries the full list). The run
reported here completed **14/14 checks**, exit code 0:

| Check | Result | Measured |
|---|---|---|
| T1 v1 negative control | PASS | v1 rejected on all 5 launches, plus no declaration/alloc/copy/free |
| T2 candidate pointer staging | PASS | declaration, alloc, HostToDevice copy, 3 D013 device pointers, 2 core device-energy pointers, free |
| T2b 18 static guard/ABI invariants | PASS | every guard/refusal/counter/status count **identical to v1**; 9 mutation anchors still unique |
| T2c minimality | PASS | exactly `+1 cudaMalloc`, `+1 cudaFree` |
| T2d clean host-stub builds | PASS | v1 `bbcf6183…`, v2 `5504bce8…`, zero warnings |
| T3 upstream v1 verifier | PASS | repo's own reference-agreement + mutation-rejection complete (rc=0) |
| T4a fault-stub build | PASS | zero warnings |
| T4b clean run, nothing armed | PASS | `status=1 (OK)`, 24 launches, 25 allocs, 25 frees |
| T4c allocation fault | PASS | `status=0 (REFUSED)`, scrubbed, **0 launches**, 1 alloc attempt, bridge raises typed refusal |
| T4d payload-staging copy fault | PASS | `status=0 (REFUSED)`, scrubbed, **0 launches**, 13 allocs / 25 frees (all released) |
| T4e launch fault | PASS | `status=0 (REFUSED)`, scrubbed, fault landed mid-run at launch 2 |
| T5a v1 release still valid | PASS | all 4 bound hashes unchanged |
| T5b no config/launcher binding | PASS | neither mentions `cuda_qualification_v2` |
| T5c pinned stub unmodified | PASS | `fff06b9a…a4c` |

T4c and T4d are the two most load-bearing rows: the injected fault lands
**before any kernel runs**, so the candidate cannot execute a kernel on
unstaged payload memory, and it still refuses and releases every allocation.

None of T1–T5 is evidence about real CUDA hardware. See §2.

---

## 6. Reproduction

```
cd <project>
PYTHONDONTWRITEBYTECODE=1 python3 -B \
    research/g9/cuda_qualification_v2/verify_d013_cuda_v2_candidate.py
```

Requires only `g++` and the repo's pinned host stub. No network, no CUDA, no
credentials, no production input, no scientific computation.

---

## 7. Hash manifest

### 7.1 Output files created (all new, all under `research/g9/cuda_qualification_v2/`)

| File | SHA-256 |
|---|---|
| `stage2_cuda_d013_inactive_v2.cu` | `953b7f15a14950d75536d72b074a7907dc06df13539b2ce3f4122cc427ab0f61` |
| `verify_d013_cuda_v2_candidate.py` | `e285f0e55e7ea9b2fc78473c0eacefb2052a8aa6199eb51c2f6a82b97e36e54e` |
| `host_stub_fault_injection/cuda_runtime.h` | `8b2cf3b09c5cc8243854ae6cec65e82d39734251ccfd23445eba11d7c2261913` |
| `candidate_edit_log.json` | `7e906c93b82cca70e9b4f1c91b889c9b7340dd03bb25b67eec8ec0aec153e146` |
| `candidate_v1_to_v2.diff` | `2ae61cd0de06fbcc544e5d23a9cf0cd7975f42c6ed980f73d5fa38e88c8ace6b` |
| `GATE_9_D013_CUDA_V2_MIGRATION_NOTE.md` | this file (self-referential; verify by re-hash) |

### 7.2 Source inputs — read-only, verified unchanged before and after

These match `logs/discovery.d013.rootcause.vout` exactly, so this build was
performed against the same bytes that were diagnosed.

| File | SHA-256 |
|---|---|
| `research/g9/cuda_qualification/stage2_cuda_d013_inactive.cu` | `2d7bc8f559ced574283b8b4430ab6326058ae351dc5dde89386934910a3d023f` |
| `research/g9/cuda_qualification/stage2_cuda_d013_inactive.py` | `06b02b2ba800f0c888eb1eb9d9d9a727c0f72d6a11871deeece6e0cf342f74c4` |
| `research/g9/cuda_qualification/stage2_cuda_d013_inactive_corruption_qualification.py` | `ab0c906017fa7555ee5a00f8ba02cc15e8a467f046008d427be018c318382c5c` |
| `research/g9/cuda_qualification/GATE_9_D013_CUDA_RELEASE_DRAFT.json` | `e73a4ff4a38cb6b0cfbc35713b7ce727c6cb8b94b2c38310277a1dac372b0721` |
| `research/g9/verify_stage2_cuda_d013_inactive_host_emulation.py` | `b223206b9490fb7fe8ac12b829291a73d7ffbb1663b5cdab939bf9db4da98f4a` |
| `research/g9/cuda_qualification/stage2_cuda_core_stream_engine.cu` | `fce00217f8530a695d676a774e4f741a83dec2aa7066c8f8a85ce136eac37d14` |
| `research/g6/cuda_qualification/host_emulation_stub/cuda_runtime.h` | `fff06b9ad69b447b17f1ed31084febd59c988cb5c583e3857a627c6622f96a4c` |

### 7.3 Scope check

- **All 61 protected baseline paths** in
  `g9_jobs/lead_takeover_protected_baseline_20261001.json`: **61/61 unchanged**,
  0 changed, 0 missing.
- Files modified or created in this copy: **6, all new, all under
  `research/g9/cuda_qualification_v2/`**. No existing file was edited.
- The approved v1 `.cu`, the v1 bridge, the v1 corruption plan, the v1 release
  draft, all `kaggle_wp7b` files and all `kaggle_wp7` files are **unmodified**.
- **`.pyc` files in the project: 0. `__pycache__` directories: 0.** Every
  Python invocation used `PYTHONDONTWRITEBYTECODE=1 python3 -B`.
- No file was deleted. Temporary build artifacts were confined to
  `g9_jobs/scratch/sbbuild.mONHRkHI` and to Python `TemporaryDirectory` blocks.
