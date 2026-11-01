from pathlib import Path

import pytest

from adaptivesched.cli import main
from adaptivesched.experiments.adapter import FakeEngineAdapter
from adaptivesched.experiments.batch import read_batch_summary, run_batch
from adaptivesched.experiments.compare import comparison_table, compare, load_rows
from adaptivesched.experiments.config import BatchConfig

WORKLOADS = ["synth:light:n=40:seed=7", "synth:short_heavy:n=40:seed=7", "tests/workloads/hol_block.csv"]


def batch(out, workloads=WORKLOADS, seeds=()):
    return run_batch(BatchConfig(4, list(workloads), ["fifo", "sjf"], seeds=list(seeds), output_dir=str(out)),
                     FakeEngineAdapter(), "fake")


def files_without_timestamps(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): b"\n".join(l for l in p.read_bytes().split(b"\n")
                                                       if b'"timestamp":' not in l)
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_rerun_is_byte_identical_except_timestamps(tmp_path):
    """Hard rule 1: two batch runs into two directories; every file equal once timestamp lines go."""
    a, b = batch(tmp_path / "a", seeds=[7, 11]), batch(tmp_path / "b", seeds=[7, 11])
    compare(a), compare(b)
    assert a.name == b.name
    fa, fb = files_without_timestamps(a), files_without_timestamps(b)
    assert len(fa) == 2 + 2 * 2 * 5 + 2  # summary, manifest, 10 runs x 2 files, compare csv+md
    assert fa == fb


def test_failed_run_is_listed_not_dropped(tmp_path):
    """One CSV has a 9-core job on a 4-core cluster: both its runs fail, the other 6 are ok."""
    bad = tmp_path / "impossible.csv"
    bad.write_text("job_id,arrival_time,runtime,required_cores\n1,0,5,1\n2,0,5,9\n")
    out = batch(tmp_path / "o", WORKLOADS + [str(bad)])
    rows = read_batch_summary(out)
    assert len(rows) == 8
    failed = [r for r in rows if r["status"] == "failed"]
    assert {r["strategy"] for r in failed} == {"fifo", "sjf"}
    assert all("impossible.csv line 3, field required_cores" in r["error"] for r in failed)
    assert sum(r["status"] == "ok" for r in rows) == 6
    md = compare(out)[2]
    assert md.count("failed: ValidationError") == 2


def test_compare_one_table_per_workload_and_refuses_mixing(tmp_path):
    out = batch(tmp_path / "o")
    rows = load_rows(out)
    md = compare(out)[2]
    assert md.count("### ") == 3 and "engine: fake" in md
    hol = [r for r in rows if r["workload_id"].startswith("csv:hol_block.csv:")]
    assert [(r["strategy"], r["average_waiting_time"], r["max_waiting_time"]) for r in hol] == \
           [("fifo", 6.5, 9), ("sjf", 2.25, 9)]  # hand-computed in test_fake_engine
    with pytest.raises(ValueError, match="refusing to compare runs with different workload ids"):
        comparison_table(rows)
    with pytest.raises(ValueError, match="CPU core capacities"):
        comparison_table([hol[0], {**hol[1], "cluster_cores": 8}])


def test_cli_batch_and_compare(tmp_path, capsys):
    cfg = tmp_path / "b.yaml"
    cfg.write_text(f"cluster_cores: 4\nworkloads: [tests/workloads/hol_block.csv]\n"
                   f"strategies: [fifo, sjf, edf]\noutput_dir: {tmp_path.as_posix()}/r\n")
    assert main(["batch", "--config", str(cfg), "--engine", "fake"]) == 1  # edf fails, reported
    out = capsys.readouterr().out
    assert "3 runs attempted, 2 ok, 1 failed" in out and "unknown identifier 'edf'" in out
    batch_dir = next((tmp_path / "r").iterdir())
    assert main(["compare", "--batch", str(batch_dir)]) == 0
    assert main(["compare", "--batch", str(tmp_path)]) == 1
