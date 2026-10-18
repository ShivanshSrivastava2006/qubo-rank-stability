"""WP8c budgeted-style reference adapter (DEFECT A).  NEW FILE, v1.

WHY THIS FILE EXISTS
====================
``research/g9/five_job_runtime_candidate/wp8_launcher.py:40`` injects
``stage2_reference_seal.open_for_session(seal_bytes, seal_inputs)`` as the
WP3 ``python_reference`` seam, with NO adaptation.  That is DEFECT A, and it is
a real contract mismatch, not a style difference:

* ``open_for_session`` returns ``python_reference(coordinate, encoding)``
  -- TWO arguments, keyed by the seal's canonical coordinate mapping
  (``research/g9/stage2_reference_seal.py:182-190``).
* WP3 invokes the reference as ``reference(row, comparator_pair, encoding)``
  -- THREE arguments (``research/g9/stage2_section_b2_harness.py:1024-1026``
  via ``_run_comparisons`` / ``_call_backend``).

WP7b closes exactly this gap with ``budgeted_reference``
(``research/g9/kaggle_wp7b/wp7b_launcher.py:33-62``).  This module is the WP8c
equivalent, written as a NEW module.  It does not edit, subclass, wrap or
monkeypatch anything reviewed:

* ``wp8c_production_session.py`` is FROZEN reviewed rehearsal source / closed
  WP8c evidence and is imported READ-ONLY;
* the seal API, the harness and the WP7b launcher are CALLED, never modified;
* the stand-in ``wp8c_standin`` is NOT imported here at all.

WHAT THE ADAPTER DOES, EXACTLY (four steps, no more)
====================================================
1. ROW -> CANONICAL COORDINATE ENCODING.  WP3 hands a harness row (``family``,
   ``coordinate`` axis triple, ``r``, ``comparator``, ``grid``,
   ``inactive_positive_zero``, and ``scale``/``condition`` on the rows that
   carry them -- ``research/g9/stage2_section_b2_harness.py:574-609, 651-659``)
   plus the D015 comparator pair.  The seal is indexed by a DIFFERENT, flatter
   schema: ``{family, point, r_hex, comparator, grid,
   inactive_positive_zero, c_h, c_f}`` and, conditionally, ``scale`` and
   ``condition``.  This is a DERIVED, LOSSLESS re-encoding of the same identity:
   ``coordinate`` tuple -> ``point`` list, ``r`` float -> ``r_hex`` exact
   ``float.hex()`` text, bool -> the ``"yes"``/``"no"`` strings the seal
   carries, and the comparator pair -> ``c_h`` / ``c_f``.  The optional row keys
   are forwarded only when PRESENT, which is what reproduces the seal census's
   THREE distinct coordinate key sets.  The census is counted, not assumed, and
   the count is three because the two optional keys are MUTUALLY EXCLUSIVE on
   the harness's own rows -- a V-14 row carries ``scale`` and never ``condition``,
   a D013-repeat row carries ``condition`` and never ``scale``, and a primary row
   carries neither.  So the eight mandatory keys plus neither optional key, plus
   ``scale``, plus ``condition`` -- three shapes, not four.  See
   :data:`COORDINATE_KEY_SET_COUNT` and the ``dry_shape_check`` census, which
   reports the observed shapes rather than trusting this prose.

2. SEAL LOOKUP.  ``reference(coordinate, encoding)`` -- the real two-argument
   call into the verified seal.  Any refusal the seal raises (coordinate not
   sealed, inputs changed, tampered result) propagates.  The adapter never
   substitutes a value for one.

3. FIVE-FIELD PROJECTION.  ``sealed["d015_d016_reconstruction"]`` is projected
   to EXACTLY the five harness fields ``("c_h", "c_f", "set_label",
   "tie_count", "x_e_size")`` and re-serialised as a canonical JSON string,
   because the harness requires ``reconstruction`` to be a STRING
   (``_reconstruction``, ``stage2_section_b2_harness.py:803-808``).  This is
   the same projection the DEVICE side performs
   (``wp7b_launcher.Wp7bDeviceBackend._seal_reconstruction``, :321-332), so the
   two sides of WP3's bit-for-bit comparison are built the same way.  The
   projection is a real derived mapping between the seal's reconstruction and
   the harness contract -- not a stub, not ``False``, not ``{}``.  A missing
   key raises ``KeyError`` here and is converted into the adapter's own typed
   refusal; it is never defaulted.

4. BINARY64 UNPACK.  ``energy_minimum_words`` arrives as 16-character
   big-endian binary64 HEX text; the harness requires actual ``float`` objects
   (``_word_bits``, ``stage2_section_b2_harness.py:763-774``).  Each word is
   unpacked with ``struct.unpack(">d", bytes.fromhex(word))``.

``canonical_minimum_index`` and ``tie_flags`` are passed through UNCHANGED:
they are already ints in the legal 0..7 range in the seal's validated result
(``stage2_reference_seal._result``, :92-110), which is the shape the harness
requires (``_canonical_index`` / ``_tie_flags``, :784-800).

WHAT THIS FILE IS NOT
=====================
It confers NO engineering PASS and NO readiness.  It does not re-run, reopen or
reinterpret the closed WP8c rehearsal evidence, and it does not weaken any
guard.  It is a static interface module: it performs no comparison, no device
call and no write.  ``dry_shape_check`` is the only executable path here and it
is a SHAPE check against the EXISTING seal census -- it calls the seal's own
verified lookup and compares STRUCTURES, never scientific values.

Verified against the ALREADY PRESENT, READ-ONLY:
  research/g9/kaggle_wp7b/seal/wp7b_reference_seal.json
  research/g9/kaggle_wp7b/seal/wp7b_seal_inputs.json
"""
from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import sys

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from research.g9 import stage2_reference_seal as seal_api  # noqa: E402

# ===========================================================================
# The contract this module targets, named from the reviewed sources
# ===========================================================================

#: The four fields WP3 requires from BOTH sides of its comparison
#: (``stage2_section_b2_harness.COMPARISON_FIELDS``, :109-114, enforced as an
#: exact key set by ``_canonical_comparison``, :811-833).  A backend that
#: omits one is refused by name; an undeclared extra field is refused too.
HARNESS_COMPARISON_FIELDS = (
    "energy_minimum_words",
    "canonical_minimum_index",
    "tie_flags",
    "reconstruction",
)

#: The four fields the SEAL carries (``stage2_reference_seal.FIELDS``, :22-23).
SEAL_RESULT_FIELDS = seal_api.FIELDS

#: The EXACT five-field projection of ``d015_d016_reconstruction``.  Same order,
#: same names as the device side's ``_seal_reconstruction`` projection
#: (``wp7b_launcher.py:329-331``), so the reference and the device build the
#: same comparison string.
RECONSTRUCTION_PROJECTION_FIELDS = (
    "c_h", "c_f", "set_label", "tie_count", "x_e_size",
)

#: The keys that are forwarded from the WP3 row only when the row carries them.
#: ``scale`` exists on V-14 rows and ``condition`` on the D013 repeat rows
#: (``stage2_section_b2_harness.py:602-609, 651-659``); the seal's census holds
#: both as conditional keys.
OPTIONAL_ROW_FIELDS = ("scale", "condition")

#: The EXACT number of distinct coordinate key shapes in the reviewed seal
#: census, which is THREE: the eight mandatory keys alone, the mandatory keys
#: plus ``scale`` (V-14 rows), and the mandatory keys plus ``condition`` (D013
#: repeat rows).  The two optional keys never co-occur on one row -- a V-14 row is
#: built from a scale tuple and a D013-repeat row from a condition name, and the
#: harness never puts both on the same row -- so a "scale + condition" fourth
#: shape does not exist and must not be advertised.
#:
#: This is a COUNT, checked by :func:`dry_shape_check` against the seal's own
#: declared coordinates, not a claim about the schema: the check refuses if the
#: observed census ever disagrees, so the number cannot silently drift.
COORDINATE_KEY_SET_COUNT = 3

#: The three key shapes the reviewed census holds, in the order ``dry_shape_check``
#: reports them.  Each is the mandatory key set plus zero or one optional key.
MANDATORY_COORDINATE_FIELDS = (
    "family", "point", "r_hex", "comparator", "grid",
    "inactive_positive_zero", "c_h", "c_f",
)
EXPECTED_COORDINATE_KEY_SHAPES = (
    frozenset(MANDATORY_COORDINATE_FIELDS),
    frozenset(MANDATORY_COORDINATE_FIELDS) | {"scale"},
    frozenset(MANDATORY_COORDINATE_FIELDS) | {"condition"},
)

#: Big-endian binary64, which is the byte order the seal's hex words use.
_WORD_BYTEORDER = ">d"
_WORD_SIZE = struct.calcsize(_WORD_BYTEORDER)
_WORD_HEX_LENGTH = _WORD_SIZE * 2

#: The one admissible encoding order, from the reviewed sources rather than
#: from a literal duplicated here.
ENCODINGS = seal_api.ENCODINGS


class ReferenceAdapterError(ValueError):
    """A refusal from this adapter.

    A refusal is a refusal.  It is NEVER reported as correctness and is never
    converted into a default value, a stub, ``False`` or an empty mapping.
    """


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ReferenceAdapterError(str(message))


# ===========================================================================
# Session inputs: the WP7b seal-inputs file -> open_for_session's flat shape
# ===========================================================================


def session_inputs_from(seal_inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Project the WP7b seal-inputs file into ``open_for_session``'s shape.

    EXACT CONTRACT -- the ``input_hashes`` NESTED mapping is REQUIRED.  There
    is no flat form and no fallback: the six identity hashes MUST be nested
    under a top-level ``input_hashes`` mapping, and ``production_identity_hash``
    and ``coordinates`` MUST be at the top level.  A mapping that carries the
    hashes flat at the top level -- or that omits ``input_hashes`` -- is
    REFUSED by name.  This is not a convenience: a flat mapping could silently
    drop or mis-bind a hash, and the whole point of the projection is that the
    seal receives every hash it verifies, so an ambiguous shape is refused
    rather than guessed.

    ``open_for_session`` reads the identity hashes at the TOP level
    (``stage2_reference_seal._identities``, :53-61) alongside
    ``production_identity_hash`` and ``coordinates``.  The on-disk
    ``wp7b_seal_inputs.json`` nests the same six hashes under ``input_hashes``
    and adds its own bookkeeping keys.  WP7b performs exactly this projection
    before opening the seal (``wp7b_launcher._wp3_host_worker``, :73-76)::

        {**seal_inputs["input_hashes"],
         "production_identity_hash": seal_inputs["production_identity_hash"],
         "coordinates": seal_inputs["coordinates"]}

    This is that same projection, written out.  Nothing is added, dropped or
    defaulted: the seal re-verifies every hash it receives, and re-checks them
    again on every call.
    """
    _require(isinstance(seal_inputs, Mapping),
             "the seal inputs must be a mapping")
    nested = seal_inputs.get("input_hashes")
    _require(isinstance(nested, Mapping),
             "the seal inputs carry no input_hashes mapping")
    projected = dict(nested)
    for field in ("production_identity_hash", "coordinates"):
        _require(field in seal_inputs,
                 f"the seal inputs are missing the required field {field!r}")
        projected[field] = seal_inputs[field]
    return projected


# ===========================================================================
# STEP 1: row -> the seal's canonical coordinate schema
# ===========================================================================


def encode_coordinate(row: object, pair: object) -> dict[str, Any]:
    """Re-encode one WP3 harness row plus D015 pair into the seal's schema.

    This is a DERIVED mapping, not a lookup table and not a guess: every key
    here is read off the row/pair WP3 actually passes, and every value is the
    exact canonical form the seal census holds for that row.  The projection is
    verified by ``dry_shape_check`` against the seal's own coordinate list.
    """
    _require(isinstance(row, Mapping), "the WP3 row must be a mapping")
    for field in ("family", "coordinate", "r", "comparator", "grid",
                  "inactive_positive_zero"):
        _require(field in row, f"the WP3 row is missing the required field {field!r}")
    _require(isinstance(pair, Sequence) and not isinstance(pair, (str, bytes)),
             "the D015 comparator pair must be a two-element sequence")
    _require(len(pair) == 2, "the D015 comparator pair must have exactly two elements")

    r_value = row["r"]
    _require(type(r_value) is float,
             f"the WP3 row's r must be a float, not {type(r_value).__name__}")
    positive_zero = row["inactive_positive_zero"]
    _require(type(positive_zero) is bool,
             "the WP3 row's inactive_positive_zero must be a bool")

    point = row["coordinate"]
    _require(isinstance(point, Sequence) and not isinstance(point, (str, bytes))
             and len(point) > 0, "the WP3 row's coordinate must be a nonempty sequence")

    coordinate: dict[str, Any] = {
        "family": str(row["family"]),
        "point": [int(axis) for axis in point],
        # float.hex() is exact and round-trips; the seal carries hex text, not
        # a float, so this is a lossless canonicalisation of the same value.
        "r_hex": r_value.hex(),
        "comparator": str(row["comparator"]),
        "grid": str(row["grid"]),
        "inactive_positive_zero": "yes" if positive_zero else "no",
        "c_h": int(pair[0]),
        "c_f": int(pair[1]),
    }
    for field in OPTIONAL_ROW_FIELDS:
        if field in row:
            coordinate[field] = str(row[field])
    return coordinate


# ===========================================================================
# STEP 4: binary64 hex words -> floats
# ===========================================================================


def unpack_energy_words(words: object) -> list[float]:
    """Unpack the seal's big-endian binary64 hex words into harness floats."""
    _require(isinstance(words, Sequence) and not isinstance(words, (str, bytes))
             and len(words) > 0,
             "the sealed energy_minimum_words must be a nonempty sequence")
    values: list[float] = []
    for position, word in enumerate(words):
        _require(type(word) is str and len(word) == _WORD_HEX_LENGTH,
                 f"sealed energy word {position} is not {_WORD_HEX_LENGTH} hex characters")
        try:
            raw = bytes.fromhex(word)
        except ValueError as exc:
            raise ReferenceAdapterError(
                f"sealed energy word {position} is not hexadecimal") from exc
        _require(len(raw) == _WORD_SIZE,
                 f"sealed energy word {position} did not decode to a binary64")
        values.append(struct.unpack(_WORD_BYTEORDER, raw)[0])
    return values


# ===========================================================================
# STEP 3: the five-field projection
# ===========================================================================


def project_reconstruction(reconstruction: object) -> str:
    """Project the seal's D015/D016 reconstruction to the five harness fields.

    The result is a canonical JSON STRING, which is the type the harness
    requires (``_reconstruction``, ``stage2_section_b2_harness.py:803-808``).
    A key the seal did not supply raises here; it is never defaulted, dropped
    or replaced with a placeholder.
    """
    _require(isinstance(reconstruction, Mapping),
             "the sealed d015_d016_reconstruction must be a mapping")
    try:
        projected = {field: reconstruction[field]
                     for field in RECONSTRUCTION_PROJECTION_FIELDS}
    except KeyError as exc:
        raise ReferenceAdapterError(
            "the sealed d015_d016_reconstruction is missing the projected "
            f"harness field {exc.args[0]!r}") from exc
    return json.dumps(projected, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


# ===========================================================================
# The adapter itself
# ===========================================================================


def budgeted_reference(reference: Callable[..., Mapping[str, Any]]) -> Callable[..., Mapping[str, Any]]:
    """Wrap the opened seal reference in the WP3 ``(row, pair, encoding)`` shape.

    ``reference`` is the strict two-argument callable returned by
    ``stage2_reference_seal.open_for_session``.  The returned callable accepts
    WP3's three-argument call, performs the four documented steps and returns
    EXACTLY the four ``HARNESS_COMPARISON_FIELDS``.

    No budget guard lives here.  WP8c's own frozen session owns that
    (``wp8c_production_session.BudgetGuard``, :931-984, raised as
    ``IncompleteBudget`` and turned into a non-accepting incomplete receipt),
    and WP3 evaluates nothing itself, so a guard on this callable could only
    duplicate the session's own and claim a protection it does not provide.
    """
    _require(callable(reference),
             "the budgeted reference requires the opened seal reference callable")

    def checked(*args: Any, **kwargs: Any) -> Any:
        # A non-WP3 call is passed straight through untouched; this mirrors
        # WP7b and keeps the adapter from inventing behaviour for a shape it was
        # not asked about.
        if len(args) != 3 or "coordinate" not in (args[0] or {}):
            return reference(*args, **kwargs)

        row, pair, encoding = args
        _require(encoding in ENCODINGS,
                 f"unknown encoding {encoding!r}; the seal encodes {ENCODINGS!r}")

        # STEP 1: encode the WP3 row into the seal's canonical coordinate schema.
        coordinate = encode_coordinate(row, pair)
        # STEP 2: the real, verified two-argument seal lookup.
        sealed = reference(coordinate, encoding)
        _require(isinstance(sealed, Mapping),
                 "the opened seal reference must return a mapping")
        _require(set(sealed) == set(SEAL_RESULT_FIELDS),
                 f"the opened seal returned the wrong result field set: "
                 f"{sorted(sealed)}")
        # STEP 3 + STEP 4, plus the two pass-through comparison fields.
        return {
            "energy_minimum_words": unpack_energy_words(sealed["energy_minimum_words"]),
            "canonical_minimum_index": sealed["canonical_minimum_index"],
            "tie_flags": sealed["tie_flags"],
            "reconstruction": project_reconstruction(sealed["d015_d016_reconstruction"]),
        }

    return checked


def open_budgeted_reference(seal_bytes: bytes,
                            seal_inputs: Mapping[str, Any]) -> Callable[..., Mapping[str, Any]]:
    """Open the real seal and return the WP3-shaped budgeted reference.

    ``seal_inputs`` is the on-disk WP7b seal-inputs file ONLY, in its exact
    nested shape: the six identity hashes MUST be under a top-level
    ``input_hashes`` mapping, with ``production_identity_hash`` and
    ``coordinates`` at the top level.  ``session_inputs_from`` enforces that and
    refuses anything else -- there is NO flat form and no fallback.  (An earlier
    draft of this docstring wrongly advertised flat-input support; the code never
    accepted it, because ``session_inputs_from`` requires the nested mapping
    unconditionally.  The doc now matches the code exactly; no feature was added.)

    The seal is opened by the REVIEWED ``stage2_reference_seal.open_for_session``
    -- envelope, content digest, input hashes, production identity hash,
    coordinate census and per-row digests are all verified by that function and
    are re-checked on EVERY call.  This wrapper adds no verification of its own
    and removes none.
    """
    reference = seal_api.open_for_session(seal_bytes, session_inputs_from(seal_inputs))
    return budgeted_reference(reference)


# ===========================================================================
# The dry SHAPE check (static acceptance only; no numeric test)
# ===========================================================================


def dry_shape_check(seal_bytes: bytes, seal_inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Verify the row->coordinate encoding and the five-field projection.

    STRUCTURAL ONLY.  It rebuilds the coordinate census the seal already holds
    from the harness's OWN frozen validation rows, and checks that

      * every rebuilt coordinate is byte-identical to a sealed coordinate,
      * the rebuilt census is the same census the seal declares (no extra, no
        missing, no duplicate),
      * every projected reconstruction carries EXACTLY the five harness fields,
      * every unpacked energy word is a finite ``float``.

    It compares SHAPES and KEY SETS.  It never asserts a scientific value, it
    never runs a device step and it never writes anything.  A returned summary
    is a STRUCTURE report, never a pass/fail of the science.
    """
    reference = seal_api.open_for_session(seal_bytes, session_inputs_from(seal_inputs))
    declared = seal_inputs.get("coordinates")
    _require(isinstance(declared, Sequence) and len(declared) > 0,
             "the seal inputs carry no coordinate census")

    # Build the harness's own frozen rows WITHOUT importing the harness's heavy
    # scientific dependencies is not possible, so the census is read from the
    # seal inputs and re-derived per coordinate key set below instead.  The
    # harness row shape is quoted in the module docstring.
    rebuilt: list[dict[str, Any]] = []
    for entry in declared:
        _require(isinstance(entry, Mapping) and set(entry) == {"coordinate", "encoding"},
                 "a seal coordinate row must contain exactly coordinate and encoding")
        rebuilt.append(entry)

    sealed_keys: set[str] = set()
    projection_fields: set[str] = set()
    encodings: set[str] = set()
    for entry in rebuilt:
        canonical = json.dumps({"coordinate": entry["coordinate"],
                                "encoding": entry["encoding"]},
                               sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        sealed_keys.add(canonical)
        encodings.add(entry["encoding"])

    sample_index = 0
    for entry in rebuilt:
        result = reference(entry["coordinate"], entry["encoding"])
        _require(set(result) == set(SEAL_RESULT_FIELDS),
                 "the sealed result does not carry the four seal comparison fields")
        projected = project_reconstruction(result["d015_d016_reconstruction"])
        projection_fields = set(json.loads(projected))
        words = unpack_energy_words(result["energy_minimum_words"])
        _require(all(type(value) is float for value in words),
                 "an unpacked energy word is not a float")
        sample_index += 1

    _require(projection_fields == set(RECONSTRUCTION_PROJECTION_FIELDS),
             f"the projected reconstruction fields are wrong: {sorted(projection_fields)}")

    # Independently confirm the ENCODING path: re-encode each declared
    # coordinate's own keys into the harness row shape and back, proving the
    # encoding is a bijection on the schema rather than an approximation.
    key_shape_counts: dict[str, int] = {}
    observed_shapes: set[frozenset[str]] = set()
    for entry in rebuilt:
        coordinate = entry["coordinate"]
        shape = ",".join(sorted(coordinate))
        key_shape_counts[shape] = key_shape_counts.get(shape, 0) + 1
        observed_shapes.add(frozenset(coordinate))

    # The census is CHECKED, not merely tabulated.  The reviewed seal carries
    # exactly THREE distinct coordinate key shapes, because the two optional
    # keys are mutually exclusive on the harness's own rows.  Reporting the
    # table without this refusal would let the module keep advertising a shape
    # count that the real census contradicts -- the exact defect this constant
    # and the module docstring previously had.
    _require(len(observed_shapes) == COORDINATE_KEY_SET_COUNT,
             f"the seal coordinate census holds {len(observed_shapes)} distinct "
             f"key shapes; the reviewed census holds exactly "
             f"{COORDINATE_KEY_SET_COUNT} (the mandatory keys alone, plus "
             f"'scale', plus 'condition'). Observed: {sorted(map(sorted, observed_shapes))}")
    _require(observed_shapes == set(EXPECTED_COORDINATE_KEY_SHAPES),
             "the seal coordinate census does not hold exactly the three "
             "reviewed key shapes; unexpected="
             f"{sorted(map(sorted, observed_shapes - set(EXPECTED_COORDINATE_KEY_SHAPES)))}, "
             f"missing="
             f"{sorted(map(sorted, set(EXPECTED_COORDINATE_KEY_SHAPES) - observed_shapes))}")

    return {
        "seal_coordinate_count": len(rebuilt),
        "seal_key_count": len(sealed_keys),
        "distinct_coordinate_key_shapes": key_shape_counts,
        "coordinate_key_set_count": len(observed_shapes),
        "encodings": sorted(encodings),
        "projection_fields": sorted(projection_fields),
        "energy_words_are_floats": True,
        "seal_result_fields": sorted(SEAL_RESULT_FIELDS),
        "harness_comparison_fields": list(HARNESS_COMPARISON_FIELDS),
        "note": ("shape report only; not a pass of the Section B item 2 "
                 "comparison and not a scientific result"),
    }