### synth:light:n=300:seed=7 - 16 CPU cores

| strategy | status | average_waiting_time | max_waiting_time | cpu_utilization | makespan | bounded_slowdown | average_turnaround_time |
|---|---|---:|---:|---:|---:|---:|---:|
| fifo | ok | 4.783 | 81 | 52.352 | 5711 | 1.092 | 67.070 |
| sjf | ok | 3.433 | 113 | 52.151 | 5733 | 1.051 | 65.720 |
| adaptive | ok | 3.593 | 89 | 52.352 | 5711 | 1.062 | 65.880 |
| easy_backfill | ok | 4.360 | 81 | 52.379 | 5708 | 1.084 | 66.647 |

### synth:light:n=300:seed=11 - 16 CPU cores

| strategy | status | average_waiting_time | max_waiting_time | cpu_utilization | makespan | bounded_slowdown | average_turnaround_time |
|---|---|---:|---:|---:|---:|---:|---:|
| fifo | ok | 4.983 | 67 | 54.278 | 5907 | 1.092 | 72.210 |
| sjf | ok | 3.677 | 62 | 54.278 | 5907 | 1.067 | 70.903 |
| adaptive | ok | 3.573 | 62 | 54.278 | 5907 | 1.065 | 70.800 |
| easy_backfill | ok | 3.407 | 66 | 54.278 | 5907 | 1.068 | 70.633 |

### synth:light:n=300:seed=13 - 16 CPU cores

| strategy | status | average_waiting_time | max_waiting_time | cpu_utilization | makespan | bounded_slowdown | average_turnaround_time |
|---|---|---:|---:|---:|---:|---:|---:|
| fifo | ok | 3.910 | 79 | 49.203 | 6213 | 1.086 | 73.617 |
| sjf | ok | 3.017 | 113 | 49.203 | 6213 | 1.045 | 72.723 |
| adaptive | ok | 2.903 | 92 | 49.203 | 6213 | 1.050 | 72.610 |
| easy_backfill | ok | 3.497 | 79 | 49.203 | 6213 | 1.072 | 73.203 |

### synth:heavy:n=300:seed=7 - 16 CPU cores

| strategy | status | average_waiting_time | max_waiting_time | cpu_utilization | makespan | bounded_slowdown | average_turnaround_time |
|---|---|---:|---:|---:|---:|---:|---:|
| fifo | ok | 203.523 | 581 | 86.913 | 3440 | 5.028 | 265.810 |
| sjf | ok | 111.623 | 2224 | 86.013 | 3476 | 2.103 | 173.910 |
| adaptive | ok | 136.617 | 462 | 89.569 | 3338 | 3.501 | 198.903 |
| easy_backfill | ok | 139.743 | 461 | 90.055 | 3320 | 3.713 | 202.030 |

### synth:heavy:n=300:seed=11 - 16 CPU cores

| strategy | status | average_waiting_time | max_waiting_time | cpu_utilization | makespan | bounded_slowdown | average_turnaround_time |
|---|---|---:|---:|---:|---:|---:|---:|
| fifo | ok | 214.477 | 524 | 91.292 | 3512 | 4.954 | 281.703 |
| sjf | ok | 95.580 | 2105 | 90.570 | 3540 | 1.913 | 162.807 |
| adaptive | ok | 153.370 | 451 | 92.879 | 3452 | 3.692 | 220.597 |
| easy_backfill | ok | 156.403 | 479 | 93.858 | 3416 | 3.916 | 223.630 |

### synth:heavy:n=300:seed=13 - 16 CPU cores

| strategy | status | average_waiting_time | max_waiting_time | cpu_utilization | makespan | bounded_slowdown | average_turnaround_time |
|---|---|---:|---:|---:|---:|---:|---:|
| fifo | ok | 100.343 | 234 | 92.162 | 3317 | 2.982 | 170.050 |
| sjf | ok | 60.017 | 1621 | 88.404 | 3458 | 1.633 | 129.723 |
| adaptive | ok | 64.483 | 224 | 93.287 | 3277 | 2.083 | 134.190 |
| easy_backfill | ok | 69.697 | 219 | 93.173 | 3281 | 2.353 | 139.403 |

### synth:short_heavy:n=300:seed=7 - 16 CPU cores

| strategy | status | average_waiting_time | max_waiting_time | cpu_utilization | makespan | bounded_slowdown | average_turnaround_time |
|---|---|---:|---:|---:|---:|---:|---:|
| fifo | ok | 221.827 | 944 | 66.880 | 7910 | 14.089 | 417.970 |
| sjf | ok | 64.583 | 986 | 68.349 | 7740 | 3.417 | 260.727 |
| adaptive | ok | 106.733 | 805 | 67.849 | 7797 | 6.162 | 302.877 |
| easy_backfill | ok | 172.870 | 828 | 67.832 | 7799 | 11.156 | 369.013 |

### synth:short_heavy:n=300:seed=11 - 16 CPU cores

| strategy | status | average_waiting_time | max_waiting_time | cpu_utilization | makespan | bounded_slowdown | average_turnaround_time |
|---|---|---:|---:|---:|---:|---:|---:|
| fifo | ok | 374.020 | 1356 | 72.302 | 7857 | 23.528 | 564.603 |
| sjf | ok | 104.303 | 1834 | 72.961 | 7786 | 5.864 | 294.887 |
| adaptive | ok | 79.423 | 1604 | 73.093 | 7772 | 4.605 | 270.007 |
| easy_backfill | ok | 262.500 | 1277 | 73.699 | 7708 | 16.479 | 453.083 |

### synth:short_heavy:n=300:seed=13 - 16 CPU cores

| strategy | status | average_waiting_time | max_waiting_time | cpu_utilization | makespan | bounded_slowdown | average_turnaround_time |
|---|---|---:|---:|---:|---:|---:|---:|
| fifo | ok | 148.180 | 1804 | 64.340 | 7514 | 9.770 | 336.273 |
| sjf | ok | 51.460 | 1517 | 58.843 | 8216 | 3.135 | 239.553 |
| adaptive | ok | 47.597 | 1516 | 58.850 | 8215 | 2.989 | 235.690 |
| easy_backfill | ok | 76.873 | 1736 | 64.340 | 7514 | 5.117 | 264.967 |

### synth:mixed:n=300:seed=7 - 16 CPU cores

| strategy | status | average_waiting_time | max_waiting_time | cpu_utilization | makespan | bounded_slowdown | average_turnaround_time |
|---|---|---:|---:|---:|---:|---:|---:|
| fifo | ok | 1573.267 | 4820 | 73.217 | 15509 | 52.104 | 1691.020 |
| sjf | ok | 349.220 | 11031 | 67.478 | 16828 | 3.257 | 466.973 |
| adaptive | ok | 524.377 | 2672 | 82.464 | 13770 | 13.729 | 642.130 |
| easy_backfill | ok | 535.827 | 2904 | 83.661 | 13573 | 15.884 | 653.580 |

### synth:mixed:n=300:seed=11 - 16 CPU cores

| strategy | status | average_waiting_time | max_waiting_time | cpu_utilization | makespan | bounded_slowdown | average_turnaround_time |
|---|---|---:|---:|---:|---:|---:|---:|
| fifo | ok | 3422.020 | 6887 | 73.963 | 20976 | 101.374 | 3572.617 |
| sjf | ok | 350.570 | 12296 | 73.798 | 21023 | 3.340 | 501.167 |
| adaptive | ok | 1499.847 | 4628 | 84.802 | 18295 | 37.862 | 1650.443 |
| easy_backfill | ok | 1552.817 | 4541 | 85.250 | 18199 | 42.692 | 1703.413 |

### synth:mixed:n=300:seed=13 - 16 CPU cores

| strategy | status | average_waiting_time | max_waiting_time | cpu_utilization | makespan | bounded_slowdown | average_turnaround_time |
|---|---|---:|---:|---:|---:|---:|---:|
| fifo | ok | 2337.357 | 4815 | 77.158 | 20703 | 75.935 | 2539.857 |
| sjf | ok | 530.570 | 9635 | 70.429 | 22681 | 7.199 | 733.070 |
| adaptive | ok | 900.920 | 3477 | 86.346 | 18500 | 24.801 | 1103.420 |
| easy_backfill | ok | 878.033 | 3285 | 87.457 | 18265 | 24.009 | 1080.533 |

### synth:wide_jobs:n=300:seed=7 - 16 CPU cores

| strategy | status | average_waiting_time | max_waiting_time | cpu_utilization | makespan | bounded_slowdown | average_turnaround_time |
|---|---|---:|---:|---:|---:|---:|---:|
| fifo | ok | 2269.810 | 5367 | 75.889 | 18724 | 45.959 | 2332.097 |
| sjf | ok | 1275.627 | 15539 | 76.334 | 18615 | 13.391 | 1337.913 |
| adaptive | ok | 2075.163 | 5100 | 77.839 | 18255 | 40.507 | 2137.450 |
| easy_backfill | ok | 2122.803 | 4916 | 77.762 | 18273 | 42.823 | 2185.090 |

### synth:wide_jobs:n=300:seed=11 - 16 CPU cores

| strategy | status | average_waiting_time | max_waiting_time | cpu_utilization | makespan | bounded_slowdown | average_turnaround_time |
|---|---|---:|---:|---:|---:|---:|---:|
| fifo | ok | 3061.187 | 6165 | 76.114 | 20141 | 57.230 | 3128.413 |
| sjf | ok | 1627.953 | 17559 | 76.765 | 19970 | 15.449 | 1695.180 |
| adaptive | ok | 2555.680 | 6094 | 78.745 | 19468 | 46.256 | 2622.907 |
| easy_backfill | ok | 2709.200 | 5595 | 78.331 | 19571 | 50.710 | 2776.427 |

### synth:wide_jobs:n=300:seed=13 - 16 CPU cores

| strategy | status | average_waiting_time | max_waiting_time | cpu_utilization | makespan | bounded_slowdown | average_turnaround_time |
|---|---|---:|---:|---:|---:|---:|---:|
| fifo | ok | 3078.617 | 5494 | 73.147 | 20795 | 61.608 | 3148.323 |
| sjf | ok | 1393.873 | 18230 | 73.747 | 20626 | 11.839 | 1463.580 |
| adaptive | ok | 2362.160 | 4655 | 77.252 | 19690 | 45.392 | 2431.867 |
| easy_backfill | ok | 2410.193 | 4386 | 77.264 | 19687 | 48.246 | 2479.900 |
