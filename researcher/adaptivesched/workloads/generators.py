"""Named synthetic workloads (SPEC §1.2).

Each workload is a pure function of (name, seed, n_jobs, cluster_cores, runtime_estimate_error)
using numpy.random.default_rng(seed). Draw order is fixed: runtimes, CPU cores, inter-arrival gaps.

Arrivals are a Poisson process: the first job arrives at 0, later ones at the floor of the
cumulative exponential gaps. The mean gap is set so the offered load is

    rho = mean(runtime x required_cores) / (cluster_cores x mean_interarrival)

computed on the drawn jobs: rho = 0.5 for `light`, 1.0 for every congested condition. With
the same seed, `heavy` is exactly `light` with every gap halved; only congestion differs.
"""
from __future__ import annotations

import math
import re

import numpy as np

from adaptivesched.experiments.adapter import JobSpec
from adaptivesched.workloads.loader import Workload
from adaptivesched.workloads.validate import ValidationError, check_cluster_cores, validate_jobs


def _lognormal_runtimes(rng, n, sigma, median=60):
    return np.maximum(1, np.rint(median * np.exp(sigma * rng.standard_normal(n))))


def _cores(rng, n, lo, hi):
    return rng.integers(lo, max(lo, hi) + 1, n)  # inclusive; at least one value


def _light(rng, n, c):
    return _lognormal_runtimes(rng, n, 0.5), _cores(rng, n, 1, c // 4)


def _short_heavy(rng, n, c):
    is_long = np.zeros(n, dtype=bool)
    is_long[rng.choice(n, round(0.1 * n), replace=False)] = True
    runtimes = np.where(is_long, rng.integers(600, 3001, n), rng.integers(5, 31, n))
    return runtimes, _cores(rng, n, 1, c // 8)


def _mixed(rng, n, c):
    return _lognormal_runtimes(rng, n, 1.5), _cores(rng, n, 1, math.floor(0.6 * c))


def _wide_jobs(rng, n, c):
    return _lognormal_runtimes(rng, n, 0.5), _cores(rng, n, math.ceil(c / 2), c)


# name: (offered load, sampler, description)
GENERATORS = {
    "light": (0.5, _light, "runtime lognormal(median 60, sigma 0.5); CPU cores 1..25% of capacity"),
    "heavy": (1.0, _light, "as light, inter-arrival gaps halved"),
    "short_heavy": (1.0, _short_heavy, "90% runtime 5..30, 10% runtime 600..3000; CPU cores 1..12.5%"),
    "mixed": (1.0, _mixed, "runtime lognormal(median 60, sigma 1.5); CPU cores 1..60%"),
    "wide_jobs": (1.0, _wide_jobs, "runtime lognormal(median 60, sigma 0.5); CPU cores 50..100%"),
}

_ID = re.compile(r"synth:(?P<name>\w+):n=(?P<n>\d+):seed=(?P<seed>\d+)")


def generate(name: str, seed: int, n_jobs: int, cluster_cores: int,
             runtime_estimate_error: float = 0.0) -> Workload:
    if name not in GENERATORS:
        raise ValidationError(f"workload: unknown generator {name!r}; available: {', '.join(GENERATORS)}")
    if runtime_estimate_error != 0.0:
        raise ValidationError("runtime_estimate_error must be 0.0 in this iteration (exact runtimes), "
                              f"got {runtime_estimate_error}")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValidationError(f"seed must be an integer >= 0, got {seed!r}")
    if isinstance(n_jobs, bool) or not isinstance(n_jobs, int) or n_jobs <= 0:
        raise ValidationError(f"n_jobs must be an integer > 0, got {n_jobs!r}")
    check_cluster_cores(cluster_cores)

    load, sampler, _ = GENERATORS[name]
    rng = np.random.default_rng(seed)
    runtimes, cores = sampler(rng, n_jobs, cluster_cores)
    mean_interarrival = float(np.mean(runtimes * cores)) / (load * cluster_cores)
    gaps = rng.exponential(mean_interarrival, n_jobs)
    gaps[0] = 0.0
    arrivals = np.floor(np.cumsum(gaps))

    jobs = tuple(JobSpec(i + 1, int(a), int(r), int(c))
                 for i, (a, r, c) in enumerate(zip(arrivals, runtimes, cores)))
    validate_jobs(jobs, cluster_cores)  # guards against a generator bug
    return Workload(f"synth:{name}:n={n_jobs}:seed={seed}", jobs, {
        "source": "synthetic", "generator": name, "seed": seed, "n_jobs": n_jobs,
        "cluster_cores": cluster_cores, "offered_load": load,
        "mean_interarrival": round(mean_interarrival, 6),
        "runtime_estimate_error": runtime_estimate_error,
    })


def from_id(workload_id: str, cluster_cores: int) -> Workload:
    """Rebuild a synthetic workload from its id. The id plus cluster_cores reproduces it."""
    m = _ID.fullmatch(workload_id)
    if not m:
        raise ValidationError(f"workload: {workload_id!r} is not a synthetic id; "
                              "expected synth:<name>:n=<n_jobs>:seed=<seed>")
    return generate(m["name"], int(m["seed"]), int(m["n"]), cluster_cores)
