#!/usr/bin/env python3
"""Shared NON-PRODUCTION stand-in material for the WP8c rehearsal and fixture.

STATUS: BUILD + VALIDATION ONLY. UNARMED.

Everything this module produces is conspicuously NON-PRODUCTION:

* the only instance it ever prepares is a stand-in whose id starts with
  ``NONPROD-STANDIN`` and contains ``NON-PRODUCTION``, which is the ONLY id WP8b's
  single fixture branch will accept
  (``research/g9/wp8b/wp8b_non_synthetic_preparation.py:318``,
  ``check_fixture_only_approval`` at ``:935-965``, whose record announces
  ``prepared_non_production_standin`` and never
  ``prepared_non_synthetic_authorized``);
* the ``mu_new`` / ``Sigma_new`` encodings and the return matrix are obvious
  placeholder CONSTANTS — no generator ran, no draw occurred and no numerics
  were computed to produce them;
* the WP1 identity it reuses is the DRAFT_UNQUALIFIED payload that WP1 itself
  requires (``research/g9/stage2_production_identity.py:400-402``).  It is
  re-derived on every call from the reviewed ``runtime_config.json`` and is
  NEVER re-labelled, re-stated or reinterpreted as accepted, qualified or
  authorized;
* the platform observations are conspicuous non-production constants fed to
  :class:`~research.g9.wp8c_production.wp8c_production_session.AuthorityBoundary`.

This module also supplies the two things WP8c deliberately does NOT own: a WP3
device-backend stand-in and a Python reference, both injected through the seam
mapping.  They exist so the ORDER, BLOCKING and receipt SHAPES can be rehearsed;
neither is a production backend and neither computes a scientific value.  The
device stand-in returns the SAME placeholder words as the reference, so WP3's
bit-for-bit comparison is genuinely exercised (a mismatch would raise) while no
energy is ever evaluated.
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9 import stage2_instance_preparation as wp5b  # noqa: E402
from research.g9 import stage2_production_identity as wp1  # noqa: E402
from research.g9.wp8b import wp8b_non_synthetic_preparation as wp8b  # noqa: E402
from research.g9.wp8d_production import wp8d_production_layout as wp8dp  # noqa: E402

#: The one conspicuously non-production instance id this package ever uses.
STANDIN_ID = "NONPROD-STANDIN-0001-NON-PRODUCTION"
#: A second stand-in, for the "swapped instance" negative case.
STANDIN_ID_B = "NONPROD-STANDIN-0002-NON-PRODUCTION"
#: A real-looking id that is NOT a conspicuously labelled stand-in.  WP8b's
#: fixture branch refuses it, which is the negative control on the labelling.
UNLABELLED_ID = "STAGE2-01"

#: A fixed date, so every record is a pure function of its inputs and no test
#: depends on a clock.
PINNED = datetime.date(2026, 1, 1)
PINNED_FUTURE = "2099-12-31"

#: The reviewed runtime config that carries the WP1 DRAFT identity.  It is read,
#: never written, and the identity inside it keeps its own DRAFT_UNQUALIFIED
#: status and ``authorization = NONE``.
RUNTIME_CONFIG_REL = "research/g9/kaggle_wp7b/runtime_config.json"

#: Conspicuously non-production platform observations.  These are DECLARED
#: values, not probes and not measurements.  They are deliberately different from
#: the pinned WP7 image pin so that a caller cannot pass them off as observed
#: platform facts.
STANDIN_OBSERVATIONS = {
    "platform_reported": {
        "gpu_name": "STANIN-NONPRODUCTION-DECLARED",
        "compute_capability": "0.0",
        "cuda_driver_version": "0.0",
        "cuda_runtime_version": "0.0",
        "nvcc_version_release": "0.0, V0.0.0",
        "python_version": "0.0.0",
        "numpy_version": "0.0.0",
    },
    "image_reported": {
        "build_env": {
            "BUILD_DATE": "NONPROD-DECLARED",
            "COLAB_IMAGE_TYPE": "NONPROD-DECLARED",
            "CUDA_VERSION": "NONPROD-DECLARED",
            "GIT_COMMIT": "NONPROD-DECLARED",
        },
        "cuda_home": "/nonproduction-declared/cuda",
        "nvcc_path": "/nonproduction-declared/cuda/bin/nvcc",
    },
}


def runtime_config() -> dict:
    """Read the reviewed runtime config.  Read-only; never re-serialized."""
    return json.loads((ROOT / RUNTIME_CONFIG_REL).read_text("ascii"))


def draft_identity() -> dict:
    """The WP1 DRAFT_UNQUALIFIED identity, re-derived from the reviewed file.

    Returned UNCHANGED.  Its ``status`` stays ``DRAFT_UNQUALIFIED`` and its
    ``authorization`` stays ``NONE`` — this module never edits either field, and
    the fixture asserts both, because silently reinterpreting the draft is
    precisely the failure WP8a's owner default 1 forbids
    (``...OWNER_DECISION.md:149``).
    """
    identity = runtime_config()["accepted_identity"]
    wp1.validate_production_identity(identity)
    return copy.deepcopy(identity)


def draft_identity_sha256() -> str:
    return wp1.validate_production_identity(draft_identity())


def standin_instance(instance_id: str = STANDIN_ID) -> wp5b.SyntheticInstance:
    """A tiny (n=3) stand-in instance.  Obvious non-production parameters."""
    return wp5b.SyntheticInstance(
        instance_id=instance_id,
        synthetic=False,
        order=("AAA", "BBB", "CCC"),
        mu=(0.1, 0.2, 0.3),
        Sigma=((0.04, 0.01, 0.005), (0.01, 0.05, 0.008), (0.005, 0.008, 0.06)),
        p=(0.3, 0.3, 0.4),
        K=2,
        C=2,
        B=1100.0,
        kappa=1.0,
        sector_of={"AAA": "tech", "BBB": "tech", "CCC": "util"},
        sector_labels=("tech", "util"),
        approval=None,
    )


def approval_over(*, instance_id: str = STANDIN_ID, nonce: str = "wp8c-standin-nonce-1",
                  scope: str = wp8b.FIXTURE_SCOPE, status: str = wp8b.APPROVAL_STATUS,
                  label: str = wp8b.OWNER_APPROVAL_LABEL,
                  expiry: str = PINNED_FUTURE) -> dict:
    """A structurally complete WP8b approval, every field overridable.

    This is WP8b's OWN fixture-branch approval, consumed by WP8b's own
    ``prepare_non_synthetic``.  It is NOT a WP8c one-use scientific-write
    authorization: that record is a different schema, and WP8c never constructs
    one.
    """
    return {
        "schema": wp8b.APPROVAL_SCHEMA,
        "status": status,
        "label": label,
        "scope": scope,
        "approves_instance_content_sha256": wp8b.instance_content_sha256(
            standin_instance(instance_id)),
        "instance_id": instance_id,
        "expiry": expiry,
        "nonce": nonce,
        "statement": wp8b.APPROVAL_STATEMENT,
    }


def prepare_standin(instance, approval, *, root: str) -> dict:
    """Drive WP8b's ONE accepting branch, always naming the module's token."""
    return wp8b.prepare_non_synthetic(
        instance, approval, root=root, now=PINNED,
        fixture_context=wp8b.FIXTURE_CONTEXT_TOKEN)


def mu_sigma() -> tuple[list[str], list[list[str]]]:
    """NON-PRODUCTION placeholder moment encodings in binary64 hex.

    Obviously-labelled constants.  No generator, no draw and no numerics were run
    to produce them, and nothing in WP8c reads a value out of them.
    """
    count = wp8dp.RETURN_MATRIX_BYTES  # unused for shape; kept explicit below
    del count
    from research.g9.wp8d import wp8d_drawn_instance_layout as wp8d
    mu = ["0x1.5c28f5c28f5c3p+0"] * wp8d.ASSET_COUNT
    sigma = [["0x1.a3d70a3d70a3d8p-3"] * wp8d.ASSET_COUNT
             for _ in range(wp8d.ASSET_COUNT)]
    return mu, sigma


def return_matrix() -> bytes:
    """A NON-PRODUCTION placeholder return matrix of the exact required length."""
    digest = hashlib.sha512(b"wp8c-nonproduction-standin-return-matrix").digest()
    count, rest = divmod(wp8dp.RETURN_MATRIX_BYTES, len(digest))
    return digest * count + digest[:rest]


def sandbox_root(base: str, name: str) -> str:
    """A WP8d-production layout root: the instance root already exists."""
    root = os.path.join(base, name)
    os.makedirs(root, exist_ok=True)
    os.makedirs(os.path.join(root, wp8dp.INSTANCE_ROOT), exist_ok=True)
    return root


def writer_root(base: str, name: str) -> str:
    """A WP4b instance root, which is the directory holding the range plan."""
    root = os.path.join(base, name)
    os.makedirs(root, exist_ok=True)
    return root


def write_kwargs(*, root: str, record: dict, instance, slot: int = 1, attempt: int = 0,
                 instance_id: str = STANDIN_ID, sector: bytes = b"wp8c-nonprod-sector",
                 feasible_count: int = 7,
                 impl: str = hashlib.sha256(
                     b"wp8c-nonproduction-implementation-record").hexdigest()) -> dict:
    """The full WP8d-production write-argument set for one stand-in instance."""
    mu, sigma = mu_sigma()
    return dict(
        slot=slot, attempt=attempt, instance_id=instance_id,
        sector_partition_sha256=hashlib.sha256(sector).hexdigest(),
        feasible_count=feasible_count, return_matrix=return_matrix(),
        prepared_record=record, instance=instance,
        implementation_record_content_sha256=impl,
        mu_new=mu, sigma_new=sigma, root=root)


def promote_standin(base: str, *, slot: int = 1, instance_id: str = STANDIN_ID,
                    nonce: str = "wp8c-standin-nonce-1") -> dict:
    """Prepare and promote ONE stand-in instance through WP8d-production.

    This is the "previously validated WP8d production layout" the session
    consumes.  It is a stand-in, so WP8b is asked with
    ``require_production=False``; the production path is exercised separately
    and refuses.
    """
    instance = standin_instance(instance_id)
    approval = approval_over(instance_id=instance_id, nonce=nonce)
    record = prepare_standin(instance, approval, root=base)
    kwargs = write_kwargs(root=base, record=record, instance=instance, slot=slot,
                          instance_id=instance_id)
    return wp8dp.write_standin_instance(**kwargs)


# ===========================================================================
# The two injected WP3 callables
# ===========================================================================

#: The one placeholder energy word.  A declared NON-PRODUCTION constant, not a
#: computed value: no energy is evaluated anywhere in this package.
PLACEHOLDER_WORD = 0.0

#: The placeholder record-shaping constants.  Obvious non-production values, NOT
#: computed and NOT scientific: no energy minimum was evaluated, no
#: classification was performed and no instance was read to produce them.
PLACEHOLDER_MINIMUM = -1.5
PLACEHOLDER_F_STAR = 0.0
PLACEHOLDER_LAMBDA_REF = 1.0

#: What a comparator pair is allowed to claim.  The device stand-in and the
#: Python reference both return exactly this, so WP3's bit-for-bit comparison
#: runs for real over every row x pair x encoding and a disagreement would raise.
COMPARISON_FIELDS = ("energy_minimum_words", "canonical_minimum_index",
                     "tie_flags", "reconstruction")


def placeholder_comparison(row, pair, encoding) -> dict:
    """The declared stand-in comparison result.  A VALUE, not a verdict.

    The SHAPE is the reviewed one, not a convenient one: WP3's
    ``_canonical_comparison`` refuses a tie flag that is a bool rather than an
    int (``research/g9/stage2_section_b2_harness.py:796``), and
    ``_word_bits`` refuses a non-float energy word (``:763-774``), so a stand-in
    that "just returns something" would be refused by WP3 for a reason that has
    nothing to do with the contract under test.  Matching the shape keeps the
    refusal channel honest.

    ``reconstruction`` is a deterministic function of the inputs, so the device
    and the reference agree by construction — which is exactly what makes the
    rehearsal a rehearsal: it proves the ORDER, the BLOCKING and the receipt
    SHAPES, and it proves WP3's comparison code path executes, without any
    energy ever being evaluated.
    """
    c_h, c_f = int(pair[0]), int(pair[1])
    return {
        "energy_minimum_words": [PLACEHOLDER_WORD],
        "canonical_minimum_index": 0,
        "tie_flags": [0],
        "reconstruction": json.dumps(
            {"c_h": c_h, "c_f": c_f, "set_label": "NONPROD-STANDIN",
             "tie_count": 0, "x_e_size": 0},
            sort_keys=True, separators=(",", ":")),
    }


class StandinDeviceBackend:
    """The NON-PRODUCTION WP3 device-backend stand-in.

    It is NOT a production backend and is never loaded from CUDA.  It declares
    ``supports_inactive_positive_zero = True`` as a PLAIN DATA attribute, which
    is the only way WP3 will unlock the D013 repeat
    (``research/g9/stage2_section_b2_harness.py:1109``, ``:1122-1136``) — so
    the D013 prerequisite is genuinely exercised, and a backend that did NOT
    declare it is genuinely refused.
    """

    supports_inactive_positive_zero = True

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, row, pair, encoding) -> dict:
        self.calls += 1
        return placeholder_comparison(row, pair, encoding)


class UndeclaredDeviceBackend(StandinDeviceBackend):
    """A stand-in that does NOT declare the inactive ``+0.0`` support.

    Models the qualified v1 backend, which refuses inactive families at
    ``research/g9/cuda_qualification/stage2_cuda_core_bridge.cu:29`` (as named
    by ``stage2_section_b2_harness.py:1124-1135``).  Used to prove the D013
    prerequisite really blocks a fired D013 rather than being a flag.
    """

    supports_inactive_positive_zero = False


def device_backend_factory(boundary) -> StandinDeviceBackend:
    """The injected device-backend factory, taking the authority boundary.

    The boundary is accepted and IGNORED on purpose: it proves the boundary
    cannot smuggle a pass in, because the backend's result is fixed regardless
    of what the boundary claims.
    """
    return StandinDeviceBackend()


def undeclared_device_backend_factory(boundary) -> UndeclaredDeviceBackend:
    return UndeclaredDeviceBackend()


def python_reference(row, pair, encoding) -> dict:
    """The injected Python reference callable WP3 compares the device against."""
    return placeholder_comparison(row, pair, encoding)


def standin_boundary(module) -> object:
    """The conspicuously labelled non-production authority boundary."""
    return module.AuthorityBoundary(STANDIN_OBSERVATIONS, production=False)
