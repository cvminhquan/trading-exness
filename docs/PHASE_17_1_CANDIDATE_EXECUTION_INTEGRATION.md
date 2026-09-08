# PHASE 17.1 — ExecutionCandidate → ExecutionOrchestrator Integration

**Transport boundary: FAKE / Spy only.**

**REAL MT5 `order_send` executed: NO**  
**LiveMT5ExecutionTransport reachable from Phase 17.1 path: NO**  
**Automatic broker execution enabled: NO**

---

## Result

**PASS**

Validation (trading-engine):

- `pytest`: **907 passed**, 5 skipped
- `ruff check src tests`: clean
- `mypy src`: clean
- Phase 17.1 unit tests: **31 passed**
- Phase 12.6 orchestration: regression covered in full suite
- CLI smoke `candidate-execution-smoke`: exit 0, submit count 1, broker mutation NO
- Safety audit on `execution/integration`: no `order_send` / LiveMT5 / gated port / `broker.mt5` imports

Phase 16.3 `ExecutionCandidate` (`mtf_technical_v1`) is connected to the existing Phase-12 `ExecutionOrchestrator` without rebuilding the execution engine.

---

## Architecture

```
MultiTimeframeAnalysis
    ↓
CanonicalTradeSetup (durable SqliteSetupLifecycleStore)
    ↓
ExecutionCandidate
    ↓
CandidateExecutionService.consume
    ├─ precheck (fail-closed)
    ├─ CandidateExecutionAdapter → ExecutionPlan
    ↓
ExecutionOrchestrator (sole lifecycle owner)
    ↓
FakeExecutionPort / SpyExecutionPort
```

Phase 12 components remain source of truth:

- `ExecutionOrchestrator`
- `DurableIntentStore` / `SnapshotIntentStore`
- idempotency keys
- UNKNOWN recovery (no auto-resubmit)
- IN_FLIGHT-before-side-effect
- global unresolved blocking

---

## Source contract

Only allowed strategy input:

- `strategyId = mtf_technical_v1`

Rejected (fail-closed `LEGACY_STRATEGY_NOT_EXECUTABLE`):

- `ema_rsi_atr_v1`
- `phase16_decide_signal_v1`
- any non-canonical ID via `LEGACY_NON_EXECUTABLE_STRATEGY_IDS` / `!= MTF_STRATEGY_ID`

---

## Adapter

Module: `trading-engine/src/exness_bot/execution/integration/adapter.py`

Mapping only (no sizing / signal / S/R recalculation):

| Candidate / setup field | ExecutionPlan |
|-------------------------|---------------|
| `candidate_id` | `signal_id`, metadata |
| `setup_id` | metadata |
| `analysis_fingerprint` | metadata |
| `mtf_technical_v1` | `strategy_id` |
| `symbol` / `broker_symbol` | symbol + metadata |
| `side` LONG/SHORT | `SignalDirection` |
| `entry` / SL / TP list | SL + **TP1** as `take_profit`; full TP list in metadata |
| `proposed_volume` | `requested_volume` |
| risk estimates | metadata |
| source candle timestamp | `signal_timestamp` |

---

## Idempotency key

Deterministic (never random UUID):

```
strategy_id
+ symbol
+ primary_timeframe
+ source_candle_timestamp
+ setup_id
+ candidate_id
+ side
```

Implemented by extending Phase-12 `build_execution_idempotency_key` with
`signal_id = "{setup_id}|{candidate_id}"`, stored as `plan.metadata["idempotency_key"]`.

Same candidate consumed twice → at most one `port.submit`.

---

## Orchestrator ownership & lifecycle ordering

Required lifecycle (unchanged):

```
CREATED → persist → IN_FLIGHT → persist DURABLY → port.submit → FILLED | REJECTED | UNKNOWN
```

Invariant preserved and tested via Spy `on_submit`:

**IN_FLIGHT must be durably persisted BEFORE `ExecutionPort.submit`.**

Adapter and candidate service never transition lifecycle or submit directly.

---

## Precheck (`CandidateExecutionPrecheck`)

Verdict: `READY` | `BLOCKED`.

Gates include:

1. Canonical strategy
2. Candidate eligibility (`eligible`, risk, broker, IDs, fingerprint, volume)
3. Reload setup from durable store
4. Lifecycle revalidation (`ENTRY_ZONE`, not expired/invalidated/superseded)
5. Fingerprint match (`ANALYSIS_FINGERPRINT_CHANGED`)
6. Timeframe / quote / account freshness
7. Durable Sqlite setup store mandatory (`DURABLE_SETUP_STORE_UNAVAILABLE`)
8. Strict broker metadata (no `contract_size=100` fallback)
9. Spread guard
10. Unresolved intent guard (`UNRESOLVED_EXECUTION_EXISTS`)

If any gate fails → **do not** call `ExecutionOrchestrator`.

---

## Freshness & account hardening

- Quote age vs `LIVE_DATA_STALE_SECONDS`
- Account age vs `ACCOUNT_SNAPSHOT_MAX_AGE_SECONDS` using authoritative `snapshot.updated_at`
- Missing account timestamp → `ACCOUNT_FRESHNESS_UNKNOWN` (fail closed)
- Required TF context: M15 / H1 / H4 / D1 must be LIVE

---

## Durable setup store

Analysis API may still use in-memory fallback for read-only paths.

**Consume path:** `SqliteSetupLifecycleStore` required via `require_durable_setup_store`.

In-memory store → block with `DURABLE_SETUP_STORE_UNAVAILABLE`.

---

## Fake transport boundary

Factory: `execution/integration/factory.py` → `build_fake_candidate_execution_service`

- Constructs `SpyExecutionPort` only
- Does **not** import `broker.mt5`, `LiveMT5ExecutionTransport`, or `build_gated_mt5_execution_port`
- No `--live` CLI option

CLI: `exness-bot candidate-execution-smoke --symbol XAUUSD`

---

## UNKNOWN & unresolved

- Fake UNKNOWN → intent `UNKNOWN` → `READ_ONLY_RECONCILIATION_REQUIRED`
- Re-consume same / new candidate while unresolved → **zero** additional submits
- Existing `INTENT_CREATED` / `IN_FLIGHT` / `UNKNOWN` globally blocks new execution

---

## Failure injection

| Scenario | Expected |
|----------|----------|
| Fake FILLED | 1 submit |
| Fake REJECTED | 1 submit |
| Fake UNKNOWN | 1 submit; no retry |
| Persist fail before IN_FLIGHT | 0 submit |
| Persist fail on create | 0 submit |
| Finalize fail after side effect | UNKNOWN; no resend |

---

## Duplicate protection

Covered:

- same candidate same process
- same candidate after service recreation (shared intent store)
- same candidate after store reload / idempotency collision
- repeated consume simulating API poll

---

## Tests

- `tests/unit/test_phase_17_1_candidate_execution_integration.py`
- Existing Phase-12 orchestration suites remain regression gates

---

## Safety audit

Search Phase 17.1 integration package for:

- `order_send(`
- `LiveMT5ExecutionTransport`
- `build_gated_mt5_execution_port`
- `broker.mt5`

Expected: **no** broker-mutating dependency reachable from the Phase 17.1 factory.

---

## Remaining limitations

1. **TP1 only** on `ExecutionPlan.take_profit` — multi-TP stays in metadata until a later execution phase.
2. Paper / backtest **not** migrated to MTF (Phase 16.3 plan unchanged).
3. No mutation HTTP API (`POST /execute`) — smoke CLI / tests only.
4. Phase 17.2 will introduce gated DEMO MT5; this phase must not be extended to live transport.
5. Analysis read API may still use in-memory setup store; only **consume** mandates Sqlite.

---

## Files (primary)

| Path | Role |
|------|------|
| `execution/integration/adapter.py` | Candidate → plan |
| `execution/integration/precheck.py` | Fail-closed gates |
| `execution/integration/service.py` | `CandidateExecutionService` |
| `execution/integration/factory.py` | Fake-only wiring |
| `execution/integration/smoke_cli.py` | Safe smoke |
| `execution/integration/models.py` | Precheck / result |
| `cli.py` | `candidate-execution-smoke` |
| `config/settings.py` | `ACCOUNT_SNAPSHOT_MAX_AGE_SECONDS` |
| `docs/PHASE_17_1_CANDIDATE_EXECUTION_INTEGRATION.md` | This document |
