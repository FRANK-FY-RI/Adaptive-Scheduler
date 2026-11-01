"""YAML experiment configs (SPEC §3.1), validated into dataclasses. Errors name the file and key."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from adaptivesched.metrics.summary import sha12
from adaptivesched.workloads.validate import ValidationError


@dataclass(frozen=True)
class RunConfig:
    workload: str
    strategy: str
    cluster_cores: int
    strategy_params: dict = field(default_factory=dict)
    output_dir: str = "results"

    def config_hash(self) -> str:
        """Hash of everything that determines the outputs (output_dir excluded)."""
        d = asdict(self)
        d.pop("output_dir")
        return sha12(d)


@dataclass(frozen=True)
class BatchConfig:
    cluster_cores: int
    workloads: list
    strategies: list
    strategy_params: dict = field(default_factory=dict)  # {strategy: {param: value}}
    seeds: list = field(default_factory=list)            # from `repeats: {seeds: [...]}`
    output_dir: str = "results"

    def workload_ids(self) -> list[str]:
        """Each synthetic workload once per seed (each seed is its own workload id); CSVs once."""
        out = []
        for w in self.workloads:
            variants = [re.sub(r":seed=\d+$", f":seed={s}", w) for s in self.seeds] \
                if self.seeds and w.startswith("synth:") else [w]
            out += [v for v in variants if v not in out]
        return out

    def runs(self) -> list[RunConfig]:
        return [RunConfig(w, s, self.cluster_cores, dict(self.strategy_params.get(s, {})), self.output_dir)
                for w in self.workload_ids() for s in self.strategies]


def _read(path) -> dict:
    path = Path(path)
    try:
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValidationError(f"config file not found: {path}") from None
    except yaml.YAMLError as e:
        raise ValidationError(f"{path}: not valid YAML: {e}") from None
    if not isinstance(d, dict):
        raise ValidationError(f"{path}: expected a mapping of keys, got {type(d).__name__}")
    return d


def _check(path, d: dict, types: dict, required: set) -> None:
    for k in d:
        if k not in types:
            raise ValidationError(f"{path}: unknown key {k!r}; allowed: {', '.join(types)}")
    for k in required - d.keys():
        raise ValidationError(f"{path}: missing required key {k!r}")
    for k, v in d.items():
        t = types[k]
        if isinstance(v, bool) or not isinstance(v, t):
            raise ValidationError(f"{path}, key {k}: expected {t.__name__}, got {v!r}")
        if t is list and not all(isinstance(x, (str, int)) and not isinstance(x, bool) for x in v):
            raise ValidationError(f"{path}, key {k}: list items must be strings or integers, got {v!r}")
    if "cluster_cores" in d and d["cluster_cores"] <= 0:
        raise ValidationError(f"{path}, key cluster_cores: must be > 0, got {d['cluster_cores']}")


def load_run_config(path) -> RunConfig:
    d = _read(path)
    _check(path, d, {"workload": str, "strategy": str, "cluster_cores": int,
                     "strategy_params": dict, "output_dir": str},
           {"workload", "strategy", "cluster_cores"})
    return RunConfig(**d)


def load_batch_config(path) -> BatchConfig:
    d = _read(path)
    repeats = d.pop("repeats", None)
    _check(path, d, {"cluster_cores": int, "workloads": list, "strategies": list,
                     "strategy_params": dict, "output_dir": str},
           {"cluster_cores", "workloads", "strategies"})
    seeds = []
    if repeats is not None:
        seeds = repeats.get("seeds") if isinstance(repeats, dict) and set(repeats) == {"seeds"} else None
        is_seed = lambda s: isinstance(s, int) and not isinstance(s, bool) and s >= 0
        if not isinstance(seeds, list) or not all(map(is_seed, seeds)):
            raise ValidationError(f"{path}, key repeats: expected {{seeds: [non-negative integers]}}, got {repeats!r}")
    for k in ("workloads", "strategies"):
        if not d[k]:
            raise ValidationError(f"{path}, key {k}: must not be empty")
    return BatchConfig(**d, seeds=seeds)
