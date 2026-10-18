# Gate-6 CUDA/T4 qualification and V-14 batch contract

Non-production track for a **Colab NVIDIA T4** (compute capability 7.5,
`sm_75`).  It is separate from, and never mixes with, the RX 9070 / ROCm
(`gpu_qualification/`, `gfx1201`) track.  Nothing here evaluates a Gate-6
domain, reads the Gate-5 corpus, writes a Gate-6 artifact, installs a
package, or authorizes GPU-produced values.  The CPU remains the only
approved producer until a dated owner approval names a CUDA backend.

## Files

- `cuda_unbalanced_energy_crosscheck.cu` — CUDA transcription of
  `src/g4/energy.py::unbalanced_energy` (transcript text byte-identical to the
  reviewed HIP kernel), binary64 only, explicit T4 / 7.5 device selection,
  same input/output word formats as the HIP cross-check.
- `cuda_energy_crosscheck.py` — reuses the HIP prototype's 1710-state set,
  four reviewed coefficient points, encodings, and comparator (pinned);
  nvcc contract; T4-only device-report validation; emits mismatch counts and
  environment identity (`qualification_identity` + its SHA-256) only.
- `../run_cuda_energy_crosscheck.py [--plan|--run]` — `--plan` needs no nvcc
  or GPU and writes nothing; `--run` compiles in an auto-removed temporary
  directory and fails closed without nvcc, the CUDA runtime, or a T4.
- `host_emulation_stub/cuda_runtime.h` — g++-only shim for the hardware-free
  emulation check; never on a real nvcc include path.
- `v14_batch_contract.py` + `../plan_v14_cuda_batches.py` — V-14 batch
  planning and metadata-only final-set validation (no value-producing run).
- `../verify_cuda_energy_crosscheck_{fixtures,import_boundary,host_emulation}.py`,
  `../verify_v14_cuda_batch_fixtures.py` — hardware-free checks; run under
  `python3` and `python3 -O` with `PYTHONDONTWRITEBYTECODE=1`.

nvcc contract: `-std=c++17 -O0 -gencode arch=compute_75,code=sm_75
--fmad=false --ftz=false --prec-div=true --prec-sqrt=true -Xptxas -O0
-Xcompiler -O0 -Xcompiler -ffp-contract=off -Xcompiler -fno-fast-math`.

## Colab (T4 runtime) — qualification only

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 research/g6/verify_cuda_energy_crosscheck_fixtures.py
python3 -O research/g6/verify_cuda_energy_crosscheck_fixtures.py
python3 research/g6/verify_cuda_energy_crosscheck_import_boundary.py
python3 research/g6/verify_cuda_energy_crosscheck_host_emulation.py
python3 research/g6/run_cuda_energy_crosscheck.py --plan
python3 research/g6/run_cuda_energy_crosscheck.py --run > /tmp/cuda_t4_qualification.json
```

Paste the complete `--run` JSON back for independent review.  A `pass`
(zero GPU-vs-Python and zero host-C++-vs-Python mismatches over 4 × 1710
evaluations) is bounded qualification evidence for the unbalanced transcript
on that T4/toolchain only.

## V-14 batches (planning only; no values yet)

Batch order: `linear = card*N^2 + sector*N + budget`; a batch is `[start, stop)`
and is independent of every other batch.  Sizing is derived, never guessed:
`uncapped = floor(slowest_rate × (12600 s − largest_setup_seconds) × derate)`,
`coordinates_per_batch = min(uncapped, 4096)` (the engine's per-invocation
cap), derate default 9/10, under a 14400 s session budget; setup is fixed
per independent session and is never amortised.  A throughput measurement
(`decisions_os/g6_v14_cuda_t4_throughput_measurement/v1`; samples carry
`coordinates`, `wall_seconds`, `setup_seconds`, `coordinate_seconds` as exact
decimals reconciling exactly; bound to the engine identity SHA-256) comes
only from the engine's `--throughput` run.

```bash
python3 research/g6/plan_v14_cuda_batches.py plan --scale 2x \
  --qualification /tmp/cuda_t4_qualification.json --throughput measurement.json > plan.json
python3 research/g6/plan_v14_cuda_batches.py validate-final-set --plan plan.json batch_*.manifest.json
```

The final-set validator accepts only an exact non-overlapping cover whose
manifests all bind the identical plan, ledger, source, CUDA/T4, compiler, and
qualification identity; different Colab sessions / physical T4s are allowed,
intra-batch drift and any RX 9070 / ROCm / HIP / emulation platform are not.

## Slack-energy cross-check at the exact lift (CUDA/T4, non-production)

Second qualification step, after a passed unbalanced `--run`.  Same 1710 raw
masks and four reviewed points; each auxiliary comes **only** from
`src/g4/energy.py::exact_slack_lift`, and raw states without an exact lift
are excluded and counted by register (derived at plan/run time, never
assumed; on the accepted instance 293 lift, 1417 are excluded).  Compared
bit-for-bit against `src.g4.energy.slack_energy` at 4 × 293 evaluations.

- `cuda_slack_energy_crosscheck.cu` — HIP slack transcript text verbatim,
  CUDA scaffolding from the qualified unbalanced program (both pinned).
- `cuda_slack_energy_crosscheck.py`, `../run_cuda_slack_energy_crosscheck.py`
  — same `--plan`/`--run` contract and nvcc flags as the unbalanced runner;
  `--run` refuses without nvcc/T4 and writes nothing.
- `../verify_cuda_slack_energy_crosscheck_{fixtures,import_boundary,host_emulation}.py`
  — hardware-free; the fixtures never invoke nvcc even when installed.

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 research/g6/verify_cuda_slack_energy_crosscheck_fixtures.py
python3 -O research/g6/verify_cuda_slack_energy_crosscheck_fixtures.py
python3 research/g6/verify_cuda_slack_energy_crosscheck_import_boundary.py
python3 research/g6/verify_cuda_slack_energy_crosscheck_host_emulation.py
python3 research/g6/run_cuda_slack_energy_crosscheck.py --plan
python3 research/g6/run_cuda_slack_energy_crosscheck.py --run   # Colab T4 only
```

A `pass` is bounded qualification evidence for the slack transcript at the
exact lift only (every `slack_delta` is `+0.0`); it authorizes no GPU-produced
Gate-6 value, V-14 value, domain run, tie set, label, rate, or conclusion.

## Full-domain V-14 engine: validation and throughput only (CUDA/T4, non-value)

Owner-authorized (2026-09-20) for implementation and **non-value** validation.
It emits only counters, exact elapsed times, and identities; energies,
minima, tie flags, and states exist only in process memory and in the
auto-removed temporary directory.  It never emits a V-14 value, batch,
manifest, rate, comparison, or conclusion.

- `cuda_v14_prepared_domain_engine.cu` — prepares both canonical domains on
  the device (unbalanced: 2^20 `BinaryDomain` states; slack: the canonical
  active-CSB `SlackDomainCache`, 1,048,576 entries, logical digest
  `d052e678…`, supplied by the runner, never re-derived), evaluates
  `*_energy_prepared` transcripts (qualified segments verbatim), then a
  deterministic first-seen minimum and D015 tie flags at c_H ∈ {1024, 2048,
  4096} (`certify.py` semantics; strided scans, no shared memory/atomics).
- `cuda_v14_engine.py`, `../run_cuda_v14_engine.py` — `--plan` (no nvcc/GPU/
  writes; re-derives and pins the domain identity), `--validate` (8 declared
  coordinates × full domains × both encodings vs the canonical CPU prepared
  services and reduction), `--throughput --scale S --start A --stop B` (linear
  range `[A, B)`, ≤ 4096 coordinates; prints counts, exact timing, and a
  `throughput_measurement` in the batch-contract schema whose sample carries
  `coordinates`, `wall_seconds` (end-to-end `monotonic_ns` span from the
  environment guard to result construction), `setup_seconds`, and
  `coordinate_seconds` (engine loop), with `wall == setup + coordinate`
  exactly at nanosecond precision; the device reduction counts non-finite
  words in every mode).  Both runs require
  `--unbalanced-record` and `--slack-record` (the passed qualifier `--run`
  outputs); observed platform must equal both.
- `../verify_cuda_v14_engine_{fixtures,import_boundary,host_emulation}.py`.
- The batch contract (`v14_batch_contract.py`) now binds the engine
  `--validate` record, which carries **both** prerequisite identities, the
  slack-domain digest, and the engine source; a bare qualifier record is
  refused.

Declared validation coordinates (scale, card, sector, budget): 0.5x (0,0,0),
(15,15,15), (30,30,30), (30,0,15); 2x (0,0,0), (70,70,70), (110,110,110),
(110,0,55).  Per coordinate 2,097,152 evaluations; 16,777,216 in total.

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 research/g6/verify_cuda_v14_engine_fixtures.py && python3 -O research/g6/verify_cuda_v14_engine_fixtures.py
python3 research/g6/verify_cuda_v14_engine_import_boundary.py
python3 research/g6/verify_cuda_v14_engine_host_emulation.py
python3 research/g6/run_cuda_v14_engine.py --plan --unbalanced-record U.json --slack-record S.json
python3 research/g6/run_cuda_v14_engine.py --validate --unbalanced-record U.json --slack-record S.json > engine_validation.json   # Colab T4
python3 research/g6/run_cuda_v14_engine.py --throughput --scale 2x --start 0 --stop 64 --unbalanced-record U.json --slack-record S.json   # Colab T4
```

## Core batch producer (CUDA/T4, production-isolated; build and non-value validation only)

Separate from, and separately pinned against, the non-value engine.  A later
independent review and an explicit owner release record are required before
any `--run-batch` invocation; none has occurred.

- `cuda_v14_core_batch_engine.cu` — same transcripts/reduction as the pinned
  engine; returns only per-encoding `H_min` bits + canonical index and the
  deterministically **compacted** tie list (4096 contiguous chunks → host
  exclusive prefix offsets → ascending canonical order; ordering proof in the
  source header).  No energy word and no per-state flag array is ever copied
  to the host or written; output size = 56 B + 48 B per coordinate + 8 B per
  tied state, hard-capped at 2^28 tied entries per run.  Host temporaries are
  bounded by one coordinate's tie lists (≤ 2 × 8 MiB); the Python side
  streams one coordinate at a time.  `validate` mode adds an in-process
  host-C++ minima/compact-list reference.
- `cuda_v14_core_batch.py` — reconstructs `T_E` (canonical order) and `X_E`
  (`decode_x_e`, first-seen) from flags, classifies with
  `src.g4.classification` (Lambda_ref/f* from the pinned G3 ground truth;
  ADNYE-001, DECISIONS.md D015/D016 digests bound), and emits per-coordinate
  records for `(2048,2048)` plus the four D015 diagnostics (`c_f` re-labels the
  same `X_E`): `H_E_min_hex`, tie-comparator metadata, `T_E_size`, `X_E_size`,
  D016 set label, atomic A/B/C counts, atomic-label set, `I_C_exist`/`I_C_univ`,
  exact `p_A/p_B/p_C` as `[numerator, denominator]`, and SHA-256 commitments
  to the tied-domain-index and decoded-index streams.  No floats or booleans.
- `../run_cuda_v14_core_batches.py` — `--plan`, `--validate` (counters only),
  `--measure --scale S --start A --stop B` (timing only; records discarded),
  future `--run-batch --plan-file P --batch-id ID --release-record R
  --output-dir DIR` (DIR must be outside the repository; atomic pending-directory
  rename; collisions refused; a failed batch is rerun as the same range).
- `v14_core_batch_contract.py`, `../plan_v14_cuda_core_batches.py` — core plan
  from the core `--validate` record and core `--measure` timing only (engine
  timing refused), 3.5 h target / 4 h budget, 4096 cap, cap-limited
  calibration; `validate-final-set --plan P --artifacts DIR --output INDEX`
  verifies identities/hashes/exact coverage, the exact artifact member set
  (no extra or symlinked files), and every record semantically (exact key
  sets, plan/ledger key and coefficient bindings, all five D015 conditions
  per encoding, `c_H`/`c_f` bindings, integer/rational shapes, count sums and
  denominators, D016 label/indicator consistency, tie metadata, commitment
  formats and descriptors, canonical hex), then writes only a merged index.
- `../verify_cuda_v14_core_batch_{fixtures,import_boundary,host_emulation}.py`.
