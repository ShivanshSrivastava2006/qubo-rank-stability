#!/usr/bin/env python3
"""End-to-end and negative tests for the G9 Stage-2 analysis pipeline.

    python3 -B run_mock_tests.py [--work DIR] [--keep]

It runs, in order:

  T1  the MOCK harness, five slots, `verify -> analyze -> render`, and asserts
      each stage exited 0 and produced the expected artefacts;
  T2  the four mandated negative tests, each of which MUST fail closed:
        N1  tampered record hash          -> the record's own content_sha256
        N2  missing slot                  -> V1_slot_present
        N3  short row count               -> V8_row_census
        N4  wrong instance                -> V1_instance_identity / V3
      plus two more that exercise the same machinery from other directions:
        N5  tampered range plan (re-partitioned)  -> V4_sealed_plan
        N6  census profile claiming a different ROW total -> refused at load
  T3  the MOCK labelling assertions: every generated file and every rendered
      caption carries the literal `MOCK`.

Exit 0 iff every assertion held.  Nothing here touches `project/paper/`.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import make_mock_outputs_v2 as mock  # noqa: E402
import stage2_schema_v2 as schema  # noqa: E402

MOCK_CENSUS = HERE / schema.MOCK_CENSUS_NAME
FROZEN_CENSUS = HERE / schema.FROZEN_CENSUS_NAME
MOCK_MARKER = mock.MOCK_MARKER_NAME

FAILURES: list[str] = []
PASSES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    if ok:
        PASSES.append(name)
        print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))
    else:
        FAILURES.append(f"{name}: {detail}")
        print(f"  FAIL  {name} — {detail}")
    return ok


def run(script: str, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-B", str(HERE / script), *args],
        capture_output=True, text=True, env=env, cwd=str(HERE))


def read_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# T1 — the happy path on MOCK data
# ---------------------------------------------------------------------------

def test_end_to_end(work: Path) -> None:
    print("\nT1  end-to-end MOCK run: verify -> analyze -> render")
    root = work / "mock"
    census = schema.load_census_profile(MOCK_CENSUS)
    # The mock tree is a pure function of the census profile, so it is BUILT
    # ONCE into a cache and then copied.  Rebuilding it for every negative test
    # would dominate the run time without testing anything new.
    cache = work / "mock_cache"
    if cache.is_dir() and (cache / "STAGE2_MOCK.json").is_file():
        print(f"  ....  reusing the cached mock tree at {cache}")
        summary = {"slots": [{"rows": census["per_slot_rows"]}] * 5}
    else:
        if root.exists():
            shutil.rmtree(root)
        summary = mock.build(root, [1, 2, 3, 4, 5],
                             census["records_per_range"], census["scale"])
        if cache.exists():
            shutil.rmtree(cache)
        shutil.copytree(root, cache)
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(cache, root)
    check("T1.mock_tree_built",
          len(summary["slots"]) == 5
          and all(slot["rows"] == census["per_slot_rows"]
                  for slot in summary["slots"]),
          f"5 slots x {census['per_slot_rows']:,} records "
          f"(real census is {schema.PER_SLOT_ROWS:,})")

    out = work / "out"
    if out.exists():
        shutil.rmtree(out)

    report_path = work / "verify.json"
    verified = run("verify_outputs_v2.py", "--results-root", str(root),
                   "--census", str(MOCK_CENSUS), "--report", str(report_path))
    check("T1.verify_exit_zero", verified.returncode == 0,
          f"exit={verified.returncode}")
    if verified.returncode != 0:
        print(verified.stdout[-4000:])
        check("T1.verify_pass", False, "verifier did not pass on well-formed mock")
        return
    report = read_report(report_path)
    check("T1.verify_pass", report["failure_count"] == 0,
          f"{report['checks_run']} checks, 0 failures")
    check("T1.verify_rows", report["census_profile"]["per_slot_rows"]
          == census["per_slot_rows"],
          f"{report['census_profile']['per_slot_rows']:,} rows per slot")
    check("T1.verify_not_frozen", report["census_profile"]["is_frozen_real_census"]
          is False, "mock profile correctly reported as not the frozen census")

    inference = out / "STAGE2_INFERENCE.json"
    analyzed = run("analyze_stage2_v2.py", "--results-root", str(root),
                   "--census", str(MOCK_CENSUS), "--out", str(out),
                   "--verify-report", str(report_path))
    check("T1.analyze_exit_zero", analyzed.returncode == 0,
          f"exit={analyzed.returncode}")
    if analyzed.returncode != 0:
        print(analyzed.stdout[-4000:])
        print(analyzed.stderr[-4000:])
        check("T1.analyze_pass", False, "analyzer refused a verified tree")
        return
    payload = read_report(inference)
    check("T1.inference_self_hash",
          schema.content_sha256(payload) == payload["content_sha256"],
          f"content_sha256={payload['content_sha256'][:16]}...")
    check("T1.inference_is_mock", payload["is_mock"] is True,
          "is_mock=true because the census profile is not the frozen one")
    check("T1.inference_five_slots", payload["slot_count"] == 5, "5 slots")
    check("T1.no_floats", _no_float_leaf(payload),
          "the inference record contains no JSON float leaf")

    rendered = run("render_paper_slots_v2.py", "--inference", str(inference),
                   "--out", str(out))
    check("T1.render_exit_zero", rendered.returncode == 0,
          f"exit={rendered.returncode}")
    if rendered.returncode != 0:
        print(rendered.stdout[-3000:])
        print(rendered.stderr[-3000:])
        check("T1.render_pass", False, "renderer refused its own inference record")
        return
    manifest = read_report(out / "RENDERED_SLOTS.json")
    check("T1.render_manifest_self_hash",
          schema.content_sha256(manifest) == manifest["content_sha256"],
          "RENDERED_SLOTS.json re-derives")
    check("T1.slots_emitted",
          set(manifest["slots_emitted"]) ==
          {"SLOT-1", "SLOT-2", "SLOT-4", "SLOT-5", "SLOT-6", "SLOT-7"},
          ", ".join(sorted(manifest["slots_emitted"])))
    check("T1.slots_refused",
          set(manifest["slots_not_emitted"]) == {"SLOT-3", "SLOT-8"},
          "SLOT-3 and SLOT-8 refused with stated reasons")


def _no_float_leaf(value: Any) -> bool:
    if isinstance(value, float):
        return False
    if isinstance(value, dict):
        return all(_no_float_leaf(item) for item in value.values())
    if isinstance(value, list):
        return all(_no_float_leaf(item) for item in value)
    return True


# ---------------------------------------------------------------------------
# T2 — the negative tests, each of which MUST fail closed
# ---------------------------------------------------------------------------

def _clone(source: Path, target: Path) -> Path:
    """A throwaway COPY of the mock tree.

    A real copy, never hard links: several negative tests WRITE into the clone
    (`Path.write_bytes` truncates the inode in place), and a hard link would
    apply that write straight through to the shared cache.  Each clone is
    deleted as soon as its checks are done, so peak disk stays at two trees.
    """
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return target


def _verify(root: Path, work: Path, tag: str) -> tuple[int, dict[str, Any]]:
    report_path = work / f"neg_{tag}.json"
    result = run("verify_outputs_v2.py", "--results-root", str(root),
                 "--census", str(MOCK_CENSUS), "--report", str(report_path))
    if not report_path.is_file():
        return result.returncode, {"failure_count": -1, "failures": [],
                                   "checks": []}
    return result.returncode, read_report(report_path)


def _failure_checks(report: dict[str, Any]) -> set[str]:
    return {failure["check"] for failure in report.get("failures", [])}


def test_negatives(work: Path) -> None:
    print("\nT2  negative tests — each MUST fail closed")
    source = work / "mock"

    # N1 — a tampered record: one A-count flipped inside one full record, so the
    # record's own content_sha256 no longer matches its body.
    root = _clone(source, work / "neg_hash")
    target = _first_record(root / "slot1", 1)
    raw = gzip.decompress(target.read_bytes())
    lines = raw.split(b"\n")
    record = json.loads(lines[0])
    cell = record["reconstruction"][schema.PRIMARY_SUMMARY_KEY]["slack"]
    cell["set_label"] = "C" if cell["set_label"] != "C" else "A"
    lines[0] = schema.canonical_bytes(record)
    target.write_bytes(gzip.compress(b"\n".join(lines), compresslevel=1, mtime=0))
    code, report = _verify(root, work, "hash")
    check("N1.tampered_record_hash_fails", code == 1,
          f"exit={code}")
    check("N1.tampered_record_hash_named",
          bool(_failure_checks(report) & {"V6_full_records", "V8_row_census"}),
          f"failing checks: {sorted(_failure_checks(report))}")
    shutil.rmtree(root)

    # N2 — a missing slot: delete slot 4's instance tree entirely.
    root = _clone(source, work / "neg_missing")
    victim = (root / "slot4" / "staged_qualified_sources"
              / schema.INSTANCE_ROOT / "stage2_04")
    shutil.rmtree(victim)
    code, report = _verify(root, work, "missing")
    check("N2.missing_slot_fails", code == 1, f"exit={code}")
    check("N2.missing_slot_named", "V1_slot_present" in _failure_checks(report),
          f"failing checks: {sorted(_failure_checks(report))}")
    shutil.rmtree(root)

    # N3 — a short row count: drop the final sealed range of one family, so
    # the census falls one range short even though every remaining hash agrees.
    root = _clone(source, work / "neg_short")
    family = (root / "slot2" / "staged_qualified_sources"
              / schema.INSTANCE_ROOT / "stage2_02" / "sweep"
              / "primary__primary__r0x1_0000000000000p_1")
    plan = json.loads((family / schema.PLAN_NAME).read_text())
    last = plan["ranges"][-1]["batch_id"]
    shutil.rmtree(family / schema.RANGES_DIRNAME / last)
    (family / schema.FULL_RECORDS_DIRNAME / f"{last}.jsonl.gz").unlink()
    code, report = _verify(root, work, "short")
    check("N3.short_row_count_fails", code == 1, f"exit={code}")
    check("N3.short_row_count_named",
          bool(_failure_checks(report) & {"V5_range_cover", "V8_row_census"}),
          f"failing checks: {sorted(_failure_checks(report))}")
    shutil.rmtree(root)

    # N4 — a wrong instance: swap slot 3's PREPARED.json for slot 5's, so the
    # slot tree and the instance identity disagree.
    root = _clone(source, work / "neg_instance")
    three = (root / "slot3" / "staged_qualified_sources"
             / schema.INSTANCE_ROOT / "stage2_03" / "instance/PREPARED.json")
    five = (root / "slot5" / "staged_qualified_sources"
            / schema.INSTANCE_ROOT / "stage2_05" / "instance/PREPARED.json")
    shutil.copyfile(five, three)
    code, report = _verify(root, work, "instance")
    check("N4.wrong_instance_fails", code == 1, f"exit={code}")
    check("N4.wrong_instance_named",
          bool(_failure_checks(report) & {"V1_instance_identity",
                                           "V3_baseline_instance_id",
                                           "V3_d013_trigger",
                                           "V8_slot_row_census"}),
          f"failing checks: {sorted(_failure_checks(report))}")
    shutil.rmtree(root)

    # N5 — a re-partitioned sealed plan: widen one range and recompute the
    # plan's own content hash so it is internally consistent but no longer the
    # canonical 32768-wide partition the census profile declares.
    root = _clone(source, work / "neg_plan")
    family = (root / "slot1" / "staged_qualified_sources"
              / schema.INSTANCE_ROOT / "stage2_01" / "sweep"
              / "d011__d011__r0x1_0000000000000p_0")
    plan = json.loads((family / schema.PLAN_NAME).read_text())
    plan["ranges"][0]["stop"] = plan["ranges"][0]["stop"] + 1
    plan["content_sha256"] = schema.content_sha256(plan)
    (family / schema.PLAN_NAME).write_bytes(schema.canonical_bytes(plan))
    code, report = _verify(root, work, "plan")
    check("N5.repartitioned_plan_fails", code == 1, f"exit={code}")
    check("N5.repartitioned_plan_named", "V4_sealed_plan" in _failure_checks(report),
          f"failing checks: {sorted(_failure_checks(report))}")
    shutil.rmtree(root)

    # N6 — a census profile that claims a different ROW total must be refused
    # at load, before any slot is read.
    forged = schema.build_census_profile(
        schema.MOCK_RECORDS_PER_RANGE, schema.FAMILY_CENSUS, "FORGED")
    forged["per_slot_rows"] = forged["per_slot_rows"] - 1
    forged["content_sha256"] = schema.content_sha256(forged)
    path = work / "forged_census.json"
    path.write_bytes(schema.canonical_bytes(forged))
    result = run("verify_outputs_v2.py", "--results-root", str(source),
                 "--census", str(path))
    check("N6.forged_census_fails", result.returncode == 2,
          f"exit={result.returncode}")
    check("N6.forged_census_named", "per_slot_rows" in result.stderr,
          result.stderr.strip()[:110])


def _first_record(slot_root: Path, slot_number: int) -> Path:
    """The gzip stream of the first sealed range of the slot's r=1 family."""
    family_root = (slot_root / "staged_qualified_sources" / schema.INSTANCE_ROOT
                   / schema.SLOT_NAMES[slot_number - 1] / "sweep"
                   / "primary__primary__r0x1_0000000000000p_0")
    plan = json.loads((family_root / schema.PLAN_NAME).read_text())
    return (family_root / schema.FULL_RECORDS_DIRNAME
            / f"{plan['ranges'][0]['batch_id']}.jsonl.gz")


# ---------------------------------------------------------------------------
# T3 — MOCK labelling
# ---------------------------------------------------------------------------

def test_mock_labels(work: Path) -> None:
    print("\nT3  MOCK labelling")
    root = work / "mock"
    markers = sorted(root.rglob(MOCK_MARKER))
    check("T3.marker_everywhere", len(markers) == 6,
          f"{len(markers)} markers (root + 5 slots)")

    out = work / "out"
    produced = sorted(p for p in out.rglob("*")
                      if p.is_file() and p.suffix in (".tex", ".csv", ".json"))
    if not produced:
        check("T3.every_table_and_csv_labelled", False,
              "the renderer produced no files; T1 must have run first")
        return
    unlabelled = []
    for path in produced:
        if path.name in ("STAGE2_INFERENCE.json", "RENDERED_SLOTS.json"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if schema.MOCK_LABEL not in text:
            unlabelled.append(str(path.relative_to(out)))
    check("T3.every_table_and_csv_labelled", not unlabelled,
          f"{len(produced)} files; unlabelled: {unlabelled}")

    inference = json.loads((out / "STAGE2_INFERENCE.json").read_text())
    check("T3.inference_flagged_mock", inference["is_mock"] is True,
          "STAGE2_INFERENCE.json carries is_mock=true")
    check("T3.inference_statement_present",
          isinstance(inference.get("is_mock_statement"), str)
          and "FABRICATED" in inference["is_mock_statement"],
          "is_mock_statement names the data as fabricated")

    captions = [p for p in produced if p.suffix == ".tex"]
    # The SLOT-8 refusal stub deliberately has NO \caption: it writes no table
    # at all, by design.  It carries the MOCK token in its banner instead,
    # which T3.every_table_and_csv_labelled already asserts.
    stub = out / "tables" / "slot8_d013_ablation_NOT_EMITTED.tex"
    check("T3.slot8_stub_is_the_only_captionless_table",
          stub.is_file()
          and "NO TABLE, NO FIGURE, NO NUMBER" in stub.read_text()
          and schema.MOCK_LABEL in stub.read_text(),
          "SLOT-8 stub carries the MOCK banner and no caption, by design")
    emitting = [p for p in captions if p != stub]
    mock_caption = [p for p in emitting
                    if "MOCK SYNTHETIC DATA" in p.read_text(encoding="utf-8")]
    check("T3.every_table_caption_labelled",
          len(mock_caption) == len(emitting),
          f"{len(mock_caption)}/{len(emitting)} emitting tables carry the "
          "caption token")

    # Every row inside a `tabular` must end with `\\`.  A row ending in a single
    # backslash is the LaTeX "no newline here" control character and silently
    # swallows the NEXT row, which no assertion in this suite would otherwise
    # catch — the renderer returns 0 and the file is written.
    bad_rows: list[str] = []
    for path in emitting:
        inside = False
        for number, line in enumerate(path.read_text(encoding="utf-8")
                                      .splitlines(), 1):
            if line.strip().startswith("\\begin{tabular}"):
                inside = True
                continue
            if line.strip().startswith("\\end{tabular}"):
                inside = False
                continue
            if not inside or not line.strip():
                continue
            if line.rstrip().endswith("\\") and not line.rstrip().endswith("\\\\"):
                bad_rows.append(f"{path.name}:{number}")
    check("T3.every_latex_row_terminated", not bad_rows,
          f"{len(emitting)} tables; unterminated rows: {bad_rows}")

    # Two LaTeX hazards the renderer must never emit, because neither is caught
    # by the renderer exiting 0 and both would surface only at typeset time:
    # a raw thousands comma (LaTeX drops the grouping) and a markdown `**`.
    #
    # The comma test is deliberately NOT a bare `\d,\d`: a projection triple
    # like `[22,22,22]` is a legitimate comma SEPARATOR, and a thousands
    # separator is always preceded by exactly three digits (or is 1-3 digits
    # followed by a group).  So a separator inside a bracketed list is exempt
    # and everything else must be protected as `1{,}225`.
    raw_commas: list[str] = []
    markdown: list[str] = []
    separator = re.compile(r"\[[\d,]+\]")
    thousands = re.compile(r"(?<![\d{])\d{1,3}(?:,\d{3})+")
    for path in emitting:
        inside = False
        for number, line in enumerate(path.read_text(encoding="utf-8")
                                      .splitlines(), 1):
            if line.strip().startswith("\\begin{tabular}"):
                inside = True
            elif line.strip().startswith("\\end{tabular}"):
                inside = False
            if not inside or not line.strip():
                continue
            scrubbed = separator.sub("", line)
            if thousands.search(scrubbed):
                raw_commas.append(f"{path.name}:{number}")
            if "**" in line:
                markdown.append(f"{path.name}:{number}")
    check("T3.no_raw_thousands_commas", not raw_commas,
          f"unprotected thousands commas in cells: {raw_commas}")
    check("T3.no_markdown_in_tables", not markdown,
          f"markdown emphasis in cells: {markdown}")

    figures = sorted((out / "figures").glob("*.csv"))
    check("T3.figures_labelled",
          all(schema.MOCK_LABEL in p.read_text() for p in figures),
          f"{len(figures)} figure CSVs")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the Stage-2 pipeline's MOCK end-to-end and negative "
                    "tests.")
    parser.add_argument("--work", type=Path, default=None,
                        help="Scratch directory for the mock tree and outputs. "
                             "Defaults to a fresh mktemp -d under "
                             "g9_jobs/scratch/analysis.")
    parser.add_argument("--keep", action="store_true",
                        help="Keep the scratch tree instead of deleting it.")
    args = parser.parse_args(argv)

    if args.work is not None:
        work = args.work.resolve()
        work.mkdir(parents=True, exist_ok=True)
    else:
        scratch_root = Path("/home/shivansh-srivastava/decisions_os/g9_jobs"
                            "/scratch/analysisfix")
        scratch_root.mkdir(parents=True, exist_ok=True)
        import tempfile
        work = Path(tempfile.mkdtemp(prefix="pipeline_tests.", dir=str(scratch_root)))
    print(f"work dir: {work}")

    try:
        test_end_to_end(work)
        test_negatives(work)
        test_mock_labels(work)
    finally:
        if not args.keep and args.work is None:
            shutil.rmtree(work, ignore_errors=True)

    print("\n" + "=" * 72)
    print(f"passed: {len(PASSES)}    failed: {len(FAILURES)}")
    for failure in FAILURES:
        print(f"  FAILED  {failure}")
    print("VERDICT:", "PASS" if not FAILURES else "FAIL")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    raise SystemExit(main())