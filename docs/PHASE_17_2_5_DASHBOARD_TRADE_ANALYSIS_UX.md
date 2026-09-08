# PHASE 17.2.5 — DASHBOARD TRADE ANALYSIS UX

## Summary

Redesign khu vực **Phân tích giao dịch** trên Dashboard theo hierarchy quyết định → setup → risk → reasons → MTF details (collapsed).

READ-ONLY UI. Không thêm nút execute/order. Không đổi backend/API/strategy/execution rules.

## Files changed

### Components (new)

- `dashboard/components/trading-analysis/TradeAnalysisSection.tsx`
- `dashboard/components/trading-analysis/TradeDecisionHero.tsx`
- `dashboard/components/trading-analysis/MtfScoreBar.tsx`
- `dashboard/components/trading-analysis/TradeSetupCard.tsx`
- `dashboard/components/trading-analysis/RiskAssessmentCard.tsx`
- `dashboard/components/trading-analysis/DecisionReasonsCard.tsx`
- `dashboard/components/trading-analysis/MultiTimeframeDetails.tsx`
- `dashboard/components/trading-analysis/TimeframeAnalysisAccordion.tsx`
- `dashboard/components/trading-analysis/AnalysisStatusBadge.tsx`

### Helpers / i18n / page

- `dashboard/lib/trading-analysis/mtf-display.ts`
- `dashboard/lib/trading-analysis/reason-labels.ts`
- `dashboard/lib/trading-analysis/mtf-display.test.ts`
- `dashboard/lib/i18n/vi.ts` (`TRADE_ANALYSIS_UX`, `ANALYSIS_REASON_LABELS`, confidence tooltip)
- `dashboard/app/dashboard/page.tsx` — wire `TradeAnalysisSection` (MTF + eligibility)

### Legacy cards

`TradeAnalysisCard` / `MultiTimeframeAnalysisCard` không còn mount trên overview (file giữ nguyên, không xóa để tránh diff ngoài scope).

## API changes

**NONE** — vẫn dùng:

- `GET /api/v1/analysis/{symbol}/multi-timeframe`
- `GET /api/v1/analysis/{symbol}/execution-candidate`

## Backend / Strategy / Execution changes

**NONE**

## Broker mutation

**NO** — không gọi ExecutionOrchestrator / GatedMT5 / order_send; không có UI action mutation.

## UX states (mô tả)

| State | UI |
| --- | --- |
| **WAIT / NO_SETUP** | Hero lớn `WAIT`, không fake Entry/SL/TP; Setup card: “Chưa có directional setup.” |
| **WAITING_FOR_ENTRY** | Direction + zone + khoảng cách giá; TP1 = Execution target; TP2/TP3 = analysis only |
| **ENTRY_ZONE / READY** | Badge / note “DEMO candidate ready” + “Yêu cầu operator thực hiện preview riêng.” |
| **BLOCKED** | Badge `BLOCKED` tách khỏi WAIT; Risk tách Broker Executable vs Risk Acceptable |
| **Mobile** | 1 cột: Hero → Setup → Risk → Reasons → MTF |
| **Desktop ≥1280** | Setup + Risk 2 cột |

## Score bar

Marker trên thang −100…+100 với ngưỡng ±20. Weighted score **present** từ `totalScore` từng TF × trọng số engine (`0.2/0.3/0.3/0.2`) — không tính lại EMA/RSI/ATR/signal.

## Confidence

Luôn ghi **EVIDENCE ALIGNMENT** + tooltip: không phải xác suất thắng.

## Tests

- Unit: weighted score −12.63, distance-to-threshold, setup detection, reason mapping, broker≠risk invariant
- Run: `npm run lint`, `npm run typecheck`, `npm test` trong `dashboard/`
