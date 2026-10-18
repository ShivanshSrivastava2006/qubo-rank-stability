#!/usr/bin/env python3
"""Gate-9 Arm-0 INTRINSIC IMAGE FINGERPRINT probe: non-scientific, stdlib only.

Purpose: let a session MEASURE the container image it is actually running in,
reducing filesystem facts to one deterministic SHA-256, without trusting any
platform-supplied string.  This is Arm 0 of
GATE_9_CUDA_IMAGE_TRACKING_EXPERIMENT_DESIGN_DRAFT.md: its only immediate job is
to test whether such a fingerprint is STABLE across two runs of the same image.

This probe does NOT establish the section-B pre-write identity check, does not
qualify CUDA, and does not make a session Stage-2 ready.  A single run shows
nothing about stability; two runs showing the same value show only that the
value did not move between those two runs.

What it reads, always through injectable readers:
  * interpreter facts: sys.version and sys.implementation details;
  * the bytes of /etc/os-release (content hash plus the parsed ID and VERSION_ID
    fields), of /etc/debian_version, and of /var/lib/dpkg/status -- each byte
    capped, each reduced to a SHA-256, none ever emitted;
  * the COMPLETE set of installed Python distributions as (normalised name,
    version) pairs, enumerated with importlib.metadata.distributions();
  * for the three paths in IMMUTABLE_PATHS, the pair (st_size, st_mode).

Why package state rather than a small path whitelist.  An earlier draft hashed
(path, st_size, st_mtime_ns, st_mode) over about sixteen paths under /usr and
/etc.  That construction fails in both directions inside a 20GB+ image: sixteen
paths cannot cover a rollover that bumps, say, scipy or xgboost, so two DIFFERENT
images could collide on one fingerprint -- which mimics exactly the constant
behaviour the experiment exists to reject -- while any container-runtime injected
file caught in the whitelist (/etc/hosts, /etc/resolv.conf, /etc/hostname,
/etc/mtab, /etc/ld.so.cache, /etc/machine-id) would make two runs of the SAME
image differ for a spurious reason.  The full distribution enumeration is
`pip freeze` without a subprocess, and the /var/lib/dpkg/status hash is
`dpkg-query -l` without a subprocess; together they cover the package state of
the whole image.

No mtime is read anywhere.  mtime is the likeliest source of same-image
instability, so it is excluded from every component by construction; the three
retained IMMUTABLE_PATHS contribute st_size and st_mode only.

There is no directory walk: every path read comes from a fixed module-level
whitelist.  There is no network, no subprocess, and no credential access.

This probe reads NO environment variable at all.  Measuring the environment
channel is a different probe's job (stage2_cuda_image_channel_probe.py) and the
two are kept separate on purpose: this one is a pure filesystem measurement.

Deliberately excluded and REFUSED rather than skipped, because they are host or
session state rather than image content: /proc, /sys, /dev, /kaggle, /tmp,
/var/run and the other session-writable prefixes in EXCLUDED_PREFIXES, plus the
runtime-injected files in RUNTIME_INJECTED_PATHS, which are refused even though
they sit under an otherwise allowed prefix.

Known limit of the distribution component, stated plainly because the design
draft did not anticipate it: importlib.metadata resolves distributions against
sys.path, and this probe cannot verify that every sys.path entry lies under an
image-owned prefix without the directory walk it refuses to do.  A session-local
install (for example pip --user into a writable prefix) would change that
component while the image did not.  It is therefore reported with the trust enum
DISTRIBUTION_TRUST and must be read as weaker evidence than the byte-capped
content hashes.

Determinism is the whole point: run_probe is a pure function of its injected
readers.  The same inputs MUST produce the same image_content_fingerprint.
Enumeration order is removed by sorting, so a reader that yields the same set in
a different order yields the same fingerprint.

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

SCHEMA = "decisions_os/g9_cuda_image_fingerprint_probe_report/v1"
PROBE_VERSION = 1
MODE = "non_scientific_intrinsic_image_fingerprint_measurement"
ARM = "arm_0_fingerprint_stability_prerequisite"

# Bumping this changes every fingerprint: a fingerprint is comparable only
# within one spec version, and the spec version is part of the hashed structure.
FINGERPRINT_SPEC_VERSION = 2

# A read path must sit under one of these image-owned prefixes.
ALLOWED_PREFIXES = ("/etc/", "/usr/", "/var/lib/dpkg/")

# Host state or session state, never image content.  A path matching one of
# these is a REFUSAL, not a silent skip.
EXCLUDED_PREFIXES = (
    "/dev/", "/home/", "/kaggle/", "/media/", "/mnt/", "/proc/", "/root/",
    "/run/", "/sys/", "/tmp/", "/var/cache/", "/var/log/", "/var/run/",
    "/var/tmp/", "/working/",
)

# Injected by the container runtime at start-up.  They live under an allowed
# prefix and would therefore pass the prefix rule, so they are named and refused
# explicitly: any of them in a fingerprint would break same-image stability.
RUNTIME_INJECTED_PATHS = (
    "/etc/hostname",
    "/etc/hosts",
    "/etc/ld.so.cache",
    "/etc/machine-id",
    "/etc/mtab",
    "/etc/resolv.conf",
)

# Byte-capped content reads.  os-release is required; the others are optional
# and their absence is a deterministic value, not a failure.
OS_RELEASE_PATH = "/etc/os-release"
DEBIAN_VERSION_PATH = "/etc/debian_version"
DPKG_STATUS_PATH = "/var/lib/dpkg/status"
CONTENT_PATHS = (
    ("os_release", OS_RELEASE_PATH, 8192, True),
    ("debian_version", DEBIAN_VERSION_PATH, 1024, False),
    ("dpkg_status", DPKG_STATUS_PATH, 1 << 24, False),
)

# The only stat'ed paths that survived review, and the only non-package-state
# component.  Each is a file that a container runtime never rewrites, and only
# (st_size, st_mode) is taken: no mtime, anywhere in this probe.
IMMUTABLE_PATHS = (
    "/usr/bin/dpkg",
    "/usr/bin/python3",
    "/usr/lib/x86_64-linux-gnu/libc.so.6",
)

MAX_PATH_CHARS = 128
MAX_IMMUTABLE_PATHS = 8
MAX_DISTRIBUTIONS = 4096
MAX_NAME_CHARS = 128
MAX_VERSION_CHARS = 64
MAX_LABEL_CHARS = 32
MAX_ST_MODE = 0xFFFF_FFFF
MAX_ST_SIZE = 1 << 48
MAX_REPORT_BYTES = 8192

PATH_PATTERN = re.compile(r"/[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*")
NAME_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,127})")
RAW_NAME_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,127})")
VERSION_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._+!-]{0,63})")
LABEL_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,31})")
OS_RELEASE_LINE = re.compile(r"([A-Z][A-Z0-9_]{0,63})=(.*)")
NAME_SEPARATORS = re.compile(r"[-_.]+")

OS_RELEASE_FIELDS = ("ID", "VERSION_ID")
IMPLEMENTATION_KEYS = ("cache_tag", "hexversion", "name", "version")

COMPONENT_STATUSES = (
    "not_measured",
    "measured",
    "measured_partial",
    "absent",
)
# The distribution component carries this alongside its status: see the module
# docstring.  It is a measurement whose intrinsic-ness is unverified.
DISTRIBUTION_TRUST = "not_prefix_verifiable_weaker_than_byte_capped_content_hashes"
PATH_STATUSES = ("present", "absent")

VERDICTS = (
    "fingerprint_measured",
    "refused",
)
REFUSAL_REASONS = (
    "whitelist_malformed",
    "whitelist_overcount",
    "path_excluded_prefix",
    "path_runtime_injected",
    "path_not_allowed_prefix",
    "path_not_whitelisted",
    "interpreter_reader_malformed",
    "content_reader_malformed",
    "content_file_oversize",
    "content_file_absent",
    "os_release_field_malformed",
    "stat_reader_malformed",
    "stat_value_out_of_range",
    "distribution_reader_malformed",
    "distribution_overcount",
    "distribution_name_malformed",
    "distribution_version_malformed",
    "distribution_version_oversize",
    "fingerprint_malformed",
    "reader_error",
    "report_oversize",
)

SECTION_B_STATUS = "not_established_by_this_probe"
CUDA_STATUS = "not_qualified_by_this_probe"
STABILITY_STATUS = "not_testable_in_a_single_run_requires_two_runs_of_the_same_image"
ENVIRONMENT_STATUS = "no_environment_variable_is_read_by_this_probe"
MTIME_STATUS = "no_mtime_is_read_by_any_component"
ABSENT = "intentionally absent"
REPORT_KEYS = (
    "arm", "component_sha256", "component_status", "content_sha256", "counts",
    "cross_run_stability", "cuda_qualification", "distribution_trust",
    "environment_channel", "excluded_prefixes_sha256", "fingerprint_spec_version",
    "image_content_fingerprint", "immutable_paths", "labels", "mtime_policy",
    "mode", "probe_version", "refusal_reason", "refused_path", "schema",
    "scientific_outputs", "section_B_prewrite_identity", "stage2_inputs",
    "verdict", "whitelist_sha256",
)

WORKING_DIR = Path("/kaggle/working")
RECEIPT_NAME = "g9_cuda_image_fingerprint_probe_receipt.json"
FAILURE_NAME = "g9_cuda_image_fingerprint_probe_failure.log"
FAILURE_HEADER = (b"Gate-9 intrinsic image fingerprint probe REFUSED "
                  b"(no receipt written; no fingerprint; nothing established)\n")


class ProbeRefusal(Exception):
    """A fail-closed refusal carrying only an enum reason and at most one path."""

    def __init__(self, reason: str, path: str | None = None) -> None:
        if reason not in REFUSAL_REASONS:
            raise ValueError("unknown refusal reason")
        super().__init__(reason)
        self.reason = reason
        self.path = path


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    """Canonical JSON bytes.  allow_nan=False: no non-finite value can be emitted."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def report_bytes(report: dict) -> bytes:
    return canonical(report) + b"\n"


def _bounded_ascii(value: object, limit: int) -> bool:
    return (type(value) is str and 0 < len(value) <= limit and value.isascii() and
            value.isprintable())


def _bounded_int(value: object, limit: int) -> bool:
    # type(...) is int rejects bool, which json would otherwise render as a keyword.
    return type(value) is int and 0 <= value <= limit


def whitelisted_paths() -> tuple:
    """Every path this probe may read, from module constants alone."""
    return tuple(sorted(IMMUTABLE_PATHS + tuple(path for _, path, _, _ in CONTENT_PATHS)))


def check_path(path: object) -> str:
    """Refuse any path that is not an image-owned whitelist entry.

    Rule order is deliberate.  The excluded-prefix rule and the runtime-injected
    rule are enforced BEFORE the allow rule and before whitelist membership, so
    a /proc, /sys, /dev, /kaggle, /tmp or /var/run path is REFUSED with
    path_excluded_prefix -- never quietly skipped, never merely "not
    whitelisted" -- and /etc/hosts and its siblings are refused by name."""
    if not _bounded_ascii(path, MAX_PATH_CHARS):
        raise ProbeRefusal("whitelist_malformed")
    if PATH_PATTERN.fullmatch(path) is None or ".." in path.split("/"):
        raise ProbeRefusal("whitelist_malformed")
    for prefix in EXCLUDED_PREFIXES:
        if path == prefix.rstrip("/") or path.startswith(prefix):
            raise ProbeRefusal("path_excluded_prefix", path)
    if path in RUNTIME_INJECTED_PATHS:
        raise ProbeRefusal("path_runtime_injected", path)
    if not any(path.startswith(prefix) for prefix in ALLOWED_PREFIXES):
        raise ProbeRefusal("path_not_allowed_prefix", path)
    if path not in whitelisted_paths():
        raise ProbeRefusal("path_not_whitelisted", path)
    return path


def validate_whitelist() -> int:
    """Every fixed path is re-checked at run time; a bad constant refuses."""
    paths = whitelisted_paths()
    if len(IMMUTABLE_PATHS) > MAX_IMMUTABLE_PATHS:
        raise ProbeRefusal("whitelist_overcount")
    if len(set(paths)) != len(paths):
        raise ProbeRefusal("whitelist_malformed")
    if tuple(sorted(IMMUTABLE_PATHS)) != IMMUTABLE_PATHS:
        raise ProbeRefusal("whitelist_malformed")
    for path in paths:
        check_path(path)
    for _, _, limit, _required in CONTENT_PATHS:
        if not _bounded_int(limit, 1 << 28) or limit == 0:
            raise ProbeRefusal("whitelist_malformed")
    for path in RUNTIME_INJECTED_PATHS:
        if path in paths:
            raise ProbeRefusal("whitelist_malformed")
    return len(paths)


def measure_interpreter(read_interpreter) -> tuple:
    """Return (fingerprint_part, labels).  The full sys.version string feeds the
    fingerprint; only the coarse major.minor and implementation name are emitted."""
    facts = read_interpreter()
    if type(facts) is not dict or set(facts) != {"implementation", "version"}:
        raise ProbeRefusal("interpreter_reader_malformed")
    version = facts["version"]
    if not _bounded_ascii(version, 512):
        raise ProbeRefusal("interpreter_reader_malformed")
    implementation = facts["implementation"]
    if type(implementation) is not dict or set(implementation) != set(IMPLEMENTATION_KEYS):
        raise ProbeRefusal("interpreter_reader_malformed")
    cache_tag = implementation["cache_tag"]
    if cache_tag is not None and not _bounded_ascii(cache_tag, MAX_LABEL_CHARS):
        raise ProbeRefusal("interpreter_reader_malformed")
    if not _bounded_int(implementation["hexversion"], 1 << 63):
        raise ProbeRefusal("interpreter_reader_malformed")
    name = implementation["name"]
    if not _bounded_ascii(name, MAX_LABEL_CHARS) or LABEL_PATTERN.fullmatch(name) is None:
        raise ProbeRefusal("interpreter_reader_malformed")
    raw_version = implementation["version"]
    if type(raw_version) not in (list, tuple) or len(raw_version) != 5:
        raise ProbeRefusal("interpreter_reader_malformed")
    major, minor, micro, releaselevel, serial = raw_version
    for number in (major, minor, micro, serial):
        if not _bounded_int(number, 1 << 20):
            raise ProbeRefusal("interpreter_reader_malformed")
    if not _bounded_ascii(releaselevel, MAX_LABEL_CHARS) or \
            LABEL_PATTERN.fullmatch(releaselevel) is None:
        raise ProbeRefusal("interpreter_reader_malformed")
    part = {
        "implementation": {
            "cache_tag": cache_tag,
            "hexversion": implementation["hexversion"],
            "name": name,
            "version": [major, minor, micro, releaselevel, serial],
        },
        "version": version,
    }
    labels = {"implementation_name": name,
              "python_major_minor": "{}.{}".format(major, minor)}
    return part, labels


def _read_content(read_file, path: str, limit: int, required: bool) -> bytes | None:
    """Read at most limit + 1 bytes of one fixed, whitelisted path."""
    check_path(path)
    data = read_file(path, limit)
    if data is None:
        if required:
            raise ProbeRefusal("content_file_absent", path)
        return None
    if type(data) is not bytes:
        raise ProbeRefusal("content_reader_malformed", path)
    if len(data) > limit:
        raise ProbeRefusal("content_file_oversize", path)
    return data


def parse_os_release(data: bytes) -> dict:
    """Extract only the fixed fields.  No other key, and no value beyond those
    fields, ever leaves this function; a malformed field value refuses."""
    fields = {field: None for field in OS_RELEASE_FIELDS}
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ProbeRefusal("os_release_field_malformed", OS_RELEASE_PATH) from None
    for line in text.splitlines():
        match = OS_RELEASE_LINE.fullmatch(line.strip())
        if match is None:
            continue
        key = match.group(1)
        if key not in OS_RELEASE_FIELDS or fields[key] is not None:
            continue
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if value == "":
            continue
        if not _bounded_ascii(value, MAX_LABEL_CHARS) or \
                LABEL_PATTERN.fullmatch(value) is None:
            raise ProbeRefusal("os_release_field_malformed", OS_RELEASE_PATH)
        fields[key] = value
    return fields


def measure_contents(read_file) -> tuple:
    """Content hashes of the fixed content files, plus the os-release labels.

    /var/lib/dpkg/status is the Debian package state of the whole image, read as
    bytes and reduced to one hash: dpkg-query without a subprocess.  Its absence
    is the deterministic status `absent`, not a crash."""
    parts = {}
    statuses = {}
    labels = {"os_release_id": None, "os_release_version_id": None}
    for label, path, limit, required in CONTENT_PATHS:
        data = _read_content(read_file, path, limit, required)
        if data is None:
            parts[label] = {"sha256": None, "status": "absent"}
            statuses[label] = "absent"
            continue
        parts[label] = {"sha256": _sha(data), "status": "measured"}
        statuses[label] = "measured"
        if label == "os_release":
            fields = parse_os_release(data)
            parts[label]["id"] = fields["ID"]
            parts[label]["version_id"] = fields["VERSION_ID"]
            labels["os_release_id"] = fields["ID"]
            labels["os_release_version_id"] = fields["VERSION_ID"]
    return parts, statuses, labels


def normalise_distribution_name(name: object) -> str:
    """PEP 503 normalisation, so one distribution has one spelling."""
    if not _bounded_ascii(name, MAX_NAME_CHARS) or RAW_NAME_PATTERN.fullmatch(name) is None:
        raise ProbeRefusal("distribution_name_malformed")
    normalised = NAME_SEPARATORS.sub("-", name).lower()
    if NAME_PATTERN.fullmatch(normalised) is None:
        raise ProbeRefusal("distribution_name_malformed")
    return normalised


def measure_distributions(list_distributions) -> tuple:
    """The COMPLETE installed distribution set as sorted (name, version) pairs.

    This is `pip freeze` without a subprocess.  The result is sorted, so the
    enumeration order of the reader -- which follows sys.path and is not
    guaranteed -- cannot change the fingerprint.  Duplicate entries are kept:
    the same distribution installed twice is a real difference.  No version
    string is ever emitted in the report."""
    rows = []
    count = 0
    for entry in list_distributions():
        count += 1
        if count > MAX_DISTRIBUTIONS:
            raise ProbeRefusal("distribution_overcount")
        if type(entry) not in (list, tuple) or len(entry) != 2:
            raise ProbeRefusal("distribution_reader_malformed")
        name, version = entry
        name = normalise_distribution_name(name)
        if type(version) is not str:
            raise ProbeRefusal("distribution_version_malformed")
        if len(version) > MAX_VERSION_CHARS:
            raise ProbeRefusal("distribution_version_oversize")
        if not _bounded_ascii(version, MAX_VERSION_CHARS) or \
                VERSION_PATTERN.fullmatch(version) is None:
            raise ProbeRefusal("distribution_version_malformed")
        rows.append([name, version])
    rows.sort()
    unique = len({row[0] for row in rows})
    return rows, count, unique


def measure_immutable_paths(stat_path) -> tuple:
    """(path, st_size, st_mode) over IMMUTABLE_PATHS.  No mtime is read.

    Absence is a value, not an error: an absent path contributes the same
    deterministic record on every run."""
    rows = []
    emitted = []
    present = 0
    for path in IMMUTABLE_PATHS:
        check_path(path)
        result = stat_path(path)
        if result is None:
            rows.append({"path": path, "status": "absent"})
            emitted.append({"path": path, "status": "absent"})
            continue
        if type(result) is not dict or set(result) != {"st_mode", "st_size"}:
            raise ProbeRefusal("stat_reader_malformed", path)
        if not (_bounded_int(result["st_mode"], MAX_ST_MODE) and
                _bounded_int(result["st_size"], MAX_ST_SIZE)):
            raise ProbeRefusal("stat_value_out_of_range", path)
        rows.append({"path": path, "st_mode": result["st_mode"],
                     "st_size": result["st_size"], "status": "present"})
        emitted.append({"path": path, "status": "present"})
        present += 1
    return rows, emitted, present


def compute_fingerprint(interpreter: dict, contents: dict, distributions: list,
                        immutable_paths: list) -> str:
    """Reduce the whole measurement to one SHA-256.

    This is a pure function of its arguments: identical arguments give an
    identical digest, on any host, in any process, under -O, for ever.  The
    hashed structure is canonical JSON (sorted keys, no whitespace, ASCII)."""
    structure = {
        "contents": contents,
        "distributions": distributions,
        "immutable_paths": immutable_paths,
        "interpreter": interpreter,
        "spec": FINGERPRINT_SPEC_VERSION,
        "whitelist": list(whitelisted_paths()),
    }
    try:
        digest = _sha(canonical(structure))
    except (TypeError, ValueError):
        raise ProbeRefusal("fingerprint_malformed") from None
    if len(digest) != 64 or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ProbeRefusal("fingerprint_malformed")
    return digest


def _base_body() -> dict:
    return {
        "arm": ARM,
        "component_sha256": {
            "debian_version": None,
            "distributions": None,
            "dpkg_status": None,
            "immutable_paths": None,
            "os_release": None,
        },
        "component_status": {
            "debian_version": "not_measured",
            "distributions": "not_measured",
            "dpkg_status": "not_measured",
            "immutable_paths": "not_measured",
            "interpreter": "not_measured",
            "os_release": "not_measured",
        },
        "counts": {
            "absent_immutable_path_count": 0,
            "distribution_count": 0,
            "excluded_prefix_count": len(EXCLUDED_PREFIXES),
            "immutable_path_count": 0,
            "present_immutable_path_count": 0,
            "runtime_injected_refused_count": len(RUNTIME_INJECTED_PATHS),
            "unique_distribution_name_count": 0,
        },
        "cross_run_stability": STABILITY_STATUS,
        "cuda_qualification": CUDA_STATUS,
        "distribution_trust": DISTRIBUTION_TRUST,
        "environment_channel": ENVIRONMENT_STATUS,
        "excluded_prefixes_sha256": _sha(canonical(list(EXCLUDED_PREFIXES))),
        "fingerprint_spec_version": FINGERPRINT_SPEC_VERSION,
        "image_content_fingerprint": None,
        "immutable_paths": [],
        "labels": {"implementation_name": None, "os_release_id": None,
                   "os_release_version_id": None, "python_major_minor": None},
        "mode": MODE,
        "mtime_policy": MTIME_STATUS,
        "probe_version": PROBE_VERSION,
        "refusal_reason": None,
        "refused_path": None,
        "schema": SCHEMA,
        "scientific_outputs": ABSENT,
        "section_B_prewrite_identity": SECTION_B_STATUS,
        "stage2_inputs": ABSENT,
        "verdict": None,
        "whitelist_sha256": _sha(canonical(list(whitelisted_paths()))),
    }


def _seal(body: dict) -> dict:
    report = dict(body)
    report["content_sha256"] = _sha(canonical(body))
    return report


def verify_seal(report: object) -> bool:
    """True when the seal covers exactly the rest of the report."""
    if type(report) is not dict or "content_sha256" not in report:
        return False
    body = {key: value for key, value in report.items() if key != "content_sha256"}
    try:
        return _sha(canonical(body)) == report["content_sha256"]
    except (TypeError, ValueError):
        return False


def refusal_report(reason: str, path: str | None = None) -> dict:
    """A refusal carries the enum reason and at most one whitelisted path.  It
    carries NO fingerprint, no component digest and no partial measurement."""
    body = _base_body()
    body["refusal_reason"] = reason
    body["refused_path"] = path
    body["verdict"] = "refused"
    return _seal(body)


def run_probe(*, read_interpreter, read_file, list_distributions, stat_path) -> dict:
    """Return the sealed report.  Pure in its readers: same inputs, same output.

    Order: whitelist validation, interpreter, content files, distributions, the
    immutable stat pairs.  Any refusal stops before the later reads and yields a
    refusal report with no fingerprint."""
    try:
        path_count = validate_whitelist()
        interpreter, interpreter_labels = measure_interpreter(read_interpreter)
        contents, content_statuses, content_labels = measure_contents(read_file)
        dist_rows, dist_count, unique_names = measure_distributions(list_distributions)
        stat_rows, stat_emitted, present_paths = measure_immutable_paths(stat_path)
        fingerprint = compute_fingerprint(interpreter, contents, dist_rows, stat_rows)
    except ProbeRefusal as refusal:
        return refusal_report(refusal.reason, refusal.path)
    except Exception:
        return refusal_report("reader_error")
    body = _base_body()
    body["component_sha256"] = {
        "debian_version": contents["debian_version"]["sha256"],
        "distributions": _sha(canonical(dist_rows)),
        "dpkg_status": contents["dpkg_status"]["sha256"],
        "immutable_paths": _sha(canonical(stat_rows)),
        "os_release": contents["os_release"]["sha256"],
    }
    body["component_status"] = {
        "debian_version": content_statuses["debian_version"],
        "distributions": "measured" if dist_count else "absent",
        "dpkg_status": content_statuses["dpkg_status"],
        "immutable_paths": ("measured" if present_paths == len(IMMUTABLE_PATHS) else
                            "absent" if present_paths == 0 else "measured_partial"),
        "interpreter": "measured",
        "os_release": content_statuses["os_release"],
    }
    body["counts"] = {
        "absent_immutable_path_count": len(IMMUTABLE_PATHS) - present_paths,
        "distribution_count": dist_count,
        "excluded_prefix_count": len(EXCLUDED_PREFIXES),
        "immutable_path_count": len(IMMUTABLE_PATHS),
        "present_immutable_path_count": present_paths,
        "runtime_injected_refused_count": len(RUNTIME_INJECTED_PATHS),
        "unique_distribution_name_count": unique_names,
    }
    body["image_content_fingerprint"] = fingerprint
    body["immutable_paths"] = stat_emitted
    body["labels"] = {
        "implementation_name": interpreter_labels["implementation_name"],
        "os_release_id": content_labels["os_release_id"],
        "os_release_version_id": content_labels["os_release_version_id"],
        "python_major_minor": interpreter_labels["python_major_minor"],
    }
    body["verdict"] = "fingerprint_measured"
    report = _seal(body)
    if len(report_bytes(report)) > MAX_REPORT_BYTES:
        return refusal_report("report_oversize")
    return report


def live_interpreter() -> dict:
    """sys facts only; no file and no environment variable is touched here."""
    implementation = sys.implementation
    return {
        "implementation": {
            "cache_tag": implementation.cache_tag,
            "hexversion": implementation.hexversion,
            "name": implementation.name,
            "version": list(implementation.version),
        },
        "version": sys.version,
    }


def live_read_file(path: str, limit: int) -> bytes | None:
    """Read at most limit + 1 bytes of one of the fixed content paths."""
    if (path, limit) not in {(fixed, cap) for _, fixed, cap, _ in CONTENT_PATHS}:
        raise ValueError("not a fixed content path")
    try:
        with open(path, "rb") as handle:
            return handle.read(limit + 1)
    except OSError:
        return None


def live_list_distributions() -> tuple:
    """Every installed distribution as (name, version): pip freeze, no subprocess.

    See the module docstring: importlib.metadata resolves against sys.path, so a
    session-writable sys.path entry would make this component non-intrinsic, and
    this probe cannot check that without a directory walk."""
    import importlib.metadata as metadata
    rows = []
    for distribution in metadata.distributions():
        name = distribution.metadata["Name"]
        rows.append((name, distribution.version))
    return tuple(rows)


def live_stat_path(path: str) -> dict | None:
    """stat() one fixed immutable path.  No directory is opened or listed, and
    st_mtime_ns is deliberately not read."""
    if path not in IMMUTABLE_PATHS:
        raise ValueError("not a fixed immutable path")
    try:
        status = os.stat(path)
    except OSError:
        return None
    return {"st_mode": int(status.st_mode), "st_size": int(status.st_size)}


def live_sources() -> dict:
    return {
        "list_distributions": live_list_distributions,
        "read_file": live_read_file,
        "read_interpreter": live_interpreter,
        "stat_path": live_stat_path,
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
    report = run_probe(**(live_sources() if sources is None else sources))
    data = report_bytes(report)
    sys.stdout.write(data.decode("ascii"))
    sys.stdout.flush()
    refused = report["verdict"] == "refused"
    with open(working_dir / (FAILURE_NAME if refused else RECEIPT_NAME), "xb") as handle:
        handle.write(FAILURE_HEADER + data if refused else data)
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
