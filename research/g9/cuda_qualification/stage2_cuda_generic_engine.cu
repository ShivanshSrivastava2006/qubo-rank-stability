// Generic Stage-2 CUDA numerical qualification engine — synthetic self-test only.
//
// This source deliberately has no Stage-2 instance reader, ledger reader, output
// writer, or production mode.  It exercises the numerical core that a later
// reviewed producer will use: fixed binary64 accumulation for both encodings,
// deterministic first-seen minimum selection, D015 nested tie flags, and
// explicit non-finite detection.  Its only supported command, --self-test,
// generates a fixed artificial 257-state term table and prints checksums, never
// an instance-dependent quantity.
//
// Numerical contract: binary64 only; no fp32, FMA, reassociation, atomics,
// shared-memory reduction, fast math, or FTZ.  nvcc must be invoked with
// --fmad=false --ftz=false --prec-div=true --prec-sqrt=true and host
// -ffp-contract=off.  The Python harness independently reproduces every
// synthetic word/checksum.  Real CUDA selection is reported, then bound by the
// qualification identity; no device UUID or session ID is retained.

#include <cuda_runtime.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#pragma STDC FP_CONTRACT OFF

#if defined(__CUDACC__)
#define G9_LAUNCH(kernel, grid, block, ...) kernel<<<grid, block>>>(__VA_ARGS__)
#else
#define G9_LAUNCH(kernel, grid, block, ...) g6_host_emulation_launch(kernel, grid, block, __VA_ARGS__)
#endif

constexpr std::uint32_t kStates = 257;
constexpr std::uint32_t kPoints = 4;
constexpr std::uint32_t kEncodings = 2;
constexpr std::uint32_t kCHCount = 3;
constexpr std::uint32_t kBlockSize = 64;
constexpr double kEpsilon = 0x1p-52;
constexpr double kLambdaRef = 0x1p-5;
constexpr std::uint64_t kFNVOffset = 1469598103934665603ULL;
constexpr std::uint64_t kFNVPrime = 1099511628211ULL;

struct Terms {
  double f_value;
  double card_square;
  double h_sector[4];
  double sector_square[4];
  double h_budget;
  double budget_square;
  double sector_slack_square[4];
  double budget_slack_square;
};

struct Coefficients {
  double alpha;
  double sector_slack;
  double budget_slack;
  double sector_linear;
  double sector_quadratic;
  double budget_linear;
  double budget_quadratic;
};

__host__ __device__ static std::uint64_t double_to_word(const double value) {
  std::uint64_t word = 0;
#if defined(__CUDA_ARCH__)
  word = static_cast<std::uint64_t>(__double_as_longlong(value));
#else
  std::memcpy(&word, &value, sizeof(word));
#endif
  return word;
}

__host__ __device__ static double word_to_double(const std::uint64_t word) {
  double value = 0.0;
#if defined(__CUDA_ARCH__)
  value = __longlong_as_double(static_cast<long long>(word));
#else
  std::memcpy(&value, &word, sizeof(value));
#endif
  return value;
}

__host__ __device__ static bool word_is_nonfinite(const std::uint64_t word) {
  return ((word >> 52) & 0x7ffULL) == 0x7ffULL;
}

__host__ __device__ static double unbalanced_energy(const Terms* term, const Coefficients* coeff) {
  const double card_penalty = coeff->alpha * term->card_square;
  double h = term->f_value;
  h = h + card_penalty;
  for (std::uint32_t sector = 0; sector < 4; ++sector) {
    const double linear_product = coeff->sector_linear * term->h_sector[sector];
    const double quadratic_product = coeff->sector_quadratic * term->sector_square[sector];
    const double penalty = (-linear_product) + quadratic_product;
    h = h + penalty;
  }
  const double budget_linear = coeff->budget_linear * term->h_budget;
  const double budget_quadratic = coeff->budget_quadratic * term->budget_square;
  h = h + ((-budget_linear) + budget_quadratic);
  return h;
}

__host__ __device__ static double slack_energy(const Terms* term, const Coefficients* coeff) {
  const double card_penalty = coeff->alpha * term->card_square;
  double h = term->f_value;
  h = h + card_penalty;
  for (std::uint32_t sector = 0; sector < 4; ++sector) {
    const double penalty = coeff->sector_slack * term->sector_slack_square[sector];
    h = h + penalty;
  }
  const double budget_penalty = coeff->budget_slack * term->budget_slack_square;
  h = h + budget_penalty;
  return h;
}

__host__ __device__ static double ch_value(const std::uint32_t index) {
  return index == 0 ? 1024.0 : (index == 1 ? 2048.0 : 4096.0);
}

// FROZEN_MATH_SPEC §5.3 / src.g4.energy.tau, written in the same binary64
// operation order: gap = abs(fl(y-y')); scale = fl(lambda_ref +
// max(abs(y),abs(y_prime))); tau = fl((c*epsilon)*scale).
__host__ __device__ static bool frozen_tie(const double y, const double y_prime, const double c_h) {
  const double difference = y - y_prime;
  const double gap = difference < 0.0 ? -difference : difference;
  const double y_magnitude = y < 0.0 ? -y : y;
  const double prime_magnitude = y_prime < 0.0 ? -y_prime : y_prime;
  const double maximum = y_magnitude > prime_magnitude ? y_magnitude : prime_magnitude;
  const double scale = kLambdaRef + maximum;
  const double tolerance = (c_h * kEpsilon) * scale;
  return gap <= tolerance;
}

// The artificial table includes exact duplicate minima plus one state each
// that joins at c_H=1024, 2048, and 4096.  These cases make strict first-seen
// selection and each D015 threshold bit load-bearing.  They are not data from
// a Stage-2 instance and never appear in a production path.
__host__ __device__ static double synthetic_control_energy(
    const double raw, const std::uint32_t state, const std::uint32_t point, const std::uint32_t encoding) {
  const std::uint32_t pair = point * kEncodings + encoding;
  const std::uint32_t anchor = 17u + point * 31u + encoding * 7u;
  const double base = -256.0 - static_cast<double>(pair) * 16.0;
  if (state == anchor || state == anchor + 1u) return base;
  if (state == anchor + 2u) return base + 0x1p-35;
  if (state == anchor + 3u) return base + 0x1.8p-34;
  if (state == anchor + 4u) return base + 0x1.8p-33;
  return raw;
}

__global__ void energy_kernel(const Terms* terms, const Coefficients* coefficients, std::uint64_t* words,
                               std::uint8_t* nonfinite) {
  const std::uint32_t state = blockIdx.x * blockDim.x + threadIdx.x;
  if (state >= kStates) return;
  for (std::uint32_t point = 0; point < kPoints; ++point) {
    const Terms* term = &terms[state];
    const Coefficients* coeff = &coefficients[point];
    for (std::uint32_t encoding = 0; encoding < kEncodings; ++encoding) {
      const double raw = encoding == 0 ? unbalanced_energy(term, coeff) : slack_energy(term, coeff);
      const double energy = synthetic_control_energy(raw, state, point, encoding);
      const std::uint32_t offset = (point * kEncodings + encoding) * kStates + state;
      words[offset] = double_to_word(energy);
      nonfinite[offset] = word_is_nonfinite(words[offset]) ? 1u : 0u;
    }
  }
}

// One deterministic serial device thread per point/encoding: strict < gives
// first-seen canonical state selection without atomics or scheduling effects.
__global__ void minimum_kernel(const std::uint64_t* words, std::uint64_t* minimum_words, std::uint32_t* minimum_indices) {
  const std::uint32_t pair = blockIdx.x * blockDim.x + threadIdx.x;
  if (pair >= kPoints * kEncodings) return;
  const std::uint32_t offset = pair * kStates;
  double best = word_to_double(words[offset]);
  std::uint32_t best_index = 0;
  for (std::uint32_t state = 1; state < kStates; ++state) {
    const double candidate = word_to_double(words[offset + state]);
    if (candidate < best) {
      best = candidate;
      best_index = state;
    }
  }
  minimum_words[pair] = double_to_word(best);
  minimum_indices[pair] = best_index;
}

__global__ void tie_flags_kernel(const std::uint64_t* words, const std::uint64_t* minimum_words, std::uint8_t* flags) {
  const std::uint32_t state = blockIdx.x * blockDim.x + threadIdx.x;
  if (state >= kStates) return;
  for (std::uint32_t pair = 0; pair < kPoints * kEncodings; ++pair) {
    const double energy = word_to_double(words[pair * kStates + state]);
    const double minimum = word_to_double(minimum_words[pair]);
    std::uint8_t value = 0;
    for (std::uint32_t c_h = 0; c_h < kCHCount; ++c_h) {
      if (frozen_tie(energy, minimum, ch_value(c_h))) value = static_cast<std::uint8_t>(value | (1u << c_h));
    }
    flags[pair * kStates + state] = value;
  }
}

static std::uint64_t fnv_word(std::uint64_t state, const std::uint64_t word) {
  return (state ^ word) * kFNVPrime;
}

static Terms synthetic_terms(const std::uint32_t state) {
  Terms out{};
  const int signed_state = static_cast<int>((state * 37u) % 257u) - 128;
  out.f_value = static_cast<double>(signed_state) / 251.0;
  const double card = static_cast<double>(state % 9u) - 4.0;
  out.card_square = card * card;
  for (std::uint32_t sector = 0; sector < 4; ++sector) {
    const double residual = static_cast<double>((state * (sector + 3u) + 5u) % 17u) / 13.0 - 1.0;
    out.h_sector[sector] = residual;
    out.sector_square[sector] = residual * residual;
    const double slack_delta = residual - static_cast<double>((state + sector) % 3u);
    out.sector_slack_square[sector] = slack_delta * slack_delta;
  }
  out.h_budget = static_cast<double>((state * 11u + 7u) % 31u) / 7.0 - 3.0;
  out.budget_square = out.h_budget * out.h_budget;
  const double budget_delta = out.h_budget - static_cast<double>(state % 7u);
  out.budget_slack_square = budget_delta * budget_delta;
  return out;
}

static Coefficients synthetic_coefficients(const std::uint32_t point) {
  constexpr Coefficients values[kPoints] = {
      {0x1.0000000000000p-3, 0x1.0000000000000p-4, 0x1.8000000000000p-5, 0x1.4000000000000p-3,
       0x1.0000000000000p-5, 0x1.0000000000000p-4, 0x1.0000000000000p-6},
      {0x1.4000000000000p-3, 0x1.8000000000000p-4, 0x1.0000000000000p-5, 0x1.0000000000000p-3,
       0x1.8000000000000p-5, 0x1.4000000000000p-4, 0x1.0000000000000p-7},
      {0x1.8000000000000p-3, 0x1.0000000000000p-5, 0x1.4000000000000p-5, 0x1.8000000000000p-3,
       0x1.0000000000000p-6, 0x1.8000000000000p-4, 0x1.4000000000000p-7},
      {0x1.0000000000000p-2, 0x1.4000000000000p-4, 0x1.8000000000000p-5, 0x1.4000000000000p-3,
       0x1.4000000000000p-5, 0x1.0000000000000p-4, 0x1.8000000000000p-7},
  };
  return values[point];
}

static bool run_self_test() {
  int device_count = 0;
  if (cudaGetDeviceCount(&device_count) != cudaSuccess || device_count <= 0) return false;
  int selected = -1;
  cudaDeviceProp property{};
  for (int device = 0; device < device_count; ++device) {
    cudaDeviceProp candidate{};
    if (cudaGetDeviceProperties(&candidate, device) == cudaSuccess && candidate.major > 0) {
      selected = device;
      property = candidate;
      break;
    }
  }
  if (selected < 0 || cudaSetDevice(selected) != cudaSuccess) return false;

  Terms host_terms[kStates];
  Coefficients host_coefficients[kPoints];
  for (std::uint32_t state = 0; state < kStates; ++state) host_terms[state] = synthetic_terms(state);
  for (std::uint32_t point = 0; point < kPoints; ++point) host_coefficients[point] = synthetic_coefficients(point);
  constexpr std::uint32_t energy_count = kStates * kPoints * kEncodings;
  Terms* device_terms = nullptr;
  Coefficients* device_coefficients = nullptr;
  std::uint64_t* device_words = nullptr;
  std::uint8_t* device_nonfinite = nullptr;
  std::uint64_t* device_minimum_words = nullptr;
  std::uint32_t* device_minimum_indices = nullptr;
  std::uint8_t* device_flags = nullptr;
  bool ok = cudaMalloc(&device_terms, sizeof(host_terms)) == cudaSuccess &&
            cudaMalloc(&device_coefficients, sizeof(host_coefficients)) == cudaSuccess &&
            cudaMalloc(&device_words, sizeof(std::uint64_t) * energy_count) == cudaSuccess &&
            cudaMalloc(&device_nonfinite, sizeof(std::uint8_t) * energy_count) == cudaSuccess &&
            cudaMalloc(&device_minimum_words, sizeof(std::uint64_t) * kPoints * kEncodings) == cudaSuccess &&
            cudaMalloc(&device_minimum_indices, sizeof(std::uint32_t) * kPoints * kEncodings) == cudaSuccess &&
            cudaMalloc(&device_flags, sizeof(std::uint8_t) * energy_count) == cudaSuccess;
  ok = ok && cudaMemcpy(device_terms, host_terms, sizeof(host_terms), cudaMemcpyHostToDevice) == cudaSuccess &&
       cudaMemcpy(device_coefficients, host_coefficients, sizeof(host_coefficients), cudaMemcpyHostToDevice) == cudaSuccess;
  if (ok) G9_LAUNCH(energy_kernel, dim3((kStates + kBlockSize - 1u) / kBlockSize), dim3(kBlockSize),
                    device_terms, device_coefficients, device_words, device_nonfinite);
  if (ok) G9_LAUNCH(minimum_kernel, dim3(1), dim3(kPoints * kEncodings), device_words, device_minimum_words, device_minimum_indices);
  if (ok) G9_LAUNCH(tie_flags_kernel, dim3((kStates + kBlockSize - 1u) / kBlockSize), dim3(kBlockSize),
                    device_words, device_minimum_words, device_flags);
  ok = ok && cudaGetLastError() == cudaSuccess && cudaDeviceSynchronize() == cudaSuccess;
  std::uint64_t host_words[energy_count]{};
  std::uint8_t host_nonfinite[energy_count]{};
  std::uint64_t host_minimum_words[kPoints * kEncodings]{};
  std::uint32_t host_minimum_indices[kPoints * kEncodings]{};
  std::uint8_t host_flags[energy_count]{};
  ok = ok && cudaMemcpy(host_words, device_words, sizeof(host_words), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(host_nonfinite, device_nonfinite, sizeof(host_nonfinite), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(host_minimum_words, device_minimum_words, sizeof(host_minimum_words), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(host_minimum_indices, device_minimum_indices, sizeof(host_minimum_indices), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(host_flags, device_flags, sizeof(host_flags), cudaMemcpyDeviceToHost) == cudaSuccess;
  std::uint64_t energy_checksum = kFNVOffset;
  std::uint64_t minimum_checksum = kFNVOffset;
  std::uint64_t flags_checksum = kFNVOffset;
  std::uint32_t tie_counts[kPoints * kEncodings][kCHCount]{};
  std::uint32_t nonfinite_total = 0;
  if (ok) {
    for (std::uint32_t index = 0; index < energy_count; ++index) {
      energy_checksum = fnv_word(energy_checksum, host_words[index]);
      flags_checksum = fnv_word(flags_checksum, static_cast<std::uint64_t>(host_flags[index]));
      nonfinite_total += host_nonfinite[index];
      const std::uint32_t pair = index / kStates;
      for (std::uint32_t c_h = 0; c_h < kCHCount; ++c_h) {
        if ((host_flags[index] & (1u << c_h)) != 0u) tie_counts[pair][c_h] += 1u;
      }
    }
    for (std::uint32_t pair = 0; pair < kPoints * kEncodings; ++pair) {
      minimum_checksum = fnv_word(minimum_checksum, host_minimum_words[pair]);
      minimum_checksum = fnv_word(minimum_checksum, host_minimum_indices[pair]);
    }
    std::printf("{\"schema\":\"decisions_os/g9_cuda_generic_self_test/v1\",\"device_index\":%d,\"device_name\":\"%s\",\"state_count\":%u,\"point_count\":%u,\"energy_checksum\":\"%016llx\",\"minimum_checksum\":\"%016llx\",\"flags_checksum\":\"%016llx\",\"tie_counts\":[",
                selected, property.name, kStates, kPoints, static_cast<unsigned long long>(energy_checksum),
                static_cast<unsigned long long>(minimum_checksum), static_cast<unsigned long long>(flags_checksum));
    for (std::uint32_t pair = 0; pair < kPoints * kEncodings; ++pair) {
      if (pair != 0u) std::printf(",");
      std::printf("[%u,%u,%u]", tie_counts[pair][0], tie_counts[pair][1], tie_counts[pair][2]);
    }
    std::printf("],\"nonfinite_energies\":%u,\"scientific_outputs\":\"intentionally absent\",\"verdict\":\"%s\"}\n",
                nonfinite_total, nonfinite_total == 0 ? "pass" : "fail");
  }
  cudaFree(device_terms); cudaFree(device_coefficients); cudaFree(device_words); cudaFree(device_nonfinite);
  cudaFree(device_minimum_words); cudaFree(device_minimum_indices); cudaFree(device_flags);
  return ok && nonfinite_total == 0;
}

int main(int argc, char** argv) {
  if (argc != 2 || std::strcmp(argv[1], "--self-test") != 0) {
    std::fprintf(stderr, "usage: stage2_cuda_generic_engine --self-test\\n");
    return 2;
  }
  if (!run_self_test()) {
    std::fprintf(stderr, "FAIL Stage-2 generic CUDA self-test\\n");
    return 1;
  }
  return 0;
}
