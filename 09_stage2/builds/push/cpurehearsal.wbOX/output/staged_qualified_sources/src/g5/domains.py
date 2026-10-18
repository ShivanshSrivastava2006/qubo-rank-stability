"""Exact, reusable Gate-5 candidate domains.

The active-CSB slack domain is grid-independent: every accepted Gate-5
coefficient is finite and strictly positive, so an auxiliary minimizer depends
on the decoded residual and register bounds, not on the coefficient magnitude.
The compact cache below records that domain once. A future D013 inactive
family uses +0.0 and must build a different, coefficient-dependent domain; this
module therefore rejects inactive coefficients rather than reusing this cache.
"""

from __future__ import annotations

from array import array
from bisect import bisect_right
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
import hashlib
import itertools
import json
import math
import struct

from src.g4 import energy as canonical_energy
from src.g4.energy import (
    PreparedDecodedState,
    PreparedSlackState,
    prepare_decoded_state,
    prepare_instance,
    prepare_slack_state,
)
from src.g4.instance import Instance
from src.g4.parameters import Coefficients


def _bits_from_mask(mask: int, width: int) -> tuple[int, ...]:
    """Match itertools.product((0, 1), repeat=width) ordering."""
    return tuple((mask >> (width - 1 - index)) & 1 for index in range(width))


def _auxiliary_from_mask(mask: int, width: int) -> tuple[int, ...]:
    """Slack register layout is little-endian within consecutive registers."""
    return tuple((mask >> index) & 1 for index in range(width))


def _domain_instance_digest(instance: Instance) -> str:
    """Bind exactly the fields that determine decoded ordering and slack lifts."""
    payload = {
        "tickers": instance.tickers,
        "sectors": instance.sectors,
        "prices_hex": tuple(float(value).hex() for value in instance.prices),
        "C_hex": float(instance.C).hex(),
        "B_hex": float(instance.B).hex(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class BinaryDomain(Sequence[tuple[int, ...]]):
    """Compact re-iterable representation of {0,1}^n."""

    def __init__(self, width: int):
        if not isinstance(width, int) or width < 0 or width >= 63:
            raise ValueError("binary-domain width must be an integer in [0, 63)")
        self.width = width
        self._length = 1 << width

    def __len__(self) -> int:
        return self._length

    def __getitem__(self, index: int | slice):
        if isinstance(index, slice):
            return tuple(self[position] for position in range(*index.indices(len(self))))
        if not isinstance(index, int):
            raise TypeError("binary-domain index must be an integer or slice")
        if index < 0:
            index += len(self)
        if index < 0 or index >= len(self):
            raise IndexError("binary-domain index out of range")
        return _bits_from_mask(index, self.width)


@dataclass(frozen=True)
class SlackDomainCache(Sequence[tuple[tuple[int, ...], tuple[int, ...]]]):
    """Compact exact-minimizer slack domain, reusable across active CSB rows."""

    decoded_width: int
    sector_count: int
    sector_slack_bits: int
    budget_slack_bits: int
    auxiliary_width: int
    offset_bytes: bytes
    auxiliary_bytes: bytes
    activity_signature: tuple[bool, bool]
    instance_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.decoded_width, int) or self.decoded_width < 0 or self.decoded_width >= 63:
            raise ValueError("slack-domain decoded width is malformed")
        if not isinstance(self.sector_count, int) or self.sector_count <= 0:
            raise ValueError("slack-domain sector count is malformed")
        if (
            not isinstance(self.sector_slack_bits, int)
            or self.sector_slack_bits <= 0
            or self.sector_slack_bits >= 32
        ):
            raise ValueError("slack-domain sector width is malformed")
        if (
            not isinstance(self.budget_slack_bits, int)
            or self.budget_slack_bits <= 0
            or self.budget_slack_bits >= 32
        ):
            raise ValueError("slack-domain budget width is malformed")
        expected_auxiliary_width = (
            self.sector_count * self.sector_slack_bits + self.budget_slack_bits
        )
        if self.auxiliary_width != expected_auxiliary_width or self.auxiliary_width > 32:
            raise ValueError("slack-domain register partition is malformed")
        expected_offsets = (1 << self.decoded_width) + 1
        if not isinstance(self.offset_bytes, bytes) or len(self.offset_bytes) != expected_offsets * 8:
            raise ValueError("slack-domain offsets are malformed")
        if not isinstance(self.auxiliary_bytes, bytes) or len(self.auxiliary_bytes) % 4:
            raise ValueError("slack-domain auxiliary masks are malformed")
        offsets = memoryview(self.offset_bytes).cast("Q")
        if offsets[0] != 0 or offsets[-1] != len(self):
            raise ValueError("slack-domain offsets do not cover the cached lifts")
        if self.activity_signature != (True, True):
            raise ValueError("active-CSB cache cannot represent an inactive +0.0 family")
        if len(self.instance_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.instance_sha256
        ):
            raise ValueError("slack-domain instance binding is malformed")
        previous = -1
        for offset in offsets:
            if offset <= previous:
                raise ValueError("every decoded state must have at least one cached lift")
            previous = offset

    def __len__(self) -> int:
        return len(self.auxiliary_bytes) // 4

    def _state(self, decoded_mask: int, lift_index: int):
        x = _bits_from_mask(decoded_mask, self.decoded_width)
        auxiliary_masks = memoryview(self.auxiliary_bytes).cast("I")
        y = _auxiliary_from_mask(auxiliary_masks[lift_index], self.auxiliary_width)
        return x, y

    def __getitem__(self, index: int | slice):
        if isinstance(index, slice):
            return tuple(self[position] for position in range(*index.indices(len(self))))
        if not isinstance(index, int):
            raise TypeError("slack-domain index must be an integer or slice")
        if index < 0:
            index += len(self)
        if index < 0 or index >= len(self):
            raise IndexError("slack-domain index out of range")
        offsets = memoryview(self.offset_bytes).cast("Q")
        decoded_mask = bisect_right(offsets, index) - 1
        return self._state(decoded_mask, index)

    def __iter__(self) -> Iterator[tuple[tuple[int, ...], tuple[int, ...]]]:
        offsets = memoryview(self.offset_bytes).cast("Q")
        for decoded_mask in range(1 << self.decoded_width):
            start = offsets[decoded_mask]
            stop = offsets[decoded_mask + 1]
            for lift_index in range(start, stop):
                yield self._state(decoded_mask, lift_index)

    def iter_indexed(
        self,
    ) -> Iterator[tuple[int, tuple[int, ...], tuple[int, ...]]]:
        """Yield the decoded mask with each raw lift, preserving cache order."""
        offsets = memoryview(self.offset_bytes).cast("Q")
        for decoded_mask in range(1 << self.decoded_width):
            start = offsets[decoded_mask]
            stop = offsets[decoded_mask + 1]
            for lift_index in range(start, stop):
                x, y = self._state(decoded_mask, lift_index)
                yield decoded_mask, x, y

    def iter_auxiliary_indexed(self) -> Iterator[tuple[int, tuple[int, ...]]]:
        """Yield mask position and auxiliary bits without rebuilding decoded tuples."""
        offsets = memoryview(self.offset_bytes).cast("Q")
        auxiliary_masks = memoryview(self.auxiliary_bytes).cast("I")
        for decoded_mask in range(1 << self.decoded_width):
            start = offsets[decoded_mask]
            stop = offsets[decoded_mask + 1]
            for lift_index in range(start, stop):
                y = _auxiliary_from_mask(
                    auxiliary_masks[lift_index], self.auxiliary_width
                )
                yield decoded_mask, y

    @property
    def packed_bytes(self) -> int:
        """Bytes in the packed buffers, excluding small object overhead."""
        return len(self.offset_bytes) + len(self.auxiliary_bytes)

    def logical_sha256(self) -> str:
        """Hash logical integers canonically, independent of host byte order."""
        digest = hashlib.sha256()
        digest.update(b"G5-SLACK-DOMAIN-CACHE-V1\0")
        digest.update(bytes.fromhex(self.instance_sha256))
        digest.update(
            struct.pack(
                "<IIII??",
                self.decoded_width,
                self.sector_count,
                self.sector_slack_bits,
                self.budget_slack_bits,
                *self.activity_signature,
            )
        )
        for offset in memoryview(self.offset_bytes).cast("Q"):
            digest.update(struct.pack("<Q", int(offset)))
        for mask in memoryview(self.auxiliary_bytes).cast("I"):
            digest.update(struct.pack("<I", int(mask)))
        return digest.hexdigest()

    def require_compatible(self, coefficients: Coefficients) -> None:
        """Fail closed instead of reusing this cache for an inactive family."""
        _require_active_slack_coefficients(coefficients)

    def require_instance(self, instance: Instance) -> None:
        """Reject width-compatible caches produced from different instance bytes."""
        if _domain_instance_digest(instance) != self.instance_sha256:
            raise ValueError("slack-domain cache is bound to a different instance")

    def require_canonical_energy_layout(self) -> None:
        """Bind the packed register partition to the accepted §5.2 evaluator."""
        if self.sector_count != 4:
            raise ValueError("canonical slack energy requires exactly four sector registers")
        if self.sector_slack_bits != canonical_energy.SECTOR_SLACK_BITS:
            raise ValueError("sector slack width does not match the canonical energy layout")
        if self.budget_slack_bits != canonical_energy.BUDGET_SLACK_BITS:
            raise ValueError("budget slack width does not match the canonical energy layout")
        if self.auxiliary_width != canonical_energy.SLACK_AUXILIARY_LENGTH:
            raise ValueError("auxiliary width does not match the canonical energy layout")


_PREPARED_DOMAIN_FACTORY_TOKEN = object()


@dataclass(frozen=True, init=False)
class PreparedDomainCache(Sequence[PreparedDecodedState | PreparedSlackState]):
    """Grid-independent prepared states aligned positionally with a raw domain."""

    raw_domain: Sequence
    states: tuple[PreparedDecodedState | PreparedSlackState, ...]
    encoding: str

    def __init__(
        self,
        raw_domain: Sequence,
        states: tuple[PreparedDecodedState | PreparedSlackState, ...],
        encoding: str,
        *,
        _factory_token: object = None,
    ) -> None:
        if _factory_token is not _PREPARED_DOMAIN_FACTORY_TOKEN:
            raise TypeError("prepared-domain caches must be created by a domain preparation service")
        object.__setattr__(self, "raw_domain", raw_domain)
        object.__setattr__(self, "states", states)
        object.__setattr__(self, "encoding", encoding)
        self.__post_init__()

    def __post_init__(self) -> None:
        if self.encoding not in ("slack", "unbalanced"):
            raise ValueError("unknown prepared-domain encoding")
        if len(self.raw_domain) != len(self.states) or not self.states:
            raise ValueError("prepared states must align with a nonempty raw domain")
        expected = PreparedSlackState if self.encoding == "slack" else PreparedDecodedState
        if any(not isinstance(state, expected) for state in self.states):
            raise TypeError("prepared-domain state type does not match its encoding")

    def __len__(self) -> int:
        return len(self.states)

    def __getitem__(self, index: int | slice):
        return self.states[index]

    def raw_state(self, index: int):
        return self.raw_domain[index]


def _make_prepared_domain_cache(
    raw_domain: Sequence,
    states: tuple[PreparedDecodedState | PreparedSlackState, ...],
    encoding: str,
) -> PreparedDomainCache:
    """The sole constructor boundary for positionally aligned prepared states."""
    return PreparedDomainCache(
        raw_domain, states, encoding, _factory_token=_PREPARED_DOMAIN_FACTORY_TOKEN
    )


def _require_active_slack_coefficients(coefficients: Coefficients) -> None:
    if not isinstance(coefficients, Coefficients):
        raise TypeError("coefficients must be a validated Coefficients instance")
    for name in ("sector_slack", "budget_slack"):
        value = getattr(coefficients, name)
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(
                f"{name} must be active and strictly positive; +0.0 invalidates the active-CSB cache"
            )


def _register_minimizers(residual: float, maximum: int) -> tuple[int, ...]:
    if not math.isfinite(residual):
        raise ValueError("slack residual must be finite")
    lower = math.floor(residual)
    candidates = {min(max(lower, 0), maximum), min(max(lower + 1, 0), maximum)}
    penalties = []
    for value in sorted(candidates):
        delta = residual - float(value)
        penalty = delta * delta
        if not math.isfinite(penalty):
            raise ValueError("nonfinite slack-minimizer penalty")
        penalties.append((value, penalty))
    minimum = min(penalty for _, penalty in penalties)
    return tuple(value for value, penalty in penalties if penalty == minimum)


def _toy_residuals(instance: Instance, x: tuple[int, ...]):
    """Residual transcript for isolated non-primary V-4 fixtures only."""
    if len(x) != len(instance.tickers):
        raise ValueError("toy decoded state width does not match its instance")
    xs = []
    for index, bit in enumerate(x):
        if bit not in (0, 1):
            raise ValueError(f"toy x[{index}] is not a bit")
        xs.append(float(bit))
    sector_residuals = []
    for j, members in enumerate(instance.sectors):
        sector_sum = +0.0
        for index in sorted(members):
            sector_sum = sector_sum + xs[index]
        residual = float(instance.C) - sector_sum
        if not math.isfinite(residual):
            raise ValueError(f"nonfinite toy sector residual {j}")
        sector_residuals.append(residual)
    budget_sum = +0.0
    for index, bit in enumerate(xs):
        spend = instance.prices[index] * bit
        budget_sum = budget_sum + spend
    budget_residual = instance.B - budget_sum
    if not math.isfinite(budget_residual):
        raise ValueError("nonfinite toy budget residual")
    return tuple(sector_residuals), budget_residual


def build_slack_domain_cache(
    instance: Instance,
    coefficients: Coefficients,
    sector_slack_bits: int = 2,
    budget_slack_bits: int = 11,
) -> SlackDomainCache:
    """Construct C_slack once for active CSB coefficients."""
    _require_active_slack_coefficients(coefficients)
    primary_schema = len(instance.tickers) == 20 and len(instance.sectors) == 4
    prepared_instance = prepare_instance(instance) if primary_schema else None
    if not isinstance(sector_slack_bits, int) or sector_slack_bits <= 0 or sector_slack_bits >= 32:
        raise ValueError("sector_slack_bits must be an integer in [1, 32)")
    if not isinstance(budget_slack_bits, int) or budget_slack_bits <= 0 or budget_slack_bits >= 32:
        raise ValueError("budget_slack_bits must be an integer in [1, 32)")
    auxiliary_width = len(instance.sectors) * sector_slack_bits + budget_slack_bits
    if auxiliary_width > 32:
        raise ValueError("packed auxiliary layout exceeds 32 bits")
    sector_max = (1 << sector_slack_bits) - 1
    budget_max = (1 << budget_slack_bits) - 1
    offsets = array("Q", [0])
    auxiliary_masks = array("I")

    for x in BinaryDomain(len(instance.tickers)):
        if prepared_instance is not None:
            xs = tuple(float(bit) for bit in x)
            _, h_sector, h_budget = canonical_energy._residuals_from_bits(
                prepared_instance.instance, xs
            )
        else:
            h_sector, h_budget = _toy_residuals(instance, x)
        sector_choices = tuple(_register_minimizers(value, sector_max) for value in h_sector)
        budget_choices = _register_minimizers(h_budget, budget_max)
        for values in itertools.product(*sector_choices, budget_choices):
            packed = 0
            offset = 0
            for value in values[:-1]:
                packed |= value << offset
                offset += sector_slack_bits
            packed |= values[-1] << offset
            auxiliary_masks.append(packed)
        offsets.append(len(auxiliary_masks))

    return SlackDomainCache(
        decoded_width=len(instance.tickers),
        sector_count=len(instance.sectors),
        sector_slack_bits=sector_slack_bits,
        budget_slack_bits=budget_slack_bits,
        auxiliary_width=auxiliary_width,
        offset_bytes=offsets.tobytes(),
        auxiliary_bytes=auxiliary_masks.tobytes(),
        activity_signature=(True, True),
        instance_sha256=_domain_instance_digest(instance),
    )


def prepare_unbalanced_domain(instance: Instance) -> PreparedDomainCache:
    """Prepare every decoded state once, outside every coefficient-grid loop."""
    prepared_instance = prepare_instance(instance)
    raw_domain = BinaryDomain(len(instance.tickers))
    states = tuple(prepare_decoded_state(prepared_instance, x) for x in raw_domain)
    return _make_prepared_domain_cache(raw_domain, states, "unbalanced")


def prepare_slack_domain(instance: Instance, domain: SlackDomainCache) -> PreparedDomainCache:
    """Prepare the cached active-CSB slack domain once, outside the grid loop."""
    if not isinstance(domain, SlackDomainCache):
        raise TypeError("domain must come from build_slack_domain_cache")
    if domain.decoded_width != len(instance.tickers):
        raise ValueError("slack-domain cache does not match the instance width")
    domain.require_instance(instance)
    domain.require_canonical_energy_layout()
    prepared_instance = prepare_instance(instance)
    raw_decoded = BinaryDomain(len(instance.tickers))
    decoded_states = tuple(
        prepare_decoded_state(prepared_instance, x) for x in raw_decoded
    )
    states = tuple(
        prepare_slack_state(decoded_states[decoded_mask], y)
        for decoded_mask, y in domain.iter_auxiliary_indexed()
    )
    return _make_prepared_domain_cache(domain, states, "slack")


@dataclass(frozen=True)
class PreparedDomainPair:
    """Both encodings prepared from one shared decoded-state transcript."""

    unbalanced: PreparedDomainCache
    slack: PreparedDomainCache

    def __post_init__(self) -> None:
        if self.unbalanced.encoding != "unbalanced" or self.slack.encoding != "slack":
            raise ValueError("prepared-domain pair has mismatched encodings")


def prepare_active_domains(
    instance: Instance, domain: SlackDomainCache
) -> PreparedDomainPair:
    """Prepare both full active-CSB domains while sharing every decoded state."""
    if not isinstance(domain, SlackDomainCache):
        raise TypeError("domain must come from build_slack_domain_cache")
    if domain.decoded_width != len(instance.tickers):
        raise ValueError("slack-domain cache does not match the instance width")
    domain.require_instance(instance)
    domain.require_canonical_energy_layout()

    prepared_instance = prepare_instance(instance)
    raw_decoded = BinaryDomain(len(instance.tickers))
    decoded_states = tuple(
        prepare_decoded_state(prepared_instance, x) for x in raw_decoded
    )
    slack_states = tuple(
        prepare_slack_state(decoded_states[decoded_mask], y)
        for decoded_mask, y in domain.iter_auxiliary_indexed()
    )
    return PreparedDomainPair(
        unbalanced=_make_prepared_domain_cache(
            raw_decoded, decoded_states, "unbalanced"
        ),
        slack=_make_prepared_domain_cache(domain, slack_states, "slack"),
    )


def prepare_fixture_domains(
    instance: Instance,
    raw_decoded: tuple[tuple[int, ...], ...],
    raw_slack: tuple[tuple[tuple[int, ...], tuple[int, ...]], ...],
) -> PreparedDomainPair:
    """Prepare an explicitly supplied bounded fixture through the same services."""
    if not isinstance(raw_decoded, tuple) or not raw_decoded:
        raise TypeError("fixture decoded domain must be a nonempty tuple")
    if not isinstance(raw_slack, tuple) or not raw_slack:
        raise TypeError("fixture slack domain must be a nonempty tuple")
    prepared_instance = prepare_instance(instance)
    decoded_states = tuple(
        prepare_decoded_state(prepared_instance, x) for x in raw_decoded
    )
    by_x = dict(zip(raw_decoded, decoded_states, strict=True))
    if len(by_x) != len(raw_decoded):
        raise ValueError("fixture decoded domain contains duplicate states")
    slack_states = []
    for x, y in raw_slack:
        decoded = by_x.get(x)
        if decoded is None:
            raise ValueError("fixture slack state is not aligned to the decoded domain")
        slack_states.append(prepare_slack_state(decoded, y))
    return PreparedDomainPair(
        unbalanced=_make_prepared_domain_cache(
            raw_decoded, decoded_states, "unbalanced"
        ),
        slack=_make_prepared_domain_cache(
            raw_slack, tuple(slack_states), "slack"
        ),
    )


def iter_unbalanced_domain(instance: Instance, coefficients: Coefficients):
    del coefficients
    yield from BinaryDomain(len(instance.tickers))


def iter_slack_domain(
    instance: Instance,
    coefficients: Coefficients,
    sector_slack_bits: int = 2,
    budget_slack_bits: int = 11,
):
    """Compatibility iterator; repeated callers should reuse the explicit cache."""
    yield from build_slack_domain_cache(
        instance, coefficients, sector_slack_bits, budget_slack_bits
    )
