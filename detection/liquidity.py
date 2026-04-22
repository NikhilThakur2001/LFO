from collections import deque
from models.signal import Candle

SWING_LOOKBACK = 20


def _find_swing_points(candles: list[Candle]) -> tuple[list[float], list[float]]:
    """Identify swing highs and lows via simple 3-bar pattern."""
    highs, lows = [], []
    for i in range(1, len(candles) - 1):
        if candles[i].high > candles[i - 1].high and candles[i].high > candles[i + 1].high:
            highs.append(candles[i].high)
        if candles[i].low < candles[i - 1].low and candles[i].low < candles[i + 1].low:
            lows.append(candles[i].low)
    return highs, lows


def check_liquidity_sweep(fvg_direction: str, candles: deque) -> tuple[bool, str]:
    """
    Confirm price swept opposing liquidity before the FVG formed.
    The displacement candle is candles[-2]; sweep must occur at or before it.
    Returns (swept, description).
    """
    cl = list(candles)
    # Swing points are found on candles before the displacement candle
    pre_fvg = cl[:-2]
    if len(pre_fvg) < 3:
        return False, ""

    swing_highs, swing_lows = _find_swing_points(pre_fvg[-SWING_LOOKBACK:])
    displacement = cl[-2]

    if fvg_direction == "LONG":
        # Need displacement candle to dip below a prior swing low (sell-side sweep)
        if not swing_lows:
            return False, ""
        nearest_low = min(swing_lows, key=lambda x: abs(x - displacement.low))
        if displacement.low < nearest_low:
            return True, f"Swept sell-side liquidity at {nearest_low:.5g}"
        return False, ""

    # SHORT: need displacement candle to spike above a prior swing high (buy-side sweep)
    if not swing_highs:
        return False, ""
    nearest_high = max(swing_highs, key=lambda x: abs(x - displacement.high))
    if displacement.high > nearest_high:
        return True, f"Swept buy-side liquidity at {nearest_high:.5g}"
    return False, ""
