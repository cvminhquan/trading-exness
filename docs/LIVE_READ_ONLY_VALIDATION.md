# Phase 10.7 — Live Read-only Validation

Tài liệu xác nhận pipeline **chỉ đọc** từ Exness/MT5 tới Dashboard. Không chứa mật khẩu, API key, hay credential.

```
Exness
  → MetaTrader 5
  → MT5ReadOnlyClient
  → TradingDataProvider
  → Python API (FastAPI)
  → Next.js Dashboard
```

Phase này **không** triển khai khớp lệnh.

---

## 1. Môi trường kiểm thử

| Thành phần | Giá trị |
|------------|---------|
| OS live | Windows 10/11 |
| Broker | Exness (MT5) |
| Terminal | MetaTrader 5 |
| Canonical symbol | `XAUUSD` |
| Broker symbol (thực tế) | `XAUUSDm` (resolver tự map; Dashboard chỉ thấy `XAUUSD`) |
| Timeframe nghiên cứu | M15 (không đổi trong phase này) |
| Engine API | `http://127.0.0.1:8000` |
| Dashboard | `http://localhost:3000` |
| Ngưỡng giá cũ | `LIVE_DATA_STALE_SECONDS=10` |

Tài khoản demo/thật được cấu hình trong `trading-engine/.env` (không ghi login/password vào tài liệu này).

---

## 2. Linux / Windows

| Vai trò | Linux | Windows |
|---------|-------|---------|
| `DATA_SOURCE=mock` | Có | Có |
| Backtest / pytest | Có | Có |
| API + Dashboard development | Có | Có |
| MetaTrader 5 + Exness live | Không | Có |
| `DATA_SOURCE=mt5` | API sống; live endpoints `BROKER_UNAVAILABLE` / quote `UNAVAILABLE` | Live read-only |

Repository vẫn portable: không import `MetaTrader5` trên Linux trong đường đi mock/backtest.

Dashboard:

| `NEXT_PUBLIC_DATA_SOURCE` | Hành vi |
|--------------------------|---------|
| `mock` | `MockTradingRepository` — không cần API/MT5 |
| `api` | `ApiTradingRepository` — **không** fallback mock khi API/MT5 lỗi |

Khi engine `DATA_SOURCE=mt5`, Dashboard phải dùng `NEXT_PUBLIC_DATA_SOURCE=api`. Factory engine không bao giờ trả `MockTradingDataProvider` ở mode MT5.

---

## 3. Ranh giới an toàn

Forbidden trên API / provider / Dashboard:

- `order_send`
- đóng vị thế
- sửa SL/TP
- hủy lệnh
- start/stop bot
- đổi strategy / risk (ngoài đọc cấu hình)

**POST duy nhất:** `POST /api/v1/accounts/active` — đổi login MT5 để **xem** demo/thật. Không đặt lệnh.

### Code execution đã tồn tại (không reachable từ API)

| Vị trí | API |
|--------|-----|
| `trading-engine/src/exness_bot/broker/mt5/trading_client.py` | `order_send` |
| `trading-engine/src/exness_bot/broker/mt5/adapter.py` | gọi `order_send` |
| `trading-engine/src/exness_bot/broker/mt5/mapper.py` | `TRADE_ACTION_DEAL`, `TRADE_ACTION_SLTP` (build dict) |
| `trading-engine/src/exness_bot/orders/manager.py` | modify SL/TP (engine loop, không phải HTTP) |

Không có trong: `read_only_client.py`, `connection_manager.py`, `mt5_provider.py`, `data/freshness.py`, `api/routes/v1.py`, `api/services/account_runtime.py`.

`TRADE_ACTION_PENDING` / `TRADE_ACTION_REMOVE` / `order_check` không xuất hiện trên đường read-only.

---

## 4. Bước validation

1. Windows: mở MT5, login Exness (demo hoặc thật — chỉ đọc).
2. Engine: `DATA_SOURCE=mt5`, `MT5_ENABLED=true`.
3. `exness-bot-api` (hoặc uvicorn `127.0.0.1:8000`).
4. Dashboard: `NEXT_PUBLIC_DATA_SOURCE=api`, `npm run dev`.
5. `GET /health` → `{ "status": "ok" }`.
6. `GET /api/v1/quotes?symbols=XAUUSD` → bid/ask/last/spread, `updatedAt` UTC, `freshness`.
7. `GET /api/v1/account` so với cửa sổ Account MT5.
8. `GET /api/v1/positions` — bot **không** mở lệnh. Chỉ đọc vị thế có sẵn hoặc vị thế demo mở thủ công trên MT5.
9. `GET /api/v1/trades` so với History MT5.
10. Dashboard: header `MT5 đã kết nối` + `Dữ liệu live`; watchlist `XAUUSD` (không suffix).
11. Ngắt MT5: `/health` vẫn 200; `/account` → `503 BROKER_UNAVAILABLE`; header `MT5 mất kết nối`; quotes `UNAVAILABLE` (không số mock).
12. Mở lại MT5: polling tự `connect()` lại — **không** cần restart API nếu IPC MT5 còn sống.
13. `DATA_SOURCE=mock`: Dashboard/API chạy không cần MT5.
14. `pytest` backtest không đổi tham số chiến lược.

---

## 5. Mapping giá trị

### 5.1 Symbol

Canonical `XAUUSD` → broker `XAUUSDm` (Exness cent/mini naming). API/Dashboard chỉ trả `XAUUSD`.

### 5.2 Quote

| Field | Nguồn |
|-------|--------|
| bid / ask / last | `symbol_info_tick` |
| spread | `ask - bid` |
| updatedAt | `tick.time` → UTC ISO-8601 `Z` |
| freshness | `LIVE` nếu tuổi ≤ `LIVE_DATA_STALE_SECONDS`; không thì `STALE`; không tick → `UNAVAILABLE` |
| last = 0 | fallback mid(bid, ask) |

### 5.3 Account (`GET /api/v1/account`)

| API | MT5 |
|-----|-----|
| `balance` | Balance |
| `equity` | Equity |
| `profit` | Profit (PnL thả nổi tài khoản) |
| `currency` | Currency |
| `leverage` | Leverage |
| `margin` | Margin |
| `freeMargin` | Free margin |
| `marginLevel` | Margin level (%) |

**Khác biệt có chủ đích (không phải bug mapping tick):**

- `todayPnl` lấy từ equity − `day_start_equity` (risk state), **không** phải ô “Daily” của MT5 nếu chưa có journal intra-day.
- `totalPnl` so với equity mặc định cấu hình, **không** phải Profit toàn vòng đời tài khoản MT5.
- `drawdownPct` từ peak equity risk state.

So sánh live nên dùng: Balance, Equity, Profit, Margin, Free margin, Leverage, Currency.

Không expose login password. Label phiên có dạng `Server #login` (login là số tài khoản công khai trên terminal).

### 5.4 Position

ticket, symbol (canonical), direction, volume, entry, current, SL, TP, floating PnL, swap, open time UTC.

Bot **không** tạo và **không** đóng vị thế. Validation thủ công: mở/đóng trên MT5.

### 5.5 Trade history

Deal ID / ticket, symbol canonical, direction, volume, entry/exit, profit, commission, swap, `closedAt` UTC. Gộp từ `history_deals_get` (IN+OUT). Có thể lệch vài mili/giây so với terminal vì polling.

---

## 6. Dashboard UX

| Trạng thái | UI |
|------------|-----|
| MT5 Connected | Badge xanh `MT5 đã kết nối` |
| Data Live | `Dữ liệu live` (freshness `LIVE`) |
| Data Stale | `Dữ liệu cũ` — **không** gắn nhãn live |
| MT5 Disconnected | Badge đỏ `MT5 mất kết nối` |
| Quote unavailable | `Không khả dụng` — không vẽ giá giả |

Polling React Query: quotes 2s, positions 3s, account/status/overview 5s, trades 15s. Không WebSocket.

---

## 7. Mất kết nối / kết nối lại

| Bước | Kỳ vọng |
|------|---------|
| Đóng MT5 / mất IPC | `GET /health` = 200. Live account/positions/trades → `503 BROKER_UNAVAILABLE`. Status `DISCONNECTED`. Quotes `freshness=UNAVAILABLE`. |
| Mở lại MT5 | Request sau đó gọi `health_check` + `connect()`. Dashboard tự hồi phục nhờ polling. |

**Giới hạn:** Nếu Python `MetaTrader5` IPC kẹt sau khi kill process API khi terminal đang mở, có thể phải mở lại MT5 và/hoặc restart API. Không có connection manager phức tạp hơn lazy connect + health check.

---

## 8. Kiểm thử tự động (không cần MT5)

```bash
cd trading-engine
pytest
ruff check src tests
mypy src
```

Phủ: mapping giá/account/position/trade, UTC, freshness LIVE/STALE/UNAVAILABLE, disconnected, factory không fallback mock, schema API, không mutation route.

Dashboard:

```bash
cd dashboard
npx tsc --noEmit
npx vitest run
```

---

## 9. Checklist thủ công

- [x] MT5 connected
- [x] XAUUSD resolved (`XAUUSDm` phía broker, `XAUUSD` phía Dashboard)
- [x] Real bid received
- [x] Real ask received
- [x] Spread correct (`ask - bid`)
- [x] Timestamp UTC
- [x] Account matches MT5 (balance / equity / profit / margin)
- [x] Positions match MT5 (3 SHORT thủ công trên demo; bot không mở)
- [x] Trade history matches MT5 (deals UTC; heuristic exitReason)
- [x] Dashboard receives live data
- [x] Polling works
- [x] Disconnect handled (`/health` 200, live 503 / UNAVAILABLE, không mock)
- [x] Reconnect handled (polling + one-shot initialize)
- [x] Mock mode still works (`DATA_SOURCE=mock` tests)
- [x] Backtest still works (pytest baseline + API list)
- [x] No trading API reachable

---

## 10. Giá trị quan sát (live, 2026-08-29)

Phiên demo Exness MT5 Trial. Không ghi password. Thị trường vàng/FX đóng cửa (thứ Bảy) nên tick XAUUSD được gắn **STALE** — đúng spec, không gắn LIVE.

| Mục | MT5 / broker | API | Dashboard |
|-----|--------------|-----|-----------|
| Canonical symbol | `XAUUSDm` | `XAUUSD` | `XAUUSD` |
| Bid | 4456.134 | 4456.134 | 4456.134 |
| Ask | 4456.394 | 4456.394 | 4456.394 |
| Spread | 0.26 | 0.26 | 0.26 |
| last | 0 trên tick → mid | 4456.264 | 4456.264 |
| `updatedAt` | unix UTC | `...Z` | UTC |
| `freshness` XAUUSD | — | `STALE` (weekend) | DỮ LIỆU CŨ |
| BTCUSD / ETHUSD | crypto 24/7 | `LIVE` | DỮ LIỆU LIVE (hàng) |
| Balance | 8161.76 | 8161.76 | $8,161.76 |
| Equity | 41177.56 | 41177.56 | $41,177.56 |
| Profit | 33015.8 | 33015.8 | khớp PnL thả nổi |
| Leverage | 1:200 | 200 | 1:200 |
| Margin / free | 6849.67 / 34327.89 | cùng | cùng |
| Positions | 3 SHORT 1.0 lot XAU (thủ công) | 3 rows canonical | 3 rows, bot không mở/đóng |
| Trades | history deals | 227 records UTC | nhật ký |
| Disconnect `/health` | — | 200 | — |
| Disconnect live | IPC -6 trước khi sửa initialize | 503 `BROKER_UNAVAILABLE`, quotes `UNAVAILABLE` | không hiện mock |
| Reconnect | initialize(path+login) một lần | `CONNECTED` không restart MT5 | polling tự hồi phục |

**todayPnl** API = $0 vì chưa có day_start_equity journal — khác ô Daily MT5. **totalPnl** so với equity mặc định cấu hình.

---

## 11. Lệnh validation

```bash
# Engine
cd trading-engine
pytest
ruff check src tests
mypy src
exness-bot-api

# Dashboard
cd dashboard
npx tsc --noEmit
npm run dev
```

Live (Windows, API đang chạy):

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/quotes?symbols=XAUUSD
curl http://127.0.0.1:8000/api/v1/account
curl http://127.0.0.1:8000/api/v1/status
curl http://127.0.0.1:8000/api/v1/positions
curl http://127.0.0.1:8000/api/v1/trades
```

---

## 12. Giới hạn còn lại

- Không có execution / strategy loop live.
- Không WebSocket; độ trễ = interval polling + tick MT5.
- `todayPnl` / `totalPnl` / drawdown không đồng nhất 1-1 với mọi ô thống kê MT5.
- `botStatus=RUNNING` khi broker connected — phản ánh kênh đọc, không phải bot đang đặt lệnh.
- Reconnect tự động qua polling; `initialize(path)` rồi `login()` tách bước có thể lỗi IPC `-6 Authorization failed` trên Exness. Client read-only truyền login trong **một** `initialize()`.
- Tick `last=0` (phổ biến trên XAU) → mid(bid, ask).
- Weekend: XAUUSD/FX `STALE`; crypto có thể vẫn `LIVE`. Header freshness theo XAUUSD.
- Heuristic `exitReason` trên history deals có thể gán `take_profit` cho lệnh đóng thủ công — không đổi giả định backtest.
- Vị thế validation dùng vị thế thủ công đã có trên demo; bot không tạo/đóng.
