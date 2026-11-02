# Decisions log: next development phase

One line per decision: date, what was decided, why. Earlier researcher-side decisions (M0–M6) are
in the researcher repository's `docs/DECISIONS.md`.

- 2026-11-01 — Work on `main` @ `daa589d` (preemption) via fast-forward; nothing committed or pushed: the user commits and pushes on a non-main branch.
- 2026-11-01 — New policy `adaptive_multifactor` added beside the team's `adaptive`, not replacing it. The brief says not to rewrite working code, and the two are compared in the evaluation.
- 2026-11-01 — AMF = Slurm-style normalised multifactor (age, shortness, narrowness) + adaptive weight shift toward age (Tang et al. 2012 idea) + selective reservation by expansion factor (Srinivasan et al. 2002) + optional priority preemption. Each part has a published source and can be tested on its own.
- 2026-11-01 — Shortness uses ln(1 + remaining runtime) normalised by the largest over waiting and running jobs. Logarithmic, so one very long job does not flatten the others; over waiting and running, so preemption compares utilities on one scale.
- 2026-11-01 — Adaptation signal = mean normalised age of the queue. It exists in the context, is bounded to [0, 1] and is deterministic; it reacts to widespread waiting, not one outlier (documented limitation).
- 2026-11-01 — Preemption only for the top-ranked job, only if lower-utility victims can free enough cores (all or nothing), with a 0.1 utility margin. No useless partial preemptions; the margin prevents ping-pong.
- 2026-11-01 — No engine change. AMF needed only context fields that `daa589d` already exposes.
- 2026-11-01 — `policies.policy_ids()` added (one id per policy = module name or registered name). `discover_policies()` also returns class-name and display-name aliases, which made listings ambiguous (SCH-FR-10).
- 2026-11-01 — Waiting time = finish − arrival − runtime. It equals RES §6's start − arrival for a job never preempted, and also counts waits between segments, matching the engine's `waiting_time`.
- 2026-11-01 — Fairness = Jain's index over per-job bounded slowdowns (job-level). Workloads have no user field, so user-level fair share cannot be computed without a schema change.
- 2026-11-01 — Throughput = completed jobs / makespan; completed_jobs is its own metric function (hard rule: metrics computed in one place only).
- 2026-11-01 — Records CSV gains `turnaround_time, preemption_count, execution_segments` ("a-b;c-d"). Old files without them are still readable as one-segment jobs.
- 2026-11-01 — Batch configs gain `variants: {label: {strategy, params}}`. One comparison can hold one policy in several configurations (preemptive on/off, adaptation off), which the evaluation needs; a variant's summary records `base_strategy`.
- 2026-11-01 — `batch_adaptive_fixed.yaml` removed: its `adaptive` parameters no longer exist after `daa589d`. Its role (an adaptation control) is now the `amf_fixed` variant in `batch_study.yaml`.
- 2026-11-01 — CSV job ids may be strings (`J1`, as in `workloads/synthetic_workload.csv`); an id that is an integer is read as one; mixed ids sort ints first, then strings.
- 2026-11-01 — `engine_version` for an editable install = the checkout's HEAD, plus `+dirty` if `src/` has uncommitted changes. The evaluation's runs record `daa589d0cffc+dirty`, which is honest: the policy file is not committed yet.
- 2026-11-01 — `researcher/pyproject.toml` depends on `adaptive-scheduler` by name instead of a git pin: the code needs this phase's engine package, which lives one directory up; install the root package first.
- 2026-11-01 — Non-finite floats (`reservation_xf: .inf`) are written to JSON as the string "inf": browsers reject the non-standard `Infinity` token.
- 2026-11-01 — Plot colours: all eight slots of the dataviz reference palette in fixed order (fifo, sjf, adaptive, easy_backfill, srtf, adaptive_multifactor, amf_preemptive, amf_fixed). Only the first three pass the all-pairs colour checks, so the scatter is now small multiples per condition and the scatter and CDF are direct-labelled: identity never rests on colour alone.
- 2026-11-01 — API on the standard library (`ThreadingHTTPServer` + one worker thread). No framework dependency, which the brief's "avoid premature complexity" and the project's dependency rule both favour; validation is explicit code with tests.
- 2026-11-01 — Experiment store = files (`<results>/<id>/experiment.json` + the batch directory). No database: the runner already writes reproducible files, and the dashboard reads them.
- 2026-11-01 — API refuses researcher strategy files and arbitrary CSV paths: a policy file is executable code and a path could read any file; the CLI keeps both.
- 2026-11-01 — One worker thread runs experiments in submission order, so results never depend on thread timing and reads never wait. A ponytail note marks where to add workers.
- 2026-11-01 — Dashboard in plain HTML/CSS/JS served by the API, with no CDN and no framework: the project runs offline; charts are inline SVG and the Gantt is a canvas (scales to thousands of segments).
- 2026-11-01 — Server binds to 127.0.0.1 by default; there is no authentication, so exposing it on a network is a deliberate `--host` choice.
- 2026-11-01 — Real workloads: cleaned Parallel Workloads Archive logs (KTH SP2, SDSC SP2, HPC2N, CTC SP2, SDSC Blue; 100–1,152 CPUs), converted to the CSV format by `adaptivesched workloads --from-swf`. A CSV keeps the format every tool already reads; the SWF reader is the only new code.
- 2026-11-01 — SWF mapping: job_id = field 1, arrival = field 2 (rebased to 0), runtime = round(field 4), CPU cores = field 5 (8 if missing), cluster = header MaxProcs. Drop runtime <= 0, no processor count, wider than the machine; keep failed/cancelled jobs that ran (they used CPU cores).
- 2026-11-01 — A converted workload is a window of consecutive jobs (default 5,000, centred in the log): whole logs are 28k–243k jobs; a window keeps the real arrival pattern and job mix at a size every policy simulates in seconds.
- 2026-11-01 — Engine invariant checks off above 1,000 jobs (`engine_invariant_checks` in every summary): the engine's per-event check scans all jobs (1,500 jobs: 17.8 s vs 1.6 s); the runner still verifies every record (segments, capacity, waits).
- 2026-11-01 — Raw logs are not committed (`workloads/pwa/*.swf.gz` ignored); the archive refuses scripted downloads, so they are fetched in a browser from the links in workloads/README.md.
- 2026-11-01 — Gantt limit raised from 64 to 2,048 CPU cores (thin lanes, no outlines above 64) so real machines can be drawn.
- 2026-11-01 — "Optimal weights" defined by a stated objective: J = mean ln(bsld/bsld_EASY) + mean ln(maxwait/maxwait_EASY) over windows. It counts the typical job and the worst-off job equally, ratios to EASY make machines of different sizes comparable, and every other metric is recorded per candidate so the ranking can be redone.
- 2026-11-01 — Search = seeded random search + two rounds of local refinement (`adaptivesched tune`), not machine learning: nothing is fitted, candidates are simulated. Training windows (2,000 jobs at 10% and 75% of each log) are disjoint from the held-out 5,000-job windows used for validation.
- 2026-11-01 — A second search with preemption fixed off: free preemption dominates the objective, and a real cluster without cheap checkpointing can only use the non-preemptive result.
- 2026-11-01 — Searches and validation run on the college HPC (PBS, workq, ncpus 8/6) at the user's request, from a tarball in ~/adaptivesched-m0/next; the tuner forks workers (Python 3.14's forkserver/spawn re-import the main script, which failed for stdin and for the Windows console launcher).
- 2026-11-01 — Class defaults of AdaptiveMultifactorPolicy are not changed to the tuned values: the defaults are pinned by hand-computed tests, and the tuned max_age (in seconds) does not transfer to the synthetic workloads' time scale. The tuned values are published in TUNING.md and examples/tuned/*.yaml.
- 2026-11-01 — Tuned parameter sets live on the policy class as `AdaptiveMultifactorPolicy.PRESETS` (one source for code, API and dashboard); `GET /api/policies` serves them and the dashboard offers a Preset menu. JSON has no infinity, so the dashboard sends "inf" and the API converts it.
