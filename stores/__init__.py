"""Store adapters — one implementation per backend.

Phase-1 stores: quorin, redis_hgetall, inprocess_dict, stdlib_shm.
Phase-2 stubs: arrow_plasma, feast_online, lmdb_store, memcached_store.

Use ``get_store(name)`` to map a name to a constructor. Importing the
module directly is fine; importing this package's ``__init__`` does not
pull any backend-specific dependency.
"""

from __future__ import annotations

from typing import Any

# Registry of store-name -> module path for lazy loading.
# Lazy because the four Phase-1 adapters have disjoint dependencies
# (Quorin, redis-py, numpy-only, stdlib) and we don't want a missing
# Phase-2 dep to break Phase-1 runs.
_STORE_MODULES: dict[str, str] = {
    "quorin": "stores.quorin_store",
    "redis_hgetall": "stores.redis_hgetall",
    "inprocess_dict": "stores.inprocess_dict",
    "stdlib_shm": "stores.stdlib_shm",
    # Phase-2 stubs:
    "arrow_plasma": "stores.arrow_plasma",
    "feast_online": "stores.feast_online",
    "lmdb_store": "stores.lmdb_store",
    "memcached_store": "stores.memcached_store",
}

PHASE_1_STORES = ("quorin", "redis_hgetall", "inprocess_dict", "stdlib_shm")


def get_store_class(name: str) -> Any:
    """Import + return the Store class for ``name``. Raises KeyError if unknown."""
    if name not in _STORE_MODULES:
        raise KeyError(f"unknown store {name!r}; known: {sorted(_STORE_MODULES)}")
    import importlib

    mod = importlib.import_module(_STORE_MODULES[name])
    # Convention: every adapter exports a class named after its CamelCase
    # equivalent of the store name (quorin -> QuorinStore, redis_hgetall ->
    # RedisHGetAllStore, etc.).
    cls_name_map = {
        "quorin": "QuorinStore",
        "redis_hgetall": "RedisHGetAllStore",
        "inprocess_dict": "InProcessDictStore",
        "stdlib_shm": "StdlibShmStore",
        "arrow_plasma": "ArrowPlasmaStore",
        "feast_online": "FeastOnlineStore",
        "lmdb_store": "LmdbStore",
        "memcached_store": "MemcachedStore",
    }
    return getattr(mod, cls_name_map[name])
