#!/usr/bin/env python3
"""Independently replay ADNYE-002's D010 domain box.

This audit is deliberately separate from the D014 contract validator.  It
re-checks the closed resolved-branch file set, canonical sidecars, the two
ADNYE-001 dependency references, and the D010 arithmetic from raw decimal
JSON values.  It creates no official artifact and cannot accept a new gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any


ONE_NAME = "ADNYE-001_Lambda_ref.json"
TWO_NAME = "ADNYE-002_s_domain_box.json"
SIDECAR_RE = re.compile(r"^[0-9a-f]{64}  [A-Za-z0-9_.-]+\.json\n$")
RESOLVED_NAMES = {
    ONE_NAME,
    ONE_NAME + ".sha256",
    TWO_NAME,
    TWO_NAME + ".sha256",
}


class AuditError(ValueError):
    """An official output does not agree with the independently replayed rule."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise AuditError(f"duplicate JSON key: {key!r}")
        output[key] = value
    return output


def reject_constant(value: str) -> None:
    raise AuditError(f"non-finite JSON constant: {value}")


def canonical_digest(record: dict[str, Any]) -> str:
    data = json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def load_pair(root: Path, name: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    path = root / name
    raw = path.read_text(encoding="utf-8")
    regular = json.loads(raw, object_pairs_hook=reject_duplicate_pairs, parse_constant=reject_constant)
    decimal = json.loads(
        raw,
        object_pairs_hook=reject_duplicate_pairs,
        parse_constant=reject_constant,
        parse_float=Decimal,
        parse_int=Decimal,
    )
    require(type(regular) is dict and type(decimal) is dict, f"{name} must be a JSON object")
    sidecar = (root / (name + ".sha256")).read_text(encoding="utf-8")
    require(SIDECAR_RE.fullmatch(sidecar) is not None, f"invalid sidecar grammar: {name}.sha256")
    digest = canonical_digest(regular)
    require(sidecar == f"{digest}  {name}\n", f"canonical sidecar mismatch: {name}")
    return regular, decimal, "sha256:" + digest


def decimal_ceil_log10(value: Decimal) -> tuple[int, int]:
    """Return floor(log10(value)), ceil(log10(value)) without libm rounding."""
    require(value > 0, "D010 ratio must be positive")
    floor = value.adjusted()
    exact_power = Decimal(1).scaleb(floor)
    ceil = floor if value == exact_power else floor + 1
    return floor, ceil


def audit(root: Path) -> dict[str, Any]:
    require(root.is_dir() and not root.is_symlink(), "ADNYE root must be a regular directory")
    names = {entry.name for entry in root.iterdir()}
    require(names == RESOLVED_NAMES, f"resolved D014 whitelist mismatch: {sorted(names)!r}")
    require(all((root / name).is_file() and not (root / name).is_symlink() for name in names),
            "all ADNYE outputs must be regular files")

    one, one_decimal, one_digest = load_pair(root, ONE_NAME)
    two, two_decimal, two_digest = load_pair(root, TWO_NAME)
    require(one.get("status") == "resolved" and one.get("adnye_id") == "ADNYE-001",
            "ADNYE-001 is not the resolved predecessor")
    require(two.get("status") == "resolved" and two.get("adnye_id") == "ADNYE-002",
            "ADNYE-002 is not a resolved box record")
    require("delta_full" not in two, "ADNYE-002 must not duplicate Delta_full")

    inputs = two.get("inputs")
    require(type(inputs) is list and len(inputs) == 2, "ADNYE-002 must have two named inputs")
    expected_inputs = (("Lambda_ref", "value"), ("Delta_full", "delta_full"))
    for observed, (name, field) in zip(inputs, expected_inputs):
        require(type(observed) is dict, f"{name} input must be an object")
        require(observed == {
            "name": name, "adnye_id": "ADNYE-001", "field": field, "digest": one_digest,
        }, f"{name} input is not the exact ADNYE-001 dependency edge")

    lambda_decimal = one_decimal.get("value")
    delta_decimal = one_decimal.get("delta_full")
    require(type(lambda_decimal) is Decimal and type(delta_decimal) is Decimal,
            "ADNYE-001 numeric inputs must be JSON numbers")
    require(lambda_decimal > 0 and delta_decimal >= lambda_decimal,
            "D010 requires positive Lambda_ref and Delta_full >= Lambda_ref")
    with localcontext() as context:
        context.prec = 100
        rho_decimal = delta_decimal / lambda_decimal
    q_floor, q_ceil = decimal_ceil_log10(rho_decimal)
    q_min, q_max = q_floor - 4, q_ceil + 1
    min_decimal, max_decimal = Decimal(1).scaleb(q_min), Decimal(1).scaleb(q_max)

    lambda_float, delta_float = float(one["value"]), float(one["delta_full"])
    rho_float = delta_float / lambda_float
    require(math.isfinite(rho_float), "binary64 D010 ratio is non-finite")
    require(two["rho_box"] == rho_float, "rho_box differs from independent binary64 division")
    require(two_decimal["s_min"] == min_decimal, "s_min differs from exact integer-power D010 result")
    require(two_decimal["s_max"] == max_decimal, "s_max differs from exact integer-power D010 result")
    require(float(two["s_min"]) == float(min_decimal) and float(two["s_max"]) == float(max_decimal),
            "box endpoints are not the required binary64 powers of ten")
    require(q_max - q_min == 6, "D010 result is not the declared six-decade span for this instance")

    ulp_error = abs(Decimal.from_float(rho_float) - rho_decimal) / Decimal.from_float(math.ulp(rho_float))
    require(ulp_error <= Decimal("0.5"), "binary64 rho_box is not correctly rounded from raw decimal inputs")
    return {
        "calculated": {
            "Lambda_ref_raw_decimal": str(lambda_decimal),
            "Delta_full_raw_decimal": str(delta_decimal),
            "rho_box_decimal_100dp": format(rho_decimal, "f"),
            "rho_box_binary64": rho_float,
            "rho_box_rounding_error_ulps": float(ulp_error),
            "q_floor": q_floor,
            "q_ceil": q_ceil,
            "q_min": q_min,
            "q_max": q_max,
            "s_min": float(min_decimal),
            "s_max": float(max_decimal),
            "decade_span": q_max - q_min,
        },
        "official": {
            "adnye_001_digest": one_digest,
            "adnye_002_digest": two_digest,
            "rho_box": two["rho_box"],
            "s_min": two["s_min"],
            "s_max": two["s_max"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="official research/adnye directory")
    parser.add_argument("--report", type=Path, help="write one new JSON replay report after a clean replay")
    args = parser.parse_args()
    try:
        if args.report is not None and args.report.exists():
            raise AuditError(f"refusing to overwrite existing audit report: {args.report}")
        result = audit(args.root)
    except (AuditError, OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"AUDIT FAILED: {exc}", file=sys.stderr)
        return 1
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps({"status": "REPLAY_CLEAN_NOT_ACCEPTED", **result}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print("PASS: independent ADNYE-002 D010 replay agrees with the sidecar-verified predecessor")
    print(f"  rho_box={result['calculated']['rho_box_binary64']!r}; "
          f"q_min={result['calculated']['q_min']}; q_max={result['calculated']['q_max']}")
    print(f"  s_min={result['calculated']['s_min']!r}; s_max={result['calculated']['s_max']!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
