"""`adaptivesched` command line."""
from __future__ import annotations

import argparse
import os
import json
import re
import sys

from adaptivesched.experiments.adapter import ADAPTERS


def _strategies(args):
    _engine_banner(args.engine)
    for name in ADAPTERS[args.engine]().strategies():
        print(name)


def _workloads(args):
    from adaptivesched.workloads import resolve
    from adaptivesched.workloads.generators import GENERATORS
    from adaptivesched.workloads.loader import to_csv_text

    if args.from_swf:
        from pathlib import Path

        from adaptivesched.workloads.swf import swf_window

        if not args.out:
            raise ValueError("--from-swf needs --out CSV")
        text, cores, info = swf_window(args.from_swf, args.jobs, args.start)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {Path(args.out).as_posix()}: {info['window_jobs']} jobs (SWF {info['first_job']}.."
              f"{info['last_job']}) of {info['jobs_in_log']} usable, {info['computer']}, {cores} CPU cores, "
              f"arrivals over {info['arrival_span_s'] / 86400:.1f} days")
        print(f"run it with cluster_cores: {cores}")
        return
    if not args.show:
        print("Named synthetic workloads. Id: synth:<name>:n=<n_jobs>:seed=<seed>;")
        print("the jobs also depend on the cluster's CPU cores, which every run records.\n")
        for name, (load, _, desc) in GENERATORS.items():
            print(f"  {name:<12} offered load {load:<4} {desc}")
        print("\nParameters: seed, n_jobs, cluster_cores, runtime_estimate_error (must be 0.0 in this iteration).")
        print("CSV workloads: header job_id,arrival_time,runtime,required_cores; integers; '#' comments.")
        return
    if args.cluster_cores is None:
        raise ValueError("--show needs --cluster-cores")
    w = resolve(args.show, args.cluster_cores)
    jobs = w.jobs[:args.head] if args.head else w.jobs
    comments = [f"workload_id: {w.workload_id}", f"params: {json.dumps(dict(w.params))}"]
    if len(jobs) < len(w.jobs):
        comments.append(f"showing first {len(jobs)} of {len(w.jobs)} jobs")
    sys.stdout.write(to_csv_text(jobs, comments))


METRIC_LABELS = [
    ("average_waiting_time", "average waiting time"),
    ("max_waiting_time", "max waiting time"),
    ("cpu_utilization", "CPU utilization (%)"),
    ("makespan", "makespan"),
    ("bounded_slowdown", "bounded slowdown (tau=10)"),
    ("average_turnaround_time", "average turnaround time"),
    ("completed_jobs", "completed jobs"),
    ("throughput", "throughput (jobs/time unit)"),
    ("fairness_index", "fairness (Jain, slowdowns)"),
    ("total_preemptions", "preemptions"),
]

# `plot` default: the five comparisons of the brief (§2.4) plus max wait and fairness.
PLOT_METRICS = ["average_waiting_time", "average_turnaround_time", "cpu_utilization", "makespan",
                "bounded_slowdown", "max_waiting_time", "fairness_index"]


def _engine_banner(engine):
    if engine == "fake":
        print("engine: fake (test infrastructure, not study results)")


def _run(args):
    from pathlib import Path

    from adaptivesched.experiments.config import load_run_config
    from adaptivesched.experiments.export import write_run
    from adaptivesched.experiments.runner import run_one

    cfg = load_run_config(args.config)
    outcome = run_one(cfg, ADAPTERS[args.engine]())
    if outcome.status == "failed":
        raise RuntimeError(f"run failed (strategy={cfg.strategy}, workload={outcome.workload_id}, "
                           f"cluster_cores={cfg.cluster_cores}): {outcome.error}")
    s, meta = outcome.summary, outcome.summary["metadata"]
    _engine_banner(args.engine)
    print(f"run_id {meta['run_id']}  strategy {s['strategy']}  workload {s['workload']}  "
          f"cluster_cores {s['cluster_cores']}  jobs {s['total_jobs']}")
    for key, label in METRIC_LABELS:
        v = s[key]
        print(f"  {label:<28} {v:.3f}" if isinstance(v, float) else f"  {label:<28} {v}")
    print(f"  {'preemptive':<28} {'yes' if s['preemptive'] else 'no'}")
    print(f"dispatch: {meta['strategy_dispatch_note']}")
    for p in write_run(outcome, Path(cfg.output_dir) / "runs"):
        print(f"wrote {p.as_posix()}")


def _batch(args):
    from adaptivesched.experiments.batch import read_batch_summary, run_batch
    from adaptivesched.experiments.config import load_batch_config

    cfg = load_batch_config(args.config)
    out = run_batch(cfg, ADAPTERS[args.engine](), args.engine)
    rows = read_batch_summary(out)
    _engine_banner(args.engine)
    failed = [r for r in rows if r["status"] == "failed"]
    print(f"batch {out.as_posix()}: {len(rows)} runs attempted, {len(rows) - len(failed)} ok, {len(failed)} failed")
    for r in failed:
        print(f"  failed: strategy={r['strategy']} workload={r['workload_id']}: {r['error']}")
    print(f"next: adaptivesched compare --batch {out.as_posix()}")
    return 1 if failed else 0


def _compare(args):
    from adaptivesched.experiments.compare import compare

    csv_path, md_path, md = compare(args.batch)
    print(md)
    print(f"wrote {csv_path.as_posix()}\nwrote {md_path.as_posix()}")


def _plot(args):
    from pathlib import Path

    from adaptivesched.analysis import plots
    from adaptivesched.analysis.gantt import gantt_pair
    from adaptivesched.experiments.compare import load_rows

    batch = Path(args.batch)
    rows = load_rows(batch)  # fails clearly if this is not a batch directory
    out = batch / "plots"
    safe = lambda wid: re.sub(r"[:/\\]", "_", wid)  # workload id -> file name
    written = []
    if args.gantt:
        workload, a, b = args.gantt
        written += gantt_pair(batch, workload, a, b, out / f"gantt_{safe(workload)}_{a}_vs_{b}")
    else:
        for metric in args.metric:
            written += plots.metric_grid(batch, metric, out / f"grid_{metric}")
        written += plots.tradeoff_scatter(batch, out / "tradeoff_avg_vs_max_wait")
        for wid in dict.fromkeys(r["workload_id"] for r in rows if r["status"] == "ok"):
            written += plots.waiting_time_cdf(batch, wid, out / f"cdf_{safe(wid)}")
    for p in written:
        print(f"wrote {p.as_posix()}")


def _findings(args):
    from adaptivesched.analysis.findings import tradeoff_table, write_skeleton

    print(tradeoff_table(args.batch))
    print(f"wrote {write_skeleton(args.batch).as_posix()}")


def _inspect(args):
    from adaptivesched.analysis.inspect import inspect_job

    text, ok = inspect_job(args.run, args.job)
    print(text)
    return 0 if ok else 1


def _serve(args):
    from adaptivesched.api.server import serve

    serve(args.host, args.port, args.results, engine=args.engine)


def _tune(args):
    import glob
    from pathlib import Path

    from adaptivesched.experiments.tune import tune

    windows = sorted(glob.glob(args.windows))
    if not windows:
        raise ValueError(f"--windows {args.windows!r} matches no file")
    defaults = {"age_weight": 0.4, "short_weight": 0.4, "size_weight": 0.2, "max_age": 500.0,
                "adaptation_gain": 0.5, "reservation_xf": 2.0, "preemptive": False, "preempt_margin": 0.1}
    res = tune(windows, args.out, args.trials, seed=args.seed, workers=args.workers,
               preemptive={"any": None, "on": True, "off": False}[args.preemptive],
               extra={"defaults": defaults, "age7d": {**defaults, "max_age": 604800.0}})
    for k in ("best", "best_non_preemptive", "best_preemptive"):
        r = res[k]
        if r:
            print(f"{k:20} J {r['J']:+.3f}  bsld x{r['bsld_ratio']:.2f}  max wait x{r['max_wait_ratio']:.2f}  "
                  f"avg wait x{r['avg_wait_ratio']:.2f} (vs easy_backfill)")
    print(f"{res['evaluated']} candidates on {len(windows)} windows; wrote {Path(args.out).as_posix()}/result.json, candidates.csv")


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--engine", choices=sorted(ADAPTERS), default="team",
                        help="simulation engine: 'team' (default) or 'fake' (in-repo test infrastructure)")

    parser = argparse.ArgumentParser(
        prog="adaptivesched",
        description="Run scheduling strategies on the same workload and CPU core capacity, "
                    "and compare them with shared metric definitions.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("strategies", parents=[common], help="list registered strategy identifiers"
                   ).set_defaults(func=_strategies)
    w = sub.add_parser("workloads", help="list named synthetic workloads, or validate and print one as CSV")
    w.add_argument("--show", metavar="WORKLOAD", help="synthetic id or CSV path to validate and print")
    w.add_argument("--cluster-cores", type=int, help="CPU core capacity (required with --show)")
    w.add_argument("--head", type=int, help="print only the first N jobs")
    w.add_argument("--from-swf", metavar="SWF", help="convert a Parallel Workloads Archive log (.swf or .swf.gz)")
    w.add_argument("--jobs", type=int, default=5000, help="with --from-swf: consecutive jobs to keep (default 5000)")
    w.add_argument("--start", type=int, help="with --from-swf: index of the first usable job (default: centred)")
    w.add_argument("--out", help="with --from-swf: CSV file to write")
    w.set_defaults(func=_workloads)
    r = sub.add_parser("run", parents=[common], help="run one strategy on one workload and capacity")
    r.add_argument("--config", required=True, help="run config YAML (workload, strategy, cluster_cores)")
    r.set_defaults(func=_run)
    b = sub.add_parser("batch", parents=[common], help="run every strategy on every workload (x seeds)")
    b.add_argument("--config", required=True, help="batch config YAML (workloads, strategies, cluster_cores)")
    b.set_defaults(func=_batch)
    c = sub.add_parser("compare", help="tabulate a batch: one table per workload and CPU core capacity")
    c.add_argument("--batch", required=True, help="batch directory written by `adaptivesched batch`")
    c.set_defaults(func=_compare)
    p = sub.add_parser("plot", help="comparison plots, or a Gantt chart pair, from a batch directory")
    p.add_argument("--batch", required=True, help="batch directory written by `adaptivesched batch`")
    p.add_argument("--metric", nargs="+", default=PLOT_METRICS,
                   help="metrics for the small-multiples grids (default: the seven comparison metrics)")
    p.add_argument("--gantt", nargs=3, metavar=("WORKLOAD", "A", "B"),
                   help="Gantt charts of strategies A and B on one workload id, stacked")
    p.set_defaults(func=_plot)
    f = sub.add_parser("findings", help="trade-off table and a findings skeleton (numbers only) for a batch")
    f.add_argument("--batch", required=True, help="batch directory written by `adaptivesched batch`")
    f.set_defaults(func=_findings)
    i = sub.add_parser("inspect", help="show one job's execution record and check its invariants")
    i.add_argument("--run", required=True, help="results/batch_xxx/runs/<run_id>")
    i.add_argument("--job", required=True, help="job_id (integer or string id)")
    i.set_defaults(func=_inspect)
    t = sub.add_parser("tune", help="search adaptive_multifactor's parameters on training windows")
    t.add_argument("--windows", required=True, help="glob of converted CSV windows, e.g. '../workloads/pwa/train/*.csv'")
    t.add_argument("--trials", type=int, default=160, help="random-search candidates before refinement")
    t.add_argument("--seed", type=int, default=2026)
    t.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1), help="parallel simulations")
    t.add_argument("--out", default="results/tuning")
    t.add_argument("--preemptive", choices=["any", "on", "off"], default="any",
                   help="search preemption (any) or fix it on/off for every candidate")
    t.set_defaults(func=_tune)
    s = sub.add_parser("serve", parents=[common], help="web dashboard and HTTP API on the same runner")
    s.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1: this machine only)")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--results", default="results/web", help="directory experiments are stored in")
    s.set_defaults(func=_serve)

    args = parser.parse_args(argv)
    try:
        return args.func(args) or 0
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
