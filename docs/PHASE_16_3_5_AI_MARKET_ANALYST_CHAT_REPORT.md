# PHASE 16.3.5 — AI MARKET ANALYST CHAT

STATUS: **PASS**

## ARCHITECTURE

### Backend
- `trading-engine/src/exness_bot/market_analysis/analyst_chat/`
  - `models.py`, `context_builder.py`, `prompt_builder.py`
  - `provider_base.py`, `gemini_provider.py`, `fake_provider.py`
  - `validator.py`, `fallback.py`, `intent.py`
  - `service.py`, `session.py`, `rate_limit.py`
- API: `POST /api/v1/analysis/{symbol}/analyst-chat`
- Settings + `.env.example` keys for chat (default OFF)

### Frontend
- `dashboard/components/market-context/MarketAnalystChat.tsx`
- Wired under Market Context (`MarketContextSection`) — additive
- Schema: `marketAnalystChatResponseSchema`
- `tradingRepository.postAnalystChat` + `useMarketAnalystChat`
- i18n: `ANALYST_CHAT` in `lib/i18n/vi.ts`

### Context builder
Server builds `MarketAnalystContext` from TechnicalSnapshot + ExternalContext + MarketSynthesis. Browser does not supply authoritative market facts.

### Provider abstraction
`MarketAnalystProvider` → `GeminiMarketAnalystProvider` / `FakeMarketAnalystProvider`

### Sessions
JSON files under `data/analyst_chat/`; symbol change starts a new session; history bounded.

## CONTEXT

- Technical schema: 1.0 (16.3.1)
- External schema: 1.0 (16.3.2)
- Synthesis schema: 1.0 (16.3.3)
- Fingerprints on every answer; `context_changed=true` when fingerprints differ since previous turn

## AI

- Enabled default: **false** (`AI_MARKET_ANALYST_CHAT_ENABLED=false`)
- Provider: gemini
- Model: configurable (`gemini-2.5-flash` default)
- API key: **NOT_CONFIGURED**
- Fallback: **YES** (deterministic intent routing)
- Direct Google search from chat: **NO**

## CHAT

- Endpoint: `POST /api/v1/analysis/{symbol}/analyst-chat`
- Session: per-symbol lightweight store
- History limit: 12 (configurable)
- Message length: 3000 (configurable)
- Rate limit: 20 / 60s / symbol
- Intent routing: keyword/rule (WHY_BOT_SIGNAL, PRICE, EXTERNAL, …)

## SOURCES

- Canonical source IDs only
- Invented URLs blocked by validator
- Freshness warnings: `technical_stale` / `external_stale`

## UI

- Location: below Market Context cards
- Empty state + suggested analysis questions
- Messages, source chips, fallback/disabled hints
- Context updated + stale warnings
- Responsive (scrollable message area ~420–520px)

## REAL AI CHAT SMOKE

**NOT_RUN** — `GEMINI_API_KEY` not configured

Do **not** claim real grounded citation behavior verified (16.3.2 Google smoke also not run).

## TESTS

| Suite | Result |
|-------|--------|
| Backend new (`test_phase_16_3_5_analyst_chat.py`) | 20 passed |
| Frontend new (`analyst-chat.test.ts` + display) | 11 passed (market-context) |
| 16.3.1 / 16.3.2 / 16.3.3 regression | PASS (66 combined with 16.3.5) |
| 16.2.4A.2 forward validation | 27 passed |
| ruff (analyst_chat) | PASS |
| mypy (analyst_chat) | PASS |
| tsc | PASS |
| eslint (chat-related) | PASS |

## FORWARD

- Cutoff changed: **NO**
- V2 freeze changed: **NO**
- Metric fingerprint changed: **NO**
- Hypotheses changed: **NO**
- Contaminated: **NO**

## SAFETY

- V1 modified: **NO**
- V2 modified: **NO**
- V2 promoted: **NO**
- ExecutionCandidate modified: **NO**
- Phase17 modified: **NO**
- order_send: **ZERO** (no execution identifiers in package)
- Broker mutation: **NO**
- Execution tools exposed to AI: **NO**
- Chat affects strategy: **NO**

## DOCS

- `docs/AI_MARKET_ANALYST_CHAT.md`

## STOP

Implementation complete. No execution wiring, no V2 promotion, no multimodal, no forward-protocol changes.
