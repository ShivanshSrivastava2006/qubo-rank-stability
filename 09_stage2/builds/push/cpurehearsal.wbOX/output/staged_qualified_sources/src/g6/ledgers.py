"""Pre-execution coordinate and coefficient ledgers for Gate 6.

The functions here bind input bit patterns only.  They neither enumerate an
encoded domain nor derive a tie set, label, rate, transition, or conclusion.
"""

from __future__ import annotations

from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
G4_LEDGER_REL = "research/g4/G4_PRIMARY_LEDGER.json"
ADNYE_001_REL = "research/adnye/ADNYE-001_Lambda_ref.json"
ADNYE_002_REL = "research/adnye/ADNYE-002_s_domain_box.json"
INSTANCE_REL = "research/canonical/stage1_instance.json"
FROZEN_SPEC_REL = "research/00_specifications/FROZEN_MATH_SPEC.md"
DECISIONS_REL = "research/decisions/DECISIONS.md"
OWNER_RECORD_REL = "research/decisions/GATE_5_OWNER_EXCEPTION_AND_EXIT.md"

G4_LEDGER_SHA256 = "9f1277cb642697786f8a7216382199e376c28a40e272d1d7039c5c693c4dad71"
G4_LEDGER_CONTENT_SHA256 = "817f286071fb054e0a07b29cb379dcaa01979bb6ff399873fd22e032fffc7798"
ADNYE_001_SHA256 = "9473c205a002697492c75af9ab694920b6bf822b38b5bd5c58f8f240ca66116a"
ADNYE_002_SHA256 = "9d634366be5c737dbefd1ade5be5f76ceb960c9af4fa4b3d4cbc5ab3b35a2992"
INSTANCE_SHA256 = "c4615d9b5066597c4754a1e06d2b3a7906c218965a7d6d530cf54f75c4b5f243"
FROZEN_SPEC_SHA256 = "e963a7e10ba797a373ef50d585bec1056ee82f7274d762b7c8bab9a817062900"
DECISIONS_SHA256 = "274c6cd92d4958957d125efc7ae2ddb6f40629eb78b7c2e2be99224e038ce849"
OWNER_RECORD_SHA256 = "061004477a1e71e76664878fc5b46eb281f7e55fea470fbf4828a477efb23d9c"

SCHEMA = "decisions_os/g6_preexecution_coefficient_ledger/v1"
P = 10


class LedgerError(RuntimeError):
    """Raised when a frozen Gate-6 ledger input cannot be established."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LedgerError(message)


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha256(path: Path) -> str:
    _require(path.is_file(), f"required input is missing: {path.relative_to(ROOT)}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise LedgerError(f"unreadable JSON input: {relative}") from exc
    _require(isinstance(payload, dict), f"JSON input must be an object: {relative}")
    return payload


def _validate_canonical_hash(payload: Mapping[str, Any], label: str, expected: str) -> None:
    body = dict(payload)
    digest = body.pop("content_sha256", None)
    _require(isinstance(digest, str), f"{label} lacks content_sha256")
    actual = hashlib.sha256(canonical_bytes(body)).hexdigest()
    _require(actual == digest == expected, f"{label} is not the accepted artifact")


def _positive(value: float, label: str) -> float:
    _require(math.isfinite(value) and value > 0.0, f"{label} must be finite and strictly positive")
    return value


def _positive_hex(value: Any, label: str) -> float:
    """Parse a finite, strictly positive binary64 literal fail-closed."""
    _require(isinstance(value, str), f"{label} must be a hexadecimal binary64 string")
    try:
        parsed = float.fromhex(value)
    except ValueError as exc:
        raise LedgerError(f"{label} is not a hexadecimal binary64 value") from exc
    return _positive(parsed, label)


def _coordinate(q_min: int, index: int, intervals: int, precision: int) -> Decimal:
    with localcontext() as context:
        context.prec = precision
        exponent = Decimal(q_min) + Decimal(index) / Decimal(intervals)
        return Decimal(10) ** exponent


def _coordinate_rows(q_min: int, q_max: int, intervals: int = P) -> list[dict[str, str | int]]:
    _require(isinstance(q_min, int) and isinstance(q_max, int) and q_max >= q_min, "invalid coordinate range")
    _require(isinstance(intervals, int) and intervals > 0, "invalid intervals per decade")
    count = intervals * (q_max - q_min) + 1
    rows: list[dict[str, str | int]] = []
    for index in range(count):
        low_precision = _coordinate(q_min, index, intervals, 120)
        high_precision = _coordinate(q_min, index, intervals, 180)
        value = float(low_precision)
        _require(value == float(high_precision), f"coordinate {index} is not precision-stable")
        _positive(value, f"coordinate {index}")
        exponent = Decimal(q_min) + Decimal(index) / Decimal(intervals)
        rows.append({
            "index": index,
            "exponent_decimal": str(exponent),
            "decimal_120": format(low_precision, "f"),
            "binary64_hex": value.hex(),
        })
    _require(rows[0]["binary64_hex"] == float(f"1e{q_min}").hex(), "lower endpoint drift")
    _require(rows[-1]["binary64_hex"] == float(f"1e{q_max}").hex(), "upper endpoint drift")
    return rows


def _load_accepted_inputs() -> tuple[dict[str, Any], float, dict[str, str]]:
    g4_path, adnye_path = ROOT / G4_LEDGER_REL, ROOT / ADNYE_001_REL
    _require(_sha256(g4_path) == G4_LEDGER_SHA256, "G4 primary ledger file hash mismatch")
    _require(_sha256(adnye_path) == ADNYE_001_SHA256, "ADNYE-001 file hash mismatch")
    _require(_sha256(ROOT / ADNYE_002_REL) == ADNYE_002_SHA256, "ADNYE-002 file hash mismatch")
    _require(_sha256(ROOT / INSTANCE_REL) == INSTANCE_SHA256, "canonical instance file hash mismatch")
    _require(_sha256(ROOT / FROZEN_SPEC_REL) == FROZEN_SPEC_SHA256, "frozen math specification hash mismatch")
    _require(_sha256(ROOT / DECISIONS_REL) == DECISIONS_SHA256, "DECISIONS.md hash mismatch")
    _require(_sha256(ROOT / OWNER_RECORD_REL) == OWNER_RECORD_SHA256, "Gate-5 owner record hash mismatch")

    g4 = _read_json(G4_LEDGER_REL)
    _validate_canonical_hash(g4, "G4 primary ledger", G4_LEDGER_CONTENT_SHA256)
    _require(g4.get("schema") == "g4-primary-coordinate-coefficient-ledger/v1", "unexpected G4 ledger schema")
    _require(g4.get("grid_rule") == {"q_min": -4, "q_max": 2, "P": 10, "N_axis": 61},
             "unexpected G4 primary grid rule")
    coordinates = g4.get("coordinates")
    _require(isinstance(coordinates, list) and len(coordinates) == 61, "malformed G4 coordinate ledger")

    adnye = _read_json(ADNYE_001_REL)
    _require(adnye.get("status") == "resolved", "ADNYE-001 is not resolved")
    try:
        lambda_ref = float(adnye["value"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LedgerError("ADNYE-001 has no valid Lambda_ref value") from exc
    _positive(lambda_ref, "Lambda_ref")
    inputs = g4.get("inputs")
    _require(isinstance(inputs, dict) and inputs.get("lambda_ref_binary64_hex") == lambda_ref.hex(),
             "Lambda_ref binary64 authority mismatch")
    for field, expected in (("v_card_binary64_hex", float(1.0).hex()),
                            ("v_sector_binary64_hex", float(1.0).hex()),
                            ("v_budget_binary64_hex", float(5.0).hex())):
        _require(inputs.get(field) == expected, f"unexpected frozen primitive: {field}")
    return g4, lambda_ref, {
        G4_LEDGER_REL: G4_LEDGER_SHA256,
        ADNYE_001_REL: ADNYE_001_SHA256,
        ADNYE_002_REL: ADNYE_002_SHA256,
        INSTANCE_REL: INSTANCE_SHA256,
        FROZEN_SPEC_REL: FROZEN_SPEC_SHA256,
        DECISIONS_REL: DECISIONS_SHA256,
        OWNER_RECORD_REL: OWNER_RECORD_SHA256,
        "src/g6/ledgers.py": _sha256(Path(__file__).resolve()),
    }


def _g4_coordinate(row: Mapping[str, Any], index: int) -> float:
    _require(row.get("index") == index and isinstance(row.get("binary64_hex"), str),
             f"malformed G4 coordinate row {index}")
    try:
        value = float.fromhex(row["binary64_hex"])
    except ValueError as exc:
        raise LedgerError(f"invalid G4 coordinate row {index}") from exc
    return _positive(value, f"G4 coordinate {index}")


def _axis_coefficients_d006_r1(s: float, lambda_ref: float, violation: float) -> dict[str, str]:
    """Independently transcribe frozen §4.3's r=1 primitive sequence."""
    _positive(s, "s"); _positive(lambda_ref, "Lambda_ref"); _positive(violation, "violation")
    t0 = float(2.0 * s)
    t1 = float(1.0 * 1.0)
    t2 = float(t1 + t0)
    t3 = float(math.sqrt(t2))
    t4 = float(t3 + 1.0)
    a = float(t0 / t4)
    v2 = float(violation * violation)
    lambda_slack = float(float(s * lambda_ref) / v2)
    lambda_1 = float(float(lambda_ref * a) / violation)
    lambda_2 = float(float(lambda_ref * float(a * a)) / float(2.0 * v2))
    return {
        "a_r_hex": _positive(a, "D006 a_r").hex(),
        "lambda_slack_hex": _positive(lambda_slack, "D006 lambda_slack").hex(),
        "lambda_1_hex": _positive(lambda_1, "D006 lambda_1").hex(),
        "lambda_2_hex": _positive(lambda_2, "D006 lambda_2").hex(),
    }


def _axis_coefficients_d011_cm(s: float, lambda_ref: float, violation: float) -> dict[str, str]:
    """Transcribe D011's approved a=2 curvature-match mapping."""
    _positive(s, "s"); _positive(lambda_ref, "Lambda_ref"); _positive(violation, "violation")
    v2 = float(violation * violation)
    numerator = float(s * lambda_ref)
    lambda_slack = float(numerator / v2)
    lambda_1 = float(numerator / violation)
    lambda_2 = float(numerator / v2)
    return {
        "a_fixed_hex": float(2.0).hex(),
        "lambda_slack_hex": _positive(lambda_slack, "D011 lambda_slack").hex(),
        "lambda_1_hex": _positive(lambda_1, "D011 lambda_1").hex(),
        "lambda_2_hex": _positive(lambda_2, "D011 lambda_2").hex(),
    }


def _cardinality_coefficients(s: float, lambda_ref: float) -> dict[str, str]:
    alpha = float(float(s * lambda_ref) / float(1.0 * 1.0))
    return {"alpha_hex": _positive(alpha, "alpha").hex()}


def _coefficient_ledger(rows: list[dict[str, str | int]], lambda_ref: float, mapping: str) -> dict[str, list[dict[str, str | int]]]:
    if mapping == "d006_r1":
        family = _axis_coefficients_d006_r1
    elif mapping == "d011_cm":
        family = _axis_coefficients_d011_cm
    else:
        raise LedgerError(f"unknown coefficient mapping: {mapping}")
    cardinality, sector, budget = [], [], []
    for row in rows:
        index, coordinate_hex = row["index"], row["binary64_hex"]
        _require(isinstance(index, int) and isinstance(coordinate_hex, str), "malformed coordinate row")
        s = _positive_hex(coordinate_hex, f"coordinate {index}")
        cardinality.append({"index": index, **_cardinality_coefficients(s, lambda_ref)})
        sector.append({"index": index, **family(s, lambda_ref, 1.0)})
        budget.append({"index": index, **family(s, lambda_ref, 5.0)})
    return {"cardinality": cardinality, "sector": sector, "budget": budget}


def _finalize(payload: dict[str, Any]) -> dict[str, Any]:
    payload["content_sha256"] = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    return payload


def _base_payload(*, pass_id: str, purpose: str, source_snapshot: Mapping[str, str], lambda_ref: float,
                  grid_rule: Mapping[str, Any], coordinates: list[dict[str, str | int]], mapping: str,
                  authority: str, transcript: list[str], recorded_defect: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "pass_id": pass_id,
        "purpose": purpose,
        "authority": authority,
        "source_snapshot": dict(source_snapshot),
        "inputs": {"lambda_ref_binary64_hex": lambda_ref.hex(), "v_card_binary64_hex": float(1.0).hex(),
                   "v_sector_binary64_hex": float(1.0).hex(), "v_budget_binary64_hex": float(5.0).hex()},
        "grid_rule": dict(grid_rule),
        "coordinates": coordinates,
        "coefficient_mapping": mapping,
        "coefficient_transcript": transcript,
        "coefficient_ledger": _coefficient_ledger(coordinates, lambda_ref, mapping),
        "scientific_outputs": "intentionally absent",
    }
    if recorded_defect is not None:
        payload["recorded_defect"] = recorded_defect
    return _finalize(payload)


def build_d011_ledger() -> dict[str, Any]:
    """Build D011's 13-point-per-axis input ledger from G4 primary rows."""
    g4, lambda_ref, snapshot = _load_accepted_inputs()
    selected = list(range(0, 61, 5))
    rows: list[dict[str, str | int]] = []
    for g4_index in selected:
        g4_row = g4["coordinates"][g4_index]
        _require(isinstance(g4_row, dict), f"malformed G4 coordinate row {g4_index}")
        value = _g4_coordinate(g4_row, g4_index)
        rows.append({"index": len(rows), "primary_ell": g4_index,
                     "binary64_hex": value.hex(), "exponent_decimal": g4_row["exponent_decimal"],
                     "decimal_120": g4_row["decimal_120"]})
    return _base_payload(
        pass_id="d011_curvature_companion",
        purpose="Binds D011 curvature-match coordinate and coefficient inputs; not a certification or result artifact.",
        source_snapshot=snapshot,
        lambda_ref=lambda_ref,
        grid_rule={"coordinate_source": "g4-primary-subgrid", "primary_ell": selected, "N_axis": 13},
        coordinates=rows,
        mapping="d011_cm",
        authority="DECISIONS.md D011 and the 2026-08-26 D011 coarse-subgrid approval; FROZEN_MATH_SPEC.md §4.3",
        transcript=["v2=fl(v*v)", "numerator=fl(s*Lambda_ref)", "lambda_S=fl(numerator/v2)",
                    "lambda_1=fl(numerator/v)", "lambda_2=fl(numerator/v2)", "a_fixed=2.0"],
    )


def build_v14_ledger(scale: str) -> dict[str, Any]:
    """Build one frozen V-14 r=1 coordinate/coefficient input ledger."""
    choices = {"0.5x": {"m_lo": 2, "m_hi": 0, "N_axis": 31},
               "2x": {"m_lo": 8, "m_hi": 2, "N_axis": 111}}
    _require(scale in choices, "V-14 scale must be '0.5x' or '2x'")
    g4, lambda_ref, snapshot = _load_accepted_inputs()
    adnye_002 = _read_json(ADNYE_002_REL)
    _require(adnye_002.get("status") == "resolved", "ADNYE-002 is not resolved")
    try:
        rho_box = float(adnye_002["rho_box"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LedgerError("ADNYE-002 has no valid rho_box") from exc
    _positive(rho_box, "rho_box")
    base_q_min, base_q_max = math.floor(math.log10(rho_box)), math.ceil(math.log10(rho_box))
    _require(g4["grid_rule"] == {"q_min": base_q_min - 4, "q_max": base_q_max + 1, "P": P, "N_axis": 61},
             "D010 primary-grid derivation mismatch")
    rule = {**choices[scale], "q_min": base_q_min - choices[scale]["m_lo"],
            "q_max": base_q_max + choices[scale]["m_hi"], "P": P, "r_hex": float(1.0).hex()}
    rows = _coordinate_rows(rule["q_min"], rule["q_max"], P)
    _require(len(rows) == rule["N_axis"], "V-14 coordinate count mismatch")
    return _base_payload(
        pass_id=f"v14_expansion_{scale}",
        purpose="Binds V-14 expansion coordinate and D006-r=1 coefficient inputs; not a certification or result artifact.",
        source_snapshot=snapshot,
        lambda_ref=lambda_ref,
        grid_rule=rule,
        coordinates=rows,
        mapping="d006_r1",
        authority="DECISIONS.md V-14 execution reading and FROZEN_MATH_SPEC.md §4.3",
        transcript=["t0=fl(2.0*s)", "t1=fl(1.0*1.0)", "t2=fl(t1+t0)", "t3=sqrt(t2)",
                    "t4=fl(t3+1.0)", "a=fl(t0/t4)", "v2=fl(v*v)",
                    "lambda_S=fl(fl(s*Lambda_ref)/v2)", "lambda_1=fl(fl(Lambda_ref*a)/v)",
                    "lambda_2=fl(fl(Lambda_ref*fl(a*a))/fl(2.0*v2))"],
        recorded_defect=("V-14 0.5x: 0.5*m_hi=0.5 is non-integer; the approved 2026-08-26 reading floors m_hi to 0."
                         if scale == "0.5x" else None),
    )


def validate_preexecution_ledger(payload: Mapping[str, Any]) -> None:
    """Validate ledger structure and its own canonical hash without deriving results."""
    _require(payload.get("schema") == SCHEMA, "unexpected Gate-6 ledger schema")
    _validate_canonical_hash(payload, "Gate-6 preexecution ledger", str(payload.get("content_sha256", "")))
    _require(payload.get("scientific_outputs") == "intentionally absent", "ledger result boundary violated")
    pass_id = payload.get("pass_id")
    factories = {
        "d011_curvature_companion": build_d011_ledger,
        "v14_expansion_0.5x": lambda: build_v14_ledger("0.5x"),
        "v14_expansion_2x": lambda: build_v14_ledger("2x"),
    }
    _require(pass_id in factories, "unknown Gate-6 preexecution pass id")
    expected = factories[pass_id]()
    actual_body, expected_body = dict(payload), dict(expected)
    actual_body.pop("content_sha256", None)
    expected_body.pop("content_sha256", None)
    _require(actual_body == expected_body,
             "Gate-6 preexecution ledger fails deterministic coordinate/coefficient transcript replay")
    coordinates, coefficients = payload.get("coordinates"), payload.get("coefficient_ledger")
    _require(isinstance(coordinates, list) and isinstance(coefficients, dict), "malformed Gate-6 ledger")
    mapping = payload.get("coefficient_mapping")
    _require(mapping in {"d006_r1", "d011_cm"}, "unknown Gate-6 coefficient mapping")
    expected_fields = {
        "cardinality": {"index", "alpha_hex"},
        "sector": ({"index", "a_r_hex", "lambda_slack_hex", "lambda_1_hex", "lambda_2_hex"}
                   if mapping == "d006_r1" else {"index", "a_fixed_hex", "lambda_slack_hex", "lambda_1_hex", "lambda_2_hex"}),
        "budget": ({"index", "a_r_hex", "lambda_slack_hex", "lambda_1_hex", "lambda_2_hex"}
                   if mapping == "d006_r1" else {"index", "a_fixed_hex", "lambda_slack_hex", "lambda_1_hex", "lambda_2_hex"}),
    }
    for family in ("cardinality", "sector", "budget"):
        rows = coefficients.get(family)
        _require(isinstance(rows, list) and len(rows) == len(coordinates), f"malformed {family} coefficient ledger")
    for index, coordinate in enumerate(coordinates):
        _require(isinstance(coordinate, dict) and coordinate.get("index") == index
                 and isinstance(coordinate.get("binary64_hex"), str), "misaligned coordinate row")
        _positive_hex(coordinate["binary64_hex"], f"coordinate {index}")
        for family, fields in expected_fields.items():
            coefficient = coefficients[family][index]
            _require(isinstance(coefficient, dict) and set(coefficient) == fields and coefficient.get("index") == index,
                     f"misaligned {family} coefficient row")
            for key, value in coefficient.items():
                if key != "index":
                    parsed = _positive_hex(value, f"{family} coefficient {key} at row {index}")
                    if key == "a_fixed_hex":
                        _require(parsed == 2.0, "D011 fixed curvature parameter drift")


def verify_nested_primary_coordinates() -> None:
    """Check the D011/V-14 primary-grid nesting obligations in memory."""
    g4, _, _ = _load_accepted_inputs()
    primary = [_g4_coordinate(row, index) for index, row in enumerate(g4["coordinates"])]
    d011 = build_d011_ledger()
    half = build_v14_ledger("0.5x")
    double = build_v14_ledger("2x")
    validate_preexecution_ledger(d011); validate_preexecution_ledger(half); validate_preexecution_ledger(double)
    for row, primary_index in zip(d011["coordinates"], range(0, 61, 5), strict=True):
        _require(row["binary64_hex"] == primary[primary_index].hex(), "D011 primary-subgrid mismatch")
    for index, primary_index in enumerate(range(20, 51)):
        _require(half["coordinates"][index]["binary64_hex"] == primary[primary_index].hex(),
                 "V-14 0.5x nested-primary mismatch")
    for primary_index in range(61):
        _require(double["coordinates"][primary_index + 40]["binary64_hex"] == primary[primary_index].hex(),
                 "V-14 2x nested-primary mismatch")

    primary_coefficients = g4["coefficient_ledger"]
    for d011_index, primary_index in enumerate(range(0, 61, 5)):
        _require(d011["coefficient_ledger"]["cardinality"][d011_index]["alpha_hex"]
                 == primary_coefficients["cardinality"][primary_index]["alpha_hex"],
                 "D011 cardinality coefficient drift")
        for family in ("sector", "budget"):
            _require(d011["coefficient_ledger"][family][d011_index]["lambda_slack_hex"]
                     == primary_coefficients[family][primary_index]["lambda_slack_hex"],
                     "D011 slack coefficient drift")
            _require(d011["coefficient_ledger"][family][d011_index]["lambda_2_hex"]
                     == d011["coefficient_ledger"][family][d011_index]["lambda_slack_hex"],
                     "D011 curvature-match lambda_2 mismatch")
            _require(d011["coefficient_ledger"][family][d011_index]["lambda_1_hex"]
                     != primary_coefficients[family][primary_index]["lambda_1_hex"]
                     and d011["coefficient_ledger"][family][d011_index]["lambda_2_hex"]
                     != primary_coefficients[family][primary_index]["lambda_2_hex"],
                     "D011 unexpectedly equals the primary inequality mapping")

    def require_d006_nesting(candidate: Mapping[str, Any], candidate_index: int, primary_index: int) -> None:
        _require(candidate["coefficient_ledger"]["cardinality"][candidate_index]["alpha_hex"]
                 == primary_coefficients["cardinality"][primary_index]["alpha_hex"],
                 "V-14 cardinality coefficient nesting mismatch")
        for family in ("sector", "budget"):
            for field in ("a_r_hex", "lambda_slack_hex", "lambda_1_hex", "lambda_2_hex"):
                _require(candidate["coefficient_ledger"][family][candidate_index][field]
                         == primary_coefficients[family][primary_index][field],
                         f"V-14 {family} {field} coefficient nesting mismatch")

    for half_index, primary_index in enumerate(range(20, 51)):
        require_d006_nesting(half, half_index, primary_index)
    for primary_index in range(61):
        require_d006_nesting(double, primary_index + 40, primary_index)
