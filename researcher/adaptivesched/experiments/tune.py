"""Parameter search for adaptive_multifactor (AMF): seeded random search, then local refinement.

This is black-box optimisation, not machine learning. Nothing is fitted to data: candidate
parameter sets are scored by simulating them, and the best are perturbed and scored again.

Objective (lower is better; 0 = exactly as good as EASY backfilling on both counts):

    J = mean_w ln(bsld_w / bsld_w^EASY) + mean_w ln(maxwait_w / maxwait_w^EASY)

w ranges over the training windows. Bounded slowdown measures the typical job's cost, max wait
the worst-off job's. Ratios to EASY on the same window make windows from machines of different
sizes comparable, and the logs give one point per window, so each window counts once. Every
candidate's average wait, fairness and preemptions are recorded too, so other objectives can be
read off the same results without rerunning anything.
"""
from __future__ import annotations

import csv
import json
import math
from functools import lru_cache
from multiprocessing import get_all_start_methods, get_context
from pathlib import Path

import numpy as np

from adaptivesched.experiments.adapter import TeamEngineAdapter
from adaptivesched.experiments.export import write_json
from adaptivesched.metrics import definitions as m
from adaptivesched.workloads.loader import load_csv
from adaptivesched.workloads.swf import declared_cores

POLICY = "adaptive_multifactor"
BASELINE = "easy_backfill"
MAX_AGE = (60.0, 30 * 86400.0)  # seconds: one minute to thirty days, searched on a log scale
XF = (1.0, 16.0)
P_NO_RESERVATION = 0.15         # share of samples with reservation_xf = inf (never reserve)
FIELDS = ["age_weight", "short_weight", "size_weight", "max_age", "adaptation_gain", "reservation_xf",
          "preemptive", "preempt_margin"]


# ---- search space ------------------------------------------------------------------------

def sample(rng) -> dict:
    w = rng.dirichlet([1.0, 1.0, 1.0])  # uniform on the weight simplex
    return {"age_weight": float(w[0]), "short_weight": float(w[1]), "size_weight": float(w[2]),
            "max_age": float(math.exp(rng.uniform(*map(math.log, MAX_AGE)))),
            "adaptation_gain": float(rng.uniform(0, 1)),
            "reservation_xf": math.inf if rng.random() < P_NO_RESERVATION
            else float(math.exp(rng.uniform(*map(math.log, XF)))),
            "preemptive": bool(rng.random() < 0.5),
            "preempt_margin": float(rng.uniform(0, 0.5))}


def perturb(p: dict, rng, scale: float) -> dict:
    """A neighbour of p: weights moved in log space and renormalised, max_age and reservation_xf on a
    log scale, gain and margin additively; preemption flipped with probability scale/2."""
    w = np.log(np.maximum([p["age_weight"], p["short_weight"], p["size_weight"]], 1e-6))
    w = np.exp(w + rng.normal(0, scale, 3))
    w /= w.sum()
    clip = lambda x, lo, hi: float(min(hi, max(lo, x)))
    xf = p["reservation_xf"]
    if math.isinf(xf):
        xf = math.inf if rng.random() > scale / 2 else XF[1]
    else:
        xf = clip(xf * math.exp(rng.normal(0, scale)), *XF)
    return {"age_weight": float(w[0]), "short_weight": float(w[1]), "size_weight": float(w[2]),
            "max_age": clip(p["max_age"] * math.exp(rng.normal(0, 2 * scale)), *MAX_AGE),
            "adaptation_gain": clip(p["adaptation_gain"] + rng.normal(0, scale / 2), 0, 1),
            "reservation_xf": xf,
            "preemptive": (not p["preemptive"]) if rng.random() < scale / 2 else p["preemptive"],
            "preempt_margin": clip(p["preempt_margin"] + rng.normal(0, scale / 4), 0, 0.5)}


# ---- evaluation --------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _window(path: str):
    cores = declared_cores(path)
    if cores is None:
        raise ValueError(f"{path}: no '# cluster_cores: N' header; convert it with --from-swf")
    return load_csv(path, cores).jobs, cores


def simulate(task) -> dict:
    """One (strategy, params, window) simulation -> its metrics. Runs in a worker process."""
    strategy, params, path = task
    jobs, cores = _window(path)
    r = TeamEngineAdapter().run(jobs, cores, strategy, params, workload_id=path).records
    return {"bsld": m.bounded_slowdown(r), "max_wait": m.max_waiting_time(r),
            "avg_wait": m.average_waiting_time(r), "fairness": m.fairness_index(r),
            "preemptions_per_job": m.total_preemptions(r) / len(r), "utilization": m.cpu_utilization_pct(r, cores)}


def objective(cand: list[dict], base: list[dict]) -> float:
    """J above; cand and base hold one metrics dict per window, in the same order."""
    n = len(base)
    return (sum(math.log(c["bsld"] / b["bsld"]) for c, b in zip(cand, base)) / n
            + sum(math.log(max(c["max_wait"], 1) / max(b["max_wait"], 1)) for c, b in zip(cand, base)) / n)


def summarise(params: dict, cand: list[dict], base: list[dict], stage: str) -> dict:
    gmean = lambda xs: math.exp(sum(map(math.log, xs)) / len(xs))
    return {"stage": stage, **params, "J": objective(cand, base),
            "bsld_ratio": gmean([c["bsld"] / b["bsld"] for c, b in zip(cand, base)]),
            "max_wait_ratio": gmean([max(c["max_wait"], 1) / max(b["max_wait"], 1) for c, b in zip(cand, base)]),
            "avg_wait_ratio": gmean([max(c["avg_wait"], 1e-9) / max(b["avg_wait"], 1e-9) for c, b in zip(cand, base)]),
            "fairness_mean": sum(c["fairness"] for c in cand) / len(cand),
            "preemptions_per_job": sum(c["preemptions_per_job"] for c in cand) / len(cand)}


def pareto(rows: list[dict], x="bsld_ratio", y="max_wait_ratio") -> list[dict]:
    """Rows not dominated on (x, y), both lower-better, sorted by x."""
    front, best_y = [], math.inf
    for r in sorted(rows, key=lambda r: (r[x], r[y])):
        if r[y] < best_y:
            front.append(r)
            best_y = r[y]
    return front


# ---- search ------------------------------------------------------------------------------

def tune(windows: list[str], out, trials: int = 160, refine_top: int = 6, refine_each: int = 12,
         seed: int = 2026, workers: int = 1, extra: dict | None = None, preemptive: bool | None = None) -> dict:
    """Random search (trials) + two rounds of local refinement around the best candidates.
    `extra` adds named reference candidates (e.g. the defaults) to the first stage.
    preemptive=True/False fixes that parameter for every candidate (None: searched)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    if preemptive is not None:
        fix = lambda p: {**p, "preemptive": preemptive}
        sample_, perturb_ = (lambda r: fix(sample(r))), (lambda p, r, s: fix(perturb(p, r, s)))
    else:
        sample_, perturb_ = sample, perturb
    windows = sorted(windows)
    # fork where the OS has it: forkserver (Python 3.14's POSIX default) and spawn re-import the
    # main script, which fails when it is stdin or a frozen console-script launcher.
    ctx = get_context("fork" if "fork" in get_all_start_methods() else "spawn")
    pool = ctx.Pool(workers) if workers > 1 else None
    run = (lambda tasks: pool.map(simulate, tasks, chunksize=1)) if pool else (lambda tasks: list(map(simulate, tasks)))
    try:
        base = run([(BASELINE, {}, w) for w in windows])
        rows: list[dict] = []

        def evaluate(cands: list[dict], stage: str):
            flat = run([(POLICY, c, w) for c in cands for w in windows])
            k = len(windows)
            for i, c in enumerate(cands):
                rows.append(summarise(c, flat[i * k:(i + 1) * k], base, stage))

        named = dict(extra or {})
        evaluate([sample_(rng) for _ in range(trials)] + list(named.values()), "random")
        for j, name in enumerate(named):
            rows[trials + j]["stage"] = f"reference:{name}"
        for stage, top, each, scale in [("refine-1", refine_top, refine_each, 0.5),
                                        ("refine-2", max(1, refine_top // 2), refine_each, 0.2)]:
            best = sorted(rows, key=lambda r: r["J"])[:top]
            evaluate([perturb_({f: b[f] for f in FIELDS}, rng, scale) for b in best for _ in range(each)], stage)
    finally:
        if pool:
            pool.close()
            pool.join()

    cols = ["stage", *FIELDS, "J", "bsld_ratio", "max_wait_ratio", "avg_wait_ratio", "fairness_mean",
            "preemptions_per_job"]
    with open(out / "candidates.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    ranked = sorted(rows, key=lambda r: r["J"])
    result = {"objective": "J = mean ln(bsld/bsld_EASY) + mean ln(maxwait/maxwait_EASY) over training windows",
              "windows": windows, "seed": seed, "evaluated": len(rows),
              "preemptive": "searched" if preemptive is None else preemptive,
              "best": ranked[0],
              "best_non_preemptive": next((r for r in ranked if not r["preemptive"]), None),
              "best_preemptive": next((r for r in ranked if r["preemptive"]), None),
              "references": [r for r in rows if r["stage"].startswith("reference:")],
              "pareto_bsld_vs_max_wait": pareto(rows),
              "baseline": {"strategy": BASELINE, "per_window": dict(zip(windows, base))}}
    write_json(result, out / "result.json")
    return result


def params_of(row: dict) -> dict:
    """The constructor parameters in a result row, ready for a batch config."""
    return {f: (bool(row[f]) if f == "preemptive" else row[f]) for f in FIELDS}


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(sample(np.random.default_rng(0)), indent=2))
