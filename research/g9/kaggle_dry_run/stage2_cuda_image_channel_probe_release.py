#!/usr/bin/env python3
"""Gate-9 CUDA image-channel probe one-shot decision packet release generator.

OFFLINE, UNAPPROVED. Read-only and pure by default.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from pathlib import Path

EXPECTED_PROBE_FILES = {
    "GATE_9_CUDA_IMAGE_CHANNEL_PROBE_DRAFT.md": "af818ee1f4c0547c6129407b01969b30ea38056e8b7fb924de432cccc9436d05",
    "build_g9_cuda_image_channel_probe_bundle.py": "138e5e7ac0bfc7d14344feb149a229d37594dbd846e1e30d7a2971f9bc3fec1e",
    "stage2_cuda_image_channel_probe.py": "184de4188562ba107348540de9a265d92550b5c59378b60b4bf00de18031e7fa",
    "verify_g9_cuda_image_channel_probe_fixtures.py": "8b0e99b3cf115f1780ceffa3a94823052d61f820b5c523679316e0f7b38b1889",
}

ACCOUNT_SLUG = "shivanshsrivastava06"
KERNEL_ID = "g9-cuda-image-channel-probe"
METADATA_NAME = "kernel-metadata.json"
SOURCE_NAME = "g9_cuda_image_channel_probe_kaggle.py"

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

REQUIRED_PRIVACY_FIELDS = {
    "is_private": True,
    "enable_internet": False,
    "machine_shape": "NvidiaTeslaT4",
}

def derive_privacy(metadata: dict) -> dict:
    """Read the reported privacy posture out of the validated metadata itself.

    Every field is taken from the parsed bundle metadata rather than restated as
    a literal, so the plan cannot report a posture the bundle does not carry.
    Each field is still required to hold its reviewed value, and the comparison
    is exact in type as well as value.
    """
    derived = {}
    for key, required in REQUIRED_PRIVACY_FIELDS.items():
        if key not in metadata:
            raise ValueError(f"metadata missing privacy field: {key}")
        value = metadata[key]
        if type(value) is not type(required) or value != required:
            raise ValueError(f"metadata privacy field {key} is not {required!r}: got {value!r}")
        derived[key] = value
    derived["unpinned_image"] = not any(
        k in metadata for k in ("docker_image", "docker_image_pinning_type")
    )
    if derived["unpinned_image"] is not True:
        raise ValueError("metadata privacy field unpinned_image is not True")
    return derived

def build_plan(root: Path) -> dict:
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        raise RuntimeError("PYTHONDONTWRITEBYTECODE=1 must be set in environment")
    sys.dont_write_bytecode = True

    buffers = {}
    for name, expected_hash in EXPECTED_PROBE_FILES.items():
        p = root / name
        try:
            st = p.lstat()
        except FileNotFoundError:
            raise ValueError(f"missing file: {name}")
        if stat.S_ISLNK(st.st_mode):
            raise ValueError(f"symlink rejected: {name}")
        if not stat.S_ISREG(st.st_mode):
            raise ValueError(f"non-regular file rejected: {name}")
            
        b = p.read_bytes()
        actual_hash = digest(b)
        if actual_hash != expected_hash:
            raise ValueError(f"hash mismatch for {name}: expected {expected_hash}, got {actual_hash}")
        buffers[name] = b

    builder_code = compile(buffers["build_g9_cuda_image_channel_probe_bundle.py"], "build_g9_cuda_image_channel_probe_bundle.py", "exec", dont_inherit=True)
    builder_ns = {}
    exec(builder_code, builder_ns)

    metadata_bytes = builder_ns["build_metadata"](ACCOUNT_SLUG)
    launcher_bytes = builder_ns["build_launcher"](buffers["stage2_cuda_image_channel_probe.py"])

    # Verify metadata against policy (builder's expectations)
    parsed_metadata = json.loads(metadata_bytes.decode("ascii"))
    builder_ns["validate_metadata"](parsed_metadata)
    
    if parsed_metadata.get("enable_internet") is not False:
        raise ValueError("metadata internet must be False")
    if any(k in parsed_metadata for k in ("docker_image", "docker_image_pinning_type")):
        raise ValueError("metadata must be unpinned")

    # Derived from the validated metadata, never restated as literals here.
    privacy = derive_privacy(parsed_metadata)

    # The identity keys are excluded from validate_metadata's policy comparison,
    # so they must be checked here or the plan would report an identity it never
    # verified against the bundle it is describing.
    kernel_id = parsed_metadata.get("id")
    if type(kernel_id) is not str or kernel_id != f"{ACCOUNT_SLUG}/{KERNEL_ID}":
        raise ValueError(f"metadata id is not {ACCOUNT_SLUG}/{KERNEL_ID}: got {kernel_id!r}")
    if parsed_metadata.get("code_file") != SOURCE_NAME:
        raise ValueError(f"metadata code_file is not {SOURCE_NAME}: got {parsed_metadata.get('code_file')!r}")

    return {
        "schema": "decisions_os/g9_cuda_image_channel_probe_release_plan/v1",
        "status": "UNAPPROVED_NOT_EXECUTABLE",
        "action": "ONE_SHOT_PROBE_EXECUTION",
        "semantics": "ONE_ATTEMPT_NO_RETRY",
        "kernel_id": kernel_id,
        "bundle_hashes": {
            METADATA_NAME: digest(metadata_bytes),
            SOURCE_NAME: digest(launcher_bytes),
        },
        "required_outputs": [
            "kernel-metadata.json",
            "g9_cuda_image_channel_probe_kaggle.py"
        ],
        "privacy": privacy,
    }

def main() -> int:
    try:
        plan = build_plan(Path(__file__).resolve().parent)
    except Exception as exc:
        sys.stderr.write(f"FAIL: {exc}\n")
        return 1

    out = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    sys.stdout.buffer.write((out + "\n").encode("ascii"))
    return 0

if __name__ == "__main__":
    sys.exit(main())
