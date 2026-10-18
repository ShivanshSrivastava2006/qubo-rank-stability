#!/usr/bin/env python3
"""Read-only ROCm/HIP inventory for the experimental Gate-6 GPU track.

This is intentionally only an environment check.  It never imports a Gate-6
runner, reads the Gate-5 corpus, compiles code, writes a file, or creates a
Gate-6 result.  A successful result means that the machine may proceed to the
separate binary64 probe; it does *not* approve GPU-produced Gate-6 values.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any


TARGET_ARCHITECTURE = "gfx1201"
AMD_SUPPORTED_LINUX_IDS = frozenset({"ubuntu", "rhel", "redhat", "ol"})
TIMEOUT_SECONDS = 15


def _which(name: str) -> str | None:
    """Locate a ROCm executable on PATH or the standard ROCm prefix."""
    standard = Path("/opt/rocm/bin") / name
    return shutil.which(name) or (str(standard) if standard.is_file() else None)


def _run(command: list[str]) -> dict[str, Any]:
    """Capture an observational command without raising on its absence/failure."""
    executable = _which(command[0])
    if executable is None:
        return {"command": command, "found": False}
    try:
        completed = subprocess.run(
            [executable, *command[1:]],
            text=True,
            capture_output=True,
            check=False,
            timeout=TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "command": command,
            "found": True,
            "error": type(exc).__name__,
        }
    return {
        "command": command,
        "found": True,
        "returncode": completed.returncode,
        # Command output is retained only as inventory evidence; cap it so a
        # broken driver cannot produce an unbounded terminal payload.
        "stdout": completed.stdout[:16000],
        "stderr": completed.stderr[:4000],
    }


def _os_release() -> dict[str, str]:
    path = Path("/etc/os-release")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    output: dict[str, str] = {}
    for line in lines:
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        output[key] = value.strip().strip('"')
    return output


def _device_access(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "readable": os.access(path, os.R_OK),
        "writable": os.access(path, os.W_OK),
    }


def collect_preflight() -> dict[str, Any]:
    """Collect sufficient evidence to decide whether a HIP probe can be run."""
    os_release = _os_release()
    distro_id = os_release.get("ID", "").lower()
    rocminfo = _run(["rocminfo"])
    hipcc = _run(["hipcc", "--version"])
    hipconfig = _run(["hipconfig", "--full"])
    lspci = _run(["lspci", "-nnk"])
    amd_smi = _run(["amd-smi", "version"])
    rocm_smi = _run(["rocm-smi", "--showproductname"])
    clinfo = _run(["clinfo", "-l"])

    rocminfo_text = str(rocminfo.get("stdout", ""))
    lspci_text = str(lspci.get("stdout", ""))
    has_target_agent = (
        rocminfo.get("returncode") == 0
        and TARGET_ARCHITECTURE in rocminfo_text.lower()
    )
    has_amd_pci_device = "amd" in lspci_text.lower() or "ati" in lspci_text.lower()
    devices = {
        "kfd": _device_access(Path("/dev/kfd")),
        "dri_render_nodes": [
            _device_access(path)
            for path in sorted(Path("/dev/dri").glob("renderD*"))
        ],
    }
    kfd = devices["kfd"]
    device_access = bool(kfd["exists"] and kfd["readable"] and kfd["writable"])
    compiler_ready = hipcc.get("returncode") == 0
    runtime_ready = has_target_agent and device_access
    probe_ready = compiler_ready and runtime_ready

    if probe_ready:
        verdict = "experimental_probe_ready"
    elif not compiler_ready:
        verdict = "blocked_missing_hipcc"
    elif not has_target_agent:
        verdict = "blocked_missing_gfx1201_rocm_agent"
    else:
        verdict = "blocked_gpu_device_access"

    official_os = distro_id in AMD_SUPPORTED_LINUX_IDS
    return {
        "schema": "decisions_os/g6_gpu_preflight/v1",
        "purpose": (
            "non-production ROCm/HIP qualification only; GPU output cannot "
            "contribute to a Gate-6 artifact"
        ),
        "scientific_outputs": "intentionally absent",
        "target_gpu": {
            "reported_model": "AMD Radeon RX 9070",
            "expected_llvm_target": TARGET_ARCHITECTURE,
        },
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version,
            "os_release": os_release,
            "groups": sorted(os.getgroups()),
        },
        "support": {
            "amd_current_linux_matrix_official_os": official_os,
            "note": (
                "Fedora is not an officially supported RX 9070 compute OS in "
                "AMD's current Linux compatibility matrix. A successful probe "
                "there is experimental evidence only."
            ),
        },
        "devices": devices,
        "commands": {
            "lspci": lspci,
            "rocminfo": rocminfo,
            "hipcc": hipcc,
            "hipconfig": hipconfig,
            "amd_smi": amd_smi,
            "rocm_smi": rocm_smi,
            "clinfo": clinfo,
        },
        "checks": {
            "pci_amd_device_observed": has_amd_pci_device,
            "rocminfo_reports_gfx1201": has_target_agent,
            "hipcc_available": compiler_ready,
            "gpu_device_access": device_access,
            "hip_probe_ready": probe_ready,
        },
        "verdict": verdict,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero unless the machine is ready for the HIP probe",
    )
    args = parser.parse_args(argv)
    result = collect_preflight()
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if not args.strict or result["checks"]["hip_probe_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
