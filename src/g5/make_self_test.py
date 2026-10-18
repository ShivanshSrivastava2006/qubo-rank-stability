import json
import math
import hashlib
from pathlib import Path
import sys
import random

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.g4.instance import load_instance
from src.g4.parameters import load_coefficients
from src.g4.energy import (
    objective,
    residuals,
    slack_energy,
    unbalanced_energy,
    SLACK_AUXILIARY_LENGTH
)

INSTANCE_PATH = ROOT / "research/canonical/stage1_instance.json"
LEDGER_PATH = ROOT / "research/g4/G4_PRIMARY_LEDGER.json"
OUTPUT = ROOT / "research/g5/worker_self_test.json"

def make_bits(index, length):
    return tuple((index >> i) & 1 for i in range(length))

def main():
    instance = load_instance(INSTANCE_PATH)
    
    x_zeros = tuple(0 for _ in range(20))
    x_ones = tuple(1 for _ in range(20))
    x_star = tuple(1 if i in (3, 9, 11, 12, 15, 18) else 0 for i in range(20))
    
    cases = []
    
    special_states = [x_zeros, x_ones, x_star]
    special_rows = [0, 30, 60]
    encodings = ["slack", "unbalanced"]
    
    rng = random.Random(42)
    
    for state in special_states:
        for row in special_rows:
            for enc in encodings:
                if enc == "slack":
                    aux = make_bits(rng.randint(0, (1<<SLACK_AUXILIARY_LENGTH) - 1), SLACK_AUXILIARY_LENGTH)
                    cases.append((state, row, enc, aux))
                else:
                    cases.append((state, row, enc, ()))
                
    while len(cases) < 64:
        state = make_bits(rng.randint(0, (1<<20) - 1), 20)
        row = rng.randint(0, 60)
        enc = rng.choice(encodings)
        if enc == "slack":
            aux = make_bits(rng.randint(0, (1<<SLACK_AUXILIARY_LENGTH) - 1), SLACK_AUXILIARY_LENGTH)
            case = (state, row, enc, aux)
        else:
            case = (state, row, enc, ())
        if case not in cases:
            cases.append(case)
            
    cases.sort()
    
    results = []
    for state, row, enc, aux in cases:
        coefs = load_coefficients(LEDGER_PATH, row, row, row)
        f_val = objective(instance, state)
        h_card, h_sector, h_budget = residuals(instance, state)
        
        if enc == "slack":
            h_e = slack_energy(instance, state, aux, coefs)
            case_dict = {
                "state_bits": state,
                "auxiliary_bits": aux,
                "ledger_row": row,
                "encoding": enc,
                "expected_f_hex": f_val.hex(),
                "expected_h_card_hex": h_card.hex(),
                "expected_h_sector_hex": [h.hex() for h in h_sector],
                "expected_h_budget_hex": h_budget.hex(),
                "expected_H_E_hex": h_e.hex()
            }
        else:
            h_e = unbalanced_energy(instance, state, coefs)
            case_dict = {
                "state_bits": state,
                "ledger_row": row,
                "encoding": enc,
                "expected_f_hex": f_val.hex(),
                "expected_h_card_hex": h_card.hex(),
                "expected_h_sector_hex": [h.hex() for h in h_sector],
                "expected_h_budget_hex": h_budget.hex(),
                "expected_H_E_hex": h_e.hex()
            }
        results.append(case_dict)
        
    payload = {
        "schema": "g5-worker-self-test-vector/v1",
        "authority": "DECISIONS.md — Process Approval — GATE 5 authorization",
        "purpose": "Proves worker environment reproduces exact binary64 energy outputs.",
        "cases": results
    }
    
    canonical_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    payload["content_sha256"] = hashlib.sha256(canonical_bytes).hexdigest()
    
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE {OUTPUT.relative_to(ROOT)} content_sha256={payload['content_sha256']}")

if __name__ == "__main__":
    main()
