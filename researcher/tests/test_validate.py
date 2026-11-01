"""Every validation error in INTERFACES.md §4, each naming the row (file line) or field."""
import pytest

from adaptivesched.workloads.loader import load_csv
from adaptivesched.workloads.validate import ValidationError, check_strategy

H = "job_id,arrival_time,runtime,required_cores\n"


def write(tmp_path, text, name="w.csv"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


@pytest.mark.parametrize("text, cores, message", [
    ("", 4, r"w\.csv: no header"),
    ("id,arr,run,cores\n1,0,5,1\n", 4, r"w\.csv line 1: header must be exactly"),
    (H + "1,0,5\n", 4, r"w\.csv line 2: expected 4 columns .* got 3"),
    (H + "1,0,5,1,9\n", 4, r"w\.csv line 2: expected 4 columns .* got 5"),
    (H + "1,0,abc,1\n", 4, r"w\.csv line 2, field runtime: 'abc' is not an integer"),
    (H + "1,0,5.5,1\n", 4, r"w\.csv line 2, field runtime: '5\.5' is not an integer"),
    (H + "1,0,5,1\n# note\n1,3,5,1\n", 4,
     r"w\.csv line 4, field job_id: duplicate job_id 1 \(first at w\.csv line 2\)"),
    (H + "1,-1,5,1\n", 4, r"w\.csv line 2, field arrival_time: must be >= 0, got -1"),
    (H + "1,0,0,1\n", 4, r"w\.csv line 2, field runtime: must be > 0, got 0"),
    (H + "1,0,5,0\n", 4, r"w\.csv line 2, field required_cores: must be > 0, got 0"),
    (H + "1,0,5,1\n2,0,5,9\n", 4,
     r"w\.csv line 3, field required_cores: job 2 needs 9 CPU cores but the cluster has 4"),
    (H, 4, r"workload has no jobs"),
    (H + "1,0,5,1\n", 0, r"cluster_cores must be an integer > 0, got 0"),
])
def test_csv_errors_name_row_or_field(tmp_path, text, cores, message):
    with pytest.raises(ValidationError, match=message):
        load_csv(write(tmp_path, text), cores)


def test_missing_file(tmp_path):
    with pytest.raises(ValidationError, match="workload file not found"):
        load_csv(tmp_path / "nope.csv", 4)


def test_unknown_strategy():
    with pytest.raises(ValidationError, match=r"strategy: unknown identifier 'edf'; available: fifo, sjf"):
        check_strategy("edf", ["fifo", "sjf"])


def test_comments_blank_lines_whitespace_and_deferred_capacity(tmp_path):
    w = load_csv(write(tmp_path, "# c\n\n" + H + " 2 , 0 , 5 , 8 \n1,0,5,1\n"))  # no capacity yet
    assert [j.job_id for j in w.jobs] == [2, 1]
    with pytest.raises(ValidationError, match="line 4, field required_cores"):
        load_csv(write(tmp_path, "# c\n\n" + H + "2,0,5,8\n"), 4)


def test_workload_id_hash_follows_content_not_name_or_layout(tmp_path):
    a = load_csv(write(tmp_path, H + "1,0,5,1\n2,1,3,2\n", "a.csv"))
    b = load_csv(write(tmp_path, "# renamed, reordered\n" + H + "2,1,3,2\n1,0,5,1\n", "b.csv"))
    c = load_csv(write(tmp_path, H + "1,0,5,1\n2,1,4,2\n", "c.csv"))
    assert a.workload_id.startswith("csv:a.csv:") and b.workload_id.startswith("csv:b.csv:")
    assert a.params["content_sha256_12"] == b.params["content_sha256_12"]
    assert a.params["content_sha256_12"] != c.params["content_sha256_12"]
    assert a.params["runtime_estimate_error"] == 0.0
