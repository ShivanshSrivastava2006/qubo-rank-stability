# Gate 4 — M5 Scope Question for Owner Decision

**Status:** SCOPE AND OWNERSHIP RECORDED 2026-08-26 — implementation, independent review, and Gate-4 exit
remain open.

## Why this question exists

The frozen Gate-1 charter assigns M5 to the Class-B obligations that G4 must enforce:

> M5 — decoded-object classification declaration: the classifier accepts only decoded `x`, `f*`, and the
> original feasibility predicate — no energy, no encoding identity.

`research/00_specifications/GATE_1_CHARTER.md` §7 then states that Class B is specifically M4 and M5,
declared at G1 and enforced at G4. `FROZEN_MATH_SPEC.md` §7 repeats the mapping: M5 is the decoded-only
classifier interface and separate service, enforced through V-4/V-8/G4.

The original direct Gate-4 authorization covered coordinate/coefficient ledgers, objective/residual/slack/
unbalanced modules, explicit QUBO formulation, V-18, formula/ledger conformance, and feasible-state
penalty behavior, while excluding classifier/tie-set work. On 2026-08-26, the owner extended G4 solely to
enforce M5's decoded-only classifier/service boundary and V-4/V-8 conformance checks, including isolated
toy fixtures as required. The extension retains its stated prohibitions, including primary-instance exact
ground-state certification, encoded tie-set computation, reported A/B/C classification, experiments,
results, conclusions, and Gate-5 work.

This is an authority/scope question, not a defect in the produced QUBO values or their bounded conformance
evidence.

## Frozen M5 boundary that must be preserved

The governing rules distinguish two objects:

1. The encoded-energy path forms `T_E` from canonical `H_E`; it does not decide original optimality.
2. The separate original-objective service forms `OPT_f(x)` from its immutable D015 configuration and only
   decoded `x`, `f*`, and an independent original-feasibility predicate. It receives neither encoded energy
   nor an encoding identity.

The resulting decoded labels are fixed by D016:

```text
A_x = OPT_f(x)
B_x = feasible(x) and not A_x
C_x = not feasible(x)
```

The primary aggregate partition is likewise frozen: exists `C` first; otherwise all `A`; otherwise `B`.
Any later scope decision must retain this separation and must not use an encoded energy, encoding name, raw
auxiliary multiplicity, or post-result choice to decide `OPT_f` or a decoded label.

## Mapped M5 items and the approved boundary

The frozen rule assigns the enforcement boundary to G4. The dated extension supplies limited scope, and the
later ownership amendment names the reviewer Medium as producer and the lead as independent M5 reviewer; its explicit
exclusions remain binding.

| Item | Frozen source | Current authorization state |
|---|---|---|
| Decoded-only classifier/service interface | Charter §7 M5; frozen spec §§5.3, 6, 7 | Authorized; the reviewer Medium is producer and the lead is independent M5 reviewer |
| Isolation proof/test: classifier receives no encoded energy or encoding identity | Charter §7 M5; frozen spec §5.3 | Authorized as M5 conformance; same producer/reviewer split |
| V-8 hand-constructed A/B/C classification cases | `VALIDATION_SPEC.md` V-8 | Authorized as conformance only; no reported A/B/C classification |
| V-4 full-pipeline toy ground-state/tie-set check | `VALIDATION_SPEC.md` V-4 | Authorized only for isolated toy instances of at most approximately 22 total variables, solely as conformance; primary/result-producing tie computation remains prohibited |
| Any use of the classifier on an actual encoded tie set | D015/D016; frozen spec §§5–6 | Not authorized; this would require an encoded tie set |

The table makes no implementation decision or ownership assignment. It preserves the owner-approved scope
and its exclusions for the future producer/reviewer plan.

## Authorization now recorded; remaining boundary controls

The owner recorded the following dated authorization in `research/decisions/DECISIONS.md`:

> Approved: extend Gate 4 solely to enforce M5’s decoded-only classifier/service boundary and its V-4/V-8
> conformance checks, including isolated toy fixtures as required. This does not authorize any
> primary-instance ground-state certification, encoded tie-set computation, reported A/B/C classification,
> experiment, result, conclusion, or Gate 5 work. Gate 4 remains open pending producer handoff,
> independent review, and my explicit final exit decision.

The owner subsequently clarified V-4, then superseded the deferred M5 ownership after the builder filed its
F3/F1/F2/F5 handoff: the reviewer Medium is the sole M5 producer; the lead is the independent M5 reviewer; an auxiliary tool is
a non-blocking independent auditor; the reviewer remains paused from producer work; the builder is relieved of further
G4 work. The approval does not take a Gate-4 exit; the final snapshot still needs independent review.

## Explicit non-actions

This document creates no classifier, no original-optimum recomputation, no ground-state search, no encoded
tie set, no A/B/C label, no rate, no experiment, no result, and no Gate-4 or Gate-5 exit decision.
