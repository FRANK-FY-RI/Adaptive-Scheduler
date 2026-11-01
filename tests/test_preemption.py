"""Tests for engine-level preemption and the built-in SRTF strategy."""

import unittest

from adaptive_scheduler import (
    InvalidSchedulingDecisionError,
    JobLifecycleState,
    JobSpec,
    SchedulerContext,
    SimulationEngine,
)
from adaptive_scheduler.policies import FIFOPolicy, SRTFPolicy


class TestPreemptiveScheduling(unittest.TestCase):
    def test_srtf_preempts_and_resumes_with_remaining_runtime(self) -> None:
        jobs = [
            JobSpec("LONG", arrival_time=0, runtime=10, required_cores=2),
            JobSpec("SHORT", arrival_time=3, runtime=2, required_cores=2),
        ]
        result = SimulationEngine(2, jobs, SRTFPolicy()).run()
        records = {record.job_id: record for record in result.execution_records}

        self.assertEqual(result.final_time, 12)
        self.assertEqual(records["SHORT"].start_time, 3)
        self.assertEqual(records["SHORT"].finish_time, 5)
        self.assertEqual(records["LONG"].start_time, 0)
        self.assertEqual(records["LONG"].finish_time, 12)
        self.assertEqual(records["LONG"].runtime, 10)
        self.assertEqual(records["LONG"].waiting_time, 2)
        self.assertEqual(records["LONG"].preemption_count, 1)
        self.assertEqual(
            [(s.start_time, s.finish_time) for s in records["LONG"].execution_segments],
            [(0, 3), (5, 12)],
        )

    def test_existing_policy_remains_non_preemptive(self) -> None:
        jobs = [
            JobSpec("LONG", arrival_time=0, runtime=10, required_cores=2),
            JobSpec("SHORT", arrival_time=3, runtime=2, required_cores=2),
        ]
        result = SimulationEngine(2, jobs, FIFOPolicy()).run()
        records = {record.job_id: record for record in result.execution_records}

        self.assertEqual(records["LONG"].finish_time, 10)
        self.assertEqual(records["LONG"].preemption_count, 0)
        self.assertEqual(records["SHORT"].start_time, 10)
        self.assertEqual(records["SHORT"].waiting_time, 7)

    def test_preempts_multiple_jobs_to_free_a_multi_core_request(self) -> None:
        jobs = [
            JobSpec("A", arrival_time=0, runtime=9, required_cores=2),
            JobSpec("B", arrival_time=0, runtime=8, required_cores=2),
            JobSpec("URGENT", arrival_time=3, runtime=2, required_cores=4),
        ]
        result = SimulationEngine(4, jobs, SRTFPolicy()).run()
        records = {record.job_id: record for record in result.execution_records}

        self.assertEqual(records["URGENT"].start_time, 3)
        self.assertEqual(records["URGENT"].finish_time, 5)
        self.assertEqual(records["A"].preemption_count, 1)
        self.assertEqual(records["B"].preemption_count, 1)
        self.assertEqual(records["A"].finish_time, 11)
        self.assertEqual(records["B"].finish_time, 10)
        self.assertEqual(records["A"].waiting_time, 2)
        self.assertEqual(records["B"].waiting_time, 2)

    def test_job_can_be_preempted_more_than_once(self) -> None:
        jobs = [
            JobSpec("A", arrival_time=0, runtime=10, required_cores=1),
            JobSpec("B", arrival_time=3, runtime=5, required_cores=1),
            JobSpec("C", arrival_time=4, runtime=1, required_cores=1),
            JobSpec("D", arrival_time=6, runtime=1, required_cores=1),
        ]
        result = SimulationEngine(1, jobs, SRTFPolicy()).run()
        records = {record.job_id: record for record in result.execution_records}

        self.assertEqual(records["B"].preemption_count, 2)
        self.assertEqual(records["B"].runtime, 5)
        self.assertEqual(records["B"].finish_time, 10)
        self.assertEqual(records["A"].finish_time, 17)
        self.assertEqual(
            [(s.start_time, s.finish_time) for s in records["B"].execution_segments],
            [(3, 4), (5, 6), (7, 10)],
        )

    def test_invalid_preemption_proposal_is_rejected_before_mutation(self) -> None:
        class InvalidPreemptPolicy:
            def select_jobs_to_preempt(self, context: SchedulerContext) -> tuple[str, ...]:
                return ("NOT_RUNNING",)

            def select_next_job(self, context: SchedulerContext) -> str | None:
                return context.waiting_jobs[0].job_id if context.waiting_jobs else None

        jobs = [JobSpec("A", arrival_time=0, runtime=5, required_cores=1)]
        engine = SimulationEngine(1, jobs, InvalidPreemptPolicy())
        with self.assertRaises(InvalidSchedulingDecisionError):
            engine.step()
        self.assertEqual(engine.get_job_lifecycle_state("A"), JobLifecycleState.WAITING)
        self.assertEqual(engine.available_cores, 1)
        self.assertEqual(engine.allocated_cores, 0)


if __name__ == "__main__":
    unittest.main()
