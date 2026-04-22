from tests.conftest import make_deque, make_candle
from detection.displacement import check_displacement


def _make_high_vol_deque():
    """20 candles with volume=100, then a displacement candle with volume=200."""
    tuples = [(100, 102, 99, 101, 100.0)] * 20
    d = make_deque(tuples)
    # displacement candle at index 20
    d.append(make_candle(101, 106, 101, 106, v=200.0))  # strong bullish body
    return d, len(d) - 1


def test_valid_displacement_passes():
    d, idx = _make_high_vol_deque()
    assert check_displacement(d, idx, has_volume=True) is True


def test_low_volume_fails():
    tuples = [(100, 102, 99, 101, 100.0)] * 20
    d = make_deque(tuples)
    d.append(make_candle(101, 106, 101, 106, v=50.0))  # volume below threshold
    assert check_displacement(d, len(d) - 1, has_volume=True) is False


def test_weak_body_ratio_fails():
    tuples = [(100, 102, 99, 101, 100.0)] * 20
    d = make_deque(tuples)
    # Long wick: body=1, total range=10 → ratio=0.1 < 0.6
    d.append(make_candle(100, 110, 99, 101, v=300.0))
    assert check_displacement(d, len(d) - 1, has_volume=True) is False


def test_atr_fallback_passes_for_gold():
    # ATR ≈ 3.0 per bar; displacement range = 6.0 > 3.0 × 1.5 = 4.5
    tuples = [(100, 103, 97, 100, 0.0)] * 15  # range=6 each
    d = make_deque(tuples)
    d.append(make_candle(100, 106, 100, 106, v=0.0))  # body=6, range=6
    assert check_displacement(d, len(d) - 1, has_volume=False) is True


def test_returns_false_on_bad_index():
    d = make_deque([(100, 102, 99, 101)] * 5)
    assert check_displacement(d, 999, has_volume=True) is False
