"""Researcher-defined scheduling strategies, run with ``--policy-file`` (README §2).

Each strategy looks only at the waiting jobs that fit in the free CPU cores right now, so a
job is never held back while another one could start (none of them reserve cores for a
wide job). They differ only in which fitting job they prefer. Ties always fall back to
earlier arrival time, then job id, so every run is deterministic.

Run one from the repository root, for example:

    python -m adaptive_scheduler.run_simulation --csv workloads/synthetic_workload.csv \\
        --cores 8 --policy-file examples/researcher_strategies.py --policy-class SJFAgingStrategy
"""
from adaptive_scheduler import JobId, SchedulerContext


def _fitting(context: SchedulerContext):
    return [j for j in context.waiting_jobs if j.required_cores <= context.available_cores]


class SJFAgingStrategy:
    """SJF with aging: start the fitting job with the lowest runtime - AGING_RATE * waiting time.

    Idea: SJF keeps average waiting time low but can leave a long job waiting behind a stream
    of short ones. Every time unit a job waits takes AGING_RATE time units off its priority,
    so a long job eventually gets ahead. AGING_RATE = 0 is plain SJF with first-fit.
    """

    AGING_RATE = 1.0

    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        jobs = _fitting(context)
        if not jobs:
            return None
        now = context.current_time
        return min(jobs, key=lambda j: (j.runtime - self.AGING_RATE * (now - j.arrival_time),
                                        j.arrival_time, str(j.job_id))).job_id


class SmallestAreaFirstStrategy:
    """Smallest area first: start the fitting job with the lowest runtime x required CPU cores.

    Idea: SJF ignores width, so a short job that needs the whole cluster counts as cheap.
    Area is the CPU-core time a job takes from everyone else, so ordering by area accounts
    for both how long and how wide a job is.
    """

    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        jobs = _fitting(context)
        if not jobs:
            return None
        return min(jobs, key=lambda j: (j.runtime * j.required_cores,
                                        j.arrival_time, str(j.job_id))).job_id


class BestFitStrategy:
    """Best fit: start the fitting job that needs the most CPU cores (ties: shorter runtime).

    Idea: fill the free CPU cores as fully as possible, aiming at utilization. Wider jobs go
    first while they fit, at the cost of making narrow jobs wait.
    """

    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        jobs = _fitting(context)
        if not jobs:
            return None
        return min(jobs, key=lambda j: (-j.required_cores, j.runtime,
                                        j.arrival_time, str(j.job_id))).job_id


# Aging-rate variants for a sensitivity check (the constructor takes no arguments, so a
# variant is a subclass). Rate 0 is plain SJF with first-fit: the fair baseline for the others.
class SJFFirstFitStrategy(SJFAgingStrategy):
    """SJF with first-fit: start the shortest fitting job (SJFAgingStrategy with AGING_RATE 0)."""

    AGING_RATE = 0.0


class SJFAgingHalfStrategy(SJFAgingStrategy):
    """SJF with aging at AGING_RATE 0.5 (each time unit waited takes 0.5 off the runtime)."""

    AGING_RATE = 0.5


class SJFAgingDoubleStrategy(SJFAgingStrategy):
    """SJF with aging at AGING_RATE 2 (each time unit waited takes 2 off the runtime)."""

    AGING_RATE = 2.0
