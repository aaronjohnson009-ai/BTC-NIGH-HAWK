"""
Aaron's BTC Watchdog Bot (V2)
------------------------------
Runs on a schedule (via GitHub Actions). Each run:
  1. Fetches latest BTC price + recent history (CoinGecko, free, no API key)
  2. Computes trend, RSI, EMAs, support/resistance, volume, volatility
  3. Builds a Setup Quality score from how many signals agree
  4. Sends a Telegram alert if the score clears the threshold (and cooldown/mute allow it)
  5. Checks custom price alerts (/alert 120000 style)
  6. Checks for any commands you typed since the last run and replies
  7. Resolves past alerts (checks if they were actually right) for real /stats and /history
  8. Sends a once-a-day summary
  9. Saves everything back to state.json

NOTE: This runs on a schedule instead of a live server, so command replies
are delayed by however often the schedule runs (see workflow file) - not instant.

IMPORTANT: This bot describes what the data shows. It does not give financial
advice, entry/exit instructions, or trade recommendations. Every decision
about your money is yours - the bot is just a faster way to see the numbers.
"""

import os
import json
import math
import requests
from datetime import datetime, timezone, timedelta

# ---------- CONFIG (safe to tweak) ----------
COIN_ID = "bitcoin"
VS_CURRENCY = "usd"
STATE_FILE = "state.json"

MIN_SETUP_SCORE_TO_ALERT = 60      # 0-100. Higher = fewer, stronger alerts
ALERT_COOLDOWN_MINUTES = 60        # don't re-alert on the same direction within this window
RSI_PERIOD = 14
EMA_PERIODS = [20, 50, 200]
LOOKBACK_DAYS = 30                 # history window used for support/resistance + EMAs

OUTCOME_CHECK_HOURS = 4            # how long to wait before scoring an alert right/wrong
OUTCOME_MOVE_THRESHOLD = 0.3       # % move needed in predicted direction to count as "correct"

DAILY_SUMMARY_HOUR_UTC = 16        # ~9am Pacific - adjust if you want it earlier/later

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ---------- STATE (persisted between runs via git commit) ----------
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"WARNING: couldn't read state.json ({e}), starting fresh")
            state = {}
    else:
        state = {}

    state.setdefault("last_update_id", 0)
    state.setdefault("price_history", [])
    state.setdefault("alerts", [])
    state.setdefault("last_alert_direction", None)
    state.setdefault("last_alert_time", None)
    state.setdefault("muted", False)
    state.setdefault("price_targets", [])       # [{"price": 120000, "created": iso, "hit": False}]
    state.setdefault("last_daily_summary_date", None)  # "YYYY-MM-DD"
    return state


def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except OSError as e:
        print(f"ERROR: couldn't save state.json: {e}")


# ---------- DATA FETCH ----------
def fetch_market_data():
    """Get recent hourly prices + volumes from CoinGecko (free, no key needed).
    Returns (prices, volumes) or (None, None) if the fetch fails."""
    url = f"https://api.coingecko.com/api/v3/coins/{COIN_ID}/market_chart"
    params = {"vs_currency": VS_CURRENCY, "days": LOOKBACK_DAYS, "interval": "hourly"}
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        prices = [p[1] for p in data["prices"]]
        volumes = [v[1] for v in data["total_volumes"]]
        return prices, volumes
    except (requests.RequestException, KeyError, ValueError) as e:
        print(f"ERROR: market data fetch failed: {e}")
        return None, None


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


def confidence_tier(score):
    if score >= 90:
        return "🚨 Exceptional"
    elif score >= 80:
        return "🔥 Very Strong"
    elif score >= 70:
        return "🟠 Strong"
    elif score >= 60:
        return "🟡 Decent"
    else:
        return "⚪ Weak"


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
        "bull_votes": bullish_votes,
        "bear_votes": bearish_votes,
    }


# ---------- TELEGRAM ----------
def send_message(text):
    if not CHAT_ID:
        print("No CHAT_ID set yet - skipping send.")
        return
    try:
        requests.post(f"{TELEGRAM_API}/sendMessage", data={
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"
        }, timeout=15)
    except requests.RequestException as e:
        print(f"ERROR: failed to send Telegram message: {e}")


def get_updates(offset):
    try:
        r = requests.get(f"{TELEGRAM_API}/getUpdates", params={"offset": offset, "timeout": 0}, timeout=15)
        r.raise_for_status()
        return r.json().get("result", [])
    except (requests.RequestException, ValueError) as e:
        print(f"ERROR: failed to get Telegram updates: {e}")
        return []


# ---------- MESSAGE FORMATTING ----------
DISCLAIMER = "<i>This reflects what the data shows right now, not a recommendation. Markets can reverse fast - your call, your risk.</i>"


def simple_label(direction, score):
    if direction == "SIDEWAYS" or score < MIN_SETUP_SCORE_TO_ALERT:
        return "🟡 NO CLEAR SETUP"
    elif direction == "BULLISH":
        return "🟢 BULLISH LEANING"
    else:
        return "🔴 BEARISH LEANING"


def format_alert(a):
    label = simple_label(a["direction"], a["score"])
    tier = confidence_tier(a["score"])
    reasons_text = "\n".join(f"• {r}" for r in a["reasons"])
    return (
        f"{label}\n"
        f"Confidence: {tier} ({a['score']}/100)\n\n"
        f"BTC: ${a['price']:,.0f}\n\n"
        f"WHY?\n{reasons_text}\n\n"
        f"📍 Reference levels\n"
        f"Resistance: ${a['resistance']:,.0f}\n"
        f"Support: ${a['support']:,.0f}\n\n"
        f"{DISCLAIMER}"
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
        f"Resistance (ceiling): ${a['resistance']:,.0f}\n\n"
        f"{DISCLAIMER}"
    )


def format_why(a):
    lines = [f"🧠 Why the current score is {a['score']}/100:\n"]
    if a["reasons"]:
        for r in a["reasons"]:
            lines.append(f"• {r}")
    else:
        lines.append("• No strong signals agreeing right now")
    lines.append(f"\nBull signals: {a['bull_votes']} | Bear signals: {a['bear_votes']}")
    return "\n".join(lines)


def format_stats(state):
    alerts = state.get("alerts", [])
    resolved = [x for x in alerts if x.get("resolved")]
    if not resolved:
        pending = len(alerts) - len(resolved)
        return f"📈 No resolved alerts yet.\nPending (still tracking): {pending}\n\nCheck back after a few alerts have had time to play out ({OUTCOME_CHECK_HOURS}h each)."
    correct = [x for x in resolved if x.get("correct")]
    win_rate = len(correct) / len(resolved) * 100
    return (
        f"📈 ALERT PERFORMANCE\n\n"
        f"Resolved alerts: {len(resolved)}\n"
        f"Correct direction: {len(correct)}\n"
        f"Win rate: {win_rate:.0f}%\n\n"
        f"<i>Based on whether price moved {OUTCOME_MOVE_THRESHOLD}%+ in the predicted direction within {OUTCOME_CHECK_HOURS}h.</i>"
    )


def format_history(state):
    alerts = state.get("alerts", [])[-10:]
    if not alerts:
        return "No alerts logged yet."
    lines = ["📜 LAST ALERTS\n"]
    for x in reversed(alerts):
        dirn = "LONG" if x["direction"] == "BULLISH" else "SHORT"
        if x.get("resolved"):
            outcome = "✅" if x.get("correct") else "❌"
            move = x.get("outcome_move_pct")
            move_text = f"{move:+.1f}%" if move is not None else "?"
            lines.append(f"{outcome} {dirn} {x['score']} @ ${x['price']:,.0f} → {move_text}")
        else:
            lines.append(f"⏳ {dirn} {x['score']} @ ${x['price']:,.0f} (tracking...)")
    return "\n".join(lines)


HELP_TEXT = (
    "🤖 BTC Watchdog Commands\n\n"
    "/price - current BTC price\n"
    "/trend - up, down, or sideways\n"
    "/analysis - full simple breakdown\n"
    "/levels - support & resistance\n"
    "/volume - trading activity vs normal\n"
    "/volatility - calm/normal/active/crazy\n"
    "/why - what's driving the current score\n"
    "/stats - how past alerts performed\n"
    "/history - last 10 alerts + outcomes\n"
    "/alert 120000 - ping me when BTC crosses this price\n"
    "/mute - pause alerts\n"
    "/unmute - resume alerts\n"
    "/help - this list\n\n"
    "Replies can take a few minutes since I check for your messages on a schedule, not instantly.\n"
    "Nothing here is financial advice - it's a faster way to see the data. Your calls are yours."
)


# ---------- OUTCOME TRACKING ----------
def resolve_past_alerts(state, current_price, now):
    """Check alerts old enough to have a verdict, mark them correct/incorrect."""
    for alert in state.get("alerts", []):
        if alert.get("resolved"):
            continue
        try:
            alert_time = datetime.fromisoformat(alert["time"])
        except (KeyError, ValueError):
            continue
        hours_since = (now - alert_time).total_seconds() / 3600
        if hours_since < OUTCOME_CHECK_HOURS:
            continue
        entry_price = alert["price"]
        move_pct = (current_price - entry_price) / entry_price * 100
        if alert["direction"] == "BULLISH":
            correct = move_pct >= OUTCOME_MOVE_THRESHOLD
        else:
            correct = move_pct <= -OUTCOME_MOVE_THRESHOLD
        alert["resolved"] = True
        alert["correct"] = correct
        alert["outcome_move_pct"] = move_pct


# ---------- CUSTOM PRICE TARGETS ----------
def check_price_targets(state, prices, current_price):
    """Check /alert targets - fires once when price crosses, in either direction."""
    if len(prices) < 2:
        return
    prev_price = prices[-2]
    for target in state.get("price_targets", []):
        if target.get("hit"):
            continue
        price_val = target["price"]
        crossed = (prev_price < price_val <= current_price) or (prev_price > price_val >= current_price)
        if crossed:
            send_message(f"🎯 Price alert! BTC crossed ${price_val:,.0f}\nCurrent: ${current_price:,.0f}")
            target["hit"] = True


# ---------- DAILY SUMMARY ----------
def maybe_send_daily_summary(state, prices, now):
    today_str = now.strftime("%Y-%m-%d")
    if state.get("last_daily_summary_date") == today_str:
        return
    if now.hour < DAILY_SUMMARY_HOUR_UTC:
        return

    todays_points = [
        p for p in state.get("price_history", [])
        if p["time"].startswith(today_str)
    ]
    if todays_points:
        today_prices = [p["price"] for p in todays_points]
        day_high = max(today_prices)
        day_low = min(today_prices)
        day_open = today_prices[0]
        day_now = today_prices[-1]
        change_pct = (day_now - day_open) / day_open * 100
        range_text = (
            f"Open: ${day_open:,.0f}\n"
            f"High: ${day_high:,.0f}\n"
            f"Low: ${day_low:,.0f}\n"
            f"Now: ${day_now:,.0f} ({change_pct:+.1f}%)"
        )
    else:
        range_text = f"Now: ${prices[-1]:,.0f}"

    todays_alerts = [
        a for a in state.get("alerts", [])
        if a["time"].startswith(today_str)
    ]
    resolved_today = [a for a in todays_alerts if a.get("resolved")]
    correct_today = [a for a in resolved_today if a.get("correct")]
    if resolved_today:
        perf_text = f"{len(correct_today)}/{len(resolved_today)} correct so far"
    else:
        perf_text = "none resolved yet"

    msg = (
        f"📅 DAILY SUMMARY\n\n"
        f"{range_text}\n\n"
        f"Alerts sent today: {len(todays_alerts)}\n"
        f"Performance: {perf_text}\n\n"
        f"{DISCLAIMER}"
    )
    send_message(msg)
    state["last_daily_summary_date"] = today_str


# ---------- MAIN ----------
def main():
    if not BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN not set")

    state = load_state()
    prices, volumes = fetch_market_data()

    if prices is None:
        print("Market data unavailable this run - skipping analysis, will retry next run.")
        save_state(state)
        return

    a = analyze(prices, volumes)
    now = datetime.now(timezone.utc)

    # 1. Handle any commands sent since last run
    updates = get_updates(state["last_update_id"] + 1)
    for u in updates:
        state["last_update_id"] = u["update_id"]
        msg = u.get("message", {})
        text = msg.get("text", "") or ""
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
        elif text.startswith("/why"):
            send_message(format_why(a))
        elif text.startswith("/stats"):
            send_message(format_stats(state))
        elif text.startswith("/history"):
            send_message(format_history(state))
        elif text.startswith("/mute"):
            state["muted"] = True
            send_message("🔕 Alerts muted. Send /unmute to turn them back on. Commands still work.")
        elif text.startswith("/unmute"):
            state["muted"] = False
            send_message("🔔 Alerts unmuted.")
        elif text.startswith("/alert"):
            parts = text.split()
            if len(parts) >= 2:
                try:
                    target_price = float(parts[1].replace(",", "").replace("$", ""))
                    state["price_targets"].append({
                        "price": target_price,
                        "created": now.isoformat(),
                        "hit": False,
                    })
                    send_message(f"🎯 I'll ping you when BTC crosses ${target_price:,.0f}")
                except ValueError:
                    send_message("Couldn't read that price. Try: /alert 120000")
            else:
                send_message("Usage: /alert 120000")
        elif text.startswith("/help") or text.startswith("/start"):
            send_message(HELP_TEXT)

    # 2. Check custom price targets
    check_price_targets(state, prices, a["price"])

    # 3. Resolve past alerts (outcome tracking)
    resolve_past_alerts(state, a["price"], now)

    # 4. Check whether to send a new setup alert
    cooldown_ok = True
    if state.get("last_alert_time"):
        last_time = datetime.fromisoformat(state["last_alert_time"])
        minutes_since = (now - last_time).total_seconds() / 60
        if minutes_since < ALERT_COOLDOWN_MINUTES and state.get("last_alert_direction") == a["direction"]:
            cooldown_ok = False

    if (a["score"] >= MIN_SETUP_SCORE_TO_ALERT and a["direction"] != "SIDEWAYS"
            and cooldown_ok and not state.get("muted")):
        send_message(format_alert(a))
        state["last_alert_direction"] = a["direction"]
        state["last_alert_time"] = now.isoformat()
        state["alerts"].append({
            "time": now.isoformat(),
            "price": a["price"],
            "direction": a["direction"],
            "score": a["score"],
            "reasons": a["reasons"],
            "resolved": False,
        })

    # 5. Save price point + trim history
    state["price_history"].append({"time": now.isoformat(), "price": a["price"]})
    state["price_history"] = state["price_history"][-2000:]
    state["alerts"] = state["alerts"][-500:]

    # 6. Daily summary (checked last so it has today's freshly-added price point)
    maybe_send_daily_summary(state, prices, now)

    save_state(state)

    print(f"Run complete. Price=${a['price']:,.0f} Direction={a['direction']} Score={a['score']} Muted={state.get('muted')}")


if __name__ == "__main__":
    main()
