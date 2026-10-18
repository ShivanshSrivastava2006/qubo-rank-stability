#!/usr/bin/env python3
"""Chunked, exact frozen-authority verifier for the core-stream engine.

Usage::

    verify_stage2_cuda_core_stream_engine_frozen_authority.py --chunk K/8

``K`` is 0..7 and the chunk covers the contiguous canonical decoded interval
``[floor(K * 2**20 / 8), floor((K + 1) * 2**20 / 8))``, together with exactly
the slack lifts those states own.  The eight chunks together compare every
decoded state and every corresponding slack lift exactly once: this is a split
of one exhaustive comparison, **not** a sample.

Each chunk independently computes, for its own interval, both the frozen
authority's values (``src.g4.energy`` / ``src.g5.domains``) and this
component's reference values, and compares them directly.  Nothing is accepted
because a pre-embedded digest matched; the printed chunk checksum is
diagnostic evidence only.  No file, cache or artifact is written, and each
chunk is independently runnable.

How a chunk-local run still proves a whole-domain claim.  The tie flags are
scored against the global minimum, which no single interval can derive.  The
chunk therefore recomputes the component's whole-domain claim itself, and then
proves it chunk-locally so the eight runs are jointly exhaustive:

* no word in this interval is strictly below the claimed minimum -- across the
  eight chunks this proves the claimed value is the true minimum;
* no position in this interval strictly before the claimed winner attains the
  minimum, and if the winner lies in this interval it does attain it -- across
  the eight chunks this proves the strict first-seen winner;
* every flag in this interval, recomputed from the frozen ``tau``, equals the
  component's flag, and the interval's per-``c_H`` tallies are printed so the
  eight chunk tallies sum to the whole-domain counts.

Per the component brief this verifier does not rebuild a whole-domain Python
lift cache inside the authority comparison: each state's lifts are
reconstructed directly from the frozen per-register rule.
"""
from __future__ import annotations

import itertools
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as engine  # noqa: E402
from src.g4.energy import (  # noqa: E402
    BUDGET_SLACK_BITS,
    SECTOR_SLACK_BITS,
    SLACK_AUXILIARY_LENGTH,
    prepare_coefficients,
    prepare_decoded_state,
    prepare_instance,
    prepare_slack_state,
    slack_energy_prepared,
    tau,
    unbalanced_energy_prepared,
)
from src.g4.instance import Instance  # noqa: E402
from src.g4.parameters import Coefficients  # noqa: E402
from src.g5.domains import BinaryDomain, _register_minimizers  # noqa: E402

CHUNK_COUNT = 8


class AuthorityError(RuntimeError):
    """Typed refusal: the component disagrees with the frozen authority."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuthorityError(message)


def chunk_bounds(chunk: int) -> tuple[int, int]:
    """The contiguous canonical decoded interval owned by one chunk."""
    require(type(chunk) is int and 0 <= chunk < CHUNK_COUNT, "chunk index is out of range")
    return ((chunk * engine.STATE_COUNT) // CHUNK_COUNT,
            ((chunk + 1) * engine.STATE_COUNT) // CHUNK_COUNT)


def parse_chunk(argv: list[str]) -> int:
    """Accept exactly '--chunk K/8' with K in 0..7; refuse every other syntax."""
    if len(argv) != 3 or argv[1] != "--chunk":
        raise AuthorityError(f"usage: --chunk K/{CHUNK_COUNT} with K in 0..{CHUNK_COUNT - 1}")
    parts = argv[2].split("/")
    if len(parts) != 2 or not parts[0].isdigit() or parts[1] != str(CHUNK_COUNT):
        raise AuthorityError(f"usage: --chunk K/{CHUNK_COUNT} with K in 0..{CHUNK_COUNT - 1}")
    chunk = int(parts[0])
    # Demand the canonical spelling exactly: '00/8' or '+0/8' is not chunk 0.
    if chunk >= CHUNK_COUNT or argv[2] != f"{chunk}/{CHUNK_COUNT}":
        raise AuthorityError(f"usage: --chunk K/{CHUNK_COUNT} with K in 0..{CHUNK_COUNT - 1}")
    return chunk


def frozen_instance(payload) -> Instance:
    return Instance(
        tickers=tuple(f"SYN{index:02d}" for index in range(engine.ASSET_COUNT)),
        sectors=tuple(tuple(block) for block in payload["sectors"]),
        mu=tuple(payload["mu"]),
        sigma=tuple(tuple(row) for row in payload["sigma"]),
        prices=tuple(payload["prices"]),
        kappa_risk=float(payload["kappa_risk"]),
        K=int(payload["k"]),
        C=int(payload["c"]),
        B=float(payload["b"]),
    )


def frozen_coefficients(row: str) -> Coefficients:
    values = engine.coefficient_row(row)
    return Coefficients(**{field: values[field] for field in engine.COEFFICIENT_FIELDS})


def _fnv(state: int, word: int) -> int:
    return ((state ^ word) * engine.FNV_PRIME) & engine.MASK64


def interval_natural(domain, row, encoding, first, last):
    """Yield exactly this interval's words of the stream ``scan`` consumes.

    This is ``natural_energies`` itself -- the implementation the component
    actually uses -- not a substitute helper, so every word it yields is
    compared against an independently reconstructed frozen-authority engine.
    """
    for position, value in enumerate(engine.natural_energies(domain, row, encoding)):
        if position < first:
            continue
        if position >= last:
            return
        yield value


def authority_packed_masks(register_values):
    """Frozen 19-bit packed masks, derived here from the frozen ledger alone.

    Register order is sector 0 slowest ... budget fastest.  The bit offsets are
    rebuilt from ``src.g4.energy``'s own layout constants rather than from the
    component's ``register_offset``, so the component cannot define its own
    layout into agreement.
    """
    for combination in itertools.product(*register_values):
        mask = 0
        for register, value in enumerate(combination):
            offset = (register * SECTOR_SLACK_BITS if register < engine.SECTOR_COUNT
                      else engine.SECTOR_COUNT * SECTOR_SLACK_BITS)
            mask |= value << offset
        yield mask


def interval_words(domain, row, encoding, first, last, natural_minimum, control):
    """Yield this interval's controlled words without retaining the rest."""
    for position, value in enumerate(engine.natural_energies(domain, row, encoding)):
        if position < first:
            continue
        if position >= last:
            return
        yield natural_minimum + control[position] if position in control else value


def main(argv: list[str]) -> int:
    try:
        chunk = parse_chunk(argv)
    except AuthorityError as error:
        print(str(error), file=sys.stderr)
        return 2
    start, stop = chunk_bounds(chunk)

    payload = engine.validate_payload(engine.synthetic_payload())
    # The instance's own lambda_ref drives every D015 comparison below.
    lambda_ref = payload["lambda_ref"]
    require(isinstance(lambda_ref, float) and lambda_ref > 0.0,
            "the payload carries no usable lambda_ref")
    require(not engine.is_contiguous_membership(payload["sectors"]),
            "the anchored partition must be non-contiguous")
    require(engine.SECTOR_SLACK_BITS == SECTOR_SLACK_BITS
            and engine.BUDGET_SLACK_BITS == BUDGET_SLACK_BITS
            and engine.AUXILIARY_BITS == SLACK_AUXILIARY_LENGTH,
            "slack layout constants differ from the frozen ledger")

    # The component's own whole-domain claim, recomputed here; the chunk then
    # proves it over its interval.
    domain = engine.build_domain(engine.synthetic_payload())
    scans = {(row, encoding): engine.scan(domain, row, encoding)
             for row in engine.ROW_NAMES for encoding in engine.ENCODINGS}
    # The control-free generic path is bound against the frozen authority too:
    # its flags are scored against the natural minimum, and its compaction is
    # a different stream from the controlled one.
    generic = {(row, encoding): engine.scan(domain, engine.coefficient_row(row), encoding,
                                            control={})
               for row in engine.ROW_NAMES for encoding in engine.ENCODINGS}

    prepared_instance = prepare_instance(frozen_instance(payload))
    prepared_rows = {row: prepare_coefficients(frozen_coefficients(row)) for row in engine.ROW_NAMES}
    coefficient_values = {row: engine.coefficient_row(row) for row in engine.ROW_NAMES}
    binary_domain = BinaryDomain(engine.ASSET_COUNT)
    sector_max = engine.register_maximum(0)
    budget_max = engine.register_maximum(engine.SECTOR_COUNT)

    digest = _fnv(_fnv(engine.FNV_OFFSET, chunk), CHUNK_COUNT)
    digest = _fnv(_fnv(digest, start), stop)
    states = registers = compared_words = flags_compared = interval_lifts = 0
    compacted_here = 0
    masks_compared = 0
    authority_mask_digest = component_mask_digest = engine.FNV_OFFSET
    per_ch = {key: [0, 0, 0] for key in scans}

    # The exact streams scan() consumes, positioned on this chunk's interval,
    # advanced in lockstep with the frozen reconstruction below.
    slack_first = int(domain["offsets"][start])
    slack_last = int(domain["offsets"][stop])
    streams = {}
    for row in engine.ROW_NAMES:
        streams[(row, "unbalanced")] = interval_natural(domain, row, "unbalanced", start, stop)
        streams[(row, "slack")] = interval_natural(domain, row, "slack", slack_first, slack_last)
    stream_words = 0

    for index in range(start, stop):
        bits = binary_domain[index]
        require(engine.canonical_bits(index) == bits,
                f"canonical order differs from BinaryDomain at {index}")

        frozen_decoded = prepare_decoded_state(prepared_instance, bits)
        mine = engine.prepared_terms(payload, index)
        frozen_terms = (frozen_decoded.f_value, frozen_decoded.card_square,
                        *frozen_decoded.h_sector, *frozen_decoded.sector_square,
                        frozen_decoded.h_budget, frozen_decoded.budget_square)
        require(len(mine) == len(frozen_terms), f"prepared arity differs at {index}")
        for slot, (left, right) in enumerate(zip(mine, frozen_terms)):
            require(left == right, f"prepared term {slot} differs from src.g4.energy at {index}")
        require(domain["objective"][index] == frozen_decoded.f_value,
                f"the cached objective differs from src.g4.energy at {index}")
        require(domain["card_square"][index] == frozen_decoded.card_square,
                f"the cached card square differs from src.g4.energy at {index}")
        for sector in range(engine.SECTOR_COUNT):
            require(domain["sector_residual"][sector][index] == frozen_decoded.h_sector[sector],
                    f"the cached sector[{sector}] residual differs at {index}")
            require(domain["sector_square"][sector][index] == frozen_decoded.sector_square[sector],
                    f"the cached sector[{sector}] square differs at {index}")
        require(domain["budget_residual"][index] == frozen_decoded.h_budget,
                f"the cached budget residual differs at {index}")
        require(domain["budget_square"][index] == frozen_decoded.budget_square,
                f"the cached budget square differs at {index}")
        states += 1

        # Registers and every lift of this state, straight from the frozen rule.
        sector_values = []
        for sector in range(engine.SECTOR_COUNT):
            residual = frozen_decoded.h_sector[sector]
            frozen_min = _register_minimizers(residual, sector_max)
            mine_min = engine.register_minimizers(residual, sector_max)
            require(tuple(value for value, _ in mine_min) == frozen_min,
                    f"sector[{sector}] minimizers differ from src.g5.domains at {index}")
            # Integer sector residuals cannot tie; the lift multiplicity below
            # relies on that, so it is asserted rather than assumed.
            require(len(frozen_min) == 1,
                    f"sector[{sector}] register unexpectedly tied at {index}")
            require(domain["sector_penalty"][sector][index] == mine_min[0][1],
                    f"the cached sector[{sector}] penalty differs at {index}")
            sector_values.append(frozen_min[0])
            registers += 1
        frozen_budget = _register_minimizers(frozen_decoded.h_budget, budget_max)
        mine_budget = engine.register_minimizers(frozen_decoded.h_budget, budget_max)
        require(tuple(value for value, _ in mine_budget) == frozen_budget,
                f"budget minimizers differ from src.g5.domains at {index}")
        require(tuple(domain["budget_penalties"][index]) == tuple(p for _, p in mine_budget),
                f"the cached budget penalties differ at {index}")
        registers += 1
        require(domain["lift_counts"][index] == len(frozen_budget),
                f"the cached lift multiplicity differs at {index}")
        interval_lifts += len(frozen_budget)

        # The packed 19-bit lift sequence, in declared Cartesian-product order.
        # Tied budget minimizers carry EQUAL penalties, so an inverted or
        # dropped tied mask leaves every energy word untouched; only this
        # comparison binds the order, the bit positions and the retention.
        authority_values = tuple(
            _register_minimizers(frozen_decoded.h_sector[sector], sector_max)
            for sector in range(engine.SECTOR_COUNT)) + (frozen_budget,)
        authority_masks = tuple(authority_packed_masks(authority_values))
        component_masks = tuple(engine.packed_lift_masks(
            engine.register_values_for_state(
                [domain["sector_residual"][sector][index]
                 for sector in range(engine.SECTOR_COUNT)],
                domain["budget_residual"][index])))
        require(len(authority_masks) == len(frozen_budget),
                f"the frozen product order yields the wrong multiplicity at {index}")
        require(len(component_masks) == len(authority_masks),
                f"the component produced the wrong lift multiplicity at {index}: "
                f"{len(component_masks)} masks for {len(authority_masks)} frozen lifts")
        require(component_masks == authority_masks,
                f"the packed lift masks differ from the frozen layout at {index}")
        require(int(domain["offsets"][index + 1]) - int(domain["offsets"][index])
                == len(authority_masks),
                f"the cached offsets disagree with the lift multiplicity at {index}")
        for mask in authority_masks:
            authority_mask_digest = _fnv(authority_mask_digest, mask)
        for mask in component_masks:
            component_mask_digest = _fnv(component_mask_digest, mask)
            digest = _fnv(digest, mask)
            masks_compared += 1

        sector_auxiliary = []
        for sector in range(engine.SECTOR_COUNT):
            sector_auxiliary.extend((sector_values[sector] >> bit) & 1
                                    for bit in range(SECTOR_SLACK_BITS))

        for row in engine.ROW_NAMES:
            prepared = prepared_rows[row]
            values = coefficient_values[row]
            frozen_value = unbalanced_energy_prepared(frozen_decoded, prepared)
            mine_value = engine.unbalanced_energy(mine, values)
            require(mine_value == frozen_value,
                    f"unbalanced energy differs from src.g4.energy at {index} ({row})")
            streamed = next(streams[(row, "unbalanced")], None)
            require(streamed is not None,
                    f"natural_energies ended early at {index} ({row}/unbalanced)")
            require(streamed == frozen_value,
                    f"natural_energies differs from src.g4.energy at {index} ({row}/unbalanced)")
            stream_words += 1
            compared_words += 1
            digest = _fnv(digest, engine._word(frozen_value))

            for lift, budget_value in enumerate(frozen_budget):
                auxiliary = tuple(sector_auxiliary
                                  + [(budget_value >> bit) & 1 for bit in range(BUDGET_SLACK_BITS)])
                frozen_slack_state = prepare_slack_state(frozen_decoded, auxiliary)
                frozen_slack = slack_energy_prepared(frozen_slack_state, prepared)
                squares = (*frozen_slack_state.sector_slack_square,
                           frozen_slack_state.budget_slack_square)
                mine_slack = engine.slack_energy(mine, squares, values)
                require(mine_slack == frozen_slack,
                        f"slack energy differs from src.g4.energy at {index} lift {lift} ({row})")
                streamed = next(streams[(row, "slack")], None)
                require(streamed is not None,
                        f"natural_energies ended early at {index} lift {lift} ({row}/slack)")
                require(streamed == frozen_slack,
                        f"natural_energies differs from src.g4.energy at {index} "
                        f"lift {lift} ({row}/slack)")
                stream_words += 1
                compared_words += 1
                digest = _fnv(digest, engine._word(frozen_slack))

    # Every stream must be exactly exhausted: no extra word, none missing.
    for (row, encoding), stream in streams.items():
        require(next(stream, None) is None,
                f"natural_energies yielded more words than the interval owns ({row}/{encoding})")
    require(stream_words == compared_words,
            "the consumed stream and the frozen reconstruction fell out of lockstep")
    require(authority_mask_digest == component_mask_digest,
            "the packed lift-mask digests disagree")
    builder_digest, builder_masks = engine.lift_mask_digest(domain, start, stop)
    require(builder_digest == authority_mask_digest and builder_masks == masks_compared,
            "the builder's own lift-mask digest disagrees with the frozen layout")

    # Chunk-local proof of the whole-domain minima, winners and flags.
    for row in engine.ROW_NAMES:
        for encoding in engine.ENCODINGS:
          for mode in ("controlled", "generic"):
            data = scans[(row, encoding)] if mode == "controlled" else generic[(row, encoding)]
            claimed_minimum = data["minimum"]
            claimed_index = data["minimum_index"]
            control = (dict(zip(engine.CONTROL_POSITIONS[encoding],
                                engine.control_offsets(row, encoding)))
                       if mode == "controlled" else {})
            if encoding == "unbalanced":
                first, last = start, stop
            else:
                first, last = int(domain["offsets"][start]), int(domain["offsets"][stop])
            attained_before_winner = 0
            winner_here = False
            expected_entries = []
            for offset, value in enumerate(interval_words(domain, row, encoding, first, last,
                                                          claimed_minimum, control)):
                position = first + offset
                require(not (value < claimed_minimum),
                        f"{row}/{encoding}/{mode}: a word below the claimed minimum at {position}")
                if value == claimed_minimum:
                    if position < claimed_index:
                        attained_before_winner += 1
                    elif position == claimed_index:
                        winner_here = True
                flags = engine.tie_flags(value, claimed_minimum, lambda_ref)
                expected = 0
                for bit, c_h in enumerate(engine.CH_VALUES):
                    if abs(value - claimed_minimum) <= tau(value, claimed_minimum,
                                                           lambda_ref, c_h):
                        expected |= 1 << bit
                require(flags == expected,
                        f"{row}/{encoding}/{mode}: flag at {position} differs from src.g4.engine.tau")
                if flags:
                    require(flags in engine.COMPACTED_FLAGS,
                            f"{row}/{encoding}/{mode}: a flagged entry at {position} is not in {{4,6,7}}")
                    expected_entries.append((flags << 32) | position)
                for bit in range(len(engine.CH_VALUES)):
                    if flags & (1 << bit):
                        per_ch[(row, encoding)][bit] += 1
                flags_compared += 1
                digest = _fnv(digest, flags)
            require(flags_compared > 0, f"{row}/{encoding}/{mode}: the interval produced no words")
            # The compacted stream restricted to this interval must BE the
            # flagged subsequence, in ascending canonical order, seated at the
            # exclusive prefix the earlier intervals imply.  Across the eight
            # chunks this binds order, prefix, drops and duplicates exactly.
            entries = list(data["compacted_entries"])
            carried = [int(entry & 0xFFFFFFFF) for entry in entries]
            require(carried == sorted(set(carried)),
                    f"{row}/{encoding}/{mode}: the compacted stream is not strictly ascending")
            before = sum(1 for held in carried if held < first)
            inside = [entry for entry, held in zip(entries, carried) if first <= held < last]
            require(entries[before:before + len(inside)] == inside,
                    f"{row}/{encoding}/{mode}: this interval's entries are not contiguous in the stream")
            require(inside == expected_entries,
                    f"{row}/{encoding}/{mode}: the compacted entries differ from the flagged subsequence "
                    f"({len(inside)} held vs {len(expected_entries)} frozen)")
            compacted_here += len(inside)
            # Per-compaction-chunk counts, for the chunks this interval owns.
            size = engine.COMPACTION_CHUNK_SIZE
            counts = data["compaction_counts"]
            for compaction_chunk in range(len(counts)):
                low = compaction_chunk * size
                high = low + size
                # Only chunks wholly inside this interval: the slack stream's
                # bounds are lift offsets and need not be 4096-aligned, so a
                # straddling chunk is owned by no single interval.  The
                # elementwise comparison above already binds every entry.
                if low < first or high > last:
                    continue
                owned = sum(1 for entry in expected_entries
                            if low <= (entry & 0xFFFFFFFF) < high)
                require(counts[compaction_chunk] == owned,
                        f"{row}/{encoding}/{mode}: compaction chunk {compaction_chunk} counted "
                        f"{counts[compaction_chunk]}, frozen says {owned}")
            require(attained_before_winner == 0,
                    f"{row}/{encoding}/{mode}: the claimed first-seen winner is preceded in this chunk")
            if first <= claimed_index < last:
                require(winner_here,
                        f"{row}/{encoding}/{mode}: the claimed winner does not attain the minimum")

    tallies = " ".join(f"{row}/{encoding}={tuple(per_ch[(row, encoding)])}"
                       for row in engine.ROW_NAMES for encoding in engine.ENCODINGS)
    print(f"PASS chunk {chunk}/{CHUNK_COUNT} states [{start},{stop}) lifts {interval_lifts} "
          f"prepared {states} registers {registers} energy_words {compared_words} "
          f"streamed {stream_words} masks {masks_compared} "
          f"flags {flags_compared} compacted {compacted_here} "
          f"per_c_h {tallies} chunk_checksum {digest:016x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
