// CUDA/T4 V-14 core batch engine: device minima and D015 tie flags only.
//
// This is the production-isolated core producer's device program.  It is
// derived from the reviewed non-value engine (cuda_v14_prepared_domain_engine.cu)
// and shares its transcripts verbatim: canonical prepared domains, the
// qualified unbalanced and slack energy transcripts, the deterministic
// first-seen strict minimum, and the D015 tie comparator at c_H in
// {1024, 2048, 4096}.  It differs in ONE respect: it never writes an energy
// word or a per-state flag array.  Per coordinate it returns to the host
// only the two encodings' H_min bit patterns with their canonical domain
// indices and the COMPACTED tie list: one word per tied state (flags in the
// high bits, canonical index in the low bits), in ascending canonical index
// order.  Energies and per-state flags exist only in device memory (and, in
// validate mode, energies in the host C++ reference's process memory) and
// are freed on exit.  The host reconstructs T_E / X_E from the compact list
// with the canonical Python services and performs every D016 classification
// there.
//
// Ordering proof for the compaction: the domain [0, count) is split into
// kPartialCount contiguous chunks; chunk t counts its tied states, the host
// forms exclusive prefix sums over the chunk counts in chunk order, and
// chunk t then writes its tied states in ascending index order starting at
// its prefix offset.  Chunks are disjoint, contiguous, and increasing, so
// the concatenation is exactly the ascending sequence of tied indices --
// the canonical enumeration order certify.py's tie loop uses.  No atomics,
// no shared memory, no data-dependent scheduling.
//
// Modes: 0 = validate (host C++ transcript recomputes minima and flags and
// reports a mismatch count), 1 = produce (device only).  A future --run-batch
// uses mode 1; nothing in this program aggregates, rates, or interprets.
//
// Numerical contract: binary64 only; no fp32, FMA, reassociation, fast-math,
// flush-to-zero, shared-memory or atomic reductions; nvcc --fmad=false
// --ftz=false --prec-div=true --prec-sqrt=true; host -ffp-contract=off; only
// an NVIDIA T4 (compute capability 7.5, sm_75) is selected, by capability and
// name, never by assuming device zero.

#include <cuda_runtime.h>

#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#pragma STDC FP_CONTRACT OFF

// Kernel launch.  nvcc compiles the real triple-chevron launch; the
// host-emulation stub (never on a real nvcc include path) provides
// g6_host_emulation_launch so an ordinary C++ compiler can run the same
// kernels serially on the CPU.  __CUDACC__ is defined by nvcc only.
#if defined(__CUDACC__)
#define G6_LAUNCH_KERNEL(kernel, grid, block, ...) kernel<<<grid, block>>>(__VA_ARGS__)
#else
#define G6_LAUNCH_KERNEL(kernel, grid, block, ...) \
  g6_host_emulation_launch(kernel, grid, block, __VA_ARGS__)
#endif

constexpr std::uint32_t kAssetCount = 20;
constexpr std::uint32_t kSectorCount = 4;
constexpr std::uint32_t kSigmaCount = kAssetCount * kAssetCount;
constexpr std::uint32_t kSectorSlackBits = 2;
constexpr std::uint32_t kBudgetSlackBits = 11;
constexpr std::uint32_t kAuxiliaryLength = kSectorCount * kSectorSlackBits + kBudgetSlackBits;
constexpr std::uint32_t kDecodedCount = 1u << kAssetCount;
constexpr std::uint32_t kCoefficientWords = 7;
constexpr std::uint32_t kHeaderWords = 9;
constexpr std::uint32_t kMaxCoordinates = 4096;
constexpr std::uint64_t kInputMagic = 0x3158503431563647ULL;   // "G6V14PX1" little-endian
constexpr std::uint64_t kOutputMagic = 0x3159433431563647ULL;  // "G6V14CY1" little-endian
constexpr std::uint64_t kFormatVersion = 1;
constexpr std::uint64_t kModeValidate = 0;
constexpr std::uint64_t kModeProduce = 1;
constexpr std::uint64_t kStateMask = (1ULL << kAssetCount) - 1ULL;
constexpr std::uint64_t kAuxiliaryMask = (1ULL << kAuxiliaryLength) - 1ULL;
constexpr int kTargetMajor = 7;
constexpr int kTargetMinor = 5;
constexpr std::uint32_t kChCount = 3;
constexpr std::uint32_t kPartialCount = 4096;
// Compact tie entry: (flags << 32) | canonical index.  Hard cap on the tied
// entries one run may emit (2^28 words = 2 GiB); exceeding it fails closed.
constexpr std::uint32_t kEntryFlagShift = 32;
constexpr std::uint64_t kMaxTiedEntriesPerRun = 1ULL << 28;
constexpr std::uint32_t kBlockSize = 64;
// D015 frozen c_H family and epsilon = 2^-52 (energy.py EPSILON; exact literal).
__host__ __device__ inline double ch_value(const std::uint32_t k) {
  return k == 0 ? 1024.0 : (k == 1 ? 2048.0 : 4096.0);
}
constexpr double kEpsilon = 0x1p-52;

struct InstanceData {
  double mu[kAssetCount];
  double sigma[kSigmaCount];  // row-major: sigma[i * 20 + k] == instance.sigma[i][k]
  double prices[kAssetCount];
  double kappa_risk;
  double k_float;
  double c_float;
  double b;
  std::uint32_t sector_count[kSectorCount];
  std::uint32_t sector_member[kSectorCount][kAssetCount];  // sorted ascending
};

// One coordinate's seven coefficients (src/g4/parameters.py Coefficients
// field order), assembled by the runner from the ledger rows card/sector/budget.
struct CoefficientPoint {
  double alpha;
  double sector_slack;
  double budget_slack;
  double sector_linear;
  double sector_quadratic;
  double budget_linear;
  double budget_quadratic;
};

// energy.py PreparedDecodedState.
struct PreparedDecoded {
  double f_value;
  double card_square;
  double h_sector[kSectorCount];
  double sector_square[kSectorCount];
  double h_budget;
  double budget_square;
};

// energy.py PreparedSlackState (the grid-independent slack squares).
struct PreparedSlack {
  double sector_slack_square[kSectorCount];
  double budget_slack_square;
};

// BinaryDomain index -> little-endian mask consumed by the qualified transcript.
__host__ __device__ static std::uint64_t canonical_index_to_mask(const std::uint32_t index) {
  std::uint64_t mask = 0;
  for (std::uint32_t i = 0; i < kAssetCount; ++i) {
    mask |= static_cast<std::uint64_t>((index >> (kAssetCount - 1 - i)) & 1u) << i;
  }
  return mask;
}

// energy.py prepare_decoded_state: the qualified unbalanced transcript prefix
// (verbatim) followed by card_square, sector_square[j], budget_square.
__host__ __device__ static void prepare_decoded_transcript(
    const InstanceData* instance, const std::uint64_t mask, PreparedDecoded* out) {
  // _x_bits: float(bit) for each of the 20 bits.
  double xs[kAssetCount];
  for (std::uint32_t i = 0; i < kAssetCount; ++i) {
    xs[i] = ((mask >> i) & 1ULL) ? 1.0 : 0.0;
  }

  // _objective_from_bits: mu_term[i] = -(mu[i] * x[i]).
  double mu_term[kAssetCount];
  for (std::uint32_t i = 0; i < kAssetCount; ++i) {
    const double product = instance->mu[i] * xs[i];
    mu_term[i] = -product;
  }
  // quad_term[i,k] = kappa_risk * ((sigma[i][k] * x[i]) * x[k]).
  double quad_term[kSigmaCount];
  for (std::uint32_t i = 0; i < kAssetCount; ++i) {
    for (std::uint32_t k = 0; k < kAssetCount; ++k) {
      const double sigma_xi = instance->sigma[i * kAssetCount + k] * xs[i];
      const double inner = sigma_xi * xs[k];
      quad_term[i * kAssetCount + k] = instance->kappa_risk * inner;
    }
  }
  // f_acc starts at +0.0; mu terms first, then quad terms, in index order.
  double f_acc = +0.0;
  for (std::uint32_t i = 0; i < kAssetCount; ++i) {
    f_acc = f_acc + mu_term[i];
  }
  for (std::uint32_t index = 0; index < kSigmaCount; ++index) {
    f_acc = f_acc + quad_term[index];
  }
  const double f_value = f_acc;

  // _residuals_from_bits.
  double card_sum = +0.0;
  for (std::uint32_t i = 0; i < kAssetCount; ++i) {
    card_sum = card_sum + xs[i];
  }
  const double h_card = card_sum - instance->k_float;

  double h_sector[kSectorCount];
  for (std::uint32_t j = 0; j < kSectorCount; ++j) {
    double sector_sum = +0.0;
    for (std::uint32_t m = 0; m < instance->sector_count[j]; ++m) {
      const std::uint32_t i = instance->sector_member[j][m];
      sector_sum = sector_sum + xs[i];
    }
    h_sector[j] = instance->c_float - sector_sum;
  }

  double budget_sum = +0.0;
  for (std::uint32_t i = 0; i < kAssetCount; ++i) {
    const double spend = instance->prices[i] * xs[i];
    budget_sum = budget_sum + spend;
  }
  const double h_budget = instance->b - budget_sum;

  out->f_value = f_value;
  out->card_square = h_card * h_card;
  for (std::uint32_t j = 0; j < kSectorCount; ++j) {
    out->h_sector[j] = h_sector[j];
    out->sector_square[j] = h_sector[j] * h_sector[j];
  }
  out->h_budget = h_budget;
  out->budget_square = h_budget * h_budget;
}

// energy.py prepare_slack_state: the qualified slack transcript's register,
// delta, and square statements (verbatim) over the supplied auxiliary word.
__host__ __device__ static void prepare_slack_transcript(
    const PreparedDecoded* decoded, const std::uint64_t auxiliary_word, PreparedSlack* out) {
  const double* h_sector = decoded->h_sector;
  const double h_budget = decoded->h_budget;
  std::uint32_t offset = 0;
  for (std::uint32_t j = 0; j < kSectorCount; ++j) {
    // _slack_register over this sector's y bits: S_acc starts at +0.0;
    // term = 2^d * y[d] with 2^d formed by integer shift (_bit_weight).
    double s_acc = +0.0;
    for (std::uint32_t d = 0; d < kSectorSlackBits; ++d) {
      const double y_d = ((auxiliary_word >> (offset + d)) & 1ULL) ? 1.0 : 0.0;
      const double weight = static_cast<double>(1ULL << d);
      const double term = weight * y_d;
      s_acc = s_acc + term;
    }
    offset = offset + kSectorSlackBits;
    const double slack_delta = h_sector[j] - s_acc;
    const double slack_square = slack_delta * slack_delta;
    out->sector_slack_square[j] = slack_square;
  }
  // _slack_register over the budget's y bits.
  double budget_s_acc = +0.0;
  for (std::uint32_t d = 0; d < kBudgetSlackBits; ++d) {
    const double y_d = ((auxiliary_word >> (offset + d)) & 1ULL) ? 1.0 : 0.0;
    const double weight = static_cast<double>(1ULL << d);
    const double term = weight * y_d;
    budget_s_acc = budget_s_acc + term;
  }
  const double budget_slack_delta = h_budget - budget_s_acc;
  const double budget_slack_square = budget_slack_delta * budget_slack_delta;
  out->budget_slack_square = budget_slack_square;
}

// energy.py unbalanced_energy_prepared.
__host__ __device__ static double unbalanced_energy_prepared_transcript(
    const PreparedDecoded* state, const CoefficientPoint* values) {
  const double p_card = values->alpha * state->card_square;
  double h_acc = state->f_value;
  h_acc = h_acc + p_card;
  for (std::uint32_t j = 0; j < kSectorCount; ++j) {
    const double residual = state->h_sector[j];
    const double linear_product = values->sector_linear * residual;
    const double quadratic_product = values->sector_quadratic * state->sector_square[j];
    const double negated_linear = -linear_product;
    const double penalty = negated_linear + quadratic_product;
    h_acc = h_acc + penalty;
  }
  const double linear_product = values->budget_linear * state->h_budget;
  const double quadratic_product = values->budget_quadratic * state->budget_square;
  const double negated_linear = -linear_product;
  const double p_budget = negated_linear + quadratic_product;
  const double h_e = h_acc + p_budget;
  return h_e;
}

// energy.py slack_energy_prepared.
__host__ __device__ static double slack_energy_prepared_transcript(
    const PreparedDecoded* decoded, const PreparedSlack* state, const CoefficientPoint* values) {
  const double p_card = values->alpha * decoded->card_square;
  double h_acc = decoded->f_value;
  h_acc = h_acc + p_card;
  for (std::uint32_t j = 0; j < kSectorCount; ++j) {
    const double penalty = values->sector_slack * state->sector_slack_square[j];
    h_acc = h_acc + penalty;
  }
  const double p_budget = values->budget_slack * state->budget_slack_square;
  const double h_e = h_acc + p_budget;
  return h_e;
}

// certify.py tie comparator for one state at every frozen c_H; bit k of the
// result is the c_H = {1024, 2048, 4096}[k] membership.
__host__ __device__ static std::uint8_t tie_flags_transcript(
    const double y, const double h_min, const double lambda_ref) {
  const double diff = y - h_min;
  const double gap = fabs(diff);
  const double abs_y = fabs(y);
  const double abs_min = fabs(h_min);
  const double m = (abs_min > abs_y) ? abs_min : abs_y;  // Python max(abs(y), abs(h_min))
  const double scale = lambda_ref + m;
  std::uint8_t flags = 0;
  for (std::uint32_t k = 0; k < kChCount; ++k) {
    const double c_eps = ch_value(k) * kEpsilon;
    const double tie_tau = c_eps * scale;
    if (gap <= tie_tau) {
      flags = static_cast<std::uint8_t>(flags | (1u << k));
    }
  }
  return flags;
}

__host__ __device__ static double word_to_double_any(const std::uint64_t word) {
  double value = 0.0;
  std::memcpy(&value, &word, sizeof(value));
  return value;
}

__host__ __device__ static std::uint64_t double_to_word_any(const double value) {
  std::uint64_t output = 0;
  std::memcpy(&output, &value, sizeof(output));
  return output;
}

__global__ void prepare_decoded_kernel(const InstanceData* instance, PreparedDecoded* prepared) {
  const std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index < kDecodedCount) {
    prepare_decoded_transcript(instance, canonical_index_to_mask(index), &prepared[index]);
  }
}

__global__ void prepare_slack_kernel(const PreparedDecoded* prepared, const std::uint32_t* entry_mask,
                                     const std::uint64_t* auxiliaries, PreparedSlack* slack,
                                     const std::uint32_t slack_count) {
  const std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index < slack_count) {
    prepare_slack_transcript(&prepared[entry_mask[index]], auxiliaries[index], &slack[index]);
  }
}

// One thread per prepared state: decoded states first (unbalanced energy),
// then slack entries, each in canonical prepared-domain order.
__global__ void energy_kernel(const PreparedDecoded* prepared, const PreparedSlack* slack,
                              const std::uint32_t* entry_mask, const CoefficientPoint* values,
                              std::uint64_t* out_unbalanced, std::uint64_t* out_slack,
                              const std::uint32_t slack_count) {
  const std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index < kDecodedCount) {
    out_unbalanced[index] = double_to_word_any(unbalanced_energy_prepared_transcript(&prepared[index], values));
  } else if (index < kDecodedCount + slack_count) {
    const std::uint32_t entry = index - kDecodedCount;
    out_slack[entry] = double_to_word_any(
        slack_energy_prepared_transcript(&prepared[entry_mask[entry]], &slack[entry], values));
  }
}

// A binary64 word is non-finite (inf or NaN) iff its exponent field is all ones.
__host__ __device__ static bool word_is_nonfinite(const std::uint64_t word) {
  return ((word >> 52) & 0x7FFULL) == 0x7FFULL;
}

// Deterministic strided partial minimum: partial t scans t, t+P, t+2P, ...
// keeping the first-seen strict minimum, exactly as certify.py's first pass,
// and counts every non-finite word it visits (summed on the host in both
// modes, so throughput mode genuinely inspects every energy word).
__global__ void min_partial_kernel(const std::uint64_t* words, const std::uint32_t count,
                                   std::uint64_t* partial_bits, std::uint32_t* partial_index,
                                   std::uint32_t* partial_nonfinite) {
  const std::uint32_t t = blockIdx.x * blockDim.x + threadIdx.x;
  if (t < kPartialCount) {
    bool have = false;
    double best = 0.0;
    std::uint32_t best_index = 0;
    std::uint32_t nonfinite = 0;
    for (std::uint32_t i = t; i < count; i += kPartialCount) {
      if (word_is_nonfinite(words[i])) ++nonfinite;
      const double y = word_to_double_any(words[i]);
      if (!have || y < best) {
        have = true;
        best = y;
        best_index = i;
      }
    }
    partial_bits[t] = have ? double_to_word_any(best) : 0;
    partial_index[t] = have ? best_index : count;
    partial_nonfinite[t] = nonfinite;
  }
}

__global__ void tie_flags_kernel(const std::uint64_t* words, const std::uint32_t count,
                                 const std::uint64_t h_min_bits, const double lambda_ref,
                                 std::uint8_t* flags) {
  const std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index < count) {
    flags[index] = tie_flags_transcript(word_to_double_any(words[index]), word_to_double_any(h_min_bits),
                                        lambda_ref);
  }
}

// Deterministic stable compaction, step 1: chunk t (a contiguous range of
// `chunk` states) counts its tied states.
__global__ void tie_count_kernel(const std::uint8_t* flags, const std::uint32_t count,
                                 const std::uint32_t chunk, std::uint32_t* chunk_counts) {
  const std::uint32_t t = blockIdx.x * blockDim.x + threadIdx.x;
  if (t < kPartialCount) {
    const std::uint32_t begin = t * chunk;
    const std::uint32_t end = (begin + chunk < count) ? begin + chunk : count;
    std::uint32_t tied = 0;
    for (std::uint32_t i = begin; i < end; ++i) {
      if (flags[i] != 0) ++tied;
    }
    chunk_counts[t] = tied;
  }
}

// Step 2: chunk t writes its tied states, in ascending index order, at the
// host-computed exclusive prefix offset.  Together with step 1 this yields
// the ascending canonical sequence of tied indices.
__global__ void tie_compact_kernel(const std::uint8_t* flags, const std::uint32_t count,
                                   const std::uint32_t chunk, const std::uint32_t* chunk_offsets,
                                   std::uint64_t* entries) {
  const std::uint32_t t = blockIdx.x * blockDim.x + threadIdx.x;
  if (t < kPartialCount) {
    const std::uint32_t begin = t * chunk;
    const std::uint32_t end = (begin + chunk < count) ? begin + chunk : count;
    std::uint32_t cursor = chunk_offsets[t];
    for (std::uint32_t i = begin; i < end; ++i) {
      if (flags[i] != 0) {
        entries[cursor++] = (static_cast<std::uint64_t>(flags[i]) << kEntryFlagShift) | static_cast<std::uint64_t>(i);
      }
    }
  }
}

static bool check(const cudaError_t status, const char* call) {
  if (status == cudaSuccess) {
    return true;
  }
  std::fprintf(stderr, "CUDA failure at %s: %s\n", call, cudaGetErrorString(status));
  return false;
}

static double word_to_double(const std::uint64_t word) {
  double value = 0.0;
  std::memcpy(&value, &word, sizeof(value));
  return value;
}

static bool read_words(std::FILE* stream, std::uint64_t* destination, const std::size_t count) {
  for (std::size_t index = 0; index < count; ++index) {
    unsigned char bytes[8];
    if (std::fread(bytes, 1, sizeof(bytes), stream) != sizeof(bytes)) {
      return false;
    }
    std::uint64_t word = 0;
    for (int b = 7; b >= 0; --b) {
      word = (word << 8) | static_cast<std::uint64_t>(bytes[b]);
    }
    destination[index] = word;
  }
  return true;
}

static bool write_words(std::FILE* stream, const std::uint64_t* source, const std::size_t count) {
  for (std::size_t index = 0; index < count; ++index) {
    unsigned char bytes[8];
    std::uint64_t word = source[index];
    for (int b = 0; b < 8; ++b) {
      bytes[b] = static_cast<unsigned char>(word & 0xFFULL);
      word >>= 8;
    }
    if (std::fwrite(bytes, 1, sizeof(bytes), stream) != sizeof(bytes)) {
      return false;
    }
  }
  return true;
}


struct Inputs {
  InstanceData instance{};
  std::uint64_t mode = 0;
  std::uint32_t coordinate_count = 0;
  std::uint32_t slack_count = 0;
  double lambda_ref = 0.0;
  CoefficientPoint* points = nullptr;
  std::uint64_t* offsets = nullptr;      // kDecodedCount + 1 words (SlackDomainCache.offset_bytes)
  std::uint64_t* auxiliaries = nullptr;  // slack_count words (SlackDomainCache.auxiliary_bytes)
  std::uint32_t* entry_mask = nullptr;   // derived: decoded index owning each slack entry
};

// Little-endian uint64 word stream written by the Python runner.  Header:
// magic, version, asset count, sector slack bits, budget slack bits, mode,
// coordinate count, slack entry count, Lambda_ref bits.
static bool load_inputs(const char* path, Inputs* inputs) {
  std::FILE* stream = std::fopen(path, "rb");
  if (stream == nullptr) {
    std::fprintf(stderr, "cannot open input file\n");
    return false;
  }
  bool ok = true;
  std::uint64_t header[kHeaderWords];
  ok = read_words(stream, header, kHeaderWords);
  if (ok && (header[0] != kInputMagic || header[1] != kFormatVersion || header[2] != kAssetCount ||
             header[3] != kSectorSlackBits || header[4] != kBudgetSlackBits)) {
    std::fprintf(stderr, "input header mismatch\n");
    ok = false;
  }
  if (ok && (header[5] != kModeValidate && header[5] != kModeProduce)) {
    std::fprintf(stderr, "unknown mode\n");
    ok = false;
  }
  if (ok && (header[6] == 0 || header[6] > kMaxCoordinates || header[7] == 0 ||
             header[7] > (1ULL << 32) - 1ULL)) {
    std::fprintf(stderr, "coordinate/slack counts are outside the bounded contract\n");
    ok = false;
  }
  if (ok) {
    inputs->mode = header[5];
    inputs->coordinate_count = static_cast<std::uint32_t>(header[6]);
    inputs->slack_count = static_cast<std::uint32_t>(header[7]);
    inputs->lambda_ref = word_to_double(header[8]);
    if (!(inputs->lambda_ref > 0.0) || std::isinf(inputs->lambda_ref)) {
      std::fprintf(stderr, "Lambda_ref must be finite and strictly positive\n");
      ok = false;
    }
  }
  if (ok) {
    std::uint64_t scalar_words[kAssetCount + kSigmaCount + kAssetCount + 4];
    ok = read_words(stream, scalar_words, sizeof(scalar_words) / sizeof(scalar_words[0]));
    if (ok) {
      std::size_t cursor = 0;
      for (std::uint32_t i = 0; i < kAssetCount; ++i) {
        inputs->instance.mu[i] = word_to_double(scalar_words[cursor++]);
      }
      for (std::uint32_t index = 0; index < kSigmaCount; ++index) {
        inputs->instance.sigma[index] = word_to_double(scalar_words[cursor++]);
      }
      for (std::uint32_t i = 0; i < kAssetCount; ++i) {
        inputs->instance.prices[i] = word_to_double(scalar_words[cursor++]);
      }
      inputs->instance.kappa_risk = word_to_double(scalar_words[cursor++]);
      inputs->instance.k_float = word_to_double(scalar_words[cursor++]);
      inputs->instance.c_float = word_to_double(scalar_words[cursor++]);
      inputs->instance.b = word_to_double(scalar_words[cursor++]);
    }
  }
  if (ok) {
    std::uint32_t seen[kAssetCount] = {};
    for (std::uint32_t j = 0; ok && j < kSectorCount; ++j) {
      std::uint64_t count_word = 0;
      ok = read_words(stream, &count_word, 1);
      if (!ok || count_word == 0 || count_word > kAssetCount) {
        std::fprintf(stderr, "sector count malformed\n");
        ok = false;
        break;
      }
      inputs->instance.sector_count[j] = static_cast<std::uint32_t>(count_word);
      std::uint64_t members[kAssetCount];
      ok = read_words(stream, members, count_word);
      for (std::uint64_t m = 0; ok && m < count_word; ++m) {
        if (members[m] >= kAssetCount || (m > 0 && members[m] <= members[m - 1])) {
          std::fprintf(stderr, "sector members are not sorted distinct indices\n");
          ok = false;
          break;
        }
        inputs->instance.sector_member[j][m] = static_cast<std::uint32_t>(members[m]);
        seen[members[m]] += 1;
      }
    }
    for (std::uint32_t i = 0; ok && i < kAssetCount; ++i) {
      if (seen[i] != 1) {
        std::fprintf(stderr, "sectors do not partition the asset index set\n");
        ok = false;
      }
    }
  }

  if (ok) {
    inputs->points = static_cast<CoefficientPoint*>(
        std::calloc(inputs->coordinate_count, sizeof(CoefficientPoint)));
    inputs->offsets = static_cast<std::uint64_t*>(
        std::calloc(static_cast<std::size_t>(kDecodedCount) + 1, sizeof(std::uint64_t)));
    inputs->auxiliaries = static_cast<std::uint64_t*>(
        std::calloc(inputs->slack_count, sizeof(std::uint64_t)));
    inputs->entry_mask = static_cast<std::uint32_t*>(
        std::calloc(inputs->slack_count, sizeof(std::uint32_t)));
    ok = inputs->points != nullptr && inputs->offsets != nullptr && inputs->auxiliaries != nullptr &&
         inputs->entry_mask != nullptr;
  }
  for (std::uint32_t c = 0; ok && c < inputs->coordinate_count; ++c) {
    std::uint64_t words[kCoefficientWords];
    ok = read_words(stream, words, kCoefficientWords);
    if (ok) {
      inputs->points[c].alpha = word_to_double(words[0]);
      inputs->points[c].sector_slack = word_to_double(words[1]);
      inputs->points[c].budget_slack = word_to_double(words[2]);
      inputs->points[c].sector_linear = word_to_double(words[3]);
      inputs->points[c].sector_quadratic = word_to_double(words[4]);
      inputs->points[c].budget_linear = word_to_double(words[5]);
      inputs->points[c].budget_quadratic = word_to_double(words[6]);
    }
  }
  if (ok) {
    ok = read_words(stream, inputs->offsets, static_cast<std::size_t>(kDecodedCount) + 1);
    // SlackDomainCache invariants: offsets[0] == 0, strictly increasing
    // (every decoded state has at least one lift), last == slack_count.
    if (ok && (inputs->offsets[0] != 0 || inputs->offsets[kDecodedCount] != inputs->slack_count)) {
      std::fprintf(stderr, "slack-domain offsets do not cover the cached lifts\n");
      ok = false;
    }
    for (std::uint32_t d = 0; ok && d < kDecodedCount; ++d) {
      if (inputs->offsets[d + 1] <= inputs->offsets[d]) {
        std::fprintf(stderr, "every decoded state must have at least one cached lift\n");
        ok = false;
        break;
      }
      for (std::uint64_t e = inputs->offsets[d]; e < inputs->offsets[d + 1]; ++e) {
        inputs->entry_mask[e] = d;
      }
    }
  }
  if (ok) {
    ok = read_words(stream, inputs->auxiliaries, inputs->slack_count);
    for (std::uint32_t e = 0; ok && e < inputs->slack_count; ++e) {
      if (inputs->auxiliaries[e] > kAuxiliaryMask) {
        std::fprintf(stderr, "slack auxiliary exceeds 19 bits\n");
        ok = false;
      }
    }
  }
  if (ok) {
    unsigned char trailing = 0;
    if (std::fread(&trailing, 1, 1, stream) != 0) {
      std::fprintf(stderr, "unexpected trailing input bytes\n");
      ok = false;
    }
  }
  if (!ok) {
    std::fprintf(stderr, "input file is malformed or truncated\n");
  }
  std::fclose(stream);
  return ok;
}

// The device must be an NVIDIA T4: compute capability exactly 7.5 and a
// name containing "T4".  The Python runner additionally requires the exact
// product name; this program never falls back to another capability.
static bool is_target_device(const cudaDeviceProp& properties) {
  return properties.major == kTargetMajor && properties.minor == kTargetMinor &&
         std::strstr(properties.name, "T4") != nullptr;
}

static void print_uuid_hex(const cudaDeviceProp& properties) {
  for (int b = 0; b < 16; ++b) {
    std::printf("%02x", static_cast<unsigned>(static_cast<unsigned char>(properties.uuid.bytes[b])));
  }
}

static std::int64_t now_ns() {
  return static_cast<std::int64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now().time_since_epoch()).count());
}

// Finish a strided partial minimum in index order: smallest value, then the
// smallest index among equal values (== certify.py's first-seen strict '<').
static bool finish_minimum(const std::uint64_t* partial_bits, const std::uint32_t* partial_index,
                           const std::uint32_t count, std::uint64_t* h_min_bits, std::uint32_t* h_min_index) {
  bool have = false;
  double best = 0.0;
  std::uint32_t best_index = 0;
  for (std::uint32_t t = 0; t < kPartialCount; ++t) {
    if (partial_index[t] >= count) continue;
    const double y = word_to_double(partial_bits[t]);
    if (!have || y < best || (y == best && partial_index[t] < best_index)) {
      have = true;
      best = y;
      best_index = partial_index[t];
    }
  }
  *h_min_bits = double_to_word_any(best);
  *h_min_index = best_index;
  return have;
}

static std::uint32_t sum_partials(const std::uint32_t* partials) {
  std::uint32_t total = 0;
  for (std::uint32_t t = 0; t < kPartialCount; ++t) {
    total += partials[t];
  }
  return total;
}

int main(int argc, char** argv) {
  if (argc != 3) {
    std::fprintf(stderr, "usage: %s <input.words> <output.words>\n", argv[0]);
    return 64;
  }
  Inputs inputs;
  if (!load_inputs(argv[1], &inputs)) {
    return 65;
  }
  if (inputs.slack_count % 8 != 0) {
    std::fprintf(stderr, "slack entry count must be a multiple of eight for packed flags\n");
    return 65;
  }
  const bool validate = inputs.mode == kModeValidate;
  const std::uint32_t slack_count = inputs.slack_count;
  const std::uint32_t per_coordinate = kDecodedCount + slack_count;

  int device_count = 0;
  if (!check(cudaGetDeviceCount(&device_count), "cudaGetDeviceCount") || device_count < 1) {
    return 2;
  }
  int selected_device = -1;
  cudaDeviceProp properties{};
  for (int candidate = 0; candidate < device_count; ++candidate) {
    cudaDeviceProp candidate_properties{};
    if (!check(cudaGetDeviceProperties(&candidate_properties, candidate),
               "cudaGetDeviceProperties")) {
      return 2;
    }
    // Select the target by capability and name explicitly rather than
    // assuming device zero; any other visible GPU is ignored, never used.
    if (is_target_device(candidate_properties)) {
      selected_device = candidate;
      properties = candidate_properties;
      break;
    }
  }
  if (selected_device < 0 || !check(cudaSetDevice(selected_device), "cudaSetDevice(T4)")) {
    std::fprintf(stderr, "no NVIDIA T4 (compute capability 7.5) device is visible\n");
    return 2;
  }
  int driver_version = 0;
  int runtime_version = 0;
  if (!check(cudaDriverGetVersion(&driver_version), "cudaDriverGetVersion") ||
      !check(cudaRuntimeGetVersion(&runtime_version), "cudaRuntimeGetVersion")) {
    return 2;
  }

  InstanceData* device_instance = nullptr;
  PreparedDecoded* device_prepared = nullptr;
  PreparedSlack* device_slack = nullptr;
  std::uint32_t* device_entry_mask = nullptr;
  std::uint64_t* device_auxiliaries = nullptr;
  CoefficientPoint* device_points = nullptr;
  std::uint64_t* device_out_u = nullptr;
  std::uint64_t* device_out_s = nullptr;
  std::uint64_t* device_partial_bits = nullptr;
  std::uint32_t* device_partial_index = nullptr;
  std::uint32_t* device_partial_nonfinite = nullptr;
  std::uint8_t* device_flags_u = nullptr;
  std::uint8_t* device_flags_s = nullptr;
  std::uint64_t* partial_bits = static_cast<std::uint64_t*>(std::calloc(kPartialCount, sizeof(std::uint64_t)));
  std::uint32_t* partial_index = static_cast<std::uint32_t*>(std::calloc(kPartialCount, sizeof(std::uint32_t)));
  std::uint32_t* partial_nonfinite = static_cast<std::uint32_t*>(std::calloc(kPartialCount, sizeof(std::uint32_t)));
  std::uint32_t* chunk_counts = static_cast<std::uint32_t*>(std::calloc(kPartialCount, sizeof(std::uint32_t)));
  std::uint32_t* chunk_offsets = static_cast<std::uint32_t*>(std::calloc(kPartialCount, sizeof(std::uint32_t)));
  std::uint32_t* device_chunk_counts = nullptr;
  std::uint32_t* device_chunk_offsets = nullptr;
  std::uint64_t* device_entries = nullptr;
  // Host-side compact tie lists are allocated per coordinate and encoding at
  // exactly the tied count (bounded by the larger domain: 2^20 entries =
  // 8 MiB), never by the coordinate count, and freed before the next coordinate.
  PreparedDecoded* host_prepared = nullptr;
  PreparedSlack* host_slack = nullptr;
  bool ok = partial_bits != nullptr && partial_index != nullptr && partial_nonfinite != nullptr &&
            chunk_counts != nullptr && chunk_offsets != nullptr;
  const std::uint32_t larger_domain = kDecodedCount > slack_count ? kDecodedCount : slack_count;
  ok = ok && check(cudaMalloc(&device_instance, sizeof(InstanceData)), "cudaMalloc(instance)") &&
       check(cudaMalloc(&device_prepared, static_cast<std::size_t>(kDecodedCount) * sizeof(PreparedDecoded)),
             "cudaMalloc(prepared)") &&
       check(cudaMalloc(&device_slack, static_cast<std::size_t>(slack_count) * sizeof(PreparedSlack)),
             "cudaMalloc(slack)") &&
       check(cudaMalloc(&device_entry_mask, static_cast<std::size_t>(slack_count) * sizeof(std::uint32_t)),
             "cudaMalloc(entry_mask)") &&
       check(cudaMalloc(&device_auxiliaries, static_cast<std::size_t>(slack_count) * sizeof(std::uint64_t)),
             "cudaMalloc(auxiliaries)") &&
       check(cudaMalloc(&device_points, inputs.coordinate_count * sizeof(CoefficientPoint)),
             "cudaMalloc(points)") &&
       check(cudaMalloc(&device_out_u, static_cast<std::size_t>(kDecodedCount) * sizeof(std::uint64_t)),
             "cudaMalloc(out_u)") &&
       check(cudaMalloc(&device_out_s, static_cast<std::size_t>(slack_count) * sizeof(std::uint64_t)),
             "cudaMalloc(out_s)") &&
       check(cudaMalloc(&device_partial_bits, kPartialCount * sizeof(std::uint64_t)), "cudaMalloc(partial_bits)") &&
       check(cudaMalloc(&device_partial_index, kPartialCount * sizeof(std::uint32_t)), "cudaMalloc(partial_index)") &&
       check(cudaMalloc(&device_partial_nonfinite, kPartialCount * sizeof(std::uint32_t)), "cudaMalloc(partial_nonfinite)") &&
       check(cudaMalloc(&device_flags_u, kDecodedCount), "cudaMalloc(flags_u)") &&
       check(cudaMalloc(&device_flags_s, slack_count), "cudaMalloc(flags_s)") &&
       check(cudaMalloc(&device_chunk_counts, kPartialCount * sizeof(std::uint32_t)), "cudaMalloc(chunk_counts)") &&
       check(cudaMalloc(&device_chunk_offsets, kPartialCount * sizeof(std::uint32_t)), "cudaMalloc(chunk_offsets)") &&
       check(cudaMalloc(&device_entries, static_cast<std::size_t>(larger_domain) * sizeof(std::uint64_t)),
             "cudaMalloc(entries)") &&
       check(cudaMemcpy(device_instance, &inputs.instance, sizeof(InstanceData), cudaMemcpyHostToDevice),
             "cudaMemcpy(instance)") &&
       check(cudaMemcpy(device_entry_mask, inputs.entry_mask, static_cast<std::size_t>(slack_count) * sizeof(std::uint32_t),
                        cudaMemcpyHostToDevice), "cudaMemcpy(entry_mask)") &&
       check(cudaMemcpy(device_auxiliaries, inputs.auxiliaries, static_cast<std::size_t>(slack_count) * sizeof(std::uint64_t),
                        cudaMemcpyHostToDevice), "cudaMemcpy(auxiliaries)") &&
       check(cudaMemcpy(device_points, inputs.points, inputs.coordinate_count * sizeof(CoefficientPoint),
                        cudaMemcpyHostToDevice), "cudaMemcpy(points)");

  // Phase 1 (once): prepare both canonical domains on the device.
  const std::int64_t prepare_start = now_ns();
  if (ok) {
    G6_LAUNCH_KERNEL(prepare_decoded_kernel, dim3((kDecodedCount + kBlockSize - 1) / kBlockSize), dim3(kBlockSize),
                     device_instance, device_prepared);
    ok = check(cudaGetLastError(), "prepare_decoded launch") && check(cudaDeviceSynchronize(), "prepare_decoded sync");
  }
  if (ok) {
    G6_LAUNCH_KERNEL(prepare_slack_kernel, dim3((slack_count + kBlockSize - 1) / kBlockSize), dim3(kBlockSize),
                     device_prepared, device_entry_mask, device_auxiliaries, device_slack, slack_count);
    ok = check(cudaGetLastError(), "prepare_slack launch") && check(cudaDeviceSynchronize(), "prepare_slack sync");
  }
  const std::int64_t prepare_end = now_ns();

  // Host C++ transcript of the prepared domains, validate mode only: it
  // recomputes every energy, minimum, and tie flag in process memory and is
  // compared with the device; nothing from it is written.  The Python
  // evaluators remain the reference.
  std::uint64_t* host_energy = nullptr;
  if (ok && validate) {
    host_prepared = static_cast<PreparedDecoded*>(std::calloc(kDecodedCount, sizeof(PreparedDecoded)));
    host_slack = static_cast<PreparedSlack*>(std::calloc(slack_count, sizeof(PreparedSlack)));
    host_energy = static_cast<std::uint64_t*>(std::calloc(kDecodedCount > slack_count ? kDecodedCount : slack_count,
                                                          sizeof(std::uint64_t)));
    ok = host_prepared != nullptr && host_slack != nullptr && host_energy != nullptr;
    for (std::uint32_t d = 0; ok && d < kDecodedCount; ++d) {
      prepare_decoded_transcript(&inputs.instance, canonical_index_to_mask(d), &host_prepared[d]);
    }
    for (std::uint32_t e = 0; ok && e < slack_count; ++e) {
      prepare_slack_transcript(&host_prepared[inputs.entry_mask[e]], inputs.auxiliaries[e], &host_slack[e]);
    }
  }

  std::FILE* stream = nullptr;
  if (ok) {
    stream = std::fopen(argv[2], "wb");
    ok = stream != nullptr;
    if (ok) {
      const std::uint64_t header[7] = {kOutputMagic, kFormatVersion, inputs.mode, inputs.coordinate_count,
                                       kDecodedCount, slack_count, static_cast<std::uint64_t>(selected_device)};
      ok = write_words(stream, header, 7);
    }
    if (!ok) std::fprintf(stderr, "cannot write output file\n");
  }

  // Phase 2 (per coordinate, timed): energies stay on the device; the host
  // receives only the strided partial minima and the packed tie flags.
  std::uint32_t device_vs_host_mismatches = 0;
  // Cumulative over both encodings and up to kMaxCoordinates coordinates
  // (bound 4096 * 2^21 = 2^33 > 2^32), so both cumulative controls are 64-bit;
  // per-encoding counts are bounded by 2^20 and stay 32-bit.
  std::uint64_t nonfinite_total = 0;
  std::uint64_t nesting_total = 0;
  std::uint64_t evaluations = 0;
  std::uint64_t entries_total = 0;  // tied entries written this run; capped by kMaxTiedEntriesPerRun
  std::uint64_t checksum = 0;  // folds every internal result so no work can be elided; never printed
  const std::int64_t coordinates_start = now_ns();
  for (std::uint32_t c = 0; ok && c < inputs.coordinate_count; ++c) {
    G6_LAUNCH_KERNEL(energy_kernel, dim3((per_coordinate + kBlockSize - 1) / kBlockSize), dim3(kBlockSize),
                     device_prepared, device_slack, device_entry_mask, &device_points[c],
                     device_out_u, device_out_s, slack_count);
    ok = check(cudaGetLastError(), "energy launch") && check(cudaDeviceSynchronize(), "energy sync");
    std::uint64_t h_min_bits[2] = {0, 0};
    std::uint32_t h_min_index[2] = {0, 0};
    const std::uint64_t* outs[2] = {device_out_u, device_out_s};
    std::uint8_t* device_flags[2] = {device_flags_u, device_flags_s};
    const std::uint32_t counts[2] = {kDecodedCount, slack_count};
    std::uint32_t tied_counts[2] = {0, 0};
    std::uint64_t coordinate_record[6] = {0, 0, 0, 0, 0, 0};
    // Entries for both encodings are buffered for this coordinate only, then written.
    std::uint64_t* encoding_entries[2] = {nullptr, nullptr};
    for (std::uint32_t enc = 0; ok && enc < 2; ++enc) {
      G6_LAUNCH_KERNEL(min_partial_kernel, dim3((kPartialCount + kBlockSize - 1) / kBlockSize), dim3(kBlockSize),
                       outs[enc], counts[enc], device_partial_bits, device_partial_index, device_partial_nonfinite);
      ok = check(cudaGetLastError(), "min launch") && check(cudaDeviceSynchronize(), "min sync") &&
           check(cudaMemcpy(partial_bits, device_partial_bits, kPartialCount * sizeof(std::uint64_t),
                            cudaMemcpyDeviceToHost), "cudaMemcpy(partial_bits)") &&
           check(cudaMemcpy(partial_index, device_partial_index, kPartialCount * sizeof(std::uint32_t),
                            cudaMemcpyDeviceToHost), "cudaMemcpy(partial_index)") &&
           check(cudaMemcpy(partial_nonfinite, device_partial_nonfinite, kPartialCount * sizeof(std::uint32_t),
                            cudaMemcpyDeviceToHost), "cudaMemcpy(partial_nonfinite)");
      if (ok) {
        nonfinite_total += sum_partials(partial_nonfinite);
      }
      if (ok && !finish_minimum(partial_bits, partial_index, counts[enc], &h_min_bits[enc], &h_min_index[enc])) {
        std::fprintf(stderr, "empty reduction\n");
        ok = false;
      }
      if (ok) {
        G6_LAUNCH_KERNEL(tie_flags_kernel, dim3((counts[enc] + kBlockSize - 1) / kBlockSize), dim3(kBlockSize),
                         outs[enc], counts[enc], h_min_bits[enc], inputs.lambda_ref, device_flags[enc]);
        ok = check(cudaGetLastError(), "tie launch") && check(cudaDeviceSynchronize(), "tie sync");
      }
      // Deterministic stable compaction of the tied states (see the header).
      const std::uint32_t chunk = (counts[enc] + kPartialCount - 1) / kPartialCount;
      if (ok) {
        G6_LAUNCH_KERNEL(tie_count_kernel, dim3((kPartialCount + kBlockSize - 1) / kBlockSize), dim3(kBlockSize),
                         device_flags[enc], counts[enc], chunk, device_chunk_counts);
        ok = check(cudaGetLastError(), "tie count launch") && check(cudaDeviceSynchronize(), "tie count sync") &&
             check(cudaMemcpy(chunk_counts, device_chunk_counts, kPartialCount * sizeof(std::uint32_t),
                              cudaMemcpyDeviceToHost), "cudaMemcpy(chunk_counts)");
      }
      if (ok) {
        std::uint32_t running = 0;
        for (std::uint32_t c2 = 0; c2 < kPartialCount; ++c2) {
          chunk_offsets[c2] = running;
          running += chunk_counts[c2];
        }
        tied_counts[enc] = running;
        if (running == 0 || running > counts[enc]) {
          std::fprintf(stderr, "compaction count outside [1, domain]\n");
          ok = false;
        }
      }
      if (ok) {
        ok = check(cudaMemcpy(device_chunk_offsets, chunk_offsets, kPartialCount * sizeof(std::uint32_t),
                              cudaMemcpyHostToDevice), "cudaMemcpy(chunk_offsets)");
        G6_LAUNCH_KERNEL(tie_compact_kernel, dim3((kPartialCount + kBlockSize - 1) / kBlockSize), dim3(kBlockSize),
                         device_flags[enc], counts[enc], chunk, device_chunk_offsets, device_entries);
        ok = ok && check(cudaGetLastError(), "tie compact launch") && check(cudaDeviceSynchronize(), "tie compact sync");
      }
      if (ok) {
        encoding_entries[enc] = static_cast<std::uint64_t*>(std::calloc(tied_counts[enc], sizeof(std::uint64_t)));
        ok = encoding_entries[enc] != nullptr &&
             check(cudaMemcpy(encoding_entries[enc], device_entries, static_cast<std::size_t>(tied_counts[enc]) * sizeof(std::uint64_t),
                              cudaMemcpyDeviceToHost), "cudaMemcpy(entries)");
      }
      if (ok) {
        // Structural checks on the compact list: strictly ascending indices,
        // D015 nesting (flags in {4, 6, 7}), the minimum tied at every c_H.
        std::uint64_t previous_index = 0;
        bool min_seen = false;
        std::uint32_t primary_ties = 0;
        for (std::uint32_t k = 0; k < tied_counts[enc]; ++k) {
          const std::uint64_t entry = encoding_entries[enc][k];
          const std::uint64_t index = entry & 0xFFFFFFFFULL;
          const std::uint32_t f = static_cast<std::uint32_t>(entry >> kEntryFlagShift);
          if (k > 0 && index <= previous_index) {
            std::fprintf(stderr, "compaction order violated\n");
            ok = false;
            break;
          }
          previous_index = index;
          if (f != 4u && f != 6u && f != 7u) ++nesting_total;
          if (f & 2u) ++primary_ties;
          if (index == h_min_index[enc] && f == 7u) min_seen = true;
        }
        if (ok && !min_seen) {
          std::fprintf(stderr, "minimum state is not tied at every c_H\n");
          ok = false;
        }
        checksum ^= h_min_bits[enc] ^ (static_cast<std::uint64_t>(h_min_index[enc]) << 32) ^ primary_ties ^ tied_counts[enc];
      }
      if (ok && validate) {
        // Host C++ reference for this encoding: energies, first-seen minimum,
        // and flags recomputed in process memory and compared against the
        // device minimum and the compact list, streaming, with no host flag array.
        bool have = false;
        double best = 0.0;
        std::uint32_t best_index = 0;
        for (std::uint32_t i = 0; i < counts[enc]; ++i) {
          const double y = enc == 0
              ? unbalanced_energy_prepared_transcript(&host_prepared[i], &inputs.points[c])
              : slack_energy_prepared_transcript(&host_prepared[inputs.entry_mask[i]], &host_slack[i], &inputs.points[c]);
          host_energy[i] = double_to_word_any(y);
          if (!have || y < best) {
            have = true;
            best = y;
            best_index = i;
          }
        }
        if (double_to_word_any(best) != h_min_bits[enc] || best_index != h_min_index[enc]) {
          ++device_vs_host_mismatches;
        }
        std::uint32_t cursor = 0;
        for (std::uint32_t i = 0; i < counts[enc]; ++i) {
          const std::uint8_t reference = tie_flags_transcript(word_to_double_any(host_energy[i]), best, inputs.lambda_ref);
          const bool device_tied = cursor < tied_counts[enc] &&
                                   (encoding_entries[enc][cursor] & 0xFFFFFFFFULL) == static_cast<std::uint64_t>(i);
          if (reference != 0) {
            if (!device_tied || static_cast<std::uint8_t>(encoding_entries[enc][cursor] >> kEntryFlagShift) != reference) {
              ++device_vs_host_mismatches;
            }
            if (device_tied) ++cursor;
          } else if (device_tied) {
            ++device_vs_host_mismatches;
            ++cursor;
          }
        }
        if (cursor != tied_counts[enc]) ++device_vs_host_mismatches;
      }
    }
    if (ok) {
      entries_total += static_cast<std::uint64_t>(tied_counts[0]) + static_cast<std::uint64_t>(tied_counts[1]);
      if (entries_total > kMaxTiedEntriesPerRun) {
        std::fprintf(stderr, "tied-entry output cap exceeded\n");
        ok = false;
      }
    }
    evaluations += per_coordinate;
    if (ok) {
      coordinate_record[0] = h_min_bits[0];
      coordinate_record[1] = h_min_index[0];
      coordinate_record[2] = h_min_bits[1];
      coordinate_record[3] = h_min_index[1];
      coordinate_record[4] = tied_counts[0];
      coordinate_record[5] = tied_counts[1];
      ok = write_words(stream, coordinate_record, 6) && write_words(stream, encoding_entries[0], tied_counts[0]) &&
           write_words(stream, encoding_entries[1], tied_counts[1]);
      if (!ok) std::fprintf(stderr, "cannot write output file\n");
    }
    std::free(encoding_entries[0]);
    std::free(encoding_entries[1]);
  }
  const std::int64_t coordinates_end = now_ns();
  if (stream != nullptr) {
    ok = (std::fclose(stream) == 0) && ok;
  }

  if (device_instance != nullptr) cudaFree(device_instance);
  if (device_prepared != nullptr) cudaFree(device_prepared);
  if (device_slack != nullptr) cudaFree(device_slack);
  if (device_entry_mask != nullptr) cudaFree(device_entry_mask);
  if (device_auxiliaries != nullptr) cudaFree(device_auxiliaries);
  if (device_points != nullptr) cudaFree(device_points);
  if (device_out_u != nullptr) cudaFree(device_out_u);
  if (device_out_s != nullptr) cudaFree(device_out_s);
  if (device_partial_bits != nullptr) cudaFree(device_partial_bits);
  if (device_partial_index != nullptr) cudaFree(device_partial_index);
  if (device_partial_nonfinite != nullptr) cudaFree(device_partial_nonfinite);
  if (device_flags_u != nullptr) cudaFree(device_flags_u);
  if (device_flags_s != nullptr) cudaFree(device_flags_s);
  if (device_chunk_counts != nullptr) cudaFree(device_chunk_counts);
  if (device_chunk_offsets != nullptr) cudaFree(device_chunk_offsets);
  if (device_entries != nullptr) cudaFree(device_entries);
  std::free(partial_bits);
  std::free(partial_index);
  std::free(partial_nonfinite);
  std::free(chunk_counts);
  std::free(chunk_offsets);
  std::free(host_prepared);
  std::free(host_slack);
  std::free(host_energy);
  std::free(inputs.points);
  std::free(inputs.offsets);
  std::free(inputs.auxiliaries);
  std::free(inputs.entry_mask);
  if (!ok) return 2;
  // The checksum is consumed only to keep every internal result live; it is
  // deliberately not printed.
  if (checksum == 0xFFFFFFFFFFFFFFFFULL && evaluations == 0) return 3;

  // Environment identity and counters only.  No energy, minimum, tie count,
  // state, or label is printed.
#if defined(__CUDACC_VER_MAJOR__) && defined(__CUDACC_VER_MINOR__) && defined(__CUDACC_VER_BUILD__)
  const int nvcc_major = __CUDACC_VER_MAJOR__;
  const int nvcc_minor = __CUDACC_VER_MINOR__;
  const int nvcc_build = __CUDACC_VER_BUILD__;
  const char* backend = "cuda-runtime";
#else
  const int nvcc_major = 0;
  const int nvcc_minor = 0;
  const int nvcc_build = 0;
  const char* backend = "not-nvcc";
#endif
  std::printf(
      "{\"architecture\":\"sm_%d%d\",\"backend\":\"%s\",\"compute_capability\":\"%d.%d\","
      "\"coordinate_count\":%u,\"cuda_driver_version\":%d,\"cuda_runtime_version\":%d,"
      "\"decoded_state_count\":%u,\"device_count\":%d,\"device_index\":%d,\"device_name\":\"%s\","
      "\"device_uuid_hex\":\"",
      properties.major, properties.minor, backend, properties.major, properties.minor,
      inputs.coordinate_count, driver_version, runtime_version, kDecodedCount, device_count,
      selected_device, properties.name);
  print_uuid_hex(properties);
  std::printf(
      "\",\"device_vs_host_cxx_mismatches\":%u,\"elapsed_ns_coordinates\":%lld,\"elapsed_ns_prepare\":%lld,"
      "\"evaluations\":%llu,\"host_reference_evaluated\":%s,\"mode\":\"%s\",\"multiprocessor_count\":%d,"
      "\"nonfinite_energies\":%llu,\"nvcc_version\":\"%d.%d.%d\",\"pci_bus_id\":%d,\"pci_device_id\":%d,"
      "\"pci_domain_id\":%d,\"point_count\":%u,\"probe\":\"v14_core_batch_engine_cuda\","
      "\"scientific_outputs\":\"intentionally absent\",\"slack_state_count\":%u,\"state_count\":%u,"
      "\"tie_nesting_violations\":%llu,\"tied_entries_written\":%llu,\"total_global_memory_bytes\":%llu}\n",
      device_vs_host_mismatches, static_cast<long long>(coordinates_end - coordinates_start),
      static_cast<long long>(prepare_end - prepare_start), static_cast<unsigned long long>(evaluations),
      validate ? "true" : "false", validate ? "validate" : "produce", properties.multiProcessorCount,
      static_cast<unsigned long long>(nonfinite_total), nvcc_major, nvcc_minor, nvcc_build, properties.pciBusID,
      properties.pciDeviceID,
      properties.pciDomainID, inputs.coordinate_count, slack_count, per_coordinate,
      static_cast<unsigned long long>(nesting_total), static_cast<unsigned long long>(entries_total),
      static_cast<unsigned long long>(properties.totalGlobalMem));
  return 0;
}
