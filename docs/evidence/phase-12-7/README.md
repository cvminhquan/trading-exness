# Phase 12.7 Evidence Pack

Operator-controlled DEMO one-shot evidence templates.

**Do not commit** private account numbers, passwords, tokens, or full login IDs.

Use masked login only (example: `***4158`).

## Files

| File | Purpose |
|------|---------|
| [`schema.md`](schema.md) | Field schema for sanitized evidence |
| `smoke-YYYYMMDD-HHMMSS.json` | Optional operator-filled evidence (gitignored locally if sensitive) |

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

Copy sanitized fields from CLI logs (`demo_smoke_evidence`) into a local JSON matching `schema.md`.
