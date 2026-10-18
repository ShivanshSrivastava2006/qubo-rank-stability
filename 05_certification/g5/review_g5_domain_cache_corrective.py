import sys
import math
import hashlib
import struct
import itertools
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.g4.instance import Instance
from src.g4.parameters import Coefficients
from src.g5.domains import (
    build_slack_domain_cache,
    prepare_slack_domain,
    PreparedDomainCache,
    BinaryDomain
)
from src.g4.energy import prepare_decoded_state, prepare_instance

def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)

# ---------------------------------------------------------
# 4. Independent fractional-residual minimizer oracle
# ---------------------------------------------------------
def _exact_minimizer_rule(h: float, q_max: int) -> list[int]:
    if not math.isfinite(h):
        raise ValueError("nonfinite h")
    if h <= 0.0: return [0]
    if h >= q_max: return [q_max]
    s1 = math.floor(h)
    s2 = math.ceil(h)
    if s1 == s2: return [s1]
    frac = h - s1
    if frac == 0.5: return [s1, s2]
    elif frac < 0.5: return [s1]
    else: return [s2]

def oracle_lifts_for_x(instance: Instance, x: tuple[int, ...], sector_bits: int = 2, budget_bits: int = 11) -> set[tuple[int, ...]]:
    h_sectors = [float(instance.C) - sum(x[i] for i in members) for members in instance.sectors]
    h_budget = float(instance.B) - sum(float(instance.prices[i]) * x[i] for i in range(len(x)))
    
    sector_max = (1 << sector_bits) - 1
    budget_max = (1 << budget_bits) - 1
    
    sector_choices = [_exact_minimizer_rule(h, sector_max) for h in h_sectors]
    budget_choices = _exact_minimizer_rule(h_budget, budget_max)
    
    lifts = []
    for s_vals in itertools.product(*sector_choices, budget_choices):
        packed = []
        for val in s_vals[:-1]:
            packed.extend((val >> d) & 1 for d in range(sector_bits))
        packed.extend((s_vals[-1] >> d) & 1 for d in range(budget_bits))
        lifts.append(tuple(packed))
    return set(lifts)

# ---------------------------------------------------------
# 2. Platform-independent logical-content digesting
# ---------------------------------------------------------
def portable_logical_digest(instance_sha: str, offsets: list[int], masks: list[int]) -> str:
    d = hashlib.sha256()
    d.update(instance_sha.encode('ascii'))
    for off in offsets: d.update(struct.pack('<Q', off))
    for m in masks: d.update(struct.pack('<I', m))
    return d.hexdigest()

def extract_ints(raw_bytes: bytes, type_code: str, byteorder: str) -> list[int]:
    element_size = 8 if type_code == "Q" else 4
    if len(raw_bytes) % element_size != 0:
        raise ValueError("Malformed buffer length")
    fmt = f"{byteorder}{len(raw_bytes) // element_size}{type_code}"
    return list(struct.unpack(fmt, raw_bytes))

# ---------------------------------------------------------
# Test Harness
# ---------------------------------------------------------
def run_acceptance_test(name: str, func) -> None:
    print(f"Running {name}...")
    try:
        func()
        print(f"  [PASS] {name}")
    except AssertionError as e:
        if "CURRENT DEFECT" in str(e):
            print(f"  [EXPECTED CURRENT FAILURE] {e}")
        else:
            print(f"  [UNEXPECTED INSTRUMENT FAILURE] {e}")
            sys.exit(1)
    except Exception as e:
        print(f"  [UNEXPECTED ERROR] {e}")
        sys.exit(1)

# ---------------------------------------------------------
# Tests
# ---------------------------------------------------------
def create_valid_toy():
    # 20 tickers, 4 sectors needed by prepare_instance
    return Instance(
        tickers=tuple(f"T{i}" for i in range(20)),
        sectors=tuple((i,) for i in range(4)),
        mu=(0.0,)*20, sigma=tuple((0.0,)*20 for _ in range(20)), prices=(1.0,)*20,
        kappa_risk=1.0, K=1, C=1, B=1.0
    )

def test_partition_binding():
    # 1. Exact sector/budget partition binding
    toy = create_valid_toy()
    coef = Coefficients(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
    
    # 4 sectors * 3 bits + 7 bits = 19 bits
    # Standard is 4 * 2 + 11 = 19 bits
    bad_cache = build_slack_domain_cache(toy, coef, sector_slack_bits=3, budget_slack_bits=7)
    
    try:
        prepare_slack_domain(toy, bad_cache)
    except (ValueError, TypeError):
        pass
    else:
        raise AssertionError("CURRENT DEFECT: prepare_slack_domain silently accepted alternate widths (sector=3, budget=7) that sum to 19.")

def test_misaligned_prepared_domain():
    # 3. Rejection of shuffled misaligned prepared-domain data
    toy = create_valid_toy()
    raw_domain = BinaryDomain(20)
    prep_inst = prepare_instance(toy)
    
    # Generate 2 valid states, clone the rest to bypass 2^20 expensive calls
    valid_state_0 = prepare_decoded_state(prep_inst, raw_domain[0])
    valid_state_1 = prepare_decoded_state(prep_inst, raw_domain[1])
    
    # Shuffled states: swap the first two
    shuffled_states = [valid_state_1, valid_state_0] + [valid_state_0] * ((1<<20) - 2)
    
    try:
        cache = PreparedDomainCache(raw_domain, tuple(shuffled_states), "unbalanced")
    except (ValueError, TypeError):
        pass
    else:
        raise AssertionError("CURRENT DEFECT: PreparedDomainCache silently accepted a misaligned state sequence.")

def test_fractional_oracle_self_test():
    # 4. Prove the oracle does not use premature int() coercion
    toy = replace(create_valid_toy(), C=1.5, B=1.5)
    
    x = (0,)*20
    lifts = oracle_lifts_for_x(toy, x, sector_bits=2, budget_bits=11)
    
    # h_sector = 1.5 -> minimisers: 1, 2. (4 sectors -> 16 combinations)
    # h_budget = 1.5 -> minimisers: 1, 2. (2 combinations)
    # Total combinations = 32.
    require(len(lifts) == 32, f"Oracle self-test failed: expected 32 tied lifts, got {len(lifts)}")
    
def test_preservation_and_reconstruction():
    # 5. Preservation of packed bit ordering and exact raw-state reconstruction
    toy = create_valid_toy()
    coef = Coefficients(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
    
    cache = build_slack_domain_cache(toy, coef, sector_slack_bits=2, budget_slack_bits=11)
    
    produced_lifts = []
    # Test only the first state (all zeros) for speed
    expected_x = (0,)*20
    for x, y in cache:
        if x != expected_x:
            break
        produced_lifts.append(y)
            
    expected_lifts = oracle_lifts_for_x(toy, expected_x, sector_bits=2, budget_bits=11)
    require(set(produced_lifts) == expected_lifts, "CURRENT DEFECT: Cache exact-minimizer reconstruction did not match the fractional oracle.")
    
def test_platform_independent_digest_self_test():
    # 2. Self-test proving the portable digest resolves endianness differences
    instance_sha = "0" * 64
    offsets = [0, 2, 4]
    masks = [10, 20, 30]
    
    le_offsets = struct.pack("<3Q", *offsets)
    le_masks = struct.pack("<3I", *masks)
    
    be_offsets = struct.pack(">3Q", *offsets)
    be_masks = struct.pack(">3I", *masks)
    
    le_extracted_off = extract_ints(le_offsets, "Q", "<")
    le_extracted_mask = extract_ints(le_masks, "I", "<")
    
    be_extracted_off = extract_ints(be_offsets, "Q", ">")
    be_extracted_mask = extract_ints(be_masks, "I", ">")
    
    digest_le = portable_logical_digest(instance_sha, le_extracted_off, le_extracted_mask)
    digest_be = portable_logical_digest(instance_sha, be_extracted_off, be_extracted_mask)
    
    require(digest_le == digest_be, "Portable digest self-test failed: endianness not resolved")

def test_explicit_fail_closed():
    # 6. Explicit fail-closed behavior under normal Python and python3 -O
    toy = create_valid_toy()
    
    class InactiveCoef:
        alpha = 1.0
        sector_slack = +0.0
        budget_slack = 1.0
        sector_linear = 1.0
        sector_quadratic = 1.0
        budget_linear = 1.0
        budget_quadratic = 1.0
        
    try:
        # should fail on _require_active_slack_coefficients
        build_slack_domain_cache(toy, InactiveCoef(), sector_slack_bits=2, budget_slack_bits=11)
    except (ValueError, TypeError):
        pass
    else:
        raise AssertionError("CURRENT DEFECT: Failed to explicitly fail-closed on inactive/invalid coefficients.")

def print_production_hashes():
    import subprocess
    print("\n--- Production Hashes Tested Against ---")
    files = ["src/g5/domains.py", "src/g5/certify.py", "research/g5/verify_domain_cache.py"]
    for f in files:
        output = subprocess.check_output(["sha256sum", f]).decode("utf-8").strip()
        print(output)

def main():
    run_acceptance_test("1. Exact partition binding", test_partition_binding)
    run_acceptance_test("2. Portable digest self-test", test_platform_independent_digest_self_test)
    run_acceptance_test("3. Misaligned prepared-domain rejection", test_misaligned_prepared_domain)
    run_acceptance_test("4. Fractional oracle self-test", test_fractional_oracle_self_test)
    run_acceptance_test("5. Bit preservation & state reconstruction", test_preservation_and_reconstruction)
    run_acceptance_test("6. Explicit fail-closed check", test_explicit_fail_closed)
    
    print_production_hashes()

if __name__ == "__main__":
    main()
