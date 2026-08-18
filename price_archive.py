"""
price_archive.py — Growing Price History

Appends each run's latest price to a persistent, growing archive (capped
at config.PRICE_ARCHIVE_MAX_POINTS) instead of only ever seeing whatever
CoinGecko returns for the last 30 days. This slowly builds up real history
the bot owns — useful for future features (longer-range reporting, and
eventually strategy evolution once there's enough of it) that need more
than a rolling 30-day window.
"""

from datetime import datetime, timezone

import config
import storage

KEY = "price_archive"


def append(price: float):
    archive = storage.load(KEY, [])
    archive.append({"time": datetime.now(timezone.utc).isoformat(), "price": price})
    archive = archive[-config.PRICE_ARCHIVE_MAX_POINTS:]
    storage.save(KEY, archive)


def all_points() -> list[dict]:
    return storage.load(KEY, [])
