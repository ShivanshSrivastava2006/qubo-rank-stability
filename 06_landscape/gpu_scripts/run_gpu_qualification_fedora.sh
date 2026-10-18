#!/usr/bin/env bash
# One-command, non-production qualification for the reported RX 9070 host.
#
# By default this script does not install packages, change drivers, access the
# Gate-5 corpus, or create Gate-6 output. With --install-fedora-rocm it adds
# only Fedora's HIP compiler/runtime prerequisites, then resumes qualification.
# It exits 2 after printing the inventory if ROCm/HIP is not ready.

set -euo pipefail

install_fedora_rocm=false
if [[ $# -eq 1 && "$1" == "--install-fedora-rocm" ]]; then
  install_fedora_rocm=true
elif [[ $# -ne 0 ]]; then
  echo "usage: ./run_gpu_qualification_fedora.sh [--install-fedora-rocm]" >&2
  exit 64
fi

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1

temporary_dir="$(mktemp -d -t g6-gpu-qualification.XXXXXX)"
trap 'rm -rf -- "$temporary_dir"' EXIT
preflight_json="$temporary_dir/preflight.json"

echo '[1/4] Checking the isolated GPU-qualification fixtures…'
python3 research/g6/verify_gpu_qualification_fixtures.py

echo '[2/4] Rechecking those fixtures under python -O…'
python3 -O research/g6/verify_gpu_qualification_fixtures.py

if [[ "$install_fedora_rocm" == "true" ]]; then
  if ! grep -qx 'ID=fedora' /etc/os-release; then
    echo 'Refusing --install-fedora-rocm: this host is not Fedora.' >&2
    exit 64
  fi
  if ! command -v dnf >/dev/null 2>&1; then
    echo 'Refusing --install-fedora-rocm: dnf is unavailable.' >&2
    exit 64
  fi
  fedora_version="$(. /etc/os-release && printf '%s' "$VERSION_ID")"
  fedora_base="https://dl.fedoraproject.org/pub/fedora/linux/releases/${fedora_version}/Everything/$(uname -m)/os/"
  echo '[3/5] Installing Fedora HIP/ROCm qualification prerequisites…'
  # Deliberately no driver, kernel, or full "rocm" meta-package installation.
  # The official Fedora release mirror avoids a known stale-mirror 404 for
  # Fedora 44's ROCm packages.
  sudo dnf \
    --setopt="fedora.baseurl=${fedora_base}" \
    --setopt='fedora.metalink=' \
    --setopt='fedora.mirrorlist=' \
    --setopt=max_parallel_downloads=10 \
    install --assumeyes hipcc rocminfo rocm-hip-devel libdrm-devel
fi

echo '[preflight] Inspecting Fedora, ROCm, HIP, and the RX 9070 device…'
python3 research/g6/run_gpu_qualification.py | tee "$preflight_json"

probe_ready="$({
  python3 - "$preflight_json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
print("true" if payload["preflight"]["checks"]["hip_probe_ready"] else "false")
PY
} )"

if [[ "$probe_ready" != "true" ]]; then
  echo >&2
  echo 'GPU probe not started: ROCm/HIP is not ready on this host.' >&2
  echo 'Nothing was installed or changed. Send the JSON printed above to the reviewer.' >&2
  exit 2
fi

echo '[probe] Compiling and running the temporary strict-binary64 HIP probe…'
python3 research/g6/run_gpu_qualification.py --probe

echo 'PASS: RX 9070 GPU qualification probe completed.'
echo 'This is non-production evidence only; it does not authorize GPU Gate-6 output.'
