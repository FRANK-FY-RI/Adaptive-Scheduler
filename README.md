# Adaptive Scheduler

A discrete-event cluster simulation testbed for developing, evaluating, and benchmarking HPC job scheduling algorithms.

The simulation engine handles clock progression, resource allocation, and cluster-state invariants. Researchers can focus on scheduling strategies and evaluate them against workload traces without modifying the engine.

## Project structure

The project uses the `src` layout. The importable application package is `adaptive_scheduler`; `src/` is only the source-code container.

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
│       ├── policy_loader.py
│       ├── run_simulation.py
│       ├── workload.py
│       └── policies/
│           ├── __init__.py
│           ├── fifo.py
│           └── sjf.py
├── tests/
│   ├── __init__.py
│   ├── test_engine.py
│   └── test_policy_loader.py
├── examples/
│   └── researcher_policy.py
└── workloads/
    └── synthetic_workload.csv
```

## 1. Quickstart

### Prerequisites

- Python 3.10 or newer
- `venv` and `pip`
- No third-party runtime dependencies are currently required by the simulation engine.

### Create and activate a virtual environment

Run these commands from the project root:

```bash
python3 -m venv .venv
```

Activate the environment using the command for your shell:

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

Editable installation makes the `adaptive_scheduler` package importable in the virtual environment while you develop. You do not need to reinstall it after every source-code change.

### Run a simulation with a built-in policy

```bash
python -m adaptive_scheduler.run_simulation \
    --csv workloads/synthetic_workload.csv \
    --cores 8 \
    --policy fifo-fit
```

Available built-in policies:

| CLI value | Behavior |
|---|---|
| `fifo` | FIFO with strict head-of-line scheduling. |
| `fifo-fit` | FIFO while allowing a later waiting job to run if it fits. |
| `sjf` | Shortest Job First with strict head-of-line scheduling. |
| `sjf-fit` | Shortest Job First while allowing a later job to run if it fits. |

The default policy is `fifo-fit`, so `--policy` can be omitted.

Run the application as a module from the project root. Do not execute `run_simulation.py` by its file path; the module invocation ensures it runs in its package context.

To see all CLI options:

```bash
python -m adaptive_scheduler.run_simulation --help
```

## 2. Write and run a researcher-defined policy

A researcher can implement a scheduling strategy in a separate Python file. The file does not need to be placed inside the `adaptive_scheduler` package, and adding a new policy does not require modifying the simulation engine or the built-in policy registry.

### Step 1: Implement the policy interface

Create a file such as `my_policy.py`:

```python
from adaptive_scheduler import JobId, SchedulerContext


class MyPolicy:
    """Choose the shortest job that fits in the available capacity."""

    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        runnable_jobs = [
            job
            for job in context.waiting_jobs
            if job.required_cores <= context.available_cores
        ]

        if not runnable_jobs:
            return None

        selected_job = min(
            runnable_jobs,
            key=lambda job: (job.runtime, job.arrival_time, str(job.job_id)),
        )
        return selected_job.job_id
```

The policy contract is defined by `adaptive_scheduler.interfaces.SchedulingPolicy`.

A custom policy must:

- Provide a callable `select_next_job(context)` method.
- Return the `job_id` of a waiting job that can be started with the currently available cores, or return `None` to defer scheduling.
- Have a zero-argument constructor in the current implementation.

The engine validates each proposed job before starting it. Policies should make decisions using the supplied `SchedulerContext` and must not attempt to mutate engine state.

### Step 2: Run the custom policy

From the project root, with the virtual environment active and the package installed in editable mode:

```bash
python -m adaptive_scheduler.run_simulation \
    --csv workloads/synthetic_workload.csv \
    --cores 8 \
    --policy-file ./my_policy.py
```

When the file contains exactly one policy class defined in that file, the loader selects it automatically.

If the file contains multiple policy classes, choose one with `--policy-class`:

```bash
python -m adaptive_scheduler.run_simulation \
    --csv workloads/synthetic_workload.csv \
    --cores 8 \
    --policy-file ./my_policies.py \
    --policy-class MyPolicy
```

Use either `--policy` (a built-in policy) or `--policy-file` (a researcher policy), not both. `--policy-class` is only valid with `--policy-file`.

An example researcher policy is available at `examples/researcher_policy.py`.

### Step 3: Load a policy programmatically

The loader can also be used without the CLI:

```python
from adaptive_scheduler import ClusterConfig, SimulationEngine
from adaptive_scheduler.policy_loader import load_policy_from_file
from adaptive_scheduler.workload import load_workload_from_csv

jobs = load_workload_from_csv("workloads/synthetic_workload.csv")
policy = load_policy_from_file("./my_policy.py")

engine = SimulationEngine(
    total_cores=ClusterConfig(8),
    jobs=jobs,
    policy=policy,
)

result = engine.run()
print(f"Makespan: {result.final_time}")
```

To choose a class explicitly when the file defines more than one policy:

```python
policy = load_policy_from_file("./my_policies.py", class_name="MyPolicy")
```

### Policy API: `SchedulerContext`

The policy receives an immutable snapshot of the simulation state:

| Attribute | Description |
|---|---|
| `current_time` | Current simulation timestamp. |
| `total_cores` | Total CPU cores in the cluster. |
| `available_cores` | CPU cores currently available for scheduling. |
| `allocated_cores` | CPU cores currently allocated to running jobs. |
| `waiting_jobs` | Tuple of waiting `JobSpec` objects. |
| `running_jobs` | Tuple of read-only running-job views. |
| `reservations` | Tuple of active reservation records. |

Each waiting `JobSpec` provides `job_id`, `arrival_time`, `runtime`, and `required_cores`.

**Security note:** A policy file is executable Python code and runs with the same permissions as the simulation process. The policy loader is an import mechanism, not a sandbox. Only load policy files you trust.

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

The CSV header must contain all four column names shown above.

## 4. Running tests

Run the complete test suite from the project root with the virtual environment active:

```bash
python -m unittest discover -s tests -v
```

Run only the policy-loader tests:

```bash
python -m unittest tests.test_policy_loader -v
```

Run only the engine tests:

```bash
python -m unittest tests.test_engine -v
```

## 5. Development conventions

To keep execution and imports consistent across contributors:

- Use absolute imports beginning with `adaptive_scheduler`, for example `from adaptive_scheduler.models import JobSpec`.
- Keep application modules inside `src/adaptive_scheduler/`.
- Keep built-in scheduling policies inside `src/adaptive_scheduler/policies/`.
- Keep researcher examples in `examples/`; researcher policy files can also live outside the repository.
- Keep tests inside `tests/`.
- Run commands from the repository root.
- Run application modules with `python -m adaptive_scheduler.module_name`.
- Install the project in each developer's virtual environment with `python -m pip install -e .`.
- Do not use `src/` in import statements; it is a source directory, not part of the package's import name.
