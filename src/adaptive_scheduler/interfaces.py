"""Scheduling policy contracts for non-preemptive and preemptive strategies."""

from typing import Protocol, runtime_checkable

from adaptive_scheduler.models import JobId, SchedulerContext


@runtime_checkable
class SchedulingPolicy(Protocol):
    """Base contract implemented by every scheduling strategy.

    The engine calls ``select_next_job`` repeatedly to start waiting jobs. Existing
    policies remain non-preemptive unless they additionally implement the optional
    ``select_jobs_to_preempt`` hook from :class:`PreemptiveSchedulingPolicy`.
    """

    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        """Return a waiting job to start, or ``None`` to stop this dispatch pass."""
        ...


@runtime_checkable
class PreemptiveSchedulingPolicy(SchedulingPolicy, Protocol):
    """Optional extension for policies that may suspend currently running jobs.

    The hook is called once per event timestamp, before the engine starts any new
    waiting jobs. Return the IDs of running jobs to suspend. The engine validates
    the complete proposal before changing state; suspended jobs return to WAITING
    with their remaining runtime preserved. Policies must not mutate engine state.
    """

    def select_jobs_to_preempt(
        self, context: SchedulerContext
    ) -> tuple[JobId, ...]:
        """Return zero or more currently running jobs to preempt at this timestamp."""
        ...
