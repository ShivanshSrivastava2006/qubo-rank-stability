// Non-production THROUGHPUT BENCHMARK harness for the reviewed unbalanced
// energy cross-check kernel.  Experimental Gate-6 GPU track only.
//
// This file adds nothing to the numerical transcript.  It textually includes
// the pinned cross-check program (gpu_unbalanced_energy_crosscheck.hip.cpp)
// with that program's `main` renamed, so the kernel, the transcript, the
// input loader, and the output writer are the very same source text the
// bit-exact cross-check compiles.  The harness only launches that kernel
// repeatedly on the same fixed inputs and records launch timings.
//
// It emits timings and counts on stdout, and raw bit patterns of the LAST
// launch to the output file so the Python runner can re-run the same
// comparator and reject the measurement if the profile is not bit-exact.
// No energy value, minimum, label, rate, or other scientific quantity is
// printed, and the repeated launches serve no purpose beyond timing.
//
// Numerical contract is inherited from the included source: binary64 only,
// `#pragma clang fp contract(off)` / `reassociate(off)`, explicit gfx1201
// device selection.  The optimisation level is chosen by the compile
// command; the Python runner permits exactly the profiles it declares.

// Headers first, so the `main` rename below can only affect the pinned
// source text itself, never a runtime or standard header.
#include <hip/hip_runtime.h>

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#define main crosscheck_program_main
#include "gpu_unbalanced_energy_crosscheck.hip.cpp"
#undef main

#pragma clang fp contract(off)
#pragma clang fp reassociate(off)

constexpr std::uint64_t kMaxWarmupLaunches = 100;
constexpr std::uint64_t kMaxTimedLaunches = 5000;

static bool parse_count(const char* text, const std::uint64_t maximum, std::uint64_t* value) {
  if (text == nullptr || *text == '\0') return false;
  std::uint64_t parsed = 0;
  for (const char* cursor = text; *cursor != '\0'; ++cursor) {
    if (*cursor < '0' || *cursor > '9') return false;
    const std::uint64_t digit = static_cast<std::uint64_t>(*cursor - '0');
    if (parsed > (maximum - digit) / 10) return false;
    parsed = parsed * 10 + digit;
  }
  if (parsed > maximum) return false;
  *value = parsed;
  return true;
}

int main(int argc, char** argv) {
  if (argc != 5) {
    std::fprintf(stderr, "usage: %s <input.words> <output.words> <warmup_launches> <timed_launches>\n",
                 argv[0]);
    return 64;
  }
  std::uint64_t warmup_launches = 0;
  std::uint64_t timed_launches = 0;
  if (!parse_count(argv[3], kMaxWarmupLaunches, &warmup_launches) ||
      !parse_count(argv[4], kMaxTimedLaunches, &timed_launches) || timed_launches == 0) {
    std::fprintf(stderr, "launch counts are outside the bounded benchmark contract\n");
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
    // Same explicit selection as the cross-check: never assume device zero.
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
  // Per-launch timings in milliseconds as reported by HIP events.  This is
  // the only fp32 quantity in the harness; it is a duration, never an energy.
  double* per_launch_ms = static_cast<double*>(std::calloc(timed_launches, sizeof(double)));
  bool ok = host_output != nullptr && host_reference != nullptr && per_launch_ms != nullptr;
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

  constexpr std::uint32_t block_size = 64;
  const std::uint32_t block_count = (total + block_size - 1) / block_size;
  hipEvent_t start_event = nullptr;
  hipEvent_t stop_event = nullptr;
  ok = ok && check(hipEventCreate(&start_event), "hipEventCreate(start)") &&
       check(hipEventCreate(&stop_event), "hipEventCreate(stop)");

  // Warm-up launches: identical work, excluded from every timing figure.
  for (std::uint64_t launch = 0; ok && launch < warmup_launches; ++launch) {
    hipLaunchKernelGGL(crosscheck_kernel, dim3(block_count), dim3(block_size), 0, 0,
                       device_instance, device_points, device_states, device_output,
                       inputs.point_count, inputs.state_count);
    ok = check(hipGetLastError(), "warm-up kernel launch") &&
         check(hipDeviceSynchronize(), "warm-up hipDeviceSynchronize");
  }

  // Synchronous per-launch timing: event, launch, event, wait.
  for (std::uint64_t launch = 0; ok && launch < timed_launches; ++launch) {
    ok = check(hipEventRecord(start_event, 0), "hipEventRecord(start)");
    hipLaunchKernelGGL(crosscheck_kernel, dim3(block_count), dim3(block_size), 0, 0,
                       device_instance, device_points, device_states, device_output,
                       inputs.point_count, inputs.state_count);
    ok = ok && check(hipGetLastError(), "timed kernel launch") &&
         check(hipEventRecord(stop_event, 0), "hipEventRecord(stop)") &&
         check(hipEventSynchronize(stop_event), "hipEventSynchronize(stop)");
    float elapsed_ms_f32 = 0.0f;
    ok = ok && check(hipEventElapsedTime(&elapsed_ms_f32, start_event, stop_event),
                     "hipEventElapsedTime");
    if (ok) per_launch_ms[launch] = static_cast<double>(elapsed_ms_f32);
  }

  // Back-to-back batch: the same number of launches queued without an
  // intermediate wait, timed by a host steady clock around one final
  // synchronisation.  Exposes launch overhead that the synchronous loop
  // cannot hide.
  double batch_wall_ms = 0.0;
  if (ok) {
    const auto batch_start = std::chrono::steady_clock::now();
    for (std::uint64_t launch = 0; ok && launch < timed_launches; ++launch) {
      hipLaunchKernelGGL(crosscheck_kernel, dim3(block_count), dim3(block_size), 0, 0,
                         device_instance, device_points, device_states, device_output,
                         inputs.point_count, inputs.state_count);
      ok = check(hipGetLastError(), "batch kernel launch");
    }
    ok = ok && check(hipDeviceSynchronize(), "batch hipDeviceSynchronize");
    const auto batch_stop = std::chrono::steady_clock::now();
    batch_wall_ms =
        std::chrono::duration<double, std::milli>(batch_stop - batch_start).count();
  }

  ok = ok && check(hipMemcpy(host_output, device_output, total * sizeof(std::uint64_t),
                             hipMemcpyDeviceToHost),
                   "hipMemcpy(output)");

  // Host C++ transcript of the same function on the same inputs, as triage
  // evidence only.  The Python evaluator remains the reference.
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
  if (start_event != nullptr) hipEventDestroy(start_event);
  if (stop_event != nullptr) hipEventDestroy(stop_event);
  if (device_instance != nullptr) hipFree(device_instance);
  if (device_points != nullptr) hipFree(device_points);
  if (device_states != nullptr) hipFree(device_states);
  if (device_output != nullptr) hipFree(device_output);
  std::free(host_output);
  std::free(host_reference);
  std::free(inputs.points);
  std::free(inputs.states);
  if (!ok) {
    std::free(per_launch_ms);
    return 2;
  }

  std::printf(
      "{\"architecture\":\"%s\",\"batch_launches\":%llu,\"batch_wall_ms\":%.6f,"
      "\"block_count\":%u,\"block_size\":%u,\"device_index\":%d,\"device_name\":\"%s\","
      "\"device_vs_host_cxx_mismatches\":%u,\"evaluations_per_launch\":%u,"
      "\"per_launch_ms\":[",
      properties.gcnArchName, static_cast<unsigned long long>(timed_launches), batch_wall_ms,
      block_count, block_size, selected_device, properties.name, device_vs_host_mismatches,
      total);
  for (std::uint64_t launch = 0; launch < timed_launches; ++launch) {
    std::printf("%s%.6f", launch == 0 ? "" : ",", per_launch_ms[launch]);
  }
  std::printf(
      "],\"point_count\":%u,\"probe\":\"unbalanced_energy_transcript_benchmark\","
      "\"scientific_outputs\":\"intentionally absent\",\"state_count\":%u,"
      "\"timed_launches\":%llu,\"warmup_launches\":%llu}\n",
      inputs.point_count, inputs.state_count, static_cast<unsigned long long>(timed_launches),
      static_cast<unsigned long long>(warmup_launches));
  std::free(per_launch_ms);
  return 0;
}
