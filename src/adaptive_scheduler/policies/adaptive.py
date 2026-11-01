"""Multi-heuristic adaptive scheduling policy with starvation protection."""

from __future__ import annotations

import math
from typing import TypeAlias

from adaptive_scheduler.exceptions import ConfigurationError
from adaptive_scheduler.models import JobId, SchedulerContext, make_job_sort_key

AdaptiveWeights: TypeAlias = tuple[float, float, float]


class AdaptivePolicy:
    """Ranks runnable jobs using waiting-time, runtime, and core-count heuristics.

    The waiting-time weight grows with observed waiting pressure relative to the
    mean runtime of the current queue. This lets short jobs perform well under
    normal load while progressively protecting jobs that have waited too long.
    """

    name = "Adaptive Multi-Heuristic"

    def __init__(self, *, base_wait_weight: float = 0.1) -> None:
        if (
            isinstance(base_wait_weight, bool)
            or not isinstance(base_wait_weight, (int, float))
            or not math.isfinite(base_wait_weight)
            or base_wait_weight <= 0
        ):
            raise ConfigurationError("base_wait_weight must be a finite positive number.")
        self.base_wait_weight = float(base_wait_weight)

    def compute_adaptive_weights(self, context: SchedulerContext) -> AdaptiveWeights:
        """Return (waiting, runtime, core) weights for this scheduling decision."""
        if not context.waiting_jobs:
            return (self.base_wait_weight, 1.0, 0.1)

        mean_runtime = sum(job.runtime for job in context.waiting_jobs) / len(
            context.waiting_jobs
        )
        mean_runtime = max(mean_runtime, 1.0)
        max_wait = max(
            max(0, context.current_time - job.arrival_time)
            for job in context.waiting_jobs
        )

        starvation_pressure = max_wait / mean_runtime
        wait_weight = self.base_wait_weight * (1.0 + starvation_pressure)
        return (wait_weight, 1.0, 0.1)

    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        runnable = [
            job
            for job in context.waiting_jobs
            if job.required_cores <= context.available_cores
        ]
        if not runnable:
            return None

        wait_weight, runtime_weight, core_weight = self.compute_adaptive_weights(context)

        def ranking_key(job):
            waited = max(0, context.current_time - job.arrival_time)
            utility = (
                wait_weight * waited
                - runtime_weight * job.runtime
                - core_weight * job.required_cores
            )
            # sort ascending: highest utility first, then FIFO and stable job ID.
            return (
                -utility,
                job.arrival_time,
                make_job_sort_key(job.job_id),
            )

        return min(runnable, key=ranking_key).job_id
