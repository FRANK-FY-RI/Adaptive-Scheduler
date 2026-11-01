# Adaptive Scheduler

A discrete-event HPC cluster scheduling simulator for developing,
evaluating, and comparing job-scheduling algorithms.

The engine owns simulation time, job lifecycle transitions, event
processing, CPU-core allocation, completion handling, and invariant
checks. Scheduling policies receive an immutable snapshot of the cluster
state and propose which waiting job should run.

The project includes non-preemptive policies, a preemptive scheduling
extension, backfilling, an adaptive multi-heuristic policy, and support
for researcher-defined policies.

## Features

-   Discrete-event simulation driven by job arrivals and completions.
-   Multi-core cluster resource allocation.
-   Built-in FIFO and Shortest Job First (SJF) policies, with strict and
    fit/non-blocking variants.
-   EASY backfilling policy.
-   Adaptive multi-heuristic policy that increases the influence of
    waiting time under starvation pressure.
-   Optional policy-driven preemption, with remaining-runtime accounting
    and job resumption.
-   Built-in multi-core SRTF-inspired preemptive policy.
-   Custom policy registration and discovery.
-   Load a researcher policy from a standalone Python file.
-   Immutable `SchedulerContext` snapshots and engine invariant checks.
-   Profiling counters and per-job execution records.

## Project structure

The repository uses a `src` layout. The importable package is
`adaptive_scheduler`; `src/` is only the source-code container.

``` text
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
│       ├── policy_loader.py
│       └── policies/
│           ├── __init__.py
│           ├── registry.py
│           ├── fifo.py
│           ├── sjf.py
│           ├── adaptive.py
│           ├── easy_backfill.py
│           └── srtf.py
├── examples/
│   ├── researcher_policy.py
│   └── researcher_preemptive_policy.py
├── tests/
│   ├── test_engine.py
│   ├── test_policies.py
│   ├── test_preemption.py
│   └── test_policy_loader.py
└── workloads/
    └── synthetic_workload.csv
```

The exact set of files may vary as the project evolves.

## 1. Setup

### Requirements

-   Python 3.10 or newer.
-   `venv` and `pip`.
-   The simulator's core implementation uses the Python standard
    library. Tests use `pytest` where specified.

### Create and activate a virtual environment

Run from the repository root:

``` bash
python3 -m venv .venv
```

Activate it:

``` bash
# Bash / Zsh
source .venv/bin/activate

# Fish
source .venv/bin/activate.fish
```

### Install the package

``` bash
python -m pip install --upgrade pip
python -m pip install -e .
```

Install test dependencies if they are not already included in your
development environment:

``` bash
python -m pip install pytest
```

Editable installation makes `adaptive_scheduler` importable while you
work on the source files. You generally do not need to reinstall after
changing Python source code.

## 2. Run a simulation

Run the CLI as a module from the repository root:

``` bash
# FIFO, fit/non-blocking variant
python -m adaptive_scheduler.run_simulation \
    --csv workloads/synthetic_workload.csv \
    --cores 8 \
    --policy fifo-fit

# SJF
python -m adaptive_scheduler.run_simulation \
    --csv workloads/synthetic_workload.csv \
    --cores 8 \
    --policy sjf

# Preemptive SRTF-inspired policy
python -m adaptive_scheduler.run_simulation \
    --csv workloads/synthetic_workload.csv \
    --cores 8 \
    --policy srtf
```

The CLI currently exposes `fifo`, `fifo-fit`, `sjf`, `sjf-fit`, and
`srtf` as built-in `--policy` choices. `AdaptivePolicy` and
`EASYBackfillPolicy` are available through the policy package API; do
not assume they are CLI choices unless the CLI has been extended to
include them.

Use the CLI help for the exact options in your checkout:

``` bash
python -m adaptive_scheduler.run_simulation --help
```

Use `python -m ...` rather than executing
`src/adaptive_scheduler/run_simulation.py` directly. Module execution
preserves the package import context.

## 3. Built-in scheduling policies

Policies implement the `SchedulingPolicy` interface and operate on a
read-only `SchedulerContext`.

  -------------------------------------------------------------------------
  Policy                 Scheduling behavior                    Preemptive?
  ---------------------- --------------------- ----------------------------
  `FIFOPolicy`           Selects by arrival                              No
                         time, with            
                         deterministic job-ID  
                         tie-breaking.         
                         Supports strict       
                         head-of-line blocking 
                         or scanning for a job 
                         that fits.            

  `SJFPolicy`            Selects the job with                            No
                         the shortest          
                         requested runtime,    
                         with deterministic    
                         tie-breaking.         
                         Supports strict or    
                         fit/non-blocking      
                         selection.            

  `AdaptivePolicy`       Uses multiple                No, unless separately
                         scheduling signals                        extended
                         and dynamically       
                         increases the         
                         waiting-time weight   
                         as starvation         
                         pressure grows.       

  `EASYBackfillPolicy`   Allows safe short                               No
                         jobs to backfill      
                         while protecting the  
                         head job's            
                         reservation.          

  `SRTFPolicy`           Multi-core                                     Yes
                         SRTF-inspired policy  
                         that considers        
                         remaining runtime and 
                         can preempt running   
                         jobs to admit a       
                         shorter waiting job.  
  -------------------------------------------------------------------------

### Use policies programmatically

``` python
from adaptive_scheduler.engine import SimulationEngine
from adaptive_scheduler.models import ClusterConfig
from adaptive_scheduler.policies import AdaptivePolicy
from adaptive_scheduler.workload import load_workload_from_csv

jobs = load_workload_from_csv("workloads/synthetic_workload.csv")

engine = SimulationEngine(
    total_cores=ClusterConfig(8),
    jobs=jobs,
    policy=AdaptivePolicy(),
)

result = engine.run()
print(f"Makespan: {result.final_time}")
```

Other policies can be imported from `adaptive_scheduler.policies`:

``` python
from adaptive_scheduler.policies import (
    AdaptivePolicy,
    EASYBackfillPolicy,
    FIFOPolicy,
    SJFPolicy,
    SRTFPolicy,
)
```

## 4. Preemptive scheduling

Preemption is an optional engine capability. A policy that only
implements `select_next_job(context)` remains non-preemptive. A policy
opts into preemption by additionally implementing the optional hook:

``` python
def select_jobs_to_preempt(
    self,
    context: SchedulerContext,
) -> tuple[JobId, ...]:
    """Return IDs of currently running jobs that should be suspended."""
```

At an event timestamp, the engine processes completion and arrival
events, asks the policy whether any running jobs should be preempted,
and then performs dispatch. The engine validates the proposal, releases
the selected jobs' cores, invalidates their pending completion events,
and returns them to the waiting state.

When a suspended job resumes, it runs only for its remaining service
time. Its original runtime is not restarted.

### Current preemption model and limitations

-   **Zero context-switch overhead:** preemption and resumption consume
    no simulated time.
-   **Event-driven decisions:** policies make preemption decisions at
    simulation event timestamps (for example, job arrivals or
    completions), not at arbitrary periodic time slices.
-   **Gang scheduling:** a multi-core job is suspended as a whole and
    releases all cores allocated to it.
-   **No checkpoint cost or migration model:** checkpointing,
    restoration, migration, and preemption penalties are not currently
    represented.

### Execution records

A completed job produces one execution record, even if it was preempted
multiple times. The record includes:

-   `runtime`: total CPU service demand.
-   `waiting_time`: time spent waiting before first execution and
    between execution segments.
-   `execution_segments`: the half-open intervals
    `[start_time, finish_time)` during which the job executed.
-   `preemption_count`: number of times the job was suspended.

The execution-segment durations should sum to the job's requested
runtime. Turnaround time is `finish_time - arrival_time`; it includes
both execution and waiting.

## 5. Implement a custom policy

A non-preemptive researcher policy can be defined in a standalone Python
file. It does not need to be added to the simulator package.

For example, save this as `my_policy.py`:

``` python
from adaptive_scheduler import JobId, SchedulerContext


class MyPolicy:
    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        runnable = [
            job for job in context.waiting_jobs
            if job.required_cores <= context.available_cores
        ]

        if not runnable:
            return None

        return min(
            runnable,
            key=lambda job: (job.runtime, job.arrival_time, str(job.job_id)),
        ).job_id
```

Run it using the CLI:

``` bash
python -m adaptive_scheduler.run_simulation \
    --csv workloads/synthetic_workload.csv \
    --cores 8 \
    --policy-file ./my_policy.py
```

If the file defines exactly one policy class, the loader can infer which
class to instantiate. If it defines multiple policy classes, specify
one:

``` bash
python -m adaptive_scheduler.run_simulation \
    --csv workloads/synthetic_workload.csv \
    --cores 8 \
    --policy-file ./my_policies.py \
    --policy-class MyPolicy
```

Custom policy classes currently use a zero-argument constructor. They
must implement `select_next_job(context)` and return a waiting job ID or
`None`.

### Implement a preemptive custom policy

In addition to `select_next_job`, implement `select_jobs_to_preempt`:

``` python
from adaptive_scheduler import JobId, SchedulerContext


class MyPreemptivePolicy:
    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        # Select a waiting job that fits in currently available capacity.
        runnable = [
            job for job in context.waiting_jobs
            if job.required_cores <= context.available_cores
        ]
        if not runnable:
            return None
        return min(runnable, key=lambda job: job.runtime).job_id

    def select_jobs_to_preempt(
        self,
        context: SchedulerContext,
    ) -> tuple[JobId, ...]:
        # Replace with your preemption criterion.
        return ()
```

The example above demonstrates the interface only; returning an empty
tuple means it does not actually preempt any jobs. A complete policy
should compare waiting jobs against running jobs and return only the
running job IDs it intends to suspend.

Policy files are imported and executed as ordinary Python code with the
permissions of the simulation process. The loader is not a security
sandbox. Only load policy files you trust.

## 6. Policy registration and discovery

Policies can also be registered in-process and instantiated by name.

``` python
from adaptive_scheduler.policies import register_policy, get_policy


class LargestJobFirstPolicy:
    def select_next_job(self, context):
        runnable = [
            job for job in context.waiting_jobs
            if job.required_cores <= context.available_cores
        ]
        if not runnable:
            return None
        return max(runnable, key=lambda job: job.required_cores).job_id


register_policy("largest-job-first", LargestJobFirstPolicy)

policy = get_policy("largest-job-first")
```

Registration also supports decorator usage:

``` python
@register_policy("largest-job-first")
class LargestJobFirstPolicy:
    ...
```

The registry rejects duplicate custom names. `discover_policies()`
returns the built-in and explicitly registered policy classes by their
normalized names. The `_CUSTOM_REGISTRY` symbol is internal and is
exposed only for compatibility with the current policy tests;
application code should use `register_policy`, `discover_policies`, and
`get_policy`.

## 7. Scheduler context

The engine passes policies an immutable `SchedulerContext` snapshot. The
commonly used fields include:

-   `context.current_time`: current simulation timestamp.
-   `context.total_cores`: total cluster CPU capacity.
-   `context.available_cores`: currently free CPU cores.
-   `context.allocated_cores`: currently allocated CPU cores.
-   `context.waiting_jobs`: waiting `JobSpec` values.
-   `context.running_jobs`: running-job views, including start and
    expected finish information.
-   `context.reservations`: active reservation information used by
    reservation-aware policies.

Preemption-aware contexts may additionally expose remaining-runtime
information through running-job views or waiting-job views. Consult the
model definitions in `src/adaptive_scheduler/models.py` for the exact
fields available in the current checkout.

## 8. Workload CSV format

Workload files use this schema:

``` csv
job_id,arrival_time,runtime,required_cores
J1,0,10,4
J2,2,6,2
J3,5,15,8
J4,8,3,1
```

  -----------------------------------------------------------------------
  Column                              Meaning
  ----------------------------------- -----------------------------------
  `job_id`                            Unique job identifier (string or
                                      integer).

  `arrival_time`                      Non-negative integer simulation
                                      timestamp.

  `runtime`                           Positive integer CPU service
                                      duration.

  `required_cores`                    Number of CPU cores required by the
                                      job; at least 1 and no greater than
                                      cluster capacity.
  -----------------------------------------------------------------------

The simulator assumes each job's arrival time, runtime, and core
requirement are known from the workload trace.

## 9. Testing

Run the full test suite from the repository root with the virtual
environment activated:

``` bash
python -m unittest discover -s tests -v
```

Run policy tests with pytest:

``` bash
pytest tests/test_policies.py -v
```

Run individual test modules as needed:

``` bash
python -m unittest tests.test_engine -v
python -m unittest tests.test_preemption -v
python -m unittest tests.test_policy_loader -v
```

If a test module uses pytest fixtures or `pytest.raises`, invoke it with
`pytest`.

## 10. Development conventions

-   Use absolute imports beginning with `adaptive_scheduler`, for
    example `from adaptive_scheduler.models import JobId`.
-   Keep application modules inside `src/adaptive_scheduler/`.
-   Keep tests inside `tests/`.
-   Run commands from the repository root.
-   Run application modules with
    `python -m adaptive_scheduler.module_name`.
-   Install the project in editable mode in each developer's virtual
    environment using `python -m pip install -e .`.
-   Do not write imports such as `from src...`; `src/` is a source
    directory, not part of the package's import name.
-   Keep scheduling decisions inside policy classes; the engine remains
    responsible for state transitions, event management, and resource
    accounting.
