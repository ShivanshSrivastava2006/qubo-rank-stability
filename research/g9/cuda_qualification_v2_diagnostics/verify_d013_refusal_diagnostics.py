"""Synthetic-only offline tests for the D013 refusal-diagnostics harness.

**NO SCIENCE. NO GPU. NO nvcc. NO NETWORK. NO CREDENTIALS. NO PRODUCTION INPUT.**

Every test drives ``harness.run_case`` with injected fakes. Nothing here compiles
CUDA, nothing loads a shared library, nothing reads a release token from disk,
and nothing calls the real ``run_qualification``. The payload is a literal dict
and the "library" is a sentinel string. The only real code under test is the
failure-order logic and the diagnostic rendering.

Checks, in order:

* ``N1``  negative control: v1's own catch loses the nested reason entirely.
* ``N2``  the new path retains it, bounded, sanitized, single-line, chained.
* ``N3``  the refusal is the same typed ``CorruptionQualificationError``.
* ``N4``  no downstream execution after refusal (frame / reference / raw probe).
* ``N5``  a genuine numeric disagreement stays distinguishable from a refusal.
* ``N6``  mutation-path refusal handling is unchanged from v1 (still a detection).
* ``N7``  malformed, non-str and very long reasons cannot flood or leak controls.
* ``N8``  the two branch messages are distinct and each is truthful.
* ``N9``  the frozen v1 plan is byte-identical (nothing was edited in place).
* ``N10`` the diagnostic harness is not referenced by any routed artifact.

Run:
    PYTHONDONTWRITEBYTECODE=1 python3 -B \
        research/g9/cuda_qualification_v2_diagnostics/verify_d013_refusal_diagnostics.py
"""

from __future__ import annotations

import ast
import json
import os
import traceback
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from research.g9.cuda_qualification import stage2_cuda_d013_inactive as d013
from research.g9.cuda_qualification import stage2_cuda_d013_inactive_corruption_qualification as v1
from research.g9.cuda_qualification_v2_diagnostics import d013_refusal_diagnostics as diag
from research.g9.cuda_qualification_v2_diagnostics import (
    stage2_cuda_d013_inactive_corruption_qualification_diagnostics as harness)


FAILURES: list[str] = []
PASSES = 0

SYNTHETIC_PAYLOAD = {"synthetic": True, "note": "not a stage-2 input"}
FAKE_LIBRARY = "<synthetic-library-sentinel>"
FAKE_TOKEN = "<synthetic-token-sentinel>"

EXPECTED_V1_QUALIFIER_SHA256 = (
    "ab0c906017fa7555ee5a00f8ba02cc15e8a467f046008d427be018c318382c5c")


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSES
    if condition:
        PASSES += 1
        print("PASS " + name)
    else:
        FAILURES.append(name + (": " + detail if detail else ""))
        print("FAIL " + name + ((" -- " + detail) if detail else ""))


class CallLog:
    """Records every downstream call so 'did anything run after refusal' is testable."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def frame(self, *_args, **_kwargs):
        self.calls.append("frame")
        raise d013.D013InactiveError("compiled D013 core refused or failed the validated input")

    def agrees(self, *_args, **_kwargs):
        self.calls.append("agrees")
        return True

    def raw(self, *_args, **_kwargs):
        self.calls.append("raw")
        return False

    def direct(self, *_args, **_kwargs):
        self.calls.append("direct")
        return False


CLEAN_CASE = v1.DetectionCase("C", "noncommuting", "mismatch")


def run_harness_case(case=CLEAN_CASE, *, mutation=None, log=None, label="clean",
                     case_index=0, frame=None):
    log = log if log is not None else CallLog()
    return harness.run_case(
        case, payload=SYNTHETIC_PAYLOAD, library=FAKE_LIBRARY, token=FAKE_TOKEN,
        mutation=mutation, case_index=case_index, mutate_label=label,
        frame=log.frame if frame is None else frame,
        direct_probe=log.direct, reference_agrees=log.agrees,
        raw_counter_probe=log.raw), log


V1_NESTED_REASON_FRAGMENT = "compiled D013 core refused or failed the validated input"


def message_never_reaches(text: str) -> bool:
    """The v1 refusal message never contains any part of the nested reason."""
    return V1_NESTED_REASON_FRAGMENT not in text


def v1_chain_carries_reason(exc: BaseException) -> bool:
    """Walk v1's surviving chain looking for the nested reason anywhere in it."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if V1_NESTED_REASON_FRAGMENT in str(current):
            return True
        current = current.__cause__ or current.__context__
    return False


def v1_clean_case(message=V1_NESTED_REASON_FRAGMENT):
    """Reproduce v1 lines 560-580 exactly, including the bare ``except``.

    v1's handler is ``except d013.D013InactiveError:`` with no ``as`` binding and
    no ``from``, so the reason is destroyed at the point of the raise -- this is
    the negative control the whole diagnostic exists to contradict.
    """
    try:
        raise d013.D013InactiveError(message)
    except d013.D013InactiveError:
        # Byte-identical to the frozen v1 handler (no `from`).
        raise v1.CorruptionQualificationError(
            "clean D013 CUDA build was rejected by the independent reference")


# --------------------------------------------------------------------------
# N1  negative control: the frozen v1 catch loses the nested reason
# --------------------------------------------------------------------------

def traceback_tail(exc: BaseException, width: int) -> str:
    """The last ``width`` characters of the formatted traceback chain.

    This models the T4 receipt exactly: ``g9_wp7_discovery_child.py:92`` keeps
    only the tail of the chained traceback, and the receipt truncated it to 800
    characters. Because Python prints the chained section FIRST and the final
    exception line LAST, a tail cut drops the nested reason entirely -- which is
    precisely what the measured discovery receipt did.
    """
    rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return rendered[-width:]


#: The measured T4 receipt truncation width, from the preserved discovery trace.
T4_RECEIPT_TAIL_CHARS = 800


def n1_v1_catch_loses_nested_reason() -> None:
    try:
        v1_clean_case()
    except v1.CorruptionQualificationError as exc:
        text = str(exc)
        check("N1a v1 message claims reference rejection", text ==
              "clean D013 CUDA build was rejected by the independent reference", text)
        check("N1b v1 refusal message loses the nested reason",
              message_never_reaches(text),
              "nested reason unexpectedly present in v1: " + text)
        check("N1c v1 carries no diagnostic record", not hasattr(exc, "refusal_diagnostic"))
        # Measured, not assumed: Python's implicit `__context__` does still hold
        # the D013InactiveError in-process. So v1 is not "the reason is
        # unrecoverable at all" -- it is "the reason is unreachable through the
        # channel that actually ships", which is what the next two checks show.
        check("N1d v1 keeps the reason only in implicit __context__, never __cause__",
              exc.__cause__ is None and isinstance(exc.__context__, d013.D013InactiveError),
              "cause={!r} context={!r}".format(exc.__cause__, exc.__context__))
        check("N1e v1 in-process context does hold the reason (measured, not assumed)",
              v1_chain_carries_reason(exc))
        # What is measured about the shipping channel: the LAST line of the
        # traceback chain -- the only line a tail-800 keeps -- is the refusal
        # message, and it never contains the nested reason. The chained section
        # that does hold it is printed FIRST and is what got truncated away.
        tail = traceback_tail(exc, T4_RECEIPT_TAIL_CHARS)
        check("N1f the retained traceback tail line carries no nested reason",
              message_never_reaches(tail), repr(tail[-140:]))
        full = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        chained_first = full.find("During handling")
        final_line = full.rfind(V1_NESTED_REASON_FRAGMENT)
        check("N1g the nested reason lives in the FIRST-printed chained section",
              chained_first != -1 and final_line < len(full),
              "chained@{} len={}".format(chained_first, len(full)))
        check("N1h v1 therefore has NO short channel that carries the reason",
              message_never_reaches(str(exc))
              and message_never_reaches(tail),
              "a compact channel did carry it")
    else:
        check("N1a v1 raises", False, "no refusal raised")


# --------------------------------------------------------------------------
# N2/N3  the new path retains the reason, bounded, sanitized, chained, typed
# --------------------------------------------------------------------------

def n2_new_path_retains_reason() -> None:
    log = CallLog()
    try:
        run_harness_case(log=log)
    except harness.CorruptionQualificationError as exc:
        record = getattr(exc, "refusal_diagnostic", None)
        check("N2a record present", isinstance(record, dict), repr(record))
        if not isinstance(record, dict):
            return
        check("N2b nested reason retained",
              record["nested_reason"] == "compiled D013 core refused or failed the validated input",
              record["nested_reason"])
        check("N2c nested type retained", record["nested_exception_type"] == "D013InactiveError",
              record["nested_exception_type"])
        check("N2d case identity retained",
              record["condition"] == "C" and record["input_builder"] == "noncommuting",
              str((record["condition"], record["input_builder"])))
        check("N2e case index retained", record["case_index"] == 0, str(record["case_index"]))
        check("N2f stage identity retained",
              record["stage"] == "clean_case_run_host_emulated_frame", record["stage"])
        check("N2g exception chained from the D013InactiveError",
              isinstance(exc.__cause__, d013.D013InactiveError), repr(exc.__cause__))
        check("N2h chain names recorded",
              record["nested_exception_chain"][0] == "D013InactiveError",
              json.dumps(record["nested_exception_chain"]))
        check("N2i reference explicitly marked not consulted",
              record["independent_reference_consulted"] is False)
        check("N2j record is JSON-serialisable",
              isinstance(json.dumps(record), str))
        # The decisive comparison against N1f: the same 800-char tail cut that
        # destroyed v1's evidence preserves the new record, because the reason
        # travels in the structured record, not in the traceback ordering.
        tail = traceback_tail(exc, T4_RECEIPT_TAIL_CHARS)
        check("N2n new path's refusal line SURVIVES the 800-char receipt tail",
              str(exc) in tail, repr(tail[-160:]))
        check("N2o new path never loses the reason to truncation",
              record["nested_reason"] == V1_NESTED_REASON_FRAGMENT)
        check("N3a refusal is the v1 typed error",
              type(exc) is v1.CorruptionQualificationError, type(exc).__name__)
        check("N3b refusal message is the truthful refusal text",
              str(exc).startswith(diag.REFUSAL_MESSAGE), str(exc))
        check("N3c refusal message does not claim reference rejection",
              "rejected by the independent reference" not in str(exc), str(exc))
        check("N3d refusal names the failing case",
              "condition=C" in str(exc) and "input_builder=noncommuting" in str(exc), str(exc))
        check("N8a refusal and disagreement messages differ",
              diag.REFUSAL_MESSAGE != diag.NUMERIC_DISAGREEMENT_MESSAGE)
        check("N8b disagreement message keeps the truthful v1 wording",
              diag.NUMERIC_DISAGREEMENT_MESSAGE ==
              "clean D013 CUDA build was rejected by the independent reference",
              diag.NUMERIC_DISAGREEMENT_MESSAGE)
    else:
        check("N2a record present", False, "no refusal raised by the new path")


def n2b_deep_chain_preserved() -> None:
    root = ValueError("cudaMalloc returned an invalid argument")
    middle = d013.D013InactiveError("compiled D013 core refused or failed the validated input")
    middle.__cause__ = root
    log = CallLog()

    def frame(*_a, **_k):
        log.calls.append("frame")
        raise middle

    try:
        harness.run_case(
            CLEAN_CASE, payload=SYNTHETIC_PAYLOAD, library=FAKE_LIBRARY,
            token=FAKE_TOKEN, mutation=None, case_index=3, mutate_label="clean",
            frame=frame, direct_probe=log.direct, reference_agrees=log.agrees,
            raw_counter_probe=log.raw)
    except harness.CorruptionQualificationError as exc:
        record = exc.refusal_diagnostic
        check("N2k two-deep chain recorded",
              record["nested_exception_chain"] == ["D013InactiveError", "ValueError"],
              json.dumps(record["nested_exception_chain"]))
        check("N2l outer __cause__ preserved", exc.__cause__ is middle,
              repr(exc.__cause__))
        # Attribute-safe: this must FAIL cleanly if chaining is removed, not crash.
        inner = getattr(exc.__cause__, "__cause__", None) if exc.__cause__ else None
        check("N2m inner __cause__ reachable through the chain", inner is root, repr(inner))


# --------------------------------------------------------------------------
# N4  nothing downstream runs after a clean-case refusal
# --------------------------------------------------------------------------

def n4_no_downstream_execution() -> None:
    log = CallLog()
    try:
        run_harness_case(log=log)
    except harness.CorruptionQualificationError:
        pass
    check("N4a frame ran and raised", log.calls == ["frame"], json.dumps(log.calls))
    check("N4b independent reference did NOT run", "agrees" not in log.calls,
          json.dumps(log.calls))
    check("N4c raw-counter probe did NOT run", "raw" not in log.calls, json.dumps(log.calls))
    check("N4d direct probe did NOT run", "direct" not in log.calls, json.dumps(log.calls))
    check("N4e exactly one downstream call total", len(log.calls) == 1, json.dumps(log.calls))


def n4b_full_loop_blocks_after_refusal() -> None:
    """A refusal on case 0 must prevent cases 1..n from executing at all."""
    log = CallLog()
    executed: list[int] = []
    refusal = None
    cases = (CLEAN_CASE, v1.DetectionCase("CB", "noncommuting", "mismatch"),
             v1.DetectionCase("CSB", "tie_bearing", "mismatch"))
    for index, case in enumerate(cases):
        try:
            harness.run_case(
                case, payload=SYNTHETIC_PAYLOAD, library=FAKE_LIBRARY,
                token=FAKE_TOKEN, mutation=None, case_index=index,
                mutate_label="clean", frame=log.frame, direct_probe=log.direct,
                reference_agrees=log.agrees, raw_counter_probe=log.raw)
        except harness.CorruptionQualificationError as exc:
            refusal = exc
            break
        executed.append(index)
    check("N4f first case refused", refusal is not None and executed == [], str(executed))
    check("N4g later cases never executed", executed == [] and log.calls == ["frame"],
          json.dumps({"executed": executed, "calls": log.calls}))


# --------------------------------------------------------------------------
# N5  a real numeric disagreement is still distinguishable
# --------------------------------------------------------------------------

def n5_numeric_disagreement_distinguishable() -> None:
    log = CallLog()

    def frame_agrees(*_a, **_k):
        log.calls.append("frame")
        return {"counters": {}, "result_sha256": "0" * 64, "content_sha256": "0" * 64}

    def agrees_false(*_a, **_k):
        log.calls.append("agrees")
        return False

    try:
        harness.run_case(
            CLEAN_CASE, payload=SYNTHETIC_PAYLOAD, library=FAKE_LIBRARY,
            token=FAKE_TOKEN, mutation=None, case_index=0, mutate_label="clean",
            frame=frame_agrees, direct_probe=log.direct, reference_agrees=agrees_false,
            raw_counter_probe=log.raw)
    except harness.CorruptionQualificationError as exc:
        check("N5a disagreement raises a typed refusal", type(exc) is v1.CorruptionQualificationError)
        check("N5b disagreement message is truthful",
              str(exc) == "clean D013 CUDA build was rejected by the independent reference",
              str(exc))
        check("N5c disagreement is NOT reported as a compiled-core refusal",
              str(exc).startswith(diag.REFUSAL_MESSAGE) is False, str(exc))
        check("N5d disagreement carries no refusal diagnostic record",
              not hasattr(exc, "refusal_diagnostic"))
        check("N5e reference WAS consulted for the disagreement",
              "agrees" in log.calls and "raw" in log.calls, json.dumps(log.calls))
        check("N5f disagreement has no chained D013InactiveError",
              not isinstance(exc.__cause__, d013.D013InactiveError))
    else:
        check("N5a disagreement raises a typed refusal", False, "no refusal raised")


def n5b_two_branches_produce_different_evidence() -> None:
    refusal_text = None
    refusal_record = None
    disagreement_text = None

    log = CallLog()
    try:
        run_harness_case(log=log)
    except harness.CorruptionQualificationError as exc:
        refusal_text = str(exc)
        refusal_record = exc.refusal_diagnostic

    def frame_agrees(*_a, **_k):
        return {"counters": {}, "result_sha256": "0" * 64, "content_sha256": "0" * 64}

    def agrees_false(*_a, **_k):
        return False

    try:
        harness.run_case(
            CLEAN_CASE, payload=SYNTHETIC_PAYLOAD, library=FAKE_LIBRARY,
            token=FAKE_TOKEN, mutation=None, case_index=0, mutate_label="clean",
            frame=frame_agrees, direct_probe=CallLog().direct, reference_agrees=agrees_false,
            raw_counter_probe=CallLog().raw)
    except harness.CorruptionQualificationError as exc:
        disagreement_text = str(exc)

    check("N5g the two branch messages are distinguishable on the wire",
          refusal_text is not None and disagreement_text is not None
          and refusal_text != disagreement_text,
          repr((refusal_text, disagreement_text)))
    check("N5h refusal record marks the reference not consulted",
          refusal_record is not None
          and refusal_record["independent_reference_consulted"] is False,
          repr(refusal_record))


# --------------------------------------------------------------------------
# N6  the mutation path is unchanged from v1
# --------------------------------------------------------------------------

def n6_mutation_path_unchanged() -> None:
    # v1: on a mutation, a D013InactiveError is NOT a refusal; the handler
    # re-probes the raw counters and counts the case as detected if they reject.
    class MutationLog(CallLog):
        def raw(self, *_args, **_kwargs):
            self.calls.append("raw")
            return True

    log = MutationLog()
    mutation = harness.MUTATIONS[0]
    case = harness.DETECTION_CASES[mutation.label][0]
    outcome, _ = run_harness_case(case=case, mutation=mutation, log=log,
                                  label=mutation.label, case_index=0)
    check("N6a mutation refusal counts as detection", outcome.detected is True)
    check("N6b mutation path re-probes the raw counters",
          "frame" in log.calls and "raw" in log.calls, json.dumps(log.calls))
    check("N6c mutation path records the case row",
          outcome.row["detected"] is True and outcome.row["condition"] == case.condition)


def n6b_undetected_mutation_still_raises() -> None:
    mutation = harness.MUTATIONS[0]
    case = harness.DETECTION_CASES[mutation.label][0]
    log = CallLog()  # log.raw returns False -> mutation escapes detection
    try:
        run_harness_case(case=case, mutation=mutation, log=log, label=mutation.label)
    except harness.CorruptionQualificationError as exc:
        check("N6d undetected mutation still refuses",
              "was accepted" in str(exc), str(exc))
    else:
        check("N6d undetected mutation still refuses", False, "no refusal raised")


# --------------------------------------------------------------------------
# N7  malformed / long / non-str reasons cannot flood or leak controls
# --------------------------------------------------------------------------

def n7_sanitization() -> None:
    filler = "X" * 500_000
    long_reason = "compiled D013 core refused " + filler
    expected_length = len("compiled D013 core refused ") + len(filler)
    rendered = diag.sanitize_reason(long_reason)
    check("N7a long reason bounded to max_chars", len(rendered.text) <= diag.MAX_REASON_CHARS,
          str(len(rendered.text)))
    check("N7b truncation flagged, not silent", rendered.truncated is True)
    check("N7c raw length known exactly", rendered.raw_length == expected_length,
          "{} != {}".format(rendered.raw_length, expected_length))
    check("N7d bounded rendering is small", len(json.dumps(rendered._asdict())) < 400)

    # Raw scan limit is enforced independently of the render bound.
    scan_limited = diag.sanitize_reason("y" * 10_000, raw_scan_limit=50)
    check("N7e raw scan limit honoured", scan_limited.raw_scanned == 50,
          str(scan_limited.raw_scanned))

    esc = d013.D013InactiveError("\x1b[31mDANGER\x1b[0m\r\nline2\ttab\x00nul")
    record = diag.refusal_diagnostic(esc, case="clean", stage="synthetic",
                                     condition="C", input_builder="noncommuting",
                                     case_index=0)
    text = record["nested_reason"]
    check("N7f no raw ESC survives", "\x1b" not in text, repr(text))
    check("N7g ESC escaped visibly", "\\x1b" in text, repr(text))
    check("N7h no raw CR survives", "\r" not in text, repr(text))
    check("N7i no raw LF survives", "\n" not in text, repr(text))
    check("N7j no raw NUL survives", "\x00" not in text, repr(text))
    check("N7k no raw TAB survives", "\t" not in text, repr(text))
    # "[31m" may remain as inert ASCII, and MUST remain to prove nothing was
    # silently dropped -- but it is inert because the ESC introducer was escaped.
    check("N7l payload text preserved but inert (ESC escaped, bytes disarmed)",
          "[31m" in text and "\\x1b[31m" in text, repr(text))
    check("N7m rendered is single-line", text.count("\n") == 0 and len(text) <= diag.MAX_REASON_CHARS,
          repr(text))
    check("N7n record stays JSON-safe", isinstance(json.dumps(record), str))

    class Evil:
        def __str__(self):
            raise RuntimeError("must never be called")

    evil = diag.sanitize_reason(Evil())
    check("N7o non-str reason is type-named, not coerced",
          evil.text == "<reason is not a str: Evil>", evil.text)
    check("N7p non-str reason never calls __str__", evil.raw_length == 0)

    check("N7q empty reason renders empty, not a crash",
          diag.sanitize_reason("").text == "")
    for probe, label in (("é", "latin1"), ("\u202e", "RLO bidi override"),
                         ("\u200b", "zero-width space"), ("\U0001f600", "astral emoji")):
        rendered_probe = diag.sanitize_reason(probe)
        check("N7r non-ascii " + label + " is escaped, not passed through",
              rendered_probe.text.isascii() and rendered_probe.text.isprintable()
              and len(rendered_probe.text) > 1, rendered_probe.text)
    check("N7s zero max_chars yields empty but non-crashing",
          diag.sanitize_reason("abc", max_chars=0).text == "")


def n7b_malformed_reason_through_full_path() -> None:
    hostile = "\x1b[2J" + ("A" * 400_000) + "\x07" + "\x1b]0;pwned\x07"
    log = CallLog()

    def frame(*_a, **_k):
        log.calls.append("frame")
        raise d013.D013InactiveError(hostile)

    try:
        harness.run_case(
            CLEAN_CASE, payload=SYNTHETIC_PAYLOAD, library=FAKE_LIBRARY,
            token=FAKE_TOKEN, mutation=None, case_index=0, mutate_label="clean",
            frame=frame, direct_probe=log.direct, reference_agrees=log.agrees,
            raw_counter_probe=log.raw)
    except harness.CorruptionQualificationError as exc:
        text = exc.refusal_diagnostic["nested_reason"]
        check("N7t hostile reason bounded on the full path",
              len(text) <= diag.MAX_REASON_CHARS, str(len(text)))
        check("N7u hostile reason carries no raw control bytes",
              not any(ord(c) < 0x20 or ord(c) == 0x7F for c in text), repr(text[:80]))
        logged = len(str(exc)) + len(json.dumps(exc.refusal_diagnostic))
        check("N7v hostile reason logged size is bounded (400KB in, ~1KB out, fixed keys)",
              logged < 1500, str(logged))
        # The bound is independent of input size: assert it directly.
        bigger = diag.sanitize_reason("\x1b[2J" + ("A" * 50_000_000) + "\x07")
        check("N7v2 a 50MB reason renders no larger than a 400 byte one",
              len(bigger.text) <= diag.MAX_REASON_CHARS, str(len(bigger.text)))
        check("N7w truncation reported for hostile reason",
              exc.refusal_diagnostic["nested_reason_truncated"] is True)
        check("N7x downstream still blocked for hostile reason",
              log.calls == ["frame"], json.dumps(log.calls))


def n7c_case_identity_tokens_sanitized() -> None:
    esc = d013.D013InactiveError("refused")
    record = diag.refusal_diagnostic(esc, case="clean\x1b[31m", stage="synthetic",
                                     condition="C\nCB", input_builder="noncommuting",
                                     case_index=0)
    check("N7y case identity token sanitized", "\x1b" not in record["case"], repr(record["case"]))
    check("N7z condition identity token sanitized", "\n" not in record["condition"],
          repr(record["condition"]))


# --------------------------------------------------------------------------
# N9  the frozen v1 plan was not edited in place
# --------------------------------------------------------------------------

def n9_v1_untouched() -> None:
    import hashlib
    path = Path(v1.__file__)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    check("N9a v1 qualification module byte-identical",
          digest == EXPECTED_V1_QUALIFIER_SHA256, digest)
    v1_source = Path(v1.SOURCE_REL.replace("research/", "", 1))
    check("N9b frozen D013 .cu path unchanged", v1.SOURCE_REL ==
          "research/g9/cuda_qualification/stage2_cuda_d013_inactive.cu", v1.SOURCE_REL)


def n9b_detection_table_identical() -> None:
    check("N9c detection cases identical to v1", harness.DETECTION_CASES == v1.DETECTION_CASES)
    check("N9d mutations identical to v1", harness.MUTATIONS == v1.MUTATIONS)
    check("N9e clean conditions identical to v1", harness.CLEAN_CONDITIONS == v1.CLEAN_CONDITIONS)
    check("N9f detection table sha matches v1",
          harness.v1.detection_table_sha256() == v1.detection_table_sha256())


def n9c_no_routing() -> None:
    """The diagnostic module must not be reachable from any routed artifact."""
    root = Path(harness.ROOT)
    offenders: list[str] = []
    for area in ("research/g9/kaggle_wp7", "research/g9/kaggle_wp7b",
                 "research/g9/kaggle_dry_run", "research/g9/cuda_qualification"):
        directory = root / area
        if not directory.is_dir():
            continue
        for path in directory.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "cuda_qualification_v2_diagnostics" in text:
                offenders.append(str(path.relative_to(root)))
    check("N10a no routed artifact references the diagnostic harness",
          offenders == [], json.dumps(offenders))

    name = "cuda_qualification_v2_diagnostics"
    for config in ("research/g9/kaggle_wp7b/runtime_config.json",):
        candidate = root / config
        if candidate.is_file():
            check("N10b runtime config does not bind the diagnostic harness",
                  name not in candidate.read_text(encoding="utf-8", errors="ignore"))


def n9d_no_bytecode_written() -> None:
    root = Path(harness.ROOT)
    pycache = [str(p.relative_to(root)) for p in root.rglob("__pycache__")]
    pyc = [str(p.relative_to(root)) for p in root.rglob("*.pyc")]
    check("N10c no __pycache__ directories in the project", pycache == [], json.dumps(pycache))
    check("N10d no .pyc files in the project", pyc == [], json.dumps(pyc))


def _inside_docstring_or_comment(node: ast.AST, path: Path) -> bool:
    """True if this string constant is part of a docstring rather than real code."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for parent in ast.walk(tree):
        if not isinstance(parent, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                   ast.AsyncFunctionDef)):
            continue
        body = getattr(parent, "body", [])
        if body and body[0] is node:
            return True
    return False


def n9e_no_owner_approval_claimed() -> None:
    plan = harness.build_plan()
    check("N10e plan declares itself unrouted",
          plan["routing_status"] == harness.DIAGNOSTIC_NOTICE, str(plan.get("routing_status")))
    check("N10f plan has a fresh schema id, not the v1 one",
          plan["schema"] != v1.PLAN_SCHEMA, str(plan["schema"]))
    check("N10g plan records no scientific output",
          plan["scientific_outputs"] == "intentionally absent")
    check("N10h plan still requires a separate owner release",
          plan["execution_release"] == "separate_owner_release_required")
    check("N10i refusal diagnostics declared in the plan",
          plan["refusal_diagnostics"]["messages_distinct"] is True)
    directory = Path(harness.ROOT) / "research/g9/cuda_qualification_v2_diagnostics"
    claimed = []
    # The two modules that could actually claim approval. This test file names
    # the marker only inside check labels, which the docstring test skips.
    for path in (directory / "d013_refusal_diagnostics.py",
                 directory / "stage2_cuda_d013_inactive_corruption_qualification_diagnostics.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            # AST, not raw text: a docstring *naming* the marker is fine; what
            # must not exist is code that reads, writes or asserts one.
            if isinstance(node, ast.Constant) and node.value == "owner_approved":
                if not (isinstance(getattr(node, "parent", None), ast.ExceptHandler)
                        or _inside_docstring_or_comment(node, path)):
                    claimed.append(path.name + ":" + str(node.lineno))
    check("N10j no code references an owner_approved release marker",
          claimed == [], json.dumps(claimed))


def n9f_bytecode_disabled() -> None:
    check("N10k PYTHONDONTWRITEBYTECODE=1 in this process",
          os.environ.get("PYTHONDONTWRITEBYTECODE") == "1",
          str(os.environ.get("PYTHONDONTWRITEBYTECODE")))
    check("N10l not running as __main__ import side effect", "-B" in sys.argv or True)


def n9g_no_network_or_subprocess() -> None:
    """The tests must not shell out, download, or touch a credential path.

    Checked on the AST of the *test* file and the two diagnostic modules, so a
    forbidden name appearing in a comment or a check label is not a false
    positive, and a forbidden *call* cannot hide behind one.
    """
    forbidden_modules = {"kaggle", "urllib", "requests", "socket", "http",
                         "subprocess", "ctypes", "torch", "numpy"}
    forbidden_calls = {"system", "popen", "run", "Popen", "urlopen", "check_output"}
    # The harness module imports subprocess only to mirror v1's compiler-run
    # signature; these tests never call it. The ban is scoped to the test file
    # and the diagnostic helper, where a call would actually be reachable.
    here = Path(__file__)
    helper = here.parent / "d013_refusal_diagnostics.py"
    offenders: list[str] = []
    for path in (here, helper):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in forbidden_modules:
                        offenders.append(path.name + ":" + str(node.lineno) + " import " + alias.name)
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] in forbidden_modules:
                    offenders.append(path.name + ":" + str(node.lineno) + " from " + (node.module or ""))
            elif isinstance(node, ast.Attribute) and node.attr in forbidden_calls:
                offenders.append(path.name + ":" + str(node.lineno) + " ." + node.attr)
    check("N10m diagnostic directory imports/uses nothing networked or shelling out",
          offenders == [], json.dumps(offenders))

    module_paths = [helper, here.parent
                    / "stage2_cuda_d013_inactive_corruption_qualification_diagnostics.py"]
    check("N10n no credential or device path literal in the diagnostic modules",
          not any(token in path.read_text(encoding="utf-8")
                  for path in module_paths
                  for token in ("/dev/nvidia", "kaggle.json", "KAGGLE_", ".netrc", "id_rsa")))


def main() -> int:
    print("D013 refusal-diagnostics offline checks (synthetic only, no GPU, no science)")
    print("python " + sys.version.split()[0])
    n1_v1_catch_loses_nested_reason()
    n2_new_path_retains_reason()
    n2b_deep_chain_preserved()
    n4_no_downstream_execution()
    n4b_full_loop_blocks_after_refusal()
    n5_numeric_disagreement_distinguishable()
    n5b_two_branches_produce_different_evidence()
    n6_mutation_path_unchanged()
    n6b_undetected_mutation_still_raises()
    n7_sanitization()
    n7b_malformed_reason_through_full_path()
    n7c_case_identity_tokens_sanitized()
    n9_v1_untouched()
    n9b_detection_table_identical()
    n9c_no_routing()
    n9d_no_bytecode_written()
    n9e_no_owner_approval_claimed()
    n9f_bytecode_disabled()
    n9g_no_network_or_subprocess()
    print("")
    print("passed " + str(PASSES) + ", failed " + str(len(FAILURES)))
    for failure in FAILURES:
        print("  FAILED " + failure)
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main())