# Gate 1 Charter

**Status:** **FROZEN — AUTHORITATIVE GATE-1 CHARTER (W0b APPROVED)**  
**Gate:** G1 — executable mathematical specification  
**Created:** 2026-08-23  
**Frozen:** 2026-08-25  
**Authority:** Shivansh's direct W0b approval freezes this charter through D016. It is a governance freeze,
not a scientific decision, Gate-1 exit, ADNYE execution, or authorization for G2+ work.

## 1. Purpose

Gate 1 converts the approved research design into a frozen, executable mathematical specification for the QUBO encoding comparison. At Gate-1 exit, every downstream mathematical choice must be either an approved value or an approved deterministic rule, with its units, dependencies, and validation obligation stated.

The purpose is to eliminate downstream discretion: an implementation team must not need to decide what a symbol, penalty coefficient, tie, or comparison rule means.

## 2. Boundary

Gate 1 may draft and freeze mathematical rules, resolve the decisions assigned to this gate, create a bounded specification verifier, and document validation interfaces.

Gate 1 does **not** authorize:

- canonical ticker-keyed data reconstruction (G2 / U-07);
- original-problem ground truth or numeric `Lambda_ref` computation (G3);
- QUBO assembly or encoding implementation (G4);
- encoded-QUBO ground-state certification (G5);
- penalty-landscape or Stage-1/Stage-2 experiments (G6–G9); or
- scientific conclusions (G10).

No Gate-1 artifact may treat prototype portfolio outputs as financial ground truth: the documented 18/20 positional ticker join defect remains a G2 correctness repair.

## 3. Starting state and fixed premises

### Entry criteria

Entry criteria E1--E5 are met. E6 is **WITHDRAWN** as a standalone criterion and is folded into E1 as a documentation-integrity precondition. It must not be revived as a separate entry criterion.

Gate 0 is approved and Gate-1 entry is authorized. The following are already approved and must be carried forward exactly as scoped in `research/decisions/DECISIONS.md`:

- D001: objective-normalized, dimensionless penalty coordinate;
- D002 / U-01: three-dimensional joint grid `(s_card, s_sector, s_budget)`;
- D004: corrected unbalanced parent family;
- D005: per-constraint native minimum attainable positive violation rule; and
- D006: `c_j = 1` and R2 `a(s) = sqrt(1 + 2s) - 1` for inequality families only, with fixed `r in {0.5, 2}` sensitivities; and
- D007 / U-02: `kappa_risk = (1.0, (decimal simple daily return)^-1, daily)` as an indivisible value/unit/period triple, with no annualization or other horizon conversion absent a separately approved aggregation model. U-02 is closed and this triple binds U-07/G2 to build and verify conforming canonical returns.
- D008 / U-03: predicate-defined feasible-set range rule for `Lambda_ref`, with its numeric result admitted as an unexecuted ADNYE record; `Lambda_ref = 0` is a G3 stop condition, never a value to patch or substitute;
- D009 / U-13: the already-approved `alpha(s_card)` map, its specification propagation, and the no-threshold certification policy; and
- D010 / U-04: the deterministic common-cube domain-box rule, with its numeric box admitted as an unexecuted ADNYE record; and
- D011 / V-12: the required non-primary curvature-match companion (`a=2`, `Lambda_pen=s*Lambda_ref/2`) for inequality families, with its known positive local gap stated as conditioning; and
- D012 / U-05: the primary-grid density rule; D013 / U-12: the conditional four-condition ablation rule;
  D014: the field-5 ADNYE output-provenance contract for D008/D010; D015 / U-14: the separate
  canonical-binary64 encoded-energy and encoding-blind original-objective comparator rule; and D016 / U-17:
  the decoded mixed-tie primary partition and secondary reporting rule.

U-06 is closed: the Scope-Lock slack formulation has 39 variables. D006 is a conditioning choice, not a neutrality claim: for the primary R2 rule its local gap `D(w) = a(s) w (1-w)` is negative for every `w > 1`. The gap is hypothesis-aligned with H2 and confounds every `w > 1` comparison; it does not predict any A/B/C outcome. The reachable-support counts (2 of 3 sector cases and 1067 of 1068 budget cases) are **pre-canonical** expectations pending U-07/G2, not canonical facts.

For the approved D006 family, `a_r(s) = -r + sqrt(r^2 + 2s)` is the mathematical definition, but frozen numerical evaluation must use `a_r(s) = 2s / (sqrt(r^2 + 2s) + r)`. This general rule binds both the primary `r = 1` evaluation and the `r in {0.5, 2}` sensitivity evaluations; at `r = 1` it reduces to `2s / (sqrt(1 + 2s) + 1)`. The direct subtractive form is not an implementation option at small positive `s`.

## 4. Gate-1 decision set and order

Each item requires a human-approved decision record; a draft memo may recommend but never approve it.

1. **U-02 — CLOSED (D007):** `kappa_risk` fixes `f`, then the optimum set/value `X* / f*`, `Lambda_ref`, and the numerical penalty mapping. This completed dependency is why U-03 may now proceed.
2. **U-03 — CLOSED (D008):** `Lambda_ref = max_{x in F} f(x) - min_{x in F} f(x)` over predicate-defined
   `F`, units `E`, rule only. Its numeric value is an admitted prospective ADNYE record at
   `G3.compute_Lambda_ref`, not an approved number. **`Lambda_ref = 0` is a G3 stop condition:** it is never
   patched or substituted, and no dependent coefficient or box computation may proceed. This completed
   dependency supported the joint resolution of U-13 and U-04 in D009 and D010.
3. **U-13 — CLOSED (D009):** D002 / `SCOPE_AMENDMENT_001.md` §3 had already frozen
   `alpha(s_card) = s_card * Lambda_ref / v_card^2`; D009 propagates that approved map into the
   implementation specification and fixes the certification policy of no asserted enforcement threshold:
   V-17 obligation 1 remains unconditional, while obligation 2 is untriggered—not retired or waived—and
   binds any future threshold claim, which would need separate approval.
   **U-04 — CLOSED (D010):** the deterministic common-cube domain-box rule is frozen, with
   `rho_box = Delta_full / Lambda_ref`, derived `m_hi = 1`, and recorded judgement `m_lo = 4`. Its numeric
   bounds are an admitted prospective ADNYE record, not approved numbers.
4. **V-12 curvature-match companion — CLOSED (D011):** the dimensionally valid `a=2` mapping is fixed for inequality families as a required non-primary coarse companion. Its exact coarse-subgrid extent remains a pre-execution commitment; it must not be chosen after results.
5. **U-05 — CLOSED (D012):** primary three-axis grid density is `P=10` base-10 log intervals per decade,
   endpoints included; any refinement is separately declared and additionally reported, never a replacement.
   This does not settle a sensitivity-pass extent or V-14's expansion reading.
6. **U-12 — CLOSED (D013):** the exact conditional set `{C, CB, CS, CSB}`, D006 exact-sign trigger,
   active-axis D008/D010/D012 coordinates, applicable D006/D011/V-14 package, and R-U12-1 are frozen.
   The rule is a non-primary follow-up only; D016 now supplies its required primary classification.
7. **U-14 — CLOSED (D015):** the canonical binary64 encoded-energy ledger, separate encoding-blind
   original-objective comparator, primary `(c_H,c_f)=(2048,2048)`, four fixed diagnostics, provenance,
   oracle disposition, and R-U14-1 are frozen.
8. **U-17 — CLOSED (D016):** D015's `T_E` and encoding-blind `OPT_f` are consumed unchanged; atomic labels
   are assigned over distinct decoded `X_E`, and the frozen primary partition is `exists C -> C`, else
   `all A -> A`, else `B`, with the required raw/decoded and secondary reporting plus R-U17-1.

The order is binding for dependency management, not a scientific approval. U-07 belongs to G2; D003 and U-08–U-11 belong to the Stage-2 protocol.

## 5. Deferred numeric outputs (prospective ADNYE contract)

U-03 and U-04 may freeze deterministic rules at G1 while their numeric outputs are produced later without discretion. No prospective ADNYE record is admitted until its underlying rule is approved. D008 admits the numeric `Lambda_ref` record and D010 admits the three-axis domain-box record below; both remain unexecuted. **D014 now approves their shared field-5 output-provenance contract; it does not execute either record.**

An admitted prospective record must state all of the following:

1. deterministic rule;
2. named inputs;
3. declared dependency edges and an acyclic closure;
4. exact execution point;
5. standalone output location and content-hash scheme; and
6. prohibition on encoded-QUBO or result artifacts anywhere in its closure.

The only prospective candidates are:

| Record | Exact execution point | Inputs / dependency rule |
|---|---|---|
| Numeric `Lambda_ref` — **ADMITTED by D008; not executed** | `G3.compute_Lambda_ref` | Canonical `mu`, `Sigma`, D007 triple, canonical instance, and predicate-defined original-problem feasible set under D008 rule |
| Three-axis numeric domain box — **ADMITTED by D010; not executed** | `G3.exit.resolve_box`, after `Lambda_ref` and before `G4.start` | Resolved `Lambda_ref` record; `Delta_full = range_{x in {0,1}^20} f(x)` expressly authorized by D010 as the second input; and the approved D010 bound rule |

**D014 fixes field 5 for both rows:** their only permitted output location, branch behavior, schemas,
dependency references, source-attested snapshots, digest preimages, and chronology rule are the approved
ADNYE Output Contract revision 6. No record or validator is created at G1.

`alpha(s_card)` and all coefficient maps are functions across the grid, not ADNYE scalars. A cardinality-enforcement threshold certificate is an encoded-QUBO validation artifact, not an ADNYE record.

## 6. Required Gate-1 artifacts

Before exit, the project must contain:

- this authoritative charter, frozen after the required human approvals;
- approved decision records for every Section 4 item;
- `FROZEN_MATH_SPEC.md` with a complete symbol-and-units table and no unresolved mathematical marker;
- `research/audit/verify_gate1_math.py`, limited to claims that a Gate-1 verifier can actually check;
- a mapped `VALIDATION_SPEC.md` with explicit retirements where applicable;
- `research/logs/GATE_1.md`, including unresolved later-stage validations and provenance commitments; and
- an independent Codex reconstruction of the frozen specification followed by human exit approval.

## 7. Acceptance checks and verification limits

The frozen specification must establish each mapped requirement below.

1. **M1 — symbol completeness:** every symbol occurring in a frozen formula has a non-empty domain, units, source decision ID, and status.
2. **M2 — dimensional homogeneity:** every additive term of every energy expression is dimensionally coherent.
3. **M3a and M3b — objective-rescaling:** M3a is the required analytic, term-by-term proof of all-scale homogeneity. M3b is the separately required finite cross-decades regression witness. M3b is a regression witness only and must never be presented as establishing M3.
4. **M4 — encoding separation declaration:** the specification declares the module interfaces and requires the slack and unbalanced encodings to share residual definitions only — no shared penalty helper. G1 checks that declaration is present and complete; G4 enforces conformance through V-18.
5. **M5 — decoded-object classification declaration:** the classifier accepts only decoded `x`, `f*`, and the original feasibility predicate — no energy, no encoding identity.
6. **M6 — mixed ties (D016):** the A/B/C partition is mutually exclusive and exhaustive over distinct decoded portfolios `X_E` for every non-empty finite set, preserving the frozen Section 16 A rule. G1 requires an arbitrary-size proof; U-17 enumeration through size 4 is not sufficient.
7. **M7 — register arithmetic:** the 39-variable register-width derivation, with declared inputs and exactness over the whole QUBO domain.
8. **M8 — slack conditions:** the closed-form slack minimizer with its conditions, including behavior at `lambda_S = 0` and half-integer residuals.
9. **M9 — conditional claims:** every frozen formula cross-references its source decision ID and carries its conditioning assumption.
10. **M10 — pre-registration integrity:** no result artifact or run manifest predates approval of a decision it depends on, and every such artifact records the governing approved-decision hash and, when applicable, its resolved ADNYE-record hash.

**Class A (mechanically checkable at G1)** is M1, M2, M6, M7, M8, M9, plus the Section 5 field-3 dependency-edge/acyclic-closure declaration and field-4 exact-execution-point declaration. M3a and M3b are both required for the rescaling claim, with the distinct proof/witness roles stated above. **Class B (declared at G1 and enforced at G4)** is specifically M4 and M5: a G1 verifier may check the presence and shape of their declarations but cannot prove properties of G4 modules that do not yet exist. M10 is a narrow necessary audit-trail condition; its residual risk of unrecorded human exposure is procedural trust, not a verified property.

## 8. Exit criteria and handoff

Gate 1 exits only after:

1. all specified mathematical checks pass;
2. every Section 4 decision is approved with scope, approver, and date;
3. the frozen specification has no unresolved mathematical choices and enumerates every permitted prospective record;
4. Codex independently reconstructs the frozen specification and all disagreements are closed;
5. the human approves Gate-1 exit;
6. all Gate-1 artifacts pass the current retraction-ledger checks;
7. the Gate-1 log explicitly states what remains unverified for later gates; and
8. G2 receives typed, unit-specified interfaces without any presupposition of canonical ticker order.

## 9. Failure and return conditions

Gate 1 must stop and seek a scope amendment or return to Gate 0 if a frozen-scope mathematical defect is found, an acceptance check requires a new scope change, an approved decision conflicts with another approval, or a decision is shown to depend on observed results. A retracted Gate-0 claim reappearing in a Gate-1 artifact is also a stop condition until corrected and independently checked.

## 10. Frozen status

This document is authoritative for Gate-1 mathematical definitions and approved decision interfaces through
D016. It does not itself authorize data assembly, numeric ADNYE execution, encoding implementation,
certification, experiment, parameter selection after results, Gate-1 exit, or G2+ work. Changes require a
new dated human approval and must identify any result already observed.
