"""
main.py — BTC-NIGHT-HAWK Entry Point (Phase 2+3: Paper Trading, Risk Engine,
Multi-Timeframe, Market Regime, Outcome Tracking, Price Alerts)

Runs on a schedule via GitHub Actions. Each run:
1. Fetches + validates market data (data_engine)
2. Computes indicators, multi-timeframe agreement, and market regime
3. Builds bullish/bearish evidence and scores the setup (signal_engine, scoring_engine)
4. Determines the current action state (action_engine)
5. Records the signal in the journal (journal) and appends to the price archive
6. Grades any signals that are now old enough to evaluate (outcome_engine)
7. Handles any Telegram commands sent since the last run
8. Sends a Telegram alert if warranted, or an hourly check-in otherwise
9. Checks custom price alerts (price_alerts)
10. Runs every paper trading strategy and sends a message for any trade opened or closed
11. Persists everything back to /data via storage.py (committed to git by the workflow)

NOTE: Genetic strategy evolution (the "self-learning" piece) is still Phase
4 — it needs a large, varied dataset to responsibly split into training,
validation, and test sets, which 30 days of hourly data can't yet provide
without risking a misleading result.
"""

from datetime import datetime, timezone

import config
import storage
import data_engine
import signal_engine
import scoring_engine
import action_engine
import journal
import learn
import paper_trading
import performance
import multi_timeframe
import regime_engine
import outcome_engine
import price_alerts
import price_archive
import telegram_bot as tg


def handle_commands(state: dict, snap: dict, paper_window: list[dict]) -> dict:
    updates = tg.get_updates(state.get("last_update_id", 0) + 1)
    for u in updates:
        state["last_update_id"] = u["update_id"]
        msg = u.get("message", {})
        text = msg.get("text", "") or ""
        chat_id = msg.get("chat", {}).get("id")

        if chat_id and not config.TELEGRAM_CHAT_ID:
            print(f"First message seen. Your chat_id is: {chat_id}")

        if text.startswith("/price"):
            tg.send_message(f"💰 BTC: ${snap['price']:,.0f}")
        elif text.startswith("/trend"):
            tg.send_message(f"Trend: {snap['trend']}")
        elif text.startswith("/analysis"):
            tg.send_message(tg.format_analysis(snap))
        elif text.startswith("/levels"):
            support = snap["support"] if snap["support"] is not None else 0
            resistance = snap["resistance"] if snap["resistance"] is not None else 0
            tg.send_message(f"Support: ${support:,.0f}\nResistance: ${resistance:,.0f}")
        elif text.startswith("/volume"):
            tg.send_message(f"Trading activity is {snap['volume_spike']:.1f}x normal")
        elif text.startswith("/volatility"):
            tg.send_message(f"{snap['volatility_emoji']} {snap['volatility']}")
        elif text.startswith("/action"):
            tg.send_message(tg.format_action_block(snap))
        elif text.startswith("/position"):
            tg.send_message(tg.format_position(snap))
        elif text.startswith("/status"):
            tg.send_message(tg.format_status(snap))
        elif text.startswith("/health"):
            errors = storage.load("error_log", [])
            tg.send_message(tg.format_health(state.get("last_run_time"), len(errors), state.get("last_price_points", 0)))
        elif text.startswith("/paper"):
            tg.send_message(performance.format_leaderboard(paper_trading.all_metrics(snap["price"])))
        elif text.startswith("/consensus"):
            tg.send_message(tg.format_consensus(paper_trading.consensus(paper_window)))
        elif text.startswith("/regime"):
            tg.send_message(tg.format_regime(snap.get("regime_info", {})))
        elif text.startswith("/stats"):
            tg.send_message(tg.format_stats(outcome_engine.summary()))
        elif text.startswith("/alerts"):
            tg.send_message(tg.format_alerts_list(price_alerts.list_alerts()))
        elif text.startswith("/alert"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                tg.send_message("Usage: /alert <price>, e.g. /alert 70000")
            else:
                try:
                    target = float(parts[1].replace(",", "").replace("$", ""))
                    price_alerts.add_alert(target)
                    tg.send_message(f"🎯 Alert set for ${target:,.2f}. I'll message you when BTC crosses it.")
                except ValueError:
                    tg.send_message("That doesn't look like a number. Try: /alert 70000")
        elif text.startswith("/learn"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                tg.send_message(f"Usage: /learn <topic>\nAvailable: {learn.list_topics()}")
            else:
                tg.send_message(tg.format_learn(parts[1]))
        elif text.startswith("/help") or text.startswith("/start"):
            tg.send_message(tg.HELP_TEXT)

    return state


def run():
    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN not set")

    state = storage.load("bot_state", {
        "last_update_id": 0,
        "last_alert_direction": None,
        "last_alert_time": None,
        "last_heartbeat_time": None,
        "last_run_time": None,
        "last_price_points": 0,
        "last_price": None,
    })

    try:
        prices, volumes, fetched_at = data_engine.fetch_market_data()
    except data_engine.DataQualityError as e:
        error_log = storage.load("error_log", [])
        error_log.append({"time": datetime.now(timezone.utc).isoformat(), "error": str(e)})
        storage.save("error_log", error_log[-200:])
        tg.send_message(f"⚠️ Data quality problem, skipping this run:\n{e}")
        print(f"DataQualityError: {e}")
        return

    raw_snapshot = signal_engine.build_snapshot(prices, volumes)
    scored = scoring_engine.score_snapshot(raw_snapshot)
    snap = action_engine.determine_action(scored)

    # Multi-timeframe + market regime — descriptive context, attached to the snapshot
    regime_info = regime_engine.detect(prices, snap["volatility"])
    snap["regime"] = regime_info["regime"]
    snap["regime_info"] = regime_info

    paper_window = [{"price": p} for p in prices[-config.PAPER_STRATEGY_WINDOW:]]

    # Signal journal — record every signal, not just alerts
    journal.record_signal(journal.next_signal_id(), {
        "price": snap["price"], "direction": snap["direction"], "score": snap["score"],
        "action": snap["action"], "rsi": snap["rsi"], "ema20": snap["ema20"], "ema50": snap["ema50"],
        "ema200": snap["ema200"], "support": snap["support"], "resistance": snap["resistance"],
        "volatility": snap["volatility"], "volume_spike": snap["volume_spike"],
        "reasons": snap["reasons"], "opposing_reasons": snap["opposing_reasons"],
        "regime": snap["regime"],
    })

    # Grow the price archive and grade any signals old enough to evaluate — both silent/background
    price_archive.append(snap["price"])
    outcome_engine.grade_due_signals(snap["price"])

    # Handle Telegram commands using this run's fresh snapshot
    state = handle_commands(state, snap, paper_window)

    # Alerting: only on actual entries/exits, never on HOLD/WATCH/WAIT — avoids spam
    now = datetime.now(timezone.utc)
    cooldown_ok = True
    if state.get("last_alert_time"):
        last_time = datetime.fromisoformat(state["last_alert_time"])
        minutes_since = (now - last_time).total_seconds() / 60
        if minutes_since < config.ALERT_COOLDOWN_MINUTES and state.get("last_alert_direction") == snap["direction"]:
            cooldown_ok = False

    alert_sent = False
    if snap["action"] in ("LONG_ENTRY", "SHORT_ENTRY", "EXIT_LONG", "EXIT_SHORT") and cooldown_ok:
        tg.send_message(tg.format_alert(snap))
        alert_sent = True
        state["last_alert_direction"] = snap["direction"]
        state["last_alert_time"] = now.isoformat()

    # Hourly heartbeat — keeps you posted even when nothing crosses the alert bar
    heartbeat_due = True
    if state.get("last_heartbeat_time"):
        last_hb = datetime.fromisoformat(state["last_heartbeat_time"])
        if (now - last_hb).total_seconds() / 60 < config.HEARTBEAT_MINUTES:
            heartbeat_due = False

    if heartbeat_due:
        if not alert_sent:
            tg.send_message("⏱ HOURLY CHECK-IN\n\n" + tg.format_analysis(snap) + "\n\n" + tg.format_action_block(snap))
        state["last_heartbeat_time"] = now.isoformat()

    # Custom price alerts — notify on any target crossed since the last run
    for msg in price_alerts.check_and_trigger(snap["price"], state.get("last_price")):
        tg.send_message(msg)

    # Paper trading — every strategy takes its own simulated action on the latest prices
    for msg in paper_trading.run_all(snap["price"], paper_window):
        tg.send_message(msg)

    state["last_price"] = snap["price"]
    state["last_run_time"] = now.isoformat()
    state["last_price_points"] = len(prices)
    storage.save("bot_state", state)

    print(f"Run complete. Price=${snap['price']:,.0f} Action={snap['action']} Score={snap['score']} Regime={snap['regime']}")


if __name__ == "__main__":
    run()
