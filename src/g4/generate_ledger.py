"""Generate the bounded G4 primary coordinate/coefficient bit-pattern ledger.

The Decimal calculations bind the mathematical coordinates.  A second,
higher-precision evaluation must convert to the identical binary64 value before
the artifact is emitted; otherwise generation fails closed.
"""

from __future__ import annotations

from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "research/canonical/stage1_instance.json"
ADNYE_001 = ROOT / "research/adnye/ADNYE-001_Lambda_ref.json"
ADNYE_002 = ROOT / "research/adnye/ADNYE-002_s_domain_box.json"
OUTPUT = ROOT / "research/g4/G4_PRIMARY_LEDGER.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _coordinate(q_min: int, index: int, intervals: int, precision: int) -> Decimal:
    with localcontext() as context:
        context.prec = precision
        exponent = Decimal(q_min) + (Decimal(index) / Decimal(intervals))
        return Decimal(10) ** exponent


def _hex(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("nonfinite binary64 ledger value")
    return value.hex()


def _positive_hex(value: float, label: str) -> str:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be finite and strictly positive")
    return value.hex()


def _primary_coefficients(s: float, lambda_ref: float, violation: float) -> dict[str, str]:
    # These assignments deliberately mirror frozen §4.3's one-operation ledger.
    if any(not math.isfinite(value) or value <= 0.0 for value in (s, lambda_ref, violation)):
        raise ValueError("active coefficient inputs must be finite and strictly positive")
    t0 = 2.0 * s
    t1 = 1.0 * 1.0
    t2 = t1 + t0
    t3 = math.sqrt(t2)
    t4 = t3 + 1.0
    a = t0 / t4
    v2 = violation * violation
    lambda_slack = (s * lambda_ref) / v2
    lambda_1 = (lambda_ref * a) / violation
    lambda_2 = (lambda_ref * (a * a)) / (2.0 * v2)
    return {
        "a_r_hex": _positive_hex(a, "a_r"),
        "lambda_slack_hex": _positive_hex(lambda_slack, "lambda_slack"),
        "lambda_1_hex": _positive_hex(lambda_1, "lambda_1"),
        "lambda_2_hex": _positive_hex(lambda_2, "lambda_2"),
    }


def build() -> dict[str, object]:
    canonical = json.loads(CANONICAL.read_text(encoding="utf-8"))
    adnye_001 = json.loads(ADNYE_001.read_text(encoding="utf-8"))
    adnye_002 = json.loads(ADNYE_002.read_text(encoding="utf-8"))
    if adnye_001["status"] != "resolved" or adnye_002["status"] != "resolved":
        raise ValueError("resolved D014 inputs are required")
    lambda_ref = float(adnye_001["value"])
    if not math.isfinite(lambda_ref) or lambda_ref <= 0.0:
        raise ValueError("Lambda_ref must be finite and positive")
    rho_box = float(adnye_002["rho_box"])
    if not math.isfinite(rho_box) or rho_box <= 0.0:
        raise ValueError("D010 rho_box must be finite and positive")
    q_min = math.floor(math.log10(rho_box)) - 4
    q_max = math.ceil(math.log10(rho_box)) + 1
    intervals = 10
    expected_min, expected_max = float(adnye_002["s_min"]), float(adnye_002["s_max"])
    coordinates = []
    for index in range(intervals * (q_max - q_min) + 1):
        low_precision = _coordinate(q_min, index, intervals, 120)
        high_precision = _coordinate(q_min, index, intervals, 180)
        value = float(low_precision)
        if value != float(high_precision):
            raise ValueError(f"coordinate {index} is not precision-stable")
        coordinates.append({
            "index": index,
            "exponent_decimal": str(Decimal(q_min) + Decimal(index) / Decimal(intervals)),
            "decimal_120": format(low_precision, "f"),
            "binary64_hex": _hex(value),
        })
    if float.fromhex(coordinates[0]["binary64_hex"]) != expected_min:
        raise ValueError("lower endpoint does not equal D010 record")
    if float.fromhex(coordinates[-1]["binary64_hex"]) != expected_max:
        raise ValueError("upper endpoint does not equal D010 record")
    cardinality = []
    sector = []
    budget = []
    for coordinate in coordinates:
        s = float.fromhex(coordinate["binary64_hex"])
        alpha = (s * lambda_ref) / (1.0 * 1.0)
        cardinality.append({"index": coordinate["index"], "alpha_hex": _positive_hex(alpha, "alpha")})
        sector.append({"index": coordinate["index"], **_primary_coefficients(s, lambda_ref, 1.0)})
        budget.append({"index": coordinate["index"], **_primary_coefficients(s, lambda_ref, 5.0)})
    payload: dict[str, object] = {
        "schema": "g4-primary-coordinate-coefficient-ledger/v1",
        "authority": "DECISIONS.md — Process Approval — Gate 4 bounded encoding formulation and conformance",
        "purpose": "Binds primary binary64 coordinate and coefficient inputs; not a grid sweep or result artifact.",
        "inputs": {
            "canonical_instance_sha256": _sha256(CANONICAL),
            "adnye_001_sha256": _sha256(ADNYE_001),
            "adnye_002_sha256": _sha256(ADNYE_002),
            "lambda_ref_binary64_hex": _hex(lambda_ref),
            "v_card_binary64_hex": _hex(1.0),
            "v_sector_binary64_hex": _hex(1.0),
            "v_budget_binary64_hex": _hex(5.0),
        },
        "grid_rule": {"q_min": q_min, "q_max": q_max, "P": intervals, "N_axis": len(coordinates)},
        "coordinates": coordinates,
        "coefficient_ledger": {"cardinality": cardinality, "sector": sector, "budget": budget},
        "exclusions": [
            "G5 exact ground-state certification", "encoded tie-set computation", "A/B/C classification",
            "grid sweep", "experiment", "result", "conclusion", "D011 companion execution", "V-14 expansion execution",
        ],
    }
    canonical_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    payload["content_sha256"] = hashlib.sha256(canonical_bytes).hexdigest()
    return payload


def main() -> int:
    payload = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE {OUTPUT.relative_to(ROOT)} content_sha256={payload['content_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
