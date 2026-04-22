"""
Polls Finnhub economic calendar every 5 min.
Exposes check_news_clear(asset) used by inference_manager as Phase 2 guardrail.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import finnhub

from config import Config
from db.repository import save_audit_event
from state import SystemState

log = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 300  # 5 minutes
BLOCK_BEFORE_MIN = 60
BLOCK_AFTER_MIN = 15

ASSET_CURRENCIES: dict[str, list[str]] = {
    "XAUUSD": ["USD"],
    "BTCUSDT": [],   # crypto has no forex calendar
    "ETHUSDT": [],
}


async def run_news_agent(state: SystemState, config: Config) -> None:
    client = finnhub.Client(api_key=config.finnhub_api_key)

    while True:
        try:
            state.beat("NewsAgent")
            now = datetime.now(timezone.utc)
            date_str = now.strftime("%Y-%m-%d")
            tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")

            data = await asyncio.to_thread(
                client.economic_calendar,
                _from=date_str,
                to=tomorrow,
            )
            events = data.get("economicCalendar", [])
            async with state.lock:
                state.news_cache = events
            log.debug(f"NewsAgent refreshed: {len(events)} events")
        except Exception as e:
            log.error(f"NewsAgent poll error: {e}")

        await asyncio.sleep(POLL_INTERVAL_SEC)


def check_news_clear(asset: str, state: SystemState) -> tuple[bool, str]:
    """
    Returns (is_clear, reason).
    is_clear=False means skip the signal — high-impact event too close.
    """
    currencies = ASSET_CURRENCIES.get(asset, [])
    if not currencies:
        return True, ""

    now = datetime.now(timezone.utc)

    for event in state.news_cache:
        if event.get("impact") != "high":
            continue
        if event.get("currency") not in currencies:
            continue

        try:
            event_time = datetime.fromisoformat(event["time"].replace("Z", "+00:00"))
        except Exception:
            continue

        delta_min = (event_time - now).total_seconds() / 60
        if -BLOCK_AFTER_MIN <= delta_min <= BLOCK_BEFORE_MIN:
            reason = (
                f"High-impact {event.get('country','')} "
                f"{event.get('event','')} in {delta_min:.0f}min"
            )
            save_audit_event("news_skip", asset, reason)
            return False, reason

    return True, ""
