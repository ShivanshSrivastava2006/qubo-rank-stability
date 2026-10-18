"""WP7b D013 v2 bridge COMPATIBILITY ADAPTER -- COPY, CANDIDATE, NOT APPROVED.

What this file is for
---------------------

The WP7b launcher (:mod:`research.g9.kaggle_wp7b.wp7b_launcher`) reaches the D013
bridge through exactly three names:

    d013_bridge._load_checked_abi(library_path, verified_release=token)   # :225
    d013_bridge.run_host_emulated_frame(payload, records, condition,
                                        library_path, feasible_count,
                                        verified_release=token)            # :350
    d013_bridge.ENCODINGS                                                # used by
                                                                          # run_verified_frame

The reviewed v2 bridge
(:mod:`research.g9.cuda_qualification_v2.stage2_cuda_d013_inactive_v2_bridge`)
exports ``load_checked_abi`` and ``run_verified_frame`` and does not export
``ENCODINGS``. Neither name mismatch is a defect in that bridge -- it was never
written against the launcher. It simply means the launcher cannot bind to it
unmodified.

This module supplies ONLY that missing compatibility surface, and it does so by
DELEGATION, never by re-implementation: every constant, ctypes structure,
validator, refuser, counter extractor and envelope commitment is reached
through the frozen v1 bridge that the reviewed v2 bridge itself already
re-exports. The two review-critical differences are preserved exactly:

  1. the backend-1 release gate is the **v2** gate
     (``v2_bridge.require_verified_v2_release``), and
  2. bounded-result acceptance is the **v2** variant
     (``v2_bridge.require_bounded_result_v2``).

What this file deliberately does NOT do
---------------------------------------

  * It does not weaken, relax, re-implement or short-circuit any guard.
  * It does not mint, synthesise, infer or default a ``VerifiedReleaseToken``.
    A token must arrive from the caller and must independently satisfy
    ``v2_plan._check_token``, which re-derives the source map from disk,
    re-derives the token proof, and requires ``owner_approved is True`` in the
    v2 release draft. With the shipped draft that is ``False``, so every
    backend-1 path here refuses. That refusal is the correct behaviour.
  * It does not touch the frozen v1 bridge, plan, contract, fixture or the
    accepted v1 release; it imports them by absolute path.
  * It does not compute a scientific result or read any production data.

FROZEN-LIBRARY CONTRACT, restated because it is the whole point
---------------------------------------------------------------

On the backend-1 (real T4) path the token is verified against the **v2** release
draft and the **v2** source map. A v1 token is refused for two independent
reasons: its ``release_sha256`` names different bytes, and its
``source_map_sha256`` is the digest of a different four-entry map. There is no
code path in this adapter through which a v1 token, a stale token, a
hand-written token or a ``None`` can reach a backend-1 call.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Mapping

# FROZEN reviewed dependencies, imported by absolute path. Not copied, not
# edited. The v1 bridge keeps validating against v1 and the v1 release keeps
# validating against the v1 source.
from research.g9.cuda_qualification import stage2_cuda_d013_inactive as _frozen_bridge
from research.g9.cuda_qualification import (
    stage2_cuda_d013_inactive_corruption_qualification as _frozen_v1_plan)
from research.g9.cuda_qualification_v2 import (
    stage2_cuda_d013_inactive_v2_bridge as _v2_bridge)
from research.g9.cuda_qualification_v2 import (
    stage2_cuda_d013_inactive_v2_corruption_qualification as _v2_plan)


# The reviewed v2 candidate this whole path exists to exercise.
CANDIDATE_SOURCE_REL = _v2_plan.SOURCE_REL
CANDIDATE_SOURCE_SHA256 = (
    "953b7f15a14950d75536d72b074a7907dc06df13539b2ce3f4122cc427ab0f61")

# Which plan owns the release gate. One line, and it is the important one.
PLAN_MODULE = _v2_plan


# --- the launcher-facing surface, delegated unchanged ----------------------

# ``ENCODINGS`` is consumed by ``run_verified_frame`` and by the launcher's
# reconstruction loop. The reviewed v2 bridge deliberately does not re-export
# it; the frozen v1 bridge is its single reviewed definition.
ENCODINGS = _frozen_bridge.ENCODINGS

SCHEMA = _v2_bridge.SCHEMA
ABI_NAME = _v2_bridge.ABI_NAME
CONDITION_CODE = _v2_bridge.CONDITION_CODE
CONDITIONS = _v2_bridge.CONDITIONS
STATUS_REFUSED = _v2_bridge.STATUS_REFUSED
STATUS_OK = _v2_bridge.STATUS_OK
STATUS_BUSY = _v2_bridge.STATUS_BUSY
D013InactiveError = _v2_bridge.D013InactiveError
D013EmptyFeasibleSetError = _v2_bridge.D013EmptyFeasibleSetError
inactive_width = _v2_bridge.inactive_width
expected_abi_layout = _v2_bridge.expected_abi_layout
expected_counters_layout = _v2_bridge.expected_counters_layout
expected_condition_codes = _v2_bridge.expected_condition_codes


def require_verified_v2_release(token: object) -> None:
    """Refuse unless ``token`` is a currently valid **v2** release token.

    Delegates the entire decision to the reviewed v2 bridge, which delegates to
    the v2 plan's ``_check_token``. That function re-derives the source map from
    disk, re-derives the token proof, and requires ``owner_approved is True`` in
    the v2 release draft. It returns False rather than raising on any failure, so
    a bad token becomes a refusal here and never a crash.
    """
    _v2_bridge.require_verified_v2_release(token)


def _load_checked_abi(library_path: Path, *, verified_release: object = None):
    """Launcher-named alias of the reviewed v2 ``load_checked_abi``.

    This is a pure rename. The reviewed v2 loader performs the ABI/counter/
    condition-code layout comparisons, the retired-entry-point refusals, the
    ctypes signatures and the backend-tag check, and it applies the **v2**
    release gate on the backend-1 path. Nothing is added, removed or weakened.
    """
    return _v2_bridge.load_checked_abi(library_path, verified_release=verified_release)


def run_host_emulated_frame(payload: object, records: object, condition: object,
                            library_path: Path, feasible_count: object,
                            *, verified_release: object = None) -> dict[str, object]:
    """Launcher-named alias of the reviewed v2 ``run_verified_frame``.

    The envelope construction -- counter extraction, per-row summaries, the
    ``minimum_word`` bit round-trip, the content hash and the result commitment
    -- is the reviewed v2 code path and is byte-identical in shape to a v1
    envelope. Bounded-result acceptance is the **v2** variant, so the v1 plan is
    never consulted for a backend-1 envelope.

    No release decision is taken here. The reviewed routine loads the ABI itself
    on every call, reads the compiled backend tag, and applies the **v2** release
    gate when and only when that tag is 1. Repeating that decision at this layer
    would either double-require the token on the fixture path (backend 0, where
    no token exists by design) or re-implement the predicate this file exists to
    delegate. The backend tag, not the caller, decides.
    """
    if isinstance(library_path, str):
        library_path = Path(library_path)
    return _v2_bridge.run_verified_frame(
        payload, records, condition, library_path, feasible_count,
        verified_release=verified_release)


def require_bounded_result_v2(envelope: object, condition: str, record_count: int,
                              expected_content_sha256: object = None,
                              verified_release: object = None) -> dict[str, object]:
    """The reviewed v2 bounded-result acceptance, re-exported for callers."""
    return _v2_bridge.require_bounded_result_v2(
        envelope, condition, record_count,
        expected_content_sha256=expected_content_sha256,
        verified_release=verified_release)


def v1_plan_module():
    """The frozen v1 plan, for reviewers comparing the two release gates."""
    return _frozen_v1_plan


def v2_bridge_module():
    """The reviewed v2 bridge this adapter delegates to."""
    return _v2_bridge


__all__ = [
    "PLAN_MODULE", "CANDIDATE_SOURCE_REL", "CANDIDATE_SOURCE_SHA256",
    "ENCODINGS", "SCHEMA", "ABI_NAME", "CONDITIONS", "CONDITION_CODE",
    "STATUS_REFUSED", "STATUS_OK", "STATUS_BUSY", "D013InactiveError",
    "D013EmptyFeasibleSetError", "inactive_width", "expected_abi_layout",
    "expected_counters_layout", "expected_condition_codes",
    "require_verified_v2_release", "_load_checked_abi", "run_host_emulated_frame",
    "require_bounded_result_v2", "v1_plan_module", "v2_bridge_module",
]