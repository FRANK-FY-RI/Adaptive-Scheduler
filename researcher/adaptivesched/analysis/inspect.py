"""UC-R03: show one job's execution record and check its two invariants."""
from __future__ import annotations

from pathlib import Path

from adaptivesched.experiments.export import read_records


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


def inspect_job(run, job_id: int) -> tuple[str, bool]:
    """(report text, invariants hold)."""
    recs = {r.job_id: r for r in read_records(records_path(run))}
    if job_id not in recs:
        raise ValueError(f"job {job_id} is not in {run} ({len(recs)} jobs)")
    r = recs[job_id]
    wait, turnaround = r.start_time - r.arrival_time, r.finish_time - r.arrival_time
    checks = [(f"waiting_time == start_time - arrival_time  ({r.waiting_time} == {wait})", r.waiting_time == wait),
              (f"finish_time == start_time + runtime  ({r.finish_time} == {r.start_time + r.runtime})",
               r.finish_time == r.start_time + r.runtime)]
    lines = [f"job {r.job_id}",
             *(f"  {k:<15} {v}" for k, v in vars(r).items() if k != "job_id"),
             f"  derived waiting time     {wait}",
             f"  derived turnaround time  {turnaround}",
             *(f"  [{'ok' if ok else 'FAILED'}] {text}" for text, ok in checks)]
    return "\n".join(lines), all(ok for _, ok in checks)
