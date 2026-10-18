// HOST-EMULATION STUB — THIS IS NOT THE HIP RUNTIME.
//
// It exists only so research/g6/verify_gpu_energy_crosscheck_host_emulation.py
// can compile gpu_unbalanced_energy_crosscheck.hip.cpp with an ordinary C++
// compiler and run its kernel serially on the host CPU.  That proves the C++
// transcript is bit-identical to src/g4/energy.py without a GPU or hipcc.  It
// must never be on the include path of a real hipcc build; the real runner
// compiles the pinned source in a temporary directory with no -I option.
//
// The stub reports a fake first device that is not gfx1201 so the source's
// explicit device selection is exercised, and names the emulated device
// "gfx1201-host-emulation-stub", which the real runner's architecture check
// rejects.
#pragma once
#include <cstdint>
#include <cstdlib>
#include <cstring>

#define __host__
#define __device__
#define __global__

typedef int hipError_t;
enum { hipSuccess = 0, hipErrorHostEmulationStub = 1 };
enum hipMemcpyKind { hipMemcpyHostToDevice, hipMemcpyDeviceToHost };

struct hipDeviceProp_t {
  char name[256];
  char gcnArchName[256];
};

struct dim3 {
  unsigned x, y, z;
  dim3(unsigned x_ = 1, unsigned y_ = 1, unsigned z_ = 1) : x(x_), y(y_), z(z_) {}
};

struct HostEmulationIndex {
  unsigned x, y, z;
};
static HostEmulationIndex blockIdx{0, 0, 0};
static HostEmulationIndex blockDim{1, 1, 1};
static HostEmulationIndex threadIdx{0, 0, 0};

static inline long long __double_as_longlong(const double value) {
  long long output = 0;
  std::memcpy(&output, &value, sizeof(output));
  return output;
}

static inline const char* hipGetErrorString(hipError_t) { return "host-emulation-stub"; }

static inline hipError_t hipGetDeviceCount(int* count) {
  *count = 2;
  return hipSuccess;
}

static inline hipError_t hipGetDeviceProperties(hipDeviceProp_t* properties, const int index) {
  std::memset(properties, 0, sizeof(*properties));
  if (index == 0) {
    std::strcpy(properties->name, "host-emulation-fake-apu");
    std::strcpy(properties->gcnArchName, "gfx1150-host-emulation-stub");
  } else {
    std::strcpy(properties->name, "host-emulation-stub");
    std::strcpy(properties->gcnArchName, "gfx1201-host-emulation-stub");
  }
  return hipSuccess;
}

static inline hipError_t hipSetDevice(int) { return hipSuccess; }

template <typename T>
static inline hipError_t hipMalloc(T** pointer, const std::size_t bytes) {
  *pointer = static_cast<T*>(std::malloc(bytes));
  return *pointer != nullptr ? hipSuccess : hipErrorHostEmulationStub;
}

static inline hipError_t hipMemcpy(void* destination, const void* source, const std::size_t bytes,
                                   hipMemcpyKind) {
  std::memcpy(destination, source, bytes);
  return hipSuccess;
}

static inline hipError_t hipFree(void* pointer) {
  std::free(pointer);
  return hipSuccess;
}

static inline hipError_t hipGetLastError() { return hipSuccess; }
static inline hipError_t hipDeviceSynchronize() { return hipSuccess; }

// Serial launch: every (block, thread) pair runs the kernel body in order.
template <typename Kernel, typename... Args>
static inline void hipLaunchKernelGGL(Kernel kernel, const dim3 grid, const dim3 block,
                                      std::size_t, int, Args... args) {
  blockDim = {block.x, 1, 1};
  for (unsigned b = 0; b < grid.x; ++b) {
    for (unsigned t = 0; t < block.x; ++t) {
      blockIdx = {b, 0, 0};
      threadIdx = {t, 0, 0};
      kernel(args...);
    }
  }
}
