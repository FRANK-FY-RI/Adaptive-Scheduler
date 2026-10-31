"""Reference scheduling strategies for testing and baseline comparisons (Section 8, Section 13)."""

from .models import JobId, SchedulerContext, make_job_sort_key


class FIFOPolicy:
    """First-In-First-Out (FIFO) scheduling policy.

    Args:
        strict_head_of_line: If True (default), waits when the earliest-arrived
            waiting job does not fit in available cores. If False, scans waiting
            jobs in FIFO order and selects the first job that fits.
    """

    def __init__(self, *, strict_head_of_line: bool = True) -> None:
        self.strict_head_of_line = strict_head_of_line

    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        if not context.waiting_jobs:
            return None

        ordered = sorted(
            context.waiting_jobs,
            key=lambda job: (job.arrival_time, make_job_sort_key(job.job_id)),
        )
        if self.strict_head_of_line:
            head = ordered[0]
            return head.job_id if head.required_cores <= context.available_cores else None

        for job in ordered:
            if job.required_cores <= context.available_cores:
                return job.job_id
        return None


class SJFPolicy:
    """Shortest-Job-First (SJF) scheduling policy ordered by runtime, then arrival time.

    Args:
        strict_head_of_line: If True (default), waits if the shortest waiting job
            requires more cores than currently available. If False, selects the
            shortest waiting job that currently fits.
    """

    def __init__(self, *, strict_head_of_line: bool = True) -> None:
        self.strict_head_of_line = strict_head_of_line

    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        if not context.waiting_jobs:
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
