# Retraction-ledger scan scope — POLICY

**Decision: APPROVED by Shivansh, 2026-08-23.** This is a **process/protocol** decision about audit
tooling. It is **not** a scientific decision and does not appear in `DECISIONS.md`.

**Governs:** `research/audit/check_retractions.py` — specifically the F18 scan-coverage item.

---

## The policy

**The append-only log and message files are OUT OF SCOPE for the retraction ledger, by design.**

Out of scope, deliberately:

- `progress.md`
- the review log
- the review log

In scope: everything under `research/` matching the declared SCAN MANIFEST (`.md`, `.py`; excluding
`raw`, `02_experiments`, `03_result`).

This is a **positive statement of intent**, not an unestablished limit. F18 should be worded accordingly:
the ledger's coverage of the log files is not "not yet established" — it is **declined on purpose**.

## Why

These three files are **append-only**. They are a **historical record of what was believed and when**,
not a statement of current project state. Two consequences follow:

1. **A superseded claim in a log entry is not an error — it is the record working correctly.** The log is
   supposed to show that something was once believed and later withdrawn. Marking or removing it would
   destroy the very history the append-only rule exists to preserve.
2. **Bringing them in scope would create unrepairable failures.** Any retracted claim already written into
   an append-only file could never be brought under the retraction grammar, because the file cannot be
   edited. The scan would fail permanently with no permitted repair — a guard that cannot be satisfied is
   worse than a declared boundary.

There is also an ongoing authoring cost: under the alternative, every future handoff that *quotes* a
retracted claim in order to discuss or withdraw it would itself need marker formatting. That burden falls
on exactly the sentences whose purpose is to correct the record.

## The protocol that replaces ledger coverage

**Retraction-by-later-entry.** When a claim in an earlier log or message entry is found to be wrong:

1. **Do not edit the earlier entry.** Both files are append-only.
2. Append a **new timestamped, authored entry** that quotes or identifies the false statement, names its
   **file and line**, states plainly that it is **retracted**, and gives the correct statement.
3. If the same claim also appears in any file under `research/`, repair **that** occurrence under the
   ledger's retraction grammar — that is where the ledger is authoritative.

A reader must therefore treat the log files as **dated** and read forward for corrections. They are not a
status surface. The authoritative current-state surfaces are `DECISIONS.md`, `UNRESOLVED_DECISIONS.md`,
`STATUS.md` and the specifications.

## Known unmarked occurrences in out-of-scope files

Recorded here so that a reader who greps the repository and finds them knows their status. **These are
permitted under this policy and must not be edited.**

| File | Occurrences | Tag | Status |
|---|---|---|---|
| the review log | 3 | `U15-2` | 1 original error (`:2221-2222`), 2 later quotations made in order to retract it |
| `progress.md` | 0 | `U15-2` | the 03:05 entry paraphrased rather than quoted; retracted in the 04:10 entry |

The `U15-2` claim itself is retracted, and is correctly bound under the retraction grammar at its
in-scope location in `research/01_validation/VALIDATION_SPEC.md`.

## Scope of this policy

It settles **where the ledger scans**. It does **not** weaken any other declared limit — in particular
**F16 (paraphrase / semantic equivalence) remains manual review**, unchanged, for every file in scope.
