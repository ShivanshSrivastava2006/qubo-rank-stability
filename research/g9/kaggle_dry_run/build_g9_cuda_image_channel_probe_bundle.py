#!/usr/bin/env python3
"""Build the offline non-scientific image-channel discovery probe bundle.

This builder never contacts Kaggle, reads credentials, runs nvcc, reads
instance data, or touches the network. Output only when explicitly invoked.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from pathlib import Path

# Static metadata expectation, not runtime observed.
EXPECTED_METADATA_POLICY = {
    "competition_sources": [],
    "dataset_sources": [],
    "enable_gpu": True,
    "enable_internet": False,
    "enable_tpu": False,
    "is_private": True,
    "kernel_sources": [],
    "kernel_type": "script",
    "keywords": [],
    "language": "python",
    "machine_shape": "NvidiaTeslaT4",
    "model_sources": [],
}
METADATA_IDENTITY_KEYS = ("code_file", "id", "title")

KERNEL_ID = "g9-cuda-image-channel-probe"
SOURCE_NAME = "g9_cuda_image_channel_probe_kaggle.py"
METADATA_NAME = "kernel-metadata.json"
EXPECTED_SOURCE_SHA256 = "184de4188562ba107348540de9a265d92550b5c59378b60b4bf00de18031e7fa"

LAUNCHER_TEMPLATE = """#!/usr/bin/env python3
import base64
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

EXPECTED_SHA256 = "{sha256}"
PAYLOAD_B64 = "{b64}"

def main():
    payload = base64.b64decode(PAYLOAD_B64)
    if hashlib.sha256(payload).hexdigest() != EXPECTED_SHA256:
        sys.stderr.write("REFUSED: embedded payload hash mismatch\\n")
        return 1
    
    with tempfile.TemporaryDirectory(prefix="g9-image-channel-probe-") as d:
        script = Path(d) / "stage2_cuda_image_channel_probe.py"
        script.write_bytes(payload)
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run([sys.executable, "-O", str(script)], env=env).returncode

if __name__ == "__main__":
    sys.exit(main())
"""

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")

def validate_metadata(metadata: dict) -> None:
    policy = {k: v for k, v in metadata.items() if k not in METADATA_IDENTITY_KEYS}
    if canonical(policy) != canonical(EXPECTED_METADATA_POLICY):
        raise ValueError("metadata policy drift")
    if metadata.get("enable_internet") is not False:
        raise ValueError("metadata internet must be False")
    if any(k in metadata for k in ("docker_image", "docker_image_pinning_type")):
        raise ValueError("metadata must be unpinned")

def build_metadata(kaggle_user: str) -> bytes:
    import re
    if not re.match(r"^[a-zA-Z0-9]+(-[a-zA-Z0-9]+)*$", kaggle_user):
        raise ValueError("invalid kaggle user slug")
    metadata = dict(EXPECTED_METADATA_POLICY)
    metadata["id"] = f"{kaggle_user}/{KERNEL_ID}"
    metadata["title"] = "G9 CUDA Image Channel Discovery Probe"
    metadata["code_file"] = SOURCE_NAME
    validate_metadata(metadata)
    return (json.dumps(metadata, sort_keys=True, indent=2) + "\n").encode("ascii")

def source_bytes(root: Path) -> bytes:
    probe = (root / "stage2_cuda_image_channel_probe.py").read_bytes()
    if digest(probe) != EXPECTED_SOURCE_SHA256:
        raise ValueError("stage2_cuda_image_channel_probe.py hash mismatch")
    return probe

def build_launcher(probe: bytes) -> bytes:
    b64 = base64.b64encode(probe).decode("ascii")
    text = LAUNCHER_TEMPLATE.format(sha256=EXPECTED_SOURCE_SHA256, b64=b64)
    return text.encode("ascii")

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kaggle-user", required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="existing empty absolute directory")
    args = parser.parse_args()

    output_dir = args.output_dir
    if not output_dir.is_absolute() or output_dir.is_symlink() or not output_dir.is_dir() or any(output_dir.iterdir()):
        parser.error("--output-dir must be an existing, empty, absolute directory and not a symlink")

    root = Path(__file__).resolve().parent
    try:
        metadata = build_metadata(args.kaggle_user)
        probe = source_bytes(root)
        launcher = build_launcher(probe)
    except ValueError as exc:
        print("FAIL:", exc, file=sys.stderr)
        return 1

    (output_dir / METADATA_NAME).write_bytes(metadata)
    (output_dir / SOURCE_NAME).write_bytes(launcher)

    summary = {
        "schema": "decisions_os/g9_cuda_image_channel_probe_kaggle_bundle/v1",
        "kernel_id": f"{args.kaggle_user}/{KERNEL_ID}",
        "output_dir": str(output_dir),
        "files_sha256": {
            METADATA_NAME: digest(metadata),
            SOURCE_NAME: digest(launcher),
        },
    }
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
