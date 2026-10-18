#!/usr/bin/env python3
"""Synthetic-only fixtures for the canonical Stage-2 CUDA input frame."""

from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import sys

if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
    raise SystemExit("PYTHONDONTWRITEBYTECODE=1 is required")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as core
from research.g9.cuda_qualification import stage2_cuda_input_frame as frame_api


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def refused(call, message: str) -> None:
    try:
        call()
    except frame_api.InputFrameError:
        return
    raise RuntimeError(message)


def main() -> None:
    payload = core.synthetic_payload()
    rows = [core.coefficient_row("row0"), core.coefficient_row("row1")]
    offsets_sha = hashlib.sha256(b"synthetic offset-table fixture identity").hexdigest()
    frame = frame_api.build_input_frame(payload, rows, offsets_sha)
    require(frame_api.validate_input_frame(frame) == frame, "valid frame did not round-trip")
    require(frame_api.require_expected_input(frame, payload, rows, offsets_sha) == frame["content_sha256"],
            "expected-input binding did not match")
    decoded_payload, decoded_rows = frame_api.decoded_inputs(frame)
    require(frame_api.build_input_frame(decoded_payload, decoded_rows, offsets_sha) == frame,
            "decoded input words did not rebuild the frame")
    raw = frame_api.canonical_bytes(frame)
    require(raw == frame_api.canonical_bytes(frame_api.validate_input_frame(frame)) and
            not raw.endswith(b"\n") and all(byte < 128 for byte in raw), "canonical bytes drift")
    require(frame["payload"]["mu"][0] == payload["mu"][0].hex(), "mu binary64 word drift")
    require(frame["payload"]["sigma"][7][12] == payload["sigma"][7][12].hex(),
            "sigma binary64 word drift")
    require(frame["coefficients"][1]["budget_linear"] == rows[1]["budget_linear"].hex(),
            "coefficient binary64 word drift")

    one = frame_api.build_input_frame(payload, rows[:1], offsets_sha)
    require(frame_api.validate_input_frame(one) == one and one != frame,
            "one-row frame was not distinct")
    refused(lambda: frame_api.build_input_frame(payload, [], offsets_sha), "zero rows accepted")
    refused(lambda: frame_api.build_input_frame(payload, rows + rows[:1], offsets_sha),
            "three rows accepted")
    refused(lambda: frame_api.build_input_frame(payload, rows, offsets_sha.upper()),
            "uppercase offset digest accepted")

    for field, replacement in (("mu", float.fromhex("0x1p-7").hex()),
                               ("prices", float.fromhex("0x1p+4").hex())):
        altered = copy.deepcopy(frame)
        altered["payload"][field][0] = replacement
        altered["content_sha256"] = frame_api.content_sha256(altered)
        if field == "mu":
            require(frame_api.validate_input_frame(altered) == altered, "valid changed mu refused")
        refused(lambda altered=altered: frame_api.require_expected_input(
            altered, payload, rows, offsets_sha), f"changed {field} accepted as expected")

    changed_row = copy.deepcopy(frame)
    changed_row["coefficients"][0]["alpha"] = float.fromhex("0x1p-2").hex()
    changed_row["content_sha256"] = frame_api.content_sha256(changed_row)
    require(frame_api.validate_input_frame(changed_row) == changed_row,
            "valid changed coefficient refused")
    refused(lambda: frame_api.require_expected_input(changed_row, payload, rows, offsets_sha),
            "changed coefficient accepted as expected")

    changed_offset = copy.deepcopy(frame)
    changed_offset["offsets_sha256"] = hashlib.sha256(b"different valid table, same lift total").hexdigest()
    changed_offset["content_sha256"] = frame_api.content_sha256(changed_offset)
    require(frame_api.validate_input_frame(changed_offset) == changed_offset,
            "valid alternate offset identity refused")
    refused(lambda: frame_api.require_expected_input(changed_offset, payload, rows, offsets_sha),
            "different offset identity accepted as expected")

    noncanonical = copy.deepcopy(frame)
    noncanonical["payload"]["mu"][0] = "-0x0p+0"
    noncanonical["content_sha256"] = frame_api.content_sha256(noncanonical)
    refused(lambda: frame_api.validate_input_frame(noncanonical),
            "noncanonical binary64 spelling accepted")
    bad_hash = copy.deepcopy(frame)
    bad_hash["content_sha256"] = hashlib.sha256(b"unrelated").hexdigest()
    refused(lambda: frame_api.validate_input_frame(bad_hash), "wrong frame hash accepted")
    bad_numeric = copy.deepcopy(frame)
    bad_numeric["payload"]["mu"][0] = "nan"
    bad_numeric["content_sha256"] = frame_api.content_sha256(bad_numeric)
    refused(lambda: frame_api.validate_input_frame(bad_numeric), "nonfinite payload accepted")
    bad_membership = copy.deepcopy(frame)
    bad_membership["payload"]["sectors"][0].reverse()
    bad_membership["content_sha256"] = frame_api.content_sha256(bad_membership)
    refused(lambda: frame_api.validate_input_frame(bad_membership), "unsorted sector accepted")

    signed_zero = copy.deepcopy(rows[0])
    signed_zero["alpha"] = -0.0
    unsigned_zero = copy.deepcopy(rows[0])
    unsigned_zero["alpha"] = 0.0
    require(frame_api.build_input_frame(payload, [signed_zero], offsets_sha)["content_sha256"] !=
            frame_api.build_input_frame(payload, [unsigned_zero], offsets_sha)["content_sha256"],
            "binary64 signed zero was not bound")
    print("PASS Stage-2 synthetic CUDA input-frame fixtures")


if __name__ == "__main__":
    main()
