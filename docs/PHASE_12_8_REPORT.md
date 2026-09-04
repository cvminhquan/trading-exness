# PHASE 12.8 REPORT

## Status

```text
PASS
```

```text
Phase 12.8 DOES NOT ENABLE AUTONOMOUS LIVE TRADING.
```

---

## Objective

Tích hợp `MT5Executor` qua `GatedMT5ExecutionPort` dưới `ExecutionOrchestrator`, tái sử dụng demo safety gates, **không** bật autonomous live trading và **không** nối strategy loop tới MT5.

---

## Architecture

```text
ExecutionOrchestrator  (lifecycle owner)
        ↓
GatedMT5ExecutionPort  (pre-submit demo gates)
        ↓
MT5Executor            (request build + transport)
        ↓
OneShotExecutionTransport
        ↓
FakeMT5ExecutionTransport | LiveMT5ExecutionTransport
```

Default runtime:

```text
build_execution_service → Paper only
```

Gated MT5 chỉ qua:

```text
exness_bot.execution.mt5.factory.build_gated_mt5_execution_port(...)
```

```text
                         ┌─ Paper/Fake ✅ (default)
ExecutionOrchestrator ───┤
                         └─ GatedMT5 → MT5Executor ✅ (explicit factory only)
                                      Live transport ❌ not auto-wired
```

---

## Implementation

| Component | Path |
|-----------|------|
| `GatedMT5ExecutionPort` | `execution/mt5/gated_port.py` |
| `GatedExecutionSnapshot` | `execution/mt5/snapshot.py` |
| Factory | `execution/mt5/factory.py` |
| Gates reused | `controlled_demo.enablement.evaluate_demo_controlled_enablement` |

Inner `MT5Executor(require_enablement=False)` — demo gates sống ở outer gated port (tránh xung đột live enablement).

---

## Safety Gates

| Gate | Behavior |
|------|----------|
| Kill switch | `LIVE_KILL_SWITCH=true` → BLOCK, no executor |
| Demo environment | `TRADING_ENV != demo` → BLOCK |
| Approval | `LIVE_DEMO_APPROVAL` / snapshot approval → BLOCK if false |
| Allowlist | Empty `DEMO_ACCOUNT_ALLOWLIST` → BLOCK |
| Symbol map | Empty / unmapped symbol → BLOCK |
| Quote freshness | STALE / unknown → BLOCK |
| Terminal permission | `trade_allowed=false` → BLOCK |

---

## Lifecycle

`ExecutionOrchestrator` vẫn là owner duy nhất:

```text
CREATED → IN_FLIGHT (durable) → port.submit → FILLED|REJECTED|UNKNOWN
```

Gated port **không** create/persist intent.

---

## Idempotency

Giữ deterministic key qua orchestrator. Same plan → one port call.

---

## UNKNOWN Recovery

Ambiguous / transport UNKNOWN → lifecycle UNKNOWN → no resubmit; unresolved UNKNOWN blocks plan mới (global).

---

## MT5 Boundary

- `.order_send(` trên Phase 12 path: `LiveMT5ExecutionTransport`
- Legacy `MT5Adapter` / `MT5TradingClient` vẫn isolated (`ALLOW_LEGACY_RUN=false`)
- Core `execution/{plan,orchestrator,guard,...}` không import `broker.mt5`
- Integration: `execution/mt5/`

---

## Strategy Loop

```text
NOT WIRED
```

`build_execution_service` không instantiate `GatedMT5ExecutionPort` / `MT5Executor` / Live transport.

---

## Tests

| Gate | Result |
|------|--------|
| pytest | **742 passed**, 5 skipped, 1 deselected |
| ruff | PASS |
| mypy | PASS |

Suite: `tests/unit/test_phase_12_8_gated_mt5.py` (gates, side-effect, idempotency, UNKNOWN, restart, failure injection, defaults, static).

---

## Static Audit

`order_send` call sites (Phase 12):

```text
broker/mt5/execution_transport.py  → LiveMT5ExecutionTransport.send
```

Legacy (blocked by default): `trading_client.py`, `adapter.py`.

`import MetaTrader5`: read-only client / CLI availability messages only — not in strategy/signal/risk/orchestrator.

---

## Files Changed

- `trading-engine/src/exness_bot/execution/mt5/*` (new)
- `trading-engine/src/exness_bot/paper_execution/factory.py` (doc: never wire gated MT5)
- `trading-engine/tests/unit/test_phase_12_8_gated_mt5.py`
- `docs/PHASE_12_8_REPORT.md`
- `docs/LIVE_EXECUTION_ARCHITECTURE.md`

---

## Safety Defaults

```text
LIVE_KILL_SWITCH=true
LIVE_DEMO_APPROVAL=false
EXECUTION_MODE=paper
ALLOW_LEGACY_RUN=false
```

Unchanged.

---

## What Was NOT Executed

```text
demo-execution-smoke --execute
MetaTrader5.order_send (real)
Any broker-mutating action
Strategy loop → MT5
```

---

## What remains disabled

```text
AUTONOMOUS LIVE TRADING: NOT IMPLEMENTED
PRODUCTION EXECUTION: NOT ENABLED
STRATEGY → MT5 EXECUTOR: NOT WIRED
DEFAULT RUNTIME: PAPER
```

---

## Remaining Risks

1. Real DEMO one-shot vẫn operator-gated (Phase 12.7 CONDITIONAL).  
2. Controlled demo smoke chưa bắt buộc đi qua `GatedMT5ExecutionPort` (vẫn MT5Executor + demo enablement riêng — cùng `evaluate_demo_controlled_enablement`).  
3. Multi-process exactly-once vẫn không có.

---

## Recommendation

```text
DO NOT BEGIN Phase 12.9 AUTOMATICALLY
```

Tiếp theo (nếu có): operator hoàn tất DEMO smoke theo runbook; cân nhắc thống nhất smoke CLI qua `GatedMT5ExecutionPort` — vẫn không autonomous loop.
