#!/usr/bin/env python3
"""Fast, non-primary checks for the bounded Gate-6 CPU trial binding."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.g6.trial_runner import (
    DIAGNOSTIC_PAIRS,
    TrialError,
    _atomic_write_new,
    fixture_plan,
    run_bounded_cpu_trial,
    _render_certification,
)
from src.g4.instance import load_instance


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TrialError(message)


def main() -> int:
    try:
        plan = fixture_plan()
        _require(plan["trial_ids"] == [
            "d011_primary_30", "v14_2x_embedded_primary_30",
            "v14_2x_lower_endpoint", "v14_2x_upper_endpoint",
        ], "bounded-trial point selection drift")
        _require(tuple(tuple(pair) for pair in plan["diagnostic_pairs"]) == DIAGNOSTIC_PAIRS,
                 "D015 diagnostic-pair selection drift")
        _require(plan["scientific_outputs"] == "intentionally absent",
                 "fixture path has crossed the scientific-output boundary")
        tree = ast.parse((ROOT / "src/g6/trial_runner.py").read_text(encoding="utf-8"))
        _require(not any(isinstance(node, ast.Assert) for node in ast.walk(tree)),
                 "trial runner must not rely on assert")
        instance = load_instance(ROOT / "research/canonical/stage1_instance.json")
        x = (0,) * len(instance.tickers)

        class DiagnosticClassifier:
            def label(self, _x, _f_star):
                return "B"

            def label_set(self, _xs, _f_star):
                return "B"

        diagnostic = _render_certification(
            (0.0, [x], [x], "A"), "unbalanced", instance, DiagnosticClassifier(), 0.0, 1.0, 2048
        )
        _require(diagnostic["set_label"] == "B" and diagnostic["X_E"][0]["atomic_label"] == "B",
                 "D015 diagnostic rendering retained a primary-c_f set label")
        with tempfile.TemporaryDirectory(prefix="g6-trial-fixture-") as temporary:
            target = Path(temporary) / "artifact.json"
            _atomic_write_new(target, {"fixture": "bounded-cpu-trial"})
            original = target.read_bytes()
            try:
                _atomic_write_new(target, {"fixture": "replacement"})
            except TrialError:
                pass
            else:
                raise TrialError("trial artifact writer accepted an overwrite")
            _require(target.read_bytes() == original, "trial artifact writer changed an existing file")
            guard = Path(temporary) / "must-not-run"
            guard.mkdir()
            previous = os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
            try:
                try:
                    run_bounded_cpu_trial(Path(temporary) / "must-not-run")
                except TrialError:
                    pass
                else:
                    raise TrialError("bounded trial accepted an unqualified environment")
            finally:
                if previous is not None:
                    os.environ["PYTHONDONTWRITEBYTECODE"] = previous
        print("PASS bounded CPU trial fixtures; no Gate-5 corpus read or energy enumeration")
        return 0
    except TrialError as exc:
        print(f"FAIL bounded CPU trial fixtures: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
