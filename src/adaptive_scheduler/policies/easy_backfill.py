"""EASY Backfilling scheduling policy (SCH-FR-12, FR-29)."""

from adaptive_scheduler.models import JobId, SchedulerContext, make_job_sort_key


class EASYBackfillPolicy:
    """EASY Backfilling scheduling strategy (SCH-FR-12).

    Semantics:
    - Orders waiting jobs in strict FIFO order `(arrival_time, make_job_sort_key(job_id))`.
    - If the head-of-line (oldest) waiting job fits in `available_cores`, starts it immediately.
    - Otherwise, computes a shadow reservation timestamp for the head-of-line job using
      `context.earliest_available_time(head.required_cores)`.
    - Scans subsequent waiting jobs in FIFO order and starts the first runnable job that
      either completes on/before `shadow_time` or requires no more than the extra cores
      remaining at `shadow_time`.
    """

    @property
    def name(self) -> str:
        """Stable unique strategy identifier (SCH-FR-10)."""
        return "easy_backfill"

    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        if not context.waiting_jobs or context.available_cores <= 0:
            return None

        ordered = sorted(
            context.waiting_jobs,
            key=lambda job: (job.arrival_time, make_job_sort_key(job.job_id)),
        )
        head = ordered[0]
        if head.required_cores <= context.available_cores:
            return head.job_id

        shadow_time = context.earliest_available_time(head.required_cores)
        cores_busy_at_shadow = sum(
            rjob.job.required_cores
            for rjob in context.running_jobs
            if rjob.expected_finish_time > shadow_time
        )
        extra_cores_at_shadow = (
            context.total_cores - cores_busy_at_shadow - head.required_cores
        )

        for candidate in ordered[1:]:
            if candidate.required_cores > context.available_cores:
                continue
            if (
                context.current_time + candidate.runtime <= shadow_time
                or candidate.required_cores <= extra_cores_at_shadow
            ):
                return candidate.job_id

        return None
