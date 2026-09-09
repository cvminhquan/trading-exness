# PHASE 16.3.2 REPORT — External Intelligence & Grounded Market Context

**Ngày:** 2026-09-09  
**Trạng thái:** PASS  
**Symbol / TF:** XAUUSD · M15 PRIMARY  
**Baseline:** 16.3.1 TechnicalMarketSnapshot PASS · Forward 16.2.4A.2 không contaminated · V2 chưa promote

```text
REAL MT5 order_send: NO
Broker mutation: NO
Strategy / MTF / V2 freeze changed: NO
ExecutionCandidate modified: NO
Google HTML scraping: NO
External context affects strategy: NO
```

---

## Tổng kết

| Hạng mục | Kết quả |
|----------|---------|
| Provider abstraction + Gemini Google Search grounding | PASS |
| Deterministic query planner | PASS |
| ExternalMarketContext schema 1.0 | PASS |
| Cache + fingerprint (không invalidate vì tick) | PASS |
| Read-only API | PASS |
| Fake provider + unit tests | PASS |
| Feature default OFF | PASS |
| Real Google smoke | NOT_RUN — API KEY NOT_CONFIGURED |

---

## Mục đích

Layer read-only:

```text
TechnicalMarketSnapshot
        → ExternalContextQueryPlanner
        → ExternalIntelligenceProvider (Gemini / Fake)
        → ExternalMarketContext
```

Cung cấp ngữ cảnh bên ngoài có grounding (USD, yields, Fed, macro, geopolitics…) **không** tạo tín hiệu khớp lệnh.

---

## Architecture

**Package:** `trading-engine/src/exness_bot/market_analysis/external_context/`

| File | Vai trò |
|------|---------|
| `models.py` | Schema typed ExternalMarketContext |
| `planner.py` | Search plan bounded ≤6 topics |
| `gemini_provider.py` | `google.genai` + tool `google_search` |
| `fake_provider.py` | CI offline |
| `normalizer.py` | Validate / freshness / sources |
| `cache.py` | Memory + `data/external_context/` |
| `service.py` | Orchestration |
| `__main__.py` | CLI smoke |

**Docs:** `docs/EXTERNAL_INTELLIGENCE_GROUNDED_CONTEXT.md`

---

## Config

```text
EXTERNAL_INTELLIGENCE_ENABLED=false
EXTERNAL_INTELLIGENCE_PROVIDER=gemini_google
GEMINI_API_KEY=
EXTERNAL_INTELLIGENCE_MODEL=gemini-2.5-flash
EXTERNAL_INTELLIGENCE_CACHE_TTL_SECONDS=600
```

Optional dep: `pip install -e ".[ai]"` (`google-genai`)

---

## API

```text
GET /api/v1/analysis/{symbol}/external-context
  ?view=compact
  ?forceRefresh=true
```

Refresh = analysis-only. Không POST broker.

CLI:

```text
python -m exness_bot.market_analysis.external_context --symbol XAUUSD
```

---

## Schema highlights

- **Bias:** `BULLISH_FOR_GOLD` / `BEARISH_FOR_GOLD` / `MIXED` / `NEUTRAL` / `INSUFFICIENT_EVIDENCE` (không BUY/SELL)
- **Evidence:** `STRONG` / `MODERATE` / `WEAK` / `INSUFFICIENT`
- **Alignment (M15 only):** SUPPORT / CONFLICT / NEUTRAL / MIXED / INSUFFICIENT_DATA
- **Freshness:** BREAKING ≤2h · RECENT ≤24h · CURRENT ≤72h · STALE · UNDATED
- Claims + sources + drivers + event_risk

---

## Tests

| Suite | Kết quả |
|-------|---------|
| `test_phase_16_3_2_external_intelligence.py` | 16 passed |
| 16.3.1 regression | PASS |
| 16.2.4A.2 forward | PASS |
| ruff / mypy (`external_context`) | PASS |

Forward: cutoff `2026-09-08T16:00:00Z` unchanged · contaminated NO

---

## Safety

- Forbidden execution imports: ZERO trong package
- `order_send`: ZERO
- Prompt-injection defense trên web content
- Default OFF → dashboard/API behavior cũ không đổi

---

## STOP

Không bắt đầu 16.3.3 trong report này (đã làm phase riêng).  
Không tune strategy từ external observations.
