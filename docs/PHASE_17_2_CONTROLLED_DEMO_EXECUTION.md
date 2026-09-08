# PHASE 17.2 — Controlled Exness DEMO Strategy Execution

**ExecutionCandidate → Gated MT5 DEMO one-shot (operator-triggered only)**

---

## Result classification

| Layer | Status |
|-------|--------|
| **PHASE 17.2 IMPLEMENTATION** | **PASS** (code + fake E2E + full suite) |
| **REAL DEMO EVIDENCE** | **PENDING** (human operator only) |
| **OVERALL** | **CONDITIONAL — AWAITING OPERATOR DEMO EVIDENCE** |

---

## Mandatory statements

- **REAL MT5 `order_send` executed by agent: NO**
- **Automatic strategy → broker execution enabled: NO**
- **Strategy loop connected to MT5 execution: NO**
- **Execution mode: CONTROLLED OPERATOR-TRIGGERED DEMO ONE-SHOT ONLY**
- **UNKNOWN automatic resubmission: DISABLED**
- **Open DEMO position auto-close: NO**

### Hotfix — preview data source (2026-09-08)

Preview previously wrapped MT5 in a partial `_DataSource` (snapshot/tick only),
so `MultiTimeframeAnalysisService` crashed with `get_candles` missing.

**Fix:** inject `MT5TradingDataProvider` directly (same contract as Dashboard /
Phase 16.2). Signature reused:

`get_candles(self, symbol: str, timeframe: Timeframe, count: int) -> list[Candle] | None`

Insufficient closed candles → `MTF_DATA_UNAVAILABLE` (fail closed), never AttributeError.

---

## Agent prohibition

The AI / Cursor agent **MUST NEVER** run:

```text
exness-bot candidate-demo-execution-smoke --execute --confirm DEMO-EXECUTE
```

Only a human operator may authorize broker mutation. Automated tests use `FakeMT5ExecutionTransport` only.

---

## Architecture

```
ExecutionCandidate (mtf_technical_v1)
    → CandidateExecutionService (Phase 17.1 reuse)
    → CandidateExecutionAdapter → ExecutionPlan (TP1_ONLY)
    → ExecutionOrchestrator (Phase 12)
    → GatedMT5ExecutionPort
    → MT5Executor
    → OneShotExecutionTransport
    → LiveMT5ExecutionTransport   # human CLI only
         OR FakeMT5ExecutionTransport  # tests / preview
    → Exness DEMO
```

Default app path remains paper / Fake (Phase 17.1).  
`build_controlled_demo_candidate_execution_service` is **not** used by strategy loop or dashboard.

---

## Preview vs mutation

| Mode | Command | Behavior |
|------|---------|----------|
| **PREVIEW** (default) | `candidate-demo-execution-smoke --symbol XAUUSD` | MTF candidate + 17.1/17.2 precheck + DEMO gates; **REAL order_send: NO** |
| **EXECUTE** (human) | `... --execute --confirm DEMO-EXECUTE` | One gated submit; max 1 OneShot send |

Wrong / missing confirm → **zero** sends.

---

## Candidate revalidation (before submit)

Reuses Phase 17.1 precheck, plus Phase 17.2 market revalidate:

- Fresh M15/H1/H4/D1, quote, account (`ACCOUNT_SNAPSHOT_MAX_AGE_SECONDS`)
- Entry zone vs **ASK** (LONG) / **BID** (SHORT)
- Spread vs `MAX_SPREAD_POINTS`
- SL / TP1 side + `stops_level` / `freeze_level`
- Volume from **candidate.proposed_volume** (no `CONTROLLED_DEMO_TEST_VOLUME=0.01` override)
- Strict broker metadata (no `contract_size=100` fallback)
- Durable Sqlite setup store required
- Unresolved `CREATED` / `IN_FLIGHT` / `UNKNOWN` block

`EXECUTED_TP_POLICY = TP1_ONLY` — TP2/TP3 remain metadata only.

---

## DEMO gates (Phase 12 reuse)

- `TRADING_ENV=demo`
- `LIVE_KILL_SWITCH=false`
- `LIVE_DEMO_APPROVAL=true`
- Account allowlist + server allowlist
- Broker `trade_mode` proven DEMO (not inferred from server name alone)
- Symbol map explicit

Safe repository defaults remain:

- `LIVE_KILL_SWITCH=true`
- `LIVE_DEMO_APPROVAL=false`
- `EXECUTION_MODE=paper`

---

## Idempotency / OneShot / UNKNOWN

- Same candidate identity → at most one broker send (durable intent store)
- `OneShotExecutionTransport` fail-closed on second `send`
- UNKNOWN → read-only reconciliation only; **no** auto-resubmit
- Open DEMO positions are **not** auto-closed

Concurrent multi-process exactly-once is **not** claimed beyond existing single-process durable store + OneShot + ledger semantics of Phase 12.

---

## Files

| Path | Role |
|------|------|
| `execution/integration/demo_factory.py` | Gated factory (inject transport; never builds Live itself) |
| `execution/integration/demo_revalidate.py` | Entry/SL/TP/volume/spread recheck |
| `execution/integration/demo_cli.py` | Preview + human execute runner |
| `execution/integration/service.py` | `transport_label` + demo revalidate flag |
| `cli.py` | `candidate-demo-execution-smoke` |
| `tests/unit/test_phase_17_2_candidate_demo_execution.py` | Fake E2E matrix |
| `docs/PHASE_17_2_DEMO_RUNBOOK.md` | Operator runbook |

---

## Tests / validation

Validation evidence (trading-engine):

- `pytest`: **934 passed**, 5 skipped
- `ruff check src tests`: clean
- `mypy src`: clean
- Phase 17.2 unit tests: **27 passed**
- Phase 17.1 regression: included in full suite

- Fake gated E2E covered:
  - eligible → 1 send → FILLED
  - Zero-send matrix: preview, wrong confirm, kill switch, approval, env, allowlists, lifecycle, stale TF, spread, risk, metadata, unresolved UNKNOWN
  - Duplicate / UNKNOWN no resubmit
  - Volume from candidate (not Phase-12 forced 0.01 rewrite)
  - Safety: no `order_send(` in integration package; `LiveMT5ExecutionTransport(` only in human CLI execute branch of `demo_cli.py`


---

## Remaining limitations

1. Real Exness DEMO evidence requires human operator runbook (separate).
2. No dashboard Execute control.
3. No strategy loop → broker wiring.
4. No partial TP / position management.
5. Margin estimation: relies on existing Phase-12 gated / MT5 executor checks where available — no invented leverage.

See [PHASE_17_2_DEMO_RUNBOOK.md](./PHASE_17_2_DEMO_RUNBOOK.md).
