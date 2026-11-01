"""The only place the researcher part touches the engine and strategies (docs/INTERFACES.md §3).

When the teammates' API lands, only this file changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class JobSpec:
    job_id: int
    arrival_time: int
    runtime: int
    required_cores: int


@dataclass(frozen=True)
class JobRecord:
    job_id: int
    arrival_time: int
    start_time: int
    finish_time: int
    runtime: int
    waiting_time: int
    required_cores: int


@dataclass(frozen=True)
class RunResult:
    strategy: str
    strategy_dispatch_note: str
    workload_id: str
    cluster_cores: int
    records: tuple[JobRecord, ...]  # sorted by job_id
    engine: str  # "team" | "fake"
    engine_version: str


class EngineAdapter(Protocol):
    def run(self, jobs: Sequence[JobSpec], cluster_cores: int, strategy_id: str,
            strategy_params: Mapping[str, Any], *, workload_id: str) -> RunResult: ...

    def strategies(self) -> list[str]: ...


class TeamEngineAdapter:
    """Wraps the teammates' engine: package `adaptive_scheduler` (FRANK-FY-RI/Adaptive-Scheduler),
    pinned by commit in pyproject.toml. Their code is used as installed, never edited.

    Their FIFO orders the queue by (arrival_time, job_id), SJF by (runtime, arrival_time,
    job_id). `strict_head_of_line` (default True) is wait-behind-head; False starts the first
    job in queue order that fits. Imports stay inside methods (RES-NFR-06).
    """

    def run(self, jobs, cluster_cores, strategy_id, strategy_params, *, workload_id):
        from adaptive_scheduler import JobSpec as TeamJob, SimulationEngine
        from adaptive_scheduler.policies import get_policy

        policy = get_policy(strategy_id, **strategy_params)
        team_jobs = [TeamJob(j.job_id, j.arrival_time, j.runtime, j.required_cores) for j in jobs]
        result = SimulationEngine(cluster_cores, team_jobs, policy).run()
        records = (JobRecord(r.job_id, r.arrival_time, r.start_time, r.finish_time, r.runtime,
                             r.waiting_time, r.required_cores) for r in result.execution_records)
        return RunResult(
            strategy=strategy_id,
            strategy_dispatch_note=_team_dispatch_note(strategy_id, policy),
            workload_id=workload_id,
            cluster_cores=cluster_cores,
            records=tuple(sorted(records, key=lambda r: r.job_id)),
            engine="team",
            engine_version=_team_version(),
        )

    def strategies(self):
        from adaptive_scheduler.policies import discover_policies

        # their registry holds both file names and class names ("fifo", "fifopolicy")
        return sorted(k for k in discover_policies() if not k.endswith("policy"))


# How each team strategy picks the next job, from their docstrings at the pinned commit.
_DISPATCH_RULES = {
    "wait-behind-head": "wait-behind-head (if the head job does not fit the free CPU cores, no other job starts)",
    "first-fit": "first-fit (starts the first job in queue order that fits the free CPU cores)",
    "easy_backfill": "EASY backfilling: queue in arrival order; if the head job does not fit the free "
                     "CPU cores, a later job starts only if it finishes by the head job's reserved start "
                     "or fits in the CPU cores left over at that time",
    "adaptive": "utility-ranked: U = w_wait*wait + w_short*shortness + w_pack*width; weights shift toward "
                "waiting time as more queued jobs wait longer than the mean queued runtime, and toward "
                "width as CPU cores sit idle; if the top job does not fit, backfilling as in "
                "easy_backfill when enable_backfill is true, else nothing starts",
}


def _team_dispatch_note(strategy_id: str, policy: Any) -> str:
    params = vars(policy)  # e.g. {'strict_head_of_line': True} or adaptive's weights
    if "strict_head_of_line" in params:
        rule = _DISPATCH_RULES["wait-behind-head" if policy.strict_head_of_line else "first-fit"]
    else:
        rule = _DISPATCH_RULES.get(strategy_id, "dispatch rule not documented by the strategy")
    return f"team engine {strategy_id} ({type(policy).__name__}, {params}): {rule}"


def _team_version() -> str:
    """Package version plus the git commit it was installed from, when pip recorded one."""
    import importlib.metadata as md
    import json

    dist = md.distribution("adaptive-scheduler")
    commit = json.loads(dist.read_text("direct_url.json") or "{}").get("vcs_info", {}).get("commit_id", "")
    return f"adaptive-scheduler {dist.version}" + (f"@{commit[:12]}" if commit else "")


class FakeEngineAdapter:
    """TEST INFRASTRUCTURE ONLY — runs experiments/_fake_engine.py. Selected only by --engine fake."""

    def run(self, jobs, cluster_cores, strategy_id, strategy_params, *, workload_id):
        from adaptivesched.experiments import _fake_engine as fake

        if strategy_params:
            raise ValueError(f"strategy {strategy_id!r} on the fake engine takes no parameters, "
                             f"got {dict(strategy_params)}")
        records = fake.simulate(jobs, cluster_cores, strategy_id)
        return RunResult(
            strategy=strategy_id,
            strategy_dispatch_note=fake.DISPATCH_NOTES[strategy_id],
            workload_id=workload_id,
            cluster_cores=cluster_cores,
            records=tuple(sorted(records, key=lambda r: r.job_id)),
            engine="fake",
            engine_version=fake.VERSION,
        )

    def strategies(self):
        from adaptivesched.experiments import _fake_engine as fake

        return list(fake.DISPATCH_NOTES)


ADAPTERS = {"team": TeamEngineAdapter, "fake": FakeEngineAdapter}
