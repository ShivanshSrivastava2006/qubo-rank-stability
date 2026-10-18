from fractions import Fraction
import math

def detection_probability(n: int, c: int, k: int) -> Fraction:
    if c == 0 or k == 0: return Fraction(0)
    if c > n - k: return Fraction(1)
    return 1 - Fraction(math.perm(n - c, k), math.perm(n, k))

def required_sample_size(n: int, c: int, target: Fraction) -> int:
    target_log_miss = math.log(1.0 - float(target)) if float(target) < 1.0 else -math.inf
    k = 0
    log_miss = 0.0
    limit = n - c
    while k < limit and log_miss > target_log_miss:
        log_miss += math.log(n - c - k) - math.log(n - k)
        k += 1
    if k == 0: k = 1
    while k > 1 and detection_probability(n, c, k - 1) >= target:
        k -= 1
    while k < n and detection_probability(n, c, k) < target:
        k += 1
    return k

def true_required_sample_size(n, c, target):
    for k in range(1, n+1):
        if detection_probability(n, c, k) >= target:
            return k
    return n

print("Testing...")
for n in [10, 100, 1000]:
    for c in range(1, n+1):
        for t_num in [1, 50, 99]:
            target = Fraction(t_num, 100)
            res = required_sample_size(n, c, target)
            tru = true_required_sample_size(n, c, target)
            if res != tru:
                print(f"FAILED! n={n}, c={c}, target={target}: expected {tru}, got {res}")
print("Done.")
