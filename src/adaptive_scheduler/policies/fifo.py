"""First-In-First-Out scheduling policy."""

try:
    from adaptive_scheduler.models import JobId, SchedulerContext, make_job_sort_key
except ImportError:
    from adaptive_scheduler.models import JobId, SchedulerContext, make_job_sort_key


class FIFOPolicy:
    """First-In-First-Out (FIFO) scheduling policy."""

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
