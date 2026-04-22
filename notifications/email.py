import logging

import resend

from config import Config
from models.signal import TradeSignal

log = logging.getLogger(__name__)


def _build_html(signal: TradeSignal) -> str:
    direction_color = "#22c55e" if signal.direction == "LONG" else "#ef4444"
    return f"""
<!DOCTYPE html>
<html>
<body style="font-family: monospace; background: #0f172a; color: #e2e8f0; padding: 24px;">
  <h2 style="color:{direction_color};">
    FVG SIGNAL — {signal.asset} {signal.direction}
  </h2>
  <table style="border-collapse:collapse; width:100%; max-width:480px;">
    <tr><td style="padding:8px; color:#94a3b8;">Entry</td>
        <td style="padding:8px; font-weight:bold;">{signal.entry_price:.5g}</td></tr>
    <tr><td style="padding:8px; color:#94a3b8;">Stop Loss</td>
        <td style="padding:8px; color:#ef4444;">{signal.sl:.5g}</td></tr>
    <tr><td style="padding:8px; color:#94a3b8;">TP1 (1:1)</td>
        <td style="padding:8px; color:#22c55e;">{signal.tp1:.5g}</td></tr>
    <tr><td style="padding:8px; color:#94a3b8;">TP2 (1:2)</td>
        <td style="padding:8px; color:#22c55e;">{signal.tp2:.5g}</td></tr>
    <tr><td style="padding:8px; color:#94a3b8;">Confidence</td>
        <td style="padding:8px;">{signal.confidence}/100</td></tr>
    <tr><td style="padding:8px; color:#94a3b8;">Session</td>
        <td style="padding:8px;">{signal.session}</td></tr>
    <tr><td style="padding:8px; color:#94a3b8;">Inference</td>
        <td style="padding:8px;">{signal.inference_path}</td></tr>
  </table>
  <p style="margin-top:16px; color:#94a3b8; font-style:italic;">
    {signal.reasoning_summary}
  </p>
  <p style="color:#f59e0b; font-size:12px;">
    ⚠️ Risk 1% max. This is a signal — not financial advice. Manual execution only.
  </p>
  <p style="color:#475569; font-size:11px;">
    Signal ID: {signal.signal_id} | {signal.timestamp.strftime('%Y-%m-%d %H:%M UTC')}
  </p>
</body>
</html>"""


def _build_plain(signal: TradeSignal) -> str:
    return (
        f"FVG SIGNAL — {signal.asset} {signal.direction}\n"
        f"Entry: {signal.entry_price:.5g}\n"
        f"SL: {signal.sl:.5g}\n"
        f"TP1: {signal.tp1:.5g} (1:1)\n"
        f"TP2: {signal.tp2:.5g} (1:2)\n"
        f"Confidence: {signal.confidence}/100\n"
        f"Session: {signal.session}\n\n"
        f"{signal.reasoning_summary}\n\n"
        f"Risk 1% max. Manual execution only."
    )


async def send_email(signal: TradeSignal, config: Config) -> None:
    resend.api_key = config.resend_api_key
    subject = f"[FVG SIGNAL] {signal.asset} {signal.direction} — Entry {signal.entry_price:.5g}"
    try:
        resend.Emails.send({
            "from": config.resend_from_email,
            "to": [config.resend_to_email],
            "subject": subject,
            "html": _build_html(signal),
        })
        log.info(f"Email sent: {signal.asset} {signal.direction}")
    except Exception as e:
        log.error(f"HTML email failed ({e}), trying plain text")
        resend.Emails.send({
            "from": config.resend_from_email,
            "to": [config.resend_to_email],
            "subject": subject,
            "text": _build_plain(signal),
        })
