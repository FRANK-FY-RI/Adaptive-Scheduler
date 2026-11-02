# Tuning the adaptive multi-factor policy's weights

Written 2026-11-01. This document finds the parameters of `adaptive_multifactor` (AMF,
`docs/ADAPTIVE_POLICY.md`) that work best on real HPC workloads, and checks them on data the
search never saw. Every number here can be regenerated from the commands in §7. All searches and
validation runs were executed on the college HPC (PBS jobs 28221, 28222, 28223).

## 1. What "optimal" means here

There is no single best schedule: one that is best for the typical job is worse for the
worst-off job (`docs/EVALUATION.md`). So the objective is stated first, and everything below is
optimal **with respect to it**:

    J = mean_w ln(bsld_w / bsld_w^EASY) + mean_w ln(maxwait_w / maxwait_w^EASY)

- *bsld* is mean bounded slowdown (τ = 10 s), the standard measure of what a typical job pays
  (Feitelson et al. 1997).
- *maxwait* is the longest any job waited: what the worst-off job pays.
- Both are divided by EASY backfilling's value on the same window. EASY is the production standard,
  and on our real logs it had the best worst case (EVALUATION R3). The ratios make windows from a
  100-CPU and a 1,152-CPU machine comparable.
- The logarithm weights a halving and a doubling equally. J = 0 means "as good as EASY", and J < 0
  means better overall. J = −1 means, for example, both ratios at e^−0.5 ≈ 0.61.
- Average wait, fairness and preemptions per job were recorded for every candidate too
  (`candidates.csv`), so anyone who prefers another objective can re-rank without rerunning.

## 2. Data: training and held-out windows

| set | windows | used for |
|---|---|---|
| training | 10 windows of 2,000 consecutive jobs: each of the five real logs at 10% and 75% of its length (`workloads/pwa/train/`) | the search only |
| held-out | the 10 real 5,000-job windows of EVALUATION §9 (centred and first-quarter) | validation only; they do not overlap the training windows |
| transfer | the 15 synthetic workload ids of the study (`batch_study.yaml`) | validation only |

Each window runs at its machine's own size (100–1,152 CPUs), with real arrival times, runtimes
and widths.

## 3. Search space and method

| parameter | range searched | scale |
|---|---|---|
| age, short, size weights | the whole simplex (sum 1) | Dirichlet(1,1,1) |
| `max_age` | 60 s – 30 days | log-uniform |
| `adaptation_gain` | 0 – 1 | uniform |
| `reservation_xf` | 1 – 16, or ∞ (never reserve) with probability 0.15 | log-uniform |
| `preemptive` | on / off | coin flip (search 1), fixed off (search 2) |
| `preempt_margin` | 0 – 0.5 | uniform |

**Method: black-box optimisation**, implemented in `researcher/adaptivesched/experiments/tune.py`
and tested in `tests/test_tune.py`. It is not machine learning: nothing is fitted to data.
1. **Random search**: N candidates sampled from the space (seeded), each simulated on all 10
   training windows.
2. **Local refinement, two rounds**: the 6 best candidates are each perturbed 12 times (weights in
   log space, `max_age` and `reservation_xf` on a log scale, step 0.5), then the 3 best of
   everything are perturbed 12 times with step 0.2.
3. The defaults and `amf_age7d` are scored alongside as references.

| search | preemption | seed | candidates | simulations | wall time (8 CPUs) |
|---|---|---|---|---|---|
| 1 | searched | 2026 | 160 random + 2 reference + 72 + 36 = 270 | 2,710 | 5.5 min |
| 2 | fixed off | 2027 | 240 random + 2 reference + 72 + 36 = 350 | 3,510 | 4.5 min |

Search 2 exists because search 1's objective is dominated by preemption. With free preemption,
slowdown falls to about 1/25 of EASY's, against about 1/3 without (§4), so search 1's refinement
spent its budget on preemptive candidates. The
non-preemptive policy is the one a real cluster could adopt without a checkpointing system, so it
got its own search.

![every candidate](../researcher/results/tuning/search_tradeoff.png)

## 4. Results on the training windows

| candidate | age | short | size | max_age | gain | reservation_xf | preempt | J | bsld × | max wait × | avg wait × |
|---|---|---|---|---|---|---|---|---|---|---|---|
| defaults | .40 | .40 | .20 | 500 s | .50 | 2.0 | no | −0.09 | 0.31 | 2.97 | 0.49 |
| amf_age7d | .40 | .40 | .20 | 7 d | .50 | 2.0 | no | −0.68 | 0.33 | 1.52 | 0.54 |
| **amf_tuned** (best of search 2) | **.386** | **.521** | **.093** | **2.36 d** (203,692 s) | **.24** | **1.0** | no | **−1.19** | 0.32 | 0.96 | 0.68 |
| **amf_tuned_preemptive** (best of search 1) | .687 | .297 | .017 | 11.4 d (984,900 s) | .715 | ∞ | yes, margin .0006 | −3.32 | 0.043 | 0.84 | 0.28 |

(× = geometric mean over windows of the ratio to EASY backfilling.)

**What the search says about each parameter.** These are the ranges among the 10 best
non-preemptive candidates of search 2:

| parameter | top-10 range | reading |
|---|---|---|
| `reservation_xf` | 1.00–1.20 | **clearly determined**: always reserve for the top job (EASY on the utility order). The default 2.0 left blocked jobs unprotected for too long |
| `max_age` | 1.7–3.2 days | **clearly determined**: on these logs, with waits of hours, age should keep growing for about two days. 500 s (default) saturates at once; 7 days is too slow |
| size weight | 0.07–0.11 | **determined**: a little preference for narrow jobs; the default 0.2 is too much |
| short weight | 0.48–0.83 | loosely determined |
| age weight | 0.10–0.44 | loosely determined; trades off with the gain |
| `adaptation_gain` | 0.24–0.95 | loosely determined. A low age weight with a high gain and a high age weight with a low gain both give age a similar share once the queue has aged |

The search therefore pins down the *structure* (always reserve, ~2-day age horizon, small size
weight), but not the exact split between base age weight and adaptation. Several settings within
those ranges are equally good on the training windows.

## 5. Validation on unseen data

**Held-out real windows (10 × 5,000 jobs, never seen by the search):**

| strategy | J | bsld × | max wait × | avg wait × | windows better than EASY on bsld / max wait |
|---|---|---|---|---|---|
| easy_backfill | 0 | 1 | 1 | 1 | – |
| sjf | +0.28 | 0.37 | 3.60 | 0.99 | 10 / 0 |
| srtf (preemptive) | −2.10 | 0.042 | 2.94 | 0.18 | 10 / 0 |
| adaptive (team) | +1.28 | 0.84 | 4.29 | 0.55 | 6 / 0 |
| AMF defaults | +0.53 | 0.28 | 6.04 | 0.49 | 10 / 0 |
| amf_age7d | −0.68 | 0.32 | 1.60 | 0.52 | 10 / 0 |
| **amf_tuned** | **−1.07** | 0.31 | **1.09** | 0.72 | **10 / 5** |
| **amf_tuned_preemptive** | **−3.11** | 0.046 | 0.98 | 0.26 | 10 / 6 |

- **The tuned parameters generalise.** J went from −1.19 on training to −1.07 on held-out windows
  for `amf_tuned`, and from −3.32 to −3.11 for the preemptive one. The search did not overfit its
  2,000-job windows.
- **amf_tuned keeps SJF-like slowdown with EASY-like worst case.** Its slowdown is 0.31× EASY's in
  every window, and its max wait is 1.09× EASY's on average (better than EASY in 5 of 10 windows,
  worst 1.78× on HPC2N). For comparison, sjf's max wait is 3.60× and the defaults' 6.04×.
- **The price of amf_tuned is average wait.** Its 0.72× EASY's is higher than the defaults'
  0.49×: the always-on reservation keeps some short jobs waiting so that blocked wide jobs are
  protected.
- **amf_tuned_preemptive is the only policy better than EASY on all three aggregates** (slowdown
  0.046×, max wait 0.98×, average wait 0.26×), at 0.5–2.5 preemptions per job, each costing
  nothing in this model.

Per held-out window (bsld × / max wait × EASY):

| window | amf_tuned | amf_tuned_preemptive | amf_age7d |
|---|---|---|---|
| KTH SP2 | 0.23 / 0.83 | 0.01 / 0.61 | 0.30 / 2.38 |
| KTH SP2 q1 | 0.33 / 1.00 | 0.01 / 0.75 | 0.28 / 1.47 |
| SDSC SP2 | 0.54 / 1.06 | 0.03 / 0.79 | 0.43 / 1.33 |
| SDSC SP2 q1 | 0.27 / 1.17 | 0.02 / 0.88 | 0.33 / 1.35 |
| HPC2N | 0.23 / 1.78 | 0.07 / 1.85 | 0.27 / 1.58 |
| HPC2N q1 | 0.33 / 0.93 | 0.08 / 1.32 | 0.29 / 1.10 |
| CTC SP2 | 0.26 / 0.91 | 0.05 / 1.06 | 0.23 / 2.10 |
| CTC SP2 q1 | 0.26 / 1.17 | 0.06 / 0.85 | 0.22 / 1.95 |
| SDSC Blue | 0.37 / 1.41 | 0.12 / 1.22 | 0.49 / 1.87 |
| SDSC Blue q1 | 0.44 / 0.94 | 0.17 / 0.98 | 0.44 / 1.32 |

**Transfer to the synthetic study (15 workload ids): the tuned parameters do not transfer.**

| condition | amf_tuned bsld / max / avg × EASY | defaults bsld / max / avg × EASY |
|---|---|---|
| light | 0.97 / 1.23 / 0.73 | 0.97 / 1.18 / 0.70 |
| heavy | 0.48 / **4.79** / 0.54 | 0.84 / 1.05 / 0.87 |
| short_heavy | 0.40 / 1.14 / 0.44 | 0.65 / 0.98 / 0.66 |
| mixed | 0.20 / 2.95 / 0.37 | 0.42 / 2.49 / 0.55 |
| wide_jobs | 0.30 / 3.18 / 0.59 | 0.49 / 2.91 / 0.71 |

`max_age` is in time units. Tuned on logs measured in seconds with waits of hours, a 2.36-day
horizon (203,692 units) never fills on synthetic workloads, whose waits are tens to thousands of
units. Age then counts for almost nothing, the policy becomes shortness-first, and the worst case
degrades (heavy: 4.79× EASY's max wait). The defaults, whose `max_age` = 500 happens to suit that
scale, do better there. **The tuned weights are specific to workloads on the scale of the training
logs.**

## 6. Recommendation

For real HPC-like workloads (times in seconds, waits of hours), without preemption:

```yaml
adaptive_multifactor: {age_weight: 0.386, short_weight: 0.521, size_weight: 0.093, max_age: 203692,
                       adaptation_gain: 0.24, reservation_xf: 1.0, preemptive: false}
```

If the cluster can checkpoint and preempt cheaply, and only then:

```yaml
adaptive_multifactor: {age_weight: 0.687, short_weight: 0.2965, size_weight: 0.0166, max_age: 984900,
                       adaptation_gain: 0.715, reservation_xf: .inf, preemptive: true, preempt_margin: 0.0006}
```

On workloads with a different time scale, keep the structure the search found (always reserve, a
small size weight) and set `max_age` to roughly the time a job should be allowed to wait before
it outranks any shorter job. Here that was ~2 days for waits of hours. The class defaults are
unchanged: they are the documented specification pinned by hand-computed tests, and on the
synthetic scale they are the better choice (§5).

## 7. Reproduce

```sh
cd researcher
adaptivesched tune --windows "../workloads/pwa/train/*.csv" --trials 160 --seed 2026 --out results/tuning
adaptivesched tune --windows "../workloads/pwa/train/*.csv" --trials 240 --seed 2027 --preemptive off --out results/tuning_np
for c in examples/tuned/*.yaml; do adaptivesched batch --config $c; done      # validation
```

`results/tuning*/candidates.csv` holds every candidate with its parameters and scores, and
`result.json` holds the best, the Pareto set and the per-window EASY baseline. The same seed gives
the same candidates and scores on any machine: the 60 runs shared between the laptop and the HPC
produced identical metrics. On the HPC, the PBS scripts are `tune.pbs`, `tune_np.pbs` and
`validate.pbs` in `~/adaptivesched-m0/next/`.

## 8. Limits

- **Free preemption.** The preemptive optimum relies on 0.5–2.5 suspensions per job costing
  nothing. Any real checkpoint or restart cost would change both the optimum and its advantage.
- **Exact runtimes.** Shortness, reservations and expansion factors all read the true runtime. Real
  schedulers see users' estimates (SWF field 9), which are often far off.
- **One objective.** A different trade-off between typical and worst case, or average wait instead
  of slowdown, gives a different optimum. `candidates.csv` allows re-ranking, and the Pareto set is
  in `result.json`.
- **Search budget.** 620 candidates in 8 dimensions do not prove a global optimum. The top
  candidates agree on the structure (§4), but the split between age weight and adaptation gain is
  not resolved.
- **Five machines, 1996–2006.** Modern clusters, with many-core nodes, GPUs and Slurm's fair share,
  could favour different weights.
