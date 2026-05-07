"""Cold-start latency — process spawn through first successful read.

Implementation sketch (Phase 2):
* Parent populates the store. Quorin's segment is left in place.
* Spawn N child Python processes via ``subprocess.run``; each child
  imports the store, opens it, does ONE read, prints the elapsed
  time from import-start to read-completion.
* The "cold start" includes: Python interpreter startup, store-module
  import, store ``__init__`` (Numba prewarm for Quorin), and the first
  read. Some stores (Quorin) pay non-trivial cold-start because of
  Numba; ``inprocess_dict`` and ``stdlib_shm`` pay nothing.

This scenario surfaces Quorin's tradeoff most clearly: higher
cold-start cost in exchange for lower hot-path latency. Reporting it
explicitly is required by the project's reporting policy.
"""

from __future__ import annotations


def run(*args, **kwargs):  # noqa: ARG001
    raise NotImplementedError("cold_start is a Phase-2 stub")
