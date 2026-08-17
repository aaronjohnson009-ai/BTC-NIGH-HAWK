"""
paper_trader.py — Backtesting + Paper Trading Engine for BTC-NIGH-HAWK

WHAT THIS DOES:
1. Defines "strategies" — simple, testable trading rules (e.g. "buy when RSI < 30")
2. Backtests each strategy against your bot's stored price history (state.json)
3. Runs strategies forward in "paper trading" mode — fake money, real logic,
   so you can see if a strategy actually works BEFORE trusting it

This is the foundation. Once this works, we plug in:
- Genetic evolution (auto-generate + breed new strategies)
- Confidence scoring (win-rate per strategy, shown in Telegram alerts)
- Multi-strategy comparison (run 10 strategies at once, see which wins)

HOW IT FITS YOUR EXISTING BOT:
Your bot.py already tracks price in state.json. This module reads that same
file, so no new data source is needed yet. Whale/news data comes later.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional


STATE_FILE = "state.json"  # your bot already saves full price_history here
PAPER_TRADES_FILE = "paper_trades.json"
STARTING_BALANCE = 500.0  # fake dollars, for paper trading only


# ---------------------------------------------------------------------------
# 1. PRICE HISTORY — your state.json already stores a running price_history
# list (each entry has "time" and "price"), so we read directly from it.
# No separate log file needed.
# ---------------------------------------------------------------------------

def load_price_history() -> list[dict]:
    """Reads price_history straight from your bot's existing state.json."""
    if not os.path.exists(STATE_FILE):
        return []
    with open(STATE_FILE, "r") as f:
        data = json.load(f)
    return data.get("price_history", [])


# ---------------------------------------------------------------------------
# 2. STRATEGY DEFINITION — a strategy is just a function: data -> "buy"/"sell"/"hold"
# ---------------------------------------------------------------------------

@dataclass
class Strategy:
    name: str
    # decide(price_window) -> "buy" | "sell" | "hold"
    # price_window is a list of recent price dicts, most recent last
    decide: Callable[[list[dict]], str]
    params: dict = field(default_factory=dict)


def rsi(prices: list[float], period: int = 14) -> Optional[float]:
    """Standard RSI calculation. Returns None if not enough data yet."""
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        change = prices[-i] - prices[-i - 1]
        (gains if change > 0 else losses).append(abs(change))
    avg_gain = sum(gains) / period if gains else 0.0001
    avg_loss = sum(losses) / period if losses else 0.0001
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def moving_average(prices: list[float], period: int) -> Optional[float]:
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


# --- A few starter strategies. More get added by the evolution engine later.

def strategy_rsi_reversal(window: list[dict], oversold=30, overbought=70) -> str:
    prices = [p["price"] for p in window]
    r = rsi(prices)
    if r is None:
        return "hold"
    if r < oversold:
        return "buy"
    if r > overbought:
        return "sell"
    return "hold"


def strategy_ma_crossover(window: list[dict], fast=9, slow=21) -> str:
    prices = [p["price"] for p in window]
    ma_fast = moving_average(prices, fast)
    ma_slow = moving_average(prices, slow)
    if ma_fast is None or ma_slow is None:
        return "hold"
    prev_fast = moving_average(prices[:-1], fast)
    prev_slow = moving_average(prices[:-1], slow)
    if prev_fast is None or prev_slow is None:
        return "hold"
    # crossover = fast line just crossed above/below slow line
    if prev_fast <= prev_slow and ma_fast > ma_slow:
        return "buy"
    if prev_fast >= prev_slow and ma_fast < ma_slow:
        return "sell"
    return "hold"


DEFAULT_STRATEGIES = [
    Strategy("RSI Reversal", strategy_rsi_reversal),
    Strategy("MA Crossover (9/21)", strategy_ma_crossover),
]


# ---------------------------------------------------------------------------
# 3. BACKTESTER — runs a strategy against past data, reports how it would've done
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    strategy_name: str
    trades: int
    wins: int
    losses: int
    total_return_pct: float
    win_rate_pct: float


def backtest(strategy: Strategy, history: list[dict], window_size: int = 30) -> BacktestResult:
    if len(history) < window_size + 1:
        return BacktestResult(strategy.name, 0, 0, 0, 0.0, 0.0)

    balance = STARTING_BALANCE
    position = None  # None or {"entry_price": float}
    trades, wins, losses = 0, 0, 0

    for i in range(window_size, len(history)):
        window = history[i - window_size:i]
        signal = strategy.decide(window)
        price = history[i]["price"]

        if signal == "buy" and position is None:
            position = {"entry_price": price}
        elif signal == "sell" and position is not None:
            pnl_pct = (price - position["entry_price"]) / position["entry_price"]
            balance *= (1 + pnl_pct)
            trades += 1
            if pnl_pct > 0:
                wins += 1
            else:
                losses += 1
            position = None

    total_return_pct = ((balance - STARTING_BALANCE) / STARTING_BALANCE) * 100
    win_rate = (wins / trades * 100) if trades > 0 else 0.0
    return BacktestResult(strategy.name, trades, wins, losses, round(total_return_pct, 2), round(win_rate, 1))


def run_all_backtests(strategies: list[Strategy] = None) -> list[BacktestResult]:
    strategies = strategies or DEFAULT_STRATEGIES
    history = load_price_history()
    results = [backtest(s, history) for s in strategies]
    results.sort(key=lambda r: r.total_return_pct, reverse=True)
    return results


# ---------------------------------------------------------------------------
# 4. PAPER TRADING — forward-testing with fake money, persisted between runs
# ---------------------------------------------------------------------------

def load_paper_state() -> dict:
    if not os.path.exists(PAPER_TRADES_FILE):
        return {
            "balance": STARTING_BALANCE,
            "position": None,
            "closed_trades": [],
        }
    with open(PAPER_TRADES_FILE, "r") as f:
        return json.load(f)


def save_paper_state(state: dict):
    with open(PAPER_TRADES_FILE, "w") as f:
        json.dump(state, f, indent=2)


def paper_trade_step(strategy: Strategy, current_price: float, window: list[dict]) -> str:
    """
    Call this once per bot run (e.g. every 10 min, same cadence as your
    existing schedule). It checks the strategy's signal and updates the
    fake portfolio accordingly. Returns a human-readable message you can
    send to Telegram.
    """
    state = load_paper_state()
    signal = strategy.decide(window)
    now = datetime.now(timezone.utc).isoformat()

    if signal == "buy" and state["position"] is None:
        state["position"] = {"entry_price": current_price, "opened_at": now}
        save_paper_state(state)
        return f"📈 PAPER BUY @ ${current_price:,.2f} ({strategy.name})"

    if signal == "sell" and state["position"] is not None:
        entry = state["position"]["entry_price"]
        pnl_pct = (current_price - entry) / entry * 100
        state["balance"] *= (1 + pnl_pct / 100)
        state["closed_trades"].append({
            "entry_price": entry,
            "exit_price": current_price,
            "pnl_pct": round(pnl_pct, 2),
            "opened_at": state["position"]["opened_at"],
            "closed_at": now,
        })
        state["position"] = None
        save_paper_state(state)
        result = "✅ WIN" if pnl_pct > 0 else "❌ LOSS"
        return f"📉 PAPER SELL @ ${current_price:,.2f} | {result} {pnl_pct:+.2f}% | Balance: ${state['balance']:,.2f}"

    return ""  # no action taken, nothing to report


def paper_trading_summary() -> str:
    state = load_paper_state()
    trades = state["closed_trades"]
    if not trades:
        return "📊 Paper trading: no closed trades yet."
    wins = sum(1 for t in trades if t["pnl_pct"] > 0)
    total_return = (state["balance"] - STARTING_BALANCE) / STARTING_BALANCE * 100
    return (
        f"📊 PAPER TRADING SUMMARY\n"
        f"Balance: ${state['balance']:,.2f} (started at ${STARTING_BALANCE:,.2f})\n"
        f"Total return: {total_return:+.2f}%\n"
        f"Trades: {len(trades)} | Wins: {wins} | Win rate: {wins/len(trades)*100:.1f}%"
    )


# ---------------------------------------------------------------------------
# Quick manual test — run this file directly to see backtest results
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    results = run_all_backtests()
    print("=== BACKTEST RESULTS ===")
    for r in results:
        print(f"{r.strategy_name}: {r.trades} trades, {r.win_rate_pct}% win rate, {r.total_return_pct:+.2f}% return")
    print()
    print(paper_trading_summary())
