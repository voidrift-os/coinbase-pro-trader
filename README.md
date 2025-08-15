# pro-coinbase-bot

[![CI](https://github.com/voidrift-os/coinbase-pro-trader/actions/workflows/ci.yml/badge.svg)](https://github.com/voidrift-os/coinbase-pro-trader/actions/workflows/ci.yml)

Python 3.11 trading bot for Coinbase Advanced using ccxt with minimal dependencies.

Strategy and risk features implemented:
- Explicit long-only SMA crossover strategy
  - Enter when close > SMA(fast) and SMA(fast) > SMA(slow)
  - Exit on close < SMA(fast) or stop-loss/take-profit triggers
- Stop-loss and take-profit
  - Defaults: 2% stop, 4% take profit
- Correlation-based position sizing
  - Inverse-correlation weights normalized to 1 across symbols
- Risk management
  - USD daily loss cap (default $500): stop trading when daily PnL <= -cap
  - Max equity drawdown cap at 3%: halt trading when breached
- Symbol validation
  - Any unavailable market pairs are dropped up front
- In-memory OHLCV caching with 3 min TTL
- 3 retries with exponential backoff for exchange calls
- State persistence to state.json for auto-resume

CLI
- Backtest: `python -m pro_coinbase_bot backtest BTC/USD ETH/USD --timeframe 1h --limit 300`
- Live (dry-run placeholder): `python -m pro_coinbase_bot live BTC/USD --timeframe 1h --limit 200 --max 5`

Deployment checklist
- Run make sanity
- Run make backtest and ensure results are reasonable
- Run make ci-all and ensure it is green
- Perform smoke test: make live MAX=5
- Tag a release in Git once CI and smoke tests pass

Notes
- This repository uses ruff, black (line-length 100), and mypy. Ensure lint/type checks pass before PRs.
- Risk caps must not be disabled. Correlation-based sizing must remain enabled.
- See CHANGELOG.md for the latest changes.

Local setup
- pip install -r requirements.txt
- pip install pre-commit
- pre-commit install
- Run checks locally: pre-commit run --all-files

## Development & CI

### Development Commands
- Format code: `make fmt` (Black + Ruff)
- Lint code: `make lint`
- Type check: `make type` (mypy)
- Run tests: `make test`
- Run full CI: `make ci-all`

### Test Markers
We use a custom `performance` marker for slow/stress tests.
- Exclude perf tests (default): `pytest -m "not performance"`
- Run only perf tests: `pytest -m performance`

### Backtests
Run the multi-timeframe/symbol sweep and generate CSV + Markdown summaries:

```bash
make backtests
# results in backtests/results.csv and backtests/results.md
```

What you’ll get
- backtests/results.csv — rows for each (symbol, timeframe)
- backtests/results.md — aggregate + per-symbol table for PRs
- backtests/results.json — machine-readable for dashboards

Optional MCP integrations
- See docs/mcp/ for safe usage of TradingView alerts and other MCP servers. Execution must always flow through the CLI so risk controls are enforced.
- See docs/ai-ides.md for integrating AI-powered IDEs and CDP docs via MCP (docs-only).

