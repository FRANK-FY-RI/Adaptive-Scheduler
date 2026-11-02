# AdaptiveSched HTTP API

Start it with `adaptivesched serve [--port 8000] [--host 127.0.0.1] [--results results/web]`.
The dashboard is at `/`. All endpoints are JSON unless noted. Errors are
`{"error": "<what and where>"}` with status 400 (bad input), 404 (unknown experiment/run/path),
409 (no results yet), 413 (body > 1 MB) or 500.

The API never simulates or computes anything itself. `POST /api/experiments` validates the
request, then queues an ordinary batch (`experiments.batch.run_batch`, the same function as
`adaptivesched batch`) on a background thread. Everything else serves the files that batch wrote.
A run submitted here produces the same summaries and records as the same config through the CLI
(`researcher/tests/test_api.py::test_cli_and_web_give_identical_results`).

## Catalog

| Method | Path | Returns |
|---|---|---|
| GET | `/api/health` | `{"ok": true}` |
| GET | `/api/overview` | `total_experiments`, `by_status`, `runs_ok`, `runs_failed`, `policies`, `workloads`, `engine`, `recent` (8 latest) |
| GET | `/api/policies` | `[{id, name, doc, preemptive_capable, params: [{name, default, type}], presets: {name: {param: value}}}]`, where `params` are the constructor's keyword parameters (the configuration schema) |
| GET | `/api/workloads` | `{synthetic: [{name, offered_load, description, id_template}], csv: [{name, path}]}` |

## Experiments

| Method | Path | Body / returns |
|---|---|---|
| POST | `/api/experiments` | body below → **202** with the experiment record (`status: queued`) |
| GET | `/api/experiments` | every experiment record, newest first |
| GET | `/api/experiments/{id}` | the record, plus `manifest` (batch_manifest.json) and `rows` (one per run: status, metrics, error) once finished |
| POST | `/api/experiments/{id}/rerun` | **202**, a new experiment with the identical saved request |
| GET | `/api/experiments/{id}/runs/{run_id}` | `{summary, records: [...], lanes, gantt_max_cores}`. `records` have `execution_segments` and `preemption_count`; `lanes` = Gantt layout `[job_id, start, finish, first_lane, n_lanes]` per segment (null above 64 CPU cores) |
| GET | `/api/experiments/{id}/runs/{run_id}/records.csv` | per-job CSV (download) |
| GET | `/api/experiments/{id}/runs/{run_id}/summary.json` | run summary with reproducibility metadata (download) |
| GET | `/api/experiments/{id}/compare.csv` | comparison table, every workload (download) |
| GET | `/api/experiments/{id}/plots/{metric}.png` | small-multiples chart; `metric` ∈ average_waiting_time, average_turnaround_time, cpu_utilization, makespan, bounded_slowdown, max_waiting_time, fairness_index, throughput |

**Request body** for `POST /api/experiments`:

```json
{
  "name": "heavy, preemption on/off",
  "cluster_cores": 16,
  "workloads": ["synth:heavy:n=300:seed=7", "<a CSV path listed by /api/workloads>"],
  "seeds": [7, 11, 13],
  "strategies": ["fifo", "srtf", "adaptive_multifactor", "amf_preemptive"],
  "strategy_params": {"fifo": {"strict_head_of_line": true}},
  "variants": {"amf_preemptive": {"strategy": "adaptive_multifactor", "params": {"preemptive": true}}}
}
```

- `seeds` expands each synthetic workload once per seed (each seed is its own workload id).
- `variants` gives a label to a registered policy with other parameters, so one comparison can
  hold, for example, the policy with and without preemption.
- Checked before anything runs: unknown fields; types; `cluster_cores > 0`; known generator ids;
  CSVs only from the catalog (no arbitrary file paths); every job fits the cluster; strategy ids
  registered; parameters accepted by the policy's constructor; at most 500 runs. Researcher policy
  files are not accepted over HTTP, because they are executable code (use the CLI's
  `strategy_files`).

**Experiment record:** `id` (`YYYYMMDDTHHMMSS-xxxxxx`), `name`, `created`, `finished`, `request`
(as submitted), `engine`, `status` (`queued` → `running` → `completed` | `failed`; `interrupted`
if the server stopped mid-run), `progress` `[done, total]`, `error`, `batch_dir`, `runs_ok`,
`runs_failed`. Failed *runs* inside a completed experiment appear in `rows` with their error.
They are never dropped.

**Storage:** `<results>/<id>/experiment.json` and `<results>/<id>/batch_<run_set_id>/`. There is
no database. Restarting the server lists every stored experiment again.
