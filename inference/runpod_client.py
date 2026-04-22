"""
Sends a signal context to RunPod Serverless GPU for deep chain-of-thought reasoning.
Uses async fire-and-forget: RunPod calls back to /webhook/runpod when done.
"""
import json
import logging

import runpod

from config import Config
from models.signal import DetectionContext

log = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
You are a senior SMC/ICT trader with 10 years experience.
Analyze this potential FVG trade setup step by step.

Asset: {asset} | Direction: {direction} | Session: {session}
FVG range: {fvg_low:.5g}–{fvg_high:.5g} | Equilibrium: {eq:.5g}
H1 trend: {h1_trend}
H4 context: {h4_context}
Liquidity sweep: {sweep}
D1 warning: {d1_warning}

Recent M15 candles (O/H/L/C):
{candles_str}

Reason through these questions:
1. Is this FVG protected by a higher timeframe Order Block?
2. Does the displacement show genuine institutional intent?
3. Is this an Accumulation or Distribution Wyckoff phase?
4. Are there any confluences or conflicts I am missing?
5. Final verdict: TAKE / SKIP / MONITOR

Respond ONLY with valid JSON (no extra text, no markdown):
{{
  "verdict": "TAKE" | "SKIP" | "MONITOR",
  "confidence": <int 0-100>,
  "entry": <float>,
  "sl": <float>,
  "tp1": <float>,
  "tp2": <float>,
  "reasoning_summary": "<max 2 sentences>"
}}"""


def build_prompt(ctx: DetectionContext, entry: float, sl: float, tp1: float, tp2: float) -> str:
    candles_str = "\n".join(
        f"  {c.timestamp.strftime('%H:%M')} O={c.open:.5g} H={c.high:.5g} L={c.low:.5g} C={c.close:.5g}"
        for c in ctx.candle_snapshot[-10:]
    )
    return _PROMPT_TEMPLATE.format(
        asset=ctx.asset,
        direction=ctx.direction,
        session=ctx.session,
        fvg_low=ctx.fvg.gap_low,
        fvg_high=ctx.fvg.gap_high,
        eq=ctx.fvg.equilibrium,
        h1_trend=ctx.h1_trend,
        h4_context=ctx.h4_context,
        sweep=ctx.sweep_description,
        d1_warning=ctx.d1_warning or "None",
        candles_str=candles_str,
        entry=entry,
        sl=sl,
        tp1=tp1,
        tp2=tp2,
    )


def dispatch_to_runpod(
    signal_id: str,
    ctx: DetectionContext,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
    config: Config,
) -> str:
    """
    Fire-and-forget. Returns RunPod job_id (used as signal_id match in webhook).
    RunPod will POST result to VPS_WEBHOOK_URL/webhook/runpod.
    """
    runpod.api_key = config.runpod_api_key
    endpoint = runpod.Endpoint(config.runpod_endpoint_id)
    prompt = build_prompt(ctx, entry, sl, tp1, tp2)
    job = endpoint.run(
        {
            "input": {
                "signal_id": signal_id,
                "prompt": prompt,
            }
        },
        webhook=f"{config.vps_webhook_url}/webhook/runpod",
    )
    log.info(f"Dispatched to RunPod: job={job.job_id} signal={signal_id}")
    return job.job_id
