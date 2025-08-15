#!/usr/bin/env python3
"""
Batch backtests:
- Timeframes: 15m, 1h, 4h
- Symbols: BTC-USD, ETH-USD, SOL-USD, AVAX-USD, DOGE-USD
- Outputs: backtests/results.csv + results.md with aggregate table

Assumptions:
- You have a `backtest(strategy, symbol, timeframe, **params)` callable that returns a dict like:
  {
    "symbol": str,
    "timeframe": str,
    "trades": int,
    "win_rate": float,     # 0..1
    "cagr": float,         # 0..1
    "pf": float,           # profit factor
    "sharpe": float,
    "max_dd": float,       # 0..1 drawdown
    "exposure": float,     # 0..1
    "net_pnl": float,
    "start": "YYYY-MM-DD",
    "end": "YYYY-MM-DD",
  }
Adapt the import below to your project structure.
"""
from __future__ import annotations
import os, math, json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

import ccxt
import pandas as pd

# Use the project backtester and CLI helpers to reuse symbol validation and OHLCV caching
from pro_coinbase_bot.backtest import Backtester  # type: ignore
from pro_coinbase_bot.cli import ohlcv_dataframe, validate_symbols  # type: ignore
from pro_coinbase_bot.backtesting.stats import compute_stats  # type: ignore
from pro_coinbase_bot.strategy import LongOnlySMAStrategy  # type: ignore

SYMBOLS = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "DOGE-USD"]
TIMEFRAMES = ["15m", "1h", "4h"]

DEFAULT_PARAMS = {
    # Example knobs — tune or remove based on your strategy:
    "fee_bps": 5,             # 0.05%
    "slippage_bps": 2,        # 0.02%
    "warmup_bars": 300,
    "capital": 10_000.0,
    "risk_per_trade": 0.01,
    "allow_short": False,
}

OUT_DIR = Path("backtests")
CSV_PATH = OUT_DIR / "results.csv"
JSON_PATH = OUT_DIR / "results.json"
MD_PATH = OUT_DIR / "results.md"

def _safe(v):
    if v is None:
        return ""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return ""
    return v

def _api_symbol(sym: str) -> str:
    return sym.upper().replace("-", "/")


def _limit_for_tf(tf: str) -> int:
    return {"15m": 500, "1h": 400, "4h": 300}.get(tf, 200)


def run_all() -> List[Dict[str, Any]]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bt = Backtester()
    results: List[Dict[str, Any]] = []

    exchange = ccxt.coinbaseadvanced({"enableRateLimit": True})

    # Validate symbols against exchange markets (uses CLI helper with retries/cache)
    api_symbols = [_api_symbol(s) for s in SYMBOLS]
    valid = validate_symbols(exchange, api_symbols)
    if not valid:
        raise SystemExit("No valid symbols after validation")

# Intersect requested timeframes with exchange-supported timeframes, fallback to 1h
    supported_map = (getattr(exchange, "timeframes", None) or {})
    wanted_tfs = [tf for tf in TIMEFRAMES if tf in supported_map] or ["1h"]

    for tf in wanted_tfs:
        limit = _limit_for_tf(tf)
        for sym in valid:
            # Fetch OHLCV and feed into backtester
            df = ohlcv_dataframe(exchange, sym, tf, limit=limit)
            # Ensure expected columns and timezone
            if df.empty or not set(["timestamp","open","high","low","close","volume"]).issubset(df.columns):
                continue

            # Run SMA strategy per symbol to obtain per-bar position and pnl
            strat = LongOnlySMAStrategy()
            sim_df = strat.simulate_symbol(
                df,
                position_size=float(DEFAULT_PARAMS.get("risk_per_trade", 0.01)),
                initial_cash=float(DEFAULT_PARAMS.get("capital", 10_000.0)),
                equity=float(DEFAULT_PARAMS.get("capital", 10_000.0)),
            )

            # Standardize columns for stats
            if "position" not in sim_df.columns and "pos" in sim_df.columns:
                sim_df["position"] = sim_df["pos"]
            if "timestamp" not in sim_df.columns and "timestamp" in df.columns:
                sim_df["timestamp"] = df["timestamp"]

            stats = compute_stats(sim_df, start_equity=float(DEFAULT_PARAMS.get("capital", 10_000.0)))

            # Compose a result row
            res_out = {
                "symbol": sym.replace("/", "-"),
                "timeframe": tf,
                "trades": int(stats.get("trades", 0)),
                "win_rate": float(stats.get("win_rate", 0.0)),
                "cagr": float(stats.get("cagr", 0.0)),
                "pf": float(stats.get("pf", 0.0)),
                "sharpe": float(stats.get("sharpe", 0.0)),
                "max_dd": float(stats.get("max_dd", 0.0)),
                "exposure": float(stats.get("exposure", 0.0)),
                "net_pnl": float(stats.get("net_pnl", 0.0)),
                "start": stats.get("start", str(df["timestamp"].iloc[0].date()) if len(df) else ""),
                "end": stats.get("end", str(df["timestamp"].iloc[-1].date()) if len(df) else ""),
            }
            results.append(res_out)
    return results

def write_csv(rows: List[Dict[str, Any]]) -> None:
    import csv
    cols = [
        "symbol","timeframe","trades","win_rate","cagr","pf","sharpe",
        "max_dd","exposure","net_pnl","start","end"
    ]
    with CSV_PATH.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: _safe(r.get(k)) for k in cols})

def write_json(rows: List[Dict[str, Any]]) -> None:
    JSON_PATH.write_text(json.dumps(rows, indent=2))

def pct(x: float) -> str:
    return f"{x*100:.1f}%" if x is not None else ""

def fmt(x: float, nd=2) -> str:
    return f"{x:.{nd}f}" if x is not None else ""

def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """
    Compute per-timeframe and overall aggregates.
    Aggregations:
      - trades: sum
      - win_rate: weighted by trades
      - cagr, sharpe, pf: average (simple)
      - max_dd: worst (max)
      - exposure: average
      - net_pnl: sum
    """
    from collections import defaultdict
    buckets = defaultdict(list)
    for r in rows:
        buckets[r["timeframe"]].append(r)
    buckets["ALL"] = rows

    agg = {}
    for key, lst in buckets.items():
        if not lst:
            continue
        trades = sum(r["trades"] for r in lst)
        w_win = sum(r["win_rate"] * r["trades"] for r in lst)
        win_rate = (w_win / trades) if trades > 0 else 0.0
        cagr = sum(r["cagr"] for r in lst) / len(lst)
        sharpe = sum(r["sharpe"] for r in lst) / len(lst)
        pf = sum(r["pf"] for r in lst) / len(lst)
        max_dd = max(r["max_dd"] for r in lst)
        exposure = sum(r["exposure"] for r in lst) / len(lst)
        net_pnl = sum(r["net_pnl"] for r in lst)
        agg[key] = {
            "trades": trades,
            "win_rate": win_rate,
            "cagr": cagr,
            "pf": pf,
            "sharpe": sharpe,
            "max_dd": max_dd,
            "exposure": exposure,
            "net_pnl": net_pnl,
        }
    return agg

def write_md(rows: List[Dict[str, Any]], agg: Dict[str, Dict[str, float]]) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = []
    lines.append(f"# Backtest Results\n\n_Run at: {ts}_\n")
    lines.append("## Aggregate (by timeframe & overall)\n")
    lines.append("| bucket | trades | win% | CAGR | PF | Sharpe | MaxDD | Exposure | Net PnL |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for bucket in ["15m","1h","4h","ALL"]:
        if bucket not in agg: 
            continue
        a = agg[bucket]
        lines.append("| {b} | {tr} | {wr} | {c} | {pf} | {sh} | {dd} | {ex} | {p} |".format(
            b=bucket,
            tr=a["trades"],
            wr=pct(a["win_rate"]),
            c=pct(a["cagr"]),
            pf=fmt(a["pf"]),
            sh=fmt(a["sharpe"]),
            dd=pct(a["max_dd"]),
            ex=pct(a["exposure"]),
            p=fmt(a["net_pnl"], 2),
        ))
    lines.append("\n## Per-symbol breakdown\n")
    lines.append("| symbol | tf | trades | win% | CAGR | PF | Sharpe | MaxDD | Exposure | Net PnL | Start | End |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|")
    for r in rows:
        lines.append("| {s} | {tf} | {tr} | {wr} | {c} | {pf} | {sh} | {dd} | {ex} | {p} | {st} | {en} |".format(
            s=r["symbol"], tf=r["timeframe"], tr=r["trades"],
            wr=pct(r["win_rate"]), c=pct(r["cagr"]),
            pf=fmt(r["pf"]), sh=fmt(r["sharpe"]),
            dd=pct(r["max_dd"]), ex=pct(r["exposure"]),
            p=fmt(r["net_pnl"], 2), st=r["start"], en=r["end"]
        ))
    MD_PATH.write_text("\n".join(lines))

def main():
    rows = run_all()
    write_csv(rows)
    write_json(rows)
    agg = aggregate(rows)
    write_md(rows, agg)
    print(f"Wrote: {CSV_PATH}")
    print(f"Wrote: {JSON_PATH}")
    print(f"Wrote: {MD_PATH}")

if __name__ == "__main__":
    main()

