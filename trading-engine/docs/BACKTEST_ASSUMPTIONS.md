# Backtest Assumptions — Exness Bot

This document describes the simulation assumptions used by the Phase 7 backtesting
engine. The backtest reuses live **indicators**, **strategy**, and **risk rules**
but never connects to MT5 or submits real orders.

---

## 1. Candle timing (no look-ahead)

- The engine walks forward one **closed M15 bar** at a time.
- At bar index `i`, only candles `[0 … i]` are visible.
- Indicators are recomputed from that truncated history on every step.
- Signals are evaluated at the **close** of bar `i`.
- Warm-up: the first `200` bars are used only to seed EMA200; no trades occur.

This prevents look-ahead bias: future highs, lows, or closes are never used for
decisions on earlier bars.

---

## 2. Execution model

| Event | Price |
|-------|-------|
| **Long entry** | `close + half_spread + slippage` |
| **Short entry** | `close - half_spread - slippage` |
| **Stop loss exit** | `stop_loss - half_spread - slippage` (long) |
| **Take profit exit** | `take_profit - half_spread - slippage` (long) |
| **End of data** | `close ± exit costs` (open positions only) |

Entries occur on the **same bar** the signal is generated (bar close), matching
the live bot’s “act immediately after candle close” behaviour.

---

## 3. Spread

- **Model:** fixed spread in **points** (default: 20 points = $0.20 on XAUUSD).
- Half the spread is added against the trader on entry **and** exit fills.
- Exit trigger levels (SL/TP) are unchanged; costs apply to the fill price.

Configurable via `BacktestConfig.spread_points`.

---

## 4. Slippage

- **Model:** fixed slippage in points, applied against trade direction on entry **and exit**.
- **Default:** `1` point (conservative).

Configurable via `BacktestConfig.slippage_points`.

---

## 5. Commission

- **Model:** flat **USD per lot per side**.
- Deducted as `commission_per_lot × volume × 2` (entry + exit).
- **Default:** `$0.00`.

Exness account-type commission tiers are not modeled in V1.

---

## 6. Swap / overnight funding

- **Model:** flat USD per lot per calendar day while a position remains open.
- **Default:** `0` (disabled).
- Charge accrues when the simulation date changes and a position is still open.

---

## 7. Stop loss / take profit resolution

- Exits are checked on bars **after** the entry bar using `high` and `low`.
- If both SL and TP are within the same bar’s range, **stop loss takes priority**
  (conservative / worst-case assumption).
- No partial fills; full volume closes at the exit price.

---

## 8. Position limits

- Maximum **one open position** at a time (same as live `MAX_OPEN_POSITIONS=1`).
- No pyramiding, hedging, or scale-in/out.
- A new signal while a position is open is ignored until the position closes.

---

## 9. Risk management

The live `RiskManager` is used unchanged:

- Position sizing from equity and ATR stop distance
- Daily loss, drawdown, spread, margin, and lot-size limits
- `day_start_equity` resets at each new calendar day in the simulation

Account is simulated with `trade_mode=demo` and `free_margin=equity`.

---

## 10. Symbol specification (XAUUSD defaults)

| Parameter | Default |
|-----------|---------|
| Point | 0.01 |
| Contract size | 100 oz |
| Min lot | 0.01 |
| Lot step | 0.01 |
| Max lot | 100.0 |

PnL: `(exit - entry) / point × contract_size × point × volume` for longs.

---

## 11. Out of scope (V1)

- Parameter optimization / walk-forward analysis
- Variable or historical spread per bar (CSV `spread` column reserved for future)
- Gap handling beyond intrabar high/low
- Pending/limit orders (market entries only)
- Multi-symbol portfolios

---

## 12. CLI usage

```bash
exness-bot backtest --file data/xauusd_m15.csv
exness-bot backtest --file data/xauusd_m15.csv --json report.json
```

CSV format: `timestamp,open,high,low,close` (+ optional `volume`, `spread`).
