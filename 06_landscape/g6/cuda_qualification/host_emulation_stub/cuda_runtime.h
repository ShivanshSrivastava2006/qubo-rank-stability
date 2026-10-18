// HOST-EMULATION STUB — THIS IS NOT THE CUDA RUNTIME.
//
// It exists only so research/g6/verify_cuda_energy_crosscheck_host_emulation.py
// can compile cuda_unbalanced_energy_crosscheck.cu with an ordinary C++
// compiler and run its kernel serially on the host CPU.  That proves the C++
// transcript is bit-identical to src/g4/energy.py without a GPU or nvcc.  It
// must never be on the include path of a real nvcc build; the real runner
// compiles the pinned source in a temporary directory with no -I option, and
// __CUDACC__ (defined only by nvcc) selects the real triple-chevron launch.
//
// The stub reports a fake first device that is not a T4 so the source's
// explicit device selection is exercised, and names the emulated device
// "Tesla T4 host-emulation-stub", which the real runner's exact-name check
// rejects.
#pragma once
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <utility>

#define __host__
#define __device__
#define __global__

typedef int cudaError_t;
enum { cudaSuccess = 0, cudaErrorHostEmulationStub = 1 };
enum cudaMemcpyKind { cudaMemcpyHostToDevice, cudaMemcpyDeviceToHost };
typedef void* cudaStream_t;

struct cudaUUID_t {
  char bytes[16];
};

struct cudaDeviceProp {
  char name[256];
  cudaUUID_t uuid;
  std::size_t totalGlobalMem;
  int major;
  int minor;
  int multiProcessorCount;
  int pciBusID;
  int pciDeviceID;
  int pciDomainID;
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

static inline const char* cudaGetErrorString(cudaError_t) { return "host-emulation-stub"; }

static inline cudaError_t cudaGetDeviceCount(int* count) {
  *count = 2;
  return cudaSuccess;
}

static inline cudaError_t cudaGetDeviceProperties(cudaDeviceProp* properties, const int index) {
  std::memset(properties, 0, sizeof(*properties));
  if (index == 0) {
    std::strcpy(properties->name, "host-emulation-fake-gpu");
    properties->major = 8;
    properties->minor = 6;
  } else {
    std::strcpy(properties->name, "Tesla T4 host-emulation-stub");
    properties->major = 7;
    properties->minor = 5;
  }
  for (int b = 0; b < 16; ++b) {
    properties->uuid.bytes[b] = static_cast<char>(index * 16 + b);
  }
  properties->totalGlobalMem = 0;
  properties->multiProcessorCount = 1;
  properties->pciBusID = index;
  properties->pciDeviceID = 0;
  properties->pciDomainID = 0;
  return cudaSuccess;
}

static inline cudaError_t cudaSetDevice(int) { return cudaSuccess; }
static inline cudaError_t cudaDriverGetVersion(int* version) {
  *version = 0;
  return cudaSuccess;
}
static inline cudaError_t cudaRuntimeGetVersion(int* version) {
  *version = 0;
  return cudaSuccess;
}

template <typename T>
static inline cudaError_t cudaMalloc(T** pointer, const std::size_t bytes) {
  *pointer = static_cast<T*>(std::malloc(bytes));
  return *pointer != nullptr ? cudaSuccess : cudaErrorHostEmulationStub;
}

static inline cudaError_t cudaMemcpy(void* destination, const void* source, const std::size_t bytes,
                                     cudaMemcpyKind) {
  std::memcpy(destination, source, bytes);
  return cudaSuccess;
}

static inline cudaError_t cudaFree(void* pointer) {
  std::free(pointer);
  return cudaSuccess;
}

static inline cudaError_t cudaGetLastError() { return cudaSuccess; }
static inline cudaError_t cudaDeviceSynchronize() { return cudaSuccess; }

// Serial launch: every (block, thread) pair runs the kernel body in order.
// This is the target of the source's G6_LAUNCH_KERNEL macro when __CUDACC__
// is absent.
template <typename Kernel, typename... Args>
static inline void g6_host_emulation_launch(Kernel kernel, const dim3 grid, const dim3 block,
                                            Args... args) {
  blockDim = {block.x, 1, 1};
  for (unsigned b = 0; b < grid.x; ++b) {
    for (unsigned t = 0; t < block.x; ++t) {
      blockIdx = {b, 0, 0};
      threadIdx = {t, 0, 0};
      kernel(args...);
    }
  }
}
