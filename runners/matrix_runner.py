"""Iterate over the (scenario, store) matrix and run the orchestrator.

This is what ``make benchmark`` calls. It:

1. Detects the hardware-class label (operator override via
   ``--hardware`` or auto-detected via ``hardware_collector``).
2. Writes ``results/<hardware>/_hardware.json`` once.
3. For every (scenario, store) tuple in the chosen phase, calls
   ``runners.fresh_subprocess.main`` with the right scenario args.
4. Prints per-combo progress so a 30-min run isn't a black box.

Phase-1 matrix: 4 stores x 3 scenarios x (warm + cold or batch sizes
or mixed) = the four-store comparison the README headlines.

The exact scenario-arg variants are pinned in this file so the
generated JSONs are predictably named and the CI workflow can locate
them without parsing.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


# A "combo" is a single (scenario, scenario_args, output_filename) entry.
# We expand the matrix into combos rather than nested loops so the result
# JSON paths are immediately predictable.

_PHASE_1_COMBOS_BASE: list[dict[str, Any]] = [
    # single_read warm and cold
    {
        "scenario": "single_read",
        "args": ["--capacity", "10000", "--n-iters", "10000", "--mode", "warm"],
        "subdir": "single_read_warm",
    },
    {
        "scenario": "single_read",
        "args": ["--capacity", "10000", "--n-iters", "5000", "--mode", "cold"],
        "subdir": "single_read_cold",
    },
    # batch_read at four sizes (warm only — cold + batch is Phase 2)
    {
        "scenario": "batch_read",
        "args": ["--capacity", "10000", "--batch-size", "10", "--n-iters", "2000"],
        "subdir": "batch_read_n10",
    },
    {
        "scenario": "batch_read",
        "args": ["--capacity", "10000", "--batch-size", "100", "--n-iters", "2000"],
        "subdir": "batch_read_n100",
    },
    {
        "scenario": "batch_read",
        "args": ["--capacity", "10000", "--batch-size", "1000", "--n-iters", "500"],
        "subdir": "batch_read_n1000",
    },
    {
        "scenario": "batch_read",
        "args": [
            "--capacity",
            "10000",
            "--batch-size",
            "10000",
            "--n-iters",
            "100",
        ],
        "subdir": "batch_read_n10000",
    },
    # mixed_workload: full-throttle (no rate cap), 10s duration.
    # Subdir name documents the workload shape, not a target RPS — we
    # report the achieved RPS in the result JSON.
    {
        "scenario": "mixed_workload",
        "args": [
            "--capacity",
            "10000",
            "--write-fraction",
            "0.05",
            "--duration-seconds",
            "10",
        ],
        "subdir": "mixed_95r_5w",
    },
]


def _phase_1_combos(stores: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for combo in _PHASE_1_COMBOS_BASE:
        for store in stores:
            out.append({**combo, "store": store})
    return out


def _detect_hardware_label() -> str:
    """Heuristic: try GitHub-Actions / WSL2 / generic-linux."""
    import os  # noqa: PLC0415

    if os.environ.get("GITHUB_ACTIONS") == "true":
        return "ubuntu-latest"
    try:
        proc_version = Path("/proc/version").read_text()
    except (FileNotFoundError, OSError):
        return "unknown"
    if "microsoft" in proc_version.lower():
        return "wsl2"
    return "linux-local"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="runners/matrix_runner.py", description=__doc__)
    parser.add_argument(
        "--phase",
        type=int,
        default=1,
        help="benchmark phase (1 = Phase-1; Phase-2+ are stubs and will fail)",
    )
    parser.add_argument(
        "--num-runs",
        type=int,
        default=20,
        help="N for fresh-subprocess aggregator (default 20; CI uses 5)",
    )
    parser.add_argument(
        "--stores",
        nargs="+",
        default=None,
        help="subset of stores to run (default: Phase-1 four)",
    )
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=None,
        help="subset of scenarios (matched by 'subdir' prefix) to run",
    )
    parser.add_argument(
        "--hardware",
        default=None,
        help="hardware label (e.g. 'ubuntu-latest', 'aws-c6i-2xlarge'); auto-detected if not set",
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=REPO_ROOT / "results",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if args.phase != 1:
        print(f"only Phase 1 is implemented; --phase={args.phase} is a stub", file=sys.stderr)
        return 2

    from stores import PHASE_1_STORES  # noqa: PLC0415

    stores = args.stores or list(PHASE_1_STORES)
    hardware = args.hardware or _detect_hardware_label()

    out_root = args.results_root / hardware
    out_root.mkdir(parents=True, exist_ok=True)

    # Hardware metadata (one-shot, overwrites any prior).
    from runners import hardware_collector  # noqa: PLC0415

    hw_path = out_root / "_hardware.json"
    hardware_collector.write(hw_path)
    print(f"matrix_runner: hardware -> {hw_path}", file=sys.stderr)

    combos = _phase_1_combos(stores)
    if args.scenarios:
        combos = [
            c for c in combos
            if any(c["subdir"].startswith(s) for s in args.scenarios)
        ]

    from runners.fresh_subprocess import main as orchestrator_main  # noqa: PLC0415

    summary: dict[str, Any] = {
        "hardware": hardware,
        "phase": args.phase,
        "num_runs": args.num_runs,
        "stores": stores,
        "combos": [],
    }

    t0 = time.monotonic()
    for combo in combos:
        scenario = combo["scenario"]
        store = combo["store"]
        subdir = combo["subdir"]
        scenario_args = combo["args"]

        out_dir = out_root / subdir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{store}.json"

        if not args.quiet:
            print(
                f"\nmatrix_runner: scenario={scenario} store={store} subdir={subdir} -> {out_file}",
                file=sys.stderr,
            )

        orch_argv = [
            "--scenario",
            scenario,
            "--store",
            store,
            "--num-runs",
            str(args.num_runs),
            "--output",
            str(out_file),
            *(["--quiet"] if args.quiet else []),
            "--",
            *scenario_args,
        ]
        rc = orchestrator_main(orch_argv)
        summary["combos"].append({
            "scenario": scenario,
            "store": store,
            "subdir": subdir,
            "output": str(out_file.relative_to(args.results_root.parent)),
            "exit_code": rc,
        })
        if rc != 0:
            print(
                f"matrix_runner: combo {subdir}/{store} failed (rc={rc}); continuing",
                file=sys.stderr,
            )

    summary["elapsed_seconds"] = time.monotonic() - t0
    summary_path = out_root / "_matrix_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\nmatrix_runner: summary -> {summary_path}", file=sys.stderr)
    failed = [c for c in summary["combos"] if c["exit_code"] != 0]
    if failed:
        print(
            f"matrix_runner: {len(failed)} of {len(summary['combos'])} combos FAILED",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
