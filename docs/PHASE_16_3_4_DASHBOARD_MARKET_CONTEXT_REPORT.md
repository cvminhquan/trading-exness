# PHASE 16.3.4 REPORT — Dashboard Market Context

**Ngày:** 2026-09-09  
**Trạng thái:** PASS  
**Frontend:** Next.js / React / TypeScript  
**Symbol / TF:** XAUUSD · M15 PRIMARY  
**Baseline:** 16.3.1–16.3.3 PASS · Forward không contaminated · V2 chưa promote

```text
Dashboard broker mutation: NO
Buy / Sell / Execute / Close controls: NO
order_send / ExecutionOrchestrator / MT5Executor: ZERO
Strategy modified: NO
Chat UI (16.3.5): NOT STARTED
```

---

## Tổng kết

| Hạng mục | Kết quả |
|----------|---------|
| Market Context section trên Overview | PASS |
| Typed `marketSynthesisSchema` + repository + hook | PASS |
| Technical vs External + M15 PRIMARY | PASS |
| Event risk / drivers / AI narrative / sources | PASS |
| TECHNICAL_ONLY / disabled / fallback UX | PASS |
| Polling không forceRefresh Gemini | PASS |
| typecheck + vitest | PASS |
| Backend regression 16.3.1–16.3.3 + 16.2.4A.2 | PASS (73) |
| Visual review live | PASS (TECHNICAL_ONLY khi external OFF) |

---

## Mục đích

UI read-only giúp operator thấy:

1. Bot thấy gì về mặt kỹ thuật  
2. External/macro nói gì  
3. SUPPORT hay CONFLICT với M15  
4. Giải thích tổng hợp (AI hoặc deterministic)  
5. Event risk / what to watch  
6. Nguồn trích dẫn  

---

## UI hierarchy (Overview)

1. Account Summary  
2. Symbol tabs  
3. Trading Analysis  
4. **Market Context** ← phase này  
5. Positions  
6. Realized PnL  

Trong Market Context:

- Summary + status badge + **Làm mới ngữ cảnh**
- Technical vs External (+ HTF roles M15/H1/H4/D1)
- Drivers | Event Risk  
- AI / deterministic explanation (collapsible)  
- Uncertainties | What to watch  
- Sources (`target=_blank` · `rel=noopener noreferrer`)

**Style:** canvas `#F4F7FB` · card trắng · accent `#2563EB` chỉ interaction · bullish emerald / bearish rose / warning amber.

---

## Data flow

```text
GET /api/v1/analysis/{symbol}/market-synthesis
        → ApiTradingRepository.getMarketSynthesis
        → useMarketSynthesis(symbol)
        → MarketContextSection
```

| Client | Value |
|--------|--------|
| Query key | `["trading", "market-synthesis", symbol]` |
| staleTime | 45s |
| refetchInterval | 60s |
| Normal poll forceRefresh | **NO** |
| Manual refresh | `forceRefresh=true` (analysis-only) |

Không gọi Gemini từ browser. Không recalculate EMA/RSI/ATR/alignment ở TypeScript.

---

## Files

**Added**

- `dashboard/components/market-context/MarketContextSection.tsx`
- `dashboard/lib/market-context/display.ts`
- `dashboard/lib/market-context/display.test.ts`
- `docs/DASHBOARD_MARKET_CONTEXT.md` (design/data-flow)
- `docs/PHASE_16_3_4_DASHBOARD_MARKET_CONTEXT_REPORT.md` (report này)

**Modified**

- `dashboard/app/dashboard/[symbol]/page.tsx`
- `dashboard/domain/schemas.ts`
- `dashboard/lib/api/paths.ts`, `lib/i18n/vi.ts`
- `dashboard/queries/keys.ts`, `use-trading-queries.ts`
- `dashboard/repositories/*` (+ mock)

---

## States (UI)

| Backend status | Nhãn VI |
|----------------|---------|
| AVAILABLE | Khả dụng |
| TECHNICAL_ONLY | Chỉ kỹ thuật |
| PARTIAL | Một phần |
| STALE | Cũ |
| UNAVAILABLE | Không khả dụng |

External disabled → hint nhẹ, không banner “lỗi hệ thống”.  
`ai_metadata.fallback_used` → badge **Phân tích dự phòng**.

---

## Tests

| Check | Kết quả |
|-------|---------|
| Vitest (toàn dashboard) | 61 passed (8 mới market-context) |
| `tsc --noEmit` | PASS |
| ESLint files phase | PASS |
| Backend 16.3.1–16.3.3 + 16.2.4A.2 | 73 passed |

---

## Visual / Real data

- Live Overview: section **Bối cảnh thị trường** sau Trading Analysis  
- Observed khi external OFF: `TECHNICAL_ONLY`, bot `WAIT`, deterministic fallback  
- Không chat input · không execution CTA  

---

## Safety

- Signal LONG/SHORT/WAIT chỉ là nhãn read-only  
- `safeExternalHref` chặn `javascript:` / `file:`  
- Không import execution stack  

---

## STOP

**Không** bắt đầu Phase 16.3.5 AI Market Analyst Chat.  
Không tune strategy. Không nối control dashboard với broker mutation.
