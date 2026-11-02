# Evaluation: the adaptive multi-factor policy against the existing policies

Written 2026-11-01. Every number traces to two batches written by `adaptivesched batch`:

- **Study batch**: `researcher/examples/batch_study.yaml` → `researcher/results/batch_5f4bccb5ca39/`
  (`compare.md`, `findings_skeleton.md` with run ids, `plots/`).
- **Ablation batch**: `researcher/examples/batch_amf_ablation.yaml` → `researcher/results/batch_ab26da2b7812/`.

Rerunning either config writes the same directory, and every file is byte-identical except
`timestamp` fields (`researcher/tests/test_batch.py` checks this). The policy is specified in
`docs/ADAPTIVE_POLICY.md`.

## 1. Methodology

Each policy runs on the same workload and the same 16-CPU-core cluster through the same engine
(`adaptive-scheduler 0.1.0@daa589d0cffc+dirty`; the `+dirty` marks this phase's uncommitted
policy code). Any difference in outcome is therefore caused by the policy. Metrics come from one
definition each (`researcher/adaptivesched/metrics/definitions.py`, hand-computed tests):

| metric | definition |
|---|---|
| waiting time | finish − arrival − runtime (all waiting intervals; = start − arrival if never preempted) |
| turnaround time | finish − arrival |
| makespan | latest finish − earliest arrival |
| CPU utilization | 100 × Σ cores × runtime / (cluster cores × makespan) |
| bounded slowdown | mean of max(1, turnaround / max(runtime, τ)), τ = 10 |
| fairness | Jain's index over per-job bounded slowdowns (1 = every job slowed equally) |
| throughput | completed jobs / makespan |

Strategies are compared only within one workload id (one seed), and values are never averaged
across seeds. "X–Y" below is the range over seeds 7, 11 and 13. "Led" means the best value in
that seed, and a tie is not a lead.

## 2. Workloads and configurations

Five synthetic conditions, 300 jobs each, generated from seeds 7, 11 and 13 (15 workload ids):

| condition | arrivals | runtimes | CPU cores per job | stresses |
|---|---|---|---|---|
| light | offered load 0.5 | lognormal, median 60, σ 0.5 | 1–25% | an uncongested cluster |
| heavy | offered load 1.0 | as light | 1–25% | congestion |
| short_heavy | 1.0 | 90% 5–30, 10% 600–3000 | 1–12.5% | short jobs behind long ones |
| mixed | 1.0 | lognormal σ 1.5 | 1–60% | spread in both dimensions |
| wide_jobs | 1.0 | lognormal σ 0.5 | 50–100% | blocking on CPU cores |

Eight strategy configurations ran on every workload, 120 runs with 0 failed:

| label | policy | execution | notes |
|---|---|---|---|
| fifo, sjf | team baselines | non-preemptive | wait-behind-head |
| easy_backfill | team | non-preemptive | EASY reservation for the head job |
| srtf | team | **preemptive** | shortest remaining runtime |
| adaptive | team `AdaptivePolicy` | non-preemptive | `base_wait_weight` 0.1, first-fit |
| adaptive_multifactor | **AMF**, defaults | non-preemptive | weights .4/.4/.2, max_age 500, gain .5, XF 2 |
| amf_preemptive | AMF | **preemptive** | `preemptive: true`, margin 0.1 |
| amf_fixed | AMF | non-preemptive | `adaptation_gain: 0` (control for adaptation) |

## 3. Results

Average and max waiting time (range over three seeds):

| condition | fifo | sjf | easy_backfill | srtf | adaptive | AMF | amf_preemptive | amf_fixed |
|---|---|---|---|---|---|---|---|---|
| light, avg | 3.9–5.0 | 3.0–3.7 | 3.7–5.0 | 2.6–3.1 | 2.8–3.3 | 2.8–3.3 | 2.7–3.3 | 2.8–3.3 |
| light, max | 67–81 | 62–113 | 67–81 | 113–133 | 62–114 | 62–106 | 60–106 | 62–109 |
| heavy, avg | 100–215 | 60–112 | 89–202 | 32–75 | 49–123 | 78–173 | 70–176 | 69–168 |
| heavy, max | 234–581 | 1621–2224 | 215–545 | 1639–2077 | 395–596 | 258–532 | 246–532 | 267–510 |
| short_heavy, avg | 148–374 | 51–104 | 77–224 | 15–20 | 49–95 | 55–113 | 30–94 | 50–91 |
| short_heavy, max | 944–1804 | 986–1834 | 931–1736 | 1048–1636 | 1234–1744 | 992–1517 | 616–1312 | 1210–1976 |
| mixed, avg | 1573–3422 | 349–531 | 552–1486 | 113–201 | 459–1203 | 373–658 | 318–447 | 313–457 |
| mixed, max | 4815–6887 | 9635–12296 | 2989–4437 | 6926–10515 | 2702–5650 | 6683–11074 | 7634–10773 | 7992–10785 |
| wide_jobs, avg | 2270–3079 | 1276–1628 | 2123–2709 | 1144–1433 | 2035–2571 | 1510–1926 | 1510–1926 | 1516–1870 |
| wide_jobs, max | 5367–6165 | 15539–18230 | 4386–5595 | 15347–17717 | 4354–5438 | 10996–18517 | 10996–18517 | 11021–18448 |

CPU utilization under congestion (heavy / mixed / wide_jobs): easy_backfill 87.8–92.8 /
83.1–86.3 / 77.3–78.3; adaptive 89.3–94.0 / 82.4–86.9 / 78.0–79.0; AMF 88.3–91.6 / 78.4–78.5 /
75.2–77.6; sjf 86.0–90.6 / 67.5–73.8 / 73.7–76.8. Preemptions per run: srtf 38–420, amf_preemptive
0–128 (most on short_heavy: 48–128). Full tables, including fairness, slowdown, throughput and
makespan: `compare.md`. Plots: `plots/grid_<metric>.png`, `tradeoff_avg_vs_max_wait.png`,
`cdf_*.png`, and the Gantt pairs `gantt_*_srtf_vs_amf_preemptive.png` and
`gantt_*_fifo_vs_adaptive_multifactor.png`.

## 4. Findings

Each finding states an observation with numbers, the trade-off, an interpretation and a
confidence note; no policy is called best. Run ids for every workload id are in `findings_skeleton.md`.

**E1: srtf has the lowest average waiting time everywhere, and pays for it with preemptions.**
Observation: srtf had the lowest average wait in all 15 workload ids, e.g. short_heavy 15–20 vs
fifo 148–374, mixed 113–201 vs sjf 349–531. Trade-off: 38–420 preemptions per run; max wait
1639–2077 on heavy (fifo 234–581) and 15347–17717 on wide_jobs (easy_backfill 4386–5595).
Interpretation: suspending long jobs whenever a shorter one arrives is the strongest rule for the
average, and it reproduces SJF's starvation of long jobs. In this model preemption costs nothing.
Confidence: all seeds agree; any real checkpoint or context-switch cost would cut into this lead.

**E2: AMF lowers average wait against the arrival-order policies on every congested condition.**
Observation: against easy_backfill, AMF's average wait is lower in 15 of 15 workload ids
(heavy −12 to −14%, short_heavy −19 to −50%, mixed −27 to −67%, wide_jobs −28 to −29%). Against
fifo it is lower in 15 of 15 (−19 to −86%). Trade-off: see E3. Interpretation: the shortness and
narrowness factors do what SJF does, but less aggressively: AMF's average wait is above sjf's on
heavy (+30 to +81%), mixed (+7 to +41%) and wide_jobs (+18 to +24%). Confidence: the direction
holds in every seed.

**E3: AMF's max wait depends on the workload's waiting-time scale. It holds on heavy and fails
on mixed and wide_jobs.** Observation: on heavy, AMF's max wait (258–532) is close to
easy_backfill's (215–545) and 76–84% below sjf's. On mixed and wide_jobs it is 2.2–4.2×
easy_backfill's (mixed 6683–11074 vs 2989–4437; wide_jobs 10996–18517 vs 4386–5595). On
wide_jobs seed 13 it is as high as sjf's (18517 vs 18230). Trade-off: on those two conditions,
the team's `adaptive` keeps the lowest max wait of all eight configurations in 4 of 6 workload
ids, while AMF's average wait there is 19–59% below `adaptive`'s. Interpretation: waits on mixed and wide_jobs run
into the thousands, far past `max_age` = 500. Every old job's age factor saturates at 1, and
shortness and narrowness then decide alone, so long, wide jobs are overtaken repeatedly. The
ablation (E5) tests this explanation. Confidence: all seeds agree on the direction. The size
varies by seed (×2.2–×4.2).

**E4: Adaptation (gain 0.5 vs 0) mostly raised the average wait without a consistent max-wait
gain.** Observation (AMF vs amf_fixed, seeds 7/11/13): average wait +3 to +13% on heavy, +10 to
+38% on short_heavy, +13 to +44% on mixed, −0 to +4% on wide_jobs, +0 to +1% on light. Max wait:
short_heavy −18%, −32%, 0; mixed −16%, +3%, −9%; heavy +4%, −3%, −3%; wide_jobs within ±1%.
Trade-off: where adaptation lowered the max wait (short_heavy seeds 7 and 11, mixed seeds 7 and
13), it raised the average by more, in percentage terms, in 3 of those 4 ids (short_heavy seed 11:
max −32%, average +24%). Interpretation: moving weight to age pushes the policy
toward arrival order, the same direction the team `adaptive` showed in our earlier study (F6
there). With `max_age` = 500 the age factor is saturated for most of the queue on mixed and
wide_jobs, so shifting weight onto it cannot separate jobs further. Confidence: average wait is
higher with adaptation in 12 of 15 ids, equal in 2 (light), lower in 1 (wide_jobs seed 7). The max-wait effect changes sign between seeds:
treat it as unsettled.

**E5 (ablation): `max_age` sets where AMF sits on the average-vs-max trade-off.**
Observation (`amf_age5000` vs AMF): mixed max wait −53 to −57% and wide_jobs −49 to −74%, with
average wait +4 to +112% and +31 to +36%. That brings AMF's max wait to within +3 to +33% of
easy_backfill's, while its average wait stays 3–30% below easy_backfill's on mixed and wide_jobs.
On heavy the effect reverses: max wait +97 to +214%, average −37 to −46%. Interpretation: on heavy
the waits rarely reach 5000, so age barely counts and AMF behaves like a shortness-first policy.
No single `max_age` suits both waiting-time scales. The value has to come from the workload, the
same tuning question Slurm operators face with `PriorityMaxAge`. Confidence: three seeds per
condition, two values of `max_age`. The curve between and beyond them is unknown.

**E6 (ablation): the reservation threshold matters much less than `max_age`.** Observation:
always reserving (`reservation_xf` 1) changed AMF's wait metrics by 0% on wide_jobs and by −22
to +9% elsewhere. Never reserving (∞) lowered heavy's average wait by 24–32% and raised its max
wait by 3–31%. Interpretation: on wide_jobs a starving job is rarely the top-ranked job (see E3),
so a reservation that only the top job can hold almost never protects it. Confidence: all seeds
agree that the reservation threshold does not move wide_jobs.

**E7: Priority preemption helped AMF most where short jobs queue behind long ones.**
Observation (amf_preemptive vs AMF): short_heavy average wait −17 to −55% and max wait −14 to
−38% (48–128 preemptions per run). amf_preemptive had the lowest max wait of all eight
configurations in 3 of 3 short_heavy ids (616, 928, 1312). Mixed average −10 to −41%, but max
wait +14% and +21% in 2 of 3 seeds. Heavy and wide_jobs: 0–5 preemptions, changes within ±10%.
Trade-off: compared with srtf, its average wait on short_heavy is higher (30–94 vs 15–20), with
far fewer preemptions (48–128 vs 46–180) and a lower max wait. Interpretation: the 0.1 utility
margin keeps preemption rare. It acts where an old or short job is blocked behind long ones, and
otherwise does nothing. Confidence: the short_heavy direction holds in all seeds. Mixed is mixed.

**E8: When the cluster is half idle, the policy barely matters.** Observation: light's average
wait is 2.6–5.0 for all eight configurations, and utilization is identical to within 0.3 points.
Interpretation: queues rarely form. Confidence: all seeds agree.

## 5. Trade-off table

Generated by `adaptivesched findings` (cell: the metrics a strategy led or trailed on, in k of 3
seeds; fairness counts higher as better):

| strategy | light | heavy | short_heavy | mixed | wide_jobs |
|---|---|---|---|---|---|
| fifo | led: max wait 2/3, makespan 2/3<br>trailed: avg wait 3/3, slowdown 3/3, fairness 3/3 | led: -<br>trailed: avg wait 3/3, slowdown 3/3, fairness 1/3 | led: makespan 1/3<br>trailed: avg wait 3/3, max wait 1/3, makespan 1/3, slowdown 3/3 | led: -<br>trailed: avg wait 3/3, slowdown 3/3 | led: fairness 2/3<br>trailed: avg wait 3/3, makespan 3/3, slowdown 3/3 |
| sjf | led: makespan 1/3<br>trailed: makespan 1/3 | led: -<br>trailed: max wait 2/3, makespan 3/3, fairness 1/3 | led: -<br>trailed: makespan 1/3 | led: -<br>trailed: max wait 2/3, makespan 3/3, fairness 1/3 | led: -<br>trailed: max wait 2/3 |
| easy_backfill | led: max wait 2/3, makespan 2/3<br>trailed: avg wait 2/3, slowdown 2/3, fairness 2/3 | led: max wait 2/3, makespan 1/3<br>trailed: - | led: makespan 1/3<br>trailed: fairness 2/3 | led: max wait 2/3, makespan 1/3<br>trailed: - | led: fairness 1/3<br>trailed: - |
| srtf | led: avg wait 3/3, slowdown 3/3, fairness 3/3<br>trailed: max wait 2/3, makespan 2/3 | led: avg wait 3/3, slowdown 3/3<br>trailed: max wait 1/3, fairness 1/3 | led: avg wait 3/3, slowdown 3/3, fairness 3/3<br>trailed: makespan 1/3 | led: avg wait 3/3, slowdown 3/3, fairness 3/3<br>trailed: - | led: avg wait 3/3, slowdown 3/3<br>trailed: fairness 3/3 |
| adaptive | led: makespan 1/3<br>trailed: max wait 1/3 | led: max wait 1/3, makespan 2/3<br>trailed: - | led: -<br>trailed: max wait 1/3, makespan 1/3 | led: max wait 1/3, makespan 2/3<br>trailed: fairness 2/3 | led: max wait 3/3, makespan 3/3<br>trailed: - |
| adaptive_multifactor | led: makespan 1/3<br>trailed: - | led: max wait 1/3<br>trailed: - | led: -<br>trailed: makespan 1/3 | led: -<br>trailed: - | led: -<br>trailed: max wait 1/3 |
| amf_preemptive | led: max wait 1/3, makespan 1/3<br>trailed: - | led: -<br>trailed: - | led: max wait 3/3<br>trailed: fairness 1/3 | led: -<br>trailed: max wait 1/3 | led: -<br>trailed: max wait 1/3 |
| amf_fixed | led: makespan 1/3<br>trailed: - | led: fairness 3/3<br>trailed: - | led: makespan 2/3<br>trailed: max wait 1/3, makespan 1/3 | led: -<br>trailed: - | led: -<br>trailed: - |

## 6. Where the adaptive policy did better or worse

| | better than | worse than |
|---|---|---|
| average wait | fifo and easy_backfill in 15/15 workload ids; team `adaptive` on mixed and wide_jobs (−19 to −59%) | srtf everywhere; sjf on heavy, mixed, wide_jobs; team `adaptive` on heavy (+41 to +60%) |
| max wait | sjf and srtf on heavy (−76 to −84%); preemptive variant best of all on short_heavy | easy_backfill and team `adaptive` on mixed and wide_jobs (×2.2–×4.2) at the default `max_age` |
| adaptation | | the fixed-weight control on average wait in 12/15 ids (2 equal), with no consistent max-wait gain |

AMF is a middle point in this study, not a winner. It sits between SJF/SRTF (low average, high
max) and the arrival-order policies (high average, low max). Where exactly it sits is set mainly
by `max_age`, and the default suited heavy but not mixed or wide_jobs.

## 7. Threats to validity and limitations

- **Synthetic workloads only**, five conditions, 300 jobs, one cluster size (16 CPU cores). No
  real trace was replayed (SWF traces are deferred).
- **Exact runtimes** (`runtime_estimate_error = 0`). sjf, srtf, easy_backfill and AMF all use
  runtime. With real estimates, often off by large factors [Mu'alem & Feitelson 2001], their
  advantage over fifo would likely shrink.
- **Zero-cost preemption.** srtf's and amf_preemptive's gains assume suspending and resuming a
  gang-scheduled job costs nothing.
- **Parameters**: AMF was run at its defaults plus one change per ablation variant. It was not
  tuned per workload, and doing so would favour it unfairly unless every other policy were tuned
  too.
- **Fairness is job-level** (Jain over slowdowns). There is no user field, so user-level fair
  share, the factor production multifactor schedulers weight most, is not modelled.
- **Three seeds** per condition. Effects that change sign between seeds are reported as
  unsettled, not averaged away.
- **Engine version**: these results come from `daa589d` plus this phase's uncommitted policy file
  (`+dirty`). After the code is committed, rerunning the two configs records the clean commit and
  must reproduce every number here, since the engine code itself is unchanged.

## 8. Conclusion

Eight scheduling configurations ran on fifteen workload ids under identical conditions. The
policy that minimises average waiting time (srtf) also produces some of the longest waits for
individual jobs. The policies that protect the longest-waiting job (easy_backfill, the team's
`adaptive`) give up average wait to do it. The adaptive multi-factor policy, built from Slurm's
normalised multifactor priority, Tang et al.'s state-dependent re-weighting and Srinivasan et
al.'s selective reservation, landed between the two. Its worst-case protection depended on
whether `max_age` matched the workload's waiting-time scale. Adapting the weights to queue age
cost average wait more often than it helped the worst case. Optional priority preemption was
its most effective addition where short jobs queue behind long ones. Which of these trade-offs
is acceptable depends on the workload and on whether the operator values the mean or the worst
case. The study does not settle that choice, and leaves it to the reader.

---

## 9. Real workloads: five production logs (Parallel Workloads Archive)

Synthetic workloads (§2–§8) are controlled but invented. This section replays **real job logs**
from five production machines. Each log contributes two windows of 5,000 consecutive jobs: one
centred in the log and one starting a quarter of the way in. Each window is run at the machine's
own size. Conversion: `workloads/README.md`. Configs: `researcher/examples/real/<log>.yaml`.
Results: `researcher/results/real/batch_*/` (90 runs, 0 failed).

| log | CPUs | windows' load | runtime median / p90 | job width median / p90 / max |
|---|---|---|---|---|
| KTH SP2 (1996–97) | 100 | 0.72 | 526 s / 7.5 h | 2 / 16 / 96 |
| SDSC SP2 (1998–2000) | 128 | 0.85 | 148 s / 7.3 h | 4 / 24 / 128 |
| HPC2N (2002–06) | 240 | 0.69 | 53 min / 5.8 h | 2 / 12 / 128 |
| CTC SP2 (1996–97) | 338 | 0.82 | 476 s / 11.5 h | 4 / 32 / 306 |
| SDSC Blue (2000–03) | 1,152 | 0.78 | 166 s / 2.2 h | 8 / 64 / 960 |

(Load and percentiles are for the centred window. Times are seconds as logged; a window spans
18–63 days.)

Nine configurations ran on every window: the eight of §2, plus `amf_age7d`, which is AMF with
`max_age` = 7 days (604,800 s, Slurm's default `PriorityMaxAge`). This variant was added because
E3/E5 showed that `max_age` must match the waiting-time scale, and these logs count in seconds.
Average wait (hours) / max wait (days), per window, centred window first:

| strategy | KTH | KTH q1 | SDSC SP2 | SP2 q1 | HPC2N | HPC2N q1 | CTC | CTC q1 | Blue | Blue q1 |
|---|---|---|---|---|---|---|---|---|---|---|
| fifo | 26.9/3.5 | 39.9/5.2 | 130.8/9.3 | 18.0/2.4 | 0.8/0.3 | 5.1/1.2 | 24.2/2.1 | 36.0/3.4 | 15.2/1.5 | 4.2/1.4 |
| sjf | 3.6/5.4 | 4.6/20.1 | 4.6/35.4 | 4.1/14.1 | 0.3/0.5 | 1.4/1.9 | 2.3/9.6 | 4.7/7.5 | 1.6/2.8 | 0.7/1.5 |
| easy_backfill | 2.4/2.2 | 3.0/2.3 | 5.3/3.5 | 2.9/2.2 | 0.4/0.3 | 2.7/1.2 | 3.3/1.8 | 4.5/2.0 | 1.1/0.9 | 0.8/1.1 |
| srtf | 0.4/3.8 | 0.5/7.4 | 1.1/27.5 | 0.5/9.4 | 0.1/0.9 | 0.6/2.8 | 0.5/6.4 | 0.8/5.9 | 0.2/2.4 | 0.2/1.3 |
| adaptive | 2.1/19.9 | 2.1/8.8 | 4.2/33.6 | 2.1/9.3 | 0.3/0.5 | 0.9/1.4 | 0.9/5.8 | 1.5/9.4 | 0.9/6.3 | 0.4/7.4 |
| AMF (max_age 500 s) | 2.4/48.8 | 1.7/16.8 | 3.4/44.8 | 1.7/28.1 | 0.2/0.5 | 0.8/1.9 | 1.0/6.8 | 1.2/16.5 | 0.6/6.2 | 0.4/4.4 |
| amf_preemptive | 2.4/49.0 | 2.1/42.0 | 3.9/43.4 | 1.2/28.3 | 0.2/0.4 | 0.6/2.0 | 0.7/11.8 | 1.0/16.4 | 0.5/9.6 | 0.3/1.7 |
| amf_fixed | 2.4/48.8 | 1.7/18.8 | 3.4/44.8 | 1.7/28.8 | 0.2/0.5 | 0.8/1.9 | 1.0/6.8 | 1.2/16.5 | 0.6/6.2 | 0.4/4.4 |
| **amf_age7d** | 1.6/5.2 | 2.0/3.4 | 3.8/4.6 | 1.8/3.0 | 0.2/0.5 | 1.0/1.3 | 1.2/3.7 | 2.1/3.8 | 0.6/1.6 | 0.3/1.4 |

**R1: On real logs the default AMF starves long jobs for weeks; with `max_age` = 7 days it does
not.** Observation: AMF at `max_age` = 500 s had max waits of up to 48.8 days (KTH). With 7 days,
max wait fell in 10 of 10 windows (to 0.10–0.99× the default's), e.g. KTH 48.8 → 5.2 days and SDSC
SP2 44.8 → 4.6 days. Trade-off: average wait rose in 6 of 10 windows (ratio 0.68–1.80).
Interpretation: this confirms E3/E5 on real data. A 500-second age cap saturates within minutes
on logs where waits are hours, and shortness then overtakes long jobs indefinitely. Confidence:
direction 10/10. The size of the change varies by machine (HPC2N barely changes, because its waits
are short).

**R2: `amf_age7d` beat SJF on both average and maximum wait in every window.** Observation: lower
average wait in 10/10 windows (0.38–0.83× sjf) and lower max wait in 10/10 (0.13–0.96×). Against
the team's `adaptive`: lower max wait in 10/10 (0.14–0.97×), lower average in 7/10. Interpretation:
on these logs, adding a properly scaled age factor and a reservation to shortness-first ordering
removes most of SJF's starvation without giving back its average-wait gain. Confidence: all ten
windows. Exact runtimes favour every runtime-based policy here (§7).

**R3: EASY backfilling still had the best worst case.** Observation: easy_backfill had the
lowest max wait in 9 of 10 windows (in the 10th, HPC2N q1, it tied with fifo). `amf_age7d`'s max
wait was 1.10–2.38× easy_backfill's, while its average wait was 0.35–0.72× and its bounded
slowdown 0.22–0.49× easy_backfill's. Interpretation: the same trade-off as on synthetic workloads.
AMF moves along it, and does not escape it. Confidence: 10/10 windows in both directions.

**R4: srtf minimised average wait and slowdown everywhere, using 2,802–11,928 preemptions per
5,000 jobs.** Observation: lowest average wait and bounded slowdown in 10/10 windows. Max wait
was up to 27.5 days (SDSC SP2), and the preemption count is 0.6–2.4 per job. Trade-off:
amf_preemptive used 576–1,546 preemptions (2.4–9.9× fewer) and cut AMF's slowdown in 10/10 windows
(0.20–0.71×), but its max wait rose in 6 of 10. Interpretation: on real logs, frequent free
preemption dominates the averages, but the model gives preemption no cost; on a real system,
thousands of checkpoint-and-restart operations per few thousand jobs would not be free.
Confidence: 10/10 for srtf's lead on averages.

**R5: Adaptation again changed little.** AMF vs amf_fixed: average wait 0.94–1.12×, max wait
0.90–1.00×. With `max_age` = 500 s the age factor is saturated for almost every waiting job, so
moving weight onto it cannot separate jobs (the mechanism of E4).

**R6: FIFO with wait-behind-head is the worst choice on real logs.** Average wait 0.8–131 hours;
easy_backfill cut it to 0.04–0.56× in 10/10 windows with the same arrival order. Real logs contain
jobs as wide as the whole machine, and every one of them blocks the queue under wait-behind-head.

Caveat specific to this section: these logs record what the production schedulers actually did,
including their own waits. We re-simulate only arrival, runtime and width. Real users'
requested times (SWF field 9) were not used, because the simulator assumes exact runtimes.

**Follow-up.** The parameter search suggested by R1 and E5 is in `docs/TUNING.md`. Tuned on separate
training windows of the same five logs and checked on these ten windows, the non-preemptive
`amf_tuned` reached 0.31× EASY's bounded slowdown at 1.09× its max wait, against `amf_age7d`'s
0.32× and 1.60×.
