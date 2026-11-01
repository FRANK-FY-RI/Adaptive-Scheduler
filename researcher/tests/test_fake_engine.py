"""Hand-computed FIFO and SJF schedules for the three workloads in tests/workloads/ (SPEC §1.3).

Every schedule below was worked out on paper before the assertion was written.
Record tuples are (job_id, arrival, start, finish, runtime, waiting, cores).
These same expectations are the M5 check that the team engine matches (INTERFACES §5).
"""
from pathlib import Path

import pytest

from adaptivesched.experiments.adapter import FakeEngineAdapter, TeamEngineAdapter
from adaptivesched.workloads.loader import load_csv

WORKLOADS = Path(__file__).parent / "workloads"


def load(name):
    return load_csv(WORKLOADS / name).jobs


def run(name, cores, strategy):
    res = FakeEngineAdapter().run(load(name), cores, strategy, {}, workload_id=name)
    assert res.engine == "fake" and res.strategy == strategy and res.cluster_cores == cores
    for r in res.records:  # UC-R03 invariants
        assert r.waiting_time == r.start_time - r.arrival_time
        assert r.finish_time == r.start_time + r.runtime
    return [tuple(vars(r).values()) for r in res.records]


def test_hol_block_fifo():
    """4 CPU cores. Jobs (id: arrival, runtime, cores): 1:(0,10,2) 2:(1,5,3) 3:(2,2,1) 4:(3,2,1)

    t=0  job 1 arrives, starts (free 4→2), finishes 10.
    t=1  job 2 arrives; head needs 3, free 2 → blocked.
    t=2  job 3 arrives behind job 2; head still blocked → nothing starts (2 cores idle).
    t=3  job 4 arrives; same → nothing starts.
    t=10 job 1 completes (free 4). Job 2 starts (free 1, fin 15); job 3 starts (free 0, fin 12);
         job 4 needs 1, free 0 → waits.
    t=12 job 3 completes (free 1); job 4 starts, fin 14.
    Waits: 0, 9, 8, 9 → avg 26/4 = 6.5, max 9. Last finish 15.
    Head-of-line blocking: jobs 3 and 4 wait 8 and 9 while 2 CPU cores sit idle over [1,10).
    """
    assert run("hol_block.csv", 4, "fifo") == [
        (1, 0, 0, 10, 10, 0, 2),
        (2, 1, 10, 15, 5, 9, 3),
        (3, 2, 10, 12, 2, 8, 1),
        (4, 3, 12, 14, 2, 9, 1),
    ]


def test_hol_block_sjf():
    """Same workload, SJF (wait-behind-head on the shortest job).

    t=0  job 1 starts (free 2), fin 10.
    t=1  job 2 queued (runtime 5); needs 3, free 2 → blocked.
    t=2  job 3 arrives (runtime 2) → queue [3, 2]; head job 3 fits → starts (free 1), fin 4.
         Next head job 2 needs 3 → stop.
    t=3  job 4 arrives (runtime 2) → queue [4, 2]; job 4 fits → starts (free 0), fin 5.
    t=4  job 3 completes (free 1); job 2 blocked.  t=5 job 4 completes (free 2); job 2 blocked.
    t=10 job 1 completes (free 4); job 2 starts, fin 15.
    Waits: 0, 9, 0, 0 → avg 9/4 = 2.25, max 9. Last finish 15 (same as FIFO).
    """
    assert run("hol_block.csv", 4, "sjf") == [
        (1, 0, 0, 10, 10, 0, 2),
        (2, 1, 10, 15, 5, 9, 3),
        (3, 2, 2, 4, 2, 0, 1),
        (4, 3, 3, 5, 2, 0, 1),
    ]


def test_sjf_starve_fifo():
    """1 CPU core. 1:(0,4) 2:(1,20) 3:(2,3) 4:(5,3) 5:(8,3) 6:(11,3)   (arrival, runtime)

    Arrival order on one core: 1 [0,4), 2 [4,24), 3 [24,27), 4 [27,30), 5 [30,33), 6 [33,36).
    Waits: 0, 3, 22, 22, 22, 22 → avg 91/6 ≈ 15.17, max 22. Last finish 36.
    """
    assert run("sjf_starve.csv", 1, "fifo") == [
        (1, 0, 0, 4, 4, 0, 1),
        (2, 1, 4, 24, 20, 3, 1),
        (3, 2, 24, 27, 3, 22, 1),
        (4, 5, 27, 30, 3, 22, 1),
        (5, 8, 30, 33, 3, 22, 1),
        (6, 11, 33, 36, 3, 22, 1),
    ]


def test_sjf_starve_sjf():
    """Same workload, SJF.

    t=0  job 1 starts, fin 4.  t=1 job 2 queued.  t=2 job 3 queued.
    t=4  queue [3(r3), 2(r20)] → job 3 runs [4,7).
    t=5  job 4 arrives. t=7 queue [4, 2] → job 4 runs [7,10).
    t=8  job 5 arrives. t=10 → job 5 runs [10,13).
    t=11 job 6 arrives. t=13 → job 6 runs [13,16).
    t=16 queue [2] → job 2 finally runs [16,36).
    Waits: 0, 15, 2, 2, 2, 2 → avg 23/6 ≈ 3.83, max 15. Last finish 36.
    The long job's wait goes 3 (FIFO) → 15 (SJF): every short arrival overtakes it.
    """
    assert run("sjf_starve.csv", 1, "sjf") == [
        (1, 0, 0, 4, 4, 0, 1),
        (2, 1, 16, 36, 20, 15, 1),
        (3, 2, 4, 7, 3, 2, 1),
        (4, 5, 7, 10, 3, 2, 1),
        (5, 8, 10, 13, 3, 2, 1),
        (6, 11, 13, 16, 3, 2, 1),
    ]


@pytest.mark.parametrize("strategy", ["fifo", "sjf"])
def test_tie_break(strategy):
    """1 CPU core. File order 3, 1, 2. 3:(0,4) 1:(0,4) 2:(1,4)   (arrival, runtime)

    All runtimes equal, so SJF's key (runtime, arrival, job_id) reduces to FIFO's
    (arrival, job_id) — both strategies must give the same schedule.
    t=0  jobs 3 and 1 arrive together → lower job_id first: job 1 runs [0,4). File order ignored.
    t=1  job 2 arrives.
    t=4  queue [3 (arr 0), 2 (arr 1)] → earlier arrival beats lower job_id: job 3 runs [4,8).
    t=8  job 2 runs [8,12).
    Waits: 1→0, 2→7, 3→4.
    """
    assert run("tie_break.csv", 1, strategy) == [
        (1, 0, 0, 4, 4, 0, 1),
        (2, 1, 8, 12, 4, 7, 1),
        (3, 0, 4, 8, 4, 4, 1),
    ]


def test_fake_rejects_bad_input():
    fake = FakeEngineAdapter()
    jobs = load("hol_block.csv")
    with pytest.raises(ValueError, match="unknown strategy 'edf'"):
        fake.run(jobs, 4, "edf", {}, workload_id="x")
    with pytest.raises(ValueError, match="job 2: required_cores=3 does not fit cluster_cores=2"):
        fake.run(jobs, 2, "fifo", {}, workload_id="x")
    with pytest.raises(ValueError, match="takes no parameters"):
        fake.run(jobs, 4, "fifo", {"alpha": 1}, workload_id="x")


@pytest.mark.parametrize("name, cores", [("hol_block.csv", 4), ("sjf_starve.csv", 1), ("tie_break.csv", 1)])
@pytest.mark.parametrize("strategy", ["fifo", "sjf"])
def test_team_engine_matches_hand_computed(name, cores, strategy):
    """M5 check (INTERFACES §5): the team engine reproduces the fake's records, which the
    tests above pin to the hand-computed schedules. A mismatch means one of them is wrong."""
    jobs = load(name)
    team = TeamEngineAdapter().run(jobs, cores, strategy, {}, workload_id=name)
    fake = FakeEngineAdapter().run(jobs, cores, strategy, {}, workload_id=name)
    assert team.records == fake.records
    assert team.engine == "team" and "wait-behind-head" in team.strategy_dispatch_note
    assert team.engine_version.startswith("adaptive-scheduler ")


def test_team_engine_first_fit_param():
    """strict_head_of_line=False on hol_block, FIFO, 4 CPU cores:
    t=0 job 1 starts (free 2). t=1 job 2 needs 3 -> skipped. t=2 job 3 fits -> [2,4) (free 1).
    t=3 job 4 fits -> [3,5) (free 0). t=4,5 jobs 3,4 finish (free 2): job 2 still blocked.
    t=10 job 1 finishes -> job 2 [10,15). Same as SJF here; waits 0, 9, 0, 0."""
    res = TeamEngineAdapter().run(load("hol_block.csv"), 4, "fifo", {"strict_head_of_line": False},
                                  workload_id="x")
    assert [r.start_time for r in res.records] == [0, 10, 2, 3]
    assert "first-fit" in res.strategy_dispatch_note


@pytest.mark.parametrize("strategy", ["easy_backfill", "adaptive"])
def test_team_backfilling_strategies_hand_computed(strategy):
    """hol_block, 4 CPU cores, team defaults (adaptive: base weights .35/.45/.20, gain .5, backfill on).

    easy_backfill: t=0 job 1 [0,10) (free 2). t=1 job 2 needs 3; shadow = 10 (job 1 frees 2),
      extra cores at shadow = 4-0-3 = 1. t=2 job 3: 2+2=4 <= 10 -> [2,4). t=3 job 4: 3+2=5 <= 10
      -> [3,5). t=10 job 2 [10,15).
    adaptive: t=2 waiting 2,3; pressure 0 (waits 1,0 < mean runtime 3.5), idle 2/4 ->
      w = (.35, .45, .2625); wait_scale 3.5, min runtime 2.
      U2 = .35*1/3.5 + .45*2/5 + .2625*3/4 = .1 + .18 + .196875 = .476875
      U3 = 0 + .45*2/2 + .2625*1/4 = .45 + .065625 = .515625 -> job 3 [2,4).
      t=3 waiting 2,4; idle 1/4 -> w_pack .23125; U2 = .2 + .18 + .1734375 = .5534375,
      U4 = .45 + .0578125 = .5078125 -> job 2 top but needs 3 (free 1); shadow 10, extra 1;
      job 4: 3+2=5 <= 10 -> backfills [3,5). t=10 job 2 [10,15).
    Both: waits 0, 9, 0, 0 -> avg 2.25, max 9, makespan 15; job 2 is not delayed by the backfill."""
    res = TeamEngineAdapter().run(load("hol_block.csv"), 4, strategy, {}, workload_id="x")
    assert [tuple(vars(r).values()) for r in res.records] == [
        (1, 0, 0, 10, 10, 0, 2),
        (2, 1, 10, 15, 5, 9, 3),
        (3, 2, 2, 4, 2, 0, 1),
        (4, 3, 3, 5, 2, 0, 1),
    ]
    assert "backfill" in res.strategy_dispatch_note
