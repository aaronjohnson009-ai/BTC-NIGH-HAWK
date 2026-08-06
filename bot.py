"""
Aaron's BTC Watchdog Bot
------------------------
Runs on a schedule (via GitHub Actions). Each run:
  1. Fetches latest BTC price + recent history (CoinGecko, free, no API key)
  2. Computes trend, RSI, EMAs, support/resistance, volume, volatility
  3. Builds a Setup Quality score from how many signals agree
  4. Sends a Telegram alert if the score clears the threshold (and cooldown allows it)
  5. Checks for any commands you typed (e.g. /price) since the last run and replies
  6. Saves everything (price history, alert log, outcome tracking) back to state.json

NOTE: Because this runs on a schedule instead of a live server, command replies
are delayed by however often the schedule runs (see workflow file) - not instant.
"""

import os
import json
import time
import math
import requests
from datetime import datetime, timezone

# ---------- CONFIG (safe to tweak) ----------
COIN_ID = "bitcoin"
VS_CURRENCY = "usd"
STATE_FILE = "state.json"

MIN_SETUP_SCORE_TO_ALERT = 60      # 0-100. Higher = fewer, stronger alerts
ALERT_COOLDOWN_MINUTES = 60        # don't re-alert on the same direction within this window
RSI_PERIOD = 14
EMA_PERIODS = [20, 50, 200]
LOOKBACK_DAYS = 30                 # history window used for support/resistance + EMAs

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")  # set after first message, see get_chat_id.py

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ---------- STATE (persisted between runs via git commit) ----------
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "last_update_id": 0,
        "price_history": [],       # list of {time, price}
        "alerts": [],              # logged alerts for accuracy tracking
        "last_alert_direction": None,
        "last_alert_time": None,
    }


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ---------- DATA FETCH ----------
def fetch_market_data():
    """Get recent hourly prices + volumes from CoinGecko (free, no key needed)."""
    url = f"https://api.coingecko.com/api/v3/coins/{COIN_ID}/market_chart"
    params = {"vs_currency": VS_CURRENCY, "days": LOOKBACK_DAYS, "interval": "hourly"}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    prices = [p[1] for p in data["prices"]]
    volumes = [v[1] for v in data["total_volumes"]]
    return prices, volumes


# ---------- INDICATORS (plain math, no extra libraries needed) ----------
def ema(values, period):
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e


def rsi(values, period=14):
    if len(values) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        gain = max(change, 0)
        loss = max(-change, 0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def support_resistance(values):
    recent = values[-24 * 7:]  # last ~7 days of hourly data
    return min(recent), max(recent)


def volatility_label(values):
    recent = values[-24:]
    if len(recent) < 2:
        return "NORMAL", "🟢"
    pct_changes = [abs((recent[i] - recent[i - 1]) / recent[i - 1]) for i in range(1, len(recent))]
    avg_move = sum(pct_changes) / len(pct_changes) * 100
    if avg_move < 0.15:
        return "CALM", "😴"
    elif avg_move < 0.4:
        return "NORMAL", "🟢"
    elif avg_move < 0.8:
        return "ACTIVE", "⚠️"
    else:
        return "CRAZY", "🔥"


def volume_spike(volumes):
    if len(volumes) < 25:
        return 1.0
    current = volumes[-1]
    avg = sum(volumes[-25:-1]) / 24
    if avg == 0:
        return 1.0
    return current / avg


# ---------- ANALYSIS ----------
def analyze(prices, volumes):
    current_price = prices[-1]
    ema20 = ema(prices, 20)
    ema50 = ema(prices, 50)
    ema200 = ema(prices, min(200, len(prices) - 1)) if len(prices) > 20 else None
    rsi_val = rsi(prices, RSI_PERIOD)
    support, resistance = support_resistance(prices)
    vol_state, vol_emoji = volatility_label(prices)
    vspike = volume_spike(volumes)

    # --- trend ---
    if ema20 and ema50:
        if ema20 > ema50 * 1.001:
            trend = "UP"
        elif ema20 < ema50 * 0.999:
            trend = "DOWN"
        else:
            trend = "SIDEWAYS"
    else:
        trend = "SIDEWAYS"

    # --- signal votes (each True/False signal that agrees = evidence) ---
    bullish_votes = 0
    bearish_votes = 0
    reasons_bull, reasons_bear = [], []

    if trend == "UP":
        bullish_votes += 1
        reasons_bull.append("Short-term trend is up (20 vs 50 average)")
    elif trend == "DOWN":
        bearish_votes += 1
        reasons_bear.append("Short-term trend is down (20 vs 50 average)")

    if ema200:
        if current_price > ema200:
            bullish_votes += 1
            reasons_bull.append("Price is above its longer-term average")
        else:
            bearish_votes += 1
            reasons_bear.append("Price is below its longer-term average")

    if rsi_val is not None:
        if rsi_val < 35:
            bullish_votes += 1
            reasons_bull.append(f"RSI ({rsi_val:.0f}) suggests it may be oversold (due for a bounce)")
        elif rsi_val > 65:
            bearish_votes += 1
            reasons_bear.append(f"RSI ({rsi_val:.0f}) suggests it may be overbought (due for a pullback)")

    if current_price <= support * 1.01:
        bullish_votes += 1
        reasons_bull.append(f"Price is near a support floor (${support:,.0f})")
    if current_price >= resistance * 0.99:
        bearish_votes += 1
        reasons_bear.append(f"Price is near a resistance ceiling (${resistance:,.0f})")

    if vspike > 1.5:
        # volume spike supports whichever direction price is currently moving
        recent_change = (prices[-1] - prices[-6]) / prices[-6] if len(prices) > 6 else 0
        note = f"Trading activity is about {vspike:.1f}x higher than normal"
        if recent_change > 0:
            bullish_votes += 1
            reasons_bull.append(note)
        elif recent_change < 0:
            bearish_votes += 1
            reasons_bear.append(note)

    total_votes = bullish_votes + bearish_votes
    if total_votes == 0:
        direction, score, reasons = "SIDEWAYS", 0, []
    elif bullish_votes >= bearish_votes:
        direction = "BULLISH"
        score = round((bullish_votes / max(total_votes, 1)) * 100 * min(total_votes / 4, 1))
        reasons = reasons_bull
    else:
        direction = "BEARISH"
        score = round((bearish_votes / max(total_votes, 1)) * 100 * min(total_votes / 4, 1))
        reasons = reasons_bear

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
        "direction": direction,
        "score": score,
        "reasons": reasons,
    }


# ---------- TELEGRAM ----------
def send_message(text):
    if not CHAT_ID:
        print("No CHAT_ID set yet - skipping send. See get_chat_id.py")
        return
    requests.post(f"{TELEGRAM_API}/sendMessage", data={
        "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"
    }, timeout=15)


def get_updates(offset):
    r = requests.get(f"{TELEGRAM_API}/getUpdates", params={"offset": offset, "timeout": 0}, timeout=15)
    r.raise_for_status()
    return r.json().get("result", [])


# ---------- MESSAGE FORMATTING ----------
def format_alert(a):
    emoji = "🟢" if a["direction"] == "BULLISH" else "🔴"
    priority = "🔴 MAJOR ALERT" if a["score"] >= 80 else "🟠 IMPORTANT ALERT"
    reasons_text = "\n".join(f"• {r}" for r in a["reasons"])
    return (
        f"{priority}\n\n"
        f"BTC: ${a['price']:,.0f}\n\n"
        f"{emoji} {'Looking bullish (leaning up)' if a['direction']=='BULLISH' else 'Looking bearish (leaning down)'}\n"
        f"Setup Quality: {a['score']}/100\n\n"
        f"WHY?\n{reasons_text}\n\n"
        f"🎯 Next level to watch: ${a['resistance']:,.0f}\n"
        f"❌ Idea weakens below: ${a['support']:,.0f}\n\n"
        f"<i>Score = how much evidence agrees, not a guaranteed outcome.</i>"
    )


def format_analysis(a):
    trend_emoji = {"UP": "🟢 Going up", "DOWN": "🔴 Going down", "SIDEWAYS": "🟡 Sideways"}[a["trend"]]
    rsi_text = f"{a['rsi']:.0f}" if a["rsi"] is not None else "N/A"
    return (
        f"📊 BTC ANALYSIS\n\n"
        f"Price: ${a['price']:,.0f}\n"
        f"Trend: {trend_emoji}\n"
        f"Volatility: {a['volatility_emoji']} {a['volatility']}\n"
        f"Trading activity: {a['volume_spike']:.1f}x normal\n"
        f"RSI: {rsi_text}\n\n"
        f"Support (floor): ${a['support']:,.0f}\n"
        f"Resistance (ceiling): ${a['resistance']:,.0f}"
    )


HELP_TEXT = (
    "🤖 BTC Watchdog Commands\n\n"
    "/price - current BTC price\n"
    "/trend - up, down, or sideways\n"
    "/analysis - full simple breakdown\n"
    "/levels - support & resistance\n"
    "/volume - trading activity vs normal\n"
    "/volatility - calm/normal/active/crazy\n"
    "/stats - how past alerts performed\n"
    "/help - this list\n\n"
    "Note: replies can take a few minutes since I check for your messages on a schedule, not instantly."
)


# ---------- MAIN ----------
def main():
    if not BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN not set")

    state = load_state()
    prices, volumes = fetch_market_data()
    a = analyze(prices, volumes)

    # 1. Handle any commands sent since last run
    updates = get_updates(state["last_update_id"] + 1)
    for u in updates:
        state["last_update_id"] = u["update_id"]
        msg = u.get("message", {})
        text = msg.get("text", "")
        chat_id = msg.get("chat", {}).get("id")
        if chat_id and not CHAT_ID:
            print(f"First message seen. Your chat_id is: {chat_id}")
        if text.startswith("/price"):
            send_message(f"💰 BTC: ${a['price']:,.0f}")
        elif text.startswith("/trend"):
            send_message(f"Trend: {a['trend']}")
        elif text.startswith("/analysis"):
            send_message(format_analysis(a))
        elif text.startswith("/levels"):
            send_message(f"Support: ${a['support']:,.0f}\nResistance: ${a['resistance']:,.0f}")
        elif text.startswith("/volume"):
            send_message(f"Trading activity is {a['volume_spike']:.1f}x normal")
        elif text.startswith("/volatility"):
            send_message(f"{a['volatility_emoji']} {a['volatility']}")
        elif text.startswith("/stats"):
            alerts = state.get("alerts", [])
            if not alerts:
                send_message("No alerts logged yet - stats will show up once some have run their course.")
            else:
                send_message(f"Logged alerts so far: {len(alerts)}\n(Full accuracy stats coming once outcomes are tracked)")
        elif text.startswith("/help") or text.startswith("/start"):
            send_message(HELP_TEXT)

    # 2. Check whether to send a new alert
    now = datetime.now(timezone.utc)
    cooldown_ok = True
    if state.get("last_alert_time"):
        last_time = datetime.fromisoformat(state["last_alert_time"])
        minutes_since = (now - last_time).total_seconds() / 60
        if minutes_since < ALERT_COOLDOWN_MINUTES and state.get("last_alert_direction") == a["direction"]:
            cooldown_ok = False

    if a["score"] >= MIN_SETUP_SCORE_TO_ALERT and a["direction"] != "SIDEWAYS" and cooldown_ok:
        send_message(format_alert(a))
        state["last_alert_direction"] = a["direction"]
        state["last_alert_time"] = now.isoformat()
        state["alerts"].append({
            "time": now.isoformat(),
            "price": a["price"],
            "direction": a["direction"],
            "score": a["score"],
            "reasons": a["reasons"],
        })

    # 3. Save price point + trim history + persist state
    state["price_history"].append({"time": now.isoformat(), "price": a["price"]})
    state["price_history"] = state["price_history"][-2000:]  # keep file size sane
    state["alerts"] = state["alerts"][-500:]
    save_state(state)

    print(f"Run complete. Price=${a['price']:,.0f} Direction={a['direction']} Score={a['score']}")


if __name__ == "__main__":
    main()
