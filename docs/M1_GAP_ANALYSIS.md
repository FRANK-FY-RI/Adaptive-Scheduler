# Milestone 1: architecture, gap analysis and plan (revised)

Scope: `writing-block.md` ("Next Development Phase") against the code, AS-REQ-RES-001
(Researcher), AS-REQ-SCH-001 (Scheduling Algorithm Developer) and AS-REQ-ENG-001 (Engine).
First written against `main` @ `dfb647f`. **Revised 2026-11-01 against `main` @ `daa589d`**,
which added engine preemption, so decision D1 of the first version is settled.
"Status before" is what `daa589d` had. "Now" is the working tree after this phase.
Every status was checked in the code.

Status key: **Done** · **Partial** · **Missing** · **Modify** · **New**.

## 0. What changed in the brief's premises

1. **Preemption now exists** (`daa589d`, Omkar). `PreemptiveSchedulingPolicy.select_jobs_to_preempt`
   is an optional hook. `ExecutionRecord` carries `execution_segments` and `preemption_count`, and
   `waiting_time` includes waits between segments. `SRTFPolicy` is the first preemptive policy.
   The brief's "both semantics" premise is now true.
2. **`AdaptivePolicy` was rewritten** in the same commit: one parameter `base_wait_weight`, first-fit
   over `w·wait − runtime − 0.1·cores`, no reservation. The researcher configs still passed its old
   parameters (`base_short_weight`, `adaptation_gain`, `enable_backfill`), so every `adaptive` run
   would have failed. Fixed (§1, row 2.1-c).
3. Two CLIs remain: the team's `python -m adaptive_scheduler.run_simulation` (one run, prints
   metrics) and `adaptivesched` (configs, batches, exports, plots, findings, and now the dashboard).
   The API sits on the second, so web and CLI share one code path.

## 1. Consolidated requirements checklist

### Phase 1: adaptive multi-heuristic policy

| # | Requirement | Before | Now | Where |
|---|---|---|---|---|
| 1.1 | Literature-based adaptive multi-heuristic policy | Missing | **Done** | `docs/ADAPTIVE_POLICY.md` §2–3: Slurm multifactor + Tang et al. adaptation + Srinivasan selective reservation |
| 1.1-1..6 | Multiple heuristics, documented utility, adaptation, tunable, deterministic, uses context | Partial (`adaptive`: no grounding) | **Done** | `policies/adaptive_multifactor.py`; formula §4, rules §5, parameters §6 |
| 1.1-7 | Both execution semantics | Missing | **Done** | `preemptive` parameter; `select_jobs_to_preempt` |
| 1.2 | Research document | Missing | **Done** | `docs/ADAPTIVE_POLICY.md` (11 references, complexity §8, limitations §9) |
| 1.3-1..5 | Interface, separate from engine, read-only context, valid/None, respects resources | Done (pattern) | **Done** | no engine change was needed (§10 of the policy doc) |
| 1.3-6 | Policy-specific parameters | Partial | **Done** | keyword-only constructor params; validated with `ConfigurationError` |
| 1.3-7 | Stable unique identifier (SCH-FR-10) | Modify | **Done** | `policies.policy_ids()`: one id per policy, no class-name aliases |
| 1.3-8 | Selectable through the runner | Partial | **Done** | `adaptivesched` (any id) and team CLI (`adaptive-multifactor[-preemptive]`, plus `adaptive`, `easy-backfill`) |
| 1.3-9 | Document utility, params, tie-breaks, assumptions | Partial | **Done** | class docstring + policy doc; parameter schema served by `GET /api/policies` (SCH-FR-14) |
| 1.4 | Tests: heuristics, utility, adaptation, cores, short/long, waits, constrained, ties, empty queue, invalid proposals, both semantics | Partial | **Done** | `tests/test_adaptive_multifactor.py`: 22 tests, numbers hand-computed in the docstrings |

### Phase 2: experimentation and analysis

| # | Requirement | Before | Now | Where |
|---|---|---|---|---|
| 2.1-a | One/many policies, workload, cores, params, batches, failed runs recorded | Done | Done | `experiments/batch.py` |
| 2.1-b | Preemptive / non-preemptive configuration | Missing | **Done** | policy parameter (`preemptive`) or policy choice (`srtf`); every summary records `preemptive` |
| 2.1-c | Same policy, several configurations in one comparison | Missing | **New, done** | `variants:` in batch configs (e.g. `amf_preemptive`, `amf_fixed`) |
| 2.1-d | Reproducibility metadata | Partial (engine commit lost on editable installs) | **Done** | `engine_version` = commit from the editable checkout, `+dirty` if engine sources are edited |
| 2.2 | Avg waiting, avg turnaround, makespan, utilization, completed jobs | Partial | **Done** | `metrics/definitions.py` (`completed_jobs` added) |
| 2.2 | Bounded slowdown (τ documented), max waiting | Done | Done | τ = 10 |
| 2.2 | Throughput | Missing | **Done** | completed / makespan |
| 2.2 | Fairness | Missing | **Done (job-level)** | Jain's index over bounded slowdowns; no user field, so no user-level fair share |
| 2.2 | Preemption-aware waiting/turnaround | Modify | **Done** | waiting = finish − arrival − runtime (all intervals) |
| 2.3 | Per-job: turnaround, execution intervals, preemption count | Missing | **Done** | `*.records.csv` columns `turnaround_time, preemption_count, execution_segments` |
| 2.3 | Record invariants that admit preemption | Modify (runner rejected any preempted job) | **Done** | `adapter.record_problems` (segments ordered, sum to runtime, …) |
| 2.3 | String job ids (team CSV format `J1`) | Missing | **Done** | loader, records, inspect, Gantt |
| 2.4 | Gantt from recorded intervals, several per preempted job | Partial | **Done** | `analysis/gantt.py` (resumed segments hatched); dashboard canvas Gantt |
| 2.4 | Comparison plots for all five metrics | Partial | **Done** | `adaptivesched plot` default: 7 metrics |
| 2.4 | Evaluation document | Partial | **Done** | `docs/EVALUATION.md` (120 + 45 runs, 0 failed) |

### Phase 3: dashboard (all New, all done)

| Item | Where |
|---|---|
| API: policies + parameter schema, workloads, create/run single or comparison, async status/progress, metrics, records, export, metadata, rerun | `researcher/adaptivesched/api/server.py`, documented in `docs/API.md` |
| Background execution: reads never wait on a run | one worker thread; `tests/test_api.py::test_long_run_does_not_block_reads` |
| Input validation with meaningful errors | 400 with the failing field (11 negative tests) |
| Frontend sections A–H | `researcher/adaptivesched/web/` (no framework, no CDN) |
| Results consistent with the CLI | same `run_batch`; `test_cli_and_web_give_identical_results` diffs every summary and records file |
| Large result sets | paged job table (50 rows), canvas Gantt; Gantt limited to 64 CPU cores (table still works) |

### Phase 4: testing and documentation

| Item | Status |
|---|---|
| Unit tests: policies, utility, metrics | Done: 71 team tests, 126 researcher tests (`pytest` from the repo root: 197 pass) |
| Integration: policy–engine, experiment execution, API, frontend↔backend, regression for both semantics, reproducibility, errors | Done (see the test files named above) |
| CLI ↔ web parity | Done |
| README for the new architecture | Done: `researcher/README.md` (full) + a pointer section in the root `README.md` |

## 2. Roadmap as executed

| Milestone | Delivered |
|---|---|
| M1 | this document |
| M2 | `docs/ADAPTIVE_POLICY.md` |
| M3 | `adaptive_multifactor.py`, `policy_ids()`, team CLI choices, 22 tests |
| M4 | preemption-aware records and metrics, variants, plots, Gantt, `docs/EVALUATION.md` |
| M5 | API + dashboard + `adaptivesched serve`, 18 API tests |
| M6 | full suite green; README and docs; decisions in `docs/DECISIONS.md` |

## 3. Task allocation (for the team's own follow-up)

Per the user's instruction this phase was done in one pass across the codebase. For review and
ownership, the work maps to the three roles:

| Owner | Files to review |
|---|---|
| Scheduling algorithm developer | `src/adaptive_scheduler/policies/adaptive_multifactor.py`, `policies/__init__.py` (`policy_ids`), `tests/test_adaptive_multifactor.py`, `docs/ADAPTIVE_POLICY.md` |
| Engine / API developer | `src/adaptive_scheduler/run_simulation.py` (new choices), `researcher/adaptivesched/api/`, `researcher/adaptivesched/web/`, `docs/API.md` |
| Researcher | `researcher/adaptivesched/{metrics,experiments,analysis}/`, `researcher/examples/`, `docs/EVALUATION.md` |

The engine itself (`engine.py`, `models.py`, `interfaces.py`) is **unchanged**.

## 4. Integration points

| Interface | Producer → consumer | Contract |
|---|---|---|
| `select_next_job` / `select_jobs_to_preempt` | policies → engine | unchanged from `daa589d` |
| `policy_ids()`, `get_policy(id, **params)` | policies → runner, API | one stable id per policy; constructor keywords are the parameter schema |
| `ExecutionRecord` (segments, preemption_count) | engine → adapter | mapped field for field into `JobRecord` |
| `run_batch(cfg, adapter, engine, on_progress)` | runner → CLI, API | the only way any run is executed |
| batch directory files | runner → analysis, API, dashboard | `batch_summary.csv`, `batch_manifest.json`, `runs/<id>.{records.csv,summary.json}` |

## 5. Architecture

```
src/adaptive_scheduler/        engine + policies (team package; engine untouched)
  policies/adaptive_multifactor.py   NEW policy
researcher/adaptivesched/
  workloads/ metrics/ experiments/ analysis/   experiment layer (extended)
  api/server.py                 NEW: stdlib ThreadingHTTPServer + one worker thread
  web/                          NEW: static dashboard (HTML/CSS/JS, served by the API)
docs/                           M1 (this), ADAPTIVE_POLICY, EVALUATION, API, DECISIONS
```

No new runtime dependency, no database (the result files are the store), no authentication
(the server binds to 127.0.0.1 by default).

## 6. Acceptance criteria and their checks

| Milestone | Accepted when | Check |
|---|---|---|
| M2 | every §1.2 item, all edge cases specified, ≥ 3 credible references | `docs/ADAPTIVE_POLICY.md` §1–10, 11 references |
| M3 | registered under one id; params validated; §1.4 bullets tested; existing tests pass with invariants on | `pytest tests` (71 pass) |
| M4 | hand-computed metric tests; segment columns; all comparison plots; byte-identical rerun; evaluation doc | `pytest researcher/tests` (126 pass) |
| M5 | API covers §3.2; web run equals CLI run; long runs do not block reads | `researcher/tests/test_api.py` |
| M6 | full suite green; README covers §4.2 | `pytest` from the repo root: 197 pass |
