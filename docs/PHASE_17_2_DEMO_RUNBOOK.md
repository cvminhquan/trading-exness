# PHASE 17.2 — Operator DEMO Runbook

Controlled one-shot: `ExecutionCandidate` (`mtf_technical_v1`) → gated Exness DEMO.

## Agent rule

**Do not ask Cursor / AI to run mutation.** Agents must never execute:

```bash
exness-bot candidate-demo-execution-smoke --execute --confirm DEMO-EXECUTE
```

---

## Prerequisites

1. Open MetaTrader 5 with the intended **DEMO** account.
2. Confirm account trade mode is DEMO in MT5 (do not trust server name alone).
3. Enable **Algo Trading** in the terminal.
4. Keep repository defaults safe until the moment of the one-shot:
   - `LIVE_KILL_SWITCH=true`
   - `LIVE_DEMO_APPROVAL=false`
   - `EXECUTION_MODE=paper`

## Temporary overrides (operator machine only — never commit secrets)

Conceptual requirements (do not print passwords):

```text
TRADING_ENV=demo
LIVE_KILL_SWITCH=false
LIVE_DEMO_APPROVAL=true
DEMO_ACCOUNT_ALLOWLIST=<your demo login>
DEMO_SERVER_ALLOWLIST=<your demo server>
LIVE_SYMBOL_MAP=XAUUSD:XAUUSDm
```

Ensure `.env` is gitignored.

---

## Step-by-step

### 1. Read-only preview (safe — agent may run this)

```bash
cd trading-engine
.\.venv\Scripts\python.exe -m exness_bot.cli candidate-demo-execution-smoke --symbol XAUUSD
```

### 1b. Read-only setup watcher (safe — agent may run this)

Wait for a real MTF directional setup without manufacturing signals:

```bash
.\.venv\Scripts\python.exe -m exness_bot.cli candidate-demo-watch --symbol XAUUSD
```

See `docs/PHASE_17_2_2_READ_ONLY_SETUP_WATCHER.md`. READY is informational only — still run PREVIEW (#1) before any human mutate.
Expect:

- `MODE: CONTROLLED DEMO PREVIEW`
- `REAL order_send: NO`
- Precheck + DEMO gates reported
- `TP POLICY: TP1_ONLY`

If **BLOCKED** → **STOP**. Fix data / risk / gates. Do not execute.

### 2. Inspect

- Setup state must be `ENTRY_ZONE`
- Candidate eligible; `riskAcceptable` and `brokerExecutable`
- `proposed_volume` from candidate (not a forced 0.01 smoke constant)
- Spread / quote age acceptable
- For ~$10.50 equity: if min lot risk exceeds budget → expect block (`MIN_VOLUME_EXCEEDS_RISK_BUDGET` / risk flags). Do **not** force volume.

### 3. Human-only mutation (optional)

Only if preview is READY:

```bash
exness-bot candidate-demo-execution-smoke \
  --symbol XAUUSD \
  --execute \
  --confirm DEMO-EXECUTE
```

Record full terminal output.

### 4. After submit

- Inspect MT5 positions / history **read-only**.
- If `EXECUTION STATE: UNKNOWN`:
  - **ACTION REQUIRED: READ-ONLY BROKER RECONCILIATION**
  - **AUTOMATIC RESUBMISSION: DISABLED**
  - **Do not simply rerun `--execute`.**
- Open DEMO positions are **not** auto-closed — operator manages manually.

### 5. Restore safe defaults

```text
LIVE_KILL_SWITCH=true
LIVE_DEMO_APPROVAL=false
EXECUTION_MODE=paper
```

---

## Evidence package (operator)

Attach:

1. Preview terminal output
2. Execute terminal output (if performed)
3. Masked account login / server / symbol
4. MT5 screenshots (order / deal / position) — no passwords
5. Note: `ORDER_SEND CALL COUNT` ≤ 1

Store under `docs/evidence/` only if the project convention requires it (e.g. Phase 12.10 style).
