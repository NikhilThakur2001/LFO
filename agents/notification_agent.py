"""
Reads TradeSignal from notification_queue.
Dispatches Telegram + Email concurrently.
In PAPER_MODE: logs only, no actual sends.
"""
import asyncio
import logging

from config import Config
from db.repository import save_signal, save_audit_event
from notifications.email import send_email
from notifications.telegram import send_telegram
from models.signal import TradeSignal
from state import SystemState

log = logging.getLogger(__name__)


async def run_notification_agent(
    state: SystemState,
    config: Config,
    notification_queue: asyncio.Queue,
) -> None:
    while True:
        try:
            signal: TradeSignal = await asyncio.wait_for(notification_queue.get(), timeout=10)
            state.beat("NotificationAgent")
            await _dispatch(signal, config)
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            log.error(f"NotificationAgent error: {e}")


async def _dispatch(signal: TradeSignal, config: Config) -> None:
    if config.paper_mode:
        log.info(
            f"[PAPER] Signal: {signal.asset} {signal.direction} "
            f"entry={signal.entry_price:.5g} SL={signal.sl:.5g} "
            f"TP1={signal.tp1:.5g} TP2={signal.tp2:.5g} "
            f"confidence={signal.confidence}"
        )
        save_signal(signal, dispatched=False, skip_reason="PAPER_MODE")
        return

    results = await asyncio.gather(
        send_telegram(signal, config.__class__.__new__(config.__class__) if False else config),
        send_email(signal, config),
        return_exceptions=True,
    )

    all_ok = True
    for i, res in enumerate(results):
        channel = "telegram" if i == 0 else "email"
        if isinstance(res, Exception):
            log.error(f"Notification failed [{channel}]: {res}")
            save_audit_event("notify_fail", signal.asset, f"{channel}: {res}")
            all_ok = False

    save_signal(signal, dispatched=all_ok)
    if all_ok:
        log.info(f"Signal dispatched: {signal.asset} {signal.direction} {signal.entry_price:.5g}")
