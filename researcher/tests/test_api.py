"""HTTP API and dashboard: endpoints, validation, async execution, CLI parity, reproducibility."""
import json
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from adaptivesched.api.server import WEB, make_server
from adaptivesched.experiments.adapter import TeamEngineAdapter
from adaptivesched.experiments.batch import run_batch
from adaptivesched.experiments.config import batch_config_from_dict
from adaptivesched.experiments.export import read_json

REQUEST = {"name": "api test", "cluster_cores": 8, "workloads": ["synth:heavy:n=25:seed=7"],
           "strategies": ["fifo", "srtf", "adaptive_multifactor", "amf_pre"],
           "strategy_params": {"fifo": {"strict_head_of_line": True}},
           "variants": {"amf_pre": {"strategy": "adaptive_multifactor", "params": {"preemptive": True}}},
           "seeds": [7, 11]}


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    root = tmp_path_factory.mktemp("web")
    srv = make_server("127.0.0.1", 0, root)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def call(base, path, body=None, method=None):
    req = urllib.request.Request(base + path, method=method or ("POST" if body is not None else "GET"),
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if r.headers["Content-Type"] == "application/json" else raw), r.headers
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read()), e.headers


def wait(base, exp_id, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        _, e, _ = call(base, f"/api/experiments/{exp_id}")
        if e["status"] not in ("queued", "running"):
            return e
        time.sleep(0.2)
    raise AssertionError(f"experiment {exp_id} still {e['status']}")


@pytest.fixture(scope="module")
def done(server):
    _, base = server
    status, e, _ = call(base, "/api/experiments", REQUEST)
    assert status == 202 and e["status"] == "queued" and e["progress"] == [0, 8]
    return wait(base, e["id"])


def test_catalog_endpoints(server):
    _, base = server
    assert call(base, "/api/health")[1] == {"ok": True}
    _, pol, _ = call(base, "/api/policies")
    amf = next(p for p in pol if p["id"] == "adaptive_multifactor")
    assert {"name": "preemptive", "default": False, "type": "bool"} in amf["params"] and amf["preemptive_capable"]
    assert [p["id"] for p in pol] == sorted(p["id"] for p in pol) and "srtf" in [p["id"] for p in pol]
    _, wl, _ = call(base, "/api/workloads")
    assert {s["name"] for s in wl["synthetic"]} >= {"light", "heavy", "mixed"}
    assert any(c["name"] == "synthetic_workload.csv" for c in wl["csv"])


def test_experiment_completes_with_metrics_and_records(server, done):
    _, base = server
    assert done["status"] == "completed" and done["progress"] == [8, 8] and done["runs_failed"] == 0
    rows = {(r["strategy"], r["workload_id"]): r for r in done["rows"]}
    assert len(rows) == 8 and all(r["status"] == "ok" for r in rows.values())
    run = rows[("srtf", "synth:heavy:n=25:seed=7")]
    _, detail, _ = call(base, f"/api/experiments/{done['id']}/runs/{run['run_id']}")
    assert detail["summary"]["preemptive"] is True and len(detail["records"]) == 25
    r0 = detail["records"][0]
    assert set(r0) >= {"job_id", "arrival_time", "start_time", "finish_time", "runtime", "waiting_time",
                       "turnaround_time", "required_cores", "preemption_count", "execution_segments"}
    assert sum(len(r["execution_segments"]) for r in detail["records"]) == 25 + detail["summary"]["total_preemptions"]
    assert len(detail["lanes"]) >= 25


def test_exports(server, done):
    _, base = server
    run_id = done["rows"][0]["run_id"]
    status, csv, headers = call(base, f"/api/experiments/{done['id']}/runs/{run_id}/records.csv")
    assert status == 200 and csv.startswith(b"job_id,arrival_time,start_time,finish_time,runtime,waiting_time,"
                                            b"turnaround_time,required_cores,preemption_count,execution_segments")
    assert f'filename="{run_id}.records.csv"' in headers["Content-Disposition"]
    status, summary, _ = call(base, f"/api/experiments/{done['id']}/runs/{run_id}/summary.json")
    assert status == 200 and summary["metadata"]["run_id"] == run_id
    status, comp, _ = call(base, f"/api/experiments/{done['id']}/compare.csv")
    assert status == 200 and comp.count(b"\n") == 9
    status, png, headers = call(base, f"/api/experiments/{done['id']}/plots/average_waiting_time.png")
    assert status == 200 and png[:8] == b"\x89PNG\r\n\x1a\n"


def _no_timestamp(s):
    s = json.loads(json.dumps(s))
    s["metadata"].pop("timestamp")
    s["metadata"].pop("config_hash")  # hashes a config with output_dir removed: identical anyway; checked below
    return s


def test_cli_and_web_give_identical_results(server, done, tmp_path):
    """The same configuration through the CLI's run_batch: every summary equal except the timestamp."""
    d = {k: v for k, v in REQUEST.items() if k not in ("name", "seeds")}
    cfg = batch_config_from_dict({**d, "repeats": {"seeds": REQUEST["seeds"]}, "output_dir": str(tmp_path)})
    out = run_batch(cfg, TeamEngineAdapter(), "team")
    web_runs = Path(done["batch_dir"]) / "runs"
    assert out.name == Path(done["batch_dir"]).name  # same run-set id: same config, same engine
    for p in (out / "runs").glob("*.summary.json"):
        cli, web = read_json(p), read_json(web_runs / p.name)
        assert cli["metadata"]["config_hash"] == web["metadata"]["config_hash"]
        assert _no_timestamp(cli) == _no_timestamp(web)
        assert (out / "runs" / p.name.replace("summary.json", "records.csv")).read_bytes() == \
               (web_runs / p.name.replace("summary.json", "records.csv")).read_bytes()


def test_rerun_reproduces(server, done):
    _, base = server
    status, e, _ = call(base, f"/api/experiments/{done['id']}/rerun", body={}, method="POST")
    assert status == 202 and e["request"] == done["request"]
    again = wait(base, e["id"])
    for a, b in zip(done["rows"], again["rows"]):
        assert {k: v for k, v in a.items() if k != "engine"} == {k: v for k, v in b.items() if k != "engine"}
    _, listed, _ = call(base, "/api/experiments")
    assert [x["id"] for x in listed][:2] == [again["id"], done["id"]]
    _, ov, _ = call(base, "/api/overview")
    assert ov["total_experiments"] >= 2 and ov["runs_ok"] >= 16 and "adaptive_multifactor" in ov["policies"]


@pytest.mark.parametrize("body, message", [
    ([], "must be a JSON object"),
    ({**REQUEST, "colour": 1}, "unknown field(s) ['colour']"),
    ({**REQUEST, "cluster_cores": 0}, "cluster_cores: must be > 0"),
    ({**REQUEST, "strategies": ["edf"], "variants": {}}, "unknown identifier 'edf'"),
    ({**REQUEST, "strategies": ["fifo"]}, "variants: 'amf_pre' must be listed in strategies"),
    ({**REQUEST, "strategy_params": {"fifo": {"alpha": 1}}}, "unexpected keyword argument 'alpha'"),
    ({**REQUEST, "variants": {"amf_pre": {"strategy": "adaptive_multifactor", "params": {"max_age": -1}}}},
     "max_age must be in"),
    ({**REQUEST, "workloads": ["synth:nope:n=5:seed=1"]}, "unknown generator 'nope'"),
    ({**REQUEST, "workloads": ["C:/Windows/win.ini"]}, "not a CSV listed by /api/workloads"),
    ({**REQUEST, "cluster_cores": 2, "workloads": ["synth:wide_jobs:n=5:seed=1"]}, None),  # valid: widths scale
    ({**REQUEST, "seeds": [1] * 0 + list(range(200))}, "at most 500 per experiment"),
])
def test_invalid_requests_are_rejected_with_reasons(server, body, message):
    _, base = server
    status, e, _ = call(base, "/api/experiments", body)
    if message is None:
        assert status == 202
        wait(base, e["id"])
    else:
        assert status == 400 and message in e["error"], e


def test_not_found_and_bad_ids(server, done):
    _, base = server
    assert call(base, "/api/nope")[0] == 404
    assert call(base, "/api/experiments/../../etc")[0] == 404
    assert call(base, f"/api/experiments/{done['id']}/runs/zzz")[0] == 404
    assert call(base, f"/api/experiments/{done['id']}/plots/secret.png")[0] == 404
    status, e, _ = call(base, "/api/experiments", body=None, method="POST")
    assert status == 400


def test_long_run_does_not_block_reads(server):
    """While a 300-job, 8-strategy experiment runs on the worker thread, GETs answer at once."""
    _, base = server
    big = {**REQUEST, "workloads": ["synth:mixed:n=300:seed=3"], "seeds": [3]}
    _, e, _ = call(base, "/api/experiments", big)
    t = time.time()
    for _ in range(5):
        assert call(base, "/api/experiments")[0] == 200
    assert time.time() - t < 5
    assert wait(base, e["id"])["status"] == "completed"


def test_dashboard_is_served_and_only_calls_real_endpoints(server):
    _, base = server
    status, html, headers = call(base, "/")
    assert status == 200 and b"<title>AdaptiveSched Dashboard</title>" in html
    assert call(base, "/app.js")[0] == 200 and call(base, "/style.css")[0] == 200
    js = (WEB / "app.js").read_text(encoding="utf-8")
    from adaptivesched.api.server import FILES, ROUTES

    patterns = [p for _, p, _ in ROUTES] + [p for p, _, _ in FILES]
    used = set(re.findall(r"[`\"](/api/[^`\"?]*)", js))
    assert used, "no API calls found in app.js"
    for path in used:
        concrete = re.sub(r"\$\{[^}]+\}", "x0", path)  # template parts -> a placeholder segment
        assert any(re.fullmatch(p, concrete) for p in patterns), path
    for tab in "ABCDEFGH":
        assert f"<h1>{tab}." in html.decode() or f"{tab}. " in html.decode()


def test_presets_served_and_inf_accepted(server):
    """GET /api/policies carries the tuned presets (infinity as "inf"); a request using the
    preemptive preset, as the dashboard sends it, runs with reservation_xf = inf."""
    _, base = server
    _, pol, _ = call(base, "/api/policies")
    presets = next(p for p in pol if p["id"] == "adaptive_multifactor")["presets"]
    pre = presets["tuned for real HPC logs, preemptive"]
    assert pre["reservation_xf"] == "inf" and presets["tuned for real HPC logs"]["max_age"] == 203692
    body = {"cluster_cores": 8, "workloads": ["synth:heavy:n=20:seed=1"], "strategies": ["adaptive_multifactor"],
            "strategy_params": {"adaptive_multifactor": pre}}
    status, e, _ = call(base, "/api/experiments", body)
    assert status == 202, e
    done = wait(base, e["id"])
    assert done["status"] == "completed" and done["runs_failed"] == 0
    _, detail, _ = call(base, f"/api/experiments/{done['id']}/runs/{done['rows'][0]['run_id']}")
    assert detail["summary"]["metadata"]["strategy_params"]["reservation_xf"] == "inf"
    assert detail["summary"]["preemptive"] is True
    status, err, _ = call(base, "/api/experiments", {**body, "strategy_params": {"adaptive_multifactor": {"max_age": "soon"}}})
    assert status == 400 and "max_age" in err["error"]
