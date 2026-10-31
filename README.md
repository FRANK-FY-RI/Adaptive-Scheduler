# Adaptive Scheduler

A discrete-event cluster simulation testbed for developing, evaluating, and benchmarking adaptive scheduling algorithms.

The simulation engine handles clock progression, resource allocation, and cluster-state invariants, allowing researchers and scheduling-algorithm developers to focus on designing and testing scheduling policies.

## Project structure

The project uses a `src` layout. The importable application package is `adaptive_scheduler`; the `src/` directory is only the source-code container.

```text
adaptive_scheduler/
├── pyproject.toml
├── README.md
├── src/
│   └── adaptive_scheduler/
│       ├── __init__.py
│       ├── engine.py
│       ├── exceptions.py
│       ├── interfaces.py
│       ├── models.py
│       ├── workload.py
│       ├── run_simulation.py
│       └── policies/
│           ├── __init__.py
│           ├── fifo.py
│           └── sjf.py
├── tests/
│   ├── __init__.py
│   └── test_engine.py
└── workloads/
    └── synthetic_workload.csv
```

## 1. Quickstart

### Prerequisites

- Python 3.10 or newer
- `venv` and `pip`
- The project currently has no third-party runtime dependencies.

### Create and activate a virtual environment

From the project root:

```bash
python3 -m venv .venv
```

Activate it using the command for your shell:

```bash
# Bash / Zsh
source .venv/bin/activate

# Fish
source .venv/bin/activate.fish
```

### Install the project in editable mode

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

Editable installation makes the `adaptive_scheduler` package importable while you work on the source files. You do not need to reinstall it after every code change.

### Run a simulation

Run the application as a module from the project root:

```bash
python -m adaptive_scheduler.run_simulation \
    --csv workloads/synthetic_workload.csv \
    --policy fifo
```

The module invocation (`python -m ...`) is intentional: it runs the entry point in its package context. Avoid launching the file directly with `python src/adaptive_scheduler/run_simulation.py`.

Use `python -m adaptive_scheduler.run_simulation --help` to see the CLI options supported by the current version.

## 2. Developing a scheduling policy

To implement an adaptive scheduling strategy, create a class that implements the policy interface's `select_next_job` method. The engine supplies an immutable `SchedulerContext` snapshot at each decision point.

For example:

```python
from adaptive_scheduler.models import JobId, SchedulerContext


class MyAdaptivePolicy:
    """Example custom scheduling policy."""

    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        # Select jobs that fit in the currently available capacity.
        runnable = [
            job for job in context.waiting_jobs
            if job.required_cores <= context.available_cores
        ]

        if not runnable:
            return None  # Yield until the next simulation event.

        # Replace this with your scheduling heuristic.
        runnable.sort(key=lambda job: (job.runtime, job.arrival_time))
        return runnable[0].job_id
```

The policy should follow the project's scheduling-policy interface and return either the selected job ID or `None` when it cannot currently select a job.

### Using the engine and workload loader

The package imports use the installed package name, not filesystem-relative paths:

```python
from adaptive_scheduler.engine import SimulationEngine
from adaptive_scheduler.models import ClusterConfig
from adaptive_scheduler.workload import load_workload_from_csv

jobs = load_workload_from_csv("workloads/synthetic_workload.csv")

engine = SimulationEngine(
    total_cores=ClusterConfig(8),
    jobs=jobs,
    policy=MyAdaptivePolicy(),
)

result = engine.run()

print(f"Makespan: {result.final_time}")
for record in result.execution_records:
    print(
        f"Job {record.job_id} waited {record.waiting_time} ticks, "
        f"finished at {record.finish_time}"
    )
```

Adapt the example to the exact policy interface and constructor signatures in the current source.

### `SchedulerContext` reference

The context supplied to a policy includes:

- `context.current_time`: current simulation timestamp.
- `context.available_cores`: free CPU cores available for scheduling.
- `context.total_cores`: total cluster CPU capacity.
- `context.waiting_jobs`: waiting jobs, represented as `JobSpec` values.
- `context.running_jobs`: currently running jobs, including their start and expected finish times.

## 3. Workload CSV format

Workload files are CSV files with the following schema:

```csv
job_id,arrival_time,runtime,required_cores
J1,0,10,4
J2,2,6,2
J3,5,15,8
J4,8,3,1
```

| Column | Meaning |
|---|---|
| `job_id` | Unique job identifier (string or integer). |
| `arrival_time` | Non-negative integer simulation timestamp. |
| `runtime` | Positive integer job duration. |
| `required_cores` | Number of CPU cores required by the job; must be at least 1 and no greater than the cluster capacity. |

## 4. Running tests

Run the test suite from the project root with the virtual environment activated:

```bash
python -m unittest discover -s tests -v
```

Run an individual test module with:

```bash
python -m unittest tests.test_engine -v
```

## 5. Development conventions

To keep imports and execution consistent across the team:

- Use absolute imports beginning with `adaptive_scheduler`, for example `from adaptive_scheduler.models import JobId`.
- Keep application modules inside `src/adaptive_scheduler/`.
- Keep tests inside `tests/`.
- Run commands from the repository root.
- Run application modules with `python -m adaptive_scheduler.module_name`.
- Install the project in editable mode in each developer's virtual environment with `python -m pip install -e .`.
- Do not add `src/` to imports; it is a source directory, not part of the package's import name.
