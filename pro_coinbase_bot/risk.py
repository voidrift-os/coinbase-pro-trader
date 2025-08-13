from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class RiskConfig:
    usd_daily_loss_cap: float = 500.0  # stop trading if daily PnL drops below -cap
    max_drawdown_pct: float = 0.03  # 3% equity drawdown cap


class RiskManager:
    def __init__(self, cfg: RiskConfig | None = None) -> None:
        self.cfg = cfg or RiskConfig()

    def check_daily_loss_cap(self, daily_pnl: float) -> bool:
        """Return True if trading should stop due to daily loss cap breach."""
        return daily_pnl <= -abs(self.cfg.usd_daily_loss_cap)

    def check_drawdown(self, equity_curve: list[float]) -> bool:
        """Return True if max drawdown breached relative to peak-to-trough."""
        if not equity_curve:
            return False
        peak = equity_curve[0]
        max_dd = 0.0
        for v in equity_curve:
            peak = max(peak, v)
            dd = (peak - v) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
            if max_dd >= self.cfg.max_drawdown_pct:
                return True
        return False

    @staticmethod
    def correlation_based_weights(prices: dict[str, pd.Series]) -> dict[str, float]:
        """
        Compute inverse-correlation weights. Assets that are highly correlated
        receive lower weights. Normalize to sum to 1. If fewer than 2 assets,
        return 1.0 for the sole asset.
        """
        if len(prices) == 0:
            return {}
        if len(prices) == 1:
            k = next(iter(prices))
            return {k: 1.0}
        df = pd.DataFrame(prices)
        rets = df.pct_change().dropna(how="any")
        if rets.empty:
            # fallback equal weights
            w = 1.0 / len(prices)
            return {k: w for k in prices}
        corr = rets.corr().fillna(0.0)
        # correlation penalty: sum of absolute correlations per asset
        penalty = corr.abs().sum(axis=1) - 1.0  # exclude self-corr
        inv = 1.0 / (1.0 + penalty)
        raw = inv.clip(lower=0.0)
        s = raw.sum()
        if s <= 0:
            w = 1.0 / len(prices)
            return {k: w for k in prices}
        weights = (raw / s).to_dict()
        return {str(k): float(v) for k, v in weights.items()}
