"""Quorin adapter — POSIX shared memory + Numba assemble.

Phase-1 design choices (documented for ADR-015 §"honest disclosure"):

* ``populate`` uses **per-row** ``pack_row + insert``, NOT the bulk
  Numba ``insert_many`` kernel. Reason: keep parity with what the
  other Phase-1 stores can do — they all loop over rows. Bulk insert
  is a Quorin-internal optimization that's out of scope for the
  Phase-1 read-comparison; comparing it to Redis's HSET-per-row is
  unfair in the wrong direction. A Phase-2 ``bulk_load`` scenario
  will exercise ``insert_many``.

* ``read`` calls ``quorin.assembly.assemble`` (the Numba hot path),
  not ``quorin.serving.assemble`` (the Python oracle). The Numba
  path is what the headline ~5 us p99 claim is built on.

* ``read_batch`` is a Python loop over ``assemble``, NOT
  ``quorin.assembly.assemble_batch``. Reason: parity with the other
  three Phase-1 stores, which have no vectorized batch path. Phase
  2's ``batch_throughput`` scenario will exercise the kernel
  separately.

* ``__init__`` calls ``prewarm()`` synchronously. The first call
  triggers Numba's LLVM init (~200 ms); paying it in setup keeps
  measurement honest.

* ``close()`` calls ``registry.close + posix_shm.unlink`` to ensure
  /dev/shm is clean even though we run in-process (no watchdog).
  Idempotent: a second close is a no-op.

Requires Redis at the URL passed via ``redis_url`` kwarg or the
default ``redis://localhost:6379``. Quorin's control plane lives
there even though the read hot path never touches it.
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np

from benchscripts._schema import CANONICAL_ELEMENT_COUNT, quorin_schema_class

DEFAULT_REDIS_URL = os.environ.get("QUORIN_BENCH_REDIS_URL", "redis://localhost:6379")


class QuorinStore:
    """Adapter for the ``quorin`` library."""

    name: str = "quorin"

    def __init__(
        self,
        *,
        capacity: int,
        schema_name: str,  # noqa: ARG002 - kept on the protocol; the canonical name is fixed
        redis_url: str = DEFAULT_REDIS_URL,
    ) -> None:
        # Lazy import keeps `import stores` cheap for non-Quorin paths.
        import redis as redis_lib  # noqa: PLC0415
        from quorin.assembly import assemble, prewarm  # noqa: PLC0415
        from quorin.layout import insert, pack_row  # noqa: PLC0415
        from quorin.shm import SegmentRegistry  # noqa: PLC0415

        self._closed = False
        self._redis_lib = redis_lib
        self._assemble = assemble
        self._pack_row = pack_row
        self._insert = insert

        # We deliberately use the canonical class name from _schema.py
        # ("BENCH_SCHEMA") and do NOT mutate __name__ post-hoc. Quorin
        # derives segment names + control-plane keys from the schema's
        # name; renaming after the class object exists risks splitting
        # the bookkeeping between the compiled form and Quorin's hashes.
        # `schema_name` from the Store protocol is informational only.
        self._schema_class = quorin_schema_class()

        self._redis = redis_lib.Redis.from_url(redis_url)
        self._registry = SegmentRegistry(self._redis)

        # set_current=False so we don't pollute Redis's schema:current
        # pointer (other tests/benches may be running). The bench owns
        # its segment by reference, not by Redis lookup.
        self._segment = self._registry.create(
            self._schema_class,
            capacity=capacity,
            set_current=False,
        )

        # Pre-allocate the assemble output buffer so read() doesn't
        # allocate per-call. The Quorin API supports an `out` kwarg.
        self._out = np.empty(CANONICAL_ELEMENT_COUNT, dtype=np.float32)

        # Pay Numba's LLVM init upfront (~200 ms first call).
        prewarm()

    def populate(self, rows: list[tuple[str, dict[str, Any]]]) -> None:
        # Per-row path: pack + insert. The pack_row signature accepts
        # **kwargs for the field values.
        for eid, row in rows:
            blob = self._pack_row(self._schema_class, **row)
            self._insert(self._segment, eid, blob)

    def read(self, entity_id: str) -> np.ndarray:
        # `out=self._out` reuses the preallocated buffer and returns it.
        return self._assemble(self._segment, entity_id, out=self._out)

    def read_batch(self, entity_ids: list[str]) -> np.ndarray:
        out = np.empty((len(entity_ids), CANONICAL_ELEMENT_COUNT), dtype=np.float32)
        for i, eid in enumerate(entity_ids):
            self._assemble(self._segment, eid, out=out[i])
        return out

    def write(self, entity_id: str, row: dict[str, Any]) -> None:
        blob = self._pack_row(self._schema_class, **row)
        self._insert(self._segment, entity_id, blob)

    def close(self) -> None:
        if self._closed:
            return
        from quorin._internal import posix_shm  # noqa: PLC0415

        try:
            self._registry.close(self._segment)
        finally:
            try:
                posix_shm.unlink(self._segment.name)
            except FileNotFoundError:
                # Already gone (watchdog or duplicate close).
                pass
        try:
            self._redis.close()
        except Exception:  # noqa: BLE001 - close-time best-effort
            pass
        self._closed = True
