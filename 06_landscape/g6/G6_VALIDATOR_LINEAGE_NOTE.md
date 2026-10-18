# Gate-6 Validator Lineage Note

Status: **PRE-PRODUCTION TRACEABILITY NOTE — NO SCIENTIFIC OUTPUT**

Date: 2026-09-19 (Asia/Kolkata)

## Purpose

The owner-ratified Gate-5 identity registry is immutable. Its producer hashes
identify the code used when that registry was emitted; they are not a claim
that every later, additive Gate-6 validator retains those exact bytes.

## Historical registry producers

The owner-ratified registry and
`research/decisions/GATE_5_IDENTITY_REGISTRY_RATIFICATION.md` pin these
historical producer identities:

| File | SHA-256 |
| --- | --- |
| `src/g6/g5_digest_registry.py` | `48ee606a8937cf047cc12ca5e46391142d6e47a214acf734b35d36b7f818f989` |
| `research/g6/make_g5_digest_registry.py` | `fbc8a2cd1de8ce13c900d2ae9713166e85344101d269f12e93a3b0834a913c5b` |

The registry itself remains the sole ratified identity lock:

- file SHA-256: `64d0c92b53bd7f4340e3b3837ddaaacb1009a7427dd11d6e38714582b93b66be`
- canonical `content_sha256`: `ab0c84400ae92fdf5da7c75511ce559679ebdadd003a9007a959585b40e74955`

## Current additive validation boundary

After registry generation, `g5_digest_registry.py` was extended so
`verify_pending_registry_against_corpus` returns the summary it has already
fully validated. This lets the later ratified boundary avoid treating a
separate structural reread as its record-access path. It does not alter the
registry, its generation protocol, or any Gate-5 byte.

At publication of this note, the live validation files are:

| File | SHA-256 |
| --- | --- |
| `src/g6/g5_digest_registry.py` | `ed80f784a1c13da0dae27393efa0c1f95c3811f35551748f60833fbf38e65e60` |
| `src/g6/g5_input.py` | `4584aa39f893dc4aaf79444818d7c7b60c6a707426bb6ae36dbaaff41868cb50` |
| `src/g6/ratified_g5_input.py` | `5ab9974a48cefc270658cf895c6caff01fccc81a427e4a0595737f8e0d1d525b` |
| `research/g6/verify_ratified_g5_input.py` | `e64bd1368fe9e3b2f5666f84cfe39bad8870eee33f1612bde69feff84b326721` |
| `research/g6/verify_ratified_g5_iterator.py` | `4eae9f16251fefe795d91ab0710127478bb302af94b6b5c73f8094eaf1e0c579` |
| `research/g6/verify_g6_input_import_boundary.py` | `9afcf4d6b4f831111b4ff728747933e3d41c2b1bddfe9d8d2dd53dca9570be15` |

Every bounded-trial and production-pass manifest must capture the actual
SHA-256 values of the live input-boundary sources it invokes. A changed source
requires a new reviewed manifest; it never changes the ratified registry.
