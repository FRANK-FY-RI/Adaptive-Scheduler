"""RES-FR-10: one table per (workload id, CPU cores); strategies as rows, metrics as columns.

Runs with different workload ids or capacities never share a table (CLAUDE.md hard rule 2).
Failed runs appear as rows with status `failed` and their error.
"""
from __future__ import annotations

import csv
from pathlib import Path

from adaptivesched.experiments.batch import read_batch_summary
from adaptivesched.experiments.export import read_json

METRICS = ["average_waiting_time", "max_waiting_time", "cpu_utilization", "makespan",
           "bounded_slowdown", "average_turnaround_time"]
COLUMNS = ["workload_id", "cluster_cores", "strategy", "status", *METRICS, "run_id", "error"]


def load_rows(batch_dir) -> list[dict]:
    """batch_summary rows, each with its summary metrics if the run is ok."""
    batch_dir = Path(batch_dir)
    rows = []
    for r in read_batch_summary(batch_dir):
        row = {k: r[k] for k in ("workload_id", "strategy", "status", "run_id", "error")}
        row["cluster_cores"] = int(r["cluster_cores"])
        if r["status"] == "ok":
            s = read_json(batch_dir / "runs" / f"{r['run_id']}.summary.json")
            row.update({m: s[m] for m in METRICS})
            row["engine"] = s["metadata"]["engine"]
        rows.append(row)
    return rows


def comparison_table(rows: list[dict]) -> list[dict]:
    """Rows for one table. Refuses rows from more than one workload id or capacity."""
    keys = {(r["workload_id"], r["cluster_cores"]) for r in rows}
    if len(keys) != 1:
        raise ValueError("refusing to compare runs with different workload ids or CPU core capacities: "
                         + "; ".join(f"{w} @ {c} cores" for w, c in sorted(keys)))
    return rows


def group(rows: list[dict]) -> dict[tuple[str, int], list[dict]]:
    groups: dict[tuple[str, int], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["workload_id"], r["cluster_cores"]), []).append(r)
    return {k: comparison_table(v) for k, v in groups.items()}


def _fmt(v) -> str:
    return "" if v is None else f"{v:.3f}" if isinstance(v, float) else str(v)


def to_markdown(groups) -> str:
    out = []
    for (workload, cores), rows in groups.items():
        engines = {r.get("engine") for r in rows} - {None}
        note = " (engine: fake, test infrastructure, not study results)" if engines == {"fake"} else ""
        out += [f"### {workload} - {cores} CPU cores{note}", "",
                "| strategy | status | " + " | ".join(METRICS) + " |",
                "|---|---|" + "---:|" * len(METRICS)]
        for r in rows:
            cells = [_fmt(r.get(m)) for m in METRICS] if r["status"] == "ok" \
                else [f"failed: {r['error']}"] + [""] * (len(METRICS) - 1)
            out.append(f"| {r['strategy']} | {r['status']} | " + " | ".join(cells) + " |")
        out.append("")
    return "\n".join(out)


def compare(batch_dir) -> tuple[Path, Path, str]:
    batch_dir = Path(batch_dir)
    groups = group(load_rows(batch_dir))
    csv_path, md_path = batch_dir / "compare.csv", batch_dir / "compare.md"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLUMNS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for rows in groups.values():
            w.writerows(rows)
    md = to_markdown(groups)
    md_path.write_text(md, encoding="utf-8", newline="\n")
    return csv_path, md_path, md
