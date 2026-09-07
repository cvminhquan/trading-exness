# DEMO Execution Smoke — Operator Runbook

**Phase:** 12.10  
**Command:** `exness-bot demo-execution-smoke`  
**Submit (HUMAN ONLY):** `exness-bot demo-execution-smoke --execute --confirm DEMO-EXECUTE`

Canonical path:

```text
ExecutionOrchestrator
  → GatedMT5ExecutionPort
  → MT5Executor
  → OneShotExecutionTransport
  → LiveMT5ExecutionTransport
  → MT5 order_send()
```

Deterministic smoke order (after all gates):

```text
SIDE = BUY
VOLUME = 0.01          # CONTROLLED_DEMO_TEST_VOLUME — not strategy sizing
SYMBOL = XAUUSD
BROKER_SYMBOL = XAUUSDm
```

---

## Warning

```text
This command can place ONE DEMO order.
It must never be used against a production account.
The Cursor agent must NEVER run the --execute command.
```

Repository defaults must stay:

```text
LIVE_KILL_SWITCH=true
LIVE_DEMO_APPROVAL=false
EXECUTION_MODE=paper
ALLOW_LEGACY_RUN=false
```

Temporary local overrides are operator-only and must be restored after the smoke.
Do not commit local DEMO overrides.

---

## Operator checklist (Phase 12.10)

### 1. Run read-only preflight

```bash
exness-bot demo-execution-smoke
```

Do not proceed unless overall is **PASS**.

### 2. Verify account is DEMO

Confirm connected `trade_mode=demo` (broker identity — not config alone).

### 3. Verify XAUUSDm

Confirm `LIVE_SYMBOL_MAP=XAUUSD:XAUUSDm` (or equivalent) and preflight broker symbol = `XAUUSDm`.

### 4. Verify spread

Confirm `spread_points <= MAX_SPREAD_POINTS` (DEMO may use `MAX_SPREAD_POINTS=260`; do not raise further).

### 5. Verify VOLUME=0.01

Banner / intent must show explicit controlled DEMO test lot `0.01` — never strategy-sized volume.

### 6. Human executes the one-shot command

```bash
exness-bot demo-execution-smoke --execute --confirm DEMO-EXECUTE
```

Requirements:

- Exact phrase `DEMO-EXECUTE` (no fuzzy / yes / interactive fallback)
- Maximum **one** broker submission
- No strategy loop, no retry, no auto-close

### 7. Capture terminal output

Save sanitized logs (mask login). File under `docs/evidence/phase-12-10/` if desired.

Expected local fields after gates:

```text
SIDE=BUY
VOLUME=0.01
SYMBOL=XAUUSD
BROKER_SYMBOL=XAUUSDm
transport_send_count <= 1
```

### 8. Perform read-only reconciliation

Inspect via read-only MT5 / CLI evidence (order, deal, position, ticket, price, timestamp).

```text
Do NOT call order_send during reconciliation.
Do NOT mutate broker state to “fix” UNKNOWN.
```

### 9. Do not resubmit UNKNOWN

If lifecycle is `UNKNOWN`:

```text
STOP
DO NOT RETRY
DO NOT RESUBMIT
DO NOT CLOSE AUTOMATICALLY
VERIFY BROKER STATE READ-ONLY
RECONCILE INTENT
ONLY THEN CONTINUE
```

### 10. Do not auto-close an open position

```text
Position remains open and requires separate explicit operator action.
```

### 11. Restore safe defaults

```text
LIVE_KILL_SWITCH=true
LIVE_DEMO_APPROVAL=false
EXECUTION_MODE=paper
ALLOW_LEGACY_RUN=false
```

Also restore any temporary DEMO-only overrides you changed locally.

---

## Before execution (detailed)

```text
[ ] Connected to intended MT5 terminal
[ ] Account verified DEMO (connected trade_mode=demo)
[ ] Server verified / allowlisted
[ ] Account allowlisted (DEMO_ACCOUNT_ALLOWLIST)
[ ] Symbol mapping verified (XAUUSD → XAUUSDm)
[ ] Quote fresh (QUOTE: FRESH)
[ ] Spread within MAX_SPREAD_POINTS
[ ] Terminal trade permission enabled (Algo Trading)
[ ] Kill switch intentionally disabled LOCALLY for this one-shot only
[ ] LIVE_DEMO_APPROVAL=true LOCALLY
[ ] TRADING_ENV=demo LOCALLY
[ ] Legacy run disabled (ALLOW_LEGACY_RUN=false)
[ ] Read-only preflight PASS
```

---

## After execution

```text
[ ] Broker response captured (sanitized)
[ ] Broker state independently queried (read-only)
[ ] Local intent reconciled (FILLED | REJECTED | UNKNOWN)
[ ] transport_send_count <= 1
[ ] No duplicate submission (ledger blocks second run)
[ ] Any open position documented — do NOT auto-close
[ ] Safe defaults restored
[ ] No autonomous loop enabled
[ ] Optional sanitized evidence under docs/evidence/phase-12-10/
```

---

## Second run

A second `--execute` must be **BLOCKED** by the demo smoke ledger.

Do **not** attempt a second real broker submission to “verify” idempotency.

---

## Related docs

- [`PHASE_12_10_DEMO_EXECUTION_EVIDENCE.md`](PHASE_12_10_DEMO_EXECUTION_EVIDENCE.md)
- [`PHASE_12_9_CONTROLLED_DEMO_EXECUTION_HARDENING.md`](PHASE_12_9_CONTROLLED_DEMO_EXECUTION_HARDENING.md)
- [`evidence/phase-12-10/README.md`](evidence/phase-12-10/README.md)
- [`LIVE_EXECUTION_ARCHITECTURE.md`](LIVE_EXECUTION_ARCHITECTURE.md)
