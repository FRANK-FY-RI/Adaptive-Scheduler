"""Runs a simulation experiment using CSV workload data."""

import argparse
from pathlib import Path

from adaptive_scheduler.engine import SimulationEngine
from adaptive_scheduler.models import ClusterConfig, SimulationSettings
from adaptive_scheduler.policies import FIFOPolicy, SJFPolicy
from adaptive_scheduler.workload import load_workload_from_csv


def run_experiment(csv_path: str, cores: int, policy_name: str) -> None:
    # 1. Load workload
    jobs = load_workload_from_csv(csv_path)
    print(f"Loaded {len(jobs)} jobs from {csv_path}")

    # 2. Select scheduling policy
    policies = {
        "fifo": FIFOPolicy(strict_head_of_line=True),
        "fifo-fit": FIFOPolicy(strict_head_of_line=False),
        "sjf": SJFPolicy(strict_head_of_line=True),
        "sjf-fit": SJFPolicy(strict_head_of_line=False),
    }
    selected_policy = policies.get(policy_name.lower())
    if not selected_policy:
        raise ValueError(f"Unknown policy '{policy_name}'. Options: {list(policies.keys())}")

    # 3. Configure and execute engine
    config = ClusterConfig(total_cores=cores)
    settings = SimulationSettings(enable_profiling=True, check_invariants=True)
    engine = SimulationEngine(
        total_cores=config,
        jobs=jobs,
        policy=selected_policy,
        settings=settings,
    )

    print(f"Starting simulation on {cores} cores using {policy_name.upper()}...")
    result = engine.run()

    # 4. Process execution results
    total_waiting_time = sum(r.waiting_time for r in result.execution_records)
    avg_waiting_time = total_waiting_time / len(result.execution_records)
    total_turnaround_time = sum(
        r.finish_time - r.arrival_time for r in result.execution_records
    )
    avg_turnaround_time = total_turnaround_time / len(result.execution_records)

    print("\n--- Simulation Complete ---")
    print(f"Makespan (Final Time):   {result.final_time}")
    print(f"Average Waiting Time:    {avg_waiting_time:.2f}")
    print(f"Average Turnaround Time: {avg_turnaround_time:.2f}")

    if result.profile:
        print(f"Total Events Processed:  {result.profile.total_events_processed}")
        print(f"Wall-clock Time:         {result.profile.wall_time_seconds:.4f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AdaptiveSched Simulation Runner")
    parser.add_argument("--csv", type=str, default="workloads/synthetic_workload.csv")
    parser.add_argument("--cores", type=int, default=8)
    parser.add_argument("--policy", type=str, default="fifo-fit")
    args = parser.parse_args()

    run_experiment(args.csv, args.cores, args.policy)
