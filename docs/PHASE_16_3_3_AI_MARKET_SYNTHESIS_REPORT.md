# PHASE 16.3.3 REPORT — AI Market Synthesis Engine

**Ngày:** 2026-09-09  
**Trạng thái:** PASS  
**Symbol / TF:** XAUUSD · M15 PRIMARY  
**Baseline:** 16.3.1 + 16.3.2 PASS · Forward không contaminated · V2 chưa promote

```text
REAL MT5 order_send: NO
Broker mutation: NO
Google/web search from synthesis: NO
Strategy / MTF / V2 freeze changed: NO
ExecutionCandidate modified: NO
MarketSynthesis generates trades: NO
```

---

## Tổng kết

| Hạng mục | Kết quả |
|----------|---------|
| Hybrid deterministic + optional AI | PASS |
| MarketSynthesis schema 1.0 · rule version 1.0 | PASS |
| AI optional (default OFF) + deterministic fallback | PASS |
| No second web search | PASS |
| Execution-language guard + validation | PASS |
| Cache + synthesis fingerprint | PASS |
| Read-only API + compact | PASS |
| Real AI smoke | NOT_RUN — API KEY NOT_CONFIGURED |

---

## Mục đích

```text
TechnicalMarketSnapshot + ExternalMarketContext
        → MarketSynthesisService
        → MarketSynthesis (human-facing)
```

Giải thích tình huống hiện tại — **không** tạo tín hiệu mới, **không** đổi MTF/execution.

---

## Architecture

**Package:** `trading-engine/src/exness_bot/market_analysis/synthesis/`

| Layer | Trách nhiệm |
|-------|-------------|
| Deterministic (`rules.py`) | status, state enum, technical/external views, facts, fallback narrative |
| AI (`gemini_provider.py`) | narrative wording only — **không** `google_search` tool |
| Fake | CI offline + execution-language / invented URL scenarios |
| `validator.py` | reject BUY NOW / lots / SL / invented URLs |
| `cache.py` | `data/market_synthesis/` |

**Docs:** `docs/AI_MARKET_SYNTHESIS.md`

---

## Synthesis state (RULE_VERSION 1.0)

Precedence (rút gọn):

1. Insufficient technical → `INSUFFICIENT_CONTEXT`
2. `event_risk=HIGH` → `HIGH_EVENT_RISK` (alignment vẫn ở external_view)
3. SUPPORT / CONFLICT (moderate+) → ALIGNED / CONFLICT
4. WEAK evidence → EXTERNAL_SUPPORT_WEAK / EXTERNAL_CONFLICT_WEAK
5. MIXED → TECHNICAL_DOMINANT_EXTERNAL_MIXED
6. Neutral/directional variants…
7. Else → INSUFFICIENT_CONTEXT

AI **không** chọn enum state.

---

## Config

```text
AI_MARKET_SYNTHESIS_ENABLED=false
AI_MARKET_SYNTHESIS_PROVIDER=gemini
AI_MARKET_SYNTHESIS_MODEL=gemini-2.5-flash
AI_MARKET_SYNTHESIS_CACHE_TTL_SECONDS=600
AI_MARKET_SYNTHESIS_TIMEOUT_SECONDS=30
```

Reuse `GEMINI_API_KEY`.

---

## API

```text
GET /api/v1/analysis/{symbol}/market-synthesis
  ?view=compact
  ?forceRefresh=true
```

External disabled → vẫn trả `TECHNICAL_ONLY`.  
AI disabled → deterministic narrative + `ai_metadata.used=false`.

CLI:

```text
python -m exness_bot.market_analysis.synthesis --symbol XAUUSD
```

---

## Output

- `technical_view` / `external_view` (copy/normalize — không rewrite)
- `synthesis.state` + summary / explanations / uncertainties / what_to_watch
- `sources` provenance từ ExternalMarketContext
- `ai_metadata` (enabled / used / fallback_used / latency / error)

---

## Tests

| Suite | Kết quả |
|-------|---------|
| `test_phase_16_3_3_market_synthesis.py` | 13 passed |
| 16.3.1 + 16.3.2 + 16.2.4A.2 | PASS (combined 73 với 16.3.2/1/forward) |
| ruff / mypy (`synthesis`) | PASS |

---

## Safety

- Không score kết hợp technical+external vào MTF
- Không win probability / trade confidence %
- Prompt injection: claim text = untrusted data
- `order_send` / execution imports: ZERO

---

## STOP

Không bắt đầu 16.3.4/16.3.5 trong scope report này (16.3.4 làm phase riêng).  
Không gắn synthesis vào ExecutionCandidate.
