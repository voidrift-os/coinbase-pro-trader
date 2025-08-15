import numpy as np
import pandas as pd
from pro_coinbase_bot.backtesting.stats import compute_stats, max_drawdown_from_equity


def test_compute_stats_basic() -> None:
    # 10 bars, long from 2..5 (win), short from 6..9 (loss)
    idx = pd.date_range("2024-01-01", periods=10, freq="H", tz="UTC")
    cum = np.array([0, 0, 1, 2, 3, 3, 1, 2, 1, 1], dtype=float)
    pnl = np.diff(cum, prepend=0)
    pos = [0, 0, 1, 1, 1, 0, -1, -1, 0, 0]
    df = pd.DataFrame(index=idx, data={"pnl": pnl, "position": pos})

    stats = compute_stats(df, start_equity=1000.0, periods_per_year=24 * 365)
    assert stats["trades"] == 2
    assert 0.0 <= stats["win_rate"] <= 1.0
    assert isinstance(stats["pf"], float)
    assert isinstance(stats["max_dd"], float)
    assert "start" in stats and "end" in stats


def test_mdd() -> None:
    idx = pd.date_range("2024-01-01", periods=6, freq="D", tz="UTC")
    eq = pd.Series([100, 120, 110, 130, 90, 95], index=idx)
    mdd = max_drawdown_from_equity(eq)
    assert 0.0 <= mdd <= 1.0
    assert mdd >= (130 - 90) / 130 - 1e-6
