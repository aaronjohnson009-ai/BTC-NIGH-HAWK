"""
data_engine.py — Market Data Retrieval & Validation

Fetches BTC price/volume history from CoinGecko, retries on failure, and
checks the data for obvious problems (empty, stale, wrong shape, implausible
jumps) before handing it to the rest of the system. If data quality is
questionable, callers get a clear reason instead of silently working with
bad data — per the "fail closed" principle: no signal, no trade, on bad data.
"""

import time
import requests
from datetime import datetime, timezone

import config


class DataQualityError(Exception):
    """Raised when market data fails validation — callers must not trade on it."""
    pass


def fetch_market_data(max_retries: int = 3, retry_delay_seconds: float = 2.0):
    """
    Returns (prices, volumes, fetched_at) — lists of floats plus the time the
    data was pulled. Raises DataQualityError if the data can't be trusted,
    after retrying transient failures.
    """
    url = f"https://api.coingecko.com/api/v3/coins/{config.COIN_ID}/market_chart"
    params = {"vs_currency": config.VS_CURRENCY, "days": config.LOOKBACK_DAYS, "interval": "hourly"}

    last_error = None
    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
            prices = [p[1] for p in data.get("prices", [])]
            volumes = [v[1] for v in data.get("total_volumes", [])]
            _validate(prices, volumes)
            return prices, volumes, datetime.now(timezone.utc)
        except (requests.RequestException, DataQualityError, ValueError) as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(retry_delay_seconds)

    raise DataQualityError(f"Market data fetch failed after {max_retries} attempts: {last_error}")


def _validate(prices, volumes):
    if not prices or not volumes:
        raise DataQualityError("Market data came back empty.")
    if len(prices) < 30:
        raise DataQualityError(f"Only {len(prices)} price points returned — too little to analyze safely.")
    if any(p <= 0 for p in prices[-10:]):
        raise DataQualityError("Recent prices include a zero or negative value — likely bad data.")
    # sanity check: no single-hour move should plausibly exceed ~30% in normal conditions
    for i in range(1, min(len(prices), 50)):
        prev = prices[-i - 1]
        if prev > 0:
            change = abs(prices[-i] - prev) / prev
            if change > 0.30:
                raise DataQualityError(f"Implausible price jump detected ({change * 100:.0f}% in one interval).")
