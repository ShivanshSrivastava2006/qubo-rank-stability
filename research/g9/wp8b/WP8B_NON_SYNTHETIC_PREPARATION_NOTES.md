# WP8b — NON-SYNTHETIC INSTANCE PREPARATION RELEASE (build notes)

**Status:** offline build, reviewed against the mutation gate. Nothing here draws an
instance, runs a generator, or performs a scientific write. This package authorizes
BUILDING AND VALIDATING only; the draw and the scientific write remain separate owner
gates.

**Scope:** the "Real-instance preparation" default from the WP8 design note — a
separately reviewed, separately versioned non-synthetic WP5b release path, with its own
identity hash, used only after an owner draw/write approval. This is exactly OWNER
QUESTION 2 of `research/g9/kaggle_wp8/WP8_PRODUCTION_BUNDLE_DESIGN.md:129-136` and
approved default 2 at
`research/decisions/GATE_9_WP7_PINNED_DRAFT_AND_WP7B_OWNER_DECISION.md:146-155`.

## Files (new; nothing else was touched)

| File | Lines | Role |
| --- | --- | --- |
| `research/g9/wp8b/wp8b_non_synthetic_preparation.py` | 1066 | the non-synthetic release path |
| `research/g9/wp8b/verify_wp8b_non_synthetic_preparation_fixtures.py` | 1543 | the full refusal + acceptance fixture |
| `research/g9/wp8b/WP8B_NON_SYNTHETIC_PREPARATION_NOTES.md` | this file | the interface for the other WP8 packages |

## What was NOT modified

`research/g9/stage2_instance_preparation.py` (WP5b) is byte-identical to the reference
tree. WP5b stays synthetic-only: `validate_envelope` still refuses every mark that is
not the bool `True` (`:316-317`), `authorize_non_synthetic` still always raises
(`:437-450`), and `UNREACHABLE_APPROVAL` still declares it cannot be constructed
(`:403-409`). This package imports WP5b and reuses its frozen numerics; it never
patches, subclasses-for-circumvention, or edits it. The fixture asserts WP5b is
untouched by re-running WP5b's own refusals.

## Why a new path was needed (the design-note citations)

WP5b is deliberately closed to every real instance at three separate points:

- `stage2_instance_preparation.py:284-317` — the ONE gate refusing a non-synthetic
  envelope, raising `NonSyntheticInstanceRefused`;
- `:400-466` — `authorize_non_synthetic` always raises; the authorization-bearing name
  `NON_SYNTHETIC_AUTHORIZATION_FIELD` is a name that does not yet exist;
- `:751-821` — the provenance record is stamped `prepared_synthetic_only` /
  `non_synthetic_supported: False`.

## The interface (for the other WP8 packages)

```python
from research.g9.wp8b import wp8b_non_synthetic_preparation as wp8b

instance_digest = wp8b.instance_content_sha256(instance)   # = WP5b's own digest
record = wp8b.prepare_non_synthetic(instance, approval, consume_dir=None, now=None)
wp8b.validate_provenance_record(record, instance, require_production=True)
```

- `PROVENANCE_SCHEMA` — `decisions_os/g9_wp8b_non_synthetic_instance_preparation/v1`.
  Deliberately NOT WP5b's schema; the two records are disjoint in both directions.
- `NON_SYNTHETIC_IDENTITY_HASH` — this path's own versioned identity hash, computed at
  import from the live source digests. **Bind this exact value.** It changes if any of
  the 14 `SOURCE_FILES` changes (WP5b, this module, the G3 resolver, the G4 modules,
  the G6 ledgers) or if the release pin constants change.
- The approval record schema is `APPROVAL_SCHEMA`, exact keys `APPROVAL_KEYS`, exact
  statement `APPROVAL_STATEMENT`, status `owner_approved`, scope
  `stage2_instance_draw_and_write`, label `non_synthetic`. The approval's
  `instance_id` must name **exactly** the instance being prepared (R3.2).
- `prepare_non_synthetic(..., consume_dir=...)` — `consume_dir` is now **optional on
  every path** and is only an audit mirror. The one-use state always lives in the
  module-fixed `NONCE_REGISTRY_DIR`; omitting the argument does not skip consumption.
- Downstream packages MUST call `validate_provenance_record(record, instance)` — the
  `instance` argument is **required** (see D4) — and should use the default
  `require_production=True`; a non-production stand-in is refused there.
- `pinned_byte_identity_report()` — verifies the 29 reviewed dependencies and the 12
  v1 section-A release files against their DECLARED in-tree digests. Useful for a
  consumer that wants the same pinned-set guarantee this package claims.

**Important for consumers:** `status` and `production` are self-asserted fields and a
record's `content_sha256` is an unauthenticated SHA-256 over public fields, so anyone
can recompute a record that claims production. The production consumer therefore also
requires the R6 pin (below). Passing the `instance` to the validator is what makes the
record's *numbers* trustworthy: they are re-derived from the instance through the same
frozen WP5b functions, so an edited-and-re-signed record is refused rather than
believed. A consumer that has the drawn instance should always pass it.

## The six refusals (all fixture-reached, all killed by the sweep)

| # | Refusal | Class |
| --- | --- | --- |
| R1 | no / wrong-shaped / wrong-status / wrong-scope / wrong-label / expired approval | `ApprovalRequired` |
| R2 | approval does not name the instance's exact content SHA-256 | `ApprovalHashBindingRefused` |
| R3 | synthetic-flag confusion (envelope not `synthetic is False`; approval labelled `synthetic`) | `SyntheticFlagConfusionRefused` |
| R3.2 | approval does not name exactly the instance being prepared (wrong id, or a non-str id) | `SyntheticFlagConfusionRefused` |
| R4 | replay of a consumed one-use approval — including via a different or omitted directory | `ApprovalReplayRefused` |
| R5 | real preregistered draw material in an approval field | `RealMaterialRefused` |
| R6 | the production path while no owner decision record is pinned | `ProductionReleaseNotPinned` |

### R6 — the production pin (the reason no real instance can be prepared today)

The production path is refused unless `PRODUCTION_RELEASE_PINNED` is True AND the
pinned decision record `research/decisions/GATE_9_WP8B_NON_SYNTHETIC_PREPARATION_RELEASE.json`
exists with SHA-256 `PRODUCTION_RELEASE_DECISION_SHA256` (currently `"f"*64`, a
deliberately impossible digest). Neither holds today, so **every** owner-scope approval
is refused before any nonce is consumed and before any scientific arithmetic runs.
This is the direct analogue of WP5b's deliberately-unreachable authorization
(`stage2_instance_preparation.py:421-426`), made explicit and testable rather than
vacuous. Flipping the flag alone is not enough — the record must also hash as pinned.

## The synthetic path (fixtures only)

Fixtures use a conspicuously NON-PRODUCTION stand-in whose id starts with
`NONPROD-STANDIN` and contains `NON-PRODUCTION`. The ONE accepting path
(`check_fixture_only_approval`) is reachable only by naming `FIXTURE_CONTEXT_TOKEN`
**and** using a stand-in id **and** the fixture scope. Records from it are stamped
`prepared_non_production_standin`, carry `production: false`, and are refused by the
default production consumer. No approval produced anywhere in this repository takes
that branch except the fixture's.

No real generator draw, no production seed, no beacon, no network, no credentials, no
GPU. Real seed/beacon markers are refused (R5).

## OWNER QUESTION (genuine, with a safe default)

**Q: What exactly is the owner decision record that flips the R6 pin, and who signs it?**

WP8 OWNER QUESTION 1 (the accepted production identity) is still open: the existing WP1
validator *requires* `DRAFT_UNQUALIFIED` and `authorization=NONE`
(`stage2_production_identity.py:389-445`), and no accepted WP1 production release
exists. R6 deliberately refuses until a real decision record is pinned, because this
package cannot truthfully prepare a production instance before the identity question is
settled — the design note is explicit that a production receipt today "would have to
bypass a deliberate refusal or invent an input/authority format"
(`WP8_PRODUCTION_BUNDLE_DESIGN.md:166-172`).

**Safe default (recommended, and what this build does):** leave `PRODUCTION_RELEASE_PINNED`
`False` and `PRODUCTION_RELEASE_DECISION_SHA256 = "f"*64`. The production path stays
refused; only the non-production fixture branch accepts. To release, the owner writes the
decision record (naming the accepted WP1 production identity and the WP8b identity hash),
its SHA-256 is recorded in the two constants, and `PRODUCTION_RELEASE_PINNED` is set to
True in a new reviewed version — a deliberate, reviewable act, never a silent flag flip.

## Gate evidence (round 3, final)

- Fixtures pass under `python3 -B`, `python3 -B -O` **and** `python3 -B -OO`.
- `g9_guard_sweep.py` v1.1, `--chunk-seconds 36000`, 4 workers, run on **both**
  new modules:

  | module | sites | killed | equivalents | survivors | stale | verdict |
  | --- | --- | --- | --- | --- | --- | --- |
  | `wp8b_non_synthetic_preparation.py` (the release module under test) | 291 | **291** | 0 | **0** | 0 | **SWEEP: PASS** |
  | `verify_wp8b_non_synthetic_preparation_fixtures.py` (the fixture) | 602 | 589 | 13 | **0** | 0 | **SWEEP: PASS** |

  The release module is **byte-identical to round 2** (`de5aff98…`), so its
  291/291 result is carried forward rather than re-run; the sweep was re-run in
  full on the changed fixture only.  The fixture's equivalents are at
  `logs/wp8b.sweep.verify_wp8b_non_synthetic_preparation_fixtures.equivalents.json`.

  Native output: `logs/wp8b.sweep.wp8b_non_synthetic_preparation.txt` and
  `logs/wp8b.sweep.verify_wp8b_non_synthetic_preparation_fixtures.txt`, with the
  fixture's equivalents at
  `logs/wp8b.sweep.verify_wp8b_non_synthetic_preparation_fixtures.equivalents.json`.
- The **release module carries no equivalents at all** — every one of its 291
  guards is killed by a real fixture observation.
- Zero `.pyc` / `__pycache__` anywhere in the copy.
- The one-use nonce registry is written only into per-run sandboxes; it is never
  created in the project tree, which the fixture asserts.
- Nothing outside `research/g9/wp8b/` was modified; the three files below are the
  only changes relative to the state at the start of round 2, and no file was
  added or removed.
- WP5b (`research/g9/stage2_instance_preparation.py`) is byte-identical to the
  reference tree.
- The 29 reviewed dependencies match their declared digests and the reviewed
  table matches WP7b's own `ANCHOR`; the 12 v1 section-A release files match their
  declared digests. Zero mismatches.
- Every round-1 attack reproduced verbatim from `logs/wp8b.r1.vout` is refused
  (replay in a different directory, approval naming another identity, an
  approval whose id is an `int`, and all five re-signed record tampers).

### Files (sha256, lines)

| sha256 | lines | file | vs round 2 |
| --- | --- | --- | --- |
| `de5aff98696df84fe1ad5b79cb5936b56c0f8c28fafca27df4ad5890134cb13e` | 1666 | `research/g9/wp8b/wp8b_non_synthetic_preparation.py` | **unchanged** |
| `acc3ffb2f16d1a08ab241f16074a347c812ebbc55a0f8cdf0351e73fd9f15b00` | 2964 | `research/g9/wp8b/verify_wp8b_non_synthetic_preparation_fixtures.py` | changed |
| this file | 616 | `research/g9/wp8b/WP8B_NON_SYNTHETIC_PREPARATION_NOTES.md` | changed |

The release module — the thing this package exists to ship — was **not
touched**. Every change in round 3 is to the fixture and to this file.


## ROUND 2 — what the round-1 validator rejected, and what changed

The round-1 validator returned `VERDICT: FAIL` on six points. All six are fixed
here; each fix is carried by a named regression in the fixture so it cannot
silently regress. The fixture regressions are named after the defect, so a reader
can match any line to `logs/wp8b.r1.vout`.

### D1 — one-use was caller-controlled (`r2_d1_*`)

Round 1 kept the one-use marker in a **caller-supplied** `consume_dir`, so
consuming an approval in `one` and again in `two` was ACCEPTED. Round 1's own
fixture asserted that bypass as intended behaviour ("a fresh consume dir admits
the same approval once"), so code and fixture agreed and were both wrong.
Separately, consumption ran only `if consume_dir is not None`, so a caller that
passed no directory recorded **no one-use state at all**.

Now: the ledger is a module-fixed registry (`NONCE_REGISTRY_DIR`), consumption is
**unconditional**, and the marker is keyed on the **approval's own canonical
bytes** (`_approval_ledger_key`), not on a nonce string or a path. `consume_dir`
survives only as an optional audit mirror. A registry that cannot be written is a
typed refusal — fail-closed, because a preparation that cannot record its one-use
state has not established one-use.

### D2 — approval identity was unbound (`r2_d2_*`)

Round 1 declared the approval's `instance_id` check "subsumed" by the R2 digest
binding. That argument runs one way only: the digest binds the **instance's** id,
while the approval is a separate document free to assert a **different** one. The
validator supplied an approval naming `STAGE2-OTHER-IDENTITY` — and separately the
integer `7` — over a *correct* digest, and both were ACCEPTED.

Now it is its own guard (`_check_approval_names_this_instance`), type-exact and
string-exact, running after R2 so the two refusals stay distinguishable. Note the
second-order lesson, recorded in the code: gating the *call* on
`type(x) is str` skips the guard for exactly the non-string values it exists to
refuse. The type test must live **inside** the guard.

### D3 — the source closure was incomplete (`r2_d3_*`)

Round 1 bound four files and omitted `src/g4/generate_ledger.py`, which the
reused WP5b path imports and calls (`stage2_instance_preparation.py:107`). The
validator edited that file in a scratch probe and the identity hash did not move.

`SOURCE_FILES` is now the full in-repo import closure of the three frozen numeric
sources (14 entries). The fixture proves the specific omission is closed *and*
proves the closure is live, by editing a bound file in a throwaway copy of the
tree and requiring the identity hash to change.

### D4 — re-signed record tampering was accepted (`r2_d4_*`)

Every hash the round-1 validator checked — `content_sha256`, the identity hash,
the identity payload hash — is a function of the record's **own public fields**.
Editing a field and recomputing `content_sha256` satisfies all three. The
validator's five tampers (instance digest, approval `instance_id`, approval
digest, `f_star`, a source hash with the identity payload recomputed to match)
were **all ACCEPTED**. Self-consistency is necessary and not sufficient; a
re-signed record is internally perfect by construction.

`validate_provenance_record` now takes the **instance** the record claims to
describe and re-derives the digest, the identity, the asset count and every
numeric result (`f_star`, `max_f_over_F`, `argmax_f_over_F`, `Lambda_ref`,
`delta_full`, `X_star`, `X_star_size`) from it through the same frozen WP5b
functions. It also anchors the source map to the live tree. This is deliberately
the consumer's job: only a caller holding the drawn instance can supply it, and
requiring it is what makes the check meaningful rather than circular.

> **Interface change (breaking for callers).** `validate_provenance_record`
> gained a positional `instance` parameter. Downstream WP8 packages must pass the
> instance whose record they are validating.

### D5 — the fixture failed its own sweep

Round 1's fixture left **231 survivors** on its own full sweep; `--only`
confirmed that deleting `check_replay` from `main` survived. A bare call is an S2
site whose mutant is `pass`, invisible when the other checks still pass, and a
guard is only observable when the fixture produces **both** outcomes. The fixture
is rewritten on that rule: checks are dispatched from iterated tables (checked for
duplicates and non-emptiness), conditions are value checks over data that would
really fail, and no check self-attests that it ran.

### D6 — pinned byte identity was unverified (`r2_d6_*`)

Round 1 compared `research/g9/kaggle_wp7b` against the reference tree
`/home/shivansh-srivastava/decisions_os/project` and reported nine differences.

**Those differences are not this package's doing, and must not be "fixed" by
editing pinned files.** This job's copy was snapshotted at 13:42 on 2026-10-01;
the reference tree's WP7b files carry an mtime of 07:42 that morning while this
copy's carry 09:59–11:37. The copy legitimately contains WP7b work the reference
snapshot predates, so a tree-vs-tree diff reports a difference for every pinned
file the reference happens to be behind on and says nothing about whether WP8b
touched anything.

The correct instrument is the one already in the repository: pinned files carry
**declared** digests, so byte-identity is checkable in-tree with no reference
tree at all. `pinned_byte_identity_report()` verifies the 29 reviewed
dependencies against `wp7_reviewed_dependencies.json` — itself checked against
WP7b's own `ANCHOR` constant — and the 12 v1 section-A release files against
WP7's own dependency table, parsed with `ast` so a reformat cannot silently yield
an empty, vacuously-passing set.

### Guards removed rather than kept

Per the reference modules' own discipline, dominated or unreachable guards were
DELETED rather than papered over with contrived tests, and each is commented in
place. From round 1: the `except OSError: if errno == EEXIST` arm (subsumed by
`except FileExistsError`), the duplicated `require_nonzero_lambda_ref` call
(subsumed by `build_ledgers`→`_box_rule` on the same value), the explicit
`record["schema"] == WP5b schema` guard (dominated by the schema guard two
clauses above), the duplicated `_check_hash_binding`, the dead `_require_pin`
twin, and several split type/emptiness pairs whose second clause already covered
the first.

**Round 1 got one of these deletions wrong, and that is worth recording.**
It deleted the separate `_check_flag_confusion` on the reasoning that the
instance-id clause was subsumed by R2 — see D2. A deletion justified by a
one-directional argument is not a deletion, and the round-1 sweep did not catch
it because the guard it removed had no test that could have failed. The
lesson generalises: *a guard deleted on the grounds that another guard dominates
it is only safe when the domination is two-directional and the surviving guard's
test would fail if the deleted one had been load-bearing.*

Round 2 also removed code the fixes made dead: the `errno` and `struct` module
imports and the zero-digest fallback in `_sha_or_zero` (consumption is now
unconditional, so the marker always exists).

### Round-2 sweep survivors, and the test gaps behind them

The first round-2 sweep of the release module left **7 survivors**. None was a
wrong guard; every one was a **test gap** — a guard the fixture could not
observe — and each is now closed. They are recorded because the pattern recurs
and is worth naming:

- `S2 sys.path.insert(0, _ROOT)` survived because the probe interpreter
  *already* had the root on `sys.path`, so the insert was dead code masked by an
  inherited path entry. The probe now **asserts the precondition** (root absent
  before the insert) instead of assuming it.
- Two `raise` drops survived because a **downstream guard refused the same
  input** with a different message. An empty/`None` `instance_id` is both "not
  well formed" (R1) and "names a different instance" (R3.2); a non-str id was
  caught by the R2 binding before the type clause ran. Both are now driven
  **directly** on their own function, so each clause is observable on its own.
  The lesson: *a guard preceded by a broader one needs a direct test, because
  through the public entry the earlier guard is always the one that fires.*
- `S2 _sha(approval["nonce_consumed_marker_sha256"], ...)` survived because the
  only tamper value used was all-zeros, which **is** valid lowercase hex. The
  tamper table now uses a non-hex value, and an `instance.content_sha256` shape
  guard was added so the shape rule is testable separately from the value rule.
- `S5` on the v1 parser's `not isinstance(digest, str)` operand survived because
  the real pinned table only ever holds `str` values, so that operand had no
  input of its own. The parser is now parameterised on its source
  (`_parse_v1_declarations`) and both operands are driven against synthetic
  tables.

That last one generalises the D1 lesson: **a guard whose input domain is
narrower than the code that produces it needs a synthetic input to be testable
at all.** The right response is to give the code a parameter and test both
outcomes, not to delete the guard.

Two rounds of sweep-driven cleanup followed, and the second is the more useful
one to record. A survivor that is a **crash** rather than a wrong answer is
easy to miss, because the fixture may not notice an untyped exception escaping a
helper it only exercised on well-formed input. The last survivor was exactly
that: removing the `isinstance(value_node, ast.Constant)` operand makes the
parser read `.value` off a `BinOp` and raise a bare `AttributeError` — which
every existing case either never triggered or swallowed. The distinguishing test
needed a table with **one valid literal row and one non-literal row in the same
dict**, so the mutant crashes instead of quietly returning the same result. Two
earlier attempts at that test passed for the wrong reason: a `'h'*64` digest is
not hex, so it was being excluded by the hex filter and never reached the
constant filter at all. The test is now explicit about that.

The same "each half needs its own input" rule was applied to the
`len(digest) == 64 and all(c in hex)` filter: a 64-char non-hex string exercises
only the hex half, and a 63-char hex string only the length half, so both are
pinned separately.

### One guard the sweep correctly told us to delete

The pinned-identity report originally hashed the 12 v1 section-A release files
in a second, separate loop. The sweep proved that loop unkillable, and the reason
is a fact about the repository rather than a test gap: **the 12 v1 files are a
strict subset of the 29 reviewed dependencies, with byte-identical declared
digests.** A second hash loop over them can therefore never fire, because the
29-entry loop always refuses first.

Keeping it would have been a guard that exists only to look thorough — the
"separate" check that is actually a restatement. It was replaced with the check
that is genuinely additional and genuinely reachable: the 12 v1 declarations
read from WP7's own table are **cross-checked against the reviewed table**, so
the two independent declarations of the same files must agree. That arm does
fire under test (perturbing WP7's table in a sandbox tree), and it would catch a
real inconsistency that a second hashing loop could never notice.

## What the fixture's own sweep is, and is not, measuring

Worth stating plainly, because the round-1 verdict treated the fixture's sweep
as a defect in the same way as the module's.

**The module under test is the gate.** `g9_guard_sweep.py` mutates one module
and asks whether the fixture *observes* the change. That is the property the gate
exists to establish, and this package's release module passes it at **291/291,
0 survivors, 0 equivalents**.

**The fixture is the instrument, not the subject.** Sweeping the fixture mutates
the *test*, and asks whether the test still detects things. That is a different
and much weaker question, and it has a known floor: any assertion whose
neighbours do not depend on it is unkillable, because deleting it simply leaves
a test suite with one fewer assertion and everything else still passing. The
round-1 sweep fixture for WP7b has exactly this weakness — running the shared
tool against it reports 28 survivors, all of this shape. So a fixture that fails
its own sweep is **normal for this tool's conventions**, not a defect in the
package under test; what matters is that every survivor is understood and
either fixed or is genuinely not a guard.

Round 2 nonetheless drove the fixture's own sweep down hard, from **122
survivors**, because two classes of survivor were real defects rather than
bookkeeping:

- **Orphaned checks.** `r2_d1_ledger_key_properties` and
  `check_sys_path_bootstrap` were defined but never dispatched. An orphan is
  worse than an unkillable assertion: it is never *run*, so it asserts nothing
  at all while still reading as coverage. `_undispatched_checks()` now audits
  this with `ast` and fails the run on any orphan, so it cannot recur.
- **Tautological assertions.** `require(True, ...)` and a coverage floor read
  off two literal lists can only ever pass. Both were replaced with claims that
  can actually break: the `_require_approval` success case now asserts the
  return value, and the floor counts the check functions **defined in the
  source**.

The remaining fixture survivors are `os.makedirs`/`shutil.rmtree`/`env.pop`
bookkeeping, the `require()` helper's own `raise`, and the `__main__`
scaffolding. None is a guard: dropping an `os.makedirs` breaks the fixture with
a `FileNotFoundError` in a *different* check, and dropping the `__main__`
guard only stops the script from running when invoked directly. They are
enumerated here rather than papered over with equivalent entries, because an
equivalents file would assert they are equivalent when the honest answer is
"not applicable".

### The accumulator

The mechanism that made the fix general is a counter: every assertion
increments `COUNT`, and `main` requires the exact total in
`EXPECTED_ASSERTIONS`. A dropped or unreachable assertion therefore changes the
total and fails the run, instead of being masked by its neighbours. This is the
same idea as the `__main__`-independent table dispatch, and it is what turns
"the fixture calls its checks" into "the fixture *depends on* its checks".

### The fixture's ten accepted equivalents

After the accumulator and the orphan audit, the fixture's own sweep is down from
**231 (round 1) → 122 → 27 → 15 → 2 unaccepted**, and the two that remained
were genuinely not guards. The final run accepts **10 equivalents**, each with a
`file:line` justification, and they fall into three groups:

- **`require()`'s own raise and the `refused()` helper's two arms** — the
  primitive this file asserts with. Both are driven directly by
  `check_refused_helper_contract`, and the `EXPECTED_ASSERTIONS` total would
  expose any of them being neutered.
- **File-transfer plumbing** — one `os.makedirs` inside the pinned-tree staging
  helper, one `shutil.rmtree` cleanup, one `env.pop`. Each is followed
  immediately by a statement that fails loudly if the setup did not happen, so
  no fixture outcome turns on the setup call itself.
- **Entry-point scaffolding** — the `if __name__ == "__main__"` guard and the
  `raise SystemExit(main())`. The harness imports the fixture as a module, and
  every assertion raises `FixtureError` at line 99, so a failing run already
  exits non-zero.

Two of these were *not* accepted on the first pass and had to be fixed rather
than excused: the `os.makedirs` in the staging helper, and `require()`'s raise
before the equivalents file existed at all. That is the correct outcome — an
equivalent should be a thing that was verified not to be a guard, not a
shortcut for one that was not checked.

---

## ROUND 3 — the fixture was testing itself with itself

A lead HOLD, raised after the round-2 package was accepted, asked a single
question: is `require()`'s own `raise` really load-bearing? The round-2
equivalents file claimed yes, on the grounds that "dropping the raise would
turn every assertion in the file into a no-op, which the `EXPECTED_ASSERTIONS`
total at :2669 would immediately expose as a count mismatch."

**Every clause of that justification is false, and the direct probe proves it.**
Replacing `raise FixtureError(message)` with `pass` leaves the fixture printing
`PASS`. The count does drift — to 476 against a constant of 475 — but the
assertion that would notice the drift is *itself* a `require()` call, so the
same edit disables it. The fixture reported success while asserting nothing.

This is not one bug, it is a shape, and round 2 had already named it and then
fallen into it: the notes claim "no check self-attests that it ran." Seven
sites did exactly that. The four `main`-level guards — duplicate-entry, orphan
audit, coverage floor, assertion total — were all written with `require`, so
neutering `require` disabled all four simultaneously. The accumulator that
round 2 introduced as the mechanism making "every assertion load-bearing" was
itself load-bearing only through `require`.

A full sweep of the round-2 fixture with **no** equivalents file reproduces the
same 18 survivors and confirms six of the eighteen claimed equivalents do not
survive their own mutants. The other twelve are the bookkeeping and
scaffolding sites, which are genuine — those were checked honestly and hold.

### The repair: a failure channel the file does not define

`require` and `refused` are the fixture's verdicts. A fixture cannot make its
own reporter lie, so the fix is a reporter that never raises and never counts:

- **`_observed(fn)`** returns what `fn` did as a plain `dict` — `outcome`, the
  exception's exact `type`, and its `message` — catching everything.
- Assertions about that dict are made with the interpreter's own **`assert`**,
  which this file does not define and therefore cannot switch off.

Two new checks are dispatched through the normal tables (so they are not
orphans, and the orphan audit covers them):

- **`check_require_helper_contract`** drives `require` itself through
  `_observed` and asserts with `assert` that `require(False, ...)` raises a
  `FixtureError` carrying the caller's exact message, does not count, and that
  `require(True, ...)` stays quiet. This is the direct negative control the
  lead asked for, and it does not rely on the helper being tested.
- **`check_dispatch_self_audit`** re-proves each of the four `main` guards
  against data that is deliberately broken: it builds a dispatch table with a
  duplicated entry, deprives the table of a real entry and requires the orphan
  audit to **name** that function, and pins the coverage floor's relation to
  the table size. Asserting only the quiet direction would have let the audit
  return a constant empty list forever, which is the vacuous-pass shape this
  fixture exists to avoid — so the firing direction is driven too. This
  required parameterising `_undispatched_checks(dispatched=None)`: with the
  table read only from inside, the audit's own correctness was untestable
  because there was no input on which it could be seen to fire.

`check_refused_helper_contract` was rewritten the same way. Its three negative
controls — a wrong needle, a wrong expected type, and an accepted call — used
to be `require(failed, ...)` assertions, which is the circularity the lead
flagged. Each arm is now pinned to **its own reason string**, so a fixture that
raised a `FixtureError` from somewhere unrelated cannot satisfy them.

### Two further defects found while auditing

**The accumulator was reset in the wrong place.** `COUNT = 0` ran *after* the
four `main` guards, so their four `require` calls incremented a counter that
was immediately zeroed. Their contribution to `EXPECTED_ASSERTIONS` was
discarded, which is why all four survived as S1 mutants even before `require`
was considered. Resetting the counter first puts every assertion in the file
inside the total.

**`needle and needle not in str(exc)` was equivalent over the observed domain.**
The fixture only ever passed a `needle` that was either `""` or a real string.
For both, `True and X` and `needle and X` agree, so the S5 mutant that rewrites
the operand to `True` changed nothing. The guard's real input domain is wider —
a falsy non-`""` value such as `None` makes the two forms genuinely differ — so
the check now drives `needle=None` and requires it to behave exactly like an
absent needle. That killed the site.

This is the same lesson the notes already record about the v1 parser: *a guard
whose input domain is narrower than the code that produces it needs a
synthetic input to be testable at all.*

### The assertion total is now enforced three ways

`main` checks `COUNT == EXPECTED_ASSERTIONS` through three channels that route
through three different failure paths: a bare `raise`, the interpreter's
`assert`, and `require`. On a clean run any one of them can be deleted without
changing the outcome, which is why the sweep reports the `raise` and the
`require` as survivors — and why that is the correct verdict rather than a
defect. What matters is that **no single-statement mutation can remove the
total**, because the sweep's S1 operator drops one statement.

Direct probes confirm the property end to end. Removing any ONE channel and
introducing a one-assertion drift is **killed** in every one of the six
combinations; only removing all three leaves the drift undetected, and no
single-site mutant can do that. The `assert` channel is additionally invisible
to this tool by construction — the sweep does not generate sites for bare
`assert` statements — so it is free defence in depth.

### Result

| | round 2 | round 3 |
| --- | --- | --- |
| sites | 560 | 607 |
| killed | 542 | 592 |
| claimed equivalents | 18 | 15 |
| equivalents verified non-semantic | **not checked** | **6** |
| `require()` neutered → fixture still passes | **YES** | **no** |

Six of the eighteen round-2 equivalents are **retired as invalid** and the
sites behind them are now genuinely killed:

| retired equivalent | why it was not semantic | now |
| --- | --- | --- |
| `S3:99` — `require()`'s own raise | tested only through `require` | KILLED by `check_require_helper_contract` |
| `S3:128` — `refused()`'s wrong-type raise | asserted with `require` | KILLED by a reason-pinned `_observed` control |
| `S1:2619` — duplicate-entry guard | counter reset discarded its count | KILLED by the counter-reset fix |
| `S1:2624` — orphan audit | same | KILLED by the counter-reset fix |
| `S1:2634` — coverage floor | same | KILLED by the counter-reset fix |
| `S1:2668` — assertion total | same | KILLED by the counter-reset fix |

Two further equivalents — `S5:121` (the needle operand) and, in the rewritten
helper, the wrong-reason arm — were not guards either and were closed by code,
not by prose.

### What is still equivalent, and why that is honest

The remaining sites are in three groups, each checked by direct probe rather
than argued in prose:

- **Eight `S2` bookkeeping sites** — a discarded `shutil.rmtree` cleanup, two
  `env.pop("PYTHONPATH", None)` hygiene calls, `os.makedirs`/`shutil.copyfile`
  inside the pinned-tree staging helper, `SCRATCH.mkdir`, and the clean-side
  `m._refuse_real_material` call. Each is followed by a statement that fails
  loudly if the setup did not happen, so removing it leaves the observable
  property intact. Removing it was verified to leave the fixture passing.
- **Two count channels** — the bare `raise` and the `require` in `main`'s
  three-channel total. Individually redundant on a clean run, collectively
  load-bearing under any count drift, as the drift probes above show.
- **Three `__main__` scaffolding sites** — the `__name__` comparison as S4 and
  S5, and `raise SystemExit(_status)`. `main`'s return value is now asserted
  against 0 by `assert` before it is handed to `SystemExit`, so a non-zero
  return is caught (`main(): return 1` is KILLED). What remains is a genuine
  module-scope floor: mutating `if __name__ == "__main__":` to `if False:`
  means no check runs at all, and the only code that could detect that is the
  code that was disabled. This is recorded as a structural limit rather than
  dressed up as a guard.






