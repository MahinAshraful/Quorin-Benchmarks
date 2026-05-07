"""Single-entity read latency — warm and cold variants.

Output: per-percentile latency dict (seconds) for ``store.read(eid)``.

Configuration:
* ``capacity``: how many entities to populate before measuring.
* ``n_iters``: how many timed reads to collect.
* ``warm``: True for warm-cache reads (consecutive calls). False for
  cold-cache via 4xL3 traversal between calls (ADR-015 §4).
* ``seed``: deterministic per-iteration entity-id selection.

The hot loop is hand-inlined: no function-call wrapper, no list
comprehension. ``perf_counter_ns()`` deltas are written directly into
a pre-allocated ndarray. This minimizes the Python-level overhead
visible to the measurement.

Cold-cache details:
* The clobber array is sized at 4xL3 capped at 1 GB. Allocated once
  outside the timed loop.
* Between every measured ``read()``, we sum-stride-walk the clobber
  array (one cache-line touch per stride). That evicts the working
  set so the next read pays cold-cache cost.
* The traversal sum is folded into a sentinel so the optimizer cannot
  drop the loop. (numpy's `arr[::64].sum()` is a C-level call so it
  isn't hot-loop reorderable, but folding makes intent explicit.)
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
    n_iters: int = 10000,
    warm: bool = True,
    warmup_iters: int = 100,
    seed: int = 0xBEEF,
) -> dict[str, float]:
    """Run the single-read scenario and return per-percentile stats.

    A small ``warmup_iters`` prefix is run BEFORE the timed loop and
    NOT included in any percentile. This burns the first-touch page
    faults, branch-prediction misses, and (for stores with a per-call
    op-cache like Redis pipeline factories) the pool-init costs that
    don't represent steady-state behavior.
    """
    # --- setup ---
    dataset = make_dataset(capacity)
    store.populate(dataset)

    rng = random.Random(seed)
    entity_ids = [eid for eid, _ in dataset]
    chosen = [rng.choice(entity_ids) for _ in range(warmup_iters + n_iters)]

    samples = np.empty(n_iters, dtype=np.float64)
    sentinel = 0  # keep clobber traversal alive

    from time import perf_counter_ns  # noqa: PLC0415
    read = store.read

    if warm:
        # Warmup: discard timings.
        for i in range(warmup_iters):
            read(chosen[i])
        # Measured loop.
        for i in range(n_iters):
            t0 = perf_counter_ns()
            read(chosen[warmup_iters + i])
            samples[i] = perf_counter_ns() - t0
    else:
        clobber = make_clobber_array()
        # Warmup ALSO traverses the clobber array per call so the
        # warm-up itself is cold-cache (otherwise warm-up would hide
        # any cold-cache state we care about measuring).
        for i in range(warmup_iters):
            sentinel ^= traverse(clobber)
            read(chosen[i])
        for i in range(n_iters):
            sentinel ^= traverse(clobber)
            t0 = perf_counter_ns()
            read(chosen[warmup_iters + i])
            samples[i] = perf_counter_ns() - t0

    # Convert ns -> seconds.
    samples_s = samples * 1e-9
    out = percentile_dict(samples_s)
    # Pin sentinel so the clobber loop can't be DCE'd.
    out["_sentinel"] = float(sentinel)
    out["mode"] = "warm" if warm else "cold"  # type: ignore[assignment]
    out["warmup_iters_discarded"] = float(warmup_iters)
    return out


def main() -> None:
    """Subprocess inner-mode entry point — driven by fresh_subprocess.py."""
    import argparse  # noqa: PLC0415
    import json  # noqa: PLC0415
    import sys  # noqa: PLC0415

    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True)
    parser.add_argument("--capacity", type=int, default=10000)
    parser.add_argument("--n-iters", type=int, default=10000)
    parser.add_argument("--mode", choices=["warm", "cold"], default="warm")
    parser.add_argument("--seed", type=int, default=0xBEEF)
    args = parser.parse_args()

    from stores import get_store_class  # noqa: PLC0415

    cls = get_store_class(args.store)
    store = cls(capacity=args.capacity, schema_name="BENCH_SCHEMA")
    try:
        result = run(
            store,
            capacity=args.capacity,
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
