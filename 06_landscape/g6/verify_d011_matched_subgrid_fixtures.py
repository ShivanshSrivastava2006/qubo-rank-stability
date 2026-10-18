#!/usr/bin/env python3
"""Hardware-free fixtures for the bounded D011 matched-subgrid comparator.

These fixtures use synthetic records only.  They neither read the Gate-5
corpus nor the D011 artifact, calculate an energy, or write a project output.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.g6 import d011_matched_subgrid as matched


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _raises(callable_: Any, expected: str) -> None:
    try:
        callable_()
    except matched.D011MatchedSubgridError:
        return
    raise RuntimeError(expected)


def _label(coordinate: tuple[int, int, int], offset: int = 0) -> str:
    return matched.LABELS[(sum(value // 5 for value in coordinate) + offset) % len(matched.LABELS)]


def _record(coordinate: tuple[int, int, int], *, offset: int = 0,
            r_hex: str = matched.PRIMARY_R_HEX, c_h: int = matched.PRIMARY_C_H) -> dict[str, Any]:
    return {
        "key": {
            "ell_card": coordinate[0],
            "ell_sector": coordinate[1],
            "ell_budget": coordinate[2],
            "r_hex": r_hex,
        },
        "unbalanced": {"set_label": _label(coordinate, offset), "tie_comparator": {"c_H": c_h}},
        "slack": {"set_label": _label(coordinate, offset + 1), "tie_comparator": {"c_H": c_h}},
    }


def _records() -> list[dict[str, Any]]:
    return [
        _record((card, sector, budget))
        for card in matched.PRIMARY_INDICES
        for sector in matched.PRIMARY_INDICES
        for budget in matched.PRIMARY_INDICES
    ]


def _walk(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return [item for child in value.values() for item in _walk(child)]
    if isinstance(value, list):
        return [item for child in value for item in _walk(child)]
    return [value]


def _source_checks() -> None:
    permitted = {
        "src.g6.d011_transition_output",
        "src.g6.ratified_g5_input",
        "src.g6.ledgers",
        "src.g6.d011_matched_subgrid",
    }
    for relative in ("src/g6/d011_matched_subgrid.py", "research/g6/make_d011_matched_subgrid_comparison.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
        _require(not any(isinstance(node, ast.Assert) for node in ast.walk(tree)),
                 f"assert found in {relative}")
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src.g6"):
                _require(node.module in permitted,
                         f"unexpected Gate-6 import boundary in {relative}: {node.module}")
            if isinstance(node, ast.Import) and any(alias.name.startswith("src.g5") for alias in node.names):
                raise RuntimeError(f"direct Gate-5 import in {relative}")
        _require("core_pass_output" not in source,
                 f"literal Gate-5 corpus path in {relative}")
    _require(hashlib.sha256((ROOT / matched.AUTHORIZATION_REL).read_bytes()).hexdigest()
             == matched.AUTHORIZATION_SHA256,
             "owner authorization pin drift")
    _require(hashlib.sha256((ROOT / matched.TRANSITION_REL / matched.TRANSITION_OUTPUT_FILENAME).read_bytes()).hexdigest()
             == matched.TRANSITION_OUTPUT_SHA256,
             "transition output pin drift")


def _selection_checks() -> None:
    records = _records()
    labels = matched._gate5_matched_primary_labels(records)
    _require(set(labels) == set(matched.ENCODINGS), "encoding set drift")
    _require(len(labels["unbalanced"]) == matched.MATCHED_COORDINATE_COUNT, "unbalanced selection size drift")
    _require(len(labels["slack"]) == matched.MATCHED_COORDINATE_COUNT, "slack selection size drift")
    _require(labels["unbalanced"][(0, 0, 0)] == _label((0, 0, 0)), "origin mapping drift")
    _require(labels["slack"][(12, 12, 12)] == _label((60, 60, 60), 1), "endpoint mapping drift")

    irrelevant = _record((0, 0, 0), r_hex="0x1.0000000000000p-1")
    _require(matched._gate5_matched_primary_labels(records + [irrelevant]) == labels,
             "non-r=1 record influenced the selected lattice")
    _raises(lambda: matched._gate5_matched_primary_labels(records[:-1]), "missing coordinate accepted")
    _raises(lambda: matched._gate5_matched_primary_labels(records + [records[0]]), "duplicate coordinate accepted")
    wrong_c_h = _records()
    wrong_c_h[0] = _record((0, 0, 0), c_h=1024)
    _raises(lambda: matched._gate5_matched_primary_labels(wrong_c_h), "wrong primary c_H accepted")
    bad_label = _records()
    bad_label[0]["unbalanced"]["set_label"] = "Z"
    _raises(lambda: matched._gate5_matched_primary_labels(bad_label), "invalid set label accepted")


def _metric_checks() -> None:
    gate5 = {(card, sector, budget): "A" for card in matched.COARSE_INDICES
             for sector in matched.COARSE_INDICES for budget in matched.COARSE_INDICES}
    d011 = dict(gate5)
    d011[(0, 0, 0)] = "B"
    d011[(12, 12, 12)] = "C"
    result = matched._comparison("unbalanced", gate5, d011)
    _require(result["accepted_gate5_r1"]["exact_integer_count_by_label"] == {
        "A": 2197, "B": 0, "C": 0
    }, "Gate-5 synthetic counts drift")
    _require(result["d011_companion_primary"]["exact_integer_count_by_label"] == {
        "A": 2195, "B": 1, "C": 1
    }, "D011 synthetic counts drift")
    _require(result["accepted_gate5_r1"]["rho_E_exact"] == {"numerator": 2197, "denominator": 2197},
             "exact reference rho drift")
    _require(result["d011_minus_gate5_rho_E_exact"] == {"numerator": -2, "denominator": 2197},
             "exact rho difference drift")
    _require(not any(isinstance(value, (float, bool)) for value in _walk(result)),
             "metric emitted a float or boolean")
    _raises(lambda: matched._fraction(True), "boolean numerator accepted")


def _publication_guard_checks() -> None:
    root = ROOT / "research/g6"
    _raises(lambda: matched._require_safe_output_dir(root), "research/g6 output root accepted")
    _raises(lambda: matched._require_safe_output_dir(ROOT / matched.TRANSITION_REL),
            "transition input directory accepted as output")
    _raises(lambda: matched._require_safe_output_dir(root / "a" / "b"), "nested output accepted")
    candidate = root / ".fixture-d011-matched-subgrid-output"
    _require(not candidate.exists(), "fixture target unexpectedly exists")
    _require(matched._require_safe_output_dir(candidate) == candidate,
             "dedicated direct child output refused")


def main() -> int:
    _source_checks()
    _selection_checks()
    _metric_checks()
    _publication_guard_checks()
    print("PASS D011 matched-subgrid fixtures; no Gate-5 corpus read or project output write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
