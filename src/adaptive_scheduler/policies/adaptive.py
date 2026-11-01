"""Adaptive utility-based scheduling policy (SCH-FR-13, Section 6.3)."""

from adaptive_scheduler.exceptions import ConfigurationError
from adaptive_scheduler.models import JobId, JobSpec, SchedulerContext, make_job_sort_key


class AdaptivePolicy:
    """Adaptive utility-based scheduling strategy (SCH-FR-13, Section 6.3).

    Utility Formula:
        U(j, t) = w_wait(t) * NormWait(j, t)
                + w_short(t) * NormShort(j)
                + w_pack(t) * NormCores(j)

    Where for each waiting job j at simulated time t:
        - NormWait(j, t) = (t - arrival_time_j) / max(max_wait, mean_runtime) in [0, 1]
        - NormShort(j)   = min_runtime / runtime_j                            in (0, 1]
        - NormCores(j)   = required_cores_j / total_cores                     in (0, 1]

    Adaptation Mechanism (State-Driven Heuristic):
        - Queue starvation pressure `pressure` in [0, 1] is computed as the fraction of
          waiting jobs whose waiting time exceeds the mean runtime of waiting jobs.
        - Cluster idle ratio `idle_ratio` in [0, 1] is `available_cores / total_cores`.
        - As `pressure` increases, `w_wait(t)` increases and `w_short(t)` decreases to
          prevent starvation of long jobs.
        - As `idle_ratio` increases, `w_pack(t)` increases to favor jobs that utilize
          idle cluster capacity.
        - If the highest-utility job cannot currently fit in `available_cores` and
          `enable_backfill=True`, the policy reserves its earliest start time via
          `context.earliest_available_time()` and only dispatches a lower-ranked job
          if doing so will not delay the highest-utility job.
    """

    def __init__(
        self,
        *,
        base_wait_weight: float = 0.35,
        base_short_weight: float = 0.45,
        base_pack_weight: float = 0.20,
        adaptation_gain: float = 0.50,
        enable_backfill: bool = True,
    ) -> None:
        for param_name, val in (
            ("base_wait_weight", base_wait_weight),
            ("base_short_weight", base_short_weight),
            ("base_pack_weight", base_pack_weight),
            ("adaptation_gain", adaptation_gain),
        ):
            if isinstance(val, bool) or not isinstance(val, (int, float)) or val < 0:
                raise ConfigurationError(f"{param_name} must be a non-negative number.")
        if not isinstance(enable_backfill, bool):
            raise ConfigurationError("enable_backfill must be a boolean.")

        self.base_wait_weight = float(base_wait_weight)
        self.base_short_weight = float(base_short_weight)
        self.base_pack_weight = float(base_pack_weight)
        self.adaptation_gain = float(adaptation_gain)
        self.enable_backfill = enable_backfill

    @property
    def name(self) -> str:
        """Stable unique strategy identifier (SCH-FR-10)."""
        return "adaptive"

    def compute_adaptive_weights(
        self, context: SchedulerContext
    ) -> tuple[float, float, float]:
        """Computes state-adapted (w_wait, w_short, w_pack) weights at `context.current_time`."""
        if not context.waiting_jobs:
            return (self.base_wait_weight, self.base_short_weight, self.base_pack_weight)

        waits = [max(0, context.current_time - j.arrival_time) for j in context.waiting_jobs]
        mean_runtime = sum(j.runtime for j in context.waiting_jobs) / len(context.waiting_jobs)

        starving_jobs = sum(1 for w in waits if w >= mean_runtime)
        pressure = starving_jobs / len(context.waiting_jobs)
        idle_ratio = (
            context.available_cores / context.total_cores
            if context.total_cores > 0
            else 0.0
        )

        w_wait = self.base_wait_weight + self.adaptation_gain * pressure
        w_short = max(0.05, self.base_short_weight - 0.5 * self.adaptation_gain * pressure)
        w_pack = self.base_pack_weight + 0.25 * self.adaptation_gain * idle_ratio
        return (w_wait, w_short, w_pack)

    def score_job(self, job: JobSpec, context: SchedulerContext) -> float:
        """Calculates the scalar utility score for a waiting job in the given context."""
        w_wait, w_short, w_pack = self.compute_adaptive_weights(context)
        waits = [max(0, context.current_time - j.arrival_time) for j in context.waiting_jobs]
        mean_runtime = (
            sum(j.runtime for j in context.waiting_jobs) / len(context.waiting_jobs)
            if context.waiting_jobs
            else 1.0
        )
        wait_scale = max(max(waits, default=0), mean_runtime, 1.0)
        min_runtime = min(j.runtime for j in context.waiting_jobs) if context.waiting_jobs else 1

        job_wait = max(0, context.current_time - job.arrival_time)
        norm_wait = job_wait / wait_scale
        norm_short = min_runtime / job.runtime
        norm_cores = job.required_cores / context.total_cores

        return (w_wait * norm_wait) + (w_short * norm_short) + (w_pack * norm_cores)

    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        if not context.waiting_jobs or context.available_cores <= 0:
            return None

        ranked = sorted(
            context.waiting_jobs,
            key=lambda job: (
                -round(self.score_job(job, context), 12),
                job.arrival_time,
                make_job_sort_key(job.job_id),
            ),
        )

        top_job = ranked[0]
        if top_job.required_cores <= context.available_cores:
            return top_job.job_id

        if not self.enable_backfill:
            return None

        shadow_time = context.earliest_available_time(top_job.required_cores)
        cores_busy_at_shadow = sum(
            rjob.job.required_cores
            for rjob in context.running_jobs
            if rjob.expected_finish_time > shadow_time
        )
        extra_cores_at_shadow = (
            context.total_cores - cores_busy_at_shadow - top_job.required_cores
        )

        for candidate in ranked[1:]:
            if candidate.required_cores > context.available_cores:
                continue
            finishes_before_shadow = (
                context.current_time + candidate.runtime <= shadow_time
            )
            fits_alongside_reservation = candidate.required_cores <= extra_cores_at_shadow
            if finishes_before_shadow or fits_alongside_reservation:
                return candidate.job_id

        return None
