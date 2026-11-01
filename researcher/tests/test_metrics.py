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
