// Synthetic CUDA stable tie-compaction self-test — transport only.
//
// This source is independent of stage2_cuda_generic_engine.cu,
// stage2_cuda_preparation_selftest.cu and stage2_cuda_membership_adapter.cu.
// It computes no energy, no minimum, no tie threshold, no label and no rate:
// its input is a fixed synthetic table of canonical decoded indices with
// already-computed packed nested D015-like flags, and --self-test prints
// checksums and counters only.  It has no instance reader, no ledger reader,
// no output writer and no production mode.
//
// Flags are nested by construction (the D015 tolerance grows with c_H), so the
// only legal values are 0, 4 (4096), 6 (2048+4096) and 7 (1024+2048+4096).
// Anything else is counted as an illegal flag, and a tighter bit set without
// its containing looser bit is additionally counted as a nesting violation.
//
// Stable compaction contract: count flagged entries per fixed contiguous
// chunk, form exclusive offsets in ascending chunk order, then let each chunk
// write its flagged entries in ascending local order.  No atomics, no shared
// memory, no sorting, and no dependence on thread scheduling: every chunk owns
// a disjoint output range fixed before the write.  The transported word is
// (flags << 32) | canonical_index; the self-test never prints or retains the
// compacted indices themselves, only a checksum and counters over them.

#include <cuda_runtime.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#pragma STDC FP_CONTRACT OFF

#if defined(__CUDACC__)
#define G9_TIE_LAUNCH(kernel, grid, block, ...) kernel<<<grid, block>>>(__VA_ARGS__)
#else
#define G9_TIE_LAUNCH(kernel, grid, block, ...) g6_host_emulation_launch(kernel, grid, block, __VA_ARGS__)
#endif

constexpr std::uint32_t kStateCount = 257;
constexpr std::uint32_t kChunkSize = 32;
constexpr std::uint32_t kChunkCount = (kStateCount + kChunkSize - 1u) / kChunkSize;
constexpr std::uint32_t kIndexStride = 4073;
constexpr std::uint32_t kCHCount = 3;
constexpr std::uint32_t kForcedEmptyChunk = 5;
constexpr std::uint32_t kBlockSize = 64;
constexpr std::uint64_t kSentinel = ~0ULL;
constexpr std::uint64_t kFNVOffset = 1469598103934665603ULL;
constexpr std::uint64_t kFNVPrime = 1099511628211ULL;

struct ChunkAudit {
  std::uint32_t flagged;
  std::uint32_t illegal;
  std::uint32_t nesting;
  std::uint32_t per_ch[kCHCount];
};

struct StreamAudit {
  std::uint32_t order_violations;
  std::uint32_t duplicate_entries;
  std::uint32_t unwritten_slots;
  std::uint32_t sentinel_violations;
  std::uint32_t direct_flagged_total;
};

__host__ __device__ static bool flag_is_legal(const std::uint32_t flags) {
  return flags == 0u || flags == 4u || flags == 6u || flags == 7u;
}

__host__ __device__ static bool flag_violates_nesting(const std::uint32_t flags) {
  const bool tied_1024 = (flags & 1u) != 0u;
  const bool tied_2048 = (flags & 2u) != 0u;
  const bool tied_4096 = (flags & 4u) != 0u;
  return (tied_1024 && !tied_2048) || (tied_2048 && !tied_4096);
}

// The transported word: flags in the high half, canonical index in the low half.
__host__ __device__ static std::uint64_t compact_word(const std::uint32_t index, const std::uint32_t flags) {
  return (static_cast<std::uint64_t>(flags) << 32) | static_cast<std::uint64_t>(index);
}

// Count flagged entries and flag defects for one fixed contiguous chunk.
__global__ void chunk_count_kernel(const std::uint32_t* flags, ChunkAudit* audits) {
  const std::uint32_t chunk = blockIdx.x * blockDim.x + threadIdx.x;
  if (chunk >= kChunkCount) return;
  ChunkAudit local{};
  const std::uint32_t start = chunk * kChunkSize;
  std::uint32_t span = kChunkSize;
  if (start + span > kStateCount) span = kStateCount - start;
  for (std::uint32_t scan = 0; scan < span; ++scan) {
    const std::uint32_t value = flags[start + scan];
    if (value != 0u) local.flagged += 1u;
    if (!flag_is_legal(value)) local.illegal += 1u;
    if (flag_violates_nesting(value)) local.nesting += 1u;
    for (std::uint32_t bit = 0; bit < kCHCount; ++bit) {
      if ((value & (1u << bit)) != 0u) local.per_ch[bit] += 1u;
    }
  }
  audits[chunk] = local;
}

// One deterministic serial thread forms the exclusive prefix in ascending
// chunk order; offsets[kChunkCount] is the total.  No atomics, no scan tree.
__global__ void prefix_kernel(const ChunkAudit* audits, std::uint32_t* offsets) {
  if (blockIdx.x * blockDim.x + threadIdx.x != 0u) return;
  std::uint32_t running = 0u;
  offsets[0] = 0u;
  for (std::uint32_t prefix_chunk = 0; prefix_chunk < kChunkCount; ++prefix_chunk) {
    running = running + audits[prefix_chunk].flagged;
    offsets[prefix_chunk + 1u] = running;
  }
}

// Each chunk writes its flagged entries into its own disjoint output range, in
// ascending local order, so the stream is ascending by canonical index.
__global__ void compact_kernel(const std::uint32_t* indices, const std::uint32_t* flags,
                               const std::uint32_t* offsets, std::uint64_t* output) {
  const std::uint32_t chunk = blockIdx.x * blockDim.x + threadIdx.x;
  if (chunk >= kChunkCount) return;
  const std::uint32_t start = chunk * kChunkSize;
  std::uint32_t span = kChunkSize;
  if (start + span > kStateCount) span = kStateCount - start;
  std::uint32_t cursor = offsets[chunk];
  for (std::uint32_t local = 0; local < span; ++local) {
    const std::uint32_t position = start + local;
    const std::uint32_t entry_flags = flags[position];
    if (entry_flags != 0u) {
      output[cursor] = compact_word(indices[position], entry_flags);
      cursor = cursor + 1u;
    }
  }
}

// One serial thread audits ordering, duplicates and the untouched tail.
__global__ void stream_audit_kernel(const std::uint32_t* flags, const std::uint64_t* output,
                                    const std::uint32_t* offsets, StreamAudit* audit) {
  if (blockIdx.x * blockDim.x + threadIdx.x != 0u) return;
  StreamAudit local{};
  for (std::uint32_t position = 0; position < kStateCount; ++position) {
    if (flags[position] != 0u) local.direct_flagged_total += 1u;
  }
  const std::uint32_t total = offsets[kChunkCount];
  bool has_previous = false;
  std::uint32_t previous = 0u;
  for (std::uint32_t slot = 0; slot < total; ++slot) {
    const std::uint64_t word = output[slot];
    if (word == kSentinel) {
      local.unwritten_slots += 1u;
      continue;
    }
    const std::uint32_t index = static_cast<std::uint32_t>(word & 0xFFFFFFFFULL);
    if (has_previous) {
      if (index == previous) local.duplicate_entries += 1u;
      if (index <= previous) local.order_violations += 1u;
    }
    previous = index;
    has_previous = true;
  }
  for (std::uint32_t slot = total; slot < kStateCount; ++slot) {
    if (output[slot] != kSentinel) local.sentinel_violations += 1u;
  }
  *audit = local;
}

static std::uint64_t fnv_word(const std::uint64_t state, const std::uint64_t word) {
  return (state ^ word) * kFNVPrime;
}

static std::uint32_t synthetic_index(const std::uint32_t position) {
  return position * kIndexStride;
}

// Fixed deterministic legal flag pattern; no result is consulted.  Chunk 5 and
// the final partial chunk are deliberately empty.
static std::uint32_t synthetic_flags(const std::uint32_t position) {
  if (position / kChunkSize == kForcedEmptyChunk || position == kStateCount - 1u) return 0u;
  if (position % 7u == 3u) return 7u;
  if (position % 5u == 2u) return 6u;
  if (position % 11u == 4u) return 4u;
  return 0u;
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

  std::uint32_t host_indices[kStateCount]{};
  std::uint32_t host_flags[kStateCount]{};
  std::uint64_t host_output[kStateCount]{};
  for (std::uint32_t position = 0; position < kStateCount; ++position) {
    host_indices[position] = synthetic_index(position);
    host_flags[position] = synthetic_flags(position);
    host_output[position] = kSentinel;
  }

  std::uint32_t* device_indices = nullptr;
  std::uint32_t* device_flags = nullptr;
  std::uint32_t* device_offsets = nullptr;
  std::uint64_t* device_output = nullptr;
  ChunkAudit* device_audits = nullptr;
  StreamAudit* device_stream_audit = nullptr;
  bool ok = cudaMalloc(&device_indices, sizeof(host_indices)) == cudaSuccess &&
            cudaMalloc(&device_flags, sizeof(host_flags)) == cudaSuccess &&
            cudaMalloc(&device_offsets, sizeof(std::uint32_t) * (kChunkCount + 1u)) == cudaSuccess &&
            cudaMalloc(&device_output, sizeof(host_output)) == cudaSuccess &&
            cudaMalloc(&device_audits, sizeof(ChunkAudit) * kChunkCount) == cudaSuccess &&
            cudaMalloc(&device_stream_audit, sizeof(StreamAudit)) == cudaSuccess;
  ok = ok && cudaMemcpy(device_indices, host_indices, sizeof(host_indices), cudaMemcpyHostToDevice) == cudaSuccess &&
       cudaMemcpy(device_flags, host_flags, sizeof(host_flags), cudaMemcpyHostToDevice) == cudaSuccess &&
       cudaMemcpy(device_output, host_output, sizeof(host_output), cudaMemcpyHostToDevice) == cudaSuccess;
  if (ok) G9_TIE_LAUNCH(chunk_count_kernel, dim3((kChunkCount + kBlockSize - 1u) / kBlockSize), dim3(kBlockSize),
                        device_flags, device_audits);
  if (ok) G9_TIE_LAUNCH(prefix_kernel, dim3(1), dim3(1), device_audits, device_offsets);
  if (ok) G9_TIE_LAUNCH(compact_kernel, dim3((kChunkCount + kBlockSize - 1u) / kBlockSize), dim3(kBlockSize),
                        device_indices, device_flags, device_offsets, device_output);
  if (ok) G9_TIE_LAUNCH(stream_audit_kernel, dim3(1), dim3(1), device_flags, device_output, device_offsets,
                        device_stream_audit);
  ok = ok && cudaGetLastError() == cudaSuccess && cudaDeviceSynchronize() == cudaSuccess;

  ChunkAudit host_audits[kChunkCount]{};
  StreamAudit host_stream_audit{};
  std::uint32_t host_offsets[kChunkCount + 1u]{};
  ok = ok && cudaMemcpy(host_audits, device_audits, sizeof(host_audits), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(host_offsets, device_offsets, sizeof(host_offsets), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(host_output, device_output, sizeof(host_output), cudaMemcpyDeviceToHost) == cudaSuccess &&
       cudaMemcpy(&host_stream_audit, device_stream_audit, sizeof(host_stream_audit), cudaMemcpyDeviceToHost) == cudaSuccess;

  std::uint64_t input_checksum = kFNVOffset;
  std::uint64_t offsets_checksum = kFNVOffset;
  std::uint64_t compacted_checksum = kFNVOffset;
  std::uint32_t illegal_flag_entries = 0;
  std::uint32_t nesting_violations = 0;
  std::uint32_t per_ch[kCHCount] = {0u, 0u, 0u};
  if (ok) {
    for (std::uint32_t position = 0; position < kStateCount; ++position) {
      input_checksum = fnv_word(input_checksum, host_indices[position]);
      input_checksum = fnv_word(input_checksum, host_flags[position]);
    }
    for (std::uint32_t chunk = 0; chunk < kChunkCount; ++chunk) {
      offsets_checksum = fnv_word(offsets_checksum, host_audits[chunk].flagged);
      illegal_flag_entries += host_audits[chunk].illegal;
      nesting_violations += host_audits[chunk].nesting;
      for (std::uint32_t bit = 0; bit < kCHCount; ++bit) per_ch[bit] += host_audits[chunk].per_ch[bit];
    }
    for (std::uint32_t chunk = 0; chunk <= kChunkCount; ++chunk) {
      offsets_checksum = fnv_word(offsets_checksum, host_offsets[chunk]);
    }
    const std::uint32_t total = host_offsets[kChunkCount];
    for (std::uint32_t slot = 0; slot < total; ++slot) {
      compacted_checksum = fnv_word(compacted_checksum, host_output[slot]);
    }
    const std::uint32_t total_mismatch = total == host_stream_audit.direct_flagged_total ? 0u : 1u;
    const bool nested_counts = per_ch[0] <= per_ch[1] && per_ch[1] <= per_ch[2] && per_ch[2] == total;
    const bool pass = illegal_flag_entries == 0u && nesting_violations == 0u && total_mismatch == 0u &&
                      host_stream_audit.order_violations == 0u && host_stream_audit.duplicate_entries == 0u &&
                      host_stream_audit.unwritten_slots == 0u && host_stream_audit.sentinel_violations == 0u &&
                      nested_counts;
    std::printf("{\"schema\":\"decisions_os/g9_cuda_tie_transport_self_test/v1\",\"device_index\":%d,\"device_name\":\"%s\",\"state_count\":%u,\"chunk_size\":%u,\"chunk_count\":%u,\"input_checksum\":\"%016llx\",\"offsets_checksum\":\"%016llx\",\"compacted_checksum\":\"%016llx\",\"compacted_total\":%u,\"direct_flagged_total\":%u,\"total_mismatch\":%u,\"count_c_h_1024\":%u,\"count_c_h_2048\":%u,\"count_c_h_4096\":%u,\"illegal_flag_entries\":%u,\"nesting_violations\":%u,\"order_violations\":%u,\"duplicate_entries\":%u,\"unwritten_slots\":%u,\"sentinel_violations\":%u,\"scientific_outputs\":\"intentionally absent\",\"verdict\":\"%s\"}\n",
                selected, property.name, kStateCount, kChunkSize, kChunkCount,
                static_cast<unsigned long long>(input_checksum),
                static_cast<unsigned long long>(offsets_checksum),
                static_cast<unsigned long long>(compacted_checksum),
                total, host_stream_audit.direct_flagged_total, total_mismatch,
                per_ch[0], per_ch[1], per_ch[2], illegal_flag_entries, nesting_violations,
                host_stream_audit.order_violations, host_stream_audit.duplicate_entries,
                host_stream_audit.unwritten_slots, host_stream_audit.sentinel_violations,
                pass ? "pass" : "fail");
    ok = ok && pass;
  }
  cudaFree(device_indices);
  cudaFree(device_flags);
  cudaFree(device_offsets);
  cudaFree(device_output);
  cudaFree(device_audits);
  cudaFree(device_stream_audit);
  return ok;
}

int main(int argc, char** argv) {
  if (argc != 2 || std::strcmp(argv[1], "--self-test") != 0) {
    std::fprintf(stderr, "usage: stage2_cuda_tie_transport --self-test\n");
    return 2;
  }
  if (!run_self_test()) {
    std::fprintf(stderr, "FAIL Stage-2 tie-transport self-test\n");
    return 1;
  }
  return 0;
}
