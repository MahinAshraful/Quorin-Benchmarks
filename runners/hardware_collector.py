"""Capture hardware + environment metadata for a benchmark run.

Output: a flat dict written to ``results/<hardware>/_hardware.json``
once at the start of every ``matrix_runner`` invocation. The result
JSONs reference this file's contents so the headline numbers are
always traceable to the venue they were measured on.

Mirrors Quorin's ADR-015 §"hardware metadata" — kernel version, CPU
model, /proc/cpuinfo, available memory, /dev/shm size, Python version,
pinned dep versions.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any


def _read_file(path: str) -> str | None:
    p = Path(path)
    try:
        return p.read_text()
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _cpuinfo_summary() -> dict[str, Any]:
    raw = _read_file("/proc/cpuinfo")
    if not raw:
        return {}
    cpu_models: list[str] = []
    cpu_count = 0
    for line in raw.splitlines():
        if line.startswith("model name"):
            cpu_count += 1
            model = line.split(":", 1)[1].strip()
            if model not in cpu_models:
                cpu_models.append(model)
    return {
        "cpu_models": cpu_models,
        "logical_cpu_count": cpu_count,
    }


def _meminfo_summary() -> dict[str, Any]:
    raw = _read_file("/proc/meminfo")
    if not raw:
        return {}
    out: dict[str, Any] = {}
    for line in raw.splitlines():
        if line.startswith(("MemTotal:", "MemAvailable:", "SwapTotal:")):
            key, val = line.split(":", 1)
            out[key.strip()] = val.strip()
    return out


def _shm_summary() -> dict[str, Any]:
    """Approximate /dev/shm size (mount tmpfs limit)."""
    out: dict[str, Any] = {}
    try:
        usage = shutil.disk_usage("/dev/shm")
        out["dev_shm_total_bytes"] = usage.total
        out["dev_shm_free_bytes"] = usage.free
    except (FileNotFoundError, OSError):
        out["dev_shm_total_bytes"] = None
        out["dev_shm_free_bytes"] = None
    return out


def _l3_size() -> dict[str, Any]:
    raw = _read_file("/sys/devices/system/cpu/cpu0/cache/index3/size")
    return {"l3_size_raw": raw.strip() if raw else None}


def _kernel() -> dict[str, Any]:
    try:
        uname = platform.uname()
        return {
            "kernel_release": uname.release,
            "kernel_version": uname.version,
            "machine": uname.machine,
            "system": uname.system,
        }
    except OSError:
        return {}


def _wsl_detection() -> dict[str, Any]:
    """Detect WSL2 — relevant because /dev/shm is 9P/virtio-fs there
    and cold-page-fault throughput is ~5x slower than native."""
    raw = _read_file("/proc/version")
    return {
        "is_wsl2": bool(raw and "microsoft" in raw.lower()),
        "proc_version": raw.strip() if raw else None,
    }


PINNED_PACKAGES = (
    "quorin",
    "redis",
    "msgpack",
    "numpy",
    "numba",
    "psutil",
    "posix-ipc",
    "structlog",
    "prometheus-client",
)


def _package_versions() -> dict[str, str]:
    out: dict[str, str] = {}
    for name in PINNED_PACKAGES:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = "<not installed>"
    return out


def _git_metadata() -> dict[str, Any]:
    """If we're in a git repo, capture HEAD sha + dirty flag."""
    out: dict[str, Any] = {"git_sha": None, "git_dirty": None}
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if sha.returncode == 0:
            out["git_sha"] = sha.stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if status.returncode == 0:
            out["git_dirty"] = bool(status.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return out


def collect() -> dict[str, Any]:
    """Build the full metadata dict."""
    return {
        "python_version": sys.version,
        "python_implementation": platform.python_implementation(),
        **_kernel(),
        **_wsl_detection(),
        "cpu": _cpuinfo_summary(),
        **_l3_size(),
        "memory": _meminfo_summary(),
        "shm": _shm_summary(),
        "package_versions": _package_versions(),
        "git": _git_metadata(),
    }


def write(output_path: Path) -> dict[str, Any]:
    data = collect()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2, default=str))
    return data


def main() -> None:
    """CLI entry: ``python -m runners.hardware_collector --output PATH``."""
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = write(args.output)
    print(f"hardware: wrote {args.output}")
    print(f"  python: {sys.version.splitlines()[0]}")
    cpu = data.get("cpu", {})
    if cpu:
        print(f"  cpu: {cpu.get('logical_cpu_count', '?')} logical, {cpu.get('cpu_models', ['?'])[0]}")
    print(f"  is_wsl2: {data.get('is_wsl2')}")


if __name__ == "__main__":
    main()
