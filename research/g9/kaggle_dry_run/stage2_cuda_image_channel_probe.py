#!/usr/bin/env python3
"""Gate-9 pre-write image-channel DISCOVERY probe: non-scientific, standard library only.

Purpose: discover whether a Kaggle session exposes a candidate in-session channel
that carries a content digest of its own executing image.  This probe NEVER
establishes, claims or substitutes for the section-B pre-write identity check,
and a single run cannot show that a candidate tracks the actual image across
versions.  Any candidate it reports is a hypothesis for separate, owner-approved
follow-up; see GATE_9_CUDA_IMAGE_CHANNEL_PROBE_DRAFT.md in this directory.

What it reads, always through injectable readers:
  * environment variable NAMES.  A value is read only for a name that contains
    IMAGE, DIGEST or CONTAINER and none of SENSITIVE_TOKENS; the sensitive-name
    exclusion is applied to the name before any value is read;
  * stat() of the fixed paths /dev/nvidia0 ... /dev/nvidia15 (character devices);
  * optionally the fixed files /proc/self/cgroup and /proc/self/mountinfo, byte
    capped and reduced to match-only booleans labelled as untrusted hints.
There is no network, subprocess, PID-1 environment file, directory walk or
credential access.  The report carries only variable names, counts and enum
classifications: never a raw value, URL, hostname or unrecognised hash.

Importing this module writes nothing.  Executed as a script, which is permitted
only inside a separately owner-approved Kaggle session, it writes exactly one
file under /kaggle/working: the receipt, or on refusal the failure log.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import hashlib
import json
import os
from pathlib import Path
import re
import stat

SCHEMA = "decisions_os/g9_cuda_image_channel_probe_report/v1"
PROBE_VERSION = 1
MODE = "non_scientific_image_channel_discovery"

# Public section-A version-1 image identities: the SHA-256 of the preserved public
# manifest and of its config blob.  Owner-accepted for that one run only.
EXPECTED_MANIFEST_DIGEST = "sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461"
EXPECTED_CONFIG_ID = "sha256:c72831376c5485ec652a6f4a771bf091ae0726310e1b9db3db064387e173e941"
EXPECTED_IMAGE_SOURCE = "public_section_A_version1_manifest_and_config"

# The reviewed submission policy: private T4 script, internet off, no input
# sources and no image pin.  id, title and code_file are checked for shape only.
EXPECTED_METADATA_POLICY = {
    "competition_sources": [],
    "dataset_sources": [],
    "enable_gpu": True,
    "enable_internet": False,
    "enable_tpu": False,
    "is_private": True,
    "kernel_sources": [],
    "kernel_type": "script",
    "keywords": [],
    "language": "python",
    "machine_shape": "NvidiaTeslaT4",
    "model_sources": [],
}
METADATA_IDENTITY_KEYS = ("code_file", "id", "title")
METADATA_IDENTITY_LIMIT = 160
FORBIDDEN_METADATA_KEYS = ("docker_image", "docker_image_pinning_type")

SELECT_TOKENS = ("IMAGE", "DIGEST", "CONTAINER")
SENSITIVE_TOKENS = ("TOKEN", "SECRET", "KEY", "PASSWORD", "PASSWD", "AUTH", "PROXY",
                    "CREDENTIAL", "COOKIE")
MAX_ENVIRONMENT_NAMES = 4096
MAX_SELECTED_NAMES = 16
MAX_VALUE_BYTES = 512
MAX_GPU_DEVICE_NODES = 16
MAX_REPORT_BYTES = 8192
NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")

SHA256_DIGEST = re.compile(r"sha256:([0-9a-f]{64})")
BARE_HEX64 = re.compile(r"([0-9a-f]{64})")
REPOSITORY_DIGEST = re.compile(r"([a-z0-9][a-z0-9._:/-]{0,254})@sha256:([0-9a-f]{64})")
DIGEST_MARKER = re.compile(r"sha256|[0-9a-f]{64}", re.IGNORECASE)

GPU_DEVICE_PATHS = tuple("/dev/nvidia" + str(index) for index in range(MAX_GPU_DEVICE_NODES))
HINT_PATHS = (
    ("proc_self_cgroup", "/proc/self/cgroup", 16384),
    ("proc_self_mountinfo", "/proc/self/mountinfo", 262144),
)
HINT_TRUST = "untrusted_hint_not_proof"

INTERNET_OBSERVATIONS = ("not_observed", "observed_off", "observed_on")
# No stdlib, network-free and read-bounded way to observe internet state exists
# here, so the live run relies on the reviewed metadata declaration.
LIVE_INTERNET_OBSERVATION = "not_observed"
INTERNET_BASIS = "declared_by_reviewed_metadata_policy_not_observed_in_session"

CLASSIFICATIONS = (
    "expected_manifest_digest",
    "expected_config_id",
    "other_digest_shaped_value",
    "no_digest_shaped_value",
)
VERDICTS = (
    "expected_digest_candidate_observed",
    "digest_shaped_value_without_expected_match",
    "no_digest_shaped_value_observed",
    "refused",
)
REFUSAL_REASONS = (
    "metadata_internet_enabled",
    "metadata_image_pin_present",
    "metadata_drift",
    "internet_observation_malformed",
    "internet_observed_on",
    "gpu_device_reader_malformed",
    "gpu_device_absent",
    "environment_name_overcount",
    "environment_name_malformed",
    "selected_name_malformed",
    "selected_name_overcount",
    "selected_value_oversize",
    "selected_value_malformed",
    "hint_reader_malformed",
    "hint_file_oversize",
    "reader_error",
    "report_oversize",
)

SECTION_B_STATUS = "not_established_by_this_probe"
CANDIDATE_STATUS = ("hypothesis_only_requires_owner_approved_version_bound_"
                    "and_changed_image_observations")
CROSS_VERSION_STATUS = "not_testable_in_a_single_run"
ABSENT = "intentionally absent"
REPORT_KEYS = (
    "candidate_status", "content_sha256", "cross_version_tracking", "environment",
    "expected_image", "gpu_device_node_count", "hints", "internet",
    "metadata_policy_sha256", "mode", "probe_version", "refusal_reason",
    "refused_selected_names", "schema", "scientific_outputs",
    "section_B_prewrite_identity", "stage2_inputs", "verdict",
)

WORKING_DIR = Path("/kaggle/working")
RECEIPT_NAME = "g9_cuda_image_channel_probe_receipt.json"
FAILURE_NAME = "g9_cuda_image_channel_probe_failure.log"
FAILURE_HEADER = (b"Gate-9 image-channel discovery probe REFUSED "
                  b"(no receipt written; nothing established)\n")


class ProbeRefusal(Exception):
    """A fail-closed refusal carrying only an enum reason and selected names."""

    def __init__(self, reason: str, names: tuple = ()) -> None:
        if reason not in REFUSAL_REASONS:
            raise ValueError("unknown refusal reason")
        super().__init__(reason)
        self.reason = reason
        self.names = tuple(names)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    """Canonical JSON bytes.  allow_nan=False: no non-finite value can be emitted."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def report_bytes(report: dict) -> bytes:
    return canonical(report) + b"\n"


def _hex(digest: str) -> str:
    return digest.split(":", 1)[1]


def _bounded_ascii(value: object, limit: int) -> bool:
    return (type(value) is str and 0 < len(value) <= limit and value.isascii() and
            value.isprintable())


def check_metadata(metadata: object) -> str | None:
    """None for the reviewed private T4, internet-off, source-free, unpinned
    request; otherwise the refusal reason.  Types are compared exactly."""
    if type(metadata) is not dict:
        return "metadata_drift"
    if "enable_internet" in metadata and metadata["enable_internet"] is not False:
        return "metadata_internet_enabled"
    if any(key in metadata for key in FORBIDDEN_METADATA_KEYS):
        return "metadata_image_pin_present"
    for key in METADATA_IDENTITY_KEYS:
        if key in metadata and not _bounded_ascii(metadata[key], METADATA_IDENTITY_LIMIT):
            return "metadata_drift"
    policy = {key: value for key, value in metadata.items() if key not in METADATA_IDENTITY_KEYS}
    try:
        same = canonical(policy) == canonical(EXPECTED_METADATA_POLICY)
    except (TypeError, ValueError):
        return "metadata_drift"
    return None if same else "metadata_drift"


def check_internet(observation: object) -> str:
    if type(observation) is not str or observation not in INTERNET_OBSERVATIONS:
        raise ProbeRefusal("internet_observation_malformed")
    if observation == "observed_on":
        raise ProbeRefusal("internet_observed_on")
    return observation


def check_gpu(count_gpu_devices) -> int:
    count = count_gpu_devices()
    if type(count) is not int or not 0 <= count <= MAX_GPU_DEVICE_NODES:
        raise ProbeRefusal("gpu_device_reader_malformed")
    if count == 0:
        raise ProbeRefusal("gpu_device_absent")
    return count


def select_names(list_env_names) -> tuple:
    """Choose names from NAMES alone.  Sensitive names are dropped here, before
    any value is read; no value reader is reachable from this function."""
    seen = set()
    selected = []
    excluded = 0
    count = 0
    for name in list_env_names():
        count += 1
        if count > MAX_ENVIRONMENT_NAMES:
            raise ProbeRefusal("environment_name_overcount")
        if type(name) is not str or name in seen:
            raise ProbeRefusal("environment_name_malformed")
        seen.add(name)
        upper = name.upper()
        if any(token in upper for token in SENSITIVE_TOKENS):
            excluded += 1
            continue
        if not any(token in upper for token in SELECT_TOKENS):
            continue
        if NAME_PATTERN.fullmatch(name) is None:
            raise ProbeRefusal("selected_name_malformed")
        selected.append(name)
    if len(selected) > MAX_SELECTED_NAMES:
        raise ProbeRefusal("selected_name_overcount")
    return count, excluded, sorted(selected)


def classify_value(value: object) -> str:
    """Enum classification of one selected value; the value never leaves here.
    Raises ProbeRefusal on oversize or malformed input."""
    if type(value) is not str:
        raise ProbeRefusal("selected_value_malformed")
    if len(value) > MAX_VALUE_BYTES:
        raise ProbeRefusal("selected_value_oversize")
    if not (value.isascii() and value.isprintable()):
        raise ProbeRefusal("selected_value_malformed")
    match = SHA256_DIGEST.fullmatch(value) or BARE_HEX64.fullmatch(value)
    if match is not None:
        candidate = match.group(1)
    else:
        match = REPOSITORY_DIGEST.fullmatch(value)
        repository = None if match is None else match.group(1)
        if (repository is not None and "//" not in repository and
                not repository.endswith(("/", ":", ".", "-"))):
            candidate = match.group(2)
        elif DIGEST_MARKER.search(value) is not None:
            raise ProbeRefusal("selected_value_malformed")
        else:
            return "no_digest_shaped_value"
    if candidate == _hex(EXPECTED_MANIFEST_DIGEST):
        return "expected_manifest_digest"
    if candidate == _hex(EXPECTED_CONFIG_ID):
        return "expected_config_id"
    return "other_digest_shaped_value"


def scan_environment(list_env_names, read_env_value) -> dict:
    count, excluded, selected = select_names(list_env_names)
    rows = []
    for name in selected:
        try:
            classification = classify_value(read_env_value(name))
        except ProbeRefusal as refusal:
            raise ProbeRefusal(refusal.reason, (name,)) from None
        rows.append({"classification": classification, "name": name})
    counts = {label: sum(row["classification"] == label for row in rows)
              for label in CLASSIFICATIONS}
    return {
        "classification_counts": counts,
        "excluded_sensitive_name_count": excluded,
        "names_seen_count": count,
        "selected": rows,
        "selected_name_count": len(rows),
    }


def inspect_hints(read_hint) -> dict:
    """Match-only booleans over byte-capped fixed files; content never leaves here."""
    result = {"trust": HINT_TRUST}
    for label, path, limit in HINT_PATHS:
        entry = {"contains_expected_config_hex": None, "contains_expected_manifest_hex": None,
                 "status": "not_requested"}
        if read_hint is not None:
            data = read_hint(path, limit)
            if data is None:
                entry["status"] = "unavailable"
            elif type(data) is not bytes:
                raise ProbeRefusal("hint_reader_malformed")
            elif len(data) > limit:
                raise ProbeRefusal("hint_file_oversize")
            else:
                entry = {
                    "contains_expected_config_hex":
                        _hex(EXPECTED_CONFIG_ID).encode("ascii") in data,
                    "contains_expected_manifest_hex":
                        _hex(EXPECTED_MANIFEST_DIGEST).encode("ascii") in data,
                    "status": "read",
                }
        result[label] = entry
    return result


def _base_body() -> dict:
    return {
        "candidate_status": CANDIDATE_STATUS,
        "cross_version_tracking": CROSS_VERSION_STATUS,
        "environment": None,
        "expected_image": {"config_id": EXPECTED_CONFIG_ID,
                           "manifest_digest": EXPECTED_MANIFEST_DIGEST,
                           "source": EXPECTED_IMAGE_SOURCE},
        "gpu_device_node_count": None,
        "hints": None,
        "internet": None,
        "metadata_policy_sha256": _sha(canonical(EXPECTED_METADATA_POLICY)),
        "mode": MODE,
        "probe_version": PROBE_VERSION,
        "refusal_reason": None,
        "refused_selected_names": [],
        "schema": SCHEMA,
        "scientific_outputs": ABSENT,
        "section_B_prewrite_identity": SECTION_B_STATUS,
        "stage2_inputs": ABSENT,
        "verdict": None,
    }


def _seal(body: dict) -> dict:
    report = dict(body)
    report["content_sha256"] = _sha(canonical(body))
    return report


def refusal_report(reason: str, names: tuple = ()) -> dict:
    body = _base_body()
    body["refusal_reason"] = reason
    body["refused_selected_names"] = sorted(names)
    body["verdict"] = "refused"
    return _seal(body)


def run_probe(metadata: object, *, list_env_names, read_env_value, count_gpu_devices,
              read_hint=None, internet_observation: object = LIVE_INTERNET_OBSERVATION) -> dict:
    """Return the sealed report.  Order: metadata, internet, GPU device, then the
    environment names, then optional hints.  Any refusal stops before later reads."""
    try:
        reason = check_metadata(metadata)
        if reason is not None:
            raise ProbeRefusal(reason)
        internet = check_internet(internet_observation)
        gpu_count = check_gpu(count_gpu_devices)
        environment = scan_environment(list_env_names, read_env_value)
        hints = inspect_hints(read_hint)
    except ProbeRefusal as refusal:
        return refusal_report(refusal.reason, refusal.names)
    except Exception:
        return refusal_report("reader_error")
    counts = environment["classification_counts"]
    if counts["expected_manifest_digest"] or counts["expected_config_id"]:
        verdict = "expected_digest_candidate_observed"
    elif counts["other_digest_shaped_value"]:
        verdict = "digest_shaped_value_without_expected_match"
    else:
        verdict = "no_digest_shaped_value_observed"
    body = _base_body()
    body["environment"] = environment
    body["gpu_device_node_count"] = gpu_count
    body["hints"] = hints
    body["internet"] = {"basis": INTERNET_BASIS, "declared_enable_internet": False,
                        "in_session_observation": internet}
    body["verdict"] = verdict
    report = _seal(body)
    if len(report_bytes(report)) > MAX_REPORT_BYTES:
        return refusal_report("report_oversize")
    return report


def live_env_names() -> tuple:
    """Environment variable NAMES only; no value is touched here."""
    return tuple(os.environ.keys())


def live_env_value(name: str) -> str:
    """Reached only for names already chosen by select_names."""
    return os.environ[name]


def live_gpu_device_count() -> int:
    count = 0
    for path in GPU_DEVICE_PATHS:
        try:
            mode = os.stat(path).st_mode
        except OSError:
            continue
        if stat.S_ISCHR(mode):
            count += 1
    return count


def live_read_hint(path: str, limit: int) -> bytes | None:
    """Read at most limit + 1 bytes of one of the two fixed hint files."""
    if (path, limit) not in {(fixed, cap) for _, fixed, cap in HINT_PATHS}:
        raise ValueError("not a fixed hint path")
    try:
        with open(path, "rb") as handle:
            return handle.read(limit + 1)
    except OSError:
        return None


def live_sources() -> dict:
    return {
        "count_gpu_devices": live_gpu_device_count,
        "internet_observation": LIVE_INTERNET_OBSERVATION,
        "list_env_names": live_env_names,
        "read_env_value": live_env_value,
        "read_hint": live_read_hint,
    }


def main(working_dir: Path = WORKING_DIR, sources: dict | None = None) -> int:
    """Kaggle entry point.  Writes exactly one new file in working_dir."""
    if working_dir.is_symlink() or not working_dir.is_dir():
        print("REFUSED: the Kaggle working directory is unavailable; nothing written",
              file=sys.stderr)
        return 2
    for name in (RECEIPT_NAME, FAILURE_NAME):
        if os.path.lexists(working_dir / name):
            print("REFUSED: a probe output already exists; nothing written", file=sys.stderr)
            return 2
    report = run_probe(EXPECTED_METADATA_POLICY, **(live_sources() if sources is None else sources))
    data = report_bytes(report)
    sys.stdout.write(data.decode("ascii"))
    sys.stdout.flush()
    refused = report["verdict"] == "refused"
    with open(working_dir / (FAILURE_NAME if refused else RECEIPT_NAME), "xb") as handle:
        handle.write(FAILURE_HEADER + data if refused else data)
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
