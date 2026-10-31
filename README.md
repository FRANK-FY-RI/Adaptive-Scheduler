# Adaptive Scheduler

A discrete-event cluster simulation testbed built to develop, evaluate, and benchmark adaptive scheduling algorithms.

The simulation engine handles clock progression, resource allocation, and cluster state invariants, allowing researchers to focus entirely on designing and testing scheduling policies.

---

## 1. Quickstart

### Prerequisites
* Python 3.10+ (standard library only)

### Run a Simulation via CLI
Execute a simulation using a workload CSV file and a reference scheduling policy:

```bash
# Run with FIFO (first-fit) on an 8-core cluster
python3 run_simulation.py --csv workloads/sample.csv --cores 8 --policy fifo-fit

# Run with Shortest-Job-First (first-fit) on a 16-core cluster
python3 run_simulation.py --csv workloads/sample.csv --cores 16 --policy sjf-fit
```

---

## 2. Testing Your Own Policy

To test an adaptive scheduling strategy, create a class implementing the `select_next_job` method. The engine supplies an immutable `SchedulerContext` snapshot at each decision point.

```python
from src.engine import SimulationEngine
from src.models import ClusterConfig, JobId, SchedulerContext
from src.workload import load_workload_from_csv


class MyAdaptivePolicy:
    """Example custom policy."""

    def select_next_job(self, context: SchedulerContext) -> JobId | None:
        # 1. Filter waiting jobs that fit into available capacity
        runnable = [
            job for job in context.waiting_jobs
            if job.required_cores <= context.available_cores
        ]
        if not runnable:
            return None  # Yield: wait for the next event

        # 2. Your custom adaptive heuristic/ranking logic here
        runnable.sort(key=lambda j: (j.runtime, j.arrival_time))

        # 3. Return the selected job ID to start
        return runnable[0].job_id


# Run your policy:
jobs = load_workload_from_csv("workloads/sample.csv")
engine = SimulationEngine(
    total_cores=ClusterConfig(8),
    jobs=jobs,
    policy=MyAdaptivePolicy(),
)
result = engine.run()

print(f"Makespan: {result.final_time}")
for rec in result.execution_records:
    print(f"Job {rec.job_id} waited {rec.waiting_time} ticks, finished at {rec.finish_time}")
```

### Context Reference (`SchedulerContext`)
* `context.current_time`: Current simulation timestamp.
* `context.available_cores`: Free CPU cores available to schedule.
* `context.total_cores`: Total cluster CPU capacity.
* `context.waiting_jobs`: Tuple of `JobSpec(job_id, arrival_time, runtime, required_cores)`.
* `context.running_jobs`: Tuple of active jobs with their `start_time` and `expected_finish_time`.

---

## 3. Workload Data Format

Workload files are standard `.csv` files with the following schema:

```csv
job_id,arrival_time,runtime,required_cores
J1,0,10,4
J2,2,6,2
J3,5,15,8
J4,8,3,1
```

* `job_id`: Unique identifier (string or integer).
* `arrival_time`: Integer timestamp ($t \ge 0$).
* `runtime`: Integer duration ($t > 0$).
* `required_cores`: Integer CPU cores ($1 \le \text{cores} \le \text{total\_cores}$).

---

## 4. Running Verification Tests

Run the engine test suite to verify event handling and state invariants:

```bash
python3 -m unittest discover -s tests
```
