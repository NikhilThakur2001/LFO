"""
Supervisor agent. Read-only on SystemState.
Responsibilities:
- Heartbeat watch (alerts if any agent silent >5 min)
- Spam guard (>2 signals same zone in 1h → suppress)
- RunPod daily cost tracker
- Weekly digest every Sunday 09:00 UTC
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from config import Config
from db.repository import get_weekly_summary, save_audit_event, count_recent_signals
from state import SystemState

log = logging.getLogger(__name__)

HEARTBEAT_TIMEOUT_MIN = 5
AVG_RUNPOD_COST_USD = 0.02
SPAM_THRESHOLD = 2
SPAM_WINDOW_MIN = 60
AUDIT_INTERVAL_SEC = 60


async def run_auditor_agent(state: SystemState, config: Config) -> None:
    last_digest_day: int | None = None

    while True:
        try:
            state.beat("AuditorAgent")
            await _check_heartbeats(state, config)
            await _check_runpod_cost(state, config)
            await _maybe_send_weekly_digest(state, config, last_digest_day)
        except Exception as e:
            log.error(f"AuditorAgent error: {e}")

        await asyncio.sleep(AUDIT_INTERVAL_SEC)


async def _check_heartbeats(state: SystemState, config: Config) -> None:
    now = datetime.utcnow()
    for agent, last_beat in state.agent_heartbeats.items():
        silent_min = (now - last_beat).total_seconds() / 60
        if silent_min > HEARTBEAT_TIMEOUT_MIN:
            msg = f"⚠️ [{agent}] silent for {silent_min:.0f}min — check VPS"
            log.warning(msg)
            save_audit_event("agent_silent", agent, msg)
            await _send_alert(msg, config)


async def _check_runpod_cost(state: SystemState, config: Config) -> None:
    estimated = state.runpod_calls_today * AVG_RUNPOD_COST_USD
    if estimated > config.runpod_daily_budget_usd:
        msg = (
            f"⚠️ RunPod daily estimate ${estimated:.2f} "
            f"exceeds budget ${config.runpod_daily_budget_usd:.2f} "
            f"({state.runpod_calls_today} calls)"
        )
        log.warning(msg)
        save_audit_event("cost_spike", "", msg)
        await _send_alert(msg, config)

    # Reset counter at midnight UTC
    now = datetime.now(timezone.utc)
    if now.hour == 0 and now.minute < 2:
        state.runpod_calls_today = 0


async def _maybe_send_weekly_digest(
    state: SystemState, config: Config, last_digest_day: int | None
) -> None:
    now = datetime.now(timezone.utc)
    is_sunday = now.weekday() == 6
    is_digest_hour = now.hour == 9 and now.minute < 2
    already_sent_today = last_digest_day == now.day

    if is_sunday and is_digest_hour and not already_sent_today:
        summary = get_weekly_summary()
        estimated_monthly = summary["runpod_calls"] * AVG_RUNPOD_COST_USD * 4.3
        msg = (
            f"📊 *Weekly FVG Agent Digest*\n\n"
            f"Signals fired: {summary['dispatched']}/{summary['total']}\n"
            f"Skipped: {summary['skipped']}\n"
            f"RunPod calls: {summary['runpod_calls']}\n"
            f"Fast-path calls: {summary['fast_calls']}\n"
            f"Est\\. monthly RunPod cost: ${estimated_monthly:.2f}\n\n"
            f"Top skip reasons:\n"
        )
        for reason, count in summary["top_skip_reasons"]:
            msg += f"  • {reason}: {count}\n"

        save_audit_event("weekly_digest", "", msg)
        await _send_alert(msg, config)


async def _send_alert(text: str, config: Config) -> None:
    if config.paper_mode:
        log.info(f"[PAPER AUDITOR] {text}")
        return
    try:
        from telegram import Bot
        bot = Bot(token=config.telegram_bot_token)
        await bot.send_message(chat_id=config.telegram_chat_id, text=text)
    except Exception as e:
        log.error(f"Auditor alert send failed: {e}")


def check_spam(asset: str, direction: str, zone_key: float) -> bool:
    """Returns True if this signal is spam (same zone fired too recently)."""
    count = count_recent_signals(asset, direction, zone_key, within_minutes=SPAM_WINDOW_MIN)
    return count >= SPAM_THRESHOLD
