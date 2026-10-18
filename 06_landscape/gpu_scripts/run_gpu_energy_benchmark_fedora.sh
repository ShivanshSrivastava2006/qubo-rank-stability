#!/usr/bin/env bash
# Non-production THROUGHPUT BENCHMARK wrapper for the reviewed unbalanced-energy
# GPU kernel on the reported RX 9070 (gfx1201) Fedora host.
#
# Default: hardware-free fixtures (normal and python -O), the import-boundary
# proof, the host-only C++ emulation of both compile profiles and of the
# rejection gates, and the no-write --plan.  Nothing is compiled with hipcc,
# nothing runs on the GPU, and no project file is written.
#
# --run: first requires the existing strict cross-check wrapper to pass with
# --run (binary64 probe, then the 6840-evaluation bit-exact cross-check at
# -O0), then compiles both profiles (strict -O0; candidate -O3 with fp
# contraction off and no fast-math) in an automatically removed temporary
# directory, gates each on the same 6840-evaluation cross-check, and prints
# durations and counts only.  It prints no energy or other scientific value.
#
# This script never installs packages, changes drivers, reads the Gate-5
# corpus, sweeps a domain, or creates a Gate-5/Gate-6 artifact.  An
# "accepted" verdict is a bounded measurement, not a production claim.

set -euo pipefail

run=false
if [[ $# -eq 1 && "$1" == "--run" ]]; then
  run=true
elif [[ $# -ne 0 ]]; then
  echo "usage: ./run_gpu_energy_benchmark_fedora.sh [--run]" >&2
  exit 64
fi

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1

echo '[1/7] Hardware-free benchmark fixtures…'
python3 research/g6/verify_gpu_energy_benchmark_fixtures.py
echo '[2/7] Hardware-free benchmark fixtures under python -O…'
python3 -O research/g6/verify_gpu_energy_benchmark_fixtures.py
echo '[3/7] Import-boundary proof (no Gate-5 corpus/runner path reachable)…'
python3 research/g6/verify_gpu_energy_benchmark_import_boundary.py
echo '[4/7] Host-only C++ emulation of both profiles and of the rejection gates…'
python3 research/g6/verify_gpu_energy_benchmark_host_emulation.py
echo '[5/7] No-write plan…'
python3 research/g6/run_gpu_energy_benchmark.py --plan

if [[ "$run" != "true" ]]; then
  echo '[6/7] Skipped: pass --run to require the strict cross-check and then benchmark.'
  echo '[7/7] Skipped GPU execution.'
  echo 'Nothing was compiled with hipcc, run on the GPU, installed, or written.'
  exit 0
fi

echo '[6/7] Precondition: the existing strict cross-check wrapper must pass with --run…'
./run_gpu_energy_crosscheck_fedora.sh --run
echo '[7/7] Compiling, gating, and timing both profiles on gfx1201 (temporary files only)…'
python3 research/g6/run_gpu_energy_benchmark.py --run

echo 'ACCEPTED: both profiles were bit-exact on the 6840-evaluation cross-check and were timed.'
echo 'Timings and counts only; non-production; no scientific output; no GPU backend is authorized.'
