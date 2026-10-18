#!/usr/bin/env python3
"""Build the non-scientific Gate-9 API GPU probe bundle offline.

No Kaggle import or call exists here. --plan is read-only. --build writes exactly
two files into an explicitly supplied, existing, empty directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


APPROVED_UI_DRAFT_SHA256 = (
    "13034e40a4f4ebfa5f22d364920dfe0773f03c4e5aeea9ae2f4c60c28295ac65"
)
PINNED_SOURCE_SHA256 = (
    "b0aa74f3ff1710e9eecae40cc077c031ea39689da433672ede4fc22c29841bff"
)
KERNEL_ID = "shivanshsrivastava06/g9-gpu-allocation-api-probe-v1"
SOURCE_NAME = "g9_gpu_allocation_api_probe.py"
METADATA_NAME = "kernel-metadata.json"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_bytes() -> bytes:
    draft = Path(__file__).resolve().with_name(
        "GATE_9_KAGGLE_GPU_ALLOCATION_PROBE_DRAFT.md"
    ).read_bytes()
    if digest(draft) != APPROVED_UI_DRAFT_SHA256:
        raise ValueError("approved UI probe draft hash changed")
    lines = draft.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line == b"```python\n"]
    if len(starts) != 1:
        raise ValueError("expected exactly one fenced Python cell")
    start = starts[0] + 1
    try:
        end = next(i for i in range(start, len(lines)) if lines[i] == b"```\n")
    except StopIteration as exc:
        raise ValueError("missing closing Python fence") from exc
    source = b"".join(lines[start:end])
    if digest(source) != PINNED_SOURCE_SHA256:
        raise ValueError("pinned probe cell hash changed")
    return source


def metadata_bytes() -> bytes:
    metadata = {
        "id": KERNEL_ID,
        "title": "G9 GPU Allocation API Probe V1",
        "code_file": SOURCE_NAME,
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": False,
        "machine_shape": "NvidiaTeslaT4",
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    return (json.dumps(metadata, sort_keys=True, indent=2) + "\n").encode("ascii")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="print hashes; write nothing")
    mode.add_argument("--build", action="store_true", help="write the two bundle files")
    parser.add_argument("--output-dir", type=Path, help="existing empty absolute directory")
    args = parser.parse_args()
    source = source_bytes()
    metadata = metadata_bytes()
    plan = {
        "kernel_id": KERNEL_ID,
        "source_name": SOURCE_NAME,
        "source_sha256": digest(source),
        "metadata_name": METADATA_NAME,
        "metadata_sha256": digest(metadata),
        "submitted_docker_image_key": False,
        "kaggle_call": False,
    }
    if args.plan:
        if args.output_dir is not None:
            parser.error("--plan does not accept --output-dir")
        print(json.dumps(plan, sort_keys=True))
        return
    if args.output_dir is None or not args.output_dir.is_absolute():
        parser.error("--build requires an absolute --output-dir")
    output_dir = args.output_dir
    if output_dir.is_symlink() or not output_dir.is_dir():
        parser.error("--output-dir must be an existing non-symlink directory")
    if any(output_dir.iterdir()):
        parser.error("--output-dir must be empty")
    with (output_dir / SOURCE_NAME).open("xb") as handle:
        handle.write(source)
    with (output_dir / METADATA_NAME).open("xb") as handle:
        handle.write(metadata)
    print(json.dumps({**plan, "output_dir": str(output_dir)}, sort_keys=True))


if __name__ == "__main__":
    main()
