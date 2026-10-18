# U-15 CONSISTENCY AUDIT — limited-scope, non-independent

> **Title narrowed after review finding 4.** This was headed "FINAL AUDIT REPORT". That overstated it:
> the author is not independent, and the audit is a fixed set of predicate checks with known coverage
> limits (§2, §4). It is a **consistency audit**, not a validation, and it is not final.

> **SUPERSEDED STATUS, 2026-08-23.** This report audited U-15 while it was **PROPOSED**. **U-15 was
> approved as D005 on 2026-08-23** (Option B). Item 10 below therefore records a status that is no longer
> current; `audit_u15.py` item 10 has been updated to assert the **APPROVED (D005)** status and to fail if
> any surface still carries the superseded "PROPOSED — NOT APPROVED" phrase, and a new item 11 asserts that
> the approved **rule** is not conflated with the still-pending numeric `(1,1,5)`. Re-run the script for
> current state; this document is a dated record.

**Date:** 2026-08-22 · **Auditor:** the lead (**not independent** — see §4) · **Scope:** U-15 only.
**Reproducible check:** `python3 research/audit/audit_u15.py` (read-only; modifies nothing).
**Files audited:** `U15_DECISION_MEMO.md`, `UNRESOLVED_DECISIONS.md`, `STATUS.md`,
`verify_u15.py`. `progress.md` is deliberately excluded because it is an append-only log, not an
authoritative decision surface.

**No scientific decision was modified.** U-17, U-18, U-02, U-03 and all others are untouched. Nothing was
approved and nothing was implemented.

---

## 1. Item-by-item result — **10 / 10 PASS**

Item 10 was added after review finding 2: cross-file status consistency was previously *printed but never
asserted*, while the report drew a conclusion from it. It is now a required check on the full status phrase.

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | `v_budget` = exact smallest attainable positive violation, **not merely** `gcd(prices)` | **PASS** | Memo §11 defines it as the "exact, DP-derived smallest attainable positive budget violation"; gcd is framed as a **lower bound only**; the register carries the identical definition |
| 2 | Stage-1 value verified as **5** | **PASS** | `verify_u15.py` asserts the exact DP-derived minimum `== 5`, asserts gcd-equality as an **INSTANCE FACT** (not a rule), and carries two counterexamples where `gcd ≠ minimum` (`[10,10,10], B=15`; `[6,10,15], B=7`) |
| 3 | Residual-unit / invariance claims correct; **ledger command currently exits zero** | **PASS**, *narrow* | Memo states **both** options preserve objective-rescaling invariance, and that A-as-"one dollar" is **already invariant**; the C0-01-class framing carries `[RETRACTED:U15-2]`. **The ledger result is reported as command behaviour only.** It guards 14 *enumerated* literals under a declared grammar; it does **not** establish that no retracted claim survives. The reviewer independently rechecked the v5 grammar and its regression fixtures; that does not turn this literal guard into certification |
| 4 | Cardinality **completely excluded** from U-18(a) `r` reasoning | **PASS** | Memo §7 has **no live `r_card` column** — the single mention is inside the labelled SCOPE CORRECTION recording that an earlier version carried one. §7 states "no `r` at all" and "sector vs budget only"; register agrees |
| 5 | 5× / 25× calibration statements explicitly conditional on **fixed numerical `s` and `a`** | **PASS** | Present in memo §7, memo §9 table, the register, **and** the verifier's printed output — all four surfaces |
| 6 | Stage-2 comparability explicitly conditional on the eventual **U-09 estimand** | **PASS** | Memo §11.2 names the "Stage-2 estimand", states incomparability is **NOT automatic**, and requires an explicit U-09 decision; register carries the same condition |
| 7 | No text claims Option B is neutral or outcome-independent | **PASS**, *limited* | *Negative:* a pattern scan over `neutral`, `outcome-independent`, `outcome-agnostic`, `unbiased`, `non-directional`, `bias-free`, `result-independent`, bounded to U-15 material, finds no unnegated claim. **It cannot prove absence of arbitrary paraphrase.** *Positive:* the memo carries "Conditioning assumptions attached to this recommendation" and "Conclusions remain conditional on this choice… does not become canonical by being approved"; the register's U-15 section records conditioning. Progress is context only, never evidence |
| 8 | `verify_u15.py` passes | **PASS** | Exit 0 |
| 9 | Retraction ledger **currently exits zero** | **PASS**, *advisory* | Scan and `--selftest` (the ledger's declared fixture suite, F01–F15 + F17) both exit 0. **Advisory only** — a regression guard over enumerated claims, not certification |

| 10 | Cross-file status consistently **PROPOSED / NOT APPROVED** (asserted, not merely printed) | **PASS** | Full phrase required in the memo and the register's U-15 section; STATUS.md records Option B PROPOSED/not approved. The latest U-15-bearing progress entry is context only, not audit evidence |

---

## 2. Remaining contradictions

**No contradiction found by the ten specified checks.** This is deliberately narrower than "none within
U-15" `[review finding 4]`: ten predicates cannot establish global consistency, and §4 lists what they do
not cover.

Three items failed on the audit's **first** run. All three were **defects in the audit script, not in the
documents**, and are recorded here rather than quietly fixed:

| First-run FAIL | Cause | Disposition |
|---|---|---|
| Item 4 | Checker flagged any `r_card` string; the only occurrence is inside a **labelled retraction** | Checker narrowed to live table rows |
| Item 6 | Checker regex was case-sensitive; the memo says "**NOT** automatic" | Checker made case-insensitive |
| Item 7 | Checker scanned whole files and matched per-line; the flagged text was (a) about **U-02/U-18**, out of U-15 scope, and (b) negated **across a line break** | Checker scoped to U-15 material; negation window widened |

**One weakness found and corrected in the audit itself:** item 7 initially passed **vacuously** — the word
"neutral" simply never appears in the U-15 memo, so an absence-only check proves nothing. It now
additionally asserts the **positive** statements of conditionality. This is disclosed because a
vacuous PASS is not evidence.

---

## 3. Out-of-scope observations (recorded, **not** acted on)

The word "neutral" appears in **U-02** material ("`kappa_risk = 1.0` — a neutral, round value") and **U-18**
material ("No reduction is comparatively neutral", "weighted-neutral (review)", "bias-neutral"). These are
claims about **other decisions**, not about Option B, and are **out of U-15 scope**. Per instruction they
were **not examined and not modified**.

---

## 4. What these checks do NOT cover

Stated explicitly so the 10/10 result is not read as more than it is:

1. **Paraphrase.** Item 7 is a pattern scan over seven stated tokens. A claim of neutrality worded without
   any of them would pass undetected. Only a reader can close this.
2. **The ledger guards enumerated claims only.** Items 3 and 9 report that it *currently exits zero*; they
   do **not** certify that no retracted claim survives anywhere. A retraction never added to the ledger is
   unguarded. The v5 grammar and fixtures were independently rechecked by the reviewer, but that does not close
   paraphrase or coverage limits.
3. **Predicate audits cannot establish global consistency.** Ten string/structure predicates over five files
   cannot rule out a semantic contradiction none of them was written to look for.
4. **Substance is out of scope.** These checks test whether the U-15 *documents agree with each other*.
   They say nothing about whether Option B is the *right* choice — that is the human approver's decision,
   informed by the reviewer's independent audit.
5. **Author is not independent** — see below.

---

**This audit is not independent.** I am the author of the material being audited and of the checker that
audits it; the first run's three false failures are direct evidence that the checker is fallible.
**The reviewer's independent audit is still required before approval.**

**I do not approve U-15.** Approval is the human approver's decision.
## 5. Readiness for human approval

**U-15 is internally consistent and, on the record audited here, ready to be put to a human approver — with
four conditions that must travel with it and be approved alongside, not after:**

1. **It is a conditioning choice.** Not an invariance repair, not outcome-neutral. Both options preserve
   objective-rescaling invariance, and both are currency-unit invariant when stated dimensionally, so
   rescaling is **not** a discriminator. The discriminator is **reachability**: under A the budget
   reference violation cannot occur.
2. **`v_budget = 5` is contingent on a synthetic price vector** — hand-chosen round numbers with no
   documented market derivation (`PROTOTYPE_AUDIT.md` F-4). This must be stated in any write-up.
3. **It requires an explicit U-09 decision.** If Stage 2 resamples prices the reference may change per
   instance; whether that breaks comparability depends on the Stage-2 estimand, which is **not yet
   defined**.
4. **It does not resolve U-18(a).** It removes one obstacle — a common `r` becomes coherent across the two
   inequality families — but the choice of `r` remains an external conditioning decision with **no
   recommendation**.

