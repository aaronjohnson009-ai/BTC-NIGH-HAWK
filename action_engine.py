"""
action_engine.py — Position-Aware Action States

Turns a direction + score into a clear action: LONG ENTRY, SHORT ENTRY,
WAIT, HOLD, WATCH, or EXIT — depending on whether the system currently has
an open (tracked, not real-money) position. This intentionally never says
plain "BUY" or "SELL", which a beginner can easily misread as "open a
short" vs "sell something I already own."
"""

import storage
import config

STATE_KEY = "signal_position"


def _load_position():
    return storage.load(STATE_KEY, {"side": None, "entry_score": None, "entry_price": None})


def _save_position(position):
    storage.save(STATE_KEY, position)


def determine_action(scored_snapshot: dict) -> dict:
    position = _load_position()
    direction = scored_snapshot["direction"]
    score = scored_snapshot["score"]
    price = scored_snapshot["price"]
    side = position["side"]

    if side is None:
        if score >= config.ALERT_SETUP_SCORE_THRESHOLD and direction == "BULLISH":
            action = "LONG_ENTRY"
            position = {"side": "long", "entry_score": score, "entry_price": price}
        elif score >= config.ALERT_SETUP_SCORE_THRESHOLD and direction == "BEARISH":
            action = "SHORT_ENTRY"
            position = {"side": "short", "entry_score": score, "entry_price": price}
        else:
            action = "WAIT"

    elif side == "long":
        if direction == "BEARISH" or score < config.ACTION_EXIT_SCORE_THRESHOLD:
            action = "EXIT_LONG"
            position = {"side": None, "entry_score": None, "entry_price": None}
        elif position["entry_score"] is not None and score < position["entry_score"] - config.ACTION_WATCH_SCORE_DROP:
            action = "WATCH_LONG"
        else:
            action = "HOLD_LONG"

    else:  # side == "short"
        if direction == "BULLISH" or score < config.ACTION_EXIT_SCORE_THRESHOLD:
            action = "EXIT_SHORT"
            position = {"side": None, "entry_score": None, "entry_price": None}
        elif position["entry_score"] is not None and score < position["entry_score"] - config.ACTION_WATCH_SCORE_DROP:
            action = "WATCH_SHORT"
        else:
            action = "HOLD_SHORT"

    _save_position(position)
    return {**scored_snapshot, "action": action, "position": position}
