"""Tests for AdaptiveMultifactorPolicy (docs/ADAPTIVE_POLICY.md). Every expected number was
computed by hand first; the arithmetic is in each docstring. Defaults: weights (.4, .4, .2),
max_age 500, adaptation_gain .5, reservation_xf 2, preempt_margin .1."""

import math

import pytest

from adaptive_scheduler import (
    ConfigurationError,
    InvalidSchedulingDecisionError,
    JobSpec,
    RunningJobView,
    SchedulerContext,
    SimulationEngine,
)
from adaptive_scheduler.policies import AdaptiveMultifactorPolicy, get_policy, policy_ids


def ctx(waiting, running=(), total=4, t=0):
    running = tuple(running)
    used = sum(r.job.required_cores for r in running)
    return SchedulerContext(current_time=t, total_cores=total, available_cores=total - used,
                            allocated_cores=used, waiting_jobs=tuple(waiting), running_jobs=running)


def run_view(job, start, finish):
    return RunningJobView(job=job, start_time=start, expected_finish_time=finish,
                          remaining_runtime=finish - start)


# ---- utility and heuristics ------------------------------------------------------------

def test_utility_hand_computed():
    """8 CPU cores, t=10. A(arr 0, run 9, cores 2), B(arr 10, run 1, cores 8).
    Age: A 10/500 = .02, B 0. sigma = .01, shift = .5*.01 = .005.
    W = (.4 + .005*.6, .4*.995, .2*.995) = (.403, .398, .199).
    r_max 9: S_A = 1 - ln10/ln10 = 0;  S_B = 1 - ln2/ln10 = .69897.
    N_A = 7/8 = .875;  N_B = 1/8 = .125.
    U_A = .403*.02 + .199*.875 = .00806 + .174125 = .182185
    U_B = .398*.69897 + .199*.125 = .278190 + .024875 = .303065"""
    a, b = JobSpec(1, 0, 9, 2), JobSpec(2, 10, 1, 8)
    u = AdaptiveMultifactorPolicy().utilities(ctx([a, b], total=8, t=10))
    assert u[1] == pytest.approx(0.182185, abs=1e-6)
    assert u[2] == pytest.approx(0.303065, abs=1e-6)


def test_weights_sum_to_one_and_adapt_to_queue_age():
    """Gain 1, every waiting job aged >= max_age -> sigma 1 -> all weight on age (1, 0, 0).
    Gain 0 keeps the base weights. Weights are normalised: (2, 2, 1) -> (.4, .4, .2)."""
    old = [JobSpec(1, 0, 5, 1), JobSpec(2, 0, 5, 1)]
    assert AdaptiveMultifactorPolicy(adaptation_gain=1).compute_weights(ctx(old, t=600)) \
        == pytest.approx((1.0, 0.0, 0.0))
    assert AdaptiveMultifactorPolicy(adaptation_gain=0).compute_weights(ctx(old, t=600)) \
        == pytest.approx((0.4, 0.4, 0.2))
    w = AdaptiveMultifactorPolicy(age_weight=2, short_weight=2, size_weight=1).compute_weights(ctx(old))
    assert w == pytest.approx((0.4, 0.4, 0.2)) and math.isclose(sum(w), 1)


def test_short_job_preferred_when_nobody_has_waited():
    """4 CPU cores, t=0. L(run 100, 1 core), S(run 1, 1 core), both just arrived.
    U_L = .4*0 + .4*0 + .2*1 = .2;  U_S = .4*(1 - ln2/ln101) + .2 = .4*.84981 + .2 = .53992 -> S."""
    jobs = [JobSpec("L", 0, 100, 1), JobSpec("S", 0, 1, 1)]
    assert AdaptiveMultifactorPolicy().select_next_job(ctx(jobs)) == "S"


def test_adaptation_flips_decision_for_long_waiting_job():
    """max_age 2000, t=1000. L(arr 0, run 100) waited 1000 -> A_L = .5; S(arr 1000, run 1) A_S = 0.
    Gain 0: U_L = .4*.5 + .2 = .4;  U_S = .4*.84981 + .2 = .53992 -> S (shortness wins).
    Gain 1: sigma = .25 -> W = (.55, .3, .15). U_L = .55*.5 + .15 = .425;
            U_S = .3*.84981 + .15 = .40494 -> L (the aged queue shifts weight to age)."""
    jobs = [JobSpec("L", 0, 100, 1), JobSpec("S", 1000, 1, 1)]
    c = ctx(jobs, t=1000)
    assert AdaptiveMultifactorPolicy(max_age=2000, adaptation_gain=0).select_next_job(c) == "S"
    assert AdaptiveMultifactorPolicy(max_age=2000, adaptation_gain=1).select_next_job(c) == "L"


def test_size_factor_prefers_narrow_job_and_skips_jobs_that_do_not_fit():
    """4 CPU cores, same arrival and runtime; N(1 core) = 1, W(3 cores) = .5 -> U_N - U_W = .2*.5 = .1.
    With 2 CPU cores free a 3-core top job could not start anyway."""
    narrow, wide = JobSpec(1, 0, 5, 1), JobSpec(2, 0, 5, 3)
    p = AdaptiveMultifactorPolicy()
    u = p.utilities(ctx([wide, narrow]))
    assert u[1] - u[2] == pytest.approx(0.1)
    assert p.select_next_job(ctx([wide, narrow])) == 1


def test_deterministic_tie_break_by_arrival_then_job_id():
    """Identical jobs: equal utility. Earlier arrival wins; then the lower job id (int ids sort
    numerically, 2 before 10). Input order never matters."""
    p = AdaptiveMultifactorPolicy()
    assert p.select_next_job(ctx([JobSpec(10, 0, 5, 1), JobSpec(2, 0, 5, 1)])) == 2
    assert p.select_next_job(ctx([JobSpec(2, 1, 5, 1), JobSpec(10, 0, 5, 1)], t=1)) == 10
    assert p.select_next_job(ctx([JobSpec("b", 0, 5, 1), JobSpec("a", 0, 5, 1)])) == "a"


def test_empty_queue():
    p = AdaptiveMultifactorPolicy(preemptive=True)
    assert p.select_next_job(ctx([])) is None
    assert p.select_jobs_to_preempt(ctx([], [run_view(JobSpec(1, 0, 5, 1), 0, 5)], t=1)) == ()
    assert p.utilities(ctx([])) == {}


# ---- selective reservation -------------------------------------------------------------

def _blocked(w_arrival, extra):
    """4 CPU cores, t=5; R(3 cores) runs [0,10) so 1 core is free and the reserved time is 10.
    W(4 cores, run 2) is the top job (size_weight 0 isolates age and shortness)."""
    r = run_view(JobSpec(9, 0, 10, 3), 0, 10)
    return ctx([JobSpec(1, w_arrival, 2, 4), *extra], [r], t=5)


def test_starving_top_job_holds_a_reservation():
    """W arrived at 0: waited 5, XF = (5+2)/2 = 3.5 >= 2 -> reservation at t=10.
    X(run 10, 1 core) would end at 15 > 10 -> not started.  Y(run 4) ends at 9 <= 10 -> started."""
    p = AdaptiveMultifactorPolicy(size_weight=0)
    x, y = JobSpec(2, 5, 10, 1), JobSpec(3, 5, 4, 1)
    assert p.select_next_job(_blocked(0, [x])) is None
    assert p.select_next_job(_blocked(0, [x, y])) == 3


def test_fresh_top_job_does_not_block_others():
    """W arrived at 4: waited 1, XF = (1+2)/2 = 1.5 < 2 -> no reservation; X starts although it
    ends after 10. reservation_xf 1 always reserves; inf never does."""
    x = JobSpec(2, 5, 10, 1)
    assert AdaptiveMultifactorPolicy(size_weight=0).select_next_job(_blocked(4, [x])) == 2
    assert AdaptiveMultifactorPolicy(size_weight=0, reservation_xf=1).select_next_job(_blocked(4, [x])) is None
    assert AdaptiveMultifactorPolicy(size_weight=0, reservation_xf=math.inf).select_next_job(_blocked(0, [x])) == 2


# ---- preemption ------------------------------------------------------------------------

def _preempt_ctx(b_finish, b_start=0):
    """4 CPU cores, t=10, nothing free. A(1 core, run 100) runs [0,100): remaining 90, waited 0.
    B(3 cores) runs [b_start, b_finish). U(4 cores, run 1) just arrived."""
    a = run_view(JobSpec("A", 0, 100, 1), 0, 100)
    b = run_view(JobSpec("B", 0, b_finish - b_start, 3), b_start, b_finish)
    return ctx([JobSpec("U", 10, 1, 4)], [a, b], t=10)


def test_preemption_needs_enough_lower_utility_victims():
    """B runs [0,12): remaining 2. r_max 90, weights (.4,.4,.2).
    U_U = .4*(1 - ln2/ln91) + .2*1/4 = .338535 + .05 = .388535
    U_A = .4*0 + .2*1 = .2 (gap .19 > .1: victim)
    U_B = .4*(1 - ln3/ln91) + .2*2/4 = .302580 + .1 = .402580 (higher than U: not a victim)
    A frees 1 core, U needs 4 -> preempt nothing."""
    assert AdaptiveMultifactorPolicy(preemptive=True).select_jobs_to_preempt(_preempt_ctx(12)) == ()


def test_preemption_picks_lowest_utility_first():
    """B runs [0,100): remaining 90 -> U_B = 0 + .2*2/4 = .1; U_A = .2. Both gaps > .1.
    Lowest utility first: B (frees 3), then A (frees 4 >= 4) -> ("B", "A").
    Not preemptive, or margin .5 (gap .19 for A), -> nothing."""
    c = _preempt_ctx(100)
    assert AdaptiveMultifactorPolicy(preemptive=True).select_jobs_to_preempt(c) == ("B", "A")
    assert AdaptiveMultifactorPolicy().select_jobs_to_preempt(c) == ()
    assert AdaptiveMultifactorPolicy(preemptive=True, preempt_margin=0.5).select_jobs_to_preempt(c) == ()


def test_job_started_this_instant_is_never_a_victim():
    """B started at t=10 (elapsed 0; the engine forbids preempting it) -> only A is eligible,
    1 core < 4 -> nothing."""
    assert AdaptiveMultifactorPolicy(preemptive=True).select_jobs_to_preempt(_preempt_ctx(100, 10)) == ()


def test_preemptive_simulation_suspends_and_resumes():
    """2 CPU cores. L(arr 0, run 100, 2 cores), S(arr 10, run 1, 2 cores).
    t=10: U_S = .4*(1 - ln2/ln91) + .2*1/2 = .438535; U_L = 0 + .1 = .1 -> gap > .1, L preempted.
    S [10,11); L resumes [11,101): one preemption, waiting 1, finish 101.
    Non-preemptive: S waits until 100."""
    jobs = [JobSpec("L", 0, 100, 2), JobSpec("S", 10, 1, 2)]
    rec = {r.job_id: r for r in SimulationEngine(2, jobs, AdaptiveMultifactorPolicy(preemptive=True)).run()
           .execution_records}
    assert [(s.start_time, s.finish_time) for s in rec["L"].execution_segments] == [(0, 10), (11, 101)]
    assert (rec["L"].preemption_count, rec["L"].waiting_time, rec["L"].finish_time) == (1, 1, 101)
    assert (rec["S"].start_time, rec["S"].finish_time, rec["S"].waiting_time) == (10, 11, 0)
    plain = {r.job_id: r for r in SimulationEngine(2, jobs, AdaptiveMultifactorPolicy()).run().execution_records}
    assert plain["S"].start_time == 100 and plain["L"].preemption_count == 0


def test_resumed_job_is_ranked_by_remaining_runtime_and_accumulated_wait():
    """A context built by the engine after a preemption: L(run 100) has 90 left and waited 1 at t=11.
    waited = 11 - 0 - (100 - 90) = 1, not 11; shortness uses 90, not 100."""
    from adaptive_scheduler import WaitingJobView

    l = JobSpec("L", 0, 100, 2)
    c = SchedulerContext(current_time=11, total_cores=2, available_cores=2, allocated_cores=0,
                         waiting_jobs=(l,), running_jobs=(),
                         waiting_job_views=(WaitingJobView(job=l, remaining_runtime=90),))
    cand = AdaptiveMultifactorPolicy._waiting(c)[0]
    assert (cand.remaining, cand.waited) == (90, 1)


# ---- integration with the engine -------------------------------------------------------

def _workload():
    """40 jobs on 8 CPU cores, mixed widths and lengths; deterministic."""
    return [JobSpec(i, (i * 7) % 60, 1 + (i * 13) % 40, 1 + (i * 5) % 8) for i in range(40)]


@pytest.mark.parametrize("params", [{}, {"preemptive": True}, {"reservation_xf": 1},
                                    {"adaptation_gain": 0}, {"size_weight": 0}])
def test_full_simulation_keeps_engine_invariants_and_is_deterministic(params):
    """check_invariants is on by default: every event batch is checked by the engine."""
    runs = [SimulationEngine(8, _workload(), AdaptiveMultifactorPolicy(**params)).run() for _ in range(2)]
    assert runs[0] == runs[1]
    recs = runs[0].execution_records
    assert len(recs) == 40
    for r in recs:
        assert sum(s.duration for s in r.execution_segments) == r.runtime
        assert r.waiting_time == r.finish_time - r.arrival_time - r.runtime
        assert len(r.execution_segments) == r.preemption_count + 1


def test_invalid_proposal_from_a_broken_variant_is_rejected():
    """A subclass that ignores capacity proposes a job that does not fit: the engine refuses it."""
    class Broken(AdaptiveMultifactorPolicy):
        def select_next_job(self, context):
            order = self._ranked(context)
            return order[0].job.job_id if order else None

    jobs = [JobSpec(1, 0, 10, 3), JobSpec(2, 0, 10, 3)]
    with pytest.raises(InvalidSchedulingDecisionError, match="requiring 3 cores"):
        SimulationEngine(4, jobs, Broken()).run()


def test_registered_and_selectable():
    assert "adaptive_multifactor" in policy_ids()
    p = get_policy("adaptive_multifactor", preemptive=True, max_age=100)
    assert isinstance(p, AdaptiveMultifactorPolicy) and p.preemptive and p.max_age == 100


@pytest.mark.parametrize("bad", [
    {"age_weight": -1}, {"age_weight": 0, "short_weight": 0, "size_weight": 0}, {"max_age": 0},
    {"max_age": math.inf}, {"adaptation_gain": 1.5}, {"reservation_xf": 0.5}, {"preemptive": "yes"},
    {"preempt_margin": 2}, {"short_weight": True}, {"size_weight": float("nan")},
])
def test_invalid_parameters_rejected(bad):
    with pytest.raises(ConfigurationError):
        AdaptiveMultifactorPolicy(**bad)


def test_team_cli_selects_the_policy(tmp_path, capsys):
    from adaptive_scheduler.run_simulation import run_experiment

    csv = tmp_path / "w.csv"
    csv.write_text("job_id,arrival_time,runtime,required_cores\nJ1,0,100,2\nJ2,10,1,2\n")
    run_experiment(csv, 2, "adaptive-multifactor-preemptive")
    assert "Makespan (Final Time):   101" in capsys.readouterr().out


def test_presets_are_valid_parameter_sets():
    """docs/TUNING.md presets: each builds a policy, and the non-preemptive one is not preemptive."""
    presets = AdaptiveMultifactorPolicy.PRESETS
    assert set(presets) == {"tuned for real HPC logs", "tuned for real HPC logs, preemptive"}
    for name, params in presets.items():
        p = AdaptiveMultifactorPolicy(**params)
        assert p.preemptive is ("preemptive" in name)
    assert math.isinf(presets["tuned for real HPC logs, preemptive"]["reservation_xf"])
