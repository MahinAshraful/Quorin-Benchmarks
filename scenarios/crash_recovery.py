"""SIGKILL a worker, measure watchdog reclaim time — Phase-2 stub.

Implementation sketch:
* Parent populates the store, forks a worker.
* Worker opens the store, does some reads.
* Parent sends SIGKILL (``os.kill(pid, signal.SIGKILL)``), records t0.
* Parent polls the control plane (Quorin: refcount; Redis: nothing
  to clean; stdlib_shm: nothing — and that's the bug).
* For Quorin: t1 is when the watchdog HDELs the dead PID's heartbeat
  and DECRs the refcount, so the segment becomes reclaimable.
* Reports: time-to-reclaim per store. Quorin should be ~150 s
  (heartbeat TTL + watchdog cadence per ADR-013); stdlib_shm should
  be 0 (no recovery; the segment leaks forever or is destroyed
  prematurely depending on resource_tracker timing).

Coarse timing per ADR-012 §11 — we do NOT attempt to instrument
mid-kernel state. SIGKILL + post-join check, sleep 50/100ms.
"""

from __future__ import annotations


def run(*args, **kwargs):  # noqa: ARG001
    raise NotImplementedError("crash_recovery is a Phase-2 stub")
