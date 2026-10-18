// Generic capacity-safe full-domain slack-cache self-test — synthetic only.
//
// Independent of every other Stage-2 CUDA component.  It builds the complete
// active-CSB slack-domain cache over the whole canonical decoded domain
// (2^20 positions) for a generic validated in-memory 20-asset payload with
// four explicit sorted five-asset membership lists.  There is no filesystem
// parser, no candidate draw, no coefficient ledger, no energy, no minimum, no
// tie set, no label and no record: the cache holds packed auxiliary registers
// and 64-bit per-state offsets only, and --self-test prints counts, digests
// and capacity evidence — never an entry.
//
// Frozen rules reproduced here, not invented:
//   * canonical decoded order x[i] = (index >> (width - 1 - i)) & 1, matching
//     src.g5.domains.BinaryDomain;
//   * residuals in the frozen transcript order, each accumulator from +0.0 and
//     each sector summed over its own sorted membership;
//   * a register admits the clamped floor(h) / floor(h)+1 candidates compared
//     by exact binary64 (h - S)^2, retaining EVERY tied minimizer;
//   * the lifts of one decoded state are the Cartesian product of the
//     per-register minimizer sets with sector 0 slowest and the budget
//     register fastest, matching the frozen builder's product order;
//   * the frozen 19-bit layout: sector j at offset 2j (two little-endian
//     bits), then eleven little-endian budget bits at offset 8.
//
// Capacity safety: offsets and totals are 64-bit throughout, the total is
// proved to fit the declared capacity BEFORE any cache buffer is allocated or
// written, multiplication is overflow-checked, and a non-finite residual is
// refused before any narrowing conversion.
//
// Numerical contract: binary64 only; no fp32, FMA, reassociation, atomics,
// shared memory, sorting, fast math, FTZ or libm.

#include <cuda_runtime.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#pragma STDC FP_CONTRACT OFF

#if defined(__CUDACC__)
#define G9_CACHE_LAUNCH(kernel, grid, block, ...) kernel<<<grid, block>>>(__VA_ARGS__)
#else
#define G9_CACHE_LAUNCH(kernel, grid, block, ...) g6_host_emulation_launch(kernel, grid, block, __VA_ARGS__)
#endif

constexpr std::uint32_t kAssetCount = 20;
constexpr std::uint32_t kSectorCount = 4;
constexpr std::uint32_t kSectorSize = 5;
constexpr std::uint32_t kSectorSlackBits = 2;
constexpr std::uint32_t kBudgetSlackBits = 11;
constexpr std::uint32_t kAuxiliaryBits = kSectorCount * kSectorSlackBits + kBudgetSlackBits;
constexpr std::uint32_t kRegisterCount = kSectorCount + 1;
constexpr std::uint32_t kDecodedWidth = kAssetCount;
constexpr std::uint64_t kStateCount = 1ULL << kDecodedWidth;
constexpr std::uint32_t kMaxLiftsPerState = 1u << kRegisterCount;
constexpr std::uint64_t kCacheCapacity = kStateCount * static_cast<std::uint64_t>(kMaxLiftsPerState);
constexpr std::uint32_t kProbeCount = 7;
constexpr std::uint32_t kBlockSize = 64;
constexpr std::uint64_t kFNVOffsetA = 1469598103934665603ULL;
constexpr std::uint64_t kFNVOffsetB = 1099511628211ULL;
constexpr std::uint64_t kFNVPrime = 1099511628211ULL;
constexpr std::uint64_t kUint64Max = ~0ULL;

// Capacity arithmetic is 64-bit by contract; the alias makes a downgrade an
// explicit, mutation-testable edit rather than a silent type change.
using CapacityInt = std::uint64_t;

struct PayloadData {
  double prices[kAssetCount];
  double c_value;
  double b;
  std::uint32_t membership[kSectorCount][kSectorSize];
};

__host__ __device__ static bool value_is_nonfinite(const double value) {
  std::uint64_t word = 0;
#if defined(__CUDA_ARCH__)
  word = static_cast<std::uint64_t>(__double_as_longlong(value));
#else
  std::memcpy(&word, &value, sizeof(word));
#endif
  return ((word >> 52) & 0x7ffULL) == 0x7ffULL;
}

// Canonical decoded order, identical to src.g5.domains.BinaryDomain.
__host__ __device__ static double decoded_bit(const std::uint32_t index, const std::uint32_t asset) {
  return ((index >> (kDecodedWidth - 1u - asset)) & 1u) ? 1.0 : 0.0;
}

__host__ __device__ static std::uint32_t register_maximum(const std::uint32_t reg) {
  const std::uint32_t bits = reg < kSectorCount ? kSectorSlackBits : kBudgetSlackBits;
  return (1u << bits) - 1u;
}

__host__ __device__ static std::uint32_t register_offset(const std::uint32_t reg) {
  return reg < kSectorCount ? (reg * kSectorSlackBits) : (kSectorCount * kSectorSlackBits);
}

// Frozen residual transcript: each accumulator starts at +0.0, each sector is
// summed over its own explicit sorted membership list.
__host__ __device__ static void frozen_residuals(const PayloadData* payload, const std::uint32_t index,
                                                 double* residuals) {
  for (std::uint32_t sector = 0; sector < kSectorCount; ++sector) {
    double total = +0.0;
    for (std::uint32_t member = 0; member < kSectorSize; ++member) {
      const std::uint32_t asset = payload->membership[sector][member];
      total = total + decoded_bit(index, asset);
    }
    residuals[sector] = payload->c_value - total;
  }
  double budget = +0.0;
  for (std::uint32_t asset = 0; asset < kAssetCount; ++asset) {
    budget = budget + (payload->prices[asset] * decoded_bit(index, asset));
  }
  residuals[kSectorCount] = payload->b - budget;
}

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

// Frozen per-register rule.  Returns 0 — an invalid register — for a
// non-finite residual and for an extreme finite residual whose squared penalty
// is not finite, exactly as src.g5.domains._register_minimizers refuses them.
// The residual is narrowed only inside [0, maximum), the one range where the
// floor is needed: below it both candidates clamp to 0 and at or above it both
// clamp to maximum, so no out-of-range value ever reaches the cast.
__host__ __device__ static std::uint32_t register_minimizers(const double residual, const std::uint32_t maximum,
                                                             std::uint32_t* values, std::uint32_t* exact) {
  values[0] = 0u;
  values[1] = 0u;
  *exact = 0u;
  if (value_is_nonfinite(residual)) return 0u;
  std::uint32_t low = 0u;
  std::uint32_t high = 0u;
  if (residual < 0.0) {
    low = 0u;
    high = 0u;
  } else if (residual >= static_cast<double>(maximum)) {
    low = maximum;
    high = maximum;
  } else {
    const long long lower = floor_double(residual);
    const std::uint32_t first = clamp_register(lower, maximum);
    const std::uint32_t second = clamp_register(lower + 1, maximum);
    low = first < second ? first : second;
    high = first < second ? second : first;
  }
  const double delta_low = residual - static_cast<double>(low);
  const double delta_high = residual - static_cast<double>(high);
  const double penalty_low = delta_low * delta_low;
  const double penalty_high = delta_high * delta_high;
  // An extreme finite residual squares to infinity: fail closed rather than
  // silently reporting the clamped endpoint.
  if (value_is_nonfinite(penalty_low) || value_is_nonfinite(penalty_high)) return 0u;
  // Exactness needs no cast outside the safe range.
  if (residual >= 0.0 && residual <= static_cast<double>(maximum)) {
    const long long truncated = static_cast<long long>(residual);
    *exact = (static_cast<double>(truncated) == residual) ? 1u : 0u;
  }
  if (low == high) {
    values[0] = low;
    return 1u;
  }
  if (penalty_low < penalty_high) {
    values[0] = low;
    return 1u;
  }
  if (penalty_high < penalty_low) {
    values[0] = high;
    return 1u;
  }
  values[0] = low;
  values[1] = high;
  return 2u;
}

// Overflow-checked capacity proof, evaluated before any allocation or write.
__host__ __device__ static bool capacity_total(const CapacityInt states, const CapacityInt per_state,
                                               const CapacityInt capacity, CapacityInt* total) {
  *total = 0;
  if (per_state != 0 && states > (static_cast<CapacityInt>(kUint64Max) / per_state)) return false;
  const CapacityInt product = states * per_state;
  if (product > capacity) return false;
  *total = product;
  return true;
}

__global__ void count_kernel(const PayloadData* payload, std::uint32_t* counts, std::uint32_t* audit) {
  const std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index >= kStateCount) return;
  double residuals[kRegisterCount];
  frozen_residuals(payload, index, residuals);
  std::uint32_t multiplicity = 1u;
  std::uint32_t invalid = 0u;
  std::uint32_t exact_here = 0u;
  std::uint32_t tied_here = 0u;
  for (std::uint32_t reg = 0; reg < kRegisterCount; ++reg) {
    std::uint32_t values[2];
    std::uint32_t exact = 0u;
    const std::uint32_t count = register_minimizers(residuals[reg], register_maximum(reg), values, &exact);
    if (count == 0u) {
      invalid += 1u;
      continue;
    }
    multiplicity *= count;
    exact_here += exact;
    if (count > 1u) tied_here += 1u;
  }
  if (invalid != 0u || multiplicity > kMaxLiftsPerState) {
    counts[index] = 0u;
    audit[index] = 1u;
    return;
  }
  counts[index] = multiplicity;
  audit[index] = 0u;
  // Register censuses ride in the high bits of the audit word so no extra
  // buffer is needed; they carry no scientific value.
  audit[index] = (exact_here << 8) | (tied_here << 16);
}

// Each decoded state owns a disjoint output range fixed by the 64-bit prefix,
// so the fill needs no atomics and no scheduling assumption.
__global__ void fill_kernel(const PayloadData* payload, const std::uint64_t* offsets, std::uint32_t* masks,
                            std::uint32_t* violations) {
  const std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index >= kStateCount) return;
  double residuals[kRegisterCount];
  frozen_residuals(payload, index, residuals);
  std::uint32_t values[kRegisterCount][2];
  std::uint32_t counts[kRegisterCount];
  for (std::uint32_t reg = 0; reg < kRegisterCount; ++reg) {
    std::uint32_t exact = 0u;
    counts[reg] = register_minimizers(residuals[reg], register_maximum(reg), values[reg], &exact);
  }
  std::uint64_t cursor = offsets[index];
  const std::uint64_t stop = offsets[index + 1];
  // Register order: sector 0 slowest, the budget register fastest.
  for (std::uint32_t a = 0; a < counts[0]; ++a) {
    for (std::uint32_t b = 0; b < counts[1]; ++b) {
      for (std::uint32_t c = 0; c < counts[2]; ++c) {
        for (std::uint32_t d = 0; d < counts[3]; ++d) {
          for (std::uint32_t e = 0; e < counts[4]; ++e) {
            if (cursor >= stop) {
              violations[index] += 1u;
              return;
            }
            masks[cursor] = (values[0][a] << register_offset(0)) | (values[1][b] << register_offset(1)) |
                            (values[2][c] << register_offset(2)) | (values[3][d] << register_offset(3)) |
                            (values[4][e] << register_offset(4));
            cursor = cursor + 1u;
          }
        }
      }
    }
  }
  if (cursor != stop) violations[index] += 1u;
}

// Per-range integrity: the declared span, strict ascent and no duplicates.
__global__ void range_audit_kernel(const std::uint64_t* offsets, const std::uint32_t* masks,
                                   std::uint32_t* unsorted, std::uint32_t* duplicates) {
  const std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index >= kStateCount) return;
  std::uint32_t local_unsorted = 0u;
  std::uint32_t local_duplicate = 0u;
  bool has_previous = false;
  std::uint32_t previous = 0u;
  for (std::uint64_t slot = offsets[index]; slot < offsets[index + 1]; ++slot) {
    const std::uint32_t value = masks[slot];
    if (has_previous) {
      if (value == previous) local_duplicate += 1u;
      if (value <= previous) local_unsorted += 1u;
    }
    previous = value;
    has_previous = true;
  }
  unsorted[index] = local_unsorted;
  duplicates[index] = local_duplicate;
}

__global__ void probe_kernel(const CapacityInt* states, const CapacityInt* per_state,
                             const CapacityInt* capacity, std::uint32_t* accepted, CapacityInt* totals) {
  const std::uint32_t probe = blockIdx.x * blockDim.x + threadIdx.x;
  if (probe >= kProbeCount) return;
  CapacityInt total = 0;
  accepted[probe] = capacity_total(states[probe], per_state[probe], capacity[probe], &total) ? 1u : 0u;
  totals[probe] = total;
}

// Deterministic two-lane FNV checksum over explicit little-endian bytes, so
// the value does not depend on host endianness.  This is a SYNTHETIC
// CORRUPTION CHECKSUM ONLY: it is not SHA-256, not cryptographic, and is never
// a provenance or content identity.
struct Digest {
  std::uint64_t low;
  std::uint64_t high;
};

static void digest_byte(Digest* digest, const std::uint8_t byte) {
  digest->low = (digest->low ^ static_cast<std::uint64_t>(byte)) * kFNVPrime;
  digest->high = (digest->high ^ static_cast<std::uint64_t>(byte ^ 0xFFu)) * kFNVPrime;
}

static void digest_u32(Digest* digest, const std::uint32_t value) {
  for (std::uint32_t shift = 0; shift < 32u; shift += 8u) {
    digest_byte(digest, static_cast<std::uint8_t>((value >> shift) & 0xFFu));
  }
}

static void digest_u64(Digest* digest, const std::uint64_t value) {
  for (std::uint32_t shift = 0; shift < 64u; shift += 8u) {
    digest_byte(digest, static_cast<std::uint8_t>((value >> shift) & 0xFFu));
  }
}

// Host-side buffers live in static storage: 2^20 entries would overflow the
// stack, and no scientific value is ever placed in them.
static std::uint32_t g_counts[kStateCount];
static std::uint32_t g_audit[kStateCount];
static std::uint64_t g_offsets[kStateCount + 1];
static std::uint32_t g_unsorted[kStateCount];
static std::uint32_t g_duplicates[kStateCount];
static std::uint32_t g_violations[kStateCount];

static PayloadData synthetic_payload() {
  PayloadData value{};
  for (std::uint32_t asset = 0; asset < kAssetCount; ++asset) {
    value.prices[asset] = static_cast<double>(1u + (asset % 5u));
  }
  // One deliberately fractional price makes half-integer budget residuals, so
  // naturally tied budget registers occur across the domain.
  value.prices[7] = 2.5;
  value.c_value = 2.0;
  value.b = 40.0;
  const std::uint32_t blocks[kSectorCount][kSectorSize] = {
      {0u, 6u, 11u, 15u, 19u}, {1u, 5u, 10u, 14u, 18u}, {2u, 7u, 9u, 13u, 17u}, {3u, 4u, 8u, 12u, 16u}};
  for (std::uint32_t sector = 0; sector < kSectorCount; ++sector) {
    for (std::uint32_t member = 0; member < kSectorSize; ++member) {
      value.membership[sector][member] = blocks[sector][member];
    }
  }
  return value;
}

static void synthetic_probes(CapacityInt* states, CapacityInt* per_state, CapacityInt* capacity) {
  const CapacityInt probe_states[kProbeCount] = {kStateCount, kStateCount, kStateCount, kStateCount,
                                                 1ULL << 62, kUint64Max, 0ULL};
  const CapacityInt probe_per_state[kProbeCount] = {1ULL, kMaxLiftsPerState, kMaxLiftsPerState + 1ULL,
                                                    1ULL << 44, 1ULL << 32, 2ULL, 5ULL};
  for (std::uint32_t probe = 0; probe < kProbeCount; ++probe) {
    states[probe] = probe_states[probe];
    per_state[probe] = probe_per_state[probe];
    capacity[probe] = kCacheCapacity;
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

  const PayloadData host_payload = synthetic_payload();
  CapacityInt host_probe_states[kProbeCount]{};
  CapacityInt host_probe_per_state[kProbeCount]{};
  CapacityInt host_probe_capacity[kProbeCount]{};
  synthetic_probes(host_probe_states, host_probe_per_state, host_probe_capacity);

  PayloadData* device_payload = nullptr;
  std::uint32_t* device_counts = nullptr;
  std::uint32_t* device_audit = nullptr;
  std::uint64_t* device_offsets = nullptr;
  std::uint32_t* device_unsorted = nullptr;
  std::uint32_t* device_duplicates = nullptr;
  std::uint32_t* device_violations = nullptr;
  std::uint32_t* device_masks = nullptr;
  CapacityInt* device_probe_states = nullptr;
  CapacityInt* device_probe_per_state = nullptr;
  CapacityInt* device_probe_capacity = nullptr;
  CapacityInt* device_probe_totals = nullptr;
  std::uint32_t* device_probe_accepted = nullptr;

  bool ok = cudaMalloc(&device_payload, sizeof(host_payload)) == cudaSuccess &&
            cudaMalloc(&device_counts, sizeof(std::uint32_t) * kStateCount) == cudaSuccess &&
            cudaMalloc(&device_audit, sizeof(std::uint32_t) * kStateCount) == cudaSuccess &&
            cudaMalloc(&device_offsets, sizeof(std::uint64_t) * (kStateCount + 1ULL)) == cudaSuccess &&
            cudaMalloc(&device_unsorted, sizeof(std::uint32_t) * kStateCount) == cudaSuccess &&
            cudaMalloc(&device_duplicates, sizeof(std::uint32_t) * kStateCount) == cudaSuccess &&
            cudaMalloc(&device_violations, sizeof(std::uint32_t) * kStateCount) == cudaSuccess &&
            cudaMalloc(&device_probe_states, sizeof(host_probe_states)) == cudaSuccess &&
            cudaMalloc(&device_probe_per_state, sizeof(host_probe_per_state)) == cudaSuccess &&
            cudaMalloc(&device_probe_capacity, sizeof(host_probe_capacity)) == cudaSuccess &&
            cudaMalloc(&device_probe_totals, sizeof(CapacityInt) * kProbeCount) == cudaSuccess &&
            cudaMalloc(&device_probe_accepted, sizeof(std::uint32_t) * kProbeCount) == cudaSuccess;
  ok = ok && cudaMemcpy(device_payload, &host_payload, sizeof(host_payload), cudaMemcpyHostToDevice) == cudaSuccess &&
       cudaMemcpy(device_probe_states, host_probe_states, sizeof(host_probe_states), cudaMemcpyHostToDevice) == cudaSuccess &&
       cudaMemcpy(device_probe_per_state, host_probe_per_state, sizeof(host_probe_per_state), cudaMemcpyHostToDevice) == cudaSuccess &&
       cudaMemcpy(device_probe_capacity, host_probe_capacity, sizeof(host_probe_capacity), cudaMemcpyHostToDevice) == cudaSuccess;

  const dim3 state_grid(static_cast<unsigned>((kStateCount + kBlockSize - 1u) / kBlockSize));
  if (ok) G9_CACHE_LAUNCH(count_kernel, state_grid, dim3(kBlockSize), device_payload, device_counts, device_audit);
  if (ok) G9_CACHE_LAUNCH(probe_kernel, dim3(1), dim3(kProbeCount), device_probe_states, device_probe_per_state,
                          device_probe_capacity, device_probe_accepted, device_probe_totals);
  ok = ok && cudaGetLastError() == cudaSuccess && cudaDeviceSynchronize() == cudaSuccess;
  ok = ok && cudaMemcpy(g_counts, device_counts, sizeof(std::uint32_t) * kStateCount, cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(g_audit, device_audit, sizeof(std::uint32_t) * kStateCount, cudaMemcpyDeviceToHost) == cudaSuccess;

  // Capacity proof BEFORE the cache buffer exists.
  CapacityInt lift_total = 0;
  std::uint32_t invalid_residuals = 0;
  std::uint64_t exact_registers = 0;
  std::uint64_t tied_registers = 0;
  if (ok) {
    g_offsets[0] = 0ULL;
    for (std::uint64_t index = 0; index < kStateCount; ++index) {
      if (g_audit[index] == 1u) invalid_residuals += 1u;
      exact_registers += (g_audit[index] >> 8) & 0xFFu;
      tied_registers += (g_audit[index] >> 16) & 0xFFu;
      const CapacityInt multiplicity = g_counts[index];
      if (multiplicity > kMaxLiftsPerState) { ok = false; break; }
      if (lift_total > kUint64Max - multiplicity) { ok = false; break; }
      lift_total += multiplicity;
      g_offsets[index + 1ULL] = lift_total;
    }
  }
  CapacityInt proved_total = 0;
  const bool capacity_ok = ok && invalid_residuals == 0u &&
                           capacity_total(1ULL, lift_total, kCacheCapacity, &proved_total) &&
                           proved_total == lift_total;
  ok = ok && capacity_ok;
  if (ok) ok = cudaMalloc(&device_masks, sizeof(std::uint32_t) * static_cast<std::size_t>(lift_total)) == cudaSuccess;
  ok = ok && cudaMemcpy(device_offsets, g_offsets, sizeof(std::uint64_t) * (kStateCount + 1ULL), cudaMemcpyHostToDevice) == cudaSuccess;
  if (ok) {
    for (std::uint64_t index = 0; index < kStateCount; ++index) g_violations[index] = 0u;
    ok = cudaMemcpy(device_violations, g_violations, sizeof(std::uint32_t) * kStateCount, cudaMemcpyHostToDevice) == cudaSuccess;
  }
  if (ok) G9_CACHE_LAUNCH(fill_kernel, state_grid, dim3(kBlockSize), device_payload, device_offsets,
                          device_masks, device_violations);
  if (ok) G9_CACHE_LAUNCH(range_audit_kernel, state_grid, dim3(kBlockSize), device_offsets, device_masks,
                          device_unsorted, device_duplicates);
  ok = ok && cudaGetLastError() == cudaSuccess && cudaDeviceSynchronize() == cudaSuccess;

  std::uint32_t* host_masks = nullptr;
  if (ok) {
    host_masks = static_cast<std::uint32_t*>(std::malloc(sizeof(std::uint32_t) * static_cast<std::size_t>(lift_total)));
    ok = host_masks != nullptr;
  }
  ok = ok && cudaMemcpy(host_masks, device_masks, sizeof(std::uint32_t) * static_cast<std::size_t>(lift_total), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(g_unsorted, device_unsorted, sizeof(std::uint32_t) * kStateCount, cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(g_duplicates, device_duplicates, sizeof(std::uint32_t) * kStateCount, cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(g_violations, device_violations, sizeof(std::uint32_t) * kStateCount, cudaMemcpyDeviceToHost) == cudaSuccess;

  CapacityInt host_probe_totals[kProbeCount]{};
  std::uint32_t host_probe_accepted[kProbeCount]{};
  ok = ok && cudaMemcpy(host_probe_totals, device_probe_totals, sizeof(host_probe_totals), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(host_probe_accepted, device_probe_accepted, sizeof(host_probe_accepted), cudaMemcpyDeviceToHost) == cudaSuccess;

  if (ok) {
    std::uint64_t unsorted_ranges = 0;
    std::uint64_t duplicate_lifts = 0;
    std::uint64_t range_violations = 0;
    for (std::uint64_t index = 0; index < kStateCount; ++index) {
      unsorted_ranges += g_unsorted[index];
      duplicate_lifts += g_duplicates[index];
      range_violations += g_violations[index];
    }
    Digest membership{kFNVOffsetA, kFNVOffsetB};
    for (std::uint32_t sector = 0; sector < kSectorCount; ++sector) {
      for (std::uint32_t member = 0; member < kSectorSize; ++member) {
        digest_u32(&membership, host_payload.membership[sector][member]);
      }
    }
    Digest cache{kFNVOffsetA, kFNVOffsetB};
    const char tag[] = "G9-FULL-DOMAIN-SLACK-CACHE-V1";
    for (std::uint32_t position = 0; position < sizeof(tag); ++position) {
      digest_byte(&cache, static_cast<std::uint8_t>(tag[position]));
    }
    digest_u32(&cache, kDecodedWidth);
    digest_u32(&cache, kSectorCount);
    digest_u32(&cache, kSectorSlackBits);
    digest_u32(&cache, kBudgetSlackBits);
    digest_u64(&cache, lift_total);
    for (std::uint64_t index = 0; index <= kStateCount; ++index) digest_u64(&cache, g_offsets[index]);
    for (std::uint64_t slot = 0; slot < lift_total; ++slot) digest_u32(&cache, host_masks[slot]);
    Digest probe{kFNVOffsetA, kFNVOffsetB};
    std::uint32_t accepts = 0;
    std::uint32_t rejects = 0;
    for (std::uint32_t index = 0; index < kProbeCount; ++index) {
      digest_byte(&probe, host_probe_accepted[index] != 0u ? 0u : 1u);
      digest_u64(&probe, host_probe_totals[index]);
      if (host_probe_accepted[index] != 0u) accepts += 1u; else rejects += 1u;
    }
    const bool pass = invalid_residuals == 0u && range_violations == 0u && duplicate_lifts == 0u &&
                      unsorted_ranges == 0u && lift_total >= kStateCount && tied_registers > 0u &&
                      exact_registers > 0u;
    std::printf("{\"schema\":\"decisions_os/g9_cuda_full_domain_cache_self_test/v1\",\"device_index\":%d,\"device_name\":\"%s\",\"decoded_width\":%u,\"state_count\":%llu,\"register_count\":%u,\"auxiliary_bits\":%u,\"max_lifts_per_state\":%u,\"cache_capacity\":%llu,\"membership_digest\":\"%016llx\",\"cache_digest\":\"%016llx%016llx\",\"capacity_probe_digest\":\"%016llx\",\"lift_total\":%llu,\"exact_registers\":%llu,\"clamped_registers\":%llu,\"tied_registers\":%llu,\"unsorted_ranges\":%llu,\"duplicate_lifts\":%llu,\"capacity_accepts\":%u,\"capacity_rejects\":%u,\"invalid_residuals\":%u,\"scientific_outputs\":\"intentionally absent\",\"verdict\":\"%s\"}\n",
                selected, property.name, kDecodedWidth, static_cast<unsigned long long>(kStateCount),
                kRegisterCount, kAuxiliaryBits, kMaxLiftsPerState,
                static_cast<unsigned long long>(kCacheCapacity),
                static_cast<unsigned long long>(membership.low),
                static_cast<unsigned long long>(cache.low), static_cast<unsigned long long>(cache.high),
                static_cast<unsigned long long>(probe.low),
                static_cast<unsigned long long>(lift_total),
                static_cast<unsigned long long>(exact_registers),
                static_cast<unsigned long long>(kStateCount * kRegisterCount - exact_registers),
                static_cast<unsigned long long>(tied_registers),
                static_cast<unsigned long long>(unsorted_ranges),
                static_cast<unsigned long long>(duplicate_lifts),
                accepts, rejects, invalid_residuals, pass ? "pass" : "fail");
    ok = ok && pass;
  }
  std::free(host_masks);
  cudaFree(device_payload); cudaFree(device_counts); cudaFree(device_audit); cudaFree(device_offsets);
  cudaFree(device_unsorted); cudaFree(device_duplicates); cudaFree(device_violations); cudaFree(device_masks);
  cudaFree(device_probe_states); cudaFree(device_probe_per_state); cudaFree(device_probe_capacity);
  cudaFree(device_probe_totals); cudaFree(device_probe_accepted);
  return ok;
}

int main(int argc, char** argv) {
  if (argc != 2 || std::strcmp(argv[1], "--self-test") != 0) {
    std::fprintf(stderr, "usage: stage2_cuda_full_domain_cache --self-test\n");
    return 2;
  }
  if (!run_self_test()) {
    std::fprintf(stderr, "FAIL Stage-2 full-domain cache self-test\n");
    return 1;
  }
  return 0;
}
