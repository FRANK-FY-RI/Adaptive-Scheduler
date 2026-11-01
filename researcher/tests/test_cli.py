from adaptivesched.cli import main


def test_strategies_fake(capsys):
    assert main(["strategies", "--engine", "fake"]) == 0
    assert capsys.readouterr().out.splitlines()[1:] == ["fifo", "sjf"]


def test_strategies_team(capsys):
    assert main(["strategies"]) == 0
    assert capsys.readouterr().out.splitlines() == ["adaptive", "easy_backfill", "fifo", "sjf"]


def test_workloads_list_and_show(capsys):
    assert main(["workloads"]) == 0
    out = capsys.readouterr().out
    assert all(n in out for n in ["light", "heavy", "short_heavy", "mixed", "wide_jobs"])
    assert main(["workloads", "--show", "synth:heavy:n=5:seed=7", "--cluster-cores", "16"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "# workload_id: synth:heavy:n=5:seed=7"
    assert lines[2] == "job_id,arrival_time,runtime,required_cores" and len(lines) == 8


def test_workloads_show_bad_input_fails_loudly(capsys):
    assert main(["workloads", "--show", "synth:heavy:n=5:seed=7"]) == 1
    assert "--show needs --cluster-cores" in capsys.readouterr().err
    assert main(["workloads", "--show", "tests/workloads/hol_block.csv", "--cluster-cores", "2"]) == 1
    assert "hol_block.csv line 5, field required_cores" in capsys.readouterr().err
