# Autonomous DEMO Execution (Phase 17.3)

**DEMO ONLY — NO real-money autonomous execution.**

## Purpose

Evaluate each **new closed M15** candle for `XAUUSD`, build the production
`ExecutionCandidate` (`mtf_technical_v1`), apply fail-closed gates, and submit
**at most one** order via the existing execution stack when eligible.

## Architecture (reuse only)

```text
Closed M15
  → AutonomousDemoExecutionLoop
  → ExecutionCandidate (mtf_technical_v1)
  → CandidateExecutionService
  → ExecutionOrchestrator
  → GatedMT5ExecutionPort
  → MT5Executor
  → LiveMT5ExecutionTransport   ← sole order_send path
```

Do **not** create a second execution architecture.

## Safe defaults

| Setting | Default |
|---------|---------|
| `AUTO_DEMO_EXECUTION_ENABLED` | `false` |
| `LIVE_KILL_SWITCH` | `true` |
| `LIVE_DEMO_APPROVAL` | `false` |
| `EXECUTION_MODE` | `paper` |
| `ALLOW_LEGACY_RUN` | `false` |

Autonomous execution requires **all** of:

- `TRADING_ENV=demo`
- `AUTO_DEMO_EXECUTION_ENABLED=true`
- `LIVE_DEMO_APPROVAL=true`
- `LIVE_KILL_SWITCH=false`
- login in `DEMO_ACCOUNT_ALLOWLIST`
- broker `trade_mode=demo` (unknown → **BLOCK**)

## Operator commands

```bash
python -m exness_bot.execution.auto_demo status
python -m exness_bot.execution.auto_demo preflight
python -m exness_bot.execution.auto_demo once --dry
python -m exness_bot.execution.auto_demo once
python -m exness_bot.execution.auto_demo run --dry
python -m exness_bot.execution.auto_demo run
```

### `preflight` (read-only)

Verifies DEMO account / allowlist / M15 / flags **without** requiring
`LIVE_KILL_SWITCH=false`. Never calls orchestrator / transport / `order_send`.

- API/dashboard **do not** auto-start this loop.
- Read-only status: `GET /api/v1/execution/auto-demo/status`

## Trigger

Only a **new closed M15** candle. Not ticks, dashboard poll, Analyst Chat, or External Intelligence.

## Idempotency

`decision_id = symbol|M15|closed_m15_timestamp|strategy_id`

Persisted before side effect. Same candle never double-submits across restart/reconnect/re-poll.

## Lifecycle

`OBSERVED → EVALUATING → ELIGIBLE → IN_FLIGHT → ACCEPTED|REJECTED|UNKNOWN|BLOCKED|SKIPPED`

- Persist **IN_FLIGHT before** broker side effect.
- **UNKNOWN never auto-resubmits.**

## Hot-read safety

Before each side effect, re-read from process env:

- `LIVE_KILL_SWITCH`
- `LIVE_DEMO_APPROVAL`
- `AUTO_DEMO_EXECUTION_ENABLED`
- `TRADING_ENV`

Other settings are startup-frozen.

## Boundaries

| Source | May drive orders? |
|--------|-------------------|
| `mtf_technical_v1` ExecutionCandidate | YES (only) |
| ExternalMarketContext / Synthesis / Chat / Gemini / Grounding / RSS / BLS | NO |
| Analyst Chat “mở lệnh” | NO broker action |

## Position policy

Respect `MAX_OPEN_POSITIONS` (default 1). Do not auto-close to make room.
Execution plan remains **TP1_ONLY**.

## Kill switch

`LIVE_KILL_SWITCH=true` blocks **new** submissions immediately on next evaluation.
Does not auto-close open positions.
