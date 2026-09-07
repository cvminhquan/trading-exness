# PHASE 12.9 — CONTROLLED DEMO EXECUTION PATH HARDENING

**Date:** 2026-09-07  
**Scope:** DEMO-only path hardening. Does **not** enable autonomous live trading.

---

## 1. Problem

Phase 12.8 introduced `GatedMT5ExecutionPort` under `ExecutionOrchestrator`, but the
controlled DEMO smoke CLI still used a **parallel** path:

```text
ControlledDemoSmoke
  → evaluate_demo_controlled_enablement (once)
  → build_controlled_demo_intent → RiskManager.assess  ← strategy sizing
  → OneShotExecutionTransport + MT5Executor(custom enablement bypass)
```

Issues:

1. **Duplicated / bypassed gate evaluation** — smoke used a synthetic post-approval
   `LiveEnablementResult` inside `MT5Executor` instead of `GatedMT5ExecutionPort`.
2. **Oversized volume** — RiskManager sized ~**38.99 lots** on a large DEMO equity with
   tight synthetic ATR geometry, then failed `MAX_POSITION_LOTS=1.0` before the intent
   factory could apply `volume_min`.
3. Smoke was treated like a strategy trade rather than a deterministic execution probe.

---

## 2. Current architecture (after 12.9)

```text
demo-execution-smoke
        ↓
ControlledDemoSmoke (operator CLI boundary only)
        ↓
ExecutionOrchestrator          ← lifecycle owner (CREATED → IN_FLIGHT → terminal)
        ↓
GatedMT5ExecutionPort          ← evaluate_demo_controlled_enablement (reuse)
        ↓
MT5Executor (require_enablement=False)
        ↓
OneShotExecutionTransport      ← durable process guard; ledger adds restart guard
        ↓
FakeMT5ExecutionTransport | LiveMT5ExecutionTransport
```

Default runtime remains paper:

```text
build_execution_service → Paper only
LIVE_KILL_SWITCH=true
LIVE_DEMO_APPROVAL=false
EXECUTION_MODE=paper
ALLOW_LEGACY_RUN=false
```

---

## 3. Previous failure

Operator / smoke evidence (Phase 12.x):

```text
Position size 38.99 exceeds maximum allowed 1.0 lots
```

Later paths that forced `VOLUME=0.01` after risk approval were incomplete when
`RiskManager.assess` **rejected** first — intent never built.

---

## 4. Root cause of 38.99 lot calculation

`build_controlled_demo_intent` previously:

1. Built a synthetic Signal with small ATR (from `stops_level` / `point`).
2. Called `RiskManager.assess` → `calculate_position_size(equity, risk_pct, SL)`.
3. On a large DEMO equity (order of ~$58k) with tight SL distance, raw volume ≈ **38.99**.
4. `check_max_position_size(38.99, MAX_POSITION_LOTS=1.0)` → **reject**.
5. Only *after* a successful assess would the factory set `volume = symbol.volume_min`.

So the smoke path depended on strategy risk sizing and failed closed on max lots —
or, if max lots were weakened, would have submitted an absurd size.

**Fix:** never call strategy risk sizing for controlled DEMO. Use an explicit constant.

---

## 5. Controlled DEMO sizing design

```text
CONTROLLED_DEMO_TEST_VOLUME = 0.01   # auditable constant
        ↓
resolve_controlled_demo_volume()
        ↓ validate:
            - exact match to 0.01
            - broker volume_min / volume_max / volume_step
            - MAX_POSITION_LOTS ceiling
        ↓
ExecutionPlan.requested_volume = 0.01
```

- SL/TP: geometric from stops metadata (not equity risk budget).
- `RiskManager` behavior for normal strategy signals is **unchanged**.
- Oversized strategy positions still reject on `MAX_POSITION_LOTS`.

Files:

- `controlled_demo/intent_factory.py`

---

## 6. Unified execution path

`ControlledDemoSmoke.run`:

1. Read-only probe + `evaluate_demo_controlled_enablement` (CLI UX / early block).
2. Require `--execute` + `--confirm DEMO-EXECUTE`.
3. `build_controlled_demo_plan` → explicit 0.01.
4. Freeze **prior** intent snapshot (exclude the about-to-be IN_FLIGHT intent).
5. `build_gated_mt5_execution_port(..., wrap_oneshot=False)` with local oneshot wrap.
6. `ExecutionOrchestrator.execute(plan)`.
7. Ledger + approval consume **only if** `gated.executor_submit_count > 0`.

Removed:

- Custom `_demo_enablement` / `LiveEnablementResult` bypass inside smoke.
- Direct `MT5Executor(require_enablement=True)` wiring from smoke.

Gate rules are not duplicated — both preflight and gated port call
`evaluate_demo_controlled_enablement`.

---

## 7. Safety invariants

| Invariant | Status |
|-----------|--------|
| Kill switch blocks | Keep |
| DEMO env / trade_mode | Keep |
| Allowlist | Keep |
| Approval required | Keep (rechecked by gated port) |
| Quote freshness | Keep |
| Terminal trade permission | Keep |
| Symbol map / allowlist | Keep |
| Strategy loop disconnected | Keep |
| No auto-close / auto-retry UNKNOWN | Keep |
| Safe defaults unchanged | Keep |
| `MAX_SPREAD_POINTS` not increased beyond operator DEMO need | Keep (default 50; DEMO may use 260 locally) |
| No credentials in source | Keep |

---

## 8. UNKNOWN handling

Lifecycle remains:

```text
CREATED → IN_FLIGHT (durable before transport) → FILLED | REJECTED | UNKNOWN
```

- Transport / ack ambiguity → `UNKNOWN`.
- Finalize persistence failure after side effect → `UNKNOWN`.
- `UNKNOWN` never auto-resubmits.
- Unresolved `CREATED` / `IN_FLIGHT` / `UNKNOWN` blocks new plans (`UnresolvedIntentGuard`).
- Durable ledger blocks a second controlled DEMO submission across CLI restarts.

---

## 9. One-shot guarantee

| Layer | Behavior |
|-------|----------|
| `OneShotExecutionTransport` | `transport_send_count` / process max one `send` |
| `DemoSmokeLedger` | `prior_submission_count >= 1` → enablement BLOCK |
| Approval consume | After executor reached |
| Orchestrator idempotency | Same plan key → no second port submit |

Target for controlled DEMO smoke: **`transport_send_count <= 1`**.

---

## 10. Test results

| Gate | Result |
|------|--------|
| pytest | **778 passed**, 1 deselected |
| ruff check src tests | **PASS** |
| mypy src | **PASS** (168 source files) |
| `exness-bot demo-execution-smoke --help` | **PASS** (agent-safe) |

Suite: `tests/unit/test_phase_12_9_controlled_demo_hardening.py` covers:

1. controlled DEMO uses 0.01 lot  
2–4. broker min / step / max-lots  
5. RiskManager sizing unchanged  
6. oversized strategy still rejected  
7. smoke uses `GatedMT5ExecutionPort`  
8–14. kill switch, non-DEMO, allowlist, approval, stale quote, trade permission, invalid symbol  
15–16. duplicate / unresolved UNKNOWN blocks  
17. IN_FLIGHT before transport send  
18. send count ≤ 1  
19–21. REJECTED / UNKNOWN / no auto-resubmit  
22. strategy loop not invoked  

Prior Phase 12.4 / 12.8 suites still pass.

**Not run by agent:**

```text
exness-bot demo-execution-smoke --execute --confirm DEMO-EXECUTE
```

---

## 11. Static audit results

| Check | Result |
|-------|--------|
| Phase 12 `order_send` mutation boundary | `LiveMT5ExecutionTransport` in `broker/mt5/execution_transport.py` |
| Legacy `order_send` | `adapter.py` / `trading_client.py` — isolated by `ALLOW_LEGACY_RUN=false` |
| `demo-execution-smoke` | Present; wires gated path |
| Safe Settings defaults | `LIVE_KILL_SWITCH=true`, `LIVE_DEMO_APPROVAL=false`, `EXECUTION_MODE=paper`, `ALLOW_LEGACY_RUN=false` |
| Intent factory | No `RiskManager`; `CONTROLLED_DEMO_TEST_VOLUME = 0.01` |

### dotenv warning

Previous warning:

```text
python-dotenv could not parse statement starting at line 13
```

Investigation: almost always an **unquoted** `MT5_PASSWORD=...` containing `#`, spaces, or quotes.
Local `.env` line 13 is a commented password placeholder; guidance added to `.env` and
`.env.example` to require double-quoted passwords. **Password values were never printed.**

---

## 12. Remaining risks

1. Real DEMO one-shot still requires a human operator; this phase does **not** claim broker fill evidence.
2. Multi-process exactly-once is still not guaranteed (single-process ledger + oneshot).
3. Gated snapshot uses **frozen prior intents** so the orchestrator's own IN_FLIGHT is not
   self-blocked — correct for composition, but operators must still recover true stuck
   IN_FLIGHT / UNKNOWN before re-running.
4. Open DEMO positions after a fill still require **separate explicit** operator action
   (no auto-close).

---

## 13. Operator-only DEMO execution instructions

1. Restore / set local overrides carefully (never commit):

```text
TRADING_ENV=demo
LIVE_KILL_SWITCH=false          # temporary
LIVE_DEMO_APPROVAL=true         # temporary
DEMO_ACCOUNT_ALLOWLIST=<login>
DEMO_SERVER_ALLOWLIST=<server>
LIVE_SYMBOL_MAP=XAUUSD:XAUUSDm
MAX_SPREAD_POINTS=260           # DEMO quote tolerance; do not raise further
ALLOW_LEGACY_RUN=false
EXECUTION_MODE=paper            # smoke CLI path is explicit; keep default paper
```

2. Read-only preflight:

```bash
exness-bot demo-execution-smoke
```

3. Only if PASS, human runs:

```bash
exness-bot demo-execution-smoke --execute --confirm DEMO-EXECUTE
```

4. Expect deterministic intent fields after gates:

```text
SIDE = BUY
VOLUME = 0.01
SYMBOL = XAUUSD / XAUUSDm
```

5. Immediately restore:

```text
LIVE_KILL_SWITCH=true
LIVE_DEMO_APPROVAL=false
```

6. If lifecycle is `UNKNOWN`: read-only reconcile only — **do not resubmit**.

Cursor agents must **never** run step 3.

---

## Files changed

- `trading-engine/src/exness_bot/controlled_demo/intent_factory.py`
- `trading-engine/src/exness_bot/controlled_demo/smoke.py`
- `trading-engine/src/exness_bot/cli.py` (docstring)
- `trading-engine/tests/unit/test_phase_12_9_controlled_demo_hardening.py` (new)
- `trading-engine/.env.example` (password quoting guidance)
- `docs/PHASE_12_9_CONTROLLED_DEMO_EXECUTION_HARDENING.md` (this file)
- `docs/LIVE_EXECUTION_ARCHITECTURE.md`
- `docs/DEMO_EXECUTION_SMOKE_RUNBOOK.md`

---

## PHASE 12.9 RESULT

```text
PASS
```

**Reasons:**

- Controlled DEMO smoke unified onto `ExecutionOrchestrator → GatedMT5ExecutionPort → MT5Executor → OneShotExecutionTransport`.
- Explicit auditable `VOLUME=0.01`; root cause of 38.99 lot RiskManager sizing removed from smoke path without weakening `MAX_POSITION_LOTS` or normal RiskManager.
- Lifecycle / UNKNOWN / one-shot / MT5 boundary / safe defaults preserved.
- pytest **778 passed**, ruff **PASS**, mypy **PASS**.
- Real DEMO `--execute` was **not** performed by the agent; broker fill success is **not** claimed.
