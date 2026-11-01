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


def run_batch(cfg: BatchConfig, adapter, engine: str) -> Path:
    """Runs serially. ponytail: one process; a 300-job run takes well under a second on the fake
    engine — add multiprocessing.Pool over cfg.runs() if the team engine makes the study slow."""
    resolved = asdict(cfg)
    resolved.pop("output_dir")
    run_set_id = sha12([resolved, engine])
    out = Path(cfg.output_dir) / f"batch_{run_set_id}"
    (out / "runs").mkdir(parents=True, exist_ok=True)

    rows, engine_versions = [], []
    for rc in cfg.runs():
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
