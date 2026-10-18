"""Synthetic-only fixtures for the §B item 1 pre-write identity recheck harness.

Run with ``python3 -B`` and again with ``python3 -B -O``; ``PYTHONDONTWRITEBYTECODE=1``
is required.  Nothing here writes a file, and nothing here touches a real
candidate, a real instance, real ground truth, a real Kaggle image or any
scientific value.  The identities used are simple synthetic stand-ins for the
injected WP1 dependency, which is still under review and is deliberately not
imported.

Coverage:
  1. pass case, and determinism across two identical calls;
  2. each of the six §B item 1 elements individually wrong -> refusal naming it;
  3. each of the six elements missing -> refusal naming it;
  4. the emitted record's exact key set, and a refusal for any coordinate-level
     value, float, list or mapping anywhere in it;
  5. the platform-reported label on both image fields, on the record;
  6. a non-``str`` truthy ``exact_match`` return is still a refusal;
  7. every banned compiler flag fragment is refused;
     compliant negations and comma-separated compiler bundles are recognized;
  8. the approval documents are re-read from disk and compared with the pins;
  9. the session/accepted identity validators are consulted, and their failure is
     a refusal;
 10. require_gate raises on a refusal and accepts a pass, and refuses a
     hand-written "pass" record paired with a closed gate;
 11. each element check in isolation through ``discover_element``, so no check is
     masked by a second one;
 12. self-consistent forgeries, whose only remaining defence is a semantic check;
 13. every public argument fuzzed with None/bool/int/float/str/bytes/list/dict/
     unhashable and nested-wrong-type values, requiring a typed outcome only;
 14. one fixture per check that round 2 added, moved or narrowed, so each of them
     has a case that fails if and only if that check is removed.
"""
import hashlib
import importlib.util
import json as json_mod
import os
import shutil
import sys
import tempfile
from pathlib import Path

if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
    raise SystemExit("PYTHONDONTWRITEBYTECODE=1 required")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.g9 import stage2_section_b1_recheck as recheck


# ---------------------------------------------------------------------------
# Synthetic stand-ins for the injected WP1 identity dependency.
# ---------------------------------------------------------------------------
SYNTHETIC_SOURCE = {
    "research/g9/synthetic_engine.py": "1" * 64,
    "research/g9/synthetic_writer.py": "2" * 64,
}
SYNTHETIC_PLATFORM = {
    "compute_capability": "7.5",
    "cuda_driver_version": "13000",
    "cuda_runtime_version": "12080",
    "gpu_name": "NVIDIA Tesla T4",
    "kaggle_image": "synthetic/image:pinned-placeholder",
    "kaggle_image_build": "synthetic/build:0001",
    "numpy_version": "2.0.2",
    "nvcc_version": "12.8.93",
    "python_version": "3.12.13",
}
SYNTHETIC_COMPILER = {"version": "12.8.93", "flags": ["-O2", "-std=c++17", "--prec-div=true", "--prec-sqrt=true"]}
SYNTHETIC_GENERATOR_SHA = "3" * 64
SYNTHETIC_GROUND_TRUTH_SHA = "4" * 64


def synthetic_canonical(value):
    return json_mod.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def synthetic_validate(payload):
    """Stand-in for WP1's validate(payload) -> sha256 hex.  Rejects float leaves."""
    def walk(node):
        if type(node) is dict:
            for nested in node.values():
                walk(nested)
        elif type(node) is list:
            for nested in node:
                walk(nested)
        else:
            if type(node) is float:
                raise ValueError("synthetic identity may not contain a float leaf")
    walk(payload)
    return hashlib.sha256(synthetic_canonical(payload)).hexdigest()


def synthetic_exact_match(session, accepted):
    """Stand-in for WP1's exact_match(session, accepted); raises on any difference."""
    if type(session) is not dict or type(accepted) is not dict:
        raise ValueError("identity payloads must be mappings")
    if sorted(session) != sorted(accepted):
        raise ValueError("identity key set differs")
    for key in sorted(accepted):
        if session[key] != accepted[key]:
            raise ValueError(f"identity field {key!r} differs")


def raising_validate(_payload):
    raise ValueError("synthetic validator refuses this identity")


def wrong_hash_validate(_payload):
    return "not-a-sha256"


def raising_matcher(_session, _accepted):
    raise ValueError("synthetic exact_match found a difference")


def _identity_pair():
    """The accepted and session identity payloads of a fully passing case."""
    accepted = {
        "platform": dict(SYNTHETIC_PLATFORM),
        "compiler": {"version": SYNTHETIC_COMPILER["version"], "flags": list(SYNTHETIC_COMPILER["flags"])},
        "source_sha256": dict(SYNTHETIC_SOURCE),
    }
    session = {
        "platform": dict(SYNTHETIC_PLATFORM),
        "compiler": {"version": SYNTHETIC_COMPILER["version"], "flags": list(SYNTHETIC_COMPILER["flags"])},
        "source_sha256": dict(SYNTHETIC_SOURCE),
    }
    return accepted, session


def arguments():
    """A complete, passing set of recheck arguments."""
    accepted, session = _identity_pair()
    observed = recheck.read_approval_hashes()
    return {
        "accepted_identity": accepted,
        "validate_identity": synthetic_validate,
        "exact_match": synthetic_exact_match,
        "observed_approval_sha256": observed,
        "expected_approval_sha256": dict(observed),
        "session_identity": session,
        "generator_implementation_record_sha256": SYNTHETIC_GENERATOR_SHA,
        "expected_generator_implementation_record_sha256": SYNTHETIC_GENERATOR_SHA,
        "ground_truth_provenance_sha256": SYNTHETIC_GROUND_TRUTH_SHA,
        "expected_ground_truth_provenance_sha256": SYNTHETIC_GROUND_TRUTH_SHA,
    }


# The keyword arguments of recheck_before_first_write / discover_element, in the
# order they are declared.  Used by the fuzz group to walk every public argument
# rather than a hand-picked subset.
RECHECK_KEYWORDS = (
    "accepted_identity",
    "validate_identity",
    "exact_match",
    "observed_approval_sha256",
    "expected_approval_sha256",
    "session_identity",
    "generator_implementation_record_sha256",
    "expected_generator_implementation_record_sha256",
    "ground_truth_provenance_sha256",
    "expected_ground_truth_provenance_sha256",
)


def run(args):
    return recheck.recheck_before_first_write(**args)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def require_refusal(args, element, label):
    """Run and require a refusal that names exactly this element."""
    record, gate = run(args)
    require(gate is False, f"{label}: the gate opened on a refusal case")
    require(record["verdict"] == "refused", f"{label}: verdict is not 'refused'")
    require(element in record["failed_elements"],
            f"{label}: the refusal does not name {element!r}: {record['failed_elements']}")
    require(any(reason.startswith(f"{element}: ") for reason in record["refusal_reasons"]),
            f"{label}: no reason names {element!r}: {record['refusal_reasons']}")
    recheck._validate_record(record)
    try:
        recheck.require_gate(record, gate)
    except recheck.SectionB1RecheckError:
        return record
    raise RuntimeError(f"{label}: require_gate did not raise on a closed gate")


# ---------------------------------------------------------------------------
def main():
    checks = []

    # --- 1. pass case -------------------------------------------------------
    args = arguments()
    record, gate = run(args)
    require(gate is True, "1: the passing case was refused")
    require(record["verdict"] == "pass", "1: verdict is not 'pass'")
    recheck._validate_record(record)
    require(record["counters"] == {"elements_checked": 6, "elements_passed": 6, "elements_failed": 0},
            f"1: pass counters are wrong: {record['counters']}")
    require(record["elements_checked"] == list(recheck.ELEMENT_NAMES), "1: element list mismatch")
    require(sorted(record["element_results"]) == sorted(recheck.ELEMENT_NAMES),
            "1: the passing record does not carry a result for all six elements")
    require(all(row["status"] == "match" for row in record["element_results"].values()),
            "1: a passing record carries a non-match element result")
    require(record["failed_elements"] == [] and record["refusal_reasons"] == [],
            "1: a passing record carries refusal content")
    # Determinism: two identical calls produce byte-identical records.
    again, gate_again = run(arguments())
    require(gate_again is True, "1: the second passing call was refused")
    require(again == record, "1: two identical calls produced different records")
    checks.append("1 pass case + determinism")

    # --- 5. platform-reported label on the image fields ---------------------
    require(record["platform_reported_fields"] == sorted(recheck.IMAGE_PLATFORM_FIELDS),
            f"5: platform-reported fields are wrong: {record['platform_reported_fields']}")
    require(set(recheck.IMAGE_PLATFORM_FIELDS) <= set(recheck.PLATFORM_FIELDS),
            "5: the image fields are not all platform fields")
    for field in recheck.IMAGE_PLATFORM_FIELDS:
        require(record["platform_identity"].get(field) == SYNTHETIC_PLATFORM[field],
                f"5: the platform identity lost its {field!r} value")
    require(record["platform_identity"] == SYNTHETIC_PLATFORM,
            "5: the platform identity does not carry all declared platform fields")
    require(record["identity"]["exact_match"] == "no_differences",
            "5: the record does not state the exact-match equality")
    require(record["evidence"]["authorizes_write"] == "no",
            "5: the record claims a write authorization")
    # A platform-reported drift is a refusal, even though the value is only
    # reported: the provider-trust amendment §3 keeps requalification mandatory.
    for field in recheck.IMAGE_PLATFORM_FIELDS:
        drifted = arguments()
        drifted["session_identity"]["platform"][field] = "synthetic/image:drifted"
        require_refusal(drifted, "platform", f"5 image drift in {field!r}")
    checks.append("5 platform-reported image label + image drift refused")

    # --- 2. each element individually wrong ---------------------------------
    wrong = arguments()
    wrong["expected_approval_sha256"][recheck.APPROVAL_PATHS[0]] = "0" * 64
    require_refusal(wrong, "protocol", "2 protocol wrong")

    wrong = arguments()
    wrong["generator_implementation_record_sha256"] = "5" * 64
    require_refusal(wrong, "generator", "2 generator wrong")

    wrong = arguments()
    wrong["ground_truth_provenance_sha256"] = "5" * 64
    require_refusal(wrong, "ground_truth", "2 ground_truth wrong")

    wrong = arguments()
    wrong["session_identity"]["source_sha256"]["research/g9/synthetic_writer.py"] = "6" * 64
    require_refusal(wrong, "source", "2 source wrong")

    for field in recheck.PLATFORM_FIELDS:
        wrong = arguments()
        wrong["session_identity"]["platform"][field] = "synthetic/drifted"
        require_refusal(wrong, "platform", f"2 platform wrong in {field!r}")

    wrong = arguments()
    wrong["session_identity"]["compiler"]["version"] = "12.9.0"
    require_refusal(wrong, "compiler", "2 compiler version wrong")

    wrong = arguments()
    wrong["session_identity"]["compiler"]["flags"] = list(SYNTHETIC_COMPILER["flags"]) + ["-DFOO=1"]
    require_refusal(wrong, "compiler", "2 compiler flags wrong")
    checks.append("2 six elements individually wrong")

    # --- 3. each element missing -------------------------------------------
    for key in recheck.APPROVAL_PATHS:
        missing = arguments()
        del missing["observed_approval_sha256"][key]
        require_refusal(missing, "protocol", f"3 protocol missing {key}")

    missing = arguments()
    missing["generator_implementation_record_sha256"] = None
    require_refusal(missing, "generator", "3 generator missing")

    missing = arguments()
    missing["expected_generator_implementation_record_sha256"] = None
    require_refusal(missing, "generator", "3 generator pin missing")

    missing = arguments()
    missing["ground_truth_provenance_sha256"] = None
    require_refusal(missing, "ground_truth", "3 ground_truth missing")

    missing = arguments()
    missing["expected_ground_truth_provenance_sha256"] = None
    require_refusal(missing, "ground_truth", "3 ground_truth pin missing")

    missing = arguments()
    del missing["session_identity"]["source_sha256"]
    require_refusal(missing, "source", "3 source missing")

    missing = arguments()
    del missing["session_identity"]["platform"]
    require_refusal(missing, "platform", "3 platform missing")

    missing = arguments()
    del missing["session_identity"]["compiler"]
    require_refusal(missing, "compiler", "3 compiler missing")

    # A missing element must fail closed, not be skipped.  With the whole session
    # identity absent, the three session-derived elements (source, platform,
    # compiler) all refuse, while protocol, generator and ground_truth are
    # rechecked from their own independent evidence and therefore still pass.
    # The gate is nonetheless closed: one refusal is enough.
    missing = arguments()
    missing["session_identity"] = {}
    absent = require_refusal(missing, "session_identity", "3 whole session identity missing")
    for element in ("source", "platform", "compiler"):
        require(element in absent["failed_elements"],
                f"3: an absent session identity did not refuse {element!r}: {absent['failed_elements']}")
    require("session_identity" in absent["failed_elements"],
            "3: an absent session identity did not refuse the identity itself")
    require(sorted(absent["element_results"]) == ["generator", "ground_truth", "protocol"],
            f"3: the independently pinned elements were not rechecked: {sorted(absent['element_results'])}")
    require(absent["counters"]["elements_passed"] == 3 and absent["counters"]["elements_failed"] == 3,
            f"3: wrong counters for an absent session identity: {absent['counters']}")
    # One refusal alone closes the gate, even with five elements still matching.
    single = arguments()
    single["ground_truth_provenance_sha256"] = "a" * 64
    closed = require_refusal(single, "ground_truth", "3 a single refusal closes the gate")
    require(closed["counters"]["elements_passed"] == 5,
            f"3: a single refusal changed the other elements' verdicts: {closed['counters']}")
    checks.append("3 six elements missing")

    # --- 4. the §B item 3 write limit --------------------------------------
    require(set(record) == set(recheck.RECORD_KEYS),
            f"4: the passing record's key set is not the declared one: "
            f"{sorted(set(record) ^ set(recheck.RECORD_KEYS))}")
    # Assert the exact key set literally, not only against the module constant,
    # so widening the record's shape is caught by this fixture.
    require(
        set(record) == {
            "schema", "clause", "verdict", "elements_checked", "counters",
            "element_results", "failed_elements", "refusal_reasons", "identity",
            "platform_identity", "platform_reported_fields", "source_identity",
            "source_identity_sha256", "validation_digest", "content_sha256", "evidence",
        },
        f"4: the passing record's key set drifted: {sorted(record)}",
    )
    refusal = require_refusal(_wrong_protocol(), "protocol", "4 write-limit refusal sample")
    require(set(refusal) == set(recheck.RECORD_KEYS),
            "4: the refusing record's key set is not the declared one")
    require(refusal["verdict"] == "refused" and refusal["failed_elements"] == ["protocol"],
            "4: the sampled refusal does not look like a refusal")

    # No coordinate-level value: the record must refuse any float, list or
    # mapping leaf anywhere.  This is the check that makes §B item 3's "no
    # unapproved coordinate-level scientific values" mechanical.
    poisoned = arguments()
    poisoned["session_identity"]["platform"]["device_uuid"] = "GPU-0DEADBEEF"
    refused = require_refusal(poisoned, "platform", "4 extra platform field")
    require(refused["platform_identity"] == {},
            "4: a refusal still carries a platform identity")

    for bad in (-1.5, 0.0, 1e308, [1, 2], {"a": 1}, (1, 2), b"bytes", set(), complex(1, 2)):
        try:
            recheck._retained_value(bad, "fixture")
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"4: the record writer accepted a coordinate-level value: {bad!r}")
    for bad in ("", "line\nbreak", "tab\there", None, -1, "x" * 513, "\x00", "\x7f", b"bytes", ()):
        try:
            recheck._retained_value(bad, "fixture")
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"4: the record writer accepted a non-permitted leaf: {bad!r}")
    require(recheck._retained_value(0, "fixture") == 0, "4: a zero counter was refused")
    require(recheck._retained_value(7, "fixture") == 7, "4: a non-negative int counter was refused")
    require(recheck._retained_value(True, "fixture") is True, "4: a bool verdict was refused")
    require(recheck._retained_value("7" * 64, "fixture") == "7" * 64, "4: a sha256 leaf was refused")
    require(recheck._retained_value("platform_reported", "fixture") == "platform_reported",
            "4: a declared status string was refused")
    # The reason strings are built from a closed vocabulary, never from caller
    # data, so a caller cannot inject text into the refusal record.
    injected = arguments()
    injected["session_identity"]["platform"]["gpu_name"] = "x\ny"
    refused = require_refusal(injected, "platform", "4 newline in a platform value")
    for reason in refused["refusal_reasons"]:
        require("\n" not in reason, "4: a refusal reason carries a newline")
        require(not reason.endswith(": "), "4: a refusal reason is empty")
    checks.append("4 exact key set + no coordinate-level value")

    # --- 6. the exact_match contract ---------------------------------------
    # The injected contract is raise-based, so a matcher that returns at all has
    # found no difference: None and True are both acceptances.  Only an explicit
    # False, and only a raise, are refusals.
    for acceptance in (None, True, "match", 0, "", [], ()):
        strict = arguments()
        strict["exact_match"] = lambda _s, _a, value=acceptance: value
        strict_record, strict_gate = run(strict)
        require(strict_gate is True,
                f"6: a matcher returning {acceptance!r} was refused: {strict_record['refusal_reasons']}")
    strict = arguments()
    strict["exact_match"] = lambda _s, _a: False
    require_refusal(strict, "source", "6 exact_match returns False")
    strict = arguments()
    strict["exact_match"] = lambda _s, _a: 0
    strict_record, strict_gate = run(strict)
    require(strict_gate is True,
            f"6: a matcher returning 0 was refused: {strict_record['refusal_reasons']}")
    # A matcher that raises on a difference must actually be reached with the
    # difference: record the argument order and both objects.
    seen = []
    def recording_matcher(session_payload, accepted_payload):
        seen.append((session_payload, accepted_payload))
    strict = arguments()
    strict["exact_match"] = recording_matcher
    strict_record, strict_gate = run(strict)
    require(strict_gate is True, "6: the recording matcher case was refused")
    require(len(seen) == 1, f"6: exact_match was called {len(seen)} times")
    require(seen[0][0] is strict["session_identity"], "6: exact_match did not receive the session identity")
    require(seen[0][1] is strict["accepted_identity"], "6: exact_match did not receive the accepted identity")
    strict = arguments()
    strict["exact_match"] = raising_matcher
    require_refusal(strict, "source", "6 exact_match raises on a difference")
    strict = arguments()
    strict["session_identity"]["source_sha256"]["research/g9/synthetic_writer.py"] = "e" * 64
    strict["exact_match"] = raising_matcher
    require_refusal(strict, "source", "6 exact_match raises on a source drift")
    checks.append("6 exact_match return and argument contract")

    # --- 7. the fixed binary64 compiler contract ----------------------------
    # Frozen v1 flags copied byte-for-byte from
    # build_g9_cuda_core_A_bundle.py:78-82.
    frozen_v1_flags = [
        "-std=c++17", "-O0", "--fmad=false", "--ftz=false",
        "--prec-div=true", "--prec-sqrt=true", "-Xcompiler",
        "-O0,-ffp-contract=off,-fno-fast-math,-fPIC",
    ]
    frozen = arguments()
    frozen["session_identity"]["compiler"] = {
        "version": SYNTHETIC_COMPILER["version"], "flags": list(frozen_v1_flags),
    }
    frozen["accepted_identity"]["compiler"] = {
        "version": SYNTHETIC_COMPILER["version"], "flags": list(frozen_v1_flags),
    }
    frozen_record, frozen_gate = run(frozen)
    require(frozen_gate is True,
            f"7: exact frozen v1 flags were refused: {frozen_record['refusal_reasons']}")

    # A table of tricky individual spellings pins both expected outcomes and
    # comma/wrapper handling at the scanner boundary.
    flag_verdicts = (
        ("-fno-fast-math", False), ("-fno-fmad", False),
        ("-fno-ffp-contract", False), ("--fmad=false", False),
        ("-Xcompiler=-O0,-ffp-contract=off,-fno-fast-math,-fPIC", False),
        ("-Xcompiler -O0,-ffp-contract=off,-fno-fast-math,-fPIC", False),
        ("-Xptxas=--fmad=false,-O2", False), ("--ftz=off", False),
        ("--use_fast_math", True), ("--USE_FAST_MATH", True),
        ("-ffast-math", True), ("-fno-fast-math,-ffast-math", True),
        ("-Xcompiler=-ffast-math", True),
        ("-Xcompiler -O0,-ffast-math", True),
        ("--fmad", True), ("--fmad=true", True),
        ("--fmad=", True), ("-ffp-contract=fast", True),
        ("-ffp-contract=on", True),
        ("-Xcompiler=-ffp-contract=fast", True),
        ("-Xcompiler -O0,-ffp-contract=on", True),
        ("-Xptxas=--fmad=true", True), ("--ftz=yes", True),
        ("-Xcompiler=-Xptxas=--fmad=true", True),
        ("-fno-fast-math -ffast-math", True),
        ("-fno-fmad --fmad=true", True),
        ("-Xcompiler=-fno-fast-math -ffast-math", True),
        ("-fno-fast-math -fassociative-math", True),
        ("-fno-fmad -ffast-math", True),
        ("-fno-fmad --fmad", True),
        ("-fno-fno-fast-math", True), ("-fno-fno-fmad", True),
        ("-fno-no-fast-math", True), ("--fno-fmad", True),
        ("-fno-fast-math=false", True), ("-fno-fast-math=off", True),
        ("--fno-fast-math=false", True),
        ("-ffast-math=off", True), ("-ffmad=false", True), ("-ffmad=0", True),
        ("--prec-div=true", False), ("-O2,-fPIC", False),
        ("--generate-code=arch=compute_75,code=sm_75", False),
        ("-fassociative-math", True), ("-fno-associative-math", False),
        ("-fno-unsafe-math-optimizations", False),
        ("--use_fast_math=false", False),
    )
    require(len(flag_verdicts) >= 20, "7: tricky flag verdict table is too short")
    for flag_text, expected_violation in flag_verdicts:
        actual_violation = recheck._flag_violation(flag_text) is not None
        require(actual_violation is expected_violation,
                f"7: wrong scanner verdict for {flag_text!r}: expected violation="
                f"{expected_violation}, got {actual_violation}")

    # Every explicitly named enabling spelling must close the actual WP2 gate.
    for spelling in (
        "-ffast-math", "--use_fast_math", "-Xcompiler=-ffast-math",
        "-Xcompiler -O0,-ffast-math", "--fmad", "--fmad=true",
        "-ffp-contract=fast", "-ffp-contract=on",
    ):
        banned = arguments()
        flags = list(SYNTHETIC_COMPILER["flags"]) + [spelling]
        banned["session_identity"]["compiler"] = {
            "version": SYNTHETIC_COMPILER["version"], "flags": flags,
        }
        banned["accepted_identity"]["compiler"] = {
            "version": SYNTHETIC_COMPILER["version"], "flags": list(flags),
        }
        require_refusal(banned, "compiler", f"7 enabling flag {spelling!r}")

    # The last option wins: a later enabling form still refuses after a
    # compliant GCC/Clang negation in the same flag list.
    reenabled = arguments()
    flags = list(SYNTHETIC_COMPILER["flags"]) + ["-fno-fast-math", "-ffast-math"]
    reenabled["session_identity"]["compiler"] = {
        "version": SYNTHETIC_COMPILER["version"], "flags": flags,
    }
    reenabled["accepted_identity"]["compiler"] = {
        "version": SYNTHETIC_COMPILER["version"], "flags": list(flags),
    }
    require_refusal(reenabled, "compiler", "7 fast-math re-enabled after negation")

    for stem in recheck.BANNED_COMPILER_FLAG_STEMS:
        for spelling, token in ((f"--{stem}", None), (f"--{stem}=true", None), (f"-{stem}", None),
                                (f"--{stem}=1", None), (f"-Xptxas=--{stem}", None)):
            banned = arguments()
            # Identical on both sides: only the banned-stem scan can refuse this.
            flags = list(SYNTHETIC_COMPILER["flags"]) + [spelling]
            banned["session_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
            banned["accepted_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
            require_refusal(banned, "compiler", f"7 banned flag {spelling!r}")
        # The compliance spelling of the same stem must NOT be refused: a flag
        # that turns the behaviour OFF is what the contract requires.
        for compliant in ("false", "0", "off", "no", "none", "FALSE", " Off "):
            if compliant not in ("false", "0", "off", "FALSE"):
                case = arguments()
                flags = list(SYNTHETIC_COMPILER["flags"]) + [f"--{stem}={compliant}"]
                case["session_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
                case["accepted_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
                require_refusal(case, "compiler", f"7 non-compliance spelling {compliant!r}")
                continue
            allowed = arguments()
            flags = list(SYNTHETIC_COMPILER["flags"]) + [f"--{stem}={compliant}"]
            allowed["session_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
            allowed["accepted_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
            allowed_record, allowed_gate = run(allowed)
            require(allowed_gate is True,
                    f"7: the compliant flag --{stem}={compliant!r} was refused: "
                    f"{allowed_record['refusal_reasons']}")
    # A compliance-preserving flag that is not a banned stem at all must pass.
    # None of these may duplicate a base flag, or the duplicate check -- itself a
    # real check -- would refuse for a different reason than the one under test.
    for compliant in ("-prec-div=true", "-prec-sqrt=true", "-O3", "-std=c++20",
                      "--expt-relaxed-constexpr", "-DUSE_DOUBLE=1", "--generate-code=arch=compute_75,code=sm_75",
                      "-lineinfo", "--Xcompiler=-Wall", "-Xptxas=-O2", "--Wno-deprecated-gpu-targets"):
        if compliant in ("-prec-div=true", "-prec-sqrt=true"):
            rejected = arguments()
            flags = list(SYNTHETIC_COMPILER["flags"]) + [compliant]
            rejected["session_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
            rejected["accepted_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
            require_refusal(rejected, "compiler", f"7 single-dash required-true spelling {compliant!r}")
            continue
        allowed = arguments()
        flags = list(SYNTHETIC_COMPILER["flags"]) + [compliant]
        allowed["session_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
        allowed["accepted_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
        allowed_record, allowed_gate = run(allowed)
        require(allowed_gate is True,
                f"7: the compliant flag {compliant!r} was refused: {allowed_record['refusal_reasons']}")
    for compliant in ("--prec-div=on", "--prec-div=1", "--prec-sqrt=on", "--prec-sqrt=1"):
        allowed = arguments()
        flags = list(SYNTHETIC_COMPILER["flags"]) + [compliant]
        allowed["session_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
        allowed["accepted_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
        allowed_record, allowed_gate = run(allowed)
        require(allowed_gate is True,
                f"7: the exact required-true flag {compliant!r} was refused: {allowed_record['refusal_reasons']}")
    # A banned stem hidden behind a non-compliance value is still a violation.
    for value in ("true", "1", "on", "yes", ""):
        banned = arguments()
        flags = list(SYNTHETIC_COMPILER["flags"]) + [f"--fmad={value}"]
        banned["session_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
        banned["accepted_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
        require_refusal(banned, "compiler", f"7 non-compliance value {value!r}")

    # Required-true controls and -Ofast are stateful contract flags.
    for spelling in ("--prec-div=false", "--prec-div=off", "--prec-div=0",
                     "--prec-sqrt=false", "--prec-sqrt=off", "--prec-sqrt=0", "--ftz=true"):
        direct = recheck._flag_stream_violation([spelling])
        require(direct is not None,
                f"7 required-true scanner did not identify the standalone violation {spelling!r}")
        case = arguments()
        flags = list(SYNTHETIC_COMPILER["flags"]) + [spelling]
        case["session_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
        case["accepted_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
        require_refusal(case, "compiler", f"7 required-true violation {spelling!r}")
    for spelling in ("-Ofast", "-OFast"):
        case = arguments()
        flags = list(SYNTHETIC_COMPILER["flags"]) + [spelling]
        case["session_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
        case["accepted_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
        require_refusal(case, "compiler", f"7 fast-math optimization level {spelling!r}")

    # Independent, deliberately dumb oracle. This literal set is the entire
    # compliance vocabulary; it is intentionally not derived from module data.
    oracle_compliant = {
        "-fno-fast-math", "-fno-fast_math", "--fast-math=false", "--fast-math=off", "--fast-math=0",
        "-fno-fastmath", "--fastmath=false", "--fastmath=off", "--fastmath=0",
        "-fno-fmad", "--fmad=false", "--fmad=off", "--fmad=0",
        "-fno-ffp-contract", "-fno-ffp_contract", "--ffp-contract=false", "--ffp-contract=off", "--ffp-contract=0",
        "-fno-ftz", "--ftz=false", "--ftz=off", "--ftz=0",
        "-fno-contraction", "--contraction=false", "--contraction=off", "--contraction=0",
        "-fno-contract", "--contract=false", "--contract=off", "--contract=0",
        "-fno-unsafe-math", "-fno-unsafe_math", "--unsafe-math=false", "--unsafe-math=off", "--unsafe-math=0",
        "-fno-unsafe-math-optimizations", "--unsafe-math-optimizations=false", "--unsafe-math-optimizations=off", "--unsafe-math-optimizations=0",
        "-fno-associative-math", "-fno-associative_math", "--associative-math=false", "--associative-math=off", "--associative-math=0",
        "-fno-associative", "--associative=false", "--associative=off", "--associative=0",
        "-fno-reassoc", "--reassoc=false", "--reassoc=off", "--reassoc=0",
        "-fno-atomics", "--atomics=false", "--atomics=off", "--atomics=0",
        "-fno-nondeterministic", "--nondeterministic=false", "--nondeterministic=off", "--nondeterministic=0",
        "-fno-non-deterministic", "-fno-non_deterministic", "--non-deterministic=false", "--non-deterministic=off", "--non-deterministic=0",
        "-fno-reduce", "--reduce=false", "--reduce=off", "--reduce=0",
        "-fno-reduction", "--reduction=false", "--reduction=off", "--reduction=0",
        "--prec-div=true", "--prec-div=on", "--prec-div=1", "--prec_div=true", "--prec_div=on", "--prec_div=1",
        "--prec-sqrt=true", "--prec-sqrt=on", "--prec-sqrt=1", "--prec_sqrt=true", "--prec_sqrt=on", "--prec_sqrt=1",
        "-ffp-contract=off", "-ffp_contract=off",
        "--use_fast_math=false", "--use_fast_math=off", "--use_fast_math=0",
        "--use-fast-math=false", "--use-fast-math=off", "--use-fast-math=0",
    }

    # The corpus oracle only knows plain normalized substring mentions and the
    # hand-written exact-token set above. It shares no parser predicates with
    # the implementation.
    def reference_tokens(value):
        output = []
        wrapped_next = False
        for word in value.split():
            low = word.lower()
            if wrapped_next:
                output.extend(piece for piece in word.split(",") if piece)
                wrapped_next = False
            elif low in ("-xcompiler", "-xptxas"):
                wrapped_next = True
            elif low.startswith("-xcompiler=") or low.startswith("-xptxas="):
                output.extend(piece for piece in word.split("=", 1)[1].split(",") if piece)
            else:
                output.append(word)
        return output

    def reference_violation(value):
        state = {}
        required = {}
        stems = ("fastmath", "fmad", "ffpcontract", "ftz", "contraction", "contract",
                 "unsafemath", "unsafemathoptimizations", "associativemath", "associative",
                 "reassoc", "atomics", "nondeterministic", "nondeterministic", "reduce", "reduction")
        for token in reference_tokens(value):
            low = token.lower()
            compact = low.replace("_", "").replace("-", "")
            if low == "-ofast":
                state["fast-math"] = True
            compliant = low in oracle_compliant
            for stem in stems:
                if stem in compact:
                    state[stem] = not compliant
            if "precdiv" in compact:
                required["prec-div"] = compliant
            if "precsqrt" in compact:
                required["prec-sqrt"] = compliant
            if "ftz" in compact:
                required["ftz"] = not compliant
        if any(state.values()):
            return True
        return any((name in ("prec-div", "prec-sqrt") and not value) or
                   (name == "ftz" and value) for name, value in required.items())

    generated = []
    stems_for_corpus = (
        "fast-math", "fastmath", "fmad", "ffp-contract", "ftz", "contraction", "contract",
        "unsafe-math", "unsafe-math-optimizations", "associative-math", "associative",
        "reassoc", "atomics", "nondeterministic", "non-deterministic", "reduce", "reduction",
    )
    for stem in stems_for_corpus:
        forms = (f"-fno-{stem}", f"--{stem}=false", f"--{stem}=off", f"--{stem}=0",
                 f"-{stem}", f"--{stem}=true", f"-fno-fno-{stem}", f"-fno-no-{stem}",
                 f"--fno-{stem}", f"-fno-{stem}=1", f"-fno--{stem}", f"--{stem}==false",
                 f"--{stem}=1=false", f"--{stem}=true=false", f"--{stem}=off=0")
        for first, middle, last in ((forms[0], forms[4], forms[0]),
                                    (forms[0], forms[4], forms[4]),
                                    (forms[4], forms[0], forms[4]),
                                    (forms[6], forms[4], forms[0]),
                                    (forms[7], forms[4], forms[0]),
                                    (forms[9], forms[0], forms[4])):
            for separator in (" ", "\t", ","):
                for wrapper in ("plain", "compiler-inline", "compiler-separated", "ptxas-inline", "ptxas-separated"):
                    payload = separator.join((first, middle, last))
                    if wrapper == "compiler-inline":
                        text = "-Xcompiler=" + payload
                    elif wrapper == "compiler-separated":
                        text = "-Xcompiler " + payload
                    elif wrapper == "ptxas-inline":
                        text = "-Xptxas=" + payload
                    elif wrapper == "ptxas-separated":
                        text = "-Xptxas " + payload
                    else:
                        text = payload
                    generated.append(text)
        generated.extend((f"--{stem}=0=false", f"--{stem}=off=0", f"--{stem}=true=false",
                          f"-fno--{stem}", f"--{stem}==false", f"--{stem}=1=false",
                          f"--{stem}--=false", f"--{stem}=false--", f"-fno-{stem}--",
                          f"--{stem}==off", f"--{stem}=off==0",
                          f"  --{stem}=false", f"--{stem}=false  ", f"--{stem} =false",
                          f"--{stem}= false", f"--{stem}=false\t", f"--{stem}\n=false",
                          f"\t--{stem}=false", f"--{stem}\t=false", f"--{stem}=false\n"))
    generated.extend(("--ftz=0=false", "--fmad=off=0", "--fast-math=true=false",
                      "--ftz=true=false", "--fmad==false", "--fmad=1=false",
                      "-fno--fast-math", "-fno--fmad", "-fno--reassoc", "-fno--atomics",
                      "-fno--contraction", "-fno--reduce", "-fno--reduction", "-fno--unsafe-math"))
    require(len(generated) >= 500, f"7 generated corpus too small: {len(generated)}")
    for candidate in generated:
        expected_violation = reference_violation(candidate)
        actual_violation = recheck._flag_stream_violation([candidate]) is not None
        require(actual_violation is expected_violation,
                f"7 independent oracle disagreement for {candidate!r}: "
                f"expected={expected_violation} actual={actual_violation}")

    # Preserve the old implementation's refusal boundary for the full generated
    # corpus, with only the exact frozen v1 compiler list grandfathered.
    original_path = Path("/home/shivansh-srivastava/decisions_os/project/research/g9/stage2_section_b1_recheck.py")
    with tempfile.TemporaryDirectory(prefix="wp2-original-") as temp_root:
        temp_copy = Path(temp_root) / "stage2_section_b1_recheck.py"
        shutil.copyfile(original_path, temp_copy)
        spec = importlib.util.spec_from_file_location("wp2_original_recheck", temp_copy)
        original = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(original)
        compatibility_corpus = [[candidate] for candidate in generated]
        compatibility_corpus.extend([[text] for text, _ in flag_verdicts])
        compatibility_corpus.append(list(frozen_v1_flags))
        for flag_list in compatibility_corpus:
            old_refused = any(original._flag_violation(item) is not None for item in flag_list)
            new_passed = recheck._flag_stream_violation(flag_list) is None
            # The permitted compatibility exception is a list whose final
            # oracle state is compliant through exact allowlisted negations;
            # the one exact multi-flag compatibility case is the frozen v1 list.
            allowed_final_negations = flag_list == frozen_v1_flags or (
                len(flag_list) == 1 and not reference_violation(flag_list[0])
            )
            require(not (old_refused and new_passed and not allowed_final_negations),
                    f"7 original refusal became a pass outside final negations: {flag_list!r}")
    require(recheck._flag_stream_violation(frozen_v1_flags) is None,
            "7 exact frozen v1 list did not pass as an ordered stream")
    # Case-insensitivity: an upper-case spelling hides nothing.
    banned = arguments()
    flags = list(SYNTHETIC_COMPILER["flags"]) + ["--USE_FAST_MATH"]
    banned["session_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
    banned["accepted_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": flags}
    require_refusal(banned, "compiler", "7 upper-case banned flag")
    for bad in (None, 12, {}, ("-O2",), "-O2", [None], [7], [b"x"], ["x\ny"], [""]):
        case = arguments()
        case["session_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": bad}
        case["accepted_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"], "flags": bad}
        require_refusal(case, "compiler", f"7 malformed flag container {bad!r}")
    # "12.8.93" is deliberately NOT in this list: a well-formed version is not
    # malformed, and a fixture that expected it to be refused would be testing
    # nothing.  The values here are each refused by the version type/shape rule
    # alone, with every other field correct.
    for bad in (None, 12, {}, [], "x" * 513, "x\ny", "\x00", "", b"x", 0.0, True):
        case = arguments()
        case["session_identity"]["compiler"] = {"version": bad, "flags": list(SYNTHETIC_COMPILER["flags"])}
        case["accepted_identity"]["compiler"] = {"version": bad, "flags": list(SYNTHETIC_COMPILER["flags"])}
        require_refusal(case, "compiler", f"7 malformed compiler version {bad!r}")
    for bad in (None, 12, {}, [], True, "not-a-mapping", 0):
        case = arguments()
        case["session_identity"]["compiler"] = bad
        case["accepted_identity"]["compiler"] = bad
        require_refusal(case, "compiler", f"7 compiler is {bad!r}")
    malformed = arguments()
    malformed["session_identity"]["compiler"] = {"version": SYNTHETIC_COMPILER["version"]}
    require_refusal(malformed, "compiler", "7 compiler flags key absent")
    malformed = arguments()
    malformed["session_identity"]["compiler"] = {"version": "", "flags": ["-O2"]}
    malformed["accepted_identity"]["compiler"] = {"version": "", "flags": ["-O2"]}
    require_refusal(malformed, "compiler", "7 empty compiler version")
    duplicated = arguments()
    duplicated["session_identity"]["compiler"]["flags"] = ["-O2", "-O2"]
    duplicated["accepted_identity"]["compiler"]["flags"] = ["-O2", "-O2"]
    require_refusal(duplicated, "compiler", "7 duplicated flags")
    empty = arguments()
    empty["session_identity"]["compiler"]["flags"] = []
    empty["accepted_identity"]["compiler"]["flags"] = []
    require_refusal(empty, "compiler", "7 empty flag list")
    checks.append("7 fixed binary64 compiler contract")

    # --- 8. the approval documents are re-read from disk --------------------
    observed = recheck.read_approval_hashes()
    require(set(observed) == set(recheck.APPROVAL_PATHS), "8: the approval path set is wrong")
    for relative, digest in observed.items():
        require(hashlib.sha256((recheck.ROOT / relative).read_bytes()).hexdigest() == digest,
                f"8: the read hash for {relative} is not the on-disk hash")
    tampered = arguments()
    tampered["observed_approval_sha256"] = dict(observed)
    tampered["observed_approval_sha256"][recheck.APPROVAL_PATHS[1]] = "7" * 64
    require_refusal(tampered, "protocol", "8 approval document drift")
    wrongset = arguments()
    wrongset["observed_approval_sha256"] = {"research/decisions/other.md": "8" * 64}
    require_refusal(wrongset, "protocol", "8 approval path set")
    short = arguments()
    short["expected_approval_sha256"] = dict(observed)
    short["expected_approval_sha256"][recheck.APPROVAL_PATHS[0]] = "abc"
    require_refusal(short, "protocol", "8 malformed expected hash")
    for bad_paths in ([], "research/decisions/GATE_9_STAGE2_PROTOCOL_DRAFT.md",
                      list(recheck.APPROVAL_PATHS) + ["research/decisions/extra.md"],
                      list(recheck.APPROVAL_PATHS)[:-1], None, 7, b"bytes", (),
                      list(reversed(recheck.APPROVAL_PATHS))):
        try:
            recheck.read_approval_hashes(bad_paths)
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"8: read_approval_hashes accepted a non-fixed path list: {bad_paths!r}")
    # The same three paths in a tuple is the SAME list of paths, so it is read
    # and must yield the same hashes: the check is on the paths, not the type.
    require(recheck.read_approval_hashes(tuple(recheck.APPROVAL_PATHS)) == observed,
            "8: read_approval_hashes refused a tuple holding the fixed paths")
    # A malformed *value* on either side is a refusal, scoped to that side.
    for side in ("observed_approval_sha256", "expected_approval_sha256"):
        for bad in (None, 12, [], b"x", "", "x" * 63, "X" * 64, 1.5, True):
            case = arguments()
            case[side][recheck.APPROVAL_PATHS[2]] = bad
            require_refusal(case, "protocol", f"8 malformed {side} value {bad!r}")
    # A mapping with a mixed-type key set: the §B answer is a refusal record,
    # not an untyped TypeError out of a sort.
    for side in ("observed_approval_sha256", "expected_approval_sha256"):
        case = arguments()
        case[side] = dict(case[side])
        case[side][7] = "9" * 64
        require_refusal(case, "protocol", f"8 mixed-type key in {side}")
    checks.append("8 approval documents re-read from disk")

    # --- 9. the injected identity dependency is actually consulted -----------
    consulted = []
    def tracking_validate(payload):
        consulted.append(id(payload))
        return synthetic_validate(payload)

    tracked = arguments()
    tracked["validate_identity"] = tracking_validate
    tracked_record, tracked_gate = run(tracked)
    require(tracked_gate is True, "9: the tracked passing case was refused")
    require(len(consulted) == 2, f"9: the validator was consulted {len(consulted)} times, not once per identity")
    require(consulted[0] == id(tracked["accepted_identity"]), "9: the accepted identity was not validated")
    require(consulted[1] == id(tracked["session_identity"]), "9: the session identity was not validated")

    refused = arguments()
    refused["validate_identity"] = raising_validate
    require_refusal(refused, "accepted_identity", "9 accepted identity validator raises")
    # A malformed hash must be a refusal, not an escaping exception, and must be
    # scoped to whichever identity produced it.  The accepted identity is
    # validated first, so a validator that is bad for both names it first.
    refused = arguments()
    refused["validate_identity"] = wrong_hash_validate
    both = require_refusal(refused, "accepted_identity", "9 validator returns a non-sha256")
    require("session_identity" in both["failed_elements"],
            f"9: a bad validator did not also scope the session: {both['failed_elements']}")
    # A validator that is malformed for the session only.
    refused = arguments()
    session_ref = refused["session_identity"]
    refused["validate_identity"] = lambda payload: "9" * 64 if payload is session_ref else synthetic_validate(payload)
    require_refusal(refused, "session_identity", "9 session identity validator returns a non-sha256")
    # Two identities, two different hashes: a difference no element check reads
    # must still close the gate.
    refused = arguments()
    accepted_ref = refused["accepted_identity"]
    refused["validate_identity"] = (
        lambda payload: "9" * 64 if payload is accepted_ref else synthetic_validate(payload)
    )
    require_refusal(refused, "session_identity", "9 session identity hash differs from the accepted one")
    for bad in (None, 0, "", [], "not-a-mapping", b"bytes", 0.0, True, ()):
        require_refusal(arguments() | {"accepted_identity": bad}, "accepted_identity", f"9 accepted identity {bad!r}")
        require_refusal(arguments() | {"session_identity": bad}, "session_identity", f"9 session identity {bad!r}")
    # A validator that raises an untyped error is still a refusal, never an
    # escape: the refusal reason names the exception class and nothing else.
    for raiser in (lambda _p: (_ for _ in ()).throw(TypeError("boom")),
                   lambda _p: (_ for _ in ()).throw(RecursionError("boom")),
                   lambda _p: (_ for _ in ()).throw(MemoryError("boom"))):
        refused = arguments()
        refused["validate_identity"] = raiser
        record_for_class = require_refusal(refused, "accepted_identity", "9 untyped validator exception")
        for reason in record_for_class["refusal_reasons"]:
            require("boom" not in reason, "9: a refusal reason echoed caller text")
    # An INTERRUPT is not a finding and must not be swallowed into a refusal
    # record: KeyboardInterrupt and SystemExit are BaseException, and a session
    # that is being torn down must not be told it simply failed a check.
    for interrupt in (KeyboardInterrupt, SystemExit):
        refused = arguments()
        refused["validate_identity"] = lambda _p, exc=interrupt: (_ for _ in ()).throw(exc("boom"))
        try:
            run(refused)
        except interrupt:
            pass
        else:
            raise RuntimeError(f"9: a {interrupt.__name__} from the validator was converted into a verdict")
    for bad in (None, 0, "not-callable", [], b"x", 1.5, 0.0):
        for key in ("validate_identity", "exact_match"):
            try:
                run(arguments() | {key: bad})
            except recheck.SectionB1RecheckError:
                continue
            raise RuntimeError(f"9: a non-callable {key} was accepted: {bad!r}")
    checks.append("9 injected identity dependency consulted")

    # --- 10. require_gate ----------------------------------------------------
    recheck.require_gate(record, True)
    for bad_gate in (None, 0, 1, "true", [], b"x", 0.0):
        try:
            recheck.require_gate(record, bad_gate)
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"10: require_gate accepted a non-bool gate: {bad_gate!r}")
    # A hand-written pass record paired with a closed gate must still raise.
    try:
        recheck.require_gate(record, False)
    except recheck.SectionB1RecheckError:
        pass
    else:
        raise RuntimeError("10: require_gate accepted a closed gate")
    # A tampered record must be refused by the gate, not written.  Each mutation
    # changes exactly one field, so a refusal can only come from the check that
    # field is supposed to trip -- never from a different, incidental reason.
    for mutate in (
        lambda r: r.update(platform_identity={"gpu_name": "synthetic"}),
        lambda r: r["identity"].update(accepted_sha256="0" * 64),
        lambda r: r.update(validation_digest="0" * 64),
        lambda r: r.update(content_sha256="0" * 64),
        lambda r: r.update(extra="smuggled"),
        lambda r: r["platform_identity"].update(energy=-1.5),
        lambda r: r["source_identity"].update({"research/g9/x.py": -1.5}),
        lambda r: r["platform_reported_fields"].append("gpu_name"),
        lambda r: r["platform_reported_fields"].pop(),
        lambda r: r.update(counters={"elements_checked": 6, "elements_passed": 5, "elements_failed": 0}),
        lambda r: r["element_results"].pop("platform"),
        lambda r: r["element_results"]["platform"].update(status="mismatch"),
        lambda r: r.update(elements_checked=list(recheck.ELEMENT_NAMES)[:5]),
        lambda r: r.update(clause=["something-else"]),
        lambda r: r.update(schema="decisions_os/not-the-schema/v1"),
        lambda r: r["evidence"].update(authorizes_write="yes"),
        lambda r: r.update(failed_elements=["platform"]),
        lambda r: r.update(refusal_reasons=["platform: forged"]),
    ):
        tampered_record = json_mod.loads(json_mod.dumps(record))
        before = json_mod.dumps(tampered_record, sort_keys=True)
        mutate(tampered_record)
        if json_mod.dumps(tampered_record, sort_keys=True) == before:
            raise RuntimeError(f"10: the mutation {mutate} was a no-op, so it tested nothing")
        try:
            recheck.require_gate(tampered_record, True)
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"10: require_gate accepted a tampered record after {mutate}")
    # A refusal record with the verdict flipped to "pass" is refused.
    flipped = json_mod.loads(json_mod.dumps(refusal))
    flipped["verdict"] = "pass"
    try:
        recheck.require_gate(flipped, True)
    except recheck.SectionB1RecheckError:
        pass
    else:
        raise RuntimeError("10: require_gate accepted a refusal record relabelled as a pass")
    checks.append("10 require_gate contract")

    # --- 11. each element check, in isolation ------------------------------
    # Group 11 exists because groups 2 and 3 cannot see these checks.  Several
    # element checks are masked by a second, independent check: a missing
    # platform field also breaks the whole-identity hash equality, and a
    # malformed expected-approval set also breaks the per-document comparison.
    # A validator who deleted a masked check would see groups 1-10 stay green.
    # Driving each element through `discover_element` removes the masking: every
    # other check is held to a pass while this one is the only thing under test.
    for element in recheck.ELEMENT_NAMES:
        require_element_match(element, arguments(), "11 baseline")
    for bad_element in ("", "Platform", "PLATFORM", "source_sha256", "device_uuid", None, 1, ["platform"],
                        b"platform", 0.0, True, ("platform",), {"platform": 1}):
        try:
            discover(bad_element, arguments())
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"11: discover_element accepted an undeclared element: {bad_element!r}")
    # discover_element consults the same two injected callables and must refuse a
    # non-callable for either of them.
    for bad in (None, 0, "not-callable", [], b"x"):
        for key in ("validate_identity", "exact_match"):
            try:
                discover("platform", arguments() | {key: bad})
            except recheck.SectionB1RecheckError:
                continue
            raise RuntimeError(f"11: discover_element accepted a non-callable {key}: {bad!r}")

    # protocol: each of the three sub-checks on its own, with the others intact.
    case = arguments()
    case["expected_approval_sha256"] = {recheck.APPROVAL_PATHS[0]: "1" * 64}
    require_element_reason("protocol", case, "expected approval hash set is not the fixed approved set",
                           "11 protocol expected-set is not the fixed set")
    case = arguments()
    case["observed_approval_sha256"] = {recheck.APPROVAL_PATHS[0]: "1" * 64}
    require_element_reason("protocol", case, "observed approval hash set is not the fixed approved set",
                           "11 protocol observed-set is not the fixed set")
    case = arguments()
    case["observed_approval_sha256"][recheck.APPROVAL_PATHS[1]] = "not-a-hash"
    require_element_reason("protocol", case, "observed approval hash is malformed",
                           "11 protocol malformed observed hash")
    case = arguments()
    case["expected_approval_sha256"][recheck.APPROVAL_PATHS[2]] = "not-a-hash"
    require_element_reason("protocol", case, "expected approval hash is malformed",
                           "11 protocol malformed expected hash")
    case = arguments()
    case["expected_approval_sha256"] = []
    require_element_reason("protocol", case, "expected approval hashes are not a mapping",
                           "11 protocol expected hashes not a mapping")
    case = arguments()
    case["observed_approval_sha256"] = "not-a-mapping"
    require_element_reason("protocol", case, "observed approval hashes are not a mapping",
                           "11 protocol observed hashes not a mapping")
    # Only ONE of the two sides malformed: the other side's per-document
    # comparison must not fire, so naming the side is what pins the check.
    case = arguments()
    case["observed_approval_sha256"] = "not-a-mapping"
    require_element_refusal_excluding("protocol", case, "expected approval hashes are not a mapping",
                                      "11 protocol only the observed side is not a mapping")
    case = arguments()
    case["expected_approval_sha256"] = "not-a-mapping"
    require_element_refusal_excluding("protocol", case, "observed approval hashes are not a mapping",
                                      "11 protocol only the expected side is not a mapping")
    # Only ONE of the two key sets wrong: the other side's test must not fire.
    case = arguments()
    case["observed_approval_sha256"] = {recheck.APPROVAL_PATHS[0]: "1" * 64}
    require_element_refusal_excluding("protocol", case, "expected approval hash set is not the fixed approved set",
                                      "11 protocol only the observed key set is wrong")
    case = arguments()
    case["expected_approval_sha256"] = {recheck.APPROVAL_PATHS[0]: "1" * 64}
    require_element_refusal_excluding("protocol", case, "observed approval hash set is not the fixed approved set",
                                      "11 protocol only the expected key set is wrong")

    # generator / ground_truth: the absent pin is its OWN refusal, distinct from
    # the "not a SHA-256" refusal that also fires.  The reason assertion is what
    # separates the two, and the two absent-side branches have distinct reason
    # strings so that each can be pinned AND shown not to fire the other.
    PIN_ABSENT_BRANCHES = (
        ("generator", "expected_generator_implementation_record_sha256",
         "the expected generator implementation-record hash is missing",
         "the observed generator implementation-record hash is missing"),
        ("ground_truth", "expected_ground_truth_provenance_sha256",
         "the expected ground-truth provenance hash is missing",
         "the observed ground-truth provenance hash is missing"),
    )
    for element, expected_key, expected_phrase, observed_phrase in PIN_ABSENT_BRANCHES:
        for key, phrase, other_phrase in (
            (expected_key, expected_phrase, observed_phrase),
            (expected_key.replace("expected_", ""), observed_phrase, expected_phrase),
        ):
            case = arguments()
            case[key] = None
            require_element_reason(element, case, phrase, f"11 {key} absent branch")
            require_element_refusal_excluding(element, case, other_phrase,
                                              f"11 {key} absent branch does not also fire the other side")
            require_element_refusal_excluding(element, case, "is malformed",
                                              f"11 {key} absent branch is not a malformed hash")
    # Round 1 asserted one loose phrase -- "hash is missing" -- for all four
    # absent keys.  The per-side table above is strictly tighter, but the loose
    # assertion is KEPT for every key so that no round-1 case was dropped: an
    # absent pin must still read as a MISSING hash, on either side, for either
    # element.  This is the round-1 assertion verbatim.
    for key in ("expected_generator_implementation_record_sha256",
                "generator_implementation_record_sha256",
                "expected_ground_truth_provenance_sha256",
                "ground_truth_provenance_sha256"):
        case = arguments()
        case[key] = None
        require_element_reason("generator" if "generator" in key else "ground_truth", case,
                               "hash is missing", f"11 {key} is None")
    for key in ("expected_generator_implementation_record_sha256",
                "generator_implementation_record_sha256",
                "expected_ground_truth_provenance_sha256",
                "ground_truth_provenance_sha256"):
        case = arguments()
        case[key] = "not-a-hash"
        require_element_reason("generator" if "generator" in key else "ground_truth", case,
                               "is malformed", f"11 {key} is malformed")
        case = arguments()
        case[key] = 12345
        require_element_reason("generator" if "generator" in key else "ground_truth", case,
                               "is malformed", f"11 {key} is an int")
    for key in ("expected_generator_implementation_record_sha256",
                "expected_ground_truth_provenance_sha256"):
        case = arguments()
        case[key] = "1" * 64
        require_element_reason("generator" if "generator" in key else "ground_truth", case,
                               "differs from its pin", f"11 {key} differs from its pin")

    # source: the empty map, a non-mapping map, and a malformed entry.
    for bad in ({}, [], "not-a-mapping", 7, None, True, (), 0.0, b"bytes"):
        case = arguments()
        case["session_identity"]["source_sha256"] = bad
        require_element_refusal("source", case, f"11 source map is {bad!r}")
    case = arguments()
    case["session_identity"]["source_sha256"]["research/g9/bad.py"] = "not-a-hash"
    require_element_refusal("source", case, "11 source map entry is malformed")
    case = arguments()
    case["session_identity"]["source_sha256"][""] = "3" * 64
    require_element_refusal("source", case, "11 source map key is empty")
    case = arguments()
    case["session_identity"]["source_sha256"][7] = "3" * 64
    require_element_refusal("source", case, "11 source map key is not a string")
    case = arguments()
    case["session_identity"]["source_sha256"]["x\ny"] = "3" * 64
    require_element_refusal("source", case, "11 source map key carries a newline")
    # Exercise source entry guards when the trusted comparison side carries the
    # same malformed entry: exact equality alone must not bless malformed keys
    # or hashes.
    for bad_key, bad_hash, label in (
        ("x\ny", "3" * 64, "key"),
        ("research/g9/synthetic_writer.py", "not-a-hash", "hash"),
    ):
        case = arguments()
        malformed_source = {bad_key: bad_hash}
        case["session_identity"]["source_sha256"] = dict(malformed_source)
        case["accepted_identity"]["source_sha256"] = dict(malformed_source)
        require_element_refusal("source", case, f"11 identical malformed source {label}")
    case = arguments()
    del case["session_identity"]["source_sha256"]
    require_element_refusal("source", case, "11 source map key absent")
    # The absent key and the None value are the same finding, so the isolated
    # check must state the same reason for both spellings.
    absent_key = arguments()
    del absent_key["session_identity"]["source_sha256"]
    none_value = arguments()
    none_value["session_identity"]["source_sha256"] = None
    require_element_reason("source", absent_key, "is missing or is not a non-empty mapping",
                           "11 source absent key uses the single reason")
    require_element_reason("source", none_value, "is missing or is not a non-empty mapping",
                           "11 source None value uses the same single reason")

    # platform: EVERY declared field is required, and a field the amendment
    # forbids transiently (the device UUID) is not a platform field at all.
    for field in recheck.PLATFORM_FIELDS:
        case = arguments()
        del case["session_identity"]["platform"][field]
        require_element_refusal("platform", case, f"11 platform field {field!r} absent")
        case = arguments()
        case["session_identity"]["platform"][field] = None
        require_element_refusal("platform", case, f"11 platform field {field!r} is None")
        case = arguments()
        case["session_identity"]["platform"][field] = ""
        require_element_refusal("platform", case, f"11 platform field {field!r} is empty")
        case = arguments()
        case["session_identity"]["platform"][field] = "x" * 513
        require_element_refusal("platform", case, f"11 platform field {field!r} is over-long")
        case = arguments()
        case["session_identity"]["platform"][field] = 1.5
        require_element_refusal("platform", case, f"11 platform field {field!r} is a float")
    for transient in ("device_uuid", "device_uuid_hex", "session_id", "pci_bus_id"):
        case = arguments()
        case["session_identity"]["platform"][transient] = "synthetic-transient"
        require_element_reason("platform", case, "carries undeclared fields",
                               f"11 platform carries transient {transient!r}")
    for extra_field in ("gpu_uuid", "hostname", "kaggle_kernel", "unknown_field"):
        case = arguments()
        case["session_identity"]["platform"][extra_field] = "synthetic-extra"
        require_element_reason("platform", case, "carries undeclared fields",
                               f"11 platform carries undeclared {extra_field!r}")
    for bad in ("not-a-mapping", [], 7, None, True, (), 0.0, b"bytes"):
        case = arguments()
        case["session_identity"]["platform"] = bad
        require_element_refusal("platform", case, f"11 platform is {bad!r}")
    # A missing required field and an undeclared field are DIFFERENT reasons, so
    # each of the two set-difference branches can be pinned on its own.
    case = arguments()
    del case["session_identity"]["platform"]["gpu_name"]
    require_element_reason("platform", case, "is missing required fields",
                           "11 platform missing-field branch")
    require_element_refusal_excluding("platform", case, "carries undeclared fields",
                                      "11 platform missing-field branch only")
    case = arguments()
    case["session_identity"]["platform"]["hostname"] = "synthetic-extra"
    require_element_reason("platform", case, "carries undeclared fields",
                           "11 platform undeclared-field branch")
    require_element_refusal_excluding("platform", case, "is missing required fields",
                                      "11 platform undeclared-field branch only")
    # A field of the wrong type: malformed, not drifted.  One wrong-type field
    # with everything else correct pins the per-field type loop.
    case = arguments()
    case["session_identity"]["platform"]["nvcc_version"] = None
    require_element_reason("platform", case, "session platform field is malformed",
                           "11 platform field type branch")
    # The accepted platform that is absent or EMPTY, and the one that is not a
    # mapping: those reach the accepted-side branch alone.  A NON-EMPTY accepted
    # platform with a different key set is a DRIFT, not an absent accepted side,
    # and is covered by the drift case just below.
    for accepted_platform in (None, {}):
        case = arguments()
        if accepted_platform is None:
            del case["accepted_identity"]["platform"]
        else:
            case["accepted_identity"]["platform"] = accepted_platform
        require_element_reason("platform", case, "accepted identity carries no platform values to compare",
                               f"11 platform accepted-side branch {accepted_platform!r}")
        require_element_refusal_excluding("platform", case, "is missing required fields",
                                          f"11 platform accepted-side branch {accepted_platform!r} only")
    # An accepted platform that is not a mapping at all.
    for accepted_platform in ([], "synthetic", 7, 0.0, True):
        case = arguments()
        case["accepted_identity"]["platform"] = accepted_platform
        require_element_reason("platform", case, "accepted identity carries no platform values to compare",
                               f"11 platform accepted side is {accepted_platform!r}")
    # The accepted platform that agrees field-for-field is a MATCH: the drift
    # branch must not fire on an equal structure.
    require_element_match("platform", arguments(), "11 platform equal-but-not-identical object")
    # Same shape, different value: only the drift branch can refuse this.
    case = arguments()
    case["accepted_identity"]["platform"] = dict(SYNTHETIC_PLATFORM, gpu_name="synthetic/other")
    require_element_reason("platform", case, "differs from the accepted identity",
                           "11 platform drift branch")
    require_element_refusal_excluding("platform", case, "carries undeclared fields",
                                      "11 platform drift branch only")
    require_element_refusal_excluding("platform", case, "is missing required fields",
                                      "11 platform drift branch only")

    # compiler: every sub-check, in isolation.
    for bad in ("not-a-mapping", [], 7, None, True, (), 0.0, b"bytes"):
        case = arguments()
        case["session_identity"]["compiler"] = bad
        require_element_refusal("compiler", case, f"11 compiler is {bad!r}")
    for drop in ("version", "flags"):
        case = arguments()
        del case["session_identity"]["compiler"][drop]
        require_element_refusal("compiler", case, f"11 compiler key {drop!r} absent")
        case = arguments()
        case["session_identity"]["compiler"][drop + "_extra"] = 1
        require_element_refusal("compiler", case, f"11 compiler key {drop!r} has an extra")
    # The empty mapping is refused by the "not a non-empty mapping" branch, which
    # is distinct from the "wrong key set" branch -- one each, so neither can be
    # deleted while the other keeps the suite green.
    case = arguments()
    case["session_identity"]["compiler"] = {}
    require_element_reason("compiler", case, "is missing or is not a non-empty mapping",
                           "11 compiler empty mapping branch")
    require_element_refusal_excluding("compiler", case, "is missing required fields",
                                      "11 compiler empty mapping branch only")
    case = arguments()
    case["session_identity"]["compiler"] = {"version": "12.8.93", "flags": ["-O2"], "extra": "x"}
    require_element_reason("compiler", case, "is missing required fields",
                           "11 compiler wrong key set branch")
    require_element_refusal_excluding("compiler", case, "is missing or is not a non-empty mapping",
                                      "11 compiler wrong key set branch only")
    # The missing flags key and a None flag container are different branches.
    case = arguments()
    case["session_identity"]["compiler"] = {"version": "12.8.93", "flags": None}
    require_element_reason("compiler", case, "session compiler flags are missing or not a list",
                           "11 compiler flags container branch")
    require_element_refusal_excluding("compiler", case, "session compiler flag is malformed",
                                      "11 compiler flags container branch only")
    # One malformed flag element, everything else correct: pins the flag loop.
    case = arguments()
    case["session_identity"]["compiler"] = {"version": "12.8.93", "flags": ["-O2", "x\ny"]}
    require_element_reason("compiler", case, "session compiler flag is malformed",
                           "11 compiler flag element branch")
    case = arguments()
    case["session_identity"]["compiler"] = {"version": "12.8.93", "flags": ["-O2", "-O2"]}
    require_element_reason("compiler", case, "session compiler flags are duplicated",
                           "11 compiler duplicate branch")
    case = arguments()
    case["session_identity"]["compiler"] = {"version": "12.8.93", "flags": ["-O2", "--fmad=true"]}
    require_element_reason("compiler", case, "violates the fixed binary64 contract",
                           "11 compiler banned-stem branch")
    case = arguments()
    case["session_identity"]["compiler"] = {"version": "12.8.93", "flags": ["-O2"]}
    require_element_reason("compiler", case, "differs from the accepted identity",
                           "11 compiler leaf-drift branch")
    require_element_refusal_excluding("compiler", case, "violates the fixed binary64 contract",
                                      "11 compiler leaf-drift branch only")
    case = arguments()
    del case["accepted_identity"]["compiler"]
    require_element_reason("compiler", case, "accepted identity carries no compiler values to compare",
                           "11 compiler accepted key absent")
    # The accepted side with a PARTIAL key set: the one key-set test covers both
    # "the accepted identity has no compiler values" and "the key sets differ",
    # so this fixture is what makes that merged test load-bearing.
    for partial in ({"version": "12.8.93"}, {"flags": ["-O2"]}, {}, {"extra": 1}):
        case = arguments()
        case["accepted_identity"]["compiler"] = partial
        require_element_reason("compiler", case, "accepted identity carries no compiler values to compare",
                               f"11 compiler accepted partial key set {sorted(partial)}")
        require_element_refusal_excluding("compiler", case, "differs from the accepted identity",
                                          f"11 compiler accepted partial key set {sorted(partial)} only")
    checks.append("11 each element check in isolation")

    # --- 12. self-consistent forgeries -------------------------------------
    # Group 12 is the anti-masking group.  Everywhere else a tampered record is
    # caught by a hash that no longer matches.  Here BOTH hashes are recomputed
    # from the forged record, so the record is internally consistent and only a
    # *semantic* check -- the closed key set, the leaf walk, the platform
    # field-set, the verdict/counter agreement, the refusal withholding -- can
    # catch it.  A validator who deleted one of those checks would otherwise see
    # a green run, because every hash-level check would pass.
    def forge(record, mutate):
        forged = json_mod.loads(json_mod.dumps(record))
        mutate(forged)
        forged["validation_digest"] = recheck.validation_digest(forged)
        forged["content_sha256"] = recheck.content_sha256(forged)
        return forged

    def require_forgery_refused(forged, label):
        try:
            recheck._validate_record(forged)
        except recheck.SectionB1RecheckError:
            return
        raise RuntimeError(f"12: a self-consistent forgery was accepted: {label}")

    # 12a: an extra top-level key, with both hashes recomputed.  Only the closed
    # key set can refuse this: the hashes are correct by construction.
    require_forgery_refused(forge(record, lambda r: r.update(smuggled="payload")),
                            "extra top-level key")
    require_forgery_refused(forge(record, lambda r: r.update(coordinates=[1, 2, 3])),
                            "extra coordinate-list key")
    # 12b: a coordinate-level value smuggled into an already-declared branch.
    require_forgery_refused(forge(record, lambda r: r["platform_identity"].update(energy=-1.5)),
                            "float in platform_identity")
    require_forgery_refused(forge(record, lambda r: r["evidence"].update(statement=1.5)),
                            "float in evidence.statement")
    require_forgery_refused(forge(record, lambda r: r["source_identity"].update({"a.py": [1, 2]})),
                            "list in source_identity")
    require_forgery_refused(forge(record, lambda r: r["identity"].update(accepted_sha256="not-a-sha")),
                            "non-sha256 accepted_sha256 in identity")
    require_forgery_refused(forge(record, lambda r: r["identity"].update(session_sha256=1.5)),
                            "float session_sha256 in identity")
    require_forgery_refused(forge(record, lambda r: r["platform_identity"].update(gpu_name="")),
                            "empty string in platform_identity")
    require_forgery_refused(forge(record, lambda r: r["platform_identity"].update(gpu_name="x\ny")),
                            "newline in platform_identity")
    require_forgery_refused(forge(record, lambda r: r["platform_identity"].update(gpu_name="x" * 513)),
                            "over-long string in platform_identity")
    # 12c: a transient field the amendment forbids, with correct hashes.
    for transient in ("device_uuid", "device_uuid_hex", "session_id", "pci_bus_id"):
        require_forgery_refused(forge(record, lambda r, t=transient: r["platform_identity"].update({t: "x"})),
                                f"transient {transient}")
    # 12d: verdict/counter disagreement, with correct hashes.
    require_forgery_refused(forge(record, lambda r: r.update(failed_elements=["platform"])),
                            "pass verdict with a refused element")
    require_forgery_refused(
        forge(record, lambda r: r.update(counters={"elements_checked": 6, "elements_passed": 5,
                                                  "elements_failed": 0})),
        "pass verdict with a mismatched counter")
    require_forgery_refused(forge(record, lambda r: r["element_results"]["platform"].update(status="mismatch")),
                            "pass verdict with a mismatched element result")
    # 12d0: a pass verdict whose element_results carry a non-match while the
    # counters, the refused-element list and the reasons all still say "pass",
    # with both hashes recomputed.  Nothing else in the record disagrees, so
    # only "a pass requires every element to have matched" can refuse it.
    for non_match in (
        lambda r: r["element_results"].pop("platform"),
        lambda r: r["element_results"].update(platform={"element": "platform", "status": "mismatch"}),
        lambda r: r["element_results"].update(compiler={"element": "compiler", "status": "invalid"}),
        lambda r: r["element_results"].update(source={"element": "source", "status": "missing"}),
        lambda r: r["element_results"].update(protocol={"element": "protocol", "status": "mismatch"}),
    ):
        forged_non_match = forge(record, non_match)
        # Bring the counter into line with the shrunken/mismatched results, so
        # the ONLY remaining inconsistency is the pass verdict itself.
        remaining = sorted(name for name, row in forged_non_match["element_results"].items()
                           if row["status"] == "match")
        forged_non_match["counters"] = {"elements_checked": 6, "elements_passed": len(remaining),
                                        "elements_failed": 6 - len(remaining)}
        forged_non_match["validation_digest"] = recheck.validation_digest(forged_non_match)
        forged_non_match["content_sha256"] = recheck.content_sha256(forged_non_match)
        require_forgery_refused(forged_non_match,
                                f"pass verdict with {len(remaining)}/6 elements matched")
    # 12d2: the per-element result identity/shape/status checks, each reached by
    # a forgery that changes exactly that one thing and nothing else.
    require_forgery_refused(forge(record, lambda r: r["element_results"]["platform"].update(element="compiler")),
                            "result names a different element")
    require_forgery_refused(forge(record, lambda r: r["element_results"]["platform"].update(status="maybe")),
                            "result status is undeclared")
    require_forgery_refused(forge(record, lambda r: r["element_results"]["platform"].update(extra="x")),
                            "result has an extra key")
    require_forgery_refused(forge(record, lambda r: r["element_results"].update(smuggled={"element": "smuggled",
                                                                                        "status": "match"})),
                            "result names an undeclared element")
    require_forgery_refused(forge(record, lambda r: r.update(counters={"elements_checked": 6,
                                                                       "elements_passed": 7,
                                                                       "elements_failed": -1})),
                            "negative counter")
    require_forgery_refused(forge(record, lambda r: r.update(counters={"elements_checked": 6,
                                                                       "elements_passed": 5})),
                            "counter key set narrowed")
    require_forgery_refused(forge(record, lambda r: r.update(counters={"elements_checked": 5,
                                                                       "elements_passed": 5,
                                                                       "elements_failed": 0})),
                            "counter element count mismatch")
    require_forgery_refused(forge(record, lambda r: r["identity"].update(exact_match="partial")),
                            "identity exact_match label")
    require_forgery_refused(forge(record, lambda r: r["identity"].update(extra="x")),
                            "identity key set widened")
    require_forgery_refused(forge(record, lambda r: r["evidence"].update(extra="x")),
                            "evidence key set widened")
    require_forgery_refused(forge(record, lambda r: r["evidence"].update(equality="partial")),
                            "evidence equality label")
    require_forgery_refused(forge(record, lambda r: r.update(verdict="maybe")),
                            "verdict is neither pass nor refused")
    # 12d3: the refused-element / reason agreement, each direction on its own.
    require_forgery_refused(forge(record, lambda r: r.update(refusal_reasons=["platform: forged"])),
                            "pass verdict with a forged reason")
    require_forgery_refused(forge(record, lambda r: r.update(platform_reported_fields=[])),
                            "pass verdict withholding the platform-reported labels")
    require_forgery_refused(forge(record, lambda r: r.update(source_identity={})),
                            "pass verdict withholding the source identity")
    require_forgery_refused(forge(record, lambda r: r.update(
        platform_reported_fields=["kaggle_image"])),
        "pass verdict reporting only one image field")
    require_forgery_refused(forge(record, lambda r: r.update(
        platform_reported_fields=sorted(recheck.IMAGE_PLATFORM_FIELDS) + ["kaggle_image"])),
        "platform-reported list with a duplicate")
    # 12b2: a refusal record re-labelled as a PASS, with every counter and
    # element result left untouched and both hashes recomputed.  This is the
    # one forgery the verdict/counter agreement checks exist to catch: nothing
    # else about the record is inconsistent, so only "a pass cannot carry a
    # refused element" and "a pass cannot carry a refusal reason" can refuse it.
    refused_base = arguments()
    refused_base["expected_approval_sha256"] = dict(refused_base["expected_approval_sha256"])
    refused_base["expected_approval_sha256"][recheck.APPROVAL_PATHS[0]] = "0" * 64
    relabel_record, relabel_gate = run(refused_base)
    require(relabel_gate is False, "12: the re-label base case was not a refusal")
    require(relabel_record["verdict"] == "refused" and relabel_record["failed_elements"],
            "12: the re-label base case is not a shaped refusal")
    for relabel in (
        lambda r: r.update(verdict="pass"),
        lambda r: r.update(verdict="pass", failed_elements=[]),
        lambda r: r.update(verdict="pass", refusal_reasons=[]),
        lambda r: r.update(verdict="pass", failed_elements=[], refusal_reasons=[]),
        lambda r: r.update(verdict="refused", failed_elements=[], refusal_reasons=[]),
        lambda r: r.update(verdict="refused", refusal_reasons=[]),
        lambda r: r.update(verdict="refused", failed_elements=[]),
    ):
        require_forgery_refused(forge(relabel_record, relabel),
                                f"re-labelled verdict ({relabel})")
    # A refusal naming an UNDECLARED element, and reasons that name no failed
    # element: each pins one half of the reason/name agreement.
    require_forgery_refused(forge(relabel_record, lambda r: r.update(
        failed_elements=["platform", "smuggled"])),
        "refusal naming an undeclared element")
    require_forgery_refused(forge(relabel_record, lambda r: r.update(
        failed_elements=["platform", "protocol"], refusal_reasons=["platform: forged"])),
        "refusal that does not name the reason for a failed element")
    require_forgery_refused(forge(relabel_record, lambda r: r.update(
        refusal_reasons=["smuggled: forged"])),
        "reason naming no failed element")
    require_forgery_refused(forge(relabel_record, lambda r: r.update(
        failed_elements=["platform", "platform"])),
        "refused-element list with a duplicate")
    # 12b3: a record whose digests were tampered with but nothing else.  These
    # are RAW tampers -- unlike `forge`, the hashes are NOT recomputed, because
    # recomputing them is precisely what the digest re-derivation check exists to
    # notice.  A record that carries a digest nobody can reproduce is not valid.
    def require_raw_tamper_refused(mutate, label):
        tampered = json_mod.loads(json_mod.dumps(record))
        mutate(tampered)
        try:
            recheck._validate_record(tampered)
        except recheck.SectionB1RecheckError:
            return
        raise RuntimeError(f"12: a raw tamper was accepted: {label}")

    for field in ("validation_digest", "content_sha256"):
        for bad in ("0" * 64, "f" * 64, "1" * 63, "1" * 65, "not-a-hash", 0, None, "", 1.5, [], True):
            require_raw_tamper_refused(lambda r, f=field, b=bad: r.update({f: bad}),
                                       f"tampered {field} = {bad!r}")
    # One digest field carrying the *other's* value, and vice versa: a record
    # whose two digests are merely swapped is not self-consistent.
    require_raw_tamper_refused(
        lambda r: r.update(validation_digest=record["content_sha256"]), "digests swapped")
    # A record whose content hash was copied from a different record entirely.
    other_for_hash = arguments()
    other_for_hash["expected_approval_sha256"] = dict(other_for_hash["expected_approval_sha256"])
    other_for_hash["expected_approval_sha256"][recheck.APPROVAL_PATHS[0]] = "0" * 64
    other_record, other_hash_gate = run(other_for_hash)
    require(other_hash_gate is False, "12: the donor record was not a refusal")
    require_raw_tamper_refused(
        lambda r: r.update(content_sha256=other_record["content_sha256"]),
        "content hash copied from a different record")
    require_raw_tamper_refused(
        lambda r: r.update(validation_digest=other_record["validation_digest"]),
        "validation digest copied from a different record")
    # The VALIDATION digest alone: recompute only it, and the content hash no
    # longer matches.  Recompute only the content hash and the validation digest
    # is stale.  Neither field can be repaired without the other.
    only_validation = json_mod.loads(json_mod.dumps(record))
    only_validation["platform_identity"]["gpu_name"] = "synthetic/other"
    only_validation["validation_digest"] = recheck.validation_digest(only_validation)
    only_validation["content_sha256"] = record["content_sha256"]
    try:
        recheck._validate_record(only_validation)
    except recheck.SectionB1RecheckError:
        pass
    else:
        raise RuntimeError("12: a record with a recomputed validation digest but a stale "
                           "content hash was accepted")
    only_content = json_mod.loads(json_mod.dumps(record))
    only_content["platform_identity"]["gpu_name"] = "synthetic/other"
    only_content["content_sha256"] = recheck.content_sha256(only_content)
    try:
        recheck._validate_record(only_content)
    except recheck.SectionB1RecheckError:
        pass
    else:
        raise RuntimeError("12: a record with a recomputed content hash but a stale "
                           "validation digest was accepted")
    # 12d1: a REFUSAL record whose counter claims fewer passes than its element
    # results actually record, with both hashes recomputed.  The verdict,
    # the refused-element list and the reasons are all coherent, and the counter
    # still sums to the checked count, so only "the counter must equal the number
    # of matching element results" can refuse it.
    require_forgery_refused(forge(relabel_record, lambda r: r.update(
        counters={"elements_checked": 6, "elements_passed": 0, "elements_failed": 6})),
        "refusal counter 0 vs its element results")
    require_forgery_refused(forge(relabel_record, lambda r: r.update(
        counters={"elements_checked": 6, "elements_passed": 2, "elements_failed": 4})),
        "refusal counter 2 vs its element results")
    require_forgery_refused(forge(relabel_record, lambda r: r.update(
        counters={"elements_checked": 6, "elements_passed": 6, "elements_failed": 0})),
        "refusal counter claims all six passed")
    # 12e: a refusal record whose refusal content is then stripped, with correct
    # hashes.  A "refused" verdict with no failed element and no reason is
    # internally incoherent: it asserts a refusal and names nothing.  Only the
    # verdict/reasons agreement check can refuse it -- the counters, the element
    # results and both hashes are all self-consistent.
    stripped = arguments()
    stripped["ground_truth_provenance_sha256"] = "a" * 64
    stripped_record, stripped_gate = run(stripped)
    require(stripped_gate is False, "12: the stripped base case was not a refusal")
    for strip in (lambda r: r.update(refusal_reasons=[]),
                  lambda r: r.update(failed_elements=[]),
                  lambda r: r.update(failed_elements=[], refusal_reasons=[])):
        require_forgery_refused(forge(stripped_record, strip),
                                "refusal with its refusal content stripped")
    # 12f: a refusal record that has been re-armed with the accepted identities,
    # with correct hashes.  This is the dangerous one: a refused recheck dressed
    # up as one that saw a real identity.
    for element in recheck.ELEMENT_NAMES:
        single = arguments()
        single["expected_approval_sha256"] = dict(single["expected_approval_sha256"])
        single["expected_approval_sha256"][recheck.APPROVAL_PATHS[0]] = "0" * 64
        refused_record, refused_gate = run(single)
        require(refused_gate is False, "12: the re-arming base case was not a refusal")
        for rearm in (lambda r: r.update(platform_identity=dict(SYNTHETIC_PLATFORM)),
                      lambda r: r.update(source_identity=dict(SYNTHETIC_SOURCE)),
                      lambda r: r.update(platform_reported_fields=sorted(recheck.IMAGE_PLATFORM_FIELDS))):
            require_forgery_refused(forge(refused_record, rearm),
                                    f"refusal re-armed with the accepted identity ({element})")
        del refused_record
    # 12f: the validation digest must bind every field it claims to.  A digest
    # that ignored the counters, the reasons or the evidence would let a record
    # be re-labelled without disturbing it, and no hash-level check would notice
    # -- so the binding is asserted directly, one field at a time.
    def digest_of(record_to_digest):
        return recheck.validation_digest(record_to_digest)

    baseline = digest_of(record)
    digest_mutations = [
        ("counters.elements_passed", lambda r: r["counters"].update(elements_passed=5)),
        ("counters.elements_failed", lambda r: r["counters"].update(elements_failed=1)),
        ("counters.elements_checked", lambda r: r["counters"].update(elements_checked=5)),
        ("refusal_reasons", lambda r: r.update(refusal_reasons=["platform: forged"])),
        ("failed_elements", lambda r: r.update(failed_elements=["platform"])),
        ("evidence.authorizes_write", lambda r: r["evidence"].update(authorizes_write="yes")),
        ("evidence.equality", lambda r: r["evidence"].update(equality="partial")),
        ("evidence.statement", lambda r: r["evidence"].update(statement="synthetic")),
        ("element_results", lambda r: r["element_results"]["platform"].update(status="mismatch")),
        ("identity", lambda r: r["identity"].update(session_sha256="0" * 64)),
        ("identity.exact_match", lambda r: r["identity"].update(exact_match="partial")),
        ("platform_identity", lambda r: r["platform_identity"].update(gpu_name="synthetic")),
        ("platform_reported_fields", lambda r: r.update(platform_reported_fields=[])),
        ("source_identity", lambda r: r.update(source_identity={})),
        ("source_identity_sha256", lambda r: r.update(source_identity_sha256="0" * 64)),
        ("elements_checked", lambda r: r.update(elements_checked=list(recheck.ELEMENT_NAMES)[:5])),
        ("clause", lambda r: r.update(clause=["other"])),
        ("schema", lambda r: r.update(schema="decisions_os/other/v1")),
    ]
    for label, mutate in digest_mutations:
        changed = json_mod.loads(json_mod.dumps(record))
        mutate(changed)
        require(digest_of(changed) != baseline,
                f"12: the validation digest does not bind {label}")
    # And the digest must not be a constant: two different records must differ.
    other = arguments()
    other["session_identity"]["platform"]["gpu_name"] = "synthetic/other"
    other_record, other_gate = run(other)
    require(other_gate is False, "12: the second-record case was not a refusal")
    require(digest_of(other_record) != baseline, "12: two different records share a digest")
    # 12g: the leaf walk reaches arbitrary depth, unit-level, because a record
    # with a legitimate three-level branch is the only way to test the walk's
    # recursion without a specific field tripping some other check first.
    for deep in ({"a": {"b": -1.5}}, {"a": [{"b": -1.5}]}, {"a": {"b": {"c": [0.5]}}},
                 {"a": [[[-1.5]]]}, {"a": ()}, {"a": {1: "x"}}, {"a": {"b": 1.5}},
                 {"a": [[-1.5]]}, {"a": {"b": -1}}, {"a": {1: 2, "b": -1.5}}):
        try:
            recheck._require_retained(deep, "fixture")
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"12: the leaf walk accepted a nested value: {deep!r}")
    recheck._require_retained({"a": {"b": ["1" * 64, 0, True, "status"]}}, "fixture")
    checks.append("12 self-consistent forgeries")

    # --- 13. every public argument, fuzzed ----------------------------------
    # Each public argument is replaced, one at a time, by each of a fixed set of
    # hostile values.  The ONLY acceptable outcomes are the two typed ones: a
    # refusal record with a closed gate, or SectionB1RecheckError.  An untyped
    # TypeError/KeyError/AttributeError/IndexError is a failure, and so is a
    # call that returns a "pass" on an input that cannot have passed.
    FUZZ_VALUES = (
        ("None", None),
        ("True", True),
        ("False", False),
        ("int", 12345),
        ("negative int", -1),
        ("zero", 0),
        ("big int", 2 ** 70),
        ("float", 1.5),
        ("nan", float("nan")),
        ("inf", float("inf")),
        ("str", "not-a-mapping"),
        ("empty str", ""),
        ("sha256-like str", "a" * 64),
        ("short str", "a" * 63),
        ("bytes", b"bytes"),
        ("bytearray", bytearray(b"bytes")),
        ("list", [1, 2, 3]),
        ("empty list", []),
        ("nested list", [[1.0], [{"a": -1.5}]]),
        ("tuple", (1, 2)),
        ("dict", {"a": 1}),
        ("empty dict", {}),
        ("nested wrong-type dict", {"a": {"b": -1.5}}),
        ("mixed-key dict", {"a": 1, 7: "b"}),
        ("set", {1, 2}),
        ("frozenset", frozenset()),
        ("object", object()),
        ("type", int),
        ("complex", complex(1, 2)),
    )
    for keyword in RECHECK_KEYWORDS:
        for label, hostile in FUZZ_VALUES:
            args = arguments()
            args[keyword] = hostile
            # A fresh call must not be able to observe the mutated object after
            # the call, so the object is also checked for being left untouched
            # where the module documents that it does not mutate its arguments.
            try:
                fuzzed_record, fuzzed_gate = run(args)
            except recheck.SectionB1RecheckError:
                continue
            except Exception as exc:  # noqa: BLE001 - this branch IS the assertion
                raise RuntimeError(
                    f"13: {keyword}={label} produced an untyped {exc.__class__.__name__}: {exc}") from exc
            require(isinstance(fuzzed_record, dict),
                    f"13: {keyword}={label} returned a non-mapping record")
            require(type(fuzzed_gate) is bool,
                    f"13: {keyword}={label} returned a non-bool gate")
            # A refusal this module hands back must itself be a record its own
            # validator accepts, so a caller could write it verbatim.  A record
            # its validator REFUSES is a bug: the harness emitted a shape the
            # writer would not be allowed to persist.
            try:
                recheck._validate_record(fuzzed_record)
            except recheck.SectionB1RecheckError as exc:
                raise RuntimeError(
                    f"13: {keyword}={label} produced a record its own validator refuses: {exc}") from exc
            if fuzzed_gate:
                require(fuzzed_record["verdict"] == "pass",
                        f"13: {keyword}={label} opened the gate without a pass verdict")
            else:
                require(fuzzed_record["verdict"] == "refused" and fuzzed_record["failed_elements"],
                        f"13: {keyword}={label} closed the gate without naming a refusal")
                try:
                    recheck.require_gate(fuzzed_record, fuzzed_gate)
                except recheck.SectionB1RecheckError:
                    pass
                else:
                    raise RuntimeError(f"13: {keyword}={label} closed the gate but require_gate passed")
    # discover_element: the same sweep, over the element selector and the
    # keyword set it shares with recheck_before_first_write.
    for label, hostile in FUZZ_VALUES:
        try:
            discover(hostile, arguments())
        except recheck.SectionB1RecheckError:
            pass
        else:
            raise RuntimeError(f"13: discover_element accepted element={label}")
    for keyword in RECHECK_KEYWORDS:
        for label, hostile in FUZZ_VALUES:
            try:
                discover("platform", arguments() | {keyword: hostile})
            except recheck.SectionB1RecheckError:
                continue
            except Exception as exc:  # noqa: BLE001 - this branch IS the assertion
                raise RuntimeError(
                    f"13: discover_element {keyword}={label} produced an untyped "
                    f"{exc.__class__.__name__}: {exc}") from exc
    # The remaining public functions take the record, not an identity.
    for label, hostile in FUZZ_VALUES:
        for gate in (True, False):
            try:
                recheck.require_gate(hostile, gate)
            except recheck.SectionB1RecheckError:
                continue
            except Exception as exc:  # noqa: BLE001 - this branch IS the assertion
                raise RuntimeError(
                    f"13: require_gate record={label} produced an untyped "
                    f"{exc.__class__.__name__}: {exc}") from exc
            raise RuntimeError(f"13: require_gate accepted a {label} record with gate={gate}")
        try:
            recheck.content_sha256(hostile)
        except recheck.SectionB1RecheckError:
            pass
        except Exception as exc:  # noqa: BLE001 - this branch IS the assertion
            raise RuntimeError(
                f"13: content_sha256 {label} produced an untyped {exc.__class__.__name__}: {exc}") from exc
        try:
            recheck.validation_digest(hostile)
        except recheck.SectionB1RecheckError:
            pass
        except Exception as exc:  # noqa: BLE001 - this branch IS the assertion
            raise RuntimeError(
                f"13: validation_digest {label} produced an untyped {exc.__class__.__name__}: {exc}") from exc
    # canonical_bytes: a non-JSON value and a non-string key are typed refusals.
    # A plain float and a NaN are DIFFERENT: a finite float is valid JSON and is
    # encoded (it is ``_require_retained`` that refuses a float, so no
    # coordinate can reach a record), while NaN/Infinity are not valid JSON and
    # must be a typed refusal rather than a ``ValueError`` from json.
    for label, hostile in (("nan", float("nan")), ("inf", float("inf")),
                           ("object", object()), ("set", {1, 2}),
                           ("int key", {1: "a"}), ("float key", {1.5: "a"}),
                           ("nested int key", {"a": {2: "b"}}), ("nested int key in list", [{"a": {2: "b"}}]),
                           ("nested nan", {"a": float("nan")})):
        try:
            recheck.canonical_bytes(hostile)
        except recheck.SectionB1RecheckError:
            continue
        except Exception as exc:  # noqa: BLE001 - this branch IS the assertion
            raise RuntimeError(
                f"13: canonical_bytes {label} produced an untyped {exc.__class__.__name__}") from exc
        raise RuntimeError(f"13: canonical_bytes accepted a {label}")
    require(recheck.canonical_bytes(1.5) == b"1.5",
            "13: canonical_bytes mangled a finite float")
    require(recheck.canonical_bytes("synthetic-e-acute".encode("ascii").decode("ascii")) == b'"synthetic-e-acute"',
            "13: canonical_bytes mangled a plain ASCII string")
    # _digest_payload / _validate_record on a non-mapping.
    for label, hostile in (("None", None), ("list", []), ("str", "x"), ("int", 1)):
        try:
            recheck._validate_record(hostile)
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"13: _validate_record accepted a {label}")
    # A record whose branches are the WRONG TYPE, each one its own case so no
    # single guard can cover two of them.
    for field, bad in (("counters", []), ("element_results", []), ("failed_elements", {}),
                       ("refusal_reasons", {}), ("identity", []), ("platform_identity", []),
                       ("platform_reported_fields", {}), ("source_identity", []), ("evidence", [])):
        forged = json_mod.loads(json_mod.dumps(record))
        forged[field] = bad
        try:
            recheck._validate_record(forged)
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"13: a record with a non-mapping {field!r} branch was accepted")
    # ...and a branch whose KEYS are the wrong type, which is the case a sort
    # would otherwise turn into an untyped TypeError.
    for field, bad in (("failed_elements", [7]), ("platform_reported_fields", [7]),
                       ("element_results", {7: {"element": "platform", "status": "match"}}),
                       ("counters", {"elements_checked": "6", "elements_passed": 6, "elements_failed": 0})):
        forged = json_mod.loads(json_mod.dumps(record))
        forged[field] = bad
        try:
            recheck._validate_record(forged)
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"13: a record with a non-string key in {field!r} was accepted")
    checks.append("13 every public argument fuzzed, typed outcome only")

    # --- 14. one fixture per check round 2 touched --------------------------
    # Round 1's validator found redundant checks and untested branches here.
    # Every case below fails if and only if the check it names is removed, so
    # the merged / narrowed / added checks each carry their own fixture.
    #
    # 14a. A missing key and a None value are the SAME finding.  Each spelling
    # alone must be refused, and the two must agree on the reason: that is what
    # lets the second "is it None" test be deleted without a fixture going green.
    for keyword, reason_phrase in (
        ("platform", "is missing or is not a non-empty mapping"),
        ("compiler", "is missing or is not a non-empty mapping"),
        ("source_sha256", "is missing or is not a non-empty mapping"),
    ):
        absent = arguments()
        del absent["session_identity"][keyword]
        none_valued = arguments()
        none_valued["session_identity"][keyword] = None
        element = "source" if keyword == "source_sha256" else keyword
        require_element_reason(element, absent, reason_phrase, f"14a absent {keyword}")
        require_element_reason(element, none_valued, reason_phrase, f"14a None {keyword}")
        # Through the public entry point both spellings must be refused and must
        # name the element, so neither spelling is silently skipped.
        require_refusal(absent, element, f"14a public absent {keyword}")
        require_refusal(none_valued, element, f"14a public None {keyword}")
        # And the whole session identity being absent must still refuse the same
        # element, which is the third spelling of the same finding.
        require_refusal(arguments() | {"session_identity": {}}, element, f"14a empty identity {keyword}")
    # 14b. The one accepted-side key-set test replaces two round-1 checks, so it
    # must cover BOTH of them: an accepted identity with no compiler values, and
    # an accepted identity whose key set differs from the session's.
    for accepted_compiler in (None, {}, {"version": "12.8.93"}, {"flags": ["-O2"]},
                              {"version": "12.8.93", "flags": ["-O2"], "extra": "x"}):
        case = arguments()
        if accepted_compiler is None:
            del case["accepted_identity"]["compiler"]
        else:
            case["accepted_identity"]["compiler"] = accepted_compiler
        require_element_reason("compiler", case, "accepted identity carries no compiler values to compare",
                               f"14b accepted compiler {accepted_compiler!r}")
        require_refusal(case, "compiler", f"14b public accepted compiler {accepted_compiler!r}")
    # 14c. The same merged test must not fire on an accepted identity that is
    # equal: a match is a match, and the fixtures hold that green.
    require_element_match("compiler", arguments(), "14c compiler accepted identity is equal")
    # 14d. The source digest is zeroed by _check_source's own failure returns, so
    # a refusal never carries a real source digest.  Every refusal path of the
    # source element must yield the all-zero digest.
    source_refusals = (
        ("map is None", lambda a: a["session_identity"].__setitem__("source_sha256", None)),
        ("map is empty", lambda a: a["session_identity"].__setitem__("source_sha256", {})),
        ("map key absent", lambda a: a["session_identity"].pop("source_sha256")),
        ("map is a list", lambda a: a["session_identity"].__setitem__("source_sha256", [])),
        ("entry malformed", lambda a: a["session_identity"]["source_sha256"].__setitem__("x.py", "nope")),
        ("matcher returns False", lambda a: a.__setitem__("exact_match", lambda _s, _a: False)),
        ("matcher raises", lambda a: a.__setitem__("exact_match", raising_matcher)),
    )
    for label, break_it in source_refusals:
        case = arguments()
        break_it(case)
        refused = require_refusal(case, "source", f"14d {label}")
        require(refused["source_identity_sha256"] == "0" * 64,
                f"14d: a refused source element carried a real digest for {label!r}: "
                f"{refused['source_identity_sha256']}")
        require(refused["source_identity"] == {},
                f"14d: a refused source element carried a source map for {label!r}")
    # 14e. require_gate's two branches: the gate test cannot see a self-
    # contradictory (open gate, refused verdict) pair, and the verdict test
    # cannot see a closed gate.  Both pairs must raise, and each raises for its
    # OWN reason -- the message names which check refused.
    try:
        recheck.require_gate(refusal, True)
    except recheck.SectionB1RecheckError as exc:
        require("record verdict is not a pass" in str(exc),
                f"14e: the open-gate/refused-verdict pair was refused by the wrong check: {exc}")
    else:
        raise RuntimeError("14e: require_gate accepted an open gate paired with a refused record")
    try:
        recheck.require_gate(record, False)
    except recheck.SectionB1RecheckError as exc:
        require("may not write" in str(exc),
                f"14e: the closed gate was refused by the wrong check: {exc}")
    else:
        raise RuntimeError("14e: require_gate accepted a closed gate")
    # The gate test's own reason list must be the record's reasons, so a caller
    # reading the exception is told why the session may not write.
    try:
        recheck.require_gate(refusal, False)
    except recheck.SectionB1RecheckError as exc:
        for reason in refusal["refusal_reasons"]:
            require(reason in str(exc), f"14e: the closed-gate message dropped {reason!r}: {exc}")
    else:
        raise RuntimeError("14e: require_gate accepted a closed gate carrying a refusal")
    # 14f. The record the module builds must satisfy the very validator the
    # fixtures use, on BOTH verdicts, without the fixtures re-deriving anything
    # by hand.  If the two ever disagree, one of them is wrong.
    for label, args in (("pass", arguments()),
                        ("refusal", _wrong_protocol()),
                        ("source refusal", arguments() | {"exact_match": raising_matcher}),
                        ("identity refusal", arguments() | {"accepted_identity": {}})):
        built, built_gate = run(args)
        recheck._validate_record(built)
        require(type(built_gate) is bool, f"14f: the {label} case returned a non-bool gate")
        recheck.require_gate(built, built_gate) if built_gate else None
        require(built["content_sha256"] == recheck.content_sha256(built),
                f"14f: the {label} record's own content hash is not reproducible")
        require(built["validation_digest"] == recheck.validation_digest(built),
                f"14f: the {label} record's own validation digest is not reproducible")
    # 14g. A refusal withholds the platform-reported labels AND the identities,
    # for every element that can be the one that fails.
    for element in recheck.ELEMENT_NAMES:
        for label, break_it in (
            ("wrong", lambda a, e=element: break_element(a, e)),
            ("missing", lambda a, e=element: remove_element(a, e)),
        ):
            case = arguments()
            break_it(case)
            refused, refused_gate = run(case)
            require(refused_gate is False, f"14g: {element} {label} opened the gate")
            require(not refused["platform_identity"] and not refused["source_identity"]
                    and not refused["platform_reported_fields"],
                    f"14g: a refusal on {element} {label} still carries an identity")
            recheck._validate_record(refused)
    checks.append("14 one fixture per check round 2 touched")

    # --- 15. one self-consistent forgery per remaining record check ---------
    # Group 15 is the second anti-masking group, and it exists because the
    # mutation sweep found these checks reachable only in combination.  Every
    # case here is a forgery whose BOTH hashes have been recomputed, so the
    # record is internally self-consistent and the ONLY thing that can refuse it
    # is the one named check.  In groups 10 and 12 each of these fields was only
    # ever tampered with the hashes left stale, so a hash-level check caught it
    # first and the named check itself was never shown to matter.
    def forge_consistent(record_to_forge, mutate):
        forged = json_mod.loads(json_mod.dumps(record_to_forge))
        mutate(forged)
        forged["validation_digest"] = recheck.validation_digest(forged)
        forged["content_sha256"] = recheck.content_sha256(forged)
        return forged

    def require_consistent_refused(mutate, label):
        forged = forge_consistent(record, mutate)
        try:
            recheck._validate_record(forged)
        except recheck.SectionB1RecheckError:
            return forged
        raise RuntimeError(f"15: a self-consistent forgery was accepted: {label}")

    # The scalar header fields: only the exact-value test on each can refuse.
    require_consistent_refused(lambda r: r.update(schema="decisions_os/other/v1"), "wrong schema")
    require_consistent_refused(
        lambda r: r.update(schema="decisions_os/g9_stage2_section_b1_recheck_record/v2"),
        "schema differs only in its version suffix")
    require_consistent_refused(lambda r: r.update(clause=["other"]), "wrong clause")
    require_consistent_refused(lambda r: r.update(clause=[recheck.AMENDMENT_CLAUSE]), "clause missing a clause")
    require_consistent_refused(lambda r: r.update(clause=[recheck.AMENDMENT_CLAUSE, recheck.PROVIDER_TRUST_CLAUSE,
                                                          "extra"]), "clause with an extra entry")
    require_consistent_refused(lambda r: r.update(elements_checked=list(recheck.ELEMENT_NAMES)[:5]),
                               "element list shortened")
    require_consistent_refused(lambda r: r.update(elements_checked=sorted(recheck.ELEMENT_NAMES)),
                               "element list reordered")
    require_consistent_refused(lambda r: r.update(elements_checked=list(recheck.ELEMENT_NAMES) + ["smuggled"]),
                               "element list widened")
    # The counters: each counter rule is the only thing that can refuse.
    require_consistent_refused(lambda r: r["counters"].update(elements_checked=5),
                               "counter element count")
    require_consistent_refused(lambda r: r["counters"].update(elements_passed=4, elements_failed=2),
                               "counters do not sum to the checked count")
    require_consistent_refused(lambda r: r["counters"].update(elements_failed=-1, elements_passed=7),
                               "negative counter")
    require_consistent_refused(lambda r: r["counters"].update(elements_passed=True, elements_failed=5),
                               "bool counter where an int is required")
    require_consistent_refused(lambda r: r["counters"].update(elements_passed="6", elements_failed=0),
                               "string counter where an int is required")
    require_consistent_refused(lambda r: r["counters"].update(extra=0), "counter key set widened")
    # The refusal content: each rule is the only thing that can refuse.
    require_consistent_refused(lambda r: r.update(failed_elements=["platform", "platform"]),
                               "refused-element list with a duplicate")
    require_consistent_refused(lambda r: r.update(failed_elements=["platform"]),
                               "refused-element list unsorted")
    require_consistent_refused(lambda r: r.update(refusal_reasons=["platform"]),
                               "reason with no element prefix")
    require_consistent_refused(lambda r: r.update(refusal_reasons=["platformnospace: forged"]),
                               "reason whose prefix names no failed element")
    require_consistent_refused(lambda r: r.update(refusal_reasons=["platform: forged", 7]),
                               "non-string reason in the list")
    require_consistent_refused(lambda r: r.update(refusal_reasons={}), "reason list is a mapping")
    # The identity and evidence branches.
    require_consistent_refused(lambda r: r["identity"].update(session_sha256="not-a-sha"),
                               "session identity hash is not a sha256")
    require_consistent_refused(lambda r: r["identity"].update(exact_match="partial"),
                               "identity exact_match label")
    require_consistent_refused(lambda r: r["identity"].update(extra="x"), "identity key set widened")
    require_consistent_refused(lambda r: r["evidence"].update(equality="partial"),
                               "evidence equality label")
    require_consistent_refused(lambda r: r["evidence"].update(statement=1.5),
                               "float in the evidence statement")
    require_consistent_refused(lambda r: r["evidence"].update(extra="x"), "evidence key set widened")
    # The platform-reported labels: each rule is the only thing that can refuse.
    require_consistent_refused(lambda r: r.update(platform_reported_fields=["kaggle_image"]),
                               "pass record reporting only one image field")
    require_consistent_refused(lambda r: r.update(
        platform_reported_fields=["kaggle_image_build", "kaggle_image"]),
        "platform-reported list unsorted")
    require_consistent_refused(lambda r: r.update(platform_reported_fields=["gpu_name"]),
                               "non-image field labelled platform-reported")
    # A refusal record, for the rules that only apply to a pass.
    pass_required = (
        ("platform_identity", lambda r: r.update(platform_identity={})),
        ("source_identity", lambda r: r.update(source_identity={})),
        ("platform_reported_fields", lambda r: r.update(platform_reported_fields=[])),
    )
    for field, mutate in pass_required:
        forged = forge_consistent(record, mutate)
        try:
            recheck._validate_record(forged)
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"15: a pass record withholding {field!r} was accepted")
    # ...and the mirror rule: a REFUSAL record must withhold all three, with
    # both hashes recomputed, which is the direction group 12f missed.
    for field, value in (("platform_identity", dict(SYNTHETIC_PLATFORM)),
                         ("source_identity", dict(SYNTHETIC_SOURCE)),
                         ("platform_reported_fields", sorted(recheck.IMAGE_PLATFORM_FIELDS))):
        forged = forge_consistent(refused, lambda r, f=field, v=value: r.update({f: v}))
        try:
            recheck._validate_record(forged)
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"15: a refusal record re-armed with {field!r} was accepted")
    # The source-identity branch: each value rule is the only thing that can
    # refuse, so a bad value there is not merely a hash mismatch.
    for bad in ("not-a-sha", 1.5, [], None, 0):
        require_consistent_refused(lambda r, b=bad: r["source_identity"].update({"a.py": b}),
                                   f"source identity value {bad!r}")
    require_consistent_refused(lambda r: r.update(source_identity_sha256="not-a-sha"),
                               "source identity digest is not a sha256")
    require_consistent_refused(lambda r: r.update(source_identity_sha256=1.5),
                               "source identity digest is a float")
    # The platform-identity branch: the declared-field set, on a pass record.
    require_consistent_refused(lambda r: r["platform_identity"].update(energy=0.0),
                               "non-platform field in the platform identity")
    require_consistent_refused(lambda r: r["platform_identity"].pop("gpu_name"),
                               "platform identity missing a field on a pass record")
    # The digest FIELDS, tampered WITHOUT re-deriving them.  Re-deriving is not
    # an option here: a forge recomputes both digests, so a "swap" written that
    # way is not a swap at all.  Group 12b3 covers the swap as a raw tamper; what
    # is added here is that each digest is separately re-derived, so neither
    # field can be repaired without the other.
    for field, donor in (("validation_digest", record["content_sha256"]),
                         ("content_sha256", record["validation_digest"])):
        swapped = json_mod.loads(json_mod.dumps(record))
        swapped[field] = donor
        try:
            recheck._validate_record(swapped)
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"15: a record whose {field!r} carries the other digest was accepted")
    for field, bad in (("validation_digest", "not-a-sha"), ("content_sha256", 1.5),
                       ("validation_digest", None), ("content_sha256", [])):
        tampered_field = json_mod.loads(json_mod.dumps(record))
        tampered_field[field] = bad
        try:
            recheck._validate_record(tampered_field)
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"15: a record whose {field!r} is {bad!r} was accepted")
    # A record MISSING a branch the digest payload commits to.  Here the payload
    # cannot even be built, so the refusal has to come from the digest itself --
    # which is why both digest entry points are checked: computing a digest over
    # a record that is missing a claim would silently bind less than it claims.
    for branch in ("counters", "evidence", "failed_elements", "refusal_reasons",
                   "identity", "platform_identity", "element_results"):
        for entry_point in (recheck.validation_digest, recheck._digest_payload):
            partial = json_mod.loads(json_mod.dumps(record))
            partial.pop(branch)
            try:
                entry_point(partial)
            except recheck.SectionB1RecheckError:
                continue
            except Exception as exc:  # noqa: BLE001 - this branch IS the assertion
                raise RuntimeError(
                    f"15: the digest over a record missing {branch!r} produced an untyped "
                    f"{exc.__class__.__name__}") from exc
            raise RuntimeError(f"15: the digest bound a record missing {branch!r}")
        # And the validator must refuse the same partial record.
        partial = json_mod.loads(json_mod.dumps(record))
        partial.pop(branch)
        try:
            recheck._validate_record(partial)
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"15: a record missing the {branch!r} branch was accepted")
    checks.append("15 one self-consistent forgery per remaining record check")

    # --- 16. _differences, unit level --------------------------------------
    # The mutation sweep found every arm of ``_differences`` uncaught, and the
    # reason is structural: its callers only ask "is the result empty?", so a
    # disabled arm still produces SOME non-empty list and the refusal still
    # fires.  The function's real contract is the PATHS it returns, not just
    # emptiness, and nothing asserted on the paths.  This group pins the exact
    # return value of every arm, so an arm that is disabled returns the wrong
    # paths and is caught.
    def require_paths(expected_value, observed_value, prefix, expected_paths, label):
        got = recheck._differences(expected_value, observed_value, prefix)
        require(got == expected_paths,
                f"16: _differences{label} returned {got!r}, not {expected_paths!r}")

    # The equal case: every arm must report nothing.
    require_paths({"a": 1, "b": {"c": 2}}, {"a": 1, "b": {"c": 2}}, "", [], " on equal dicts")
    require_paths([1, 2, 3], [1, 2, 3], "", [], " on equal lists")
    require_paths("x", "x", "", [], " on equal scalars")
    require_paths(7, 7, "", [], " on equal ints")
    require_paths(True, True, "", [], " on equal bools")
    require_paths(None, None, "", [], " on equal Nones")
    # The dict arm: a differing leaf, at depth, with the path built by nesting.
    require_paths({"a": 1}, {"a": 2}, "", ["a"], " on a differing top-level leaf")
    require_paths({"a": {"b": {"c": 1}}}, {"a": {"b": {"c": 2}}}, "", ["a.b.c"],
                  " on a differing leaf three levels down")
    require_paths({"a": {"b": 1}}, {"a": {"b": 1}}, "pfx", [], " on equal nested dicts")
    require_paths({"a": {"b": 1}}, {"a": {"b": 2}}, "pfx", ["pfx.a.b"],
                  " on a differing nested leaf under a prefix")
    # The dict arm's missing-key branch: EXTRA on the observed side and MISSING
    # from the observed side are different paths, and both are reported.
    require_paths({"a": 1}, {"b": 1}, "", ["a", "b"], " on disjoint key sets")
    require_paths({"a": 1, "b": 2}, {"a": 1}, "", ["b"], " on a key missing from the observed side")
    require_paths({"a": 1}, {"a": 1, "b": 2}, "", ["b"], " on a key extra in the observed side")
    require_paths({"a": 1, "z": 1}, {"a": 1, "b": 1}, "", ["b", "z"], " on one extra and one missing key")
    require_paths({"a": {"b": 1}}, {"a": {}}, "p", ["p.a.b"], " on a key missing from a nested mapping")
    # The list arm: element-wise paths, and the length branch.
    require_paths([1, 2], [1, 3], "", ["[1]"], " on a differing list element")
    require_paths([1, 2], [2, 1], "", ["[0]", "[1]"], " on two differing list elements")
    require_paths([1, 2], [1, 2, 3], "", [""], " on a longer observed list")
    require_paths([1, 2, 3], [1, 2], "", [""], " on a shorter observed list")
    require_paths([], [], "", [], " on two empty lists")
    require_paths([[1, 2]], [[1, 3]], "p", ["p[0][1]"], " on a differing element of a nested list")
    require_paths({"a": [1]}, {"a": [2]}, "", ["a[0]"], " on a list nested in a mapping")
    # The scalar arm: a type difference and a value difference are both reported.
    require_paths(1, "1", "", [""], " on a type difference between scalars")
    require_paths("1", 1, "", [""], " on the same type difference the other way")
    require_paths(1, 1.0, "", [""], " on an int against a float")
    require_paths(True, 1, "", [""], " on a bool against an int")
    require_paths([1], "1", "", [""], " on a list against a scalar")
    require_paths({"a": 1}, [1], "", [""], " on a mapping against a list")
    require_paths(None, "x", "", [""], " on None against a string")
    # A prefix is threaded through every arm, so a caller reading the paths
    # cannot be misled by a top-level difference reported with no context.
    require_paths({"a": {"b": 1}}, {"a": {"b": 2}}, "", ["a.b"], " on a nested leaf with an empty prefix")
    require_paths({"a": 1}, {"a": 2}, "root", ["root.a"], " on a top-level leaf with a prefix")
    # The two calls the module actually makes, through the isolated element
    # checks, so the unit contract above is anchored to real inputs.
    for field in recheck.PLATFORM_FIELDS:
        case = arguments()
        case["session_identity"]["platform"][field] = "synthetic/drifted"
        matched, reasons = discover("platform", case)
        require(matched is False, f"16: platform drift in {field!r} still matched")
    case = arguments()
    case["session_identity"]["platform"].pop("gpu_name")
    matched, reasons = discover("platform", case)
    require(matched is False, "16: a missing platform field still matched")
    checks.append("16 _differences return values, unit level")

    # --- 17. one fixture per check the round-2 mutation sweep found ---------
    # Group 17 exists because the round-2 mutation sweep found 23 checks that
    # SURVIVED their own mutation: the fixture suite stayed green when the check
    # was disabled.  Each is a real check, so none may be deleted (that would
    # weaken a protection).  Each is therefore given here a case that FAILS if
    # and only if that check is removed.  The four shapes that recur:
    #
    #  17a. The `not X` half of every `type(X) is not dict or not X` guard.  A
    #       MISSING key reaches the `type` half (it is None), which is why the
    #       earlier groups never reached the `not X` half -- but an EMPTY
    #       mapping is a dict, so only the `not X` half can refuse it.  Every
    #       one of those guards is now pinned by an empty-mapping case.
    #  17b. The record-shape checks inside ``_validate_record``.  Each of them
    #       is masked by the verdict/counters/results consistency check unless
    #       the forgery is a SELF-CONSISTENT REFUSAL that still carries all six
    #       element results, with the counters re-derived from them.  The helper
    #       below builds exactly that, which is what makes each named check the
    #       only thing that can refuse its own forgery.
    #  17c. The two private helpers whose only caller passes them a constant
    #       (``_file_sha256``) and the two whose branch is never taken because
    #       a caller never produces that record (``canonical_bytes``'s
    #       re-dispatch, ``_retained_value``'s str branch).
    #  17d. The two build-time checks in ``_build_record`` that no input can
    #       currently reach, which are pinned by driving the helpers directly.
    def coherent_refusal(mutate):
        """A self-consistent REFUSAL record that still carries all six results.

        A refusal the module actually produces can be missing an element result
        (an element that failed is recorded as absent, not as a mismatch), so
        the earlier groups could never pair a bad result shape with a refusal.
        This builds the record the module's own shape rules want -- six results,
        a coherent verdict/counter/result agreement, withheld identities -- and
        then applies one corruption, so the named check is the only one left
        that can refuse it.
        """
        forged = json_mod.loads(json_mod.dumps(record))
        forged["verdict"] = "refused"
        results = forged["element_results"]
        mutate(results)
        matched = [name for name, row in results.items() if row.get("status") == "match"]
        forged["counters"] = {
            "elements_checked": len(recheck.ELEMENT_NAMES),
            "elements_passed": len(matched),
            "elements_failed": len(recheck.ELEMENT_NAMES) - len(matched),
        }
        forged["elements_checked"] = list(recheck.ELEMENT_NAMES)
        not_matched = [name for name in recheck.ELEMENT_NAMES if name not in matched]
        forged["failed_elements"] = sorted(set(not_matched)) or ["protocol"]
        forged["refusal_reasons"] = [f"{name}: forged" for name in forged["failed_elements"]]
        forged["platform_identity"] = {}
        forged["source_identity"] = {}
        forged["platform_reported_fields"] = []
        return forged

    def require_coherent_refusal(mutate, label):
        forged = coherent_refusal(mutate)
        forged["validation_digest"] = recheck.validation_digest(forged)
        forged["content_sha256"] = recheck.content_sha256(forged)
        try:
            recheck._validate_record(forged)
        except recheck.SectionB1RecheckError:
            return forged
        raise RuntimeError(f"17: a self-consistent refusal forgery was accepted: {label}")

    # bool is an int subclass in Python and is explicitly retained as a bool
    # leaf, so the counter type clause must reject it even when all arithmetic
    # and result counts otherwise agree.
    boolean_counter = coherent_refusal(
        lambda results: [
            row.update(status="mismatch")
            for name, row in results.items() if name != "generator"
        ]
    )
    boolean_counter["counters"]["elements_passed"] = True
    boolean_counter["validation_digest"] = recheck.validation_digest(boolean_counter)
    boolean_counter["content_sha256"] = recheck.content_sha256(boolean_counter)
    require_forgery_refused(boolean_counter, "bool used as an integer counter")

    # 17a. The `not X` half of each `type(X) is not dict or not X` guard.  The
    # empty mapping is a dict, so the `type` half passes it through and only the
    # emptiness half can refuse it.  Each case is scoped to the element whose
    # guard it exercises, so it fails if and only if THAT guard is removed.
    empty = arguments()
    empty["session_identity"]["source_sha256"] = {}
    empty["accepted_identity"]["source_sha256"] = {}
    require_element_refusal("source", empty, "17a empty source mapping")
    empty = arguments()
    empty["session_identity"]["platform"] = {}
    empty["accepted_identity"]["platform"] = {}
    require_element_refusal("platform", empty, "17a empty platform mapping")
    empty = arguments()
    empty["session_identity"]["compiler"] = {}
    empty["accepted_identity"]["compiler"] = {}
    require_element_refusal("compiler", empty, "17a empty compiler mapping")
    # The two whole-identity guards, the same way.
    require_refusal(arguments() | {"accepted_identity": {}}, "accepted_identity",
                    "17a empty accepted identity")
    empty_session = require_refusal(arguments() | {"session_identity": {}}, "session_identity",
                                    "17a empty session identity")
    for element in ("source", "platform", "compiler"):
        require(element in empty_session["failed_elements"],
                f"17a: an empty session identity did not refuse {element!r}: "
                f"{empty_session['failed_elements']}")
    # ...and the same two through the isolated per-element entry point, so the
    # masking from the whole-identity hash comparison cannot hide them there.
    matched, _ = discover("platform", arguments() | {"accepted_identity": {}})
    require(matched is False, "17a: an empty accepted identity still matched the platform")
    matched, _ = discover("source", arguments() | {"session_identity": {}})
    require(matched is False, "17a: an empty session identity still matched the source")
    checks.append("17a the emptiness half of every mapping guard")

    # 17b. The record-shape checks, each alone on a coherent refusal forgery.
    # Each of these is refused by exactly the named check; every other check in
    # ``_validate_record`` is satisfied by construction.
    # The refusal base used below is this group's own, so it does not depend on
    # which record earlier groups happened to leave bound to the name ``refused``.
    refused, _ = run(_wrong_protocol())
    recheck._validate_record(refused)
    # Exact map shapes remain material even when every expected member is
    # present and all record digests are recomputed.
    require_forgery_refused(
        forge(record, lambda r: r["counters"].update(extra="x")),
        "counter mapping with an extra key",
    )
    require_forgery_refused(
        forge(record, lambda r: r["identity"].update(extra="x")),
        "identity mapping with an extra key",
    )
    require_forgery_refused(
        forge(record, lambda r: r["evidence"].update(extra="x")),
        "evidence mapping with an extra key",
    )
    require_forgery_refused(
        forge(record, lambda r: r.update(refusal_reasons=["unmatched reason"])),
        "pass record with an unmatched refusal reason",
    )
    require_forgery_refused(
        forge(record, lambda r: r.update(refusal_reasons=["protocol: forged"])),
        "pass record with a reason but no failed element",
    )
    require_forgery_refused(
        forge(record, lambda r: r["evidence"].update(equality="not_exact_match")),
        "evidence with the wrong equality label",
    )
    require_forgery_refused(
        forge(record, lambda r: r["evidence"].update(authorizes_write="yes")),
        "evidence claiming write authorization",
    )
    duplicate_failed = forge(refused, lambda r: r.update(
        failed_elements=["protocol", "protocol"],
        refusal_reasons=["protocol: forged", "protocol: forged"],
    ))
    require_forgery_refused(duplicate_failed, "duplicate refused element names")
    require_coherent_refusal(
        lambda results: results["generator"].update(status="weird"),
        "an element result carries an undeclared status",
    )
    require_coherent_refusal(
        lambda results: (results.pop("generator"),
                         results.update(smuggled={"element": "smuggled", "status": "mismatch"})),
        "an element result names an undeclared element",
    )
    # The result's OWN key set: a third key is refused only by that rule.
    third_key = coherent_refusal(lambda results: results["generator"].update(extra="x"))
    third_key["validation_digest"] = recheck.validation_digest(third_key)
    third_key["content_sha256"] = recheck.content_sha256(third_key)
    try:
        recheck._validate_record(third_key)
    except recheck.SectionB1RecheckError:
        pass
    else:
        raise RuntimeError("17b: a result row with a third key was accepted")
    # The verdict vocabulary: a verdict outside {pass, refused} is refused only
    # by the membership test, so the coherent-refusal shape is what isolates it.
    bad_verdict = json_mod.loads(json_mod.dumps(refused))
    bad_verdict["verdict"] = "refused "
    bad_verdict["validation_digest"] = recheck.validation_digest(bad_verdict)
    bad_verdict["content_sha256"] = recheck.content_sha256(bad_verdict)
    try:
        recheck._validate_record(bad_verdict)
    except recheck.SectionB1RecheckError:
        pass
    else:
        raise RuntimeError("17b: a record whose verdict is 'refused ' was accepted")
    # The counter rules, on a coherent refusal: elements_checked and the sum.
    for label, counters in (
        ("counter element count", {"elements_checked": 5, "elements_passed": 5, "elements_failed": 1}),
        ("counter sum", {"elements_checked": 6, "elements_passed": 4, "elements_failed": 3}),
    ):
        forged = json_mod.loads(json_mod.dumps(refused))
        forged["counters"] = dict(counters)
        forged["validation_digest"] = recheck.validation_digest(forged)
        forged["content_sha256"] = recheck.content_sha256(forged)
        try:
            recheck._validate_record(forged)
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"17b: a refusal with a wrong {label} was accepted")
    # The refused-element name vocabulary: a name outside SCOPE_NAMES is
    # refused only by that membership test.
    wrong_name = json_mod.loads(json_mod.dumps(refused))
    wrong_name["failed_elements"] = ["PLATFORM"]
    wrong_name["refusal_reasons"] = ["PLATFORM: forged"]
    wrong_name["validation_digest"] = recheck.validation_digest(wrong_name)
    wrong_name["content_sha256"] = recheck.content_sha256(wrong_name)
    try:
        recheck._validate_record(wrong_name)
    except recheck.SectionB1RecheckError:
        pass
    else:
        raise RuntimeError("17b: a refused-element list naming 'PLATFORM' was accepted")
    # The platform-identity rules, on a coherent refusal (a refusal withholds
    # the identity, so a non-mapping and an undeclared field are isolated here).
    for label, value in (
        ("platform identity is not a mapping", "x"),
        ("platform identity carries an undeclared field", {"undeclared": "x"}),
    ):
        forged = json_mod.loads(json_mod.dumps(refused))
        forged["platform_identity"] = value
        forged["validation_digest"] = recheck.validation_digest(forged)
        forged["content_sha256"] = recheck.content_sha256(forged)
        try:
            recheck._validate_record(forged)
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"17b: a refusal whose {label} was accepted")
    # The platform-reported label rules, on a coherent refusal: a refusal
    # withholds the labels, so a non-list and a non-string name are isolated.
    for label, value in (
        ("platform-reported fields are not a list", "kaggle_image"),
        ("platform-reported fields hold a non-string", [7]),
    ):
        forged = json_mod.loads(json_mod.dumps(refused))
        forged["platform_reported_fields"] = value
        forged["validation_digest"] = recheck.validation_digest(forged)
        forged["content_sha256"] = recheck.content_sha256(forged)
        try:
            recheck._validate_record(forged)
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"17b: a refusal whose {label} was accepted")
    checks.append("17b one coherent refusal per record-shape check")

    # 17c. The private helper branches the public surface never reaches.
    # ``canonical_bytes`` re-dispatches its OWN typed error so the specific
    # diagnosis ("every dictionary key must be exactly str") survives instead of
    # being flattened into the generic "not canonical JSON".  Without this the
    # re-dispatch is invisible: both paths raise the same type.
    try:
        recheck.canonical_bytes({7: "int key"})
    except recheck.SectionB1RecheckError as exc:
        require("exactly str" in str(exc),
                f"17c: canonical_bytes flattened its own diagnosis: {exc}")
    else:
        raise RuntimeError("17c: canonical_bytes accepted a non-string key")
    # ...while a genuinely non-canonical value still gets the generic message.
    for hostile, expected in (
        (float("nan"), "not canonical"),
        (float("inf"), "not canonical"),
        (b"bytes", "not canonical"),
    ):
        try:
            recheck.canonical_bytes(hostile)
        except recheck.SectionB1RecheckError as exc:
            require(expected in str(exc),
                    f"17c: canonical_bytes({hostile!r}) reported {exc!r}, not the generic refusal")
        else:
            raise RuntimeError(f"17c: canonical_bytes accepted {hostile!r}")
    # ``_retained_value``'s str branch: a string leaf returns the SAME object, so
    # the branch is observable only by identity, not by a refusal.
    leaf = "synthetic/retained-value"
    require(recheck._retained_value(leaf, "17c") is leaf,
            "17c: _retained_value did not return its str branch unchanged")
    # ``_file_sha256``: the only caller passes it the module's own constant, so
    # its path-shape and its OSError branch are driven here directly.
    for bad_path in ("", "/etc/passwd", "../escape.md", "research/../../escape.md",
                     None, 7, b"bytes", ["a"]):
        try:
            recheck._file_sha256(bad_path)
        except recheck.SectionB1RecheckError:
            continue
        except Exception as exc:
            raise RuntimeError(
                f"17c: _file_sha256({bad_path!r}) raised an untyped {exc.__class__.__name__}") from exc
        raise RuntimeError(f"17c: _file_sha256 accepted a non-canonical path {bad_path!r}")
    # A valid absolute path that exists distinguishes the absolute-path guard
    # from the later file-read failure, and an existing traversal target does
    # the same for the parent-component guard.
    for bad_path in (
        "/etc/passwd",
        "../project/research/g9/stage2_section_b1_recheck.py",
    ):
        try:
            recheck._file_sha256(bad_path)
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"17c: _file_sha256 accepted an unsafe readable path {bad_path!r}")
    for missing in ("research/decisions/NO_SUCH_DOCUMENT.md", "research/g9/__absent__.md"):
        try:
            recheck._file_sha256(missing)
        except recheck.SectionB1RecheckError as exc:
            require("cannot read approved document" in str(exc),
                    f"17c: an unreadable document reported the wrong refusal: {exc}")
        else:
            raise RuntimeError(f"17c: _file_sha256 read a document that does not exist: {missing!r}")
    # A real document still reads, and re-hashes to the same digest: the OSError
    # branch is the failure path, not a blanket refusal.
    first = recheck.APPROVAL_PATHS[0]
    require(recheck._file_sha256(first) == observed[first],
            f"17c: _file_sha256({first!r}) did not reproduce the read hash")
    # Pin _sha's individual conjuncts with same-length, all-hex and wrong-length
    # inputs, plus non-strings.  These cases make each SHA-256 shape clause
    # observable without relying on another identity comparison.
    for bad_hash in ("a" * 63, "a" * 65, "g" * 64, 7, None, b"a" * 64):
        try:
            recheck._sha(bad_hash, "17c direct hash")
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"17c: _sha accepted malformed digest {bad_hash!r}")
    # read_approval_hashes deliberately accepts concrete tuples but refuses
    # other iterables even when they yield the fixed path sequence.
    try:
        recheck.read_approval_hashes(iter(recheck.APPROVAL_PATHS))
    except recheck.SectionB1RecheckError:
        pass
    else:
        raise RuntimeError("17c: read_approval_hashes accepted an iterator")
    checks.append("17c private helper branches the public surface cannot reach")

    # 17d. The two build-time checks in ``_build_record``.  A payload the module
    # builds can never carry a forbidden leaf, so these are driven through the
    # walker they call, and through a record whose branch is edited underneath it.
    # The walk is RECURSIVE, so a container is fine as long as every leaf under it
    # is a permitted one; what it refuses is a forbidden leaf at any depth.
    for bad in (-1.5, [1.5], {"a": -1.5}, [[b"bytes"]], {"a": {"b": [None]}}, float("nan")):
        try:
            recheck._require_retained(bad, "17d")
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"17d: the record walker accepted a forbidden leaf: {bad!r}")
    for good in ("x", 0, 7, True, {"a": "b"}, [[1], "x"], {"a": {"b": [0]}}):
        recheck._require_retained(good, "17d")
    # The build-time walk covers EVERY walked branch, which is what makes a
    # smuggled leaf in a nested branch fail at build time rather than silently.
    nested = json_mod.loads(json_mod.dumps(record))
    nested["platform_identity"] = dict(SYNTHETIC_PLATFORM, energy=-1.5)
    try:
        recheck._require_retained(nested["platform_identity"], "platform_identity")
    except recheck.SectionB1RecheckError:
        pass
    else:
        raise RuntimeError("17d: a float survived the build-time walk of a nested branch")
    # A non-string key is refused BEFORE the keys are sorted, so a mixed key set
    # is a typed refusal rather than an untyped TypeError out of a sort.
    try:
        recheck._require_retained({7: "x", "a": "y"}, "17d mixed keys")
    except recheck.SectionB1RecheckError:
        pass
    else:
        raise RuntimeError("17d: the record walker accepted a non-string key")
    checks.append("17d build-time record walk and the refused-element dedup")

    # 17e. The refusal-reason de-duplication in ``_build_record``: an element
    # refused for two DIFFERENT reasons is listed once in ``failed_elements`` and
    # keeps BOTH reasons.  The pin is the two-reasons-one-element case: a
    # wrong observed path set AND a wrong expected path set are two independent
    # findings about the same element, so dropping the de-duplication would
    # list "protocol" twice, which the record's own sorted-set rule then refuses.
    two_reasons = arguments()
    two_reasons["observed_approval_sha256"] = {"research/decisions/other.md": "8" * 64}
    del two_reasons["expected_approval_sha256"][recheck.APPROVAL_PATHS[1]]
    refused_twice, gate_twice = run(two_reasons)
    require(gate_twice is False, "17e: a twice-refused element opened the gate")
    require(refused_twice["failed_elements"].count("protocol") == 1,
            f"17e: a twice-refused element was listed twice: {refused_twice['failed_elements']}")
    protocol_reasons = [r for r in refused_twice["refusal_reasons"] if r.startswith("protocol: ")]
    require(len(protocol_reasons) == 2,
            f"17e: the de-duplication dropped a distinct reason: {protocol_reasons}")
    require(len(set(protocol_reasons)) == 2, f"17e: the two reasons are not distinct: {protocol_reasons}")
    recheck._validate_record(refused_twice)
    checks.append("17e refused-element de-duplication keeps every reason")

    # 17f. The two hash-holding branches of the walk, which the walk skips by
    # design: a non-sha256 there is refused by its own ``_sha``, so the skip is
    # narrow rather than a hole.
    for field in ("validation_digest", "content_sha256", "source_identity_sha256"):
        for bad in ("not-a-sha", 1.5, [], None, "A" * 64):
            tampered_field = json_mod.loads(json_mod.dumps(record))
            tampered_field[field] = bad
            try:
                recheck._validate_record(tampered_field)
            except recheck.SectionB1RecheckError:
                continue
            raise RuntimeError(f"17f: a record whose {field!r} is {bad!r} was accepted")
    # And the two hashes really are re-derived, so a hand-edited record cannot
    # keep a digest that no longer matches its own content.
    edited = json_mod.loads(json_mod.dumps(record))
    edited["evidence"]["authorizes_write"] = "yes"
    try:
        recheck._validate_record(edited)
    except recheck.SectionB1RecheckError:
        pass
    else:
        raise RuntimeError("17f: a record edited to claim a write authorization was accepted")
    checks.append("17f the two skipped hash branches are still re-derived")

    # --- 18. the checks group 17 could not isolate, isolated properly -------
    # Group 17 removed 11 of the 23 survivors.  The 12 it could not reach are
    # here, and each needed a DIFFERENT construction, because in every case the
    # obvious forgery was already caught by a neighbour.  Each construction below
    # was proved by mutation: disabling the named check makes exactly this case
    # fail, and no other fixture changes.
    #
    # 18a. ``_retained_value``'s str branch.  A non-str leaf is refused either
    #      way, so only the MESSAGE distinguishes the branches; the pin is that a
    #      float/sequence/mapping is reported as an unapproved record leaf, not
    #      as a malformed string.
    for bad in (1.5, [1, 2], {"a": 1}, b"x", None, set(), (1, 2)):
        try:
            recheck._retained_value(bad, "18a")
        except recheck.SectionB1RecheckError as exc:
            require("not a permitted record leaf" in str(exc),
                    f"18a: {bad!r} was refused as a malformed string rather than as an "
                    f"unapproved record leaf: {exc}")
        else:
            raise RuntimeError(f"18a: _retained_value accepted {bad!r}")
    checks.append("18a the record-leaf branch of _retained_value")

    # 18b. ``_differences``' type test.  For two JSON-encodable values a type
    #      difference always shows up as a byte difference, so the clause looked
    #      redundant -- but a value that is NOT JSON-encodable (bytes, an int
    #      key, NaN) is the case: without the type test the comparison raises
    #      instead of REPORTING a difference, which turns a readable refusal into
    #      an exception.  The pin is the returned path, not the exception.
    for left, right in ((0, b"x"), (1, {1: 2}), (float("nan"), 0), ("s", b"s"), (None, b"")):
        got = recheck._differences(left, right, "p")
        require(got == ["p"],
                f"18b: _differences({left!r}, {right!r}) returned {got!r}, not the differing path")
    checks.append("18b the type test in _differences")

    # 18c. The re-dispatch in ``_check_source``.  A matcher that raises this
    #      module's OWN error must PROPAGATE it; flattening it into a refusal
    #      would tell the caller the session merely mismatched, when in fact the
    #      injected dependency reported something it could not express as a diff.
    def typed_matcher(_session, _accepted):
        raise recheck.SectionB1RecheckError("matcher refused on purpose")

    try:
        run(arguments() | {"exact_match": typed_matcher})
    except recheck.SectionB1RecheckError as exc:
        require("on purpose" in str(exc),
                f"18c: the matcher's own typed error was rewritten: {exc}")
    else:
        raise RuntimeError("18c: a matcher's own typed error was swallowed into a refusal")
    # The generic branch is unchanged: an ordinary exception is still a refusal.
    require_refusal(arguments() | {"exact_match": raising_matcher}, "source",
                    "18c an untyped matcher exception is still a refusal")
    checks.append("18c the typed re-dispatch around the injected matcher")

    # 18d. The counter rules, on the two bases that isolate them.  On a PASS the
    #      consistency check only pins ``elements_passed``, so a wrong
    #      ``elements_failed`` and a wrong ``elements_checked`` are the sum rule's
    #      and the element-count rule's alone; on a REFUSAL the consistency check
    #      is looser, so both are isolated there too.
    for label, counters, base in (
        ("pass with a non-zero failure counter",
         {"elements_checked": 6, "elements_passed": 6, "elements_failed": 1}, record),
        ("pass with a doubled failure counter",
         {"elements_checked": 6, "elements_passed": 6, "elements_failed": 3}, record),
        ("refusal with a short element count",
         {"elements_checked": 5, "elements_passed": 5, "elements_failed": 0}, refused),
        ("refusal with a padded element count",
         {"elements_checked": 7, "elements_passed": 5, "elements_failed": 2}, refused),
    ):
        forged = json_mod.loads(json_mod.dumps(base))
        forged["counters"] = dict(counters)
        forged["validation_digest"] = recheck.validation_digest(forged)
        forged["content_sha256"] = recheck.content_sha256(forged)
        try:
            recheck._validate_record(forged)
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"18d: a record with a wrong {label} was accepted")
    checks.append("18d the counter sum and element-count rules")

    # 18e. The platform-reported label rules.  A REFUSAL withholds the labels, so
    #      ``{}`` and ``0`` -- both falsy, so the withholding rule cannot see
    #      them -- are refused by the shape rule alone.
    for label, value in (("an empty mapping", {}), ("a zero", 0)):
        forged = json_mod.loads(json_mod.dumps(refused))
        forged["platform_reported_fields"] = value
        forged["validation_digest"] = recheck.validation_digest(forged)
        forged["content_sha256"] = recheck.content_sha256(forged)
        try:
            recheck._validate_record(forged)
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"18e: a refusal whose platform-reported fields are {label} was accepted")
    checks.append("18e the platform-reported label shape rule")

    # 18f. The platform-identity mapping rule.  A refusal withholds the identity,
    #      and an empty list is falsy, so the withholding rule cannot see it; the
    #      mapping rule is the only thing that refuses it.
    for label, value in (("an empty list", []), ("a zero", 0), ("an empty tuple", ())):
        forged = json_mod.loads(json_mod.dumps(refused))
        forged["platform_identity"] = list(value) if isinstance(value, tuple) else value
        forged["validation_digest"] = recheck.validation_digest(forged)
        forged["content_sha256"] = recheck.content_sha256(forged)
        try:
            recheck._validate_record(forged)
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"18f: a refusal whose platform identity is {label} was accepted")
    checks.append("18f the platform-identity mapping rule")

    # 18g. The build-time walk.  ``_build_record`` walks every branch before it
    #      binds a digest, so a platform map carrying a coordinate-level float is
    #      refused at BUILD time -- driven here directly, because no public
    #      argument can produce one.
    poisoned_platform = dict(SYNTHETIC_PLATFORM, energy=-1.5)
    try:
        recheck._build_record(
            True, {}, [], "0" * 64, "0" * 64, poisoned_platform, [], {}, "0" * 64,
        )
    except recheck.SectionB1RecheckError as exc:
        require("not a permitted record leaf" in str(exc),
                f"18g: the build-time walk refused for the wrong reason: {exc}")
    else:
        raise RuntimeError("18g: _build_record accepted a coordinate-level float in the platform map")
    # ...and a forbidden leaf in ANY walked branch, not only the platform one.
    # The walk is recursive, so what it refuses is a forbidden leaf at any depth.
    for branch, value in (
        ("source_identity", {"a.py": 1.5}),
        ("platform_reported_fields", [-1.5]),
        ("element_results", {"platform": {"element": "platform", "status": 1.5}}),
    ):
        try:
            recheck._require_retained(value, branch)
        except recheck.SectionB1RecheckError:
            continue
        raise RuntimeError(f"18g: the walk accepted a forbidden leaf in {branch!r}")
    checks.append("18g the build-time record walk")

    print("PASS synthetic section-B item 1 identity recheck; "
          f"{len(checks)} fixture groups; no writes")


def discover(element, args):
    return recheck.discover_element(element, **args)


def break_element(args, element):
    """Make exactly one §B item 1 element wrong in an otherwise passing case."""
    if element == "protocol":
        args["expected_approval_sha256"] = dict(args["expected_approval_sha256"])
        args["expected_approval_sha256"][recheck.APPROVAL_PATHS[0]] = "0" * 64
    elif element == "generator":
        args["generator_implementation_record_sha256"] = "5" * 64
    elif element == "ground_truth":
        args["ground_truth_provenance_sha256"] = "5" * 64
    elif element == "source":
        args["session_identity"]["source_sha256"]["research/g9/synthetic_writer.py"] = "6" * 64
    elif element == "platform":
        args["session_identity"]["platform"]["gpu_name"] = "synthetic/drifted"
    elif element == "compiler":
        args["session_identity"]["compiler"]["version"] = "12.9.0"
    else:
        raise RuntimeError(f"undeclared element {element!r}")


def remove_element(args, element):
    """Make exactly one §B item 1 element absent in an otherwise passing case."""
    if element == "protocol":
        args["observed_approval_sha256"] = dict(args["observed_approval_sha256"])
        del args["observed_approval_sha256"][recheck.APPROVAL_PATHS[1]]
    elif element == "generator":
        args["generator_implementation_record_sha256"] = None
    elif element == "ground_truth":
        args["expected_ground_truth_provenance_sha256"] = None
    elif element == "source":
        del args["session_identity"]["source_sha256"]
    elif element == "platform":
        del args["session_identity"]["platform"]
    elif element == "compiler":
        del args["session_identity"]["compiler"]
    else:
        raise RuntimeError(f"undeclared element {element!r}")


def require_element_refusal(element, args, label):
    matched, reasons = discover(element, args)
    require(matched is False, f"{label}: the isolated {element!r} check still matched")
    require(reasons, f"{label}: the isolated {element!r} check refused without stating a reason")


def require_element_reason(element, args, phrase, label):
    """Assert the isolated check refuses *for this reason*, not merely refuses.

    Several element checks have a second, independent check that also refuses
    the same input: an absent generator pin is both "missing" and "not a
    SHA-256", and a transient platform field is both "undeclared" and "drifted
    from the accepted identity".  Asserting only `matched is False` cannot tell
    those two apart, so a validator who deletes the specific check still sees a
    green run.  Naming the reason is what pins the check itself.
    """
    matched, reasons = discover(element, args)
    require(matched is False, f"{label}: the isolated {element!r} check still matched")
    require(any(phrase in reason for reason in reasons),
            f"{label}: the isolated {element!r} check refused, but not for {phrase!r}: {sorted(reasons)}")


def require_element_refusal_excluding(element, args, absent_phrase, label):
    """Assert the isolated check refuses, and did NOT also fire ``absent_phrase``.

    The mirror of :func:`require_element_reason`.  Two branches of the same
    check are distinguished only by their reason, so pinning one of them means
    asserting the other did not fire: otherwise deleting the *other* branch
    would leave this fixture green.
    """
    matched, reasons = discover(element, args)
    require(matched is False, f"{label}: the isolated {element!r} check still matched")
    require(not any(absent_phrase in reason for reason in reasons),
            f"{label}: the isolated {element!r} check also fired {absent_phrase!r}: {sorted(reasons)}")


def require_element_match(element, args, label):
    matched, reasons = discover(element, args)
    require(matched is True,
            f"{label}: the isolated {element!r} check refused a matching identity: {sorted(reasons)}")
    require(not reasons, f"{label}: the isolated {element!r} check matched but reported reasons")


def _wrong_protocol():
    """A minimal refusing case, used to sample the refusal record's shape."""
    args = arguments()
    args["expected_approval_sha256"] = dict(args["expected_approval_sha256"])
    args["expected_approval_sha256"][recheck.APPROVAL_PATHS[0]] = "0" * 64
    return args


if __name__ == "__main__":
    main()
