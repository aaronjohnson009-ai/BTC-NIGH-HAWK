"""
regime_engine.py — Market Regime Detection

Labels the overall market condition using measurable rules — trend
strength across timeframes plus current volatility — not a guess. This is
descriptive context for the user and other engines, not a trading signal
by itself.
"""

import config
import multi_timeframe

REGIME_EXPLANATIONS = {
    "Strong Bull": "Bitcoin has been trending up strongly across multiple timeframes.",
    "Weak Bull": "Bitcoin is leaning upward, but the trend isn't strong or fully agreed on.",
    "Sideways": "Bitcoin is moving up and down within a relatively limited range instead of trending. Trend-following strategies often have a harder time here.",
    "Weak Bear": "Bitcoin is leaning downward, but the trend isn't strong or fully agreed on.",
    "Strong Bear": "Bitcoin has been trending down strongly across multiple timeframes.",
    "High Volatility": "Price is swinging aggressively right now, regardless of direction.",
    "Unknown": "Not enough data yet to confidently label the current market regime.",
}


def detect(prices: list[float], volatility_label: str) -> dict:
    if len(prices) < 30:
        return {
            "regime": "Unknown", "explanation": REGIME_EXPLANATIONS["Unknown"],
            "higher_change_pct": 0.0, "timeframes": {}, "agreement": "insufficient data",
        }

    tf = multi_timeframe.analyze(prices)

    higher_hours = min(config.TIMEFRAME_HIGHER_HOURS, len(prices) - 1)
    base_price = prices[-1 - higher_hours] if higher_hours > 0 else prices[0]
    higher_change_pct = ((prices[-1] - base_price) / base_price * 100) if base_price else 0.0

    if volatility_label == "CRAZY":
        regime = "High Volatility"
    elif higher_change_pct >= config.REGIME_TREND_STRONG_PCT and tf["bullish_count"] >= 2:
        regime = "Strong Bull"
    elif higher_change_pct > 0 and tf["bullish_count"] >= 2:
        regime = "Weak Bull"
    elif higher_change_pct <= -config.REGIME_TREND_STRONG_PCT and tf["bearish_count"] >= 2:
        regime = "Strong Bear"
    elif higher_change_pct < 0 and tf["bearish_count"] >= 2:
        regime = "Weak Bear"
    else:
        regime = "Sideways"

    return {
        "regime": regime,
        "explanation": REGIME_EXPLANATIONS[regime],
        "higher_change_pct": round(higher_change_pct, 2),
        "timeframes": tf["timeframes"],
        "agreement": tf["agreement"],
    }
