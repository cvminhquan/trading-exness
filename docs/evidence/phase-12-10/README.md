# Phase 12.10 Evidence Pack

Operator-controlled DEMO one-shot evidence for Phase 12.10.

**Do not commit** private account numbers, passwords, tokens, or full login IDs.
Use masked login only (example: `***4158`).

## Files

| File | Purpose |
|------|---------|
| [`../phase-12-7/schema.md`](../phase-12-7/schema.md) | Field schema for sanitized evidence |
| `smoke-YYYYMMDD-HHMMSS.json` | Optional operator-filled evidence (keep local if sensitive) |

## Agent rule

The agent may run **read-only** preflight:

```bash
exness-bot demo-execution-smoke
```

The agent must **not** run:

```bash
exness-bot demo-execution-smoke --execute --confirm DEMO-EXECUTE
```

## After human smoke

1. Capture terminal output (sanitize).
2. Read-only reconcile order / deal / position.
3. Confirm `transport_send_count <= 1`.
4. If a position is open — document it; do **not** auto-close.
5. Restore `LIVE_KILL_SWITCH=true` and `LIVE_DEMO_APPROVAL=false`.
6. Optionally copy sanitized JSON here.
