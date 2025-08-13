import numpy as np
import pandas as pd
from pro_coinbase_bot.backtest import Backtester


def test_offline_backtester_runs() -> None:
    # synthetic close prices with a simple uptrend and noise
    n = 300
    ts = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    base = np.linspace(100, 120, n)
    noise = np.random.normal(0, 0.2, n)
    close = base + noise
    high = close + 0.3
    low = close - 0.3
    open_ = close
    vol = np.random.randint(1, 10, n)

    df = pd.DataFrame(
        {
            "timestamp": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": vol,
        }
    )

    bt = Backtester()
    res = bt.run({"SYN/USD": df})

    # Basic sanity: keys exist and values are finite numbers
    assert "_daily_pnl" in res
    assert "_equity" in res
    assert "_stop_daily" in res
    assert "_stop_dd" in res

    assert np.isfinite(float(res["_equity"]))
    assert np.isfinite(float(res["_daily_pnl"]))
