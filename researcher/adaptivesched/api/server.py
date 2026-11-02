"""Stdlib HTTP API + static dashboard. Every experiment is an ordinary batch run by
experiments.batch.run_batch, so results are byte-for-byte what the CLI writes; the API only
validates input, queues the batch on a background thread and serves the files it wrote.

Experiment store: <results>/<experiment_id>/experiment.json (+ the batch_<id>/ directory).
No database: the files are the record, and a restarted server lists them again.
"""
from __future__ import annotations

import inspect
import json
import math
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from adaptivesched.experiments.adapter import ADAPTERS
from adaptivesched.experiments.batch import read_batch_summary, run_batch
from adaptivesched.experiments.config import batch_config_from_dict
from adaptivesched.experiments.export import read_json, read_records, write_json
from adaptivesched.workloads.validate import ValidationError

WEB = Path(__file__).resolve().parent.parent / "web"
PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # researcher/
CSV_DIRS = [PACKAGE_ROOT.parent / "workloads", PACKAGE_ROOT / "tests" / "workloads"]
PLOT_METRICS = ["average_waiting_time", "average_turnaround_time", "cpu_utilization", "makespan",
                "bounded_slowdown", "max_waiting_time", "fairness_index", "throughput"]
MAX_RUNS = 500  # one request may not queue more runs than this
GANTT_MAX_CORES = 2048  # real machines in workloads/pwa have up to 1,152 CPU cores


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _jsonable(v):
    if isinstance(v, float) and not math.isfinite(v):
        return str(v)
    return v if isinstance(v, (str, int, float, bool, type(None))) else repr(v)


class Store:
    """Experiments on disk plus the in-memory progress of the running ones."""

    def __init__(self, root, engine: str = "team", csv_dirs=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.engine = engine
        self.adapter = ADAPTERS[engine]()
        self.csv_dirs = [Path(d) for d in (csv_dirs or CSV_DIRS)]
        self.lock = threading.Lock()
        # ponytail: one worker thread runs experiments in submission order; API reads never wait on it.
        # Add workers (or processes) if several researchers share one server.
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="experiment")
        for p in self.root.glob("*/experiment.json"):  # a run cut off by a restart is reported, not hidden
            e = read_json(p)
            if e["status"] in ("queued", "running"):
                e.update(status="interrupted", error="server stopped before the experiment finished")
                write_json(e, p)

    # ---- catalog -----------------------------------------------------------------------

    def policies(self) -> list[dict]:
        if self.engine == "fake":
            return [{"id": s, "name": s, "doc": "fake engine (test infrastructure)", "preemptive_capable": False,
                     "params": []} for s in self.adapter.strategies()]
        from adaptive_scheduler.policies import discover_policies

        found = discover_policies()
        out = []
        for pid in self.adapter.strategies():
            cls = found[pid]
            params = [{"name": n, "default": _jsonable(p.default),
                       "type": type(p.default).__name__ if p.default is not inspect.Parameter.empty else "any"}
                      for n, p in inspect.signature(cls.__init__).parameters.items()
                      if n != "self" and p.kind is p.KEYWORD_ONLY]
            out.append({"id": pid, "name": getattr(cls, "name", pid), "doc": inspect.cleandoc(cls.__doc__ or ""),
                        "preemptive_capable": callable(getattr(cls, "select_jobs_to_preempt", None)),
                        "params": params,
                        "presets": {name: {k: _jsonable(v) for k, v in values.items()}
                                    for name, values in getattr(cls, "PRESETS", {}).items()}})
        return out

    def workloads(self) -> dict:
        from adaptivesched.workloads.generators import GENERATORS
        from adaptivesched.workloads.swf import declared_cores

        csvs = sorted({p.resolve() for d in self.csv_dirs if d.is_dir()
                       for p in [*d.glob("*.csv"), *d.glob("pwa/*.csv")]})
        return {"synthetic": [{"name": n, "offered_load": load, "description": desc,
                               "id_template": f"synth:{n}:n=<n_jobs>:seed=<seed>"}
                              for n, (load, _, desc) in GENERATORS.items()],
                "csv": [{"name": p.name, "path": str(p), "cluster_cores": declared_cores(p)} for p in csvs]}

    # ---- experiments -------------------------------------------------------------------

    def _dir(self, exp_id: str) -> Path:
        if not re.fullmatch(r"[0-9]{8}T[0-9]{6}-[0-9a-f]{6}", exp_id):
            raise ApiError(404, f"no experiment {exp_id!r}")
        d = self.root / exp_id
        if not (d / "experiment.json").exists():
            raise ApiError(404, f"no experiment {exp_id!r}")
        return d

    def get(self, exp_id: str) -> dict:
        d = self._dir(exp_id)
        with self.lock:
            e = read_json(d / "experiment.json")
        if e.get("batch_dir") and (Path(e["batch_dir"]) / "batch_summary.csv").exists():
            from adaptivesched.experiments.compare import load_rows

            e["manifest"] = read_json(Path(e["batch_dir"]) / "batch_manifest.json")
            e["rows"] = load_rows(e["batch_dir"])
        return e

    def list(self) -> list[dict]:
        with self.lock:
            exps = [read_json(p) for p in self.root.glob("*/experiment.json")]
        return sorted(exps, key=lambda e: e["id"], reverse=True)

    def _validate(self, body) -> tuple[dict, object]:
        if not isinstance(body, dict):
            raise ApiError(400, "request body must be a JSON object")
        allowed = {"name", "workloads", "strategies", "cluster_cores", "strategy_params", "variants", "seeds"}
        if extra := set(body) - allowed:
            raise ApiError(400, f"unknown field(s) {sorted(extra)}; allowed: {sorted(allowed)}")
        name = body.get("name", "")
        if not isinstance(name, str) or len(name) > 200:
            raise ApiError(400, "name must be a string of at most 200 characters")
        d = {k: body[k] for k in ("workloads", "strategies", "cluster_cores", "strategy_params", "variants")
             if k in body}
        # JSON has no infinity: the dashboard sends "inf" (e.g. reservation_xf of a preset)
        inf = lambda params: {k: math.inf if isinstance(v, str) and v.strip().lower() in ("inf", "infinity") else v
                              for k, v in params.items()} if isinstance(params, dict) else params
        if isinstance(d.get("strategy_params"), dict):
            d["strategy_params"] = {s: inf(p) for s, p in d["strategy_params"].items()}
        if isinstance(d.get("variants"), dict):
            d["variants"] = {s: {**v, "params": inf(v.get("params", {}))} if isinstance(v, dict) else v
                             for s, v in d["variants"].items()}
        if body.get("seeds"):
            d["repeats"] = {"seeds": body["seeds"]}
        try:
            cfg = batch_config_from_dict(d, "request", strategy_files_allowed=False)
        except ValidationError as e:
            raise ApiError(400, str(e)) from None
        if len(cfg.runs()) > MAX_RUNS:
            raise ApiError(400, f"{len(cfg.runs())} runs requested; at most {MAX_RUNS} per experiment")
        catalog = {c["path"] for c in self.workloads()["csv"]}
        from adaptivesched.workloads import resolve

        for w in cfg.workload_ids():
            if not w.startswith("synth:") and str(Path(w).resolve()) not in catalog:
                raise ApiError(400, f"workload {w!r}: not a synthetic id and not a CSV listed by /api/workloads")
            try:
                resolve(w, cfg.cluster_cores)
            except ValidationError as e:
                raise ApiError(400, f"workload {w!r}: {e}") from None
        known = self.adapter.strategies()
        for label in cfg.strategies:
            base = cfg.variants.get(label, {}).get("strategy", label)
            if base not in known:
                raise ApiError(400, f"strategy {label!r}: unknown identifier {base!r}; available: {', '.join(known)}")
            params = cfg.variants[label].get("params", {}) if label in cfg.variants \
                else cfg.strategy_params.get(label, {})
            if self.engine == "team":
                from adaptive_scheduler.policies import get_policy

                try:
                    get_policy(base, **params)
                except Exception as e:  # ConfigurationError, TypeError for unknown parameters
                    raise ApiError(400, f"strategy {label!r} parameters {params}: {e}") from None
        # saved exactly as submitted, so a rerun replays the same request through the same checks
        return {"name": name, **{k: body[k] for k in sorted(allowed - {"name"}) if k in body}}, d

    def create(self, body) -> dict:
        request, d_cfg = self._validate(body)
        exp_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
        d = self.root / exp_id
        d.mkdir(parents=True)
        cfg = batch_config_from_dict({**d_cfg, "output_dir": str(d)}, "request", strategy_files_allowed=False)
        e = {"id": exp_id, "name": request["name"], "created": _now(), "request": request,
             "engine": self.engine, "status": "queued", "progress": [0, len(cfg.runs())],
             "error": "", "batch_dir": "", "finished": ""}
        write_json(e, d / "experiment.json")
        self.pool.submit(self._execute, exp_id, cfg)
        return e

    def _update(self, exp_id: str, **changes) -> None:
        p = self.root / exp_id / "experiment.json"
        with self.lock:
            e = read_json(p)
            e.update(changes)
            write_json(e, p)

    def _execute(self, exp_id: str, cfg) -> None:
        self._update(exp_id, status="running")
        try:
            out = run_batch(cfg, self.adapter, self.engine,
                            on_progress=lambda i, n: self._update(exp_id, progress=[i, n]))
            rows = read_batch_summary(out)
            failed = sum(r["status"] == "failed" for r in rows)
            self._update(exp_id, status="completed", batch_dir=str(out), finished=_now(),
                         runs_failed=failed, runs_ok=len(rows) - failed)
        except Exception as e:  # never leaves an experiment silently "running"
            self._update(exp_id, status="failed", error=f"{type(e).__name__}: {e}", finished=_now())

    def rerun(self, exp_id: str) -> dict:
        return self.create(self.get(exp_id)["request"])

    def run_files(self, exp_id: str, run_id: str) -> tuple[Path, Path]:
        e = self.get(exp_id)
        if not re.fullmatch(r"[0-9a-f]{12}", run_id) or not e.get("batch_dir"):
            raise ApiError(404, f"no run {run_id!r} in experiment {exp_id}")
        runs = Path(e["batch_dir"]) / "runs"
        rec, summ = runs / f"{run_id}.records.csv", runs / f"{run_id}.summary.json"
        if not rec.exists():
            raise ApiError(404, f"no run {run_id!r} in experiment {exp_id} (failed runs have no records)")
        return rec, summ

    def run_detail(self, exp_id: str, run_id: str) -> dict:
        from adaptivesched.analysis.gantt import lane_segments

        rec, summ = self.run_files(exp_id, run_id)
        summary = read_json(summ)
        records = read_records(rec)
        cores = summary["cluster_cores"]
        lanes = [list(s) for s in lane_segments(records, cores)] if cores <= GANTT_MAX_CORES else None
        return {"summary": summary, "lanes": lanes, "gantt_max_cores": GANTT_MAX_CORES,
                "records": [{"job_id": r.job_id, "arrival_time": r.arrival_time, "start_time": r.start_time,
                             "finish_time": r.finish_time, "runtime": r.runtime, "waiting_time": r.waiting_time,
                             "turnaround_time": r.finish_time - r.arrival_time,
                             "required_cores": r.required_cores, "preemption_count": r.preemption_count,
                             "execution_segments": [list(s) for s in r.segments()]} for r in records]}

    def compare_csv(self, exp_id: str) -> Path:
        from adaptivesched.experiments.compare import compare

        e = self.get(exp_id)
        if not e.get("batch_dir"):
            raise ApiError(409, f"experiment {exp_id} has no results yet (status {e['status']})")
        return compare(e["batch_dir"])[0]

    def plot(self, exp_id: str, metric: str) -> Path:
        from adaptivesched.analysis.plots import metric_grid

        if metric not in PLOT_METRICS:
            raise ApiError(404, f"no plot for {metric!r}; available: {', '.join(PLOT_METRICS)}")
        e = self.get(exp_id)
        if e["status"] != "completed" or not any(r["status"] == "ok" for r in e.get("rows", [])):
            raise ApiError(409, f"experiment {exp_id} has no ok runs to plot (status {e['status']})")
        stem = Path(e["batch_dir"]) / "plots" / f"grid_{metric}"
        if not stem.with_suffix(".png").exists():
            with self.lock:  # matplotlib's pyplot state is not thread-safe
                metric_grid(e["batch_dir"], metric, stem)
        return stem.with_suffix(".png")

    def overview(self) -> dict:
        exps = self.list()
        by_status: dict[str, int] = {}
        for e in exps:
            by_status[e["status"]] = by_status.get(e["status"], 0) + 1
        w = self.workloads()
        return {"total_experiments": len(exps), "by_status": by_status,
                "runs_ok": sum(e.get("runs_ok", 0) for e in exps),
                "runs_failed": sum(e.get("runs_failed", 0) for e in exps),
                "policies": [p["id"] for p in self.policies()],
                "workloads": len(w["synthetic"]) + len(w["csv"]), "engine": self.engine,
                "recent": exps[:8]}


ROUTES = [
    ("GET", r"/api/health", lambda s, m, q: {"ok": True}),
    ("GET", r"/api/overview", lambda s, m, q: s.overview()),
    ("GET", r"/api/policies", lambda s, m, q: s.policies()),
    ("GET", r"/api/workloads", lambda s, m, q: s.workloads()),
    ("GET", r"/api/experiments", lambda s, m, q: s.list()),
    ("POST", r"/api/experiments", None),  # body handled in the handler
    ("GET", r"/api/experiments/(?P<id>[^/]+)", lambda s, m, q: s.get(m["id"])),
    ("POST", r"/api/experiments/(?P<id>[^/]+)/rerun", lambda s, m, q: s.rerun(m["id"])),
    ("GET", r"/api/experiments/(?P<id>[^/]+)/runs/(?P<run>[^/]+)", lambda s, m, q: s.run_detail(m["id"], m["run"])),
]
FILES = [
    (r"/api/experiments/(?P<id>[^/]+)/runs/(?P<run>[^/]+)/records\.csv",
     lambda s, m: s.run_files(m["id"], m["run"])[0], "text/csv"),
    (r"/api/experiments/(?P<id>[^/]+)/runs/(?P<run>[^/]+)/summary\.json",
     lambda s, m: s.run_files(m["id"], m["run"])[1], "application/json"),
    (r"/api/experiments/(?P<id>[^/]+)/compare\.csv", lambda s, m: s.compare_csv(m["id"]), "text/csv"),
    (r"/api/experiments/(?P<id>[^/]+)/plots/(?P<metric>\w+)\.png", lambda s, m: s.plot(m["id"], m["metric"]),
     "image/png"),
]
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8")}


def make_handler(store: Store):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AdaptiveSched"

        def log_message(self, fmt, *args):  # quiet; errors are returned to the client
            pass

        def _send(self, status, body: bytes, ctype: str, download: str = ""):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status, obj):
            self._send(status, json.dumps(obj).encode(), "application/json")

        def _dispatch(self, method):
            url = urlparse(self.path)
            path, query = url.path.rstrip("/") or "/", parse_qs(url.query)
            try:
                if method == "GET" and path in STATIC:
                    name, ctype = STATIC[path]
                    return self._send(200, (WEB / name).read_bytes(), ctype)
                if method == "GET":
                    for pattern, fn, ctype in FILES:
                        if m := re.fullmatch(pattern, path):
                            f = fn(store, m)  # runs/<run_id>.records.csv keeps its name; others get the id
                            name = "" if f.suffix == ".png" else f.name if "run" in m.groupdict() \
                                else f"{m['id']}_{f.name}"
                            return self._send(200, f.read_bytes(), ctype, name)
                for verb, pattern, fn in ROUTES:
                    if verb == method and (m := re.fullmatch(pattern, path)):
                        if fn is None:
                            n = int(self.headers.get("Content-Length") or 0)
                            if n > 1_000_000:
                                raise ApiError(413, "request body larger than 1 MB")
                            try:
                                body = json.loads(self.rfile.read(n) or b"null")
                            except json.JSONDecodeError as e:
                                raise ApiError(400, f"request body is not valid JSON: {e}") from None
                            return self._json(202, store.create(body))
                        status = 202 if method == "POST" else 200
                        return self._json(status, fn(store, m, query))
                known = any(re.fullmatch(p, path) for _, p, _ in ROUTES) or path in STATIC
                raise ApiError(405 if known else 404, f"{method} {path} is not supported" if known
                               else f"no such endpoint {path}")
            except ApiError as e:
                self._json(e.status, {"error": str(e)})
            except Exception as e:  # a bug is reported as a 500 with its message, never a hang
                self._json(500, {"error": f"{type(e).__name__}: {e}"})

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

    return Handler


def make_server(host: str, port: int, results, engine: str = "team", csv_dirs=None) -> ThreadingHTTPServer:
    store = Store(results, engine, csv_dirs)
    server = ThreadingHTTPServer((host, port), make_handler(store))
    server.store = store
    return server


def serve(host: str, port: int, results, engine: str = "team") -> None:
    server = make_server(host, port, results, engine)
    print(f"AdaptiveSched dashboard: http://{host}:{server.server_address[1]}/  (experiments in {results}; "
          "Ctrl+C stops)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.store.pool.shutdown(wait=False, cancel_futures=True)
