# PROJECT FLOW AUDIT — EXNESS BOT

**Ngày audit:** 2026-09-12  
**Phạm vi:** CODE + DOCS trong repository `trading-exness`  
**Quy tắc:** CODE là source of truth khi mâu thuẫn với docs. Không sửa code trong audit này.

---

## A. EXECUTIVE SUMMARY

### PROJECT PURPOSE

Exness Bot là monorepo giao dịch thuật toán Exness qua MetaTrader 5: engine Python đọc nến/quote, chạy chiến lược kỹ thuật đa khung thời gian (`mtf_technical_v1`), tạo `ExecutionCandidate`, và (khi bật gate) có thể gửi lệnh **DEMO** qua stack execution có kiểm soát.

Runtime chính hiện tại là **API FastAPI (`exness-bot-api`) + MT5 read/attach** phục vụ dashboard, cộng **CLI `python -m exness_bot.execution.auto_demo`** cho autonomous DEMO — không tự start từ API/dashboard.

Bot **không** được coi là trading LIVE production: đường đặt lệnh mới mặc định fail-closed; LIVE cần nhiều flag riêng. Trạng thái thực thi thực tế là **analysis + DEMO-capable**, với **bằng chứng lệnh DEMO thật vẫn PENDING** theo docs Phase 17.3.

Dashboard là **bảng điều khiển vận hành**: hiển thị account, MTF, setup/plan/risk, positions, market context, AI chat; có thêm **đóng vị thế** (close-only) được gate riêng — không phải zero broker mutation toàn dashboard.

External Intelligence / AI là **research & giải thích read-only**: tổng hợp BLS/Fed/RSS/(FRED), synthesis, Analyst Chat. Chúng **không** ghi vào score/`ExecutionCandidate`/`order_send`.

### CURRENT PROJECT STATE

| Area | Status | Giải thích 1 câu |
|------|--------|------------------|
| Research | WORKING | V2 (`mtf_technical_v2_candidate`) + forward harness tồn tại nhưng **không promote** execution. |
| Technical Analysis | WORKING | `mtf_technical_v1` M15/H1/H4/D1 + S/R + setup chạy qua API. |
| Risk | WORKING | Eligibility + sizing + auto-demo risk gates có trong code. |
| Execution | WORKING | Stack Candidate→Orchestrator→GatedMT5→Executor→LiveTransport đã nối; mặc định fail-closed. |
| Autonomous DEMO | IMPLEMENTED BUT NOT FULLY VERIFIED | Impl PASS (17.3); **REAL DEMO EVIDENCE: PENDING**. |
| Dashboard | WORKING | Unified analysis card + positions/PnL/context/chat; close-only mutation có gate. |
| External Intelligence | PARTIAL | Code free_sources sẵn; runtime phụ thuộc `EXTERNAL_INTELLIGENCE_ENABLED` (`.env` hiện `true`). |
| AI Analyst | PARTIAL | Chat/synthesis có Gemini + deterministic fallback; grounding thật 16.3.6 vẫn BLOCKED trong docs. |

---

## B. HIGH-LEVEL ARCHITECTURE

```
┌─────────────────────────── RUNTIME / PRODUCTION PATH ───────────────────────────┐
│                                                                                 │
│  MetaTrader 5 (Exness)                                                          │
│       │ [READ] candles/quotes/account                                           │
│       ▼                                                                         │
│  MT5 Data Provider / Read clients                                               │
│       │ [DETERMINISTIC]                                                         │
│       ▼                                                                         │
│  Closed Candle Engine (M15 primary + H1/H4/D1)                                  │
│       │                                                                         │
│       ▼                                                                         │
│  Indicators + Structure + S/R + Scoring                                          │
│       │ [DETERMINISTIC]                                                         │
│       ▼                                                                         │
│  MultiTimeframeAnalysisService  (strategy_id = mtf_technical_v1)                │
│       │                                                                         │
│       ├──► TradeSetup / CanonicalTradeSetup / Entry Zone / SL / TP1–3           │
│       │                                                                         │
│       ▼                                                                         │
│  ExecutionContractService → ExecutionCandidate                                  │
│       │ eligibility + sizing                                                    │
│       ▼                                                                         │
│  ┌─ API (exness-bot-api) ────────────────────┐                                 │
│  │  GET multi-timeframe / execution-candidate │──► Dashboard [MOSTLY READ]      │
│  │  GET positions / account / quotes          │    + close-only [MUTATION GATE] │
│  └────────────────────────────────────────────┘                                 │
│                                                                                 │
│  ┌─ Autonomous DEMO CLI (riêng process) ──────┐                                 │
│  │  closed M15 → candidate → risk_gates       │ [DEMO MUTATION if enabled]      │
│  │  → CandidateExecutionService               │                                 │
│  │  → ExecutionOrchestrator                   │                                 │
│  │  → GatedMT5ExecutionPort                   │                                 │
│  │  → MT5Executor                             │                                 │
│  │  → LiveMT5ExecutionTransport               │                                 │
│  │  → MetaTrader5.order_send                  │                                 │
│  └────────────────────────────────────────────┘                                 │
│                                                                                 │
│  Legacy: MT5Adapter.order_send (open/close/modify)                              │
│          isolated by ALLOW_LEGACY_RUN=false  [NO DEFAULT EXECUTION ACCESS]      │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────── RESEARCH / CONTEXT (NO EXECUTION ACCESS) ────────────────────┐
│                                                                                 │
│  BLS / Fed / RSS / (FRED optional)                                              │
│       │ [RESEARCH ONLY]                                                         │
│       ▼                                                                         │
│  FreeSourcesCompositeProvider                                                   │
│       │ gated by EXTERNAL_INTELLIGENCE_ENABLED                                  │
│       ▼                                                                         │
│  ExternalMarketContext → MarketSynthesis → Dashboard Market Context             │
│       │                                                                         │
│       ▼                                                                         │
│  AI Analyst Chat / Gemini narrative  [RESEARCH ONLY · READ snapshots]           │
│                                                                                 │
│  market_analysis/research (mtf_technical_v2_candidate)                          │
│       └── offline harness / forward validation  [RESEARCH ONLY]                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

Nhãn:

| Tag | Ý nghĩa |
|-----|---------|
| `[READ ONLY]` | Không `order_send` trên path đó |
| `[DETERMINISTIC]` | Công thức cố định, không AI |
| `[RESEARCH ONLY]` | Không wire ExecutionCandidate production |
| `[DEMO MUTATION]` | Có thể `order_send` khi DEMO gates pass |
| `[NO EXECUTION ACCESS]` | Không import/gọi execution stack |

---

## C. END-TO-END FLOW

### STEP 1 — Data source
- **Input:** Terminal MT5 Exness (hoặc mock).
- **Output:** Candles/quotes/account.
- **Module:** `data/mt5_provider.py`, read-only clients.
- **Runtime:** Có. **Mutation:** Không trên read path.

### STEP 2 — Nhận data
- **Module:** Provider → API `ReadService` / Auto-demo bundle builder.
- **File:** `api/services/read_service.py`, `execution/auto_demo/cli.py` (`_build_bundle_from_provider`).

### STEP 3 — Candle dùng
- **Closed candles only** (`open + duration <= now`); forming bị loại.
- **Primary:** M15; confirm/context: H1, H4, D1.
- **File:** `market_data/candles.py`.

### STEP 4 — Indicators
- EMA20/50/200, RSI14, ATR14, MACD 12/26/9, tick volume vs avg20.
- **File:** analyzers trong `market_analysis/` + `timeframe_analyzer.py`.

### STEP 5 — Canonical strategy
- **`mtf_technical_v1`** (`market_analysis/contract/identity.py`).
- Research: `mtf_technical_v2_candidate` — **cấm execution**.

### STEP 6 — MTF
- Per-TF score → weighted aggregate → LONG/SHORT/WAIT + confidence.
- Xem section E.

### STEP 7 — Setup state
- `build_trade_setup()` → lifecycle `NO_SETUP` / `WAITING_FOR_ENTRY` / `ENTRY_ZONE` / …
- **File:** `market_analysis/setup.py`, `contract/lifecycle.py`.

### STEP 8 — ExecutionCandidate
- Khi `ExecutionContractService.evaluate_from_analysis` + `evaluate_eligibility` → eligible.
- **File:** `contract/service.py`, `contract/candidate.py`, `contract/eligibility.py`.

### STEP 9 — Risk checks
- Eligibility/sizing trong contract; auto-demo thêm `risk_gates.py` (daily loss, DD, open positions, margin…).
- Precheck trước consume: `execution/integration/precheck.py`.

### STEP 10 — Eligible / blocked
- `evaluate_eligibility()` + precheck + (auto-demo) enablement/risk_gates/GatedMT5.
- Dashboard chỉ **hiển thị** status từ API.

### STEP 11 — ExecutionOrchestrator
- Intent lifecycle, idempotency, `IN_FLIGHT` trước side effect, map ack → FILLED/REJECTED/UNKNOWN.
- **File:** `execution/orchestrator.py`.
- **Không** import MetaTrader5.

### STEP 12 — `order_send`
- Path mới: `LiveMT5ExecutionTransport.send` → `MT5TradingClient.order_send` → `MetaTrader5.order_send`.
- Legacy: `MT5Adapter` (open/close/modify) — `ALLOW_LEGACY_RUN=false`.
- Dashboard close: `PositionCloseService` → `MT5Adapter.close_position` → `order_send` (gate riêng).

### STEP 13 — Persistence / idempotency
- Decision SQLite auto-demo (`decision_id = symbol|tf|closed_ts|strategy_id`).
- Orchestrator intent store: CLI hiện **không** truyền `state_path` → intent **không bền** qua restart (gap docs↔code).
- Setup lifecycle SQLite; external/synthesis JSON cache.

### STEP 14 — Dashboard APIs
- `/account/overview`, `/positions`, `/quotes`, `/analysis/{symbol}/multi-timeframe`, `/execution-candidate`, `/market-synthesis`, `POST .../analyst-chat`, `/account/pnl/daily`, close endpoints.

### STEP 15 — External Intelligence merge
- `ExternalContextService` → `MarketSynthesisService` → API market-synthesis.
- **Không** merge vào candidate/eligibility.

### STEP 16 — AI synthesis/chat
- Narrative + Analyst Chat đọc snapshot technical/external/synthesis.
- Fallback deterministic khi disable/thiếu key.

### STEP 17 — External/AI → execution?
- **EXTERNAL → EXECUTION PATH: NONE**
- **AI → EXECUTION PATH: NONE** (verified no import wiring).

---

## D. TECHNICAL ANALYSIS FLOW

| Mục | Code thực tế |
|-----|--------------|
| Symbols | Canonical `XAUUSD` (+ dashboard multi-symbol tabs); broker map `LIVE_SYMBOL_MAP` / suffix `m` |
| Timeframe | M15 primary; H1/H4/D1 |
| Closed candle | Bắt buộc |
| Indicators | EMA/RSI/ATR/MACD/volume |
| Structure | Swing L/R=2; HH/HL/LH/LL |
| S/R | Cluster swing ± 0.25 ATR |
| Score | Weighted components −100…100 |
| LONG/SHORT TF | ±25 |
| LONG/SHORT MTF | ±20 |
| WAIT | Score trong khoảng / conflict H4–D1 / không đủ data |
| Evidence Alignment | `confidenceScore` — đồng thuận kỹ thuật, **không** win rate |
| Entry Zone | entry ± 0.25 ATR |
| SL | Structure vs ATR×multiplier, lấy phía an toàn hơn |
| TP1/2/3 | S/R rồi 1R/2R/3R; allocation 30/40/30 |
| R:R | Tính theo từng TP |
| Execution TP | **TP1_ONLY** |

**CANONICAL PRODUCTION STRATEGY:** `mtf_technical_v1`  
**RESEARCH STRATEGIES:** `mtf_technical_v2_candidate` (frozen weights M15-first)  
**Không được execution dùng:** mọi ID trong `market_analysis/research/` + legacy `ema_rsi_atr_v1` / `phase16_decide_signal_v1` cho Phase 17 candidate.

---

## E. MTF FLOW

| Timeframe | Role | Weight (default) | Data min |
|-----------|------|------------------|----------|
| M15 | PRIMARY | 0.20 | 50 |
| H1 | CONFIRMATION | 0.30 | 50 |
| H4 | CONTEXT | 0.30 | 50 |
| D1 | MACRO | 0.20 | 40 |

- **TF score:** `0.30×trend + 0.25×structure + 0.20×momentum + 0.15×location + 0.10×volume`
- **Aggregate:** weighted sum / sum weights của TF đủ dữ liệu
- **LONG:** score ≥ 20; **SHORT:** ≤ −20; else WAIT
- **H4↔D1 conflict:** buộc WAIT, confidence × 0.6
- **H1↔H4 conflict:** signal theo score nhưng eligibility có thể block (`H1_H4_CONFLICT` blocking trong contract)
- **Evidence Alignment:** confidence kỹ thuật; **KHÔNG** phải xác suất thắng / confidence of profit

**Docs mâu thuẫn:** `PHASE_16_2` từng mô tả H1/H4 conflict chỉ là warning — code eligibility hiện treat một số reason là blocking.

---

## F. SETUP + EXECUTION CANDIDATE

| Khái niệm | Ý nghĩa |
|-----------|---------|
| SIGNAL | `finalSignal` LONG/SHORT/WAIT từ MTF |
| SETUP | Entry zone + SL/TP + lifecycle state |
| EXECUTION CANDIDATE | Snapshot eligible + sizing + fingerprint |
| EXECUTION PLAN | Map candidate → plan (TP1_ONLY) cho orchestrator |
| ORDER | Payload MT5 DEAL qua transport |

**Ví dụ SELL:**

```
SHORT signal → WAITING_FOR_ENTRY / ENTRY_ZONE
→ Entry zone near resistance
→ eligibility (zone, spread, volume, risk…)
→ ExecutionCandidate
→ (auto-demo) precheck + risk_gates
→ ExecutionPlan (TP1)
→ Orchestrator → GatedMT5 → order_send
```

**Không tạo / không eligible khi:** WAIT, thiếu TF, stale quote/account, ngoài entry zone, setup expired/invalidated, volume/risk fail, legacy strategy, spread quá rộng, (auto-demo) kill switch / allowlist / kill…

---

## G. RISK ENGINE

| Check | File | Block khi | Runtime |
|-------|------|-----------|---------|
| Strategy id | `eligibility.py` | ≠ `mtf_technical_v1` | Candidate |
| Signal WAIT | eligibility | WAIT | Candidate |
| TF incomplete/stale | eligibility | thiếu/stale TF | Candidate |
| Quote/account freshness | eligibility | stale/missing | Candidate |
| Spread | eligibility / risk_gates | > max | Candidate + DEMO |
| Entry zone / setup state | eligibility | ngoài zone / invalid | Candidate |
| Volume / risk budget | `sizing.py` | min lot vượt budget | Candidate |
| Daily loss | `auto_demo/risk_gates.py` | vượt % | DEMO only |
| Drawdown | risk_gates | vượt % | DEMO only |
| Max open positions | risk_gates | vượt cap | DEMO only |
| Margin | risk_gates | free margin thấp | DEMO only |
| DEMO enablement | `enablement.py` / GatedMT5 | kill/approval/allowlist/env | DEMO |

**Leverage:** không ảnh hưởng signal/score/confidence; sizing dùng tick value / risk budget / margin feasibility — **không** dùng leverage để tăng confidence.

---

## H. EXECUTION ARCHITECTURE

### Call graph (path mới)

```
ExecutionCandidate
→ CandidateExecutionService.precheck/consume
→ map_candidate_to_execution_plan (TP1_ONLY)
→ ExecutionOrchestrator.execute
→ GatedMT5ExecutionPort.submit
→ MT5Executor.submit
→ LiveMT5ExecutionTransport.send
→ MT5TradingClient.order_send
→ MetaTrader5.order_send
```

**WHO OWNS LIFECYCLE:** `ExecutionOrchestrator`  
**WHO MAY CALL order_send (path mới):** chỉ `LiveMT5ExecutionTransport`

### `order_send` occurrences (repo)

| Location | Vai trò |
|----------|---------|
| `broker/mt5/execution_transport.py` | Path Phase-12/17 live send |
| `broker/mt5/trading_client.py` | Wrapper MT5 |
| `broker/mt5/adapter.py` (×4) | Legacy open/close/modify SL/TP |
| Dashboard close path | Qua `PositionCloseService` → adapter close |
| Docs/tests | Nhiều mention — không phải runtime call |

**Nguy hiểm cần biết:** Legacy adapter vẫn tồn tại; bị cô lập bởi `ALLOW_LEGACY_RUN=false`. Dashboard close là mutation có chủ đích, không phải open trade từ analysis.

---

## I. AUTONOMOUS DEMO LOOP

| Mục | Thực tế |
|-----|---------|
| Entrypoint | `python -m exness_bot.execution.auto_demo` |
| Commands | `status`, `preflight`, `once`, `run`, `--dry` |
| Trigger | Closed M15 mới |
| decision_id | `symbol\|M15\|closed_ts\|mtf_technical_v1` |
| Persistence | SQLite decisions; intent store CLI thiếu `state_path` → không durable |
| Duplicate | Skip nếu decision_id đã terminal/unresolved |
| UNKNOWN | Không auto-resubmit |
| Kill switch | Chặn lệnh mới; không đóng position |
| Approval | `LIVE_DEMO_APPROVAL` sticky |
| Allowlist | `DEMO_ACCOUNT_ALLOWLIST` |
| Env | `TRADING_ENV=demo` |
| Poll | `run` hardcode ~5s trong CLI |

| Command | Mutation? |
|---------|-----------|
| `status` | Không |
| `preflight` | Không (`order_send_calls=0`) |
| `once --dry` / `run --dry` | Fake transport |
| `once` / `run` | Có thể thật nếu gates pass |

**IMPLEMENTATION:** PASS  
**REAL DEMO ORDER EVIDENCE:** PENDING (`docs/PHASE_17_3_AUTONOMOUS_DEMO_EXECUTION_REPORT.md`)

`.env` quan sát lúc audit (2026-09-12): `AUTO_DEMO_EXECUTION_ENABLED=true`, `LIVE_KILL_SWITCH=false`, `TRADING_ENV=demo` — config đã mở hơn docs mặc định, nhưng **chưa có file evidence smoke JSON thật** trong `docs/evidence/`.

---

## J. CONFIG / SAFETY GATES

| Env | Default (settings) | Meaning | Critical |
|-----|--------------------|---------|----------|
| `TRADING_ENV` | `research` | DEMO path yêu cầu `demo` | YES |
| `EXECUTION_MODE` | `paper` | Hot-read nhưng **không** gate auto-demo | MEDIUM |
| `LIVE_KILL_SWITCH` | `true` | Chặn submit mới | YES |
| `LIVE_DEMO_APPROVAL` | `false` | Sticky DEMO approval | YES |
| `DEMO_ACCOUNT_ALLOWLIST` | empty | Login phải match | YES |
| `AUTO_DEMO_EXECUTION_ENABLED` | `false` | Master auto-demo | YES |
| `ALLOW_LEGACY_RUN` | `false` | Cô lập MT5Adapter legacy | YES |
| `EXTERNAL_INTELLIGENCE_ENABLED` | `false` | Master external | Context only |
| `EXTERNAL_INTELLIGENCE_PROVIDER` | `free_sources` | Provider | Context |
| `FREE_EXTERNAL_SOURCES_ENABLED` | `true` | Fallback unknown provider | Context |
| `BLS_ENABLED` | `true` | Child provider | Context |
| `FEDERAL_RESERVE_ENABLED` | `true` | Child | Context |
| `EXTERNAL_RSS_ENABLED` | `true` | Child | Context |
| `FRED_ENABLED` | `false` | Child optional | Context |
| `GOOGLE_GROUNDING_ENABLED` | `false` | Gemini search | Context |

**Precedence:** process env > `.env` (cwd-relative) > defaults.  
Hot-read auto-demo: process env ghi đè; **không** re-read `.env` giữa vòng loop.

---

## K. EXTERNAL INTELLIGENCE

```
BLS / Fed / RSS / (FRED)
→ FreeSourcesCompositeProvider
→ ExternalContextService (gate ENABLED)
→ ExternalMarketContext
→ MarketSynthesisService
→ GET /market-synthesis
→ Dashboard badges
```

Fields chính: `status`, `external_bias`, `alignment_with_technical`, `event_risk`, `evidence_strength`, `freshness`, `source_count`, `sources`, `top_drivers`, `important_events`.

| Status UI | Ý nghĩa |
|-----------|---------|
| `TECHNICAL_ONLY` | Technical OK, external DISABLED/UNAVAILABLE |
| `DISABLED` | `EXTERNAL_INTELLIGENCE_ENABLED=false` |
| `AVAILABLE` / `PARTIAL` | Có nguồn |
| `INSUFFICIENT_EVIDENCE` / `INSUFFICIENT_DATA` | Bias/alignment khi thiếu bằng chứng |

**EXTERNAL → EXECUTION PATH: NONE**

---

## L. AI ANALYST / GEMINI

| Dùng ở đâu | Provider | Ảnh hưởng execution? |
|------------|----------|----------------------|
| External `gemini_google` | Gemini + grounding optional | Không |
| Market Synthesis narrative | Gemini text-only | Không |
| Analyst Chat | Gemini + deterministic fallback | Không (intent execution → fallback) |

- Không sửa raw technical facts.
- Không tool calling đặt lệnh.
- Thiếu key / disable → deterministic.
- Docs: Phase 16.3.6 real grounding **BLOCKED** (thiếu evidence API key).

Phân biệt: **Technical Truth** (deterministic) ≠ **External Intelligence** (sources) ≠ **AI Synthesis** (narrative).

---

## M. DASHBOARD

| UI Section | API | Backend | Read-only? |
|------------|-----|---------|------------|
| Account Summary | `/account/overview` | MT5 account | YES |
| Symbols/tabs | `/quotes` + MTF | MT5 + analysis | YES |
| Trading Analysis | `/multi-timeframe` + `/execution-candidate` | MTF + contract | YES |
| Key Levels / Entry / MTF / Evidence / Plan / Risk | từ MTF + candidate | analysis | YES |
| Positions | `/positions` | MT5 | YES list |
| Close position | `POST .../close` | PositionCloseService | **NO** (gated) |
| Realized PnL | `/account/pnl/daily` | history | YES |
| Market Context | `/market-synthesis` | external+synthesis | YES |
| AI Analyst | `POST .../analyst-chat` | chat service | YES |

Frontend search: **không** import Orchestrator / GatedMT5 / MT5Executor / LiveTransport / `order_send`.

Duplicate presentation đã giảm sau Unified Trading Analysis Card; Entry Zone vẫn xuất hiện ở Key Levels + Trade Plan (plan giữ giá trị executable — intentional secondary).

---

## N. DATA STORES / PERSISTENCE

| Data | Storage | Owner | Purpose |
|------|---------|-------|---------|
| Setup lifecycle | SQLite | contract | Durable setup states |
| Auto-demo decisions | SQLite sibling DB | auto_demo | Idempotency theo candle |
| Orchestrator intents | SnapshotIntentStore | orchestrator | Lifecycle (CLI thiếu file path) |
| External cache/history | JSON/JSONL | external_context | Cache research |
| Synthesis cache | JSON/JSONL | synthesis | Cache narrative |
| Analyst chat sessions | `data/analyst_chat` | analyst_chat | Session history |
| Active MT5 profile | `.mt5_active_account` | account_runtime | demo/live profile |
| Backtests | `data/backtests/*.json` | backtest | Research reports |
| Paper state | `.paper_execution_state.json` | paper | Paper sim |

Cần giữ qua restart: decisions DB, setup lifecycle, `.env`, MT5 profile. Intent file path hiện thiếu trên CLI.

---

## O. RESEARCH vs PRODUCTION

| Component | Production | Research | Execution Allowed |
|-----------|------------|----------|-------------------|
| `mtf_technical_v1` | YES | — | YES (gated DEMO) |
| `mtf_technical_v2_candidate` | NO | YES | **NO** |
| Backtests | — | YES | NO |
| Forward validation | — | YES | NO |
| External Intelligence | Display | YES | **NO** |
| AI synthesis/chat | Display | YES | **NO** |
| Dashboard analysis | YES | — | NO open-trade |
| Dashboard close | YES gated | — | Close-only |
| Auto DEMO | YES gated | — | DEMO only |
| Manual controlled DEMO CLI | YES gated | — | DEMO only |

**V2:** `PROMISING_V2_REQUIRES_MORE_DATA`; **không promote**.

---

## P. PHASE HISTORY

| Phase | Purpose | Status | Output |
|-------|---------|--------|--------|
| 0–9 | Foundation → early dashboard | Superseded | Docs/base |
| 10.x | API + Dashboard RO | PASS | FastAPI + Next |
| 11.x | Candle/paper/exec arch | CONDITIONAL→evolved | Architecture |
| 12.x | Intent/gates/DEMO smoke | PASS / evidence PENDING | Gated MT5 path |
| 15 | Account overview | PASS | Dashboard home |
| 16–16.2 | Technical + MTF v1 | PASS | Canonical strategy |
| 16.2.4 | V2 research | PASS research | No promote |
| 16.3.x | Contract + External + Chat | PASS / 16.3.6 BLOCKED | Context RO |
| 17.1–17.2 | Candidate→Orchestrator / UX | PASS | Integration |
| **17.3** | Autonomous DEMO loop | **Impl PASS / Evidence PENDING** | CLI loop |

**CURRENT ACTIVE PHASE:** 17.3 Autonomous DEMO Execution  

**CURRENT REAL OBJECTIVE:** Có **bằng chứng lệnh DEMO thật** (một closed M15 eligible → ACCEPTED/FILLED hoặc documented REJECT) trên allowlist, không mở LIVE.

---

## Q. WHAT ACTUALLY WORKS TODAY

### WORKING NOW
- MT5 attach + API read account/positions/quotes/MTF
- `mtf_technical_v1` analysis + setup + candidate status API
- Dashboard unified analysis + positions/PnL/context/chat UI
- Execution stack unit/integration với Fake transport
- Auto-demo CLI preflight / dry-run / decision persistence
- External free_sources providers (khi ENABLED)

### IMPLEMENTED BUT NOT FULLY VERIFIED
- Autonomous DEMO **real** `order_send` fill evidence
- Intent store durability trên CLI auto-demo
- External intelligence runtime end-to-end “AVAILABLE” ổn định (phụ thuộc nguồn + ENABLED)
- Gemini grounding thật (16.3.6)

### RESEARCH / NOT PRODUCTION
- `mtf_technical_v2_candidate`
- Forward validation datasets
- Backtest/paper legacy paths
- AI narrative/chat

---

## R. KNOWN GAPS

| Severity | Gap |
|----------|-----|
| CRITICAL | REAL DEMO order evidence vẫn PENDING |
| HIGH | CLI auto-demo không truyền `state_path` → intent không bền restart |
| HIGH | `EXECUTION_MODE` không gate auto-demo dù hot-read |
| HIGH | Snapshot provider CLI hardcode một số trade/quote flags |
| MEDIUM | Docs ROADMAP/ARCHITECTURE outdated (Phase 0 Current) |
| MEDIUM | Docs “sole order_send” vs legacy adapter + dashboard close |
| MEDIUM | H1/H4 conflict docs vs blocking eligibility |
| LOW | UX polish; FRED mặc định tắt; poll interval docs vs hardcode 5s |

---

## S. NHỮNG THỨ KHÔNG NÊN TẬP TRUNG LÚC NÀY

- Promote / retune `mtf_technical_v2_candidate`
- Wire External/AI → signal hoặc execution
- LIVE trading / tắt kill switch cho live
- Redesign dashboard lớn ngoài việc hỗ trợ đọc DEMO evidence
- Gemini grounding thật nếu chưa cần cho objective DEMO evidence
- Mở rộng symbol/strategy mới

---

## T. PROJECT FLOW — SIMPLE VERSION (≤15 bước)

1. MT5 Exness cung cấp nến/quote/tài khoản.  
2. Bot chỉ dùng **nến đã đóng** (M15 chính + H1/H4/D1).  
3. Bot tính indicator + cấu trúc + hỗ trợ/kháng cự.  
4. Chiến lược `mtf_technical_v1` cho điểm số từng khung và tổng hợp.  
5. Nếu đủ điều kiện → tín hiệu LONG/SHORT; không thì WAIT.  
6. Bot tạo vùng vào lệnh, SL, TP1/TP2/TP3.  
7. Nếu giá vào vùng + risk OK → tạo `ExecutionCandidate`.  
8. Dashboard **chỉ hiển thị** phân tích/candidate/vị thế (đóng lệnh là tính năng riêng có khóa).  
9. External/AI chỉ giải thích thị trường — **không** đặt lệnh.  
10. Auto DEMO CLI (process riêng) theo dõi M15 đóng.  
11. Nếu trùng decision_id → bỏ qua.  
12. Nếu gates DEMO fail → BLOCKED, không gửi broker.  
13. Nếu pass → Orchestrator đánh dấu IN_FLIGHT rồi gửi qua Gated MT5.  
14. Chỉ transport live gọi `order_send` (DEMO).  
15. Kết quả lưu decision store; dashboard đọc lại qua API.

---

## U. ONE-SCREEN PROJECT MAP

```
PROJECT: Exness algorithmic trading monorepo (Python engine + Next dashboard)
CURRENT GOAL: Verify autonomous DEMO execution with real broker evidence
INPUT: MT5 closed candles + quotes + account (Exness)
TECHNICAL ENGINE: MultiTimeframeAnalysisService (closed M15/H1/H4/D1)
STRATEGY: mtf_technical_v1 (production) | mtf_technical_v2_candidate (research only)
SETUP: Entry zone + SL + TP1–3; lifecycle WAITING_FOR_ENTRY / ENTRY_ZONE / …
RISK: Eligibility + sizing + auto-demo risk_gates + GatedMT5
EXECUTION: CandidateExecutionService → Orchestrator → GatedMT5 → Executor → LiveTransport
BROKER: MetaTrader5.order_send (DEMO gated; legacy adapter isolated)
AUTONOMOUS MODE: CLI python -m exness_bot.execution.auto_demo (not auto-started by API)
DASHBOARD: Read analysis/context + gated position close only
EXTERNAL DATA: free_sources (BLS/Fed/RSS/FRED) → Market Context only
AI: Gemini synthesis/chat read-only; no execution tools
RESEARCH: V2 scoring + forward validation; no promote
CURRENT BLOCKER: REAL DEMO ORDER EVIDENCE PENDING
NEXT MILESTONE: One documented DEMO fill/reject under allowlist + kill-switch discipline
```

---

## V. NEXT ACTIONS (tối đa 5)

1. **Thu thập REAL DEMO evidence**  
   - WHY: Phase 17.3 còn PENDING; đây là objective thật.  
   - DONE WHEN: Có smoke JSON / log decision `ACCEPTED`/`REJECTED` + retcode MT5 trong `docs/evidence/` (không bịa).

2. **Sửa gap CLI `state_path` cho intent store**  
   - WHY: Docs nói durable intent; code CLI không truyền path.  
   - DONE WHEN: Restart process vẫn đọc được IN_FLIGHT/UNKNOWN intents.

3. **Audit lại snapshot hardcodes trong auto_demo CLI**  
   - WHY: trade_allowed/quote_fresh hardcode làm lệch fail-closed outer gate.  
   - DONE WHEN: Preflight/gate dùng giá trị đọc thật từ MT5.

4. **Đồng bộ docs ROADMAP/ARCHITECTURE với Phase 17.3**  
   - WHY: Developer mới bị mất context vì Phase 0 “Current”.  
   - DONE WHEN: ROADMAP trỏ đúng active phase + link AUTONOMOUS_DEMO.

5. **Giữ External/AI read-only; bật `EXTERNAL_INTELLIGENCE_ENABLED` chỉ để dashboard context**  
   - WHY: Không làm nhiễu objective DEMO evidence.  
   - DONE WHEN: Market Context AVAILABLE/PARTIAL khi muốn — vẫn `EXTERNAL→EXECUTION: NONE`.

---

## Phụ lục — Docs outdated / mâu thuẫn với CODE

| Doc | Vấn đề |
|-----|--------|
| `docs/ROADMAP.md` | Vẫn “Phase 0 Current”; Phase 1–8 Pending |
| `docs/ARCHITECTURE.md` | Diagram FastAPI “Future”; thiếu market_analysis/execution/auto_demo |
| `docs/TRADING_RULES.md` | Legacy EMA/RSI fixed TP — không phải v1 |
| `docs/LIVE_EXECUTION_ARCHITECTURE.md` | CURRENT gắn 12.9/12.10, chưa 17.3 |
| `docs/PHASE_16_2_…` | H1/H4 conflict chỉ warning vs eligibility blocking |
| `PHASE_17_3` / một số report | “sole order_send” đúng path mới; legacy adapter + dashboard close vẫn gọi `order_send` |
| `trading-engine/README.md` | “Full trading logic not yet implemented” lỗi thời |
| Intent durability docs | CLI không truyền `state_path` |

---

## Phụ lục — Execution path nguy hiểm?

| Path | Nguy hiểm? | Ghi chú |
|------|------------|---------|
| Auto-demo → LiveTransport | Có chủ đích DEMO | Nhiều gate; evidence PENDING |
| Legacy `MT5Adapter` | Có nếu `ALLOW_LEGACY_RUN=true` | Default false |
| Dashboard close | Có chủ đích | Gate phrase + flags |
| External/AI | Không | Không nối execution |
| Analysis API | Không | Read candidate only |

**Không phát hiện backdoor AI→order_send.**  
**Cần cảnh giác:** `.env` operator có thể đã mở `AUTO_DEMO=true` + `LIVE_KILL_SWITCH=false` — vẫn chỉ an toàn nếu account DEMO allowlist đúng và không nhầm LIVE.
