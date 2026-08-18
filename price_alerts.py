"""
price_alerts.py — Custom Price Alerts

Lets you set a target price ("alert me if BTC hits $70,000") and get
notified once it's crossed. One-time by default — once triggered, the
alert is removed automatically.
"""

from datetime import datetime, timezone

import storage

KEY = "price_alerts"


def add_alert(target_price: float) -> dict:
    alerts = storage.load(KEY, [])
    alert = {
        "id": f"alert_{len(alerts) + 1}_{int(datetime.now(timezone.utc).timestamp())}",
        "target_price": target_price,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    alerts.append(alert)
    storage.save(KEY, alerts)
    return alert


def list_alerts() -> list[dict]:
    return storage.load(KEY, [])


def check_and_trigger(current_price: float, previous_price: float) -> list[str]:
    """Returns Telegram messages for any alert crossed since the last check, removing them once fired."""
    if previous_price is None:
        return []

    alerts = storage.load(KEY, [])
    remaining = []
    messages = []

    for a in alerts:
        target = a["target_price"]
        crossed = (previous_price < target <= current_price) or (previous_price > target >= current_price)
        if crossed:
            messages.append(
                f"🎯 PRICE ALERT\nBTC hit your target of ${target:,.2f}\n"
                f"Current price: ${current_price:,.2f}"
            )
        else:
            remaining.append(a)

    storage.save(KEY, remaining)
    return messages
