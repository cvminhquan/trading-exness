# AI Market Analyst Chat (Phase 16.3.5)

## Purpose

Context-aware, **read-only** chat for operators to ask about technical state,
MTF roles, external context, event risk, and synthesis for the selected symbol
(primary: **XAUUSD** / **M15**).

The chat **cannot** execute or approve trades.

## Architecture

```
Selected Symbol
  → TechnicalMarketSnapshot
  → ExternalMarketContext
  → MarketSynthesis
  → MarketAnalystContextBuilder
  → AnalystChatService
      → GeminiMarketAnalystProvider | FakeMarketAnalystProvider
  → MarketAnalystChatResponse
  → Dashboard MarketAnalystChat
```

Backend package: `trading-engine/src/exness_bot/market_analysis/analyst_chat/`

## Context hierarchy

1. **TechnicalMarketSnapshot** — canonical technical truth  
2. **ExternalMarketContext** — grounded external evidence  
3. **MarketSynthesis** — existing interpretation  
4. **Chat model** — explanation layer only (lowest authority)

The browser must **not** submit market facts as authoritative truth.
Request body: `message`, optional `session_id` only.

## Technical truth

Consumed from Phase 16.3.1 snapshot (compact): price, M15/H1/H4/D1 roles,
indicators, S/R, bot signal (`mtf_technical_v1`), setup/execution status.

Research V2 is **not** exposed as default trading opinion.

## External evidence

From Phase 16.3.2 only. Chat does **not** run Google Search per message.

## Synthesis

From Phase 16.3.3 only. Chat consumes; does not change synthesis rules.

## Provider

- Abstraction: `MarketAnalystProvider`
- Production: `GeminiMarketAnalystProvider` (plain generation, **no tools**)
- Tests: `FakeMarketAnalystProvider`
- Reuses `GEMINI_API_KEY`
- Default: `AI_MARKET_ANALYST_CHAT_ENABLED=false`

## Sessions

Lightweight JSON session store under `data/analyst_chat/`.
Symbol change → new session. History bounded by
`AI_MARKET_ANALYST_CHAT_MAX_HISTORY_MESSAGES`.

Market context is rebuilt every request; fingerprints may set
`context_changed=true` without wiping history.

## Freshness

Stale technical/external surfaces as warnings. Chat must not present stale
quotes as live. Prefer “External context không khả dụng / đã cũ” over silent
re-search.

## Sources

`source_refs` must reference canonical `ExternalMarketContext.sources`.
Invented URLs are rejected by the validator.

## Fallback

Deterministic intent routing answers common questions when AI is disabled or
the provider fails (`fallback_used=true`).

## Prompt injection

User text and external claims are untrusted data. System prompt has authority.
No broker tools are exposed to the model.

## Trading-action boundary

Requests like “Mở lệnh short” receive a read-only refusal.
Responses claiming execution are rejected.

## API

`POST /api/v1/analysis/{symbol}/analyst-chat`

Body:

```json
{ "message": "...", "session_id": "optional" }
```

Analysis-only. Does **not** mutate broker state.

## Dashboard UI

`MarketAnalystChat` under Market Context (additive). Suggested analysis
questions, sources, context-updated / stale hints, loading, disabled,
fallback badges. No Buy/Sell/Execute controls.

## Configuration

See `trading-engine/.env.example`:

- `AI_MARKET_ANALYST_CHAT_ENABLED=false`
- `AI_MARKET_ANALYST_CHAT_PROVIDER=gemini`
- `AI_MARKET_ANALYST_CHAT_MODEL=...`
- `AI_MARKET_ANALYST_CHAT_TIMEOUT_SECONDS=...`
- `AI_MARKET_ANALYST_CHAT_MAX_HISTORY_MESSAGES=12`
- `AI_MARKET_ANALYST_CHAT_MAX_MESSAGE_LENGTH=3000`
- `AI_MARKET_ANALYST_CHAT_RATE_LIMIT=20`

## Limitations

- No multimodal / chart vision  
- No arbitrary web-search chat  
- No floating global assistant  
- No execution / strategy / V2 promotion  
- Deterministic fallback is not full natural-language AI  

## Safety

- Zero imports of execution stack in `analyst_chat`  
- No `order_send`  
- External context does not drive bot signal explanations as if strategy consumed it  

## Future improvements

- Controlled “Search latest news” mode  
- Optional session history GET  
- Global assistant (still analysis-only)  
- Multimodal chart Q&A (research only)
