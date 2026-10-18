# G4 — Bounded encoding formulation and conformance provenance

**Status:** bounded B-1/B-2/B-3 repair produced, pending independent review. This is not a
Gate-4 acceptance or exit record.

## Authority and boundary

The direct 2026-08-25 authorization is recorded in `DECISIONS.md` under
*Process Approval — Gate 4 bounded encoding formulation and conformance*. It
permits primary coordinate/coefficient ledgers, separated encoding modules,
explicit QUBO formulations, and bounded conformance checks only.

The 2026-08-26 *Gate 4 bounded M5 enforcement extension*, its V-4
clarification, and the later ownership reassignment additionally authorize the reviewer
Medium alone to produce M5's decoded-only classifier/service boundary and
V-4/V-8 conformance. V-4 exact ground-state and full raw tie-set enumeration
is confined to isolated toy instances of at most 22 total encoded variables.
The lead is the independent M5 reviewer; an auxiliary tool is a non-blocking auditor.

It does not authorize primary-instance ground-state certification, primary
encoded tie sets, reported primary A/B/C classification, sweeps, experiments,
sensitivity/expansion execution, results, conclusions, or a Gate-4 exit.
Accepted G2/G3 evidence remains read-only. The
canonical section 5.2 evaluator `src/g4/energy.py` was produced by a builder
under the ownership records *Process Approval — Gate 4 ownership amendment* as
corrected twice (a builder, then a builder for the F3 finish), and its
arithmetic is untouched by this repair pass.

## Produced artifacts

| Artifact | SHA-256 |
|---|---|
| `research/g4/G4_PRIMARY_LEDGER.json` | `9f1277cb642697786f8a7216382199e376c28a40e272d1d7039c5c693c4dad71` |
| `research/g4/verify_g4_conformance.py` | `8c76d2af538b95c00af647775f1844db165dc5a80d5d103588fcd2dc5edce369` |
| `research/g4/verify_g4_energy.py` | `ec0cb84aff949dbf34f1ad2f729a7f140373272a3190ed4eb23932e47cf82729` |
| `04_encodings/g4/review_g4_energy_conformance.py` (read-only oracle) | `57da8154b278ec2a7ed107693c6973c7afb8092acc69579c974f92d320976831` |
| `research/g4/verify_m5_conformance.py` | `b1817bafed042437a23100ffefeff1c1c0f8109bc5db5c531efc53b15345caef` |
| `src/g4/classification.py` | `9a35f0829de8216ff47e6b1dd257e5dbc5a0dd96c9a051dd058bfe54bd672da1` |
| `src/g4/__init__.py` | `ce71102f51064425027c2999709eb9a003095bc432ba2f861a9e1cf44de32c67` |
| `src/g4/energy.py` | `ed66dc4346b1ccbd8e0e1adeae749fb6bcf195f4b4476c5545fb56371aeab1fa` |
| `src/g4/generate_ledger.py` | `a8ba50cf45ab5634c715929d7d4d887a57c45103bbc931f6930d32d86f134134` |
| `src/g4/constraints.py` | `dac9b0b10f7ee2e3e79d224fd66e16799f574ffd515289339ce419ebf5a97a96` |
| `src/g4/objective.py` | `8fbf424695586ee0a4879aaaccc97f2128baf662e358e2375b2c4ee09e913d54` |
| `src/g4/instance.py` | `645419374fd30891c2f9ff14d030ed65a032d52d8fe88fab068ad23417b58187` |
| `src/g4/parameters.py` | `cbbdebbe44b9af0d47fa1d5da7e00303e492d70d21abd696e6bdd5a4cd5be97c` |
| `src/g4/quadratic.py` | `ade40007e7c0f536d0136e9963765e0d66c958a4d2e228402d53afad99f6bb80` |
| `src/g4/slack.py` | `5ab5f677d9150bfb63c9bf5afcd79b2fe8a80202c8c2821c282522cc5a8f4d72` |
| `src/g4/unbalanced.py` | `83849bb1fc22680aaa789145e9c0a54ee4efa36624e814feec40dbce0c6b1ab6` |

The ledger binds all 61 D010/D012 primary-axis coordinates from `1e-4` to
`1e2`, their binary64 hexadecimal representations, and primary D006/D009
coefficient bit patterns for cardinality, sector, and budget. It records the
current hashes of the accepted canonical and both ADNYE inputs and fails closed
if its Decimal coordinate evaluations at 120 and 180 digits yield different
binary64 conversions.

## Canonical H_E evaluator (`src/g4/energy.py`)

`src/g4/energy.py` transcribes the frozen `FROZEN_MATH_SPEC.md` section 5.2
residual-form binary64 ledger literally: ordered accumulators at `+0.0`, no
FMA/contraction/reassociation/library dot product/pow/math.fsum/NumPy,
fail-closed on nonfinite inputs, nonpositive `Lambda_ref`, nonpositive
tolerance multiplier, or a digest-invalid ledger, all via explicit `raise`.
Coefficients come only from `parameters.load_coefficients`. Slack register
widths are the scope-locked 2 bits per sector family and 11 for budget.
The lead independently verified it at exact binary64 equality against a separate
reviewer-side transcription
(`04_encodings/g4/review_g4_energy_conformance.py`) over the full 976-state
feasible lift population and a seeded infeasible sample at all 61 primary rows,
both encodings: max difference 0.0.

## Conformance evidence

Both scripts below were run with `PYTHONDONTWRITEBYTECODE=1` under `python3`
and `python3 -O` so their checks do not rely on removable `assert` statements;
all four runs exit zero.

### `research/g4/verify_g4_conformance.py`

- The independent ledger checker derives the D010/D012 bounds from the accepted
  ADNYE inputs and compares all 61 coordinate and cardinality/sector/budget
  coefficient hexadecimal patterns to the frozen §4.3 transcript.
- V-18 compares a separately written hard-feasibility predicate with the shared
  residual predicates across all `2^20` decoded states; they agree, and the
  feasible population has 976 states.
- Feasible slack behavior (finding F5 restated): the evidence is that every
  feasible state's sector residuals lie exactly in `{0,1,2,3}` and the budget
  residual in `{0,...,2047}`, i.e. each feasible residual is exactly
  representable in its slack register at every primary coordinate, which makes
  the exact-minimizer lift's penalty identically zero bit-for-bit. A literal
  `(value - int(value))**2 == 0.0` assertion would be tautological given the
  representability check immediately above it and was removed rather than kept
  as false assurance.
- Energy-level cross-check (findings F1/F2 closed): the previous coefficient-
  level oracle (`add_oracle_square` / `add_oracle_zeta` /
  `add_oracle_objective`) was a line-for-line copy of the producer's own
  `slack._add_square` / `unbalanced._add_zeta` /
  `objective.add_qubo_terms`, so it compared the code to itself. It is replaced
  by evaluating each encoding's expanded QUBO against the canonical
  `src/g4/energy.py` residual form over real states — all 61 primary rows ×
  976 feasible states per encoding. The two agree within a derived diagnostic
  bound. The measured maximum normalized drift is exactly
  `0x1.9e1aaac6499cfp-36` (`2.3539096691422382e-11`) across every row and both
  encodings; an explicit `8x` safety factor gives
  `1.8831277353137906e-10`. This is an algebra-conformance bound, not D015
  `tau`, and the two accumulation paths are NOT asserted equal:

  - slack_feasible: max gap `2.370043397648125e-11` at row 60, up to
    `3279.9×` the D015 `tau` at `c_H = 2048`
  - unbalanced_feasible: max gap `1.686828454694e-11` at row 60, up to
    `94.5×` tau (row 47)

  Exact agreement everywhere would mean the evaluator had reimplemented the
  expansion, so nonzero drift is required by the check itself and the
  magnitude is reported against `tau` in the script output. This also gives
  the previously unwitnessed provenance figure (F2) a reproducible witness:
  the same `2.370043397648125e-11` appears in both this script and the
  reviewer probe.
- Mutation power is exercised through the actual `Qubo.energy` path at every
  one of the 61 ledger rows and both encodings. The largest active diagonal
  coefficient is perturbed by `+/-1e-6`; all 244 mutations breach the derived
  bound. The weakest case is still `15.310x` the bound: unbalanced row 13,
  positive direction, diagonal index 3, original coefficient
  `-0.0028959958919221925`, normalized signal `2.8829788844927375e-09`.
- Separated-penalty architecture: both encodings import the common
  objective/residual modules, never one another, and retain their own
  `_add_square` / `_add_zeta` assembly.
- Nonfinite/nonpositive coefficients, a zero coordinate, and a digest-invalid
  ledger fail closed before QUBO formulation.

### `research/g4/verify_g4_energy.py`

- Source scan: uses structural AST-node inspection, not normalized-source
  substrings. It rejects explicitly enumerated forms of direct/imported/aliased/attribute and relevant
  indirect `fsum`/`fma`/`pow`, built-in `pow()` and `**`, NumPy imports/access,
  QUBO assembly, and bare assertions. Dynamic prohibited-module lookup/import
  fails closed; syntax errors fail closed. Focused self-tests include the four
  filed evasions plus direct and alias cases, while comments, docstrings,
  unrelated strings, and `**kwargs` remain accepted. It provides no universal
  guarantee against adversarial evasion; the threat model is accidental
  regression in a hash-pinned file.
- Before dynamic import, the verifier requires the reviewer oracle's exact
  SHA-256 `57da8154...6831`. A digest-altered temporary copy is rejected in a
  focused fail-closed test. The oracle itself remained read-only.
- Fail-closed negatives: short/non-bit `x`, nonfinite `mu`, nonpositive
  `Lambda_ref` and tolerance multiplier, nonfinite `tau` input, a
  digest-altered ledger, and a wrong-length slack auxiliary all raise.
- Cross-agreement: exact binary64 equality between `slack_energy` /
  `unbalanced_energy` and the independent reviewer transcription over 976
  feasible lifts and 2000 seeded infeasible states at all 61 primary rows.
- Drift reporting: canonical `H_E` vs `Qubo.energy` gaps recorded against
  D015 `tau(H_E, expanded)` at `c_H = 2048`; worst feasible figures match the
  table above, and infeasible-state drift reaches `1.396983861923e-09`
  (row 60). Drift present-and-reported is itself asserted; agreement everywhere
  fails the run.

Expanded QUBO accumulation is deliberately not the canonical D015 energy
ledger: cancellation between expanded terms causes the measured drift above.
The frozen primitive residual-form ledger remains the only canonical comparison
path; the expanded matrix is a solver formulation artifact. This is a
formulation observation, not certification.

## Bounded M5 production and conformance

Starting touched-file snapshot before the reviewer's edits:

| Path | Starting SHA-256 |
|---|---|
| `research/g4/G4_PROVENANCE.md` | `0df83c57fa308695bfe094d89b9ea651b17ddd13d2392c696291fdb77c62f3e7` |
| `src/g4/__init__.py` | `cd1f3f3143acf2d051c8d54152629a5d12ff5eea1727b4e7627102b567b0c826` |
| `src/g4/classification.py` | absent |
| `research/g4/verify_m5_conformance.py` | absent |

`src/g4/classification.py` implements an immutable original-objective
comparison service and decoded classifier. Its callable label boundary has
only decoded `x` and frozen `f*` as per-call inputs; original objective and
feasibility are injected as narrowly typed original-problem capabilities.
There is no encoded energy, `T_E`, encoding identifier, auxiliary state,
multiplicity, QUBO coefficient, or search-result parameter. The atomic rule is
exactly `A = OPT_f(x)`, `B = feasible(x) and not A`, `C = not feasible(x)`;
decoded-set aggregation is `exists C`, else `all A`, else `B`. Malformed,
nonfinite, nonpositive, non-Boolean, and empty-set cases fail closed.

`research/g4/verify_m5_conformance.py` is separately written conformance
evidence. Its behavioral capability spies prove what actually crosses the
classifier boundary, and prohibited keyword injections fail. V-8 covers a
feasible optimum, feasible suboptimum, isolated cardinality/sector/budget
violations, simultaneous violations, `K-1`, `K+1`, `C`, `C+1`, `B`, and
`B+1`, plus decoded A+B/A+C/B+C aggregation. V-4 uses a six-total-variable
toy only: an independent full enumeration of all 64 raw states is compared
with a decoded closed-form slack path, including the complete tolerance-based
tie set. It loads no primary instance, primary ledger, ADNYE record, or
primary encoded state, and its toy output supports no scientific claim.

Commands and outcomes for the final candidate snapshot:

- `PYTHONDONTWRITEBYTECODE=1 python3 research/g4/verify_m5_conformance.py` — PASS.
- `PYTHONDONTWRITEBYTECODE=1 python3 -O research/g4/verify_m5_conformance.py` — PASS.
- `PYTHONDONTWRITEBYTECODE=1 python3 research/g4/verify_g4_conformance.py` — PASS.
- `PYTHONDONTWRITEBYTECODE=1 python3 -O research/g4/verify_g4_conformance.py` — PASS.
- `PYTHONDONTWRITEBYTECODE=1 python3 research/g4/verify_g4_energy.py` — PASS.
- `PYTHONDONTWRITEBYTECODE=1 python3 -O research/g4/verify_g4_energy.py` — PASS.
- `PYTHONDONTWRITEBYTECODE=1 python3 research/audit/verify_gate1_math.py` — PASS.
- `PYTHONDONTWRITEBYTECODE=1 python3 research/audit/check_retractions.py` — PASS.
- `PYTHONDONTWRITEBYTECODE=1 python3 research/audit/check_retractions.py --self-test` — PASS.
- `(cd research/canonical && sha256sum -c DIGESTS.txt)` — 6/6 OK.
- `(cd research/ground_truth && sha256sum -c DIGESTS.txt)` — 8/8 OK.
- `PYTHONDONTWRITEBYTECODE=1 python3 research/audit/validate_adnye_output.py --root research/adnye` — PASS.
- `PYTHONDONTWRITEBYTECODE=1 python3 research/audit/verify_g2_canonical.py` — PASS.
- `PYTHONDONTWRITEBYTECODE=1 python3 research/audit/verify_g2_d005.py` — PASS.

No existing G4 formulation, ledger, energy evaluator, or inherited conformance
verifier changed. The only pre-existing G4 source changed is
`src/g4/__init__.py`, whose package-boundary prose now acknowledges the
authorized decoded-only M5 module. No primary-instance ground-state
certification, primary tie-set computation, `T_E`/`X_E` production, reported
primary classification, grid sweep, experiment, result, conclusion, Gate-4
exit, or Gate-5 work occurred.

bounded M5 work produced, pending independent review.

### 2026-08-26 bounded M5 corrective delta

Under the owner-approved 14:02:05 IST corrective record, the reviewer changed only the
two authorized M5 surfaces plus this provenance and a new append-only handoff
entry. Opening hashes were `58bd2d5b...b7af` for
`src/g4/classification.py`, `b1a99e3b...1be7` for
`research/g4/verify_m5_conformance.py`, `1aa23d92...6f54` for this file,
and `612b08f6...ff9` for the handoff before its new append.

The classifier change is documentation only: it warns that
`agrees_with_frozen_optimum` is the objective-comparison component, not the
complete feasibility-aware `OPT_f`; `DecodedClassifier.label` remains the
full atomic path. The verifier now independently constructs the D015 boundary
with `Lambda_ref=2^41-1`, `f*=0`, and the three adjacent binary64 gaps
`nextafter(1,0)`, `1`, and `nextafter(1,+inf)`. All three scale additions round
to `2^41`, making frozen `tau` exactly `1` and fixing expected labels A/A/B.

Normal and `python3 -O` verifier runs pass. An in-memory scratch mutation
harness substituted each of lead N-1's exact five changes, without writing
repository bytes: `c_f 2048->1`, `epsilon 2^-52->2^-30`, scale addition to
multiplication, `<=` to `<`, and `max` to `min`. The new boundary fixture
rejected all five under both normal and optimized Python. Gate-1 math,
retraction check and self-test, canonical 6/6 manifest, ground-truth 8/8
manifest, and D014 ADNYE validation also pass. No inherited G4 verifier was
rerun because this delta changes neither inherited verifier nor formulation/
energy code, and their prior normal/optimized passes remain pinned above.

No toy V-4 logic, package initializer, builder artifact, protected input,
primary computation, tie set, reported classification, sweep, experiment,
result, conclusion, Gate-4 exit, or Gate-5 work changed or occurred.

bounded M5 corrective delta produced, pending independent review.

### 2026-08-26 bounded B-1/B-2/B-3 verifier hardening

Authority is the owner-approved record at 14:36:52 IST. Opening hashes were
`bb4a5107...f2ddd` for `verify_g4_conformance.py`,
`b8a00ce7...02b5` for `verify_g4_energy.py`, `67794d46...6609` for this
provenance, and `8c1d9a63...91d3` for the reviewer's handoff. The read-only oracle
opened and closed at `57da8154...6831`; `src/g4/energy.py` opened and closed at
`ed66dc43...ab1fa`.

B-1 replaces both producer-verifier `1e-6` round constants with the exact
measured normalized drift and explicit 8x safety margin above. The inherited
conformance script additionally runs +/-1e-6 coefficient mutations across all
rows/encodings and reports the weakest case. Residual-form `H_E` remains the
sole canonical D015 authority; expanded `Qubo.energy` remains a formulation
diagnostic with measured accumulation drift.

B-2 replaces `_code_only`/substring matching with structural AST inspection
and normal/optimized self-tests. B-3 pins the reviewer oracle in this artifact
table and hash-verifies it before `spec_from_file_location` or module
execution; altered bytes fail closed.

Completed final-snapshot commands:

- `PYTHONDONTWRITEBYTECODE=1 python3 research/g4/verify_g4_conformance.py` — PASS; derived bound and all-row mutation evidence reported.
- `PYTHONDONTWRITEBYTECODE=1 python3 -O research/g4/verify_g4_conformance.py` — PASS; identical figures.
- `PYTHONDONTWRITEBYTECODE=1 python3 research/g4/verify_g4_energy.py` — PASS to completion.
- `PYTHONDONTWRITEBYTECODE=1 python3 -O research/g4/verify_g4_energy.py` — PASS to completion.
- `PYTHONDONTWRITEBYTECODE=1 python3 research/g4/verify_m5_conformance.py` — PASS.
- `PYTHONDONTWRITEBYTECODE=1 python3 -O research/g4/verify_m5_conformance.py` — PASS.
- Focused B-2/B-3 normal and optimized imports/self-tests — PASS.
- Gate-1 math, retraction check and self-test, canonical 6/6, ground-truth
  8/8, D014 ADNYE validation, G2 canonical/D005, and G2 delta audit — PASS.

No formulation, ledger, production evaluator, classifier, toy V-4 logic,
protected input, frozen authority, reviewer oracle, primary computation, tie
set, classification result, sweep, experiment, conclusion, Gate-4 exit, or
Gate-5 work changed or occurred. No persistent cache was created.

bounded B-1/B-2/B-3 repair produced, pending independent review.

## Review ownership

The reviewer produced the original bounded G4 package; a builder produced
`src/g4/energy.py` under the corrected ownership records; a builder executed
the earlier bounded repair (scanner fix, dangling-import removal, F1/F2
energy-level cross-check, and F5 restatement). The reviewer Medium produced the bounded
M5 files and the later owner-authorized B-1/B-2/B-3 verifier hardening. The lead
is the independent reviewer and must review this delta and the final combined
snapshot before any acceptance claim. No self-acceptance or G4 exit claim is
permitted, and Gate 5 remains unauthorized and unstarted.

### 2026-08-26 Gate-4 Final Corrective Pass — Item 6 Reversion (The second reviewer)

Item 6 (coefficient cross-check) was initially attempted during the bounded corrective pass. It was subsequently reverted and declined because §4.3 defines the coefficients as a step-wise `fl()` sequence with rounding at every operation, whereas the high-precision `Decimal` reference value composed the entire mathematical expression before rounding once at the end. A step-wise `fl()` sequence cannot be tested identically against a single composed high-precision reference value, so a `Decimal` cross-check of the composed expression is not a valid test of §4.3 conformance. The generation ledger was reverted to its exact previous state `a8ba50cf45ab5634c715929d7d4d887a57c45103bbc931f6930d32d86f134134`.
