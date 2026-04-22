"""
Fast inference via local Ollama (Qwen2.5-1.5B).
Returns complexity score + validity for routing decision.
"""
import json
import logging

import ollama

from config import Config
from models.signal import DetectionContext

log = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
You are a financial analyst using ICT/SMC methodology.
Asset: {asset}, Direction: {direction}, Timeframe: M15
FVG range: {fvg_low:.5g}–{fvg_high:.5g}, Equilibrium: {eq:.5g}
H1 trend: {h1_trend}, H4 context: {h4_context}
Liquidity sweep: {sweep}
D1 warning: {d1_warning}

Score the complexity of this setup from 0 to 10.
0 = textbook clean setup, 10 = highly ambiguous or conflicting signals.
Also answer: Is this setup valid? (yes/no)

Respond ONLY with valid JSON, no extra text:
{{"complexity": <int 0-10>, "valid": <true|false>, "reason": "<one sentence>"}}"""


def run_fast_path(ctx: DetectionContext, config: Config) -> dict:
    """
    Returns dict with keys: complexity (int), valid (bool), reason (str).
    On any error returns complexity=10, valid=False so it routes to RunPod.
    """
    prompt = _PROMPT_TEMPLATE.format(
        asset=ctx.asset,
        direction=ctx.direction,
        fvg_low=ctx.fvg.gap_low,
        fvg_high=ctx.fvg.gap_high,
        eq=ctx.fvg.equilibrium,
        h1_trend=ctx.h1_trend,
        h4_context=ctx.h4_context,
        sweep=ctx.sweep_description,
        d1_warning=ctx.d1_warning or "None",
    )
    try:
        response = ollama.chat(
            model=config.ollama_fast_model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1},
        )
        raw = response["message"]["content"].strip()
        # Strip markdown code fences if model wraps in ```json
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as e:
        log.error(f"FastPath error: {e}")
        return {"complexity": 10, "valid": False, "reason": f"fast_path_error: {e}"}
