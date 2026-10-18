#!/usr/bin/env python3
"""Offline synthetic fixtures and isolated parallel mutation audit for Option A."""
from __future__ import annotations

import ast
from concurrent.futures import ProcessPoolExecutor, as_completed
import copy
import hashlib
from functools import lru_cache
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9 import stage2_reference_seal as S
from research.g9 import pilot_stage2_cpu_cost as pilot
from src.g4.energy import tau
from src.g4.classification import DecodedClassifier, OriginalObjectiveService
from src.g5.certify import decode_x_e, classify_t_e
from src.g5.domains import BinaryDomain


class FixtureError(RuntimeError):
    pass


def check(condition, message):
    if not condition:
        raise FixtureError(message)


def refused(operation, *args):
    try:
        operation(*args)
    except S.ReferenceSealError:
        return
    raise FixtureError("invalid seal or input was accepted")


def h(label):
    return hashlib.sha256(label.encode()).hexdigest()


def inputs():
    value = {key: h(key) for key in S.HASH_FIELDS}
    value["production_identity_hash"] = h("production")
    value["additional_input_hashes"] = {"ground_truth_digest": h("truth")}
    return value


def rows():
    return [
        {"coordinate": {"kind": "primary", "r": "1", "point": [30, 30, 30],
                        "pair": [2048, 2048]}, "encoding": "unbalanced"},
        {"coordinate": {"kind": "primary", "r": "1", "point": [30, 30, 30],
                        "pair": [2048, 2048]}, "encoding": "slack"},
    ]


@lru_cache(maxsize=1)
def _streams():
    return pilot.reference_values_block(0, 8, ("row0",))[3]

def frozen(coordinate, encoding):
    # The energy stream is evaluated by the unchanged, pure-Python pilot path.
    stream = _streams()[("row0", encoding)]
    minimum = min(stream)
    index = stream.index(minimum)
    flags = [sum((1 << i) for i, c_h in enumerate((1024, 2048, 4096))
                 if abs(y - minimum) <= tau(y, minimum, pilot.E.LAMBDA_REF, c_h))
             for y in stream]
    binary = BinaryDomain(20)
    classifier = DecodedClassifier(OriginalObjectiveService(
        lambda x: float(sum(x)), float(pilot.E.LAMBDA_REF), 2048.0),
        lambda x: sum(x) <= 1)
    tied = [position for position, flag in enumerate(flags) if flag & 2]
    # The fixture's small prefix has a single canonical slack lift at each state.
    decoded = decode_x_e(tied, lambda position: binary[position])
    reconstruction = {"pair": coordinate["pair"], "set_label":
                      classify_t_e(decoded, classifier, 0.0),
                      "tie_count": len(tied)}
    import struct
    return {"energy_minimum_words": [struct.pack(">d", minimum).hex()],
            "canonical_minimum_index": index, "tie_flags": flags,
            "d015_d016_reconstruction": reconstruction}


def fast():
    check(S.FORMAT == "decisions_os/g9_section_b2_python_reference_seal/v1",
          "seal format identifier changed")
    refused(S._json, object())
    source = inputs()
    coordinates = rows()
    direct = [frozen(row["coordinate"], row["encoding"]) for row in coordinates]
    computed = S.precompute(source, coordinates, frozen)
    check([row["result"] for row in computed] == direct, "precompute differs from frozen Python")
    default = {**source, "frozen_reference": frozen}
    check([row["result"] for row in S.precompute(default, coordinates)] == direct,
          "default frozen reference differs")
    sealed = S.seal(default, coordinates, source["production_identity_hash"])
    session = {**source, "coordinates": coordinates}
    opened = S.open_for_session(sealed, session)
    for row, expected in zip(coordinates, direct):
        check(opened(row["coordinate"], row["encoding"]) == expected,
              "WP3-shaped callable differs from direct frozen Python")
    check(sealed == S.seal(default, coordinates, source["production_identity_hash"]),
          "seal is not deterministic")
    for key in S.HASH_FIELDS:
        changed = {**session, key: h(key + "changed")}
        refused(S.open_for_session, sealed, changed)
        changed_default = {**default, key: h(key + "changed")}
        check(S.seal(changed_default, coordinates, source["production_identity_hash"]) != sealed,
              "input change did not change seal")
    refused(S.open_for_session, sealed, {**session, "production_identity_hash": h("other")})
    refused(S.open_for_session, sealed, {**session,
            "additional_input_hashes": {"ground_truth_digest": h("other truth")}})
    check(S.seal({**default, "additional_input_hashes":
                  {"ground_truth_digest": h("other truth")}}, coordinates,
                 source["production_identity_hash"]) != sealed,
          "additional input change did not change seal")
    check(S.seal(default, coordinates, h("other")) != sealed,
          "identity change did not change seal")
    for location in (0, len(sealed)//2, len(sealed)-1):
        corrupt = bytearray(sealed)
        corrupt[location] ^= 1
        refused(S.open_for_session, bytes(corrupt), session)
    refused(S.open_for_session, sealed, {**session, "coordinates": coordinates[:1]})
    refused(S.open_for_session, sealed, {**session, "coordinates": coordinates + [
        {"coordinate": {"kind": "D013", "family": "C", "point": [30,30,30]},
         "encoding": "unbalanced"}]})
    refused(opened, {"kind": "D013", "family": "C", "point": [30,30,30]}, "unbalanced")
    d013 = [{"coordinate": {"kind": "D013", "family": family,
                            "point": [30,30,30], "inactive": "+0.0", "pair": [2048,2048]},
             "encoding": encoding} for family in ("C", "CB", "CS", "CSB")
            for encoding in S.ENCODINGS]
    dseal = S.seal(default, d013, source["production_identity_hash"])
    dopened = S.open_for_session(dseal, {**source, "coordinates": d013})
    check(dopened(d013[0]["coordinate"], "unbalanced") == frozen(d013[0]["coordinate"], "unbalanced"),
          "explicit D013 branch missing")
    refused(dopened, {**d013[0]["coordinate"], "family": "not-requested"}, "unbalanced")
    # Recomputed digest cannot mask a changed result, an entry census change, or a bad row.
    doc = json.loads(sealed)
    def resign(value):
        body = {"manifest": value["manifest"], "results": value["results"]}
        value["content_sha256"] = S._digest(body)
        return S._json(value)
    altered = copy.deepcopy(doc)
    altered["results"][0]["result_sha256"] = h("bad row digest")
    refused(S.open_for_session, resign(altered), session)
    altered = copy.deepcopy(doc)
    altered["results"][0]["extra"] = "unexpected"
    refused(S.open_for_session, resign(altered), session)
    altered = copy.deepcopy(doc)
    altered["unexpected"] = "extra"
    refused(S.open_for_session, S._json(altered), session)
    refused(S.open_for_session, sealed + b" ", session)
    altered = copy.deepcopy(doc)
    altered["content_sha256"] = h("wrong content")
    refused(S.open_for_session, S._json(altered), session)
    altered = copy.deepcopy(doc)
    altered["results"][0]["result"]["canonical_minimum_index"] += 1
    refused(S.open_for_session, resign(altered), session)
    altered = copy.deepcopy(doc)
    altered["results"].pop()
    refused(S.open_for_session, resign(altered), session)
    altered = copy.deepcopy(doc)
    altered["results"][0]["encoding"] = "slack"
    refused(S.open_for_session, resign(altered), session)
    altered = copy.deepcopy(doc)
    altered["manifest"]["coordinates"] = coordinates[:1]
    refused(S.open_for_session, resign(altered), session)
    altered = copy.deepcopy(doc)
    altered["manifest"]["format"] = "wrong"
    refused(S.open_for_session, resign(altered), session)
    # Every result field is independently checked; malformed inputs must refuse.
    for field, replacement in (("energy_minimum_words", []),
                               ("canonical_minimum_index", True),
                               ("tie_flags", [8]),
                               ("d015_d016_reconstruction", {}),
                               ("energy_minimum_words", ["bad"]),
                               ("extra", "unexpected")):
        def bad_runner(coord, enc, field=field, replacement=replacement):
            return {**frozen(coord, enc), field: replacement}
        refused(S.precompute, source, coordinates, bad_runner)
    def bad_nested(coord, enc):
        value = frozen(coord, enc)
        value["d015_d016_reconstruction"]["bad"] = object()
        return value
    refused(S.precompute, source, coordinates, bad_nested)
    def bad_reconstruction_float(coord, enc):
        value = frozen(coord, enc)
        value["d015_d016_reconstruction"]["bad"] = 0.1
        return value
    refused(S.precompute, source, coordinates, bad_reconstruction_float)
    def bad_index_bool(coord, enc):
        value = frozen(coord, enc)
        value["canonical_minimum_index"] = True
        value["tie_flags"][1] = 7
        return value
    refused(S.precompute, source, coordinates, bad_index_bool)
    def bad_word(coord, enc):
        value = frozen(coord, enc)
        value["energy_minimum_words"][0] = "bad"
        return value
    refused(S.precompute, source, coordinates, bad_word)
    def empty_stream(coord, enc):
        value = frozen(coord, enc)
        value["energy_minimum_words"] = []
        value["tie_flags"] = []
        return value
    refused(S.precompute, source, coordinates, empty_stream)
    # None, bool, int, float, str, bytes, list, dict, unhashable set and nested
    # wrong types are all refused with the typed error, never a raw Python one.
    for malformed in (None, True, 7, 0.1, "bad", b"bad", [], {}, {"x": []}, [[{}]],
                      {1, 2}, {"nested": [None, {"deep": False}]}, ("unhashable",)):
        refused(S.precompute, malformed, coordinates, frozen)
        refused(S.precompute, source, malformed, frozen)
        refused(S.precompute, source, coordinates, malformed)
        refused(S.seal, source, coordinates, source["production_identity_hash"], malformed)
        refused(S.seal, malformed, coordinates, source["production_identity_hash"], frozen)
        refused(S.seal, source, malformed, source["production_identity_hash"], frozen)
        refused(S.seal, source, coordinates, malformed, frozen)
        refused(S.open_for_session, malformed, session)
        refused(S.open_for_session, sealed, malformed)
        refused(opened, malformed, "unbalanced")
        refused(opened, coordinates[0]["coordinate"], malformed)
    for invalid in (
        [{"coordinate": {}, "encoding": "unbalanced"}],
        [{"coordinate": {"x": True}, "encoding": "unbalanced"}],
        [{"coordinate": {"x": [1, {"nested": False}]}, "encoding": "unbalanced"}],
        [{"coordinate": {1: "x"}, "encoding": "unbalanced"}],
        [{"coordinate": {"x": "a"}, "encoding": "wrong"}],
        [coordinates[0], coordinates[0]],
        [{"coordinate": {"x": "a"}}],
    ):
        refused(S.precompute, source, invalid, frozen)
    for malformed in (None, True, 7, 0.1, "bad", b"bad", [], {}, {"x": []}, [[{}]],
                      {1, 2}, {"nested": [None, {"deep": False}]}):
        refused(S.precompute, {**source, "instance_digest": malformed}, coordinates, frozen)
        refused(S.open_for_session, sealed,
                {**session, "coordinates": malformed})
    refused(S.precompute, source, coordinates, None)
    refused(S.precompute, {**source, "additional_input_hashes": {"x": None}}, coordinates, frozen)
    refused(S.precompute, {**source, "additional_input_hashes": {"instance_digest": h("x")}}, coordinates, frozen)
    mutable_session = {**session}
    live = S.open_for_session(sealed, mutable_session)
    mutable_session["instance_digest"] = h("changed after open")
    refused(live, coordinates[0]["coordinate"], "unbalanced")
    identity_session = {**session}
    identity_live = S.open_for_session(sealed, identity_session)
    identity_session["production_identity_hash"] = h("changed identity after open")
    refused(identity_live, coordinates[0]["coordinate"], "unbalanced")
    coordinate_session = {**session}
    coordinate_live = S.open_for_session(sealed, coordinate_session)
    coordinate_session["coordinates"] = copy.deepcopy(coordinates)
    coordinate_session["coordinates"][0]["coordinate"]["point"][0] = 29
    refused(coordinate_live, coordinates[0]["coordinate"], "unbalanced")
    # A copy is returned; consumers cannot rewrite subsequent answers.
    answer = opened(coordinates[0]["coordinate"], "unbalanced")
    answer["tie_flags"][0] = 99
    check(opened(coordinates[0]["coordinate"], "unbalanced") == direct[0],
          "callable exposed mutable seal state")
    print("PASS fast synthetic Option A seal fixtures")


def _mutant(task):
    line, ordinal, label, original, target, replacement = task
    with tempfile.TemporaryDirectory(prefix="g9-seal-mutant-") as tmp:
        project = Path(tmp) / "project"
        shutil.copytree(ROOT, project, copy_function=os.link, symlinks=True)
        # Break this hard link before editing, so the original tree stays immutable.
        path = project / "research/g9/stage2_reference_seal.py"
        path.unlink()
        path.write_text(original.replace(target, replacement, 1))
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
               "PYTHONPATH": str(project) + os.pathsep + str(ROOT)}
        result = subprocess.run([sys.executable, "-B", str(project /
                                 "research/g9/verify_stage2_reference_seal_fixtures.py"), "--fast"],
                                cwd=project, env=env, capture_output=True, text=True, timeout=120)
        return (line, ordinal, label, result.returncode != 0,
                result.stdout[-200:] + result.stderr[-300:])


def sweep():
    source = (ROOT / "research/g9/stage2_reference_seal.py").read_text()
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    tasks = []
    for node in ast.walk(tree):
        check_call = (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and
                      isinstance(node.value.func, ast.Name) and node.value.func.id == "_require")
        refusal_raise = isinstance(node, ast.Raise)
        refusal_guard = (isinstance(node, ast.If) and isinstance(node.test, ast.UnaryOp)
                         and isinstance(node.test.op, ast.Not) and
                         isinstance(node.test.operand, ast.Name) and
                         node.test.operand.id == "condition")
        if check_call or refusal_raise or refusal_guard:
            target = "".join(lines[node.lineno-1:node.end_lineno])
            tasks.append((node.lineno, len(tasks), "whole check", source, target,
                          " " * node.col_offset + "pass\n"))
            if (check_call and isinstance(node.value.args[0], ast.BoolOp) and
                    any(isinstance(child, ast.Name) and child.id == "session_inputs"
                        for child in ast.walk(node))):
                for clause in node.value.args[0].values:
                    clause_text = ast.get_source_segment(source, clause)
                    tasks.append((node.lineno, len(tasks),
                                  "post-open clause " + str(len(tasks)), source,
                                  clause_text, "True"))
    format_line = next(line for line in lines if line.startswith("FORMAT = "))
    tasks.append((25, len(tasks), "format literal", source, format_line,
                  "FORMAT = None\n"))
    start = time.monotonic()
    with ProcessPoolExecutor(max_workers=4) as pool:
        # Sort by (line, ordinal), not line alone: as_completed yields in
        # completion order, and a line-only stable sort would leave rows that
        # share a line number in a nondeterministic order between runs.
        results = sorted((future.result() for future in as_completed(
            [pool.submit(_mutant, task) for task in tasks])), key=lambda x: (x[0], x[1]))
    survivors = [row for row in results if not row[2]]
    print("MUTATION TABLE: check | mutation applied | fixture result")
    for line, _, label, failed, detail in results:
        mutation = "replaced with pass" if label == "whole check" else "replaced with True/None"
        print(f"{label} line {line} | {mutation} | {'FAIL' if failed else 'SURVIVED'}")
        if not failed:
            print(detail)
    print(f"SWEEP: {len(survivors)} survivors / {len(results)} mutations; wall {time.monotonic()-start:.2f}s")
    check(not survivors, "mutation sweep has survivors")


if __name__ == "__main__":
    try:
        fast()
        if "--fast" not in sys.argv:
            sweep()
    except (FixtureError, S.ReferenceSealError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
