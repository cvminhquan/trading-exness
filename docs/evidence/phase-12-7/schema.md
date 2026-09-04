# Phase 12.7 Evidence Schema

Sanitized DEMO one-shot evidence. **Exclude** passwords, tokens, secrets, full credentials.

## Required fields

| Field | Type | Notes |
|-------|------|-------|
| `session_id` | string | Smoke session id |
| `timestamp_utc` | string | ISO-8601 UTC |
| `environment` | string | Must be `demo` |
| `broker` | string | Optional label |
| `server` | string | Connected broker server |
| `masked_account` | string | e.g. `***4158` |
| `symbol` | string | Canonical symbol |
| `broker_symbol` | string | Mapped broker symbol |
| `side` | string | LONG/SHORT or BUY/SELL |
| `requested_volume` | number | |
| `bid` | number \| null | Quote at decision |
| `ask` | number \| null | |
| `quote_age_seconds` | number \| null | |
| `quote_status` | string | `FRESH` or `STALE` |
| `preflight_status` | string | `PASS` / `BLOCKED` / `FAIL` |
| `intent_id` | string | |
| `idempotency_key` | string | |
| `lifecycle` | string | FILLED / REJECTED / UNKNOWN |
| `broker_retcode` | number \| null | If available |
| `broker_order` | string \| null | |
| `broker_deal` | string \| null | |
| `fill_price` | number \| null | |
| `filled_quantity` | number \| null | |
| `verified_position` | object \| null | ticket/symbol/side/volume/open/sl/tp |
| `reconciliation` | string \| null | CONFIRMED_FILLED / … / MATCH |
| `final_status` | string | Same as lifecycle or operator summary |
| `transport_send_count` | number | Must be `0` or `1` |
| `real_broker_submission` | boolean | |
| `open_position_policy` | string \| null | Open-position notice if any |

## Explicitly excluded

```text
password
access token
API key
private key
full unmasked login (prefer mask)
raw MT5 session objects
```

## Example (placeholder — not real evidence)

```json
{
  "session_id": "demo-smoke-example",
  "timestamp_utc": "2026-09-04T00:00:00+00:00",
  "environment": "demo",
  "server": "Exness-MT5Trial17",
  "masked_account": "***4158",
  "symbol": "XAUUSD",
  "broker_symbol": "XAUUSDm",
  "side": "LONG",
  "requested_volume": 0.01,
  "bid": 4470.0,
  "ask": 4470.2,
  "quote_age_seconds": 1.2,
  "quote_status": "FRESH",
  "preflight_status": "PASS",
  "intent_id": "…",
  "idempotency_key": "…",
  "lifecycle": "NOT_TESTED",
  "broker_retcode": null,
  "broker_order": null,
  "broker_deal": null,
  "fill_price": null,
  "filled_quantity": null,
  "verified_position": null,
  "reconciliation": null,
  "final_status": "NOT_TESTED",
  "transport_send_count": 0,
  "real_broker_submission": false,
  "open_position_policy": null
}
```
