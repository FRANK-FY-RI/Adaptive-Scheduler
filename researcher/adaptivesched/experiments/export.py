"""Write and read per-job records and run summaries (RES-FR-11).

Files are UTF-8 with '\\n' line endings on every OS, so reruns diff byte-for-byte.
"""
from __future__ import annotations

import csv
import json
from dataclasses import astuple, fields
from pathlib import Path

from adaptivesched.experiments.adapter import JobRecord

RECORD_FIELDS = [f.name for f in fields(JobRecord)]


def write_records(records, path: Path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(RECORD_FIELDS)
        w.writerows(astuple(r) for r in records)


def read_records(path) -> tuple[JobRecord, ...]:
    with open(path, encoding="utf-8", newline="") as f:
        return tuple(JobRecord(*(int(row[k]) for k in RECORD_FIELDS)) for row in csv.DictReader(f))


def write_json(obj, path: Path) -> None:
    Path(path).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8", newline="\n")


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
