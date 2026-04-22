"""
Connects to Delta Exchange WebSocket for real-time M5/M15 candles per asset.
Backfills H1/H4/D1 via REST on startup, refreshes every 4h.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

import httpx
import websockets

from config import Config
from models.signal import Candle
from state import SystemState

log = logging.getLogger(__name__)

WS_URL = "wss://socket.delta.exchange"
REST_URL = "https://api.delta.exchange"

# Delta Exchange resolution strings
TF_RESOLUTION = {"M5": "5m", "M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}
# Timeframes fetched via REST (too slow to stream)
REST_TIMEFRAMES = ["H1", "H4", "D1"]
# Timeframes subscribed via WebSocket
WS_TIMEFRAMES = ["M5", "M15"]


def _parse_candle(data: dict) -> Candle:
    return Candle(
        timestamp=datetime.fromtimestamp(int(data["time"]), tz=timezone.utc),
        open=float(data["open"]),
        high=float(data["high"]),
        low=float(data["low"]),
        close=float(data["close"]),
        volume=float(data.get("volume", 0)),
        is_closed=True,
    )


async def _backfill_rest(asset: str, state: SystemState, config: Config) -> None:
    """Fetch historical candles for H1/H4/D1 via REST API."""
    async with httpx.AsyncClient(base_url=REST_URL, timeout=30) as client:
        for tf in REST_TIMEFRAMES:
            resolution = TF_RESOLUTION[tf]
            buf_size = state.get_candles(asset, tf).maxlen or 100
            try:
                resp = await client.get(
                    "/v2/history/candles",
                    params={"resolution": resolution, "symbol": asset, "limit": buf_size},
                    headers={"api-key": config.delta_api_key},
                )
                resp.raise_for_status()
                candles_data = resp.json().get("result", [])
                for raw in sorted(candles_data, key=lambda x: x["time"]):
                    state.push_candle(asset, tf, _parse_candle(raw))
                log.info(f"Backfilled {len(candles_data)} {tf} candles for {asset}")
            except Exception as e:
                log.error(f"REST backfill failed {asset}/{tf}: {e}")


async def run_data_agent(asset: str, state: SystemState, config: Config) -> None:
    """Main data agent loop for one asset."""
    await _backfill_rest(asset, state, config)

    while True:
        try:
            async with websockets.connect(WS_URL) as ws:
                # Subscribe to M5 and M15 candlestick channels
                channels = [
                    {"name": f"candlestick_{TF_RESOLUTION[tf]}", "symbols": [asset]}
                    for tf in WS_TIMEFRAMES
                ]
                await ws.send(json.dumps({"type": "subscribe", "payload": {"channels": channels}}))
                log.info(f"DataAgent subscribed: {asset} M5/M15")

                refresh_counter = 0
                async for raw_msg in ws:
                    state.beat(f"DataAgent:{asset}")
                    msg = json.loads(raw_msg)
                    msg_type = msg.get("type", "")

                    # Identify timeframe from message type, e.g. "candlestick_5m"
                    for tf, res in TF_RESOLUTION.items():
                        if msg_type == f"candlestick_{res}" and tf in WS_TIMEFRAMES:
                            candle = _parse_candle(msg.get("data", {}))
                            if candle.is_closed:
                                async with state.lock:
                                    state.push_candle(asset, tf, candle)
                            break

                    # Refresh higher-TF candles every ~4h (approx 48 M5 candles)
                    refresh_counter += 1
                    if refresh_counter >= 48 * 4:
                        await _backfill_rest(asset, state, config)
                        refresh_counter = 0

        except Exception as e:
            log.error(f"DataAgent {asset} WebSocket error: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)
