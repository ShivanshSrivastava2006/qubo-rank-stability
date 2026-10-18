#!/usr/bin/env python3
"""Hardware-free fixtures for the bounded GPU slack-energy cross-check.

These checks need no HIP compiler, no GPU, and no Gate-5 corpus access.  They
prove the static contract (flags, pragmas, pins, no assert), that the raw
state set and coefficient points are byte-identical to the unbalanced
prototype's, that every attached auxiliary is the exact residual integer
(independent oracle) and every exclusion is justified, the input/output
encodings, the comparator, and the fail-closed behaviour of ``--run`` on a
host without hipcc.  They evaluate the canonical slack energy only on a
handful of synthetic-coefficient states to exercise the comparator; no
ledger-point energy is computed here.
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
MODULE = ROOT / "research/g6/gpu_qualification/slack_energy_crosscheck.py"
UNBALANCED_MODULE = ROOT / "research/g6/gpu_qualification/energy_crosscheck.py"
RUNNER = ROOT / "research/g6/run_gpu_slack_energy_crosscheck.py"
HIP_SOURCE = ROOT / "research/g6/gpu_qualification/gpu_slack_energy_crosscheck.hip.cpp"
BOUNDARY = ROOT / "research/g6/verify_gpu_slack_energy_crosscheck_import_boundary.py"
HOST_EMULATION = ROOT / "research/g6/verify_gpu_slack_energy_crosscheck_host_emulation.py"
NEW_PYTHON = (MODULE, RUNNER, Path(__file__).resolve(), BOUNDARY, HOST_EMULATION)

EXPECTED_POINT_IDS = (
    "d011_primary_ell_30",
    "v14_2x_row_70_embedded_primary",
    "v14_2x_row_0_lower_endpoint",
    "v14_2x_row_110_upper_endpoint",
)
# Regression pins: the raw state set must equal the unbalanced prototype's,
# and the exact-lift partition of it is fixed.
EXPECTED_STATE_COUNT = 1710
EXPECTED_STATE_DIGEST = "b38bd5158f397e8f7382a872ccd6794e224f46329fe0374dfbc8ac295344d5be"
EXPECTED_LIFTED_COUNT = 293
EXPECTED_LIFTED_DIGEST = "0dde7972844658dab75d12d5d4a429a633b123a4485336ffbe76ba7a64afa03f"
EXPECTED_EXCLUDED = {"budget": 132, "sector[0]": 685, "sector[1]": 280, "sector[2]": 149, "sector[3]": 171}


class FixtureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def load_by_path(name: str, path: Path):
    specification = importlib.util.spec_from_file_location(name, path)
    require(specification is not None and specification.loader is not None, f"module unavailable: {path.name}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def prototype_tree_digest() -> str:
    """Digest of every file the prototype could plausibly touch.

    Restricted to the qualification directory and the files directly under
    ``research/g6`` so that an unrelated concurrent Gate-6 trial writing its
    own output subdirectory cannot perturb this check.
    """
    digest = hashlib.sha256()
    files = sorted(p for p in (ROOT / "research/g6/gpu_qualification").rglob("*") if p.is_file())
    files += sorted(p for p in (ROOT / "research/g6").iterdir() if p.is_file())
    for path in files:
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
    require("slack_energy_transcript_crosscheck" in hip_text, "HIP source does not name the slack probe")
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
    require(code_only.count("static_cast<double>(1ULL << d)") == 2,
            "slack bit weights must be formed by integer shift in both register loops")
    require("kSectorSlackBits = 2" in code_only and "kBudgetSlackBits = 11" in code_only,
            "HIP slack register widths drift from the scope-locked 2/11")
    for flag in module.REQUIRED_COMPILE_FLAGS:
        require(flag in module.compile_command("hipcc", Path("a"), Path("b")), f"compile command lacks {flag}")
    require(module.TARGET_ARCHITECTURE == "gfx1201", "target architecture drift")
    require(module.ENCODING == "slack" and module.REFERENCE == "src.g4.energy.slack_energy"
            and module.LIFT_SOURCE == "src.g4.energy.exact_slack_lift", "encoding/reference labels drift")
    for source in NEW_PYTHON:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        require(not any(isinstance(node, ast.Assert) for node in ast.walk(tree)),
                f"assert is not permitted: {source.name}")


def check_pins(module, unbalanced) -> None:
    observed = module.verify_pinned_inputs()
    require(observed == module.PINNED_INPUTS, "pinned inputs drifted")
    require(observed[module.HIP_SOURCE_REL] == hashlib.sha256(HIP_SOURCE.read_bytes()).hexdigest(),
            "HIP source pin is stale")
    require(observed[module.UNBALANCED_LIBRARY_REL] == hashlib.sha256(UNBALANCED_MODULE.read_bytes()).hexdigest(),
            "unbalanced library pin is stale")
    shared = set(module.PINNED_INPUTS) & set(unbalanced.PINNED_INPUTS)
    require(shared == set(unbalanced.PINNED_INPUTS) - {unbalanced.HIP_SOURCE_REL},
            "slack pins do not cover every unbalanced pin except the unbalanced HIP source")
    require(all(module.PINNED_INPUTS[key] == unbalanced.PINNED_INPUTS[key] for key in shared),
            "slack and unbalanced prototypes pin different bytes for a shared input")
    tampered = dict(module.PINNED_INPUTS)
    tampered["src/g4/energy.py"] = "0" * 64
    try:
        module.verify_pinned_inputs(tampered)
    except module.CrosscheckError as exc:
        require("src/g4/energy.py" in str(exc), "drift message does not name the drifted file")
    else:
        raise FixtureError("pin verification accepted a drifted input")


def check_points(module, unbalanced) -> tuple:
    ledgers = module.load_ledgers()
    points = module.coefficient_points(ledgers)
    shared = unbalanced.coefficient_points(unbalanced.load_ledgers())
    require(tuple(point["point_id"] for point in points) == EXPECTED_POINT_IDS, "coefficient point drift")
    require(len(points) == len(shared) == 4, "point count drift")
    for point, other in zip(points, shared, strict=True):
        require(point["point_id"] == other["point_id"] and point["coefficients"] == other["coefficients"]
                and point["coefficients_hex"] == other["coefficients_hex"]
                and point["ledger_content_sha256"] == other["ledger_content_sha256"]
                and point["ledger_index"] == other["ledger_index"],
                f"slack point differs from the unbalanced point: {point['point_id']}")
        require(point["consumed_by_slack_transcript"] == ["alpha", "sector_slack", "budget_slack"]
                and set(point["not_consumed"]) == {"sector_linear", "sector_quadratic", "budget_linear", "budget_quadratic"}
                and "consumed_by_unbalanced_transcript" not in point,
                f"slack point consumption labels drift: {point['point_id']}")
    require(points[0]["primary_ell"] == 30 and points[0]["ledger_index"] == {"card": 6, "sector": 6, "budget": 6},
            "D011 primary_ell=30 row binding drift")
    require(points[1]["ledger_index"]["card"] == 70 and points[1]["coordinate_hex"] == points[0]["coordinate_hex"],
            "V-14 2x row 70 is not the embedded primary coordinate")
    require(points[2]["ledger_index"]["card"] == 0 and points[3]["ledger_index"]["card"] == 110,
            "V-14 2x endpoint binding drift")
    # D011 and the embedded V-14 point share alpha and both slack coefficients,
    # so the slack transcript sees identical coefficients at those two points.
    for name in ("alpha", "sector_slack", "budget_slack"):
        require(points[0]["coefficients_hex"][name] == points[1]["coefficients_hex"][name],
                f"embedded primary {name} differs between D011 and V-14 2x")
    return points


def check_states_and_lift(module, unbalanced, instance) -> tuple:
    states, families = module.declared_states(instance)
    other, other_families = unbalanced.declared_states(instance)
    require(states == other and families == other_families, "slack raw state set differs from the unbalanced set")
    require(len(states) == len(set(states)) == EXPECTED_STATE_COUNT, "declared state count drift")
    require(unbalanced.states_digest(states) == EXPECTED_STATE_DIGEST, "declared state digest drift")

    lifted, excluded = module.lift_states(instance, states)
    again, excluded_again = module.lift_states(instance, states)
    require(lifted == again and excluded == excluded_again, "lift is not deterministic")
    require(len(lifted) == EXPECTED_LIFTED_COUNT and excluded == EXPECTED_EXCLUDED, "lift partition drift")
    require(module.lifted_digest(lifted) == EXPECTED_LIFTED_DIGEST, "lifted pair digest drift")
    require(len(lifted) + sum(excluded.values()) == len(states), "lift partition does not cover the raw set")
    lifted_masks = [mask for mask, _word in lifted]
    require(lifted_masks == [mask for mask in states if mask in set(lifted_masks)], "lift does not preserve declaration order")

    # Independent oracle: each attached register must hold exactly the
    # canonical residual, and each exclusion must be forced by the first
    # register (sector 0..3, then budget) whose residual is not an in-range
    # integer.  Uses residuals(), not exact_slack_lift().
    from src.g4.energy import BUDGET_SLACK_BITS, SECTOR_SLACK_BITS, exact_slack_lift, residuals

    lifted_by_mask = dict(lifted)
    oracle_excluded: dict[str, int] = {}
    for mask in states:
        x = module.mask_to_x(mask)
        _h_card, h_sector, h_budget = residuals(instance, x)
        registers = [(f"sector[{j}]", h_sector[j], SECTOR_SLACK_BITS) for j in range(4)] + [("budget", h_budget, BUDGET_SLACK_BITS)]
        refusal = next((name for name, value, width in registers
                        if not (float(int(value)) == value and 0 <= int(value) < (1 << width))), None)
        if refusal is None:
            require(mask in lifted_by_mask, f"liftable mask was excluded: 0x{mask:05x}")
            word = lifted_by_mask[mask]
            auxiliary = module.word_to_auxiliary(word)
            require(module.auxiliary_to_word(auxiliary) == word, "auxiliary word round trip failed")
            require(auxiliary == exact_slack_lift(instance, x), f"attached auxiliary is not the canonical lift: 0x{mask:05x}")
            offset = 0
            for name, value, width in registers:
                register = sum(auxiliary[offset + d] << d for d in range(width))
                offset += width
                require(register == int(value), f"{name} register does not equal the residual for 0x{mask:05x}")
            require(offset == 19 and word <= module.AUXILIARY_MASK, "auxiliary layout drift")
        else:
            require(mask not in lifted_by_mask, f"unliftable mask was lifted: 0x{mask:05x}")
            oracle_excluded[refusal] = oracle_excluded.get(refusal, 0) + 1
    require(oracle_excluded == excluded, "exclusion reasons differ from the independent oracle")
    require(lifted[0] == (0, 0x44CAA), "all-zero state lift drift (sectors 2,2,2,2; budget 1100)")

    try:
        module.lift_states(instance, (module.FULL_MASK,))
    except module.CrosscheckError as exc:
        require("no raw state admits" in str(exc), "empty lift message drift")
    else:
        raise FixtureError("lift accepted a set with no liftable state")
    return states, lifted


def check_encoding(module, instance, points, lifted) -> None:
    payload = module.encode_inputs(instance, points, lifted)
    words = [int.from_bytes(payload[i:i + 8], "little") for i in range(0, len(payload), 8)]
    require(len(payload) % 8 == 0, "input stream is not word aligned")
    require(words[:7] == [module.INPUT_MAGIC, module.FORMAT_VERSION, 20, 2, 11, len(points), len(lifted)],
            "input header drift")
    require(module.INPUT_MAGIC == int.from_bytes(b"G6SLKCX1", "little")
            and module.OUTPUT_MAGIC == int.from_bytes(b"G6SLKCY1", "little"), "magic drift")
    cursor = 7
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
        require(words[cursor:cursor + 3] == expected, "coefficient encoding drift")
        cursor += 3
    masks = [mask for mask, _word in lifted]
    auxiliaries = [word for _mask, word in lifted]
    require(words[cursor:cursor + len(masks)] == masks, "state encoding drift")
    cursor += len(masks)
    require(words[cursor:] == auxiliaries, "auxiliary encoding drift")
    require(cursor + len(auxiliaries) == len(words), "input stream length drift")


def check_comparator(module, instance) -> None:
    from src.g4.energy import slack_energy
    from src.g4.parameters import Coefficients

    synthetic = Coefficients(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
    points = ({"point_id": "synthetic_unit", "coefficients": synthetic},)
    lifted, excluded = module.lift_states(instance, (0, 1, module.FULL_MASK, 0x00033, 0x00002))
    require([mask for mask, _w in lifted] == [0, 1, 0x00002] and sum(excluded.values()) == 2,
            "synthetic lift partition drift")
    reference = module.python_reference_bits(instance, points, lifted)
    require(len(reference) == 3, "reference length drift")
    for (mask, word), bits in zip(lifted, reference, strict=True):
        direct = slack_energy(instance, module.mask_to_x(mask), module.word_to_auxiliary(word), synthetic)
        require(module.float_bits(direct) == bits, "reference bits differ from a direct canonical call")
    clean = module.compare_bits(reference, reference, points, lifted)
    require(clean["mismatches"] == 0 and clean["evaluations"] == 3 and clean["first_mismatches"] == [],
            "comparator reports mismatches on identical bits")
    corrupted = list(reference)
    corrupted[2] ^= 1
    flagged = module.compare_bits(reference, tuple(corrupted), points, lifted)
    require(flagged["mismatches"] == 1 and flagged["first_mismatches"] == [
        {"point_id": "synthetic_unit", "state_mask_hex": "0x00002"}], "comparator missed a one-ulp corruption")
    require(set(flagged["first_mismatches"][0]) == {"point_id", "state_mask_hex"}, "comparator leaked a value")
    header = [module.OUTPUT_MAGIC, module.FORMAT_VERSION, len(points), len(lifted), 1]
    stream = b"".join(int(w).to_bytes(8, "little") for w in header + list(reference) + list(reference))
    device_index, device_bits, host_bits = module.decode_output(stream, len(points), len(lifted))
    require(device_index == 1 and device_bits == reference and host_bits == reference, "output decoding drift")
    for broken in (stream[:-8], stream.replace(b"G6SLKCY1", b"G6UBNCY1", 1)):
        try:
            module.decode_output(broken, len(points), len(lifted))
        except module.CrosscheckError:
            pass
        else:
            raise FixtureError("malformed output was accepted")


def check_cli() -> None:
    environment = {"PATH": "", "PYTHONDONTWRITEBYTECODE": "1"}
    before = prototype_tree_digest()
    plan = subprocess.run([sys.executable, str(RUNNER)], cwd=ROOT, text=True, capture_output=True,
                          check=False, env=environment)
    require(plan.returncode == 0, "default invocation must plan without a HIP compiler: " + plan.stderr[-400:])
    payload = json.loads(plan.stdout)
    require(payload["mode"] == "plan" and payload["writes"] == "none"
            and payload["encoding"] == "slack"
            and payload["scientific_outputs"] == "intentionally absent"
            and payload["hipcc_located"] is False
            and payload["raw_state_set"]["count"] == EXPECTED_STATE_COUNT
            and payload["lift"]["lifted_count"] == EXPECTED_LIFTED_COUNT
            and payload["lift"]["excluded_by_register"] == EXPECTED_EXCLUDED
            and payload["lift"]["sha256_le_uint64_pairs"] == EXPECTED_LIFTED_DIGEST
            and payload["planned_evaluations"] == 4 * EXPECTED_LIFTED_COUNT
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
    require(prototype_tree_digest() == before, "CLI invocations changed the prototype tree")
    leftovers = [p for p in Path(tempfile.gettempdir()).glob("g6-gpu-slack-energy-*")]
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
        module = load_by_path("g6_gpu_slack_energy_crosscheck_fixture", MODULE)
        unbalanced = load_by_path("g6_gpu_energy_crosscheck_fixture_reference", UNBALANCED_MODULE)
        check_static(module)
        check_pins(module, unbalanced)
        points = check_points(module, unbalanced)
        from src.g4.instance import load_instance

        instance = load_instance(ROOT / module.INSTANCE_REL)
        _states, lifted = check_states_and_lift(module, unbalanced, instance)
        check_encoding(module, instance, points, lifted)
        check_comparator(module, instance)
        check_run_guard(module)
        check_cli()
        forbidden = [name for name in sys.modules if name.startswith("src.g5") or name in {
            "src.g6.g5_input", "src.g6.ratified_g5_input", "src.g6.g5_digest_registry",
            "src.g6.trial_runner", "src.g6.d011_runner"}]
        require(not forbidden, "fixtures loaded a Gate-5 corpus/runner module: " + ", ".join(forbidden))
        print("PASS GPU slack energy cross-check fixtures; no HIP compiler, GPU, Gate-5 corpus read, or repository write")
        return 0
    except FixtureError as exc:
        print(f"FAIL GPU slack energy cross-check fixtures: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
