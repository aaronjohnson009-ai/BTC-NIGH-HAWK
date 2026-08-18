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

# ---------- MULTI-TIMEFRAME ----------
TIMEFRAME_SHORT_HOURS = 24              # ~1 day
TIMEFRAME_INTERMEDIATE_HOURS = 24 * 7   # ~1 week
TIMEFRAME_HIGHER_HOURS = 24 * 30        # ~1 month (full lookback window)

# ---------- MARKET REGIME ----------
REGIME_TREND_STRONG_PCT = 5.0      # % move over the higher timeframe to call a trend "Strong" vs "Weak"

# ---------- SIGNAL OUTCOME TRACKING ----------
OUTCOME_EVALUATION_HOURS = 24            # how long to wait before grading a signal's outcome
OUTCOME_SUCCESS_THRESHOLD_PCT = 1.0      # price must move at least this much in the predicted direction to count as a "success"

# ---------- PRICE ARCHIVE ----------
PRICE_ARCHIVE_MAX_POINTS = 8760    # ~1 year of hourly points

# ---------- PAPER TRADING ----------
PAPER_STARTING_BALANCE = 500.0
PAPER_FEE_PCT = 0.1                # simulated round-trip fee, % of trade size
PAPER_SLIPPAGE_PCT = 0.05          # simulated slippage, % applied against you on entry/exit
PAPER_STRATEGY_WINDOW = 30         # how many recent hourly prices each strategy looks at

# ---------- RISK ENGINE (used by paper trading; would apply to live trading too, if that existed) ----------
RISK_PER_TRADE_PCT = 2.0           # % of a strategy's balance risked per trade
DEFAULT_STOP_LOSS_PCT = 3.0
DEFAULT_TAKE_PROFIT_PCT = 6.0
MAX_OPEN_POSITIONS_PER_STRATEGY = 1
DAILY_LOSS_LIMIT_PCT = 5.0         # pause a strategy for the day if it loses this much
MAX_CONSECUTIVE_LOSSES = 4         # pause a strategy after this many losses in a row
MAX_DRAWDOWN_PCT = 20.0            # pause a strategy entirely if its drawdown from its peak balance exceeds this

# ---------- MODE ----------
# Three modes: "analysis" (alerts only, no simulated trades), "paper"
# (simulated trades — current mode), "live" (real money — NOT implemented
# in this project; there is intentionally no code path anywhere that can
# submit a real exchange order).
MODE = "paper"

# ---------- TELEGRAM ----------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
