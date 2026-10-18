// Composed synthetic Stage-2 CUDA self-test — fixed artificial data only.
//
// One fixed 257-state path joining the already-reviewed concepts: canonical
// 20-bit decoded order, explicit sorted non-contiguous sector membership, the
// frozen decoded preparation transcript, the frozen per-register slack
// minimizer policy (tied minimizers retained), both frozen energy transcripts,
// a strict first-seen minimum scan, the frozen D015 tau comparator at
// c_H in {1024, 2048, 4096}, and stable chunked compaction of
// (flags << 32) | canonical_index.
//
// There is no instance reader, ledger reader, output writer or production
// mode.  --self-test prints checksums, counters and device metadata only; it
// never prints or retains an energy, a minimum, a tie index, a label, a rate
// or a record.  The first-seen minimum index and every compacted index exist
// only inside a checksum.
//
// Synthetic control adjustment (narrow, documented, checksum-bound).  Flags
// are derived from real minima through the frozen comparator, but a natural
// near-tie at a fraction of tau cannot be arranged from an arbitrary synthetic
// instance.  So for the six fixed control positions only, the energy is
// replaced by phase_a_minimum + offset with exact binary64 offsets calibrated
// per encoding to yield flags 7, 7, 7, 6, 4 and 0.  The other 251 energies per
// encoding are the unmodified frozen transcript, the phase-A minimum that
// anchors the control is itself a natural energy, and the offsets are bound
// into control_checksum and both energy checksums.
//
// The tied-minimizer branch is not simulated: one synthetic price is
// deliberately non-integer, so some budget residuals are half-integers and the
// frozen rule legitimately retains two minimizers.
//
// Numerical contract: binary64 only; no fp32, FMA, reassociation, atomics,
// shared memory, sorting, fast math, FTZ or libm.  floor is an exact
// truncating cast guarded by an explicit non-finite check.

#include <cuda_runtime.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#pragma STDC FP_CONTRACT OFF

#if defined(__CUDACC__)
#define G9_COMPOSED_LAUNCH(kernel, grid, block, ...) kernel<<<grid, block>>>(__VA_ARGS__)
#else
#define G9_COMPOSED_LAUNCH(kernel, grid, block, ...) g6_host_emulation_launch(kernel, grid, block, __VA_ARGS__)
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
constexpr std::uint32_t kIndexStride = 4073;
constexpr std::uint32_t kChunkSize = 32;
constexpr std::uint32_t kChunkCount = (kStateCount + kChunkSize - 1u) / kChunkSize;
constexpr std::uint32_t kEncodingCount = 2;
constexpr std::uint32_t kCHCount = 3;
constexpr std::uint32_t kControlCount = 6;
constexpr std::uint32_t kBlockSize = 64;
constexpr double kEpsilon = 0x1p-52;
constexpr double kLambdaRef = 0x1p-5;
constexpr std::uint64_t kSentinel = ~0ULL;
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

struct CoefficientData {
  double alpha;
  double sector_slack;
  double budget_slack;
  double sector_linear;
  double sector_quadratic;
  double budget_linear;
  double budget_quadratic;
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
  double slack_squares[kRegisterCount];
  std::uint32_t packed;
  std::uint32_t multiplicity;
  std::uint32_t invalid;
  std::uint32_t nonfinite;
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

// Canonical 20-bit decoded order, identical to src.g5.domains.BinaryDomain.
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

// Frozen preparation transcript with explicit sorted sector membership.
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

// Frozen per-register rule: clamped floor/floor+1, exact binary64 penalties,
// every tied minimizer retained.  Fails closed before the truncating cast.
__host__ __device__ static void register_policy(const double residual, const std::uint32_t maximum,
                                                RegisterPolicy* out) {
  out->count = 0u;
  out->exact = 0u;
  out->invalid = 0u;
  out->values[0] = 0u;
  out->values[1] = 0u;
  out->penalties[0] = +0.0;
  out->penalties[1] = +0.0;
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
  out->exact = (static_cast<double>(lower) == residual && lower >= 0 &&
                lower <= static_cast<long long>(maximum)) ? 1u : 0u;
}

// Frozen 19-bit layout: sector j at offset 2j (two little-endian bits), then
// eleven little-endian budget bits at offset 8.
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

__host__ __device__ static double unbalanced_energy(const double* terms, const CoefficientData* coeff) {
  double h = terms[0];
  h = h + (coeff->alpha * terms[1]);
  for (std::uint32_t sector = 0; sector < kSectorCount; ++sector) {
    const double linear = coeff->sector_linear * terms[2u + sector];
    const double quadratic = coeff->sector_quadratic * terms[2u + kSectorCount + sector];
    h = h + ((-linear) + quadratic);
  }
  const double linear = coeff->budget_linear * terms[2u + 2u * kSectorCount];
  const double quadratic = coeff->budget_quadratic * terms[3u + 2u * kSectorCount];
  return h + ((-linear) + quadratic);
}

__host__ __device__ static double slack_energy(const double* terms, const double* slack_squares,
                                               const CoefficientData* coeff) {
  double h = terms[0];
  h = h + (coeff->alpha * terms[1]);
  for (std::uint32_t sector = 0; sector < kSectorCount; ++sector) {
    h = h + (coeff->sector_slack * slack_squares[sector]);
  }
  return h + (coeff->budget_slack * slack_squares[kSectorCount]);
}

__host__ __device__ static double ch_value(const std::uint32_t index) {
  return index == 0u ? 1024.0 : (index == 1u ? 2048.0 : 4096.0);
}

// FROZEN_MATH_SPEC §5.3 / src.g4.energy.tau in the same binary64 order.
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

__host__ __device__ static std::uint64_t compact_word(const std::uint32_t index, const std::uint32_t flags) {
  return (static_cast<std::uint64_t>(flags) << 32) | static_cast<std::uint64_t>(index);
}

__global__ void prepare_kernel(const InstanceData* instance, const CoefficientData* coefficients,
                               StateOutput* states, double* energies) {
  const std::uint32_t position = blockIdx.x * blockDim.x + threadIdx.x;
  if (position >= kStateCount) return;
  StateOutput local{};
  decoded_terms(instance, canonical_index_to_mask(position * kIndexStride), local.terms);
  double residuals[kRegisterCount];
  for (std::uint32_t sector = 0; sector < kSectorCount; ++sector) residuals[sector] = local.terms[2u + sector];
  residuals[kSectorCount] = local.terms[2u + 2u * kSectorCount];
  local.packed = 0u;
  local.invalid = 0u;
  local.multiplicity = 1u;
  for (std::uint32_t reg = 0; reg < kRegisterCount; ++reg) {
    register_policy(residuals[reg], register_maximum(reg), &local.registers[reg]);
    if (local.registers[reg].invalid != 0u) local.invalid += 1u;
  }
  if (local.invalid == 0u) {
    for (std::uint32_t reg = 0; reg < kRegisterCount; ++reg) {
      local.multiplicity *= local.registers[reg].count;
      local.packed |= local.registers[reg].values[0] << register_offset(reg);
    }
    for (std::uint32_t reg = 0; reg < kRegisterCount; ++reg) {
      const double value = unpack_register_value(local.packed, reg);
      const double delta = residuals[reg] - value;
      local.slack_squares[reg] = delta * delta;
    }
  } else {
    local.multiplicity = 0u;
    for (std::uint32_t reg = 0; reg < kRegisterCount; ++reg) local.slack_squares[reg] = +0.0;
  }
  local.nonfinite = 0u;
  for (std::uint32_t term = 0; term < kTermCount; ++term) {
    if (value_is_nonfinite(local.terms[term])) local.nonfinite += 1u;
  }
  for (std::uint32_t reg = 0; reg < kRegisterCount; ++reg) {
    if (value_is_nonfinite(local.slack_squares[reg])) local.nonfinite += 1u;
  }
  states[position] = local;
  energies[position] = unbalanced_energy(local.terms, coefficients);
  energies[kStateCount + position] = slack_energy(local.terms, local.slack_squares, coefficients);
}

// One deterministic serial thread: phase-A minimum value per encoding.
__global__ void phase_a_kernel(const double* energies, double* phase_a) {
  if (blockIdx.x * blockDim.x + threadIdx.x != 0u) return;
  for (std::uint32_t encoding = 0; encoding < kEncodingCount; ++encoding) {
    const std::uint32_t base = encoding * kStateCount;
    double best = energies[base];
    for (std::uint32_t position = 1; position < kStateCount; ++position) {
      if (energies[base + position] < best) best = energies[base + position];
    }
    phase_a[encoding] = best;
  }
}

// Checksum every natural energy word *before* the control overwrites six of
// them, so a defect confined to a natural energy at a control position cannot
// hide behind the adjustment.  Only the digest leaves the device.
__global__ void natural_checksum_kernel(const double* energies, std::uint64_t* checksums) {
  if (blockIdx.x * blockDim.x + threadIdx.x != 0u) return;
  for (std::uint32_t encoding = 0; encoding < kEncodingCount; ++encoding) {
    std::uint64_t digest = kFNVOffset;
    for (std::uint32_t position = 0; position < kStateCount; ++position) {
      digest = (digest ^ double_to_word(energies[encoding * kStateCount + position])) * kFNVPrime;
    }
    checksums[encoding] = digest;
  }
}

// The documented synthetic control: six fixed positions per encoding become
// phase_a_minimum + a fixed exact offset.  Nothing else is touched.
__global__ void control_kernel(const std::uint32_t* positions, const double* offsets,
                               const double* phase_a, double* energies) {
  if (blockIdx.x * blockDim.x + threadIdx.x != 0u) return;
  for (std::uint32_t encoding = 0; encoding < kEncodingCount; ++encoding) {
    for (std::uint32_t slot = 0; slot < kControlCount; ++slot) {
      const std::uint32_t position = positions[slot];
      energies[encoding * kStateCount + position] = phase_a[encoding] + offsets[encoding * kControlCount + slot];
    }
  }
}

// Strict first-seen minimum: '<' keeps the earliest canonical index.  The same
// scan counts non-finite energies so the self-test fails closed on them rather
// than relying on a checksum difference alone.
__global__ void minimum_kernel(const double* energies, double* minima, std::uint32_t* minimum_indices,
                               std::uint32_t* nonfinite_energies) {
  if (blockIdx.x * blockDim.x + threadIdx.x != 0u) return;
  *nonfinite_energies = 0u;
  for (std::uint32_t encoding = 0; encoding < kEncodingCount; ++encoding) {
    const std::uint32_t base = encoding * kStateCount;
    double best = energies[base];
    std::uint32_t best_index = 0u;
    for (std::uint32_t position = 0; position < kStateCount; ++position) {
      if (value_is_nonfinite(energies[base + position])) *nonfinite_energies += 1u;
    }
    for (std::uint32_t position = 1; position < kStateCount; ++position) {
      if (energies[base + position] < best) {
        best = energies[base + position];
        best_index = position;
      }
    }
    minima[encoding] = best;
    minimum_indices[encoding] = best_index;
  }
}

__global__ void flags_kernel(const double* energies, const double* minima, std::uint32_t* flags) {
  const std::uint32_t position = blockIdx.x * blockDim.x + threadIdx.x;
  if (position >= kStateCount) return;
  for (std::uint32_t encoding = 0; encoding < kEncodingCount; ++encoding) {
    const std::uint32_t slot = encoding * kStateCount + position;
    std::uint32_t value = 0u;
    for (std::uint32_t bit = 0; bit < kCHCount; ++bit) {
      if (frozen_tie(energies[slot], minima[encoding], ch_value(bit))) value |= 1u << bit;
    }
    flags[slot] = value;
  }
}

__global__ void chunk_count_kernel(const std::uint32_t* flags, std::uint32_t* counts) {
  const std::uint32_t chunk = blockIdx.x * blockDim.x + threadIdx.x;
  if (chunk >= kChunkCount) return;
  for (std::uint32_t encoding = 0; encoding < kEncodingCount; ++encoding) {
    const std::uint32_t start = chunk * kChunkSize;
    std::uint32_t span = kChunkSize;
    if (start + span > kStateCount) span = kStateCount - start;
    std::uint32_t total = 0u;
    for (std::uint32_t scan = 0; scan < span; ++scan) {
      if (flags[encoding * kStateCount + start + scan] != 0u) total += 1u;
    }
    counts[encoding * kChunkCount + chunk] = total;
  }
}

// Exclusive prefix in ascending chunk order; no atomics, no scan tree.
__global__ void prefix_kernel(const std::uint32_t* counts, std::uint32_t* offsets) {
  if (blockIdx.x * blockDim.x + threadIdx.x != 0u) return;
  for (std::uint32_t encoding = 0; encoding < kEncodingCount; ++encoding) {
    std::uint32_t running = 0u;
    offsets[encoding * (kChunkCount + 1u)] = 0u;
    for (std::uint32_t prefix_chunk = 0; prefix_chunk < kChunkCount; ++prefix_chunk) {
      running = running + counts[encoding * kChunkCount + prefix_chunk];
      offsets[encoding * (kChunkCount + 1u) + prefix_chunk + 1u] = running;
    }
  }
}

__global__ void compact_kernel(const std::uint32_t* flags, const std::uint32_t* offsets, std::uint64_t* output) {
  const std::uint32_t chunk = blockIdx.x * blockDim.x + threadIdx.x;
  if (chunk >= kChunkCount) return;
  for (std::uint32_t encoding = 0; encoding < kEncodingCount; ++encoding) {
    const std::uint32_t start = chunk * kChunkSize;
    std::uint32_t span = kChunkSize;
    if (start + span > kStateCount) span = kStateCount - start;
    std::uint32_t cursor = offsets[encoding * (kChunkCount + 1u) + chunk];
    for (std::uint32_t local = 0; local < span; ++local) {
      const std::uint32_t position = start + local;
      const std::uint32_t entry_flags = flags[encoding * kStateCount + position];
      if (entry_flags != 0u) {
        output[encoding * kStateCount + cursor] = compact_word(position * kIndexStride, entry_flags);
        cursor = cursor + 1u;
      }
    }
  }
}

__global__ void audit_kernel(const std::uint64_t* output, const std::uint32_t* offsets, std::uint32_t* audit) {
  if (blockIdx.x * blockDim.x + threadIdx.x != 0u) return;
  for (std::uint32_t slot = 0; slot < 4u; ++slot) audit[slot] = 0u;
  for (std::uint32_t encoding = 0; encoding < kEncodingCount; ++encoding) {
    const std::uint32_t total = offsets[encoding * (kChunkCount + 1u) + kChunkCount];
    const std::uint32_t base = encoding * kStateCount;
    bool has_previous = false;
    std::uint32_t previous = 0u;
    for (std::uint32_t slot = 0; slot < total; ++slot) {
      const std::uint64_t word = output[base + slot];
      if (word == kSentinel) {
        audit[2] += 1u;
        continue;
      }
      const std::uint32_t index = static_cast<std::uint32_t>(word & 0xFFFFFFFFULL);
      if (has_previous) {
        if (index == previous) audit[1] += 1u;
        if (index <= previous) audit[0] += 1u;
      }
      previous = index;
      has_previous = true;
    }
    for (std::uint32_t slot = total; slot < kStateCount; ++slot) {
      if (output[base + slot] != kSentinel) audit[3] += 1u;
    }
  }
}

static std::uint64_t fnv_word(const std::uint64_t state, const std::uint64_t word) {
  return (state ^ word) * kFNVPrime;
}

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
  // One deliberately non-integer price makes half-integer budget residuals —
  // and therefore the frozen tied-minimizer branch — reachable.
  value.prices[7] = 2.5;
  value.kappa_risk = 1.0;
  value.k_value = 6.0;
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

static CoefficientData synthetic_coefficients() {
  CoefficientData value{};
  value.alpha = 0x1.0000000000000p-3;
  value.sector_slack = 0x1.0000000000000p-4;
  value.budget_slack = 0x1.8000000000000p-5;
  value.sector_linear = 0x1.4000000000000p-3;
  value.sector_quadratic = 0x1.0000000000000p-5;
  value.budget_linear = 0x1.0000000000000p-4;
  value.budget_quadratic = 0x1.0000000000000p-6;
  return value;
}

static void synthetic_control(std::uint32_t* positions, double* offsets) {
  const std::uint32_t control_positions[kControlCount] = {40u, 41u, 100u, 101u, 200u, 201u};
  const double unbalanced_offsets[kControlCount] = {0x0p+0, 0x0p+0, 0x1p-43, 0x1p-42, 0x1p-41, 0x1p-40};
  const double slack_offsets[kControlCount] = {0x0p+0, 0x0p+0, 0x1p-46, 0x1p-45, 0x1p-44, 0x1p-43};
  for (std::uint32_t slot = 0; slot < kControlCount; ++slot) {
    positions[slot] = control_positions[slot];
    offsets[slot] = unbalanced_offsets[slot];
    offsets[kControlCount + slot] = slack_offsets[slot];
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
  const CoefficientData host_coefficients = synthetic_coefficients();
  std::uint32_t host_control_positions[kControlCount]{};
  double host_control_offsets[kEncodingCount * kControlCount]{};
  synthetic_control(host_control_positions, host_control_offsets);
  std::uint64_t host_output[kEncodingCount * kStateCount]{};
  for (std::uint32_t slot = 0; slot < kEncodingCount * kStateCount; ++slot) host_output[slot] = kSentinel;

  InstanceData* device_instance = nullptr;
  CoefficientData* device_coefficients = nullptr;
  StateOutput* device_states = nullptr;
  double* device_energies = nullptr;
  double* device_phase_a = nullptr;
  double* device_minima = nullptr;
  std::uint32_t* device_minimum_indices = nullptr;
  std::uint32_t* device_nonfinite_energies = nullptr;
  std::uint64_t* device_natural_checksums = nullptr;
  std::uint32_t* device_flags = nullptr;
  std::uint32_t* device_counts = nullptr;
  std::uint32_t* device_offsets = nullptr;
  std::uint64_t* device_output = nullptr;
  std::uint32_t* device_audit = nullptr;
  std::uint32_t* device_control_positions = nullptr;
  double* device_control_offsets = nullptr;
  bool ok = cudaMalloc(&device_instance, sizeof(host_instance)) == cudaSuccess &&
            cudaMalloc(&device_coefficients, sizeof(host_coefficients)) == cudaSuccess &&
            cudaMalloc(&device_states, sizeof(StateOutput) * kStateCount) == cudaSuccess &&
            cudaMalloc(&device_energies, sizeof(double) * kEncodingCount * kStateCount) == cudaSuccess &&
            cudaMalloc(&device_phase_a, sizeof(double) * kEncodingCount) == cudaSuccess &&
            cudaMalloc(&device_minima, sizeof(double) * kEncodingCount) == cudaSuccess &&
            cudaMalloc(&device_minimum_indices, sizeof(std::uint32_t) * kEncodingCount) == cudaSuccess &&
            cudaMalloc(&device_nonfinite_energies, sizeof(std::uint32_t)) == cudaSuccess &&
            cudaMalloc(&device_natural_checksums, sizeof(std::uint64_t) * kEncodingCount) == cudaSuccess &&
            cudaMalloc(&device_flags, sizeof(std::uint32_t) * kEncodingCount * kStateCount) == cudaSuccess &&
            cudaMalloc(&device_counts, sizeof(std::uint32_t) * kEncodingCount * kChunkCount) == cudaSuccess &&
            cudaMalloc(&device_offsets, sizeof(std::uint32_t) * kEncodingCount * (kChunkCount + 1u)) == cudaSuccess &&
            cudaMalloc(&device_output, sizeof(host_output)) == cudaSuccess &&
            cudaMalloc(&device_audit, sizeof(std::uint32_t) * 4u) == cudaSuccess &&
            cudaMalloc(&device_control_positions, sizeof(host_control_positions)) == cudaSuccess &&
            cudaMalloc(&device_control_offsets, sizeof(host_control_offsets)) == cudaSuccess;
  ok = ok && cudaMemcpy(device_instance, &host_instance, sizeof(host_instance), cudaMemcpyHostToDevice) == cudaSuccess &&
       cudaMemcpy(device_coefficients, &host_coefficients, sizeof(host_coefficients), cudaMemcpyHostToDevice) == cudaSuccess &&
       cudaMemcpy(device_output, host_output, sizeof(host_output), cudaMemcpyHostToDevice) == cudaSuccess &&
       cudaMemcpy(device_control_positions, host_control_positions, sizeof(host_control_positions), cudaMemcpyHostToDevice) == cudaSuccess &&
       cudaMemcpy(device_control_offsets, host_control_offsets, sizeof(host_control_offsets), cudaMemcpyHostToDevice) == cudaSuccess;
  const dim3 state_grid((kStateCount + kBlockSize - 1u) / kBlockSize);
  const dim3 chunk_grid((kChunkCount + kBlockSize - 1u) / kBlockSize);
  if (ok) G9_COMPOSED_LAUNCH(prepare_kernel, state_grid, dim3(kBlockSize), device_instance, device_coefficients,
                             device_states, device_energies);
  if (ok) G9_COMPOSED_LAUNCH(natural_checksum_kernel, dim3(1), dim3(1), device_energies, device_natural_checksums);
  if (ok) G9_COMPOSED_LAUNCH(phase_a_kernel, dim3(1), dim3(1), device_energies, device_phase_a);
  if (ok) G9_COMPOSED_LAUNCH(control_kernel, dim3(1), dim3(1), device_control_positions, device_control_offsets,
                             device_phase_a, device_energies);
  if (ok) G9_COMPOSED_LAUNCH(minimum_kernel, dim3(1), dim3(1), device_energies, device_minima, device_minimum_indices,
                             device_nonfinite_energies);
  if (ok) G9_COMPOSED_LAUNCH(flags_kernel, state_grid, dim3(kBlockSize), device_energies, device_minima, device_flags);
  if (ok) G9_COMPOSED_LAUNCH(chunk_count_kernel, chunk_grid, dim3(kBlockSize), device_flags, device_counts);
  if (ok) G9_COMPOSED_LAUNCH(prefix_kernel, dim3(1), dim3(1), device_counts, device_offsets);
  if (ok) G9_COMPOSED_LAUNCH(compact_kernel, chunk_grid, dim3(kBlockSize), device_flags, device_offsets, device_output);
  if (ok) G9_COMPOSED_LAUNCH(audit_kernel, dim3(1), dim3(1), device_output, device_offsets, device_audit);
  ok = ok && cudaGetLastError() == cudaSuccess && cudaDeviceSynchronize() == cudaSuccess;

  StateOutput host_states[kStateCount]{};
  double host_energies[kEncodingCount * kStateCount]{};
  double host_minima[kEncodingCount]{};
  std::uint32_t host_minimum_indices[kEncodingCount]{};
  std::uint32_t host_flags[kEncodingCount * kStateCount]{};
  std::uint32_t host_counts[kEncodingCount * kChunkCount]{};
  std::uint32_t host_offsets[kEncodingCount * (kChunkCount + 1u)]{};
  std::uint32_t host_audit[4]{};
  std::uint32_t host_nonfinite_energies = 0;
  std::uint64_t host_natural_checksums[kEncodingCount]{};
  ok = ok && cudaMemcpy(host_states, device_states, sizeof(host_states), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(host_energies, device_energies, sizeof(host_energies), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(host_minima, device_minima, sizeof(host_minima), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(host_minimum_indices, device_minimum_indices, sizeof(host_minimum_indices), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(host_flags, device_flags, sizeof(host_flags), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(host_counts, device_counts, sizeof(host_counts), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(host_offsets, device_offsets, sizeof(host_offsets), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(host_output, device_output, sizeof(host_output), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(host_audit, device_audit, sizeof(host_audit), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(&host_nonfinite_energies, device_nonfinite_energies, sizeof(host_nonfinite_energies), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(host_natural_checksums, device_natural_checksums, sizeof(host_natural_checksums), cudaMemcpyDeviceToHost) == cudaSuccess;

  std::uint64_t membership_checksum = kFNVOffset;
  std::uint64_t domain_checksum = kFNVOffset;
  std::uint64_t terms_checksum = kFNVOffset;
  std::uint64_t lift_checksum = kFNVOffset;
  std::uint64_t control_checksum = kFNVOffset;
  std::uint64_t energy_checksum[kEncodingCount] = {kFNVOffset, kFNVOffset};
  std::uint64_t minimum_checksum[kEncodingCount] = {kFNVOffset, kFNVOffset};
  std::uint64_t flags_checksum[kEncodingCount] = {kFNVOffset, kFNVOffset};
  std::uint64_t offsets_checksum[kEncodingCount] = {kFNVOffset, kFNVOffset};
  std::uint64_t compacted_checksum[kEncodingCount] = {kFNVOffset, kFNVOffset};
  std::uint32_t per_ch[kEncodingCount][kCHCount] = {{0u, 0u, 0u}, {0u, 0u, 0u}};
  std::uint32_t exact_registers = 0, clamped_registers = 0, tied_registers = 0;
  std::uint32_t invalid_registers = 0, nonfinite_terms = 0;
  std::uint64_t multiplicity_total = 0;
  std::uint32_t illegal_flag_entries = 0, nesting_violations = 0;
  if (ok) {
    for (std::uint32_t sector = 0; sector < kSectorCount; ++sector) {
      for (std::uint32_t member = 0; member < kSectorSize; ++member) {
        membership_checksum = fnv_word(membership_checksum, host_instance.membership[sector][member]);
      }
    }
    for (std::uint32_t position = 0; position < kStateCount; ++position) {
      const StateOutput* row = &host_states[position];
      domain_checksum = fnv_word(domain_checksum, position * kIndexStride);
      for (std::uint32_t term = 0; term < kTermCount; ++term) {
        terms_checksum = fnv_word(terms_checksum, double_to_word(row->terms[term]));
      }
      for (std::uint32_t reg = 0; reg < kRegisterCount; ++reg) {
        const RegisterPolicy* policy = &row->registers[reg];
        lift_checksum = fnv_word(lift_checksum, policy->count);
        lift_checksum = fnv_word(lift_checksum, policy->exact);
        for (std::uint32_t index = 0; index < policy->count; ++index) {
          lift_checksum = fnv_word(lift_checksum, policy->values[index]);
          lift_checksum = fnv_word(lift_checksum, double_to_word(policy->penalties[index]));
        }
        if (policy->exact != 0u) exact_registers += 1u; else clamped_registers += 1u;
        if (policy->count > 1u) tied_registers += 1u;
        if (policy->invalid != 0u) invalid_registers += 1u;
      }
      lift_checksum = fnv_word(lift_checksum, row->packed);
      for (std::uint32_t reg = 0; reg < kRegisterCount; ++reg) {
        lift_checksum = fnv_word(lift_checksum, double_to_word(row->slack_squares[reg]));
      }
      multiplicity_total += row->multiplicity;
      nonfinite_terms += row->nonfinite;
    }
    for (std::uint32_t encoding = 0; encoding < kEncodingCount; ++encoding) {
      for (std::uint32_t slot = 0; slot < kControlCount; ++slot) {
        control_checksum = fnv_word(control_checksum, host_control_positions[slot]);
        control_checksum = fnv_word(control_checksum, double_to_word(host_control_offsets[encoding * kControlCount + slot]));
      }
    }
    for (std::uint32_t encoding = 0; encoding < kEncodingCount; ++encoding) {
      const std::uint32_t base = encoding * kStateCount;
      for (std::uint32_t position = 0; position < kStateCount; ++position) {
        energy_checksum[encoding] = fnv_word(energy_checksum[encoding], double_to_word(host_energies[base + position]));
        const std::uint32_t value = host_flags[base + position];
        flags_checksum[encoding] = fnv_word(flags_checksum[encoding], value);
        if (!(value == 0u || value == 4u || value == 6u || value == 7u)) illegal_flag_entries += 1u;
        const bool tied_1024 = (value & 1u) != 0u;
        const bool tied_2048 = (value & 2u) != 0u;
        const bool tied_4096 = (value & 4u) != 0u;
        if ((tied_1024 && !tied_2048) || (tied_2048 && !tied_4096)) nesting_violations += 1u;
        for (std::uint32_t bit = 0; bit < kCHCount; ++bit) {
          if ((value & (1u << bit)) != 0u) per_ch[encoding][bit] += 1u;
        }
      }
      // The first-seen minimum index is bound into a checksum, never printed.
      minimum_checksum[encoding] = fnv_word(minimum_checksum[encoding], double_to_word(host_minima[encoding]));
      minimum_checksum[encoding] = fnv_word(minimum_checksum[encoding], host_minimum_indices[encoding]);
      for (std::uint32_t chunk = 0; chunk < kChunkCount; ++chunk) {
        offsets_checksum[encoding] = fnv_word(offsets_checksum[encoding], host_counts[encoding * kChunkCount + chunk]);
      }
      for (std::uint32_t chunk = 0; chunk <= kChunkCount; ++chunk) {
        offsets_checksum[encoding] = fnv_word(offsets_checksum[encoding], host_offsets[encoding * (kChunkCount + 1u) + chunk]);
      }
      const std::uint32_t total = host_offsets[encoding * (kChunkCount + 1u) + kChunkCount];
      for (std::uint32_t slot = 0; slot < total; ++slot) {
        compacted_checksum[encoding] = fnv_word(compacted_checksum[encoding], host_output[base + slot]);
      }
    }
    const std::uint32_t total_unbalanced = host_offsets[kChunkCount];
    const std::uint32_t total_slack = host_offsets[(kChunkCount + 1u) + kChunkCount];
    const bool pass = nonfinite_terms == 0u && host_nonfinite_energies == 0u && invalid_registers == 0u && illegal_flag_entries == 0u &&
                      nesting_violations == 0u && host_audit[0] == 0u && host_audit[1] == 0u &&
                      host_audit[2] == 0u && host_audit[3] == 0u &&
                      per_ch[0][0] <= per_ch[0][1] && per_ch[0][1] <= per_ch[0][2] &&
                      per_ch[1][0] <= per_ch[1][1] && per_ch[1][1] <= per_ch[1][2] &&
                      per_ch[0][2] == total_unbalanced && per_ch[1][2] == total_slack;
    std::printf("{\"schema\":\"decisions_os/g9_cuda_composed_self_test/v1\",\"device_index\":%d,\"device_name\":\"%s\",\"state_count\":%u,\"chunk_size\":%u,\"chunk_count\":%u,\"register_count\":%u,\"auxiliary_bits\":%u,\"membership_checksum\":\"%016llx\",\"domain_checksum\":\"%016llx\",\"terms_checksum\":\"%016llx\",\"lift_policy_checksum\":\"%016llx\",\"control_checksum\":\"%016llx\",\"exact_registers\":%u,\"clamped_registers\":%u,\"tied_registers\":%u,\"lift_multiplicity_total\":%llu,\"nonfinite_terms\":%u,\"nonfinite_energies\":%u,\"invalid_registers\":%u,\"scientific_outputs\":\"intentionally absent\",\"natural_energy_checksum_unbalanced\":\"%016llx\",\"controlled_energy_checksum_unbalanced\":\"%016llx\",\"minimum_checksum_unbalanced\":\"%016llx\",\"flags_checksum_unbalanced\":\"%016llx\",\"offsets_checksum_unbalanced\":\"%016llx\",\"compacted_checksum_unbalanced\":\"%016llx\",\"compacted_total_unbalanced\":%u,\"count_c_h_1024_unbalanced\":%u,\"count_c_h_2048_unbalanced\":%u,\"count_c_h_4096_unbalanced\":%u,\"natural_energy_checksum_slack\":\"%016llx\",\"controlled_energy_checksum_slack\":\"%016llx\",\"minimum_checksum_slack\":\"%016llx\",\"flags_checksum_slack\":\"%016llx\",\"offsets_checksum_slack\":\"%016llx\",\"compacted_checksum_slack\":\"%016llx\",\"compacted_total_slack\":%u,\"count_c_h_1024_slack\":%u,\"count_c_h_2048_slack\":%u,\"count_c_h_4096_slack\":%u,\"order_violations\":%u,\"duplicate_entries\":%u,\"unwritten_slots\":%u,\"sentinel_violations\":%u,\"illegal_flag_entries\":%u,\"nesting_violations\":%u,\"verdict\":\"%s\"}\n",
                selected, property.name, kStateCount, kChunkSize, kChunkCount, kRegisterCount, kAuxiliaryBits,
                static_cast<unsigned long long>(membership_checksum),
                static_cast<unsigned long long>(domain_checksum),
                static_cast<unsigned long long>(terms_checksum),
                static_cast<unsigned long long>(lift_checksum),
                static_cast<unsigned long long>(control_checksum),
                exact_registers, clamped_registers, tied_registers,
                static_cast<unsigned long long>(multiplicity_total), nonfinite_terms, host_nonfinite_energies, invalid_registers,
                static_cast<unsigned long long>(host_natural_checksums[0]),
                static_cast<unsigned long long>(energy_checksum[0]),
                static_cast<unsigned long long>(minimum_checksum[0]),
                static_cast<unsigned long long>(flags_checksum[0]),
                static_cast<unsigned long long>(offsets_checksum[0]),
                static_cast<unsigned long long>(compacted_checksum[0]),
                total_unbalanced, per_ch[0][0], per_ch[0][1], per_ch[0][2],
                static_cast<unsigned long long>(host_natural_checksums[1]),
                static_cast<unsigned long long>(energy_checksum[1]),
                static_cast<unsigned long long>(minimum_checksum[1]),
                static_cast<unsigned long long>(flags_checksum[1]),
                static_cast<unsigned long long>(offsets_checksum[1]),
                static_cast<unsigned long long>(compacted_checksum[1]),
                total_slack, per_ch[1][0], per_ch[1][1], per_ch[1][2],
                host_audit[0], host_audit[1], host_audit[2], host_audit[3],
                illegal_flag_entries, nesting_violations, pass ? "pass" : "fail");
    ok = ok && pass;
  }
  cudaFree(device_instance); cudaFree(device_coefficients); cudaFree(device_states);
  cudaFree(device_energies); cudaFree(device_phase_a); cudaFree(device_minima);
  cudaFree(device_minimum_indices); cudaFree(device_flags); cudaFree(device_counts);
  cudaFree(device_offsets); cudaFree(device_output); cudaFree(device_audit);
  cudaFree(device_control_positions); cudaFree(device_control_offsets); cudaFree(device_nonfinite_energies);
  cudaFree(device_natural_checksums);
  return ok;
}

int main(int argc, char** argv) {
  if (argc != 2 || std::strcmp(argv[1], "--self-test") != 0) {
    std::fprintf(stderr, "usage: stage2_cuda_composed_selftest --self-test\n");
    return 2;
  }
  if (!run_self_test()) {
    std::fprintf(stderr, "FAIL Stage-2 composed self-test\n");
    return 1;
  }
  return 0;
}
