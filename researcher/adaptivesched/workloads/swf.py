"""Real workloads from the Parallel Workloads Archive (Standard Workload Format, SWF) as CSV.

SWF: one line per job, 18 whitespace-separated fields; header lines start with ';'
(https://www.cs.huji.ac.il/labs/parallel/workload/swf.html). Fields used, by SWF number:

    1  Job Number                     -> job_id (kept, so a job traces back to the log)
    2  Submit Time (s)                -> arrival_time, shifted so the window's first job arrives at 0
    4  Run Time (s, wall clock)       -> runtime, rounded to whole seconds
    5  Number of Allocated Processors -> required_cores (8, Requested Processors, if 5 is missing)
    header MaxProcs (else MaxNodes)   -> the cluster's CPU cores

Jobs are dropped when their rounded run time is <= 0 (cancelled before starting, or under half a
second), when they have no processor count, or when they need more processors than the machine
has; the counts are written into the CSV header. Cancelled or failed jobs that did run are kept:
they occupied CPU cores. A window is a contiguous run of kept jobs in submit order.
"""
from __future__ import annotations

import gzip
import re
from pathlib import Path

from adaptivesched.experiments.adapter import JobSpec
from adaptivesched.workloads.loader import to_csv_text
from adaptivesched.workloads.validate import ValidationError, validate_jobs

ARCHIVE = "https://www.cs.huji.ac.il/labs/parallel/workload/"


def _open(path: Path):
    return gzip.open(path, "rt", encoding="utf-8", errors="replace") if path.suffix == ".gz" \
        else open(path, encoding="utf-8", errors="replace")


def read_swf(path) -> tuple[dict, list[JobSpec], dict]:
    """(header {label: value}, kept jobs in file order, dropped counts by reason)."""
    path = Path(path)
    if not path.exists():
        raise ValidationError(f"SWF file not found: {path}")
    header, jobs = {}, []
    dropped = {"run time <= 0": 0, "no processor count": 0, "more processors than the machine": 0}
    rows = []
    try:
        with _open(path) as f:
            for lineno, line in enumerate(f, 1):
                s = line.strip()
                if not s:
                    continue
                if s.startswith(";"):
                    if m := re.match(r";\s*(\w+):\s*(.*)", s):
                        header.setdefault(m[1], m[2].strip())
                    continue
                fields = s.split()
                if len(fields) < 18:
                    raise ValidationError(f"{path.name} line {lineno}: expected 18 SWF fields, got {len(fields)}")
                rows.append((lineno, fields))
    except (OSError, EOFError, gzip.BadGzipFile) as e:
        raise ValidationError(f"{path.name}: cannot read as SWF ({type(e).__name__}: {e}); "
                              "is it the .swf.gz file itself and not an HTML error page?") from None
    procs = header.get("MaxProcs") or header.get("MaxNodes")
    if not procs or not re.match(r"\d+", procs):
        raise ValidationError(f"{path.name}: header has no MaxProcs or MaxNodes line; cannot size the cluster")
    max_procs = int(re.match(r"\d+", procs)[0])
    for lineno, f in rows:
        try:
            job, submit, run, alloc, req = int(f[0]), float(f[1]), float(f[3]), int(f[4]), int(f[7])
        except ValueError:
            raise ValidationError(f"{path.name} line {lineno}: fields 1, 2, 4, 5, 8 must be numbers") from None
        cores = alloc if alloc > 0 else req
        runtime = round(run)
        if runtime <= 0:
            dropped["run time <= 0"] += 1
        elif cores <= 0:
            dropped["no processor count"] += 1
        elif cores > max_procs:
            dropped["more processors than the machine"] += 1
        else:
            jobs.append(JobSpec(job, int(submit), runtime, cores))
    header["_max_procs"] = max_procs
    return header, jobs, dropped


def swf_window(path, n_jobs: int, start: int | None = None) -> tuple[str, int, dict]:
    """CSV text of n_jobs consecutive kept jobs from `start` (default: centred in the log), the
    cluster's CPU cores, and a summary dict."""
    path = Path(path)
    header, jobs, dropped = read_swf(path)
    if isinstance(n_jobs, bool) or not isinstance(n_jobs, int) or n_jobs <= 0:
        raise ValidationError(f"jobs must be an integer > 0, got {n_jobs!r}")
    if n_jobs > len(jobs):
        raise ValidationError(f"{path.name} has {len(jobs)} usable jobs; cannot take {n_jobs}")
    start = (len(jobs) - n_jobs) // 2 if start is None else start
    if not 0 <= start <= len(jobs) - n_jobs:
        raise ValidationError(f"start must be in 0..{len(jobs) - n_jobs} for {n_jobs} jobs, got {start}")
    window = jobs[start:start + n_jobs]
    t0 = window[0].arrival_time
    window = [JobSpec(j.job_id, j.arrival_time - t0, j.runtime, j.required_cores) for j in window]
    cores = header["_max_procs"]
    validate_jobs(window, cores)
    span = window[-1].arrival_time
    info = {"source": path.name, "computer": header.get("Computer", "?"), "cluster_cores": cores,
            "jobs_in_log": len(jobs), "window_start": start, "window_jobs": n_jobs,
            "first_job": window[0].job_id, "last_job": window[-1].job_id, "arrival_span_s": span,
            "dropped": dropped}
    comments = [
        f"source: {path.name} (Parallel Workloads Archive, {ARCHIVE}); cite Feitelson, Tsafrir, Krakov, JPDC 2014",
        f"computer: {info['computer']}; log start: {header.get('StartTime', '?')}",
        f"cluster_cores: {cores}",
        f"window: usable jobs {start}..{start + n_jobs - 1} of {len(jobs)} (SWF jobs {window[0].job_id}.."
        f"{window[-1].job_id}), arrivals shifted by -{t0} s, span {span} s ({span / 86400:.1f} days)",
        "dropped from the whole log: " + ", ".join(f"{k}: {v}" for k, v in dropped.items()),
        "mapping: job_id=SWF 1; arrival_time=SWF 2 - first; runtime=round(SWF 4); "
        "required_cores=SWF 5 (SWF 8 if 5 missing); time unit: seconds",
    ]
    return to_csv_text(window, comments), cores, info


def declared_cores(csv_path) -> int | None:
    """The `# cluster_cores: N` comment a converted trace carries (None if absent)."""
    try:
        with open(csv_path, encoding="utf-8") as f:
            for _, line in zip(range(20), f):
                if m := re.match(r"#\s*cluster_cores:\s*(\d+)", line):
                    return int(m[1])
    except OSError:
        pass
    return None
