# AdaptiveSched: experiments, analysis and dashboard

The experiment layer on top of the `adaptive_scheduler` engine (this repository's root). It runs
scheduling policies on the same workload and the same cluster, computes metrics with one shared
definition each, exports reproducible results, draws comparison plots and Gantt charts, and
serves a web dashboard for all of it. The command line remains the reference interface. The
dashboard calls the same code.

## Architecture

```
adaptive_scheduler (repo root, src/)        engine: clock, events, CPU cores, preemption, records
  policies/  fifo sjf easy_backfill srtf     policies: propose decisions through SchedulerContext
             adaptive adaptive_multifactor
researcher/adaptivesched/
  workloads/   synthetic generators, CSV loader, validation
  experiments/ adapter (the only engine import), config, runner, batch, compare, export
  metrics/     definitions.py: every metric, one function each
  analysis/    plots, Gantt, inspect, findings: read result files, never the engine
  api/         HTTP API: validates input, queues batches, serves result files
  web/         dashboard: presentation only
```

| responsibility | lives in | never in |
|---|---|---|
| simulation state, resources, events | engine | policies, runner, API, web |
| scheduling decisions | `policies/` | engine, API, web |
| orchestration, reproducibility metadata | `experiments/` | API (it calls `run_batch`) |
| metric formulas | `metrics/definitions.py` | anywhere else |
| presentation | `analysis/` (files), `web/` (browser) | engine, policies |

## Install

```sh
python -m venv .venv && . .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -e .                                   # the engine package (repo root)
pip install -e "researcher[test]"                  # this package + pytest
```

Requirements: Python ≥ 3.10; numpy, pandas, matplotlib, pyyaml (installed with the package). The
dashboard needs no extra dependency and no network.

## Command line

Run from `researcher/`:

```sh
adaptivesched strategies                       # registered policy ids
adaptivesched workloads                        # synthetic workload conditions
adaptivesched workloads --show synth:heavy:n=300:seed=7 --cluster-cores 16 --head 10
adaptivesched run      --config examples/run_heavy_sjf.yaml
adaptivesched batch    --config examples/batch_study.yaml        # 120 runs, about 2 minutes
adaptivesched compare  --batch results/batch_<id>                # one table per workload and capacity
adaptivesched plot     --batch results/batch_<id>                # all comparison plots
adaptivesched plot     --batch results/batch_<id> --gantt synth:short_heavy:n=300:seed=7 srtf amf_preemptive
adaptivesched inspect  --run results/batch_<id>/runs/<run_id> --job 17
adaptivesched findings --batch results/batch_<id>                # trade-off table + findings skeleton
adaptivesched serve    [--port 8000]                             # dashboard at http://127.0.0.1:8000/

# real production logs (Parallel Workloads Archive; downloads in ../workloads/README.md)
adaptivesched workloads --from-swf ../workloads/pwa/KTH-SP2-1996-2.1-cln.swf.gz --jobs 5000 --out ../workloads/pwa/kth_sp2_5000.csv
adaptivesched batch    --config examples/real/kth_sp2.yaml       # one config per log, at its own CPU count

# parameter search for adaptive_multifactor (../docs/TUNING.md)
adaptivesched tune     --windows "../workloads/pwa/train/*.csv" --trials 160 --out results/tuning
```

`batch` exits 1 if any run failed (after writing everything), so scripts notice. The batch
directory name is a hash of the config and engine, so the same config always writes to the same
place, and every file except `timestamp` fields is byte-identical on rerun.

## Available policies

| id | semantics | parameters (defaults) |
|---|---|---|
| `fifo` | non-preemptive; arrival order | `strict_head_of_line` (true = wait behind a blocked head job) |
| `sjf` | non-preemptive; shortest runtime | `strict_head_of_line` (true) |
| `easy_backfill` | non-preemptive; arrival order + EASY reservation for the head job | none |
| `srtf` | **preemptive**; shortest remaining runtime, suspends longer running jobs | none |
| `adaptive` | non-preemptive; first-fit by `w·wait − runtime − 0.1·cores`, w grows with queue wait | `base_wait_weight` (0.1) |
| `adaptive_multifactor` | non-preemptive or **preemptive**; adaptive multi-factor priority with selective reservation | `age_weight` .4, `short_weight` .4, `size_weight` .2, `max_age` 500, `adaptation_gain` .5, `reservation_xf` 2, `preemptive` false, `preempt_margin` .1 |

Researcher policies in a standalone file run with `strategy_files: {label: path.py:Class}` in a
batch config (CLI only).

## Adaptive policy

`adaptive_multifactor` scores each waiting job with
`U = W_age·min(1, wait/max_age) + W_short·(1 − ln(1+r)/ln(1+r_max)) + W_size·(C − c + 1)/C`.
The weights shift toward age as the queue's mean normalised age σ grows:
`W_age = w_age + g·σ·(w_short + w_size)`, with the other two scaled by `(1 − g·σ)`. A blocked
top job whose expansion factor `(wait + r)/r ≥ reservation_xf` holds an EASY-style reservation.
With `preemptive: true`, lower-utility running jobs may be suspended for it. Full research
background, formulation, complexity and limitations: `../docs/ADAPTIVE_POLICY.md`. Results:
`../docs/EVALUATION.md`.

## Workload format

CSV with header `job_id,arrival_time,runtime,required_cores`. Integer times, CPU cores and
runtime; `job_id` an integer or a non-empty string (`J1`); `#` comments and blank lines ignored.
Errors name the file, line and field. Named synthetic workloads are written
`synth:<light|heavy|short_heavy|mixed|wide_jobs>:n=<jobs>:seed=<seed>`: the id plus the cluster's
CPU cores reproduces the jobs exactly.

## Experiment configuration

```yaml
cluster_cores: 16
workloads: [synth:heavy:n=300:seed=7, ../workloads/synthetic_workload.csv]
strategies: [fifo, srtf, adaptive_multifactor, amf_preemptive]
strategy_params:
  fifo: {strict_head_of_line: true}
variants:                       # a registered policy under a label, with other parameters
  amf_preemptive: {strategy: adaptive_multifactor, params: {preemptive: true}}
repeats: {seeds: [7, 11, 13]}   # each synthetic workload once per seed
output_dir: results/
```

A single run (`adaptivesched run`) takes `workload`, `strategy`, `cluster_cores`, and optionally
`strategy_params`, `output_dir` and `strategy_file`.

## Outputs

`results/batch_<id>/`: `batch_summary.csv` (every attempted run, status `ok` or `failed`, error
text), `batch_manifest.json`, `runs/<run_id>.records.csv`, `runs/<run_id>.summary.json`, and
after `compare`/`plot`/`findings`: `compare.{csv,md}`, `plots/`, `findings_skeleton.md`.

Per-job records: `job_id, arrival_time, start_time` (first start), `finish_time, runtime,
waiting_time, turnaround_time, required_cores, preemption_count, execution_segments`
(`"0-10;11-101"`).

Each summary holds the metrics below plus `metadata`: run id, workload id and generator parameters
(including `runtime_estimate_error = 0.0`), strategy, base strategy for variants, parameters,
dispatch rule, cluster CPU cores, engine and its commit, package version, config hash, timestamp.

## Metrics

| metric | definition |
|---|---|
| `average_waiting_time`, `max_waiting_time` | waiting = finish − arrival − runtime (all waiting intervals; = start − arrival if never preempted) |
| `average_turnaround_time` | mean(finish − arrival) |
| `makespan` | max(finish) − min(arrival) |
| `cpu_utilization` | 100 × Σ(cores × runtime) / (cluster cores × makespan) |
| `bounded_slowdown` | mean of max(1, (finish − arrival)/max(runtime, τ)), τ = 10 |
| `fairness_index` | Jain's index over per-job bounded slowdowns, in (0, 1], 1 = equal slowdown |
| `throughput` | completed jobs / makespan |
| `completed_jobs`, `total_preemptions` | counts |

Each is one function in `adaptivesched/metrics/definitions.py`, with a hand-computed test in
`tests/test_metrics.py`.

## Dashboard

`adaptivesched serve` → `http://127.0.0.1:8000/`. Experiments are stored under `results/web/`
(`--results` to change).

- **A. Overview**: experiment, run, policy and workload counts; recent activity.
- **B. Configure**: workloads (synthetic with job count and seeds, or a listed CSV), CPU cores,
  a **Preset** menu for `adaptive_multifactor` (its defaults, or the tuned values of `docs/TUNING.md`),
  policies with their parameters (preemptive execution where supported), labelled variants.
- **C/G. Experiments**: status and progress of running experiments, errors and failed runs, the
  saved configuration, history, and rerun with the identical configuration.
- **D. Results**: metric table and bar charts per workload and capacity (never mixed).
- **E. Gantt**: execution segments on CPU-core lanes, preempted jobs as separate bars (resumed
  ones hatched); hover for details, click to inspect.
- **F. Jobs**: searchable, sortable, paged job table with segments and preemption counts.
- **H. Export**: per-run records CSV and summary JSON, the comparison CSV, chart PNGs.

API reference: `../docs/API.md`.

## Tests

```sh
pytest                        # from the repo root: engine, policies, experiments, API (197 tests)
python -m unittest discover -s tests -v   # the team's unittest-style engine tests
```

They include hand-computed schedules and metrics, a byte-identical rerun check, CLI-versus-web
parity, failed-run reporting, and input-validation errors.

## Known limitations

- Real logs come in only through `adaptivesched workloads --from-swf` (Parallel Workloads Archive,
  see `../workloads/README.md`); the dashboard lists converted CSVs but does not convert itself.
- Exact runtimes (`runtime_estimate_error` must be 0.0): runtime-based policies are favoured
  relative to a real cluster with user estimates.
- Preemption is free (no checkpoint or context-switch cost).
- Fairness is job-level; workloads have no user field.
- Gantt charts are drawn for at most 64 CPU cores (the job table works at any size).
- The dashboard has no authentication: it binds to 127.0.0.1 unless `--host` says otherwise.
- AMF's `max_age` must match the workload's waiting-time scale (`../docs/EVALUATION.md` E3, E5).
