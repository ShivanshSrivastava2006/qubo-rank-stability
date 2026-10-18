# WP8d-production — production-capable drawn-instance layout (v1)

**Status: BUILD + VALIDATION ONLY. UNARMED. NOT A DRAW, NOT A RELEASE.**

This is a NEW, separately versioned layout package. It builds in the isolated copy
`g9_jobs/copies/wp8dprod.cMkW/project` at `research/g9/wp8d_production/`. It does not
modify, patch, subclass-for-circumvention or re-implement either reviewed package it
builds on:

| package | role | bytes |
|---|---|---|
| `research/g9/wp8d/wp8d_drawn_instance_layout.py` | SYNTHETIC-ONLY layout (r3). Its record builders/validators are **called** here (they carry no status policy). | untouched |
| `research/g9/wp8b/wp8b_non_synthetic_preparation.py` | The reviewed non-synthetic preparation path. `validate_provenance_record` is the **only** gate through which a prepared record passes here. | untouched |

Both accepted packages' fixtures still pass in this copy after the build:
WP8d `680 checks` PASS, WP8b unchanged.

---

## 1. Why a parallel module and not an edit

Owner default 5 (*"a reviewed generation-artifact layout, with its parser/validator
bound before the first draw"*, `research/decisions/GATE_9_WP7_PINNED_DRAFT_AND_WP7B_OWNER_DECISION.md:146-154`)
is satisfied by the synthetic-only WP8d package — which refuses
`non_synthetic_supported is True` outright and is deliberately fail-closed.

That fail-closed guarantee **is the property the accepted package exists to have**, so
widening its accepted status set would destroy it. WP8d's own notes reach the same
conclusion independently and name the form explicitly
(`WP8D_DRAWN_INSTANCE_LAYOUT_NOTES.md:361-392`):

> the natural form is a **new status string plus a `/v3` index schema in a new parallel
> layout module**, not an edit to this one, so the synthetic-only package keeps its
> fail-closed guarantee.

So: a sibling. New schemas, new index name, new status vocabulary — nothing borrowed.

## 2. The one thing that changes semantically

WP8d binds the prepared record to the generation record by its **CLAIMED** identity — a
hash-and-agreement check between two files.

This module binds it by **CONTENT**. `INSTANCE_ENVELOPE.json` is a member of the prepared
sidecar; the reader re-parses it from the bound bytes; the resulting `SyntheticInstance`
is handed to WP8b, which recomputes the instance digest, the named identity, the approval's
hash binding and every numeric result through the same frozen WP5b functions the
preparation used (`wp8b_non_synthetic_preparation.py:1330-1467`).

Consequently, on **both** write and read, a prepared record is accepted only by:

```python
_wp8b.validate_provenance_record(record, instance_from_bound_bytes,
                                 require_production=<path constant>)
```

`require_production` is a constant of the code path, never a caller argument. Concretely:

- no public function in this module has a `production` or `require_production` parameter
  (asserted by signature inspection in the fixture);
- `require_production` exists only on the **private** helper `_validate_prepared`, whose
  two call sites are the two public paths, each passing a module constant;
- re-sealing a record cannot help, because WP8b's anchor recomputes every factual claim
  from the instance — not from the record's own hashes.

## 3. Two layouts, one code path

`require_production` is selected at the **same two boundaries** WP8b separates them on:

1. **a marker member.** The production prepared sidecar holds exactly
   `{PREPARED.json, INSTANCE_ENVELOPE.json, MANIFEST.json}`. The stand-in sidecar holds
   exactly those **plus** `STANDIN.json`. The exact-directory check therefore forbids a
   stand-in marker in a production layout and *requires* one in a stand-in layout — in both
   directions.
2. **the index's `layout_kind`,** cross-bound to the record's own WP8b status and
   `production` flag, in both directions.

| public path | layout kind | WP8b flag |
|---|---|---|
| `write_instance` / `verify_instance` | `production_instance` | `require_production=True` |
| `write_standin_instance` / `verify_standin_instance` | `non_production_standin` | `require_production=False` |
| `resume_standin` / `verify_all_standin_slots` | `non_production_standin` | `require_production=False` |

The stand-in path can never be read as production: the reader is chosen by a module
constant; a stand-in directory's index says `non_production_standin`; its `STANDIN.json`
says so in a member of its own; and if an attacker re-seals the index to claim production,
WP8b is asked with `require_production=True` and refuses the record's own status.

## 4. What is bound across write and read

The index additionally carries, and the reader compares against the **file it actually
read** (not against the index's own arithmetic):

- `generation_id` — the generation record's own content hash
- `prepared_id` — the WP8b record's own content hash
- the envelope's bytes hash **and** content hash
- the prepared record's status and `production` flag
- both sidecar manifests (bytes and content hash), the retained-attempt ledger, the
  implementation record, and the `mu_new` / `Sigma_new` digests

Identity, generation, prepared record, manifests, slot/attempt and accepted status are
cross-bound in **both** directions between the index, the generation record, the prepared
record, the envelope and the directory name.

Preserved from WP8d/WP5: exact-directory membership, canonical-JSON round-tripping,
write-once manifest, staging-and-rename promotion, per-file and per-directory fsync, and
refusal to merge into or overwrite an existing slot.

Refused: traversal and symlinks, a mismatched generation or prepared id, a swapped slot, a
re-sealed tamper, an unknown status, and an interrupted promotion.

## 5. What this package does **NOT** establish

- **It is unarmed.** The production path calls WP8b with `require_production=True`, and
  WP8b refuses while the owner has pinned no production release decision record (R6,
  `wp8b_non_synthetic_preparation.py:894-932`). Today a production write or read **cannot
  succeed**, and the refusal is WP8b's own typed `ProductionReleaseNotPinned`. No second,
  weaker switch was added.
- **No draw, no seed, no beacon, no scientific step, no network, no credentials.** The
  return-matrix bytes and the recorded `mu_new`/`Sigma_new` encodings are caller inputs
  (WP8d takes them for the same reason). The module names, binds, rehashes and refuses. It
  imports no NumPy.
- **No fabricated approval.** The adapter never constructs an owner approval record and
  never writes WP8b's production release decision record. The only accepting path
  exercisable today is WP8b's own non-production fixture branch, whose record announces
  `prepared_non_production_standin` in its own status.
- **Origin is not in any file.** A fully re-sealed, self-consistent trio is still refused
  by WP8b's approval binding, one-use nonce and R6 pin — none of which live in this
  layout. What binds a layout to a real draw is the approval and the pin, not this
  directory.

## 6. Offline rehearsal — what was demonstrated

All of it is NON-PRODUCTION. The only instance prepared is a conspicuously labelled
stand-in (`NONPROD-STANDIN-…-NON-PRODUCTION`); WP8b's fixture branch refuses any other id,
so the accepting path reachable offline is WP8b's own and no other.

```
WRITE   verdict=written  kind=non_production_standin  armed=False  slot=stage2_01
  members            ['generation', 'instance', 'meta']
  prepared members   ['INSTANCE_ENVELOPE.json', 'MANIFEST.json', 'PREPARED.json', 'STANDIN.json']
  index_content_sha256  b4df516fe082fc1b4e550b3ba54ce8ace9317bb1198ba8258e88c0836d0e60ad
  prepared_id           5b414496594778898dcfa121c0168ced041cee3bbb41dc934ca4882364a2501f
  generation_id         f9bbfa835abd489b359128d4d3c36635ab701bf123e2d72f100a42eb9ed39e68
READ    verdict=verified  instance=NONPROD-STANDIN-0001-NON-PRODUCTION
  reverify deterministic: True
RESUME  verdict=verified  resumed=True  writable=False
RESUME  free slot: absent  writable=True
SWEEP   slots=['stage2_01']  count=1
```

**Negative control — the prior synthetic-only layout refuses a non-synthetic claim:**

```
wp8d._require_not_non_synthetic(True)   -> LayoutError: refusing a prepared record that
                                          claims non-synthetic support: the reviewed WP5b
                                          non-synthetic release path does not exist
wp8d._require_status('prepared_non_production_standin')
                                       -> LayoutError: status is not an accepted
                                          prepared-record status
wp8d._require_status('prepared_non_synthetic_authorized')
                                       -> LayoutError: status is not an accepted
                                          prepared-record status
```

**The production path is unarmed, and refuses:**

```
PRODUCTION_RELEASE_PINNED = False
  decision_record = research/decisions/GATE_9_WP8B_NON_SYNTHETIC_PREPARATION_RELEASE.json
adapter _validate_prepared(require_production=True)
                    -> ProductionLayoutError: ... refused by the reviewed WP8b provenance
                       validator (require_production=True)
verify_instance(1) on a stand-in directory
                    -> ProductionLayoutError: prepared sidecar contents differ from the
                       canonical layout
write_instance(...) with a stand-in record
                    -> refused BEFORE any byte is written
```

## 7. Broken variants — each refused for its own reason

| variant | refused by | needle |
|---|---|---|
| **bypass WP8b** (adapter's validator stubbed to only re-sign; tampered `f_star` written) | WP8b anchor on read | `require_production=False` |
| **read-only assertion** (index `production` flipped to `True` and re-sealed) | read-side cross-check vs the record | `production flag disagrees` |
| **slot swap** (slot 1's directory moved to slot 2) | generation record's own slot | `different slot than the instance directory` |
| **resealed provenance** ×4 (instance digest / `f_star` / approval binding / status claim — each re-signed AND manifests+index re-sealed) | WP8b anchor | `require_production=False` |
| **wrong instance** (envelope bytes swapped for another stand-in's) | WP8b anchor | refusal |
| **missing fsync** (`_fsync_dir` raising after promotion) | rollback leaves neither slot nor staging | refusal + rollback |
| **interrupted promotion** (stray staging directory) | resume + whole-root sweep | `interrupted staging directory` |
| **traversal** (`stage2_01/../stage2_01`, `..`) | slot-name guard | `slot name is not one of` |
| **symlink** (prepared record replaced by a symlink) | real-file guard | `PREPARED.json` |
| **extra member** (`STRAY.json`) | exact-directory check | `differ from the canonical layout` |

Each tamper deliberately **re-seals** — record, sidecar manifest and index — so the
directory is internally self-consistent and the *only* authority left is WP8b's
recomputation from the bound instance bytes. Without re-sealing, every tamper would also
break a stale hash and the anchor would be untested.

The bypass probe also runs an untampered **control** in the same check, so its refusal is
provably caused by the tamper and not by the probe's own setup.

## 8. One real defect the fixtures found and fixed

`_layout.slot_number()` raises WP8d's `LayoutError`, and three call sites in
`wp8d_production_layout.py` (`_slot_number`, `resume_standin`, `verify_all_standin_slots`)
called it directly. A traversal or unknown slot name therefore escaped as `LayoutError`
rather than this module's own `ProductionLayoutError` — so a caller writing the documented
`except ProductionLayoutError:` contract would **not** catch it, and the fail-closed
guarantee was silently incomplete. Fixed by routing all three through
`_slot_number`/`_as_production`. The fixture now pins it.

## 9. Fixture design notes that are load-bearing

- `require` is the reporter, so it cannot be trusted alone. `_observed` reports an outcome
  as a **value** (exception type and message) and the structural checks assert with the
  interpreter's own `assert` — a channel this file does not define.
- `main` requires an exact assertion total (**114**) through **three independent channels**
  (`raise` / `assert` / `require`), so dropping any single assertion fails the run rather
  than hiding behind its neighbours.
- Dispatch is by **signature**, not a hand-maintained name list: a check needing
  `(tmp, nonce_root)` and a standalone check are discovered automatically, and
  `_undispatched_checks` re-proves coverage. (This caught a genuinely undispatched check
  during the build.)
- `refused()` requires an *exact* exception type and an optional message needle, so a
  wrong-reason refusal is a failure — that is what makes these negative probes rather than
  smoke tests.
- 55 check functions, floor pinned at 20 — the file's own count, not a number copied from
  a larger sibling package. (44 before continuation `wp8dprod.eqfix` added the fault-injection
  probes described in §10.1.)
- `check_pinned_reviewed_bytes` deliberately pins **no digest** for the reviewed packages.
  Asserting a hash this build cannot honestly establish would be a fabricated claim; what
  is asserted is the observable property — both modules are still callable and still refuse
  exactly what they refused before this build existed.

Runs green under both `python3 -B` and `python3 -B -O`: **424 assertions, 54 dispatch
groups, 55 defined checks**, no bytecode written.

## 10. Mutation gate

`g9_guard_sweep.py` v1.1, full fixture, **12 workers**, `--nice 10`, on the
isolated copy only.

**This section was REWRITTEN by continuation `wp8dprod.eqfix`; see §10.1.**

Final result: **`SWEEP: PASS`** — 493 sites, **477 killed, 0 survivors,
0 errors, 0 stale**, 16 accepted equivalents.

```
  shape  sites              KILLED             TIMEOUT            SURVIVED               ERROR EQUIVALENT-ACCEPTED               STALE
  S1       138                 127                   0                   0                   0                  11                   0
  S2        54                  53                   0                   0                   0                   1                   0
  S3        20                  20                   0                   0                   0                   0                   0
  S4       130                 128                   0                   0                   0                   2                   0
  S5       151                 149                   0                   0                   0                   2                   0
  ALL      493                 477                   0                   0                   0                  16                   0
```

Evidence: `logs/wp8dprod.eqfix.sweep.r2.{txt,json}`,
`logs/wp8dprod.eqfix.equivalents.json`. The earlier rounds are preserved, not
deleted.

### The 194 → 0 trajectory was mostly FIXTURE work, not exemptions

The first sweep found **194 survivors**. Rather than exempting them, the fixture was
extended until only genuinely-unreachable or genuinely-redundant statements remained.
Every round is preserved in the `.rN` files so the progression is auditable.

Two things are worth recording because they *changed how the code was written*:

1. **A real defect, found by the fixture.** `_layout.slot_number()` raises WP8d's
   `LayoutError`, and three call sites called it directly. A traversal or unknown slot
   name therefore escaped as `LayoutError` rather than this module's own
   `ProductionLayoutError`, so a caller writing the documented `except
   ProductionLayoutError:` contract would **not** have caught it — the fail-closed
   guarantee was silently incomplete. Fixed by routing all three through
   `_slot_number`/`_as_production`; the fixture now pins it.

2. **The WP8d fsync precedent, applied rather than inherited.** WP8d's first
   equivalents file carried two post-promotion `fsync` entries justified as
   "durability, not content, therefore unobservable". That reasoning was **wrong on
   the evidence** and was retired (see
   `logs/wp8d.r3.sweep.layout.equivalents.RETIREMENT.md`): a `_fsync_dir` **recorder**
   makes those calls observable, asserting both fire exactly once in WP5's order
   (destination, then parent) and that a failure of either refuses the write and
   leaves the slot absent. `check_fsync_calls_are_observable` applies that same
   discipline here, so **no fsync site is exempted**.

### The 26 accepted equivalents — REJECTED by continuation `wp8dprod.eqfix`

The original text here read:

> Each was justified by a **direct probe**, never inherited […] A **test gap is
> never recorded as an equivalence** — that is precisely the suppression the
> WP8d RETIREMENT record warns against, and it is why 194 survivors became 26
> verified equivalents rather than 194 exemptions.

**That claim was false, and this continuation exists because of it.** All 26
justifications were re-derived against the module rather than inherited, and
**eight were wrong**. See §10.1 for the full adjudication; the short form is
that they were claims about *what the fixture had not constructed*, not
properties of the module, and eight named genuinely reachable guards as
`UNPROVABLE-IN-ONE-RUN`, `UNREACHABLE` or `SHADOWED`.

The category table above is retained only as a record of what was claimed. The
categories that do not survive scrutiny are `UNPROVABLE-IN-ONE-RUN` (all three
refuted), and `SHADOWED` as applied to `S3:806`, `S3:853`, `S3:861`, `S2:865`,
`S3:710`, `S2:607`, `S2:750` and `S2:1046`.

## 10.1 The re-adjudication

Sixteen equivalents remain, each with a **verified** justification recorded in
`logs/wp8dprod.eqfix.equivalents.json`:

| category | n | what it means |
|---|---|---|
| `PRIVATE BOUNDARY` | 2 | `S1:743`, `S1:1095` — the layout-kind guard in each private helper, whose only two call sites each pass a module constant. No caller-controlled input exists. |
| `UNARMED PRODUCTION PATH` | 6 | The `1152`/`1154` branch and its S4/S5 mutations. Reachable only once the R6 owner gate closes; WP8b refuses every `require_production=True` validation until then. The stand-in mirror is tested today. |
| `DUPLICATE PREDICATE` | 2 | `S1:1147`, `S1:1149` — the validator invariant at `wp8d_production_layout.py:665` forces the index's two production flags equal, so the reader's two comparisons are the same predicate with the same message. The reaching input **is** driven and asserted by the fixture. |
| `WP8B DIGEST ANCHOR` | 1 | `S1:1126` — the envelope's id cannot be moved without breaking the instance digest WP8b recomputes. |
| `SEED-BOUND UPSTREAM` | 1 | `S1:1177` — the attempt number is bound to U-08 seed commitments; probed by raising the attempt in both files, and the seed check fires first. |
| `TAUTOLOGY UNDER INVARIANTS` | 1 | `S1:1181` — both sides are provably `0` for every reachable input (the index validator forces the count to `0`; WP8d forces an accepted ledger to carry no codes). |
| `MUTUALLY SHADOWING` | 2 | `S1:1157`, `S1:1159` — WP8b accepts the paired production record and refuses either field alone, so the pair is the only reachable input and both statements fire together. |
| `FAIL-FAST DUPLICATE` | 1 | `S2:1302` — re-derived by the very next statement. **Its sibling `S2:1270` is NOT a duplicate and is now killed.** |

Two of these deserve emphasis because they are *stronger* than the prior
reasoning rather than weaker:

* **`S1:1181` is a tautology, not merely "shadowed".** The prior justification
  only covered the index side. The generation side is pinned too, so the
  equality is `0 == 0` on every reachable input.
* **`S2:1270` was wrongly bundled with `S2:1302`.** In `verify_all_standin_slots`
  the loop's check is genuinely repeated by the per-entry verify that follows.
  In `resume_standin` it is **not**, because the function returns early when the
  requested slot is absent. With 1270 deleted, resume reports a slot as
  free-to-write while a stray directory sits in the instance root — a fail-open.
  It is now killed by `check_resume_refuses_a_stray_non_slot_directory`.

### The eight refuted entries

| site | prior label | what the evidence actually showed |
|---|---|---|
| `S3:806` | UNPROVABLE-IN-ONE-RUN | `staging.mkdir` is one ordinary call; failing exactly that call is a single injection. |
| `S3:853` | UNPROVABLE-IN-ONE-RUN | The bare `raise` is load-bearing: mutated to `None`, the write falls through to the durability block and reports a **misleading fsync error** for a write that never promoted. |
| `S3:861` | UNPROVABLE-IN-ONE-RUN | Promotion and rollback are two *distinct* calls; failing only the second is one injection. |
| `S2:865` | SHADOWED | **Backwards.** 865 is the cleanup after a rollback that **succeeded**; the 861 branch raises and never reaches it. |
| `S3:710` | SHADOWED | Reachable only by a **dangling** symlink — and see the fixture defect below. |
| `S1:348` | UNREACHABLE | `SyntheticInstance` is a plain **dataclass**: `instance_id: str` is an annotation, not a runtime check. A real instance with `instance_id=7` passes the `isinstance` guard and 348 fires. |
| `S2:607` | SHADOWED | Malforming only the *nested* copy reaches the shape guard. |
| `S2:750`, `S2:1046` | SHADOWED | WP8b with `require_production=False` **accepts** a record whose status and flag are both production, so these call sites are the only catch. |

### Two were FIXTURE DEFECTS, not missing coverage

A probe that satisfies the mutant is worse than no probe: it converts a live
defect into a recorded exemption.

* **`S3:710`** — the old probe named its own scratch path `symlink-destination`
  and asserted only `needle="symlink"`. With the raise deleted, `os.rename` then
  failed with a message that **also** contained the substring "symlink" — because
  the fixture had put the word in its own filename — so the mutant satisfied the
  same assertion. The corrected probe uses neutral scratch names and asserts the
  link is genuinely dangling.
* **`S3:853`** — the old probe asserted only the exception **type**, which cannot
  see a mutant that reports a *different* error. The observable is the
  **message**: the refusal must carry the original cause. A first attempt at this
  check asserted the type and still let the mutant through; the fall-through
  diagnosis is preserved in `scratch/wp8dprod.eqfix/probe_why853_still_survives.py`.

### A methodological note worth keeping

An intermediate sweep appeared to report five sites as survivors that the very
same fixture kills when swept individually, and none of them at any worker count.
The cause was **not** a fixture defect and **not** concurrency: the sweep had
been launched *before* a documentation edit to the fixture and had snapshotted
the older file. **A mutation sweep must be run against a frozen fixture**, and
the fixture's SHA-256 should be recorded beside the sweep result so the two can
be checked against each other. Both are recorded below.

### Fixture and hashes for this round

| artifact | SHA-256 |
|---|---|
| `wp8d_production_layout.py` (**unchanged**) | `4a37a3c5c9cadb13d77eb576111da5e16260060aaa9d7691b3bd986b422915b5` |
| `verify_wp8d_production_layout_fixtures.py` | `9c1e0e99798be2f24dc649cc92d9d434217fe5babee5a9f874084bf79130672c` |
| `wp8d_drawn_instance_layout.py` (reviewed, untouched) | `71a99d7d8ec9fb7e0c27649650a2692a0d425b1705ac78820f1de4f3bbc5c663` |
| `wp8b_non_synthetic_preparation.py` (reviewed, untouched) | `de5aff98696df84fe1ad5b79cb5936b56c0f8c28fafca27df4ad5890134cb13e` |

The **production module was not edited** — the whole correction is fixture work,
which is what lead asked for. `EXPECTED_ASSERTIONS` moved 380 → 423 (assertions
added by the new probes, less one removed with the defective 710 probe), giving
`424 assertions / 54 dispatch groups / 55 defined checks`, green under both
`python3 -B` and `python3 -B -O`.

## 11. Limits

- This package is **build/validation only**. It cannot be armed until the later owner gates
  (the R6 production release decision record, and a real draw/write approval) close.
- Offline rehearsal proves the **layout** binding and refusal properties. It does not and
  cannot prove anything about a real draw, because no draw material exists here.
- The moment and return-matrix inputs in the fixtures are conspicuously-labelled
  placeholder constants, **not** computed or scientific results.
- The one-use nonce registry is exercised inside a per-run sandbox root, never in the
  project tree.
- No owner approval record, accepted release, or production data was fabricated, and none
  exists in this package.