"""Shared per-scenario helpers: timing primitives + percentile reporting.

Kept tiny so each scenario file is self-contained. The N=20
fresh-subprocess runner (``runners/fresh_subprocess.py``) does the
across-runs aggregation; per-run percentile computation lives here.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

# Percentiles every scenario reports. Same set as Quorin's bench-spec
# YAML convention: 999 -> p99.9, 9999 -> p99.99.
PERCENTILES = (50, 95, 99, 999, 9999)


def percentile_dict(samples_seconds: np.ndarray) -> dict[str, float]:
    """Convert a 1-D ndarray of per-call durations (seconds) to a flat
    percentile dict. Same convention as Quorin's repeat.py: pXX maps
    to ``np.percentile(samples, q)`` where q normalizes 999 -> 99.9.
    """
    out: dict[str, float] = {}
    for pct in PERCENTILES:
        q = float(pct) if pct <= 100 else _normalize(pct)
        out[f"p{pct}"] = float(np.percentile(samples_seconds, q))
    out["min"] = float(samples_seconds.min())
    out["max"] = float(samples_seconds.max())
    out["mean"] = float(samples_seconds.mean())
    out["median"] = float(np.median(samples_seconds))
    out["n_samples"] = int(samples_seconds.size)
    return out


def _normalize(pct: float) -> float:
    s = str(int(pct))
    return float(s[0] + "9." + s[2:])


def now_ns() -> int:
    """Single source of monotonic ns timestamp."""
    return time.perf_counter_ns()


def time_one_call(fn: Any, *args: Any, **kwargs: Any) -> tuple[Any, int]:
    """Call ``fn(*args, **kwargs)`` and return ``(result, duration_ns)``.

    Inlined into hot loops where the function-call overhead matters
    (~30 ns per call). Only used for non-hot-path code paths in
    scenarios.
    """
    t0 = time.perf_counter_ns()
    result = fn(*args, **kwargs)
    return result, time.perf_counter_ns() - t0
