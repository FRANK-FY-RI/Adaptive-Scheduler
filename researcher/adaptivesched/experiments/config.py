"""YAML experiment configs (SPEC §3.1), validated into dataclasses. Errors name the file and key."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from adaptivesched.experiments.adapter import split_strategy_file
from adaptivesched.metrics.summary import sha12
from adaptivesched.workloads.validate import ValidationError


@dataclass(frozen=True)
class RunConfig:
    workload: str
    strategy: str
    cluster_cores: int
    strategy_params: dict = field(default_factory=dict)
    output_dir: str = "results"
    strategy_file: str = ""  # researcher strategy: "path.py" or "path.py:ClassName"
    base_strategy: str = ""  # set for a labelled variant: the registered strategy it runs

    def config_hash(self) -> str:
        """Hash of everything that determines the outputs (output_dir excluded). A strategy
        file counts by its content and class, not its path, so moving it keeps the hash."""
        d = asdict(self)
        d.pop("output_dir")
        if not self.base_strategy:
            d.pop("base_strategy")  # keeps hashes of non-variant runs unchanged
        if self.strategy_file:
            path, cls = split_strategy_file(self.strategy_file)
            try:
                d["strategy_file"] = [hashlib.sha256(Path(path).read_bytes()).hexdigest(), cls]
            except OSError:
                pass  # the run fails loudly when the adapter loads it
        else:
            d.pop("strategy_file")  # keeps hashes of built-in runs unchanged
        return sha12(d)


@dataclass(frozen=True)
class BatchConfig:
    cluster_cores: int
    workloads: list
    strategies: list
    strategy_params: dict = field(default_factory=dict)  # {strategy: {param: value}}
    seeds: list = field(default_factory=list)            # from `repeats: {seeds: [...]}`
    output_dir: str = "results"
    strategy_files: dict = field(default_factory=dict)   # {strategy: "path.py[:ClassName]"}
    variants: dict = field(default_factory=dict)          # {label: {strategy: id, params: {...}}}

    def workload_ids(self) -> list[str]:
        """Each synthetic workload once per seed (each seed is its own workload id); CSVs once."""
        out = []
        for w in self.workloads:
            variants = [re.sub(r":seed=\d+$", f":seed={s}", w) for s in self.seeds] \
                if self.seeds and w.startswith("synth:") else [w]
            out += [v for v in variants if v not in out]
        return out

    def runs(self) -> list[RunConfig]:
        out = []
        for w in self.workload_ids():
            for s in self.strategies:
                v = self.variants.get(s)
                params = v.get("params", {}) if v else self.strategy_params.get(s, {})
                out.append(RunConfig(w, s, self.cluster_cores, dict(params), self.output_dir,
                                     self.strategy_files.get(s, ""), v["strategy"] if v else ""))
        return out


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


def _beside(config_path, spec: str) -> str:
    """A relative strategy file path is relative to the config file, like a CSV workload."""
    return str(Path(config_path).parent / spec) if not Path(spec).is_absolute() else spec


def load_run_config(path) -> RunConfig:
    d = _read(path)
    _check(path, d, {"workload": str, "strategy": str, "cluster_cores": int,
                     "strategy_params": dict, "output_dir": str, "strategy_file": str},
           {"workload", "strategy", "cluster_cores"})
    if d.get("strategy_file"):
        d["strategy_file"] = _beside(path, d["strategy_file"])
    return RunConfig(**d)


def load_batch_config(path) -> BatchConfig:
    return batch_config_from_dict(_read(path), path)


def batch_config_from_dict(d: dict, path="config", strategy_files_allowed: bool = True) -> BatchConfig:
    """Validate a batch config mapping (from YAML or the web API); errors name `path` and the key.
    strategy_files_allowed=False refuses `strategy_files` (executable code; the API never loads it)."""
    d = dict(d)
    repeats = d.pop("repeats", None)
    types = {"cluster_cores": int, "workloads": list, "strategies": list, "strategy_params": dict,
             "output_dir": str, "strategy_files": dict, "variants": dict}
    if not strategy_files_allowed:
        types.pop("strategy_files")
    _check(path, d, types, {"cluster_cores", "workloads", "strategies"})
    if len(set(d["strategies"])) != len(d["strategies"]):
        raise ValidationError(f"{path}, key strategies: each label may appear once, got {d['strategies']!r}")
    files = d.get("strategy_files", {})
    for name, spec in files.items():
        if name not in d["strategies"] or not isinstance(spec, str):
            raise ValidationError(f"{path}, key strategy_files: {name!r} must be listed in strategies "
                                  f"and map to a 'file.py[:ClassName]' string, got {spec!r}")
    if files:
        d["strategy_files"] = {k: _beside(path, v) for k, v in files.items()}
    for label, v in d.get("variants", {}).items():
        ok = (isinstance(v, dict) and set(v) <= {"strategy", "params"} and isinstance(v.get("strategy"), str)
              and isinstance(v.get("params", {}), dict))
        if label not in d["strategies"] or label in files or not ok:
            raise ValidationError(f"{path}, key variants: {label!r} must be listed in strategies and map to "
                                  f"{{strategy: <registered id>, params: {{...}}}}, got {v!r}")
    for name, params in d.get("strategy_params", {}).items():
        if not isinstance(params, dict):
            raise ValidationError(f"{path}, key strategy_params: {name!r} must map to a mapping, got {params!r}")
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
