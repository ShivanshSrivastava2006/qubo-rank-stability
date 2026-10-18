#!/usr/bin/env python3
"""Offline verifier for the Gate-9 amendment-A corruption-qualification Kaggle bundle.

Standard library only, plus the builder's read-only import of the reviewed
qualifier plan.  A synthetic approved release is written only inside a
TemporaryDirectory copy of the 16 other bound files; research/decisions is
never written by this verifier.  If an owner-approved A release exists in the
real tree, its read-only bundle path is checked separately.  The builder runs
in-process and, for --plan and refusals, as a subprocess.  The generated
launcher runs in-process with subprocess.run replaced by a recording sentinel,
a synthetic environment, a never-executed nvcc stub and a fake /dev whose
nvidiaN entry is a symlink to /dev/null (a real character device).  The
reviewed qualification CLI is never invoked in any mode; no nvcc, GPU,
network or Kaggle access.  Explicit checks, no assert: meaningful under -O.
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
import runpy
import shutil
import subprocess
import tempfile
import types

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_g9_cuda_core_A_bundle as builder  # noqa: E402

ROOT = builder.ROOT
NON_A_RELS = tuple(sorted({*builder.SOURCE_RELS, *builder.FIXED_RELS}))
FAILURES: list[str] = []
PASSES = 0
DROP = object()

# Every metadata key read by kaggle 2.2.4 KaggleApi.kernels_push.
KAGGLE_CLI_2_2_4_PUSH_KEYS = frozenset({
    "id", "id_no", "title", "code_file", "language", "kernel_type", "is_private", "enable_gpu",
    "enable_tpu", "enable_internet", "dataset_sources", "competition_sources", "kernel_sources",
    "model_sources", "keywords", "docker_image_pinning_type", "docker_image", "machine_shape",
})
SPENT_SLUG_PREFIXES = ("g9-cuda-core-nonscientific-dry-run", "g9-gpu-allocation-probe")
LAUNCHER_IMPORTS = {"base64", "hashlib", "json", "os", "pathlib", "re", "shutil", "subprocess", "sys",
                    "tempfile"}
ENV_PREFIX = "Gate-9 A pre-launch environment: "


def check(condition: bool, label: str) -> None:
    global PASSES
    if condition:
        PASSES += 1
    else:
        FAILURES.append(label)
        print("FAIL: " + label, file=sys.stderr)


def report() -> int:
    status = "PASS" if not FAILURES else "FAIL"
    print(f"{status} g9 amendment-A Kaggle bundle verifier: {PASSES} checks passed, {len(FAILURES)} failed "
          f"(optimize={sys.flags.optimize})")
    return 0 if not FAILURES else 1


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canon(value: object) -> bytes:
    return builder._canonical(value) + b"\n"


def live_hashes(root: Path) -> dict[str, str]:
    return {rel: sha((root / rel).read_bytes()) for rel in NON_A_RELS}


def pycache_dirs() -> list[str]:
    return sorted(str(p) for p in (ROOT / "research" / "g9").rglob("__pycache__"))


def refusal(function, *args, **kwargs) -> str | None:
    """BundleError message, or None if the call did not refuse cleanly."""
    try:
        function(*args, **kwargs)
    except builder.BundleError as exc:
        return str(exc)
    except Exception:  # an unexpected error is not a clean refusal
        return None
    return None


def refuses(function, *args, **kwargs) -> bool:
    return refusal(function, *args, **kwargs) is not None


def run_builder_cli(*args: str, bytecode_env: bool = True) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if bytecode_env:
        env["PYTHONDONTWRITEBYTECODE"] = "1"
    else:
        env.pop("PYTHONDONTWRITEBYTECODE", None)
    return subprocess.run([sys.executable, *(["-O"] if sys.flags.optimize else []), "-B",
                           str(HERE / "build_g9_cuda_core_A_bundle.py"), *args],
                          text=True, capture_output=True, env=env, check=False, timeout=300)


def entries_of(script: str) -> list[tuple[str, str, bytes]]:
    for node in ast.parse(script).body:
        if isinstance(node, ast.Assign) and [getattr(t, "id", None) for t in node.targets] == ["PAYLOAD"]:
            return [(rel, digest, base64.b64decode("".join(chunks), validate=True))
                    for rel, digest, chunks in ast.literal_eval(node.value)]
    raise RuntimeError("PAYLOAD not found")


def payload_literal(entries: list[tuple[str, str, bytes]]) -> str:
    lines = ["PAYLOAD = ("]
    for rel, digest, data in entries:
        encoded = base64.b64encode(data).decode("ascii")
        lines.append(f"    ({rel!r}, {digest!r}, (")
        for start in range(0, len(encoded), 76):
            lines.append(f"        {encoded[start:start + 76]!r},")
        lines.append("    )),")
    lines.append(")")
    return "\n".join(lines)


def with_payload(script: str, entries: list[tuple[str, str, bytes]]) -> str:
    start = script.index("PAYLOAD = (\n")
    end = script.index("\n)\n", start) + 2
    return script[:start] + payload_literal(entries) + script[end:]


def edited(entries, rel, *, data=None, digest=None, new_rel=None, rehash=False):
    result = []
    for r, d, b in entries:
        if r == rel:
            b = b if data is None else data
            d = sha(b) if rehash else (d if digest is None else digest)
            r = r if new_rel is None else new_rel
        result.append((r, d, b))
    return result


class Sentinel:
    """Stands in for subprocess.run; records calls and inspects the staged tree.  Executes nothing."""

    def __init__(self, returncode=0, stdout="", stderr="", raise_timeout=False, raise_oserror=False):
        self.calls: list[dict] = []
        self.result = (returncode, stdout, stderr)
        self.raise_timeout = raise_timeout
        self.raise_oserror = raise_oserror

    def run(self, command, **kwargs):
        cwd = Path(kwargs["cwd"])
        staged = {str(p.relative_to(cwd)).replace(os.sep, "/"): sha(p.read_bytes())
                  for p in cwd.rglob("*") if p.is_file()}
        self.calls.append({"command": list(command), "kwargs": kwargs, "staged": staged})
        if self.raise_timeout:
            raise subprocess.TimeoutExpired(command, kwargs.get("timeout"), output="partial", stderr="late")
        if self.raise_oserror:
            raise OSError("synthetic exec failure")
        return subprocess.CompletedProcess(command, self.result[0], self.result[1], self.result[2])


class Fixture:
    """Synthetic Kaggle runtime: environment mapping, CUDA_HOME with an nvcc
    stub that is never executed, and a fake /dev."""

    NVCC_STUB = "#!/bin/sh\necho 'g9 A verifier nvcc stub must never run' >&2\nexit 97\n"

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
        self.environ = {
            "PATH": os.pathsep.join([str(self.cuda / "bin"), str(base / "bin")]),
            "CUDA_HOME": str(self.cuda),
            "CUDA_VERSION": "12.8.1",
            "HOME": str(base),
            "COLAB_IMAGE_TYPE": "gpu",
            "BUILD_DATE": "synthetic-build-date",
            "GIT_COMMIT": "synthetic-git-commit",
        }


def run_launcher(script: str, sentinel: Sentinel, working: Path, fixture: Fixture) -> tuple[int, str, str]:
    namespace = {"__name__": "g9_A_launcher_under_test"}
    exec(compile(script, builder.CODE_FILE, "exec"), namespace)
    namespace["subprocess"] = types.SimpleNamespace(run=sentinel.run, TimeoutExpired=subprocess.TimeoutExpired)
    namespace["WORKING_DIR"] = working
    namespace["ENVIRON"] = dict(fixture.environ)
    namespace["DEV_DIR"] = fixture.dev
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = namespace["main"]()
    return rc, out.getvalue(), err.getvalue()


def printed_diagnostics(stdout: str) -> dict | None:
    lines = [line for line in stdout.splitlines() if line.startswith(ENV_PREFIX)]
    return json.loads(lines[0][len(ENV_PREFIX):]) if len(lines) == 1 else None


def synthetic_receipt(a_sha: str, plan: dict, *, drop=(), rehash=True, **changes) -> str:
    mutations = [
        {**row, "device_self_test_rejected": False,
         "python_reference_rejected": True, "rejection_reason": "synthetic mismatch"}
        for row in plan["mutations"]
    ]
    body = {
        "schema": builder.RECEIPT_SCHEMA, "mode": builder.RECEIPT_MODE,
        "scientific_outputs": "intentionally absent", "stage2_inputs": "intentionally absent",
        "verdict": builder.PENDING_VERDICT, "amendment_A_status": builder.AMENDMENT_A_STATUS,
        "execution_release_sha256": a_sha, "plan_content_sha256": plan["content_sha256"],
        "source_sha256": dict(plan["source_sha256"]), "image_digest_status": builder.IMAGE_DIGEST_STATUS,
        "core_release_sha256": builder.CORE_RELEASE_SHA256,
        "clean_dry_run_receipt_sha256": builder.CLEAN_RECEIPT_SHA256,
        "baseline_report_sha256": sha(b"synthetic baseline"),
        "platform_probe": {"gpu_name": "Tesla T4", "compute_capability": "7.5",
                           "cuda_driver_version": "13000", "cuda_runtime_version": "12080"},
        "runtime_build_observed": {
            "BUILD_DATE": "synthetic-build", "GIT_COMMIT": "a" * 40,
            "CUDA_VERSION": "12.8.1", "COLAB_IMAGE_TYPE": "gpu",
            "cuda_home": "/synthetic/cuda", "nvcc_path": "/synthetic/cuda/bin/nvcc",
            "nvidia_device_count": 1, "python_version": "3.12.3", "numpy_version": "2.4.4",
        },
        "nvcc_version": "synthetic nvcc version",
        "compiler_flags": list(plan["compile_flags"]),
        "mutations": mutations,
    }
    body.update(changes)
    for key in drop:
        body.pop(key, None)
    body["content_sha256"] = sha(builder._canonical(body)) if rehash else "0" * 64
    return canon(body).decode("ascii")


def main() -> int:
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        print("FAIL: PYTHONDONTWRITEBYTECODE=1 is required", file=sys.stderr)
        return 2
    real_a = ROOT / builder.A_RELEASE_REL
    real_a_absent = not real_a.exists() and not real_a.is_symlink()
    before = live_hashes(ROOT)
    caches_before = pycache_dirs()

    # --- constants and live pins ----------------------------------------------
    check(len(builder.SOURCE_RELS) == 12 and len(set(builder.SOURCE_RELS)) == 12 and
          len(builder.FIXED_RELS) == 4 and len(NON_A_RELS) == 16 and
          len(builder.BUNDLE_RELS) == 17 and builder.BUNDLE_FILE_COUNT == 17,
          "bundle is exactly 12 sources + clean release + clean receipt + 2 authorities + A release")
    check(builder.LAUNCH_TIMEOUT_SECONDS == 7200, "single-launch cap is 7200 seconds")
    check(builder.SUBMITTED_DOCKER_IMAGE is None and builder.REQUIRED_IMAGE_TYPE == "gpu" and
          builder.BUILD_ENV_NAMES == ("BUILD_DATE", "GIT_COMMIT", "CUDA_VERSION"),
          "no submitted image; observed GPU image type and three build fields are required")
    check(before[builder.CORE_RELEASE_REL] == builder.CORE_RELEASE_SHA256 and
          before[builder.CLEAN_RECEIPT_REL] == builder.CLEAN_RECEIPT_SHA256 and
          all(before[rel] == digest for rel, digest in builder.AUTHORITY_SHA256.items()),
          "live clean release, clean T4 receipt and authorities match builder pins")
    try:
        plan = builder.current_plan()
    except builder.BundleError as exc:
        check(False, "current qualifier plan is available: " + str(exc))
        return report()
    check(plan["source_sha256"] == {rel: before[rel] for rel in builder.SOURCE_RELS},
          "current plan binds the live 12-file source map")
    check(builder.check_plan(dict(plan)) == plan, "current plan passes the builder's independent self-hash check")
    qualifier = builder._load_qualifier()
    old_origin = qualifier.core.__file__
    old_cache_prefix = sys.pycache_prefix
    shadow_error = io.StringIO()
    try:
        qualifier.core.__file__ = "/unreviewed/research/g9/cuda_qualification/stage2_cuda_core_stream_engine.py"
        with contextlib.redirect_stderr(shadow_error):
            try:
                runpy.run_path(str(ROOT / builder.CLI_REL), run_name="g9_shadow_probe")
            except SystemExit as exc:
                shadow_code = exc.code
            else:
                shadow_code = 0
    finally:
        qualifier.core.__file__ = old_origin
        sys.pycache_prefix = old_cache_prefix
    check(shadow_code == 2 and "import escaped the staged source" in shadow_error.getvalue(),
          "reviewed CLI refuses a Python module imported from outside the staged root")

    with tempfile.TemporaryDirectory(prefix="g9-A-bundle-verify-") as temporary:
        tmp = Path(temporary)

        # --- read-only --plan and CLI refusals on the real tree ----------------
        first_plan = run_builder_cli("--plan")
        second_plan = run_builder_cli("--plan")
        check(first_plan.returncode == 0 and first_plan.stdout == second_plan.stdout,
              "--plan succeeds deterministically without an A release: " + first_plan.stderr.strip())
        summary = json.loads(first_plan.stdout) if first_plan.returncode == 0 else {}
        check(summary == builder.plan_summary(ROOT, plan), "CLI --plan equals the in-process plan summary")
        check(summary.get("plan_content_sha256") == plan["content_sha256"] and
              summary.get("source_sha256") == plan["source_sha256"] and
              summary.get("bundle_file_count") == 17 and summary.get("writes") == "none" and
              set(summary.get("fixed_sha256", {})) == set(builder.FIXED_RELS) and "status" not in summary,
              "plan summary binds the current plan and proposes no approved release")
        for extra in (["--reviewed", "0" * 64], ["--kaggle-user", "example-user"],
                      ["--output-dir", str(tmp / "plan-out")]):
            check(run_builder_cli("--plan", *extra).returncode == 1 and not (tmp / "plan-out").exists(),
                  "--plan refuses extra argument " + extra[0])
        check(run_builder_cli("--plan", bytecode_env=False).returncode == 1,
              "builder requires PYTHONDONTWRITEBYTECODE=1")
        check(run_builder_cli().returncode == 1 and run_builder_cli("--reviewed", "0" * 64).returncode == 1,
              "bundling without all of --reviewed/--kaggle-user/--output-dir is refused")
        real = run_builder_cli("--reviewed", "0" * 64, "--kaggle-user", "example-user",
                               "--output-dir", str(tmp / "real"))
        check(real.returncode == 1 and not (tmp / "real").exists() and
              (not real_a_absent or "approved A release is absent" in real.stderr),
              "real tree refuses a wrong release hash before output: " + real.stderr.strip())
        if not real_a_absent:
            real_sha = sha(real_a.read_bytes())
            real_raw, real_release = builder.load_a_release(ROOT, real_sha)
            check(real_raw == real_a.read_bytes() and
                  real_release["plan_content_sha256"] == plan["content_sha256"] and
                  real_release["source_sha256"] == plan["source_sha256"],
                  "real owner-approved A release binds the current plan and source map")
            real_good = run_builder_cli("--reviewed", real_sha,
                                        "--kaggle-user", "example-user",
                                        "--output-dir", str(tmp / "real-approved"))
            check(real_good.returncode == 0 and (tmp / "real-approved").is_dir() and
                  sorted(p.name for p in (tmp / "real-approved").iterdir()) ==
                  sorted([builder.CODE_FILE, builder.METADATA_FILE]),
                  "real approved release builds exactly two offline files")

        # --- synthetic approved A release, only inside a temporary copy --------
        copy_root = tmp / "copy"
        for rel in NON_A_RELS:
            (copy_root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, copy_root / rel)
        a_path = copy_root / builder.A_RELEASE_REL
        good_body = {"plan_content_sha256": plan["content_sha256"], "schema": builder.A_RELEASE_SCHEMA,
                     "source_sha256": dict(plan["source_sha256"]), "status": "approved"}
        good_raw = canon(good_body)
        a_path.write_bytes(good_raw)
        a_sha = sha(good_raw)
        check(real_a_absent == (not real_a.exists() and not real_a.is_symlink()),
              "synthetic A release is written only in the temporary copy")
        expected_bound = {**{rel: before[rel] for rel in NON_A_RELS}, builder.A_RELEASE_REL: a_sha}

        def run_main(*argv: str, root: Path = copy_root, plan_arg: dict | None = plan) -> tuple[int, str, str]:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = builder.main(list(argv), root=root, plan=plan_arg)
            return rc, out.getvalue(), err.getvalue()

        bundle_args = ("--reviewed", a_sha, "--kaggle-user", "example-user", "--output-dir")
        rc_a, out_a, err_a = run_main(*bundle_args, str(tmp / "a"))
        check(rc_a == 0, "builder bundles against the synthetic approved A release: " + err_a.strip())
        if rc_a != 0:
            return report()
        rc_b, _, _ = run_main(*bundle_args, str(tmp / "b"))
        rc_c, _, err_c = run_main(*bundle_args, str(tmp / "c"), plan_arg=None)
        names = sorted(p.name for p in (tmp / "a").iterdir())
        check(names == sorted([builder.METADATA_FILE, builder.CODE_FILE]), "bundle holds exactly two files")
        check(rc_b == 0 and rc_c == 0 and
              all((tmp / "a" / n).read_bytes() == (tmp / d / n).read_bytes() for n in names for d in ("b", "c")),
              "bundle generation is deterministic, including with the plan recomputed: " + err_c.strip())
        cross_process = (
            "from pathlib import Path; import hashlib; "
            "from research.g9.kaggle_dry_run import build_g9_cuda_core_A_bundle as b; "
            "print(hashlib.sha256(b.build_bundle('example-user', "
            "'" + a_sha + "', Path('" + str(copy_root) + "'))[b.CODE_FILE]).hexdigest())"
        )
        seed_digests = []
        for seed in ("1", "2"):
            result = subprocess.run(
                [sys.executable, "-c", cross_process], cwd=ROOT,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": seed},
                text=True, capture_output=True, check=False, timeout=60)
            seed_digests.append((result.returncode, result.stdout.strip(), result.stderr))
        check(all(rc == 0 and digest == sha((tmp / "a" / builder.CODE_FILE).read_bytes())
                  and not stderr for rc, digest, stderr in seed_digests),
              "launcher bytes are deterministic across Python hash seeds")
        bundle_summary = json.loads(out_a)
        check(bundle_summary == {
            "schema": "decisions_os/g9_cuda_core_A_kaggle_bundle/v1", "a_release_sha256": a_sha,
            "plan_content_sha256": plan["content_sha256"],
            "kernel_id": "example-user/" + builder.kernel_slug(a_sha),
            "submitted_docker_image": None, "image_digest_status": "post_run_metadata_audit_required",
            "launch_timeout_seconds_cap_not_guarantee": 7200, "bundled_sha256": expected_bound,
            "output_dir": str(tmp / "a"),
            "files_sha256": {n: sha((tmp / "a" / n).read_bytes()) for n in names}, "pushed": False},
              "builder summary is exact and records no push")

        # --- output-dir policy -------------------------------------------------
        check(run_main(*bundle_args, str(tmp / "a"))[0] == 1, "non-empty output dir is refused")
        (tmp / "afile").write_text("x")
        check(run_main(*bundle_args, str(tmp / "afile"))[0] == 1, "existing file as output dir is refused")
        check(run_main(*bundle_args, str(tmp / "missing" / "deep"))[0] == 1, "missing parent is refused")
        (tmp / "empty").mkdir()
        check(run_main(*bundle_args, str(tmp / "empty"))[0] == 0, "existing empty output dir is accepted")
        inside_copy = copy_root / "research" / "out"
        check(run_main(*bundle_args, str(inside_copy))[0] == 1 and not inside_copy.exists(),
              "output dir inside the bound tree is refused")
        inside_real = HERE / "must_not_be_created_A"
        check(run_main(*bundle_args, str(inside_real))[0] == 1 and not inside_real.exists(),
              "output dir inside the project is refused")
        (tmp / "link").symlink_to(tmp / "empty2", target_is_directory=True)
        check(run_main(*bundle_args, str(tmp / "link"))[0] == 1, "symlink output dir is refused")

        # --- metadata ----------------------------------------------------------
        slug = builder.kernel_slug(a_sha)
        title = builder.kernel_title(a_sha)
        metadata_bytes = (tmp / "a" / builder.METADATA_FILE).read_bytes()
        metadata = json.loads(metadata_bytes)
        check(metadata_bytes == (json.dumps(metadata, sort_keys=True, indent=2) + "\n").encode("ascii"),
              "metadata is canonical sorted JSON with one final LF")
        check(metadata == {
            "id": "example-user/" + slug, "title": title, "code_file": builder.CODE_FILE,
            "language": "python", "kernel_type": "script", "is_private": True, "enable_gpu": True,
            "enable_tpu": False, "enable_internet": False, "machine_shape": "NvidiaTeslaT4",
            "keywords": [], "dataset_sources": [], "competition_sources": [], "kernel_sources": [],
            "model_sources": []},
              "metadata is exactly a private T4 GPU script, internet off, no sources, no image")
        check(set(metadata) <= KAGGLE_CLI_2_2_4_PUSH_KEYS, "metadata uses only keys Kaggle CLI 2.2.4 push reads")
        check(b"docker_image" not in metadata_bytes and b"pinning_type" not in metadata_bytes,
              "neither an image nor a pinning type is submitted")
        check(slug == "g9-cuda-core-a-corruption-qualification-" + a_sha[:8] and
              title.lower().replace(" ", "-") == slug and 5 <= len(title) <= 50 and
              not any(slug.startswith(prefix) for prefix in SPENT_SLUG_PREFIXES) and
              builder.kernel_slug(sha(b"another A release")) != slug,
              "new slug is derived from the A release SHA and never addresses a spent kernel")

        # --- launcher structure ------------------------------------------------
        script_bytes = (tmp / "a" / builder.CODE_FILE).read_bytes()
        script = script_bytes.decode("ascii")
        tree = ast.parse(script)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module.split(".")[0])
        check(imports == LAUNCHER_IMPORTS, "launcher imports only the expected standard-library modules")
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        dotted = [f"{c.func.value.id}.{c.func.attr}" for c in calls
                  if isinstance(c.func, ast.Attribute) and isinstance(c.func.value, ast.Name)]
        named = [c.func.id for c in calls if isinstance(c.func, ast.Name)]
        check(dotted.count("subprocess.run") == 1 and
              not [d for d in dotted if d.startswith("subprocess.") and d != "subprocess.run"],
              "exactly one subprocess.run call site and no other subprocess API")
        check(not {"exec", "eval", "compile", "__import__"} & set(named) and
              not [d for d in dotted if d in ("os.system", "os.execv", "os.execve", "os.popen", "os.spawnv")],
              "no alternate execution path in launcher")
        check(script.count("--qualify-corruptions") == 2 and "--qualify-self-test" not in script and
              "--plan" not in script, "reviewed A flag appears only in the docstring and the single command")
        check(f"A_RELEASE_SHA256 = {a_sha!r}" in script and
              f"PLAN_CONTENT_SHA256 = {plan['content_sha256']!r}" in script and
              "LAUNCH_TIMEOUT_SECONDS = 7200" in script and "not a runtime guarantee" in script and
              "SUBMITTED_DOCKER_IMAGE = None" in script and "@sha256:" not in script and
              "docker_image" not in script.lower().replace("submitted_docker_image", "") and
              "G9_KAGGLE_IMAGE_BUILD" not in script and
              "G9_ALLOW_NONSCIENTIFIC_CUDA_QUALIFICATION" not in script,
              "launcher embeds the A/plan SHAs, a 7200 s cap stated as no guarantee, and no digest claim")
        check(f"RECEIPT_SCHEMA = {builder.RECEIPT_SCHEMA!r}" in script and
              f"PENDING_VERDICT = {builder.PENDING_VERDICT!r}" in script and
              f"AMENDMENT_A_STATUS = {builder.AMENDMENT_A_STATUS!r}" in script and
              f"RECEIPT_MODE = {builder.RECEIPT_MODE!r}" in script,
              "launcher embeds the exact pending receipt scope")
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        check_dotted = sorted(f"{n.func.value.id}.{n.func.attr}" for name in
                              ("environment_check", "_device_nodes", "_valid_build_value")
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
        entries = entries_of(script)
        embedded = {rel: data for rel, _, data in entries}
        check(len(entries) == 17 and set(embedded) == builder.BUNDLE_RELS, "payload holds exactly the 17 bound paths")
        check(all(embedded[rel] == (copy_root / rel).read_bytes() for rel in embedded) and
              embedded[builder.A_RELEASE_REL] == good_raw, "embedded bytes equal the bound bytes")
        check({rel: digest for rel, digest, _ in entries} == expected_bound, "embedded digests equal the bound table")
        check(with_payload(script, entries) == script, "payload re-rendering is exact (tamper helper is faithful)")

        # --- builder refusals --------------------------------------------------
        def build(reviewed, plan_arg=plan, user="example-user"):
            return builder.build_bundle(user, reviewed, root=copy_root, plan=plan_arg)

        check(not refuses(build, a_sha) and build(a_sha)[builder.CODE_FILE] == script_bytes,
              "in-process build equals the CLI build")
        for bad in ("0" * 64, a_sha.upper(), a_sha[:63], a_sha + "0", "", None, 7):
            check(refuses(build, bad), f"bad or mismatched --reviewed refused: {bad!r}")
        for user in ("", "Example", "a/b", "-ab", "ab-", "a--b", "a_b", "a b", "x" * 60, "ab\n"):
            check(refuses(build, a_sha, user=user), f"bad kaggle user refused: {user!r}")

        def body(**changes) -> dict:
            result = dict(good_body)
            for key, value in changes.items():
                if value is DROP:
                    result.pop(key, None)
                else:
                    result[key] = value
            return result

        source_map = dict(plan["source_sha256"])
        victim_rel = builder.SOURCE_RELS[0]
        release_variants = {
            "pretty-printed": (json.dumps(good_body, sort_keys=True, indent=2) + "\n").encode("ascii"),
            "no final LF": builder._canonical(good_body),
            "two final LFs": good_raw + b"\n",
            "status pending": canon(body(status="pending")),
            "status missing": canon(body(status=DROP)),
            "clean release schema": canon(body(schema=builder.CORE_RELEASE_SCHEMA)),
            "extra key": canon(body(note="synthetic")),
            "plan sha missing": canon(body(plan_content_sha256=DROP)),
            "plan sha wrong": canon(body(plan_content_sha256="0" * 64)),
            "plan sha uppercase": canon(body(plan_content_sha256=plan["content_sha256"].upper())),
            "source map missing one": canon(body(source_sha256={k: v for k, v in source_map.items()
                                                                if k != victim_rel})),
            "source map extra": canon(body(source_sha256={**source_map, "research/g9/extra.py": sha(b"")})),
            "source digest wrong": canon(body(source_sha256={**source_map, builder.CLI_REL: sha(b"other")})),
            "source map is a list": canon(body(source_sha256=sorted(source_map))),
            "JSON array": canon([good_body]),
            "not JSON": b"approved\n",
        }
        for label, raw in release_variants.items():
            a_path.write_bytes(raw)
            check(raw != good_raw and refuses(build, sha(raw)), "A release refused: " + label)
            a_path.write_bytes(good_raw)
        check(not refuses(build, a_sha), "good synthetic A release restored and accepted")

        a_path.unlink()
        message = refusal(builder.build_bundle, "example-user", a_sha, root=copy_root, plan="not a plan") or ""
        check("approved A release is absent" in message, "absent A release refuses before any plan is consulted")
        (tmp / "elsewhere.json").write_bytes(good_raw)
        a_path.symlink_to(tmp / "elsewhere.json")
        check(refuses(build, a_sha), "symlinked A release refused")
        a_path.unlink()
        a_path.mkdir()
        check(refuses(build, a_sha), "directory in place of the A release refused")
        a_path.rmdir()
        a_path.write_bytes(good_raw)

        def rehashed(changed: dict) -> dict:
            result = {k: v for k, v in changed.items() if k != "content_sha256"}
            result["content_sha256"] = sha(builder._canonical(result))
            return result

        plan_variants = {
            "content hash wrong": {**plan, "content_sha256": "0" * 64},
            "body changed without rehash": {**plan, "mode": "other"},
            "rehashed body the A release does not bind": rehashed({**plan, "mode": "other"}),
            "rehashed source map missing one": rehashed({**plan, "source_sha256": {
                k: v for k, v in source_map.items() if k != victim_rel}}),
            "rehashed source digest differs": rehashed({**plan, "source_sha256": {
                **source_map, builder.CLI_REL: sha(b"other")}}),
            "rehashed clean release pin wrong": rehashed({**plan, "core_release_sha256": "0" * 64}),
            "rehashed duplicate mutation": rehashed({**plan, "mutations": [
                plan["mutations"][0], *plan["mutations"][1:-1], plan["mutations"][0]]}),
            "rehashed missing mutation": rehashed({**plan, "mutations": plan["mutations"][:-1]}),
            "rehashed compiler flags drift": rehashed({**plan, "compile_flags": ["-ffast-math"]}),
            "not a dict": [],
        }
        for label, variant in plan_variants.items():
            check(refuses(build, a_sha, plan_arg=variant), "plan mismatch refused: " + label)

        # An A release consistent with drifted bytes but not with the current plan.
        for drift_rel in ("research/g9/verify_stage2_cuda_core_corruption_qualification_fixtures.py",
                          "research/g9/cuda_qualification/stage2_cuda_core_stream_engine.cu"):
            victim = copy_root / drift_rel
            original = victim.read_bytes()
            victim.write_bytes(original + b"\n// drift\n")
            drifted = canon(body(source_sha256={**source_map, drift_rel: sha(victim.read_bytes())}))
            a_path.write_bytes(drifted)
            check(refuses(build, sha(drifted)), "A release binding drifted bytes, not the current plan, refused: "
                  + drift_rel)
            victim.write_bytes(original)
            a_path.write_bytes(good_raw)

        for rel in NON_A_RELS:
            victim = copy_root / rel
            original = victim.read_bytes()
            victim.write_bytes(original + b" ")
            check(refuses(build, a_sha), "tampered bound file refused: " + rel)
            victim.unlink()
            check(refuses(build, a_sha), "missing bound file refused: " + rel)
            victim.write_bytes(original)
        (copy_root / "research/g9/smuggle_me.py").write_text("print('x')\n")
        rebuilt = build(a_sha)[builder.CODE_FILE]
        check(rebuilt == script_bytes and b"smuggle_me" not in rebuilt, "unbound files are never embedded")

        # --- launcher: good path with sentinel ---------------------------------
        counter = [0]

        def fresh(name: str) -> Path:
            path = tmp / "work" / name
            path.mkdir(parents=True)
            return path

        def fixture() -> Fixture:
            counter[0] += 1
            return Fixture(tmp / "fixtures" / str(counter[0]))

        receipt_text = synthetic_receipt(a_sha, plan)
        good = fixture()
        work = fresh("ok")
        sentinel = Sentinel(0, receipt_text)
        rc, out, _ = run_launcher(script, sentinel, work, good)
        check(rc == 0 and len(sentinel.calls) == 1, "good launcher calls the mocked CLI exactly once")
        call = sentinel.calls[0] if sentinel.calls else {"command": [], "kwargs": {}, "staged": {}}
        check(call["command"] == [sys.executable, builder.CLI_REL, "--qualify-corruptions", "--reviewed", a_sha],
              "launcher command is the reviewed A CLI invocation")
        check(call["kwargs"].get("env") == {**good.environ, "PYTHONDONTWRITEBYTECODE": "1", builder.ALLOW_ENV: "1"},
              "launcher environment is the checked environment plus exactly the two required flags")
        check(call["staged"] == expected_bound, "staged root holds exactly the 17 bound files at launch time")
        check(call["kwargs"].get("check") is False and call["kwargs"].get("timeout") == 7200 and
              call["kwargs"].get("capture_output") is True and call["kwargs"].get("text") is True,
              "single capped launch with captured output")
        check(not Path(call["kwargs"].get("cwd", str(tmp / "never"))).exists(),
              "temporary staging root is removed after the launch")
        check(sorted(p.name for p in work.iterdir()) == [builder.RECEIPT_NAME] and
              (work / builder.RECEIPT_NAME).read_text() == receipt_text,
              "only the receipt is saved, verbatim, on success")
        check(printed_diagnostics(out) == {
            "submitted_docker_image": None, "image_digest_status": "post_run_metadata_audit_required",
            "COLAB_IMAGE_TYPE": "gpu",
            "build_env": {"BUILD_DATE": "synthetic-build-date", "GIT_COMMIT": "synthetic-git-commit",
                          "CUDA_VERSION": "12.8.1"},
            "CUDA_HOME": str(good.cuda), "cuda_home_bin_on_path": True, "nvcc_path": str(good.nvcc),
            "nvidia_device_nodes": ["nvidia0"], "problems": []},
              "printed diagnostics are exact, bounded and nonsecret")
        check(good.nvcc.read_text() == Fixture.NVCC_STUB, "nvcc stub untouched (looked up, never run)")

        work = fresh("boundary-128")
        case = fixture()
        case.environ["BUILD_DATE"] = "b" * 128
        sentinel = Sentinel(0, receipt_text)
        check(run_launcher(script, sentinel, work, case)[0] == 0 and len(sentinel.calls) == 1,
              "a 128-character build field is accepted, matching the qualifier bound")

        # --- launcher: post-launch failures, still exactly one call ------------
        def only_failure(work_dir: Path) -> bool:
            return sorted(p.name for p in work_dir.iterdir()) == [builder.FAILURE_NAME]

        work = fresh("rc1")
        sentinel = Sentinel(1, "x" * 100000, "FAIL Gate-9 CUDA corruption qualification: synthetic\n" * 2000)
        rc = run_launcher(script, sentinel, work, good)[0]
        check(rc == 1 and len(sentinel.calls) == 1 and only_failure(work) and
              (work / builder.FAILURE_NAME).stat().st_size < 40000 and
              '"problems": []' in (work / builder.FAILURE_NAME).read_text(),
              "nonzero rc: one call, only a bounded failure log carrying diagnostics")
        work = fresh("rc1-valid-receipt")
        sentinel = Sentinel(1, receipt_text)
        check(run_launcher(script, sentinel, work, good)[0] == 1 and only_failure(work),
              "a receipt-shaped stdout with nonzero rc is not saved")

        receipt_variants = {
            "schema wrong": synthetic_receipt(a_sha, plan, schema="decisions_os/g9_cuda_core_dry_run_receipt/v1"),
            "schema missing": synthetic_receipt(a_sha, plan, drop=("schema",)),
            "release sha wrong": synthetic_receipt(a_sha, plan, execution_release_sha256=builder.CORE_RELEASE_SHA256),
            "clean dry-run mode": synthetic_receipt(a_sha, plan, mode="non_scientific_dry_run"),
            "mode missing": synthetic_receipt(a_sha, plan, drop=("mode",)),
            "scientific outputs present": synthetic_receipt(a_sha, plan, scientific_outputs="present"),
            "scientific outputs missing": synthetic_receipt(a_sha, plan, drop=("scientific_outputs",)),
            "stage2 inputs missing": synthetic_receipt(a_sha, plan, drop=("stage2_inputs",)),
            "verdict passed": synthetic_receipt(a_sha, plan, verdict="passed"),
            "verdict missing": synthetic_receipt(a_sha, plan, drop=("verdict",)),
            "amendment satisfied": synthetic_receipt(a_sha, plan, amendment_A_status="satisfied"),
            "clean-run amendment status": synthetic_receipt(
                a_sha, plan, amendment_A_status="not_satisfied_corrupted_kernel_tests_pending"),
            "image digest claimed": synthetic_receipt(a_sha, plan, image_digest_status="sha256:" + "0" * 64),
            "plan sha wrong": synthetic_receipt(a_sha, plan, plan_content_sha256="0" * 64),
            "source map differs": synthetic_receipt(a_sha, plan, source_sha256={
                **source_map, builder.CLI_REL: sha(b"other")}),
            "empty mutation list": synthetic_receipt(a_sha, plan, mutations=[]),
            "dropped mutation": synthetic_receipt(
                a_sha, plan, mutations=json.loads(receipt_text)["mutations"][:-1]),
            "false Python rejection": synthetic_receipt(
                a_sha, plan, mutations=[
                    {**row, "python_reference_rejected": False} if i == 0 else row
                    for i, row in enumerate(json.loads(receipt_text)["mutations"])]),
            "wrong mutation source": synthetic_receipt(
                a_sha, plan, mutations=[
                    {**row, "source_sha256": "0" * 64} if i == 0 else row
                    for i, row in enumerate(json.loads(receipt_text)["mutations"])]),
            "missing baseline": synthetic_receipt(a_sha, plan, drop=("baseline_report_sha256",)),
            "wrong compiler flags": synthetic_receipt(a_sha, plan, compiler_flags=[]),
            "missing Python version": synthetic_receipt(
                a_sha, plan, runtime_build_observed={
                    key: value for key, value in json.loads(receipt_text)["runtime_build_observed"].items()
                    if key != "python_version"}),
            "content hash wrong": synthetic_receipt(a_sha, plan, rehash=False),
            "pretty printed": json.dumps(json.loads(receipt_text), sort_keys=True, indent=2) + "\n",
            "missing final LF": receipt_text[:-1],
            "extra trailing line": receipt_text + "extra\n",
            "JSON array": "[]\n",
            "not JSON": "not json",
            "empty": "",
        }
        for label, text in receipt_variants.items():
            work = fresh("receipt-" + label.replace(" ", "-"))
            sentinel = Sentinel(0, text)
            check(text != receipt_text and run_launcher(script, sentinel, work, good)[0] == 1 and
                  len(sentinel.calls) == 1 and only_failure(work),
                  "rc 0 without the exact pending receipt is a failure: " + label)

        for label, guard, text in (
            ("verdict", 'receipt.get("verdict") == PENDING_VERDICT and',
             receipt_variants["verdict passed"]),
            ("amendment status", 'receipt.get("amendment_A_status") == AMENDMENT_A_STATUS and',
             receipt_variants["amendment satisfied"]),
            ("content hash", 'receipt.get("content_sha256") == _sha(_canonical(body).encode("ascii")) and',
             receipt_variants["content hash wrong"]),
        ):
            weakened = script.replace(guard, "True and", 1)
            work = fresh("weakened-" + label.replace(" ", "-"))
            sentinel = Sentinel(0, text)
            check(weakened != script and run_launcher(weakened, sentinel, work, good)[0] == 0 and
                  (work / builder.RECEIPT_NAME).exists(),
                  "without the " + label + " guard the bad receipt would be saved (load-bearing)")

        work = fresh("timeout")
        sentinel = Sentinel(raise_timeout=True)
        check(run_launcher(script, sentinel, work, good)[0] == 1 and len(sentinel.calls) == 1 and
              only_failure(work) and "launch cap; not retried" in (work / builder.FAILURE_NAME).read_text(),
              "timeout: one call, no retry, only a failure log")
        work = fresh("oserror")
        sentinel = Sentinel(raise_oserror=True)
        check(run_launcher(script, sentinel, work, good)[0] == 1 and len(sentinel.calls) == 1 and only_failure(work),
              "start failure: one call, no retry, only a failure log")

        for name in (builder.RECEIPT_NAME, builder.FAILURE_NAME):
            work = fresh("preexisting-" + name)
            (work / name).write_text("old")
            sentinel = Sentinel(0, receipt_text)
            refused = False
            try:
                run_launcher(script, sentinel, work, good)
            except Exception:
                refused = True
            check(refused and not sentinel.calls and (work / name).read_text() == "old" and
                  sorted(p.name for p in work.iterdir()) == [name],
                  "pre-existing output refuses before launch: " + name)

        # --- launcher: observed-image preflight refuses before launch ----------
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

        def no_devices(case: Fixture) -> None:
            for node in case.dev.iterdir():
                node.unlink()

        def regular_file_device(case: Fixture) -> None:
            (case.dev / "nvidia0").unlink()
            (case.dev / "nvidia0").write_text("")

        def v1_like_cpu_image(case: Fixture) -> None:
            case.environ = {"PATH": str(case.base / "bin"), "HOME": str(case.base), "COLAB_IMAGE_TYPE": "cpu"}
            no_devices(case)

        missing_build = "is missing or not 1-128 printable ASCII characters"
        environment_cases = {
            "wrong image type (cpu)": (set_env(COLAB_IMAGE_TYPE="cpu"), "COLAB_IMAGE_TYPE is not gpu"),
            "missing image type": (set_env(COLAB_IMAGE_TYPE=None), "COLAB_IMAGE_TYPE is not gpu"),
            "missing nvcc": (lambda c: c.nvcc.unlink(), "nvcc is not an executable on PATH"),
            "non-executable nvcc": (lambda c: c.nvcc.chmod(0o644), "nvcc is not an executable on PATH"),
            "CUDA_HOME unset": (set_env(CUDA_HOME=None), "CUDA_HOME is unset"),
            "CUDA_HOME relative": (set_env(CUDA_HOME="usr/local/cuda"), "CUDA_HOME is unset"),
            "CUDA_HOME/bin off PATH": (set_env(PATH="{base}/bin"), "CUDA_HOME/bin is not on PATH"),
            "empty PATH": (set_env(PATH=""), "nvcc is not an executable on PATH"),
            "nvcc shadowed outside CUDA_HOME": (nvcc_elsewhere_first, "nvcc on PATH is not CUDA_HOME/bin/nvcc"),
            "no device evidence": (no_devices, "no /dev/nvidiaN"),
            "only nvidiactl": (lambda c: (c.dev / "nvidia0").unlink(), "no /dev/nvidiaN"),
            "device node is a regular file": (regular_file_device, "no /dev/nvidiaN"),
            "device name not nvidiaN": (lambda c: (c.dev / "nvidia0").rename(c.dev / "nvidia-uvm"),
                                        "no /dev/nvidiaN"),
            "BUILD_DATE missing": (set_env(BUILD_DATE=None), "BUILD_DATE " + missing_build),
            "BUILD_DATE empty": (set_env(BUILD_DATE=""), "BUILD_DATE " + missing_build),
            "BUILD_DATE too long": (set_env(BUILD_DATE="b" * 129), "BUILD_DATE " + missing_build),
            "BUILD_DATE non-ASCII": (set_env(BUILD_DATE="2026é"), "BUILD_DATE " + missing_build),
            "BUILD_DATE non-printable": (set_env(BUILD_DATE="2026\t01"), "BUILD_DATE " + missing_build),
            "GIT_COMMIT missing": (set_env(GIT_COMMIT=None), "GIT_COMMIT " + missing_build),
            "CUDA_VERSION missing": (set_env(CUDA_VERSION=None), "CUDA_VERSION " + missing_build),
            "v1-like CPU image": (v1_like_cpu_image, "COLAB_IMAGE_TYPE is not gpu"),
        }
        for label, (mutate, reason) in environment_cases.items():
            case = fixture()
            mutate(case)
            work = fresh("env-" + label.replace(" ", "-").replace("/", "_"))
            sentinel = Sentinel(0, receipt_text)
            rc = run_launcher(script, sentinel, work, case)[0]
            log = (work / builder.FAILURE_NAME).read_text() if (work / builder.FAILURE_NAME).exists() else ""
            check(rc == 2 and not sentinel.calls and only_failure(work) and
                  "pre-launch environment check refused" in log and reason in log,
                  "wrong environment refuses before launch with diagnostics: " + label)
        check(all(fragment in log for fragment in ("COLAB_IMAGE_TYPE is not gpu", "no /dev/nvidiaN",
                                                   "nvcc is not an executable on PATH",
                                                   "BUILD_DATE " + missing_build)),
              "v1-like CPU image records every missing condition")

        work = fresh("env-oversized-values")
        case = fixture()
        set_env(COLAB_IMAGE_TYPE="x" * 100000)(case)
        _, out, _ = run_launcher(script, Sentinel(0, receipt_text), work, case)
        diagnostics = printed_diagnostics(out) or {}
        check(len(diagnostics.get("COLAB_IMAGE_TYPE", "")) == 256 and
              (work / builder.FAILURE_NAME).stat().st_size < 20000, "diagnostic values are bounded")
        for label, mutate in (("refused", set_env(COLAB_IMAGE_TYPE="cpu")), ("accepted", set_env())):
            work = fresh("env-secret-" + label)
            case = fixture()
            mutate(case)
            case.environ.update(KAGGLE_KEY="must-not-leak", KAGGLE_USERNAME="must-not-leak")
            _, out, err = run_launcher(script, Sentinel(0, receipt_text), work, case)
            check("must-not-leak" not in out + err and
                  not any("must-not-leak" in p.read_text() for p in work.iterdir()),
                  "unrelated environment variables are never recorded: " + label)

        # --- the preflight fixtures are load-bearing ---------------------------
        for label, old, new, mutate in (
            ("problem refusal", "        if problems:\n", "        if problems and False:\n",
             set_env(COLAB_IMAGE_TYPE="cpu")),
            ("image-type check", '    if ENVIRON.get("COLAB_IMAGE_TYPE") != REQUIRED_IMAGE_TYPE:\n',
             "    if False:\n", set_env(COLAB_IMAGE_TYPE="cpu")),
            ("device check", "    if not devices:\n", "    if False:\n", no_devices),
            ("build-field check", "        if not _valid_build_value(ENVIRON.get(key)):\n",
             "        if False:\n", set_env(BUILD_DATE=None)),
        ):
            disarmed = script.replace(old, new, 1)
            case = fixture()
            mutate(case)
            sentinel = Sentinel(0, receipt_text)
            run_launcher(disarmed, sentinel, fresh("disarmed-" + label.replace(" ", "-")), case)
            check(disarmed != script and len(sentinel.calls) == 1,
                  "without the " + label + " the bad environment would launch (load-bearing)")

        # --- launcher: tampered embedded payloads never launch -----------------
        authority_rel = sorted(builder.AUTHORITY_SHA256)[0]
        forged_core = canon({**json.loads(embedded[builder.CORE_RELEASE_REL]), "status": "pending"})
        other_plan_release = canon(body(plan_content_sha256="1" * 64))
        omitting_release = canon(body(source_sha256={k: v for k, v in source_map.items() if k != victim_rel}))

        def forged_release(raw: bytes) -> str:
            text = with_payload(script, edited(entries, builder.A_RELEASE_REL, data=raw, rehash=True))
            return text.replace(f"A_RELEASE_SHA256 = {a_sha!r}", f"A_RELEASE_SHA256 = {sha(raw)!r}", 1)

        flipped = bytearray(embedded[victim_rel])
        flipped[0] ^= 1
        tampered = {
            "flipped source byte": with_payload(script, edited(entries, victim_rel, data=bytes(flipped))),
            "renamed path": with_payload(script, edited(entries, entries[-1][0], new_rel="research/g9/renamed.py")),
            "path escape": with_payload(script, edited(entries, victim_rel, new_rel="research/../escape.py")),
            "duplicate path": with_payload(script, [entries[0], entries[0], *entries[2:]]),
            "extra file": with_payload(script, [*entries, ("research/g9/extra.py", sha(b""), b"")]),
            "dropped authority": with_payload(script, [e for e in entries if e[0] != authority_rel]),
            "digest swapped": with_payload(script, edited(entries, victim_rel, digest=sha(b"forged"))),
            "consistently forged source": with_payload(
                script, edited(entries, victim_rel, data=embedded[victim_rel] + b"#", rehash=True)),
            "consistently forged clean release": with_payload(
                script, edited(entries, builder.CORE_RELEASE_REL, data=forged_core, rehash=True)),
            "consistently forged A release": with_payload(
                script, edited(entries, builder.A_RELEASE_REL, data=canon(body(status="pending")), rehash=True)),
            "forged A release binding another plan": forged_release(other_plan_release),
            "forged A release omitting an embedded source": forged_release(omitting_release),
            "A release constant swapped": script.replace(f"A_RELEASE_SHA256 = {a_sha!r}",
                                                         f"A_RELEASE_SHA256 = {'0' * 64!r}", 1),
            "plan constant swapped": script.replace(f"PLAN_CONTENT_SHA256 = {plan['content_sha256']!r}",
                                                    f"PLAN_CONTENT_SHA256 = {'1' * 64!r}", 1),
        }
        for label, text in tampered.items():
            work = fresh("tamper-" + label.replace(" ", "-"))
            sentinel = Sentinel(0, receipt_text)
            rc = run_launcher(text, sentinel, work, good)[0] if text != script else None
            check(text != script and rc == 2 and not sentinel.calls and only_failure(work) and
                  "pre-launch payload verification refused" in (work / builder.FAILURE_NAME).read_text(),
                  "tampered launcher refuses before staging or launch, even on a good GPU: " + label)

    check(live_hashes(ROOT) == before, "bound project files unchanged after verification")
    check(real_a_absent == (not real_a.exists() and not real_a.is_symlink()),
          "real A release presence unchanged (verifier never writes research/decisions)")
    check(pycache_dirs() == caches_before and not list(HERE.glob("**/__pycache__")),
          "no bytecode directories created")
    return report()


if __name__ == "__main__":
    raise SystemExit(main())
