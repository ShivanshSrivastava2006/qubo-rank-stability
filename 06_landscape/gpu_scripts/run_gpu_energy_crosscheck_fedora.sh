#!/usr/bin/env bash
# Bounded, non-production GPU-vs-CPU unbalanced-energy cross-check wrapper for
# the reported RX 9070 (gfx1201) Fedora host.
#
# Default: hardware-free fixtures, the import-boundary proof, the host-only
# C++ emulation check, and the no-write --plan.  Nothing is compiled with
# hipcc, nothing runs on the GPU, and no project file is written.
#
# --run: additionally requires the existing strict binary64 HIP probe to pass,
# then compiles and executes the energy cross-check in an automatically
# removed temporary directory and prints mismatch counts only.  A pass is
# qualification evidence; it does not authorize GPU-produced Gate-6 output.
#
# This script never installs packages, changes drivers, reads the Gate-5
# corpus, or creates a Gate-5/Gate-6 artifact.

set -euo pipefail

run=false
if [[ $# -eq 1 && "$1" == "--run" ]]; then
  run=true
elif [[ $# -ne 0 ]]; then
  echo "usage: ./run_gpu_energy_crosscheck_fedora.sh [--run]" >&2
  exit 64
fi

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1

echo '[1/6] Hardware-free cross-check fixtures…'
python3 research/g6/verify_gpu_energy_crosscheck_fixtures.py
echo '[2/6] Hardware-free cross-check fixtures under python -O…'
python3 -O research/g6/verify_gpu_energy_crosscheck_fixtures.py
echo '[3/6] Import-boundary proof (no Gate-5 corpus/runner path reachable)…'
python3 research/g6/verify_gpu_energy_crosscheck_import_boundary.py
echo '[4/6] Host-only C++ emulation of the transcript versus Python…'
python3 research/g6/verify_gpu_energy_crosscheck_host_emulation.py
echo '[5/6] No-write plan…'
python3 research/g6/run_gpu_energy_crosscheck.py --plan

if [[ "$run" != "true" ]]; then
  echo '[6/6] Skipped GPU execution: pass --run to compile and execute the bounded cross-check.'
  echo 'Nothing was compiled with hipcc, run on the GPU, installed, or written.'
  exit 0
fi

echo '[6/6a] Precondition: the existing strict binary64 HIP probe must pass…'
python3 research/g6/run_gpu_qualification.py --probe
echo '[6/6b] Compiling and executing the bounded unbalanced-energy cross-check on gfx1201…'
python3 research/g6/run_gpu_energy_crosscheck.py --run

echo 'PASS: bounded GPU-vs-CPU unbalanced-energy cross-check reported zero mismatches.'
echo 'This is non-production qualification evidence only; it does not authorize GPU Gate-6 output.'
