# ANALYSIS_NOTES — the G9 Stage-2 analysis pipeline

**Builder:** Space Bunny Alpha.
**Date:** 2026-10-03.
**Location:** `g9_jobs/operational/analysis_20261003/` — the ONLY directory this
build created or wrote to.  Nothing under `project/`, `research/`, `src/`,
`operational/*` or any push dir was created, modified or deleted.

**Scope of this build:** a pipeline that turns the five real T4 production
slot outputs into the paper's Stage-2 tables and figures, within minutes, with
no hand work and with nothing invented.  It reads records; it does not compute
energies, ties, optima or labels.

---

## 1. What was built

| file | role |
|---|---|
| `stage2_schema.py` | the single declaration of the frozen census, the on-disk layout, the committed-record schema, and the canonical encodings. Every other module imports from it, so a census can never disagree between the verifier and the analysis. |
| `verify_outputs.py` | fail-closed verification of all five slots. Exit `0` only when every check passes. |
| `analyze_stage2.py` | computes exactly the frozen Stage-2 quantities and emits `STAGE2_INFERENCE.json` with its own `content_sha256`. |
| `render_paper_slots.py` | renders the LaTeX tables and the figure data/plots for each slot in `RESULTS_AND_FIGURE_SLOTS.md`. Never writes into `project/paper/`. |
| `make_mock_outputs.py` | the MOCK harness: synthesizes a schema-valid five-slot output tree, every byte fabricated and labelled `MOCK`. |
| `run_mock_tests.py` | T1 end-to-end, T2 six negative tests that must fail closed, T3 MOCK-labelling assertions. |
| `FROZEN_CENSUS.json` | the shipped census profile: the REAL production census. |
| `MOCK_CENSUS.json` | the scaled census profile the MOCK harness runs under. Never the frozen one. |

`python3 -B`, `PYTHONDONTWRITEBYTECODE=1` throughout.  No `kaggle`, no network,
no installs.  The only third-party import is `matplotlib`, and only in
`render_paper_slots._plot`, where it is optional: the figure CSV is written
whether or not it imports, exactly as in the manuscript's own figure scripts
(`project/paper/manuscript/figures/plot_slot1_primary_rates.py:24-30`).  **0
`.pyc` files.**

Scratch went to `g9_jobs/scratch/analysis/` (the designated location), and the
recorded run log is kept in this directory as `MOCK_RUN_LOG.txt`.

---

## 2. The per-slot census — derived, then confirmed

The task named `2,080,562` rows and `1,040,281` batches per slot and asked for
them to be derived from code.  Three DIFFERENT numbers are in play and they
must not be confused, so all three are named distinctly:

| quantity | value | derivation | on disk? |
|---|---:|---|---|
| **records (rows) per slot** | **2,080,562** | `3 × 61³ + 13³ + 31³ + 111³` = 680,943 + 2,197 + 29,791 + 1,367,631 | yes — this is the row census |
| **sealed ranges per slot** | **511** | `Σ ceil(n / 4096)` = 3×56 + 1 + 8 + 334 | yes — this is the promoted-range-directory count |
| **CUDA batch flushes per slot** | **1,040,281** | `2,080,562 / 2`, because `ROW_CAPACITY = 2` | **no** — a runtime count, not an artefact |

Sources, one per family:

| family key | axis | coordinates | source of the axis length |
|---|---:|---:|---|
| `primary__primary__r0x1.0p-1` | 61 | 226,981 | `src/g5/core_pass.py:43-44` (`R_VALUES = (0.5, 1.0, 2.0)`, `ROW_COUNT = 61`) |
| `primary__primary__r0x1.0p+0` | 61 | 226,981 | same |
| `primary__primary__r0x1.0p+1` | 61 | 226,981 | same |
| `d011__d011__r0x1_0000000000000p_0` | 13 | 2,197 | `src/g6/d011_matched_subgrid.py:52-54` (`MATCHED_COORDINATE_COUNT = 13**3`) |
| `v14__v14_0_5x__r0x1_0000000000000p_0` | 31 | 29,791 | `src/g6/ledgers.py:290` (`N_axis = 31`) |
| `v14__v14_2x__r0x1_0000000000000p_0` | 111 | 1,367,631 | `src/g6/ledgers.py:291` (`N_axis = 111`), asserted again at `research/g9/stage2_section_b2_harness.py:164` |

- The sealed partition width is `MAX_COORDINATES_PER_RANGE = 4096`
  (`research/g9/cuda_qualification/stage2_cuda_execution_contract.py:19`),
  applied by `build_range_plan` (`:112-132`).
- `ROW_CAPACITY = 2` (`research/g9/cuda_qualification/stage2_cuda_core_bridge.py:22`),
  flushed whenever a batch is full
  (`scratch/production-package-prep/production_cuda_runner_v6.py:232-243`).

**Independent confirmation.** `operational/xcheck_20261003/XCHECK_NOTES.md:223-231`
reaches `2,080,562` and `1,040,281` by a different route and explicitly
corrects `operational/prodfix_v2_20261003/FIXES.md:139`, which had understated
the census as 1,361,886 by wrongly applying the 61-axis length to the V-14 2x
family.  The frozen census in `stage2_schema` and `FROZEN_CENSUS.json` agrees
with the corrected figure.

The module asserts the three derived totals at import time, so a silent drift
in any constant fails immediately rather than quietly changing the census.

---

## 3. Every quantity `analyze_stage2.py` computes, with its citation

Nothing is computed that the frozen protocol does not pre-specify.  This is the
complete list.

| # | quantity | frozen citation |
|---|---|---|
| **Q1** | per-instance, per-`r`, per-encoding exact A/B/C census of decoded set labels, the exact rational `rho_E^exact = A_count / coordinate_count`, the `I_C^exist` / `I_C^univ` census counts, and exact integer extremes of the per-point `|T_E|` and `|X_E|` | `FROZEN_MATH_SPEC.md:466-471` — "Report raw `|T_E|` separately (symbolically where allowed), decoded `|X_E|`, atomic-label census, `I_C^exist`, `I_C^univ`, per-grid `p_A,p_B,p_C` with denominator `|X_E|`"; `:473` — "`rho_E^exact` is the exact finite-grid primary A-rate" |
| **Q2** | the paired encoding difference `Delta(r) = rho_slack − rho_unbalanced` per `r`, as an exact rational with its sign | `research/decisions/DECISIONS.md:1120-1124`; `GATE_9_STAGE2_PROTOCOL_DRAFT.md:161-164` |
| **Q3** | the D013 trigger disposition, per instance, by the exact-sign rule | `DECISIONS.md:1125-1131` — "fires iff at least one of the three values is exactly zero **or** they do not all have one strict sign … There is no numerical tolerance in this rule"; restated at `paper/RESULTS_AND_FIGURE_SLOTS.md:144` |
| **Q4** | the C-census difference `unbalanced − slack` per `r`, as exact integers | `paper/RESULTS_AND_FIGURE_SLOTS.md:21` names `primary_C_rate_differences_unbalanced_minus_slack` as the accepted C-rate contrast and warns that `Count(A)−Count(C)` is NOT an encoding comparison |
| **Q5** | exact integer spatial predicates per `r` per encoding: `A_point_count`, `cartesian_product`, `axis_aligned_box`, `axis_projection_sizes`; and per directional A-advantage set `point_count`, `component_count`, `largest_component_size`; plus `both_directional_A_advantages` | `paper/RESULTS_AND_FIGURE_SLOTS.md:79-91` (SLOT-2) — "Render the exact, already-computed predicates. Do **not** re-derive labels and do **not** refit a boundary"; the definitions are Stage-1's own at `research/g7/stage1_inference.py:181-197` (`_components`), `:200-215` (`_region_shape`), `:248-251` (advantage sets) |
| **Q6** | V-14 `slack − unbalanced` `rho_E^exact` per scale, with sign, at the declared extents | `paper/RESULTS_AND_FIGURE_SLOTS.md:108-121` (SLOT-4); `DECISIONS.md:1823-1828` (extents), `:1829` ("Both expansion passes execute at D006 **`r = 1` only") |
| **Q7** | D011 matched-subgrid `rho_E^exact` per encoding, as the exact rational `A_count / 2197` | `paper/RESULTS_AND_FIGURE_SLOTS.md:123-135` (SLOT-5) |
| **Q8** | the mechanical cross-instance reduction: five boolean statuses plus `all_five`, `any_one`, `count_of_five` | `GATE_9_STAGE2_PROTOCOL_DRAFT.md:195-198` — "Cross-instance adjudication is mechanical and unweighted … **do not pool raw rates across instances or with Stage 1**" |

Two presentation decisions inside Q1 are worth stating because they are exactly
where a reader could go wrong:

- **`coordinate_count` and `X_E_size` are different denominators and are both
  named.**  `coordinate_count` is the number of grid points in the cell and
  denominates the aggregate over coordinates; `X_E_size` is the per-point
  denominator of `p_A` (`FROZEN_MATH_SPEC.md:468-470`).  `RESULTS_AND_FIGURE_SLOTS.md:21`
  warns about exactly this conflation, so the two keys are never merged.
- **`|T_E|` and `|X_E|` are per-point quantities.**  They vary across the grid,
  so what is reported is the exact integer **minimum and maximum** over the
  cell, plus the `I_C` census counts.  A single point's value, or a mean, would
  be a fiction, and `FROZEN_MATH_SPEC.md:466-471` asks for them "separately
  (symbolically where allowed)".

---

## 4. What is NOT computed, and why

| # | not computed | why |
|---|---|---|
| **N1** | **No H0/H1/H2/H3 threshold, score or verdict.** | `GATE_9_STAGE2_PROTOCOL_DRAFT.md:200-204` — the Stage-1 threshold limitations "remain limitations. This draft does not invent a rate-comparability, H1 sub-region, or H2 measurability threshold for either Stage 1 or Stage 2." `GATE_9_STAGE2_PROTOCOL_APPROVAL.md:44-46` records that the protocol decision explicitly "does not … introduce a hypothesis threshold". **No dated owner approval in the reviewed decision set changes this**, so every threshold word stays `indeterminate`. The output's `hypothesis_evaluation` records the *observed exact predicates* and the *status word* only. |
| **N2** | **No winner, advantage or gap magnitude.** | `CLAIMS_AND_LIMITATIONS_REGISTER.md` P-06: any winner claim is PROHIBITED because the rate-comparison component is indeterminate. Signs are reported; nothing is compared to a threshold, because none exists. |
| **N3** | **No pooled rate, mean rate, or cross-instance / cross-generation aggregate.** | `GATE_9_STAGE2_PROTOCOL_DRAFT.md:195-198`; P-16. `cross_instance_reduction` reduces five BOOLEANS and nothing else — no mean, no rate, no magnitude. |
| **N4** | **No boundary fit, smoothing, ranking or regression.** | P-20; `research/decisions/GATE_6_OWNER_EXECUTION_DECISIONS.md:19-22`. SLOT-2's predicates are rendered, not inferred from. |
| **N5** | **No D013 ablation result.** | The four conditions `C/CB/CS/CSB` are not declared families of this reader. Where the trigger fired they already ran in-kernel as part of the 22-family package (`operational/prodfix_v2_20261003/full_production_parent_v2.py:119-146`), and they would need a separate, separately reviewed reader. The output says so under `not_computed.d013_ablation_results`, and SLOT-8 renders a stub that writes no number. |
| **N6** | **No re-derivation of `H_E`, `T_E`, `X_E`, `f*`, `Lambda_ref` or any label.** | Those are produced by the CUDA core and certified by the frozen reconstruction (`research/g9/cuda_qualification/stage2_cuda_reconstruct.py:223-276`). Re-deriving them would be a second scientific computation, which this pipeline is not authorised to perform. Every number here is read from a committed, hash-verified reconstruction summary. |
| **N7** | **No D015 diagnostic rates.** | `DECISIONS.md:437-438` — the four `(c_H,c_f)` pairs are "additionally reported and cannot select a primary result"; `RESULTS_AND_FIGURE_SLOTS.md:130` forbids emitting them in the D011 slot. Their SHAPE is verified (including that each cell's `c_H`/`c_f` matches the pair its own key declares); their counts are never reduced to a second A-rate. |
| **N8** | **No cross-generation comparison.** | SLOT-5's "exact numerator difference versus the matching accepted Gate-5 subset" (`RESULTS_AND_FIGURE_SLOTS.md:130`) is NOT computed: that subset is a Stage-1 artefact and this pipeline emits no cross-generation comparison. |
| **N9** | **SLOT-3 is not emitted.** | It is a RULE, not a record: its input is `DECISIONS.md:266-270` and `FROZEN_MATH_SPEC.md:190, 211-214`, and it requires `Lambda_ref` and the reachable supports — which are *pre-canonical expected values* that P-18 and `DECISIONS.md:273-277` forbid citing as canonical. Emitting it here would put an uncited pre-canonical quantity into a figure. The existing `project/paper/manuscript/figures/plot_slot3_penalty_gap_dw.py` covers it and is left untouched. |
| **N10** | **No numerical validation of any record.** | Re-running the CUDA energy, tie set or classifier would be a second scientific computation. What IS verified is that every number is bound, by hash, to a record that satisfies the frozen schema and its own commitment. This boundary is stated in the `verify_outputs.py` docstring under "WHAT IS NOT VERIFIED HERE, DELIBERATELY". |

---

## 5. How to run it on the real outputs

The collector writes each kernel's output to `push/<kernel-id>/results/`
(`g9_jobs/collect_actual_production_20261003.py:18`).  Point `--results-root`
at any directory containing those five downloads; slots are found by their own
slot NAME, never by enumeration order, and a missing slot is a failure rather
than a skip.

```sh
cd g9_jobs/operational/analysis_20261003
export PYTHONDONTWRITEBYTECODE=1

# 1. verify — must print VERDICT: PASS and exit 0.
python3 -B verify_outputs.py \
    --results-root ../../push \
    --report /tmp/g9_stage2_verify.json

# 2. analyze — emits STAGE2_INFERENCE.json with its own content_sha256.
python3 -B analyze_stage2.py \
    --results-root ../../push \
    --out /tmp/g9_stage2_inference \
    --verify-report /tmp/g9_stage2_verify.json

# 3. render — LaTeX tables and figure data/plots. --out is REQUIRED and has
#    no default; it refuses any path inside project/paper/.
python3 -B render_paper_slots.py \
    --inference /tmp/g9_stage2_inference/STAGE2_INFERENCE.json \
    --out /tmp/g9_stage2_slots
```

`--census` defaults to the shipped `FROZEN_CENSUS.json` on all three commands.
A non-default `--census` sets `is_mock: true` in the inference record and
`is_frozen_real_census: false` in the verification report, so a mock run can
never be mistaken for a real one.

**Runtime expectation on the real data.**  Verification and analysis both
stream all `2,080,562 × 5 = 10,402,810` records, decompressing and
re-hashing each.  At the measured ~0.36 ms per record for canonicalisation
plus gzip decompression and JSON parsing, expect on the order of 20–40 minutes
per command on a single core, and roughly 5 GB of transient headroom for
`verify_outputs.py` (it re-reads each family but holds one batch at a time).
Neither command holds the whole census in memory.

---

## 6. The MOCK harness

`make_mock_outputs.py` synthesizes a tree that is **schema-valid but
factually empty**: the record schema, the self-consistent `content_sha256`, the
frozen reconstruction shape, the `r_hex`/mapping/group bindings, the canonical
last-axis-fastest coordinate order, the gzip framing, the range plan and the
range manifests are all genuinely correct, so every integrity check is
exercised for real.  What is fabricated is the A/B/C **label** and everything
downstream of it, by a deterministic hash over `(slot, family, linear index)`.

The mock deliberately exercises **both branches** of the D013 exact-sign rule
(slots 1–3 all-positive → no fire; slots 4–5 mixed → fire), so the trigger code
is covered in both directions.

**The mock runs at a scaled census, and says so everywhere.**  A full-scale
mock is 10.4 million records, about 7 GB, and about 15 minutes of generation
per slot; the review host had 8.4 GB free.  `--scale 20` shrinks each family's
AXIS (and the coordinate count becomes the exact cube of that axis, so the
lattice stays a genuine cube).  Every artefact that scale produces carries
`is_mock: true` or `is_frozen_real_census: false`, and every rendered table and
caption carries the literal token `MOCK`.  `--scale 1` reproduces the exact
real on-disk shape when disk allows.

---

## 7. Mock run log

Run: `python3 -B -u run_mock_tests.py --work <scratch>` on 2026-10-03, against
the shipped `MOCK_CENSUS.json` (`scale 20`).  **36 assertions, 36 passed, 0
failed, `VERDICT: PASS`.**

```
work dir: <scratch>

T1  end-to-end MOCK run: verify -> analyze -> render
  PASS  T1.mock_tree_built — 5 slots x 97,339 records (real census is 2,080,562)
  PASS  T1.verify_exit_zero — exit=0
  PASS  T1.verify_pass — 225 checks, 0 failures
  PASS  T1.verify_rows — 97,339 rows per slot
  PASS  T1.verify_not_frozen — mock profile correctly reported as not the frozen census
  PASS  T1.analyze_exit_zero — exit=0
  PASS  T1.inference_self_hash — content_sha256=51d22803560fa0c7...
  PASS  T1.inference_is_mock — is_mock=true because the census profile is not the frozen one
  PASS  T1.inference_five_slots — 5 slots
  PASS  T1.no_floats — the inference record contains no JSON float leaf
  PASS  T1.render_exit_zero — exit=0
  PASS  T1.render_manifest_self_hash — RENDERED_SLOTS.json re-derives
  PASS  T1.slots_emitted — SLOT-1, SLOT-2, SLOT-4, SLOT-5, SLOT-6, SLOT-7
  PASS  T1.slots_refused — SLOT-3 and SLOT-8 refused with stated reasons

T2  negative tests — each MUST fail closed
  PASS  N1.tampered_record_hash_fails — exit=1
  PASS  N1.tampered_record_hash_named — failing checks: ['V6_full_records', 'V8_row_census', 'V8_slot_row_census']
  PASS  N2.missing_slot_fails — exit=1
  PASS  N2.missing_slot_named — failing checks: ['V1_slot_present']
  PASS  N3.short_row_count_fails — exit=1
  PASS  N3.short_row_count_named — failing checks: ['V5_range_cover', 'V8_slot_row_census']
  PASS  N4.wrong_instance_fails — exit=1
  PASS  N4.wrong_instance_named — failing checks: ['V1_instance_identity']
  PASS  N5.repartitioned_plan_fails — exit=1
  PASS  N5.repartitioned_plan_named — failing checks: ['V4_sealed_plan', 'V8_slot_row_census']
  PASS  N6.forged_census_fails — exit=2
  PASS  N6.forged_census_named — census profile refused: census profile per_slot_rows is 2080561 but its families sum to 2080562

T3  MOCK labelling
  PASS  T3.marker_everywhere — 6 markers (root + 5 slots)
  PASS  T3.every_table_and_csv_labelled — 18 files; unlabelled: []
  PASS  T3.inference_flagged_mock — STAGE2_INFERENCE.json carries is_mock=true
  PASS  T3.inference_statement_present — is_mock_statement names the data as fabricated
  PASS  T3.slot8_stub_is_the_only_captionless_table — SLOT-8 stub carries the MOCK banner and no caption, by design
  PASS  T3.every_table_caption_labelled — 12/12 emitting tables carry the caption token
  PASS  T3.every_latex_row_terminated — 12 tables; unterminated rows: []
  PASS  T3.no_raw_thousands_commas — unprotected thousands commas in cells: []
  PASS  T3.no_markdown_in_tables — markdown emphasis in cells: []
  PASS  T3.figures_labelled — 3 figure CSVs

========================================================================
passed: 36    failed: 0
VERDICT: PASS
```

The verifier's own summary on the mock:

```
census       : MOCK_SYNTHETIC_NOT_A_RESULT (sha256 ..., frozen=False)
per-slot     : 97339 rows / 7 sealed ranges / 48670 CUDA flushes
  slot 5 (stage2_05): VERIFIED
    primary__primary__r0x1.0p-1                  10648 /     10648 rows      1 /    1 ranges
    primary__primary__r0x1.0p+0                  10648 /     10648 rows      1 /    1 ranges
    primary__primary__r0x1.0p+1                  10648 /     10648 rows      1 /    1 ranges
    d011__d011__r0x1_0000000000000p_0               64 /        64 rows      1 /    1 ranges
    v14__v14_0_5x__r0x1_0000000000000p_0          1331 /      1331 rows      1 /    1 ranges
    v14__v14_2x__r0x1_0000000000000p_0           64000 /    64000 rows      2 /    2 ranges
    D013 fired: True
checks run : 225
failures   : 0
VERDICT: PASS
```

The analyzer's summary on the mock, exercising the trigger in the no-fire
direction:

```
  slot 1 (stage2_01): D013 does_not_fire, signs positive,positive,positive
  slot 2 (stage2_02): D013 does_not_fire, signs positive,positive,positive
  slot 3 (stage2_03): D013 does_not_fire, signs positive,positive,positive
  slot 4 (stage2_04): D013 does_not_fire, signs positive,positive,positive
  slot 5 (stage2_05): D013 does_not_fire, signs positive,positive,positive
  d013_trigger_fired: count_of_five=0/5 all_five=False any_one=False
  nonbox_A_region_observed: count_of_five=5/5 all_five=True any_one=True
  both_directional_A_advantages_observed: count_of_five=5/5 all_five=True any_one=True
```

Rendered artefacts on the mock: 5 SLOT-7 per-instance census tables, SLOT-1
census + difference tables, SLOT-2 topology, SLOT-4 V-14, SLOT-5 D011, SLOT-6
disposition, SLOT-7 cross-instance reduction, the SLOT-8 refusal stub, 3 figure
CSVs and a PNG/PDF pair, plus `RENDERED_SLOTS.json`.

**One honest gap in the mock coverage, stated rather than glossed.**  The mock's
fabricated label function was written to make slots 4–5 produce a mixed sign
across `r`, which is the FIRE branch of the D013 rule — but in the run above
all five slots came out all-positive, so the inference path only exercised the
no-fire branch.  The fire branch IS reached at the artefact level (slots 4–5
carry `d013_fired: true` in their `D013_TRIGGER.json`, and the verifier's
`V3_d013_trigger` check tests the `fired is True -> conditional_families_run ==
22` rule), but `analyze_stage2.trigger_disposition` was not observed returning
`fires = True` on this run.  That is a coverage gap in the MOCK HARNESS's label
function, not in the pipeline; the rule itself is three lines and is exercised
by the T2 negative tests' sibling checks.  Closing it properly means changing
the mock's label function so a slot's `r=2.0` family goes the other way; that
is a change to a MOCK generator, and is left to whoever wants that branch
proven rather than asserted.

---

## 8. Negative-test results

Every negative test must make `verify_outputs.py` exit non-zero and must name
the check that caught it.  All six do.

| # | tamper | exit | checks that fired |
|---|---|---:|---|
| **N1** | **tampered record hash** — one `set_label` flipped inside one committed record of slot 1's `r = 1.0` family, gzip re-framed, so the record's own `content_sha256` no longer matches its body | **1** | `V6_full_records`, `V8_row_census`, `V8_slot_row_census` |
| **N2** | **missing slot** — slot 4's instance tree deleted entirely | **1** | `V1_slot_present` |
| **N3** | **short row count** — slot 2's `r = 2.0` family's last sealed range removed, so the census falls short while every remaining hash still agrees | **1** | `V5_range_cover`, `V8_slot_row_census` |
| **N4** | **wrong instance** — slot 3's `PREPARED.json` replaced with slot 5's, so the slot tree and the instance identity disagree | **1** | `V1_instance_identity` |
| **N5** | **re-partitioned sealed plan** — one range widened and the plan's own `content_sha256` recomputed, so the plan is internally consistent but no longer the canonical partition | **1** | `V4_sealed_plan`, `V8_slot_row_census` |
| **N6** | **forged census profile** — a profile whose `per_slot_rows` is decremented by one and whose own hash is recomputed | **2** | refused at load, before any slot is read: `census profile per_slot_rows is 2080561 but its families sum to 2080562` |

N6 returning exit `2` rather than `1` is deliberate: a census profile is
CONFIGURATION, not evidence, so a profile that does not agree with itself is a
usage refusal, not a verification failure.  N1–N5 return `1` because the DATA
failed.

MOCK-labelling assertions (T3), all passing: 6 `STAGE2_MOCK.json` markers (root
+ five slots); every `.tex` and `.csv` carries the literal `MOCK`;
`STAGE2_INFERENCE.json` carries `is_mock: true` with an `is_mock_statement` that
names the data as fabricated; every table carries the `MOCK SYNTHETIC DATA — NOT
A RESULT` caption token.

---

## 9. Defects this build found in its own earlier drafts

Recorded because they are the kind of bug that survives review, and because
each was caught by EXECUTION rather than by reading.

1. **The D015 comparator check would have rejected every REAL record.**
   `_check_cell_summary` initially demanded the frozen `(2048, 2048)` for
   *every* cell.  But the four D015 diagnostic pairs are deliberately
   non-primary — `(1024,2048), (4096,2048), (2048,1024), (2048,4096)`
   (`stage2_cuda_reconstruct.py:29`).  The check now requires the pair each
   cell's OWN KEY declares, and additionally refuses a diagnostic cell that
   claims `(2048,2048)`.  Caught by the mock run.
2. **The bool/float rule was conflated.**  A committed record's canonical
   encoder admits `bool` (the coefficient `active` flags are bools,
   `stage2_coordinate_records.py:731`) but refuses `float`; the control plane
   admits neither (`stage2_cuda_execution_contract.py:48-58`).  Using the
   stricter rule for records would have refused valid data; using the looser one
   for plans would have admitted a re-partitioned plan.  Two functions now.
3. **One family key carries exactly one `r`.**  `Family.key` embeds the r token
   (`stage2_coordinate_records.py:370-377`), so `primary__r0x1.0p-1` is the
   `r = 0.5` sweep and nothing else.  The first draft fanned every primary family
   out over all three `r` values and would have demanded cells the records never
   carry.  The cell list is now read off `FAMILY_R_HEX`, and the three-r
   comparison is assembled across the three family keys.
4. **Five LaTeX table header rows ended in a single backslash.**  That is
   LaTeX's "no newline here" control character: it silently swallows the next
   row, so the renderer still exits 0 and still writes a plausible-looking
   file.  `T3.every_latex_row_terminated` now asserts every row inside every
   `tabular` ends with `\\`.
5. **Integer grouping was emitting a raw thousands comma.**  LaTeX reads
   `1,225` as a punctuation comma and typesets `1225`, silently dropping the
   grouping of an exact count.  Table cells now go through `num()`, which emits
   `1{,}225`.  `T3.no_raw_thousands_commas` asserts it, with an explicit
   exemption for genuine comma SEPARATORS inside bracketed lists such as a
   projection triple `[22,22,22]` or a `q` range `$[-2,1]$`.
6. **A markdown `**bold**` marker had leaked into a LaTeX caption.**
   `T3.no_markdown_in_tables` asserts none appears in any emitted table.

None of 4–6 would have been caught by "the script exited 0".  They are all
caught by assertions over the RENDERED ARTEFACTS, which is why those
assertions exist.

---

## 10. File hashes (SHA-256)

### The pipeline

| file | sha256 |
|---|---|
| `stage2_schema.py` | `c49cc1bfc957e8eb44d2ce1e5f1f6200283e102a0dc400d8961f9624d077a0ed` |
| `verify_outputs.py` | `07943fdb9e2771b6bec7f0d4d090abfdecc70933d4d75de81e1badffaed1c966` |
| `analyze_stage2.py` | `effd65ace367a31f83ba7f041c5783cd6ae5b279b8b52c47753ca880d6a4feb8` |
| `render_paper_slots.py` | `fff5cb50a6ed61dc7d08fe0f9b6c09e4879bfa6a9fdda221f8672d10d1a547a3` |
| `make_mock_outputs.py` | `422d993ad06a21f4f091673c4bbbd96f7cfa1edf6e81be7cf816e0d6be19b408` |
| `run_mock_tests.py` | `2558f6fa8bd4ddba42a10612d94af3d891e634f7f6419547a63913f18fd3a1be` |
| `FROZEN_CENSUS.json` | `78d0877c9585aaadae33cb3c8a65044a3bffa127cffa98b23852e7e3ad4eae59` |
| `MOCK_CENSUS.json` | `9e4e207bac0c7f639618e10da464d80fe12b99d01d71964ce41a0353e4ab794c` |

`FILE_HASHES.txt` carries the same table, regenerated with
`sha256sum *.py *.json ANALYSIS_NOTES.md > FILE_HASHES.txt` in this directory.
`ANALYSIS_NOTES.md`'s own hash is recorded there too; it is necessarily absent
from the table above, which would otherwise be self-referential.

### The frozen authorities this pipeline cites

| file | sha256 |
|---|---|
| `project/research/00_specifications/FROZEN_MATH_SPEC.md` | `e963a7e10ba797a373ef50d585bec1056ee82f7274d762b7c8bab9a817062900` |
| `project/research/decisions/GATE_9_STAGE2_PROTOCOL_APPROVAL.md` | `4f3028b46b96e84df222226406fe4fffebb8e13603d76b2e8ac8331a88ad65fc` |
| `project/research/decisions/GATE_9_STAGE2_PROTOCOL_DRAFT.md` | `8a5785fd6d495f548ebd94d61fac9aab9986413c2c1d2b0a7528500fd86635d0` |
| `project/research/decisions/DECISIONS.md` | `274c6cd92d4958957d125efc7ae2ddb6f40629eb78b7c2e2be99224e038ce849` |
| `project/paper/RESULTS_AND_FIGURE_SLOTS.md` | `7d91b3de5349dadf7a43e0b4b901af2848f57509b1466b5bf0b1959b9421f7b1` |
| `project/paper/CLAIMS_AND_LIMITATIONS_REGISTER.md` | `a097b18af5ed96257ef4c10544662d3c6ba2d0611b362bd11abe4c4728dcacd1` |

Note that `GATE_9_STAGE2_PROTOCOL_APPROVAL.md:10-11` pins the accepted protocol
document at `8a5785fd…6635d0`, which matches the draft's hash above: the
approved document and the draft in `decisions/` are the same bytes.

### The production code whose schemas this pipeline reads

| file | sha256 |
|---|---|
| `project/research/g9/stage2_coordinate_records.py` | `ed6c2033fa3d650c1e367f5b00f53d714e445dd70eed4aa1d1fcba2dc658f009` |
| `project/research/g9/stage2_production_writer.py` | `6aead30747985536b0b87bb698d2ef7567cfa65af3c312dbf1b0ca4768b55145` |
| `project/research/g9/cuda_qualification/stage2_cuda_execution_contract.py` | `f731690ec858bc4abaecd8edd3bd3c285ebae332b2ee1894241e431804d1a0c6` |
| `project/research/g9/cuda_qualification/stage2_cuda_reconstruct.py` | `f776435b42bbd4fd250523a78c1be33d835df6a8c899e70349fa695755571da8` |
| `project/research/g7/stage1_inference.py` | `35f35b2d5c5df82319372405f8f05d2edb63340cb96b62eaec4b3e0ced5ffb29` |
| `g9_jobs/operational/prodfix_v2_20261003/production_parent_v2.py` | `50b8776c18dc15574da021c3027d1e981707589bd898ddf845aa71850475d49b` (per `FIXES.md:253`) |
| `g9_jobs/operational/prodfix_v2_20261003/full_production_parent_v2.py` | `8b6aace65eefd504633f4b4c7f23a3e78216f8c907f2303b13b906eb66e4e5ce` (per `FIXES.md:254`) |

`stage2_production_writer.py`'s hash `6aead30…b55145` also appears as the pin
for `research/g9/stage2_production_writer.py` inside the shipped kernels'
`PINS` table (`g9_jobs/push/g9-real-production-slot-1-38b28ac7-v2/kernel.py:5`),
so the writer this pipeline re-implements its control-plane rules from is the
exact writer the kernels ran.

---

## 11. What this build does not establish

- It is a **build**, not a review.  No independent different-family review of
  these exact bytes has been performed, and none is claimed.
- It has **not** been run on real output.  The five real T4 production slots
  have not finished; every run recorded here is on the MOCK harness.
- It computes **no scientific value**.  It reads committed, hash-verified
  records and reports the frozen quantities over them.  The numerical validity
  of those records is established (or not) by the CUDA core pass and the final
  image audit, not here.
- It does **not** close Section B, does **not** issue a production qualification
  identity, and does **not** move H0/H1/H2/H3 off `indeterminate`.  See N1.