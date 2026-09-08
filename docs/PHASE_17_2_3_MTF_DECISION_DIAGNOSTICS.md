# PHASE 17.2.3 — MTF Decision Diagnostics

Read-only observability for `mtf_technical_v1` WAIT / LONG / SHORT.

## Scope

Explains **why** the canonical MTF strategy returns a signal.

Does **not** change:

- MTF weights
- LONG/SHORT thresholds (±20)
- EMA / RSI / MACD / ATR / structure / S-R / pattern / volume rules
- confidence calculation
- setup generation / risk sizing

## Command

```bash
cd trading-engine
.\.venv\Scripts\python.exe -m exness_bot.cli candidate-demo-watch --symbol XAUUSD
.\.venv\Scripts\python.exe -m exness_bot.cli candidate-demo-watch --symbol XAUUSD --verbose-analysis
```

Still read-only. No `--execute` / `--confirm`.

## Architecture

```text
analyze_timeframe (closed candles)
  → ScoreBreakdown on each TF
MultiTimeframeAnalysisService._aggregate
  → MtfAggregateTrace (exact weighted_score + conflicts + final)
build_mtf_decision_diagnostics(...)
  → compact / verbose watcher output
```

`MTF_WEIGHTED_SCORE` in diagnostics **is** `MtfAggregateTrace.weighted_score` —
the same float used for `final_signal` (no parallel scoring engine).

## Thresholds (unchanged)

- LONG: weighted score `>= 20`
- SHORT: weighted score `<= -20`
- WAIT: otherwise, or H4/D1 conflict force

## Conflicts

| Code | Engine effect |
|------|----------------|
| H4/D1 (`HIGHER_TF_CONFLICT`) | force WAIT, conf × 0.6 |
| H1/H4 (`H1_H4_CONFLICT`) | conf × 0.75; score thresholds still apply |

## Watcher output

Full/change report prints compact `MTF DECISION` first, then setup/candidate block.

`--verbose-analysis` adds per-TF indicators + component scores from the same closed candles.

## Safety

No path to `ExecutionOrchestrator` / gated MT5 / `order_send`.
READY / diagnostics never authorize mutation.
