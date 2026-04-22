import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from models.signal import Candle, TradeSignal, CachedResult

ASSETS = ["XAUUSD", "BTCUSDT", "ETHUSDT"]
TIMEFRAMES = ["M5", "M15", "H1", "H4", "D1"]
BUFFER_SIZES = {"M5": 200, "M15": 200, "H1": 100, "H4": 100, "D1": 50}


@dataclass
class SystemState:
    candle_buffers: dict = field(default_factory=dict)
    active_signals: list = field(default_factory=list)
    # signal_id → TradeSignal, awaiting RunPod webhook callback
    pending_signals: dict = field(default_factory=dict)
    # signal_id → (TradeSignal, expires_at datetime), in MONITOR watch-list
    monitor_signals: dict = field(default_factory=dict)
    news_cache: list = field(default_factory=list)
    # cache_key → CachedResult
    inference_cache: dict = field(default_factory=dict)
    # agent_name → last heartbeat datetime
    agent_heartbeats: dict = field(default_factory=dict)
    runpod_calls_today: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        for asset in ASSETS:
            self.candle_buffers[asset] = {
                tf: deque(maxlen=BUFFER_SIZES[tf]) for tf in TIMEFRAMES
            }

    def beat(self, agent_name: str) -> None:
        self.agent_heartbeats[agent_name] = datetime.utcnow()

    def get_candles(self, asset: str, timeframe: str) -> deque:
        return self.candle_buffers[asset][timeframe]

    def push_candle(self, asset: str, timeframe: str, candle: Candle) -> None:
        self.candle_buffers[asset][timeframe].append(candle)
