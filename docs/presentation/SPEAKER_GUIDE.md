# AdaptiveSched: detailed speaker guide (every slide, every plot)

For the 12-slide deck `AdaptiveSched.pptx`. For each visual: **how to read it** (axes, colours,
markers), **where to point**, **the exact numbers**, **what it means**, and **likely questions**.
All numbers come from the result files; nothing is estimated from the pictures.

**Colours used in every chart (say this once, on slide 6):**
FIFO blue · SJF orange · EASY backfilling yellow · SRTF pink · team `adaptive` teal ·
AMF (ours) dark green · AMF preemptive purple · AMF with fixed weights red.

**Units:** synthetic workloads use abstract "time units" (think seconds). Real logs use seconds.

---

## Slide 1: Title

Nothing to read off a chart. Say: "We built a simulator that tests job-scheduling rules fairly,
designed an adaptive scheduler from published ideas, and evaluated it on real supercomputer logs.
Our conclusion is a trade-off, not a winner."

---

## Slide 2: The problem (queue diagram)

**How to read the diagram**
- The **grid of 16 squares** is the cluster: each square is one CPU core. 12 are coloured (busy)
  and 4 are empty (free).
- The **blocks in the queue** are waiting jobs. **Width = number of cores** the job needs,
  **length = runtime**. The first block (8 cores, 4 h) is at the head, followed by small jobs
  (2 cores 5 min, 1 core 20 min, 3 cores 2 min).

**Where to point and what to say**
1. "The job at the head needs 8 cores, but only 4 are free."
2. "Under strict arrival order (FIFO), nothing may overtake it. So the small jobs behind it also
   wait, even though some of them would fit right now (the 1-core and 3-core jobs together need
   exactly 4), and 4 cores sit idle." This is **head-of-line blocking**.
3. "If we instead let small jobs go first every time, the big job can be overtaken forever." This
   is **starvation**.
4. "The rule that decides is the **scheduling policy**. Every policy we compare is a different
   answer to this picture."

**Likely questions**
- *Why can't the 8-core job just use 4 cores now?* Parallel jobs are **rigid**: a job asks for
  exactly c cores and runs only when all c are free at once.

---

## Slide 3: Simulation and engine (two diagrams)

### Top diagram: one step of the discrete-event engine

**How to read it:** six boxes left to right, with an arrow underneath looping back to the start.
One pass through the boxes is one **event time**.
1. **Advance clock:** jump straight to the next arrival or completion. No ticking second by second.
2. **Completions:** jobs that finish now release their cores.
3. **Arrivals:** jobs submitted now join the waiting queue.
4. **Preemption hook** (yellow, optional): a preemptive policy may suspend running jobs.
5. **Dispatch loop** (yellow): the policy proposes a job; the engine checks that it exists, is
   waiting and fits; then it starts it. Repeat until the policy says "none".
6. **Check invariants:** cores are never over-used, and every job is in exactly one state.

The yellow boxes are where the **policy** acts; the blue boxes are owned by the **engine**. The
bottom line states the tie rule: completions before arrivals, ties by job id. That makes every
run deterministic.

### Bottom diagram: system architecture

**How to read it:** top row = how people use it; middle row = the experiment software; bottom
row = the simulation core. Arrows show who calls whom.
- **Researcher → Frontend → HTTP API:** the dashboard in the browser sends JSON to a small Python
  server.
- **"CLI" and "run_batch()" arrows both point to the Experiment layer.** This is the key point:
  the command line and the dashboard call the **same** code, so they always give the same numbers.
- **Experiment layer → (adapter) → Simulation engine ⇄ Scheduling policies:** the engine sends
  a read-only *context* to the policy, and the policy sends back a *decision*.
- **Experiment layer → Result files:** CSV and JSON. **Analysis** (plots, Gantt charts) reads only
  these files, never the engine.

**Numbers to mention:** reruns are byte-identical; laptop vs HPC gave identical metrics in 60 of
60 runs.

**Likely questions**
- *Why not simulate second by second?* A 5,000-job log spans weeks (millions of seconds), but
  has only ~10,000 events. Jumping between events is thousands of times faster.
- *Why can't the policy start jobs itself?* So that a buggy policy can never break the simulation:
  the engine is the only one that changes state, and it validates every request.

---

## Slide 4: Scheduling as an AI agent (two tables)

**PEAS table:** read it row by row.
- **Performance:** what "good" means: low waiting time and slowdown, low maximum wait, high utilization.
- **Environment:** what the agent lives in: queue, running jobs, free cores, simulated clock.
- **Actuators:** what it can do: start a job; optionally suspend one.
- **Sensors:** what it can see: a read-only snapshot (time, free cores, waiting jobs, running jobs
  with their expected finish times).

**Environment properties** (the sentence under the table):
- *fully observable*: it sees the whole queue
- *deterministic*: runtimes are exact in our model
- *sequential*: starting a job now changes what is possible later
- *dynamic*: jobs keep arriving
- *discrete*: events, cores and jobs are countable
- *single-agent*: one scheduler

**Agent-type table**
- **Simple reflex** (FIFO, SJF, SRTF): "if the condition holds, do the action", looking only at
  the current queue.
- **Model-based + goal-based** (EASY): it keeps a model of when running jobs will finish, and has
  a goal: never delay the reserved first job.
- **Utility-based** (team adaptive, AMF): each job gets a numeric score, and the highest wins. AMF
  also keeps **internal state** (how old the queue is) and changes its weights with it.
- **Not a learning agent:** AMF's weights were found by offline search, then fixed. It doesn't
  improve itself while running.

**Likely questions**
- *Adaptive vs learning?* Adaptive means its behaviour changes with the situation through a fixed
  formula. Learning means it changes its own formula from experience. AMF is the first, not the
  second.

---

## Slide 5: AMF policy (factor-curve figure)

**How to read the figure:** three small plots, one per factor. The **y-axis is always the factor's
value from 0 to 1**, and a higher value means a higher priority.

**Left: Age A = min(1, wait / max_age)**
- x-axis: how long the job has waited, in hours (0–72). Three lines for three values of max_age.
- **Blue (500 s, the default):** jumps to 1 almost immediately, after 500 seconds. That is why
  every waiting job on real logs looked "maximally old", and age stopped telling them apart.
- **Orange (2.36 days, tuned):** rises steadily and reaches 1 at about 57 hours. Age keeps
  separating jobs for two days.
- **Green (7 days):** after 72 hours it has only reached 0.43, so it grows too slowly.

**Middle: Shortness S = 1 − ln(1+r) / ln(1+r_max)**
- x-axis: remaining runtime in hours, with the longest job in the queue r_max = 24 h.
- It falls steeply at first, then flattens. Example values:
  **1-minute job → 0.64**, **1-hour job → 0.28**, **12-hour job → 0.06**, **24-hour job → 0**.
- Why the logarithm: a plain ratio would give every job except the 24-hour one a score near 1.
  The log spreads short jobs apart.

**Right: Narrowness N = (C − c + 1) / C**
- x-axis: cores requested on a 128-core cluster. A straight line from **1.0 (1 core)** through
  **0.51 (64 cores)** to **0.008 (128 cores)**.

**Then the text on the slide**
- U = W_age·A + W_short·S + W_size·N, with weights summing to 1.
- Adaptation: σ is the average age of the queue. As σ grows, weight moves onto age:
  W_age = w_age + g·σ·(w_short + w_size).
- **Worked example:** job 1 (runtime 9, 2 cores, waited 10) scores 0.182; job 2 (runtime 1,
  8 cores, just arrived) scores 0.303, so job 2 starts first. This is an automated test whose
  numbers were computed by hand first.

**Likely questions**
- *What happens when the top job doesn't fit?* If it has waited at least as long as it will run
  (expansion factor ≥ the threshold), it reserves a start time, and others may run only if they
  finish before then. Otherwise the best job that fits starts.

---

## Slide 6: Synthetic results (two bar-chart grids)

Left grid: **average** waiting time. Right grid: **maximum** waiting time. They have the same
layout.

**How to read the grids**
- **5 rows = 5 workload conditions:** light, heavy, short_heavy, mixed, wide_jobs (300 jobs each,
  16 cores).
- **3 columns = 3 seeds (7, 11, 13):** three different random workloads of the same kind. If all
  three agree, the result is not luck.
- **Each small panel:** 8 bars, one per policy, in the fixed colours. The y-axis is waiting time.
  **Panels in one row share the y-scale; different rows have different scales.** So compare bars
  within a panel, or across one row, but never between rows.

**Left grid (average wait): where to point**
- **light row:** all bars are 2.6–5.0. The cluster is half idle, so the policy hardly matters.
  FIFO and EASY are identical in seeds 7 and 11 (4.78, 4.98): EASY only acts when the first job
  doesn't fit, which rarely happens on a quiet cluster.
- **short_heavy row:** FIFO's blue bar towers (148–374), while SRTF's pink bar almost vanishes
  (15–20). Many short jobs are stuck behind a few very long ones, and SRTF runs the short ones
  immediately.
- **mixed row:** FIFO reaches 1,573–3,422. SRTF is 113–201 and SJF 349–531. AMF (green) is
  373–658, far below FIFO and EASY (552–1,486).
- **wide_jobs row:** everyone waits thousands (1,144–3,079), because every job needs at least half
  the machine, so at most one job fits beside another.
- Overall: **SRTF has the lowest average in all 15 panels**, and AMF beats FIFO and EASY in all 15.

**Right grid (max wait): where to point**
- **heavy row:** SJF's orange bar and SRTF's pink bar shoot up to 1,621–2,224, while the others
  stay at 215–596. A few long jobs keep being overtaken.
- **mixed and wide_jobs rows:** SJF and SRTF are tallest again (wide_jobs 15,347–18,230). EASY and
  the team's `adaptive` are lowest (wide_jobs 4,354–5,595). AMF at default settings sits high on
  these rows (11,000–18,500). That foreshadows the max_age problem of slide 9.
- **short_heavy row:** the purple AMF-preemptive bar is the **lowest in all three seeds**
  (616, 928, 1,312).

**What it means:** comparing the two grids side by side, the policies with the **shortest average
bars** (SJF, SRTF) have the **tallest maximum bars**. That is the lesson on the slide.

**Likely questions**
- *Why do FIFO and EASY sometimes give exactly the same numbers?* When the first job always fits,
  there is nothing to backfill, so EASY behaves exactly like FIFO.

---

## Slide 7: The trade-off (scatter plot + CDF)

### Scatter plot (five panels)

**How to read it**
- **One panel per workload condition.** x-axis = average waiting time, y-axis = maximum waiting
  time, **both on log scales** (each grid line is ×10).
- **Each point = one policy on one workload.** Colour = policy; **marker shape = seed**
  (circle = seed 7, square = 11, triangle = 13). Seed-7 points carry a text label.
- **Down and to the left is better on both counts.** No colour sits in the bottom-left corner of
  every panel.

**Where to point**
- **heavy panel:** SJF (orange) and SRTF (pink) are top-left (low average, max 1,600–2,200). FIFO
  (blue) and EASY (yellow) are bottom-right (high average, max 215–581). AMF (dark green) sits
  between them: seed 7 has average 164, max 532.
- **wide_jobs panel:** the clearest split. SRTF and SJF are top-left (average about 1,200,
  max about 15,000+). FIFO, EASY and adaptive are bottom-right (average 2,000–3,000, max about
  5,000). AMF is in the middle (average 1,510, max 11,000).
- Say: "Moving left costs you height. That is the trade-off."

### CDF (heavy workload, seed 7)

**How to read it**
- x-axis = waiting time. y-axis = **fraction of jobs that waited at most that long**.
- A curve that rises **steeply on the left** means most jobs barely waited. Where a curve finally
  **reaches 1.0** is the longest wait (the maximum).

**Where to point (exact numbers for this workload)**
| policy | waited 0 | waited ≤ 50 | median | 90 % waited ≤ | max |
|---|---|---|---|---|---|
| SRTF | 50 % | 83 % | 0 | 138 | 1,639 |
| SJF | 32 % | 77 % | 10 | 187 | **2,224** |
| team adaptive | 25 % | 54 % | 38 | 323 | 507 |
| AMF | 23 % | 39 % | 128 | 385 | 532 |
| EASY | 18 % | 34 % | 151 | 407 | 545 |
| FIFO | 17 % | 33 % | 176 | 444 | 581 |

- **Pink and orange (SRTF, SJF)** jump to about 0.8 almost immediately, so most jobs hardly
  wait. But their lines crawl along the top all the way to 1,639 and 2,224. That long flat tail is
  the few starved jobs.
- **Blue (FIFO)** rises slowly but finishes early (581). Everyone waits a bit; nobody waits forever.
- AMF and AMF-preemptive overlap completely here: no preemption happened on this workload.

**Likely questions**
- *Why log axes on the scatter?* Values range from 3 to 18,000; on a linear scale the light
  workload would be a dot in the corner.

---

## Slide 8: Gantt charts (two figures)

**How to read a Gantt chart**
- x-axis = time. y-axis = **CPU core lanes 0–16**. Lanes are assigned only for drawing; the real
  machine does not tie a job to particular cores.
- Each **rectangle = one job running**: its **width is how long** it ran, its **height is how
  many cores** it used.
- **Light grey background = idle cores** (wasted capacity).
- **Hatched (striped) rectangles** = a piece of a job that **resumed after being paused**.
- Two policies are stacked on the **same time axis**, so you can compare them vertically. The
  caption at the bottom gives both policies' average and maximum wait.

### Left: FIFO (blue, top) vs AMF (green, bottom), heavy workload, seed 7

**Where to point:** the grey gaps in the blue chart, especially early on (0–600) and scattered
later. These are moments when the first job in line didn't fit, so FIFO left cores empty. The
green chart has fewer, smaller gaps, because AMF starts another job that fits.

**Numbers:** average wait 203.5 → 163.8, max 581 → 532, CPU utilization 86.9 % → 88.3 %, all jobs
done at time 3,440 → 3,387.

### Right: SRTF (pink, top) vs preemptive AMF (purple, bottom), short_heavy workload, seed 7

**Where to point**
- The long bars are the 10 % of very long jobs (600–3,000 time units). In SRTF's chart, almost all
  of them are **hatched and chopped into many pieces**: every time a shorter job arrives, the long
  one is paused.
- Preemptive AMF's chart has more solid bars: it pauses less (128 pauses vs SRTF's 180).

**Numbers:** SRTF average wait **19.0**, max **1,048**; preemptive AMF average **50.5**, max
**616**. SRTF is better for the typical job; AMF is better for the worst-off job.

**Likely questions**
- *Isn't pausing jobs wasteful?* In our model a pause is free. On a real machine the job's memory
  must be saved and restored (checkpointing), which costs time. So these charts flatter
  preemptive policies, and we say so.

---

## Slide 9: Real workloads (table + bar chart)

**Table:** five real logs from the Parallel Workloads Archive. Machine size runs from **100 to
1,152 CPUs**, and the logs cover **28,476 to 243,306 jobs** from 1996–2006. We cut **windows of
5,000 consecutive jobs** and ran each on its machine's real size. The load in the windows was
69–85 %.

**Bar chart: how to read it**
- x-axis: the policies. For each there are two bars:
  - **Blue = bounded slowdown** (how much the *typical* job was slowed down).
  - **Orange = maximum waiting time** (the *worst-off* job).
- y-axis: **ratio to EASY backfilling**, on a **log scale**. **The black line at 1 is EASY.**
  Below the line is better than EASY, above is worse.
- Each bar is the **geometric mean over 10 windows** (2 per log). That is the right average for
  ratios: a halving and a doubling cancel out.

**Exact values (slowdown / max wait, × EASY)**
| policy | slowdown | max wait |
|---|---|---|
| SJF | 0.37 | 3.60 |
| SRTF | 0.04 | 2.94 |
| team adaptive | 0.84 | 4.29 |
| AMF defaults | 0.28 | **6.04** |
| AMF, max_age 7 days | 0.32 | 1.60 |
| **AMF tuned** | 0.31 | **1.09** |
| AMF tuned + preemption | 0.05 | 0.98 |

**Where to point**
1. "Almost every blue bar is below the line: nearly all policies make the typical job faster than EASY."
2. "But almost every orange bar is above it: EASY protects the worst-off job best. It had the
   lowest max wait in 9 of 10 windows, and tied in the 10th."
3. "Look at **AMF defaults: 6.04**. Its worst-off job waited six times longer than EASY's. In one
   log a job waited **49 days**." Point back to the blue line on slide 5: a 500-second age cap fills
   instantly when waits are hours, so age stops protecting anyone.
4. "With max_age set to the right scale (7 days) it drops to 1.60, and after tuning to 1.09:
   almost EASY's worst case, at a third of EASY's slowdown."

**Likely questions**
- *What is bounded slowdown?* (waiting + runtime) / runtime, with runtime counted as at least
  10 s. A 1-minute job that waited 9 minutes has slowdown 10.
- *Why compare to EASY?* It is what most real supercomputers run, and it had the best worst case.

---

## Slide 10: Parameter search (results table + candidate scatter)

**The objective (top text):** J = mean ln(slowdown / EASY's) + mean ln(max wait / EASY's).
- It counts the typical job and the worst-off job **equally**. J = 0 means "exactly as good as
  EASY", and **more negative is better**.
- The log means that halving one ratio and doubling the other cancels out.

**Table (held-out windows, ratios to EASY)**
| | slowdown | max wait | avg wait |
|---|---|---|---|
| AMF defaults | 0.28 | 6.04 | 0.49 |
| SJF | 0.37 | 3.60 | 0.99 |
| **AMF tuned** | **0.31** | **1.09** | 0.72 |
| AMF tuned + preemption | 0.05 | 0.98 | 0.26 |

Explain the row for AMF tuned: "Slowdown is about SJF's, max wait is about EASY's. That's the
middle point we wanted." The price is a higher average wait than the defaults (0.72 vs 0.49).

**Scatter: how to read it**
- **Every dot is one candidate setting** from the search, scored on the 10 *training* windows.
- x-axis = slowdown ÷ EASY's, y-axis = max wait ÷ EASY's, **both on log scales**. The grey lines at
  1 mark EASY. **The bottom-left quadrant beats EASY on both.**
- **Green dots (457) = non-preemptive candidates; purple dots (163) = preemptive ones.**
- **Black diamonds** are named points: EASY (1, 1); defaults (0.31, 2.97); age7d (0.33, 1.52);
  **amf_tuned (0.32, 0.96)**; amf_tuned_preemptive (0.043, 0.84).

**Where to point**
1. "The purple cloud sits far to the left, at 0.04–0.2: with free preemption, slowdown collapses.
   That's why we ran a second search with preemption switched off."
2. "The green cloud is at 0.27–1.2. Most green dots are above the line, worse than EASY on max
   wait. Our tuned point is one of the few green dots just below it."
3. "The defaults sit high up at 2.97. Tuning moved us straight down."

**Method in one breath:** 160–240 random candidates, then two rounds of small changes around the
best ones; 620 candidates × 10 windows = 6,200 simulations, run in parallel on the college HPC.
Training and test windows don't overlap. The score went from J = −1.19 in training to −1.07 on
unseen windows, so it **generalises**. It does **not** transfer to the synthetic workloads (a
different time scale).

**Likely questions**
- *Why not grid search?* With 8 parameters, 10 values each would be 100 million combinations.
  Random search plus refinement found good regions with 620.
- *Is this machine learning?* No: no model is fitted. Each candidate is simulated and judged; it
  is black-box optimisation.
- *Which parameters mattered?* Always reserve for the top job, an age horizon of about 2 days, and
  a small size weight. The split between age weight and adaptation gain mattered little.

---

## Slide 11: Tooling (screenshots + engine diagram)

**Configuration screenshot:** point at the workload checkboxes (synthetic conditions and the real
logs, each showing its CPU count), the cluster-cores box, and the `adaptive_multifactor` block
with the **Preset** menu ("tuned for real HPC logs" fills in the tuned values) and the
"preemptive execution" tick box.

**Results screenshot:** the metrics table (one row per policy for one workload and cluster size)
and the bar charts, one per metric, with a note saying whether lower or higher is better.
Hovering a bar shows its exact value.

**Gantt screenshot:** the same kind of chart as slide 8, but interactive: hover shows a job's
arrival, wait and cores, and clicking opens it in the job table.

**Engine diagram (repeated):** a reminder that the dashboard is just a window onto the same runner.

**Numbers:** 210 automated tests; byte-identical reruns; 60 of 60 runs identical between laptop
and HPC.

---

## Slide 12: Conclusion, limitations, future work

No chart. Speak to the three blocks:
- **Conclusion:** there is no universal winner; tuned AMF is a strong middle point on real logs;
  parameters must fit the workload's time scale (slide 9 showed why).
- **Limitations:** exact runtimes; free preemption; only CPU cores; fairness per job, not per
  user; logs from 1996–2006.
- **Future work:** runtime estimates and a preemption cost; user-level fairness; modern logs; an
  age horizon that adjusts itself to the time scale; online (learning) adaptation of the weights.

End with the open question ("average or worst case? It depends on the users") and stop.

---

## Quick reference: numbers to remember

- 120 synthetic runs · 90 real-log runs · 620 tuning candidates (6,200 simulations) · 210 tests
- SRTF: lowest average wait in all 15 synthetic workloads; max waits up to 27 days on real logs
- AMF defaults on real logs: max wait 6.04× EASY's, up to 49 days
- AMF tuned (held-out): slowdown 0.31×, max wait 1.09× EASY's
- Tuned weights: age 0.386 · short 0.521 · size 0.093 · max_age 2.36 days · gain 0.24 · always reserve
