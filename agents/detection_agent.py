"""
Runs the 5-check FVG detection pipeline on each closed M15 candle.
Puts valid DetectionContext objects into the inference queue.
"""
import asyncio
import logging
from datetime import datetime, timezone

from config import Config
from db.repository import save_signal, save_audit_event
from detection.confluence import check_d1_extreme, check_h4_conflict, detect_trend
from detection.displacement import check_displacement
from detection.fvg import detect_fvg
from detection.liquidity import check_liquidity_sweep
from detection.session import check_session
from models.signal import DetectionContext, TradeSignal
from state import SystemState

log = logging.getLogger(__name__)

# Assets where volume data from Delta Exchange is reliable
VOLUME_ASSETS = {"BTCUSDT", "ETHUSDT"}


def _compute_levels(fvg_eq: float, fvg_low: float, fvg_high: float, direction: str) -> tuple:
    """Compute SL, TP1, TP2 from FVG boundaries."""
    buffer = fvg_eq * 0.001  # 0.1% buffer on SL
    if direction == "LONG":
        sl = fvg_low - buffer
        risk = fvg_eq - sl
    else:
        sl = fvg_high + buffer
        risk = sl - fvg_eq
    tp1 = fvg_eq + risk if direction == "LONG" else fvg_eq - risk
    tp2 = fvg_eq + 2 * risk if direction == "LONG" else fvg_eq - 2 * risk
    rr = 2.0
    return sl, tp1, tp2, rr


async def run_detection_agent(
    asset: str,
    state: SystemState,
    config: Config,
    inference_queue: asyncio.Queue,
) -> None:
    """Poll M15 buffer; run pipeline on each new closed candle."""
    last_candle_ts: datetime | None = None

    while True:
        try:
            state.beat(f"DetectionAgent:{asset}")
            m15 = state.get_candles(asset, "M15")

            if len(m15) < 3:
                await asyncio.sleep(5)
                continue

            latest: datetime = m15[-1].timestamp
            if latest == last_candle_ts:
                await asyncio.sleep(5)
                continue
            last_candle_ts = latest

            # --- Check 1: FVG ---
            fvg = detect_fvg(m15)
            if not fvg:
                await asyncio.sleep(5)
                continue

            # --- Check 2: Displacement ---
            has_vol = asset in VOLUME_ASSETS
            if not check_displacement(m15, fvg.displacement_candle_idx, has_vol):
                _skip(asset, fvg.direction, "SKIP_DISPLACEMENT", state)
                await asyncio.sleep(5)
                continue

            # --- Check 3: Multi-TF Confluence ---
            h1 = state.get_candles(asset, "H1")
            h4 = state.get_candles(asset, "H4")
            d1 = state.get_candles(asset, "D1")
            h1_trend = detect_trend(h1)

            if fvg.direction == "LONG" and h1_trend == "DOWNTREND":
                _skip(asset, fvg.direction, "SKIP_H1_TREND", state)
                await asyncio.sleep(5)
                continue
            if fvg.direction == "SHORT" and h1_trend == "UPTREND":
                _skip(asset, fvg.direction, "SKIP_H1_TREND", state)
                await asyncio.sleep(5)
                continue

            if check_h4_conflict(fvg.direction, fvg.equilibrium, h4):
                _skip(asset, fvg.direction, "SKIP_H4_CONFLICT", state)
                await asyncio.sleep(5)
                continue

            d1_warn, d1_reason = check_d1_extreme(fvg.direction, fvg.equilibrium, d1)
            h4_context = f"No H4 zone conflict. H4 trend context: {detect_trend(h4)}"

            # --- Check 4: Session ---
            now = datetime.now(timezone.utc)
            valid_session, session_name = check_session(asset, now)
            if not valid_session:
                _skip(asset, fvg.direction, "SKIP_SESSION", state)
                await asyncio.sleep(5)
                continue

            # --- Check 5: Liquidity Sweep ---
            swept, sweep_desc = check_liquidity_sweep(fvg.direction, m15)
            if not swept:
                _skip(asset, fvg.direction, "SKIP_NO_SWEEP", state)
                await asyncio.sleep(5)
                continue

            # All 5 checks passed — build context and enqueue
            ctx = DetectionContext(
                asset=asset,
                direction=fvg.direction,
                fvg=fvg,
                h1_trend=h1_trend,
                h4_context=h4_context + (f" | D1 warning: {d1_reason}" if d1_warn else ""),
                d1_warning=d1_reason if d1_warn else "",
                sweep_description=sweep_desc,
                session=session_name,
                candle_snapshot=list(m15)[-20:],
            )
            log.info(f"[{asset}] All checks passed — queuing for inference")
            await inference_queue.put(ctx)

        except Exception as e:
            log.error(f"DetectionAgent {asset} error: {e}")

        await asyncio.sleep(5)


def _skip(asset: str, direction: str, reason: str, state: SystemState) -> None:
    log.debug(f"[{asset}] {direction} skipped: {reason}")
    save_audit_event("signal_skipped", asset, reason)
