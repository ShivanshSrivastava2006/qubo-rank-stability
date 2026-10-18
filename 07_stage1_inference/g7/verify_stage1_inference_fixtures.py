#!/usr/bin/env python3
"""Hardware-free fixtures for the Gate-7 inference reader.

Uses a tiny synthetic label lattice and a synthetic rate artifact.  It never
opens the accepted corpus, V-14 batch records, or accepted rate artifact.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g7 import stage1_inference as m  # noqa: E402


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def rejected(callback, label: str) -> None:
    try:
        callback()
    except m.Gate7InferenceError:
        return
    raise AssertionError(f"accepted malformed fixture: {label}")


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def fraction(numerator: int, denominator: int) -> dict[str, int]:
    return {"numerator": numerator, "denominator": denominator}


def primary(source: str, r: str, encoding: str, labels: dict[str, int], count: int) -> dict:
    return {"source": source, "r_hex": r, "encoding": encoding, "coordinate_count": count,
            "set_label_counts": labels, "rho_E_exact": fraction(labels["A"], count),
            "I_C_exist_count": labels["C"], "I_C_univ_count": 0,
            "mean_p": {"A": fraction(labels["A"], count), "B": fraction(labels["B"], count),
                       "C": fraction(labels["C"], count)}}


def v14(scale: str, count: int, encoding: str, a: int) -> dict:
    return {"source": "v14", "scale": scale,
            "condition": {"c_H": 2048, "c_f": 2048, "role": "primary"}, "encoding": encoding,
            "coordinate_count": count, "set_label_counts": {"A": a, "B": count - a, "C": 0},
            "rho_E_exact": fraction(a, count), "I_C_exist_count": 0, "I_C_univ_count": 0,
            "mean_p": {"A": fraction(a, count), "B": fraction(count - a, count), "C": fraction(0, count)}}


def record(r: str, card: int, sector: int, budget: int, unbalanced: str, slack: str) -> dict:
    return {"key": {"r_hex": r, "ell_card": card, "ell_sector": sector, "ell_budget": budget},
            "unbalanced": {"set_label": unbalanced}, "slack": {"set_label": slack}}


def fixture_rate(records: list[dict]) -> dict:
    cells = []
    for r in m.R_HEX:
        for encoding in m.ENCODINGS:
            tally = {x: 0 for x in "ABC"}
            for item in records:
                if item["key"]["r_hex"] == r:
                    tally[item[encoding]["set_label"]] += 1
            cells.append(primary("gate5_csb_primary", r, encoding, tally, m.CELL_COUNT))
    # The V-14 terms are required for shape validation but are not coupled to the tiny lattice.
    cells.extend((v14("0.5x", 29_791, "unbalanced", 1), v14("0.5x", 29_791, "slack", 2),
                  v14("2x", 1_367_631, "unbalanced", 1), v14("2x", 1_367_631, "slack", 2)))
    deltas = []
    for r in m.R_HEX:
        by = {(x["r_hex"], x["encoding"]): x for x in cells if x["source"] == "gate5_csb_primary"}
        delta = by[(r, "slack")]["rho_E_exact"]["numerator"] - by[(r, "unbalanced")]["rho_E_exact"]["numerator"]
        deltas.append({"r_hex": r, "numerator": delta, "denominator": m.CELL_COUNT})
    payload = {
        "schema": m.RATE_SCHEMA,
        "purpose": "synthetic", "input_identities": {
            "gate5_registry_content_sha256": m.ratified_g5_input.REGISTRY_CONTENT_SHA256,
            "accepted_v14_plans": dict(m.ACCEPTED_V14_PLANS),
            "v14": {scale: {"plan_content_sha256": scale, "audit_receipt_content_sha256": scale + "-audit",
                              "batch_count": batches, "coordinate_count": count}
                    for scale, batches, count in (("0.5x", 8, 29_791), ("2x", 334, 1_367_631))},
        },
        "series": cells,
        "d013_disposition": {"rule": "synthetic", "differences": deltas, "disposition": "does_not_fire",
                              "required_conditions": [], "ablation_status": "not_applicable"},
        "producer_source_sha256": {"synthetic": "0" * 64}, "reviewed_handoff": "fixture",
        "scientific_outputs": "synthetic",
    }
    payload["content_sha256"] = hashlib.sha256(canonical(payload)).hexdigest()
    return payload


def main() -> int:
    original = (m.AXIS, m.CELL_COUNT, m.R_HEX, m.D011)
    m.AXIS, m.CELL_COUNT, m.R_HEX, m.D011 = 2, 8, ("r0", "r1", "r2"), {}
    try:
        records = []
        # Each r covers the 2^3 lattice exactly.  Both directional A advantages occur at r0.
        label_rows = (("A", "B"), ("B", "A"), ("A", "A"), ("C", "C"),
                      ("B", "B"), ("A", "A"), ("C", "C"), ("B", "B"))
        for r in m.R_HEX:
            for linear, (unbalanced, slack) in enumerate(label_rows):
                card, rem = divmod(linear, 4)
                sector, budget = divmod(rem, 2)
                records.append(record(r, card, sector, budget, unbalanced, slack))
        payload = fixture_rate(records)
        with tempfile.TemporaryDirectory(prefix="g7-inference-fixture-") as tmp:
            rate_path = Path(tmp) / "rate.json"
            raw = canonical(payload)
            rate_path.write_bytes(raw)
            file_hash = hashlib.sha256(raw).hexdigest()
            result = m.build_inference(rate_path=rate_path, reviewed_handoff="fixture-review",
                                       records=iter(records), expected_rate_file_sha256=file_hash,
                                       expected_rate_content_sha256=payload["content_sha256"])
            require(result["hypothesis_evaluation"]["H1_rank_instability"]["literal_A_advantage_crossover"] == "observed",
                    "literal H1 crossover fixture was not observed")
            require(result["hypothesis_evaluation"]["H0_rank_stability"]["rate_component"]
                    == "indeterminate_no_preregistered_comparability_threshold",
                    "a tiny exact rate gap was treated as a pre-registered comparability threshold")
            require(result["hypothesis_evaluation"]["H1_rank_instability"]["status"]
                    == "not_falsified_crossover_not_adjudicated_no_preregistered_subregion_criterion",
                    "single-point bidirectional advantage overclaimed a crossover")
            require(result["hypothesis_evaluation"]["H2_infeasibility_asymmetry"]["status"]
                    == "indeterminate_no_preregistered_measurability_threshold", "H2 threshold guard drift")
            require(hashlib.sha256(canonical({k: v for k, v in result.items() if k != "content_sha256"})).hexdigest()
                    == result["content_sha256"], "result content hash drift")
            rejected(lambda: m.build_inference(rate_path=rate_path, reviewed_handoff="fixture-review",
                                                records=iter(records), expected_rate_file_sha256="1" * 64,
                                                expected_rate_content_sha256=payload["content_sha256"]), "wrong rate file pin")
            altered = dict(payload); altered["series"] = list(payload["series"]); altered["series"][0] = dict(altered["series"][0]); altered["series"][0]["coordinate_count"] = 7
            altered["content_sha256"] = hashlib.sha256(canonical({k: v for k, v in altered.items() if k != "content_sha256"})).hexdigest()
            rate_path.write_bytes(canonical(altered))
            altered_hash = hashlib.sha256(rate_path.read_bytes()).hexdigest()
            rejected(lambda: m.build_inference(rate_path=rate_path, reviewed_handoff="fixture-review", records=iter(records),
                                                expected_rate_file_sha256=altered_hash,
                                                expected_rate_content_sha256=altered["content_sha256"]), "malformed aggregate count")
            rate_path.write_bytes(raw)
            duplicate = records + [records[0]]
            rejected(lambda: m.build_inference(rate_path=rate_path, reviewed_handoff="fixture-review", records=iter(duplicate),
                                                expected_rate_file_sha256=file_hash,
                                                expected_rate_content_sha256=payload["content_sha256"]), "duplicate lattice coordinate")
            malformed = [dict(x) for x in records]
            malformed[0] = dict(malformed[0]); malformed[0]["slack"] = {"set_label": "AB"}
            rejected(lambda: m.build_inference(rate_path=rate_path, reviewed_handoff="fixture-review", records=iter(malformed),
                                                expected_rate_file_sha256=file_hash,
                                                expected_rate_content_sha256=payload["content_sha256"]), "malformed label")
    finally:
        m.AXIS, m.CELL_COUNT, m.R_HEX, m.D011 = original
    runner = ROOT / "research/g7/run_stage1_inference.py"
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    normal = subprocess.run([sys.executable, str(runner)], cwd=ROOT, env=env, text=True, capture_output=True, check=True)
    optimized = subprocess.run([sys.executable, "-O", str(runner)], cwd=ROOT, env=env, text=True, capture_output=True, check=True)
    require(normal.stdout == optimized.stdout, "plan stdout differs under -O")
    print("PASS Gate-7 inference fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
