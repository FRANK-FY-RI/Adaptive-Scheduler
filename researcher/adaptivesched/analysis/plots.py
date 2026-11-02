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
    """Small multiples, one panel per workload condition; one point per (strategy, seed):
    colour = strategy, marker = seed. Each strategy is direct-labelled once per panel, so
    identity does not rest on colour when more than three strategies share a panel."""
    rows = _ok(load_rows(batch_dir))
    conditions = list(dict.fromkeys(split_seed(r["workload_id"])[0] for r in rows))
    seeds = list(dict.fromkeys(split_seed(r["workload_id"])[1] for r in rows))
    strategies = list(dict.fromkeys(r["strategy"] for r in rows))
    cores = sorted({r["cluster_cores"] for r in rows})
    cols = min(3, len(conditions))
    nrows = -(-len(conditions) // cols)
    fig, axes = plt.subplots(nrows, cols, squeeze=False, figsize=(4.2 * cols + 1.6, 3.4 * nrows))
    for i, cond in enumerate(conditions):
        ax = axes[i // cols][i % cols]
        labelled = set()
        for r in (r for r in rows if split_seed(r["workload_id"])[0] == cond):
            m = CONDITION_MARKERS[seeds.index(split_seed(r["workload_id"])[1]) % len(CONDITION_MARKERS)]
            ax.scatter(r[x], r[y], s=40, marker=m, color=color(r["strategy"]), edgecolor="white", linewidth=1)
            if r["strategy"] not in labelled:
                labelled.add(r["strategy"])
                ax.annotate(r["strategy"], (r[x], r[y]), xytext=(4, 3), textcoords="offset points",
                            fontsize=6.5, color=TEXT_2)
        ax.set_xscale("symlog", linthresh=1)
        ax.set_yscale("symlog", linthresh=1)
        ax.set_title(cond.removeprefix("synth:"))
        ax.set_xlabel(f"{x} (log scale)")
        ax.set_ylabel(f"{y} (log scale)")
    for ax in axes.flat[len(conditions):]:
        ax.set_visible(False)
    fig.suptitle(f"{y} vs {x} by workload condition - {', '.join(map(str, cores))} CPU cores", color=TEXT_2)
    s_handles = [plt.Line2D([], [], ls="", marker="o", color=color(s), label=s) for s in strategies]
    m_handles = [plt.Line2D([], [], ls="", marker=CONDITION_MARKERS[i % len(CONDITION_MARKERS)],
                            color=TEXT_2, label=f"seed {s}" if s is not None else "csv") for i, s in enumerate(seeds)]
    fig.legend(handles=s_handles + m_handles, loc="upper left", bbox_to_anchor=(1.0, 0.95))
    fig.tight_layout()
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
        # direct label where the curve reaches 90%: identity is not colour alone past 3 series
        k = min(int(np.searchsorted(frac, 0.9)), len(waits) - 1)
        ax.annotate(r["strategy"], (waits[k], frac[k]), xytext=(4, -2), textcoords="offset points",
                    fontsize=7, color=TEXT_2)
    ax.set_ylim(0, 1.02)
    ax.set_xlim(left=0)
    ax.set_xlabel("waiting time")
    ax.set_ylabel("fraction of jobs waiting at most this long")
    ax.set_title(f"waiting time distribution\n{workload_id} - {rows[0]['cluster_cores']} CPU cores")
    ax.legend(title="strategy", loc="lower right")
    return save(fig, out_stem)
