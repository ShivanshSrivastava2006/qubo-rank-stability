"""Fast producer-side integrity checks for the Gate-5 named-point artifact.

This verifier checks the immutable result, point/authority binding, every
reported tied-state energy through the non-prepared canonical evaluator, and
decoded-only classification.  It deliberately does not claim an independent
full-domain proof of T_E completeness; that belongs to the controlling review.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.g4.classification import DecodedClassifier, OriginalObjectiveService
from src.g4.energy import objective, slack_energy, unbalanced_energy
from src.g4.instance import load_instance
from src.g4.parameters import load_coefficients


RESULT = ROOT / "research/g5/G5_NAMED_POINT_RESULT.json"
SIDECAR = ROOT / "research/g5/G5_NAMED_POINT_RESULT.json.sha256"
EXPECTED_FILE_SHA256 = "07a209507afcb44d60a931df91b431d45425c8fd6623389c936d9506c5982f64"
EXPECTED_CONTENT_SHA256 = "c6f03a0ca958b4dfff7fc606dc1b733fcea448f078226138e7586b44969856b9"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    encoded = RESULT.read_bytes()
    file_digest = hashlib.sha256(encoded).hexdigest()
    require(file_digest == EXPECTED_FILE_SHA256, "named-point file digest mismatch")
    require(
        SIDECAR.read_text(encoding="ascii")
        == f"{EXPECTED_FILE_SHA256}  {RESULT.name}\n",
        "named-point sidecar mismatch",
    )
    payload = json.loads(encoded)
    content = copy.deepcopy(payload)
    claimed_content = content.pop("content_sha256", None)
    canonical = json.dumps(
        content, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    require(claimed_content == EXPECTED_CONTENT_SHA256, "unexpected content digest claim")
    require(hashlib.sha256(canonical).hexdigest() == claimed_content, "content digest mismatch")
    require(payload["point"]["r"] == 1.0, "named point is not primary r=1")
    require(
        payload["point"]["indices"]
        == {"budget": 30, "cardinality": 30, "sector": 30},
        "named-point indices mismatch",
    )
    require(
        set(payload["encodings"]) == {"slack", "unbalanced"},
        "both and only authorized encodings are required",
    )

    for relative, expected in payload["artifact_sha256"].items():
        require(
            hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected,
            f"bound artifact changed: {relative}",
        )

    instance = load_instance(ROOT / "research/canonical/stage1_instance.json")
    coefficients = load_coefficients(
        ROOT / "research/g4/G4_PRIMARY_LEDGER.json", 30, 30, 30
    )
    ground_truth = json.loads(
        (ROOT / "research/ground_truth/G3_GROUND_TRUTH.json").read_text(encoding="utf-8")
    )
    f_star = float(ground_truth["results"]["f_star"])
    lambda_ref = float(ground_truth["results"]["Lambda_ref"])

    def feasible(x: tuple[int, ...]) -> bool:
        if sum(x) != instance.K:
            return False
        if any(sum(x[index] for index in members) > instance.C for members in instance.sectors):
            return False
        spend = +0.0
        for index, bit in enumerate(x):
            spend = spend + instance.prices[index] * float(bit)
        return spend <= instance.B

    classifier = DecodedClassifier(
        OriginalObjectiveService(lambda x: objective(instance, x), lambda_ref),
        feasible,
    )
    for encoding, record in payload["encodings"].items():
        require(record["T_E_size"] == len(record["T_E"]), f"{encoding} T_E count mismatch")
        require(record["X_E_size"] == len(record["X_E"]), f"{encoding} X_E count mismatch")
        decoded = []
        for state in record["T_E"]:
            x = tuple(state["x_bits"])
            decoded.append(x)
            if encoding == "slack":
                energy = slack_energy(
                    instance, x, tuple(state["auxiliary_bits"]), coefficients
                )
            else:
                energy = unbalanced_energy(instance, x, coefficients)
            require(
                energy.hex() == record["H_E_min_hex"],
                f"{encoding} tied-state energy mismatch",
            )
        unique = tuple(dict.fromkeys(decoded))
        require(
            [list(x) for x in unique] == [item["x_bits"] for item in record["X_E"]],
            f"{encoding} X_E decoding mismatch",
        )
        for x, item in zip(unique, record["X_E"], strict=True):
            require(objective(instance, x).hex() == item["objective_hex"], f"{encoding} objective mismatch")
            require(feasible(x) is item["hard_feasible"], f"{encoding} feasibility mismatch")
            require(classifier.label(x, f_star) == item["label"], f"{encoding} atomic label mismatch")
        require(
            classifier.label_set(unique, f_star) == record["set_label"],
            f"{encoding} set label mismatch",
        )

    print(
        "PASS named-point artifact integrity, bound hashes, reported tie energies, "
        "decoding, feasibility, and labels; T_E completeness remains for controlling review"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
