# Backtest Audit — Phase 7.1

**Date:** 2026-08-29  
**Scope:** `src/exness_bot/backtest/`  
**Strategy under test:** `ema_rsi_atr_v1` (XAUUSD M15)  
**Verdict:** **CONDITIONALLY TRUSTWORTHY**

This document records the audit of the backtesting engine. It does **not** claim
profitability or predictive power — only whether simulation mechanics are sound
enough for **demo research** when assumptions are understood.

---

## 1. Current architecture

```
CSV → loader → validate_candle_series()
         ↓
BacktestEngine (bar-by-bar loop)
  → IndicatorCalculator (history [0..i] only)
  → EmaRsiAtrStrategy.evaluate()
  → RiskManager.assess()  [live rules]
  → VirtualExecutor (entry / SL / TP / costs)
  → Trade journal + equity curve
         ↓
calculate_metrics() → BacktestReport (JSON + summary)
```

No MT5 connection. No live orders. No parameter optimization.

---

## 2. Execution & timing model

| Step | When | Data used |
|------|------|-----------|
| Warm-up | Bars `0..199` | Indicators only; no trades |
| Signal | Close of bar `i` | OHLCV `[0..i]` |
| Risk sizing | After signal | Equity, symbol spec, ATR-based SL/TP |
| Entry fill | Same bar close as signal | `close ± half_spread ± slippage` |
| SL/TP check | Bars `i+1` onward only | Intrabar `high` / `low` |
| Same-bar SL+TP | Both touched | **Stop loss first** (`SAME_BAR_EXIT_RULE`) |
| New entry | Only if flat | Max 1 position; no same-bar re-entry after exit |

**Entry timing note:** Fill occurs at the signal bar **close**, not the next bar
open. This matches the live bot’s “act after M15 close” behaviour but is slightly
optimistic vs exchange queue position. Documented as a known limitation.

---

## 3. Assumptions (post-audit)

| Component | Model | Default |
|-----------|--------|---------|
| Spread | Half-spread on entry; half-spread on exit | 20 points |
| Slippage | Against trader on entry and exit | **1 point** (conservative) |
| Commission | Flat USD/lot/side, deducted from net PnL | $0 |
| Swap | Flat USD/lot/calendar day while position open | $0 |
| SL/TP fills | Trigger level ± exit costs | Conservative |
| Same-bar conflict | SL before TP | Always |

Full detail: [BACKTEST_ASSUMPTIONS.md](./BACKTEST_ASSUMPTIONS.md)

---

## 4. Audit findings by area

### 4.1 Look-ahead bias — PASS (with caveats)

| Check | Result |
|-------|--------|
| OHLC history truncated to `[0..i]` | ✅ |
| EMA / RSI / ATR from truncated bars | ✅ |
| Signal uses latest closed bar only | ✅ |
| SL/TP not evaluated on entry bar | ✅ Fixed (explicit `bar_index > entry_bar_index`) |
| Future bars never visible | ✅ |

**Caveat:** SL/TP levels are computed from signal `close`, while fill uses
`close + costs`. Effective stop distance differs slightly from live fill-based
sizing. Slightly alters realized risk vs configured %.

### 4.2 Candle timing — PASS

- One signal evaluation per bar after warm-up
- Forming candle excluded (sequential closed bars from CSV)
- No second trade on same bar while position open
- Re-entry same bar after exit is allowed (rare on M15)

### 4.3 OHLC execution — PASS

- SL/TP detected via intrabar high/low
- Both hit → SL wins (`stop_loss_first`)
- Documented in code as `SAME_BAR_EXIT_RULE`

### 4.4 Spread — PASS (after fix)

| Location | Before audit | After fix |
|----------|--------------|-----------|
| Entry | Half-spread ✅ | Unchanged |
| Exit (SL/TP/EOD) | Exact level ❌ | Half-spread adverse ✅ |
| SL/TP trigger levels | Unchanged | Unchanged (costs on fill only) |

### 4.5 Slippage — PASS (after fix)

- Configurable `slippage_points`
- Applied entry **and** exit
- Default changed from `0` → `1` point (conservative)

### 4.6 Commission — PASS

- Included in `TradeRecord.commission` and net PnL
- Configurable per lot per side

### 4.7 Swap — DOCUMENTED + BASIC MODEL

- M15 holds can cross midnight → swap may matter
- Added accrual: `swap_per_lot_per_day × volume` per calendar day while open
- Default remains `0`; enable for overnight sensitivity analysis

### 4.8 Position sizing — PASS

- Uses live `RiskManager` + `calculate_position_size()`
- Based on equity, risk %, SL distance, symbol contract spec
- No hardcoded lot sizes

### 4.9 Risk controls — PASS

Enforced via live `RiskManager`:

- Max risk per trade (position sizing)
- Max daily loss ✅ tested
- Max drawdown ✅ tested
- Max open positions (1) ✅ engine + risk
- Max position size (lot cap)

### 4.10 Data quality — PASS (after fix)

Added `validate_candle_series()`:

- Insufficient warm-up → `ValueError`
- Duplicate timestamps → `ValueError`
- Missing M15 gaps → `ValueError`
- Invalid OHLC → `ValueError`
- Timestamps normalized to UTC
- Unsorted CSV sorted on load (duplicates/gaps still fail)

Weekend gaps in real XAUUSD data will fail strict gap check — use continuous
CSV segments or relax `strict_gaps` in future if needed.

### 4.11 PnL calculation — PASS (after fix)

| Metric | Issue found | Fix |
|--------|-------------|-----|
| `gross_profit` / `gross_loss` | Used `net_pnl` | Fixed to use `gross_pnl` |
| `net_profit` | — | Sum of `net_pnl` |
| Exit costs | Missing on exit | Spread + slippage on fill |
| Manual TP long | — | Verified in audit tests |

### 4.12 Reproducibility — PASS

Identical CSV + settings → identical `BacktestReport.model_dump()` (tested).

---

## 5. Bugs found & fixes applied

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| B1 | High | Exit fills ignored spread/slippage | `_exit_fill_price()` on all exits |
| B2 | High | `gross_profit`/`gross_loss` used net PnL | `metrics.py` corrected |
| B3 | Medium | SL/TP could fire on entry bar in theory | `bar_index > entry_bar_index` guard |
| B4 | Medium | No data validation (dupes/gaps/OHLC) | `validation.py` + engine hook |
| B5 | Low | Slippage default 0 (optimistic) | Default → 1 point |
| B6 | Low | Swap not modeled | Optional daily accrual added |

---

## 6. Known limitations (remaining risks)

1. **Entry at bar close** — not next-bar open; may overstate fill quality.
2. **SL/TP from signal close** — not from actual fill price; minor risk % drift.
3. **Fixed spread** — CSV per-bar spread column not yet used.
4. **Strict gap validation** — real market CSV with weekend holes may fail load.
5. **Swap default 0** — overnight costs understated unless configured.
6. **No partial fills, gaps, or limit orders.**
7. **End-of-data exit** uses last close ± costs — may not reflect real liquidation.
8. **Backtest ≠ live** — latency, requotes, and broker rejection not simulated.

---

## 7. Test coverage added

`tests/unit/test_backtest_audit.py` — 18 deterministic tests covering:

1. BUY → TP  
2. BUY → SL  
3. SELL → TP  
4. SELL → SL  
5. Same-bar SL+TP (conservative)  
6. Insufficient data  
7. Duplicate candle  
8. Missing candle gap  
9. Position sizing  
10. Spread (entry + exit)  
11. Slippage default  
12. Commission  
13. Manual PnL verification  
14. Max daily loss  
15. Max drawdown  
16. Max open positions  
17. No exit on entry bar  
18. Reproducibility  

---

## 8. Confidence assessment

### **CONDITIONALLY TRUSTWORTHY**

**Trust for demo research when:**

- CSV data is clean (no dupes, continuous M15 series)
- Spread/slippage/commission assumptions are explicitly set
- Results are interpreted as **relative** comparisons, not profit guarantees
- Same-bar SL-first and exit costs are acceptable conservative choices

**Not trustworthy for:**

- Live capital allocation decisions without forward/demo validation
- Overnight carry-sensitive strategies (unless swap configured)
- Data with session gaps without preprocessing

**Not claimed:** profitability, optimal parameters, or live performance parity.

---

## 9. Commands run

```bash
pytest          # 235 passed
ruff check src tests
mypy src
```
