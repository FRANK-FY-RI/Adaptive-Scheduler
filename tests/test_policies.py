"""Unit and integration tests for scheduling policies (AS-REQ-SCH-001)."""

from dataclasses import FrozenInstanceError
import pytest

from adaptive_scheduler.exceptions import ConfigurationError
from adaptive_scheduler.interfaces import SchedulingPolicy
from adaptive_scheduler.models import JobSpec, RunningJobView, SchedulerContext
from adaptive_scheduler.policies import (
    AdaptivePolicy,
    EASYBackfillPolicy,
    FIFOPolicy,
    SJFPolicy,
    discover_policies,
    get_policy,
    register_policy,
)
from adaptive_scheduler.policies import _CUSTOM_REGISTRY


def make_context(
    waiting: list[JobSpec],
    running: list[RunningJobView] | None = None,
    available_cores: int = 8,
    total_cores: int = 8,
    current_time: int = 0,
) -> SchedulerContext:
    running_tuple = tuple(running or [])
    allocated = total_cores - available_cores
    return SchedulerContext(
        current_time=current_time,
        total_cores=total_cores,
        available_cores=available_cores,
        allocated_cores=allocated,
        waiting_jobs=tuple(waiting),
        running_jobs=running_tuple,
    )


def test_all_policies_satisfy_protocol_and_have_names():
    """SCH-FR-01, SCH-FR-10: All built-in strategies satisfy SchedulingPolicy and expose .name."""
    policies = [FIFOPolicy(), SJFPolicy(), AdaptivePolicy(), EASYBackfillPolicy()]
    names = set()
    for policy in policies:
        assert isinstance(policy, SchedulingPolicy)
        assert isinstance(policy.name, str) and policy.name
        names.add(policy.name)
    assert len(names) == len(policies)


def test_fifo_uses_arrival_order_and_deterministic_tie_break():
    """SCH-FR-07, SCH-NFR-02: FIFO orders by arrival_time, then job_id."""
    j1 = JobSpec(job_id=10, arrival_time=0, runtime=5, required_cores=2)
    j2 = JobSpec(job_id=2, arrival_time=0, runtime=15, required_cores=2)
    j3 = JobSpec(job_id=1, arrival_time=3, runtime=1, required_cores=2)
    ctx = make_context([j3, j1, j2], available_cores=4)

    policy = FIFOPolicy()
    assert policy.select_next_job(ctx) == 2


def test_fifo_head_of_line_blocking_vs_nonblocking():
    """Section 6.1: FIFO strict HoL waits if head job exceeds available cores; non-blocking scans."""
    head = JobSpec(job_id=1, arrival_time=0, runtime=10, required_cores=6)
    small = JobSpec(job_id=2, arrival_time=1, runtime=2, required_cores=2)
    ctx = make_context([head, small], available_cores=4)

    assert FIFOPolicy(strict_head_of_line=True).select_next_job(ctx) is None
    assert FIFOPolicy(strict_head_of_line=False).select_next_job(ctx) == 2


def test_sjf_prefers_shortest_runtime_and_tie_breaks():
    """SCH-FR-08, Section 6.2: SJF selects shortest runtime, breaking ties by arrival_time and job_id."""
    j1 = JobSpec(job_id=5, arrival_time=2, runtime=4, required_cores=2)
    j2 = JobSpec(job_id=3, arrival_time=1, runtime=4, required_cores=2)
    j3 = JobSpec(job_id=1, arrival_time=0, runtime=10, required_cores=2)
    ctx = make_context([j1, j2, j3], available_cores=4)

    assert SJFPolicy().select_next_job(ctx) == 3


def test_sjf_blocking_vs_nonblocking_when_shortest_exceeds_available_cores():
    """Section 6.2: SJF strict_head_of_line=True waits for shortest job; False picks shortest runnable."""
    shortest_huge = JobSpec(job_id=1, arrival_time=0, runtime=2, required_cores=8)
    longer_small = JobSpec(job_id=2, arrival_time=0, runtime=5, required_cores=2)
    ctx = make_context([shortest_huge, longer_small], available_cores=4)

    assert SJFPolicy(strict_head_of_line=True).select_next_job(ctx) is None
    assert SJFPolicy(strict_head_of_line=False).select_next_job(ctx) == 2


def test_easy_backfilling_starts_short_job_without_delaying_head_reservation():
    """SCH-FR-12: EASY backfilling allows short jobs to run before shadow_time but blocks delaying jobs."""
    running_job = RunningJobView(
        job=JobSpec(job_id=100, arrival_time=0, runtime=10, required_cores=6),
        start_time=0,
        expected_finish_time=10,
    )
    # Head job needs 8 cores -> shadow_time is t=10 when running_job finishes
    head = JobSpec(job_id=1, arrival_time=1, runtime=20, required_cores=8)
    # Delaying candidate needs 2 cores for runtime 15 (finishes at t=17 > shadow_time=10)
    delaying = JobSpec(job_id=2, arrival_time=2, runtime=15, required_cores=2)
    # Safe backfill candidate needs 2 cores for runtime 5 (finishes at t=7 <= shadow_time=10)
    safe_backfill = JobSpec(job_id=3, arrival_time=3, runtime=5, required_cores=2)

    ctx = make_context(
        waiting=[head, delaying, safe_backfill],
        running=[running_job],
        available_cores=2,
        total_cores=8,
        current_time=2,
    )
    policy = EASYBackfillPolicy()
    assert policy.select_next_job(ctx) == 3


def test_adaptive_policy_shifts_weights_and_prevents_starvation():
    """SCH-FR-13, Section 6.3: Adaptive policy increases wait weight under starvation pressure."""
    starving_long = JobSpec(job_id=1, arrival_time=0, runtime=12, required_cores=4)
    fresh_short = JobSpec(job_id=2, arrival_time=99, runtime=4, required_cores=2)

    # At t=2 (no starvation yet), fresh short job is preferred over long job
    early_ctx = make_context(
        [
            JobSpec(job_id=1, arrival_time=0, runtime=12, required_cores=4),
            JobSpec(job_id=2, arrival_time=2, runtime=4, required_cores=2),
        ],
        available_cores=4,
        current_time=2,
    )
    # At t=100 (job 1 has waited 100 units > mean runtime), adaptive policy prioritizes job 1
    starving_ctx = make_context([starving_long, fresh_short], available_cores=4, current_time=100)

    policy = AdaptivePolicy()
    w_wait_early, _, _ = policy.compute_adaptive_weights(early_ctx)
    w_wait_late, _, _ = policy.compute_adaptive_weights(starving_ctx)

    assert w_wait_late > w_wait_early
    assert policy.select_next_job(early_ctx) == 2
    assert policy.select_next_job(starving_ctx) == 1


def test_context_immutability_prevents_state_mutation():
    """SCH-FR-05, SCH-FR-06, SCH-NFR-04: Policies cannot mutate context or JobSpec records."""
    job = JobSpec(job_id=1, arrival_time=0, runtime=5, required_cores=2)
    ctx = make_context([job], available_cores=4)

    with pytest.raises(FrozenInstanceError):
        job.runtime = 1  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        ctx.available_cores = 8  # type: ignore[misc]


def test_policy_registration_and_discovery():
    """UC-S04, SCH-FR-09, Section 9: Custom policies can be registered; duplicates and unknowns error."""
    class CustomMaxCoresPolicy:
        def select_next_job(self, context: SchedulerContext):
            fit = [j for j in context.waiting_jobs if j.required_cores <= context.available_cores]
            return max(fit, key=lambda j: j.required_cores).job_id if fit else None

    _CUSTOM_REGISTRY.pop("custom_max_cores", None)
    register_policy("custom_max_cores", CustomMaxCoresPolicy)
    try:
        inst = get_policy("custom_max_cores")
        assert isinstance(inst, CustomMaxCoresPolicy)

        with pytest.raises(ValueError, match="Duplicate policy registration"):
            register_policy("custom_max_cores", CustomMaxCoresPolicy)

        with pytest.raises(ValueError, match="Unknown policy"):
            get_policy("non_existent_strategy_xyz")
    finally:
        _CUSTOM_REGISTRY.pop("custom_max_cores", None)


def test_policy_parameter_validation():
    """SCH-FR-11: Invalid policy parameters raise ConfigurationError."""
    with pytest.raises(ConfigurationError):
        FIFOPolicy(strict_head_of_line="yes")  # type: ignore[arg-type]

    with pytest.raises(ConfigurationError):
        AdaptivePolicy(base_wait_weight=-0.5)
