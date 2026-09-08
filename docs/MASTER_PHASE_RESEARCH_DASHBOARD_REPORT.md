# MASTER PHASE REPORT — Research Harness Hardening + Multi-Symbol Dashboard

**Date:** 2026-09-08  
**Research verdict:** `PROMISING_V2_REQUIRES_MORE_DATA`  
**v2 promoted:** NO

```text
mtf_technical_v1 modified: NO
v2 wired to ExecutionCandidate: NO
Phase17 changed: NO
order_send: NO
broker mutation: NO
Dashboard broker actions: NO
```

---

## SECTION 1 — Research (Track A)

Freeze snapshot **immutable** (asserted in code). Full details:

- `docs/PHASE_16_2_4A_VALIDATION_HARDENING.md`
- `docs/M15_FIRST_SCORING_RESEARCH.md`
- JSON: `trading-engine/data/historical/m15_first_research_16_2_4A.json`

### Coverage

| Field | Value |
|-------|------:|
| TOTAL_M15_BARS | 35973 |
| WARMUP_EXCLUDED | 250 |
| SAMPLING_EXCLUDED | 0 (fixed; legacy step=48 removed) |
| FINAL_EVALUATED | 35723 |

### Answers

1. **V1 lag on strong M15?** YES — structure ±100 + low M15 weight + HTF veto.  
2. **V2 latency:** 4h synthetic 16→4 bars (−12 / −180 min / missed ATR 28→7).  
3. **False signals:** holdout false rate 66.0%→64.6% (slight ↓).  
4. **Whipsaw:** 21.0%→23.4% (slight ↑).  
5. **Expectancy/PF holdout:** +0.016/1.02 → **+0.057/1.09**.  
6. **Drawdown_R:** 33→**58** (worse — blocks outperform).  
7. **V2 SHORT while V1 WAIT (121):** win 44.6%, expectancy **+0.34**.  
8. **Harness coverage?** YES after 16.2.4A (step=1).  
9. **Need forward/unseen data?** YES — holdout already observed; no retune on same set.

### Resampling

M15 canonical → UTC floor H1/H4/D1; closed buckets only; unit test `test_phase_16_2_4a_resample_alignment.py`.

**Verdict:** `PROMISING_V2_REQUIRES_MORE_DATA`

---

## SECTION 2 — Dashboard (Track B)

### Routes

| Route | Role |
|-------|------|
| `/dashboard` | Redirect → `/dashboard/XAUUSD` |
| `/dashboard/[symbol]` | Multi-symbol overview workspace |
| `/dashboard/positions` | Open positions (existing) |
| `/dashboard/trades` | Journal / Signal explorer (read-only) |
| `/dashboard/strategy` | v1 production + v2 research-only card |
| `/dashboard/risk` | Risk snapshot |
| `/dashboard/backtest` | Existing backtest UI |
| `/dashboard/paper` | Existing paper UI |
| `/dashboard/settings` | Existing settings (read-mostly) |

### Components

- `SymbolTabs` — price + freshness from quotes API  
- Removed **Dòng tiền thịnh hành** from overview  
- `PriceRelationshipBar` — TP1 / CURRENT / ENTRY / SL  
- TF roles on MTF summary (PRIMARY / CONFIRMATION / CONTEXT / MACRO)  
- Positions on overview filtered by selected symbol  

### Endpoints consumed

Existing: account overview, MTF analysis, execution-candidate, positions, quotes, PnL daily.  
No new broker mutation APIs.

### Missing / honest limits

- Closed-position history: only if backend already provides (positions page uses open API).  
- % change on tabs: not fabricated (only last/bid/ask).  
- Backtest run-from-UI: existing engine/UI only — no new live MT5 path.

---

## SECTION 3 — Sidebar status

| Item | Status | Notes |
|------|--------|-------|
| Tổng quan | **IMPLEMENTED** | Symbol tabs + analysis + symbol positions |
| Vị thế | **IMPLEMENTED** | Open positions table; closed history LIMITED if API absent |
| Giao dịch | **IMPLEMENTED** | Read-only journal / signal explorer framing (no BUY/SELL) |
| Chiến lược | **IMPLEMENTED** | v1 + research-only v2 card (no activate) |
| Rủi ro | **IMPLEMENTED** | Account metrics + risk snapshot limits; config READ ONLY |
| Backtest | **LIMITED** | Existing reports UI; run-from-engine, no new broker path |
| Paper Trading | **LIMITED** | Existing isolated paper page; no LiveMT5 / order_send |
| Cài đặt | **LIMITED** | READ ONLY groups + Diagnostics; no fake Save / no password |

---

## SECTION 4 — Safety

Static expectations:

- Dashboard must not import ExecutionOrchestrator / GatedMT5 / LiveMT5 / order_send  
- No Execute/Open/Close action buttons  
- SELL/SHORT as **signal labels** allowed  

Production must not import `market_analysis.research`.

---

## SECTION 5 — Verification

```text
pytest (research / 16.2.4*): 16 passed (+2 resample alignment)
dashboard lint: PASS
dashboard typecheck: PASS
dashboard build: FAIL (EPERM rmdir .next — file lock / OneDrive; not a code error)
Safety grep dashboard: ZERO ExecutionOrchestrator / GatedMT5 / LiveMT5 / order_send
Action OPEN/CLOSE/Execute buttons: ZERO
```

---

## SECTION 6 — UI states (descriptions)

| View | Description |
|------|-------------|
| Dashboard XAUUSD | Tabs + hero + setup/risk + MTF + XAU positions |
| Dashboard BTCUSD | Same shell; analysis queries `BTCUSD` |
| WAIT / SHORT / BLOCKED | Hero badges + reasons card |
| Positions / Trading / Strategy / Risk / Backtest / Paper / Settings | Sidebar routes |
| Mobile | Symbol tabs horizontal scroll; stacked analysis |

---

## FINAL RESEARCH VERDICT

```text
PROMISING_V2_REQUIRES_MORE_DATA
```

Do **not** promote `mtf_technical_v2_candidate` to execution.
