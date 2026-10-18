// FAULT-INJECTION CUDA RUNTIME STUB -- CANDIDATE v2 DIAGNOSTIC ONLY.
//
// This header is a NEW, versioned diagnostic artifact. It is NOT the CUDA
// runtime, NOT the pinned repo host stub, and NOT on any qualified build's
// include path. It exists so the candidate's device-staging can be exercised
// on CPU with a forced allocation, copy or launch failure.
//
// It reuses the PINNED repo stub
// (research/g6/cuda_qualification/host_emulation_stub/cuda_runtime.h,
// sha256 fff06b9ad69b447b17f1ed31084febd59c988cb5c583e3857a627c6622f96a4c)
// by renaming the handful of functions it needs to intercept, so every OTHER
// behaviour of the pinned stub -- dim3, blockIdx/threadIdx bookkeeping, the
// serial launch loop, cudaFree -- is literally the pinned code and cannot
// drift from it.
//
// WHAT IT DOES NOT DO: it does not make anything pass. It only makes the
// pinned stub return a failure code where a real CUDA runtime would. Every
// such failure must propagate to the candidate's existing fail-closed
// `ok == false` path, which is exactly what the fixture asserts.
//
// EVIDENCE STATUS: CPU ONLY. No nvcc, no GPU, no /dev/nvidia* here. Nothing
// in this file is evidence about real CUDA hardware behaviour.

#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

// ---------------------------------------------------------------------------
// Phase 1: pull in the pinned stub with the four interceptable entry points
// renamed, so we can wrap rather than reimplement them.
// ---------------------------------------------------------------------------
#define cudaMalloc cudaMalloc_pinned
#define cudaMemcpy cudaMemcpy_pinned
#define cudaFree cudaFree_pinned
#define cudaGetLastError cudaGetLastError_pinned
#define cudaDeviceSynchronize cudaDeviceSynchronize_pinned
#define g6_host_emulation_launch g6_host_emulation_launch_pinned

// Included by EXPLICIT RELATIVE PATH, never as <cuda_runtime.h>: this header
// itself IS named cuda_runtime.h and must be on -I for the D013 source's own
// `#include <cuda_runtime.h>`, so a bare include here would recurse into
// itself. The path below is the pinned stub, relative to this directory.
#include "../../../g6/cuda_qualification/host_emulation_stub/cuda_runtime.h"

#undef cudaMalloc
#undef cudaMemcpy
#undef cudaFree
#undef cudaGetLastError
#undef cudaDeviceSynchronize
#undef g6_host_emulation_launch

// ---------------------------------------------------------------------------
// Phase 2: the fault-injection control surface, visible to ctypes.
// ---------------------------------------------------------------------------
extern "C" {

// Number of device allocations that must SUCCEED before cudaMalloc starts
// failing. -1 disables allocation injection entirely.
void g9_d013v2_fault_arm_malloc(long long succeed_before);

// Fail the first cudaMemcpy whose element count equals exactly this many
// bytes. Used to target the candidate's payload HostToDevice staging
// specifically, without touching any other copy. -1 disables.
void g9_d013v2_fault_arm_memcpy_of_size(unsigned long long bytes);

// Number of kernel launches that must succeed before the launch is reported
// as failed. -1 disables launch injection entirely.
void g9_d013v2_fault_arm_launch(long long succeed_before);

// Write 8 counters: malloc_ok, malloc_failed, memcpy_calls, launches,
// launch_failures_armed, free_calls, memcpy_failures, allocations_total.
std::uint32_t g9_d013v2_fault_stats(std::uint64_t* values, std::uint32_t capacity);

// Arm nothing. Called by the fixture before every clean measurement.
void g9_d013v2_fault_reset();

}  // extern "C"

namespace g9_d013v2_fault {

struct State {
  long long malloc_succeed_before = -1;
  long long launch_succeed_before = -1;
  unsigned long long memcpy_target_bytes = ~0ULL;
  std::uint64_t malloc_ok = 0;
  std::uint64_t malloc_failed = 0;
  std::uint64_t memcpy_calls = 0;
  std::uint64_t memcpy_failures = 0;
  std::uint64_t launches = 0;
  std::uint64_t launch_failures = 0;
  std::uint64_t free_calls = 0;
};

inline State& state() {
  static State value;
  return value;
}

}  // namespace g9_d013v2_fault

// ---------------------------------------------------------------------------
// Phase 3: the wrappers.
// ---------------------------------------------------------------------------

extern "C" void g9_d013v2_fault_arm_malloc(long long succeed_before) {
  g9_d013v2_fault::state().malloc_succeed_before = succeed_before;
}

extern "C" void g9_d013v2_fault_arm_memcpy_of_size(unsigned long long bytes) {
  g9_d013v2_fault::state().memcpy_target_bytes = bytes;
}

extern "C" void g9_d013v2_fault_arm_launch(long long succeed_before) {
  g9_d013v2_fault::state().launch_succeed_before = succeed_before;
}

extern "C" std::uint32_t g9_d013v2_fault_stats(std::uint64_t* values, std::uint32_t capacity) {
  const auto& s = g9_d013v2_fault::state();
  if (values == nullptr || capacity < 8u) return 0u;
  values[0] = s.malloc_ok;
  values[1] = s.malloc_failed;
  values[2] = s.memcpy_calls;
  values[3] = s.launches;
  values[4] = s.launch_failures;
  values[5] = s.free_calls;
  values[6] = s.memcpy_failures;
  values[7] = s.malloc_ok + s.malloc_failed;
  return 8u;
}

extern "C" void g9_d013v2_fault_reset() {
  // Disarms every injection AND zeroes the counters, so a statistic read
  // afterwards describes only the run that followed. Without the zeroing the
  // counters are process-lifetime totals and cannot show that a fault landed
  // BEFORE any launch.
  auto& s = g9_d013v2_fault::state();
  s = g9_d013v2_fault::State();
}

template <typename T>
static inline cudaError_t cudaMalloc(T** pointer, const std::size_t bytes) {
  auto& s = g9_d013v2_fault::state();
  const bool armed = s.malloc_succeed_before >= 0;
  if (armed && static_cast<long long>(s.malloc_ok) >= s.malloc_succeed_before) {
    s.malloc_failed += 1ULL;
    *pointer = nullptr;
    return static_cast<cudaError_t>(cudaErrorHostEmulationStub);
  }
  const cudaError_t result = cudaMalloc_pinned(pointer, bytes);
  if (result == cudaSuccess) {
    s.malloc_ok += 1ULL;
  } else {
    s.malloc_failed += 1ULL;
  }
  return result;
}

static inline cudaError_t cudaMemcpy(void* destination, const void* source, const std::size_t bytes,
                                     cudaMemcpyKind kind) {
  auto& s = g9_d013v2_fault::state();
  s.memcpy_calls += 1ULL;
  if (static_cast<unsigned long long>(bytes) == s.memcpy_target_bytes) {
    s.memcpy_failures += 1ULL;
    return static_cast<cudaError_t>(cudaErrorHostEmulationStub);
  }
  return cudaMemcpy_pinned(destination, source, bytes, kind);
}

static inline cudaError_t cudaGetLastError() {
  auto& s = g9_d013v2_fault::state();
  if (s.launch_succeed_before >= 0 &&
      static_cast<long long>(s.launch_failures + s.launches) > s.launch_succeed_before) {
    return static_cast<cudaError_t>(cudaErrorHostEmulationStub);
  }
  return cudaGetLastError_pinned();
}

static inline cudaError_t cudaDeviceSynchronize() { return cudaDeviceSynchronize_pinned(); }

// Counts each serial launch so the injected launch failure is positioned
// exactly, then delegates to the pinned serial launch loop unchanged.
template <typename Kernel, typename... Args>
static inline void g6_host_emulation_launch(Kernel kernel, const dim3 grid, const dim3 block,
                                            Args... args) {
  g9_d013v2_fault::state().launches += 1ULL;
  g6_host_emulation_launch_pinned(kernel, grid, block, args...);
}

// cudaFree is counted but never altered: the pinned stub's free is already the
// real behaviour, and a fault here would only test the stub.
static inline cudaError_t cudaFree(void* pointer) {
  g9_d013v2_fault::state().free_calls += 1ULL;
  return cudaFree_pinned(pointer);
}
