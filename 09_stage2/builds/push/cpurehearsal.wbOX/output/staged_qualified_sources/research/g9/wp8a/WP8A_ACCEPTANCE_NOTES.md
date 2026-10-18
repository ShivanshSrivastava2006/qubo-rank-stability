# WP8a — Production identity acceptance record and PRODUCTION validator

**Package:** WP8a. **Owner default:** 1 of the WP8 design, approved 2026-10-01
~14:20 IST (`research/decisions/GATE_9_WP7_PINNED_DRAFT_AND_WP7B_OWNER_DECISION.md`
lines 146-154: "issued by a newly versioned, independently reviewed acceptance
record plus a production validator, bound into a newly qualified source map. The
bundle requires their exact hashes. The draft is never reinterpreted as
accepted."). **Answers:** OWNER QUESTION 1 of
`research/g9/kaggle_wp8/WP8_PRODUCTION_BUNDLE_DESIGN.md:122-128`.

**Status: built and validated offline. This package issues no production
identity and grants no authority.** Offline code cannot verify an owner's
identity cryptographically, so nothing here claims to; see *Fail-closed scope*.

**Round 2.** The independent validator failed round 1 on four blocking findings.
All four are closed and each has its own named regression test; the fixes are
listed at the end of this file.

## Files

| file | lines | sha256 |
|---|---|---|
| `research/g9/wp8a/wp8a_production_identity_acceptance.py` | 1237 | `19a5d57781738c6c730dcdd63cabdb8e6a011ffa2aa5fc032c33d9e8c2ae4113` |
| `research/g9/wp8a/verify_wp8a_production_identity_acceptance_fixtures.py` | 2445 | `a7cc7edc4280f6588775b53aae92467944260446205570b2983ac08d4244a538` |
| `research/g9/wp8a/WP8A_ACCEPTANCE_NOTES.md` | this file | hash it directly; a file cannot record its own hash |

Mutation gate: `g9_guard_sweep.py` v1.1 over the acceptance module, 6 workers,
`--chunk-seconds 36000` — **271 sites, 260 KILLED, 0 survived, 0 errors, 0 stale,
11 EQUIVALENT-ACCEPTED. `SWEEP: PASS`.** Native output:
`g9_jobs/logs/wp8a.sweep.acceptance.txt`. The 11 equivalents are listed with their
file:line dominators in `g9_jobs/scratch/wp8a/r2b/equiv.json`; every one is a rule
*repeated in full* by a neighbouring line that is itself killed. Where a rule had
no driven input at all, the rule was made observable instead of accepted.

Both Python files are new. Nothing pinned was modified: no file under
`research/g9/kaggle_wp7/`, `research/g9/kaggle_wp7b/`, `src/`, the 29 reviewed
dependencies, or the 12 v1 files was touched. `stage2_production_identity.py` and
`wp7_session.py` are imported and called **exactly as published**; neither is
forked, patched or relaxed.

## The problem this solves

The WP1 production-identity validator is deliberately narrow. It requires
`status == DRAFT_UNQUALIFIED`, `authorization == NONE` and the pinned draft
authorization note, and refuses everything else
(`research/g9/stage2_production_identity.py:396-402`). The WP7b runtime config
carries that draft. So there was no way to say "this identity is accepted"
without either reinterpreting the draft — which the owner decision forbids — or
inventing an acceptance format out of nothing.

This package supplies the second thing, additively: a **newly versioned
acceptance record** (`.../g9_wp8a_production_identity_acceptance/v2`) and a
**PRODUCTION validator** that accept a genuine, still-draft WP1 identity by
*binding its exact hash* and re-validating it with the unmodified WP1 validator on
every read. A payload that claims to be qualified is refused twice: by WP1, and
again by `bound.draft_identity_status`.

## The authority: an externally supplied pin, never a signature

Offline code cannot verify an owner's identity cryptographically, so this package
makes **no** cryptographic claim and holds **no** `signature`, `signed_by` or
`owner-signed` field, schema string or helper. A fixture asserts that no such
name survives anywhere in the record, in the module's namespace, or in its
source text.

The authority is instead the repository's own D013-release pattern
(`research/g9/cuda_qualification/stage2_cuda_d013_inactive_corruption_qualification.py:411-444`,
re-checked at `:455-491`): the acceptance record is **canonical bytes** —
`contract.canonical_bytes(record) + b"\n"`, exactly the form the D013 release
draft is held to at `:427` — and the gate accepts it **only if**

1. `record["status"] == "approved"`, and
2. the sha256 of exactly those bytes equals `reviewed_record_sha256`, a value
   the **caller passes in explicitly** because the lead pinned it after the owner
   approved.

Point 2 supplies the authority: the pin is not derived from the record, so a
caller cannot present a forged record together with a pin of its own making and
be believed. It arrives from outside, exactly as `reviewed_release_sha256`
arrives at `stage2_cuda_d013_inactive_corruption_qualification.py:494`.

**Every path in the record is a file, not an assertion.** The WP7 receipt, the
review note and every qualified-source-map entry must resolve to a regular,
non-symlink file **inside the repo root** and must hash to the value recorded.
Missing, extra or mismatched is a typed refusal. Round 1 named files that did not
exist and never opened a bound file.

## Interface for the other WP8 packages

```python
from research.g9.wp8a import wp8a_production_identity_acceptance as acc
```

### Step 1 — build the record (a draft until the review binds its note)

```python
record = acc.build_acceptance_record(draft_identity, repo_root="/path/to/repo")
```

`draft_identity` must be a genuine WP1 DRAFT identity; anything WP1 refuses is
refused here with the same refusal. `repo_root` is used to **read** the WP7
dry-run receipt and to hash every file the qualified source map names, so the
record returned names only files that exist and only hashes that were observed.

The result already carries `status == "approved"`, but its `approval` block has
`review_note_rel`, `review_note_sha256` and `reviewed_at_utc` all `null`, so it
is **refused** by the gate. Building is not approval.

### Step 2 — the independent review binds a review note that exists

```python
record = acc.bind_review_note(record, review_note_rel, reviewed_at_utc,
                              reviewed_by=..., repo_root="/path/to/repo")
```

The note is read out of the repo root and hashed **here**; a note that does not
exist, is a symlink, escapes the root or is not a `.json` document is a typed
refusal. A record that already binds a note refuses a rebind. This supplies a
file the validator can find and re-hash, so a record cannot claim a review that
left no artifact. **It is still not approval** — the authority is the pin.

### Step 3 — the PRODUCTION gate

```python
accepted = acc.accept_production_identity(record, reviewed_record_sha256=PIN,
                                          repo_root="/path/to/repo")
```

`PIN` is the value the lead pinned. Returns the exact hashes, the qualified
source map and the embedded draft identity to hand to WP1's `exact_match()`.

The structural validator is public too:

```python
receipt = acc.validate_acceptance_record(record, reviewed_record_sha256=PIN,
                                         repo_root="/path/to/repo")
```

### Step 4 — session-side comparison

```python
verdict = acc.exact_match_session(session_identity, record, reviewed_record_sha256=PIN,
                                  repo_root="/path/to/repo")
```

Delegates to `stage2_production_identity.exact_match()` — the total, symmetric,
name-every-difference comparison (`stage2_production_identity.py:436-475`) — and
re-raises its refusals as `AcceptanceSessionMismatch` (carrying
`differing_fields`) or `AcceptanceRecordError`. The comparison is **not**
re-implemented, so this package cannot be laxer than WP1 about what a difference
is. Note that WP1 validates **both** operands first (`:444-445`), so a session
identity that is not itself a well-formed WP1 identity is refused as a record
error, not as a mismatch.

## Record shape

Nine top-level keys, exactly (`RECORD_KEYS`):

```
schema, status, scope_statement, approval, bound, draft_identity,
wp7_dry_run_evidence, qualified_source_map, content_sha256
```

Nothing may be added or removed. This includes `content_sha256`: deleting it
changes the record's canonical bytes, so a caller pinning the reduced record
reaches the gate with a pin that **matches**, and both the pin check and the
internal consistency check would pass. The exact key-set check is what refuses
it, and it runs first. `test_deleting_the_content_sha256_slot_is_refused` pins
this for every member of `RECORD_KEYS`, under both the original pin and a pin of
the record's own reduced bytes.

### `bound` — re-derived, not trusted

| slot | re-derived from |
|---|---|
| `draft_identity_schema` | pinned to `wp1.PRODUCTION_IDENTITY_SCHEMA` |
| `draft_identity_status` | pinned to `wp1.DRAFT_STATUS` (`DRAFT_UNQUALIFIED`) |
| `draft_identity_content_sha256` | `wp1.validate_production_identity()` |
| `qualification_identity_content_sha256` | the frozen contract's inner hash (`stage2_cuda_execution_contract.py:96-102`) |
| `source_map_content_sha256` | the frozen canonicalizer over the embedded WP1 source map (`stage2_cuda_execution_contract.py:40-47`) |
| `bound_file_count` | the embedded source map, already re-counted by WP1 (`stage2_production_identity.py:386`) |
| `qualified_source_map_content_sha256` | the frozen canonicalizer over the embedded WP8a qualified map |
| `qualified_source_map_file_count` | the embedded WP8a qualified map |

### Two hashes, two jobs

`record["content_sha256"]` is the frozen contract's own hash of the record body
excluding its own slot (`stage2_cuda_execution_contract.py:44-47`) — the record's
internal consistency check. `record_content_sha256(record)` is the sha256 of the
record's **full** canonical bytes including that slot, and is the number the lead
pins and the bundle embeds. Neither can be re-pointed: the first is re-derived
from the body, the second from the whole record.

### `wp7_dry_run_evidence` — a real WP7 receipt

Eleven keys, exactly: `evidence_state`, `receipt_rel`, `receipt_sha256`, `mode`,
`steps_executed`, `package_status`, `push_authorized`,
`gpu_allocation_authorized`, `scientific_output_count`, `content_sha256`,
`statement`.

The bound file is a **real `wp7_session` receipt**, not a shape invented by this
package. Its schema and mode are `wp7_session`'s own
(`research/g9/kaggle_wp7/wp7_session.py:83-84`), its thirteen required fields are
`wp7_session.RECEIPT_REQUIRED_FIELDS` (`:204-219`), and every receipt is put
through `wp7_session.validate_receipt()` (`:982-1022`) before anything is bound.
It must be canonical bytes plus one newline, must report
`push_authorized is False`, `gpu_allocation_authorized is False`,
`scientific_output_count == 0`, and must name the step that produced the identity
(`wp1_production_identity_candidate`) and the receipt step
(`emit_non_scientific_receipt`).

**Every field of the evidence block is COPIED from the receipt's bytes.** This
package types none of `mode`, `package_status`, the two authorization flags, the
scientific-output count, the executed steps or the receipt's own content hash. So
the record cannot describe a dry run the receipt does not describe: `_validate_evidence`
re-reads the receipt, re-derives the whole block and names every differing field.

### `qualified_source_map` — the WP8a package is itself qualified

Nine WP1 roles, plus one added role `wp8a_acceptance`. Its shape
(`QUALIFIED_SOURCE_MAP_SCHEMA`) mirrors WP1's: `schema`, `hash_algorithm`,
`roles`, `bound_file_count`, `not_yet_built_roles`, with the same
single-use-path, sorted-order, count and role-set rules, re-derived on every read
(`_validate_qualified_source_map_shape`). The WP7 session module is added to the
`v1_engine` role, because it is part of the reviewed WP7 package the evidence
comes from.

The validator then **re-hashes every file the map names against disk**
(`_validate_qualified_source_map_against_disk`), and finally checks
**containment**: every path in `wp8a_qualified_files()` must be bound by *some*
role, not merely by the WP8a one. Without that, a WP1 role could be edited to
stop binding one of this package's files and nothing else would notice, because
re-hashing a narrower map would happily succeed.

`wp8a_qualified_files()` — this module, its fixtures, its notes, `wp7_session.py`,
`stage2_production_identity.py`, the §A v1 release file WP1 reads and pins, and
`stage2_cuda_execution_contract.py`. A source-map path is bound by exactly one
role, so `wp8a_acceptance` binds the subset the WP1 roles do not already cover;
the rest remain qualified through their WP1 entry, whose hash is still
re-verified against disk on every validation.

The qualified-path suffix rule is WP1's own `.py`/`.cu`
(`stage2_production_identity.py:244`) plus WP1's own release-document `.json`
(`:222`) plus `.md` for this package's notes file. `.json` is needed because the
§A v1 release file is a document WP1 reads, not a source file it compiles.

## Typed refusals

All derive from `AcceptanceRecordError(ValueError)`:

- `AcceptanceStatusError` — the record is not in the one state the caller asked for.
- `AcceptanceEvidenceError` — the WP7 receipt is missing, malformed, or the evidence does not re-derive from it.
- `AcceptanceBindingError` — a bound hash does not re-derive from the embedded payload.
- `AcceptanceReviewError` — no review note is bound, or the note does not exist or does not hash to what is recorded.
- `AcceptanceSessionMismatch` — a session identity differs; carries `differing_fields` and `message`.

**Every malformed input is a typed refusal.** `_object()` is applied to every
untrusted node before any field of it is read, so a wrong type, a missing key or
nested garbage raises `AcceptanceRecordError` and never `KeyError` or
`TypeError`. Round 1 read `record["bound"]` directly and leaked `KeyError` out of
the production gate.

## Fail-closed scope

- **The draft is never reinterpreted.** The embedded payload is re-validated by
  the *unmodified* WP1 validator on every single read, and
  `bound.draft_identity_status` is independently pinned to `DRAFT_UNQUALIFIED`.
- **Accepting an identity is not a draw, a push, a GPU allocation or a scientific
  write.** `SCOPE_STATEMENT` says so inside the record and is pinned to exact
  wording, so a self-flattering variant is refused.
- The module imports only `__future__`, `copy`, `hashlib`, `json`, `pathlib`,
  `typing` and `research` — no `os`, `socket`, `subprocess`, `time` or clock. It
  touches no network, no Kaggle account, no GPU and no Stage-2 instance or
  value, and it writes nothing. This is asserted on the parsed AST, not on text.
- No timestamp is compared to "now" anywhere. The review timestamp is *recorded*,
  not *spent*: a validator that read a clock would give different answers on
  different days for the same pinned bytes, and the pinned-hash check would stop
  being a check.

## How the other WP8 packages should use this

- **WP8 bundle builder** — require the acceptance record's
  `accepted_content_sha256` as a pinned field alongside the bundle's other exact
  hashes, and call `accept_production_identity()` before any one-use approval is
  embedded. This module's and the record's file hashes are already inside the
  record's own `qualified_source_map`, whose
  `qualified_source_map_content_sha256` and `qualified_source_map_file_count` are
  the values to bind.
- **WP8 session/adapter** — call `exact_match_session()` against the session's own
  identity before the scientific-write permission, and treat any refusal as
  fail-closed. Do not re-implement the comparison.
- **Nobody** should treat the record's `status == "approved"` as approval on its
  own. Without the lead's pin, the gate refuses it.

## OWNER QUESTION

**Should the pin be passed on the command line or read from a pinned file, and
where should the pinned value live?**

This package takes `reviewed_record_sha256` as a required keyword argument and
never reads it from the record, the environment or a file inside the repo. The
caller's choice of transport is therefore the caller's, and the lead's pin
arrives the way `reviewed_release_sha256` arrives at
`stage2_cuda_d013_inactive_corruption_qualification.py:494`.

*Recommendation (safe default in force unless the owner says otherwise):* the WP8
bundle's own reviewed configuration file should carry the pin as a field, exactly
as the design's proposed authorization envelope does for `bundle_sha256`,
`accepted_identity_sha256` and the rest
(`WP8_PRODUCTION_BUNDLE_DESIGN.md:91-99`), and the bundle should pass that field
to `accept_production_identity()`. That keeps one reviewed artifact to hash,
rather than two (a file plus an out-of-band flag), and the bundle's rehash of its
own bytes still happens before scientific-run permission.

*The alternative,* if the owner wants the pin to be reachable without any WP8
code at all: a tiny standalone pin-checker that prints
`acc.record_content_sha256(record)` for a candidate record file, so a reviewer can
compute the value to pin, run it offline, and hand the resulting string to the
lead. That is safe — it computes the pin from bytes and prints it, it accepts
nothing — but it must never be wired into the gate itself, because then the pin
would again be caller-computable and the authority would evaporate.

*Also for the owner:* `REVIEW_NOTE_REL` defaults to
`research/decisions/WP8A_ACCEPTANCE_REVIEW_NOTE.json`. If the owner wants the
review notes of successive accepted identities kept side by side rather than
overwritten at one path, that needs a per-identity note filename convention
decided **before** the first real acceptance, since the record binds the path and
its hash and the lead pins the whole record.

## Fixtures

```
PYTHONDONTWRITEBYTECODE=1 G9_WP8A_SCRATCH=/path/outside/the/repo \
  python3 -B research/g9/wp8a/verify_wp8a_production_identity_acceptance_fixtures.py
```

45 groups, offline, synthetic, passing identically under `-B` and `-B -O` (there
is deliberately no `assert` in the file; every check raises). Every synthetic
platform value is conspicuously non-production. The WP7 receipt and the review
note live only inside the temporary tree; the receipt's step digests are filler
matching nothing, it reports a platform label that says it is not a real device,
and its own `differences` list says no real dry run produced it. The one
non-synthetic input is the 12 real §A files plus the accepted §A release
document, read-only and hashed.

The fixture re-derives `_is_sha256`, `_is_utc_stamp`, `_is_safe_rel` and
`_is_safe_source_rel` independently and asserts the two implementations agree on
every probe — compared raise-or-return, not value-to-value — so a mirror that
drifted could not make the negative cases test the wrong thing.

`G9_WP8A_ONLY` selects which groups run (comma-separated names, unset by default
means all of them). It is bookkeeping for the mutation gate and nothing else: each
named group still runs alone, on its own tree, with its own exit status, and
`TESTS` is unchanged.

### Coverage rules this fixture follows

These are the rules that make a passing fixture mean something. Every one of them
was learned the hard way in round 2, from a guard that no input could kill.

- **Pin the bytes you edited, not the bytes you started from.** If a case edits a
  record and then pins the ORIGINAL record, the pin guard refuses first and the
  case proves nothing about the guard it names. Each case now pins what it built —
  and the deletion regression pins the reduced record too, which is the whole
  point of that test.
- **Recompute the bookkeeping that would otherwise shadow the guard.** Where a
  cheaper guard (a file count, a bound hash) would fire first, the fixture
  re-derives it so the intended guard is reached.
- **Make a single guard report every defect it found, and name it.** A guard whose
  refusal text is identical to its neighbour's cannot be attributed, so it cannot
  be pinned either. The record shell, the approval block, the evidence block and
  the qualified role each collect their findings into one report that names which
  one was wrong.
- **Assert refusal by whatever actually fires, and say so in the message** — never
  demand a specific message a test cannot guarantee. Where a case can only be
  reached through a different guard, the message says which.
- **A no-op edit is not a refusal.** Where a fuzz value happens to equal the field's
  own value, the record is byte-identical, so the fixture asserts it still
  *validates* instead. Requiring a refusal there would assert that a valid record
  is invalid.
- **Give a predicate a driven input, or the mutations to it are invisible.** Every
  timestamp the fixture used was one real value, so a mutation of the digit check
  could not fail. Impossible-but-well-formed stamps (hour 60, minute 60, second 60)
  are now driven on both paths that reach the predicate.
- **The pin comparison is probed with all 960 single-character substitutions**, so
  no mutation to that comparison can survive.
- **A guard that no input can reach must be deleted, not accepted.** Six were
  deleted in round 2 (see below); none was listed as an equivalent.

## What round 2 fixed

Each item is a round-1 blocking finding with a named regression test.

1. **The forged owner-labelled record got through.** A fabricated record naming
   files that did not exist was accepted. Now every named path must exist, be a
   regular non-symlink file inside the repo root and hash to what the record
   says; the forged record is rebuilt in
   `test_forged_owner_labelled_record_is_refused` and refused.
2. **Nonexistent evidence and authority files.** `test_nonexistent_evidence_file_is_refused`,
   `test_nonexistent_authority_file_is_refused`.
3. **No bound file was ever opened.** Every qualified-source-map file is re-hashed
   against disk: `test_every_bound_source_file_is_rehashed_against_disk` flips a
   byte in each of the 27+ bound files in turn;
   `test_deleting_a_bound_source_file_is_refused`.
4. **The WP8a module was outside any source map.** The record now carries its own
   newly qualified source map with an added `wp8a_acceptance` role and a
   containment guard: `test_wp8a_module_is_inside_the_qualified_source_map`,
   `test_every_package_file_must_be_bound_by_some_role`.
5. **Malformed bound data raised `KeyError`.** `_object()`/`_field()` total
   access everywhere:
   `test_malformed_bound_block_is_a_typed_refusal_not_a_KeyError` plus four
   fuzz groups covering every top-level slot, every nested field, the qualified
   map, the embedded draft, the whole record, the pin, the repo root and the
   session identity.
6. **The pseudo-signature.** Removed in round 2 and asserted absent by
   `test_no_signature_field_or_claim_exists`.
7. **Found by this package's own probing, not by the validator:** deleting
   `content_sha256` from a record and pinning the reduced record passed every
   guard, because both the pin and the internal consistency hash are computed over
   the same reduced bytes. Fixed by the exact key-set check running first, and
   pinned by `test_deleting_the_content_sha256_slot_is_refused`.
8. **An invented WP7 receipt format.** Round 2 defined
   `g9_wp7_dry_run_receipt/v1`, a five-key document of its own with a
   `kernel_id` and a `bundle_sha256` that exist nowhere in this repository, and
   bound that as "the WP7 dry-run receipt". No such format exists. The bound file
   is now a real `wp7_session` receipt, gated by `wp7_session.validate_receipt()`,
   with every evidence field copied from it:
   `test_the_wp7_receipt_is_read_from_disk_not_asserted`.
9. **A §A v1 release file read but not qualified.** WP1 reads and pins
   `GATE_9_CUDA_CORE_CORRUPTION_QUALIFICATION_RELEASE.json`
   (`stage2_production_identity.py:205-225`); it is now in the qualified file set,
   which is why the qualified suffix rule widened to WP1's own `.json`.

### Guards removed as dead, rather than papered over

A check that cannot fire is not a check, and none of these was listed as an
accepted equivalent. Each was verified unkillable by a full sweep first, and each
is recorded here so a reviewer does not have to rediscover it.

- `_is_safe_rel()` tested `or not value`; the per-component loop already refuses
  `""`, since `"".split("/")` is `[""]`.
- `_field()` tested `key in mapping`, but every call site runs immediately after
  an exact key-set check on the same mapping. The invariant is now stated in its
  docstring and held by the fuzz groups, which would raise `KeyError` if the
  key-set guard were ever weakened.
- `_validated_draft()` tested `type(draft_identity) is dict`, but the untouched WP1
  validator requires `isinstance(payload, dict)` at
  `stage2_production_identity.py:394` and is called next. The fixture asserts that
  dominance directly instead: every non-mapping payload's refusal IS WP1's.
- `accept_production_identity()` re-read `receipt["status"]` and
  `receipt["schema"]` after `validate_acceptance_record()` had already proved
  both from the same constants — a constant compared with itself.
- `_repo_file_sha256()` re-checked containment with `is_relative_to` after
  `rel_check` had already refused every absolute path, backslash, colon and
  traversal component, and guarded a `read_bytes()` that returns `bytes` by
  definition.
- `_qualified_source_map_from()` checked for a duplicate path the WP1 shape
  validator had already refused (`stage2_production_identity.py:382`) over a
  constant it alone supplies.
- The qualified map's "is not a list / is empty" and "not in sorted path order"
  checks were merged into one per-role report, because a case that corrupts a role
  necessarily produces both findings and could not attribute them.
- A separate second pass re-hashing every qualified entry was removed once the
  entry hashes are verified against disk *inside* the shape pass.

### Two guards made stronger rather than accepted

- The WP7 gate's `validate_receipt()` result is no longer a discarded call: it is
  bound, compared, and everything downstream reads the gate's own verdict rather
  than the bytes. The case that proves it is a receipt file carrying one extra
  leading space — `json.loads` ignores it, so the parsed body and the pin are
  unchanged and only a validator comparing the file to its gate's output can see
  it.
- `bind_review_note()` now validates the record it produced through the production
  gate before returning it, so a note with a legal but unusual name cannot be bound
  by the act and then refused at the gate.

## For the reviewer

`accept_production_identity(record, reviewed_record_sha256=PIN, repo_root=...)`
is the whole public gate. To check this package, do not trust the fixtures —
drive that function directly with a record you edited, a pin you computed
yourself, and a tree you damaged. Every refusal must be an `AcceptanceRecordError`
subclass, never a `KeyError`, `TypeError` or `AttributeError`.
