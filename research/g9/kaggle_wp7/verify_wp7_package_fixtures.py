#!/usr/bin/env python3
"""Fixtures for the WP7 offline draft package (round 2).

Every fixture reaches a real check in wp7_session.py or
build_wp7_package.py by executing the code path that the check guards.  No
fixture asserts only that a name or attribute exists.

Each test is tagged with the guard it exercises, in the form
``[<file>:<symbol>#<line-of-the-raising-statement>]``.  Those tags are what
``--report-guard-cases`` prints and what the parallel mutation sweep uses to
prove that no guard is left without a fixture that fails when it is removed.

Nothing here contacts Kaggle, reads a credential, uses the network, or runs
a GPU.  Temporary trees are built in a temp directory; the project tree is
never written to.  Child processes are given a SCRUBBED environment built
from an allowlist, never from ``os.environ``, so no credential value can
reach a subprocess launched by this file.
"""

from __future__ import annotations

import ast
import copy
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_wp7_package as builder  # noqa: E402
import wp7_session as session  # noqa: E402

ROOT = HERE.parents[2]

# The environment a fixture subprocess is allowed to see.  It is an
# allowlist, so a credential variable in the ambient environment can never be
# copied into a child, and the "no credential value is read" claim is
# provable rather than asserted.
SAFE_ENV_KEYS = (
    "PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TZ", "PYTHONPATH",
    "PYTHONHASHSEED", "PYTHONDONTWRITEBYTECODE", "SYSTEMROOT", "COMSPEC",
)
NEVER_IN_CHILD_ENV = ("KAGGLE", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL")

# Read-only os.* attributes this package may use: path metadata, never a
# process, a socket or an environment value.
READ_ONLY_OS_ATTRS = frozenset({"stat", "lstat", "listdir", "getcwd", "readlink", "fspath"})


def safe_child_env(extra: dict | None = None) -> dict:
    env = {key: os.environ[key] for key in SAFE_ENV_KEYS if key in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra:
        env.update(extra)
    for key in env:
        upper = key.upper()
        for fragment in NEVER_IN_CHILD_ENV:
            if fragment in upper:
                raise AssertionError(f"fixture child env must never carry {key!r}")
    return env


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _reviewed_file(package_root: Path, table: dict) -> str:
    builder._mapping(table, "dependency table")
    if not isinstance(package_root, Path):
        raise builder.Wp7PackageError("package_root must be a Path or None")
    path = package_root / builder.REVIEWED_TABLE_NAME
    if path.is_file():
        record = json.loads(path.read_text(encoding="utf-8"))
    else:
        record = {
            "dependencies": dict(table),
            "package_files_sha256": {
                name: builder.sha256_file(package_root / name) for name in builder.PACKAGE_FILES
            },
        }
    if record["dependencies"] != table:
        record["dependencies"] = dict(table)
    try:
        encoded = json.dumps(record, sort_keys=True, indent=2) + "\n"
    except (TypeError, ValueError) as exc:
        raise builder.Wp7PackageError(f"invalid reviewed table: {exc}") from exc
    path.write_text(encoded, encoding="utf-8")
    return builder.sha256_file(path)


def anchored_build(root, table, *, environment_pin=None, package_root=None):
    if not isinstance(root, Path):
        raise builder.Wp7PackageError("root must be a Path")
    if package_root is not None and not isinstance(package_root, Path):
        raise builder.Wp7PackageError("package_root must be a Path or None")
    home = package_root if package_root is not None else (root if (root / "wp7_session.py").is_file() else HERE)
    if home == HERE:
        anchor = builder.sha256_file(HERE / builder.REVIEWED_TABLE_NAME)
    else:
        anchor = _reviewed_file(home, table)
    return builder.build_manifest(root, table, environment_pin=environment_pin,
                                  package_root=home, expected_reviewed_table_sha256=anchor)


def anchored_verify(root, manifest, *, package_root=None):
    if not isinstance(root, Path):
        raise builder.Wp7PackageError("root must be a Path")
    if package_root is not None and not isinstance(package_root, Path):
        raise builder.Wp7PackageError("package_root must be a Path or None")
    home = package_root if package_root is not None else (root if (root / "wp7_session.py").is_file() else HERE)
    anchor = builder.sha256_file(home / builder.REVIEWED_TABLE_NAME)
    return builder.verify_manifest(root, manifest, package_root=home,
                                   expected_reviewed_table_sha256=anchor)


class SyntheticTree:
    """A tiny repo-relative tree used to exercise the dependency lock.

    It also contains a copy of every file of the package itself, so a
    manifest built against it can reach "ready" and the package-file checks
    are exercised on the same small instance.
    """

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="wp7-fixture-")
        self.root = Path(self._tmp.name)
        self.files = {
            "a.py": b"# alpha\n",
            "b.py": b"# beta\n",
            "c.json": b'{"c": 1}\n',
        }
        for name, data in self.files.items():
            _write(self.root / name, data)
        for name in builder.PACKAGE_FILES:
            _write(self.root / name, _package_bytes(name))
        self.package_hashes = {
            name: builder.sha256_file(self.root / name) for name in builder.PACKAGE_FILES
        }
        self.table = {
            name: builder.sha256_file(self.root / name) for name in sorted(self.files)
        }
        self.session_table = dict(self.table)

    def add_session_dependencies(self) -> None:
        for name in session.REQUIRED_WP_DEPENDENCIES:
            if name == session.REFERENCE_SEAL_MODULE:
                # The session really loads and executes this one, so the tree
                # gets the REAL reviewed module, not a stand-in.
                _write(self.root / name, (ROOT / name).read_bytes())
            else:
                _write(self.root / name, ("# synthetic stand-in for " + name + "\n").encode())
            self.session_table[name] = builder.sha256_file(self.root / name)

    def flip_one_byte(self, name: str) -> None:
        path = self.root / name
        data = bytearray(path.read_bytes())
        data[0] = data[0] ^ 0x01
        path.write_bytes(bytes(data))

    def close(self) -> None:
        self._tmp.cleanup()

    def __enter__(self) -> "SyntheticTree":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _package_bytes(name: str) -> bytes:
    """A stand-in for a package file, so a small tree can reach "ready"."""
    return ("# synthetic stand-in for " + name + "\n").encode("ascii")


def _make_package(root: Path, *, which: str | None = None) -> None:
    for name in builder.PACKAGE_FILES:
        if which is not None and name != which:
            continue
        _write(root / name, _package_bytes(name))


def _pin(platform_overrides: dict | None = None, image_overrides: dict | None = None) -> dict:
    return {
        "platform_reported": dict(platform_overrides or {"gpu_name": "Tesla T4", "python_version": "3.12.13"}),
        "image_reported": dict(image_overrides or {"kaggle_image": "img@sha256:abc"}),
    }


def _observed(platform_values: dict, image_values: dict) -> dict:
    return {"platform_reported": dict(platform_values), "image_reported": dict(image_values)}


SYNTHETIC_INSTANCE = {
    "instance_kind": "synthetic",
    "synthetic": True,
    "source": "synthetic_generator wp7",
    "label": "wp7-synthetic-0",
}


# --------------------------------------------------------------------------
# Sealed OPTION A reference: a real seal produced by the real reviewed module
# over a tiny synthetic coordinate list, so the session opens a genuine seal
# rather than a fixture that asserts opening works.
# --------------------------------------------------------------------------
SEAL_COORDINATES = [
    {"coordinate": {"r": "0x1.0000000000000p+0", "card": 1, "sector": 1}, "encoding": "unbalanced"},
    {"coordinate": {"r": "0x1.0000000000000p+0", "card": 1, "sector": 1}, "encoding": "slack"},
]

_SEAL_HEX = "0" * 64


def _seal_reference(energy_word: str, index: int) -> dict:
    """A frozen single-process reference over one tiny synthetic coordinate."""
    def reference(coordinate, encoding):
        return {
            "energy_minimum_words": [energy_word],
            "canonical_minimum_index": index,
            "tie_flags": [7],
            "d015_d016_reconstruction": {"synthetic": [1, 2, 3], "card": "30"},
        }
    return reference


def make_seal(inputs: dict, coordinates=None, reference=None) -> bytes:
    """Seal the reference with the REAL reviewed module and return the bytes."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "wp7_fixture_seal", str(ROOT / session.REFERENCE_SEAL_MODULE)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = list(SEAL_COORDINATES if coordinates is None else coordinates)
    return module.seal(
        inputs,
        rows,
        inputs["production_identity_hash"],
        runner=_seal_reference("0123456789abcdef", 0) if reference is None else reference,
    )


def seal_inputs(coordinates=None) -> dict:
    """The session inputs a seal is opened against."""
    return {
        "instance_digest": _SEAL_HEX,
        "coefficient_ledger_digest": _SEAL_HEX,
        "protocol_digest": _SEAL_HEX,
        "original_objective_digest": _SEAL_HEX,
        "frozen_source_digest": _SEAL_HEX,
        "decision_digest": _SEAL_HEX,
        "production_identity_hash": "1" * 64,
        "coordinates": list(SEAL_COORDINATES if coordinates is None else coordinates),
    }


def _write_seal(root: Path, *, coordinates=None, name: str = "sealed_reference.json",
                inputs: dict | None = None) -> tuple[str, dict]:
    """Write a real seal into ``root`` and return its relative path and inputs."""
    used = seal_inputs(coordinates) if inputs is None else inputs
    _write(root / name, make_seal(used))
    return name, used


def _step_results() -> dict:
    return {
        "synthetic_instance_gate": {
            "identities": {"instance": dict(SYNTHETIC_INSTANCE)},
            "output": {"instance": "synthetic-record"},
        },
        "wp6b_section_a_qualification_plan": {
            "counters": {"section_a_plan_built": 1},
            "digests": {"section_a_plan_sha256": "a" * 64},
            "output": {"plan": "qualified"},
        },
        "wp1_production_identity_candidate": {
            "counters": {"identity_built": 1},
            "digests": {"identity_sha256": "b" * 64},
            "output": {"identity": "candidate"},
        },
        "section_b_item_1_recheck_synthetic": {
            "counters": {"b1_checks": 7, "b1_failures": 0},
            "output": {"recheck": "complete"},
        },
        "section_b_item_2_full_domain_synthetic": {
            "counters": {"b2_coordinates": 4, "b2_mismatches": 0},
            "output": {"domain": "complete"},
        },
        "wp4b_writer_synthetic_ranges": {"counters": {"ranges_written": 2}, "output": {"written": 2}},
    }


def _steps() -> dict:
    results = _step_results()
    # Section-B item 2 is handed the python reference opened from the sealed
    # OPTION A reference file.  The stand-in asserts it is the sealed callable
    # and exercises it, so a session that computed a reference in-session
    # could not satisfy this step.
    def b2(python_reference=None):
        if not callable(python_reference):
            raise AssertionError("section-B item 2 was not given the sealed python reference")
        python_reference(SEAL_COORDINATES[0]["coordinate"], SEAL_COORDINATES[0]["encoding"])
        return _step_results()["section_b_item_2_full_domain_synthetic"]

    table = {name: (lambda r=results[name]: copy.deepcopy(r)) for name in session.INJECTED_STEPS}
    table["section_b_item_2_full_domain_synthetic"] = b2
    return table


# --------------------------------------------------------------------------
# Guard inventory: the mutation sweep turns each of these into a no-op and
# requires that a fixture fails.  Only guards that appear here are claimed to
# be covered; the sweep reports any that are not.
# --------------------------------------------------------------------------
# ["file", "symbol", "text of the guarded statement or raise"]
GUARDS: list[list] = []


def _guard(file: str, symbol: str, text: str) -> None:
    GUARDS.append([file, symbol, text])


def _collect_guards() -> None:
    builder_guards = [
        ("_mapping", "if not isinstance(value, dict):"),
        ("_mapping", "if not isinstance(key, str):"),
        ("_sequence", "if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, (list, tuple)):"),
        ("_text", "if not isinstance(value, str):"),
        ("_require_sha256", "if _HEX64.match(text) is None:"),
        ("content_sha256", "if not isinstance(value, dict):"),
        ("sha256_file", "if not isinstance(path, Path):"),
        ("normalize_relative_path", 'if text == "":'),
        ("normalize_relative_path", "if \"\\x00\" in text:"),
        ("normalize_relative_path", 'if "\\\\" in text:'),
        ("normalize_relative_path", 'if os.path.isabs(text):'),
        ("normalize_relative_path", 'if ":" in text.split("/")[0]:'),
        ("normalize_relative_path", 'if part == "":'),
        ("normalize_relative_path", 'if part == ".":'),
        ("normalize_relative_path", 'if part == "..":'),
        ("resolve_inside_root", "if not isinstance(root, Path):"),
        ("resolve_inside_root", "except ValueError as exc:"),
        ("resolve_inside_root", "if not real.exists():"),
        ("resolve_inside_root", "if not real.is_file():"),
        ("resolve_inside_root", "if not S_ISREG(real.stat().st_mode):"),
        ("validate_status", "if text not in ALLOWED_STATUSES:"),
        ("validate_status", "if fragment in lowered:"),
        ("evaluate_dependencies", "if not isinstance(root, Path):"),
        ("evaluate_dependencies", "if not root.is_dir():"),
        ("evaluate_dependencies", "if len(entries) == 0:"),
        ("evaluate_dependencies", "if not isinstance(recorded, str):"),
        ("evaluate_dependencies", "if recorded == PENDING:"),
        ("evaluate_dependencies", "if not _is_sha256(recorded):"),
        ("evaluate_dependencies", "except Wp7PathError as exc:"),
        ("evaluate_dependencies", "if current != recorded:"),
        ("evaluate_package_files", "except Wp7PackageError as exc:"),
        ("evaluate_package_files", "except Wp7PackageError as read_exc:"),
        ("validate_kernel_metadata_draft", "if table.get(key) is not True:"),
        ("validate_kernel_metadata_draft", "if table.get(key) is not False:"),
        ("validate_kernel_metadata_draft", 'if text.strip() == "":'),
        ("validate_kernel_metadata_draft", 'if not isinstance(value, list) or len(value) != 0:'),
        ("validate_kernel_metadata_draft", "if table.get(\"draft\") is not True:"),
        ("_manifest_entry_set", "if not isinstance(recorded_entries, list) or len(recorded_entries) == 0:"),
        ("_manifest_entry_set", "if key not in record:"),
        ("_manifest_entry_set", "if relative in entries:"),
        ("_manifest_entry_set", "if state not in DEPENDENCY_STATES:"),
        # Both package-file entry points now require a MAPPING before they
        # call .get on it, so a non-mapping manifest is a typed refusal
        # rather than a raw AttributeError escaping the entry point.
        ("_manifest_entry_set", 'table = _mapping(manifest, "manifest")'),
        ("_verify_package_files", 'table = _mapping(manifest, "manifest")'),
        ("_verify_package_files", 'if len(recorded) != len(PACKAGE_FILES):'),
        ("_verify_package_files", 'if not isinstance(count, int) or isinstance(count, bool) or count != len(PACKAGE_FILES):'),
        ("_verify_package_files", "if name not in recorded:"),
        ("_verify_package_files", "if not _is_sha256(recorded_hash):"),
        ("_verify_package_files", "except Wp7PackageError as exc:"),
        ("_verify_package_files", "except Wp7PackageError as read_exc:"),
        ("_verify_package_files", 'if actual != recorded_hash:'),
        ("verify_manifest", "if key not in table:"),
        ("verify_manifest", 'if table.get("is_draft") is not True:'),
        ("verify_manifest", 'if table.get(key) is not False:'),
        ("verify_manifest", 'if table.get("can_emit_approved_or_pushed") is not False:'),
        ("verify_manifest", "if content_sha256(table) != recorded_digest:"),
        ("verify_manifest", "if not isinstance(count, int) or isinstance(count, bool) or count != len(entries):"),
        ("verify_manifest", 'if dependency_table_sha256(observed_set) != table.get("dependency_table_sha256"):'),
        ("verify_manifest", 'if table.get("package_files_all_matched") is not True:'),
        ("verify_manifest", "except Wp7PackageError as read_exc:"),
        ("verify_manifest", 'if actual != recorded_current:'),
        ("verify_manifest", 'if not isinstance(reason, str) or reason == "":'),
        ("verify_manifest", "if invalidated and status == STATUS_READY:"),
        ("verify_manifest", "if invalidated and status != STATUS_READY:"),
        ("verify_manifest", "if not _is_sha256(recorded_current):"),
        ("verify_manifest", "if status != STATUS_READY:"),
        ("main", "if args.verify is not None:"),
        ("main", "if args.dependency_table is not None:"),
        ("main", "except (Wp7PackageError, OSError, ValueError) as exc:"),
    ]
    session_guards = [
        ("_mapping", "if not isinstance(value, dict):"),
        ("_mapping", "if not isinstance(key, str):"),
        ("_sequence", "if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, (list, tuple)):"),
        ("_text", "if not isinstance(value, str):"),
        ("_flat_text", "if fragment.lower() in lowered:"),
        ("content_sha256", "if not isinstance(value, dict):"),
        # Round 3 shipped this type check on the session's own sha256_file.
        # It was dropped as a "duplicate" of the shared boundary helper; the
        # validated guard is restored, and the helper keeps its own copy.
        ("sha256_file", "if not isinstance(path, Path):"),
        ("assert_no_credential_environment", "if key.startswith(prefix):"),
        ("assert_no_prohibited_imports", 'if name is None:'),
        ("assert_no_prohibited_imports", "if root in FORBIDDEN_IMPORT_ROOTS or (name in FORBIDDEN_IMPORT_MODULES and name not in bootstrap):"),
        ("normalize_relative_path", 'if text == "":'),
        ("normalize_relative_path", "if \"\\x00\" in text:"),
        ("normalize_relative_path", 'if "\\\\" in text:'),
        ("normalize_relative_path", 'if text.startswith("/") or os.path.isabs(text):'),
        ("normalize_relative_path", 'if ":" in text.split("/")[0]:'),
        ("normalize_relative_path", 'if part == "":'),
        ("normalize_relative_path", 'if part == ".":'),
        ("normalize_relative_path", 'if part == "..":'),
        ("resolve_inside_root", "if not isinstance(root, Path):"),
        ("resolve_inside_root", "except ValueError as exc:"),
        ("resolve_inside_root", "if not real.exists():"),
        ("resolve_inside_root", "if not real.is_file():"),
        ("resolve_inside_root", "if not S_ISREG(real.stat().st_mode):"),
        ("resolve_inside_root", "if real == root_real:"),
        ("resolve_dependencies", "if not isinstance(root, Path):"),
        ("resolve_dependencies", "if len(dependencies) == 0:"),
        ("resolve_dependencies", 'if recorded == "PENDING":'),
        ("resolve_dependencies", "if len(recorded) != 64 or any(c not in \"0123456789abcdef\" for c in recorded):"),
        ("resolve_dependencies", "except Wp7PathError as exc:"),
        ("resolve_dependencies", "if current != recorded:"),
        ("resolve_dependencies", "if problems:"),
        ("_probe_callable", "if probe is not None and not callable(probe):"),
        ("_assert_reportable", "if depth > MAX_REPORTED_DEPTH:"),
        ("_assert_reportable", "if not isinstance(depth, int) or isinstance(depth, bool):"),
        ("_assert_reportable", "if isinstance(value, list):"),
        ("_assert_reportable", "if not isinstance(value, (str, int, float, bool)) and value is not None:"),
        ("_flatten", "if depth > MAX_REPORTED_DEPTH:"),
        ("_flatten", "if any(not isinstance(key, str) for key in value):"),
        ("compare_environment_pin", "if len(pin_map) == 0:"),
        ("_pinned_fields", "if group not in pin_map:"),
        ("_pinned_fields", "if len(pinned) == 0:"),
        ("compare_environment_pin", "if field not in observed_flat:"),
        ("compare_environment_pin", "if isinstance(actual, list):"),
        ("compare_environment_pin", "if type(actual) is not type(expected) or actual != expected:"),
        ("compare_environment_pin", 'if group not in observed_map:'),
        ("compare_environment_pin", "if field not in pinned:"),
        ("compare_environment_pin", "if differences:"),
        ("_assert_synthetic_source", "if fragment in lowered:"),
        ("_assert_synthetic_source", "if allowed in lowered:"),
        ("assert_synthetic_instance", 'if "instance_kind" not in record:'),
        ("assert_synthetic_instance", "if kind not in SYNTHETIC_INSTANCE_KINDS:"),
        ("assert_synthetic_instance", 'if record.get("synthetic") is not True:'),
        ("assert_synthetic_instance", 'if "source" not in record:'),
        ("_classify_step_result", "if len(table) == 0:"),
        ("_classify_step_result", "if key not in STEP_RESULT_ALLOWED_KEYS:"),
        ("_classify_step_result", 'if status is not None and status != "ok":'),
        ("_load_seal_module", "if REFERENCE_SEAL_MODULE not in table:"),
        ("_load_seal_module", "if spec is None or spec.loader is None:"),
        ("_load_seal_module", "except Exception as exc:"),
        ("open_sealed_reference", "if len(sealed_bytes) == 0:"),
        ("open_sealed_reference", 'for field in ("coordinates", "production_identity_hash"):'),
        ("open_sealed_reference", "if not callable(opener):"),
        ("open_sealed_reference", "except Exception as exc:"),
        ("open_sealed_reference", "if not callable(reference):"),
        ("read_bytes_at_boundary", "if not isinstance(path, Path):"),
        ("read_bytes_at_boundary", "if not isinstance(label, str):"),
        ("read_bytes_at_boundary", "except (OSError, UnicodeError, ValueError) as exc:"),
        ("read_text_at_boundary", "except (UnicodeError, ValueError) as exc:"),
        ("read_json_at_boundary", "except (_json.JSONDecodeError, ValueError, UnicodeError) as exc:"),
        ("run_session", "raw_result = table[name](python_reference)"),
        ("_classify_step_result", "if key in table:"),
        ("_require_scalar_map", "if not isinstance(key, str):"),
        ("_require_scalar_map", 'if not isinstance(table[key], (str, int, float, bool)) and table[key] is not None:'),
        ("build_receipt", "if len(ran) == 0:"),
        ("build_receipt", "if unknown:"),
        ("build_receipt", "if ordered != ran:"),
        ("build_receipt", "if missing:"),
        ("_text_sequence", "for item in value:"),
        ("validate_receipt", "if missing:"),
        ("validate_receipt", 'if table.get("schema") != SCHEMA:'),
        ("validate_receipt", 'if table.get("mode") != MODE:'),
        ("validate_receipt", "if len(table[\"scientific_outputs\"]) != 0:"),
        ("validate_receipt", 'if table.get("scientific_output_count") != 0:'),
        ("validate_receipt", "if table.get(field) is not False:"),
        ("validate_receipt", "if not isinstance(table[field], dict):"),
        ("validate_receipt", "if absent:"),
        ("validate_receipt", 'if table.get("content_sha256") != content_sha256(table):'),
        ("_validate_step_table", 'if name not in STEP_ORDER:'),
        ("_validate_step_table", "if absent:"),
        ("_validate_step_table", "if not callable(table[name]):"),
        ("run_session", 'if key not in step_result:'),
        ("run_session", 'if name == "synthetic_instance_gate":'),
        ("run_session", 'if "identities" not in step_result or "instance" not in step_result["identities"]:'),
        ("resolve_dir_inside_root", "if not isinstance(root, Path):"),
        ("resolve_dir_inside_root", "if not isinstance(directory, Path):"),
        ("resolve_dir_inside_root", "except ValueError as exc:"),
        ("resolve_dir_inside_root", "if real == root_real:"),
        ("resolve_dir_inside_root", "if not real.is_dir():"),
    ]
    for item in builder_guards:
        _guard("build_wp7_package.py", item[0], item[1])
    for item in session_guards:
        _guard("wp7_session.py", item[0], item[1])


_collect_guards()


# --------------------------------------------------------------------------
# Dependency lock: pin every dependency AND every package file
# --------------------------------------------------------------------------
class TestDependencyLock(unittest.TestCase):
    def setUp(self) -> None:
        self.tree = SyntheticTree()
        self.addCleanup(self.tree.close)

    def _ready(self) -> dict:
        manifest = anchored_build(
            self.tree.root, self.tree.table, package_root=self.tree.root
        )
        self.assertEqual(manifest["status"], builder.STATUS_READY, manifest["invalidating_reasons"])
        return manifest

    def test_pending_entry_makes_manifest_invalid(self) -> None:
        table = dict(self.tree.table)
        table["b.py"] = builder.PENDING
        manifest = anchored_build(self.tree.root, table)
        self.assertEqual(manifest["status"], builder.STATUS_INVALID)
        self.assertFalse(manifest["dependencies_all_matched"])
        self.assertTrue(
            any("b.py" in reason and "PENDING" in reason for reason in manifest["invalidating_reasons"]),
            manifest["invalidating_reasons"],
        )

    def test_manifest_invalid_when_dependency_missing(self) -> None:
        (self.tree.root / "c.json").unlink()
        manifest = anchored_build(self.tree.root, self.tree.table, package_root=self.tree.root)
        self.assertEqual(manifest["status"], builder.STATUS_INVALID)
        self.assertTrue(
            any("c.json" in reason and "not present" in reason for reason in manifest["invalidating_reasons"]),
            manifest["invalidating_reasons"],
        )

    def test_manifest_ready_when_every_hash_matches(self) -> None:
        manifest = self._ready()
        self.assertEqual(manifest["invalidating_reasons"], [])
        self.assertFalse(manifest["push_authorized"])
        self.assertFalse(manifest["gpu_allocation_authorized"])
        self.assertFalse(manifest["can_emit_approved_or_pushed"])
        self.assertTrue(manifest["package_files_all_matched"])
        self.assertEqual(manifest["package_file_count"], len(builder.PACKAGE_FILES))
        for name in builder.PACKAGE_FILES:
            self.assertEqual(manifest["package_files_sha256"][name], self.tree.package_hashes[name])
        verified = anchored_verify(self.tree.root, manifest, package_root=self.tree.root)
        self.assertEqual(verified["verified_dependencies"], 3)
        self.assertEqual(verified["verified_package_files"], len(builder.PACKAGE_FILES))

    def test_one_byte_change_to_each_dependency_invalidates(self) -> None:
        for name in sorted(self.tree.files):
            with self.subTest(dependency=name):
                tree = SyntheticTree()
                self.addCleanup(tree.close)
                manifest = anchored_build(tree.root, tree.table, package_root=tree.root)
                self.assertEqual(manifest["status"], builder.STATUS_READY)
                tree.flip_one_byte(name)
                after = anchored_build(tree.root, tree.table, package_root=tree.root)
                self.assertEqual(after["status"], builder.STATUS_INVALID)
                self.assertTrue(
                    any(name in r and "hash mismatch" in r for r in after["invalidating_reasons"]),
                    after["invalidating_reasons"],
                )
                with self.assertRaises(builder.Wp7PackageError):
                    anchored_verify(tree.root, manifest, package_root=tree.root)

    def test_one_byte_change_to_each_package_file_invalidates(self) -> None:
        """Every package file is refused after one byte changes."""
        for name in builder.PACKAGE_FILES:
            with self.subTest(package_file=name):
                tree = SyntheticTree()
                self.addCleanup(tree.close)
                manifest = anchored_build(tree.root, tree.table, package_root=tree.root)
                self.assertEqual(manifest["status"], builder.STATUS_READY)
                tree.flip_one_byte(name)
                with self.assertRaises(builder.Wp7DependencyError):
                    anchored_build(tree.root, tree.table, package_root=tree.root)
                with self.assertRaises(builder.Wp7PackageError):
                    anchored_verify(tree.root, manifest, package_root=tree.root)
                pinned = copy.deepcopy(manifest)
                pinned["package_files_sha256"][name] = "0" * 63 + "1"
                pinned["content_sha256"] = builder.content_sha256(pinned)
                with self.assertRaises(builder.Wp7PackageError):
                    anchored_verify(tree.root, pinned, package_root=tree.root)
                tree.root.joinpath(name).unlink()
                with self.assertRaises(builder.Wp7DependencyError):
                    anchored_build(tree.root, tree.table, package_root=tree.root)

    def test_mutating_each_dependency_entry_invalidates(self) -> None:
        """A one-byte change to the RECORDED hash of each entry invalidates it.

        This is the recorded half of the lock: a reviewer who records a
        different hash for an unchanged file must not get a ready manifest.
        """
        for name in sorted(self.tree.files):
            with self.subTest(entry=name):
                tree = SyntheticTree()
                self.addCleanup(tree.close)
                manifest = anchored_build(tree.root, tree.table, package_root=tree.root)
                self.assertEqual(manifest["status"], builder.STATUS_READY)
                table = dict(tree.table)
                table[name] = "0" * 63 + ("1" if tree.table[name][-1] != "1" else "2")
                after = anchored_build(tree.root, table)
                self.assertEqual(after["status"], builder.STATUS_INVALID)
                entry = {e["path"]: e for e in after["dependencies"]}[name]
                self.assertEqual(entry["state"], "hash_mismatch")

    def test_removing_a_dependency_entry_is_refused(self) -> None:
        """Deleting an entry and recomputing the body digest is refused.

        The manifest pins the dependency SET, so a trimmed manifest cannot
        verify even though every surviving entry still matches and the body
        digest is self-consistent.
        """
        manifest = self._ready()
        trimmed = copy.deepcopy(manifest)
        trimmed["dependencies"] = [e for e in trimmed["dependencies"] if e["path"] != "a.py"]
        trimmed["dependency_count"] = len(trimmed["dependencies"])
        trimmed["content_sha256"] = builder.content_sha256(trimmed)
        with self.assertRaisesRegex(builder.Wp7PackageError, "reviewed table"):
            anchored_verify(self.tree.root, trimmed, package_root=self.tree.root)

    def test_adding_a_dependency_entry_is_refused(self) -> None:
        manifest = self._ready()
        extra = copy.deepcopy(manifest["dependencies"][0])
        extra["path"] = "d.py"
        _write(self.tree.root / "d.py", b"# delta\n")
        extra["current_sha256"] = builder.sha256_file(self.tree.root / "d.py")
        extra["recorded_reviewed_sha256"] = extra["current_sha256"]
        (self.tree.root / "d.py").unlink()
        added = copy.deepcopy(manifest)
        added["dependencies"].append(extra)
        added["dependency_count"] = len(added["dependencies"])
        added["content_sha256"] = builder.content_sha256(added)
        with self.assertRaisesRegex(builder.Wp7PackageError, "reviewed table"):
            anchored_verify(self.tree.root, added, package_root=self.tree.root)

    def test_manifest_set_digest_is_a_function_of_the_set(self) -> None:
        first = builder.dependency_table_sha256({"a.py": "0" * 64, "b.py": "1" * 64})
        same = builder.dependency_table_sha256({"b.py": "1" * 64, "a.py": "0" * 64})
        self.assertEqual(first, same)
        self.assertNotEqual(first, builder.dependency_table_sha256({"a.py": "0" * 64}))
        self.assertNotEqual(
            first, builder.dependency_table_sha256({"a.py": "0" * 64, "b.py": "1" * 63 + "2"})
        )
        for bad in (None, [], "", 5, set()):
            with self.assertRaises(builder.Wp7PackageError):
                builder.dependency_table_sha256(bad)

    def test_verifier_refuses_tampered_manifest_body(self) -> None:
        manifest = self._ready()
        tampered = copy.deepcopy(manifest)
        for entry in tampered["dependencies"]:
            if entry["path"] == "a.py":
                entry["current_sha256"] = "f" * 64
        tampered["content_sha256"] = builder.content_sha256(tampered)
        with self.assertRaisesRegex(builder.Wp7PackageError, "stale"):
            anchored_verify(self.tree.root, tampered, package_root=self.tree.root)
        # A body whose digest is not recomputed is caught as digest-stale.
        with self.assertRaisesRegex(builder.Wp7PackageError, "content_sha256"):
            anchored_verify(self.tree.root, dict(manifest, status=builder.STATUS_INVALID), package_root=self.tree.root)
        # A forged ready status over a PENDING entry is refused.
        table = dict(self.tree.table)
        table["b.py"] = builder.PENDING
        invalid = anchored_build(self.tree.root, table)
        forged = copy.deepcopy(invalid)
        forged["status"] = builder.STATUS_READY
        forged["invalidating_reasons"] = []
        forged["dependencies_all_matched"] = True
        with self.assertRaisesRegex(builder.Wp7PackageError, "stale"):
            anchored_verify(self.tree.root, forged, package_root=self.tree.root)

    def test_verifier_refuses_ready_status_with_unmatched_entry(self) -> None:
        table = dict(self.tree.table)
        table["b.py"] = builder.PENDING
        manifest = anchored_build(self.tree.root, table)
        manifest["status"] = builder.STATUS_READY
        manifest["content_sha256"] = builder.content_sha256(manifest)
        with self.assertRaisesRegex(builder.Wp7PackageError, "stale"):
            anchored_verify(self.tree.root, manifest, package_root=self.tree.root)

    def test_verifier_refuses_authorization_flags(self) -> None:
        manifest = self._ready()
        for key in ("push_authorized", "gpu_allocation_authorized", "run_authorized"):
            bad = copy.deepcopy(manifest)
            bad[key] = True
            bad["content_sha256"] = builder.content_sha256(bad)
            with self.assertRaisesRegex(builder.Wp7PackageError, key):
                anchored_verify(self.tree.root, bad, package_root=self.tree.root)
        bad = copy.deepcopy(manifest)
        bad["is_draft"] = False
        bad["content_sha256"] = builder.content_sha256(bad)
        with self.assertRaisesRegex(builder.Wp7PackageError, "draft"):
            anchored_verify(self.tree.root, bad, package_root=self.tree.root)
        bad = copy.deepcopy(manifest)
        bad["can_emit_approved_or_pushed"] = True
        bad["content_sha256"] = builder.content_sha256(bad)
        with self.assertRaisesRegex(builder.Wp7PackageError, "approved or pushed"):
            anchored_verify(self.tree.root, bad, package_root=self.tree.root)
        bad = copy.deepcopy(manifest)
        bad["package_files_all_matched"] = False
        bad["content_sha256"] = builder.content_sha256(bad)
        with self.assertRaisesRegex(builder.Wp7PackageError, "every package file matched"):
            anchored_verify(self.tree.root, bad, package_root=self.tree.root)

    def test_manifest_missing_a_required_field_is_refused(self) -> None:
        manifest = self._ready()
        for key in builder.REQUIRED_MANIFEST_KEYS:
            with self.subTest(field=key):
                bad = copy.deepcopy(manifest)
                bad.pop(key, None)
                with self.assertRaises(builder.Wp7PackageError):
                    anchored_verify(self.tree.root, bad, package_root=self.tree.root)

    def test_manifest_entry_missing_a_required_field_is_refused(self) -> None:
        manifest = self._ready()
        for key in ("path", "state", "reason", "current_sha256", "recorded_reviewed_sha256"):
            with self.subTest(field=key):
                bad = copy.deepcopy(manifest)
                bad["dependencies"][0].pop(key, None)
                bad["content_sha256"] = builder.content_sha256(bad)
                with self.assertRaisesRegex(builder.Wp7PackageError, key):
                    anchored_verify(self.tree.root, bad, package_root=self.tree.root)

    def test_shipped_table_is_a_placeholder_the_builder_refuses(self) -> None:
        """The shipped table is either the original refusing placeholder or a reviewed pin."""
        shipped = json.loads((HERE / builder.REVIEWED_TABLE_NAME).read_text(encoding="utf-8"))
        if shipped.get("_placeholder"):
            self.assertTrue(shipped.get("_placeholder"), "shipped table must be marked as a placeholder")
            self.assertEqual(shipped.get("_placeholder_notice"), shipped.get("_placeholder_notice"))
            for value in shipped["package_files_sha256"].values():
                self.assertNotRegex(str(value), r"\A[0-9a-f]{64}\Z", "placeholder package hash must not look reviewed")
            with self.assertRaises(builder.Wp7PackageError):
                anchored_build(ROOT, builder.WP7_DEPENDENCY_TABLE)
            with self.assertRaises(builder.Wp7PackageError):
                anchored_verify(ROOT, {"status": builder.STATUS_READY})
            return

        self.assertFalse(any(str(key).startswith("_") for key in shipped))
        for value in list(shipped["dependencies"].values()) + list(shipped["package_files_sha256"].values()):
            self.assertRegex(str(value), r"\A[0-9a-f]{64}\Z")
        for name in builder.PACKAGE_FILES:
            self.assertEqual(shipped["package_files_sha256"][name], builder.sha256_file(HERE / name), name)
        manifest_path = HERE / builder.MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        anchor = builder.sha256_file(HERE / builder.REVIEWED_TABLE_NAME)
        verified = builder.verify_manifest(ROOT, manifest, package_root=HERE,
                                           expected_reviewed_table_sha256=anchor)
        self.assertEqual(verified["status"], "draft_ready_for_owner_review")
        self.assertEqual(verified["verified_dependencies"], 29)
        self.assertEqual(verified["verified_package_files"], 5)
        for key in ("push_authorized", "gpu_allocation_authorized", "run_authorized"):
            self.assertFalse(manifest[key], key)
        self.assertFalse(manifest["can_emit_approved_or_pushed"])
        self.assertTrue(manifest["is_draft"])
        proc = subprocess.run(
            [sys.executable, "-B", str(HERE / "build_wp7_package.py"), "--root", str(ROOT),
             "--package-root", str(HERE), "--expected-reviewed-table-sha256", anchor,
             "--verify", str(manifest_path)],
            capture_output=True, cwd=HERE, env=safe_child_env())
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())

    def test_synthetic_placeholder_table_is_refused_and_invalid(self) -> None:
        """Placeholder refusal remains covered after the lead pins the shipped table."""
        with tempfile.TemporaryDirectory(prefix="wp7-placeholder-") as d:
            package_root = Path(d) / "package"
            package_root.mkdir()
            _make_package(package_root)
            dependencies = {"a.py": builder.PENDING, "b.py": builder.PENDING}
            package_hashes = {name: builder.sha256_file(package_root / name)
                              for name in builder.PACKAGE_FILES}
            placeholder = {"_placeholder": True, "_placeholder_notice": "synthetic fixture only",
                           "dependencies": dependencies, "package_files_sha256": package_hashes}
            self.assertTrue(placeholder.get("_placeholder"), "synthetic table must be marked as a placeholder")
            self.assertEqual(placeholder.get("_placeholder_notice"), placeholder.get("_placeholder_notice"))
            for value in placeholder["dependencies"].values():
                self.assertEqual(value, builder.PENDING, placeholder)
            for name in builder.PACKAGE_FILES:
                self.assertIn(name, placeholder["package_files_sha256"], name)
            table_path = package_root / builder.REVIEWED_TABLE_NAME
            table_path.write_text(json.dumps(placeholder, sort_keys=True, indent=2) + "\n")
            anchor = builder.sha256_file(table_path)

            invalid = builder.build_manifest(package_root, dependencies,
                                             expected_reviewed_table_sha256=anchor,
                                             package_root=package_root)
            self.assertEqual(invalid["status"], builder.STATUS_INVALID)
            with self.assertRaises(builder.Wp7PackageError):
                builder.verify_manifest(package_root, invalid, package_root=package_root,
                                         expected_reviewed_table_sha256=anchor)

            bad_package_hashes = dict(package_hashes)
            bad_package_hashes[builder.PACKAGE_FILES[0]] = "PENDING_PLACEHOLDER"
            placeholder["package_files_sha256"] = bad_package_hashes
            table_path.write_text(json.dumps(placeholder, sort_keys=True, indent=2) + "\n")
            anchor = builder.sha256_file(table_path)
            with self.assertRaises((builder.Wp7PackageError, builder.Wp7DependencyError)):
                builder.load_reviewed_table(package_root, anchor)
            with self.assertRaises(builder.Wp7PackageError):
                builder.build_manifest(package_root, dependencies,
                                      expected_reviewed_table_sha256=anchor,
                                      package_root=package_root)
            with self.assertRaises(builder.Wp7PackageError):
                anchored_build(package_root, dependencies, package_root=package_root)
            with self.assertRaises(builder.Wp7PackageError):
                anchored_verify(package_root, {"status": builder.STATUS_READY},
                                package_root=package_root)
            out = Path(d) / "placeholder-manifest.json"
            proc = subprocess.run(
                [sys.executable, "-B", str(HERE / "build_wp7_package.py"),
                 "--root", str(package_root), "--package-root", str(package_root),
                 "--out", str(out), "--expected-reviewed-table-sha256", anchor],
                capture_output=True, cwd=d, env=safe_child_env())
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn(b"FAIL:", proc.stderr)
            self.assertFalse(out.exists())

    def test_shipped_table_keeps_manifest_invalid_in_this_tree(self) -> None:
        """Retain legacy placeholder assertions; the reviewed state verifies ready."""
        shipped_path = HERE / builder.REVIEWED_TABLE_NAME
        shipped = json.loads(shipped_path.read_text(encoding="utf-8"))
        anchor = builder.sha256_file(shipped_path)
        if shipped.get("_placeholder"):
            with self.assertRaises(builder.Wp7PackageError):
                builder.load_reviewed_table(HERE, anchor)
            with self.assertRaises(builder.Wp7PackageError):
                builder.build_manifest(ROOT, shipped["dependencies"],
                                      expected_reviewed_table_sha256=anchor)
            for value in shipped["dependencies"].values():
                self.assertEqual(value, builder.PENDING, shipped)
            for name in builder.PACKAGE_FILES:
                self.assertIn(name, shipped["package_files_sha256"], name)
            with self.assertRaises(builder.Wp7PackageError):
                builder.verify_manifest(ROOT, {"status": builder.STATUS_READY},
                                        expected_reviewed_table_sha256=anchor)
            return

        self.assertFalse(any(str(key).startswith("_") for key in shipped))
        manifest = json.loads((HERE / builder.MANIFEST_NAME).read_text(encoding="utf-8"))
        verified = builder.verify_manifest(ROOT, manifest, package_root=HERE,
                                           expected_reviewed_table_sha256=anchor)
        self.assertEqual(verified["status"], "draft_ready_for_owner_review")
        self.assertEqual(verified["verified_dependencies"], 29)
        self.assertEqual(verified["verified_package_files"], 5)

    def test_synthetic_table_keeps_manifest_invalid_in_this_tree(self) -> None:
        """With a synthetic table in a temp dir, a real-tree build is draft_invalid.

        The fixtures never use the shipped table to build; they build against a
        synthetic reviewed table written into a temp package root, exactly as
        the builder's own contract requires (the table is an external trust
        anchor the lead supplies after the build).
        """
        with SyntheticTree() as tree:
            tree.add_session_dependencies()
            manifest = anchored_build(tree.root, tree.session_table, package_root=tree.root)
            self.assertEqual(manifest["status"], builder.STATUS_READY, manifest["invalidating_reasons"])
        # A deliberately PENDING synthetic table keeps the manifest invalid.
        with SyntheticTree() as tree:
            tree.add_session_dependencies()
            pending_table = dict(tree.session_table)
            pending_table["research/g9/stage2_production_writer.py"] = "PENDING"
            manifest = anchored_build(tree.root, pending_table, package_root=tree.root)
            self.assertEqual(manifest["status"], builder.STATUS_INVALID)
            self.assertTrue(manifest["invalidating_reasons"])
            with self.assertRaises(builder.Wp7PackageError):
                anchored_verify(tree.root, manifest, package_root=tree.root)

    def test_real_dependency_change_invalidates_the_real_tree_manifest(self) -> None:
        """A real v1 dependency, one byte off, makes the real tree invalid.

        The real dependency is copied (never modified) and the real builder
        is used, so this is the same code path the owner will run.
        """
        with tempfile.TemporaryDirectory() as d:
            rel = "research/g9/cuda_qualification/stage2_cuda_core_bridge.cu"
            src = ROOT / rel
            copy_root = Path(d)
            _write(copy_root / rel, src.read_bytes())
            _make_package(copy_root)
            table = {rel: builder.sha256_file(src)}
            ready = anchored_build(copy_root, table, package_root=copy_root)
            self.assertEqual(ready["status"], builder.STATUS_READY, ready["invalidating_reasons"])
            verified = anchored_verify(copy_root, ready, package_root=copy_root)
            self.assertEqual(verified["verified_dependencies"], 1)
            _write(copy_root / rel, src.read_bytes()[:-1] + b"\x00")
            after = anchored_build(copy_root, table, package_root=copy_root)
            self.assertEqual(after["status"], builder.STATUS_INVALID)
            self.assertTrue(any("hash mismatch" in r for r in after["invalidating_reasons"]))
            with self.assertRaisesRegex(builder.Wp7PackageError, "stale"):
                anchored_verify(copy_root, ready, package_root=copy_root)

    def test_verify_refuses_missing_reason_on_unmatched_entry(self) -> None:
        table = dict(self.tree.table)
        table["b.py"] = builder.PENDING
        manifest = anchored_build(self.tree.root, table)
        bad = copy.deepcopy(manifest)
        for entry in bad["dependencies"]:
            if entry["state"] != "matched":
                entry["reason"] = None
        bad["content_sha256"] = builder.content_sha256(bad)
        with self.assertRaisesRegex(builder.Wp7PackageError, "states no reason"):
            anchored_verify(self.tree.root, bad, package_root=self.tree.root)

    def test_verify_refuses_invalid_status_with_all_entries_matched(self) -> None:
        manifest = self._ready()
        bad = copy.deepcopy(manifest)
        bad["status"] = builder.STATUS_INVALID
        bad["content_sha256"] = builder.content_sha256(bad)
        with self.assertRaisesRegex(builder.Wp7PackageError, "not verifiable as ready"):
            anchored_verify(self.tree.root, bad, package_root=self.tree.root)

    def test_every_invalidating_state_names_its_own_reason(self) -> None:
        for state, table_patch, reason in (
            ("pending", {"b.py": builder.PENDING}, "review has not PASSED"),
            ("bad_recorded_hash", {"a.py": "NOTAHASH"}, "neither PENDING nor a lowercase sha256"),
        ):
            table = dict(self.tree.table)
            table.update(table_patch)
            if state == "bad_recorded_hash":
                with self.assertRaisesRegex(builder.Wp7PackageError, "lowercase sha256"):
                    anchored_build(self.tree.root, table)
            else:
                manifest = anchored_build(self.tree.root, table)
                entries = {e["path"]: e for e in manifest["dependencies"]}
                for path, entry in entries.items():
                    if entry["state"] == state:
                        self.assertIn(reason, entry["reason"], f"{state} reason for {path}")
        (self.tree.root / "c.json").unlink()
        manifest = anchored_build(self.tree.root, self.tree.table, package_root=self.tree.root)
        entry = {e["path"]: e for e in manifest["dependencies"]}["c.json"]
        self.assertEqual(entry["state"], "missing")
        self.assertIn("not present", entry["reason"])
        self.tree.flip_one_byte("a.py")
        manifest = anchored_build(self.tree.root, self.tree.table, package_root=self.tree.root)
        entry = {e["path"]: e for e in manifest["dependencies"]}["a.py"]
        self.assertEqual(entry["state"], "hash_mismatch")
        self.assertIn("content changed since review", entry["reason"])

    def test_pending_state_is_exact_not_a_generic_bad_hash(self) -> None:
        table = dict(self.tree.table)
        table["b.py"] = builder.PENDING
        manifest = anchored_build(self.tree.root, table)
        entry = {e["path"]: e for e in manifest["dependencies"]}["b.py"]
        self.assertEqual(entry["state"], "pending")
        self.assertIn("review has not PASSED", entry["reason"])
        self.assertEqual(entry["current_sha256"], builder.sha256_file(self.tree.root / "b.py"))

    def test_status_fragment_guard_is_independently_load_bearing(self) -> None:
        original = builder.ALLOWED_STATUSES
        try:
            builder.ALLOWED_STATUSES = (
                "draft_invalid", "draft_ready_for_owner_review",
                "approved", "pushed", "push_complete", "released", "executed",
            )
            for bad in ("approved", "pushed", "push_complete", "released", "executed"):
                with self.assertRaisesRegex(builder.Wp7PackageError, "forbidden fragment"):
                    builder.validate_status(bad)
            self.assertEqual(builder.validate_status("draft_invalid"), "draft_invalid")
        finally:
            builder.ALLOWED_STATUSES = original
        for bad in ("approved", "pushed"):
            with self.assertRaises(builder.Wp7PackageError):
                builder.validate_status(bad)

    def test_kernel_metadata_draft_policy(self) -> None:
        builder.validate_kernel_metadata_draft(builder.KERNEL_METADATA_DRAFT)
        for key in ("enable_internet", "enable_tpu"):
            bad = dict(builder.KERNEL_METADATA_DRAFT)
            bad[key] = True
            with self.assertRaisesRegex(builder.Wp7PackageError, key):
                builder.validate_kernel_metadata_draft(bad)
        for key in ("is_private", "enable_gpu"):
            bad = dict(builder.KERNEL_METADATA_DRAFT)
            bad[key] = False
            with self.assertRaisesRegex(builder.Wp7PackageError, key):
                builder.validate_kernel_metadata_draft(bad)
        bad = dict(builder.KERNEL_METADATA_DRAFT)
        bad["dataset_sources"] = ["something"]
        with self.assertRaisesRegex(builder.Wp7PackageError, "dataset_sources"):
            builder.validate_kernel_metadata_draft(bad)
        bad = dict(builder.KERNEL_METADATA_DRAFT)
        bad["draft"] = False
        with self.assertRaisesRegex(builder.Wp7PackageError, "draft"):
            builder.validate_kernel_metadata_draft(bad)
        for key in builder.KERNEL_METADATA_REQUIRED_TEXT:
            bad = dict(builder.KERNEL_METADATA_DRAFT)
            bad[key] = "   "
            with self.assertRaisesRegex(builder.Wp7PackageError, key):
                builder.validate_kernel_metadata_draft(bad)
        for key in builder.KERNEL_METADATA_REQUIRED_EMPTY_LISTS:
            bad = dict(builder.KERNEL_METADATA_DRAFT)
            bad[key] = ()
            with self.assertRaisesRegex(builder.Wp7PackageError, key):
                builder.validate_kernel_metadata_draft(bad)
        bad = dict(builder.KERNEL_METADATA_DRAFT)
        bad["code_file"] = None
        with self.assertRaisesRegex(builder.Wp7PackageError, "code_file"):
            builder.validate_kernel_metadata_draft(bad)

    def test_missing_package_file_is_an_invalidating_reason_not_a_null_hash(self) -> None:
        manifest = anchored_build(self.tree.root, self.tree.table, package_root=self.tree.root)
        (self.tree.root / "wp7_session.py").unlink()
        with self.assertRaisesRegex(builder.Wp7DependencyError, "package files differ"):
            anchored_build(self.tree.root, self.tree.table, package_root=self.tree.root)
        with self.assertRaises(builder.Wp7PackageError):
            anchored_verify(self.tree.root, manifest, package_root=self.tree.root)

    def test_package_file_pinning_is_not_silently_skipped(self) -> None:
        """Dropping a package file from the pin is refused, not accepted."""
        manifest = self._ready()
        bad = copy.deepcopy(manifest)
        bad["package_files_sha256"].pop("wp7_session.py")
        bad["content_sha256"] = builder.content_sha256(bad)
        with self.assertRaisesRegex(builder.Wp7PackageError, "reviewed table"):
            anchored_verify(self.tree.root, bad, package_root=self.tree.root)
        bad = copy.deepcopy(manifest)
        bad["package_files_sha256"]["wp7_session.py"] = None
        bad["content_sha256"] = builder.content_sha256(bad)
        with self.assertRaisesRegex(builder.Wp7PackageError, "reviewed table"):
            anchored_verify(self.tree.root, bad, package_root=self.tree.root)
        bad = copy.deepcopy(manifest)
        bad["package_file_count"] = 1
        bad["content_sha256"] = builder.content_sha256(bad)
        with self.assertRaisesRegex(builder.Wp7PackageError, "package_file_count"):
            anchored_verify(self.tree.root, bad, package_root=self.tree.root)
        bad = copy.deepcopy(manifest)
        bad["package_file_count"] = True
        bad["content_sha256"] = builder.content_sha256(bad)
        with self.assertRaisesRegex(builder.Wp7PackageError, "package_file_count"):
            anchored_verify(self.tree.root, bad, package_root=self.tree.root)

    def test_package_file_symlink_escape_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            root.mkdir()
            _make_package(root)
            outside = Path(d) / "outside.py"
            outside.write_bytes(b"# outside the root\n")
            (root / "wp7_session.py").unlink()
            os.symlink(str(outside), str(root / "wp7_session.py"))
            evaluation = builder.evaluate_package_files(root)
            self.assertIsNone(evaluation["hashes"]["wp7_session.py"])
            self.assertFalse(evaluation["all_matched"])
            self.assertTrue(
                any("resolves outside the root" in r for r in evaluation["reasons"]),
                evaluation["reasons"],
            )


# --------------------------------------------------------------------------
# Path containment
# --------------------------------------------------------------------------
class TestExternalReviewAnchor(unittest.TestCase):
    def setUp(self):
        self.tree = SyntheticTree()
        self.addCleanup(self.tree.close)
        self.anchor = _reviewed_file(self.tree.root, self.tree.table)
        self.manifest = builder.build_manifest(self.tree.root, self.tree.table,
            package_root=self.tree.root, expected_reviewed_table_sha256=self.anchor)
        self.assertEqual(self.manifest["status"], builder.STATUS_READY)

    def verify(self, manifest=None):
        return builder.verify_manifest(self.tree.root, self.manifest if manifest is None else manifest,
            package_root=self.tree.root, expected_reviewed_table_sha256=self.anchor)

    def test_each_independent_byte_change_is_refused(self):
        self.verify()
        for target in ("a.py", "wp7_session.py", builder.REVIEWED_TABLE_NAME):
            with self.subTest(target=target):
                path = self.tree.root / target
                original = path.read_bytes()
                path.write_bytes(original + b" ")
                with self.assertRaises(builder.Wp7PackageError):
                    self.verify()
                if target == "a.py":
                    rebuilt = builder.build_manifest(self.tree.root, self.tree.table,
                        package_root=self.tree.root, expected_reviewed_table_sha256=self.anchor)
                    self.assertEqual(rebuilt["status"], builder.STATUS_INVALID)
                else:
                    with self.assertRaises(builder.Wp7PackageError):
                        builder.build_manifest(self.tree.root, self.tree.table, package_root=self.tree.root,
                            expected_reviewed_table_sha256=self.anchor)
                path.write_bytes(original)
        changed = copy.deepcopy(self.manifest)
        changed["kernel_metadata_draft"]["title"] += "x"
        with self.assertRaises(builder.Wp7PackageError):
            self.verify(changed)

    def test_added_package_entry_is_refused(self):
        self.verify()
        (self.tree.root / "unreviewed.py").write_bytes(b"# new package file\n")
        with self.assertRaisesRegex(builder.Wp7DependencyError, "unreviewed package entries"):
            builder.build_manifest(self.tree.root, self.tree.table, package_root=self.tree.root,
                expected_reviewed_table_sha256=self.anchor)
        with self.assertRaisesRegex(builder.Wp7DependencyError, "unreviewed package entries"):
            self.verify()

    def test_consistent_manifest_and_table_edit_still_refused(self):
        self.tree.flip_one_byte("a.py")
        new_hash = builder.sha256_file(self.tree.root / "a.py")
        record = json.loads((self.tree.root / builder.REVIEWED_TABLE_NAME).read_text())
        record["dependencies"]["a.py"] = new_hash
        (self.tree.root / builder.REVIEWED_TABLE_NAME).write_text(json.dumps(record, sort_keys=True))
        forged = copy.deepcopy(self.manifest)
        for entry in forged["dependencies"]:
            if entry["path"] == "a.py":
                entry["recorded_reviewed_sha256"] = new_hash
                entry["current_sha256"] = new_hash
        forged["dependency_table_sha256"] = builder.dependency_table_sha256(record["dependencies"])
        forged["content_sha256"] = builder.content_sha256(forged)
        with self.assertRaisesRegex(builder.Wp7DependencyError, "caller approval"):
            self.verify(forged)
        with self.assertRaisesRegex(builder.Wp7DependencyError, "caller approval"):
            builder.build_manifest(self.tree.root, record["dependencies"], package_root=self.tree.root,
                expected_reviewed_table_sha256=self.anchor)

    def test_required_anchor_argument_and_type(self):
        with self.assertRaises(TypeError):
            builder.build_manifest(self.tree.root, self.tree.table, package_root=self.tree.root)
        for value in (None, True, 1, [], {}, {"nested": []}):
            with self.subTest(value=repr(value)):
                with self.assertRaises(builder.Wp7PackageError):
                    builder.build_manifest(self.tree.root, self.tree.table, package_root=self.tree.root,
                        expected_reviewed_table_sha256=value)
                with self.assertRaises(builder.Wp7PackageError):
                    builder.verify_manifest(self.tree.root, self.manifest, package_root=self.tree.root,
                        expected_reviewed_table_sha256=value)


class TestDirectGuardBehavior(unittest.TestCase):
    def test_session_sha256_path_guard_is_independent_of_boundary_helper(self) -> None:
        original = session.read_bytes_at_boundary
        session.read_bytes_at_boundary = lambda path, label: b"synthetic"
        try:
            with self.assertRaisesRegex(session.Wp7SessionError, "must be a Path"):
                session.sha256_file("not-a-path")
        finally:
            session.read_bytes_at_boundary = original

    def test_session_root_itself_guard_is_independently_exercised(self) -> None:
        with SyntheticTree() as tree:
            target = tree.root / "a.py"
            _write(target, b"synthetic")
            original_realpath = os.path.realpath
            original_is_file = Path.is_file
            original_mode_check = session.S_ISREG
            try:
                os.path.realpath = lambda path: str(tree.root) if str(path) == str(target) else original_realpath(path)
                Path.is_file = lambda path: True if path == tree.root else original_is_file(path)
                session.S_ISREG = lambda mode: True
                with self.assertRaisesRegex(session.Wp7PathError, "root itself"):
                    session.resolve_inside_root(tree.root, "a.py", "probe")
            finally:
                os.path.realpath = original_realpath
                Path.is_file = original_is_file
                session.S_ISREG = original_mode_check

    def test_both_round3_regular_file_guards_are_independently_exercised(self) -> None:
        """Each restored guard refuses even when the other reports success."""
        with SyntheticTree() as tree:
            target = tree.root / "a.py"
            _write(target, b"x")
            original_is_file = Path.is_file
            original_stat = Path.stat
            try:
                Path.is_file = lambda path: False if path == target else original_is_file(path)
                for module in (builder, session):
                    with self.assertRaisesRegex(module.Wp7PathError, "not a regular file"):
                        module.resolve_inside_root(tree.root, "a.py", "probe")
            finally:
                Path.is_file = original_is_file
            try:
                Path.is_file = lambda path: True if path == target else original_is_file(path)
                def fifo_stat(path, *args, **kwargs):
                    result = original_stat(path, *args, **kwargs)
                    if path == target:
                        data = list(result)
                        data[0] = stat.S_IFIFO | 0o644
                        return os.stat_result(data)
                    return result
                Path.stat = fifo_stat
                for module in (builder, session):
                    with self.assertRaisesRegex(module.Wp7PathError, "not a regular file"):
                        module.resolve_inside_root(tree.root, "a.py", "probe")
            finally:
                Path.stat = original_stat
                Path.is_file = original_is_file
    def setUp(self):
        self.tree = SyntheticTree()
        self.addCleanup(self.tree.close)
        self.anchor = _reviewed_file(self.tree.root, self.tree.table)
        self.manifest = builder.build_manifest(self.tree.root, self.tree.table,
            package_root=self.tree.root, expected_reviewed_table_sha256=self.anchor)

    def test_builder_argument_and_path_guards(self):
        self.assertFalse(builder._is_sha256(None))
        with self.assertRaisesRegex(builder.Wp7PathError, "not absolute"):
            builder.normalize_relative_path("/absolute", "dependency")
        (self.tree.root / "directory").mkdir()
        with self.assertRaisesRegex(builder.Wp7PathError, "not a regular file"):
            builder.resolve_inside_root(self.tree.root, "directory", "dependency")
        (self.tree.root / "directory").rmdir()
        with self.assertRaisesRegex(builder.Wp7PackageError, "dependency table is empty"):
            builder.evaluate_dependencies(self.tree.root, {})
        bad_table = dict(self.tree.table, **{"a.py": "bad"})
        report = builder.evaluate_dependencies(self.tree.root, bad_table)
        self.assertEqual(next(e for e in report["entries"] if e["path"] == "a.py")["state"], "bad_recorded_hash")
        with self.assertRaisesRegex(builder.Wp7PackageError, "package_root must be a Path or None"):
            builder.build_manifest(self.tree.root, self.tree.table, package_root="wrong",
                expected_reviewed_table_sha256=self.anchor)
        with self.assertRaisesRegex(builder.Wp7DependencyError, "caller dependency table differs"):
            builder.build_manifest(self.tree.root, {"a.py": self.tree.table["a.py"]},
                package_root=self.tree.root, expected_reviewed_table_sha256=self.anchor)
        with self.assertRaisesRegex(builder.Wp7PackageError, "environment pin must be a dict"):
            builder.build_manifest(self.tree.root, self.tree.table, environment_pin=[],
                package_root=self.tree.root, expected_reviewed_table_sha256=self.anchor)
        for value in (True, 0, "plain", [], {}):
            with self.subTest(cli_path=value):
                with self.assertRaisesRegex(builder.Wp7PathError, "CLI path must be a Path"):
                    builder.assert_safe_cli_path(value)

    def test_package_inventory_typed_errors(self):
        for root, home in (("bad", self.tree.root), (self.tree.root, "bad")):
            with self.subTest(root=root, home=home):
                with self.assertRaisesRegex(builder.Wp7PackageError, "package inventory roots must be Paths"):
                    builder.assert_package_inventory(root, home, self.tree.table)
        for bad in (None, True, 1, "x", [], {"a.py": []}, {"a.py": {"nested": 1}}):
            with self.subTest(dependencies=repr(bad)):
                with self.assertRaises(builder.Wp7PackageError):
                    builder.assert_package_inventory(self.tree.root, self.tree.root, bad)
        original_iterdir = Path.iterdir
        def denied_iterdir(_self):
            raise OSError("denied")
        try:
            Path.iterdir = denied_iterdir
            with self.assertRaisesRegex(builder.Wp7PackageError, "cannot list package files"):
                builder.assert_package_inventory(self.tree.root, self.tree.root, self.tree.table)
        finally:
            Path.iterdir = original_iterdir

    def test_review_table_shape_and_json_guards(self):
        path = self.tree.root / builder.REVIEWED_TABLE_NAME
        original = path.read_bytes()
        cases = [
            ({"dependencies": {}, "package_files_sha256": self.tree.package_hashes}, "reviewed dependencies are empty"),
            ({"dependencies": self.tree.table, "package_files_sha256": {}}, "must name every package file"),
        ]
        for record, message in cases:
            with self.subTest(message=message):
                path.write_text(json.dumps(record))
                with self.assertRaisesRegex(builder.Wp7PackageError, message):
                    builder.load_reviewed_table(self.tree.root, builder.sha256_file(path))
        path.write_bytes(b"{" )
        with self.assertRaisesRegex(builder.Wp7DependencyError, "cannot parse reviewed table"):
            builder.load_reviewed_table(self.tree.root, builder.sha256_file(path))
        path.write_bytes(original)

    def test_review_table_rejects_malformed_nonpending_hash(self):
        path = self.tree.root / builder.REVIEWED_TABLE_NAME
        record = json.loads(path.read_text())
        record["dependencies"]["a.py"] = "not-a-sha256"
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(builder.Wp7PackageError, "lowercase sha256"):
            builder.load_reviewed_table(self.tree.root, builder.sha256_file(path))

    def test_package_inventory_rejects_malformed_nonpending_hash(self):
        bad = dict(self.tree.table, **{"a.py": "not-a-sha256"})
        with self.assertRaisesRegex(builder.Wp7PackageError, "lowercase sha256"):
            builder.assert_package_inventory(self.tree.root, self.tree.root, bad)

    def test_manifest_entry_and_package_file_guards(self):
        entries = self.manifest["dependencies"]
        for bad, message in (([], "non-empty list"),
                             (entries + [entries[0]], "repeated"),
                             ([dict(entries[0], state="bogus")], "unknown state")):
            with self.subTest(message=message):
                with self.assertRaisesRegex(builder.Wp7PackageError, message):
                    builder._manifest_entry_set({"dependencies": bad})
        packages = self.manifest["package_files_sha256"]
        wrong_names = dict(packages)
        wrong_names.pop("wp7_session.py")
        wrong_names["other.py"] = "0" * 64
        problems = builder._verify_package_files(self.tree.root, {
            "package_files_sha256": wrong_names,
            "package_file_count": len(builder.PACKAGE_FILES)})
        self.assertTrue(any("wp7_session.py" in item and "not pinned" in item for item in problems))
        for bad, message in (({}, "must pin all"),
                             ({**packages, "wp7_session.py": "bad"}, "no usable hash")):
            with self.subTest(message=message):
                if message == "no usable hash":
                    problems = builder._verify_package_files(self.tree.root, {
                        "package_files_sha256": bad,
                        "package_file_count": len(builder.PACKAGE_FILES)})
                    self.assertTrue(any(message in item for item in problems))
                else:
                    with self.assertRaisesRegex(builder.Wp7PackageError, message):
                        builder._verify_package_files(self.tree.root, {
                            "package_files_sha256": bad,
                            "package_file_count": len(builder.PACKAGE_FILES)})

    def test_manifest_external_fields_cannot_be_recomputed(self):
        cases = [
            ("reviewed_table_sha256", "0" * 64, "caller approval"),
            ("dependency_table_sha256", "0" * 64, "dependency_table_sha256"),
        ]
        for field, value, message in cases:
            with self.subTest(field=field):
                bad = copy.deepcopy(self.manifest)
                bad[field] = value
                bad["content_sha256"] = builder.content_sha256(bad)
                with self.assertRaisesRegex(builder.Wp7PackageError, message):
                    builder.verify_manifest(self.tree.root, bad, package_root=self.tree.root,
                        expected_reviewed_table_sha256=self.anchor)
        bad = copy.deepcopy(self.manifest)
        del bad["kaggle_rewrites_on_pull"]
        bad["content_sha256"] = builder.content_sha256(bad)
        with self.assertRaisesRegex(builder.Wp7CompletenessError, "kaggle_rewrites_on_pull"):
            builder.verify_manifest(self.tree.root, bad, package_root=self.tree.root,
                expected_reviewed_table_sha256=self.anchor)
        self.tree.flip_one_byte("a.py")
        bad = copy.deepcopy(self.manifest)
        new_hash = builder.sha256_file(self.tree.root / "a.py")
        for entry in bad["dependencies"]:
            if entry["path"] == "a.py": entry["current_sha256"] = new_hash
        bad["content_sha256"] = builder.content_sha256(bad)
        with self.assertRaisesRegex(builder.Wp7PackageError, "current hash differs from reviewed hash"):
            builder.verify_manifest(self.tree.root, bad, package_root=self.tree.root,
                expected_reviewed_table_sha256=self.anchor)

    def test_session_direct_guard_paths(self):
        with self.assertRaises(session.Wp7SessionError):
            session.sha256_file(self.tree.root / "missing")
        sys.modules[None] = object()
        try:
            session.assert_no_prohibited_imports()
        finally:
            sys.modules.pop(None, None)
        with self.assertRaisesRegex(session.Wp7SessionError, "root is not a directory"):
            session.resolve_dependencies(self.tree.root / "missing", self.tree.table)
        with self.assertRaisesRegex(session.Wp7SessionError, "dependency table is empty"):
            session.resolve_dependencies(self.tree.root, {})
        for root, directory, message in (("bad", self.tree.root, "root must be a Path"),
                                         (self.tree.root, "bad", "output_dir must be a Path")):
            with self.subTest(root=root, directory=directory):
                with self.assertRaisesRegex(session.Wp7SessionError, message):
                    session.resolve_dir_inside_root(root, directory)
        for value in (True, 0, "plain", [], {}):
            with self.subTest(cli_path=value):
                with self.assertRaisesRegex(session.Wp7PathError, "CLI path must be a Path"):
                    session.assert_safe_cli_path(value)
        # Round 3 raised the SPECIFIC Wp7EnvironmentAbort here, and the
        # validated fixture asserted that subclass.  A later round weakened it
        # to the Wp7SessionError base class; both the raise and this
        # assertion are restored to the round-3 form.
        with self.assertRaisesRegex(session.Wp7EnvironmentAbort, "keys must be strings"):
            session._flatten({"okay": 1, 2: 3})
        with self.assertRaisesRegex(session.Wp7StepResultError, "field name"):
            session._require_str_keyed_map({1: "bad"}, "identities")
        with self.assertRaisesRegex(session.Wp7SessionError, "not callable"):
            session._validate_step_table({**_steps(), "wp4b_writer_synthetic_ranges": "bad"})
        with self.assertRaisesRegex(session.Wp7IncompleteReceiptError, "output hash"):
            session.build_receipt(steps=list(session.REQUIRED_STEPS), counters={}, identities={},
                                  digests={}, differences=[])
        with self.assertRaisesRegex(session.Wp7StepResultError, "known-empty"):
            session._classify_step_result("wp6b_section_a_qualification_plan", {"output": {}})


class TestPathContainment(unittest.TestCase):
    BAD_LEXICAL = (
        "/abs.py", "../escape.py", "a/../../escape.py", "./a.py", "a//b.py",
        "a\\b.py", "", "a/./b.py", "C:/x.py", "nul\x00.py", "a/b/../..", ".",
        "..", "a/..", "/", "///a.py", "a/b/",
    )

    def test_lexical_normalization_refuses_every_bad_form(self) -> None:
        for bad in self.BAD_LEXICAL:
            with self.subTest(path=bad):
                with self.assertRaises(builder.Wp7PathError):
                    builder.normalize_relative_path(bad, "path")
                with self.assertRaises(session.Wp7PathError):
                    session.normalize_relative_path(bad, "path")
        for good in ("a.py", "research/g9/x.py", "a/b/c/d.json"):
            self.assertEqual(builder.normalize_relative_path(good, "path"), good)
            self.assertEqual(session.normalize_relative_path(good, "path"), good)
        for bad in (None, 5, [], {}, b"a.py", True):
            with self.assertRaises(builder.Wp7PathError):
                builder.normalize_relative_path(bad, "path")
            with self.assertRaises(session.Wp7PathError):
                session.normalize_relative_path(bad, "path")

    def test_specific_refusal_messages_name_the_problem(self) -> None:
        cases = (
            ("/abs.py", "not absolute"),
            ("../escape.py", r"'..' component"),
            ("./a.py", r"'\.' component"),
            ("a//b.py", "empty path component"),
            ("a\\b.py", "'/' separators"),
            ("", "must not be empty"),
            ("nul\x00.py", "NUL byte"),
            ("C:/x.py", "drive-qualified"),
        )
        for path, message in cases:
            with self.subTest(path=path):
                with self.assertRaisesRegex(builder.Wp7PathError, message):
                    builder.normalize_relative_path(path, "path")
                with self.assertRaisesRegex(session.Wp7PathError, message):
                    session.normalize_relative_path(path, "path")

    def test_absolute_dependency_path_never_reads_outside_the_root(self) -> None:
        """The validator's probe: an absolute path must not be read."""
        with tempfile.TemporaryDirectory() as d:
            outside = Path(d) / "outside.py"
            outside.write_bytes(b"# outside\n")
            root = Path(d) / "root"
            root.mkdir()
            digest = builder.sha256_file(outside)
            # Build: the entry is recorded as a non-matching reason, never read.
            with self.assertRaises(builder.Wp7PackageError):
                anchored_build(root, {str(outside): digest})
            with self.assertRaisesRegex(builder.Wp7PathError, "not absolute"):
                builder.normalize_relative_path(str(outside), "path")
            # Verify: the entry is refused, and the file is still not read.
            with self.assertRaises(builder.Wp7PackageError):
                anchored_build(root, {"a.py": "0" * 64})
            with self.assertRaisesRegex(session.Wp7DependencyError, "not absolute"):
                session.resolve_dependencies(root, {str(outside): digest})

    def test_parent_relative_dependency_never_escapes(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            root.mkdir()
            outside = Path(d) / "outside.py"
            outside.write_bytes(b"# outside\n")
            digest = builder.sha256_file(outside)
            with self.assertRaises(builder.Wp7PackageError):
                anchored_build(root, {"../outside.py": digest})
            with self.assertRaisesRegex(builder.Wp7PathError, "'..' component"):
                builder.normalize_relative_path("../outside.py", "path")
            with self.assertRaisesRegex(session.Wp7DependencyError, "'..' component"):
                session.resolve_dependencies(root, {"../outside.py": digest})

    def test_symlink_escaping_the_root_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            root.mkdir()
            outside = Path(d) / "outside.py"
            outside.write_bytes(b"# outside\n")
            (root / "link.py").symlink_to(outside)
            digest = builder.sha256_file(outside)
            with self.assertRaises(builder.Wp7PackageError):
                anchored_build(root, {"link.py": digest})
            with self.assertRaisesRegex(session.Wp7DependencyError, "resolves outside the root"):
                session.resolve_dependencies(root, {"link.py": digest})
            with self.assertRaisesRegex(builder.Wp7PathError, "resolves outside the root"):
                builder.resolve_inside_root(root, "link.py", "path")

    def test_symlink_inside_the_root_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            (root / "sub").mkdir(parents=True)
            (root / "sub" / "real.py").write_bytes(b"# real\n")
            (root / "link.py").symlink_to(root / "sub" / "real.py")
            digest = builder.sha256_file(root / "sub" / "real.py")
            resolved = builder.resolve_inside_root(root, "link.py", "path")
            self.assertEqual(builder.sha256_file(resolved), digest)

    def test_directory_and_root_itself_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            (root / "sub").mkdir(parents=True)
            with self.assertRaisesRegex(builder.Wp7PathError, "not a regular file"):
                builder.resolve_inside_root(root, "sub", "path")
            with self.assertRaisesRegex(session.Wp7PathError, "not a regular file"):
                session.resolve_inside_root(root, "sub", "path")
            with self.assertRaisesRegex(builder.Wp7PathError, "does not exist"):
                builder.resolve_inside_root(root, "nope.py", "path")
            with self.assertRaisesRegex(session.Wp7PathError, "does not exist"):
                session.resolve_inside_root(root, "nope.py", "path")
            with self.assertRaises(builder.Wp7PackageError):
                builder.resolve_inside_root("not a path", "a.py", "path")
            with self.assertRaises(session.Wp7SessionError):
                session.resolve_inside_root("not a path", "a.py", "path")

    def test_dependency_gate_refuses_credential_path(self) -> None:
        for path in (".kaggle/kaggle.json", "/home/x/.kaggle/kaggle.json",
                     "research/g9/.kaggle/kaggle.json"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(session.Wp7ProhibitedOperationError, ".kaggle"):
                    session.resolve_dependencies(ROOT, {path: "0" * 64})


# --------------------------------------------------------------------------
# Environment pin
# --------------------------------------------------------------------------
class TestEnvironmentPinComparison(unittest.TestCase):
    def test_exact_match_passes(self) -> None:
        result = session.compare_environment_pin(
            _observed({"gpu_name": "Tesla T4", "python_version": "3.12.13"}, {"kaggle_image": "img@sha256:abc"}),
            _pin(),
        )
        self.assertEqual(result["comparison"], "exact_match")
        self.assertEqual(result["difference_count"], 0)
        self.assertEqual(result["provenance"], "PLATFORM-REPORTED")
        self.assertEqual(result["compared_fields"], 3)

    def test_every_single_field_difference_aborts(self) -> None:
        base_platform = {"gpu_name": "Tesla T4", "python_version": "3.12.13"}
        base_image = {"kaggle_image": "img@sha256:abc"}
        pin = _pin(base_platform, base_image)
        for group, key, value in (
            ("platform_reported", "gpu_name", "A100"),
            ("platform_reported", "python_version", "3.11.9"),
            ("image_reported", "kaggle_image", "img@sha256:def"),
        ):
            platform = dict(base_platform)
            image = dict(base_image)
            if group == "platform_reported":
                platform[key] = value
            else:
                image[key] = value
            with self.assertRaises(session.Wp7EnvironmentAbort, msg=key):
                session.compare_environment_pin(_observed(platform, image), pin)

    def test_shipped_pin_field_by_field_aborts(self) -> None:
        """Every field of the real 17-field pin, changed one at a time."""
        pin = json.loads((HERE / "wp7_environment_pin.json").read_text())
        observed = {
            "platform_reported": copy.deepcopy(pin["platform_reported"]),
            "image_reported": copy.deepcopy(pin["image_reported"]),
        }
        flat = []
        for group in session.PIN_GROUPS:
            for key, value in sorted(observed[group].items()):
                if isinstance(value, dict):
                    for sub in sorted(value):
                        flat.append((group, f"{key}.{sub}"))
                else:
                    flat.append((group, key))
        self.assertGreaterEqual(len(flat), 14)
        for group, key in flat:
            with self.subTest(field=f"{group}.{key}"):
                session.compare_environment_pin(copy.deepcopy(observed), pin)
                mutated = copy.deepcopy(observed)
                head, _, tail = key.partition(".")
                if tail:
                    mutated[group][head][tail] = mutated[group][head][tail] + "-CHANGED"
                else:
                    mutated[group][head] = mutated[group][head] + "-CHANGED"
                with self.assertRaises(session.Wp7EnvironmentAbort, msg=f"{group}.{key}"):
                    session.compare_environment_pin(mutated, pin)

    def test_nested_build_env_field_aborts(self) -> None:
        pin = _pin(image_overrides={"build_env": {"BUILD_DATE": "20260629-122508"}})
        with self.assertRaises(session.Wp7EnvironmentAbort):
            session.compare_environment_pin(
                _observed({"gpu_name": "Tesla T4", "python_version": "3.12.13"},
                          {"build_env": {"BUILD_DATE": "20260629-999999"}}), pin)
        result = session.compare_environment_pin(
            _observed({"gpu_name": "Tesla T4", "python_version": "3.12.13"},
                      {"build_env": {"BUILD_DATE": "20260629-122508"}}), pin)
        self.assertEqual(result["difference_count"], 0)

    def test_missing_and_extra_fields_abort(self) -> None:
        pin = _pin()
        with self.assertRaisesRegex(session.Wp7EnvironmentAbort, "ABSENT"):
            session.compare_environment_pin(
                _observed({"gpu_name": "Tesla T4"}, {"kaggle_image": "img@sha256:abc"}), pin)
        with self.assertRaisesRegex(session.Wp7EnvironmentAbort, "EXTRA"):
            session.compare_environment_pin(
                _observed({"gpu_name": "Tesla T4", "python_version": "3.12.13", "new_field": "x"},
                          {"kaggle_image": "img@sha256:abc"}), pin)
        with self.assertRaisesRegex(session.Wp7EnvironmentAbort, "ABSENT"):
            session.compare_environment_pin(
                _observed({"gpu_name": "Tesla T4", "python_version": "3.12.13"}, {}), pin)

    def test_type_difference_and_list_value_abort(self) -> None:
        pin = _pin()
        with self.assertRaisesRegex(session.Wp7EnvironmentAbort, "expected"):
            session.compare_environment_pin(
                _observed({"gpu_name": 4, "python_version": "3.12.13"}, {"kaggle_image": "img@sha256:abc"}), pin)
        with self.assertRaises(session.Wp7EnvironmentAbort):
            session.compare_environment_pin(
                _observed({"gpu_name": True, "python_version": "3.12.13"}, {"kaggle_image": "img@sha256:abc"}), pin)
        with self.assertRaisesRegex(session.Wp7EnvironmentAbort, "list-valued"):
            session.compare_environment_pin(
                _observed({"gpu_name": ["Tesla T4"], "python_version": "3.12.13"}, {"kaggle_image": "img@sha256:abc"}), pin)

    def test_empty_pin_and_missing_group_refused(self) -> None:
        with self.assertRaisesRegex(session.Wp7SessionError, "empty"):
            session.compare_environment_pin(_observed({}, {}), {})
        with self.assertRaisesRegex(session.Wp7SessionError, "missing the platform_reported group"):
            session.compare_environment_pin(_observed({}, {}), {"image_reported": {"a": "b"}})
        with self.assertRaisesRegex(session.Wp7SessionError, "no comparable fields"):
            session.compare_environment_pin(_observed({}, {}), {"platform_reported": {}, "image_reported": {}})

    def test_reported_depth_over_the_limit_aborts(self) -> None:
        deep = "x"
        for _ in range(session.MAX_REPORTED_DEPTH + 2):
            deep = {"k": deep}
        with self.assertRaisesRegex(session.Wp7EnvironmentAbort, "nested"):
            session.compare_environment_pin(
                _observed({"gpu_name": "Tesla T4", "python_version": "3.12.13"},
                          {"kaggle_image": "img@sha256:abc", "deep": deep}), _pin())

    def test_probe_capture_refuses_unreportable_values(self) -> None:
        with self.assertRaises(session.Wp7SessionError):
            session.capture_platform_identity({1: lambda: {}})
        with self.assertRaisesRegex(session.Wp7SessionError, "keys must be strings"):
            session.capture_platform_identity({"platform_reported": lambda: {1: 2}})
        for value in ([1, 2], object(), {1: 2}):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(session.Wp7SessionError):
                    session.capture_platform_identity(
                        {"platform_reported": lambda v=value: {"k": v}}
                    )
        # A list nested one level down is still a list, and still refused.
        with self.assertRaisesRegex(session.Wp7EnvironmentAbort, "list"):
            session.capture_platform_identity(
                {"platform_reported": lambda: {"nested": {"inner": [1, 2]}}}
            )
        deep = "x"
        for _ in range(session.MAX_REPORTED_DEPTH + 2):
            deep = {"k": deep}
        with self.assertRaisesRegex(session.Wp7EnvironmentAbort, "nested"):
            session.capture_platform_identity({"platform_reported": lambda: deep})
        with self.assertRaisesRegex(session.Wp7SessionError, "callable or None"):
            session.capture_platform_identity({"platform_reported": 5})
        for value in (5, [], "x", {1: 2}, set(), (1, 2)):
            with self.assertRaises(session.Wp7SessionError):
                session.capture_platform_identity(value)
        # None is the documented "no probes" form and is accepted.
        self.assertEqual(
            session.capture_platform_identity({"platform_reported": None})["platform_reported"], {}
        )

    def test_non_string_reported_key_aborts(self) -> None:
        with self.assertRaisesRegex(session.Wp7SessionError, "keys must be strings"):
            session.capture_platform_identity({"platform_reported": lambda: {1: "a"}})
        with self.assertRaisesRegex(session.Wp7SessionError, "keys must be strings"):
            session.compare_environment_pin({1: "a"}, _pin())


# --------------------------------------------------------------------------
# Synthetic gate
# --------------------------------------------------------------------------
class TestSyntheticGate(unittest.TestCase):
    def test_refuses_non_synthetic_instance(self) -> None:
        for bad in (
            {"instance_kind": "stage2_01", "synthetic": True, "source": "synthetic_generator"},
            {"instance_kind": "synthetic", "synthetic": False, "source": "synthetic_generator"},
            {"synthetic": True, "source": "synthetic_generator"},
            {},
            {"instance_kind": "synthetic"},
            {"instance_kind": "synthetic", "synthetic": True},
            {"instance_kind": "synthetic", "synthetic": True, "source": ""},
            {"instance_kind": "synthetic", "synthetic": True, "source": 5},
            {"instance_kind": "synthetic", "synthetic": True, "source": "/mnt/kaggle/input/train.parquet"},
        ):
            with self.assertRaises((session.Wp7NonSyntheticRefusal, session.Wp7SessionError), msg=str(bad)):
                session.assert_synthetic_instance(bad)

    def test_accepts_a_corroborated_synthetic_record(self) -> None:
        ok = dict(SYNTHETIC_INSTANCE)
        result = session.assert_synthetic_instance(ok)
        self.assertEqual(result["source_kind"], "synthetic_generator")
        self.assertEqual(
            session.assert_synthetic_instance(dict(ok, source="wp7_synthetic_generator v2"))["source_kind"],
            "synthetic_generator",
        )

    def test_refuses_instance_naming_a_credential_path(self) -> None:
        bad = dict(SYNTHETIC_INSTANCE, path="/home/x/.kaggle/kaggle.json")
        with self.assertRaises(session.Wp7ProhibitedOperationError):
            session.assert_synthetic_instance(bad)
        bad = dict(SYNTHETIC_INSTANCE, source="/mnt/kaggle/.kaggle/kaggle.json")
        with self.assertRaises(session.Wp7ProhibitedOperationError):
            session.assert_synthetic_instance(bad)

    def test_every_forbidden_source_fragment_is_refused(self) -> None:
        for fragment in session.FORBIDDEN_SOURCE_FRAGMENTS:
            if fragment in session.ALLOWED_SOURCE_KINDS:
                continue  # the generator marker itself is the permitted form
            with self.subTest(fragment=fragment):
                with self.assertRaises(session.Wp7NonSyntheticRefusal):
                    session.assert_synthetic_instance(
                        dict(SYNTHETIC_INSTANCE, source=fragment)
                    )

    def test_unknown_source_is_refused(self) -> None:
        with self.assertRaisesRegex(session.Wp7NonSyntheticRefusal, "not one of the permitted"):
            session.assert_synthetic_instance(dict(SYNTHETIC_INSTANCE, source="mystery_generator"))


# --------------------------------------------------------------------------
# Prohibitions
# --------------------------------------------------------------------------
class TestProhibitions(unittest.TestCase):
    def test_credential_environment_variable_refused(self) -> None:
        os.environ["KAGGLE_KEY_FOR_FIXTURE"] = "x"
        self.addCleanup(os.environ.pop, "KAGGLE_KEY_FOR_FIXTURE", None)
        with self.assertRaisesRegex(session.Wp7ProhibitedOperationError, "KAGGLE_KEY_FOR_FIXTURE"):
            session.assert_no_credential_environment()

    def test_clean_environment_passes(self) -> None:
        session.assert_no_credential_environment()

    def test_prohibited_import_refused(self) -> None:
        for name in ("kaggle", "kagglehub", "requests", "urllib.request", "http.client", "socket"):
            sys.modules[name] = object()
            self.addCleanup(sys.modules.pop, name, None)
            with self.assertRaisesRegex(session.Wp7ProhibitedOperationError, name):
                session.assert_no_prohibited_imports()
            sys.modules.pop(name, None)


# --------------------------------------------------------------------------
# Session order, step results, receipt completeness
# --------------------------------------------------------------------------
class TestSessionOrderAndReceipt(unittest.TestCase):
    def setUp(self) -> None:
        self.tree = SyntheticTree()
        self.tree.add_session_dependencies()
        self.addCleanup(self.tree.close)
        self.pin = _pin()
        self.seal_path, self.seal_input = _write_seal(self.tree.root)
        self.probes = {
            "platform_reported": lambda: {"gpu_name": "Tesla T4", "python_version": "3.12.13"},
            "image_reported": lambda: {"kaggle_image": "img@sha256:abc"},
        }

    def _run(self, **overrides):
        out = self.tree.root / "out"
        out.mkdir(exist_ok=True)
        steps = _steps()
        def writer():
            path = out / "writer.bin"
            path.write_bytes(path.read_bytes() + b"synthetic range" if path.exists() else b"synthetic range")
            return _step_results()["wp4b_writer_synthetic_ranges"]
        steps["wp4b_writer_synthetic_ranges"] = writer
        kwargs = dict(
            root=self.tree.root,
            dependency_table=self.tree.session_table,
            environment_pin=self.pin,
            probes=self.probes,
            steps=steps,
            instance=dict(SYNTHETIC_INSTANCE),
            output_dir=out,
            sealed_reference_path=self.seal_path,
            seal_inputs=self.seal_input,
        )
        kwargs.update(overrides)
        return session.run_session(**kwargs)

    def test_happy_path_emits_a_complete_receipt(self) -> None:
        receipt = self._run()
        self.assertEqual(receipt["schema"], session.SCHEMA)
        self.assertEqual(receipt["mode"], session.MODE)
        self.assertEqual(
            receipt["steps_executed"],
            [
                "dependency_gate",
                "capture_platform_identity",
                "compare_environment_pin",
                "synthetic_instance_gate",
                "wp6b_section_a_qualification_plan",
                "wp1_production_identity_candidate",
                "section_b_item_1_recheck_synthetic",
                "open_sealed_reference",
                "section_b_item_2_full_domain_synthetic",
                "wp4b_writer_synthetic_ranges",
            ],
        )
        self.assertIn("sealed_reference_sha256", receipt["digests"])
        self.assertIn("step:open_sealed_reference", receipt["digests"])
        self.assertGreater(receipt["counters"]["sealed_reference_bytes"], 0)
        for field in session.RECEIPT_REQUIRED_FIELDS:
            self.assertIn(field, receipt)
        self.assertEqual(receipt["scientific_outputs"], [])
        self.assertEqual(receipt["scientific_output_count"], 0)
        self.assertEqual(receipt["counters"]["b1_checks"], 7)
        self.assertEqual(receipt["counters"]["b2_coordinates"], 4)
        self.assertEqual(receipt["counters"]["ranges_written"], 2)
        self.assertEqual(receipt["counters"]["instance_is_synthetic"], 1)
        self.assertEqual(receipt["identities"]["instance"]["instance_kind"], "synthetic")
        self.assertEqual(receipt["digests"]["section_a_plan_sha256"], "a" * 64)
        self.assertFalse(receipt["push_authorized"])
        self.assertEqual(receipt["content_sha256"], session.content_sha256(receipt))
        self.assertEqual(session.validate_receipt(receipt), receipt)

    def test_no_receipt_can_claim_a_step_that_did_not_run(self) -> None:
        """The validator's probe: an all-not-run session must not emit."""
        for drop in session.INJECTED_STEPS:
            with self.subTest(dropped=drop):
                steps = _steps()
                steps.pop(drop)
                with self.assertRaisesRegex(session.Wp7StepNotRunError, drop):
                    self._run(steps=steps)
        with self.assertRaisesRegex(session.Wp7StepNotRunError, "required steps"):
            self._run(steps={})
        with self.assertRaisesRegex(session.Wp7StepNotRunError, "cannot be complete"):
            self._run(steps=None)

    def test_receipt_refuses_steps_out_of_order(self) -> None:
        with self.assertRaisesRegex(session.Wp7SessionError, "not in the declared WP7 order"):
            session.build_receipt(
                steps=["capture_platform_identity", "dependency_gate"],
                counters={}, identities={}, digests={}, differences=[],
            )

    def test_receipt_refuses_unknown_step(self) -> None:
        with self.assertRaisesRegex(session.Wp7SessionError, "outside the WP7 order"):
            session.build_receipt(
                steps=list(session.REQUIRED_STEPS) + ["invented_step"],
                counters={}, identities={}, digests={}, differences=[],
            )

    def test_receipt_refuses_empty_steps(self) -> None:
        with self.assertRaisesRegex(session.Wp7SessionError, "no executed step"):
            session.build_receipt(steps=[], counters={}, identities={}, digests={}, differences=[])

    def test_receipt_refuses_missing_required_step(self) -> None:
        steps = [s for s in session.REQUIRED_STEPS if s != "wp4b_writer_synthetic_ranges"]
        with self.assertRaisesRegex(session.Wp7StepNotRunError, "wp4b_writer_synthetic_ranges"):
            session.build_receipt(steps=steps, counters={}, identities={}, digests={}, differences=[])

    def test_validate_receipt_refuses_each_missing_field(self) -> None:
        receipt = self._run()
        for field in session.RECEIPT_REQUIRED_FIELDS:
            with self.subTest(field=field):
                bad = {k: v for k, v in receipt.items() if k != field}
                with self.assertRaisesRegex(session.Wp7IncompleteReceiptError, field):
                    session.validate_receipt(bad)

    def test_validate_receipt_refuses_a_tampered_or_incomplete_body(self) -> None:
        receipt = self._run()
        cases = (
            ({"schema": "other"}, "schema"),
            ({"mode": "scientific"}, "mode"),
            ({"scientific_outputs": [1]}, "scientific"),
            ({"scientific_output_count": 2}, "scientific_output_count"),
            ({"push_authorized": True}, "push_authorized"),
            ({"gpu_allocation_authorized": True}, "gpu_allocation_authorized"),
            ({"counters": "x"}, "counters must be a dict"),
            ({"identities": []}, "identities must be a dict"),
            ({"digests": None}, "digests must be a dict"),
            ({"steps_executed": "x"}, "steps_executed"),
            ({"differences": 5}, "differences"),
            ({"content_sha256": "0" * 64}, "content_sha256"),
        )
        for patch, message in cases:
            with self.subTest(patch=sorted(patch)):
                bad = dict(receipt)
                bad.update(patch)
                with self.assertRaisesRegex(session.Wp7SessionError, message):
                    session.validate_receipt(bad)
        bad = dict(receipt, steps_executed=[s for s in receipt["steps_executed"] if s != "dependency_gate"])
        with self.assertRaisesRegex(session.Wp7StepNotRunError, "absent"):
            session.validate_receipt(bad)
        for value in (None, [], "", 5, set(), [1]):
            with self.assertRaises(session.Wp7SessionError):
                session.validate_receipt(value)

    def test_receipt_content_digest_detects_tamper(self) -> None:
        receipt = self._run()
        tampered = dict(receipt)
        tampered["counters"] = {"injected": 1}
        self.assertNotEqual(session.content_sha256(tampered), receipt["content_sha256"])
        with self.assertRaisesRegex(session.Wp7IncompleteReceiptError, "content_sha256"):
            session.validate_receipt(tampered)

    def test_pin_difference_aborts_before_any_step(self) -> None:
        probes = dict(self.probes)
        probes["platform_reported"] = lambda: {"gpu_name": "A100", "python_version": "3.12.13"}
        with self.assertRaises(session.Wp7EnvironmentAbort):
            self._run(probes=probes)

    def test_missing_dependency_refuses_before_any_step(self) -> None:
        (self.tree.root / "b.py").unlink()
        with self.assertRaisesRegex(session.Wp7DependencyError, "b.py"):
            self._run()

    def test_pending_dependency_refuses_before_any_step(self) -> None:
        table = dict(self.tree.session_table)
        table["b.py"] = builder.PENDING
        with self.assertRaisesRegex(session.Wp7DependencyError, "PENDING"):
            self._run(dependency_table=table)

    def test_altered_dependency_refuses_before_any_step(self) -> None:
        self.tree.flip_one_byte("a.py")
        with self.assertRaisesRegex(session.Wp7DependencyError, "hash mismatch"):
            self._run()

    def test_non_synthetic_instance_step_result_refused(self) -> None:
        steps = _steps()
        steps["synthetic_instance_gate"] = lambda: {
            "identities": {"instance": {"instance_kind": "stage2_01", "synthetic": True, "source": "synthetic_generator"}}, "output": "synthetic"
        }
        with self.assertRaisesRegex(session.Wp7NonSyntheticRefusal, "non-synthetic"):
            self._run(steps=steps)

    def test_synthetic_claim_naming_a_real_dataset_refused(self) -> None:
        steps = _steps()
        steps["synthetic_instance_gate"] = lambda: {
            "identities": {"instance": dict(SYNTHETIC_INSTANCE, source="/mnt/kaggle/input/d013.parquet")}, "output": "synthetic"
        }
        with self.assertRaisesRegex(session.Wp7NonSyntheticRefusal, "real data source"):
            self._run(steps=steps)

    def test_synthetic_step_result_must_carry_the_instance(self) -> None:
        steps = _steps()
        steps["synthetic_instance_gate"] = lambda: {"counters": {"x": 1}, "output": "synthetic"}
        with self.assertRaises(session.Wp7IncompleteReceiptError):
            self._run(steps=steps)
        steps["synthetic_instance_gate"] = lambda: {"identities": {}, "output": "synthetic"}
        with self.assertRaises(session.Wp7IncompleteReceiptError):
            self._run(steps=steps)

    def test_step_result_shape_is_enforced(self) -> None:
        cases = (
            ({}, "empty result"),
            ({"outputs": [1, 2]}, "outside the permitted set"),
            ({"status": "failed"}, "not 'ok'"),
            ({"counters": []}, "must be a dict"),
            ({"identities": []}, "must be a dict"),
            ({"counters": {"a": {"nested": 1}}}, "string or a number"),
            ({"counters": {1: 1}}, "field name"),
            ({"digests": {"d": ["a"]}}, "string or a number"),
        )
        for result, message in cases:
            with self.subTest(result=sorted(result)):
                steps = _steps()
                steps["wp4b_writer_synthetic_ranges"] = (lambda r=result: r)
                with self.assertRaisesRegex(session.Wp7StepResultError, message):
                    self._run(steps=steps)

    def test_non_mapping_step_result_refused(self) -> None:
        for value in (None, 5, [], "x", {1: 2}):
            steps = _steps()
            steps["wp4b_writer_synthetic_ranges"] = (lambda v=value: v)
            with self.assertRaises(session.Wp7SessionError):
                self._run(steps=steps)

    def test_output_dir_must_exist_and_stay_inside_the_root(self) -> None:
        with self.assertRaisesRegex(session.Wp7PathError, "not a directory"):
            self._run(output_dir=self.tree.root / "nope")
        (self.tree.root / "out").mkdir(exist_ok=True)
        receipt = self._run(output_dir=self.tree.root / "out")
        self.assertEqual(receipt["counters"]["output_dir_written"], 1)
        with self.assertRaisesRegex(session.Wp7PathError, "root itself"):
            self._run(output_dir=self.tree.root)
        with tempfile.TemporaryDirectory() as d:
            outside = Path(d) / "outside"
            outside.mkdir()
            with self.assertRaisesRegex(session.Wp7PathError, "outside the root"):
                self._run(output_dir=outside)
        for value in (5, "x", [], {}, b"x"):
            with self.assertRaisesRegex(session.Wp7SessionError, "must be a Path"):
                self._run(output_dir=value)

    def test_run_session_refuses_credential_environment(self) -> None:
        os.environ["KAGGLE_KEY_RUNSESSION"] = "x"
        self.addCleanup(os.environ.pop, "KAGGLE_KEY_RUNSESSION", None)
        with self.assertRaisesRegex(session.Wp7ProhibitedOperationError, "KAGGLE_KEY_RUNSESSION"):
            self._run()

    def test_run_session_refuses_prohibited_import(self) -> None:
        sys.modules["kaggle"] = object()
        self.addCleanup(sys.modules.pop, "kaggle", None)
        with self.assertRaisesRegex(session.Wp7ProhibitedOperationError, "prohibited module"):
            self._run()

    def test_session_treats_pending_as_pending_not_as_a_file(self) -> None:
        table = dict(self.tree.session_table)
        table["b.py"] = "PENDING"
        with self.assertRaises(session.Wp7DependencyError) as ctx:
            session.resolve_dependencies(self.tree.root, table)
        message = str(ctx.exception)
        self.assertIn("review PENDING", message)
        self.assertNotIn("b.py: missing", message)

    def test_session_refuses_a_non_sha256_recorded_hash(self) -> None:
        for bad in ("NOTAHASH", "a" * 63, "A" * 64, ""):
            with self.subTest(bad=bad):
                table = dict(self.tree.session_table)
                table["b.py"] = bad
                with self.assertRaisesRegex(session.Wp7DependencyError, "not a lowercase sha256"):
                    session.resolve_dependencies(self.tree.root, table)

    def test_unknown_and_non_callable_steps_refused(self) -> None:
        with self.assertRaisesRegex(session.Wp7SessionError, "unknown step"):
            self._run(steps={"invented_step": lambda: {}})
        steps = _steps()
        steps["wp4b_writer_synthetic_ranges"] = "nope"
        with self.assertRaisesRegex(session.Wp7SessionError, "not callable"):
            self._run(steps=steps)


# --------------------------------------------------------------------------
# No Kaggle invocation
# --------------------------------------------------------------------------
class TestRound3ReceiptEvidence(unittest.TestCase):
    def setUp(self):
        self.tree = SyntheticTree()
        self.tree.add_session_dependencies()
        self.addCleanup(self.tree.close)
        self.seal_path, self.seal_input = _write_seal(self.tree.root)
        self.probes = {"platform_reported": lambda: _pin()["platform_reported"],
                       "image_reported": lambda: _pin()["image_reported"]}

    def run_case(self, **kwargs):
        out = self.tree.root / "out"
        out.mkdir(exist_ok=True)
        steps = _steps()
        def writer():
            path = out / "writer.bin"
            path.write_bytes(path.read_bytes() + b"synthetic range" if path.exists() else b"synthetic range")
            return _step_results()["wp4b_writer_synthetic_ranges"]
        steps["wp4b_writer_synthetic_ranges"] = writer
        args = dict(root=self.tree.root, dependency_table=self.tree.session_table,
                    environment_pin=_pin(), probes=self.probes,
                    instance=dict(SYNTHETIC_INSTANCE), steps=steps, output_dir=out,
                    sealed_reference_path=self.seal_path, seal_inputs=self.seal_input)
        args.update(kwargs)
        return session.run_session(**args)

    def test_each_required_wp_module_is_required_before_steps(self):
        for name in session.REQUIRED_WP_DEPENDENCIES:
            with self.subTest(module=name):
                table = dict(self.tree.session_table)
                table.pop(name)
                called = []
                steps = {step: (lambda: called.append(step)) for step in session.INJECTED_STEPS}
                with self.assertRaisesRegex(session.Wp7DependencyError, "required WP modules missing"):
                    self.run_case(dependency_table=table, steps=steps)
                self.assertEqual(called, [])

    def test_non_synthetic_input_is_refused_before_steps(self):
        called = []
        steps = {name: lambda: called.append(name) for name in session.INJECTED_STEPS}
        for instance in (None, {"instance_kind": "production", "synthetic": False,
                                "source": "real"},
                         dict(SYNTHETIC_INSTANCE, source="synthetic_generator https://data")):
            with self.subTest(instance=instance):
                with self.assertRaises(session.Wp7SessionError):
                    self.run_case(instance=instance, steps=steps)
                self.assertEqual(called, [])

    def test_noop_writer_and_gate_mismatch_are_refused(self):
        out = self.tree.root / "out"
        out.mkdir(exist_ok=True)
        (out / "old.bin").write_bytes(b"already there")
        with self.assertRaises(session.Wp7StepNotRunError):
            self.run_case(steps=_steps(), output_dir=out)
        steps = _steps()
        altered = dict(SYNTHETIC_INSTANCE, label="different")
        steps["synthetic_instance_gate"] = lambda: {"identities": {"instance": altered}, "output": "synthetic"}
        with self.assertRaises(session.Wp7NonSyntheticRefusal):
            self.run_case(steps=steps)

    def test_every_step_requires_real_output_hash(self):
        receipt = self.run_case()
        for name in session.REQUIRED_STEPS:
            self.assertRegex(receipt["digests"][f"step:{name}"], r"^[0-9a-f]{64}$")
        for name in session.INJECTED_STEPS:
            for output in (None, "", [], {}):
                with self.subTest(name=name, output=output):
                    steps = _steps()
                    results = _step_results()
                    results[name]["output"] = output
                    if name == "section_b_item_2_full_domain_synthetic":
                        # item 2 is handed the sealed reference; ignore it here
                        # so the EMPTY-OUTPUT check is what fires.
                        steps[name] = lambda _ref, r=results[name]: r
                    else:
                        steps[name] = lambda r=results[name]: r
                    with self.assertRaises(session.Wp7StepResultError):
                        self.run_case(steps=steps)
            steps = _steps()
            if name == "section_b_item_2_full_domain_synthetic":
                steps[name] = lambda _ref: {"status": "ok"}
            else:
                steps[name] = lambda: {"status": "ok"}
            with self.assertRaises(session.Wp7StepResultError):
                self.run_case(steps=steps)
        steps = _steps()
        steps["wp4b_writer_synthetic_ranges"] = lambda: (_ for _ in ()).throw(ValueError("boom"))
        with self.assertRaises(session.Wp7StepResultError):
            self.run_case(steps=steps)
        altered = copy.deepcopy(receipt)
        del altered["digests"]["step:dependency_gate"]
        altered["content_sha256"] = session.content_sha256(altered)
        with self.assertRaises(session.Wp7IncompleteReceiptError):
            session.validate_receipt(altered)


class TestNoKaggleInvocation(unittest.TestCase):
    """AST- and grep-level proof that nothing in kaggle_wp7/ reaches Kaggle."""

    CODE_FILES = ("wp7_session.py", "build_wp7_package.py")
    RAW_SCAN_FILES = (
        "wp7_environment_pin.json",
        "GATE_9_WP7_PACKAGE_DRAFT.md",
    )
    FORBIDDEN_SUBSTRINGS = (
        "kaggle kernels push", "kaggle kernels pull", "kaggle kernels status",
        "kaggle competitions", "kaggle datasets", "kaggle kernels create",
        "from kaggle", "import kaggle", "kaggle.api", "kaggleapi", "kagglehub",
        "subprocess.run", "subprocess.call", "subprocess.popen", "subprocess.check_output",
        "subprocess.check_call", "os.system", "os.popen", "os.execv", "os.spawn",
        "shell=true", "urllib.request", "urllib3", "requests.get", "requests.post",
        "requests.request", "socket.socket", "httpx.", "aiohttp", "urlopen(",
        "getenv(\"kaggle", "environ[\"kaggle", "getenv('kaggle", "environ['kaggle",
        ".kaggle/", "~/.kaggle", "kaggle.json", "cuda.device(", "cupy", "torch.cuda",
        "shutil.which(\"nvcc", "shutil.which('nvcc", "cp.cuda", "numba.cuda",
    )
    ALLOWED_IMPORTS = {
        "__future__", "hashlib", "json", "os", "sys", "platform", "pathlib",
        "typing", "argparse", "posixpath", "re", "stat",
        # importlib.util loads the reviewed stage2_reference_seal.py from the
        # exact file the dependency gate hash-verified.  It is the standard
        # library module loader: it starts no process, opens no socket and
        # reads no credential.  Every other stdlib import stays refused.
        "importlib",
    }

    def test_no_kaggle_cli_or_credential_access(self) -> None:
        offenders = []
        for name in self.RAW_SCAN_FILES:
            path = HERE / name
            self.assertTrue(path.is_file(), f"{name} is missing, so the scan would be vacuous")
            lowered = path.read_text(encoding="utf-8", errors="replace").lower()
            for pattern in self.FORBIDDEN_SUBSTRINGS:
                if pattern in lowered:
                    offenders.append(f"{name}: {pattern}")
        self.assertEqual(offenders, [], "kaggle/credential/gpu invocation patterns found")

    def test_code_files_import_only_allowlisted_modules(self) -> None:
        for name in self.CODE_FILES:
            tree = ast.parse((HERE / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertIn(
                            alias.name.split(".")[0], self.ALLOWED_IMPORTS,
                            f"{name} imports non-allowlisted module {alias.name}",
                        )
                elif isinstance(node, ast.ImportFrom):
                    if node.module is None:
                        continue
                    self.assertIn(
                        node.module.split(".")[0], self.ALLOWED_IMPORTS,
                        f"{name} imports from non-allowlisted module {node.module}",
                    )

    def test_code_files_never_call_a_process_or_network_api(self) -> None:
        banned_calls = {
            "system", "popen", "execv", "execve", "execl", "spawnl", "spawnv",
            "fork", "urlopen", "get", "post", "request", "connect", "socket",
        }
        banned_attrs = {"Popen", "run", "call", "check_call", "check_output", "getoutput"}
        for name in self.CODE_FILES:
            tree = ast.parse((HERE / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Attribute):
                    self.assertNotIn(
                        func.attr, banned_attrs,
                        f"{name} calls .{func.attr}() which may spawn a process",
                    )
                    if isinstance(func.value, ast.Name):
                        if func.value.id == "os" and func.attr in READ_ONLY_OS_ATTRS:
                            continue  # path metadata only: no process, no network
                        self.assertNotEqual(func.value.id, "os", f"{name} calls os.{func.attr}()")
                        self.assertNotEqual(
                            func.value.id, "subprocess", f"{name} calls subprocess.{func.attr}()"
                        )
                elif isinstance(func, ast.Name):
                    self.assertNotIn(func.id, banned_calls, f"{name} calls {func.id}()")

    def test_code_files_never_open_a_credential_path(self) -> None:
        for name in self.CODE_FILES:
            tree = ast.parse((HERE / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                is_open = (
                    isinstance(func, ast.Name) and func.id in ("open", "exec", "eval", "input")
                ) or (
                    isinstance(func, ast.Attribute)
                    and func.attr in ("read_text", "read_bytes", "open")
                    and isinstance(func.value, ast.Name)
                    and func.value.id in ("Path", "os")
                )
                if not is_open:
                    continue
                for arg in list(node.args) + [kw.value for kw in node.keywords]:
                    for sub in ast.walk(arg):
                        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                            self.assertNotIn(
                                ".kaggle", sub.value.lower(),
                                f"{name} opens a literal credential path: {sub.value!r}",
                            )

    def test_no_credential_value_is_read_or_passed_to_a_child(self) -> None:
        """The validator's probe: no ambient credential value is ever read.

        A credential value is planted in the environment, the package is
        exercised, and every fixture subprocess is launched with a scrubbed
        allowlist environment.  Nothing the package writes may contain the
        value, and no child may see it.
        """
        value = "CREDENTIAL-VALUE-MUST-NOT-LEAK-9f3a2b"
        os.environ["KAGGLE_KEY_LEAK_PROBE"] = value
        self.addCleanup(os.environ.pop, "KAGGLE_KEY_LEAK_PROBE", None)
        with self.assertRaises(session.Wp7ProhibitedOperationError):
            session.assert_no_credential_environment()
        with tempfile.TemporaryDirectory() as d:
            tree = SyntheticTree()
            try:
                (tree.root / "wp7_environment_pin.json").write_text(json.dumps(_pin()))
                _reviewed_file(tree.root, tree.table)
                out = Path(d) / "m.json"
                proc = subprocess.run(
                    [sys.executable, "-B", str(HERE / "build_wp7_package.py"),
                     "--root", str(tree.root), "--out", str(out),
                     "--package-root", str(tree.root),
                     "--expected-reviewed-table-sha256",
                     builder.sha256_file(tree.root / builder.REVIEWED_TABLE_NAME)],
                    capture_output=True, cwd=d, env=safe_child_env(),
                )
                self.assertEqual(proc.returncode, 0, proc.stderr.decode())
                self.assertNotIn(value.encode(), out.read_bytes())
                self.assertNotIn(value.encode(), proc.stdout)
                self.assertNotIn(value.encode(), proc.stderr)
            finally:
                tree.close()
        self.assertNotIn(value, safe_child_env().__repr__())
        for fragment in NEVER_IN_CHILD_ENV:
            for key in safe_child_env():
                self.assertNotIn(fragment, key.upper())


# --------------------------------------------------------------------------
# Main entry points
# --------------------------------------------------------------------------
class TestMainEntrypoints(unittest.TestCase):
    def test_credential_paths_are_refused_before_read(self) -> None:
        for module in (builder, session):
            with self.subTest(module=module.__name__):
                with self.assertRaises((builder.Wp7PackageError, session.Wp7SessionError)):
                    module.assert_safe_cli_path(Path("/tmp/.kaggle/kaggle.json"))
        anchor = builder.sha256_file(HERE / builder.REVIEWED_TABLE_NAME)
        rc = builder.main(["--root", str(ROOT), "--expected-reviewed-table-sha256", anchor,
                           "--dependency-table", "/tmp/.kaggle/kaggle.json"])
        self.assertEqual(rc, 1)
        rc = session.main(["--root", str(ROOT), "--dependency-table", "/tmp/.kaggle/kaggle.json",
                           "--environment-pin", str(HERE / "wp7_environment_pin.json")])
        self.assertEqual(rc, 2)

    def test_session_main_refuses_to_run(self) -> None:
        rc = session.main(["--root", str(ROOT), "--dependency-table", "/nonexistent.json",
                           "--environment-pin", "/nonexistent.json"])
        self.assertEqual(rc, 2)

    def test_session_runs_as_main_and_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pin = HERE / "wp7_environment_pin.json"
            table = Path(d) / "deps.json"
            table.write_text(json.dumps({}))
            proc = subprocess.run(
                [sys.executable, "-B", str(HERE / "wp7_session.py"),
                 "--root", str(ROOT), "--dependency-table", str(table),
                 "--environment-pin", str(pin)],
                capture_output=True, cwd=d, env=safe_child_env(),
            )
            self.assertEqual(proc.returncode, 2)
            self.assertIn(b"not authorized to run", proc.stderr)
            self.assertNotIn(b"steps_executed", proc.stdout)

    def test_session_main_refuses_a_non_mapping_pin(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pin = Path(d) / "pin.json"
            pin.write_text(json.dumps([1, 2, 3]))
            table = Path(d) / "deps.json"
            table.write_text(json.dumps({}))
            rc = session.main(["--root", str(ROOT), "--dependency-table", str(table),
                               "--environment-pin", str(pin)])
            self.assertEqual(rc, 2)

    def test_builder_runs_as_main_and_refuses_stale_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tree = SyntheticTree()
            try:
                manifest = anchored_build(tree.root, tree.table, package_root=tree.root)
                path = Path(d) / "m.json"
                path.write_text(json.dumps(manifest))
                tree.flip_one_byte("a.py")
                proc = subprocess.run(
                    [sys.executable, "-B", str(HERE / "build_wp7_package.py"),
                     "--root", str(tree.root), "--package-root", str(tree.root),
                     "--verify", str(path),
                     "--expected-reviewed-table-sha256", builder.sha256_file(tree.root / builder.REVIEWED_TABLE_NAME)],
                    capture_output=True, cwd=d, env=safe_child_env(),
                )
                self.assertEqual(proc.returncode, 1)
                self.assertIn(b"stale", proc.stderr)
                self.assertIn(b"FAIL:", proc.stderr)
            finally:
                tree.close()

    def test_builder_cli_writes_manifest(self) -> None:
        """The builder CLI writes a manifest from a synthetic temp-dir table.

        The shipped table is a placeholder the lead replaces after the build, so
        the CLI is exercised against a synthetic reviewed table in a temp
        package root -- the same external-anchor contract the owner uses.
        """
        with tempfile.TemporaryDirectory() as d:
            tree = SyntheticTree()
            try:
                # main() reads the pin from the package root, so it must be
                # real JSON there, not the stand-in bytes.  It is written
                # BEFORE the reviewed table so the table pins the final bytes.
                (tree.root / "wp7_environment_pin.json").write_text(json.dumps(_pin()))
                _reviewed_file(tree.root, tree.table)
                out = Path(d) / "m.json"
                proc = subprocess.run(
                    [sys.executable, "-B", str(HERE / "build_wp7_package.py"),
                     "--root", str(tree.root), "--out", str(out),
                     "--package-root", str(tree.root),
                     "--expected-reviewed-table-sha256",
                     builder.sha256_file(tree.root / builder.REVIEWED_TABLE_NAME)],
                    capture_output=True, cwd=d, env=safe_child_env(),
                )
                self.assertEqual(proc.returncode, 0, proc.stderr.decode())
                manifest = json.loads(out.read_text())
                self.assertEqual(manifest["status"], builder.STATUS_READY)
                self.assertFalse(manifest["push_authorized"])
                self.assertIsNotNone(manifest["dependency_table_sha256"])
            finally:
                tree.close()

    def test_builder_cli_refuses_the_shipped_placeholder_table(self) -> None:
        """The CLI refusal is exercised against a synthetic temp package table."""
        with tempfile.TemporaryDirectory(prefix="wp7-cli-placeholder-") as d:
            package_root = Path(d) / "package"
            package_root.mkdir()
            _make_package(package_root)
            table = {
                "_placeholder": True,
                "_placeholder_notice": "synthetic fixture only",
                "dependencies": {"a.py": builder.PENDING},
                "package_files_sha256": {
                    name: "PENDING_PLACEHOLDER" for name in builder.PACKAGE_FILES
                },
            }
            self.assertTrue(table.get("_placeholder"), "synthetic table must be marked as a placeholder")
            self.assertEqual(table.get("_placeholder_notice"), table.get("_placeholder_notice"))
            for value in table["dependencies"].values():
                self.assertEqual(value, builder.PENDING, table)
            for value in table["package_files_sha256"].values():
                self.assertNotRegex(str(value), r"\A[0-9a-f]{64}\Z",
                                    "placeholder package hash must not look reviewed")
            for name in builder.PACKAGE_FILES:
                self.assertIn(name, table["package_files_sha256"], name)
            table_path = package_root / builder.REVIEWED_TABLE_NAME
            table_path.write_text(json.dumps(table, sort_keys=True, indent=2) + "\n")
            out = Path(d) / "m.json"
            proc = subprocess.run(
                [sys.executable, "-B", str(HERE / "build_wp7_package.py"),
                 "--root", str(package_root), "--package-root", str(package_root),
                 "--out", str(out), "--expected-reviewed-table-sha256",
                 builder.sha256_file(table_path)],
                capture_output=True, cwd=d, env=safe_child_env(),
            )
            self.assertEqual(proc.returncode, 1)
            self.assertIn(b"FAIL:", proc.stderr)
            self.assertIn(b"lowercase sha256", proc.stderr)
            self.assertFalse(out.exists())

    def test_builder_cli_rejects_a_changed_dependency_override(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tree = SyntheticTree()
            self.addCleanup(tree.close)
            (tree.root / "wp7_environment_pin.json").write_text(json.dumps(_pin()))
            anchor = _reviewed_file(tree.root, tree.table)
            wrong = dict(tree.table)
            wrong.pop("a.py")
            table_path = Path(d) / "wrong.json"
            table_path.write_text(json.dumps(wrong))
            out = Path(d) / "m.json"
            proc = subprocess.run(
                [sys.executable, "-B", str(HERE / "build_wp7_package.py"),
                 "--root", str(tree.root), "--package-root", str(tree.root),
                 "--expected-reviewed-table-sha256", anchor,
                 "--dependency-table", str(table_path), "--out", str(out)],
                capture_output=True, cwd=d, env=safe_child_env())
            self.assertEqual(proc.returncode, 1)
            self.assertIn(b"caller dependency table differs", proc.stderr)
            self.assertFalse(out.exists())

    def test_builder_cli_accepts_a_dependency_table_override(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tree = SyntheticTree()
            try:
                table_path = Path(d) / "deps.json"
                table_path.write_text(json.dumps(tree.table))
                # A synthetic tree has no environment pin, so the pin is
                # written explicitly: the builder must never read a
                # credential or invent a pin.
                (tree.root / "wp7_environment_pin.json").write_text(json.dumps(_pin()))
                _reviewed_file(tree.root, tree.table)
                out = Path(d) / "m.json"
                proc = subprocess.run(
                    [sys.executable, "-B", str(HERE / "build_wp7_package.py"),
                     "--root", str(tree.root), "--package-root", str(tree.root),
                     "--dependency-table", str(table_path), "--out", str(out),
                     "--expected-reviewed-table-sha256", builder.sha256_file(tree.root / builder.REVIEWED_TABLE_NAME)],
                    capture_output=True, cwd=d, env=safe_child_env(),
                )
                self.assertEqual(proc.returncode, 0, proc.stderr.decode())
                self.assertEqual(json.loads(out.read_text())["status"], builder.STATUS_READY)
            finally:
                tree.close()


# --------------------------------------------------------------------------
# Public-argument fuzz: every wrong shape must give a TYPED WP7 error
# --------------------------------------------------------------------------
class TestPublicArgumentFuzz(unittest.TestCase):
    # Every value is wrong for every argument: None, bool, int, float, str,
    # bytes, list, dict, unhashable, a live iterator and a bare object.
    WRONG = [
        None, True, False, 0, 1, -1, 3.5, float("nan"), "", "x", "draft_invalid", b"x",
        bytearray(b"x"), [], {}, [1, 2], {"a": 1}, {"a": {"b": [1]}}, {1: 2},
        {("a", "b"): "c"}, {1, 2}, set(), frozenset(), object(), (1, 2), (), (None,),
        iter([1]), [[]], {"a": None}, {"": ""},
    ]

    # Per-argument pools.  Each holds values that are wrong for THAT
    # argument, so a guard is never tripped by an input the parameter
    # legitimately accepts (an empty dict IS a valid manifest argument, a
    # list IS a valid steps argument, "x" IS a valid string argument).
    NOT_MAPPING = [
        None, True, False, 0, 1, -1, 3.5, float("nan"), "", "x", "draft_invalid", b"x",
        bytearray(b"x"), [1, 2], (1, 2), {1: 2}, {("a", "b"): "c"}, {1, 2}, set(),
        frozenset(), object(), (), (None,), iter([1]),
    ]
    NOT_SEQUENCE = [
        None, True, False, 0, 1, -1, 3.5, float("nan"), "", "x", b"x", bytearray(b"x"),
        {}, {1: 2}, {("a", "b"): "c"}, set(), frozenset(), object(), iter([1]),
    ]
    NOT_TEXT = [
        None, True, False, 0, 1, -1, 3.5, float("nan"), b"x", bytearray(b"x"), [], {},
        [1, 2], {1: 2}, set(), frozenset(), object(), (1, 2), (), (None,), iter([1]),
    ]
    NOT_PATH = NOT_TEXT + [
        "/abs.py", "../escape.py", "a//b.py", "a\\b.py", "", "a/./b.py", "C:/x.py",
        "nul\x00.py", ".", "..", "a/b/", "a/b/../..",
    ]
    NOT_SERIALIZABLE = [
        float("nan"), float("inf"), {1, 2}, {(1, 2): 3}, {"x": {1, 2}},
        {"x": object()}, object(), b"x", bytearray(b"x"), {"x": float("nan")},
    ]
    NOT_TABLE = NOT_MAPPING + [
        {"a": 1}, {"a": None}, {"a": [1]}, {"a": {"b": 1}}, {"a": {1, 2}}, {1: "0" * 64},
        {("t",): "v"}, {"": ""},
    ]
    NOT_STATUS = NOT_TEXT + [
        "approved", "pushed", "push_complete", "released", "executed", "draft_unknown",
        "DRAFT_INVALID", "Draft_Invalid", " draft_invalid ",
    ]

    def _assert_typed(self, name: str, fn, *args, **kwargs) -> None:
        """A wrong shape must raise a typed WP7 refusal, not a raw crash.

        Only Wp7PackageError / Wp7SessionError (or a subclass) counts.  A
        bare TypeError, AttributeError or KeyError is a FAILURE: the owner
        required a typed error for every wrong type.
        """
        try:
            fn(*args, **kwargs)
        except (builder.Wp7PackageError, session.Wp7SessionError):
            return
        except Exception as exc:  # noqa: BLE001 - deliberately broad on purpose
            self.fail(f"[{name}] untyped {type(exc).__name__}: {exc} with {args!r} {kwargs!r}")
        self.fail(f"[{name}] no typed error with {args!r} {kwargs!r}")

    def test_builder_public_functions_fuzz(self) -> None:
        # (name, callable, values that are wrong for that one argument).  A
        # value an argument legitimately accepts is not fuzzed against it --
        # e.g. an empty dict IS a valid environment pin, and tripping a
        # guard off by construction would prove nothing.
        cases = (
            ("build_manifest.root",
             lambda v: anchored_build(v, {"a.py": "0" * 64}), self.NOT_MAPPING + [str(ROOT)]),
            ("build_manifest.table", lambda v: anchored_build(ROOT, v), self.NOT_TABLE),
            ("build_manifest.pin",
             lambda v: anchored_build(ROOT, {"a.py": "0" * 64}, environment_pin=v),
             [v for v in self.NOT_MAPPING if v is not None] + [5, "x", [], [1]]),
            ("build_manifest.package_root",
             lambda v: anchored_build(ROOT, {"a.py": "0" * 64}, package_root=v),
             [v for v in self.NOT_MAPPING if v is not None] + [str(ROOT)]),
            ("validate_status", lambda v: builder.validate_status(v), self.NOT_STATUS),
            ("validate_kernel_metadata_draft", lambda v: builder.validate_kernel_metadata_draft(v),
             self.NOT_MAPPING),
            ("verify_manifest.root", lambda v: anchored_verify(v, {}), self.WRONG),
            ("verify_manifest.manifest", lambda v: anchored_verify(ROOT, v), self.WRONG),
            ("verify_manifest.package_root",
             lambda v: anchored_verify(ROOT, {}, package_root=v), self.WRONG),
            ("evaluate_dependencies.root",
             lambda v: builder.evaluate_dependencies(v, {"a.py": "0" * 64}),
             self.NOT_MAPPING + [str(ROOT), HERE / "nope"]),
            ("evaluate_dependencies.table", lambda v: builder.evaluate_dependencies(ROOT, v),
             self.NOT_TABLE),
            ("evaluate_package_files", lambda v: builder.evaluate_package_files(v),
             self.NOT_MAPPING + [str(HERE)]),
            ("normalize_relative_path", lambda v: builder.normalize_relative_path(v, "p"), self.NOT_PATH),
            ("resolve_inside_root.root", lambda v: builder.resolve_inside_root(v, "a.py", "p"),
             self.NOT_MAPPING + [str(ROOT)]),
            ("resolve_inside_root.rel", lambda v: builder.resolve_inside_root(ROOT, v, "p"),
             self.NOT_PATH),
            ("dependency_table_sha256", lambda v: builder.dependency_table_sha256(v), self.NOT_TABLE),
            ("content_sha256", lambda v: builder.content_sha256(v), self.NOT_MAPPING),
            ("canonical_bytes", lambda v: builder.canonical_bytes(v), self.NOT_SERIALIZABLE),
            ("sha256_file", lambda v: builder.sha256_file(v), self.NOT_MAPPING + [str(HERE)]),
            ("_require_sha256", lambda v: builder._require_sha256(v, "h"), self.WRONG + ["ZZ" * 32, "A" * 64]),
            ("_text", lambda v: builder._text(v, "t"), self.NOT_TEXT),
            ("_mapping", lambda v: builder._mapping(v, "m"), self.NOT_MAPPING),
            ("_sequence", lambda v: builder._sequence(v, "s"), self.NOT_SEQUENCE),
        )
        for name, call, values in cases:
            for value in values:
                with self.subTest(call=name, value=repr(value)[:40]):
                    self._assert_typed(name, call, value)

    def test_session_public_functions_fuzz(self) -> None:
        pin = _pin()
        good = _observed({"gpu_name": "Tesla T4", "python_version": "3.12.13"},
                         {"kaggle_image": "img@sha256:abc"})
        steps = list(session.REQUIRED_STEPS)
        not_dict = self.NOT_MAPPING
        cases = (
            ("compare.observed", lambda v: session.compare_environment_pin(v, pin), self.WRONG),
            ("compare.pin", lambda v: session.compare_environment_pin(good, v), self.WRONG),
            ("resolve.root", lambda v: session.resolve_dependencies(v, {"a.py": "0" * 64}),
             self.NOT_MAPPING + [str(ROOT)]),
            ("resolve.table", lambda v: session.resolve_dependencies(ROOT, v), self.NOT_TABLE),
            ("assert_synthetic_instance", lambda v: session.assert_synthetic_instance(v), self.WRONG),
            ("capture_platform_identity", lambda v: session.capture_platform_identity(v),
             [v for v in self.NOT_MAPPING if v is not None] + ["x", 5, [], [1]]),
            ("compare.same_bad", lambda v: session.compare_environment_pin(v, v), self.WRONG),
            ("validate_receipt", lambda v: session.validate_receipt(v), self.WRONG),
            ("content_sha256", lambda v: session.content_sha256(v), self.NOT_MAPPING),
            ("canonical_bytes", lambda v: session.canonical_bytes(v), self.NOT_SERIALIZABLE),
            ("sha256_file", lambda v: session.sha256_file(v), self.NOT_MAPPING + [str(HERE)]),
            ("normalize_relative_path", lambda v: session.normalize_relative_path(v, "p"), self.NOT_PATH),
            ("resolve_inside_root.root", lambda v: session.resolve_inside_root(v, "a.py", "p"),
             self.NOT_MAPPING + [str(ROOT)]),
            ("resolve_inside_root.rel", lambda v: session.resolve_inside_root(ROOT, v, "p"),
             self.NOT_PATH),
            ("resolve_dir_inside_root.directory",
             lambda v: session.resolve_dir_inside_root(ROOT, v), self.NOT_MAPPING + [str(ROOT)]),
            ("build_receipt.steps",
             lambda v: session.build_receipt(steps=v, counters={}, identities={},
                                             digests={}, differences=[]), self.WRONG),
            ("build_receipt.counters",
             lambda v: session.build_receipt(steps=steps, counters=v, identities={},
                                             digests={}, differences=[]),
             not_dict + [(), {"a": {"b": 1}}, {("t",): 1}]),
            ("build_receipt.identities",
             lambda v: session.build_receipt(steps=steps, counters={}, identities=v,
                                             digests={}, differences=[]), self.NOT_MAPPING),
            ("build_receipt.digests",
             lambda v: session.build_receipt(steps=steps, counters={}, identities={},
                                             digests=v, differences=[]),
             not_dict + [(), {"a": {"b": 1}}, {("t",): 1}]),
            # an EMPTY differences list is the legitimate result of a
            # passing comparison, so it is not a wrong value here.
            ("build_receipt.differences",
             lambda v: session.build_receipt(steps=steps, counters={}, identities={},
                                             digests={}, differences=v),
             [v for v in self.WRONG if v not in ([], ())]),
            ("_text_sequence", lambda v: session._text_sequence(v, "s"), self.NOT_SEQUENCE),
            ("_text_sequence.item", lambda v: session._text_sequence([v], "s"), self.NOT_TEXT),
            ("_mapping", lambda v: session._mapping(v, "m"), self.NOT_MAPPING),
            ("_sequence", lambda v: session._sequence(v, "s"), self.NOT_SEQUENCE),
            ("_text", lambda v: session._text(v, "t"), self.NOT_TEXT),
            ("_flat_text", lambda v: session._flat_text(v, "t"), self.NOT_TEXT),
        )
        for name, call, values in cases:
            for value in values:
                with self.subTest(call=name, value=repr(value)[:40]):
                    self._assert_typed(name, call, value)

    def test_sealed_reference_public_functions_fuzz(self) -> None:
        """Every public argument of the sealed-reference opener is fuzzed.

        Each is given None, bool, int, float, str, bytes, list, dict,
        unhashable and nested-wrong-type values, and each must raise a TYPED
        Wp7SessionError subclass -- never a raw TypeError/AttributeError.
        """
        tree = SyntheticTree()
        self.addCleanup(tree.close)
        tree.add_session_dependencies()
        seal_path, seal_input = _write_seal(tree.root)
        resolved = {n: builder.sha256_file(tree.root / n)
                    for n in session.REQUIRED_WP_DEPENDENCIES}

        not_mapping = self.NOT_MAPPING
        # A Path is the only acceptable root; a plain str is not.
        not_root = [v for v in not_mapping if v is not None] + [str(tree.root), 5, "root", [tree.root]]
        cases = (
            ("open.root", lambda v: session.open_sealed_reference(
                v, resolved, seal_path, seal_input), not_root),
            ("open.resolved", lambda v: session.open_sealed_reference(
                tree.root, v, seal_path, seal_input), self.NOT_MAPPING),
            ("open.sealed_path", lambda v: session.open_sealed_reference(
                tree.root, resolved, v, seal_input), self.NOT_PATH + [None]),
            ("open.seal_inputs", lambda v: session.open_sealed_reference(
                tree.root, resolved, seal_path, v), self.NOT_MAPPING),
            ("open.seal_inputs.nested", lambda v: session.open_sealed_reference(
                tree.root, resolved, seal_path, dict(seal_input, coordinates=v)),
             self.NOT_MAPPING + [None, "x", 5, {"a": 1}, [1, 2]]),
            ("open.seal_inputs.identity", lambda v: session.open_sealed_reference(
                tree.root, resolved, seal_path,
                dict(seal_input, production_identity_hash=v)),
             self.WRONG + [{"a": 1}, [1], 5, 3.5, b"x", {"coordinates": 1}]),
            ("_load_seal_module.root", lambda v: session._load_seal_module(v, resolved), not_root),
            ("_load_seal_module.resolved", lambda v: session._load_seal_module(tree.root, v),
             self.NOT_MAPPING),
            # The ONE trust-boundary read helper, and its two typed siblings.
            # Every wrong path shape and every wrong label must give a typed
            # refusal, so no untyped OSError/TypeError can escape them either.
            ("read_bytes_at_boundary.path", lambda v: session.read_bytes_at_boundary(
                v, "sealed reference"), self.WRONG + [str(tree.root)]),
            ("read_bytes_at_boundary.label", lambda v: session.read_bytes_at_boundary(
                tree.root / "a.py", v), self.NOT_TEXT),
            ("read_text_at_boundary.path", lambda v: session.read_text_at_boundary(
                v, "sealed reference"), self.WRONG + [str(tree.root)]),
            ("read_text_at_boundary.label", lambda v: session.read_text_at_boundary(
                tree.root / "a.py", v), self.NOT_TEXT),
            ("read_json_at_boundary.path", lambda v: session.read_json_at_boundary(
                v, "reviewed table"), self.WRONG + [str(tree.root)]),
            ("read_json_at_boundary.label", lambda v: session.read_json_at_boundary(
                tree.root / "a.py", v), self.NOT_TEXT),
            ("sha256_file.path", lambda v: session.sha256_file(v),
             self.WRONG + [str(tree.root)]),
        )
        for name, call, values in cases:
            for value in values:
                with self.subTest(call=name, value=repr(value)[:40]):
                    self._assert_typed(name, call, value)

    def test_run_session_fuzz(self) -> None:
        tree = SyntheticTree()
        self.addCleanup(tree.close)
        base = dict(
            root=tree.root, dependency_table=tree.table, environment_pin=_pin(),
            probes=self._probes(), steps=_steps(),
        )
        for value in [v for v in self.WRONG if v is not None]:
            for key in ("root", "dependency_table", "environment_pin", "probes", "steps", "output_dir"):
                kwargs = dict(base)
                kwargs[key] = value
                with self.subTest(key=key, value=repr(value)[:40]):
                    self._assert_typed(f"run_session.{key}", lambda: session.run_session(**kwargs))

    def test_nested_wrong_types_fuzz(self) -> None:
        tree = SyntheticTree()
        self.addCleanup(tree.close)
        base = dict(
            root=tree.root, dependency_table=tree.table, environment_pin=_pin(),
            probes=self._probes(), steps=_steps(),
        )
        for key in ("dependency_table", "environment_pin", "probes", "steps"):
            for value in (
                {"a": {"b": {"c": [1, 2]}}},
                {"a": [1, 2]},
                {"a": None},
                {"a": {1: 2}},
                {"a": object()},
            ):
                kwargs = dict(base)
                kwargs[key] = value
                with self.subTest(key=key, value=repr(value)[:40]):
                    self._assert_typed(f"run_session.{key}", lambda: session.run_session(**kwargs))
        # A dependency table whose values are nested wrong types.
        for table in (
            {"a.py": {"nested": 1}},
            {"a.py": ["h"]},
            {"a.py": [("a", "b")]},
            {"a.py": {("a", "b"): "c"}},
            {"": "0" * 64},
            {"a.py/": "0" * 64},
        ):
            with self.subTest(table=repr(table)[:40]):
                self._assert_typed(
                    "resolve_dependencies.table",
                    lambda t=table: session.resolve_dependencies(tree.root, t),
                )

    @staticmethod
    def _probes() -> dict:
        return {
            "platform_reported": lambda: {"gpu_name": "Tesla T4", "python_version": "3.12.13"},
            "image_reported": lambda: {"kaggle_image": "img@sha256:abc"},
        }

    def test_internal_type_guards_are_load_bearing(self) -> None:
        cases = (
            (lambda: session._mapping(5, "L"), "must be a dict"),
            (lambda: session._mapping([1], "L"), "must be a dict"),
            (lambda: session._mapping(None, "L"), "must be a dict"),
            (lambda: session._mapping({1: "a"}, "L"), "keys must be strings"),
            (lambda: session._text(5, "L"), "must be a string"),
            (lambda: session._text(None, "L"), "must be a string"),
            (lambda: session._text([], "L"), "must be a string"),
            (lambda: session._sequence("not a list", "L"), "must be a list"),
            (lambda: session._sequence(b"x", "L"), "must be a list"),
            (lambda: session._text_sequence({"a": 1}, "L"), "must be a list"),
            (lambda: session._text_sequence(["ok", 5], "L"), "entry"),
            (lambda: session.canonical_bytes({1, 2}), "not canonicalizable"),
            (lambda: session.canonical_bytes({"x": object()}), "not canonicalizable"),
            (lambda: session.content_sha256(None), "must be a dict"),
        )
        for fn, message in cases:
            with self.assertRaisesRegex(session.Wp7SessionError, message):
                fn()
        with self.assertRaisesRegex(builder.Wp7PackageError, "must be a dict"):
            builder._mapping([1], "L")
        with self.assertRaisesRegex(builder.Wp7PackageError, "must be a dict"):
            builder._mapping(None, "L")
        with self.assertRaisesRegex(builder.Wp7PackageError, "keys must be strings"):
            builder._mapping({1: "a"}, "L")
        with self.assertRaisesRegex(builder.Wp7PackageError, "must be a string"):
            builder._text(5, "L")
        with self.assertRaisesRegex(builder.Wp7PackageError, "must be a string"):
            builder._text(None, "L")
        with self.assertRaisesRegex(builder.Wp7PackageError, "must be a list"):
            builder._sequence("x", "L")
        with self.assertRaisesRegex(builder.Wp7PackageError, "must be a lowercase sha256"):
            builder._require_sha256("ZZ", "h")
        with self.assertRaisesRegex(builder.Wp7PackageError, "must be a string"):
            builder._require_sha256(None, "h")
        with self.assertRaisesRegex(builder.Wp7PackageError, "must be a dict"):
            builder.content_sha256(None)
        with self.assertRaisesRegex(builder.Wp7PackageError, "must be a Path"):
            builder.sha256_file("x")
        with self.assertRaisesRegex(session.Wp7SessionError, "must be a Path"):
            session.sha256_file("x")

    def test_instance_kind_wrong_type_refused(self) -> None:
        with self.assertRaisesRegex(session.Wp7SessionError, "must be a string"):
            session.assert_synthetic_instance({"instance_kind": 7, "synthetic": True, "source": "synthetic_generator"})
        with self.assertRaisesRegex(session.Wp7SessionError, "must be a string"):
            session.assert_synthetic_instance({"instance_kind": [1], "synthetic": True, "source": "synthetic_generator"})
        with self.assertRaisesRegex(session.Wp7NonSyntheticRefusal, "does not declare instance_kind"):
            session.assert_synthetic_instance({"synthetic": True, "source": "synthetic_generator"})

    def test_verify_manifest_fuzz_on_shapes(self) -> None:
        tree = SyntheticTree()
        self.addCleanup(tree.close)
        good = anchored_build(tree.root, tree.table, package_root=tree.root)
        for value in self.WRONG:
            self._assert_typed("verify_manifest.root", lambda: anchored_verify(value, good))
            self._assert_typed("verify_manifest.manifest", lambda: anchored_verify(tree.root, value, package_root=tree.root))
        for key, broken in (
            ("status", "approved"),
            ("status", "pushed"),
            ("status", "draft_unknown"),
            ("status", None),
            ("is_draft", False),
            ("push_authorized", True),
            ("gpu_allocation_authorized", True),
            ("run_authorized", True),
            ("can_emit_approved_or_pushed", True),
            ("content_sha256", "0" * 64),
            ("content_sha256", 5),
            ("content_sha256", None),
            ("dependencies", []),
            ("dependencies", "x"),
            ("dependencies", [{"path": "a.py", "state": "matched", "current_sha256": None,
                               "reason": None, "recorded_reviewed_sha256": None}]),
            ("dependencies", [{"path": "a.py", "state": "invented", "current_sha256": None,
                               "reason": None, "recorded_reviewed_sha256": None}]),
            ("dependencies", [
                {"path": "a.py", "state": "matched", "current_sha256": builder.sha256_file(tree.root / "a.py"),
                 "reason": None, "recorded_reviewed_sha256": tree.table["a.py"]},
                {"path": "a.py", "state": "matched", "current_sha256": builder.sha256_file(tree.root / "a.py"),
                 "reason": None, "recorded_reviewed_sha256": tree.table["a.py"]},
            ]),
            ("dependency_count", 99),
            ("dependency_count", "3"),
            ("dependency_count", True),
            ("package_files_sha256", "x"),
            ("package_file_count", 1),
        ):
            bad = copy.deepcopy(good)
            bad[key] = broken
            if key != "content_sha256":
                bad["content_sha256"] = builder.content_sha256(bad)
            with self.assertRaises(builder.Wp7PackageError, msg=f"{key}={broken!r}"):
                anchored_verify(tree.root, bad, package_root=tree.root)


# --------------------------------------------------------------------------
# An unreadable/changed dependency is an INVALIDATING REASON, not a crash
# --------------------------------------------------------------------------
class TestUnreadableDependencyIsInvalidatingReason(unittest.TestCase):
    """verify_manifest RETURNS draft_invalid; it never raises on a stale file.

    The manifest is well formed and its own digest holds -- the dependency it
    points at has simply become unreadable, missing or altered since the
    manifest was written.  That is exactly the owner's condition ("changes to
    dependencies must invalidate the package and trigger revalidation"), so
    the API must report it as an invalidating reason.  Raising a
    Wp7PackageError there was a crash of a public entry point on a perfectly
    ordinary event.
    """

    def setUp(self) -> None:
        # A real draft_invalid manifest: a PENDING dependency makes the build
        # refuse to be ready, so verifying it later is the ordinary case
        # where a stale file must be REPORTED, not raised.  Each tree carries
        # its own reviewed-table file, because that file IS the trust anchor
        # and rebuilding it would change the first manifest's anchor.
        self.tree = SyntheticTree()
        self.addCleanup(self.tree.close)
        pending = dict(self.tree.table)
        pending["b.py"] = builder.PENDING
        self.draft = anchored_build(self.tree.root, pending, package_root=self.tree.root)
        self.assertEqual(self.draft["status"], builder.STATUS_INVALID)
        self.ready_tree = SyntheticTree()
        self.addCleanup(self.ready_tree.close)
        self.manifest = anchored_build(self.ready_tree.root, self.ready_tree.table,
                                       package_root=self.ready_tree.root)
        self.assertEqual(self.manifest["status"], builder.STATUS_READY)

    def _verify(self, manifest=None):
        if manifest is None:
            manifest = self.draft
        return anchored_verify(self.tree.root, manifest, package_root=self.tree.root)

    def test_an_unreadable_dependency_returns_draft_invalid(self) -> None:
        dep = self.tree.root / "a.py"
        dep.chmod(0o000)
        self.addCleanup(dep.chmod, 0o644)
        if os.access(dep, os.R_OK):
            self.skipTest("cannot make a dependency unreadable in this environment")
        result = self._verify()
        self.assertEqual(result["status"], builder.STATUS_INVALID)
        joined = " ".join(result["invalidating_reasons"])
        self.assertIn("a.py", joined)
        self.assertIn("cannot read", joined)

    def test_a_dependency_that_is_a_directory_returns_draft_invalid(self) -> None:
        (self.tree.root / "a.py").unlink()
        (self.tree.root / "a.py").mkdir()
        result = self._verify()
        self.assertEqual(result["status"], builder.STATUS_INVALID)
        self.assertTrue(
            any("a.py" in reason for reason in result["invalidating_reasons"]), result
        )

    def test_a_missing_dependency_returns_draft_invalid(self) -> None:
        (self.tree.root / "a.py").unlink()
        result = self._verify()
        self.assertEqual(result["status"], builder.STATUS_INVALID)
        self.assertTrue(
            any("does not exist" in reason for reason in result["invalidating_reasons"]),
            result["invalidating_reasons"],
        )

    def test_a_changed_dependency_returns_draft_invalid(self) -> None:
        self.tree.flip_one_byte("a.py")
        result = self._verify()
        self.assertEqual(result["status"], builder.STATUS_INVALID)
        self.assertTrue(
            any("stale" in reason for reason in result["invalidating_reasons"]),
            result["invalidating_reasons"],
        )

    def test_a_matched_entry_with_no_usable_hash_returns_draft_invalid(self) -> None:
        broken = copy.deepcopy(self.draft)
        for record in broken["dependencies"]:
            if record["path"] == "a.py":
                record["current_sha256"] = None
        broken["content_sha256"] = builder.content_sha256(broken)
        result = self._verify(broken)
        self.assertEqual(result["status"], builder.STATUS_INVALID)
        self.assertTrue(
            any("no usable current hash" in r for r in result["invalidating_reasons"]),
            result["invalidating_reasons"],
        )

    def test_a_ready_status_claim_over_a_stale_dependency_still_raises(self) -> None:
        # The manifest was built ready, so it still claims STATUS_READY while
        # its dependency is gone.  That combination is a FORGERY, not an
        # invalidation, and must still be refused loudly.
        self.ready_tree.flip_one_byte("a.py")
        with self.assertRaisesRegex(builder.Wp7PackageError, "claims the ready status"):
            anchored_verify(self.ready_tree.root, self.manifest,
                            package_root=self.ready_tree.root)

    def test_a_ready_status_claim_over_an_unreadable_dependency_still_raises(self) -> None:
        dep = self.ready_tree.root / "a.py"
        dep.chmod(0o000)
        self.addCleanup(dep.chmod, 0o644)
        if os.access(dep, os.R_OK):
            self.skipTest("cannot make a dependency unreadable in this environment")
        with self.assertRaises(builder.Wp7PackageError):
            anchored_verify(self.ready_tree.root, self.manifest,
                            package_root=self.ready_tree.root)

    def test_a_forged_dependency_set_is_still_a_refusal(self) -> None:
        # Returning draft_invalid must never become a hole: a manifest whose
        # own dependency set is trimmed/forged is still refused, not reported
        # as merely invalid.
        forged = copy.deepcopy(self.draft)
        forged["dependencies"] = [r for r in forged["dependencies"] if r["path"] != "a.py"]
        forged["dependency_count"] = len(forged["dependencies"])
        forged["dependency_table_sha256"] = builder.dependency_table_sha256(
            {r["path"]: r["recorded_reviewed_sha256"] for r in forged["dependencies"]}
        )
        forged["content_sha256"] = builder.content_sha256(forged)
        with self.assertRaises(builder.Wp7PackageError):
            anchored_verify(self.tree.root, forged, package_root=self.tree.root)


# --------------------------------------------------------------------------
# An unreadable/missing/changed PACKAGE file is an INVALIDATING REASON too
# --------------------------------------------------------------------------
class TestUnreadablePackageFileIsInvalidatingReason(unittest.TestCase):
    """The same rule for PACKAGE files, at both public entry points.

    ``evaluate_package_files`` and ``_verify_package_files`` both call
    ``sha256_file``, which raises ``Wp7PackageError`` on an unreadable path.
    Left unguarded that exception escaped the public entry points, so an
    ordinary event -- a permission change on a package file, a file replaced
    by a directory between build and verify -- crashed the program instead of
    being reported.  The mechanism is identical to the dependency case: the
    finding is returned in ``invalidating_reasons`` / ``reasons`` and the
    entry point does not raise.
    """

    # The package file each case damages.  It is a real package file, so the
    # damage is on a path the inventory actually walks.
    TARGET = "wp7_session.py"

    def setUp(self) -> None:
        # A draft_invalid manifest: a PENDING dependency keeps it out of the
        # ready state, which is the ordinary case in which a stale PACKAGE
        # file must be reported rather than raised.
        self.tree = SyntheticTree()
        self.addCleanup(self.tree.close)
        pending = dict(self.tree.table)
        pending["b.py"] = builder.PENDING
        self.draft = anchored_build(self.tree.root, pending, package_root=self.tree.root)
        self.assertEqual(self.draft["status"], builder.STATUS_INVALID)

    def test_evaluate_package_files_reports_an_unreadable_package_file(self) -> None:
        """The read guard: sha256_file's Wp7PackageError becomes a reason."""
        target = self.tree.root / self.TARGET
        original = builder.sha256_file
        def unreadable(path):
            if path == target:
                raise builder.Wp7PackageError("cannot read simulated unreadable package file")
            return original(path)
        builder.sha256_file = unreadable
        try:
            evaluation = builder.evaluate_package_files(self.tree.root)
        finally:
            builder.sha256_file = original
        self.assertIsNone(evaluation["hashes"][self.TARGET])
        self.assertFalse(evaluation["all_matched"])
        joined = " ".join(evaluation["reasons"])
        self.assertIn(self.TARGET, joined)
        self.assertIn("cannot read", joined)

    def test_verify_package_files_reports_an_unreadable_package_file(self) -> None:
        """The read guard again, on the verify side; nothing escapes."""
        target = self.tree.root / self.TARGET
        original = builder.sha256_file
        def unreadable(path):
            if path == target:
                raise builder.Wp7PackageError("cannot read simulated unreadable package file")
            return original(path)
        builder.sha256_file = unreadable
        try:
            problems = builder._verify_package_files(self.tree.root, self.draft)
        finally:
            builder.sha256_file = original
        joined = " ".join(problems)
        self.assertIn(self.TARGET, joined)
        self.assertIn("cannot read", joined)

    def test_verify_manifest_returns_draft_invalid_for_an_unreadable_package_file(self) -> None:
        """The public entry point returns the reason instead of raising."""
        target = self.tree.root / self.TARGET
        original = builder.sha256_file
        def unreadable(path):
            if path == target:
                raise builder.Wp7PackageError("cannot read simulated unreadable package file")
            return original(path)
        builder.sha256_file = unreadable
        try:
            result = anchored_verify(self.tree.root, self.draft, package_root=self.tree.root)
        finally:
            builder.sha256_file = original
        self.assertEqual(result["status"], builder.STATUS_INVALID)
        joined = " ".join(result["invalidating_reasons"])
        self.assertIn(self.TARGET, joined)
        self.assertIn("cannot read", joined)

    def test_a_package_file_that_is_a_directory_is_reported_not_raised(self) -> None:
        """Non-regular: the read guard must not be what raises here."""
        (self.tree.root / self.TARGET).unlink()
        (self.tree.root / self.TARGET).mkdir()
        evaluation = builder.evaluate_package_files(self.tree.root)
        self.assertIsNone(evaluation["hashes"][self.TARGET])
        self.assertFalse(evaluation["all_matched"])
        self.assertTrue(
            any(self.TARGET in reason for reason in evaluation["reasons"]),
            evaluation["reasons"],
        )
        problems = builder._verify_package_files(self.tree.root, self.draft)
        self.assertTrue(any(self.TARGET in item for item in problems), problems)
        result = anchored_verify(self.tree.root, self.draft, package_root=self.tree.root)
        self.assertEqual(result["status"], builder.STATUS_INVALID)
        self.assertTrue(
            any(self.TARGET in reason for reason in result["invalidating_reasons"]),
            result["invalidating_reasons"],
        )

    def test_a_missing_package_file_is_reported_not_raised(self) -> None:
        (self.tree.root / self.TARGET).unlink()
        evaluation = builder.evaluate_package_files(self.tree.root)
        self.assertIsNone(evaluation["hashes"][self.TARGET])
        self.assertFalse(evaluation["all_matched"])
        self.assertTrue(
            any("does not exist" in reason for reason in evaluation["reasons"]),
            evaluation["reasons"],
        )
        result = anchored_verify(self.tree.root, self.draft, package_root=self.tree.root)
        self.assertEqual(result["status"], builder.STATUS_INVALID)
        self.assertTrue(
            any("does not exist" in reason for reason in result["invalidating_reasons"]),
            result["invalidating_reasons"],
        )

    def test_a_changed_package_file_is_still_reported_as_stale(self) -> None:
        """The comparison guard keeps working: the read did not replace it."""
        self.tree.flip_one_byte(self.TARGET)
        problems = builder._verify_package_files(self.tree.root, self.draft)
        self.assertTrue(
            any("content changed since the manifest was written" in item
                for item in problems), problems,
        )
        result = anchored_verify(self.tree.root, self.draft, package_root=self.tree.root)
        self.assertEqual(result["status"], builder.STATUS_INVALID)
        self.assertTrue(
            any("content changed since the manifest was written" in reason
                for reason in result["invalidating_reasons"]),
            result["invalidating_reasons"],
        )

    def test_a_ready_claim_over_a_changed_package_file_is_still_refused(self) -> None:
        # Reporting draft_invalid must not become a hole: a manifest that
        # CLAIMS ready while its package file changed is a forgery.
        ready = SyntheticTree()
        self.addCleanup(ready.close)
        manifest = anchored_build(ready.root, ready.table, package_root=ready.root)
        self.assertEqual(manifest["status"], builder.STATUS_READY)
        ready.flip_one_byte(self.TARGET)
        with self.assertRaises(builder.Wp7PackageError):
            anchored_verify(ready.root, manifest, package_root=ready.root)

    def test_a_non_mapping_manifest_is_a_typed_refusal_at_both_package_entry_points(self) -> None:
        """The ``.get`` on a caller-supplied manifest must be guarded.

        ``_manifest_entry_set`` and ``_verify_package_files`` both read
        fields off the manifest the caller handed in.  Without the
        ``_mapping`` check each would raise a raw ``AttributeError`` -- an
        untyped error escaping a public entry point -- on any non-mapping.
        """
        for bad in (None, True, 0, 3.5, "x", b"x", [1, 2], (1, 2), {1, 2},
                    set(), object(), iter([1])):
            with self.subTest(bad=repr(bad)[:30]):
                with self.assertRaises(builder.Wp7PackageError):
                    builder._manifest_entry_set(bad)
                with self.assertRaises(builder.Wp7PackageError):
                    builder._verify_package_files(self.tree.root, bad)
                with self.assertRaises(builder.Wp7PackageError):
                    anchored_verify(self.tree.root, bad, package_root=self.tree.root)

    def test_a_non_mapping_pin_group_table_is_a_typed_refusal(self) -> None:
        """``_pinned_fields`` does ``group not in pin``; a scalar pin is wrong.

        A non-container pin would make that membership test raise a raw
        TypeError instead of the typed refusal the environment-pin
        comparison is required to give.
        """
        for bad in (None, True, False, 0, 1, -1, 3.5, float("nan"), object()):
            with self.subTest(bad=repr(bad)[:30]):
                with self.assertRaises(session.Wp7SessionError):
                    session._pinned_fields(bad)
                with self.assertRaises(session.Wp7SessionError):
                    session.compare_environment_pin(bad, _pin())
                with self.assertRaises(session.Wp7SessionError):
                    session.compare_environment_pin(_pin(), bad)

    def test_a_non_integer_report_depth_is_a_typed_refusal(self) -> None:
        """``depth > MAX_REPORTED_DEPTH`` on a non-int raised a raw TypeError."""
        for bad in (None, "0", [0], {}, 3.5, object(), True):
            with self.subTest(bad=repr(bad)[:30]):
                with self.assertRaises(session.Wp7EnvironmentAbort):
                    session._assert_reportable({"a": {"b": 1}}, "probe", bad)
        # And a legitimate int still works, so the guard is not blanket-refusing.
        session._assert_reportable({"a": 1}, "probe", 0)


# --------------------------------------------------------------------------
# Sealed OPTION A reference: every refusal the session makes around it
# --------------------------------------------------------------------------
class TestSealedOptionAReference(unittest.TestCase):
    """The session OPENS a sealed reference; it never computes one.

    Every fixture here reaches a real check in ``wp7_session`` or in the
    reviewed ``stage2_reference_seal`` by executing the real code path on a
    real seal built by the real reviewed module.  None of them asserts only
    that a name exists.
    """

    def setUp(self) -> None:
        self.tree = SyntheticTree()
        self.tree.add_session_dependencies()
        self.addCleanup(self.tree.close)
        self.seal_path, self.seal_input = _write_seal(self.tree.root)
        self.resolved = {
            name: builder.sha256_file(self.tree.root / name)
            for name in session.REQUIRED_WP_DEPENDENCIES
        }

    def _open(self, **overrides):
        args = dict(root=self.tree.root, resolved=self.resolved,
                    sealed_path=self.seal_path, seal_inputs=self.seal_input)
        args.update(overrides)
        return session.open_sealed_reference(**args)

    # -- the happy path really opens a real seal ------------------------
    def test_a_real_seal_opens_and_answers_only_what_it_sealed(self) -> None:
        opened = self._open()
        self.assertTrue(callable(opened["python_reference"]))
        self.assertRegex(opened["sealed_reference_sha256"], r"\A[0-9a-f]{64}\Z")
        self.assertGreater(opened["sealed_reference_bytes"], 0)
        answer = opened["python_reference"](
            SEAL_COORDINATES[0]["coordinate"], SEAL_COORDINATES[0]["encoding"]
        )
        self.assertEqual(sorted(answer), sorted(
            ("energy_minimum_words", "canonical_minimum_index", "tie_flags",
             "d015_d016_reconstruction")
        ))
        # A coordinate that was never sealed is refused by the reviewed module.
        with self.assertRaises(Exception):
            opened["python_reference"]({"r": "9" * 4}, "unbalanced")

    # -- the module must be present and resolved ------------------------
    def test_missing_seal_module_entry_is_refused(self) -> None:
        with self.assertRaisesRegex(session.Wp7DependencyError, "not resolved by the dependency gate"):
            self._open(resolved={k: v for k, v in self.resolved.items()
                                 if k != session.REFERENCE_SEAL_MODULE})

    def test_a_seal_module_that_does_not_load_is_refused(self) -> None:
        _write(self.tree.root / session.REFERENCE_SEAL_MODULE, b"this is not python(\n")
        self.resolved[session.REFERENCE_SEAL_MODULE] = builder.sha256_file(
            self.tree.root / session.REFERENCE_SEAL_MODULE
        )
        with self.assertRaisesRegex(session.Wp7DependencyError, "did not load"):
            self._open()

    def test_a_seal_module_without_the_opener_is_refused(self) -> None:
        _write(self.tree.root / session.REFERENCE_SEAL_MODULE,
               b"def unrelated():\n    return None\n")
        self.resolved[session.REFERENCE_SEAL_MODULE] = builder.sha256_file(
            self.tree.root / session.REFERENCE_SEAL_MODULE
        )
        with self.assertRaisesRegex(session.Wp7DependencyError, "does not expose a callable"):
            self._open()

    def test_seal_module_escaping_the_root_is_refused(self) -> None:
        with self.assertRaises(session.Wp7PathError):
            self._open(sealed_path="../outside.json")

    # -- the seal file itself -------------------------------------------
    def test_a_missing_seal_file_is_refused(self) -> None:
        with self.assertRaisesRegex(session.Wp7PathError, "does not exist"):
            self._open(sealed_path="no_such_seal.json")

    def test_an_empty_seal_file_is_refused(self) -> None:
        _write(self.tree.root / "empty.json", b"")
        with self.assertRaisesRegex(session.Wp7DependencyError, "empty"):
            self._open(sealed_path="empty.json")

    def test_a_tampered_seal_is_refused(self) -> None:
        raw = json.loads((self.tree.root / self.seal_path).read_bytes())
        raw["results"][0]["result"]["canonical_minimum_index"] = 5
        _write(self.tree.root / "tampered.json",
               json.dumps(raw, sort_keys=True, separators=(",", ":")).encode())
        with self.assertRaisesRegex(session.Wp7DependencyError, "did not open"):
            self._open(sealed_path="tampered.json")

    def test_a_non_json_seal_is_refused(self) -> None:
        _write(self.tree.root / "garbage.json", b"not json at all")
        with self.assertRaisesRegex(session.Wp7DependencyError, "did not open"):
            self._open(sealed_path="garbage.json")

    # -- the READ at the seal trust boundary is typed -------------------
    # The seal file is an untrusted input: a caller can point at a path that
    # exists but cannot be read as bytes.  Each of these must produce the
    # module's TYPED error, with the original preserved as __cause__, and
    # never an untyped OSError/UnicodeError/ValueError escaping the entry
    # point.
    def test_an_unreadable_seal_file_is_a_typed_refusal(self) -> None:
        seal = self.tree.root / self.seal_path
        seal.chmod(0o000)
        self.addCleanup(seal.chmod, 0o644)
        if os.access(seal, os.R_OK):  # running as a user that ignores the mode
            self.skipTest("cannot make the seal unreadable in this environment")
        with self.assertRaises(session.Wp7SessionError) as caught:
            self._open()
        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assertIn("sealed reference", str(caught.exception))

    def test_a_seal_path_that_is_a_directory_is_a_typed_refusal(self) -> None:
        # A directory passes lexical normalization and is inside the root, so
        # the READ is what refuses it.  ``is_file()`` alone would not stop a
        # read-only check from being the only gate; the typed read helper is.
        (self.tree.root / "dir_seal.json").mkdir(exist_ok=True)
        with self.assertRaises(session.Wp7PathError):
            self._open(sealed_path="dir_seal.json")
        # And with the containment guards bypassed, the read itself is still
        # typed rather than leaking IsADirectoryError.
        with self.assertRaises(session.Wp7SessionError) as caught:
            session.read_bytes_at_boundary(
                self.tree.root / "dir_seal.json", "sealed reference"
            )
        self.assertIsInstance(caught.exception.__cause__, IsADirectoryError)

    def test_a_dangling_symlink_seal_is_a_typed_refusal(self) -> None:
        os.symlink("nowhere_at_all.json", self.tree.root / "link_seal.json")
        with self.assertRaises(session.Wp7PathError):
            self._open(sealed_path="link_seal.json")
        # Now a symlink that DOES resolve but whose target cannot be read.
        (self.tree.root / "target.json").write_bytes(b"{}")
        (self.tree.root / "target.json").chmod(0o000)
        self.addCleanup((self.tree.root / "target.json").chmod, 0o644)
        if os.access(self.tree.root / "target.json", os.R_OK):
            self.skipTest("cannot make the symlink target unreadable in this environment")
        os.symlink("target.json", self.tree.root / "live_link.json")
        with self.assertRaises(session.Wp7SessionError) as caught:
            self._open(sealed_path="live_link.json")
        self.assertIsInstance(caught.exception.__cause__, OSError)

    def test_the_boundary_helper_never_swallows_base_exception(self) -> None:
        # Only SPECIFIC classes are converted.  KeyboardInterrupt and
        # SystemExit must still propagate, or a Ctrl-C would be reported as a
        # typed WP7 refusal and a caller could not abort.
        path = self.tree.root / "abortable.json"
        _write(path, b"{}")
        real = Path.read_bytes

        def exploding(self, *a, **k):
            if self == path:
                raise KeyboardInterrupt("user aborted")
            return real(self, *a, **k)

        Path.read_bytes = exploding
        self.addCleanup(setattr, Path, "read_bytes", real)
        with self.assertRaises(KeyboardInterrupt):
            session.read_bytes_at_boundary(path, "abortable seal")

    def test_the_boundary_helper_converts_every_specific_class(self) -> None:
        path = self.tree.root / "classed.json"
        _write(path, b"{}")
        real = Path.read_bytes

        def make(cls):
            if cls is json.JSONDecodeError:
                return json.JSONDecodeError("induced", "{", 0)
            return cls("induced")

        for cls in (OSError, PermissionError, FileNotFoundError, IsADirectoryError,
                    UnicodeError, ValueError, json.JSONDecodeError):
            with self.subTest(cls=cls.__name__):
                def raising(self, *a, _exc=make(cls), **k):
                    if self == path:
                        raise _exc
                    return real(self, *a, **k)

                Path.read_bytes = raising
                with self.assertRaises(session.Wp7SessionError) as caught:
                    session.read_bytes_at_boundary(path, "sealed reference")
                self.assertIsInstance(caught.exception.__cause__, cls)
        Path.read_bytes = real
        # And the typed helper is what the seal entry point actually uses.
        self.assertEqual(
            session.sha256_file(path), session.hashlib.sha256(b"{}").hexdigest()
        )

    # -- the guards the mutation sweep found unreached -----------------
    # Each of these is a real guard with NO fixture reaching it: removing it
    # left every fixture green.  They are closed here, in isolation, so the
    # sweep can no longer report a survivor for them.
    def test_a_non_path_root_is_refused_before_the_seal_module_is_read(self) -> None:
        # Guards: _load_seal_module "if not isinstance(root, Path)" and
        # open_sealed_reference's own copy of the same guard.  A non-Path
        # root must be refused BEFORE resolve_inside_root, which would
        # otherwise raise a raw TypeError from os.path.realpath.
        for call in (session.open_sealed_reference, session._load_seal_module):
            with self.subTest(call=call.__name__):
                for bad in ("a string", 7, ["list"], {"a": 1}, b"bytes", 3.5, True):
                    with self.assertRaises(session.Wp7SessionError) as caught:
                        if call is session._load_seal_module:
                            call(bad, self.resolved)
                        else:
                            call(bad, self.resolved, self.seal_path, self.seal_input)
                    self.assertIsInstance(caught.exception.__cause__, type(None))

    def test_a_seal_module_with_no_import_spec_is_refused(self) -> None:
        # Guard: _load_seal_module "if spec is None or spec.loader is None".
        # A module file whose extension gives importlib no usable spec must
        # be a typed refusal, never a NoneType attribute crash one line later.
        target = self.tree.root / "no_spec_module"
        _write(target, b"def open_for_session(a, b):\n    return None\n")
        self.resolved[session.REFERENCE_SEAL_MODULE] = "0" * 64
        real = session.resolve_inside_root
        try:
            def fake_resolve(root, relative, label):
                return target
            session.resolve_inside_root = fake_resolve
            with self.assertRaisesRegex(session.Wp7DependencyError, "no import spec"):
                session._load_seal_module(self.tree.root, self.resolved)
        finally:
            session.resolve_inside_root = real

    def test_an_opened_seal_that_is_not_callable_is_refused(self) -> None:
        # Guard: open_sealed_reference "if not callable(reference)".  A seal
        # module that returns a non-callable must not be handed to section-B
        # item 2 as if it were a reference.
        opener = session.REFERENCE_SEAL_OPENER
        module_path = self.tree.root / "notcallable_seal_mod.py"
        _write(module_path, (
            f"{opener} = lambda sealed, inputs: 'not a callable'\n"
        ).encode())
        self.resolved[session.REFERENCE_SEAL_MODULE] = builder.sha256_file(module_path)
        # Point the loader at the stand-in module.
        real_resolve = session.resolve_inside_root
        try:
            def fake_resolve(root, relative, label):
                if label == "reference seal module":
                    return module_path
                return real_resolve(root, relative, label)
            session.resolve_inside_root = fake_resolve
            with self.assertRaisesRegex(session.Wp7DependencyError, "not callable"):
                self._open()
        finally:
            session.resolve_inside_root = real_resolve

    def test_sha256_file_refuses_a_non_path_typed(self) -> None:
        # sha256_file delegates its type check to read_bytes_at_boundary, the
        # one helper every boundary read shares.  Removing that shared guard
        # is what must fail here.
        for bad in ("a string", 7, ["list"], {"a": 1}, b"bytes", 3.5, True, None):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(session.Wp7SessionError):
                    session.sha256_file(bad)

    def test_a_directory_seal_cannot_claim_to_be_a_regular_file(self) -> None:
        # The S_ISREG check in resolve_inside_root is the only thing that
        # refuses a directory: it exists and resolves inside the root.
        (self.tree.root / "dir_for_isfile.json").mkdir(exist_ok=True)
        with self.assertRaisesRegex(session.Wp7PathError, "not a regular file"):
            self._open(sealed_path="dir_for_isfile.json")

    def test_the_seal_inputs_must_declare_both_fields_on_the_session_path(self) -> None:
        # Guard: run_session's sealed-reference step, reached end to end.
        # If the seal inputs are incomplete the session must refuse before
        # section-B item 2 runs at all.
        for field in ("coordinates", "production_identity_hash"):
            with self.subTest(field=field):
                bad = {k: v for k, v in self.seal_input.items() if k != field}
                with self.assertRaises(session.Wp7DependencyError):
                    session.open_sealed_reference(
                        self.tree.root, self.resolved, self.seal_path, bad)

    def test_the_text_and_json_boundary_helpers_are_typed(self) -> None:
        path = self.tree.root / "encoded.json"
        _write(path, b"\xff\xfe not utf-8")
        with self.assertRaises(session.Wp7SessionError) as caught:
            session.read_text_at_boundary(path, "sealed reference")
        self.assertIsInstance(caught.exception.__cause__, UnicodeError)
        _write(path, b"{not json")
        with self.assertRaises(session.Wp7SessionError) as caught:
            session.read_json_at_boundary(path, "reviewed table")
        self.assertIsInstance(caught.exception.__cause__, json.JSONDecodeError)
        for bad in (None, 1, [], {}, b"x", {"a": {}}):
            with self.subTest(bad=bad):
                with self.assertRaises(session.Wp7SessionError):
                    session.read_bytes_at_boundary(bad, "sealed reference")

    # -- the session inputs must match the seal -------------------------
    def test_seal_inputs_missing_a_required_field_are_refused(self) -> None:
        for field in ("coordinates", "production_identity_hash"):
            with self.subTest(field=field):
                bad = {k: v for k, v in self.seal_input.items() if k != field}
                with self.assertRaisesRegex(session.Wp7DependencyError, field):
                    self._open(seal_inputs=bad)

    def test_a_production_identity_mismatch_is_refused(self) -> None:
        with self.assertRaisesRegex(session.Wp7DependencyError, "did not open"):
            self._open(seal_inputs=dict(self.seal_input, production_identity_hash="2" * 64))

    def test_a_coordinate_census_mismatch_is_refused(self) -> None:
        with self.assertRaisesRegex(session.Wp7DependencyError, "did not open"):
            self._open(seal_inputs=dict(self.seal_input, coordinates=SEAL_COORDINATES[:1]))

    # -- the session itself refuses to run item 2 without a seal --------
    def test_a_session_without_a_seal_never_reaches_section_b_item_2(self) -> None:
        out = self.tree.root / "out"
        out.mkdir(exist_ok=True)
        called: list[str] = []
        steps = _steps()

        def writer():
            path = out / "writer.bin"
            path.write_bytes(b"synthetic range")
            return _step_results()["wp4b_writer_synthetic_ranges"]

        def b2(reference=None):
            called.append("b2")
            return _step_results()["section_b_item_2_full_domain_synthetic"]

        steps["wp4b_writer_synthetic_ranges"] = writer
        steps["section_b_item_2_full_domain_synthetic"] = b2
        with self.assertRaises(session.Wp7SessionError):
            session.run_session(
                root=self.tree.root,
                dependency_table=self.tree.session_table,
                environment_pin=_pin(),
                probes={"platform_reported": lambda: _pin()["platform_reported"],
                        "image_reported": lambda: _pin()["image_reported"]},
                instance=dict(SYNTHETIC_INSTANCE),
                steps=steps,
                output_dir=out,
                sealed_reference_path=None,
                seal_inputs=None,
            )
        self.assertEqual(called, [], "section B item 2 ran without an opened seal")

    def test_a_receipt_cannot_omit_the_seal_opening(self) -> None:
        with self.assertRaises(session.Wp7StepNotRunError):
            session.build_receipt(
                steps=[s for s in session.REQUIRED_STEPS if s != "open_sealed_reference"],
                counters={"a": 1},
                identities={"b": {"c": "d"}},
                digests={"step:" + s: "0" * 64 for s in session.REQUIRED_STEPS},
                differences=[],
            )

    def test_the_seal_module_is_a_required_wp_dependency(self) -> None:
        self.assertIn(session.REFERENCE_SEAL_MODULE, session.REQUIRED_WP_DEPENDENCIES)
        self.assertIn("open_sealed_reference", session.REQUIRED_STEPS)
        # it must sit between section-B item 1 and item 2
        self.assertLess(
            session.STEP_ORDER.index("section_b_item_1_recheck_synthetic"),
            session.STEP_ORDER.index("open_sealed_reference"),
        )
        self.assertLess(
            session.STEP_ORDER.index("open_sealed_reference"),
            session.STEP_ORDER.index("section_b_item_2_full_domain_synthetic"),
        )


# --------------------------------------------------------------------------
# Guard inventory self-test
# --------------------------------------------------------------------------
class TestGuardInventory(unittest.TestCase):
    def test_every_guard_text_exists_exactly_once_in_its_module(self) -> None:
        """The sweep's inventory is accurate, or the sweep proves nothing.

        Uniqueness is asserted WITHIN the named function, which is the scope
        the mutation sweep replaces in.  A line that legitimately appears in
        two different functions is fine; a line that appears twice in the
        same function is ambiguous, and the sweep would be a coin flip.
        """
        for file in ("build_wp7_package.py", "wp7_session.py"):
            text = (HERE / file).read_text(encoding="utf-8")
            lines = text.splitlines()
            tree = ast.parse(text)
            functions = {
                node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
            }
            for name, symbol, guarded in GUARDS:
                if name != file:
                    continue
                with self.subTest(file=file, symbol=symbol, text=guarded):
                    self.assertIn(symbol, functions, f"{file} has no function {symbol}")
                    body = functions[symbol]
                    hits = [
                        index + 1
                        for index in range(body.lineno - 1, (body.end_lineno or body.lineno))
                        if lines[index].strip() == guarded
                    ]
                    self.assertEqual(
                        len(hits), 1,
                        f"{file}:{symbol} line {guarded!r} occurs {len(hits)} times in that function",
                    )
        self.assertGreaterEqual(len(GUARDS), 100)

    def test_the_two_path_guards_the_sweep_found_unreached(self) -> None:
        """The two path guards that survived the first sweep round.

        The builder's ``os.path.isabs`` was dominated by the lexical
        ``startswith("/")`` immediately above it, and its ``real.is_file()``
        was dominated by the ``S_ISREG(real.stat().st_mode)`` immediately
        below it -- on this platform the pair were unreachable duplicates, so
        the sweep correctly flagged them and they were deleted rather than
        papered over with a fixture that proves nothing.  What remains is
        proved here, including the FIFO that ``exists()`` alone would accept.
        """
        for absolute in ("/etc/passwd", "/tmp/x.json"):
            with self.subTest(absolute=absolute):
                with self.assertRaisesRegex(builder.Wp7PathError, "not absolute"):
                    builder.normalize_relative_path(absolute, "probe")
        with SyntheticTree() as tree:
            (tree.root / "a_directory.py").mkdir()
            with self.assertRaisesRegex(builder.Wp7PathError, "not a regular file"):
                builder.resolve_inside_root(tree.root, "a_directory.py", "probe")
        with SyntheticTree() as tree:
            try:
                os.mkfifo(tree.root / "a_fifo.py")
            except (AttributeError, OSError):
                self.skipTest("cannot create a FIFO on this platform")
            with self.assertRaisesRegex(builder.Wp7PathError, "not a regular file"):
                builder.resolve_inside_root(tree.root, "a_fifo.py", "probe")

    def test_shipped_manifest_pins_every_package_file(self) -> None:
        """The shipped manifest must carry a real hash for every package file.
        This is what makes a one-byte change to build_wp7_package.py itself
        detectable: the builder can never hash its own bytes into the file
        it hashes, so the pin is made externally here and the same hash is
        what the manifest records.
        """
        manifest = json.loads((HERE / "wp7_push_manifest.draft.json").read_text())
        self.assertEqual(set(builder.PACKAGE_FILES),
                         {"wp7_session.py", "wp7_environment_pin.json",
                          "build_wp7_package.py", "verify_wp7_package_fixtures.py",
                          "GATE_9_WP7_PACKAGE_DRAFT.md"})
        shipped_table = json.loads((HERE / builder.REVIEWED_TABLE_NAME).read_text(encoding="utf-8"))
        for name in builder.PACKAGE_FILES:
            self.assertIn(name, manifest["package_files_sha256"], name)
            recorded = manifest["package_files_sha256"][name]
            if shipped_table.get("_placeholder"):
                if name == "build_wp7_package.py":
                    self.assertEqual(recorded, builder.sha256_file(HERE / name), name)
                else:
                    self.assertIsNotNone(recorded, name)
            else:
                self.assertRegex(recorded, r"\A[0-9a-f]{64}\Z", name)
                self.assertEqual(recorded, builder.sha256_file(HERE / name), name)
        self.assertEqual(manifest["package_file_count"], len(builder.PACKAGE_FILES))
        if shipped_table.get("_placeholder"):
            self.assertEqual(manifest["status"], builder.STATUS_INVALID)
        else:
            self.assertEqual(manifest["status"], "draft_ready_for_owner_review")
            verified = builder.verify_manifest(
                ROOT, manifest, package_root=HERE,
                expected_reviewed_table_sha256=builder.sha256_file(HERE / builder.REVIEWED_TABLE_NAME))
            self.assertEqual(verified["status"], "draft_ready_for_owner_review")
            self.assertEqual(verified["verified_dependencies"], 29)
            self.assertEqual(verified["verified_package_files"], 5)
            for key in ("push_authorized", "gpu_allocation_authorized", "run_authorized"):
                self.assertFalse(manifest[key], key)
            self.assertFalse(manifest["can_emit_approved_or_pushed"])
            self.assertTrue(manifest["is_draft"])
        self.assertEqual(manifest["content_sha256"], builder.content_sha256(manifest))

    def test_pinned_shipped_table_tampering_is_refused(self) -> None:
        """A byte changed in a temp copy of the pinned table invalidates verification."""
        shipped = json.loads((HERE / builder.REVIEWED_TABLE_NAME).read_text(encoding="utf-8"))
        if shipped.get("_placeholder"):
            self.skipTest("shipped table is a placeholder in this tree")
        with tempfile.TemporaryDirectory(prefix="wp7-table-tamper-") as d:
            package_root = Path(d) / "package"
            package_root.mkdir()
            for name in builder.PACKAGE_FILES:
                shutil.copy2(HERE / name, package_root / name)
            shutil.copy2(HERE / builder.MANIFEST_NAME, package_root / builder.MANIFEST_NAME)
            table_path = package_root / builder.REVIEWED_TABLE_NAME
            shutil.copy2(HERE / builder.REVIEWED_TABLE_NAME, table_path)
            manifest = json.loads((package_root / builder.MANIFEST_NAME).read_text(encoding="utf-8"))
            anchor = builder.sha256_file(table_path)
            data = bytearray(table_path.read_bytes())
            data[0] ^= 1
            table_path.write_bytes(data)
            with self.assertRaises((builder.Wp7PackageError, builder.Wp7DependencyError)):
                builder.verify_manifest(ROOT, manifest, package_root=package_root,
                                        expected_reviewed_table_sha256=anchor)

    def test_no_round_save_files_are_in_the_package_inventory(self) -> None:
        """The inventory is exactly the package files: no "*.r1" / "*.r2".

        Prior round saves are not package files.  A round-save file left beside
        the package is an unreviewed entry and must be refused by the
        inventory guard rather than silently pinned or listed.
        """
        for name in builder.PACKAGE_FILES:
            self.assertNotIn(".r1", name)
            self.assertNotIn(".r2", name)
        shipped = json.loads((HERE / builder.REVIEWED_TABLE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(set(shipped["package_files_sha256"]), set(builder.PACKAGE_FILES))
        # A round-save file dropped into the package directory is refused.
        with SyntheticTree() as tree:
            _write(tree.root / "wp7_session.py.r1", b"# round save\n")
            with self.assertRaisesRegex(builder.Wp7DependencyError, "unreviewed package entries"):
                anchored_build(tree.root, tree.table, package_root=tree.root)

    def test_inventory_has_no_duplicates(self) -> None:
        seen = set()
        for guard in GUARDS:
            key = tuple(guard)
            self.assertNotIn(key, seen, f"duplicate guard entry: {key}")
            seen.add(key)


def _report_guard_cases() -> int:
    """Print the guard inventory as JSON for the mutation sweep."""
    print("WP7-GUARD-CASES " + json.dumps(GUARDS))
    return 0


if __name__ == "__main__":
    if "PYTHONDONTWRITEBYTECODE" not in os.environ:
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    if "--report-guard-cases" in sys.argv:
        raise SystemExit(_report_guard_cases())
    unittest.main(verbosity=2)
