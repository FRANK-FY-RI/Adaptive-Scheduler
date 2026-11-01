"""Preemptive shortest-remaining-time-first policy for multi-core jobs."""

from adaptive_scheduler.models import (
    JobId,
    SchedulerContext,
    WaitingJobView,
    make_job_sort_key,
)


class SRTFPolicy:
    """Shortest-remaining-time-first policy with zero-cost job preemption.

    This is an SRTF-inspired policy for a multi-core cluster: it chooses the
    waiting job with the smallest remaining CPU service demand and may suspend
    longer-running jobs to obtain the cores needed by that job. Running jobs are
    only preempted when their remaining runtime is strictly greater than the
    candidate's remaining runtime.

    Because jobs may request multiple cores, this is a practical gang-scheduling
    adaptation rather than the classic single-CPU textbook SRTF algorithm.
    """

    @staticmethod
    def _waiting_views(context: SchedulerContext) -> tuple[WaitingJobView, ...]:
        if context.waiting_job_views:
            return context.waiting_job_views
        # Compatibility for callers that construct SchedulerContext directly.
        return tuple(
            WaitingJobView(job=job, remaining_runtime=job.runtime)
            for job in context.waiting_jobs
        )

    @staticmethod
    def _waiting_key(view: WaitingJobView) -> tuple[int, int, tuple[int, str]]:
        return (
            view.remaining_runtime,
            view.job.arrival_time,
            make_job_sort_key(view.job.job_id),
        )

    def select_jobs_to_preempt(self, context: SchedulerContext) -> tuple[JobId, ...]:
        """Free enough cores for the shortest waiting job, if shorter victims exist."""
        waiting = sorted(self._waiting_views(context), key=self._waiting_key)
        if not waiting or not context.running_jobs:
            return ()

        for candidate in waiting:
            cores_needed = candidate.job.required_cores - context.available_cores
            if cores_needed <= 0:
                return ()

            victims = [
                running
                for running in context.running_jobs
                if (running.remaining_runtime or running.expected_finish_time - context.current_time)
                > candidate.remaining_runtime
            ]
            victims.sort(
                key=lambda running: (
                    -(running.remaining_runtime or running.expected_finish_time - context.current_time),
                    make_job_sort_key(running.job.job_id),
                )
            )

            selected: list[JobId] = []
            freed_cores = 0
            for victim in victims:
                selected.append(victim.job.job_id)
                freed_cores += victim.job.required_cores
                if freed_cores >= cores_needed:
                    return tuple(selected)

        return ()

    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        """Starts the shortest remaining waiting job that fits current capacity."""
        for view in sorted(self._waiting_views(context), key=self._waiting_key):
            if view.job.required_cores <= context.available_cores:
                return view.job.job_id
        return None
