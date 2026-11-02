# Adaptive multi-heuristic scheduling policy: research and specification

**Policy:** Adaptive Multi-Factor priority (AMF), identifier `adaptive_multifactor`.
**Code:** `src/adaptive_scheduler/policies/adaptive_multifactor.py`.
**Tests:** `tests/test_adaptive_multifactor.py`.
**Evaluation:** `docs/EVALUATION.md`.
Written 2026-11-01 against `main` @ `daa589d` (preemption-capable engine).

This document is the implementation contract. A developer should be able to re-implement the
policy from §4–§6 alone and reproduce every decision the tests pin.

---

## 1. Problem statement and motivation

A cluster of `C` CPU cores receives rigid jobs, each with an arrival time, a known runtime and a
CPU-core requirement. The scheduler decides which waiting job starts next. The fixed rules
already in the simulator each optimise one thing and pay for it somewhere else:

| rule | what it optimises | what it costs (seen in our earlier study, `researcher/FINDINGS` F2–F5) |
|---|---|---|
| FIFO (wait-behind-head) | arrival order, predictability | idle CPU cores behind a blocked head job; highest average wait |
| SJF | average waiting time | long jobs overtaken repeatedly: max wait 1.8–6.9× FIFO's |
| EASY backfilling | utilisation without delaying the head job | arrival order is kept, so short jobs still queue behind long ones |
| SRTF (preemptive) | average waiting time, again | long jobs suspended again and again |

No fixed rule is right for every workload, and the operator's priorities differ (mean response
or worst case). The researcher brief asks for **one policy that combines several heuristics in a
documented utility function, adapts to the workload's state, has tunable parameters, is
deterministic, and uses only the read-only `SchedulerContext`**. It must also work with both
non-preemptive and preemptive execution. The brief explicitly rules out an arbitrary weighted
formula with no grounding in existing practice, and any claim of machine learning.

## 2. Literature review

**Production priority schedulers: weighted sums of normalised factors.**
The Maui scheduler [2] computes a job's priority as a weighted sum of components: queue time,
expansion factor (XFactor), requested resources, fair share, and others. It combines this with
backfilling. Slurm's *multifactor priority* plugin [1] normalises every factor to [0, 1] and
sums them with integer weights. The factors are age, job size, fair share, partition, QOS and
others. The age factor grows with queue time and **saturates at 1.0 after `PriorityMaxAge`**.
Job size can favour small or large jobs. Normalising first is what keeps the weights
interpretable: a weight is the largest share of priority that factor can contribute.

**Utility functions from the research literature.**
Tang et al. [3] formalise scheduling as ranking by a utility function and evaluate it on Blue
Gene/P traces. One of those utilities is the WFP family used in Argonne's Cobalt scheduler,
which grows with (wait / requested time)^k × job size, so long-waiting, wide jobs rise.
Carastan-Santos and de Camargo [10] instead obtain priority functions by simulation-driven
regression over job features. Their functions perform well, but they are learned offline.

**Adaptation.** Tang et al.'s *adaptive metric-aware* scheduling [4] monitors the system's
current state, for example queue depth and accumulated wait. It shifts a balance factor between
an efficiency-oriented ordering and a fairness-oriented one at run time, so the scheduler favours
throughput when the queue is healthy and protects old jobs when it is not. A journal extension
[11] reports sustained improvements on production traces.

**Reservations and backfilling.** EASY backfilling [7, 6] gives the head job a reservation at
the earliest time enough cores will be free. Any other job may start only if it does not delay
that reservation. Srinivasan et al. [5] show that reserving for *every* blocked head job is
unnecessary. Their **selective reservation** grants a reservation only once a job's expansion
factor (wait + runtime) / runtime crosses a threshold. This keeps most of aggressive
backfilling's packing while bounding how long any job can be passed over.

**Metrics.** Bounded slowdown with a runtime threshold τ [8] keeps very short jobs from
dominating mean slowdown. Jain's index [9] is the standard scalar for how evenly a quantity is
shared.

## 3. Candidates and the choice

| candidate | multi-heuristic | documented utility | adapts | implementable on `SchedulerContext` | reason not chosen / chosen |
|---|---|---|---|---|---|
| WFP utility [3] | wait, runtime, size in one product | yes | no (static exponent) | yes | no adaptation; the product makes the weights hard to read |
| Adaptive metric-aware [4] | two orderings | yes | yes (balance factor) | needs metric thresholds tuned on production traces we do not have | its *idea* (shift weight with queue state) is kept |
| Learned priority functions [10] | yes | a fitted formula | no (fixed after training) | yes | offline machine learning; the brief excludes ML that is not really implemented |
| Team `adaptive` policy | wait, runtime, cores | yes | yes | yes | raw time units are mixed in one sum (wait in time units minus runtime minus 0.1·cores), so a weight has no fixed meaning; no reservation, so a wide job can be passed over indefinitely |
| **AMF (chosen)** | age, shortness, size | yes, normalised | yes | yes | combines the production structure of [1, 2], the adaptation idea of [4] and the reservation rule of [5] |

AMF is chosen because each part has a clear source and a role you can test:
- the factor structure is Slurm/Maui's: normalised factors, weights that are shares;
- the adaptation is Tang et al.'s idea, made concrete with a signal that exists in the context
  (the mean normalised age of the queue);
- starvation is bounded by selective reservation [5] instead of hoping age eventually wins;
- preemption is optional (off by default), so the policy runs under both execution semantics.

AMF is a deterministic hand-designed rule. **It does not learn**: nothing is fitted to data, and
its parameters change only when an experimenter changes them.

## 4. Mathematical formulation

Notation at decision time `t`. `Q` is the set of waiting jobs (including jobs suspended by
preemption) and `R` the set of running jobs. `C` is the cluster's CPU cores and `F` the free
CPU cores. For job `j`: `a_j` arrival, `p_j` runtime, `c_j` CPU cores, and
`r_j` its remaining runtime: `p_j` for a job never started; the `WaitingJobView.remaining_runtime`
of a suspended job; `expected_finish_time − t` for a running one.

**Time waited so far** (every waiting interval, not just the first):

    w_j = (t − a_j) − (p_j − r_j)

**Factors**, each in [0, 1]:

    A_j = min(1, w_j / max_age)                           age (Slurm PriorityMaxAge)
    S_j = 1 − ln(1 + r_j) / ln(1 + r_max)                 shortness, r_max = max over Q ∪ R of r_k
    N_j = (C − c_j + 1) / C                               narrowness (favours small jobs)

The logarithm keeps one very long job from flattening every other job's shortness to ≈ 1.
`r_max ≥ 1`, so the denominator is at least ln 2 > 0. `r_max` is taken over waiting *and*
running jobs, so a running job and a waiting job are scored on one scale, which the preemption
rule needs.

**Base weights** `(w_A, w_S, w_N)` are non-negative and normalised to sum to 1.

**Adaptation.** The queue's age pressure is

    σ(t) = (1/|Q|) Σ_{j∈Q} A_j        ∈ [0, 1]   (0 if Q is empty)

and with the adaptation gain `g ∈ [0, 1]` the weights used at `t` are

    W_A(t) = w_A + g·σ(t)·(w_S + w_N)
    W_S(t) = w_S · (1 − g·σ(t))
    W_N(t) = w_N · (1 − g·σ(t))

They still sum to 1. With `g = 0` the policy is a static multifactor priority. With `g = 1` and
every queued job past `max_age`, all weight is on age (the order becomes arrival order).

**Utility:**

    U_j(t) = W_A(t)·A_j + W_S(t)·S_j + W_N(t)·N_j

## 5. Decision rules

**Ranking.** Waiting jobs are sorted by `(−U_j, a_j, job_id)`, so higher utility comes first,
then earlier arrival. Job ids order deterministically: integers numerically, then strings, as
in the engine's `make_job_sort_key`.

**`select_next_job(context)`** (the engine calls it repeatedly at one timestamp until it returns
`None` or the cores run out):
1. If `Q` is empty, return `None`.
2. Let `top` be the first job in the ranking. If `c_top ≤ F`, return `top`.
3. Compute `top`'s expansion factor `XF = (w_top + r_top) / r_top`.
   - If `XF ≥ reservation_xf`: `top` holds a reservation at
     `shadow = context.earliest_available_time(c_top)`. Return the first job `k` after `top` in
     ranking order with `c_k ≤ F` and `t + r_k ≤ shadow`, or `None` if none qualifies.
   - Otherwise: return the first job `k` after `top` in ranking order with `c_k ≤ F`, or `None`.

A reservation is re-derived at every call from the running jobs' expected finish times. Nothing
is stored between calls, so the policy is stateless.

**`select_jobs_to_preempt(context)`** (the engine calls it once per event timestamp before
dispatch; a no-op unless `preemptive=True`):
1. If `Q` or `R` is empty, return `()`.
2. Let `top` be the first job in the ranking. If `c_top ≤ F`, return `()`: nothing needs freeing.
3. Victims are running jobs `v` with `start_v < t` (the engine forbids suspending a job in the
   instant it started), `r_v > 0`, and `U_top − U_v > preempt_margin`. Utilities are computed
   with the same weights and `r_max`.
4. Order victims by `(U_v, −start_v, job_id)`: lowest utility first, then the most recently
   started (least work lost). Take victims in order until they free at least `c_top − F` CPU cores.
   If the victims cannot free that many, return `()`. A useless partial preemption is never made.

After a preemption, `top` is the highest-utility waiting job and now fits, so the dispatch that
follows starts it first.

**Dispatch semantics, in the words SCH §6.1 asks for:** AMF does *not* wait behind a preferred
job that cannot fit, unless that job has earned a reservation (XF ≥ `reservation_xf`). Then it
waits only for jobs that would delay the reservation.

## 6. Parameters and defaults

| parameter | meaning | range | default | why this default |
|---|---|---|---|---|
| `age_weight` (w_A) | base share of age | ≥ 0 | 0.4 | equal to shortness: neither dominates when the queue is young |
| `short_weight` (w_S) | base share of shortness | ≥ 0 | 0.4 | as above |
| `size_weight` (w_N) | base share of narrowness | ≥ 0 | 0.2 | packing is a secondary concern |
| `max_age` | wait at which A saturates (time units) | > 0 | 500 | ≈ 8× the 60-unit median runtime of our synthetic workloads. **Must be set to the workload's waiting-time scale**: see EVALUATION §5 |
| `adaptation_gain` (g) | how far age pressure moves weight to age | [0, 1] | 0.5 | half of the movable weight at full pressure |
| `reservation_xf` | expansion factor that earns a reservation | ≥ 1 or ∞ | 2.0 | a job reserves once it has waited as long as it will run. 1 = always reserve (EASY on the utility order), ∞ = never |
| `preemptive` | enable priority preemption | bool | `false` | non-preemptive by default, matching the engine's base model |
| `preempt_margin` | utility gap required to preempt | [0, 1] | 0.1 | hysteresis: no ping-pong between near-equal jobs |

Invalid values raise `ConfigurationError` at construction (negative weights, all weights zero,
`max_age ≤ 0` or infinite, `g` outside [0, 1], `reservation_xf < 1`, non-boolean `preemptive`,
NaN, booleans passed as numbers).

**Tuned values** (`docs/TUNING.md`). A black-box search over all eight parameters, run on
real production logs and validated on held-out windows, recommends the following for workloads
measured in seconds with waits of hours (no preemption): `age_weight` .386, `short_weight` .521,
`size_weight` .093, `max_age` 203,692 s (2.36 days), `adaptation_gain` .24, `reservation_xf` 1.0.
On the held-out logs this gives 0.31× EASY's bounded slowdown at 1.09× its max wait. The class
defaults above are not changed: they suit the synthetic workloads' time scale better, and the
tuned `max_age` does not transfer to it.

## 7. Worked example (pinned by `test_utility_hand_computed`)

8 CPU cores, `t = 10`. Job 1 (`a = 0, p = 9, c = 2`) and job 2 (`a = 10, p = 1, c = 8`).
Ages: `10/500 = .02` and `0`, so `σ = .01` and `g·σ = .005`, giving
`W = (.403, .398, .199)`. `r_max = 9`. Shortness: `S_1 = 0` and `S_2 = 1 − ln2/ln10 = .69897`.
Narrowness: `N_1 = 7/8` and `N_2 = 1/8`.
`U_1 = .403·.02 + .199·.875 = .182185`; `U_2 = .398·.69897 + .199·.125 = .303065`.
Job 2 ranks first, and job 1 starts only if job 2 does not fit.

The other tests pin further cases: adaptation flipping a decision, the reservation holding and
releasing, preemption choosing victims or declining, and resumed jobs ranked by remaining
runtime.

## 8. Computational complexity

With `n = |Q|` and `m = |R|`, one `select_next_job` call costs:
`O(n + m)` for the factors and `r_max`, `O(n log n)` for the ranking, and `O(m log m)` for
`earliest_available_time` when a reservation is checked: `O((n + m) log(n + m))` in total.
`select_jobs_to_preempt` costs the same plus `O(m log m)` to order victims. A dispatch pass that
starts `k` jobs costs `O(k (n + m) log(n + m))`. Memory is `O(n + m)` per call, and nothing is
kept between calls. On the study workloads (300 jobs, 16 CPU cores) a whole simulation takes
well under a second.

## 9. Assumptions, limitations and failure cases

1. **Exact runtimes.** Shortness, the expansion factor and the reservation test all read
   `runtime`, which this simulator knows exactly (`runtime_estimate_error = 0`). Real user
   estimates are often far off [6], and every runtime-based rule here would be affected.
2. **`max_age` is absolute.** Once every old job has waited past `max_age`, age no longer
   separates them, and shortness and narrowness decide among them. On workloads whose waits run
   into the thousands, the default 500 lets long, wide jobs be overtaken repeatedly. The
   evaluation measures this (EVALUATION §5): max wait drops 47–74% on `mixed` and `wide_jobs`
   when `max_age` is 5000. Slurm's `PriorityMaxAge` has the same property. Choose `max_age`
   from the workload's waiting-time scale.
3. **Reservation only for the top job, and only past the XF threshold.** As in EASY, a blocked
   job that is not top-ranked has no protection. With the default `max_age`, such a job can stay
   below the top on congested workloads.
4. **No user-level fair share.** The workload has no user field, so Slurm's fair-share factor
   has no input. Fairness is measured at job level only.
5. **Preemption is free in the model**: zero context-switch, checkpoint or migration cost
   (engine README §4). A real system would make each preemption cost time, and the margin would
   need retuning. Only the top-ranked job can trigger preemption.
6. **The adaptation signal is the mean normalised age.** One very old job among many fresh ones
   moves σ only a little, so adaptation responds to *widespread* waiting, not to one starving job.
7. **Floating point.** Utilities are float sums. Ties in `U` fall to arrival time and job id, and
   the same input always produces the same ordering (no randomness, no clock).

## 10. Interface: no engine change needed

AMF uses only `SchedulerContext` fields that exist at `daa589d`: `current_time`, `total_cores`,
`available_cores`, `waiting_jobs`, `waiting_job_views` (remaining runtime of suspended jobs),
`running_jobs` (`start_time`, `expected_finish_time`) and `earliest_available_time`. It
implements `select_next_job`, plus the optional `select_jobs_to_preempt` from
`PreemptiveSchedulingPolicy`. It is registered by module discovery under the stable id
`adaptive_multifactor`. `policies.policy_ids()` (added in this phase) lists one id per policy,
without discovery's class-name aliases. The team CLI offers it as `adaptive-multifactor` and
`adaptive-multifactor-preemptive`.

## References

1. SchedMD. *Multifactor Priority Plugin*. Slurm documentation.
   https://slurm.schedmd.com/priority_multifactor.html (checked 2026-11-01).
2. D. Jackson, Q. Snell, M. Clement. "Core Algorithms of the Maui Scheduler." *JSSPP 2001*,
   LNCS 2221, Springer.
3. W. Tang, Z. Lan, N. Desai, D. Buettner. "Fault-Aware, Utility-Based Job Scheduling on Blue
   Gene/P Systems." *IEEE Cluster 2009*.
4. W. Tang, D. Ren, Z. Lan, N. Desai. "Adaptive Metric-Aware Job Scheduling for Production
   Supercomputers." *5th Intl. Workshop on Parallel Programming Models and Systems Software for
   High-End Computing (P2S2), with ICPP 2012*. (Listing checked 2026-11-01.)
5. S. Srinivasan, R. Kettimuthu, V. Subramani, P. Sadayappan. "Selective Reservation Strategies
   for Backfill Job Scheduling." *JSSPP 2002*, LNCS 2537, pp. 55–71.
   doi:10.1007/3-540-36180-4_4 (checked 2026-11-01).
6. A. W. Mu'alem, D. G. Feitelson. "Utilization, Predictability, Workloads, and User Runtime
   Estimates in Scheduling the IBM SP2 with Backfilling." *IEEE TPDS* 12(6), 2001.
7. D. A. Lifka. "The ANL/IBM SP Scheduling System." *JSSPP 1995*, LNCS 949.
8. D. G. Feitelson, L. Rudolph, U. Schwiegelshohn, K. C. Sevcik, P. Wong. "Theory and Practice
   in Parallel Job Scheduling." *JSSPP 1997*, LNCS 1291.
9. R. Jain, D. Chiu, W. Hawe. "A Quantitative Measure of Fairness and Discrimination for
   Resource Allocation in Shared Computer Systems." DEC Research Report TR-301, 1984.
10. D. Carastan-Santos, R. Y. de Camargo. "Obtaining Dynamic Scheduling Policies with Simulation
    and Machine Learning." *SC17*, 2017.
11. W. Tang et al. "Toward Balanced and Sustainable Job Scheduling for Production
    Supercomputers." *Parallel Computing*, 2013. (Existence checked 2026-11-01; author list not
    confirmed.)

References 1, 4 and 5 were checked against their index pages on 2026-11-01. The others are
standard citations in the job-scheduling literature, but their page numbers and venues should be
confirmed against the publisher's record before formal citation.
