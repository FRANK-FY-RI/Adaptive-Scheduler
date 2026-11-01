"""Comparison plots (SPEC §4.1). Read records and summaries from disk only; never import the
engine or a strategy (RES-NFR-06). Every title names the metric, workload and CPU cores."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from adaptivesched.analysis.style import (CONDITION_MARKERS, TEXT_2, color, plt, save,
                                          split_seed)
from adaptivesched.experiments.compare import comparison_table, group, load_rows
from adaptivesched.experiments.export import read_records


def _ok(rows):
    return [r for r in rows if r["status"] == "ok"]


def _bars(ax, rows, metric):
    rows = comparison_table(rows)
    names = [r["strategy"] for r in rows]
    values = [r.get(metric) or 0 for r in rows]
    ax.bar(names, values, color=[color(n) for n in names], width=0.6, edgecolor="white", linewidth=1)
    for i, r in enumerate(rows):
        if r["status"] != "ok":
            ax.text(i, 0, "failed", ha="center", va="bottom", color=TEXT_2)
    # zero-based via the bars' sticky edges; never set_ylim here: on sharey="row" it freezes
    # the row at the first panel's data and clips the others
    ax.tick_params(axis="x", labelrotation=30)
    plt.setp(ax.get_xticklabels(), ha="right", rotation_mode="anchor")
    ax.grid(axis="x", visible=False)


def metric_bars(rows, metric, out_stem):
    """One workload and capacity: strategies on x, the metric on y."""
    rows = comparison_table(rows)
    fig, ax = plt.subplots(figsize=(4, 3))
    _bars(ax, rows, metric)
    ax.set_title(f"{metric}\n{rows[0]['workload_id']} - {rows[0]['cluster_cores']} CPU cores")
    ax.set_ylabel(metric)
    return save(fig, out_stem)


def metric_grid(batch_dir, metric, out_stem):
    """Small multiples: one row per workload condition, one column per seed, bars per strategy.
    Rows share a y-scale so seeds can be compared; conditions have their own scales."""
    by_id = group(load_rows(batch_dir))  # {(workload_id, cluster_cores): rows}
    conditions = list(dict.fromkeys(split_seed(w)[0] for w, _ in by_id))
    seeds = list(dict.fromkeys(split_seed(w)[1] for w, _ in by_id))
    cores = {c for _, c in by_id}
    fig, axes = plt.subplots(len(conditions), len(seeds), squeeze=False, sharey="row",
                             figsize=(2.4 * len(seeds) + 1, 1.9 * len(conditions) + 0.6))
    for (wid, c), rows in by_id.items():
        cond, seed = split_seed(wid)
        ax = axes[conditions.index(cond)][seeds.index(seed)]
        _bars(ax, rows, metric)
        ax.set_title(wid if seed is None else f"{cond.removeprefix('synth:')}  seed {seed}")
    for ax in axes.flat:
        if not ax.has_data():
            ax.set_visible(False)
    fig.suptitle(f"{metric} by strategy - {', '.join(map(str, sorted(cores)))} CPU cores "
                 f"(rows: workload condition, columns: seed)", color=TEXT_2)
    fig.tight_layout()
    return save(fig, out_stem)


def tradeoff_scatter(batch_dir, out_stem, x="average_waiting_time", y="max_waiting_time"):
    """One point per (strategy, workload): colour = strategy, marker = workload condition."""
    rows = _ok(load_rows(batch_dir))
    conditions = list(dict.fromkeys(split_seed(r["workload_id"])[0] for r in rows))
    strategies = list(dict.fromkeys(r["strategy"] for r in rows))
    cores = sorted({r["cluster_cores"] for r in rows})
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    for r in rows:
        m = CONDITION_MARKERS[conditions.index(split_seed(r["workload_id"])[0]) % len(CONDITION_MARKERS)]
        ax.scatter(r[x], r[y], s=40, marker=m, color=color(r["strategy"]), edgecolor="white", linewidth=1)
    ax.set_xscale("symlog", linthresh=1)
    ax.set_yscale("symlog", linthresh=1)
    ax.set_xlabel(f"{x} (log scale)")
    ax.set_ylabel(f"{y} (log scale)")
    ax.set_title(f"{y} vs {x}, one point per strategy and workload - {', '.join(map(str, cores))} CPU cores")
    s_handles = [plt.Line2D([], [], ls="", marker="o", color=color(s), label=s) for s in strategies]
    c_handles = [plt.Line2D([], [], ls="", marker=CONDITION_MARKERS[i % len(CONDITION_MARKERS)],
                            color=TEXT_2, label=c.removeprefix("synth:")) for i, c in enumerate(conditions)]
    leg = ax.legend(handles=s_handles, title="strategy", loc="upper left", bbox_to_anchor=(1.01, 1))
    ax.add_artist(leg)
    ax.legend(handles=c_handles, title="workload", loc="upper left", bbox_to_anchor=(1.01, 0.6))
    return save(fig, out_stem)


def waiting_time_cdf(batch_dir, workload_id, out_stem):
    """Fraction of jobs that waited at most t, one curve per strategy: the tail averages hide."""
    batch_dir = Path(batch_dir)
    rows = comparison_table([r for r in _ok(load_rows(batch_dir)) if r["workload_id"] == workload_id])
    fig, ax = plt.subplots(figsize=(6, 3.6))
    for r in rows:
        waits = np.sort([rec.waiting_time for rec in read_records(batch_dir / "runs" / f"{r['run_id']}.records.csv")])
        frac = np.arange(1, len(waits) + 1) / len(waits)
        ax.step(waits, frac, where="post", color=color(r["strategy"]), linewidth=2, label=r["strategy"])
    ax.set_ylim(0, 1.02)
    ax.set_xlim(left=0)
    ax.set_xlabel("waiting time")
    ax.set_ylabel("fraction of jobs waiting at most this long")
    ax.set_title(f"waiting time distribution\n{workload_id} - {rows[0]['cluster_cores']} CPU cores")
    ax.legend(title="strategy", loc="lower right")
    return save(fig, out_stem)
