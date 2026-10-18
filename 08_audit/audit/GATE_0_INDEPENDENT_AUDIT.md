# Gate 0 Closure Audit and Approval Packet

**Audit date:** 2026-08-23  
**Auditor:** the reviewer  
**Verdict:** **CLOSURE AUDIT PASSED. Gate 0 APPROVED by Shivansh, 2026-08-23. Gate 1 entry is authorized.**

> **Re-verification note (The reviewer, 2026-08-23).** The validation-item summary and prototype-ordering
> limit added during packet review were independently checked against the authoritative validation and
> prototype-audit records, then adopted into this audit. They do not alter any decision, verdict, or
> verification result.

This is an audit and approval packet. It records no new scientific decision, does not change a decision
status, and does not authorize implementation by itself.

## What Was Audited

- Current authoritative status and decision surfaces: `STATUS.md`, `DECISIONS.md`,
  `UNRESOLVED_DECISIONS.md`, and `SCOPE_AMENDMENT_001.md`.
- Gate-0 implementation and validation specifications.
- D004/D005/D006 propagation, including units, rescaling, cardinality exclusion, the R2 conditioning,
  sensitivity non-selection, numerical evaluation requirements, and status separation.
- Retraction-ledger grammar, F19 orphan-marker guard, and approved F18 scan-scope policy.

## Closure Result

The approved mapping is internally specified and mechanically checked:

| Item | Current disposition |
|---|---|
| D001 | Approved objective-normalized dimensionless penalty parameterization |
| D002 / U-01 | Approved 3-D joint grid; U-01 closed |
| D004 / U-16 | Approved corrected unbalanced parent family |
| D005 / U-15 | Approved native minimum-attainable-violation rule; numeric `(1,1,5)` remains pending canonical G2 data |
| D006 / U-18(a,b) | Approved jointly: `c_j=1`, R2 `r=1`, sector/budget inequalities only; sensitivities `r in {0.5,2}` fixed and non-selectable |
| U-06 | Closed: 39-variable scope-lock formulation |

D006's non-neutral conditioning is preserved: R2 matches at `w=1` only and has local gap
`D(w)=a(s)w(1-w)`. It must not be described as a neutrality result or as a prediction of A/B/C outcomes.

## Verification Run

All commands exited zero on 2026-08-23:

1. `verify_amendment_001.py`
2. `verify_gate0_review_findings.py`
3. `verify_d006.py`
4. `verify_gate0_facts.py`
5. `verify_u15.py`
6. `verify_u16.py`
7. `verify_u17.py`
8. `verify_u18a.py`
9. `audit_u15.py` (11/11)
10. `check_retractions.py`
11. `check_retractions.py --selftest` (14 tags, 431 assertions)

The ledger's scan scope is intentionally limited to the declared `research/` manifest. Append-only
collaboration logs are historical records governed by retraction-by-later-entry; see
`SCAN_SCOPE_POLICY.md`. F16 paraphrase/semantic equivalence remains a manual-review limitation.

## Validation Items

The validation specification is part of what Gate 0 freezes, so its live caveats are recorded here.
**None has been executed as a downstream encoded-QUBO or experimental validation.** The approved V-15
homogeneity derivation has been run as a specification verifier; V-17 and V-18 await their later-stage
implementations and data. This distinction is intentional.

| Item | State at G0 closure |
|---|---|
| **V-15** — objective-rescaling invariance `[CRITICAL, T2]` | The **frozen** `[SCOPE §14]` mapping **FAILS** this test (verified: the unbalanced decoded ground state flips between `c = 2` and `c = 6` while slack's never moves). The **approved** mapping passes it **analytically** — a term-by-term homogeneity proof over all `gamma > 0`, not a finite-decade regression (`verify_d006.py` §5, satisfying charter finding M3). This is the item that would have caught C0-01 automatically. |
| **V-17** — certified `alpha` bound `[CRITICAL, T2]` | **Reframed** after C1-01. Split into classification correctness at **all** grid points, and threshold certification **only where a threshold is claimed**. The earlier "no off-cardinality ground state at any grid point" requirement was **withdrawn** as incompatible with D002's deliberate weak-`s_card` sweep. `alpha > Lambda_ref` remains **withdrawn** as a sufficient criterion (C0-05). |
| **V-18** — residuals vs. an independent feasibility predicate `[CRITICAL, T3]` | **New** from C0-07; shared-residual code does not by itself prevent bias. Unexecuted. |

## Known Limits and Deferred Work

These are not Gate-0 closure blockers, and this packet does not resolve them:

- **Prototype asset-ordering defect (CRITICAL).** `mu.csv` / `Sigma.csv` are **alphabetically**
  ticker-indexed while `prices` / `sector_map` are **sector-grouped**, and nothing reindexes — **18 of 20
  positions are mis-joined**. Root cause: the data pipeline's `yf.download` result is alphabetically
  ordered. **Consequence: the prototype's numeric portfolio results are NOT trustworthy as financial
  statements.** The abstract mathematical machinery, enumeration logic, constraint arithmetic, and
  constraint parameters `K`, `C`, `B`, `alpha`, and `prices` are unaffected; `mu`/`Sigma` must instead be
  joined by ticker. This makes G2 canonical-data reconstruction a required correctness repair, not merely
  pending work. Source: `research/audit/PROTOTYPE_AUDIT.md` F-1; independently reproducible by
  `research/audit/verify_gate0_facts.py`.
- U-02, U-03, U-04, U-05, U-07, U-08 through U-14, and U-17 remain open.
- D003 remains pending.
- Canonical data assembly has not occurred — **and per the ordering defect above it is a correctness
  repair, not merely pending work**. Prototype-derived budget-support counts and `(1,1,5)` are
  expected/pre-canonical, not canonical facts.
- No experiment, Stage-2 generation, encoded-QUBO certification, or ground-truth result exists.
- The Scope Lock's literature record, technical-report PDF, and archive remain outside this audit's
  independent verification boundary as recorded in the Gate-0 log.

## What Human Gate-0 Approval Authorizes

Approval satisfies Gate-1 entry criterion E1. Together with already-met E2--E5, it authorizes **entry to
Gate 1 only**: freeze and validate the executable mathematical specification and resolve decisions assigned
to that gate.

It does **not** authorize:

- changing D004/D005/D006 or selecting a sensitivity calibration after results;
- treating pre-canonical data-derived values as canonical;
- canonical-data assembly (G2), original-problem ground truth (G3), encoding work (G4), QUBO
  certification (G5), experiments (G6--G9), or final scientific conclusions (G10);
- resolving any deferred scientific decision without its own recorded approval.

## Human Approval Record

> **Gate 0 APPROVED, 2026-08-23, Shivansh.** The Gate-0 closure audit is accepted and entry to Gate 1
> only is authorized. D001, D002, D004, D005, and D006 remain scoped exactly as recorded. No experiment
> or downstream gate is authorized by this approval.
