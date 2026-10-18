# Gate-6 GPU qualification — RX 9070

This directory contains a deliberately non-production test track for the
reported AMD Radeon RX 9070 (`gfx1201`). It can establish whether a HIP build
is usable and whether a small ordered binary64 transcript agrees bit-for-bit
between CPU and GPU. It does not evaluate a Gate-6 domain, access the Gate-5
corpus, write a Gate-6 artifact, or authorize GPU values.

The CPU remains the only approved Gate-6 producer. A later, dated owner
approval would have to name a GPU backend, numerical contract, and provenance
before a GPU could contribute results.

## Fedora caveat

AMD lists the RX 9070 as `gfx1201` support, but its current Linux compatibility
matrix limits supported RX 9070 compute operating systems to specified Ubuntu
and RHEL releases. Fedora is therefore an **experimental qualification host**,
not a production platform. Do not blindly mix packages from another
distribution or change drivers just to make this pass.

## Run on the Fedora machine

From this repository root, first collect a no-write inventory:

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 research/g6/run_gpu_qualification.py
```

Paste the complete JSON output here. The minimum technical prerequisites for
the next step are:

- `rocminfo` exits successfully and reports `gfx1201`;
- `hipcc --version` exits successfully;
- `/dev/kfd` exists and is readable and writable by the invoking user.

On the observed Fedora 44 host, the kernel driver and `/dev/kfd` are already
ready, but the HIP compiler/runtime is absent. To install the minimal Fedora
packages and then continue automatically, use the repository-root wrapper:

```bash
./run_gpu_qualification_fedora.sh --install-fedora-rocm
```

That invokes `sudo dnf install hipcc rocminfo rocm-hip-devel libdrm-devel`.
It does not install an AMD driver, change the kernel, or install the broad
`rocm` meta-package.

If those conditions are true, run the temporary compile-and-execute probe:

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 research/g6/run_gpu_qualification.py --probe
```

The wrapper compiles with `-ffp-contract=off`,
`-mno-unsafe-fp-atomics`, and `--offload-arch=gfx1201`; on Fedora it also
links the packaged HIP runtime explicitly with `-lamdhip64`. It rejects a
failed compile or any CPU/GPU bit mismatch. The binary lives only in a
temporary directory and is deleted automatically. A `pass` is evidence for
progressing to a real energy-transcript prototype, not permission to run a
GPU Gate-6 pass.

## Bounded unbalanced-energy cross-check (prototype, non-production)

After the strict binary64 probe passes, the next and only further step on
this track is a bounded GPU-vs-CPU bit-exact cross-check of the **unbalanced**
energy transcript.  It is not a Gate-6 pass and produces no scientific value.

Files:

- `gpu_unbalanced_energy_crosscheck.hip.cpp` — HIP transcription of
  `src/g4/energy.py::unbalanced_energy`, operation-for-operation, binary64
  only, `#pragma clang fp contract(off)`, explicit `gfx1201` device selection.
- `energy_crosscheck.py` — declares the finite state set (1710 raw 20-bit
  masks: all-zero, all-one, every single bit, every all-but-one bit, every
  two-bit pair, named high-bit/alternating masks, whole sectors and their
  complements, two 256-mask ramps, and 1024 seeded splitmix64 draws), loads
  four reviewed coefficient points from the pre-execution ledgers (D011
  `primary_ell=30`; V-14 2x rows 70, 0 and 110), hash-pins every consumed
  input, encodes inputs, and compares raw bit patterns.
- `../run_gpu_energy_crosscheck.py` — CLI.  Default/`--plan` validates and
  prints the plan without compiling, evaluating, or writing.  `--run`
  compiles and executes in an automatically removed temporary directory and
  reports mismatch counts only.  `PYTHONDONTWRITEBYTECODE=1` is required.
- `../verify_gpu_energy_crosscheck_fixtures.py`,
  `../verify_gpu_energy_crosscheck_import_boundary.py`,
  `../verify_gpu_energy_crosscheck_host_emulation.py` — hardware-free checks
  (the last needs an ordinary C++ compiler and the stub in
  `host_emulation_stub/`, never hipcc).
- Repository-root `run_gpu_energy_crosscheck_fedora.sh [--run]` — wrapper.
  Without `--run` it performs only the hardware-free checks and the plan.

Compile contract: `-std=c++17 -O0 -ffp-contract=off -mno-unsafe-fp-atomics
-fno-fast-math --offload-arch=gfx1201 … -lamdhip64`.  The runner refuses to
substitute relaxed flags, fails closed on any pinned-input drift before or
after the run, and rejects any non-`gfx1201` architecture report.

On the Fedora machine, from the repository root:

```bash
./run_gpu_energy_crosscheck_fedora.sh          # hardware-free checks + plan only
./run_gpu_energy_crosscheck_fedora.sh --run    # probe precondition, then the cross-check
```

Paste the complete output back for independent review.  A `pass` (zero
GPU-vs-Python and zero host-C++-vs-Python mismatches over 4 × 1710
evaluations) is bounded qualification evidence for the unbalanced transcript
only.  It covers no slack encoding, no minimum, tie set, label, rate, or
transition, and it does not authorize a GPU backend.

## Throughput benchmark of the reviewed kernel (prototype, non-production)

Separate from, and never a substitute for, the cross-check above.  It times
the **same** reviewed kernel on the **same** fixed inputs (1710 declared
states × 4 reviewed coefficient points = 6840 evaluations per launch) under
two compile profiles, and compares their durations:

1. `strict_o0` — the existing cross-check compile command, unchanged;
2. `candidate_o3` — `-O3` with `-ffp-contract=off` and `-fno-fast-math`;
   every other flag identical.

Each profile is first gated by compiling the pinned cross-check program with
that profile's flags and running the full 6840-evaluation GPU↔Python
comparison; any mismatch rejects the profile and no timing is measured.  The
harness (`gpu_unbalanced_energy_benchmark.hip.cpp`) then textually includes
the pinned cross-check source with its `main` renamed — so the kernel text is
byte-identical — launches it repeatedly, and reports HIP-event per-launch
durations plus a back-to-back batch wall time.  Its last-launch bit patterns
are compared again; any mismatch withholds the timings.

Files:

- `gpu_unbalanced_energy_benchmark.hip.cpp` — harness (no kernel of its own).
- `energy_benchmark.py` — profiles, forbidden-flag guard, strict
  timing-report validator, gates, summary; loads `energy_crosscheck.py` by
  path and pins it.
- `host_emulation_stub_benchmark/` — steady-clock event shims layered over
  the cross-check stub, for hardware-free emulation only.
- `../run_gpu_energy_benchmark.py [--plan|--run] [--warmup N] [--launches N]`
  — CLI; default `--plan` compiles nothing and writes nothing; `--run`
  requires `PYTHONDONTWRITEBYTECODE=1`, hipcc, and temporary files only.
  Bounds: warm-up 0–100, timed 1–5000 (defaults 10 and 200).
- `../verify_gpu_energy_benchmark_fixtures.py`,
  `../verify_gpu_energy_benchmark_import_boundary.py`,
  `../verify_gpu_energy_benchmark_host_emulation.py` — hardware-free checks;
  the last drives the real gate with an ordinary C++ compiler, proves both
  profiles bit-exact on the host, and proves a mutated cross-check build and
  a mutated harness build are each rejected without timings.
- Repository-root `run_gpu_energy_benchmark_fedora.sh [--run]` — wrapper;
  with `--run` it first requires `./run_gpu_energy_crosscheck_fedora.sh --run`
  to pass.

Output is timings and counts only (no energy, minimum, label, rate, or other
scientific quantity).  An `accepted` verdict means both profiles were
bit-exact on this bounded input and were timed; it is not a production
throughput claim, does not cover any other input or the slack encoding, and
does not authorize a GPU backend or an `-O3` production build.

On the Fedora machine, from the repository root:

```bash
./run_gpu_energy_benchmark_fedora.sh          # hardware-free checks + plan only
./run_gpu_energy_benchmark_fedora.sh --run    # strict cross-check first, then both profiles
```

## Bounded slack-energy cross-check at the exact lift (prototype, non-production)

A second bounded cross-check covers the **slack** encoding.  It reuses, by
import, the unbalanced prototype's raw state set and four coefficient points,
and for each raw state uses only the canonical exact-minimizer lift
`src/g4/energy.py::exact_slack_lift` as the 19-bit auxiliary.  Raw states
whose sector or budget residual is not exactly representable in its slack
register (negative or out of range) have no exact lift; they are excluded,
counted by register, and reported.  On the accepted instance 293 of the 1710
raw masks lift, so the check is 4 × 293 = 1172 evaluations.  No clamped or
searched auxiliary is ever substituted, no slack domain is enumerated, and no
minimum, tie set, label, rate, or transition is computed.

Because the lift is exact, every `slack_delta` is `+0.0`; the check therefore
exercises the register accumulation, delta, square, and penalty statements
only at the zero-delta branch, and the objective/cardinality path in full.

Files:

- `gpu_slack_energy_crosscheck.hip.cpp` — HIP transcription of
  `src/g4/energy.py::slack_energy`, operation-for-operation, binary64 only,
  bit weights by integer shift, `#pragma clang fp contract(off)`, explicit
  `gfx1201` device selection; the auxiliary word is consumed, never derived.
- `slack_energy_crosscheck.py` — binds the shared state set and points from
  `energy_crosscheck.py`, attaches the exact lift, hash-pins every consumed
  input (including `energy_crosscheck.py`), encodes inputs, and compares raw
  bit patterns.
- `../run_gpu_slack_energy_crosscheck.py` — CLI; same `--plan`/`--run`
  contract as the unbalanced runner.
- `../verify_gpu_slack_energy_crosscheck_fixtures.py`,
  `../verify_gpu_slack_energy_crosscheck_import_boundary.py`,
  `../verify_gpu_slack_energy_crosscheck_host_emulation.py` — hardware-free
  checks (the fixtures include an independent residual oracle for every
  attached auxiliary and every exclusion; the emulation proves three slack
  and objective mutations are detected).
- Repository-root `run_gpu_slack_energy_crosscheck_fedora.sh [--run]`.

Intended order on the Fedora machine: probe, unbalanced cross-check, then

```bash
./run_gpu_slack_energy_crosscheck_fedora.sh          # hardware-free checks + plan only
./run_gpu_slack_energy_crosscheck_fedora.sh --run    # probe precondition, then the slack cross-check
```

Paste the complete output back for independent review.  A `pass` is bounded
qualification evidence for the slack transcript at the exact lift only and
does not authorize a GPU backend.
