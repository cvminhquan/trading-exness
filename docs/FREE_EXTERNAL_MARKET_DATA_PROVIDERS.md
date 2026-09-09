# PHASE 16.3.7 — Free External Market Data Providers

**Ngày:** 2026-09-09  
**Symbol / TF:** XAUUSD · M15  
**Mục tiêu:** Free-Sources-First cho External Intelligence — Google Search Grounding chỉ còn optional enrichment.

---

## Architecture

```text
Technical Truth
    +
Free External Data Providers (BLS / FRED? / Fed / RSS)
    ↓
ExternalMarketContext  (schema 1.0 — không đổi model song song)
    ↓
MarketSynthesis → Dashboard / Analyst Chat
```

Gemini **không** phải nguồn market-data authoritative.  
Google Grounding: `GOOGLE_GROUNDING_ENABLED=false` (mặc định).

---

## Providers

| Provider | Package | Ghi chú |
|----------|---------|---------|
| BLS | `providers/bls.py` | Public Data API, zero-key mode |
| FRED | `providers/fred.py` | Optional; cần `FRED_API_KEY` |
| Federal Reserve | `providers/federal_reserve.py` | Official RSS/XML feeds |
| RSS | `providers/rss.py` | Allowlist only |
| Composite | `providers/composite.py` | Partial failure OK |

Supporting: `macro_models.py`, `macro_normalizer.py`, `news_normalizer.py`, `providers/provenance.py`, `providers/provider_cache.py`, `providers/provider_health.py`.

### BLS series (documented)

| Series ID | Meaning |
|-----------|---------|
| `CUUR0000SA0` | CPI-U All items (NSA) |
| `CUUR0000SA0L1E` | Core CPI-U less food/energy (NSA) |
| `LNS14000000` | Unemployment Rate (SA) |
| `CES0000000001` | Total nonfarm payroll employment (SA) |

### FRED series (when configured)

| Series ID | Meaning |
|-----------|---------|
| `DGS10` | 10-Year Treasury CMS |
| `DGS2` | 2-Year Treasury CMS |
| `DTWEXBGS` | Nominal Broad USD Index |

### Fed feeds

- `https://www.federalreserve.gov/feeds/press_monetary.xml`
- `https://www.federalreserve.gov/feeds/speeches.xml`
- `https://www.federalreserve.gov/feeds/press_all.xml`

---

## Config

```text
EXTERNAL_INTELLIGENCE_ENABLED=false
EXTERNAL_INTELLIGENCE_PROVIDER=free_sources
FREE_EXTERNAL_SOURCES_ENABLED=true
BLS_ENABLED=true
BLS_API_KEY=
FRED_ENABLED=false
FRED_API_KEY=
FEDERAL_RESERVE_ENABLED=true
EXTERNAL_RSS_ENABLED=true
GOOGLE_GROUNDING_ENABLED=false
```

---

## CLI

```bash
python -m exness_bot.market_analysis.external_context providers
python -m exness_bot.market_analysis.external_context smoke-free --symbol XAUUSD
```

- Không cần `GEMINI_API_KEY`
- Không cần Google Grounding
- Zero broker mutation

---

## Cache TTL (provider-specific)

| Provider | TTL |
|----------|-----|
| BLS | 6 hours |
| FRED | 1 hour |
| Fed / RSS | 10 minutes |

Technical fingerprint vẫn bỏ qua quote tick. Closed M15 mới có thể re-align với evidence đã cache.

---

## Safety

- Không `order_send` / ExecutionOrchestrator / MT5Executor
- Không sửa V1 / V2 / ExecutionCandidate / Phase17 / forward freeze
- External không override bot signal
- 16.3.6 vẫn **BLOCKED**
