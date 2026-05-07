"""N=20 fresh-subprocess orchestrator (mirrors Quorin's repeat.py).

Why fresh subprocesses (ADR-015 §6): single-run pytest-benchmark of
rare tail events is statistically useless because GC state, page
cache, OS scheduler state, and Python module-level state all carry
over within a process. Fresh subprocesses reset all of that.

What "fresh" means here:
* Each run is a brand-new ``python -m scenarios.<scenario>`` invocation.
* GC state, page cache, scheduler state, Python module-level state —
  all new per subprocess.
* NOT fresh: Numba's on-disk JIT cache, OS file cache for /dev/shm
  paths. The QuorinStore adapter calls ``prewarm()`` in setup so the
  Numba cost is paid before the timed loop, regardless of cache state.

CLI entry::

    python -m runners.fresh_subprocess \\
        --scenario single_read \\
        --store quorin \\
        --num-runs 20 \\
        --output results/<hw>/single_read_warm/quorin.json \\
        -- --capacity 10000 --n-iters 10000 --mode warm

Anything after ``--`` is passed verbatim to the scenario subprocess.

Aggregation: ``median(p99)``, ``stddev(p99)``, ``max_of_max``.
``median(pXX)`` for every percentile reported by the scenario.
``raw_runs`` is committed alongside so future analysis can
recompute different aggregates without re-running.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NUM_RUNS = 20
DEFAULT_TIMEOUT_SECONDS = 600


def run_one_subprocess(
    scenario: str,
    store: str,
    extra_args: list[str],
    *,
    timeout_seconds: int,
    env: dict[str, str],
) -> dict[str, Any]:
    """Spawn one fresh ``python -m scenarios.<scenario>`` invocation.

    The scenario module's ``main()`` writes a single JSON line to
    stdout containing the per-run percentile dict.
    """
    cmd = [
        sys.executable,
        "-m",
        f"scenarios.{scenario}",
        "--store",
        store,
        *extra_args,
    ]
    res = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        env=env,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"subprocess failed for scenario={scenario} store={store}: "
            f"rc={res.returncode}\n--- stdout ---\n{res.stdout}\n"
            f"--- stderr ---\n{res.stderr}"
        )
    # Last non-empty line is the JSON; earlier lines may be diagnostics.
    lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
    if not lines:
        raise RuntimeError(
            f"subprocess produced no output for scenario={scenario} store={store}"
        )
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"subprocess output not JSON: {lines[-1]!r}\nstderr: {res.stderr}"
        ) from e


def _is_numeric(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """median-of-{percentile, max, median, ...} + stddev(p99) + max-of-max.

    Numeric fields are aggregated. Non-numeric fields (e.g. ``mode:
    "warm"``) are passed through unchanged IF every run agrees on the
    value — that preserves config tags like the warm/cold flag in the
    aggregate JSON for at-a-glance reading. Disagreement drops the
    field (with the ``"_${k}_inconsistent": true`` marker so the
    drop is visible).
    """
    if not runs:
        raise ValueError("aggregate() requires at least one run")
    out: dict[str, Any] = {}
    keys = list(runs[0].keys())
    for k in keys:
        numeric_vals = [r[k] for r in runs if k in r and _is_numeric(r[k])]
        if numeric_vals:
            if k.startswith("p") or k in {"median", "min", "mean"}:
                out[f"median_{k}"] = float(np.median(numeric_vals))
            elif k == "max":
                out["max_of_max"] = float(np.max(numeric_vals))
                out["median_max"] = float(np.median(numeric_vals))
            elif k == "n_samples":
                out["total_samples"] = int(np.sum(numeric_vals))
            else:
                # Catch-all: report median for any other numeric we don't
                # have a special case for (achieved_rps, mean_per_key_seconds,
                # read_p99, write_p99, ...).
                out[f"median_{k}"] = float(np.median(numeric_vals))
            continue

        # Non-numeric field: preserve if all runs agree.
        present = [r[k] for r in runs if k in r]
        if not present:
            continue
        if all(v == present[0] for v in present):
            out[k] = present[0]
        else:
            out[f"_{k}_inconsistent"] = True
    p99s = [r["p99"] for r in runs if _is_numeric(r.get("p99"))]
    if p99s:
        out["stddev_p99"] = float(np.std(p99s, ddof=1)) if len(p99s) > 1 else 0.0
        out["n_runs_p99"] = len(p99s)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="runners/fresh_subprocess.py", description=__doc__)
    parser.add_argument("--scenario", required=True, help="scenario module name (e.g. single_read)")
    parser.add_argument("--store", required=True, help="store name (e.g. quorin)")
    parser.add_argument("--num-runs", type=int, default=DEFAULT_NUM_RUNS)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--quiet", action="store_true", help="suppress per-run progress lines"
    )
    parser.add_argument(
        "extra_args", nargs=argparse.REMAINDER, help="passed through to the scenario subprocess (after `--`)"
    )
    args = parser.parse_args(argv)

    # Strip leading `--` if present
    extra = args.extra_args[1:] if args.extra_args and args.extra_args[0] == "--" else args.extra_args

    env = os.environ.copy()

    runs: list[dict[str, Any]] = []
    t0 = time.monotonic()
    for i in range(args.num_runs):
        run_id = f"{i + 1:02d}/{args.num_runs}"
        try:
            run_metrics = run_one_subprocess(
                args.scenario,
                args.store,
                extra,
                timeout_seconds=args.timeout_seconds,
                env=env,
            )
        except RuntimeError as e:
            print(
                f"  [run {run_id}] FAILED: {e}",
                file=sys.stderr,
            )
            return 1
        runs.append(run_metrics)
        elapsed = time.monotonic() - t0
        avg = elapsed / (i + 1)
        eta = avg * (args.num_runs - i - 1)
        if not args.quiet:
            p99_us = run_metrics.get("p99", 0) * 1e6
            line = (
                f"  -> scenario={args.scenario} store={args.store} "
                f"run {run_id} p99={p99_us:.2f}us "
                f"(elapsed {elapsed:.0f}s, eta {eta:.0f}s)"
            )
            # Mixed-workload reports read_p99 / write_p99 instead of p99.
            if "read_p99" in run_metrics:
                rp = run_metrics["read_p99"] * 1e6
                wp = run_metrics.get("write_p99", 0) * 1e6
                line = (
                    f"  -> scenario={args.scenario} store={args.store} "
                    f"run {run_id} read_p99={rp:.2f}us write_p99={wp:.2f}us "
                    f"(elapsed {elapsed:.0f}s, eta {eta:.0f}s)"
                )
            print(line, file=sys.stderr)

    agg = aggregate(runs)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "scenario": args.scenario,
                "store": args.store,
                "num_runs": args.num_runs,
                "extra_args": extra,
                "raw_runs": runs,
                "aggregate": agg,
                "elapsed_seconds": time.monotonic() - t0,
            },
            indent=2,
        )
    )
    if not args.quiet:
        med_p99 = agg.get("median_p99")
        if med_p99 is not None:
            print(
                f"\norchestrator: wrote {args.output}\n"
                f"  median(p99) across {args.num_runs} runs: {med_p99 * 1e6:.2f}us\n"
                f"  stddev(p99):                          {agg.get('stddev_p99', 0) * 1e6:.2f}us\n"
                f"  max_of_max:                           {agg.get('max_of_max', 0) * 1e6:.2f}us",
                file=sys.stderr,
            )
        else:
            print(f"\norchestrator: wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
