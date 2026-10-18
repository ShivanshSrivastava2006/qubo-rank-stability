// C ABI for the generic core, compiled in the SAME translation unit as the
// reviewed numerical source. No parser, file access, instance input, or GPU
// qualification is performed by this source alone. The host constructs the
// ABI structs from one validated input frame and verifies the computed offset
// table after the call. This wrapper is deliberately serial/non-reentrant.

#include <cstddef>
#define main g9_core_embedded_self_test_main
#include "stage2_cuda_core_stream_engine.cu"
#undef main

static bool g9_last_core_success = false;

extern "C" std::uint32_t g9_core_backend_v1() {
#if defined(__CUDACC__)
  return 1u;
#else
  return 0u;
#endif
}

static bool g9_coefficients_valid(const CoefficientData& row) {
  const double values[7] = {row.alpha, row.sector_slack, row.budget_slack,
                            row.sector_linear, row.sector_quadratic,
                            row.budget_linear, row.budget_quadratic};
  for (std::uint32_t i = 0; i < 7u; ++i) {
    if (value_is_nonfinite(values[i])) return false;
  }
  return row.sector_slack > 0.0 && row.budget_slack > 0.0;
}

extern "C" std::uint32_t g9_core_abi_layout_v1(std::uint64_t* values, std::uint32_t capacity) {
  if (values == nullptr || capacity != 26u) return 0u;
  const std::uint64_t layout[26] = {
    sizeof(PayloadData), sizeof(CoefficientData), sizeof(ScanResult), sizeof(CoreOutput),
    offsetof(PayloadData, mu), offsetof(PayloadData, sigma),
    offsetof(PayloadData, prices), offsetof(PayloadData, kappa_risk),
    offsetof(PayloadData, k_value), offsetof(PayloadData, c_value),
    offsetof(PayloadData, b), offsetof(PayloadData, lambda_ref),
    offsetof(PayloadData, membership),
    offsetof(ScanResult, word_count), offsetof(ScanResult, per_ch),
    offsetof(ScanResult, illegal), offsetof(ScanResult, compacted_count),
    offsetof(ScanResult, compaction_checksum), offsetof(ScanResult, compaction_chunks),
    offsetof(ScanResult, natural_minimum_checksum), offsetof(ScanResult, minimum),
    offsetof(ScanResult, minimum_index), offsetof(ScanResult, entries),
    offsetof(CoreOutput, results), offsetof(CoreOutput, lift_total),
    offsetof(CoreOutput, row_count),
  };
  std::memcpy(values, layout, sizeof(layout));
  return 26u;
}

extern "C" std::uint32_t g9_core_run_v1(const PayloadData* payload,
                                         const CoefficientData* rows,
                                         std::uint32_t row_count, CoreOutput* output) {
  g9_last_core_success = false;
  if (payload == nullptr || rows == nullptr || output == nullptr ||
      row_count == 0u || row_count > kRowCount) return 0u;
  // The numerical core casts integral C to long long. Refuse finite values
  // outside that range before reaching the cast (a malformed frame must not
  // trigger undefined behaviour even if Python would accept its float).
  if (value_is_nonfinite(payload->c_value) || payload->c_value < 0.0 ||
      !(payload->c_value < 0x1p63)) return 0u;
  if (!(payload->k_value > 0.0) || !validate_payload_contract(*payload)) return 0u;
  for (std::uint32_t i = 0; i < kAssetCount; ++i) {
    for (std::uint32_t j = i + 1u; j < kAssetCount; ++j) {
      if (payload->sigma[i * kAssetCount + j] !=
          payload->sigma[j * kAssetCount + i]) return 0u;
    }
  }
  for (std::uint32_t row = 0; row < row_count; ++row) {
    if (!g9_coefficients_valid(rows[row])) return 0u;
  }
  if (!run_core(*payload, rows, row_count, nullptr, nullptr, output)) return 0u;
  if (output->row_count != row_count || output->invalid_registers != 0u) return 0u;
  g9_last_core_success = true;
  return 1u;
}

extern "C" std::uint32_t g9_core_copy_offsets_v1(std::uint64_t* destination,
                                                  std::uint64_t capacity) {
  if (!g9_last_core_success || destination == nullptr ||
      capacity != kStateCount + 1ULL) return 0u;
  std::memcpy(destination, g_offsets, sizeof(g_offsets));
  return 1u;
}
