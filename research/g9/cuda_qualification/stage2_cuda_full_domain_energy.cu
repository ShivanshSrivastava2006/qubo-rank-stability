// Synthetic full-domain energy / strict-minimum / D015-flag self-test.
//
// Independent of every other Stage-2 CUDA component.  For a fixed synthetic
// 20-asset payload with an explicit non-contiguous 4x5 membership it scans the
// WHOLE canonical decoded domain (2^20 unbalanced states) and the COMPLETE
// active-CSB slack lift cache, at two fixed synthetic coefficient rows,
// computing both encodings' energies, deterministic strict-first-seen minima,
// and frozen D015 flags at c_H in {1024, 2048, 4096}.
//
// There is no instance reader, ledger reader, output writer or production
// mode.  --self-test prints synthetic checksums, integer counters, fixed
// identity metadata and a verdict only — never an energy, a minimum, an index,
// a tie list, a label, a rate or a record.
//
// Pre-nvcc numerical compile contract.  Any future integrated CUDA runner MUST
// build this translation unit with:
//   nvcc --fmad=false --ftz=false --prec-div=true --prec-sqrt=true
// and the host emulation build MUST use:
//   g++ -ffp-contract=off -fno-fast-math
// Contracted flags: --fmad=false --ftz=false --prec-div=true --prec-sqrt=true
// Every one of them is required for the frozen binary64 transcripts to be
// reproduced exactly: contraction, flush-to-zero, or fast division/sqrt would
// each silently change a reported word.  This declaration is
// NOT a claim of real CUDA numerical qualification: nothing in this component
// invokes nvcc, and that qualification remains future work for the integrated
// runner.
//
// Frozen rules reproduced here, not invented:
//   * canonical decoded order x[i] = (index >> (19 - i)) & 1;
//   * the residual transcript, the clamped floor/floor+1 minimizer rule with
//     EVERY tied minimizer retained, the frozen 19-bit register layout and the
//     frozen Cartesian-product lift order (sector 0 slowest, budget fastest),
//     with uint64 offsets and a capacity proof;
//   * the prepared-energy transcripts: objective first, then alpha*card_square,
//     then each sector family, then the budget family, accumulators from +0.0;
//   * D015: gap = abs(fl(y - y_min)); scale = fl(lambda_ref + max(abs(y),
//     abs(y_min))); tau = fl((c_H * eps) * scale); tie iff gap <= tau.
//
// Two optimisations are exact, not approximations.  Objective terms whose x
// factor is zero are skipped: each is +-0.0 and the accumulator starts at
// +0.0, so they cannot change the value.  Flags short-circuit on the loosest
// threshold: c_H is a power of two and eps = 2^-52, so c_H*eps is exact and
// tau is exactly monotone in c_H.
//
// Synthetic control adjustment (declared, checksum-bound).  The natural
// landscape has unique minima and no near-ties, so a small fixed set of
// control positions per (row, encoding) takes the value natural_minimum +
// offset.  Offsets are non-negative, so the controlled minimum VALUE is the
// natural minimum; only the first-seen winner and the flag population change.
// A natural pre-control checksum over every full-domain word is retained
// beside the controlled checksum, so a natural-energy defect cannot hide
// behind a control.
//
// Numerical contract: binary64 only; no fp32, FMA, reassociation, fast math,
// FTZ, atomics, shared-memory reductions, sorting, libm, or nondeterministic
// minimum selection.  Coefficient words are fixed host-validated inputs; the
// device never derives a coefficient map.

#include <cuda_runtime.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#pragma STDC FP_CONTRACT OFF

#if defined(__CUDACC__)
#define G9_ENERGY_LAUNCH(kernel, grid, block, ...) kernel<<<grid, block>>>(__VA_ARGS__)
#else
#define G9_ENERGY_LAUNCH(kernel, grid, block, ...) g6_host_emulation_launch(kernel, grid, block, __VA_ARGS__)
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
constexpr std::uint32_t kSegmentSize = 1024;
constexpr std::uint32_t kMaxLiftsPerState = 1u << kRegisterCount;
constexpr std::uint64_t kCacheCapacity = kStateCount * static_cast<std::uint64_t>(kMaxLiftsPerState);
constexpr std::uint32_t kRowCount = 2;
constexpr std::uint32_t kEncodingCount = 2;
constexpr std::uint32_t kCHCount = 3;
constexpr std::uint32_t kControlCount = 7;
constexpr std::uint32_t kBlockSize = 64;
constexpr double kEpsilon = 0x1p-52;
constexpr double kLambdaRef = 0x1p-5;
constexpr std::uint64_t kFNVOffset = 1469598103934665603ULL;
constexpr std::uint64_t kFNVPrime = 1099511628211ULL;
constexpr std::uint64_t kUint64Max = ~0ULL;

struct PayloadData {
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

__host__ __device__ static std::uint64_t double_to_word(const double value) {
  std::uint64_t word = 0;
#if defined(__CUDA_ARCH__)
  word = static_cast<std::uint64_t>(__double_as_longlong(value));
#else
  std::memcpy(&word, &value, sizeof(word));
#endif
  return word;
}

__host__ __device__ static bool value_is_nonfinite(const double value) {
  return ((double_to_word(value) >> 52) & 0x7ffULL) == 0x7ffULL;
}

__host__ __device__ static bool decoded_selected(const std::uint32_t index, const std::uint32_t asset) {
  return ((index >> (kDecodedWidth - 1u - asset)) & 1u) != 0u;
}

__host__ __device__ static std::uint32_t register_maximum(const std::uint32_t reg) {
  const std::uint32_t bits = reg < kSectorCount ? kSectorSlackBits : kBudgetSlackBits;
  return (1u << bits) - 1u;
}

__host__ __device__ static std::uint32_t register_offset(const std::uint32_t reg) {
  return reg < kSectorCount ? (reg * kSectorSlackBits) : (kSectorCount * kSectorSlackBits);
}

// Frozen objective, skipping the provably neutral zero terms.
__host__ __device__ static double objective_of(const PayloadData* payload, const std::uint32_t index) {
  double accumulator = +0.0;
  for (std::uint32_t asset = 0; asset < kAssetCount; ++asset) {
    if (decoded_selected(index, asset)) accumulator = accumulator + (-(payload->mu[asset] * 1.0));
  }
  for (std::uint32_t row = 0; row < kAssetCount; ++row) {
    if (!decoded_selected(index, row)) continue;
    for (std::uint32_t column = 0; column < kAssetCount; ++column) {
      if (!decoded_selected(index, column)) continue;
      const double sigma_x = payload->sigma[row * kAssetCount + column] * 1.0;
      accumulator = accumulator + (payload->kappa_risk * (sigma_x * 1.0));
    }
  }
  return accumulator;
}

__host__ __device__ static double card_square_of(const PayloadData* payload, const std::uint32_t index) {
  double cardinality = +0.0;
  for (std::uint32_t asset = 0; asset < kAssetCount; ++asset) {
    cardinality = cardinality + (decoded_selected(index, asset) ? 1.0 : 0.0);
  }
  const double h = cardinality - payload->k_value;
  return h * h;
}

__host__ __device__ static void residuals_of(const PayloadData* payload, const std::uint32_t index,
                                             double* sector, double* budget) {
  for (std::uint32_t s = 0; s < kSectorCount; ++s) {
    double total = +0.0;
    for (std::uint32_t member = 0; member < kSectorSize; ++member) {
      const std::uint32_t asset = payload->membership[s][member];
      total = total + (decoded_selected(index, asset) ? 1.0 : 0.0);
    }
    sector[s] = payload->c_value - total;
  }
  double spend = +0.0;
  for (std::uint32_t asset = 0; asset < kAssetCount; ++asset) {
    spend = spend + (payload->prices[asset] * (decoded_selected(index, asset) ? 1.0 : 0.0));
  }
  *budget = payload->b - spend;
}

__host__ __device__ static long long floor_double(const double value) {
  long long lower = static_cast<long long>(value);
  if (static_cast<double>(lower) > value) lower -= 1;
  return lower;
}

// Frozen per-register rule with both fail-closed guards; 0 means invalid.
__host__ __device__ static std::uint32_t register_minimizers(const double residual, const std::uint32_t maximum,
                                                             std::uint32_t* values, double* penalties) {
  values[0] = 0u; values[1] = 0u;
  penalties[0] = +0.0; penalties[1] = +0.0;
  if (value_is_nonfinite(residual)) return 0u;
  std::uint32_t low = 0u, high = 0u;
  if (residual < 0.0) {
    low = 0u; high = 0u;
  } else if (residual >= static_cast<double>(maximum)) {
    low = maximum; high = maximum;
  } else {
    const long long lower = floor_double(residual);
    std::uint32_t first = lower < 0 ? 0u : (lower > static_cast<long long>(maximum) ? maximum : static_cast<std::uint32_t>(lower));
    const long long next = lower + 1;
    std::uint32_t second = next < 0 ? 0u : (next > static_cast<long long>(maximum) ? maximum : static_cast<std::uint32_t>(next));
    low = first < second ? first : second;
    high = first < second ? second : first;
  }
  const double delta_low = residual - static_cast<double>(low);
  const double delta_high = residual - static_cast<double>(high);
  const double penalty_low = delta_low * delta_low;
  const double penalty_high = delta_high * delta_high;
  if (value_is_nonfinite(penalty_low) || value_is_nonfinite(penalty_high)) return 0u;
  if (low == high) { values[0] = low; penalties[0] = penalty_low; return 1u; }
  if (penalty_low < penalty_high) { values[0] = low; penalties[0] = penalty_low; return 1u; }
  if (penalty_high < penalty_low) { values[0] = high; penalties[0] = penalty_high; return 1u; }
  values[0] = low; penalties[0] = penalty_low;
  values[1] = high; penalties[1] = penalty_high;
  return 2u;
}

// FROZEN_MATH_SPEC 5.3 order, with the exactly monotone short-circuit.
__host__ __device__ static std::uint32_t tie_flags(const double y, const double y_min) {
  const double difference = y - y_min;
  const double gap = difference < 0.0 ? -difference : difference;
  const double y_magnitude = y < 0.0 ? -y : y;
  const double min_magnitude = y_min < 0.0 ? -y_min : y_min;
  const double maximum = y_magnitude > min_magnitude ? y_magnitude : min_magnitude;
  const double scale = kLambdaRef + maximum;
  if (gap > (4096.0 * kEpsilon) * scale) return 0u;
  std::uint32_t flags = 0u;
  if (gap <= (1024.0 * kEpsilon) * scale) flags |= 1u;
  if (gap <= (2048.0 * kEpsilon) * scale) flags |= 2u;
  if (gap <= (4096.0 * kEpsilon) * scale) flags |= 4u;
  return flags;
}

__global__ void terms_kernel(const PayloadData* payload, double* objective, double* card_square,
                             std::uint32_t* lift_counts, std::uint32_t* invalid) {
  const std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index >= kStateCount) return;
  objective[index] = objective_of(payload, index);
  card_square[index] = card_square_of(payload, index);
  double sector[kSectorCount], budget;
  residuals_of(payload, index, sector, &budget);
  std::uint32_t multiplicity = 1u;
  std::uint32_t bad = 0u;
  for (std::uint32_t s = 0; s < kSectorCount; ++s) {
    std::uint32_t values[2]; double penalties[2];
    const std::uint32_t count = register_minimizers(sector[s], register_maximum(s), values, penalties);
    if (count == 0u) bad = 1u; else multiplicity *= count;
  }
  std::uint32_t values[2]; double penalties[2];
  const std::uint32_t count = register_minimizers(budget, register_maximum(kSectorCount), values, penalties);
  if (count == 0u) bad = 1u; else multiplicity *= count;
  invalid[index] = bad;
  lift_counts[index] = (bad != 0u || multiplicity > kMaxLiftsPerState) ? 0u : multiplicity;
}

// One thread per decoded state writes that state's energies: for slack it
// fills its own disjoint [offsets[i], offsets[i+1]) range in frozen product
// order, so no atomics and no scheduling assumption are needed.
__global__ void energy_kernel(const PayloadData* payload, const CoefficientData* coefficients,
                              const double* objective, const double* card_square,
                              const std::uint64_t* offsets, const std::uint32_t encoding,
                              double* energies) {
  const std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index >= kStateCount) return;
  double sector[kSectorCount], budget;
  residuals_of(payload, index, sector, &budget);
  double base = objective[index];
  base = base + (coefficients->alpha * card_square[index]);
  if (encoding == 0u) {
    double h = base;
    for (std::uint32_t s = 0; s < kSectorCount; ++s) {
      const double linear = coefficients->sector_linear * sector[s];
      const double quadratic = coefficients->sector_quadratic * (sector[s] * sector[s]);
      h = h + ((-linear) + quadratic);
    }
    const double linear = coefficients->budget_linear * budget;
    const double quadratic = coefficients->budget_quadratic * (budget * budget);
    energies[index] = h + ((-linear) + quadratic);
    return;
  }
  double h = base;
  for (std::uint32_t s = 0; s < kSectorCount; ++s) {
    std::uint32_t values[2]; double penalties[2];
    register_minimizers(sector[s], register_maximum(s), values, penalties);
    h = h + (coefficients->sector_slack * penalties[0]);
  }
  std::uint32_t values[2]; double penalties[2];
  const std::uint32_t count = register_minimizers(budget, register_maximum(kSectorCount), values, penalties);
  std::uint64_t cursor = offsets[index];
  for (std::uint32_t lift = 0; lift < count; ++lift) {
    energies[cursor] = h + (coefficients->budget_slack * penalties[lift]);
    cursor = cursor + 1u;
  }
}

// Deterministic contiguous segments: one thread per segment, strict '<', so
// the earliest position inside a segment wins an exact tie.
__global__ void segment_kernel(const double* energies, const std::uint64_t word_count,
                               const std::uint32_t segment_count, double* segment_value,
                               std::uint64_t* segment_index, std::uint32_t* nonfinite) {
  const std::uint32_t segment = blockIdx.x * blockDim.x + threadIdx.x;
  if (segment >= segment_count) return;
  const std::uint64_t start = static_cast<std::uint64_t>(segment) * kSegmentSize;
  std::uint64_t stop = start + kSegmentSize;
  if (stop > word_count) stop = word_count;
  std::uint32_t bad = 0u;
  double best = 0.0;
  std::uint64_t best_index = start;
  bool have = false;
  for (std::uint64_t position = start; position < stop; ++position) {
    const double value = energies[position];
    if (value_is_nonfinite(value)) { bad += 1u; continue; }
    if (!have || value < best) { best = value; best_index = position; have = true; }
  }
  segment_value[segment] = have ? best : 0.0;
  segment_index[segment] = have ? best_index : kUint64Max;
  nonfinite[segment] = bad;
}

__global__ void flags_kernel(const double* energies, const std::uint64_t word_count,
                             const double minimum, const std::uint32_t segment_count,
                             std::uint64_t* per_ch, std::uint32_t* illegal, std::uint32_t* nesting) {
  const std::uint32_t segment = blockIdx.x * blockDim.x + threadIdx.x;
  if (segment >= segment_count) return;
  const std::uint64_t start = static_cast<std::uint64_t>(segment) * kSegmentSize;
  std::uint64_t stop = start + kSegmentSize;
  if (stop > word_count) stop = word_count;
  std::uint64_t counts[kCHCount] = {0ULL, 0ULL, 0ULL};
  std::uint32_t bad_legal = 0u, bad_nest = 0u;
  for (std::uint64_t position = start; position < stop; ++position) {
    const std::uint32_t flags = tie_flags(energies[position], minimum);
    if (!(flags == 0u || flags == 4u || flags == 6u || flags == 7u)) bad_legal += 1u;
    const bool t1 = (flags & 1u) != 0u, t2 = (flags & 2u) != 0u, t4 = (flags & 4u) != 0u;
    if ((t1 && !t2) || (t2 && !t4)) bad_nest += 1u;
    for (std::uint32_t bit = 0; bit < kCHCount; ++bit) {
      if ((flags & (1u << bit)) != 0u) counts[bit] += 1ULL;
    }
  }
  for (std::uint32_t bit = 0; bit < kCHCount; ++bit) per_ch[segment * kCHCount + bit] = counts[bit];
  illegal[segment] = bad_legal;
  nesting[segment] = bad_nest;
}

static std::uint64_t fnv_step(const std::uint64_t state, const std::uint64_t word) {
  return (state ^ word) * kFNVPrime;
}

static PayloadData synthetic_payload() {
  PayloadData value{};
  for (std::uint32_t asset = 0; asset < kAssetCount; ++asset) {
    value.mu[asset] = (static_cast<double>(asset) - 9.0) / 1000.0;
    value.prices[asset] = static_cast<double>(1u + (asset % 5u));
    for (std::uint32_t other = 0; other < kAssetCount; ++other) {
      value.sigma[asset * kAssetCount + other] =
          asset == other ? (0.01 + static_cast<double>(asset) / 10000.0)
                         : static_cast<double>((asset + other) % 7u) / 100000.0;
    }
  }
  value.prices[7] = 2.5;
  value.kappa_risk = 1.0;
  value.k_value = 6.0;
  value.c_value = 2.0;
  value.b = 40.0;
  const std::uint32_t blocks[kSectorCount][kSectorSize] = {
      {0u, 6u, 11u, 15u, 19u}, {1u, 5u, 10u, 14u, 18u}, {2u, 7u, 9u, 13u, 17u}, {3u, 4u, 8u, 12u, 16u}};
  for (std::uint32_t s = 0; s < kSectorCount; ++s) {
    for (std::uint32_t m = 0; m < kSectorSize; ++m) value.membership[s][m] = blocks[s][m];
  }
  return value;
}

static CoefficientData synthetic_row(const std::uint32_t row) {
  CoefficientData value{};
  if (row == 0u) {
    value.alpha = 0x1p-3; value.sector_slack = 0x1p-4; value.budget_slack = 0x1.8p-5;
    value.sector_linear = 0x1.4p-3; value.sector_quadratic = 0x1p-5;
    value.budget_linear = 0x1p-4; value.budget_quadratic = 0x1p-6;
  } else {
    value.alpha = 0x1p-5; value.sector_slack = 0x1p+2; value.budget_slack = 0x1p+1;
    value.sector_linear = 0x1p-1; value.sector_quadratic = 0x1p-2;
    value.budget_linear = 0x1.8p-1; value.budget_quadratic = 0x1p-3;
  }
  return value;
}

static void synthetic_control(std::uint32_t* positions, double* offsets) {
  // 40 and 41 tie inside segment 0; 1064 ties from segment 1, so the
  // fixed-order ascending merge and its strict '<' are both load-bearing.
  const std::uint32_t control_positions[kControlCount] = {40u, 41u, 1064u, 100u, 101u, 200u, 201u};
  // [row][encoding][slot]
  const double table[kRowCount][kEncodingCount][kControlCount] = {
      {{0x0p+0, 0x0p+0, 0x0p+0, 0x1p-43, 0x1p-42, 0x1p-41, 0x1p-40},
       {0x0p+0, 0x0p+0, 0x0p+0, 0x1p-47, 0x1p-46, 0x1p-45, 0x1p-44}},
      {{0x0p+0, 0x0p+0, 0x0p+0, 0x1p-44, 0x1p-43, 0x1p-42, 0x1p-41},
       {0x0p+0, 0x0p+0, 0x0p+0, 0x1p-47, 0x1p-46, 0x1p-45, 0x1p-44}}};
  for (std::uint32_t slot = 0; slot < kControlCount; ++slot) positions[slot] = control_positions[slot];
  for (std::uint32_t r = 0; r < kRowCount; ++r) {
    for (std::uint32_t e = 0; e < kEncodingCount; ++e) {
      for (std::uint32_t slot = 0; slot < kControlCount; ++slot) {
        offsets[(r * kEncodingCount + e) * kControlCount + slot] = table[r][e][slot];
      }
    }
  }
}

// Host-side buffers live in static storage: 2^20-entry arrays would overflow
// the stack, and no scientific value is ever placed in them.
static double g_objective[kStateCount];
static double g_card_square[kStateCount];
static std::uint32_t g_lift_counts[kStateCount];
static std::uint32_t g_invalid[kStateCount];
static std::uint64_t g_offsets[kStateCount + 1];

struct ScanResult {
  std::uint64_t natural_checksum;
  std::uint64_t controlled_checksum;
  std::uint64_t flags_checksum;
  std::uint64_t minimum_checksum;
  std::uint64_t word_count;
  std::uint64_t per_ch[kCHCount];
  std::uint32_t illegal;
  std::uint32_t nesting;
  std::uint32_t nonfinite;
  std::uint32_t disagreements;
};

static bool run_self_test() {
  int device_count = 0;
  if (cudaGetDeviceCount(&device_count) != cudaSuccess || device_count <= 0) return false;
  int selected = -1;
  cudaDeviceProp property{};
  for (int device = 0; device < device_count; ++device) {
    cudaDeviceProp candidate{};
    if (cudaGetDeviceProperties(&candidate, device) == cudaSuccess && candidate.major > 0) {
      selected = device; property = candidate; break;
    }
  }
  if (selected < 0 || cudaSetDevice(selected) != cudaSuccess) return false;

  const PayloadData host_payload = synthetic_payload();
  std::uint32_t host_control_positions[kControlCount]{};
  double host_control_offsets[kRowCount * kEncodingCount * kControlCount]{};
  synthetic_control(host_control_positions, host_control_offsets);

  PayloadData* device_payload = nullptr;
  CoefficientData* device_row = nullptr;
  double* device_objective = nullptr;
  double* device_card_square = nullptr;
  std::uint32_t* device_lift_counts = nullptr;
  std::uint32_t* device_invalid = nullptr;
  std::uint64_t* device_offsets = nullptr;
  double* device_energies = nullptr;
  double* device_segment_value = nullptr;
  std::uint64_t* device_segment_index = nullptr;
  std::uint32_t* device_segment_nonfinite = nullptr;
  std::uint64_t* device_per_ch = nullptr;
  std::uint32_t* device_illegal = nullptr;
  std::uint32_t* device_nesting = nullptr;

  bool ok = cudaMalloc(&device_payload, sizeof(host_payload)) == cudaSuccess &&
            cudaMalloc(&device_row, sizeof(CoefficientData)) == cudaSuccess &&
            cudaMalloc(&device_objective, sizeof(double) * kStateCount) == cudaSuccess &&
            cudaMalloc(&device_card_square, sizeof(double) * kStateCount) == cudaSuccess &&
            cudaMalloc(&device_lift_counts, sizeof(std::uint32_t) * kStateCount) == cudaSuccess &&
            cudaMalloc(&device_invalid, sizeof(std::uint32_t) * kStateCount) == cudaSuccess &&
            cudaMalloc(&device_offsets, sizeof(std::uint64_t) * (kStateCount + 1ULL)) == cudaSuccess;
  ok = ok && cudaMemcpy(device_payload, &host_payload, sizeof(host_payload), cudaMemcpyHostToDevice) == cudaSuccess;

  const dim3 state_grid(static_cast<unsigned>((kStateCount + kBlockSize - 1u) / kBlockSize));
  if (ok) G9_ENERGY_LAUNCH(terms_kernel, state_grid, dim3(kBlockSize), device_payload, device_objective,
                           device_card_square, device_lift_counts, device_invalid);
  ok = ok && cudaGetLastError() == cudaSuccess && cudaDeviceSynchronize() == cudaSuccess;
  ok = ok && cudaMemcpy(g_objective, device_objective, sizeof(double) * kStateCount, cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(g_card_square, device_card_square, sizeof(double) * kStateCount, cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(g_lift_counts, device_lift_counts, sizeof(std::uint32_t) * kStateCount, cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(g_invalid, device_invalid, sizeof(std::uint32_t) * kStateCount, cudaMemcpyDeviceToHost) == cudaSuccess;

  std::uint64_t lift_total = 0;
  std::uint32_t invalid_registers = 0;
  if (ok) {
    g_offsets[0] = 0ULL;
    for (std::uint64_t index = 0; index < kStateCount; ++index) {
      invalid_registers += g_invalid[index];
      const std::uint64_t multiplicity = g_lift_counts[index];
      if (multiplicity == 0ULL || multiplicity > kMaxLiftsPerState) { ok = false; break; }
      if (lift_total > kUint64Max - multiplicity) { ok = false; break; }
      lift_total += multiplicity;
      g_offsets[index + 1ULL] = lift_total;
    }
    ok = ok && invalid_registers == 0u && lift_total <= kCacheCapacity;
  }
  ok = ok && cudaMemcpy(device_offsets, g_offsets, sizeof(std::uint64_t) * (kStateCount + 1ULL), cudaMemcpyHostToDevice) == cudaSuccess;

  const std::uint64_t max_words = lift_total > kStateCount ? lift_total : kStateCount;
  const std::uint32_t max_segment_count = static_cast<std::uint32_t>((max_words + kSegmentSize - 1ULL) / kSegmentSize);
  if (ok) ok = cudaMalloc(&device_energies, sizeof(double) * static_cast<std::size_t>(max_words)) == cudaSuccess &&
               cudaMalloc(&device_segment_value, sizeof(double) * max_segment_count) == cudaSuccess &&
               cudaMalloc(&device_segment_index, sizeof(std::uint64_t) * max_segment_count) == cudaSuccess &&
               cudaMalloc(&device_segment_nonfinite, sizeof(std::uint32_t) * max_segment_count) == cudaSuccess &&
               cudaMalloc(&device_per_ch, sizeof(std::uint64_t) * max_segment_count * kCHCount) == cudaSuccess &&
               cudaMalloc(&device_illegal, sizeof(std::uint32_t) * max_segment_count) == cudaSuccess &&
               cudaMalloc(&device_nesting, sizeof(std::uint32_t) * max_segment_count) == cudaSuccess;

  double* host_energies = nullptr;
  double* host_segment_value = nullptr;
  std::uint64_t* host_segment_index = nullptr;
  std::uint32_t* host_segment_nonfinite = nullptr;
  std::uint64_t* host_per_ch = nullptr;
  std::uint32_t* host_illegal = nullptr;
  std::uint32_t* host_nesting = nullptr;
  if (ok) {
    host_energies = static_cast<double*>(std::malloc(sizeof(double) * static_cast<std::size_t>(max_words)));
    host_segment_value = static_cast<double*>(std::malloc(sizeof(double) * max_segment_count));
    host_segment_index = static_cast<std::uint64_t*>(std::malloc(sizeof(std::uint64_t) * max_segment_count));
    host_segment_nonfinite = static_cast<std::uint32_t*>(std::malloc(sizeof(std::uint32_t) * max_segment_count));
    host_per_ch = static_cast<std::uint64_t*>(std::malloc(sizeof(std::uint64_t) * max_segment_count * kCHCount));
    host_illegal = static_cast<std::uint32_t*>(std::malloc(sizeof(std::uint32_t) * max_segment_count));
    host_nesting = static_cast<std::uint32_t*>(std::malloc(sizeof(std::uint32_t) * max_segment_count));
    ok = host_energies && host_segment_value && host_segment_index && host_segment_nonfinite &&
         host_per_ch && host_illegal && host_nesting;
  }

  ScanResult results[kRowCount][kEncodingCount]{};
  for (std::uint32_t row = 0; ok && row < kRowCount; ++row) {
    const CoefficientData host_row = synthetic_row(row);
    ok = ok && cudaMemcpy(device_row, &host_row, sizeof(host_row), cudaMemcpyHostToDevice) == cudaSuccess;
    for (std::uint32_t encoding = 0; ok && encoding < kEncodingCount; ++encoding) {
      const std::uint64_t word_count = encoding == 0u ? kStateCount : lift_total;
      const std::uint32_t segment_count = static_cast<std::uint32_t>((word_count + kSegmentSize - 1ULL) / kSegmentSize);
      if (ok) G9_ENERGY_LAUNCH(energy_kernel, state_grid, dim3(kBlockSize), device_payload, device_row,
                               device_objective, device_card_square, device_offsets, encoding, device_energies);
      ok = ok && cudaGetLastError() == cudaSuccess && cudaDeviceSynchronize() == cudaSuccess;
      ok = ok && cudaMemcpy(host_energies, device_energies, sizeof(double) * static_cast<std::size_t>(word_count),
                            cudaMemcpyDeviceToHost) == cudaSuccess;
      if (!ok) break;

      ScanResult* result = &results[row][encoding];
      result->word_count = word_count;
      result->natural_checksum = kFNVOffset;
      std::uint32_t nonfinite = 0u;
      double natural_minimum = 0.0;
      bool have = false;
      for (std::uint64_t position = 0; position < word_count; ++position) {
        const double value = host_energies[position];
        result->natural_checksum = fnv_step(result->natural_checksum, double_to_word(value));
        if (value_is_nonfinite(value)) { nonfinite += 1u; continue; }
        if (!have || value < natural_minimum) { natural_minimum = value; have = true; }
      }
      if (!have) { ok = false; break; }

      // Apply the declared control offsets, then re-measure on device.
      const double* offsets_row = &host_control_offsets[(row * kEncodingCount + encoding) * kControlCount];
      for (std::uint32_t slot = 0; slot < kControlCount; ++slot) {
        const std::uint64_t position = host_control_positions[slot];
        if (position < word_count) host_energies[position] = natural_minimum + offsets_row[slot];
      }
      ok = ok && cudaMemcpy(device_energies, host_energies, sizeof(double) * static_cast<std::size_t>(word_count),
                            cudaMemcpyHostToDevice) == cudaSuccess;
      if (!ok) break;

      result->controlled_checksum = kFNVOffset;
      for (std::uint64_t position = 0; position < word_count; ++position) {
        result->controlled_checksum = fnv_step(result->controlled_checksum, double_to_word(host_energies[position]));
      }

      const dim3 segment_grid((segment_count + kBlockSize - 1u) / kBlockSize);
      if (ok) G9_ENERGY_LAUNCH(segment_kernel, segment_grid, dim3(kBlockSize), device_energies, word_count,
                               segment_count, device_segment_value, device_segment_index, device_segment_nonfinite);
      ok = ok && cudaGetLastError() == cudaSuccess && cudaDeviceSynchronize() == cudaSuccess;
      ok = ok && cudaMemcpy(host_segment_value, device_segment_value, sizeof(double) * segment_count, cudaMemcpyDeviceToHost) == cudaSuccess &&
           cudaMemcpy(host_segment_index, device_segment_index, sizeof(std::uint64_t) * segment_count, cudaMemcpyDeviceToHost) == cudaSuccess &&
           cudaMemcpy(host_segment_nonfinite, device_segment_nonfinite, sizeof(std::uint32_t) * segment_count, cudaMemcpyDeviceToHost) == cudaSuccess;
      if (!ok) break;

      // Fixed-order host merge in ascending segment order with strict '<'.
      double minimum = 0.0; std::uint64_t minimum_index = kUint64Max; bool merged = false;
      for (std::uint32_t segment = 0; segment < segment_count; ++segment) {
        nonfinite += host_segment_nonfinite[segment];
        if (host_segment_index[segment] == kUint64Max) continue;
        if (!merged || host_segment_value[segment] < minimum) {
          minimum = host_segment_value[segment];
          minimum_index = host_segment_index[segment];
          merged = true;
        }
      }
      if (!merged) { ok = false; break; }
      result->nonfinite = nonfinite;
      result->disagreements = (minimum == natural_minimum) ? 0u : 1u;
      result->minimum_checksum = fnv_step(fnv_step(kFNVOffset, double_to_word(minimum)), minimum_index);

      if (ok) G9_ENERGY_LAUNCH(flags_kernel, segment_grid, dim3(kBlockSize), device_energies, word_count,
                               minimum, segment_count, device_per_ch, device_illegal, device_nesting);
      ok = ok && cudaGetLastError() == cudaSuccess && cudaDeviceSynchronize() == cudaSuccess;
      ok = ok && cudaMemcpy(host_per_ch, device_per_ch, sizeof(std::uint64_t) * segment_count * kCHCount, cudaMemcpyDeviceToHost) == cudaSuccess &&
           cudaMemcpy(host_illegal, device_illegal, sizeof(std::uint32_t) * segment_count, cudaMemcpyDeviceToHost) == cudaSuccess &&
           cudaMemcpy(host_nesting, device_nesting, sizeof(std::uint32_t) * segment_count, cudaMemcpyDeviceToHost) == cudaSuccess;
      if (!ok) break;
      // The flag checksum is one FNV chain over the whole stream in canonical
      // order, which no per-segment digest can recombine, so the host replays it.
      result->flags_checksum = kFNVOffset;
      for (std::uint64_t position = 0; position < word_count; ++position) {
        result->flags_checksum = fnv_step(result->flags_checksum, tie_flags(host_energies[position], minimum));
      }
      for (std::uint32_t bit = 0; bit < kCHCount; ++bit) result->per_ch[bit] = 0ULL;
      result->illegal = 0u; result->nesting = 0u;
      for (std::uint32_t segment = 0; segment < segment_count; ++segment) {
        for (std::uint32_t bit = 0; bit < kCHCount; ++bit) result->per_ch[bit] += host_per_ch[segment * kCHCount + bit];
        result->illegal += host_illegal[segment];
        result->nesting += host_nesting[segment];
      }
    }
  }

  if (ok) {
    // Every lift's packed word in frozen cache order: the layout stays
    // load-bearing even though the energies consume register penalties.
    std::uint64_t lift_digest = kFNVOffset;
    for (std::uint64_t index = 0; index < kStateCount; ++index) {
      double sector[kSectorCount], budget;
      residuals_of(&host_payload, static_cast<std::uint32_t>(index), sector, &budget);
      std::uint32_t sector_bits = 0u;
      for (std::uint32_t s = 0; s < kSectorCount; ++s) {
        std::uint32_t values[2]; double penalties[2];
        register_minimizers(sector[s], register_maximum(s), values, penalties);
        sector_bits |= values[0] << register_offset(s);
      }
      std::uint32_t values[2]; double penalties[2];
      const std::uint32_t count = register_minimizers(budget, register_maximum(kSectorCount), values, penalties);
      for (std::uint32_t lift = 0; lift < count; ++lift) {
        lift_digest = fnv_step(lift_digest, sector_bits | (values[lift] << register_offset(kSectorCount)));
      }
    }
    std::uint64_t membership_digest = kFNVOffset;
    for (std::uint32_t s = 0; s < kSectorCount; ++s) {
      for (std::uint32_t m = 0; m < kSectorSize; ++m) {
        const std::uint32_t member = host_payload.membership[s][m];
        for (std::uint32_t shift = 0; shift < 32u; shift += 8u) {
          membership_digest = fnv_step(membership_digest, (member >> shift) & 0xFFu);
        }
      }
    }
    std::uint64_t coefficient_digest = kFNVOffset;
    for (std::uint32_t row = 0; row < kRowCount; ++row) {
      const CoefficientData r = synthetic_row(row);
      const double fields[7] = {r.alpha, r.sector_slack, r.budget_slack, r.sector_linear,
                                r.sector_quadratic, r.budget_linear, r.budget_quadratic};
      for (std::uint32_t field = 0; field < 7u; ++field) {
        coefficient_digest = fnv_step(coefficient_digest, double_to_word(fields[field]));
      }
    }
    std::uint64_t control_digest = kFNVOffset;
    for (std::uint32_t row = 0; row < kRowCount; ++row) {
      for (std::uint32_t encoding = 0; encoding < kEncodingCount; ++encoding) {
        for (std::uint32_t slot = 0; slot < kControlCount; ++slot) {
          control_digest = fnv_step(control_digest, host_control_positions[slot]);
          control_digest = fnv_step(control_digest,
              double_to_word(host_control_offsets[(row * kEncodingCount + encoding) * kControlCount + slot]));
        }
      }
    }
    std::uint64_t exact_registers = 0, clamped_registers = 0, tied_registers = 0;
    for (std::uint64_t index = 0; index < kStateCount; ++index) {
      double sector[kSectorCount], budget;
      residuals_of(&host_payload, static_cast<std::uint32_t>(index), sector, &budget);
      for (std::uint32_t reg = 0; reg < kRegisterCount; ++reg) {
        const double residual = reg < kSectorCount ? sector[reg] : budget;
        const std::uint32_t maximum = register_maximum(reg);
        std::uint32_t values[2]; double penalties[2];
        const std::uint32_t count = register_minimizers(residual, maximum, values, penalties);
        if (count > 1u) tied_registers += 1ULL;
        const bool exact = residual >= 0.0 && residual <= static_cast<double>(maximum) &&
                           residual == static_cast<double>(static_cast<long long>(residual));
        if (exact) exact_registers += 1ULL; else clamped_registers += 1ULL;
      }
    }
    std::uint32_t nonfinite_total = 0, disagreements = 0, illegal_total = 0, nesting_total = 0;
    for (std::uint32_t row = 0; row < kRowCount; ++row) {
      for (std::uint32_t encoding = 0; encoding < kEncodingCount; ++encoding) {
        nonfinite_total += results[row][encoding].nonfinite;
        disagreements += results[row][encoding].disagreements;
        illegal_total += results[row][encoding].illegal;
        nesting_total += results[row][encoding].nesting;
      }
    }
    const bool pass = nonfinite_total == 0u && disagreements == 0u && illegal_total == 0u &&
                      nesting_total == 0u && invalid_registers == 0u && lift_total > kStateCount;
    std::printf("{\"schema\":\"decisions_os/g9_cuda_full_domain_energy_self_test/v1\",\"device_index\":%d,\"device_name\":\"%s\",\"decoded_width\":%u,\"state_count\":%llu,\"segment_size\":%u,\"segment_count\":%llu,\"register_count\":%u,\"auxiliary_bits\":%u,\"row_count\":%u,\"lift_total\":%llu,\"cache_capacity\":%llu,\"lift_digest\":\"%016llx\",\"membership_digest\":\"%016llx\",\"coefficient_digest\":\"%016llx\",\"control_digest\":\"%016llx\",\"exact_registers\":%llu,\"clamped_registers\":%llu,\"tied_registers\":%llu,\"nonfinite_energies\":%u,\"reduction_disagreements\":%u,\"illegal_flag_entries\":%u,\"nesting_violations\":%u,\"scientific_outputs\":\"intentionally absent\"",
                selected, property.name, kDecodedWidth, static_cast<unsigned long long>(kStateCount),
                kSegmentSize, static_cast<unsigned long long>(kStateCount / kSegmentSize),
                kRegisterCount, kAuxiliaryBits, kRowCount,
                static_cast<unsigned long long>(lift_total),
                static_cast<unsigned long long>(kCacheCapacity),
                static_cast<unsigned long long>(lift_digest),
                static_cast<unsigned long long>(membership_digest),
                static_cast<unsigned long long>(coefficient_digest),
                static_cast<unsigned long long>(control_digest),
                static_cast<unsigned long long>(exact_registers),
                static_cast<unsigned long long>(clamped_registers),
                static_cast<unsigned long long>(tied_registers),
                nonfinite_total, disagreements, illegal_total, nesting_total);
    const char* row_names[kRowCount] = {"row0", "row1"};
    const char* encoding_names[kEncodingCount] = {"unbalanced", "slack"};
    for (std::uint32_t row = 0; row < kRowCount; ++row) {
      for (std::uint32_t encoding = 0; encoding < kEncodingCount; ++encoding) {
        const ScanResult* r = &results[row][encoding];
        std::printf(",\"natural_energy_checksum_%s_%s\":\"%016llx\",\"controlled_energy_checksum_%s_%s\":\"%016llx\",\"flags_checksum_%s_%s\":\"%016llx\",\"minimum_checksum_%s_%s\":\"%016llx\",\"word_count_%s_%s\":%llu,\"count_c_h_1024_%s_%s\":%llu,\"count_c_h_2048_%s_%s\":%llu,\"count_c_h_4096_%s_%s\":%llu",
                    row_names[row], encoding_names[encoding], static_cast<unsigned long long>(r->natural_checksum),
                    row_names[row], encoding_names[encoding], static_cast<unsigned long long>(r->controlled_checksum),
                    row_names[row], encoding_names[encoding], static_cast<unsigned long long>(r->flags_checksum),
                    row_names[row], encoding_names[encoding], static_cast<unsigned long long>(r->minimum_checksum),
                    row_names[row], encoding_names[encoding], static_cast<unsigned long long>(r->word_count),
                    row_names[row], encoding_names[encoding], static_cast<unsigned long long>(r->per_ch[0]),
                    row_names[row], encoding_names[encoding], static_cast<unsigned long long>(r->per_ch[1]),
                    row_names[row], encoding_names[encoding], static_cast<unsigned long long>(r->per_ch[2]));
      }
    }
    std::printf(",\"verdict\":\"%s\"}\n", pass ? "pass" : "fail");
    ok = ok && pass;
  }
  std::free(host_energies); std::free(host_segment_value); std::free(host_segment_index);
  std::free(host_segment_nonfinite); std::free(host_per_ch);
  std::free(host_illegal); std::free(host_nesting);
  cudaFree(device_payload); cudaFree(device_row); cudaFree(device_objective); cudaFree(device_card_square);
  cudaFree(device_lift_counts); cudaFree(device_invalid); cudaFree(device_offsets); cudaFree(device_energies);
  cudaFree(device_segment_value); cudaFree(device_segment_index); cudaFree(device_segment_nonfinite);
  cudaFree(device_per_ch); cudaFree(device_illegal); cudaFree(device_nesting);
  return ok;
}

int main(int argc, char** argv) {
  if (argc != 2 || std::strcmp(argv[1], "--self-test") != 0) {
    std::fprintf(stderr, "usage: stage2_cuda_full_domain_energy --self-test\n");
    return 2;
  }
  if (!run_self_test()) {
    std::fprintf(stderr, "FAIL Stage-2 full-domain energy self-test\n");
    return 1;
  }
  return 0;
}
