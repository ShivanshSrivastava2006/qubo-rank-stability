"""Conformance evidence for the canonical section 5.2 H_E evaluator.

The oracle is the independent residual-form transcription in
04_encodings/g4/review_g4_energy_conformance.py — written by the reviewer,
not by this producer, and not a copy of src/g4/energy.py. Exact binary64
agreement is required. A disagreement is an R-U14-1 numerical-rule conflict
and is reported, not tolerated.

This script also demonstrates that H_E is not Qubo.energy: expanded-matrix
drift is recorded against the D015 tau at c_H=2048. Agreement everywhere
with the expansion would mean the evaluator reimplemented the QUBO matrix.

Fail-closed checks use explicit raise and are executed under python3 -O as
well as python3. No search, minimum, tie set, classification, or sweep.
Writes nothing.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile


def _forbidden_operations(source: str) -> tuple[str, ...]:
    """Return structural violations; raise on syntax or ambiguous indirection.

    Comments and all string literals are inert unless a string is used as the
    target of ``getattr`` or ``__import__``.  Dynamic forms of either primitive
    fail closed because their target cannot be proven safe statically. This
    verifies only the explicitly enumerated AST structures, not a universal guarantee.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise ValueError("energy source is not parseable Python") from error

    findings: set[str] = set()
    math_names = {"fsum", "fma", "pow"}
    math_roots = {"math"}
    numpy_roots = {"numpy", "np"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "math":
                    math_roots.add(alias.asname or "math")
                if alias.name == "numpy" or alias.name.startswith("numpy."):
                    numpy_roots.add(alias.asname or alias.name.split(".", 1)[0])
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root == "numpy":
                    findings.add("NumPy import")
                if alias.name == "math" and alias.asname:
                    # Aliasing math is safe by itself; attribute nodes below
                    # identify fsum/fma/pow regardless of the alias spelling.
                    pass
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "numpy" or module.startswith("numpy."):
                findings.add("NumPy import")
            if module == "math" and any(alias.name in math_names for alias in node.names):
                findings.add("imported math.fsum/fma/pow")
            if module == "builtins" and any(alias.name == "pow" for alias in node.names):
                findings.add("imported pow")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            findings.add("** exponentiation")
        elif isinstance(node, ast.Attribute):
            if node.attr in math_names:
                findings.add(f"attribute {node.attr}")
            root = node.value
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name) and root.id in numpy_roots:
                findings.add("NumPy attribute access")
            if node.attr in {"add_linear", "add_pair"}:
                findings.add("QUBO assembly call")
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in math_names:
                findings.add(f"direct/aliased {node.id}")
            if node.id == "pow":
                findings.add("pow call/reference")
            if node.id in numpy_roots:
                findings.add("NumPy name access")
            if node.id == "Qubo":
                findings.add("Qubo reference")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "getattr":
                if len(node.args) < 2 or not isinstance(node.args[1], ast.Constant) \
                        or not isinstance(node.args[1].value, str):
                    if (node.args and isinstance(node.args[0], ast.Name)
                            and node.args[0].id in math_roots | numpy_roots):
                        findings.add("ambiguous prohibited-module getattr")
                elif node.args[1].value in math_names:
                    if isinstance(node.args[0], ast.Name) and node.args[0].id in math_roots | numpy_roots:
                        findings.add(f"indirect {node.args[1].value}")
                elif isinstance(node.args[0], ast.Name) and node.args[0].id in numpy_roots:
                    findings.add("indirect NumPy access")
            elif node.func.id == "__import__":
                if not node.args or not isinstance(node.args[0], ast.Constant) \
                        or not isinstance(node.args[0].value, str):
                    findings.add("ambiguous dynamic import")
                elif node.args[0].value == "numpy" or node.args[0].value.startswith("numpy."):
                    findings.add("indirect NumPy import")
        elif isinstance(node, ast.Assert):
            findings.add("assert statement")
        elif isinstance(node, ast.ClassDef) and node.name == "Qubo":
            findings.add("Qubo class")
    return tuple(sorted(findings))


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.g4 import slack, unbalanced
from src.g4.energy import (
    C_H_PRIMARY,
    exact_slack_lift,
    objective,
    residuals,
    slack_energy,
    tau,
    unbalanced_energy,
)
from src.g4.instance import Instance, load_instance
from src.g4.parameters import load_coefficients


INSTANCE_PATH = ROOT / "research/canonical/stage1_instance.json"
LEDGER_PATH = ROOT / "research/g4/G4_PRIMARY_LEDGER.json"
ADNYE_001 = ROOT / "research/adnye/ADNYE-001_Lambda_ref.json"
REVIEW_PATH = ROOT / "04_encodings/g4/review_g4_energy_conformance.py"
REVIEW_SHA256 = "cff4f778b18330933a9e5063a3a31cd8a9b4681e1525f881464b947cf97705f1"
MEASURED_MAX_NORMALIZED_DRIFT = float.fromhex("0x1.9e1aaac6499cfp-36")
DRIFT_SAFETY_FACTOR = 8.0
ALGEBRA_TOLERANCE = MEASURED_MAX_NORMALIZED_DRIFT * DRIFT_SAFETY_FACTOR


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _require_review_digest(path: Path) -> bytes:
    require(path.is_file(), "independent review probe is missing")
    buffer = path.read_bytes()
    actual = hashlib.sha256(buffer).hexdigest()
    require(actual == REVIEW_SHA256,
            f"independent review probe digest mismatch: {actual} != {REVIEW_SHA256}")
    return buffer


def load_review():
    buffer = _require_review_digest(REVIEW_PATH)
    import types
    module = types.ModuleType("review_g4_energy_conformance")
    module.__file__ = str(REVIEW_PATH)
    code = compile(buffer, str(REVIEW_PATH), "exec")
    exec(code, module.__dict__)
    return module


def check_review_digest_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as directory:
        altered = Path(directory) / "review_g4_energy_conformance.py"
        altered.write_bytes(REVIEW_PATH.read_bytes() + b"\n# digest alteration\n")
        try:
            _require_review_digest(altered)
        except AssertionError:
            pass
        else:
            raise AssertionError("digest-altered independent review probe was accepted")
    print("PASS reviewer oracle is pinned before loading and digest alteration fails closed")


def check_source_is_residual_ledger() -> None:
    raw = (ROOT / "src/g4/energy.py").read_text(encoding="utf-8")
    findings = _forbidden_operations(raw)
    require(not findings, f"energy.py contains structurally forbidden operations: {findings}")
    print("PASS energy.py is a residual-form ledger (no detected FMA/pow/fsum/NumPy)")


def check_structural_detector_self_tests() -> None:
    prohibited = {
        "direct attribute": "import math\nx = math.fsum([1.0])\n",
        "imported alias": "from math import fsum as total\nx = total([1.0])\n",
        "attribute alias": "import math as m\nx = m.fma(1.0, 2.0, 3.0)\n",
        "indirect fsum": "import math\nx = getattr(math, 'fsum')([1.0])\n",
        "pow call": "x = pow(2.0, 3.0)\n",
        "pow operator": "x = 2.0 ** 3.0\n",
        "math.pow attribute": "import math\nx = math.pow(2.0, 3.0)\n",
        "from math import pow": "from math import pow\nx = pow(2.0, 3.0)\n",
        "import math as m pow": "import math as m\nx = m.pow(2.0, 3.0)\n",
        "NumPy import": "import numpy as numerical\nx = numerical.sum([1.0])\n",
        "indirect NumPy": "x = __import__('numpy').sum([1.0])\n",
        "ambiguous getattr": "import math\nname = input()\nx = getattr(math, name)\n",
    }
    for label, source in prohibited.items():
        require(_forbidden_operations(source), f"structural detector missed {label}")
    safe = '''\n"""math.fsum, math.fma, pow/**, and numpy are prose only."""\n# from math import fsum\nMESSAGE = "unrelated fsum and numpy text"\ndef function(**kwargs):\n    return kwargs.get("pow", "math.fma")\nclass Dummy:\n    pass\nd = Dummy()\nx = getattr(d, "fsum", None)\n'''
    require(not _forbidden_operations(safe),
            f"structural detector falsely rejected inert prose/**kwargs: {_forbidden_operations(safe)}")
    try:
        _forbidden_operations("def broken(:\n")
    except ValueError:
        pass
    else:
        raise AssertionError("unparseable source did not fail closed")
    print("PASS structural detector self-tests: direct/aliased/indirect evasions rejected; inert prose accepted")


def check_fail_closed(instance, review) -> None:
    x = tuple(0 for _ in range(20))
    try:
        objective(instance, x[:-1])
    except ValueError:
        pass
    else:
        raise AssertionError("short x did not fail closed")
    try:
        objective(instance, tuple(2 if i == 0 else 0 for i in range(20)))
    except ValueError:
        pass
    else:
        raise AssertionError("non-bit x did not fail closed")

    bad_mu = Instance(
        tickers=instance.tickers,
        sectors=instance.sectors,
        mu=(float("nan"),) + instance.mu[1:],
        sigma=instance.sigma,
        prices=instance.prices,
        kappa_risk=instance.kappa_risk,
        K=instance.K,
        C=instance.C,
        B=instance.B,
    )
    try:
        objective(bad_mu, x)
    except ValueError:
        pass
    else:
        raise AssertionError("nonfinite mu did not fail closed")

    try:
        tau(0.0, 0.0, 0.0, C_H_PRIMARY)
    except ValueError:
        pass
    else:
        raise AssertionError("nonpositive Lambda_ref did not fail closed")
    try:
        tau(0.0, 0.0, -1.0, C_H_PRIMARY)
    except ValueError:
        pass
    else:
        raise AssertionError("negative Lambda_ref did not fail closed")
    try:
        tau(0.0, 0.0, 1.0, 0.0)
    except ValueError:
        pass
    else:
        raise AssertionError("nonpositive tolerance multiplier did not fail closed")
    try:
        tau(float("nan"), 0.0, 1.0, C_H_PRIMARY)
    except ValueError:
        pass
    else:
        raise AssertionError("nonfinite tau input did not fail closed")

    altered = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    altered["coefficient_ledger"]["cardinality"][0]["alpha_hex"] = "0x0.0p+0"
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "altered.json"
        path.write_text(json.dumps(altered), encoding="utf-8")
        try:
            load_coefficients(path, 0, 0, 0)
        except ValueError:
            pass
        else:
            raise AssertionError("digest-invalid ledger did not fail closed")

    coefficients = load_coefficients(LEDGER_PATH, 0, 0, 0)
    try:
        slack_energy(instance, x, tuple(0 for _ in range(18)), coefficients)
    except ValueError:
        pass
    else:
        raise AssertionError("wrong-length slack auxiliary did not fail closed")
    print("PASS fail-closed: nonfinite input, nonpositive Lambda_ref/c, digest-invalid ledger")


def check_cross_agreement_and_expansion_drift(instance, review, lambda_ref: float) -> None:
    feasible = review.feasible_states(instance)
    require(len(feasible) == 976, f"unexpected feasible population {len(feasible)}")
    rng = review.random.Random(review.SEED)
    infeasible = review.infeasible_sample(instance, feasible, review.INFEASIBLE_SAMPLE, rng)
    cached = {x: (review.objective_value(instance, x), review.residual_triple(instance, x))
              for x in feasible}
    lifts = {x: review.exact_lift(instance, x) for x in feasible}
    for x in feasible:
        require(exact_slack_lift(instance, x) == lifts[x], "exact slack lift disagrees with the independent probe")
        require(objective(instance, x) == cached[x][0], "objective disagrees with the independent probe")
        require(residuals(instance, x) == cached[x][1], "residuals disagree with the independent probe")
    for x, _ in infeasible:
        if x not in cached:
            cached[x] = (review.objective_value(instance, x), review.residual_triple(instance, x))
            require(objective(instance, x) == cached[x][0], "infeasible objective disagrees with the independent probe")
            require(residuals(instance, x) == cached[x][1], "infeasible residuals disagree with the independent probe")

    rows = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))["grid_rule"]["N_axis"]
    keys = ("slack_feasible", "unbalanced_feasible", "slack_infeasible", "unbalanced_infeasible")
    worst_gap = {key: (0.0, None) for key in keys}
    worst_ratio = {key: (0.0, None) for key in keys}
    n_equal_expansion = {key: 0 for key in keys}
    n_states = {key: 0 for key in keys}

    for index in range(rows):
        coefficients = load_coefficients(LEDGER_PATH, index, index, index)
        slack_qubo = slack.formulate(instance, coefficients)
        unbalanced_qubo = unbalanced.formulate(instance, coefficients)
        for label, states in (("feasible", [(x, lifts[x]) for x in feasible]),
                              ("infeasible", infeasible)):
            for x, auxiliary in states:
                reference = review.slack_energy(instance, x, auxiliary, coefficients, cached[x])
                produced = slack_energy(instance, x, auxiliary, coefficients)
                if produced != reference:
                    raise AssertionError(
                        f"R-U14-1: slack H_E disagrees with the independent section 5.2 "
                        f"transcription at row {index}: produced {produced!r} vs reference {reference!r}"
                    )
                expanded = slack_qubo.energy(tuple(x) + tuple(auxiliary))
                require(math.isfinite(expanded), f"nonfinite slack Qubo.energy at row {index}")
                gap = abs(produced - expanded)
                algebra = ALGEBRA_TOLERANCE * (1.0 + abs(produced))
                require(gap <= algebra,
                        f"slack expansion algebra disagrees with H_E at row {index}: "
                        f"{produced!r} vs {expanded!r}")
                key = f"slack_{label}"
                n_states[key] += 1
                if gap == 0.0:
                    n_equal_expansion[key] += 1
                scale = tau(produced, expanded, lambda_ref, C_H_PRIMARY)
                ratio = gap / scale
                if gap > worst_gap[key][0]:
                    worst_gap[key] = (gap, index)
                if ratio > worst_ratio[key][0]:
                    worst_ratio[key] = (ratio, index)

                reference = review.unbalanced_energy(instance, x, coefficients, cached[x])
                produced = unbalanced_energy(instance, x, coefficients)
                if produced != reference:
                    raise AssertionError(
                        f"R-U14-1: unbalanced H_E disagrees with the independent section 5.2 "
                        f"transcription at row {index}: produced {produced!r} vs reference {reference!r}"
                    )
                expanded = unbalanced_qubo.energy(tuple(x))
                require(math.isfinite(expanded), f"nonfinite unbalanced Qubo.energy at row {index}")
                gap = abs(produced - expanded)
                algebra = ALGEBRA_TOLERANCE * (1.0 + abs(produced))
                require(gap <= algebra,
                        f"unbalanced expansion algebra disagrees with H_E at row {index}: "
                        f"{produced!r} vs {expanded!r}")
                key = f"unbalanced_{label}"
                n_states[key] += 1
                if gap == 0.0:
                    n_equal_expansion[key] += 1
                scale = tau(produced, expanded, lambda_ref, C_H_PRIMARY)
                ratio = gap / scale
                if gap > worst_gap[key][0]:
                    worst_gap[key] = (gap, index)
                if ratio > worst_ratio[key][0]:
                    worst_ratio[key] = (ratio, index)

    print(
        f"PASS exact binary64 agreement with the independent section 5.2 transcription "
        f"over {len(feasible)} feasible lifts and {len(infeasible)} infeasible states "
        f"at all {rows} primary rows"
    )
    print()
    print("REPORTED — canonical H_E vs Qubo.energy binary64 drift, against D015 tau(H_E, expanded) at c_H=2048:")
    any_drift = False
    for key in keys:
        gap, gap_row = worst_gap[key]
        ratio, ratio_row = worst_ratio[key]
        equal = n_equal_expansion[key]
        total = n_states[key]
        if gap > 0.0:
            any_drift = True
        print(
            f"     {key:22s} max gap {gap:.12e} (row {gap_row})"
            f"   max gap/tau {ratio:10.1f} (row {ratio_row})"
            f"   equal {equal}/{total}"
        )
    require(any_drift,
            "H_E agreed with Qubo.energy everywhere — the evaluator reimplemented the expansion")
    require(worst_gap["slack_feasible"][0] > 0.0,
            "slack feasible H_E agreed with Qubo.energy everywhere")
    require(worst_gap["unbalanced_feasible"][0] > 0.0,
            "unbalanced feasible H_E agreed with Qubo.energy everywhere")
    print("PASS H_E is not the expanded matrix: drift is present and recorded against tau")


def main() -> int:
    review = load_review()
    instance = load_instance(INSTANCE_PATH)
    lambda_ref = float(json.loads(ADNYE_001.read_text(encoding="utf-8"))["value"])
    require(math.isfinite(lambda_ref) and lambda_ref > 0.0, "Lambda_ref must be finite and positive")
    check_source_is_residual_ledger()
    check_structural_detector_self_tests()
    check_review_digest_fail_closed()
    check_fail_closed(instance, review)
    check_cross_agreement_and_expansion_drift(instance, review, lambda_ref)
    print()
    print("RESULT: PASS — bounded G4 H_E evaluator evidence only; no search, minimum,")
    print("        tie set, classification, or sweep was computed. Not a Gate-4 exit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
