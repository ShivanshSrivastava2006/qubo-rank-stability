"""Bounded, sanitized diagnostics for D013 clean-case refusals.

**DRAFT DIAGNOSTIC. NOT A RELEASE ARTIFACT. NOT OWNER-APPROVED. NOT ROUTED.**

This module exists because of a measured, non-hypothetical defect in the frozen
D013 v1 corruption qualification plan
``research/g9/cuda_qualification/stage2_cuda_d013_inactive_corruption_qualification.py``.

Measured fact (T4 discovery push consumed 2026-10-01, see
``g9_jobs/logs/discovery.d013.diagnose.bout``): the clean case reached the
``except d013.D013InactiveError`` handler at v1 lines 575-578 and that handler
raised ``CorruptionQualificationError("clean D013 CUDA build was rejected by
the independent reference")``. Two distinct branches carry that identical
string in v1 -- the numeric-disagreement raise at line 574 and this handler at
line 577 -- so the preserved traceback cannot distinguish them. The handler also
binds no exception variable at all, so ``str(exc)`` is discarded and never
reaches the receipt. The result is that an ordinary D013 refusal (for example
``compiled D013 core refused or failed the validated input``) is reported to the
owner as a failure of the independent numerical reference, which did not run.

This module supplies the missing observation surface and nothing else. It:

* preserves the v1 failure order and fail-closed disposition unchanged -- a
  diagnostic refusal is still a ``CorruptionQualificationError`` raised out of
  the case loop, so every dependent GPU, WP3 and write step remains blocked;
* retains a bounded, sanitized, single-line rendering of the nested reason, the
  exception type name, and the case/stage identity that was in flight;
* preserves exception chaining (``raise ... from exc``) so the original
  ``D013InactiveError`` and its own ``__cause__`` chain remain inspectable;
* keeps the numeric-disagreement branch truthful and *distinguishable* from a
  refusal, by giving the two branches separate, non-overlapping message
  constants.

Explicitly NOT here: no change to any guard, no catch-and-continue, no
substitution of a success value, no release token, no owner approval, no CUDA
call, no scientific computation, and no production input.

Bounded-rendering contract
--------------------------
A refusal reason is untrusted text from a compiled-library boundary. Rendering
is bounded in three independent ways so that neither a hostile nor merely
runaway reason can flood a log or smuggle raw control bytes through it:

1. ``RAW_SCAN_LIMIT`` bounds how much raw text is even inspected.
2. ``MAX_REASON_CHARS`` bounds the rendered result, with an explicit
   ``truncated`` flag rather than a silent cut.
3. Every character outside printable ASCII is escaped to a visible two-or-more
   character form, so ESC/CSI/ANSI sequences and CR/LF cannot survive into a
   log line and cannot be reassembled from the rendered text.

The escape happens *before* slicing, so the bound is enforced on rendered
output, which is what actually reaches a log.
"""

from __future__ import annotations

from typing import NoReturn, NamedTuple

# The typed refusal the diagnostic path raises. It is deliberately the SAME
# class the v1 plan raises, so any existing ``except CorruptionQualificationError``
# downstream of the qualification call keeps catching it. Using a new exception
# type would silently unblock a guard, so it is not permitted here.
from research.g9.cuda_qualification.stage2_cuda_d013_inactive_corruption_qualification import (
    CorruptionQualificationError,
)


DIAGNOSTIC_HARNESS_VERSION = "d013-refusal-diagnostics/v2.1"
DIAGNOSTIC_SCHEMA = "decisions_os/g9_d013_refusal_diagnostic/v1"

#: How many raw characters are inspected before the renderer stops looking.
RAW_SCAN_LIMIT = 4096

#: Hard bound on the rendered reason. Matches the frozen core harness convention
#: at ``stage2_cuda_core_corruption_qualification.py:358`` (``str(exc)[:200]``)
#: so the two harnesses record comparable evidence.
MAX_REASON_CHARS = 200

#: The refusal branch. Truthful: the independent reference did NOT disagree with
#: anything, because it was never reached.
REFUSAL_MESSAGE = ("clean D013 CUDA build was REFUSED by the compiled core before "
                   "the independent reference was consulted")

#: The numeric-disagreement branch, preserved verbatim from v1 line 573-574.
#: Truthful: the reference ran and returned numbers it would not accept.
NUMERIC_DISAGREEMENT_MESSAGE = ("clean D013 CUDA build was rejected by the "
                                "independent reference")

# The two messages must never collide again: their collision in v1 is the entire
# reason this module exists. This is asserted at import time, not only in tests.
if REFUSAL_MESSAGE == NUMERIC_DISAGREEMENT_MESSAGE:  # pragma: no cover
    raise RuntimeError("refusal and numeric-disagreement messages must differ")

_ESCAPES = {
    "\\": "\\\\",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\x0b": "\\v",
    "\x0c": "\\f",
    "\x00": "\\x00",
    "\x1b": "\\x1b",
    "\x7f": "\\x7f",
}


class SanitizedReason(NamedTuple):
    """A bounded, single-line, control-free rendering of an untrusted reason."""

    text: str
    truncated: bool
    raw_length: int
    raw_scanned: int
    non_printable_escaped: int


def sanitize_reason(raw: object, *, max_chars: int = MAX_REASON_CHARS,
                    raw_scan_limit: int = RAW_SCAN_LIMIT) -> SanitizedReason:
    """Render ``raw`` as bounded, sanitized, single-line diagnostic text.

    Defensive by construction, because the caller is a ``except`` handler over
    an exception raised at a compiled-library boundary:

    * a non-``str`` ``raw`` is reported as a type name, never coerced;
    * at most ``raw_scan_limit`` characters are inspected;
    * every non-printable character is escaped, so no raw control byte, CR/LF
      or ANSI escape survives into the rendering;
    * the rendering is truncated to ``max_chars`` with ``truncated=True``.
    """
    if not isinstance(max_chars, int) or isinstance(max_chars, bool) or max_chars < 0:
        raise ValueError("max_chars must be a non-negative int")
    if (not isinstance(raw_scan_limit, int) or isinstance(raw_scan_limit, bool)
            or raw_scan_limit < 0):
        raise ValueError("raw_scan_limit must be a non-negative int")

    if type(raw) is not str:
        # Never repr() an arbitrary object: __repr__/__str__ may be overridden
        # to raise, to recurse, or to emit arbitrary content.
        return SanitizedReason("<reason is not a str: " + type(raw).__name__ + ">",
                               False, 0, 0, 0)

    raw_length = len(raw)
    escaped = 0
    pieces: list[str] = []
    rendered = 0
    for character in raw[:raw_scan_limit]:
        codepoint = ord(character)
        replacement = _ESCAPES.get(character)
        # Everything outside printable ASCII is escaped. `str.isprintable()` is
        # NOT sufficient here: it returns True for U+00E9 and for bidi and
        # zero-width characters, so a reason could carry invisible or
        # direction-spoofing text straight into a log line.
        if replacement is None and not (0x20 <= codepoint <= 0x7E):
            replacement = "\\u{:04x}".format(codepoint) if codepoint <= 0xFFFF else (
                "\\U{:08x}".format(codepoint))
        if replacement is not None:
            pieces.append(replacement)
            escaped += 1
            rendered += len(replacement)
        else:
            pieces.append(character)
            rendered += 1
        if rendered >= max_chars:
            break

    text = "".join(pieces)
    if len(text) > max_chars:
        text = text[:max_chars]
    truncated = rendered > max_chars or raw_length > raw_scan_limit
    return SanitizedReason(text, truncated, raw_length, min(raw_length, raw_scan_limit),
                           escaped)


def exception_type_name(exc: BaseException) -> str:
    """The exception's type name, sanitized to a single safe token."""
    name = type(exc).__name__
    return "".join(character if character.isalnum() or character == "_" else "_"
                   for character in name)[:64] or "UnknownException"


def cause_chain_names(exc: BaseException, *, depth: int = 8) -> list[str]:
    """Sanitized type names of the ``__cause__``/``__context__`` chain, bounded."""
    chain: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and len(chain) < depth and id(current) not in seen:
        seen.add(id(current))
        chain.append(exception_type_name(current))
        current = current.__cause__ or current.__context__
    return chain


def refusal_diagnostic(exc: BaseException, *, case: object, stage: str,
                       condition: object = None, input_builder: object = None,
                       mutation_label: object = None, case_index: object = None,
                       ) -> dict[str, object]:
    """Build the bounded diagnostic record for one clean-case D013 refusal.

    Returns a plain JSON-serialisable dict carrying the case/stage identity and
    the bounded nested reason. It does NOT raise, so callers that want to inspect
    the record before deciding can; :func:`raise_clean_case_refusal` is the
    raising form used by the harness.
    """
    if not isinstance(exc, BaseException):
        raise TypeError("refusal_diagnostic requires an exception instance")
    if not isinstance(stage, str) or not stage:
        raise ValueError("stage must be a non-empty str")
    reason = sanitize_reason(str(exc))
    return {
        "diagnostic_version": DIAGNOSTIC_HARNESS_VERSION,
        "schema": DIAGNOSTIC_SCHEMA,
        "branch": "compiled_core_refusal",
        "stage": stage,
        "case": _safe_token(case),
        "condition": _safe_token(condition),
        "input_builder": _safe_token(input_builder),
        "mutation_label": _safe_token(mutation_label),
        "case_index": case_index if isinstance(case_index, int) else None,
        "nested_exception_type": exception_type_name(exc),
        "nested_reason": reason.text,
        "nested_reason_truncated": reason.truncated,
        "nested_reason_raw_length": reason.raw_length,
        "nested_exception_chain": cause_chain_names(exc),
        "independent_reference_consulted": False,
        "evidence_class": "failure_evidence_only",
    }


def _safe_token(value: object, *, limit: int = 64) -> str:
    """Render an identity token as a bounded, printable, control-free string."""
    if isinstance(value, str):
        rendered = sanitize_reason(value, max_chars=limit).text
    elif isinstance(value, bool) or value is None:
        rendered = "true" if value is True else ("false" if value is False else "<none>")
    elif isinstance(value, int):
        # Case indices are small non-negative ordinals; render them as decimal
        # text rather than a type name, but keep them bounded like every token.
        rendered = str(value)[:limit]
    else:
        rendered = sanitize_reason(type(value).__name__, max_chars=limit).text
    return rendered


def refusal_message(*, condition: object, input_builder: object, case_index: object) -> str:
    """The bounded refusal headline that names *where* the refusal happened."""
    return (REFUSAL_MESSAGE + " (condition=" + _safe_token(condition) +
            ", input_builder=" + _safe_token(input_builder) +
            ", case_index=" + _safe_token(case_index) + ")")


def raise_clean_case_refusal(exc: BaseException, *, case: object, stage: str,
                             condition: object = None, input_builder: object = None,
                             mutation_label: object = None, case_index: object = None,
                             ) -> NoReturn:
    """Raise the typed qualification refusal, chained from ``exc``.

    This is the diagnostic replacement for the v1 handler. Semantics preserved
    from v1: a typed ``CorruptionQualificationError`` propagates out of the
    case loop, so the qualification aborts fail-closed and no dependent GPU,
    WP3 or write step runs. Semantics changed from v1, deliberately and only in
    the diagnostic dimension: the message is truthful and distinguishable, and
    the nested reason, exception type and case/stage identity are carried on the
    exception for the receipt.

    The record is attached to the raised exception as
    ``refusal_diagnostic`` so a caller that catches it downstream still sees the
    bounded evidence, without any of it being re-derived from ``str(exc)``.
    """
    record = refusal_diagnostic(exc, case=case, stage=stage, condition=condition,
                                input_builder=input_builder,
                                mutation_label=mutation_label, case_index=case_index)
    refusal = CorruptionQualificationError(
        refusal_message(condition=condition, input_builder=input_builder,
                        case_index=case_index))
    refusal.refusal_diagnostic = record  # type: ignore[attr-defined]
    raise refusal from exc