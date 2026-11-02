"""Adaptive multi-factor priority scheduling (specification: docs/ADAPTIVE_POLICY.md).

A Slurm-style multi-factor priority (age, shortness, size) whose weights shift toward age as the
queue ages, combined with a selective reservation for the top job (Srinivasan et al., JSSPP 2002)
and optional priority preemption. Every factor is normalised to [0, 1].
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from adaptive_scheduler.exceptions import ConfigurationError
from adaptive_scheduler.models import (
    JobId,
    JobSpec,
    SchedulerContext,
    WaitingJobView,
    make_job_sort_key,
)


@dataclass(frozen=True)
class _Candidate:
    job: JobSpec
    remaining: int  # CPU service still needed (= runtime unless the job was preempted)
    waited: int  # time spent waiting so far, across all waiting intervals
    segment_start: int | None = None  # running jobs only: start of the current segment


def _number(name: str, value, lo: float, hi: float = math.inf, *, allow_inf: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or math.isnan(value):
        raise ConfigurationError(f"{name} must be a number; got {value!r}.")
    if math.isinf(value) and not allow_inf:
        raise ConfigurationError(f"{name} must be finite; got {value!r}.")
    if not lo <= value <= hi:
        raise ConfigurationError(f"{name} must be in [{lo}, {hi}]; got {value!r}.")
    return float(value)


class AdaptiveMultifactorPolicy:
    """Adaptive multi-factor priority with selective reservation and optional preemption.

    Utility of job j at time t (all factors in [0, 1]):
        U_j = W_age(t) * A_j + W_short(t) * S_j + W_size(t) * N_j
        A_j = min(1, w_j / max_age)                    w_j: time waited so far
        S_j = 1 - ln(1 + r_j) / ln(1 + r_max)          r_j: remaining runtime; r_max over waiting+running
        N_j = (C - c_j + 1) / C                        c_j: CPU cores, C: cluster CPU cores
    Adaptation: sigma(t) = mean over waiting jobs of A_j; with g = adaptation_gain,
        W_age = w_age + g*sigma*(w_short + w_size),  W_short = w_short*(1 - g*sigma),
        W_size = w_size*(1 - g*sigma)                  (base weights normalised to sum 1).
    Dispatch: highest U first, ties by (arrival_time, job_id). If the top job does not fit and its
    expansion factor (w + r) / r >= reservation_xf, it holds a reservation: another job may start
    only if it fits now and ends by the reserved time. Otherwise the highest-U fitting job starts.
    Preemption (preemptive=True): if the top job does not fit, running jobs whose utility is lower
    by more than preempt_margin are suspended, lowest utility first, only if that frees enough CPU
    cores; otherwise nothing is preempted.
    """

    name = "Adaptive Multi-Factor"
    policy_id = "adaptive_multifactor"

    # Named parameter sets (docs/TUNING.md): found by black-box search on real production logs
    # (times in seconds, waits of hours) and checked on held-out windows. They do not transfer to
    # workloads on a much shorter time scale (max_age is in time units). Defaults stay as above.
    PRESETS = {
        "tuned for real HPC logs": {
            "age_weight": 0.386, "short_weight": 0.521, "size_weight": 0.093, "max_age": 203692,
            "adaptation_gain": 0.24, "reservation_xf": 1.0, "preemptive": False, "preempt_margin": 0.1},
        "tuned for real HPC logs, preemptive": {
            "age_weight": 0.687, "short_weight": 0.2965, "size_weight": 0.0166, "max_age": 984900,
            "adaptation_gain": 0.715, "reservation_xf": math.inf, "preemptive": True, "preempt_margin": 0.0006},
    }

    def __init__(
        self,
        *,
        age_weight: float = 0.4,
        short_weight: float = 0.4,
        size_weight: float = 0.2,
        max_age: float = 500,
        adaptation_gain: float = 0.5,
        reservation_xf: float = 2.0,
        preemptive: bool = False,
        preempt_margin: float = 0.1,
    ) -> None:
        weights = [
            _number("age_weight", age_weight, 0),
            _number("short_weight", short_weight, 0),
            _number("size_weight", size_weight, 0),
        ]
        total = sum(weights)
        if total <= 0:
            raise ConfigurationError("age_weight + short_weight + size_weight must be > 0.")
        self.age_weight, self.short_weight, self.size_weight = (w / total for w in weights)
        self.max_age = _number("max_age", max_age, 0)
        if self.max_age == 0:
            raise ConfigurationError("max_age must be > 0.")
        self.adaptation_gain = _number("adaptation_gain", adaptation_gain, 0, 1)
        self.reservation_xf = _number("reservation_xf", reservation_xf, 1, allow_inf=True)
        if not isinstance(preemptive, bool):
            raise ConfigurationError(f"preemptive must be a boolean; got {preemptive!r}.")
        self.preemptive = preemptive
        self.preempt_margin = _number("preempt_margin", preempt_margin, 0, 1)

    # ---- state read from the context ---------------------------------------------------

    @staticmethod
    def _waiting(context: SchedulerContext) -> list[_Candidate]:
        views = context.waiting_job_views or tuple(
            WaitingJobView(job=j, remaining_runtime=j.runtime) for j in context.waiting_jobs
        )
        t = context.current_time
        return [
            _Candidate(v.job, v.remaining_runtime,
                       t - v.job.arrival_time - (v.job.runtime - v.remaining_runtime))
            for v in views
        ]

    @staticmethod
    def _running(context: SchedulerContext) -> list[_Candidate]:
        t = context.current_time
        out = []
        for v in context.running_jobs:
            remaining = v.expected_finish_time - t
            out.append(_Candidate(v.job, remaining,
                                  t - v.job.arrival_time - (v.job.runtime - remaining), v.start_time))
        return out

    def _age(self, c: _Candidate) -> float:
        return min(1.0, max(0, c.waited) / self.max_age)

    # ---- the documented formula --------------------------------------------------------

    def compute_weights(self, context: SchedulerContext, waiting: list | None = None) -> tuple[float, float, float]:
        """(W_age, W_short, W_size) for this decision; they always sum to 1."""
        waiting = self._waiting(context) if waiting is None else waiting
        sigma = sum(map(self._age, waiting)) / len(waiting) if waiting else 0.0
        shift = self.adaptation_gain * sigma
        others = self.short_weight + self.size_weight
        return (self.age_weight + shift * others,
                self.short_weight * (1 - shift),
                self.size_weight * (1 - shift))

    def _utilities(self, context: SchedulerContext, cands: list[_Candidate],
                   waiting: list | None = None) -> dict[JobId, float]:
        waiting = self._waiting(context) if waiting is None else waiting
        w_age, w_short, w_size = self.compute_weights(context, waiting)
        everyone = waiting + self._running(context)
        denom = math.log1p(max(c.remaining for c in everyone))
        cores = context.total_cores
        return {
            c.job.job_id: w_age * self._age(c)
            + w_short * (1 - math.log1p(c.remaining) / denom)
            + w_size * (cores - c.job.required_cores + 1) / cores
            for c in cands
        }

    def utilities(self, context: SchedulerContext) -> dict[JobId, float]:
        """Utility of every waiting job at this decision (for inspection and tests)."""
        waiting = self._waiting(context)
        return self._utilities(context, waiting, waiting) if waiting else {}

    def _ranked(self, context: SchedulerContext) -> list[_Candidate]:
        waiting = self._waiting(context)
        if not waiting:
            return []
        u = self._utilities(context, waiting, waiting)
        return sorted(waiting, key=lambda c: (-u[c.job.job_id], c.job.arrival_time,
                                              make_job_sort_key(c.job.job_id)))

    # ---- SchedulingPolicy / PreemptiveSchedulingPolicy ---------------------------------

    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        order = self._ranked(context)
        if not order:
            return None
        free = context.available_cores
        top = order[0]
        if top.job.required_cores <= free:
            return top.job.job_id
        if (top.waited + top.remaining) / top.remaining >= self.reservation_xf:
            shadow = context.earliest_available_time(top.job.required_cores)
            for c in order[1:]:
                if c.job.required_cores <= free and context.current_time + c.remaining <= shadow:
                    return c.job.job_id
            return None
        for c in order[1:]:
            if c.job.required_cores <= free:
                return c.job.job_id
        return None

    def select_jobs_to_preempt(self, context: SchedulerContext) -> tuple[JobId, ...]:
        if not self.preemptive or not context.running_jobs:
            return ()
        order = self._ranked(context)
        if not order:
            return ()
        top = order[0]
        need = top.job.required_cores - context.available_cores
        if need <= 0:
            return ()
        running = self._running(context)
        u = self._utilities(context, running + [top])
        t = context.current_time
        victims = sorted(
            (r for r in running
             if r.segment_start < t and r.remaining > 0
             and u[top.job.job_id] - u[r.job.job_id] > self.preempt_margin),
            key=lambda r: (u[r.job.job_id], -r.segment_start, make_job_sort_key(r.job.job_id)),
        )
        chosen, freed = [], 0
        for r in victims:
            chosen.append(r.job.job_id)
            freed += r.job.required_cores
            if freed >= need:
                return tuple(chosen)
        return ()
