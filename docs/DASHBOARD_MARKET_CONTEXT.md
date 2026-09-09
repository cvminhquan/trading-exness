# Dashboard Market Context

Phase **16.3.4** — UI read-only cho Market Synthesis trên Overview.

## Purpose

Giúp operator hiểu nhanh:

1. Bot thấy gì về mặt kỹ thuật (M15 PRIMARY)
2. Ngữ cảnh bên ngoài / macro nói gì
3. SUPPORT hay CONFLICT với M15
4. Giải thích tổng hợp (AI hoặc deterministic)
5. Rủi ro sự kiện / điểm cần theo dõi
6. Nguồn trích dẫn

## Data flow

```
GET /api/v1/analysis/{symbol}/market-synthesis
        |
        v
ApiTradingRepository.getMarketSynthesis
        |
        v
useMarketSynthesis(symbol)   staleTime 45s · refetchInterval 60s
        |
        v
MarketContextSection
```

Không gọi Gemini từ browser.  
Không forceRefresh khi poll thường.

Manual **Làm mới ngữ cảnh** → `forceRefresh=true` (analysis-only).

## API

- Path: `API_V1.marketSynthesis(symbol)`
- Schema: `marketSynthesisSchema` (nhận snake_case backend → camelCase UI)
- Query key: `["trading", "market-synthesis", symbol]`

## UI hierarchy (Overview)

1. Account Summary  
2. Symbol tabs  
3. Trading Analysis  
4. **Market Context** ← phase này  
5. Positions  
6. Realized PnL  

Trong Market Context:

- Summary + status + refresh  
- Technical vs External (+ HTF roles)  
- Drivers | Event Risk  
- AI / deterministic explanation (collapsible details)  
- Uncertainties | What to watch  
- Sources  

## Status handling

| Backend | UI |
|---------|-----|
| AVAILABLE | Khả dụng |
| TECHNICAL_ONLY | Chỉ kỹ thuật + gợi ý external unavailable/disabled |
| PARTIAL | Một phần |
| STALE | Cũ |
| UNAVAILABLE | Không khả dụng |

Unknown enum → graceful fallback (không crash).

## Freshness

Hiển thị `Cập nhật Xm ago` từ `generatedAt`.  
Freshness nguồn / external hiện trong source rows.

## Sources

`target="_blank"` + `rel="noopener noreferrer"`.  
Frontend chặn scheme không an toàn (`safeExternalHref`).

## AI labeling

Subtitle: giải thích dựa trên technical + grounded context.  
Không dùng copy kiểu “AI trade recommendation / prediction / signal”.  
`ai_metadata.used=false` → badge Deterministic / Fallback.

## Safety boundary

- Không Buy/Sell/Execute/Close controls  
- Không import execution stack  
- Signal LONG/SHORT/WAIT chỉ là nhãn read-only  

## Responsive

- Desktop: summary full width; drivers | event risk 2 cột  
- Mobile: một cột theo thứ tự summary → comparison → risk → drivers → AI → uncertainties → watch → sources  

## Phase 16.3.5 handoff

Chat sẽ consume compact synthesis / facts / sources.  
**Chưa** thêm input chat ở phase này.
