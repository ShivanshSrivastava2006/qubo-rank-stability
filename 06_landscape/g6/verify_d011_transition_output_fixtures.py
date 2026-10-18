#!/usr/bin/env python3
"""Hardware-free fixtures for the approved D011 mechanical transition output.

These checks never run a D011 computation and never create a project output
artifact.  They validate the complete input boundary, exercise the lattice,
count-table, edge, replay, and collision-refusal contracts in memory or in an
automatically removed system temporary directory.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(ROOT))

MODULE_PATH = ROOT / "src/g6/d011_transition_output.py"
RUNNER_PATH = ROOT / "research/g6/make_d011_transition_output.py"


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def load_module():
    specification = importlib.util.spec_from_file_location("g6_d011_transition_output_fixture", MODULE_PATH)
    require(specification is not None and specification.loader is not None, "transition output module is unavailable")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def input_digest() -> str:
    directory = ROOT / "research/g6/d011_curvature_companion"
    digest = hashlib.sha256()
    for path in sorted(directory.iterdir()):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def full_labels(module, checkerboard: bool) -> dict[tuple[int, int, int], str]:
    return {
        (card, sector, budget): ("A" if not checkerboard or (card + sector + budget) % 2 == 0 else "B")
        for card in range(module.d011.AXIS_COUNT)
        for sector in range(module.d011.AXIS_COUNT)
        for budget in range(module.d011.ROW_COUNT)
    }


def check_static(module) -> None:
    source_text = MODULE_PATH.read_text(encoding="utf-8")
    runner_text = RUNNER_PATH.read_text(encoding="utf-8")
    require("GATE_6_OWNER_EXECUTION_DECISIONS.md" in source_text, "owner authority is not bound")
    require("OUTPUT_SCOPE" in source_text and "face-adjacent" in source_text,
            "approved output boundary is not stated")
    require("D011Runner(" not in source_text and ".run(" not in source_text,
            "transition output may not invoke a D011 computation")
    for path in (MODULE_PATH, RUNNER_PATH, Path(__file__).resolve()):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        require(not any(isinstance(node, ast.Assert) for node in ast.walk(tree)),
                f"assert is not permitted: {path.name}")
    require("--write" in runner_text and "--reviewed" in runner_text and "--verify" in runner_text,
            "CLI does not expose the required guarded modes")
    require(module.OWNER_DECISION_SHA256 == "0d7d212dd1205a8c1c84d702f0f8b44a444b952d84c29a6a352d9a17b716e4fe",
            "owner decision pin drift")


def check_lattice_math(module) -> None:
    constant = full_labels(module, checkerboard=False)
    tables = module._count_tables(constant)
    require(tables["global_by_label"] == {"A": 2197, "B": 0, "C": 0}, "constant global counts drift")
    for axis in module.AXES:
        require(len(tables["by_axis"][axis]) == 13
                and all(row["A"] == 169 and row["B"] == row["C"] == 0
                        for row in tables["by_axis"][axis]),
                f"constant {axis} count table drift")
    require(module._unequal_face_edges(constant) == [], "constant lattice has unequal edges")

    checkerboard = full_labels(module, checkerboard=True)
    tables = module._count_tables(checkerboard)
    require(sum(tables["global_by_label"].values()) == 2197, "checkerboard counts do not cover lattice")
    edges = module._unequal_face_edges(checkerboard)
    # 3 axes * 12 steps * 13 * 13 face positions; checkerboard changes at every face.
    require(len(edges) == 3 * 12 * 13 * 13, "checkerboard face-edge population drift")
    require({edge["axis"] for edge in edges} == set(module.AXES), "edge axes drift")
    for edge in edges:
        source = tuple(edge["from"][axis] for axis in module.AXES)
        target = tuple(edge["to"][axis] for axis in module.AXES)
        require(sum(abs(a - b) for a, b in zip(source, target, strict=True)) == 1
                and edge["from"]["set_label"] != edge["to"]["set_label"],
                "emitted edge is not one unequal face")


def check_real_input_and_replay(module) -> None:
    before = input_digest()
    plan = module.build_plan()
    require(plan["writes"] == "none" and plan["shards"] == 169 and plan["coordinates"] == 2197,
            "plan population drift")
    require(len(plan["configurations"]) == 5 and all(item["encodings"] == ["unbalanced", "slack"]
                                                     for item in plan["configurations"]),
            "plan configuration coverage drift")
    payload = module.build_transition_output("fixture-independent-review")
    module.validate_transition_output(payload)
    require(payload["input_artifact"]["shard_count"] == 169
            and payload["input_artifact"]["coordinate_count"] == 2197
            and len(payload["configurations"]) == 10,
            "replayed output population drift")
    for configuration in payload["configurations"]:
        lattice = configuration["label_lattice"]
        counts = configuration["exact_integer_count_tables"]
        edges = configuration["face_adjacent_unequal_label_edges"]
        require(len(lattice) == 2197 and sum(counts["global_by_label"].values()) == 2197,
                "configuration lattice/count coverage drift")
        require(all(sum(row[label] for label in module.LABELS) == 169
                    for rows in counts["by_axis"].values() for row in rows),
                "per-axis count table coverage drift")
        require(all(edge["from"]["set_label"] != edge["to"]["set_label"] for edge in edges),
                "equal-label edge emitted")
    tampered = json.loads(json.dumps(payload))
    tampered["configurations"][0]["label_lattice"][0]["set_label"] = "B"
    tampered["content_sha256"] = hashlib.sha256(module.canonical_bytes(
        {key: value for key, value in tampered.items() if key != "content_sha256"})).hexdigest()
    try:
        module.validate_transition_output(tampered)
    except module.TransitionOutputError:
        pass
    else:
        raise FixtureError("replay validator accepted a rehashed label drift")
    require(input_digest() == before, "in-memory build altered the D011 input artifact")


def check_writer(module) -> None:
    payload = {"fixture": True}
    with tempfile.TemporaryDirectory(prefix="g6-transition-output-fixture-") as temporary:
        parent = Path(temporary)
        target = parent / "artifact.json"
        module._write_new(target, payload)
        require(target.read_bytes() == module.canonical_bytes(payload), "atomic writer bytes drift")
        original = target.read_bytes()
        try:
            module._write_new(target, {"fixture": False})
        except module.TransitionOutputError:
            pass
        else:
            raise FixtureError("writer accepted an overwrite")
        require(target.read_bytes() == original, "writer changed an existing target")
    outside = Path(tempfile.gettempdir()) / "not-a-g6-output"
    try:
        module.write_transition_output(outside, "fixture-independent-review")
    except module.TransitionOutputError as exc:
        require("under research/g6" in str(exc), "outside-output refusal drift")
    else:
        raise FixtureError("writer accepted an output directory outside research/g6")


def check_published_mirror(module) -> None:
    """Exercise guarded publication without creating anything in the repository."""
    original_root = module.ROOT
    with tempfile.TemporaryDirectory(prefix="g6-transition-output-mirror-") as temporary:
        mirror = Path(temporary)
        mirror_g6 = mirror / "research/g6"
        mirror_g6.mkdir(parents=True)
        shutil.copytree(ROOT / "research/g6/d011_curvature_companion",
                        mirror_g6 / "d011_curvature_companion")
        shutil.copytree(ROOT / "research/g6/preexecution_ledgers", mirror_g6 / "preexecution_ledgers")
        (mirror / "research/decisions").mkdir(parents=True)
        shutil.copy2(ROOT / "research/decisions/GATE_6_OWNER_EXECUTION_DECISIONS.md",
                     mirror / "research/decisions/GATE_6_OWNER_EXECUTION_DECISIONS.md")
        shutil.copy2(RUNNER_PATH, mirror_g6 / "make_d011_transition_output.py")
        module.ROOT = mirror
        try:
            output_dir = mirror_g6 / "d011_transition_output"
            input_dir = mirror_g6 / "d011_curvature_companion"
            result = module.write_transition_output(output_dir, "fixture-independent-review", input_dir)
            require(Path(result["output_file"]).is_file(), "mirror publication did not create the output")
            module.validate_published_transition_output(output_dir, input_dir, "fixture-independent-review")
            payload = json.loads((output_dir / module.OUTPUT_FILENAME).read_text(encoding="utf-8"))
            entries = payload["input_artifact"]["shard_digest_registry"]["entries"]
            require(len(entries) == 169 and entries[0]["shard_id"] == "d011__card=00__sector=00"
                    and entries[-1]["shard_id"] == "d011__card=12__sector=12",
                    "published shard digest registry drift")
            try:
                module.validate_published_transition_output(output_dir, input_dir, "different-review")
            except module.TransitionOutputError:
                pass
            else:
                raise FixtureError("published output accepted a different review identifier")
            try:
                module.write_transition_output(output_dir, "fixture-independent-review", input_dir)
            except module.TransitionOutputError:
                pass
            else:
                raise FixtureError("writer accepted an existing published directory")
            for unsafe in (mirror_g6 / "d011_curvature_companion" / "nested-output", mirror_g6):
                try:
                    module.write_transition_output(unsafe, "fixture-independent-review", input_dir)
                except module.TransitionOutputError:
                    pass
                else:
                    raise FixtureError("writer accepted an unsafe output location")
            try:
                module.load_verified_d011_input(mirror / "outside-input")
            except module.TransitionOutputError:
                pass
            else:
                raise FixtureError("input boundary accepted an outside project path")
        finally:
            module.ROOT = original_root


def main() -> int:
    try:
        module = load_module()
        check_static(module)
        check_lattice_math(module)
        check_real_input_and_replay(module)
        check_writer(module)
        check_published_mirror(module)
        print("PASS D011 transition-output fixtures; no D011 computation or project output write")
        return 0
    except (FixtureError, RuntimeError, OSError) as exc:
        print(f"FAIL D011 transition-output fixtures: {exc}", file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
