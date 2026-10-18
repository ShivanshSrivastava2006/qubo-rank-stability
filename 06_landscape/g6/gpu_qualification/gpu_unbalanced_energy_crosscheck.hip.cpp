// Non-production GPU-vs-CPU bit-exact cross-check of the unbalanced energy
// transcript for the experimental Gate-6 GPU track.
//
// This program is a bounded qualification prototype only.  It evaluates the
// FROZEN_MATH_SPEC.md section 5.2 unbalanced energy transcript, transcribed
// operation-for-operation from src/g4/energy.py, on an explicitly declared
// finite state set at explicitly declared coefficient points.  It does not
// enumerate a domain, search for a minimum, form a tie set, decode, label,
// aggregate, or emit a scientific value.  Its output is a file of raw
// binary64 bit patterns that the Python runner compares against the
// canonical Python evaluator; only mismatch counts are reported.
//
// Numerical contract (enforced here and by the compile command):
//   * binary64 only; no fp32, FMA, reassociation, fast-math, vector
//     reduction, pow, or transcendental substitution;
//   * every arithmetic operation is one explicit rounded statement in the
//     same order as src/g4/energy.py;
//   * the discrete gfx1201 device is selected by architecture name, never
//     by assuming device zero.

#include <hip/hip_runtime.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#pragma clang fp contract(off)
#pragma clang fp reassociate(off)

// Helpers keep the same linkage pattern as the accepted binary64 probe: static
// host/device helpers and one kernel at global scope.
constexpr std::uint32_t kAssetCount = 20;
constexpr std::uint32_t kSectorCount = 4;
constexpr std::uint32_t kSigmaCount = kAssetCount * kAssetCount;
constexpr std::uint32_t kCoefficientWords = 5;
constexpr std::uint64_t kInputMagic = 0x3158434E42553647ULL;   // "G6UBNCX1" little-endian
constexpr std::uint64_t kOutputMagic = 0x3159434E42553647ULL;  // "G6UBNCY1" little-endian
constexpr std::uint64_t kFormatVersion = 1;
constexpr std::uint64_t kStateMask = (1ULL << kAssetCount) - 1ULL;

// Instance data, transcribed from src/g4/instance.py's Instance fields.  K
// and C arrive already converted to binary64 because energy.py uses
// float(instance.K) and float(instance.C).
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

// One grid point's coefficients consumed by the unbalanced transcript.  The
// slack coefficients are deliberately absent: this prototype covers the
// unbalanced encoding only.
struct CoefficientPoint {
  double alpha;
  double sector_linear;
  double sector_quadratic;
  double budget_linear;
  double budget_quadratic;
};

// Literal transcription of src/g4/energy.py:
//   unbalanced_energy -> objective/_objective_from_bits,
//                        residuals/_residuals_from_bits,
//                        then the section 5.2 penalty accumulation.
// Bit order: x[i] = (mask >> i) & 1 for canonical ticker index i.
__host__ __device__ static double unbalanced_energy_transcript(
    const InstanceData* instance, const CoefficientPoint* coefficients,
    const std::uint64_t mask) {
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

  // unbalanced_energy: card_square, P_card, H_acc, four sector penalties,
  // budget penalty.
  const double card_square = h_card * h_card;
  const double p_card = coefficients->alpha * card_square;
  double h_acc = f_value;
  h_acc = h_acc + p_card;
  for (std::uint32_t j = 0; j < kSectorCount; ++j) {
    const double residual = h_sector[j];
    const double linear_product = coefficients->sector_linear * residual;
    const double quadratic_square = residual * residual;
    const double quadratic_product = coefficients->sector_quadratic * quadratic_square;
    const double negated_linear = -linear_product;
    const double penalty = negated_linear + quadratic_product;
    h_acc = h_acc + penalty;
  }
  const double budget_residual = h_budget;
  const double budget_linear_product = coefficients->budget_linear * budget_residual;
  const double budget_quadratic_square = budget_residual * budget_residual;
  const double budget_quadratic_product =
      coefficients->budget_quadratic * budget_quadratic_square;
  const double negated_budget_linear = -budget_linear_product;
  const double p_budget = negated_budget_linear + budget_quadratic_product;
  const double h_e = h_acc + p_budget;
  return h_e;
}

__device__ static std::uint64_t bits_device(const double value) {
  return static_cast<std::uint64_t>(__double_as_longlong(value));
}

static std::uint64_t bits_host(const double value) {
  std::uint64_t output = 0;
  std::memcpy(&output, &value, sizeof(output));
  return output;
}

// One thread per (coefficient point, state) pair.  Output index is
// point_index * state_count + state_index.
__global__ void crosscheck_kernel(const InstanceData* instance,
                                  const CoefficientPoint* points,
                                  const std::uint64_t* states,
                                  std::uint64_t* output,
                                  const std::uint32_t point_count,
                                  const std::uint32_t state_count) {
  const std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
  const std::uint32_t total = point_count * state_count;
  if (index < total) {
    const std::uint32_t point_index = index / state_count;
    const std::uint32_t state_index = index - point_index * state_count;
    output[index] = bits_device(unbalanced_energy_transcript(
        instance, &points[point_index], states[state_index]));
  }
}

static bool check(const hipError_t status, const char* call) {
  if (status == hipSuccess) {
    return true;
  }
  std::fprintf(stderr, "HIP failure at %s: %s\n", call, hipGetErrorString(status));
  return false;
}

static double word_to_double(const std::uint64_t word) {
  double value = 0.0;
  std::memcpy(&value, &word, sizeof(value));
  return value;
}

struct Inputs {
  InstanceData instance{};
  std::uint32_t point_count = 0;
  std::uint32_t state_count = 0;
  CoefficientPoint* points = nullptr;
  std::uint64_t* states = nullptr;
};

// Little-endian uint64 word stream written by the Python runner.  Layout is
// declared in research/g6/gpu_qualification/energy_crosscheck.py and
// validated field-by-field here; any structural surprise is a hard failure.
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

static bool load_inputs(const char* path, Inputs* inputs) {
  std::FILE* stream = std::fopen(path, "rb");
  if (stream == nullptr) {
    std::fprintf(stderr, "cannot open input file\n");
    return false;
  }
  bool ok = true;
  std::uint64_t header[5];
  ok = read_words(stream, header, 5);
  if (ok && (header[0] != kInputMagic || header[1] != kFormatVersion ||
             header[2] != kAssetCount)) {
    std::fprintf(stderr, "input header mismatch\n");
    ok = false;
  }
  if (ok && (header[3] == 0 || header[3] > 64 || header[4] == 0 || header[4] > (1ULL << 20))) {
    std::fprintf(stderr, "input point/state counts are outside the bounded contract\n");
    ok = false;
  }
  if (ok) {
    inputs->point_count = static_cast<std::uint32_t>(header[3]);
    inputs->state_count = static_cast<std::uint32_t>(header[4]);
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
        std::calloc(inputs->point_count, sizeof(CoefficientPoint)));
    inputs->states = static_cast<std::uint64_t*>(
        std::calloc(inputs->state_count, sizeof(std::uint64_t)));
    ok = inputs->points != nullptr && inputs->states != nullptr;
  }
  for (std::uint32_t p = 0; ok && p < inputs->point_count; ++p) {
    std::uint64_t words[kCoefficientWords];
    ok = read_words(stream, words, kCoefficientWords);
    if (ok) {
      inputs->points[p].alpha = word_to_double(words[0]);
      inputs->points[p].sector_linear = word_to_double(words[1]);
      inputs->points[p].sector_quadratic = word_to_double(words[2]);
      inputs->points[p].budget_linear = word_to_double(words[3]);
      inputs->points[p].budget_quadratic = word_to_double(words[4]);
    }
  }
  if (ok) {
    ok = read_words(stream, inputs->states, inputs->state_count);
    for (std::uint32_t s = 0; ok && s < inputs->state_count; ++s) {
      if (inputs->states[s] > kStateMask) {
        std::fprintf(stderr, "state exceeds 20 bits\n");
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

int main(int argc, char** argv) {
  if (argc != 3) {
    std::fprintf(stderr, "usage: %s <input.words> <output.words>\n", argv[0]);
    return 64;
  }
  Inputs inputs;
  if (!load_inputs(argv[1], &inputs)) {
    return 65;
  }
  const std::uint32_t total = inputs.point_count * inputs.state_count;

  int device_count = 0;
  if (!check(hipGetDeviceCount(&device_count), "hipGetDeviceCount") || device_count < 1) {
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
  if (selected_device < 0 || !check(hipSetDevice(selected_device), "hipSetDevice(gfx1201)")) {
    std::fprintf(stderr, "no gfx1201 device is visible\n");
    return 2;
  }

  InstanceData* device_instance = nullptr;
  CoefficientPoint* device_points = nullptr;
  std::uint64_t* device_states = nullptr;
  std::uint64_t* device_output = nullptr;
  std::uint64_t* host_output =
      static_cast<std::uint64_t*>(std::calloc(total, sizeof(std::uint64_t)));
  std::uint64_t* host_reference =
      static_cast<std::uint64_t*>(std::calloc(total, sizeof(std::uint64_t)));
  bool ok = host_output != nullptr && host_reference != nullptr;
  ok = ok && check(hipMalloc(&device_instance, sizeof(InstanceData)), "hipMalloc(instance)") &&
       check(hipMalloc(&device_points, inputs.point_count * sizeof(CoefficientPoint)),
             "hipMalloc(points)") &&
       check(hipMalloc(&device_states, inputs.state_count * sizeof(std::uint64_t)),
             "hipMalloc(states)") &&
       check(hipMalloc(&device_output, total * sizeof(std::uint64_t)), "hipMalloc(output)") &&
       check(hipMemcpy(device_instance, &inputs.instance, sizeof(InstanceData),
                       hipMemcpyHostToDevice),
             "hipMemcpy(instance)") &&
       check(hipMemcpy(device_points, inputs.points,
                       inputs.point_count * sizeof(CoefficientPoint), hipMemcpyHostToDevice),
             "hipMemcpy(points)") &&
       check(hipMemcpy(device_states, inputs.states,
                       inputs.state_count * sizeof(std::uint64_t), hipMemcpyHostToDevice),
             "hipMemcpy(states)");
  if (ok) {
    constexpr std::uint32_t block_size = 64;
    const std::uint32_t block_count = (total + block_size - 1) / block_size;
    hipLaunchKernelGGL(crosscheck_kernel, dim3(block_count), dim3(block_size), 0, 0,
                       device_instance, device_points, device_states, device_output,
                       inputs.point_count, inputs.state_count);
    ok = check(hipGetLastError(), "kernel launch") &&
         check(hipDeviceSynchronize(), "hipDeviceSynchronize") &&
         check(hipMemcpy(host_output, device_output, total * sizeof(std::uint64_t),
                         hipMemcpyDeviceToHost),
               "hipMemcpy(output)");
  }
  // Host C++ transcript of the same function, kept only as triage evidence
  // for the Python runner.  The Python evaluator remains the reference.
  std::uint32_t device_vs_host_mismatches = 0;
  for (std::uint32_t index = 0; ok && index < total; ++index) {
    const std::uint32_t point_index = index / inputs.state_count;
    const std::uint32_t state_index = index - point_index * inputs.state_count;
    host_reference[index] = bits_host(unbalanced_energy_transcript(
        &inputs.instance, &inputs.points[point_index], inputs.states[state_index]));
    if (host_reference[index] != host_output[index]) {
      ++device_vs_host_mismatches;
    }
  }
  if (ok) {
    std::FILE* stream = std::fopen(argv[2], "wb");
    ok = stream != nullptr;
    if (ok) {
      const std::uint64_t header[5] = {kOutputMagic, kFormatVersion, inputs.point_count,
                                       inputs.state_count,
                                       static_cast<std::uint64_t>(selected_device)};
      ok = write_words(stream, header, 5) && write_words(stream, host_output, total) &&
           write_words(stream, host_reference, total);
      ok = (std::fclose(stream) == 0) && ok;
    }
    if (!ok) {
      std::fprintf(stderr, "cannot write output file\n");
    }
  }
  if (device_instance != nullptr) hipFree(device_instance);
  if (device_points != nullptr) hipFree(device_points);
  if (device_states != nullptr) hipFree(device_states);
  if (device_output != nullptr) hipFree(device_output);
  std::free(host_output);
  std::free(host_reference);
  std::free(inputs.points);
  std::free(inputs.states);
  if (!ok) return 2;

  std::printf(
      "{\"architecture\":\"%s\",\"device_index\":%d,\"device_name\":\"%s\","
      "\"device_vs_host_cxx_mismatches\":%u,\"evaluations\":%u,"
      "\"point_count\":%u,\"probe\":\"unbalanced_energy_transcript_crosscheck\","
      "\"scientific_outputs\":\"intentionally absent\",\"state_count\":%u}\n",
      properties.gcnArchName, selected_device, properties.name, device_vs_host_mismatches,
      total, inputs.point_count, inputs.state_count);
  return 0;
}
