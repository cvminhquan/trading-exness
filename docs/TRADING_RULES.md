# Trading Rules — Exness Trading Bot V1

## 1. Instrument

| Parameter | Value |
|-----------|-------|
| Symbol | XAUUSD |
| Broker | Exness (via MT5) |
| Timeframe | M15 |
| Session | 24/5 (Gold) — gap handling TBD |

---

## 2. Indicators

| Indicator | Period | Source |
|-----------|--------|--------|
| EMA Fast | 20 | Close |
| EMA Medium | 50 | Close |
| EMA Slow | 200 | Close |
| RSI | 14 | Close |
| ATR | 14 | True Range |

**Minimum bars required:** 200 + buffer (recommend 250 bars warmup).

---

## 3. Entry Rules (Proposed — Pending Confirmation)

### 3.1 Long Entry

Tất cả điều kiện phải đúng **tại bar close M15**:

1. **EMA Trend:** `EMA20 > EMA50 > EMA200`
2. **RSI Confirmation:** `RSI14 > 50` và `RSI14 < 70` (tránh overbought extreme)
3. **No existing long** trên XAUUSD (max 1 position V1)
4. **Risk Manager approval**

### 3.2 Short Entry

1. **EMA Trend:** `EMA20 < EMA50 < EMA200`
2. **RSI Confirmation:** `RSI14 < 50` và `RSI14 > 30` (tránh oversold extreme)
3. **No existing short** trên XAUUSD
4. **Risk Manager approval**

### 3.3 No Trade

- EMA alignment không rõ (crossed / flat market)
- RSI ngoài vùng confirmation
- Daily loss limit đã hit
- Drawdown limit đã hit
- Max open positions reached

---

## 4. Exit Rules (Proposed)

### 4.1 Stop Loss

```
SL_distance = ATR14 × ATR_SL_MULTIPLIER

Long:  SL = entry_price - SL_distance
Short: SL = entry_price + SL_distance
```

**Proposed `ATR_SL_MULTIPLIER`:** 1.5 (pending confirmation)

### 4.2 Take Profit

**Option A (recommended for V1):** Fixed R:R

```
TP_distance = SL_distance × REWARD_RISK_RATIO
```

**Proposed `REWARD_RISK_RATIO`:** 2.0 (pending confirmation)

**Option B:** Opposite EMA cross — deferred to V1.1

### 4.3 Trailing Stop

Not in V1 scope. See ROADMAP V1.1.

---

## 5. Position Sizing

```
risk_amount = account_equity × (RISK_PER_TRADE_PCT / 100)
sl_points   = abs(entry_price - stop_loss) / point_size
volume      = risk_amount / (sl_points × tick_value)
volume      = normalize_to_broker_lot_step(volume)
volume      = clamp(min_lot, max_lot)
```

| Parameter | Default |
|-----------|---------|
| `RISK_PER_TRADE_PCT` | 0.5% |

**Constraints:**
- Không hardcode lot size
- Respect broker min/max/step lot (from MT5 symbol info)
- Reject nếu computed volume < min_lot

---

## 6. Risk Limits

| Limit | Default | Action when breached |
|-------|---------|----------------------|
| Risk per trade | 0.5% | Reject signal |
| Max daily loss | 2.0% of day-start equity | Stop trading for day |
| Max drawdown | 5.0% from peak equity | Stop trading until manual reset |
| Max open positions | 1 | Reject new signals |

**Daily loss calculation:**
```
daily_pnl_pct = (current_equity - day_start_equity) / day_start_equity × 100
if daily_pnl_pct <= -MAX_DAILY_LOSS_PCT: HALT
```

**Drawdown calculation:**
```
drawdown_pct = (peak_equity - current_equity) / peak_equity × 100
if drawdown_pct >= MAX_DRAWDOWN_PCT: HALT
```

---

## 7. Order Types

| Action | Order Type |
|--------|------------|
| Entry | Market order |
| Stop Loss | Attached SL at order placement |
| Take Profit | Attached TP at order placement |

**Slippage / deviation:** Configurable `MAX_DEVIATION_POINTS` (default TBD from Exness XAUUSD spec).

---

## 8. Safety Rules (Non-Negotiable)

1. **Default mode:** DEMO + DRY_RUN
2. **Live trading requires:**
   - `TRADING_MODE=live`
   - `ALLOW_LIVE_TRADING=true`
   - Explicit runtime confirmation (future CLI `--confirm-live`)
3. **DRY_RUN:** Log order intent, không gọi `place_order`
4. **No martingale / grid / averaging down** in V1
5. **One strategy instance per symbol** in V1

---

## 9. Signal Metadata

Mỗi `Signal` phải carry:

```python
{
    "strategy": "ema_trend_rsi",
    "symbol": "XAUUSD",
    "timeframe": "M15",
    "direction": "LONG" | "SHORT",
    "entry_price": float,      # bar close at signal
    "ema20": float,
    "ema50": float,
    "ema200": float,
    "rsi14": float,
    "atr14": float,
    "timestamp": datetime,
}
```

---

## 10. Backtest Rules

- Dùng **cùng entry/exit/risk rules** như live
- Không look-ahead bias: chỉ dùng data available tại bar close
- Spread model: fixed spread hoặc historical spread (TBD)
- Commission: Exness commission model (TBD)
- Slippage: configurable fixed slippage (default 0 for initial backtest)

---

## 11. Decisions Pending User Confirmation

| # | Decision | Proposed Default | Impact |
|---|----------|------------------|--------|
| 1 | RSI long threshold | > 50 and < 70 | Entry frequency |
| 2 | RSI short threshold | < 50 and > 30 | Entry frequency |
| 3 | ATR SL multiplier | 1.5 | Risk per trade |
| 4 | Reward:Risk ratio | 2.0 | Profit target |
| 5 | Trade only on new bar | Yes | Signal timing |
| 6 | Filter news events | No (V1) | Complexity |
| 7 | Max spread filter | TBD (e.g. 50 points) | Entry quality |
| 8 | Session filter (avoid rollover) | No (V1) | Complexity |

---

## 12. Example Trade (Long)

```
Account equity: $10,000
Risk per trade: 0.5% → $50 risk

XAUUSD @ 2350.00
ATR14 = 8.0
SL = 2350.00 - (8.0 × 1.5) = 2338.00
SL distance = 12.0

TP = 2350.00 + (12.0 × 2.0) = 2374.00

Volume = $50 / (12.0 × tick_value) → normalize to 0.01 step
```

*(tick_value lấy từ MT5 symbol_info)*
