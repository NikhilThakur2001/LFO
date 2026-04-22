from collections import deque
from models.signal import Candle, FVGResult

MIN_GAP_PERCENT = 0.001  # 0.1% of price


def detect_fvg(candles: deque) -> FVGResult | None:
    """
    Scan last 3 closed M15 candles for FVG pattern.
    candles[-3] = n-2 (before gap)
    candles[-2] = n-1 (displacement candle)
    candles[-1] = n   (current closed candle)
    """
    if len(candles) < 3:
        return None

    c_n2: Candle = candles[-3]
    c_n1: Candle = candles[-2]   # noqa: F841 — displacement candle, used by caller
    c_n: Candle = candles[-1]

    current_price = c_n.close
    min_gap = current_price * MIN_GAP_PERCENT

    # Bullish FVG: top of c_n2 < bottom of c_n
    if c_n2.high < c_n.low:
        gap_high = c_n.low
        gap_low = c_n2.high
        if gap_high - gap_low >= min_gap:
            return FVGResult(
                detected=True,
                direction="LONG",
                gap_high=gap_high,
                gap_low=gap_low,
                equilibrium=(gap_high + gap_low) / 2,
                displacement_candle_idx=len(candles) - 2,
            )

    # Bearish FVG: bottom of c_n2 > top of c_n
    if c_n2.low > c_n.high:
        gap_high = c_n2.low
        gap_low = c_n.high
        if gap_high - gap_low >= min_gap:
            return FVGResult(
                detected=True,
                direction="SHORT",
                gap_high=gap_high,
                gap_low=gap_low,
                equilibrium=(gap_high + gap_low) / 2,
                displacement_candle_idx=len(candles) - 2,
            )

    return None
