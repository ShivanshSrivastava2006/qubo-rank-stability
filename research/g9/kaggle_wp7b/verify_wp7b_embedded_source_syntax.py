"""Offline syntax gate for native source emitted or held by the WP7b entrypoints."""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PKG = ROOT / "research/g9/kaggle_wp7b"
SCRATCH = Path("/home/shivansh-srivastava/decisions_os/g9_jobs/scratch/wp7bprobe")
sys.path.insert(0, str(ROOT))

from research.g9.cuda_qualification import stage2_cuda_core_qualification as pinned
from research.g9.kaggle_wp7b import build_wp7b_bundle as builder
from research.g9.kaggle_wp7b import wp7b_launcher as launcher

STUB = """#pragma once
enum cudaError_t { cudaSuccess = 0 };
struct cudaDeviceProp { char name[256]; int major; int minor; };
cudaError_t cudaGetDeviceCount(int*);
cudaError_t cudaGetDeviceProperties(cudaDeviceProp*, int);
cudaError_t cudaDriverGetVersion(int*);
cudaError_t cudaRuntimeGetVersion(int*);
"""
ENTRYPOINTS = ("wp7b_launcher.py", "wp7b_child_entry.py", "build_wp7b_bundle.py")


# Any of these markers means the literal is native C/C++/CUDA, not Python prose.
# A native string without an #include must still be caught, so the detector is
# marker-based rather than include-based.
NATIVE_MARKERS = re.compile(
    r'(^\s*#include\s*[<"][^>"\n]+[>"])|(\b__global__\b)|(\b__device__\b)'
    r'|(\bcudaError_t\b)|(\bcudaDeviceProp\b)|(\bcudaSuccess\b)|(\bint\s+main\s*\()'
    r'|(\bextern\s+"C"\b)|(\bstd::printf\b)',
    re.MULTILINE)


def native_literals(source: str, label: str):
    """Inspect parsed literals, including builder's generated Python template."""
    tree = ast.parse(source, filename=label)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if NATIVE_MARKERS.search(value):
                yield f"{label}:{node.lineno}", value


def compile_source(label: str, source: str, directory: Path) -> subprocess.CompletedProcess[str]:
    path = directory / "source.cpp"
    path.write_text(source, encoding="utf-8")
    return subprocess.run(
        ["g++", "-std=c++17", "-fsyntax-only", "-x", "c++", "-I", str(directory), str(path)],
        capture_output=True, text=True, timeout=30,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generated-script", type=Path)
    parser.add_argument("--inject-broken-escape", action="store_true")
    args = parser.parse_args(argv)
    source = launcher._platform_probe_source()
    if source != pinned.PLATFORM_PROBE:
        raise AssertionError("launcher probe differs from pinned PLATFORM_PROBE")
    if args.inject_broken_escape:
        source = source.replace('\\"', '\\\\"', 1)
    if not source.startswith("#include <cuda_runtime.h>"):
        raise AssertionError("launcher probe source missing")

    # A minimal valid seal blob suffices to render and inspect the generated template.
    generated = builder.script_source(
        [("research/g9/kaggle_wp7b/seal.json", builder.sha(b"{}"), b"{}")],
        "0" * 64, None, {}, True,
    )
    inspected = [(name, (PKG / name).read_text(encoding="utf-8")) for name in ENTRYPOINTS]
    inspected.append(("generated template", generated))
    if args.generated_script:
        inspected.append((str(args.generated_script), args.generated_script.read_text(encoding="utf-8")))
    native = [(label, value) for name, text in inspected for label, value in native_literals(text, name)]
    # The entire package is searched as well, including fixtures and the seal builder.
    package_native = [(label, value) for path in sorted(PKG.rglob("*.py"))
                      for label, value in native_literals(path.read_text(encoding="utf-8"), str(path.relative_to(ROOT)))]
    all_sources = [("pinned PLATFORM_PROBE via launcher", source), *native, *package_native]
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="wp7b-native-syntax-", dir=SCRATCH) as td:
        directory = Path(td)
        (directory / "cuda_runtime.h").write_text(STUB, encoding="ascii")
        for label, value in all_sources:
            compiled = compile_source(label, value, directory)
            if compiled.returncode:
                raise AssertionError(f"native source syntax failed at {label}: {compiled.stderr[-2000:]}")
        broken = pinned.PLATFORM_PROBE.replace('\\"', '\\\\"', 1)
        if broken == pinned.PLATFORM_PROBE or compile_source("broken escape control", broken, directory).returncode == 0:
            raise AssertionError("broken escape control unexpectedly compiled")
    print(f"EMBEDDED SOURCE: PASS; compiled={len(all_sources)}; entrypoint_literals={len(native)}; package_literals={len(package_native)}; broken_escape=rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
