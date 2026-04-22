from tests.conftest import make_deque
from detection.confluence import detect_trend, check_h4_conflict, check_d1_extreme


def test_uptrend_detected():
    # Strictly rising highs and lows
    candles = make_deque([(i*1.0, i+1.0, i-0.5, i+0.5) for i in range(100, 110)])
    assert detect_trend(candles) == "UPTREND"


def test_downtrend_detected():
    candles = make_deque([(i*1.0, i+0.5, i-1.0, i-0.5) for i in range(110, 100, -1)])
    assert detect_trend(candles) == "DOWNTREND"


def test_ranging_detected():
    # Alternating
    candles = make_deque([(100, 103, 97, 101), (101, 104, 98, 100), (100, 103, 97, 101)])
    assert detect_trend(candles) == "RANGING"


def test_h4_conflict_bullish_in_supply():
    # Bearish H4 candles (open > close) with body covering equilibrium 100
    h4 = make_deque([(102, 103, 98, 99)] * 5)  # bearish body 99–102 covers 100
    assert check_h4_conflict("LONG", 100.0, h4) is True


def test_no_h4_conflict_bullish_below_supply():
    # Bearish bodies at 200–210, equilibrium at 100 — no conflict
    h4 = make_deque([(210, 215, 205, 200)] * 5)
    assert check_h4_conflict("LONG", 100.0, h4) is False


def test_d1_extreme_resistance_warning_long():
    # Price range 1000–2000, equilibrium at 1950 (top 5%)
    d1 = make_deque([(i*10.0, i*10+5, i*10-5, i*10) for i in range(100, 200)])
    # period_high ≈ 1995, period_low ≈ 995, range=1000
    # top 10% threshold = 1995 - 100 = 1895; equilibrium 1950 > 1895
    warn, reason = check_d1_extreme("LONG", 1950.0, d1)
    assert warn is True
    assert "resistance" in reason.lower()


def test_d1_no_warning_mid_range():
    d1 = make_deque([(i*10.0, i*10+5, i*10-5, i*10) for i in range(100, 200)])
    warn, _ = check_d1_extreme("LONG", 1500.0, d1)
    assert warn is False
