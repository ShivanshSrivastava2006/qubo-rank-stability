"""Canonical, non-writing input frame for a future Stage-2 CUDA bridge.

The frame binds the exact binary64 payload, one or two coefficient records,
and the immutable slack-offset-table SHA-256. It contains no result and does
not run a kernel. A future device runner must construct its C++ input from
this validated frame, verify the computed offset table, and put this frame's
content hash inside the returned result. Merely echoing the hash is not proof
that a kernel consumed the frame; that integration remains to be built.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence

from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as core


SCHEMA = "decisions_os/g9_cuda_core_input_frame/v1"
PAYLOAD_FIELDS = ("mu", "sigma", "prices", "kappa_risk", "k", "c", "b", "lambda_ref", "sectors")
SCALAR_FIELDS = ("kappa_risk", "k", "c", "b", "lambda_ref")
FRAME_FIELDS = frozenset({"schema", "payload", "coefficients", "offsets_sha256", "content_sha256"})


class InputFrameError(ValueError):
    """A frame or its expected binding is malformed or inconsistent."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InputFrameError(message)


def _sha256(value: object, label: str) -> str:
    _require(type(value) is str and len(value) == 64 and
             all(character in "0123456789abcdef" for character in value),
             f"{label} must be a lowercase SHA-256")
    return value


def canonical_bytes(value: Mapping[str, object]) -> bytes:
    """ASCII JSON, sorted keys, compact separators, and no trailing newline."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def content_sha256(value: Mapping[str, object]) -> str:
    body = dict(value)
    body.pop("content_sha256", None)
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def _payload_words(payload: Mapping[str, object]) -> dict[str, object]:
    try:
        normalized = core.validate_payload(payload)
    except (core.CoreStreamEngineError, TypeError, ValueError, OverflowError) as exc:
        raise InputFrameError("invalid core payload") from exc
    words: dict[str, object] = {
        "mu": [value.hex() for value in normalized["mu"]],
        "sigma": [[value.hex() for value in row] for row in normalized["sigma"]],
        "prices": [value.hex() for value in normalized["prices"]],
        "sectors": [list(block) for block in normalized["sectors"]],
    }
    for name in SCALAR_FIELDS:
        words[name] = normalized[name].hex()
    return words


def _coefficient_words(records: Sequence[Mapping[str, object]]) -> list[dict[str, str]]:
    _require(isinstance(records, Sequence) and not isinstance(records, (str, bytes)) and
             1 <= len(records) <= 2, "exactly one or two coefficient records are required")
    result = []
    for record in records:
        try:
            normalized = core.coefficient_record(record)
        except (core.CoreStreamEngineError, TypeError, ValueError, OverflowError) as exc:
            raise InputFrameError("invalid coefficient record") from exc
        result.append({name: normalized[name].hex() for name in core.COEFFICIENT_FIELDS})
    return result


def build_input_frame(payload: Mapping[str, object], records: Sequence[Mapping[str, object]],
                      offsets_sha256: str) -> dict[str, object]:
    """Freeze exact input words and the separately computed offset identity."""
    frame: dict[str, object] = {
        "schema": SCHEMA,
        "payload": _payload_words(payload),
        "coefficients": _coefficient_words(records),
        "offsets_sha256": _sha256(offsets_sha256, "offset-table identity"),
    }
    frame["content_sha256"] = content_sha256(frame)
    return frame


def _hex_word(value: object, label: str) -> float:
    _require(type(value) is str, f"{label} must be a hexadecimal binary64 word")
    try:
        decoded = float.fromhex(value)
    except (ValueError, OverflowError) as exc:
        raise InputFrameError(f"{label} is not a hexadecimal binary64 word") from exc
    _require(decoded.hex() == value, f"{label} is not in canonical binary64 spelling")
    return decoded


def validate_input_frame(frame: object) -> dict[str, object]:
    """Reject noncanonical frames, including hash-consistent malformed edits."""
    _require(type(frame) is dict and set(frame) == FRAME_FIELDS, "input frame has wrong key set")
    _require(frame["schema"] == SCHEMA, "input-frame schema mismatch")
    _sha256(frame["content_sha256"], "input-frame content hash")
    _sha256(frame["offsets_sha256"], "offset-table identity")
    encoded = frame["payload"]
    _require(type(encoded) is dict and set(encoded) == set(PAYLOAD_FIELDS),
             "encoded payload has wrong key set")
    _require(type(encoded["mu"]) is list and type(encoded["sigma"]) is list and
             type(encoded["prices"]) is list and type(encoded["sectors"]) is list,
             "encoded payload arrays must be lists")
    _require(all(type(row) is list for row in encoded["sigma"]),
             "encoded covariance rows must be lists")
    decoded: dict[str, object] = {
        "mu": [_hex_word(value, "mu") for value in encoded["mu"]],
        "sigma": [[_hex_word(value, "sigma") for value in row] for row in encoded["sigma"]],
        "prices": [_hex_word(value, "price") for value in encoded["prices"]],
        "sectors": encoded["sectors"],
    }
    for name in SCALAR_FIELDS:
        decoded[name] = _hex_word(encoded[name], name)
    rows = frame["coefficients"]
    _require(type(rows) is list and 1 <= len(rows) <= 2, "encoded row count must be one or two")
    decoded_rows = []
    for row in rows:
        _require(type(row) is dict and set(row) == set(core.COEFFICIENT_FIELDS),
                 "encoded coefficient fields mismatch")
        decoded_rows.append({name: _hex_word(row[name], name) for name in core.COEFFICIENT_FIELDS})
    rebuilt = build_input_frame(decoded, decoded_rows, frame["offsets_sha256"])
    _require(frame == rebuilt, "input frame is not canonical or its hash is wrong")
    return rebuilt


def require_expected_input(frame: object, payload: Mapping[str, object],
                           records: Sequence[Mapping[str, object]], offsets_sha256: str) -> str:
    """Compare a received frame to the caller's separately validated inputs."""
    validated = validate_input_frame(frame)
    expected = build_input_frame(payload, records, offsets_sha256)
    _require(validated == expected, "input frame does not match expected payload, rows, or offsets")
    return validated["content_sha256"]


def decoded_inputs(frame: object) -> tuple[dict[str, object], list[dict[str, float]]]:
    """Return the exact validated words that a compiled core must consume."""
    validated = validate_input_frame(frame)
    encoded = validated["payload"]
    payload: dict[str, object] = {
        "mu": [float.fromhex(value) for value in encoded["mu"]],
        "sigma": [[float.fromhex(value) for value in row] for row in encoded["sigma"]],
        "prices": [float.fromhex(value) for value in encoded["prices"]],
        "sectors": [list(block) for block in encoded["sectors"]],
    }
    for name in SCALAR_FIELDS:
        payload[name] = float.fromhex(encoded[name])
    records = [{name: float.fromhex(row[name]) for name in core.COEFFICIENT_FIELDS}
               for row in validated["coefficients"]]
    return payload, records
