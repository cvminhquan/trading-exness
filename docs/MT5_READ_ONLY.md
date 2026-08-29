# MT5 Read-only Integration — Phase 10.6

Tài liệu mô tả adapter **read-only** cho MetaTrader 5, phục vụ Python API và Next.js Dashboard.

---

## 1. Mục tiêu

Cho phép Dashboard đọc dữ liệu thật từ Exness/MT5 **mà không đặt lệnh**.

```
MT5 Terminal
    ↓ (read-only)
MT5ReadOnlyClient
    ↓
MT5TradingDataProvider
    ↓
ReadService (FastAPI)
    ↓
Dashboard (React Query polling)
```

**Ran giới an toàn:** Không gọi `order_send` hoặc bất kỳ API MT5 nào thay đổi trạng thái giao dịch.

---

## 2. Kiến trúc

| Layer | Thành phần | Trách nhiệm |
|-------|------------|-------------|
| Broker | `MT5ReadOnlyClient` | Wrapper MT5 — chỉ đọc |
| Broker | `MT5TradingClient` | Trading engine — có `order_send` |
| Broker | `MT5ConnectionManager` | Lazy connect, thread-safe |
| Data | `TradingDataProvider` | Abstraction domain |
| Data | `MockTradingDataProvider` | Development / Linux |
| Data | `MT5TradingDataProvider` | Live read-only |
| API | `ReadService` | Map domain → Dashboard DTO |

### Luồng dữ liệu

```
MT5 Python object
    ↓ mapper (broker/mt5/mapper.py)
Domain model (AccountInfo, Position, ClosedTrade, Tick)
    ↓ ReadService
API Schema (Pydantic camelCase)
    ↓ HTTP JSON
Dashboard Zod validation
```

---

## 3. MT5 Read-only Client

File: `trading-engine/src/exness_bot/broker/mt5/read_only_client.py`

**Được phép:**

- `initialize` / `shutdown` / `login`
- `account_info` / `terminal_info`
- `symbol_info` / `symbol_info_tick` / `symbol_select`
- `positions_get` / `orders_get`
- `history_deals_get` / `history_orders_get`
- `copy_rates_*` / `symbols_get`

**Không có:** `order_send`

Trading engine tiếp tục dùng `MT5TradingClient` (`MT5Client` alias) cho execution.

---

## 4. TradingDataProvider

Factory: `create_trading_data_provider(settings)`  
File: `trading-engine/src/exness_bot/data/factory.py`

| `DATA_SOURCE` | Provider | Mô tả |
|---------------|----------|--------|
| `mock` (default) | `MockTradingDataProvider` | Dữ liệu mock, không cần MT5 |
| `backtest` | `BacktestTradingDataProvider` | Không live; backtest qua JSON riêng |
| `mt5` | `MT5TradingDataProvider` | Đọc MT5 thật (Windows) |

---

## 5. Cấu hình

```env
# Chế độ dữ liệu
DATA_SOURCE=mock          # mock | backtest | mt5

# MT5 (chỉ khi DATA_SOURCE=mt5)
MT5_ENABLED=false
MT5_LOGIN=
MT5_PASSWORD=
MT5_SERVER=Exness-MT5Trial
MT5_PATH=C:/Program Files/MetaTrader 5/terminal64.exe
MT5_TIMEOUT=30
MT5_SYMBOL=                # optional — resolve XAUUSD → XAUUSDm

# Symbol canonical cho Dashboard
SYMBOL=XAUUSD
TIMEFRAME=M15
```

**Bảo mật:**

- Không đưa `MT5_PASSWORD` vào `NEXT_PUBLIC_*`
- API không trả password, token, credentials
- Password không được log

---

## 6. Vòng đời kết nối

`MT5ConnectionManager`:

1. **Lazy** — không connect khi import API
2. **Thread-safe** — `threading.RLock`
3. **Single-process MVP** — không connection pool phức tạp
4. Trạng thái: `CONNECTED` | `DISCONNECTED` | `UNAVAILABLE` | `ERROR`

Khi `DATA_SOURCE=mt5` trên Linux → `UNAVAILABLE`, API vẫn chạy; `/account` trả `503 BROKER_UNAVAILABLE`.

---

## 7. Symbol resolution

Canonical symbol (`SYMBOL=XAUUSD`) được expose ra Dashboard.

Broker symbol thực tế (vd. `XAUUSDm`) được resolve nội bộ qua `broker/mt5/symbol_resolver.py`.

Positions/trades/tick luôn trả `symbol: "XAUUSD"` cho frontend.

---

## 8. Hành vi theo endpoint

| Endpoint | mock | mt5 connected | mt5 unavailable |
|----------|------|---------------|-----------------|
| `/health` | 200 | 200 | 200 |
| `/api/v1/status` | CONNECTED | CONNECTED | DISCONNECTED |
| `/api/v1/account` | mock data | MT5 account | 503 |
| `/api/v1/positions` | mock positions | MT5 positions | 503 |
| `/api/v1/trades` | mock trades | history_deals | 503 |
| `/api/v1/backtests` | JSON files | JSON files | JSON files |

Timestamps: ISO-8601 UTC (`updatedAt` trên account/risk).

---

## 9. Linux vs Windows

### Linux (development)

```bash
DATA_SOURCE=mock
exness-bot-api
```

- API start bình thường
- Mock + backtest hoạt động
- `DATA_SOURCE=mt5` → graceful failure, không crash

### Windows + MT5

**Yêu cầu:**

- Windows với MetaTrader 5 cài đặt
- Tài khoản Exness đã login trong terminal
- Python 3.12 + `pip install MetaTrader5`
- AutoTrading **có thể OFF** — phase này read-only

```bash
DATA_SOURCE=mt5
MT5_ENABLED=true
MT5_LOGIN=...
MT5_PASSWORD=...
MT5_SERVER=Exness-MT5Trial
exness-bot-api
```

Dashboard:

```env
NEXT_PUBLIC_DATA_SOURCE=api
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

---

## 10. Polling Dashboard (Phase 10.6)

Chưa có WebSocket. Dashboard dùng React Query polling:

| Dữ liệu | Interval gợi ý |
|---------|-----------------|
| status | 5–10s |
| account | 5–10s |
| positions | 2–5s |
| trades | 10–30s |

Cấu hình interval trong Dashboard queries (phase sau có thể centralize).

---

## 11. Kiểm thử

```bash
cd trading-engine
pytest tests/unit/test_mt5_readonly.py
pytest tests/unit/test_trading_data_provider.py
pytest tests/api/test_mt5_mode_linux.py
pytest tests/api/test_readonly_api.py
```

Safety test xác minh read-only modules **không** chứa `def order_send` hoặc `.order_send(`.

---

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân | Cách xử lý |
|-------------|-------------|------------|
| `503 BROKER_UNAVAILABLE` | MT5 không chạy / Linux | Dùng `DATA_SOURCE=mock` hoặc chuyển Windows |
| `UNAVAILABLE` on Windows | Package chưa cài | `pip install MetaTrader5` |
| Symbol not found | Sai tên symbol | Set `MT5_SYMBOL` hoặc kiểm tra Market Watch |
| Login failed | Sai credentials | Kiểm tra `.env`, không commit password |
| Empty trades | Không có deals trong range | Mở rộng query `start`/`end` |

---

## 13. Giới hạn phase này

- Không có strategy execution loop live
- Không WebSocket streaming
- Không authentication API
- Trade history từ `history_deals_get` — chưa có SQLite journal
- Risk limits dùng config + snapshot, chưa sync đầy đủ với engine loop

---

## 14. Phase tiếp theo (10.7 gợi ý)

1. Live strategy signal từ engine loop (shared state)
2. Trade journal persistent (SQLite read API)
3. WebSocket/SSE cho equity/status
4. API authentication
5. Polling intervals configurable tập trung
