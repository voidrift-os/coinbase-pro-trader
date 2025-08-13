from scripts.tradingview_gateway import build_args


def test_build_args_symbol_normalization() -> None:
    args = build_args({"symbol": "ethusd", "timeframe": "5m", "limit": 300, "max": 20})
    # Should normalize symbol to ETHUSD/USD and cap max to 10
    assert "ETHUSD/USD" in args
    assert args[-1] == "10"


def test_build_args_tf_fallback_and_limit_cap() -> None:
    args = build_args({"symbol": "BTC-USD", "timeframe": "2h", "limit": 5000, "max": 1})
    # TF not in safe set should fallback to 1h; limit capped to 2000
    # args structure: [..., "--timeframe", tf, "--limit", limit, "--max", max]
    tf_index = args.index("--timeframe") + 1
    limit_index = args.index("--limit") + 1
    assert args[tf_index] == "1h"
    assert args[limit_index] == "2000"
