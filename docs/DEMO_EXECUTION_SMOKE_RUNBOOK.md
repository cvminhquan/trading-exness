# DEMO Execution Smoke — Operator Runbook

**Phase:** 12.7  
**Command:** `exness-bot demo-execution-smoke`  
**Submit (HUMAN ONLY):** `exness-bot demo-execution-smoke --execute --confirm DEMO-EXECUTE`

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

---

## Before execution

```text
[ ] Connected to intended MT5 terminal
[ ] Account verified DEMO (connected trade_mode=demo — not config alone)
[ ] Server verified
[ ] Account allowlisted (DEMO_ACCOUNT_ALLOWLIST)
[ ] Symbol mapping verified (LIVE_SYMBOL_MAP / MT5_SYMBOL)
[ ] Quote fresh (QUOTE: FRESH — not STALE)
[ ] Terminal trade permission enabled (Algo Trading / trade_allowed=true)
[ ] Kill switch intentionally disabled LOCALLY for this one-shot only
[ ] LIVE_DEMO_APPROVAL=true LOCALLY
[ ] TRADING_ENV=demo LOCALLY
[ ] Legacy run disabled (ALLOW_LEGACY_RUN=false)
[ ] Read-only preflight PASS:

      exness-bot demo-execution-smoke
```

Do not proceed if preflight reports BLOCKED / FAIL.

---

## Execution (human operator only)

```bash
exness-bot demo-execution-smoke --execute --confirm DEMO-EXECUTE
```

Requirements:

- Exact phrase `DEMO-EXECUTE` (no fuzzy / yes / interactive fallback)
- Maximum **one** broker submission
- No strategy loop, no retry, no auto-close

---

## After execution

```text
[ ] Broker response captured (sanitized evidence log)
[ ] Broker state independently queried (read-only)
[ ] Local intent reconciled
[ ] No duplicate submission (ledger blocks second run)
[ ] Any open position documented — do NOT auto-close
[ ] Safe defaults restored locally:
      LIVE_KILL_SWITCH=true
      LIVE_DEMO_APPROVAL=false
      EXECUTION_MODE=paper
      ALLOW_LEGACY_RUN=false
[ ] No autonomous loop enabled
[ ] Sanitized evidence filed under docs/evidence/phase-12-7/ (optional operator copy)
```

Open position policy:

```text
Position remains open and requires separate explicit operator action.
```

---

## UNKNOWN procedure

If lifecycle is UNKNOWN:

```text
STOP
DO NOT RETRY
DO NOT RESUBMIT
DO NOT CLOSE AUTOMATICALLY
VERIFY BROKER STATE READ-ONLY
RECONCILE INTENT
ONLY THEN CONTINUE
```

```text
EXECUTION STATE: UNKNOWN
ACTION REQUIRED: READ-ONLY BROKER RECONCILIATION
AUTOMATIC RESUBMISSION: DISABLED
```

---

## Second run

A second `--execute` must be **BLOCKED** by the demo smoke ledger.

Do **not** attempt a second real broker submission to “verify” idempotency.

---

## Related docs

- [`PHASE_12_7_REPORT.md`](PHASE_12_7_REPORT.md)
- [`evidence/phase-12-7/README.md`](evidence/phase-12-7/README.md)
- [`LIVE_EXECUTION_ARCHITECTURE.md`](LIVE_EXECUTION_ARCHITECTURE.md)
