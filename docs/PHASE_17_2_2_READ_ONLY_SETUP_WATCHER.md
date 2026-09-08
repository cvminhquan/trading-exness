# PHASE 17.2.2 — Read-Only Setup Watcher

Monitor MTF setup readiness without broker mutation.

## Result scope

`candidate-demo-watch` observes:

MTF analysis → CanonicalTradeSetup → ExecutionCandidate eligibility → PREVIEW diagnostics

It **never** reaches:

- `ExecutionOrchestrator.submit`
- `GatedMT5ExecutionPort`
- `MT5Executor`
- `LiveMT5ExecutionTransport`
- `order_send`

There is **no** `--execute` / `--confirm` flag.

---

## Command

```bash
cd trading-engine
.\.venv\Scripts\python.exe -m exness_bot.cli candidate-demo-watch --symbol XAUUSD
```

Optional:

```bash
.\.venv\Scripts\python.exe -m exness_bot.cli candidate-demo-watch --symbol XAUUSD --interval-seconds 15
```

- Default interval: **15** seconds
- Minimum interval: **5** seconds

Agent may run this command (read-only).

Agent must **never** run:

```bash
candidate-demo-execution-smoke --execute --confirm DEMO-EXECUTE
```

---

## Architecture (read-only)

```text
MT5ReadOnlyClient + MT5ConnectionManager
        ↓
MT5TradingDataProvider (get_candles / get_tick / snapshot)
        ↓
MultiTimeframeAnalysisService (CLOSED candles only)
        ↓
ExecutionContractService.evaluate_from_analysis
        ↓
WatchSnapshot + change detection + READY banner
```

Shared builder: `execution/integration/candidate_status.py`  
(reused by PREVIEW smoke and watcher — no demo_factory / gated port).

---

## Polling behavior

- Full report on meaningful state changes
- Compact heartbeat when unchanged, e.g. `[18:30:15] XAUUSD NO_SETUP WAIT`
- Ctrl+C → graceful stop, disconnect read-only client, print:

```text
Watcher stopped.
Broker mutation performed: NO
```

---

## State transitions (reported)

| Change | Full report |
|--------|-------------|
| WAIT → LONG/SHORT | yes |
| NO_SETUP → WAITING_FOR_ENTRY | yes |
| WAITING_FOR_ENTRY ↔ ENTRY_ZONE | yes |
| → INVALIDATED / EXPIRED / SUPERSEDED | yes |
| eligible false ↔ true | yes |
| block reasons / setup_id change | yes |

---

## READY semantics

Emitted **once per transition into** ready when:

- `FINAL_SIGNAL` ∈ {LONG, SHORT}
- `SETUP_STATE` = ENTRY_ZONE
- `CANDIDATE_ELIGIBLE` = true
- `BLOCK_REASONS` empty

READY is **informational only**. It does **not** authorize execution.

Operator next step:

```bash
.\.venv\Scripts\python.exe -m exness_bot.cli candidate-demo-execution-smoke --symbol XAUUSD
```

(independent PREVIEW revalidation — still no mutation unless human adds `--execute --confirm DEMO-EXECUTE`).

---

## Closed-candle invariant

M15 / H1 / H4 / D1 directional analysis uses **closed candles only**.

Quote updates may change:

- spread diagnostics
- WAITING_FOR_ENTRY ↔ ENTRY_ZONE
- executable price

They must **not** mint a new strategy signal every tick.

---

## Setup identity stability

Same source candle + direction → same `setup_id` / fingerprint across polls.

Quote-only movement may flip entry-zone state without changing setup identity.

---

## Safety boundary

| Action | Watcher |
|--------|---------|
| Read MT5 account/quotes/candles | yes |
| Build ExecutionCandidate status | yes |
| Print diagnostics / READY | yes |
| Call orchestrator / gated submit | **no** |
| `order_send` | **no** |
| Auto-run `--execute` | **no** |

---

## Operator workflow

1. Run `candidate-demo-watch` and wait for READY (or meaningful ENTRY_ZONE progress).
2. Manually run `candidate-demo-execution-smoke` PREVIEW to revalidate.
3. Only a human may authorize the one-shot mutate path (Phase 17.2 runbook).

---

## Disconnect handling

If MT5 disconnects or MTF data is unavailable:

- `DATA_STATE: DISCONNECTED` / `UNAVAILABLE`
- `CANDIDATE_ELIGIBLE: false`
- watcher continues polling / reconnect attempts
- no execution side effects
