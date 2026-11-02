"""The only place the researcher part touches the engine and strategies (docs/INTERFACES.md §3).

When the teammates' API lands, only this file changes.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence, Union

JobId = Union[int, str]


def job_key(job_id: JobId) -> tuple[int, int | str]:
    """Total order over mixed int/str job ids: ints numerically, then strings."""
    return (0, job_id) if isinstance(job_id, int) else (1, job_id)


def parse_job_id(text: str) -> JobId:
    """A CSV job id: an integer when it is one ("7"), otherwise the stripped string ("J7")."""
    text = text.strip()
    try:
        return int(text)
    except ValueError:
        return text


@dataclass(frozen=True)
class JobSpec:
    job_id: JobId
    arrival_time: int
    runtime: int
    required_cores: int


@dataclass(frozen=True)
class JobRecord:
    job_id: JobId
    arrival_time: int
    start_time: int  # first start
    finish_time: int
    runtime: int
    waiting_time: int  # total time spent waiting, across every waiting interval
    required_cores: int
    preemption_count: int = 0
    execution_segments: tuple[tuple[int, int], ...] = ()  # [start, finish) intervals; () = one interval

    def segments(self) -> tuple[tuple[int, int], ...]:
        """The intervals the job ran in; a non-preempted job ran in one, [start, finish)."""
        return self.execution_segments or ((self.start_time, self.finish_time),)


def record_problems(r) -> list[str]:
    """Invariants of one record, preemptive or not; empty when they all hold (UC-R03).
    Segments are ordered, non-overlapping, inside [start_time, finish_time], sum to runtime."""
    segs = r.segments()
    problems = []
    if r.start_time < r.arrival_time:
        problems.append("start_time >= arrival_time")
    if (segs[0][0], segs[-1][1]) != (r.start_time, r.finish_time):
        problems.append("first segment starts at start_time and last ends at finish_time")
    if any(b <= a for a, b in segs) or any(c < b for (_, b), (c, _) in zip(segs, segs[1:])):
        problems.append("segments are positive, ordered and non-overlapping")
    if sum(b - a for a, b in segs) != r.runtime:
        problems.append("execution segments sum to runtime")
    if r.waiting_time != r.finish_time - r.arrival_time - r.runtime:
        problems.append("waiting_time == finish_time - arrival_time - runtime")
    if len(segs) != r.preemption_count + 1:
        problems.append("number of segments == preemption_count + 1")
    return problems


@dataclass(frozen=True)
class RunResult:
    strategy: str
    strategy_dispatch_note: str
    workload_id: str
    cluster_cores: int
    records: tuple[JobRecord, ...]  # sorted by job_key(job_id)
    engine: str  # "team" | "fake"
    engine_version: str
    preemptive: bool = False  # the strategy may suspend running jobs in this configuration
    engine_invariant_checks: bool = True  # engine re-checked its invariants after every event


INVARIANT_CHECK_MAX_JOBS = 1000


class EngineAdapter(Protocol):
    def run(self, jobs: Sequence[JobSpec], cluster_cores: int, strategy_id: str,
            strategy_params: Mapping[str, Any], *, workload_id: str,
            strategy_file: str = "") -> RunResult: ...

    def strategies(self) -> list[str]: ...


class TeamEngineAdapter:
    """Wraps the teammates' engine: package `adaptive_scheduler` (FRANK-FY-RI/Adaptive-Scheduler),
    pinned by commit in pyproject.toml. Their code is used as installed, never edited.

    Their FIFO orders the queue by (arrival_time, job_id), SJF by (runtime, arrival_time,
    job_id). `strict_head_of_line` (default True) is wait-behind-head; False starts the first
    job in queue order that fits. A policy with `select_jobs_to_preempt` may suspend running
    jobs; its records carry every execution segment. Imports stay inside methods (RES-NFR-06).
    """

    def run(self, jobs, cluster_cores, strategy_id, strategy_params, *, workload_id, strategy_file=""):
        from adaptive_scheduler import JobSpec as TeamJob, SimulationEngine

        if strategy_file:
            policy, note = _load_strategy_file(strategy_file, strategy_params)
        else:
            from adaptive_scheduler.policies import get_policy

            policy = get_policy(strategy_id, **strategy_params)
            note = _team_dispatch_note(strategy_id, policy)
        from adaptive_scheduler import SimulationSettings

        team_jobs = [TeamJob(j.job_id, j.arrival_time, j.runtime, j.required_cores) for j in jobs]
        # ponytail: the engine's per-event invariant check scans every job, so it is quadratic
        # (1,500 jobs: 17.8 s on vs 1.6 s off). Above this size only check_records (runner) verifies
        # the result. Records are identical either way; summaries record which mode ran.
        checks = len(team_jobs) <= INVARIANT_CHECK_MAX_JOBS
        result = SimulationEngine(cluster_cores, team_jobs, policy,
                                  settings=SimulationSettings(check_invariants=checks)).run()
        records = (JobRecord(r.job_id, r.arrival_time, r.start_time, r.finish_time, r.runtime,
                             r.waiting_time, r.required_cores, r.preemption_count,
                             tuple((s.start_time, s.finish_time) for s in r.execution_segments))
                   for r in result.execution_records)
        return RunResult(
            strategy=strategy_id,
            strategy_dispatch_note=note,
            workload_id=workload_id,
            cluster_cores=cluster_cores,
            records=tuple(sorted(records, key=lambda r: job_key(r.job_id))),
            engine="team",
            engine_version=_team_version(),
            preemptive=is_preemptive(policy),
            engine_invariant_checks=checks,
        )

    def strategies(self):
        from adaptive_scheduler.policies import policy_ids

        return policy_ids()


def is_preemptive(policy: Any) -> bool:
    """True if the policy implements the preemption hook and has not switched it off."""
    return callable(getattr(policy, "select_jobs_to_preempt", None)) and getattr(policy, "preemptive", True)


# How each team strategy picks the next job, from its docstring and code (main @ daa589d).
_DISPATCH_RULES = {
    "wait-behind-head": "wait-behind-head (if the head job does not fit the free CPU cores, no other job starts)",
    "first-fit": "first-fit (starts the first job in queue order that fits the free CPU cores)",
    "easy_backfill": "EASY backfilling: queue in arrival order; if the head job does not fit the free "
                     "CPU cores, a later job starts only if it fits now and finishes by the head job's "
                     "reserved start",
    "adaptive": "utility-ranked, first-fit: among jobs that fit the free CPU cores, highest "
                "U = w_wait*wait - runtime - 0.1*cores, w_wait = base_wait_weight*(1 + max queued wait / "
                "mean queued runtime); no reservation",
    "srtf": "preemptive shortest remaining runtime first: starts the fitting job with the least remaining "
            "runtime; suspends running jobs with strictly more remaining runtime (longest first) when "
            "that frees enough CPU cores for the shortest waiting job",
    "adaptive_multifactor": "adaptive multi-factor priority (docs/ADAPTIVE_POLICY.md): highest "
                            "U = W_age*age + W_short*shortness + W_size*narrowness, weights shift toward age "
                            "as the queue ages; a blocked top job with expansion factor >= reservation_xf "
                            "holds a reservation (others start only if they end by it), otherwise the "
                            "highest-U fitting job starts; preemptive=True suspends lower-utility running "
                            "jobs for the top job",
}


def _team_dispatch_note(strategy_id: str, policy: Any) -> str:
    params = vars(policy)  # e.g. {'strict_head_of_line': True} or adaptive's weights
    if "strict_head_of_line" in params:
        rule = _DISPATCH_RULES["wait-behind-head" if policy.strict_head_of_line else "first-fit"]
    else:
        rule = _DISPATCH_RULES.get(strategy_id, "dispatch rule not documented by the strategy")
    return f"team engine {strategy_id} ({type(policy).__name__}, {params}): {rule}"


def split_strategy_file(spec: str) -> tuple[str, str | None]:
    """'path/to/file.py:ClassName' -> (path, ClassName); 'path/to/file.py' -> (path, None)."""
    path, sep, cls = spec.rpartition(":")
    return (path, cls) if sep and path.endswith(".py") else (spec, None)


def _load_strategy_file(spec: str, strategy_params: Mapping[str, Any]):
    """A researcher strategy file, loaded by the team's loader (README §2). Its constructor
    takes no arguments, so a variant is a subclass, not a parameter."""
    import hashlib
    from pathlib import Path

    from adaptive_scheduler.policy_loader import load_policy_from_file

    if strategy_params:
        raise ValueError(f"strategy file {spec!r} takes no strategy_params (zero-argument "
                         f"constructor); got {dict(strategy_params)}")
    path, cls = split_strategy_file(spec)
    policy = load_policy_from_file(path, cls)
    sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
    doc = (type(policy).__doc__ or "dispatch rule not documented by the strategy").strip().splitlines()[0]
    return policy, f"researcher strategy {Path(path).name}:{type(policy).__name__} (file sha256 {sha}): {doc}"


@functools.lru_cache(maxsize=1)
def _team_version() -> str:
    """Package version plus the git commit it came from: pip's record for a git install, or the
    checkout's HEAD for an editable install ('+dirty' when the engine sources have local edits).
    A source tree copied without git (e.g. to the HPC) states its version in
    ADAPTIVESCHED_ENGINE_VERSION. Cached: it shells out to git, and a tuning run calls it thousands of times."""
    import importlib.metadata as md
    import json
    import os
    import subprocess
    from urllib.request import url2pathname
    from urllib.parse import urlparse

    if os.environ.get("ADAPTIVESCHED_ENGINE_VERSION"):
        return os.environ["ADAPTIVESCHED_ENGINE_VERSION"]
    try:
        dist = md.distribution("adaptive-scheduler")
    except md.PackageNotFoundError:
        return "adaptive-scheduler (not installed; imported from a source tree, version unknown)"
    url = json.loads(dist.read_text("direct_url.json") or "{}")
    commit = url.get("vcs_info", {}).get("commit_id", "")[:12]
    if not commit and url.get("dir_info", {}).get("editable"):
        path = url2pathname(urlparse(url["url"]).path)
        try:
            git = lambda *a: subprocess.run(["git", "-C", path, *a], capture_output=True, text=True,
                                            check=True).stdout.strip()
            commit = git("rev-parse", "HEAD")[:12]
            if git("status", "--porcelain", "--untracked-files=all", "--", "src"):
                commit += "+dirty"
        except (OSError, subprocess.CalledProcessError):
            commit = ""
    return f"adaptive-scheduler {dist.version}" + (f"@{commit}" if commit else "")


class FakeEngineAdapter:
    """TEST INFRASTRUCTURE ONLY — runs experiments/_fake_engine.py. Selected only by --engine fake."""

    def run(self, jobs, cluster_cores, strategy_id, strategy_params, *, workload_id, strategy_file=""):
        from adaptivesched.experiments import _fake_engine as fake

        if strategy_file:
            raise ValueError("the fake engine cannot run strategy files; use --engine team")
        if strategy_params:
            raise ValueError(f"strategy {strategy_id!r} on the fake engine takes no parameters, "
                             f"got {dict(strategy_params)}")
        records = fake.simulate(jobs, cluster_cores, strategy_id)
        return RunResult(
            strategy=strategy_id,
            strategy_dispatch_note=fake.DISPATCH_NOTES[strategy_id],
            workload_id=workload_id,
            cluster_cores=cluster_cores,
            records=tuple(sorted(records, key=lambda r: job_key(r.job_id))),
            engine="fake",
            engine_version=fake.VERSION,
        )

    def strategies(self):
        from adaptivesched.experiments import _fake_engine as fake

        return list(fake.DISPATCH_NOTES)


ADAPTERS = {"team": TeamEngineAdapter, "fake": FakeEngineAdapter}
