from dataclasses import replace

import pytest

from adaptivesched.experiments.adapter import FakeEngineAdapter, TeamEngineAdapter
from adaptivesched.experiments.config import RunConfig, load_batch_config, load_run_config
from adaptivesched.experiments.export import read_json, read_records, write_run
from adaptivesched.experiments.runner import run_one
from adaptivesched.workloads.validate import ValidationError

HOL = "tests/workloads/hol_block.csv"


def test_ok_run_summary_and_files(tmp_path):
    """hol_block FIFO at 4 CPU cores, schedule from test_fake_engine:
    waits 0, 9, 8, 9 -> avg 6.5, max 9; makespan 15 - 0 = 15;
    busy = 2*10 + 3*5 + 1*2 + 1*2 = 39 -> util 100*39/(4*15) = 65.0."""
    out = run_one(RunConfig(HOL, "fifo", 4), FakeEngineAdapter())
    assert out.status == "ok", out.error
    s = out.summary
    assert list(s)[:10] == ["strategy", "workload", "cluster_cores", "total_jobs", "average_waiting_time",
                            "max_waiting_time", "cpu_utilization", "makespan", "bounded_slowdown", "tau"]
    assert (s["average_waiting_time"], s["max_waiting_time"], s["makespan"], s["cpu_utilization"]) \
        == (6.5, 9, 15, 65.0)
    meta = s["metadata"]
    for k in ["run_id", "workload_id", "workload_params", "strategy", "strategy_params",
              "strategy_dispatch_note", "cluster_cores", "engine", "engine_version",
              "package_version", "config_hash", "timestamp"]:
        assert k in meta
    assert meta["engine"] == "fake" and meta["workload_params"]["runtime_estimate_error"] == 0.0

    rec, summ = write_run(out, tmp_path)
    assert read_records(rec) == out.result.records
    assert read_json(summ) == s
    assert b"\r\n" not in rec.read_bytes() + summ.read_bytes()


@pytest.mark.parametrize("cfg, adapter, message", [
    (RunConfig(HOL, "fifo", 2), FakeEngineAdapter(), "line 5, field required_cores"),
    (RunConfig(HOL, "edf", 4), FakeEngineAdapter(), "unknown identifier 'edf'"),
    (RunConfig("missing.csv", "fifo", 4), FakeEngineAdapter(), "workload file not found"),
    (RunConfig(HOL, "fifo", 4, {"alpha": 1}), TeamEngineAdapter(), "unexpected keyword argument 'alpha'"),
    (RunConfig(HOL, "edf", 4), TeamEngineAdapter(), "unknown identifier 'edf'"),
])
def test_failed_runs_report_not_raise(cfg, adapter, message):
    out = run_one(cfg, adapter)
    assert out.status == "failed" and message in out.error and out.summary is None


class LyingEngine(FakeEngineAdapter):
    """Returns a record whose start time puts 5 CPU cores in use on a 4-core cluster."""

    def run(self, *a, **k):
        res = super().run(*a, **k)
        recs = list(res.records)
        # job 2 (3 cores, arrival 1) moved to [5,10) while job 1 holds 2 cores on [0,10): 5 in use
        recs[1] = replace(recs[1], start_time=5, finish_time=10, waiting_time=4)
        return replace(res, records=tuple(recs))


def test_engine_result_breaking_capacity_is_refused():
    out = run_one(RunConfig(HOL, "fifo", 4), LyingEngine())
    assert out.status == "failed" and "CPU cores in use, capacity 4" in out.error


def test_config_hash_ignores_output_dir():
    assert RunConfig(HOL, "fifo", 4, output_dir="a").config_hash() == \
           RunConfig(HOL, "fifo", 4, output_dir="b").config_hash()
    assert RunConfig(HOL, "fifo", 4).config_hash() != RunConfig(HOL, "sjf", 4).config_hash()


def write(tmp_path, text):
    p = tmp_path / "c.yaml"
    p.write_text(text)
    return p


def test_run_config_ok_and_errors(tmp_path):
    cfg = load_run_config(write(tmp_path, f"workload: {HOL}\nstrategy: sjf\ncluster_cores: 4\n"))
    assert cfg == RunConfig(HOL, "sjf", 4)
    for text, msg in [("strategy: sjf\ncluster_cores: 4\n", "missing required key 'workload'"),
                      (f"workload: {HOL}\nstrategy: sjf\ncluster_cores: 4\ncores: 2\n", "unknown key 'cores'"),
                      (f"workload: {HOL}\nstrategy: sjf\ncluster_cores: four\n", "key cluster_cores: expected int"),
                      (f"workload: {HOL}\nstrategy: sjf\ncluster_cores: 0\n", "key cluster_cores: must be > 0"),
                      ("- a\n- b\n", "expected a mapping"),
                      ("a: [\n", "not valid YAML")]:
        with pytest.raises(ValidationError, match=msg):
            load_run_config(write(tmp_path, text))


def test_batch_config_expands_seeds(tmp_path):
    cfg = load_batch_config(write(tmp_path, f"""
cluster_cores: 16
workloads: [synth:light:n=10:seed=7, {HOL}]
strategies: [fifo, sjf]
repeats: {{seeds: [7, 11]}}
"""))
    assert cfg.workload_ids() == ["synth:light:n=10:seed=7", "synth:light:n=10:seed=11", HOL]
    assert len(cfg.runs()) == 6
    with pytest.raises(ValidationError, match="key repeats"):
        load_batch_config(write(tmp_path, "cluster_cores: 4\nworkloads: [a]\nstrategies: [b]\nrepeats: 3\n"))
