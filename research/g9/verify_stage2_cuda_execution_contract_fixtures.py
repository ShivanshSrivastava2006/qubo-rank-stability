#!/usr/bin/env python3
"""Synthetic fixtures for the Stage-2 CUDA qualification/range control plane."""
from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9.cuda_qualification import stage2_cuda_execution_contract as c  # noqa: E402


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def rejected(action, label: str) -> None:
    try:
        action()
    except c.CUDAExecutionContractError:
        return
    except Exception as exc:
        raise FixtureError(f"{label}: raw {type(exc).__name__}") from exc
    raise FixtureError(f"{label}: accepted")


def reseal(payload: dict) -> None:
    payload["content_sha256"] = c.content_sha256(payload)


def identity() -> dict:
    return c.qualification_identity(
        {"gpu_name": "synthetic NVIDIA", "compute_capability": "9.9", "cuda_driver_version": "1",
         "cuda_runtime_version": "1", "nvcc_version": "1", "kaggle_image": "synthetic",
         "python_version": "3.12.3", "numpy_version": "2.4.4"},
        {"research/g9/cuda_qualification/synthetic.cu": hashlib.sha256(b"synthetic source").hexdigest()},
        ("-std=c++17", "-O0", "--fmad=false"),
    )


def main() -> int:
    qualification = identity()
    identity_hash = c.validate_qualification_identity(qualification)
    rejected(lambda: c.qualification_identity({**qualification["platform"], "device_uuid": "transient"}, qualification["source_sha256"], qualification["compiler_flags"]),
             "transient device identifier")
    bad_identity = copy.deepcopy(qualification)
    bad_identity["platform"]["gpu_name"] = "other"
    reseal(bad_identity)
    # A fully canonical changed platform is a distinct identity, not malformed;
    # the sealed range plan below is what refuses it from this output family.
    require(c.validate_qualification_identity(bad_identity) != identity_hash, "platform drift did not change identity")
    rejected(lambda: c.qualification_identity(qualification["platform"], qualification["source_sha256"], ("-O0", "-O0")),
             "duplicated compiler flags")

    plan = c.build_range_plan("primary", 10_001, identity_hash)
    checked = c.validate_range_plan(plan)
    require([(row["start"], row["stop"]) for row in checked["ranges"]] == [(0, 4096), (4096, 8192), (8192, 10001)],
            "range partition drift")
    bad_plan = copy.deepcopy(plan)
    bad_plan["ranges"][1]["start"] = 4095
    reseal(bad_plan)
    rejected(lambda: c.validate_range_plan(bad_plan), "rehashed range overlap")

    manifests = [c.complete_range_manifest(plan, row["batch_id"], hashlib.sha256(f"file{i}".encode()).hexdigest(),
                                          hashlib.sha256(f"content{i}".encode()).hexdigest(), identity_hash)
                 for i, row in enumerate(plan["ranges"])]
    receipt = c.validate_final_manifests(plan, manifests)
    require(receipt["verdict"] == "accepted" and receipt["batch_count"] == 3 and receipt["total_coordinates"] == 10001,
            "completed exact cover rejected")
    for label, mutate in (
        ("missing range", lambda rows: rows.pop()),
        ("duplicate range", lambda rows: rows.append(copy.deepcopy(rows[0]))),
        ("mixed identity", lambda rows: rows[0].__setitem__("qualification_identity_sha256", "0" * 64)),
        ("range drift", lambda rows: rows[0].__setitem__("stop", 4095)),
        ("extra field", lambda rows: rows[0].__setitem__("extra", 1)),
        ("float field", lambda rows: rows[0].__setitem__("start", 0.0)),
    ):
        bad = copy.deepcopy(manifests)
        mutate(bad)
        for row in bad:
            if isinstance(row, dict) and "content_sha256" in row:
                reseal(row)
        rejected(lambda bad=bad: c.validate_final_manifests(plan, bad), label)
    require(not (ROOT / "research/g9/stage2_generation").exists(), "fixtures must not create a Stage-2 output")
    print("PASS Stage-2 CUDA execution-contract fixtures; synthetic qualification/range metadata only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
