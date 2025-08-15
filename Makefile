# Defaults (can be overridden: e.g., `make backtest SYMBOLS="BTC/USD ETH/USD" TF=1h LIMIT=300`)
SYMBOLS ?= BTC/USD ETH/USD
TF ?= 1h
LIMIT ?= 200
MAX ?= 5
PYTHON ?= python

# Tools per project rules
BLACK ?= black --line-length 100
RUFF ?= ruff
MYPY ?= mypy
PYTEST ?= pytest
RUN_PYTEST := $(if $(wildcard .venv/bin/pytest),.venv/bin/pytest,$(PYTEST))

# Ensure phony targets
.PHONY: sanity backtest live smoke ci-all install precommit test

# Lint and type checks + quick CLI argument parse sanity
sanity:
	$(RUFF) check pro_coinbase_bot tests
	$(BLACK) --check pro_coinbase_bot tests
	$(MYPY) pro_coinbase_bot/src pro_coinbase_bot/scripts
	$(MYPY) tests
	# dry-parse CLI to ensure entrypoints are intact
	$(PYTHON) -m pro_coinbase_bot --help >/dev/null

# Backtest with configurable symbols/timeframe/limit
backtest:
	$(PYTHON) -m pro_coinbase_bot backtest $(SYMBOLS) --timeframe $(TF) --limit $(LIMIT)

# Live loop (dry-run placeholder in code) with risk controls enforced
live:
	$(PYTHON) -m pro_coinbase_bot live $(SYMBOLS) --timeframe $(TF) --limit $(LIMIT) --max $(MAX)

# Smoke test: short live run; defaults to MAX=5 per deployment rules
smoke:
	$(MAKE) live MAX=$(MAX)

# Developer helpers
install:
	@if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
	@if [ -f requirements-dev.txt ]; then pip install -r requirements-dev.txt; fi

backtests:
	$(PYTHON) -u scripts/run_backtests.py

precommit:
	pre-commit install

# Offline tests (project tests only, with production config)
test:
	PRO_CONFIG=pro_coinbase_bot/config/production.yaml PYTHONPATH=$(PWD) $(RUN_PYTEST) -q pro_coinbase_bot/tests || true

# CI aggregation target: run sanity and project tests
ci-all: sanity
	PRO_CONFIG=pro_coinbase_bot/config/production.yaml PYTHONPATH=$(PWD) $(RUN_PYTEST) -q pro_coinbase_bot/tests

