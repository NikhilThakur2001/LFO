import logging
import re

from telegram import Bot
from telegram.constants import ParseMode

from config import Config
from models.signal import TradeSignal

log = logging.getLogger(__name__)

_DIRECTION_EMOJI = {"LONG": "🟢", "SHORT": "🔴"}


def _escape(text: str) -> str:
    """Escape special chars for Telegram MarkdownV2."""
    return re.sub(r"([_*\[\]()~`>#+\-=|{}.!\\])", r"\\\1", str(text))


def _format_message(signal: TradeSignal) -> str:
    dir_emoji = _DIRECTION_EMOJI.get(signal.direction, "⚪")
    return (
        f"🔔 *FVG SIGNAL — {_escape(signal.asset)} {_escape(signal.direction)}* {dir_emoji}\n\n"
        f"📍 Entry: `{_escape(f'{signal.entry_price:.5g}')}`\n"
        f"🛑 Stop Loss: `{_escape(f'{signal.sl:.5g}')}`\n"
        f"🎯 TP1: `{_escape(f'{signal.tp1:.5g}')}` \\(1:1\\)\n"
        f"🎯 TP2: `{_escape(f'{signal.tp2:.5g}')}` \\(1:2\\)\n\n"
        f"📊 Confidence: {_escape(str(signal.confidence))}/100\n"
        f"💡 _{_escape(signal.reasoning_summary)}_\n"
        f"🕐 Session: {_escape(signal.session)}\n\n"
        f"⚠️ Risk 1% max\\. Manual execution only\\."
    )


async def send_telegram(signal: TradeSignal, config: Config) -> None:
    bot = Bot(token=config.telegram_bot_token)
    text = _format_message(signal)
    await bot.send_message(
        chat_id=config.telegram_chat_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    log.info(f"Telegram sent: {signal.asset} {signal.direction}")
