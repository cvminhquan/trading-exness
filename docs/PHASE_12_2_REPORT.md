# Phase 12.2 Report — Live Enablement Gate & Preflight Hardening

**Date:** 2026-08-29  
**Scope:** Multi-gate live enablement + read-only preflight (API/CLI). Non-trading.  
**Status: CONDITIONAL**

---

## Status

```text
CONDITIONAL
```

| Label | Ý nghĩa |
|-------|---------|
| **PASS** | 11 gates fail-closed, readiness ≠ execution capability, kill switch, UNKNOWN blocks, legacy isolation, API/CLI read-only, tests/ruff/mypy |
| **CONDITIONAL** | `EXECUTION_MODE=live` parseable for preflight nhưng không operational; broker identity phụ thuộc allowlist cấu hình |
| **NOT IMPLEMENTED** | `MT5Executor`, live order execution, operational `EXECUTION_MODE=live` |
| **NOT TESTED** | Live MT5 account identity against real terminal |
| **BLOCKED** | Không — sẵn sàng Phase 12.3 (live executor) khi được approve riêng |

---

## Live execution

```text
NOT IMPLEMENTED
```

`allowed` luôn `False`. `MT5_EXECUTOR_IMPLEMENTED = False`.

---

## Gate matrix (defaults)

| Gate | Default result | Reason |
|------|----------------|--------|
| Execution mode | BLOCKED | paper (live required for future path) |
| Explicit live flag | BLOCKED | ALLOW_LIVE_TRADING=false |
| Environment | BLOCKED | TRADING_ENV≠live |
| Broker identity | BLOCKED | allowlist empty / mismatch |
| Symbol metadata | depends | stops/freeze/quote/volume |
| Risk config | PASS (if defaults valid) | existing RiskManager bounds |
| Intent store | PASS (if healthy) | UNKNOWN/IN_FLIGHT block |
| UNKNOWN reconciliation | BLOCKED | query unavailable by default |
| Legacy isolation | PASS | ALLOW_LEGACY_RUN=false |
| Kill switch | BLOCKED | LIVE_KILL_SWITCH=true (default) |
| Executor capability | BLOCKED | MT5Executor NOT IMPLEMENTED |

---

## Readiness vs capability

```text
configuration_preflight_ready  ≠  execution_capability
PREFLIGHT_READY / NOT_IMPLEMENTED  ≠  LIVE READY
```

Statuses: `LIVE_DISABLED` | `BLOCKED` | `PREFLIGHT_READY` | `NOT_IMPLEMENTED`

---

## Surfaces

- `GET /api/v1/live-readiness` — read-only
- `exness-bot live-preflight` — read-only, exit 1 when not allowed

---

## Quality gates

```text
pytest: 600 passed, 5 skipped
ruff: clean
mypy: clean (142 source files)
dashboard: NOT CHANGED / NOT RUN
```

---

## Static safety

Phase 12 enablement modules: no `order_send`, no `TRADE_ACTION_*`, no `class MT5Executor`, no `MT5Adapter` imports.

Legacy stack still isolated behind `ALLOW_LEGACY_RUN`.

---

## Known limitations

1. Local JSON intent store only (Phase 12.1).  
2. Broker identity allowlist is config-based, not live terminal probe in all contexts.  
3. CLI preflight uses UnavailableBrokerExecutionQuery unless wired later.  

---

## Phase 12.3 readiness

Còn lại trước live-execution phase:

1. Implement `MT5Executor` behind ExecutionPort (riêng, có approve)  
2. Wire real BrokerExecutionQuery + account identity from read-only client  
3. Activate multi-gates only after executor exists  
4. Demo smoke với approval riêng  

**Không** tự bắt đầu Phase 12.3.
