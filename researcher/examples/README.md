# Reproducing the study from a clean checkout

Run every command from the repository root.

```sh
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[test]"
pytest                                               # all tests must pass first

adaptivesched strategies                             # registered strategy identifiers
adaptivesched workloads                              # the five named workload conditions
adaptivesched workloads --show synth:heavy:n=300:seed=7 --cluster-cores 16 --head 10

adaptivesched run     --config examples/run_heavy_sjf.yaml
adaptivesched batch   --config examples/batch_study.yaml
adaptivesched compare --batch results/batch_<id>     # id printed by `batch`
adaptivesched plot    --batch results/batch_<id>
adaptivesched plot    --batch results/batch_<id> --gantt synth:heavy:n=300:seed=7 fifo sjf
adaptivesched inspect --run results/batch_<id>/runs/<run_id> --job 17
adaptivesched findings --batch results/batch_<id>     # trade-off table + findings skeleton

# RQ3 control: adaptive with fixed weights (adaptation_gain 0), compared in docs/FINDINGS.md F6
adaptivesched batch   --config examples/batch_adaptive_fixed.yaml
adaptivesched compare --batch results/batch_<id2>
```

The default engine is the team engine (`adaptive_scheduler`, installed by `pip install -e .`
from the pinned commit in `pyproject.toml`; needs network once). After the pin changes, run
`pip install --force-reinstall --no-deps "adaptive-scheduler @ git+...@<commit>"`: their
version stays 0.1.0, so a plain install keeps the old code. `--engine fake` selects the
in-repo test engine; its output is test infrastructure, not study results, and every
summary and table it produces says so.

The batch id is a hash of the config and engine, so the same config always writes to the
same directory, and every file except `timestamp` fields is byte-identical on rerun.
