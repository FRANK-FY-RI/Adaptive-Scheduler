"""Hand-computed schedules for the researcher strategies in examples/researcher_strategies.py,
run through the team engine via the adapter's strategy-file path. Each workload is chosen so the
strategy's schedule differs from SJF first-fit (computed alongside, in the docstring)."""
from pathlib import Path

import pytest

from adaptivesched.experiments.adapter import JobSpec, TeamEngineAdapter
from adaptivesched.experiments.config import RunConfig, load_batch_config
from adaptivesched.experiments.runner import run_one

FILE = str(Path(__file__).resolve().parents[2] / "examples" / "researcher_strategies.py")


def starts(jobs, cores, cls):
    res = TeamEngineAdapter().run(jobs, cores, cls, {}, workload_id="x", strategy_file=f"{FILE}:{cls}")
    assert f"researcher_strategies.py:{cls} (file sha256 " in res.strategy_dispatch_note
    return [r.start_time for r in res.records]


def test_sjf_aging():
    """1 CPU core, AGING_RATE 1. Jobs (id: arrival, runtime): 1:(0,2) 2:(1,5) 3:(2,3) 4:(4,3).
    Priority = runtime - (now - arrival).
    t=0 job 1 [0,2).
    t=2 job 2: 5-1=4, job 3: 3-0=3 -> job 3 [2,5).
    t=5 job 2: 5-4=1, job 4: 3-1=2 -> job 2 [5,10).   (SJF picks job 4 here: 3 < 5)
    t=10 job 4 [10,13).
    Starts 0, 5, 2, 10."""
    jobs = [JobSpec(1, 0, 2, 1), JobSpec(2, 1, 5, 1), JobSpec(3, 2, 3, 1), JobSpec(4, 4, 3, 1)]
    assert starts(jobs, 1, "SJFAgingStrategy") == [0, 5, 2, 10]


def test_smallest_area_first():
    """4 CPU cores. Jobs (id: arrival, runtime, cores; area): 1:(0,2,4) 2:(1,3,4;12) 3:(1,5,2;10)
    4:(1,4,2;8).
    t=0 job 1 [0,2), free 0. t=1 jobs 2-4 arrive, nothing fits.
    t=2 free 4: job 4 (area 8) [2,6) free 2; job 3 (area 10) [2,7) free 0.
    t=6 free 2: job 2 needs 4 -> waits. t=7 free 4: job 2 [7,10).
    Starts 0, 7, 2, 2.   (SJF: job 2 first at t=2 since runtime 3 is shortest -> 0, 2, 5, 5)"""
    jobs = [JobSpec(1, 0, 2, 4), JobSpec(2, 1, 3, 4), JobSpec(3, 1, 5, 2), JobSpec(4, 1, 4, 2)]
    assert starts(jobs, 4, "SmallestAreaFirstStrategy") == [0, 7, 2, 2]


def test_best_fit():
    """4 CPU cores. Jobs (id: arrival, runtime, cores): 1:(0,10,1) 2:(1,2,1) 3:(1,4,2) 4:(1,6,3).
    t=0 job 1 [0,10), free 3.
    t=1 free 3: widest fitting is job 4 (3 cores) [1,7), free 0.
    t=7 free 3: job 3 (2 cores) [7,11) free 1; job 2 (1 core) [7,9) free 0.
    Starts 0, 7, 7, 1.   (SJF: jobs 2, 3 at t=1, job 4 at t=5 -> 0, 1, 1, 5)"""
    jobs = [JobSpec(1, 0, 10, 1), JobSpec(2, 1, 2, 1), JobSpec(3, 1, 4, 2), JobSpec(4, 1, 6, 3)]
    assert starts(jobs, 4, "BestFitStrategy") == [0, 7, 7, 1]


def test_strategy_file_rejects_params_and_fake_engine():
    jobs = [JobSpec(1, 0, 1, 1)]
    with pytest.raises(ValueError, match="takes no strategy_params"):
        TeamEngineAdapter().run(jobs, 1, "s", {"x": 1}, workload_id="x", strategy_file=FILE + ":BestFitStrategy")


def test_run_one_with_strategy_file_and_missing_file(tmp_path):
    ok = run_one(RunConfig("synth:light:n=20:seed=1", "best_fit", 8,
                           strategy_file=f"{FILE}:BestFitStrategy"), TeamEngineAdapter())
    assert ok.status == "ok", ok.error
    bad = run_one(RunConfig("synth:light:n=20:seed=1", "nope", 8,
                            strategy_file=str(tmp_path / "nope.py")), TeamEngineAdapter())
    assert bad.status == "failed" and "nope.py" in bad.error


def test_batch_config_strategy_files_resolved_beside_config(tmp_path):
    cfg = tmp_path / "b.yaml"
    cfg.write_text("cluster_cores: 8\nworkloads: [synth:light:n=20:seed=1]\nstrategies: [fifo, aging]\n"
                   "strategy_files: {aging: strategies.py:SJFAgingStrategy}\n", encoding="utf-8")
    runs = load_batch_config(cfg).runs()
    assert [r.strategy_file for r in runs] == ["", str(tmp_path / "strategies.py") + ":SJFAgingStrategy"]
    cfg.write_text(cfg.read_text().replace("{aging:", "{other:"), encoding="utf-8")
    with pytest.raises(Exception, match="must be listed in strategies"):
        load_batch_config(cfg)
