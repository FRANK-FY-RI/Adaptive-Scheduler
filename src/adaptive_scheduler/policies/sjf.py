"""Shortest-Job-First scheduling policy."""

from adaptive_scheduler.exceptions import ConfigurationError
from adaptive_scheduler.models import JobId, SchedulerContext, make_job_sort_key


class SJFPolicy:
    """Non-preemptive SJF with configurable head-of-line blocking."""

    name = "Shortest Job First"

    def __init__(self, *, strict_head_of_line: bool = True) -> None:
        if not isinstance(strict_head_of_line, bool):
            raise ConfigurationError("strict_head_of_line must be a boolean.")
        self.strict_head_of_line = strict_head_of_line

    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        if not context.waiting_jobs:
            return None

        ordered = sorted(
            context.waiting_jobs,
            key=lambda job: (
                job.runtime,
                job.arrival_time,
                make_job_sort_key(job.job_id),
            ),
        )

        if self.strict_head_of_line:
            shortest = ordered[0]
            return (
                shortest.job_id
                if shortest.required_cores <= context.available_cores
                else None
            )

        for job in ordered:
            if job.required_cores <= context.available_cores:
                return job.job_id
        return None
