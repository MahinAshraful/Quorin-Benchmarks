"""Scenario modules — one workload per file.

Each scenario exports a ``run(store, **kwargs) -> dict[str, float]``
function. The runner imports the scenario by name, instantiates the
store, calls ``populate()``, then ``run()``. Stats come back as a
flat dict so they can be merged into result JSON unchanged.

Phase 1: ``single_read``, ``batch_read``, ``mixed_workload``.
Phase 2 stubs: everything else.
"""

from __future__ import annotations

PHASE_1_SCENARIOS = ("single_read", "batch_read", "mixed_workload")
