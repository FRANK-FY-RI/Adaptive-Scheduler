"""The numbers a finding needs (docs/STUDY.md §3-4); the interpretation is written by a person.

Strategies are ranked inside one workload id (one seed) and the ranks are then counted
across seeds - values are never averaged across workload ids (CLAUDE.md hard rule 2).
"""
from __future__ import annotations

from pathlib import Path

from adaptivesched.analysis.style import split_seed
from adaptivesched.experiments.compare import group, load_rows

# Lower is better for all four. cpu_utilization and average_turnaround_time are left out:
# in this model they rank exactly like makespan and average_waiting_time (same jobs, same
# runtimes), so counting them would count the same result twice.
RANKED = ["average_waiting_time", "max_waiting_time", "makespan", "bounded_slowdown"]
SHORT = {"average_waiting_time": "avg wait", "max_waiting_time": "max wait",
         "makespan": "makespan", "bounded_slowdown": "slowdown"}


def seed_results(batch_dir) -> dict:
    """{(condition, cores): [one dict per seed: {"workload_id", "rows", metric: (best, worst)}]}.

    best/worst are the sets of strategies with the lowest/highest value; both are empty
    when every strategy has the same value (a tie is not a lead). Failed runs are not ranked.
    """
    out: dict = {}
    for (wid, cores), rows in group(load_rows(batch_dir)).items():
        ok = [r for r in rows if r["status"] == "ok"]
        seed = {"workload_id": wid, "rows": rows}
        for m in RANKED:
            vals = {r["strategy"]: r[m] for r in ok}
            lo, hi = min(vals.values()), max(vals.values())
            seed[m] = (set(), set()) if lo == hi else \
                ({s for s, v in vals.items() if v == lo}, {s for s, v in vals.items() if v == hi})
        out.setdefault((split_seed(wid)[0], cores), []).append(seed)
    return out


def _counts(seeds, strategy, which) -> str:
    """'avg wait 3/3, slowdown 2/3' - metrics where `strategy` led (which=0) or trailed (which=1)."""
    n = len(seeds)
    parts = [f"{SHORT[m]} {k}/{n}" for m in RANKED
             if (k := sum(strategy in s[m][which] for s in seeds))]
    return ", ".join(parts) or "-"


def tradeoff_table(batch_dir) -> str:
    """Strategies x conditions; each cell: metrics the strategy led / trailed on, in k of n seeds."""
    res = seed_results(batch_dir)
    strategies = list(dict.fromkeys(r["strategy"] for seeds in res.values() for s in seeds for r in s["rows"]))
    head = [f"{c.removeprefix('synth:')} ({cores} CPU cores)" for c, cores in res]
    lines = ["| strategy | " + " | ".join(head) + " |", "|---|" + "---|" * len(head)]
    for st in strategies:
        cells = [f"led: {_counts(seeds, st, 0)}<br>trailed: {_counts(seeds, st, 1)}" for seeds in res.values()]
        lines.append(f"| {st} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def skeleton(batch_dir) -> str:
    """One finding stub per condition with leaders, values and run ids filled in."""
    out = ["# Findings skeleton (generated - numbers only; write the interpretation by hand)", "",
           "Ranked within each seed, counted across seeds. Format: docs/STUDY.md §3.", "",
           "## Trade-off table", "", tradeoff_table(batch_dir), ""]
    for i, ((cond, cores), seeds) in enumerate(seed_results(batch_dir).items(), 1):
        out += [f"## F{i} - {cond} - {cores} CPU cores", ""]
        for m in RANKED:
            per_seed = []
            for s in seeds:
                vals = {r["strategy"]: r.get(m) for r in s["rows"] if r["status"] == "ok"}
                best, worst = s[m]
                fmt = lambda names: "/".join(sorted(names)) or "all tied"
                per_seed.append(f"seed {split_seed(s['workload_id'])[1]}: lowest {fmt(best)} "
                                f"({min(vals.values()):g}), highest {fmt(worst)} ({max(vals.values()):g})")
            out.append(f"- {SHORT[m]}: " + "; ".join(per_seed))
        failed = [f"{r['strategy']} on {s['workload_id']}" for s in seeds for r in s["rows"] if r["status"] != "ok"]
        out += [f"- failed runs: {', '.join(failed) or 'none'}",
                "- evidence (run ids): " + ", ".join(f"{r['strategy']}={r['run_id']}" for s in seeds for r in s["rows"]),
                "", "Observation:", "Trade-off:", "Interpretation:", "Confidence:", ""]
    return "\n".join(out)


def write_skeleton(batch_dir) -> Path:
    path = Path(batch_dir) / "findings_skeleton.md"
    path.write_text(skeleton(batch_dir), encoding="utf-8", newline="\n")
    return path
