from tests.conftest import make_deque, make_candle
from detection.liquidity import check_liquidity_sweep


def _build_deque_with_sweep(fvg_direction: str):
    """
    Build a 25-candle deque that has a valid liquidity sweep.
    For LONG: create a swing low at 98, then displacement dips to 97.5.
    For SHORT: create a swing high at 103, then displacement spikes to 103.5.
    """
    d = make_deque([(100, 102, 99, 101)] * 10)

    if fvg_direction == "LONG":
        # Create a swing low: surrounding candles higher
        d.append(make_candle(101, 102, 99, 100))  # higher low
        d.append(make_candle(100, 101, 98, 99))   # swing low at 98
        d.append(make_candle(99, 102, 99, 101))   # higher low
        # Filler candles
        for _ in range(7):
            d.append(make_candle(100, 102, 99, 101))
        # Displacement candle sweeps below swing low (97.5 < 98)
        d.append(make_candle(99, 102, 97.5, 101, v=2000))
        # Current candle
        d.append(make_candle(102, 105, 102, 104))
    else:
        d.append(make_candle(100, 101, 98, 99))
        d.append(make_candle(101, 103, 100, 102))  # swing high at 103
        d.append(make_candle(102, 102, 99, 100))
        for _ in range(7):
            d.append(make_candle(100, 102, 99, 101))
        d.append(make_candle(101, 103.5, 99, 100, v=2000))  # sweeps above 103
        d.append(make_candle(99, 101, 96, 97))
    return d


def test_bullish_sweep_detected():
    d = _build_deque_with_sweep("LONG")
    swept, desc = check_liquidity_sweep("LONG", d)
    assert swept is True
    assert "sell-side" in desc.lower()


def test_bearish_sweep_detected():
    d = _build_deque_with_sweep("SHORT")
    swept, desc = check_liquidity_sweep("SHORT", d)
    assert swept is True
    assert "buy-side" in desc.lower()


def test_no_sweep_when_displacement_stays_above_low():
    # Displacement candle low=99.5, swing low=98 → 99.5 > 98, no sweep
    d = make_deque([(100, 102, 99, 101)] * 10)
    d.append(make_candle(101, 102, 99, 100))
    d.append(make_candle(100, 101, 98, 99))   # swing low at 98
    d.append(make_candle(99, 102, 99, 101))
    for _ in range(7):
        d.append(make_candle(100, 102, 99, 101))
    d.append(make_candle(100, 103, 99.5, 102))  # displacement low=99.5 > 98
    d.append(make_candle(102, 105, 102, 104))
    swept, _ = check_liquidity_sweep("LONG", d)
    assert swept is False


def test_insufficient_candles_returns_false():
    d = make_deque([(100, 102, 99, 101)] * 2)
    swept, _ = check_liquidity_sweep("LONG", d)
    assert swept is False
