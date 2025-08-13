from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class StrategyConfig:
    fast_sma: int = 20
    slow_sma: int = 50
    stop_loss_pct: float = 0.02  # 2% stop
    take_profit_pct: float = 0.04  # 4% tp


class LongOnlySMAStrategy:
    """
    Explicit long-only strategy using SMA crossover with bar-executed SL/TP checks.

    Signal logic:
    - enter long when close > SMA(fast) and SMA(fast) > SMA(slow)
    - exit when close < SMA(fast) or SL/TP are hit
    """

    def __init__(self, cfg: StrategyConfig | None = None) -> None:
        self.cfg = cfg or StrategyConfig()

    def indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["sma_fast"] = (
            out["close"].rolling(self.cfg.fast_sma, min_periods=self.cfg.fast_sma).mean()
        )
        out["sma_slow"] = (
            out["close"].rolling(self.cfg.slow_sma, min_periods=self.cfg.slow_sma).mean()
        )
        out["signal"] = (out["close"] > out["sma_fast"]) & (out["sma_fast"] > out["sma_slow"])
        return out

    def simulate_symbol(
        self,
        df: pd.DataFrame,
        position_size: float,
        initial_cash: float,
        equity: float,
    ) -> pd.DataFrame:
        """
        Simulate trades for a single symbol with long-only positions and SL/TP.

        position_size: fraction of equity to allocate when entering a new position.
        initial_cash and equity are used for sizing; returns per-bar PnL at close.
        """
        data = self.indicators(df)
        data = data.copy()
        data["pos"] = 0
        data["entry"] = pd.NA
        data["pnl"] = 0.0
        in_pos = False
        entry_price: float | None = None
        qty: float = 0.0
        # iterate row by row
        for i in range(len(data)):
            row = data.iloc[i]
            price = float(row["close"])  # execution at close for simplicity
            if not in_pos:
                if bool(row["signal"]):
                    # allocate
                    alloc_cash = equity * position_size
                    if alloc_cash > 0 and price > 0:
                        qty = alloc_cash / price
                        entry_price = price
                        in_pos = True
                        data.iat[i, data.columns.get_loc("pos")] = 1
                        data.iat[i, data.columns.get_loc("entry")] = entry_price
                # else remain flat
            else:
                # manage SL/TP within the bar using high/low approximations
                assert entry_price is not None
                stop = entry_price * (1 - self.cfg.stop_loss_pct)
                tp = entry_price * (1 + self.cfg.take_profit_pct)
                low = float(row["low"]) if not pd.isna(row["low"]) else price
                high = float(row["high"]) if not pd.isna(row["high"]) else price
                exit_price: float | None = None
                if low <= stop:
                    exit_price = stop
                elif high >= tp:
                    exit_price = tp
                elif not bool(row["signal"]):
                    exit_price = price
                if exit_price is not None:
                    # realize PnL
                    pnl = (exit_price - entry_price) * qty
                    data.iat[i, data.columns.get_loc("pnl")] = pnl
                    in_pos = False
                    entry_price = None
                    qty = 0.0
                else:
                    # hold, mark-to-market PnL at close
                    mtm = (price - entry_price) * qty
                    data.iat[i, data.columns.get_loc("pnl")] = mtm
                    data.iat[i, data.columns.get_loc("pos")] = 1
                    data.iat[i, data.columns.get_loc("entry")] = entry_price
        return data
