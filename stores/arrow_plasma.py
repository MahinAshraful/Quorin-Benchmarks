"""Apache Arrow Plasma / Ray Object Store adapter — Phase-2 stub.

Not implemented in Phase 1. The Plasma store is a shared-memory object
store that's a closer architectural cousin to Quorin than Redis is —
the comparison will be informative but requires either ``ray`` (for
the modern object store) or the legacy ``pyarrow.plasma`` (deprecated
in PyArrow 12+, removed in 14+). Both add nontrivial setup; deferred.

Implementation sketch (when we get there):
* Use ``ray.init(...)`` + ``ray.put(row_bytes)`` for population.
* Read path: ``ray.get(object_ref)`` indexed by per-process
  ``entity_id -> ObjectRef`` dict.
* Cleanup: shut down the Ray runtime.
"""

from __future__ import annotations


class ArrowPlasmaStore:
    name: str = "arrow_plasma"

    def __init__(self, *, capacity: int, schema_name: str) -> None:  # noqa: ARG002
        raise NotImplementedError("arrow_plasma is a Phase-2 stub")
