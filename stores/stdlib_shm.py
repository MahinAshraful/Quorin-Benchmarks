"""stdlib ``multiprocessing.shared_memory`` adapter — manual shared-memory baseline.

This adapter represents the path a developer would take to implement
shared-memory feature serving directly using only the Python standard
library, without Quorin.

What this measures:
* Raw layout speed when shared memory is paired with a process-local
  ``entity_id -> row_index`` dict. Hot path: dict lookup followed by
  a strided numpy slice into the shared-memory buffer. Roughly the
  same shape as Quorin's read minus the slot-table indirection and
  the JIT-compiled assemble path.
* If Quorin matches this baseline, the slot-table indirection adds
  no observable cost on the measured workload. If Quorin is faster
  (achievable through Numba-jitted assemble), the difference is
  attributable to the JIT path.

What this does NOT measure:
* Cross-process correctness. ``multiprocessing.shared_memory`` is the
  module Quorin's ADR-001 explicitly avoids: its ``resource_tracker``
  unlinks segments when readers exit cleanly, destroying data still
  in use by other processes. This adapter is deliberately
  single-process so that failure mode does not appear in the timing
  loop. Cross-process behavior is a Phase-2 scenario, not a Phase-1
  latency comparison.
* Cross-process index resolution. The ``entity_id -> row_index`` table
  here is a Python dict. A correct cross-process implementation would
  require a shared lookup structure — exactly the work Quorin's
  layout module performs. This adapter measures the layout floor
  assuming the indexing problem has been solved separately.

Layout:
* One ``SharedMemory`` block of size ``capacity * row_bytes``.
* ``row_bytes = sum(field byte-widths)``: 4 + 8 + 16*4 + 8 = 84 B.
* Each entity's row at offset ``row_index * row_bytes``.
* Per-process dict ``entity_id -> row_index`` for lookup.
* Read path: dict lookup, slice, numpy decode into the canonical
  float32 output array.
"""

from __future__ import annotations

import struct
from multiprocessing import shared_memory
from typing import Any

import numpy as np

from benchscripts._schema import CANONICAL_ELEMENT_COUNT, CANONICAL_FIELDS

# Byte-width per field. Hand-computed; locks the layout to canonical schema.
_FIELD_BYTES = [
    4,        # feat_a float32 scalar
    8,        # feat_b int64 scalar
    16 * 4,   # feat_c float32[16]
    8,        # feat_d float64 scalar
]
_ROW_BYTES = sum(_FIELD_BYTES)  # 84 bytes/row

# Per-row byte offsets (running cumsum).
_FIELD_OFFSETS = [0]
for _b in _FIELD_BYTES[:-1]:
    _FIELD_OFFSETS.append(_FIELD_OFFSETS[-1] + _b)

# Pre-built struct.pack format for write fast-path. Native byte order
# (`=`), float32 + int64 + 16 float32 + float64.
_PACK_FMT = "=fq" + "f" * 16 + "d"
_STRUCT = struct.Struct(_PACK_FMT)
assert _STRUCT.size == _ROW_BYTES


class StdlibShmStore:
    """Adapter for ``multiprocessing.shared_memory`` (single-process)."""

    name: str = "stdlib_shm"

    def __init__(
        self,
        *,
        capacity: int,
        schema_name: str,  # noqa: ARG002
    ) -> None:
        self._closed = False
        self._capacity = capacity
        self._next_index = 0
        # Process-local ID -> row-index table. Real cross-process designs
        # need a shared variant; we are NOT measuring that here.
        self._index_of: dict[str, int] = {}

        # Single shared memory block sized to capacity. Use a unique-ish
        # name to avoid collisions across concurrent benches.
        size = capacity * _ROW_BYTES
        self._shm = shared_memory.SharedMemory(create=True, size=size)
        # numpy view over the buffer; we'll slice per-row in read/write.
        self._buf = np.frombuffer(self._shm.buf, dtype=np.uint8)
        # Pre-allocated read output buffer.
        self._out = np.empty(CANONICAL_ELEMENT_COUNT, dtype=np.float32)

    def _pack_row_into(self, row: dict[str, Any], dst: Any, *, offset: int) -> None:
        # struct.pack_into writes directly into any buffer-protocol
        # object (memoryview / numpy array). Zero-copy.
        feat_c = row["feat_c"]
        _STRUCT.pack_into(
            dst,
            offset,
            row["feat_a"],
            row["feat_b"],
            *feat_c,
            row["feat_d"],
        )

    def _unpack_into(self, offset: int, out: np.ndarray) -> None:
        # unpack_from reads directly off the SharedMemory buffer — no
        # intermediate `bytes(...)` copy and no second decode pass.
        # vals layout: feat_a, feat_b, feat_c0..feat_c15, feat_d (19 values).
        vals = _STRUCT.unpack_from(self._shm.buf, offset)
        out[0] = vals[0]
        out[1] = vals[1]
        out[2:18] = vals[2:18]
        out[18] = vals[18]

    def populate(self, rows: list[tuple[str, dict[str, Any]]]) -> None:
        for eid, row in rows:
            idx = self._next_index
            if idx >= self._capacity:
                raise RuntimeError(f"stdlib_shm capacity {self._capacity} exceeded")
            self._index_of[eid] = idx
            self._pack_row_into(row, self._shm.buf, offset=idx * _ROW_BYTES)
            self._next_index = idx + 1

    def read(self, entity_id: str) -> np.ndarray:
        offset = self._index_of[entity_id] * _ROW_BYTES
        self._unpack_into(offset, self._out)
        return self._out

    def read_batch(self, entity_ids: list[str]) -> np.ndarray:
        out = np.empty((len(entity_ids), CANONICAL_ELEMENT_COUNT), dtype=np.float32)
        idx_of = self._index_of
        rb = _ROW_BYTES
        unpack_into = self._unpack_into
        for i, eid in enumerate(entity_ids):
            unpack_into(idx_of[eid] * rb, out[i])
        return out

    def write(self, entity_id: str, row: dict[str, Any]) -> None:
        idx = self._index_of.get(entity_id)
        if idx is None:
            idx = self._next_index
            if idx >= self._capacity:
                raise RuntimeError(f"stdlib_shm capacity {self._capacity} exceeded")
            self._index_of[entity_id] = idx
            self._next_index = idx + 1
        self._pack_row_into(row, self._shm.buf, offset=idx * _ROW_BYTES)

    def close(self) -> None:
        if self._closed:
            return
        # Drop numpy view BEFORE closing the SHM (release memoryview ref).
        del self._buf
        try:
            self._shm.close()
        finally:
            try:
                self._shm.unlink()
            except FileNotFoundError:
                pass
        self._closed = True
