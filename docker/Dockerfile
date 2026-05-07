# Reproducible reference environment for quorin-benchmarks.
#
# Usage:
#   docker build -t quorin-benchmarks -f docker/Dockerfile .
#   docker run --rm --shm-size=2g \
#     -v "$(pwd)/results:/app/results" \
#     -e QUORIN_BENCH_REDIS_URL=redis://redis:6379 \
#     --network host \
#     quorin-benchmarks make benchmark NUM_RUNS=20
#
# Notes:
# * --shm-size=2g matches what /dev/shm needs for Phase-1 (10k entities,
#   tiny). Bump for larger workloads.
# * Bring up Redis separately (docker-compose-style) and point at it
#   via QUORIN_BENCH_REDIS_URL. Adapter assumes localhost by default.

FROM python:3.12-slim AS base

# System deps for posix-ipc (Quorin's POSIX shm wrapper) + numba.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        git \
        make \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Phase-1 deps explicitly so a docker layer cache works well.
COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir \
    "quorin==0.1.0" \
    "numpy>=1.26,<2.0" \
    "redis==5.0.8" \
    "msgpack==1.0.8"

# Copy source last so iterations on benchscripts/ don't bust the deps layer.
COPY benchscripts/ /app/benchscripts/
COPY stores/ /app/stores/
COPY scenarios/ /app/scenarios/
COPY runners/ /app/runners/
COPY analysis/ /app/analysis/
COPY Makefile README.md /app/

# Default: run the full Phase-1 matrix with N=5 (CI scope). Override by
# passing `make benchmark NUM_RUNS=20` to `docker run`.
CMD ["make", "benchmark-ci"]
