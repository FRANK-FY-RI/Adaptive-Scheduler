"""UC-R01: one run. Validates before the engine is touched; never raises (SPEC §3.2)."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from adaptivesched.experiments.adapter import EngineAdapter, JobSpec, RunResult, record_problems
from adaptivesched.experiments.config import RunConfig
from adaptivesched.metrics.summary import build_summary
from adaptivesched.workloads import resolve
from adaptivesched.workloads.validate import check_strategy


@dataclass(frozen=True)
class RunOutcome:
    status: str  # "ok" | "failed"
    workload_id: str  # resolved id when known, else the config's workload string
    result: RunResult | None = None
    summary: dict | None = None
    error: str | None = None


def check_records(jobs: Sequence[JobSpec], result: RunResult) -> None:
    """Refuse an engine result that breaks the record contract (INTERFACES §1)."""
    specs = {j.job_id: j for j in jobs}
    got = [r.job_id for r in result.records]
    if len(got) != len(specs) or set(got) != set(specs):
        raise RuntimeError(f"engine returned records for {len(got)} jobs, workload has {len(specs)}")
    for r in result.records:
        s = specs[r.job_id]
        if (r.arrival_time, r.runtime, r.required_cores) != (s.arrival_time, s.runtime, s.required_cores):
            raise RuntimeError(f"job {r.job_id}: record does not match its workload row")
        if problems := record_problems(r):
            raise RuntimeError(f"job {r.job_id}: record breaks invariants ({'; '.join(problems)}): {r}")
    # CPU cores in use never exceed capacity; a completion at t frees cores before a start at t.
    events = sorted([(a, 1, r.required_cores) for r in result.records for a, _ in r.segments()]
                    + [(b, 0, -r.required_cores) for r in result.records for _, b in r.segments()])
    in_use = 0
    for t, _, delta in events:
        in_use += delta
        if in_use > result.cluster_cores:
            raise RuntimeError(f"t={t}: {in_use} CPU cores in use, capacity {result.cluster_cores}")


def run_one(cfg: RunConfig, adapter: EngineAdapter) -> RunOutcome:
    workload_id = cfg.workload
    try:
        w = resolve(cfg.workload, cfg.cluster_cores)
        workload_id = w.workload_id
        strategy_id = cfg.base_strategy or cfg.strategy  # a labelled variant runs its base strategy
        if not cfg.strategy_file:  # a strategy file is checked when the adapter loads it
            check_strategy(strategy_id, adapter.strategies())
        result = adapter.run(w.jobs, cfg.cluster_cores, strategy_id, cfg.strategy_params,
                             workload_id=w.workload_id, strategy_file=cfg.strategy_file)
        result = replace(result, strategy=cfg.strategy)
        check_records(w.jobs, result)
        summary = build_summary(result, w.params, cfg.strategy_params, cfg.config_hash(), cfg.base_strategy)
        return RunOutcome("ok", workload_id, result, summary)
    except Exception as e:
        return RunOutcome("failed", workload_id, error=f"{type(e).__name__}: {e}")
