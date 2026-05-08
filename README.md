# quorin-benchmarks

[![Phase 1 benchmark](https://github.com/MahinAshraful/quorin-benchmarks/actions/workflows/benchmark_phase1.yml/badge.svg)](.github/workflows/benchmark_phase1.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![Platform: Linux/WSL2](https://img.shields.io/badge/platform-Linux%20%7C%20WSL2-lightgrey.svg)](#)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](#license)

Comparative benchmarks for the [`quorin`](https://pypi.org/project/quorin/)
ML feature-serving library, against the alternatives a team picking a
feature store today would actually consider.

This repo is **separate** from the `quorin` source tree. Its results
are not used to gate Quorin's CI (Quorin has its own regression
suite). Its purpose is the question every README reader arrives with:
"how does this compare?"

### TL;DR

- **What it benchmarks:** Quorin vs. Redis HGETALL vs. in-process Python `dict` vs. stdlib `multiprocessing.shared_memory` on warm/cold reads, batch reads (10 → 10k), and a 95/5 mixed workload.
- **How it runs:** N=20 fresh subprocesses per (scenario × store), `median(p99)` reported, never a max-of-max-of-max.
- **Where:** Linux/WSL2, single-machine, all stores warm, no disk, no network beyond Redis on localhost.
- **Try it:** `make install && docker run -d -p 6379:6379 redis:7 && make benchmark-ci && make summary` (~10 min).

> **Linux/WSL2 only.** Same platform scope as Quorin itself.
>
> **Reporting policy.** All measurements are reported as observed.
> If a competing store outperforms Quorin on a given workload, the
> result table reflects that. If Quorin's headline claim is weaker
> on a particular hardware class, the result table reflects that.
> Bare-metal extrapolations appear only as footnotes, never as the
> primary reported number.

### Contents

- [Headline comparison](#headline-comparison)
- [What this measures (and what it does not)](#what-this-measures-and-what-it-does-not)
- [Reproducing the numbers](#reproducing-the-numbers)
- [Repo layout](#repo-layout)
- [Methodology rigor](#methodology-rigor-mirrors-quorins-adr-015)
- [Adding a store](#adding-a-store-phase-2-expansion) · [Adding a scenario](#adding-a-scenario)
- [Layout of `results/`](#layout-of-results)
- [License](#license)

---

## Headline comparison

The table below is regenerated from the result JSONs in
`results/ubuntu-latest/` after every CI run. Numbers are
`median(p99)` aggregated across N=5 fresh subprocesses (CI) or N=20
(operator runs). Methodology details below.

<!-- BEGIN HEADLINE TABLE -->
_Populate this section with `make benchmark && make readme-table`. The
table compares Quorin, Redis HGETALL, Python in-process `dict`, and
stdlib `multiprocessing.shared_memory` across `single_read` (warm + cold),
`batch_read` (n=100, n=1000), and `mixed_workload` (95% read / 5% write,
full throttle) on the venue listed in `_hardware.json`._
<!-- END HEADLINE TABLE -->

The `inprocess_dict` column is the latency floor — the best a
single-process Python program can achieve, with no serialization or
IPC. If Quorin gets within ~3× of it on the warm path, that bounds
Quorin's overhead. The `redis_hgetall` column represents the most
common production setup today and is the primary comparison point.
The `stdlib_shm` column shows raw single-process layout speed using
`multiprocessing.shared_memory`; Quorin's
[ADR-001](https://github.com/MahinAshraful/Quorin/blob/main/docs/adr/001-posix-shm-over-multiprocessing-shared-memory.md)
documents why that approach gives up cross-process correctness, but
the layout numbers themselves remain a valid datapoint.

---

## What this measures (and what it does not)

We measure **single-machine** read/write latency with all stores
warm. Phase 1 deliberately does NOT cross network boundaries beyond
Redis on localhost, does NOT touch disk for any store, does NOT model
durability.

| Phase | Status | Adds |
|---|---|---|
| 1 | shipped | Quorin / Redis HGETALL / Python dict / stdlib shm × `single_read` warm+cold / `batch_read` × {10, 100, 1k, 10k} / `mixed_workload` 95/5 |
| 2 | stubs in tree | Plasma / Feast / lmdb / Memcached × multi-process concurrent / cold-start / sustained-throughput / crash-recovery |
| 3 | planned | AWS c6i / c7g / Apple Silicon / bare-metal venue |
| 4 | planned | End-to-end ML serving stacks (Triton, BentoML) |
| 5 | planned | Operational benchmarks: schema-upgrade impact, capacity-boundary stress |

### Honest disclosures

* **Cold-cache numbers are CPU-cache-cold, not page-cache-cold.**
  Tmpfs `/dev/shm` is RAM-resident; we don't `posix_fadvise` because
  it doesn't apply to tmpfs. (Mirrors Quorin's
  [ADR-015 §4 "honest disclosure (1)"](https://github.com/MahinAshraful/Quorin/blob/main/docs/adr/015-benchmark-methodology.md).)
* **Numbers are venue-specific.** GitHub Actions `ubuntu-latest`
  uses older Xeons with ~30 MB shared L3. Modern desktop CPUs (Ryzen
  7950X, Apple M3, etc.) are 1.5–3× faster on Quorin's hot path; we
  document this in `results/<hardware>/summary.md` per venue, never
  collapse to a single number.
* **`stdlib_shm` is single-process in Phase 1.** Quorin's
  [ADR-001](https://github.com/MahinAshraful/Quorin/blob/main/docs/adr/001-posix-shm-over-multiprocessing-shared-memory.md)
  documents the `multiprocessing.shared_memory` `resource_tracker`
  failure mode that unlinks segments on clean reader exit, destroying
  data still in use by other processes. Phase 1 measures only raw
  single-process layout speed; the cross-process correctness gap
  surfaces in Phase 2's `multiprocess_concurrent` scenario.
* **Quorin's hot-path number does not include Numba's ~200 ms
  cold-start cost.** Cold-start latency is a separate scenario in
  Phase 2 and is reported independently.

---

## Reproducing the numbers

### On a fresh WSL2 Ubuntu shell (recommended)

```bash
# 1. Clone the repo
git clone https://github.com/MahinAshraful/quorin-benchmarks
cd quorin-benchmarks

# 2. Bring up Redis (any localhost Redis works; Docker is convenient)
docker run -d --name qbench-redis -p 6379:6379 redis:7

# 3. Install Python deps
make install

# 4. Run the full Phase-1 N=20 matrix (~20 min on ubuntu-latest)
make benchmark

# 5. Render the markdown summary, then open results/<hardware>/summary.md
make summary
```

For a faster regression check, `make benchmark-ci` runs the N=5 matrix
(~5 min). N=20 is the published-number configuration; N=5 is intended
only for fast regression detection in CI.

### Via Docker

```bash
# Start Redis (skip if you already have one on localhost:6379)
docker run -d --name qbench-redis -p 6379:6379 redis:7

# Build and run the benchmarks; results land in ./results
docker build -t quorin-benchmarks -f docker/Dockerfile .
docker run --rm --shm-size=2g \
  --network host \
  -e QUORIN_BENCH_REDIS_URL=redis://localhost:6379 \
  -v "$(pwd)/results:/app/results" \
  quorin-benchmarks make benchmark NUM_RUNS=20
```

### From a CI artifact

GitHub Actions runs Phase 1 on every push to `main` (N=5) and
publishes the result JSONs as a workflow artifact. Download from
the latest green run on the
[`benchmark-phase1` workflow](.github/workflows/benchmark_phase1.yml).
The `benchmark-full-matrix` workflow (`workflow_dispatch` only) runs
N=20 instead.

---

## Repo layout

```
quorin-benchmarks/
├── benchscripts/           # canonical schema + data + L3-clobber helpers
├── stores/                 # one adapter per backend (Phase-1: 4 implemented)
├── scenarios/              # one workload per file (Phase-1: 3 implemented)
├── runners/                # fresh-subprocess orchestrator + matrix runner
├── analysis/               # JSON -> markdown table generator
├── results/<hw>/<scenario>/<store>.json   # all measurement data
├── docker/Dockerfile       # reproducible reference env
└── .github/workflows/      # benchmark_phase1.yml + benchmark_full_matrix.yml
```

The README, the per-adapter docstrings in `stores/`, and the per-scenario
docstrings in `scenarios/` carry the design rationale. Adapter and scenario
files are reference implementations: copy the closest match when adding new
ones.

---

## Methodology rigor (mirrors Quorin's [ADR-015](https://github.com/MahinAshraful/Quorin/blob/main/docs/adr/015-benchmark-methodology.md))

1. **Fresh subprocess per data point.** N=20 brand-new Python
   interpreters per (scenario, store) combination. Reports
   `median(p99)`, `stddev(p99)`, `max_of_max`. Never `max-of-max-of-max`.
2. **Identical input data across stores.** A single `_data.py` builds
   the entity-id list and row payloads once, deterministically seeded.
   All stores' setup phases load from the same in-memory structure.
3. **Numba prewarm BEFORE the timed loop.** Quorin's adapter calls
   `quorin.assembly.prewarm()` in setup. Other stores have nothing
   equivalent; setup-vs-measurement split is identical for parity.
4. **Cold-cache via 4×L3 clobber, not numactl.** Detect L3 from
   `/sys/devices/system/cpu/cpu0/cache/index3/size`; fall back to 16 MiB
   with a `WARN` (not L2 — silently measures L2-cold). Traverse the
   array between calls.
5. **Hardware metadata captured per run.** `_hardware.json` per
   hardware class: kernel, CPU model, /proc/cpuinfo, /dev/shm size,
   pinned dep versions.
6. **Pinned everything.** Python 3.12+, Quorin `==0.1.0`, all deps
   pinned with `==`.
7. **JSONs committed to the repo.** Markdown summaries are generated
   from JSONs by `analysis/render_table.py`, never edited by hand.
8. **Visible progress.** Every (scenario, store, run) prints
   `→ scenario=X store=Y run=07/20 p99=... us` to stderr. A 30-min
   run is not a black box.
9. **Single-process pytest-benchmark numbers are NOT a Phase-1
   deliverable.** Headline numbers come from the N=20 fresh-subprocess
   aggregator. Same rule Quorin's ADR-015 §6 adopted.

---

## Adding a store (Phase 2 expansion)

1. Pick a name (lowercase snake): `lmdb_store`.
2. Implement `stores/lmdb_store.py` with the protocol from
   `stores/_base.py`. The four Phase-1 adapters are reference
   implementations — copy the closest match.
3. Add an entry to `stores/__init__.py::_STORE_MODULES` and the
   class-name map.
4. Run `python -m runners.matrix_runner --phase 1 --stores lmdb_store
   --num-runs 5` to smoke-test.
5. Document any non-obvious requirements in the adapter docstring
   (see `stores/quorin_store.py` for the pattern).

---

## Adding a scenario

1. Pick a name: `multiprocess_concurrent`.
2. Implement `scenarios/multiprocess_concurrent.py` exporting
   `run(store, **kwargs) -> dict[str, float]` plus a `main()` entry
   point that calls `run` and JSON-dumps the result to stdout. The
   three Phase-1 scenarios are reference implementations.
3. Add a combo entry to `runners/matrix_runner.py::_PHASE_1_COMBOS_BASE`
   (or a new `_PHASE_2_COMBOS_BASE` once Phase-2 lands).
4. Smoke test: `python -m runners.fresh_subprocess --scenario X
   --store inprocess_dict --num-runs 1 --output /tmp/x.json -- ...`.

---

## Layout of `results/`

```
results/
├── ubuntu-latest/
│   ├── _hardware.json              # CPU / kernel / mem / dep versions
│   ├── _matrix_summary.json        # which combos ran, exit codes, total time
│   ├── single_read_warm/
│   │   ├── quorin.json
│   │   ├── redis_hgetall.json
│   │   ├── inprocess_dict.json
│   │   └── stdlib_shm.json
│   ├── single_read_cold/...
│   ├── batch_read_n10/...
│   ├── batch_read_n100/...
│   ├── batch_read_n1000/...
│   ├── batch_read_n10000/...
│   ├── mixed_95r_5w/...
│   └── summary.md                  # generated by render_table.py
├── aws-c6i-2xlarge/...             # operator-driven (workflow_dispatch)
└── aws-c7g-2xlarge/...
```

Every JSON has the schema: `{ scenario, store, num_runs, raw_runs,
aggregate, elapsed_seconds, extra_args }`. `aggregate` contains the
`median_pXX`, `stddev_p99`, `max_of_max`. `raw_runs` is committed too
so future analysis can recompute different aggregates.

---

## License

MIT. Same as Quorin.

---

## Where this fits in Quorin's overall design

Quorin's stated goal is to build the most performant single-node
Python ML feature-serving library available. Performance claims of
that shape are only meaningful if they are measurable, reproducible,
and comparable to the alternatives a reader would otherwise reach for.
This repository provides that measurement infrastructure under a
methodology any reader can clone and re-run.
