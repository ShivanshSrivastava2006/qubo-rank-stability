# Gate-5 Per-Shard Provenance Contract

This contract specifies the mandatory provenance information that every worker shard of the distributed Gate-5 execution must record. To ensure results are fully reproducible and attributable, no shard's output may be accepted unless it provides a complete and verifiable record meeting all requirements below.

## 1. Source and Input Hashes
Every shard must record the exact SHA-256 digests of:
- Every Python source file the shard executed (e.g., `energy.py`, `classification.py`).
- The primary evaluation artifacts:
  - `research/g4/G4_PRIMARY_LEDGER.json`
  - `research/canonical/stage1_instance.json`
  - `research/adnye/ADNYE-001_Lambda_ref.json`
  - `research/adnye/ADNYE-002_s_domain_box.json`

## 2. Governing Decision Hashes
The shard must record the governing decision hashes as required by the V-13 / M10 lineage validations to ensure the execution respects the correct authorized process state.

## 3. Worker Self-Test Certification
The shard must record the exact digest of `research/g5/worker_self_test.json`. It must also provide an explicit attestation that the worker executed and successfully passed the exact binary64 output expectations dictated by this self-test vector **before** evaluating any candidate states for the shard.

## 4. Platform Fingerprint
Because §5.2 execution demands exact binary64 reproducibility and forbids architectural deviations like fused multiply-add (FMA), the shard must record a comprehensive platform fingerprint, including:
- Python build information and version.
- OS, platform identification, and `libm` details.
- Active CPU flags, especially those relevant to FMA or extended-precision arithmetic.

## 5. Shard Bounds
The shard must record its exact coordinate range (e.g., subset of ledger rows, specific chunk of decoded states). This ensures global coverage is fully checkable and any missing gaps can be detected when results are merged.

## 6. Merge and Quarantine Rule
Before combining results from multiple shards, the aggregator must apply the following merge rule:
- Every contributing shard must exactly agree on the source file hashes, primary input hashes, governing decision hashes, and platform fingerprints.
- Every shard must present the required self-test attestation matching the authorized test vector.
- Any shard that fails to provide the required provenance, or whose hashes/fingerprints do not match the globally agreed-upon baseline for the execution, must be strictly **quarantined** and its results rejected.
