#!/bin/bash
# Run every Stage-2 fixture suite from the project root; one TSV row each: exit code, seconds, suite.
# Usage: bash ops/scripts/run_stage2_fixtures.sh <out.tsv>
export PYTHONDONTWRITEBYTECODE=1
out="${1:?usage: run_stage2_fixtures.sh <out.tsv>}"
: > "$out"
for f in research/g9/verify_stage2_*_fixtures.py; do
  t0=$(date +%s)
  timeout 900 python3 "$f" > /dev/null 2>&1
  printf '%s\t%s\t%s\n' "$?" "$(( $(date +%s) - t0 ))" "$f" >> "$out"
done
echo "done: $(wc -l < "$out") suites, $(awk -F'\t' '$1==0' "$out" | wc -l) passed"
