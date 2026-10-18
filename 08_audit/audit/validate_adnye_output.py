#!/usr/bin/env python3
"""Validate the approved D014 ADNYE-001/002 output contract.

This validator accepts only the branch-conditional, closed schemas approved in
DECISIONS.md D014 / ADNYE_OUTPUT_CONTRACT_MEMO.md revision 6.  It does not
compute an ADNYE value; it validates an already-emitted record.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DECISIONS_PATH = REPO_ROOT / "research/decisions/DECISIONS.md"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SIDECAR_RE = re.compile(r"^[0-9a-f]{64}  [A-Za-z0-9_.-]+\.json\n$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

ONE_JSON = "ADNYE-001_Lambda_ref.json"
TWO_JSON = "ADNYE-002_s_domain_box.json"
ONE_SIDECAR = ONE_JSON + ".sha256"
TWO_SIDECAR = TWO_JSON + ".sha256"
STOPPED_NAMES = {ONE_JSON, ONE_SIDECAR}
RESOLVED_NAMES = STOPPED_NAMES | {TWO_JSON, TWO_SIDECAR}

D008_HEADING = "## D008 — Definition of `Lambda_ref` (U-03)"
D010_HEADING = "## D010 — Three-axis `s`-domain box (U-04)"
D008_RULE = (
    "Lambda_ref = max_{x in F} f(x) - min_{x in F} f(x)\n"
    "F = { x in {0,1}^20 : sum_i x_i = K, n_j(x) <= C for all j = 1..4, p^T x <= B }"
)
D010_RULE = (
    "Delta_full = max_{x in {0,1}^20} f(x) - min_{x in {0,1}^20} f(x)\n"
    "rho_box = Delta_full / Lambda_ref\n"
    "s_max = 10^(ceil(log10(rho_box)) + 1)\n"
    "s_min = 10^(floor(log10(rho_box)) - 4)\n"
    "COMMON CUBE [s_min, s_max] on ALL THREE axes: s_card, s_sector, s_budget\n"
    "m_hi = 1\n"
    "m_lo = 4"
)


class ContractError(ValueError):
    """A record violates the D014 contract."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key!r}")
        out[key] = value
    return out


def reject_json_constant(value: str) -> None:
    raise ContractError(f"non-finite JSON constant: {value}")


def load_record(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_pairs,
            parse_constant=reject_json_constant,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot parse {path.name}: {exc}") from exc
    require_type(value, dict, f"{path.name} top level")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def require_type(value: Any, expected: type, name: str) -> None:
    require(type(value) is expected, f"{name} must be {expected.__name__}")


def require_string(value: Any, name: str) -> None:
    require_type(value, str, name)


def require_number(value: Any, name: str) -> None:
    require(type(value) in (int, float), f"{name} must be a JSON number")
    require(math.isfinite(value), f"{name} must be finite")


def require_integer(value: Any, name: str) -> None:
    require_type(value, int, name)


def require_keys(value: dict[str, Any], keys: set[str], name: str) -> None:
    actual = set(value)
    require(actual == keys, f"{name} keys must be exactly {sorted(keys)!r}; got {sorted(actual)!r}")


def require_digest(value: Any, name: str) -> None:
    require_string(value, name)
    require(DIGEST_RE.fullmatch(value) is not None, f"{name} must be sha256:<64 lowercase hex>")


def require_date(value: Any, name: str) -> dt.date:
    require_string(value, name)
    require(DATE_RE.fullmatch(value) is not None, f"{name} must be YYYY-MM-DD")
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{name} is not a valid Gregorian date") from exc


def require_utc(value: Any, name: str) -> dt.datetime:
    require_string(value, name)
    require(UTC_RE.fullmatch(value) is not None, f"{name} must be YYYY-MM-DDTHH:MM:SSZ")
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError as exc:
        raise ContractError(f"{name} is not a valid non-leap-second UTC instant") from exc


def section_from_current_decisions(heading: str) -> str:
    lines = DECISIONS_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    start: int | None = None
    end = len(lines)
    fenced = False
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if line.rstrip("\r\n") == heading:
            require(start is None, f"decision heading {heading!r} occurs more than once")
            start = index
        elif start is not None and re.match(r"^## D[0-9]{3} —", line):
            end = index
            break
    require(start is not None, f"decision heading not found: {heading}")
    return "".join(lines[start:end])


def verify_sidecar(root: Path, json_name: str, record: dict[str, Any]) -> str:
    sidecar = root / (json_name + ".sha256")
    require(sidecar.is_file() and not sidecar.is_symlink(), f"missing regular sidecar {sidecar.name}")
    text = sidecar.read_text(encoding="utf-8")
    require(SIDECAR_RE.fullmatch(text) is not None, f"invalid sidecar grammar: {sidecar.name}")
    expected = sha256(canonical_bytes(record))
    require(text == f"{expected}  {json_name}\n", f"sidecar digest mismatch: {sidecar.name}")
    return "sha256:" + expected


def verify_common(record: dict[str, Any], *, decision: str, heading: str, rule: str,
                  execution_point: str, intake: bool = False) -> None:
    common = {
        "adnye_id", "quantity", "units", "governing_decision", "governing_decision_approved_date",
        "governing_decision_source", "governing_decision_snapshot", "governing_decision_digest",
        "governing_rule_verbatim", "governing_rule_digest", "execution_point", "inputs", "status",
        "resolved_at_utc", "resolver",
    }
    require(common <= set(record), "record is missing a common D014 field")
    for field in common - {"governing_decision_source", "inputs", "resolver"}:
        if field not in {"status"}:
            require_string(record[field], field)
    require(record["governing_decision"] == decision, "wrong governing_decision")
    require(record["execution_point"] == execution_point, "wrong execution_point")
    require(record["governing_rule_verbatim"] == rule, "governing_rule_verbatim is not the exact approved rule")
    require_digest(record["governing_decision_digest"], "governing_decision_digest")
    require_digest(record["governing_rule_digest"], "governing_rule_digest")
    require(
        record["governing_decision_digest"] == "sha256:" + sha256(record["governing_decision_snapshot"].encode("utf-8")),
        "governing_decision_digest does not hash governing_decision_snapshot",
    )
    require(
        record["governing_rule_digest"] == "sha256:" + sha256(rule.encode("utf-8")),
        "governing_rule_digest does not hash governing_rule_verbatim",
    )
    source = record["governing_decision_source"]
    require_type(source, dict, "governing_decision_source")
    require_keys(source, {"path", "section_heading", "source_file_digest", "capture_rule"}, "governing_decision_source")
    require(source["path"] == "research/decisions/DECISIONS.md", "wrong governing decision source path")
    require(source["section_heading"] == heading, "wrong governing decision section heading")
    require(source["capture_rule"] == "decision_section_v1", "wrong decision capture rule")
    require_digest(source["source_file_digest"], "governing_decision_source.source_file_digest")
    if intake:
        current_bytes = DECISIONS_PATH.read_bytes()
        require(
            source["source_file_digest"] == "sha256:" + sha256(current_bytes),
            "governing decision source digest does not attest current intake bytes",
        )
        require(
            record["governing_decision_snapshot"] == section_from_current_decisions(heading),
            "governing_decision_snapshot does not equal the captured decision section",
        )
    approved = require_date(record["governing_decision_approved_date"], "governing_decision_approved_date")
    resolved = require_utc(record["resolved_at_utc"], "resolved_at_utc")
    require(approved < resolved.date(), "date-only approval must be strictly earlier than resolved_at_utc date")
    resolver = record["resolver"]
    require_type(resolver, dict, "resolver")
    require_keys(resolver, {"python", "numpy"}, "resolver")
    for key, value in resolver.items():
        require_string(value, f"resolver.{key}")
        require(bool(value), f"resolver.{key} may not be empty")


def verify_candidates(candidates: Any) -> None:
    require_type(candidates, list, "transparency_candidates")
    required = [
        ("range", "F", False),
        ("std", "F", True),
        ("range", "cardinality_feasible", False),
        ("std", "cardinality_feasible", True),
        ("range", "binary_full_space", False),
    ]
    require(len(candidates) == len(required), "transparency_candidates must contain exactly five entries")
    for index, (candidate, (statistic, population, needs_ddof)) in enumerate(zip(candidates, required), 1):
        require_type(candidate, dict, f"transparency_candidates[{index}]")
        keys = {"statistic", "population", "value", "units"} | ({"ddof"} if needs_ddof else set())
        require_keys(candidate, keys, f"transparency_candidates[{index}]")
        require(candidate["statistic"] == statistic, f"candidate {index} has wrong statistic")
        require(candidate["population"] == population, f"candidate {index} has wrong population")
        require(candidate["units"] == "E", f"candidate {index} has wrong units")
        require_number(candidate["value"], f"candidate {index} value")
        if needs_ddof:
            require_integer(candidate["ddof"], f"candidate {index} ddof")
            require(candidate["ddof"] >= 0, f"candidate {index} ddof must be nonnegative")


def verify_one(record: dict[str, Any], *, intake: bool = False) -> None:
    expected = {
        "adnye_id", "quantity", "units", "governing_decision", "governing_decision_approved_date",
        "governing_decision_source", "governing_decision_snapshot", "governing_decision_digest",
        "governing_rule_verbatim", "governing_rule_digest", "execution_point", "inputs", "status",
        "resolved_at_utc", "resolver", "value", "delta_full", "transparency_candidates",
    }
    require_keys(record, expected, ONE_JSON)
    require(record["adnye_id"] == "ADNYE-001", "wrong ADNYE-001 identifier")
    require(record["quantity"] == "Lambda_ref", "wrong ADNYE-001 quantity")
    require(record["units"] == "E", "wrong ADNYE-001 units")
    verify_common(record, decision="D008", heading=D008_HEADING, rule=D008_RULE,
                  execution_point="G3.compute_Lambda_ref", intake=intake)
    require_type(record["inputs"], list, "ADNYE-001 inputs")
    expected_names = ["canonical_mu", "canonical_Sigma", "D007_kappa_risk_triple", "canonical_instance", "F_predicate"]
    require(len(record["inputs"]) == len(expected_names), "ADNYE-001 must have exactly five inputs")
    for input_record, name in zip(record["inputs"], expected_names):
        require_type(input_record, dict, f"ADNYE-001 input {name}")
        require_keys(input_record, {"name", "digest"}, f"ADNYE-001 input {name}")
        require(input_record["name"] == name, f"ADNYE-001 input order/name mismatch: expected {name}")
        require_digest(input_record["digest"], f"ADNYE-001 input {name} digest")
    require_number(record["value"], "ADNYE-001 value")
    require_number(record["delta_full"], "ADNYE-001 delta_full")
    require(record["value"] >= 0, "ADNYE-001 value must be nonnegative")
    require(record["delta_full"] >= record["value"], "delta_full must be at least Lambda_ref")
    verify_candidates(record["transparency_candidates"])
    require(
        record["transparency_candidates"][0]["value"] == record["value"],
        "the D008 range-over-F transparency candidate must equal ADNYE-001 value",
    )
    require(
        record["transparency_candidates"][4]["value"] == record["delta_full"],
        "the full-space range transparency candidate must equal ADNYE-001 delta_full",
    )
    required_status = "stopped_zero" if record["value"] == 0 else "resolved"
    require(record["status"] == required_status, f"ADNYE-001 status must be {required_status}")


def verify_two(record: dict[str, Any], one_digest: str, one: dict[str, Any], *, intake: bool = False) -> None:
    expected = {
        "adnye_id", "quantity", "units", "governing_decision", "governing_decision_approved_date",
        "governing_decision_source", "governing_decision_snapshot", "governing_decision_digest",
        "governing_rule_verbatim", "governing_rule_digest", "execution_point", "inputs", "status",
        "resolved_at_utc", "resolver", "rho_box", "s_min", "s_max",
    }
    require_keys(record, expected, TWO_JSON)
    require(record["adnye_id"] == "ADNYE-002", "wrong ADNYE-002 identifier")
    require(record["quantity"] == "s_domain_box", "wrong ADNYE-002 quantity")
    require(record["units"] == "dimensionless", "wrong ADNYE-002 units")
    verify_common(record, decision="D010", heading=D010_HEADING, rule=D010_RULE,
                  execution_point="G3.exit.resolve_box", intake=intake)
    require(record["status"] == "resolved", "ADNYE-002 status must be resolved")
    require(one["status"] == "resolved" and one["value"] != 0, "ADNYE-002 requires resolved nonzero ADNYE-001")
    require_type(record["inputs"], list, "ADNYE-002 inputs")
    expected_inputs = [("Lambda_ref", "value"), ("Delta_full", "delta_full")]
    require(len(record["inputs"]) == 2, "ADNYE-002 must have exactly two inputs")
    for input_record, (name, field) in zip(record["inputs"], expected_inputs):
        require_type(input_record, dict, f"ADNYE-002 input {name}")
        require_keys(input_record, {"name", "adnye_id", "field", "digest"}, f"ADNYE-002 input {name}")
        require(input_record["name"] == name and input_record["adnye_id"] == "ADNYE-001" and input_record["field"] == field,
                f"ADNYE-002 input {name} is not the required ADNYE-001 reference")
        require(input_record["digest"] == one_digest, f"ADNYE-002 input {name} digest must equal ADNYE-001 sidecar digest")
    for field in ("rho_box", "s_min", "s_max"):
        require_number(record[field], f"ADNYE-002 {field}")
    value = float(one["value"])
    delta = float(one["delta_full"])
    rho = delta / value
    expected_min = 10.0 ** (math.floor(math.log10(rho)) - 4)
    expected_max = 10.0 ** (math.ceil(math.log10(rho)) + 1)
    require(record["rho_box"] >= 1 and 0 < record["s_min"] <= record["s_max"], "invalid ADNYE-002 numeric ordering")
    require(record["rho_box"] == rho, "rho_box does not equal Delta_full / Lambda_ref")
    require(record["s_min"] == expected_min, "s_min does not equal the D010 formula")
    require(record["s_max"] == expected_max, "s_max does not equal the D010 formula")


def validate(root: Path, *, intake: bool = False) -> None:
    require(root.is_dir() and not root.is_symlink(), f"ADNYE root must be a regular directory: {root}")
    children = {item.name for item in root.iterdir()}
    require(children in (STOPPED_NAMES, RESOLVED_NAMES), f"branch whitelist violation: got {sorted(children)!r}")
    for name in children:
        item = root / name
        require(item.is_file() and not item.is_symlink(), f"ADNYE artifact must be a regular file: {name}")
    one = load_record(root / ONE_JSON)
    verify_one(one, intake=intake)
    one_digest = verify_sidecar(root, ONE_JSON, one)
    if one["status"] == "stopped_zero":
        require(children == STOPPED_NAMES, "stopped-zero branch permits only the ADNYE-001 pair")
        return
    require(children == RESOLVED_NAMES, "resolved ADNYE-001 requires the complete resolved branch")
    two = load_record(root / TWO_JSON)
    verify_two(two, one_digest, one, intake=intake)
    verify_sidecar(root, TWO_JSON, two)


def preflight_one(root: Path, *, intake: bool = False) -> None:
    """Verify an emitted ADNYE-001 pair before ADNYE-002 exists.

    This is deliberately *not* contract acceptance: the D014 full validator
    above continues to reject a resolved ADNYE-001-only directory because the
    resolved branch's final whitelist requires both pairs.  It implements the
    frozen chronology phrase “after sidecar-verifying ADNYE-001” without
    weakening the full branch acceptance rule.
    """
    require(root.is_dir() and not root.is_symlink(), f"ADNYE root must be a regular directory: {root}")
    children = {item.name for item in root.iterdir()}
    permitted = {ONE_JSON, ONE_SIDECAR}
    require(permitted <= children and children <= RESOLVED_NAMES,
            f"ADNYE-001 preflight permits only an in-progress or final D014 branch; got {sorted(children)!r}")
    for name in children:
        item = root / name
        require(item.is_file() and not item.is_symlink(), f"ADNYE artifact must be a regular file: {name}")
    one = load_record(root / ONE_JSON)
    verify_one(one, intake=intake)
    verify_sidecar(root, ONE_JSON, one)


def build_selftest_record(decision: str, heading: str, rule: str, execution: str) -> dict[str, Any]:
    snapshot = section_from_current_decisions(heading)
    decision_digest = sha256(snapshot.encode("utf-8"))
    source_digest = sha256(DECISIONS_PATH.read_bytes())
    return {
        "governing_decision": decision,
        "governing_decision_approved_date": "2026-08-24",
        "governing_decision_source": {
            "path": "research/decisions/DECISIONS.md",
            "section_heading": heading,
            "source_file_digest": "sha256:" + source_digest,
            "capture_rule": "decision_section_v1",
        },
        "governing_decision_snapshot": snapshot,
        "governing_decision_digest": "sha256:" + decision_digest,
        "governing_rule_verbatim": rule,
        "governing_rule_digest": "sha256:" + sha256(rule.encode("utf-8")),
        "execution_point": execution,
        "resolved_at_utc": "2026-08-25T19:15:34Z",
        "resolver": {"python": "selftest", "numpy": "selftest"},
    }


def write_selftest_pair(root: Path, name: str, record: dict[str, Any]) -> str:
    (root / name).write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    digest = sha256(canonical_bytes(record))
    (root / (name + ".sha256")).write_text(f"{digest}  {name}\n", encoding="utf-8")
    return "sha256:" + digest


def selftest() -> None:
    with tempfile.TemporaryDirectory(prefix="adnye-validator-") as temporary:
        root = Path(temporary)
        one = build_selftest_record("D008", D008_HEADING, D008_RULE, "G3.compute_Lambda_ref")
        one.update({
            "adnye_id": "ADNYE-001", "quantity": "Lambda_ref", "units": "E", "status": "resolved",
            "inputs": [{"name": name, "digest": "sha256:" + "0" * 64} for name in
                       ["canonical_mu", "canonical_Sigma", "D007_kappa_risk_triple", "canonical_instance", "F_predicate"]],
            "value": 1.0, "delta_full": 2.0,
            "transparency_candidates": [
                {"statistic": "range", "population": "F", "value": 1.0, "units": "E"},
                {"statistic": "std", "population": "F", "value": 0.1, "units": "E", "ddof": 0},
                {"statistic": "range", "population": "cardinality_feasible", "value": 1.5, "units": "E"},
                {"statistic": "std", "population": "cardinality_feasible", "value": 0.2, "units": "E", "ddof": 0},
                {"statistic": "range", "population": "binary_full_space", "value": 2.0, "units": "E"},
            ],
        })
        one_digest = write_selftest_pair(root, ONE_JSON, one)
        two = build_selftest_record("D010", D010_HEADING, D010_RULE, "G3.exit.resolve_box")
        two.update({
            "adnye_id": "ADNYE-002", "quantity": "s_domain_box", "units": "dimensionless", "status": "resolved",
            "inputs": [
                {"name": "Lambda_ref", "adnye_id": "ADNYE-001", "field": "value", "digest": one_digest},
                {"name": "Delta_full", "adnye_id": "ADNYE-001", "field": "delta_full", "digest": one_digest},
            ],
            "rho_box": 2.0, "s_min": 0.0001, "s_max": 100.0,
        })
        write_selftest_pair(root, TWO_JSON, two)
        validate(root)
        (root / ONE_SIDECAR).write_text("0" * 64 + f"  {ONE_JSON}\n", encoding="utf-8")
        try:
            validate(root)
        except ContractError:
            return
        raise AssertionError("tampered sidecar unexpectedly passed validation")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="D014 ADNYE output directory")
    parser.add_argument("--selftest", action="store_true", help="run isolated positive and negative contract fixtures")
    parser.add_argument("--preflight-one", action="store_true", help="verify ADNYE-001 before full-branch acceptance")
    parser.add_argument("--intake", action="store_true", help="also attest the living decision register at emission time")
    args = parser.parse_args()
    if args.selftest:
        try:
            selftest()
        except (ContractError, OSError, AssertionError) as exc:
            print(f"SELF-TEST FAILED: {exc}", file=sys.stderr)
            return 1
        print("PASS: ADNYE validator self-test (resolved branch + tampered-sidecar rejection)")
        return 0
    if args.root is None:
        parser.error("--root is required unless --selftest is used")
    try:
        if args.preflight_one:
            preflight_one(args.root, intake=args.intake)
            print(f"PASS: sidecar/schema preflight for ADNYE-001 at {args.root}; NOT a D014 branch acceptance")
            return 0
        validate(args.root, intake=args.intake)
    except (ContractError, OSError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: D014 ADNYE output contract validated at {args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
