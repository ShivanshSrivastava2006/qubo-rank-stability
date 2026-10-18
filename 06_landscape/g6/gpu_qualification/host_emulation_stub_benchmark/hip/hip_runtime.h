// HOST-EMULATION STUB EXTENSION FOR THE BENCHMARK HARNESS — NOT THE HIP RUNTIME.
//
// It layers HIP event timing shims (steady-clock based) over the existing
// cross-check stub so research/g6/verify_gpu_energy_benchmark_host_emulation.py
// can compile gpu_unbalanced_energy_benchmark.hip.cpp with an ordinary C++
// compiler and run its repeated launches serially on the host CPU.  It exists
// only to prove the harness mechanics and the Python-side gate; timings it
// produces are host-CPU durations with no meaning for the GPU.  It must never
// be on the include path of a real hipcc build.
#pragma once
#include "../../host_emulation_stub/hip/hip_runtime.h"

#include <chrono>

struct HostEmulationEvent {
  std::chrono::steady_clock::time_point recorded_at;
};
typedef HostEmulationEvent* hipEvent_t;
typedef void* hipStream_t;

static inline hipError_t hipEventCreate(hipEvent_t* event) {
  *event = new HostEmulationEvent{std::chrono::steady_clock::now()};
  return hipSuccess;
}

static inline hipError_t hipEventRecord(hipEvent_t event, hipStream_t) {
  event->recorded_at = std::chrono::steady_clock::now();
  return hipSuccess;
}

static inline hipError_t hipEventSynchronize(hipEvent_t) { return hipSuccess; }

static inline hipError_t hipEventElapsedTime(float* milliseconds, hipEvent_t start, hipEvent_t stop) {
  *milliseconds = std::chrono::duration<float, std::milli>(stop->recorded_at - start->recorded_at).count();
  return hipSuccess;
}

static inline hipError_t hipEventDestroy(hipEvent_t event) {
  delete event;
  return hipSuccess;
}
