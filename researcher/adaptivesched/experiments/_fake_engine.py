"""TEST INFRASTRUCTURE — NOT THE ADAPTIVESCHED ENGINE.

A minimal event-driven simulator that exists only so the researcher part (workloads,
metrics, export, batch, plots) is testable before the teammates' engine is integrated.
It is never selected unless `--engine fake` is passed, and every summary it produces
says `engine: fake`. Results from it are not study results.

Semantics (docs/INTERFACES.md §1, §3):
- At each timestamp: completions free their CPU cores, then arrivals join the queue,
  then dispatch.
- Dispatch is wait-behind-head for both strategies: start the head of the queue while
  it fits the free CPU cores; when the head does not fit, start nothing else.
- Queue order (all ties broken by these keys, never by input order):
    fifo: (arrival_time, job_id)
    sjf:  (runtime, arrival_time, job_id)
- A job finishes at exactly start_time + runtime (runtime_estimate_error = 0).
"""
from __future__ import annotations

import heapq
from typing import Sequence

from adaptivesched.experiments.adapter import JobRecord, JobSpec

VERSION = "fake-0.1"

DISPATCH_NOTES = {
    "fifo": "fake engine FIFO: queue ordered by (arrival_time, job_id); wait-behind-head "
            "(if the head job does not fit the free CPU cores, no later job starts)",
    "sjf": "fake engine SJF: queue ordered by (runtime, arrival_time, job_id); wait-behind-head "
           "(if the shortest job does not fit the free CPU cores, no other job starts)",
}

_KEYS = {
    "fifo": lambda j: (j.arrival_time, j.job_id),
    "sjf": lambda j: (j.runtime, j.arrival_time, j.job_id),
}


def simulate(jobs: Sequence[JobSpec], cluster_cores: int, strategy: str) -> list[JobRecord]:
    if strategy not in _KEYS:
        raise ValueError(f"unknown strategy {strategy!r}; the fake engine has {sorted(_KEYS)}")
    if cluster_cores <= 0:
        raise ValueError(f"cluster_cores must be > 0, got {cluster_cores}")
    for j in jobs:  # full validation is workloads/validate.py; this guard only prevents a hang
        if not 0 < j.required_cores <= cluster_cores:
            raise ValueError(f"job {j.job_id}: required_cores={j.required_cores} "
                             f"does not fit cluster_cores={cluster_cores}")

    key = _KEYS[strategy]
    arrivals = sorted(jobs, key=lambda j: (j.arrival_time, j.job_id))
    queue: list = []    # heap of (key, job); keys are unique because they end in job_id
    running: list = []  # heap of (finish_time, job_id, required_cores)
    free, i, records = cluster_cores, 0, []

    while i < len(arrivals) or queue or running:
        # Next event time. With the queue non-empty, something is always running or
        # arriving: on an empty cluster the head job fits (guarded above).
        t = min(([arrivals[i].arrival_time] if i < len(arrivals) else [])
                + ([running[0][0]] if running else []))
        while running and running[0][0] == t:
            free += heapq.heappop(running)[2]
        while i < len(arrivals) and arrivals[i].arrival_time == t:
            heapq.heappush(queue, (key(arrivals[i]), arrivals[i]))
            i += 1
        while queue and queue[0][1].required_cores <= free:
            j = heapq.heappop(queue)[1]
            free -= j.required_cores
            heapq.heappush(running, (t + j.runtime, j.job_id, j.required_cores))
            records.append(JobRecord(j.job_id, j.arrival_time, t, t + j.runtime,
                                     j.runtime, t - j.arrival_time, j.required_cores))
    return records
