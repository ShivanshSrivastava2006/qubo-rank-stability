// Version-2 C ABI sidecar for the generic core: ONE call returns the bounded
// CoreOutput AND the STATE_COUNT + 1 slack offsets computed by that same call.
//
// OFFLINE / SYNTHETIC-ONLY DRAFT.  This file does not replace or modify the
// accepted version-1 wrapper (stage2_cuda_core_bridge.cu), which stays
// byte-identical.  It is compiled in the SAME translation unit as the
// unchanged reviewed numerical source, but it is a different source/ABI:
// using it on a GPU requires a fresh, separately approved §A qualification.
// Nothing here compiles CUDA, selects a device, reads a Stage-2 input, or
// establishes an executing-image identity.  Gate-9 §B remains open.
//
// Transaction contract (design draft §2):
//   * the only run export is g9_core_run_v2; there is no separate
//     offset-copy export and no process-global "last call succeeded" flag;
//   * one process-wide std::atomic_flag guards every entry into run_core and
//     its process-global host arrays.  A second entry while a call is in
//     flight -- another thread, a direct C caller that bypasses Python, or a
//     re-entrant call -- is refused with G9_CORE_V2_BUSY before anything is
//     read or written, and its caller buffers are left untouched;
//   * the embedded self-test entry point is given internal linkage below, so
//     it cannot be reached from outside this library to bypass the guard;
//   * success (G9_CORE_V2_OK) is returned only after BOTH the bounded output
//     and the complete offset table are written from this invocation;
//   * every other status means "discard both buffers".  When the guard was
//     held and the argument buffers were usable, a failed call also scrubs
//     both caller buffers to all-zero bytes, so a partially built or stale
//     result can never look accepted to a caller that ignores the status.
//
// This is not multi-word atomicity on the device: the core runs several
// kernels and copies and assembles CoreOutput on the host.  The guard only
// serializes callers inside one process.  It proves nothing about which
// binary or device produced the numbers.

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstring>
// Internal linkage for the embedded self-test entry point: the core's
// `int main(int, char**)` becomes a static, unexported function here.
#define main static g9_core_v2_embedded_self_test_main [[maybe_unused]]
#include "stage2_cuda_core_stream_engine.cu"
#undef main

enum : std::uint32_t {
  G9_CORE_V2_REFUSED = 0u,  // failed or refused; discard both buffers
  G9_CORE_V2_OK = 1u,       // bounded output and offsets from this call
  G9_CORE_V2_BUSY = 2u,     // another call holds the guard; nothing touched
};

// std::atomic_flag is the one type the C++ standard guarantees lock-free.
// Constant-initialized before any caller can run; never re-initialized.
static std::atomic_flag g9_core_v2_busy = ATOMIC_FLAG_INIT;

namespace {

class G9CoreV2Guard {
 public:
  G9CoreV2Guard() : held_(!g9_core_v2_busy.test_and_set(std::memory_order_acquire)) {}
  ~G9CoreV2Guard() {
    if (held_) g9_core_v2_busy.clear(std::memory_order_release);
  }
  G9CoreV2Guard(const G9CoreV2Guard&) = delete;
  G9CoreV2Guard& operator=(const G9CoreV2Guard&) = delete;
  bool held() const { return held_; }

 private:
  const bool held_;
};

bool g9_v2_coefficients_valid(const CoefficientData& row) {
  const double values[7] = {row.alpha, row.sector_slack, row.budget_slack,
                            row.sector_linear, row.sector_quadratic,
                            row.budget_linear, row.budget_quadratic};
  for (std::uint32_t i = 0; i < 7u; ++i) {
    if (value_is_nonfinite(values[i])) return false;
  }
  return row.sector_slack > 0.0 && row.budget_slack > 0.0;
}

bool g9_v2_disjoint(const void* first, const std::size_t first_bytes,
                    const void* second, const std::size_t second_bytes) {
  const std::uintptr_t a = reinterpret_cast<std::uintptr_t>(first);
  const std::uintptr_t b = reinterpret_cast<std::uintptr_t>(second);
  return a + first_bytes <= b || b + second_bytes <= a;
}

// Runs only while the guard is held.  Writes the caller buffers only on
// success; the exported wrapper scrubs them on any failure.
bool g9_v2_run_locked(const PayloadData* payload, const CoefficientData* rows,
                      const std::uint32_t row_count, CoreOutput* output,
                      std::uint64_t* offsets) {
  // Same refusals as the version-1 wrapper, before any cast or launch.
  if (value_is_nonfinite(payload->c_value) || payload->c_value < 0.0 ||
      !(payload->c_value < 0x1p63)) return false;
  if (!(payload->k_value > 0.0) || !validate_payload_contract(*payload)) return false;
  for (std::uint32_t i = 0; i < kAssetCount; ++i) {
    for (std::uint32_t j = i + 1u; j < kAssetCount; ++j) {
      if (payload->sigma[i * kAssetCount + j] !=
          payload->sigma[j * kAssetCount + i]) return false;
    }
  }
  for (std::uint32_t row = 0; row < row_count; ++row) {
    if (!g9_v2_coefficients_valid(rows[row])) return false;
  }
  if (!run_core(*payload, rows, row_count, nullptr, nullptr, output)) return false;
  // g_offsets was rebuilt by THIS run_core call under the guard.
  if (output->row_count != row_count || output->invalid_registers != 0u ||
      g_offsets[0] != 0ULL || g_offsets[kStateCount] != output->lift_total) return false;
  std::memcpy(offsets, g_offsets, sizeof(g_offsets));
  return true;
}

}  // namespace

extern "C" std::uint32_t g9_core_backend_v2() {
#if defined(__CUDACC__)
  return 1u;
#else
  return 0u;
#endif
}

// Same 26-value struct layout as version 1 (the structs are unchanged), plus
// the offset-table word count and byte size that v2 callers must supply.
extern "C" std::uint32_t g9_core_abi_layout_v2(std::uint64_t* values, std::uint32_t capacity) {
  if (values == nullptr || capacity != 28u) return 0u;
  const std::uint64_t layout[28] = {
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
    kStateCount + 1ULL, sizeof(g_offsets),
  };
  std::memcpy(values, layout, sizeof(layout));
  return 28u;
}

extern "C" std::uint32_t g9_core_run_v2(const PayloadData* payload,
                                         const CoefficientData* rows,
                                         std::uint32_t row_count, CoreOutput* output,
                                         std::uint64_t* offsets, std::uint64_t capacity) {
  // Argument shape only: no shared state is read, no buffer is written.
  if (payload == nullptr || rows == nullptr || output == nullptr || offsets == nullptr ||
      row_count == 0u || row_count > kRowCount || capacity != kStateCount + 1ULL) {
    return G9_CORE_V2_REFUSED;
  }
  const std::size_t rows_bytes = sizeof(CoefficientData) * row_count;
  if (!g9_v2_disjoint(output, sizeof(CoreOutput), offsets, sizeof(g_offsets)) ||
      !g9_v2_disjoint(output, sizeof(CoreOutput), payload, sizeof(PayloadData)) ||
      !g9_v2_disjoint(output, sizeof(CoreOutput), rows, rows_bytes) ||
      !g9_v2_disjoint(offsets, sizeof(g_offsets), payload, sizeof(PayloadData)) ||
      !g9_v2_disjoint(offsets, sizeof(g_offsets), rows, rows_bytes)) {
    return G9_CORE_V2_REFUSED;
  }
  const G9CoreV2Guard guard;
  if (!guard.held()) return G9_CORE_V2_BUSY;
  if (g9_v2_run_locked(payload, rows, row_count, output, offsets)) return G9_CORE_V2_OK;
  std::memset(static_cast<void*>(output), 0, sizeof(CoreOutput));
  std::memset(offsets, 0, sizeof(g_offsets));
  return G9_CORE_V2_REFUSED;
}
