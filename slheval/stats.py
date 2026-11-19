"""Small statistics helpers, standard library only."""
from __future__ import annotations

import math
import random

DEFAULT_SEED = 20261119


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else float("nan")


def wilson_ci(k, n, z=1.959964):
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return centre - half, centre + half


def bootstrap_ci(values, n_boot=10000, seed=DEFAULT_SEED, alpha=0.05):
    """Percentile bootstrap CI for the mean, resampling items (or paired differences)."""
    vals = list(values)
    n = len(vals)
    if n == 0:
        return float("nan"), float("nan")
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        total = 0.0
        for _ in range(n):
            total += vals[rng.randrange(n)]
        means.append(total / n)
    means.sort()
    lo = means[int((alpha / 2) * n_boot)]
    hi = means[int((1 - alpha / 2) * n_boot) - 1]
    return lo, hi
