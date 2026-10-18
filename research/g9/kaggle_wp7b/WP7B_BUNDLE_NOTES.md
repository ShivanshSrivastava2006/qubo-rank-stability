# WP7b Integration Build Notes

## Round 6 — Kaggle kernel process isolation

The generated armed entry now treats the API-pushed notebook kernel as an
outer verifier and supervisor. It checks its self hash, decodes and validates
the complete archive, validates the owner approval, consumes the one-use nonce,
and stages the payload under a fresh mode-0700 directory. It imports neither
`wp7_session` nor `wp7b_launcher`, sets no armed permission variables, and
runs no WP7 step. It writes a hash-pinned canonical staging index, then starts
the embedded `wp7b_child_entry.py` as
`[sys.executable, "-I", "-S", "-B", ...]`. Its 36,300 second timeout exceeds
the 36,000 second WP7 budget guard and remains below Kaggle's 36,600 second
kernel timeout. It relays the child's exit code and writes a typed difference
record only when the child fails without writing a receipt.

The child first checks the staged-index SHA-256 and every staged file SHA-256.
It does not import from the stage before those checks pass. It then validates
and explicitly adds existing absolute site-package paths. `-S` keeps Python
from loading `.pth` hooks and `sitecustomize.py`; the parent test deliberately
loads a `sitecustomize.py` that imports `socket` to confirm it stays parent-only.
Before loading the session or launcher, the child rejects any forbidden module
already in `sys.modules` and any `KAGGLE_*` environment name. Only then does
the production armed path set the two permission variables and run the same
probes, adapters, session, outer receipt, and budget receipt path.

The child environment is built from this allowlist. No `KAGGLE_*` or `PYTHON*`
name can pass through; excluded names are filtered before looking up any
values, so Kaggle token values are never read. `PYTHONDONTWRITEBYTECODE=1`
is added explicitly.

| Name or prefix | Reason it reaches the isolated child |
|---|---|
| `PATH` | Finds `nvcc` and the compiler/toolchain executables used by the launcher probes and CUDA build. |
| `LD_LIBRARY_PATH` | Lets `nvcc` and compiled CUDA probes resolve CUDA runtime/driver libraries. |
| `CUDA_HOME`, `CUDA_VERSION` | Read by `build_probes` for the pinned image identity. |
| `CUDA_VISIBLE_DEVICES`, `CUDA_DEVICE_ORDER` | Preserve CUDA device visibility and device enumeration for the launcher's device-0 runtime probe. |
| `BUILD_DATE`, `COLAB_IMAGE_TYPE`, `GIT_COMMIT` | Read by `build_probes` for the pinned image build identity. |
| `HOME`, `LANG`, `LC_*`, `TMPDIR` | Standard toolchain/runtime home, locale, and scratch directory inputs; `TMPDIR` is used by temporary compiler probes. |
| `NVIDIA_*` | CUDA image/runtime configuration passed by the platform; retained for CUDA driver and compiler execution. |
| `PYTHONDONTWRITEBYTECODE=1` | Prevents bytecode writes in the child and its fixture worker. |
| `WP7B_TEST_*` (fixture mode only) | Narrow rehearsal controls for probe emulation and negative tests; the ordinary armed bundle hardcodes fixture mode off. |

The Kaggle-realistic rehearsal now runs the generated armed entry both by
`exec` of its source and as `python script.py` under a parent with an imported
socket, fake Kaggle environment names, and the socket-importing site hook. It
also checks staged tampering, injected child `KAGGLE_*`, child timeout/kill,
and a missing site-package path. These controls are fixture-only and are not
reachable from an ordinary armed script. `wp7b_launcher.py`,
`wp7b_identity_binding.py`, `runtime_config.json`, its generator, and the seal
artifacts remain byte-identical to their pinned copies.

### Isolation bundle identity and audit artifacts

Two fresh production draft builds into the same scratch output directory were
byte-identical across the script, kernel metadata, and complete manifest:

- Bundle SHA-256: `853c13a92c28a4b7d4c4710d3641450cb49e02e0a3ffb4b277177c2076746ce6`.
- Kernel: `shivanshsrivastava06/g9-wp7-nonscientific-dry-run-853c13a9`.
- Script: 564,784 bytes, 83 blobs; SHA-256 `44fce263a17898b98fca8fd78a3b1fab119d95acddefd531a3a3199fdab70a6b`.
- Drafts remain intentionally non-runnable. The manifest's suggested push
  command now uses `-t 36600`, accommodating the isolated child's timeout.

`verify_wp7b_child_fixtures.py` adds direct staged-index/type/path/link checks,
site-directory validation, forbidden-import checks, atomic output durability
and cleanup checks, isolated fake-runtime receipts and refusals, and generated
supervisor signal/exit/timeout/missing-receipt checks. The full bundle fixture
calls these checks before its existing full CPU emulation. The rehearsal
compares two ordinary armed test records and permits differences only in
`APPROVAL_FIELDS`, `APPROVAL_SHA`, `ARCHIVE_CHUNKS`, `ARCHIVE_SHA`,
`EXPECTED_INDEX`, `SELF_SHA`, and the approval-dependent `STAGE_INDEX_SHA`.

Validation artifacts are `logs/wpiso.fixture.*.txt` and
`logs/wpiso.determinism.json`; the armed approval-only comparison is
`logs/wpiso.armed-diff.json`. The unchanged seal fixture is executed from its
source with only its hardcoded scratch directory redirected in memory to
`g9_jobs/scratch/wp7biso/seal`; the committed seal fixture remains identical.
Scope, file hashes and line counts are recorded in `logs/wpiso.scope.json`.
The live comparison root acquired a later owner-decision amendment after this
copy was made; that pre-existing decision-document difference is recorded
separately and is not a WP7b-ISO edit.

All eight fixture groups passed under both `-B` and `-B -O`: full bundle,
Kaggle-realistic armed rehearsal, child/supervisor, focused builder, focused
launcher, device backend, full seal, and small-domain seal. The full seal
covered 328 checks at 1,048,576 states; the small mode covered 373 checks while
checking the committed full-domain artifact digests. The device backend
covered 50 comparisons and detected the injected minimum, entry-flag, and
copied-offset corruptions. `logs/wpiso.validation.json` records each mode's
final log hash. The final `-B` rehearsal used a separate scratch subdirectory
to avoid collisions with the optimized rehearsal; its source differed only
in that scratch path.

The final gates use shared tool v1.1, the full bundle fixture, 12 workers,
nice 10, and `--chunk-seconds 36000`, sequentially for the builder and child.
Logs: `logs/wpiso.sweep.builder.txt`, `logs/wpiso.sweep.child.txt`;
results: `logs/wpiso.sweep.builder.json`, `logs/wpiso.sweep.child.json`;
semantic-only equivalent justifications: `logs/wpiso.equivalents.json`.
The launcher's existing 291-site gate remains applicable because its bytes
are unchanged.

## Round 5 — XZ transport envelope

The bundle now carries one deterministic archive instead of per-file base64
payloads. A canonical JSON index records each name, raw SHA-256, byte offset,
and byte length, followed by the concatenated raw blobs. The raw reference seal
is part of that byte stream. The complete container is compressed as XZ with
`CHECK_SHA256` and preset `9 | PRESET_EXTREME`, then embedded as base85 with a
pinned compressed-archive SHA-256.

The generated entry point checks its own source hash first, then the archive
digest, bounded XZ expansion (400,000,000 bytes), canonical index, exact name
set, contiguous ranges, each blob digest, and the raw seal digest before it
opens the approval record or stages files. Transport failures raise the
generated `TransportError`. The builder refuses scripts at or above 950,000
bytes; its test-only size helper accepts an injected limit while normal builds
use the fixed constant.

`bundle_sha256` retains the canonical SHA-256 over sorted `[name, digest]`
pairs, excluding the approval record. The seal entry now uses the raw seal
digest rather than the former zlib digest, so the bundle hash and derived
kernel id change while the payload bytes and all semantic checks stay fixed.
Two production draft builds were byte-identical: bundle SHA-256
`336bbb62d24a981e39548e0485bba485ba95df2463e91af175a6c0a391659ecc`, kernel
`shivanshsrivastava06/g9-wp7-nonscientific-dry-run-336bbb62`, 561,579 script
bytes, and 82 blobs. Two armed builds with distinct test approval records
produced script differences only in `APPROVAL_FIELDS`, `APPROVAL_SHA`,
`ARCHIVE_CHUNKS`, `ARCHIVE_SHA`, `EXPECTED_INDEX`, and `SELF_SHA`.

The full bundle fixture passed under `-B` and `-B -O`, including explicit
archive, index, range, trailing-data, decompression-cap, blob-digest, raw-seal,
and 950,000-byte builder-cap tamper/refusal checks. The armed-chain rehearsal
passed under both modes and reached the outer
`pending_image_metadata_audit` receipt from a fresh test-approved bundle. The
device backend, builder and launcher sweep fixtures, and full seal fixture
also passed in both modes; the full seal fixture covered 328 checks over
1,048,576 states, and the small-domain seal fixture covered 373 checks. The
final builder mutation sweep used v1.1, 12 workers, nice 10, and
`--chunk-seconds 36000` with the full bundle fixture: 154/154 sites were
killed, with no timeouts, survivors, errors, stale sites, or semantic
equivalents. Its log is `logs/wpxz.sweep.builder.txt`, results are
`logs/wpxz.sweep.results.json`, and the semantic-only equivalents file is
`logs/wpxz.equivalents.json` (empty). The sweep ended `SWEEP: PASS`.

## Round 4 — identity re-bind and armed-chain rehearsal

The re-bound production identity is tied to the hash-checked owner pin, not the
offline builder host. `wp7b_identity_binding.build_identity_mapping` is the one
mapping function called by both `build_wp7b_seal.py` and the session launcher.
The launcher constructs the identity from fresh probes and uses the pin only for
values the session cannot observe. The accepted pin was independently observed
in the owner-approved T4 smoke receipt from 2026-09-29 22:05.

| identity field | session source | audit treatment |
|---|---|---|
| `platform.gpu_name` | CUDA device probe | observed, compared to pin before work |
| `platform.compute_capability` | CUDA device probe | observed, compared to pin before work |
| `platform.cuda_driver_version` | CUDA driver probe | observed, compared to pin before work |
| `platform.cuda_runtime_version` | CUDA runtime probe | observed, compared to pin before work |
| `platform.nvcc_version` | `nvcc --version` probe | observed, compared to pin before work |
| `platform.python_version` | Python runtime probe | observed, compared to pin before work |
| `platform.numpy_version` | NumPy runtime probe | observed, compared to pin before work |
| `image_build.runtime_build_observed_platform_reported` | `BUILD_DATE`, `COLAB_IMAGE_TYPE`, `CUDA_VERSION`, `GIT_COMMIT`, `CUDA_HOME`, `nvcc_path` probes | six observed values composed and compared to pin before work |
| `platform.kaggle_image` | pin constant | post-run metadata audit |
| `image_build.kaggle_docker_image_platform_reported` | pin constant | post-run metadata audit |
| `image_build.kaggle_image_manifest_digest_platform_reported` | pin constant | post-run metadata audit |
| `image_build.kaggle_image_config_digest_platform_reported` | pin constant | post-run metadata audit |
| `image_build.kaggle_saved_version_build_platform_reported` | fixed declared `[platform_reported]` string; no pre-run observation exists | post-run audit; listed in outer receipt |
| `image_build.kaggle_kernel_version_platform_reported` | fixed declared `[platform_reported]` string; no pre-run observation exists | post-run audit; listed in outer receipt |
| `image_build.kaggle_environment_pinning_platform_reported` | fixed declared `[platform_reported]` string | pin request is separately checked; recorded as request assertion |

The re-bind changed the identity-bound artifacts as follows; the scientific
instance, preparation, coordinates, and all 160 unit results stayed unchanged.

| artifact | old round-3 SHA-256 | re-bound SHA-256 |
|---|---|---|
| production identity file | `33a76780e54e240d47ac59814d0bacf4c71bfeb72c38f4213c447c5e1a45698c` | `fe8b814d03a8bafe9ce787303dcd5bb0bc75502e5af1d12e0e5c4c174797a7c2` |
| identity content hash | `a1aa3e788e7bdcd5577cf3fe6fca7d9e4db9728d99dec663c0a1d82371b49e87` | `bba613a2754fdd929bb659d381730e897a012f962a94c0d889fb6fd3f5bc2077` |
| seal inputs | `fdc7049d0a9cd5ec2b2950690b863e17edcc8f3482101ae09f9c532945d267ac` | `40be683c6d052aee1bef6f9b447a82425e6444742c60e320008413bb0becc573` |
| raw reference seal | `e4cd3daf633b7c894e3a1720236c516fb69eda0ba009d89a5ad517afc89e6099` | `220eae886fec6fecb594c7c9dcf7df2b6458b7846b90f6ce298c959f0cb69a5b` |
| zlib-9 reference seal | `3840a644739aba3638188effbb319ce81b4561269f80f37e2a2d4b29ded6e393` | `dd02b10a2445a2d4080fede49829d72cfd886d2ef05d389906ae520f643b2307` |

The pin and post-run handling follow the owner's “Post-run audit, v1-style”
choice. The identity draft explicitly says the in-session image variable is a
platform assertion and does not prove the executing OCI manifest (§1); the
four image values are checked against pulled metadata after the run (§3). A
post-run mismatch voids the run. The saved-version build and kernel version
have no pre-run value, so their explicit fixed strings remain marked
`[platform_reported]` and are listed in the receipt for audit.

The generated runtime config SHA-256 is
`542182a3b7bcb69250d96cdcb01671ae0656327aa7a525deeb625b41a946db97`
(content SHA-256
`f2d133d8e6f4d624150345be30aedc3d679f1fda04d4c49ea4318a796ed21bac`). It
contains fixed expected hashes for the three WP2 governing documents, the
prepared-record provenance hash, the WP3 protocol digest, and the generated
identity-only WP4b range plan. WP2 passed all six real recheck elements, and a
direct WP4b adapter rehearsal sealed its plan and wrote its synthetic range.

The generated armed main passed end-to-end in the host rehearsal. It exact-
matched WP1/WP2, ran the 12 base plus four D013 repeat rows through the real
WP3 harness with all 160 comparisons matching the re-bound seal, wrote one
identity-only WP4b range, and produced the outer
`pending_image_metadata_audit` receipt. The negative driver-probe case refused
before writes with a typed difference receipt; the injected-clock budget guard
also refused at the expected last completed step. Fixture mode runs the WP3
host-emulation worker in a clean child process; the ordinary armed payload
hardcodes `FIXTURE_MODE=False` and retains the production inline backend path.

Re-bound seal identity SHA-256: `bba613a2754fdd929bb659d381730e897a012f962a94c0d889fb6fd3f5bc2077`.
Raw seal SHA-256: `220eae886fec6fecb594c7c9dcf7df2b6458b7846b90f6ce298c959f0cb69a5b`.
Compressed zlib-9 SHA-256/bytes: `dd02b10a2445a2d4080fede49829d72cfd886d2ef05d389906ae520f643b2307` / `351155`.

## Round 3 changes

- `generate_wp7b_runtime_config.py` now derives `role_paths`, the WP1 field-source table, `IMAGE_BUILD`, `COMPILER_FLAGS`, and the accepted production identity from the seal builder's literal declarations and `wp7b_production_identity.json`. It verifies the generated role set and identity hash against the seal inputs before writing config.
- Field sources in the generated config: the eight numerical platform fields except `kaggle_image` are read from `build_probes` at runtime; `kaggle_image` is the post-run-only field fixed by the sealed identity. `role_paths` comes from `build_wp7b_seal.ROLE_FILES` plus the accepted v1 release source set; `image_build` and `compiler_flags` come from `IMAGE_BUILD` and `COMPILER_FLAGS`; `accepted_identity` comes from the sealed identity artifact. These are seal-fixed values, not runtime observations.
- The launcher now resolves probe-backed WP1 values from its runtime probe callables. The cache crossover was caused by the per-encoding reconstruction loop overwriting the caller's `encoding` local; the loop now uses `stream_encoding` (`wp7b_launcher.py:383-387`). The offline fixture passed under `-B` and `-B -O`: one backend compared primary plus C, CB, CS and CSB repeat rows, all five comparator pairs and both encodings in harness call order (50 comparisons against the opened seal). Minimum, compacted-flag and copied-offset corruption were detected (`verify_wp7b_device_backend_emulation.py`).
- The round-3 offline-host identity blocker was resolved by the owner-directed seal re-bind below. The accepted identity now uses the hash-checked environment pin, and a session-built identity exact-matches it.

## Host-derived WP3 fields

- Device ABI supplies minimum values, canonical minimum indices, and compacted entries. The backend builds the harness tie-flag prefix from those entries (`wp7b_launcher.py:389-397`).
- D015/D016 reconstruction uses frozen `stage2_cuda_reconstruct.reconstruct_pair` or `reconstruct_stream`, `SlackIndexMap`, `DecodedClassifier`, and `OriginalObjectiveService` (`wp7b_launcher.py:207-263, 373-390`). The seal projection is `c_h <- c_H`, `c_f <- c_f`, `set_label <- set_label`, `tie_count <- T_E_size`, `x_e_size <- X_E_size` (`wp7b_launcher.py:291-302`).
- D013 C/CB/CS slack offsets come from frozen structural residual/lift rules in `src/g5/domains.py::_register_minimizers`, with no energy evaluation. The generated base total must equal device `lift_total_base`; CSB host offsets are compared byte-for-byte and by SHA-256 against checked core device offsets (`wp7b_launcher.py:207-238, 330-363`).

## Open items

- The four post-run-only image values remain pending metadata audit. This offline build performs no Kaggle push, GPU allocation, or run.
- The four post-run-only image fields remain pending metadata audit. No network, Kaggle, credentials, or GPU were used for this offline work.
- The full bundle fixture passes under both `PYTHONDONTWRITEBYTECODE=1 python3 -B` and `python3 -B -O`; each reports the draft refuses and 82 embedded blobs. Both fixture runs used `TMPDIR=/home/shivansh-srivastava/decisions_os/g9_jobs/scratch/wp7bint/tmp`.
- The builder and launcher sweep fixtures pass under both `-B` and `-B -O`.
- The full fixture passes with the final launcher fixture changes under `-B` (full-fixture mutation proof baseline) and `-B -O` (`scratch/wp7bint/r3.full-final-opt.log`). The targeted launcher fixture directly exercises valid probe-backed and seal-fixed WP1 sources, malformed probe maps, unsupported source kinds, missing probe observations, and invalid resolved values; it passes under both modes.
- The full fixture now checks relative-import closure discovery for payload package files that are not seed dependencies. Dead draft placeholder rewriting and the redundant username format check were removed; the builder accepts only the exact pinned account, which itself has valid syntax.
- The final builder sweep used the full bundle fixture and killed all 138 sites. The launcher focused sweep killed all 281 sites; it had no survivors, and a seed `20260930` random sample of 20 killed sites was re-run against the full fixture and all 20 were killed. No equivalent is claimed. Reports: `/home/shivansh-srivastava/decisions_os/g9_jobs/logs/wp7bint.r3.sweep.builder.txt`, `wp7bint.r3.sweep.launcher.txt`, and `wp7bint.r3.launcher.fullproof.txt`; `wp7bint.r3.equivalents.json` is empty.
- Two clean repeated draft builds in `/home/shivansh-srivastava/decisions_os/g9_jobs/scratch/wp7bint/r3-final-same-dir` were byte-identical. Bundle SHA-256 `8965a4b0ef34822a03532c6b802d904d8184f110db1ef6a5250545810471e87f`; kernel id `shivanshsrivastava06/g9-wp7-nonscientific-dry-run-8965a4b0`; script size 3,848,306 bytes; blob count 76. Manifest: `/home/shivansh-srivastava/decisions_os/g9_jobs/scratch/wp7bint/r3-final-same-dir/wp7b_bundle_manifest.json`.

## Final Round 4 verification

- Two repeated final draft builds in `/home/shivansh-srivastava/decisions_os/g9_jobs/scratch/wp7bint/draft-final-rebuild` were byte-identical: bundle SHA-256 `d3fd5617f2db5d4f2f280dc520cd363b746161520db3c85274e1e8d4adb0c306`, kernel id `shivanshsrivastava06/g9-wp7-nonscientific-dry-run-d3fd5617`, script size 4,039,464 bytes, 82 blobs.
- The runtime closure now pins and embeds `research/g9/stage2_beacon_nonce.py` (`d855129fb6096d6939203b7f55cb707b0f9a06b2870204e6aaddc57ba6840426`), required by the real WP4b writer's flat sibling import.
- The armed rehearsal, full bundle fixture, launcher fixture and shared-backend D013 fixture passed under `-B` and `-B -O`. The seal full and small fixtures also passed in both modes; small mode reports 373 checks.

## Round 7 — platform-probe source repair (dry run 853c13a9)

The dry run on a real Kaggle T4 ran the isolated child cleanly and then refused
at the environment comparison: `gpu_name`, `compute_capability`,
`cuda_driver_version` and `cuda_runtime_version` were all `None`.

Root cause. `wp7b_launcher.py::build_probes` carried its own copy of the
platform-probe CUDA source inside a Python raw triple-quoted string. The
`printf` line was written with `\\"` sequences, so the literal that reached the
compiler contained `\"` where the C source needs a plain `"`. The result was a
stray-backslash string-literal error; `nvcc` failed, `build_probes` returned
the untouched `None` placeholder values, and the fail-closed pin comparison
refused. The same probe text is already pinned, reviewed and proven on the T4
in `research/g9/cuda_qualification/stage2_cuda_core_qualification.py` as
`PLATFORM_PROBE`; the launcher now loads that one text rather than owning a
second copy.

- `wp7b_launcher.py:118-121` — `_platform_probe_source()` resolves the pinned
  qualification module by absolute path (`Path(__file__).resolve().parents[3]`)
  and returns its `PLATFORM_PROBE` through the same hash-checked staged-module
  loader `_load()` the launcher already uses for every other pinned module.
  The child re-hashes the staged file against the archive index before any
  import, so the probe text is covered by the same reviewed-hash check as the
  rest of the closure. The text is never re-typed and never re-escaped.
- `wp7b_launcher.py:142` — `build_probes` compiles that text with the
  unchanged `FLAGS` and the unchanged temporary-directory layout. No other
  behaviour changed: a missing `nvcc`, an unrecognised version banner, a
  malformed probe payload and a failed run all still leave the observed values
  `None`, and the session's exact pin comparison still refuses closed.
- `wp7b_launcher.py:158-160` — NEW. A compile failure and a run failure now
  print a diagnostic to stderr carrying the return code and the last 2,000
  characters of compiler/runtime stderr. Previously both failures were silent,
  which is why 853c13a9 could not show its own cause from the Kaggle log. The
  diagnostic is diagnostic only: it does not change the refusal, and it prints
  before the comparison runs.

## Mandatory offline native-source gate

`verify_wp7b_embedded_source_syntax.py` is a new fixture and is now run by the
full bundle fixture, so it is part of the mandatory gate rather than an
optional check.

- It asserts exact string equality between what the launcher would compile and
  the pinned `PLATFORM_PROBE`. A re-typed or re-escaped copy cannot pass.
- It discovers every C/C++/CUDA literal in the launcher, the child entry, the
  builder, the builder's generated script template, the whole
  `kaggle_wp7b` package and, with `--generated-script`, an actual built bundle
  script. Detection is marker-based (`#include`, `__global__`, `__device__`,
  `cudaError_t`, `cudaDeviceProp`, `cudaSuccess`, `int main(`, `extern "C"`,
  `std::printf`), so a native source that omits `#include` is still caught.
- Each discovered literal is compiled with
  `g++ -std=c++17 -fsyntax-only` against a minimal stub `cuda_runtime.h` that
  declares only `cudaError_t`, `cudaSuccess`, `cudaDeviceProp` and the four
  runtime entry points the probe calls. No CUDA toolkit is required.
- The gate carries a deliberate broken-escape control: it mutates one `\"` in
  the pinned text into `\\"` and requires the compiler to reject it. Running the
  fixture with `--inject-broken-escape` reproduces the exact 853c13a9 defect
  and fails the fixture, which is how the gate is proven to bite.

## Package-wide embedded-source audit

The whole `kaggle_wp7b` package and the generated script were searched for
raw triple-quoted strings and native-source literals. Findings:

- `wp7b_launcher.py` was the only raw-string native-source carrier, and it is
  the one repaired here. The launcher holds no other C/C++/CUDA literal.
- `wp7b_child_entry.py` and `build_wp7b_bundle.py` hold no native source. The
  builder's only large embedded literal is its own generated Python template,
  which is ordinary (non-raw) triple-quoted text; it contains no backslash
  escapes that would be reinterpreted, and it is now covered by the gate.
- The remaining embedded literals are fixture-side and were verified benign:
  the rehearsal's fake `nvcc` shell script (`verify_wp7b_armed_rehearsal.py`,
  a row list joined by newlines, not a raw string), the child fixtures'
  fake adapter and session modules (`verify_wp7b_child_fixtures.py`, plain
  triple-quoted Python with no backslashes), and the stub header in this gate.
- The `.cu` sources the launcher compiles at runtime
  (`stage2_cuda_core_stream_engine.cu`, `stage2_cuda_core_bridge.cu`,
  `stage2_cuda_d013_inactive.cu`) are separate reviewed files in the closure,
  never embedded as Python literals, so no escaping can affect them.

## Round 7 verification

- The diagnostic print added in Round 7 is covered, not merely present. The
  launcher fixture now captures stderr across a failing probe compile and a
  failing probe run and requires the diagnostic name, the return code and the
  compiler/runtime stderr tail to appear, while the observed GPU values must
  still be `None`. Replacing both `print(...)` statements with `pass` in a
  throwaway copy makes the fixture fail with
  `failed probe compile printed no diagnostic`.
- Two repeated draft builds into the same output directory are byte-identical
  across script, kernel metadata and manifest: script SHA-256
  `18a0862420938c764ded989ad37896d6fc1713ddb6a6b021ae1eccca4f32b09a`,
  `6e1eb2e7c7e48a91c2fdcf3c49fe174c8c451dc3b84a74b4155b3c4291f1ff3e`,
  `d6e4edca9e413ea8fa08037c3f8735de9a66a3e9681daa8c991a997e653a9805`.
  Bundle SHA-256
  `04cd89f698f36b6b103cf8c0b726ea6345b2a0e48bc23fb0e1640111476c537f`;
  kernel id `shivanshsrivastava06/g9-wp7-nonscientific-dry-run-04cd89f6`;
  script size 564,587 bytes (limit 950,000); blob count 83. Building into two
  *different* directories produces the same script and metadata; only the
  recorded `push_command` path differs, which is the output directory argument
  echoed back, not bundle content.
- Two independent armed builds whose approval records differ only in `nonce`
  and `expiry` were compared. Decoded through the generated `decode_archive`,
  every non-approval blob is byte-identical, `BUNDLE_SHA` is identical, and
  `APPROVAL_FIELDS` differs in exactly `nonce` and `expiry`. Applying the
  fixture's own `normalize_approval_regions` mask (the seven assignments
  `ARCHIVE_CHUNKS`, `ARCHIVE_SHA`, `EXPECTED_INDEX`, `APPROVAL_SHA`,
  `APPROVAL_FIELDS`, `STAGE_INDEX_SHA`, `SELF_SHA`) makes the two scripts
  identical, so the approval swap touches only the approval regions.

### Fixture results (Round 7)

All fixtures run with `PYTHONDONTWRITEBYTECODE=1` under both `python3 -B` and
`python3 -B -O`; every run exited 0.

| Fixture | `-B` | `-B -O` |
| --- | --- | --- |
| `verify_wp7b_bundle_fixtures.py` (full, now includes the native-source gate) | PASS | PASS |
| `verify_wp7b_armed_rehearsal.py` (Kaggle-simulated armed rehearsal) | PASS | PASS |
| `verify_wp7b_embedded_source_syntax.py` | PASS | PASS |
| `verify_wp7b_launcher_sweep_fixture.py` | PASS | PASS |
| `verify_wp7b_builder_sweep_fixture.py` | PASS | PASS |
| `verify_wp7b_child_fixtures.py` | PASS | PASS |
| `verify_wp7b_device_backend_emulation.py` | PASS | PASS |
| `seal/verify_wp7b_seal_fixtures.py` (full) | PASS | PASS |
| `seal/verify_wp7b_seal_fixtures.py` (small) | PASS | PASS |

The `-B` and `-B -O` rehearsal logs are byte-identical
(`6191808de61c396ae1af1e137578a10f4d951f22d8b08206df5bb591e5ee35f7`), as are
the two full-bundle-fixture receipts, both reporting bundle SHA-256
`1d8155f7cd43f373c31c7ac51c14429cb4ae96cf43cc07ae9e04d88b354c4e52`, 83
embedded blobs, and the draft refusing.

`verify_wp7b_embedded_source_syntax.py` compiles 4 native sources on every run:
the pinned `PLATFORM_PROBE` exactly as the launcher obtains it, the gate's own
stub-header literal, and the two CUDA source literals held by the launcher
fixture (the `#include <cuda_runtime.h>` prefix assertion at
`verify_wp7b_launcher_sweep_fixture.py:102` and the gate's prefix assertion).
The launcher, the child entry and the builder currently hold **no** native
source of their own, which is the point of the Round 7 repair: the probe text
now exists in exactly one place.

### Mutation gate (Round 7)

The shared tool `/home/shivansh-srivastava/decisions_os/g9_jobs/tools/g9_guard_sweep.py`
v1.1 was run on `research/g9/kaggle_wp7b/wp7b_launcher.py` with the FULL bundle
fixture, 12 workers, `--chunk-seconds 36000`, `--resume` over the site records
already collected. Result: **SWEEP: PASS** — 291 sites, 291 killed, 0
survived, 0 error, 0 equivalent-accepted, 0 stale; shapes S2 15, S3 35, S4 70,
S5 171. Report: `logs/wpprobe.sweep.launcher.txt`; raw records
`/home/shivansh-srivastava/decisions_os/g9_jobs/scratch/wp7bprobe/sweep.launcher.full.json`.
No semantic equivalent is claimed anywhere in this round.

The launcher is the only module changed by this round, so it is the only module
that required a re-sweep. `verify_wp7b_launcher_sweep_fixture.py` and
`verify_wp7b_bundle_fixtures.py` are fixtures, not shipped modules, and the
builder, the child entry and the seal builder are byte-unchanged.

### Residual risk

The launcher now depends on the probe text existing at exactly one path,
`research/g9/cuda_qualification/stage2_cuda_core_qualification.py`. That file is
in the bundle closure and is hash-checked twice: by the builder against the
reviewed-dependency table before embedding, and by the child against the staged
index before the launcher may import it. The offline gate additionally asserts
the compiled text equals `PLATFORM_PROBE` exactly, so a future edit to either
side must be a deliberate, gate-visible change.
