# PHASE 17.2 SERIES REPORT

**Ngày:** 2026-09-08  
**Phạm vi:** Controlled DEMO candidate path + read-only observability  
**Strategy canonical:** `mtf_technical_v1`

---

## Tổng kết

| Phase | Tên | Kết quả |
|-------|-----|---------|
| 17.2 | Controlled DEMO candidate execution | **PASS** (impl) / evidence mutate = PENDING human |
| 17.2.1 | Preview reason quality (spread + NO_SETUP) | **PASS** |
| 17.2.2 | Read-only setup watcher | **PASS** |
| 17.2.3 | MTF decision diagnostics | **PASS** |
| 17.2.4 | Read-only watcher alerts | **PASS** |
| 17.2.5 | Dashboard Trade Analysis UX redesign | **PASS** |
| 17.2.5C | Densify / contrast / terminal hierarchy | **PASS** |
| 17.2.5D | Bright modern visual redesign (mockup) | **PASS** |

```text
REAL MT5 order_send executed by agent: NO
Automatic execution: NO
Strategy rules / MTF thresholds changed: NO
Dashboard execution mutation path: NO
```

---

## 1. PHASE 17.2 — Controlled DEMO

### Mục tiêu

`ExecutionCandidate` → gated DEMO one-shot, mặc định **PREVIEW** read-only.

### CLI

```bash
# PREVIEW (agent được phép)
exness-bot candidate-demo-execution-smoke --symbol XAUUSD

# MUTATE (CHỈ HUMAN — agent cấm)
exness-bot candidate-demo-execution-smoke --symbol XAUUSD --execute --confirm DEMO-EXECUTE
```

### Kết quả kỹ thuật

- Volume lấy từ `candidate.proposed_volume` (không ép Phase-12 `0.01`)
- Revalidate entry/SL/TP1/spread trước submit
- `EXECUTED_TP_POLICY=TP1_ONLY`
- Docs: `PHASE_17_2_CONTROLLED_DEMO_EXECUTION.md`, `PHASE_17_2_DEMO_RUNBOOK.md`

### Evidence DEMO mutate

**PENDING** — cần human chạy one-shot khi có candidate READY.

---

## 2. PHASE 17.2.1 — Preview reason quality

### Bug đã sửa

`CURRENT_SPREAD_POINTS ≈ MAX_SPREAD_POINTS` vẫn ra `SPREAD_TOO_WIDE` vì so sánh float thô (`>`).

### Sửa

- Module `market_analysis/contract/spread.py`
- Semantic: `spread <= max` → allowed; `spread > max` → blocked
- Normalize + eps; **không** đổi `MAX_SPREAD_POINTS`

### Reason precedence (NO_SETUP)

Khi `FINAL_SIGNAL_WAIT` / `NO_DIRECTIONAL_SETUP`:

- **Không** gắn `VOLUME_INVALID` / `RISK_NOT_ACCEPTABLE`
- Diagnostics: entry/volume = N/A

### Boundary tests

| Spread | Kết quả |
|--------|---------|
| 259 | pass |
| 260 | pass |
| 261 | block |

---

## 3. PHASE 17.2.2 — Read-only setup watcher

### CLI

```bash
exness-bot candidate-demo-watch --symbol XAUUSD
exness-bot candidate-demo-watch --symbol XAUUSD --interval-seconds 15
```

- Không có `--execute` / `--confirm`
- Không import Orchestrator / GatedMT5 / Live transport / `order_send`

### Hành vi

- Poll MTF → setup → eligibility
- Full report khi state đổi; heartbeat khi giữ nguyên
- Banner `CONTROLLED DEMO CANDIDATE READY` (informational only)
- Ctrl+C: `Watcher stopped. / Broker mutation performed: NO`

### Docs

`docs/PHASE_17_2_2_READ_ONLY_SETUP_WATCHER.md`

---

## 4. PHASE 17.2.3 — MTF decision diagnostics

### Mục tiêu

Giải thích **vì sao** `mtf_technical_v1` trả LONG / SHORT / WAIT — observability only.

### CLI

```bash
exness-bot candidate-demo-watch --symbol XAUUSD --verbose-analysis
```

### Engine (không đổi)

| Hạng mục | Giá trị |
|----------|---------|
| LONG | weighted ≥ **20** |
| SHORT | weighted ≤ **-20** |
| WAIT | còn lại, hoặc H4/D1 conflict force |
| Weights | M15 0.20 / H1 0.30 / H4 0.30 / D1 0.20 |

`MTF_WEIGHTED_SCORE` diagnostics = đúng float từ `_aggregate` (`MtfAggregateTrace`).

### Real MT5 snapshot (2026-09-08 ~21:26 UTC+7)

```text
M15:  +6.68
H1 : -21.62
H4 : +18.00
D1 : -34.00

WEIGHTED: -6.55
THRESHOLDS: SHORT <= -20 | LONG >= 20

H1_H4_CONFLICT: NO
H4_D1_CONFLICT: NO

FINAL: WAIT
CONFIDENCE: 36.44
CONFIDENCE_MEANING: EVIDENCE_ALIGNMENT

WHY:
- SCORE_INSIDE_WAIT_ZONE
- STRUCTURE_MIXED

SPREAD: NORMALIZED=260.0 / MAX=260 (allowed)
SETUP_STATE: NO_SETUP
CANDIDATE_ELIGIBLE: false
BLOCK_REASONS: FINAL_SIGNAL_WAIT, NO_DIRECTIONAL_SETUP

BROKER MUTATION: NO
ORDER_SEND: NO
```

**Diễn giải:** Bot không “hỏng”. Score MTF (-6.55) nằm trong vùng WAIT; structure mixed (M15/H1/H4 BULLISH vs D1 BEARISH). Chưa có directional setup → chưa thu thập evidence DEMO one-shot.

### Docs

`docs/PHASE_17_2_3_MTF_DECISION_DIAGNOSTICS.md`

---

## 5. Validation gần nhất

```text
pytest tests/unit : 948 passed
ruff check src tests : clean
mypy src : clean
```

Watcher / verbose smoke: agent chạy read-only OK.

---

## 6. Operator workflow (tiếp theo)

1. Chạy watcher (tuỳ chọn verbose):

   ```bash
   cd trading-engine
   .\.venv\Scripts\python.exe -m exness_bot.cli candidate-demo-watch --symbol XAUUSD --verbose-analysis
   ```

2. Đợi `FINAL: LONG|SHORT` + `SETUP_STATE: ENTRY_ZONE` + READY (hoặc gần READY).

3. PREVIEW độc lập:

   ```bash
   .\.venv\Scripts\python.exe -m exness_bot.cli candidate-demo-execution-smoke --symbol XAUUSD
   ```

4. **Chỉ human** mới được mutate:

   ```bash
   .\.venv\Scripts\python.exe -m exness_bot.cli candidate-demo-execution-smoke --symbol XAUUSD --execute --confirm DEMO-EXECUTE
   ```

---

## 7. Safety audit (bắt buộc)

| Check | Status |
|-------|--------|
| REAL MT5 `order_send` (agent) | **NO** |
| `ExecutionOrchestrator` từ watcher | **NO** |
| `LiveMT5ExecutionTransport` từ watcher | **NO** |
| Automatic execution | **NO** |
| Strategy / threshold thay đổi vì diagnostics | **NO** |
| DEMO mutate evidence | **PENDING (human)** |

---

## 17.2.4 Watcher alerts

```bash
.\.venv\Scripts\python.exe -m exness_bot.cli candidate-demo-watch --symbol XAUUSD --beep --alert-log logs/candidate_watch_alerts.log
```

Alerts (directional / ENTRY_ZONE / READY) are informational only. See `docs/PHASE_17_2_4_WATCHER_ALERT.md`.

---

## 17.2.5 Dashboard Trade Analysis UX

Hierarchy: Hero → Setup/Risk → Reasons → MTF (collapsed). READ-ONLY. Chi tiết: `docs/PHASE_17_2_5_DASHBOARD_TRADE_ANALYSIS_UX.md`.

## 17.2.5C / 17.2.5D Visual redesign

- **17.2.5C:** densify / contrast / terminal hierarchy — `docs/PHASE_17_2_5C_VISUAL_REDESIGN.md`
- **17.2.5D:** bright modern mockup (Financial Blue, SymbolTabs sparkline + Thêm, Realized PnL 7/30, AccountSwitcher pill + loading) — `docs/PHASE_17_2_5D_REPORT.md`

UI-only. Không đổi strategy / ExecutionCandidate / `order_send`.

---

## File chính

| Path | Vai trò |
|------|---------|
| `execution/integration/demo_cli.py` | PREVIEW / DEMO smoke |
| `execution/integration/demo_watch.py` | Read-only watcher |
| `execution/integration/demo_watch_alerts.py` | Alert dedupe / beep / log |
| `execution/integration/candidate_status.py` | Builder status (shared) |
| `market_analysis/contract/spread.py` | Spread normalize/compare |
| `market_analysis/mtf_service.py` | Aggregate + `MtfAggregateTrace` |
| `market_analysis/mtf_diagnostics.py` | Decision diagnostics format |
| `docs/PHASE_17_2_*.md` | Spec / runbook / watcher / diagnostics |

---

## Verdict

```text
PHASE 17.2 SERIES IMPLEMENTATION: PASS
PHASE 17.2 DEMO MUTATE EVIDENCE: CONDITIONAL (await human + real READY candidate)
CURRENT MARKET STATE: WAIT / NO_SETUP — expected, not a pipeline failure
```
