"""
signal_engine.py — Combines indicator readings into bullish/bearish evidence

Each indicator "votes" bullish, bearish, or stays silent, along with the
plain-English reason behind that vote. Collecting these together is what
lets the scoring engine (and eventually the user, via "Why?") see exactly
why the system leans the way it does — not just a black-box number.
"""

import indicators


def build_snapshot(prices: list[float], volumes: list[float]) -> dict:
    current_price = prices[-1]
    ema20 = indicators.ema(prices, 20)
    ema50 = indicators.ema(prices, 50)
    ema200 = indicators.ema(prices, min(200, len(prices) - 1)) if len(prices) > 20 else None
    rsi_val = indicators.rsi(prices)
    support, resistance = indicators.support_resistance(prices)
    vol_state, vol_emoji = indicators.volatility_label(prices)
    vspike = indicators.volume_spike(volumes)

    if ema20 and ema50:
        if ema20 > ema50 * 1.001:
            trend = "UP"
        elif ema20 < ema50 * 0.999:
            trend = "DOWN"
        else:
            trend = "SIDEWAYS"
    else:
        trend = "SIDEWAYS"

    bullish, bearish = [], []

    if trend == "UP":
        bullish.append("Short-term trend is up (20-hour average above 50-hour average)")
    elif trend == "DOWN":
        bearish.append("Short-term trend is down (20-hour average below 50-hour average)")

    if ema200 is not None:
        if current_price > ema200:
            bullish.append("Price is above its longer-term (200-hour) average")
        else:
            bearish.append("Price is below its longer-term (200-hour) average")

    if rsi_val is not None:
        if rsi_val < 35:
            bullish.append(f"RSI ({rsi_val:.0f}) suggests it may be oversold (due for a bounce)")
        elif rsi_val > 65:
            bearish.append(f"RSI ({rsi_val:.0f}) suggests it may be overbought (due for a pullback)")

    if support is not None and current_price <= support * 1.01:
        bullish.append(f"Price is near a support floor (${support:,.0f})")
    if resistance is not None and current_price >= resistance * 0.99:
        bearish.append(f"Price is near a resistance ceiling (${resistance:,.0f})")

    if vspike > 1.5:
        recent_change = (
            (prices[-1] - prices[-6]) / prices[-6]
            if len(prices) > 6 and prices[-6] != 0 else 0
        )
        note = f"Trading activity is about {vspike:.1f}x higher than normal"
        if recent_change > 0:
            bullish.append(note)
        elif recent_change < 0:
            bearish.append(note)

    return {
        "price": current_price,
        "trend": trend,
        "rsi": rsi_val,
        "ema20": ema20,
        "ema50": ema50,
        "ema200": ema200,
        "support": support,
        "resistance": resistance,
        "volatility": vol_state,
        "volatility_emoji": vol_emoji,
        "volume_spike": vspike,
        "bullish_reasons": bullish,
        "bearish_reasons": bearish,
    }
