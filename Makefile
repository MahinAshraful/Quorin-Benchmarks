# quorin-benchmarks — top-level entry points
#
# Linux/WSL2 only. Requires:
#   - Python 3.12+
#   - Redis at localhost:6379 (override via QUORIN_BENCH_REDIS_URL)
#   - pip install -e . (or `make install`)
#
# Common targets:
#   make install        # editable install + Phase-1 deps
#   make benchmark      # full Phase-1 N=20 matrix
#   make benchmark-ci   # Phase-1 N=5 matrix (~10 min)
#   make benchmark-headline   # only the headline subset
#   make summary        # render results/<hw>/summary.md
#   make readme-table   # render the headline table for the README
#   make clean          # rm result JSONs (keeps directory structure)

PYTHON ?= python
NUM_RUNS ?= 20

.PHONY: install benchmark benchmark-ci benchmark-headline summary readme-table clean lint typecheck

install:
	$(PYTHON) -m pip install -e .

benchmark:
	$(PYTHON) -m runners.matrix_runner --phase 1 --num-runs $(NUM_RUNS)

benchmark-ci:
	$(PYTHON) -m runners.matrix_runner --phase 1 --num-runs 5

benchmark-headline:
	$(PYTHON) -m runners.matrix_runner --phase 1 --num-runs $(NUM_RUNS) \
		--scenarios single_read mixed

summary:
	$(PYTHON) -m analysis.render_table --scope full --write

readme-table:
	$(PYTHON) -m analysis.render_table --scope headline

clean:
	@find results -type f \( -name '*.json' -o -name '*.md' \) -not -name '.gitkeep' -delete 2>/dev/null || true
	@echo "cleaned results/*/*.json and results/*/summary.md"

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy benchscripts stores scenarios runners analysis
