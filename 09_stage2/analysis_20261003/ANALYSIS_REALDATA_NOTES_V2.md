# Real production format validation — V2

All changes are additive `_v2` files in this directory. The 10 original files
covered by `FILE_HASHES.txt` still pass `sha256sum --check --quiet`. Existing
production artifacts were read only. All test writes used mktemp directories
under `g9_jobs/scratch/analysisfix`. No network, Kaggle command or install ran.
No inference or scientific conclusions were computed from real records.

## Mismatches and fixes

1. **Primary family names:** the three old `primary__primary__r0x1.0p...`
   names disagreed with committed production names. Schema, verifier, analyzer,
   mock generator and sealed census profiles now use:
   `primary__primary__r0x1_0000000000000p-1`,
   `primary__primary__r0x1_0000000000000p_0`, and
   `primary__primary__r0x1_0000000000000p_1`.
   All six baseline keys exactly match the V4K plan's `canonical_family_order`;
   D011 and V14 keys already matched. Unknown keys produce a schema refusal
   instead of a dictionary `KeyError`. The axis lengths, row/range counts,
   comparators, coordinate order and reconstruction rules are unchanged.
   Only the new census configurations were resealed; evidence was not renamed
   or rewritten. No further coordinate-record shape mismatch was found.
2. **Preparation metadata encoder:** real `PREPARED.json` contains finite
   JSON floats in its provenance blocks. Its writer uses ordinary canonical
   JSON (`wp8d_drawn_instance_layout._canonical`, `production_parent_v2.canonical`).
   `read_prepared_metadata` recomputes that hash with `allow_nan=False`.
   Coordinate records retain their original strict no-float encoder; this is
   not a general relaxation of committed-record validation.
3. **Preparation identity location:** production puts the instance identifier
   in `PREPARED.instance.instance_id`, while the mock used top-level fields.
   Both forms are checked, and `instance_id_of` returns the checked identifier.
4. **Family layout:** legacy `<staged>/research/g9/stage2_instances/<instance>/sweep/<family>`
   and modern `<staged>/scratch/v4_sweep/<instance>/<family>` are resolved by one
   helper. Both present at once is an explicit ambiguity refusal. The collector
   retains instance metadata under the legacy instance tree, so slot discovery
   still uses that metadata tree. Receipt paths bind to unchanged bytes under
   either merged layout prefix.
5. **Three-piece collection versus one terminal run:** a V4K merge is
   `<merge-root>/piece_merge_slotN/staged_qualified_sources/...`; it has merged
   range artifacts and instance metadata, not a fabricated single-run terminal
   receipt. `--piece-plan` plus `--piece-outputs` invokes the existing collector's
   read-only `verify_slot` with no merge/download action. All three pieces per
   slot, their sessions, identities, range coverage and receipts are reverified;
   every merged evidence file is hash-bound to those receipts, and preparation
   identity is checked. Collector proof replaces the legacy single-session
   receipt/registry checks only for those proven slots. Ordinary family integrity
   checks still run. Verification scope is baseline collection, `accepted=false`;
   conditional work and final image/scientific acceptance remain pending.
   Raw duplicate piece trees must first be assembled by the collector; they
   are never silently combined as independent instances.
6. **Incomplete inputs:** an inventory records every missing slot, family,
   plan and range artifact before terminal checks. Missing data never becomes
   successful completion or synthesized records. Failed receipt guards no longer
   cause tuple-unpacking crashes. Ambiguous family paths are recorded failures.
   `all_slots_verified` also requires zero failures. The analyzer revalidates
   inputs and refuses incomplete data before inference; `--check-inputs-only`
   exits after validation without computing inference.
7. **Mock runner paths:** relative `--work` paths were interpreted from the
   subprocess script directory. The V2 runner resolves them absolutely and its
   default scratch root is `scratch/analysisfix`.
8. **Build regression corrections:** the first mock analyzer rerun exposed
   missing verification-scope fields; these are now supplied by the verifier.
   Public schema identifiers were restored after the filename migration.
   Plot caching is confined to the scratch run directory beside the output
   tree, keeping cache JSON outside manuscript artifacts and their MOCK-label
   checks. Corrected analysis/rendering checks were rerun successfully.

## Validation evidence

- Source: `scratch/v4j_p1_out_shivanshsrivastava06/staged_qualified_sources/research/g9/stage2_instances/stage2_01/sweep/primary__primary__r0x1_0000000000000p-1`.
- Real records: **56 gzip files; 226,981 checked; 226,981 passed; 0 failed**.
  The final streaming scanner also checked contiguous linear indices.
- Complete available family: **60 verifier integrity checks; 0 failures**;
  **226,981 rows and 56 ranges**. These checks cover manifests, byte hashes,
  record commitments, writer projections and census; they do not replay CUDA.
- Format regressions: **23 passed, 0 failed**. Three scratch piece sources
  assembled unchanged real range artifacts into both legacy and modern merged
  slot layouts. Tests cover absent ranges, ambiguous layouts, metadata hash
  tampering, unknown keys, record float refusal and receipt-path binding.
- Each partial layout reports exactly **five missing slot-1 families and four
  missing slots** in its completeness inventory. No other inventory defect was
  found. The genuine terminal status is `incomplete_piece`, and the genuine
  piece receipt is `incomplete_refused`; these are correctly refused, not changed.
  The report has 14 failures including terminal refusal and repeated slot
  presence failures. Its first precise failure is:
  `incomplete: missing family stage2_01/primary__primary__r0x1_0000000000000p_0`.
  Both verifier calls return refusal without crashing; analyzer returns 2 and
  creates no inference artifact.
- Mock regression: **36 distinct checks passed in final executions; 0 remain
  failed** (14 end-to-end, 10 labeling, 12 checks across six negative cases).
  The full runner completed the six negative cases; corrected end-to-end and
  labels were rerun separately after the scope-field fix. The final renderer was
  rerun again after cache placement, with 10 labeling checks and its manifest
  hash passing. The earlier combined log retains superseded T1/T3 failures;
  `MOCK_TEST_RESULTS_v2.json` records the final results and exact evidence paths.
- Zero new `.pyc` files: zero in this analysis directory and task scratch.
  Workspace-wide inspection found 38 pre-existing `.pyc` files, all predating
  this build; they remain untouched because locations elsewhere are read only.
- Only the available family and partial layouts were tested on real data. A
  complete five-slot, fifteen-piece production collection was unavailable;
  completeness is not claimed. Full scientific analysis ran only on synthetic
  mock fixtures as required by the regression tests.

Machine-readable counts: `REALDATA_VALIDATION_v2.json` and
`MOCK_TEST_RESULTS_v2.json`. Scratch evidence is retained.

## How to run

Run from `g9_jobs`, using Python without bytecode:

```sh
mkdir -p scratch/analysisfix
ANALYSISFIX_WORK=$(mktemp -d "$PWD/scratch/analysisfix/check.XXXXXX")
python3 -B operational/analysis_20261003/validate_real_records_v2.py \
  --family-root scratch/v4j_p1_out_shivanshsrivastava06/staged_qualified_sources/research/g9/stage2_instances/stage2_01/sweep/primary__primary__r0x1_0000000000000p-1 \
  --report "$ANALYSISFIX_WORK/record_counts.json"
python3 -B operational/analysis_20261003/run_realdata_tests_v2.py \
  --source scratch/v4j_p1_out_shivanshsrivastava06
python3 -B operational/analysis_20261003/run_mock_tests_v2.py \
  --work "$ANALYSISFIX_WORK/mock" --keep
```

For an already collected V4K merge, keep its original `sNpM` piece-output
folders and the original plan/package references available. The following
commands read them; they do not download or assemble output:

```sh
python3 -B operational/analysis_20261003/verify_outputs_v2.py \
  --results-root /path/to/merge-root \
  --piece-plan operational/multiacct_20261003/production_v4_release/final_v4k/PRODUCTION_V4_PLAN.json \
  --piece-outputs /path/to/piece-output-parent \
  --report "$ANALYSISFIX_WORK/VERIFY.json"
python3 -B operational/analysis_20261003/analyze_stage2_v2.py \
  --results-root /path/to/merge-root \
  --piece-plan operational/multiacct_20261003/production_v4_release/final_v4k/PRODUCTION_V4_PLAN.json \
  --piece-outputs /path/to/piece-output-parent \
  --out "$ANALYSISFIX_WORK/check_only" --check-inputs-only
```

For legacy complete single-run downloads, use the same V2 scripts without
piece arguments. To check tonight's partial production tree, set
`--results-root scratch/v4j_p1_out_shivanshsrivastava06`, omit the piece
arguments, and expect verifier exit 1 / analyzer exit 2 with precise missing
items in the JSON report. No missing families or slots are manufactured.

The default census is `FROZEN_CENSUS_v2.json`. `MOCK_CENSUS_v2.json` is used only
by the synthetic harness and remains explicitly non-frozen. Removing
`--check-inputs-only` enables the existing inference path for a fully verified
collection; that real-data inference path was not executed in this build.
