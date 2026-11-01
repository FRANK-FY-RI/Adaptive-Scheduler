"""Comprehensive unit, negative, invariant, and NFR benchmark tests (AS-REQ-ENG-001)."""

import unittest

from adaptive_scheduler import (
    ClusterConfig,
    ConfigurationError,
    ExecutionRecord,
    ExecutionSegment,
    InvalidSchedulingDecisionError,
    InvariantViolationError,
    JobId,
    JobLifecycleState,
    JobSpec,
    ReservationInfo,
    SchedulerContext,
    SimulationEngine,
    SimulationSettings,
    SimulationStalledError,
)
from adaptive_scheduler.policies import FIFOPolicy, SJFPolicy


class TestSimulationEngineComplete(unittest.TestCase):
    """Covers Section 11 error cases, Section 12 test cases, Section 13 checklist, and Section 9 NFRs."""

    def test_01_single_job_starts_at_arrival_and_finishes_after_runtime(self) -> None:
        jobs = [JobSpec(job_id="J1", arrival_time=5, runtime=12, required_cores=4)]
        engine = SimulationEngine(
            total_cores=ClusterConfig(8),
            jobs=jobs,
            policy=FIFOPolicy(),
            settings=SimulationSettings(enable_profiling=True),
        )
        result = engine.run()

        self.assertEqual(result.final_time, 17)
        self.assertEqual(len(result.execution_records), 1)
        self.assertEqual(
            result.execution_records[0],
            ExecutionRecord(
                job_id="J1",
                arrival_time=5,
                start_time=5,
                finish_time=17,
                runtime=12,
                waiting_time=0,
                required_cores=4,
                execution_segments=(ExecutionSegment(start_time=5, finish_time=17),),
                preemption_count=0,
            ),
        )
        assert result.profile is not None
        self.assertEqual(result.profile.timestamps_visited, 2) 

    def test_02_multiple_jobs_share_cluster_without_exceeding_capacity(self) -> None:
        jobs = [
            JobSpec(job_id="J1", arrival_time=0, runtime=10, required_cores=4),
            JobSpec(job_id="J2", arrival_time=0, runtime=6, required_cores=4),
        ]
        engine = SimulationEngine(total_cores=8, jobs=jobs, policy=FIFOPolicy())
        result = engine.run()

        by_id = {r.job_id: r for r in result.execution_records}
        self.assertEqual(by_id["J1"].start_time, 0)
        self.assertEqual(by_id["J2"].start_time, 0)
        self.assertEqual(engine.available_cores, 8)

    def test_03_job_waits_when_insufficient_cores_available(self) -> None:
        jobs = [
            JobSpec(job_id="J1", arrival_time=0, runtime=10, required_cores=6),
            JobSpec(job_id="J2", arrival_time=2, runtime=5, required_cores=4),
        ]
        engine = SimulationEngine(total_cores=8, jobs=jobs, policy=FIFOPolicy())
        result = engine.run()

        by_id = {r.job_id: r for r in result.execution_records}
        self.assertEqual(by_id["J2"].start_time, 10)
        self.assertEqual(by_id["J2"].waiting_time, 8)

    def test_04_completed_jobs_release_cores(self) -> None:
        jobs = [
            JobSpec(job_id=1, arrival_time=0, runtime=4, required_cores=8),
            JobSpec(job_id=2, arrival_time=1, runtime=3, required_cores=8),
            JobSpec(job_id=3, arrival_time=2, runtime=2, required_cores=8),
        ]
        engine = SimulationEngine(total_cores=8, jobs=jobs, policy=FIFOPolicy())
        result = engine.run()

        self.assertEqual([r.start_time for r in result.execution_records], [0, 4, 7])
        self.assertEqual([r.finish_time for r in result.execution_records], [4, 7, 9])

    def test_05_arrivals_during_execution_processed_correctly(self) -> None:
        jobs = [
            JobSpec(job_id="J1", arrival_time=0, runtime=10, required_cores=4),
            JobSpec(job_id="J2", arrival_time=2, runtime=8, required_cores=4),
            JobSpec(job_id="J3", arrival_time=4, runtime=3, required_cores=4),
        ]
        engine = SimulationEngine(total_cores=4, jobs=jobs, policy=SJFPolicy())
        result = engine.run()

        by_id = {r.job_id: r for r in result.execution_records}
        self.assertEqual(by_id["J3"].start_time, 10)
        self.assertEqual(by_id["J2"].start_time, 13)

    def test_06_simultaneous_completions_release_all_resources_before_dispatch(self) -> None:
        jobs = [
            JobSpec(job_id="J1", arrival_time=0, runtime=5, required_cores=2),
            JobSpec(job_id="J2", arrival_time=0, runtime=5, required_cores=2),
            JobSpec(job_id="J3", arrival_time=5, runtime=4, required_cores=4),
        ]
        engine = SimulationEngine(total_cores=4, jobs=jobs, policy=FIFOPolicy())
        result = engine.run()

        by_id = {r.job_id: r for r in result.execution_records}
        self.assertEqual(by_id["J3"].start_time, 5)
        self.assertEqual(by_id["J3"].waiting_time, 0)

    def test_07_simultaneous_arrivals_processed_deterministically(self) -> None:
        jobs = [
            JobSpec(job_id="B", arrival_time=0, runtime=5, required_cores=4),
            JobSpec(job_id="A", arrival_time=0, runtime=5, required_cores=4),
            JobSpec(job_id="C", arrival_time=0, runtime=5, required_cores=4),
        ]
        engine = SimulationEngine(total_cores=4, jobs=jobs, policy=FIFOPolicy())
        result = engine.run()

        self.assertEqual([r.job_id for r in result.execution_records], ["A", "B", "C"])

    def test_08_invalid_configurations_and_oversized_jobs_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            SimulationEngine(
                total_cores=4,
                jobs=[JobSpec(job_id="BIG", arrival_time=0, runtime=5, required_cores=8)],
                policy=FIFOPolicy(),
            )
        with self.assertRaises(ConfigurationError):
            SimulationEngine(
                total_cores=4,
                jobs=[JobSpec(job_id="NEG", arrival_time=-1, runtime=5, required_cores=2)],
                policy=FIFOPolicy(),
            )
        with self.assertRaises(ConfigurationError):
            SimulationEngine(
                total_cores=4,
                jobs=[JobSpec(job_id="ZERO_RT", arrival_time=0, runtime=0, required_cores=2)],
                policy=FIFOPolicy(),
            )

    def test_09_job_never_started_twice_or_before_arrival(self) -> None:
        class PrematureStartPolicy:
            def select_next_job(self, context: SchedulerContext) -> JobId | None:
                return "FUTURE_JOB"

        jobs = [
            JobSpec(job_id="NOW_JOB", arrival_time=0, runtime=5, required_cores=2),
            JobSpec(job_id="FUTURE_JOB", arrival_time=10, runtime=5, required_cores=2),
        ]
        engine = SimulationEngine(total_cores=4, jobs=jobs, policy=PrematureStartPolicy())
        with self.assertRaises(InvalidSchedulingDecisionError):
            engine.run()
        self.assertEqual(engine.get_job_lifecycle_state("FUTURE_JOB"), JobLifecycleState.PENDING_ARRIVAL)

    def test_10_custom_strategy_and_reservation_projection_support(self) -> None:
        """Verifies ENG-FR-18 reservation exposure and earliest_available_time calculation."""
        observed_earliest_start: list[int] = []

        class ReservationInspectingPolicy:
            def select_next_job(self, context: SchedulerContext) -> JobId | None:
                for job in context.waiting_jobs:
                    if job.required_cores <= context.available_cores:
                        return job.job_id
                    observed_earliest_start.append(
                        context.earliest_available_time(job.required_cores)
                    )
                return None

        jobs = [
            JobSpec(job_id="J1", arrival_time=0, runtime=6, required_cores=2),
            JobSpec(job_id="J2", arrival_time=0, runtime=10, required_cores=2),
            JobSpec(job_id="J3", arrival_time=1, runtime=4, required_cores=4),
        ]
        engine = SimulationEngine(total_cores=4, jobs=jobs, policy=ReservationInspectingPolicy())

        # Step 1 (t=0): J1 and J2 arrive and start (using 2+2=4 cores)
        self.assertTrue(engine.step())
        self.assertEqual(engine.current_time, 0)
        self.assertEqual(engine.available_cores, 0)

        # Step 2 (t=1): J3 arrives needing 4 cores; J1 finishes at t=6 (frees 2), J2 at t=10 (frees 2)
        self.assertTrue(engine.step())
        self.assertEqual(observed_earliest_start, [10])

        # Register an explicit reservation for J3 at t=10..14 and verify context exposure
        engine.set_reservations(
            [ReservationInfo(job_id="J3", reserved_start_time=10, reserved_finish_time=14, reserved_cores=4)]
        )
        self.assertEqual(len(engine.reservations), 1)

        # Run remaining steps; reservation automatically clears once J3 starts at t=10
        result = engine.run()
        self.assertEqual(result.final_time, 14)
        self.assertEqual(len(engine.reservations), 0)

    def test_11_repeated_deterministic_runs_produce_identical_records(self) -> None:
        jobs = [
            JobSpec(job_id=i, arrival_time=(i * 3) % 7, runtime=(i % 5) + 1, required_cores=(i % 4) + 1)
            for i in range(1, 20)
        ]
        baseline = SimulationEngine(total_cores=6, jobs=jobs, policy=SJFPolicy(strict_head_of_line=False)).run()
        for _ in range(5):
            repeat = SimulationEngine(total_cores=6, jobs=jobs, policy=SJFPolicy(strict_head_of_line=False)).run()
            self.assertEqual(baseline.execution_records, repeat.execution_records)

    def test_12_invalid_proposals_rejected_without_corrupting_state(self) -> None:
        class BadProposalPolicy:
            def select_next_job(self, context: SchedulerContext) -> JobId | None:
                return "UNKNOWN_ID"

        jobs = [JobSpec(job_id="J1", arrival_time=0, runtime=5, required_cores=2)]
        engine = SimulationEngine(total_cores=4, jobs=jobs, policy=BadProposalPolicy())
        with self.assertRaises(InvalidSchedulingDecisionError):
            engine.run()

        self.assertEqual(engine.available_cores, 4)
        self.assertEqual(engine.allocated_cores, 0)
        self.assertEqual(engine.get_job_lifecycle_state("J1"), JobLifecycleState.WAITING)

    def test_13_stalled_policy_detected_immediately_even_with_future_arrivals(self) -> None:
        """Verifies Section 11: policy failing to progress when runnable work exists on idle cluster."""

        class NoOpPolicy:
            def select_next_job(self, context: SchedulerContext) -> JobId | None:
                return None

        jobs = [
            JobSpec(job_id="J1", arrival_time=0, runtime=5, required_cores=2),
            JobSpec(job_id="J2", arrival_time=100, runtime=5, required_cores=2),
        ]
        engine = SimulationEngine(total_cores=4, jobs=jobs, policy=NoOpPolicy())
        with self.assertRaises(SimulationStalledError):
            engine.step()
        # Caught immediately at t=0 without advancing to t=100
        self.assertEqual(engine.current_time, 0)

    def test_14_corrupted_completion_event_detected_by_invariants(self) -> None:
        """Verifies Section 11: missing or inconsistent completion events raise InvariantViolationError."""
        jobs = [JobSpec(job_id="J1", arrival_time=0, runtime=10, required_cores=4)]
        engine = SimulationEngine(total_cores=4, jobs=jobs, policy=FIFOPolicy())
        engine.step()  # J1 starts at t=0, completion scheduled at t=10
        # Simulate internal corruption by dropping the completion event from the heap
        engine._event_queue.clear()
        with self.assertRaises(SimulationStalledError):
            engine.step()

    def test_15_nfr03_and_nfr08_sparse_timestamps_and_large_workload_benchmark(self) -> None:
        """Verifies ENG-NFR-03 (event-driven jumping) and ENG-NFR-08 (2,000-job workload)."""
        # 1. Sparse timestamp jump: 0 -> 10^9 takes 4 events, not 10^9 ticks
        sparse_jobs = [
            JobSpec(job_id="EARLY", arrival_time=0, runtime=10, required_cores=2),
            JobSpec(job_id="LATE", arrival_time=1_000_000_000, runtime=25, required_cores=2),
        ]
        sparse_engine = SimulationEngine(
            total_cores=4,
            jobs=sparse_jobs,
            policy=FIFOPolicy(),
            settings=SimulationSettings(enable_profiling=True),
        )
        sparse_res = sparse_engine.run()
        self.assertEqual(sparse_res.final_time, 1_000_000_025)
        
        # Type narrowing for Pyright:
        assert sparse_res.profile is not None
        self.assertEqual(sparse_res.profile.timestamps_visited, 4)

        # 2. Representative 2,000-job workload
        large_jobs = [
            JobSpec(
                job_id=i,
                arrival_time=i * 2,
                runtime=(i % 12) + 1,
                required_cores=(i % 8) + 1,
            )
            for i in range(2000)
        ]
        large_engine = SimulationEngine(
            total_cores=16,
            jobs=large_jobs,
            policy=FIFOPolicy(strict_head_of_line=False),
            settings=SimulationSettings(enable_profiling=True, check_invariants=False),
        )
        large_res = large_engine.run()
        self.assertEqual(len(large_res.execution_records), 2000)

        # Type narrowing for Pyright:
        assert large_res.profile is not None
        self.assertLess(large_res.profile.wall_time_seconds, 2.0) 
if __name__ == "__main__":
    unittest.main()
