# Roadmap — Exness Trading Bot

## Phase 0: Foundation ✅ (Current)

**Goal:** Documentation, project structure, config, domain models, safety guards, tooling.

| Task | Status |
|------|--------|
| PRD, Architecture, Trading Rules, Roadmap | ✅ |
| Python package structure (`src/exness_bot`) | ✅ |
| Pydantic Settings with DEMO defaults | ✅ |
| Domain models & enums | ✅ |
| BrokerPort interface (stub) | ✅ |
| SafetyGuard implementation | ✅ |
| Unit tests for config & safety | ✅ |
| pyproject.toml, ruff, mypy, pytest | ✅ |
| Docker Compose (PostgreSQL) | ✅ |
| README | ✅ |

**Deliverable:** Runnable `pytest`, `ruff check`, `mypy` — no live trading logic.

---

## Phase 1: Market Data & Indicators

**Goal:** Connect MT5 Demo, fetch XAUUSD M15, compute indicators.

| Task | Priority |
|------|----------|
| MT5Adapter.connect / disconnect / health | P0 |
| MT5Adapter.get_bars | P0 |
| MT5Adapter.get_account_info | P0 |
| MT5MarketDataProvider | P0 |
| IndicatorCalculator: EMA 20/50/200 | P0 |
| IndicatorCalculator: RSI 14 | P0 |
| IndicatorCalculator: ATR 14 | P0 |
| Unit tests with fixture DataFrames | P0 |
| Integration test `@pytest.mark.mt5` | P1 |

**Exit criteria:** Script logs latest bars + indicator values from Demo account.

---

## Phase 2: Strategy & Signals

**Goal:** EMA trend + RSI strategy producing typed signals.

| Task | Priority |
|------|----------|
| Confirm RSI/ATR thresholds with user | P0 |
| EmaTrendRsiStrategy implementation | P0 |
| Signal factory & validation | P0 |
| Strategy unit tests (bull/bear/sideways fixtures) | P0 |
| Bar-close detection (no duplicate signals) | P1 |

**Exit criteria:** Strategy returns correct signals on historical fixture data.

---

## Phase 3: Risk Management

**Goal:** Position sizing and limit enforcement.

| Task | Priority |
|------|----------|
| PositionSizer (ATR-based SL → lot size) | P0 |
| DailyLossTracker | P0 |
| DrawdownTracker | P0 |
| MaxOpenPositions check | P0 |
| RiskManager.assess() integration | P0 |
| Unit tests for all rejection paths | P0 |

**Exit criteria:** RiskManager correctly approves/rejects with logged reasons.

---

## Phase 4: Order Execution

**Goal:** Safe order placement on Demo.

| Task | Priority |
|------|----------|
| OrderManager with DRY_RUN path | P0 |
| OrderManager pre-flight safety checks | P0 |
| MT5Adapter.place_order | P0 |
| MT5Adapter.close_position | P1 |
| Position tracking | P1 |
| Structured order logging | P0 |

**Exit criteria:** Demo order placed (or dry-run logged) with SL/TP attached.

---

## Phase 5: Trading Engine & CLI

**Goal:** End-to-end loop on Demo.

| Task | Priority |
|------|----------|
| TradingEngine orchestrator | P0 |
| M15 bar-close scheduler / polling | P0 |
| CLI: `exness-bot run --dry-run` | P0 |
| CLI: `exness-bot run --demo` | P0 |
| Graceful shutdown & reconnect | P1 |
| Health check endpoint (optional) | P2 |

**Exit criteria:** Bot runs on Demo, logs signals and orders for 24h without crash.

---

## Phase 6: Persistence

**Goal:** PostgreSQL storage for audit trail.

| Task | Priority |
|------|----------|
| SQLAlchemy models: trades, signals, risk_events | P0 |
| Alembic migrations | P0 |
| Repository layer | P1 |
| Day-start equity snapshot job | P1 |

**Exit criteria:** All signals and orders persisted, queryable.

---

## Phase 7: Backtesting

**Goal:** Validate strategy on historical data.

| Task | Priority |
|------|----------|
| CsvMarketDataProvider | P0 |
| SimulatedOrderExecutor | P0 |
| BacktestRunner | P0 |
| Metrics: win rate, max DD, profit factor | P0 |
| CLI: `exness-bot backtest --file data.csv` | P1 |
| MT5 history export script | P2 |

**Exit criteria:** Backtest report generated for 6+ months XAUUSD M15.

---

## Phase 8: Production Readiness

**Goal:** Safe VPS deployment.

| Task | Priority |
|------|----------|
| Windows VPS setup guide | P0 |
| Live trading triple-guard + CLI `--confirm-live` | P0 |
| Monitoring & alerting (Telegram/email) | P1 |
| Docker engine on Linux (data only) + Win agent | P2 |
| Failover / restart policies | P2 |

**Exit criteria:** Documented deployment, live trading only with explicit flags.

---

## Phase 9: Dashboard (Future)

**Goal:** Next.js web UI.

| Task | Priority | Status |
|------|----------|--------|
| FastAPI REST API | P1 | Pending |
| Next.js + React Query scaffold | P1 | ✅ Phase 10.1 |
| Dashboard UX & visual polish | P1 | ✅ Phase 10.2 |
| Trades & equity chart | P1 | ✅ MVP (mock) |
| Strategy config UI | P2 | Pending |
| Manual kill switch | P0 | Pending |

---

## Phase 10: Dashboard MVP

| Phase | Scope | Status |
|-------|-------|--------|
| 10.1 | Architecture, routes, repository, mock data | ✅ |
| 10.2 | UX polish, formatting, responsive layout, a11y | ✅ |
| 10.3 | Backtest analytics dashboard | ✅ |
| 10.4 | API contract & repository boundary | ✅ |
| 10.5 | FastAPI read-only server | ✅ Done |
| 10.6 | MT5 read-only live data adapter | ✅ Done |

---

## Unresolved Decisions

| ID | Question | Owner | Target Phase |
|----|----------|-------|--------------|
| D-01 | RSI entry thresholds final values | User | Phase 2 |
| D-02 | ATR SL multiplier & R:R ratio | User | Phase 2 |
| D-03 | Max spread filter for XAUUSD | User | Phase 3 |
| D-04 | PostgreSQL schema v1 | Dev | Phase 6 |
| D-05 | Backtest data source | Dev | Phase 7 |
| D-06 | Polling interval vs bar event | Dev | Phase 5 |
| D-07 | VPS: Windows-only vs Wine | Dev | Phase 8 |

---

## Version Milestones

| Version | Scope | Target |
|---------|-------|--------|
| v0.1.0 | Foundation (this phase) | 2026-08 |
| v0.2.0 | Market data + indicators | TBD |
| v0.3.0 | Strategy + signals | TBD |
| v0.4.0 | Risk + orders (Demo) | TBD |
| v0.5.0 | Engine + CLI | TBD |
| v0.6.0 | Backtest | TBD |
| v1.0.0 | Production-ready Demo + optional Live | TBD |
