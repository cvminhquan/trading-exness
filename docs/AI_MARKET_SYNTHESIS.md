# AI Market Synthesis

Phase **16.3.3** — giải thích tình huống thị trường hiện tại (read-only).

## Purpose

Kết hợp:

1. `TechnicalMarketSnapshot` (16.3.1)
2. `ExternalMarketContext` (16.3.2)

→ `MarketSynthesis` (structured + human-readable).

**Không** tạo tín hiệu giao dịch mới.  
**Không** phê duyệt lệnh.  
**Không** Google/web search (16.3.2 sở hữu search).

## Architecture

```
TechnicalMarketSnapshot ----+
                            |
ExternalMarketContext ------+
                            v
                 MarketSynthesisService
                            |
              +-------------+-------------+
              |                           |
     Deterministic rules            AI provider (optional)
              |                           |
              +-------------+-------------+
                            v
                     MarketSynthesis
                            |
              API / future dashboard / chat
```

Package: `exness_bot.market_analysis.synthesis/`

## Deterministic vs AI Responsibilities

| Deterministic | AI (optional) |
|---------------|---------------|
| synthesis status | concise summary |
| synthesis state enum | technical/external/alignment explanations |
| technical_view / external_view | risk wording |
| facts, sources, fingerprints | uncertainties / what_to_watch phrasing |
| fallback narrative templates | — |

AI **không** chọn `SynthesisState`.

## Inputs

- Chỉ consume snapshot + external context đã có
- Không gọi MT5 indicators
- Không search web
- Không dump raw grounding / API keys

## Synthesis State

`RULE_VERSION = 1.0` precedence:

1. Insufficient technical → `INSUFFICIENT_CONTEXT`
2. `event_risk == HIGH` → `HIGH_EVENT_RISK` (alignment vẫn ở `external_view`)
3. Technical directional + SUPPORT (strong/moderate) → `TECHNICAL_EXTERNAL_ALIGNED`
4. Technical directional + CONFLICT (strong/moderate) → `TECHNICAL_EXTERNAL_CONFLICT`
5. SUPPORT + weak evidence → `EXTERNAL_SUPPORT_WEAK`
6. CONFLICT + weak evidence → `EXTERNAL_CONFLICT_WEAK`
7. MIXED → `TECHNICAL_DOMINANT_EXTERNAL_MIXED`
8. Technical neutral + external directional → `TECHNICAL_NEUTRAL_EXTERNAL_DIRECTIONAL`
9. Technical directional + external neutral/unavailable → `TECHNICAL_DIRECTIONAL_EXTERNAL_NEUTRAL`
10. Else → `INSUFFICIENT_CONTEXT`

## Technical View / External View

Copy/normalize từ snapshot và external — **không** rewrite.

## Narrative

Sections: summary, technical_explanation, external_explanation, alignment_explanation, risk_explanation, uncertainties, what_to_watch.

Không: BUY/SELL now, lots, SL/TP, win probability.

## Event Risk

`HIGH` được surface rõ; **không** suy ra hướng giá.

## Uncertainty / What To Watch

Liệt kê conflict HTF, evidence yếu, undated sources, v.v.  
What-to-watch chỉ quan sát — không instruction khớp lệnh.

## Source Provenance

Giữ `source_id` / title / domain / url từ ExternalMarketContext.  
AI không được invent URL.

## AI Provider

- Abstraction: `MarketSynthesisProvider`
- `GeminiMarketSynthesisProvider` — **không** gắn `google_search` tool
- `FakeMarketSynthesisProvider` — CI

Config:

```
AI_MARKET_SYNTHESIS_ENABLED=false
AI_MARKET_SYNTHESIS_PROVIDER=gemini
AI_MARKET_SYNTHESIS_MODEL=gemini-2.5-flash
AI_MARKET_SYNTHESIS_CACHE_TTL_SECONDS=600
AI_MARKET_SYNTHESIS_TIMEOUT_SECONDS=30
```

Reuse `GEMINI_API_KEY`.

## Fallback Behavior

AI disabled / timeout / invalid / execution-language → deterministic narrative.  
`ai_metadata.fallback_used=true`.

## Cache

Key: technical fingerprint + external fingerprint + provider/model + schema/rules.  
Quote tick không invalidate khi closed-candle fingerprint không đổi.

## API

```
GET /api/v1/analysis/{symbol}/market-synthesis
  ?view=compact
  ?forceRefresh=true
```

External disabled → vẫn trả `TECHNICAL_ONLY`.  
AI disabled → deterministic vẫn AVAILABLE/TECHNICAL_ONLY.

CLI:

```
python -m exness_bot.market_analysis.synthesis --symbol XAUUSD
```

## Prompt Injection Defense

Claim/web text = UNTRUSTED DATA trong delimiter.  
Bỏ qua “ignore previous instructions” / lệnh khớp.  
Execution-language guard + validation.

## Safety Boundary

`MarketSynthesis` ↛ MTF score / ExecutionCandidate / volume / SL/TP / `order_send`.

Does **not** generate or approve trades.

## Limitations

- Chất lượng narrative AI phụ thuộc model; state vẫn deterministic
- External disabled → TECHNICAL_ONLY
- Không calendar institutional; event risk từ 16.3.2

## Future Dashboard Integration

16.3.4 sẽ consume compact synthesis.

## Future AI Analyst Chat

16.3.5 sẽ dùng compact + facts/sources — chưa implement ở phase này.
