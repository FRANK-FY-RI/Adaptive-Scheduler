"""SWF (Parallel Workloads Archive) conversion. The log below is hand-written; expected values
are worked out line by line in each docstring."""
import gzip

import pytest

from adaptivesched.cli import main
from adaptivesched.experiments.adapter import TeamEngineAdapter
from adaptivesched.experiments.config import RunConfig
from adaptivesched.experiments.runner import run_one
from adaptivesched.workloads.loader import load_csv
from adaptivesched.workloads.swf import declared_cores, read_swf, swf_window
from adaptivesched.workloads.validate import ValidationError

# fields: job submit wait run alloc cpu mem req_procs req_time req_mem status user group exe queue part prev think
SWF = """; Version: 2
; Computer: Test SP2
; MaxNodes: 8
; MaxProcs: 8
; StartTime: Mon Jan  1 00:00:00 2001
1 100 5 60.4 4 -1 -1 4 120 -1 1 1 1 1 1 1 -1 -1
2 110 0 0 2 -1 -1 2 60 -1 5 1 1 1 1 1 -1 -1
3 120 3 30 -1 -1 -1 2 60 -1 1 2 1 1 1 1 -1 -1
4 130 0 10 16 -1 -1 16 60 -1 1 2 1 1 1 1 -1 -1
5 140 1 0.6 1 -1 -1 1 60 -1 0 3 1 1 1 1 -1 -1
6 150 0 20 -1 -1 -1 -1 60 -1 1 3 1 1 1 1 -1 -1
7 160 0 45 8 -1 -1 8 60 -1 1 1 1 1 1 1 -1 -1
"""


@pytest.fixture
def swf(tmp_path):
    p = tmp_path / "test.swf.gz"
    with gzip.open(p, "wt") as f:
        f.write(SWF)
    return p


def test_read_swf_maps_fields_and_drops_unusable_jobs(swf):
    """job 1: run 60.4 -> 60, 4 processors.          kept
    job 2: run 0 (cancelled before start)            dropped: run time <= 0
    job 3: allocated -1 -> requested 2               kept
    job 4: 16 processors on an 8-processor machine   dropped
    job 5: run 0.6 -> 1, failed (status 0) but ran   kept
    job 6: no allocated or requested processors      dropped
    job 7: 8 processors = the whole machine          kept"""
    header, jobs, dropped = read_swf(swf)
    assert header["Computer"] == "Test SP2" and header["_max_procs"] == 8
    assert [(j.job_id, j.arrival_time, j.runtime, j.required_cores) for j in jobs] == [
        (1, 100, 60, 4), (3, 120, 30, 2), (5, 140, 1, 1), (7, 160, 45, 8)]
    assert dropped == {"run time <= 0": 1, "no processor count": 1, "more processors than the machine": 1}


def test_window_is_centred_and_rebased(swf):
    """4 usable jobs, window of 2 -> start (4-2)//2 = 1 -> jobs 3 and 5; first arrival 120 -> 0, 140 -> 20."""
    text, cores, info = swf_window(swf, 2)
    assert cores == 8 and (info["first_job"], info["last_job"]) == (3, 5)
    lines = [l for l in text.splitlines() if not l.startswith("#")]
    assert lines == ["job_id,arrival_time,runtime,required_cores", "3,0,30,2", "5,20,1,1"]
    assert "# cluster_cores: 8" in text and "Parallel Workloads Archive" in text


def test_converted_csv_loads_and_runs(swf, tmp_path, capsys):
    out = tmp_path / "w.csv"
    assert main(["workloads", "--from-swf", str(swf), "--jobs", "4", "--start", "0", "--out", str(out)]) == 0
    assert "4 jobs (SWF 1..7) of 4 usable" in capsys.readouterr().out
    assert declared_cores(out) == 8
    w = load_csv(out, 8)
    assert [j.arrival_time for j in w.jobs] == [0, 20, 40, 60]
    run = run_one(RunConfig(str(out), "adaptive_multifactor", 8), TeamEngineAdapter())
    assert run.status == "ok" and run.summary["completed_jobs"] == 4


def test_errors_are_explicit(swf, tmp_path):
    with pytest.raises(ValidationError, match="has 4 usable jobs; cannot take 9"):
        swf_window(swf, 9)
    with pytest.raises(ValidationError, match="start must be in 0..2"):
        swf_window(swf, 2, start=3)
    html = tmp_path / "blocked.swf.gz"
    html.write_text("<!DOCTYPE html><html>Something went wrong...</html>")
    with pytest.raises(ValidationError, match="not an HTML error page"):
        read_swf(html)
    plain = tmp_path / "noheader.swf"
    plain.write_text("1 0 0 5 1 -1 -1 1 5 -1 1 1 1 1 1 1 -1 -1\n")
    with pytest.raises(ValidationError, match="no MaxProcs or MaxNodes"):
        read_swf(plain)
    short = tmp_path / "short.swf"
    short.write_text("; MaxProcs: 4\n1 0 0 5\n")
    with pytest.raises(ValidationError, match="line 2: expected 18 SWF fields"):
        read_swf(short)
