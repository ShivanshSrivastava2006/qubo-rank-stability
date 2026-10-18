#!/usr/bin/env python3
"""Isolated WP7b runtime, v2 D013 COPY -- CANDIDATE, NOT APPROVED.

This is the reviewed ``research/g9/kaggle_wp7b/wp7b_child_entry.py`` with one
functional change and no other difference.

The change: ``arm_permissions`` also sets the **v2** D013 permission variable,
``G9_ALLOW_NONSCIENTIFIC_D013_CUDA_V2_CORRUPTION_QUALIFICATION``. The reviewed
child sets only the v1 variable, and the reviewed v2 plan requires its own
separate variable and explicitly documents that the v1 variable does not arm
it. Without this line the v2 executor's release gate refuses before nvcc is
ever looked up, so the repaired candidate could not be exercised.

Both variables are set. The v1 one is still required by the v1 core
corruption qualification, which is unchanged and still runs.

The v2 arming variable is a PERMISSION for a non-scientific dry run of the
owner-approved candidate. It is not itself a release: the shipped v2 release
draft must independently be canonical and carry ``owner_approved: true``.

TMPDIR is additionally pinned to a durable directory the child computes itself
from the ``out_base`` and ``bundle_sha256`` it was already passed, rather than
inheriting whatever the provider happens to default to. Every runtime temp
operation in this process and in the launcher it drives therefore lands on the
durable staged volume, never on the provider's non-persistent default ``/tmp``.

Nothing else is altered: the staged-index and per-file hash verification, the
``-I -S`` process isolation, the forbidden-module and ``KAGGLE_*`` refusals,
the environment allowlist, the atomic receipt writing, the budget receipt path
and the typed difference record are all byte-identical to the reviewed child.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path


FORBIDDEN = ("requests", "urllib.request", "http.client", "socket")
FORBIDDEN_ROOTS = ("kaggle", "kagglehub")
ALLOW_D013 = "G9_ALLOW_NONSCIENTIFIC_D013_CUDA_CORRUPTION_QUALIFICATION"
ALLOW_CORE = "G9_ALLOW_NONSCIENTIFIC_CUDA_CORRUPTION_QUALIFICATION"
# NEW: the v2 plan's own separate arming variable. The v1 variable above does
# not arm it, so the v2 permission must be requested explicitly.
ALLOW_D013_V2 = "G9_ALLOW_NONSCIENTIFIC_D013_CUDA_V2_CORRUPTION_QUALIFICATION"


class ChildRefusal(RuntimeError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def assert_clean_process(modules=None, environment=None) -> None:
    modules = sys.modules if modules is None else modules
    environment = os.environ if environment is None else environment
    prohibited = [name for name in modules
                  if name in FORBIDDEN or name.split(".", 1)[0] in FORBIDDEN_ROOTS]
    if prohibited:
        raise ChildRefusal("prohibited module imported before payload: " + prohibited[0])
    if any(key.startswith("KAGGLE_") for key in environment):
        raise ChildRefusal("KAGGLE_ environment variable is present")


def validate_site_dirs(site_dirs):
    if type(site_dirs) is not list or not site_dirs:
        raise ChildRefusal("site-packages paths are missing")
    validated = []
    for value in site_dirs:
        if type(value) is not str or not Path(value).is_absolute() or not Path(value).is_dir():
            raise ChildRefusal("site-packages path is missing or invalid: " + str(value))
        if value not in validated:
            validated.append(value)
    return validated


def arm_permissions(fixture_mode: bool, durable_tmpdir=None) -> None:
    if not fixture_mode:
        os.environ[ALLOW_D013] = "1"
        os.environ[ALLOW_CORE] = "1"
        # NEW: arm the v2 D013 qualification path as well. This is a permission
        # for a non-scientific dry run of the owner-approved candidate; it is not
        # a release, and the v2 release gate still refuses unless the shipped
        # draft is canonical AND owner-approved.
        os.environ[ALLOW_D013_V2] = "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    # NEW: pin TMPDIR to the durable staged volume. The outer entry already sets
    # it, and child_environment() allowlists TMPDIR so it is inherited; this is
    # the explicit assertion so this module never depends on inheriting the
    # provider's default. It is set unconditionally in BOTH fixture and non-
    # fixture mode because it is a durability requirement, not a permission.
    target = durable_tmpdir if durable_tmpdir is not None else os.environ.get("TMPDIR")
    if not target or not Path(target).is_absolute():
        raise ChildRefusal("a durable absolute TMPDIR is required: " + repr(target))
    target_path = Path(target)
    try:
        target_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ChildRefusal("durable TMPDIR is not writable: " + str(exc))
    os.environ["TMPDIR"] = str(target_path)


def atomic_write(path: Path, data: bytes) -> None:
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify_stage(root: Path, index_path: Path, expected_index_sha: str):
    if not root.is_absolute() or not index_path.is_absolute():
        raise ChildRefusal("stage paths must be absolute")
    if not index_path.is_file() or index_path.is_symlink():
        raise ChildRefusal("stage index is missing")
    rows = json.loads(index_path.read_bytes())
    if type(rows) is not list or not rows:
        raise ChildRefusal("stage index is malformed")
    if sha(canonical(rows)) != expected_index_sha:
        raise ChildRefusal("stage index sha256 mismatch")
    for name, digest in rows:
        if type(name) is not str or type(digest) is not str:
            raise ChildRefusal("stage index entry is malformed")
        path = root / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
            raise ChildRefusal("staged file missing or escaping root: " + name)
        if sha(path.read_bytes()) != digest:
            raise ChildRefusal("staged file sha256 mismatch: " + name)
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("index", type=Path)
    parser.add_argument("index_sha256")
    parser.add_argument("out_base", type=Path)
    parser.add_argument("site_dirs")
    parser.add_argument("bundle_sha256")
    parser.add_argument("approval_sha256")
    parser.add_argument("fixture_mode", choices=("0", "1"))
    args = parser.parse_args(argv)
    root = args.root
    out_base = args.out_base
    fixture_mode = args.fixture_mode == "1"
    receipt = out_base / "wp7b_receipt.json"
    difference = out_base / "wp7b_difference.json"
    started = time.monotonic()
    last = None
    verified = False
    adapter = None
    try:
        verify_stage(root, args.index, args.index_sha256)
        verified = True
        try:
            site_dirs = json.loads(args.site_dirs)
        except Exception as exc:
            raise ChildRefusal("site-packages list is malformed") from exc
        validated = validate_site_dirs(site_dirs)
        for value in validated:
            if value not in sys.path:
                sys.path.append(value)
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        assert_clean_process()

        # Test-only controls exist solely in fixture-mode generated bundles.
        if fixture_mode:
            test_env = os.environ.get("WP7B_TEST_CHILD_ENV_JSON")
            if test_env:
                injected = json.loads(test_env)
                if type(injected) is not dict or any(type(k) is not str or type(v) is not str for k, v in injected.items()):
                    raise ChildRefusal("fixture child environment injection is malformed")
                os.environ.update(injected)
                assert_clean_process()
            delay = os.environ.get("WP7B_TEST_CHILD_SLEEP")
            if delay:
                started_file = os.environ.get("WP7B_TEST_CHILD_STARTED_FILE")
                if started_file:
                    Path(started_file).write_text("child-entered-fixture-run\n", encoding="ascii")
                time.sleep(float(delay))
        arm_permissions(fixture_mode,
                        durable_tmpdir=out_base / ("wp7b-tmp-" + args.bundle_sha256[:16]))

        import json as _json
        from research.g9.kaggle_wp7 import wp7_session as session
        from research.g9.kaggle_wp7b import wp7b_launcher as adapter
        forced_budget = os.environ.get("WP7B_TEST_FORCE_BUDGET") if fixture_mode else None
        if forced_budget:
            adapter.START = time.monotonic()
            raise RuntimeError("incomplete_budget:last_completed=" + forced_budget)
        pin = _json.loads((root / "research/g9/kaggle_wp7/wp7_environment_pin.json").read_text())
        environment_pin = adapter.environment_comparison_pin(pin)
        table = _json.loads((root / "research/g9/kaggle_wp7/wp7_reviewed_dependencies.json").read_text())
        cfg = _json.loads((root / "research/g9/kaggle_wp7b/runtime_config.json").read_text())
        instance = _json.loads((root / cfg["instance_path"]).read_text())
        prepared = _json.loads((root / cfg["prepared_record_path"]).read_text())
        seal_inputs = _json.loads((root / cfg["seal_inputs_path"]).read_text())
        session_seal_inputs = {**seal_inputs["input_hashes"],
            "production_identity_hash": seal_inputs["production_identity_hash"],
            "coordinates": seal_inputs["coordinates"]}
        probes = adapter.build_probes(pin)
        if fixture_mode:
            probe_json = os.environ.get("WP7B_TEST_PROBES_JSON")
            if probe_json:
                observations = _json.loads(probe_json)
                probes = {"platform_reported": lambda: observations["platform_reported"],
                          "image_reported": lambda: observations["image_reported"]}
        cfg["runtime_probes"] = probes
        steps, out, times = adapter.run_adapters(root, instance, prepared, seal_inputs, cfg,
                                                  fixture_only=fixture_mode)
        last = "runtime_adapters"
        receipt_value = session.run_session(root=root, dependency_table=table["dependencies"],
            environment_pin=environment_pin, probes=probes, instance=instance,
            output_dir=out, steps=steps, sealed_reference_path=cfg["seal_path"],
            seal_inputs=session_seal_inputs)
        receipt_value = session.validate_receipt(receipt_value)
        outer = {"schema": "decisions_os/wp7b_outer_receipt/v1",
            "status": "pending_image_metadata_audit", "session_receipt": receipt_value,
            "step_wall_seconds": times, "approval_record_sha256": args.approval_sha256,
            "bundle_sha256": args.bundle_sha256,
            "post_run_only_image_fields": list(adapter.POST_RUN_ONLY_IMAGE_FIELDS),
            "post_run_only_image_expected": adapter.post_run_image_expectations(pin),
            "post_run_audited_identity_fields": ["kaggle_saved_version_build_platform_reported",
                "kaggle_kernel_version_platform_reported"]}
        outer["content_sha256"] = sha(canonical(outer))
        atomic_write(receipt, canonical(outer) + b"\n")
        return 0
    except Exception as exc:
        msg = str(exc)
        if verified and adapter is not None and "incomplete_budget" in msg:
            row = adapter.budget_receipt_for_error(
                exc, adapter.time.monotonic() - getattr(adapter, "START", started))
            if row is not None:
                atomic_write(receipt, (json.dumps(row, sort_keys=True) + "\n").encode())
                return 0
        last_completed = msg.split("last_completed=", 1)[1] if "last_completed=" in msg else last
        row = {"status": "refused", "difference": msg,
               "error_type": type(exc).__name__,
               "last_completed_step": last_completed, "scientific_outputs": []}
        atomic_write(difference, (json.dumps(row, sort_keys=True) + "\n").encode())
        print("CHILD REFUSED: " + msg, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
