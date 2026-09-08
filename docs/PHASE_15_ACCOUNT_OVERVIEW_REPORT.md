# PHASE 15 — Account Overview & Dashboard Home

## Status

```text
PASS (feature delivered; no order_send / no auto-close)
```

**Ngày báo cáo:** 2026-09-07  
**Phạm vi phiên làm việc:** Account Overview + PnL, dọn UI home, trending quotes, phân tích rủi ro tài khoản nhỏ (~$10.50).  
**Tài liệu chi tiết số liệu:** [`docs/DASHBOARD_ACCOUNT_OVERVIEW.md`](./DASHBOARD_ACCOUNT_OVERVIEW.md)

---

## Objective

Làm rõ số liệu tài khoản Demo trên Dashboard (Balance / Equity / PnL hôm nay / freshness), giảm nhiễu UI trên `/dashboard`, và hiển thị phân tích rủi ro khi equity nhỏ vẫn **mở được** min lot broker — **không** đặt lệnh, **không** tự đóng vị thế.

---

## Đã làm

### 1. Backend — Account Overview & PnL (chỉ đọc)

| Hạng mục | Chi tiết |
|----------|----------|
| Package | `trading-engine/src/exness_bot/account_overview/` (`pnl.py`, `freshness.py`) |
| Endpoint mới | `GET /api/v1/account/overview` |
| Endpoint mới | `GET /api/v1/account/pnl/daily?days=7` |
| Legacy | `GET /api/v1/account` **giữ nguyên** contract |
| Positions snapshot | Đọc **toàn bộ** vị thế đang mở (không giới hạn 1 symbol) |

**Công thức chính**

- Realized NET (deal/trade): `profit + swap + commission + fee` (chỉ BUY/SELL)
- Unrealized: `Σ position.profit`
- Total hôm nay: `realized + unrealized`
- `dailyReturnPct`: chỉ khi reconstruct vốn đầu ngày đáng tin; ngược lại `null`
- Freshness: `LIVE` \| `STALE` \| `DISCONNECTED` \| `UNAVAILABLE`

**Tests**

- `trading-engine/tests/unit/test_phase_15_account_overview.py`
- `trading-engine/tests/api/test_phase_15_account_overview_api.py`

---

### 2. Dashboard — Account Overview UI

| Thành phần | Path |
|------------|------|
| Section số liệu | `dashboard/components/account/AccountOverviewSection.tsx` |
| Safety panel (status-only) | `dashboard/components/account/AccountSafetyPanel.tsx` |
| Biểu đồ realized 7 ngày | `dashboard/components/account/RealizedPnlChart.tsx` |
| Card phân tích rủi ro | `dashboard/components/account/TradeAnalysisRiskCard.tsx` |
| Schema / hooks / repo | `accountOverviewSchema`, `useAccountOverview`, `useDailyRealizedPnl`, API paths |
| Format tests | `dashboard/lib/format.account.test.ts` |

Safety panel hiển thị Mode / Server / MT5 / Algo / Kill Switch / Execution Mode — **không** có nút bật live hay đặt lệnh.

---

### 3. UX home — dọn và bố cục lại `/dashboard`

Các thay đổi theo phản hồi người dùng (declutter):

- Bỏ khối metric trùng “Tài khoản broker”, Drawdown/leverage trên home
- Header gọn: account cạnh switch Demo/Thật (`server · ***login`); bỏ Nguồn API / PAPER ONLY dài
- Bỏ banner paper trên home; bỏ equity curve + signal khỏi home
- Vị thế đang mở **giữ trên home**; lịch sử giao dịch đóng không nằm trên home
- Bỏ badge freshness “Live” trên overview (tránh nhầm với live trading; tài khoản là **Demo**)

**Bố cục home hiện tại**

1. Account overview (metrics + realized/unrealized/margin level)
2. Trending quotes \| Safety + Risk analysis
3. Bảng vị thế đang mở
4. Biểu đồ realized PnL 7 ngày

File chính: `dashboard/app/dashboard/page.tsx`

---

### 4. Trending quotes (giá theo dõi)

| File | Vai trò |
|------|---------|
| `dashboard/components/market/TrendingQuotesCard.tsx` | Top symbols + thêm symbol |
| `dashboard/lib/market/trending.ts` | Logic danh sách trending |
| `dashboard/lib/market/trending.test.ts` | Tests |
| Repo | `getQuotes(symbols?)` qua API quotes hiện có |

---

### 5. Phân tích rủi ro tài khoản ~$10.50

**Yêu cầu:** Với equity ~$10.5, **0.01 lot vẫn được mở** (min broker). Không coi là “không mở được”. Hiển thị rủi ro thực tế và **thiếu** so với % cấu hình.

| File | Vai trò |
|------|---------|
| `dashboard/lib/risk/sizing.ts` | `estimateRiskSizing()` |
| `dashboard/lib/risk/sizing.test.ts` | Tests |
| `TradeAnalysisRiskCard.tsx` | UI + badge “0.01 lot: mở được” |

**Ví dụ minh họa** (equity `$10.50`, risk `0.5%`, stop×contract `5×100`):

| Metric | Giá trị |
|--------|---------|
| Ngân sách theo % | ≈ `$0.05` |
| Lot theo % cấu hình | `0.000` |
| Min lot broker | `0.01` (mở được) |
| Rủi ro nếu lấy 0.01 | ≈ `$5.00` (~47.6% equity) |
| Thiếu so với ngân sách | ≈ `$4.95` |

**Lưu ý:** stop distance / contract size đang **hardcode minh họa**, chưa lấy ATR từ chiến lược.

---

## Không làm / đã hủy

| Hạng mục | Kết luận |
|----------|----------|
| Đóng vị thế từ `/dashboard/positions` | Đã khảo sát (API hiện read-only; close nằm ở engine nhưng chưa HTTP) → **user bỏ qua** |
| Tự đóng vị thế đang mở | **Không** triển khai; bot/API không auto-close qua dashboard |
| `order_send` / mutation qua Account Overview | **Không** — feature chỉ đọc |

---

## Ranh giới an toàn

- API Account Overview / daily PnL / positions: **read-only**
- Không expose password / secrets; login masked
- Dashboard không gọi MT5 trực tiếp
- Card rủi ro: analysis-only, không submit lệnh

---

## File / docs liên quan

| Loại | Path |
|------|------|
| Spec số liệu | `docs/DASHBOARD_ACCOUNT_OVERVIEW.md` |
| Backend package | `trading-engine/src/exness_bot/account_overview/` |
| Routes | `trading-engine/src/exness_bot/api/routes/v1.py` |
| Home UI | `dashboard/app/dashboard/page.tsx` |
| Report này | `docs/PHASE_15_ACCOUNT_OVERVIEW_REPORT.md` |

---

## Kiểm thử đã có

- Backend unit + API Phase 15
- Dashboard: `format.account.test.ts`, `sizing.test.ts`, `trending.test.ts`

*(Không chạy lại full suite trong bước xuất report này.)*

---

## Việc còn mở (ngoài phạm vi đã giao)

- Gắn stop distance / contract size risk card với ATR / symbol specs thật
- (Tuỳ chọn) HTTP manual close position — đã hủy theo yêu cầu user
- Commit git — **chưa** được yêu cầu trong phiên này
