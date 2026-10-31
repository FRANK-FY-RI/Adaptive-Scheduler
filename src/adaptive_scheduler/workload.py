"""Workload loading utilities for AdaptiveSched."""

import csv
from pathlib import Path
from typing import Sequence

from adaptive_scheduler.exceptions import ConfigurationError
from adaptive_scheduler.models import JobSpec


def load_workload_from_csv(file_path: str | Path) -> list[JobSpec]:
    """Parses a CSV file into a validated list of JobSpec instances.

    Args:
        file_path: Path to the CSV file.

    Returns:
        List of JobSpec objects ordered as read from the file.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Workload file not found: {path}")

    jobs: list[JobSpec] = []
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required_fields = {"job_id", "arrival_time", "runtime", "required_cores"}
        if not reader.fieldnames or not required_fields.issubset(reader.fieldnames):
            raise ConfigurationError(
                f"CSV must contain headers {required_fields}; got {reader.fieldnames}."
            )

        for row_idx, row in enumerate(reader, start=2):
            try:
                job_id = row["job_id"].strip()
                arrival_time = int(row["arrival_time"].strip())
                runtime = int(row["runtime"].strip())
                required_cores = int(row["required_cores"].strip())
            except ValueError as e:
                raise ConfigurationError(
                    f"Invalid integer formatting on CSV line {row_idx}: {e}"
                ) from e

            jobs.append(
                JobSpec(
                    job_id=job_id,
                    arrival_time=arrival_time,
                    runtime=runtime,
                    required_cores=required_cores,
                )
            )

    return jobs
