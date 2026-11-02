"""Preemptive strategies, string job ids and labelled variants through the experiment layer."""
from dataclasses import replace
from pathlib import Path

import pytest

from adaptivesched.analysis.gantt import lane_segments
from adaptivesched.analysis.inspect import inspect_job
from adaptivesched.experiments.adapter import JobRecord, TeamEngineAdapter, record_problems
from adaptivesched.experiments.batch import read_batch_summary, run_batch
from adaptivesched.experiments.compare import load_rows
from adaptivesched.experiments.config import BatchConfig, RunConfig, load_batch_config
from adaptivesched.experiments.export import read_json, read_records, write_run
from adaptivesched.experiments.runner import run_one
from adaptivesched.workloads.loader import load_csv
from adaptivesched.workloads.validate import ValidationError

TEAM_CSV = Path(__file__).resolve().parents[2] / "workloads" / "synthetic_workload.csv"


@pytest.fixture
def preempt_csv(tmp_path):
    """2 CPU cores. L(arr 0, run 100, 2 cores), S(arr 10, run 1, 2 cores)."""
    p = tmp_path / "preempt.csv"
    p.write_text("job_id,arrival_time,runtime,required_cores\nL,0,100,2\nS,10,1,2\n")
    return str(p)


def test_srtf_run_records_segments_and_round_trips(preempt_csv, tmp_path):
    """srtf at t=10: S (remaining 1) < L (remaining 90) -> L suspended. Segments L [0,10), [11,101).
    waits: L 101-0-100 = 1, S 0 -> avg .5. One preemption; summary says preemptive."""
    out = run_one(RunConfig(preempt_csv, "srtf", 2), TeamEngineAdapter())
    assert out.status == "ok", out.error
    s = out.summary
    assert (s["average_waiting_time"], s["total_preemptions"], s["preemptive"]) == (0.5, 1, True)
    rec, summ = write_run(out, tmp_path)
    back = read_records(rec)
    assert back == out.result.records
    assert {r.job_id: r.execution_segments for r in back}["L"] == ((0, 10), (11, 101))
    assert "L,0,0,101,100,1,101,2,1,0-10;11-101" in rec.read_text()
    text, ok = inspect_job(rec, "L")
    assert ok and "segments        [0, 10); [11, 101)" in text and "preemption_count 1" in text


def test_non_preemptive_strategy_is_marked_so(preempt_csv):
    out = run_one(RunConfig(preempt_csv, "adaptive_multifactor", 2), TeamEngineAdapter())
    assert out.status == "ok" and out.summary["preemptive"] is False and out.summary["total_preemptions"] == 0
    on = run_one(RunConfig(preempt_csv, "adaptive_multifactor", 2, {"preemptive": True}), TeamEngineAdapter())
    assert on.summary["preemptive"] is True and on.summary["total_preemptions"] == 1


def test_team_workload_with_string_ids_runs():
    """workloads/synthetic_workload.csv uses ids J1..; it loads, runs on every strategy and keeps ids."""
    w = load_csv(TEAM_CSV, 8)
    assert w.jobs[0].job_id == "J1"
    for strategy in TeamEngineAdapter().strategies():
        out = run_one(RunConfig(str(TEAM_CSV), strategy, 8), TeamEngineAdapter())
        assert out.status == "ok", (strategy, out.error)
        assert {r.job_id for r in out.result.records} == {j.job_id for j in w.jobs}


def test_empty_job_id_rejected(tmp_path):
    p = tmp_path / "w.csv"
    p.write_text("job_id,arrival_time,runtime,required_cores\n,0,5,1\n")
    with pytest.raises(ValidationError, match="line 2, field job_id: must not be empty"):
        load_csv(p, 4)


def test_record_problems_catch_bad_segments():
    good = JobRecord(1, 0, 0, 101, 100, 1, 2, 1, ((0, 10), (11, 101)))
    assert record_problems(good) == []
    assert "execution segments sum to runtime" in record_problems(replace(good, execution_segments=((0, 10), (11, 100))))
    assert "segments are positive, ordered and non-overlapping" in \
        record_problems(replace(good, execution_segments=((0, 12), (11, 101))))
    assert "number of segments == preemption_count + 1" in record_problems(replace(good, preemption_count=0))


def test_lane_segments_draw_each_execution_segment():
    """2 CPU cores. L (2 cores) [0,10) and [11,101); S (2 cores) [10,11).
    t=0 L lanes 0-1; t=10 L frees, S takes 0-1; t=11 S frees, L takes 0-1 again."""
    recs = [JobRecord("L", 0, 0, 101, 100, 1, 2, 1, ((0, 10), (11, 101))),
            JobRecord("S", 10, 10, 11, 1, 0, 2, 0, ((10, 11),))]
    assert lane_segments(recs, 2) == [("L", 0, 10, 0, 2), ("S", 10, 11, 0, 2), ("L", 11, 101, 0, 2)]


def test_variants_run_one_strategy_with_two_configurations(tmp_path, preempt_csv):
    """amf_preemptive is adaptive_multifactor with preemptive=True; labels keep them apart in one batch."""
    cfg = tmp_path / "b.yaml"
    cfg.write_text(f"cluster_cores: 2\nworkloads: [{preempt_csv}]\n"
                   "strategies: [adaptive_multifactor, amf_preemptive]\n"
                   "variants: {amf_preemptive: {strategy: adaptive_multifactor, params: {preemptive: true}}}\n"
                   f"output_dir: {tmp_path.as_posix()}/r\n")
    bc = load_batch_config(cfg)
    assert [(r.strategy, r.base_strategy, r.strategy_params) for r in bc.runs()] == [
        ("adaptive_multifactor", "", {}), ("amf_preemptive", "adaptive_multifactor", {"preemptive": True})]
    out = run_batch(bc, TeamEngineAdapter(), "team")
    rows = {r["strategy"]: r for r in load_rows(out)}
    assert rows["adaptive_multifactor"]["total_preemptions"] == 0 and rows["amf_preemptive"]["total_preemptions"] == 1
    s = read_json(out / "runs" / f"{rows['amf_preemptive']['run_id']}.summary.json")
    assert s["strategy"] == "amf_preemptive" and s["metadata"]["base_strategy"] == "adaptive_multifactor"
    assert all(r["status"] == "ok" for r in read_batch_summary(out))


@pytest.mark.parametrize("text, msg", [
    ("strategies: [a]\nvariants: {b: {strategy: fifo}}\n", "variants: 'b' must be listed in strategies"),
    ("strategies: [a]\nvariants: {a: {strategy: fifo, extra: 1}}\n", "variants: 'a'"),
    ("strategies: [a, a]\n", "each label may appear once"),
])
def test_variant_config_errors(tmp_path, text, msg):
    p = tmp_path / "b.yaml"
    p.write_text("cluster_cores: 2\nworkloads: [x]\n" + text)
    with pytest.raises(ValidationError, match=msg):
        load_batch_config(p)


def test_batch_progress_callback(tmp_path):
    seen = []
    run_batch(BatchConfig(4, ["tests/workloads/hol_block.csv"], ["fifo", "sjf"], output_dir=str(tmp_path)),
              TeamEngineAdapter(), "team", on_progress=lambda i, n: seen.append((i, n)))
    assert seen == [(1, 2), (2, 2)]
