# Workloads

| file | what |
|---|---|
| `synthetic_workload.csv` | 5 hand-made jobs for smoke tests |
| `pwa/*.csv` | windows of **real job logs** from production machines (Parallel Workloads Archive) |
| `pwa/*.swf.gz` | the downloaded logs themselves (not in git; download again with the links below) |

Synthetic workloads with any number of jobs come from the generators:
`synth:<light|heavy|short_heavy|mixed|wide_jobs>:n=<jobs>:seed=<seed>` (`researcher/README.md`).

## Real logs: Parallel Workloads Archive

The [Parallel Workloads Archive](https://www.cs.huji.ac.il/labs/parallel/workload/logs.html)
publishes the accounting logs of production parallel machines in the
[Standard Workload Format](https://www.cs.huji.ac.il/labs/parallel/workload/swf.html) (SWF). It
recommends the **cleaned** versions (`-cln`), which remove administrative bursts and other
unrepresentative activity. When using these logs, cite: D. G. Feitelson, D. Tsafrir, D. Krakov,
"Experience with using the Parallel Workloads Archive", *JPDC* 74(10), 2014.

The five logs used here cover machines from 100 to 1,152 CPUs and three decades of HPC practice:

| log | machine | CPUs | jobs (cleaned) | period | download (save into `workloads/pwa/`) |
|---|---|---|---|---|---|
| KTH SP2 | IBM SP2, KTH Stockholm | 100 | 28,476 | 1996–97 | [KTH-SP2-1996-2.1-cln.swf.gz](https://www.cs.huji.ac.il/labs/parallel/workload/l_kth_sp2/KTH-SP2-1996-2.1-cln.swf.gz) |
| SDSC SP2 | IBM SP2, San Diego | 128 | 59,715 | 1998–2000 | [SDSC-SP2-1998-4.2-cln.swf.gz](https://www.cs.huji.ac.il/labs/parallel/workload/l_sdsc_sp2/SDSC-SP2-1998-4.2-cln.swf.gz) |
| HPC2N | Linux cluster, Umeå | 240 | 202,871 | 2002–06 | [HPC2N-2002-2.2-cln.swf.gz](https://www.cs.huji.ac.il/labs/parallel/workload/l_hpc2n/HPC2N-2002-2.2-cln.swf.gz) |
| CTC SP2 | IBM SP2, Cornell | 338 | 77,222 | 1996–97 | [CTC-SP2-1996-3.1-cln.swf.gz](https://www.cs.huji.ac.il/labs/parallel/workload/l_ctc_sp2/CTC-SP2-1996-3.1-cln.swf.gz) |
| SDSC Blue | IBM SP Blue Horizon, San Diego | 1,152 | 243,306 | 2000–03 | [SDSC-BLUE-2000-4.2-cln.swf.gz](https://www.cs.huji.ac.il/labs/parallel/workload/l_sdsc_blue/SDSC-BLUE-2000-4.2-cln.swf.gz) |

The archive's server refuses scripted downloads, so download the files in a browser (click, or
right-click → Save link as) into `workloads/pwa/`. A file of about 600 bytes is the server's error
page, not a log; the converter says so.

### Which SWF attributes are used

| SWF field | used as |
|---|---|
| 1 Job Number | `job_id` (kept, so every job can be traced back to the log) |
| 2 Submit Time | `arrival_time`, shifted so the window's first job arrives at 0 |
| 4 Run Time | `runtime`, rounded to whole seconds |
| 5 Allocated Processors (8 Requested Processors if 5 is missing) | `required_cores` |
| header `MaxProcs` | the cluster's CPU cores |

Dropped: jobs whose run time rounds to 0 (cancelled before starting), jobs with no processor count,
and jobs wider than the machine. Jobs that were cancelled or failed after starting are kept, because
they occupied CPU cores. The other SWF fields (requested time, memory, user, queue, …) are not used:
the simulator has exact runtimes and one resource type.

### Convert

A whole log is months of activity (up to 243,000 jobs). Each converted CSV is a window of
**consecutive** jobs, centred in the log unless `--start` is given:

```sh
cd researcher
adaptivesched workloads --from-swf ../workloads/pwa/KTH-SP2-1996-2.1-cln.swf.gz --jobs 5000 --out ../workloads/pwa/kth_sp2_5000.csv
```

The CSV header records the source file, the machine, `cluster_cores`, the window (SWF job numbers
and time span) and what was dropped. Run a converted log at its own machine size
(`cluster_cores` in its header). The dashboard fills this in when you tick the log.
