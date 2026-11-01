"""The only place a metric is computed (CLAUDE.md hard rule 3).

Each function is pure over per-job execution records and raises on an empty run.
Times are integer simulation time units; CPU cores are integers.
"""
from __future__ import annotations

from statistics import fmean
from typing import Sequence

from adaptivesched.experiments.adapter import JobRecord

TAU = 10  # bounded-slowdown threshold, time units; same for every strategy (RES §6)


def _nonempty(records: Sequence[JobRecord]) -> Sequence[JobRecord]:
    if not records:
        raise ValueError("metrics are undefined on a run with no job records")
    return records


def average_waiting_time(records: Sequence[JobRecord]) -> float:
    """mean over jobs of (start_time - arrival_time)."""
    return fmean(r.start_time - r.arrival_time for r in _nonempty(records))


def max_waiting_time(records: Sequence[JobRecord]) -> int:
    """max over jobs of (start_time - arrival_time): the job that paid most."""
    return max(r.start_time - r.arrival_time for r in _nonempty(records))


def average_turnaround_time(records: Sequence[JobRecord]) -> float:
    """mean over jobs of (finish_time - arrival_time)."""
    return fmean(r.finish_time - r.arrival_time for r in _nonempty(records))


def makespan(records: Sequence[JobRecord]) -> int:
    """max(finish_time) - min(arrival_time): first arrival to last completion."""
    records = _nonempty(records)
    return max(r.finish_time for r in records) - min(r.arrival_time for r in records)


def cpu_utilization_pct(records: Sequence[JobRecord], cluster_cores: int) -> float:
    """100 x sum(required_cores x runtime) / (cluster_cores x makespan).

    Interval: first arrival to last completion (the makespan interval).
    """
    busy = sum(r.required_cores * r.runtime for r in _nonempty(records))
    return 100 * busy / (cluster_cores * makespan(records))


def bounded_slowdown(records: Sequence[JobRecord], tau: int = TAU) -> float:
    """mean over jobs of max(1, (waiting_time + runtime) / max(runtime, tau)).

    tau keeps very short jobs from dominating the mean with huge ratios.
    """
    return fmean(max(1.0, ((r.start_time - r.arrival_time) + r.runtime) / max(r.runtime, tau))
                 for r in _nonempty(records))
