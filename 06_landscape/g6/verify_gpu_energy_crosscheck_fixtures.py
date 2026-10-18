#!/usr/bin/env python3
"""Hardware-free fixtures for the bounded GPU unbalanced-energy cross-check.

These checks need no HIP compiler, no GPU, and no Gate-5 corpus access.  They
prove the static contract (flags, pragmas, pins, no assert), the state-set
declaration, the input/output encodings, the comparator, and the fail-closed
behaviour of ``--run`` on a host without hipcc.  They evaluate the canonical
energy only on a handful of synthetic-coefficient states to exercise the
comparator; no ledger-point energy is computed here.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MODULE = ROOT / "research/g6/gpu_qualification/energy_crosscheck.py"
RUNNER = ROOT / "research/g6/run_gpu_energy_crosscheck.py"
HIP_SOURCE = ROOT / "research/g6/gpu_qualification/gpu_unbalanced_energy_crosscheck.hip.cpp"
BOUNDARY = ROOT / "research/g6/verify_gpu_energy_crosscheck_import_boundary.py"
HOST_EMULATION = ROOT / "research/g6/verify_gpu_energy_crosscheck_host_emulation.py"
NEW_PYTHON = (MODULE, RUNNER, Path(__file__).resolve(), BOUNDARY, HOST_EMULATION)

EXPECTED_POINT_IDS = (
    "d011_primary_ell_30",
    "v14_2x_row_70_embedded_primary",
    "v14_2x_row_0_lower_endpoint",
    "v14_2x_row_110_upper_endpoint",
)
# Regression pin of the declared state set (count and little-endian digest).
EXPECTED_STATE_COUNT = 1710
EXPECTED_STATE_DIGEST = "b38bd5158f397e8f7382a872ccd6794e224f46329fe0374dfbc8ac295344d5be"


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def load_module():
    specification = importlib.util.spec_from_file_location("g6_gpu_energy_crosscheck_fixture", MODULE)
    require(specification is not None and specification.loader is not None, "module unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def tree_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(ROOT)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def check_static(module) -> None:
    hip_text = HIP_SOURCE.read_text(encoding="utf-8")
    require("#pragma clang fp contract(off)" in hip_text, "HIP source lacks contract(off) pragma")
    require('"gfx1201", 7) == 0' in hip_text and "hipSetDevice(selected_device)" in hip_text,
            "HIP source does not select the gfx1201 device explicitly")
    require("device zero" in hip_text, "HIP source does not document the APU/device-order hazard")
    require("scientific_outputs" in hip_text and "intentionally absent" in hip_text,
            "HIP source must declare the absent scientific output")
    # Token checks run on code only; line comments may name the forbidden
    # constructs while explaining why they are absent.
    code_only = re.sub(r"//[^\n]*", "", hip_text)
    forbidden_tokens = ("fma(", "__fma", "pow(", "sqrt(", "exp(", "log(", "-ffast-math",
                        "__builtin_fma", "atomicAdd", "__fmul_rn", "__dmul_rn", "__dadd_rn",
                        "_Float", "__fp16", "half")
    for token in forbidden_tokens:
        require(token not in code_only, f"forbidden token in HIP source: {token!r}")
    require(re.search(r"\bfloat\b", code_only) is None, "HIP source must not declare fp32 values")
    require(re.search(r"#pragma\s+clang\s+fp\s+contract\(off\)", code_only) is not None,
            "contract(off) pragma is not in code")
    for flag in module.REQUIRED_COMPILE_FLAGS:
        require(flag in module.compile_command("hipcc", Path("a"), Path("b")), f"compile command lacks {flag}")
    require(module.TARGET_ARCHITECTURE == "gfx1201", "target architecture drift")
    for source in NEW_PYTHON:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        require(not any(isinstance(node, ast.Assert) for node in ast.walk(tree)),
                f"assert is not permitted: {source.name}")


def check_pins(module) -> None:
    observed = module.verify_pinned_inputs()
    require(observed == module.PINNED_INPUTS, "pinned inputs drifted")
    require(observed[module.HIP_SOURCE_REL] == hashlib.sha256(HIP_SOURCE.read_bytes()).hexdigest(),
            "HIP source pin is stale")
    tampered = dict(module.PINNED_INPUTS)
    tampered["src/g4/energy.py"] = "0" * 64
    try:
        module.verify_pinned_inputs(tampered)
    except module.CrosscheckError as exc:
        require("src/g4/energy.py" in str(exc), "drift message does not name the drifted file")
    else:
        raise FixtureError("pin verification accepted a drifted input")


def check_points(module) -> None:
    ledgers = module.load_ledgers()
    points = module.coefficient_points(ledgers)
    require(tuple(point["point_id"] for point in points) == EXPECTED_POINT_IDS, "coefficient point drift")
    require(points[0]["primary_ell"] == 30 and points[0]["ledger_index"] == {"card": 6, "sector": 6, "budget": 6},
            "D011 primary_ell=30 row binding drift")
    require(points[1]["ledger_index"]["card"] == 70 and points[1]["coordinate_hex"] == points[0]["coordinate_hex"],
            "V-14 2x row 70 is not the embedded primary coordinate")
    require(points[2]["ledger_index"]["card"] == 0 and points[3]["ledger_index"]["card"] == 110,
            "V-14 2x endpoint binding drift")
    for point in points:
        require(point["coefficients_hex"]["alpha"] == point["coefficients"].alpha.hex(),
                "reported coefficient hex differs from loaded value")
        require(point["ledger_content_sha256"] == ledgers[point["ledger_file"]]["content_sha256"],
                "point does not cite its ledger content hash")
    # The embedded V-14 point and the D011 point share only the alpha/slack mapping.
    require(points[0]["coefficients_hex"]["alpha"] == points[1]["coefficients_hex"]["alpha"],
            "embedded primary alpha differs between D011 and V-14 2x")
    require(points[0]["coefficients_hex"]["sector_linear"] != points[1]["coefficients_hex"]["sector_linear"],
            "D011 curvature-match mapping unexpectedly equals D006 r=1 mapping")


def check_states(module, instance) -> tuple[int, ...]:
    states, families = module.declared_states(instance)
    again, families_again = module.declared_states(instance)
    require(states == again and families == families_again, "state declaration is not deterministic")
    require(len(states) == len(set(states)) == EXPECTED_STATE_COUNT, "declared state count drift")
    require(module.states_digest(states) == EXPECTED_STATE_DIGEST, "declared state digest drift")
    require(all(0 <= mask <= module.FULL_MASK for mask in states), "state outside 20 bits")
    require(states[0] == 0 and states[1] == module.FULL_MASK, "all-zero/all-one not declared first")
    for i in range(20):
        require((1 << i) in states and (module.FULL_MASK ^ (1 << i)) in states, "single-bit family incomplete")
    for mask in module.NAMED_MASKS:
        require(mask in states, "named mask missing")
    require(families["splitmix64_seeded"] > 0 and families["low_range_0_255"] > 0, "declared families missing")
    for mask in states[:64]:
        x = module.mask_to_x(mask)
        require(len(x) == 20 and module.x_to_mask(x) == mask, "mask/x round trip failed")
        require(all(x[i] == (mask >> i) & 1 for i in range(20)), "bit order drift")
    return states


def check_encoding(module, instance, points, states) -> None:
    payload = module.encode_inputs(instance, points, states)
    words = [int.from_bytes(payload[i:i + 8], "little") for i in range(0, len(payload), 8)]
    require(len(payload) % 8 == 0, "input stream is not word aligned")
    require(words[:5] == [module.INPUT_MAGIC, module.FORMAT_VERSION, 20, len(points), len(states)],
            "input header drift")
    cursor = 5
    require(words[cursor:cursor + 20] == [module.float_bits(v) for v in instance.mu], "mu encoding drift")
    cursor += 20
    for i, row in enumerate(instance.sigma):
        require(words[cursor + 20 * i:cursor + 20 * (i + 1)] == [module.float_bits(v) for v in row],
                f"sigma row {i} encoding drift")
    cursor += 400
    require(words[cursor:cursor + 20] == [module.float_bits(v) for v in instance.prices], "price encoding drift")
    cursor += 20
    require(words[cursor:cursor + 4] == [module.float_bits(instance.kappa_risk), module.float_bits(float(instance.K)),
                                         module.float_bits(float(instance.C)), module.float_bits(instance.B)],
            "scalar encoding drift")
    cursor += 4
    for members in instance.sectors:
        ordered = sorted(members)
        require(words[cursor] == len(ordered) and words[cursor + 1:cursor + 1 + len(ordered)] == ordered,
                "sector encoding drift")
        cursor += 1 + len(ordered)
    for point in points:
        expected = [module.float_bits(getattr(point["coefficients"], name)) for name in module.COEFFICIENT_ORDER]
        require(words[cursor:cursor + 5] == expected, "coefficient encoding drift")
        cursor += 5
    require(words[cursor:] == list(states), "state encoding drift")
    require(cursor + len(states) == len(words), "input stream length drift")


def check_comparator(module, instance) -> None:
    from src.g4.parameters import Coefficients

    synthetic = Coefficients(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
    points = ({"point_id": "synthetic_unit", "coefficients": synthetic},)
    states = (0, 1, module.FULL_MASK, 0x00033)
    reference = module.python_reference_bits(instance, points, states)
    require(len(reference) == 4, "reference length drift")
    clean = module.compare_bits(reference, reference, points, states)
    require(clean["mismatches"] == 0 and clean["evaluations"] == 4 and clean["first_mismatches"] == [],
            "comparator reports mismatches on identical bits")
    corrupted = list(reference)
    corrupted[2] ^= 1
    flagged = module.compare_bits(reference, tuple(corrupted), points, states)
    require(flagged["mismatches"] == 1 and flagged["first_mismatches"] == [
        {"point_id": "synthetic_unit", "state_mask_hex": "0xfffff"}], "comparator missed a one-ulp corruption")
    require(all("hex" not in key or key == "state_mask_hex" for key in flagged["first_mismatches"][0]),
            "comparator leaked a value")
    total = len(points) * len(states)
    header = [module.OUTPUT_MAGIC, module.FORMAT_VERSION, len(points), len(states), 1]
    stream = b"".join(int(w).to_bytes(8, "little") for w in header + list(reference) + list(reference))
    device_index, device_bits, host_bits = module.decode_output(stream, len(points), len(states))
    require(device_index == 1 and device_bits == reference and host_bits == reference, "output decoding drift")
    try:
        module.decode_output(stream[:-8], len(points), len(states))
    except module.CrosscheckError:
        pass
    else:
        raise FixtureError("truncated output was accepted")
    require(total == 4, "synthetic total drift")


def check_cli() -> None:
    environment = {"PATH": "", "PYTHONDONTWRITEBYTECODE": "1"}
    before = tree_digest(ROOT / "research/g6")
    plan = subprocess.run([sys.executable, str(RUNNER)], cwd=ROOT, text=True, capture_output=True,
                          check=False, env=environment)
    require(plan.returncode == 0, "default invocation must plan without a HIP compiler: " + plan.stderr[-400:])
    payload = json.loads(plan.stdout)
    require(payload["mode"] == "plan" and payload["writes"] == "none"
            and payload["scientific_outputs"] == "intentionally absent"
            and payload["hipcc_located"] is False
            and payload["state_set"]["count"] == EXPECTED_STATE_COUNT
            and payload["planned_evaluations"] == 4 * EXPECTED_STATE_COUNT
            and [p["point_id"] for p in payload["coefficient_points"]] == list(EXPECTED_POINT_IDS),
            "plan payload drift")
    require("verdict" not in payload and "gpu_vs_python" not in payload, "plan must not carry run fields")
    explicit = subprocess.run([sys.executable, str(RUNNER), "--plan"], cwd=ROOT, text=True,
                              capture_output=True, check=False, env=environment)
    require(explicit.returncode == 0 and explicit.stdout == plan.stdout, "--plan differs from default")
    both = subprocess.run([sys.executable, str(RUNNER), "--plan", "--run"], cwd=ROOT, text=True,
                          capture_output=True, check=False, env=environment)
    require(both.returncode == 2, "--plan and --run must be mutually exclusive")
    no_hipcc = subprocess.run([sys.executable, str(RUNNER), "--run"], cwd=ROOT, text=True,
                              capture_output=True, check=False, env=environment)
    require(no_hipcc.returncode == 1 and "hipcc is unavailable" in no_hipcc.stderr and no_hipcc.stdout == "",
            "--run without hipcc must fail closed before any evaluation")
    no_env = subprocess.run([sys.executable, str(RUNNER), "--run"], cwd=ROOT, text=True,
                            capture_output=True, check=False, env={"PATH": ""})
    require(no_env.returncode == 1 and "PYTHONDONTWRITEBYTECODE=1 is required" in no_env.stderr,
            "--run without PYTHONDONTWRITEBYTECODE must fail closed")
    require(tree_digest(ROOT / "research/g6") == before, "CLI invocations changed the research/g6 tree")
    leftovers = [p for p in Path(tempfile.gettempdir()).glob("g6-gpu-energy-crosscheck-*")]
    require(not leftovers, "temporary cross-check directories were left behind")


def check_run_guard(module) -> None:
    previous = os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
    try:
        try:
            module.run_crosscheck()
        except module.CrosscheckError as exc:
            require("PYTHONDONTWRITEBYTECODE" in str(exc), "run guard message drift")
        else:
            raise FixtureError("run_crosscheck accepted an unqualified environment")
    finally:
        if previous is not None:
            os.environ["PYTHONDONTWRITEBYTECODE"] = previous


def main() -> int:
    try:
        module = load_module()
        check_static(module)
        check_pins(module)
        check_points(module)
        from src.g4.instance import load_instance

        instance = load_instance(ROOT / module.INSTANCE_REL)
        states = check_states(module, instance)
        points = module.coefficient_points(module.load_ledgers())
        check_encoding(module, instance, points, states)
        check_comparator(module, instance)
        check_run_guard(module)
        check_cli()
        forbidden = [name for name in sys.modules if name.startswith("src.g5") or name in {
            "src.g6.g5_input", "src.g6.ratified_g5_input", "src.g6.g5_digest_registry",
            "src.g6.trial_runner", "src.g6.d011_runner"}]
        require(not forbidden, "fixtures loaded a Gate-5 corpus/runner module: " + ", ".join(forbidden))
        print("PASS GPU energy cross-check fixtures; no HIP compiler, GPU, Gate-5 corpus read, or repository write")
        return 0
    except FixtureError as exc:
        print(f"FAIL GPU energy cross-check fixtures: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
