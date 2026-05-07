"""Feast online store (Redis backend) adapter — Phase-2 stub.

Not implemented in Phase 1. Feast adds a meaningful layer on top of
Redis: feature-view registry, point-in-time materialization, type
conversion. Comparing Quorin to Feast-on-Redis isolates "the Feast
overhead on top of the Redis floor" — separately from "the Redis
floor itself" (which ``redis_hgetall`` measures).

Implementation sketch:
* ``feast.FeatureStore(...)`` against a tempdir-config that wires
  Redis as the online store.
* ``store.materialize_incremental`` to populate.
* ``store.get_online_features(...)`` for the read path. Note the
  return type is ``OnlineResponse``; convert to ndarray to match the
  Store protocol.
"""

from __future__ import annotations


class FeastOnlineStore:
    name: str = "feast_online"

    def __init__(self, *, capacity: int, schema_name: str) -> None:  # noqa: ARG002
        raise NotImplementedError("feast_online is a Phase-2 stub")
