// Generic arbitrary-membership prepared-domain adapter — synthetic self-test only.
//
// This source is independent of stage2_cuda_preparation_selftest.cu and does
// NOT inherit its contiguous `sector * 5 + offset` sector assumption: the four
// sectors arrive as four explicit sorted five-asset membership lists carried in
// the instance record, so an arbitrary balanced partition is representable.
//
// It has no Stage-2 instance reader, ledger reader, output writer, or
// production mode.  --self-test builds one fixed artificial instance with a
// fixed non-contiguous partition, walks a fixed deterministic list of canonical
// decoded indices, and prints checksums and counters only.  No candidate,
// energy, minimum, tie set, label, rate, record, or file exists here.
//
// Lift policy is taken from the frozen authorities, not invented:
// FROZEN_MATH_SPEC.md §5.1 admits exactly those lifts whose every auxiliary
// register is an exact minimizer for its decoded x, and
// src/g5/domains.py::_register_minimizers realises that per register as the
// clamped floor(h) / floor(h)+1 candidates compared by exact binary64
// (h - S)^2, retaining every tied minimizer.  Exact representability is the
// special case in which the single minimizer is h itself with penalty +0.0;
// out-of-range and half-integer residuals are admitted with a non-zero penalty
// (and, when tied, with two minimizers), never rejected.
//
// Numerical contract: binary64 only; no fp32, FMA, reassociation, atomics,
// shared memory, fast math, FTZ, or libm.  floor is obtained by an exact
// truncating cast, valid for the bounded residuals used here.

#include <cuda_runtime.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#pragma STDC FP_CONTRACT OFF

#if defined(__CUDACC__)
#define G9_ADAPTER_LAUNCH(kernel, grid, block, ...) kernel<<<grid, block>>>(__VA_ARGS__)
#else
#define G9_ADAPTER_LAUNCH(kernel, grid, block, ...) g6_host_emulation_launch(kernel, grid, block, __VA_ARGS__)
#endif

constexpr std::uint32_t kAssetCount = 20;
constexpr std::uint32_t kSectorCount = 4;
constexpr std::uint32_t kSectorSize = 5;
constexpr std::uint32_t kSectorSlackBits = 2;
constexpr std::uint32_t kBudgetSlackBits = 11;
constexpr std::uint32_t kAuxiliaryBits = kSectorCount * kSectorSlackBits + kBudgetSlackBits;
constexpr std::uint32_t kRegisterCount = kSectorCount + 1;
constexpr std::uint32_t kTermCount = 12;
constexpr std::uint32_t kStateCount = 257;
constexpr std::uint32_t kStateStride = 4093;
constexpr std::uint32_t kProbeCount = 12;
constexpr std::uint32_t kBlockSize = 64;
constexpr std::uint64_t kFNVOffset = 1469598103934665603ULL;
constexpr std::uint64_t kFNVPrime = 1099511628211ULL;

struct InstanceData {
  double mu[kAssetCount];
  double sigma[kAssetCount * kAssetCount];
  double prices[kAssetCount];
  double kappa_risk;
  double k_value;
  double c_value;
  double b;
  std::uint32_t membership[kSectorCount][kSectorSize];
};

struct RegisterPolicy {
  std::uint32_t count;
  std::uint32_t exact;
  std::uint32_t invalid;
  std::uint32_t values[2];
  double penalties[2];
};

struct StateOutput {
  double terms[kTermCount];
  RegisterPolicy registers[kRegisterCount];
  double reconstructed[kRegisterCount];
  std::uint32_t packed;
  std::uint32_t lift_count;
  std::uint32_t nonfinite;
  std::uint32_t mismatches;
  std::uint32_t invalid;
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

__host__ __device__ static bool value_is_nonfinite(const double value) {
  return word_is_nonfinite(double_to_word(value));
}

// Canonical 20-bit decoded order, identical to src.g5.domains.BinaryDomain:
// x[i] = (index >> (width - 1 - i)) & 1.
__host__ __device__ static std::uint64_t canonical_index_to_mask(const std::uint32_t index) {
  std::uint64_t mask = 0;
  for (std::uint32_t asset = 0; asset < kAssetCount; ++asset) {
    mask |= static_cast<std::uint64_t>((index >> (kAssetCount - 1u - asset)) & 1u) << asset;
  }
  return mask;
}

__host__ __device__ static std::uint32_t register_maximum(const std::uint32_t reg) {
  const std::uint32_t bits = reg < kSectorCount ? kSectorSlackBits : kBudgetSlackBits;
  return (1u << bits) - 1u;
}

__host__ __device__ static std::uint32_t register_offset(const std::uint32_t reg) {
  return reg < kSectorCount ? (reg * kSectorSlackBits) : (kSectorCount * kSectorSlackBits);
}

__host__ __device__ static double accumulate_mu(const InstanceData* instance, const double* x, double f_acc) {
  for (std::uint32_t asset = 0; asset < kAssetCount; ++asset) {
    const double mu_term = -(instance->mu[asset] * x[asset]);
    f_acc = f_acc + mu_term;
  }
  return f_acc;
}

__host__ __device__ static double accumulate_quadratic(const InstanceData* instance, const double* x, double f_acc) {
  for (std::uint32_t row = 0; row < kAssetCount; ++row) {
    for (std::uint32_t column = 0; column < kAssetCount; ++column) {
      const double sigma_x = instance->sigma[row * kAssetCount + column] * x[row];
      const double product = sigma_x * x[column];
      f_acc = f_acc + (instance->kappa_risk * product);
    }
  }
  return f_acc;
}

// Frozen preparation transcript.  Sector residuals use each sector's explicit
// sorted membership list, never a contiguous block formula.
__host__ __device__ static void decoded_terms(const InstanceData* instance, const std::uint64_t mask, double* terms) {
  double x[kAssetCount];
  for (std::uint32_t asset = 0; asset < kAssetCount; ++asset) {
    x[asset] = ((mask >> asset) & 1ULL) ? 1.0 : 0.0;
  }
  double f_acc = +0.0;
  f_acc = accumulate_mu(instance, x, f_acc);
  f_acc = accumulate_quadratic(instance, x, f_acc);
  double cardinality = +0.0;
  for (std::uint32_t asset = 0; asset < kAssetCount; ++asset) cardinality = cardinality + x[asset];
  const double h_card = cardinality - instance->k_value;
  terms[0] = f_acc;
  terms[1] = h_card * h_card;
  for (std::uint32_t sector = 0; sector < kSectorCount; ++sector) {
    double total = +0.0;
    for (std::uint32_t member = 0; member < kSectorSize; ++member) {
      const std::uint32_t asset = instance->membership[sector][member];
      total = total + x[asset];
    }
    const double residual = instance->c_value - total;
    terms[2u + sector] = residual;
    terms[2u + kSectorCount + sector] = residual * residual;
  }
  double budget = +0.0;
  for (std::uint32_t asset = 0; asset < kAssetCount; ++asset) {
    budget = budget + (instance->prices[asset] * x[asset]);
  }
  const double h_budget = instance->b - budget;
  terms[2u + 2u * kSectorCount] = h_budget;
  terms[3u + 2u * kSectorCount] = h_budget * h_budget;
}

// Exact truncating floor; no libm call and no rounding-mode dependence for the
// bounded residuals this adapter handles.
__host__ __device__ static long long floor_double(const double value) {
  long long lower = static_cast<long long>(value);
  if (static_cast<double>(lower) > value) lower -= 1;
  return lower;
}

__host__ __device__ static std::uint32_t clamp_register(const long long value, const std::uint32_t maximum) {
  if (value < 0) return 0u;
  if (value > static_cast<long long>(maximum)) return maximum;
  return static_cast<std::uint32_t>(value);
}

// src/g5/domains.py::_register_minimizers, per register: clamped floor / floor+1
// candidates, exact binary64 penalties, every tied minimizer retained.
__host__ __device__ static void register_policy(const double residual, const std::uint32_t maximum,
                                                RegisterPolicy* out) {
  out->count = 0u;
  out->exact = 0u;
  out->invalid = 0u;
  out->values[0] = 0u;
  out->values[1] = 0u;
  out->penalties[0] = +0.0;
  out->penalties[1] = +0.0;
  // Fail closed before any narrowing conversion: floor_double's truncating
  // cast is undefined for a non-finite residual, so such a register is marked
  // invalid and neither cast, packed, nor read back.
  if (value_is_nonfinite(residual)) {
    out->invalid = 1u;
    return;
  }
  const long long lower = floor_double(residual);
  const std::uint32_t first = clamp_register(lower, maximum);
  const std::uint32_t second = clamp_register(lower + 1, maximum);
  std::uint32_t candidates[2];
  std::uint32_t candidate_count = 0;
  candidates[candidate_count++] = first < second ? first : second;
  if (first != second) candidates[candidate_count++] = first < second ? second : first;
  double penalties[2];
  for (std::uint32_t index = 0; index < candidate_count; ++index) {
    const double delta = residual - static_cast<double>(candidates[index]);
    penalties[index] = delta * delta;
  }
  double best = penalties[0];
  for (std::uint32_t index = 1; index < candidate_count; ++index) {
    if (penalties[index] < best) best = penalties[index];
  }
  for (std::uint32_t index = 0; index < candidate_count; ++index) {
    if (penalties[index] == best) {
      out->values[out->count] = candidates[index];
      out->penalties[out->count] = penalties[index];
      out->count += 1u;
    }
  }
  // Exact representability is reported separately from the general rule above.
  out->exact = (static_cast<double>(lower) == residual && lower >= 0 &&
                lower <= static_cast<long long>(maximum)) ? 1u : 0u;
}

// Frozen 19-bit layout: sector j occupies two little-endian bits at offset 2j,
// then eleven little-endian budget bits at offset 8.
__host__ __device__ static double unpack_register_value(const std::uint32_t auxiliary, const std::uint32_t reg) {
  const std::uint32_t offset = register_offset(reg);
  double accumulator = +0.0;
  if (reg < kSectorCount) {
    for (std::uint32_t bit = 0; bit < kSectorSlackBits; ++bit) {
      const double value = ((auxiliary >> (offset + bit)) & 1u) ? 1.0 : 0.0;
      const double sector_weight = static_cast<double>(1ULL << bit);
      accumulator = accumulator + (sector_weight * value);
    }
    return accumulator;
  }
  for (std::uint32_t bit = 0; bit < kBudgetSlackBits; ++bit) {
    const double value = ((auxiliary >> (offset + bit)) & 1u) ? 1.0 : 0.0;
    const double budget_weight = static_cast<double>(1ULL << bit);
    accumulator = accumulator + (budget_weight * value);
  }
  return accumulator;
}

__global__ void adapter_kernel(const InstanceData* instance, const std::uint32_t* indices, StateOutput* output) {
  const std::uint32_t state = blockIdx.x * blockDim.x + threadIdx.x;
  if (state >= kStateCount) return;
  StateOutput local{};
  decoded_terms(instance, canonical_index_to_mask(indices[state]), local.terms);
  double residuals[kRegisterCount];
  for (std::uint32_t sector = 0; sector < kSectorCount; ++sector) residuals[sector] = local.terms[2u + sector];
  residuals[kSectorCount] = local.terms[2u + 2u * kSectorCount];
  local.packed = 0u;
  local.invalid = 0u;
  for (std::uint32_t reg = 0; reg < kRegisterCount; ++reg) {
    register_policy(residuals[reg], register_maximum(reg), &local.registers[reg]);
    if (local.registers[reg].invalid != 0u) local.invalid += 1u;
  }
  local.mismatches = 0u;
  if (local.invalid == 0u) {
    local.lift_count = 1u;
    for (std::uint32_t reg = 0; reg < kRegisterCount; ++reg) {
      local.lift_count *= local.registers[reg].count;
      local.packed |= local.registers[reg].values[0] << register_offset(reg);
    }
    for (std::uint32_t reg = 0; reg < kRegisterCount; ++reg) {
      const double value = unpack_register_value(local.packed, reg);
      const double delta = residuals[reg] - value;
      local.reconstructed[reg] = delta * delta;
      if (double_to_word(local.reconstructed[reg]) != double_to_word(local.registers[reg].penalties[0])) {
        local.mismatches += 1u;
      }
    }
  } else {
    // No lift exists for this state: nothing is packed and no register value
    // is read back, so an invalid residual cannot reach the layout path.
    local.lift_count = 0u;
    for (std::uint32_t reg = 0; reg < kRegisterCount; ++reg) local.reconstructed[reg] = +0.0;
  }
  local.nonfinite = 0u;
  for (std::uint32_t term = 0; term < kTermCount; ++term) {
    if (value_is_nonfinite(local.terms[term])) local.nonfinite += 1u;
  }
  for (std::uint32_t reg = 0; reg < kRegisterCount; ++reg) {
    if (value_is_nonfinite(local.reconstructed[reg])) local.nonfinite += 1u;
    for (std::uint32_t index = 0; index < local.registers[reg].count; ++index) {
      if (value_is_nonfinite(local.registers[reg].penalties[index])) local.nonfinite += 1u;
    }
  }
  output[state] = local;
}

__global__ void probe_kernel(const double* residuals, const std::uint32_t* maxima, RegisterPolicy* output) {
  const std::uint32_t probe = blockIdx.x * blockDim.x + threadIdx.x;
  if (probe >= kProbeCount) return;
  register_policy(residuals[probe], maxima[probe], &output[probe]);
}

static std::uint64_t fnv_word(const std::uint64_t state, const std::uint64_t word) {
  return (state ^ word) * kFNVPrime;
}

// Fixed synthetic non-contiguous balanced partition: each block sorted, the
// four blocks disjoint and covering 0..19, and no block a contiguous run.
static InstanceData synthetic_instance() {
  InstanceData value{};
  for (std::uint32_t asset = 0; asset < kAssetCount; ++asset) {
    value.mu[asset] = (static_cast<double>(asset) - 9.0) / 1000.0;
    value.prices[asset] = static_cast<double>(1u + (asset % 5u));
    for (std::uint32_t other = 0; other < kAssetCount; ++other) {
      value.sigma[asset * kAssetCount + other] =
          asset == other ? (0.01 + static_cast<double>(asset) / 10000.0)
                         : static_cast<double>((asset + other) % 7u) / 100000.0;
    }
  }
  value.kappa_risk = 1.0;
  value.k_value = 6.0;
  value.c_value = 2.0;
  value.b = 1100.0;
  const std::uint32_t blocks[kSectorCount][kSectorSize] = {
      {0u, 5u, 9u, 14u, 19u}, {1u, 4u, 8u, 12u, 17u}, {2u, 6u, 10u, 13u, 16u}, {3u, 7u, 11u, 15u, 18u}};
  for (std::uint32_t sector = 0; sector < kSectorCount; ++sector) {
    for (std::uint32_t member = 0; member < kSectorSize; ++member) {
      value.membership[sector][member] = blocks[sector][member];
    }
  }
  return value;
}

static void synthetic_probes(double* residuals, std::uint32_t* maxima) {
  const double probe_residuals[kProbeCount] = {2.0, 0.0, 3.0, -1.0, -2.5, 4.0,
                                               0.5, 1.5, 2.5, 1100.0, 2047.5, -0.5};
  const std::uint32_t probe_maxima[kProbeCount] = {3u, 3u, 3u, 3u, 3u, 3u, 3u, 3u, 3u, 2047u, 2047u, 2047u};
  for (std::uint32_t probe = 0; probe < kProbeCount; ++probe) {
    residuals[probe] = probe_residuals[probe];
    maxima[probe] = probe_maxima[probe];
  }
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
  std::uint32_t host_indices[kStateCount]{};
  for (std::uint32_t position = 0; position < kStateCount; ++position) {
    host_indices[position] = static_cast<std::uint32_t>(
        (static_cast<std::uint64_t>(position) * kStateStride) % (1ULL << kAssetCount));
  }
  double host_probe_residuals[kProbeCount]{};
  std::uint32_t host_probe_maxima[kProbeCount]{};
  synthetic_probes(host_probe_residuals, host_probe_maxima);

  InstanceData* device_instance = nullptr;
  std::uint32_t* device_indices = nullptr;
  StateOutput* device_output = nullptr;
  double* device_probe_residuals = nullptr;
  std::uint32_t* device_probe_maxima = nullptr;
  RegisterPolicy* device_probe_output = nullptr;
  bool ok = cudaMalloc(&device_instance, sizeof(host_instance)) == cudaSuccess &&
            cudaMalloc(&device_indices, sizeof(host_indices)) == cudaSuccess &&
            cudaMalloc(&device_output, sizeof(StateOutput) * kStateCount) == cudaSuccess &&
            cudaMalloc(&device_probe_residuals, sizeof(host_probe_residuals)) == cudaSuccess &&
            cudaMalloc(&device_probe_maxima, sizeof(host_probe_maxima)) == cudaSuccess &&
            cudaMalloc(&device_probe_output, sizeof(RegisterPolicy) * kProbeCount) == cudaSuccess;
  ok = ok && cudaMemcpy(device_instance, &host_instance, sizeof(host_instance), cudaMemcpyHostToDevice) == cudaSuccess &&
       cudaMemcpy(device_indices, host_indices, sizeof(host_indices), cudaMemcpyHostToDevice) == cudaSuccess &&
       cudaMemcpy(device_probe_residuals, host_probe_residuals, sizeof(host_probe_residuals), cudaMemcpyHostToDevice) == cudaSuccess &&
       cudaMemcpy(device_probe_maxima, host_probe_maxima, sizeof(host_probe_maxima), cudaMemcpyHostToDevice) == cudaSuccess;
  if (ok) G9_ADAPTER_LAUNCH(adapter_kernel, dim3((kStateCount + kBlockSize - 1u) / kBlockSize), dim3(kBlockSize),
                            device_instance, device_indices, device_output);
  if (ok) G9_ADAPTER_LAUNCH(probe_kernel, dim3(1), dim3(kProbeCount),
                            device_probe_residuals, device_probe_maxima, device_probe_output);
  ok = ok && cudaGetLastError() == cudaSuccess && cudaDeviceSynchronize() == cudaSuccess;

  StateOutput host_output[kStateCount]{};
  RegisterPolicy host_probe_output[kProbeCount]{};
  ok = ok && cudaMemcpy(host_output, device_output, sizeof(host_output), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(host_probe_output, device_probe_output, sizeof(host_probe_output), cudaMemcpyDeviceToHost) == cudaSuccess;

  std::uint64_t membership_checksum = kFNVOffset;
  std::uint64_t domain_checksum = kFNVOffset;
  std::uint64_t terms_checksum = kFNVOffset;
  std::uint64_t policy_checksum = kFNVOffset;
  std::uint64_t packed_checksum = kFNVOffset;
  std::uint64_t probe_checksum = kFNVOffset;
  std::uint32_t exact_registers = 0;
  std::uint32_t clamped_registers = 0;
  std::uint32_t tied_registers = 0;
  std::uint64_t total_lifts = 0;
  std::uint32_t reconstruction_mismatches = 0;
  std::uint32_t invalid_registers = 0;
  std::uint32_t nonfinite_terms = 0;
  if (ok) {
    for (std::uint32_t sector = 0; sector < kSectorCount; ++sector) {
      for (std::uint32_t member = 0; member < kSectorSize; ++member) {
        membership_checksum = fnv_word(membership_checksum, host_instance.membership[sector][member]);
      }
    }
    for (std::uint32_t state = 0; state < kStateCount; ++state) {
      const StateOutput* row = &host_output[state];
      domain_checksum = fnv_word(domain_checksum, host_indices[state]);
      for (std::uint32_t term = 0; term < kTermCount; ++term) {
        terms_checksum = fnv_word(terms_checksum, double_to_word(row->terms[term]));
      }
      for (std::uint32_t reg = 0; reg < kRegisterCount; ++reg) {
        const RegisterPolicy* policy = &row->registers[reg];
        policy_checksum = fnv_word(policy_checksum, policy->count);
        policy_checksum = fnv_word(policy_checksum, policy->exact);
        policy_checksum = fnv_word(policy_checksum, policy->invalid);
        for (std::uint32_t index = 0; index < policy->count; ++index) {
          policy_checksum = fnv_word(policy_checksum, policy->values[index]);
          policy_checksum = fnv_word(policy_checksum, double_to_word(policy->penalties[index]));
        }
        if (policy->exact != 0u) exact_registers += 1u; else clamped_registers += 1u;
        if (policy->count > 1u) tied_registers += 1u;
      }
      total_lifts += row->lift_count;
      packed_checksum = fnv_word(packed_checksum, row->packed);
      for (std::uint32_t reg = 0; reg < kRegisterCount; ++reg) {
        packed_checksum = fnv_word(packed_checksum, double_to_word(row->reconstructed[reg]));
      }
      reconstruction_mismatches += row->mismatches;
      invalid_registers += row->invalid;
      nonfinite_terms += row->nonfinite;
    }
    for (std::uint32_t probe = 0; probe < kProbeCount; ++probe) {
      const RegisterPolicy* policy = &host_probe_output[probe];
      probe_checksum = fnv_word(probe_checksum, policy->count);
      probe_checksum = fnv_word(probe_checksum, policy->exact);
      probe_checksum = fnv_word(probe_checksum, policy->invalid);
      for (std::uint32_t index = 0; index < policy->count; ++index) {
        probe_checksum = fnv_word(probe_checksum, policy->values[index]);
        probe_checksum = fnv_word(probe_checksum, double_to_word(policy->penalties[index]));
      }
    }
    const bool pass = nonfinite_terms == 0u && reconstruction_mismatches == 0u && invalid_registers == 0u;
    std::printf("{\"schema\":\"decisions_os/g9_cuda_membership_adapter_self_test/v1\",\"device_index\":%d,\"device_name\":\"%s\",\"state_count\":%u,\"auxiliary_bits\":%u,\"register_count\":%u,\"probe_count\":%u,\"membership_checksum\":\"%016llx\",\"domain_checksum\":\"%016llx\",\"terms_checksum\":\"%016llx\",\"lift_policy_checksum\":\"%016llx\",\"packed_lift_checksum\":\"%016llx\",\"policy_probe_checksum\":\"%016llx\",\"exact_registers\":%u,\"clamped_registers\":%u,\"tied_registers\":%u,\"total_lifts\":%llu,\"reconstruction_mismatches\":%u,\"invalid_registers\":%u,\"nonfinite_terms\":%u,\"scientific_outputs\":\"intentionally absent\",\"verdict\":\"%s\"}\n",
                selected, property.name, kStateCount, kAuxiliaryBits, kRegisterCount, kProbeCount,
                static_cast<unsigned long long>(membership_checksum),
                static_cast<unsigned long long>(domain_checksum),
                static_cast<unsigned long long>(terms_checksum),
                static_cast<unsigned long long>(policy_checksum),
                static_cast<unsigned long long>(packed_checksum),
                static_cast<unsigned long long>(probe_checksum),
                exact_registers, clamped_registers, tied_registers,
                static_cast<unsigned long long>(total_lifts),
                reconstruction_mismatches, invalid_registers, nonfinite_terms, pass ? "pass" : "fail");
  }
  cudaFree(device_instance);
  cudaFree(device_indices);
  cudaFree(device_output);
  cudaFree(device_probe_residuals);
  cudaFree(device_probe_maxima);
  cudaFree(device_probe_output);
  return ok && nonfinite_terms == 0u && reconstruction_mismatches == 0u && invalid_registers == 0u;
}

int main(int argc, char** argv) {
  if (argc != 2 || std::strcmp(argv[1], "--self-test") != 0) {
    std::fprintf(stderr, "usage: stage2_cuda_membership_adapter --self-test\n");
    return 2;
  }
  if (!run_self_test()) {
    std::fprintf(stderr, "FAIL Stage-2 membership adapter self-test\n");
    return 1;
  }
  return 0;
}
