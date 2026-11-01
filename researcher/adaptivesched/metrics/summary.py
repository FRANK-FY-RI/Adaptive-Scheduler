"""Run summary in RES §8 field order, plus the reproducibility metadata block (SPEC §3.3)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Mapping

from adaptivesched.experiments.adapter import RunResult
from adaptivesched.metrics import definitions as m


def sha12(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:12]


def package_version() -> str:
    try:
        return version("adaptivesched")
    except PackageNotFoundError:
        return "unknown (not installed)"


def run_id(workload_id: str, strategy: str, strategy_params: Mapping, cluster_cores: int,
           engine: str) -> str:
    return sha12([workload_id, strategy, dict(strategy_params), cluster_cores, engine])


def build_summary(result: RunResult, workload_params: Mapping[str, Any],
                  strategy_params: Mapping[str, Any], config_hash: str) -> dict:
    r = result.records
    return {
        "strategy": result.strategy,
        "workload": result.workload_id,
        "cluster_cores": result.cluster_cores,
        "total_jobs": len(r),
        "average_waiting_time": m.average_waiting_time(r),
        "max_waiting_time": m.max_waiting_time(r),
        "cpu_utilization": m.cpu_utilization_pct(r, result.cluster_cores),
        "makespan": m.makespan(r),
        "bounded_slowdown": m.bounded_slowdown(r),
        "tau": m.TAU,
        "average_turnaround_time": m.average_turnaround_time(r),
        "utilization_interval": "first arrival to last completion (makespan)",
        "metadata": {
            "run_id": run_id(result.workload_id, result.strategy, strategy_params,
                             result.cluster_cores, result.engine),
            "workload_id": result.workload_id,
            "workload_params": dict(workload_params),
            "strategy": result.strategy,
            "strategy_params": dict(strategy_params),
            "strategy_dispatch_note": result.strategy_dispatch_note,
            "cluster_cores": result.cluster_cores,
            "engine": result.engine,
            "engine_version": result.engine_version,
            "package_version": package_version(),
            "config_hash": config_hash,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    }
