import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from adaptivesched.analysis import plots
from adaptivesched.analysis.gantt import gantt_pair, lane_segments
from adaptivesched.analysis.inspect import inspect_job
from adaptivesched.cli import main
from adaptivesched.experiments.adapter import FakeEngineAdapter, JobRecord
from adaptivesched.experiments.batch import run_batch
from adaptivesched.experiments.compare import load_rows
from adaptivesched.experiments.config import BatchConfig


@pytest.fixture(scope="module")
def batch_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("b")
    cfg = BatchConfig(4, ["tests/workloads/hol_block.csv", "synth:heavy:n=30:seed=7"], ["fifo", "sjf"],
                      seeds=[7, 11], output_dir=str(out))
    return run_batch(cfg, FakeEngineAdapter(), "fake")


def digests(root):
    return {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(root).rglob("*") if p.is_file()}


def test_plots_leave_inputs_unchanged(batch_dir, tmp_path):
    before = digests(batch_dir)
    hol = next(r["workload_id"] for r in load_rows(batch_dir) if r["workload_id"].startswith("csv:"))
    written = []
    written += plots.metric_grid(batch_dir, "average_waiting_time", tmp_path / "grid")
    written += plots.metric_bars([r for r in load_rows(batch_dir) if r["workload_id"] == hol],
                                 "max_waiting_time", tmp_path / "bars")
    written += plots.tradeoff_scatter(batch_dir, tmp_path / "scatter")
    written += plots.waiting_time_cdf(batch_dir, hol, tmp_path / "cdf")
    written += gantt_pair(batch_dir, hol, "fifo", "sjf", tmp_path / "gantt")
    assert digests(batch_dir) == before
    assert all(p.stat().st_size > 0 for p in written) and len(written) == 10


def test_lane_segments_use_recorded_times_only():
    """hol_block FIFO records (4 CPU cores). Lanes first-fit:
    t=0  job 1 (2 cores) -> lanes 0-1.
    t=10 job 1 frees 0-1; job 2 (3) -> lanes 0,1,2; job 3 (1) -> lane 3.
    t=12 job 3 frees 3; job 4 (1) -> lane 3.
    Runtime is deliberately inconsistent on job 4 (99) to show only start/finish are drawn."""
    recs = [JobRecord(1, 0, 0, 10, 10, 0, 2), JobRecord(2, 1, 10, 15, 5, 9, 3),
            JobRecord(3, 2, 10, 12, 2, 8, 1), JobRecord(4, 3, 12, 14, 99, 9, 1)]
    assert lane_segments(recs, 4) == [(1, 0, 10, 0, 2), (2, 10, 15, 0, 3), (3, 10, 12, 3, 1), (4, 12, 14, 3, 1)]


def test_lane_segments_split_non_contiguous_lanes():
    """3 CPU cores: A [0,5) lane 0, B [0,9) lane 1, A ends, C (2 cores) [5,9) -> lanes 0 and 2."""
    recs = [JobRecord(1, 0, 0, 5, 5, 0, 1), JobRecord(2, 0, 0, 9, 9, 0, 1), JobRecord(3, 0, 5, 9, 4, 5, 2)]
    assert lane_segments(recs, 3) == [(1, 0, 5, 0, 1), (2, 0, 9, 1, 1), (3, 5, 9, 0, 1), (3, 5, 9, 2, 1)]


def test_inspect(batch_dir, tmp_path, capsys):
    row = next(r for r in load_rows(batch_dir) if r["workload_id"].startswith("csv:") and r["strategy"] == "fifo")
    run = batch_dir / "runs" / row["run_id"]
    text, ok = inspect_job(run, 2)
    assert ok and "start_time      10" in text and "derived waiting time     9" in text
    assert main(["inspect", "--run", str(run) + ".summary.json", "--job", "3"]) == 0
    assert main(["inspect", "--run", str(run), "--job", "99"]) == 1

    bad = tmp_path / "x.records.csv"
    bad.write_text("job_id,arrival_time,start_time,finish_time,runtime,waiting_time,required_cores\n1,0,4,9,3,4,1\n")
    text, ok = inspect_job(tmp_path / "x", 1)
    assert not ok and "[FAILED] finish_time == start_time + runtime" in text


def test_cli_plot(batch_dir, capsys):
    assert main(["plot", "--batch", str(batch_dir), "--metric", "makespan"]) == 0
    assert "grid_makespan.png" in capsys.readouterr().out
    hol = next(r["workload_id"] for r in load_rows(batch_dir) if r["workload_id"].startswith("csv:"))
    assert main(["plot", "--batch", str(batch_dir), "--gantt", hol, "fifo", "sjf"]) == 0
    assert main(["plot", "--batch", str(batch_dir), "--gantt", hol, "fifo", "edf"]) == 1


def test_analysis_and_metrics_never_import_simulation_logic():
    """RES-NFR-06: importing analysis/ and metrics/ must not load the engine, strategies or the fake."""
    code = ("import sys, adaptivesched.analysis.plots, adaptivesched.analysis.gantt, "
            "adaptivesched.analysis.inspect, adaptivesched.metrics.summary; "
            "bad = [m for m in sys.modules if m.endswith('_fake_engine') or "
            "m.startswith(('adaptivesched.engine', 'adaptivesched.strategies'))]; "
            "assert not bad, bad")
    subprocess.run([sys.executable, "-c", code], check=True)


def test_shared_row_scale_fits_every_panel():
    """Regression: set_ylim in _bars froze a sharey row at the first panel (short_heavy seeds
    11/13 clipped at ~1040 while the values reached 1834). Every panel's tallest bar must fit."""
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, sharey="row")
    for ax, v in zip(axes, (10, 1000)):
        plots._bars(ax, [{"workload_id": "w", "cluster_cores": 4, "status": "ok", "strategy": "fifo",
                          "m": v}], "m")
    assert axes[0].get_ylim()[0] == 0 and axes[0].get_ylim()[1] >= 1000
    plt.close(fig)


def test_findings_rank_within_seed(batch_dir):
    """Fake engine, 4 CPU cores. hol_block (SPEC §1.3, tests/test_fake_engine.py):
    fifo waits 0,9,8,9 -> avg 6.5, max 9;  sjf waits 0,9,0,0 -> avg 2.25, max 9.
    So on avg wait sjf leads and fifo trails; on max wait both are 9 -> tie, nobody leads;
    makespan 15 for both -> tie. Slowdown (tau 10), runtimes 10,5,2,2:
    fifo (10/10, 14/10, 10/10, 11/10) -> mean 1.125; sjf (1, 1.4, max(1, 2/10), 1) -> 1.1: sjf leads.
    One workload id (CSV, no seeds) -> counts are k/1."""
    from adaptivesched.analysis.findings import seed_results, tradeoff_table

    hol = next(v for (cond, _), v in seed_results(batch_dir).items() if cond.startswith("csv:"))
    assert len(hol) == 1
    assert hol[0]["average_waiting_time"] == ({"sjf"}, {"fifo"})
    assert hol[0]["max_waiting_time"] == (set(), set())
    assert hol[0]["makespan"] == (set(), set())
    table = tradeoff_table(batch_dir)
    assert "| sjf | led: avg wait 1/1, slowdown 1/1<br>trailed: -" in table
