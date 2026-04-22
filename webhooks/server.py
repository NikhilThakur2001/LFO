"""
FastAPI server on port 8080.
Receives RunPod async webhook callbacks and resolves pending signals.
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request, HTTPException
from models.signal import CachedResult, TradeSignal

log = logging.getLogger(__name__)

app = FastAPI(title="FVG Agent Webhook")

# Injected at startup by main.py
_state = None
_notification_queue: asyncio.Queue | None = None


def init_webhook(state, notification_queue: asyncio.Queue) -> None:
    global _state, _notification_queue
    _state = state
    _notification_queue = notification_queue


@app.post("/webhook/runpod")
async def runpod_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    job_id = data.get("id")
    status = data.get("status")

    if not job_id:
        raise HTTPException(status_code=400, detail="Missing job id")

    log.info(f"RunPod webhook: job={job_id} status={status}")

    if status != "COMPLETED":
        log.warning(f"RunPod job {job_id} non-complete status: {status}")
        return {"ok": True}

    # Match job_id to pending signal
    signal: TradeSignal | None = None
    async with _state.lock:
        signal = _state.pending_signals.pop(job_id, None)

    if not signal:
        log.warning(f"No pending signal for RunPod job {job_id}")
        return {"ok": True}

    output = data.get("output", {})
    if isinstance(output, str):
        try:
            output = json.loads(output)
        except Exception:
            log.error(f"RunPod output not parseable: {output}")
            return {"ok": True}

    verdict = output.get("verdict", "SKIP")
    confidence = int(output.get("confidence", 0))
    reasoning = output.get("reasoning_summary", "")
    entry = float(output.get("entry", signal.entry_price))
    sl = float(output.get("sl", signal.sl))
    tp1 = float(output.get("tp1", signal.tp1))
    tp2 = float(output.get("tp2", signal.tp2))

    if verdict == "TAKE":
        updated = TradeSignal(
            signal_id=signal.signal_id,
            asset=signal.asset,
            direction=signal.direction,
            entry_price=entry,
            sl=sl, tp1=tp1, tp2=tp2,
            rr_ratio=signal.rr_ratio,
            confidence=confidence,
            reasoning_summary=reasoning,
            session=signal.session,
            timestamp=datetime.now(timezone.utc),
            inference_path="runpod",
        )
        await _notification_queue.put(updated)
        log.info(f"RunPod TAKE: {signal.asset} {signal.direction} queued for dispatch")

    elif verdict == "MONITOR":
        expires = datetime.utcnow() + timedelta(minutes=30)
        async with _state.lock:
            _state.monitor_signals[signal.signal_id] = (signal, expires)
        log.info(f"RunPod MONITOR: {signal.asset} on watch until {expires}")

    else:
        log.info(f"RunPod SKIP: {signal.asset} — {reasoning}")

    return {"ok": True}


@app.get("/health")
async def health():
    return {"status": "ok"}
