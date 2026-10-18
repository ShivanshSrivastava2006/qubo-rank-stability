# Gate-9 WP7 packaging — DRAFT (final round)

**Status: DRAFT. NOTHING HAS BEEN PUSHED.** No Kaggle API call, no Kaggle CLI
invocation, no GPU allocation, no `nvcc` invocation, no run, and no credential
read occurred in producing or testing this package. This document is not an
approval, a release, or an authorization of any kind.

**Owner authorization, verbatim:** "Build the WP7 session script,
environment-pinning configuration and push manifest offline. Treat them as
drafts until all dependency hashes and reviews are final. No API push, GPU
allocation or run is authorized. Changes to dependencies must invalidate the
package and trigger revalidation."

## What changed in this final round

Four carry-forward items, each with a fixture that fails when its guard is
removed.

1. **The package inventory is exactly the package files.** The hardcoded
   `*.r1` / `*.r2` round-save entries are gone from `PACKAGE_FILES`
   (`build_wp7_package.py:44-56`). `PACKAGE_FILES` is now the five real
   package files. A round-save file left beside the package is therefore an
   *unreviewed* entry, and `assert_package_inventory` refuses it
   (`Wp7DependencyError: unreviewed package entries`) rather than silently
   pinning it. This is what makes the package directory contain only package
   files.

2. **The session opens a SEALED OPTION A reference; it never computes one.**
   The owner-approved Option A is wired in. `open_sealed_reference`
   (`wp7_session.py:0d`) reads a seal file shipped with the package, hands it
   and the session inputs to `stage2_reference_seal.open_for_session` — loaded
   by file path from the dependency the gate already hash-verified — and
   receives a callable that answers only what the seal contains. The reviewed
   seal module re-verifies the whole seal, the input hashes, the production
   identity and the coordinate census on open, and refuses on any mismatch.
   `open_sealed_reference` is a **mandatory step** in `REQUIRED_STEPS` and sits
   between section-B item 1 and item 2; a receipt that omits it is refused, and
   item 2 is never reached without it. The session is structurally prevented
   from computing a reference in-session.

3. **The reviewed-dependency table is a clearly-marked placeholder.**
   `wp7_reviewed_dependencies.json` is `_placeholder: true` with
   `PENDING_PLACEHOLDER` package hashes and `PENDING` dependencies. The lead
   (Claude) writes the real table **after** this build, from the applied
   real-project hashes. The builder refuses a placeholder table, so the
   manifest stays `draft_invalid` and cannot be built or verified as ready from
   the shipped table. The fixtures build against a **synthetic** table in a
   temp dir, never the shipped one.

4. **The session order is unchanged** and now records the seal opening:

   `dependency_gate` → `capture_platform_identity` → `compare_environment_pin`
   (fail-closed) → `synthetic_instance_gate` → `wp6b_section_a_qualification_plan`
   (WP6b §A) → `wp1_production_identity_candidate` (WP1) →
   `section_b_item_1_recheck_synthetic` (WP2) → **`open_sealed_reference`** →
   `section_b_item_2_full_domain_synthetic` (WP3, on a synthetic instance,
   against the sealed reference) → `wp4b_writer_synthetic_ranges` (WP4b) →
   `emit_non_scientific_receipt`. A non-synthetic input is refused before any
   step.

WP4b (the production writer) and WP6b (the CUDA +0.0 path) are still in their
own final review rounds and are **not yet in this tree**. They are integrated
through their documented entry points as **injected dependencies**: the session
refuses to run if they are missing. The session does not wait for them.

## What this package is

Per the 2026-09-27 revision of
`research/g9/GATE_9_SECTION_B_CLOSURE_PLAN_DRAFT.md`, WP7 covers three things in
**one** owner-approved push:

1. the WP6b §A corruption qualification;
2. production-identity qualification (WP1);
3. the non-scientific end-to-end dry run.

The files here are the offline draft of the session package for that single
push. They are built and tested entirely offline.

| File | Role |
| --- | --- |
| `wp7_session.py` | the session script that *would* run on Kaggle |
| `wp7_environment_pin.json` | the DRAFT environment-pinning configuration |
| `build_wp7_package.py` | assembles the bundle and the push manifest; also the manifest verifier (`--verify`) |
| `wp7_reviewed_dependencies.json` | the PLACEHOLDER reviewed table the lead replaces after the build |
| `wp7_push_manifest.draft.json` | produced by the builder; carries the draft status |
| `verify_wp7_package_fixtures.py` | the fixtures and the guard inventory |
| `GATE_9_WP7_PACKAGE_DRAFT.md` | this document |

## Validity rule — the package is invalid right now

The package status is **`draft_invalid`**, and it stays invalid until **every**
dependency review has PASSED and its content hash is recorded in the dependency
table. Concretely:

- The builder reads a dependency table mapping a repo-relative path to the
  sha256 recorded when that file's review PASSED, or the literal `PENDING`.
- It hashes every dependency **and every file of the package itself**
  (`kaggle_wp7/*`). If **any** entry is `PENDING`, **any** file is missing, or
  **any** current hash differs from the recorded reviewed hash, the manifest
  status is `draft_invalid` and each individual reason is listed in
  `invalidating_reasons`.
- The status is `draft_ready_for_owner_review` **only** when every entry matches.
- The manifest verifier re-hashes everything and refuses a stale manifest.

### What round 2 added, and why

The independent validator of round 1 found three ways to change the package
without invalidating it. Each is now closed and each is proved by a fixture that
fails when the guard is removed.

| Round-1 defect | Round-2 closure |
| --- | --- |
| Removing a dependency entry from a ready manifest and recomputing the body digest still verified. | The manifest pins the dependency **set**: `dependency_table_sha256` is the canonical digest of `path -> recorded hash` and `dependency_count` fixes its size. `verify_manifest` recomputes the set from the entries and refuses any set that does not reproduce it. |
| Four package files were pinned as `null`, so package code could change without invalidating anything. | Every one of the five `kaggle_wp7/*` files is hashed by `evaluate_package_files`; a missing file is an invalidating reason, never a silently skipped entry. A one-byte change to any of them makes the manifest that pinned the old bytes stale. |
| The session could emit a receipt with every required step `not_run`. | `REQUIRED_STEPS` are mandatory. A missing step is a refusal (`Wp7StepNotRunError`); there is no `*_not_run` counter. The receipt is only returned after `validate_receipt` accepts it, and `validate_receipt` refuses a receipt missing any of `RECEIPT_REQUIRED_FIELDS`. |
| A record claiming to be synthetic was accepted while naming a real dataset. | The instance must declare `instance_kind`, `synthetic: true` **and** a `source` naming one of the permitted synthetic generators and naming no real data source. |
| Absolute and `..` dependency paths read files outside the root. | Two path guards. `normalize_relative_path` refuses, lexically, absolute, drive-qualified, backslash, NUL, empty, `.` and `..` forms before anything is opened. `resolve_inside_root` then refuses a missing file, a non-regular file, and any symlink whose real target leaves the root. |
| `content_sha256(None)` raised a raw `TypeError`, and the fuzz fixture accepted `TypeError`/`AttributeError`. | Every public entry point raises a typed `Wp7PackageError`/`Wp7SessionError`. The fuzz fixture accepts **only** those types, and fuzzes each argument with `None`, `bool`, `int`, `float`, `str`, `bytes`, `list`, `tuple`, `dict`, unhashable values, live iterators and bare objects, including nested wrong types. |
| The fixtures copied all of `os.environ` into child processes. | Child processes get a scrubbed, allowlist-built environment. A fixture plants a credential value, runs the builder CLI and asserts the value appears in no file, no stdout and no stderr. |

### What this final round fixed

The validators found three exception-handling defects and three
regressions against the validated round-3 design. All six are closed, and
each closure has a fixture that fails when the guard is removed.

| Defect | Closure |
| --- | --- |
| `open_sealed_reference` called `seal_real.read_bytes()` unguarded, so an unreadable seal path let a raw `OSError` escape a public entry point. | Every trust-boundary read goes through `read_bytes_at_boundary` (with typed siblings `read_text_at_boundary` and `read_json_at_boundary`). It converts **`OSError`, `UnicodeError`, `ValueError` and `json.JSONDecodeError` only** — never `BaseException`, so `KeyboardInterrupt`/`SystemExit` still propagate — into the module's typed error with `from`, preserving the original as `__cause__`. Fixtures cover an unreadable file, a directory, a dangling and a live symlink, every specific class, and a `KeyboardInterrupt` that must *not* be swallowed. |
| `verify_manifest` called `sha256_file(real)` outside the guarded block, so an unreadable dependency **crashed** the verifier instead of reporting the invalidation. | An unreadable, missing or changed matched dependency is an **invalidating reason**: `verify_manifest` returns `status: draft_invalid` with `invalidating_reasons` naming it, and does not raise. This is the owner's condition made executable. A manifest that *claims* `draft_ready_for_owner_review` over a stale dependency is still refused loudly — that is a forgery, not an invalidation — and a forged/trimmed dependency set is still refused, so the new return path is not a hole. |
| `evaluate_package_files` and `_verify_package_files` called `sha256_file(real)` without catching an unreadable package file. | Both return a package-file invalidating reason. Fixtures cover unreadable, missing, non-regular and changed files, including the `draft_invalid` result from `verify_manifest`. |
| `_require` was deleted. | Restored verbatim in both modules. |
| `test_shipped_table_keeps_manifest_invalid_in_this_tree` was deleted. | Restored, rewritten against the current anchor API: it proves the shipped placeholder is refused at its own true digest and that no manifest can be built or verified as ready from it. |
| `S_ISREG(real.stat().st_mode)` was weakened to `.is_file()`, which follows symlinks. | Restored, alongside `resolve_inside_root`'s "resolves to the root itself" guard, `normalize_relative_path`'s absolute-`"/"` and `posixpath.normpath` guards, the `dependency path must be a string` and `package_root must be a Path` type checks, and the session's `probes` / empty-source / empty-record / `os.path.normpath` guards. |

The round-3 ordering in `assert_synthetic_source` was also restored: the
generator-name check runs **after** the forbidden-fragment check, so a record
that claims to be synthetic while naming a real dataset is still refused
rather than laundered into a source classification.

Restoring `_require(isinstance(key, str), ...)` in `_flatten` surfaced a real
bug: the round-1 replacement checked key types *after* `sorted(value)`, so a
mixed-key dict raised a raw `TypeError` from the comparison instead of the
typed refusal. The check now runs before the sort.

**Any change to any dependency, to any file of the package, or to the dependency
set itself — one byte is enough — changes the pinned hashes, returns the status
to `draft_invalid`, and triggers revalidation.** That is the owner's rule and it
is enforced in code, not in prose.

**The manifest can never emit an "approved" or "pushed" status.** The status
vocabulary is closed to `draft_invalid` and `draft_ready_for_owner_review`;
`validate_status` raises on anything else, and the verifier independently
refuses a manifest that claims `push_authorized`, `gpu_allocation_authorized`,
`run_authorized`, or `can_emit_approved_or_pushed`. A manifest missing any
required schema field is refused as incomplete, never partially accepted.

At the time of writing, WP1, WP2, WP3, WP4a, WP4b, WP5b, WP6 and the WP6b
`+0.0` CUDA files **do not exist in this tree**; their review is happening in
other packages. They are recorded `PENDING` in the dependency table, and that
alone keeps the manifest invalid.

## Environment pin

`wp7_environment_pin.json` records the accepted v1 platform values and the
image/build fields, each labelled **PLATFORM-REPORTED**. Per the provider-trust
amendment §3 these are reported values, never called proof, and a reported
change still forces requalification.

The comparison rule is **fail-closed** and runs as the first action of the
session before any computation. A difference in value, in type, in presence, or
an extra reported field is a difference, never a pass; so is a reported value
that is a list, or an identity nested deeper than the reported identity allows.
The session aborts and emits a non-scientific difference record naming each
differing field. The request to Kaggle is to pin the environment to the accepted
image digest — but the pin is then *verified by comparison*, never assumed to
have taken effect, because dry run v2 submitted a pin and still ran a CPU
environment.

## Session script

`wp7_session.py` runs in the declared order and refuses out of order:

 0. refuse to start unless every declared dependency is present, is a normalized
    repo-relative path that stays inside the root, and its content hash matches
    the recorded reviewed hash;
 1. capture the platform-reported identity;
 2. compare it with the pin — any single field difference aborts before any
    computation;
 3. run the synthetic-instance gate — a refusal if the instance is not synthetic,
    and a refusal if the gate produced no instance at all;
 4. run the WP6b §A corruption qualification plan;
 5. build the WP1 production identity and record it as a qualification candidate;
 6. run §B item 1 (WP2), then open the sealed OPTION A reference, then run
    §B item 2 (WP3) against that sealed reference on a **synthetic instance
    only**;
 7. run the writer (WP4b) on synthetic ranges into a local output directory that
    must resolve inside the root;
 8. emit only non-scientific counters, identities and digests per §B item 3, plus
    a receipt.

**The receipt is complete or it is not emitted.** `RECEIPT_REQUIRED_FIELDS` is
the required field set; a receipt missing any of them is refused. Every required
step must appear in `steps_executed`; a step that is absent is a refusal, never
a "not run" counter. Step results are shape-checked: a result may only carry
`counters`/`identities`/`digests`/`status`, `counters` and `digests` must be
plain scalars (so no list of "scientific outputs" and no credential path can be
smuggled into the receipt), and a non-`ok` status is refused. The receipt keeps
no scientific value: `scientific_outputs` is empty and `scientific_output_count`
is 0.

The script is never run here beyond a host-side dry parse/import check with
stand-ins. Its `main()` refuses to execute and returns 2.

## Kernel metadata draft

`kernel_metadata_draft` inside the manifest is a **draft**, consistent with the
submitted/pulled pairs in `research/g9/kaggle_dry_run/`: a private T4 GPU
script, internet off, TPU off, no attached sources.

**Kaggle rewrites some fields on pull**, so a pulled field is not a submitted
field. From the observed pairs: `id_no` is added by Kaggle; `code_file` is
slugified with dashes where the submitted form used underscores; `keywords`
gained `"gpu"` in the accepted v1 pull where the submitted value was `[]`; and
`docker_image` is added on pull and was never submitted in the accepted v1 run.
`kaggle_rewrites_on_pull` records each of these so no reviewer mistakes one for
the other.

## Prohibitions observed in the code and in the fixtures

- No Kaggle CLI invocation, no Kaggle API call, no `subprocess` call, no shell,
  no network client anywhere in `kaggle_wp7/`.
- No credential file or credential environment variable is read. The session
  refuses to start if any environment variable whose name begins with
  `KAGGLE_` is present, reading only the variable **name**, never its value,
  and it never opens the account's Kaggle configuration directory.
- No GPU allocation and no compiler invocation; no GPU array module and no
  device framework is imported.
- Grep-level and AST-level fixtures assert the absence of all of these in
  every file in this directory.

## How the checks were proved

`verify_wp7_package_fixtures.py` carries a guard inventory (`GUARDS`): **166**
`(file, function, guarded line)` triples. The inventory is itself checked
against the sources, so a stale entry is a fixture failure.

An **automated parallel mutation sweep** replaces each guarded statement, one
at a time, with a no-op in a private `mktemp -d` copy of the whole
`research/g9` tree, structurally identical to the original, and runs the fast
fixture subset there. `if` guards become `if False:`, `raise`/`assert`/`return`
become their innocuous form, an `except` handler becomes an empty one — so the
original exception escapes, which is exactly the regression the typed-read
helper exists to prevent — a `for` body is emptied and a value-threading
`Assign` becomes `None`. A mutant that still passes has no fixture reaching
it.

**The sweep runs a control first**: the unmutated copy, through the identical
pipeline, which must pass. Without it a broken temp copy would kill every
mutant on the same incidental error and the survivor count would read `0`
while no guard was ever exercised. (It did exactly that on the first run here,
which is why the control is now mandatory and the sweep aborts without it.)

Final round result: **166 mutants, 166 killed, 0 survivors, 0 skipped,
0 errors**, control `CONTROL-PASS`, at most 4 concurrent workers under
`nice -n 10`, **187.86 s wall time**. The `2^20` production comparison is
outside this offline package fixture suite and was not run by the sweep.

**Survivor count: 0.**

The earlier sweep surfaced **8 survivors**. The continuation restored the
validated guards and added fixtures that isolate them; the remaining
duplicates were resolved by the dominance proof below:

| Survivor | Why it was unreachable | Resolution |
| --- | --- | --- |
| `sha256_file` / `_load_seal_module` / `open_sealed_reference` `isinstance(path, Path)` | The very next line (`read_bytes_at_boundary`, `resolve_inside_root`) already refuses a non-Path with the same typed error. | The validated `sha256_file` check was restored and separately exercised; the two new helper duplicates remain omitted. |
| `build.normalize_relative_path` `os.path.isabs` | On this platform `os.path.isabs` is exactly `startswith("/")`, which the preceding line already tests. | Restored as a validated guard and covered by the final sweep. |
| `build.resolve_inside_root` `real.is_file()` | The `S_ISREG(real.stat().st_mode)` line immediately below catches every case it caught. | Restored as a validated guard; a fixture makes each regular-file check decisive in turn. |
| `build.normalize_relative_path` `posixpath.normpath` | Exhaustively enumerated over 2- and 3-component paths: **no** string differs from its normpath while surviving the `""`/`.`/`..` component checks. | Deleted. |
| `build.resolve_inside_root` `real == root_real` | Every relative path that could resolve to the root itself (`.`, `a/..`, `a/b/..`) is already refused as a `.`/`..` component. | Deleted. |
| `run_session` `python_reference is None` | The branch immediately above unconditionally assigns it in the same `if`. | Deleted; the comment records why. |

The remaining omissions are dominated by guards that are still present. The
regular-file boundary cases are pinned by fixtures, including a FIFO and a
directory.

The round-3 continuation restored four checks that the prior sweep could not
distinguish from neighboring checks. Targeted fixtures now exercise each
independently: the two regular-file checks, the session SHA-256 path type check,
and the refusal when a path resolves to the root itself. The final sweep above
was rerun after those fixtures were added.

Every public argument is fuzzed with `None`, `bool`, `int`, `float`, `str`,
`bytes`, `list`, `dict`, unhashable values, live iterators, bare objects and
nested wrong types, and every one must raise a **typed**
`Wp7PackageError`/`Wp7SessionError` — never a raw `TypeError` or
`AttributeError`.

The fixtures run identically under `python3 -B` and `python3 -B -O`.

## Nothing here may be pushed

This package is a draft. Pushing it would require a separate, explicit owner
authorization, and the manifest cannot record one. No run is authorized. A
successful dry run would still state that no scientific value is produced and
would authorize no scientific work.

## Review anchor and receipt evidence

**The shipped `wp7_reviewed_dependencies.json` is a PLACEHOLDER, not a reviewed
table.** It carries `_placeholder: true`, `PENDING_PLACEHOLDER` package hashes
and `PENDING` dependencies. The lead (Claude) writes the real table **after**
this build, from the applied real-project dependency hashes, and supplies its
SHA-256 to both build and verify as `--expected-reviewed-table-sha256`. The
package never obtains that expected value from its manifest.

Because the shipped table is a placeholder, `load_reviewed_table` **refuses**
it (`reviewed package hash of ... must be a lowercase sha256 hex digest`), so
no manifest can be built or verified as ready from it, and the shipped draft
manifest stays `draft_invalid`. The fixtures build against a **synthetic**
reviewed table in a `mktemp -d` package root, never the shipped one. This is
the intended state: the package is invalid until the lead's real table lands.

The real table records reviewed dependency hashes or `PENDING`, and hashes of
every package file except the table itself and the generated manifest. Any
changed table, dependency, package file, added package entry, or manifest is
refused against the caller's approved table digest and the recorded file
hashes. **Changes to dependencies must invalidate the package and trigger
revalidation** — that is enforced in code, not in prose.

A session accepts a synthetic instance only. Each completed step must return a
nonempty output whose SHA-256 is included in the receipt. A skipped or empty
step cannot produce a complete receipt. `open_sealed_reference` is a required
step: a receipt that does not record it is refused.
