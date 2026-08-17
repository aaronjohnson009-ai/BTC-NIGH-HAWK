"""
scoring_engine.py — Setup Quality Score

Turns the bullish/bearish evidence from signal_engine into a single 0-100
"Setup Quality" score and a direction.

IMPORTANT: this score describes how much evidence agrees, NOT a probability
of winning. An 80/100 score does not mean an "80% chance." telegram_bot.py
attaches that disclaimer to every score shown to the user — see it there.
"""


def score_snapshot(snapshot: dict) -> dict:
    bullish = snapshot["bullish_reasons"]
    bearish = snapshot["bearish_reasons"]
    total_votes = len(bullish) + len(bearish)

    if total_votes == 0:
        direction, score, reasons, opposing = "SIDEWAYS", 0, [], []
    elif len(bullish) >= len(bearish):
        direction = "BULLISH"
        score = round((len(bullish) / max(total_votes, 1)) * 100 * min(total_votes / 4, 1))
        reasons, opposing = bullish, bearish
    else:
        direction = "BEARISH"
        score = round((len(bearish) / max(total_votes, 1)) * 100 * min(total_votes / 4, 1))
        reasons, opposing = bearish, bullish

    return {
        **snapshot,
        "direction": direction,
        "score": score,
        "reasons": reasons,
        "opposing_reasons": opposing,
    }
