"""CSV workloads (SPEC §1.1): header `job_id,arrival_time,runtime,required_cores`, integers,
`#` comment lines and blank lines ignored."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from adaptivesched.experiments.adapter import JobSpec
from adaptivesched.workloads.validate import ValidationError, validate_jobs

HEADER = ("job_id", "arrival_time", "runtime", "required_cores")


@dataclass(frozen=True)
class Workload:
    workload_id: str
    jobs: tuple[JobSpec, ...]
    params: Mapping[str, Any]  # generator params or CSV hash; always has runtime_estimate_error


def to_csv_text(jobs: Iterable[JobSpec], comments: Iterable[str] = ()) -> str:
    lines = [f"# {c}" for c in comments] + [",".join(HEADER)]
    lines += [f"{j.job_id},{j.arrival_time},{j.runtime},{j.required_cores}" for j in jobs]
    return "\n".join(lines) + "\n"


def content_hash(jobs: Iterable[JobSpec]) -> str:
    """sha256[:12] of the jobs in job_id order: ignores comments, whitespace and row order."""
    canonical = to_csv_text(sorted(jobs, key=lambda j: j.job_id))
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


def load_csv(path: str | Path, cluster_cores: int | None = None) -> Workload:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ValidationError(f"workload file not found: {path}") from None

    jobs, locations, header_seen = [], [], False
    for lineno, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        at = f"{path.name} line {lineno}"
        fields = [f.strip() for f in s.split(",")]
        if not header_seen:
            if tuple(fields) != HEADER:
                raise ValidationError(f"{at}: header must be exactly {','.join(HEADER)}, got {s!r}")
            header_seen = True
            continue
        if len(fields) != len(HEADER):
            raise ValidationError(f"{at}: expected {len(HEADER)} columns ({','.join(HEADER)}), "
                                  f"got {len(fields)}")
        values = []
        for name, f in zip(HEADER, fields):
            try:
                values.append(int(f))
            except ValueError:
                raise ValidationError(f"{at}, field {name}: {f!r} is not an integer") from None
        jobs.append(JobSpec(*values))
        locations.append(at)

    if not header_seen:
        raise ValidationError(f"{path.name}: no header; expected {','.join(HEADER)}")
    validate_jobs(jobs, cluster_cores, locations)
    digest = content_hash(jobs)
    return Workload(f"csv:{path.name}:{digest}", tuple(jobs),
                    {"source": "csv", "file": path.name, "content_sha256_12": digest,
                     "runtime_estimate_error": 0.0})
