"""
outcome_engine.py — Signal Outcome Tracking

Revisits past signals from the journal after a configured waiting period
and grades whether price actually moved the way the signal leaned. This is
tracked completely separately from paper trading performance — an alert
"succeeding" is not the same thing as a strategy making money. Powers the
/stats command, which was a stub in the very first version of this bot and
now actually does something.
"""

from datetime import datetime, timezone

import config
import journal
import storage

GRADED_KEY = "graded_signal_ids"
OUTCOMES_KEY = "signal_outcomes"


def _already_graded() -> set:
    return set(storage.load(GRADED_KEY, []))


def _mark_graded(signal_id: str):
    graded = storage.load(GRADED_KEY, [])
    graded.append(signal_id)
    storage.save(GRADED_KEY, graded[-5000:])


def grade_due_signals(current_price: float) -> list[dict]:
    """
    Looks through the journal for signals old enough to grade, grades each
    one exactly once, and returns any newly graded results. Silent by
    design — this runs every cycle in the background; results surface via
    the /stats command rather than pushing a message each time.
    """
    now = datetime.now(timezone.utc)
    graded_ids = _already_graded()
    newly_graded = []

    for entry in journal.all_signals():
        if entry["id"] in graded_ids:
            continue
        if entry["direction"] not in ("BULLISH", "BEARISH"):
            continue

        recorded_at = datetime.fromisoformat(entry["recorded_at"])
        hours_elapsed = (now - recorded_at).total_seconds() / 3600
        if hours_elapsed < config.OUTCOME_EVALUATION_HOURS:
            continue

        change_pct = (current_price - entry["price"]) / entry["price"] * 100 if entry["price"] else 0
        if entry["direction"] == "BULLISH":
            success = change_pct >= config.OUTCOME_SUCCESS_THRESHOLD_PCT
        else:
            success = change_pct <= -config.OUTCOME_SUCCESS_THRESHOLD_PCT

        outcome = {
            "id": entry["id"], "direction": entry["direction"], "score": entry["score"],
            "price_then": entry["price"], "price_now": current_price,
            "change_pct": round(change_pct, 2), "success": success,
            "graded_at": now.isoformat(),
        }
        outcomes = storage.load(OUTCOMES_KEY, [])
        outcomes.append(outcome)
        storage.save(OUTCOMES_KEY, outcomes[-5000:])
        _mark_graded(entry["id"])
        newly_graded.append(outcome)

    return newly_graded


def summary() -> dict:
    outcomes = storage.load(OUTCOMES_KEY, [])
    if not outcomes:
        return {"graded": 0}
    successes = sum(1 for o in outcomes if o["success"])
    return {
        "graded": len(outcomes),
        "success_rate_pct": round(successes / len(outcomes) * 100, 1),
        "avg_change_pct": round(sum(o["change_pct"] for o in outcomes) / len(outcomes), 2),
    }
