#!/usr/bin/env python3
"""Build the offline Kaggle bundle for the Gate-9 API-launched GPU allocation probe.

Standard library only.  This tool never contacts Kaggle, never reads or writes
Kaggle credentials, never runs nvcc or a GPU, never creates a kernel and never
pushes.  It imports no network and no subprocess module, so it has no such
capability at all.

It reads the pinned probe draft
`research/g9/kaggle_dry_run/GATE_9_KAGGLE_GPU_ALLOCATION_PROBE_DRAFT.md`,
extracts its single fenced ``python`` block -- the reviewed section-4 probe cell
-- byte for byte, and refuses unless both the draft and the extracted cell hash
to their pinned values.  The draft remains the sole authority for the cell: no
copy of it is embedded in this file, and it is written nowhere except into the
operator-chosen staging directory, because section 7.1 of the draft forbids
sidecar copies of the cell.

Two modes, exactly one per invocation:
  --plan            pure.  Prints the planned bundle, its hashes and the planned
                    (NOT executed) CLI command.  Writes nothing, anywhere.
  --output-dir DIR  builds into a new or empty directory outside the project
                    tree and prints the written files' SHA-256 values.

Build-mode outputs, two files and nothing else:
  kernel-metadata.json         private Python `script` kernel, enable_gpu true,
                               machine_shape NvidiaTeslaT4, internet off, no
                               sources, and no docker_image or
                               docker_image_pinning_type key of any kind
  g9_gpu_allocation_probe.py   exactly the pinned section-4 probe cell bytes

Building is not launching.  `kaggle kernels push -p DIR` on the locally
installed CLI 2.2.4 starts a session immediately (the v2 README records that
`--no-run` is not offered there), so the single owner-gated push is also the
single run.  This tool never issues it and prints it only as text.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]

BUNDLE_SCHEMA = "decisions_os/g9_gpu_allocation_probe_api_bundle/v1"

# The reviewed probe draft, pinned by hash.  It is the single authority for the
# probe cell (draft section 7.1); this builder copies nothing out of it except
# into the operator's staging directory.
DRAFT_REL = "research/g9/kaggle_dry_run/GATE_9_KAGGLE_GPU_ALLOCATION_PROBE_DRAFT.md"
DRAFT_SHA256 = "13034e40a4f4ebfa5f22d364920dfe0773f03c4e5aeea9ae2f4c60c28295ac65"
# Draft section 7.1's two pinned values for the section-4 cell.
CELL_SHA256_FULL = "b0aa74f3ff1710e9eecae40cc077c031ea39689da433672ede4fc22c29841bff"
CELL_SHA256_WITHOUT_TERMINAL_LF = "7d2fa191388e93aa105364dae39150cd9d980a29d1214ad7d34fde12f39c8014"
FENCE_OPEN = b"```python"
FENCE_CLOSE = b"```"

# Kaggle prepends exactly this 12-byte marker to a pulled `script` source; both
# v2 pulls showed it (V2 version-2 outcome, "Source identity").  Recorded here
# only to predict the pulled hash for the offline identity check; the prediction
# is an expectation, not a guarantee.
KAGGLE_SCRIPT_CELL_MARKER = b"# %% [code]\n"

# Spent kernels.  The new slug must differ from every one of them, and none of
# them is ever addressed, copied, forked or re-versioned.
SPENT_KERNEL_SLUGS = frozenset({
    "g9-cuda-core-nonscientific-dry-run-50f25827",
    "g9-cuda-core-nonscientific-dry-run-v2-50f25827",
})
KERNEL_SLUG = "g9-gpu-allocation-probe-api-" + CELL_SHA256_FULL[:8]
KERNEL_TITLE = "G9 GPU Allocation Probe API " + CELL_SHA256_FULL[:8]
CODE_FILE = "g9_gpu_allocation_probe.py"
METADATA_FILE = "kernel-metadata.json"

ACCELERATOR_MACHINE_SHAPE = "NvidiaTeslaT4"  # official docs: GPU T4 x2
# Deliberately absent from the emitted metadata.  The draft's whole point is to
# remove the image pin as a variable, and the pinning-type field's interaction
# with a first push is not established (v2 README).
FORBIDDEN_METADATA_KEYS = frozenset({"docker_image", "docker_image_pinning_type"})

# Planned, never executed.  Printed as text so a reviewer can read the exact
# command before deciding.  Without --no-run this push is also the run.
PLANNED_CLI_COMMAND = ("kaggle", "kernels", "push", "-p")

# Kaggle usernames as they appear in kernel URLs: lowercase alphanumerics with
# single interior hyphens.  Deliberately stricter than necessary.
USER_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9]|-(?=[a-z0-9])){0,48}")


class BundleError(RuntimeError):
    """The bundle cannot be produced safely."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BundleError(message)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_kaggle_user(value: str) -> str:
    _require(type(value) is str and USER_PATTERN.fullmatch(value) is not None,
             "--kaggle-user must be a lowercase Kaggle username slug")
    return value


def fenced_python_blocks(text: bytes) -> list[bytes]:
    """Every ```python fenced block, each reassembled with one terminal LF."""
    blocks: list[bytes] = []
    current: list[bytes] = []
    inside = False
    for line in text.split(b"\n"):
        if not inside:
            if line == FENCE_OPEN:
                inside, current = True, []
        elif line == FENCE_CLOSE:
            inside = False
            blocks.append(b"\n".join(current) + b"\n")
            current = []
        else:
            current.append(line)
    _require(not inside, "the pinned draft has an unterminated fenced block")
    return blocks


def load_probe_cell(root: Path = ROOT) -> bytes:
    """Return the reviewed section-4 probe cell bytes, or refuse.

    Refuses on any drift in the draft or the cell, so the bundle can only ever
    carry the reviewed bytes.
    """
    path = root / DRAFT_REL
    _require(not path.is_symlink() and path.is_file(), "the pinned probe draft is missing")
    draft = path.read_bytes()
    _require(_sha(draft) == DRAFT_SHA256,
             "probe draft hash differs from the reviewed draft; stop and re-review")
    blocks = fenced_python_blocks(draft)
    _require(len(blocks) == 1,
             f"expected exactly one fenced python block in the draft, found {len(blocks)}")
    cell = blocks[0]
    _require(_sha(cell) == CELL_SHA256_FULL,
             "extracted probe cell does not match the pinned full_with_terminal_lf hash")
    _require(cell.endswith(b"\n") and _sha(cell[:-1]) == CELL_SHA256_WITHOUT_TERMINAL_LF,
             "extracted probe cell does not match the pinned without_one_terminal_lf hash")
    return cell


def build_metadata(kaggle_user: str) -> bytes:
    """The kernel metadata bytes.  A pure function of --kaggle-user."""
    validate_kaggle_user(kaggle_user)
    _require(KERNEL_SLUG not in SPENT_KERNEL_SLUGS,
             "kernel slug collides with a spent kernel")
    metadata = {
        "id": f"{kaggle_user}/{KERNEL_SLUG}",
        "title": KERNEL_TITLE,
        "code_file": CODE_FILE,
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": False,
        "machine_shape": ACCELERATOR_MACHINE_SHAPE,
        "keywords": [],
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    _require(not FORBIDDEN_METADATA_KEYS & set(metadata),
             "metadata must not pin an image or a pinning type")
    return (json.dumps(metadata, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("ascii")


def build_bundle(kaggle_user: str, root: Path = ROOT) -> dict[str, bytes]:
    """Return {filename: bytes} for the two-file bundle.  Pure; writes nothing."""
    cell = load_probe_cell(root)
    metadata = build_metadata(kaggle_user)
    _require(json.loads(metadata)["code_file"] == CODE_FILE, "code_file disagrees with the bundle")
    return {METADATA_FILE: metadata, CODE_FILE: cell}


def plan(kaggle_user: str, root: Path = ROOT) -> dict:
    """The reviewable plan.  Pure: reads the pinned draft and writes nothing."""
    bundle = build_bundle(kaggle_user, root)
    cell = bundle[CODE_FILE]
    return {
        "schema": BUNDLE_SCHEMA,
        "mode": "plan",
        "writes": "nothing",
        "pinned_draft": {"path": DRAFT_REL, "sha256": DRAFT_SHA256},
        "probe_cell": {
            "source": "the single fenced python block of the pinned draft, section 4",
            "bytes": len(cell),
            "sha256_full_with_terminal_lf": _sha(cell),
            "sha256_without_one_terminal_lf": _sha(cell[:-1]),
            "copied_into_repository": False,
            "edited": False,
        },
        "kernel_id": json.loads(bundle[METADATA_FILE])["id"],
        "kernel_slug": KERNEL_SLUG,
        "spent_kernel_slugs_never_addressed": sorted(SPENT_KERNEL_SLUGS),
        "metadata": json.loads(bundle[METADATA_FILE]),
        "metadata_keys_absent": sorted(FORBIDDEN_METADATA_KEYS),
        "files_sha256": {name: _sha(data) for name, data in sorted(bundle.items())},
        "expected_pulled_source_sha256": _sha(KAGGLE_SCRIPT_CELL_MARKER + cell),
        "expected_pulled_source_note": (
            "prediction only: Kaggle prepended the 12-byte marker "
            + repr(KAGGLE_SCRIPT_CELL_MARKER)
            + " to both v2 script pulls.  A mismatch is an identity finding, not a retry trigger."
        ),
        "planned_cli_command": list(PLANNED_CLI_COMMAND) + ["<output-dir>"],
        "cli_command_executed": False,
        "cli_command_warning": (
            "this push starts the single session immediately; CLI 2.2.4 offers no --no-run"
        ),
        "attempt_cap": "exactly one push, which is exactly one run; no retry under any outcome",
        "pushed": False,
        "kaggle_contacted": False,
        "credentials_read": False,
        "compilation_performed": False,
        "authorizes": "nothing",
    }


def _prepare_output_dir(raw: str, root: Path = ROOT) -> Path:
    _require(bool(raw), "--output-dir must be explicit")
    target = Path(raw).expanduser().absolute()
    _require(not target.is_symlink(), "--output-dir must not be a symlink")
    resolved = target.resolve()
    _require(resolved != root and root not in resolved.parents,
             "--output-dir must be outside the project tree")
    if target.exists():
        _require(target.is_dir() and not any(target.iterdir()),
                 "--output-dir must be a new or empty directory")
    else:
        _require(target.parent.is_dir(), "--output-dir parent must exist")
        target.mkdir()
    return target


def write_bundle(bundle: dict[str, bytes], target: Path) -> None:
    for name, data in sorted(bundle.items()):
        with open(target / name, "xb") as handle:
            handle.write(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline Gate-9 API-launched GPU allocation probe bundle (never pushes)")
    parser.add_argument("--kaggle-user", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true",
                      help="print the plan and its hashes; write nothing")
    mode.add_argument("--output-dir",
                      help="new or empty directory outside the project tree to build into")
    args = parser.parse_args(argv)
    try:
        if args.plan:
            report = plan(args.kaggle_user)
        else:
            bundle = build_bundle(args.kaggle_user)
            target = _prepare_output_dir(args.output_dir)
            write_bundle(bundle, target)
            report = plan(args.kaggle_user)
            report["mode"] = "build"
            report["writes"] = "exactly the two bundle files, in --output-dir"
            report["output_dir"] = str(target)
            report["planned_cli_command"] = list(PLANNED_CLI_COMMAND) + [str(target)]
    except BundleError as exc:
        print("FAIL bundle: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
