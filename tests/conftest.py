from collections import deque
from datetime import datetime, timezone

import pytest

from models.signal import Candle


def make_candle(
    o: float, h: float, l: float, c: float,
    v: float = 1000.0,
    ts: datetime | None = None,
) -> Candle:
    return Candle(
        timestamp=ts or datetime.now(timezone.utc),
        open=o, high=h, low=l, close=c, volume=v,
    )


def make_deque(tuples: list[tuple], maxlen: int = 200) -> deque:
    """Build a deque from (o, h, l, c) or (o, h, l, c, v) tuples."""
    d = deque(maxlen=maxlen)
    for t in tuples:
        if len(t) == 4:
            d.append(make_candle(*t))
        else:
            d.append(make_candle(*t))
    return d
