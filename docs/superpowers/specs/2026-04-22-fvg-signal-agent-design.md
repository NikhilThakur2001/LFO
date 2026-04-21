# FVG Signal Agent — System Design Spec
**Date:** 2026-04-22
**Author:** Nikhil Thakur
**Status:** Approved

---

## 1. Project Purpose

Build a 24/7 agentic AI system that monitors XAU/USD (Gold), BTC/USDT, and ETH/USDT for high-probability Fair Value Gap (FVG) trade setups using Smart Money Concepts (SMC/ICT methodology), then sends trade alerts via Telegram and Email. **No automated execution — signal-only system.** User places trades manually after receiving alert.

The system avoids the failure modes of legacy bots:
- Multi-timeframe blindness (M15 FVG inside H4 supply zone = trap)
- Missing displacement confirmation (low-volume gaps are fakeouts)
- No liquidity sweep detection (entering before sweep = providing liquidity to institutions)
- Ignoring macro events (trading into NFP/CPI = high-slippage failure)

---

## 2. Infrastructure

### 2.1 Production (Contabo VPS)
- **Specs:** 12GB RAM, 6 vCPUs, Navi Mumbai DC (~2–15ms to Indian data sources)
- **Role:** 24/7 orchestrator — data ingestion, signal detection, news guardrail, notification dispatch, auditor
- **Runtime:** Python 3.12, PM2 for process persistence (auto-restart on crash)
- **Local LLM:** Ollama running `qwen2.5:1.5b` on CPU for fast signal screening

### 2.2 On-Demand Reasoning (RunPod Serverless GPU)
- **Role:** Heavy chain-of-thought reasoning for complex setups
- **Model:** DeepSeek-R1-32B or Qwen3-32B (whichever available on RunPod)
- **Trigger:** Only when VPS fast-check scores signal complexity ≥ 6/10
- **Integration:** Async webhook — VPS sends payload, RunPod calls back, VPS dispatches notification. VPS never hangs waiting.
- **Cost control:** Result cached in-memory 30 min per zone. Same asset + same zone within 30 min = no new GPU call.
- **Target cost:** ~$13–15/month total (VPS + RunPod combined)
- **SDK:** `runpod` Python SDK with FlashBoot for sub-200ms cold starts

### 2.3 Dashboard (Vercel)
- **Role:** Read-only frontend only. No trading logic runs here.
- **Data source:** Reads from Supabase (VPS writes signal + audit records to Supabase in real-time)
- **Displays:** Live signal feed, skip log with reasons, RunPod cost tracker, per-asset signal history

### 2.4 Database (Supabase)
- **Role:** Persistent storage for signals, audit logs, user notification preferences
- **On-VPS:** SQLite as local audit log (zero RAM overhead, survives restarts, SQL-queryable for backtesting)
- **Sync:** VPS writes to SQLite first, then async-replicates to Supabase

### 2.5 Dev Environment
- **Machine:** Asus Zephyrus G14, 16GB RAM, RTX 4060 (8GB VRAM)
- **Local LLM for dev:** `deepseek-r1:8b-0528-qwen-q6_K` via Ollama (~6.6GB VRAM, fits RTX 4060)
- **Deploy flow:** Git push to repo → SSH pull on Contabo VPS → PM2 restart

---

## 3. Market Data

### 3.1 Source
**Delta Exchange** — single unified source for all three assets.
- **WebSocket:** Real-time tick/candle data (primary feed)
- **REST API:** Historical OHLCV backfill on startup

### 3.2 Assets & Symbols
| Asset | Delta Symbol | Type |
|-------|-------------|------|
| Gold | `XAUUSD` | Spot/Perpetual |
| Bitcoin | `BTCUSDT` | Perpetual |
| Ethereum | `ETHUSDT` | Perpetual |

### 3.3 Timeframe Buffers (in-memory, per asset)
| Timeframe | Purpose | Buffer size |
|-----------|---------|------------|
| M5 | FVG detection raw | 200 candles |
| M15 | Primary FVG timeframe | 200 candles |
| H1 | Trend direction filter | 100 candles |
| H4 | Supply/demand zone context | 100 candles |
| D1 | Macro structure | 50 candles |

All buffers stored as `deque` in `SystemState`. WebSocket updates M5/M15 live. REST API backfills H1/H4/D1 on startup and refreshes every 4h.

### 3.4 API Credentials
Stored in `.env` only — never committed to git.
```
DELTA_EXCHANGE_API_KEY=<your_key>
DELTA_EXCHANGE_API_SECRET=<your_secret>
```
Add `.env` to `.gitignore` immediately.

---

## 4. Signal Detection Pipeline

Each asset runs its own detection loop. All 5 checks must pass in sequence. Any failure → skip (log reason to SQLite) → wait for next candle close.

### Check 1: FVG Detection (M15)
**Bullish FVG:** `candle[n-2].high < candle[n].low` — gap between top of 2-back candle and bottom of current candle
**Bearish FVG:** `candle[n-2].low > candle[n].high` — inverse

- FVG must be on a **closed** M15 candle (not forming)
- Minimum gap size: 0.1% of current price (filters micro-gaps)
- FVG midpoint (`equilibrium`) = `(gap_high + gap_low) / 2` — used as limit entry level

### Check 2: Displacement Filter
The move that **created** the FVG must show institutional displacement:
- Volume of the displacement candle > 20-period volume SMA × 1.5
- Body-to-wick ratio of displacement candle > 0.6 (strong directional move, not a spike)
- If volume data unavailable (e.g., spot gold), use ATR expansion: displacement candle range > 1.5× ATR(14)

### Check 3: Multi-Timeframe Confluence
Three sub-checks, all must pass:
1. **H1 trend alignment:** Bullish FVG only valid if H1 is in uptrend (higher highs/higher lows). Bearish FVG only valid if H1 downtrend.
2. **H4 zone check:** M15 FVG must NOT sit inside an H4 supply zone (for bullish) or H4 demand zone (for bearish). If it does → `SKIP_H4_CONFLICT`.
3. **D1 macro context:** D1 must not be in opposing extreme (e.g., bullish FVG on M15 but D1 is at multi-month resistance) — soft filter, logs warning but doesn't hard-skip.

### Check 4: Session Filter
FVGs are time-sensitive. Valid session windows:
| Asset | Valid Sessions (UTC) |
|-------|---------------------|
| XAU/USD | London: 07:00–10:00, NY: 13:30–20:00 |
| BTC/ETH | 24/7 (but NY session signals weighted higher) |

Outside valid session → `SKIP_SESSION`. Signal logged but no RunPod call.

### Check 5: Liquidity Sweep Confirmation
Price must sweep **opposing liquidity** before FVG entry is valid:
- Bullish setup: price must have swept below a prior swing low (grabbed sell-side liquidity) before the FVG formed
- Bearish setup: price must have swept above a prior swing high (grabbed buy-side liquidity)
- Swing points identified from M15 chart, lookback = 20 candles
- No sweep detected → `SKIP_NO_SWEEP` — most common skip reason

**Entry level:** Limit order at FVG equilibrium (midpoint)
**Stop loss:** Below FVG low boundary (bullish) or above FVG high boundary (bearish), plus 0.1% buffer
**TP1:** 1:1 R/R from entry
**TP2:** 1:2 R/R from entry (minimum required by strategy)
**Max risk per trade:** 1% (communicated in alert, user decides position size)

---

## 5. News Guardrail (Phase 2)

Runs **before** any RunPod call. Pure CPU logic on VPS.

### 5.1 Data Source
**Finnhub API** — `/calendar/economic` endpoint
- Poll interval: every 5 minutes
- Free tier: 60 req/minute (well within budget)
- Cache results in-memory, refresh every 5 min
- `FINNHUB_API_KEY` in `.env`

### 5.2 Hard Rules
```python
# Currency mapping
ASSET_CURRENCIES = {
    'XAUUSD': ['USD'],      # Gold reacts to USD events
    'BTCUSDT': [],          # Crypto has no forex calendar — pass through
    'ETHUSDT': [],
}

# Block condition
for event in upcoming_events:
    if event['impact'] == 'High':
        if event['currency'] in asset_currencies[asset]:
            minutes_to_event = (event['time'] - now).total_seconds() / 60
            if -15 <= minutes_to_event <= 60:
                return ACTION_SKIP, f"High-impact {event['country']} {event['title']} in {minutes_to_event:.0f}min"
```

- T-60 min before event: block
- T+15 min after event: block (slippage window)
- All skips logged to SQLite with event name + asset

### 5.3 Cost Impact
Every `ACTION_SKIP` here = $0 RunPod spend. News guardrail is the primary cost control mechanism.

---

## 6. Inference Manager (Phase 3)

### 6.1 Fast Path (VPS CPU, Ollama, Qwen2.5-1.5B)
All signals that pass Phase 1+2 hit this first.

Prompt structure:
```
You are a financial analyst using ICT/SMC methodology.
Asset: {asset}, Direction: {direction}, Timeframe: M15
FVG range: {fvg_low}–{fvg_high}, Equilibrium: {eq}
H1 trend: {trend}, H4 context: {h4_context}
Liquidity sweep: {sweep_description}

Score the complexity of this setup from 0–10.
0 = textbook clean setup, 10 = highly ambiguous.
Also answer: Is this setup valid? (yes/no)
Output JSON: {"complexity": int, "valid": bool, "reason": str}
```

- Score < 6 AND valid=true → skip RunPod, go directly to notification
- Score ≥ 6 OR valid=false-but-borderline → route to RunPod
- valid=false AND score < 6 → discard, log reason

### 6.2 Heavy Path (RunPod, DeepSeek-R1-32B)
Chain-of-thought prompt (model outputs `<think>` block before answer):

```
You are a senior SMC/ICT trader with 10 years experience.
Analyze this potential FVG trade setup step by step.

[Full market context injected: candle data, volume, H1/H4/D1 structure,
 recent swing points, session, news status]

Questions to reason through:
1. Is this FVG protected by a higher timeframe Order Block?
2. Does the displacement show genuine institutional intent?
3. Is this an Accumulation or Distribution Wyckoff phase?
4. Are there any confluences or conflicts I'm missing?
5. Final verdict: TAKE / SKIP / MONITOR

Output: JSON with fields: verdict, entry, sl, tp1, tp2, confidence (0-100), reasoning_summary (2 sentences max)
```

- VPS sends HTTP POST to RunPod endpoint with payload
- RunPod webhook calls back to VPS `/webhook/runpod` endpoint
- VPS holds signal in `pending_signals` dict, matches on `signal_id`
- Timeout: 90 seconds. If RunPod doesn't respond → fall back to fast-path result
- **MONITOR verdict:** RunPod returns MONITOR when setup is valid but incomplete (e.g., sweep not yet confirmed). VPS adds signal to a 30-min watch list. If conditions complete within window → re-run fast path and dispatch. If window expires → discard, log `SKIP_MONITOR_EXPIRED`.

### 6.3 Cache
```python
# zone_key = price rounded to nearest 0.5% bucket
# e.g., XAUUSD at 2341.50 → zone_key = "2340.0"
zone_key = round(fvg_equilibrium / (price * 0.005)) * (price * 0.005)
cache_key = f"{asset}_{direction}_{zone_key}"

inference_cache: dict[str, CachedResult] = {
    cache_key: {
        "result": ReasoningResult,
        "timestamp": datetime,
        "ttl_minutes": 30
    }
}
```
Same asset + direction + price zone within 30 min → return cached result, no GPU call.

---

## 7. Notification Dispatch

### 7.1 Signal Object
```python
@dataclass
class TradeSignal:
    signal_id: str          # UUID
    asset: str              # 'XAUUSD', 'BTCUSDT', 'ETHUSDT'
    direction: str          # 'LONG' or 'SHORT'
    entry_price: float      # FVG equilibrium
    sl: float               # Stop loss level
    tp1: float              # 1:1 R/R target
    tp2: float              # 1:2 R/R target
    rr_ratio: float         # Actual R/R (always >= 2.0)
    confidence: int         # 0–100, from LLM
    reasoning_summary: str  # 2-sentence max
    session: str            # 'LONDON' | 'NEW_YORK' | 'ASIAN'
    timestamp: datetime
    inference_path: str     # 'fast' | 'runpod'
```

### 7.2 Telegram
- Library: `python-telegram-bot` async
- Format: MarkdownV2
- Target: `TELEGRAM_CHAT_ID` in `.env`

```
🔔 *FVG SIGNAL — XAUUSD LONG*

📍 Entry: `2,341.50`
🛑 Stop Loss: `2,334.20`
🎯 TP1: `2,348.80` \(1:1\)
🎯 TP2: `2,356.10` \(1:2\)

📊 Confidence: 78/100
💡 _H4 OB protected, clean sweep of 2,330 lows, NY session open_

⚠️ Risk 1% max\. Manual execution only\.
```

### 7.3 Email (Resend)
- To: `nikhil2050thakur2001@gmail.com`
- Subject: `[FVG SIGNAL] XAUUSD LONG — Entry 2341.50`
- Body: Full HTML with reasoning chain, all levels, timestamp
- Fallback: Plain text if HTML send fails
- `RESEND_API_KEY` in `.env`

### 7.4 Dispatch Logic
```python
async def dispatch(signal: TradeSignal):
    results = await asyncio.gather(
        send_telegram(signal),
        send_email(signal),
        return_exceptions=True  # one failure doesn't block other
    )
    # log both results to SQLite regardless
```

---

## 8. Auditor Agent (Supervisor)

Runs as shielded `asyncio` task. Never modifies trade logic. Read-only access to `SystemState`.

### 8.1 Responsibilities
- **Heartbeat check:** If any agent task hasn't updated its timestamp in >5 min → Telegram alert: "⚠️ [DataAgent] silent for 7min — check VPS"
- **Spam guard:** Same asset + same direction + same zone firing >2 signals in 1h → suppress and alert "Repeated signal for XAUUSD LONG at 2341 zone — suppressed"
- **RunPod cost tracker:** Estimate spend (calls × avg cost/call). If daily estimate > $2 → Telegram alert
- **Signal quality log:** Writes every signal (fired + skipped) to SQLite with full context
- **Weekly digest:** Every Sunday 09:00 UTC → Telegram summary:
  - Total signals fired
  - Top skip reasons (ranked)
  - RunPod calls vs fast-path calls
  - Estimated monthly RunPod cost

### 8.2 SQLite Schema
```sql
CREATE TABLE signals (
    id TEXT PRIMARY KEY,
    asset TEXT,
    direction TEXT,
    entry_price REAL,
    sl REAL, tp1 REAL, tp2 REAL,
    confidence INTEGER,
    inference_path TEXT,
    dispatched INTEGER,  -- 1=sent, 0=skipped
    skip_reason TEXT,
    created_at TIMESTAMP
);

CREATE TABLE audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT,     -- 'agent_silent', 'spam_suppressed', 'cost_spike', etc.
    asset TEXT,
    detail TEXT,
    created_at TIMESTAMP
);
```

---

## 9. Application Architecture (Modular AsyncIO Monolith)

### 9.1 Process Structure
```
main.py
├── asyncio.TaskGroup
│   ├── DataAgent (per asset × 3)        — WebSocket + buffer management
│   ├── DetectionAgent (per asset × 3)   — 5-check pipeline on each M15 close
│   ├── NewsAgent                         — Finnhub polling every 5 min
│   ├── InferenceManager                  — Fast path + RunPod routing
│   ├── NotificationAgent                 — Telegram + Email dispatch
│   ├── AuditorAgent                      — Supervisor, heartbeat, weekly digest
│   └── WebhookServer                     — FastAPI on port 8080, receives RunPod callbacks
└── SystemState                           — Shared in-memory state object
```

Each task wrapped in `asyncio.shield()` + individual `try/except`. TaskGroup catches unshielded crashes and restarts via PM2.

**WebhookServer networking requirement:** Contabo VPS must expose port 8080 publicly (open in VPS firewall). RunPod sends webhook callbacks to `http://<VPS_PUBLIC_IP>:8080/webhook/runpod`. Set `VPS_WEBHOOK_URL=http://<ip>:8080` in `.env` and pass this when registering RunPod endpoint. Optionally proxy via Nginx with SSL.

### 9.2 Shared State
```python
@dataclass
class SystemState:
    candle_buffers: dict[str, dict[str, deque]]  # asset → timeframe → candles
    active_signals: list[TradeSignal]
    pending_signals: dict[str, TradeSignal]       # awaiting RunPod webhook
    news_cache: list[dict]                        # Finnhub events
    inference_cache: dict[str, CachedResult]
    agent_heartbeats: dict[str, datetime]
    runpod_calls_today: int
    lock: asyncio.Lock                            # protects writes
```

### 9.3 Configuration (.env)
```
# Delta Exchange
DELTA_EXCHANGE_API_KEY=...
DELTA_EXCHANGE_API_SECRET=...

# Finnhub
FINNHUB_API_KEY=...

# RunPod
RUNPOD_API_KEY=...
RUNPOD_ENDPOINT_ID=...

# Telegram
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# Resend (Email)
RESEND_API_KEY=...
RESEND_FROM_EMAIL=alerts@yourdomain.com  # requires verified domain in Resend dashboard
# Alternative if no domain: use Resend's free onboarding address for testing

# Supabase
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...

# Ollama (local fast model)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_FAST_MODEL=qwen2.5:1.5b

# Thresholds
COMPLEXITY_THRESHOLD=6
RUNPOD_DAILY_BUDGET_USD=2.0
MAX_DAILY_DRAWDOWN_OVERRIDE=false  # hard-coded off — AI cannot override
```

---

## 10. Key Design Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Modular AsyncIO monolith over Docker microservices | 12GB VPS RAM preserved for Ollama. Simpler debugging. PM2 handles restarts. Sufficient for 20–50 alerts/day. |
| SQLite on VPS + Supabase sync | SQLite = zero RAM, instant writes, backtestable. Supabase = Vercel dashboard + persistence across VPS rebuilds. |
| Two-tier inference (Qwen1.5B → DeepSeek-R1-32B) | Fast path handles textbook setups at $0. RunPod only for ambiguous ones. Keeps monthly GPU cost < $5. |
| Async RunPod webhook, not polling | VPS never blocks. Signal pipeline continues while GPU reasons. |
| Signal-only, no execution | User requested. Eliminates exchange permission complexity, regulatory risk, and runaway bot risk entirely. |
| Liquidity sweep as final entry gate | Primary edge from the article's research — most bots miss this. Prevents entering before institutional move. |
| News guardrail before RunPod call | Every skipped GPU call saves money. High-impact events block on CPU before any heavy inference. |
| `MAX_DAILY_DRAWDOWN_OVERRIDE=false` hard-coded | AI cannot change this. Safety feature from article's research — one of the "what worked" items. |

---

## 11. What This System Does NOT Do
- Execute trades automatically
- Manage positions or move stops
- Connect to any brokerage for order placement
- Guarantee profitable signals (past performance ≠ future results)

---

## 12. Dependencies (Python packages)
```
delta-rest-client       # Delta Exchange REST
websockets              # Delta Exchange WebSocket
finnhub-python          # Finnhub economic calendar
ollama                  # Local LLM fast path
runpod                  # RunPod serverless GPU
python-telegram-bot     # Telegram alerts
resend                  # Email alerts
supabase                # Database sync
fastapi                 # Webhook server (RunPod callbacks)
uvicorn                 # FastAPI server
sqlalchemy              # SQLite ORM
python-dotenv           # .env management
```

---

## 13. Paper Trading Mode
Before live signal deployment: run in `PAPER_MODE=true` for minimum 14 days.
- All signals generated and logged to SQLite
- NO Telegram/Email sent
- Auditor tracks would-be performance
- After 14 days: review SQLite, check win rate, skip rate, cost estimate
- Only enable live notifications after review
