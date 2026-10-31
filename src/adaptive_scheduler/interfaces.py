"""Common scheduling strategy interface (ENG-FR-12, ENG-NFR-02)."""

from typing import Protocol, runtime_checkable
from adaptive_scheduler.models import JobId, SchedulerContext


@runtime_checkable
class SchedulingPolicy(Protocol):
    """Protocol that all scheduling strategies must implement.

    Strategies propose scheduling decisions based on a read-only `SchedulerContext`
    without directly mutating simulation engine state.
    """

    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        """Selects a waiting job ID to start at `context.current_time`, or `None` to wait.

        Args:
            context: Immutable snapshot of current simulation state.

        Returns:
            The `job_id` of a waiting job that fits within `context.available_cores`,
            or `None` if the policy chooses not to start any job at this dispatch point.
        """
        ...
