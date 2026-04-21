# FVG AI Trading Agent — Project Context

## Source Article
**Title:** "I Lost $12,400 Testing FVG Strategies Before Finding This AI Agent—The 2026 Truth"
**Author:** Kimberlygreenthomasaviqu | Mar 8, 2026

## Core Problem Being Solved
Standard Pine Script bots and legacy platforms (Cryptohopper, 3Commas) fail at FVG trading because:
- No volume/displacement confirmation — treat every gap as an entry
- Single-timeframe blindness — M15 FVG inside H4 supply zone = trap
- No context awareness — gap in trending market ≠ gap in ranging market
- Static logic — no understanding of session timing (10AM NY ≠ 6PM NY)
- No liquidity sweep detection — bots provide liquidity TO institutions

## Key Trading Concepts Required
- **Fair Value Gap (FVG):** Price imbalance between candles — objective but context-dependent
- **Liquidity Sweep:** Price sweeps opposing liquidity before true move
- **Market Structure Shift (MSS):** Signals trend change — used for dynamic exits
- **Order Block (OB):** Institutional supply/demand zone — protects or invalidates FVG
- **Displacement:** High-volume/momentum move that creates the gap (fakeout if absent)
- **Wyckoff Accumulation/Distribution:** Macro phase context for entries
- **ICT/SMC framework:** Inner Circle Trader / Smart Money Concepts methodology

## What Worked (From Article)
- FVG + Wyckoff Accumulation pattern confluence
- Real-time forex news reading (NFP, CPI, Fed)
- Hard-coded max daily drawdown AI cannot override
- Transformer-based architecture analyzing order flow + FVG
- Chain-of-thought reasoning: "Is FVG protected by higher TF order block?"
- Liquidity sweep confirmation BEFORE entry
- MSS-based trailing stops (not arbitrary %)

## What Failed
- Standalone FVG indicators without volume confirmation
- Grid bots in trending markets
- Black-box bots without trade logic explanation
- Single-timeframe analysis

## Pseudocode Entry Logic (From Article)
```python
if price.created_gap(m15) and market.is_trending(h1):
    if volume > volume.average(20) * 1.5:
        agent.analyze_liquidity_sweep(target='external')
        if agent.sentiment == 'Bullish':
            execute_limit_entry(level=fvg.equilibrium, risk=0.01)
            set_stop_loss(below=fvg.low_boundary)
```

## Phased Entry Logic
- **Phase 1 — Filtered Entry:** Identify FVG, wait for liquidity sweep of opposing side
- **Phase 2 — Narrative Alignment:** Check high-impact macro events (no trading into Fed/NFP)
- **Phase 3 — Dynamic Exit:** Trail stop based on MSS, not fixed %

## Performance Benchmarks (Article Claims)
- Win rate with chain-of-thought logic gate: 38% → 62% in Accumulation/Distribution zones
- Test: $20k split among 5 platforms, 180 days, NFP/CPI/crypto volatility
- Parameters: 1:2 min R/R, 1% max risk per trade, zero manual interference
- Cryptohopper: 12 FVG trades, lost $1,100 in 30 days
- Legacy bots: liquidated within 45 days

## Notification Requirement
When agent identifies valid entry:
- **Email** with: entry price, SL level, targets (TP1, TP2), reasoning summary
- **SMS/text** with: same trade details
- User places trade manually (signal-only, not auto-execute — to be confirmed)

## Supervisor Agent Concept ("Auditor")
- Bird's-eye view of all sub-agents
- Contextual awareness like senior financial analyst
- Maintains running P&L context
- Flags when agents disagree or context shifts
- Keeps trade log and performance metrics

## LLM References in Article
- DeepSeek R1 integration
- GPT-4 integration
- Transformer-based order flow analysis
- Chain-of-thought (CoT) reasoning for trade validation

## Markets Mentioned
- BTCUSDT (crypto)
- Forex pairs implied (NFP context)

## Tech Stack Hints
- Python pseudocode shown
- LLM-driven inference engine (not rule-based)
- Paper trading module recommended (14-day minimum)
