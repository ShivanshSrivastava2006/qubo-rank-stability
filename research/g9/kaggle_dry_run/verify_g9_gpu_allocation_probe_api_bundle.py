#!/usr/bin/env python3
"""Offline verifier for the Gate-9 API-launched GPU allocation probe bundle.

Standard library only.  Nothing here contacts Kaggle, reads Kaggle credentials,
pushes, creates a kernel, runs the probe cell, runs nvcc or touches a GPU.  The
probe cell is never executed: it is parsed with `ast` and hashed.

What is checked:
  * the bundle carries exactly the pinned section-4 probe cell, extracted from
    the pinned draft, and refuses on any drift (with load-bearing mutations);
  * the metadata is a private GPU T4 x2 script kernel with internet off, no
    sources, and no `docker_image` / `docker_image_pinning_type` of any kind;
  * the slug differs from both spent kernels;
  * `--plan` is pure and `--output-dir` is guarded;
  * the builder itself has no network, subprocess or credential capability;
  * the probe cell stays non-scientific, bounded, compiles nothing, and keeps
    the allocation and compiler statuses separate;
  * the post-run source-identity rules of draft section 7.1, including the
    12-byte Kaggle `script` marker, accept only the reviewed bytes.

`--pulled-source PATH` additionally runs the section-7.1 identity check against
a real pulled source file, offline and read-only.  It is optional; every other
check runs regardless.

Uses explicit checks (not assert) so it is meaningful under `python3 -O`.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import ast
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_g9_gpu_allocation_probe_api_bundle as builder  # noqa: E402

ROOT = builder.ROOT
FAILURES: list[str] = []
PASSES = 0

USER = "probe-user"
CELL_BYTES = 10227

# Every metadata key read by kaggle 2.2.4 KaggleApi.kernels_push (the same list
# the v2 verifier pins).  Anything outside it would be silently ignored.
KAGGLE_CLI_2_2_4_PUSH_KEYS = frozenset({
    "id", "id_no", "title", "code_file", "language", "kernel_type", "is_private", "enable_gpu",
    "enable_tpu", "enable_internet", "dataset_sources", "competition_sources", "kernel_sources",
    "model_sources", "keywords", "docker_image_pinning_type", "docker_image", "machine_shape",
})
EXPECTED_METADATA_KEYS = frozenset({
    "id", "title", "code_file", "language", "kernel_type", "is_private", "enable_gpu",
    "enable_tpu", "enable_internet", "machine_shape", "keywords", "dataset_sources",
    "competition_sources", "kernel_sources", "model_sources",
})
# The builder may import only these.  No subprocess, no socket, no urllib, no
# http, no kaggle: the tool is structurally incapable of a Kaggle call.
BUILDER_ALLOWED_IMPORTS = frozenset({"__future__", "argparse", "hashlib", "json", "pathlib", "re", "sys"})
# The probe cell may import only these (draft section 4).
CELL_ALLOWED_IMPORTS = frozenset({"glob", "json", "os", "shutil", "stat", "subprocess"})
FORBIDDEN_CALL_NAMES = frozenset({
    "open", "eval", "exec", "compile", "__import__", "input",
    "os.system", "os.popen", "os.remove", "os.unlink", "os.rmdir", "os.execv", "os.execvp",
    "os.fork", "os.spawnv", "os.makedirs", "os.mkdir", "os.chmod", "os.rename",
    "subprocess.Popen", "subprocess.call", "subprocess.check_call", "subprocess.check_output",
    "subprocess.getoutput", "shutil.rmtree", "shutil.copy", "socket.socket",
    "urllib.request.urlopen", "Path", "write_text", "write_bytes",
})
# Draft section 4: the cell reads exactly these environment variables.
CELL_ENVIRONMENT_READS = frozenset({"COLAB_IMAGE_TYPE", "CUDA_HOME", "PATH"})
# The four statuses must stay separate and present.
CELL_REQUIRED_TOKENS = (
    '"gpu_allocation"', '"cuda_compiler"', '"cuda_compiler_usable"',
    '"launcher_guard_cuda_home"', '"probe_conditions_met"',
    '"compilation_performed": False', '"authorizes": "nothing"',
    "GATE9_PROBE_NOT_CLEAN", "SCHEMA_VERSION = 3",
)


def check(condition: bool, label: str) -> None:
    global PASSES
    if condition:
        PASSES += 1
    else:
        FAILURES.append(label)
        print("FAIL: " + label, file=sys.stderr)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def refuses(call, needle: str = "") -> bool:
    """True when `call` raises BundleError, optionally mentioning `needle`."""
    try:
        call()
    except builder.BundleError as exc:
        return needle in str(exc)
    except Exception:
        return False
    return False


def fake_root(tmp: Path, draft: bytes | None, name: str) -> Path:
    """A minimal project root holding (or missing) a probe draft."""
    root = tmp / name
    (root / "research" / "g9" / "kaggle_dry_run").mkdir(parents=True)
    if draft is not None:
        (root / builder.DRAFT_REL).write_bytes(draft)
    return root


# --------------------------------------------------------------------------
# Draft section 7.1 post-run source identity.  Offline, read-only, no retry.
# --------------------------------------------------------------------------

def pulled_source_identity(data: bytes) -> dict:
    """Apply draft section 7.1 to pulled source bytes.

    Returns a record naming the branch used, the raw hash, the extracted hash
    and which pinned variant matched (or none).  A mismatch is an identity
    finding: no allocation, compiler or usability conclusion follows from it,
    and it never authorizes a retry.
    """
    pinned = {
        "full_with_terminal_lf": builder.CELL_SHA256_FULL,
        "without_one_terminal_lf": builder.CELL_SHA256_WITHOUT_TERMINAL_LF,
    }
    record: dict = {
        "raw_sha256": sha(data),
        "raw_bytes": len(data),
        "branch": None,
        "script_marker_present": data.startswith(builder.KAGGLE_SCRIPT_CELL_MARKER),
        "extracted_sha256": None,
        "matched_pinned_variant": None,
        "identity_established": False,
        "problems": [],
    }
    extracted: bytes | None = None
    if record["script_marker_present"]:
        record["branch"] = "script"
        extracted = data[len(builder.KAGGLE_SCRIPT_CELL_MARKER):]
    else:
        try:
            document = json.loads(data)
        except ValueError:
            document = None
        if type(document) is dict and "cells" in document:
            record["branch"] = "notebook"
            cells = document["cells"]
            if type(cells) is not list or len(cells) != 1:
                record["problems"].append("notebook does not hold exactly one cell")
            elif type(cells[0]) is not dict or cells[0].get("cell_type") != "code":
                record["problems"].append("the single notebook cell is not a code cell")
            else:
                source = cells[0].get("source")
                if type(source) is str:
                    extracted = source.encode("utf-8")
                elif type(source) is list and all(type(part) is str for part in source):
                    extracted = "".join(source).encode("utf-8")
                else:
                    record["problems"].append("notebook cell source is not a string or list of strings")
        else:
            record["branch"] = "unknown"
            record["problems"].append(
                "pulled source is neither a marker-prefixed script nor a .ipynb notebook")
    if extracted is not None:
        record["extracted_sha256"] = sha(extracted)
        for variant, digest in sorted(pinned.items()):
            if record["extracted_sha256"] == digest:
                record["matched_pinned_variant"] = variant
        if record["matched_pinned_variant"] is None:
            record["problems"].append("extracted source matches neither pinned hash")
    record["identity_established"] = (
        record["matched_pinned_variant"] is not None and not record["problems"])
    return record


def notebook(cells: list) -> bytes:
    return json.dumps({"cells": cells, "metadata": {}, "nbformat": 4,
                       "nbformat_minor": 5}).encode("utf-8")


def code_cell(source) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": source}


# --------------------------------------------------------------------------

def dotted_name(node: ast.AST) -> str:
    parts = []
    while type(node) is ast.Attribute:
        parts.append(node.attr)
        node = node.value
    if type(node) is ast.Name:
        parts.append(node.id)
    return ".".join(reversed(parts))


def imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if type(node) is ast.Import:
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif type(node) is ast.ImportFrom and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def called_names(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if type(node) is ast.Call:
            name = dotted_name(node.func)
            if name:
                names.add(name)
                names.add(name.rsplit(".", 1)[-1])
    return names


def environment_reads(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if (type(node) is ast.Call and type(node.func) is ast.Attribute
                and node.func.attr == "get" and dotted_name(node.func).endswith("environ.get")
                and node.args and type(node.args[0]) is ast.Constant):
            names.add(node.args[0].value)
    return names


def call_count(tree: ast.AST, name: str) -> int:
    return sum(1 for node in ast.walk(tree)
               if type(node) is ast.Call and dotted_name(node.func) == name)


def dir_hashes(directory: Path) -> dict[str, str]:
    return {str(p.relative_to(directory)): sha(p.read_bytes())
            for p in sorted(directory.rglob("*")) if p.is_file()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline verifier (never contacts Kaggle)")
    parser.add_argument("--pulled-source",
                        help="optional: apply the section-7.1 identity check to a pulled source file")
    args = parser.parse_args(argv)

    before = dir_hashes(HERE)
    cell = builder.load_probe_cell(ROOT)
    bundle = builder.build_bundle(USER, ROOT)
    metadata_bytes = bundle[builder.METADATA_FILE]
    metadata = json.loads(metadata_bytes)
    report = builder.plan(USER, ROOT)

    # --- the cell is exactly the pinned draft cell --------------------------
    check(sha(cell) == builder.CELL_SHA256_FULL == report["probe_cell"]["sha256_full_with_terminal_lf"],
          "extracted cell matches the pinned full_with_terminal_lf hash")
    check(sha(cell[:-1]) == builder.CELL_SHA256_WITHOUT_TERMINAL_LF,
          "extracted cell matches the pinned without_one_terminal_lf hash")
    check(len(cell) == CELL_BYTES, "extracted cell is the expected byte length")
    check(sha((ROOT / builder.DRAFT_REL).read_bytes()) == builder.DRAFT_SHA256,
          "the live draft still hashes to the pinned draft")
    check(bundle[builder.CODE_FILE] == cell, "the bundle code file is the cell verbatim")
    check(len(builder.fenced_python_blocks((ROOT / builder.DRAFT_REL).read_bytes())) == 1,
          "the pinned draft has exactly one fenced python block")
    check(not any(p.name.endswith(".py") and sha(p.read_bytes()) == builder.CELL_SHA256_FULL
                  for p in HERE.iterdir() if p.is_file()),
          "no sidecar copy of the cell exists in the repository (draft section 7.1)")

    # --- fence scanner behaviour -------------------------------------------
    check(builder.fenced_python_blocks(b"a\n```python\nx = 1\n```\nb\n") == [b"x = 1\n"],
          "fence scanner returns the block with one terminal LF")
    check(builder.fenced_python_blocks(b"```\nplain\n```\n") == [],
          "fence scanner ignores unlabelled fences")
    check(len(builder.fenced_python_blocks(b"```python\na\n```\n```python\nb\n```\n")) == 2,
          "fence scanner finds every labelled block")
    check(refuses(lambda: builder.fenced_python_blocks(b"```python\na\n"), "unterminated"),
          "fence scanner refuses an unterminated block")

    with tempfile.TemporaryDirectory(prefix="g9-probe-verify-") as temporary:
        tmp = Path(temporary)
        draft = (ROOT / builder.DRAFT_REL).read_bytes()

        # --- drift in the draft or the cell refuses -------------------------
        check(refuses(lambda: builder.load_probe_cell(fake_root(tmp, None, "missing")), "missing"),
              "a missing draft refuses")
        check(refuses(lambda: builder.load_probe_cell(fake_root(tmp, draft + b"\n", "appended")),
                      "hash differs"),
              "an appended byte in the draft refuses on the draft hash")
        check(refuses(lambda: builder.load_probe_cell(
            fake_root(tmp, draft.replace(b"BOUNDED_TIMEOUT_S = 30", b"BOUNDED_TIMEOUT_S = 99", 1),
                      "edited")), "hash differs"),
              "an edited cell refuses on the draft hash")

        # load-bearing: with the draft hash re-pinned to the edited draft, the
        # cell hash must still refuse.
        edited = draft.replace(b"BOUNDED_TIMEOUT_S = 30", b"BOUNDED_TIMEOUT_S = 99", 1)
        check(edited != draft, "tamper applied: cell timeout changed")
        pinned_draft_sha = builder.DRAFT_SHA256
        builder.DRAFT_SHA256 = sha(edited)
        cell_hash_refused = refuses(
            lambda: builder.load_probe_cell(fake_root(tmp, edited, "repinned")), "pinned full")
        builder.DRAFT_SHA256 = pinned_draft_sha
        check(cell_hash_refused, "the cell hash check is load-bearing on its own")
        check(builder.DRAFT_SHA256 == pinned_draft_sha, "the pinned draft hash was restored")

        # --- output-dir guards ----------------------------------------------
        check(refuses(lambda: builder._prepare_output_dir(str(HERE)), "outside the project tree"),
              "a path inside the project tree refuses")
        check(refuses(lambda: builder._prepare_output_dir(""), "explicit"),
              "an empty --output-dir refuses")
        missing_parent = tmp / "absent" / "child"
        check(refuses(lambda: builder._prepare_output_dir(str(missing_parent)), "parent must exist"),
              "a missing parent refuses")
        link = tmp / "link"
        link.symlink_to(tmp, target_is_directory=True)
        check(refuses(lambda: builder._prepare_output_dir(str(link)), "symlink"),
              "a symlink --output-dir refuses")
        occupied = tmp / "occupied"
        occupied.mkdir()
        (occupied / "stray").write_bytes(b"")
        check(refuses(lambda: builder._prepare_output_dir(str(occupied)), "new or empty"),
              "a non-empty --output-dir refuses")

        # --- build mode writes exactly two files ----------------------------
        target = tmp / "staging"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = builder.main(["--kaggle-user", USER, "--output-dir", str(target)])
        written = sorted(p.name for p in target.iterdir())
        summary = json.loads(out.getvalue())
        check(rc == 0 and written == sorted([builder.METADATA_FILE, builder.CODE_FILE]),
              "build mode writes exactly the two bundle files")
        check((target / builder.CODE_FILE).read_bytes() == cell,
              "the written code file is the pinned cell byte for byte")
        check((target / builder.METADATA_FILE).read_bytes() == metadata_bytes,
              "the written metadata is the built metadata byte for byte")
        check(summary["mode"] == "build" and summary["output_dir"] == str(target) and
              summary["pushed"] is False and summary["cli_command_executed"] is False and
              summary["kaggle_contacted"] is False and summary["authorizes"] == "nothing",
              "the build summary records no push, no CLI execution and no authority")
        check(summary["files_sha256"] == {name: sha(data) for name, data in sorted(bundle.items())},
              "the build summary hashes match the bundle bytes")
        check(summary["planned_cli_command"] == ["kaggle", "kernels", "push", "-p", str(target)],
              "the planned CLI command names the staging directory and is only data")
        check(refuses(lambda: builder._prepare_output_dir(str(target)), "new or empty"),
              "a second build into the same directory refuses")

        # --- determinism ----------------------------------------------------
        again = tmp / "staging-again"
        with contextlib.redirect_stdout(io.StringIO()):
            builder.main(["--kaggle-user", USER, "--output-dir", str(again)])
        check(dir_hashes(again) == dir_hashes(target), "two builds are byte-identical")

        # --- --plan is pure -------------------------------------------------
        pure = tmp / "pure"
        pure.mkdir()
        cwd = os.getcwd()
        os.chdir(pure)
        try:
            recorded: list = []
            real_write, real_prepare = builder.write_bundle, builder._prepare_output_dir
            builder.write_bundle = lambda *a, **k: recorded.append(a)
            builder._prepare_output_dir = lambda *a, **k: recorded.append(a)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = builder.main(["--kaggle-user", USER, "--plan"])
            builder.write_bundle, builder._prepare_output_dir = real_write, real_prepare
        finally:
            os.chdir(cwd)
        plan_report = json.loads(out.getvalue())
        check(rc == 0 and not recorded and not list(pure.iterdir()),
              "--plan writes nothing and never reaches the writer")
        check(plan_report["mode"] == "plan" and plan_report["writes"] == "nothing" and
              "output_dir" not in plan_report,
              "--plan reports itself as writing nothing and names no output directory")
        check(plan_report["cli_command_executed"] is False and plan_report["pushed"] is False and
              plan_report["planned_cli_command"][-1] == "<output-dir>",
              "--plan prints the CLI command as an unexecuted placeholder")

        # --- mode selection is explicit -------------------------------------
        for bad, label in (([], "neither mode"), (["--plan", "--output-dir", str(tmp / "x")],
                                                  "both modes")):
            code = None
            with contextlib.redirect_stderr(io.StringIO()):
                try:
                    builder.main(["--kaggle-user", USER] + bad)
                except SystemExit as exc:
                    code = exc.code
            check(code == 2, "argument parsing rejects " + label)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = builder.main(["--kaggle-user", "Bad_User", "--plan"])
        check(rc == 1 and "FAIL bundle" in err.getvalue(), "an invalid username fails closed")

        # --- section 7.1 identity fixtures ----------------------------------
        good_script = builder.KAGGLE_SCRIPT_CELL_MARKER + cell
        check(report["expected_pulled_source_sha256"] == sha(good_script),
              "the plan's predicted pulled-source hash matches a marker-prefixed pull")
        accepted = {
            "marker + cell": (good_script, "script", "full_with_terminal_lf"),
            "marker + cell without terminal LF": (
                builder.KAGGLE_SCRIPT_CELL_MARKER + cell[:-1], "script", "without_one_terminal_lf"),
            "notebook, one code cell, string source": (
                notebook([code_cell(cell.decode("utf-8"))]), "notebook", "full_with_terminal_lf"),
            "notebook, one code cell, list source": (
                notebook([code_cell(cell.decode("utf-8").splitlines(keepends=True))]),
                "notebook", "full_with_terminal_lf"),
        }
        for label, (data, branch, variant) in accepted.items():
            record = pulled_source_identity(data)
            check(record["identity_established"] and record["branch"] == branch and
                  record["matched_pinned_variant"] == variant and not record["problems"],
                  "identity established: " + label)
        rejected = {
            "cell with no marker": cell,
            "wrong marker (CRLF)": b"# %% [code]\r\n" + cell,
            "marker + one edited byte": builder.KAGGLE_SCRIPT_CELL_MARKER + cell.replace(
                b"BOUNDED_TIMEOUT_S = 30", b"BOUNDED_TIMEOUT_S = 99", 1),
            "marker + truncated cell": builder.KAGGLE_SCRIPT_CELL_MARKER + cell[:-200],
            "marker stripped twice": cell[len(builder.KAGGLE_SCRIPT_CELL_MARKER):],
            "notebook with two cells": notebook(
                [code_cell(cell.decode("utf-8")), code_cell("")]),
            "notebook with a markdown cell": notebook(
                [{"cell_type": "markdown", "metadata": {}, "source": cell.decode("utf-8")}]),
            "notebook cell source not text": notebook([code_cell({"nope": 1})]),
            "empty file": b"",
            "unrelated bytes": b"print('hello')\n",
        }
        for label, data in rejected.items():
            record = pulled_source_identity(data)
            check(not record["identity_established"] and record["problems"] and
                  record["raw_sha256"] == sha(data),
                  "identity refused and the raw hash still recorded: " + label)

        if args.pulled_source:
            path = Path(args.pulled_source).expanduser()
            record = pulled_source_identity(path.read_bytes())
            print("pulled source identity (" + str(path) + "): "
                  + json.dumps(record, sort_keys=True, indent=2))
            check(record["identity_established"],
                  "supplied pulled source matches a pinned variant")

    # --- metadata ----------------------------------------------------------
    check(set(metadata) == EXPECTED_METADATA_KEYS, "metadata holds exactly the expected keys")
    check(set(metadata) <= KAGGLE_CLI_2_2_4_PUSH_KEYS, "every metadata key is read by CLI 2.2.4")
    check(not builder.FORBIDDEN_METADATA_KEYS & set(metadata) and
          b"docker_image" not in metadata_bytes,
          "no docker_image and no docker_image_pinning_type, not even as bytes")
    check(metadata["enable_gpu"] is True and metadata["machine_shape"] == "NvidiaTeslaT4",
          "GPU is requested as T4 x2 (NvidiaTeslaT4)")
    check(metadata["is_private"] is True and metadata["enable_internet"] is False and
          metadata["enable_tpu"] is False,
          "the kernel is private, internet off, no TPU")
    check(metadata["kernel_type"] == "script" and metadata["language"] == "python" and
          metadata["code_file"] == builder.CODE_FILE,
          "the kernel is a Python script pointing at the probe code file")
    check(all(metadata[key] == [] for key in
              ("keywords", "dataset_sources", "competition_sources", "kernel_sources", "model_sources")),
          "no dataset, competition, kernel or model sources")
    check(metadata["id"] == USER + "/" + builder.KERNEL_SLUG, "the id is <user>/<new slug>")
    check(builder.KERNEL_SLUG not in builder.SPENT_KERNEL_SLUGS and
          all(slug not in builder.KERNEL_SLUG for slug in builder.SPENT_KERNEL_SLUGS) and
          len(builder.SPENT_KERNEL_SLUGS) == 2,
          "the slug is new and names neither spent kernel")
    check(metadata_bytes.endswith(b"\n") and
          metadata_bytes == (json.dumps(metadata, sort_keys=True, indent=2,
                                        ensure_ascii=True) + "\n").encode("ascii"),
          "metadata bytes are canonical sorted ASCII JSON with one final LF")
    for bad in ("", "Bad", "a--b", "-a", "a-", "a" * 60, "us_er"):
        check(refuses(lambda bad=bad: builder.build_metadata(bad), "kaggle-user"),
              "an invalid Kaggle username refuses: " + repr(bad))

    # --- the builder has no Kaggle capability ------------------------------
    builder_source = Path(builder.__file__).read_bytes()
    builder_tree = ast.parse(builder_source)
    check(imported_modules(builder_tree) <= BUILDER_ALLOWED_IMPORTS,
          "the builder imports nothing beyond the allowed stdlib set")
    check(not {"subprocess", "socket", "urllib", "http", "requests", "kaggle", "kagglesdk",
               "ssl", "ftplib", "telnetlib", "smtplib"} & imported_modules(builder_tree),
          "the builder imports no network, subprocess or Kaggle module")
    check(b"KAGGLE_KEY" not in builder_source and b"KAGGLE_USERNAME" not in builder_source and
          b"kaggle.json" not in builder_source and b"/.kaggle" not in builder_source and
          b"~/.kaggle" not in builder_source,
          "the builder never names Kaggle credentials")
    check(builder.PLANNED_CLI_COMMAND == ("kaggle", "kernels", "push", "-p"),
          "the planned CLI command is an inert constant")

    # --- the probe cell stays non-scientific and bounded -------------------
    cell_text = cell.decode("utf-8")
    cell_tree = ast.parse(cell_text)
    check(imported_modules(cell_tree) == CELL_ALLOWED_IMPORTS,
          "the cell imports exactly the six stdlib modules of section 4")
    check(not FORBIDDEN_CALL_NAMES & called_names(cell_tree),
          "the cell opens no file, spawns nothing and writes nothing")
    check(environment_reads(cell_tree) == CELL_ENVIRONMENT_READS,
          "the cell reads exactly COLAB_IMAGE_TYPE, CUDA_HOME and PATH")
    check(call_count(cell_tree, "subprocess.run") == 1 and
          call_count(cell_tree, "run_bounded") == 2,
          "exactly one subprocess call site, reached exactly twice")
    check('run_bounded([exe, "-L"])' in cell_text and
          'run_bounded([exe, "--version"])' in cell_text,
          "the only two bounded commands are `nvidia-smi -L` and `nvcc --version`")
    check("timeout=BOUNDED_TIMEOUT_S" in cell_text and "BOUNDED_TIMEOUT_S = 30" in cell_text and
          "check=False" in cell_text,
          "both bounded calls carry the 30 second timeout and never raise on exit status")
    check(all(token in cell_text for token in CELL_REQUIRED_TOKENS),
          "the four statuses, probe_conditions_met and the fail-closed marker are all present")
    check("nvcc" in cell_text and " -o " not in cell_text and ".cu" not in cell_text and
          "-arch" not in cell_text and "gcc" not in cell_text,
          "the cell compiles, assembles and links nothing")
    check('"verdict"' not in cell_text and "numpy" not in cell_text and "torch" not in cell_text,
          "the cell emits no verdict and imports no numerical library")
    check(cell_text.count("raise RuntimeError") == 1 and
          cell_text.index("print(json.dumps(report") < cell_text.index("raise RuntimeError"),
          "the cell prints its JSON before failing closed")

    after = dir_hashes(HERE)
    check(after == before, "no file under kaggle_dry_run changed during verification")
    check(not list(HERE.glob("**/__pycache__")), "no bytecode written under kaggle_dry_run")
    status = "PASS" if not FAILURES else "FAIL"
    print(f"{status} g9 GPU allocation probe API bundle verifier: {PASSES} checks passed, "
          f"{len(FAILURES)} failed (optimize={sys.flags.optimize})")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    raise SystemExit(main())
