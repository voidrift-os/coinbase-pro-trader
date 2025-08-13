#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from typing import Any, Dict, List

SAFE_TIMEFRAMES = {"1m", "5m", "15m", "1h"}


def _tv_symbol_to_cli(sym: str) -> str:
    # Accept formats like BTCUSD, BTC-USD, BTC/USD; normalize to BTC/USD
    s = sym.strip().upper().replace("-", "/")
    if "/" not in s:
        # assume USD quote if not provided
        s = f"{s}/USD"
    return s


def build_args(alert: Dict[str, Any]) -> List[str]:
    # Extract basic fields with safe defaults
    sym = alert.get("symbol") or alert.get("SYMBOL") or "BTCUSD"
    tf = str(alert.get("timeframe") or alert.get("TF") or "1h").lower()
    limit = int(alert.get("limit") or alert.get("LIMIT") or 200)
    max_iters = int(alert.get("max") or alert.get("MAX") or 5)

    cli_symbol = _tv_symbol_to_cli(str(sym))
    if tf not in SAFE_TIMEFRAMES:
        tf = "1h"
    # Hard cap to prevent long loops
    if max_iters > 10:
        max_iters = 10
    if limit > 2000:
        limit = 2000

    # Compose the CLI invocation to the existing dry-run live loop
    return [
        sys.executable,
        "-m",
        "pro_coinbase_bot",
        "live",
        cli_symbol,
        "--timeframe",
        tf,
        "--limit",
        str(limit),
        "--max",
        str(max_iters),
    ]


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="TradingView alert gateway: routes alerts to a safe, controlled CLI run (no direct orders)"
    )
    p.add_argument("--alert-json", help="Alert payload as JSON string (if omitted, read stdin)")
    args = p.parse_args(argv)

    raw = args.alert_json
    if not raw:
        raw = sys.stdin.read()
    try:
        alert = json.loads(raw)
    except Exception as e:
        print(f"Invalid JSON payload: {e}", file=sys.stderr)
        return 2

    cmd = build_args(alert)
    print("Running:", shlex.join(cmd))
    try:
        res = subprocess.run(cmd, check=False)
        return int(res.returncode)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

