"""`adaptivesched` command line."""
from __future__ import annotations

import argparse
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
]


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
    p.add_argument("--metric", nargs="+", default=["average_waiting_time", "max_waiting_time"],
                   help="metrics for the small-multiples grid")
    p.add_argument("--gantt", nargs=3, metavar=("WORKLOAD", "A", "B"),
                   help="Gantt charts of strategies A and B on one workload id, stacked")
    p.set_defaults(func=_plot)
    f = sub.add_parser("findings", help="trade-off table and a findings skeleton (numbers only) for a batch")
    f.add_argument("--batch", required=True, help="batch directory written by `adaptivesched batch`")
    f.set_defaults(func=_findings)
    i = sub.add_parser("inspect", help="show one job's execution record and check its invariants")
    i.add_argument("--run", required=True, help="results/batch_xxx/runs/<run_id>")
    i.add_argument("--job", required=True, type=int, help="job_id")
    i.set_defaults(func=_inspect)

    args = parser.parse_args(argv)
    try:
        return args.func(args) or 0
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
