# PHASE 16.3 — Analysis → Execution Contract Hardening

## Kết quả

Phase này **không** gửi lệnh broker. Chỉ hardening contract:

`MultiTimeframeAnalysis → CanonicalTradeSetup → SetupLifecycle → ExecutionCandidate → ExecutionEligibility`

Dừng tại đây. Phase 17 sẽ consume `ExecutionCandidate`.

## Canonical strategy source

| Source | Strategy ID | Vai trò Phase 16.3 / 17 |
|--------|-------------|-------------------------|
| Phase 16.2 MTF | `mtf_technical_v1` | **Canonical** — nguồn duy nhất tạo ExecutionCandidate |
| `EmaRsiAtrStrategy` | `ema_rsi_atr_v1` | **Legacy** — paper/backtest hiện tại; `LEGACY_NON_EXECUTABLE_FOR_PHASE_17` |
| Phase 16 `decide_signal` | `phase16_decide_signal_v1` | **Legacy read-only** — UI `/analysis/{symbol}` |

### Migration (không thực hiện trong 16.3)

1. Paper/backtest tiếp tục dùng `EmaRsiAtrStrategy`.
2. Phase 17 **không** được tạo candidate từ `ema_rsi_atr_v1` hoặc `phase16_decide_signal_v1`.
3. Khi migrate paper/DEMO: chuyển signal engine sang consume `ExecutionCandidate` / cùng rule MTF.
4. Flag kiểm soát: `LEGACY_NON_EXECUTABLE_STRATEGY_IDS` trong `contract/identity.py`.

## Setup identity

`setup_id = setup_sha256(strategy|symbol|M15|source_candle|direction|contract_version)[:24]`

Cùng closed candle → cùng ID (không random UUID).

## Fingerprint

Canonical JSON (sort_keys) trên: strategy, symbol, TF, candle, direction, entry zone, SL, TP prices, version.

Đổi field execution-relevant → fingerprint đổi.

## Lifecycle (durable SQLite / in-memory)

States: `NO_SETUP` | `WAITING_FOR_ENTRY` | `ENTRY_ZONE` | `INVALIDATED` | `EXPIRED` | `SUPERSEDED`

- Persist qua bảng `analysis_setup_lifecycle` (cùng `DATABASE_URL` sqlite).
- Poll API không tạo setup logic mới nếu cùng `setup_id`.
- Fingerprint/ID khác → setup cũ `SUPERSEDED`, setup mới active.
- `SETUP_MAX_CANDLES` (default 8) × duration M15 → `expires_at`.

## Invalidation / entry zone

- LONG: price ≤ SL → `INVALIDATED`; trong zone → `ENTRY_ZONE`; else `WAITING_FOR_ENTRY`.
- SHORT symmetrical.
- LONG alone ≠ executable. Cần `ENTRY_ZONE` + toàn bộ eligibility.

## Eligibility (strategy only — Phase-12 gates vẫn riêng)

Blocked khi thiếu bất kỳ điều kiện:

- finalSignal LONG/SHORT
- state ENTRY_ZONE, chưa expired/invalidated/superseded
- đủ M15/H1/H4/D1 (không INSUFFICIENT/STALE)
- quote/account fresh
- broker metadata đầy đủ (volume_min/step/max, tick_size/value, point, digits) — **không** fallback `contract_size=100`
- spread ≤ `MAX_SPREAD_POINTS`
- `riskAcceptable=true` (min lot broker-executable nhưng risk quá → vẫn block)
- không blocking S/R / HIGHER_TF_CONFLICT

## Blocking vs warning mapping

Xem `contract/reasons.py` — `BLOCKING_REASON_CODES` / `WARNING_REASON_CODES`.

## API

`GET /api/v1/analysis/{symbol}/execution-candidate` (read-only)

```json
{
  "eligible": false,
  "setupState": "WAITING_FOR_ENTRY",
  "candidate": null,
  "reasons": ["PRICE_NOT_IN_ENTRY_ZONE"],
  "strategyId": "mtf_technical_v1",
  "confidenceMeaning": "EVIDENCE_ALIGNMENT"
}
```

## Dashboard

`MultiTimeframeAnalysisCard` + eligibility:

- Setup state
- Execution eligibility ELIGIBLE / BLOCKED
- Reason codes

Không có nút Execute.

## Small account

`brokerExecutable` vs `riskAcceptable` giữ nguyên. ~$10.50 + min lot → thường `eligible=false`.

## Tests

`tests/unit/test_phase_16_3_execution_contract.py`

## Safety

Không `order_send` / `LiveMT5ExecutionTransport` / `ExecutionOrchestrator` / `GatedMT5ExecutionPort` trong `market_analysis/contract/`.

## Limitations

- Lifecycle SQLite chỉ khi `DATABASE_URL` sqlite; fallback in-memory.
- Account freshness đơn giản (presence), chưa age riêng nếu snapshot thiếu timestamp.
- Paper/backtest chưa migrate sang MTF.
- Không claim profitability.
