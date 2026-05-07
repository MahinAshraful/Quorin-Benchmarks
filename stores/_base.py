"""Store adapter Protocol — the contract every backend implements.

A Store is a stateful object scoped to a single benchmark run:
``__init__`` connects / creates, ``populate`` does a one-shot bulk
load, ``read`` / ``read_batch`` / ``write`` are the timed hot paths,
and ``close`` releases everything (no /dev/shm leaks, no Redis keys
left around) so the next run starts fresh.

All stores return the **same shape** from ``read``: an
``np.ndarray`` of dtype ``float32`` with one element per element in
the canonical schema (see ``benchscripts/_schema.py``). Stores that
internally hold typed dicts (Redis HGETALL with msgpack blob,
in-process dict) reconstruct that array on read so scenario code is
store-agnostic.

Why a Protocol and not an ABC: we want adapter modules to be
importable *without* any subclass machinery, and we want type
checkers (mypy, pyright) to verify duck-typing rather than ancestry.
The Protocol gives us that.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class Store(Protocol):
    """Backend-agnostic adapter for ML-feature read/write benchmarks."""

    name: str  # human-readable, lowercase-snake (e.g. "quorin")

    def __init__(self, *, capacity: int, schema_name: str) -> None:
        """Create / connect. ``capacity`` is the max number of distinct
        entity IDs the store will hold. ``schema_name`` is the canonical
        name from ``_schema.py``."""
        ...

    def populate(self, rows: list[tuple[str, dict[str, Any]]]) -> None:
        """One-shot bulk load. Called once per benchmark run, before
        any timed measurement. Stores that have a fast bulk path may
        use it; per-store notes in the adapter docstring document
        the choice."""
        ...

    def read(self, entity_id: str) -> np.ndarray:
        """Single-entity hot read. Returns float32 1-D array in the
        canonical schema's declaration order. This is the primary
        latency surface measured."""
        ...

    def read_batch(self, entity_ids: list[str]) -> np.ndarray:
        """Batch hot read. Returns float32 2-D array, shape
        ``(len(entity_ids), CANONICAL_ELEMENT_COUNT)``."""
        ...

    def write(self, entity_id: str, row: dict[str, Any]) -> None:
        """Single-entity hot write. The mixed_workload scenario uses
        this for the 5% write fraction. Stores can implement this any
        way that's honest (e.g. Redis: HSET; Quorin: in-process
        per-row insert; dict: assignment)."""
        ...

    def close(self) -> None:
        """Release all resources. After close(), the store is unusable.
        Idempotent so a finally-block can call it without risk."""
        ...
