"""EASY (non-preemptive) backfilling scheduling policy."""

from adaptive_scheduler.models import JobId, SchedulerContext, make_job_sort_key


class EASYBackfillPolicy:
    """Backfill jobs only when they are predicted not to delay the head job.

    The first waiting job receives a reservation at the earliest time enough
    cores are expected to become available. Later jobs may run only if they fit
    now and their known runtime ends no later than that reservation time.
    """

    name = "EASY Backfilling"

    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        if not context.waiting_jobs:
            return None

        ordered = sorted(
            context.waiting_jobs,
            key=lambda job: (job.arrival_time, make_job_sort_key(job.job_id)),
        )
        head = ordered[0]

        if head.required_cores <= context.available_cores:
            return head.job_id

        shadow_time = context.earliest_available_time(head.required_cores)

        for candidate in ordered[1:]:
            if candidate.required_cores > context.available_cores:
                continue
            predicted_finish = context.current_time + candidate.runtime
            if predicted_finish <= shadow_time:
                return candidate.job_id

        return None
