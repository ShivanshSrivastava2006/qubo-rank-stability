# WP8d — drawn-instance artifact layout, parser and validator (REPAIR r3)

Owner default 5 of `research/g9/kaggle_wp8/WP8_PRODUCTION_BUNDLE_DESIGN.md:155-164`,
approved at `research/decisions/GATE_9_WP7_PINNED_DRAFT_AND_WP7B_OWNER_DECISION.md:146-154`
("Drawn-instance layout: a reviewed generation-artifact layout, with its parser/validator
bound before the first draw").

**This package defines a file layout and validates it. It performs no draw, no scientific
step and no production write.** It has no command line and never imports NumPy. A layout
that parses is not an accepted instance: acceptance stays with the protocol's own gates and
with WP5b's deliberate non-synthetic refusal.

## STATUS: SYNTHETIC-ONLY — NOT PRODUCTION READY

This layout is **synthetic-only** and is **not** production ready. Every fixture value is
synthetic, **no draw was performed**, no production seed or beacon was used, and a real
drawn instance still requires the **separately reviewed WP8b integration** plus an
owner-approved non-synthetic WP5b release path that **does not exist in this repository**
(`stage2_instance_preparation.py:400-466,766-767`).

Passing every check in this document says the layout is **complete, internally consistent
and tamper-evident**. It does **not** say that any instance has been drawn, accepted, or is
fit to publish. The recorded `mu_new`/`Sigma_new` encodings in particular are **fixtures**,
not a draw's output — see "The recorded U-09 moments, precisely" for exactly what they do
and do not establish.

## What r3 changed, and why

Two independent validators agreed on the same blocking finding, and it is the whole
scope of r3.

The first validator (`logs/wp8d.reviewer-evidence.vout.last`) reported the r1 module's
**structural** acceptance and durability gaps. r2 fixed those. The second validator
(`logs/wp8d.r2.builder.retry.vout`) then confirmed r2 fixed them — *"The builder repaired
the original unexpected accepts"* — but found that the **required protocol content was
never added at all**, and that the sweep still failed on 2 stale equivalence entries.

r3 does exactly those two things and nothing else. It preserves all ten r2 repairs, the
five repaired adversarial refusals, and the fsync durability tests unchanged.

### 1. The protocol content that was missing

The protocol requires content the r1/r2 schemas **could not represent**:

| Protocol requirement | Source | r1/r2 state | r3 |
| --- | --- | --- | --- |
| Every attempt — accepted or rejected — retained with one or more **fixed rejection codes** | `GATE_9_STAGE2_PROTOCOL_DRAFT.md:58-62` | `ATTEMPT_KEYS` had no rejection code and no history at all; a record could not say "rejected" | `ATTEMPT.json` **v2**: `disposition`, `rejection_codes`, `rejected_attempt_history` |
| The generated instance records **canonical binary64 `mu_new` and `Sigma_new`** | `GATE_9_STAGE2_PROTOCOL_DRAFT.md:92-105` | `GENERATION_KEYS` had no field for either; the requirement was unrepresentable | `GENERATION.json` **v2**: `moment_summary` with both blocks |

Both were verified as genuinely absent, not merely untested: r3 reconstructs records in
the literal r2 shape, re-seals every hash those records control, and shows each is
refused through the **new** guard. See "Proof the new checks refuse the prior bytes"
below.

**The encoding is derived from the reviewed generator contract, not chosen here.**
`ReturnDraw.mu_hex` and `ReturnDraw.sigma_hex` are produced by `float(value).hex()`
(`stage2_generator.py:337-338`) — CPython's shortest round-tripping C99 `%a` form, which
is exact, platform independent and locale independent. That is exactly what a binary64
value stored in a JSON record needs, and JSON has no byte order of its own. So the
declared encoding is `binary64_hex_c99`, deliberately **not** the matrix's
`binary64_le`: those are two different storage questions, and conflating them is exactly
the silent drift this module exists to prevent.

**No numerical value was invented and no draw was run.** The encodings are supplied by
the caller — in production, by the generator's own `ReturnDraw` fields — and the module
only validates their form, shape and integrity. Fixtures use synthetic fixed vectors.

### 2. Ordering and hash binding

The r1/r2 index bound the generation manifest but not the ledger. r3 adds index schema
**v3** with two blocks:

- `attempt_ledger` — the ledger's exact **bytes**, its content hash, its accepted attempt
  number, its disposition, its rejection-code count and its retained-history count.
- `moments` — the digest of each recorded moment block.

So the ledger and the recorded moments are now committed from **outside** the files that
contain them. A rewritten ledger re-sealed together with its manifest no longer
verifies: the manifest is inside the attacker's reach, the index's ledger-bytes hash is
not. Both bindings are asserted against the files, not trusted from the index.

**Accepted-attempt ordering.** A retained rejected attempt must be numbered strictly
below the accepted attempt, the history must be strictly increasing, and the index's own
validator requires the history count not to exceed the accepted attempt number. That
makes the pair (retained history, accepted attempt) determine the accepted attempt
unambiguously. `verify_instance` checks the ordering against the ledger's real entries,
not merely against the index's count.

### 3. The stale equivalents

r2 left two `EQUIVALENT-ACCEPTED` entries in `logs/wp8d.sweep.layout.equivalents.json`
for the post-promotion `_fsync_dir` sites, which the second validator **killed** — the
calls, their order and their failure path are all observable, and r2's own
`test_fsync_durability_observable` asserts exactly that. An exemption for an observable
site is a test gap recorded as an exemption, so both were retired.

The old file was **not deleted**: it was preserved as
`logs/wp8d.sweep.layout.equivalents.json.bak` (`cp -p`, no `rm -f`, no `rm -rf`), and the
new evidence file is `logs/wp8d.r3.sweep.layout.equivalents.json`, which is an **empty
list**. r3 claims **zero** semantic equivalents; every mutation site is killed by a real
assertion. The retirement is documented in
`logs/wp8d.r3.sweep.layout.equivalents.RETIREMENT.md`.

### Preserved from r2, unchanged

All ten r2 repairs stand, including the five adversarial refusals (slot cross-binding,
WP5b-validated prepared records on both sides, prepared-identity agreement, nested
status, manifest byte-bindings), the rollback-on-durability-failure behaviour, and the
fsync durability tests. The five regression cases in
`test_regression_adversarial_five` are untouched and still pass.

One r2-adjacent defect was found and fixed while wiring the new fields, because the change
would otherwise have introduced it: inlining the generation payload into `write_instance`
(so the bytes it hashes are the bytes it writes) removed the return-matrix length guard
from the write path. It is now asserted explicitly in `write_instance`, with a fixture
covering a short and a long matrix at the write boundary.

## Proof the new checks refuse the prior bytes

`g9_jobs/scratch/wp8d.r3/r2_bytes_probe.py` reconstructs each r2 record byte-shape —
same key set, same schema string, same absent fields — **re-seals every hash those records
control**, and asserts the refusal reaches the *new* guard. Re-sealing matters: a refusal
credited to a stale content hash would prove nothing.

| Probe | Refused through |
| --- | --- |
| r2 `ATTEMPT.json` as emitted | `attempt record has wrong key set` |
| r2 `ATTEMPT.json` + new keys, v1 schema string | `this is a superseded v1 attempt record, which cannot express the protocol's fixed rejection codes or rejected-attempt history` |
| r2 `GENERATION.json` as emitted | `generation record has wrong key set` |
| r2 `GENERATION.json` + moments, v1 schema string | `this is a superseded v1 generation record, which cannot express the protocol's canonical binary64 mu_new and Sigma_new encodings` |
| r2 `INSTANCE.json` as emitted | `instance index has wrong key set` |
| r2 `INSTANCE.json` + new blocks, v2 schema string | `this is a superseded v2 instance index, which cannot bind the retained-attempt ledger or the recorded mu_new/Sigma_new digests` |

The probe also asserts the converse — that the repaired schema **does** carry both
encodings (20 `mu_new` + 400 `Sigma_new` values) — so the difference is the schema, not a
missing capability. Result: **6/6 refusals reached the new guard**. Output:
`g9_jobs/scratch/wp8d.r3/r2_bytes_probe.out`.

## What changed in the r2 repair, and why

This is a repair of the r1 module, not a fresh build. An independent validator
(`g9_jobs/scratch/wp8d.validator.final.gJkgiX/adversarial.py`) found inputs that were
**accepted** and should have been refused. All were reproduced by the lead and are fixed
here, each with a regression test that fails on the r1 bytes.

| # | Was accepted, now refused | Fix |
| --- | --- | --- |
| 1 | `verify_instance(2)` on a `stage2_02` directory whose records all say slot 1 | the requested slot, the directory name and the slot in all three records must agree (`verify_instance`) |
| 2 | a `PREPARED.json` that frozen WP5b's validator refuses, on write **and** on read | `write_instance` and `validate_prepared_directory` both call WP5b's own `validate_provenance_record` (`stage2_instance_preparation.py:811-832`) before and after writing |
| 3 | a prepared record naming a different `instance_id` than the generation | the record's `instance.instance_id` must equal the identity being written, and must equal the generation's on read |
| 4 | a re-sealed index whose **nested** `prepared_record.status` is unknown | the nested status, the nested `non_synthetic_supported` and the top-level `status` are each compared to the prepared **file** |
| 5 | the two post-promotion `_fsync_dir` sites excused as "unobservable" | they are observable: the calls, their order, and the failure path are asserted (`test_fsync_durability_observable`) |
| 6 | a post-promotion fsync failure left the promoted slot on disk | a durability failure after promotion rolls the slot back, so the slot stays retryable |
| 7 | the prepared sidecar's and the meta sidecar's manifest **bytes** were unbound | index schema **v2** binds the prepared manifest's bytes and content hash; all three manifests must be byte-canonical |
| 8 | a prepared record missing `status` leaked `KeyError` | every prepared record is read through WP5b's validator; no direct subscripting survives |
| 9 | `test_write_instance_unique_guards` was an empty shell — a nested test body nothing called | the body is now the function body and runs (~15 checks that never ran) |
| 10 | the notes claimed 423 checks; the fixture ran 415 | the count is now generated by running it; the notes quote the measured number |

### On #5, precisely (still true in r3)

r1 recorded the two post-promotion `_fsync_dir` sites as EQUIVALENT-ACCEPTED, justified by
"no fixture can observe the difference between a synced and an unsynced directory without
crashing the machine". That is true of the **sync** and false of the **call**, the
**order** and the **failure**. All three are observable by substituting a recorder for
`_fsync_dir`, which is what the fixture now does. **No durability call was weakened or
removed to pass the sweep** — the calls are unchanged and are now measured. r3 retires the
two stale exemptions that outlived this fix.

## Files (all three changed; nothing else in the copy was touched)

| File | Role |
| --- | --- |
| `research/g9/wp8d/wp8d_drawn_instance_layout.py` | the layout, its three record schemas, the builder and the validator |
| `research/g9/wp8d/verify_wp8d_drawn_instance_layout_fixtures.py` | the full fixture |
| `research/g9/wp8d/WP8D_DRAWN_INSTANCE_LAYOUT_NOTES.md` | this file |

## The canonical layout

```
research/g9/stage2_instances/stage2_NN/          N = 01..05
    generation/                       WP5 write_generation
        MANIFEST.json                 WP5 manifest (write-once commitment)
        ATTEMPT.json                  retained-attempt record (v2: disposition,
                                      fixed rejection codes, rejected history)
        GENERATION.json               the drawn instance's own record (v2: canonical
                                      binary64 mu_new / Sigma_new encodings)
        returns.f64.le.row_major      249x20 little-endian binary64 doubles
    instance/                         WP5 write_generation
        MANIFEST.json                 WP5 manifest over PREPARED.json
        PREPARED.json                 the WP5b prepared record, verbatim
    meta/                             WP5 write_generation
        MANIFEST.json                 WP5 manifest over INSTANCE.json
        INSTANCE.json                 the per-instance index
```

The instance root is the protocol's per-instance input-manifest location
(`GATE_9_STAGE2_PROTOCOL_DRAFT.md:220-222`); the slot names are the protocol's
(`:51-53`). **This module never creates the instance root** — that location table is a
reviewed choice (`:214-223`).

## Public interface

```python
slot_name(slot) -> str            slot_number(name) -> int
slot_dir(slot, *, root) -> Path   generation_member/prepared_member/meta_member(name) -> str

build_attempt_record(*, slot, attempt, sector_partition_sha256, feasible_count,
                     rejected_attempt_history=()) -> dict
build_rejected_attempt_record(*, slot, attempt, sector_partition_sha256,
                              feasible_count, rejection_codes) -> dict
validate_attempt_record(record) -> dict
build_generation_record(*, slot, attempt, instance_id, return_matrix_sha256,
                        implementation_record_content_sha256, mu_new, sigma_new)
validate_generation_record(record) -> dict
build_instance_index(*, slot, attempt, instance_id, prepared_record_sha256,
                     prepared_record_status, non_synthetic_supported,
                     prepared_manifest_sha256, prepared_manifest_content_sha256,
                     generation_manifest_sha256, generation_manifest_content_sha256,
                     attempt_record_sha256, attempt_record_content_sha256,
                     attempt_disposition, rejection_code_count,
                     rejected_attempt_history_count, mu_new_sha256, sigma_new_sha256,
                     implementation_record_content_sha256)
validate_instance_index(record) -> dict

build_generation_payload(...) -> dict[str, bytes]   # the direct write_generation argument
write_instance(*, slot, attempt, instance_id, sector_partition_sha256, feasible_count,
               return_matrix, prepared_record, implementation_record_content_sha256,
               mu_new, sigma_new, rejected_attempt_history=(), root=ROOT) -> dict

validate_generation_directory(dir) -> dict
validate_prepared_directory(dir)  -> dict
validate_meta_directory(dir)       -> dict
verify_instance(slot, *, root=ROOT) -> dict        # slot int 1..5 or name "stage2_NN"
verify_all_slots(*, root=ROOT, present=()) -> dict
```

Every refusal is a **`LayoutError`** (`ValueError`). WP5's `GenerationWriterError` and
WP5b's `InstancePreparationError` are both translated at the boundary so a caller catches
exactly one exception type.

### `build_instance_index` gained two required keyword arguments (schema v1 → v2)

`prepared_manifest_sha256` and `prepared_manifest_content_sha256`. This is a **breaking
signature change**, deliberate: without them the prepared sidecar's manifest bytes were
unbound and the notes' "binds both manifests' bytes and content hashes" was false. A v1
index will not validate under this module — that is intended, and `INSTANCE_SCHEMA` moved
to `/v2` so the two are distinguishable.

## What "validated" means here — read this before quoting WP8d

**Shape, binding and integrity. Not scientific content.**

- **Shape**: exact key set, schema string, types, hash forms. A field with the right name
  and type but a meaningless value passes.
- **Binding/integrity**: the opened directory is the requested slot; the generation record,
  the index and the WP5b prepared record all name the same instance, slot, attempt,
  implementation record and status; every named file's bytes hash to the named value; a
  forgery that re-seals every hash it controls is still refused.
- **NOT content**: the return matrix is checked for **exact length** (`249*20*8 = 39,840`
  bytes) and for the **SHA-256** the generation record names. The 4,980 binary64 values
  inside are **not** re-derived, range-checked, or checked for finiteness, and no claim
  here should be read as if they were — the values come from the draw, and re-deriving them
  is a scientific step this module is forbidden to take. The prepared record's `results`
  block is sealed by WP5b's validator but the optimisation that produced it is **not**
  re-run.

**A correct statement of what a `verdict="verified"` result means**: this instance directory
is exactly the canonical layout, nothing in it has changed since it was written, and its
three records agree about which instance it is. **An incorrect statement**, which WP8b must
not make: "the drawn instance was semantically validated", or "the numbers were checked".

### The recorded U-09 moments, precisely

The recorded `mu_new`/`Sigma_new` are the protocol content that was most clearly missing, so
it is worth being exact about what is now established about them.

**What IS validated.** *Form*: every value is an exact `str` in the C99 hexadecimal-float
spelling the reviewed generator emits. *Shape*: `mu_new` holds exactly 20 values,
`Sigma_new` exactly 400 row-major with its 20×20 shape declared and checked. *Encoding
name*: both blocks declare `binary64_hex_c99`, deliberately not the matrix's `binary64_le`.
*Integrity*: each block carries a SHA-256 over its own canonical encoded text, **recomputed
and compared** on read, and the index binds both digests — so a changed moment changes the
generation record, the WP5 manifest and the index: three independent commitments, none
repairable by re-sealing another.

**What is NOT validated, and is not claimed.** The layout never decodes these values. It
does **not** check that `mu_new` is finite, that `Sigma_new` is symmetric, that it is PSD,
that it agrees with the return matrix beside it, or that it is the sample covariance of
that matrix. Each of those is a scientific check, this module imports no NumPy by design,
and the protocol makes them the **generator's** post-conditions
(`stage2_generator.py:288-297`) rather than the layout's — a failed
finite/shape/symmetry/PSD validation is a *producer* failure, not a candidate rejection
(`GATE_9_STAGE2_PROTOCOL_DRAFT.md:96-99`). A record may therefore carry a well-formed
encoding of a NaN payload and the layout accepts the **form** while making no claim about
the **value**.

### Attempt history, precisely

**What IS validated.** Each retained rejected attempt carries its own fixed codes from the
closed set, the list is duplicate-free, a rejected attempt cannot carry an empty code list,
an accepted one cannot carry any code, a rejected record cannot itself carry a history,
rejected attempts are numbered strictly below the accepted attempt and strictly increasing,
and the index binds the ledger's bytes, content hash, disposition and both counts.

**What is NOT validated, and is not claimed.** That the history is **complete**. A layout
cannot tell whether attempt 3 was rejected, or accepted and superseded by a later re-draw, or
never made — only the generator's own screening loop knows that, and the protocol's
first-satisfying-attempt rule (`:51-56`) is enforced there. An **empty history is
therefore valid**: it is the truthful record of an attempt accepted at attempt 0, and this
layout does not pretend otherwise. Likewise the fixed codes are validated as **members** of
the generator's enumerated set, not recomputed: which code an attempt earned is the
screening loop's output, and re-deriving it here would mean re-running the feasibility
count.

## Schemas

All three records are **canonical JSON** (sorted keys, `(",", ":")`, ASCII,
`allow_nan=False`) and each carries `content_sha256` = sha256 of the canonical body with
that field removed — byte-identical to WP5's convention
(`stage2_generation_writer.py:83-86`).

- `ATTEMPT.json` (`decisions_os/g9_wp8d_drawn_attempt/v2`) — slot, attempt, **disposition**,
  **fixed rejection codes**, the **retained rejected-attempt history**, the two U-08 seed
  commitments, the partition digest, the feasibility count, scope. **The key set is closed**,
  so no QUBO energy, minimum, tie, label, rate or hypothesis outcome is representable — and
  the rejection codes are drawn from a **closed fixed set** taken from the generator's own
  enumerated outcomes (`stage2_generator.py:258-264`), so a code is a *fixed* code and not a
  free string. An accepted attempt must carry **no** codes; a rejected one must carry **at
  least one**.
- `GENERATION.json` (`decisions_os/g9_wp8d_drawn_generation/v2`) — instance identity,
  return-matrix hash, the fixed 249×20 shape, the **canonical binary64 `mu_new` and
  `Sigma_new` encodings** in `moment_summary`, the implementation record. `Sigma_new` is
  stored flat and row-major with its 20×20 shape declared separately, so the row structure
  and the row count cannot disagree.
- `INSTANCE.json` (`decisions_os/g9_wp8d_drawn_instance_index/v3`) — the generation
  manifest's **bytes and content hash**, the prepared record's **bytes**, the prepared
  manifest's **bytes and content hash**, the **`attempt_ledger` binding** (bytes, content
  hash, accepted attempt, disposition, both counts), the **`moments` digests**, the status,
  and the non-synthetic flag.

### Breaking signature changes, by revision

Each is deliberate, and each moved the schema string so the revisions are distinguishable.
A record from an older revision is refused **by name**, saying what it cannot express.

| Revision | Change | Why |
| --- | --- | --- |
| index v1 → v2 | two required index arguments | prepared sidecar manifest bytes were unbound, so the notes' claim was false |
| attempt v1 → v2, generation v1 → v2, index v2 → v3 | `disposition`, `rejection_codes`, `rejected_attempt_history`, `moment_summary`, `attempt_ledger`, `moments` | the protocol's retained-rejection content and canonical moment encodings were **unrepresentable** in v1 |

### The one binding that is deliberately absent

`meta/MANIFEST.json` commits to `meta/INSTANCE.json`, so the index cannot also commit to
that manifest's bytes: the manifest's content hash covers the index's bytes and the index's
content hash would cover the manifest's. **There is no fixed point, and inventing one is
not possible.** The gap is closed by a different sound rule: every manifest **file** must be
the canonical encoding of the manifest it commits to, so a byte change that is not a
re-encoding is refused. The meta manifest's hash is also returned in the write receipt so an
owner approval or the WP8 bundle can bind it externally.

## INTEGRATION GAP for WP8b — must be closed before any real instance

**This package cannot yet accept a production instance, by design, and that is not a bug.**

1. **Synthetic-only provenance.** `ACCEPTED_STATUSES = ("prepared_synthetic_only",)` is the
   only accepted status and `non_synthetic_supported is True` is **refused**, because the
   reviewed non-synthetic WP5b release path (owner default 2,
   `GATE_9_WP7_PINNED_DRAFT_AND_WP7B_OWNER_DECISION.md:150`) **does not exist in this
   repository** — WP5b refuses non-synthetic instances outright
   (`stage2_instance_preparation.py:400-466`). This is deliberately **fail-closed** and must
   stay that way until a separately reviewed, production-capable version lands.
2. **What WP8b must do**: do not widen `ACCEPTED_STATUSES` in this module. When the
   production-capable WP5b exists, it needs a **separately reviewed** change here — the
   natural form is a **new status string plus a `/v3` index schema in a new parallel layout
   module**, not an edit to this one, so the synthetic-only package keeps its fail-closed
   guarantee. Deciding the version/schema naming is lead engineering within the approved
   defaults, not a new permission boundary: default 5 already authorises building the
   real-instance layout.
3. **Do not fabricate an accepted identity or a production release.** Nothing here
   constitutes owner approval, an acceptance record, a production validator, or a draw
   permission.

## OWNER QUESTION (safe default in force)

**When the reviewed non-synthetic WP5b release path (default 2) lands, what should its
prepared-record status string be, and should this layout accept it?** *Safe default,
already in force:* the new status is **not** anticipated — a record carrying it is refused by
name until this module is re-reviewed, which keeps a drawn-but-unreviewed instance from
being treated as usable. The owner should confirm whether the new path gets its own `/v3`
schema and a parallel layout module rather than widening this accepted set.

## Mutation gate

`g9_guard_sweep.py` **v1.1** (`TOOL_VERSION = "1.1"`, `tools/g9_guard_sweep.py:61`), **FULL
fixture**, `--chunk-seconds 36000`, **4 workers**, with the **empty** r3 equivalents file
`logs/wp8d.r3.sweep.layout.equivalents.json`:

```
  shape  sites              KILLED             TIMEOUT            SURVIVED               ERROR EQUIVALENT-ACCEPTED               STALE
  S1       148                 148                   0                   0                   0                   0                   0
  S2        88                  88                   0                   0                   0                   0                   0
  S3        19                  19                   0                   0                   0                   0                   0
  S4       132                 132                   0                   0                   0                   0                   0
  S5       154                 154                   0                   0                   0                   0                   0
  S6         0                   0                   0                   0                   0                   0                   0
  ALL      541                 541                   0                   0                   0                   0                   0

no survivors, no errors, no stale equivalents

SWEEP: PASS
```

**541 sites, 541 KILLED, 0 survivors, 0 errors, 0 stale, 0 EQUIVALENT-ACCEPTED.** The site
count differs from r2's 362 because r3 adds guards and every guard adds sites — and because
four unreachable guards were *removed* rather than exempted, which removes sites too.

Sweep output: `logs/wp8d.r3.sweep.txt`; results JSON: `logs/wp8d.r3.sweep.results.json`.

The equivalents file used for the r3 run is **empty**, so a stale entry is impossible by
construction: a stale entry is one whose site id no longer exists, and with no entries there
are none. The superseded r2 file is preserved as
`logs/wp8d.sweep.layout.equivalents.json.bak` and its retirement is documented in
`logs/wp8d.r3.sweep.layout.equivalents.RETIREMENT.md`.

### Getting to zero equivalents

r1 carried a `--equivalents` file justifying two `EQUIVALENT-ACCEPTED` sites and reported
one `SURVIVED`. r2 kept the two exemptions after the sites became observable, which is why
r2's sweep exited FAIL on **2 STALE** entries. r3 claims **no equivalents at all** — every
site is killed by a real assertion. Getting there meant, in order:

1. **Restoring a dead test.** `test_write_instance_unique_guards` was an empty shell: its
   entire body was a nested `def` nothing called, so the `_require(type(prepared_record)
   is dict, ...)` site it exercised never ran and was a `SURVIVED` mutant. The body is now
   the function body.
2. **Writing the tests r1 declined to write.** The two `_fsync_dir` sites are observable
   (call, order, failure), and their refusal paths are now asserted. The new provenance,
   identity, slot, nested-status, prepared-manifest and rollback guards are all exercised.
3. **Removing three guards that were genuinely unobservable**, each with the reason
   recorded in place — no weak test and no invented test:
   - `base.name == slot_name(number)`: a tautology, because `base` was just built as
     `slot_dir(number)`.
   - `index["status"] == prepared["prepared_record_status"]`: both sides are forced to the
     single string in `ACCEPTED_STATUSES`, so there is no falsifiable input.
   - `index["prepared_record"]["non_synthetic_supported"] == prepared[...]`: both sides are
     forced to the single object `False`.

   The last two are the reason the **nested `prepared_record["status"]`** cross-binding IS
   kept: the index's own validator never inspects that field, so it is not forced, and only
   the comparison to the file stops a re-sealed index from misreporting its prepared record.
4. **Writing the tests the r3 code needed.** The r3 sweep took three rounds to reach zero
   survivors — **8**, then **8** again — and every survivor was in the new v2/v3 code. None
   was exempted. Each was exercised, or removed with a proof that it could not fire:
   - four scalar guards on the new `build_rejected_attempt_record` — its tests only ever
     passed valid arguments, so no fixture could falsify them. Nine boundary cases added.
   - a **rejection-code length cap** — unobservable by construction: with a closed 3-code
     set and duplicates already refused, the longest legal list is 3, so the cap could only
     fire on an input the duplicate check refuses first. Removed rather than kept and
     excused; the field is bounded by `len(REJECTION_CODE_SET)`, which is the real bound.
   - a `_sha` on the moment block's own digest — provably redundant, because the digest is
     recomputed from the canonical encoding and compared a few lines later, so no input can
     make the format check fire without the comparison firing too. Removed.
   - a `type(values) is not str` conjunct alongside `isinstance(values, (list, tuple))` —
     provably redundant, since `str` is neither a `list` nor a `tuple`. Removed.
   - a `_require_disposition_codes(ACCEPTED, [], ...)` in `build_attempt_record` — a
     tautology: the disposition is a hard-coded constant and the code list a hard-coded
     empty literal, so no input could falsify it. The rule is enforced on the read side,
     where both values come from the record.
   - four **cross-record** comparisons in `verify_instance` — each dominated by an earlier
     check in the same function or in the record's own validator: the ledger disposition
     (the file's own validator admits only `accepted` for a record carrying a history), the
     index's top-level attempt (transitively equal via the ledger binding just above it),
     and the history-ordering pair, which `_rejected_history` already guarantees.
     Exhaustive enumeration over the legal histories confirmed no accepted record can
     violate the ordering comparison. All four removed, not exempted.
   - a moment-block shape check and the two index attempt range guards, which were
     reachable but had **no falsifying input**: a wrong-length shape was caught earlier by
     the `values` length check, and the two attempt range guards could never fire because
     every fixture moved *both* attempt fields together. Both were made falsifiable instead
     — the shape comparison is now a length test plus a per-element type test plus a
     per-element value test with fixtures for right-length-wrong-contents, wrong-length,
     three-deep, and `str`/`float`/`bool` elements; and the attempt guards each got their own
     single-field case, plus an **acceptance control** asserting that a legal, equal pair is
     still accepted. Without that control a guard refusing *every* attempt change would
     pass every refusal case in the table.

## Verification performed

| Check | Result |
| --- | --- |
| `python3 -B` fixture | **PASS (680 checks)** |
| `python3 -B -O` fixture | **PASS (680 checks)** — identical count, so nothing depends on `__debug__` |
| `r2_bytes_probe.py` — prior r2 record bytes vs the new guards | **6/6 refusals reached the new guard** |
| r2's five repaired adversarial refusals | **preserved and passing** (`test_regression_adversarial_five`) |
| r2's fsync durability tests | **preserved and passing** (`test_fsync_durability_observable`) |
| `g9_guard_sweep.py` **v1.1** FULL fixture, 4 workers, empty equivalents | **SWEEP: PASS — 541/541 KILLED, 0 survivors, 0 stale** |
| `.pyc` files anywhere in the copy | **0** |

### File hashes (SHA-256)

| File | SHA-256 | Lines |
| --- | --- | ---: |
| `wp8d_drawn_instance_layout.py` | see `logs/wp8d.r3.bout` | 2213 |
| `verify_wp8d_drawn_instance_layout_fixtures.py` | see `logs/wp8d.r3.bout` | 3114 |
| `WP8D_DRAWN_INSTANCE_LAYOUT_NOTES.md` | see `logs/wp8d.r3.bout` | this file |

The authoritative hashes are recorded in `logs/wp8d.r3.bout`; a note cannot contain its own
hash, so this table points at the record rather than duplicating a number that would go
stale the moment this file is edited.

No production seed, no draw, no GPU, no network, no credentials, no package changes, and no
file outside `research/g9/wp8d/` was modified in the copy.

## Interface notes for the other WP8 packages

- **WP8 (bundle)** — take `verify_instance(...)` hashes, not a directory path. The index's
  `content_sha256` is the one field to bind per instance; `instance_id` is caller-supplied
  and is **not** derived here, so the bundle must bind it explicitly. Also bind
  `meta_manifest_sha256` from the write receipt (see the absent binding above). The index
  now also carries `moments.mu_new_sha256` / `moments.sigma_new_sha256` and the
  `attempt_ledger` digests, so a bundle can bind the recorded moments without reopening
  `GENERATION.json`.
- **WP8b/8c** — `write_instance` is the only supported writer; it refuses an existing slot,
  so a retry is a fresh attempt, never a merge. A durability failure after promotion
  **rolls back**, so a retry after one really does succeed. When a real draw happens, the
  caller passes `mu_new=draw.mu_hex` and `sigma_new=draw.sigma_hex` straight from the
  generator's `ReturnDraw` — **this module must not compute them**, and it will refuse a
  malformed encoding rather than repair one.
- Callers do **not** need to run WP5b's `validate_provenance_record` first. The repair
  removed that caller-discipline requirement because it was a test gap dressed as a rule;
  `write_instance` now calls the real validator itself. The prepared record's own
  `instance.instance_id` must still match the `instance_id` argument.
- **The retained history is the caller's to build.** `rejected_attempt_history` defaults to
  `()` because an attempt accepted at 0 has nothing to retain. Populating it truthfully is
  the screening loop's job; this layout validates what it is given and cannot detect a
  missing entry. Do not synthesise a history to make a record look complete.
- No production seed, no draw and no GPU were used. Fixture values are conspicuously
  non-production constants; the matrix is synthetic filler and the moments are synthetic
  fixed vectors, not a draw.
