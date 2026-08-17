"""
telegram_bot.py — Telegram Send/Receive + Message Formatting

Handles all Telegram I/O and message formatting in one place, so the rest
of the system never has to know about Telegram's API shape.
"""

import requests

import config
import learn

TELEGRAM_API = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"

ACTION_LABELS = {
    "LONG_ENTRY": "🟢 LONG ENTRY",
    "SHORT_ENTRY": "🔴 SHORT ENTRY",
    "WAIT": "🟡 WAIT",
    "HOLD_LONG": "🟢 HOLD LONG",
    "WATCH_LONG": "🟡 WATCH LONG",
    "EXIT_LONG": "🔴 EXIT LONG",
    "HOLD_SHORT": "🔴 HOLD SHORT",
    "WATCH_SHORT": "🟡 WATCH SHORT",
    "EXIT_SHORT": "🟢 EXIT SHORT",
}

ACTION_SIMPLE = {
    "LONG_ENTRY": "The system currently sees stronger evidence for upward price movement than downward movement.",
    "SHORT_ENTRY": "The system currently sees stronger evidence for downward price movement. This means a short position, not selling BTC you already own.",
    "WAIT": "The system doesn't currently see a strong enough setup in either direction. Doing nothing is a valid result.",
    "HOLD_LONG": "The conditions that supported the long position are still acceptable — no exit condition has triggered.",
    "WATCH_LONG": "The long position is still open, but some supporting conditions have weakened. Worth monitoring.",
    "EXIT_LONG": "The configured exit conditions for the long position have been triggered.",
    "HOLD_SHORT": "The conditions that supported the short position are still acceptable — no exit condition has triggered.",
    "WATCH_SHORT": "The short position is still open, but some supporting conditions have weakened. Worth monitoring.",
    "EXIT_SHORT": "The configured exit conditions for the short position have been triggered.",
}

HELP_TEXT = (
    "🦅 BTC-NIGHT-HAWK Commands\n\n"
    "/price - current BTC price\n"
    "/trend - up, down, or sideways\n"
    "/analysis - full breakdown\n"
    "/levels - support & resistance\n"
    "/volume - trading activity vs normal\n"
    "/volatility - calm/normal/active/crazy\n"
    "/action - current LONG/SHORT/WAIT/HOLD/EXIT state\n"
    "/position - current tracked position\n"
    "/status - full dashboard\n"
    "/health - system health check\n"
    "/learn <topic> - beginner explanation (e.g. /learn rsi)\n"
    "/help - this list\n\n"
    "Mode: ANALYSIS only for now — no simulated or real trades yet, that's\n"
    "coming in the next phase. Live trading is not built into this bot at all.\n\n"
    "You'll get an hourly check-in automatically, plus real alerts when\n"
    "something strong is happening."
)


def send_message(text: str):
    if not config.TELEGRAM_CHAT_ID:
        print("No CHAT_ID set yet - skipping send.")
        return
    requests.post(f"{TELEGRAM_API}/sendMessage", data={
        "chat_id": config.TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"
    }, timeout=15)


def get_updates(offset: int):
    r = requests.get(f"{TELEGRAM_API}/getUpdates", params={"offset": offset, "timeout": 0}, timeout=15)
    r.raise_for_status()
    return r.json().get("result", [])


def format_action_block(snap: dict) -> str:
    label = ACTION_LABELS.get(snap["action"], snap["action"])
    simple = ACTION_SIMPLE.get(snap["action"], "")
    return f"ACTION\n{label}\n\nSimple:\n{simple}"


def format_alert(snap: dict) -> str:
    reasons_text = "\n".join(f"• {r}" for r in snap["reasons"]) or "• (no strong reasons yet)"
    risks_text = "\n".join(f"• {r}" for r in snap["opposing_reasons"]) or "• None weighing against it right now"
    support = snap["support"] if snap["support"] is not None else 0
    resistance = snap["resistance"] if snap["resistance"] is not None else 0
    return (
        f"🦅 BTC-NIGHT-HAWK\n\n"
        f"{format_action_block(snap)}\n\n"
        f"BTC: ${snap['price']:,.0f}\n"
        f"Setup Quality: {snap['score']}/100\n\n"
        f"Why:\n{reasons_text}\n\n"
        f"Risks:\n{risks_text}\n\n"
        f"Important levels:\n"
        f"Support: ${support:,.0f}\n"
        f"Resistance: ${resistance:,.0f}\n\n"
        f"<i>Setup Quality reflects how much evidence agrees, not a win probability.</i>"
    )


def format_analysis(snap: dict) -> str:
    rsi_text = f"{snap['rsi']:.0f}" if snap["rsi"] is not None else "N/A"
    trend_emoji = {"UP": "🟢 Going up", "DOWN": "🔴 Going down", "SIDEWAYS": "🟡 Sideways"}[snap["trend"]]
    support = snap["support"] if snap["support"] is not None else 0
    resistance = snap["resistance"] if snap["resistance"] is not None else 0
    return (
        f"📊 BTC ANALYSIS\n\n"
        f"Price: ${snap['price']:,.0f}\n"
        f"Trend: {trend_emoji}\n"
        f"Volatility: {snap['volatility_emoji']} {snap['volatility']}\n"
        f"Trading activity: {snap['volume_spike']:.1f}x normal\n"
        f"RSI: {rsi_text}\n\n"
        f"Support (floor): ${support:,.0f}\n"
        f"Resistance (ceiling): ${resistance:,.0f}"
    )


def format_status(snap: dict) -> str:
    rsi_text = f"{snap['rsi']:.0f}" if snap["rsi"] is not None else "N/A"
    pos = snap["position"]
    position_text = "NONE" if pos["side"] is None else pos["side"].upper()
    return (
        f"🦅 BTC-NIGHT-HAWK STATUS\n\n"
        f"BTC: ${snap['price']:,.0f}\n\n"
        f"{format_action_block(snap)}\n\n"
        f"Setup Quality: {snap['score']}/100\n"
        f"Trend: {snap['trend']}\n"
        f"RSI: {rsi_text}\n"
        f"Volatility: {snap['volatility_emoji']} {snap['volatility']}\n\n"
        f"Position: {position_text}\n\n"
        f"Mode: 🧪 {config.MODE.upper()}\n"
        f"Auto-trading: 🔴 OFF (not built into this bot)"
    )


def format_position(snap: dict) -> str:
    pos = snap["position"]
    if pos["side"] is None:
        return "Current position: NONE"
    return (
        f"Current position: {pos['side'].upper()}\n"
        f"Entry price: ${pos['entry_price']:,.2f}\n"
        f"Entry Setup Quality: {pos['entry_score']}/100\n"
        f"Current price: ${snap['price']:,.2f}"
    )


def format_health(last_run_time, error_count, price_points):
    return (
        f"🩺 SYSTEM HEALTH\n\n"
        f"Last successful scan: {last_run_time or 'never'}\n"
        f"Price points last run: {price_points}\n"
        f"Recent errors logged: {error_count}\n"
        f"Telegram: ✅ connected\n"
        f"Mode: 🧪 {config.MODE.upper()}\n"
        f"Auto-trading: 🔴 OFF"
    )


def format_learn(topic_key: str) -> str:
    topic = learn.get(topic_key)
    if not topic:
        return f"I don't have a lesson on '{topic_key}' yet. Try one of: {learn.list_topics()}"
    return (
        f"📚 {topic['title']}\n\n"
        f"What it is:\n{topic['what']}\n\n"
        f"Why it matters:\n{topic['why']}\n\n"
        f"Simple example:\n{topic['example']}\n\n"
        f"Important:\n{topic['not']}"
    )
