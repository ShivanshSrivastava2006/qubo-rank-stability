"""Conformance and performance checks for the Gate-5 clause-(b) domain cache.

No primary minimum, tie set, classification, grid point, sweep, experiment, or
result is produced here. Primary-domain checks concern only C_E construction.
Certification equivalence is exercised on a bounded deterministic subset.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
import itertools
import math
from pathlib import Path
import struct
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.g4.classification import DecodedClassifier, OriginalObjectiveService
from src.g4.energy import (
    exact_slack_lift,
    objective,
    prepare_coefficients,
    prepare_decoded_state,
    prepare_instance,
    prepare_slack_state,
    slack_energy,
    slack_energy_prepared,
    unbalanced_energy,
    unbalanced_energy_prepared,
)
from src.g4.instance import load_instance
from src.g4.parameters import Coefficients, load_coefficients
from src.g5.certify import certify_domain, certify_prepared_domain
from src.g5.domains import (
    BinaryDomain,
    PreparedDomainCache,
    SlackDomainCache,
    build_slack_domain_cache,
    prepare_fixture_domains,
    prepare_slack_domain,
)


INSTANCE_PATH = ROOT / "research/canonical/stage1_instance.json"
LEDGER_PATH = ROOT / "research/g4/G4_PRIMARY_LEDGER.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_failure(callable_, label: str) -> None:
    try:
        callable_()
    except (FrozenInstanceError, IndexError, TypeError, ValueError):
        return
    raise AssertionError(f"fail-closed probe accepted: {label}")


def _stream_digest(cache: SlackDomainCache) -> str:
    """Independent canonical logical transcript for the cache digest."""
    digest = hashlib.sha256()
    digest.update(b"G5-SLACK-DOMAIN-CACHE-V1\0")
    digest.update(bytes.fromhex(cache.instance_sha256))
    digest.update(
        struct.pack(
            "<IIII??",
            cache.decoded_width,
            cache.sector_count,
            cache.sector_slack_bits,
            cache.budget_slack_bits,
            *cache.activity_signature,
        )
    )
    for offset in memoryview(cache.offset_bytes).cast("Q"):
        digest.update(struct.pack("<Q", int(offset)))
    for mask in memoryview(cache.auxiliary_bytes).cast("I"):
        digest.update(struct.pack("<I", int(mask)))
    return digest.hexdigest()


def check_digest_portability() -> None:
    """Prove the logical transcript is invariant to source serialization order."""
    offsets = (0, 2, 5)
    masks = (3, 7, 11, 13, 17)
    little_offsets = struct.unpack("<3Q", struct.pack("<3Q", *offsets))
    big_offsets = struct.unpack(">3Q", struct.pack(">3Q", *offsets))
    little_masks = struct.unpack("<5I", struct.pack("<5I", *masks))
    big_masks = struct.unpack(">5I", struct.pack(">5I", *masks))

    def digest(values_offsets, values_masks):
        transcript = hashlib.sha256()
        for value in values_offsets:
            transcript.update(struct.pack("<Q", int(value)))
        for value in values_masks:
            transcript.update(struct.pack("<I", int(value)))
        return transcript.digest()

    require(
        digest(little_offsets, little_masks) == digest(big_offsets, big_masks),
        "logical cache digest depends on source byte order",
    )
    print("PASS cache logical digest is invariant to simulated source byte order")


def _nearest_register_values(residual: float, maximum: int) -> tuple[int, ...]:
    """Independent floor/ceiling oracle with no integer truncation."""
    require(math.isfinite(residual), "independent residual is nonfinite")
    if residual <= 0.0:
        return (0,)
    if residual >= maximum:
        return (maximum,)
    lower = math.floor(residual)
    upper = math.ceil(residual)
    if lower == upper:
        return (lower,)
    lower_distance = residual - float(lower)
    upper_distance = float(upper) - residual
    if lower_distance < upper_distance:
        return (lower,)
    if upper_distance < lower_distance:
        return (upper,)
    return (lower, upper)


def _independent_primary_lifts(instance, x: tuple[int, ...]) -> set[tuple[int, ...]]:
    """Bounds-based oracle independent of energy and cache implementation."""
    choices = []
    for members in instance.sectors:
        residual = float(instance.C) - sum(float(x[index]) for index in members)
        choices.append(_nearest_register_values(residual, 3))
    spend = sum(float(instance.prices[index]) * float(x[index]) for index in range(20))
    choices.append(_nearest_register_values(float(instance.B) - spend, 2047))
    lifts = set()
    for values in itertools.product(*choices):
        bits = []
        for value in values[:-1]:
            bits.extend(((value >> degree) & 1) for degree in range(2))
        bits.extend(((values[-1] >> degree) & 1) for degree in range(11))
        lifts.add(tuple(bits))
    return lifts


def check_primary_cache() -> SlackDomainCache:
    instance = load_instance(INSTANCE_PATH)
    row0 = load_coefficients(LEDGER_PATH, 0, 0, 0)
    row60 = load_coefficients(LEDGER_PATH, 60, 60, 60)
    started = time.perf_counter()
    cache0 = build_slack_domain_cache(instance, row0)
    first_seconds = time.perf_counter() - started
    require(len(cache0) == 1 << 20, "active primary C_slack must have one lift per x")
    cache0.require_compatible(row60)
    cache0.require_canonical_energy_layout()
    require(cache0.sector_slack_bits == 2, "wrong sector register width")
    require(cache0.budget_slack_bits == 11, "wrong budget register width")
    require(cache0.packed_bytes <= 16 * 1024 * 1024, "compact domain exceeds 16 MiB")
    require(first_seconds < 120.0, "cache construction is not materially bounded")

    for index, (x, y) in enumerate(cache0):
        require(index == sum(bit << (19 - position) for position, bit in enumerate(x)), "decoded ordering changed")
        expected = _independent_primary_lifts(instance, x)
        require(len(expected) == 1, f"primary state {index} has unexpected oracle degeneracy")
        require(y in expected, f"wrong primary lift at decoded index {index}")

    digest = _stream_digest(cache0)
    require(cache0.logical_sha256() == digest, "production logical digest differs from oracle")
    print(
        "PASS active primary slack domain: "
        f"{len(cache0)} exact lifts, digest={digest}, packed={cache0.packed_bytes} bytes, "
        f"build={first_seconds:.3f}s"
    )
    return cache0


def check_toy_exact_minimizers() -> None:
    from src.g4.instance import Instance

    toy = Instance(
        tickers=("A",), sectors=((0,),), mu=(0.0,), sigma=((0.0,),), prices=(1.0,),
        kappa_risk=1.0, K=1, C=1.5, B=1.0,
    )
    coefficients = Coefficients(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
    produced = set(build_slack_domain_cache(toy, coefficients))
    expected = set()
    for x in itertools.product((0, 1), repeat=1):
        best = None
        minimizers = []
        for y in itertools.product((0, 1), repeat=13):
            sector = y[0] + 2 * y[1]
            budget = sum(y[2 + degree] << degree for degree in range(11))
            penalty = (1.5 - x[0] - sector) * (1.5 - x[0] - sector)
            penalty += (1.0 - x[0] - budget) * (1.0 - x[0] - budget)
            if best is None or penalty < best:
                best = penalty
                minimizers = [y]
            elif penalty == best:
                minimizers.append(y)
        expected.update((x, y) for y in minimizers)
    require(produced == expected, "analytic toy minimizers differ from full auxiliary enumeration")
    print(f"PASS analytic minimizers against full toy enumeration: {len(produced)} lifts")


def _classifier(instance) -> DecodedClassifier:
    service = OriginalObjectiveService(lambda x: objective(instance, x), lambda_ref=1.0)
    return DecodedClassifier(service, lambda x: True)


def check_prepared_certification(cache: SlackDomainCache) -> None:
    instance = load_instance(INSTANCE_PATH)
    raw_coefficients = load_coefficients(LEDGER_PATH, 30, 30, 30)
    coefficients = prepare_coefficients(raw_coefficients)
    indices = tuple(range(0, 1 << 20, (1 << 20) // 64))

    raw_unbalanced = tuple(cache[index][0] for index in indices)
    raw_slack = tuple(cache[index] for index in indices)
    pair = prepare_fixture_domains(instance, raw_unbalanced, raw_slack)
    unbalanced_cache = pair.unbalanced
    slack_cache = pair.slack
    for decoded, slack in zip(unbalanced_cache.states, slack_cache.states, strict=True):
        require(slack.decoded is decoded, "slack and unbalanced caches do not share decoded objects")
    classifier = _classifier(instance)

    cases = (
        (
            "unbalanced",
            raw_unbalanced,
            unbalanced_cache,
            lambda x: unbalanced_energy(instance, x, raw_coefficients),
            lambda state: unbalanced_energy_prepared(state, coefficients),
            lambda x: x,
        ),
        (
            "slack",
            raw_slack,
            slack_cache,
            lambda z: slack_energy(instance, z[0], z[1], raw_coefficients),
            lambda state: slack_energy_prepared(state, coefficients),
            lambda z: z[0],
        ),
    )
    for label, raw, prepared, raw_energy, prepared_energy, decode in cases:
        legacy = certify_domain(
            lambda raw=raw: iter(raw), raw_energy, 1.0, 0.0, decode, classifier
        )
        produced = certify_prepared_domain(
            prepared, prepared_energy, 1.0, 0.0, decode, classifier
        )
        require(produced == legacy, f"prepared {label} certification differs from legacy path")
    print("PASS prepared positional certification equals legacy certification for both encodings")


def check_fail_closed(cache: SlackDomainCache) -> None:
    instance = load_instance(INSTANCE_PATH)
    valid = load_coefficients(LEDGER_PATH, 0, 0, 0)
    inactive = object.__new__(Coefficients)
    for name, value in valid.__dict__.items():
        object.__setattr__(inactive, name, value)
    object.__setattr__(inactive, "budget_slack", +0.0)

    expect_failure(lambda: cache.require_compatible(inactive), "+0.0 cache reuse")
    expect_failure(
        lambda: build_slack_domain_cache(load_instance(INSTANCE_PATH), inactive),
        "+0.0 cache construction",
    )
    expect_failure(lambda: setattr(cache, "activity_signature", (False, True)), "cache mutation")
    expect_failure(
        lambda: cache.require_instance(replace(instance, B=instance.B + 1.0)),
        "cache reuse on a different instance",
    )
    alternate_partition = replace(cache, sector_slack_bits=3, budget_slack_bits=7)
    expect_failure(
        lambda: prepare_slack_domain(instance, alternate_partition),
        "equal-total-width but wrong register partition",
    )
    expect_failure(lambda: cache.__getitem__(len(cache)), "cache index overflow")
    prepared_instance = prepare_instance(instance)
    raw = BinaryDomain(20)
    state0 = prepare_decoded_state(prepared_instance, raw[0])
    state1 = prepare_decoded_state(prepared_instance, raw[1])
    expect_failure(
        lambda: PreparedDomainCache((raw[0], raw[1]), (state1, state0), "unbalanced"),
        "manually misaligned prepared-domain construction",
    )
    auxiliary = (0,) * 19
    valid_pair = prepare_fixture_domains(
        instance,
        (raw[0], raw[1]),
        ((raw[0], auxiliary), (raw[1], auxiliary)),
    )
    expect_failure(
        lambda: replace(
            valid_pair.unbalanced,
            states=tuple(reversed(valid_pair.unbalanced.states)),
        ),
        "dataclass replacement of an aligned prepared domain",
    )
    expect_failure(
        lambda: certify_prepared_domain([], lambda _: 0.0, 1.0, 0.0, lambda x: x, _classifier(instance)),
        "raw domain passed to prepared certifier",
    )
    print("PASS cache invalidation, immutability, bounds, and typed-boundary fail closed")


def main() -> int:
    check_toy_exact_minimizers()
    check_digest_portability()
    cache = check_primary_cache()
    check_prepared_certification(cache)
    check_fail_closed(cache)
    print("PASS Gate-5 clause-(b) domain-cache checks; no primary certification executed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
