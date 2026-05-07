"""Redis HGETALL adapter — the most common production setup today.

What we measure (and why):

* **Storage shape**: one Redis hash key per entity_id (``ent:{eid}``).
  The hash has a single ``blob`` field holding the msgpack-packed
  row. This matches the encoding pattern used by mature production
  systems: packing 4-200 fields into a hash with one HGET-blob is
  significantly faster than 4-200 separate field round-trips.
  Phase 1 measures this configuration. A field-by-field HGETALL
  variant is reserved for Phase 2 as a contrast.

* **Hot read**: ``HGET ent:{eid} blob`` (single round-trip), then
  msgpack-unpack and cast into the canonical float32 array. The HGET
  round-trip dominates (~30-80 us on localhost; see Quorin's ADR-002
  for the per-read Redis cost analysis). The msgpack unpack adds a
  small constant on top.

* **Batch read**: ``pipeline.hget(...)`` per entity, single
  ``execute()``. Pipelined RTT is the only honest comparison to
  Quorin's Numba batch loop.

* **Write**: ``HSET ent:{eid} blob ...`` (single command). 5% mixed
  workload uses this.

* **Cleanup**: scan + delete all ``ent:*`` keys we created. Best-
  effort; if Redis is unreachable we log and move on (the next run
  will pick up the orphans during populate's HSET — they're keyed
  by the same prefix and will be overwritten).

The msgpack encoding is intentionally simple: one ``[feat_a, feat_b,
feat_c (list of 16 floats), feat_d]`` list. We do NOT use a dict
keyed by field name — that's twice the bytes and zero benefit for
the comparison. Production code with mature codepaths uses positional
encoding.
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np

from benchscripts._schema import CANONICAL_ELEMENT_COUNT, CANONICAL_FIELDS

DEFAULT_REDIS_URL = os.environ.get("QUORIN_BENCH_REDIS_URL", "redis://localhost:6379")
KEY_PREFIX = "qbench:ent:"  # bench-only namespace, distinct from any prod use

_BLOB_FIELD = b"blob"  # bytes literal saves an encode per HGET


class RedisHGetAllStore:
    """Adapter for the canonical ``HSET key blob ...`` / ``HGET key blob`` shape."""

    name: str = "redis_hgetall"

    def __init__(
        self,
        *,
        capacity: int,  # noqa: ARG002 - capacity is informational; Redis sizes itself
        schema_name: str,  # noqa: ARG002 - schema_name unused; canonical fields are fixed
        redis_url: str = DEFAULT_REDIS_URL,
    ) -> None:
        import msgpack  # noqa: PLC0415
        import redis as redis_lib  # noqa: PLC0415

        self._closed = False
        self._packer = msgpack.Packer(use_bin_type=True)
        self._unpackb = msgpack.unpackb
        self._redis = redis_lib.Redis.from_url(redis_url)
        # Pre-allocate the read output buffer; reuse per call.
        self._out = np.empty(CANONICAL_ELEMENT_COUNT, dtype=np.float32)
        # Track keys we wrote so close() can clean up exactly what we touched.
        self._written_keys: set[bytes] = set()

    # --------- helpers ---------

    @staticmethod
    def _key(entity_id: str) -> bytes:
        return f"{KEY_PREFIX}{entity_id}".encode()

    def _pack_row(self, row: dict[str, Any]) -> bytes:
        # Positional list mirrors what a real production msgpack codec
        # would emit. Field order is the canonical declaration order.
        ordered = [row[name] for name, _dt, _shape in CANONICAL_FIELDS]
        return self._packer.pack(ordered)

    def _unpack_into(self, blob: bytes, out: np.ndarray) -> np.ndarray:
        # Positional decode -> scatter into canonical float32 vector.
        values = self._unpackb(blob, raw=False)
        idx = 0
        for v, (_name, _dt, shape) in zip(values, CANONICAL_FIELDS, strict=True):
            if shape == ():
                out[idx] = v
                idx += 1
            else:
                # 1-D shaped (only float32 (16,) for canonical schema)
                length = shape[0]
                out[idx : idx + length] = v
                idx += length
        return out

    # --------- Store protocol ---------

    def populate(self, rows: list[tuple[str, dict[str, Any]]]) -> None:
        # Single pipeline for the whole population — the alternative
        # (per-row HSET) would dominate setup time and add nothing to
        # the read measurement.
        pipe = self._redis.pipeline(transaction=False)
        for eid, row in rows:
            k = self._key(eid)
            pipe.hset(k, _BLOB_FIELD, self._pack_row(row))
            self._written_keys.add(k)
        pipe.execute()

    def read(self, entity_id: str) -> np.ndarray:
        blob = self._redis.hget(self._key(entity_id), _BLOB_FIELD)
        if blob is None:
            raise KeyError(entity_id)
        return self._unpack_into(blob, self._out)

    def read_batch(self, entity_ids: list[str]) -> np.ndarray:
        pipe = self._redis.pipeline(transaction=False)
        for eid in entity_ids:
            pipe.hget(self._key(eid), _BLOB_FIELD)
        blobs = pipe.execute()
        out = np.empty((len(entity_ids), CANONICAL_ELEMENT_COUNT), dtype=np.float32)
        for i, blob in enumerate(blobs):
            if blob is None:
                raise KeyError(entity_ids[i])
            self._unpack_into(blob, out[i])
        return out

    def write(self, entity_id: str, row: dict[str, Any]) -> None:
        k = self._key(entity_id)
        self._redis.hset(k, _BLOB_FIELD, self._pack_row(row))
        self._written_keys.add(k)

    def close(self) -> None:
        if self._closed:
            return
        try:
            if self._written_keys:
                # DEL in chunks of 1000 (Redis command-arg limit comfort).
                keys = list(self._written_keys)
                for i in range(0, len(keys), 1000):
                    self._redis.delete(*keys[i : i + 1000])
        except Exception:  # noqa: BLE001 - close-time best-effort
            pass
        try:
            self._redis.close()
        except Exception:  # noqa: BLE001
            pass
        self._closed = True
