#!/usr/bin/env python3
"""Build the offline Kaggle handoff bundle for the Gate-9 CUDA core dry run.

Standard library only.  This tool never contacts Kaggle, never reads Kaggle
credentials, never runs nvcc or a GPU, and never pushes.  It reads exactly the
11 release-bound files (the approved release record, its 8 source files and
its 2 authorities), refuses on any byte drift, and writes two files into a
new or empty operator-chosen directory outside the project tree:

  kernel-metadata.json   private Python script, GPU on, internet off, no sources,
                         explicit digest-pinned Kaggle GPU docker_image
  g9_cuda_core_dry_run_kaggle.py   self-verifying launcher with embedded payload
                         and a fail-closed pre-launch image/toolchain/device check

Revision v2 (after the v1 postmortem): v1 ran on the CPU image and stopped at
`nvcc is unavailable`.  v2 uses a new kernel slug, requests the GPU image by
digest, and refuses before launch unless the running environment carries that
image's fingerprint, CUDA_HOME/bin/nvcc on PATH, and an NVIDIA device node.

Output bytes are a pure function of (release-bound bytes, --kaggle-user).
Pushing the bundle is a separate owner-gated act: a `kaggle kernels push`
without `--no-run` starts a session immediately.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
APPROVED_RELEASE_SHA256 = "50f25827ef07b8fcbf3f19223f3982b486f1b11c5d71a7d0c037fd1c6f5328a9"
RELEASE_REL = "research/decisions/GATE_9_CUDA_CORE_DRY_RUN_RELEASE.json"
RELEASE_SCHEMA = "decisions_os/g9_cuda_core_dry_run_release/v1"
CLI_REL = "research/g9/run_stage2_cuda_core_qualification.py"
EXPECTED_AUTHORITY_RELS = frozenset({
    "research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_APPROVAL.md",
    "research/decisions/GATE_9_STAGE2_KAGGLE_CUDA_AMENDMENT_DRAFT.md",
})
EXPECTED_SOURCE_RELS = frozenset({
    "research/g9/cuda_qualification/stage2_cuda_core_bridge.cu",
    "research/g9/cuda_qualification/stage2_cuda_core_bridge.py",
    "research/g9/cuda_qualification/stage2_cuda_core_qualification.py",
    "research/g9/cuda_qualification/stage2_cuda_core_stream_engine.cu",
    "research/g9/cuda_qualification/stage2_cuda_core_stream_engine.py",
    "research/g9/cuda_qualification/stage2_cuda_execution_contract.py",
    "research/g9/cuda_qualification/stage2_cuda_input_frame.py",
    CLI_REL,
})
BUNDLE_FILE_COUNT = 11

BUNDLE_REVISION = "v2"
V1_KERNEL_SLUG = "g9-cuda-core-nonscientific-dry-run-" + APPROVED_RELEASE_SHA256[:8]  # spent; never reused
KERNEL_SLUG = f"g9-cuda-core-nonscientific-dry-run-{BUNDLE_REVISION}-" + APPROVED_RELEASE_SHA256[:8]
KERNEL_TITLE = f"G9 CUDA Core Nonscientific Dry Run {BUNDLE_REVISION.upper()} " + APPROVED_RELEASE_SHA256[:8]
CODE_FILE = "g9_cuda_core_dry_run_kaggle.py"
METADATA_FILE = "kernel-metadata.json"

# Kaggle's official GPU image repository (Kaggle/docker-python README), tags
# `latest`/`v170`.  The digest is the manifest digest served anonymously by the
# public registry (served bytes re-hashed locally).  Its config blob is
# sha256:c72831376c5485ec652a6f4a771bf091ae0726310e1b9db3db064387e173e941,
# which is the GPU config named in the v1 postmortem.  v1 ran on the CPU
# repository's `v170` (sha256:dafd4ce5...).
GPU_DOCKER_IMAGE = ("gcr.io/kaggle-gpu-images/python@sha256:"
                    "37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461")
# Image-config environment values that fingerprint that exact build.  The
# launcher refuses before launch unless the runtime environment carries them.
GPU_IMAGE_ENV_FINGERPRINT = {
    "BUILD_DATE": "20260629-122508",
    "COLAB_IMAGE_TYPE": "gpu",
    "GIT_COMMIT": "fc61d5cda7da39530055bae9bd0e92865f995cd9",
}
# Fixed, not operator-chosen: says what was requested and that the container
# digest itself cannot be observed from inside the session.
IMAGE_LABEL = ("kaggle-gpu-images/python@sha256:" + GPU_DOCKER_IMAGE.rsplit(":", 1)[1]
               + "+requested-not-digest-verified")
RECEIPT_NAME = "g9_cuda_core_dry_run_receipt.json"
FAILURE_NAME = "g9_cuda_core_dry_run_failure.log"
ENVIRONMENT_NAME = "g9_cuda_core_dry_run_prelaunch_environment.json"
RECEIPT_SCHEMA = "decisions_os/g9_cuda_core_dry_run_receipt/v1"

# Kaggle usernames as they appear in kernel URLs: lowercase alphanumerics with
# single interior hyphens.  Deliberately stricter than necessary.
USER_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9]|-(?=[a-z0-9])){0,48}")
# The qualifier requires a nonempty label without whitespace; keep it to a
# plain printable ASCII token so it embeds and prints unambiguously.
LABEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+@=-]{0,127}")
REL_PATTERN = re.compile(r"research(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*)+")


class BundleError(RuntimeError):
    """The bundle cannot be produced safely."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BundleError(message)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def validate_kaggle_user(value: str) -> str:
    _require(type(value) is str and USER_PATTERN.fullmatch(value) is not None,
             "--kaggle-user must be a lowercase Kaggle username slug")
    return value


def validate_image_label(value: str) -> str:
    _require(type(value) is str and LABEL_PATTERN.fullmatch(value) is not None,
             "--image-label must be a nonempty printable ASCII token without whitespace")
    return value


def _read_regular(root: Path, relative: str) -> bytes:
    _require(REL_PATTERN.fullmatch(relative) is not None and ".." not in relative.split("/"),
             f"release path is not a plain research/ path: {relative!r}")
    path = root / relative
    _require(not path.is_symlink() and path.is_file(), f"release-bound file is missing: {relative}")
    return path.read_bytes()


def load_release_payload(root: Path = ROOT) -> dict[str, tuple[str, bytes]]:
    """Return {relative: (sha256, bytes)} for exactly the 11 release-bound files."""
    release_bytes = _read_regular(root, RELEASE_REL)
    _require(_sha(release_bytes) == APPROVED_RELEASE_SHA256,
             "release record hash differs from the approved handoff")
    try:
        release = json.loads(release_bytes)
    except json.JSONDecodeError as exc:
        raise BundleError("release record is not JSON") from exc
    _require(type(release) is dict and release_bytes == _canonical(release) + b"\n",
             "release record is not canonical JSON with one final LF")
    _require(set(release) == {"schema", "status", "source_sha256", "authorities"} and
             release["schema"] == RELEASE_SCHEMA and release["status"] == "approved",
             "release record has invalid fields")
    sources, authorities = release["source_sha256"], release["authorities"]
    _require(type(sources) is dict and set(sources) == EXPECTED_SOURCE_RELS,
             "release source map is not the reviewed 8-file set")
    _require(type(authorities) is dict and set(authorities) == EXPECTED_AUTHORITY_RELS,
             "release authority map is not the reviewed 2-file set")
    payload = {RELEASE_REL: (APPROVED_RELEASE_SHA256, release_bytes)}
    for relative, expected in sorted({**sources, **authorities}.items()):
        data = _read_regular(root, relative)
        _require(_sha(data) == expected, f"release-bound file hash drift: {relative}")
        payload[relative] = (expected, data)
    _require(len(payload) == BUNDLE_FILE_COUNT, "release does not bind exactly 11 files")
    return dict(sorted(payload.items()))


def build_metadata(kaggle_user: str) -> bytes:
    validate_kaggle_user(kaggle_user)
    metadata = {
        "id": f"{kaggle_user}/{KERNEL_SLUG}",
        "title": KERNEL_TITLE,
        "code_file": CODE_FILE,
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": False,
        "machine_shape": "NvidiaTeslaT4",
        # Forwarded verbatim by Kaggle CLI 2.2.4 kernels_push as
        # ApiSaveKernelRequest.docker_image.  Whether the server honours it is
        # not established; the launcher's pre-launch check fails closed if not.
        "docker_image": GPU_DOCKER_IMAGE,
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


SCRIPT_TEMPLATE = '''#!/usr/bin/env python3
"""GENERATED - Gate-9 non-scientific synthetic CUDA core dry run (Kaggle launcher, {revision}).

Do not edit.  Generated offline by
research/g9/kaggle_dry_run/build_g9_cuda_core_dry_run_bundle.py.

Order of operations (fail closed at every step):
  1. decode all 11 embedded release-bound files and check each SHA-256,
     plus the release record's own maps against the embedded table;
  2. stage them under a fresh temporary root preserving research/... layout
     and re-hash the staged bytes from disk;
  3. pre-launch environment check, executing nothing: record bounded
     nonsecret diagnostics to /kaggle/working/{environment_name} and refuse
     unless the pinned GPU image fingerprint, CUDA_HOME/bin/nvcc on PATH and
     an NVIDIA device node are all present;
  4. only then execute the reviewed CLI exactly once:
       run_stage2_cuda_core_qualification.py --qualify-self-test --reviewed <release sha>
     with cwd = staged root; no retry and no alternate execution path;
  5. on rc 0 with a receipt-shaped stdout, save stdout verbatim to
     /kaggle/working/{receipt_name}; otherwise write a bounded
     /kaggle/working/{failure_name}.
Nothing here is scientific: no Stage-2 candidate, instance or result is read.
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

APPROVED_RELEASE_SHA256 = {release_sha!r}
RELEASE_REL = {release_rel!r}
CLI_REL = {cli_rel!r}
IMAGE_LABEL = {image_label!r}
REQUESTED_DOCKER_IMAGE = {docker_image!r}
IMAGE_ENV_FINGERPRINT = {image_env!r}
WORKING_DIR = Path("/kaggle/working")
ENVIRON = os.environ
DEV_DIR = Path("/dev")
PROC_GPU_DIR = Path("/proc/driver/nvidia/gpus")
RECEIPT_NAME = {receipt_name!r}
FAILURE_NAME = {failure_name!r}
ENVIRONMENT_NAME = {environment_name!r}
RECEIPT_SCHEMA = {receipt_schema!r}
LAUNCH_TIMEOUT_SECONDS = 3600
LOG_LIMIT_BYTES = 16384
DIAGNOSTIC_VALUE_LIMIT = 256
DIAGNOSTIC_ITEM_LIMIT = 16
DEVICE_NODE = re.compile(r"nvidia[0-9]+")
EXPECTED_FILE_COUNT = {file_count!r}

{payload}


class DryRunRefusal(RuntimeError):
    pass


def _require(condition, message):
    if not condition:
        raise DryRunRefusal(message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def verified_payload():
    """Decode and hash-check every embedded file; no filesystem or process side effects."""
    _require(len(PAYLOAD) == EXPECTED_FILE_COUNT, "embedded payload does not hold exactly 11 files")
    files = {{}}
    for relative, digest, chunks in PAYLOAD:
        _require(relative not in files, "duplicate embedded path")
        _require(relative.startswith("research/") and ".." not in relative.split("/"),
                 "embedded path escapes research/")
        data = base64.b64decode("".join(chunks).encode("ascii"), validate=True)
        _require(_sha(data) == digest, "embedded SHA-256 mismatch: " + relative)
        files[relative] = (digest, data)
    _require(RELEASE_REL in files and files[RELEASE_REL][0] == APPROVED_RELEASE_SHA256,
             "embedded release record is not the approved release")
    release = json.loads(files[RELEASE_REL][1])
    bound = dict(release["source_sha256"])
    bound.update(release["authorities"])
    bound[RELEASE_REL] = APPROVED_RELEASE_SHA256
    _require(release.get("status") == "approved" and CLI_REL in release["source_sha256"],
             "embedded release record is not an approved CLI release")
    _require(bound == {{relative: digest for relative, (digest, _) in files.items()}},
             "embedded payload is not exactly the release-bound file set")
    return files


def stage(files, root):
    for relative, (digest, data) in sorted(files.items()):
        path = root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "xb") as handle:
            handle.write(data)
    staged = sorted(str(p.relative_to(root)).replace(os.sep, "/")
                    for p in root.rglob("*") if p.is_file() or p.is_symlink())
    _require(staged == sorted(files), "staged tree is not exactly the release-bound file set")
    for relative, (digest, _) in files.items():
        _require(_sha(root.joinpath(*relative.split("/")).read_bytes()) == digest,
                 "staged SHA-256 mismatch: " + relative)


def _bounded(text):
    data = (text or "").encode("utf-8", "replace")
    if len(data) > LOG_LIMIT_BYTES:
        data = b"...[truncated]...\\n" + data[-LOG_LIMIT_BYTES:]
    return data.decode("utf-8", "replace")


def _diagnostics_json(diagnostics):
    return json.dumps(diagnostics, sort_keys=True, indent=2, ensure_ascii=True)


def write_failure(summary, returncode=None, stdout="", stderr="", diagnostics=None):
    body = ("Gate-9 CUDA core dry run FAILED (no receipt written)\\n"
            "approved_release_sha256: " + APPROVED_RELEASE_SHA256 + "\\n"
            "kaggle_image_label: " + IMAGE_LABEL + "\\n"
            "summary: " + _bounded(summary)[:2000] + "\\n"
            "returncode: " + repr(returncode) + "\\n"
            "--- pre-launch environment diagnostics ---\\n" +
            (_diagnostics_json(diagnostics) if diagnostics is not None else "not recorded") + "\\n"
            "--- stdout (bounded tail) ---\\n" + _bounded(stdout) + "\\n"
            "--- stderr (bounded tail) ---\\n" + _bounded(stderr) + "\\n")
    (WORKING_DIR / FAILURE_NAME).write_text(body, encoding="utf-8")


def _clip(value):
    return None if value is None else str(value)[:DIAGNOSTIC_VALUE_LIMIT]


def _device_nodes():
    try:
        names = sorted(p.name for p in DEV_DIR.iterdir() if DEVICE_NODE.fullmatch(p.name))
    except OSError:
        return []
    return [name for name in names if (DEV_DIR / name).is_char_device()][:DIAGNOSTIC_ITEM_LIMIT]


def _proc_gpu_models():
    try:
        entries = sorted(PROC_GPU_DIR.iterdir())[:DIAGNOSTIC_ITEM_LIMIT]
    except OSError:
        return []
    models = []
    for entry in entries:
        try:
            text = (entry / "information").read_text(encoding="utf-8", errors="replace")[:4096]
        except OSError:
            continue
        models.extend(_clip(line.split(":", 1)[1].strip()) for line in text.splitlines()
                      if line.startswith("Model:"))
    return models[:DIAGNOSTIC_ITEM_LIMIT]


def environment_check():
    """Pre-launch image/toolchain/device check.  Reads only named environment
    variables, PATH lookup and /dev, /proc entries; executes nothing.
    Returns (problems, diagnostics); any problem refuses the launch."""
    path_entries = [entry for entry in ENVIRON.get("PATH", "").split(os.pathsep) if entry]
    cuda_home = ENVIRON.get("CUDA_HOME")
    cuda_bin = (os.path.normpath(os.path.join(cuda_home, "bin"))
                if cuda_home and os.path.isabs(cuda_home) else None)
    cuda_bin_on_path = cuda_bin is not None and cuda_bin in {{os.path.normpath(e) for e in path_entries}}
    nvcc = shutil.which("nvcc", path=os.pathsep.join(path_entries)) if path_entries else None
    devices = _device_nodes()
    diagnostics = {{
        "requested_docker_image": REQUESTED_DOCKER_IMAGE,
        "image_env": {{key: _clip(ENVIRON.get(key)) for key in
                      sorted(set(IMAGE_ENV_FINGERPRINT) | {{"CUDA_VERSION"}})}},
        "CUDA_HOME": _clip(cuda_home),
        "cuda_home_bin_on_path": cuda_bin_on_path,
        "nvcc_path": _clip(nvcc),
        "nvidia_device_nodes": devices,
        "nvidiactl_present": (DEV_DIR / "nvidiactl").is_char_device(),
        "proc_driver_gpu_models": _proc_gpu_models(),
    }}
    problems = []
    for key, expected in sorted(IMAGE_ENV_FINGERPRINT.items()):
        if ENVIRON.get(key) != expected:
            problems.append(key + " does not match the pinned GPU image")
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
    diagnostics["problems"] = problems
    return problems, diagnostics


def write_environment(diagnostics):
    text = _diagnostics_json(diagnostics)
    (WORKING_DIR / ENVIRONMENT_NAME).write_text(text + "\\n", encoding="ascii")
    print("Gate-9 pre-launch environment: " + json.dumps(diagnostics, sort_keys=True, ensure_ascii=True))


def _receipt_shaped(stdout):
    try:
        receipt = json.loads(stdout)
    except ValueError:
        return False
    return (type(receipt) is dict and receipt.get("schema") == RECEIPT_SCHEMA and
            receipt.get("execution_release_sha256") == APPROVED_RELEASE_SHA256 and
            receipt.get("scientific_outputs") == "intentionally absent")


def launch(root):
    """The single execution of the reviewed CLI; called only after all hash and environment checks."""
    env = dict(ENVIRON)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["G9_ALLOW_NONSCIENTIFIC_CUDA_QUALIFICATION"] = "1"
    env["G9_KAGGLE_IMAGE_BUILD"] = IMAGE_LABEL
    command = [sys.executable, CLI_REL, "--qualify-self-test", "--reviewed", APPROVED_RELEASE_SHA256]
    return subprocess.run(command, cwd=str(root), env=env, text=True, capture_output=True,
                          check=False, timeout=LAUNCH_TIMEOUT_SECONDS)


def main():
    _require(WORKING_DIR.is_dir(), "Kaggle working directory is unavailable")
    for name in (RECEIPT_NAME, FAILURE_NAME, ENVIRONMENT_NAME):
        _require(not (WORKING_DIR / name).exists(), "output already exists: " + name)
    try:
        files = verified_payload()
    except Exception as exc:
        write_failure("pre-launch payload verification refused: " + str(exc))
        return 2
    with tempfile.TemporaryDirectory(prefix="g9-core-dry-run-stage-") as temporary:
        root = Path(temporary)
        try:
            stage(files, root)
        except Exception as exc:
            write_failure("pre-launch staging verification refused: " + str(exc))
            return 2
        try:
            problems, diagnostics = environment_check()
            write_environment(diagnostics)
        except Exception as exc:
            write_failure("pre-launch environment check could not complete: " + str(exc))
            return 2
        if problems:
            write_failure("pre-launch environment check refused: " + "; ".join(problems),
                          diagnostics=diagnostics)
            print("FAIL Gate-9 CUDA core dry run before launch; see " + str(WORKING_DIR / FAILURE_NAME),
                  file=sys.stderr)
            return 2
        try:
            outcome = launch(root)
        except subprocess.TimeoutExpired as exc:
            write_failure("reviewed CLI timed out", None,
                          exc.stdout if isinstance(exc.stdout, str) else "",
                          exc.stderr if isinstance(exc.stderr, str) else "", diagnostics)
            return 1
        except OSError as exc:
            write_failure("reviewed CLI could not start: " + str(exc), diagnostics=diagnostics)
            return 1
    if outcome.returncode == 0 and _receipt_shaped(outcome.stdout):
        (WORKING_DIR / RECEIPT_NAME).write_text(outcome.stdout, encoding="ascii")
        print("PASS Gate-9 CUDA core dry run; receipt: " + str(WORKING_DIR / RECEIPT_NAME))
        return 0
    summary = ("reviewed CLI returned nonzero status" if outcome.returncode != 0
               else "reviewed CLI returned 0 without a receipt-shaped stdout")
    write_failure(summary, outcome.returncode, outcome.stdout, outcome.stderr, diagnostics)
    print("FAIL Gate-9 CUDA core dry run; see " + str(WORKING_DIR / FAILURE_NAME), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


def build_script(payload: dict[str, tuple[str, bytes]]) -> bytes:
    validate_image_label(IMAGE_LABEL)
    _require(len(payload) == BUNDLE_FILE_COUNT, "payload does not hold exactly 11 files")
    text = SCRIPT_TEMPLATE.format(
        revision=BUNDLE_REVISION, release_sha=APPROVED_RELEASE_SHA256, release_rel=RELEASE_REL,
        cli_rel=CLI_REL, image_label=IMAGE_LABEL, docker_image=GPU_DOCKER_IMAGE,
        image_env=dict(sorted(GPU_IMAGE_ENV_FINGERPRINT.items())), receipt_name=RECEIPT_NAME,
        failure_name=FAILURE_NAME, environment_name=ENVIRONMENT_NAME, receipt_schema=RECEIPT_SCHEMA,
        file_count=BUNDLE_FILE_COUNT, payload=_payload_literal(payload))
    return text.encode("ascii")


def build_bundle(kaggle_user: str, root: Path = ROOT) -> dict[str, bytes]:
    """Return {filename: bytes}; pure, no writes."""
    validate_kaggle_user(kaggle_user)
    payload = load_release_payload(root)
    return {METADATA_FILE: build_metadata(kaggle_user), CODE_FILE: build_script(payload)}


def _prepare_output_dir(raw: str, root: Path = ROOT) -> Path:
    _require(bool(raw), "--output-dir must be explicit")
    target = Path(raw).expanduser().absolute()
    _require(not target.is_symlink(), "--output-dir must not be a symlink")
    resolved = target.resolve()
    _require(resolved != root and root not in resolved.parents,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline Gate-9 CUDA core dry-run Kaggle bundle")
    parser.add_argument("--kaggle-user", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    try:
        bundle = build_bundle(args.kaggle_user)
        target = _prepare_output_dir(args.output_dir)
        write_bundle(bundle, target)
    except BundleError as exc:
        print("FAIL bundle: " + str(exc), file=sys.stderr)
        return 1
    summary = {
        "schema": "decisions_os/g9_cuda_core_dry_run_kaggle_bundle/" + BUNDLE_REVISION,
        "approved_release_sha256": APPROVED_RELEASE_SHA256,
        "kernel_id": f"{args.kaggle_user}/{KERNEL_SLUG}",
        "requested_docker_image": GPU_DOCKER_IMAGE,
        "image_label": IMAGE_LABEL,
        "output_dir": str(target),
        "files_sha256": {name: _sha(data) for name, data in sorted(bundle.items())},
        "pushed": False,
    }
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
