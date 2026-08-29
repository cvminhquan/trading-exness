# Architecture — Exness Trading Bot

## 1. Tổng quan

Hệ thống tuân theo **layered architecture** với separation of concerns nghiêm ngặt. Mỗi layer chỉ phụ thuộc vào layer bên dưới hoặc abstraction (interface), không phụ thuộc implementation cụ thể.

```
┌─────────────────────────────────────────────────────────────┐
│                     Application Layer                        │
│  CLI / Scheduler / (Future: FastAPI / Next.js dashboard)   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                     Trading Engine                           │
│  Orchestrates: data → strategy → risk → orders               │
└──┬────────┬──────────┬──────────┬──────────┬────────────────┘
   │        │          │          │          │
   ▼        ▼          ▼          ▼          ▼
 Market   Strategy   Signal    Risk      Order
  Data               (domain)  Manager   Manager
   │                                        │
   ▼                                        ▼
 Broker Port ◄────────────────────── Broker Adapter (MT5)
   │
   ▼
 Persistence (PostgreSQL) — Phase 2+
```

---

## 2. Module Structure

```
src/exness_bot/
├── config/          # Pydantic settings, env validation
├── domain/          # Core types: Bar, Signal, Order, Position, enums
├── market_data/     # MarketDataProvider abstraction + implementations
├── indicators/      # Pure functions: EMA, RSI, ATR
├── strategy/        # Strategy interface + EMA trend implementation
├── signals/         # Signal models and factory
├── risk/            # RiskManager — position sizing, limits
├── orders/          # OrderManager — sole order submission point
├── broker/          # BrokerPort interface
│   └── mt5/         # MT5Adapter (isolated MT5 calls)
├── engine/          # TradingEngine orchestrator
├── backtest/        # BacktestRunner (historical simulation)
└── logging/         # Structured logging setup
```

---

## 3. Dependency Rules

| Layer | Được phép import | Không được import |
|-------|------------------|-------------------|
| `domain` | stdlib only | mọi layer khác |
| `indicators` | domain, pandas, numpy | broker, orders, strategy |
| `strategy` | domain, indicators, market_data (interface) | broker, orders, mt5 |
| `risk` | domain, config | broker, mt5 |
| `orders` | domain, broker (interface), config | strategy |
| `broker/mt5` | domain, MetaTrader5 | strategy, risk |
| `engine` | tất cả layers | — |

**Không circular dependencies.** Enforce bằng import-linter hoặc review (future).

---

## 4. Core Abstractions

### 4.1 BrokerPort

Interface duy nhất mà Order Manager và Market Data sử dụng để nói chuyện với broker.

```python
class BrokerPort(Protocol):
    def connect(self) -> bool: ...
    def disconnect(self) -> None: ...
    def is_connected(self) -> bool: ...
    def get_account_info(self) -> AccountInfo: ...
    def get_bars(self, symbol: str, timeframe: Timeframe, count: int) -> list[Bar]: ...
    def get_open_positions(self, symbol: str | None = None) -> list[Position]: ...
    def place_order(self, request: OrderRequest) -> OrderResult: ...
    def close_position(self, ticket: int) -> OrderResult: ...
```

Implementation: `MT5Adapter` — tất cả `import MetaTrader5` chỉ ở đây.

### 4.2 MarketDataProvider

```python
class MarketDataProvider(Protocol):
    def get_latest_bars(self, symbol: str, timeframe: Timeframe, count: int) -> pd.DataFrame: ...
```

Implementations:
- `MT5MarketDataProvider` — live data qua BrokerPort
- `CsvMarketDataProvider` — backtest (phase 2)

### 4.3 Strategy

```python
class Strategy(Protocol):
    def evaluate(self, bars: pd.DataFrame, indicators: IndicatorSnapshot) -> Signal | None: ...
```

Strategy trả về `Signal | None`, **không** side-effect.

### 4.4 RiskManager

```python
class RiskManager:
    def assess(self, signal: Signal, account: AccountInfo, open_positions: list[Position]) -> RiskDecision: ...
```

`RiskDecision` = `ApprovedOrderPlan | RejectedSignal`.

### 4.5 OrderManager

```python
class OrderManager:
    def execute(self, plan: ApprovedOrderPlan) -> OrderResult: ...
```

Pre-flight checks:
1. `DRY_RUN` → log only, no broker call
2. `TRADING_MODE != live` hoặc `ALLOW_LIVE_TRADING != true` → reject live orders
3. Validate lot size, SL/TP distances
4. Delegate to `BrokerPort.place_order`

---

## 5. Domain Models (Pydantic / dataclass)

| Model | Mô tả |
|-------|-------|
| `Bar` | OHLCV + timestamp |
| `Timeframe` | Enum: M15, ... |
| `SignalDirection` | LONG, SHORT, FLAT |
| `Signal` | direction, symbol, timeframe, strength, metadata |
| `OrderRequest` | symbol, volume, type, sl, tp, comment |
| `OrderResult` | success, ticket, error_message |
| `Position` | ticket, symbol, volume, profit, sl, tp |
| `AccountInfo` | balance, equity, margin, currency |
| `RiskDecision` | approved plan hoặc rejection reason |
| `ApprovedOrderPlan` | signal + computed volume + sl + tp |

---

## 6. Configuration

Centralized trong `Settings` (Pydantic BaseSettings):

```yaml
# Safety (defaults)
TRADING_MODE: demo          # demo | live
DRY_RUN: true
ALLOW_LIVE_TRADING: false

# MT5
MT5_LOGIN: ""
MT5_PASSWORD: ""
MT5_SERVER: ""
MT5_PATH: ""                # optional terminal path

# Trading
SYMBOL: XAUUSD
TIMEFRAME: M15

# Risk
RISK_PER_TRADE_PCT: 0.5
MAX_DAILY_LOSS_PCT: 2.0
MAX_DRAWDOWN_PCT: 5.0
MAX_OPEN_POSITIONS: 1

# Database
DATABASE_URL: postgresql://...
```

**Validation rules:**
- `TRADING_MODE=live` + `ALLOW_LIVE_TRADING=false` → startup warning / block orders
- `RISK_PER_TRADE_PCT` ∈ (0, 5]
- Credentials required only when not in pure backtest mode

---

## 7. Safety Architecture

```
                    ┌─────────────────┐
                    │  Settings load  │
                    │  default: DEMO  │
                    └────────┬────────┘
                             │
              ┌──────────────▼──────────────┐
              │   SafetyGuard.validate()    │
              │   at startup & per order    │
              └──────────────┬──────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
   DRY_RUN check      LIVE flag check     Risk limits
   (OrderManager)     (OrderManager)      (RiskManager)
```

**Triple guard cho live orders:**
1. Config: `ALLOW_LIVE_TRADING=true`
2. Config: `TRADING_MODE=live`
3. OrderManager: explicit `confirm_live=True` parameter (future CLI flag)

---

## 8. Data Flow — Live Trading Loop

```
1. Engine.tick()
2. MarketDataProvider.get_latest_bars(XAUUSD, M15, n)
3. IndicatorCalculator.compute(bars) → IndicatorSnapshot
4. Strategy.evaluate(bars, indicators) → Signal | None
5. if Signal:
     RiskManager.assess(signal, account, positions) → RiskDecision
6. if Approved:
     OrderManager.execute(plan) → OrderResult
7. Log structured event + (future) persist to DB
```

---

## 9. Backtest Architecture (Phase 2)

```
Historical CSV/MT5 export
    → CsvMarketDataProvider
    → Same Strategy + RiskManager (with simulated account)
    → SimulatedOrderExecutor (no BrokerPort)
    → BacktestReport (metrics: win rate, drawdown, Sharpe)
```

Strategy và RiskManager **reuse** — chỉ thay data source và order executor.

---

## 10. Logging

Structured JSON logging (stdlib `logging` + custom formatter):

```json
{
  "timestamp": "2026-08-29T09:00:00Z",
  "level": "INFO",
  "module": "orders.manager",
  "event": "order_dry_run",
  "symbol": "XAUUSD",
  "direction": "LONG",
  "volume": 0.01
}
```

---

## 11. Testing Strategy

| Loại | Phạm vi | Tools |
|------|---------|-------|
| Unit | domain models, indicators, config, safety guards | pytest |
| Unit | strategy logic với fixture DataFrame | pytest + pandas |
| Unit | risk manager với mock account | pytest |
| Integration | MT5 adapter (optional, cần terminal) | pytest marker `@pytest.mark.mt5` |
| Integration | PostgreSQL (phase 2) | pytest + docker |

CI chạy unit tests; integration tests MT5 skip nếu không có terminal.

---

## 12. Deployment (Future VPS)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   VPS Win    │     │  PostgreSQL  │     │  Next.js     │
│  MT5 + Bot   │────▶│  (Docker)    │◀────│  Dashboard   │
└──────────────┘     └──────────────┘     └──────────────┘
```

MT5 Python API yêu cầu Windows + MT5 terminal installed. VPS Windows là target production.

---

## 13. Technology Decisions

| Quyết định | Lựa chọn | Lý do |
|------------|----------|-------|
| Config | Pydantic Settings | Validation, type-safe |
| DI | Constructor injection | Simple, testable, no framework |
| ORM | SQLAlchemy (phase 2) | PostgreSQL standard |
| Async | Sync first | MT5 API is sync; asyncio later if needed |
| Package layout | `src/` layout | Best practice PEP 517 |

---

## 14. Open Architecture Questions

1. **Event-driven vs polling:** V1 dùng polling mỗi M15 bar close; có cần tick handler không?
2. **State storage:** In-memory vs Redis cho multi-instance (V1: single process)
3. **API layer:** FastAPI wrapper cho dashboard — phase nào?
4. **Idempotency:** Làm sao tránh duplicate orders khi reconnect?

Xem [ROADMAP.md](./ROADMAP.md) cho timeline giải quyết.

---

## 15. Dashboard Integration Boundary (Phase 10.4–10.5)

Dashboard Next.js **tách biệt hoàn toàn** khỏi `trading-engine/src/`. Ranh giới tích hợp là **HTTP API read-only** (FastAPI — Phase 10.5).

```
┌─────────────────┐
│ Browser         │
│  Next.js UI     │
└────────┬────────┘
         │ React Query
         ▼
┌─────────────────┐
│ TradingRepository │  ← interface domain-oriented
├─────────────────┤
│ MockTradingRepository  (development)
│ ApiTradingRepository   (production / integration)
└────────┬────────┘
         │ HTTP JSON + Zod validation
         ▼
┌─────────────────┐
│ FastAPI         │  ← read-only adapter (Phase 10.5)
│ exness_bot/api  │
└────────┬────────┘
         │ service/query layer
         ▼
┌─────────────────┐
│ Trading Engine  │  strategy, risk, backtest domain
└────────┬────────┘
         ▼
      MT5 / Backtest JSON / SQLite
```

**API read-only:** Không có endpoint đặt lệnh, đóng vị thế, sửa SL/TP, start/stop bot, hoặc thay đổi risk/strategy. Trading mutations cố ý không khả dụng qua HTTP.

### Trách nhiệm

| Thành phần | Trách nhiệm |
|------------|-------------|
| **Dashboard** | Hiển thị, format, UX — **không** quyết định giao dịch |
| **Trading Engine** | Logic giao dịch, risk, strategy, backtest |
| **API Contract** | [`API_CONTRACT.md`](./API_CONTRACT.md) — envelope, endpoints, schemas |

### Quy tắc kiến trúc

1. Page/Component **không** gọi `fetch()` trực tiếp
2. Mọi data qua `TradingRepository`
3. Chuyển mock ↔ API bằng `NEXT_PUBLIC_DATA_SOURCE` tại factory duy nhất
4. Response API validate bằng Zod trước khi vào UI
5. Lỗi chuẩn hóa `ApiError` — message tiếng Việt cho operator
6. **Read-only** — không mutation endpoints ở giai đoạn này

### Cấu trúc Dashboard (liên quan integration)

```
dashboard/
├── domain/schemas.ts       # Domain + Zod
├── domain/api/             # Envelope, query params
├── lib/api/                # ApiClient, ApiError
├── lib/config/env.ts       # DATA_SOURCE, API_BASE_URL
├── repositories/
│   ├── trading-repository.ts
│   ├── mock-trading-repository.ts
│   ├── api-trading-repository.ts
│   └── create-trading-repository.ts
└── queries/                # React Query → repository
```
