"""UC-R03: show one job's execution record and check its invariants (preemption-aware)."""
from __future__ import annotations

from pathlib import Path

from adaptivesched.experiments.adapter import parse_job_id, record_problems
from adaptivesched.experiments.export import read_records

CHECKS = ["start_time >= arrival_time",
          "first segment starts at start_time and last ends at finish_time",
          "segments are positive, ordered and non-overlapping",
          "execution segments sum to runtime",
          "waiting_time == finish_time - arrival_time - runtime",
          "number of segments == preemption_count + 1"]


def records_path(run) -> Path:
    """Accept runs/<run_id>, runs/<run_id>.records.csv or runs/<run_id>.summary.json."""
    p = Path(run)
    for suffix in (".records.csv", ".summary.json"):
        if p.name.endswith(suffix):
            p = p.with_name(p.name[: -len(suffix)])
    p = p.with_name(p.name + ".records.csv")
    if not p.exists():
        raise FileNotFoundError(f"no records file {p}")
    return p


def inspect_job(run, job_id) -> tuple[str, bool]:
    """(report text, invariants hold). job_id: an int or a string id; "7" means job 7."""
    job_id = parse_job_id(job_id) if isinstance(job_id, str) else job_id
    recs = {r.job_id: r for r in read_records(records_path(run))}
    if job_id not in recs:
        raise ValueError(f"job {job_id} is not in {run} ({len(recs)} jobs)")
    r = recs[job_id]
    failed = set(record_problems(r))
    segs = "; ".join(f"[{a}, {b})" for a, b in r.segments())
    lines = [f"job {r.job_id}",
             *(f"  {k:<15} {v}" for k, v in vars(r).items() if k not in ("job_id", "execution_segments")),
             f"  segments        {segs}",
             f"  derived waiting time     {r.finish_time - r.arrival_time - r.runtime}",
             f"  derived turnaround time  {r.finish_time - r.arrival_time}",
             *(f"  [{'FAILED' if c in failed else 'ok'}] {c}" for c in CHECKS)]
    return "\n".join(lines), not failed
