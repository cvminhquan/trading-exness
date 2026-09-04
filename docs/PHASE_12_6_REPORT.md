# Phase 12.6 Report — Execution Orchestration Hardening

**Date:** 2026-09-04  
**Scope:** Deterministic orchestration layer (`ExecutionPlan` → `ExecutionOrchestrator` → `DurableIntentStore` → `ExecutionPort`) with Fake/Paper only.  
**Status: PASS**

---

## 1. Overall status

```text
PASS
```

```text
EXECUTION ORCHESTRATION VALIDATED
REAL MT5 EXECUTION STILL OPERATOR-ONLY
AUTONOMOUS BROKER WIRING NOT IMPLEMENTED
```

Không kết luận `READY FOR AUTONOMOUS LIVE TRADING`.

---

## 2. Architectural changes

Package mới `exness_bot/execution/` (broker-neutral):

| Module | Vai trò |
|--------|---------|
| `plan.py` | `ExecutionPlan` immutable |
| `eligibility.py` | `ExecutionEventKind` LIVE / CATCH_UP / REPLAY |
| `idempotency.py` | Deterministic execution identity |
| `guard.py` | `ExecutionGuard` + eligibility + unresolved UNKNOWN |
| `orchestrator.py` | Durable CREATED → IN_FLIGHT → submit → terminal |
| `spy.py` | `SpyExecutionPort` (đếm `calls`) |
| `planning.py` | Build plan từ `SignalResult` + `ApprovedOrderPlan` |
| `smoke_cli.py` | Diagnostic Fake-only |

`ExecutionService.consume` **refactor** để gọi `ExecutionOrchestrator` sau Risk/validation (một lifecycle path).

```text
                         ┌─ Paper/Fake ExecutionPort ✅
ExecutionOrchestrator ───┤
                         └─ MT5Executor ❌ NOT WIRED
```

---

## 3. ExecutionPlan design

Immutable dataclass, broker-neutral:

`plan_id`, `signal_id`, `strategy_id`, `symbol`, `timeframe`, `side`, `requested_volume`, `stop_loss`, `take_profit`, `signal_timestamp`, `decision_timestamp`, `reason`, `metadata`, `event_kind`.

Không chứa: ticket MT5, status mutable, `TRADE_ACTION_*`.

Phân biệt:

- **Plan** = quyết định muốn khớp  
- **Intent** = cam kết vào execution boundary  

---

## 4. Idempotency design

```text
strategy_id|symbol|timeframe|candle_ts|signal_id|side
```

Cùng logical decision → cùng key → intent hiện có trả về → `port_calls == 0`.

Paper path giữ `SignalResult.idempotency_key` qua `metadata["idempotency_key"]`.

**Giới hạn:** single-process `SnapshotIntentStore` + file JSON — **không** distributed exactly-once.

---

## 5. Lifecycle / state-machine evidence

| Transition | Evidence |
|------------|----------|
| CREATED → IN_FLIGHT trước side effect | Unit: `in_flight_before_submit == IN_FLIGHT` |
| IN_FLIGHT → FILLED / REJECTED / UNKNOWN | Spy responses |
| IN_FLIGHT crash → UNKNOWN, no resubmit | Restart recovery test |
| Forbidden FILLED→IN_FLIGHT etc. | `assert_transition_allowed` raises |

---

## 6. Duplicate-event tests

| Scenario | Result |
|----------|--------|
| Same plan twice | 1 call |
| Restart + same signal | 0 second calls |
| Concurrent/sequential same key | store lock + idempotency |

---

## 7. Catch-up blocking

| Event kind | Result |
|------------|--------|
| `CATCH_UP_EVENT` | BLOCKED, `calls==0` |
| `REPLAY_EVENT` | BLOCKED, `calls==0` |
| `LIVE_EVENT` | eligible |

---

## 8. UNKNOWN blocking / recovery

Unresolved CREATED / IN_FLIGHT / UNKNOWN **global** block plan mới (khác key).  
UNKNOWN không auto-retry / auto-resubmit.  
Reconcile vẫn qua path Phase 12.x hiện có.

---

## 9. Restart behavior

| State | After restart |
|-------|---------------|
| FILLED / REJECTED / UNKNOWN | Persisted; duplicate no submit |
| IN_FLIGHT | `recover_in_flight_to_unknown` → UNKNOWN; no resubmit |

---

## 10. Failure-injection results

| Case | Expected | Result |
|------|----------|--------|
| A Store fail before CREATED | 0 calls | PASS |
| B IN_FLIGHT persist fail | 0 calls | PASS |
| C Port exception after IN_FLIGHT | UNKNOWN, no retry | PASS |
| D Reject | REJECTED | PASS |
| E Success | FILLED | PASS |
| F Finalize fail after side effect | UNKNOWN / no resend | PASS |

---

## 11. Static broker-boundary audit

- `execution/` core: no `MetaTrader5`, `order_send`, `LiveMT5ExecutionTransport`
- Phase 11 packages clean
- `build_execution_service` / factory: no MT5Executor wiring
- CLI smoke: Fake only (`BROKER EXECUTION: DISABLED`)

---

## 12. CLI diagnostic evidence

```text
exness-bot execution-orchestration-smoke
```

Observed:

```text
BROKER EXECUTION: DISABLED
TRANSPORT: FAKE/PAPER
lifecycle: FILLED
execution_port_calls: 1
```

Không instantiate `LiveMT5ExecutionTransport`.

---

## 13. Test results

| Gate | Result |
|------|--------|
| pytest | **699 passed**, 5 skipped, 1 deselected |
| ruff | PASS |
| mypy | PASS (164 source files) |

---

## 14. Remaining risks

1. Multi-process / multi-host duplicate vẫn có thể xảy ra (JSON store).  
2. Real DEMO `order_send` vẫn **NOT TESTED** (Phase 12.5 CONDITIONAL).  
3. Paper `ExecutionService` giờ block global trên UNKNOWN — chặt hơn per-key cũ (an toàn hơn).  
4. Orchestrator chưa thay `controlled_demo` smoke (vẫn one-shot riêng).  

---

## 15. Changed files

- `trading-engine/src/exness_bot/execution/*` (new)
- `trading-engine/src/exness_bot/paper_execution/service.py` (refactor → orchestrator)
- `trading-engine/src/exness_bot/paper_execution/__init__.py` (lazy `ExecutionService`)
- `trading-engine/src/exness_bot/cli.py` (`execution-orchestration-smoke`)
- `trading-engine/tests/unit/test_phase_12_6_orchestration.py`
- `docs/PHASE_12_6_REPORT.md`
- `docs/LIVE_EXECUTION_ARCHITECTURE.md`

---

## 16. Phase 12.7 recommendation

```text
DO NOT BEGIN Phase 12.7 AUTOMATICALLY
```

Khuyến nghị khi sẵn sàng (operator review):

1. Hoàn tất real DEMO one-shot evidence (12.5 → PASS) nếu cần trước live wiring.  
2. Chỉ khi có runbook UNKNOWN + open-position: cân nhắc wire **gated** `MT5Executor` dưới orchestrator + kill switch — vẫn **không** SignalEngine loop liên tục.  
3. Không Dashboard BUY/SELL; không production money.

Safe defaults unchanged:

```text
LIVE_KILL_SWITCH=true
LIVE_DEMO_APPROVAL=false
EXECUTION_MODE=paper
ALLOW_LEGACY_RUN=false
```
