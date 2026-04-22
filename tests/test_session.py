from datetime import datetime, timezone
from detection.session import check_session


def _utc(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 1, 6, hour, minute, tzinfo=timezone.utc)  # Tuesday


def test_gold_london_session_valid():
    valid, session = check_session("XAUUSD", _utc(8, 30))
    assert valid is True
    assert session == "LONDON"


def test_gold_ny_session_valid():
    valid, session = check_session("XAUUSD", _utc(15, 0))
    assert valid is True
    assert session == "NEW_YORK"


def test_gold_off_hours_invalid():
    valid, session = check_session("XAUUSD", _utc(22, 0))
    assert valid is False
    assert session == "SKIP_SESSION"


def test_gold_asian_invalid():
    valid, session = check_session("XAUUSD", _utc(3, 0))
    assert valid is False
    assert session == "SKIP_SESSION"


def test_btc_always_valid_off_hours():
    valid, session = check_session("BTCUSDT", _utc(22, 0))
    assert valid is True
    assert session == "OFF_HOURS"


def test_btc_ny_session_labelled():
    valid, session = check_session("BTCUSDT", _utc(16, 0))
    assert valid is True
    assert session == "NEW_YORK"


def test_eth_asian_session():
    valid, session = check_session("ETHUSDT", _utc(2, 0))
    assert valid is True
    assert session == "ASIAN"
