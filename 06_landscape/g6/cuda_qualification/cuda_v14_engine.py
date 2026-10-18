"""Independent CUDA/T4 full-domain V-14 validation-and-throughput engine (non-value).

Owner authorization (2026-09-20) permits implementation and NON-VALUE
validation of this engine using the already-qualified unbalanced and slack
energy transcripts.  It may emit only validation pass/fail, mismatch
counters, coordinate/evaluation counts, exact elapsed times, and
platform/toolchain/source/domain identities.  It never emits or retains an
energy, minimum, tie set or size, decoded state, label, rate, V-14
comparison, or conclusion; such values exist only in process memory and in
the automatically removed temporary directory during a run.

Correspondence with the accepted Gate-5 prepared-domain computation
(``src/g5/domains.py``, ``src/g4/energy.py``, ``src/g5/certify.py``):

* unbalanced domain: ``BinaryDomain(20)`` order, 2^20 logical states;
* slack domain: the canonical active-CSB ``SlackDomainCache`` from
  ``build_slack_domain_cache`` (bounded register minimizers, boundary lifts
  included), iterated in ``iter_auxiliary_indexed`` order, one prepared
  logical state per cache entry; its ``logical_sha256`` and entry count are
  pinned and re-derived on every plan/run;
* CPU reference energies come only from ``prepare_decoded_state`` /
  ``prepare_slack_state`` / ``unbalanced_energy_prepared`` /
  ``slack_energy_prepared``, the same services ``prepare_active_domains``
  composes, applied in the same order;
* the device reduction (first-seen strict minimum, D015 tie flags at c_H in
  {1024, 2048, 4096}) is compared against a CPU transcription of
  ``certify_prepared_domain`` / ``certify_prepared_domain_multi_ch`` using
  canonical ``energy.tau``; only a mismatch counter leaves the process.

Prerequisites, bound not substituted: the passed unbalanced and slack CUDA/T4
qualification records are required inputs; their identities are re-derived,
must agree with each other, and must equal the platform observed at run
time.  Importing this module has no side effects and writes nothing.
"""

from __future__ import annotations

from array import array
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g6.cuda_qualification import cuda_energy_crosscheck as cuda_unbalanced  # noqa: E402
from research.g6.cuda_qualification import cuda_slack_energy_crosscheck as cuda_slack  # noqa: E402
from src.g4.energy import (  # noqa: E402
    EPSILON,
    prepare_coefficients,
    prepare_decoded_state,
    prepare_instance,
    prepare_slack_state,
    slack_energy_prepared,
    tau,
    unbalanced_energy_prepared,
)
from src.g4.instance import Instance, load_instance  # noqa: E402
from src.g4.parameters import Coefficients  # noqa: E402
from src.g5.domains import BinaryDomain, SlackDomainCache, build_slack_domain_cache  # noqa: E402
from src.g6.ledgers import validate_preexecution_ledger  # noqa: E402


SCHEMA_PLAN = "decisions_os/g6_cuda_t4_v14_engine_plan/v1"
SCHEMA_VALIDATE = "decisions_os/g6_cuda_t4_v14_engine_validation_run/v1"
SCHEMA_THROUGHPUT_RUN = "decisions_os/g6_cuda_t4_v14_engine_throughput_run/v1"
# Must equal v14_batch_contract.SCHEMA_THROUGHPUT (asserted by the fixtures).
SCHEMA_THROUGHPUT_MEASUREMENT = "decisions_os/g6_v14_cuda_t4_throughput_measurement/v1"
PURPOSE = ("non-value CUDA/T4 full-domain V-14 engine: validation counters, throughput, and identities only; "
           "no energy, minimum, tie set, label, rate, comparison, or conclusion")
TRACK = "cuda-t4"
PROBE = "v14_prepared_domain_engine_cuda"
BACKEND = cuda_unbalanced.BACKEND
COMPILE_FLAGS = cuda_unbalanced.COMPILE_FLAGS
CH_VALUES = (1024, 2048, 4096)
DECODED_WIDTH = 20
DECODED_COUNT = 1 << DECODED_WIDTH
PARTIAL_COUNT = 4096
MAX_COORDINATES_PER_INVOCATION = 4096
LINEAR_ORDER = "linear = card * N^2 + sector * N + budget; N = axis_count; range = [start, stop)"
DECODED_ORDER = "src.g5.domains.BinaryDomain: x[i] = (index >> (19 - i)) & 1; the device reverses 20 bits into the qualified little-endian mask"
INPUT_MAGIC = int.from_bytes(b"G6V14PX1", "little")
OUTPUT_MAGIC = int.from_bytes(b"G6V14PY1", "little")
FORMAT_VERSION = 1
MODE_VALIDATE, MODE_THROUGHPUT = 0, 1
COEFFICIENT_ORDER = ("alpha", "sector_slack", "budget_slack", "sector_linear", "sector_quadratic",
                     "budget_linear", "budget_quadratic")

# Canonical active-CSB slack domain identity on the accepted instance
# (re-derived from build_slack_domain_cache on every plan/run; drift refuses).
EXPECTED_SLACK_DOMAIN = {"entries": 1048576,
                         "logical_sha256": "d052e67892d0e39882db26798f881628480d83c0119ee3a1e2ba9b1cdcf03063"}

SCALES = {"0.5x": {"file": "v14_expansion_0_5x.json", "pass_id": "v14_expansion_0.5x", "axis_count": 31},
          "2x": {"file": "v14_expansion_2x.json", "pass_id": "v14_expansion_2x", "axis_count": 111}}
# Fixed, declared validation coordinates (scale, (card, sector, budget)):
# both scales, all-axis endpoints, an interior all-axis row, the embedded
# primary coordinate, and one mixed-axis point per scale.  Never adaptive.
VALIDATION_COORDINATES: tuple[tuple[str, tuple[int, int, int]], ...] = (
    ("0.5x", (0, 0, 0)), ("0.5x", (15, 15, 15)), ("0.5x", (30, 30, 30)), ("0.5x", (30, 0, 15)),
    ("2x", (0, 0, 0)), ("2x", (70, 70, 70)), ("2x", (110, 110, 110)), ("2x", (110, 0, 55)),
)

LEDGER_DIR_REL = "research/g6/preexecution_ledgers"
MANIFEST_REL = f"{LEDGER_DIR_REL}/manifest.json"
INSTANCE_REL = "research/canonical/stage1_instance.json"
CUDA_SOURCE_REL = "research/g6/cuda_qualification/cuda_v14_prepared_domain_engine.cu"
PINNED_INPUTS: dict[str, str] = {
    "src/g4/energy.py": "0ba83c0d33e0d2996352370e26bf0e782002ec49cb79e1628b74a2a74dd5fa11",
    "src/g4/instance.py": "645419374fd30891c2f9ff14d030ed65a032d52d8fe88fab068ad23417b58187",
    "src/g4/parameters.py": "cbbdebbe44b9af0d47fa1d5da7e00303e492d70d21abd696e6bdd5a4cd5be97c",
    "src/g5/domains.py": "89d3b1cadf660ec7ea4a127af09a73073afb03d5c78a74e7a15b5808999dadf7",
    "src/g5/certify.py": "018b0a67ae1d1fdf8cf797cd38296ed0a98ec3bd0d2e5c1124dc51e36e614d64",
    "src/g6/ledgers.py": "40ff906fdedb526f7063c7d40aeb778335cf49291a47a948d9f5b31620fc0723",
    INSTANCE_REL: "c4615d9b5066597c4754a1e06d2b3a7906c218965a7d6d530cf54f75c4b5f243",
    MANIFEST_REL: "900b639509074114b4be1149dfaef7d14b6e4ba4a7c1fbcf90d719057a0611ca",
    f"{LEDGER_DIR_REL}/v14_expansion_0_5x.json": "90ad1a7b7af8b41714c6edcc6659ac77d5774e937730d051afc0ed49ac33bff9",
    f"{LEDGER_DIR_REL}/v14_expansion_2x.json": "3bd7341a7dcf8ca5de007cf2d92ab89e64e95b887349df8e7dede0cc5b0ec3ea",
    "research/g6/cuda_qualification/cuda_energy_crosscheck.py": "cf826736cf2c1dafca03b0d2e8c31cf6d9ed5a86eee961bc84345669698dc2f1",
    "research/g6/cuda_qualification/cuda_slack_energy_crosscheck.py": "2d37973f61bc79d13219b0db4f5451b96d214f2e8598f3f47b204f6b72571816",
    "research/g6/cuda_qualification/cuda_unbalanced_energy_crosscheck.cu": "006421acc9bb61b92df3a45189c734977f6459b092909a821e6e52855a357e1c",
    "research/g6/cuda_qualification/cuda_slack_energy_crosscheck.cu": "9661374be597dfd17f9eb2a983124c0e9d44ccd70e1ff48a11f3036736a4af54",
    CUDA_SOURCE_REL: "671299980835776a9ade31a835765af37f503a2d469b52702d21478380c16d54",
}
SELF_RELATIVES = ("research/g6/cuda_qualification/cuda_v14_engine.py", "research/g6/run_cuda_v14_engine.py")
COMPILE_TIMEOUT_SECONDS = 900
EXECUTE_TIMEOUT_SECONDS = 3600 * 4


class EngineError(RuntimeError):
    """Raised when the engine contract cannot be established."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EngineError(message)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _shared(function: Callable, *arguments):
    try:
        return function(*arguments)
    except (cuda_unbalanced.CrosscheckError, cuda_slack.CrosscheckError) as exc:
        raise EngineError(str(exc)) from exc


def current_hashes(relatives: Sequence[str]) -> dict[str, str]:
    return _shared(cuda_unbalanced.current_hashes, tuple(relatives))


def verify_pinned_inputs(expected: Mapping[str, str] | None = None) -> dict[str, str]:
    pins = dict(PINNED_INPUTS if expected is None else expected)
    observed = current_hashes(tuple(pins))
    drifted = sorted(relative for relative in pins if observed[relative] != pins[relative])
    _require(not drifted, "pinned input drift: " + ", ".join(drifted))
    return observed


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EngineError(f"{label} is unreadable JSON") from exc
    _require(isinstance(payload, dict), f"{label} must be a JSON object")
    return payload


# --------------------------------------------------------------------------
# Ledgers, coordinates, coefficients
# --------------------------------------------------------------------------

def load_ledgers() -> dict[str, dict[str, Any]]:
    """Both reviewed V-14 ledgers through the manifest and transcript replay."""
    manifest = _read_json(ROOT / MANIFEST_REL, "preexecution-ledger manifest")
    body = {key: value for key, value in manifest.items() if key != "content_sha256"}
    _require(manifest.get("content_sha256") == _sha256_bytes(canonical_bytes(body)), "manifest content hash mismatch")
    listed = manifest.get("ledgers")
    _require(isinstance(listed, dict), "malformed preexecution-ledger manifest")
    output: dict[str, dict[str, Any]] = {}
    for scale, choice in SCALES.items():
        relative = f"{LEDGER_DIR_REL}/{choice['file']}"
        entry = listed.get(choice["file"])
        _require(isinstance(entry, dict) and entry.get("file_sha256") == PINNED_INPUTS[relative]
                 == current_hashes((relative,))[relative], f"ledger file identity mismatch: {scale}")
        payload = _read_json(ROOT / relative, choice["file"])
        _require(payload.get("content_sha256") == entry.get("content_sha256"), f"ledger content identity mismatch: {scale}")
        try:
            validate_preexecution_ledger(payload)
        except Exception as exc:
            raise EngineError(f"ledger fails transcript replay: {scale}") from exc
        _require(payload.get("pass_id") == choice["pass_id"] and len(payload["coordinates"]) == choice["axis_count"],
                 f"V-14 {scale} ledger shape drift")
        output[scale] = payload
    return output


def lambda_ref_from(ledgers: Mapping[str, Mapping[str, Any]]) -> float:
    values = {float.fromhex(ledger["inputs"]["lambda_ref_binary64_hex"]) for ledger in ledgers.values()}
    _require(len(values) == 1, "V-14 ledgers disagree on Lambda_ref")
    value = values.pop()
    _require(math.isfinite(value) and value > 0.0, "Lambda_ref must be finite and strictly positive")
    return value


def linear_index(card: int, sector: int, budget: int, axis_count: int) -> int:
    for label, value in (("card", card), ("sector", sector), ("budget", budget)):
        _require(isinstance(value, int) and 0 <= value < axis_count, f"{label} index outside the axis")
    return card * axis_count * axis_count + sector * axis_count + budget


def coordinate_at(linear: int, axis_count: int) -> tuple[int, int, int]:
    _require(isinstance(linear, int) and 0 <= linear < axis_count ** 3, "linear index outside the grid")
    card, remainder = divmod(linear, axis_count * axis_count)
    sector, budget = divmod(remainder, axis_count)
    return card, sector, budget


def coefficients_at(ledger: Mapping[str, Any], card: int, sector: int, budget: int) -> Coefficients:
    """Per-family row mapping, transcribed from src/g6/d011_runner.py::_coefficient_at."""
    rows = ledger.get("coefficient_ledger")
    _require(isinstance(rows, dict), "coefficient ledger is malformed")
    try:
        card_row, sector_row, budget_row = rows["cardinality"][card], rows["sector"][sector], rows["budget"][budget]
        _require(card_row["index"] == card and sector_row["index"] == sector and budget_row["index"] == budget,
                 "coefficient rows are misaligned")
        values = Coefficients(
            alpha=float.fromhex(card_row["alpha_hex"]),
            sector_slack=float.fromhex(sector_row["lambda_slack_hex"]),
            budget_slack=float.fromhex(budget_row["lambda_slack_hex"]),
            sector_linear=float.fromhex(sector_row["lambda_1_hex"]),
            sector_quadratic=float.fromhex(sector_row["lambda_2_hex"]),
            budget_linear=float.fromhex(budget_row["lambda_1_hex"]),
            budget_quadratic=float.fromhex(budget_row["lambda_2_hex"]),
        )
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise EngineError("coefficient ledger row is malformed") from exc
    prepare_coefficients(values)
    return values


def validation_points(ledgers: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    points = []
    for scale, (card, sector, budget) in VALIDATION_COORDINATES:
        axis_count = SCALES[scale]["axis_count"]
        points.append({
            "scale": scale, "pass_id": SCALES[scale]["pass_id"],
            "coordinate": {"card": card, "sector": sector, "budget": budget},
            "linear": linear_index(card, sector, budget, axis_count),
            "coefficients": coefficients_at(ledgers[scale], card, sector, budget),
        })
    return points


def range_points(ledgers: Mapping[str, Mapping[str, Any]], scale: str, start: int, stop: int) -> list[dict[str, Any]]:
    _require(scale in SCALES, "scale must be '0.5x' or '2x'")
    axis_count = SCALES[scale]["axis_count"]
    _require(isinstance(start, int) and isinstance(stop, int) and 0 <= start < stop <= axis_count ** 3,
             "throughput range must be a non-empty half-open range inside the grid")
    _require(stop - start <= MAX_COORDINATES_PER_INVOCATION,
             f"throughput range exceeds {MAX_COORDINATES_PER_INVOCATION} coordinates")
    points = []
    for linear in range(start, stop):
        card, sector, budget = coordinate_at(linear, axis_count)
        points.append({"scale": scale, "pass_id": SCALES[scale]["pass_id"],
                       "coordinate": {"card": card, "sector": sector, "budget": budget}, "linear": linear,
                       "coefficients": coefficients_at(ledgers[scale], card, sector, budget)})
    return points


def validation_coordinates_sha256() -> str:
    return _sha256_bytes(canonical_bytes({"coordinates": [[scale, list(triple)] for scale, triple in VALIDATION_COORDINATES]}))


def _point_report(point: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in point.items() if key != "coefficients"}


# --------------------------------------------------------------------------
# Canonical domains
# --------------------------------------------------------------------------

def build_slack_domain(instance: Instance) -> SlackDomainCache:
    """The canonical active-CSB slack cache; identity re-derived and pinned."""
    cache = build_slack_domain_cache(instance, Coefficients(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0))
    cache.require_instance(instance)
    cache.require_canonical_energy_layout()
    _require(cache.decoded_width == DECODED_WIDTH, "slack domain decoded width drift")
    _require(len(cache) == EXPECTED_SLACK_DOMAIN["entries"], "canonical slack domain entry count drift")
    _require(cache.logical_sha256() == EXPECTED_SLACK_DOMAIN["logical_sha256"], "canonical slack domain logical digest drift")
    return cache


def domain_identity(cache: SlackDomainCache) -> dict[str, Any]:
    return {
        "unbalanced": {"order": DECODED_ORDER, "width": DECODED_WIDTH, "count": DECODED_COUNT},
        "slack": {"source": "src.g5.domains.build_slack_domain_cache (active-CSB, bounded register minimizers)",
                  "order": "SlackDomainCache.iter_auxiliary_indexed: decoded index major, cached lift order",
                  "entries": len(cache), "logical_sha256": cache.logical_sha256(),
                  "instance_sha256": cache.instance_sha256,
                  "register_widths": {"sector": cache.sector_slack_bits, "budget": cache.budget_slack_bits}},
    }


def canonical_index_to_mask(index: int) -> int:
    """BinaryDomain index -> little-endian mask the qualified transcript consumes."""
    _require(isinstance(index, int) and 0 <= index < DECODED_COUNT, "decoded index outside the domain")
    mask = 0
    for i in range(DECODED_WIDTH):
        mask |= ((index >> (DECODED_WIDTH - 1 - i)) & 1) << i
    return mask


def float_bits(value: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def bits_float(word: int) -> float:
    return struct.unpack("<d", struct.pack("<Q", word))[0]


def cpu_reference(instance: Instance, points: Sequence[Mapping[str, Any]], cache: SlackDomainCache,
                  decoded_indices: Sequence[int] | None = None) -> tuple[list[dict[int, int]], list[dict[int, int]]]:
    """Canonical prepared-domain energies, streamed in canonical order.

    Returns, per point, ``{decoded_index: word}`` and ``{slack_entry: word}``
    for every decoded index in ``decoded_indices`` (default: the full 2^20
    domain) and every cached lift of those decoded states.  Values never
    leave process memory.
    """
    prepared_instance = prepare_instance(instance)
    prepared = [prepare_coefficients(point["coefficients"]) for point in points]
    domain = BinaryDomain(DECODED_WIDTH)
    offsets = memoryview(cache.offset_bytes).cast("Q")
    unbalanced: list[dict[int, int]] = [{} for _ in points]
    slack: list[dict[int, int]] = [{} for _ in points]
    indices = range(DECODED_COUNT) if decoded_indices is None else decoded_indices
    for decoded_index in indices:
        decoded = prepare_decoded_state(prepared_instance, domain[decoded_index])
        for k, values in enumerate(prepared):
            energy = unbalanced_energy_prepared(decoded, values)
            _require(math.isfinite(energy), "nonfinite canonical unbalanced energy")
            unbalanced[k][decoded_index] = float_bits(energy)
        for entry in range(offsets[decoded_index], offsets[decoded_index + 1]):
            _mask, y = cache[entry]
            state = prepare_slack_state(decoded, y)
            for k, values in enumerate(prepared):
                energy = slack_energy_prepared(state, values)
                _require(math.isfinite(energy), "nonfinite canonical slack energy")
                slack[k][entry] = float_bits(energy)
    return unbalanced, slack


def canonical_reduction(words: Sequence[int], lambda_ref: float) -> tuple[int, int, bytes]:
    """certify.py first-seen strict minimum and D015 tie flags at every c_H, on energy words.

    Transcribes ``certify_prepared_domain`` / ``certify_prepared_domain_multi_ch``:
    gap = abs(y - H_min); scale = Lambda_ref + max(abs(y), abs(H_min));
    tie_tau = (c_H * EPSILON) * scale; tie iff gap <= tie_tau -- the same
    binary64 statements as canonical ``energy.tau`` (the fixtures prove the
    equality).  Returns (H_min bits, H_min index, flags) where flag bit k
    marks c_H = CH_VALUES[k] membership; nesting is enforced.
    """
    _require(len(words) > 0, "empty reduction domain")
    energies = array("d")
    energies.frombytes(array("Q", words).tobytes())
    h_min = None
    h_index = 0
    for index, value in enumerate(energies):
        _require(math.isfinite(value), "nonfinite energy in reduction")
        if h_min is None or value < h_min:
            h_min, h_index = value, index
    flags = bytearray(len(energies))
    c_eps = tuple(float(c_h) * EPSILON for c_h in CH_VALUES)
    abs_min = abs(h_min)
    for index, value in enumerate(energies):
        gap = abs(value - h_min)
        scale = lambda_ref + max(abs(value), abs_min)
        f = 0
        if gap <= c_eps[0] * scale:
            f |= 1
        if gap <= c_eps[1] * scale:
            f |= 2
        if gap <= c_eps[2] * scale:
            f |= 4
        _require(f in (0, 4, 6, 7), "D015 tie-set nesting drift")
        flags[index] = f
    return float_bits(h_min), h_index, bytes(flags)


# --------------------------------------------------------------------------
# Binary I/O with the CUDA program
# --------------------------------------------------------------------------

def _words(values: Sequence[int]) -> bytes:
    return b"".join(struct.pack("<Q", value) for value in values)


def encode_inputs(instance: Instance, lambda_ref: float, points: Sequence[Mapping[str, Any]],
                  cache: SlackDomainCache, mode: int) -> bytes:
    """Header, instance, coefficients, then the canonical cache's offsets and auxiliary words."""
    _require(mode in (MODE_VALIDATE, MODE_THROUGHPUT), "unknown engine mode")
    _require(0 < len(points) <= MAX_COORDINATES_PER_INVOCATION, "bounded coordinate contract violated")
    _require(len(instance.tickers) == 20 and len(instance.sectors) == 4, "instance shape is not 20 assets in 4 sectors")
    header = [INPUT_MAGIC, FORMAT_VERSION, 20, cache.sector_slack_bits, cache.budget_slack_bits, mode, len(points),
              len(cache), float_bits(lambda_ref)]
    scalars = [float_bits(value) for value in instance.mu]
    for row in instance.sigma:
        _require(len(row) == 20, "Sigma row length mismatch")
        scalars.extend(float_bits(value) for value in row)
    scalars.extend(float_bits(value) for value in instance.prices)
    scalars.extend([float_bits(instance.kappa_risk), float_bits(float(instance.K)), float_bits(float(instance.C)),
                    float_bits(instance.B)])
    sectors: list[int] = []
    covered: list[int] = []
    for members in instance.sectors:
        ordered = sorted(members)
        _require(0 < len(ordered) <= 20 and len(set(ordered)) == len(ordered), "sector members are not distinct")
        sectors.append(len(ordered))
        sectors.extend(ordered)
        covered.extend(ordered)
    _require(sorted(covered) == list(range(20)), "sectors do not partition the assets")
    coefficient_words: list[int] = []
    for point in points:
        values = point["coefficients"]
        _require(isinstance(values, Coefficients), "point lacks validated Coefficients")
        coefficient_words.extend(float_bits(getattr(values, name)) for name in COEFFICIENT_ORDER)
    offsets = memoryview(cache.offset_bytes).cast("Q")
    auxiliaries = memoryview(cache.auxiliary_bytes).cast("I")
    _require(len(offsets) == DECODED_COUNT + 1 and len(auxiliaries) == len(cache), "cache buffers malformed")
    return (_words(header) + _words(scalars) + _words(sectors) + _words(coefficient_words)
            + _words(list(offsets)) + _words(list(auxiliaries)))


def decode_output(payload: bytes, coordinate_count: int, slack_count: int, mode: int) -> dict[str, Any]:
    """Parse the program's output: header, then per coordinate (validate mode) minima, words, flags."""
    _require(len(payload) >= 56 and len(payload) % 8 == 0, "engine output is not word aligned")
    header = struct.unpack("<7Q", payload[:56])
    _require(header[0] == OUTPUT_MAGIC and header[1] == FORMAT_VERSION, "engine output header mismatch")
    _require(header[2] == mode and header[3] == coordinate_count and header[4] == DECODED_COUNT
             and header[5] == slack_count, "engine output counts mismatch")
    output: dict[str, Any] = {"device_index": header[6], "coordinates": []}
    cursor = 56
    if mode == MODE_THROUGHPUT:
        _require(len(payload) == cursor, "throughput output must carry no per-coordinate data")
        return output
    per = 8 * (4 + DECODED_COUNT + slack_count + DECODED_COUNT // 8 + slack_count // 8)
    _require(len(payload) == cursor + coordinate_count * per, "engine output has unexpected length")
    for _ in range(coordinate_count):
        record = struct.unpack("<4Q", payload[cursor:cursor + 32])
        cursor += 32
        words_u = array("Q")
        words_u.frombytes(payload[cursor:cursor + 8 * DECODED_COUNT])
        cursor += 8 * DECODED_COUNT
        words_s = array("Q")
        words_s.frombytes(payload[cursor:cursor + 8 * slack_count])
        cursor += 8 * slack_count
        flags_u = bytes(payload[cursor:cursor + DECODED_COUNT])
        cursor += DECODED_COUNT
        flags_s = bytes(payload[cursor:cursor + slack_count])
        cursor += slack_count
        if sys.byteorder != "little":
            words_u.byteswap()
            words_s.byteswap()
        output["coordinates"].append({
            "unbalanced": {"h_min_bits": record[0], "h_min_index": record[1], "words": words_u, "flags": flags_u},
            "slack": {"h_min_bits": record[2], "h_min_index": record[3], "words": words_s, "flags": flags_s},
        })
    return output


def compare_words(reference: Mapping[int, int], candidate: Sequence[int]) -> int:
    """Count bit-pattern mismatches at the referenced positions; positions and values never leave."""
    return sum(1 for index, word in reference.items() if candidate[index] != word)


def compare_reduction(device: Mapping[str, Any], reference: tuple[int, int, bytes]) -> dict[str, int]:
    h_min_bits, h_min_index, flags = reference
    return {
        "h_min_bits_mismatch": int(device["h_min_bits"] != h_min_bits),
        "h_min_index_mismatch": int(device["h_min_index"] != h_min_index),
        "tie_flag_mismatches": sum(1 for a, b in zip(device["flags"], flags, strict=True) if a != b),
    }


# --------------------------------------------------------------------------
# Prerequisites, device validation, identity
# --------------------------------------------------------------------------

def validate_prerequisite_records(unbalanced_record: Mapping[str, Any], slack_record: Mapping[str, Any]) -> dict[str, Any]:
    """Both passed CUDA/T4 qualification records, re-derived and mutually consistent."""
    identities = {}
    for label, record, module in (("unbalanced", unbalanced_record, cuda_unbalanced), ("slack", slack_record, cuda_slack)):
        _require(isinstance(record, dict) and record.get("schema") == module.SCHEMA_RUN and record.get("mode") == "run"
                 and record.get("track") == TRACK, f"{label} record is not a CUDA/T4 cross-check run")
        _require(record.get("verdict") == "pass", f"{label} qualification did not pass")
        for key in ("gpu_vs_python", "host_cxx_vs_python"):
            comparison = record.get(key)
            _require(isinstance(comparison, dict) and comparison.get("mismatches") == 0
                     and isinstance(comparison.get("evaluations"), int) and comparison["evaluations"] > 0,
                     f"{label} record {key} is not a zero-mismatch comparison")
        identity = record.get("qualification_identity")
        _require(isinstance(identity, dict) and record.get("qualification_identity_sha256") == module.identity_sha256(identity),
                 f"{label} qualification identity hash mismatch")
        _require(identity.get("backend") == BACKEND and isinstance(identity.get("gpu_name"), str)
                 and cuda_unbalanced.TARGET_GPU_NAME_PATTERN.fullmatch(identity["gpu_name"]) is not None
                 and identity.get("compute_capability") == "%d.%d" % cuda_unbalanced.TARGET_COMPUTE_CAPABILITY
                 and identity.get("architecture") == cuda_unbalanced.TARGET_ARCHITECTURE
                 and identity.get("compile_flags") == list(COMPILE_FLAGS)
                 and identity.get("encoding") == label, f"{label} qualification identity is not a T4/sm_75 CUDA identity")
        pins = identity.get("pinned_inputs")
        _require(isinstance(pins, dict) and all(pins.get(key) == PINNED_INPUTS[key] for key in pins if key in PINNED_INPUTS)
                 and all(key in pins for key in ("src/g4/energy.py", INSTANCE_REL)),
                 f"{label} qualification was produced against different sources")
        identities[label] = identity
    keys = ("backend", "gpu_name", "compute_capability", "architecture", "cuda_driver_version", "cuda_runtime_version",
            "nvcc_release", "nvcc_build")
    platform = {key: identities["unbalanced"].get(key) for key in keys}
    _require(platform == {key: identities["slack"].get(key) for key in keys},
             "unbalanced and slack qualifications were produced on different platforms/toolchains")
    return {
        "platform": platform,
        "unbalanced_identity_sha256": unbalanced_record["qualification_identity_sha256"],
        "slack_identity_sha256": slack_record["qualification_identity_sha256"],
    }


def validate_device_report(report: object, coordinate_count: int, slack_count: int, mode: int) -> dict[str, Any]:
    per_coordinate = DECODED_COUNT + slack_count
    validated = _shared(cuda_unbalanced.validate_device_report, report, coordinate_count, per_coordinate)
    _require(validated.get("probe") == PROBE, "device report is not from the V-14 engine program")
    _require(validated.get("mode") == ("validate" if mode == MODE_VALIDATE else "throughput"), "engine mode mismatch")
    _require(validated.get("decoded_state_count") == DECODED_COUNT and validated.get("slack_state_count") == slack_count
             and validated.get("coordinate_count") == coordinate_count, "engine domain counts mismatch")
    for key in ("nonfinite_energies", "tie_nesting_violations"):
        # Exact integer zero only: any nonzero count of any magnitude, or a non-integer, is refused.
        _require(type(validated.get(key)) is int and validated[key] == 0,
                 f"engine reported nonfinite energies or D015 nesting violations ({key})")
    _require(validated.get("host_reference_evaluated") is (mode == MODE_VALIDATE), "host-reference flag mismatch")
    for key in ("elapsed_ns_prepare", "elapsed_ns_coordinates"):
        _require(isinstance(validated.get(key), int) and validated[key] >= 0, f"{key} missing")
    return validated


def engine_identity(report: Mapping[str, Any], nvcc_info: Mapping[str, Any], command: list[str], pins: Mapping[str, str],
                    domain: Mapping[str, Any], prerequisites: Mapping[str, Any]) -> dict[str, Any]:
    identity = _shared(cuda_unbalanced.qualification_identity, report, nvcc_info, command, pins, "n/a", [], 0)
    identity.update({
        "probe": PROBE, "encoding": "prepared-domain (unbalanced + slack)", "reference": "src.g4.energy.*_energy_prepared",
        "engine_source_sha256": pins[CUDA_SOURCE_REL], "cuda_source_sha256": pins[CUDA_SOURCE_REL],
        "domain": dict(domain), "c_h_values": list(CH_VALUES), "lambda_ref_source": "V-14 ledgers inputs.lambda_ref_binary64_hex",
        "validation_coordinates_sha256": validation_coordinates_sha256(),
        "prerequisites": {"unbalanced_identity_sha256": prerequisites["unbalanced_identity_sha256"],
                          "slack_identity_sha256": prerequisites["slack_identity_sha256"]},
    })
    for key in ("state_set_sha256", "coefficient_point_ids", "evaluations"):
        identity.pop(key, None)
    return identity


def identity_sha256(identity: Mapping[str, Any]) -> str:
    return _sha256_bytes(canonical_bytes(identity))


# --------------------------------------------------------------------------
# Plan and runs
# --------------------------------------------------------------------------

def _bind(records: tuple[Mapping[str, Any], Mapping[str, Any]] | None):
    pins = verify_pinned_inputs()
    ledgers = load_ledgers()
    lambda_ref = lambda_ref_from(ledgers)
    instance = load_instance(ROOT / INSTANCE_REL)
    cache = build_slack_domain(instance)
    prerequisites = None if records is None else validate_prerequisite_records(*records)
    return pins, ledgers, lambda_ref, instance, cache, prerequisites


def build_plan(records: tuple[Mapping[str, Any], Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Validate every binding (including the canonical domain identity) without nvcc, GPU, or writes."""
    pins, ledgers, lambda_ref, instance, cache, prerequisites = _bind(records)
    points = validation_points(ledgers)
    return {
        "schema": SCHEMA_PLAN, "mode": "plan", "purpose": PURPOSE, "track": TRACK,
        "target": {"backend": BACKEND, "gpu_name": cuda_unbalanced.TARGET_GPU_NAME,
                   "compute_capability": "%d.%d" % cuda_unbalanced.TARGET_COMPUTE_CAPABILITY,
                   "architecture": cuda_unbalanced.TARGET_ARCHITECTURE},
        "pinned_inputs": pins, "self_sha256": current_hashes(SELF_RELATIVES),
        "domain": domain_identity(cache),
        "lambda_ref_binary64_hex": lambda_ref.hex(), "c_h_values": list(CH_VALUES),
        "linear_order": LINEAR_ORDER,
        "validation_coordinates": [_point_report(point) for point in points],
        "validation_coordinates_sha256": validation_coordinates_sha256(),
        "planned_evaluations_per_coordinate": DECODED_COUNT + len(cache),
        "planned_validation_evaluations": len(points) * (DECODED_COUNT + len(cache)),
        "prerequisites": prerequisites if prerequisites is not None else "not supplied to --plan",
        "compile_flags": list(COMPILE_FLAGS),
        "compile_command_template": _shared(cuda_unbalanced.compile_command, "nvcc", Path("<tmp>/engine.cu"), Path("<tmp>/engine")),
        "nvcc_located": cuda_unbalanced.locate_nvcc() is not None,
        "writes": "none", "scientific_outputs": "intentionally absent",
    }


def _execute(points: Sequence[Mapping[str, Any]], mode: int, instance: Instance, lambda_ref: float,
             cache: SlackDomainCache, locate: Callable[[], str | None]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str], dict[str, Any]]:
    """Compile and run the engine in a temporary directory; return parsed outputs (never persisted)."""
    nvcc = locate()
    _require(nvcc is not None, "nvcc is unavailable; the CUDA V-14 engine cannot run on this host")
    source = ROOT / CUDA_SOURCE_REL
    encoded = encode_inputs(instance, lambda_ref, points, cache, mode)
    temporary_path: Path | None = None
    with tempfile.TemporaryDirectory(prefix="g6-cuda-t4-v14-engine-") as temporary:
        temporary_path = Path(temporary)
        nvcc_info = _shared(cuda_unbalanced.nvcc_version, nvcc, temporary_path)
        smi = _shared(cuda_unbalanced.nvidia_smi_identity, temporary_path)
        staged = temporary_path / "cuda_v14_prepared_domain_engine.cu"
        binary = temporary_path / "engine"
        input_path = temporary_path / "input.words"
        output_path = temporary_path / "output.words"
        staged.write_bytes(source.read_bytes())
        _require(_sha256_bytes(staged.read_bytes()) == PINNED_INPUTS[CUDA_SOURCE_REL], "staged engine source drift")
        input_path.write_bytes(encoded)
        command = _shared(cuda_unbalanced.compile_command, nvcc, staged, binary)
        compilation = _shared(cuda_unbalanced._run_subprocess, command, temporary_path, COMPILE_TIMEOUT_SECONDS, "nvcc compilation")
        _require(compilation.returncode == 0, "nvcc compilation failed; do not substitute relaxed flags: " + compilation.stderr[-2000:])
        execution = _shared(cuda_unbalanced._run_subprocess, [str(binary), str(input_path), str(output_path)], temporary_path,
                            EXECUTE_TIMEOUT_SECONDS, "engine execution")
        _require(execution.returncode == 0, "engine binary failed: " + execution.stderr[-2000:])
        try:
            report = json.loads(execution.stdout)
        except json.JSONDecodeError as exc:
            raise EngineError("engine emitted malformed JSON") from exc
        validate_device_report(report, len(points), len(cache), mode)
        try:
            output_bytes = output_path.read_bytes()
        except OSError as exc:
            raise EngineError("engine output file is unreadable") from exc
        decoded = decode_output(output_bytes, len(points), len(cache), mode)
        _require(decoded["device_index"] == report.get("device_index"), "device index disagreement")
    _require(temporary_path is not None and not temporary_path.exists(), "temporary directory was not removed")
    return report, decoded, nvcc_info, command, smi


def _common_run_fields(report, nvcc_info, command, smi, pins, platform_before, cache, prerequisites, points) -> dict[str, Any]:
    identity = engine_identity(report, nvcc_info, command, pins, domain_identity(cache), prerequisites)
    _require({key: identity[key] for key in prerequisites["platform"]} == prerequisites["platform"],
             "observed platform/toolchain differs from the prerequisite qualifications; requalify")
    return {
        "purpose": PURPOSE, "track": TRACK, "platform": platform_before, "pinned_inputs": pins,
        "self_sha256": current_hashes(SELF_RELATIVES), "domain": domain_identity(cache),
        "prerequisites": prerequisites, "compile_command": command, "nvcc": nvcc_info, "nvidia_smi": smi,
        "device": cuda_unbalanced.device_fingerprint(report), "device_reported": report,
        "qualification_identity": identity, "qualification_identity_sha256": identity_sha256(identity),
        "coordinates": [_point_report(point) for point in points],
        "coordinate_count": len(points), "evaluations": report["evaluations"],
        "elapsed_ns_prepare": report["elapsed_ns_prepare"], "elapsed_ns_coordinates": report["elapsed_ns_coordinates"],
        "temporary_directory_removed": True, "writes": "none", "scientific_outputs": "intentionally absent",
    }


def run_validate(records: tuple[Mapping[str, Any], Mapping[str, Any]],
                 locate: Callable[[], str | None] = cuda_unbalanced.locate_nvcc) -> dict[str, Any]:
    """Full-domain validation at the declared coordinates; counters and identities only."""
    _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 is required")
    pins, ledgers, lambda_ref, instance, cache, prerequisites = _bind(records)
    platform_before = cuda_unbalanced._platform_fingerprint()
    points = validation_points(ledgers)
    report, decoded, nvcc_info, command, smi = _execute(points, MODE_VALIDATE, instance, lambda_ref, cache, locate)
    reference_u, reference_s = cpu_reference(instance, points, cache)
    per_coordinate = []
    totals = {"word_mismatches": 0, "reduction_mismatches": 0}
    for k, point in enumerate(points):
        device = decoded["coordinates"][k]
        entry: dict[str, Any] = {"scale": point["scale"], "coordinate": point["coordinate"], "linear": point["linear"]}
        for encoding, reference in (("unbalanced", reference_u[k]), ("slack", reference_s[k])):
            words = compare_words(reference, device[encoding]["words"])
            ordered = [reference[index] for index in range(len(reference))]
            reduction = compare_reduction(device[encoding], canonical_reduction(ordered, lambda_ref))
            entry[encoding] = {"gpu_vs_python_word_mismatches": words, "evaluations": len(reference), **reduction}
            totals["word_mismatches"] += words
            totals["reduction_mismatches"] += sum(reduction.values())
        per_coordinate.append(entry)
    _require(verify_pinned_inputs() == pins, "pinned input drift during validation")
    _require(cuda_unbalanced._platform_fingerprint() == platform_before, "platform fingerprint drift during validation")
    verdict = "pass" if (totals["word_mismatches"] == 0 and totals["reduction_mismatches"] == 0
                         and report["device_vs_host_cxx_mismatches"] == 0) else "fail"
    return {"schema": SCHEMA_VALIDATE, "mode": "validate",
            **_common_run_fields(report, nvcc_info, command, smi, pins, platform_before, cache, prerequisites, points),
            "validation": {"per_coordinate": per_coordinate, "totals": totals,
                           "device_vs_host_cxx_mismatches": report["device_vs_host_cxx_mismatches"],
                           "reference": "full canonical prepared domains, both encodings, every declared coordinate"},
            "verdict": verdict}


def _seconds_text(ns: int) -> str:
    """Exact decimal seconds from an integer nanosecond count."""
    _require(isinstance(ns, int) and ns >= 0, "elapsed nanoseconds must be a non-negative integer")
    return f"{ns // 10**9}.{ns % 10**9:09d}"


def throughput_timing(wall_ns: int, coordinate_ns: int) -> dict[str, str]:
    """Exact per-invocation timing fields: wall == setup + coordinate at nanosecond precision.

    ``wall_ns`` is the end-to-end Python ``time.monotonic_ns`` span (guard to
    result construction: binding, cache derivation, nvcc compilation, execution,
    provenance re-checks); ``coordinate_ns`` is the engine's coordinate-loop
    time; ``setup`` is their difference and is fixed per independent session.
    """
    _require(isinstance(wall_ns, int) and isinstance(coordinate_ns, int) and 0 <= coordinate_ns <= wall_ns,
             "coordinate time must not exceed end-to-end wall time")
    setup_ns = wall_ns - coordinate_ns
    fields = {"wall_seconds": _seconds_text(wall_ns), "setup_seconds": _seconds_text(setup_ns),
              "coordinate_seconds": _seconds_text(coordinate_ns)}
    _require(int(fields["wall_seconds"].replace(".", "")) == int(fields["setup_seconds"].replace(".", ""))
             + int(fields["coordinate_seconds"].replace(".", "")), "timing fields do not reconcile exactly")
    return fields


def run_throughput(records: tuple[Mapping[str, Any], Mapping[str, Any]], scale: str, start: int, stop: int,
                   locate: Callable[[], str | None] = cuda_unbalanced.locate_nvcc) -> dict[str, Any]:
    """Process one declared coordinate range with the same engine; print counts, exact times, identities only."""
    _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 is required")
    started_ns = time.monotonic_ns()
    pins, ledgers, lambda_ref, instance, cache, prerequisites = _bind(records)
    platform_before = cuda_unbalanced._platform_fingerprint()
    points = range_points(ledgers, scale, start, stop)
    report, _decoded, nvcc_info, command, smi = _execute(points, MODE_THROUGHPUT, instance, lambda_ref, cache, locate)
    _require(verify_pinned_inputs() == pins, "pinned input drift during throughput")
    _require(cuda_unbalanced._platform_fingerprint() == platform_before, "platform fingerprint drift during throughput")
    common = _common_run_fields(report, nvcc_info, command, smi, pins, platform_before, cache, prerequisites, points)
    common.pop("coordinates")
    payload = {"schema": SCHEMA_THROUGHPUT_RUN, "mode": "throughput", **common,
               "range": {"scale": scale, "pass_id": SCALES[scale]["pass_id"], "start": start, "stop": stop,
                         "count": stop - start, "linear_order": LINEAR_ORDER},
               "max_coordinates_per_invocation": MAX_COORDINATES_PER_INVOCATION, "verdict": "measured"}
    finished_ns = time.monotonic_ns()
    timing = throughput_timing(finished_ns - started_ns, report["elapsed_ns_coordinates"])
    measurement = {"schema": SCHEMA_THROUGHPUT_MEASUREMENT, "unit": "coordinates",
                   "qualification_identity_sha256": common["qualification_identity_sha256"],
                   "samples": [{"coordinates": len(points), **timing}],
                   "timing_rule": "wall = end-to-end monotonic span from the environment guard to result construction; "
                                  "coordinate = engine coordinate-loop time; setup = wall - coordinate (fixed per session)",
                   "measured_by": f"{SCHEMA_THROUGHPUT_RUN} scale={scale} range=[{start},{stop})"}
    measurement["content_sha256"] = _sha256_bytes(canonical_bytes(measurement))
    payload["timing"] = {"end_to_end_wall_ns": finished_ns - started_ns, **timing}
    payload["throughput_measurement"] = measurement
    return payload
