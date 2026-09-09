# PHASE 17.2.5D REPORT — Bright Modern Visual Redesign

**Ngày:** 2026-09-09  
**Trạng thái:** PASS (UI-only)  
**Direction:** White / cool-gray canvas + rounded cards + Financial Blue `#2563EB`  
**Reference:** Mockup approved (fintech / CMC clarity + workstation semantics)

```text
REAL MT5 order_send: NO
Dashboard broker mutation: NO
Strategy / MTF thresholds changed: NO
ExecutionCandidate rules changed: NO
Fabricated market / % data: NO
```

---

## Tổng kết

| Hạng mục | Kết quả |
|----------|---------|
| Token system (accent / semantic / surface / shadow) | PASS |
| Shell + nav + header chrome | PASS |
| Symbol tabs (active L, full-width, signal, sparkline, Thêm) | PASS |
| Trade analysis 3 cột + Risk densify | PASS |
| Realized PnL filter 7 / 30 ngày | PASS |
| Account switcher pill + loading overlay | PASS |
| Live account `.env` nhận diện qua API | PASS (`live configured=True`) |

---

## BEFORE → AFTER

| BEFORE | AFTER |
|--------|--------|
| Pale flat surfaces, weak depth | Card trắng + soft `--shadow-card` trên canvas `#F4F7FB` |
| Near-black / mixed accent | Brand blue `#2563EB` **chỉ** interaction |
| M15 / LONG gắn brand blue | Semantic green/red; M15 tách khỏi `--accent` |
| Symbol tabs rời / không sparkline | Thanh full-width; sparkline session mid thật; `+ Thêm symbol` |
| Active = full blue border / underline mỏng | Active = card bo góc + viền L (trái + dưới) + shadow xanh |
| Realized PnL cố định 7 ngày | Filter **7 ngày / 30 ngày** (API `days`) |
| Account switch = 2 nút segment | Pill `DEMO ▾` / `LIVE ▾` + menu + overlay loading |

---

## Tokens

`dashboard/app/globals.css`

- `--background: #F4F7FB` (page); card `--surface: #FFFFFF`
- `--accent` / `--accent-hover` / `--accent-subtle` / `--accent-muted`
- `--positive` / `--negative` / `--warning` + `*-subtle`
- `--surface-active: var(--accent-subtle)`
- Radius: control / tab / card
- Shadows: xs / sm / card / card-hover
- Utilities: `.surface-card`, `.surface-card-interactive`
- Legacy aliases `@deprecated` giữ tương thích

**Rule màu:** blue = brand/interaction; green/red = PnL / signal only.

---

## Thay đổi chính theo vùng

### 1. Shell / chrome

- `DashboardShell.tsx` — nav groups (Giao dịch / Nghiên cứu / Hệ thống), active rail 3px reserved
- `TopHeader.tsx` — status pills + AccountSwitcher
- `button.tsx` / `badge.tsx` / tokens

### 2. Symbol tabs

`components/market/SymbolTabs.tsx`

- Một thanh trắng full-width; tab `flex-1` dàn đều
- Active: inset L-accent (trái + dưới) + shadow xanh nhẹ; tên symbol màu accent
- Inactive: divider dọc; hover subtle
- Badge LONG / SHORT / WAIT mọi tab (`useDashboardSymbolSignals`)
- Giá mid + session move abs/% (không bịa 24h)
- Sparkline: chuỗi mid từ quote poll (`session-sparkline` + `MiniSparkline` area fill)
- Nút outline `+ Thêm symbol` — extras localStorage; route `/dashboard/[SYMBOL]` qua `isValidMarketSymbol`

### 3. Trade analysis

- Overview: Hero | Setup | Risk (`lg:grid-cols-3`); MTF details **ẩn** overview (`showTimeframeDetails` chỉ trang Trades)
- Hero: M15 semantic + diverging score; Evidence Alignment dùng accent OK
- Setup: MetricRow; `PriceRelationshipBar` dạng chip thứ tự giá
- Risk densified; BLOCKED embed `maxItems={3}`; WAIT ≠ đỏ lỗi

### 4. Realized PnL

`components/account/RealizedPnlChart.tsx`

- Tự fetch `useDailyRealizedPnl(days)`
- Filter pill **7 ngày / 30 ngày**
- Header: title + **sum `$`** only (không %)
- API engine đã clamp `days` 1…90

### 5. Account switcher

`components/layout/AccountSwitcher.tsx`

- Compact: pill `DEMO`/`LIVE` + `ChevronDown` (lucide)
- Menu listbox; LIVE vẫn confirm dialog
- **Overlay loading toàn màn** khi switch (`isSwitching` tới `onSettled`) — khóa scroll/click
- Icons: **`lucide-react`** (đã dùng toàn dashboard)

### 6. Account live (ops)

Sau cập nhật `.env` + restart API:

| Profile | Configured | Ví dụ |
|---------|------------|--------|
| demo | True | `MT5_LOGIN` / Trial server |
| live | True | `MT5_LIVE_*` / Real server |

```text
DRY_RUN=true
ALLOW_LIVE_TRADING=false
→ Dashboard chỉ đọc; switch profile ≠ execution toggle
```

---

## Files chính (delta 17.2.5D)

| Path | Vai trò |
|------|---------|
| `dashboard/app/globals.css` | Design tokens |
| `dashboard/components/market/SymbolTabs.tsx` | Tabs + add + active L |
| `dashboard/components/market/MiniSparkline.tsx` | SVG sparkline + gradient |
| `dashboard/lib/market/session-sparkline.ts` | Ring buffer mid session |
| `dashboard/hooks/use-session-quote-moves.ts` | Move + series |
| `dashboard/lib/symbols/config.ts` | `isValidMarketSymbol` |
| `dashboard/components/account/RealizedPnlChart.tsx` | Range 7/30 |
| `dashboard/components/layout/AccountSwitcher.tsx` | Pill + loading |
| `dashboard/lib/i18n/vi.ts` | Labels VI |
| `dashboard/app/dashboard/[symbol]/page.tsx` | Overview layout |
| Spec / plan | `docs/superpowers/specs/2026-09-09-phase-17-2-5d-*.md` |

---

## Explicit non-changes

- Không `order_send` / không đổi strategy / không promote v2
- Không bịa % chart / không fake sparkline lịch sử 24h
- Sparkline = mid samples trong phiên Dashboard (honest)
- Thêm symbol = watchlist UI + quotes/analysis read-only; không mở execution đa symbol

---

## Verification

| Check | Status |
|-------|--------|
| `dashboard` `npm run typecheck` | PASS (sau các đợt UI) |
| `dashboard` unit tests (trước đó) | PASS |
| API `:8000` + Dashboard `:3000` sau restart `.env` live | PASS (HTTP 200) |
| `/api/v1/accounts` live configured | PASS |

---

## Visual acceptance

- [x] Bright / modern / card grouping
- [x] Brand blue không nuốt semantic PnL/signal
- [x] Active symbol scannable (L-accent + tên accent)
- [x] Sparkline + Thêm symbol theo mockup (data thật)
- [x] Realized PnL 7 / 30
- [x] Account pill + loading chặn thao tác khi switch
- [x] M15 không brand-blue

---

## Residual / optional next

- Secondary pages (Risk / Backtest / Settings) densify theo cùng tokens
- Sparkline lịch sử candle nếu sau này expose API rates read-only
- Evidence DEMO mutate vẫn **PENDING human** (ngoài scope UI)

---

## Verdict

```text
PHASE 17.2.5D VISUAL REDESIGN: PASS
BROKER / STRATEGY MUTATION: NO
ACCOUNT PROFILE SWITCH (read-only view): SUPPORTED + LOADING GUARD
```
