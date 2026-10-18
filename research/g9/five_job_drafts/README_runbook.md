# WP8 Production Runbook (DRAFT)

**Status:** DRAFT_INVALID_UNARMED
This runbook limits itself strictly to Gate-9 Stage-2 Pre-result Protocol. No scientific work is executed by this artifact.

## 1. Overview
This directory contains five draft job manifests (`stage2_01` through `stage2_05`) and their corresponding assembly skeleton. They are strictly drafts. All real instance, prepared, release, and identity hashes remain explicitly PENDING. Source dependencies snapshot hashes are PROVISIONAL with invalidation rules.

## 2. Session Execution Rules
* **One Session Per Accepted Instance:** Each accepted instance slot (`stage2_01` to `stage2_05`) requires one independent production session.
* **Missing-Range Resume:** If a run stops (e.g. at the 10-hour Kaggle bound), incomplete receipts require a missing-range resume in a *new* session, bound by a new owner one-use authority.
* **No Invented Runtime or External Queries:** Schedule scenarios must be parameterized strictly by eventual measured WP3 runtime and owner-reported GPU availability. Do not perform account, quota, or API queries. Do not invent runtimes.
* **Pre-run and Postrun Strict Gates:** Intermediate pre-run logs may update drafts only. Finalization or launch strictly requires a complete, accepted pre-run and postrun audit, and separate production gates must be passed.
* **Invalidation:** Any source, interface, input, or hash changes immediately invalidate the affected drafts and trigger an exact-byte review. No early-launch recommendations are permitted.

## 3. Operations
* **Verify Drafts:** Run `python -B check_drafts.py` to synthetically verify slot bindings, enforce pending-gate refusal, and validate schema without performing structural mutations.
* **WP8c Production Note:** WP8c production session (copies/wp8c.VL2P) remains UNREVIEWED. All designs here incorporate its interface assumptions ONLY. It is marked as PENDING and not imported, copied, or certified.
* **Pending Gates:** D013 release/T4 qualification, accepted pre-run completion/postrun audit, production identity/inputs/write approval/push approval are explicitly PENDING.
* **Execution Environment Constraints:** 
  * Scratch space configured at `/home/shivansh-srivastava/decisions_os/g9_jobs/scratch/five-job-drafts`.
  * Compute limits: `<=1` worker, `Nice10` priority.
  * No Python bytecodes (`PYTHONDONTWRITEBYTECODE=1` / `python -B`).
  * No installs, upgrades, removals, network calls (except modelAPI), pattern kills (`rm -rf`, `/tmp`), or unreviewed source edits.
