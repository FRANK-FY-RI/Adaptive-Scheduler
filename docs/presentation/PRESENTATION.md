# AdaptiveSched: presentation brief for Claude Design

Brief for a **bachelor-level college presentation** (about 20–25 minutes, 26 slides). Each slide
lists its **title**, the **on-slide content** (keep it short), the **visual** to place (an image
from `images/` next to this file, or a table or diagram to draw), and **speaker notes** (what to
say; not shown on the slide).

## Design instructions

- 16:9, clean academic style, light background (`#fcfcfb`), dark text (`#0b0b0b`), secondary
  text `#52514e`, one accent colour (blue `#2a78d6`).
- Fixed colour per scheduling policy, the same everywhere (it matches the charts):
  fifo `#2a78d6` · sjf `#eb6834` · adaptive `#1baf7a` · easy_backfill `#eda100` · srtf `#e87ba4`
  · adaptive_multifactor (AMF) `#008300` · amf_preemptive `#6250d6` · amf_fixed `#e34948`.
- Sans-serif font. At most 6 bullets per slide. Formulas in a monospace or math style.
- Images are PNGs in `images/` (SVG versions exist with the same names). Do not crop away
  axis labels or titles.
- Never call one policy "the best". The project's conclusion is that the best choice depends on
  the workload and on which metric matters.

## Image index

| file | shows | used on slide |
|---|---|---|
| `images/architecture.png` | system components and data flow | 6 |
| `images/engine_event_loop.png` | one step of the discrete-event engine | 7 |
| `images/amf_factor_curves.png` | the three heuristic factors as curves | 12 |
| `images/synthetic_avg_wait_grid.png` | average waiting time, 8 policies × 5 workloads × 3 seeds | 16 |
| `images/synthetic_max_wait_grid.png` | maximum waiting time, same layout | 16 |
| `images/synthetic_tradeoff_scatter.png` | average vs maximum wait, per workload condition | 17 |
| `images/synthetic_wait_cdf_heavy.png` | distribution of waiting times on the heavy workload | 17 (optional) |
| `images/gantt_fifo_vs_amf_heavy.png` | Gantt chart: FIFO vs AMF | 18 |
| `images/gantt_srtf_vs_amf_preemptive.png` | Gantt chart with preemption (hatched = resumed) | 18 |
| `images/realdata_heldout_summary.png` | every policy vs EASY on 10 real-log windows | 20 |
| `images/tuning_search_tradeoff.png` | all 620 candidates of the parameter search | 21 |
| `images/dashboard_configure.png` | dashboard: configuration form with presets | 23 |
| `images/dashboard_results.png` | dashboard: metrics table and charts | 23 |
| `images/dashboard_gantt.png` | dashboard: interactive Gantt | 23 |
| `images/dashboard_experiments.png` | dashboard: execution status and history | 23 (optional) |
| `images/dashboard_jobs.png` | dashboard: job inspection table | 23 (optional) |

---

## Slide 1: Title

**On slide**
- **AdaptiveSched: comparing and tuning job-scheduling policies for HPC clusters**
- Subtitle: A discrete-event simulator, an adaptive multi-heuristic scheduler, and an evaluation on real supercomputer logs
- [Team member names] · [Course / department] · [Date]

**Speaker notes:** Introduce the team and the one-line idea: we built a simulator to test
scheduling rules fairly, designed an adaptive scheduler, and measured everything on real data.

---

## Slide 2: The problem

**On slide**
- An HPC cluster has a fixed number of CPU cores; many users submit **jobs** (programs needing *c* cores for *t* seconds)
- When the cluster is full, jobs wait in a queue. **Which job should start next?**
- That choice is the **scheduling policy**. It decides how long people wait and how busy the machine is
- Different rules favour different people: short jobs, old jobs, small jobs…
- There is no rule that is best for every workload and every goal

**Visual:** a simple drawing: a queue of job blocks of different widths (CPU cores) and lengths
(runtime) waiting in front of a grid of 16 cores, some busy.

**Speaker notes:** Give an everyday analogy: a print queue or a restaurant with tables of different
sizes. A big group (wide job) can block the queue; serving small groups first is faster on average
but the big group may wait forever. That tension is the whole project.

---

## Slide 3: Goals and research questions

**On slide**
- **G1** Build a simulator in which policies can be compared under *identical* conditions
- **G2** Design an *adaptive* scheduler that combines several heuristics, grounded in the literature
- **G3** Evaluate all policies on synthetic **and real** workloads with consistent metrics
- **G4** Find good weights for the adaptive scheduler by systematic search
- **G5** Make it usable: command line + web dashboard, reproducible results
- Research questions: How do policies differ? What does each trade away? Does adapting help? Do rankings change with the workload?

**Speaker notes:** Stress that the study is comparative and open-ended. We report trade-offs, not a
single winner.

---

## Slide 4: Key terms and metrics

**On slide** (table)

| term | meaning / formula |
|---|---|
| job | arrival time, runtime, required CPU cores |
| waiting time | finish − arrival − runtime (all time not running) |
| turnaround | finish − arrival |
| makespan | last finish − first arrival |
| CPU utilization | 100 × Σ(cores × runtime) / (cluster cores × makespan) |
| bounded slowdown | mean of max(1, turnaround / max(runtime, 10)) |
| fairness | Jain's index over slowdowns, from 0 (unequal) to 1 (equal) |
| throughput | jobs completed / makespan |

**Speaker notes:** Explain slowdown with an example: a 1-minute job that waited 9 minutes has
slowdown 10, while a 10-hour job that waited 9 minutes has slowdown ≈ 1. The bound τ = 10 s stops
tiny jobs from dominating. Maximum waiting time shows the worst-off job, which averages hide. Every
metric is defined once in code (`metrics/definitions.py`) and has a hand-checked test.

---

## Slide 5: Why simulation?

**On slide**
- Real clusters cannot be used for experiments: runs are not repeatable and changes are risky
- A **discrete-event simulator** replays a workload in seconds, deterministically
- Same jobs + same cluster + only the policy changed → differences come from the policy
- Every run records its seed, configuration hash and engine version, so it can be reproduced exactly

**Speaker notes:** Mention reproducibility evidence: reruns are byte-identical, and the same runs
on a laptop and on the college HPC gave identical metrics (60 of 60).

---

## Slide 6: System architecture

**Visual:** `images/architecture.png` (full width)

**On slide (caption)**
- Engine and policies (scheduling) are separate from the experiment layer, analysis and interfaces
- The CLI and the web dashboard call the **same** experiment runner, so results are identical by construction

**Speaker notes:** Walk top to bottom. The researcher uses either the browser or the terminal. The
HTTP API is plain Python standard library: it validates input and runs experiments on a
background thread. The experiment layer loads workloads, runs the simulation through an adapter,
computes metrics and writes CSV/JSON files. Analysis reads only those files. The engine owns time
and resources, and policies only *propose* which job to start.

---

## Slide 7: The simulation engine

**Visual:** `images/engine_event_loop.png`

**On slide**
- Event-driven: the clock **jumps** to the next arrival or completion (no time ticks)
- At one time: completions first (free cores), then arrivals, then the policy decides
- The engine **validates** every decision (job exists, is waiting, fits in free cores)
- Invariants checked: cores never over-allocated, a job is in exactly one state…
- Optional **preemption**: a policy may suspend running jobs; they resume later with their remaining runtime

**Speaker notes:** Explain why event-driven is efficient: a month-long log with 5,000 jobs needs
about 10,000 steps, not millions of seconds. Preemption model: suspending is free (no checkpoint
cost), a multi-core job is suspended as a whole (gang scheduling), and decisions happen only at
events. The engine raises a clear error if a policy proposes something illegal or stalls while
work could run.

---

## Slide 8: Workload model

**On slide**
- A workload = list of jobs `(job_id, arrival_time, runtime, required_cores)`
- **Synthetic** workloads (seeded, reproducible): light, heavy, short_heavy, mixed, wide_jobs
- **Real** workloads: five production logs from the Parallel Workloads Archive (next slides)
- Inputs are validated with clear errors: bad rows, duplicate ids, jobs wider than the cluster…

**On slide** (small table)

| synthetic condition | what it stresses |
|---|---|
| light (load 0.5) | an uncongested cluster |
| heavy (load 1.0) | congestion |
| short_heavy | many short jobs behind a few very long ones |
| mixed | very varied runtimes and widths |
| wide_jobs (50–100 % of cores) | blocking on CPU cores |

**Speaker notes:** Offered load 1.0 means jobs arrive exactly as fast as the cluster can process
them, so queues grow. Each condition exists to expose a weakness of some policy.

---

## Slide 9: Baseline scheduling policies

**On slide** (table)

| policy | rule | preemptive |
|---|---|---|
| FIFO | first come, first served; if the first job does not fit, wait | no |
| SJF | shortest job first | no |
| EASY backfilling | FIFO + reserve a start time for the first job; later jobs may jump ahead only if they finish before that reservation | no |
| SRTF | shortest *remaining* time first; suspends longer running jobs | **yes** |
| adaptive (team) | waiting-time-weighted score, starts any job that fits | no |

**Speaker notes:** FIFO is fair in order but wastes cores ("head-of-line blocking"). SJF minimises
average waiting time but long jobs can starve. EASY is what most real supercomputers use. SRTF is
the preemptive version of SJF. These are the reference points for our adaptive policy.

---

## Slide 10: Scheduling as an AI agent

**On slide** (PEAS table)

| PEAS | for the scheduler |
|---|---|
| **P**erformance measure | low waiting time and slowdown, low maximum wait, high utilization |
| **E**nvironment | the cluster: waiting queue, running jobs, free CPU cores, simulated clock |
| **A**ctuators | start a waiting job; (optionally) suspend running jobs |
| **S**ensors | the read-only `SchedulerContext`: current time, free cores, waiting jobs, running jobs with expected finish times |

- **Environment:** fully observable (the whole queue is visible), deterministic (exact runtimes), **sequential** (today's choice changes tomorrow's queue), **dynamic** (jobs keep arriving), discrete, single-agent

**Speaker notes:** This maps the project onto the standard intelligent-agent framework (Russell &
Norvig). The agent never changes the environment directly. It proposes an action, and the engine
checks it, like an actuator that refuses unsafe commands.

---

## Slide 11: Which type of agent is each policy?

**On slide** (table)

| policy | agent type | why |
|---|---|---|
| FIFO, SJF, SRTF | **simple reflex agent** | fixed condition–action rule on the current queue ("if the shortest job fits, start it") |
| EASY backfilling | **model-based / goal-based** | keeps a model of when running jobs finish; goal = do not delay the reserved job |
| team `adaptive` | **utility-based** (basic) | scores jobs with a utility and picks the highest |
| **AMF (ours)** | **utility-based agent with internal state** | multi-factor utility; weights adapt to the queue's state; reservation goal; optional preemption |
| AMF tuning | **not a learning agent** | weights were found *offline* by search, then fixed; the agent does not learn while running |

**Speaker notes:** A utility-based agent chooses the action with the highest expected "usefulness".
Here the utility is a weighted score per job. AMF is adaptive (its weights change with the queue
state) but not learning: nothing is fitted from experience at run time. The tuning on slides
21–22 was done by us, the researchers, before deployment, which we describe honestly as black-box
optimisation, not machine learning.

---

## Slide 12: Our policy: Adaptive Multi-Factor (AMF), the heuristics

**Visual:** `images/amf_factor_curves.png`

**On slide**
- Every waiting job *j* gets a **utility** U_j; the highest starts first
- `U_j = W_age·A_j + W_short·S_j + W_size·N_j`
- **Age** `A_j = min(1, wait_j / max_age)`: grows while a job waits (prevents starvation)
- **Shortness** `S_j = 1 − ln(1 + r_j) / ln(1 + r_max)`: favours short remaining runtime (faster average)
- **Narrowness** `N_j = (C − c_j + 1) / C`: favours jobs needing few cores (better packing)
- All factors lie in [0, 1], so each weight is a share of the score

**Speaker notes:** Explain each curve on the image. Age rises linearly until max_age, then stays at
1. The tuned max_age is about 2.4 days. Shortness uses a logarithm so one very long job does not
squash everyone else's score. Narrowness is a straight line from 1 (one core) to almost 0 (whole
machine). The structure follows Slurm's "multifactor priority", which real supercomputers use.

---

## Slide 13: AMF, adaptation, reservation and preemption

**On slide**
- **Adaptation:** σ = mean age factor of the queue (0 = fresh queue, 1 = everyone old)
  - `W_age = w_age + g·σ·(w_short + w_size)`, `W_short = w_short·(1 − g·σ)`, `W_size = w_size·(1 − g·σ)`
  - When the queue ages, weight moves to age, so old jobs are protected
- **Selective reservation:** if the top job does not fit and its expansion factor (wait + runtime)/runtime ≥ `reservation_xf`, it reserves a start time; others may start only if they finish before it
- **Optional preemption:** if the top job does not fit, suspend running jobs whose utility is lower by more than a margin, only if that frees enough cores
- Ties broken by arrival time, then job id → fully deterministic

**Speaker notes:** Weights always sum to 1. The gain g (0–1) sets how strongly the policy adapts.
Reservation is the EASY idea applied to our ranking, and "selective" means only jobs that have
already waited long get one (Srinivasan et al. 2002). Preemption is off by default. Complexity
per decision is O((n + m) log(n + m)) for n waiting and m running jobs.

---

## Slide 14: Worked example

**On slide**
- 8 cores, time t = 10. Job 1: arrived at 0, runtime 9, 2 cores. Job 2: arrived at 10, runtime 1, 8 cores
- Ages: 10/500 = 0.02 and 0 → σ = 0.01 → weights (0.403, 0.398, 0.199)
- Shortness: S₁ = 0, S₂ = 1 − ln2/ln10 = 0.699. Narrowness: N₁ = 7/8, N₂ = 1/8
- U₁ = 0.403·0.02 + 0.199·0.875 = **0.182**
- U₂ = 0.398·0.699 + 0.199·0.125 = **0.303** → job 2 is preferred

**Speaker notes:** This exact example is a unit test in the code, computed by hand first. It shows
that a very short job beats a narrower but long job when neither has waited long.

---

## Slide 15: Literature basis and alternatives considered

**On slide**
- **Slurm multifactor priority** (SchedMD): normalised factors with weights; age capped at PriorityMaxAge
- **Maui scheduler** (Jackson et al. 2001): weighted priority + backfilling
- **Tang et al. 2009 / 2012**: utility-based and *adaptive* metric-aware scheduling
- **Srinivasan et al. 2002**: selective reservation by expansion factor
- **EASY backfilling** (Lifka 1995; Mu'alem & Feitelson 2001)
- Rejected: learned priority functions (Carastan-Santos 2017), which are offline ML, and the WFP formula, which does not adapt

**Speaker notes:** The policy is not an arbitrary formula. Each part comes from a published,
production-tested idea, and the combination is our contribution. Full references are in
`docs/ADAPTIVE_POLICY.md`.

---

## Slide 16: Results on synthetic workloads: averages and worst case

**Visual:** `images/synthetic_avg_wait_grid.png` (left) and `images/synthetic_max_wait_grid.png` (right)

**On slide**
- 8 policy configurations × 5 workload conditions × 3 seeds = 120 runs, 16 CPU cores
- SRTF has the lowest average wait in **all 15** workloads (e.g. short_heavy 15–20 vs FIFO 148–374)
- SJF and SRTF have the highest **maximum** waits on heavy, mixed and wide_jobs
- AMF beats FIFO and EASY on average wait in 15/15 workloads
- On a half-idle cluster (light), all policies are almost the same

**Speaker notes:** Read the grids: rows are workload conditions, columns are seeds (independent
random workloads). Compare bar heights only within one panel. The main lesson is that the policy
with the best average often has the worst maximum.

---

## Slide 17: The central trade-off

**Visual:** `images/synthetic_tradeoff_scatter.png` (optional small inset: `images/synthetic_wait_cdf_heavy.png`)

**On slide**
- Each point = one policy on one workload: average wait (x) vs maximum wait (y)
- Lower-left would be ideal, but no policy is there everywhere
- Favouring short jobs → low average, high maximum (starvation of long jobs)
- Arrival order / reservations → protected worst case, higher average

**Speaker notes:** This is the core insight of scheduling: you cannot minimise everyone's wait at
once. The CDF inset shows the whole waiting-time distribution. Most jobs wait little under SJF, but
the tail is long.

---

## Slide 18: Seeing schedules: Gantt charts

**Visual:** `images/gantt_fifo_vs_amf_heavy.png` and `images/gantt_srtf_vs_amf_preemptive.png`

**On slide**
- Each bar = a job running on some CPU cores over time; grey = idle cores
- FIFO leaves idle gaps when a wide job blocks the queue; AMF fills them
- With preemption, a job can run in several pieces (hatched = resumed after being suspended)
- SRTF preempts very often; amf_preemptive preempts rarely but protects the worst case better

**Speaker notes:** Gantt charts are drawn only from recorded start and finish times. They are
visual proof of what the metrics say. On the second chart, compare the captions: SRTF average wait
19.0, max 1048, against amf_preemptive average 50.5, max 616.

---

## Slide 19: Real workloads: five production supercomputer logs

**On slide** (table)

| log | machine | CPUs | jobs | period |
|---|---|---|---|---|
| KTH SP2 | IBM SP2, Stockholm | 100 | 28,476 | 1996–97 |
| SDSC SP2 | IBM SP2, San Diego | 128 | 59,715 | 1998–2000 |
| HPC2N | Linux cluster, Umeå | 240 | 202,871 | 2002–06 |
| CTC SP2 | IBM SP2, Cornell | 338 | 77,222 | 1996–97 |
| SDSC Blue | Blue Horizon, San Diego | 1,152 | 243,306 | 2000–03 |

- Source: Parallel Workloads Archive (cleaned logs, Standard Workload Format with 18 fields per job)
- Used fields: job number → id, submit time → arrival, run time → runtime, allocated processors → cores
- Windows of 5,000 consecutive jobs, each run at its machine's real size

**Speaker notes:** These are real accounting logs: real users, real arrival bursts, runtimes from
seconds to 5 days, jobs up to the whole machine. The load in our windows is 69–85 %. We wrote a
converter (`adaptivesched workloads --from-swf`) that records the source of every number.

---

## Slide 20: Results on real logs

**Visual:** `images/realdata_heldout_summary.png`

**On slide**
- EASY backfilling still had the **best worst case** (lowest max wait in 9/10 windows, tied in the 10th)
- SRTF: lowest average wait everywhere, but 0.6–2.4 preemptions *per job* and max waits up to 27 days
- AMF with default settings starved long jobs for up to **49 days**: its 500-second age cap saturates instantly on logs measured in seconds
- Setting max_age to the waiting-time scale fixed most of it, and parameter search did the rest (next slides)

**Speaker notes:** Explain the bars: each is a ratio to EASY, so below 1 is better than EASY. Blue
is the typical job (slowdown), orange the worst-off job (max wait). The discovery that max_age
must match the time scale came from experiments, not from theory, which is why evaluation matters.

---

## Slide 21: Finding the best weights: parameter search

**Visual:** `images/tuning_search_tradeoff.png`

**On slide**
- Goal (stated first): `J = mean ln(slowdown / EASY's) + mean ln(max wait / EASY's)`, lower is better; J = 0 means "as good as EASY"
- Searched all 8 parameters: three weights, max_age, adaptation gain, reservation threshold, preemption on/off, margin
- Method: **random search** (160–240 candidates) + **two rounds of local refinement** around the best
- 620 candidates × 10 training windows = 6,200 simulations, run in parallel on the **college HPC** (PBS jobs)
- Training windows are separate from the 10 test windows (no overlap)

**Speaker notes:** This is systematic trial and error, also called black-box optimisation. Each
candidate is judged by simulating it. We ran two searches, one allowing preemption and one
without, because free preemption dominated the first. The scatter shows every candidate:
lower-left is better on both counts.

---

## Slide 22: Tuned weights and validation

**On slide** (table: recommended non-preemptive setting)

| age | short | size | max_age | gain | reservation_xf |
|---|---|---|---|---|---|
| 0.386 | 0.521 | 0.093 | 2.36 days | 0.24 | 1.0 (always reserve) |

**On slide** (held-out results, ratio to EASY, lower is better)

| setting | slowdown | max wait | avg wait |
|---|---|---|---|
| AMF defaults | 0.28 | 6.04 | 0.49 |
| SJF | 0.37 | 3.60 | 0.99 |
| **AMF tuned** | **0.31** | **1.09** | 0.72 |
| AMF tuned + preemption | 0.05 | 0.98 | 0.26 |

- Clearly learned: **always reserve**, age horizon ≈ **2 days**, small size weight
- Generalises: J = −1.19 on training windows, −1.07 on unseen windows
- Does **not** transfer to synthetic workloads with a different time scale

**Speaker notes:** AMF tuned keeps SJF-like slowdown with an EASY-like worst case. The preemptive
version looks even better, but only because preemption is free in our model. A real cluster pays
for every checkpoint and restart. The tuned max_age is in seconds, so it only suits workloads on a
similar time scale. The tuned values are available as a preset in the dashboard.

---

## Slide 23: The web dashboard

**Visual:** `images/dashboard_configure.png`, `images/dashboard_results.png`, `images/dashboard_gantt.png`
(optionally `dashboard_experiments.png`, `dashboard_jobs.png`)

**On slide**
- Configure: pick workloads (synthetic or real logs), CPU cores, policies and parameters, including **presets** (tuned weights)
- Run in the background with live progress; history, rerun with one click
- Results: metrics table + charts per workload; interactive Gantt; searchable job table
- Export CSV, JSON and charts
- Same engine and runner as the CLI → identical numbers (tested)

**Speaker notes:** Start it with `adaptivesched serve` and open http://127.0.0.1:8000. It is built
with standard-library Python and plain JavaScript (no frameworks, works offline). Scheduling logic
never runs in the browser, which only displays what the runner wrote.

---

## Slide 24: Testing and reproducibility

**On slide**
- **210 automated tests**: engine, policies, metrics (hand-computed), experiments, API, dashboard wiring
- Metric and policy tests computed **by hand first**, with the arithmetic in the test
- Byte-identical reruns (only timestamps differ); identical results on laptop and HPC
- Failed runs are reported, never hidden
- Every result file records: workload id, seed, policy and parameters, engine commit, config hash

**Speaker notes:** Reproducibility is what makes a comparison trustworthy. If someone doubts a
number, they can rerun the exact configuration and get the same file.

---

## Slide 25: Benefits and limitations

**On slide: Benefits / advantages**
- Fair comparison: same jobs, same cluster, one metric definition each
- AMF combines speed (shortness), fairness to old jobs (age) and packing (size), and adapts to queue state
- Tuned AMF: SJF-like slowdown with an EASY-like worst case on real logs
- Grounded in production practice (Slurm, Maui, EASY), deterministic and explainable
- Works without preemption; preemption is optional
- Reproducible, tested, usable through a dashboard

**On slide: Disadvantages / limitations**
- `max_age` depends on the workload's time scale: wrong values cause starvation
- Assumes exact runtimes; real users' estimates are often wrong
- Preemption is free in the model (no checkpoint cost), which flatters SRTF and preemptive AMF
- Only CPU cores are modelled (no memory, GPUs, network); one cluster
- Fairness only per job, since logs have no user-level fair-share data
- Tuned on five logs from 1996–2006; modern clusters may need retuning
- The weight split between age and adaptation is not uniquely determined

**Speaker notes:** Be honest: every scheduling study depends on its model. Name the biggest
caveats: runtime estimates and preemption cost.

---

## Slide 26: Conclusion and future work

**On slide**
- No single policy wins everywhere: there is always a trade-off between the typical job and the worst-off job
- A literature-grounded adaptive utility policy, **properly tuned**, reached a strong middle point on real logs
- Parameters must match the workload's time scale; evaluation on real data revealed this
- Future work: runtime estimates instead of exact runtimes · preemption cost · user-level fairness · modern traces · a scale-free age horizon · online (learning) adaptation

**Speaker notes:** End with the open question for the audience: should a cluster minimise the
average wait or protect the worst case? The answer depends on the users, and our tools let an
operator measure that choice before making it.

**Optional final slide:** "Thank you · Questions?" plus the repository link.

---

## References (for a final slide or the appendix)

1. SchedMD, *Slurm Multifactor Priority Plugin*, https://slurm.schedmd.com/priority_multifactor.html
2. D. Jackson, Q. Snell, M. Clement, "Core Algorithms of the Maui Scheduler", JSSPP 2001
3. W. Tang, Z. Lan, N. Desai, D. Buettner, "Fault-Aware, Utility-Based Job Scheduling on Blue Gene/P Systems", IEEE Cluster 2009
4. W. Tang, D. Ren, Z. Lan, N. Desai, "Adaptive Metric-Aware Job Scheduling for Production Supercomputers", ICPP Workshops 2012
5. S. Srinivasan, R. Kettimuthu, V. Subramani, P. Sadayappan, "Selective Reservation Strategies for Backfill Job Scheduling", JSSPP 2002
6. A. W. Mu'alem, D. G. Feitelson, "Utilization, Predictability, Workloads, and User Runtime Estimates in Scheduling the IBM SP2 with Backfilling", IEEE TPDS 2001
7. D. A. Lifka, "The ANL/IBM SP Scheduling System", JSSPP 1995
8. D. G. Feitelson, L. Rudolph, U. Schwiegelshohn, K. C. Sevcik, P. Wong, "Theory and Practice in Parallel Job Scheduling", JSSPP 1997
9. R. Jain, D. Chiu, W. Hawe, "A Quantitative Measure of Fairness and Discrimination for Resource Allocation in Shared Computer Systems", DEC TR-301, 1984
10. D. G. Feitelson, D. Tsafrir, D. Krakov, "Experience with Using the Parallel Workloads Archive", JPDC 2014
11. S. Russell, P. Norvig, *Artificial Intelligence: A Modern Approach* (agent types, PEAS)

## Source documents (for details)

`docs/ADAPTIVE_POLICY.md` (policy specification) · `docs/EVALUATION.md` (all results) ·
`docs/TUNING.md` (parameter search) · `docs/API.md` · `researcher/README.md` · `workloads/README.md`
