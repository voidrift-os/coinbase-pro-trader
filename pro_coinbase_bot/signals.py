from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Literal, Protocol

SAFE_TIMEFRAMES: set[str] = {"1m", "5m", "15m", "1h"}


def normalize_symbol(sym: str) -> str:
    s = sym.strip().upper().replace("-", "/")
    if "/" not in s:
        s = f"{s}/USD"
    return s


def cap(value: int, *, max_value: int) -> int:
    return min(int(value), max_value)


@dataclass
class TradeIntent:
    symbol: str
    side: Literal["buy", "sell", "flat"] = (
        "buy"  # strategy is long-only; non-buy intents are ignored upstream
    )
    timeframe: str = "1h"
    limit: int = 200
    max_iters: int = 5
    mode: Literal["backtest", "live"] = "live"
    # Optional size hint (not position sizing; correlation sizing still applies downstream)
    size_hint: float | None = None


class StrategySignalProvider(Protocol):
    def next_intents(self) -> list[TradeIntent]: ...


def route_intent_to_cli(intent: TradeIntent) -> list[str]:
    sym = normalize_symbol(intent.symbol)
    tf = intent.timeframe.lower()
    if tf not in SAFE_TIMEFRAMES:
        tf = "1h"
    limit = cap(intent.limit, max_value=2000)
    max_iters = cap(intent.max_iters, max_value=10)

    mode = intent.mode
    if mode not in {"backtest", "live"}:
        mode = "live"

    # Build python -m pro_coinbase_bot ... args
    return [
        sys.executable,
        "-m",
        "pro_coinbase_bot",
        mode,
        sym,
        "--timeframe",
        tf,
        "--limit",
        str(limit),
        "--max",
        str(max_iters),
    ]
