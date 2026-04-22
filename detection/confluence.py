from collections import deque
from models.signal import Candle

H1_LOOKBACK = 5
H4_LOOKBACK = 10
D1_EXTREME_PCT = 0.10
D1_MIN_CANDLES = 20


def detect_trend(candles: deque, lookback: int = H1_LOOKBACK) -> str:
    """Returns 'UPTREND', 'DOWNTREND', or 'RANGING'."""
    cl = list(candles)
    if len(cl) < lookback + 1:
        return "RANGING"
    recent = cl[-lookback:]
    highs = [c.high for c in recent]
    lows = [c.low for c in recent]
    hh = all(highs[i] >= highs[i - 1] for i in range(1, len(highs)))
    hl = all(lows[i] >= lows[i - 1] for i in range(1, len(lows)))
    lh = all(highs[i] <= highs[i - 1] for i in range(1, len(highs)))
    ll = all(lows[i] <= lows[i - 1] for i in range(1, len(lows)))
    if hh and hl:
        return "UPTREND"
    if lh and ll:
        return "DOWNTREND"
    return "RANGING"


def check_h4_conflict(fvg_direction: str, fvg_equilibrium: float, h4_candles: deque) -> bool:
    """
    Returns True if FVG equilibrium sits inside an opposing H4 body cluster.
    Bullish FVG inside H4 supply (bearish bodies) = conflict.
    Bearish FVG inside H4 demand (bullish bodies) = conflict.
    """
    cl = list(h4_candles)[-H4_LOOKBACK:]
    if not cl:
        return False

    if fvg_direction == "LONG":
        for c in cl:
            if c.close < c.open:  # bearish candle = supply
                b_high = max(c.open, c.close)
                b_low = min(c.open, c.close)
                if b_low <= fvg_equilibrium <= b_high:
                    return True
    else:
        for c in cl:
            if c.close > c.open:  # bullish candle = demand
                b_high = max(c.open, c.close)
                b_low = min(c.open, c.close)
                if b_low <= fvg_equilibrium <= b_high:
                    return True
    return False


def check_d1_extreme(fvg_direction: str, fvg_equilibrium: float, d1_candles: deque) -> tuple[bool, str]:
    """
    Soft filter. Returns (is_warning, reason_str).
    Warning if equilibrium is within top/bottom 10% of D1 price range over last 50 candles.
    """
    cl = list(d1_candles)
    if len(cl) < D1_MIN_CANDLES:
        return False, ""
    period_high = max(c.high for c in cl)
    period_low = min(c.low for c in cl)
    price_range = period_high - period_low
    if price_range == 0:
        return False, ""
    if fvg_direction == "LONG" and fvg_equilibrium >= period_high - price_range * D1_EXTREME_PCT:
        return True, f"D1 resistance near {period_high:.2f}"
    if fvg_direction == "SHORT" and fvg_equilibrium <= period_low + price_range * D1_EXTREME_PCT:
        return True, f"D1 support near {period_low:.2f}"
    return False, ""
