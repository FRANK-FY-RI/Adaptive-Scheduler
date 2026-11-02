# Findings skeleton (generated - numbers only; write the interpretation by hand)

Ranked within each seed, counted across seeds. Format: docs/STUDY.md §3.

## Trade-off table

| strategy | light:n=300 (16 CPU cores) | heavy:n=300 (16 CPU cores) | short_heavy:n=300 (16 CPU cores) | mixed:n=300 (16 CPU cores) | wide_jobs:n=300 (16 CPU cores) |
|---|---|---|---|---|---|
| fifo | led: max wait 2/3<br>trailed: avg wait 3/3, max wait 1/3, slowdown 3/3 | led: -<br>trailed: avg wait 3/3, slowdown 3/3 | led: makespan 1/3<br>trailed: avg wait 3/3, max wait 1/3, makespan 2/3, slowdown 3/3 | led: -<br>trailed: avg wait 3/3, slowdown 3/3 | led: -<br>trailed: avg wait 3/3, makespan 3/3, slowdown 3/3 |
| sjf | led: avg wait 1/3, max wait 1/3, slowdown 2/3<br>trailed: max wait 2/3, makespan 1/3 | led: avg wait 3/3, slowdown 3/3<br>trailed: max wait 3/3, makespan 3/3 | led: avg wait 1/3, makespan 1/3, slowdown 1/3<br>trailed: max wait 2/3, makespan 1/3 | led: avg wait 3/3, slowdown 3/3<br>trailed: max wait 3/3, makespan 3/3 | led: avg wait 3/3, slowdown 3/3<br>trailed: max wait 3/3 |
| adaptive | led: avg wait 1/3, max wait 1/3, slowdown 1/3<br>trailed: - | led: max wait 1/3, makespan 1/3<br>trailed: - | led: avg wait 2/3, max wait 2/3, slowdown 2/3<br>trailed: - | led: max wait 1/3<br>trailed: - | led: makespan 2/3<br>trailed: - |
| easy_backfill | led: avg wait 1/3, max wait 2/3, makespan 1/3<br>trailed: - | led: max wait 2/3, makespan 2/3<br>trailed: - | led: max wait 1/3, makespan 2/3<br>trailed: - | led: max wait 2/3, makespan 3/3<br>trailed: - | led: max wait 3/3, makespan 1/3<br>trailed: - |

## F1 - synth:light:n=300 - 16 CPU cores

- avg wait: seed 7: lowest sjf (3.43333), highest fifo (4.78333); seed 11: lowest easy_backfill (3.40667), highest fifo (4.98333); seed 13: lowest adaptive (2.90333), highest fifo (3.91)
- max wait: seed 7: lowest easy_backfill/fifo (81), highest sjf (113); seed 11: lowest adaptive/sjf (62), highest fifo (67); seed 13: lowest easy_backfill/fifo (79), highest sjf (113)
- makespan: seed 7: lowest easy_backfill (5708), highest sjf (5733); seed 11: lowest all tied (5907), highest all tied (5907); seed 13: lowest all tied (6213), highest all tied (6213)
- slowdown: seed 7: lowest sjf (1.05146), highest fifo (1.09188); seed 11: lowest adaptive (1.06507), highest fifo (1.09233); seed 13: lowest sjf (1.04543), highest fifo (1.08573)
- failed runs: none
- evidence (run ids): fifo=c39087ad7070, sjf=7b361c367d3e, adaptive=502135808095, easy_backfill=728dc71f1d19, fifo=9326f0746c38, sjf=94892a2e0509, adaptive=2f11d419a6b7, easy_backfill=411fe9409a69, fifo=1169d8248d66, sjf=5c0ab8d4ae63, adaptive=0c4b4e72caf5, easy_backfill=51d0d723748c

Observation:
Trade-off:
Interpretation:
Confidence:

## F2 - synth:heavy:n=300 - 16 CPU cores

- avg wait: seed 7: lowest sjf (111.623), highest fifo (203.523); seed 11: lowest sjf (95.58), highest fifo (214.477); seed 13: lowest sjf (60.0167), highest fifo (100.343)
- max wait: seed 7: lowest easy_backfill (461), highest sjf (2224); seed 11: lowest adaptive (451), highest sjf (2105); seed 13: lowest easy_backfill (219), highest sjf (1621)
- makespan: seed 7: lowest easy_backfill (3320), highest sjf (3476); seed 11: lowest easy_backfill (3416), highest sjf (3540); seed 13: lowest adaptive (3277), highest sjf (3458)
- slowdown: seed 7: lowest sjf (2.10268), highest fifo (5.02823); seed 11: lowest sjf (1.91315), highest fifo (4.95365); seed 13: lowest sjf (1.63304), highest fifo (2.98154)
- failed runs: none
- evidence (run ids): fifo=b7db1b17e66c, sjf=97a9169b91ba, adaptive=7524110804f2, easy_backfill=97f0b4f16c27, fifo=43f5c5804c40, sjf=19628a07f24b, adaptive=c5d6fbbf7334, easy_backfill=a086914157a1, fifo=6ec1a1527b43, sjf=16c0da21f94c, adaptive=e2d28d1c0fda, easy_backfill=e6f0f0bdbed9

Observation:
Trade-off:
Interpretation:
Confidence:

## F3 - synth:short_heavy:n=300 - 16 CPU cores

- avg wait: seed 7: lowest sjf (64.5833), highest fifo (221.827); seed 11: lowest adaptive (79.4233), highest fifo (374.02); seed 13: lowest adaptive (47.5967), highest fifo (148.18)
- max wait: seed 7: lowest adaptive (805), highest sjf (986); seed 11: lowest easy_backfill (1277), highest sjf (1834); seed 13: lowest adaptive (1516), highest fifo (1804)
- makespan: seed 7: lowest sjf (7740), highest fifo (7910); seed 11: lowest easy_backfill (7708), highest fifo (7857); seed 13: lowest easy_backfill/fifo (7514), highest sjf (8216)
- slowdown: seed 7: lowest sjf (3.41689), highest fifo (14.0887); seed 11: lowest adaptive (4.60539), highest fifo (23.5284); seed 13: lowest adaptive (2.98872), highest fifo (9.77009)
- failed runs: none
- evidence (run ids): fifo=946ce0b37a5c, sjf=dbc628c80835, adaptive=cea8c6a25c24, easy_backfill=d588542f5dc6, fifo=04ff993408e7, sjf=e1dea312bd79, adaptive=be2c6ba45182, easy_backfill=3b51b469f306, fifo=e9aa685be83c, sjf=590d8bcf1b25, adaptive=70abc4f61be9, easy_backfill=81d74edc77b2

Observation:
Trade-off:
Interpretation:
Confidence:

## F4 - synth:mixed:n=300 - 16 CPU cores

- avg wait: seed 7: lowest sjf (349.22), highest fifo (1573.27); seed 11: lowest sjf (350.57), highest fifo (3422.02); seed 13: lowest sjf (530.57), highest fifo (2337.36)
- max wait: seed 7: lowest adaptive (2672), highest sjf (11031); seed 11: lowest easy_backfill (4541), highest sjf (12296); seed 13: lowest easy_backfill (3285), highest sjf (9635)
- makespan: seed 7: lowest easy_backfill (13573), highest sjf (16828); seed 11: lowest easy_backfill (18199), highest sjf (21023); seed 13: lowest easy_backfill (18265), highest sjf (22681)
- slowdown: seed 7: lowest sjf (3.25724), highest fifo (52.1036); seed 11: lowest sjf (3.34035), highest fifo (101.374); seed 13: lowest sjf (7.19865), highest fifo (75.9349)
- failed runs: none
- evidence (run ids): fifo=f05e63cbc62f, sjf=2e65fbf42aa9, adaptive=7ca6487a007b, easy_backfill=9980a346beec, fifo=e62518ac0df6, sjf=dcbdb9723127, adaptive=f3dcbd26bd91, easy_backfill=977f0feb53a4, fifo=25fdf66e64f7, sjf=ba0d95ddd51b, adaptive=70df308479aa, easy_backfill=77a1071c0531

Observation:
Trade-off:
Interpretation:
Confidence:

## F5 - synth:wide_jobs:n=300 - 16 CPU cores

- avg wait: seed 7: lowest sjf (1275.63), highest fifo (2269.81); seed 11: lowest sjf (1627.95), highest fifo (3061.19); seed 13: lowest sjf (1393.87), highest fifo (3078.62)
- max wait: seed 7: lowest easy_backfill (4916), highest sjf (15539); seed 11: lowest easy_backfill (5595), highest sjf (17559); seed 13: lowest easy_backfill (4386), highest sjf (18230)
- makespan: seed 7: lowest adaptive (18255), highest fifo (18724); seed 11: lowest adaptive (19468), highest fifo (20141); seed 13: lowest easy_backfill (19687), highest fifo (20795)
- slowdown: seed 7: lowest sjf (13.3911), highest fifo (45.9592); seed 11: lowest sjf (15.4492), highest fifo (57.2303); seed 13: lowest sjf (11.8392), highest fifo (61.6077)
- failed runs: none
- evidence (run ids): fifo=b0fa56365be7, sjf=901593a1f2bf, adaptive=219f90464a32, easy_backfill=0e7331771b35, fifo=adafd7e78462, sjf=1bd43ff20e81, adaptive=5dad12dd4136, easy_backfill=0b6366df607d, fifo=d76db63f0679, sjf=d647729e95b2, adaptive=b31160d39acc, easy_backfill=3d54cbdc40bd

Observation:
Trade-off:
Interpretation:
Confidence:
