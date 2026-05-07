"""In-process Python dict — the single-process latency floor.

This adapter establishes the lower bound for any other store on the
benchmark. There is no serialization, no IPC, and no locking. The
canonical float32 array per entity is pre-built at populate time, so
``read`` is a pure dict lookup returning a stored ndarray. Reads do
NOT copy; scenarios treat the returned array as read-only.

What this measures:
* The cost of Python attribute resolution + dict hash + lookup.
  Approximately 80-150 ns on modern hardware. Note that at this
  scale the ``perf_counter_ns`` timing harness contributes a
  significant fraction of the measured latency; see the README's
  "Honest disclosures" section for the framing.
* If Quorin matches or approaches this floor, Quorin's overhead is
  bounded by its Numba assemble + lookup path. A gap of more than
  ~3x indicates optimization headroom.

What this does NOT measure:
* Cross-process visibility. A production system requires every worker
  to see the same data. This adapter is single-process and is not a
  deployable design. Quorin's ``multiprocess_concurrent`` scenario
  in Phase 2 covers that case.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from benchscripts._schema import CANONICAL_ELEMENT_COUNT, CANONICAL_FIELDS


class InProcessDictStore:
    """Latency-floor adapter — Python dict, pre-allocated float32 arrays."""

    name: str = "inprocess_dict"

    def __init__(
        self,
        *,
        capacity: int,
        schema_name: str,  # noqa: ARG002 - canonical fields are fixed
    ) -> None:
        self._closed = False
        # Pre-size the dict to avoid rehash during populate.
        self._table: dict[str, np.ndarray] = {}
        self._capacity = capacity

    @staticmethod
    def _row_to_array(row: dict[str, Any]) -> np.ndarray:
        out = np.empty(CANONICAL_ELEMENT_COUNT, dtype=np.float32)
        idx = 0
        for name, _dt, shape in CANONICAL_FIELDS:
            v = row[name]
            if shape == ():
                out[idx] = v
                idx += 1
            else:
                length = shape[0]
                out[idx : idx + length] = v
                idx += length
        return out

    def populate(self, rows: list[tuple[str, dict[str, Any]]]) -> None:
        for eid, row in rows:
            self._table[eid] = self._row_to_array(row)

    def read(self, entity_id: str) -> np.ndarray:
        return self._table[entity_id]

    def read_batch(self, entity_ids: list[str]) -> np.ndarray:
        out = np.empty((len(entity_ids), CANONICAL_ELEMENT_COUNT), dtype=np.float32)
        t = self._table
        for i, eid in enumerate(entity_ids):
            out[i] = t[eid]
        return out

    def write(self, entity_id: str, row: dict[str, Any]) -> None:
        self._table[entity_id] = self._row_to_array(row)

    def close(self) -> None:
        if self._closed:
            return
        self._table.clear()
        self._closed = True
