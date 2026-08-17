"""
learn.py — Beginner Education Content

Plain-English explanations for terms this bot uses. Add more entries any
time — each just needs "what", "why", "example", and "not" (what it does
NOT mean).
"""

TOPICS = {
    "rsi": {
        "title": "RSI (Relative Strength Index)",
        "what": "A number from 0-100 that describes how strongly price has been moving recently.",
        "why": "It can help identify when price has moved a lot in one direction, which sometimes (not always) comes before a pause or reversal.",
        "example": "Imagine a ball being pushed uphill — the farther it goes, the more interesting it is to ask whether the push is running out of steam.",
        "not": "A high RSI does NOT mean price must fall. A low RSI does NOT mean price must rise.",
    },
    "ema": {
        "title": "EMA (Exponential Moving Average)",
        "what": "A line that smooths out price over time, giving more weight to recent prices than old ones.",
        "why": "It helps show the general direction of price without reacting to every small wiggle.",
        "example": "The 20-hour EMA crossing above the 50-hour EMA is a common way to spot a shift in short-term direction.",
        "not": "An EMA crossing does NOT guarantee the new direction will continue.",
    },
    "volatility": {
        "title": "Volatility",
        "what": "How aggressively price is moving around, regardless of direction.",
        "why": "High volatility means bigger, faster price swings — both opportunity and risk are larger.",
        "example": "A CALM market barely moves hour to hour; a CRAZY market can swing several percent in an hour.",
        "not": "High volatility does NOT tell you which direction price will go, only how big the moves might be.",
    },
    "support": {
        "title": "Support",
        "what": "A price area where BTC has previously stopped falling or slowed down.",
        "why": "Traders watch these areas because price has 'bounced' there before.",
        "example": "If BTC has bounced off $60,000 three times, that area is considered support.",
        "not": "Support does NOT guarantee price will bounce again — it can break through.",
    },
    "resistance": {
        "title": "Resistance",
        "what": "A price area where BTC has previously struggled to move above.",
        "why": "It marks a level where selling pressure has shown up before.",
        "example": "If BTC has failed to close above $72,000 twice, that's resistance.",
        "not": "Resistance does NOT guarantee price will fail there again — it can break through.",
    },
    "volume": {
        "title": "Volume",
        "what": "How much trading activity (buying and selling) is happening.",
        "why": "A price move on high volume is generally considered more meaningful than the same move on low volume.",
        "example": "A price spike with 3x normal volume suggests real conviction behind the move.",
        "not": "High volume does NOT tell you whether the move will continue.",
    },
    "setupscore": {
        "title": "Setup Quality Score",
        "what": "A 0-100 score showing how much of the evidence this bot tracks currently agrees on one direction.",
        "why": "More agreeing signals = a 'cleaner' setup, in theory.",
        "example": "A score of 80/100 means most tracked signals agree; 30/100 means they're mixed or weak.",
        "not": "This score is NOT a win probability. An 80/100 setup does NOT mean an 80% chance of winning.",
    },
    "overfitting": {
        "title": "Overfitting",
        "what": "When a strategy is tuned so precisely to past data that it stops working on new data.",
        "why": "It's the single biggest trap in building trading strategies — a great backtest, useless in practice.",
        "example": "A strategy that made money on exactly one historical month but loses money on any other month is likely overfit.",
        "not": "A great backtest does NOT mean a strategy will work going forward — that's exactly what overfitting hides.",
    },
    "winrate": {
        "title": "Win Rate",
        "what": "The percentage of closed trades that were profitable.",
        "why": "It's one useful stat, but not the whole picture.",
        "example": "7 wins out of 10 trades = 70% win rate.",
        "not": "A high win rate does NOT mean a strategy is profitable — a few big losses can outweigh many small wins.",
    },
    "drawdown": {
        "title": "Drawdown",
        "what": "How far a balance has fallen from its highest point.",
        "why": "It measures the pain of holding a strategy through its worst stretch, not just its end result.",
        "example": "If a $500 balance grows to $700 and then drops to $560, that's a 20% drawdown.",
        "not": "A strategy with a great total return can still have brutal drawdowns along the way.",
    },
}


def get(topic: str):
    return TOPICS.get(topic.lower().strip())


def list_topics() -> str:
    return ", ".join(f"/learn {t}" for t in TOPICS)
