from datetime import datetime, timezone, time

CRYPTO_ASSETS = {"BTCUSDT", "ETHUSDT"}

_LONDON_START = time(7, 0)
_LONDON_END = time(10, 0)
_NY_START = time(13, 30)
_NY_END = time(20, 0)
_ASIAN_END = time(5, 0)


def check_session(asset: str, dt: datetime) -> tuple[bool, str]:
    """
    Returns (is_valid, session_name).
    Gold: only London and NY sessions are valid.
    Crypto: always valid, but session name is labelled for signal weighting.
    """
    utc = dt.astimezone(timezone.utc).time()

    if _NY_START <= utc <= _NY_END:
        session = "NEW_YORK"
    elif _LONDON_START <= utc <= _LONDON_END:
        session = "LONDON"
    elif utc <= _ASIAN_END:
        session = "ASIAN"
    else:
        session = "OFF_HOURS"

    if asset in CRYPTO_ASSETS:
        return True, session

    # Gold: hard restrict to London and NY
    if session in ("NEW_YORK", "LONDON"):
        return True, session
    return False, "SKIP_SESSION"
