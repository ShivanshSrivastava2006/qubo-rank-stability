import json
import math
import hashlib
from pathlib import Path
import sys
import copy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.g4.instance import load_instance
from src.g4.parameters import load_coefficients
from src.g4.energy import (
    objective,
    prepare_coefficients,
    prepare_decoded_state,
    prepare_instance,
    prepare_slack_state,
    residuals,
    slack_energy,
    slack_energy_prepared,
    unbalanced_energy,
    unbalanced_energy_prepared,
)

INSTANCE_PATH = ROOT / "research/canonical/stage1_instance.json"
LEDGER_PATH = ROOT / "research/g4/G4_PRIMARY_LEDGER.json"
VECTOR_PATH = ROOT / "research/g5/worker_self_test.json"

def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)

def run_tests(payload, instance):
    prepared_instance = prepare_instance(instance)
    for idx, case in enumerate(payload["cases"]):
        state = tuple(case["state_bits"])
        row = case["ledger_row"]
        enc = case["encoding"]
        coefs = load_coefficients(LEDGER_PATH, row, row, row)
        prepared_coefs = prepare_coefficients(coefs)
        prepared_state = prepare_decoded_state(prepared_instance, state)
        
        f_val = objective(instance, state)
        h_card, h_sector, h_budget = residuals(instance, state)
        
        require(f_val.hex() == case["expected_f_hex"], f"Case {idx} f_hex mismatch: {f_val.hex()} != {case['expected_f_hex']}")
        require(h_card.hex() == case["expected_h_card_hex"], f"Case {idx} h_card mismatch")
        for i, h in enumerate(h_sector):
            require(h.hex() == case["expected_h_sector_hex"][i], f"Case {idx} h_sector mismatch")
        require(h_budget.hex() == case["expected_h_budget_hex"], f"Case {idx} h_budget mismatch")
        require(prepared_state.f_value.hex() == case["expected_f_hex"],
                f"Case {idx} prepared f_hex mismatch")
        require(prepared_state.h_card.hex() == case["expected_h_card_hex"],
                f"Case {idx} prepared h_card mismatch")
        for i, h in enumerate(prepared_state.h_sector):
            require(h.hex() == case["expected_h_sector_hex"][i],
                    f"Case {idx} prepared h_sector mismatch")
        require(prepared_state.h_budget.hex() == case["expected_h_budget_hex"],
                f"Case {idx} prepared h_budget mismatch")
        
        if enc == "slack":
            aux = tuple(case["auxiliary_bits"])
            h_e = slack_energy(instance, state, aux, coefs)
            prepared_h_e = slack_energy_prepared(
                prepare_slack_state(prepared_state, aux), prepared_coefs
            )
        else:
            h_e = unbalanced_energy(instance, state, coefs)
            prepared_h_e = unbalanced_energy_prepared(prepared_state, prepared_coefs)
            
        require(h_e.hex() == case["expected_H_E_hex"], f"Case {idx} H_E mismatch: {h_e.hex()} != {case['expected_H_E_hex']}")
        require(prepared_h_e.hex() == case["expected_H_E_hex"],
                f"Case {idx} prepared H_E mismatch: {prepared_h_e.hex()} != {case['expected_H_E_hex']}")

def main():
    require(VECTOR_PATH.is_file(), "worker self test vector missing")
    buffer = VECTOR_PATH.read_bytes()
    payload = json.loads(buffer)
    
    # check digest
    expected_hash = payload["content_sha256"]
    
    # The canonical serialization used during creation
    # canonical_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    # Actually wait, content_sha256 is part of the payload, so we need to copy payload and compute hash.
    # The canonical generation was:
    # payload["content_sha256"] = hashlib.sha256(canonical_bytes).hexdigest()
    # So we must recreate canonical_bytes without content_sha256.
    
    payload_for_hash = copy.deepcopy(payload)
    del payload_for_hash["content_sha256"]
    canonical_bytes = json.dumps(payload_for_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    actual_hash = hashlib.sha256(canonical_bytes).hexdigest()
    require(actual_hash == expected_hash, f"digest mismatch: {actual_hash} != {expected_hash}")
    
    instance = load_instance(INSTANCE_PATH)
    
    # 1. Normal run
    run_tests(payload, instance)
    
    # 2. Negative test (alter expected value)
    payload_bad = copy.deepcopy(payload)
    # alter the first H_E_hex to an invalid one
    payload_bad["cases"][0]["expected_H_E_hex"] = "0x1.0000000000000p+0"
    try:
        run_tests(payload_bad, instance)
    except AssertionError as e:
        if "H_E mismatch" not in str(e):
            raise AssertionError("negative test failed with unexpected error")
    else:
        raise AssertionError("negative test failed to reject altered expected value")
        
    print("PASS worker self test")

if __name__ == "__main__":
    main()
