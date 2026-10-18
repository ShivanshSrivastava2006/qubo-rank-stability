# Gate 4 Exit-Readiness Packet — Final reviewed basis

**Status:** SUPERSEDED AS FINAL BASIS by the authorized B-1/B-2/B-3 corrective pass — NOT an acceptance
record, Gate-4 exit, or Gate-5 authorization. Refresh only after the current independent review and any
resulting bounded correction are complete.

## Purpose and authority boundary

This is a reviewer-owned readiness template, following the Gate-3 packet pattern. It assembles the evidence
and unresolved conditions that a future owner decision must examine; it does not decide whether Gate 4
should exit. The controlling current authority is *Process Approval — Gate 4 bounded encoding formulation
and conformance* in `research/decisions/DECISIONS.md`, together with its subsequent ownership corrections.

The bounded authorization excludes primary-instance exact ground-state certification, primary encoded
tie-set computation, reported primary A/B/C classification, grid sweeps, experiments, results, and
conclusions. The later M5 extension permits only the decoded-only classifier/service boundary and V-4/V-8
conformance; V-4 enumeration is restricted to isolated toy instances of at most 22 encoded variables.
Those exclusions remain in force unless and until a separate dated owner decision changes them.

## Final review snapshot

The reviewer filed the bounded M5 corrective handoff at 2026-08-26 14:06:52 IST and stopped. The lead independently
reviewed the reviewer's M5 work and corrective delta, the builder's F3/F1/F2/F5 contribution, and the final combined
Gate-4 snapshot. The snapshot was pinned at 2026-08-26 14:11:33 IST and re-verified byte-identical at the
end of review, including after ten mutation probes. The lead filed `RECOMMEND FINAL OWNER CONFIRMATION FOR
GATE 4` at 2026-08-26 14:21:46 IST with no blocking defects. The complete report and final hashes are in
the review log under that timestamp.

## Evidence currently available

| Area | Evidence | Present status |
|---|---|---|
| Primary coordinate/coefficient ledger | `research/g4/G4_PRIMARY_LEDGER.json`; bounded all-row conformance evidence | Reviewed on final snapshot; hash `9f1277cb...d71` |
| Slack/unbalanced formulations and M4 separation | `src/g4/**`; V-18/formula/penalty checks | Reviewed and confirmed on final snapshot |
| Canonical D015 §5.2 residual-form evaluator | `src/g4/energy.py` and `research/g4/verify_g4_energy.py` | Reviewed; normal verifier exit 0 in 313 seconds |
| F3/F1/F2/F5 corrective contribution | the builder handoff plus the lead's final combined review | Independently reviewed; three non-blocking findings recorded |
| M5 decoded-only classifier interface | `src/g4/classification.py`; `research/g4/verify_m5_conformance.py` | Produced by the reviewer; corrective delta and five mutations independently confirmed normal and `-O` |
| Final combined review | the review log, 2026-08-26 14:21:46 IST | No blocking defects; recommends final owner confirmation |

## Verified facts and limitations to carry forward

1. The primary coordinate/coefficient ledger is bound to accepted canonical and ADNYE inputs and was
   independently reviewed on the final snapshot at SHA-256
   `9f1277cb642697786f8a7216382199e376c28a40e272d1d7039c5c693c4dad71`.
2. The canonical residual-form evaluator is required because D015 compares canonical `H_E`, not a
   cancellation-prone expanded `Qubo.energy` accumulation. Observed expansion drift therefore cannot be
   used as the canonical tie/comparison path.
3. The evaluator's current measured cost is a limitation, not an arithmetic failure: `slack_energy` was
   measured at approximately **830.7 microseconds/call** versus approximately **3.5 microseconds/call**
   when the frozen objective/residual intermediates are cached, a **236.6x** difference caused by repeated
   validation placement. This packet makes no claim about a repair, its ownership, or downstream execution.
4. `research/g4/verify_g4_energy.py` completed successfully in **313 seconds**. The earlier 300-second
   timeout was thirteen seconds short of completion and is superseded as outcome evidence, while remaining
   useful execution-cost history.
5. M5 scope was implemented for the decoded-only service boundary and V-4/V-8 conformance, with stated
   exclusions retained. V-4 permits exact ground-state and full encoded-tie enumeration only for isolated
   toy instances of at most 22 total variables, solely as conformance. The reviewer Medium produced it; the lead
   independently reviewed it; an auxiliary tool remains a non-blocking independent auditor.
6. Expanded-matrix drift reached **3279.9x** D015 tolerance. Every later comparison must use the canonical
   residual-form evaluator, never expanded-QUBO accumulation.
7. The lead recorded three non-blocking findings: the algebra conformance tolerance has scale-dependent
   detection power (B-1); the AST scanner can be evaded despite being adequate against accidental changes
   to hash-pinned code (B-2); and the energy verifier loads a lead-owned oracle that is not itself pinned
   or hash-checked before loading (B-3). B-1 and B-3 must be closed before Gate-4 evidence is relied on by
   a later gate; this packet does not silently treat them as fixed.
8. V-4's toy has no auxiliary degeneracy. D013's later inactive-coefficient case must not assume one lift
   per decoded state without explicitly handling symbolic auxiliary multiplicity.

## Exit-readiness disposition — reopened for corrective review

The evidence above describes the 14:11:33 snapshot and remains historical evidence. The owner subsequently
authorized the reviewer's B-1/B-2/B-3 verifier hardening; the reviewer filed its handoff at 14:58:45. The lead's independent
review of that new snapshot is in progress. Interim review confirms B-1's executable derivation and B-3's
pinned digest, but demonstrates additional B-2 evasions and notes a B-3 hash/check-load race. Required
energy runs were still pending when this packet was refreshed. Therefore this packet is not presently an
owner-exit basis.

Before exit, B-1/B-2/B-3 require a completed independent disposition on one unchanged final snapshot. The
eventual owner decision should also supersede the four stale predeclaration passages identified in `progress.md` at 2026-08-26
01:39:43 IST by pointing to the already approved D011 and V-14 decision-register entries. Frozen
specification history should not be silently rewritten.

## Explicit non-claims

This packet reports no primary ground state, minimum, tie set, decoded classification result, A/B/C rate,
grid sweep, experiment, scientific result, Gate-4 acceptance, Gate-4 exit, or Gate-5 authorization. It does
not claim that the downstream-scale evaluator architecture, B-1, B-2, or B-3 has been repaired.
