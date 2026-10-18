// D013 INACTIVE-FAMILY (`+0.0`) ADDITIVE CUDA PATH -- OFFLINE / SYNTHETIC-ONLY DRAFT.
//
// ============================ CANDIDATE v2 (NOT APPROVED) ================
// Derived from the approved v1 source by an enumerated, auditable edit set;
// the v1 file itself is preserved byte-identically and is NOT modified.
//
// WHAT THIS CANDIDATE CHANGES (device-pointer staging only; no numerical,
// guard, ABI, status-code, counter or refusal-path change):
//   v1 `g9_d013_run` launched all three D013 kernels with the CALLER'S HOST
//   pointer `payload`, and launched `segment_kernel`/`flags_kernel` with the
//   HOST `energies` array. The qualified v1 core stages the equivalent
//   structures to device memory first (`stage2_cuda_core_stream_engine.cu`
//   :583 `cudaMalloc(&device_payload,...)`, :590 `cudaMemcpy(...HostToDevice)`,
//   :593/:686 launch with `device_payload`, :733/:757 launch segment/flags
//   with `device_energies`). A device kernel cannot dereference a host
//   pointer, so the v1 D013 build faults on its first launch and the run
//   collapses to the single post-allocation `ok == false` return.
//   This candidate therefore adds the MINIMAL device staging the core
//   already performs, so the three D013 kernels receive a DEVICE payload
//   pointer and the two unchanged core kernels receive a DEVICE energy
//   pointer. Both are allocated, copied and freed exactly once.
//
//   NOTE ON `payload->lambda_ref` at the `flags_kernel` launch: that scalar
//   is still read from the validated HOST payload, exactly as in v1. It is
//   a host-side scalar kernel argument (passed BY VALUE, not dereferenced
//   in the kernel body), so it is not a device-pointer defect. It is left
//   untouched deliberately to keep this candidate minimal and to avoid any
//   appearance of changing v1 numerics; recorded here as a reviewed,
//   explicit, non-defect rather than silently altered.
//
// EVIDENCE STATUS -- READ THIS BEFORE QUOTING ANY RESULT:
//   * STATIC/CPU EVIDENCE ONLY. These edits are proven by source inspection
//     plus a synthetic host-stub (g++ / `cudaMalloc = malloc`) run on CPU.
//   * NO T4 / GPU CONFIRMATION EXISTS. No nvcc, no CUDA device and no
//     /dev/nvidia* were available. The claim that the v1 host-pointer
//     launch is the cause of the observed T4 REFUSED remains a STRONG
//     STATIC INFERENCE, and the claim that this candidate fixes it on real
//     hardware is UNVERIFIED. Only a T4 run can settle either.
//
// This candidate is NOT owner-approved, is NOT bound by any release, source
// map, runtime config or bundle, and is NOT routed by the accepted
// launcher. It cannot execute without a NEW owner-reviewed release.
// =======================================================================
//
// Authority:
//   * research/decisions/GATE_9_WP0_D013_CUDA_PATH_AND_IDENTITY_SCOPE_OWNER_DECISION.md
//     decision 1: the `+0.0` capability is built in NEW files; all 12 files of
//     the qualified v1 release stay byte-identical; this path needs its own
//     section-A corruption qualification, including new `+0.0` and
//     slack-register cases.
//   * research/decisions/GATE_9_D013_INACTIVE_EVALUATOR_SPEC_OWNER_DECISION.md:
//     per-condition F_q; an empty F_q is a typed hard stop; |T_E| is an exact
//     integer computed arithmetically as base * 2^w and recorded with its
//     factors (base, w).
//   * research/g9/GATE_9_WP6_D013_SPEC_GAP_DRAFT.md part 1: `C` inactivates
//     sector+budget, `CB` inactivates sector, `CS` inactivates budget,
//     cardinality is never inactive, the inactive register is RETAINED with
//     coefficient exactly `+0.0`, and the accumulation order is f, P_card,
//     sector j = 1..4, budget.
//
// v1 refuses this case BEFORE any compute: stage2_cuda_core_bridge.cu:29 and
// stage2_cuda_core_stream_engine.py:274-275 both require
// `sector_slack > 0.0 && budget_slack > 0.0`.  That refusal is deliberate
// (src/g5/domains.py:6-8 says an inactive family "must build a different,
// coefficient-dependent domain; this module therefore rejects inactive
// coefficients rather than reusing this cache") and is NOT relaxed here.  This
// file is a SEPARATE translation unit with its own entry point and its own ABI;
// the v1 sources are only #included, and the included numerical helpers
// (objective_of, card_square_of, residuals_of, register_minimizers, the
// segment/flag/compaction kernels and their frozen rules) are unchanged.
//
// ---------------------------------------------------------------------------
// THE TWO HAZARDS THIS PATH EXISTS TO HANDLE
// ---------------------------------------------------------------------------
//
// (1) SIGN.  The unchanged v1 slack transcript computes
//         h = h + (sector_slack * penalties[..])
//     (stream_engine.cu ~:301/:307).  With coefficient `+0.0` and a NEGATIVE
//     penalty the product is `-0.0`, and IEEE 754 says `-0.0 + -0.0 == -0.0`:
//     the accumulator would take the sign of the inactive term.  D015 section
//     1.4 requires that adding `+0.0` "must not perturb the accumulator, and
//     must not introduce -0.0".  An inactive family is therefore SKIPPED
//     ENTIRELY here: the product `coefficient * penalty` is never formed, so no
//     negative penalty can reach the accumulator.  The skipped step is
//     `H_acc = fl(H_acc + P_E)` with `P_E` exactly `+0.0`, and `fl(h + +0.0)`
//     is `h` for every `h` other than `-0.0`.  The probe kernel below asserts
//     the reported `P_E` word of every inactive family is `0`, and the energy
//     transcript can therefore never contain the inactive term's sign.
//
// (2) DOMAIN SIZE.  With a zero coefficient EVERY value of the retained
//     register is an exact lift, so enumerating lifts multiplies the domain by
//     2^w (w = 2 per inactive sector register, 8 for all four; 11 for budget).
//     The inactive family's register is accounted for SYMBOLICALLY instead:
//     the base stream enumerates only the ACTIVE registers (an ACTIVE sector
//     register is never tied, because the declared integral-C contract makes
//     every sector residual an integer, so each has exactly one minimizer; an
//     ACTIVE budget register has one or two), and the inactive factor 2^w is
//     applied ONCE, arithmetically, to form the exact integer
//     `lift_total_exact = base * 2^w`, which is |C_E|, the WHOLE-DOMAIN
//     count.  It is NOT |T_E|.  |T_E| counts the TIED candidates only and is
//     formed, per result row, as `tie_count * 2^w` with factors
//     `(tie_count, w)`, where `tie_count` is the frozen D015 c_H = 2048 count
//     the tie transcript already reports in `per_ch[1]`.  Both are arithmetic
//     and neither ever enumerates the retained register.
//     `counters.inactive_register_visits` is
//     the instrumented counter that must be 0: it folds the per-register visit
//     table, so a single read of an inactive register's minimiser is visible.
//
// ---------------------------------------------------------------------------
// WHAT THIS DOES NOT DO
// ---------------------------------------------------------------------------
// No nvcc, no device selection, no Stage-2 input, no instance, no record, no
// scientific value, and no claim about which binary or GPU produced anything.
// The host stub compiles the unchanged numerical core in this same translation
// unit with g++; a CUDA build of this file would need its own separate,
// separately approved section-A qualification.  Gate-9 section B remains OPEN.
//
// The D015 tie transcript, the strict first-seen minimum, the deterministic
// stable compaction and the bounded D016 reconstruction inputs are the
// UNCHANGED v1 code, reached through a driver whose terms/energy stages are this
// file's.  The only thing this path adds is the `+0.0` family handling and the
// symbolic inactive factor; requirement (a) of the build -- that CSB reproduce
// the unchanged v1 core bit for bit -- is exactly that claim.

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstring>

// The unchanged reviewed numerical source, compiled in THIS translation unit.
// `main` becomes an internal, unexported function so the embedded self-test
// entry point cannot be reached from outside this library.
#define main static g9_d013_embedded_self_test_main [[maybe_unused]]
#include "stage2_cuda_core_stream_engine.cu"
#undef main

enum : std::uint32_t {
  G9_D013_REFUSED = 0u,  // failed or refused; discard the buffer
  G9_D013_OK = 1u,       // output is entirely from this call
  G9_D013_BUSY = 2u,     // another call holds the guard; nothing touched
};

enum : std::uint32_t {
  G9_D013_ACTIVITY_SECTOR = 1u << 0,
  G9_D013_ACTIVITY_BUDGET = 1u << 1,
  G9_D013_ACTIVITY_MASK = G9_D013_ACTIVITY_SECTOR | G9_D013_ACTIVITY_BUDGET,
  // Condition codes, as a mask of WHICH FAMILIES ARE ACTIVE:
  //   C   -> neither family active (code 0)
  //   CB  -> budget active, sector inactive
  //   CS  -> sector active, budget inactive
  //   CSB -> both active
  // Cardinality is active in all four and is never a bit.
  G9_D013_CONDITION_C = 0u,
  G9_D013_CONDITION_CB = G9_D013_ACTIVITY_BUDGET,
  G9_D013_CONDITION_CS = G9_D013_ACTIVITY_SECTOR,
  G9_D013_CONDITION_CSB = G9_D013_ACTIVITY_MASK,
};

enum : std::uint32_t {
  // An INACTIVE family's register is never visited: not minimised, not
  // counted, not enumerated. Only these two values may be read.
  G9_D013_REGISTER_ACTIVE = 0u,
  G9_D013_REGISTER_NONE = 1u,
};

// Widths, restated here so the corruption plan has exact unique anchors and
// the host never hard-codes a magic number it has not cross-checked.
constexpr std::uint32_t kD013InactiveSectorWidth = kSectorCount * kSectorSlackBits;  // 8
constexpr std::uint32_t kD013InactiveBudgetWidth = kBudgetSlackBits;                 // 11

// The base stream's UPPER BOUND, not its actual length. With every register
// active, the base is bounded by 2 lifts per decoded state, because the
// declared integral-C contract leaves a sector register with exactly one
// minimizer and only the ACTIVE budget register can be tied. Every
// stream-sized buffer below is sized from THIS bound, never from a length
// that is only known after the terms stage, so a balanced-encoding word count
// above kStateCount can never overrun the segment or chunk arrays.
constexpr std::uint64_t kD013MaxWords = kStateCount * 2ULL;
constexpr std::uint32_t kD013MaxSegments =
    static_cast<std::uint32_t>((kD013MaxWords + kSegmentSize - 1ULL) / kSegmentSize);
constexpr std::uint32_t kD013MaxChunks =
    static_cast<std::uint32_t>((kD013MaxWords + kCompactionChunkSize - 1ULL) / kCompactionChunkSize);

// std::atomic_flag is the one type the C++ standard guarantees lock-free.
// Constant-initialised before any caller can run; never re-initialised.
static std::atomic_flag g9_d013_busy = ATOMIC_FLAG_INIT;

struct G9D013Counters {
  // MUST be 0: the instrumented proof that no kernel ever read a register
  // value belonging to an inactive family.
  std::uint64_t inactive_register_visits;
  // States whose LIFTED stream was materialised and written. Equal to
  // kStateCount for CSB, and for CB equal to the base word count: never
  // multiplied by an inactive sector register's 2^8.
  std::uint64_t enumerated_lifts_visited;
  // MUST be 0: a reported energy word equal to -0.0.
  std::uint64_t negative_zero_energies;
  // MUST be 0: a reported P_E word of an inactive family that is not the
  // positive zero, bit pattern 0.
  std::uint64_t inactive_term_nonzero;
  // NOT required to be 0. The number of states at which the NAIVE v1 product
  // `+0.0 * penalty` would have been `-0.0`. It is reported, never hidden, so
  // the fixtures can prove the `-0.0` hazard is genuinely reachable in this
  // synthetic landscape and that this path's avoidance is therefore not
  // vacuous. It is a measurement of the hazard, not of this path's output.
  std::uint64_t hazard_negative_zero_states;
  std::uint64_t states;
  // Whole active-lift domain |C_E|: base and its symbolic retained width.
  std::uint64_t lift_total_base;
  std::uint64_t lift_total_exact;
  std::uint32_t inactive_width;
  std::uint32_t row_count;
  std::uint32_t invalid_registers;
  std::uint32_t reserved;
};

struct G9D013Output {
  CoreOutput core;  // unchanged v1 bounded layout
  std::uint32_t conditions[kRowCount];
  G9D013Counters counters;
};

// Slot layout of the per-state probe table, one row per state.
enum : std::uint32_t {
  kD013ProbeStride = kRegisterCount + 1u,
  // 0..3: reported P_E_sector[j] as its exact binary64 word.
  // 4:    reported P_E_budget as its exact binary64 word.
  // 5:    the NAIVE v1 product `0.0 * first_negative_penalty` for the first
  //        inactive family, or kUint64Max when nothing is inactive. This is the
  //        hazard made visible: the fixtures require it to be 0x8000... i.e.
  //        -0.0, so a -0.0 hazard really is reachable in this synthetic
  //        landscape and the new path's avoidance is not vacuous.
};

namespace {

class G9D013Guard {
 public:
  G9D013Guard() : held_(!g9_d013_busy.test_and_set(std::memory_order_acquire)) {}
  ~G9D013Guard() {
    if (held_) g9_d013_busy.clear(std::memory_order_release);
  }
  G9D013Guard(const G9D013Guard&) = delete;
  G9D013Guard& operator=(const G9D013Guard&) = delete;
  bool held() const { return held_; }

 private:
  const bool held_;
};

// +0.0 is the ONLY accepted value of a D013-inactive coefficient.  Both -0.0
// (bit pattern 0x8000000000000000) and a tiny positive value such as 0x1p-1022
// are refused: -0.0 is a negative zero, not `+0.0`, and any strictly positive
// value is a mathematically ACTIVE coefficient.
bool g9_d013_is_positive_zero(const double value) {
  return double_to_word(value) == 0ULL;
}

// An ACTIVE family keeps v1's own rule: strictly positive and finite.
bool g9_d013_is_active_coefficient(const double value) {
  return value > 0.0 && !value_is_nonfinite(value);
}

bool g9_d013_conditions_valid(const CoefficientData* rows, const std::uint32_t row_count,
                              const std::uint32_t* conditions) {
  for (std::uint32_t row = 0; row < row_count; ++row) {
    // An unknown condition code is refused, not clamped.
    if (conditions[row] > G9_D013_ACTIVITY_MASK) return false;
    const CoefficientData& coefficients = rows[row];
    const double fixed[5] = {coefficients.alpha, coefficients.sector_linear,
                             coefficients.sector_quadratic, coefficients.budget_linear,
                             coefficients.budget_quadratic};
    for (std::uint32_t j = 0; j < 5u; ++j) {
      if (value_is_nonfinite(fixed[j])) return false;
    }
    const bool sector_active = (conditions[row] & G9_D013_ACTIVITY_SECTOR) != 0u;
    const bool budget_active = (conditions[row] & G9_D013_ACTIVITY_BUDGET) != 0u;
    if (sector_active) {
      if (!g9_d013_is_active_coefficient(coefficients.sector_slack)) return false;
    } else if (!g9_d013_is_positive_zero(coefficients.sector_slack)) {
      return false;
    }
    if (budget_active) {
      if (!g9_d013_is_active_coefficient(coefficients.budget_slack)) return false;
    } else if (!g9_d013_is_positive_zero(coefficients.budget_slack)) {
      return false;
    }
  }
  return true;
}

bool g9_d013_disjoint(const void* first, const std::size_t first_bytes,
                      const void* second, const std::size_t second_bytes) {
  const std::uintptr_t a = reinterpret_cast<std::uintptr_t>(first);
  const std::uintptr_t b = reinterpret_cast<std::uintptr_t>(second);
  return a + first_bytes <= b || b + second_bytes <= a;
}

// w, the TOTAL retained inactive register width: 2 bits per inactive sector
// register (8 for all four) and 11 for the budget register. This is the
// exponent the owner decision fixes as the second |T_E| factor.
std::uint32_t g9_d013_inactive_width(const std::uint32_t condition) {
  std::uint32_t w = 0u;
  if ((condition & G9_D013_ACTIVITY_SECTOR) == 0u) w += kD013InactiveSectorWidth;
  if ((condition & G9_D013_ACTIVITY_BUDGET) == 0u) w += kD013InactiveBudgetWidth;
  return w;
}

// THE UNBALANCED ENERGY STAGE, and the only place the unbalanced family's four
// terms are summed. Frozen D015 section 1.4 order: f, P_card, sector
// j = 1..4, then budget. An inactive family contributes the positive zero by
// being SKIPPED, which is the structural answer to the `-0.0` hazard: the
// product `coefficient * penalty` is never formed for an inactive family, so a
// negative penalty can neither produce `-0.0` nor change the accumulator's sign.
__host__ __device__ static double g9_d013_unbalanced_sum(const double objective,
                                                          const double card_square,
                                                          const CoefficientData& coefficients,
                                                          const double* sector_residual,
                                                          const double budget_residual,
                                                          const std::uint32_t condition) {
  double h_acc = objective;
  h_acc = h_acc + (coefficients.alpha * card_square);
  for (std::uint32_t s = 0; s < kSectorCount; ++s) {
    if ((condition & G9_D013_ACTIVITY_SECTOR) == 0u) continue;  // P_E_sector[j] = +0.0
    const double linear = coefficients.sector_linear * sector_residual[s];
    const double quadratic = coefficients.sector_quadratic * (sector_residual[s] * sector_residual[s]);
    h_acc = h_acc + ((-linear) + quadratic);
  }
  if ((condition & G9_D013_ACTIVITY_BUDGET) == 0u) return h_acc;  // P_E_budget = +0.0
  const double linear = coefficients.budget_linear * budget_residual;
  const double quadratic = coefficients.budget_quadratic * (budget_residual * budget_residual);
  return h_acc + ((-linear) + quadratic);
}

// THE BALANCED (SLACK) ENERGY STAGE. The same frozen order, but a family's
// term is `slack_coefficient * register_penalty` rather than the unbalanced
// linear/quadratic form, and the budget family is added PER LIFT rather than to
// the base. An inactive family is SKIPPED here for exactly the same reason: its
// `0.0 * penalty` product is never formed, so the inactive term can be neither
// `-0.0` nor a perturbation of the accumulator.
__host__ __device__ static double g9_d013_balanced_base(const double objective,
                                                        const double card_square,
                                                        const CoefficientData& coefficients,
                                                        const double* sector_penalty,
                                                        const std::uint32_t condition) {
  double h_acc = objective;
  h_acc = h_acc + (coefficients.alpha * card_square);
  for (std::uint32_t s = 0; s < kSectorCount; ++s) {
    if ((condition & G9_D013_ACTIVITY_SECTOR) == 0u) continue;  // P_E_sector[j] = +0.0
    h_acc = h_acc + (coefficients.sector_slack * sector_penalty[s]);
  }
  return h_acc;  // P_E_budget is added per LIFT, never to the base
}

// The reported P_E of ONE family, for the bit-pattern probe. An inactive
// family reports the positive-zero CONSTANT, not a computed product.
__host__ __device__ static double g9_d013_family_term(const CoefficientData& coefficients,
                                                      const double residual,
                                                      const bool is_sector,
                                                      const bool sector_active,
                                                      const bool budget_active) {
  if (is_sector ? !sector_active : !budget_active) return +0.0;
  const double linear = is_sector ? coefficients.sector_linear * residual
                                  : coefficients.budget_linear * residual;
  const double quadratic = is_sector ? coefficients.sector_quadratic * (residual * residual)
                                     : coefficients.budget_quadratic * (residual * residual);
  return (-linear) + quadratic;
}

// Prepared terms and the multiplicity of the BASE (enumerated) stream. Every
// ACTIVE register contributes its minimizer count; an INACTIVE register is
// skipped, and its 2^w factor is applied once, arithmetically, on the host. An
// ACTIVE sector register is never tied (integral-C contract), so the base is
// bounded by 2 lifts per decoded state.
//
// `sector_penalty[s]` receives the FIRST minimiser's penalty of active sector
// register s, which is all the balanced transcript needs: a non-tied sector
// register has exactly one minimiser, and an inactive one is never written.
__global__ void g9_d013_terms_kernel(const PayloadData* payload, const std::uint32_t* register_activity,
                                     double* objective, double* card_square, double* sector_penalty,
                                     std::uint32_t* lift_counts,
                                     std::uint32_t* invalid, std::uint64_t* register_visits) {
  const std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index >= kStateCount) return;
  objective[index] = objective_of(payload, index);
  card_square[index] = card_square_of(payload, index);
  double sector[kSectorCount], budget;
  residuals_of(payload, index, sector, &budget);
  std::uint32_t multiplicity = 1u;
  std::uint32_t bad = 0u;
  for (std::uint32_t r = 0; r < kRegisterCount; ++r) {
    if (register_activity[index * kRegisterCount + r] == G9_D013_REGISTER_NONE) {
      // INACTIVE: never visited, so never enumerated, never counted, and its
      // penalty slot is left untouched rather than being written with a value
      // the balanced transcript must not read.
      continue;
    }
    const bool is_sector = r < kSectorCount;
    const double residual = is_sector ? sector[r] : budget;
    const std::uint32_t maximum = register_maximum(is_sector ? r : kSectorCount);
    std::uint32_t values[2];
    double penalties[2];
    const std::uint32_t count = register_minimizers(residual, maximum, values, penalties);
    // Instrumented: one visit of this register's minimiser.
    register_visits[index * kRegisterCount + r] += 1ULL;
    if (count == 0u) {
      bad = 1u;
    } else {
      multiplicity *= count;
      if (is_sector) sector_penalty[index * kSectorCount + r] = penalties[0];
    }
  }
  invalid[index] = bad;
  lift_counts[index] = (bad != 0u || multiplicity > kMaxLiftsPerState) ? 0u : multiplicity;
}

// The base stream. `offsets` is the base prefix; the inactive factor 2^w is
// never expanded into memory.
__global__ void g9_d013_energy_kernel(const PayloadData* payload, const CoefficientData* coefficients,
                                      const std::uint32_t condition, const double* objective,
                                      const double* card_square, const double* sector_penalty,
                                      const std::uint32_t encoding,
                                      const std::uint64_t* offsets, double* energies,
                                      std::uint64_t* lift_visits) {
  const std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index >= kStateCount) return;
  double sector[kSectorCount], budget;
  residuals_of(payload, index, sector, &budget);
  if (encoding == 0u) {
    // The UNBALANCED transcript: one word per decoded state.
    energies[index] = g9_d013_unbalanced_sum(objective[index], card_square[index], *coefficients,
                                             sector, budget, condition);
    lift_visits[index] = 1ULL;
    return;
  }
  // The BALANCED transcript: the same frozen order, but the sector family's
  // term is the slack-weighted register penalty, and the budget family's term
  // is added once per LIFT below.
  const double h = g9_d013_balanced_base(objective[index], card_square[index], *coefficients,
                                          &sector_penalty[index * kSectorCount], condition);
  if ((condition & G9_D013_ACTIVITY_BUDGET) == 0u) {
    // The retained budget register is NOT enumerated: its 2^11 lifts are the
    // symbolic factor, not 2048 distinct words. The state contributes exactly
    // one base word, and P_E_budget = +0.0 is never formed.
    energies[index] = h;
    lift_visits[index] = 1ULL;
    return;
  }
  std::uint32_t values[2];
  double penalties[2];
  const std::uint32_t count = register_minimizers(budget, register_maximum(kSectorCount), values, penalties);
  std::uint64_t cursor = offsets[index];
  for (std::uint32_t lift = 0; lift < count; ++lift) {
    energies[cursor] = h + (coefficients->budget_slack * penalties[lift]);
    lift_visits[index] += 1ULL;
    cursor = cursor + 1ULL;
  }
}

// The `+0.0` bit-pattern probe. Writes, for every state, the exact binary64
// word of each reported family term, plus two hazard measurements.
//
// SLOT 5 (kRegisterCount) is the SIGN HAZARD made measurable.  The slack
// penalties are `delta * delta` and therefore never negative, so
// `+0.0 * penalty` is `+0.0` and a `-0.0` from that route is UNREACHABLE on
// this frozen register rule.  The reachable route to a negative inactive term
// is the UNBALANCED transcript, where a family's term is
// `(-linear) + quadratic` and is genuinely negative whenever the residual is
// positive and the linear term dominates.  So the hazard is measured the way
// it can actually occur: the naive `+0.0 * (an inactive family's own negative
// term)`, which is `-0.0` by IEEE 754, and which the new path never forms
// because it SKIPS the family instead.  A positive count here is the evidence
// that the skip is load-bearing rather than vacuous.
__global__ void g9_d013_probe_kernel(const PayloadData* payload, const CoefficientData* coefficients,
                                     const std::uint32_t condition, std::uint64_t* probe) {
  const std::uint32_t index = blockIdx.x * blockDim.x + threadIdx.x;
  if (index >= kStateCount) return;
  double sector[kSectorCount], budget;
  residuals_of(payload, index, sector, &budget);
  const bool sector_active = (condition & G9_D013_ACTIVITY_SECTOR) != 0u;
  const bool budget_active = (condition & G9_D013_ACTIVITY_BUDGET) != 0u;
  std::uint64_t* row = &probe[index * kD013ProbeStride];
  for (std::uint32_t s = 0; s < kSectorCount; ++s) {
    row[s] = double_to_word(g9_d013_family_term(*coefficients, sector[s], true,
                                                sector_active, budget_active));
  }
  row[kSectorCount] = double_to_word(g9_d013_family_term(*coefficients, budget, false,
                                                         sector_active, budget_active));
  // The naive product an inactive family's term would receive, formed from the
  // ACTIVE family term of that same family. This is what the skipped
  // `H_acc = fl(H_acc + +0.0 * P_E)` would look like if P_E were allowed to be
  // negative: `+0.0 * negative == -0.0`.
  double hazard = static_cast<double>(kUint64Max);
  if (!sector_active) {
    const double linear = coefficients->sector_linear * sector[0];
    const double quadratic = coefficients->sector_quadratic * (sector[0] * sector[0]);
    const double own_term = (-linear) + quadratic;
    if (own_term < 0.0) hazard = coefficients->sector_slack * own_term;
  } else if (!budget_active) {
    const double linear = coefficients->budget_linear * budget;
    const double quadratic = coefficients->budget_quadratic * (budget * budget);
    const double own_term = (-linear) + quadratic;
    if (own_term < 0.0) hazard = coefficients->budget_slack * own_term;
  }
  row[kRegisterCount] = double_to_word(hazard);
}

}  // namespace

extern "C" std::uint32_t g9_d013_backend() {
#if defined(__CUDACC__)
  return 1u;
#else
  return 0u;
#endif
}

extern "C" std::uint32_t g9_d013_condition_codes(std::uint64_t* values, std::uint32_t capacity) {
  if (values == nullptr || capacity != 6u) return 0u;
  const std::uint64_t codes[6] = {
    G9_D013_CONDITION_C, G9_D013_CONDITION_CB, G9_D013_CONDITION_CS, G9_D013_CONDITION_CSB,
    G9_D013_ACTIVITY_SECTOR, G9_D013_ACTIVITY_BUDGET,
  };
  std::memcpy(values, codes, sizeof(codes));
  return 6u;
}

extern "C" std::uint32_t g9_d013_abi_layout(std::uint64_t* values, std::uint32_t capacity) {
  if (values == nullptr || capacity != 6u) return 0u;
  const std::uint64_t layout[6] = {
    sizeof(PayloadData), sizeof(CoefficientData), sizeof(ScanResult), sizeof(CoreOutput),
    sizeof(G9D013Counters), sizeof(G9D013Output),
  };
  std::memcpy(values, layout, sizeof(layout));
  return 6u;
}

extern "C" std::uint32_t g9_d013_counters_layout(std::uint64_t* values, std::uint32_t capacity) {
  if (values == nullptr || capacity != 5u) return 0u;
  // A layout description ctypes can be compared against without a private
  // offset accessor: the two field widths, the struct size, the number of
  // REPORTED counters, and the total declared field count. The counter
  // SEMANTICS are checked against real returned values on the host, not
  // against offsets.
  const std::uint64_t layout[5] = {
    sizeof(std::uint64_t), sizeof(std::uint32_t), sizeof(G9D013Counters), 11u, 12u,
  };
  std::memcpy(values, layout, sizeof(layout));
  return 5u;
}

extern "C" std::uint32_t g9_d013_run(const PayloadData* payload, const CoefficientData* rows,
                                     const std::uint32_t* conditions, const std::uint32_t row_count,
                                     G9D013Output* out) {
  // Argument shape only: no shared state is read, no buffer is written.
  if (payload == nullptr || rows == nullptr || conditions == nullptr || out == nullptr ||
      row_count == 0u || row_count > kRowCount) {
    return G9_D013_REFUSED;
  }
  if (!g9_d013_disjoint(out, sizeof(G9D013Output), payload, sizeof(PayloadData)) ||
      !g9_d013_disjoint(out, sizeof(G9D013Output), rows, sizeof(CoefficientData) * row_count) ||
      !g9_d013_disjoint(out, sizeof(G9D013Output), conditions, sizeof(std::uint32_t) * row_count)) {
    return G9_D013_REFUSED;
  }
  const G9D013Guard guard;
  if (!guard.held()) return G9_D013_BUSY;

  // Process-global static storage: the arrays below hold 2^20 entries each and
  // would overflow the stack.
  static std::uint32_t register_activity[kStateCount * kRegisterCount];
  static std::uint32_t lift_counts[kStateCount];
  static std::uint32_t invalid_flags[kStateCount];
  static std::uint64_t register_visits[kStateCount * kRegisterCount];
  static std::uint64_t lift_visits[kStateCount];
  static std::uint64_t probe[kStateCount * kD013ProbeStride];
  static std::uint64_t offsets[kStateCount + 1ULL];
  static double objective[kStateCount];
  static double card_square[kStateCount];
  static double energies[kD013MaxWords];
  static double segment_value[kD013MaxSegments];
  static std::uint64_t segment_index[kD013MaxSegments];
  static std::uint32_t segment_nonfinite[kD013MaxSegments];
  static std::uint64_t per_ch[kD013MaxSegments * kCHCount];
  static std::uint32_t illegal[kD013MaxSegments];
  static std::uint32_t nesting[kD013MaxSegments];
  const std::uint32_t chunk_count = kD013MaxChunks;
  static std::uint32_t chunk_counts[chunk_count];
  static std::uint32_t chunk_illegal[chunk_count];
  static std::uint32_t chunk_refused[chunk_count];
  static std::uint64_t chunk_prefix[chunk_count + 1u];
  static std::uint64_t entries[kMaxCompactedEntries];
  static ScanResult results[kRowCount][kEncodingCount];

  // Refusals run before any allocation or launch. The v1 payload refusals are
  // reproduced exactly, so this path accepts exactly the payloads v1 accepts.
  if (value_is_nonfinite(payload->c_value) || payload->c_value < 0.0 ||
      !(payload->c_value < 0x1p63)) {
    std::memset(static_cast<void*>(out), 0, sizeof(G9D013Output));
    return G9_D013_REFUSED;
  }
  if (!(payload->k_value > 0.0) || !validate_payload_contract(*payload)) {
    std::memset(static_cast<void*>(out), 0, sizeof(G9D013Output));
    return G9_D013_REFUSED;
  }
  for (std::uint32_t i = 0; i < kAssetCount; ++i) {
    for (std::uint32_t j = i + 1u; j < kAssetCount; ++j) {
      if (payload->sigma[i * kAssetCount + j] != payload->sigma[j * kAssetCount + i]) {
        std::memset(static_cast<void*>(out), 0, sizeof(G9D013Output));
        return G9_D013_REFUSED;
      }
    }
  }
  if (!g9_d013_conditions_valid(rows, row_count, conditions)) {
    std::memset(static_cast<void*>(out), 0, sizeof(G9D013Output));
    return G9_D013_REFUSED;
  }

  std::memset(static_cast<void*>(out), 0, sizeof(G9D013Output));
  for (std::uint32_t r = 0; r < kRowCount; ++r) {
    for (std::uint32_t e = 0; e < kEncodingCount; ++e) results[r][e] = ScanResult{};
    out->conditions[r] = r < row_count ? conditions[r] : 0u;
  }
  // Every register of every row is marked BEFORE any launch, so the activity
  // table can never be read while it still shows a previous row's mask.  The
  // mask is a function of the CONDITION alone, never of the coefficients, so
  // rows that share a condition share one domain; rows with different
  // conditions get different domains, and each is built by its own terms
  // stage below.
  for (std::uint32_t index = 0; index < kStateCount; ++index) {
    for (std::uint32_t r = 0; r < kRegisterCount; ++r) {
      register_visits[index * kRegisterCount + r] = 0ULL;
    }
    lift_visits[index] = 0ULL;
  }

  // CANDIDATE v2: the validated payload is staged to device memory here.
  // v1 declared no device payload at all and passed the host `payload`
  // pointer straight into all three D013 kernels.
  PayloadData* device_payload = nullptr;
  CoefficientData* device_rows = nullptr;
  double* device_objective = nullptr;
  double* device_card_square = nullptr;
  double* device_sector_penalty = nullptr;
  std::uint32_t* device_lift_counts = nullptr;
  std::uint32_t* device_invalid = nullptr;
  std::uint32_t* device_activity = nullptr;
  std::uint64_t* device_register_visits = nullptr;
  std::uint64_t* device_lift_visits = nullptr;
  std::uint64_t* device_probe = nullptr;
  std::uint64_t* device_offsets = nullptr;
  double* device_energies = nullptr;
  double* device_segment_value = nullptr;
  std::uint64_t* device_segment_index = nullptr;
  std::uint32_t* device_segment_nonfinite = nullptr;
  std::uint64_t* device_per_ch = nullptr;
  std::uint32_t* device_illegal = nullptr;
  std::uint32_t* device_nesting = nullptr;
  std::uint8_t* device_flag_bytes = nullptr;
  std::uint32_t* device_chunk_counts = nullptr;
  std::uint32_t* device_chunk_illegal = nullptr;
  std::uint32_t* device_chunk_refused = nullptr;
  std::uint64_t* device_chunk_prefix = nullptr;
  std::uint64_t* device_entries = nullptr;

  const std::uint32_t state_grid =
      static_cast<std::uint32_t>((kStateCount + kBlockSize - 1u) / kBlockSize);
  const std::uint32_t segment_count = kD013MaxSegments;
  const dim3 segment_grid((segment_count + kBlockSize - 1u) / kBlockSize);
  const dim3 chunk_grid((chunk_count + kBlockSize - 1u) / kBlockSize);

  // CANDIDATE v2: first in the chain, mirroring the qualified v1 core
  // (stream_engine.cu:583), so a payload-allocation failure short-circuits
  // every later allocation exactly as the core's does.
  bool ok = cudaMalloc(&device_payload, sizeof(PayloadData)) == cudaSuccess &&
            cudaMalloc(&device_rows, sizeof(CoefficientData) * kRowCount) == cudaSuccess &&
            cudaMalloc(&device_objective, sizeof(double) * kStateCount) == cudaSuccess &&
            cudaMalloc(&device_card_square, sizeof(double) * kStateCount) == cudaSuccess &&
            cudaMalloc(&device_sector_penalty, sizeof(double) * kStateCount * kSectorCount) == cudaSuccess &&
            cudaMalloc(&device_lift_counts, sizeof(std::uint32_t) * kStateCount) == cudaSuccess &&
            cudaMalloc(&device_invalid, sizeof(std::uint32_t) * kStateCount) == cudaSuccess &&
            cudaMalloc(&device_activity, sizeof(std::uint32_t) * kStateCount * kRegisterCount) == cudaSuccess &&
            cudaMalloc(&device_register_visits, sizeof(std::uint64_t) * kStateCount * kRegisterCount) == cudaSuccess &&
            cudaMalloc(&device_lift_visits, sizeof(std::uint64_t) * kStateCount) == cudaSuccess &&
            cudaMalloc(&device_probe, sizeof(std::uint64_t) * kStateCount * kD013ProbeStride) == cudaSuccess &&
            cudaMalloc(&device_offsets, sizeof(std::uint64_t) * (kStateCount + 1ULL)) == cudaSuccess &&
            cudaMalloc(&device_energies, sizeof(double) * kD013MaxWords) == cudaSuccess;
  // CANDIDATE v2: stage the validated payload HostToDevice, mirroring the
  // qualified v1 core (stream_engine.cu:590). The copy is guarded by the same
  // `ok` chain, so a copy failure refuses without launching anything.
  ok = ok && cudaMemcpy(device_payload, payload, sizeof(PayloadData),
                        cudaMemcpyHostToDevice) == cudaSuccess;
  ok = ok && cudaMemcpy(device_rows, rows, sizeof(CoefficientData) * row_count,
                        cudaMemcpyHostToDevice) == cudaSuccess;

  if (ok) {
    ok = cudaMalloc(&device_segment_value, sizeof(double) * segment_count) == cudaSuccess &&
         cudaMalloc(&device_segment_index, sizeof(std::uint64_t) * segment_count) == cudaSuccess &&
         cudaMalloc(&device_segment_nonfinite, sizeof(std::uint32_t) * segment_count) == cudaSuccess &&
         cudaMalloc(&device_per_ch, sizeof(std::uint64_t) * segment_count * kCHCount) == cudaSuccess &&
         cudaMalloc(&device_illegal, sizeof(std::uint32_t) * segment_count) == cudaSuccess &&
         cudaMalloc(&device_nesting, sizeof(std::uint32_t) * segment_count) == cudaSuccess &&
         cudaMalloc(&device_flag_bytes, sizeof(std::uint8_t) * kD013MaxWords) == cudaSuccess &&
         cudaMalloc(&device_chunk_counts, sizeof(std::uint32_t) * chunk_count) == cudaSuccess &&
         cudaMalloc(&device_chunk_illegal, sizeof(std::uint32_t) * chunk_count) == cudaSuccess &&
         cudaMalloc(&device_chunk_refused, sizeof(std::uint32_t) * chunk_count) == cudaSuccess &&
         cudaMalloc(&device_chunk_prefix, sizeof(std::uint64_t) * (chunk_count + 1u)) == cudaSuccess &&
         cudaMalloc(&device_entries, sizeof(std::uint64_t) * kMaxCompactedEntries) == cudaSuccess;
  }

  std::uint32_t invalid_registers = 0u;
  std::uint64_t base_total = 0ULL;
  for (std::uint32_t row = 0; ok && row < row_count; ++row) {
    const std::uint32_t condition = conditions[row];
    // This row's register activity mask. It is a function of the CONDITION
    // alone, so it is rebuilt for every row and cannot leak between rows.
    {
      const bool sector_active = (condition & G9_D013_ACTIVITY_SECTOR) != 0u;
      const bool budget_active = (condition & G9_D013_ACTIVITY_BUDGET) != 0u;
      for (std::uint32_t index = 0; index < kStateCount; ++index) {
        for (std::uint32_t r = 0; r < kRegisterCount; ++r) {
          const bool active = r < kSectorCount ? sector_active : budget_active;
          register_activity[index * kRegisterCount + r] = active ? G9_D013_REGISTER_ACTIVE
                                                                : G9_D013_REGISTER_NONE;
        }
      }
    }
    for (std::uint32_t index = 0; index < kStateCount; ++index) {
      for (std::uint32_t r = 0; r < kRegisterCount; ++r) {
        register_visits[index * kRegisterCount + r] = 0ULL;
      }
      lift_visits[index] = 0ULL;
    }
    // The terms stage for THIS row's condition: the base domain, the offsets,
    // and the instrumented register-visit table.
    ok = ok && cudaMemcpy(device_activity, register_activity,
                          sizeof(std::uint32_t) * kStateCount * kRegisterCount,
                          cudaMemcpyHostToDevice) == cudaSuccess;
    if (ok) {
      // CANDIDATE v2: device payload pointer, not the host `payload`.
      G9_CORE_LAUNCH(g9_d013_terms_kernel, dim3(state_grid), dim3(kBlockSize), device_payload, device_activity,
                     device_objective, device_card_square, device_sector_penalty, device_lift_counts,
                     device_invalid, device_register_visits);
      ok = ok && cudaGetLastError() == cudaSuccess && cudaDeviceSynchronize() == cudaSuccess;
      ok = ok && cudaMemcpy(objective, device_objective, sizeof(double) * kStateCount,
                            cudaMemcpyDeviceToHost) == cudaSuccess;
      ok = ok && cudaMemcpy(card_square, device_card_square, sizeof(double) * kStateCount,
                            cudaMemcpyDeviceToHost) == cudaSuccess;
      ok = ok && cudaMemcpy(lift_counts, device_lift_counts, sizeof(std::uint32_t) * kStateCount,
                            cudaMemcpyDeviceToHost) == cudaSuccess;
      ok = ok && cudaMemcpy(invalid_flags, device_invalid, sizeof(std::uint32_t) * kStateCount,
                            cudaMemcpyDeviceToHost) == cudaSuccess;
      ok = ok && cudaMemcpy(register_visits, device_register_visits,
                            sizeof(std::uint64_t) * kStateCount * kRegisterCount,
                            cudaMemcpyDeviceToHost) == cudaSuccess;
    }
    // The BASE prefix: this row's exact integer count of enumerated words.
    // |T_E| is base * 2^w, formed once, arithmetically, below -- never by
    // enumerating the retained inactive register.
    if (ok) {
      offsets[0] = 0ULL;
      base_total = 0ULL;
      for (std::uint64_t index = 0; index < kStateCount; ++index) {
        invalid_registers += invalid_flags[index];
        const std::uint64_t multiplicity = lift_counts[index];
        if (multiplicity == 0ULL || multiplicity > kMaxLiftsPerState) {
          ok = false;
          break;
        }
        if (base_total > kUint64Max - multiplicity) {
          ok = false;
          break;
        }
        base_total += multiplicity;
        offsets[index + 1ULL] = base_total;
      }
      ok = ok && invalid_registers == 0u && base_total <= kD013MaxWords;
    }
    ok = ok && cudaMemcpy(device_offsets, offsets, sizeof(std::uint64_t) * (kStateCount + 1ULL),
                          cudaMemcpyHostToDevice) == cudaSuccess;
    // The `+0.0` bit-pattern probe, one run per row.
    if (ok) {
      // CANDIDATE v2: device payload pointer.
      G9_CORE_LAUNCH(g9_d013_probe_kernel, dim3(state_grid), dim3(kBlockSize), device_payload,
                     &device_rows[row], condition, device_probe);
      ok = ok && cudaGetLastError() == cudaSuccess && cudaDeviceSynchronize() == cudaSuccess;
      ok = ok && cudaMemcpy(probe, device_probe,
                            sizeof(std::uint64_t) * kStateCount * kD013ProbeStride,
                            cudaMemcpyDeviceToHost) == cudaSuccess;
    }
    if (ok) {
      const bool sector_active = (condition & G9_D013_ACTIVITY_SECTOR) != 0u;
      const bool budget_active = (condition & G9_D013_ACTIVITY_BUDGET) != 0u;
      std::uint64_t nonzero_terms = 0ULL;
      std::uint64_t negative_zero_terms = 0ULL;
      std::uint64_t hazard_negative_zero = 0ULL;
      for (std::uint64_t index = 0; index < kStateCount; ++index) {
        const std::uint64_t* probe_row = &probe[index * kD013ProbeStride];
        if (!sector_active) {
          for (std::uint32_t s = 0; s < kSectorCount; ++s) {
            if (probe_row[s] != 0ULL) nonzero_terms += 1ULL;
            if (probe_row[s] == 0x8000000000000000ULL) negative_zero_terms += 1ULL;
          }
        }
        if (!budget_active) {
          if (probe_row[kSectorCount] != 0ULL) nonzero_terms += 1ULL;
          if (probe_row[kSectorCount] == 0x8000000000000000ULL) negative_zero_terms += 1ULL;
        }
        if (probe_row[kRegisterCount] == 0x8000000000000000ULL) hazard_negative_zero += 1ULL;
      }
      out->counters.inactive_term_nonzero += nonzero_terms;
      out->counters.negative_zero_energies += negative_zero_terms;
      // Recorded, never hidden: the naive v1 product really is -0.0 at some
      // states in this synthetic landscape, so the new path's avoidance of it
      // is a real property and not a vacuous one.
      out->counters.hazard_negative_zero_states += hazard_negative_zero;
    }

    for (std::uint32_t encoding = 0; ok && encoding < kEncodingCount; ++encoding) {
      const std::uint64_t word_count = encoding == 0u ? kStateCount : base_total;
      const std::uint32_t words_segment_count =
          static_cast<std::uint32_t>((word_count + kSegmentSize - 1ULL) / kSegmentSize);
      const std::uint32_t words_chunk_count =
          static_cast<std::uint32_t>((word_count + kCompactionChunkSize - 1ULL) / kCompactionChunkSize);
      for (std::uint64_t index = 0; index < kStateCount; ++index) lift_visits[index] = 0ULL;
      // CANDIDATE v2: device payload pointer.
      G9_CORE_LAUNCH(g9_d013_energy_kernel, dim3(state_grid), dim3(kBlockSize), device_payload,
                     &device_rows[row], condition, device_objective, device_card_square,
                     device_sector_penalty, encoding, device_offsets, device_energies,
                     device_lift_visits);
      ok = ok && cudaGetLastError() == cudaSuccess && cudaDeviceSynchronize() == cudaSuccess;
      ok = ok && cudaMemcpy(energies, device_energies, sizeof(double) * word_count,
                            cudaMemcpyDeviceToHost) == cudaSuccess;
      ok = ok && cudaMemcpy(lift_visits, device_lift_visits, sizeof(std::uint64_t) * kStateCount,
                            cudaMemcpyDeviceToHost) == cudaSuccess;
      if (!ok) break;
      for (std::uint64_t index = 0; index < word_count; ++index) {
        if (double_to_word(energies[index]) == 0x8000000000000000ULL) {
          out->counters.negative_zero_energies += 1ULL;
        }
      }

      // CANDIDATE v2: device energy stream, as the core does
      // (stream_engine.cu:733). v1 passed the HOST `energies` array here.
      G9_CORE_LAUNCH(segment_kernel, dim3(segment_grid), dim3(kBlockSize), device_energies, word_count,
                     words_segment_count, device_segment_value, device_segment_index, device_segment_nonfinite);
      ok = ok && cudaGetLastError() == cudaSuccess && cudaDeviceSynchronize() == cudaSuccess;
      ok = ok && cudaMemcpy(segment_value, device_segment_value, sizeof(double) * words_segment_count,
                            cudaMemcpyDeviceToHost) == cudaSuccess;
      ok = ok && cudaMemcpy(segment_index, device_segment_index,
                            sizeof(std::uint64_t) * words_segment_count,
                            cudaMemcpyDeviceToHost) == cudaSuccess;
      ok = ok && cudaMemcpy(segment_nonfinite, device_segment_nonfinite,
                            sizeof(std::uint32_t) * words_segment_count,
                            cudaMemcpyDeviceToHost) == cudaSuccess;
      if (!ok) break;
      // Fixed-order host merge in ascending segment order with strict '<'.
      double minimum = 0.0;
      std::uint64_t minimum_index = kUint64Max;
      bool merged = false;
      for (std::uint32_t segment = 0; segment < words_segment_count; ++segment) {
        if (segment_index[segment] == kUint64Max) continue;
        if (!merged || segment_value[segment] < minimum) {
          minimum = segment_value[segment];
          minimum_index = segment_index[segment];
          merged = true;
        }
      }
      if (!merged) {
        ok = false;
        break;
      }
      ScanResult* result = &results[row][encoding];
      result->word_count = word_count;
      result->nonfinite = 0u;
      result->disagreements = 0u;
      for (std::uint32_t segment = 0; segment < words_segment_count; ++segment) {
        result->nonfinite += segment_nonfinite[segment];
      }
      if (result->nonfinite != 0u) {
        ok = false;
        break;
      }
      result->minimum = minimum;
      result->minimum_index = minimum_index;
      result->minimum_checksum = fnv_step(fnv_step(kFNVOffset, double_to_word(minimum)), minimum_index);

      const dim3 words_segment_grid = segment_grid;
      // CANDIDATE v2: device energy stream, as the core does
      // (stream_engine.cu:757). v1 passed the HOST `energies` array here.
      G9_CORE_LAUNCH(flags_kernel, dim3(words_segment_grid), dim3(kBlockSize), device_energies, word_count,
                     minimum, payload->lambda_ref, words_segment_count, device_per_ch,
                     device_illegal, device_nesting, device_flag_bytes);
      ok = ok && cudaGetLastError() == cudaSuccess && cudaDeviceSynchronize() == cudaSuccess;
      ok = ok && cudaMemcpy(per_ch, device_per_ch, sizeof(std::uint64_t) * words_segment_count * kCHCount,
                            cudaMemcpyDeviceToHost) == cudaSuccess;
      ok = ok && cudaMemcpy(illegal, device_illegal, sizeof(std::uint32_t) * words_segment_count,
                            cudaMemcpyDeviceToHost) == cudaSuccess;
      ok = ok && cudaMemcpy(nesting, device_nesting, sizeof(std::uint32_t) * words_segment_count,
                            cudaMemcpyDeviceToHost) == cudaSuccess;
      if (!ok) break;
      for (std::uint32_t bit = 0; bit < kCHCount; ++bit) result->per_ch[bit] = 0ULL;
      result->illegal = 0u;
      result->nesting = 0u;
      for (std::uint32_t segment = 0; segment < words_segment_count; ++segment) {
        for (std::uint32_t bit = 0; bit < kCHCount; ++bit) {
          result->per_ch[bit] += per_ch[segment * kCHCount + bit];
        }
        result->illegal += illegal[segment];
        result->nesting += nesting[segment];
      }

      const dim3 words_chunk_grid = chunk_grid;
      G9_CORE_LAUNCH(compaction_count_kernel, dim3(words_chunk_grid), dim3(kBlockSize), device_flag_bytes,
                     word_count, words_chunk_count, device_chunk_counts, device_chunk_illegal);
      ok = ok && cudaGetLastError() == cudaSuccess && cudaDeviceSynchronize() == cudaSuccess;
      ok = ok && cudaMemcpy(chunk_counts, device_chunk_counts, sizeof(std::uint32_t) * words_chunk_count,
                            cudaMemcpyDeviceToHost) == cudaSuccess;
      ok = ok && cudaMemcpy(chunk_illegal, device_chunk_illegal, sizeof(std::uint32_t) * words_chunk_count,
                            cudaMemcpyDeviceToHost) == cudaSuccess;
      if (!ok) break;
      for (std::uint32_t chunk = 0; chunk < words_chunk_count; ++chunk) {
        result->illegal += chunk_illegal[chunk];
      }
      chunk_prefix[0] = 0ULL;
      for (std::uint32_t chunk = 0; chunk < words_chunk_count; ++chunk) {
        chunk_prefix[chunk + 1u] = chunk_prefix[chunk] +
                                   static_cast<std::uint64_t>(chunk_counts[chunk]);
      }
      const std::uint64_t produced = chunk_prefix[words_chunk_count];
      if (produced > kMaxCompactedEntries) {
        // Fail closed: never write past the declared hard cap.
        result->compaction_overflows = 1u;
        ok = false;
        break;
      }
      // The exclusive prefix must reach the device before the write kernel:
      // each chunk writes only its own slice at prefix[chunk].
      ok = ok && cudaMemcpy(device_chunk_prefix, chunk_prefix,
                            sizeof(std::uint64_t) * (words_chunk_count + 1u),
                            cudaMemcpyHostToDevice) == cudaSuccess;
      if (!ok) break;
      G9_CORE_LAUNCH(compaction_write_kernel, dim3(words_chunk_grid), dim3(kBlockSize), device_flag_bytes,
                     word_count, words_chunk_count, device_chunk_prefix, kMaxCompactedEntries,
                     device_entries, device_chunk_refused);
      ok = ok && cudaGetLastError() == cudaSuccess && cudaDeviceSynchronize() == cudaSuccess;
      ok = ok && cudaMemcpy(chunk_refused, device_chunk_refused, sizeof(std::uint32_t) * words_chunk_count,
                            cudaMemcpyDeviceToHost) == cudaSuccess;
      if (!ok) break;
      for (std::uint32_t chunk = 0; chunk < words_chunk_count; ++chunk) {
        result->compaction_overflows += chunk_refused[chunk];
      }
      if (result->compaction_overflows != 0u) {
        ok = false;
        break;
      }
      if (produced > 0ULL) {
        ok = ok && cudaMemcpy(entries, device_entries, sizeof(std::uint64_t) * static_cast<std::size_t>(produced),
                              cudaMemcpyDeviceToHost) == cudaSuccess;
      }
      if (!ok) break;
      // Generic mode: reconstruct from the returned compact entries ALONE.
      for (std::uint64_t slot = 0; slot < produced; ++slot) {
        const std::uint64_t flags = entries[slot] >> 32;
        if (!(flags == 4ULL || flags == 6ULL || flags == 7ULL)) {
          result->compaction_mismatches += 1u;
        }
        result->entries[slot] = entries[slot];
      }
      for (std::uint64_t slot = 1; slot < produced; ++slot) {
        if (!((entries[slot] & 0xFFFFFFFFULL) > (entries[slot - 1ULL] & 0xFFFFFFFFULL))) {
          result->order_violations += 1u;
        }
      }
      result->compacted_count = produced;
      result->compaction_chunks = words_chunk_count;
      result->compaction_checksum = kFNVOffset;
      for (std::uint64_t slot = 0; slot < produced; ++slot) {
        result->compaction_checksum = fnv_step(result->compaction_checksum, entries[slot]);
      }
    }
    // The instrumented proof for THIS row: fold the visit table while it still
    // holds this row's condition's mask. An inactive register that was visited
    // would make the whole run unacceptable, so the count is recorded, not
    // silently dropped.
    for (std::uint64_t index = 0; index < kStateCount; ++index) {
      for (std::uint32_t r = 0; r < kRegisterCount; ++r) {
        if (register_activity[index * kRegisterCount + r] == G9_D013_REGISTER_NONE) {
          out->counters.inactive_register_visits += register_visits[index * kRegisterCount + r];
        }
      }
    }
    for (std::uint64_t index = 0; index < kStateCount; ++index) {
      if (lift_visits[index] != 0ULL) out->counters.enumerated_lifts_visited += 1ULL;
    }
  }

  // The instrumented proof, folded per row from the copied-back visit table.
  // The table holds the LAST row's visits, so the fold happens inside the row
  // loop above; the totals below are the sums over all rows.
  std::uint32_t width = 0u;
  for (std::uint32_t row = 0; row < row_count; ++row) {
    const std::uint32_t candidate = g9_d013_inactive_width(conditions[row]);
    if (candidate > width) width = candidate;
  }
  out->counters.states = kStateCount;
  out->counters.lift_total_base = base_total;
  // |C_E| = base * 2^w. The tied subset |T_E| is derived per result row
  // from D015's c_H=2048 tie count; this counter must never be used as |T_E|.
  out->counters.lift_total_exact = base_total * (1ULL << width);
  out->counters.inactive_width = width;
  out->counters.row_count = row_count;
  out->counters.invalid_registers = invalid_registers;
  out->core.lift_total = base_total;
  out->core.invalid_registers = invalid_registers;
  out->core.row_count = row_count;
  for (std::uint32_t row = 0; row < kRowCount; ++row) {
    for (std::uint32_t encoding = 0; encoding < kEncodingCount; ++encoding) {
      out->core.results[row][encoding] = results[row][encoding];
    }
  }

  // CANDIDATE v2: free the staged payload on the single post-allocation
  // return path, alongside every other device buffer.
  cudaFree(device_payload);
  cudaFree(device_rows);
  cudaFree(device_objective);
  cudaFree(device_card_square);
  cudaFree(device_sector_penalty);
  cudaFree(device_lift_counts);
  cudaFree(device_invalid);
  cudaFree(device_activity);
  cudaFree(device_register_visits);
  cudaFree(device_lift_visits);
  cudaFree(device_probe);
  cudaFree(device_offsets);
  cudaFree(device_energies);
  cudaFree(device_segment_value);
  cudaFree(device_segment_index);
  cudaFree(device_segment_nonfinite);
  cudaFree(device_per_ch);
  cudaFree(device_illegal);
  cudaFree(device_nesting);
  cudaFree(device_flag_bytes);
  cudaFree(device_chunk_counts);
  cudaFree(device_chunk_illegal);
  cudaFree(device_chunk_refused);
  cudaFree(device_chunk_prefix);
  cudaFree(device_entries);

  if (!ok) {
    std::memset(static_cast<void*>(out), 0, sizeof(G9D013Output));
    return G9_D013_REFUSED;
  }
  return G9_D013_OK;
}
