"""Independent amortisation and runner acceptance instrument (v2.2).

Audits and tests the Gate-5 multi-grid amortisation invariants against both
compliant and adversarial runner implementations.

Corrects structural lookup-site aliasing, module pre-importing, pre-loop redundant
preparation, tie-set count matching, and prevents unauthorized primary execution.

Invariants enforced for a certification run over P grid points against a
decoded domain of size D and slack domain of size L:

  1. instance validation: exactly 1 per runner invocation (flat across P=1 -> P=4)
  2. raw domain construction: exactly 1 BinaryDomain and <= 1 SlackDomainCache per invocation (flat)
  3. decoded preparation: <= D per invocation and exactly flat across P=1 -> P=4 (NOT D*P, NOT >D)
  4. slack preparation: <= L per invocation and exactly flat across P=1 -> P=4 (NOT L*P, NOT >L)
  5. prepared domain cache construction: exactly 1 cache per active encoding (flat across P=1 -> P=4)
  6. coefficient validation: exactly P per runner invocation (accounting for __post_init__)
  7. energy evaluation: exactly D*P (unbalanced) and L*P (slack), scaling exactly 4.0x
  8. legacy un-amortised evaluators: exactly 0 calls
  9. raw state reconstruction: PreparedDomainCache.raw_state call count == sum(len(t_e)) across all calls

Usage:
    python3 05_certification/g5/review_g5_amortisation_v2.py <module>:<callable>
    python3 05_certification/g5/review_g5_amortisation_v2.py --self-test
"""

from __future__ import annotations

from dataclasses import dataclass
import functools
import importlib
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Global call counters and tie set recording
CALLS: Counter = Counter()
CERTIFIED_T_E_LENGTHS: list[int] = []

# Registries for patching and original identity tracking
_ORIGINALS: dict[tuple[Any, str], Any] = {}
_CODE_TO_NAME: dict[Any, str] = {}
_WRAPPERS: dict[str, Any] = {}


def _record_call(name: str) -> None:
    CALLS[name] += 1


def _patch_callable(target_obj: Any, attr_name: str, counter_name: str) -> Any:
    if not hasattr(target_obj, attr_name):
        return None
    key = (target_obj, attr_name)
    if key in _ORIGINALS:
        return _WRAPPERS.get(counter_name)

    original = getattr(target_obj, attr_name)
    _ORIGINALS[key] = original

    code = getattr(original, "__code__", None)
    if code is not None:
        _CODE_TO_NAME[code] = counter_name

    @functools.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        _record_call(counter_name)
        return original(*args, **kwargs)

    _WRAPPERS[counter_name] = wrapper
    setattr(target_obj, attr_name, wrapper)
    return wrapper


def _patch_certify_prepared_domain(certify_mod: Any) -> None:
    """Special wrapper for certify_prepared_domain to record exact returned tie-set sizes."""
    if not hasattr(certify_mod, "certify_prepared_domain"):
        return
    key = (certify_mod, "certify_prepared_domain")
    if key in _ORIGINALS:
        return

    original = getattr(certify_mod, "certify_prepared_domain")
    _ORIGINALS[key] = original

    code = getattr(original, "__code__", None)
    if code is not None:
        _CODE_TO_NAME[code] = "certify_prepared_domain"

    @functools.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        _record_call("certify_prepared_domain")
        result = original(*args, **kwargs)
        # result is (h_e_min, t_e, x_e, label)
        if isinstance(result, tuple) and len(result) >= 2 and isinstance(result[1], (list, tuple)):
            CERTIFIED_T_E_LENGTHS.append(len(result[1]))
        return result

    _WRAPPERS["certify_prepared_domain"] = wrapper
    setattr(certify_mod, "certify_prepared_domain", wrapper)


def _patch_dataclass_post_init(cls: type, counter_name: str) -> None:
    key = (cls, "__post_init__")
    if key in _ORIGINALS:
        return
    original = getattr(cls, "__post_init__", None)
    _ORIGINALS[key] = original

    if original is not None:
        @functools.wraps(original)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            _record_call(counter_name)
            return original(self, *args, **kwargs)
        cls.__post_init__ = wrapper  # type: ignore[method-assign]
    else:
        def default_wrapper(self: Any, *args: Any, **kwargs: Any) -> None:
            _record_call(counter_name)
        cls.__post_init__ = default_wrapper  # type: ignore[method-assign]


def _patch_init(cls: type, counter_name: str) -> None:
    key = (cls, "__init__")
    if key in _ORIGINALS:
        return
    original = cls.__init__
    _ORIGINALS[key] = original

    @functools.wraps(original)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        _record_call(counter_name)
        return original(self, *args, **kwargs)

    cls.__init__ = wrapper  # type: ignore[method-assign]


def _sweep_sys_modules() -> None:
    """Sweep all loaded modules in sys.modules to intercept pre-instrumented aliases."""
    for mod_name, mod in list(sys.modules.items()):
        if mod is None or not isinstance(mod_name, str):
            continue
        if not mod_name.startswith(("src.g4", "src.g5")):
            continue
        for attr_name, attr_val in list(mod.__dict__.items()):
            if callable(attr_val):
                code = getattr(attr_val, "__code__", None)
                if code in _CODE_TO_NAME:
                    counter_name = _CODE_TO_NAME[code]
                    wrapper = _WRAPPERS.get(counter_name)
                    if wrapper is not None and attr_val is not wrapper:
                        setattr(mod, attr_name, wrapper)


def instrument() -> None:
    """Deep-instruments all lookup sites, module aliases, and class initialisers."""
    import src.g4.energy as energy
    import src.g5.domains as domains
    import src.g5.certify as certify

    # 1. Primary functions in src.g4.energy
    energy_funcs = (
        "prepare_instance",
        "prepare_coefficients",
        "prepare_decoded_state",
        "prepare_slack_state",
        "slack_energy_prepared",
        "unbalanced_energy_prepared",
        "slack_energy",
        "unbalanced_energy",
        "objective",
        "residuals",
        "exact_slack_lift",
        "_residuals_from_bits",
        "_objective_from_bits",
    )
    for name in energy_funcs:
        _patch_callable(energy, name, name)

    # 2. Re-exported / imported aliases in src.g5.domains
    domain_energy_aliases = (
        "prepare_instance",
        "prepare_decoded_state",
        "prepare_slack_state",
    )
    for name in domain_energy_aliases:
        _patch_callable(domains, name, name)

    # 3. Domain construction and cache functions in src.g5.domains
    domain_funcs = (
        "build_slack_domain_cache",
        "prepare_unbalanced_domain",
        "prepare_slack_domain",
        "iter_unbalanced_domain",
        "iter_slack_domain",
    )
    for name in domain_funcs:
        _patch_callable(domains, name, name)

    # 4. Certification and evaluation functions in src.g5.certify
    certify_funcs = (
        "certify_domain",
        "find_ground_state",
        "construct_t_e",
        "decode_x_e",
        "classify_t_e",
    )
    for name in certify_funcs:
        _patch_callable(certify, name, name)
    _patch_certify_prepared_domain(certify)

    # 5. Dataclass and class construction hooks (prevents direct instantiation bypass)
    _patch_dataclass_post_init(energy.PreparedInstance, "PreparedInstance.__post_init__")
    _patch_dataclass_post_init(energy.PreparedCoefficients, "PreparedCoefficients.__post_init__")
    _patch_dataclass_post_init(energy.PreparedDecodedState, "PreparedDecodedState.__post_init__")
    _patch_dataclass_post_init(energy.PreparedSlackState, "PreparedSlackState.__post_init__")
    _patch_dataclass_post_init(domains.SlackDomainCache, "SlackDomainCache.__post_init__")
    _patch_dataclass_post_init(domains.PreparedDomainCache, "PreparedDomainCache.__post_init__")
    _patch_init(domains.BinaryDomain, "BinaryDomain.__init__")

    # 6. Raw state access tracking on PreparedDomainCache (avoids double-counting with SlackDomainCache)
    _patch_callable(domains.PreparedDomainCache, "raw_state", "PreparedDomainCache.raw_state")

    # 7. Sweep sys.modules for any pre-imported or renamed aliases
    _sweep_sys_modules()


def report(label: str) -> Counter:
    snapshot = Counter(CALLS)
    print(f"--- {label}")
    for name, count in sorted(snapshot.items()):
        print(f"    {name:40s} {count:>12,}")
    return snapshot


def verdict(
    one: Counter,
    four: Counter,
    expected_D: int = 16,
    expected_L: int = 16,
    active_encodings: tuple[str, ...] = ("slack", "unbalanced"),
    expected_ties_1: int | None = None,
    expected_ties_4: int | None = None,
) -> int:
    """Evaluate amortisation invariants across P=1 vs P=4 runs with absolute count enforcement."""
    failures: list[str] = []

    # Invariant 1: Instance validation must occur exactly once per runner invocation
    inst_1 = one.get("PreparedInstance.__post_init__", 0)
    inst_4 = four.get("PreparedInstance.__post_init__", 0)
    if inst_1 != 1:
        failures.append(
            f"instance validation (P=1) count was {inst_1} (expected exactly 1); "
            "Instance validation must occur exactly once per run."
        )
    if inst_4 != 1:
        failures.append(
            f"instance validation (P=4) count was {inst_4} (expected exactly 1); "
            "Instance validation must not repeat across grid points."
        )

    # Invariant 2: BinaryDomain construction must occur exactly once per invocation
    bin_dom_1 = one.get("BinaryDomain.__init__", 0)
    bin_dom_4 = four.get("BinaryDomain.__init__", 0)
    if bin_dom_1 != 1:
        failures.append(
            f"binary domain construction (P=1) count was {bin_dom_1} (expected exactly 1); "
            "BinaryDomain must be constructed exactly once and reused."
        )
    if bin_dom_4 != 1:
        failures.append(
            f"binary domain construction (P=4) count was {bin_dom_4} (expected exactly 1); "
            "BinaryDomain must not be reconstructed inside or repeatedly outside the grid loop."
        )

    # Invariant 3: SlackDomainCache construction must be <= 1 (if slack is active) and flat
    if "slack" in active_encodings:
        slk_dom_1 = one.get("SlackDomainCache.__post_init__", 0)
        slk_dom_4 = four.get("SlackDomainCache.__post_init__", 0)
        if slk_dom_1 > 1:
            failures.append(
                f"slack domain construction (P=1) count was {slk_dom_1} (expected <= 1)."
            )
        if slk_dom_4 != slk_dom_1:
            failures.append(
                f"slack domain construction scaled across P=1 -> P=4 ({slk_dom_1} -> {slk_dom_4}); "
                "SlackDomainCache must be constructed once outside the grid loop."
            )

    # Invariant 4: Decoded state preparation must be <= D and exactly flat across P=1 and P=4
    dec_1 = one.get("PreparedDecodedState.__post_init__", 0)
    dec_4 = four.get("PreparedDecodedState.__post_init__", 0)
    if dec_1 == 0:
        failures.append("no PreparedDecodedState instances were created.")
    elif dec_1 > expected_D:
        failures.append(
            f"decoded state preparation (P=1) count was {dec_1} > D={expected_D}; "
            "States were prepared redundantly or multiple times outside the loop."
        )
    if dec_4 != dec_1:
        failures.append(
            f"decoded state preparation scaled across P=1 -> P=4 ({dec_1} -> {dec_4}); "
            "prepare_decoded_state is inside the grid loop; intermediate amortisation is lost."
        )

    # Invariant 5: Slack state preparation must be <= L and exactly flat across P=1 and P=4
    if "slack" in active_encodings:
        slk_1 = one.get("PreparedSlackState.__post_init__", 0)
        slk_4 = four.get("PreparedSlackState.__post_init__", 0)
        if slk_1 == 0:
            failures.append("no PreparedSlackState instances were created for active slack encoding.")
        elif slk_1 > expected_L:
            failures.append(
                f"slack state preparation (P=1) count was {slk_1} > L={expected_L}; "
                "Slack states were prepared redundantly outside the loop."
            )
        if slk_4 != slk_1:
            failures.append(
                f"slack state preparation scaled across P=1 -> P=4 ({slk_1} -> {slk_4}); "
                "prepare_slack_state is inside the grid loop; slack square amortisation is lost."
            )

    # Invariant 6: PreparedDomainCache construction must equal EXACTLY len(active_encodings)
    cache_1 = one.get("PreparedDomainCache.__post_init__", 0)
    cache_4 = four.get("PreparedDomainCache.__post_init__", 0)
    expected_caches = len(active_encodings)
    if cache_1 != expected_caches:
        failures.append(
            f"PreparedDomainCache construction (P=1) count was {cache_1} (expected exactly {expected_caches})."
        )
    if cache_4 != expected_caches:
        failures.append(
            f"PreparedDomainCache construction (P=4) count was {cache_4} (expected exactly {expected_caches}); "
            "Domain caches must be prepared once outside the grid loop."
        )

    # Invariant 7: Coefficient validation must equal EXACTLY P per run
    coeff_1 = one.get("PreparedCoefficients.__post_init__", 0)
    coeff_4 = four.get("PreparedCoefficients.__post_init__", 0)
    if coeff_1 != 1:
        failures.append(
            f"coefficient validation (P=1) count was {coeff_1} (expected exactly 1)."
        )
    if coeff_4 != 4:
        failures.append(
            f"coefficient validation (P=4) count was {coeff_4} (expected exactly 4); "
            "Coefficients must be validated exactly once per grid point."
        )

    # Invariant 8: Energy evaluation scaling must be EXACTLY 4.0x and match expected D*P, L*P
    if "unbalanced" in active_encodings:
        unb_eval_1 = one.get("unbalanced_energy_prepared", 0)
        unb_eval_4 = four.get("unbalanced_energy_prepared", 0)
        expected_unb_1 = expected_D * 1
        expected_unb_4 = expected_D * 4
        if unb_eval_1 != expected_unb_1:
            failures.append(
                f"unbalanced evaluation count for P=1 was {unb_eval_1} (expected exactly {expected_unb_1})."
            )
        if unb_eval_4 != expected_unb_4:
            failures.append(
                f"unbalanced evaluation count for P=4 was {unb_eval_4} (expected exactly {expected_unb_4}); "
                f"Scaling was {unb_eval_4 / unb_eval_1 if unb_eval_1 else 0:.2f}x (expected exactly 4.0x)."
            )

    if "slack" in active_encodings:
        slk_eval_1 = one.get("slack_energy_prepared", 0)
        slk_eval_4 = four.get("slack_energy_prepared", 0)
        expected_slk_1 = expected_L * 1
        expected_slk_4 = expected_L * 4
        if slk_eval_1 != expected_slk_1:
            failures.append(
                f"slack evaluation count for P=1 was {slk_eval_1} (expected exactly {expected_slk_1})."
            )
        if slk_eval_4 != expected_slk_4:
            failures.append(
                f"slack evaluation count for P=4 was {slk_eval_4} (expected exactly {expected_slk_4}); "
                f"Scaling was {slk_eval_4 / slk_eval_1 if slk_eval_1 else 0:.2f}x (expected exactly 4.0x)."
            )

    # Invariant 9: No legacy un-amortised evaluators or raw certify_domain calls
    for legacy_name in ("slack_energy", "unbalanced_energy", "certify_domain"):
        if four.get(legacy_name, 0) > 0 or one.get(legacy_name, 0) > 0:
            failures.append(
                f"legacy un-amortised evaluator {legacy_name} was invoked ({four.get(legacy_name, 0)} calls); "
                "All Gate-5 evaluations must use certify_prepared_domain with *_energy_prepared."
            )

    # Invariant 10: Raw state reconstruction count MUST MATCH EXACTLY sum(len(t_e))
    raw_1 = one.get("PreparedDomainCache.raw_state", 0)
    raw_4 = four.get("PreparedDomainCache.raw_state", 0)
    if expected_ties_1 is not None and raw_1 != expected_ties_1:
        failures.append(
            f"raw state reconstruction (P=1) count was {raw_1} (expected exactly sum(len(t_e)) = {expected_ties_1}); "
            "Raw states must be reconstructed only for members of T_E."
        )
    if expected_ties_4 is not None and raw_4 != expected_ties_4:
        failures.append(
            f"raw state reconstruction (P=4) count was {raw_4} (expected exactly sum(len(t_e)) = {expected_ties_4}); "
            "Raw states must be reconstructed only for members of T_E."
        )

    if failures:
        print("\n[FAIL] Amortisation & runner contract violations detected:")
        for f in failures:
            print(f"   - {f}")
        return 1

    print("\n[PASS] All Gate-5 multi-grid amortisation invariants verified:")
    print("   - Instance validation: strictly amortised (exactly 1 call per run)")
    print("   - Raw domain construction: strictly amortised (exactly 1 BinaryDomain, <= 1 SlackDomainCache)")
    print("   - Decoded & slack preparation: strictly amortised (<= D, <= L, exactly flat)")
    print("   - Prepared domain cache construction: exactly 1 per active encoding (flat)")
    print("   - Coefficient validation: exactly P per run")
    print("   - Prepared energy evaluation: exactly D*P and L*P, scaling exactly 4.0x")
    print("   - Legacy un-amortised evaluators: exactly 0 calls")
    print("   - Raw state reconstruction: exactly matches sum(len(t_e)) across all grid points")
    return 0


# ==============================================================================
# Isolated Test Fixture Protocol (Prevents Unauthorized Primary Execution)
# ==============================================================================

@dataclass(frozen=True)
class AmortisationContractFixture:
    """Explicit isolated test fixture for amortisation acceptance testing.

    Prohibits execution against the canonical Stage-1 primary dataset or full 61^3 grid.
    """
    instance: Any
    coefficients: tuple[Any, ...]
    raw_domain_decoded: tuple[tuple[int, ...], ...]
    raw_domain_slack: tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]
    f_star: float
    lambda_ref: float
    classifier: Any
    expected_D: int
    expected_L: int
    active_encodings: tuple[str, ...] = ("slack", "unbalanced")
    is_contract_fixture: bool = True


def _create_toy_instance(n_tickers: int = 20) -> Any:
    from src.g4.instance import Instance
    if n_tickers == 20:
        return Instance(
            tickers=tuple(f"T{i}" for i in range(20)),
            mu=tuple(0.01 * (i + 1) for i in range(20)),
            sigma=tuple(tuple(0.001 if i == j else 0.0001 for j in range(20)) for i in range(20)),
            prices=tuple(10.0 + i for i in range(20)),
            sectors=((0, 1, 2, 3, 4), (5, 6, 7, 8, 9), (10, 11, 12, 13, 14), (15, 16, 17, 18, 19)),
            kappa_risk=1.0,
            K=6,
            C=2,
            B=100.0,
        )
    return Instance(
        tickers=tuple(f"T{i}" for i in range(n_tickers)),
        mu=tuple(0.01 * (i + 1) for i in range(n_tickers)),
        sigma=tuple(tuple(0.001 if i == j else 0.0001 for j in range(n_tickers)) for i in range(n_tickers)),
        prices=tuple(10.0 + i for i in range(n_tickers)),
        sectors=((0,), (1,), (2,), (3,)),
        kappa_risk=1.0,
        K=2,
        C=1,
        B=50.0,
    )


def _create_toy_coefficients(alpha_offset: float = 0.0) -> Any:
    from src.g4.parameters import Coefficients
    return Coefficients(
        alpha=1.0 + alpha_offset,
        sector_slack=1.0 + alpha_offset,
        budget_slack=1.0 + alpha_offset,
        sector_linear=1.0 + alpha_offset,
        sector_quadratic=1.0 + alpha_offset,
        budget_linear=1.0 + alpha_offset,
        budget_quadratic=1.0 + alpha_offset,
    )


def _create_toy_classifier(instance: Any) -> Any:
    from src.g4.classification import DecodedClassifier, OriginalObjectiveService
    from src.g4.energy import objective, residuals

    def toy_obj(x: tuple[int, ...]) -> float:
        return objective(instance, x)

    def toy_feasible(x: tuple[int, ...]) -> bool:
        # Corrected feasibility sign: h_card == 0, sector residuals >= 0, budget residual >= 0
        h_card, h_sector, h_budget = residuals(instance, x)
        return h_card == 0.0 and all(h >= 0.0 for h in h_sector) and h_budget >= 0.0

    service = OriginalObjectiveService(objective=toy_obj, lambda_ref=10.0, c_f=2048.0)
    return DecodedClassifier(optimum_service=service, feasible=toy_feasible)


def make_isolated_contract_fixture(expected_D: int = 16, expected_L: int = 16) -> AmortisationContractFixture:
    from src.g5.domains import BinaryDomain
    instance = _create_toy_instance(20)
    coeffs = tuple(_create_toy_coefficients(0.1 * i) for i in range(4))
    bin_dom = BinaryDomain(20)
    raw_decoded = tuple(bin_dom[i] for i in range(expected_D))
    aux = (0,) * 19
    raw_slack = tuple((x, aux) for x in raw_decoded[:expected_L])
    classifier = _create_toy_classifier(instance)
    return AmortisationContractFixture(
        instance=instance,
        coefficients=coeffs,
        raw_domain_decoded=raw_decoded,
        raw_domain_slack=raw_slack,
        f_star=-0.5,
        lambda_ref=10.0,
        classifier=classifier,
        expected_D=expected_D,
        expected_L=expected_L,
        active_encodings=("slack", "unbalanced"),
    )


# ==============================================================================
# Adversarial and Compliant Toy Runners for Instrument Self-Test
# ==============================================================================

# Pre-import alias simulation: this reference was bound before instrument() runs
from src.g4.energy import prepare_decoded_state as _PREIMPORTED_PREPARE_DECODED_STATE


def toy_compliant_runner(grid_points: int = 1, fixture: AmortisationContractFixture | None = None) -> None:
    """Fully compliant runner: validates once, prepares once, evaluates prepared."""
    from src.g4.energy import (
        prepare_coefficients,
        prepare_decoded_state,
        prepare_instance,
        prepare_slack_state,
        slack_energy_prepared,
        unbalanced_energy_prepared,
    )
    from src.g5.certify import certify_prepared_domain
    from src.g5.domains import BinaryDomain, PreparedDomainCache

    if fixture is None:
        fixture = make_isolated_contract_fixture()

    instance = fixture.instance
    classifier = fixture.classifier

    # 1. Validation & setup once
    p_inst = prepare_instance(instance)
    # Construct BinaryDomain once
    bin_dom = BinaryDomain(20)
    raw_domain = tuple(bin_dom[i] for i in range(fixture.expected_D))

    # 2. Decoded preparation once
    decoded_states = tuple(prepare_decoded_state(p_inst, x) for x in raw_domain)
    unb_cache = PreparedDomainCache(raw_domain, decoded_states, "unbalanced")

    # 3. Slack preparation once, sharing decoded objects
    aux = (0,) * 19
    slack_states = tuple(prepare_slack_state(dec, aux) for dec in decoded_states)
    slack_raw = tuple((x, aux) for x in raw_domain)
    slk_cache = PreparedDomainCache(slack_raw, slack_states, "slack")

    # 4. Grid loop
    for p_idx in range(grid_points):
        coeff = fixture.coefficients[p_idx % len(fixture.coefficients)]
        p_coeff = prepare_coefficients(coeff)

        # Unbalanced certification
        certify_prepared_domain(
            domain=unb_cache,
            energy_func=lambda s: unbalanced_energy_prepared(s, p_coeff),
            lambda_ref=fixture.lambda_ref,
            f_star=fixture.f_star,
            decode_func=lambda s: s,
            classifier=classifier,
        )

        # Slack certification
        certify_prepared_domain(
            domain=slk_cache,
            energy_func=lambda s: slack_energy_prepared(s, p_coeff),
            lambda_ref=fixture.lambda_ref,
            f_star=fixture.f_star,
            decode_func=lambda s: s[0],
            classifier=classifier,
        )


def toy_adversarial_runner_preimported_alias(grid_points: int = 1, fixture: AmortisationContractFixture | None = None) -> None:
    """Adversarial Runner 1: calls pre-imported function alias inside grid loop."""
    import src.g4.energy as energy
    from src.g5.certify import certify_prepared_domain
    from src.g5.domains import BinaryDomain, PreparedDomainCache

    if fixture is None:
        fixture = make_isolated_contract_fixture()
    instance = fixture.instance
    classifier = fixture.classifier
    p_inst = energy.prepare_instance(instance)
    bin_dom = BinaryDomain(20)
    raw_domain = tuple(bin_dom[i] for i in range(fixture.expected_D))

    for p_idx in range(grid_points):
        # ADVERSARIAL: Uses _PREIMPORTED_PREPARE_DECODED_STATE inside loop
        decoded_states = tuple(_PREIMPORTED_PREPARE_DECODED_STATE(p_inst, x) for x in raw_domain)
        unb_cache = PreparedDomainCache(raw_domain, decoded_states, "unbalanced")

        coeff = fixture.coefficients[p_idx % len(fixture.coefficients)]
        p_coeff = energy.prepare_coefficients(coeff)
        certify_prepared_domain(
            domain=unb_cache,
            energy_func=lambda s: energy.unbalanced_energy_prepared(s, p_coeff),
            lambda_ref=fixture.lambda_ref,
            f_star=fixture.f_star,
            decode_func=lambda s: s,
            classifier=classifier,
        )


def toy_adversarial_runner_namespace_alias(grid_points: int = 1, fixture: AmortisationContractFixture | None = None) -> None:
    """Adversarial Runner 2: calls domains.prepare_decoded_state inside grid loop."""
    import src.g4.energy as energy
    import src.g5.domains as domains
    from src.g5.certify import certify_prepared_domain

    if fixture is None:
        fixture = make_isolated_contract_fixture()
    instance = fixture.instance
    classifier = fixture.classifier
    bin_dom = domains.BinaryDomain(20)
    raw_domain = tuple(bin_dom[i] for i in range(fixture.expected_D))

    for p_idx in range(grid_points):
        # ADVERSARIAL: Preparing inside the loop via domains namespace
        p_inst = domains.prepare_instance(instance)
        decoded_states = tuple(domains.prepare_decoded_state(p_inst, x) for x in raw_domain)
        unb_cache = domains.PreparedDomainCache(raw_domain, decoded_states, "unbalanced")

        coeff = fixture.coefficients[p_idx % len(fixture.coefficients)]
        p_coeff = energy.prepare_coefficients(coeff)
        certify_prepared_domain(
            domain=unb_cache,
            energy_func=lambda s: energy.unbalanced_energy_prepared(s, p_coeff),
            lambda_ref=fixture.lambda_ref,
            f_star=fixture.f_star,
            decode_func=lambda s: s,
            classifier=classifier,
        )


def toy_adversarial_runner_direct_instantiation(grid_points: int = 1, fixture: AmortisationContractFixture | None = None) -> None:
    """Adversarial Runner 3: bypasses functions by directly instantiating dataclasses inside loop."""
    import src.g4.energy as energy
    from src.g5.certify import certify_prepared_domain
    from src.g5.domains import BinaryDomain, PreparedDomainCache

    if fixture is None:
        fixture = make_isolated_contract_fixture()
    instance = fixture.instance
    classifier = fixture.classifier
    bin_dom = BinaryDomain(20)
    raw_domain = tuple(bin_dom[i] for i in range(fixture.expected_D))
    p_inst = energy.prepare_instance(instance)

    for p_idx in range(grid_points):
        # ADVERSARIAL: Direct instantiation of PreparedDecodedState inside the loop
        states = []
        for x in raw_domain:
            xs = energy._x_bits(x)
            f_val = energy._objective_from_bits(p_inst.instance, xs)
            hc, hs, hb = energy._residuals_from_bits(p_inst.instance, xs)
            st = energy.PreparedDecodedState(
                f_value=f_val,
                h_card=hc,
                card_square=hc * hc,
                h_sector=hs,
                sector_square=tuple(r * r for r in hs),
                h_budget=hb,
                budget_square=hb * hb,
            )
            states.append(st)
        unb_cache = PreparedDomainCache(raw_domain, tuple(states), "unbalanced")

        coeff = fixture.coefficients[p_idx % len(fixture.coefficients)]
        p_coeff = energy.prepare_coefficients(coeff)
        certify_prepared_domain(
            domain=unb_cache,
            energy_func=lambda s: energy.unbalanced_energy_prepared(s, p_coeff),
            lambda_ref=fixture.lambda_ref,
            f_star=fixture.f_star,
            decode_func=lambda s: s,
            classifier=classifier,
        )


def toy_adversarial_runner_multiple_preparation_outside_loop(grid_points: int = 1, fixture: AmortisationContractFixture | None = None) -> None:
    """Adversarial Runner 4: prepares 5 times outside loop (flat across P, but count > D)."""
    import src.g4.energy as energy
    from src.g5.certify import certify_prepared_domain
    from src.g5.domains import BinaryDomain, PreparedDomainCache

    if fixture is None:
        fixture = make_isolated_contract_fixture()
    instance = fixture.instance
    classifier = fixture.classifier
    bin_dom = BinaryDomain(20)
    raw_domain = tuple(bin_dom[i] for i in range(fixture.expected_D))
    p_inst = energy.prepare_instance(instance)

    # ADVERSARIAL: Repeated preparation 5 times outside loop
    for _ in range(5):
        decoded_states = tuple(energy.prepare_decoded_state(p_inst, x) for x in raw_domain)
    unb_cache = PreparedDomainCache(raw_domain, decoded_states, "unbalanced")

    for p_idx in range(grid_points):
        coeff = fixture.coefficients[p_idx % len(fixture.coefficients)]
        p_coeff = energy.prepare_coefficients(coeff)
        certify_prepared_domain(
            domain=unb_cache,
            energy_func=lambda s: energy.unbalanced_energy_prepared(s, p_coeff),
            lambda_ref=fixture.lambda_ref,
            f_star=fixture.f_star,
            decode_func=lambda s: s,
            classifier=classifier,
        )


def toy_adversarial_runner_repeated_binary_domain_construction(grid_points: int = 1, fixture: AmortisationContractFixture | None = None) -> None:
    """Adversarial Runner 5: constructs BinaryDomain 5 times outside loop."""
    import src.g4.energy as energy
    from src.g5.certify import certify_prepared_domain
    from src.g5.domains import BinaryDomain, PreparedDomainCache

    if fixture is None:
        fixture = make_isolated_contract_fixture()
    instance = fixture.instance
    classifier = fixture.classifier
    p_inst = energy.prepare_instance(instance)

    # ADVERSARIAL: Reconstructs BinaryDomain 5 times outside loop
    for _ in range(5):
        bin_dom = BinaryDomain(20)
    raw_domain = tuple(bin_dom[i] for i in range(fixture.expected_D))
    decoded_states = tuple(energy.prepare_decoded_state(p_inst, x) for x in raw_domain)
    unb_cache = PreparedDomainCache(raw_domain, decoded_states, "unbalanced")

    for p_idx in range(grid_points):
        coeff = fixture.coefficients[p_idx % len(fixture.coefficients)]
        p_coeff = energy.prepare_coefficients(coeff)
        certify_prepared_domain(
            domain=unb_cache,
            energy_func=lambda s: energy.unbalanced_energy_prepared(s, p_coeff),
            lambda_ref=fixture.lambda_ref,
            f_star=fixture.f_star,
            decode_func=lambda s: s,
            classifier=classifier,
        )


def toy_adversarial_runner_excess_cache_construction(grid_points: int = 1, fixture: AmortisationContractFixture | None = None) -> None:
    """Adversarial Runner 6: constructs 3 PreparedDomainCache instances for single encoding."""
    import src.g4.energy as energy
    from src.g5.certify import certify_prepared_domain
    from src.g5.domains import BinaryDomain, PreparedDomainCache

    if fixture is None:
        fixture = make_isolated_contract_fixture()
    instance = fixture.instance
    classifier = fixture.classifier
    p_inst = energy.prepare_instance(instance)
    bin_dom = BinaryDomain(20)
    raw_domain = tuple(bin_dom[i] for i in range(fixture.expected_D))
    decoded_states = tuple(energy.prepare_decoded_state(p_inst, x) for x in raw_domain)

    # ADVERSARIAL: Constructs 3 caches when 1 expected
    unb_cache_1 = PreparedDomainCache(raw_domain, decoded_states, "unbalanced")
    unb_cache_2 = PreparedDomainCache(raw_domain, decoded_states, "unbalanced")
    unb_cache_3 = PreparedDomainCache(raw_domain, decoded_states, "unbalanced")

    for p_idx in range(grid_points):
        coeff = fixture.coefficients[p_idx % len(fixture.coefficients)]
        p_coeff = energy.prepare_coefficients(coeff)
        certify_prepared_domain(
            domain=unb_cache_3,
            energy_func=lambda s: energy.unbalanced_energy_prepared(s, p_coeff),
            lambda_ref=fixture.lambda_ref,
            f_star=fixture.f_star,
            decode_func=lambda s: s,
            classifier=classifier,
        )


def toy_adversarial_runner_legacy_evaluator(grid_points: int = 1, fixture: AmortisationContractFixture | None = None) -> None:
    """Adversarial Runner 7: invokes legacy un-amortised energy evaluator inside loop."""
    import src.g4.energy as energy
    from src.g5.domains import BinaryDomain

    if fixture is None:
        fixture = make_isolated_contract_fixture()
    instance = fixture.instance
    bin_dom = BinaryDomain(20)
    raw_domain = tuple(bin_dom[i] for i in range(fixture.expected_D))

    for p_idx in range(grid_points):
        coeff = fixture.coefficients[p_idx % len(fixture.coefficients)]
        for x in raw_domain:
            _ = energy.unbalanced_energy(instance, x, coeff)


def toy_adversarial_runner_domain_rebuild_in_loop(grid_points: int = 1, fixture: AmortisationContractFixture | None = None) -> None:
    """Adversarial Runner 8: rebuilds slack domain cache inside loop."""
    from src.g5.domains import build_slack_domain_cache

    toy_instance = _create_toy_instance(n_tickers=4)
    coeff = _create_toy_coefficients()

    for _ in range(grid_points):
        # ADVERSARIAL: Rebuilding slack domain cache per grid point
        _ = build_slack_domain_cache(toy_instance, coeff, 2, 11)


def toy_adversarial_runner_partial_excess_raw_reconstruction(grid_points: int = 1, fixture: AmortisationContractFixture | None = None) -> None:
    """Adversarial Runner 9: reconstructs 6 states when tie set has 1 state."""
    import src.g4.energy as energy
    from src.g5.domains import BinaryDomain, PreparedDomainCache
    from src.g5.certify import certify_prepared_domain, decode_x_e, classify_t_e

    if fixture is None:
        fixture = make_isolated_contract_fixture()
    instance = fixture.instance
    classifier = fixture.classifier
    p_inst = energy.prepare_instance(instance)
    bin_dom = BinaryDomain(20)
    raw_domain = tuple(bin_dom[i] for i in range(fixture.expected_D))
    decoded_states = tuple(energy.prepare_decoded_state(p_inst, x) for x in raw_domain)
    unb_cache = PreparedDomainCache(raw_domain, decoded_states, "unbalanced")

    for p_idx in range(grid_points):
        coeff = fixture.coefficients[p_idx % len(fixture.coefficients)]
        p_coeff = energy.prepare_coefficients(coeff)
        # Normal certification
        certify_prepared_domain(
            domain=unb_cache,
            energy_func=lambda s: energy.unbalanced_energy_prepared(s, p_coeff),
            lambda_ref=fixture.lambda_ref,
            f_star=fixture.f_star,
            decode_func=lambda s: s,
            classifier=classifier,
        )
        # ADVERSARIAL: Extra raw state reconstruction of 6 states (partial, fewer than 16)
        extra_raw = [unb_cache.raw_state(i) for i in range(6)]
        _ = decode_x_e(extra_raw, lambda s: s)


def toy_adversarial_runner_eager_raw_reconstruction_p4_only(grid_points: int = 1, fixture: AmortisationContractFixture | None = None) -> None:
    """Adversarial Runner 10: reconstructs ties on P=1, but eagerly reconstructs all states on P=4."""
    import src.g4.energy as energy
    from src.g5.domains import BinaryDomain, PreparedDomainCache
    from src.g5.certify import decode_x_e, classify_t_e, certify_prepared_domain

    if fixture is None:
        fixture = make_isolated_contract_fixture()
    instance = fixture.instance
    classifier = fixture.classifier
    p_inst = energy.prepare_instance(instance)
    bin_dom = BinaryDomain(20)
    raw_domain = tuple(bin_dom[i] for i in range(fixture.expected_D))
    decoded_states = tuple(energy.prepare_decoded_state(p_inst, x) for x in raw_domain)
    unb_cache = PreparedDomainCache(raw_domain, decoded_states, "unbalanced")

    for p_idx in range(grid_points):
        coeff = fixture.coefficients[p_idx % len(fixture.coefficients)]
        p_coeff = energy.prepare_coefficients(coeff)
        certify_prepared_domain(
            domain=unb_cache,
            energy_func=lambda s: energy.unbalanced_energy_prepared(s, p_coeff),
            lambda_ref=fixture.lambda_ref,
            f_star=fixture.f_star,
            decode_func=lambda s: s,
            classifier=classifier,
        )
        if grid_points == 4:
            # ADVERSARIAL: Eager reconstruction of all 16 states ONLY when running P=4
            all_raw = [unb_cache.raw_state(i) for i in range(len(unb_cache))]
            x_e = decode_x_e(all_raw, lambda s: s)
            _ = classify_t_e(x_e, classifier, -0.5)


def run_self_test() -> int:
    """Verify that v2.2 instrument correctly catches all adversarial runners and passes compliant runner."""
    print("================================================================================")
    print("STARTING AMORTISATION INSTRUMENT V2.2 SELF-TEST BATTERY")
    print("================================================================================\n")

    instrument()
    fixture = make_isolated_contract_fixture()

    tests: list[tuple[str, Callable[..., None], bool, tuple[str, ...]]] = [
        ("Honest Compliant Runner", toy_compliant_runner, True, ("slack", "unbalanced")),
        ("Adversarial Runner 1 (Pre-Imported Function Alias)", toy_adversarial_runner_preimported_alias, False, ("unbalanced",)),
        ("Adversarial Runner 2 (Namespace Alias via domains)", toy_adversarial_runner_namespace_alias, False, ("unbalanced",)),
        ("Adversarial Runner 3 (Direct Dataclass Instantiation)", toy_adversarial_runner_direct_instantiation, False, ("unbalanced",)),
        ("Adversarial Runner 4 (Multiple Preparation Outside Loop)", toy_adversarial_runner_multiple_preparation_outside_loop, False, ("unbalanced",)),
        ("Adversarial Runner 5 (Repeated BinaryDomain Construction)", toy_adversarial_runner_repeated_binary_domain_construction, False, ("unbalanced",)),
        ("Adversarial Runner 6 (Excess Cache Construction)", toy_adversarial_runner_excess_cache_construction, False, ("unbalanced",)),
        ("Adversarial Runner 7 (Legacy Evaluator Call)", toy_adversarial_runner_legacy_evaluator, False, ("unbalanced",)),
        ("Adversarial Runner 8 (Domain Cache Rebuild in Loop)", toy_adversarial_runner_domain_rebuild_in_loop, False, ("slack",)),
        ("Adversarial Runner 9 (Partial Excess Raw Reconstruction)", toy_adversarial_runner_partial_excess_raw_reconstruction, False, ("unbalanced",)),
        ("Adversarial Runner 10 (Eager Raw Reconstruction on P=4 Only)", toy_adversarial_runner_eager_raw_reconstruction_p4_only, False, ("unbalanced",)),
    ]

    all_passed = True
    for test_name, runner_fn, should_pass, active_encs in tests:
        print(f"\n--- Testing: {test_name} (Expected result: {'PASS' if should_pass else 'FAIL'}) ---")
        CALLS.clear()
        CERTIFIED_T_E_LENGTHS.clear()
        runner_fn(1, fixture=fixture)
        one = report("P = 1")
        ties_1 = sum(CERTIFIED_T_E_LENGTHS)

        CALLS.clear()
        CERTIFIED_T_E_LENGTHS.clear()
        runner_fn(4, fixture=fixture)
        four = report("P = 4")
        ties_4 = sum(CERTIFIED_T_E_LENGTHS)

        code = verdict(
            one,
            four,
            expected_D=fixture.expected_D,
            expected_L=fixture.expected_L,
            active_encodings=active_encs,
            expected_ties_1=ties_1,
            expected_ties_4=ties_4,
        )
        passed = (code == 0)
        if passed == should_pass:
            print(f"[OK] Self-test verified for '{test_name}' (exit code {code})")
        else:
            print(f"[ERROR] Self-test FAILED for '{test_name}': expected pass={should_pass}, got exit code {code}")
            all_passed = False

    print("\n================================================================================")
    if all_passed:
        print(f"SELF-TEST BATTERY COMPLETE: ALL {len(tests)} TEST CASES BEHAVED AS EXPECTED (100% SUCCESS)")
        print("================================================================================")
        return 0
    else:
        print("SELF-TEST BATTERY FAILED ON ONE OR MORE CASES")
        print("================================================================================")
        return 1


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2

    if argv[1] == "--self-test":
        return run_self_test()

    if ":" not in argv[1]:
        print("Error: Target must be specified as <module_path>:<callable_name>")
        return 2

    mod_name, func_name = argv[1].split(":", 1)
    instrument()
    entry = getattr(importlib.import_module(mod_name), func_name)

    fixture = make_isolated_contract_fixture()

    try:
        CALLS.clear()
        CERTIFIED_T_E_LENGTHS.clear()
        entry(grid_points=1, fixture=fixture)
        one = report("P = 1")
        ties_1 = sum(CERTIFIED_T_E_LENGTHS)

        CALLS.clear()
        CERTIFIED_T_E_LENGTHS.clear()
        entry(grid_points=4, fixture=fixture)
        four = report("P = 4")
        ties_4 = sum(CERTIFIED_T_E_LENGTHS)
    except TypeError as exc:
        print(f"\n[FAIL CLOSED] Target {mod_name}:{func_name} does not accept the mandatory isolated AmortisationContractFixture.")
        print("To prevent unauthorized primary execution, the amortisation instrument requires targets to accept fixture=<AmortisationContractFixture>.")
        print(f"Error details: {exc}")
        return 2

    return verdict(
        one,
        four,
        expected_D=fixture.expected_D,
        expected_L=fixture.expected_L,
        active_encodings=fixture.active_encodings,
        expected_ties_1=ties_1,
        expected_ties_4=ties_4,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
