#!/usr/bin/env python3
"""Full fixtures for the WP8d drawn-instance artifact layout.

Everything happens inside ``tempfile.TemporaryDirectory`` under the job scratch
directory.  The project tree is never written to and is never used as a
generation target or staging parent.  No generator draw, no production seed and
no production beacon is used: every fixture value is either a constant invented
here or the generator's own *seed derivation* (``stream_seed``), which hashes
declared ASCII material and samples nothing.  The return-matrix bytes are
deterministic synthetic filler, NOT a draw of returns or covariance.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
SCRATCH = Path("/home/shivansh-srivastava/decisions_os/g9_jobs/scratch/wp8d")
PYC_BEFORE = set(ROOT.rglob("*.pyc"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9.wp8d import wp8d_drawn_instance_layout as L  # noqa: E402
from research.g9 import stage2_instance_preparation as P  # noqa: E402

SCRATCH.mkdir(parents=True, exist_ok=True)

COUNT = 0
FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    global COUNT
    if not condition:
        raise AssertionError(message)
    COUNT += 1


def refuses(call, needle: str, label: str) -> None:
    """Assert ``call`` leaves through the typed LayoutError for ``needle``."""
    global COUNT
    try:
        call()
    except L.LayoutError as exc:
        if needle and needle not in str(exc):
            FAILURES.append(f"{label}: refused for the wrong reason: {exc}")
            return
        COUNT += 1
        return
    except Exception as exc:  # noqa: BLE001 - the point is to catch leaks
        FAILURES.append(f"{label}: raw {type(exc).__name__} instead of LayoutError: {exc}")
        return
    FAILURES.append(f"{label}: accepted")


def fake(tag: str) -> str:
    return hashlib.sha256(tag.encode("ascii")).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


RECORD = fake("wp8d-synthetic-implementation-record-NOT-PRODUCTION")
OTHER_RECORD = fake("wp8d-other-implementation-record-NOT-PRODUCTION")
PARTITION = fake("wp8d-synthetic-sector-partition-NOT-A-DRAW")
INSTANCE_ID = "stage2_01-SYNTHETIC-NOT-A-REAL-DRAW"
SLOT = 1
ATTEMPT = 0

#: Deterministic synthetic filler of exactly the right length.  NOT a draw.
MATRIX = bytes((index * 37 + 11) % 256 for index in range(L.RETURN_MATRIX_BYTES))
MATRIX_SHA = hashlib.sha256(MATRIX).hexdigest()

# ---------------------------------------------------------------------------
# Synthetic FIXED vectors for the recorded U-09 moments.
# ---------------------------------------------------------------------------
# These are NOT a draw, NOT a covariance and NOT derived from the matrix above.
# They are hand-picked constants in the exact spelling the reviewed generator
# emits -- CPython ``float.hex()`` -- standing in for ``ReturnDraw.mu_hex`` and
# ``ReturnDraw.sigma_hex`` so the layout's record can be exercised without ever
# sampling anything.  They are deliberately NOT the all-zero or constant vector:
# a constant one would make a row/column mix-up undetectable, and these fixtures
# exist to catch exactly that.
#: A fixed synthetic mu vector of ASSET_COUNT canonical binary64 encodings.
MU_NEW = [f"0x1.{index:013x}p-{index % 7 + 1}" for index in range(L.MU_NEW_DIM)]
#: A fixed synthetic 20x20 symmetric covariance, row-major.  Values are synthetic
#: placeholders on the diagonal and small off-diagonal constants; they are NOT
#: claimed to be PSD, because nothing here computes an eigenvalue.
SIGMA_NEW = [[
    f"0x1.{(index * 31 + column * 17) % 4096:012x}p-8" if index == column
    else f"0x1.{(index + column) % 512:011x}p-12"
    for column in range(L.SIGMA_NEW_COLS)]
    for index in range(L.SIGMA_NEW_ROWS)]
#: The expected block digests, computed here independently of the layout's own
#: digest code, so a fixture can prove the digest is the hash of the canonical
#: ENCODED TEXT and not of some internal representation.
MU_NEW_SHA = hashlib.sha256("".join(MU_NEW).encode("ascii")).hexdigest()
SIGMA_NEW_SHA = hashlib.sha256("".join(v for row in SIGMA_NEW for v in row)
                              .encode("ascii")).hexdigest()

#: A fixed synthetic rejected-attempt history: attempts 0 and 1 rejected before an
#: attempt 2 is accepted, carrying fixed codes from the generator's set.  The
#: digests and counts are synthetic too.
HISTORY = [
    {"attempt": 0, "rejection_codes": ["feasible_set_below_100"],
     "sector_partition_sha256": fake("rejected-partition-0"), "feasible_count": 42},
    {"attempt": 1, "rejection_codes": ["partition_matches_stage1"],
     "sector_partition_sha256": fake("rejected-partition-1"), "feasible_count": 118},
]
HISTORY_DIGEST = fake("rejected-history-digest")

#: The accepted attempt number used by every fixture: 2, so the retained rejected
#: history (0 and 1) is non-empty and the ordering rule is actually exercised.
#: A fixture written at attempt 0 would have an empty history and would therefore
#: never test the ordering constraint at all.
ACCEPTED_ATTEMPT = 2


def prepared(status: str = L.PREPARED_STATUS,
             supported: bool = False,
             instance_id: str = INSTANCE_ID) -> dict[str, object]:
    """A prepared record that the REAL WP5b validator accepts.

    A prior revision of this fixture hand-rolled a three-key record
    (``schema``/``status``/``non_synthetic_supported``) that WP5b's
    ``validate_provenance_record`` refuses outright
    (``stage2_instance_preparation.py:814-817``): it has the wrong key set and no
    content hash.  That was possible only because ``write_instance`` did not call
    the real validator.  Now that it does, the shared helper MUST emit a record
    WP5b accepts, or every existing test would be testing a refusal instead of a
    write.  This is the shape ``build_provenance_record`` emits
    (``stage2_instance_preparation.py:764-798``), with conspicuous non-production
    values and no optimisation run: ``results`` and ``ledgers`` are empty
    mappings and ``source_sha256`` names a single fake source.

    ``status``/``supported``/``instance_id`` stay parameterised so the existing
    refusal tests keep working: a bad value here is a record WP5b OR this layout
    refuses, and the assertion names which.
    """
    record: dict[str, object] = {
        "schema": P.PROVENANCE_SCHEMA,
        "status": status,
        "non_synthetic_supported": supported,
        "instance": {"instance_id": instance_id,
                     "content_sha256": fake("wp8d-synthetic-instance-digest-NOT-A-DRAW"),
                     "n_assets": 20},
        "results": {},
        "ledgers": {},
        "f_predicate": "synthetic fixture predicate, not a real f",
        "f_predicate_sha256": fake("wp8d-synthetic-predicate-NOT-A-DRAW"),
        "source_sha256": {"wp8d-synthetic-source.py": fake("wp8d-synthetic-source")},
        "scientific_outputs": "intentionally absent",
    }
    body = dict(record)
    record["content_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True).encode("ascii")).hexdigest()
    return record


def make_root() -> Path:
    root = Path(tempfile.mkdtemp(dir=SCRATCH, prefix="wp8d-root-"))
    (root / "research" / "g9" / L.INSTANCE_ROOT.split("/")[-1]).mkdir(parents=True)
    return root


def generation_record_ok(**overrides) -> dict[str, object]:
    """A GENERATION.json the real validator accepts, with the fixed vectors."""
    kwargs = dict(slot=SLOT, attempt=ACCEPTED_ATTEMPT, instance_id=INSTANCE_ID,
                  return_matrix_sha256=MATRIX_SHA,
                  implementation_record_content_sha256=RECORD,
                  mu_new=MU_NEW, sigma_new=SIGMA_NEW)
    kwargs.update(overrides)
    return L.build_generation_record(**kwargs)


def index_ok(**overrides) -> dict[str, object]:
    """An INSTANCE.json the real validator accepts, with the fixed vectors."""
    kwargs = dict(
        slot=SLOT, attempt=ACCEPTED_ATTEMPT, instance_id=INSTANCE_ID,
        prepared_record_sha256=fake("prepared"), prepared_record_status=L.PREPARED_STATUS,
        non_synthetic_supported=False,
        prepared_manifest_sha256=fake("prepared-manifest-bytes"),
        prepared_manifest_content_sha256=fake("prepared-manifest-content"),
        generation_manifest_sha256=fake("manifest-bytes"),
        generation_manifest_content_sha256=fake("manifest-content"),
        attempt_record_sha256=fake("ledger-bytes"),
        attempt_record_content_sha256=fake("ledger-content"),
        attempt_disposition=L.DISPOSITION_ACCEPTED,
        rejection_code_count=0, rejected_attempt_history_count=len(HISTORY),
        mu_new_sha256=MU_NEW_SHA, sigma_new_sha256=SIGMA_NEW_SHA,
        implementation_record_content_sha256=RECORD)
    kwargs.update(overrides)
    return L.build_instance_index(**kwargs)


def attempt_record_ok(**overrides) -> dict[str, object]:
    """An ATTEMPT.json the real validator accepts, with the fixed history."""
    kwargs = dict(slot=SLOT, attempt=ACCEPTED_ATTEMPT, sector_partition_sha256=PARTITION,
                  feasible_count=38760, rejected_attempt_history=HISTORY)
    kwargs.update(overrides)
    return L.build_attempt_record(**kwargs)


def write_one(root: Path, slot: int = SLOT) -> dict[str, object]:
    # The identity is derived from the slot and passed to BOTH the generation
    # record and the prepared record, because the layout now requires them to
    # agree (the prepared record's own instance.instance_id must equal the
    # instance_id being written).  The two used to be built independently, which
    # is exactly the disagreement the cross-binding exists to refuse.
    identity = f"{L.slot_name(slot)}-SYNTHETIC-NOT-A-REAL-DRAW"
    return L.write_instance(
        slot=slot, attempt=ACCEPTED_ATTEMPT, instance_id=identity,
        sector_partition_sha256=fake(f"partition-{slot}"),
        feasible_count=38760, return_matrix=MATRIX,
        prepared_record=prepared(instance_id=identity),
        implementation_record_content_sha256=RECORD,
        # The fixed vectors are copied into plain lists at the boundary, exactly
        # as a real caller would hand over ``ReturnDraw.mu_hex`` / ``.sigma_hex``
        # lists.  The module requires lists, not tuples, and a fixture that
        # passed tuples would be testing a boundary no caller crosses.
        mu_new=list(MU_NEW), sigma_new=[list(row) for row in SIGMA_NEW],
        rejected_attempt_history=[dict(entry) for entry in HISTORY], root=root)


# ---------------------------------------------------------------------------
# Slots and names
# ---------------------------------------------------------------------------
def test_slots() -> None:
    check(L.SLOT_NAMES == ("stage2_01", "stage2_02", "stage2_03", "stage2_04", "stage2_05"),
          "the five canonical slot names drifted from the protocol")
    for number in range(1, 6):
        check(L.slot_name(number) == f"stage2_{number:02d}", "slot_name round trip")
        check(L.slot_number(L.slot_name(number)) == number, "slot_number round trip")
    for bad in (0, 6, -1, True, 1.0, "1", None):
        refuses(lambda bad=bad: L.slot_name(bad), "slot must be", f"slot_name({bad!r})")
    for bad in ("stage2_00", "stage2_06", "stage2_1", "STAGE2_01", "stage2_01/", "../stage2_01",
                "", "stage2_0a", None, 1):
        refuses(lambda bad=bad: L.slot_number(bad), "slot name", f"slot_number({bad!r})")
    check(L.slot_dir(1).as_posix().endswith("research/g9/stage2_instances/stage2_01"),
          "slot_dir is not the protocol's canonical location")
    # The layout is bound to the writer it promotes through.
    check(L.MANIFEST_NAME == L._writer.MANIFEST_NAME and L.STAGING_PREFIX == L._writer.STAGING_PREFIX,
          "the layout does not reuse WP5's manifest name and staging prefix")
    check(L.WRITER_SCHEMA == L._writer.SCHEMA, "writer schema drift")
    check(L.WRITER_MANIFEST_KEYS == frozenset(L._writer.MANIFEST_KEYS), "writer key set drift")
    check(L.WRITER_ENTRY_KEYS == frozenset(L._writer.ENTRY_KEYS), "writer entry key set drift")
    check(L.SLOT_MEMBERS == (L.GENERATION_DIR_NAME, L.META_DIR_NAME, L.PREPARED_DIR_NAME),
          "slot member set drift")
    check(L.RETURN_MATRIX_BYTES == 249 * 20 * 8, "return matrix length drift")
    # Each fixed member name validates through its own member validator.
    for name in L.GENERATION_MEMBERS:
        check(L.generation_member(name) == name, f"canonical member {name} was refused")
    for name in L.PREPARED_MEMBERS:
        check(L.prepared_member(name) == name, f"canonical member {name} was refused")
    check("PREPARED.json" not in L.GENERATION_MEMBERS,
          "the prepared record leaked into the generation member set")
    check(L.ATTEMPT_NAME not in L.PREPARED_MEMBERS,
          "the attempt ledger leaked into the prepared member set")
    refuses(lambda: L.generation_member("EXTRA.json"), "unknown generation member", "extra member")
    refuses(lambda: L.generation_member("../escape.json"), "plain component", "traversal member")
    refuses(lambda: L.generation_member("sub/dir.json"), "plain component", "nested member")
    refuses(lambda: L.prepared_member("NOPE.json"), "unknown prepared member", "unknown prepared")
    refuses(lambda: L.generation_member(7), "must be a str", "non-string member")
    refuses(lambda: L.generation_member(""), "non-empty string", "empty member")
    refuses(lambda: L.meta_member("NOPE.json"), "unknown meta member", "unknown meta member")
    refuses(lambda: L.meta_member("../escape.json"), "plain component", "meta traversal member")
    for name in L.META_MEMBERS:
        check(L.meta_member(name) == name, f"canonical meta member {name} was refused")


# ---------------------------------------------------------------------------
# ATTEMPT.json
# ---------------------------------------------------------------------------
def test_attempt_record() -> None:
    record = attempt_record_ok()
    body = L.validate_attempt_record(record)
    check(body["slot"] == SLOT and body["attempt"] == 2, "attempt record field drift")
    check(body["feasible_count"] == 38760, "feasible count drift")
    check(body["scope"] == L.SCOPE_STATEMENT, "attempt scope drift")
    check(body["disposition"] == L.DISPOSITION_ACCEPTED, "accepted disposition drift")
    check(body["rejection_codes"] == [], "an accepted attempt must carry no codes")
    check(len(body["rejected_attempt_history"]) == len(HISTORY),
          "the retained rejected-attempt history is not carried")
    check([e["attempt"] for e in body["rejected_attempt_history"]] == [0, 1],
          "the retained history is not in protocol attempt order")
    check(body["content_sha256"] == hashlib.sha256(canonical(
        {k: v for k, v in record.items() if k != "content_sha256"})).hexdigest(),
        "attempt content hash is not independently reproducible")
    check(set(record["seed_commitments"]) == {"returns", "sectors"},
          "the two U-08 streams are not both present")
    # The commitments are the generator's own derivation, not invented here.
    # Checked against attempt 2, the record's OWN attempt number: the accepted
    # attempt is 2 so that the retained history (0 and 1) is non-empty, and a
    # commitment re-derived for attempt 0 would be a different derivation.
    for purpose, entry in record["seed_commitments"].items():
        seed = L._generator.stream_seed(SLOT, 2, purpose)
        check(entry["material_sha256"] == seed.material_sha256
              and entry["seed_uint128"] == seed.seed_uint128
              and entry["material_ascii"] == seed.material_ascii,
              f"the {purpose} commitment is not the U-08 derivation")
    check(L.build_attempt_record(slot=SLOT, attempt=ACCEPTED_ATTEMPT,
                                 sector_partition_sha256=PARTITION,
                                 feasible_count=38760,
                                 rejected_attempt_history=HISTORY) == record,
          "attempt record is not deterministic")

    def resealed(edit) -> dict:
        body_ = json.loads(json.dumps(record))
        edit(body_)
        body_.pop("content_sha256", None)
        body_["content_sha256"] = L._content_sha256(body_)
        return body_

    for label, edit, needle in (
        ("extra key", lambda m: m.update(extra=1), "wrong key set"),
        ("missing key", lambda m: m.pop("feasible_count"), "wrong key set"),
        ("schema drift", lambda m: m.update(schema="other/v1"), "schema mismatch"),
        ("scope drift", lambda m: m.update(scope="present"), "scope statement"),
        ("slot 0", lambda m: m.update(slot=0), "slot must be in 1..5"),
        ("slot 6", lambda m: m.update(slot=6), "slot must be in 1..5"),
        ("slot bool", lambda m: m.update(slot=True), "slot must be an int"),
        ("attempt 128", lambda m: m.update(attempt=128), "attempt must be in 0..127"),
        ("attempt -1", lambda m: m.update(attempt=-1), "attempt must be in 0..127"),
        ("negative feasible count", lambda m: m.update(feasible_count=-1), "feasible_count must be non-negative"),
        ("bool feasible count", lambda m: m.update(feasible_count=True), "feasible_count must be an int"),
        ("bad partition hash", lambda m: m.update(sector_partition_sha256="zz"),
         "must be exactly 64 characters"),
        ("uppercase partition hash", lambda m: m.update(sector_partition_sha256="A" * 64),
         "must be a lowercase SHA-256"),
        ("dropped stream", lambda m: m["seed_commitments"].pop("sectors"),
         "exactly the two U-08 streams"),
        ("extra stream", lambda m: m["seed_commitments"].update(extra={}),
         "exactly the two U-08 streams"),
        ("commitment extra key", lambda m: m["seed_commitments"]["returns"].update(extra=1),
         "wrong key set"),
        ("forged material", lambda m: m["seed_commitments"]["returns"].update(
            material_ascii="decisions_os/stage2/v1|master=1|slot=01|attempt=9|purpose=returns"),
         "not the U-08 material"),
        ("wrong slot in material", lambda m: m["seed_commitments"].update(returns=dict(
            m["seed_commitments"]["returns"], material_ascii=L._u08_material(2, ATTEMPT, "returns"))),
         "not the U-08 material"),
        ("material hash not derived", lambda m: m["seed_commitments"]["returns"].update(
            material_sha256=fake("forged")),
         "not the U-08 derivation"),
        ("uint128 not derived", lambda m: m["seed_commitments"]["returns"].update(seed_uint128=7),
         "not the U-08 derivation"),
        ("uint128 out of range", lambda m: m["seed_commitments"]["returns"].update(
            seed_uint128=L.UINT128_LIMIT),
         "is not in [0, 2**128)"),
        ("uint128 bool", lambda m: m["seed_commitments"]["returns"].update(seed_uint128=True),
         "seed_uint128 must be an int"),
        # --- schema v2: the protocol's retained-rejection content ---
        ("superseded v1 schema", lambda m: m.update(schema=L.ATTEMPT_SCHEMA_V1),
         "superseded v1 attempt record"),
        ("unknown disposition", lambda m: m.update(disposition="maybe"),
         "not one of the declared dispositions"),
        ("empty disposition", lambda m: m.update(disposition=""), "non-empty string"),
        ("int disposition", lambda m: m.update(disposition=1), "must be a str"),
        ("accepted with a code", lambda m: m.update(rejection_codes=["feasible_set_below_100"]),
         "an accepted attempt must carry no rejection codes"),
        ("codes not a list", lambda m: m.update(rejection_codes="feasible_set_below_100"),
         "rejection_codes must be a list"),
        ("codes a tuple", lambda m: m.update(rejection_codes=("feasible_set_below_100",)),
         "rejection_codes must be a list"),
        ("unfixed code", lambda m: m.update(rejection_codes=["energy_too_low"]),
         "outside the fixed rejection set"),
        ("repeated code", lambda m: m.update(rejection_codes=["feasible_set_below_100"] * 2),
         "repeats a rejection code"),
        ("non-string code", lambda m: m.update(rejection_codes=[7]),
         "must hold only strings"),
        ("history not a list", lambda m: m.update(rejected_attempt_history={}),
         "rejected_attempt_history must be a list"),
        ("history entry not an object", lambda m: m.update(rejected_attempt_history=[7]),
         "history entry must be an object"),
        ("history entry key set", lambda m: m.update(
            rejected_attempt_history=[dict(HISTORY[0], extra=1)]), "wrong key set"),
        ("history not ascending", lambda m: m.update(
            rejected_attempt_history=[HISTORY[1], HISTORY[0]]),
         "strictly increasing by attempt"),
        ("history at the accepted attempt", lambda m: m.update(
            rejected_attempt_history=[dict(HISTORY[0], attempt=2)]),
         "must precede the accepted attempt"),
        ("history above the accepted attempt", lambda m: m.update(
            rejected_attempt_history=[dict(HISTORY[0], attempt=9)]),
         "must precede the accepted attempt"),
        ("history negative attempt", lambda m: m.update(
            rejected_attempt_history=[dict(HISTORY[0], attempt=-1)]),
         "attempt must be in 0..127"),
        ("history rejected with no code", lambda m: m.update(
            rejected_attempt_history=[dict(HISTORY[0], rejection_codes=[])]),
         "must carry at least one fixed rejection code"),
        ("history unfixed code", lambda m: m.update(
            rejected_attempt_history=[dict(HISTORY[0], rejection_codes=["nope"])]),
         "outside the fixed rejection set"),
        ("history bad partition hash", lambda m: m.update(
            rejected_attempt_history=[dict(HISTORY[0], sector_partition_sha256="zz")]),
         "must be exactly 64 characters"),
        ("history negative feasible count", lambda m: m.update(
            rejected_attempt_history=[dict(HISTORY[0], feasible_count=-1)]),
         "feasible_count must be non-negative"),
        ("history bool feasible count", lambda m: m.update(
            rejected_attempt_history=[dict(HISTORY[0], feasible_count=True)]),
         "feasible_count must be an int"),
    ):
        refuses(lambda edit=edit: L.validate_attempt_record(resealed(edit)),
                needle, f"attempt record: {label}")
    # An edit without resealing must be refused by the content-hash check.
    stale = json.loads(json.dumps(record))
    stale["feasible_count"] = 999
    refuses(lambda: L.validate_attempt_record(stale), "content hash mismatch",
            "attempt record: stale content hash")
    for bad in ("string", None, [], 7):
        refuses(lambda bad=bad: L.validate_attempt_record(bad), "must be an object",
                f"attempt record as {bad!r}")
    # Builder refusals.
    refuses(lambda: L.build_attempt_record(slot=0, attempt=0, sector_partition_sha256=PARTITION,
                                           feasible_count=1), "slot must be in 1..5", "builder slot 0")
    refuses(lambda: L.build_attempt_record(slot=SLOT, attempt=128, sector_partition_sha256=PARTITION,
                                           feasible_count=1), "attempt must be in 0..127", "builder attempt")
    refuses(lambda: L.build_attempt_record(slot=SLOT, attempt=ATTEMPT, sector_partition_sha256="x",
                                           feasible_count=1), "must be exactly 64 characters", "builder hash")
    # The BUILDER refuses a malformed history too, before anything is written.
    refuses(lambda: attempt_record_ok(rejected_attempt_history=[dict(HISTORY[0], rejection_codes=[])]),
            "at least one fixed rejection code", "builder: rejected entry with no code")
    refuses(lambda: attempt_record_ok(rejected_attempt_history=[dict(HISTORY[0], attempt=5)]),
            "must precede the accepted attempt", "builder: history after the accepted attempt")
    refuses(lambda: attempt_record_ok(rejected_attempt_history=[dict(HISTORY[0], rejection_codes=["free"])]),
            "outside the fixed rejection set", "builder: unfixed code in history")


def test_rejected_attempt_record() -> None:
    """A RETAINED REJECTED attempt is representable, with its fixed codes.

    Schema v1 could not express this at all: a record described an attempt and
    said nothing about why it was not used.  These are the protocol's
    "every attempt -- accepted or rejected -- is retained ... with ... one or more
    fixed rejection codes" (``GATE_9_STAGE2_PROTOCOL_DRAFT.md:58-60``).
    """
    record = L.build_rejected_attempt_record(
        slot=SLOT, attempt=0, sector_partition_sha256=fake("rejected-partition-0"),
        feasible_count=42, rejection_codes=["feasible_set_below_100", "partition_matches_stage1"])
    body = L.validate_attempt_record(record)
    check(body["disposition"] == L.DISPOSITION_REJECTED, "rejected disposition drift")
    check(body["rejection_codes"] == ["feasible_set_below_100", "partition_matches_stage1"],
          "a rejected attempt's fixed codes are not carried")
    check(body["rejected_attempt_history"] == [],
          "a rejected attempt must not carry a history")
    # Its seed commitments are the SAME U-08 derivation for its own attempt
    # number, re-derived rather than trusted -- a rejected attempt drew from the
    # same two streams as any other.
    for purpose, entry in body["seed_commitments"].items():
        seed = L._generator.stream_seed(SLOT, 0, purpose)
        check(entry["seed_uint128"] == seed.seed_uint128
              and entry["material_sha256"] == seed.material_sha256,
              f"the rejected {purpose} commitment is not the U-08 derivation")
    # A rejected attempt with NO codes is refused: the protocol requires at least
    # one, and this is the specific mutant that would let a rejected attempt be
    # recorded without a reason.
    refuses(lambda: L.build_rejected_attempt_record(
        slot=SLOT, attempt=1, sector_partition_sha256=PARTITION,
        feasible_count=1, rejection_codes=[]), "at least one fixed rejection code",
        "a rejected attempt with no codes")
    refuses(lambda: L.build_rejected_attempt_record(
        slot=SLOT, attempt=1, sector_partition_sha256=PARTITION,
        feasible_count=1, rejection_codes=["not_a_fixed_code"]), "outside the fixed rejection set",
        "a rejected attempt with an unfixed code")
    refuses(lambda: L.build_rejected_attempt_record(
        slot=SLOT, attempt=1, sector_partition_sha256=PARTITION,
        feasible_count=1, rejection_codes="feasible_set_below_100"),
        "rejection_codes must be a list",
        "a rejected attempt whose codes are a bare string")
    # A tuple of codes is refused for the same reason, and refused as a CONTAINER
    # rather than silently coerced: the builder hands the argument to the
    # validator unchanged, so a tuple cannot slip through as a list.
    refuses(lambda: L.build_rejected_attempt_record(
        slot=SLOT, attempt=1, sector_partition_sha256=PARTITION, feasible_count=1,
        rejection_codes=("feasible_set_below_100",)),
        "rejection_codes must be a list",
        "a rejected attempt whose codes are a tuple")
    # The SCALAR guards belong to this builder too, and each is a separate refusal
    # on its own entry point: dropping one of them lets a malformed retained
    # rejection through the builder even though the validator would still catch it
    # later.  These were three surviving sweep sites until they were exercised.
    for label, overrides, needle in (
            ("slot 0", {"slot": 0}, "slot must be in 1..5"),
            ("slot 6", {"slot": 6}, "slot must be in 1..5"),
            ("slot bool", {"slot": True}, "slot must be an int"),
            ("attempt 128", {"attempt": 128}, "attempt must be in 0..127"),
            ("attempt bool", {"attempt": True}, "attempt must be an int"),
            ("bad partition hash", {"sector_partition_sha256": "zz"},
             "must be exactly 64 characters"),
            ("uppercase partition hash", {"sector_partition_sha256": "A" * 64},
             "must be a lowercase SHA-256"),
            ("negative count", {"feasible_count": -1}, "feasible_count must be non-negative"),
            ("bool count", {"feasible_count": True}, "feasible_count must be an int"),
    ):
        kwargs = dict(slot=SLOT, attempt=1, sector_partition_sha256=PARTITION,
                      feasible_count=1, rejection_codes=["feasible_set_below_100"])
        kwargs.update(overrides)
        refuses(lambda kw=kwargs: L.build_rejected_attempt_record(**kw), needle,
                f"build_rejected_attempt_record: {label}")
    check(L.build_rejected_attempt_record(
        slot=SLOT, attempt=1, sector_partition_sha256=PARTITION, feasible_count=0,
        rejection_codes=list(L.REJECTION_CODE_SET))["feasible_count"] == 0,
        "build_rejected_attempt_record refused a valid request")
    # Every code in the fixed set is accepted, and the whole set at once is the
    # longest legal list: which is why there is no separate length cap.
    check(len(L.REJECTION_CODE_SET) == 3,
          f"the fixed rejection set has {len(L.REJECTION_CODE_SET)} codes, not the "
          f"documented 3")
    # And a rejected record may not smuggle a history, which would let it pose as
    # the accepted attempt of a slot.  The disposition rule is checked BEFORE the
    # history is validated, so ANY non-empty history on a rejected record is
    # refused by that rule and the ordering guard is asserted separately below,
    # where it is the only thing that can fire.
    smuggle = dict(record, rejected_attempt_history=[dict(HISTORY[0], attempt=99)])
    smuggle.pop("content_sha256")
    smuggle["content_sha256"] = L._content_sha256(smuggle)
    refuses(lambda: L.validate_attempt_record(smuggle),
            "cannot itself carry a rejected-attempt history",
            "a rejected record carrying a history")


# ---------------------------------------------------------------------------
# GENERATION.json
# ---------------------------------------------------------------------------
def test_generation_record() -> None:
    record = generation_record_ok()
    body = L.validate_generation_record(record)
    check(body["instance_id"] == INSTANCE_ID, "instance id drift")
    check(body["return_matrix_sha256"] == MATRIX_SHA, "return matrix hash drift")
    check(body["n_rows"] == 249 and body["n_assets"] == 20, "matrix shape drift")
    # The recorded moments are the protocol's canonical binary64 encodings of
    # mu_new and Sigma_new (GATE_9_STAGE2_PROTOCOL_DRAFT.md:101-104), in the
    # generator's own spelling (stage2_generator.py:337-338).
    moments = body["moment_summary"]
    check(moments["mu_new"]["values"] == list(MU_NEW), "mu_new values drift")
    check(moments["mu_new"]["encoding"] == L.MU_NEW_ENCODING, "mu_new encoding drift")
    check(moments["mu_new"]["shape"] == [L.MU_NEW_DIM], "mu_new shape drift")
    check(moments["sigma_new"]["shape"] == [L.SIGMA_NEW_ROWS, L.SIGMA_NEW_COLS],
          "Sigma_new shape drift")
    check(moments["sigma_new"]["values"] == [v for row in SIGMA_NEW for v in row],
          "Sigma_new values drift")
    # The digests are independently reproducible from the ENCODED TEXT, proving
    # they commit to the bytes a reviewer can read.
    check(moments["mu_new"]["sha256"] == MU_NEW_SHA,
          "mu_new digest is not the SHA-256 of its canonical encoding")
    check(moments["sigma_new"]["sha256"] == SIGMA_NEW_SHA,
          "Sigma_new digest is not the SHA-256 of its canonical encoding")
    # The moment encoding is deliberately NOT the return matrix's byte-order
    # encoding; conflating the two would be silent drift.
    check(L.MU_NEW_ENCODING != L.RETURN_MATRIX_ENCODING,
          "the moment encoding must be distinct from the matrix byte order")

    def resealed(edit) -> dict:
        body_ = json.loads(json.dumps(record))
        edit(body_)
        body_.pop("content_sha256", None)
        body_["content_sha256"] = L._content_sha256(body_)
        return body_

    for label, edit, needle in (
        ("extra key", lambda m: m.update(extra=1), "wrong key set"),
        ("missing key", lambda m: m.pop("n_rows"), "wrong key set"),
        ("schema drift", lambda m: m.update(schema="other/v1"), "schema mismatch"),
        ("scope drift", lambda m: m.update(scope="present"), "scope statement"),
        ("empty instance id", lambda m: m.update(instance_id=""), "non-empty string"),
        ("int instance id", lambda m: m.update(instance_id=7), "must be a str"),
        ("bad matrix hash", lambda m: m.update(return_matrix_sha256="nope"),
         "must be exactly 64 characters"),
        ("bad record hash", lambda m: m.update(implementation_record="nope"),
         "must be exactly 64 characters"),
        ("n_assets drift", lambda m: m.update(n_assets=19), f"must be the fixed {L.ASSET_COUNT}"),
        ("n_rows drift", lambda m: m.update(n_rows=248), f"must be the fixed {L.RETURN_ROWS}"),
        ("slot 6", lambda m: m.update(slot=6), "slot must be in 1..5"),
        ("attempt 128", lambda m: m.update(attempt=128), "attempt must be in 0..127"),
        # --- schema v2: the protocol's canonical mu_new / Sigma_new ---
        ("superseded v1 schema", lambda m: m.update(schema=L.GENERATION_SCHEMA_V1),
         "superseded v1 generation record"),
        ("moment_summary not an object", lambda m: m.update(moment_summary=[]),
         "moment_summary must be an object"),
        ("moment_summary missing a block", lambda m: m["moment_summary"].pop("sigma_new"),
         "must hold exactly mu_new and Sigma_new"),
        ("moment_summary extra block", lambda m: m["moment_summary"].update(extra={}),
         "must hold exactly mu_new and Sigma_new"),
        ("mu block key set", lambda m: m["moment_summary"]["mu_new"].update(extra=1),
         "wrong key set"),
        ("mu encoding drift", lambda m: m["moment_summary"]["mu_new"].update(encoding="binary64_le"),
         "encoding must be the canonical"),
        ("mu shape drift", lambda m: m["moment_summary"]["mu_new"].update(shape=[19]),
         "shape must be the protocol shape"),
        # A shape of the right LENGTH but wrong contents, which only the
        # element-wise comparison can see -- the length test alone passes it.
        ("mu shape wrong contents", lambda m: m["moment_summary"]["mu_new"].update(
            shape=[L.MU_NEW_DIM + 1]), "shape must be the protocol shape"),
        ("sigma shape wrong length", lambda m: m["moment_summary"]["sigma_new"].update(
            shape=[L.SIGMA_NEW_ROWS]), "shape must be the protocol shape"),
        ("sigma shape three deep", lambda m: m["moment_summary"]["sigma_new"].update(
            shape=[L.SIGMA_NEW_ROWS, L.SIGMA_NEW_COLS, 1]),
         "shape must be the protocol shape"),
        ("mu shape str elements", lambda m: m["moment_summary"]["mu_new"].update(
            shape=["20"]), "shape must hold only integers"),
        ("mu shape float elements", lambda m: m["moment_summary"]["mu_new"].update(
            shape=[20.0]), "shape must hold only integers"),
        ("sigma shape bool elements", lambda m: m["moment_summary"]["sigma_new"].update(
            shape=[True, 20]), "shape must hold only integers"),
        ("mu shape not a list", lambda m: m["moment_summary"]["mu_new"].update(shape=L.MU_NEW_DIM),
         "shape must be a list"),
        ("mu wrong length", lambda m: m["moment_summary"]["mu_new"].update(
            values=MU_NEW[:-1]), "must hold exactly 20 encoded values"),
        ("mu non-string value", lambda m: m["moment_summary"]["mu_new"].update(
            values=[1] + MU_NEW[1:]), "must hold only strings"),
        ("mu empty value", lambda m: m["moment_summary"]["mu_new"].update(
            values=[""] + MU_NEW[1:]), "must hold non-empty strings"),
        ("mu decimal not hex", lambda m: m["moment_summary"]["mu_new"].update(
            values=["1.5"] + MU_NEW[1:]), "not canonical binary64 hex"),
        ("mu missing exponent", lambda m: m["moment_summary"]["mu_new"].update(
            values=["0x1.0000000000000"] + MU_NEW[1:]), "not canonical binary64 hex"),
        ("mu uppercase hex", lambda m: m["moment_summary"]["mu_new"].update(
            values=["0X1.0000000000000P+0"] + MU_NEW[1:]), "not canonical binary64 hex"),
        ("mu nan spelling", lambda m: m["moment_summary"]["mu_new"].update(
            values=["nan"] + MU_NEW[1:]), "not canonical binary64 hex"),
        # A tampered value with its block digest left alone is the tamper this
        # two-commitment design exists to catch, and the re-sealed content hash
        # below proves the refusal is not credited to a stale record digest.
        ("mu value tampered", lambda m: m["moment_summary"]["mu_new"].update(
            values=["0x1.fffffffffffffp+0"] + MU_NEW[1:]),
         "sha256 does not match its own canonical encoding"),
        ("mu digest tampered", lambda m: m["moment_summary"]["mu_new"].update(
            sha256=fake("forged-mu")), "sha256 does not match its own canonical encoding"),
        ("sigma wrong length", lambda m: m["moment_summary"]["sigma_new"].update(
            values=list(m["moment_summary"]["sigma_new"]["values"])[:-1]),
         "must hold exactly 400 encoded values"),
        ("sigma shape drift", lambda m: m["moment_summary"]["sigma_new"].update(shape=[20, 19]),
         "shape must be the protocol shape"),
        ("sigma encoding drift", lambda m: m["moment_summary"]["sigma_new"].update(
            encoding="binary64_le"), "encoding must be the canonical"),
        ("sigma value tampered", lambda m: m["moment_summary"]["sigma_new"].update(
            values=["0x1.fffffffffffffp+0"] + list(m["moment_summary"]["sigma_new"]["values"])[1:]),
         "sha256 does not match its own canonical encoding"),
        ("sigma digest tampered", lambda m: m["moment_summary"]["sigma_new"].update(
            sha256=fake("forged-sigma")), "sha256 does not match its own canonical encoding"),
    ):
        refuses(lambda edit=edit: L.validate_generation_record(resealed(edit)),
                needle, f"generation record: {label}")
    stale = json.loads(json.dumps(record))
    stale["instance_id"] = "other"
    refuses(lambda: L.validate_generation_record(stale), "content hash mismatch",
            "generation record: stale content hash")
    for bad in ("string", None, []):
        refuses(lambda bad=bad: L.validate_generation_record(bad), "must be an object",
                f"generation record as {bad!r}")
    # The BUILDER refuses the same malformed moments, before any bytes exist.
    refuses(lambda: generation_record_ok(mu_new=MU_NEW[:-1]),
            "must hold exactly 20 encoded values", "builder: short mu_new")
    refuses(lambda: generation_record_ok(mu_new=list(MU_NEW) + ["1.5"]),
            "must hold exactly 20 encoded values", "builder: long mu_new")
    refuses(lambda: generation_record_ok(mu_new=["nan"] + MU_NEW[1:]),
            "not canonical binary64 hex", "builder: non-canonical mu_new")
    refuses(lambda: generation_record_ok(mu_new="0x1.0p+0"),
            "mu_new must be a list or tuple of encoded values", "builder: mu_new as a string")
    refuses(lambda: generation_record_ok(mu_new={"a": 1}),
            "mu_new must be a list or tuple of encoded values", "builder: mu_new as a dict")
    # A tuple IS accepted, and yields the identical commitment: the generator's
    # own ``ReturnDraw.mu_hex`` is a tuple, so refusing one would refuse the real
    # caller's object.
    check(generation_record_ok(mu_new=tuple(MU_NEW))["moment_summary"]["mu_new"]["sha256"]
          == MU_NEW_SHA, "a tuple mu_new did not produce the same commitment as a list")
    refuses(lambda: generation_record_ok(sigma_new=[row[:-1] for row in SIGMA_NEW]),
            "must hold exactly 20 encoded values", "builder: short Sigma_new row")
    refuses(lambda: generation_record_ok(sigma_new=SIGMA_NEW[:-1]),
            "Sigma_new must hold exactly 20 rows", "builder: short Sigma_new")
    refuses(lambda: generation_record_ok(sigma_new=["0x1.0p+0"] * L.SIGMA_NEW_ROWS),
            "Sigma_new row 0 must be a list or tuple of encoded values",
            "builder: Sigma_new row is a bare string")
    refuses(lambda: generation_record_ok(sigma_new="0x1.0p+0"),
            "Sigma_new must be a list or tuple of rows", "builder: Sigma_new as a string")
    # A tuple of tuples IS accepted, identically: ``ReturnDraw.sigma_hex`` is one.
    check(generation_record_ok(sigma_new=tuple(tuple(r) for r in SIGMA_NEW))
          ["moment_summary"]["sigma_new"]["sha256"] == SIGMA_NEW_SHA,
          "a tuple Sigma_new did not produce the same commitment as a list")


# ---------------------------------------------------------------------------
# INSTANCE.json
# ---------------------------------------------------------------------------
def test_instance_index() -> None:
    record = index_ok()
    body = L.validate_instance_index(record)
    check(body["slot_name"] == "stage2_01", "index slot name drift")
    check(body["status"] == L.PREPARED_STATUS, "index status drift")
    check(body["attempt_ledger"]["path"] == "generation/ATTEMPT.json",
          "the index does not name the ledger by its canonical path")
    check(body["attempt_ledger"]["disposition"] == L.DISPOSITION_ACCEPTED,
          "index ledger disposition drift")
    check(body["moments"]["mu_new_sha256"] == MU_NEW_SHA,
          "the index does not bind the mu_new digest")
    check(body["prepared_record"]["path"] == "instance/PREPARED.json", "prepared path drift")
    check(body["generation"]["path"] == "generation", "generation path drift")

    def resealed(edit) -> dict:
        body_ = json.loads(json.dumps(record))
        edit(body_)
        body_.pop("content_sha256", None)
        body_["content_sha256"] = L._content_sha256(body_)
        return body_

    # Each builder emits EXACTLY its declared key set.  During the schema v2/v3
    # work a key was rendered but omitted from the declared set, so every record
    # that builder produced was refused by its own validator as a "wrong key set"
    # -- a self-inconsistency the refusal tables below could each have masked by
    # matching some earlier needle.  Asserting the sets agree makes that class of
    # bug a named failure instead of a pile of wrong reasons.
    check(set(record) == L.INSTANCE_KEYS,
          f"the index builder and INSTANCE_KEYS disagree: "
          f"{sorted(set(record) ^ L.INSTANCE_KEYS)}")
    check(set(attempt_record_ok()) == L.ATTEMPT_KEYS,
          f"the attempt builder and ATTEMPT_KEYS disagree: "
          f"{sorted(set(attempt_record_ok()) ^ L.ATTEMPT_KEYS)}")
    check(set(generation_record_ok()) == L.GENERATION_KEYS,
          f"the generation builder and GENERATION_KEYS disagree: "
          f"{sorted(set(generation_record_ok()) ^ L.GENERATION_KEYS)}")

    def both(field: str, top: int, nested: int):
        """Set a top-level field and the same-named ledger field together."""
        def edit(m):
            m[field] = top
            m["attempt_ledger"][field] = nested
        return edit

    for label, edit, needle in (
        ("extra key", lambda m: m.update(extra=1), "wrong key set"),
        ("missing key", lambda m: m.pop("status"), "wrong key set"),
        ("schema drift", lambda m: m.update(schema="other/v1"), "schema mismatch"),
        ("scope drift", lambda m: m.update(scope="present"), "scope statement"),
        ("slot name mismatch", lambda m: m.update(slot_name="stage2_02"),
         "canonical name of its slot"),
        ("unknown status", lambda m: m.update(status="prepared_real"), "not an accepted"),
        ("empty status", lambda m: m.update(status=""), "non-empty string"),
        ("non-synthetic claim", lambda m: m["prepared_record"].update(
            non_synthetic_supported=True), "claims non-synthetic support"),
        ("non-synthetic not bool", lambda m: m["prepared_record"].update(
            non_synthetic_supported=1), "claims non-synthetic support"),
        ("prepared key set", lambda m: m["prepared_record"].update(extra=1), "wrong key set"),
        ("prepared path drift", lambda m: m["prepared_record"].update(path="PREPARED.json"),
         "prepared_record path mismatch"),
        ("generation key set", lambda m: m["generation"].update(extra=1), "wrong key set"),
        ("generation path drift", lambda m: m["generation"].update(path="gen"),
         "generation path mismatch"),
        ("bad prepared hash", lambda m: m["prepared_record"].update(sha256="zz"),
         "must be exactly 64 characters"),
        ("bad manifest hash", lambda m: m["generation"].update(manifest_sha256="zz"),
         "must be exactly 64 characters"),
        ("bad manifest content hash", lambda m: m["generation"].update(
            manifest_content_sha256="zz"), "must be exactly 64 characters"),
        ("bad record hash", lambda m: m.update(implementation_record="zz"),
         "must be exactly 64 characters"),
        ("slot 0", lambda m: m.update(slot=0), "slot must be in 1..5"),
        ("attempt 128", lambda m: m.update(attempt=128), "attempt must be in 0..127"),
        ("empty instance id", lambda m: m.update(instance_id=""), "non-empty string"),
        # --- schema v3: the ledger and moment bindings ---
        ("superseded v2 schema", lambda m: m.update(schema=L.INSTANCE_SCHEMA_V2),
         "superseded v2 instance index"),
        ("ledger missing", lambda m: m.pop("attempt_ledger"), "wrong key set"),
        ("ledger not an object", lambda m: m.update(attempt_ledger=[]), "must be an object"),
        ("ledger key set", lambda m: m["attempt_ledger"].update(extra=1), "wrong key set"),
        ("ledger path drift", lambda m: m["attempt_ledger"].update(path="ATTEMPT.json"),
         "attempt_ledger path mismatch"),
        ("ledger bad bytes hash", lambda m: m["attempt_ledger"].update(sha256="zz"),
         "must be exactly 64 characters"),
        ("ledger bad content hash", lambda m: m["attempt_ledger"].update(content_sha256="ZZ"),
         "attempt record content sha256 must be exactly 64 characters"),
        ("ledger attempt disagrees", lambda m: m["attempt_ledger"].update(attempt=7),
         "attempt_ledger attempt disagrees with the index attempt"),
        ("ledger attempt 128", lambda m: m["attempt_ledger"].update(attempt=128),
         "attempt must be in 0..127"),
        # And the pair moved TOGETHER.  With both fields out of range, both range
        # guards fire first, so the two cases below isolate each range guard from
        # the other.  Note there is deliberately NO "both equal and in range"
        # case: ``attempt=4`` in both fields is a perfectly legal index, so an
        # equality that fires there would be a false refusal, not a check.
        ("both attempts 128", both("attempt", 128, 128), "attempt must be in 0..127"),
        ("both attempts bool", both("attempt", True, True), "attempt must be an int"),
        ("ledger disposition rejected", lambda m: m["attempt_ledger"].update(
            disposition=L.DISPOSITION_REJECTED), "must claim the accepted disposition"),
        ("ledger unknown disposition", lambda m: m["attempt_ledger"].update(disposition="maybe"),
         "not one of the declared dispositions"),
        ("ledger code count negative", lambda m: m["attempt_ledger"].update(rejection_code_count=-1),
         "rejection code count must be non-negative"),
        ("ledger code count bool", lambda m: m["attempt_ledger"].update(rejection_code_count=True),
         "rejection code count must be an int"),
        ("history count negative", lambda m: m["attempt_ledger"].update(
            rejected_attempt_history_count=-1),
         "rejected attempt history count must be non-negative"),
        # Ordering asserted from the index alone: more retained rejections than
        # precede the accepted attempt is impossible, so it must be refused here
        # rather than only on the read side.
        ("history count above attempt",
         lambda m: (m.__setitem__("attempt", 1),
                    m["attempt_ledger"].__setitem__("attempt", 1),
                    m["attempt_ledger"].__setitem__("rejected_attempt_history_count", 5)),
         "more rejected attempts are retained than precede the accepted attempt"),
        ("moments missing", lambda m: m.pop("moments"), "wrong key set"),
        ("moments not an object", lambda m: m.update(moments=7), "must be an object"),
        ("moments key set", lambda m: m["moments"].update(extra=1), "wrong key set"),
        ("mu digest bad", lambda m: m["moments"].update(mu_new_sha256="zz"),
         "must be exactly 64 characters"),
        ("sigma digest bad", lambda m: m["moments"].update(sigma_new_sha256="nope"),
         "must be exactly 64 characters"),
    ):
        refuses(lambda edit=edit: L.validate_instance_index(resealed(edit)),
                needle, f"instance index: {label}")
    # The control for the attempt cases above: an index whose two attempt fields are
    # both moved to a LEGAL, EQUAL value must be ACCEPTED.  Without it, a guard that
    # refused every attempt disagreement -- including a correct one -- would still
    # pass every refusal case in the table.
    accepted_pair = json.loads(json.dumps(record))
    accepted_pair["attempt"] = 4
    accepted_pair["attempt_ledger"]["attempt"] = 4
    accepted_pair.pop("content_sha256")
    accepted_pair["content_sha256"] = L._content_sha256(accepted_pair)
    check(L.validate_instance_index(accepted_pair)["attempt"] == 4,
          "a legal equal attempt pair was refused: the attempt guards are too strict")
    stale = json.loads(json.dumps(record))
    stale["moments"]["mu_new_sha256"] = fake("changed-without-resealing")
    refuses(lambda: L.validate_instance_index(stale), "content hash mismatch",
            "instance index: stale content hash")
    # A non-synthetic claim must be refused by the builder too.
    refuses(lambda: index_ok(non_synthetic_supported=True),
            "claims non-synthetic support", "index builder: non-synthetic claim")
    refuses(lambda: index_ok(prepared_record_status="prepared_real"),
        "not an accepted", "index builder: unknown status")
    # Builder refusals for the two new blocks.
    refuses(lambda: index_ok(attempt_disposition="maybe"),
            "not one of the declared dispositions", "index builder: unknown disposition")
    refuses(lambda: index_ok(attempt_disposition=L.DISPOSITION_REJECTED),
            "must claim the accepted disposition",
            "index builder: an index naming a rejected ledger")
    refuses(lambda: index_ok(rejection_code_count=-1),
            "rejection code count must be non-negative", "index builder: negative code count")
    refuses(lambda: index_ok(rejected_attempt_history_count=-3),
            "rejected attempt history count must be non-negative",
            "index builder: negative history count")
    refuses(lambda: index_ok(mu_new_sha256="zz"),
            "must be exactly 64 characters", "index builder: bad mu digest")
    refuses(lambda: index_ok(attempt_record_sha256="nothex"),
            "must be exactly 64 characters", "index builder: bad ledger hash")


# ---------------------------------------------------------------------------
# Write, verify, and the on-disk refusals
# ---------------------------------------------------------------------------
def test_write_and_verify() -> None:
    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-write-") as tmp:
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
        receipt = write_one(root)
        base = root / "research/g9/stage2_instances/stage2_01"
        check(receipt["verdict"] == "written", "write receipt verdict drift")
        check(receipt["return_matrix_sha256"] == MATRIX_SHA, "receipt matrix hash drift")
        present = sorted(os.listdir(base))
        check(present == sorted(L.SLOT_MEMBERS), f"promoted slot drift: {present}")
        check(sorted(os.listdir(base / "generation")) == sorted(L.GENERATION_MEMBERS),
              "promoted generation members drift")
        check(sorted(os.listdir(base / "instance")) == sorted(L.PREPARED_MEMBERS),
              "promoted prepared members drift")
        leftovers = sorted(p.name for p in (root / "research/g9/stage2_instances").iterdir()
                           if p.name.startswith(L.STAGING_PREFIX))
        check(leftovers == [], f"staging survived: {leftovers}")
        check((base / "generation" / L.RETURN_MATRIX_NAME).read_bytes() == MATRIX,
              "promoted matrix drift")
        on_disk_index = json.loads((base / L.META_DIR_NAME / L.INDEX_NAME).read_text("ascii"))
        check(canonical(on_disk_index) == canonical(receipt["index"]),
              "the promoted index is not the receipt's index")

        summary = L.verify_instance(SLOT, root=root)
        check(summary["verdict"] == "verified", "verify verdict drift")
        check(summary["slot_name"] == "stage2_01" and summary["attempt"] == ACCEPTED_ATTEMPT,
              "verify slot/attempt drift")
        check(summary["rejected_attempt_history_count"] == len(HISTORY),
              "verify did not report the retained rejected-attempt history")
        check(summary["mu_new_sha256"] == MU_NEW_SHA
              and summary["sigma_new_sha256"] == SIGMA_NEW_SHA,
              "verify did not report the recorded moment digests")
        check(summary["instance_id"] == receipt["instance_id"], "verify instance id drift")
        check(summary["generation_manifest_sha256"] == receipt["generation_manifest_sha256"],
              "verify manifest hash drift")
        check(summary["generation_manifest_content_sha256"]
              == receipt["generation_manifest_content_sha256"], "verify manifest content drift")
        check(summary["prepared_record_sha256"] == receipt["prepared_record_sha256"],
              "verify prepared hash drift")
        check(summary["return_matrix_sha256"] == MATRIX_SHA, "verify matrix hash drift")
        check(summary["implementation_record_content_sha256"] == RECORD,
              "verify record hash drift")
        # Verification by slot name is the same check.
        check(L.verify_instance("stage2_01", root=root)["verdict"] == "verified",
              "verify by canonical slot name failed")
        # All five slots verify together.
        for slot in (2, 3, 4, 5):
            write_one(root, slot)
        every = L.verify_all_slots(root=root)
        check(every["count"] == 5 and every["slots"] == list(L.SLOT_NAMES),
              f"five-slot verification drift: {every['slots']}")
        named = L.verify_all_slots(root=root, present=(1, 2, 3, 4, 5))
        check(named["count"] == 5, "named five-slot verification drift")

        # A second write into the same slot is refused, never merged.
        refuses(lambda: write_one(root), "already exists", "second write into the same slot")
        check(sorted(os.listdir(base)) == sorted(L.SLOT_MEMBERS),
              "the refused second write modified the slot")


def test_write_refusals() -> None:
    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-write-refuse-") as tmp:
        root = Path(tmp)
        instance_root = root / "research" / "g9" / "stage2_instances"
        instance_root.mkdir(parents=True)

        def attempt(**overrides) -> None:
            kwargs = dict(slot=SLOT, attempt=ACCEPTED_ATTEMPT, instance_id=INSTANCE_ID,
                          sector_partition_sha256=PARTITION, feasible_count=38760,
                          return_matrix=MATRIX, prepared_record=prepared(),
                          implementation_record_content_sha256=RECORD,
                          mu_new=MU_NEW, sigma_new=SIGMA_NEW,
                          rejected_attempt_history=HISTORY, root=root)
            kwargs.update(overrides)
            L.write_instance(**kwargs)

        refuses(lambda: attempt(slot=0), "slot must be in 1..5", "write slot 0")
        refuses(lambda: attempt(slot=6), "slot must be in 1..5", "write slot 6")
        refuses(lambda: attempt(attempt=128), "attempt must be in 0..127", "write attempt 128")
        refuses(lambda: attempt(return_matrix="not bytes"), "payload must be bytes", "write matrix str")
        refuses(lambda: attempt(return_matrix=MATRIX[:-1]), "must be exactly", "short matrix")
        refuses(lambda: attempt(return_matrix=MATRIX + b"\x00"), "must be exactly", "long matrix")
        refuses(lambda: attempt(implementation_record_content_sha256="zz"),
                "must be exactly 64 characters", "write record hash")
        # An empty instance_id is refused by the generation record's own guard,
        # which renders first only if the prepared record still names the same
        # identity.  The prepared record is built from a valid identity here, so
        # the disagreement guard fires first; both are typed refusals and the
        # assertion is about the empty string being refused at the write
        # boundary, so the needle is the cross-binding message.
        refuses(lambda: attempt(instance_id=""),
                "instance_id disagrees with the instance being written",
                "write empty instance id")
        refuses(lambda: attempt(prepared_record={}), "non-empty object", "write empty prepared")
        # The three refusals below now fire inside the REAL WP5b validator, which
        # is strictly earlier and strictly stronger than the two-field check this
        # fixture previously asserted.  The needle is the reviewed validator's own
        # wording, so the test documents that the boundary is WP5b's and not this
        # module's re-implementation of it.
        refuses(lambda: attempt(prepared_record=prepared(status="prepared_real")),
                "WP5b provenance validator", "write unknown prepared status")
        refuses(lambda: attempt(prepared_record=prepared(supported=True)),
                "WP5b provenance validator", "write non-synthetic claim")
        refuses(lambda: attempt(prepared_record=dict(prepared(), non_synthetic_supported=1)),
                "WP5b provenance validator", "write non-synthetic not bool")
        refuses(lambda: attempt(sector_partition_sha256="zz"), "must be exactly 64 characters",
                "write bad partition hash")
        refuses(lambda: attempt(feasible_count=-5), "feasible_count must be non-negative",
                "write negative count")
        # Nothing was written by any refusal above.
        check(sorted(os.listdir(instance_root)) == [],
              f"a refused write left files behind: {sorted(os.listdir(instance_root))}")
        # A missing instance root is refused rather than created.
        refuses(lambda: L.write_instance(
            slot=SLOT, attempt=ACCEPTED_ATTEMPT, instance_id=INSTANCE_ID, sector_partition_sha256=PARTITION,
            feasible_count=1, return_matrix=MATRIX, prepared_record=prepared(),
            implementation_record_content_sha256=RECORD,
            mu_new=list(MU_NEW), sigma_new=[list(r) for r in SIGMA_NEW],
            rejected_attempt_history=list(HISTORY), root=root / "absent"),
            "instance root is not a directory", "write with a missing root")
        check(not (root / "absent").exists(), "a refused write created the instance root")
        # A file where the instance root belongs is refused.
        blocked = root / "blocked"
        blocked.mkdir()
        (blocked / "research" / "g9").mkdir(parents=True)
        (blocked / "research/g9/stage2_instances").write_bytes(b"not a directory")
        refuses(lambda: L.write_instance(
            slot=SLOT, attempt=ACCEPTED_ATTEMPT, instance_id=INSTANCE_ID, sector_partition_sha256=PARTITION,
            feasible_count=1, return_matrix=MATRIX, prepared_record=prepared(),
            implementation_record_content_sha256=RECORD,
            mu_new=list(MU_NEW), sigma_new=[list(r) for r in SIGMA_NEW],
            rejected_attempt_history=list(HISTORY), root=blocked),
            "instance root is not a directory", "write with a file instance root")
        # An existing staging path is refused, not reused.  The staging name
        # embeds THIS process's pid, so it is computed rather than guessed.
        staging = instance_root / f"{L.STAGING_PREFIX}{os.getpid()}-stage2_02"
        staging.mkdir()
        try:
            refuses(lambda: L.write_instance(
                slot=2, attempt=ACCEPTED_ATTEMPT, instance_id=INSTANCE_ID, sector_partition_sha256=PARTITION,
                feasible_count=1, return_matrix=MATRIX, prepared_record=prepared(),
                implementation_record_content_sha256=RECORD,
                mu_new=list(MU_NEW), sigma_new=[list(r) for r in SIGMA_NEW],
                rejected_attempt_history=list(HISTORY), root=root),
                "staging path already exists", "write with an occupied staging path")
        finally:
            staging.rmdir()


def test_on_disk_deviations() -> None:
    """Every deviation below is produced by editing a written instance."""
    def fresh() -> tuple[Path, Path]:
        tmp = tempfile.mkdtemp(dir=SCRATCH, prefix="wp8d-deviate-")
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
        write_one(root)
        return root, root / "research/g9/stage2_instances/stage2_01"

    # 1. An extra file in the generation directory.
    root, base = fresh()
    (base / "generation" / "EXTRA.json").write_bytes(b"{}")
    refuses(lambda: L.verify_instance(SLOT, root=root), "contents differ from the canonical layout",
            "extra file in the generation")
    (base / "generation" / "EXTRA.json").unlink()
    check(L.verify_instance(SLOT, root=root)["verdict"] == "verified",
          "removing the extra file did not restore verification")

    # 2. A missing member in the generation directory.
    root, base = fresh()
    (base / "generation" / L.ATTEMPT_NAME).unlink()
    refuses(lambda: L.verify_instance(SLOT, root=root), "contents differ from the canonical layout",
            "missing attempt record")
    root, base = fresh()
    (base / "generation" / L.RETURN_MATRIX_NAME).unlink()
    refuses(lambda: L.verify_instance(SLOT, root=root), "contents differ from the canonical layout",
            "missing return matrix")

    # 3. A truncated return matrix.  WP5's own size check refuses it, and the
    #    refusal arrives through this module's single typed error.
    root, base = fresh()
    matrix = base / "generation" / L.RETURN_MATRIX_NAME
    matrix.write_bytes(MATRIX[:-8])
    refuses(lambda: L.verify_instance(SLOT, root=root), "manifest size mismatch",
            "truncated return matrix")

    # 4. A same-length but different return matrix.
    root, base = fresh()
    matrix = base / "generation" / L.RETURN_MATRIX_NAME
    matrix.write_bytes(bytes((b + 1) % 256 for b in MATRIX))
    refuses(lambda: L.verify_instance(SLOT, root=root), "file content hash mismatch",
            "tampered return matrix")

    # 5. A re-sealed manifest that hides a tampered member: WP5's own rehash now
    #    passes, so only the generation record's binding can refuse.
    root, base = fresh()
    matrix = base / "generation" / L.RETURN_MATRIX_NAME
    matrix.write_bytes(bytes((b + 1) % 256 for b in MATRIX))
    reseal_manifest(root, base, L.GENERATION_DIR_NAME, L.RETURN_MATRIX_NAME)
    refuses(lambda: L.verify_instance(SLOT, root=root),
            "return matrix content hash does not match the generation record",
            "resealed manifest hiding a tampered matrix")

    # 6. A record member edited and fully resealed: its OWN content hash then
    #    refuses, because resealing the manifest does not reseal the record.
    root, base = fresh()
    attempt_path = base / "generation" / L.ATTEMPT_NAME
    body = json.loads(attempt_path.read_text("ascii"))
    body["feasible_count"] = 1
    attempt_path.write_bytes(canonical(body))
    reseal_manifest(root, base, L.GENERATION_DIR_NAME, L.ATTEMPT_NAME)
    refuses(lambda: L.verify_instance(SLOT, root=root), "attempt record content hash mismatch",
            "edited attempt record not resealed")

    # 7. A forged seed commitment, fully resealed through both manifests.
    root, base = fresh()
    attempt_path = base / "generation" / L.ATTEMPT_NAME
    body = json.loads(attempt_path.read_text("ascii"))
    body["seed_commitments"]["returns"]["seed_uint128"] = 12345
    body.pop("content_sha256")
    body["content_sha256"] = L._content_sha256(body)
    attempt_path.write_bytes(canonical(body))
    reseal_manifest(root, base, L.GENERATION_DIR_NAME, L.ATTEMPT_NAME)
    refuses(lambda: L.verify_instance(SLOT, root=root), "not the U-08 derivation",
            "forged seed commitment")

    # 8. A non-canonical record member (reformatted but semantically equal).
    root, base = fresh()
    index_path = base / L.META_DIR_NAME / L.INDEX_NAME
    index = json.loads(index_path.read_text("ascii"))
    index_path.write_bytes(json.dumps(index, indent=2, sort_keys=True).encode("ascii"))
    reseal_manifest(root, base, L.META_DIR_NAME, L.INDEX_NAME)
    refuses(lambda: L.verify_instance(SLOT, root=root), "not in canonical form",
            "non-canonical index bytes")

    # 9. An index naming a different prepared-record hash.
    root, base = fresh()
    index_path = base / L.META_DIR_NAME / L.INDEX_NAME
    index = json.loads(index_path.read_text("ascii"))
    index["prepared_record"]["sha256"] = fake("other-prepared")
    index.pop("content_sha256")
    index["content_sha256"] = L._content_sha256(index)
    index_path.write_bytes(canonical(index))
    reseal_manifest(root, base, L.META_DIR_NAME, L.INDEX_NAME)
    refuses(lambda: L.verify_instance(SLOT, root=root), "does not name this prepared record",
            "index naming a different prepared record")

    # 10. An index naming a different generation-manifest content hash.
    root, base = fresh()
    index_path = base / L.META_DIR_NAME / L.INDEX_NAME
    index = json.loads(index_path.read_text("ascii"))
    index["generation"]["manifest_content_sha256"] = fake("other-manifest-content")
    index.pop("content_sha256")
    index["content_sha256"] = L._content_sha256(index)
    index_path.write_bytes(canonical(index))
    reseal_manifest(root, base, L.META_DIR_NAME, L.INDEX_NAME)
    refuses(lambda: L.verify_instance(SLOT, root=root), "does not name this generation's manifest",
            "index naming a different manifest content hash")

    # 11. A prepared record claiming non-synthetic support.  Tampered on disk and
    # re-sealed so the refusal is about the record's CONTENT, not its hash: WP5b's
    # reviewed validator is now re-run on the read side and fires first.
    root, base = fresh()
    prepared_path = base / "instance" / "PREPARED.json"
    record = json.loads(prepared_path.read_text("ascii"))
    record["non_synthetic_supported"] = True
    body = dict(record)
    body.pop("content_sha256", None)
    record["content_sha256"] = L._content_sha256(body)
    prepared_bytes = canonical(record)
    prepared_path.write_bytes(prepared_bytes)
    reseal_manifest(root, base, L.PREPARED_DIR_NAME, "PREPARED.json")
    refuses(lambda: L.verify_instance(SLOT, root=root), "WP5b provenance validator",
            "prepared record claiming non-synthetic support")

    # 12. A prepared record with an unknown status, likewise re-sealed.
    root, base = fresh()
    record = json.loads((base / "instance" / "PREPARED.json").read_text("ascii"))
    record["status"] = "prepared_real"
    body = dict(record)
    body.pop("content_sha256", None)
    record["content_sha256"] = L._content_sha256(body)
    (base / "instance" / "PREPARED.json").write_bytes(canonical(record))
    reseal_manifest(root, base, L.PREPARED_DIR_NAME, "PREPARED.json")
    refuses(lambda: L.verify_instance(SLOT, root=root), "WP5b provenance validator",
            "prepared record with an unknown status")

    # 13. A sidecar bound to a different implementation record.
    root, base = fresh()
    reseal_manifest(root, base, L.PREPARED_DIR_NAME, "PREPARED.json",
                    record_hash=OTHER_RECORD, repoint_index=True)
    refuses(lambda: L.verify_instance(SLOT, root=root),
            "name different implementation records",
            "sidecar bound to a different implementation record")

    # 13b. A generation resealed against a different implementation record AND
    #      with the index repointed at it: the sidecar comparison is then the
    #      only remaining binding, so this reaches a check test 13 did not.
    root, base = fresh()
    reseal_manifest(root, base, L.GENERATION_DIR_NAME, L.RETURN_MATRIX_NAME,
                    record_hash=OTHER_RECORD, repoint_index=True)
    refuses(lambda: L.verify_instance(SLOT, root=root),
            "the manifest and the generation record name different implementation records",
            "generation resealed against a foreign implementation record")
    root, base = fresh()
    reseal_manifest(root, base, L.GENERATION_DIR_NAME, L.RETURN_MATRIX_NAME,
                    record_hash=OTHER_RECORD, repoint_index=True)
    generation_record = json.loads(
        (base / L.GENERATION_DIR_NAME / L.GENERATION_NAME).read_text("ascii"))
    generation_record["implementation_record"] = OTHER_RECORD
    generation_record.pop("content_sha256")
    generation_record["content_sha256"] = L._content_sha256(generation_record)
    (base / L.GENERATION_DIR_NAME / L.GENERATION_NAME).write_bytes(
        canonical(generation_record))
    reseal_manifest(root, base, L.GENERATION_DIR_NAME, L.GENERATION_NAME,
                    record_hash=OTHER_RECORD, repoint_index=True)
    refuses(lambda: L.verify_instance(SLOT, root=root),
            "the prepared sidecar and the generation name different implementation records",
            "a wholly resealed foreign-record generation")

    # 14. An extra file in the slot directory.
    root, base = fresh()
    (base / "EXTRA.json").write_bytes(b"{}")
    refuses(lambda: L.verify_instance(SLOT, root=root), "contents differ from the canonical layout",
            "extra file in the slot directory")

    # 15. A subdirectory inside the generation directory.
    root, base = fresh()
    (base / "generation" / "sub").mkdir()
    refuses(lambda: L.verify_instance(SLOT, root=root), "forbids",
            "subdirectory inside the generation")

    # 16. A symlinked member: WP5 refuses to hash one
    #     (``stage2_generation_writer.py:110,344,366``).
    root, base = fresh()
    real = base / "generation" / L.ATTEMPT_NAME
    payload = real.read_bytes()
    real.unlink()
    real.symlink_to(base / "instance" / "PREPARED.json")
    refuses(lambda: L.verify_instance(SLOT, root=root), "ATTEMPT.json",
            "symlinked attempt record")
    real.unlink()
    real.write_bytes(payload)

    # 17. A missing slot directory.
    root, base = fresh()
    import shutil
    shutil.rmtree(base)
    refuses(lambda: L.verify_instance(SLOT, root=root), "is not a directory",
            "missing instance directory")

    # 18. An instance root holding a non-canonical directory.  The stray check
    #     comes FIRST: a non-canonical name is refused by slot_number() before
    #     the expected-set comparison is reached, which is the stricter order.
    root, base = fresh()
    stray = base.parent / "stage2_06"
    stray.mkdir()
    refuses(lambda: L.verify_all_slots(root=root), "not one of",
            "non-canonical slot directory under the instance root")
    refuses(lambda: L.verify_all_slots(root=root, present=(1, 2, 3, 4)), "not one of",
            "named verification while a non-canonical directory exists")
    stray.rmdir()
    refuses(lambda: L.verify_all_slots(root=root, present=(1, 2, 3, 4)),
            "expected exactly", "five-slot verification with a missing slot")
    refuses(lambda: L.verify_all_slots(root=root, present=(1, 2, 3, 4, 5)),
            "expected exactly", "five-slot verification with four missing slots")
    check(L.verify_all_slots(root=root)["count"] == 1,
          "the single written slot stopped verifying after the stray was removed")

    # 19. Two slots naming the same instance_id.  Only the CROSS-slot check can
    #     see this: within one slot the index and the generation record are two
    #     separately bound objects, but the protocol forbids two slots sharing an
    #     identity, and nothing inside a single directory can detect it.
    root, base = fresh()
    write_one(root, 2)
    second = root / "research/g9/stage2_instances/stage2_02"
    index_path = second / L.META_DIR_NAME / L.INDEX_NAME
    index = json.loads(index_path.read_text("ascii"))
    shared = json.loads((base / L.META_DIR_NAME / L.INDEX_NAME).read_text("ascii"))["instance_id"]
    index["instance_id"] = shared
    index.pop("content_sha256")
    index["content_sha256"] = L._content_sha256(index)
    index_path.write_bytes(canonical(index))
    generation_record = json.loads(
        (second / L.GENERATION_DIR_NAME / L.GENERATION_NAME).read_text("ascii"))
    generation_record["instance_id"] = shared
    generation_record.pop("content_sha256")
    generation_record["content_sha256"] = L._content_sha256(generation_record)
    (second / L.GENERATION_DIR_NAME / L.GENERATION_NAME).write_bytes(
        canonical(generation_record))
    reseal_manifest(root, second, L.GENERATION_DIR_NAME, L.GENERATION_NAME,
                    repoint_index=True)
    # The prepared record in slot 2 must be retagged with the same shared
    # identity, or the layout's OWN cross-binding (prepared record instance_id vs
    # generation instance_id) refuses slot 2 before the test ever reaches the
    # cross-SLOT duplicate check.  This is the write-side counterpart of the
    # identity binding: three records (generation, index, prepared) all claiming
    # one identity is the precondition for "two slots name the same instance_id".
    prepared_path = second / L.PREPARED_DIR_NAME / "PREPARED.json"
    prepared_body = json.loads(prepared_path.read_text("ascii"))
    prepared_body["instance"]["instance_id"] = shared
    prepared_body.pop("content_sha256")
    prepared_body["content_sha256"] = L._content_sha256(prepared_body)
    prepared_path.write_bytes(canonical(prepared_body))
    # ``repoint_index=True`` repoints BOTH the prepared record's byte hash and the
    # prepared manifest's byte and content hashes, then reseals the index's own
    # manifest -- every binding the retag invalidated.
    reseal_manifest(root, second, L.PREPARED_DIR_NAME, "PREPARED.json",
                    repoint_index=True)
    check(L.verify_instance(2, root=root)["verdict"] == "verified",
          "each slot alone verifies with a shared instance_id")
    refuses(lambda: L.verify_all_slots(root=root), "same instance_id",
            "two slots naming the same instance_id")


def reseal_manifest(root: Path, base: Path, subdir: str, member: str,
                    record_hash: str | None = None, repoint_index: bool = False) -> None:
    """Rebuild a subdirectory manifest so it commits to the edited member.

    This is the strongest on-disk forgery available to a fixture: the manifest
    is fully resealed with WP5's own hashing, so only the layout's own
    derivation and binding checks can catch what follows.

    ``repoint_index`` additionally rewrites the index's recorded manifest hashes
    AND reseals the index's own WP5 manifest.  Without it a reseal also
    invalidates the index binding, which refuses on its own -- so a test that
    wants to reach a DEEPER check must repoint the index too, or it is only
    re-testing the index binding.
    """
    payload = {}
    for name in sorted(os.listdir(base / subdir)):
        if name == L.MANIFEST_NAME:
            continue
        payload[name] = (base / subdir / name).read_bytes()
    manifest = L._writer.build_manifest(
        payload, implementation_record_content_sha256=record_hash or RECORD)
    manifest_path = base / subdir / L.MANIFEST_NAME
    manifest_path.write_bytes(canonical(manifest))
    if repoint_index:
        index_path = base / L.META_DIR_NAME / L.INDEX_NAME
        index = json.loads(index_path.read_text("ascii"))
        # The index binds the generation manifest AND the prepared manifest, each
        # by file bytes and by content hash (index schema v2).  A reseal of
        # EITHER sidecar changes that side's manifest, so the refs must be
        # repointed under the ref that actually names ``subdir`` -- pointing the
        # generation ref at a prepared-sidecar manifest would leave the real
        # generation binding stale and stop the test one check too early.
        if subdir == L.GENERATION_DIR_NAME:
            index["generation"]["manifest_sha256"] = hashlib.sha256(
                manifest_path.read_bytes()).hexdigest()
            index["generation"]["manifest_content_sha256"] = manifest["content_sha256"]
        elif subdir == L.PREPARED_DIR_NAME:
            # The prepared sidecar's member bytes are bound twice: as the record
            # itself (``sha256``) and through its manifest (which just changed
            # because the record changed).  Both must be repointed.
            index["prepared_record"]["sha256"] = hashlib.sha256(
                (base / subdir / member).read_bytes()).hexdigest()
            index["prepared_record"]["manifest_sha256"] = hashlib.sha256(
                manifest_path.read_bytes()).hexdigest()
            index["prepared_record"]["manifest_content_sha256"] = manifest["content_sha256"]
        index["implementation_record"] = manifest["implementation_record_content_sha256"]
        index.pop("content_sha256")
        index["content_sha256"] = L._content_sha256(index)
        index_path.write_bytes(canonical(index))
        # The index lives in its OWN WP5 manifest, so editing it invalidates that
        # manifest too.  Resealing both is what lets a test reach the check it is
        # aimed at instead of stopping at the meta rehash.
        meta_manifest = L._writer.build_manifest(
            {L.INDEX_NAME: index_path.read_bytes()},
            implementation_record_content_sha256=manifest["implementation_record_content_sha256"])
        (base / L.META_DIR_NAME / L.MANIFEST_NAME).write_bytes(canonical(meta_manifest))


def payload_ok(**overrides) -> dict[str, bytes]:
    kwargs = dict(slot=SLOT, attempt=ACCEPTED_ATTEMPT, instance_id=INSTANCE_ID,
                  sector_partition_sha256=PARTITION, feasible_count=38760,
                  return_matrix=MATRIX, implementation_record_content_sha256=RECORD,
                  mu_new=MU_NEW, sigma_new=SIGMA_NEW, rejected_attempt_history=HISTORY)
    kwargs.update(overrides)
    return L.build_generation_payload(**kwargs)


def test_payload_builder() -> None:
    payload = payload_ok()
    check(set(payload) == {L.ATTEMPT_NAME, L.GENERATION_NAME, L.RETURN_MATRIX_NAME},
          f"generation payload members drift: {sorted(payload)}")
    check(payload[L.RETURN_MATRIX_NAME] == MATRIX, "generation payload matrix drift")
    # The payload carries the protocol's retained-rejection content and the
    # canonical moments, as bytes.
    ledger = json.loads(payload[L.ATTEMPT_NAME].decode("ascii"))
    check(ledger["disposition"] == L.DISPOSITION_ACCEPTED
          and len(ledger["rejected_attempt_history"]) == len(HISTORY),
          "the payload ledger does not carry the rejected-attempt history")
    generation = json.loads(payload[L.GENERATION_NAME].decode("ascii"))
    check(generation["moment_summary"]["mu_new"]["sha256"] == MU_NEW_SHA,
          "the payload generation record does not carry the mu_new digest")
    # The payload validates through the writer's own manifest machinery.
    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-payload-") as tmp:
        target = Path(tmp) / "generation"
        receipt = L._writer.write_generation(target=target, files=payload,
                                             implementation_record_content_sha256=RECORD)
        check(receipt["file_count"] == 3, "payload file count drift")
        summary = L.validate_generation_directory(target)
        check(summary["verdict"] == "verified", "payload did not validate as a generation")
        check(summary["return_matrix_sha256"] == MATRIX_SHA, "payload matrix hash drift")
        check(summary["rejected_attempt_history_count"] == len(HISTORY),
              "the promoted ledger lost its rejected-attempt history")
        check(summary["mu_new_sha256"] == MU_NEW_SHA,
              "the promoted generation record lost its mu_new digest")
    refuses(lambda: payload_ok(return_matrix=MATRIX[:10]),
            "must be exactly", "payload short matrix")
    refuses(lambda: payload_ok(return_matrix=None),
            "must be bytes", "payload matrix None")
    refuses(lambda: payload_ok(instance_id=""),
            "non-empty string", "payload empty instance id")
    # A malformed history is refused by the payload builder too, so it can never
    # reach the writer.
    refuses(lambda: payload_ok(rejected_attempt_history=[dict(HISTORY[0], rejection_codes=[])]),
            "at least one fixed rejection code", "payload rejected entry with no code")
    refuses(lambda: payload_ok(mu_new=MU_NEW[:-1]),
            "must hold exactly 20 encoded values", "payload short mu_new")


# ---------------------------------------------------------------------------
# Per-guard tests the mutation sweep demanded
#
# Each test below kills one specific mutant the sweep reported as SURVIVED.
# They are written per guard rather than as a generic loop because each one
# isolates a DIFFERENT conjunct: a mutant that drops one conjunct of a compound
# guard survives unless an input violates exactly that conjunct.
# ---------------------------------------------------------------------------
class StrSubclass(str):
    """A non-empty str subclass: truthy and ``isinstance``-a str, but not ``type is str``."""


class DictSubclass(dict):
    """A dict subclass that evaluates as a mapping but is not an exact dict."""


class ListSubclass(list):
    """A list subclass: a sequence, JSON-rendered identically, not an exact list."""


def test_scalar_guards_separately() -> None:
    # _slot_int / _attempt_int: the type guard and the range guard are separate.
    for value in (0, 6, -1, 200):
        refuses(lambda value=value: L._slot_int(value), "slot must be in 1..5",
                f"_slot_int range {value!r}")
    for value in (True, False, 1.0, "1", None):
        refuses(lambda value=value: L._slot_int(value), "slot must be an int",
                f"_slot_int type {value!r}")
    check(L._slot_int(1) == 1 and L._slot_int(5) == 5, "_slot_int refused a valid slot")
    for value in (-1, 128, 1000):
        refuses(lambda value=value: L._attempt_int(value), "attempt must be in 0..127",
                f"_attempt_int range {value!r}")
    for value in (True, 0.0, "0", None):
        refuses(lambda value=value: L._attempt_int(value), "attempt must be an int",
                f"_attempt_int type {value!r}")
    check(L._attempt_int(0) == 0 and L._attempt_int(127) == 127,
          "_attempt_int refused a valid attempt")
    # A range-passing but type-wrong value is what kills the TYPE guard alone.
    check(True is not False, "sanity")

    # _non_empty_string: truthy but wrong type, and falsy but right type.
    for value in (StrSubclass("x"), 7, None, b"bytes", ["a"]):
        refuses(lambda value=value: L._non_empty_string(value, "label"), "must be a str",
                f"_non_empty_string type {type(value).__name__}")
    # The empty str is an exact str, so it must reach the TRUTH guard: that is
    # the input that distinguishes the truth guard from the type guard.  An empty
    # SUBCLASS is refused by the type guard instead, which is the other side.
    refuses(lambda: L._non_empty_string("", "label"), "must be a non-empty string",
            "_non_empty_string empty str via the truth guard")
    refuses(lambda: L._non_empty_string(StrSubclass(""), "label"), "must be a str",
            "_non_empty_string empty str subclass via the type guard")
    check(L._non_empty_string("x", "label") == "x", "_non_empty_string refused a valid string")

    # _count_int: non-negative and exact-int.
    for value in (-1, -1000):
        refuses(lambda value=value: L._count_int(value, "n"), "must be non-negative",
                f"_count_int negative {value!r}")
    for value in (True, False, 1.0, "1", None):
        refuses(lambda value=value: L._count_int(value, "n"), "must be an int",
                f"_count_int type {value!r}")
    check(L._count_int(0, "n") == 0, "_count_int refused a valid zero")

    # _sha: type, length and character-set are three separate refusals.  Each
    # input below violates exactly ONE of them, which is what kills each mutant.
    for value in (None, 7, b"a" * 64, StrSubclass("a" * 64)):
        refuses(lambda value=value: L._sha(value, "h"), "h must be a str",
                f"_sha type {type(value).__name__}")
    for value in ("", "a", "a" * 63, "a" * 65, "zz"):
        refuses(lambda value=value: L._sha(value, "h"), "exactly 64 characters",
                f"_sha length {value[:8]!r}")
    for value in ("A" * 64, "g" * 64, ("a" * 63) + "Z", ("a" * 63) + " "):
        refuses(lambda value=value: L._sha(value, "h"), "lowercase SHA-256",
                f"_sha charset {value[-1:]!r}")
    check(L._sha("a" * 64, "h") == "a" * 64, "_sha refused a valid lowercase hash")

    # _bytes_sha256: a str payload must be a typed refusal, not a raw TypeError.
    for value in ("not bytes", None, 7, ["a"], bytearray(b"x")):
        refuses(lambda value=value: L._bytes_sha256(value, "matrix"), "must be bytes",
                f"_bytes_sha256 type {type(value).__name__}")
    check(L._bytes_sha256(b"payload", "matrix") == hashlib.sha256(b"payload").hexdigest(),
          "_bytes_sha256 refused valid bytes")

    # _canonical must refuse a non-canonicalisable value through the typed error.
    for value in ({1, 2}, {"a": {1, 2}}, float("nan"), float("inf")):
        refuses(lambda value=value: L._canonical(value), "not canonical JSON",
                f"_canonical {type(value).__name__}")


def test_subclass_and_mapping_refusals() -> None:
    """Subclasses are refused wherever an exact type is required.

    A ``str``/``dict`` subclass renders through ``json.dumps`` exactly like its
    base, so every hash check would pass; only the exact-type test can see it.
    """
    for field, bad in (("instance_id", StrSubclass(INSTANCE_ID)),):
        refuses(lambda bad=bad: generation_record_ok(instance_id=bad), "must be a str",
                f"build_generation_record {field} subclass")
    # A str subclass must also be refused inside the recorded moments: the values
    # are rendered by json.dumps exactly like a plain str, so only the exact-type
    # test can see it.
    refuses(lambda: generation_record_ok(mu_new=[StrSubclass(MU_NEW[0])] + MU_NEW[1:]),
            "must hold only strings", "build_generation_record str-subclass mu_new")
    # The payload builder inherits the same guards.
    refuses(lambda: L.build_generation_payload(
        slot=SLOT, attempt=ACCEPTED_ATTEMPT, instance_id=StrSubclass(INSTANCE_ID),
        sector_partition_sha256=PARTITION, feasible_count=1, return_matrix=MATRIX,
        implementation_record_content_sha256=RECORD, mu_new=MU_NEW, sigma_new=SIGMA_NEW,
        rejected_attempt_history=list(HISTORY)),
        "must be a str", "build_generation_payload subclass instance_id")
    # The validators must refuse a subclass too, not just the builders.
    generation = generation_record_ok()
    generation["instance_id"] = StrSubclass(INSTANCE_ID)
    generation.pop("content_sha256")
    generation["content_sha256"] = L._content_sha256(generation)
    refuses(lambda: L.validate_generation_record(generation), "must be a str",
            "validate_generation_record subclass instance_id")

    # A dict subclass in place of a mapping the validators demand.
    attempts = attempt_record_ok()
    attempts["seed_commitments"] = DictSubclass(attempts["seed_commitments"])
    attempts.pop("content_sha256")
    attempts["content_sha256"] = L._content_sha256(attempts)
    refuses(lambda: L.validate_attempt_record(attempts), "seed_commitments must be an object",
            "validate_attempt_record dict subclass commitments")
    attempts = attempt_record_ok()
    attempts["seed_commitments"]["returns"] = DictSubclass(
        attempts["seed_commitments"]["returns"])
    attempts.pop("content_sha256")
    attempts["content_sha256"] = L._content_sha256(attempts)
    refuses(lambda: L.validate_attempt_record(attempts),
            "seed commitment returns must be an object",
            "validate_attempt_record dict subclass commitment entry")
    # And in the schema-v2 nested structures, which are new objects with their own
    # exact-type requirements.
    moments = generation_record_ok()
    moments["moment_summary"]["mu_new"] = DictSubclass(moments["moment_summary"]["mu_new"])
    moments.pop("content_sha256")
    moments["content_sha256"] = L._content_sha256(moments)
    refuses(lambda: L.validate_generation_record(moments), "mu_new must be an object",
            "validate_generation_record dict subclass moment block")
    refused = attempt_record_ok()
    refused["rejected_attempt_history"] = ListSubclass(refused["rejected_attempt_history"])
    refused.pop("content_sha256")
    refused["content_sha256"] = L._content_sha256(refused)
    refuses(lambda: L.validate_attempt_record(refused),
            "rejected_attempt_history must be a list",
            "validate_attempt_record list-subclass history")
    # The moment VALUES list, on the read side, is required to be an exact list:
    # a record read from JSON never yields a subclass, so one is drift.
    from_list = generation_record_ok()
    from_list["moment_summary"]["mu_new"]["values"] = ListSubclass(
        from_list["moment_summary"]["mu_new"]["values"])
    from_list.pop("content_sha256")
    from_list["content_sha256"] = L._content_sha256(from_list)
    refuses(lambda: L.validate_generation_record(from_list),
            "must be a list in a record read from disk",
            "validate_generation_record list-subclass moment values")


def test_bool_substitutes_refused() -> None:
    """A bool or an int 0/1 must not pass where the layout demands ``False``.

    ``0 == False`` and ``1 == True``, so only an identity test can refuse them.
    """
    for value in (1, "false", [], {}, 0.0, 0, None, StrSubclass("")):
        refuses(lambda value=value: L._require_not_non_synthetic(value),
                "claims non-synthetic support",
                f"_require_not_non_synthetic {value!r}")
    check(L._require_not_non_synthetic(False) is None,
          "_require_not_non_synthetic refused the declared False")


def test_status_guard_separately() -> None:
    for value in (None, 7, b"x", ["s"]):
        refuses(lambda value=value: L._require_status(value), "status must be a str",
                f"_require_status type {type(value).__name__}")
    for value in ("",):
        refuses(lambda value=value: L._require_status(value), "non-empty string",
                "_require_status empty")
    for value in ("prepared_real", "accepted", "PREPARED_SYNTHETIC_ONLY", "prepared_synthetic"):
        refuses(lambda value=value: L._require_status(value), "not an accepted",
                f"_require_status unknown {value!r}")
    check(L._require_status(L.PREPARED_STATUS) is None,
          "_require_status refused the declared status")


def test_directory_guards() -> None:
    """The directory/file/symlink guards are separately testable."""
    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-dirguards-") as tmp:
        root = Path(tmp)
        target = root / "real"
        target.mkdir()
        # _require_real_dir: a missing path, a file, a symlink-to-dir.
        refuses(lambda: L._require_real_dir(root / "absent", "d"), "is not a directory",
                "_require_real_dir missing")
        plain = root / "plain"
        plain.write_bytes(b"x")
        refuses(lambda: L._require_real_dir(plain, "d"), "is not a directory",
                "_require_real_dir file")
        link = root / "link"
        link.symlink_to(target)
        refuses(lambda: L._require_real_dir(link, "d"), "is a symlink",
                "_require_real_dir symlink")
        check(L._require_real_dir(target, "d") is None, "_require_real_dir refused a real dir")

        # _require_absent: present dir, present file, DANGLING symlink.
        refuses(lambda: L._require_absent(target, "p"), "already exists",
                "_require_absent existing dir")
        refuses(lambda: L._require_absent(plain, "p"), "already exists",
                "_require_absent existing file")
        dangling = root / "dangling"
        dangling.symlink_to(root / "does-not-exist")
        refuses(lambda: L._require_absent(dangling, "p"), "is a symlink",
                "_require_absent dangling symlink")
        check(L._require_absent(root / "never", "p") is None,
              "_require_absent refused an absent path")

        # _list_names refuses a symlinked directory and a missing directory.
        refuses(lambda: L._list_names(link, "d"), "is a symlink", "_list_names symlink")
        refuses(lambda: L._list_names(root / "absent", "d"), "is not a directory",
                "_list_names missing")
        refuses(lambda: L._list_names(plain, "d"), "is not a directory", "_list_names file")

        # _list_flat_names refuses a subdirectory; _list_names accepts one.
        (target / "sub").mkdir()
        (target / "file.txt").write_bytes(b"x")
        check(L._list_names(target, "d") == ["file.txt", "sub"], "_list_names dropped a subdir")
        refuses(lambda: L._list_flat_names(target, "d"), "subdirectory, which this layout forbids",
                "_list_flat_names with a subdirectory")
        (target / "sub").rmdir()
        check(L._list_flat_names(target, "d") == ["file.txt"],
              "_list_flat_names refused a flat directory")

        # _real_file / _sha_file refuse a symlink to a regular file, a directory
        # and a missing path.  A symlink to a regular file is the case that makes
        # the is_file() and is_symlink() checks non-redundant.
        member = target / "file.txt"
        link_file = root / "linkfile"
        link_file.symlink_to(member)
        refuses(lambda: L._real_file(link_file, "f"), "is a symlink", "_real_file symlink")
        refuses(lambda: L._sha_file(link_file, "f"), "is a symlink", "_sha_file symlink")
        refuses(lambda: L._real_file(target, "f"), "not a regular file", "_real_file directory")
        refuses(lambda: L._sha_file(target, "f"), "not a regular file", "_sha_file directory")
        refuses(lambda: L._real_file(root / "absent", "f"), "not a regular file",
                "_real_file missing")
        refuses(lambda: L._sha_file(root / "absent", "f"), "not a regular file",
                "_sha_file missing")
        check(L._real_file(member, "f") == b"x", "_real_file refused a regular file")


def test_record_parsing_refusals() -> None:
    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-parse-") as tmp:
        root = Path(tmp)
        # Not ASCII.
        bad = root / "nonascii.json"
        bad.write_bytes(b'{"k": "\xff\xfe"}')
        refuses(lambda: L._load_record(bad, "r"), "is not ASCII", "_load_record non-ASCII")
        # Not JSON at all.
        broken = root / "broken.json"
        broken.write_bytes(b"{not json")
        refuses(lambda: L._load_record(broken, "r"), "is not JSON", "_load_record broken JSON")
        # Valid JSON but not an object.
        array = root / "array.json"
        array.write_bytes(b"[1,2,3]")
        refuses(lambda: L._load_record(array, "r"), "must be a JSON object",
                "_load_record JSON array")
        number = root / "number.json"
        number.write_bytes(b"42")
        refuses(lambda: L._load_record(number, "r"), "must be a JSON object",
                "_load_record JSON number")
        # An object that is not in canonical form.
        spaced = root / "spaced.json"
        spaced.write_bytes(b'{"b": 1, "a": 2}')
        refuses(lambda: L._load_record(spaced, "r"), "not in canonical form",
                "_load_record non-canonical object")
        # A canonical object is accepted.
        good = root / "good.json"
        good.write_bytes(canonical({"a": 1, "b": 2}))
        check(L._load_record(good, "r") == {"a": 1, "b": 2}, "_load_record refused a canonical object")


def test_generation_member_disagreements() -> None:
    """The cross-record agreement checks in validate_generation_directory."""
    def fresh() -> tuple[Path, Path]:
        tmp = tempfile.mkdtemp(dir=SCRATCH, prefix="wp8d-disagree-")
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
        write_one(root)
        return root, root / "research/g9/stage2_instances/stage2_01"

    # The generation record names a different SLOT than the attempt record.
    root, base = fresh()
    path = base / "generation" / L.GENERATION_NAME
    body = json.loads(path.read_text("ascii"))
    body["slot"] = 2
    body.pop("content_sha256")
    body["content_sha256"] = L._content_sha256(body)
    path.write_bytes(canonical(body))
    reseal_manifest(root, base, L.GENERATION_DIR_NAME, L.GENERATION_NAME, repoint_index=True)
    refuses(lambda: L.verify_instance(SLOT, root=root), "slot disagrees with the attempt record",
            "generation record naming a different slot")

    # The generation record names a different ATTEMPT than the attempt record.
    root, base = fresh()
    path = base / "generation" / L.GENERATION_NAME
    body = json.loads(path.read_text("ascii"))
    body["attempt"] = 5
    body.pop("content_sha256")
    body["content_sha256"] = L._content_sha256(body)
    path.write_bytes(canonical(body))
    reseal_manifest(root, base, L.GENERATION_DIR_NAME, L.GENERATION_NAME, repoint_index=True)
    refuses(lambda: L.verify_instance(SLOT, root=root),
            "attempt disagrees with the attempt record",
            "generation record naming a different attempt")

    # The manifest names a different implementation record than the generation.
    root, base = fresh()
    reseal_manifest(root, base, L.GENERATION_DIR_NAME, L.RETURN_MATRIX_NAME,
                    record_hash=OTHER_RECORD, repoint_index=True)
    refuses(lambda: L.verify_instance(SLOT, root=root),
            "the manifest and the generation record name different implementation records",
            "generation manifest naming a different implementation record")


def test_index_disagreements() -> None:
    """Every index-to-file agreement check in verify_instance, one at a time."""
    def fresh() -> tuple[Path, Path]:
        tmp = tempfile.mkdtemp(dir=SCRATCH, prefix="wp8d-index-")
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
        write_one(root)
        return root, root / "research/g9/stage2_instances/stage2_01"

    def edit_index(base: Path, edit) -> None:
        path = base / L.META_DIR_NAME / L.INDEX_NAME
        body = json.loads(path.read_text("ascii"))
        edit(body)
        body.pop("content_sha256")
        body["content_sha256"] = L._content_sha256(body)
        path.write_bytes(canonical(body))
        reseal_manifest(base.parent.parent.parent, base, L.META_DIR_NAME, L.INDEX_NAME)

    for label, edit, needle in (
        # The index's slot is now compared to the REQUESTED slot / the directory
        # that was actually opened, which is a strictly stronger boundary than the
        # comparison with the generation record this test used to assert: three
        # self-consistent records naming the wrong slot now fail here.
        ("slot and slot_name", lambda m: m.update(slot=3, slot_name="stage2_03"),
         "slot disagrees with the instance directory"),
        ("slot_name alone", lambda m: m.update(slot_name="stage2_03"),
         "canonical name of its slot"),
        # The index's top-level attempt and its nested ledger attempt are bound to
        # each other, so a re-sealed index must move BOTH to reach the comparison
        # against the generation.  Moving only the top-level one is a separate
        # refusal and is asserted separately below.
        ("attempt", lambda m: (m.update(attempt=4),
                               m["attempt_ledger"].update(attempt=4)),
         "attempt_ledger attempt disagrees with the accepted attempt"),
        ("instance_id", lambda m: m.update(instance_id="other"),
         "instance_id disagrees with the generation"),
        ("implementation record", lambda m: m.update(implementation_record=fake("other-record")),
         "implementation record disagrees with the generation"),
        ("manifest bytes", lambda m: m["generation"].update(manifest_sha256=fake("other-bytes")),
         "manifest bytes"),
        ("manifest content", lambda m: m["generation"].update(
            manifest_content_sha256=fake("other-content")), "manifest content hash"),
        ("prepared hash", lambda m: m["prepared_record"].update(sha256=fake("other-prepared")),
         "this prepared record's bytes"),
        # The ledger bindings, which schema v3 added: a re-sealed index cannot
        # misreport the ledger's bytes, its content hash, its disposition, its
        # rejection-code count, its retained-history count, or either moment
        # digest, because each is compared against the ledger and generation files
        # rather than trusted from the index.
        ("ledger bytes", lambda m: m["attempt_ledger"].update(sha256=fake("other-ledger")),
         "does not name this retained-attempt ledger's bytes"),
        ("ledger content hash", lambda m: m["attempt_ledger"].update(
            content_sha256=fake("other-ledger-content")),
         "does not name this retained-attempt ledger's content hash"),
        ("ledger disposition", lambda m: m["attempt_ledger"].update(
            disposition=L.DISPOSITION_REJECTED), "must claim the accepted disposition"),
        ("ledger code count", lambda m: m["attempt_ledger"].update(rejection_code_count=3),
         "rejection code count disagrees with the ledger"),
        ("ledger history count", lambda m: m["attempt_ledger"].update(
            rejected_attempt_history_count=0), "history count disagrees with the ledger"),
        ("mu_new digest", lambda m: m["moments"].update(mu_new_sha256=fake("other-mu")),
         "does not name this generation's mu_new digest"),
        ("Sigma_new digest", lambda m: m["moments"].update(sigma_new_sha256=fake("other-sigma")),
         "does not name this generation's Sigma_new digest"),
    ):
        root, base = fresh()
        edit_index(base, edit)
        refuses(lambda: L.verify_instance(SLOT, root=root), needle,
                f"index disagreeing on {label}")

    # Moving ONLY the index's top-level attempt is refused by the index's own
    # record-internal binding, which is a distinct boundary from the cross-record
    # comparison above and worth its own assertion.
    root, base = fresh()
    edit_index(base, lambda m: m.update(attempt=4))
    refuses(lambda: L.verify_instance(SLOT, root=root),
            "attempt_ledger attempt disagrees with the index attempt",
            "index top-level attempt moved without its ledger attempt")

    # The index status can disagree with the prepared FILE's status only when the
    # FILE says something the index validator also accepts -- which it cannot,
    # since both accept one status.  So the observable case is the reverse: the
    # prepared file claiming a status the layout refuses, already tested above.
    root, base = fresh()
    index_path = base / L.META_DIR_NAME / L.INDEX_NAME
    body = json.loads(index_path.read_text("ascii"))
    body["status"] = "prepared_real"
    body["prepared_record"]["status"] = "prepared_real"
    body.pop("content_sha256")
    body["content_sha256"] = L._content_sha256(body)
    index_path.write_bytes(canonical(body))
    reseal_manifest(root, base, L.META_DIR_NAME, L.INDEX_NAME)
    refuses(lambda: L.verify_instance(SLOT, root=root), "not an accepted",
            "index and prepared record both claiming an unknown status")


def test_sidecar_and_meta_refusals() -> None:
    def fresh() -> tuple[Path, Path]:
        tmp = tempfile.mkdtemp(dir=SCRATCH, prefix="wp8d-sidecar-")
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
        write_one(root)
        return root, root / "research/g9/stage2_instances/stage2_01"

    # An extra file in the meta directory.
    root, base = fresh()
    (base / L.META_DIR_NAME / "EXTRA.json").write_bytes(b"{}")
    refuses(lambda: L.verify_instance(SLOT, root=root), "contents differ from the canonical layout",
            "extra file in the meta directory")
    # A missing index in the meta directory.
    root, base = fresh()
    (base / L.META_DIR_NAME / L.INDEX_NAME).unlink()
    refuses(lambda: L.verify_instance(SLOT, root=root), "contents differ from the canonical layout",
            "missing instance index")
    # A subdirectory inside the meta directory.
    root, base = fresh()
    (base / L.META_DIR_NAME / "sub").mkdir()
    refuses(lambda: L.verify_instance(SLOT, root=root), "subdirectory, which this layout forbids",
            "subdirectory inside the meta directory")
    # A missing prepared record.
    root, base = fresh()
    (base / "instance" / "PREPARED.json").unlink()
    refuses(lambda: L.verify_instance(SLOT, root=root), "contents differ from the canonical layout",
            "missing prepared record")
    # A prepared record that is a JSON array, not an object.
    root, base = fresh()
    (base / "instance" / "PREPARED.json").write_bytes(b"[]")
    reseal_manifest(root, base, L.PREPARED_DIR_NAME, "PREPARED.json")
    refuses(lambda: L.verify_instance(SLOT, root=root), "must be a JSON object",
            "prepared record written as a JSON array")
    # A prepared record missing its status field entirely: WP5b's reviewed
    # validator refuses the wrong key set first.
    root, base = fresh()
    body = {"non_synthetic_supported": False}
    (base / "instance" / "PREPARED.json").write_bytes(canonical(body))
    reseal_manifest(root, base, L.PREPARED_DIR_NAME, "PREPARED.json")
    refuses(lambda: L.verify_instance(SLOT, root=root), "WP5b provenance validator",
            "prepared record with no status field")
    # A prepared record missing its non_synthetic_supported field entirely.
    root, base = fresh()
    (base / "instance" / "PREPARED.json").write_bytes(canonical({"status": L.PREPARED_STATUS}))
    reseal_manifest(root, base, L.PREPARED_DIR_NAME, "PREPARED.json")
    refuses(lambda: L.verify_instance(SLOT, root=root), "WP5b provenance validator",
            "prepared record with no non_synthetic_supported field")
    # A manifest whose implementation-record hash is malformed.
    root, base = fresh()
    manifest_path = base / "generation" / L.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text("ascii"))
    manifest["implementation_record_content_sha256"] = "zz"
    manifest.pop("content_sha256")
    manifest["content_sha256"] = L._writer._content_sha256(manifest)
    manifest_path.write_bytes(canonical(manifest))
    refuses(lambda: L.verify_instance(SLOT, root=root), "manifest record hash",
            "generation manifest with a malformed record hash (WP5 refuses first)")


def test_write_and_promote_refusals() -> None:
    """The OS-error branches of the write path, driven by patched os calls."""
    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-oserr-") as tmp:
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)

        def attempt() -> None:
            L.write_instance(slot=SLOT, attempt=ACCEPTED_ATTEMPT, instance_id=INSTANCE_ID,
                            sector_partition_sha256=PARTITION, feasible_count=1,
                            return_matrix=MATRIX, prepared_record=prepared(),
                            implementation_record_content_sha256=RECORD,
                            mu_new=list(MU_NEW), sigma_new=[list(r) for r in SIGMA_NEW],
                            rejected_attempt_history=list(HISTORY), root=root)

        # mkdir raising OSError.
        original_mkdir = os.mkdir
        try:
            os.mkdir = lambda *a, **k: (_ for _ in ()).throw(OSError("refused"))
            refuses(attempt, "cannot create staging directory", "write with mkdir refusing")
        finally:
            os.mkdir = original_mkdir
        check(sorted(os.listdir(root / "research/g9/stage2_instances")) == [],
              "a refused mkdir left a staging directory behind")

        # os.rename raising OSError: the staging directory must be cleaned up.
        original_rename = os.rename
        try:
            os.rename = lambda *a, **k: (_ for _ in ()).throw(OSError("refused"))
            refuses(attempt, "cannot promote", "write with rename refusing")
        finally:
            os.rename = original_rename
        leftovers = sorted(p.name for p in (root / "research/g9/stage2_instances").iterdir()
                           if p.name.startswith(L.STAGING_PREFIX))
        check(leftovers == [], f"a refused rename left staging behind: {leftovers}")

        # os.open raising OSError inside _fsync_dir.
        check(L.write_instance(slot=SLOT, attempt=ACCEPTED_ATTEMPT, instance_id=INSTANCE_ID,
                               sector_partition_sha256=PARTITION, feasible_count=1,
                               return_matrix=MATRIX, prepared_record=prepared(),
                               implementation_record_content_sha256=RECORD,
                               mu_new=list(MU_NEW), sigma_new=[list(r) for r in SIGMA_NEW],
                               rejected_attempt_history=list(HISTORY),
                               root=root)["verdict"] == "written",
              "the control write failed")
        original_open = os.open
        try:
            os.open = lambda *a, **k: (_ for _ in ()).throw(OSError("refused"))
            refuses(lambda: L._fsync_dir(root), "cannot open directory", "_fsync_dir open failing")
            os.open = lambda *a, **k: original_open(*a, **k)
            refuses(lambda: L._fsync_dir(root / "absent"), "cannot open directory",
                    "_fsync_dir on a missing directory")
        finally:
            os.open = original_open

        # os.fsync raising OSError inside _fsync_dir.
        original_fsync = os.fsync
        try:
            os.fsync = lambda *a, **k: (_ for _ in ()).throw(OSError("refused"))
            refuses(lambda: L._fsync_dir(root), "cannot fsync directory", "_fsync_dir fsync failing")
        finally:
            os.fsync = original_fsync

        # _promote with a destination that appeared between check and rename.
        staging = root / "staging-probe"
        staging.mkdir()
        destination = root / "destination-probe"
        destination.mkdir()
        refuses(lambda: L._promote(staging, destination),
                "refusing to overwrite an existing instance directory",
                "_promote onto an existing directory")
        check(staging.is_dir() and destination.is_dir(),
              "_promote modified either side of a refused promotion")
        # _promote onto a symlink destination.
        link = root / "link-destination"
        link.symlink_to(root / "absent-target")
        refuses(lambda: L._promote(staging, link), "refusing to overwrite a symlink target",
                "_promote onto a symlink")
        # _promote with rename raising.
        try:
            os.rename = lambda *a, **k: (_ for _ in ()).throw(OSError("refused"))
            refuses(lambda: L._promote(staging, root / "fresh-destination"), "cannot promote",
                    "_promote with rename refusing")
        finally:
            os.rename = original_rename


def test_builder_guard_refusals() -> None:
    """Every guard on every builder, tested directly on that builder.

    A builder guard is not redundant with the matching validator guard: the
    builder refuses a bad ARGUMENT before it can render a record, while the
    validator refuses a bad RECORD arriving from somewhere else.  Dropping either
    one is observable only through the entry point that owns it, so each is
    asserted on its own builder here.
    """
    # --- build_attempt_record -------------------------------------------------
    refuses(lambda: attempt_record_ok(feasible_count=-1),
            "feasible_count must be non-negative", "build_attempt_record negative count")
    refuses(lambda: attempt_record_ok(feasible_count=True),
            "feasible_count must be an int", "build_attempt_record bool count")
    check(attempt_record_ok(feasible_count=0),
          "build_attempt_record refused a zero feasible count")

    # --- build_generation_record ---------------------------------------------
    for label, overrides, needle in (
        ("slot 0", {"slot": 0}, "slot must be in 1..5"),
        ("slot 6", {"slot": 6}, "slot must be in 1..5"),
        ("slot bool", {"slot": True}, "slot must be an int"),
        ("attempt 128", {"attempt": 128}, "attempt must be in 0..127"),
        ("attempt bool", {"attempt": True}, "attempt must be an int"),
        ("empty instance id", {"instance_id": ""}, "must be a non-empty string"),
        ("int instance id", {"instance_id": 7}, "must be a str"),
        ("short matrix hash", {"return_matrix_sha256": "zz"}, "exactly 64 characters"),
        ("bad matrix hash", {"return_matrix_sha256": "A" * 64}, "lowercase SHA-256"),
        ("bad record hash", {"implementation_record_content_sha256": None}, "must be a str"),
        ("short record hash", {"implementation_record_content_sha256": "abc"},
         "exactly 64 characters"),
        # The moment guards belong to this builder too, since it is the only
        # producer of the recorded encodings.
        ("short mu", {"mu_new": MU_NEW[:-1]}, "exactly 20 encoded values"),
        ("long mu", {"mu_new": MU_NEW + [MU_NEW[0]]}, "exactly 20 encoded values"),
        ("mu as str", {"mu_new": MU_NEW[0]}, "mu_new must be a list or tuple of encoded values"),
        ("mu as dict", {"mu_new": {"a": 1}}, "mu_new must be a list or tuple of encoded values"),
        ("mu non-canonical", {"mu_new": ["1.0"] + MU_NEW[1:]},
         "not canonical binary64 hex"),
        ("short sigma row", {"sigma_new": tuple(row[:-1] for row in SIGMA_NEW)},
         "exactly 20 encoded values"),
        ("short sigma", {"sigma_new": SIGMA_NEW[:-1]}, "exactly 20 rows"),
    ):
        refuses(lambda overrides=overrides: generation_record_ok(**overrides), needle,
                f"build_generation_record: {label}")
    check(generation_record_ok()["instance_id"] == INSTANCE_ID,
          "build_generation_record refused a valid request")

    # --- build_instance_index -------------------------------------------------
    for label, overrides, needle in (
        ("slot 0", {"slot": 0}, "slot must be in 1..5"),
        ("slot bool", {"slot": True}, "slot must be an int"),
        ("attempt 128", {"attempt": 128}, "attempt must be in 0..127"),
        ("attempt bool", {"attempt": False}, "attempt must be an int"),
        ("empty instance id", {"instance_id": ""}, "must be a non-empty string"),
        ("int instance id", {"instance_id": 7}, "must be a str"),
        ("short prepared hash", {"prepared_record_sha256": "zz"}, "exactly 64 characters"),
        ("bad prepared hash", {"prepared_record_sha256": "Z" * 64}, "lowercase SHA-256"),
        ("short manifest hash", {"generation_manifest_sha256": "zz"}, "exactly 64 characters"),
        ("short manifest content hash", {"generation_manifest_content_sha256": "zz"},
         "exactly 64 characters"),
        ("short record hash", {"implementation_record_content_sha256": "zz"},
         "exactly 64 characters"),
        ("unknown status", {"prepared_record_status": "prepared_real"}, "not an accepted"),
        ("non-synthetic claim", {"non_synthetic_supported": True}, "claims non-synthetic"),
        ("short ledger hash", {"attempt_record_sha256": "zz"}, "exactly 64 characters"),
        ("upper ledger content hash", {"attempt_record_content_sha256": "A" * 64},
         "lowercase SHA-256"),
        ("unknown disposition", {"attempt_disposition": "unknown"},
         "not one of the declared dispositions"),
        ("rejected disposition", {"attempt_disposition": L.DISPOSITION_REJECTED},
         "must claim the accepted disposition"),
        ("negative code count", {"rejection_code_count": -1}, "must be non-negative"),
        ("bool code count", {"rejection_code_count": False}, "must be an int"),
        ("negative history count", {"rejected_attempt_history_count": -2},
         "must be non-negative"),
        ("short mu digest", {"mu_new_sha256": "zz"}, "exactly 64 characters"),
        ("short sigma digest", {"sigma_new_sha256": "zz"}, "exactly 64 characters"),
    ):
        refuses(lambda overrides=overrides: index_ok(**overrides), needle,
                f"build_instance_index: {label}")
    check(index_ok()["slot_name"] == "stage2_01", "build_instance_index refused a valid request")


def test_validator_guard_refusals() -> None:
    """Guards in the validators that only a directly-constructed record reaches."""
    # validate_generation_record's n_assets / n_rows TYPE guards: a value that
    # fails the type test but would compare equal to the constant.
    for field, value, needle in (
        ("n_assets", True, "n_assets must be an int"),
        ("n_assets", 20.0, "n_assets must be an int"),
        ("n_rows", True, "n_rows must be an int"),
        ("n_rows", 249.0, "n_rows must be an int"),
    ):
        record = generation_record_ok()
        record[field] = value
        record.pop("content_sha256")
        record["content_sha256"] = L._content_sha256(record)
        refuses(lambda record=record: L.validate_generation_record(record), needle,
                f"validate_generation_record {field}={value!r}")
    # An int-valued n_assets that is simply wrong.
    record = generation_record_ok()
    record["n_assets"] = 21
    record.pop("content_sha256")
    record["content_sha256"] = L._content_sha256(record)
    refuses(lambda: L.validate_generation_record(record), "must be the fixed 20",
            "validate_generation_record n_assets=21")

    # validate_instance_index's nested-object guards: a non-dict in each nested
    # slot.  A LIST is the input that reaches the type guard, because
    # ``set(["path"])`` would otherwise fail on the key-set check with a
    # different message, and a bare STRING never reaches it at all.
    base = index_ok()
    for label, field, value, needle in (
        ("prepared_record as a list", "prepared_record", ["path"],
         "prepared_record must be an object"),
        ("prepared_record as a string", "prepared_record", "not-an-object",
         "prepared_record must be an object"),
        ("generation as a list", "generation", ["path"], "generation must be an object"),
        ("generation as None", "generation", None, "generation must be an object"),
    ):
        record = json.loads(json.dumps(base))
        record[field] = value
        record.pop("content_sha256")
        record["content_sha256"] = L._content_sha256(record)
        refuses(lambda record=record: L.validate_instance_index(record), needle,
                f"validate_instance_index {label}")
    # The top-level object guard, and a dict SUBCLASS which is not an exact dict.
    refuses(lambda: L.validate_instance_index(["schema", "slot"]),
            "instance index must be an object", "validate_instance_index as a list")
    refuses(lambda: L.validate_instance_index(DictSubclass(base)),
            "instance index must be an object", "validate_instance_index as a dict subclass")
    # validate_attempt_record's nested-object guards with non-dict inputs.
    attempts = attempt_record_ok()
    for value, needle in ((["returns", "sectors"], "seed_commitments must be an object"),
                          ("not-an-object", "seed_commitments must be an object"),
                          (None, "seed_commitments must be an object")):
        record = json.loads(json.dumps(attempts))
        record["seed_commitments"] = value
        record.pop("content_sha256")
        record["content_sha256"] = L._content_sha256(record)
        refuses(lambda record=record: L.validate_attempt_record(record), needle,
                f"validate_attempt_record commitments={type(value).__name__}")
    record = json.loads(json.dumps(attempts))
    record["seed_commitments"]["returns"] = ["material_ascii"]
    record.pop("content_sha256")
    record["content_sha256"] = L._content_sha256(record)
    refuses(lambda: L.validate_attempt_record(record),
            "seed commitment returns must be an object",
            "validate_attempt_record commitment entry as a list")


def test_read_error_branches() -> None:
    """The OSError branches of the read path, driven by patched os functions."""
    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-readerr-") as tmp:
        root = Path(tmp)
        member = root / "file.bin"
        member.write_bytes(b"payload")
        holder = root / "holder"
        holder.mkdir()

        def boom(*args, **kwargs):
            raise OSError("refused")

        original_read = Path.read_bytes
        original_open = Path.open
        original_listdir = os.listdir
        try:
            # _real_file: read_bytes raising OSError.
            Path.read_bytes = boom
            refuses(lambda: L._real_file(member, "f"), "cannot read f", "_real_file read failing")
            Path.read_bytes = original_read
            # _sha_file: open raising OSError.
            Path.open = boom
            refuses(lambda: L._sha_file(member, "f"), "cannot read f", "_sha_file open failing")
            Path.open = original_open
            # _list_names: listdir raising OSError.
            os.listdir = boom
            refuses(lambda: L._list_names(holder, "d"), "cannot list d",
                    "_list_names listdir failing")
            os.listdir = original_listdir
            # verify_all_slots: listdir on the instance root raising OSError.
            instance_root = root / "research" / "g9" / "stage2_instances"
            instance_root.mkdir(parents=True)
            os.listdir = boom
            refuses(lambda: L.verify_all_slots(root=root), "cannot list the instance root",
                    "verify_all_slots listdir failing")
        finally:
            Path.read_bytes = original_read
            Path.open = original_open
            os.listdir = original_listdir
        # The controls still work after the patches are restored.
        check(L._real_file(member, "f") == b"payload", "_real_file broke after patching")
        check(L._sha_file(member, "f") == hashlib.sha256(b"payload").hexdigest(),
              "_sha_file broke after patching")
        check(L._list_names(holder, "d") == [], "_list_names broke after patching")
        check(L.verify_all_slots(root=root)["count"] == 0,
              "verify_all_slots broke after patching")
        # _require_real_dir must be reachable and refuse an absent instance root.
        refuses(lambda: L.verify_all_slots(root=root / "absent"),
                "instance root is not a directory",
                "verify_all_slots with an absent instance root")


def test_matrix_length_and_meta_record_checks() -> None:
    """The generation's matrix-length check and the meta/generation record bind."""
    def fresh() -> tuple[Path, Path]:
        tmp = tempfile.mkdtemp(dir=SCRATCH, prefix="wp8d-matrixlen-")
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
        write_one(root)
        return root, root / "research/g9/stage2_instances/stage2_01"

    # A return matrix of the wrong length, with BOTH the manifest and the
    # generation record resealed to commit to the shorter file.  WP5's size check
    # and the generation record's hash then both agree, so the layout's own fixed
    # length is the only remaining guard.
    for label, payload, needle in (
        ("short", MATRIX[:-8], f"return matrix is not {L.RETURN_MATRIX_BYTES} bytes"),
        ("long", MATRIX + b"\x00" * 8, f"return matrix is not {L.RETURN_MATRIX_BYTES} bytes"),
    ):
        root, base = fresh()
        matrix = base / "generation" / L.RETURN_MATRIX_NAME
        matrix.write_bytes(payload)
        generation_path = base / "generation" / L.GENERATION_NAME
        record = json.loads(generation_path.read_text("ascii"))
        record["return_matrix_sha256"] = hashlib.sha256(payload).hexdigest()
        record.pop("content_sha256")
        record["content_sha256"] = L._content_sha256(record)
        generation_path.write_bytes(canonical(record))
        reseal_manifest(root, base, L.GENERATION_DIR_NAME, L.GENERATION_NAME, repoint_index=True)
        refuses(lambda: L.verify_instance(SLOT, root=root), needle,
                f"a resealed {label} return matrix")

    # The meta sidecar bound to a DIFFERENT implementation record than the
    # generation.  This reaches the meta-vs-generation comparison, which the
    # prepared-sidecar comparison does not.
    root, base = fresh()
    meta_manifest = L._writer.build_manifest(
        {L.INDEX_NAME: (base / L.META_DIR_NAME / L.INDEX_NAME).read_bytes()},
        implementation_record_content_sha256=OTHER_RECORD)
    (base / L.META_DIR_NAME / L.MANIFEST_NAME).write_bytes(canonical(meta_manifest))
    refuses(lambda: L.verify_instance(SLOT, root=root),
            "the meta sidecar and the generation name different implementation records",
            "meta sidecar bound to a different implementation record")


def test_index_agreement_checks() -> None:
    """The index-to-generation agreement checks that need a resealed meta manifest."""
    def fresh() -> tuple[Path, Path]:
        tmp = tempfile.mkdtemp(dir=SCRATCH, prefix="wp8d-agree-")
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
        write_one(root)
        return root, root / "research/g9/stage2_instances/stage2_01"

    def edit_and_reseal(root: Path, base: Path, edit) -> None:
        path = base / L.META_DIR_NAME / L.INDEX_NAME
        record = json.loads(path.read_text("ascii"))
        edit(record)
        record.pop("content_sha256")
        record["content_sha256"] = L._content_sha256(record)
        path.write_bytes(canonical(record))
        reseal_manifest(root, base, L.META_DIR_NAME, L.INDEX_NAME)

    # The index's own ``attempt`` and its nested ``attempt_ledger.attempt`` are
    # cross-bound INSIDE the index, so an edit that moves only one of them is
    # refused by the index validator before any cross-record check runs.  Both
    # moves together are what reaches the cross-record comparison against the
    # ledger file, which is the binding that stops a re-sealed index from
    # misreporting which attempt was accepted.
    root, base = fresh()

    def move_both_attempts(record) -> None:
        record["attempt"] = 9
        record["attempt_ledger"]["attempt"] = 9

    edit_and_reseal(root, base, move_both_attempts)
    refuses(lambda: L.verify_instance(SLOT, root=root),
            "attempt_ledger attempt disagrees with the accepted attempt",
            "index attempt disagreeing with the generation")
    # And the internal disagreement is refused too, by a different check.
    root, base = fresh()
    edit_and_reseal(root, base, lambda m: m.update(attempt=9))
    refuses(lambda: L.verify_instance(SLOT, root=root),
            "attempt_ledger attempt disagrees with the index attempt",
            "index ledger attempt disagreeing with the index")
    # The retained-history COUNT is bound from outside the ledger file, so a
    # re-sealed index that understates how many attempts were rejected is
    # refused against the ledger itself.
    root, base = fresh()
    edit_and_reseal(root, base, lambda m: m["attempt_ledger"].update(
        rejected_attempt_history_count=0))
    refuses(lambda: L.verify_instance(SLOT, root=root),
            "attempt_ledger history count disagrees with the ledger",
            "index understating the retained rejected-attempt history")
    # So is each recorded moment digest.
    root, base = fresh()
    edit_and_reseal(root, base, lambda m: m["moments"].update(mu_new_sha256=fake("other-mu")))
    refuses(lambda: L.verify_instance(SLOT, root=root),
            "instance index does not name this generation's mu_new digest",
            "index naming a different mu_new digest")

    # The prepared FILE claiming a status the layout refuses.  WP5b's reviewed
    # validator is re-run on the read side and refuses it first.
    root, base = fresh()
    path = base / "instance" / "PREPARED.json"
    record = json.loads(path.read_text("ascii"))
    record["status"] = "prepared_real"
    body = dict(record)
    body.pop("content_sha256", None)
    record["content_sha256"] = L._content_sha256(body)
    path.write_bytes(canonical(record))
    reseal_manifest(root, base, L.PREPARED_DIR_NAME, "PREPARED.json")
    refuses(lambda: L.verify_instance(SLOT, root=root), "WP5b provenance validator",
            "prepared file claiming a status the index does not")

    # The genuinely reachable index/file status disagreement, which a prior
    # revision of this fixture argued was unreachable because both sides are
    # drawn from a one-element accepted set.  It is reachable precisely because
    # the INDEX can be tampered with and re-sealed: an index whose nested
    # prepared_record.status is an accepted-status-shaped string that the file
    # does not carry, with every hash recomputed, must be refused by the
    # cross-binding rather than by either side's own membership check.  The
    # index's own validator accepts the record because the value it checks is
    # still in ACCEPTED_STATUSES; only comparing it to the FILE catches this.
    root, base = fresh()
    def retag(record: dict) -> None:
        record["prepared_record"]["status"] = L.ACCEPTED_STATUSES[0] + "-TAMPERED"
        record["status"] = record["prepared_record"]["status"]
    # Retagging to a value outside the accepted set is refused by the index's own
    # validator -- assert that too, so both halves of the boundary are covered.
    edit_and_reseal(root, base, retag)
    refuses(lambda: L.verify_instance(SLOT, root=root), "not an accepted prepared-record status",
            "index carrying a status outside the accepted set")


def test_write_instance_unique_guards() -> None:
    """The guards that belong ONLY to write_instance's prepared-record handling.

    The scalar argument guards are shared with build_generation_payload and are
    tested there; what is unique here is the prepared record, which no builder
    accepts.  It is validated through WP5b's own reviewed validator BEFORE any
    byte is written, and its own identity must match the instance being written.

    This body was previously a nested ``def`` that nothing called, so every
    assertion in it -- and the ``_require(type(prepared_record) is dict, ...)``
    site it exercises -- never ran.  That is why the mutation sweep reported a
    SURVIVED site at that line and why the notes' check count did not match the
    fixture's real count.  It is a real test, so it is called.
    """
    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-writeuniq-") as tmp:
        root = Path(tmp)
        instance_root = root / "research" / "g9" / "stage2_instances"
        instance_root.mkdir(parents=True)

        def attempt(prepared: object) -> None:
            L.write_instance(slot=SLOT, attempt=ACCEPTED_ATTEMPT, instance_id=INSTANCE_ID,
                            sector_partition_sha256=PARTITION, feasible_count=1,
                            return_matrix=MATRIX, prepared_record=prepared,
                            implementation_record_content_sha256=RECORD,
                            mu_new=list(MU_NEW), sigma_new=[list(row) for row in SIGMA_NEW],
                            rejected_attempt_history=list(HISTORY), root=root)

        # A prepared record that is not an exact dict, including a dict subclass:
        # _canonical would raise a raw TypeError/accept a subclass otherwise.
        for value, needle in (([], "must be an object"),
                              ("string", "must be an object"),
                              (None, "must be an object"),
                              (DictSubclass(prepared()), "must be an object")):
            refuses(lambda value=value: attempt(value), needle,
                    f"write_instance prepared_record={type(value).__name__}")
        # An empty dict is a dict, so only the truth guard can refuse it.
        refuses(lambda: attempt({}), "non-empty object", "write_instance with an empty prepared record")
        # A prepared record with an unknown status, refused inside WP5b's validator.
        refuses(lambda: attempt(prepared(status="prepared_real")), "WP5b provenance validator",
                "write_instance with an unknown prepared status")
        # A prepared record claiming non-synthetic support, likewise.
        refuses(lambda: attempt(prepared(supported=True)), "WP5b provenance validator",
                "write_instance with a non-synthetic prepared record")
        # Not a bool, and not False: refused by WP5b's identity guard.
        refuses(lambda: attempt(dict(prepared(), non_synthetic_supported=0)),
                "WP5b provenance validator",
                "write_instance with non_synthetic_supported=0")
        # A prepared record naming a DIFFERENT instance than the one being
        # written.  WP5b accepts it -- the record is internally consistent -- so
        # this is refused only by the layout's own identity cross-binding.
        refuses(lambda: attempt(prepared(instance_id="SOME-OTHER-INSTANCE")),
                "instance_id disagrees with the instance being written",
                "write_instance with a mismatched prepared record identity")
        # A prepared record whose instance block is missing or malformed, so no
        # identity can be read for the cross-binding at all.
        for value, needle in (({}, "provenance record has wrong key set"),
                              ({"instance": "not an object"}, "prepared record instance must be an object")):
            body = prepared()
            if not value:
                body.pop("instance")
            else:
                body["instance"] = value["instance"]
            body.pop("content_sha256")
            body["content_sha256"] = L._content_sha256(body)
            refuses(lambda body=body: attempt(body), needle,
                    f"write_instance prepared instance block {value}")
        # None was written by any refusal above.
        check(sorted(os.listdir(instance_root)) == [],
              f"a refused write left files behind: {sorted(os.listdir(instance_root))}")
        # The control write still succeeds through the same path.
        check(L.write_instance(slot=SLOT, attempt=ACCEPTED_ATTEMPT, instance_id=INSTANCE_ID,
                               sector_partition_sha256=PARTITION, feasible_count=1,
                               return_matrix=MATRIX, prepared_record=prepared(),
                               implementation_record_content_sha256=RECORD,
                               mu_new=list(MU_NEW), sigma_new=[list(r) for r in SIGMA_NEW],
                               rejected_attempt_history=list(HISTORY),
                               root=root)["verdict"] == "written",
              "write_instance refused a valid request")



def test_validator_tamper_probe_deep() -> None:
    """A deep forgery: rewrite the ledger, re-seal its hash AND the manifest.

    Before schema v3 the index bound only the generation manifest, so re-sealing
    the manifest alongside a tampered ``ATTEMPT.json`` was enough to make an
    edited ledger verify.  Schema v3 adds ``attempt_ledger``, which names the
    ledger's exact BYTES, so the same forgery is now caught by a binding that
    does not depend on the manifest at all -- which is strictly stronger, since
    the manifest is inside the attacker's reach.

    The generation directory alone still verifies: that is correct, because the
    rewrite is self-consistent.  What must not verify is the whole instance.
    """
    def fresh() -> tuple[L.Path, L.Path]:
        tmp = tempfile.mkdtemp(dir=SCRATCH, prefix="wp8d-tamper-")
        root = L.Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
        write_one(root)
        return root, root / "research/g9/stage2_instances/stage2_01"

    root, base = fresh()
    attempt_path = base / "generation" / L.ATTEMPT_NAME
    body = json.loads(attempt_path.read_text("ascii"))
    body["feasible_count"] = 99999
    body.pop("content_sha256")
    body["content_sha256"] = L._content_sha256(body)
    attempt_path.write_bytes(canonical(body))
    reseal_manifest(root, base, L.GENERATION_DIR_NAME, L.ATTEMPT_NAME)

    # The generation directory validates on its own: the rewrite is internally
    # consistent and the manifest was re-sealed to match it.
    summary = L.validate_generation_directory(base / L.GENERATION_DIR_NAME)
    check(summary["verdict"] == "verified", "Generation directory alone should verify")

    # The whole instance must still be refused, on the ledger-bytes binding.
    refuses(lambda: L.verify_instance(SLOT, root=root),
            "instance index does not name this retained-attempt ledger's bytes",
            "deep tamper probe: modified attempt record, resealed manifest")

    # And the SAME forgery that also rewrites the index's ledger hash is caught
    # by the next binding in the chain rather than slipping through.
    root, base = fresh()
    attempt_path = base / "generation" / L.ATTEMPT_NAME
    body = json.loads(attempt_path.read_text("ascii"))
    body["feasible_count"] = 99999
    body.pop("content_sha256")
    body["content_sha256"] = L._content_sha256(body)
    attempt_path.write_bytes(canonical(body))
    reseal_manifest(root, base, L.GENERATION_DIR_NAME, L.ATTEMPT_NAME)
    index_path = base / L.META_DIR_NAME / L.INDEX_NAME
    index_body = json.loads(index_path.read_text("ascii"))
    index_body["attempt_ledger"]["sha256"] = hashlib.sha256(
        attempt_path.read_bytes()).hexdigest()
    index_body["attempt_ledger"]["content_sha256"] = body["content_sha256"]
    index_body.pop("content_sha256")
    index_body["content_sha256"] = L._content_sha256(index_body)
    index_path.write_bytes(canonical(index_body))
    reseal_manifest(root, base, L.META_DIR_NAME, L.INDEX_NAME)
    # The index now agrees with the rewritten ledger, so the refusal moves on to
    # the generated manifest, which the attacker's re-seal changed and the index
    # still names by its ORIGINAL bytes.
    refuses(lambda: L.verify_instance(SLOT, root=root),
            "instance index does not name this generation's manifest bytes",
            "deep tamper probe: fully re-sealed forgery")


# ---------------------------------------------------------------------------
# Durability: the post-promotion fsync pair is OBSERVABLE here
# ---------------------------------------------------------------------------
def test_fsync_durability_observable() -> None:
    """The two post-promotion ``_fsync_dir`` calls are asserted, not excused.

    A prior revision declared these two sites EQUIVALENT-ACCEPTED on the grounds
    that "no fixture can observe the difference between a synced and an unsynced
    directory without crashing the machine".  That is true of the SYNC and false
    of the CALL, the ORDER and the FAILURE PATH -- all three are observable by
    replacing ``_fsync_dir`` with a recorder, which is exactly what this test
    does.  Durability is not weakened or removed to make the sweep pass; it is
    measured instead.
    """
    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-fsync-") as tmp:
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)

        # (a) the CALLS: both fire, exactly once each, in the order WP5 uses --
        # the destination first, then its parent.
        calls: list[str] = []
        original = L._fsync_dir

        def record(path):
            calls.append(L.Path(path).name)
            return original(path)

        L._fsync_dir = record
        try:
            write_one(root)
        finally:
            L._fsync_dir = original
        check(calls == ["stage2_01", "stage2_instances"],
              f"the post-promotion fsync calls/order are {calls}, expected the "
              f"destination then its parent")

        # (b) the FAILURE PATH, and the rollback it must trigger.  A failure at
        # either call refuses the write, and the promoted directory must be gone
        # so the slot can be retried -- this is the invariant the notes claimed
        # and the code did not honour.
        for failing_name, where in (("stage2_01", "destination"), ("stage2_instances", "parent")):
            attempt_root = Path(tempfile.mkdtemp(dir=SCRATCH, prefix="wp8d-fsyncfail-"))
            (attempt_root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
            destination = attempt_root / "research/g9/stage2_instances/stage2_01"

            def failing(path, _name=failing_name):
                if L.Path(path).name == _name:
                    raise L.LayoutError("INJECTED-FSYNC-FAILURE")
                return original(path)

            L._fsync_dir = failing
            try:
                refuses(lambda r=attempt_root: write_one(r), "INJECTED-FSYNC-FAILURE",
                        f"a write whose {where} fsync fails")
            finally:
                L._fsync_dir = original
            check(not destination.exists(),
                  f"a {where} fsync failure left the promoted directory behind, so the "
                  f"slot cannot be retried")
            check(sorted(os.listdir(attempt_root / "research/g9/stage2_instances")) == [],
                  f"a {where} fsync failure left the instance root changed")

        # (c) a retry after a rolled-back write really does succeed, which is the
        # point of the rollback: the slot is usable again.
        retry_root = Path(tempfile.mkdtemp(dir=SCRATCH, prefix="wp8d-fsyncretry-"))
        (retry_root / "research" / "g9" / "stage2_instances").mkdir(parents=True)

        def always_fail(path):
            raise L.LayoutError("INJECTED-FSYNC-FAILURE")

        L._fsync_dir = always_fail
        try:
            refuses(lambda: write_one(retry_root), "INJECTED-FSYNC-FAILURE",
                    "a write whose durability always fails")
        finally:
            L._fsync_dir = original
        check(write_one(retry_root)["verdict"] == "written",
              "a retry after a rolled-back durability failure was refused")


# ---------------------------------------------------------------------------
# Regression tests for the five reported unexpected accepts
# ---------------------------------------------------------------------------
def test_regression_adversarial_five() -> None:
    """One test per reported unexpected accept, each proven to fail without its fix.

    These are the inputs an independent validator built, reproduced exactly.  On
    the unrepaired module every one of them was ACCEPTED; here each must be a
    typed refusal.  The tamper proofs re-seal every hash the attacker controls, so
    a refusal cannot be credited to a stale digest.
    """
    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-regress-") as tmp:
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)

        # (1) A stage2_02 directory whose records all say slot 1.  The caller
        # asked for slot 2; every file inside is self-consistent about slot 1.
        # A verifier that only cross-checks the records returns a valid slot-1
        # answer to a slot-2 question.
        instance_root = root / "research" / "g9" / "stage2_instances"
        write_one(root)
        (instance_root / "stage2_01").rename(instance_root / "stage2_02")
        refuses(lambda: L.verify_instance(2, root=root),
                "different slot than the instance directory",
                "REGRESSION 1: a slot-2 path holding slot-1 records")

    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-regress2-") as tmp:
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
        # (2) A PREPARED.json the FROZEN WP5b validator refuses, on both the
        # write side and the read side.  A three-key record with the right
        # status and the right non-synthetic flag, and nothing else.
        malformed = {"status": L.PREPARED_STATUS, "non_synthetic_supported": False,
                     "note": "INVALID-WP5B-PROVENANCE"}
        # The precondition is asserted with WP5b's own exception type: the
        # frozen reviewed validator, not this layout, is what refuses it.  It is
        # recorded as a real check, so the report cannot claim the regression
        # tests pass without also proving the frozen validator disagrees.
        before = COUNT
        try:
            P.validate_provenance_record(malformed)
        except P.InstancePreparationError:
            check(COUNT == before, "the frozen WP5b validator refuses the malformed record")
        else:
            FAILURES.append("PRECONDITION 2: the frozen WP5b validator accepted this record")
        refuses(lambda: L._validated_provenance(malformed), "WP5b provenance validator",
                "REGRESSION 2a: the layout refuses a WP5b-invalid record")
        refuses(lambda: L.write_instance(
            slot=SLOT, attempt=ACCEPTED_ATTEMPT, instance_id=INSTANCE_ID,
            sector_partition_sha256=PARTITION, feasible_count=1, return_matrix=MATRIX,
            prepared_record=malformed, implementation_record_content_sha256=RECORD,
            mu_new=list(MU_NEW), sigma_new=[list(r) for r in SIGMA_NEW],
            rejected_attempt_history=list(HISTORY),
            root=root), "WP5b provenance validator",
            "REGRESSION 2b: write_instance refuses a WP5b-invalid record")
        check(sorted(os.listdir(root / "research/g9/stage2_instances")) == [],
              "REGRESSION 2c: a WP5b-invalid record wrote something")
        # Read side: write a VALID instance, then replace the prepared record with
        # the malformed one and re-seal the sidecar manifest and the index, so
        # only the real WP5b validator can refuse it.
        instance_root = root / "research/g9/stage2_instances"
        write_one(root)
        base = instance_root / "stage2_01"
        (base / L.PREPARED_DIR_NAME / "PREPARED.json").write_bytes(canonical(malformed))
        reseal_manifest(root, base, L.PREPARED_DIR_NAME, "PREPARED.json",
                        repoint_index=True)
        refuses(lambda: L.verify_instance(SLOT, root=root), "WP5b provenance validator",
                "REGRESSION 2d: verify_instance refuses a WP5b-invalid record on disk")

    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-regress3-") as tmp:
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
        # (3) A prepared record naming a DIFFERENT, structurally valid instance.
        # WP5b accepts it -- the record is internally consistent -- so only an
        # explicit cross-binding refuses it.
        other = prepared(instance_id="OTHER-VALIDATOR-SYNTHETIC-ID")
        refuses(lambda: L.write_instance(
            slot=SLOT, attempt=ACCEPTED_ATTEMPT, instance_id=INSTANCE_ID,
            sector_partition_sha256=PARTITION, feasible_count=1, return_matrix=MATRIX,
            prepared_record=other, implementation_record_content_sha256=RECORD,
            mu_new=list(MU_NEW), sigma_new=[list(r) for r in SIGMA_NEW],
            rejected_attempt_history=list(HISTORY),
            root=root), "instance_id disagrees with the instance being written",
            "REGRESSION 3a: writing a mismatched prepared identity is refused")

    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-regress3b-") as tmp:
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
        # (3b) The read side of the same disagreement: a directory whose prepared
        # record and generation record name different instances, with every hash
        # the attacker controls re-sealed.
        instance_root = root / "research/g9/stage2_instances"
        write_one(root)
        base = instance_root / "stage2_01"
        prepared_path = base / L.PREPARED_DIR_NAME / "PREPARED.json"
        body = json.loads(prepared_path.read_text("ascii"))
        body["instance"]["instance_id"] = "A-DIFFERENT-SYNTHETIC-IDENTITY"
        body.pop("content_sha256")
        body["content_sha256"] = L._content_sha256(body)
        prepared_path.write_bytes(canonical(body))
        reseal_manifest(root, base, L.PREPARED_DIR_NAME, "PREPARED.json",
                        repoint_index=True)
        refuses(lambda: L.verify_instance(SLOT, root=root),
                "names a different instance than the generation",
                "REGRESSION 3b: verify_instance refuses a mismatched prepared identity")

    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-regress4-") as tmp:
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
        # (4) The nested index prepared_record.status changed to an unknown value
        # and EVERY hash re-sealed: the index's own content hash, its WP5
        # manifest, and the generation/prepared bindings it carries.  Nothing on
        # disk is inconsistent -- the forgery is a valid, well-sealed index that
        # misreports the prepared record it names.
        #
        # ONLY the nested field is touched.  That is the finding, not a detail:
        # the index's own validator checks the TOP-LEVEL ``status`` and never the
        # nested one, and no comparison tied the nested value to the prepared
        # FILE.  Retagging the top-level field as well would be refused by the
        # unrepaired module too, and would therefore prove nothing.
        instance_root = root / "research/g9/stage2_instances"
        write_one(root)
        base = instance_root / "stage2_01"
        index_path = base / L.META_DIR_NAME / L.INDEX_NAME
        index = json.loads(index_path.read_text("ascii"))
        index["prepared_record"]["status"] = "UNKNOWN-VALIDATOR-STATUS"
        index.pop("content_sha256")
        index["content_sha256"] = L._content_sha256(index)
        index_path.write_bytes(canonical(index))
        reseal_manifest(root, base, L.META_DIR_NAME, L.INDEX_NAME)
        # The refusal is the CROSS-BINDING, not the index's own membership check:
        # the index's top-level status is still an accepted string, so
        # ``validate_instance_index`` accepts the record, and the nested field is
        # caught only by comparing it to the prepared FILE.  That ordering is the
        # point -- a membership check alone would say nothing about which status
        # the record actually has.
        refuses(lambda: L.verify_instance(SLOT, root=root),
                "prepared_record status disagrees with the prepared record",
                "REGRESSION 4a: a re-sealed index with an unknown nested status")

    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-regress4c-") as tmp:
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
        # (4c) The nested non_synthetic flag, cross-bound the same way.  Setting
        # it to True is refused by the index's own identity guard, so what is
        # asserted here is that the guard fires -- the file still says False, and
        # only the cross-binding would notice if the file said otherwise.
        write_one(root)
        base = root / "research/g9/stage2_instances/stage2_01"
        index_path = base / L.META_DIR_NAME / L.INDEX_NAME
        index = json.loads(index_path.read_text("ascii"))
        index["prepared_record"]["non_synthetic_supported"] = True
        index.pop("content_sha256")
        index["content_sha256"] = L._content_sha256(index)
        index_path.write_bytes(canonical(index))
        reseal_manifest(root, base, L.META_DIR_NAME, L.INDEX_NAME)
        refuses(lambda: L.verify_instance(SLOT, root=root),
                "claims non-synthetic support",
                "REGRESSION 4c: a re-sealed index claiming non-synthetic support")

    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-regress5-") as tmp:
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
        # (5) The index/FILE cross-bindings, one at a time, each with EVERY hash
        # the attacker controls resealed.  Each of these is a comparison between
        # two genuinely different objects, so each is separately observable, and
        # dropping any one of them lets a well-sealed index misreport the prepared
        # record it names.
        def forged(mutate, needle, label):
            fresh = Path(tempfile.mkdtemp(dir=SCRATCH, prefix="wp8d-forge-"))
            (fresh / "research" / "g9" / "stage2_instances").mkdir(parents=True)
            write_one(fresh)
            slot_base = fresh / "research/g9/stage2_instances/stage2_01"
            path = slot_base / L.META_DIR_NAME / L.INDEX_NAME
            body = json.loads(path.read_text("ascii"))
            mutate(body)
            body.pop("content_sha256")
            body["content_sha256"] = L._content_sha256(body)
            path.write_bytes(canonical(body))
            reseal_manifest(fresh, slot_base, L.META_DIR_NAME, L.INDEX_NAME)
            refuses(lambda: L.verify_instance(SLOT, root=fresh), needle, label)

        # The index's prepared-manifest bindings, pointing at a manifest the
        # prepared sidecar does not actually have.  Both fields are separate
        # boundaries: the file-bytes hash and the manifest's own content hash.
        forged(lambda m: m["prepared_record"].update(manifest_sha256=fake("other-manifest")),
               "does not name this prepared manifest's bytes",
               "REGRESSION 5a: index naming different prepared-manifest bytes")
        forged(lambda m: m["prepared_record"].update(
                   manifest_content_sha256=fake("other-manifest-content")),
               "does not name this prepared manifest's content hash",
               "REGRESSION 5b: index naming a different prepared-manifest content hash")
        # The index's TOP-LEVEL status is a different boundary from the nested
        # one, and it is enforced by the index's OWN membership guard rather than
        # by a cross-binding: both the index's status and the file's status are
        # forced to the single accepted string, so a comparison between them would
        # have no falsifiable input (see the note in verify_instance).  What IS
        # observable is that the index's own guard refuses a value outside the
        # accepted set, and that the NESTED field -- which that guard never looks
        # at -- is caught by the cross-binding instead.  Both are asserted.
        forged(lambda m: m.update(status=L.ACCEPTED_STATUSES[0] + "-X"),
               "not an accepted prepared-record status",
               "REGRESSION 5d: index top-level status outside the accepted set")
        forged(lambda m: m["prepared_record"].update(
                   status=L.ACCEPTED_STATUSES[0] + "-X"),
               "prepared_record status disagrees with the prepared record",
               "REGRESSION 5e: index NESTED status outside the accepted set, caught "
               "by the cross-binding and not by the index's own guard")

    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-regress6-") as tmp:
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
        # (6) A post-promotion durability failure.  The refusal must be typed AND
        # the promoted slot must be gone, so the documented "a refused write
        # leaves the instance root unchanged" is true at the LAST possible moment
        # a write can fail -- after the rename has already returned.
        original = L._fsync_dir

        def failing(path):
            raise L.LayoutError("INJECTED-FSYNC-FAILURE")

        L._fsync_dir = failing
        try:
            refuses(lambda: write_one(root), "INJECTED-FSYNC-FAILURE",
                    "REGRESSION 6: a post-promotion durability failure refuses")
        finally:
            L._fsync_dir = original
        check(not (root / "research/g9/stage2_instances/stage2_01").exists(),
              "REGRESSION 6: a refused durability failure left the promoted slot behind")
        check(sorted(os.listdir(root / "research/g9/stage2_instances")) == [],
              "REGRESSION 6: a refused durability failure changed the instance root")
        check(write_one(root)["verdict"] == "written",
              "REGRESSION 6: the slot is not retryable after a rolled-back write")

    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-regress7-") as tmp:
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
        # (7) The last-resort path: durability fails AND the rollback rename fails
        # too.  That is the only state in which the promoted directory is still on
        # disk, so it must be reported as ITS OWN distinct error -- one that names
        # the directory and says a human must inspect it -- rather than being
        # swallowed or re-raised as the plain durability error, which would tell a
        # caller the rollback succeeded when it did not.
        original_fsync = L._fsync_dir
        original_rename = os.rename
        promote_seen = {"count": 0}

        def failing_fsync(path):
            raise L.LayoutError("INJECTED-FSYNC-FAILURE")

        staging_name = f"{L.STAGING_PREFIX}{os.getpid()}-{L.slot_name(SLOT)}"
        promoted = str(root / "research" / "g9" / "stage2_instances" / L.slot_name(SLOT))

        def failing_rename(src, dst):
            # Fail ONLY the rollback rename: the one that moves the PROMOTED
            # instance directory back to its staging name.  Matching on the exact
            # source and destination paths (not on a substring) matters, because
            # WP5 promotes each subdirectory with its own staging rename that also
            # mentions the slot name, and a looser match fails those instead and
            # the write never reaches the durability step at all.
            if str(src) == promoted and str(dst).endswith(staging_name):
                promote_seen["count"] += 1
                raise OSError("INJECTED-ROLLBACK-FAILURE")
            return original_rename(src, dst)

        L._fsync_dir = failing_fsync
        os.rename = failing_rename
        try:
            refuses(lambda: write_one(root), "rollback to staging also failed",
                    "REGRESSION 7: a failed rollback is reported as its own error")
        finally:
            L._fsync_dir = original_fsync
            os.rename = original_rename
        check(promote_seen["count"] > 0,
              "REGRESSION 7: the rollback rename was never attempted")
        # The promoted directory is present in this one case, and the error says so.
        check((root / "research/g9/stage2_instances/stage2_01").exists(),
              "REGRESSION 7: a failed rollback should leave the directory for inspection")
        # The staging name must NOT also be left behind: the rename out of staging
        # succeeded, so the staging path is gone and only the destination remains.
        leftovers = [p.name for p in (root / "research/g9/stage2_instances").iterdir()
                     if p.name.startswith(L.STAGING_PREFIX)]
        check(leftovers == [], f"REGRESSION 7: a failed rollback left staging behind: {leftovers}")

    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-regress8-") as tmp:
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
        # (8) The index's nested non_synthetic flag.  It is NOT cross-bound to the
        #     file, and the reason is recorded in verify_instance: the index's own
        #     identity guard forces the value to the single object False, and WP5b
        #     forces the file's value to False, so a comparison between them would
        #     have no falsifiable input.  What IS observable is that the index's
        #     own guard refuses every non-False value, so a re-sealed index cannot
        #     claim the unreviewed non-synthetic path.  Each value is asserted
        #     because each reaches the guard by a different route: True and 1 and
        #     "true" and "" all fail the ``is False`` identity test, and a dict
        #     does too, while None fails on identity as well.
        for value in (True, 1, "true", "", None, 0, [], {}):
            fresh = Path(tempfile.mkdtemp(dir=SCRATCH, prefix="wp8d-ns-"))
            (fresh / "research" / "g9" / "stage2_instances").mkdir(parents=True)
            write_one(fresh)
            slot_base = fresh / "research/g9/stage2_instances/stage2_01"
            path = slot_base / L.META_DIR_NAME / L.INDEX_NAME
            body = json.loads(path.read_text("ascii"))
            body["prepared_record"]["non_synthetic_supported"] = value
            body.pop("content_sha256")
            body["content_sha256"] = L._content_sha256(body)
            path.write_bytes(canonical(body))
            reseal_manifest(fresh, slot_base, L.META_DIR_NAME, L.INDEX_NAME)
            refuses(lambda r=fresh: L.verify_instance(SLOT, root=r), "claims non-synthetic",
                    f"REGRESSION 8: index nested non_synthetic_supported={value!r}")

    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-regress4b-") as tmp:
        root = Path(tmp)
        (root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
        # (4b) The non_synthetic flag, cross-bound the same way.  A non-False
        # value here is refused by the index's own identity guard, so the
        # observable case is the index claiming a value the FILE does not have --
        # proven by retagging the FILE to a non-synthetic claim, re-sealing, and
        # confirming the file itself is refused.
        instance_root = root / "research/g9/stage2_instances"
        write_one(root)
        base = instance_root / "stage2_01"
        prepared_path = base / L.PREPARED_DIR_NAME / "PREPARED.json"
        body = json.loads(prepared_path.read_text("ascii"))
        body["non_synthetic_supported"] = True
        body.pop("content_sha256")
        body["content_sha256"] = L._content_sha256(body)
        prepared_path.write_bytes(canonical(body))
        reseal_manifest(root, base, L.PREPARED_DIR_NAME, "PREPARED.json",
                        repoint_index=True)
        refuses(lambda: L.verify_instance(SLOT, root=root), "WP5b provenance validator",
                "REGRESSION 4b: a re-sealed prepared record claiming non-synthetic support")


def test_regression_manifest_bytes_and_typed_refusal() -> None:
    """Two further reported findings: unbound manifest bytes, and a KeyError leak.

    The index binds the generation and prepared manifests' bytes as of schema v2.
    The meta manifest's bytes cannot be bound in the index (it commits to the
    index), so the rule that closes it is byte-canonicality.  Both are asserted
    here, and both were ACCEPTED by the unrepaired module.
    """
    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="wp8d-mbytes-") as tmp:
        # One appended whitespace byte to each MANIFEST.json.  The generation and
        # prepared ones are refused by the index's byte binding; the meta one by
        # canonicality.  All three must refuse.  Each gets its own root so the
        # three forgeries do not interfere.
        for member in (L.GENERATION_DIR_NAME, L.PREPARED_DIR_NAME, L.META_DIR_NAME):
            fresh_root = Path(tempfile.mkdtemp(dir=SCRATCH, prefix="wp8d-mb2-"))
            (fresh_root / "research" / "g9" / "stage2_instances").mkdir(parents=True)
            write_one(fresh_root)
            fresh_base = fresh_root / "research/g9/stage2_instances/stage2_01"
            manifest = fresh_base / member / L.MANIFEST_NAME
            manifest.write_bytes(manifest.read_bytes() + b" ")
            refuses(lambda r=fresh_root: L.verify_instance(SLOT, root=r),
                    "canonical encoding",
                    f"REGRESSION A: one whitespace byte appended to {member}/MANIFEST.json")

        # A prepared record missing any WP5b-required field used to leak a
        # KeyError (or a raw TypeError) instead of raising this module's typed
        # LayoutError, because the record was read with direct subscripting.  Every
        # field is now covered, and ``refuses`` with an empty needle asserts the
        # EXCEPTION TYPE: a leaked KeyError or TypeError is a failure here.
        for missing in ("status", "non_synthetic_supported", "instance", "schema",
                        "results", "ledgers", "f_predicate", "f_predicate_sha256",
                        "source_sha256", "scientific_outputs", "content_sha256"):
            broken = prepared()
            broken.pop(missing, None)
            target = Path(tempfile.mkdtemp(dir=SCRATCH, prefix="wp8d-miss-"))
            (target / "research" / "g9" / "stage2_instances").mkdir(parents=True)
            refuses(lambda b=broken, t=target: L.write_instance(
                slot=SLOT, attempt=ACCEPTED_ATTEMPT, instance_id=INSTANCE_ID,
                sector_partition_sha256=PARTITION, feasible_count=1,
                return_matrix=MATRIX, prepared_record=b,
                implementation_record_content_sha256=RECORD,
                mu_new=list(MU_NEW), sigma_new=[list(r) for r in SIGMA_NEW],
                rejected_attempt_history=list(HISTORY), root=t), "",
                f"REGRESSION D: a prepared record missing {missing!r} is a typed refusal")
        for missing, needle in (("status", "WP5b provenance validator"),
                                ("non_synthetic_supported", "WP5b provenance validator")):
            broken = prepared()
            broken.pop(missing, None)
            target = Path(tempfile.mkdtemp(dir=SCRATCH, prefix="wp8d-miss2-"))
            (target / "research" / "g9" / "stage2_instances").mkdir(parents=True)
            refuses(lambda b=broken, t=target: L.write_instance(
                slot=SLOT, attempt=ACCEPTED_ATTEMPT, instance_id=INSTANCE_ID,
                sector_partition_sha256=PARTITION, feasible_count=1,
                return_matrix=MATRIX, prepared_record=b,
                implementation_record_content_sha256=RECORD,
                mu_new=list(MU_NEW), sigma_new=[list(r) for r in SIGMA_NEW],
                rejected_attempt_history=list(HISTORY), root=t), needle,
                f"REGRESSION D: a prepared record missing {missing!r} is a typed refusal")

        # The same on the READ side: a valid instance whose PREPARED.json is
        # replaced by a record missing 'status', fully resealed.  No KeyError.
        target = Path(tempfile.mkdtemp(dir=SCRATCH, prefix="wp8d-missread-"))
        (target / "research" / "g9" / "stage2_instances").mkdir(parents=True)
        write_one(target)
        base = target / "research/g9/stage2_instances/stage2_01"
        for missing in ("status", "non_synthetic_supported"):
            partial = prepared()
            partial.pop(missing, None)
            (base / L.PREPARED_DIR_NAME / "PREPARED.json").write_bytes(canonical(partial))
            reseal_manifest(target, base, L.PREPARED_DIR_NAME, "PREPARED.json",
                            repoint_index=True)
            refuses(lambda: L.verify_instance(SLOT, root=target),
                    "WP5b provenance validator",
                    f"REGRESSION D2: verify_instance on a prepared record missing {missing!r}")


def test_regression_new_guard_sites() -> None:
    """Every guard the repair added is directly exercised, or it is not a guard.

    The mutation sweep reported eight SURVIVED sites, all in code added by this
    repair.  Each is asserted here on purpose, because a surviving mutant means
    the site was untested, and an untested site is a test gap regardless of
    whether the guard happens to be redundant:

    * the two ``_sha`` guards on the prepared-manifest arguments in
      ``build_instance_index`` (schema v2 added these arguments);
    * the two matching ``_sha`` guards on the nested prepared-manifest fields in
      ``validate_instance_index``;
    * the ``_validated_provenance`` post-WP5b re-checks -- the exact-dict type
      test and the layout's own status / non-synthetic guards.  These are
      deliberate: WP5b already guarantees them, so no input can make them the
      FIRST refusal, and they are asserted through WP5b's own refusals instead;
    * the ``_non_empty_string`` on the prepared record's instance_id, asserted
      through a record whose instance block carries a non-string identity.
    """
    import copy

    good = dict(slot=SLOT, attempt=ACCEPTED_ATTEMPT, instance_id=INSTANCE_ID,
                prepared_record_sha256=fake("prepared"),
                prepared_record_status=L.PREPARED_STATUS,
                non_synthetic_supported=False,
                prepared_manifest_sha256=fake("pmb"),
                prepared_manifest_content_sha256=fake("pmc"),
                generation_manifest_sha256=fake("gmb"),
                generation_manifest_content_sha256=fake("gmc"),
                attempt_record_sha256=fake("lmb"),
                attempt_record_content_sha256=fake("lmc"),
                attempt_disposition=L.DISPOSITION_ACCEPTED,
                rejection_code_count=0, rejected_attempt_history_count=len(HISTORY),
                mu_new_sha256=MU_NEW_SHA, sigma_new_sha256=SIGMA_NEW_SHA,
                implementation_record_content_sha256=RECORD)
    record = L.build_instance_index(**good)

    # (1) The two new builder arguments are each a boundary, tested separately:
    #     dropping the length test still refuses "zz" via the character test, and
    #     dropping the type test still refuses a non-string.
    for field, value, needle in (("prepared_manifest_sha256", "zz",
                                  "must be exactly 64 characters"),
                                 ("prepared_manifest_sha256", 7, "must be a str"),
                                 ("prepared_manifest_sha256", "A" * 64,
                                  "must be a lowercase SHA-256"),
                                 ("prepared_manifest_content_sha256", "zz",
                                  "must be exactly 64 characters"),
                                 ("prepared_manifest_content_sha256", None,
                                  "must be a str"),
                                 ("prepared_manifest_content_sha256", "F" * 64,
                                  "must be a lowercase SHA-256")):
        kwargs = dict(good)
        kwargs[field] = value
        refuses(lambda kw=kwargs: L.build_instance_index(**kw), needle,
                f"index builder: {field}={value!r}")

    # (2) The two matching read-side guards, on a re-sealed index.
    for field, value, needle in (("manifest_sha256", "zz",
                                  "must be exactly 64 characters"),
                                 ("manifest_sha256", 7, "must be a str"),
                                 ("manifest_content_sha256", "",
                                  "must be exactly 64 characters"),
                                 ("manifest_content_sha256", None,
                                  "must be a str")):
        edited = copy.deepcopy(record)
        edited["prepared_record"][field] = value
        edited.pop("content_sha256")
        edited["content_sha256"] = L._content_sha256(edited)
        refuses(lambda e=edited: L.validate_instance_index(e), needle,
                f"validate_instance_index: prepared_record.{field}={value!r}")

    # (3) _validated_provenance's post-WP5b re-checks.  These three sites are
    #     unobservable through the normal path, because WP5b's validator has
    #     already refused every falsifying input before they run -- which is
    #     exactly why a mutation sweep reported them as survivors.
    #
    #     They are NOT removed.  They exist to keep the LAYOUT's invariants
    #     (ACCEPTED_STATUSES, the non-synthetic refusal) owned by the layout
    #     rather than inherited from WP5b, so that widening WP5b later cannot
    #     silently widen this package.  That is a real threat, and it is
    #     testable: substitute WP5b's validator with one that returns a record
    #     WP5b would never return, and require the layout to refuse it anyway.
    #     This asserts the boundary the guard actually defends, rather than
    #     pretending the guard is reachable from ordinary input.
    original_validator = P.validate_provenance_record

    def with_validator(fake, call, needle, label):
        L._preparation.validate_provenance_record = fake
        try:
            refuses(call, needle, label)
        finally:
            L._preparation.validate_provenance_record = original_validator

    # 632: WP5b returning something that is not a dict.
    with_validator(lambda rec: ["not", "a", "dict"],
                   lambda: L._validated_provenance(prepared()),
                   "must be an object",
                   "GUARD 632: the layout refuses a non-dict from WP5b's validator")
    with_validator(lambda rec: "a string",
                   lambda: L._validated_provenance(prepared()),
                   "must be an object",
                   "GUARD 632: the layout refuses a str from WP5b's validator")
    # 639: WP5b returning a record whose status this layout does not accept --
    # i.e. exactly what would happen if WP5b were widened to a second status.
    widened = dict(prepared(), status="prepared_non_synthetic_v2")
    with_validator(lambda rec: widened,
                   lambda: L._validated_provenance(prepared()),
                   "not an accepted",
                   "GUARD 639: the layout refuses a status WP5b might later allow")
    # 640: WP5b returning a record claiming non-synthetic support -- exactly what
    # would happen if the reviewed non-synthetic release path were switched on.
    non_synthetic = dict(prepared(), non_synthetic_supported=True)
    with_validator(lambda rec: non_synthetic,
                   lambda: L._validated_provenance(prepared()),
                   "claims non-synthetic support",
                   "GUARD 640: the layout refuses a non-synthetic record WP5b might "
                   "later allow")
    # A false alarm check: with the REAL validator restored, the same helper must
    # still accept a good record, so the four refusals above are caused by the
    # substituted validator and not by the fixture being broken.
    check(L._validated_provenance(prepared())["status"] == L.PREPARED_STATUS,
          "GUARD 632/639/640: the real WP5b validator is restored and accepts")
    check(P.validate_provenance_record is original_validator,
          "the substituted WP5b validator was restored")
    # A record whose instance block carries a NON-STRING identity: WP5b's key-set
    # check passes it (it does not type-check instance.instance_id), so the
    # layout's own _non_empty_string is the boundary that refuses it.  That WP5b
    # accepts it is asserted, because it is the fact that makes the layout's
    # guard load-bearing rather than a duplicate.
    nonstring = prepared()
    nonstring["instance"]["instance_id"] = 7
    nonstring.pop("content_sha256")
    nonstring["content_sha256"] = L._content_sha256(nonstring)
    check(P.validate_provenance_record(nonstring) is not None,
          "WP5b accepts a non-string instance_id, so the layout must refuse it")
    refuses(lambda: L._prepared_instance_id(nonstring), "must be a str",
            "_prepared_instance_id: a non-string instance_id")
    empty_id = prepared(instance_id="")
    empty_id.pop("content_sha256")
    empty_id["content_sha256"] = L._content_sha256(empty_id)
    refuses(lambda: L._prepared_instance_id(empty_id), "non-empty string",
            "_prepared_instance_id: an empty instance_id")
    missing_id = prepared()
    missing_id["instance"] = {"content_sha256": fake("d"), "n_assets": 20}
    missing_id.pop("content_sha256")
    missing_id["content_sha256"] = L._content_sha256(missing_id)
    refuses(lambda: L._prepared_instance_id(missing_id), "must be a str",
            "_prepared_instance_id: a missing instance_id")
    # And an instance block that is not an object at all.
    refuses(lambda: L._prepared_instance_id({"instance": "not-an-object"}),
            "instance must be an object",
            "_prepared_instance_id: a non-object instance block")


def main() -> int:
    tests = [test_slots, test_attempt_record, test_rejected_attempt_record,
             test_generation_record, test_instance_index,
             test_payload_builder, test_write_and_verify, test_write_refusals,
             test_on_disk_deviations, test_scalar_guards_separately,
             test_subclass_and_mapping_refusals, test_bool_substitutes_refused,
             test_status_guard_separately, test_directory_guards, test_record_parsing_refusals,
             test_generation_member_disagreements, test_index_disagreements,
             test_sidecar_and_meta_refusals, test_write_and_promote_refusals,
             test_builder_guard_refusals, test_validator_guard_refusals,
             test_read_error_branches, test_matrix_length_and_meta_record_checks,
              test_index_agreement_checks, test_write_instance_unique_guards, test_validator_tamper_probe_deep,
              test_fsync_durability_observable, test_regression_adversarial_five,
              test_regression_manifest_bytes_and_typed_refusal,
              test_regression_new_guard_sites]
    for test in tests:
        before = len(FAILURES)
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - a fixture crash is a fixture failure
            FAILURES.append(f"{test.__name__}: crashed {type(exc).__name__}: {exc}")
        status = "ok" if len(FAILURES) == before else f"{len(FAILURES) - before} FAILURES"
        print(f"  {test.__name__:<28} {status}")
    new_pyc = set(ROOT.rglob("*.pyc")) - PYC_BEFORE
    if new_pyc:
        FAILURES.append(f"the fixture created {len(new_pyc)} .pyc file(s)")
    if FAILURES:
        print(f"\nWP8d fixture: FAIL ({len(FAILURES)} failure(s), {COUNT} checks passed)")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print(f"\nWP8d fixture: PASS ({COUNT} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

