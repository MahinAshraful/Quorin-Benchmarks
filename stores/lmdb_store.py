"""lmdb embedded KV store adapter — Phase-2 stub.

Not implemented in Phase 1. lmdb is a memory-mapped B+tree database;
it competes with Quorin for the "single-machine, no separate Redis
process" niche. Useful as a comparison datapoint for users who don't
want to run Redis but still want shared state across processes.

Implementation sketch:
* ``env = lmdb.open(path, map_size=...)``
* Read: ``env.begin() as txn: blob = txn.get(eid.encode())``
* Write: ``with env.begin(write=True) as txn: txn.put(eid.encode(), blob)``
* Cleanup: ``env.close()`` + ``shutil.rmtree(path)``
"""

from __future__ import annotations


class LmdbStore:
    name: str = "lmdb_store"

    def __init__(self, *, capacity: int, schema_name: str) -> None:  # noqa: ARG002
        raise NotImplementedError("lmdb_store is a Phase-2 stub")
