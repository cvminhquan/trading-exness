# Product Requirements Document — Exness Trading Bot

## 1. Tổng quan

Hệ thống giao dịch thuật toán cá nhân kết nối tài khoản Exness qua MetaTrader 5 (MT5). Mục tiêu là xây dựng engine modular, có thể test, an toàn — mặc định chạy trên tài khoản Demo và không bao giờ đặt lệnh live trừ khi được bật rõ ràng.

**Phiên bản tài liệu:** 0.1.0 (Foundation)  
**Ngày:** 2026-08-29  
**Trạng thái:** Khởi tạo dự án — chưa triển khai logic giao dịch đầy đủ

---

## 2. Mục tiêu sản phẩm

| # | Mục tiêu | Mô tả |
|---|----------|-------|
| 1 | Kết nối MT5 | Đăng nhập tài khoản Exness qua MT5 Python API |
| 2 | Dữ liệu thị trường | Lấy OHLCV theo symbol và timeframe |
| 3 | Chỉ báo kỹ thuật | Tính EMA, RSI, ATR |
| 4 | Tín hiệu giao dịch | Strategy sinh signal, không đặt lệnh trực tiếp |
| 5 | Quản lý rủi ro | Risk Manager có quyền từ chối signal hợp lệ |
| 6 | Thực thi lệnh | Order Manager là module duy nhất submit order |
| 7 | Theo dõi vị thế | Track positions và lịch sử giao dịch |
| 8 | Backtest | Chạy strategy trên dữ liệu lịch sử |
| 9 | Demo an toàn | Mặc định Demo / Dry-run |
| 10 | VPS-ready | Thiết kế để deploy production sau này |

---

## 3. Phạm vi V1

### 3.1 Instrument & Timeframe

- **Symbol:** XAUUSD (Gold)
- **Timeframe:** M15 (15 phút)

### 3.2 Chỉ báo

| Chỉ báo | Tham số |
|---------|---------|
| EMA | 20, 50, 200 |
| RSI | 14 |
| ATR | 14 |

### 3.3 Strategy (định hướng)

- **Xu hướng:** EMA alignment (EMA20 > EMA50 > EMA200 cho long; ngược lại cho short)
- **Xác nhận:** RSI (ngưỡng cụ thể — xem `TRADING_RULES.md`)
- **Stop loss:** Dựa trên ATR (hệ số nhân — xem `TRADING_RULES.md`)

### 3.4 Quản lý rủi ro

| Quy tắc | Giá trị mặc định |
|---------|------------------|
| Rủi ro mỗi lệnh | Tối đa 0.5% equity |
| Giới hạn lỗ ngày | Cấu hình được (mặc định 2%) |
| Giới hạn drawdown | Cấu hình được (mặc định 5%) |
| Số vị thế mở tối đa | Cấu hình được (mặc định 1) |

---

## 4. Ràng buộc an toàn (Bắt buộc)

1. **Mặc định DEMO / DRY-RUN:** `TRADING_MODE=demo` và `DRY_RUN=true` khi không cấu hình.
2. **Live trading yêu cầu flag rõ ràng:** `TRADING_MODE=live` **và** `ALLOW_LIVE_TRADING=true`.
3. **Nhiều lớp guard:** Config validation, Order Manager pre-flight checks, broker adapter guards.
4. **Không hardcode credentials:** MT5 login qua biến môi trường hoặc file `.env` (không commit).
5. **Không hardcode lot size:** Position sizing tính từ risk % và stop distance.

---

## 5. Kiến trúc luồng dữ liệu

```
Market Data → Strategy → Signal → Risk Manager → Order Manager → MT5
```

- Strategy **không** gọi MT5 trực tiếp.
- Risk Manager **có thể reject** signal hợp lệ.
- Order Manager **duy nhất** submit order.
- Broker integration **tách biệt** qua abstraction (`BrokerPort`).

---

## 6. Công nghệ

### 6.1 Trading Engine

| Thành phần | Công nghệ |
|------------|-----------|
| Runtime | Python 3.12+ |
| Broker API | MetaTrader5 |
| Data / Math | pandas, numpy |
| Validation | pydantic |
| Testing | pytest |
| Lint | ruff |
| Type check | mypy |

### 6.2 Database

- PostgreSQL — lưu trades, signals, risk events, backtest runs (schema chi tiết ở phase sau)

### 6.3 Infrastructure

- Docker + Docker Compose (PostgreSQL, engine container sau này)

### 6.4 Dashboard (tương lai)

- Next.js, TypeScript, Tailwind CSS, React Query

---

## 7. Personas & Use Cases

### 7.1 Trader cá nhân (primary)

- Chạy bot trên Demo để validate strategy
- Xem log và kết quả backtest
- Chuyển sang live chỉ khi đã kiểm tra kỹ

### 7.2 Use Cases V1

| ID | Use Case | Priority |
|----|----------|----------|
| UC-01 | Kết nối MT5 Demo | P0 |
| UC-02 | Lấy dữ liệu XAUUSD M15 | P0 |
| UC-03 | Tính EMA/RSI/ATR | P0 |
| UC-04 | Sinh signal EMA trend + RSI | P0 |
| UC-05 | Validate signal qua Risk Manager | P0 |
| UC-06 | Đặt lệnh Demo (hoặc dry-run log) | P0 |
| UC-07 | Backtest strategy cơ bản | P1 |
| UC-08 | Lưu trade history vào PostgreSQL | P1 |
| UC-09 | Dashboard web | P2 (future) |

---

## 8. Non-Goals (V1)

- Multi-symbol / multi-timeframe
- Machine learning strategies
- Social/copy trading
- Mobile app
- Microservices architecture
- Live trading mặc định

---

## 9. Tiêu chí thành công V1

1. Engine kết nối được MT5 Demo và lấy được bars XAUUSD M15.
2. Strategy sinh signal đúng spec (unit test với dữ liệu mock).
3. Risk Manager reject được signal vi phạm giới hạn.
4. Order Manager không submit khi `DRY_RUN=true`.
5. Live order bị chặn khi thiếu `ALLOW_LIVE_TRADING=true`.
6. Backtest chạy được trên CSV/historical data (phase 2).
7. Test coverage cho domain models, config, safety guards ≥ 80% (foundation phase).

---

## 10. Rủi ro & Giảm thiểu

| Rủi ro | Mức | Giảm thiểu |
|--------|-----|------------|
| Lệnh live ngoài ý muốn | Cao | Multi-layer guards, default dry-run |
| MT5 disconnect | Trung bình | Reconnect logic, health checks |
| Slippage / spread | Trung bình | ATR-based SL, spread filter (future) |
| Over-trading | Trung bình | Daily loss limit, max positions |
| Data quality | Trung bình | Bar validation, gap detection (future) |

---

## 11. Ambiguities & Decisions Pending

Các quyết định chưa chốt — xem `TRADING_RULES.md` và `ROADMAP.md`:

1. Ngưỡng RSI cụ thể cho entry long/short
2. Hệ số ATR cho stop loss và take profit
3. Có trailing stop hay fixed TP không
4. Schema PostgreSQL chi tiết
5. Nguồn dữ liệu backtest (MT5 export vs third-party)
6. Tần suất poll bars (mỗi bar close vs tick)
7. Xử lý session/gap cuối tuần cho XAUUSD

---

## 12. Tài liệu liên quan

- [ARCHITECTURE.md](./ARCHITECTURE.md) — Kiến trúc kỹ thuật
- [TRADING_RULES.md](./TRADING_RULES.md) — Quy tắc giao dịch chi tiết
- [ROADMAP.md](./ROADMAP.md) — Lộ trình triển khai
