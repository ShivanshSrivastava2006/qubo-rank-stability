#!/usr/bin/env python3
"""Adversarial fixtures for the Gate-9 Arm-0 intrinsic image fingerprint probe.

Every input is injected; no real filesystem, no network, no subprocess, no GPU
and no Kaggle call is made.  The fixtures must cover:

- determinism: identical injected inputs give an identical fingerprint, twice,
  and reader enumeration order cannot change it;
- sensitivity: changing ANY single component -- one package version, one added
  package, one st_size, one st_mode, os-release bytes, debian_version bytes,
  dpkg status bytes, or the interpreter -- changes the fingerprint;
- the excluded-prefix rule REFUSES /proc, /sys, /dev, /kaggle, /tmp and
  /var/run rather than skipping them, and the runtime-injected files
  (/etc/hosts and siblings) are refused by name;
- a missing optional file (/etc/debian_version, /var/lib/dpkg/status) is
  handled deterministically, not by crashing;
- a reader returning a wrong type, oversize data, or raising is refused with the
  correct enum reason;
- the refusal path emits no fingerprint and no partial data;
- the report stays under the size cap and its seal verifies;
- the probe reads no environment variable and no mtime anywhere;
- importing the probe module writes nothing.

Run with:
PYTHONDONTWRITEBYTECODE=1 python3 verify_stage2_cuda_image_fingerprint_probe_fixtures.py
PYTHONDONTWRITEBYTECODE=1 python3 -O verify_stage2_cuda_image_fingerprint_probe_fixtures.py
"""

from __future__ import annotations

import ast
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile

# Important: run fixtures with PYTHONDONTWRITEBYTECODE=1.
if not os.environ.get("PYTHONDONTWRITEBYTECODE"):
    print("WARNING: PYTHONDONTWRITEBYTECODE is not set.", file=sys.stderr)

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import stage2_cuda_image_fingerprint_probe as probe

FAILURES = []


def check(condition: bool, message: str) -> None:
    if not condition:
        print("FAIL: " + message, file=sys.stderr)
        FAILURES.append(message)


def check_raises(reason: str, func, *args, **kwargs) -> None:
    try:
        func(*args, **kwargs)
    except probe.ProbeRefusal as refusal:
        check(refusal.reason == reason,
              "expected refusal {!r}, got {!r}".format(reason, refusal.reason))
        return
    except Exception as error:  # noqa: BLE001 - fixtures must see the wrong type
        check(False, "expected ProbeRefusal {!r}, got {!r}".format(reason, error))
        return
    check(False, "expected ProbeRefusal {!r}, nothing raised".format(reason))


# ---------------------------------------------------------------- fixture data

BASE_INTERPRETER = {
    "implementation": {"cache_tag": "cpython-311", "hexversion": 51056880,
                       "name": "cpython", "version": [3, 11, 5, "final", 0]},
    "version": "3.11.5 (main, Sep 1 2024, 00:00:00) [GCC 12.2.0]",
}
BASE_FILES = {
    probe.OS_RELEASE_PATH: (b'PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"\n'
                            b'ID=debian\nVERSION_ID="12"\n'),
    probe.DEBIAN_VERSION_PATH: b"12.7\n",
    probe.DPKG_STATUS_PATH: b"Package: libc6\nStatus: install ok installed\nVersion: 2.36-9\n\n",
}
BASE_DISTRIBUTIONS = (
    ("numpy", "1.26.4"),
    ("PIP", "24.0"),
    ("typing_extensions", "4.12.2"),
    ("xgboost", "7.7.7"),
)
BASE_STATS = {
    "/usr/bin/dpkg": {"st_mode": 33261, "st_size": 350000},
    "/usr/bin/python3": {"st_mode": 33261, "st_size": 6831736},
    "/usr/lib/x86_64-linux-gnu/libc.so.6": {"st_mode": 33261, "st_size": 1922136},
}


def make_read_file(files: dict):
    def read_file(path: str, limit: int):
        data = files.get(path)
        return None if data is None else data[:limit + 1]
    return read_file


def make_sources(interpreter=None, files=None, distributions=None, stats=None) -> dict:
    files = BASE_FILES if files is None else files
    stats = BASE_STATS if stats is None else stats
    distributions = BASE_DISTRIBUTIONS if distributions is None else distributions
    interpreter = BASE_INTERPRETER if interpreter is None else interpreter
    return {
        "list_distributions": lambda: tuple(distributions),
        "read_file": make_read_file(files),
        "read_interpreter": lambda: json.loads(json.dumps(interpreter)),
        "stat_path": lambda path: (None if stats.get(path) is None
                                   else dict(stats[path])),
    }


def fingerprint(**kwargs) -> str:
    report = probe.run_probe(**make_sources(**kwargs))
    check(report["verdict"] == "fingerprint_measured",
          "expected a measured verdict, got {!r} ({!r})".format(
              report["verdict"], report["refusal_reason"]))
    return report["image_content_fingerprint"]


# -------------------------------------------------------------------- fixtures

def test_determinism():
    first = probe.run_probe(**make_sources())
    second = probe.run_probe(**make_sources())
    check(first["image_content_fingerprint"] == second["image_content_fingerprint"],
          "same injected inputs must give the same fingerprint")
    check(probe.canonical(first) == probe.canonical(second),
          "same injected inputs must give a byte-identical report")
    check(len(first["image_content_fingerprint"]) == 64,
          "the fingerprint is a 64-character hex digest")
    check(all(character in "0123456789abcdef"
              for character in first["image_content_fingerprint"]),
          "the fingerprint is lowercase hex")
    # Determinism must not depend on reader enumeration order.
    shuffled = tuple(reversed(BASE_DISTRIBUTIONS))
    check(fingerprint(distributions=shuffled) == first["image_content_fingerprint"],
          "distribution enumeration order must not change the fingerprint")
    # Nor on the spelling of a distribution name: PEP 503 normalisation.
    respelled = tuple((name.replace("_", "-").upper() if name == "typing_extensions"
                       else name) for name, _ in BASE_DISTRIBUTIONS)
    respelled_rows = tuple(zip(respelled, [v for _, v in BASE_DISTRIBUTIONS]))
    check(fingerprint(distributions=respelled_rows) == first["image_content_fingerprint"],
          "distribution name spelling must not change the fingerprint")
    # compute_fingerprint itself is a pure function.
    args = ({"a": 1}, {"b": "c"}, [["d", "1"]], [{"path": "/usr/bin/env"}])
    check(probe.compute_fingerprint(*args) == probe.compute_fingerprint(*args),
          "compute_fingerprint is pure")


def test_sensitivity():
    base = fingerprint()
    moved = {}

    bumped = tuple((name, "9.9.9" if name == "numpy" else version)
                   for name, version in BASE_DISTRIBUTIONS)
    moved["one package version"] = fingerprint(distributions=bumped)

    added = BASE_DISTRIBUTIONS + (("scipy", "1.14.0"),)
    moved["one added package"] = fingerprint(distributions=added)

    removed = tuple(row for row in BASE_DISTRIBUTIONS if row[0] != "numpy")
    moved["one removed package"] = fingerprint(distributions=removed)

    files = dict(BASE_FILES)
    files[probe.OS_RELEASE_PATH] = (b'PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"\n'
                                    b'ID=debian\nVERSION_ID="12"\n\n')
    moved["os-release content"] = fingerprint(files=files)

    files = dict(BASE_FILES)
    files[probe.DEBIAN_VERSION_PATH] = b"12.8\n"
    moved["debian_version content"] = fingerprint(files=files)

    files = dict(BASE_FILES)
    files[probe.DPKG_STATUS_PATH] = BASE_FILES[probe.DPKG_STATUS_PATH] + b"Package: x\n\n"
    moved["dpkg status content"] = fingerprint(files=files)

    stats = {path: dict(value) for path, value in BASE_STATS.items()}
    stats["/usr/bin/python3"]["st_size"] += 1
    moved["one st_size"] = fingerprint(stats=stats)

    stats = {path: dict(value) for path, value in BASE_STATS.items()}
    stats["/usr/bin/dpkg"]["st_mode"] = 33188
    moved["one st_mode"] = fingerprint(stats=stats)

    stats = {path: dict(value) for path, value in BASE_STATS.items()}
    stats["/usr/bin/dpkg"] = None
    moved["one absent path"] = fingerprint(stats=stats)

    interpreter = json.loads(json.dumps(BASE_INTERPRETER))
    interpreter["version"] = BASE_INTERPRETER["version"] + " "
    moved["sys.version"] = fingerprint(interpreter=interpreter)

    interpreter = json.loads(json.dumps(BASE_INTERPRETER))
    interpreter["implementation"]["hexversion"] += 1
    moved["sys.implementation"] = fingerprint(interpreter=interpreter)

    for label, digest in moved.items():
        check(digest != base, "changing {} must change the fingerprint".format(label))
    check(len(set(moved.values())) == len(moved),
          "each single-component change must give its own distinct fingerprint")


def test_excluded_prefixes_are_refused_not_skipped():
    required = ("/proc", "/sys", "/dev", "/kaggle", "/tmp", "/var/run")
    for prefix in required:
        check(any(excluded.rstrip("/") == prefix
                  for excluded in probe.EXCLUDED_PREFIXES),
              "{} must be an excluded prefix".format(prefix))
    for path in ("/proc/self/status", "/proc/version", "/sys/class/dmi/id/product_uuid",
                 "/dev/nvidia0", "/kaggle/working/out.json", "/tmp/scratch",
                 "/var/run/secrets/token", "/var/tmp/x", "/var/log/dpkg.log",
                 "/root/.netrc", "/home/user/.config", "/run/secrets/x"):
        check_raises("path_excluded_prefix", probe.check_path, path)
    # The bare prefix itself is refused too.
    for path in ("/proc", "/sys", "/dev", "/tmp"):
        check_raises("path_excluded_prefix", probe.check_path, path)
    # Runtime-injected files sit under an allowed prefix and are refused by name.
    for path in probe.RUNTIME_INJECTED_PATHS:
        check_raises("path_runtime_injected", probe.check_path, path)
    # Outside every allowed prefix.
    check_raises("path_not_allowed_prefix", probe.check_path, "/opt/conda/lib/x")
    check_raises("path_not_allowed_prefix", probe.check_path, "/srv/x")
    # Allowed prefix, but not on the whitelist.
    check_raises("path_not_whitelisted", probe.check_path, "/etc/passwd")
    check_raises("path_not_whitelisted", probe.check_path, "/usr/bin/env")
    # Malformed paths never reach the prefix rules.
    for path in ("", "relative/path", "/etc/../proc/self", "/etc/x y", 123, None,
                 "/etc/" + "a" * probe.MAX_PATH_CHARS):
        check_raises("whitelist_malformed", probe.check_path, path)
    # The live readers refuse a path outside their own fixed set.
    for reader, argument in ((lambda p: probe.live_read_file(p, 8192), "/proc/version"),
                             (probe.live_stat_path, "/proc/version")):
        try:
            reader(argument)
        except ValueError:
            pass
        else:
            check(False, "a live reader must refuse a non-whitelisted path")
    # The module constants themselves pass the rule.
    check(probe.validate_whitelist() == len(probe.whitelisted_paths()),
          "the fixed whitelist validates")
    check(not set(probe.RUNTIME_INJECTED_PATHS) & set(probe.whitelisted_paths()),
          "no runtime-injected file is on the whitelist")


def test_missing_optional_files_are_deterministic():
    files = {probe.OS_RELEASE_PATH: BASE_FILES[probe.OS_RELEASE_PATH]}
    first = probe.run_probe(**make_sources(files=files))
    second = probe.run_probe(**make_sources(files=files))
    check(first["verdict"] == "fingerprint_measured",
          "a missing optional file must not refuse")
    check(first["image_content_fingerprint"] == second["image_content_fingerprint"],
          "a missing optional file must be deterministic across runs")
    check(first["component_status"]["debian_version"] == "absent",
          "an absent /etc/debian_version reports absent")
    check(first["component_status"]["dpkg_status"] == "absent",
          "an absent /var/lib/dpkg/status reports absent")
    check(first["component_sha256"]["debian_version"] is None,
          "an absent optional file has no content digest")
    check(first["image_content_fingerprint"] != fingerprint(),
          "absence of an optional file is itself a difference")
    # An empty optional file is distinct from an absent one.
    files = dict(BASE_FILES)
    files[probe.DEBIAN_VERSION_PATH] = b""
    empty = probe.run_probe(**make_sources(files=files))
    check(empty["component_status"]["debian_version"] == "measured",
          "an empty optional file is present, not absent")
    check(empty["image_content_fingerprint"] != first["image_content_fingerprint"],
          "an empty optional file differs from an absent one")
    # An absent immutable path is deterministic too.
    stats = {path: None for path in probe.IMMUTABLE_PATHS}
    first = probe.run_probe(**make_sources(stats=stats))
    second = probe.run_probe(**make_sources(stats=stats))
    check(first["component_status"]["immutable_paths"] == "absent", "all paths absent")
    check(first["counts"]["absent_immutable_path_count"] == len(probe.IMMUTABLE_PATHS),
          "absent paths are counted")
    check(first["image_content_fingerprint"] == second["image_content_fingerprint"],
          "absent immutable paths are deterministic")
    # A required file that is absent refuses.
    report = probe.run_probe(**make_sources(files={}))
    check(report["refusal_reason"] == "content_file_absent",
          "an absent /etc/os-release refuses")
    check(report["refused_path"] == probe.OS_RELEASE_PATH, "the refusal names the path")


def test_bad_readers_are_refused():
    def refusal_for(**kwargs) -> dict:
        return probe.run_probe(**make_sources(**kwargs))

    # Wrong type from the content reader.
    sources = make_sources()
    sources["read_file"] = lambda path, limit: "not bytes"
    check(probe.run_probe(**sources)["refusal_reason"] == "content_reader_malformed",
          "a content reader returning str is refused")
    # Oversize content.
    sources = make_sources()
    sources["read_file"] = lambda path, limit: b"A" * (limit + 1)
    check(probe.run_probe(**sources)["refusal_reason"] == "content_file_oversize",
          "oversize content is refused")
    # A reader that raises.
    for name in ("read_interpreter", "read_file", "list_distributions", "stat_path"):
        sources = make_sources()
        def exploding(*args, **kwargs):
            raise OSError("reader blew up")
        sources[name] = exploding
        check(probe.run_probe(**sources)["refusal_reason"] == "reader_error",
              "a raising {} reader is refused as reader_error".format(name))
    # Interpreter reader shapes.
    for facts in (None, {}, {"version": "x"}, {"version": 1, "implementation": {}},
                  {"version": "x", "implementation": {"cache_tag": "t", "hexversion": 1,
                                                      "name": "cpython",
                                                      "version": [3, 11, 5, "final"]}},
                  {"version": "x", "implementation": {"cache_tag": "t", "hexversion": True,
                                                      "name": "cpython",
                                                      "version": [3, 11, 5, "final", 0]}}):
        check_raises("interpreter_reader_malformed", probe.measure_interpreter,
                     lambda facts=facts: facts)
    # Distribution reader shapes.
    check_raises("distribution_reader_malformed", probe.measure_distributions,
                 lambda: (("numpy",),))
    check_raises("distribution_reader_malformed", probe.measure_distributions,
                 lambda: ("numpy",))
    check_raises("distribution_name_malformed", probe.measure_distributions,
                 lambda: ((123, "1.0"),))
    check_raises("distribution_name_malformed", probe.measure_distributions,
                 lambda: (("bad name", "1.0"),))
    check_raises("distribution_version_malformed", probe.measure_distributions,
                 lambda: (("numpy", None),))
    check_raises("distribution_version_malformed", probe.measure_distributions,
                 lambda: (("numpy", "1.0\n0"),))
    check_raises("distribution_version_oversize", probe.measure_distributions,
                 lambda: (("numpy", "1" * (probe.MAX_VERSION_CHARS + 1)),))
    check_raises("distribution_overcount", probe.measure_distributions,
                 lambda: tuple(("pkg" + str(index), "1.0")
                               for index in range(probe.MAX_DISTRIBUTIONS + 1)))
    # Stat reader shapes: notably, an mtime key is refused, because no component
    # of this probe reads an mtime.
    check_raises("stat_reader_malformed", probe.measure_immutable_paths,
                 lambda path: {"st_mode": 1, "st_size": 1, "st_mtime_ns": 1})
    check_raises("stat_reader_malformed", probe.measure_immutable_paths,
                 lambda path: (33261, 10))
    check_raises("stat_value_out_of_range", probe.measure_immutable_paths,
                 lambda path: {"st_mode": -1, "st_size": 1})
    check_raises("stat_value_out_of_range", probe.measure_immutable_paths,
                 lambda path: {"st_mode": True, "st_size": 1})
    # os-release field shapes.
    files = dict(BASE_FILES)
    files[probe.OS_RELEASE_PATH] = b'ID="deb ian"\n'
    check(refusal_for(files=files)["refusal_reason"] == "os_release_field_malformed",
          "a malformed os-release field is refused")
    files[probe.OS_RELEASE_PATH] = b"ID=\xff\xfe\n"
    check(refusal_for(files=files)["refusal_reason"] == "os_release_field_malformed",
          "undecodable os-release bytes are refused")
    # An unknown refusal reason cannot be constructed.
    try:
        probe.ProbeRefusal("not_a_reason")
    except ValueError:
        pass
    else:
        check(False, "an unknown refusal reason must be rejected")


def test_refusal_emits_no_fingerprint_and_no_partial_data():
    empty = probe._base_body()
    for reason in probe.REFUSAL_REASONS:
        report = probe.refusal_report(reason, "/etc/os-release")
        check(report["verdict"] == "refused", "a refusal verdict is 'refused'")
        check(report["image_content_fingerprint"] is None,
              "a refusal carries no fingerprint")
        check(report["refusal_reason"] == reason, "the enum reason is carried")
        check(all(value is None for value in report["component_sha256"].values()),
              "a refusal carries no component digest")
        check(set(report["component_status"].values()) == {"not_measured"},
              "a refusal carries no component status but not_measured")
        check(report["immutable_paths"] == [], "a refusal carries no path rows")
        check(all(value is None for value in report["labels"].values()),
              "a refusal carries no label")
        check(report["counts"]["distribution_count"] == 0,
              "a refusal carries no distribution count")
        check(report["counts"] == empty["counts"], "a refusal carries the empty counts")
        check(probe.verify_seal(report), "a refusal report is sealed")
        check(len(probe.report_bytes(report)) <= probe.MAX_REPORT_BYTES,
              "a refusal report is under the size cap")
        text = probe.report_bytes(report).decode("ascii")
        for secret in ("1.26.4", "7.7.7", "bookworm", "12.7"):
            check(secret not in text, "a refusal leaks no measured value")
    # A refusal raised mid-run discards everything measured before it.
    sources = make_sources()
    sources["stat_path"] = lambda path: {"st_mode": 1, "st_size": 1, "st_mtime_ns": 1}
    report = probe.run_probe(**sources)
    check(report["refusal_reason"] == "stat_reader_malformed", "mid-run refusal")
    check(report["image_content_fingerprint"] is None, "no fingerprint after mid-run refusal")
    check(report["counts"]["distribution_count"] == 0,
          "the distributions read before the refusal are discarded")


def test_report_seal_and_size():
    report = probe.run_probe(**make_sources())
    data = probe.report_bytes(report)
    check(len(data) <= probe.MAX_REPORT_BYTES,
          "report is {} bytes, cap is {}".format(len(data), probe.MAX_REPORT_BYTES))
    check(probe.verify_seal(report), "the seal verifies")
    check(set(report) == set(probe.REPORT_KEYS), "the report key set is exactly REPORT_KEYS")
    tampered = dict(report)
    tampered["verdict"] = "refused"
    check(not probe.verify_seal(tampered), "a tampered report fails its seal")
    tampered = dict(report)
    tampered["image_content_fingerprint"] = "0" * 64
    check(not probe.verify_seal(tampered), "a swapped fingerprint fails the seal")
    check(not probe.verify_seal({"content_sha256": "0" * 64}), "a bare seal fails")
    check(not probe.verify_seal(None), "a non-dict fails the seal")
    check(json.loads(data.decode("ascii")) == report, "the report round-trips as JSON")
    # A body that grows past the cap refuses rather than emitting.
    original = probe._base_body
    def oversize_body():
        body = original()
        body["padding"] = "A" * probe.MAX_REPORT_BYTES
        return body
    probe._base_body = oversize_body
    try:
        grown = probe.run_probe(**make_sources())
        check(grown["refusal_reason"] == "report_oversize", "an oversize report refuses")
    finally:
        probe._base_body = original


def test_report_leaks_nothing():
    report = probe.run_probe(**make_sources())
    text = probe.report_bytes(report).decode("ascii")
    for version in ("1.26.4", "24.0", "4.12.2", "7.7.7"):
        check(version not in text, "no distribution version string is emitted")
    for name, _ in BASE_DISTRIBUTIONS:
        check(name.lower() not in text.lower(),
              "no arbitrary distribution name is emitted")
    for fragment in ("bookworm", "PRETTY_NAME", "12.7", "libc6", "2.36-9",
                     "install ok installed", "Sep 1 2024", "GCC"):
        check(fragment not in text, "no raw file content is emitted: " + fragment)
    check(report["labels"]["os_release_id"] == "debian", "the coarse ID label is emitted")
    check(report["labels"]["os_release_version_id"] == "12",
          "the coarse VERSION_ID label is emitted")
    check(report["labels"]["python_major_minor"] == "3.11",
          "only the coarse python major.minor is emitted")
    check("3.11.5" not in text, "the full python version is not emitted")
    for entry in report["immutable_paths"]:
        check(set(entry) == {"path", "status"}, "a path row carries no stat value")
        check(entry["path"] in probe.IMMUTABLE_PATHS,
              "only fixed whitelist paths are emitted")
        check(entry["status"] in probe.PATH_STATUSES, "path status is an enum")
    check(report["counts"]["distribution_count"] == len(BASE_DISTRIBUTIONS),
          "distributions are reported as an integer count")
    check(report["counts"]["unique_distribution_name_count"] == len(BASE_DISTRIBUTIONS),
          "unique distribution names are counted")
    for status in report["component_status"].values():
        check(status in probe.COMPONENT_STATUSES, "component status is an enum")
    check(report["section_B_prewrite_identity"] == "not_established_by_this_probe",
          "the report disclaims section B")
    check(report["cuda_qualification"] == "not_qualified_by_this_probe",
          "the report disclaims CUDA qualification")
    check(report["stage2_inputs"] == probe.ABSENT, "no Stage-2 input is present")
    # No 64-hex value other than the fingerprint, the seal and the fixed
    # structural digests may appear.
    allowed = {report["image_content_fingerprint"], report["content_sha256"],
               report["whitelist_sha256"], report["excluded_prefixes_sha256"]}
    allowed |= {value for value in report["component_sha256"].values() if value}
    import re as _re
    for found in _re.findall(r"[0-9a-f]{64}", text):
        check(found in allowed, "an unexpected 64-hex value appears in the report")


def test_probe_reads_no_environment_and_no_mtime():
    """The probe is a pure filesystem measurement: no env channel, no mtime."""
    source = Path(probe.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    banned_names = {"environ", "environb", "getenv", "getenvb", "putenv", "unsetenv"}
    banned_modules = {"subprocess", "socket", "urllib", "http", "ctypes",
                      "multiprocessing", "shutil", "glob", "tempfile"}
    # Docstrings are prose and are allowed to discuss what is excluded; only
    # code-level strings are scanned.
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docstrings.add(id(first.value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            check(node.attr not in banned_names,
                  "the probe must not touch os.{}".format(node.attr))
            check("mtime" not in node.attr,
                  "the probe must not read the attribute {}".format(node.attr))
            check(node.attr not in ("walk", "listdir", "scandir", "iterdir", "rglob"),
                  "the probe must not walk a directory: {}".format(node.attr))
        if isinstance(node, ast.Name):
            check(node.id not in banned_names,
                  "the probe must not reference {}".format(node.id))
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings):
            check("st_mtime" not in node.value,
                  "no code-level string in the probe names st_mtime")
            check("PYTHONDONTWRITEBYTECODE" not in node.value,
                  "the probe reads no environment variable")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [alias.name for alias in node.names]
            if isinstance(node, ast.ImportFrom):
                modules.append(node.module or "")
            for module in modules:
                check(module.split(".")[0] not in banned_modules,
                      "the probe must not import {}".format(module))
    # Behavioural, not only structural: a stat reader offering an mtime is refused
    # (covered above), and the accepted stat key set contains no mtime.
    rows, _emitted, _present = probe.measure_immutable_paths(
        lambda path: {"st_mode": 33261, "st_size": 10})
    for row in rows:
        check("st_mtime_ns" not in row and "st_mtime" not in row,
              "a measured stat row carries no mtime")
    check(probe.MTIME_STATUS == "no_mtime_is_read_by_any_component",
          "the report states the mtime policy")
    # The probe never names a Kaggle, GPU or network entry point.
    for banned in ("nvcc", "nvidia", "kaggle.api", "requests.", "urlopen"):
        check(banned not in source.lower().replace("/kaggle/working", ""),
              "the probe source must not reference {}".format(banned))


def test_main_writes_exactly_one_file():
    with tempfile.TemporaryDirectory() as directory:
        working = Path(directory)
        code = probe.main(working_dir=working, sources=make_sources())
        check(code == 0, "a measured run returns 0")
        files = list(working.iterdir())
        check(len(files) == 1 and files[0].name == probe.RECEIPT_NAME,
              "a measured run writes exactly one receipt")
        receipt = json.loads(files[0].read_text(encoding="ascii"))
        check(probe.verify_seal(receipt), "the written receipt is sealed")
        check(receipt["verdict"] == "fingerprint_measured", "the receipt carries the verdict")
        check(probe.main(working_dir=working, sources=make_sources()) == 2,
              "a second run refuses rather than overwriting")
        check(len(list(working.iterdir())) == 1, "still exactly one file")
    with tempfile.TemporaryDirectory() as directory:
        working = Path(directory)
        sources = make_sources(files={})
        code = probe.main(working_dir=working, sources=sources)
        check(code == 1, "a refused run returns 1")
        files = list(working.iterdir())
        check(len(files) == 1 and files[0].name == probe.FAILURE_NAME,
              "a refused run writes exactly one failure log")
        content = files[0].read_bytes()
        check(content.startswith(probe.FAILURE_HEADER), "the failure header is present")
        check(b'"image_content_fingerprint":null' in content,
              "the failure log carries no fingerprint")
    with tempfile.TemporaryDirectory() as directory:
        missing = Path(directory) / "absent"
        check(probe.main(working_dir=missing, sources=make_sources()) == 2,
              "a missing working directory refuses")
        check(not missing.exists(), "a missing working directory is not created")


def test_import_writes_nothing():
    module_dir = Path(probe.__file__).resolve().parent
    before = sorted(entry.name for entry in module_dir.iterdir())
    with tempfile.TemporaryDirectory() as directory:
        cwd = os.getcwd()
        os.chdir(directory)
        try:
            importlib.reload(probe)
        finally:
            os.chdir(cwd)
        check(not list(Path(directory).iterdir()),
              "importing the probe writes nothing in the working directory")
    after = sorted(entry.name for entry in module_dir.iterdir())
    check(before == after, "importing the probe creates no file beside it")
    check(not (module_dir / "__pycache__").exists(), "no __pycache__ is created")


def main() -> int:
    tests = (
        test_determinism,
        test_sensitivity,
        test_excluded_prefixes_are_refused_not_skipped,
        test_missing_optional_files_are_deterministic,
        test_bad_readers_are_refused,
        test_refusal_emits_no_fingerprint_and_no_partial_data,
        test_report_seal_and_size,
        test_report_leaks_nothing,
        test_probe_reads_no_environment_and_no_mtime,
        test_main_writes_exactly_one_file,
        test_import_writes_nothing,
    )
    for test in tests:
        test()
        print("ok  " + test.__name__)
    if FAILURES:
        print("{} fixture check(s) FAILED".format(len(FAILURES)), file=sys.stderr)
        return 1
    print("All fixtures passed ({} tests).".format(len(tests)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
