"""Read every result JSON and emit a markdown comparison table.

Output: ``results/<hardware>/summary.md`` per hardware class. The
"headline" mode (``--scope headline``) emits a smaller table aimed at
the README — single_read warm + cold, batch_read n=100/1000, mixed
read p99.

Conventions:
* Microseconds for sub-millisecond numbers; milliseconds otherwise.
* p99 is the primary column; p50 is shown for context.
* "—" for missing data (a (scenario, store) combo that didn't land).
* The hardware metadata header (CPU model, kernel, is_wsl2, dep
  versions) is included so a reader can reason about the venue
  without opening _hardware.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def _fmt_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 1e-3:
        return f"{seconds * 1e6:.2f} us"
    if seconds < 1.0:
        return f"{seconds * 1e3:.2f} ms"
    return f"{seconds:.2f} s"


def _load_combo(json_path: Path) -> dict[str, Any]:
    return json.loads(json_path.read_text())


def _aggregate_value(combo_data: dict[str, Any], key: str) -> float | None:
    agg = combo_data.get("aggregate", {})
    return agg.get(key)


def _hardware_header(hw_data: dict[str, Any]) -> str:
    cpu_models = hw_data.get("cpu", {}).get("cpu_models", [])
    cpu = cpu_models[0] if cpu_models else "unknown CPU"
    cpu_count = hw_data.get("cpu", {}).get("logical_cpu_count", "?")
    kernel = hw_data.get("kernel_release", "unknown kernel")
    is_wsl2 = hw_data.get("is_wsl2", False)
    venue = "WSL2" if is_wsl2 else "native Linux"
    pkgs = hw_data.get("package_versions", {})
    quorin = pkgs.get("quorin", "<not installed>")
    py = hw_data.get("python_version", "?").splitlines()[0]
    git = hw_data.get("git", {})
    git_line = ""
    if git.get("git_sha"):
        git_line = f" / git {git['git_sha'][:8]}"
        if git.get("git_dirty"):
            git_line += " (dirty)"

    return (
        f"_Venue: {venue} / kernel {kernel}{git_line}_\n\n"
        f"_CPU: {cpu} ({cpu_count} logical cores)_\n\n"
        f"_Python: {py.split()[1] if ' ' in py else py}, quorin {quorin}_\n"
    )


def render(hardware_dir: Path, *, scope: str = "full") -> str:
    """Build the markdown for one hardware-class results directory."""
    hw_path = hardware_dir / "_hardware.json"
    hw_data = _load_combo(hw_path) if hw_path.exists() else {}

    # Discover store names by scanning the first scenario subdir.
    scenario_dirs = sorted([p for p in hardware_dir.iterdir() if p.is_dir()])
    if not scenario_dirs:
        return f"# No results for `{hardware_dir.name}`\n"

    # Stable column order: stores in PHASE_1 order if known, else alphabetical.
    canonical_order = ["quorin", "redis_hgetall", "inprocess_dict", "stdlib_shm"]
    store_set: set[str] = set()
    for sd in scenario_dirs:
        for jp in sd.glob("*.json"):
            store_set.add(jp.stem)
    stores = [s for s in canonical_order if s in store_set] + sorted(
        s for s in store_set if s not in canonical_order
    )

    # Decide which scenario subdirs to render.
    headline_subdirs = (
        "single_read_warm",
        "single_read_cold",
        "batch_read_n100",
        "batch_read_n1000",
        "mixed_95r_5w",
    )
    if scope == "headline":
        chosen_subdirs = [
            sd for sd in scenario_dirs if sd.name in headline_subdirs
        ]
    else:
        chosen_subdirs = scenario_dirs

    lines: list[str] = []
    lines.append(f"# Results — `{hardware_dir.name}`\n")
    lines.append(_hardware_header(hw_data))
    lines.append("")

    if scope == "headline":
        lines.append("## Headline comparison\n")
    else:
        lines.append("## Full results\n")

    # Table 1: median(p99) per (scenario, store).
    header = "| scenario | metric | " + " | ".join(stores) + " |"
    sep = "|" + "---|" * (2 + len(stores))
    lines.append(header)
    lines.append(sep)

    metrics_to_show = [
        ("median_p50", "p50"),
        ("median_p99", "p99"),
    ]

    for sd in chosen_subdirs:
        combos = {jp.stem: _load_combo(jp) for jp in sd.glob("*.json")}
        if not combos:
            continue
        # mixed_workload reports read_p99 / write_p99 — show those columns instead.
        is_mixed = sd.name.startswith("mixed_")
        if is_mixed:
            mixed_metrics = [
                ("median_read_p99", "read p99"),
                ("median_write_p99", "write p99"),
                ("median_achieved_rps", "achieved RPS"),
            ]
            for key, label in mixed_metrics:
                row = [sd.name, label]
                for store in stores:
                    cd = combos.get(store)
                    val = _aggregate_value(cd, key) if cd else None
                    if "rps" in key.lower():
                        row.append(f"{val:.0f}" if val is not None else "—")
                    else:
                        row.append(_fmt_seconds(val))
                lines.append("| " + " | ".join(row) + " |")
            continue

        for key, label in metrics_to_show:
            row = [sd.name, label]
            for store in stores:
                cd = combos.get(store)
                val = _aggregate_value(cd, key) if cd else None
                row.append(_fmt_seconds(val))
            lines.append("| " + " | ".join(row) + " |")

    if scope != "headline":
        lines.append("")
        lines.append("## stddev(p99) per scenario × store\n")
        sep_h = "| scenario | " + " | ".join(stores) + " |"
        lines.append(sep_h)
        lines.append("|" + "---|" * (1 + len(stores)))
        for sd in scenario_dirs:
            combos = {jp.stem: _load_combo(jp) for jp in sd.glob("*.json")}
            if not combos:
                continue
            row = [sd.name]
            for store in stores:
                cd = combos.get(store)
                val = _aggregate_value(cd, "stddev_p99") if cd else None
                row.append(_fmt_seconds(val))
            lines.append("| " + " | ".join(row) + " |")

    lines.append("")
    lines.append(
        "_All numbers are `median(p99)` aggregated across N fresh subprocess runs "
        "(see `_matrix_summary.json` for N). Stores read float32 vectors of the same "
        "canonical schema; see `progress/plan.md` § 'Per-store implementation notes' "
        "for what each adapter is actually doing under the hood._\n"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="analysis/render_table.py", description=__doc__)
    parser.add_argument(
        "--results-root",
        type=Path,
        default=REPO_ROOT / "results",
    )
    parser.add_argument(
        "--hardware",
        default=None,
        help="render one hardware-class subdir (default: all that exist)",
    )
    parser.add_argument(
        "--scope",
        choices=["full", "headline"],
        default="full",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="also write summary.md into the hardware-class dir",
    )
    args = parser.parse_args(argv)

    if args.hardware:
        targets = [args.results_root / args.hardware]
    else:
        targets = [
            p for p in args.results_root.iterdir()
            if p.is_dir() and (p / "_hardware.json").exists()
        ]
    if not targets:
        print("no hardware-class result directories found", file=sys.stderr)
        return 1

    out_chunks: list[str] = []
    for hw_dir in targets:
        chunk = render(hw_dir, scope=args.scope)
        out_chunks.append(chunk)
        if args.write and args.scope == "full":
            (hw_dir / "summary.md").write_text(chunk)
            print(f"wrote {hw_dir / 'summary.md'}", file=sys.stderr)

    sys.stdout.write("\n\n".join(out_chunks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
