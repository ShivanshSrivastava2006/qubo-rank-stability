// Generic Stage-2 prepared-domain self-test — artificial data only.
//
// This companion to stage2_cuda_generic_engine.cu implements the actual fixed
// 20-asset decoded preparation and 19-bit exact slack-register lift used by
// the future generic producer.  It has no input parser or production mode:
// --self-test builds one fixed artificial instance, selects 257 exactly
// liftable canonical decoded states, and emits checksums only.  No Stage-2
// candidate, ledger, minimum, label, or scientific record exists here.

#include <cuda_runtime.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#pragma STDC FP_CONTRACT OFF

#if defined(__CUDACC__)
#define G9_PREP_LAUNCH(kernel, grid, block, ...) kernel<<<grid, block>>>(__VA_ARGS__)
#else
#define G9_PREP_LAUNCH(kernel, grid, block, ...) g6_host_emulation_launch(kernel, grid, block, __VA_ARGS__)
#endif

constexpr std::uint32_t kAssetCount = 20;
constexpr std::uint32_t kSectorCount = 4;
constexpr std::uint32_t kSectorSize = 5;
constexpr std::uint32_t kSectorBits = 2;
constexpr std::uint32_t kBudgetBits = 11;
constexpr std::uint32_t kAuxiliaryBits = kSectorCount * kSectorBits + kBudgetBits;
constexpr std::uint32_t kSelfTestStates = 257;
constexpr std::uint32_t kBlockSize = 64;
constexpr std::uint64_t kFNVOffset = 1469598103934665603ULL;
constexpr std::uint64_t kFNVPrime = 1099511628211ULL;

struct InstanceData {
  double mu[kAssetCount];
  double sigma[kAssetCount * kAssetCount];
  double prices[kAssetCount];
  double kappa_risk;
  double k_float;
  double c_float;
  double b;
};

struct PreparedTerms {
  double f_value;
  double card_square;
  double h_sector[kSectorCount];
  double sector_square[kSectorCount];
  double h_budget;
  double budget_square;
  double sector_slack_square[kSectorCount];
  double budget_slack_square;
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

__host__ __device__ static bool word_is_nonfinite(const std::uint64_t word) {
  return ((word >> 52) & 0x7ffULL) == 0x7ffULL;
}

__host__ __device__ static std::uint64_t canonical_index_to_mask(const std::uint32_t index) {
  std::uint64_t mask = 0;
  for (std::uint32_t i = 0; i < kAssetCount; ++i) {
    mask |= static_cast<std::uint64_t>((index >> (kAssetCount - 1u - i)) & 1u) << i;
  }
  return mask;
}

__host__ __device__ static void prepare_decoded(const InstanceData* instance, const std::uint64_t mask,
                                                PreparedTerms* out) {
  double x[kAssetCount];
  for (std::uint32_t i = 0; i < kAssetCount; ++i) x[i] = ((mask >> i) & 1ULL) ? 1.0 : 0.0;
  double f_acc = +0.0;
  for (std::uint32_t i = 0; i < kAssetCount; ++i) {
    const double mu_term = -(instance->mu[i] * x[i]);
    f_acc = f_acc + mu_term;
  }
  for (std::uint32_t i = 0; i < kAssetCount; ++i) {
    for (std::uint32_t k = 0; k < kAssetCount; ++k) {
      const double sigma_xi = instance->sigma[i * kAssetCount + k] * x[i];
      const double product = sigma_xi * x[k];
      f_acc = f_acc + (instance->kappa_risk * product);
    }
  }
  double card = +0.0;
  for (std::uint32_t i = 0; i < kAssetCount; ++i) card = card + x[i];
  out->f_value = f_acc;
  const double h_card = card - instance->k_float;
  out->card_square = h_card * h_card;
  for (std::uint32_t sector = 0; sector < kSectorCount; ++sector) {
    double sum = +0.0;
    for (std::uint32_t offset = 0; offset < kSectorSize; ++offset) sum = sum + x[sector * kSectorSize + offset];
    const double residual = instance->c_float - sum;
    out->h_sector[sector] = residual;
    out->sector_square[sector] = residual * residual;
  }
  double budget = +0.0;
  for (std::uint32_t i = 0; i < kAssetCount; ++i) budget = budget + (instance->prices[i] * x[i]);
  out->h_budget = instance->b - budget;
  out->budget_square = out->h_budget * out->h_budget;
}

// Exact slack lift: sector bits occur sector-major with two bits each, then
// eleven budget bits.  The host has already selected only representable words;
// this transcript still computes every bit-weighted register and square.
__host__ __device__ static void prepare_slack(const PreparedTerms* decoded, const std::uint64_t auxiliary,
                                              PreparedTerms* out) {
  *out = *decoded;
  std::uint32_t offset = 0;
  for (std::uint32_t sector = 0; sector < kSectorCount; ++sector) {
    double register_value = +0.0;
    for (std::uint32_t bit = 0; bit < kSectorBits; ++bit) {
      const double value = ((auxiliary >> (offset + bit)) & 1ULL) ? 1.0 : 0.0;
      const double weight = static_cast<double>(1ULL << bit);
      register_value = register_value + (weight * value);
    }
    offset = offset + kSectorBits;
    const double delta = decoded->h_sector[sector] - register_value;
    out->sector_slack_square[sector] = delta * delta;
  }
  double budget_register = +0.0;
  for (std::uint32_t bit = 0; bit < kBudgetBits; ++bit) {
    const double value = ((auxiliary >> (offset + bit)) & 1ULL) ? 1.0 : 0.0;
    const double weight = static_cast<double>(1ULL << bit);
    budget_register = budget_register + (weight * value);
  }
  const double budget_delta = decoded->h_budget - budget_register;
  out->budget_slack_square = budget_delta * budget_delta;
}

__global__ void prepare_kernel(const InstanceData* instance, const std::uint32_t* indices,
                               const std::uint64_t* auxiliary, PreparedTerms* terms, std::uint8_t* nonfinite) {
  const std::uint32_t state = blockIdx.x * blockDim.x + threadIdx.x;
  if (state >= kSelfTestStates) return;
  PreparedTerms decoded{};
  prepare_decoded(instance, canonical_index_to_mask(indices[state]), &decoded);
  prepare_slack(&decoded, auxiliary[state], &terms[state]);
  bool bad = word_is_nonfinite(double_to_word(terms[state].f_value)) ||
             word_is_nonfinite(double_to_word(terms[state].card_square)) ||
             word_is_nonfinite(double_to_word(terms[state].h_budget)) ||
             word_is_nonfinite(double_to_word(terms[state].budget_slack_square));
  for (std::uint32_t sector = 0; sector < kSectorCount; ++sector) {
    bad = bad || word_is_nonfinite(double_to_word(terms[state].h_sector[sector])) ||
          word_is_nonfinite(double_to_word(terms[state].sector_square[sector])) ||
          word_is_nonfinite(double_to_word(terms[state].sector_slack_square[sector]));
  }
  nonfinite[state] = bad ? 1u : 0u;
}

static std::uint64_t fnv_word(const std::uint64_t state, const std::uint64_t word) {
  return (state ^ word) * kFNVPrime;
}

static InstanceData synthetic_instance() {
  InstanceData value{};
  for (std::uint32_t i = 0; i < kAssetCount; ++i) {
    value.mu[i] = (static_cast<double>(i) - 9.0) / 1000.0;
    value.prices[i] = static_cast<double>(1u + (i % 5u));
    for (std::uint32_t k = 0; k < kAssetCount; ++k) {
      value.sigma[i * kAssetCount + k] = i == k ? (0.01 + static_cast<double>(i) / 10000.0)
                                                    : static_cast<double>((i + k) % 7u) / 100000.0;
    }
  }
  value.kappa_risk = 1.0;
  value.k_float = 6.0;
  value.c_float = 2.0;
  value.b = 32.0;
  return value;
}

static bool exact_auxiliary_for_mask(const InstanceData* instance, const std::uint64_t mask, std::uint64_t* output) {
  std::uint64_t auxiliary = 0;
  std::uint32_t offset = 0;
  for (std::uint32_t sector = 0; sector < kSectorCount; ++sector) {
    std::uint32_t count = 0;
    for (std::uint32_t member = 0; member < kSectorSize; ++member) count += (mask >> (sector * kSectorSize + member)) & 1ULL;
    const int residual = static_cast<int>(instance->c_float) - static_cast<int>(count);
    if (residual < 0 || residual >= (1 << kSectorBits)) return false;
    auxiliary |= static_cast<std::uint64_t>(residual) << offset;
    offset += kSectorBits;
  }
  std::uint32_t spend = 0;
  for (std::uint32_t i = 0; i < kAssetCount; ++i) {
    if ((mask >> i) & 1ULL) spend += static_cast<std::uint32_t>(instance->prices[i]);
  }
  const int budget_residual = static_cast<int>(instance->b) - static_cast<int>(spend);
  if (budget_residual < 0 || budget_residual >= (1 << kBudgetBits)) return false;
  auxiliary |= static_cast<std::uint64_t>(budget_residual) << offset;
  *output = auxiliary;
  return true;
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
  const InstanceData host_instance = synthetic_instance();
  std::uint32_t host_indices[kSelfTestStates]{};
  std::uint64_t host_auxiliary[kSelfTestStates]{};
  std::uint32_t found = 0;
  for (std::uint32_t index = 0; index < (1u << kAssetCount) && found < kSelfTestStates; ++index) {
    std::uint64_t auxiliary = 0;
    if (exact_auxiliary_for_mask(&host_instance, canonical_index_to_mask(index), &auxiliary)) {
      host_indices[found] = index;
      host_auxiliary[found] = auxiliary;
      ++found;
    }
  }
  if (found != kSelfTestStates) return false;
  InstanceData* device_instance = nullptr;
  std::uint32_t* device_indices = nullptr;
  std::uint64_t* device_auxiliary = nullptr;
  PreparedTerms* device_terms = nullptr;
  std::uint8_t* device_nonfinite = nullptr;
  bool ok = cudaMalloc(&device_instance, sizeof(host_instance)) == cudaSuccess &&
            cudaMalloc(&device_indices, sizeof(host_indices)) == cudaSuccess &&
            cudaMalloc(&device_auxiliary, sizeof(host_auxiliary)) == cudaSuccess &&
            cudaMalloc(&device_terms, sizeof(PreparedTerms) * kSelfTestStates) == cudaSuccess &&
            cudaMalloc(&device_nonfinite, sizeof(std::uint8_t) * kSelfTestStates) == cudaSuccess;
  ok = ok && cudaMemcpy(device_instance, &host_instance, sizeof(host_instance), cudaMemcpyHostToDevice) == cudaSuccess &&
       cudaMemcpy(device_indices, host_indices, sizeof(host_indices), cudaMemcpyHostToDevice) == cudaSuccess &&
       cudaMemcpy(device_auxiliary, host_auxiliary, sizeof(host_auxiliary), cudaMemcpyHostToDevice) == cudaSuccess;
  if (ok) G9_PREP_LAUNCH(prepare_kernel, dim3((kSelfTestStates + kBlockSize - 1u) / kBlockSize), dim3(kBlockSize),
                          device_instance, device_indices, device_auxiliary, device_terms, device_nonfinite);
  ok = ok && cudaGetLastError() == cudaSuccess && cudaDeviceSynchronize() == cudaSuccess;
  PreparedTerms host_terms[kSelfTestStates]{};
  std::uint8_t host_nonfinite[kSelfTestStates]{};
  ok = ok && cudaMemcpy(host_terms, device_terms, sizeof(host_terms), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(host_nonfinite, device_nonfinite, sizeof(host_nonfinite), cudaMemcpyDeviceToHost) == cudaSuccess;
  std::uint64_t domain_checksum = kFNVOffset;
  std::uint64_t auxiliary_checksum = kFNVOffset;
  std::uint64_t terms_checksum = kFNVOffset;
  std::uint32_t nonfinite_total = 0;
  if (ok) {
    for (std::uint32_t state = 0; state < kSelfTestStates; ++state) {
      domain_checksum = fnv_word(domain_checksum, host_indices[state]);
      auxiliary_checksum = fnv_word(auxiliary_checksum, host_auxiliary[state]);
      const PreparedTerms* term = &host_terms[state];
      terms_checksum = fnv_word(terms_checksum, double_to_word(term->f_value));
      terms_checksum = fnv_word(terms_checksum, double_to_word(term->card_square));
      for (std::uint32_t sector = 0; sector < kSectorCount; ++sector) terms_checksum = fnv_word(terms_checksum, double_to_word(term->h_sector[sector]));
      for (std::uint32_t sector = 0; sector < kSectorCount; ++sector) terms_checksum = fnv_word(terms_checksum, double_to_word(term->sector_square[sector]));
      terms_checksum = fnv_word(terms_checksum, double_to_word(term->h_budget));
      terms_checksum = fnv_word(terms_checksum, double_to_word(term->budget_square));
      for (std::uint32_t sector = 0; sector < kSectorCount; ++sector) terms_checksum = fnv_word(terms_checksum, double_to_word(term->sector_slack_square[sector]));
      terms_checksum = fnv_word(terms_checksum, double_to_word(term->budget_slack_square));
      nonfinite_total += host_nonfinite[state];
    }
    std::printf("{\"schema\":\"decisions_os/g9_cuda_preparation_self_test/v1\",\"device_index\":%d,\"device_name\":\"%s\",\"state_count\":%u,\"auxiliary_bits\":%u,\"domain_checksum\":\"%016llx\",\"auxiliary_checksum\":\"%016llx\",\"terms_checksum\":\"%016llx\",\"nonfinite_terms\":%u,\"scientific_outputs\":\"intentionally absent\",\"verdict\":\"%s\"}\n",
                selected, property.name, kSelfTestStates, kAuxiliaryBits, static_cast<unsigned long long>(domain_checksum),
                static_cast<unsigned long long>(auxiliary_checksum), static_cast<unsigned long long>(terms_checksum),
                nonfinite_total, nonfinite_total == 0 ? "pass" : "fail");
  }
  cudaFree(device_instance); cudaFree(device_indices); cudaFree(device_auxiliary); cudaFree(device_terms); cudaFree(device_nonfinite);
  return ok && nonfinite_total == 0;
}

int main(int argc, char** argv) {
  if (argc != 2 || std::strcmp(argv[1], "--self-test") != 0) {
    std::fprintf(stderr, "usage: stage2_cuda_preparation_selftest --self-test\\n");
    return 2;
  }
  if (!run_self_test()) {
    std::fprintf(stderr, "FAIL Stage-2 CUDA preparation self-test\\n");
    return 1;
  }
  return 0;
}
