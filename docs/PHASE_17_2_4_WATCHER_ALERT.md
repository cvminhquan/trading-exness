# PHASE 17.2.4 — Read-Only Watcher Alert

Operator alerts without staring at the terminal. Still **read-only**.

## Safety

- NO `order_send` / Orchestrator / GatedMT5 / Live transport
- NO `--execute` / `--confirm`
- Strategy / thresholds / weights unchanged

## Command

```bash
cd trading-engine
.\.venv\Scripts\python.exe -m exness_bot.cli candidate-demo-watch --symbol XAUUSD --beep
.\.venv\Scripts\python.exe -m exness_bot.cli candidate-demo-watch --symbol XAUUSD --beep --alert-log logs/candidate_watch_alerts.log
```

## Alerts

| Event | Banner |
|-------|--------|
| WAIT → LONG/SHORT (not ENTRY_ZONE) | `DIRECTIONAL SETUP DETECTED` |
| ENTRY_ZONE reached | `ENTRY_ZONE REACHED` |
| Ready (signal + ENTRY_ZONE + eligible + empty blocks) | `CONTROLLED DEMO CANDIDATE READY` |
| MTF score cross ±20 | threshold alert |
| Block reasons change | generic watch alert |

READY is **informational only** — run PREVIEW manually before any DEMO mutate.

## Anti-spam

Same `setup_id + setup_state + eligible + block_reasons` (+ alert kind) → alert once per watcher process.

## Beep / log

- `--beep`: `winsound.MessageBeep` on Windows, else terminal `\a`. Failures ignored.
- `--alert-log PATH`: append timestamped lines (no credentials).
