"""
indicators.py — Technical Indicators

Pure math functions, each focused on a single indicator. Nothing here talks
to the network or Telegram — just numbers in, numbers out. That makes each
one easy to test and easy to extend later (e.g. add more periods to
config.EMA_PERIODS).
"""

from typing import Optional

import config


def rsi(prices: list[float], period: int = None) -> Optional[float]:
    period = period or config.RSI_PERIOD
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        change = prices[-i] - prices[-i - 1]
        (gains if change > 0 else losses).append(abs(change))
    avg_gain = sum(gains) / period if gains else 0.0001
    avg_loss = sum(losses) / period if losses else 0.0001
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def ema(prices: list[float], period: int) -> Optional[float]:
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    e = sum(prices[:period]) / period
    for p in prices[period:]:
        e = p * k + e * (1 - k)
    return e


def moving_average(prices: list[float], period: int) -> Optional[float]:
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def support_resistance(prices: list[float]):
    recent = prices[-config.SUPPORT_RESISTANCE_LOOKBACK_HOURS:]
    if not recent:
        return None, None
    return min(recent), max(recent)


def volatility_label(prices: list[float]):
    recent = prices[-24:]
    if len(recent) < 2:
        return "NORMAL", "🟢"
    pct_changes = [
        abs((recent[i] - recent[i - 1]) / recent[i - 1])
        for i in range(1, len(recent)) if recent[i - 1] != 0
    ]
    if not pct_changes:
        return "NORMAL", "🟢"
    avg_move = sum(pct_changes) / len(pct_changes) * 100
    if avg_move < 0.15:
        return "CALM", "😴"
    elif avg_move < 0.4:
        return "NORMAL", "🟢"
    elif avg_move < 0.8:
        return "ACTIVE", "⚠️"
    return "CRAZY", "🔥"


def volume_spike(volumes: list[float]) -> float:
    if len(volumes) < 25:
        return 1.0
    current = volumes[-1]
    avg = sum(volumes[-25:-1]) / 24
    if avg == 0:
        return 1.0
    return current / avg
