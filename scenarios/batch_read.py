"""Batch-read latency at parametrized batch sizes.

Output: per-percentile latency dict for ``store.read_batch(batch)``.
The reported numbers are **per-batch wall-clock** (seconds). Per-key
amortized latency is also surfaced (``mean_per_key_seconds``) so a
reader can compare to single_read.

Configuration:
* ``batch_size``: 10 / 100 / 1000 / 10000.
* ``n_iters``: how many timed batches to collect.
* ``capacity``: must be >= batch_size; default 10000 for parity with
  single_read.
* ``warm``: True for warm-cache; False for cold-cache (4xL3 clobber
  between batches).

Per-batch entity-ID lists are deterministic but distinct per
iteration so the same indices aren't re-measured back-to-back.
"""

from __future__ import annotations

import random
from typing import Any

import numpy as np

from benchscripts._cache_clobber import make_clobber_array, traverse
from benchscripts._data import make_dataset
from scenarios._common import percentile_dict


def run(
    store: Any,
    *,
    capacity: int = 10000,
    batch_size: int = 100,
    n_iters: int = 1000,
    warm: bool = True,
    warmup_iters: int = 10,
    seed: int = 0xCAFE,
) -> dict[str, float]:
    if batch_size > capacity:
        raise ValueError(f"batch_size {batch_size} > capacity {capacity}")
    dataset = make_dataset(capacity)
    store.populate(dataset)

    rng = random.Random(seed)
    entity_ids = [eid for eid, _ in dataset]
    # Pre-build per-iteration batches so RNG cost doesn't pollute the timing.
    # Warmup batches use the same shape; they're discarded.
    batches = [
        [rng.choice(entity_ids) for _ in range(batch_size)]
        for _ in range(warmup_iters + n_iters)
    ]

    samples = np.empty(n_iters, dtype=np.float64)
    sentinel = 0

    from time import perf_counter_ns  # noqa: PLC0415

    read_batch = store.read_batch

    if warm:
        for i in range(warmup_iters):
            read_batch(batches[i])
        for i in range(n_iters):
            t0 = perf_counter_ns()
            read_batch(batches[warmup_iters + i])
            samples[i] = perf_counter_ns() - t0
    else:
        clobber = make_clobber_array()
        for i in range(warmup_iters):
            sentinel ^= traverse(clobber)
            read_batch(batches[i])
        for i in range(n_iters):
            sentinel ^= traverse(clobber)
            t0 = perf_counter_ns()
            read_batch(batches[warmup_iters + i])
            samples[i] = perf_counter_ns() - t0

    samples_s = samples * 1e-9
    out = percentile_dict(samples_s)
    out["batch_size"] = float(batch_size)
    out["mean_per_key_seconds"] = out["mean"] / batch_size
    out["_sentinel"] = float(sentinel)
    out["mode"] = "warm" if warm else "cold"  # type: ignore[assignment]
    out["warmup_iters_discarded"] = float(warmup_iters)
    return out


def main() -> None:
    import argparse  # noqa: PLC0415
    import json  # noqa: PLC0415
    import sys  # noqa: PLC0415

    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True)
    parser.add_argument("--capacity", type=int, default=10000)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--n-iters", type=int, default=1000)
    parser.add_argument("--mode", choices=["warm", "cold"], default="warm")
    parser.add_argument("--seed", type=int, default=0xCAFE)
    args = parser.parse_args()

    from stores import get_store_class  # noqa: PLC0415

    cls = get_store_class(args.store)
    store = cls(capacity=args.capacity, schema_name="BENCH_SCHEMA")
    try:
        result = run(
            store,
            capacity=args.capacity,
            batch_size=args.batch_size,
            n_iters=args.n_iters,
            warm=(args.mode == "warm"),
            seed=args.seed,
        )
    finally:
        store.close()
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
