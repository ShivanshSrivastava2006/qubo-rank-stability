"""Synthetic-testable, non-writing bridge from the generic core to D015/D016.

This is an in-memory integration seam, not a Stage-2 producer. The caller
supplies an already chosen payload, coefficient record, frozen f*, and the
original-objective/feasibility callables. It reads no files, chooses no
instance or coefficient, derives no ground truth, and emits no artifact.

The full slack offset table remains local to this prepared instance. The core
is scanned without qualification controls, and only its bounded minima and
compacted ties are handed to the frozen host reconstruction.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import math

from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as core
from research.g9.cuda_qualification import stage2_cuda_reconstruct as recon
from src.g4.classification import DecodedClassifier, OriginalObjectiveService


class InMemoryRunnerError(RuntimeError):
    """The integration seam was given an invalid configuration or core output."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InMemoryRunnerError(message)


class PreparedInMemoryRunner:
    """Prepare one full domain, then reconstruct control-free records one by one."""

    def __init__(self, payload: Mapping[str, object], *, f_star: float,
                 objective: Callable[[tuple[int, ...]], float],
                 feasible: Callable[[tuple[int, ...]], bool]) -> None:
        _require(type(f_star) is float and math.isfinite(f_star),
                 "f_star must be finite binary64 supplied by the caller")
        _require(callable(objective) and callable(feasible),
                 "frozen original-objective and feasibility callables are required")
        domain = core.build_domain(payload)
        slack = recon.SlackIndexMap(domain["offsets"], domain["lift_total"])
        lambda_ref = domain["payload"]["lambda_ref"]
        classifiers = {c_f: DecodedClassifier(
            OriginalObjectiveService(objective, lambda_ref, float(c_f)), feasible,
        ) for c_f in recon.CF_VALUES}
        self._domain = domain
        self._slack = slack
        self._classifiers = classifiers
        self._f_star = f_star
        self._lambda_ref = lambda_ref

    @property
    def lift_total(self) -> int:
        return self._slack.lift_total

    @property
    def offsets_sha256(self) -> str:
        """Identity of the immutable slack-offset snapshot used here."""
        return self._slack.offsets_sha256

    def reconstruct_record(self, coefficients: Mapping[str, object]) -> dict[str, object]:
        """Evaluate both encodings with no controls and return summary fields."""
        record = core.coefficient_record(coefficients)
        raw = {encoding: core.scan(self._domain, record, encoding, control={})
               for encoding in core.ENCODINGS}
        return recon.reconstruct_pair(raw, self._slack, self._classifiers,
                                      self._f_star, self._lambda_ref)

    def reconstruct_core_result(self, core_result: Mapping[str, object], slot: int,
                                *, offsets_sha256: str) -> dict[str, object]:
        """Diagnostic projection of an external bounded core result.

        The caller must obtain ``offsets_sha256`` from the domain that produced
        ``core_result``. The current raw core result does not carry this digest;
        a future device-facing envelope must bind it, rather than echoing this
        runner's property without an independent check.
        """
        _require(type(offsets_sha256) is str and offsets_sha256 == self.offsets_sha256,
                 "external core result is not bound to the prepared slack offsets")
        return recon.reconstruct_core_run(core_result, slot, self._slack,
                                          self._classifiers, self._f_star,
                                          self._lambda_ref)
