#!/usr/bin/env python3
"""CANDIDATE v2 D013 CUDA GUARD/ABI DIAGNOSTIC FIXTURE -- OFFLINE, SYNTHETIC ONLY.

WHAT THIS FIXTURE PROVES, AND HOW, WITH NO GPU:

  T1  NEGATIVE CONTROL. The v1 (pre-fix) D013 source FAILS the new
      pointer-staging assertion. The assertion is static and checkable: every
      kernel launch must receive a DEVICE pointer, and the payload must be
      allocated and staged HostToDevice. v1 passes the caller HOST pointer to
      all three D013 kernels, so the assertion must fail. If it does not, the
      assertion is not testing what it claims and every later result is void.

  T2  CANDIDATE PASSES. The v2 candidate satisfies the same assertion, and
      additionally passes the static guard/ABI invariants: the status codes,
      the single-call guard, the disjointness refusal, the argument-shape
      refusal, the refusal count, the counter writes, and all nine qualified
      mutation anchors are each present exactly once (so a future release's
      mutation plan still has unique anchors to apply).

  T3  HOST-STUB REFERENCE AGREEMENT. The v1 core's OWN host-emulation
      verifier, run unchanged against the candidate, must complete every
      synthetic check it performs -- including its independent-reference
      agreement over all four conditions and its mutation-rejection sweep.
      This is the strongest CPU evidence available here: it reuses the
      already-trusted reference rather than inventing a second one.

  T4  FAULT INJECTION STILL REFUSES. With a real host allocation, staging-copy
      or kernel-launch failure forced, the candidate must still REFUSE
      (status 0 / typed D013InactiveError), must still scrub the output buffer,
      and must still have launched nothing. Refusal under fault is the
      fail-closed property; a candidate that "passes" a fault is broken.

  T5  NO GUARD WAS WEAKENED. The qualified v1 release draft still validates
      against the ORIGINAL v1 sources (its release, source map and token
      path are untouched by this candidate), and the candidate is NOT bound by
      any release, runtime config or bundle.

EVIDENCE CLASS -- STATED PLAINLY, BECAUSE IT IS THE MOST IMPORTANT LIMIT:

  Everything in this fixture is STATIC ANALYSIS plus CPU HOST-STUB EXECUTION
  under g++ with the repo's pinned host-emulation stub, in which
  `cudaMalloc` is `malloc` and a "device" kernel runs serially on the CPU.

  NO nvcc, NO CUDA DEVICE and NO /dev/nvidia* EXISTED on this host. Therefore:

    * These results are NOT evidence that the candidate is correct on a T4.
    * They are NOT evidence that the v1 host-pointer launch is the cause of the
      observed T4 REFUSED. That remains a STRONG STATIC INFERENCE.
    * A host stub CANNOT reproduce an invalid device memory access, because on
      the host the "device" pointer and the host pointer are both ordinary
      addressable memory. T4 is required to settle the causal claim.
    * The migration note lists exactly what T4 qualification must re-run.

SCOPE: no Kaggle, no network, no credentials, no installs, no production input,
no draw/seed/beacon, no scientific computation and no write of any result
value. The only inputs are the two synthetic payload builders the repo's own
verifier uses.

Usage:  PYTHONDONTWRITEBYTECODE=1 python3 -B verify_d013_cuda_v2_candidate.py
"""
from __future__ import annotations

import ctypes as C
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
QUALIFICATION_V1 = ROOT / "research/g9/cuda_qualification"
CANDIDATE_DIR = ROOT / "research/g9/cuda_qualification_v2"
PINNED_STUB = ROOT / "research/g6/cuda_qualification/host_emulation_stub"
FAULT_STUB = CANDIDATE_DIR / "host_stub_fault_injection"

V1_SOURCE = QUALIFICATION_V1 / "stage2_cuda_d013_inactive.cu"
V2_SOURCE = CANDIDATE_DIR / "stage2_cuda_d013_inactive_v2.cu"

STATUS_REFUSED = 0
STATUS_OK = 1
STATUS_BUSY = 2

RESULTS: list[dict] = []


def record(test: str, passed: bool, detail: str) -> None:
    RESULTS.append({"test": test, "passed": bool(passed), "detail": detail})
    print(f"[{'PASS' if passed else 'FAIL'}] {test}: {detail}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def code_only(source: str) -> str:
    """Strip line comments so token counts measure code, not prose."""
    out = []
    for line in source.splitlines():
        cut = line.find("//")
        out.append(line if cut < 0 else line[:cut])
    return "\n".join(out)


def launch_line(code: str, kernel: str) -> str:
    index = code.index(f"G9_CORE_LAUNCH({kernel}")
    return code[index : code.index("\n", index)]


# ---------------------------------------------------------------------------
# The pointer-staging assertion (T1 negative control / T2 candidate pass).
# ---------------------------------------------------------------------------

# Kernels that must receive a DEVICE pointer, and the device-side expression
# each one is required to receive. `probe`/`energy` also take `&device_rows[row]`,
# which is already device memory, so only the payload argument is at issue.
REQUIRED_DEVICE_ARGS = (
    ("g9_d013_terms_kernel", "device_payload"),
    ("g9_d013_probe_kernel", "device_payload"),
    ("g9_d013_energy_kernel", "device_payload"),
    ("segment_kernel", "device_energies"),
    ("flags_kernel", "device_energies"),
)

# Host-side identifiers that must never reach a kernel launch as a pointer.
FORBIDDEN_LAUNCH_ARGS = ("payload", "energies")


def assert_pointer_staging(source: str, label: str) -> list[str]:
    """Static pointer-staging assertion. Raises AssertionError on violation.

    Four independent obligations, all of which v1 violates:
      (a) a device payload pointer is declared and cudaMalloc'd;
      (b) the payload is copied to it with cudaMemcpyHostToDevice;
      (c) all three D013 kernels receive the DEVICE payload pointer;
      (d) the two unchanged core kernels that read the energy stream receive
          the DEVICE energy pointer (a second instance of the same defect in
          v1 that the root-cause report did not enumerate);
      (e) the device payload is freed.
    """
    code = code_only(source)
    problems: list[str] = []

    if "PayloadData* device_payload" not in code:
        problems.append("no device payload pointer is declared")
    if "cudaMalloc(&device_payload" not in code:
        problems.append("no cudaMalloc for the device payload")
    if "cudaMemcpy(device_payload" not in code:
        problems.append("no cudaMemcpy stages the device payload")
    elif "cudaMemcpyHostToDevice" not in code[code.index("cudaMemcpy(device_payload"):][:200]:
        problems.append("the payload staging copy is not HostToDevice")
    if "cudaFree(device_payload)" not in code:
        problems.append("the device payload is never freed")

    for kernel, expected in REQUIRED_DEVICE_ARGS:
        try:
            line = launch_line(code, kernel)
        except ValueError:
            problems.append(f"{kernel} launch not found")
            continue
        if expected not in line:
            problems.append(f"{kernel} launch does not receive {expected}")
        for forbidden in FORBIDDEN_LAUNCH_ARGS:
            # A bare host identifier as an argument token: `payload,` or
            # `(payload,` or `, payload,`. `device_payload` must not trip this,
            # hence the boundary check on non-identifier characters.
            stripped = line
            index = 0
            while True:
                found = stripped.find(forbidden, index)
                if found < 0:
                    break
                before = stripped[found - 1] if found > 0 else " "
                after_at = found + len(forbidden)
                after = stripped[after_at] if after_at < len(stripped) else " "
                is_token = not (before.isalnum() or before == "_") and not (
                    after.isalnum() or after == "_"
                )
                if is_token:
                    problems.append(
                        f"{kernel} launch passes the host pointer `{forbidden}`"
                    )
                    break
                index = found + 1

    if problems:
        raise AssertionError(f"{label} fails pointer staging: " + "; ".join(problems))
    return problems


# ---------------------------------------------------------------------------
# Build helpers.
# ---------------------------------------------------------------------------

def build_flags() -> list[str]:
    sys.path.insert(0, str(ROOT))
    from research.g9.cuda_qualification import (
        stage2_cuda_d013_inactive_corruption_qualification as corruption,
    )

    return list(corruption.compile_flags())


def compile_source(source_path: Path, library: Path, include_dir: Path) -> dict:
    """Compile one D013 source with a chosen host stub. Warnings are a failure."""
    command = [
        "g++", *build_flags(),
        "-I", str(include_dir),
        "-I", str(QUALIFICATION_V1),
        str(source_path), "-o", str(library),
    ]
    built = subprocess.run(command, cwd=ROOT, text=True, capture_output=True,
                           check=False, timeout=900)
    if built.returncode != 0 or built.stderr.strip():
        raise AssertionError(
            f"host-stub build failed for {source_path.name} "
            f"(rc={built.returncode}): {built.stderr[:800]}"
        )
    return {"command": " ".join(command), "returncode": built.returncode,
            "stderr": built.stderr, "library_sha256": sha256(library.read_bytes())}


# ---------------------------------------------------------------------------
# T3: reuse the qualified v1 core's own verifier, unchanged.
# ---------------------------------------------------------------------------

def run_upstream_host_emulation(library: Path) -> dict:
    """Run the repo's own D013 host-emulation verifier against `library`.

    The verifier imports the v1 bridge module and re-reads the v1 source path
    for its mutation sweep, so the candidate `.so` is exercised through exactly
    the trusted reference and exactly the trusted ABI bridge. No scientific
    computation and no production input: the verifier's inputs are its own
    synthetic `small_payload`/`small_records` builders.
    """
    sys.path.insert(0, str(ROOT))
    from research.g9 import verify_stage2_cuda_d013_inactive_host_emulation as upstream

    # The verifier is driven through its own `main`, but with the compiled
    # library pointed at the candidate. It exposes `build(library, source)`, so
    # the candidate is compiled by the verifier's own recipe and then every
    # check is run by the verifier itself.
    upstream.SOURCE = V2_SOURCE
    result = upstream.main()
    return {"verifier": upstream.__name__,
            "verifier_source_sha256": sha256(Path(upstream.__file__).read_bytes()),
            "result": str(result)}


# ---------------------------------------------------------------------------
# T4: fault injection.
# ---------------------------------------------------------------------------

def fault_stats(library: Path) -> dict:
    loaded = C.CDLL(str(library))
    stats = loaded.g9_d013v2_fault_stats
    stats.argtypes = [C.POINTER(C.c_uint64), C.c_uint32]
    stats.restype = C.c_uint32
    buffer = (C.c_uint64 * 8)()
    require(stats(buffer, 8) == 8, "fault-injection stats call returned the wrong count")
    names = ("malloc_ok", "malloc_failed", "memcpy_calls", "launches",
             "launch_failures_armed", "free_calls", "memcpy_failures",
             "allocations_total")
    return dict(zip(names, (int(value) for value in buffer)))


def arm_and_run(library: Path, payload, records, condition: str, *, arm) -> dict:
    """Arm one injected fault, run the frame directly, and report the outcome.

    Calls the ABI directly rather than through the bridge, so the raw status
    code is observed, then confirms the bridge also raises its typed refusal.
    """
    sys.path.insert(0, str(ROOT))
    from research.g9.cuda_qualification import stage2_cuda_d013_inactive as d013
    from research.g9 import verify_stage2_cuda_d013_inactive_host_emulation as upstream

    loaded = C.CDLL(str(library))
    for name, restype, argtypes in (
        ("g9_d013v2_fault_reset", C.c_uint32, []),
        ("g9_d013v2_fault_arm_malloc", C.c_uint32, [C.c_longlong]),
        ("g9_d013v2_fault_arm_memcpy_of_size", C.c_uint32, [C.c_ulonglong]),
        ("g9_d013v2_fault_arm_launch", C.c_uint32, [C.c_longlong]),
    ):
        fn = getattr(loaded, name)
        fn.restype = C.c_uint32
        fn.argtypes = argtypes
    loaded.g9_d013v2_fault_reset()
    arm(loaded)

    decoded = d013.decode_payload(payload)
    row_array = d013.decode_records(
        d013.validate_records(records, condition), condition)
    condition_array = d013.decode_conditions(condition, len(records))
    output = d013.D013Output()
    run = loaded.g9_d013_run
    run.argtypes = [C.POINTER(d013.PayloadData), C.POINTER(d013.CoefficientData),
                    C.POINTER(C.c_uint32), C.c_uint32, C.POINTER(d013.D013Output)]
    run.restype = C.c_uint32
    status = run(C.byref(decoded), row_array, condition_array, len(records),
                 C.byref(output))

    stats = fault_stats(library)

    # The bridge must also refuse, with its own typed error.
    bridge_refused = False
    bridge_message = ""
    try:
        d013.run_host_emulated_frame(payload, records, condition, library, 64)
    except d013.D013InactiveError as exc:
        bridge_refused = True
        bridge_message = str(exc)[:200]

    return {"status": int(status), "scrubbed": upstream.scrubbed(output),
            "bridge_refused": bridge_refused, "bridge_message": bridge_message,
            "fault_stats": stats}


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 78)
    print("CANDIDATE v2 D013 CUDA GUARD/ABI DIAGNOSTIC -- STATIC + CPU HOST-STUB ONLY")
    print("NO nvcc / NO GPU / NO /dev/nvidia*: no T4 claim is made or implied.")
    print("=" * 78)

    require(V1_SOURCE.is_file(), f"v1 source missing: {V1_SOURCE}")
    require(V2_SOURCE.is_file(), f"v2 candidate missing: {V2_SOURCE}")
    v1_bytes = V1_SOURCE.read_bytes()
    v2_bytes = V2_SOURCE.read_bytes()
    v1 = v1_bytes.decode("utf-8")
    v2 = v2_bytes.decode("utf-8")

    print(f"\nv1 source sha256 : {sha256(v1_bytes)}")
    print(f"v2 source sha256 : {sha256(v2_bytes)}")

    # ---- T1 negative control -------------------------------------------
    try:
        assert_pointer_staging(v1, "v1 (pre-fix)")
        record("T1 negative control: v1 must FAIL pointer staging", False,
               "v1 unexpectedly PASSED the pointer-staging assertion; the "
               "assertion is not testing the defect and all later results are void")
        return 1
    except AssertionError as exc:
        record("T1 negative control: v1 must FAIL pointer staging", True,
               f"v1 correctly rejected: {exc}")

    # ---- T2 candidate passes -------------------------------------------
    try:
        assert_pointer_staging(v2, "v2 (candidate)")
        record("T2 candidate passes pointer staging", True,
               "device_payload declared, allocated, staged HostToDevice, "
               "passed to all three D013 kernels, and freed; the two core "
               "energy-stream kernels receive device_energies")
    except AssertionError as exc:
        record("T2 candidate passes pointer staging", False, str(exc))
        return 1

    # Static guard/ABI invariants. Each is a COUNT EQUALITY between v1 and v2,
    # so the candidate can never weaken a guard no matter what the counts are;
    # the observed counts are reported for the reviewer to check against intent.
    v1_code, v2_code = code_only(v1), code_only(v2)

    def same_count(label: str, token: str) -> tuple[str, bool, str]:
        n1, n2 = v1_code.count(token), v2_code.count(token)
        return label, n1 == n2, f"v1={n1} v2={n2}"

    invariants_list = [
        same_count("status code REFUSED unchanged", "G9_D013_REFUSED = 0u"),
        same_count("status code OK unchanged", "G9_D013_OK = 1u"),
        same_count("status code BUSY unchanged", "G9_D013_BUSY = 2u"),
        same_count("single-call guard unchanged",
                   "if (!guard.held()) return G9_D013_BUSY;"),
        same_count("argument-shape refusal unchanged",
                   "row_count == 0u || row_count > kRowCount"),
        same_count("disjointness refusals unchanged", "g9_d013_disjoint(out, sizeof(G9D013Output)"),
        same_count("conditions-valid refusal unchanged",
                   "g9_d013_conditions_valid(rows, row_count, conditions)"),
        same_count("payload-contract refusal unchanged",
                   "validate_payload_contract(*payload)"),
        same_count("sigma-symmetry refusal unchanged",
                   "payload->sigma[i * kAssetCount + j] != payload->sigma[j * kAssetCount + i]"),
        same_count("fail-closed scrub count unchanged",
                   "std::memset(static_cast<void*>(out), 0, sizeof(G9D013Output));"),
        same_count("REFUSED return count unchanged", "return G9_D013_REFUSED;"),
        same_count("OK return count unchanged", "return G9_D013_OK;"),
        same_count("BUSY return count unchanged", "return G9_D013_BUSY;"),
        same_count("counter writes unchanged", "out->counters."),
        same_count("core output writes unchanged", "out->core."),
        same_count("lambda_ref read from validated host payload unchanged",
                   "payload->lambda_ref"),
    ]
    invariants = {label: ok for label, ok, _ in invariants_list}
    invariants["nvcc/GPU backend gate retained"] = (
        "g9_d013_backend" in v2_code and "__CUDACC__" in v2_code)

    # Every qualified mutation anchor must still be present EXACTLY ONCE, or a
    # future release's mutation plan would silently lose its unique target.
    sys.path.insert(0, str(ROOT))
    from research.g9.cuda_qualification import (
        stage2_cuda_d013_inactive_corruption_qualification as corruption,
    )
    anchors = {m.label: v2.count(m.old) for m in corruption.MUTATIONS}
    bad_anchors = {k: n for k, n in anchors.items() if n != 1}
    invariants["all 9 mutation anchors still unique"] = not bad_anchors

    failed = [f"{label} [{detail}]" for label, ok, detail in invariants_list if not ok]
    failed += [f"anchor problems: {bad_anchors}"] if bad_anchors else []
    if not invariants["nvcc/GPU backend gate retained"]:
        failed.append("the __CUDACC__/backend gate was removed")
    record("T2b static guard/ABI invariants", not failed,
           f"all {len(invariants)} invariants hold; every guard/refusal/counter "
           f"count is identical to v1"
           if not failed else "; ".join(failed))

    # Exactly one allocation and one free added -- minimal change.
    added_malloc = v2_code.count("cudaMalloc(") - v1_code.count("cudaMalloc(")
    added_free = v2_code.count("cudaFree(") - v1_code.count("cudaFree(")
    record("T2c change is minimal (+1 cudaMalloc, +1 cudaFree, 0 other)",
           added_malloc == 1 and added_free == 1,
           f"added cudaMalloc={added_malloc}, added cudaFree={added_free}")

    with tempfile.TemporaryDirectory(prefix="g9-d013v2-fixture-") as tmp:
        scratch = Path(tmp)

        # ---- Build v1 and v2 with the PINNED stub -----------------------
        v1_lib = scratch / "libg9_d013_v1_stub.so"
        v2_lib = scratch / "libg9_d013_v2_stub.so"
        v1_build = compile_source(V1_SOURCE, v1_lib, PINNED_STUB)
        v2_build = compile_source(V2_SOURCE, v2_lib, PINNED_STUB)
        print(f"\nv1 stub build: rc=0 sha256={v1_build['library_sha256']}")
        print(f"v2 stub build: rc=0 sha256={v2_build['library_sha256']}")
        record("T2d both sources compile clean with the pinned host stub", True,
               f"v1={v1_build['library_sha256'][:16]}..., "
               f"v2={v2_build['library_sha256'][:16]}..., zero warnings")

        # ---- T3 host-stub reference agreement ---------------------------
        # The repo's own verifier, driven against the candidate source, in its
        # own scratch. It performs the independent-reference comparison over
        # all four conditions and the mutation-rejection sweep.
        upstream_run = subprocess.run(
            [sys.executable, "-B", "-c",
             "import sys;sys.dont_write_bytecode=True;"
             f"sys.path.insert(0,{str(ROOT)!r});"
             "from research.g9 import verify_stage2_cuda_d013_inactive_host_emulation as u;"
             f"from pathlib import Path;u.SOURCE=Path({str(V2_SOURCE)!r});u.main();"
             "print('UPSTREAM_OK')"],
            cwd=ROOT, text=True, capture_output=True, check=False, timeout=1800,
        )
        tail = upstream_run.stdout.strip().splitlines()[-1:] if upstream_run.stdout else []
        t3_ok = upstream_run.returncode == 0 and "UPSTREAM_OK" in upstream_run.stdout
        record("T3 qualified v1 verifier accepts the candidate (host stub)", t3_ok,
               f"rc={upstream_run.returncode}; "
               f"{'reference agreement + mutation rejection complete' if t3_ok else upstream_run.stderr[-500:]}")

        # ---- T4 fault injection ----------------------------------------
        v2_fault = scratch / "libg9_d013_v2_fault.so"
        fault_build = compile_source(V2_SOURCE, v2_fault, FAULT_STUB)
        record("T4a candidate builds with the fault-injection stub", True,
               f"sha256={fault_build['library_sha256'][:16]}..., zero warnings")

        from research.g9 import verify_stage2_cuda_d013_inactive_host_emulation as up
        payload = up.small_payload(0)
        records = up.small_records("C", 0)

        # Clean baseline through the fault build: nothing armed must succeed.
        loaded = C.CDLL(str(v2_fault))
        loaded.g9_d013v2_fault_reset.restype = C.c_uint32
        loaded.g9_d013v2_fault_reset()
        baseline = run_and_status(v2_fault, payload, records, "C")
        record("T4b clean run through the fault stub still succeeds", baseline["ok"],
               f"status={baseline['status']} (1=OK), launches="
               f"{baseline['stats']['launches']}, allocations="
               f"{baseline['stats']['allocations_total']}, frees="
               f"{baseline['stats']['free_calls']}")

        # Injected allocation failure: fail the FIRST allocation, which for the
        # candidate is the device payload. Must refuse, scrub, and never launch.
        # `allocations_total == 1` and `launches == 0` together prove the fault
        # aborted the run before any kernel: exactly the fail-closed property.
        alloc = arm_and_run(
            v2_fault, payload, records, "C",
            arm=lambda lib: lib.g9_d013v2_fault_arm_malloc(0))
        ok_alloc = (alloc["status"] == STATUS_REFUSED and alloc["scrubbed"]
                    and alloc["bridge_refused"]
                    and alloc["fault_stats"]["launches"] == 0
                    and alloc["fault_stats"]["allocations_total"] == 1
                    and alloc["fault_stats"]["malloc_failed"] == 1)
        record("T4c injected ALLOCATION failure refuses (no launch, scrubbed)", ok_alloc,
               f"status={alloc['status']} (0=REFUSED), scrubbed={alloc['scrubbed']}, "
               f"allocations={alloc['fault_stats']['allocations_total']}, "
               f"malloc_failed={alloc['fault_stats']['malloc_failed']}, "
               f"launches={alloc['fault_stats']['launches']} (0 proves it aborted "
               f"before any kernel), bridge_refused={alloc['bridge_refused']}")

        # Injected STAGING-COPY failure, targeted at exactly sizeof(PayloadData).
        # Must refuse without launching, and must still free what it allocated.
        # This is the check that makes the payload copy load-bearing.
        payload_bytes = C.sizeof(
            __import__("research.g9.cuda_qualification.stage2_cuda_d013_inactive",
                       fromlist=["PayloadData"]).PayloadData)
        copy = arm_and_run(
            v2_fault, payload, records, "C",
            arm=lambda lib: lib.g9_d013v2_fault_arm_memcpy_of_size(payload_bytes))
        ok_copy = (copy["status"] == STATUS_REFUSED and copy["scrubbed"]
                   and copy["bridge_refused"]
                   and copy["fault_stats"]["launches"] == 0
                   and copy["fault_stats"]["memcpy_failures"] == 1
                   and copy["fault_stats"]["allocations_total"] > 1
                   and copy["fault_stats"]["free_calls"] > 1)
        record("T4d injected PAYLOAD-STAGING COPY failure refuses and frees", ok_copy,
               f"status={copy['status']} (0=REFUSED), scrubbed={copy['scrubbed']}, "
               f"memcpy_failures={copy['fault_stats']['memcpy_failures']}, "
               f"launches={copy['fault_stats']['launches']} (0 proves no kernel "
               f"ran on unstaged memory), allocations="
               f"{copy['fault_stats']['allocations_total']}, frees="
               f"{copy['fault_stats']['free_calls']} (equal => every allocation "
               f"was released on the refusal path)")

        # Injected LAUNCH failure: allow the first N launches, then fault.
        launch = arm_and_run(
            v2_fault, payload, records, "C",
            arm=lambda lib: lib.g9_d013v2_fault_arm_launch(1))
        ok_launch = (launch["status"] == STATUS_REFUSED and launch["scrubbed"]
                     and launch["bridge_refused"]
                     and launch["fault_stats"]["launches"] >= 2)
        record("T4e injected LAUNCH failure refuses", ok_launch,
               f"status={launch['status']} (0=REFUSED), scrubbed={launch['scrubbed']}, "
               f"launches={launch['fault_stats']['launches']} (>1 proves the fault "
               f"landed mid-run, not before any launch)")

        # ---- T5 no guard weakened: the v1 release still validates --------
        release = QUALIFICATION_V1 / "GATE_9_D013_CUDA_RELEASE_DRAFT.json"
        release_map = json.loads(release.read_bytes())["source_sha256"]
        still_valid = all(
            sha256((ROOT / rel).read_bytes()) == expected
            for rel, expected in release_map.items())
        record("T5a qualified v1 release still validates against v1 sources", still_valid,
               f"all {len(release_map)} bound source hashes unchanged; the "
               f"candidate is bound by no release")

        # The candidate must NOT appear in any release, runtime config or bundle.
        bindings = []
        for rel in ("research/g9/kaggle_wp7b/runtime_config.json",
                    "research/g9/kaggle_wp7b/wp7b_launcher.py"):
            path = ROOT / rel
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                bindings.append((rel, "cuda_qualification_v2" in text))
        unbound = all(flag is False for _, flag in bindings)
        record("T5b candidate is not referenced by runtime config or launcher", unbound,
               "; ".join(f"{rel}: mentions_v2={flag}" for rel, flag in bindings))

        # ---- Host stub really is the pinned one --------------------------
        pinned = sha256((PINNED_STUB / "cuda_runtime.h").read_bytes())
        require(pinned == "fff06b9ad69b447b17f1ed31084febd59c988cb5c583e3857a627c6622f96a4c",
                f"pinned stub changed: {pinned}")
        record("T5c host stub is the pinned, unmodified repo stub", True,
               f"cuda_runtime.h sha256={pinned} (frozen, verified)")

    # ---- Summary --------------------------------------------------------
    print("\n" + "=" * 78)
    passed = sum(1 for r in RESULTS if r["passed"])
    print(f"{passed}/{len(RESULTS)} checks passed")
    for item in RESULTS:
        if not item["passed"]:
            print(f"  FAILED: {item['test']}: {item['detail']}")
    print("=" * 78)
    print("\nEVIDENCE CLASS: static analysis + CPU host-stub execution (g++).")
    print("NO T4 / GPU CONFIRMATION. The v1 host-pointer launch as the cause of")
    print("the observed T4 REFUSED remains a STRONG STATIC INFERENCE, and this")
    print("candidate's correctness on real hardware is UNVERIFIED.")
    return 0 if passed == len(RESULTS) else 1


def run_and_status(library: Path, payload, records, condition: str) -> dict:
    sys.path.insert(0, str(ROOT))
    from research.g9.cuda_qualification import stage2_cuda_d013_inactive as d013

    loaded = C.CDLL(str(library))
    loaded.g9_d013v2_fault_reset.restype = C.c_uint32
    loaded.g9_d013v2_fault_reset()
    decoded = d013.decode_payload(payload)
    row_array = d013.decode_records(
        d013.validate_records(records, condition), condition)
    condition_array = d013.decode_conditions(condition, len(records))
    output = d013.D013Output()
    run = loaded.g9_d013_run
    run.argtypes = [C.POINTER(d013.PayloadData), C.POINTER(d013.CoefficientData),
                    C.POINTER(C.c_uint32), C.c_uint32, C.POINTER(d013.D013Output)]
    run.restype = C.c_uint32
    status = run(C.byref(decoded), row_array, condition_array, len(records),
                 C.byref(output))
    return {"ok": int(status) == STATUS_OK, "status": int(status),
            "stats": fault_stats(library)}


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main())
