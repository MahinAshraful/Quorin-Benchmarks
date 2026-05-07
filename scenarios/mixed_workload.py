"""Mixed 95/5 read/write workload, full-throttle for ``duration_seconds``.

Output: per-percentile dicts split by op-class (read / write) plus
the **achieved** RPS. Reads and writes are tracked separately because
a slow write must not pollute read tail latency.

Configuration:
* ``write_fraction``: 0.05 default. Each iteration draws a uniform
  in [0, 1); if < write_fraction, do a write; else read.
* ``duration_seconds``: hard wall-clock budget. The loop runs flat
  out (no sleep) until elapsed exceeds this.
* ``capacity``: number of entities populated up front. Writes always
  target an existing entity (key-update pattern, not key-grow), so
  the write-amplification dynamics stay simple for Phase 1.

**Why no target_rps cap.** An earlier revision used ``time.sleep`` to
cap RPS at a configured target. That approach is incorrect on Linux:
``time.sleep`` has approximately 50-200 us minimum granularity, so
any sub-millisecond inter-call budget (above approximately 5k RPS)
is unreachable. Stores with sub-microsecond per-call latency would
sleep through most of each iteration; stores with millisecond-class
per-call latency would never reach the sleep at all. The result is
that two very different per-call latencies could produce nominally
identical RPS numbers. The current implementation runs the loop at
full speed for the configured duration and reports the achieved RPS
directly, which makes the per-store contrast explicit.
"""

from __future__ import annotations

import random
import time
from typing import Any

import numpy as np

from benchscripts._data import make_dataset, make_rows
from scenarios._common import percentile_dict


def run(
    store: Any,
    *,
    capacity: int = 10000,
    write_fraction: float = 0.05,
    duration_seconds: float = 10.0,
    seed: int = 0xFACE,
) -> dict[str, float]:
    dataset = make_dataset(capacity)
    store.populate(dataset)

    rng = random.Random(seed)
    entity_ids = [eid for eid, _ in dataset]

    # Pre-build a pool of write-payloads so we don't allocate dicts in
    # the hot loop. Reuse a smaller pool than capacity to keep memory
    # tight; cycle through it.
    write_pool = make_rows(min(capacity, 4096), seed=seed ^ 0xA5A5)
    write_pool_len = len(write_pool)

    # Pre-roll the operation schedule so the hot loop has no Python
    # overhead beyond the timing primitives + the store call. We
    # over-allocate (~ 2M slots) and trim by elapsed time.
    n_ops_estimate = 2_000_000
    is_write_arr = [rng.random() < write_fraction for _ in range(n_ops_estimate)]
    eid_arr = [rng.choice(entity_ids) for _ in range(n_ops_estimate)]

    read_samples: list[int] = []
    write_samples: list[int] = []

    read = store.read
    write = store.write
    perf_counter_ns = time.perf_counter_ns
    perf_counter = time.perf_counter

    pool_idx = 0
    t_start = perf_counter()
    deadline = t_start + duration_seconds
    op_idx = 0
    while op_idx < n_ops_estimate:
        if perf_counter() >= deadline:
            break

        is_write = is_write_arr[op_idx]
        eid = eid_arr[op_idx]
        op_idx += 1

        if is_write:
            row = write_pool[pool_idx]
            pool_idx = (pool_idx + 1) % write_pool_len
            t0 = perf_counter_ns()
            write(eid, row)
            write_samples.append(perf_counter_ns() - t0)
        else:
            t0 = perf_counter_ns()
            read(eid)
            read_samples.append(perf_counter_ns() - t0)

    elapsed = perf_counter() - t_start
    total_ops = len(read_samples) + len(write_samples)
    achieved_rps = total_ops / elapsed if elapsed > 0 else 0.0

    out: dict[str, float] = {
        "elapsed_seconds": float(elapsed),
        "achieved_rps": float(achieved_rps),
        "total_ops": float(total_ops),
        "read_count": float(len(read_samples)),
        "write_count": float(len(write_samples)),
        "write_fraction": float(write_fraction),
    }
    if read_samples:
        rs = np.asarray(read_samples, dtype=np.float64) * 1e-9
        for k, v in percentile_dict(rs).items():
            out[f"read_{k}"] = v
    if write_samples:
        ws = np.asarray(write_samples, dtype=np.float64) * 1e-9
        for k, v in percentile_dict(ws).items():
            out[f"write_{k}"] = v
    return out


def main() -> None:
    import argparse  # noqa: PLC0415
    import json  # noqa: PLC0415
    import sys  # noqa: PLC0415

    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True)
    parser.add_argument("--capacity", type=int, default=10000)
    parser.add_argument("--write-fraction", type=float, default=0.05)
    parser.add_argument("--duration-seconds", type=float, default=10.0)
    parser.add_argument("--seed", type=int, default=0xFACE)
    args = parser.parse_args()

    from stores import get_store_class  # noqa: PLC0415

    cls = get_store_class(args.store)
    store = cls(capacity=args.capacity, schema_name="BENCH_SCHEMA")
    try:
        result = run(
            store,
            capacity=args.capacity,
            write_fraction=args.write_fraction,
            duration_seconds=args.duration_seconds,
            seed=args.seed,
        )
    finally:
        store.close()
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
