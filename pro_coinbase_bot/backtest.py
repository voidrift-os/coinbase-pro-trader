from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .risk import RiskConfig, RiskManager
from .strategy import LongOnlySMAStrategy, StrategyConfig


@dataclass
class BacktestConfig:
    initial_equity: float = 10_000.0


class Backtester:
    def __init__(
        self, strat_cfg: StrategyConfig | None = None, risk_cfg: RiskConfig | None = None
    ) -> None:
        self.strategy = LongOnlySMAStrategy(strat_cfg)
        self.risk = RiskManager(risk_cfg)

    def run(self, price_dfs: dict[str, pd.DataFrame]) -> dict[str, float]:
        # compute correlation-based weights on close prices
        closes = {
            sym: df["close"].reset_index(drop=True) for sym, df in price_dfs.items() if not df.empty
        }
        weights = self.risk.correlation_based_weights(closes)
        equity = 10_000.0
        daily_pnl = 0.0
        equity_curve: list[float] = []
        results: dict[str, float] = {}
        for sym, df in price_dfs.items():
            w = float(weights.get(sym, 0.0))
            if w <= 0:
                results[sym] = 0.0
                continue
            sim = self.strategy.simulate_symbol(
                df, position_size=w, initial_cash=equity, equity=equity
            )
            pnl = float(sim["pnl"].iloc[-1]) if len(sim) > 0 else 0.0
            results[sym] = pnl
            daily_pnl += pnl
        equity += daily_pnl
        equity_curve.append(equity)
        # risk checks
        results["_stop_daily"] = 1.0 if self.risk.check_daily_loss_cap(daily_pnl) else 0.0
        results["_stop_dd"] = 1.0 if self.risk.check_drawdown(equity_curve) else 0.0
        results["_equity"] = equity
        results["_daily_pnl"] = daily_pnl
        return results
