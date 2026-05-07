"""30-min sustained throughput soak — Phase-2 stub.

Implementation sketch:
* Like ``mixed_workload`` but ``duration_seconds=1800``.
* Reports p99 / p999 stability over rolling 60-second windows.
* The interesting failure modes: page-cache eviction (none of the
  stores are page-cache-bound on tmpfs, but Redis grows incrementally),
  GC stalls (Quorin's gen-2 collections), connection-pool exhaustion
  (Redis), syscall-cache thrash. We expect Quorin's p99 to drift less
  than Redis-via-localhost.
"""

from __future__ import annotations


def run(*args, **kwargs):  # noqa: ARG001
    raise NotImplementedError("sustained_throughput is a Phase-2 stub")
