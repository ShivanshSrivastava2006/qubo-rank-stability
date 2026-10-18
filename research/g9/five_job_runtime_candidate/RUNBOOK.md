# WP8c Candidate Runbook

1. **Production Boundary**: WP8c currently has no real production boundary or provider. Any attempt to instantiate `AuthorityBoundary(..., production=True)` will raise an error explicitly stating: `"WP8c has no production implementation yet. The owner has not approved a production platform mapping, so any attempt to bind one is a fabrication."`
2. **Independent Pins**: The candidate now enforces independent, owner-pinned expected hashes.
   - **S4 Protocol Recheck**: The `EXPECTED_APPROVAL_HASHES` are pinned as constant hashes within the launcher, derived directly from the accepted protocol drafts (`GATE_9_STAGE2_PROTOCOL_DRAFT.md` and two amendments). They are no longer obtained dynamically via `read_approval_hashes()`. The gate now strictly rejects the session if the on-disk drafts are modified.
   - **Generator & Ground Truth**: The expected generator implementation record and ground truth provenance hashes are now independent constants (`EXPECTED_GENERATOR_IMPLEMENTATION_RECORD_SHA256` and `EXPECTED_GROUND_TRUTH_PROVENANCE_SHA256`) rather than reflecting the `verified_instance` mapping back to itself. This ensures any modified instance or mismatched pin is strictly rejected.
   - **Manifest Scan**: The `_scan_for_pending` check is now a total scan covering all leaves (including dict keys and bytes) and handles reference cycles using a visited set. It is applied across the manifest, acceptance record, authorization, session identity, and observations. A planted token-looking string will fail closed.
3. **Required Artifacts**:
   - `GATE_9_WP8A_PRODUCTION_IDENTITY_ACCEPTANCE.json` (Owner acceptance record)
   - `GATE_9_WP8C_ONE_USE_APPROVAL_RECORD.json` (Owner one-use authorization)
   - `stage2_cuda_core_bridge.so` & `stage2_cuda_d013_inactive.so` (Compiled CUDA libraries)
4. **Execution Semantics**: The candidate will structurally fail cleanly and deterministically *before* any draw, write, or backend work occurs if any of these artifacts are missing, if any draft file hashes differ from the constants, or if a "PENDING" or "PROVISIONAL" string exists within the critical runtime records, preserving strict owner authority. Owner-gated approvals remain untouched and the system fails closed.
