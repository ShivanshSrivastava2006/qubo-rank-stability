import math
from collections.abc import Callable, Iterable
from src.g4.classification import DecodedClassifier
from src.g5.domains import PreparedDomainCache

def find_ground_state(domain: Iterable, energy_func: Callable) -> tuple[float, list]:
    """
    Exact minimum over a supplied domain using a supplied energy callable.
    Returns (H_E_min, argmin_list).
    """
    if iter(domain) is domain:
        raise TypeError("domain must be a re-iterable sequence, not a one-shot iterator")
        
    min_energy = None
    min_states = []
    for z in domain:
        energy = float(energy_func(z))
        if not math.isfinite(energy):
            raise ValueError("Energy must be finite")
        if min_energy is None or energy < min_energy:
            min_energy = energy
            min_states = [z]
        elif energy == min_energy:
            min_states.append(z)
            
    if min_energy is None:
        raise ValueError("Domain is empty")
    return min_energy, min_states


def construct_t_e(domain: Iterable, energy_func: Callable, h_e_min: float, lambda_ref: float, c_h: float = 2048.0) -> list:
    """
    T_E = { z in C_E : gap(H_E(z), H_E_min) <= tau }
    gap = abs(fl(y-y'))
    m = max(abs(y),abs(y'))
    scale = fl(Lambda_ref+m)
    tau = fl((c_H*epsilon)*scale)
    """
    if iter(domain) is domain:
        raise TypeError("domain must be a re-iterable sequence, not a one-shot iterator")
        
    if not math.isfinite(lambda_ref) or lambda_ref <= 0.0:
        raise ValueError("lambda_ref must be finite and positive")
    if not math.isfinite(c_h) or c_h <= 0.0:
        raise ValueError("c_h must be finite and positive")
        
    epsilon = math.ldexp(1.0, -52)
    t_e = []
    
    for z in domain:
        y = float(energy_func(z))
        y_prime = float(h_e_min)
        
        diff = y - y_prime
        if not math.isfinite(diff):
            raise ValueError("nonfinite difference")
        gap = abs(diff)
        m = max(abs(y), abs(y_prime))
        scale = lambda_ref + m
        if not math.isfinite(scale):
            raise ValueError("nonfinite scale")
        tau = (c_h * epsilon) * scale
        if not math.isfinite(tau):
            raise ValueError("nonfinite tau")
            
        if gap <= tau:
            t_e.append(z)
            
    return t_e


def decode_x_e(t_e: Iterable, decode_func: Callable) -> list:
    """
    X_E = { decode(z) : z in T_E }, deduplicated in first-seen order.

    Frozen decoded states are tuples and therefore hashable. A non-hashable
    decoder result fails closed instead of falling back to a quadratic scan.
    """
    seen = set()
    x_e = []
    for z in t_e:
        x = decode_func(z)
        if x not in seen:
            seen.add(x)
            x_e.append(x)
    return x_e


def classify_t_e(x_e: Iterable, classifier: DecodedClassifier, f_star: float) -> str:
    """
    Wire to D016 labelling.
    Receives only decoded x and frozen f*.
    """
    return classifier.label_set(x_e, f_star)


import array

def certify_domain(domain_factory: Callable[[], Iterable], energy_func: Callable, lambda_ref: float, f_star: float, decode_func: Callable, classifier: DecodedClassifier, c_h: float = 2048.0) -> tuple:
    '''
    Evaluates energies once into a flat float array.
    Finds H_E_min, T_E, X_E and the D016 label without materializing the full domain at once.
    '''
    if not math.isfinite(lambda_ref) or lambda_ref <= 0.0:
        raise ValueError("lambda_ref must be finite and positive")
    if not math.isfinite(c_h) or c_h <= 0.0:
        raise ValueError("c_h must be finite and positive")
        
    epsilon = math.ldexp(1.0, -52)
    energies = array.array('d')
    
    # First pass: compute all energies
    domain_iter = domain_factory()
    for z in domain_iter:
        energy = float(energy_func(z))
        if not math.isfinite(energy):
            raise ValueError("Energy must be finite")
        energies.append(energy)
        
    if not energies:
        raise ValueError("Domain is empty")
        
    h_e_min = min(energies)
    
    # Second pass: construct T_E using precomputed energies
    t_e = []
    domain_iter_2 = domain_factory()
    
    # Check that lengths match
    idx = 0
    for z in domain_iter_2:
        if idx >= len(energies):
            raise RuntimeError("domain_factory returned more elements on second pass")
        y = energies[idx]
        idx += 1
        
        y_prime = float(h_e_min)
        diff = y - y_prime
        gap = abs(diff)
        m = max(abs(y), abs(y_prime))
        scale = lambda_ref + m
        if not math.isfinite(scale):
            raise ValueError("nonfinite scale")
        tau = (c_h * epsilon) * scale
        if not math.isfinite(tau):
            raise ValueError("nonfinite tau")
            
        if gap <= tau:
            t_e.append(z)
            
    if idx != len(energies):
        raise RuntimeError("domain_factory returned fewer elements on second pass")
        
    x_e = decode_x_e(t_e, decode_func)
    label = classify_t_e(x_e, classifier, f_star)
    
    return h_e_min, t_e, x_e, label


def certify_prepared_domain(
    domain: PreparedDomainCache,
    energy_func: Callable,
    lambda_ref: float,
    f_star: float,
    decode_func: Callable,
    classifier: DecodedClassifier,
    c_h: float = 2048.0,
) -> tuple:
    """Certify a domain prepared once outside the coefficient-grid loop.

    Raw states are reconstructed only for members of T_E. Requiring the typed
    cache prevents a raw iterator or rebuilding factory from silently entering
    the core-pass hot loop.
    """
    if not isinstance(domain, PreparedDomainCache):
        raise TypeError("domain must be a PreparedDomainCache built outside the grid loop")
    if not math.isfinite(lambda_ref) or lambda_ref <= 0.0:
        raise ValueError("lambda_ref must be finite and positive")
    if not math.isfinite(c_h) or c_h <= 0.0:
        raise ValueError("c_h must be finite and positive")

    epsilon = math.ldexp(1.0, -52)
    energies = array.array("d")
    h_e_min = None
    for state in domain:
        energy = float(energy_func(state))
        if not math.isfinite(energy):
            raise ValueError("Energy must be finite")
        energies.append(energy)
        if h_e_min is None or energy < h_e_min:
            h_e_min = energy
    if h_e_min is None:
        raise ValueError("Domain is empty")

    tied_indices = []
    for index, y in enumerate(energies):
        diff = y - h_e_min
        if not math.isfinite(diff):
            raise ValueError("nonfinite difference")
        gap = abs(diff)
        m = max(abs(y), abs(h_e_min))
        scale = lambda_ref + m
        if not math.isfinite(scale):
            raise ValueError("nonfinite scale")
        tau = (c_h * epsilon) * scale
        if not math.isfinite(tau):
            raise ValueError("nonfinite tau")
        if gap <= tau:
            tied_indices.append(index)

    t_e = [domain.raw_state(index) for index in tied_indices]
    x_e = decode_x_e(t_e, decode_func)
    label = classify_t_e(x_e, classifier, f_star)
    return h_e_min, t_e, x_e, label
