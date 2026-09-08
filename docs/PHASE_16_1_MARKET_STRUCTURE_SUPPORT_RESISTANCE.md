# PHASE 16.1 — Market Structure & Support/Resistance

## Status

```text
PASS
```

**Ngày:** 2026-09-07  
**Phạm vi:** Mở rộng Phase 16 analysis bằng swing / structure / S-R **chỉ đọc**.  
**Không** rewrite strategy EMA/RSI/ATR. **Không** `order_send` / ExecutionOrchestrator.

---

## Objective

Thêm ngữ cảnh cấu trúc thị trường vào `TradeAnalysis` hiện có:

- Confirmed Swing High / Swing Low
- HH / HL / LH / LL
- Structure: BULLISH / BEARISH / RANGE / UNDETERMINED
- Support / Resistance (clustered)
- Nearest S/R + khoảng cách (giá & ATR)
- `strategySignal` giữ nguyên; `contextAssessment` có thể BLOCKED độc lập

---

## Algorithm

### Swing confirmation (no look-ahead)

Tham số: `SWING_LEFT_BARS` (mặc định 2), `SWING_RIGHT_BARS` (mặc định 2).

Chỉ chạy trên **nến đã đóng** (`closed_candles_only`).

Swing tại index `i` **chỉ confirmed** khi tồn tại đủ bars đóng tới index `i + SWING_RIGHT_BARS`.

- Swing High: `high[i]` cao hơn mọi high trong `[i-left, i) ∪ (i, i+right]`
- Swing Low: `low[i]` thấp hơn mọi low trong cùng cửa sổ

Pivot gần mép phải chuỗi (chưa đủ `right` bars) **không** được coi là confirmed → tránh look-ahead.

### HH / HL / LH / LL

So sánh lần lượt swing cùng loại với swing trước:

- High mới > high trước → HH; ngược lại → LH
- Low mới > low trước → HL; ngược lại → LL

### Structure classification

- Cặp gần đây HH+HL → **BULLISH**
- Cặp gần đây LH+LL → **BEARISH**
- Có nhãn lẫn / xung đột → **RANGE**
- Không đủ swing/nhãn → **UNDETERMINED**

### Support / Resistance

- Support = cluster các confirmed swing lows
- Resistance = cluster các confirmed swing highs
- **Không** dùng min/max N nến gần nhất làm nguồn chính

### Clustering

Tolerance:

```text
tolerance = ATR14 * SR_CLUSTER_ATR_MULTIPLIER   # default 0.25
# fallback nếu thiếu ATR: max(point * 50, point)
```

Mỗi level:

| Field | Ý nghĩa |
|-------|---------|
| price | trung bình cluster |
| type | SUPPORT \| RESISTANCE |
| touchCount | số swing trong cluster |
| strength | = touchCount (đơn giản, giải thích được) |
| firstSeen / lastSeen | timestamp swing đầu/cuối |

### Nearest + distance

Với entry đề xuất Phase 16:

- `nearestSupport` = support cao nhất **dưới** entry (hoặc null)
- `nearestResistance` = resistance thấp nhất **trên** entry (hoặc null)
- `distanceToSupport` / `distanceToResistance` = khoảng giá
- `*Atr` = khoảng / ATR14

### Context filtering (không đổi strategySignal)

| strategySignal | contextAssessment |
|----------------|-------------------|
| WAIT | NOT_APPLICABLE |
| BUY/SELL | PASS / CAUTION / BLOCKED |

Ví dụ BUY:

- Resistance ≤ `SR_NEAR_ATR_THRESHOLD` ATR → `RESISTANCE_TOO_CLOSE` → **BLOCKED**
- TP vượt resistance mạnh (touch≥2) → `TP_CROSSES_RESISTANCE` (không tự sửa TP)
- So sánh ATR SL vs support → lý do `SL_ABOVE_SUPPORT` / `SL_BELOW_SUPPORT` (không sửa SL)

SELL tương tự với support / `TP_CROSSES_SUPPORT`.

Khi `contextAssessment=BLOCKED`, `executionStatus` cũng BLOCKED nếu trước đó READY — **`signal` / `strategySignal` vẫn BUY|SELL**.

---

## Configs added

| Env | Default |
|-----|---------|
| `SWING_LEFT_BARS` | 2 |
| `SWING_RIGHT_BARS` | 2 |
| `SR_CLUSTER_ATR_MULTIPLIER` | 0.25 |
| `SR_NEAR_ATR_THRESHOLD` | 0.5 |
| `SR_CAUTION_ATR_THRESHOLD` | 1.0 |

---

## API changes (additive)

Giữ nguyên các field Phase 16. Thêm:

```json
{
  "strategySignal": "BUY",
  "contextAssessment": "BLOCKED",
  "structure": {
    "classification": "BULLISH",
    "latestSwingHigh": 2360.2,
    "latestSwingLow": 2338.4,
    "sequence": ["HH", "HL", "HH"],
    "nearestSupport": 2338.4,
    "nearestResistance": 2355.0,
    "distanceToSupport": 11.9,
    "distanceToResistance": 4.7,
    "distanceToSupportAtr": 2.67,
    "distanceToResistanceAtr": 1.05
  }
}
```

`signal` vẫn là tín hiệu chiến lược Phase 16 (backward compatible).

---

## UI changes

`TradeAnalysisCard`:

- Hiển thị `strategySignal` + `contextAssessment`
- Section **Cấu trúc thị trường**: classification, sequence HH→HL, support/resistance, khoảng cách ATR
- Reasons ✓/✕ bao gồm structure codes
- Không thêm nút giao dịch

### Chart overlay

Dashboard chưa có candle chart architecture phù hợp → **deferred**.  
Dữ liệu swing/level có trong engine (`structure.swings` / levels nội bộ); API hiện expose nearest + sequence. Overlay chart ghi nhận là hạn chế còn lại.

---

## Files changed

| Path | Vai trò |
|------|---------|
| `market_analysis/swings.py` | Confirmed swings |
| `market_analysis/structure.py` | HH/HL/LH/LL + classification |
| `market_analysis/levels.py` | S/R clustering + nearest |
| `market_analysis/context.py` | contextAssessment |
| `market_analysis/service.py` | Wire vào analyze() |
| `market_analysis/models.py` | Additive fields |
| `config/settings.py` | Swing/S-R settings |
| `api/schemas/dashboard.py` | `AnalysisStructureDTO`, fields mới |
| `api/services/read_service.py` | Map structure |
| `dashboard/.../TradeAnalysisCard.tsx` | UI structure |
| `dashboard/domain/schemas.ts` | Zod additive |
| `tests/unit/test_phase_16_1_market_structure.py` | Unit tests |
| `.env.example` | Config keys |

---

## Tests

```text
pytest: 830 passed (Phase 16.1 suite included)
mypy (market_analysis + read_service): Success
dashboard typecheck: PASS
vitest: 39 passed
```

Coverage checklist: swing high/low, no look-ahead, HH/HL/LH/LL paths, bullish/bearish/range/undetermined, S/R + clustering + nearest, ATR distance, BUY near resistance, SELL near support, TP crosses, WAIT NOT_APPLICABLE, no order_send in structure modules.

---

## Safety audit

- Không `order_send(` trong modules 16.1
- Không `ExecutionOrchestrator` / `LiveMT5ExecutionTransport`
- Không sửa Entry/SL/TP Phase 16 — chỉ đánh giá ngữ cảnh
- Dashboard không có control khớp lệnh mới

---

## Remaining limitations

1. Chart overlay S/R **chưa** vẽ (không có candle chart sẵn) — deferred.
2. Strength = touchCount đơn giản; chưa weight theo volume/time decay phức tạp.
3. Structure classification heuristic trên cửa sổ nhãn gần đây — thị trường choppy → RANGE thường xuyên.
4. Live `EmaRsiAtrStrategy` (signal engine) vẫn độc lập với rule Phase 16 analysis (đã ghi ở Phase 16).
5. Levels chi tiết (full list swings) chưa expose full trên API public — chỉ nearest + sequence.

---

## Final

```text
PHASE 16.1 RESULT: PASS
```

Không claim profitability. Không khớp lệnh broker.
