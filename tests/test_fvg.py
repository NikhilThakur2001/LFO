from collections import deque
from tests.conftest import make_deque
from detection.fvg import detect_fvg


def test_bullish_fvg_detected():
    # c_n2.high=100, c_n.low=102 → gap exists
    candles = make_deque([(99, 100, 98, 100), (100, 105, 99, 104), (102, 106, 102, 105)])
    result = detect_fvg(candles)
    assert result is not None
    assert result.direction == "LONG"
    assert result.gap_low == 100.0
    assert result.gap_high == 102.0
    assert result.equilibrium == 101.0


def test_bearish_fvg_detected():
    # c_n2.low=100, c_n.high=98 → gap exists
    candles = make_deque([(102, 103, 100, 100), (100, 101, 96, 97), (96, 98, 95, 96)])
    result = detect_fvg(candles)
    assert result is not None
    assert result.direction == "SHORT"
    assert result.gap_high == 100.0
    assert result.gap_low == 98.0


def test_no_fvg_when_candles_overlap():
    # c_n2.high=103, c_n.low=101 → overlapping, no gap
    candles = make_deque([(99, 103, 98, 102), (102, 106, 100, 104), (101, 107, 101, 106)])
    result = detect_fvg(candles)
    assert result is None


def test_no_fvg_below_min_size():
    # Gap is 0.0001 (< 0.1% of ~100)
    candles = make_deque([(99, 100.00, 98, 100.00), (100, 105, 99, 104), (100.01, 106, 100.01, 105)])
    result = detect_fvg(candles)
    assert result is None


def test_insufficient_candles_returns_none():
    candles = make_deque([(99, 103, 98, 102)])
    result = detect_fvg(candles)
    assert result is None


def test_fvg_displacement_idx_correct():
    candles = make_deque([(99, 100, 98, 100), (100, 105, 99, 104), (102, 106, 102, 105)])
    result = detect_fvg(candles)
    assert result is not None
    assert result.displacement_candle_idx == 1  # middle candle (index 1 in 3-element deque)
