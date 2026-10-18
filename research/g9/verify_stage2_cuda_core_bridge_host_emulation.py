#!/usr/bin/env python3
"""Host-stub ABI comparison; no nvcc, device, Kaggle, or real instance."""

from __future__ import annotations

import ctypes as C
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
    raise SystemExit("PYTHONDONTWRITEBYTECODE=1 is required")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.g9.cuda_qualification import stage2_cuda_core_bridge as bridge
from research.g9.cuda_qualification import stage2_cuda_core_stream_engine as core
from research.g9.cuda_qualification import stage2_cuda_input_frame as frame_api
from research.g9.cuda_qualification import stage2_cuda_reconstruct as recon


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def refused(call, message: str) -> None:
    try:
        call()
    except bridge.CoreBridgeError:
        return
    raise RuntimeError(message)


def compare_core(actual: dict[str, object], expected: dict[str, object]) -> None:
    require(actual.keys() == expected.keys() and
            actual["lift_total"] == expected["lift_total"] and
            actual["record_count"] == expected["record_count"] and
            actual["summaries"].keys() == expected["summaries"].keys(),
            "core result outer shape differs")
    for key, observed in actual["summaries"].items():
        wanted = expected["summaries"][key]
        require(observed.keys() == wanted.keys(), f"summary keys differ at {key}")
        for field in observed:
            if field == "minimum":
                require(struct.pack("<d", observed[field]) == struct.pack("<d", wanted[field]),
                        f"minimum word differs at {key}")
            else:
                require(observed[field] == wanted[field], f"{field} differs at {key}")


def main() -> None:
    payload = core.synthetic_payload()
    record = core.coefficient_row("row0")
    domain = core.build_domain(payload)
    offsets_sha = recon.SlackIndexMap(domain["offsets"], domain["lift_total"]).offsets_sha256
    frame = frame_api.build_input_frame(payload, [record], offsets_sha)
    alternate = core.synthetic_payload()
    alternate["sectors"] = core.ALTERNATE_MEMBERSHIP
    alternate["lambda_ref"] = core.ALTERNATE_LAMBDA_REF
    alternate["b"] = 45.0
    alternate_rows = [core.coefficient_row("row1"), core.coefficient_row("row0")]
    alternate_domain = core.build_domain(alternate)
    alternate_sha = recon.SlackIndexMap(alternate_domain["offsets"],
                                       alternate_domain["lift_total"]).offsets_sha256
    require(alternate_sha != offsets_sha and alternate_domain["lift_total"] != domain["lift_total"],
            "the alternate payload did not change the offset table")
    alternate_frame = frame_api.build_input_frame(alternate, alternate_rows, alternate_sha)
    stub = ROOT / "research/g6/cuda_qualification/host_emulation_stub"
    wrapper = ROOT / "research/g9/cuda_qualification/stage2_cuda_core_bridge.cu"
    with tempfile.TemporaryDirectory(prefix="g9-core-bridge-host-") as temporary:
        library = Path(temporary) / "libg9_core_host_stub.so"
        command = ["g++", "-x", "c++", "-std=c++17", "-O0", "-shared", "-fPIC",
                   "-Wall", "-Wextra", "-Wno-unknown-pragmas", "-ffp-contract=off",
                   "-fno-fast-math", "-I", str(stub), str(wrapper), "-o", str(library)]
        built = subprocess.run(command, cwd=ROOT, text=True, capture_output=True,
                               check=False, timeout=180)
        require(built.returncode == 0 and not built.stderr,
                "host-stub ABI build failed or warned: " + built.stderr)
        bound = bridge.run_host_emulated_frame(frame, library)
        require(bound["schema"] == bridge.SCHEMA and
                bound["input_frame_sha256"] == frame["content_sha256"] and
                bound["offsets_sha256"] == offsets_sha,
                "same-call input/offset binding drift")
        expected = core.run_core(*frame_api.decoded_inputs(frame))
        compare_core(bound["core_result"], expected)

        second = bridge.run_host_emulated_frame(alternate_frame, library)
        require(second["input_frame_sha256"] == alternate_frame["content_sha256"] and
                second["input_frame_sha256"] != bound["input_frame_sha256"] and
                second["offsets_sha256"] == alternate_sha and
                second["core_result"]["record_count"] == 2,
                "different two-row payload was not bound independently")
        compare_core(second["core_result"], core.run_core(*frame_api.decoded_inputs(alternate_frame)))

        wrong_offset = frame_api.build_input_frame(payload, [record],
                                                    hashlib.sha256(b"wrong offset table").hexdigest())
        refused(lambda: bridge.run_host_emulated_frame(wrong_offset, library),
                "different valid offset identity was accepted")
        bad_frame = dict(frame)
        bad_frame["content_sha256"] = "0" * 64
        refused(lambda: bridge.run_host_emulated_frame(bad_frame, library),
                "wrong frame content hash was accepted")

        # Direct C ABI refusals: invalid row count cannot reach an out-of-range
        # coefficient read, and failed calls invalidate the offset-copy channel.
        loaded = C.CDLL(str(library))
        run = loaded.g9_core_run_v1
        run.argtypes = [C.POINTER(bridge.PayloadData), C.POINTER(bridge.CoefficientData),
                        C.c_uint32, C.POINTER(bridge.CoreOutput)]
        run.restype = C.c_uint32
        copy_offsets = loaded.g9_core_copy_offsets_v1
        copy_offsets.argtypes = [C.POINTER(C.c_uint64), C.c_uint64]
        copy_offsets.restype = C.c_uint32
        abi_payload, abi_rows = bridge._decode_frame(frame)
        output = bridge.CoreOutput()
        offsets = (C.c_uint64 * (core.STATE_COUNT + 1))()
        for row_count in (0, 3):
            require(run(C.byref(abi_payload), abi_rows, row_count, C.byref(output)) == 0,
                    "invalid row count accepted by ABI")
            require(copy_offsets(offsets, len(offsets)) == 0,
                    "failed ABI call exposed stale offset table")
        invalid = bridge._decode_frame(frame)[0]
        invalid.c_value = 2.5
        require(run(C.byref(invalid), abi_rows, 1, C.byref(output)) == 0,
                "fractional C accepted by ABI")
        require(copy_offsets(offsets, len(offsets)) == 0,
                "invalid payload exposed stale offset table")
        invalid.c_value = 1e200
        require(run(C.byref(invalid), abi_rows, 1, C.byref(output)) == 0,
                "out-of-range finite C reached a C++ integer cast")
        require(copy_offsets(offsets, len(offsets)) == 0,
                "out-of-range C exposed stale offset table")
    print("PASS Stage-2 host-stub core ABI, exact Python comparison, and offset binding")


if __name__ == "__main__":
    main()
