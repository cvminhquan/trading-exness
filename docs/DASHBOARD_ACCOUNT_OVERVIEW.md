# Dashboard Account Overview (Phase 15.X)

Tài liệu nguồn số liệu, công thức PnL và ranh giới an toàn cho màn **Tổng quan tài khoản**.

## Endpoints (chỉ đọc)

| Method | Path | Mục đích |
|--------|------|----------|
| `GET` | `/api/v1/account` | Snapshot legacy (giữ nguyên contract) |
| `GET` | `/api/v1/account/overview` | **Nguồn chính** cho Account Overview UI |
| `GET` | `/api/v1/account/pnl/daily?days=7` | Lịch sử **realized** PnL theo ngày UTC |
| `GET` | `/api/v1/positions` | Vị thế đang mở (read-only) |

Không có endpoint mutation / `order_send` trong feature này.

## Nguồn từng metric

| Metric | Nguồn |
|--------|--------|
| `balance`, `equity`, `margin`, `freeMargin`, `marginLevel`, `currency` | MT5 `account_info` (qua read-only provider) |
| `unrealizedPnl` | `sum(position.profit)` từ `positions_get` (toàn bộ vị thế) |
| `realizedPnlToday` | Deals / closed trades trong ngày UTC: `net = profit + swap + commission + fee` |
| `totalPnlToday` | `realizedPnlToday + unrealizedPnl` |
| `dailyReturnPct` | Chỉ khi reconstruct vốn đầu ngày đáng tin (xem bên dưới) |
| `server`, `tradeMode` | `account_info` |
| `loginMasked` | Login đã che (vd. `***4158`) — **không** trả password |
| `status`, `updatedAt`, `ageSeconds` | Freshness snapshot |

## Balance vs Equity

- **Balance**: số dư tài khoản broker (không gồm floating).
- **Equity**: balance + floating PnL hiện tại (theo broker).

## Realized vs Unrealized

- **Unrealized**: tổng `position.profit` của vị thế đang mở.
- **Realized hôm nay**: tổng NET từ deals / closed trades có thời điểm trong ngày UTC hiện tại.
- **Công thức NET mỗi deal/trade**:

```text
net = profit + swap + commission + fee
```

Chỉ tính deal `BUY`/`SELL`. Balance/credit **không** cộng vào realized trading PnL.
Entry deal thường có `profit≈0` nhưng có thể có commission — cộng commission/fee của cả IN và OUT khi ghép closed trade (mapper).

## Daily return

```text
daily_start_equity = equity - total_pnl_today
daily_return_pct   = total_pnl_today / daily_start_equity * 100
```

`dailyReturnPct` = `null` / `dailyReturnAvailable=false` khi:

- không đọc được cashflow nạp/rút trong ngày, hoặc
- có BALANCE/CREDIT trong ngày, hoặc
- `daily_start_equity <= 0`

Không bịa % gây hiểu nhầm.

## Freshness

`status` ∈ `LIVE` | `STALE` | `DISCONNECTED` | `UNAVAILABLE`

- `DISCONNECTED` / `UNAVAILABLE`: UI hiện “Dữ liệu tài khoản không khả dụng” + `ageSeconds`.
- `STALE`: vẫn hiện số liệu kèm cảnh báo thời gian cập nhật.
- Không giữ badge xanh `LIVE` khi mất kết nối.

Ngưỡng stale: `LIVE_DATA_STALE_SECONDS` (mặc định 10s).

## Refresh (Dashboard)

| Dữ liệu | Interval gợi ý |
|---------|----------------|
| Account overview | ~3s |
| Positions (overview/positions page) | ~3s |
| Daily realized history | ~60s |

Browser gọi API; backend đọc MT5 qua provider (không để browser gọi MT5 trực tiếp).

## Safety panel (status-only)

Hiển thị: Mode DEMO/REAL, Server, MT5 CONNECTED/DISCONNECTED, Algo Trading, Kill Switch ON/OFF, Execution Mode PAPER/LIVE.

**Không** có nút bật/tắt live hay đặt lệnh.

## Trade analysis (analysis-only)

Card phân tích rủi ro dùng equity + `riskPerTradePct` để ước lot / so với lot tối thiểu broker. Không submit lệnh.

## Bảo mật

API/UI không expose: `MT5_PASSWORD`, secrets, credentials thô. Login chỉ dạng masked.

## Kiểm thử

- Backend: `tests/unit/test_phase_15_account_overview.py`, `tests/api/test_phase_15_account_overview_api.py`
- Dashboard: `lib/format.account.test.ts`
