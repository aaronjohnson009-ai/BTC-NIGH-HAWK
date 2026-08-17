"""
journal.py — Signal Journal

Every signal the system generates gets a permanent record here: the price,
direction, score, indicator readings, and reasons — captured at the moment
it happened. This is what lets us later ask "how did signals with RSI under
30 actually perform?" instead of guessing. Capped at MAX_ENTRIES so the
file never grows unbounded.
"""

from datetime import datetime, timezone

import storage

JOURNAL_KEY = "signal_journal"
MAX_ENTRIES = 5000


def record_signal(signal_id: str, snapshot: dict):
    journal = storage.load(JOURNAL_KEY, [])
    entry = {"id": signal_id, "recorded_at": datetime.now(timezone.utc).isoformat(), **snapshot}
    journal.append(entry)
    journal = journal[-MAX_ENTRIES:]
    storage.save(JOURNAL_KEY, journal)


def all_signals() -> list[dict]:
    return storage.load(JOURNAL_KEY, [])


def next_signal_id() -> str:
    journal = storage.load(JOURNAL_KEY, [])
    return f"sig_{len(journal) + 1}"
