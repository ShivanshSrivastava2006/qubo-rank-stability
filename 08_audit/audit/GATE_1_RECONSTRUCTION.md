# Gate-1 Source-First Reconstruction (W5)

**Status:** COMPLETE — review artifact, not a scientific decision or result.  
**Date:** 2026-08-25  
**Method:** Reconstruct the current mathematics from the approved Scope Lock
amendment and decision records first, then compare that reconstruction with
`research/00_specifications/FROZEN_MATH_SPEC.md`. This is independent of the
consolidation's prose path, but it is not a claim of model or organizational
independence.

## Sources and boundary

Read as authority: `RESEARCH_SCOPING_AND_SCOPE_LOCK.md`,
`research/decisions/SCOPE_AMENDMENT_001.md`, D001/D002 and D004–D016 in
`research/decisions/DECISIONS.md`, and the W0b approval. Read only for the
comparison target: the frozen charter and frozen math specification.

This reconstruction uses no canonical input data, prototype numeric output,
ADNYE record, QUBO, solver, ground state, or experiment. It therefore checks
rule agreement and declared interfaces only.

## Reconstructed approved system

| Area | Reconstruction from authority | Comparison result |
|---|---|---|
| Original objective | `f=-mu^T x+kappa_risk*x^T Sigma x`; D007 fixes `(1.0,(decimal simple daily return)^-1,daily)` and no conversion | matches §3.1 |
| Feasible population | `x in {0,1}^20`, cardinality `K=6`, four sector caps `C=2`, budget `p^T x<=B=1100`; `X*` is a set | matches §3.1 |
| Normalizer | D008: `max_F f-min_F f`, unit `E`, rule only; zero stops G3; five candidates transparency-only | matches §3.2 |
| Cardinality map | D002 amendment / D009: `alpha=s_card*Lambda_ref/v_card^2`, no threshold claim | matches §4.1 |
| Violation scales | D005/D009: `v_card=1` and `v_sector=1` are exact; `v_budget` is determined against the later canonical instance | matches §2/§4.1 |
| Primary inequalities | D006: outer scale `Lambda_ref`, `r=1`, rationalized `a_r`, and the stated `lambda_S/lambda_1/lambda_2` maps | matches §4.1 |
| D006 conditioning | `D(w)=a(s)w(1-w)<0` for `w>1`; no outcome prediction | matches §4.1 |
| Domain / density | D010: common cube from `rho_box=Delta_full/Lambda_ref`, `m_hi=1`, `m_lo=4`; D012: 10 base-10 intervals per decade incl. endpoints | matches §4.2–§4.3 |
| Required companions | D006 `r={0.5,2}` and D011 curvature match are non-primary; no post-result replacement | matches §4.1–§4.2 |
| Deferred outputs | D014 admits exactly ADNYE-001 and ADNYE-002 under its closed provenance contract; neither is executed | matches §3.2 |
| Binary64 ties | D015 fixes canonical unshifted ledger, finite fail-closed path, separate `T_E` / encoding-blind `OPT_f`, `(2048,2048)` primary and four diagnostics | matches §5 |
| Coordinates / coefficients | D010/D012 determine the exact mathematical grid; D006/D009 determine maps. W2, under W0b, adds a labelled operational RN-even transcription for reproducibility; it is not a decision-record rule | matches §4.3; no scientific map altered |
| Labels and reporting | D016 deduplicates to `X_E`, then `exists C -> C; else all A -> A; else B`; decoded denominators only | matches §6 |
| Conditional ablation | D013 exact all-three-sign trigger, conditions `{C,CB,CS,CSB}`, active axes, primary classification only | matches §6 |
| Provenance | D014 record digest and separate D015/D016 decision hashes; none substitutes for another | matches §5.3/§6 |

## Explicit disagreement search

I tested for the failure patterns that previously caused Gate-1 regressions:

1. `kappa_risk` is stated as `E^-1`, not the residual unit `R^-1`.
2. `Lambda_ref` is the D008 range over predicate-defined `F`, not a population
   count, standard deviation, full-space normalizer, or an approved number.
3. `Delta_full` is only D010's box input and ADNYE-001 field; it is not a
   replacement normalizer.
4. `alpha` retains the explicit `v_card^2` denominator and is sourced to D002,
   not spuriously derived from dimensional analysis.
5. D006 uses the rationalized numerical rule for every `r`, including the two
   diagnostics; cardinality receives no invented `r` mapping.
6. D011 is a known-biased non-primary companion; D015's diagnostic tolerance
   pairs are `(1024,2048)`, `(4096,2048)`, `(2048,1024)`, `(2048,4096)`, not
   the superseded numbers retained in the U-14 supporting draft.
7. `T_E` uses encoded energy only; `OPT_f` uses the independent original-object
   service only; raw slack multiplicity never weights decoded classification.
8. D013 consumes primary classification only, and D016's partition is proved
   for every nonempty finite decoded set rather than a bounded enumeration.

No disagreement remained after W2's two self-audited repairs: distinct symbols
for sector membership and slack values, and the D009 distinction between exact
`v_sector` and canonical-data-dependent `v_budget`.

## Limits carried forward

The reconstruction does not certify a typed G2 input file, canonical ticker
join, source date window, ADNYE JSON/sidecar, coordinate value, coefficient,
QUBO, ground state, oracle outcome, A/B/C rate, D011 coarse extent, or V-14
execution reading. Those are later-gate outputs or pre-execution commitments;
their governing rules are frozen above.

## W5 conclusion

The source-first reconstruction agrees with the frozen Gate-1 mathematical
specification. W5's document-level requirement is complete. Gate-1 remains
active pending final artifact verification and a separate human Gate-1 exit
approval; this conclusion grants neither.
