"""Read a frozen G4 coefficient ledger; do not recreate parameters ad hoc."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class Coefficients:
    alpha: float
    sector_slack: float
    budget_slack: float
    sector_linear: float
    sector_quadratic: float
    budget_linear: float
    budget_quadratic: float

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and strictly positive")


def _load_ledger(ledger_path: str | Path) -> dict[str, object]:
    ledger = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    content = dict(ledger)
    expected_digest = content.pop("content_sha256", None)
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    if not isinstance(expected_digest, str) or hashlib.sha256(encoded).hexdigest() != expected_digest:
        raise ValueError("G4 ledger content digest does not validate")
    if ledger.get("schema") != "g4-primary-coordinate-coefficient-ledger/v1":
        raise ValueError("unexpected G4 ledger schema")
    if ledger.get("grid_rule") != {"q_min": -4, "q_max": 2, "P": 10, "N_axis": 61}:
        raise ValueError("unexpected G4 primary grid rule")
    return ledger


def _row(rows: object, index: int) -> dict[str, object]:
    if not isinstance(index, int) or not isinstance(rows, list) or index < 0 or index >= len(rows):
        raise ValueError("invalid G4 ledger coordinate index")
    row = rows[index]
    if not isinstance(row, dict) or row.get("index") != index:
        raise ValueError("misaligned G4 ledger row")
    return row


def _positive_hex(row: dict[str, object], key: str) -> float:
    value = row.get(key)
    if not isinstance(value, str):
        raise ValueError(f"missing {key} in G4 ledger row")
    parsed = float.fromhex(value)
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise ValueError(f"{key} must be finite and strictly positive")
    return parsed


def load_coordinate(ledger_path: str | Path, index: int) -> float:
    ledger = _load_ledger(ledger_path)
    row = _row(ledger.get("coordinates"), index)
    return _positive_hex(row, "binary64_hex")


def load_coefficients(ledger_path: str | Path, card_index: int, sector_index: int,
                      budget_index: int) -> Coefficients:
    ledger = _load_ledger(ledger_path)
    coefficient_ledger = ledger.get("coefficient_ledger")
    if not isinstance(coefficient_ledger, dict):
        raise ValueError("missing G4 coefficient ledger")
    card = _row(coefficient_ledger.get("cardinality"), card_index)
    sector = _row(coefficient_ledger.get("sector"), sector_index)
    budget = _row(coefficient_ledger.get("budget"), budget_index)
    return Coefficients(
        alpha=_positive_hex(card, "alpha_hex"),
        sector_slack=_positive_hex(sector, "lambda_slack_hex"),
        budget_slack=_positive_hex(budget, "lambda_slack_hex"),
        sector_linear=_positive_hex(sector, "lambda_1_hex"),
        sector_quadratic=_positive_hex(sector, "lambda_2_hex"),
        budget_linear=_positive_hex(budget, "lambda_1_hex"),
        budget_quadratic=_positive_hex(budget, "lambda_2_hex"),
    )
