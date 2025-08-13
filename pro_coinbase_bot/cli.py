from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import ccxt
import pandas as pd

CACHE_TTL_SECONDS = 180  # 3 minutes
STATE_FILE = Path("state.json")


def _log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    print(f"[{ts}] {msg}")


class RetryError(Exception):
    pass


@dataclass
class TTLCache:
    ttl_seconds: int = CACHE_TTL_SECONDS
    data: dict[tuple[str, str, str, int | None], tuple[float, Any]] = field(default_factory=dict)

    def get(self, key: tuple[str, str, str, int | None]) -> Any | None:
        now = time.time()
        if key in self.data:
            ts, value = self.data[key]
            if now - ts <= self.ttl_seconds:
                return value
            else:
                # expired
                del self.data[key]
        return None

    def set(self, key: tuple[str, str, str, int | None], value: Any) -> None:
        self.data[key] = (time.time(), value)


cache = TTLCache()


def with_retries(fn: Callable[[], Any], *, retries: int = 3, base_delay: float = 0.5) -> Any:
    """Run fn with up to `retries` attempts, exponential backoff.

    Backoff schedule: base_delay * (2 ** attempt), attempt starting at 0.
    """
    last_exc: BaseException | None = None
    for attempt in range(retries):
        try:
            return fn()
        except ccxt.NetworkError as e:
            last_exc = e
        except ccxt.ExchangeError as e:
            last_exc = e
        except Exception:  # fail fast for non-ccxt errors
            raise
        delay = base_delay * (2**attempt)
        _log(f"Retry {attempt + 1}/{retries} after error: {last_exc}. Sleeping {delay:.2f}s")
        time.sleep(delay)
    raise RetryError(f"Failed after {retries} retries: {last_exc}")


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            assert isinstance(data, dict)
            return data
    except Exception:
        return {}


def save_state(state: dict[str, Any]) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, STATE_FILE)


def ohlcv_dataframe(
    exchange: ccxt.Exchange, symbol: str, timeframe: str, limit: int | None = None
) -> pd.DataFrame:
    key = (exchange.id, symbol, timeframe, limit)
    cached = cache.get(key)
    if cached is not None:
        return cached

    def _fetch() -> list[list[float]]:
        return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)  # type: ignore[no-any-return]

    raw = with_retries(_fetch, retries=3)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    cache.set(key, df)
    return df


def validate_symbols(exchange: ccxt.Exchange, symbols: list[str]) -> list[str]:
    markets = with_retries(lambda: exchange.load_markets())
    available = set(markets.keys())
    valid = [s for s in symbols if s in available]
    dropped = [s for s in symbols if s not in available]
    if dropped:
        _log(f"Dropping unavailable pairs: {', '.join(dropped)}")
    return valid


def cmd_backtest(args: argparse.Namespace) -> int:
    from .backtest import Backtester

    exchange = ccxt.coinbaseadvanced({"enableRateLimit": True})
    symbols = validate_symbols(exchange, args.symbols)
    if not symbols:
        _log("No valid symbols after validation. Exiting.")
        return 1

    # Fetch price data
    price_dfs: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        df = ohlcv_dataframe(exchange, sym, args.timeframe, limit=args.limit)
        price_dfs[sym] = df

    # Run backtest with long-only strategy and risk management
    bt = Backtester()
    res = bt.run(price_dfs)
    daily_pnl = res.get("_daily_pnl", 0.0)
    equity = res.get("_equity", 0.0)
    stop_daily = bool(res.get("_stop_daily", 0.0))
    stop_dd = bool(res.get("_stop_dd", 0.0))

    msg = (
        f"Backtest summary: daily_pnl={daily_pnl:.2f} equity={equity:.2f} "
        f"stop_daily={stop_daily} stop_dd={stop_dd}"
    )
    _log(msg)
    for sym in symbols:
        pnl = res.get(sym, 0.0)
        _log(f"  {sym}: pnl={pnl:.2f}")
    return 0


def cmd_live(args: argparse.Namespace) -> int:
    from .backtest import Backtester

    exchange = ccxt.coinbaseadvanced({"enableRateLimit": True})

    state = load_state()
    state.setdefault("runs", 0)
    state.setdefault("last_symbols", args.symbols)
    state.setdefault("last_timeframe", args.timeframe)

    symbols = validate_symbols(exchange, args.symbols)
    if not symbols:
        _log("No valid symbols after validation. Exiting.")
        return 1

    bt = Backtester()
    day_start_equity = float(state.get("equity", 10_000.0))
    daily_pnl = 0.0

    max_iters = args.max if args.max is not None else 5
    for i in range(max_iters):
        # assemble latest data window
        price_dfs: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            df = ohlcv_dataframe(exchange, sym, args.timeframe, limit=args.limit)
            price_dfs[sym] = df
            last = df.iloc[-1]
            _log(f"Live tick {i+1}/{max_iters} {sym} close={last['close']}")

        res = bt.run(price_dfs)
        step_pnl = float(res.get("_daily_pnl", 0.0))
        daily_pnl += step_pnl
        equity = day_start_equity + daily_pnl

        stop_daily = bool(res.get("_stop_daily", 0.0))
        stop_dd = bool(res.get("_stop_dd", 0.0))
        _log(f"Step summary: step_pnl={step_pnl:.2f} daily_pnl={daily_pnl:.2f} equity={equity:.2f}")
        if stop_daily or stop_dd:
            _log("Risk cap reached; halting further trading for today.")
            break

        state["runs"] = int(state.get("runs", 0)) + 1
        state["last_run_ts"] = int(time.time())
        state["last_symbols"] = symbols
        state["last_timeframe"] = args.timeframe
        state["equity"] = equity
        save_state(state)
        if i < max_iters - 1:
            time.sleep(args.sleep)

    _log("Live run completed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pro-coinbase-bot", description="Pro Coinbase Bot CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_bt = sub.add_parser("backtest", help="Run backtests")
    p_bt.add_argument("symbols", nargs="+", help="Trading pairs, e.g., BTC/USD ETH/USD")
    p_bt.add_argument("--timeframe", default="1h", help="CCXT timeframe, default 1h")
    p_bt.add_argument("--limit", type=int, default=200, help="Number of candles to fetch")
    p_bt.set_defaults(func=cmd_backtest)

    p_live = sub.add_parser("live", help="Run live trading loop (dry-run placeholder)")
    p_live.add_argument("symbols", nargs="+", help="Trading pairs, e.g., BTC/USD ETH/USD")
    p_live.add_argument("--timeframe", default="1h", help="CCXT timeframe, default 1h")
    p_live.add_argument("--limit", type=int, default=200, help="Number of candles to fetch")
    p_live.add_argument("--max", type=int, default=5, help="Max iterations for the loop")
    p_live.add_argument("--sleep", type=float, default=5.0, help="Sleep seconds between iterations")
    p_live.set_defaults(func=cmd_live)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
