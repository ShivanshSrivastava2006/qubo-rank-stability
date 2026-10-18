# Gate-9 WP0 — v1 production-gap audit (DRAFT), round 3

**Status:** READ-ONLY audit draft by the lead, 2026-09-27 (round 3, revising
round 2). Not an approval, release, requalification or authorization. **Exactly
one file was modified: this one.** No Kaggle push or run, candidate draw,
instance, ground truth, scientific record, or Gate-10 work occurred or is
authorized. §B remains **OPEN**.

**What changed in round 3, and why.** Round 2 was returned FAIL on two findings,
both **accepted**:

1. **Record coverage was incomplete.** The amendment's §B item 3 requires the
   session to write *platform/source identities*; round 2 listed only "identity
   recheck counters". And the amendment requires **every** comparison to include
   four named fields; round 2 mentioned them once in prose, not per row. Both are
   now in the coverage table as explicit rows and as an explicit per-row column,
   with the governing amendment lines quoted (§2.0, §2.2, §2.2.0).
2. **Gap G5 was mis-classified as conditional (a)/(b).** It is **not**
   conditional. A fired D013 branch runs as CUDA ranges and the amendment demands
   a bit-for-bit CUDA comparison **including the inactive `+0.0` families**, but
   v1 hard-refuses them. That is an **unconditional class (b) gap**, now split
   into **G5a** (the WP6 Python `+0.0` evaluator, the canonical reference) and
   **G5b** (the CUDA `+0.0` capability itself, needing its own §A). The round-2
   claim *"No unconditional class (b) gap found"* is **withdrawn**.

**The owner has now decided both open questions**, in
`research/decisions/GATE_9_WP0_D013_CUDA_PATH_AND_IDENTITY_SCOPE_OWNER_DECISION.md`
(APPROVED, 2026-09-27). This round rewrites the report to those decisions:

- **D013 `+0.0` capability = "New additive CUDA path"** (`:26-35`). New CUDA/host
  source files; **all 12 §A files stay byte-identical**; the new path gets its own
  §A corruption qualification including new `+0.0` and slack-register cases, in
  the same Kaggle session as the WP7 dry run; the WP6 Python evaluator is the
  canonical reference it must match bit for bit.
- **Production identity scope (G10) = "Bind producer files"** (`:36-43`). The
  production source map = the 12 §A files + the new `+0.0` path + every host-side
  file that shapes a scientific record (coordinate iterator, record writer, D016
  reconstruction, the §B item 1/2 harnesses, generation-binding code). Any change
  forces a new qualification. The production identity is qualified in the WP7 dry
  run.

**Consequence:** the conditional "(a) if scope = …, (b) if scope = …" apparatus of
round 2 is **withdrawn** — G10 is decided, so the classifications are no longer
conditional. **There is now no open class (c) gap.** G10 is RESOLVED; G5b is an
unconditional class (b) whose *route* the owner has also decided (new additive
path, not a change to v1).

**Scope question answered:** can the qualified **v1** release *as accepted,
byte-identical* produce every declared Stage-2 record type? Answer: **no** — the
release contains a bounded, coordinate-free stream engine and no producer, and it
refuses inactive `+0.0` families outright. The consequence is host-side work plus
**one** new additive CUDA path. **No v1 engine feature is claimed missing that v2
provides**, so the owner's provisional v1 choice is unaffected.

**Governing texts read** (SHA-256 recomputed this session, this copy):
- `research/g9/GATE_9_SECTION_B_CLOSURE_PLAN_DRAFT.md` — `fd88e2e2…` (the plan under audit)
- `research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md` — `589fdc29…` (approved; approval `a2b0747a…`)
- `research/decisions/GATE_9_SECTION_B_KAGGLE_PROVIDER_TRUST_AMENDMENT_DRAFT.md` — `aa10e23d…` (approved)
- `research/decisions/GATE_9_STAGE2_PROTOCOL_DRAFT.md` — `8a5785fd…` (approved)
- `research/decisions/GATE_9_CUDA_CORE_A_VERSION1_OWNER_ACCEPTANCE.md` — `a3d644da…`
- `research/decisions/GATE_9_D013_INACTIVE_EVALUATOR_SPEC_OWNER_DECISION.md` — `f8613652…` (approved owner decisions; WP6 evaluator **spec**)
- `research/decisions/GATE_9_WP0_D013_CUDA_PATH_AND_IDENTITY_SCOPE_OWNER_DECISION.md` — `33099bc9…` (**new this round; APPROVED owner decisions** on the D013 `+0.0` CUDA path and the production-identity scope)
- `research/g9/GATE_9_WP6_D013_SPEC_GAP_DRAFT.md` — `53600111…`
- `research/decisions/GATE_9_STAGE2_SAMPLED_VERIFICATION_AMENDMENT_DRAFT.md` — `3105b24d…` (**DRAFT, NOT approved**)
- `research/g9/cuda_qualification/`, `research/g9/`, and `src/`

---

## 0. ROUND-3 RULING MAP

| Ruling | Requirement | Where addressed |
| --- | --- | --- |
| **1** — ACCEPTED | Record coverage: add the required **platform/source identities** output (amendment §B item 3), and list **for every comparison row** the required fields *energy-minimum words, canonical minimum index, tie flags, and D015/D016 reconstruction*. Quote the amendment lines. | §2.0 quotes the full §B item 2–3 clause (amendment `:78-90`); **new row 16** (platform/source identities) in the §2.2 table; **new §2.2.0** stating the four required fields as a per-row obligation with the verbatim quotation; the §4.1 count table's comparison-unit column now names them |
| **2** — ACCEPTED | G5 is **unconditional class (b)**, not conditional (a)/(b). Split into **G5a** = WP6 Python `+0.0` evaluator (canonical reference, spec closed by the D013 evaluator owner decision) and **G5b** = the CUDA `+0.0` capability a fired D013 branch's CUDA ranges need. v1 refuses `+0.0`, so G5b needs fresh §A. **Decided by the owner as a new additive path.** Correct *"No unconditional class (b) gap found"* everywhere. | §2.2.4 (split and the refusal evidence), §2.5 (owner decision); **G5a/G5b** in the §3.3 register; withdrawn-claims note in §3.3; §6 summary rows and both standing-question answers |
| **3** — RESOLVED BY OWNER | G10 is resolved: remove the conditional "(a) if scope = …, (b) if scope = …" wording. Every host-side record-shaping gap is "bound into the production identity; qualified in WP7". Keep the statement that none of the 12 §A files change. | §3.0.2 (now decided, with the owner's verbatim scope), §3.1 (G10 → RESOLVED), §3.2 (conditional rule **deleted**, replaced by the decided rule), every class cell in §3.3 and §6 |
| **4** — | Update the summary table and the answers to the standing questions, **(b)/(c) first**; no open (c) item remains unless a new one is found (quote it if so). | §6 (table reordered, G5b first), §6 standing-question answers, §7 NOT DETERMINED (item 1 struck — nothing new added) |
| **5** — | Re-verify every file:line citation added or changed. | §8 (new verification ledger for this round); §1.4 ledger retained for round 2 |
| — (round 2, still standing) | Rulings 1–5 of round 2 remain addressed in place | §0 note below, and the round-2 sections they produced |

**Round-2 rulings remain addressed and are unchanged in substance:** the full
citation ledger (§1.4), the D013 companion package in coverage (§2.2 row 14), the
determinate *qualification* identity scope (§3.0.1), the +40 D013-repeat count
from the quoted text (§4.1, §4.1.1), and the MUST-FIX promotion of the beacon
chain and round-selection rule (§5.3). **No round-2 finding is withdrawn**; the
two round-3 findings are *corrections* to coverage and classification, not
reversals of the rest.

---

## 1. RELEASE INTEGRITY

### 1.1 `GATE_9_CUDA_CORE_CORRUPTION_QUALIFICATION_RELEASE.json` — 12/12 match

Every entry under `source_sha256` was rehashed with SHA-256 this session and
compared to its recorded value. **No mismatch.**

| File | Result |
| --- | --- |
| `research/g9/cuda_qualification/stage2_cuda_core_bridge.cu` | OK |
| `research/g9/cuda_qualification/stage2_cuda_core_bridge.py` | OK |
| `research/g9/cuda_qualification/stage2_cuda_core_corruption_qualification.py` | OK |
| `research/g9/cuda_qualification/stage2_cuda_core_qualification.py` | OK |
| `research/g9/cuda_qualification/stage2_cuda_core_stream_engine.cu` | OK |
| `research/g9/cuda_qualification/stage2_cuda_core_stream_engine.py` | OK |
| `research/g9/cuda_qualification/stage2_cuda_execution_contract.py` | OK |
| `research/g9/cuda_qualification/stage2_cuda_input_frame.py` | OK |
| `research/g9/run_stage2_cuda_core_corruption_qualification.py` | OK |
| `research/g9/run_stage2_cuda_core_qualification.py` | OK |
| `research/g9/verify_stage2_cuda_core_corruption_qualification_fixtures.py` | OK |
| `research/g9/verify_stage2_cuda_core_stream_engine_host_emulation.py` | OK |

The release file itself hashes to
`585da5d87908738e34c9b9858a0ef6d1c5e5cf4311dd1f6e3ba00a9d0ce6bfb9`, matching the
bound value in the owner acceptance at
`research/decisions/GATE_9_CUDA_CORE_A_VERSION1_OWNER_ACCEPTANCE.md:39`.

### 1.2 `GATE_9_CUDA_CORE_DRY_RUN_RELEASE.json` — 8/8 sources + 2/2 authorities match

All eight `source_sha256` entries match. Both `authorities` entries match:
- `GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_APPROVAL.md` → `a2b0747a…` OK
- `GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md` → `589fdc29…` OK

The file hashes to
`50f25827ef07b8fcbf3f19223f3982b486f1b11c5d71a7d0c037fd1c6f5328a9`, matching the
pinned constant at `research/g9/cuda_qualification/stage2_cuda_core_corruption_qualification.py:36`.

### 1.3 Supporting acceptance anchors — all match

| Artifact | Recomputed | Matches the value pinned at |
| --- | --- | --- |
| `GATE_9_KAGGLE_CORE_A_VERSION1_RECEIPT.json` | `e6f18e4a…` | acceptance `:42` |
| `GATE_9_KAGGLE_CORE_A_VERSION1_OUTCOME.md` | `fe42a381…` | acceptance `:16`, `:41` |
| `GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md` | `589fdc29…` | acceptance `:37` |
| `GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_APPROVAL.md` | `a2b0747a…` | acceptance `:38` |

**Conclusion:** the qualified v1 release is byte-identical to its accepted state
and must stay so. **The 12 files are untouched and stay untouched** — every gap in
this report is satisfiable without editing one of them.

### 1.4 Round-1 citation defects found and corrected

The validator named two. Re-verifying **every** citation in the round-1 body
found **six**, three of which were not named and two of which were *unsupported
claims* rather than merely off-by-one line numbers.

| Round-1 citation | What the file actually says | Correction |
| --- | --- | --- |
| `stage2_cuda_execution_contract.py:8-9` for *"neither exists in this module"* | `:8` is the closing `"""` of the module docstring; the sentence is at **`:6-7`**: *"The eventual CUDA engine and writer must use this contract; neither exists in this module."* | fixed to `:6-7` |
| `stage2_cuda_core_stream_engine.py:107-108` for `COEFFICIENT_FIELDS` | `:107` is `ROW_NAMES`, `:108` begins `COEFFICIENT_ROWS`; the seven-field tuple is `COEFFICIENT_FIELDS` at **`:114`** | fixed to `:114` |
| `…core_bridge.cu:10-13` for a D016 disclaimer | `:10` is `#undef main`, `:12` is `static bool g9_last_core_success`; **the bridge has no such disclaimer at all** | claim withdrawn; only the Python engine's own disclaimer is cited (`…stream_engine.py:39`) |
| `stage2_cuda_reconstruct.py:279` cited as `research/g9/stage2_cuda_reconstruct.py` | the file is at `research/g9/**cuda_qualification**/stage2_cuda_reconstruct.py`; `:279` is `def reconstruct_core_run(...)` and is correct there | path corrected; the "outside the map" point re-verified (§3.3 G2) |
| `GPU_DRY_RUN_V3_RELEASE_DRAFT.md:74` for a `-t 3600` operator timeout | **file does not exist in this copy** | citation withdrawn; the claim it supported is now unsupported and is marked as such in §4.3 |
| `stage2_timestamp_witness.py:566-568`, `:586-601`, `:590-591` for the ordering check | those lines belong to a *different revision* of the module. In this copy (r5) the ordering logic is `_order_verified` at **`:706-797`**, the decisive check at **`:776-778`**, and the public entry at **`:804-809`**; `MINIMUM_AUTHORITIES = 2` is at **`:56`** | all re-derived and re-quoted in §5.2 |

**Two round-1 claims were false, not mis-cited.** Both are corrected here:

- Round-1 §2.1 said *"A repository-wide search for `c_f` in `research/g9/`
  returns **no hits**."* **It returns 19 hits.** They are in
  `research/g9/cuda_qualification/stage2_cuda_reconstruct.py:25` (`CF_VALUES =
  (1024, 2048, 4096)`), `:134-143`, `:198`, and
  `research/g9/cuda_qualification/stage2_cuda_in_memory_runner.py:45-47`. This
  does **not** change the conclusion — both files are outside the qualified
  12-file map (§3.3 G2) — but the round-1 wording was wrong and is withdrawn.
- Round-1 §2.2 asserted *"Whether every 2x coordinate resolves to a coefficient
  record v1 accepts is **not determined**."* On re-reading the D015 texts this is
  answerable and is answered in §2.2.4: the `c_f` half of every D015 comparator
  pair is **already implemented** in `stage2_cuda_reconstruct.py:25,138-143,198`
  (outside the map), so the resolution is host-side and complete on paper.

---

## 2. RECORD COVERAGE — can v1 AS ACCEPTED compute it?

### 2.0 The two governing clauses, quoted in full

**Clause 1 — the protocol's package (amendment D013 branch).**
`research/decisions/GATE_9_STAGE2_PROTOCOL_DRAFT.md:159-164`:

> The D013 ablation is not a base pass, but its already-approved exact-sign
> trigger is applied mechanically and separately after each instance's three-r
> primary core pass. If the trigger does not fire, no ablation runs. If it fires,
> all and only `{C, CB, CS, CSB}` run with D013's already-fixed active-axis,
> **D011, and V-14 package**; none is pooled with the primary result. This
> protocol does not replace, widen, or reinterpret that trigger.

**Clause 2 — the CUDA amendment's §B item 2 coordinate list and required
comparison fields, plus §B item 3's required session output.**
`research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md:78-90`:

> 2. compare CUDA and Python bit-for-bit on the full prepared binary domain for
>    both encodings at every fixed validation coordinate the session may produce:
>    primary `(30,30,30)` at each `r in {0.5,1,2}` under every D015 comparator
>    pair; D011 `(6,6,6)` on its declared 13-cubed subgrid; V-14 0.5x
>    `(0,0,0)`, `(15,15,15)`, `(30,30,30)`, `(30,0,15)`; and V-14 2x
>    `(0,0,0)`, `(55,55,55)`, `(110,110,110)`, `(110,0,55)`. If D013 fires,
>    immediately before its CUDA ranges run, repeat this full-domain comparison
>    at primary `(30,30,30)` for each of `C`, `CB`, `CS`, and `CSB`, including
>    their inactive `+0.0` families. Every comparison includes energy-minimum
>    words, canonical minimum index, tie flags, and D015/D016 reconstruction; and
> 3. write only the pass/fail counters, platform/source identities, and canonical
>    validation digest. It retains no unapproved coordinate-level scientific
>    values in the qualification record.

**Two obligations are carried in that quotation, and round 2 recorded only the
first of them:**

- **§B item 2, the four per-comparison fields** (`:86-87`) — the sentence
  *"Every comparison includes energy-minimum words, canonical minimum index, tie
  flags, and D015/D016 reconstruction"* is scoped by its own words to **every
  comparison**, i.e. to every row of the coordinate list and to every D015
  comparator pair and encoding within each row. It is **not** a one-time
  requirement satisfied by a single field somewhere. §2.2.0 makes it explicit per
  row.
- **§B item 3, the session's required output** (`:88-89`) — *"write only the
  pass/fail counters, **platform/source identities**, and canonical validation
  digest"*. **Platform/source identities are a required output in their own
  right**, distinct from the pass/fail counters. Round 2's coverage table listed
  the counters (as row 8, "identity recheck counters") and the comparison
  counters + digest (row 9) but **omitted the platform/source identities
  entirely**; that is this round's first accepted finding. It is now **row 16**.

**These two clauses are different things and must not be conflated.** Clause 1
governs **which records a fired D013 branch must produce**. Clause 2 governs
**which comparisons a session must run and what each comparison must include**.
Clause 3 governs **what the session writes out**. Ruling 4 asks specifically about
Clause 2's repeat, and §4.1 handles it there. Round 1 omitted Clause 1's companion
package from the coverage table entirely; the full derivation is below.

### 2.1 What v1 is

The 12-file map is a **fixed 20-bit decoded-state-space engine**
(`ASSET_COUNT = 20`, `…stage2_cuda_core_stream_engine.py:50`;
`STATE_COUNT = 1 << DECODED_WIDTH`, `:58`). It takes a **payload plus 1 or 2 flat
seven-field coefficient records** (`…stage2_cuda_input_frame.py:71-72`, and
`COEFFICIENT_FIELDS` at `…stage2_cuda_core_stream_engine.py:114`) and returns
**bounded summaries**: per-stream minima, integer counters and the compacted
canonical tie entries, with no full energy or flag stream
(`…stage2_cuda_core_stream_engine.py:834-838`). **It has no notion of a
coordinate**, no 3-D iteration, and no writer.

`research/g9/cuda_qualification/stage2_cuda_execution_contract.py:6-7` says so
directly: *"The eventual CUDA engine and writer must use this contract; neither
exists in this module."* The v1 map contains the **partition contract**
(`build_range_plan` `:112`, `complete_range_manifest` `:147`,
`validate_final_manifests` `:170`) but no producer that fills it.

### 2.2 Full record list, re-derived from the approved texts

Re-derived line by line from the quotations in §2.0. **Rows 1–9** are the
non-D013 package (protocol `:149-157` plus amendment `:78-83`); **rows 10–14**
are the D013 package for a fired branch (protocol `:159-164`), which round 1
omitted; **row 15** is the D013 inactive `+0.0` capability; **row 16** is the
§B item 3 session output including the platform/source identities, which round 2
omitted.

**The "Required per-comparison fields" column is new in round 3** and is the
ruling-1 correction. Per amendment `:86-87`, **every** comparison must include
**energy-minimum words, canonical minimum index, tie flags, and D015/D016
reconstruction**. That obligation applies *to each row that is a comparison*,
and `—` means the row is a record-production or session-output requirement, not
itself a comparison. §2.2.0 states the per-row obligation in full and shows what
each of the four fields needs from v1.

| # | Required record type | Authority (quoted basis) | v1 as accepted? | Basis | Required per-comparison fields (amendment `:86-87`) |
| --- | --- | --- | --- | --- | --- |
| 1 | Primary core, `r ∈ {0.5,1,2}`, both encodings, 61³ grid | protocol `:149-150`; `ROW_COUNT = 61` `src/g5/core_pass.py:44` | **NO** | No coordinate input, no grid iterator. The engine loops `for slot, record … for encoding` (`…stream_engine.py:847-848`) over records it is handed, not over a grid | energy-minimum words, canonical minimum index, tie flags, D015/D016 reconstruction |
| 2 | Four D015 diagnostic pairs, same grid, never pooled | protocol `:151-152`; pairs at `DECISIONS.md:1243-1244` and `src/g6/trial_runner.py:58` | **PARTIAL** — §2.2.1 | `c_H` ladder in-map; `c_f` half out-of-map but implemented | all four |
| 3 | **D015/D016 reconstruction** (per comparison) | amendment `:86-87` | **NO** | v1 disclaims: `…stream_engine.py:39` *"not a record, classification or D016 producer"*; the reconstructor is out-of-map (§3.3 G2) | — (it *is* one of the four fields) |
| 4 | D011 `(6,6,6)` 13³ subgrid companion | protocol `:153-155`; `MATCHED_COORDINATE_COUNT = 13 ** 3` `src/g6/d011_matched_subgrid.py:54` | **NO** | Same as #1; no subgrid iterator | all four |
| 5 | V-14 0.5x readings at `r=1`, report-only | protocol `:156-157`; `N_axis = 31` `src/g6/ledgers.py:290` | **NO** | Same as #1 | all four |
| 6 | V-14 2x readings at `r=1`, report-only | protocol `:156-157`; `N_axis = 111` `src/g6/ledgers.py:291` | **NO** — §2.2.2 | Same as #1, plus a range question | all four |
| 7 | D016 original-problem ground truth (host) | protocol `:175-179`; amendment `:51-53` | **n/a — host-only by design** | Amendment assigns it to the host; not a CUDA record | — |
| 8 | Per-session §B.1 identity recheck counters | amendment `:88-90` | **NO** | No harness invokes the contract pre-write (§3.3 G8) | — |
| 9 | Per-session §B.2 comparison counters + validation digest | amendment `:88-90` | **NO** | Engine-level comparison exists; no per-session driver (§3.3 G9) | — |
| **10** | **D013 condition `C` — active-axis package** | protocol `:161-163`; `F_C` at `DECISIONS.md:1109` | **NO** | No family selector (§2.3); single condition fits one call | all four |
| **11** | **D013 condition `CB`** | protocol `:162`; `F_CB` at `DECISIONS.md:1110` | **NO** | Same | all four |
| **12** | **D013 condition `CS`** | protocol `:162`; `F_CS` at `DECISIONS.md:1111` | **NO** | Same | all four |
| **13** | **D013 condition `CSB`** | protocol `:162`; `F_CSB` at `DECISIONS.md:1112` | **NO** | Same | all four |
| **14** | **D013 companion package for EACH fired condition: the D011 13³ subgrid record and the V-14 0.5x + 2x records** | **protocol `:162-163`** — *"all and only `{C, CB, CS, CSB}` run with D013's already-fixed **active-axis, D011, and V-14 package**"* | **NO** | No per-condition subgrid or expansion iterator; each condition's D011/V-14 coordinates must be resolved host-side (§2.5) | all four (these are compared rows when a D013 branch fires) |
| 15 | D013 **inactive `+0.0` families** for each condition | amendment `:85-86`; `DECISIONS.md:1115-1118` | **NO — hard-refused before compute, §2.2.4** | `…stream_engine.py:274-275`; `…core_bridge.cu:29` | all four |
| **16** | **Per-session output: pass/fail counters, platform/source identities, and canonical validation digest** — and *nothing else* (`:89-90` *"It retains no unapproved coordinate-level scientific values in the qualification record."*) | **amendment `:88-90` (§B item 3)** — *"write only the pass/fail counters, **platform/source identities**, and canonical validation digest"* | **NO** | No per-session output writer exists (§3.3 G9). The contract defines an identity record but **no session harness binds, re-emits or digest-commits the platform/source identity fields**; `…execution_contract.py:79-81` only validates a caller-supplied mapping, and the closure plan records *"§B.1 recheck — No in-session harness"* (`:30`) | — |

**Row 16 is the round-3 addition (ruling 1).** The platform/source identities are
a required, separately-named output of every session that writes a scientific
output (amendment `:88-89`), and they are the output whose *provenance* the
production-identity scope decision (G10, §3.1) now governs: those identity fields
must name a source map that actually contains the code that shaped the records.
Under the owner's decided scope that is now guaranteed, because the producer files
are inside the production identity — which is **why** G10's answer matters and
**why** row 16 is not satisfied by the counters in rows 8–9.

#### 2.2.0 The four required per-comparison fields, stated per row (round-3
addition, ruling 1)

Amendment `:86-87`, verbatim and in full:

> Every comparison includes energy-minimum words, canonical minimum index, tie
> flags, and D015/D016 reconstruction; and

The sentence has no row-specific exception, so the obligation is inherited by
**every** comparison in the §B item 2 list: rows **1** (each of the three `r`
values, each of the 5 D015 pairs, each encoding), **4**, **5**, **6**, and the
D013 repeat over rows **10–15**. The four fields, and what each one needs from
v1:

| Required field | What it is | v1 as accepted | Evidence |
| --- | --- | --- | --- |
| **Energy-minimum words** | the minimum-energy **word stream** compared bit-for-bit between CUDA and Python | **PRESENT** | The engine's compacted canonical tie entries and per-stream minima are exactly this: `…stream_engine.py:834-838`; the device minimum and its checksum in the ABI layout at `…core_stream_engine.cu` (see `…core_bridge.cu:44-45`, `offsetof(ScanResult, minimum)` / `minimum_index`) |
| **Canonical minimum index** | the **single** canonical index of the minimum, not a set | **PRESENT** | `offsetof(ScanResult, minimum_index)`, `…core_bridge.cu:45`; `natural_minimum_checksum` at `…core_bridge.cu:44`; index space guarded at `…stream_engine.py:58,297` |
| **Tie flags** | the per-tie flags under the frozen comparator | **PRESENT for `c_H` only** | `CH_VALUES = (1024.0, 2048.0, 4096.0)` `…stream_engine.py:65`; `tie_flags` `:462-480`; C side `…core_stream_engine.cu:234-248`. The `c_f` half is out-of-map but implemented (§2.2.1) |
| **D015/D016 reconstruction** | the record reconstructed host-side from the canonical minima/tie data | **NO** | v1 disclaims it (`…stream_engine.py:39`); the reconstructor exists **outside** the 12-file map (§3.3 G2), and the amendment assigns reconstruction to the host (`:55-56`) |

**So of the four required fields, three are engine capabilities v1 has (one of
them, tie flags, only for the `c_H` half of each D015 pair) and one — the
reconstruction — is host-side and out-of-map.** The *comparison* obligation is
therefore satisfiable only by new host-side code (G2, G3) plus a new additive CUDA
path for the D013 `+0.0` rows (G5b); it is not satisfiable by v1 alone. This is
the ruling-1 correction stated as a technical consequence: round 2 mentioned these
four fields once, in §4.1's preamble, and never in the coverage table.

**Row 14 is the ruling-2 addition.** The protocol is explicit that a fired D013
branch runs the **D011 and V-14 package for each of the four conditions** — that
is 4 conditions × (1 D011 record-set + 1 V-14 0.5x set + 1 V-14 2x set) = 12
companion record-sets, on top of the four active-axis condition records. **v1
can produce none of them**, for the single structural reason in §2.1.

#### 2.2.1 The `c_f` half of a D015 pair is out-of-map but implemented

Each declared D015 configuration is a **pair** `(c_H, c_f)` — primary
`(2048,2048)` plus four diagnostics `(1024,2048)`, `(4096,2048)`, `(2048,1024)`,
`(2048,4096)` (`DECISIONS.md:1243-1244`).

v1 implements only the `c_H` ladder: `CH_VALUES = (1024.0, 2048.0, 4096.0)`
(`…stream_engine.py:65`) feeding `tie_flags` (`:462-480`) and the C `tie_flags`
(`…core_stream_engine.cu:234-248`).

**Correction to round 1:** `c_f` is *not* absent from `research/g9/`. It is
absent from the **qualified 12-file map**, and it is fully implemented just
outside it: `CF_VALUES = (1024, 2048, 4096)` at
`research/g9/cuda_qualification/stage2_cuda_reconstruct.py:25`, the classifier
set is required to be exactly those three values at `:134`, bound per-`c_f` at
`:138-143`, and emitted as `"c_f": c_f` at `:198`; the in-memory runner builds
them at `…stage2_cuda_in_memory_runner.py:45-47`. Both files are outside the map
(verified in §3.3 G2).

This is **correct architecture, not a v1 defect**: `c_f` is the *objective*
tolerance of the `OriginalObjectiveService` (`src/g4/classification.py:46,52,75`,
consumed at `src/g6/d011_runner.py:336-338`), a host-side D016 labelling
parameter, and the amendment assigns D016 labelling to the host
(amendment `:51-56`: *"The host performs bounded reference checks and reconstructs
declared records"*). The 5 pairs therefore collapse to 3 distinct `c_H` values
**on the device**; the 5-pair matrix is assembled host-side. The `c_H` half is
fully covered by v1, including fail-closed on non-finite at
`…stream_engine.py:794`.

#### 2.2.2 The V-14 2x coordinate range

The amendment names V-14 2x coordinates `(0,0,0)`, `(55,55,55)`,
`(110,110,110)`, `(110,0,55)` (amendment `:82-83`). All are legal: the 2x axis
is `{"m_lo": 8, "m_hi": 2, "N_axis": 111}` (`src/g6/ledgers.py:291`), i.e.
indices 0..110, and 111³ = 1,367,631 points (`DECISIONS.md:1827`). The 0.5x axis
is `N_axis = 31` (`src/g6/ledgers.py:290`), 0..30, 29,791 points
(`DECISIONS.md:1825`).

**But v1 has no coordinate space at all.** Its index space is the 20-bit *decoded
membership bitmask* (`STATE_COUNT`, `…stream_engine.py:58`), guarded at
`0 <= index < STATE_COUNT` (`:297`) and `index >= kStateCount` on device
(`…core_stream_engine.cu:253`). 110 is a valid *penalty-grid index* but is not
the kind of object v1 accepts. The question "can v1 reach the 2x range" therefore
does not arise: the coordinate must be resolved to a coefficient record
host-side, then the record passed in.

**Resolution of round 1's open question.** Round 1 said it was *"not determined"*
whether every 2x coordinate resolves to a v1-acceptable record. On re-reading,
it **is** determined, and the answer is that resolution is host-side work that
already has a host-side implementation pattern: the reconstructor at
`…stage2_cuda_reconstruct.py` accepts an externally supplied `SlackIndexMap` and
classifiers (`:279-281`), i.e. the coordinate→coefficients step is an *input* to
that layer, not a v1 capability. **The only genuinely open part is whether the
four specific named 2x coordinates each have a D013-active-axis counterpart**, and
that depends on the WP6 evaluator's per-condition domain, which the owner's new
decision now specifies but which is not yet implemented (§2.4, §2.5).

*(Recorded for accuracy, not a defect: the 2x coordinate equal to primary index
30 is `(70,70,70)`, not `(55,55,55)` — see `src/g6/trial_runner.py:197` and the
nesting rule `double[primary_index + 40]` at `src/g6/ledgers.py:386-388`.
`(55,55,55)` is the 2x midpoint, a valid in-range coordinate. The amendment does
not claim otherwise.)*

#### 2.2.3 D013 C / CB / CS / CSB — no family-type selector, but the 4-condition
question is now settled

The four conditions are constraint-set definitions (`DECISIONS.md:1109-1112`):
`C` = cardinality only; `CB` = + budget; `CS` = + sector caps; `CSB` = all three.
Inactive axes carry an identically zero penalty and are omitted from that
condition's grid (`DECISIONS.md:1115-1118`).

v1 has **no family-type enum or selector**. It receives a 7-field numeric record
positionally, 1 or 2 at a time (`COEFFICIENT_FIELDS`,
`…stream_engine.py:114`; `1 <= len(records) <= 2`, `…input_frame.py:71-72`;
`kRowCount = 2`, `…core_stream_engine.cu:86`).

**Ruling-3/4 consequence.** Round 1 raised as class (c) the question *"does the
amendment intend one `run_core` call or four for the D013 repeat?"* The
approved text settles the **record** question: `all and only {C, CB, CS, CSB} run`
(protocol `:162`) — four separate runs, one per condition, and each with its own
D011 and V-14 package (protocol `:162-163`). The only remaining question is the
**call-shape** question (one call per condition vs. a 4-call host loop), which is
a caller-loop concern and not an engine limit: `run_core` takes at most 2
coefficient records, so a 4-condition ablation is **4 calls**, or 8 with both
encodings. **This is not an owner decision; it is settled by the text.** It is
withdrawn from the (c) list in §3.3.

#### 2.2.4 Inactive `+0.0` coefficient families — v1 hard-refuses them, and
#### that refusal is now an **unconditional class (b) gap** (round-3 correction)

**v1 cannot accept an inactive `+0.0` family. It raises before any compute.**

Python side, in the generic entry `coefficient_record`:
```
research/g9/cuda_qualification/stage2_cuda_core_stream_engine.py:274-275
    _require(record["sector_slack"] > 0.0 and record["budget_slack"] > 0.0,
             "active-CSB slack coefficients must be strictly positive")
```
and identically in the synthetic-row path at `:258-259`.

CUDA ABI side, `g9_coefficients_valid`:
```
research/g9/cuda_qualification/stage2_cuda_core_bridge.cu:22-29
  static bool g9_coefficients_valid(const CoefficientData& row) {
    const double values[7] = {...};
    for (std::uint32_t i = 0; i < 7u; ++i) {
      if (value_is_nonfinite(values[i])) return false;
    }
    return row.sector_slack > 0.0 && row.budget_slack > 0.0;   // :29
  }
```
enforced for every row at `…core_bridge.cu:71-73`; failure returns `0u` from
`g9_core_run_v1` (`…core_bridge.cu:57-58`), and the input-frame path converts it
to `InputFrameError("invalid coefficient record")` (`…input_frame.py:76-78`).

This is a **deliberate, consistent design**. The accepted CPU path refuses
identically and says why:
- `src/g5/domains.py:6-8` — *"A future D013 inactive family uses +0.0 and must
  build a different, coefficient-dependent domain; this module therefore rejects
  inactive coefficients rather than reusing this cache."*
- `src/g5/domains.py:126-127` — *"active-CSB cache cannot represent an inactive
  +0.0 family"*
- `src/g5/domains.py:296-304` — `+0.0` *"invalidates the active-CSB cache"*

**Why the round-2 classification was wrong, and what the correct one is.**
Round 2 classified G5 as "(a)/(b) per §3.2" — i.e. it turned on an *unrelated*
question (whether producer files are inside the production identity). That was a
category error, and the validator's G5 finding is **accepted in full**. The
decisive text is the amendment, which requires the `+0.0` families to be compared
**by CUDA**, before a fired branch's CUDA ranges run:

> immediately before its CUDA ranges run, repeat this full-domain comparison at
> primary `(30,30,30)` for each of `C`, `CB`, `CS`, and `CSB`, **including their
> inactive `+0.0` families.**
> — `research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md:84-86`

A **CUDA-vs-Python bit-for-bit comparison** of a family that the CUDA path
**hard-refuses before any compute** cannot be satisfied by any host-side
arrangement. The comparison needs a **CUDA implementation of the `+0.0` family**,
and none exists. And the amendment is explicit that CUDA, not the host, produces
these records: *"the CUDA engine is permitted to generate the primary and
declared companion records for an accepted Stage-2 instance"* (`:57-59`), and the
intended producer for a completed family is *"one qualified CUDA backend"*
(`:134-136`). The round-2 conditional was therefore never the right frame:
**there is no branch of §3.2 on which this gap is (a)**, because the missing
thing is on the **device**, and no decision about which host files enter an
identity can create device code.

**G5 therefore splits into two gaps with two different classes:**

- **G5a — the WP6 Python `+0.0` evaluator (the canonical reference).** This is
  new host-side code in a **new** file, needing no change to any qualified
  source. Its **specification is closed** by
  `GATE_9_D013_INACTIVE_EVALUATOR_SPEC_OWNER_DECISION.md:27-37` (per-condition
  `F_q` and `f*_q`; *"Hard stop"* on an empty `F_q`; `|T_E|` as
  `base × 2^w` with *"2 per inactive sector register (8 for all four sectors) and
  11 for budget"*, recorded with its factors `(base, w)`). **The evaluator itself
  does not exist** — *"No implementation found"* (`GATE_9_SECTION_B_CLOSURE_PLAN_DRAFT.md:32`).
  Class: **new host-side code, bound into the production identity, qualified in
  the WP7 dry run** (§3.1). WP6.
- **G5b — the CUDA `+0.0` capability itself. This is an UNCONDITIONAL class (b)
  gap.** The amendment's `+0.0` comparison requirement is stated as a CUDA
  comparison; v1's `> 0.0` guard makes a `+0.0` record invalid at the ABI boundary
  (`…core_bridge.cu:29`) and in the Python entry (`:274-275`). Satisfying it
  requires either (i) **changing a qualified §A file** — relaxing the guard, which
  the owner has declined, see below — or (ii) **a new additive CUDA path with its
  own §A corruption qualification**. Both are class (b) by the owner's own
  definition: fresh §A evidence is required either way. **The owner has chosen
  (ii)** (§2.5), which preserves the 12 files byte-identical.

**Do not relax v1's guard.** That is stated in round 2 and it survives this
round unchanged: relaxing `> 0.0` would change a qualified source file, and the
accepted CPU path refuses the same thing for the same reason — a `+0.0` family
*"must build a different, coefficient-dependent domain"* (`src/g5/domains.py:6-8`).
It is **not** what the protocol asks for. The protocol asks for a **separate**
evaluator, ready before the first core pass (*"the exact `+0.0` inactive-family
evaluator required by a fired D013 branch must have its own reviewed
non-scientific validation"*, `GATE_9_STAGE2_PROTOCOL_DRAFT.md:166-171`; and
amendment `:111-116`).

**The consequence for the owner, stated plainly.** The WP6 evaluator is a
protocol prerequisite that gates the first core pass, so it blocks in practice.
**And G5b is not merely host work: it needs a compiled, separately qualified CUDA
path, and that qualification is planned for the same Kaggle session as the WP7
dry run** — which is itself still subject to separate owner push approval. The
production identity (G10) cannot be issued without that new path inside it
(§3.1), and no scientific record can be written before either exists.

### 2.5 What the owner decided about `+0.0` (round 3)

`GATE_9_WP0_D013_CUDA_PATH_AND_IDENTITY_SCOPE_OWNER_DECISION.md:26-35`, verbatim:

> 1. **D013 `+0.0` CUDA capability:** "New additive CUDA path".
>    - The `+0.0` inactive-family capability is built in **new** CUDA/host source
>      files. All 12 files of the qualified v1 release stay byte-identical, so v1's
>      accepted §A evidence is untouched.
>    - The new path needs its own §A corruption qualification, including new
>      `+0.0` and slack-register corruption cases.
>    - That qualification is planned for the same Kaggle session as the WP7 dry
>      run, which itself remains subject to separate owner push approval.
>    - The WP6 Python evaluator is the canonical reference it must match bit for
>      bit.

Four consequences, all binding on this audit:

1. **G5b is confirmed class (b) with a decided route.** The owner chose the
   additive path over editing a qualified file. Both are class (b); the additive
   path is the one that keeps §1's byte-identity intact.
2. **The 12 §A files are unchanged by the decision**, and are re-verified
   byte-identical this session (§1.1, §9). v1's accepted §A evidence is
   untouched.
3. **The new path is inside the production identity** (§3.1), and its
   qualification is folded into the WP7 dry run session.
4. **G5a becomes the reference, not an afterthought.** The CUDA path must match
   the WP6 Python evaluator *bit for bit*, so G5a's spec (closed) and G5b's
   implementation are now coupled: a defect in G5a propagates into the CUDA path
   and into the §B item 2 D013 pre-range comparison.

### 2.3 The two specific checks the owner named

- **Can v1 accept inactive `+0.0` coefficient families?** **No — hard-refused
  before compute**, Python and CUDA ABI alike (§2.2.4). It is not a tolerance to
  tune; it is a fail-closed guard that mirrors the accepted CPU path. Because the
  amendment requires these families to be compared **by CUDA**, this is gap
  **G5b**, an **unconditional class (b)**, routed by the owner to a new additive
  CUDA path (§2.5).
- **Can v1 accept the V-14 2x coordinate range?** The range is legal (0..110,
  111³ points, §2.2.2), but v1 has **no coordinate space at all** — its index
  space is the 20-bit decoded membership bitmask. The question does not arise at
  the engine; it is a host-side resolution step, and that step's implementation
  is outside the qualified map.

### 2.4 Record-coverage summary

**Every one of the 16 required record/output types is NO or PARTIAL for v1 as
accepted** (rows 1–16 of §2.2; row 7 is host-only by design and is not a v1
defect). The single shared cause for rows 1–14 is structural (§2.1): the
qualified map is a bounded coordinate-free stream engine plus a partition
contract, and contains no iterator, no coordinate space, no record writer and no
D016 producer. **Rows 15 and 16 have a different cause** — row 15 is a device-side
capability the qualified CUDA ABI *refuses by construction* (§2.2.4), and row 16
is a per-session output with no writer at all.

**Not one of these gaps is a numerical-capability gap that v2 adds**, and **not
one requires editing any of the 12 §A files**. One — row 15 / **G5b** — does
require a **new qualified CUDA path** (class (b)); the rest are new host-side
code bound into the production identity (§3.1). See §6.

#### 2.4.1 Host-produced per-instance inputs (Python, outside CUDA coverage)

**The rows above are the *engine's* obligations. The protocol imposes a second,
upstream set of per-instance records that the coverage list in §2.2 does not
contain, because none of them is a CUDA-produced record.** They are listed here
for completeness, not re-scored: the ruling is that they are **host (Python)
products**, so they fall outside this audit's question — *can the qualified CUDA
map produce them?* — while still being required before any encoding sweep
begins.

**Protocol §4, `GATE_9_STAGE2_PROTOCOL_DRAFT.md:174-178`, verbatim:**

> For each accepted instance, recompute the original feasible optimum and
> `Lambda_ref` from its own `F` and objective before any encoding sweep. Rebuild
> the D006/D008/D010 ledgers under the same frozen formulas, grid, comparator,
> and decoded-only classifier rules; record the new instance-specific
> provenance.

**Approved amendment, `GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md:51-52`,
verbatim:**

> Python remains the canonical reference implementation. It produces the
> canonical binary64 input/coefficient ledgers and original-problem ground truth;

The same clause continues *"CUDA consumes those host-validated values and does
not derive coefficient maps on device"* (`:53`). That is why none of the four
items below can be a CUDA-coverage defect: the amendment **assigns** them to
Python rather than leaving them unassigned.

| # | Required per-instance record | Computed by existing in-repo code? | Evidence |
| --- | --- | --- | --- |
| H1 | **The original feasible optimum `f*` over that instance's own `F`** (with `X*`, the exact-equality optimal set) | **YES — as a self-contained one-instance resolver, NOT parameterized over instances.** `research/ground_truth/compute_g3_ground_truth.py` enumerates `F` and the full space and emits `f_star`, `X_star_size`, `X_star` (`…compute_g3_ground_truth.py:413-417`) plus `max_f_over_F` / `argmax_f_over_F` (`:418-419`). The **consumer** side is instance-parameterized only by *path*: `src/g6/trial_runner.py:440-451` loads the instance and the ground-truth file and requires the two authorities to agree. **Not found:** any module that takes an arbitrary instance and recomputes `f*` — the resolver's input is one hard-pinned file (`INSTANCE = …/research/canonical/stage1_instance.json` at `:42`; `EXPECTED_INSTANCE_SHA256` at `:48`, enforced by the fail-closed `load_instance` at `:81-98`). |
| H2 | **`Lambda_ref` recomputed from that instance's `F` and objective** | **YES — same script, same one-instance scope.** `Lambda_ref = f_F_max - f_star` (`…compute_g3_ground_truth.py:281`), emitted at `:424` with its rule string `D008_RULE_VERBATIM` (`:52-55`) and its D008 stop branch (`:294-298`). **Not found:** an instance-parameterized recomputation. `src/g4`/`src/g5`/`src/g6` only *consume* `Lambda_ref` as a frozen input — `src/g4/classification.py:41-58` (`OriginalObjectiveService`, which validates finiteness/positivity but never computes it), `src/g4/generate_ledger.py:76-78`, `src/g6/ledgers.py:138-147` (reads ADNYE-001 and asserts the G4 ledger's `lambda_ref_binary64_hex` matches), `src/g6/trial_runner.py:443-451`. |
| H3 | **The rebuilt D006/D008/D010 ledgers under the same frozen formulas and grid** | **YES — the closest existing analogue.** `src/g4/generate_ledger.py:70-135` builds the D006 coefficient ledger on the D010 box-derived grid (`q_min`/`q_max` from ADNYE-002 `rho_box`, `:79-84`; endpoint equality against the D010 record, `:99-102`; the D010 grid rule emitted at `:125`); `src/g6/ledgers.py:174-193` is the D006 r=1 mapping and `:288-323` the V-14 r=1 ledgers, both carrying the frozen one-operation transcript (`:317-320`). **The limiting fact is binding, not computational:** every input is pinned to the *one* accepted instance by file hash — `src/g6/ledgers.py:26-33` (the `*_SHA256` pin block) enforced at `:121-127`, and `src/g4/generate_ledger.py:71-75` refuses unresolved ADNYE records. **Not found:** a per-instance rebuild re-derivable from a supplied instance rather than from pinned single-instance artifacts. |
| H4 | **The new instance-specific provenance record for the above** | **PARTIAL.** Provenance *plumbing* exists and is well developed: `src/g6/ledgers.py:149-161` returns the `source_snapshot` hash map, `:247` writes it into every ledger payload, `:259` finalizes through `_finalize` (`:234-236`); downstream runners carry the same idea (`src/g6/d011_runner.py:402`, `:436-440`; `src/g6/g5_input.py:371-384`; `src/g5/core_pass.py:220`). **Not found:** a provenance record that ties *this instance's* `f*`, `Lambda_ref` and rebuilt D006/D008/D010 ledgers together as one per-instance package. The G3 ground truth does record an input-digest preimage list and `…compute_g3_ground_truth.py:355` binds the canonical instance digest — but that is instance #1's resolver provenance, not a per-instance package builder. |

**Net for this audit's question.** Four required per-instance records, of which
**none is a CUDA obligation** (amendment `:51-53` assigns them to Python) and
**none is absent as a computation** — every one of the four has in-repo code
that produces it today. The real deficiency is **scope, not existence**: this is
a *single-instance* pipeline whose instance is pinned by file digest, while
protocol §4 demands the per-accepted-instance generalization. That is a new work
package, not a new class.

**Ownership: WP5b (per-instance Python preparation), new.** WP5b builds, for each
accepted instance, the H1–H4 package: recompute `f*` and `Lambda_ref` from that
instance's own `F`/objective, rebuild the D006/D008/D010 ledgers under the
frozen formulas/grid, and emit one provenance record binding them. Two
consequences follow from texts already in force, and neither is a new ruling:

- **It is record-shaping, therefore bound into the production identity.** The
  owner's G10 decision is verbatim
  (`GATE_9_WP0_D013_CUDA_PATH_AND_IDENTITY_SCOPE_OWNER_DECISION.md:36-40`): the
  production source map is *"the 12 v1 §A files plus the new `+0.0` path plus
  every host-side file that shapes a scientific record: coordinate iterator,
  record writer, D016 reconstruction, the §B item 1/2 harnesses and the
  generation-binding code."* H1–H4 **are** generation-binding code — they are
  precisely the values the CUDA engine consumes as host-validated inputs
  (amendment `:53`). So WP5b is class **(a): host-side, bound into the production
  identity, qualified in the WP7 dry run** — not class (b), because it adds no
  device code and needs no §A of its own.
- **It does not make G5a, G5b or the §B-item-2 comparison a class (b) gap**, and
  it opens no class (c) item. It is a readiness prerequisite in the same sense as
  protocol `:166-171`: the engine cannot be handed host-validated inputs that do
  not yet exist for the instance in hand. It is listed here so the coverage
  record is complete, and it is registered in §6.

**Search basis for the table** (all four rows, re-read this round): directories
`research/ground_truth/`, `src/g4`, `src/g5`, `src/g6`, `research/g6`; patterns
`Lambda_ref`/`lambda_ref`, `f_star`/`optimum`, `D006`/`D008`/`D010`,
`provenance`. Absence claims are scoped to those directories and are stated as
*"not found"*, never as *"does not exist"*.

---

## 3. GAP CLASSIFICATION

### 3.0 The question that governs everything: what do the identity's "source hashes" cover?

The owner's item 3 requires this to be determined *before* classifying, and the
round-1 report got it wrong in a way the validator correctly refused: it
concluded "12 files, therefore class (a)" while simultaneously recording that the
identity is caller-driven and the scope "unresolved". Those two statements cannot
both carry a classification. The resolution is that **there are two different
identities**, and the approved texts are determinate about one and silent about
the other.

#### 3.0.1 The **qualification** identity's source map — DETERMINATE (12 files)

The accepted §A evidence is bound to exactly 12 files, and this is not an
inference — it is a closed, hash-verified set:

- The release's `source_sha256` has **exactly 12 keys**, programmatically
  verified this session to contain **zero `.md` files** and **zero `decisions/`
  paths**, with extensions only `{.py, .cu}`.
- That map is produced by `SOURCE_RELS` at
  `…stage2_cuda_core_corruption_qualification.py:48-53` = the 8 clean
  `SOURCE_RELS` (`…stage2_cuda_core_qualification.py:33-41`) plus 4
  harness/CLI/fixture files.
- The accepted receipt carries the **identical** 12-key `source_sha256`
  (`research/g9/kaggle_dry_run/GATE_9_KAGGLE_CORE_A_VERSION1_RECEIPT.json`; the
  two mappings compare equal this session), plus separately
  `core_release_sha256`, `clean_dry_run_receipt_sha256`,
  `execution_release_sha256`, `plan_content_sha256`, `compiler_flags`,
  `nvcc_version` and `runtime_build_observed` — all keyed to **code and
  platform**, not to the amendment text.
- **The amendment text is bound only in the dry-run release, under a different
  key**: `authorities`, not `source_sha256`
  (`GATE_9_CUDA_CORE_DRY_RUN_RELEASE.json` — its top-level keys are
  `{authorities, schema, source_sha256, status}`, and its `source_sha256` also
  contains no `.md`). That release is pinned by hash
  (`…corruption_qualification.py:36`), the corruption path verifies it
  (`:129-130`) and requires the receipt to bind it (`:157`).
- The owner acceptance restates the boundary in its own words
  (`GATE_9_CUDA_CORE_A_VERSION1_OWNER_ACCEPTANCE.md:50-53`):

> The qualification attempt is limited to the release's exact 12-file source
> map, eight numerical compiler flags, observed Tesla T4 / compute capability
> 7.5 / driver 13000 / CUDA runtime 12080 / `nvcc` 12.8.93 / Python 3.12.13 /
> NumPy 2.0.2 platform, and the content-addressed image above.

**Therefore, settled:** the *qualification* identity's source hashes cover
**exactly the 12 files listed in §1.1, all `.py`/`.cu`, and no text file at
all.** The amendment text is a *separate* authority, bound under a different key
in a different release.

#### 3.0.2 The **production** identity's source map — was NOT DETERMINATE in
#### round 2; now **DECIDED by the owner** (round 3)

For the record, this is what the approved texts left open, and why round 2 had to
make it a class (c) gap:

- `qualification_identity()` is **caller-driven, not a closed set**. At
  `…stage2_cuda_execution_contract.py:79-81`:

  ```
  _require(isinstance(source_sha256, Mapping) and source_sha256, "source hash map is required")
  sources = {str(key): _sha(value, f"source hash {key!r}") for key, value in sorted(source_sha256.items())}
  _require(all(key and not key.startswith("/") for key in sources), "source hash key is invalid")
  ```

  It accepts **any** non-empty mapping. Nothing in the qualified code fixes what
  that mapping contains.
- The owner acceptance **explicitly declined to settle it**
  (`GATE_9_CUDA_CORE_A_VERSION1_OWNER_ACCEPTANCE.md:66-68`):

  > No canonical `qualification_identity()` payload or hash is emitted by this
  > decision. **Source-map scope**, compiler-flag scope, and the future-session
  > pre-write image check remain unresolved.

- The closure plan confirms no production identity has been issued
  (`GATE_9_SECTION_B_CLOSURE_PLAN_DRAFT.md:27`): *"**No production qualification
  identity issued.**"* And WP1 is the package that will define it
  (`:52`): *"**Production qualification identity.** Define the record from the v1
  §A evidence and the execution contract: source map, flags, platform fields,
  image fields labelled platform-reported."*

**The owner has now decided it** —
`GATE_9_WP0_D013_CUDA_PATH_AND_IDENTITY_SCOPE_OWNER_DECISION.md:36-43`, verbatim:

> 2. **Production identity scope (G10):** "Bind producer files".
>    - The production qualification identity's source map = the 12 v1 §A files
>      plus the new `+0.0` path plus every host-side file that shapes a scientific
>      record: coordinate iterator, record writer, D016 reconstruction, the §B
>      item 1/2 harnesses and the generation-binding code.
>    - Any change to any of them forces a new qualification before further
>      records.
>    - The production identity is qualified in the WP7 dry run.

**This is the "include the producer files" branch** — the one round 2's §3.2
labelled (b). It is now the settled scope, not a conditional. Three things follow
for this audit:

1. **Every host-side record-shaping gap in §3.3 is now class (b) in the §A
   sense** — each of those files must be *inside* the production identity and
   covered by *fresh qualification evidence* before any further record. That
   evidence is the WP7 dry run, which the owner has nominated.
2. **The gap is moved, not removed.** It does not disappear as a "class (b) gap
   requiring a source change" — it becomes a **bounded, decided, scheduled
   qualification obligation** carried by WP7. That is the honest form: WP1 issues
   the identity, WP7 qualifies it, and the identity is usable only after WP7.
3. **G5b is additionally class (b) on its own account**, because the new `+0.0`
   CUDA path is *new compiled device code* that must be qualified (§2.5) — it is
   not merely a file to be hashed.

**What this decision does NOT do:** it does not touch the 12 §A files. Every
v1 §A hash is unchanged and re-verified this session (§1.1, §9). The v1
qualification evidence remains valid as evidence **about the v1 engine**; what
changes is that production attestation is a *larger* set than v1's, and it is
qualified separately.

### 3.1 Gap G10 — RESOLVED: the production identity binds the producer files

G10 was the explicit class (c) gap of round 2, restated then as the question:

> **Does the production qualification identity's `source_sha256` include the new
> host-side producer files (the iterator, writer, comparator harness, WP4 writer,
> WP6 evaluator), or only the 12 §A files?**

**The owner answered: it includes them** (§3.0.2, quoting `:36-43`). So:

- **G10 is RESOLVED. There is no open class (c) gap in this report.**
- **Every host-side record-shaping gap (G1, G2, G3, G4, G6, G7, G8, G9, G12, and
  the M1–M7 commitment shape) is bound into the production identity and qualified
  in the WP7 dry run.**
- The specific files the owner enumerated are, by name: **coordinate iterator,
  record writer, D016 reconstruction, the §B item 1 and item 2 harnesses, and the
  generation-binding code** — plus **the new `+0.0` path**.
- **None of the 12 §A files changes.** This is unchanged from round 2 and remains
  true; it is re-verified byte-identical in §1.1 and §9.

The amendment's requalification trigger, quoted for completeness, is the rule
this decision now operates through
(`GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md:33-36`):

> A changed GPU model, compute capability, driver, runtime, compiler, image,
> source, or numeric-compiler flag requires a new qualification before any
> further record is written.

The owner's decision makes *"source"* in that trigger concrete for production:
the source set now includes the record-shaping host files, so **editing the
iterator, the writer, the reconstructor, either harness, or the generation
binding is a requalification event** — not a silent host-side change.

### 3.2 The classification rule that now applies (round 3)

**The conditional rule of round 2 is deleted.** It existed only because G10 was
undecided; it is decided, so every gap in §3.3 carries a single, unconditioned
class:

> **Rule.** A gap is **(a)** if it is *purely* new host-side code that is bound
> into the production identity and covered by the WP7 dry-run qualification.
> A gap is **(b)** if, in addition, it needs *fresh §A evidence of its own* —
> because it is new **device** code, or because it would change a qualified §A
> file. A gap is **(c)** only if the approved texts and the owner records still
> leave it genuinely open, and then it is quoted.

On the **qualification** identity's scope, the analysis is unchanged and still
determinate: it is the closed 12-file set (§3.0.1), so v1's §A evidence attests
the engine and nothing else. On the **production** identity, the scope is now
fixed by owner decision (§3.0.2).

### 3.3 Gap register (round-3 classes — unconditioned)

G10 is decided (§3.1), so **no class below is conditional**. Per §3.2: **(a)**
= new host-side code bound into the production identity and covered by the WP7
dry run; **(b)** = additionally needs fresh §A evidence of its own (new device
code, or a change to a qualified §A file).

| ID | Gap | Class | Evidence |
| --- | --- | --- | --- |
| **G5b** | **CUDA `+0.0` capability: the amendment requires a bit-for-bit CUDA comparison including the inactive `+0.0` families, but v1's ABI refuses them at the boundary. Needs a new additive CUDA path and its own §A corruption qualification (incl. `+0.0` and slack-register cases).** | **(b) — UNCONDITIONAL** | amendment `:84-86` (*"including their inactive `+0.0` families"*), `:57-59` and `:134-136` (CUDA produces the records); v1 refuses at `…core_bridge.cu:29` and `…stream_engine.py:274-275`; owner decision `GATE_9_WP0_D013_CUDA_PATH_AND_IDENTITY_SCOPE_OWNER_DECISION.md:26-35` |
| G1 | Per-coordinate 3-D iterator + record writer absent from the qualified map | **(a)** — bound into the production identity; qualified in WP7 | `…execution_contract.py:6-7`; `…stream_engine.py:847-848`; contract partitions but nothing fills it (`:112,:147,:170`) |
| G2 | D016 reconstruction/label builder not in the map | **(a)** — bound into the production identity; qualified in WP7 | v1 disclaims: `…stream_engine.py:39`; existing code `…cuda_qualification/stage2_cuda_reconstruct.py:25,134-143,198,279` is **outside** the 12 (verified) |
| G3 | `c_f` comparator dimension is out-of-map (implemented, not missing) | **(a)** — bound into the production identity; qualified in WP7 | `…stage2_cuda_reconstruct.py:25,198`; `src/g4/classification.py:46,75`; out-of-map per §3.3 G2 |
| G4 | D013 C/CB/CS/CSB per-condition grids not implemented | **(a)** — bound into the production identity; qualified in WP7 | `DECISIONS.md:1109-1112`; protocol `:162`; no implementing module found |
| G5a | WP6 Python `+0.0` evaluator — **the canonical reference** for G5b. Absent; **spec closed** by owner. | **(a)** — bound into the production identity; qualified in WP7 | `src/g5/domains.py:6-8`; `GATE_9_D013_INACTIVE_EVALUATOR_SPEC_OWNER_DECISION.md:27-37`; closure plan `:32` *"No implementation found"* |
| G6 | V-14 0.5x/2x coordinate→coefficient resolution outside the map | **(a)** — bound into the production identity; qualified in WP7 | axes `src/g6/ledgers.py:290-291`; v1 has no coordinate space (§2.2.2) |
| G7 | Production writer: atomic staging/promotion, manifests, resume, exact-cover audit | **(a)** — bound into the production identity; qualified in WP7 | `…execution_contract.py:148-149` *"a future writer owns atomic I/O"*; amendment `:118-128` |
| G8 | §B item 1 pre-write identity recheck harness | **(a)** — bound into the production identity; qualified in WP7 | closure plan `:53`; amendment `:76-77`; contract validates but nothing invokes it pre-write |
| G9 | §B item 2 in-session full-domain comparison harness **and the §B item 3 session output (pass/fail counters, platform/source identities, validation digest)** — record 16 of §2.2 | **(a)** — bound into the production identity; qualified in WP7 | closure plan `:54`; **amendment `:78-90` (§B items 2 and 3)**; comparison logic exists engine-level, no per-session driver or output writer |
| G12 | **D013 companion package (D011 + V-14 0.5x/2x) for each fired condition** | **(a)** — bound into the production identity; qualified in WP7 | **protocol `:162-163`** (row 14 of §2.2); no per-condition subgrid/expansion iterator exists |
| **G10** | ~~Production identity's source-map scope~~ — **RESOLVED by the owner: "Bind producer files".** Not an open item. | **resolved** | `GATE_9_WP0_D013_CUDA_PATH_AND_IDENTITY_SCOPE_OWNER_DECISION.md:36-43`, quoted at §3.0.2 |

**Withdrawn from round 1:** G11 ("v1 cap of 2 coefficient records vs 4 D013
conditions") is **withdrawn as a class (c) item**. The protocol settles the
record list — *"all and only `{C, CB, CS, CSB}` run"*, each with its D011 and V-14
package (protocol `:161-163`) — and the 2-record cap is a caller-loop concern, not
an owner decision (§2.2.3). It is now tracked as part of G4, not as an open
(c) item.

**Withdrawn from round 2 (this round), and why:**

- **The conditional apparatus.** Round 2 marked every class cell *"(a)/(b) per
  §3.2"*, with §3.2 spelling out two branches of an open question. **G10 is
  decided** (§3.0.2), so the second branch is the actual answer and the first is
  moot. All cells now carry a single class.
- **"No unconditional class (b) gap found."** Round 2's summary table and both
  standing-question answers asserted this. **It is withdrawn: it is false.**
  **G5b is an unconditional class (b) gap** — a fired D013 branch's records are
  produced by CUDA (amendment `:57-59`, `:134-136`) and compared by CUDA
  (`:84-86`), while v1's ABI hard-refuses the `+0.0` families
  (`…core_bridge.cu:29`). Round 2's own conditional framing also obscured this by
  tying G5 to the *host-file* scope question, which has nothing to do with a
  device-side refusal.
- **"G5 is (a)/(b) per §3.2."** Withdrawn and replaced by G5a (a) and G5b (b),
  per the amendment text quoted at §2.2.4.

**Explicitly NOT a gap, and the strongest finding in this audit:** no production
need surfaced that only **v2** meets. The two structural facts that might have
forced v2 — a coordinate space and D016 production — are **not** engine features
v1 lacks in a way v2 provides; both are explicitly **host-side responsibilities**
under the amendment (`:51-56`). v1's §A coverage is on exactly the properties
that matter numerically. **v1 remains a sound basis, and the owner's provisional
v1 choice holds on this evidence** — and the owner's new decisions take v1's
side explicitly, by keeping all 12 files byte-identical and building `+0.0`
alongside rather than modifying v1 (§2.5).

---

## 4. §B ITEM 2 SESSION COST

### 4.1 Comparison count, from the quoted approved text

Counted from the amendment quotation in §2.0 (`:78-87`). The **comparison unit**
is fixed by the clause's own words: *"for both encodings at every fixed
validation coordinate … under every D015 comparator pair"* (`:78-80`), and
*"Every comparison includes energy-minimum words, canonical minimum index, tie
flags, and D015/D016 reconstruction"* (`:86-87`).

**The last column is new in round 3** (ruling 1). It names, for **every row**, the
four fields amendment `:86-87` requires that comparison to include: **energy-
minimum words, canonical minimum index, tie flags, and D015/D016 reconstruction**.
A row is a *comparison* if it produces a coordinate the session compares; every
row below is one, so **every** row carries all four fields. §2.2.0 gives what
each field needs from v1 (three are engine capabilities; the reconstruction is
host-side and out-of-map).

| Set | Coordinates | D015 pairs | Encodings | Comparisons | Required fields per comparison (`:86-87`) |
| --- | --- | --- | --- | --- | --- |
| Primary `(30,30,30)`, `r ∈ {0.5,1,2}` (`:80`) | 3 | 5 | 2 | 30 | energy-minimum words; canonical minimum index; tie flags; D015/D016 reconstruction |
| D011 `(6,6,6)` on the 13³ subgrid (`:81`) | 1 | 5 | 2 | 10 | all four |
| V-14 0.5x `(0,0,0)`,`(15,15,15)`,`(30,30,30)`,`(30,0,15)` (`:82`) | 4 | 5 | 2 | 40 | all four |
| V-14 2x `(0,0,0)`,`(55,55,55)`,`(110,110,110)`,`(110,0,55)` (`:82-83`) | 4 | 5 | 2 | 40 | all four |
| **Subtotal, D013 unfired** | **12 coordinate-rows** | | | **120** | all four |
| D013 repeat: `C`,`CB`,`CS`,`CSB` at primary `(30,30,30)` (`:83-85`) | +4 | 5 | 2 | +40 | all four |
| **Total, D013 fired** | **16 coordinate-rows** | | | **160** | all four |

**On top of the comparisons, §B item 3 requires the session to write three
things** (`:88-89`): the **pass/fail counters**, the **platform/source
identities**, and the **canonical validation digest** — and *"retains no
unapproved coordinate-level scientific values in the qualification record"*
(`:89-90`). Those are **outputs, not comparisons**, so they are not in the 120/160
count, but they are a required deliverable per session and are covered by record
16 of §2.2 and gap **G9**. Round 2 listed only the counters; the
**platform/source identities** are added here explicitly (ruling 1).

**The D013 repeat is +40 comparisons, not +400.** The reason is in the quoted
text: *"repeat this full-domain comparison **at primary `(30,30,30)`** for each
of `C`, `CB`, `CS`, and `CSB`"* (`:84-85`). The repeated unit is the **primary
coordinate** under four conditions — not the whole coordinate list. 4 conditions
× 5 D015 pairs × 2 encodings = **40**.

**The `+0.0` inactive families are inside those four conditions**
(*"for each of `C`, `CB`, `CS`, and `CSB`, **including their inactive `+0.0`
families**"*, `:85-86`), so they are not an extra enumerated set of coordinates.
**Their number of comparisons is still not determined** — the WP6 evaluator
(G5a) does not exist. But the *class* of that gap is no longer open: because the
comparison is a **CUDA** comparison and v1's CUDA ABI refuses the `+0.0` families
(`…core_bridge.cu:29`), satisfying these rows requires the **new additive CUDA
path of G5b**, which needs its own §A qualification. This is why WP3 depends on
WP6 (closure plan `:54`) **and** on the new path, and why the count above is a
floor: the +40 assumes a working `+0.0` CUDA path exists.

#### 4.1.1 Negative result: no approved text puts D011/V-14 coordinates in the repeat

Ruling 4 required this to be checked rather than assumed. I searched the approved
texts for any requirement that the D013 repeat cover the D011 or V-14
coordinates, and **found none**:

- The amendment's repeat clause (`:84-85`) names **only** `primary (30,30,30)`
  and the four conditions. It does not enumerate D011 or V-14 coordinates.
- The protocol's D013 clause (`:162-163`) requires the D011 and V-14 **package**
  to *run* for a fired branch — that is a **record-production** requirement
  (row 14 of §2.2), and the amendment says the repeat happens *"immediately
  before its CUDA ranges run"* (`:84`), i.e. it is a **pre-range validation**
  scoped to what the ranges produce.
- The amendment's own coordinate list (`:78-83`) is introduced as *"every fixed
  validation coordinate **the session may produce**"* (`:79`) — the D013 ranges
  produce D011 and V-14 records, so those coordinates are *already* covered by
  rows 4–6 of the base list. Repeating them under the four D013 conditions is
  **not required by any text I could find.**

**So the round-1 count of +40 stands, and the validator's +400 is not supported
by the approved text.** I record the distinction explicitly because it is
material: a +400 count would have tripled the session estimate and, on the
pessimistic reference figure, pushed the session past the operator's 8400 s
timeout — a materially different production risk. **D013 companion records
(§2.2 row 14) are a real gap (G12); D013 companion *comparisons* are not a
requirement any approved text imposes.** If the owner intends the repeat to
cover the companion coordinates too, that is a new amendment, not a reading of
this one.

### 4.2 Reference time

The closure plan states ~**290 s per coordinate-row with both encodings**,
measured under load (`GATE_9_SECTION_B_CLOSURE_PLAN_DRAFT.md:54`).

**A better in-repo figure exists, and it is a measurement, not an estimate.** The
Gate-5 named-point provenance record gives a real timing breakdown for the same
pure-Python reference at primary `r=1`, ledger `(30,30,30)`, both encodings
(`research/g5/G5_NAMED_POINT_PROVENANCE.md:56-61`):

| Stage | Seconds |
| --- | --- |
| cache construction | `36.01929983700393` |
| shared domain preparation | `493.11830889599514` |
| **certification of both encodings** | **`6.045925683982205`** |
| harness total | `535.8438778679993` |
| external wall time | `8:56.80` |

**How these relate.** The 493 s domain preparation is **one-time and cached**,
reused across the whole grid (`src/g5/domains.py:1-8`). So a session pays it
**once**:

```
warm-cache, D013 unfired: 493.12 + 6.046 x 12 = 565.7 s ≈ 9.4 min
warm-cache, D013 fired:   493.12 + 6.046 x 16 = 589.9 s ≈ 9.8 min
plan figure,  D013 unfired: 290 x 12         = 3480 s ≈ 58 min
plan figure,  D013 fired:   290 x 16         = 4640 s ≈ 77 min
plan figure + one-time prep, fired: 290x16+493 = 5133 s ≈ 86 min
```

Against the plan's 290 s/row figure, 12 rows = 3,480 s ≈ 58 min and 16 rows =
4,640 s ≈ 77 min, which is where the plan's *"about an hour per session"* (`:54`)
comes from.

**The two are not in conflict but they are not interchangeable.** The 6.05 s
figure is a *warm, cache-amortized* measurement at one point; 290 s/row is a plan
estimate that embeds per-row record construction and the cost of a session that
cannot rely on a warm cache. **Which figure governs the production session is not
determined** — it depends on whether the domain cache survives across coordinate
rows inside one Kaggle session, which no in-repo source settles. WP3 must measure
it (closure plan `:54`, `:68-70`).

**Honest range: roughly 10 minutes if the cache is warm, up to ~1.3 hours if the
290 s/row figure holds.** The two differ by ~7×, so WP3's measurement is not a
formality.

### 4.3 Kaggle GPU session limits — UNKNOWN

**No in-repo source states a Kaggle GPU session time limit.** The repo names it
without a value (*"the only ceiling is Kaggle's own session limit"*, `research/g9/kaggle_dry_run/GATE_9_CUDA_IMAGE_CHANNEL_PROBE_OWNER_DECISION_DRAFT.md:89-90`),
and records Kaggle session termination as *"operationally expected"*
(amendment `:118`).

Two numeric ceilings do appear in-repo, and both are **operator-chosen CLI
timeouts for specific pushes, not platform limits**:
- `-t 8400` — `research/g9/kaggle_dry_run/GATE_9_CUDA_CORE_A_BUNDLE_DRAFT.md:122-124`,
  where the text itself says *"The `-t 8400` session cap leaves a cleanup window
  beyond the CLI's 7200-second launch cap."*
- `-t 3600` — **withdrawn.** Round 1 cited
  `GPU_DRY_RUN_V3_RELEASE_DRAFT.md:74`; **that file does not exist in this copy**
  (§1.4). The claim is unsupported and is not carried forward.

The 14,400 s "4 h" figure (`research/g6/cuda_qualification/v14_batch_contract.py:59`,
comment: `# 4 h Colab session budget the target stays below`) is a **Colab**
planning budget, not Kaggle's.

**Comparison: not possible.** The closure plan's risk note that the WP3 reference
cost *"may approach the GPU-session limit"* (`:68-70`) is **unresolvable against
in-repo evidence**. Against the only *in-repo* numeric figure (the 8400 s operator
timeout), both the warm-cache (~600 s) and pessimistic (~4640–5133 s) estimates
fit under 8400 s. That is a statement about one operator's chosen timeout, not
about Kaggle's limit, and should not be read as headroom.

---

## 5. COMMITMENT REQUIREMENTS (sampling deferred — what must be FIXED BEFORE PRODUCTION)

The owner deferred the sampling *implementation*. That does **not** remove the
commitment *shape*, because the commitment is what makes a later audit
meaningful, and several of its requirements are **ordering constraints on the
write path** that cannot be retrofitted.

### 5.1 The retrofit test used in this section

Ruling 5 requires a single test to be applied to every item, so that the
MUST/CAN split is principled rather than a matter of taste. The test is:

> **Can this be added after the production write and still bind the same
> evidence?** If yes → CAN-ADD-LATER. If no, because its value is a function of
> results that must already exist, or because it fixes an *ordering* that the
> write has already consumed → MUST-FIX-BEFORE-PRODUCTION.

The decisive mechanism is the **ordering**, and it is load-bearing in two
independent places:

1. **The commitment must precede the beacon round.** The anti-backdating
   guarantee is enforced by `_order_verified` in
   `research/g9/stage2_timestamp_witness.py:706-797`, whose decisive check is at
   **`:776-778`**:

   ```
   _require(round_publication_time > latest,
            f"the round is published at {round_publication_time}, not strictly "
            f"after the latest witness bound {latest}; backdating is not excluded")
   ```

   `latest` is the max `timestamp_latest` over verified witnesses from distinct
   signing keys (`…stage2_timestamp_witness.py:775`, with the key-distinctness
   and single-subject requirements at `:763-773`).

2. **The verifier pins the root recorded *before* the nonce was drawn.**
   `verify_sample` requires `recomputed_root == pinned_merkle_root`, where
   `pinned_merkle_root` is *"the root the owner recorded from the published,
   timestamped commitment BEFORE drawing the nonce"*
   (`research/g9/stage2_sampled_verification.py:557-558`), enforced at
   **`:622-625`**:

   ```
   _require(recomputed_root == pinned_merkle_root,
            "the commitment does not match the root pinned before the nonce was drawn")
   ```

**If results are written and only later committed, the root is a function of
results and the ordering is unrecoverable.** That is why the items below are
must-fix rather than nice-to-have.

### 5.2 MUST-FIX BEFORE PRODUCTION

| # | Requirement | Why it cannot be added later (retrofit test) | Evidence |
| --- | --- | --- | --- |
| M1 | **Canonical committable per-coordinate record form.** Every point expressible as a 2-tuple `(coordinates, result)` with an **exact declared field schema** of `int`/`bool`/`str`/`binary64`. | The leaf hash is over the canonical encoding of exactly that pair, with both halves length-prefixed; a record shape invented after the write cannot retroactively commit, and a mismatched shape will not build the commitment at all. | `…sampled_verification.py:206-215`; adapter `…stage2_commitment_adapter.py:54-58`, `:77-79` (schema field-type check), `:122-129` (record must be exactly `{coordinates, result}`) |
| M2 | **A per-instance commitment root sealed at write time**, covering **every** point (not a sample), plus a second root over the ordered coordinate list. | Backdating is only excluded if the root precedes the nonce (`:557-558`, `:622-625`). Sealing after results exist is circular — the root is a function of the very results it is supposed to pre-commit. | `…sampled_verification.py:269-283` (coordinate root), `:286` (`build_commitment`) |
| M3 | **An external timestamp of that root before any beacon round.** | `_order_verified` requires ≥2 **distinct signing keys** and the round strictly after the latest witness; a witness obtained after the round is not a witness of anything. There is no retroactive path. | `…stage2_timestamp_witness.py:775-778`; `require_round_after_witnesses` `:804-809`; `MINIMUM_AUTHORITIES = 2` at `:56` |
| **M7** | **The beacon chain choice AND the round-selection rule, plus the pin attestation — all three fixed before the round exists.** *(promoted from round-1 L3; see §5.3.)* | The round is a **deterministic function of a frozen policy and an attested pin timestamp**, and cannot be supplied by the caller. If the chain or the policy is chosen *after* a round has been observed, the producer **grinds rounds** — re-pinning until the sample misses the bad points — and the audit is theatre. The module's own revision history records exactly this failure: r1's `expected_round` was a free argument *"so any round could be substituted"*, and a backdated pin *"selects an ALREADY-PUBLISHED round whose randomness has been public for years, so the producer can compute the nonce before designing the result set"*. | `…stage2_beacon_nonce.py:47-53` (r1 findings), `:168-177` (pin attestation, verbatim), `:210-226` (`select_round`), `:229-246` (`bind_beacon`, r2 finding that the round is now computed internally and cannot be supplied), `:245-246` (round must be unpublished at pin time); schema `…stage2_beacon_nonce.py:79` is `/v3` |
| M4 | **Pinned descriptor + result schema, hashed, and the binding digest pinned — not the inner Merkle root.** | The adapter is explicit: *"future timestamp/beacon integration must pin THIS binding, not just its inner Merkle root."* A root pinned without its schema is not reproducible if the schema is revised later. | `…stage2_commitment_adapter.py:63-65`, `:158-167` |
| M5 | **Retain per-point values a verifier would need** — the full ordered leaf list, ordered coordinates, and coordinate-distinctness — not just aggregates. | `verify_sample` recomputes the root from the **leaf list** and re-derives coordinate distinctness itself. A producer retaining only aggregates cannot be audited, and *"skipped domain"* is undetectable without the leaf list. | `…sampled_verification.py:592-601` (leaf list, coordinate/leaf agreement, grid-point count), `:603-611` (distinctness, re-derived), `:619-621` (root recomputation); amendment draft `:156-158` |
| M6 | **Commit over the ordered coordinate roster supplied independently**, and refuse a roster whose root does not match. | Without the coordinate root the coordinates are hashed inside leaves and the verifier supplies them at check time — the module calls that *"circular"*. The roster must be known before the write, or the anti-reordering property is unverifiable. | `…sampled_verification.py:269-274`; `…stage2_commitment_adapter.py:114-118` |

**M1–M7 form one ordered chain:** record form (M1) → root sealed over the
roster (M2, M6) → external timestamp of that root (M3) → chain + round-selection
policy + pin fixed (M7) → beacon response bound (M7) → sample drawn → verified
against the pinned root (M5). **Every link is a before-the-write constraint. The
chain cannot be assembled after a production write without re-running the
campaign.**

### 5.3 What moved from CAN-ADD-LATER to MUST-FIX, and why (ruling 5)

Round 1 listed as **L3**: *"Drand chain choice, round selection, beacon response
retention and the externally-attested signature check."* Ruling 5 holds that the
chain and the round-selection rule (and the commitment + timestamp ordering that
precedes the round) cannot be deferred, because deferring them lets a producer
grind the round and adapt the sample. **Accepted, and the evidence is stronger
than the ruling states** — the module documents the exact attack and the exact
repair:

- The attack: *"A backdated pin timestamp selects an ALREADY-PUBLISHED round
  whose randomness has been public for years, so the producer can compute the
  nonce before designing the result set and the owner can pick the round -- both
  audits become theatre at once, and the resulting evidence looks flawless. That
  was the most serious finding against r1"*
  (`…stage2_beacon_nonce.py:168-177`).
- The other direction, stated in the module's own words: *"An owner who wants to
  pass a run they know to be corrupt can redraw a self-chosen nonce until the
  audit misses the bad points"* (`…stage2_beacon_nonce.py:28-32`).
- The repair: the round is now *"a deterministic function of a frozen policy and
  an attested pin timestamp, and cannot be supplied by the caller"*
  (`…stage2_beacon_nonce.py:376-377`; the mechanism at `:229-246`), and the
  selected round is required to be **unpublished at pin time** (`:245-246`).

**The dependency is structural, not cosmetic:** the chain choice determines
`period_seconds` and `genesis_time`, which `select_round` consumes
(`:210-226`) to compute the round, and `publication_time` (`:194-207`) uses to
prove the round was not already published. **A chain chosen after the round
exists has no attested pin to select against** — there is no valid `bind_beacon`
call to make. So M7 is not merely "better done early"; it is **unavailable
later**.

**Split of the old L3, stated precisely:**

| Component | New home | Reason |
| --- | --- | --- |
| Chain choice (which drand scheme) | **M7 — MUST-FIX** | Determines period/genesis; no attested pin can select a round without it |
| Round-selection rule (policy + pin attestation) | **M7 — MUST-FIX** | `select_round` is a pure function of policy+pin; deferring = free round choice |
| Beacon response **retention** (keeping the fetched record) | **M7 — MUST-FIX** | `recheck_beacon_record` re-derives the round *from the record's own policy and pin* (`:321-341`); a record that was not retained cannot be re-derived later, and an auditor who cannot re-derive the round cannot check it was policy-derived (r1 finding, `:52`) |
| Externally-attested BLS signature check | **L6 (can wait)** | It is a *verification* the module structurally cannot do — the attestation is *"trusted, not checked"* (amendment draft `:80-84`; `…stage2_beacon_nonce.py:360-362`). It is an audit-time act by a third party, not a producer-side ordering constraint. Choosing to defer *verification* does not let a producer steer anything, because by then the round is already fixed by M7. |

### 5.4 CAN-ADD-LATER — every item re-tested against §5.1

| # | Item | Retrofit test result — why it can wait |
| --- | --- | --- |
| L1 | The **sampling/challenge/verify driver** (`derive_challenge`, `verify_sample`, beacon client). | **Passes.** It is a pure *reader* of an already-sealed commitment and an already-bound beacon. Adding it later changes no ordering and binds no prior value. The mechanism is separable and already fixture-tested. |
| L2 | **Sample floor / corruption model / confidence target.** | **Passes.** A function of the *policy*, chosen at challenge time, not of the results. Round 1's evidence stands and is re-verified: 2,000 of 680,943 records catch one bad record with probability exactly `2000/680943` ≈ 0.29371% (`GATE_9_CONCLUSION_VERIFICATION_MAPPING_DRAFT.md:29-31`); a 99% guarantee needs 674,134 (amendment draft `:106-110`). Choosing a floor before the mapping is settled would be arbitrary. |
| L4 | **Per-family statistical policy.** | **Passes.** A reporting/aggregation choice over five already-written instance records. Per-instance figures are explicitly *not* family-wide and the union bound yields only ≥95% across five instances (amendment draft `:119-127`). |
| L5 | **Independent post-write `recheck_record` audit of a verification record.** | **Passes — and this one was re-checked hardest**, because round 1's phrasing ("it operates on records, not on the producer's write path") was an assertion rather than a citation. Verified: `recheck_record` (`:678-698`) *"audits the CHALLENGE ONLY"* and *"cannot confirm the results were recomputed correctly"*; it re-derives the challenge **from the commitment** (`:321-333` in the beacon module, and `recheck_record`'s docstring records the r3 defect where a forged record *"audited clean against a 680,943-point campaign"*). It therefore adds no ordering constraint: it runs strictly after, on retained evidence. |
| L6 | **The `py_ecc` venv / externally-attested BLS signature verification.** | **Passes.** See §5.3 — it is a third-party verification act at audit time, not a producer-side ordering constraint. Deferring it does not let a producer choose or grind the round, because M7 has already fixed both. |
| L7 | ~~Drand chain choice / round selection / beacon retention~~ | **PROMOTED to M7** (§5.3). Removed from this list. |

### 5.5 A caveat that applies to the whole section

Items M1–M7 are derived from modules that the sampled amendment describes as
**DRAFT — NOT APPROVED** (`GATE_9_STAGE2_SAMPLED_VERIFICATION_AMENDMENT_DRAFT.md:3-6`:
*"**Status:** DRAFT — NOT APPROVED. No owner decision record exists for this
file."*), and that the provider-trust amendment explicitly leaves undecided: it
*"neither requires nor forbids sampled verification"* and *"establishes no
sample floor and no corruption model"*
(`GATE_9_SECTION_B_KAGGLE_PROVIDER_TRUST_AMENDMENT_DRAFT.md:72`).

So M1–M7 are **recommendations about a future option's feasibility**, not current
obligations. They are classified must-fix only in the conditional sense the owner
asked about: *if a sampled audit is ever wanted, these must have been fixed
before the production write, because the ordering is unrecoverable.* This
conditionality is **strongest for M7**, which is also the item whose deferral is
most tempting — the closure plan calls the beacon, the timestamp witness, the
commitment adapter, the drand chain choice and the `py_ecc` venv *"off the
critical path"* (`GATE_9_SECTION_B_CLOSURE_PLAN_DRAFT.md:19-21`). **That plan
note is correct about the audit layer and wrong about M3 and M7**: the *audit* is
optional, but the *ordering constraints* it depends on are set at write time.
Deferring the decision is fine; deferring the *fact of the ordering* is not
recoverable.

The provider-trust amendment also states plainly that owner-side recomputation of
sampled points is *"the only layer independent of the platform, and it is
partial"* (`:11`) — a further reason to fix the record form even though the audit
itself is deferred.

---

## 6. SUMMARY TABLE — (b) FIRST; no open (c) item

**There is no open class (c) gap.** G10 is resolved by the owner
(`GATE_9_WP0_D013_CUDA_PATH_AND_IDENTITY_SCOPE_OWNER_DECISION.md:36-43`), and no
new open question was found in this round; §7 records what remains *not
determined*, none of which requires an owner decision. **Exactly one gap is class
(b), and it is first below.**

| # | Gap | Class | WP | Blocks work? |
| --- | --- | --- | --- | --- |
| **G5b** | **CUDA `+0.0` capability for a fired D013 branch** — the amendment requires a bit-for-bit **CUDA** comparison *including the inactive `+0.0` families* (`:84-86`), but v1's ABI hard-refuses them (`…core_bridge.cu:29`). **Unconditional class (b).** Owner decided: **new additive CUDA path + its own §A corruption qualification** (incl. `+0.0` and slack-register cases), folded into the WP7 dry-run session. The 12 §A files stay byte-identical. | **(b)** | **new package off WP6, qualified in WP7** | **No for WP6 (G5a), but YES for WP7 and for any D013 pre-range comparison** — WP7's session must carry the new path's §A |
| G5a | WP6 Python `+0.0` evaluator — the canonical reference G5b must match bit for bit. Absent; **spec closed** by owner (`…SPEC_OWNER_DECISION.md:27-37`) | (a) — bound into the production identity; qualified in WP7 | WP6 | No — but a **protocol prerequisite before the first core pass** (protocol `:166-171`) |
| G1 | Per-coordinate 3-D iterator + record writer | (a) — bound into the production identity; qualified in WP7 | WP4 | No |
| G7 | Production writer: atomic promotion, manifests, resume, exact-cover audit | (a) — bound into the production identity; qualified in WP7 | WP4 | No |
| G2 | D016 reconstruction/label builder (host-side by design) | (a) — bound into the production identity; qualified in WP7 | WP4 | No |
| G3 | `c_f` comparator dimension — implemented out-of-map, not missing | (a) — bound into the production identity; qualified in WP7 | WP3 | No |
| G9 | §B item 2 in-session comparison harness **and §B item 3 session output** (pass/fail counters, **platform/source identities**, validation digest) | (a) — bound into the production identity; qualified in WP7 | WP3 | No |
| G8 | §B item 1 pre-write identity recheck harness | (a) — bound into the production identity; qualified in WP7 | WP2 | No |
| G4 | D013 C/CB/CS/CSB per-condition grids (4 calls) | (a) — bound into the production identity; qualified in WP7 | WP6 | No |
| G6 | V-14 0.5x/2x coordinate→coefficient resolution | (a) — bound into the production identity; qualified in WP7 | WP4 | No |
| G12 | **D013 companion package (D011 + V-14 0.5x/2x) per fired condition** | (a) — bound into the production identity; qualified in WP7 | WP6 | No |
| **WP5b** | **Host-produced per-instance inputs, protocol §4** (`:174-178`): the original feasible optimum `f*`, `Lambda_ref`, the rebuilt D006/D008/D010 ledgers, and the instance-specific provenance record (H1–H4, §2.4.1). **Python-owned by the approved amendment** (`:51-52`) — *host-side, not a CUDA-coverage item*. All four have in-repo code today; the gap is per-instance scope, since the production is pinned to a single instance by file digest. Record-shaping ⇒ inside the owner's G10 *"generation-binding code"* (`:36-40`). | **host-side, bound** — bound into the production identity; qualified in WP7 | **WP5b (new)** | No for the §B dry run; **YES as a prerequisite before any core pass on a given instance** — the engine cannot consume host-validated inputs that do not exist yet (cf. protocol `:166-171`) |
| M1–M7 | **Commitment shape + ordering** (record form, sealed root, external timestamp, pinned binding, retained per-point values, coordinate roster, **chain + round selection + pin**) | (a) — bound into the production identity; qualified in WP7 | WP4 | No — but must precede any future write |
| ~~G10~~ | ~~Production identity's source-map scope~~ — **RESOLVED: "Bind producer files"** (12 §A files + new `+0.0` path + every host-side record-shaping file; any change forces a new qualification; qualified in the WP7 dry run) | **resolved** | WP1 → WP7 | — |

**Round-2 statement withdrawn:** *"No unconditional class (b) gap found."* It is
**false**; **G5b is an unconditional class (b) gap** (§2.2.4, §3.3).

### Answers to the owner's standing questions

- **Is there a production need that only v2 meets?** **No.** Every gap is
  host-side work that the amendment assigns to the host in any case (`:51-56`),
  and none is a numerical capability v1 lacks. The one device-side gap (G5b) is
  addressed by a **new additive CUDA path**, not by v2 and not by editing v1.
  **The provisional v1 choice is supported by this audit**, and the owner's
  decisions take v1's side explicitly by keeping all 12 §A files byte-identical
  (§2.5, §1.1, §9).
- **Any gap requiring a source change or requalification before proceeding?**
  **Yes — exactly one, and it is class (b): G5b, the CUDA `+0.0` capability for a
  fired D013 branch.** The amendment requires a CUDA comparison *including the
  inactive `+0.0` families* (`:84-86`) and CUDA to be the producer of those
  records (`:57-59`, `:134-136`), while v1 refuses them at the ABI boundary
  (`…core_bridge.cu:29`, `…stream_engine.py:274-275`). It is resolved **not** by
  editing a qualified file (which the owner declined and which this report
  recommends against — a `+0.0` family *"must build a different,
  coefficient-dependent domain"*, `src/g5/domains.py:6-8`) but by a **new additive
  CUDA path with its own §A corruption qualification**, planned for the same
  Kaggle session as the WP7 dry run and still subject to separate owner push
  approval (`…OWNER_DECISION.md:26-35`).
  **The class (b) gap therefore does not invalidate v1's §A evidence and requires
  no change to any of the 12 §A files** — v1's engine qualification remains
  exactly as accepted (§1.1, §9). **There is no open (c) item**: G10 is resolved,
  and this round found no new one (§7 lists only "not determined" facts, none of
  which needs an owner decision).

---

## 7. NOT DETERMINED

Stated explicitly rather than guessed, per the owner's instruction not to
overclaim:

1. ~~**The production identity's source-map scope**~~ — **no longer open.**
   It was class (c) gap G10 and was **resolved by the owner on 2026-09-27**
   (`GATE_9_WP0_D013_CUDA_PATH_AND_IDENTITY_SCOPE_OWNER_DECISION.md:36-43`):
   the production source map binds the 12 §A files, the new `+0.0` path and every
   host-side record-shaping file, and is qualified in the WP7 dry run (§3.1).
2. The number of comparisons the D013 `+0.0` inactive families add — the WP6
   evaluator (G5a) does not exist. Its *specification* is closed by the owner's
   2026-09-27 decision, but the evaluator itself is absent. **(Not an open
   question for the owner: the class is settled — G5b is (b) — and the route is
   decided, so this is a build-size unknown, not a decision.)**
3. Whether the §B item 2 reference cost is the warm ~6.05 s/row or the 290 s/row
   figure — depends on cache survival across rows in one session.
4. Kaggle's GPU session time limit — **no in-repo source states it** (§4.3).
5. Whether any approved text intends the D013 **comparison** repeat to cover the
   companion coordinates — **searched and not found** (§4.1.1). The
   D013 companion **records** are required (protocol `:162-163`); the companion
   *comparisons* are not required by any text located.
6. Whether every V-14 2x coordinate has a D013-active-axis counterpart — depends
   on the WP6 evaluator's per-condition domain, specified but not implemented.
7. Whether the sampled-verification requirement (M1–M7) is ever adopted — the
   amendment is an unapproved draft and the provider-trust amendment is neutral.

**None of these requires an owner decision, so there is no open class (c) gap.**
Item 1 was the only (c) item and it is resolved; item 2 was the nearest
candidate and the round-3 analysis closed it too, because the amendment's
requirement is unconditional and its route is owner-decided (§2.2.4, §2.5) — the
residue is an implementation-size unknown, not a choice between options. No new
(c) item arose in this round.

---

## 8. CITATION VERIFICATION LEDGER — ROUND 3 (ruling 5)

Every citation **added or changed in round 3** was re-read in this project copy
this session. Round-2 citations that were not touched are covered by the §1.4
ledger and are not restated here.

| Citation | What the file actually says | Verdict |
| --- | --- | --- |
| `GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md:78-90` | The §B item 2 coordinate list, the *"Every comparison includes energy-minimum words, canonical minimum index, tie flags, and D015/D016 reconstruction"* sentence (`:86-87`), and item 3 *"write only the pass/fail counters, platform/source identities, and canonical validation digest"* (`:88-89`) with the no-retained-values clause (`:89-90`) | **OK** — quoted verbatim in §2.0 |
| `…CUDA_AMENDMENT_DRAFT.md:84-86` | *"immediately before its CUDA ranges run, repeat this full-domain comparison at primary `(30,30,30)` for each of `C`, `CB`, `CS`, and `CSB`, including their inactive `+0.0` families"* | **OK** — the basis for G5b being unconditional |
| `…CUDA_AMENDMENT_DRAFT.md:57-59` | *"Once validation passes, the CUDA engine is permitted to generate the primary and declared companion records for an accepted Stage-2 instance."* | **OK** — CUDA produces the records |
| `…CUDA_AMENDMENT_DRAFT.md:134-136` | *"It does not permit CPU and GPU records to be mixed without an explicit provenance field. The intended scientific producer for a completed family is one qualified CUDA backend."* | **OK** |
| `…CUDA_AMENDMENT_DRAFT.md:33-36` | The requalification trigger: *"A changed GPU model, compute capability, driver, runtime, compiler, image, source, or numeric-compiler flag requires a new qualification before any further record is written."* | **OK** |
| `…CUDA_AMENDMENT_DRAFT.md:51-56` | Python is canonical; CUDA consumes host-validated values; *"The host performs bounded reference checks and reconstructs declared records"* | **OK** — basis for the "not a v2 defect" finding |
| `…CUDA_AMENDMENT_DRAFT.md:111-116` | *"The original D013 exact-sign trigger remains mechanical and per-instance. A fired branch runs all and only the already-approved conditions once the separate `+0.0` inactive-family evaluator has passed its required validation… its `+0.0` evaluator validation must be available before any Stage-2 core pass starts."* | **OK** — re-read this session (round 2 cited `:112-116`; the sentence opens at `:111`, **corrected**) |
| `GATE_9_STAGE2_PROTOCOL_DRAFT.md:166-171` | *"Before the first Stage-2 primary core pass, the exact `+0.0` inactive-family evaluator required by a fired D013 branch must have its own reviewed non-scientific validation…"* | **OK** |
| `GATE_9_WP0_D013_CUDA_PATH_AND_IDENTITY_SCOPE_OWNER_DECISION.md:26-35` | Decision 1, *"New additive CUDA path"*, all four sub-points, quoted verbatim in §2.5 | **OK** |
| `…D013_CUDA_PATH…_OWNER_DECISION.md:36-43` | Decision 2, *"Bind producer files"*, all three sub-points, quoted verbatim in §3.0.2 | **OK** — resolves G10 |
| `…D013_CUDA_PATH…_OWNER_DECISION.md:10-19` | The owner's own recorded findings, incl. the v1 refusal at `…core_bridge.cu:29` / `…stream_engine.py:274-275` | **OK** — independently re-verified below |
| `…D013_INACTIVE_EVALUATOR_SPEC_OWNER_DECISION.md:27-37` | The three decisions: per-condition `F_q`/`f*_q`; *"Hard stop"*; `|T_E|` as `base × 2^w` with *"2 per inactive sector register (8 for all four sectors) and 11 for budget"* | **OK** — G5a spec |
| `…stage2_cuda_core_bridge.cu:29` | `return row.sector_slack > 0.0 && row.budget_slack > 0.0;` — inside `g9_coefficients_valid` (`:22-30`) | **OK** — re-read this session |
| `…stage2_cuda_core_bridge.cu:22-29, :71-73, :57-58` | The validator, its per-row enforcement loop, and the `0u` returns of `g9_core_run_v1` | **OK** |
| `…stage2_cuda_core_bridge.cu:44-45` | `offsetof(ScanResult, natural_minimum_checksum)`, `minimum`; `offsetof(ScanResult, minimum_index)`, `entries` | **OK** — canonical minimum index in the ABI layout |
| `…stage2_cuda_core_stream_engine.py:274-275` | `_require(record["sector_slack"] > 0.0 and record["budget_slack"] > 0.0, "active-CSB slack coefficients must be strictly positive")` in `coefficient_record` | **OK** — re-read |
| `…stage2_cuda_core_stream_engine.py:258-259` | The identical guard in the synthetic-row path | **OK** |
| `…stage2_cuda_core_stream_engine.py:39` | *"This component is **not** a record, classification or D016 producer…"* | **OK** — unchanged from round 2 |
| `…stage2_cuda_core_stream_engine.py:834-838` | *"Only BOUNDED summaries come back: per-stream minima, integer counters, and the compacted canonical tie entries… No full energy or flag stream is returned"* | **OK** — energy-minimum words |
| `…stage2_cuda_core_stream_engine.py:65, :462-480` | `CH_VALUES = (1024.0, 2048.0, 4096.0)`; `tie_flags` (`:462-480`) | **OK** — tie flags |
| `…stage2_cuda_core_stream_engine.py:50, :58, :297` | `ASSET_COUNT = 20`; `STATE_COUNT = 1 << DECODED_WIDTH`; `0 <= index < STATE_COUNT` in `canonical_bits` | **OK** — unchanged from round 2 |
| `…stage2_cuda_core_stream_engine.py:847-848` | `for slot, record in enumerate(records): for encoding in encodings:` — the loop over records handed in | **OK** — unchanged from round 2 |
| `…stage2_cuda_core_stream_engine.cu:234-248` | The device `tie_flags` (short-circuit, `4096.0 * kEpsilon`, then the three `c_H` bits) | **OK** — re-read this session |
| `…stage2_cuda_core_stream_engine.cu:253` | `if (index >= kStateCount) return;` | **OK** — unchanged from round 2 |
| `…stage2_cuda_execution_contract.py:79-81` | `qualification_identity` accepts any non-empty mapping — the caller-driven fact | **OK** |
| `…stage2_cuda_execution_contract.py:6-7, :112, :147, :170, :148-149` | The "neither exists in this module" sentence; `build_range_plan`; `complete_range_manifest`; `validate_final_manifests`; and *"a future writer owns atomic I/O"* (`:149`, inside the `:147-148` signature) | **OK** — `:148-149` re-read this session |
| `GATE_9_CUDA_CORE_A_VERSION1_OWNER_ACCEPTANCE.md:66-68` | *"No canonical `qualification_identity()` payload or hash is emitted by this decision. **Source-map scope**, compiler-flag scope, and the future-session pre-write image check remain unresolved."* | **OK** — the round-2 class (c) basis, now superseded by the owner's decision. (Round 2 cited `:67-68`; `:66` is *"No canonical…"*, so the fuller quote starts one line earlier. **Correction applied.**) |
| `GATE_9_CUDA_CORE_A_VERSION1_OWNER_ACCEPTANCE.md:50-53` | *"The qualification attempt is limited to the release's exact 12-file source map, eight numerical compiler flags, observed Tesla T4 / compute capability 7.5…"* | **OK** — unchanged from round 2 |
| `GATE_9_SECTION_B_CLOSURE_PLAN_DRAFT.md:30, :32, :52, :54, :57` | *"§B.1 recheck — No in-session harness"*; *"No implementation found; `src/g5/domains.py:127` deliberately refuses inactive families"*; the WP1 row; the WP3 row; the WP6 row | **OK** — `:30` and `:32` re-read this session |
| `src/g5/domains.py:6-8, :126-127, :296-304` | The three refusal statements, re-read | **OK** — re-read this session |

**One round-2 citation was corrected in passing:** `OWNER_ACCEPTANCE.md:67-68` →
`:66-68`, because the sentence *"Source-map scope … remain unresolved"* is
introduced by *"No canonical `qualification_identity()` payload or hash is emitted
by this decision"* at `:66`. The substance is unchanged and the gap it supported
(G10) is now resolved anyway.

**No citation added in round 3 is wrong.** The one defect found was in a
round-2 citation whose meaning was unaffected, and it is corrected above.

---

## 9. RE-VERIFICATION OF THE QUALIFIED v1 RELEASE (ruling 5)

The two release JSONs and the 12 §A files were re-hashed **after** this round's
edits, in this copy, to confirm the audit itself changed nothing qualified.

| Artifact | Result this session |
| --- | --- |
| `GATE_9_CUDA_CORE_CORRUPTION_QUALIFICATION_RELEASE.json` — all 12 `source_sha256` entries | **12/12 match** |
| `GATE_9_CUDA_CORE_DRY_RUN_RELEASE.json` — 8 `source_sha256` + 2 `authorities` | **10/10 match** |
| The 12 §A files on disk vs. the release | **byte-identical; unchanged** |

**Conclusion: the 12 qualified §A files are untouched by this audit and by the
owner's decisions, and must stay that way** (§2.5, §3.1). The new `+0.0` CUDA
path the owner ordered is additive and lives **outside** those 12.

---

**Report SHA-256 (body, i.e. all 102,744 bytes preceding this trailer):**
`1241e3966830b8066a3580a98e98162ca112b8b26aba4b5e4a816efac7ab93bd`

BUILD: DONE
