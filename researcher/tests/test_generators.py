import math

import pytest

from adaptivesched.workloads import resolve
from adaptivesched.workloads.generators import GENERATORS, from_id, generate
from adaptivesched.workloads.loader import content_hash, load_csv, to_csv_text
from adaptivesched.workloads.validate import ValidationError

C = 16


@pytest.mark.parametrize("name", GENERATORS)
def test_id_count_validity(name):
    w = generate(name, seed=7, n_jobs=300, cluster_cores=C)
    assert w.workload_id == f"synth:{name}:n=300:seed=7"
    assert len(w.jobs) == 300 and [j.job_id for j in w.jobs] == list(range(1, 301))
    assert w.jobs[0].arrival_time == 0
    assert all(a.arrival_time <= b.arrival_time for a, b in zip(w.jobs, w.jobs[1:]))
    assert all(j.runtime > 0 and 0 < j.required_cores <= C for j in w.jobs)
    assert w.params["runtime_estimate_error"] == 0.0


@pytest.mark.parametrize("name", GENERATORS)
def test_deterministic_and_reproducible_from_id(name):
    a = generate(name, 7, 100, C)
    assert a == generate(name, 7, 100, C) == from_id(a.workload_id, C) == resolve(a.workload_id, C)
    assert a.jobs != generate(name, 11, 100, C).jobs


def test_cross_platform_golden_hash():
    """Pins numpy's default_rng stream: if this fails, the same id now yields different jobs
    (numpy changed, or a generator changed), and old results are no longer comparable."""
    assert {n: content_hash(generate(n, 7, 50, C).jobs) for n in GENERATORS} == GOLDEN


GOLDEN = {  # synth:<name>:n=50:seed=7 at 16 CPU cores; recorded 2026-10-31, numpy 2.x
    "light": "adbe779d697f", "heavy": "ea5e4c25bf2a", "short_heavy": "fa6b2ee7cfaa",
    "mixed": "9d14e29534fa", "wide_jobs": "0cea7fafa008",
}


def test_condition_shapes():
    light, heavy = generate("light", 7, 300, C), generate("heavy", 7, 300, C)
    assert [(j.runtime, j.required_cores) for j in light.jobs] == \
           [(j.runtime, j.required_cores) for j in heavy.jobs]
    assert heavy.params["mean_interarrival"] == pytest.approx(light.params["mean_interarrival"] / 2)
    assert heavy.jobs[-1].arrival_time < light.jobs[-1].arrival_time

    sh = generate("short_heavy", 7, 300, C).jobs
    assert sum(j.runtime >= 600 for j in sh) == 30
    assert all(5 <= j.runtime <= 30 or 600 <= j.runtime <= 3000 for j in sh)
    assert max(j.required_cores for j in sh) <= C // 8

    assert min(j.required_cores for j in generate("wide_jobs", 7, 300, C).jobs) >= math.ceil(C / 2)
    assert max(j.required_cores for j in generate("mixed", 7, 300, C).jobs) <= math.floor(0.6 * C)


def test_tiny_cluster_still_valid():
    for name in GENERATORS:
        assert all(j.required_cores == 1 for j in generate(name, 1, 20, 1).jobs)


@pytest.mark.parametrize("kwargs, message", [
    (dict(name="nope"), "unknown generator 'nope'"),
    (dict(runtime_estimate_error=0.1), "runtime_estimate_error must be 0.0"),
    (dict(seed=-1), "seed must be an integer >= 0"),
    (dict(n_jobs=0), "n_jobs must be an integer > 0"),
    (dict(cluster_cores=0), "cluster_cores must be an integer > 0"),
])
def test_generator_errors(kwargs, message):
    args = dict(name="light", seed=7, n_jobs=10, cluster_cores=C) | kwargs
    with pytest.raises(ValidationError, match=message):
        generate(**args)


def test_bad_id():
    with pytest.raises(ValidationError, match="expected synth:<name>:n=<n_jobs>:seed=<seed>"):
        from_id("synth:heavy:n=ten:seed=7", C)


def test_csv_round_trip(tmp_path):
    w = generate("mixed", 7, 50, C)
    p = tmp_path / "mixed.csv"
    p.write_text(to_csv_text(w.jobs, [w.workload_id]))
    assert load_csv(p, C).jobs == w.jobs
