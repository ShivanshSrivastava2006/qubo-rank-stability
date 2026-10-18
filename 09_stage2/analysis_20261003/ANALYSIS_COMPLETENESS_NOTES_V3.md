# Stage-2 analysis completeness v3

Additive implementation of paper-owner decision item 2,
`project/research/decisions/PAPER_OWNER_DECISIONS_20261003.md:7`.
All implementation files are new `_v3.py` files in this directory. Existing
analysis, staged sources, project and paper files were not edited. No network,
Kaggle invocation, installation or scientific result publication was performed.
All Python execution used `python3 -B`. Task scratch is under
`g9_jobs/scratch/analysiscomplete/`, created with `mktemp -d`.

## Frozen semantics and exact series

The authority paths below are relative to `project/`.

1. `research/00_specifications/FROZEN_MATH_SPEC.md:85` defines decoded,
   deduplicated `X_E`. The staged producer
   `push/collected_v4k/s2p2/staged_qualified_sources/research/g9/cuda_qualification/stage2_cuda_reconstruct.py:175-190`
   decodes the tie set, classifies decoded portfolios and counts atomic labels;
   `:196-213` supplies `X_E_size`, indicators and per-coordinate fractions.
   The analysis consumes those decoded counts, never encoded multiplicities or
   `T_E_size`. Reconstruction itself is not replayed by a FORMAT test.
2. Frozen spec `:452-465` defines atomic A/B/C and the existential-C,
   universal-A set-label rule. `completeness_core_v3.add_summary` validates the
   nonempty denominator, integer atomic census, label, indicators and supplied
   per-coordinate fractions before aggregation. Spec `:468-470` supplies the
   decoded denominator for `p_A,p_B,p_C`.
3. Spec `:470-471` requires the arithmetic mean of per-coordinate fractions.
   For each label the implementation sums `Fraction(atomic_count, X_E_size)`
   and divides by the number of coordinates. It reduces only at rational
   serialization, using exact integer numerator/denominator pairs. It does not
   pool atomic counts or round through floats.
4. Spec `:473` defines the finite-grid primary A-rate. The exact nine-key
   series preserves Gate-6's raw A-count/population numerator/denominator
   representation, while `mean_p` fractions are reduced. Gate-6's implementation
   is `research/g6/rate_surface_and_d013.py:105-131`; its exact `SERIES_KEYS`
   declaration is `:57-58`.

`analyze_stage2_v3.py` integrates the reducer into its existing single family
scan. Each family carries `series`, whose entries contain exactly:
`source, r_hex, encoding, coordinate_count, set_label_counts, rho_E_exact,
I_C_exist_count, I_C_univ_count, mean_p`. `source` identifies the Stage-2 family.
Each existing reported cell also carries `mean_p` and its corresponding exact
`series` entry, so the unchanged insertion renderer can consume the primary
fractions. Existing table and diagnostic metadata remain outside SERIES_KEYS.
There are no new thresholds or winner rules; hypothesis thresholds remain
indeterminate. D015 diagnostic pairs do not become additional primary rates.

The CLI also validates prepared metadata using its finite-float canonical
format, reseals inference after provenance additions, refuses overwrites, and
confines writes to task scratch. Frozen real-census CLI runs require
`--check-inputs-only`; real FORMAT tests do not export inference values.

## Machine-only certificates

`export_certificates_v3.py` finds all five pre-production reference receipts
under `push/g9-real-reference-*/results/` and prepared records in the staged
trees. It verifies prepared content seals, instance/production identity,
prepared-record digest equality, reference metadata/frame byte digests from
`REAL_REFERENCE_RESULT.json`, agreement of every reference frame's feasible
count, and bit-exact agreement of certified `f_star` and `Lambda_ref`.
Duplicate staged copies must agree; missing or inconsistent facts fail closed.

Frozen spec `:114-129` defines the original feasible set and optimum value/set;
`:148-150` defines `Lambda_ref`, the original-objective normalization. The
feasible count comes from the pre-production frame's `feasible_count`, the
optimum value and full decoded mask set from PREPARED `results.f_star` and
`results.X_star`, and normalization from `results.Lambda_ref`. No coordinate
run supplies certificate facts. Binary64 hexadecimal text preserves the
prepared numbers exactly; masks fully identify the optimum set.

Outputs are filled cell fragments, with no floating table or pending macro:
`analysis/output/certificates/stage2_0N_certificate.tex`. Every fragment includes
source paths and full SHA-256 comments for PREPARED, reference metadata,
reference frames and the reference receipt. Real exports are marked
`REAL FORMAT TEST ONLY`, confined to scratch, and were not inserted into a paper.

## Verification results (counts only)

- Final mock suite: five slots, zero verification failures, 60 exact nine-key
  series, 29 inserted cells, and one rejected certificate mismatch. Three
  invalid decoded-census fixtures were rejected. A weighted fixture distinguishes
  arithmetic means from pooled fractions. Mixed-label mock records exercise
  fractional decoded ties. The CLI-produced inference seal is checked too.
  Artifacts: `scratch/analysiscomplete/mockverified.2kB9RA/`.
- REAL FORMAT: all 56 legacy slot-1 primary `r=0.5` files, 226,981 records,
  two nine-key series; one collected-v4k piece file, 4,096 records, two nine-key
  series. Full coordinate schema validation and the v3 reducer passed.
  Five certificate fragments passed all source bindings.
  Artifacts: `scratch/analysiscomplete/testreal.jp5u91/`.
- Stage-1 consistency: all 680,943 owner-ratified Gate-5 input records;
  six full series matched the accepted series exactly, including 18 reduced
  `mean_p` fractions with identical canonical bytes. Accepted values are
  recorded in `project/research/g7/stage1_inference/STAGE1_INFERENCE.json:1`,
  `primary_reported_rates` (the file is single-line JSON). Input boundary:
  `project/src/g6/ratified_g5_input.py:85-123`; accepted corpus:
  `project/research/g5/core_pass_output/`. The same v3 reducer was used on
  decoded Stage-1 certificates; no accepted value was copied into the reducer.
  Artifacts: `scratch/analysiscomplete/teststage1.m1FnE6/`.
- Five new Python files passed AST syntax checks. Zero `.pyc` files in the
  analysis directory and task scratch tree.

## Run and insertion interface

From `g9_jobs/`, rerun the complete count-only harness:

```sh
mkdir -p scratch/analysiscomplete
analysiscomplete_work=$(mktemp -d scratch/analysiscomplete/run.XXXXXX)
python3 -B operational/analysis_20261003/run_completeness_tests_v3.py \
  --suite all --work "$analysiscomplete_work"
```

Individual suites are `mock`, `real`, and `stage1`. The mock suite writes
`$analysiscomplete_work/analysis/output/STAGE2_INFERENCE.json`, tables,
certificate fragments, `INSERTION_CELLS.json`, and the 29 insertion fragments.
It exercises the unchanged insertion engine on a minimal labelled MOCK paper
fixture. Its default `scratch/paperinsert` guard conflicts with this task's
scratch rule, so the test changes only the engine's in-memory scratch root to
the newly created task directory. No insertion source file is modified.

The existing adapter already reads `mean_p` from reported primary cells and
automatically finds `analysis/output/certificates/`. Its standalone command is:

```sh
python3 -B operational/paper_insert_20261004/render_insertion_cells.py \
  --analysis-dir "$analysiscomplete_work/analysis/output"
```

Alternatively pass `--certificate-dir` with the machine-exported directory.
The adapter's manifests must report both `certificate_values_available` and
`tie_fractions_available` as true. The mock harness verifies both flags and
insertion of all 29 slots. The existing `insert_results.py` interface remains
`--analysis-dir <output> --paper-copy <fresh-copy> --mode mock|real`; its normal
CLI restricts copies to `scratch/paperinsert`. This build does not invoke that
CLI outside the allowed task scratch tree or populate any real paper.

To regenerate REAL FORMAT certificate fragments only:

```sh
analysiscomplete_format=$(mktemp -d scratch/analysiscomplete/certformat.XXXXXX)
python3 -B operational/analysis_20261003/export_certificates_v3.py \
  --staged-root push/collected_v4k --reference-root push \
  --out "$analysiscomplete_format/analysis/output/certificates"
```

These additions close the analysis fields and certificate export interfaces.
They do not certify numerical CUDA reconstruction, Stage-2 acceptance,
conditional/image production completion, or authorize scientific publication.
