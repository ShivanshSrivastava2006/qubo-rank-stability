#!/usr/bin/env python3
"""Verify Gate-9 image-channel discovery probe fixtures.

Must cover:
- metadata drift including internet on and image pin
- sensitive environment names excluded before value read
- oversize/malformed selected values
- GPU absent
- hint caps
- no raw value leaks
- output size/counter bounds
- clean receipt/failure path
- no-overwrite
- exact one-file output

Run with:
PYTHONDONTWRITEBYTECODE=1 python3 verify_g9_cuda_image_channel_probe_fixtures.py
PYTHONDONTWRITEBYTECODE=1 python3 -O verify_g9_cuda_image_channel_probe_fixtures.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Important: Run fixtures with PYTHONDONTWRITEBYTECODE=1
if not os.environ.get("PYTHONDONTWRITEBYTECODE"):
    print("WARNING: PYTHONDONTWRITEBYTECODE is not set.", file=sys.stderr)

import stage2_cuda_image_channel_probe as probe
import build_g9_cuda_image_channel_probe_bundle as builder
import ast

def check(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL: {message}", file=sys.stderr)
        sys.exit(1)

def check_raises(exception_type, exception_reason, func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except exception_type as exc:
        if exc.reason != exception_reason:
            print(f"FAIL: expected reason {exception_reason}, got {exc.reason}", file=sys.stderr)
            sys.exit(1)
        return exc
    print(f"FAIL: did not raise {exception_type.__name__} with {exception_reason}", file=sys.stderr)
    sys.exit(1)

def test_metadata_drift():
    good = dict(probe.EXPECTED_METADATA_POLICY)
    good["id"] = "user/slug"
    good["title"] = "title"
    good["code_file"] = "code.py"
    check(probe.check_metadata(good) is None, "valid metadata passes")
    
    bad_internet = dict(good)
    bad_internet["enable_internet"] = True
    check(probe.check_metadata(bad_internet) == "metadata_internet_enabled", "internet on refuses")
    
    bad_pin = dict(good)
    bad_pin["docker_image"] = "some/image:tag"
    check(probe.check_metadata(bad_pin) == "metadata_image_pin_present", "image pin refuses")
    
    bad_drift = dict(good)
    bad_drift["enable_gpu"] = False
    check(probe.check_metadata(bad_drift) == "metadata_drift", "drift refuses")

def test_sensitive_names_excluded_before_value_read():
    read_names = []
    def list_env_names():
        return ("GOOD_IMAGE_ENV", "BAD_SECRET_IMAGE_ENV", "TOKEN_IMAGE")
    
    def read_env_value(name):
        read_names.append(name)
        return "some_value"
    
    count, excluded, selected = probe.select_names(list_env_names)
    check(count == 3, "count is 3")
    check(excluded == 2, "2 excluded")
    check(selected == ["GOOD_IMAGE_ENV"], "only good selected")
    check(not read_names, "read not called during select_names")
    
    # Also test scan_environment directly
    scan_res = probe.scan_environment(list_env_names, read_env_value)
    check(scan_res["excluded_sensitive_name_count"] == 2, "scan_environment excluded 2 names")
    check(scan_res["selected_name_count"] == 1, "scan_environment selected 1 name")
    check(read_names == ["GOOD_IMAGE_ENV"],
          "scan_environment reads only the selected safe name")

def test_oversize_malformed_selected_values():
    check_raises(probe.ProbeRefusal, "selected_value_malformed", probe.classify_value, 123)
    check_raises(probe.ProbeRefusal, "selected_value_oversize", probe.classify_value, "A" * (probe.MAX_VALUE_BYTES + 1))
    check_raises(probe.ProbeRefusal, "selected_value_malformed", probe.classify_value, "bad\nchars")

def test_gpu_absent():
    check_raises(probe.ProbeRefusal, "gpu_device_absent", probe.check_gpu, lambda: 0)
    check_raises(probe.ProbeRefusal, "gpu_device_reader_malformed", probe.check_gpu, lambda: -1)

def test_hint_caps():
    # If hint data exceeds limit, refusal should occur in inspect_hints or probe run.
    def read_hint_oversize(path, limit):
        return b"A" * (limit + 1)
    
    check_raises(probe.ProbeRefusal, "hint_file_oversize", probe.inspect_hints, read_hint_oversize)

def test_no_raw_value_leaks():
    unrelated_hash = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
    report = probe.run_probe(
        probe.EXPECTED_METADATA_POLICY,
        list_env_names=lambda: ("MY_IMAGE_DIGEST",),
        read_env_value=lambda name: unrelated_hash,
        count_gpu_devices=lambda: 1
    )
    raw_str = json.dumps(report)
    check("MY_IMAGE_DIGEST" in raw_str, "name is present")
    check("1111111111111111111111111111111111111111111111111111111111111111" not in raw_str, "raw hex not leaked")
    check(report["verdict"] == "digest_shaped_value_without_expected_match", "other digest verdict")

def test_output_size_counter_bounds():
    def list_env_names():
        return [f"IMAGE_ENV_{i}" for i in range(probe.MAX_ENVIRONMENT_NAMES + 1)]
    check_raises(probe.ProbeRefusal, "environment_name_overcount", probe.select_names, list_env_names)
    
    def list_many_selected():
        return [f"IMAGE_ENV_{i}" for i in range(probe.MAX_SELECTED_NAMES + 1)]
    check_raises(probe.ProbeRefusal, "selected_name_overcount", probe.select_names, list_many_selected)

    def list_duplicate_names():
        return ["IMAGE_ENV", "IMAGE_ENV"]
    check_raises(probe.ProbeRefusal, "environment_name_malformed", probe.select_names, list_duplicate_names)

    def list_malformed_names():
        return ["IMAGE-ENV"]
    check_raises(probe.ProbeRefusal, "selected_name_malformed", probe.select_names, list_malformed_names)

    # Test MAX_REPORT_BYTES refusal
    original_base = probe._base_body
    def huge_base():
        body = original_base()
        body["padding"] = "A" * probe.MAX_REPORT_BYTES
        return body
    probe._base_body = huge_base
    try:
        rep = probe.run_probe(
            probe.EXPECTED_METADATA_POLICY,
            list_env_names=lambda: (),
            read_env_value=lambda n: "",
            count_gpu_devices=lambda: 1
        )
        check(rep["refusal_reason"] == "report_oversize", "report_oversize refusal triggered")
    finally:
        probe._base_body = original_base

def test_clean_receipt_failure_path_no_overwrite_exact_one_file():
    with tempfile.TemporaryDirectory() as d:
        wdir = Path(d)
        
        # Test 1: Clean receipt
        sources = {
            "list_env_names": lambda: ("MY_IMAGE_ENV",),
            "read_env_value": lambda name: "not_a_digest",
            "count_gpu_devices": lambda: 1,
            "read_hint": lambda p, l: None,
            "internet_observation": "not_observed"
        }
        ret = probe.main(working_dir=wdir, sources=sources)
        check(ret == 0, "successful execution returns 0")
        
        files = list(wdir.iterdir())
        check(len(files) == 1, "exact one file output")
        check(files[0].name == probe.RECEIPT_NAME, "receipt file created")
        
        # Test 2: No overwrite
        ret2 = probe.main(working_dir=wdir, sources=sources)
        check(ret2 == 2, "no-overwrite refuses")
        check(len(list(wdir.iterdir())) == 1, "still only one file")
        
    with tempfile.TemporaryDirectory() as d:
        wdir = Path(d)
        
        # Test 3: Failure path
        fail_sources = {
            "list_env_names": lambda: ("MY_IMAGE_ENV",),
            "read_env_value": lambda name: "not_a_digest",
            "count_gpu_devices": lambda: 0, # absent GPU triggers refusal
            "read_hint": lambda p, l: None,
            "internet_observation": "not_observed"
        }
        ret_fail = probe.main(working_dir=wdir, sources=fail_sources)
        check(ret_fail == 1, "refusal execution returns 1")
        
        files = list(wdir.iterdir())
        check(len(files) == 1, "exact one file output for failure")
        check(files[0].name == probe.FAILURE_NAME, "failure file created")
        content = files[0].read_bytes()
        check(content.startswith(probe.FAILURE_HEADER), "failure header present")


def test_builder_and_launcher():
    import base64
    import hashlib
    with tempfile.TemporaryDirectory() as d:
        outdir = Path(d)
        
        # Test builder failure on invalid kaggle user
        old_argv = sys.argv
        try:
            sys.argv = ["build", "--kaggle-user", "invalid/user", "--output-dir", str(outdir)]
            ret_fail = builder.main()
            check(ret_fail == 1, "builder fails on invalid user slug")
            check(not list(outdir.iterdir()), "invalid user leaves output empty")

            # Test builder success
            sys.argv = ["build", "--kaggle-user", "test-user", "--output-dir", str(outdir)]
            ret = builder.main()
            check(ret == 0, "builder succeeds")
        finally:
            sys.argv = old_argv
        
        metadata = json.loads((outdir / builder.METADATA_NAME).read_text())
        check(metadata["id"] == "test-user/g9-cuda-image-channel-probe", "metadata id valid")
        check(metadata["enable_internet"] is False, "metadata internet off")
        check("docker_image" not in metadata, "metadata image unpinned")
        check(builder.canonical({k: v for k, v in metadata.items()
                                 if k not in builder.METADATA_IDENTITY_KEYS}) ==
              builder.canonical(builder.EXPECTED_METADATA_POLICY),
              "complete reviewed metadata policy matches")
        check(set(outdir.iterdir()) == {outdir / builder.METADATA_NAME,
                                       outdir / builder.SOURCE_NAME},
              "builder emits exactly two bundle files")
        
        launcher_code = (outdir / builder.SOURCE_NAME).read_text()
        check("import subprocess" in launcher_code, "launcher imports subprocess")
        
        # Parse AST to ensure the payload is executed and checked
        tree = ast.parse(launcher_code)
        has_hashlib = any(isinstance(n, ast.Import) and any(alias.name == "hashlib" for alias in n.names) for n in tree.body)
        check(has_hashlib, "launcher uses hashlib")
        
        # The launcher embeds the expected hash
        check(f'EXPECTED_SHA256 = "{builder.EXPECTED_SOURCE_SHA256}"' in launcher_code, "embeds exact probe hash")
        
        # Extract the embedded b64 payload and decode it
        prefix = 'PAYLOAD_B64 = "'
        b64_start = launcher_code.find(prefix) + len(prefix)
        b64_end = launcher_code.find('"', b64_start)
        b64_str = launcher_code[b64_start:b64_end]
        payload = base64.b64decode(b64_str)
        check(hashlib.sha256(payload).hexdigest() == builder.EXPECTED_SOURCE_SHA256, "payload hash matches")
        check(payload == (Path(builder.__file__).parent /
                          "stage2_cuda_image_channel_probe.py").read_bytes(),
              "embedded payload equals reviewed source bytes")

        # The generated launcher's guard is exercised without launching the
        # hardcoded /kaggle/working subprocess: a one-byte payload corruption
        # must refuse before any subprocess or output path is reached.
        namespace = {"__name__": "fixture_import"}
        exec(compile(launcher_code, "<generated-launcher>", "exec"), namespace)
        namespace["PAYLOAD_B64"] = base64.b64encode(payload + b"x").decode("ascii")
        check(namespace["main"]() == 1, "generated launcher refuses corrupted payload")
        
        # Simulate payload execution instead of running the launcher.
        # The generated launcher is NOT executed in a subprocess because it
        # strictly invokes the probe with no arguments, causing it to write to
        # the hardcoded /kaggle/working directory on the host. We use a simulation
        # to verify that the extracted payload would run correctly when provided
        # an injected safe working directory.
        with tempfile.TemporaryDirectory() as wd:
            sim_wdir = Path(wd)
            # We execute the probe's logic programmatically rather than as a subprocess.
            # This exercises the payload's behavior (via main()) but skips the launcher's
            # subprocess.run wrapper and the hardcoded /kaggle/working path.
            sources = {
                "list_env_names": lambda: ("MY_IMAGE_ENV",),
                "read_env_value": lambda name: "not_a_digest",
                "count_gpu_devices": lambda: 1,
                "read_hint": lambda p, l: None,
                "internet_observation": "not_observed"
            }
            # We already imported the probe. Execute its main with the safe dir.
            ret_probe = probe.main(working_dir=sim_wdir, sources=sources)
            check(ret_probe == 0, "simulated payload run succeeds")
            files = list(sim_wdir.iterdir())
            check(len(files) == 1, "simulated run produces exact one receipt")

def main():
    test_metadata_drift()
    test_sensitive_names_excluded_before_value_read()
    test_oversize_malformed_selected_values()
    test_gpu_absent()
    test_hint_caps()
    test_no_raw_value_leaks()
    test_output_size_counter_bounds()
    test_clean_receipt_failure_path_no_overwrite_exact_one_file()
    test_builder_and_launcher()
    print("All fixtures passed.")

if __name__ == "__main__":
    main()
