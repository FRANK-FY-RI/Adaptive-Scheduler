"""Hand-computed metric tests. The arithmetic is in each docstring, done before the code ran."""
import pytest

from adaptivesched.experiments.adapter import JobRecord
from adaptivesched.metrics import definitions as m


def rec(job_id, arrival, start, runtime, cores):
    return JobRecord(job_id, arrival, start, start + runtime, runtime, start - arrival, cores)


# 4 CPU cores.  (id, arrival, start, runtime, cores) -> finish
#   J1 (1, 0, 0, 4, 2) -> 4      J2 (2, 1, 4, 2, 4) -> 6      J3 (3, 2, 6, 1, 1) -> 7
THREE = [rec(1, 0, 0, 4, 2), rec(2, 1, 4, 2, 4), rec(3, 2, 6, 1, 1)]


def test_waiting():
    """waits = 0-0, 4-1, 6-2 = 0, 3, 4.  mean = 7/3 = 2.3333.  max = 4."""
    assert m.average_waiting_time(THREE) == pytest.approx(7 / 3)
    assert m.max_waiting_time(THREE) == 4


def test_turnaround():
    """turnaround = 4-0, 6-1, 7-2 = 4, 5, 5.  mean = 14/3 = 4.6667."""
    assert m.average_turnaround_time(THREE) == pytest.approx(14 / 3)


def test_makespan():
    """max finish 7 - min arrival 0 = 7."""
    assert m.makespan(THREE) == 7


def test_utilization():
    """busy core-time = 2*4 + 4*2 + 1*1 = 8 + 8 + 1 = 17.  capacity = 4 cores * 7 = 28.
    100 * 17 / 28 = 60.714285..."""
    assert m.cpu_utilization_pct(THREE, 4) == pytest.approx(100 * 17 / 28)


def test_utilization_exactly_100():
    """2 CPU cores; two 1-core jobs, both [0,5).  busy = 1*5 + 1*5 = 10; capacity = 2*5 = 10 -> 100."""
    assert m.cpu_utilization_pct([rec(1, 0, 0, 5, 1), rec(2, 0, 0, 5, 1)], 2) == 100


def test_bounded_slowdown_three_jobs():
    """tau = 10.  J1 (0+4)/max(4,10) = 0.4 -> 1.  J2 (3+2)/10 = 0.5 -> 1.  J3 (4+1)/10 = 0.5 -> 1.
    mean = 1.0 (every job short and barely delayed: the floor of 1 applies)."""
    assert m.bounded_slowdown(THREE) == 1.0


def test_bounded_slowdown_bound_bites():
    """1-unit job waiting 29: (29+1)/max(1,10) = 3.0  (unbounded it would be 30/1 = 30).
    20-unit job waiting 10:    (10+20)/max(20,10) = 1.5.
    mean = (3.0 + 1.5) / 2 = 2.25."""
    recs = [rec(1, 0, 29, 1, 1), rec(2, 0, 10, 20, 1)]
    assert m.bounded_slowdown(recs) == pytest.approx(2.25)
    assert m.TAU == 10


def test_empty_run_rejected():
    with pytest.raises(ValueError, match="no job records"):
        m.average_waiting_time([])
    with pytest.raises(ValueError, match="no job records"):
        m.fairness_index([])


def test_throughput_completed_fairness_on_three():
    """THREE: 3 completed jobs, makespan 7 -> throughput 3/7 = .428571.
    Slowdowns all 1 (test above) -> Jain (3)^2 / (3 * 3) = 1.0. No preemptions."""
    assert m.completed_jobs(THREE) == 3
    assert m.throughput(THREE) == pytest.approx(3 / 7)
    assert m.fairness_index(THREE) == 1.0
    assert m.total_preemptions(THREE) == 0


def test_fairness_one_job_takes_the_slowdown():
    """Slowdowns 1 and 3 (the bound-bites case gives 3.0 and 1.5; use 1-unit job waiting 29 -> 3,
    and a 20-unit job waiting 0 -> 1): Jain = (1+3)^2 / (2 * (1 + 9)) = 16/20 = .8."""
    recs = [rec(1, 0, 29, 1, 1), rec(2, 0, 0, 20, 1)]
    assert m.fairness_index(recs) == pytest.approx(0.8)


# 2 CPU cores, the preemption case from the team's tests/test_adaptive_multifactor.py:
#   L arrival 0, runtime 100, 2 cores, ran [0,10) and [11,101) (preempted once), finish 101
#   S arrival 10, runtime 1, 2 cores, ran [10,11)
PREEMPTED = [JobRecord(1, 0, 0, 101, 100, 1, 2, 1, ((0, 10), (11, 101))),
             JobRecord(2, 10, 10, 11, 1, 0, 2, 0, ((10, 11),))]


def test_metrics_with_preemption():
    """waits = 101-0-100 = 1 (not start-arrival = 0: L waited [10,11) while suspended), 11-10-1 = 0
      -> avg .5, max 1.
    turnaround 101, 1 -> 51.  makespan 101 - 0 = 101.
    busy = 2*100 + 2*1 = 202 = capacity 2*101 -> utilization 100.
    throughput 2/101.  slowdown L 101/100 = 1.01, S max(1, 1/10) = 1 -> 1.005.
    Jain (2.01)^2 / (2 * (1.0201 + 1)) = 4.0401/4.0402 = .99997525.  preemptions 1."""
    assert m.average_waiting_time(PREEMPTED) == 0.5 and m.max_waiting_time(PREEMPTED) == 1
    assert m.average_turnaround_time(PREEMPTED) == 51
    assert m.makespan(PREEMPTED) == 101 and m.cpu_utilization_pct(PREEMPTED, 2) == 100
    assert m.throughput(PREEMPTED) == pytest.approx(2 / 101)
    assert m.bounded_slowdown(PREEMPTED) == pytest.approx(1.005)
    assert m.fairness_index(PREEMPTED) == pytest.approx(4.0401 / 4.0402)
    assert m.total_preemptions(PREEMPTED) == 1
