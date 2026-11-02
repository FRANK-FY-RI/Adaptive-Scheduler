"""Parameter search for adaptive_multifactor: objective arithmetic, search space, end to end."""
import math

import numpy as np
import pytest

from adaptivesched.cli import main
from adaptivesched.experiments.export import read_json
from adaptivesched.experiments.tune import MAX_AGE, XF, objective, pareto, perturb, sample, tune
from adaptive_scheduler.policies import get_policy


def test_objective_hand_computed():
    """Two windows. bsld ratios 2/4 = .5 and 3/3 = 1; max-wait ratios 100/50 = 2 and 10/10 = 1.
    J = (ln .5 + ln 1)/2 + (ln 2 + ln 1)/2 = (-.6931)/2 + (.6931)/2 = 0:
    halving the slowdown on one window is paid for by doubling the max wait there."""
    cand = [{"bsld": 2, "max_wait": 100}, {"bsld": 3, "max_wait": 10}]
    base = [{"bsld": 4, "max_wait": 50}, {"bsld": 3, "max_wait": 10}]
    assert objective(cand, base) == pytest.approx(0.0)
    assert objective(base, base) == 0.0
    assert objective([{"bsld": 1, "max_wait": 0}], [{"bsld": 1, "max_wait": 0}]) == 0.0  # max(., 1) guard


def test_pareto_keeps_only_non_dominated():
    rows = [{"bsld_ratio": 1, "max_wait_ratio": 3}, {"bsld_ratio": 2, "max_wait_ratio": 1},
            {"bsld_ratio": 2, "max_wait_ratio": 2}, {"bsld_ratio": 3, "max_wait_ratio": 1}]
    assert pareto(rows) == rows[:2]


def test_samples_and_neighbours_stay_valid():
    rng = np.random.default_rng(1)
    for _ in range(200):
        p = sample(rng)
        q = perturb(p, rng, 0.5)
        for c in (p, q):
            assert math.isclose(c["age_weight"] + c["short_weight"] + c["size_weight"], 1)
            assert MAX_AGE[0] <= c["max_age"] <= MAX_AGE[1] and 0 <= c["adaptation_gain"] <= 1
            assert math.isinf(c["reservation_xf"]) or XF[0] <= c["reservation_xf"] <= XF[1]
            assert 0 <= c["preempt_margin"] <= 0.5
            get_policy("adaptive_multifactor", **c)  # the policy accepts every point of the space


def test_tune_end_to_end_is_deterministic(tmp_path):
    """Two tiny windows, 3 random candidates + 1 reference, refinement 2x2 then 1x2: 4 + 4 + 2 = 10 rows."""
    windows = []
    for i, jobs in enumerate(["1,0,50,4\n2,1,5,1\n3,2,5,1\n4,3,40,2", "1,0,30,2\n2,0,30,2\n3,5,2,4\n4,6,9,1"]):
        p = tmp_path / f"w{i}.csv"
        p.write_text(f"# cluster_cores: 4\njob_id,arrival_time,runtime,required_cores\n{jobs}\n")
        windows.append(str(p))
    ref = {"age_weight": .4, "short_weight": .4, "size_weight": .2, "max_age": 500.0, "adaptation_gain": .5,
           "reservation_xf": 2.0, "preemptive": False, "preempt_margin": .1}
    a = tune(windows, tmp_path / "a", trials=3, refine_top=2, refine_each=2, seed=5, extra={"defaults": ref})
    b = tune(windows, tmp_path / "b", trials=3, refine_top=2, refine_each=2, seed=5, extra={"defaults": ref})
    assert a["evaluated"] == 10 and a["best"] == b["best"]
    assert (tmp_path / "a" / "candidates.csv").read_text() == (tmp_path / "b" / "candidates.csv").read_text()
    assert a["references"][0]["stage"] == "reference:defaults"
    assert a["best"]["J"] == min(r["J"] for r in [*a["pareto_bsld_vs_max_wait"], a["best"]])
    assert not a["best_non_preemptive"]["preemptive"]
    assert read_json(tmp_path / "a" / "result.json")["seed"] == 5


def test_tune_without_any_non_preemptive_candidate(tmp_path, monkeypatch):
    """Regression (HPC job 28220): a tiny search can sample only preemptive candidates; the result
    then reports best_non_preemptive = None instead of crashing."""
    import adaptivesched.experiments.tune as t

    orig = t.sample
    monkeypatch.setattr(t, "sample", lambda rng: {**orig(rng), "preemptive": True})
    monkeypatch.setattr(t, "perturb", lambda p, rng, scale: dict(p))
    p = tmp_path / "w.csv"
    p.write_text("# cluster_cores: 2\njob_id,arrival_time,runtime,required_cores\n1,0,5,1\n2,1,5,2\n")
    r = tune([str(p)], tmp_path / "o", trials=2, refine_top=1, refine_each=1)
    assert r["best_non_preemptive"] is None and r["best_preemptive"]["preemptive"]


def test_cli_tune_rejects_empty_glob(capsys):
    assert main(["tune", "--windows", "no/such/*.csv"]) == 1
    assert "matches no file" in capsys.readouterr().err


def test_tune_can_fix_preemption_off(tmp_path):
    p = tmp_path / "w.csv"
    p.write_text("# cluster_cores: 2\njob_id,arrival_time,runtime,required_cores\n1,0,5,1\n2,1,5,2\n3,2,1,1\n")
    r = tune([str(p)], tmp_path / "o", trials=6, refine_top=2, refine_each=3, seed=3, preemptive=False)
    rows = (tmp_path / "o" / "candidates.csv").read_text().splitlines()[1:]
    assert r["preemptive"] is False and r["best_preemptive"] is None
    assert len(rows) == 6 + 6 + 3 and all(",False," in row for row in rows)
