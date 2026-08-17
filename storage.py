"""
storage.py — Persistence Layer

Everything the bot needs to remember between runs lives here, in the /data
folder, committed back to git by the GitHub Actions workflow. This is a
simple file-based store, not a real database — a fine trade-off for a
free, git-committed bot. Each concern gets its own file (data/bot_state.json,
data/signal_journal.json, etc.) instead of one giant blob, so nothing gets
tangled together.

If this project ever needs to hold months of signal history or do heavy
backtesting over long periods, a real database will be worth adding — this
layer is written so that swap could happen later without touching the code
that calls load()/save().
"""

import json
import os

DATA_DIR = "data"


def _path(name: str) -> str:
    return os.path.join(DATA_DIR, f"{name}.json")


def load(name: str, default):
    path = _path(name)
    if not os.path.exists(path):
        return default
    with open(path, "r") as f:
        return json.load(f)


def save(name: str, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_path(name), "w") as f:
        json.dump(data, f, indent=2)
