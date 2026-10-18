// Non-production CUDA-vs-CPU bit-exact cross-check of the unbalanced energy
// transcript for the Gate-6 CUDA/T4 qualification track.
//
// This program is a bounded qualification prototype only.  It evaluates the
// FROZEN_MATH_SPEC.md section 5.2 unbalanced energy transcript, transcribed
// operation-for-operation from src/g4/energy.py (and identical in statement
// order to the reviewed HIP transcription), on an explicitly declared finite
// state set at explicitly declared coefficient points.  It does not enumerate
// a domain, search for a minimum, form a tie set, decode, label, aggregate,
// or emit a scientific value.  Its output is a file of raw binary64 bit
// patterns that the Python runner compares against the canonical Python
// evaluator; only mismatch counts and environment identity are reported.
//
// Numerical contract (enforced here and by the nvcc compile command):
//   * binary64 only; no fp32, FMA, reassociation, fast-math, flush-to-zero,
//     vector reduction, pow, or transcendental substitution;
//   * every arithmetic operation is one explicit rounded statement in the
//     same order as src/g4/energy.py;
//   * nvcc is invoked with --fmad=false --ftz=false --prec-div=true
//     --prec-sqrt=true and the host compiler with -ffp-contract=off; the
//     STDC pragma below is a declaration of intent, the flags are the
//     authority;
//   * only an NVIDIA T4 (compute capability 7.5, sm_75) is selected, by
//     capability and name, never by assuming device zero.
//
// The input and output word streams are the same formats the reviewed HIP
// cross-check consumes and produces, so the Python runner reuses that
// module's state set, coefficient points, encoder, decoder, and comparator.

#include <cuda_runtime.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#pragma STDC FP_CONTRACT OFF

// Kernel launch.  nvcc compiles the real triple-chevron launch; the
// host-emulation stub (never on a real nvcc include path) provides
// g6_host_emulation_launch so an ordinary C++ compiler can run the same
// kernel serially on the CPU.  __CUDACC__ is defined by nvcc only.
#if defined(__CUDACC__)
#define G6_LAUNCH_KERNEL(kernel, grid, block, ...) kernel<<<grid, block>>>(__VA_ARGS__)
#else
#define G6_LAUNCH_KERNEL(kernel, grid, block, ...) \
  g6_host_emulation_launch(kernel, grid, block, __VA_ARGS__)
#endif

constexpr std::uint32_t kAssetCount = 20;
constexpr std::uint32_t kSectorCount = 4;
constexpr std::uint32_t kSigmaCount = kAssetCount * kAssetCount;
constexpr std::uint32_t kCoefficientWords = 5;
constexpr std::uint64_t kInputMagic = 0x3158434E42553647ULL;   // "G6UBNCX1" little-endian
constexpr std::uint64_t kOutputMagic = 0x3159434E42553647ULL;  // "G6UBNCY1" little-endian
constexpr std::uint64_t kFormatVersion = 1;
constexpr std::uint64_t kStateMask = (1ULL << kAssetCount) - 1ULL;
constexpr int kTargetMajor = 7;
constexpr int kTargetMinor = 5;

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
  CoefficientPoint* device_points = nullptr;
  std::uint64_t* device_states = nullptr;
  std::uint64_t* device_output = nullptr;
  std::uint64_t* host_output =
      static_cast<std::uint64_t*>(std::calloc(total, sizeof(std::uint64_t)));
  std::uint64_t* host_reference =
      static_cast<std::uint64_t*>(std::calloc(total, sizeof(std::uint64_t)));
  bool ok = host_output != nullptr && host_reference != nullptr;
  ok = ok && check(cudaMalloc(&device_instance, sizeof(InstanceData)), "cudaMalloc(instance)") &&
       check(cudaMalloc(&device_points, inputs.point_count * sizeof(CoefficientPoint)),
             "cudaMalloc(points)") &&
       check(cudaMalloc(&device_states, inputs.state_count * sizeof(std::uint64_t)),
             "cudaMalloc(states)") &&
       check(cudaMalloc(&device_output, total * sizeof(std::uint64_t)), "cudaMalloc(output)") &&
       check(cudaMemcpy(device_instance, &inputs.instance, sizeof(InstanceData),
                        cudaMemcpyHostToDevice),
             "cudaMemcpy(instance)") &&
       check(cudaMemcpy(device_points, inputs.points,
                        inputs.point_count * sizeof(CoefficientPoint), cudaMemcpyHostToDevice),
             "cudaMemcpy(points)") &&
       check(cudaMemcpy(device_states, inputs.states,
                        inputs.state_count * sizeof(std::uint64_t), cudaMemcpyHostToDevice),
             "cudaMemcpy(states)");
  if (ok) {
    constexpr std::uint32_t block_size = 64;
    const std::uint32_t block_count = (total + block_size - 1) / block_size;
    G6_LAUNCH_KERNEL(crosscheck_kernel, dim3(block_count), dim3(block_size),
                     device_instance, device_points, device_states, device_output,
                     inputs.point_count, inputs.state_count);
    ok = check(cudaGetLastError(), "kernel launch") &&
         check(cudaDeviceSynchronize(), "cudaDeviceSynchronize") &&
         check(cudaMemcpy(host_output, device_output, total * sizeof(std::uint64_t),
                          cudaMemcpyDeviceToHost),
               "cudaMemcpy(output)");
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
  if (device_instance != nullptr) cudaFree(device_instance);
  if (device_points != nullptr) cudaFree(device_points);
  if (device_states != nullptr) cudaFree(device_states);
  if (device_output != nullptr) cudaFree(device_output);
  std::free(host_output);
  std::free(host_reference);
  std::free(inputs.points);
  std::free(inputs.states);
  if (!ok) return 2;

  // Environment identity only.  No energy value is printed.
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
      "\"cuda_driver_version\":%d,\"cuda_runtime_version\":%d,\"device_count\":%d,"
      "\"device_index\":%d,\"device_name\":\"%s\",\"device_uuid_hex\":\"",
      properties.major, properties.minor, backend, properties.major, properties.minor,
      driver_version, runtime_version, device_count, selected_device, properties.name);
  print_uuid_hex(properties);
  std::printf(
      "\",\"device_vs_host_cxx_mismatches\":%u,\"evaluations\":%u,"
      "\"multiprocessor_count\":%d,\"nvcc_version\":\"%d.%d.%d\","
      "\"pci_bus_id\":%d,\"pci_device_id\":%d,\"pci_domain_id\":%d,\"point_count\":%u,"
      "\"probe\":\"unbalanced_energy_transcript_crosscheck_cuda\","
      "\"scientific_outputs\":\"intentionally absent\",\"state_count\":%u,"
      "\"total_global_memory_bytes\":%llu}\n",
      device_vs_host_mismatches, total, properties.multiProcessorCount, nvcc_major, nvcc_minor,
      nvcc_build, properties.pciBusID, properties.pciDeviceID, properties.pciDomainID,
      inputs.point_count, inputs.state_count,
      static_cast<unsigned long long>(properties.totalGlobalMem));
  return 0;
}
