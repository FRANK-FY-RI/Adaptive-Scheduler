"""UC-R02: workloads x strategies (x seeds). One failure never stops the batch (SPEC §3.4)."""
from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from adaptivesched.experiments.config import BatchConfig
from adaptivesched.experiments.export import write_json, write_run
from adaptivesched.experiments.runner import run_one
from adaptivesched.metrics.summary import package_version, run_id, sha12

BATCH_FIELDS = ["run_id", "status", "strategy", "workload_id", "cluster_cores", "error"]


def _resolved(cfg: BatchConfig) -> dict:
    resolved = asdict(cfg)
    resolved.pop("output_dir")
    if not resolved["variants"]:
        resolved.pop("variants")  # keeps run-set ids of batches without variants unchanged
    return resolved


def batch_dir(cfg: BatchConfig, engine: str) -> Path:
    """Where run_batch writes: <output_dir>/batch_<sha12 of (config without output_dir, engine)>."""
    return Path(cfg.output_dir) / f"batch_{sha12([_resolved(cfg), engine])}"


def run_batch(cfg: BatchConfig, adapter, engine: str, on_progress=None) -> Path:
    """Runs serially; on_progress(done, total), if given, is called after every run.
    ponytail: one process; a 300-job run takes well under a second — add multiprocessing.Pool
    over cfg.runs() if larger workloads make studies slow."""
    resolved = _resolved(cfg)
    out = batch_dir(cfg, engine)
    run_set_id = out.name.removeprefix("batch_")
    (out / "runs").mkdir(parents=True, exist_ok=True)

    rows, engine_versions = [], []
    runs = cfg.runs()
    for i, rc in enumerate(runs, 1):
        o = run_one(rc, adapter)
        if o.status == "ok":
            write_run(o, out / "runs")
            rid = o.summary["metadata"]["run_id"]
            engine_versions.append(o.summary["metadata"]["engine_version"])
        else:
            rid = run_id(o.workload_id, rc.strategy, rc.strategy_params, rc.cluster_cores, engine)
        rows.append({"run_id": rid, "status": o.status, "strategy": rc.strategy,
                     "workload_id": o.workload_id, "cluster_cores": rc.cluster_cores,
                     "error": o.error or ""})
        if on_progress:
            on_progress(i, len(runs))

    with open(out / "batch_summary.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, BATCH_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    write_json({
        "run_set_id": run_set_id,
        "config": resolved,
        "workloads": cfg.workload_ids(),
        "strategies": cfg.strategies,
        "engine": engine,
        "engine_versions": sorted(set(engine_versions)),
        "package_version": package_version(),
        "runs_attempted": len(rows),
        "runs_ok": sum(r["status"] == "ok" for r in rows),
        "runs_failed": sum(r["status"] == "failed" for r in rows),
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, out / "batch_manifest.json")
    return out


def read_batch_summary(batch_dir) -> list[dict]:
    path = Path(batch_dir) / "batch_summary.csv"
    if not path.exists():
        raise FileNotFoundError(f"{batch_dir}: no batch_summary.csv; pass a directory written by `adaptivesched batch`")
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))
