"""Canonical FeatureSchema for Phase-1 cross-store comparison.

Phase 1 fixes ONE schema across every (store, scenario) combination so
the comparison is apples-to-apples. The shape mirrors a realistic but
small ML feature row: 4 fields, 19 elements total, output dtype
float32.

Total per-row payload size (after Quorin's pack_row layout):
    feat_a (float32)        4 B
    feat_b (int64)          8 B
    feat_c (float32 x16)    64 B
    feat_d (float64)        8 B
    -----                   84 B raw payload (Quorin lays this out
                                 cache-line-aligned, so the on-segment
                                 row size is larger; the user-visible
                                 assemble output is 19 float32 = 76 B)

Adapters that don't use Quorin's layout (Redis HGETALL, dict, stdlib
shm) MUST return an `np.ndarray` of shape `(19,)` dtype `float32` from
`read()` / `read_batch()` so scenario code can treat all stores
identically. Declaration order is preserved.

The schema name + version are fixed at "BENCH_SCHEMA" / 1. Tests /
benches that need a fresh segment use the canonical name + version;
isolation between runs is via the Quorin-internal segment-name UUID
suffix the registry adds.
"""

from __future__ import annotations

from dataclasses import dataclass

CANONICAL_SCHEMA_NAME = "BENCH_SCHEMA"
CANONICAL_SCHEMA_VERSION = 1

# 4 fields, 19 elements total. The exact set is part of the contract:
# any change here invalidates every committed result JSON.
CANONICAL_FIELDS: list[tuple[str, str, tuple[int, ...]]] = [
    ("feat_a", "float32", ()),
    ("feat_b", "int64", ()),
    ("feat_c", "float32", (16,)),
    ("feat_d", "float64", ()),
]

# Total element count of the assembled float32 output vector.
CANONICAL_ELEMENT_COUNT = 1 + 1 + 16 + 1  # = 19


@dataclass(frozen=True)
class CanonicalField:
    name: str
    dtype: str
    shape: tuple[int, ...]


def canonical_field_specs() -> list[CanonicalField]:
    """Return the canonical fields as typed dataclass instances."""
    return [CanonicalField(name=n, dtype=d, shape=s) for n, d, s in CANONICAL_FIELDS]


def quorin_schema_class():  # type: ignore[no-untyped-def]
    """Construct the Quorin FeatureSchema class on demand.

    Lazy import so non-Quorin adapters (Redis, dict, stdlib_shm) don't
    pull `quorin` and Numba into their import path. Stores that don't
    need Quorin should not import this function.
    """
    from quorin.schema import FeatureField, FeatureSchema, dtype  # noqa: PLC0415

    dt_map = {
        "float32": dtype.float32,
        "float64": dtype.float64,
        "int32": dtype.int32,
        "int64": dtype.int64,
        "uint8": dtype.uint8,
    }

    class BenchSchema(FeatureSchema):
        version = CANONICAL_SCHEMA_VERSION
        fields = [
            FeatureField(name=n, dtype=dt_map[d], shape=s) for n, d, s in CANONICAL_FIELDS
        ]

    BenchSchema.__name__ = CANONICAL_SCHEMA_NAME
    BenchSchema.__qualname__ = CANONICAL_SCHEMA_NAME
    return BenchSchema
