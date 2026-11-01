"""Shortest-Job-First scheduling policy (SCH-FR-08, Section 6.2)."""

from adaptive_scheduler.exceptions import ConfigurationError
from adaptive_scheduler.models import JobId, SchedulerContext, make_job_sort_key


class SJFPolicy:
    """Shortest-Job-First (SJF) baseline scheduling policy (SCH-FR-08).

    Decision & Tie-Breaking Semantics (Section 6.2, SCH-NFR-06):
    - Prefers waiting jobs with the smallest estimated `runtime`.
    - Breaks ties deterministically by `(runtime, arrival_time, make_job_sort_key(job_id))`.
    - When `strict_head_of_line=True` (default), if the globally shortest waiting job
      exceeds `available_cores`, the policy waits (`None`) rather than starting a longer job.
    - When `strict_head_of_line=False`, selects the shortest job among those that currently
      fit within `available_cores`.
    """

    def __init__(self, *, strict_head_of_line: bool = True) -> None:
        if not isinstance(strict_head_of_line, bool):
            raise ConfigurationError("strict_head_of_line must be a boolean.")
        self.strict_head_of_line = strict_head_of_line

    @property
    def name(self) -> str:
        """Stable unique strategy identifier (SCH-FR-10)."""
        return "sjf" if self.strict_head_of_line else "sjf_nonblocking"

    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        if not context.waiting_jobs or context.available_cores <= 0:
            return None

        ordered = sorted(
            context.waiting_jobs,
            key=lambda job: (job.runtime, job.arrival_time, make_job_sort_key(job.job_id)),
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
