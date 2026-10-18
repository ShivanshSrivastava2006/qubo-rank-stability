# Gate-5 Clause-(b) Python Pipeline Provenance

**Status:** independently accepted as infrastructure; pending owner authorization of the single named point.  
**Producer:** the reviewer.  
**Final producer snapshot:** 2026-08-26 23:38:56 IST.  
**Authority:** approved Gate-5 clauses (c)/(b), subject to the single-named-point and
independent-review ordering requirements. This document records no Gate-5 acceptance or exit.

## Preserved accepted and ratified predecessors

Before the corrective pass modified any accepted or ratified surface, exact historical bytes were
promoted to inert evidence under the approved Gate-5 preservation rule:

| Artifact | SHA-256 |
|---|---|
| `research/g5/domains_ratified_clause_a.py.txt` | `3ec856d3b3061605aa6d583bb7a94a9d27c699aa08b88c64ff12e622a714d7cc` |
| `research/g5/certify_ratified_clause_a.py.txt` | `3a1a72206613c0419639fe18b7db1c521d4171454fad028a9dbc3a5d4b80d7c7` |
| `research/g5/certify_accepted_clause_c.py.txt` | `626a06237f81d5f358020776e37389720fc9b43cb20436fa1c3d6afad07ef9f6` |

Each inert artifact was independently compared byte-for-byte with its transcript-recovered candidate.

## Corrective delta

| Artifact | Opening SHA-256 | Final SHA-256 | Role |
|---|---|---|---|
| `src/g5/domains.py` | `0b8ad3dddd7a726420ab397d838fded27b1a4629656b229221bde4400e0b3476` | `89d3b1cadf660ec7ea4a127af09a73073afb03d5c78a74e7a15b5808999dadf7` | exact partition binding, portable logical digest, factory-only alignment, shared preparation |
| `src/g5/certify.py` | `018b0a67ae1d1fdf8cf797cd38296ed0a98ec3bd0d2e5c1124dc51e36e614d64` | `018b0a67ae1d1fdf8cf797cd38296ed0a98ec3bd0d2e5c1124dc51e36e614d64` | unchanged pending clause-(b) positional certifier |
| `src/g5/runner.py` | N/A | `262fda09db033cc3195c8447042836274b195907b772f827f3f21a9311f963cd` | preparation-outside-grid and fixture-gated runner services |
| `research/g5/verify_domain_cache.py` | `7abeae1c7f449f44ccc00942b5d4db15e3dba61b207c25bf0d399ff5e46386f9` | `a339386d671b9cc57f1c4958b3420c062db553ba3e95d9c97cd051a7723c8cd2` | exhaustive cache, digest, partition, alignment and sharing checks |
| `research/g5/verify_runner.py` | N/A | `42a18e993ef9851cdf0bbd351e27820ba4c90ec98787a654c94445c86b11e8c6` | isolated runner equivalence and fail-closed checks |

The correction stores sector count, sector-register width and budget-register width separately. Equal
total auxiliary width is insufficient: preparation for the accepted energy evaluator requires exactly
four 2-bit sector registers followed by one 11-bit budget register. Native in-memory array bytes remain a
same-process implementation detail; provenance hashes the logical integer sequence using explicit
little-endian `<Q` offsets and `<I` masks.

`PreparedDomainCache` is constructible only through preparation services. Its authorization token is not
a dataclass field, so direct construction and `dataclasses.replace()` cannot carry alignment authority to
reordered states. `prepare_active_domains` creates decoded intermediates once and shares the identical
objects with both encodings. `src/g5/runner.py` validates coefficients exactly once per point, evaluates
only prepared canonical residual-form energies, and reconstructs raw states only through the certifier for
members of `T_E`. Its acceptance entry point requires an injected 16-state fixture and cannot fall back to
the primary instance or grid.

The primary cache builder deliberately calls the private, byte-pinned canonical
`src.g4.energy._residuals_from_bits` rather than introducing another primary residual transcription. This
private-symbol dependency must be promoted to a reviewed public wrapper before Gate 6 modifies or extends
the energy surface. `_toy_residuals` is a separate toy-only transcription required because the canonical
20-variable instance validator correctly rejects isolated small fixtures; it is not a primary or
scientific-computation path.

## Independent precommitted instruments

| Instrument | SHA-256 | Final outcome |
|---|---|---|
| `05_certification/g5/review_g5_domain_cache_corrective.py` | `6ae25ac3945b7c92b4e706ee38e8840f6e9595473e705ac2a170321492eff0dd` | all six checks PASS, normal and `-O` |
| `05_certification/g5/review_g5_amortisation_v2.py` | `ff4154d39e52284877a88e46825948ce55da469e64d33680789feb539bf5d034` | target runner contract PASS, normal and `-O` |

The final independent cache runs pinned the production hashes shown above. Earlier producer-side attempts
that were interrupted or crossed an in-flight source edit are excluded from evidence; the final four
full-domain runs were restarted against the single 23:28:38 IST snapshot.

## Final verification outcomes

- `research/g5/verify_domain_cache.py`, normal and `python3 -O`: PASS. Both found exactly `2^20`
  primary slack lifts; packed size 12,582,920 bytes; portable logical digest
  `d052e67892d0e39882db26798f881628480d83c0119ee3a1e2ba9b1cdcf03063`; parallel build times
  22.929 s and 24.004 s.
- `research/g5/verify_runner.py`, normal and `python3 -O`: PASS on isolated 16-state fixtures.
- The second reviewer amortisation target mode, normal and `python3 -O`: PASS with one instance validation, one
  `BinaryDomain`, 16 decoded preparations, 16 slack preparations, two prepared caches, exactly `P`
  coefficient validations, exactly `D*P`/`L*P` evaluations, zero legacy evaluations, and raw-state
  reconstruction equal to the observed tie counts.
- `research/g5/test_machinery.py`, `verify_worker.py`, and `verify_python_repair.py`, normal and
  `python3 -O`: PASS. The repair verifier retained 505,920 independent bit-exact comparisons per mode.
- No bare `assert` occurs in the production or new producer-verifier files. No Python bytecode artifact
  remained at the final snapshot.

## Full preparation measurement

A single primary preprocessing-only run constructed the packed cache and both shared prepared domains.
It performed no minimum search, tie construction, classification, or grid-point certification.

| Quantity | Measured value |
|---|---:|
| Packed cache build | 35.782372 s |
| Shared preparation | 475.905368 s |
| Total wall time | 511.687740 s |
| Peak RSS | 1,116,076 KiB (about 1.064 GiB) |
| Swaps | 0 |
| Unbalanced states | 1,048,576 |
| Slack states | 1,048,576 |

Sampled slack states referenced the identical decoded objects held by the unbalanced cache. On the
32-GiB host, 8--12 workers remains a conservative provisional envelope, not a zero-risk guarantee; the
named-point end-to-end review must still measure evaluation and result-processing behavior.

## Scope statement

No primary minimum, primary `T_E`/`X_E`, primary A/B/C classification, named grid point, grid sweep,
scientific result, inference, Rust value, Gate-6 work, conclusion, Gate-5 acceptance, or Gate-5 exit was
produced. The owner-designated fresh production-isolated the second reviewer reviewer subsequently accepted the
corrected clause-(b) pipeline as infrastructure, with report SHA-256
`fa53abd72011493fbd0a014ea84381ba1a2b6730ec534357a42aa048958e63c8`. The lead's late review independently
reached the same infrastructure verdict and is supporting evidence after the ownership amendment.

Two statements in the controlling report are read with explicit corrections: at an exact half-integer the
§5.1 minimizer set retains both equally penalized adjacent integers; it is not a deterministic single
`round()` result. Also, `2^20` is the primary decoded-domain cardinality and hence the active primary
`C_slack` cardinality here, not a general claim that a grid point's decoded tie set `X_E` has size `2^20`.
The implementation and executable fixtures already follow the correct meanings.

Carried conditions are: half-integer/clipping adversarial fixtures must close before the full core pass;
the `+0.0` path remains inspection-only and must close before Gate 6; and the private canonical residual
dependency must become a reviewed public wrapper before Gate 6 touches `energy.py`. None blocks owner
consideration of the single named Python point. Infrastructure acceptance itself authorizes no named point,
Rust-produced primary value, full pass, Gate-6 work, result, conclusion, or Gate-5 exit.
