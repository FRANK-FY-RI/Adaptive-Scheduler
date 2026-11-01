"""Input validation before any engine is touched (docs/INTERFACES.md §4).

Every error names the offending row (file line or job_id) and field. Validation stops
at the first error.
"""
from __future__ import annotations

from typing import Sequence

from adaptivesched.experiments.adapter import JobSpec


class ValidationError(ValueError):
    """Bad workload, CPU core capacity or strategy identifier."""


def check_cluster_cores(cluster_cores) -> None:
    if isinstance(cluster_cores, bool) or not isinstance(cluster_cores, int) or cluster_cores <= 0:
        raise ValidationError(f"cluster_cores must be an integer > 0, got {cluster_cores!r}")


def check_strategy(strategy_id: str, available: Sequence[str]) -> None:
    if strategy_id not in available:
        raise ValidationError(f"strategy: unknown identifier {strategy_id!r}; "
                              f"available: {', '.join(available)}")


def validate_jobs(jobs: Sequence[JobSpec], cluster_cores: int | None = None,
                  locations: Sequence[str] | None = None) -> None:
    """Check every job. `locations[i]` names job i in errors (e.g. 'w.csv line 7').

    cluster_cores=None skips only the capacity check (a CSV can be loaded before the
    capacity is chosen); the runner always validates again with the capacity.
    """
    if cluster_cores is not None:
        check_cluster_cores(cluster_cores)
    if not jobs:
        raise ValidationError("workload has no jobs")
    first_seen: dict[int, str] = {}
    for i, j in enumerate(jobs):
        at = locations[i] if locations else f"job_id {j.job_id}"
        if j.job_id in first_seen:
            raise ValidationError(f"{at}, field job_id: duplicate job_id {j.job_id} "
                                  f"(first at {first_seen[j.job_id]})")
        first_seen[j.job_id] = at
        if j.arrival_time < 0:
            raise ValidationError(f"{at}, field arrival_time: must be >= 0, got {j.arrival_time}")
        if j.runtime <= 0:
            raise ValidationError(f"{at}, field runtime: must be > 0, got {j.runtime}")
        if j.required_cores <= 0:
            raise ValidationError(f"{at}, field required_cores: must be > 0, got {j.required_cores}")
        if cluster_cores is not None and j.required_cores > cluster_cores:
            raise ValidationError(
                f"{at}, field required_cores: job {j.job_id} needs {j.required_cores} CPU cores "
                f"but the cluster has {cluster_cores}; it could never start")
