from collections import deque
from models.signal import Candle

VOLUME_MULTIPLIER = 1.5
BODY_WICK_RATIO = 0.6
ATR_MULTIPLIER = 1.5
MIN_VOL_PERIODS = 5


def _atr(candles: list[Candle], period: int = 14) -> float:
    ranges = [c.high - c.low for c in candles[-period:]]
    return sum(ranges) / len(ranges) if ranges else 0.0


def check_displacement(candles: deque, displacement_idx: int, has_volume: bool = True) -> bool:
    """
    Validate that the displacement candle shows institutional intent.
    displacement_idx: absolute index into candles deque.
    has_volume: False for spot gold (use ATR fallback).
    """
    candle_list = list(candles)
    if displacement_idx < 0 or displacement_idx >= len(candle_list):
        return False

    disp = candle_list[displacement_idx]

    # --- Volume or ATR check ---
    pre = candle_list[:displacement_idx]
    if has_volume:
        if len(pre) < MIN_VOL_PERIODS:
            return False
        vol_sma = sum(c.volume for c in pre[-20:]) / min(len(pre), 20)
        if disp.volume < vol_sma * VOLUME_MULTIPLIER:
            return False
    else:
        if not pre:
            return False
        atr = _atr(pre)
        if atr == 0 or (disp.high - disp.low) < atr * ATR_MULTIPLIER:
            return False

    # --- Body-to-wick ratio ---
    total_range = disp.high - disp.low
    if total_range == 0:
        return False
    body = abs(disp.close - disp.open)
    if body / total_range < BODY_WICK_RATIO:
        return False

    return True
