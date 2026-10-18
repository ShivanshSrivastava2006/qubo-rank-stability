#!/usr/bin/env python3
"""Keep the core-stream engine scan away from real inputs, solvers, and writers."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "research/g9/cuda_qualification/stage2_cuda_core_stream_engine.py"
CUDA_SOURCE = ROOT / "research/g9/cuda_qualification/stage2_cuda_core_stream_engine.cu"
FORBIDDEN_PREFIXES = ("src", "research.g5", "research.g6", "research.g7",
                      "research.g9.stage2_generator", "research.g9.stage2_generation_contract",
                      "numpy")
FORBIDDEN_LITERALS = ("research/canonical", "research/ground_truth", "research/g5", "research/g6",
                      "stage2_generation", "stage2_instance", "stage1_instance")
FORBIDDEN_CUDA_TOKENS = ("__shared__", "atomicAdd", "atomicMin", "atomicExch", "fma(", "__fma",
                         "sqrt(", "pow(", "exp(", "log(", "qsort", "std::sort", "thrust",
                         "-ffast-math", "use_fast_math", "float ", "ofstream", "fopen(", "freopen(",
                         "std::ifstream", "__syncthreads")
REQUIRED_CUDA_ANCHORS = ("--self-test", "kDecodedWidth - 1u - asset", "terms_kernel",
                         "energy_kernel", "segment_kernel", "flags_kernel", "lift_digest",
                         "compaction_count_kernel", "compaction_write_kernel",
                         "validate_payload_contract", "run_core", "CoreOutput",
                         # instance-specific lambda_ref, and the returned interface
                         "double lambda_ref;", "payload.lambda_ref",
                         "const double scale = lambda_ref + maximum;",
                         "std::uint64_t entries[kMaxCompactedEntries];",
                         "result->minimum_index = minimum_index;",
                         "reconstruction_mismatches",
                         "run_core(host_payload, host_rows, kRowCount, nullptr, nullptr, &generic)",
                         "kMaxCompactedEntries", "kCompactionChunkSize",
                         "payload->membership[s][member]",
                         "scientific_outputs", "intentionally absent",
                         # pre-nvcc numerical compile contract (nvcc is not run)
                         "--fmad=false", "--ftz=false", "--prec-div=true", "--prec-sqrt=true",
                         "-ffp-contract=off", "-fno-fast-math",
                         "NOT a claim of real CUDA numerical qualification")
# The report may carry only synthetic checksums, integer counters, fixed
# identity metadata and a verdict.  These names would mean a leaked energy,
# minimum, index, tie list, label or rate.
# A report field may name a counter ('nonfinite_energies') or a checksum
# ('minimum_checksum_row0_slack'), but never carry a raw scientific value.
# These are the bare names, and the suffixes, that would mean a leaked value.
FORBIDDEN_REPORT_NAMES = ("minimum", "minimum_index", "energy", "energies", "tie_list", "ties",
                          "label", "labels", "rate", "record", "records", "argmin", "winner",
                          "index", "value", "values")
FORBIDDEN_REPORT_SUFFIXES = ("_minimum", "_index", "_argmin", "_winner", "_rate", "_label",
                             "_value", "_energy", "_record")


def static_python_violations() -> list[str]:
    failures: list[str] = []
    tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            names = []
        for name in names:
            if any(name == prefix or name.startswith(prefix + ".") for prefix in FORBIDDEN_PREFIXES):
                failures.append("forbidden import: " + name)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for fragment in FORBIDDEN_LITERALS:
                if fragment in node.value:
                    failures.append("forbidden path literal: " + fragment)
        if isinstance(node, ast.Assert):
            failures.append("assert statement in the reference module")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            failures.append("reference module opens a file")
    return failures


def static_cuda_violations() -> list[str]:
    source = CUDA_SOURCE.read_text(encoding="utf-8")
    uncommented = "\n".join(line for line in source.splitlines()
                            if not line.lstrip().startswith("//"))
    failures = [f"forbidden CUDA token: {token}" for token in FORBIDDEN_CUDA_TOKENS
                if token in uncommented]
    failures.extend(f"missing CUDA anchor: {anchor}" for anchor in REQUIRED_CUDA_ANCHORS
                    if anchor not in source)
    for fragment in FORBIDDEN_LITERALS:
        if fragment in uncommented:
            failures.append("forbidden CUDA path literal: " + fragment)
    return failures


# Buffers whose size is O(word_count): copying one to the host is exactly the
# unbounded transfer the generic path must not perform.  Bounded per-segment
# and per-chunk arrays, minima and compacted entries remain allowed.
FULL_STREAM_BUFFERS = ("host_energies", "host_flag_bytes")


def generic_path_violations() -> list[str]:
    """The generic run_core path must make no full-stream device-to-host copy."""
    source = CUDA_SOURCE.read_text(encoding="utf-8")
    lines = source.splitlines()
    failures: list[str] = []

    depth = 0
    quarantined: set[int] = set()
    opens = 0
    for number, line in enumerate(lines):
        if "BEGIN QUALIFICATION-ONLY" in line:
            depth += 1
            opens += 1
        if depth > 0:
            quarantined.add(number)
        if "END QUALIFICATION-ONLY" in line:
            depth -= 1
            if depth < 0:
                failures.append(f"unmatched qualification-only END at line {number + 1}")
                depth = 0
    if depth != 0:
        failures.append("an unclosed qualification-only region")
    if opens == 0:
        failures.append("no qualification-only region is marked at all")

    # Scan by STATEMENT, not by line: a cudaMemcpy call routinely wraps across
    # lines, and a per-line scan would never examine the very copies this check
    # exists to catch.
    seen_buffers: set[str] = set()
    for match in re.finditer(r"cudaMemcpy\s*\(", source):
        stop = source.find(";", match.start())
        statement = source[match.start():stop if stop >= 0 else len(source)]
        if "cudaMemcpyDeviceToHost" not in statement:
            continue
        for buffer in FULL_STREAM_BUFFERS:
            if buffer not in statement:
                continue
            seen_buffers.add(buffer)
            number = source.count("\n", 0, match.start())
            if number not in quarantined:
                failures.append(
                    f"full-stream device-to-host copy of {buffer} reachable from the generic "
                    f"path at line {number + 1}")
    missing = [buffer for buffer in FULL_STREAM_BUFFERS if buffer not in seen_buffers]
    if missing:
        failures.append("no device-to-host copy found for " + ", ".join(missing)
                        + ": this check would be vacuous")

    # Each quarantined region must sit behind the qualification flag, so the
    # generic mode (control_positions == nullptr) cannot enter it.
    for number, line in enumerate(lines):
        if "BEGIN QUALIFICATION-ONLY" not in line:
            continue
        window = "\n".join(lines[max(0, number - 4):number])
        if "if (qualification)" not in window:
            failures.append(f"a qualification-only region at line {number + 1} is not guarded "
                            "by the qualification flag")

    # The contract must be enforced before anything is allocated or launched,
    # measured INSIDE run_core (the launch macro is defined far earlier).
    start = source.find("static bool run_core(")
    stop = source.find("static bool run_self_test()")
    body = source[start:stop] if 0 <= start < stop else ""
    if not body:
        failures.append("run_core could not be located for the ordering check")
    guard = body.find("validate_payload_contract(payload)")
    malloc = body.find("cudaMalloc")
    launch = body.find("G9_CORE_LAUNCH(")
    if guard < 0:
        failures.append("run_core does not enforce the payload contract")
    elif malloc >= 0 and guard > malloc:
        failures.append("the payload contract is checked after the first allocation")
    elif launch >= 0 and guard > launch:
        failures.append("the payload contract is checked after the first launch")
    return failures


def dynamic_violations() -> list[str]:
    # The probe stays away from the full scan: it only needs to prove that
    # importing the reference reaches no scientific module and opens no file,
    # and that the declared report schema leaks no scientific value.
    probe = (
        "import json,sys; from pathlib import Path; root=Path(sys.argv[1]); sys.path.insert(0,str(root)); "
        "from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as e; "
        "p=e.validate_payload(e.synthetic_payload()); "
        "print(json.dumps({'states':e.STATE_COUNT,'bits':e.AUXILIARY_BITS,"
        "'rows':list(e.ROW_NAMES),'ch':list(e.CH_VALUES),"
        "'contiguous':e.is_contiguous_membership(p['sectors']),"
        "'cuda_flags':list(e.CUDA_COMPILE_FLAGS),'host_flags':list(e.HOST_COMPILE_FLAGS),"
        "'chunk':e.COMPACTION_CHUNK_SIZE,'cap':e.MAX_COMPACTED_ENTRIES,"
        "'compacted_flags':list(e.COMPACTED_FLAGS),"
        "'lambda_ref_is_payload_field':('lambda_ref' in p and not hasattr(e,'LAMBDA_REF')),"
        "'modules':sorted(k for k in sys.modules if k=='src' or k.startswith(('src.','numpy')))}))"
    )
    result = subprocess.run([sys.executable, "-c", probe, str(ROOT)], cwd=ROOT,
                            env={"PATH": "", "PYTHONDONTWRITEBYTECODE": "1"},
                            text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return ["dynamic probe failed: " + result.stderr[-400:]]
    payload = json.loads(result.stdout)
    failures: list[str] = []
    if payload["modules"]:
        failures.append("scientific module imported: " + ", ".join(payload["modules"]))
    if payload["states"] != (1 << 20) or payload["bits"] != 19:
        failures.append("domain or layout constants drifted")
    if payload["contiguous"]:
        failures.append("the synthetic partition is contiguous")
    if payload["ch"] != [1024.0, 2048.0, 4096.0]:
        failures.append("the D015 threshold ladder drifted")
    if len(payload["rows"]) < 2:
        failures.append("fewer than two fixed synthetic coefficient rows")
    if list(payload["cuda_flags"]) != ["--fmad=false", "--ftz=false",
                                       "--prec-div=true", "--prec-sqrt=true"]:
        failures.append("the declared CUDA numerical contract drifted")
    if list(payload["host_flags"]) != ["-ffp-contract=off", "-fno-fast-math"]:
        failures.append("the declared host numerical contract drifted")
    if payload["chunk"] <= 0 or payload["cap"] <= 0:
        failures.append("the compaction chunk size or hard cap is not positive")
    if list(payload["compacted_flags"]) != [4, 6, 7]:
        failures.append("the compacted flag set must be exactly {4, 6, 7}")
    if not payload["lambda_ref_is_payload_field"]:
        failures.append("lambda_ref is not a validated payload field")
    return failures


def report_schema_violations() -> list[str]:
    """The emitted report must expose no energy, minimum, index or tie list."""
    # The exact key set is derived from the real report builder, driven by
    # stub scans and a stub domain, so it can never drift from what the
    # component emits -- and so this check costs no full-domain build.
    probe = (
        "import json,sys; from pathlib import Path; root=Path(sys.argv[1]); sys.path.insert(0,str(root)); "
        "from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as e; "
        "domain={'payload':{'sectors':e.SYNTHETIC_MEMBERSHIP,"
        "'lambda_ref':e.SYNTHETIC_LAMBDA_REF},'lift_total':0,'lift_digest':0,"
        "'exact_registers':0,'clamped_registers':0,'tied_registers':0}; "
        "one={'natural_checksum':0,'controlled_checksum':0,'flags_checksum':0,'minimum':0.0,"
        "'minimum_index':0,'word_count':0,'per_ch':(0,0,0),'illegal':0,'nesting':0,"
        "'compacted_count':0,'compaction_chunks':0,'compaction_checksum':0}; "
        "scans={(r,c):one for r in e.ROW_NAMES for c in e.ENCODINGS}; "
        "print(json.dumps(e.expected_self_test(scans, domain, scans)))"
    )
    result = subprocess.run([sys.executable, "-c", probe, str(ROOT)], cwd=ROOT,
                            env={"PATH": "", "PYTHONDONTWRITEBYTECODE": "1"},
                            text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return ["report-schema probe failed: " + result.stderr[-400:]]
    report = json.loads(result.stdout)
    failures = []
    for field, value in report.items():
        if field in FORBIDDEN_REPORT_NAMES or field.endswith(FORBIDDEN_REPORT_SUFFIXES):
            failures.append(f"report field name denotes a raw scientific value: {field}")
        if isinstance(value, bool) or isinstance(value, float):
            failures.append(f"report field carries a non-integer numeric value: {field}")
        if isinstance(value, (list, dict)):
            failures.append(f"report field carries a container: {field}")
    return failures


def main() -> int:
    failures = (static_python_violations() + static_cuda_violations()
                + generic_path_violations() + dynamic_violations()
                + report_schema_violations())
    if failures:
        print("FAIL Stage-2 core-stream engine import boundary: " + "; ".join(failures),
              file=sys.stderr)
        return 1
    print("PASS Stage-2 core-stream engine import boundary; no real input, generator, solver, "
          "writer, NumPy, or scientific-output module reachable, no leaking report field, and "
          "no full-stream device-to-host transfer on the generic run_core path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
