"""Chart rendering — Phase-2 stub.

Phase 2 will add ``matplotlib``-based charts of:

* p50 / p95 / p99 / p999 across stores (single_read warm + cold)
* batch_size vs. per-key amortized latency (per store)
* sustained-soak rolling p99 over time (per store)

Phase 1 sticks to markdown tables in ``render_table.py``. No chart
output keeps Phase-1 deps minimal (no matplotlib).
"""

from __future__ import annotations


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001
    raise NotImplementedError("render_charts is a Phase-2 stub")


if __name__ == "__main__":
    raise SystemExit(main())
