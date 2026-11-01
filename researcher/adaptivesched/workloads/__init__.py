"""Workload generators, CSV loader and validation."""
from adaptivesched.workloads.loader import Workload, load_csv


def resolve(spec: str, cluster_cores: int) -> Workload:
    """A workload from a synthetic id (synth:<name>:n=<n>:seed=<seed>) or a CSV path, validated."""
    from adaptivesched.workloads.generators import from_id

    return from_id(spec, cluster_cores) if spec.startswith("synth:") else load_csv(spec, cluster_cores)
