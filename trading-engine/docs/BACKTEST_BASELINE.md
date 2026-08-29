# Backtest Baseline — ema_rsi_atr_v1

**Generated:** 2026-08-29T02:55:24.775925+00:00
**Status:** insufficient_data
**Message:** No historical XAUUSD M15 CSV dataset found in data/.

## Dataset

| Field | Value |
|-------|-------|
| Path | `none` |
| Start | None |
| End | None |
| Total candles | 0 |
| Duration (days) | 0.0 |
| Duplicates | 0 |
| Missing periods | 0 |
| Missing bars (est.) | 0 |
| Timezone | UTC |
| Weekend/session gaps | 0 / 0 |
| Meaningful sample | False |

## Execution assumptions

- Initial balance: $10,000.00
- Risk per trade: 0.5%
- Spread: 50 points
- Slippage: 1.0 points
- Commission: $0.0/lot/side
- Swap: $0.0/lot/day
- Max open positions: 1
- Max daily loss: 2.0%
- Max drawdown: 5.0%
- Max position lots: 1.0
- Warm-up bars: 200

## Results

Baseline metrics were **not** generated because the dataset is insufficient.
Do not infer strategy performance from this phase.

### Required data

- Minimum: 5,000 continuous XAUUSD M15 candles (UTC)
- Recommended: 20,000+ candles
- Place CSV in `data/historical/` (see README)


## Known limitations

- Backtest engine is **CONDITIONALLY TRUSTWORTHY** (see `docs/BACKTEST_AUDIT.md`).
- Fixed spread/slippage; no variable liquidity or partial fills.
- Single-position limit; no portfolio effects.
- Strategy parameters were not modified in this phase.
- No real historical XAUUSD M15 CSV is present in the repository.
- Metrics below are intentionally omitted to avoid fabricated results.

## Interpretation

This baseline is for **research only**. It does **not** claim profitability or predict live performance.

## Phase 7.3 readiness

**NOT READY** — Phase 7.3 requires a completed baseline on a meaningful historical dataset (≥5,000 M15 candles). Export XAUUSD M15 data from MT5 into `data/historical/` and re-run the baseline.
