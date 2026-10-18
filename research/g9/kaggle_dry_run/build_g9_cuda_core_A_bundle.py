#!/usr/bin/env python3
"""Build the offline Kaggle handoff bundle for Gate-9 amendment-A corruption qualification.

Standard library plus a read-only import of the reviewed qualifier's
``build_plan``.  This tool never contacts Kaggle, never reads Kaggle
credentials, never runs nvcc or a GPU, never invokes the qualification CLI and
never pushes.

Two modes:

  --plan     read-only.  Verifies the clean core release, the clean T4 receipt,
             both amendment authority files and the live 12-file source map
             against the current qualifier.build_plan(), and prints a summary.
             It neither reads, requires nor proposes an A release; it writes
             nothing.

  bundling   --reviewed <sha256> --kaggle-user <user> --output-dir <dir>.
             Refuses unless research/decisions/
             GATE_9_CUDA_CORE_CORRUPTION_QUALIFICATION_RELEASE.json exists as a
             canonical owner-approved record whose SHA-256 is exactly
             --reviewed and which binds the current plan content_sha256 and the
             exact 12-file source map.  Every one of the 17 bound files (those
             12, the clean core release, the clean T4 receipt, both amendment
             authority files and the A release) is hash-checked before anything
             is written.  Writes two files into a new or empty directory
             outside the project tree:

  kernel-metadata.json    private Python script, T4 GPU, internet off, no
                          attached sources, no submitted docker_image or
                          pinning-type field; slug derived from the A release SHA
  g9_cuda_core_a_corruption_qualification_kaggle.py
                          self-verifying launcher with the embedded 17-file
                          payload, a fail-closed observed-image preflight and a
                          single launch of the reviewed CLI

No image digest is asserted.  A saved receipt is only
gpu_corruption_checks_passed_pending_image_metadata_audit; a separate post-run
versioned metadata audit and owner acceptance remain required before amendment
A can be declared satisfied.  Output bytes are a pure function of (A-bound
bytes, --kaggle-user).  Pushing is a separate owner-gated act.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import base64
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

# Ignore pre-existing project bytecode while importing the hash-pinned qualifier.
sys.pycache_prefix = str(Path(tempfile.gettempdir()) / ("g9-A-bundle-pycache-isolated-" + uuid.uuid4().hex))

ROOT = Path(__file__).resolve().parents[3]

A_RELEASE_REL = "research/decisions/GATE_9_CUDA_CORE_CORRUPTION_QUALIFICATION_RELEASE.json"
A_RELEASE_SCHEMA = "decisions_os/g9_cuda_core_corruption_qualification_release/v1"
A_RELEASE_KEYS = ("plan_content_sha256", "schema", "source_sha256", "status")
PLAN_SCHEMA = "decisions_os/g9_cuda_core_corruption_qualification_plan/v1"
PLAN_KEYS = frozenset({
    "schema", "mode", "scientific_outputs", "stage2_inputs", "execution_release",
    "core_release_sha256", "clean_dry_run_receipt_sha256", "source_sha256",
    "compile_flags", "mutations", "image_digest_status", "content_sha256",
})
REQUIRED_CATEGORIES = frozenset({
    "accumulation_order", "index_order", "tie_threshold",
    "slack_register_handling", "nonfinite_output",
})
EXPECTED_COMPILE_FLAGS = [
    "-std=c++17", "-O0", "--fmad=false", "--ftz=false",
    "--prec-div=true", "--prec-sqrt=true", "-Xcompiler",
    "-O0,-ffp-contract=off,-fno-fast-math,-fPIC",
]
RECEIPT_SCHEMA = "decisions_os/g9_cuda_core_corruption_qualification_receipt/v1"
RECEIPT_MODE = "non_scientific_corruption_qualification"
RECEIPT_KEYS = frozenset({
    "schema", "mode", "scientific_outputs", "stage2_inputs", "verdict",
    "amendment_A_status", "execution_release_sha256", "plan_content_sha256",
    "source_sha256", "core_release_sha256", "clean_dry_run_receipt_sha256",
    "baseline_report_sha256", "platform_probe", "runtime_build_observed",
    "nvcc_version", "compiler_flags", "image_digest_status", "mutations",
    "content_sha256",
})
PENDING_VERDICT = "gpu_corruption_checks_passed_pending_image_metadata_audit"
AMENDMENT_A_STATUS = "not_satisfied_pending_post_run_audit_and_owner_acceptance"
IMAGE_DIGEST_STATUS = "post_run_metadata_audit_required"
ALLOW_ENV = "G9_ALLOW_NONSCIENTIFIC_CUDA_CORRUPTION_QUALIFICATION"
CLI_REL = "research/g9/run_stage2_cuda_core_corruption_qualification.py"
QUALIFIER_REL = "research/g9/cuda_qualification/stage2_cuda_core_corruption_qualification.py"
QUALIFIER_MODULE = "research.g9.cuda_qualification.stage2_cuda_core_corruption_qualification"

CORE_RELEASE_REL = "research/decisions/GATE_9_CUDA_CORE_DRY_RUN_RELEASE.json"
CORE_RELEASE_SHA256 = "50f25827ef07b8fcbf3f19223f3982b486f1b11c5d71a7d0c037fd1c6f5328a9"
CORE_RELEASE_SCHEMA = "decisions_os/g9_cuda_core_dry_run_release/v1"
CLEAN_RECEIPT_REL = "research/g9/kaggle_dry_run/GATE_9_KAGGLE_CORE_V3_VERSION1_RECEIPT.json"
CLEAN_RECEIPT_SHA256 = "41a32675e667ffe8e9fb0e2a5d15b191c242f39a221ce9a3d941152f41530859"
AUTHORITY_SHA256 = {
    "research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_APPROVAL.md":
        "a2b0747a5db2721f046420c120848e6bb4ea82505b2f5a16c4f8da64671377d4",
    "research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md":
        "589fdc29d71cd5f70c0734e927d109dc00b389b40cc7c485e56a655f41fd57cf",
}
CLEAN_SOURCE_RELS = frozenset({
    "research/g9/cuda_qualification/stage2_cuda_core_bridge.cu",
    "research/g9/cuda_qualification/stage2_cuda_core_bridge.py",
    "research/g9/cuda_qualification/stage2_cuda_core_qualification.py",
    "research/g9/cuda_qualification/stage2_cuda_core_stream_engine.cu",
    "research/g9/cuda_qualification/stage2_cuda_core_stream_engine.py",
    "research/g9/cuda_qualification/stage2_cuda_execution_contract.py",
    "research/g9/cuda_qualification/stage2_cuda_input_frame.py",
    "research/g9/run_stage2_cuda_core_qualification.py",
})
SOURCE_RELS = tuple(sorted({
    *CLEAN_SOURCE_RELS,
    QUALIFIER_REL,
    CLI_REL,
    "research/g9/verify_stage2_cuda_core_corruption_qualification_fixtures.py",
    "research/g9/verify_stage2_cuda_core_stream_engine_host_emulation.py",
}))
FIXED_RELS = (CORE_RELEASE_REL, CLEAN_RECEIPT_REL, *sorted(AUTHORITY_SHA256))
BUNDLE_RELS = frozenset({*SOURCE_RELS, *FIXED_RELS, A_RELEASE_REL})
BUNDLE_FILE_COUNT = 17

KERNEL_SLUG_PREFIX = "g9-cuda-core-a-corruption-qualification-"
KERNEL_TITLE_PREFIX = "G9 CUDA Core A Corruption Qualification "
CODE_FILE = "g9_cuda_core_a_corruption_qualification_kaggle.py"
METADATA_FILE = "kernel-metadata.json"
SUBMITTED_DOCKER_IMAGE = None
REQUIRED_IMAGE_TYPE = "gpu"
BUILD_ENV_NAMES = ("BUILD_DATE", "GIT_COMMIT", "CUDA_VERSION")
RECEIPT_NAME = "g9_cuda_core_a_corruption_qualification_receipt.json"
FAILURE_NAME = "g9_cuda_core_a_corruption_qualification_failure.log"
# A cap on the single CLI launch, not a runtime guarantee.  The qualifier's own
# per-step subprocess timeouts sum to 5670 s; compile and device times on the
# allocated image are unobserved until a run happens.
LAUNCH_TIMEOUT_SECONDS = 7200

USER_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9]|-(?=[a-z0-9])){0,48}")
REL_PATTERN = re.compile(r"research(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*)+")
HEX = frozenset("0123456789abcdef")


class BundleError(RuntimeError):
    """The bundle or plan cannot be produced safely."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BundleError(message)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _is_sha(value: object) -> bool:
    return type(value) is str and len(value) == 64 and set(value) <= HEX


def validate_kaggle_user(value: object) -> str:
    _require(type(value) is str and USER_PATTERN.fullmatch(value) is not None,
             "--kaggle-user must be a lowercase Kaggle username slug")
    return value


def validate_reviewed(value: object) -> str:
    _require(_is_sha(value), "--reviewed must be the exact lowercase SHA-256 of the approved A release")
    return value


def kernel_slug(reviewed: str) -> str:
    return KERNEL_SLUG_PREFIX + validate_reviewed(reviewed)[:8]


def kernel_title(reviewed: str) -> str:
    return KERNEL_TITLE_PREFIX + validate_reviewed(reviewed)[:8]


def _read_regular(root: Path, relative: str) -> bytes:
    _require(REL_PATTERN.fullmatch(relative) is not None and ".." not in relative.split("/"),
             f"bound path is not a plain research/ path: {relative!r}")
    path = root / relative
    _require(not path.is_symlink() and path.is_file(), f"bound file is missing: {relative}")
    return path.read_bytes()


def _canonical_object(data: bytes, label: str) -> dict:
    try:
        value = json.loads(data)
    except ValueError as exc:
        raise BundleError(label + " is not JSON") from exc
    _require(type(value) is dict and data == _canonical(value) + b"\n",
             label + " is not canonical JSON with one final LF")
    return value


# --- current qualifier plan ---------------------------------------------------

def _load_qualifier():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        qualifier = importlib.import_module(QUALIFIER_MODULE)
    except Exception as exc:
        raise BundleError("reviewed qualifier cannot be imported: " + type(exc).__name__) from exc
    _require(Path(qualifier.__file__).resolve() == ROOT / QUALIFIER_REL,
             "imported qualifier is not this project's reviewed file")
    clean = qualifier.clean
    _require(qualifier.RELEASE_REL == A_RELEASE_REL and qualifier.RELEASE_SCHEMA == A_RELEASE_SCHEMA and
             qualifier.PLAN_SCHEMA == PLAN_SCHEMA and qualifier.RECEIPT_SCHEMA == RECEIPT_SCHEMA and
             qualifier.ALLOW_ENV == ALLOW_ENV and
             qualifier.CORE_RELEASE_REL == CORE_RELEASE_REL and
             qualifier.CORE_RELEASE_SHA256 == CORE_RELEASE_SHA256 and
             qualifier.CLEAN_RECEIPT_REL == CLEAN_RECEIPT_REL and
             qualifier.CLEAN_RECEIPT_SHA256 == CLEAN_RECEIPT_SHA256 and
             tuple(qualifier.SOURCE_RELS) == SOURCE_RELS and
             frozenset(clean.SOURCE_RELS) == CLEAN_SOURCE_RELS and
             clean.RELEASE_SCHEMA == CORE_RELEASE_SCHEMA and
             {clean.AMENDMENT_REL: clean.AMENDMENT_SHA256,
              clean.APPROVAL_REL: clean.APPROVAL_SHA256} == AUTHORITY_SHA256,
             "builder pins differ from the reviewed qualifier")
    return qualifier


def check_plan(plan: object) -> dict:
    """Independently re-check a qualifier plan's self-hash, scope and 12-file map."""
    _require(type(plan) is dict and set(plan) == PLAN_KEYS and
             _is_sha(plan.get("content_sha256")) and
             type(plan.get("source_sha256")) is dict, "qualifier plan is malformed")
    body = {key: value for key, value in plan.items() if key != "content_sha256"}
    _require(plan["content_sha256"] == _sha(_canonical(body)),
             "qualifier plan content_sha256 does not match its body")
    _require(plan.get("schema") == PLAN_SCHEMA and
             plan.get("mode") == "non_scientific_corruption_plan" and
             plan.get("stage2_inputs") == "intentionally absent" and
             plan.get("execution_release") == "separate_owner_release_required" and
             plan.get("core_release_sha256") == CORE_RELEASE_SHA256 and
             plan.get("clean_dry_run_receipt_sha256") == CLEAN_RECEIPT_SHA256 and
             plan.get("scientific_outputs") == "intentionally absent" and
             plan.get("image_digest_status") == IMAGE_DIGEST_STATUS,
             "qualifier plan scope or bindings drift")
    sources = plan["source_sha256"]
    _require(tuple(sorted(sources)) == SOURCE_RELS and all(_is_sha(v) for v in sources.values()),
             "qualifier plan does not bind the exact 12-file source map")
    rows = plan["mutations"]
    _require(type(rows) is list and len(rows) == 8 and
             all(type(row) is dict and set(row) == {"label", "category", "source_sha256"} and
                 type(row["label"]) is str and bool(row["label"]) and
                 type(row["category"]) is str and _is_sha(row["source_sha256"])
                 for row in rows) and
             len({row["label"] for row in rows}) == 8 and
             len({row["source_sha256"] for row in rows}) == 8 and
             {row["category"] for row in rows} == REQUIRED_CATEGORIES,
             "qualifier plan does not bind eight distinct required mutations")
    _require(plan["compile_flags"] == EXPECTED_COMPILE_FLAGS,
             "qualifier plan numerical compiler flags drift")
    return plan


def current_plan() -> dict:
    """The current read-only qualifier plan; no nvcc lookup or CUDA operation."""
    qualifier = _load_qualifier()
    try:
        plan = qualifier.build_plan()
    except qualifier.CorruptionQualificationError as exc:
        raise BundleError("current qualifier plan refused: " + str(exc)) from exc
    return check_plan(plan)


# --- bound files --------------------------------------------------------------

def load_fixed_payload(root: Path = ROOT) -> dict[str, tuple[str, bytes]]:
    """The clean core release, clean T4 receipt and both authorities, hash-checked."""
    payload: dict[str, tuple[str, bytes]] = {}
    core_bytes = _read_regular(root, CORE_RELEASE_REL)
    _require(_sha(core_bytes) == CORE_RELEASE_SHA256, "approved clean core release hash drift")
    core = _canonical_object(core_bytes, "clean core release")
    _require(set(core) == {"schema", "status", "source_sha256", "authorities"} and
             core["schema"] == CORE_RELEASE_SCHEMA and core["status"] == "approved" and
             core["authorities"] == AUTHORITY_SHA256 and type(core["source_sha256"]) is dict and
             set(core["source_sha256"]) == CLEAN_SOURCE_RELS,
             "clean core release shape or authority drift")
    payload[CORE_RELEASE_REL] = (CORE_RELEASE_SHA256, core_bytes)
    receipt_bytes = _read_regular(root, CLEAN_RECEIPT_REL)
    _require(_sha(receipt_bytes) == CLEAN_RECEIPT_SHA256, "clean T4 receipt hash drift")
    payload[CLEAN_RECEIPT_REL] = (CLEAN_RECEIPT_SHA256, receipt_bytes)
    for relative, expected in sorted(AUTHORITY_SHA256.items()):
        data = _read_regular(root, relative)
        _require(_sha(data) == expected, "amendment authority hash drift: " + relative)
        payload[relative] = (expected, data)
    return payload


def load_sources(root: Path, table: dict) -> dict[str, tuple[str, bytes]]:
    _require(tuple(sorted(table)) == SOURCE_RELS, "source table is not the exact 12-file map")
    payload = {}
    for relative in SOURCE_RELS:
        data = _read_regular(root, relative)
        _require(_sha(data) == table[relative], "bound source hash drift: " + relative)
        payload[relative] = (table[relative], data)
    return payload


def load_a_release(root: Path, reviewed: str) -> tuple[bytes, dict]:
    path = root / A_RELEASE_REL
    _require(not path.is_symlink() and path.is_file(),
             "approved A release is absent: bundling is refused until a canonical owner-approved "
             + A_RELEASE_REL + " exists")
    raw = _read_regular(root, A_RELEASE_REL)
    _require(_sha(raw) == validate_reviewed(reviewed), "A release SHA-256 differs from --reviewed")
    release = _canonical_object(raw, "A release")
    _require(tuple(sorted(release)) == A_RELEASE_KEYS and release["schema"] == A_RELEASE_SCHEMA and
             release["status"] == "approved", "A release is not an approved record of the reviewed schema")
    sources = release["source_sha256"]
    _require(_is_sha(release["plan_content_sha256"]) and type(sources) is dict and
             tuple(sorted(sources)) == SOURCE_RELS and all(_is_sha(v) for v in sources.values()),
             "A release does not bind a plan SHA-256 and the exact 12-file source map")
    return raw, release


def load_a_payload(root: Path, reviewed: str) -> dict[str, tuple[str, bytes]]:
    """Exactly the 17 A-bound files, each hash-checked; refuses before any plan import."""
    fixed = load_fixed_payload(root)
    raw, release = load_a_release(root, reviewed)
    core = json.loads(fixed[CORE_RELEASE_REL][1])
    _require(core["source_sha256"].items() <= release["source_sha256"].items(),
             "A release does not carry the approved clean core source bytes")
    payload = {**fixed, **load_sources(root, release["source_sha256"]), A_RELEASE_REL: (reviewed, raw)}
    _require(len(payload) == BUNDLE_FILE_COUNT and set(payload) == BUNDLE_RELS,
             "A payload is not exactly the 17-file bound set")
    return dict(sorted(payload.items()))


def plan_summary(root: Path = ROOT, plan: dict | None = None) -> dict:
    """Read-only: verify the 16 non-A files against the current plan.  No A release is read."""
    fixed = load_fixed_payload(root)
    plan = check_plan(current_plan() if plan is None else plan)
    load_sources(root, plan["source_sha256"])
    core = json.loads(fixed[CORE_RELEASE_REL][1])
    _require(core["source_sha256"].items() <= plan["source_sha256"].items(),
             "current plan does not carry the approved clean core source bytes")
    return {
        "schema": "decisions_os/g9_cuda_core_A_kaggle_bundle_plan/v1",
        "mode": "read_only_plan",
        "plan_content_sha256": plan["content_sha256"],
        "source_sha256": plan["source_sha256"],
        "fixed_sha256": {relative: digest for relative, (digest, _) in sorted(fixed.items())},
        "a_release_rel": A_RELEASE_REL,
        "a_release": ("not read; bundling requires a canonical owner-approved A release "
                      "and its exact SHA-256 via --reviewed"),
        "bundle_file_count": BUNDLE_FILE_COUNT,
        "writes": "none",
    }


# --- generated files ----------------------------------------------------------

def build_metadata(kaggle_user: str, reviewed: str) -> bytes:
    validate_kaggle_user(kaggle_user)
    metadata = {
        "id": f"{kaggle_user}/{kernel_slug(reviewed)}",
        "title": kernel_title(reviewed),
        "code_file": CODE_FILE,
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": False,
        "machine_shape": "NvidiaTeslaT4",
        "keywords": [],
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    return (json.dumps(metadata, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("ascii")


def _payload_literal(payload: dict[str, tuple[str, bytes]]) -> str:
    lines = ["PAYLOAD = ("]
    for relative, (digest, data) in payload.items():
        encoded = base64.b64encode(data).decode("ascii")
        lines.append(f"    ({relative!r}, {digest!r}, (")
        for start in range(0, len(encoded), 76):
            lines.append(f"        {encoded[start:start + 76]!r},")
        lines.append("    )),")
    lines.append(")")
    return "\n".join(lines)


SCRIPT_TEMPLATE = r'''#!/usr/bin/env python3
"""GENERATED - Gate-9 non-scientific CUDA corruption qualification (amendment A), Kaggle launcher.

Do not edit.  Generated offline by
research/g9/kaggle_dry_run/build_g9_cuda_core_A_bundle.py.

Order of operations (fail closed at every step):
  1. decode the 17 embedded files, check every SHA-256, and require the set to
     be exactly the A release's 12-file source map, the clean core release, the
     clean T4 receipt, both amendment authority files and the A release itself;
  2. stage them under a fresh temporary root preserving the research/... layout
     and re-hash the staged bytes from disk;
  3. pre-launch check, executing nothing: observed GPU image type,
     CUDA_HOME/bin/nvcc as the nvcc on PATH, an NVIDIA character device, and
     BUILD_DATE, GIT_COMMIT and CUDA_VERSION as bounded printable ASCII;
  4. only then execute the reviewed CLI exactly once:
       run_stage2_cuda_core_corruption_qualification.py --qualify-corruptions --reviewed <A release sha>
     with cwd = staged root; no retry and no alternate execution path;
  5. on rc 0 with an exactly receipt-shaped stdout, save only that stdout as the
     receipt in /kaggle/working; otherwise write only a bounded failure log.
LAUNCH_TIMEOUT_SECONDS caps the single launch; it is not a runtime guarantee.
No image digest is submitted or asserted.  A saved receipt is only a pending
observation: amendment A stays not satisfied until a separate post-run
versioned metadata audit and owner acceptance.  Nothing here is scientific:
no Stage-2 candidate, instance or result is read.
"""

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

A_RELEASE_SHA256 = @@A_RELEASE_SHA256@@
A_RELEASE_REL = @@A_RELEASE_REL@@
A_RELEASE_SCHEMA = @@A_RELEASE_SCHEMA@@
A_RELEASE_KEYS = @@A_RELEASE_KEYS@@
PLAN_CONTENT_SHA256 = @@PLAN_CONTENT_SHA256@@
CLI_REL = @@CLI_REL@@
SOURCE_RELS = @@SOURCE_RELS@@
CORE_RELEASE_REL = @@CORE_RELEASE_REL@@
CORE_RELEASE_SHA256 = @@CORE_RELEASE_SHA256@@
CLEAN_RECEIPT_REL = @@CLEAN_RECEIPT_REL@@
CLEAN_RECEIPT_SHA256 = @@CLEAN_RECEIPT_SHA256@@
AUTHORITY_SHA256 = @@AUTHORITY_SHA256@@
ALLOW_ENV = @@ALLOW_ENV@@
RECEIPT_SCHEMA = @@RECEIPT_SCHEMA@@
RECEIPT_MODE = @@RECEIPT_MODE@@
RECEIPT_KEYS = @@RECEIPT_KEYS@@
PLAN_MUTATIONS = @@PLAN_MUTATIONS@@
COMPILE_FLAGS = @@COMPILE_FLAGS@@
PENDING_VERDICT = @@PENDING_VERDICT@@
AMENDMENT_A_STATUS = @@AMENDMENT_A_STATUS@@
IMAGE_DIGEST_STATUS = @@IMAGE_DIGEST_STATUS@@
SUBMITTED_DOCKER_IMAGE = @@SUBMITTED_DOCKER_IMAGE@@
REQUIRED_IMAGE_TYPE = @@REQUIRED_IMAGE_TYPE@@
BUILD_ENV_NAMES = @@BUILD_ENV_NAMES@@
RECEIPT_NAME = @@RECEIPT_NAME@@
FAILURE_NAME = @@FAILURE_NAME@@
# A cap on the single launch, not a guarantee that the run finishes within it.
LAUNCH_TIMEOUT_SECONDS = @@LAUNCH_TIMEOUT_SECONDS@@
EXPECTED_FILE_COUNT = @@EXPECTED_FILE_COUNT@@
WORKING_DIR = Path("/kaggle/working")
ENVIRON = os.environ
DEV_DIR = Path("/dev")
LOG_LIMIT_BYTES = 16384
DIAGNOSTIC_VALUE_LIMIT = 256
DIAGNOSTIC_ITEM_LIMIT = 16
BUILD_VALUE_LIMIT = 128
DEVICE_NODE = re.compile(r"nvidia[0-9]+")
REL_PATTERN = re.compile(r"research(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*)+")
ENVIRONMENT_PREFIX = "Gate-9 A pre-launch environment: "

@@PAYLOAD@@


class QualificationRefusal(RuntimeError):
    pass


def _require(condition, message):
    if not condition:
        raise QualificationRefusal(message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _canonical_object(data, label):
    value = json.loads(data.decode("ascii"))
    _require(type(value) is dict and data == (_canonical(value) + "\n").encode("ascii"),
             label + " is not canonical JSON with one final LF")
    return value


def verified_payload():
    """Decode and hash-check every embedded file and the exact A-bound file set.
    No filesystem or process side effects."""
    _require(len(PAYLOAD) == EXPECTED_FILE_COUNT, "embedded payload does not hold exactly 17 files")
    files = {}
    for relative, digest, chunks in PAYLOAD:
        _require(type(relative) is str and REL_PATTERN.fullmatch(relative) is not None and
                 ".." not in relative.split("/"), "embedded path is not a plain research/ path")
        _require(relative not in files, "duplicate embedded path: " + relative)
        data = base64.b64decode("".join(chunks).encode("ascii"), validate=True)
        _require(_sha(data) == digest, "embedded SHA-256 mismatch: " + relative)
        files[relative] = (digest, data)
    _require(A_RELEASE_REL in files and files[A_RELEASE_REL][0] == A_RELEASE_SHA256,
             "embedded A release is not the reviewed A release")
    release = _canonical_object(files[A_RELEASE_REL][1], "embedded A release")
    sources = release.get("source_sha256")
    _require(tuple(sorted(release)) == A_RELEASE_KEYS and release["schema"] == A_RELEASE_SCHEMA and
             release["status"] == "approved" and release["plan_content_sha256"] == PLAN_CONTENT_SHA256 and
             type(sources) is dict and tuple(sorted(sources)) == SOURCE_RELS and CLI_REL in sources,
             "embedded A release does not approve the reviewed plan and 12-file source map")
    _require(CORE_RELEASE_REL in files and files[CORE_RELEASE_REL][0] == CORE_RELEASE_SHA256,
             "embedded clean core release is not the approved clean release")
    core = _canonical_object(files[CORE_RELEASE_REL][1], "embedded clean core release")
    core_sources = core.get("source_sha256")
    _require(core.get("status") == "approved" and core.get("authorities") == AUTHORITY_SHA256 and
             type(core_sources) is dict and core_sources.items() <= sources.items(),
             "embedded clean core release does not bind the A sources and authorities")
    bound = dict(sources)
    bound.update(AUTHORITY_SHA256)
    bound[CORE_RELEASE_REL] = CORE_RELEASE_SHA256
    bound[CLEAN_RECEIPT_REL] = CLEAN_RECEIPT_SHA256
    bound[A_RELEASE_REL] = A_RELEASE_SHA256
    _require(len(bound) == EXPECTED_FILE_COUNT and
             bound == {relative: digest for relative, (digest, _) in files.items()},
             "embedded payload is not exactly the A-bound 17-file set")
    return files, release


def stage(files, root):
    _require(not any(root.iterdir()), "staging root is not fresh")
    for relative, (digest, data) in sorted(files.items()):
        path = root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "xb") as handle:
            handle.write(data)
    staged = sorted(str(p.relative_to(root)).replace(os.sep, "/")
                    for p in root.rglob("*") if p.is_file() or p.is_symlink())
    _require(staged == sorted(files), "staged tree is not exactly the A-bound file set")
    for relative, (digest, _) in files.items():
        _require(_sha(root.joinpath(*relative.split("/")).read_bytes()) == digest,
                 "staged SHA-256 mismatch: " + relative)


def _bounded(text):
    data = (text or "").encode("utf-8", "replace")
    if len(data) > LOG_LIMIT_BYTES:
        data = b"...[truncated]...\n" + data[-LOG_LIMIT_BYTES:]
    return data.decode("utf-8", "replace")


def _text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value if isinstance(value, str) else ""


def _diagnostics_json(diagnostics):
    return json.dumps(diagnostics, sort_keys=True, indent=2, ensure_ascii=True)


def write_failure(summary, returncode=None, stdout="", stderr="", diagnostics=None):
    body = ("Gate-9 CUDA core amendment-A corruption qualification FAILED (no receipt written)\n"
            "a_release_sha256: " + A_RELEASE_SHA256 + "\n"
            "image_digest_status: " + IMAGE_DIGEST_STATUS + " (no digest submitted or asserted)\n"
            "amendment_A_status: not satisfied\n"
            "summary: " + _bounded(summary)[:2000] + "\n"
            "returncode: " + repr(returncode) + "\n"
            "--- pre-launch environment diagnostics ---\n" +
            (_diagnostics_json(diagnostics) if diagnostics is not None else "not recorded") + "\n"
            "--- stdout (bounded tail) ---\n" + _bounded(stdout) + "\n"
            "--- stderr (bounded tail) ---\n" + _bounded(stderr) + "\n")
    with open(WORKING_DIR / FAILURE_NAME, "x", encoding="utf-8") as handle:
        handle.write(body)
    print("FAIL Gate-9 CUDA core amendment-A qualification; see " + str(WORKING_DIR / FAILURE_NAME),
          file=sys.stderr)


def _clip(value):
    return None if value is None else str(value)[:DIAGNOSTIC_VALUE_LIMIT]


def _device_nodes():
    try:
        names = sorted(p.name for p in DEV_DIR.iterdir() if DEVICE_NODE.fullmatch(p.name))
    except OSError:
        return []
    return [name for name in names if (DEV_DIR / name).is_char_device()][:DIAGNOSTIC_ITEM_LIMIT]


def _valid_build_value(value):
    return (type(value) is str and 0 < len(value) <= BUILD_VALUE_LIMIT and
            value.isascii() and value.isprintable())


def environment_check():
    """Observed image/toolchain/device/build preflight.  Reads only named
    environment variables, a PATH lookup and /dev entries; executes nothing.
    Returns (problems, diagnostics); any problem refuses the launch."""
    path_entries = [entry for entry in ENVIRON.get("PATH", "").split(os.pathsep) if entry]
    cuda_home = ENVIRON.get("CUDA_HOME")
    cuda_bin = (os.path.normpath(os.path.join(cuda_home, "bin"))
                if cuda_home and os.path.isabs(cuda_home) else None)
    cuda_bin_on_path = cuda_bin is not None and cuda_bin in {os.path.normpath(e) for e in path_entries}
    nvcc = shutil.which("nvcc", path=os.pathsep.join(path_entries)) if path_entries else None
    devices = _device_nodes()
    diagnostics = {
        "submitted_docker_image": SUBMITTED_DOCKER_IMAGE,
        "image_digest_status": IMAGE_DIGEST_STATUS,
        "COLAB_IMAGE_TYPE": _clip(ENVIRON.get("COLAB_IMAGE_TYPE")),
        "build_env": {key: _clip(ENVIRON.get(key)) for key in BUILD_ENV_NAMES},
        "CUDA_HOME": _clip(cuda_home),
        "cuda_home_bin_on_path": cuda_bin_on_path,
        "nvcc_path": _clip(nvcc),
        "nvidia_device_nodes": devices,
    }
    problems = []
    if ENVIRON.get("COLAB_IMAGE_TYPE") != REQUIRED_IMAGE_TYPE:
        problems.append("COLAB_IMAGE_TYPE is not gpu")
    if cuda_bin is None:
        problems.append("CUDA_HOME is unset or not absolute")
    elif not cuda_bin_on_path:
        problems.append("CUDA_HOME/bin is not on PATH")
    if nvcc is None:
        problems.append("nvcc is not an executable on PATH")
    elif cuda_bin is not None and os.path.normpath(nvcc) != os.path.join(cuda_bin, "nvcc"):
        problems.append("nvcc on PATH is not CUDA_HOME/bin/nvcc")
    if not devices:
        problems.append("no /dev/nvidiaN character device")
    for key in BUILD_ENV_NAMES:
        if not _valid_build_value(ENVIRON.get(key)):
            problems.append(key + " is missing or not 1-128 printable ASCII characters")
    diagnostics["problems"] = problems
    return problems, diagnostics


def receipt_ok(stdout, release):
    """Exact receipt shape: canonical bytes, self-hash, and the pending A scope."""
    try:
        receipt = json.loads(stdout)
    except ValueError:
        return False
    if type(receipt) is not dict:
        return False
    body = {key: value for key, value in receipt.items() if key != "content_sha256"}
    mutations = receipt.get("mutations")
    probe = receipt.get("platform_probe")
    runtime = receipt.get("runtime_build_observed")
    if (set(receipt) != set(RECEIPT_KEYS) or type(mutations) is not list or
            len(mutations) != len(PLAN_MUTATIONS) or type(probe) is not dict or
            set(probe) != {"gpu_name", "compute_capability", "cuda_driver_version",
                           "cuda_runtime_version"} or
            not all(type(value) is str and value for value in probe.values()) or
            type(runtime) is not dict or
            set(runtime) != {"BUILD_DATE", "GIT_COMMIT", "CUDA_VERSION",
                             "COLAB_IMAGE_TYPE", "cuda_home", "nvcc_path",
                             "nvidia_device_count", "python_version", "numpy_version"} or
            not all(type(runtime[key]) is str and runtime[key] for key in
                    ("BUILD_DATE", "GIT_COMMIT", "CUDA_VERSION", "cuda_home",
                     "nvcc_path", "python_version", "numpy_version")) or
            runtime["COLAB_IMAGE_TYPE"] != "gpu" or
            type(runtime["nvidia_device_count"]) is not int or
            runtime["nvidia_device_count"] < 1):
        return False
    for actual, planned in zip(mutations, PLAN_MUTATIONS):
        if (type(actual) is not dict or
                set(actual) != {"label", "category", "source_sha256",
                                "device_self_test_rejected", "python_reference_rejected",
                                "rejection_reason"} or
                any(actual[key] != planned[key] for key in
                    ("label", "category", "source_sha256")) or
                type(actual["device_self_test_rejected"]) is not bool or
                actual["python_reference_rejected"] is not True or
                type(actual["rejection_reason"]) is not str or
                not 0 < len(actual["rejection_reason"]) <= 200):
            return False
    baseline_hash = receipt.get("baseline_report_sha256")
    return (stdout == _canonical(receipt) + "\n" and
            receipt.get("content_sha256") == _sha(_canonical(body).encode("ascii")) and
            type(baseline_hash) is str and len(baseline_hash) == 64 and
            set(baseline_hash) <= set("0123456789abcdef") and
            receipt.get("schema") == RECEIPT_SCHEMA and
            receipt.get("execution_release_sha256") == A_RELEASE_SHA256 and
            receipt.get("mode") == RECEIPT_MODE and
            receipt.get("scientific_outputs") == "intentionally absent" and
            receipt.get("stage2_inputs") == "intentionally absent" and
            receipt.get("verdict") == PENDING_VERDICT and
            receipt.get("amendment_A_status") == AMENDMENT_A_STATUS and
            receipt.get("image_digest_status") == IMAGE_DIGEST_STATUS and
            receipt.get("plan_content_sha256") == PLAN_CONTENT_SHA256 and
            receipt.get("source_sha256") == release["source_sha256"] and
            receipt.get("core_release_sha256") == CORE_RELEASE_SHA256 and
            receipt.get("clean_dry_run_receipt_sha256") == CLEAN_RECEIPT_SHA256 and
            receipt.get("compiler_flags") == COMPILE_FLAGS and
            type(receipt.get("nvcc_version")) is str and bool(receipt["nvcc_version"]))


def launch(root):
    """The single execution of the reviewed CLI; called only after all hash and environment checks."""
    env = dict(ENVIRON)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env[ALLOW_ENV] = "1"
    command = [sys.executable, CLI_REL, "--qualify-corruptions", "--reviewed", A_RELEASE_SHA256]
    return subprocess.run(command, cwd=str(root), env=env, text=True, capture_output=True,
                          errors="replace", check=False, timeout=LAUNCH_TIMEOUT_SECONDS)


def main():
    _require(WORKING_DIR.is_dir(), "Kaggle working directory is unavailable")
    for name in (RECEIPT_NAME, FAILURE_NAME):
        _require(not (WORKING_DIR / name).exists(), "output already exists: " + name)
    try:
        files, release = verified_payload()
    except Exception as exc:
        write_failure("pre-launch payload verification refused: " + str(exc))
        return 2
    with tempfile.TemporaryDirectory(prefix="g9-core-A-stage-") as temporary:
        root = Path(temporary)
        try:
            stage(files, root)
        except Exception as exc:
            write_failure("pre-launch staging verification refused: " + str(exc))
            return 2
        try:
            problems, diagnostics = environment_check()
        except Exception as exc:
            write_failure("pre-launch environment check could not complete: " + str(exc))
            return 2
        print(ENVIRONMENT_PREFIX + json.dumps(diagnostics, sort_keys=True, ensure_ascii=True))
        if problems:
            write_failure("pre-launch environment check refused: " + "; ".join(problems),
                          diagnostics=diagnostics)
            return 2
        try:
            outcome = launch(root)
        except subprocess.TimeoutExpired as exc:
            write_failure("reviewed CLI exceeded the " + str(LAUNCH_TIMEOUT_SECONDS) +
                          "-second launch cap; not retried", None,
                          _text(exc.stdout), _text(exc.stderr), diagnostics)
            return 1
        except OSError as exc:
            write_failure("reviewed CLI could not start: " + str(exc), diagnostics=diagnostics)
            return 1
    if outcome.returncode == 0 and receipt_ok(outcome.stdout, release):
        with open(WORKING_DIR / RECEIPT_NAME, "x", encoding="ascii") as handle:
            handle.write(outcome.stdout)
        print("PASS (pending post-run image metadata audit and owner acceptance; amendment A not "
              "satisfied) Gate-9 CUDA corruption checks; receipt: " + str(WORKING_DIR / RECEIPT_NAME))
        return 0
    summary = ("reviewed CLI returned nonzero status" if outcome.returncode != 0
               else "reviewed CLI returned 0 without an exactly receipt-shaped stdout")
    write_failure(summary, outcome.returncode, outcome.stdout, outcome.stderr, diagnostics)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


def build_script(payload: dict[str, tuple[str, bytes]], reviewed: str, plan: dict) -> bytes:
    validate_reviewed(reviewed)
    check_plan(plan)
    _require(len(payload) == BUNDLE_FILE_COUNT and set(payload) == BUNDLE_RELS and
             payload[A_RELEASE_REL][0] == reviewed, "payload is not exactly the 17 A-bound files")
    values = {
        "A_RELEASE_SHA256": reviewed, "A_RELEASE_REL": A_RELEASE_REL,
        "A_RELEASE_SCHEMA": A_RELEASE_SCHEMA, "A_RELEASE_KEYS": A_RELEASE_KEYS,
        "PLAN_CONTENT_SHA256": plan["content_sha256"], "CLI_REL": CLI_REL, "SOURCE_RELS": SOURCE_RELS,
        "CORE_RELEASE_REL": CORE_RELEASE_REL, "CORE_RELEASE_SHA256": CORE_RELEASE_SHA256,
        "CLEAN_RECEIPT_REL": CLEAN_RECEIPT_REL, "CLEAN_RECEIPT_SHA256": CLEAN_RECEIPT_SHA256,
        "AUTHORITY_SHA256": dict(sorted(AUTHORITY_SHA256.items())), "ALLOW_ENV": ALLOW_ENV,
        "RECEIPT_SCHEMA": RECEIPT_SCHEMA, "RECEIPT_MODE": RECEIPT_MODE,
        "RECEIPT_KEYS": tuple(sorted(RECEIPT_KEYS)),
        "PLAN_MUTATIONS": tuple(plan["mutations"]),
        "COMPILE_FLAGS": plan["compile_flags"],
        "PENDING_VERDICT": PENDING_VERDICT, "AMENDMENT_A_STATUS": AMENDMENT_A_STATUS,
        "IMAGE_DIGEST_STATUS": IMAGE_DIGEST_STATUS, "SUBMITTED_DOCKER_IMAGE": SUBMITTED_DOCKER_IMAGE,
        "REQUIRED_IMAGE_TYPE": REQUIRED_IMAGE_TYPE, "BUILD_ENV_NAMES": BUILD_ENV_NAMES,
        "RECEIPT_NAME": RECEIPT_NAME, "FAILURE_NAME": FAILURE_NAME,
        "LAUNCH_TIMEOUT_SECONDS": LAUNCH_TIMEOUT_SECONDS, "EXPECTED_FILE_COUNT": BUNDLE_FILE_COUNT,
    }
    text = SCRIPT_TEMPLATE
    for key, value in values.items():
        token = "@@" + key + "@@"
        _require(text.count(token) == 1, "launcher template placeholder drift: " + key)
        text = text.replace(token, repr(value))
    _require(text.count("@@PAYLOAD@@") == 1, "launcher template placeholder drift: PAYLOAD")
    text = text.replace("@@PAYLOAD@@", _payload_literal(payload))
    _require("@@" not in text, "unfilled launcher placeholder")
    return text.encode("ascii")


def _build(kaggle_user: str, reviewed: str, root: Path, plan: dict | None):
    validate_kaggle_user(kaggle_user)
    validate_reviewed(reviewed)
    payload = load_a_payload(root, reviewed)
    plan = check_plan(current_plan() if plan is None else plan)
    release = json.loads(payload[A_RELEASE_REL][1])
    _require(release["plan_content_sha256"] == plan["content_sha256"],
             "A release does not bind the current qualifier plan content_sha256")
    _require(release["source_sha256"] == plan["source_sha256"],
             "A release does not bind the current 12-file source map")
    _require(load_a_payload(root, reviewed) == payload, "bound bytes changed while computing the plan")
    bundle = {METADATA_FILE: build_metadata(kaggle_user, reviewed),
              CODE_FILE: build_script(payload, reviewed, plan)}
    return bundle, payload, plan


def build_bundle(kaggle_user: str, reviewed: str, root: Path = ROOT, plan: dict | None = None) -> dict[str, bytes]:
    """Return {filename: bytes}; pure, no writes."""
    return _build(kaggle_user, reviewed, root, plan)[0]


def _prepare_output_dir(raw: str, root: Path) -> Path:
    _require(bool(raw), "--output-dir must be explicit")
    target = Path(raw).expanduser().absolute()
    _require(not target.is_symlink(), "--output-dir must not be a symlink")
    resolved = target.resolve()
    for tree in {root.resolve(), ROOT}:
        _require(resolved != tree and tree not in resolved.parents,
                 "--output-dir must be outside the project tree")
    if target.exists():
        _require(target.is_dir() and not any(target.iterdir()),
                 "--output-dir must be a new or empty directory")
    else:
        _require(target.parent.is_dir(), "--output-dir parent must exist")
        target.mkdir()
    return target


def write_bundle(bundle: dict[str, bytes], target: Path) -> None:
    for name, data in bundle.items():
        with open(target / name, "xb") as handle:
            handle.write(data)


def main(argv: list[str] | None = None, *, root: Path | None = None, plan: dict | None = None) -> int:
    root = ROOT if root is None else root
    parser = argparse.ArgumentParser(description="Offline Gate-9 amendment-A corruption-qualification Kaggle bundle")
    parser.add_argument("--plan", action="store_true", help="read-only plan; reads no A release, writes nothing")
    parser.add_argument("--reviewed", help="exact SHA-256 of the owner-approved A release")
    parser.add_argument("--kaggle-user")
    parser.add_argument("--output-dir")
    args = parser.parse_args(argv)
    try:
        _require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 is required")
        if args.plan:
            _require(args.reviewed is None and args.kaggle_user is None and args.output_dir is None,
                     "--plan takes no other arguments")
            print(json.dumps(plan_summary(root, plan), sort_keys=True, indent=2))
            return 0
        _require(args.reviewed is not None and args.kaggle_user is not None and args.output_dir is not None,
                 "bundling requires --reviewed, --kaggle-user and --output-dir")
        bundle, payload, current = _build(args.kaggle_user, args.reviewed, root, plan)
        target = _prepare_output_dir(args.output_dir, root)
        write_bundle(bundle, target)
    except BundleError as exc:
        print("FAIL bundle: " + str(exc), file=sys.stderr)
        return 1
    summary = {
        "schema": "decisions_os/g9_cuda_core_A_kaggle_bundle/v1",
        "a_release_sha256": args.reviewed,
        "plan_content_sha256": current["content_sha256"],
        "kernel_id": f"{args.kaggle_user}/{kernel_slug(args.reviewed)}",
        "submitted_docker_image": SUBMITTED_DOCKER_IMAGE,
        "image_digest_status": IMAGE_DIGEST_STATUS,
        "launch_timeout_seconds_cap_not_guarantee": LAUNCH_TIMEOUT_SECONDS,
        "bundled_sha256": {relative: digest for relative, (digest, _) in payload.items()},
        "output_dir": str(target),
        "files_sha256": {name: _sha(data) for name, data in sorted(bundle.items())},
        "pushed": False,
    }
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
