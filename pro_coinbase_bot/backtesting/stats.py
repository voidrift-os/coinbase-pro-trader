from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class Trade:
    entry_idx: int
    exit_idx: int
    pnl: float


def _as_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex):
        if "timestamp" in df.columns:
            df = df.set_index(pd.to_datetime(df["timestamp"], utc=True))
        else:
            raise ValueError("DataFrame needs DatetimeIndex or a 'timestamp' column.")
    return df.sort_index()


def infer_trades_from_position(df: pd.DataFrame) -> list[Trade]:
    """
    Assumes df has column 'position' (0, +size, or -size) and 'equity' OR 'pnl'.
    We detect entries/exits from sign changes (or 0→nonzero / nonzero→0).
    PnL for a trade is taken as sum of per-bar 'pnl' between entry(exclusive) and exit(inclusive).
    """
    if "position" not in df.columns:
        return []

    pos = df["position"].fillna(0).values
    pnl = df["pnl"].fillna(0).values if "pnl" in df.columns else np.zeros(len(df))
    trades: list[Trade] = []

    in_trade = False
    entry_idx: int | None = None
    for i in range(1, len(df)):
        prev, curr = pos[i - 1], pos[i]
        # enter when we go from 0 to nonzero OR flip sign
        if not in_trade and (prev == 0 and curr != 0):
            in_trade = True
            entry_idx = i
        elif in_trade and ((curr == 0) or (np.sign(curr) != np.sign(prev))):
            # exit at i (before flip) – accumulate pnl between entry..i
            ei = entry_idx if entry_idx is not None else i - 1
            trade_pnl = pnl[ei : i + 1].sum()
            trades.append(Trade(entry_idx=ei, exit_idx=i, pnl=float(trade_pnl)))
            # If we flipped, we immediately consider a new entry at i for the new side
            in_trade = curr != 0
            entry_idx = i if in_trade else None

    return trades


def max_drawdown_from_equity(equity: pd.Series) -> float:
    # returns drawdown in fraction (0..1)
    running_max = equity.cummax()
    dd = (running_max - equity) / running_max.replace(0, np.nan)
    return float(dd.max(skipna=True) or 0.0)


def compute_stats(
    df: pd.DataFrame,
    start_equity: float | None = None,
    periods_per_year: int | None = None,
) -> dict[str, Any]:
    """
    Expects df with:
      - equity (preferred) or pnl (per-bar)
      - position (for trade inference)
    Index should be time; if not, provide 'timestamp' col.

    periods_per_year:
      - If None, infer from median bar spacing (minutes) → 1y/min
    """
    df = _as_datetime_index(df).copy()

    if "equity" not in df.columns:
        if "pnl" not in df.columns:
            raise ValueError("Need 'equity' or 'pnl' column to compute stats.")
        if start_equity is None:
            start_equity = 10_000.0
        df["equity"] = float(start_equity) + df["pnl"].cumsum()

    equity = df["equity"].astype(float)
    net_pnl = float(equity.iloc[-1] - equity.iloc[0])

    # returns (log for stability)
    ret = equity.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    log_ret = np.log1p(ret).replace([np.inf, -np.inf], np.nan).dropna()

    # infer periods/year
    if periods_per_year is None:
        dt = df.index.to_series().diff().dropna()
        if len(dt):
            median_minutes = dt.median().total_seconds() / 60.0
            # 365d * 24h * 60m
            periods_per_year = int(round(365 * 24 * 60 / max(median_minutes, 1)))
        else:
            periods_per_year = 365 * 24 * 60  # fallback: per-minute

    # CAGR
    n_periods = max(len(equity) - 1, 1)
    total_return = float(equity.iloc[-1] / max(equity.iloc[0], 1e-12))
    years = n_periods / float(periods_per_year)
    cagr = (total_return ** (1 / years) - 1) if years > 0 and total_return > 0 else 0.0

    # Sharpe (annualized, rf ~ 0)
    mu = log_ret.mean() * periods_per_year if len(log_ret) else 0.0
    sigma = log_ret.std(ddof=1) * math.sqrt(periods_per_year) if len(log_ret) > 1 else 0.0
    sharpe = (mu / sigma) if sigma and not math.isclose(sigma, 0.0) else 0.0

    # Trades + PF + win-rate
    trades = infer_trades_from_position(df)
    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [-t.pnl for t in trades if t.pnl < 0]
    trade_count = len(trades)
    win_rate = (len(wins) / trade_count) if trade_count else 0.0
    gross_profit = float(sum(wins)) if wins else 0.0
    gross_loss = float(sum(losses)) if losses else 0.0
    pf = (
        (gross_profit / gross_loss)
        if gross_loss > 0
        else (float("inf") if gross_profit > 0 else 0.0)
    )

    # Max drawdown
    max_dd = max_drawdown_from_equity(equity)

    # Exposure: fraction of time in a non-zero position
    exposure = float((df["position"].fillna(0) != 0).mean()) if "position" in df.columns else 0.0

    return {
        "trades": trade_count,
        "win_rate": win_rate,
        "cagr": float(cagr),
        "pf": float(pf if math.isfinite(pf) else 0.0),
        "sharpe": float(sharpe),
        "max_dd": float(max_dd),
        "exposure": float(exposure),
        "net_pnl": float(net_pnl),
        "start": df.index[0].strftime("%Y-%m-%d"),
        "end": df.index[-1].strftime("%Y-%m-%d"),
    }
