# Phase 12.5 Report — Real MT5 DEMO Smoke & Recovery Validation

**Date:** 2026-09-04  
**Scope:** Operator-controlled validation of the Phase 12.4 execution boundary against a real MT5 DEMO account (read-only preflight + Fake-transport recovery). No autonomous trading.  
**Status: CONDITIONAL**

---

## Overall status

```text
CONDITIONAL
```

| Label | Meaning |
|-------|---------|
| **PASS** | Would require ONE real DEMO `order_send`, independent read-only verify, restart/ledger block, and safe defaults restored |
| **CONDITIONAL** | Boundary + recovery proven in automated tests; real connected DEMO identity verified read-only; real broker submission **NOT TESTED** (gates correctly blocked) |
| **BLOCKED** | Reserved for unexpected unsafe path — not observed |
| **NOT TESTED** | Real DEMO `order_send` / FILLED position reconcile against broker |
| **NOT IMPLEMENTED** | Autonomous live trading; SignalEngine→MT5Executor; Dashboard trade controls |

---

## Step 1 — Pre-execution audit

| Item | Result |
|------|--------|
| `MT5Executor` | EXISTS — `broker/mt5/executor.py` |
| `LiveMT5ExecutionTransport` | EXISTS — only Phase 12 path that may call `order_send` |
| `OneShotExecutionTransport` | EXISTS — max one `send` |
| DurableIntentStore (`SnapshotIntentStore`) | EXISTS |
| `BrokerExecutionQuery` / UNKNOWN recovery | EXISTS — no automatic resubmit |
| Demo approval gates | EXISTS — `LIVE_DEMO_APPROVAL`, `--confirm DEMO-EXECUTE` |
| Legacy `exness-bot run` | Disabled by default (`ALLOW_LEGACY_RUN=false`) |
| `EXECUTION_MODE=live` globally | NOT enabled (default `paper`) |
| Strategy loop → `MT5Executor` | ABSENT |
| Dashboard/API trading endpoints | ABSENT |
| Second broker mutation path on Phase 12 | ABSENT (legacy isolated) |

Phase 11 packages (`candle_engine/`, `signal_engine/`, `risk/`, `paper_execution/`): **no** `order_send`, `TRADE_ACTION_DEAL`, `MT5Executor`, `LiveMT5ExecutionTransport`, `MT5Adapter`, `TradingClient`, `OrderManager`.

---

## REAL MT5 DEMO EVIDENCE (read-only)

Command:

```text
exness-bot demo-execution-smoke
```

(no `--execute` — **no** `order_send`)

| Field | Observed |
|-------|----------|
| MT5 connection | PASS — terminal readable |
| Masked login | `***4158` |
| Broker/server | `Exness-MT5Trial17` |
| Account `trade_mode` | `demo` (authoritative from connected account) |
| Currency | `USD` |
| Broker symbol | `XAUUSDm` (explicit map via `MT5_SYMBOL` / settings) |
| Symbol visibility | PASS |
| Bid / Ask | `4456.134` / `4456.394` |
| Volume min/step/max | `0.01` / `0.01` / `200.0` |
| stops_level / freeze_level | `0` / `0` |
| Quote freshness | BLOCKED — STALE (`age_seconds≈30` on second probe; earlier probe much older) |
| Terminal state | PASS — `connected=true` |
| `trade_allowed` (terminal) | BLOCKED — `trade_allowed=false` (terminal Algo Trading / trade disabled) |
| Overall preflight | **BLOCKED** |

Blocking configuration gates (fail-closed, as designed):

| Gate | Status |
|------|--------|
| `TRADING_ENV` | BLOCKED — observed `research` (must be `demo`) |
| `LIVE_KILL_SWITCH` | BLOCKED — `true` (repo/operator default) |
| `LIVE_DEMO_APPROVAL` | BLOCKED — `false` |
| `DEMO_ACCOUNT_ALLOWLIST` | BLOCKED — empty |
| Quote freshness | BLOCKED — STALE |
| Terminal trade permission | BLOCKED — `terminal.trade_allowed=false` |

**Real broker submission this session:** `NOT TESTED`  
**No credentials/secrets printed.**

---

## AUTOMATED TEST EVIDENCE

| Case | Result |
|------|--------|
| UNKNOWN → CONFIRMED_FILLED → FILLED | PASS (Fake / query only) |
| UNKNOWN → CONFIRMED_REJECTED → REJECTED | PASS |
| UNKNOWN → NOT_FOUND → UNKNOWN | PASS |
| UNKNOWN → AMBIGUOUS → UNKNOWN | PASS |
| UNKNOWN → UNAVAILABLE → UNKNOWN | PASS |
| Recovery never calls `order_send` | PASS (static + unit) |
| Second smoke / ledger blocks; spy transport `calls==[]` | PASS |
| Restart preserves intent_id / idempotency / FILLED lifecycle | PASS |
| Preflight kill-switch BLOCKED | PASS |
| Preflight does not call `.order_send(` | PASS |
| Ambiguous positions → position_match UNKNOWN | PASS |
| Safe defaults (`kill_switch`, approval, paper, legacy) | PASS |

---

## Exactly-once / open position policy

- IN_FLIGHT persisted before `transport.send` (Phase 12.4 path unchanged).
- Max one transport submission per smoke; ledger blocks a second attempt.
- UNKNOWN never auto-resubmits.
- If a future real FILLED smoke leaves a position open: report must show ticket/symbol/side/volume/open/SL/TP and state *"Position remains open and requires separate explicit operator action."* — **no auto-close** in 12.5.

---

## Safe defaults restoration

Repository / Settings defaults verified:

```text
LIVE_KILL_SWITCH=true
LIVE_DEMO_APPROVAL=false
EXECUTION_MODE=paper
ALLOW_LEGACY_RUN=false
```

`.env.example` unchanged on these keys. Local operator `.env` was **not** flipped to force a real order.

---

## Quality gates

| Gate | Result |
|------|--------|
| `pytest` | **679 passed**, 5 skipped, 1 deselected |
| `ruff check src tests` | PASS |
| `mypy src` | PASS (154 source files) |

Dashboard: not modified — dashboard tests not required.

---

## Acceptance criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Real connected MT5 account identity verified | PASS (read-only, masked) |
| 2 | Connected account proven DEMO | PASS (`trade_mode=demo`) |
| 3 | Broker/server identity verified | PASS (`Exness-MT5Trial17`) |
| 4 | Explicit symbol mapping verified | PASS (`XAUUSD` → `XAUUSDm`) |
| 5 | Fresh quote verified | BLOCKED (STALE at probe time) |
| 6 | Stops/freeze metadata verified | PASS |
| 7 | Risk validation verified | AUTOMATED (unit); real path NOT TESTED |
| 8 | IN_FLIGHT before side effect | AUTOMATED PASS |
| 9 | Exactly ONE real DEMO broker submission | NOT TESTED |
| 10 | Broker execution response captured | NOT TESTED |
| 11 | Broker state independently verified | NOT TESTED (submit) / PASS (preflight RO) |
| 12 | Local intent reconciled vs broker | AUTOMATED; real NOT TESTED |
| 13 | Restart preserves final lifecycle | AUTOMATED PASS |
| 14 | Second smoke cannot submit again | AUTOMATED PASS |
| 15 | UNKNOWN recovery never resubmits | AUTOMATED PASS |
| 16 | No strategy loop | PASS |
| 17 | No autonomous live trading | PASS |
| 18 | No production/real-money path enabled | PASS |
| 19 | Safe defaults restored | PASS |
| 20 | Static safety audit | PASS |
| 21–23 | pytest / ruff / mypy | PASS (679 / ruff / mypy) |

---

## Remaining limitations

1. Operator must set `TRADING_ENV=demo`, disable kill switch **locally**, set `LIVE_DEMO_APPROVAL=true`, populate `DEMO_ACCOUNT_ALLOWLIST`, ensure fresh quote, then run `--execute --confirm DEMO-EXECUTE` for a real PASS.
2. Market/session may leave quotes STALE — fail-closed correctly.
3. No automatic position close after smoke.
4. Phase 12.6+ must not start from this report automatically.

---

## Phase 12.6 readiness

```text
NOT READY FOR AUTONOMOUS TRADING
```

Decision: **Do not begin Phase 12.6 automatically.**  
Phase 12.5 leaves the controlled boundary validated in tests and partially on a real DEMO account (identity only). Real one-shot FILLED evidence remains operator-gated.

---

## Changed files (Phase 12.5)

- `trading-engine/src/exness_bot/controlled_demo/preflight.py` — structured PASS/BLOCKED/FAIL/NOT_TESTED; terminal_state
- `trading-engine/src/exness_bot/controlled_demo/evidence.py` — broker evidence + position match
- `trading-engine/src/exness_bot/controlled_demo/identity.py` — terminal_info fields
- `trading-engine/src/exness_bot/controlled_demo/smoke.py` — evidence / session_id / open-position warning
- `trading-engine/src/exness_bot/controlled_demo/__init__.py` — exports
- `trading-engine/src/exness_bot/cli.py` — preflight-first; evidence log
- `trading-engine/tests/unit/test_phase_12_5_recovery.py` — UNKNOWN A–E, second smoke, defaults
- `docs/PHASE_12_5_REPORT.md` — this file
- `docs/LIVE_EXECUTION_ARCHITECTURE.md` — Phase 12.5 section
