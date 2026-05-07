"""Deterministic row + entity-id generation.

Built ONCE per benchmark setup and reused across all stores. The
generator is seeded so two runs of `make benchmark` on the same
machine see byte-identical input data — variance comes from the
measurement, not the data.

Phase 1 uses a fixed schema (see ``_schema.py``). The output is a list
of ``(entity_id: str, row: dict[str, value])`` tuples that every
``Store.populate`` accepts.

Why a tuple-of-(str, dict) instead of two parallel lists:
  * Stores can stream the loop; no need to coordinate two indexes.
  * Stores that need to also build aux data structures (e.g. the
    in-process dict's `entity_id -> row_index` table) can do so in
    one pass.
"""

from __future__ import annotations

import random
from typing import Any

from benchscripts._schema import CANONICAL_FIELDS

DEFAULT_SEED = 0xC0FFEE


def make_entity_ids(n: int, *, prefix: str = "user_", seed: int = DEFAULT_SEED) -> list[str]:
    """Deterministic entity-id list. Prefix + zero-padded index — easy
    to reason about and easy to dedupe. Width is fixed at 9 so 1B IDs
    sort lexically and so payload size doesn't drift across N choices."""
    return [f"{prefix}{i:09d}" for i in range(n)]


def make_rows(n: int, *, seed: int = DEFAULT_SEED) -> list[dict[str, Any]]:
    """Build n deterministic rows matching the canonical schema.

    Field generation rules (deliberately pedestrian — we are NOT
    benchmarking RNG quality, just that the data is stable across
    runs):
      * feat_a (float32 scalar): U(-1, 1)
      * feat_b (int64 scalar):   U(0, 1<<32)
      * feat_c (float32, 16):    16x U(-1, 1)
      * feat_d (float64 scalar): U(-1e6, 1e6)
    """
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for _ in range(n):
        row: dict[str, Any] = {}
        for name, _dtype, shape in CANONICAL_FIELDS:
            if shape == ():
                if name == "feat_a":
                    row[name] = rng.uniform(-1, 1)
                elif name == "feat_b":
                    row[name] = rng.randint(0, 1 << 32)
                elif name == "feat_d":
                    row[name] = rng.uniform(-1e6, 1e6)
                else:
                    row[name] = 0
            else:
                # 1-D shaped float32
                row[name] = [rng.uniform(-1, 1) for _ in range(shape[0])]
        rows.append(row)
    return rows


def make_dataset(n: int, *, seed: int = DEFAULT_SEED) -> list[tuple[str, dict[str, Any]]]:
    """Pair entity_ids with rows for a one-shot Store.populate(). One
    deterministic call; identical output across all (store, scenario)."""
    eids = make_entity_ids(n, seed=seed)
    rows = make_rows(n, seed=seed)
    return list(zip(eids, rows, strict=True))
