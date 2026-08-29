# API Contract — Dashboard ↔ Trading Engine

Tài liệu mô tả **ranh giới tích hợp read-only** giữa Next.js Dashboard và Trading Engine (FastAPI — triển khai ở phase sau).

Dashboard **không** import code từ `trading-engine/`. Mọi giao tiếp đi qua HTTP JSON theo contract này.

---

## 1. Nguyên tắc

| Quy tắc | Mô tả |
|---------|--------|
| Read-only | Không có endpoint đặt lệnh, sửa SL/TP, đổi risk, start/stop bot |
| ISO-8601 UTC | Mọi timestamp dạng `2026-08-29T10:30:00Z` |
| Số học | Giá trị tài chính là `number`, không format chuỗi |
| Enum ổn định | `RUNNING`, `BUY`, `COMPLETED` — không dịch trong JSON |
| Envelope thống nhất | Một format `data` + `meta` cho success; `error` cho lỗi |
| Validation | Dashboard validate bằng Zod trước khi vào domain |

---

## 2. Base URL

```
{NEXT_PUBLIC_API_BASE_URL}/api/v1/...
```

Mặc định development: `http://localhost:8000`

---

## 3. Response envelope

### Success — tài nguyên đơn

```json
{
  "data": { },
  "meta": {}
}
```

`meta` là optional.

### Success — danh sách có phân trang

```json
{
  "data": [],
  "meta": {
    "page": 1,
    "pageSize": 50,
    "total": 250
  }
}
```

### Error

```json
{
  "error": {
    "code": "BOT_NOT_CONNECTED",
    "message": "Bot hiện chưa kết nối.",
    "details": {}
  }
}
```

- `code`: mã kỹ thuật (tiếng Anh, UPPER_SNAKE)
- `message`: mô tả cho operator (tiếng Việt)
- `details`: optional, dành cho debug

---

## 4. HTTP status

| Status | Ý nghĩa |
|--------|---------|
| 200 | Thành công |
| 400 | Tham số không hợp lệ |
| 401 | Chưa xác thực |
| 403 | Không có quyền |
| 404 | Không tìm thấy |
| 409 | Xung đột trạng thái |
| 429 | Quá nhiều request |
| 500 | Lỗi server |
| 503 | Dịch vụ không khả dụng (vd. Bot chưa kết nối MT5) |

---

## 5. Endpoints

### GET `/api/v1/status`

**Mục đích:** Trạng thái phiên vận hành (Bot, kết nối MT5, mode, account label).

**Response `data`:** `SessionContext`

```json
{
  "data": {
    "tradingMode": "DEMO",
    "connectionStatus": "CONNECTED",
    "accountLabel": "Demo #12345678",
    "botStatus": "RUNNING"
  }
}
```

**Lỗi có thể gặp:** `BOT_NOT_CONNECTED`, `503`

---

### GET `/api/v1/account`

**Mục đích:** Snapshot tài khoản hiện tại.

**Response `data`:** `AccountSnapshot`

```json
{
  "data": {
    "balance": 10842.5,
    "equity": 10956.3,
    "todayPnl": 124.8,
    "totalPnl": 842.5,
    "drawdownPct": 1.82,
    "margin": 412.0,
    "freeMargin": 10544.3,
    "currency": "USD",
    "updatedAt": "2026-08-29T10:30:00Z"
  }
}
```

---

### GET `/api/v1/overview`

**Mục đích:** Tổng hợp trang Tổng quan (giảm số request từ browser).

**Response `data`:** `DashboardOverview`

Gồm: `botStatus`, `account`, `equityCurve`, `positions`, `recentTrades`, `currentSignal`.

---

### GET `/api/v1/positions`

**Mục đích:** Vị thế đang mở.

**Response:** danh sách phân trang `Position[]`

```json
{
  "data": [
    {
      "id": "pos-1",
      "symbol": "XAUUSD",
      "direction": "LONG",
      "volume": 0.12,
      "entryPrice": 2348.5,
      "currentPrice": 2354.2,
      "stopLoss": 2336.0,
      "takeProfit": 2373.0,
      "unrealizedPnl": 68.4,
      "rMultiple": 0.48,
      "openedAt": "2026-08-29T08:00:00Z"
    }
  ],
  "meta": { "page": 1, "pageSize": 50, "total": 1 }
}
```

---

### GET `/api/v1/trades`

**Mục đích:** Nhật ký giao dịch đã đóng.

**Query parameters (tương lai — contract sẵn sàng):**

| Param | Type | Mô tả |
|-------|------|--------|
| `page` | int | Trang (bắt đầu 1) |
| `pageSize` | int | Số bản ghi/trang |
| `symbol` | string | vd. `XAUUSD` |
| `direction` | enum | `LONG` \| `SHORT` |
| `strategy` | string | vd. `ema_rsi_atr_v1` |
| `result` | enum | `WIN` \| `LOSS` |
| `start` | ISO date | Lọc từ ngày |
| `end` | ISO date | Lọc đến ngày |

**Response:** danh sách phân trang `Trade[]`

---

### GET `/api/v1/strategy`

**Mục đích:** Trạng thái chiến lược và tín hiệu.

**Response `data`:** `StrategySnapshot`

---

### GET `/api/v1/risk`

**Mục đích:** Giới hạn rủi ro và utilization.

**Response `data`:** `RiskSnapshot`

---

### GET `/api/v1/settings`

**Mục đích:** Cấu hình hệ thống (read-only).

**Response `data`:** `SystemSettings`

---

### GET `/api/v1/backtests`

**Mục đích:** Danh sách báo cáo backtest.

**Query parameters:**

| Param | Type | Mô tả |
|-------|------|--------|
| `page` | int | Trang |
| `pageSize` | int | Kích thước trang |
| `strategy` | string | Lọc chiến lược |
| `symbol` | string | Lọc symbol |
| `timeframe` | string | Lọc timeframe |

**Response:** danh sách phân trang `BacktestReport[]` (summary-level hoặc full — server có thể trả summary rồi detail qua `:id`)

> **Lưu ý:** Dashboard domain dùng **một** `BacktestReport` cho cả list và detail. Server nên trả cùng schema; list có thể omit các field nặng (`equityCurve`, `trades`) nếu document rõ — hoặc luôn trả full (phase server quyết định).

---

### GET `/api/v1/backtests/:id`

**Mục đích:** Chi tiết một lần chạy backtest.

**Response `data`:** `BacktestReport`

**404:** `{ "error": { "code": "NOT_FOUND", "message": "Không tìm thấy báo cáo Backtest." } }`

---

## 6. Domain objects

Schema Zod đầy đủ nằm tại `dashboard/domain/schemas.ts`.

Các object chính:

- `SessionContext`
- `AccountSnapshot`
- `DashboardOverview`
- `Position`
- `Trade`
- `StrategySnapshot`
- `RiskSnapshot`
- `SystemSettings`
- `BacktestReport`

Không tạo duplicate type (`ApiPosition`, `DashboardPosition`, …).

---

## 7. Mã lỗi gợi ý

| code | message (VI) |
|------|----------------|
| `BOT_NOT_CONNECTED` | Bot hiện chưa kết nối. |
| `NOT_FOUND` | Không tìm thấy tài nguyên yêu cầu. |
| `VALIDATION_FAILED` | Dữ liệu phản hồi không hợp lệ. |
| `RATE_LIMITED` | Quá nhiều yêu cầu. Vui lòng thử lại sau. |
| `INTERNAL_ERROR` | Lỗi máy chủ nội bộ. |

---

## 8. Bảo mật

- **Không** đưa MT5 password, API key, broker credentials vào `NEXT_PUBLIC_*`
- Browser chỉ gọi API read-only
- Trading Engine chạy private; MT5 credentials chỉ ở server Python

```
Browser → Dashboard (Next.js) → HTTP API → Trading Engine → MT5
```

---

## 9. Chế độ Dashboard

| Biến môi trường | Giá trị | Hành vi |
|-----------------|---------|---------|
| `NEXT_PUBLIC_DATA_SOURCE` | `mock` (default) | `MockTradingRepository` |
| `NEXT_PUBLIC_DATA_SOURCE` | `api` | `ApiTradingRepository` → HTTP |
| `NEXT_PUBLIC_API_BASE_URL` | URL | Base URL API |

Factory: `createTradingRepository()` — **một** điểm chọn implementation.

---

## 10. Không thuộc scope phase này

- POST/PUT/PATCH/DELETE (mutation)
- WebSocket streaming
- Authentication implementation (contract 401/403 đã chuẩn bị)

**Đã triển khai (Phase 10.5):** Python FastAPI read-only server tại `trading-engine/src/exness_bot/api/`.

Khởi chạy:

```bash
cd trading-engine
pip install -e ".[api,dev]"
exness-bot-api
# hoặc: uvicorn exness_bot.api.app:app --host 127.0.0.1 --port 8000
```

Health: `GET http://localhost:8000/health`  
OpenAPI: `http://localhost:8000/docs`
