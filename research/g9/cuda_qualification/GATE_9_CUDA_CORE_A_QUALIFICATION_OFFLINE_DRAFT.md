# Gate-9 §A CUDA corruption qualification — offline candidate

Status: **ARCHIVED OFFLINE CANDIDATE; LATER GPU CHECKS PASSED; §A NOT SATISFIED**.
This additive candidate implements the amendment's generic corrupted-kernel
test path. Its offline construction did not modify the approved 11-file clean
core release, draw a Stage-2 candidate, compile with `nvcc`, start Kaggle, or
produce a scientific record. A later separately approved one-shot GPU run is
documented in `research/g9/kaggle_dry_run/GATE_9_KAGGLE_CORE_A_VERSION1_OUTCOME.md`;
its exact image-to-run provenance condition remains open. The successful v3
clean T4 dry run remains distinct evidence, not §A.

## Pinned offline bytes

| Item | SHA-256 |
| --- | --- |
| Approved clean core release | `50f25827ef07b8fcbf3f19223f3982b486f1b11c5d71a7d0c037fd1c6f5328a9` |
| Preserved clean T4 receipt | `41a32675e667ffe8e9fb0e2a5d15b191c242f39a221ce9a3d941152f41530859` |
| `stage2_cuda_core_corruption_qualification.py` | `65f0f1d67d9df65602df28854b1dcae976a9c0bfe0c25eebb45cd7249527e218` |
| `run_stage2_cuda_core_corruption_qualification.py` | `be6c06cf0587a0f4dadb47fb19554c4cbd4f368d9906a37bbc7b714c9c86f8b8` |
| `verify_stage2_cuda_core_corruption_qualification_fixtures.py` | `b8d6ea456475436f1bf63b6dbcb8a01d825de56d3f6f9be5f165368ca8d6386f` |
| Read-only `--plan` content SHA-256 | `a99fae9dd50f3c29e4db5110d05afc37f406f1cf443fbd03ae0009cba5d29856` |
| G6 host-emulation CUDA stub used by offline fixtures | `fff06b9ad69b447b17f1ed31084febd59c988cb5c583e3857a627c6622f96a4c` |

The plan binds twelve source/fixture files, the eight exact mutated CUDA
source hashes, the approved clean release, the clean T4 receipt, and the
unchanged numerical compiler flags
`--fmad=false --ftz=false --prec-div=true --prec-sqrt=true` with host
`-ffp-contract=off -fno-fast-math`. Mutation categories cover:

1. canonical index reversal and first-seen minimum weakening;
2. binary64 energy reassociation;
3. slack-register layout drift and loss of a tied minimizer;
4. omitted D015 `max(|y|,|y_min|)` scale and permuted `c_H` flag bits;
5. a non-finite energy injection.

The future GPU runner requires each mutated `.cu` to compile under the exact
reviewed flags, emit a well-formed report from the same selected GPU, and be
rejected by the independently computed Python reference. A compiler error,
crash, timeout, absent report, wrong device, or unchanged report is **not**
counted as a successful corruption rejection. The clean GPU baseline must
first match the Python reference and a separately compiled platform probe.
Only labels, categories, source hashes, bounded reasons, pass/fail evidence,
source/compiler bindings, and platform/build observations enter its receipt.
The observed runtime fields include the actual Python and NumPy versions used
by the reference process, as the amendment requires for a qualification
identity; neither version is guessed from a previous session.

## Offline evidence

`PYTHONDONTWRITEBYTECODE=1 python3` and `python3 -O` both passed the fixture
suite on the final bytes: 8/8 selected mutations compiled with g++ against
the G6 CUDA host stub and were rejected by the same Python reference that
the GPU runner will use. Each mutation matches an independently established
host-emulation source transform byte-for-byte. The NaN case also returned a
device-side failure verdict and a nonzero non-finite counter. Normal and
`-O` CLI `--plan` bytes agree; plan and unreleased execution refusals occur
before any `nvcc` lookup. No bytecode or CUDA compilation was created by
these tests.

An independent reviewer source review found one missing identity input in the
first candidate: the future GPU receipt omitted Python/NumPy fingerprints.
The qualifier now samples both after the execution-release gate, and a fixture
requires them to match the current reference process. On the final bytes,
normal and `-O` fixture runs again passed 8/8. This is a repair of the
future receipt, not evidence that a GPU qualification has happened.
The staged CLI now also refuses if any hash-pinned Python import resolves
outside the staged root. An offline fixture exercises this guard with a
shadowed module path; the final normal and `-O` corruption suites pass 8/8.

## Release and platform boundary

The named execution record
`research/decisions/GATE_9_CUDA_CORE_CORRUPTION_QUALIFICATION_RELEASE.json`
now exists at SHA-256
`585da5d87908738e34c9b9858a0ef6d1c5e5cf4311dd1f6e3ba00a9d0ce6bfb9`.
It binds the exact plan hash and twelve-file source map with `status=approved`.
The CLI's `--qualify-corruptions` additionally requires this exact reviewed
SHA-256 and explicit environment permission
`G9_ALLOW_NONSCIENTIFIC_CUDA_CORRUPTION_QUALIFICATION=1` before looking up
`nvcc`. A two-file Kaggle bundle has been staged offline as described in
`research/g9/kaggle_dry_run/GATE_9_CUDA_CORE_A_BUNDLE_DRAFT.md`. This release
did not itself authorize a Kaggle push; the owner later gave separate one-shot
approval. The resulting GPU checks and unresolved §A audit are documented in
the version-1 outcome record.

The clean dry run's image label `kaggle-api-default-gpu-unverified` is not a
provenance identity. The future §A runner records `BUILD_DATE`, `GIT_COMMIT`,
`CUDA_VERSION`, GPU model/capability, driver/runtime, and `nvcc` version, but
returns only
`gpu_corruption_checks_passed_pending_image_metadata_audit`, with amendment
status `not_satisfied_pending_post_run_audit_and_owner_acceptance`. A
separately authorized, read-only post-run audit must bind Kaggle's pulled
image digest to the versioned run, and the owner must accept the final
qualification evidence, before §A can be declared satisfied. Production sessions
must subsequently match the qualified platform/source/compiler identity;
the mechanics of that match and the instance-ready writer remain separate
work. No candidate generation or scientific write follows from this draft.
