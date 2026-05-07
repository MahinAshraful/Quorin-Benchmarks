"""Multi-process concurrent reads (1, 4, 16, 64 worker processes) — Phase-2 stub.

Implementation sketch:
* Parent populates the store, then forks N child processes via
  ``multiprocessing.Process``. Each child opens the store (Quorin
  reattaches via ``open_current``; Redis reuses the connection;
  stdlib_shm uses ``SharedMemory(name=...)``).
* Each child runs a single_read-style loop for ``duration_seconds``;
  emits its per-percentile dict via stdout JSON.
* Parent aggregates: per-store throughput-vs-N curves + p99 stability
  per worker count.

Note: this is the scenario where stdlib's
``multiprocessing.shared_memory`` shows the bug Quorin's ADR-001
documents. Children exit cleanly -> resource_tracker unlinks the
segment -> parent reads garbage. Phase 2 will write the chaos test
that demonstrates this concretely.
"""

from __future__ import annotations


def run(*args, **kwargs):  # noqa: ARG001
    raise NotImplementedError("multiprocess_concurrent is a Phase-2 stub")
