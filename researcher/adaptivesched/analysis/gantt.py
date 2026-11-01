"""Gantt charts from recorded start/finish times only (SPEC §4.2, UC-R04).

Rows are CPU cores; lanes are assigned first-fit over start time for drawing only (the
records do not say which physical cores a job used). Idle core-time is the light background.
"""
from __future__ import annotations

import heapq
from pathlib import Path

from matplotlib.ticker import MaxNLocator

from adaptivesched.analysis.style import IDLE, SURFACE, TEXT_2, color, plt, save
from adaptivesched.experiments.compare import comparison_table, load_rows
from adaptivesched.experiments.export import read_records
from adaptivesched.metrics.definitions import average_waiting_time, max_waiting_time

MAX_CORES = 64


def lane_segments(records, cluster_cores) -> list[tuple[int, int, int, int, int]]:
    """(job_id, start, finish, first_lane, n_lanes) per contiguous block of lanes a job holds.

    At each time, completions free lanes before starts take them; a job takes the
    lowest-numbered free lanes.
    """
    events = sorted([(r.finish_time, 0, r) for r in records] + [(r.start_time, 1, r) for r in records],
                    key=lambda e: (e[0], e[1], e[2].job_id))
    free = list(range(cluster_cores))
    held, out = {}, []
    for _, kind, r in events:
        if kind == 0:
            for lane in held.pop(r.job_id):
                heapq.heappush(free, lane)
            continue
        if len(free) < r.required_cores:
            raise ValueError(f"t={r.start_time}: job {r.job_id} needs {r.required_cores} CPU cores, "
                             f"{len(free)} free in the records")
        lanes = sorted(heapq.heappop(free) for _ in range(r.required_cores))
        held[r.job_id] = lanes
        block = [lanes[0]]
        for lane in lanes[1:] + [None]:
            if lane is not None and lane == block[-1] + 1:
                block.append(lane)
            else:
                out.append((r.job_id, r.start_time, r.finish_time, block[0], len(block)))
                if lane is not None:
                    block = [lane]
    return out


def gantt_pair(batch_dir, workload_id, strategy_a, strategy_b, out_stem):
    batch_dir = Path(batch_dir)
    rows = {r["strategy"]: r for r in load_rows(batch_dir)
            if r["workload_id"] == workload_id and r["status"] == "ok"}
    missing = [s for s in (strategy_a, strategy_b) if s not in rows]
    if missing:
        raise ValueError(f"no ok run for strategy {', '.join(missing)} on workload {workload_id} in {batch_dir}")
    comparison_table([rows[strategy_a], rows[strategy_b]])
    cores = rows[strategy_a]["cluster_cores"]
    if cores > MAX_CORES:
        # ponytail: band mode (rows of 8 cores) not built; SPEC lists it first to cut.
        raise ValueError(f"Gantt draws at most {MAX_CORES} CPU cores, this run has {cores}")

    recs = {s: read_records(batch_dir / "runs" / f"{rows[s]['run_id']}.records.csv")
            for s in (strategy_a, strategy_b)}
    end = max(r.finish_time for rr in recs.values() for r in rr)
    start = min(r.arrival_time for rr in recs.values() for r in rr)
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(11, max(3.6, 1.2 + 0.28 * cores * 2)))
    caption = []
    for ax, s in zip(axes, (strategy_a, strategy_b)):
        ax.broken_barh([(start, end - start)], (0, cores), facecolors=IDLE)
        for _, t0, t1, lane, n in lane_segments(recs[s], cores):
            ax.broken_barh([(t0, t1 - t0)], (lane, n), facecolors=color(s), edgecolors=SURFACE, linewidth=0.6)
        ax.set_ylim(0, cores)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        ax.set_ylabel(f"{s}\nCPU core lane")
        ax.grid(False)
        caption.append(f"{s}: average waiting time {average_waiting_time(recs[s]):.1f}, "
                       f"max waiting time {max_waiting_time(recs[s])}")
    axes[-1].set_xlabel("time")
    axes[0].set_title(f"Gantt chart - {workload_id} - {cores} CPU cores (grey: idle core-time)")
    fig.text(0.01, -0.01, "   |   ".join(caption), color=TEXT_2, ha="left", va="top")
    fig.tight_layout()
    return save(fig, out_stem)
