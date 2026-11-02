"""Write and read per-job records and run summaries (RES-FR-11).

Files are UTF-8 with '\\n' line endings on every OS, so reruns diff byte-for-byte.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from adaptivesched.experiments.adapter import JobRecord, parse_job_id

# turnaround_time is finish - arrival, written for readers of the CSV; it is not read back.
# execution_segments: "start-finish" intervals joined by ";", e.g. "0-10;11-101".
RECORD_FIELDS = ["job_id", "arrival_time", "start_time", "finish_time", "runtime", "waiting_time",
                 "turnaround_time", "required_cores", "preemption_count", "execution_segments"]
_INTS = ["arrival_time", "start_time", "finish_time", "runtime", "waiting_time", "required_cores"]


def write_records(records, path: Path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(RECORD_FIELDS)
        for r in records:
            w.writerow([r.job_id, r.arrival_time, r.start_time, r.finish_time, r.runtime, r.waiting_time,
                        r.finish_time - r.arrival_time, r.required_cores, r.preemption_count,
                        ";".join(f"{a}-{b}" for a, b in r.segments())])


def _segments(text: str) -> tuple[tuple[int, int], ...]:
    return tuple(tuple(int(x) for x in seg.split("-")) for seg in text.split(";") if seg)


def read_records(path) -> tuple[JobRecord, ...]:
    """Reads files from before preemption support too (no segment/preemption columns)."""
    with open(path, encoding="utf-8", newline="") as f:
        return tuple(JobRecord(parse_job_id(row["job_id"]), *(int(row[k]) for k in _INTS),
                               int(row.get("preemption_count") or 0),
                               _segments(row.get("execution_segments") or ""))
                     for row in csv.DictReader(f))


def _finite(obj):
    """inf/nan are not JSON (browsers refuse 'Infinity'); store them as the strings "inf", "nan"."""
    if isinstance(obj, float) and obj != obj or obj in (float("inf"), float("-inf")):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_finite(v) for v in obj]
    return obj


def write_json(obj, path: Path) -> None:
    Path(path).write_text(json.dumps(_finite(obj), indent=2, allow_nan=False) + "\n",
                          encoding="utf-8", newline="\n")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_run(outcome, runs_dir) -> tuple[Path, Path]:
    """`<runs_dir>/<run_id>.records.csv` and `.summary.json` for an ok outcome."""
    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    rid = outcome.summary["metadata"]["run_id"]
    rec, summ = runs_dir / f"{rid}.records.csv", runs_dir / f"{rid}.summary.json"
    write_records(outcome.result.records, rec)
    write_json(outcome.summary, summ)
    return rec, summ
