"""Run a simulation experiment using CSV workload data and a built-in or custom policy."""

import argparse
from pathlib import Path

from adaptive_scheduler.engine import SimulationEngine
from adaptive_scheduler.exceptions import ConfigurationError
from adaptive_scheduler.models import ClusterConfig, SimulationSettings
from adaptive_scheduler.policy_loader import load_policy_from_file
from adaptive_scheduler.workload import load_workload_from_csv


_BUILTIN_POLICY_NAMES = ("fifo", "fifo-fit", "sjf", "sjf-fit", "srtf")


def _create_builtin_policy(policy_name: str):
    """Instantiate a built-in policy only when the user selects one."""
    # Keep built-in policy imports out of the custom-policy code path.
    from adaptive_scheduler.policies import FIFOPolicy, SJFPolicy, SRTFPolicy

    factories = {
        "fifo": lambda: FIFOPolicy(strict_head_of_line=True),
        "fifo-fit": lambda: FIFOPolicy(strict_head_of_line=False),
        "sjf": lambda: SJFPolicy(strict_head_of_line=True),
        "sjf-fit": lambda: SJFPolicy(strict_head_of_line=False),
        "srtf": SRTFPolicy,
    }
    return factories[policy_name]()


def run_experiment(
    csv_path: str | Path,
    cores: int,
    policy_name: str | None = None,
    *,
    policy_file: str | Path | None = None,
    policy_class: str | None = None,
) -> None:
    """Load a workload, select a policy, and execute the simulation.

    If ``policy_file`` is provided, the file is dynamically imported and its
    selected policy class is instantiated. Otherwise, a built-in policy is used.
    """
    if policy_file is not None and policy_name is not None:
        raise ConfigurationError("Choose either a built-in --policy or --policy-file, not both.")
    if policy_file is None and policy_class is not None:
        raise ConfigurationError("--policy-class can only be used together with --policy-file.")

    # 1. Load workload
    jobs = load_workload_from_csv(csv_path)
    print(f"Loaded {len(jobs)} jobs from {csv_path}")

    # 2. Select scheduling policy
    if policy_file is not None:
        selected_policy = load_policy_from_file(policy_file, policy_class)
        policy_label = f"{Path(policy_file).name}:{type(selected_policy).__name__}"
    else:
        resolved_policy_name = (policy_name or "fifo-fit").lower()
        if resolved_policy_name not in _BUILTIN_POLICY_NAMES:
            options = ", ".join(_BUILTIN_POLICY_NAMES)
            raise ConfigurationError(
                f"Unknown built-in policy '{resolved_policy_name}'. Available policies: {options}."
            )
        selected_policy = _create_builtin_policy(resolved_policy_name)
        policy_label = resolved_policy_name.upper()

    # 3. Configure and execute engine
    config = ClusterConfig(total_cores=cores)
    settings = SimulationSettings(enable_profiling=True, check_invariants=True)
    engine = SimulationEngine(
        total_cores=config,
        jobs=jobs,
        policy=selected_policy,
        settings=settings,
    )

    print(f"Starting simulation on {cores} cores using {policy_label}...")
    result = engine.run()

    # 4. Process execution results
    completed_count = len(result.execution_records)
    total_waiting_time = sum(record.waiting_time for record in result.execution_records)
    avg_waiting_time = total_waiting_time / completed_count if completed_count else 0.0
    total_turnaround_time = sum(
        record.finish_time - record.arrival_time for record in result.execution_records
    )
    avg_turnaround_time = total_turnaround_time / completed_count if completed_count else 0.0

    print("\n--- Simulation Complete ---")
    print(f"Makespan (Final Time):   {result.final_time}")
    print(f"Average Waiting Time:    {avg_waiting_time:.2f}")
    print(f"Average Turnaround Time: {avg_turnaround_time:.2f}")

    if result.profile:
        print(f"Total Events Processed:  {result.profile.total_events_processed}")
        print(f"Wall-clock Time:         {result.profile.wall_time_seconds:.4f}s")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AdaptiveSched simulation runner",
        epilog=(
            "Custom policy files are executable Python code; only load files you trust. "
            "If a file defines more than one policy class, select one with --policy-class."
        ),
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("workloads/synthetic_workload.csv"),
        help="Path to the workload CSV file.",
    )
    parser.add_argument("--cores", type=int, default=8, help="Number of cluster CPU cores.")

    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--policy",
        choices=_BUILTIN_POLICY_NAMES,
        default=None,
        help="Built-in scheduling policy (default: fifo-fit).",
    )
    selection.add_argument(
        "--policy-file",
        type=Path,
        help="Path to a researcher-defined Python policy file.",
    )
    parser.add_argument(
        "--policy-class",
        help="Class to load from --policy-file; inferred if the file defines exactly one policy class.",
    )
    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    try:
        run_experiment(
            csv_path=args.csv,
            cores=args.cores,
            policy_name=args.policy,
            policy_file=args.policy_file,
            policy_class=args.policy_class,
        )
    except (ConfigurationError, FileNotFoundError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
