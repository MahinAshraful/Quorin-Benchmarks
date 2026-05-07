"""L3-detection + cache-clobber array (mirrors Quorin's same helper).

ADR-015 §4: cold-cache via 4xL3 traversal between calls. Detect L3 from
``/sys/devices/system/cpu/cpu0/cache/index3/size``; fall back to 16 MiB
with a WARN log if missing. **Never** fall back to L2 — on WSL2 / VMs
that hide cache hierarchy, ``index2`` reports L2 (a few MB), and a
4xL2 clobber is nowhere near L3 size. The bench would silently measure
L2-cold instead of L3-cold.

Ubuntu CI runners surface real L3 in sysfs; WSL2 / Docker Desktop
typically does not.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

LOGGER = logging.getLogger(__name__)

L3_FALLBACK_BYTES = 16 * 1024 * 1024  # 16 MiB
L3_CAP_BYTES = 1 * 1024 * 1024 * 1024  # 1 GB


def detect_l3_size_bytes() -> int:
    """Read L3 cache size from sysfs. Returns 16 MiB fallback if unavailable."""
    p = Path("/sys/devices/system/cpu/cpu0/cache/index3/size")
    try:
        raw = p.read_text().strip()
        unit = raw[-1].upper()
        num = int(raw[:-1])
        if unit == "K":
            return num * 1024
        if unit == "M":
            return num * 1024 * 1024
        if unit == "G":
            return num * 1024 * 1024 * 1024
        # numeric without unit -> bytes
        return int(raw)
    except (FileNotFoundError, ValueError, OSError):
        LOGGER.warning(
            "cold-cache: /sys/.../index3/size unavailable; using 16 MiB fallback "
            "(4x clobber = 64 MiB). On hosts with L3 > 16 MiB this measures "
            "L2/L3-partial-cold, not L3-cold. Run on bare metal for honest L3-cold."
        )
        return L3_FALLBACK_BYTES


def make_clobber_array() -> np.ndarray:
    """Allocate a 4xL3-sized uint8 array, capped at 1 GB to avoid OOM.

    We use uint8 + a stride of 64 (one cache line) when traversing, so
    each touch evicts a unique line. The total array is 4x L3 to ensure
    every line is replaced.
    """
    target = min(detect_l3_size_bytes() * 4, L3_CAP_BYTES)
    return np.ones(target, dtype=np.uint8)


def traverse(arr: np.ndarray) -> int:
    """Walk a clobber array at 64-byte stride, returning the sum.

    Returning the sum (rather than ignoring) prevents the optimizer from
    eliding the loop entirely. We add the sum into the caller's
    timing-loop hot variable to keep it live.
    """
    # numpy strided sum is the fastest portable way to touch each cache line.
    # Return as int so the caller can fold it into a sentinel (which keeps
    # this loop from being dead-code-eliminated under PGO/aggressive opt).
    return int(arr[::64].sum())
