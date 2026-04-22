"""
Reads DetectionContext from inference_queue.
Phase 2: news guardrail.
Phase 3: fast path → RunPod routing + result cache.
Puts TradeSignal into notification_queue when verdict=TAKE.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from config import Config
from agents.news_agent import check_news_clear
from db.repository import save_audit_event
from detection.confluence import detect_trend
from inference.fast_path import run_fast_path
from inference.runpod_client import dispatch_to_runpod
from models.signal import CachedResult, DetectionContext, TradeSignal
from state import SystemState

log = logging.getLogger(__name__)

CACHE_TTL_MIN = 30
MONITOR_TTL_MIN = 30
AVG_RUNPOD_COST_USD = 0.02  # ~$0.02 per call estimate


def _zone_key(asset: str, direction: str, price: float) -> str:
    bucket = round(price / (price * 0.005)) * (price * 0.005)
    return f"{asset}_{direction}_{bucket:.5g}"


def _compute_levels(eq: float, gap_low: float, gap_high: float, direction: str) -> tuple:
    buffer = eq * 0.001
    if direction == "LONG":
        sl = gap_low - buffer
        risk = eq - sl
    else:
        sl = gap_high + buffer
        risk = sl - eq
    tp1 = eq + risk if direction == "LONG" else eq - risk
    tp2 = eq + 2 * risk if direction == "LONG" else eq - 2 * risk
    return sl, tp1, tp2, 2.0


def _get_cached(key: str, state: SystemState) -> CachedResult | None:
    cached = state.inference_cache.get(key)
    if not cached:
        return None
    age = (datetime.utcnow() - cached.cached_at).total_seconds() / 60
    if age > CACHE_TTL_MIN:
        del state.inference_cache[key]
        return None
    return cached


def _store_cache(key: str, result: CachedResult, state: SystemState) -> None:
    state.inference_cache[key] = result


def _build_signal(ctx: DetectionContext, result: CachedResult, path: str) -> TradeSignal:
    return TradeSignal(
        signal_id=str(uuid.uuid4()),
        asset=ctx.asset,
        direction=ctx.direction,
        entry_price=result.entry,
        sl=result.sl,
        tp1=result.tp1,
        tp2=result.tp2,
        rr_ratio=2.0,
        confidence=result.confidence,
        reasoning_summary=result.reasoning_summary,
        session=ctx.session,
        timestamp=datetime.now(timezone.utc),
        inference_path=path,
    )


async def run_inference_manager(
    state: SystemState,
    config: Config,
    inference_queue: asyncio.Queue,
    notification_queue: asyncio.Queue,
) -> None:
    while True:
        try:
            ctx: DetectionContext = await asyncio.wait_for(inference_queue.get(), timeout=10)
            state.beat("InferenceManager")
            await _process(ctx, state, config, notification_queue)
        except asyncio.TimeoutError:
            # Check MONITOR watch-list for expired or completable signals
            await _check_monitor_list(state, config, notification_queue)
        except Exception as e:
            log.error(f"InferenceManager error: {e}")


async def _process(
    ctx: DetectionContext,
    state: SystemState,
    config: Config,
    notification_queue: asyncio.Queue,
) -> None:
    # --- Phase 2: News guardrail ---
    clear, reason = check_news_clear(ctx.asset, state)
    if not clear:
        log.info(f"[{ctx.asset}] News skip: {reason}")
        return

    sl, tp1, tp2, rr = _compute_levels(
        ctx.fvg.equilibrium, ctx.fvg.gap_low, ctx.fvg.gap_high, ctx.direction
    )
    cache_key = _zone_key(ctx.asset, ctx.direction, ctx.fvg.equilibrium)

    # --- Cache hit? ---
    cached = _get_cached(cache_key, state)
    if cached:
        log.info(f"[{ctx.asset}] Cache hit: {cache_key}")
        if cached.verdict == "TAKE":
            await notification_queue.put(_build_signal(ctx, cached, "cache"))
        return

    # --- Phase 3a: Fast path ---
    fast = await asyncio.to_thread(run_fast_path, ctx, config)
    complexity: int = fast.get("complexity", 10)
    valid: bool = fast.get("valid", False)

    if not valid and complexity < config.complexity_threshold:
        log.info(f"[{ctx.asset}] Fast path rejected: {fast.get('reason')}")
        save_audit_event("fast_skip", ctx.asset, fast.get("reason", ""))
        return

    if valid and complexity < config.complexity_threshold:
        # Clean setup — dispatch directly without RunPod
        result = CachedResult(
            verdict="TAKE",
            confidence=70,
            reasoning_summary=fast.get("reason", "Fast-path approved."),
            entry=ctx.fvg.equilibrium,
            sl=sl, tp1=tp1, tp2=tp2,
            cached_at=datetime.utcnow(),
        )
        _store_cache(cache_key, result, state)
        await notification_queue.put(_build_signal(ctx, result, "fast"))
        return

    # --- Phase 3b: Heavy path (RunPod) ---
    budget_ok = (
        state.runpod_calls_today * AVG_RUNPOD_COST_USD < config.runpod_daily_budget_usd
    )
    if not budget_ok:
        log.warning(f"[{ctx.asset}] RunPod daily budget exceeded — skipping heavy path")
        save_audit_event("budget_skip", ctx.asset, "RunPod daily budget exceeded")
        return

    signal_id = str(uuid.uuid4())
    try:
        job_id = await asyncio.to_thread(
            dispatch_to_runpod, signal_id, ctx, ctx.fvg.equilibrium, sl, tp1, tp2, config
        )
        async with state.lock:
            state.pending_signals[job_id] = TradeSignal(
                signal_id=signal_id,
                asset=ctx.asset,
                direction=ctx.direction,
                entry_price=ctx.fvg.equilibrium,
                sl=sl, tp1=tp1, tp2=tp2, rr_ratio=rr,
                confidence=0,
                reasoning_summary="",
                session=ctx.session,
                timestamp=datetime.now(timezone.utc),
                inference_path="runpod",
            )
            state.runpod_calls_today += 1
        log.info(f"[{ctx.asset}] Sent to RunPod job={job_id}")
    except Exception as e:
        log.error(f"RunPod dispatch failed: {e}")


async def _check_monitor_list(
    state: SystemState,
    config: Config,
    notification_queue: asyncio.Queue,
) -> None:
    now = datetime.utcnow()
    expired = [
        sid for sid, (_, exp) in state.monitor_signals.items() if now > exp
    ]
    for sid in expired:
        _, _ = state.monitor_signals.pop(sid)
        save_audit_event("monitor_expired", "", f"signal_id={sid}")
        log.debug(f"MONITOR signal expired: {sid}")
