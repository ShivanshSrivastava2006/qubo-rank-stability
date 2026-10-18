#!/usr/bin/env python3
"""WP8d canonical drawn-instance artifact layout, parser and validator.

Owner default 5 of ``research/g9/kaggle_wp8/WP8_PRODUCTION_BUNDLE_DESIGN.md``
("What is the canonical file layout of a drawn instance and its prepared
record?", lines 155-164) was APPROVED at
``research/decisions/GATE_9_WP7_PINNED_DRAFT_AND_WP7B_OWNER_DECISION.md:146-154``:
"a reviewed generation-artifact layout, with its parser/validator bound before
the first draw."

This module *defines* that layout and validates it.  It invents nothing the
protocol does not already fix:

* the five canonical slots ``stage2_01``..``stage2_05`` and the per-instance
  destination are the protocol's
  (``research/decisions/GATE_9_STAGE2_PROTOCOL_DRAFT.md:51-53,220-222``);
* the write-once manifest, the atomic staging/rename promotion and the rehash
  boundary are WP5's, unchanged
  (``research/g9/stage2_generation_writer.py:44-56,162-233,271-325,328-382``);
* the U-08 seed commitment, the U-09 little-endian row-major binary64 return
  matrix and the U-10 label-blind partition digest are the generator's, and are
  re-derived here rather than trusted
  (``research/g9/stage2_generator.py:107-130,232-238,330-338``);
* the prepared record is WP5b's provenance record, unchanged
  (``research/g9/stage2_instance_preparation.py:146,751-832``).

Deliberate boundary: this module has **no draw, no command line and no
scientific step**.  It never calls a sampling function and never imports NumPy;
it names, hashes, binds and refuses.  It is not draw permission, and a layout
that parses is not an accepted instance: acceptance stays with the protocol's
own gates, and this repository's WP5b is deliberately synthetic-only
(``research/g9/stage2_instance_preparation.py:766-767``).

What "validated" means here, stated precisely
----------------------------------------------

This module validates SHAPE, BINDING and INTEGRITY.  It does not validate
SCIENTIFIC CONTENT, and no claim below should be read as if it did.

* **Shape** -- a record has the exact key set, schema string, types and hash
  forms this layout (and WP5b, for the prepared record) declare.  A field with
  the right name and type but a meaningless value passes.
* **Binding and integrity** -- the named file's bytes hash to the named value;
  the directory that was opened is the slot that was asked for; the generation
  record, the per-instance index and the WP5b prepared record all name the SAME
  instance, the same slot, the same attempt, the same implementation record and
  the same status.  A forgery that re-seals every hash it controls is still
  refused, because the cross-record agreement is checked against the files and
  not merely within one record.
* **NOT content** -- the return matrix is checked for exact length
  (``249*20*8`` bytes) and for the SHA-256 the generation record names.  The
  4,980 binary64 values inside are **not** re-derived, range-checked, or checked
  for finiteness, and the layout does not claim they are: the values come from the
  draw, and re-deriving them would be a scientific step this module is
  forbidden to take.  Likewise the prepared record's ``results`` block is passed
  through WP5b's validator, which seals it but does not re-run the optimisation
  that produced it.

The recorded U-09 moments, precisely
------------------------------------

``GENERATION.json`` now records the canonical binary64 encodings of ``mu_new``
and ``Sigma_new`` that the protocol requires
(``GATE_9_STAGE2_PROTOCOL_DRAFT.md:101-104``).  Those encodings were the protocol
content most clearly missing before, and it is worth being exact about what the
layout now does and does not establish about them.

What IS validated:

* **Form.**  Every value is an exact ``str`` in the C99 hexadecimal-float spelling
  the reviewed generator emits (``float(value).hex()``,
  ``stage2_generator.py:337-338``).  That spelling is chosen by the generator, not
  invented here: it is exact, platform independent and locale independent, which
  is exactly what a value inside a JSON record needs.
* **Shape.**  ``mu_new`` holds exactly ``ASSET_COUNT`` values; ``Sigma_new``
  exactly ``ASSET_COUNT * ASSET_COUNT``, row major, with its 20x20 shape declared
  and checked against the protocol's.
* **Encoding name.**  Both blocks declare ``binary64_hex_c99``, deliberately NOT
  the matrix's ``binary64_le``: these are two different encodings and conflating
  them would be silent drift.
* **Integrity.**  Each block carries a SHA-256 over its own canonical encoded
  text, which is RECOMPUTED and compared on read.  The index binds both digests,
  so a changed moment changes the generation record, the WP5 manifest and the
  index -- three independent commitments, none repairable by re-sealing another.

What is NOT validated, and is not claimed:

* **The numbers.**  The layout never decodes these values.  It does not check that
  ``mu_new`` is finite, that ``Sigma_new`` is symmetric, that it is PSD, that it
  agrees with the return matrix beside it, or that it is the sample covariance of
  that matrix.  Every one of those is a scientific check, this module imports no
  NumPy by design, and the protocol makes them the generator's post-conditions
  (``stage2_generator.py:288-297``) rather than the layout's
  (``GATE_9_STAGE2_PROTOCOL_DRAFT.md:96-99``: a failed finite/shape/symmetry/PSD
  validation is a *producer* failure, not a candidate rejection).  A record may
  carry a well-formed encoding of a NaN payload and the layout will accept the
  FORM.
* **That they came from a draw.**  The layout cannot distinguish a real draw's
  moments from synthetic fixtures, because that distinction is the value's origin
  and origin is not recorded in any file it validates.  That is precisely why this
  layout remains SYNTHETIC-ONLY and why a real draw still requires the separately
  reviewed WP8b integration.

Attempt history, precisely
--------------------------

``ATTEMPT.json`` retains the rejected attempts of a slot as well as the accepted
one, with fixed rejection codes drawn from a closed set
(``GATE_9_STAGE2_PROTOCOL_DRAFT.md:58-62``).  What is enforced: each retained
attempt carries its own fixed codes from that set, the list is duplicate-free, a
rejected attempt cannot carry an empty code list, an accepted one cannot carry any
code, rejected attempts are numbered strictly below the accepted attempt, and the
index binds the ledger's bytes, content hash, disposition and both counts.

What is NOT enforced, and is not claimed: that this history is COMPLETE.  A
layout cannot tell whether attempt 3 was rejected, accepted and superseded by a
later re-draw, or never made; only the generator's own screening loop knows that,
and the protocol's rule that the first satisfying attempt is accepted
(``GATE_9_STAGE2_PROTOCOL_DRAFT.md:51-56``) is enforced there.  An empty history
is therefore valid -- it is the truthful record of an attempt accepted at attempt
0 -- and this layout does not pretend otherwise.  Likewise the fixed codes are
validated as MEMBERS of the generator's enumerated set
(``stage2_generator.py:258-264``), not recomputed: which code an attempt earned
is the screening loop's output, and re-deriving it here would mean re-running the
feasibility count.

SYNTHETIC-ONLY
--------------

This layout is SYNTHETIC-ONLY and is **not** production ready.  Every fixture value
is synthetic, no draw is performed, and a real drawn instance still requires the
separately reviewed WP8b integration plus an owner-approved non-synthetic WP5b
release path that does not exist in this repository
(``stage2_instance_preparation.py:400-466,766-767``).  Passing every check below
says the layout is complete and self-consistent; it does not say any instance has
been drawn, accepted, or is fit to publish.

The boundary matters for the reports that follow: WP8b must not describe this
package as having "semantically validated" a drawn instance.  What it has done
is established that an instance directory is exactly the canonical layout, that
nothing in it has been altered since it was written, and that its three records
agree about which instance they are.  Whether the numbers in it are correct is
the protocol's acceptance gate, not this package's claim.

The binding order, and why it is not circular
---------------------------------------------

WP5's writer refuses ``MANIFEST.json`` as a payload name
(``research/g9/stage2_generation_writer.py:183,228``), so a slot cannot be one
writer manifest containing a generation manifest.  The layout is therefore three
writer directories:

```
research/g9/stage2_instances/stage2_NN/
    generation/                      <- written by WP5 write_generation
        MANIFEST.json                <- WP5 manifest, write-once commitment
        ATTEMPT.json                 <- retained-attempt ledger (protocol:58-62)
        GENERATION.json              <- the drawn instance's own record
        returns.f64.le.row_major     <- 249x20 little-endian binary64 doubles
    instance/                        <- written by WP5 write_generation
        MANIFEST.json                <- WP5 manifest over PREPARED.json
        PREPARED.json                <- the WP5b prepared record, verbatim
    meta/                            <- written by WP5 write_generation
        MANIFEST.json                <- WP5 manifest over INSTANCE.json
        INSTANCE.json                <- the per-instance index (this layout)
```

Three writer directories rather than two plus a hand-written file, because WP5's
writer is the *reviewed* atomic promotion: it fsyncs every file, fsyncs every
directory and refuses to merge into an existing target
(``research/g9/stage2_generation_writer.py:120-152,236-257``).  The index is a
file like any other and wants the same discipline; re-implementing promotion for
it would duplicate a reviewed boundary for no gain.

``INSTANCE.json`` is written LAST, so it can name both other manifests' content
hashes without any hash depending on itself.  Its own content hash is returned
in the write receipt and is what an owner approval and the WP8 bundle bind
(``WP8_PRODUCTION_BUNDLE_DESIGN.md:89-99``).  Nothing in the generation has to
name the manifest that commits to it.

Only the slot directory itself is promoted by this module, with WP5's own
staging-and-rename discipline, and it is refused if it exists at all -- so an
instance is written once and is never merged, overwritten or partially updated.

The refusal posture is fail-closed at every boundary: an unknown slot, an
unknown or extra member, a name that is not a canonical relative path, a
non-lowercase hash, a size that disagrees with the bytes, a payload whose hash
disagrees with its declared hash, a drifted seed commitment, a status outside
the accepted set -- each is a typed ``LayoutError``, never a warning, never a
default, and never a partially written directory.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, Mapping, Sequence

from research.g9 import stage2_generation_writer as _writer
from research.g9 import stage2_generator as _generator
from research.g9 import stage2_instance_preparation as _preparation


ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Typed refusal and the scalar guards
# ---------------------------------------------------------------------------

class LayoutError(ValueError):
    """Typed refusal: malformed layout, unsafe member, or failed promotion."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise LayoutError(message)


def _slot_int(value: object) -> int:
    """Accept a protocol slot number: an int, not a bool, in 1..5.

    The type test and the range test are separate statements on purpose.
    ``1 <= True <= 5`` is True, so a bool would pass a range-only guard; and a
    mutant that drops the range test alone must still be caught, which only a
    fixture passing slot ``6`` distinguishes.
    """
    _require(type(value) is int, "slot must be an int")
    _require(1 <= value <= SLOT_COUNT, "slot must be in 1..5")
    return value


def _attempt_int(value: object) -> int:
    """Accept a protocol attempt number: an int, not a bool, in 0..127.

    ``0 <= True <= 127`` is True, so the type test is not redundant here either.
    """
    _require(type(value) is int, "attempt must be an int")
    _require(0 <= value <= _generator.MAX_ATTEMPT, "attempt must be in 0..127")
    return value


def _non_empty_string(value: object, label: str) -> str:
    """Accept a non-empty exact ``str``.

    The exact-type test is load-bearing and NOT redundant with the truth test: a
    non-empty ``str`` SUBCLASS evaluates like a ``str`` but is a different type,
    and ``json.dumps`` would silently render it as a plain string.  Accepting one
    would mean the record's own key-set and schema checks see a value the builder
    never actually validated.
    """
    _require(type(value) is str, f"{label} must be a str")
    _require(bool(value), f"{label} must be a non-empty string")
    return value


def _count_int(value: object, label: str) -> int:
    """Accept a non-negative exact ``int``; a bool is not a count."""
    _require(type(value) is int, f"{label} must be an int")
    _require(value >= 0, f"{label} must be non-negative")
    return value


def _bytes_sha256(payload: object, label: str) -> str:
    """Hash a payload that must be exact ``bytes``.

    The type check lives here, at the one place a payload becomes a hash, because
    ``hashlib.sha256`` on a ``str`` raises a raw ``TypeError`` ("Strings must be
    encoded before hashing") that is not this module's typed refusal.  Refusing it
    in ``write_instance`` only would leave ``build_generation_payload`` reachable
    with a ``str``, which is the same leak one call earlier.
    """
    _require(type(payload) is bytes, f"{label} payload must be bytes")
    return hashlib.sha256(payload).hexdigest()


def _sha(value: object, label: str) -> str:
    """Accept a lowercase 64-character hexadecimal SHA-256.

    Three separate statements, each separately testable: dropping the length test
    still refuses ``"zz"``, dropping the character test still refuses ``"a"*64``
    in upper case, and dropping the type test still refuses ``None``.  A single
    combined expression would leave each of those mutants unobservable.
    """
    _require(type(value) is str, f"{label} must be a str")
    _require(len(value) == 64, f"{label} must be exactly 64 characters")
    _require(not set(value) - frozenset("0123456789abcdef"),
             f"{label} must be a lowercase SHA-256")
    return value


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                          allow_nan=False).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise LayoutError("record is not canonical JSON") from exc


def _content_sha256(payload: Mapping[str, Any]) -> str:
    """Hash a record with its own content hash removed.

    Identical to WP5's ``_content_sha256``
    (``research/g9/stage2_generation_writer.py:83-86``), so a WP8d record and a
    WP5 manifest use ONE content-hash convention rather than two.
    """
    body = dict(payload)
    body.pop("content_sha256", None)
    return hashlib.sha256(_canonical(body)).hexdigest()


# ---------------------------------------------------------------------------
# The canonical layout
# ---------------------------------------------------------------------------

#: The per-instance input-manifest location fixed by the protocol
#: (``GATE_9_STAGE2_PROTOCOL_DRAFT.md:220-222``).
INSTANCE_ROOT = "research/g9/stage2_instances"

#: The five canonical slots in protocol order
#: (``GATE_9_STAGE2_PROTOCOL_DRAFT.md:51-53``).  The protocol writes them
#: ``stage2_01``..``stage2_05``; the slot NUMBER is 1..5 and is what the U-08
#: commitment is derived from (``stage2_generator.py:107-115``).
SLOT_NAMES = ("stage2_01", "stage2_02", "stage2_03", "stage2_04", "stage2_05")
SLOT_COUNT = 5

#: The three fixed subdirectory names of a slot directory.
GENERATION_DIR_NAME = "generation"
PREPARED_DIR_NAME = "instance"
META_DIR_NAME = "meta"

#: The per-instance index: the one member this layout names itself.
INDEX_NAME = "INSTANCE.json"

#: The generation members, excluding WP5's own manifest.
ATTEMPT_NAME = "ATTEMPT.json"
GENERATION_NAME = "GENERATION.json"
RETURN_MATRIX_NAME = "returns.f64.le.row_major"

#: The U-09 return matrix is exactly 249x20 little-endian binary64 doubles in
#: C order (``GATE_9_STAGE2_PROTOCOL_DRAFT.md:87-104``;
#: ``stage2_generator.py:30,330``), so its byte length is fixed and is refused
#: otherwise: a resized or truncated matrix is not the drawn instance.
RETURN_ROWS = 249
ASSET_COUNT = 20
RETURN_MATRIX_BYTES = RETURN_ROWS * ASSET_COUNT * 8
RETURN_MATRIX_ENCODING = "binary64_le"

#: WP5's own reserved name and staging prefix, reused unchanged
#: (``stage2_generation_writer.py:45-46``).
MANIFEST_NAME = _writer.MANIFEST_NAME
STAGING_PREFIX = _writer.STAGING_PREFIX

#: The exact member set of each fixed directory.
GENERATION_MEMBERS = (ATTEMPT_NAME, GENERATION_NAME, RETURN_MATRIX_NAME, MANIFEST_NAME)
PREPARED_MEMBERS = ("PREPARED.json", MANIFEST_NAME)
META_MEMBERS = (INDEX_NAME, MANIFEST_NAME)
SLOT_MEMBERS = (GENERATION_DIR_NAME, META_DIR_NAME, PREPARED_DIR_NAME)

#: WP5's schema and key sets, bound here so a layout can never drift from the
#: writer that promotes it (``stage2_generation_writer.py:44-55``).
WRITER_SCHEMA = _writer.SCHEMA
WRITER_MANIFEST_KEYS = frozenset(_writer.MANIFEST_KEYS)
WRITER_ENTRY_KEYS = frozenset(_writer.ENTRY_KEYS)

#: WP5's scope statement, restated so a scientific output smuggled into any
#: member is refused by name (``stage2_generation_writer.py:198,215-216``).
SCOPE_STATEMENT = "intentionally absent"

#: The only prepared-record status this layout will accept.  Enumerating the
#: status set rather than accepting any non-empty string is what makes "status
#: drift" a refusal instead of a silent pass.  The repository's WP5b is
#: deliberately synthetic-only (``stage2_instance_preparation.py:766-767``), so
#: this is the only status a real draw can legitimately reach today; the owner's
#: default 2 (a separately reviewed non-synthetic release path) does not exist
#: yet, and this module does not anticipate its status string.
PREPARED_STATUS = "prepared_synthetic_only"
ACCEPTED_STATUSES = (PREPARED_STATUS,)

#: The two independent U-08 streams a slot/attempt draws from
#: (``GATE_9_STAGE2_PROTOCOL_DRAFT.md:73``; ``stage2_generator.py:33``).
PURPOSES = ("returns", "sectors")

_SLOT_RE = re.compile(r"stage2_(0[1-5])\Z")
_COMPONENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


# ---------------------------------------------------------------------------
# Slots and member names
# ---------------------------------------------------------------------------

def slot_name(slot: object) -> str:
    """Map a protocol slot number to its canonical directory name."""
    return SLOT_NAMES[_slot_int(slot) - 1]


def slot_number(name: object) -> int:
    """Map a canonical slot directory name back to its protocol slot number."""
    _require(type(name) is str, "slot name must be a str")
    match = _SLOT_RE.fullmatch(name)
    _require(match is not None, f"slot name is not one of {SLOT_NAMES}")
    return int(match.group(1))


def slot_dir(slot: object, *, root: Path | str = ROOT) -> Path:
    """The canonical instance directory of one slot, under ``root``."""
    return Path(root) / INSTANCE_ROOT / slot_name(slot)


def _component(name: object, label: str) -> str:
    """Accept one plain path component and nothing else.

    WP5's writer already refuses separators, ``..``, ``.``, absolute paths, NUL
    and empty components (``stage2_generation_writer.py:89-104``), so this is not
    a re-check of those: it is the one thing the writer does NOT fix, that the
    name is one of *this layout's* fixed names.
    """
    _non_empty_string(name, label)
    _require(_COMPONENT_RE.fullmatch(name) is not None,
             f"{label} is not a plain component: {name}")
    return name


def generation_member(name: object) -> str:
    """Validate one generation member name and return it unchanged."""
    safe = _component(name, "generation member name")
    _require(safe in GENERATION_MEMBERS, f"unknown generation member: {safe}")
    return safe


def prepared_member(name: object) -> str:
    """Validate one prepared-sidecar member name and return it unchanged."""
    safe = _component(name, "prepared member name")
    _require(safe in PREPARED_MEMBERS, f"unknown prepared member: {safe}")
    return safe


def meta_member(name: object) -> str:
    """Validate one meta-sidecar member name and return it unchanged."""
    safe = _component(name, "meta member name")
    _require(safe in META_MEMBERS, f"unknown meta member: {safe}")
    return safe


# ---------------------------------------------------------------------------
# ATTEMPT.json -- the retained-attempt ledger
# ---------------------------------------------------------------------------

ATTEMPT_SCHEMA = "decisions_os/g9_wp8d_drawn_attempt/v2"
#: The superseded revision of this schema.  Named so the refusal message can say
#: what a caller holding v1 bytes has, and so ``_require`` can say "v1 cannot
#: express rejection codes or rejected history" instead of a bare "schema
#: mismatch".  v1 is NOT accepted: the protocol retains EVERY attempt
#: (``GATE_9_STAGE2_PROTOCOL_DRAFT.md:58-62``), so a v1 record -- which can
#: represent neither a rejection code nor a rejected sibling -- is structurally
#: unable to satisfy the protocol and is refused rather than migrated.
ATTEMPT_SCHEMA_V1 = "decisions_os/g9_wp8d_drawn_attempt/v1"
ATTEMPT_KEYS = frozenset({
    "schema", "slot", "attempt", "disposition", "rejection_codes",
    "rejected_attempt_history", "sector_partition_sha256", "feasible_count",
    "seed_commitments", "scope", "content_sha256",
})
SEED_COMMITMENT_KEYS = frozenset({"material_ascii", "material_sha256", "seed_uint128"})
UINT128_LIMIT = 1 << 128

#: A retained attempt is either the one this record IS, or one that was screened
#: and refused.  Naming the disposition explicitly is what lets the two cases be
#: validated by DIFFERENT rules: an accepted attempt must carry an empty
#: rejection-code list, an attempted-but-rejected one must carry at least one.
#: Schema v1 had no such field, so "rejected" was not representable at all and
#: every record read as accepted.
DISPOSITION_ACCEPTED = "accepted"
DISPOSITION_REJECTED = "rejected"
ATTEMPT_DISPOSITIONS = (DISPOSITION_ACCEPTED, DISPOSITION_REJECTED)

#: The closed set of fixed rejection codes this layout will accept.  These are
#: NOT invented here and NOT derived from any draw: they are the generator's own
#: enumerated outcomes, read from the reviewed contract
#: (``stage2_generator.py:258-264``) rather than restated from memory, so a future
#: generator revision that adds or retires a code is inherited here instead of
#: silently diverging.  The protocol requires "one or more fixed rejection codes"
#: (``GATE_9_STAGE2_PROTOCOL_DRAFT.md:58-60``); "fixed" means exactly this: a
#: closed, enumerable set, not a free string.
#:
#: The ORDER is the generator's order of appending (``stage2_generator.py:259-264``)
#: and is not itself validated; the code SET is what is validated.
#:
#: Note what this set does NOT contain: no QUBO energy, minimum, tie, label, rate
#: or hypothesis outcome is representable as a code, per the protocol's explicit
#: exclusion at ``GATE_9_STAGE2_PROTOCOL_DRAFT.md:61-62``.
REJECTION_CODE_SET = frozenset({
    "partition_matches_stage1",
    "partition_matches_earlier_accepted",
    "feasible_set_below_100",
})

#: One retained rejected attempt, as it appears inside a history list.  A closed
#: key set, so a scientific outcome cannot be smuggled into the ledger under a
#: new key name.  ``sector_partition_sha256`` and ``feasible_count`` are the same
#: two fields the accepted record carries at top level; ``rejection_codes`` is the
#: "one or more fixed rejection codes" of the protocol.
HISTORY_ENTRY_KEYS = frozenset({
    "attempt", "rejection_codes", "sector_partition_sha256", "feasible_count",
})


def _u08_material(slot: int, attempt: int, purpose: str) -> str:
    """The exact U-08 ASCII seed material (``stage2_generator.py:112-115``)."""
    return (f"{_generator.PROTOCOL_PREFIX}|master={_generator.MASTER_SEED}"
            f"|slot={slot:02d}|attempt={attempt}|purpose={purpose}")


def _seed_commitments(slot: int, attempt: int) -> dict[str, dict[str, object]]:
    commitments: dict[str, dict[str, object]] = {}
    for purpose in PURPOSES:
        seed = _generator.stream_seed(slot, attempt, purpose)
        commitments[purpose] = {
            "material_ascii": seed.material_ascii,
            "material_sha256": seed.material_sha256,
            "seed_uint128": seed.seed_uint128,
        }
    return commitments


def _rejection_codes(codes: object, label: str) -> list[str]:
    """Validate a rejection-code list against the closed fixed set.

    Three separately testable requirements, each its own statement so that
    dropping one leaves a mutant that a fixture distinguishes:

    * ``list`` exactly -- a ``tuple``, a ``str`` and a ``dict`` are all
      rejected, and a ``str`` in particular would otherwise iterate into a list
      of single characters that every membership test passes when the set is
      small;
    * every member drawn from :data:`REJECTION_CODE_SET`, so a code is a FIXED
      code rather than a free string;
    * no duplicates, because "one or more fixed rejection codes"
      (``GATE_9_STAGE2_PROTOCOL_DRAFT.md:58-60``) means a set of distinct codes
      and a repeat would silently double-count a rule in a retained ledger.

    There is deliberately **no length cap**.  An earlier revision had one, and the
    sweep proved it unobservable: with a closed 3-code set and duplicates already
    refused, the longest legal list is 3, so the cap could only ever fire on an
    input the duplicate check refuses first.  A guard no input can falsify is a
    guard that cannot be tested, and an untestable guard is an unverified claim --
    so it was removed rather than kept and excused.  Bound the field by the size
    of :data:`REJECTION_CODE_SET` instead, which is what actually bounds it.
    """
    _require(type(codes) is list, f"{label} must be a list")
    for code in codes:
        _require(type(code) is str, f"{label} must hold only strings")
        _require(code in REJECTION_CODE_SET,
                 f"{label} holds a code outside the fixed rejection set: {code}")
    _require(len(set(codes)) == len(codes), f"{label} repeats a rejection code")
    return list(codes)


def _disposition(disposition: object) -> str:
    """Accept only a declared attempt disposition."""
    _non_empty_string(disposition, "attempt disposition")
    _require(disposition in ATTEMPT_DISPOSITIONS,
             f"attempt disposition is not one of the declared dispositions: {disposition}")
    return disposition


def _require_disposition_codes(disposition: object, codes: Sequence[str], label: str) -> None:
    """Bind a disposition to its rejection-code list in both directions.

    Two statements, and BOTH are load-bearing.  An accepted attempt must carry
    no codes (otherwise a rejected attempt is recorded as accepted); a rejected
    attempt must carry at least one (otherwise it is retained with no reason,
    which the protocol forbids -- "one or more fixed rejection codes").  Checking
    only the first direction leaves the second as a testable mutant, so the
    fixture exercises both.
    """
    if disposition == DISPOSITION_ACCEPTED:
        _require(not codes,
                 f"{label}: an accepted attempt must carry no rejection codes")
    else:
        _require(bool(codes),
                 f"{label}: a rejected attempt must carry at least one fixed rejection code")


def _rejected_history(entries: object, slot: int, accepted_attempt: int) -> list[dict[str, object]]:
    """Validate the retained rejected-attempt history for one slot.

    Ordering is enforced against the protocol's attempt-ordering rule rather than
    merely "ascending": a rejected attempt is retained only if it was screened
    BEFORE the accepted one.  The protocol considers attempts in increasing
    integer order and accepts the FIRST one that satisfies every rule
    (``GATE_9_STAGE2_PROTOCOL_DRAFT.md:51-56``), so a rejected attempt numbered
    at or after the accepted attempt could not have preceded it and is refused.
    This is what "accepted attempt ordering" means here: the history is a
    strictly increasing sequence below the accepted number, so the retained pair
    (history, accepted) determines the accepted attempt without ambiguity.

    Each entry carries no seed commitments.  They are not repeated per entry
    because they are a pure function of ``(slot, attempt, purpose)`` and are
    already re-derived for every attempt number by the accepted record's own
    commitment check plus this entry's attempt number -- restating them would
    add bytes that cannot disagree with the derivation.
    """
    _require(type(entries) is list, "rejected_attempt_history must be a list")
    previous = -1
    for entry in entries:
        _require(type(entry) is dict, "rejected attempt history entry must be an object")
        _require(set(entry) == HISTORY_ENTRY_KEYS,
                 "rejected attempt history entry has wrong key set")
        number = _attempt_int(entry["attempt"])
        _require(number > previous,
                 "rejected_attempt_history must be strictly increasing by attempt")
        _require(number < accepted_attempt,
                 "a retained rejected attempt must precede the accepted attempt")
        previous = number
        _sha(entry["sector_partition_sha256"],
             "rejected attempt sector partition sha256")
        _count_int(entry["feasible_count"], "rejected attempt feasible_count")
        codes = _rejection_codes(entry["rejection_codes"],
                                 f"rejected attempt {number} rejection_codes")
        _require_disposition_codes(DISPOSITION_REJECTED, codes,
                                   f"rejected attempt {number}")
    return [dict(entry) for entry in entries]


def build_attempt_record(*, slot: int, attempt: int, sector_partition_sha256: str,
                         feasible_count: int,
                         rejected_attempt_history: Sequence[Mapping[str, Any]] = (),
                         ) -> dict[str, object]:
    """Render the non-scientific retained-attempt ledger member.

    Every field is one the protocol already declares for a retained attempt
    (``GATE_9_STAGE2_PROTOCOL_DRAFT.md:58-62``): the slot, the attempt number,
    the derived seed commitments, the partition digest, the feasibility count,
    and one or more fixed rejection codes.  No QUBO energy, minimum, tie, label,
    rate or hypothesis outcome is representable here -- the key set is closed and
    the rejection codes are drawn from a closed fixed set.

    This is the record of the ACCEPTED attempt, so its ``disposition`` is
    necessarily ``accepted`` and its own ``rejection_codes`` is necessarily the
    empty list.  The rejected attempts of the same slot are retained in
    ``rejected_attempt_history``, each with its own fixed codes.  That split is
    what lets one builder produce both kinds of retained attempt: build the
    accepted record with the history attached, and render each rejected sibling
    with :func:`build_rejected_attempt_record`, which stamps the disposition and
    codes explicitly.

    The history is optional here and REQUIRED in a written instance: an empty
    history is the truthful case of an attempt accepted at attempt 0 with nothing
    rejected before it, so it cannot be refused as such.  That an accepted attempt
    carries no rejection codes is not asserted HERE but on the read side, in
    ``validate_attempt_record``: this builder hard-codes the disposition and
    hard-codes an empty code list, so checking the pair against each other here
    would be a tautology that no input could falsify.  ``build_rejected_attempt_record``
    is the entry point where the rejected disposition and its codes are caller
    supplied, and the check is live there.
    """
    _slot_int(slot)
    _attempt_int(attempt)
    _sha(sector_partition_sha256, "sector partition sha256")
    _count_int(feasible_count, "feasible_count")
    history = _rejected_history(rejected_attempt_history, slot, attempt)
    # An accepted attempt's own code list is empty BY CONSTRUCTION: it was not
    # rejected, so it has no code.  Written as a literal rather than validated,
    # because a caller cannot supply codes here at all.
    codes: list[str] = []
    record: dict[str, object] = {
        "schema": ATTEMPT_SCHEMA,
        "slot": slot,
        "attempt": attempt,
        "disposition": DISPOSITION_ACCEPTED,
        "rejection_codes": codes,
        "rejected_attempt_history": history,
        "sector_partition_sha256": sector_partition_sha256,
        "feasible_count": feasible_count,
        "seed_commitments": _seed_commitments(slot, attempt),
        "scope": SCOPE_STATEMENT,
    }
    record["content_sha256"] = _content_sha256(record)
    return record


def build_rejected_attempt_record(*, slot: int, attempt: int,
                                  sector_partition_sha256: str, feasible_count: int,
                                  rejection_codes: Sequence[str]) -> dict[str, object]:
    """Render one RETAINED REJECTED attempt, as the protocol requires retained.

    Schema v1 had no way to express this at all: a record either described an
    attempt or said nothing about why it was not used, so "every attempt is
    retained with its fixed rejection codes"
    (``GATE_9_STAGE2_PROTOCOL_DRAFT.md:58-60``) was unrepresentable.  This builder
    is what makes it representable, and it is deliberately NOT a flag on
    :func:`build_attempt_record`: a separate entry point makes the two dispositions
    impossible to confuse, and makes the mutation "flip the disposition to
    accepted" a refusal on an empty-code list rather than a silently accepted
    record.

    ``rejection_codes`` is handed to the validator UNCHANGED -- there is no
    ``list(...)`` coercion.  Coercing first would turn a bare string into a list
    of characters and a tuple into a list, so a caller passing the wrong
    container would reach the per-code checks instead of the container check and
    be refused with a misleading reason.  The protocol requires "one or more fixed
    rejection codes", so a list is what a caller owes.
    """
    _slot_int(slot)
    _attempt_int(attempt)
    _sha(sector_partition_sha256, "sector partition sha256")
    _count_int(feasible_count, "feasible_count")
    codes = _rejection_codes(rejection_codes, "rejected attempt rejection_codes")
    _require_disposition_codes(DISPOSITION_REJECTED, codes, "rejected attempt")
    record: dict[str, object] = {
        "schema": ATTEMPT_SCHEMA,
        "slot": slot,
        "attempt": attempt,
        "disposition": DISPOSITION_REJECTED,
        "rejection_codes": codes,
        "rejected_attempt_history": [],
        "sector_partition_sha256": sector_partition_sha256,
        "feasible_count": feasible_count,
        "seed_commitments": _seed_commitments(slot, attempt),
        "scope": SCOPE_STATEMENT,
    }
    record["content_sha256"] = _content_sha256(record)
    return record


def validate_attempt_record(record: object) -> dict[str, object]:
    """Validate an attempt ledger record and return a copy of it.

    The schema-string check names the superseded v1 revision explicitly, because
    the generic "schema mismatch" would be misleading for the actual failure a
    caller hits here: a v1 record is a record from the previous revision of this
    module, and it cannot express the protocol's rejection codes or rejected
    history at all.  Saying so is the difference between a diagnosable refusal
    and a mystery.
    """
    _require(type(record) is dict, "attempt record must be an object")
    _require(set(record) == ATTEMPT_KEYS, "attempt record has wrong key set")
    _require(record["schema"] != ATTEMPT_SCHEMA_V1,
             "this is a superseded v1 attempt record, which cannot express the "
             "protocol's fixed rejection codes or rejected-attempt history")
    _require(record["schema"] == ATTEMPT_SCHEMA, "attempt record schema mismatch")
    _require(record["scope"] == SCOPE_STATEMENT, "attempt record scope statement mismatch")
    slot = _slot_int(record["slot"])
    attempt = _attempt_int(record["attempt"])
    disposition = _disposition(record["disposition"])
    codes = _rejection_codes(record["rejection_codes"], "attempt rejection_codes")
    _require_disposition_codes(disposition, codes, "attempt record")
    # A REJECTED record cannot carry a rejected-attempt history: it has no later
    # accepted attempt to be the sibling of.  This is checked BEFORE the history is
    # validated, because the disposition rule is the stronger statement -- a
    # rejected record with a history is wrong regardless of whether the history's
    # own contents are ordered, so validating the history first would report a
    # detail instead of the real fault.
    history = record["rejected_attempt_history"]
    if disposition == DISPOSITION_REJECTED:
        _require(not history,
                 "a rejected attempt cannot itself carry a rejected-attempt history")
    _rejected_history(history, slot, attempt)
    _sha(record["sector_partition_sha256"], "attempt sector partition sha256")
    _count_int(record["feasible_count"], "feasible_count")
    commitments = record["seed_commitments"]
    _require(type(commitments) is dict, "seed_commitments must be an object")
    _require(set(commitments) == set(PURPOSES),
             "seed_commitments must cover exactly the two U-08 streams")
    for purpose in PURPOSES:
        entry = commitments[purpose]
        _require(type(entry) is dict, f"seed commitment {purpose} must be an object")
        _require(set(entry) == SEED_COMMITMENT_KEYS,
                 f"seed commitment {purpose} has wrong key set")
        expected = _generator.stream_seed(slot, attempt, purpose)
        # The material is RE-DERIVED, not merely shape-checked: it is ASCII with
        # a fixed layout, but a hand-edited material of the right shape would
        # otherwise pass.  Comparing against the derived material also subsumes a
        # separate shape check on the hash, because the hash is compared against
        # the derived hash directly.
        _require(entry["material_ascii"] == _u08_material(slot, attempt, purpose),
                 f"seed commitment {purpose} is not the U-08 material for this slot/attempt")
        _require(entry["material_sha256"] == expected.material_sha256,
                 f"seed commitment {purpose} material sha256 is not the U-08 derivation")
        _count_int(entry["seed_uint128"], f"seed commitment {purpose} seed_uint128")
        _require(entry["seed_uint128"] < UINT128_LIMIT,
                 f"seed commitment {purpose} seed_uint128 is not in [0, 2**128)")
        _require(entry["seed_uint128"] == expected.seed_uint128,
                 f"seed commitment {purpose} seed_uint128 is not the U-08 derivation")
    _require(record["content_sha256"] == _content_sha256(record),
             "attempt record content hash mismatch")
    return dict(record)


# ---------------------------------------------------------------------------
# GENERATION.json -- the drawn instance's own record
# ---------------------------------------------------------------------------

GENERATION_SCHEMA = "decisions_os/g9_wp8d_drawn_generation/v2"
GENERATION_SCHEMA_V1 = "decisions_os/g9_wp8d_drawn_generation/v1"
GENERATION_KEYS = frozenset({
    "schema", "slot", "attempt", "instance_id", "return_matrix_sha256",
    "n_assets", "n_rows", "moment_summary", "implementation_record", "scope",
    "content_sha256",
})

#: Canonical binary64 scalar encoding name for the two U-09 moments.
#:
#: This is NOT the return matrix's ``binary64_le``.  The matrix is a 249x20 array
#: stored as raw little-endian doubles, which has a byte order to fix.  ``mu_new``
#: and ``Sigma_new`` are recorded inside a JSON record, and JSON has no byte
#: order of its own -- what JSON needs is a spelling whose text is independent of
#: how the host stores a float.  The generator already produces exactly such a
#: spelling: ``float(value).hex()``, CPython's shortest round-tripping C99 ``%a``
#: form, which is exact (it round-trips to the same binary64), platform
#: independent, and locale independent
#: (``stage2_generator.py:337-338``).  So the encoding is DERIVED FROM THE
#: REVIEWED GENERATOR CONTRACT, not chosen here.
#:
#: The matrix keeps ``binary64_le`` and the moments keep ``binary64_hex``: they
#: are different storage questions, and conflating them is exactly the kind of
#: silent drift this module exists to prevent.
MU_NEW_DIM = ASSET_COUNT
SIGMA_NEW_ROWS = ASSET_COUNT
SIGMA_NEW_COLS = ASSET_COUNT

#: The declared name of the scalar encoding, recorded in every moment block so a
#: reader never has to infer it from the values' spelling.  Deliberately distinct
#: from :data:`RETURN_MATRIX_ENCODING` ("binary64_le") because these are two
#: different encodings, and a reader that assumed they matched would be wrong.
MU_NEW_ENCODING = "binary64_hex_c99"

#: The number of doubles in the covariance, used to size the Sigma digest.
SIGMA_NEW_COUNT = SIGMA_NEW_ROWS * SIGMA_NEW_COLS

#: One recorded moment block.  ``sha256`` is over the canonical ENCODED FORM --
#: the exact lower-case hex text, ASCII, in row-major order -- not over a
#: re-decoded array.  Hashing the encoding makes the digest a function of the
#: bytes a reviewer can read, so the digest is reproducible by anyone with the
#: record and no float-parsing tool.
MOMENT_SUMMARY_KEYS = frozenset({"encoding", "shape", "sha256", "values"})
#: The exact spelling CPython's ``float.hex()`` emits, and therefore the exact
#: spelling the generator produces (``stage2_generator.py:337-338``):
#: ``[sign] 0x <hex integer> [ . <hex fraction> ] p [sign] <decimal exponent>``.
#:
#: All three parts are REQUIRED, which is what makes this a check on the canonical
#: encoding rather than a loose numeric-looking pattern: ``0x1.0`` (no exponent),
#: ``1.5`` (no radix prefix) and ``0X1P+0`` (upper case, which ``float.hex()``
#: never emits) are all refused.  ``nan``/``inf``/``-inf`` are likewise refused,
#: because the generator validates finiteness before it emits anything
#: (``stage2_generator.py:288-297``) and so can never produce them -- but note
#: what that means: a hex payload *denoting* a NaN (``0x1.8p+1025``) is still
#: well formed and is accepted.  See the module docstring.
_MOMENT_HEX = re.compile(r"-?0x[0-9a-f]+\.[0-9a-f]+p[+-][0-9]+\Z")


def _moment_values(values: object, count: int, label: str) -> list[str]:
    """Validate a sequence of canonical binary64 scalar encodings.

    Structural validation only, and the limit is stated plainly:

    * a ``list`` or ``tuple`` of exactly ``count`` non-empty exact ``str``;
    * each in the C99 hexadecimal-float grammar the generator emits, which is
      what makes the text canonical and platform independent.

    Both container types are accepted because the generator's own fields are
    tuples (``ReturnDraw.mu_hex``, ``ReturnDraw.sigma_hex``,
    ``stage2_generator.py:308-309``) and a layout that refused them would refuse
    the reviewed generator's real output.  A bare ``str`` is excluded even though
    it is a sequence, because it would otherwise be walked one character at a
    time.  That exclusion is a single ``isinstance`` test rather than an extra
    ``type(values) is not str`` conjunct: an earlier revision spelled it as the
    conjunct, and the sweep proved the ``isinstance`` half alone is
    indistinguishable from the pair -- ``str`` is not a ``list`` or a ``tuple``,
    so the second conjunct can never be the reason a refusal fires.  The read side
    (:func:`_validate_moment_block`) additionally requires exactly ``list``,
    because a record arriving from JSON is always a list and anything else there
    is drift.

    What is NOT done here is ``float(text)``.  This module never imports NumPy
    and never performs a scientific step, so it does not decode the values to
    check they are finite, symmetric or PSD: those are the generator's
    post-conditions (``stage2_generator.py:288-297,329``), and re-checking them
    here would be a scientific step, not a layout check.  So a record can
    carry a well-formed encoding of a NaN payload, and the layout will accept the
    FORM while making no claim about the VALUE.  See the module docstring's
    "What is and is not validated" section.
    """
    _require(isinstance(values, (list, tuple)),
             f"{label} must be a list or tuple of encoded values")
    _require(len(values) == count,
             f"{label} must hold exactly {count} encoded values, not {len(values)}")
    for value in values:
        _require(type(value) is str, f"{label} must hold only strings")
        _require(bool(value), f"{label} must hold non-empty strings")
        _require(_MOMENT_HEX.match(value) is not None,
                 f"{label} holds a value that is not canonical binary64 hex: {value}")
    return list(values)


def _moment_block(values: list[str], shape: tuple[int, ...], label: str) -> dict[str, object]:
    """Wrap validated encoded values with their shape and encoding digest."""
    text = "".join(values).encode("ascii")
    return {
        "encoding": MU_NEW_ENCODING,
        "shape": list(shape),
        "sha256": hashlib.sha256(text).hexdigest(),
        "values": values,
    }


def build_generation_record(*, slot: int, attempt: int, instance_id: str,
                            return_matrix_sha256: str,
                            implementation_record_content_sha256: str,
                            mu_new: Sequence[str], sigma_new: Sequence[Sequence[str]],
                            ) -> dict[str, object]:
    """Render the drawn-generation member.

    ``return_matrix_sha256`` is the generator's own
    ``return_matrix_sha256_le_f64_row_major`` over the little-endian C-order
    doubles (``stage2_generator.py:330-338``), which is exactly what the matrix
    member holds.  ``implementation_record_content_sha256`` is WP5's identity
    and is the same value the writer binds into ``MANIFEST.json``
    (``stage2_generation_writer.py:163,195``), so this member cannot name a
    different implementation record than the manifest that promotes it.

    ``mu_new`` and ``sigma_new`` are the canonical binary64 encodings the
    protocol requires the generated instance to record
    (``GATE_9_STAGE2_PROTOCOL_DRAFT.md:101-104``), in exactly the spelling the
    reviewed generator produces (``stage2_generator.py:337-338``): ``mu_new`` is
    ``ReturnDraw.mu_hex`` and ``sigma_new`` is ``ReturnDraw.sigma_hex``, row
    major.  Schema v1 had no field for either, so the requirement was
    unrepresentable.

    The caller supplies the encodings rather than this module computing them.
    That is deliberate and is the module's stated boundary: turning 249x20
    doubles into ``mu_new`` and ``Sigma_new`` is the U-09 computation itself, a
    scientific step this module may not take and has no NumPy to take it with.
    What this module guarantees is that whatever encodings are supplied are of
    the canonical form, of the exact protocol shape, and are committed to by a
    digest and by the record's own content hash.
    """
    _slot_int(slot)
    _attempt_int(attempt)
    _non_empty_string(instance_id, "instance_id")
    _sha(return_matrix_sha256, "return matrix sha256")
    _sha(implementation_record_content_sha256, "implementation record content sha256")
    # ``_moment_values`` owns the container, length, element-type and canonical-form
    # checks for both moments, including the ``str``-is-not-a-sequence exclusion and
    # the list-or-tuple tolerance the generator's own tuples require.
    mu_values = _moment_values(mu_new, MU_NEW_DIM, "mu_new")
    _require(isinstance(sigma_new, (list, tuple)),
             "Sigma_new must be a list or tuple of rows")
    sigma_rows = []
    for row_index, row in enumerate(sigma_new):
        sigma_rows.append(_moment_values(row, SIGMA_NEW_COLS,
                                         f"Sigma_new row {row_index}"))
    # These checks are deliberately the guards on a BUILDER that never returns a
    # malformed record: build_generation_record is the only producer of this
    # schema, so its refusals are the acceptance boundary.  validate_generation_record
    # re-checks them independently, and the two are not redundant -- one guards the
    # builder's inputs, the other guards a record arriving from disk.
    _require(len(sigma_rows) == SIGMA_NEW_ROWS,
             f"Sigma_new must hold exactly {SIGMA_NEW_ROWS} rows")
    record: dict[str, object] = {
        "schema": GENERATION_SCHEMA,
        "slot": slot,
        "attempt": attempt,
        "instance_id": instance_id,
        "return_matrix_sha256": return_matrix_sha256,
        "n_assets": ASSET_COUNT,
        "n_rows": RETURN_ROWS,
        "moment_summary": {
            "mu_new": _moment_block(mu_values, (MU_NEW_DIM,), "mu_new"),
            "sigma_new": _moment_block([value for row in sigma_rows for value in row],
                                       (SIGMA_NEW_ROWS, SIGMA_NEW_COLS), "sigma_new"),
        },
        "implementation_record": implementation_record_content_sha256,
        "scope": SCOPE_STATEMENT,
    }
    record["content_sha256"] = _content_sha256(record)
    return record


def _validate_moment_block(block: object, shape: tuple[int, ...], label: str
                           ) -> dict[str, object]:
    """Validate one recorded moment block and return a copy of it.

    The digest is RECOMPUTED and compared, not merely shape-checked.  That is
    what makes the block tamper-evident on its own: an editor who changes one
    encoded value and re-seals the record's ``content_sha256`` still cannot make
    the block's own ``sha256`` agree, so the value cannot be altered without also
    supplying a new digest -- at which point the record's content hash changes,
    the WP5 manifest changes, and the index that names the manifest changes too.
    Two independent commitments, neither of which the other can repair.
    """
    _require(type(block) is dict, f"{label} must be an object")
    _require(set(block) == MOMENT_SUMMARY_KEYS, f"{label} has wrong key set")
    _require(block["encoding"] == MU_NEW_ENCODING,
             f"{label} encoding must be the canonical {MU_NEW_ENCODING}")
    declared = block["shape"]
    _require(type(declared) is list, f"{label} shape must be a list")
    # ``declared`` is known to be a list of unknown element types at this point, so
    # the shape test is written as a length comparison against ``shape`` rather
    # than a tuple comparison.  Two reasons, both load-bearing: comparing tuples
    # would need the element type checked first, and a scalar element -- say the
    # shape ``20`` instead of ``[20]`` -- makes ``tuple(20)`` raise a raw
    # ``TypeError`` instead of this module's typed refusal.  A length test cannot
    # raise, and a scalar shape is still refused, just as a scalar.
    _require(len(declared) == len(shape),
             f"{label} shape must be the protocol shape {list(shape)}")
    _require(all(type(item) is int for item in declared),
             f"{label} shape must hold only integers")
    # The ELEMENT TYPE is checked before the element VALUE, and both the exactness
    # of the type test and the order of the two statements are load-bearing:
    # ``isinstance(True, int)`` is True and ``True == 1``, so a ``bool`` would pass
    # an ``isinstance`` test and then compare equal to ``1`` in a 2-D shape,
    # surfacing as a "wrong shape" instead of a "wrong type".  ``type(item) is int``
    # refuses the bool, and checking types first means the refusal names the real
    # fault.
    for item, expected in zip(declared, shape):
        _require(item == expected,
                 f"{label} shape must be the protocol shape {list(shape)}")
    # No ``_sha(block["sha256"], ...)`` here, and the omission is deliberate.  The
    # block's digest is RECOMPUTED from the canonical encoding and compared a few
    # lines below, so a malformed digest is already refused by that comparison --
    # and it is refused with the digest-mismatch message, which names the actual
    # fault.  An earlier revision ran ``_sha`` first as well; the sweep proved the
    # standalone ``_sha`` call unobservable, because no input can make the format
    # check fire without the comparison firing too.  The comparison is the
    # stronger guard, so the weaker one was removed rather than exempted.
    count = shape[0] if len(shape) == 1 else shape[0] * shape[1]
    # Exactly ``list`` on the READ side, where the builder's tuple tolerance does
    # not apply: a record parsed from JSON always holds lists, so anything else
    # here is drift rather than a caller's container choice.
    _require(type(block["values"]) is list,
             f"{label} values must be a list in a record read from disk")
    values = _moment_values(block["values"], count, f"{label} values")
    _require(block["sha256"] == hashlib.sha256("".join(values).encode("ascii")).hexdigest(),
             f"{label} sha256 does not match its own canonical encoding")
    return dict(block)


def validate_generation_record(record: object) -> dict[str, object]:
    """Validate a drawn-generation record and return a copy of it.

    As in the attempt record, the superseded v1 revision is refused by name: a v1
    record has no ``moment_summary`` key at all, so it cannot represent the
    canonical ``mu_new``/``Sigma_new`` encodings the protocol requires
    (``GATE_9_STAGE2_PROTOCOL_DRAFT.md:101-104``).
    """
    _require(type(record) is dict, "generation record must be an object")
    _require(set(record) == GENERATION_KEYS, "generation record has wrong key set")
    _require(record["schema"] != GENERATION_SCHEMA_V1,
             "this is a superseded v1 generation record, which cannot express the "
             "protocol's canonical binary64 mu_new and Sigma_new encodings")
    _require(record["schema"] == GENERATION_SCHEMA, "generation record schema mismatch")
    _require(record["scope"] == SCOPE_STATEMENT, "generation record scope statement mismatch")
    _slot_int(record["slot"])
    _attempt_int(record["attempt"])
    _non_empty_string(record["instance_id"], "generation instance_id")
    _sha(record["return_matrix_sha256"], "return matrix sha256")
    _sha(record["implementation_record"], "implementation record content sha256")
    _require(type(record["n_assets"]) is int, "n_assets must be an int")
    _require(record["n_assets"] == ASSET_COUNT, f"n_assets must be the fixed {ASSET_COUNT}")
    _require(type(record["n_rows"]) is int, "n_rows must be an int")
    _require(record["n_rows"] == RETURN_ROWS, f"n_rows must be the fixed {RETURN_ROWS}")
    summary = record["moment_summary"]
    _require(type(summary) is dict, "moment_summary must be an object")
    _require(set(summary) == frozenset({"mu_new", "sigma_new"}),
             "moment_summary must hold exactly mu_new and Sigma_new")
    # Sigma_new is stored FLAT and row-major, with its shape declared separately.
    # Storing it as a nested list would put the row structure in the values and the
    # row count in the shape, so the two could disagree; flattening and validating
    # the declared shape against the protocol's 20x20 makes one source of truth.
    _validate_moment_block(summary["mu_new"], (MU_NEW_DIM,), "mu_new")
    _validate_moment_block(summary["sigma_new"], (SIGMA_NEW_ROWS, SIGMA_NEW_COLS),
                           "sigma_new")
    _require(record["content_sha256"] == _content_sha256(record),
             "generation record content hash mismatch")
    return dict(record)


# ---------------------------------------------------------------------------
# INSTANCE.json -- the per-instance index
# ---------------------------------------------------------------------------

INSTANCE_SCHEMA = "decisions_os/g9_wp8d_drawn_instance_index/v3"
INSTANCE_SCHEMA_V2 = "decisions_os/g9_wp8d_drawn_instance_index/v2"
INSTANCE_KEYS = frozenset({
    "schema", "slot", "slot_name", "attempt", "instance_id", "prepared_record",
    "generation", "attempt_ledger", "moments", "implementation_record", "status",
    "scope", "content_sha256",
})
#: The index's reference to the retained-attempt ledger.  Without it the ledger is
#: only self-consistent: nothing outside ``generation/ATTEMPT.json`` committed to
#: its accepted attempt number, its rejected-attempt history, or the digests of
#: the recorded moments, so an attacker could rewrite the ledger, re-seal the
#: generation manifest and rewrite the index to match.  This block binds all
#: three, so the ledger is committed from outside the directory it lives in.
ATTEMPT_REF_KEYS = frozenset({
    "path", "sha256", "content_sha256", "attempt", "disposition",
    "rejection_code_count", "rejected_attempt_history_count",
})
#: The index's own summary of the recorded U-09 moments.  The VALUES are not
#: repeated here -- the generation record holds them, and duplicating 420 encoded
#: strings into a second file would give the pair two places to disagree without
#: adding a commitment.  What the index binds is the digest of each block, so a
#: changed moment value changes this file too, and the two records cannot
#: disagree about which moments were recorded.
MOMENT_REF_KEYS = frozenset({"mu_new_sha256", "sigma_new_sha256"})
#: The index's reference to the prepared sidecar.  It binds the prepared record's
#: OWN bytes AND the WP5 manifest that commits to it, by file bytes and by
#: content hash -- the same pair the generation reference uses.  A prior revision
#: (schema v1) bound only the prepared record's bytes, so appending a single
#: whitespace byte to ``instance/MANIFEST.json`` still verified even though the
#: notes claimed the index bound "both manifests' bytes and content hashes".
PREPARED_REF_KEYS = frozenset({
    "path", "sha256", "status", "non_synthetic_supported",
    "manifest_sha256", "manifest_content_sha256",
})
GENERATION_REF_KEYS = frozenset({"path", "manifest_sha256", "manifest_content_sha256"})

#: Deliberately NOT in the index: the meta manifest's own bytes.
#:
#: ``meta/MANIFEST.json`` commits to ``meta/INSTANCE.json``, so the index cannot
#: also commit to the manifest's bytes: the manifest's content hash covers the
#: index's bytes, and the index's content hash would cover the manifest's.  There
#: is no fixed point, and inventing one is not possible.  The gap this leaves is
#: closed by a different, sound rule instead -- the manifest FILE must be the
#: canonical encoding of the manifest it commits to
#: (``_validated_directory``).  A byte change that is not a re-encoding is refused,
#: so the meta manifest is still byte-determined, just not by an in-index hash.
#: Its hash is additionally returned in the write receipt so an owner approval or
#: the WP8 bundle can bind it externally.


def _require_status(status: object) -> None:
    """Accept only a prepared-record status this layout declares."""
    _non_empty_string(status, "status")
    _require(status in ACCEPTED_STATUSES,
             f"status is not an accepted prepared-record status: {status}")


def _require_not_non_synthetic(supported: object) -> None:
    """Refuse a prepared record that claims the unreviewed release path.

    Owner default 2 (``GATE_9_WP7_PINNED_DRAFT_AND_WP7B_OWNER_DECISION.md:150``)
    authorizes a *separately reviewed* non-synthetic WP5b release path that does
    not exist in this repository; the present WP5b refuses non-synthetic
    instances outright (``stage2_instance_preparation.py:400-466``).  A record
    asserting ``non_synthetic_supported is True`` therefore names a path that
    has not been reviewed, and is refused rather than accepted as a promise.

    The identity test ``is False`` also subsumes a separate ``type(...) is bool``
    guard: ``0``, ``0.0`` and ``""`` all compare unequal to ``False`` by identity,
    so only the one boolean object passes.
    """
    _require(supported is False,
             "refusing a prepared record that claims non-synthetic support: "
             "the reviewed WP5b non-synthetic release path does not exist")


#: The WP5b provenance schema this layout binds, read from the reviewed module
#: rather than restated, so a WP5b schema bump cannot silently diverge from the
#: copy checked in here (``stage2_instance_preparation.py:146``).
PROVENANCE_SCHEMA = _preparation.PROVENANCE_SCHEMA


def _validated_provenance(record: object) -> dict[str, object]:
    """Validate a WP5b prepared record through WP5b's OWN reviewed validator.

    The prepared record is WP5b's artifact and WP5b's
    ``validate_provenance_record`` is its reviewed validator
    (``stage2_instance_preparation.py:811-832``).  This layout does NOT
    re-implement that schema: it calls it, so the record is checked against
    exactly the key set, schema string, status, non-synthetic flag, scope
    statement, source-hash map and content hash that WP5b reviewed, and a future
    WP5b tightening is inherited here rather than silently bypassed.

    Calling discipline is explicitly NOT the control.  An earlier revision of
    this module checked only ``status`` and ``non_synthetic_supported`` and
    documented "callers must run that validator first"
    (``WP8D_DRAWN_INSTANCE_LAYOUT_NOTES.md``, prior revision).  That is a test
    gap dressed as a rule: a record that is wrong in every other field was
    written and then verified.  WP5b raises ``InstancePreparationError``, which is
    translated here into this module's typed ``LayoutError`` so a caller still
    catches exactly one exception type.

    Note the honest limit of this call: WP5b's validator is a *shape and hash*
    validator.  It proves the record is well formed, is sealed over its own body
    and declares synthetic-only scope.  It does NOT re-run the optimisation that
    produced ``results``; see the "What is and is not validated" note.
    """
    try:
        validated = _preparation.validate_provenance_record(record)
    except _preparation.InstancePreparationError as exc:
        raise LayoutError(f"prepared record is refused by the reviewed WP5b "
                          f"provenance validator: {exc}") from exc
    _require(type(validated) is dict, "prepared record must be an object")
    # The two fields this layout also renders into the index are re-checked here
    # through this module's own guards, so the accepted-status set and the
    # non-synthetic refusal stay owned by the LAYOUT and cannot be widened by a
    # WP5b change alone.  Both are separate statements: the status check is what
    # rejects an unknown status, the non-synthetic check is what rejects a
    # record claiming the unreviewed release path.
    _require_status(validated.get("status"))
    _require_not_non_synthetic(validated.get("non_synthetic_supported"))
    return validated


def _prepared_instance_id(prepared: Mapping[str, Any]) -> str:
    """The instance identity the WP5b prepared record itself claims.

    Read from the record's own ``instance.instance_id`` field
    (``stage2_instance_preparation.py:769``), which is the identity WP5b binds to
    the instance digest.  A record that does not carry a non-empty string there
    cannot be cross-bound to the generation record, so it is refused here rather
    than silently treated as unconstrained.
    """
    instance = prepared.get("instance")
    _require(type(instance) is dict, "prepared record instance must be an object")
    identity = instance.get("instance_id")
    _non_empty_string(identity, "prepared record instance_id")
    return identity


def build_instance_index(*, slot: int, attempt: int, instance_id: str,
                         prepared_record_sha256: str, prepared_record_status: str,
                         non_synthetic_supported: bool,
                         prepared_manifest_sha256: str,
                         prepared_manifest_content_sha256: str,
                         generation_manifest_sha256: str,
                         generation_manifest_content_sha256: str,
                         attempt_record_sha256: str,
                         attempt_record_content_sha256: str,
                         attempt_disposition: str,
                         rejection_code_count: int,
                         rejected_attempt_history_count: int,
                         mu_new_sha256: str, sigma_new_sha256: str,
                         implementation_record_content_sha256: str) -> dict[str, object]:
    """Render the per-instance index.

    The index is the member that makes a promoted generation directory *an
    instance* rather than an anonymous directory of files: it names the slot and
    its canonical directory name, the accepted attempt, the instance identity,
    and the exact hashes of both WP5 manifests, of the prepared record and of the
    retained-attempt ledger.

    ``*.manifest_sha256`` is the SHA-256 of the manifest FILE's bytes and
    ``*.manifest_content_sha256`` is the manifest's own content hash (the field
    WP5 seals at ``stage2_generation_writer.py:200``).  Both are recorded because
    they are different commitments: the first binds the exact bytes, the second
    is reproduced by any independent re-canonicalisation.  The generation
    reference always carried both; the prepared reference did NOT until schema
    v2, which is why appending whitespace to ``instance/MANIFEST.json`` used to
    verify.  The meta manifest's bytes are not and cannot be in the index -- see
    the note above ``PREPARED_REF_KEYS``.

    Schema v3 adds two blocks, both of which exist because the protocol requires
    content that was previously recorded only where the layout could not reach it:

    * ``attempt_ledger`` binds the ledger's bytes, its content hash, its accepted
      attempt number, its disposition and the two COUNTS the protocol cares
      about -- how many fixed rejection codes this accepted attempt carries (which
      the protocol requires to be none) and how many rejected attempts precede it.
      Recording the counts rather than the codes keeps the index free of the
      scientific-adjacent text while still making a rewritten history detectable.
    * ``moments`` binds the digest of each recorded U-09 moment block, so the
      canonical ``mu_new``/``Sigma_new`` encodings are committed outside the
      record that holds them.
    """
    # No local ``_slot_int(slot)``: the ``slot_name`` field below renders through
    # ``slot_name(slot)``, which applies that same guard, so an out-of-range slot
    # is refused on the next line with the same typed error.  A second call here
    # would be a duplicate of one boundary, not a second boundary.
    _attempt_int(attempt)
    _non_empty_string(instance_id, "instance_id")
    _sha(prepared_record_sha256, "prepared record sha256")
    _require_status(prepared_record_status)
    _require_not_non_synthetic(non_synthetic_supported)
    _sha(prepared_manifest_sha256, "prepared manifest sha256")
    _sha(prepared_manifest_content_sha256, "prepared manifest content sha256")
    _sha(generation_manifest_sha256, "generation manifest sha256")
    _sha(generation_manifest_content_sha256, "generation manifest content sha256")
    _sha(attempt_record_sha256, "attempt record sha256")
    _sha(attempt_record_content_sha256, "attempt record content sha256")
    _disposition(attempt_disposition)
    # The index describes an ACCEPTED instance, so it may not name a rejected
    # ledger.  Enforced on the builder as well as the validator: a write-side-only
    # acceptance here would let a caller write an index its own reader refuses.
    _require(attempt_disposition == DISPOSITION_ACCEPTED,
             "the index describes an accepted instance, so its retained-attempt "
             "ledger must claim the accepted disposition")
    _count_int(rejection_code_count, "rejection code count")
    _count_int(rejected_attempt_history_count, "rejected attempt history count")
    _sha(mu_new_sha256, "mu_new sha256")
    _sha(sigma_new_sha256, "sigma_new sha256")
    _sha(implementation_record_content_sha256, "implementation record content sha256")
    record: dict[str, object] = {
        "schema": INSTANCE_SCHEMA,
        "slot": slot,
        "slot_name": slot_name(slot),
        "attempt": attempt,
        "instance_id": instance_id,
        "prepared_record": {
            "path": f"{PREPARED_DIR_NAME}/PREPARED.json",
            "sha256": prepared_record_sha256,
            "status": prepared_record_status,
            "non_synthetic_supported": non_synthetic_supported,
            "manifest_sha256": prepared_manifest_sha256,
            "manifest_content_sha256": prepared_manifest_content_sha256,
        },
        "generation": {
            "path": GENERATION_DIR_NAME,
            "manifest_sha256": generation_manifest_sha256,
            "manifest_content_sha256": generation_manifest_content_sha256,
        },
        "attempt_ledger": {
            "path": f"{GENERATION_DIR_NAME}/{ATTEMPT_NAME}",
            "sha256": attempt_record_sha256,
            "content_sha256": attempt_record_content_sha256,
            "attempt": attempt,
            "disposition": attempt_disposition,
            "rejection_code_count": rejection_code_count,
            "rejected_attempt_history_count": rejected_attempt_history_count,
        },
        "moments": {
            "mu_new_sha256": mu_new_sha256,
            "sigma_new_sha256": sigma_new_sha256,
        },
        "implementation_record": implementation_record_content_sha256,
        "status": prepared_record_status,
        "scope": SCOPE_STATEMENT,
    }
    record["content_sha256"] = _content_sha256(record)
    return record


def validate_instance_index(record: object) -> dict[str, object]:
    """Validate a per-instance index and return a copy of it."""
    _require(type(record) is dict, "instance index must be an object")
    _require(set(record) == INSTANCE_KEYS, "instance index has wrong key set")
    _require(record["schema"] != INSTANCE_SCHEMA_V2,
             "this is a superseded v2 instance index, which cannot bind the "
             "retained-attempt ledger or the recorded mu_new/Sigma_new digests")
    _require(record["schema"] == INSTANCE_SCHEMA, "instance index schema mismatch")
    _require(record["scope"] == SCOPE_STATEMENT, "instance index scope statement mismatch")
    # No standalone ``_slot_int(record["slot"])``: the slot_name check below calls
    # ``slot_name(record["slot"])``, which applies that same guard, so an invalid
    # slot is refused there.  One boundary, one call.
    _require(record["slot_name"] == slot_name(record["slot"]),
             "instance index slot_name is not the canonical name of its slot")
    # The TOP-LEVEL attempt is range-checked here rather than left to the ledger's
    # check below.  The two are bound to each other, so a guard that only checked
    # one of them would let a malformed pair through -- and the sweep found exactly
    # that: a guard on the nested field alone survived, because the equality then
    # refused the out-of-range value with the wrong message and the fixture could
    # not reach the range boundary at all.  Checking the top-level field is what
    # makes ``attempt=128`` a *range* refusal rather than an equality one, and it is
    # the boundary a caller reads.
    _attempt_int(record["attempt"])
    _non_empty_string(record["instance_id"], "instance index instance_id")
    _require_status(record["status"])
    prepared = record["prepared_record"]
    _require(type(prepared) is dict, "prepared_record must be an object")
    _require(set(prepared) == PREPARED_REF_KEYS, "prepared_record has wrong key set")
    _require(prepared["path"] == f"{PREPARED_DIR_NAME}/PREPARED.json",
             "prepared_record path mismatch")
    _sha(prepared["sha256"], "prepared record sha256")
    _sha(prepared["manifest_sha256"], "prepared manifest sha256")
    _sha(prepared["manifest_content_sha256"], "prepared manifest content sha256")
    # No ``_require_status(prepared["status"])`` here: ACCEPTED_STATUSES holds one
    # string, and the index's TOP-LEVEL status is already required to be in that
    # set, so a membership check on the nested value would be an unobservable
    # duplicate.  The cross-record agreement that IS observable, and is asserted
    # in verify_instance, is against the prepared FILE: that file is a genuinely
    # different object, and this validator never looks at the nested field at all.
    _require_not_non_synthetic(prepared["non_synthetic_supported"])
    generation = record["generation"]
    _require(type(generation) is dict, "generation must be an object")
    _require(set(generation) == GENERATION_REF_KEYS, "generation has wrong key set")
    _require(generation["path"] == GENERATION_DIR_NAME, "generation path mismatch")
    _sha(generation["manifest_sha256"], "generation manifest sha256")
    _sha(generation["manifest_content_sha256"], "generation manifest content sha256")
    ledger = record["attempt_ledger"]
    _require(type(ledger) is dict, "attempt_ledger must be an object")
    _require(set(ledger) == ATTEMPT_REF_KEYS, "attempt_ledger has wrong key set")
    _require(ledger["path"] == f"{GENERATION_DIR_NAME}/{ATTEMPT_NAME}",
             "attempt_ledger path mismatch")
    _sha(ledger["sha256"], "attempt record sha256")
    _sha(ledger["content_sha256"], "attempt record content sha256")
    # The nested attempt number is checked against the top-level one HERE, not
    # only in verify_instance.  Both are in one record, so this is a record-internal
    # consistency check the validator owns; verify_instance separately compares
    # both against the ledger FILE on disk, which is the cross-record binding.
    #
    # BOTH fields are range-checked, each in its own statement, because the two
    # guards are separately falsifiable.  With only the equality, an out-of-range
    # pair such as ``(128, 128)`` agrees with itself and is refused for
    # DISAGREEING against nothing -- the range boundary is simply never reached, and
    # a fixture asserting it would be asserting a refusal that cannot happen.  The
    # two guards answer different questions: "is this a legal attempt number?" and
    # "do these two fields name the same attempt?"  Both are asked.
    _attempt_int(ledger["attempt"])
    _require(ledger["attempt"] == record["attempt"],
             "attempt_ledger attempt disagrees with the index attempt")
    _disposition(ledger["disposition"])
    _require(ledger["disposition"] == DISPOSITION_ACCEPTED,
             "the index describes an accepted instance, so its retained-attempt "
             "ledger must claim the accepted disposition")
    _count_int(ledger["rejection_code_count"], "rejection code count")
    _count_int(ledger["rejected_attempt_history_count"],
               "rejected attempt history count")
    # Ordering, asserted from the index alone: every retained rejected attempt
    # must be numbered below the accepted one, so the accepted number is strictly
    # greater than the largest rejected one and the pair determines the accepted
    # attempt unambiguously.
    _require(ledger["rejected_attempt_history_count"] <= ledger["attempt"],
             "more rejected attempts are retained than precede the accepted attempt")
    moments = record["moments"]
    _require(type(moments) is dict, "moments must be an object")
    _require(set(moments) == MOMENT_REF_KEYS, "moments has wrong key set")
    _sha(moments["mu_new_sha256"], "mu_new sha256")
    _sha(moments["sigma_new_sha256"], "sigma_new sha256")
    _sha(record["implementation_record"], "implementation record content sha256")
    _require(record["content_sha256"] == _content_sha256(record),
             "instance index content hash mismatch")
    return dict(record)


# ---------------------------------------------------------------------------
# Reading and hashing on disk
# ---------------------------------------------------------------------------

def _as_layout(fn, *args, **kwargs):
    """Call a WP5 entry point and translate its typed refusal into this one's.

    WP5 raises ``GenerationWriterError`` and this module raises ``LayoutError``.
    Without this translation a caller of ``verify_instance`` would have to catch
    two exception types for one class of failure -- a tampered member would leave
    as ``GenerationWriterError`` and a malformed record as ``LayoutError`` -- and
    the fail-closed contract a caller actually writes (``except LayoutError``)
    would be silently incomplete.  The original message is preserved verbatim,
    and only its type changes.
    """
    try:
        return fn(*args, **kwargs)
    except _writer.GenerationWriterError as exc:
        raise LayoutError(str(exc)) from exc


def _real_file(path: Path, label: str) -> bytes:
    """Read a regular, non-symlink file, refusing anything else.

    Two separate checks: ``is_file()`` is True for a symlink POINTING AT a
    regular file, so dropping the symlink test would let a member be replaced by
    a link to another file with identical contents and pass every hash check.
    """
    _require(path.is_file(), f"{label} is missing or not a regular file: {path}")
    _require(not path.is_symlink(), f"{label} is a symlink: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise LayoutError(f"cannot read {label} {path}: {exc.__class__.__name__}") from exc


def _sha_file(path: Path, label: str) -> str:
    """Re-hash a regular, non-symlink file in bounded blocks."""
    _require(path.is_file(), f"{label} is missing or not a regular file: {path}")
    _require(not path.is_symlink(), f"{label} is a symlink: {path}")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError as exc:
        raise LayoutError(f"cannot read {label} {path}: {exc.__class__.__name__}") from exc
    return digest.hexdigest()


def _load_record(path: Path, label: str) -> dict[str, object]:
    """Read one canonical JSON record member.

    The bytes must be EXACTLY the canonical encoding of the parsed object, not
    merely equivalent to it: every record member is written by this layout's own
    ``_canonical``, and a member reformatted after writing still parses, so the
    canonical-bytes check is what makes "the file on disk IS the record" true.
    """
    raw = _real_file(path, label)
    try:
        parsed = json.loads(raw.decode("ascii"))
    except UnicodeDecodeError as exc:
        raise LayoutError(f"{label} is not ASCII") from exc
    except ValueError as exc:
        raise LayoutError(f"{label} is not JSON") from exc
    _require(type(parsed) is dict, f"{label} must be a JSON object")
    _require(raw == _canonical(parsed), f"{label} is not in canonical form")
    return parsed


def _list_names(directory: Path, label: str) -> list[str]:
    """The sorted entry names of a directory."""
    _require(directory.is_dir(), f"{label} is not a directory: {directory}")
    _require(not directory.is_symlink(), f"{label} is a symlink: {directory}")
    try:
        return sorted(os.listdir(directory))
    except OSError as exc:
        raise LayoutError(f"cannot list {label} {directory}: "
                          f"{exc.__class__.__name__}") from exc


def _list_flat_names(directory: Path, label: str) -> list[str]:
    """The sorted FILE names of a flat directory, refusing any subdirectory.

    A generation directory and a sidecar hold files only, so a subdirectory there
    is a layout deviation and is refused here rather than skipped: WP5's own
    directory walk would not see an empty directory anyway
    (``stage2_generation_writer.py:369-375``), because a directory carries no
    bytes and therefore no hash that could mismatch.
    """
    names = _list_names(directory, label)
    for name in names:
        _require(not (directory / name).is_dir(),
                 f"{label} contains a subdirectory, which this layout forbids: {name}")
    return names


def _require_exact_names(present: list[str], expected: tuple[str, ...], label: str) -> None:
    _require(tuple(present) == tuple(sorted(expected)),
             f"{label} contents differ from the canonical layout: present={present} "
             f"expected={sorted(expected)}")


def _require_real_dir(path: Path, label: str) -> None:
    """Accept a real directory, refusing a file, an absent path and a symlink.

    ``is_dir()`` is True for a symlink pointing at a directory, so the two checks
    are not redundant.
    """
    _require(path.is_dir(), f"{label} is not a directory: {path}")
    _require(not path.is_symlink(), f"{label} is a symlink: {path}")


def _require_absent(path: Path, label: str) -> None:
    """Accept a path that is absent entirely -- not a file, not a symlink.

    WP5's writer refuses an existing target because ``os.rename`` onto an existing
    non-empty directory MERGES rather than replaces
    (``stage2_generation_writer.py:236-257``).  A DANGLING symlink is what makes
    the two operands non-redundant: it is invisible to ``exists()``, which follows
    links, but it is still an entry a ``rename`` would clobber.
    """
    _require(not path.exists(), f"{label} already exists: {path}")
    _require(not path.is_symlink(), f"{label} is a symlink: {path}")


# ---------------------------------------------------------------------------
# Validation of the three promoted directories
# ---------------------------------------------------------------------------

def _validated_directory(directory: Path | str, members: tuple[str, ...], label: str
                         ) -> tuple[Path, list[str], dict[str, object], bytes]:
    """Shared front half of a sidecar validation: exact members, then rehash."""
    root = Path(directory)
    present = _list_flat_names(root, label)
    _require_exact_names(present, members, label)
    # WP5's own rehash boundary, unchanged: the entry point the design draft names
    # (``WP8_PRODUCTION_BUNDLE_DESIGN.md:12-18``).  It either returns ``verdict ==
    # "verified"`` or raises, so there is no verdict left here to re-test.
    _as_layout(_writer.verify_written_generation, root)
    manifest_bytes = _real_file(root / MANIFEST_NAME, f"{label} manifest")
    manifest = _as_layout(_writer.validate_manifest, json.loads(manifest_bytes.decode("ascii")))
    # The manifest FILE must be the canonical encoding of the manifest WP5 sealed.
    # WP5's own content hash is computed over the PARSED body
    # (``stage2_generation_writer.py:83-86,200``), so it cannot see insignificant
    # whitespace, and ``verify_written_generation`` parses rather than compares
    # bytes.  Appending one space to a manifest therefore left every recorded hash
    # valid.  For the generation and prepared sidecars the index binds the
    # manifest's bytes, so the gap was already closed there; for the META manifest
    # no in-index binding is possible (it commits to the index, so a mutual byte
    # binding has no fixed point), and this canonicality check is what closes it
    # instead.  It is enforced on all three so the rule is stated once.
    _require(manifest_bytes == _canonical(manifest),
             f"{label} manifest is not the canonical encoding of its own content")
    # No local re-check of the manifest's implementation-record hash: WP5's own
    # validate_manifest already requires it to be a lowercase 64-character SHA-256
    # (``stage2_generation_writer.py:217``), and it refuses a malformed one before
    # returning, so a check here would be an unobservable duplicate of an upstream
    # refusal that has already fired.
    return root, present, manifest, manifest_bytes


def validate_generation_directory(directory: Path | str) -> dict[str, object]:
    """Validate one promoted generation directory in full, and summarise it.

    The read side of the layout.  In order:

    1. refuse anything that is not a real directory holding exactly the canonical
       generation member set;
    2. re-hash every member against WP5's ``MANIFEST.json`` through WP5's own
       ``verify_written_generation`` (``stage2_generation_writer.py:328-382``),
       which refuses a size, content-hash, extra-file, missing-file or
       record-binding mismatch;
    3. parse and validate the two record members, refusing schema, key-set,
       status, hash and derivation drift;
    4. require the two records to agree on the slot and the attempt, and to name
       the same implementation record as the manifest that promoted them;
    5. re-hash the return matrix and require it to be exactly
       ``RETURN_ROWS * ASSET_COUNT * 8`` bytes.

    Raises ``LayoutError`` on any deviation.
    """
    root, members, manifest, manifest_bytes = _validated_directory(
        directory, GENERATION_MEMBERS, "generation directory")
    attempt_bytes = _real_file(root / ATTEMPT_NAME, "attempt record")
    attempt_record = validate_attempt_record(_load_record(root / ATTEMPT_NAME,
                                                          "attempt record"))
    generation_record = validate_generation_record(
        _load_record(root / GENERATION_NAME, "generation record"))
    _require(generation_record["slot"] == attempt_record["slot"],
             "generation record slot disagrees with the attempt record")
    _require(generation_record["attempt"] == attempt_record["attempt"],
             "generation record attempt disagrees with the attempt record")
    # NO disposition check here, deliberately.  The ledger on disk is already run
    # through ``validate_attempt_record``, which refuses a record claiming
    # ``rejected`` while also carrying a history -- and any record that could reach
    # this function at all already carries one, since that is what the accepted
    # instance's ledger is.  An earlier revision asserted the disposition was
    # ``accepted`` here; the sweep proved the assertion unobservable, because the
    # validator's own dispositions rule always fired first.  Rather than exempt an
    # unreachable guard, it was removed and the reasoning recorded: the invariant
    # "this directory describes an accepted attempt" is enforced by the ledger's own
    # validator plus the fact that only ``build_attempt_record`` produces the
    # accepted shape, not by a second comparison here.
    _require(manifest["implementation_record_content_sha256"]
             == generation_record["implementation_record"],
             "the manifest and the generation record name different implementation records")

    matrix_bytes = _real_file(root / RETURN_MATRIX_NAME, "return matrix")
    _require(len(matrix_bytes) == RETURN_MATRIX_BYTES,
             f"return matrix is not {RETURN_MATRIX_BYTES} bytes: {len(matrix_bytes)}")
    _require(hashlib.sha256(matrix_bytes).hexdigest()
             == generation_record["return_matrix_sha256"],
             "return matrix content hash does not match the generation record")

    summary = generation_record["moment_summary"]
    return {
        "target": str(root),
        "verdict": "verified",
        "slot": attempt_record["slot"],
        "slot_name": slot_name(attempt_record["slot"]),
        "attempt": attempt_record["attempt"],
        "instance_id": generation_record["instance_id"],
        "members": members,
        "generation_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "generation_manifest_content_sha256": manifest["content_sha256"],
        "implementation_record_content_sha256": manifest["implementation_record_content_sha256"],
        "return_matrix_sha256": generation_record["return_matrix_sha256"],
        "attempt_record_sha256": hashlib.sha256(attempt_bytes).hexdigest(),
        "attempt_record_content_sha256": attempt_record["content_sha256"],
        "attempt_disposition": attempt_record["disposition"],
        "rejection_codes": list(attempt_record["rejection_codes"]),
        "rejected_attempt_history": [dict(entry)
                                     for entry in attempt_record["rejected_attempt_history"]],
        "rejected_attempt_history_count": len(attempt_record["rejected_attempt_history"]),
        "mu_new_sha256": summary["mu_new"]["sha256"],
        "sigma_new_sha256": summary["sigma_new"]["sha256"],
        "mu_new_encoding": summary["mu_new"]["encoding"],
    }


def validate_prepared_directory(directory: Path | str) -> dict[str, object]:
    """Validate one promoted prepared-record sidecar, and summarise it.

    The record is re-read from disk and re-run through WP5b's own reviewed
    ``validate_provenance_record`` (``stage2_instance_preparation.py:811-832``).
    Reading it is not enough: a directory that was written by a caller who
    skipped the write-side check, or edited by hand and re-sealed, must be
    refused on the way back in as well.  The summary therefore reports the
    identity the record itself claims, which ``verify_instance`` cross-binds to
    the generation record.
    """
    root, members, manifest, manifest_bytes = _validated_directory(
        directory, PREPARED_MEMBERS, "prepared sidecar")
    prepared_bytes = _real_file(root / "PREPARED.json", "prepared record")
    prepared = _validated_provenance(_load_record(root / "PREPARED.json", "prepared record"))
    return {
        "target": str(root),
        "verdict": "verified",
        "members": members,
        "prepared_record_sha256": hashlib.sha256(prepared_bytes).hexdigest(),
        "prepared_record_status": prepared["status"],
        "prepared_record_instance_id": _prepared_instance_id(prepared),
        "prepared_record_non_synthetic_supported": prepared["non_synthetic_supported"],
        "prepared_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "prepared_manifest_content_sha256": manifest["content_sha256"],
        "implementation_record_content_sha256": manifest["implementation_record_content_sha256"],
    }


def validate_meta_directory(directory: Path | str) -> dict[str, object]:
    """Validate one promoted meta sidecar, and summarise it.

    The index is bound to the generation and prepared manifests, so this
    function re-hashes the index against its own manifest and hands the caller a
    summary of the commitments it carries.  ``verify_instance`` then compares
    those commitments against the two directories it names, which is the only
    place the two sides can genuinely disagree.
    """
    root, members, manifest, manifest_bytes = _validated_directory(
        directory, META_MEMBERS, "meta sidecar")
    index = validate_instance_index(_load_record(root / INDEX_NAME, "instance index"))
    return {
        "target": str(root),
        "verdict": "verified",
        "members": members,
        "index_content_sha256": index["content_sha256"],
        "meta_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "implementation_record_content_sha256": manifest["implementation_record_content_sha256"],
        "index": index,
    }


# ---------------------------------------------------------------------------
# Whole-instance verification
# ---------------------------------------------------------------------------

def verify_instance(slot: int | str, *, root: Path | str = ROOT) -> dict[str, object]:
    """Validate one written instance end to end, and summarise it.

    Refuses a slot that is not one of the five canonical names or numbers, a
    missing or non-directory slot, a slot whose contents are not exactly the three
    fixed subdirectories, any layout deviation inside a subdirectory, an index
    naming different hashes from the files beside it, and a sidecar bound to a
    different implementation record than the generation.
    """
    number = slot_number(slot) if type(slot) is str else _slot_int(slot)
    base = slot_dir(number, root=root)
    members = _list_names(base, "instance directory")
    _require_exact_names(members, SLOT_MEMBERS, "instance directory")
    # The directory that was opened is the requested slot, by construction:
    # ``base`` was just built as ``slot_dir(number)`` and ``slot_dir`` renders its
    # last component through ``slot_name(number)`` (``wp8d_...:329-331``), so
    # ``base.name == slot_name(number)`` is a tautology and asserting it would be
    # an unobservable duplicate.  The binding that IS observable -- and the one
    # that actually fixes the reported accept -- is the comparison of the
    # requested slot against the slot the RECORDS claim, two lines below: a
    # stage2_02 directory whose three records all say slot 1 passes every
    # name-derived check and is refused only by that comparison.
    generation = validate_generation_directory(base / GENERATION_DIR_NAME)
    prepared = validate_prepared_directory(base / PREPARED_DIR_NAME)
    meta = validate_meta_directory(base / META_DIR_NAME)
    # The records must agree with the REQUESTED slot, not merely with each other.
    # The three records were compared to one another in a prior revision, which
    # let three self-consistent records naming the wrong slot pass.
    _require(generation["slot"] == number,
             "the generation record names a different slot than the instance directory")
    _require(prepared["implementation_record_content_sha256"]
             == generation["implementation_record_content_sha256"],
             "the prepared sidecar and the generation name different implementation records")
    _require(meta["implementation_record_content_sha256"]
             == generation["implementation_record_content_sha256"],
             "the meta sidecar and the generation name different implementation records")
    index = meta["index"]
    _require(index["slot"] == number,
             "instance index slot disagrees with the instance directory")
    # No slot_name comparison here: validate_instance_index already requires
    # ``slot_name`` to be ``slot_name(slot)``, so it is a pure function of the
    # slot, which the two lines above have just made equal to the requested one.
    # A disagreement is therefore unreachable, not merely untested.
    #
    # The retained-attempt ledger is bound from OUTSIDE its own directory.  Each
    # of these compares the index against the ledger FILE, which is a separate
    # object an attacker can rewrite and re-seal; the re-seal also has to fix the
    # WP5 manifest and then this index's own content hash, so the binding is what
    # makes a rewritten ledger detectable rather than merely self-consistent.
    ledger = index["attempt_ledger"]
    # Four comparisons here were removed as unreachable rather than exempted, and
    # the sweep is what established it.  In each case an EARLIER check in this same
    # function, or in the record's own validator, already refuses every input the
    # later check could have refused:
    #
    #   * ledger["disposition"] vs the ledger file -- the file was validated by
    #     ``validate_attempt_record``, whose dispositions rule admits only
    #     ``accepted`` for a record carrying a history, and this index names a
    #     history.  So the file's disposition is the single accepted string and the
    #     index's own validator already forced its nested copy to it.
    #   * index["attempt"] vs the generation -- the index validator binds
    #     ``attempt`` to ``attempt_ledger.attempt``, and the check just above binds
    #     ``attempt_ledger.attempt`` to the generation, so the two are transitively
    #     equal.  It is the composition that enforces it, not a third comparison.
    #   * history ordering (below) -- ``_rejected_history`` already requires every
    #     retained entry to be numbered below the accepted attempt, so a ledger that
    #     survives validation cannot violate it.  Exhaustive enumeration over the
    #     legal histories confirmed no accepted record can fail that comparison.
    _require(ledger["attempt"] == generation["attempt"],
             "instance index attempt_ledger attempt disagrees with the accepted attempt")
    _require(ledger["sha256"] == generation["attempt_record_sha256"],
             "instance index does not name this retained-attempt ledger's bytes")
    _require(ledger["content_sha256"] == generation["attempt_record_content_sha256"],
             "instance index does not name this retained-attempt ledger's content hash")
    _require(ledger["rejection_code_count"] == len(generation["rejection_codes"]),
             "instance index attempt_ledger rejection code count disagrees with the ledger")
    _require(ledger["rejected_attempt_history_count"]
             == generation["rejected_attempt_history_count"],
             "instance index attempt_ledger history count disagrees with the ledger")
    # The recorded U-09 moments are bound from outside the generation record too.
    _require(index["moments"]["mu_new_sha256"] == generation["mu_new_sha256"],
             "instance index does not name this generation's mu_new digest")
    _require(index["moments"]["sigma_new_sha256"] == generation["sigma_new_sha256"],
             "instance index does not name this generation's Sigma_new digest")
    _require(index["instance_id"] == generation["instance_id"],
             "instance index instance_id disagrees with the generation")
    # The prepared record's own identity must be that same identity.  WP5b's
    # validator checks the prepared record's internal consistency and cannot know
    # which instance of a layout it is being filed under, so the binding between
    # the provenance record and the generation record is this module's boundary.
    _require(prepared["prepared_record_instance_id"] == generation["instance_id"],
             "the prepared record names a different instance than the generation")
    _require(index["implementation_record"]
             == generation["implementation_record_content_sha256"],
             "instance index implementation record disagrees with the generation")
    _require(index["generation"]["manifest_sha256"]
             == generation["generation_manifest_sha256"],
             "instance index does not name this generation's manifest bytes")
    _require(index["generation"]["manifest_content_sha256"]
             == generation["generation_manifest_content_sha256"],
             "instance index does not name this generation's manifest content hash")
    _require(index["prepared_record"]["sha256"] == prepared["prepared_record_sha256"],
             "instance index does not name this prepared record's bytes")
    # The prepared sidecar's MANIFEST is bound the same way the generation
    # manifest is: exact file bytes AND the manifest's own content hash.  Schema
    # v1 of this index bound neither, so one appended whitespace byte in
    # instance/MANIFEST.json verified while the notes claimed the binding existed.
    _require(index["prepared_record"]["manifest_sha256"]
             == prepared["prepared_manifest_sha256"],
             "instance index does not name this prepared manifest's bytes")
    _require(index["prepared_record"]["manifest_content_sha256"]
             == prepared["prepared_manifest_content_sha256"],
             "instance index does not name this prepared manifest's content hash")
    # The index's nested prepared_record.status is compared to the prepared
    # FILE, which is a separate object and can genuinely disagree.  A prior
    # revision argued the comparison was unnecessary because both sides are
    # drawn from a one-element accepted-status set: that is true only while both
    # are *valid*, and the index's own validator never inspects the NESTED field
    # at all, so a re-sealed index can carry any string there.  The cross-binding
    # is what stops it.
    _require(index["prepared_record"]["status"] == prepared["prepared_record_status"],
             "instance index prepared_record status disagrees with the prepared record")
    # The nested non_synthetic flag is NOT compared to the file, for the same
    # reason the top-level status is not: ``validate_instance_index`` runs
    # ``_require_not_non_synthetic`` on it, which forces it to the single object
    # ``False`` by identity, and WP5b forces the file's value to ``False`` too.
    # Two constants, so the comparison has no falsifiable input.  The STATUS
    # above is different in kind and is the load-bearing one: the index's own
    # validator never inspects the nested status, so only that comparison stops a
    # re-sealed index from misreporting which prepared record it names.
    # The index's top-level ``status`` is not compared to the file either, for
    # the same constant-forcing reason: ``validate_instance_index`` requires
    # ``record["status"] in ACCEPTED_STATUSES`` and WP5b requires the file's
    # status to be exactly ``prepared_synthetic_only``, and ACCEPTED_STATUSES
    # holds that one string.
    return {
        "target": str(base),
        "verdict": "verified",
        "slot": generation["slot"],
        "slot_name": generation["slot_name"],
        "attempt": generation["attempt"],
        "instance_id": generation["instance_id"],
        "index_content_sha256": index["content_sha256"],
        "generation_manifest_sha256": generation["generation_manifest_sha256"],
        "generation_manifest_content_sha256": generation["generation_manifest_content_sha256"],
        "implementation_record_content_sha256": generation["implementation_record_content_sha256"],
        "prepared_record_sha256": prepared["prepared_record_sha256"],
        "prepared_record_status": prepared["prepared_record_status"],
        "prepared_record_instance_id": prepared["prepared_record_instance_id"],
        "prepared_manifest_sha256": prepared["prepared_manifest_sha256"],
        "prepared_manifest_content_sha256": prepared["prepared_manifest_content_sha256"],
        "return_matrix_sha256": generation["return_matrix_sha256"],
        "attempt_record_sha256": generation["attempt_record_sha256"],
        "attempt_record_content_sha256": generation["attempt_record_content_sha256"],
        "attempt_disposition": generation["attempt_disposition"],
        "rejected_attempt_history_count": generation["rejected_attempt_history_count"],
        "mu_new_sha256": generation["mu_new_sha256"],
        "sigma_new_sha256": generation["sigma_new_sha256"],
    }


def verify_all_slots(*, root: Path | str = ROOT,
                     present: Sequence[int] = ()) -> dict[str, object]:
    """Validate the slots that exist under ``root``, and refuse an unknown one.

    ``present`` names the slots expected to exist.  An empty sequence verifies
    exactly the canonical slot directories that are present and refuses any
    present directory whose name is not one of the five -- a stray directory under
    ``research/g9/stage2_instances/`` is a layout deviation, not an ignorable
    extra.  With ``present`` given, a missing expected slot is refused, because
    "five drawn instances" is a protocol count
    (``GATE_9_STAGE2_PROTOCOL_DRAFT.md:51-53``) and its absence must be stated.
    """
    root_dir = Path(root) / INSTANCE_ROOT
    _require_real_dir(root_dir, "instance root")
    try:
        found = sorted(os.listdir(root_dir))
    except OSError as exc:
        raise LayoutError(f"cannot list the instance root {root_dir}: "
                          f"{exc.__class__.__name__}") from exc
    for name in found:
        slot_number(name)
    if present:
        expected = sorted(slot_name(slot) for slot in present)
        _require(found == expected,
                 f"instance root holds {found}, expected exactly {expected}")
    summaries = [verify_instance(name, root=root) for name in found]
    _require(len(set(summary["instance_id"] for summary in summaries)) == len(summaries),
             "two slots name the same instance_id")
    return {
        "verdict": "verified",
        "root": str(root_dir),
        "slots": [summary["slot_name"] for summary in summaries],
        "count": len(summaries),
        "instances": summaries,
    }


# ---------------------------------------------------------------------------
# Writing an instance
# ---------------------------------------------------------------------------

def build_generation_payload(*, slot: int, attempt: int, instance_id: str,
                             sector_partition_sha256: str, feasible_count: int,
                             return_matrix: bytes,
                             implementation_record_content_sha256: str,
                             mu_new: Sequence[str], sigma_new: Sequence[Sequence[str]],
                             rejected_attempt_history: Sequence[Mapping[str, Any]] = (),
                             ) -> dict[str, bytes]:
    """Render the exact byte payload of one generation directory.

    The returned mapping is the direct argument of WP5's ``write_generation``
    (``stage2_generation_writer.py:271-276``), so the writer's own name,
    traversal, duplicate and bytes refusals apply unchanged.  This function fixes
    WHICH files exist and what each one says, so a caller cannot invent a layout
    by handing the writer its own mapping: the writer accepts arbitrary safe
    relative names (``WP8_PRODUCTION_BUNDLE_DESIGN.md:155-159``) and this is what
    closes that gap for a drawn instance.

    ``mu_new`` / ``sigma_new`` are passed straight through to the generation
    record; see :func:`build_generation_record` for why this module takes them
    rather than computing them.
    """
    _require(type(return_matrix) is bytes, "return matrix payload must be bytes")
    _require(len(return_matrix) == RETURN_MATRIX_BYTES,
             f"return matrix payload must be exactly {RETURN_MATRIX_BYTES} bytes")
    matrix_sha256 = _bytes_sha256(return_matrix, "return matrix")
    return {
        ATTEMPT_NAME: _canonical(build_attempt_record(
            slot=slot, attempt=attempt, sector_partition_sha256=sector_partition_sha256,
            feasible_count=feasible_count, rejected_attempt_history=rejected_attempt_history)),
        GENERATION_NAME: _canonical(build_generation_record(
            slot=slot, attempt=attempt, instance_id=instance_id,
            return_matrix_sha256=matrix_sha256,
            implementation_record_content_sha256=implementation_record_content_sha256,
            mu_new=mu_new, sigma_new=sigma_new)),
        RETURN_MATRIX_NAME: return_matrix,
    }


def _fsync_dir(path: Path) -> None:
    """fsync a directory so a rename inside it is durable.

    This is durability, not content: the call can fail only if the descriptor
    cannot be opened or synced, and the fixture asserts that refusal path.  No
    fixture can observe the difference between a synced and an unsynced directory
    without crashing the machine, so the fsync CALLS are not asserted; the
    refusals they raise ARE.
    """
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        raise LayoutError(f"cannot open directory {path} for fsync: "
                          f"{exc.__class__.__name__}") from exc
    try:
        os.fsync(fd)
    except OSError as exc:
        raise LayoutError(f"cannot fsync directory {path}: "
                          f"{exc.__class__.__name__}") from exc
    finally:
        os.close(fd)


def _promote(staging: Path, destination: Path) -> None:
    """Refuse to merge into an existing target, then rename.

    ``os.rename`` alone is not enough: on POSIX it moves each entry of ``staging``
    into an existing non-empty destination.  The target is re-checked here,
    immediately before the rename, and the rename is issued only while the target
    is still absent -- WP5's own boundary
    (``stage2_generation_writer.py:236-257``).
    """
    if destination.exists():
        raise LayoutError(f"refusing to overwrite an existing instance directory: {destination}")
    if destination.is_symlink():
        raise LayoutError(f"refusing to overwrite a symlink target: {destination}")
    try:
        os.rename(str(staging), str(destination))
    except OSError as exc:
        raise LayoutError(f"cannot promote {staging} to {destination}: "
                          f"{exc.__class__.__name__}") from exc


def write_instance(*, slot: int, attempt: int, instance_id: str,
                   sector_partition_sha256: str, feasible_count: int,
                   return_matrix: bytes, prepared_record: Mapping[str, Any],
                   implementation_record_content_sha256: str,
                   mu_new: Sequence[str], sigma_new: Sequence[Sequence[str]],
                   rejected_attempt_history: Sequence[Mapping[str, Any]] = (),
                   root: Path | str = ROOT) -> dict[str, object]:
    """Write one drawn instance in the canonical layout, atomically.

    All three subdirectories are promoted by WP5's ``write_generation``, so each
    carries WP5's write-once manifest, file fsync and directory fsync.  The slot
    directory is promoted by this module with WP5's staging-and-rename discipline
    and is refused if it exists at all, so an instance is written once and is
    never merged, overwritten or partially updated.

    ``prepared_record`` is the WP5b provenance record.  Its bytes are written
    verbatim to ``instance/PREPARED.json``.  Before ANY byte is written it is run
    through WP5b's own reviewed ``validate_provenance_record``
    (``stage2_instance_preparation.py:811-832``); this module does not
    re-implement that schema and does not ask the caller to have done it.  A
    record WP5b refuses is refused here, before the staging directory exists.

    The prepared record's own ``instance.instance_id`` must equal ``instance_id``:
    the two are the same instance by construction, and a layout that bound the
    generation record to one identity while the prepared record named another
    would produce a directory whose two members disagree about which instance
    they are.

    ``mu_new`` / ``sigma_new`` are the canonical binary64 encodings the protocol
    requires the generated instance to record, and ``rejected_attempt_history``
    the rejected attempts of this slot that preceded the accepted one.  Both are
    validated on the WRITE side as well as the read side, so an instance cannot
    be written that this module would then refuse to verify.

    The instance root (``research/g9/stage2_instances/``) must already exist; this
    module never creates it, because the protocol's location table is a reviewed
    choice (``GATE_9_STAGE2_PROTOCOL_DRAFT.md:214-223``).
    """
    # The scalar guards below are deliberately NOT repeated here: the very next
    # call, ``build_generation_payload``, renders BOTH the attempt record and the
    # generation record through the same ``_slot_int`` / ``_attempt_int`` /
    # ``_non_empty_string`` / ``_sha`` / ``_count_int`` guards, so an invalid
    # argument is refused there instead -- before a single byte is written, and
    # with the same typed error.  Duplicating them here would be a second copy of
    # one boundary, not a second boundary.
    #
    # The prepared record is validated HERE, before anything is created, through
    # WP5b's own reviewed validator (see ``_validated_provenance``).  The type
    # guard stays local and separate: ``_canonical`` on a non-dict would raise a
    # raw ``TypeError`` rather than a ``LayoutError``, and an empty dict would
    # render zero bytes, so both are refused before WP5b is even asked.
    _require(type(prepared_record) is dict, "prepared record must be an object")
    _require(bool(prepared_record), "prepared record must be a non-empty object")
    prepared = _validated_provenance(prepared_record)
    # The return matrix is checked for TYPE and LENGTH here, before anything else
    # touches it.  This used to be inherited from ``build_generation_payload``,
    # but ``write_instance`` now renders the generation files itself (so the
    # bytes it hashes for the index are the bytes it writes), which means the
    # payload builder is no longer on this path.  Without an explicit check here a
    # short or wrongly-typed matrix would be written and promoted: the READ side
    # would catch it in ``validate_generation_directory``, but an instance that can
    # be written and only then refused is a bad boundary, not a safe one.
    _require(type(return_matrix) is bytes, "return matrix payload must be bytes")
    _require(len(return_matrix) == RETURN_MATRIX_BYTES,
             f"return matrix payload must be exactly {RETURN_MATRIX_BYTES} bytes")
    # The identity the prepared record claims must be the identity the generation
    # record will carry.  Compared as a separate statement from the validation
    # above, because WP5b's validator legitimately accepts a well-formed record
    # naming any instance: it checks the record's internal consistency, not which
    # instance of a layout this is.
    _require(_prepared_instance_id(prepared) == instance_id,
             "prepared record instance_id disagrees with the instance being written")
    supported = prepared["non_synthetic_supported"]
    prepared_bytes = _canonical(prepared)
    prepared_sha256 = _bytes_sha256(prepared_bytes, "prepared record")
    return_matrix_sha256 = _bytes_sha256(return_matrix, "return matrix")
    # The two records are rendered HERE, once each, and the resulting canonical
    # bytes are both what gets written and what the index is bound to.  Rendering
    # them twice -- once here to hash and again inside build_generation_payload to
    # write -- would be a latent divergence: the index would commit to a hash of
    # one rendering while the file held another, and the mismatch would only ever
    # surface as an unreadable instance after it had been promoted.
    #
    # Both are built before staging.mkdir(), so a rejected history or a malformed
    # moment encoding is refused before a single directory is created.
    ledger = build_attempt_record(
        slot=slot, attempt=attempt, sector_partition_sha256=sector_partition_sha256,
        feasible_count=feasible_count, rejected_attempt_history=rejected_attempt_history)
    ledger_bytes = _canonical(ledger)
    generation_record = build_generation_record(
        slot=slot, attempt=attempt, instance_id=instance_id,
        return_matrix_sha256=return_matrix_sha256,
        implementation_record_content_sha256=implementation_record_content_sha256,
        mu_new=mu_new, sigma_new=sigma_new)
    generation_bytes = _canonical(generation_record)
    moments = generation_record["moment_summary"]

    parent = Path(root) / INSTANCE_ROOT
    _require_real_dir(parent, "instance root")
    destination = slot_dir(slot, root=root)
    _require_absent(destination, "instance directory")

    generation_files = {
        ATTEMPT_NAME: ledger_bytes,
        GENERATION_NAME: generation_bytes,
        RETURN_MATRIX_NAME: return_matrix,
    }

    staging = parent / f"{STAGING_PREFIX}{os.getpid()}-{slot_name(slot)}"
    _require_absent(staging, "staging path")
    try:
        staging.mkdir()
    except OSError as exc:
        raise LayoutError(f"cannot create staging directory: {exc.__class__.__name__}") from exc
    try:
        generation = _as_layout(_writer.write_generation,
                                target=staging / GENERATION_DIR_NAME, files=generation_files,
                                implementation_record_content_sha256=implementation_record_content_sha256)
        sidecar = _as_layout(_writer.write_generation,
                             target=staging / PREPARED_DIR_NAME,
                             files={"PREPARED.json": prepared_bytes},
                             implementation_record_content_sha256=implementation_record_content_sha256)
        index = build_instance_index(
            slot=slot, attempt=attempt, instance_id=instance_id,
            prepared_record_sha256=prepared_sha256,
            prepared_record_status=prepared["status"],
            non_synthetic_supported=supported,
            prepared_manifest_sha256=_sha_file(
                staging / PREPARED_DIR_NAME / MANIFEST_NAME, "prepared manifest"),
            prepared_manifest_content_sha256=sidecar["manifest_content_sha256"],
            generation_manifest_sha256=_sha_file(
                staging / GENERATION_DIR_NAME / MANIFEST_NAME, "generation manifest"),
            generation_manifest_content_sha256=generation["manifest_content_sha256"],
            attempt_record_sha256=_bytes_sha256(ledger_bytes, "attempt record"),
            attempt_record_content_sha256=ledger["content_sha256"],
            attempt_disposition=ledger["disposition"],
            rejection_code_count=len(ledger["rejection_codes"]),
            rejected_attempt_history_count=len(ledger["rejected_attempt_history"]),
            mu_new_sha256=moments["mu_new"]["sha256"],
            sigma_new_sha256=moments["sigma_new"]["sha256"],
            implementation_record_content_sha256=implementation_record_content_sha256)
        meta = _as_layout(_writer.write_generation,
                          target=staging / META_DIR_NAME, files={INDEX_NAME: _canonical(index)},
                          implementation_record_content_sha256=implementation_record_content_sha256)
        _promote(staging, destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    # Durability, in the order WP5 itself uses (destination before its parent,
    # ``stage2_generation_writer.py:318-319``).  A refusal HERE is after the
    # rename has already happened, so the promoted directory is rolled back:
    # otherwise a caller that saw ``LayoutError`` would still find
    # ``stage2_NN/`` on disk, and could not retry because the slot now exists.
    # The rollback is the whole directory rename brought back to staging, so a
    # rollback that itself fails is reported as its own error rather than
    # silently leaving a half-state.
    try:
        _fsync_dir(destination)
        _fsync_dir(parent)
    except BaseException as exc:
        try:
            os.rename(str(destination), str(staging))
        except OSError as rollback_exc:
            raise LayoutError(
                f"durability failed after promotion and the rollback to staging also "
                f"failed; {destination} is present and must be inspected by hand: "
                f"{rollback_exc.__class__.__name__}") from exc
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "target": str(destination),
        "verdict": "written",
        "slot": slot,
        "slot_name": slot_name(slot),
        "attempt": attempt,
        "instance_id": instance_id,
        "index": index,
        "index_content_sha256": index["content_sha256"],
        "generation_manifest_sha256": index["generation"]["manifest_sha256"],
        "generation_manifest_content_sha256": generation["manifest_content_sha256"],
        "prepared_manifest_sha256": index["prepared_record"]["manifest_sha256"],
        "prepared_manifest_content_sha256": sidecar["manifest_content_sha256"],
        # The meta manifest's bytes are NOT in the index (that would be circular:
        # it commits to the index).  They are returned here so an owner approval
        # or the WP8 bundle can bind them externally.  See the note above
        # PREPARED_REF_KEYS.
        "meta_manifest_sha256": _sha_file(destination / META_DIR_NAME / MANIFEST_NAME,
                                          "meta manifest"),
        "meta_manifest_content_sha256": meta["manifest_content_sha256"],
        "implementation_record_content_sha256": implementation_record_content_sha256,
        "prepared_record_sha256": prepared_sha256,
        "prepared_record_status": prepared["status"],
        "prepared_record_instance_id": _prepared_instance_id(prepared),
        "return_matrix_sha256": return_matrix_sha256,
        "attempt_record_sha256": _bytes_sha256(ledger_bytes, "attempt record"),
        "attempt_record_content_sha256": ledger["content_sha256"],
        "attempt_disposition": ledger["disposition"],
        "rejected_attempt_history_count": len(ledger["rejected_attempt_history"]),
        "mu_new_sha256": moments["mu_new"]["sha256"],
        "sigma_new_sha256": moments["sigma_new"]["sha256"],
        "mu_new_encoding": moments["mu_new"]["encoding"],
        "file_count": generation["file_count"] + sidecar["file_count"] + 2,
    }
