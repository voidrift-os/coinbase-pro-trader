# Changelog

## 0.1.1
- Add repository hygiene: MIT LICENSE, Python .gitignore
- Add CI badge to README and deployment checklist per project rules
- Scaffold GitHub Actions (ci.yml already present) and document usage
- Add optional MCP docs and a safe TradingView gateway script (no direct order placement)
- Add docs/ai-ides.md for safe AI IDE + MCP docs usage (docs-only)

## 0.1.0
- Add explicit long-only SMA strategy with stop-loss and take-profit
- Implement USD daily loss cap and 3% equity drawdown checks
- Add correlation-based position sizing
- Add symbol validation to drop unavailable pairs
- Wire CLI backtest/live to new modules

