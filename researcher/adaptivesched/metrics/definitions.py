"""The only place a metric is computed (CLAUDE.md hard rule 3).

Each function is pure over per-job execution records and raises on an empty run.
Times are integer simulation time units; CPU cores are integers.

Preemption: a job may run in several segments. Its waiting time is all the time it spent
not running between arrival and completion, finish - arrival - runtime. For a job that ran
in one segment this is exactly start - arrival (RES §6); for a preempted job it adds every
wait between segments, so it never hides time a job spent suspended.
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


def _wait(r: JobRecord) -> int:
    return r.finish_time - r.arrival_time - r.runtime


def _slowdown(r: JobRecord, tau: int) -> float:
    return max(1.0, (r.finish_time - r.arrival_time) / max(r.runtime, tau))


def completed_jobs(records: Sequence[JobRecord]) -> int:
    """number of job records (the engine writes one per completed job)."""
    return len(_nonempty(records))


def average_waiting_time(records: Sequence[JobRecord]) -> float:
    """mean over jobs of (finish_time - arrival_time - runtime); = start - arrival when not preempted."""
    return fmean(_wait(r) for r in _nonempty(records))


def max_waiting_time(records: Sequence[JobRecord]) -> int:
    """max over jobs of (finish_time - arrival_time - runtime): the job that paid most."""
    return max(_wait(r) for r in _nonempty(records))


def average_turnaround_time(records: Sequence[JobRecord]) -> float:
    """mean over jobs of (finish_time - arrival_time)."""
    return fmean(r.finish_time - r.arrival_time for r in _nonempty(records))


def makespan(records: Sequence[JobRecord]) -> int:
    """max(finish_time) - min(arrival_time): first arrival to last completion."""
    records = _nonempty(records)
    return max(r.finish_time for r in records) - min(r.arrival_time for r in records)


def cpu_utilization_pct(records: Sequence[JobRecord], cluster_cores: int) -> float:
    """100 x sum(required_cores x runtime) / (cluster_cores x makespan).

    Interval: first arrival to last completion (the makespan interval). A preempted job's
    segments add up to its runtime, so it counts its core-time once.
    """
    busy = sum(r.required_cores * r.runtime for r in _nonempty(records))
    return 100 * busy / (cluster_cores * makespan(records))


def throughput(records: Sequence[JobRecord]) -> float:
    """completed jobs / makespan, in jobs per time unit."""
    return completed_jobs(records) / makespan(records)


def bounded_slowdown(records: Sequence[JobRecord], tau: int = TAU) -> float:
    """mean over jobs of max(1, (finish_time - arrival_time) / max(runtime, tau)).

    finish - arrival = waiting time + runtime. tau keeps very short jobs from dominating the
    mean with huge ratios.
    """
    return fmean(_slowdown(r, tau) for r in _nonempty(records))


def fairness_index(records: Sequence[JobRecord], tau: int = TAU) -> float:
    """Jain's index over per-job bounded slowdowns x_j: (sum x)^2 / (n * sum x^2), in (0, 1].

    1 means every job was slowed down by the same factor; 1/n means one job took all of it.
    Job-level fairness: workloads carry no user field, so user-level fair share is not defined.
    """
    xs = [_slowdown(r, tau) for r in _nonempty(records)]
    return sum(xs) ** 2 / (len(xs) * sum(x * x for x in xs))


def total_preemptions(records: Sequence[JobRecord]) -> int:
    """sum over jobs of preemption_count."""
    return sum(r.preemption_count for r in _nonempty(records))
