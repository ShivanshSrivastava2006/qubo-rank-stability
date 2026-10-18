#!/usr/bin/env python3
"""Offline verifier for the Gate-9 v3 CUDA core dry-run Kaggle bundle.

Standard library only.  Generates temporary bundles, inspects metadata and the
generated launcher, checks the embedded payload byte-for-byte against the
release-bound files, and exercises the launcher in-process with
`subprocess.run` replaced by a local recording sentinel.  The reviewed CLI's
--qualify-self-test is never invoked; no nvcc, GPU, network or Kaggle access.
The pre-launch environment check is driven by synthetic fixtures: a fake
environment mapping, a never-executed `nvcc` stub file, and a fake /dev whose
`nvidiaN` entries are symlinks to /dev/null (a real character device).
Uses explicit checks (not assert) so it is meaningful under python3 -O.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import ast
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import types

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_g9_cuda_core_gpu_dry_run_v3_bundle as builder  # noqa: E402

ROOT = builder.ROOT
FAILURES: list[str] = []
PASSES = 0

# Every metadata key read by kaggle 2.2.4 KaggleApi.kernels_push.
KAGGLE_CLI_2_2_4_PUSH_KEYS = frozenset({
    "id", "id_no", "title", "code_file", "language", "kernel_type", "is_private", "enable_gpu",
    "enable_tpu", "enable_internet", "dataset_sources", "competition_sources", "kernel_sources",
    "model_sources", "keywords", "docker_image_pinning_type", "docker_image", "machine_shape",
})


def check(condition: bool, label: str) -> None:
    global PASSES
    if condition:
        PASSES += 1
    else:
        FAILURES.append(label)
        print("FAIL: " + label, file=sys.stderr)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bound_hashes(root: Path = ROOT) -> dict[str, str]:
    release = json.loads((root / builder.RELEASE_REL).read_bytes())
    table = {**release["source_sha256"], **release["authorities"]}
    table[builder.RELEASE_REL] = builder.APPROVED_RELEASE_SHA256
    return table


def live_hashes(root: Path = ROOT) -> dict[str, str]:
    return {rel: sha((root / rel).read_bytes()) for rel in bound_hashes(root)}


def refuses(function, *args, **kwargs) -> bool:
    try:
        function(*args, **kwargs)
    except builder.BundleError:
        return True
    return False


def run_builder_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, *(["-O"] if sys.flags.optimize else []),
                           str(HERE / "build_g9_cuda_core_gpu_dry_run_v3_bundle.py"), *args],
                          text=True, capture_output=True, env=env, check=False, timeout=120)


def payload_of(script: str) -> tuple:
    for node in ast.parse(script).body:
        if isinstance(node, ast.Assign) and [getattr(t, "id", None) for t in node.targets] == ["PAYLOAD"]:
            return ast.literal_eval(node.value)
    raise RuntimeError("PAYLOAD not found")


class Sentinel:
    """Stands in for subprocess.run; records calls and inspects the staged tree."""

    TimeoutExpired = subprocess.TimeoutExpired

    def __init__(self, returncode=0, stdout="", stderr="", timeout=False):
        self.calls: list[dict] = []
        self.result = (returncode, stdout, stderr)
        self.timeout = timeout
        self.working: Path | None = None

    def run(self, command, **kwargs):
        cwd = Path(kwargs["cwd"])
        staged = {str(p.relative_to(cwd)).replace(os.sep, "/"): sha(p.read_bytes())
                  for p in cwd.rglob("*") if p.is_file()}
        environment_recorded = self.working is not None and (self.working / builder.ENVIRONMENT_NAME).is_file()
        self.calls.append({"command": list(command), "kwargs": kwargs, "staged": staged,
                           "environment_recorded": environment_recorded})
        if self.timeout:
            raise subprocess.TimeoutExpired(command, kwargs.get("timeout"), output="partial", stderr="late")
        return subprocess.CompletedProcess(command, self.result[0], self.result[1], self.result[2])


class Fixture:
    """Synthetic Kaggle runtime: environment mapping, CUDA_HOME with an nvcc
    stub that is never executed, fake /dev and /proc/driver/nvidia/gpus."""

    NVCC_STUB = "#!/bin/sh\necho 'g9 verifier nvcc stub must never run' >&2\nexit 97\n"

    def __init__(self, base: Path):
        base.mkdir(parents=True)
        self.base = base
        self.cuda = base / "usr-local-cuda"
        self.nvcc = self.cuda / "bin" / "nvcc"
        self.nvcc.parent.mkdir(parents=True)
        self.nvcc.write_text(self.NVCC_STUB)
        self.nvcc.chmod(0o755)
        (base / "bin").mkdir()
        self.dev = base / "dev"
        self.dev.mkdir()
        for name in ("nvidia0", "nvidiactl"):
            (self.dev / name).symlink_to("/dev/null")
        self.proc = base / "proc-gpus"
        (self.proc / "0000:00:04.0").mkdir(parents=True)
        (self.proc / "0000:00:04.0" / "information").write_text("Model: \t\t Tesla T4 (fixture)\nIRQ: 1\n")
        self.environ = {
            "PATH": os.pathsep.join([str(self.cuda / "bin"), str(base / "bin")]),
            "CUDA_HOME": str(self.cuda),
            "CUDA_VERSION": "12.8.1",
            "HOME": str(base),
            "COLAB_IMAGE_TYPE": "gpu",
            "BUILD_DATE": "synthetic-other-build",
            "GIT_COMMIT": "synthetic-other-commit",
        }


def run_launcher(script: str, sentinel: Sentinel, working: Path, fixture: Fixture) -> int:
    namespace = {"__name__": "g9_dry_run_launcher_under_test"}
    exec(compile(script, "g9_cuda_core_dry_run_kaggle.py", "exec"), namespace)
    namespace["subprocess"] = types.SimpleNamespace(run=sentinel.run,
                                                    TimeoutExpired=subprocess.TimeoutExpired)
    namespace["WORKING_DIR"] = working
    namespace["ENVIRON"] = dict(fixture.environ)
    namespace["DEV_DIR"] = fixture.dev
    namespace["PROC_GPU_DIR"] = fixture.proc
    sentinel.working = working
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return namespace["main"]()


def fake_receipt() -> str:
    body = {"schema": builder.RECEIPT_SCHEMA, "execution_release_sha256": builder.APPROVED_RELEASE_SHA256,
            "scientific_outputs": "intentionally absent", "mode": "non_scientific_dry_run",
            "amendment_A_status": "not_satisfied_corrupted_kernel_tests_pending"}
    return json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n"


def retamper_first_source(script: str, payload: tuple) -> str:
    relative, digest, chunks = next(item for item in payload if item[0] != builder.RELEASE_REL)
    data = bytearray(base64.b64decode("".join(chunks)))
    data[0] ^= 1
    encoded = base64.b64encode(bytes(data)).decode("ascii")
    return script.replace(repr(chunks[0]), repr(encoded[:76]), 1)


def main() -> int:
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        print("FAIL: PYTHONDONTWRITEBYTECODE=1 is required", file=sys.stderr)
        return 2
    before = live_hashes()
    check(sha((ROOT / builder.RELEASE_REL).read_bytes()) == builder.APPROVED_RELEASE_SHA256,
          "release record hash is the approved hash")
    check(before == bound_hashes() and len(before) == 11, "all 11 release-bound files match")

    with tempfile.TemporaryDirectory(prefix="g9-kaggle-bundle-verify-") as temporary:
        tmp = Path(temporary)

        # --- CLI generation, determinism, output-dir policy -------------------
        first = run_builder_cli("--kaggle-user", "example-user", "--output-dir", str(tmp / "a"))
        check(first.returncode == 0, "builder CLI succeeds: " + first.stderr.strip())
        second = run_builder_cli("--kaggle-user", "example-user", "--output-dir", str(tmp / "b"))
        names = sorted(p.name for p in (tmp / "a").iterdir())
        check(names == sorted([builder.METADATA_FILE, builder.CODE_FILE]), "bundle holds exactly two files")
        check(all((tmp / "a" / n).read_bytes() == (tmp / "b" / n).read_bytes() for n in names),
              "bundle generation is deterministic")
        summary = json.loads(first.stdout)
        check(summary["pushed"] is False and summary["files_sha256"] ==
              {n: sha((tmp / "a" / n).read_bytes()) for n in names}, "builder summary hashes match files")
        check(run_builder_cli("--kaggle-user", "example-user", "--output-dir", str(tmp / "a")).returncode == 1,
              "non-empty output dir is refused")
        (tmp / "afile").write_text("x")
        check(run_builder_cli("--kaggle-user", "example-user", "--output-dir", str(tmp / "afile")).returncode == 1,
              "existing file as output dir is refused")
        check(run_builder_cli("--kaggle-user", "example-user", "--output-dir",
                              str(tmp / "missing" / "deep")).returncode == 1, "missing parent is refused")
        (tmp / "empty").mkdir()
        check(run_builder_cli("--kaggle-user", "example-user", "--output-dir", str(tmp / "empty")).returncode == 0,
              "existing empty output dir is accepted")
        inside = HERE / "must_not_be_created"
        check(run_builder_cli("--kaggle-user", "example-user", "--output-dir", str(inside)).returncode == 1
              and not inside.exists(), "output dir inside the project is refused")
        (tmp / "link").symlink_to(tmp / "empty2", target_is_directory=True)
        check(run_builder_cli("--kaggle-user", "example-user", "--output-dir", str(tmp / "link")).returncode == 1,
              "symlink output dir is refused")
        for user in ("", "Example", "a/b", "-ab", "ab-", "a--b", "a_b", "a b", "x" * 60, "ab\n"):
            check(refuses(builder.validate_kaggle_user, user), f"bad kaggle user refused: {user!r}")
        for label in ("", " ", "a b", "a\tb", "é", "a\n", "x" * 200):
            check(refuses(builder.validate_image_label, label), f"bad image label refused: {label!r}")
        for user in ("ab", "abc123", "a-b-c"):
            check(not refuses(builder.validate_kaggle_user, user), f"good kaggle user accepted: {user!r}")
        check(run_builder_cli("--kaggle-user", "example-user", "--output-dir", str(tmp / "labelled"),
                              "--image-label", "anything").returncode == 2 and not (tmp / "labelled").exists(),
              "operator-chosen --image-label is no longer accepted")
        check(summary["schema"].endswith("/v3") and summary["submitted_docker_image"] is None
              and summary["image_label"] == builder.IMAGE_LABEL,
              "builder summary names v3 and records no submitted image")

        # --- image setting and honest label ------------------------------------
        check(builder.SUBMITTED_DOCKER_IMAGE is None and builder.REQUIRED_IMAGE_TYPE == "gpu",
              "v3 submits no image and requires observed GPU image type")
        check(builder.DIAGNOSTIC_IMAGE_ENV_NAMES ==
              ("BUILD_DATE", "COLAB_IMAGE_TYPE", "CUDA_VERSION", "GIT_COMMIT"),
              "only four named image environment values enter bounded diagnostics")
        check(not refuses(builder.validate_image_label, builder.IMAGE_LABEL) and
              builder.IMAGE_LABEL == "kaggle-api-default-gpu-unverified" and
              "sha256:" not in builder.IMAGE_LABEL,
              "fixed label does not claim a submitted or verified image digest")

        # --- metadata ---------------------------------------------------------
        metadata_bytes = (tmp / "a" / builder.METADATA_FILE).read_bytes()
        metadata = json.loads(metadata_bytes)
        check(metadata_bytes == (json.dumps(metadata, sort_keys=True, indent=2) + "\n").encode("ascii"),
              "metadata is canonical sorted JSON with one final LF")
        check(metadata == {
            "id": "example-user/" + builder.KERNEL_SLUG, "title": builder.KERNEL_TITLE,
            "code_file": builder.CODE_FILE, "language": "python", "kernel_type": "script",
            "is_private": True, "enable_gpu": True, "enable_tpu": False, "enable_internet": False,
            "machine_shape": "NvidiaTeslaT4",
            "keywords": [], "dataset_sources": [],
            "competition_sources": [], "kernel_sources": [], "model_sources": []},
              "metadata has exact private-script GPU/no-image/no-internet/no-sources fields")
        check(set(metadata) <= KAGGLE_CLI_2_2_4_PUSH_KEYS, "metadata uses only keys Kaggle CLI 2.2.4 push reads")
        check("docker_image_pinning_type" not in metadata and "docker_image" not in metadata,
              "neither an image nor a pinning type is submitted")
        check(b"docker_image" not in metadata_bytes and b"pinning_type" not in metadata_bytes,
              "image key absence is true in submitted metadata bytes")
        check(builder.KERNEL_TITLE.lower().replace(" ", "-") == builder.KERNEL_SLUG,
              "kernel title slugifies to the kernel id slug")
        check(builder.KERNEL_SLUG == "g9-cuda-core-nonscientific-dry-run-v3-50f25827" and
              builder.V1_KERNEL_SLUG not in metadata_bytes.decode() and
              builder.V2_KERNEL_SLUG not in metadata_bytes.decode(),
              "v3 kernel slug is new and never addresses either spent kernel")

        # --- script structure -------------------------------------------------
        script_bytes = (tmp / "a" / builder.CODE_FILE).read_bytes()
        script = script_bytes.decode("ascii")
        check("research/g9/kaggle_dry_run/build_g9_cuda_core_gpu_dry_run_v3_bundle.py" in script and
              "research/g9/kaggle_dry_run/build_g9_cuda_core_dry_run_bundle.py" not in script,
              "generated provenance names the v3 builder, never the v2 builder")
        tree = ast.parse(script)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module.split(".")[0])
        check(imports == {"base64", "hashlib", "json", "os", "pathlib", "re", "shutil", "subprocess", "sys",
                          "tempfile"}, "launcher imports only the expected standard-library modules")
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        dotted = [f"{c.func.value.id}.{c.func.attr}" for c in calls
                  if isinstance(c.func, ast.Attribute) and isinstance(c.func.value, ast.Name)]
        named = [c.func.id for c in calls if isinstance(c.func, ast.Name)]
        check(dotted.count("subprocess.run") == 1 and not [d for d in dotted if d.startswith("subprocess.")
                                                           and d != "subprocess.run"],
              "exactly one subprocess.run call site and no other subprocess API")
        check(not {"exec", "eval", "compile", "__import__"} & set(named) and
              not [d for d in dotted if d in ("os.system", "os.execv", "os.execve", "os.popen", "os.spawnv")],
              "no alternate execution path in launcher")
        check("--qualify-self-test" in script and script.count("--qualify-self-test") == 2,
              "reviewed flag appears only in docstring and the single command")
        check(f"IMAGE_LABEL = {builder.IMAGE_LABEL!r}" in script and
              f"SUBMITTED_DOCKER_IMAGE = {builder.SUBMITTED_DOCKER_IMAGE!r}" in script and
              f"REQUIRED_IMAGE_TYPE = {builder.REQUIRED_IMAGE_TYPE!r}" in script and
              f"DIAGNOSTIC_IMAGE_ENV_NAMES = {builder.DIAGNOSTIC_IMAGE_ENV_NAMES!r}" in script,
              "honest unverified label, no submitted image, and named diagnostics embedded")
        check("IMAGE_ENV_FINGERPRINT" not in script and "REQUESTED_DOCKER_IMAGE" not in script,
              "launcher carries no pinned-build fingerprint or v2 image request")
        check("PYTHONDONTWRITEBYTECODE\"] = \"1\"" in script and
              "G9_ALLOW_NONSCIENTIFIC_CUDA_QUALIFICATION\"] = \"1\"" in script and
              "G9_KAGGLE_IMAGE_BUILD\"] = IMAGE_LABEL" in script, "launcher sets the three environment values")
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        check_dotted = sorted(f"{n.func.value.id}.{n.func.attr}" for name in
                              ("environment_check", "_device_nodes", "_proc_gpu_models")
                              for n in ast.walk(functions[name]) if isinstance(n, ast.Call) and
                              isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and
                              n.func.value.id in ("subprocess", "os", "shutil", "sys"))
        check(check_dotted == ["shutil.which"], "environment check only looks up nvcc; it executes nothing")
        main_calls = [n.func.id for n in sorted((n for n in ast.walk(functions["main"]) if isinstance(n, ast.Call)
                                                 and isinstance(n.func, ast.Name)),
                                                key=lambda n: (n.lineno, n.col_offset))]
        check(main_calls.count("launch") == 1 and main_calls.count("environment_check") == 1 and
              main_calls.index("verified_payload") < main_calls.index("stage") <
              main_calls.index("environment_check") < main_calls.index("launch"),
              "main orders payload check, staging, environment check, then the single launch")

        # --- payload exactness -------------------------------------------------
        payload = payload_of(script)
        embedded = {rel: base64.b64decode("".join(chunks), validate=True) for rel, _, chunks in payload}
        check(len(payload) == 11 and set(embedded) == set(before), "payload holds exactly the 11 bound paths")
        check(all(embedded[rel] == (ROOT / rel).read_bytes() for rel in embedded),
              "embedded bytes equal the live release-bound bytes")
        check(all(digest == before[rel] for rel, digest, _ in payload), "embedded digests equal release table")

        # --- generator fails closed on tampered/missing sources ----------------
        copy_root = tmp / "copy"
        for rel in before:
            (copy_root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, copy_root / rel)
        (copy_root / "research/g9/smuggle_me.py").write_text("print('x')\n")
        clean = builder.build_bundle("example-user", root=copy_root)
        check(clean[builder.CODE_FILE] == script_bytes and b"smuggle_me" not in clean[builder.CODE_FILE],
              "unbound repo files are never embedded")
        for rel in sorted(before):
            victim = copy_root / rel
            original = victim.read_bytes()
            victim.write_bytes(original + b" ")
            check(refuses(builder.build_bundle, "example-user", root=copy_root),
                  "tampered release-bound file refused: " + rel)
            victim.unlink()
            check(refuses(builder.build_bundle, "example-user", root=copy_root),
                  "missing release-bound file refused: " + rel)
            victim.write_bytes(original)
        check(not refuses(builder.build_bundle, "example-user", root=copy_root), "restored copy accepted")

        # --- launcher: good path with sentinel ---------------------------------
        def fresh(name: str) -> Path:
            path = tmp / "work" / name
            path.mkdir(parents=True)
            return path

        fixture_count = 0

        def fixture() -> Fixture:
            nonlocal fixture_count
            fixture_count += 1
            return Fixture(tmp / "fixtures" / str(fixture_count))

        def diagnostics_of(work: Path) -> dict:
            return json.loads((work / builder.ENVIRONMENT_NAME).read_text())

        good = fixture()
        work = fresh("ok")
        sentinel = Sentinel(0, fake_receipt(), "")
        rc = run_launcher(script, sentinel, work, good)
        check(rc == 0 and len(sentinel.calls) == 1, "good launcher calls the CLI exactly once")
        call = sentinel.calls[0]
        check(call["command"][1:] == [builder.CLI_REL, "--qualify-self-test", "--reviewed",
                                      builder.APPROVED_RELEASE_SHA256] and call["command"][0] == sys.executable,
              "launcher command is the reviewed CLI invocation")
        env = call["kwargs"]["env"]
        check(env == {**good.environ, "PYTHONDONTWRITEBYTECODE": "1",
                      "G9_ALLOW_NONSCIENTIFIC_CUDA_QUALIFICATION": "1", "G9_KAGGLE_IMAGE_BUILD": builder.IMAGE_LABEL},
              "launcher environment is the checked environment plus exactly three values")
        check(call["staged"] == before, "staged root holds exactly the 11 bound files at launch time")
        check(call["environment_recorded"], "environment diagnostics are recorded before the launch")
        check(call["kwargs"]["check"] is False and call["kwargs"]["timeout"] == 3600, "single bounded launch")
        check((work / builder.RECEIPT_NAME).read_text() == fake_receipt() and
              not (work / builder.FAILURE_NAME).exists(), "receipt saved verbatim only on success")
        check(sorted(p.name for p in work.iterdir()) == sorted([builder.RECEIPT_NAME, builder.ENVIRONMENT_NAME]),
              "no other working outputs")
        ok_diag = diagnostics_of(work)
        check(ok_diag == {
            "submitted_docker_image": None,
            "image_env": {"BUILD_DATE": "synthetic-other-build", "COLAB_IMAGE_TYPE": "gpu",
                          "CUDA_VERSION": "12.8.1", "GIT_COMMIT": "synthetic-other-commit"},
            "CUDA_HOME": str(good.cuda), "cuda_home_bin_on_path": True, "nvcc_path": str(good.nvcc),
            "nvidia_device_nodes": ["nvidia0"], "nvidiactl_present": True,
            "proc_driver_gpu_models": ["Tesla T4 (fixture)"], "problems": []},
              "success diagnostics are exact, bounded and nonsecret")
        check(good.nvcc.read_text() == Fixture.NVCC_STUB, "nvcc stub untouched (it is looked up, never run)")

        # --- launcher: failure modes after launch, still exactly one call --------
        work = fresh("rc1")
        sentinel = Sentinel(1, "x" * 100000, "FAIL Gate-9 core qualification: nvcc is unavailable\n" * 2000)
        check(run_launcher(script, sentinel, work, good) == 1 and len(sentinel.calls) == 1, "nonzero rc: one call")
        log = work / builder.FAILURE_NAME
        check(log.exists() and not (work / builder.RECEIPT_NAME).exists() and log.stat().st_size < 40000,
              "nonzero rc writes only a bounded failure log")
        check('"problems": []' in log.read_text(), "post-launch failure log carries the environment diagnostics")

        work = fresh("garbage")
        sentinel = Sentinel(0, "not json", "")
        check(run_launcher(script, sentinel, work, good) == 1 and len(sentinel.calls) == 1 and
              not (work / builder.RECEIPT_NAME).exists() and (work / builder.FAILURE_NAME).exists(),
              "rc 0 without receipt-shaped stdout is a failure")

        receipt = json.loads(fake_receipt())
        for label, changed in (
            ("missing amendment status", {key: value for key, value in receipt.items()
                                          if key != "amendment_A_status"}),
            ("wrong amendment status", {**receipt, "amendment_A_status": "satisfied"}),
            ("missing mode", {key: value for key, value in receipt.items() if key != "mode"}),
            ("wrong mode", {**receipt, "mode": "scientific_run"}),
        ):
            work = fresh("receipt-" + label.replace(" ", "-"))
            sentinel = Sentinel(0, json.dumps(changed, sort_keys=True) + "\n", "")
            check(run_launcher(script, sentinel, work, good) == 1 and len(sentinel.calls) == 1 and
                  not (work / builder.RECEIPT_NAME).exists() and
                  (work / builder.FAILURE_NAME).exists(),
                  "rc 0 receipt refuses " + label)

        status_guard = 'receipt.get("amendment_A_status") == "not_satisfied_corrupted_kernel_tests_pending"'
        weakened = script.replace(status_guard, "True", 1)
        check(weakened != script, "tamper applied: amendment-status receipt guard removed")
        work = fresh("weakened-receipt-guard")
        sentinel = Sentinel(0, json.dumps({key: value for key, value in receipt.items()
                                           if key != "amendment_A_status"}) + "\n")
        check(run_launcher(weakened, sentinel, work, good) == 0 and len(sentinel.calls) == 1 and
              (work / builder.RECEIPT_NAME).exists(),
              "without the amendment-status guard the malformed receipt would pass (load-bearing)")

        work = fresh("timeout")
        sentinel = Sentinel(timeout=True)
        check(run_launcher(script, sentinel, work, good) == 1 and len(sentinel.calls) == 1 and
              (work / builder.FAILURE_NAME).exists(), "timeout: one call, no retry, failure log")

        for name in (builder.RECEIPT_NAME, builder.FAILURE_NAME, builder.ENVIRONMENT_NAME):
            work = fresh("preexisting-" + name)
            (work / name).write_text("old")
            sentinel = Sentinel(0, fake_receipt())
            refused = False
            try:
                run_launcher(script, sentinel, work, good)
            except Exception:
                refused = True
            check(refused and not sentinel.calls and (work / name).read_text() == "old",
                  "pre-existing output refuses before launch: " + name)

        # --- launcher: pre-launch environment check refuses wrong conditions ----
        def env_case(mutate) -> Fixture:
            case = fixture()
            mutate(case)
            return case

        def set_env(**values):
            def mutate(case: Fixture) -> None:
                for key, value in values.items():
                    if value is None:
                        case.environ.pop(key, None)
                    else:
                        case.environ[key] = value.format(cuda=case.cuda, base=case.base)
            return mutate

        def nvcc_elsewhere_first(case: Fixture) -> None:
            other = case.base / "bin" / "nvcc"
            other.write_text(Fixture.NVCC_STUB)
            other.chmod(0o755)
            case.environ["PATH"] = os.pathsep.join([str(case.base / "bin"), str(case.cuda / "bin")])

        def v1_like_cpu_image(case: Fixture) -> None:
            case.environ = {"PATH": str(case.base / "bin"), "HOME": str(case.base), "COLAB_IMAGE_TYPE": "cpu",
                            "BUILD_DATE": "20260629-000000", "GIT_COMMIT": "0" * 40}
            for node in case.dev.iterdir():
                node.unlink()
            shutil.rmtree(case.proc)

        environment_cases = {
            "wrong image type (cpu)": (set_env(COLAB_IMAGE_TYPE="cpu"), "COLAB_IMAGE_TYPE"),
            "missing image type": (set_env(COLAB_IMAGE_TYPE=None), "COLAB_IMAGE_TYPE"),
            "missing nvcc": (lambda c: c.nvcc.unlink(), "nvcc is not an executable on PATH"),
            "non-executable nvcc": (lambda c: c.nvcc.chmod(0o644), "nvcc is not an executable on PATH"),
            "CUDA_HOME unset": (set_env(CUDA_HOME=None), "CUDA_HOME is unset"),
            "CUDA_HOME relative": (set_env(CUDA_HOME="usr/local/cuda"), "CUDA_HOME is unset"),
            "CUDA_HOME/bin off PATH": (set_env(PATH="{base}/bin"), "CUDA_HOME/bin is not on PATH"),
            "empty PATH": (set_env(PATH=""), "nvcc is not an executable on PATH"),
            "nvcc shadowed outside CUDA_HOME": (nvcc_elsewhere_first, "nvcc on PATH is not CUDA_HOME/bin/nvcc"),
            "no device evidence": (lambda c: [n.unlink() for n in c.dev.iterdir()], "no /dev/nvidiaN"),
            "only nvidiactl": (lambda c: (c.dev / "nvidia0").unlink(), "no /dev/nvidiaN"),
            "device node is a regular file": (lambda c: ((c.dev / "nvidia0").unlink(),
                                                         (c.dev / "nvidia0").write_text("")), "no /dev/nvidiaN"),
            "device name not nvidiaN": (lambda c: ((c.dev / "nvidia0").rename(c.dev / "nvidia-uvm")),
                                        "no /dev/nvidiaN"),
            "v1-like CPU image": (v1_like_cpu_image, "COLAB_IMAGE_TYPE"),
        }
        for label, (mutate, reason) in environment_cases.items():
            case = env_case(mutate)
            work = fresh("env-" + label.replace(" ", "-").replace("/", "_"))
            sentinel = Sentinel(0, fake_receipt())
            rc = run_launcher(script, sentinel, work, case)
            log = (work / builder.FAILURE_NAME).read_text() if (work / builder.FAILURE_NAME).exists() else ""
            diag = diagnostics_of(work) if (work / builder.ENVIRONMENT_NAME).exists() else {}
            check(rc == 2 and not sentinel.calls and not (work / builder.RECEIPT_NAME).exists() and
                  "pre-launch environment check refused" in log and reason in log and
                  any(reason in problem for problem in diag.get("problems", [])),
                  "wrong environment refuses before launch with diagnostics: " + label)
        cpu_diag = diagnostics_of(work)
        check(cpu_diag["image_env"]["COLAB_IMAGE_TYPE"] == "cpu" and cpu_diag["nvcc_path"] is None and
              cpu_diag["nvidia_device_nodes"] == [] and cpu_diag["proc_driver_gpu_models"] == [] and
              len(cpu_diag["problems"]) >= 3, "v1-like CPU image records every missing condition")

        # The allocation probe did not attest a submission-time build pin.
        # Different BUILD_DATE/GIT_COMMIT values are recorded, never refused.
        work = fresh("other-image-build")
        case = env_case(set_env(BUILD_DATE="another-build", GIT_COMMIT="f" * 40))
        sentinel = Sentinel(0, fake_receipt())
        check(run_launcher(script, sentinel, work, case) == 0 and len(sentinel.calls) == 1 and
              diagnostics_of(work)["image_env"]["BUILD_DATE"] == "another-build" and
              diagnostics_of(work)["image_env"]["GIT_COMMIT"] == "f" * 40,
              "unattested build fields are diagnostic only and do not block a valid GPU")
        for name, mutation in (
            ("missing-build-date", set_env(BUILD_DATE=None)),
            ("missing-git-commit", set_env(GIT_COMMIT=None)),
            ("other-cuda-version", set_env(CUDA_VERSION="unknown")),
        ):
            work = fresh(name)
            case = env_case(mutation)
            sentinel = Sentinel(0, fake_receipt())
            check(run_launcher(script, sentinel, work, case) == 0 and len(sentinel.calls) == 1,
                  "unattested image field does not become a hidden pin: " + name)

        work = fresh("env-oversized-values")
        case = env_case(set_env(COLAB_IMAGE_TYPE="x" * 100000))
        run_launcher(script, Sentinel(0, fake_receipt()), work, case)
        check(len(diagnostics_of(work)["image_env"]["COLAB_IMAGE_TYPE"]) == 256 and
              (work / builder.FAILURE_NAME).stat().st_size < 20000, "diagnostic values are bounded")
        work = fresh("env-secret-not-recorded")
        case = env_case(set_env(KAGGLE_KEY="must-not-leak", KAGGLE_USERNAME="must-not-leak"))
        run_launcher(script, Sentinel(0, fake_receipt()), work, case)
        check(not any("must-not-leak" in p.read_text() for p in work.iterdir()),
              "unrelated environment variables are never recorded")

        # --- the environment fixtures are load-bearing -------------------------
        disarmed = script.replace("        if problems:\n", "        if problems and False:\n", 1)
        check(disarmed != script, "tamper applied: disarmed environment refusal")
        work = fresh("disarmed")
        sentinel = Sentinel(0, fake_receipt())
        run_launcher(disarmed, sentinel, work, env_case(set_env(COLAB_IMAGE_TYPE="cpu")))
        check(len(sentinel.calls) == 1, "without the refusal a wrong image would launch (fixture is load-bearing)")
        no_image_type_check = script.replace(
            '    if ENVIRON.get("COLAB_IMAGE_TYPE") != REQUIRED_IMAGE_TYPE:\n',
            '    if False:\n', 1)
        check(no_image_type_check != script, "tamper applied: observed GPU image-type check removed")
        sentinel = Sentinel(0, fake_receipt())
        run_launcher(no_image_type_check, sentinel, fresh("no-image-type-check"),
                     env_case(set_env(COLAB_IMAGE_TYPE="cpu")))
        check(len(sentinel.calls) == 1,
              "without the image-type check a CPU-labelled runtime would launch (load-bearing)")
        no_device_check = script.replace('    if not devices:\n', '    if False:\n', 1)
        check(no_device_check != script, "tamper applied: device check removed")
        sentinel = Sentinel(0, fake_receipt())
        run_launcher(no_device_check, sentinel, fresh("no-device-check"),
                     env_case(lambda c: [n.unlink() for n in c.dev.iterdir()]))
        check(len(sentinel.calls) == 1, "without the device check absent devices would launch (load-bearing)")

        # --- launcher: tampered embedded payloads never launch ------------------
        tampered = {
            "flipped source byte": retamper_first_source(script, payload),
            "renamed path": script.replace(f"    ({payload[-1][0]!r}, ", "    ('__drop__', ", 1),
            "extra file": script.replace("PAYLOAD = (\n", "PAYLOAD = (\n    ('research/g9/extra.py', "
                                         f"{sha(b'')!r}, ('',)),\n", 1),
            "digest swapped": script.replace(repr(payload[1][1]), repr(sha(b"forged")), 1),
            "release swapped": script.replace(f"APPROVED_RELEASE_SHA256 = {builder.APPROVED_RELEASE_SHA256!r}",
                                              f"APPROVED_RELEASE_SHA256 = {'0' * 64!r}", 1),
        }
        for label, text in tampered.items():
            check(text != script, "tamper applied: " + label)
            work = fresh("tamper-" + label.replace(" ", "-"))
            sentinel = Sentinel(0, fake_receipt())
            rc = run_launcher(text, sentinel, work, good)
            check(rc == 2 and not sentinel.calls and (work / builder.FAILURE_NAME).exists() and
                  not (work / builder.RECEIPT_NAME).exists() and not (work / builder.ENVIRONMENT_NAME).exists()
                  and "pre-launch payload verification refused" in (work / builder.FAILURE_NAME).read_text(),
                  "tampered launcher refuses before environment check or launch, even on a good GPU: " + label)

    after = live_hashes()
    check(after == before, "release-bound files unchanged after verification")
    check(not list(HERE.glob("**/__pycache__")), "no bytecode written under kaggle_dry_run")
    status = "PASS" if not FAILURES else "FAIL"
    print(f"{status} g9 kaggle dry-run bundle verifier: {PASSES} checks passed, {len(FAILURES)} failed "
          f"(optimize={sys.flags.optimize})")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    raise SystemExit(main())
