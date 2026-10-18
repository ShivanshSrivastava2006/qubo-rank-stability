"""Validation contract for the eventual, non-scientific Stage-2 generation ledger.

There is deliberately no filesystem writer here.  The contract validates an
in-memory ledger only; fixtures use artificial prices and partitions.  The
future authorized writer must emit a canonical ledger that this module accepts
before any instance manifest is consumed downstream.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

from research.g9 import stage2_generator as generator


SCHEMA = "decisions_os/g9_stage2_generation_ledger/v1"
PROTOCOL_FILE_SHA256 = "8a5785fd6d495f548ebd94d61fac9aab9986413c2c1d2b0a7528500fd86635d0"
REJECTION_CODES = (
    "partition_matches_stage1",
    "partition_matches_earlier_accepted",
    "feasible_set_below_100",
)


class GenerationContractError(ValueError):
    """Typed refusal for a malformed or non-reproducible generation ledger."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GenerationContractError(message)


def _int(value: object, label: str) -> int:
    _require(type(value) is int, f"{label} must be an int")
    return value


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def content_sha256(payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    body.pop("content_sha256", None)
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def _no_float_or_bool(value: object) -> None:
    if type(value) in (float, bool):
        raise GenerationContractError("generation ledger may not carry float or bool leaves")
    if isinstance(value, dict):
        for nested in value.values():
            _no_float_or_bool(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _no_float_or_bool(nested)


def _sha(value: object, label: str) -> str:
    _require(type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value),
             f"{label} must be lowercase SHA-256")
    return value


def _seed_payload(seed: generator.StreamSeed) -> dict[str, object]:
    return {
        "material_ascii": seed.material_ascii,
        "material_sha256": seed.material_sha256,
        "seed_uint128_decimal": str(seed.seed_uint128),
    }


def _validate_seed(payload: object, expected: generator.StreamSeed, label: str) -> None:
    _require(isinstance(payload, dict) and set(payload) == {"material_ascii", "material_sha256", "seed_uint128_decimal"},
             f"{label} has wrong key set")
    _require(payload == _seed_payload(expected), f"{label} does not reproduce the U-08 commitment")


@dataclass(frozen=True)
class ScreeningInputs:
    """Fixed non-scientific inputs required to replay U-10/U-11 exactly."""

    prices: Sequence[object]
    K: object
    C: object
    B: object
    stage1_partition: Sequence[Sequence[object]]


def attempt_payload(screen: generator.AttemptScreen) -> dict[str, object]:
    """Render one replayable non-scientific attempt record for a future writer."""
    return {
        "slot": screen.slot,
        "attempt": screen.attempt,
        "returns_seed": _seed_payload(screen.returns_seed),
        "sectors_seed": _seed_payload(screen.sectors_seed),
        "partition_sha256": screen.partition_sha256,
        "feasible_count": screen.feasible_count,
        "outcome": "accepted" if screen.accepted else "rejected",
        "rejection_codes": list(screen.rejection_codes),
    }


def build_synthetic_ledger(attempts: Sequence[generator.AttemptScreen], generator_source_sha256: str) -> dict[str, object]:
    """Fixture helper only; production must use an approved atomic writer."""
    payload: dict[str, object] = {
        "schema": SCHEMA,
        "protocol_file_sha256": PROTOCOL_FILE_SHA256,
        "generator_source_sha256": _sha(generator_source_sha256, "generator source hash"),
        "attempts": [attempt_payload(item) for item in attempts],
        "scientific_outputs": "intentionally absent",
    }
    payload["content_sha256"] = content_sha256(payload)
    return payload


def validate_generation_ledger(payload: object, inputs: ScreeningInputs, generator_source_sha256: str) -> dict[str, object]:
    """Fail closed unless five slots replay as the exact first-valid U-08--U-11 sequence."""
    _require(isinstance(payload, dict), "generation ledger must be an object")
    _require(set(payload) == {"schema", "protocol_file_sha256", "generator_source_sha256", "attempts", "scientific_outputs", "content_sha256"},
             "generation ledger has wrong key set")
    _require(payload["schema"] == SCHEMA, "generation ledger schema mismatch")
    _require(payload["protocol_file_sha256"] == PROTOCOL_FILE_SHA256, "protocol identity mismatch")
    _require(payload["generator_source_sha256"] == _sha(generator_source_sha256, "expected generator source hash"),
             "generator source identity mismatch")
    _require(payload["scientific_outputs"] == "intentionally absent", "ledger scope statement mismatch")
    _require(payload["content_sha256"] == content_sha256(payload), "generation ledger content hash mismatch")
    _no_float_or_bool(payload)
    attempts = payload["attempts"]
    _require(isinstance(attempts, list), "attempt list must be a list")
    accepted_partitions: list[tuple[tuple[int, ...], ...]] = []
    cursor = 0
    accepted: list[dict[str, object]] = []
    expected_keys = {"slot", "attempt", "returns_seed", "sectors_seed", "partition_sha256", "feasible_count", "outcome", "rejection_codes"}
    for slot in range(1, generator.SLOT_COUNT + 1):
        found = False
        for attempt in range(generator.MAX_ATTEMPT + 1):
            _require(cursor < len(attempts), f"slot {slot} has no terminal accepted attempt")
            row = attempts[cursor]
            cursor += 1
            _require(isinstance(row, dict) and set(row) == expected_keys, f"slot {slot} attempt {attempt}: wrong key set")
            _require(_int(row["slot"], "slot") == slot and _int(row["attempt"], "attempt") == attempt,
                     f"attempt ordering drift at slot {slot}")
            _validate_seed(row["returns_seed"], generator.stream_seed(slot, attempt, "returns"), "returns seed")
            _validate_seed(row["sectors_seed"], generator.stream_seed(slot, attempt, "sectors"), "sectors seed")
            replay = generator.screen_attempt(
                prices=inputs.prices, K=inputs.K, C=inputs.C, B=inputs.B,
                stage1_partition=inputs.stage1_partition,
                earlier_accepted_partitions=accepted_partitions, slot=slot, attempt=attempt,
            )
            _require(_sha(row["partition_sha256"], "partition hash") == replay.partition_sha256,
                     f"slot {slot} attempt {attempt}: partition digest mismatch")
            _require(_int(row["feasible_count"], "feasible count") == replay.feasible_count,
                     f"slot {slot} attempt {attempt}: feasibility count mismatch")
            _require(isinstance(row["rejection_codes"], list) and tuple(row["rejection_codes"]) == replay.rejection_codes
                     and all(code in REJECTION_CODES for code in row["rejection_codes"]),
                     f"slot {slot} attempt {attempt}: rejection codes mismatch")
            outcome = "accepted" if replay.accepted else "rejected"
            _require(row["outcome"] == outcome, f"slot {slot} attempt {attempt}: outcome mismatch")
            if replay.accepted:
                accepted_partitions.append(replay.normalized_partition)
                accepted.append({"instance_id": f"stage2_{slot:02d}", "slot": slot, "attempt": attempt,
                                 "partition_sha256": replay.partition_sha256, "feasible_count": replay.feasible_count})
                found = True
                break
        _require(found, f"slot {slot} exceeded the approved attempt cap")
    _require(cursor == len(attempts), "attempt ledger contains rows after the fifth accepted slot")
    return {
        "verdict": "accepted",
        "slot_count": generator.SLOT_COUNT,
        "attempt_count": len(attempts),
        "accepted_instances": accepted,
        "ledger_content_sha256": payload["content_sha256"],
    }
