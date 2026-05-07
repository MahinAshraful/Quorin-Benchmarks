"""Memcached adapter — Phase-2 stub.

Not implemented in Phase 1. Memcached is an alternative to Redis for
the "remote KV" tier; useful as an additional Phase-2 datapoint for
production teams who already run memcached. Implementation should
mirror ``redis_hgetall.py`` shape: msgpack-blob value, single-RTT
get/set.

Implementation sketch:
* ``client = pymemcache.client.base.Client(("localhost", 11211))``
* Read: ``client.get(eid.encode())``
* Write: ``client.set(eid.encode(), blob)``
* Cleanup: ``client.flush_all()`` (for the bench namespace; production
  flush_all would be reckless).
"""

from __future__ import annotations


class MemcachedStore:
    name: str = "memcached_store"

    def __init__(self, *, capacity: int, schema_name: str) -> None:  # noqa: ARG002
        raise NotImplementedError("memcached_store is a Phase-2 stub")
