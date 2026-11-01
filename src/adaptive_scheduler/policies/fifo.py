"""First-In-First-Out scheduling policy (SCH-FR-07, Section 6.1)."""

from adaptive_scheduler.exceptions import ConfigurationError
from adaptive_scheduler.models import JobId, SchedulerContext, make_job_sort_key


class FIFOPolicy:
    """First-In-First-Out (FIFO) baseline scheduling policy (SCH-FR-07).

    Decision & Tie-Breaking Semantics (Section 6.1, SCH-NFR-06):
    - Orders waiting jobs by earliest `arrival_time`.
    - Breaks ties deterministically using `make_job_sort_key(job.job_id)`.
    - When `strict_head_of_line=True` (default), enforces strict Head-of-Line (HoL)
      blocking: if the oldest waiting job requires more cores than `available_cores`,
      returns `None` and waits rather than starting a later job.
    - When `strict_head_of_line=False`, scans the arrival-ordered queue and selects
      the earliest arriving job that fits within `available_cores`.
    """

    def __init__(self, *, strict_head_of_line: bool = True) -> None:
        if not isinstance(strict_head_of_line, bool):
            raise ConfigurationError("strict_head_of_line must be a boolean.")
        self.strict_head_of_line = strict_head_of_line

    @property
    def name(self) -> str:
        """Stable unique strategy identifier (SCH-FR-10)."""
        return "fifo" if self.strict_head_of_line else "fifo_nonblocking"

    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        if not context.waiting_jobs or context.available_cores <= 0:
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
