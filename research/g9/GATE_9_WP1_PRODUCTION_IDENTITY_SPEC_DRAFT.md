# Gate-9 WP1 — Stage-2 PRODUCTION qualification identity — DRAFT schema

**Status: DRAFT.** This document, and the module it describes
(`research/g9/stage2_production_identity.py`), are a **schema proposal only**.
They issue no identity, qualify nothing, and **authorize nothing**.

- They authorize no Kaggle push, run, or kernel version.
- They authorize no candidate draw, instance, ground truth, or scientific
  record.
- They do not fire D013 or change its trigger, conditions, grids, or
  coordinates.
- They do not close §B, which remains **OPEN**.
- The identity described here **is issued only after the WP7 non-scientific dry
  run and owner acceptance.** Until then the schema field
  `status` is literally `DRAFT_UNQUALIFIED` and `authorization` is literally
  `NONE`, and the module **refuses** any payload claiming otherwise.

**Builder:** external model, WP1, offline build with synthetic fixtures.
**Date:** 2026-09-27.

---

## 1. Why this record exists, and what it is not

The §A owner acceptance of 2026-09-25 is explicit that **no production
qualification identity has been issued**
(`GATE_9_CUDA_CORE_A_VERSION1_OWNER_ACCEPTANCE.md:64-73`):

> No canonical `qualification_identity()` payload or hash is emitted by this
> decision. **Source-map scope**, compiler-flag scope, and the future-session
> pre-write image check remain unresolved.

Those three gaps are what this schema closes as a *design*, not as a fact:

| §A open item | Closed here as |
| --- | --- |
| Source-map scope | §2, the nine-role table, from owner decision 2 |
| Compiler-flag scope | §3.1, the frozen contract's `compiler_flags`, passed through unchanged |
| Future-session pre-write image check | §3.2 (recorded as platform-reported) and §4, the exact-match rule that WP2 will call before any write |

Two things this schema deliberately does **not** do:

- It does not **re-derive** the qualification identity's canonicalization. It
  composes the frozen `qualification_identity()` of
  `research/g9/cuda_qualification/stage2_cuda_execution_contract.py`, one of the
  12 §A-frozen files, which is imported and never edited. See §5.1.
- It does not claim the image is proven. See §3.2.

---

## 2. The role table

The production identity's source map is the scope fixed by owner decision 2
("Bind producer files"), `GATE_9_WP0_D013_CUDA_PATH_AND_IDENTITY_SCOPE_OWNER_DECISION.md:36-43`,
quoted verbatim:

> 2. **Production identity scope (G10):** "Bind producer files".
>    - The production qualification identity's source map = the 12 v1 §A files
>      plus the new `+0.0` path plus every host-side file that shapes a scientific
>      record: coordinate iterator, record writer, D016 reconstruction, the §B
>      item 1/2 harnesses and the generation-binding code.
>    - Any change to any of them forces a new qualification before further
>      records.
>    - The production identity is qualified in the WP7 dry run.

The decision is binding and is not conditional (WP0 gap audit §3.0.2, §3.1,
round 3). The table is **fixed**: nine roles, no more, no fewer.

| Role | Binds | State | Gap / owner |
| --- | --- | --- | --- |
| `v1_engine` | Exactly the 12 files of `GATE_9_CUDA_CORE_CORRUPTION_QUALIFICATION_RELEASE.json` | **BUILT** | §A, accepted 2026-09-25 |
| `d013_plus_zero_cuda_path` | The new additive CUDA `+0.0` inactive-family path and its host side | **NOT BUILT** | G5b / WP6b, owner decision 1 |
| `coordinate_iterator` | The per-coordinate 3-D iterator producing the canonical linear coordinate order | **NOT BUILT** | G1 / WP4 |
| `record_writer` | Staged writes, atomic promotion, range manifests, interrupted-range discard, missing-range-only resume, final-set exact-cover audit | **NOT BUILT** | G7 / WP4 |
| `d016_reconstruction` | D016 reconstruction and label building, host-side, including the `c_f` comparator dimension | **NOT BUILT** | G2, G3 / WP4 |
| `section_b1_recheck` | The §B item 1 pre-write harness: protocol, generator, ground-truth, source, platform, compiler identities, fail closed | **NOT BUILT** | G8 / WP2 |
| `section_b2_harness` | The §B item 2 in-session full-domain comparison harness, and the §B item 3 session output | **NOT BUILT** | G9 / WP3 |
| `generation_binding` | Implementation record pinning generator and validator hashes plus the full runtime fingerprint | **NOT BUILT** | WP5 |
| `per_instance_preparation` | Per-instance preparation required by protocol §4: original feasible optimum, `Lambda_ref`, D006/D008/D010 ledgers under the frozen formulas | **NOT BUILT** | WP5b |

`per_instance_preparation` is WP5b, added by the closure plan's 2026-09-27
revision after the WP0 round-3 validator surfaced it. It is record-shaping, so
it is bound.

`section_b2_harness` binds both the §B item 2 harness **and** the §B item 3
session output, because the amendment's item 3 *is* the output that harness
writes (record 16 of the WP0 full record list).

### 2.1 What the builder refuses

`build_source_map(repo_root, role_paths)` takes `{role: [repo-relative paths]}`
and refuses, naming the offending role and value:

| Refusal | Trigger |
| --- | --- |
| unknown role | a key not in the nine-role table |
| missing role | any of the nine absent from the map |
| empty role | a role bound to `[]` |
| role value not a sequence | a bare `str` or a `dict` instead of a list of paths |
| duplicate path across roles | one path claimed by two roles |
| repeated path within a role | the same path listed twice in one role |
| non-string path entry | a non-`str` element |
| absolute path | `/etc/passwd`, `//research/...` |
| whitespace-padded path | `" research/g9/....py"` |
| backslash path | `research\g9\....py` |
| colon path | a Windows-style or otherwise colon-bearing component |
| traversing or empty component | `./x.py`, `a//b.py`, `a/../b.py` |
| non-`.py`/`.cu` extension | a bound path that is not a CUDA or Python source |
| repository-root escape | a **symlink** whose target resolves outside the repo root |
| unreadable file | a path that is not an existing regular file, or an `OSError` on read |

The symlink case is the only way the escape check is reachable, and the
fixtures build a real symlink to prove it.

### 2.2 The `v1_engine` role is hash-pinned, not merely listed

The `v1_engine` role is special: its 12 files are closed by an **accepted
owner record**, not by this package. Three independent refusals apply, in this
order so each is reachable and each names its own defect:

1. The **release file itself** must be the accepted one:
   `GATE_9_CUDA_CORE_CORRUPTION_QUALIFICATION_RELEASE.json` must have
   SHA-256 `585da5d87908738e34c9b9858a0ef6d1c5e5cf4311dd1f6e3ba00a9d0ce6bfb9`
   — the value the owner accepted as the "§A execution release"
   (`GATE_9_CUDA_CORE_A_VERSION1_OWNER_ACCEPTANCE.md:39`).
2. The role must bind **exactly 12** files.
3. The role's file **set** must be exactly the release's set, and **every hash**
   must equal the release's hash.

The structural checks inside `load_v1_release` (key set, schema, `approved`
status, entry count, every entry a lowercase SHA-256, every entry a `.py`/`.cu`
source, `plan_content_sha256` a SHA-256) run **before** the pin. Putting the
pin first would make all of them dead code, because any edit to the file changes
its hash. The fixtures prove each is reachable by damaging one defect at a time.

**None of the 12 §A files changes.** They are byte-identical, and the fixtures
re-verify the real 12 files read-only on every run.

---

## 3. The fields

### 3.1 Numerical platform (8 fields)

These are the frozen contract's `IDENTITY_PLATFORM_KEYS`, one for one. They are
the numerical properties the approved amendment says are "not guessed in
advance" and are "captured in a qualification identity"
(`GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md:27-31`).

| Field | Meaning | Source |
| --- | --- | --- |
| `gpu_name` | allocated accelerator model | host device query, e.g. `nvidia-smi` name |
| `compute_capability` | device compute capability `major.minor` | device query |
| `cuda_driver_version` | driver version, numerically | device query |
| `cuda_runtime_version` | CUDA runtime version, numerically | device query |
| `nvcc_version` | full `nvcc` banner verbatim | the compiler itself |
| `kaggle_image` | Kaggle image/build string — **platform-reported**, see §3.2 | platform |
| `python_version` | interpreter version | executing host |
| `numpy_version` | `numpy.__version__` | executing host |

All eight must be non-empty, whitespace-stripped strings. Missing, extra, empty,
padded, float, `None`, bool or int leaves are refused. So are the transient
fields of §3.3.

`kaggle_image` sits in the numerical block only because the **frozen contract**
defines no separate channel for it; `IDENTITY_PLATFORM_KEYS` is fixed and this
schema does not fork it. It is a string, and a change to it is a difference.

**Compiler flags** are passed to the frozen `qualification_identity()` unchanged.
This schema does **not** re-check them: the frozen contract already refuses a
non-sequence, an empty list, and duplicates. The schema only *copies* the
caller's sequence, so a later caller-side mutation cannot alter an
already-committed payload. Flag **order** is part of the identity, because the
frozen contract preserves it verbatim and `exact_match` compares the lists.

### 3.2 Image and build fields (7 fields) — PLATFORM-REPORTED

| Field | Meaning |
| --- | --- |
| `kaggle_docker_image_platform_reported` | the Kaggle image channel, as the platform reports it |
| `kaggle_saved_version_build_platform_reported` | saved kernel version's build identifier, as reported |
| `kaggle_image_manifest_digest_platform_reported` | image manifest digest, as reported |
| `kaggle_image_config_digest_platform_reported` | image config digest, as reported |
| `kaggle_kernel_version_platform_reported` | the saved kernel version the run was recorded against, as reported |
| `runtime_build_observed_platform_reported` | build/env values observed inside the run (`CUDA_VERSION`, `BUILD_DATE`, `cuda_home`, `nvcc_path`, …) |
| `kaggle_environment_pinning_platform_reported` | **the Kaggle environment pinning setting, as the platform reports it** |

**These are platform-reported, and are never proof.** The provider-trust
amendment §3 requires it in terms
(`GATE_9_SECTION_B_KAGGLE_PROVIDER_TRUST_AMENDMENT_DRAFT.md:20-24`):

> Image metadata—such as `KAGGLE_DOCKER_IMAGE`, saved-version metadata, and
> filesystem/package fingerprints—are recorded strictly as **PLATFORM-REPORTED**.
> They must be labelled as such in every record, and are never called proof.
>
> A change in platform-reported image metadata **still forces requalification**
> under the approved execution rule.

The schema enforces the label **structurally, not by convention**:

- The **key** must end in `_platform_reported`. The key set is fixed to exactly
  these seven names, all of which carry the suffix, so a map with that key set
  cannot present an unlabelled field.
- The **value** must be a non-empty string ending in the marker
  `[platform_reported]`. A value relabelled as proof, e.g. `[verified_proof]`,
  is refused.
- The evidence block carries `evidence_kind: "platform_reported"`, a literal
  `is_proof: false`, and a statement that says the values are not independently
  measured inside the GPU run and are not proof. Validation **re-checks** all
  three, so a hand-edited payload cannot upgrade them.
- The evidence block's `kaggle_image_reported_string` must equal the
  numerical platform's `kaggle_image` slot; the two views of the image cannot
  drift apart unnoticed.

**The environment pin is a field because pinning is now an operational
requirement, not a nicety.** The closure plan records it: with the
independent pre-write image proof removed, an unpinned notebook "can silently
move to a new image and invalidate the qualification identity"
(`GATE_9_SECTION_B_CLOSURE_PLAN_DRAFT.md:12-20`). So the pin's reported value
is carried in the identity, and a session reporting `unpinned` is refused by
name.

### 3.3 Excluded: device UUID and session ID

The approved amendment excludes them in terms (`:31-32`):

> …and deliberately excludes the transient device UUID and session ID.

They are **refused if supplied anywhere** in the platform map, the image/build
map, the source map or the evidence block, at any nesting depth. Matching is by
case-folded substring over `uuid`, `session_id`, `pci_bus_id`, `bus_id`, so
`device_uuid`, `device_uuid_hex`, `DEVICE_UUID` and `run_session_id_2` are all
caught. This is the amendment's rule; a second exact-name list would be
unreachable code, so there is only one list.

---

## 4. Composition and the exact-match rule

### 4.1 Composition

`build_production_identity(...)` produces:

```
schema                       "decisions_os/g9_stage2_production_qualification_identity/draft_v1"
status                       "DRAFT_UNQUALIFIED"        <- refuses any other value
authorization                "NONE"                     <- refuses any other value
authorization_note           why this authorizes nothing
qualification_identity       the FROZEN contract's payload, verbatim
source_map                   the nine-role hashed map
image_build_evidence         the platform-reported block
content_sha256               the FROZEN contract's content hash over all of the above
```

The `qualification_identity` member **is** the frozen contract's output: the
platform, the flat source-hash map and the flags are handed to
`qualification_identity()` and its payload is embedded unchanged. Validation
re-runs the frozen `validate_qualification_identity()` on it, so a
non-canonical or tampered inner payload is refused **by the frozen code**.

`validate_source_map_shape()` re-derives rather than trusts: the role set, each
entry's shape, sorted order, the single-use path rule, and `bound_file_count`
are all recomputed and compared.

**Cross-view binding.** The role-tagged source map and the frozen contract's
flat `source_sha256` are two views of the same bound files. Each identity must
agree with **itself** across both views, or the identity is refused as
structurally inconsistent. Without this, a payload whose source map was edited
independently of the frozen numerical view would pass both validators and be
merely *compared* rather than refused.

### 4.2 The exact-match rule

`exact_match(session_identity, accepted_identity)` refuses on **ANY** difference
and names every differing field. There is no tolerance, no allowlist, no
"close enough" path, and it is **symmetric**: neither argument is privileged.

It compares, in this order:

| Comparison | Prefix in the refusal |
| --- | --- |
| inner `qualification_identity` schema | (frozen contract refuses first) |
| every numerical platform field | `qualification_identity.platform.<key>` |
| every frozen source hash | `qualification_identity.source_sha256.<path>` |
| the compiler-flag list, order included | `qualification_identity.compiler_flags` |
| the bound-file set, as a summary | `bound file(s) differ: <paths>` |
| source-map anchors and schema | `source_map.<field>` |
| every role's `{path: sha256}` | `source_map.roles.<role>.<path>` |
| the cross-view binding, on **both** arguments | `<side> source_map and frozen qualification_identity disagree on bound file(s): <paths>` |
| every image/build field | `image_build_evidence.fields.<key>` |
| the two content hashes | `content_sha256` |

The remaining fields are **not** compared above because they are already pinned
to a single admissible value on **both** payloads by validation, so they cannot
differ between two valid identities. The full, authoritative list is the table in
§4.3; in short: every top-level constant (`schema`, `status`, `authorization`,
`authorization_note`), the two frozen-contract fields, the source-map scalars
(`schema`, `hash_algorithm`, the two anchors, `bound_file_count`,
`not_yet_built_roles`) and the four scalar evidence fields (`evidence_kind`,
`is_proof`, `statement`, `kaggle_image_reported_string`). Comparing them again
would be unreachable code, and §4.3's fixture asserts the validator refuses each
of them **by name** rather than leaving any of them an unnamed hole.

The refusal type is `ProductionIdentityMismatch`, a subclass of
`ProductionIdentityError`, carrying `.differing_fields` **and** a message that
names them. The fixtures mutate the type to a bare `ValueError` and require
failure, so the typed guarantee is pinned.

### 4.3 Every field is PINNED or COMPARED — never neither

The rule above is only as good as its coverage. Round 1 failed its independent
validation precisely because two fields were **neither**: `authorization_note`
was in the payload's key set but its value was never checked, and
`image_build_evidence.statement` was checked only for *containing* the substring
`PLATFORM-REPORTED` rather than for being one exact string. `exact_match` treated
both as "already pinned" and skipped them, so a change in either surfaced only as
the catch-all `content_sha256` mismatch, **unnamed**.

This is now a declared property, not a claim. `FIELD_COVERAGE` in
`stage2_production_identity.py` maps **every field path** of the payload to the
one mechanism that binds it, and `check_field_coverage()` refuses any payload
whose field paths are not exactly the declared ones — in **both** directions: a
field no row covers, and a row no field covers. A field added later without a row
is a refusal, so the round-1 failure cannot recur silently.

`PINNED` means `validate_production_identity()` requires the field to equal one
exact constant, so two valid identities cannot differ in it. `COMPARED` means
`exact_match()` compares it field-by-field and names it. A `*` component is a
wildcard matching any one key at that position.

| Field path | Mechanism | Enforced by |
| --- | --- | --- |
| `schema` | **PINNED** | `PRODUCTION_IDENTITY_SCHEMA` |
| `status` | **PINNED** | `DRAFT_STATUS` = `DRAFT_UNQUALIFIED` |
| `authorization` | **PINNED** | `NO_AUTHORIZATION` = `NONE` |
| `authorization_note` | **PINNED** | `AUTHORIZATION_NOTE` — the one admissible wording |
| `qualification_identity.schema` | **PINNED** | the FROZEN contract |
| `qualification_identity.content_sha256` | **PINNED** | the FROZEN contract (re-derived) |
| `qualification_identity.platform.*` | **COMPARED** | per-key, `…platform.<key>` |
| `qualification_identity.source_sha256.*` | **COMPARED** | per-path, `…source_sha256.<path>` |
| `qualification_identity.compiler_flags.*` | **COMPARED** | the list, order included |
| `source_map.schema` | **PINNED** | `SOURCE_MAP_SCHEMA` |
| `source_map.hash_algorithm` | **PINNED** | `HASH_ALGORITHM` = `sha256` |
| `source_map.v1_engine_release_sha256` | **PINNED** | `V1_RELEASE_SHA256` |
| `source_map.v1_engine_plan_content_sha256` | **PINNED** | re-derived from the accepted release |
| `source_map.bound_file_count` | **PINNED** | re-derived from the role entries |
| `source_map.not_yet_built_roles.*` | **PINNED** | re-derived from `ROLE_TABLE` |
| `source_map.roles.*.*.path` | **COMPARED** | per-role, `…roles.<role>.<path>` |
| `source_map.roles.*.*.sha256` | **COMPARED** | per-role, `…roles.<role>.<path>` |
| `image_build_evidence.evidence_kind` | **PINNED** | `PLATFORM_REPORTED_LABEL` |
| `image_build_evidence.is_proof` | **PINNED** | must be `False` |
| `image_build_evidence.statement` | **PINNED** | `PLATFORM_REPORTED_STATEMENT` — the one exact string |
| `image_build_evidence.kaggle_image_reported_string` | **PINNED** | must equal the frozen `platform.kaggle_image` |
| `image_build_evidence.fields.*` | **COMPARED** | per-key, `…fields.<key>` |
| `content_sha256` | **COMPARED** | the catch-all backstop |

**There is no field that is neither.** Two notes on reading the table:

* `content_sha256` is COMPARED, not pinned. The outer digest is a seal, not a
  constant: two valid identities carrying different reported image values have
  different digests. It remains the **backstop** — no other comparison is
  required for it to fire — but it is a genuine compared field, and a bare edit
  of it alone is refused by the validator as a content-hash mismatch.
* A bound file's hash lives in **two** views of the payload (the frozen flat map
  and the role-tagged map). `exact_match` checks the cross-view binding on both
  arguments, so editing one view alone is refused before any comparison. Both
  views are COMPARED, and a consistent difference in both is named twice, once
  per view, plus the aggregate `bound file(s) differ` summary.

---

## 5. What forces requalification

The approved amendment's rule, quoted
(`GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md:33-36`):

> A changed GPU model, compute capability, driver, runtime, compiler, image,
> source, or numeric-compiler flag requires a new qualification before any
> further record is written.

The owner's decision makes *"source"* concrete for production: editing the
iterator, the writer, the reconstructor, either harness, the generation binding,
the per-instance preparation, or the `+0.0` path is a requalification event,
not a silent host-side change (WP0 §3.1).

Concretely, under this schema **each of the following forces a new
qualification**, and each is refused by name:

1. **One byte** in any bound file, in any role — including a §A-frozen one.
2. A change to any of the 8 numerical platform fields.
3. A change to any of the 7 image/build fields, **including the image label
   and the environment pin**, because platform-reported is not proof.
4. Any change to the compiler flags, **including their order**.
5. A file added to or removed from any role, or moved between roles, even when
   the file bytes are identical.
6. A re-pointed source-map anchor (`v1_engine_release_sha256`,
   `v1_engine_plan_content_sha256`).

Requalification means re-running WP7 and re-accepting. It is not a judgement
call this schema can make.

---

## 6. How this was verified

`research/g9/verify_stage2_production_identity_fixtures.py` — 66 checks, all
raising (no `assert`, so `python3 -O` cannot strip them into vacuity), run
under `python3 -B` **and** `python3 -B -O` with identical results and zero
`.pyc` files.

Synthetic roles are built inside `tempfile.TemporaryDirectory`. The only real
files read are the 12 §A files and the release file, read-only; the fixtures
never write to the repository. Where a bound file must be altered, the fixture
mirrors the whole tree into a temp directory, **verifies the mirror is
byte-identical to the original**, and alters the mirror.

Coverage includes: every refusal in §2.1; every structural check of the release
anchor, each reached by damaging exactly one defect; every source-map shape
check; every platform and image/build refusal; a one-byte change in a bound
file; each of the 8 platform fields and each of the 7 image/build fields
changed one at a time and refused **by name**; reordered, replaced, added and
swapped compiler flags; a role swap with identical bytes; a tampered release
file; a tampered v1 file; a self-declared `QUALIFIED`/`AUTHORIZED` status.

**The completeness fixture.** `test_every_leaf_is_pinned_or_compared_and_named`
enumerates **every** leaf path of a real built identity (72 leaves in the
synthetic configuration) and, for each one, mutates that single leaf, keeps the
payload otherwise well formed, and requires that `exact_match` **refuses** *and*
**names** it — in `differing_fields` for a COMPARED leaf, or in the refusal
message for a PINNED leaf. For a COMPARED leaf it additionally requires that the
difference is **not** reported by the catch-all hash alone, which is the exact
round-1 defect. The run reports 16 pinned and 56 compared leaves.

**Mutation table.** Every check in the module was individually disabled, and
every constant and coverage row individually corrupted, in a throwaway temp copy,
and the fixtures re-run: **97 mutations, 97 caught, 0 still passing, 0 anchor
errors.** Round 1's process found nineteen dead or redundant checks and removed
them rather than leaving them in place — among them a `normpath` check that added
no coverage over the component check, an exact-name forbidden-key list subsumed
by the substring match, a de-duplication pass that no comparison could trigger,
and a `_hex_or_refuse` shape check on a value that is a fresh `content_sha256`
and therefore already well formed. Each removal is recorded in the module's
comments at the point where the code used to be.

Round 2's mutation pass found four more gaps, and all four were **fixed with a
fixture** rather than papered over:

| Gap found by mutation | Fix |
| --- | --- |
| `AUTHORIZATION_NOTE` wording could change with the fixtures still passing, because the builder and the validator share the constant | `test_pinned_constants_are_fixed_values` asserts the constant's literal value *and* the phrases it must contain, and that it must not claim qualification, approval or authorization |
| `SOURCE_MAP_SCHEMA` and `HASH_ALGORITHM` likewise moved builder and validator together | same fixture, same literals |
| the length test in `_row_matches` was unexercised, so a one-component row could have covered a deeper field by prefix | a fixture adds a one-component `source_map` row and requires the deeper fields to be reported uncovered |
| the coverage check's "uncovered" and "unexercised" branches were unexercised | `test_field_coverage_is_load_both_ways` exercises both, plus a narrowed wildcard row |

The same pass also showed that `AUTHORIZATION_NOTE` and `PLATFORM_REPORTED_STATEMENT`
must be asserted by **content**, not merely by identity with themselves: a pin to
a string that no one checks the wording of is not a pin.

---

## 7. Open, and not decided here

- The **compiler-flag scope** is passed through the frozen contract, but the
  *policy* question of which flag set production will use is not settled by
  this schema. The §A eight flags are the only set with evidence.
- The **`per_instance_preparation` (WP5b) file list** is bound as a role but
  the files do not exist yet; the role will be filled with real paths when
  WP5b lands.
- **WP2** must call `exact_match` before any write, and **WP3/WP4** must call it
  before contributing a range. This schema provides the function; wiring it in
  is their work.
- The **§B item 1 recheck** additionally covers protocol, generator and
  ground-truth identities, which are not files in this source map and are not
  part of this schema.
- **§B.3 commitment shape** (WP0 §5) must be fixed in WP4 before production.
  It is a separate record and is not modelled here.
