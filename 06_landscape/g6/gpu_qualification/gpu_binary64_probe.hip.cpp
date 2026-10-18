// Non-production binary64 HIP probe for the experimental Gate-6 GPU track.
//
// This is deliberately not a Gate-6 energy evaluator. It exercises the
// ordered add/subtract/multiply/divide sequences that a future evaluator would
// require, comparing device bit patterns against an explicitly uncontracted
// host transcript. A PASS demonstrates only this narrow compiler/device
// property; it does not authorize a GPU implementation of Gate 6.

#include <hip/hip_runtime.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

#pragma clang fp contract(off)

struct Input {
  double a;
  double b;
  double c;
  double d;
};

__host__ __device__ static double ordered_transcript(const Input input) {
  // Keep every operation in a separate statement. The compile command also
  // passes -ffp-contract=off; neither fast-math nor FMA is permitted.
  const double product_one = input.a * input.b;
  const double sum_one = product_one + input.c;
  const double product_two = sum_one * input.d;
  const double difference_one = product_two - input.a;
  const double square = difference_one * difference_one;
  const double sum_two = square + input.b;
  const double quotient = sum_two / input.d;
  const double difference_two = quotient - input.c;
  return difference_two;
}

__device__ static std::uint64_t bits_device(const double value) {
  return static_cast<std::uint64_t>(__double_as_longlong(value));
}

__global__ void transcript_kernel(const Input* inputs, std::uint64_t* output,
                                  const std::uint32_t count) {
  const std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index < count) {
    output[index] = bits_device(ordered_transcript(inputs[index]));
  }
}

static std::uint64_t bits_host(const double value) {
  std::uint64_t output = 0;
  std::memcpy(&output, &value, sizeof(output));
  return output;
}

static bool check(const hipError_t status, const char* call) {
  if (status == hipSuccess) {
    return true;
  }
  std::fprintf(stderr, "HIP failure at %s: %s\n", call,
               hipGetErrorString(status));
  return false;
}

int main() {
  // Exact hexadecimal literals avoid input decimal-conversion ambiguity.
  constexpr Input inputs[] = {
      {0x1.2b93cd4cbc969p-7, 0x1.999999999999ap-4,
       0x1.df52e21460f0fp-11, 0x1.32c467bb1f528p-15},
      {-0x1.6f484ef393955p-7, 0x1.4000000000000p+2,
       0x1.0000000000000p+1, 0x1.0000000000000p-2},
      {0x1.fffffffffffffp+100, 0x1.0000000000001p-50,
       -0x1.0000000000001p-20, 0x1.0000000000001p+2},
      {-0x1.0000000000001p-800, 0x1.fffffffffffffp+700,
       0x1.0000000000001p-700, 0x1.0000000000001p-3},
      {0x1.0000000000001p+0, -0x1.0000000000001p+0,
       0x1.0000000000001p-52, -0x1.0000000000001p+1},
      {0x1.8p+10, 0x1.4p+5, -0x1.2p-10, 0x1.2p+3},
      {0x1.0p-1022, 0x1.0000000000001p+0,
       0x1.0p-1022, 0x1.0000000000001p+0},
      {0x1.fffffffffffffp-1, 0x1.0000000000001p+0,
       -0x1.0000000000001p-1, 0x1.0000000000001p+0},
  };
  constexpr std::uint32_t count = sizeof(inputs) / sizeof(inputs[0]);

  int device_count = 0;
  if (!check(hipGetDeviceCount(&device_count), "hipGetDeviceCount") ||
      device_count < 1) {
    return 2;
  }
  int selected_device = -1;
  hipDeviceProp_t properties{};
  for (int candidate = 0; candidate < device_count; ++candidate) {
    hipDeviceProp_t candidate_properties{};
    if (!check(hipGetDeviceProperties(&candidate_properties, candidate),
               "hipGetDeviceProperties")) {
      return 2;
    }
    // An APU can precede the discrete RX 9070 in HIP's device order. Select
    // the target architecture explicitly rather than assuming device zero.
    if (std::strncmp(candidate_properties.gcnArchName, "gfx1201", 7) == 0) {
      selected_device = candidate;
      properties = candidate_properties;
      break;
    }
  }
  if (selected_device < 0 ||
      !check(hipSetDevice(selected_device), "hipSetDevice(gfx1201)")) {
    return 2;
  }

  Input* device_inputs = nullptr;
  std::uint64_t* device_outputs = nullptr;
  std::uint64_t host_outputs[count]{};
  bool ok =
      check(hipMalloc(&device_inputs, sizeof(inputs)), "hipMalloc(inputs)") &&
      check(hipMalloc(&device_outputs, sizeof(host_outputs)), "hipMalloc(outputs)") &&
      check(hipMemcpy(device_inputs, inputs, sizeof(inputs), hipMemcpyHostToDevice),
            "hipMemcpy(inputs)");
  if (ok) {
    constexpr std::uint32_t block_size = 64;
    transcript_kernel<<<1, block_size>>>(device_inputs, device_outputs, count);
    ok = check(hipGetLastError(), "kernel launch") &&
         check(hipDeviceSynchronize(), "hipDeviceSynchronize") &&
         check(hipMemcpy(host_outputs, device_outputs, sizeof(host_outputs),
                         hipMemcpyDeviceToHost),
               "hipMemcpy(outputs)");
  }

  std::uint32_t mismatches = 0;
  for (std::uint32_t index = 0; ok && index < count; ++index) {
    if (bits_host(ordered_transcript(inputs[index])) != host_outputs[index]) {
      ++mismatches;
    }
  }
  if (device_inputs != nullptr) hipFree(device_inputs);
  if (device_outputs != nullptr) hipFree(device_outputs);
  if (!ok) return 2;

  std::printf(
      "{\"architecture\":\"%s\",\"device_index\":%d,\"device_name\":\"%s\","
      "\"mismatches\":%u,\"probe\":\"ordered_binary64_transcript\","
      "\"samples\":%u,\"scientific_outputs\":\"intentionally absent\","
      "\"verdict\":\"%s\"}\n",
      properties.gcnArchName, selected_device, properties.name, mismatches, count,
      mismatches == 0 ? "pass" : "fail");
  return mismatches == 0 ? 0 : 1;
}
