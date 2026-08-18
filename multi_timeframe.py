"""
multi_timeframe.py — Multi-Timeframe Analysis

Looks at the same price data through three different windows — short,
intermediate, and higher — so no single narrow slice of time gets treated
as if it represents the whole market. Built entirely from the hourly price
history the bot already fetches each run; no extra data source needed.
"""

import config


def _trend_label(prices: list[float]) -> str:
    if len(prices) < 5 or not prices[0]:
        return "UNKNOWN"
    change_pct = (prices[-1] - prices[0]) / prices[0] * 100
    if change_pct > 1.0:
        return "BULLISH"
    if change_pct < -1.0:
        return "BEARISH"
    return "NEUTRAL"


def analyze(prices: list[float]) -> dict:
    short = prices[-config.TIMEFRAME_SHORT_HOURS:]
    intermediate = prices[-config.TIMEFRAME_INTERMEDIATE_HOURS:]
    higher = prices[-config.TIMEFRAME_HIGHER_HOURS:]

    timeframes = {
        "short": _trend_label(short),
        "intermediate": _trend_label(intermediate),
        "higher": _trend_label(higher),
    }

    bullish_count = sum(1 for v in timeframes.values() if v == "BULLISH")
    bearish_count = sum(1 for v in timeframes.values() if v == "BEARISH")
    total = len(timeframes)

    if bullish_count > bearish_count:
        agreement = f"{bullish_count} of {total} bullish"
    elif bearish_count > bullish_count:
        agreement = f"{bearish_count} of {total} bearish"
    else:
        agreement = "mixed / no clear agreement"

    return {
        "timeframes": timeframes,
        "agreement": agreement,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "total": total,
    }
