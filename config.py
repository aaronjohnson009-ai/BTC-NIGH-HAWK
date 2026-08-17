"""
config.py — BTC-NIGHT-HAWK Configuration

Every threshold, period, and limit lives here so nothing is buried inside
logic files. Change values here, not inside the engines. These are real
working defaults, not placeholders — tune them as you learn how the bot
behaves.
"""

import os

# ---------- SCAN & ALERTS ----------
SCAN_INTERVAL_MINUTES = 5          # how often GitHub Actions runs this bot
ALERT_SETUP_SCORE_THRESHOLD = 60   # 0-100, minimum Setup Quality to enter a position
ALERT_COOLDOWN_MINUTES = 60        # don't repeat the same direction within this window
HEARTBEAT_MINUTES = 60             # send an hourly check-in even without a strong alert

# ---------- ACTION SYSTEM (position-aware LONG/SHORT/WAIT states) ----------
ACTION_EXIT_SCORE_THRESHOLD = 40   # while in a position, exit if score drops below this
ACTION_WATCH_SCORE_DROP = 15       # flag WATCH if score falls this many points from entry

# ---------- MARKET DATA ----------
COIN_ID = "bitcoin"
VS_CURRENCY = "usd"
LOOKBACK_DAYS = 30                 # how much hourly history to pull each run

# ---------- INDICATORS ----------
RSI_PERIOD = 14
EMA_PERIODS = [20, 50, 200]
VOLUME_SPIKE_MULTIPLIER = 1.5      # trading activity above this x the 24h average counts as a "spike"
SUPPORT_RESISTANCE_LOOKBACK_HOURS = 24 * 7   # ~7 days of hourly data

# ---------- MODE ----------
# Three modes: "analysis" (alerts only, no simulated trades), "paper"
# (simulated trades), "live" (real money — NOT implemented in this project;
# there is intentionally no code path anywhere that can submit a real
# exchange order).
MODE = "analysis"

# ---------- TELEGRAM ----------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
